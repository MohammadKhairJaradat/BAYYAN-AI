import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  applyChatUpdate,
  createChatSession,
  getApiErrorMessage,
  getMyUsage,
  getPublicCapabilities,
  logChatMessage,
  sendChat,
  transcribeAudio,
  usageRequestHeaders,
} from "../services/api";
import type {
  ChatKind,
  ChatMessage,
  ChatProvider,
  ChatRole,
  PublicCapabilities,
  SubscriptionTier,
  UserUsage,
} from "../types/api";
import { useChatHistory } from "../contexts/hooks";
import { useAuth } from "../contexts/hooks";
import { useLang } from "../contexts/hooks";
import { useTaxProfile } from "../contexts/hooks";
import { ChatHistorySidebar } from "../components/chat/ChatHistorySidebar";
import { Mark, Icon } from "../components/brand";
import type {
  ChatMessage as ChatMessageType,
  ChatSource,
  ProfileUpdateSuggestion,
  ProfileUpdateValue,
} from "../types/api";

type ChatModelOption = {
  provider: ChatProvider;
  model: string;
  label: string;
};

type PendingAttachment = {
  id: string;
  file: File;
  documentType: "receipt";
};

const CHAT_MODEL_OPTIONS: ChatModelOption[] = [
  { provider: "gemini", model: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
  { provider: "gemini", model: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
  { provider: "openai", model: "gpt-5.4", label: "GPT-5.4" },
  { provider: "openai", model: "gpt-4o", label: "GPT-4o" },
  { provider: "anthropic", model: "claude-opus-4-7", label: "Claude Opus 4.7" },
  { provider: "groq", model: "llama-3.1-8b-instant", label: "Llama 3.1 8B (Groq)" },
];

const DEFAULT_CHAT_MODEL =
  CHAT_MODEL_OPTIONS.find((option) => option.model === "gemini-2.5-flash") ??
  CHAT_MODEL_OPTIONS[0];

function makePendingAttachment(file: File): PendingAttachment {
  return {
    id: `${file.name}-${file.size}-${file.lastModified}-${Math.random()
      .toString(36)
      .slice(2, 8)}`,
    file,
    documentType: "receipt",
  };
}

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function normalizeTier(tier?: string | null): SubscriptionTier {
  if (tier === "Pro" || tier === "Premium") return tier;
  return "Basic";
}

function localMessage(
  role: ChatRole,
  content: string,
  kind: ChatKind = "text",
  sessionId?: string | null,
): ChatMessage {
  return {
    id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    session_id: sessionId ?? "",
    role,
    kind,
    content,
    created_at: new Date().toISOString(),
  };
}

async function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const dataUrl = reader.result as string;
      const comma = dataUrl.indexOf(",");
      resolve(comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl);
    };
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

type WindowWithWebkitAudioContext = Window &
  typeof globalThis & {
    webkitAudioContext?: typeof AudioContext;
  };

function writeAscii(view: DataView, offset: number, value: string) {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i));
  }
}

function encodePcm16Wav(samples: Float32Array, sampleRate: number): ArrayBuffer {
  const bytesPerSample = 2;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, Number.isFinite(sample) ? sample : 0));
    view.setInt16(
      offset,
      clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff,
      true,
    );
    offset += bytesPerSample;
  }

  return buffer;
}

function mixAudioBufferToMono(audioBuffer: AudioBuffer): Float32Array {
  const channelCount = Math.max(1, audioBuffer.numberOfChannels);
  const mono = new Float32Array(audioBuffer.length);

  for (let channel = 0; channel < channelCount; channel += 1) {
    const data = audioBuffer.getChannelData(channel);
    for (let i = 0; i < data.length; i += 1) {
      mono[i] += data[i] / channelCount;
    }
  }

  return mono;
}

async function blobToMonoWav(blob: Blob): Promise<Blob> {
  const browserWindow = window as WindowWithWebkitAudioContext;
  const AudioContextCtor =
    browserWindow.AudioContext ?? browserWindow.webkitAudioContext;
  if (!AudioContextCtor) {
    throw new Error("Audio conversion is not supported in this browser.");
  }

  const audioContext = new AudioContextCtor();
  try {
    const arrayBuffer = await blob.arrayBuffer();
    const decoded = await audioContext.decodeAudioData(arrayBuffer.slice(0));
    const mono = mixAudioBufferToMono(decoded);
    return new Blob([encodePcm16Wav(mono, decoded.sampleRate)], {
      type: "audio/wav",
    });
  } finally {
    void audioContext.close().catch(() => undefined);
  }
}

const TIER_ORDER: SubscriptionTier[] = ["Basic", "Pro", "Premium"];
const CHAT_CARD_H = "clamp(560px, 76vh, 780px)";

/** Lowest tier whose allowlist unlocks a given model. */
function modelUnlockTier(model: string, capabilities: PublicCapabilities | null): SubscriptionTier {
  for (const tier of TIER_ORDER) {
    if (capabilities?.tiers.find((item) => item.name === tier)?.allowed_models.some((item) => item.model === model)) return tier;
  }
  return "Premium";
}

const TOTAL_KEYS = ["refund_due", "net_tax_due", "estimated_refund", "tax_due", "total"];

function isScalar(v: unknown): v is string | number {
  return typeof v === "string" || typeof v === "number";
}

function prettyKey(k: string): string {
  return k.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Defensive render of the loose `tax_breakdown` record as a Bayyan card. */
function BreakdownCard({ data, title }: { data: Record<string, unknown>; title: string }) {
  const entries = Object.entries(data).filter(([, v]) => isScalar(v));
  if (entries.length === 0) return null;
  const totalEntry = entries.find(([k]) => TOTAL_KEYS.includes(k.toLowerCase()));
  const rows = entries.filter(([k]) => k !== totalEntry?.[0]);
  return (
    <div style={{ marginTop: 12, borderRadius: 13, border: "1px solid var(--green-tint2)", background: "var(--paper)", overflow: "hidden" }}>
      <div className="row" style={{ gap: 8, padding: "10px 14px", borderBottom: "1px solid var(--green-tint2)", background: "var(--green-tint)" }}>
        <Icon name="coins" size={15} color="var(--green)" />
        <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--green-deep)" }}>{title}</span>
      </div>
      <div style={{ padding: "6px 14px 10px" }}>
        {rows.map(([k, v], i) => (
          <div key={k} className="row-between" style={{ padding: "7px 0", borderBottom: i < rows.length - 1 ? "1px solid var(--line)" : "none" }}>
            <span className="t-small" style={{ fontSize: 12.5 }}>{prettyKey(k)}</span>
            <span className="num" style={{ fontSize: 13.5, fontWeight: 600, color: "var(--ink)" }}>{String(v)}</span>
          </div>
        ))}
        {totalEntry && (
          <div className="row-between" style={{ marginTop: 8, padding: "10px 12px", borderRadius: 10, background: "var(--green-tint)" }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--green-deep)" }}>{prettyKey(totalEntry[0])}</span>
            <span className="num" style={{ fontSize: 16, fontWeight: 700, color: "var(--green)" }}>{String(totalEntry[1])}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function CitationLine({ sources }: { sources: ChatSource[] }) {
  const cites = sources
    .map((source) => {
      const base = source.label || source.citation;
      if (!base) return "";
      const meta: string[] = [];
      if (source.kind === "advisor_report" && source.stale !== undefined && source.stale !== null) {
        meta.push(source.stale ? "stale" : "fresh");
      }
      if (source.tax_year) meta.push(String(source.tax_year));
      return meta.length > 0 ? `${base} (${meta.join(", ")})` : base;
    })
    .filter(Boolean);
  if (cites.length === 0) return null;
  return (
    <div className="row" style={{ gap: 6, marginTop: 7, paddingInline: 4, flexWrap: "wrap" }}>
      <Icon name="scale" size={13} color="var(--green)" />
      <span className="green" style={{ fontWeight: 600, fontSize: 12 }}>{cites.join(" · ")}</span>
    </div>
  );
}

function fmtUpdateValue(v: ProfileUpdateValue | undefined): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "✓" : "✗";
  if (typeof v === "number") return v.toLocaleString();
  return String(v);
}

type UpdateCardState = "idle" | "loading" | "applied" | "dismissed" | "error";

/** One in-chat "update your profile?" confirm card (mirrors BreakdownCard styling). */
function ProfileUpdateCard({
  suggestion,
  profileId,
}: {
  suggestion: ProfileUpdateSuggestion;
  profileId?: string | null;
}) {
  const { t, lang } = useLang();
  const { profile, refreshTaxProfile } = useTaxProfile();
  const u = t.chat.update;
  const [state, setState] = useState<UpdateCardState>("idle");
  const label = lang === "ar" ? suggestion.label_ar : suggestion.label_en;
  const disabled = state === "loading" || state === "applied" || state === "dismissed";

  async function apply(entityId: string | null) {
    if (!profileId) {
      setState("error");
      return;
    }
    setState("loading");
    try {
      await applyChatUpdate(profileId, {
        entity: suggestion.entity,
        field: suggestion.field,
        action: suggestion.action === "create" ? "create" : "update",
        new_value: suggestion.new_value ?? null,
        entity_id: entityId,
        category: suggestion.category ?? null,
      }, profile?.id === profileId ? profile.version : undefined);
      setState("applied");
      void refreshTaxProfile().catch(() => undefined);
    } catch {
      setState("error");
    }
  }

  const btn = (variant: "fill" | "ghost") => ({
    padding: "7px 14px",
    borderRadius: 9,
    fontSize: 12.5,
    fontWeight: 700,
    cursor: disabled ? "default" : "pointer",
    border: `1px solid ${variant === "fill" ? "var(--green)" : "var(--line)"}`,
    background: variant === "fill" ? "var(--green)" : "transparent",
    color: variant === "fill" ? "#fff" : "var(--ink)",
    opacity: disabled ? 0.55 : 1,
  });

  return (
    <div style={{ borderRadius: 13, border: "1px solid var(--green-tint2)", background: "var(--paper)", overflow: "hidden" }}>
      <div className="row" style={{ gap: 8, padding: "9px 14px", borderBottom: "1px solid var(--green-tint2)", background: "var(--green-tint)" }}>
        <Icon name="user" size={14} color="var(--green)" />
        <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--green-deep)" }}>{u.heading}</span>
      </div>
      <div style={{ padding: "10px 14px" }}>
        <p style={{ fontSize: 13, color: "var(--ink)", marginBottom: 8 }}>{label}</p>
        {suggestion.action !== "create" && (
          <div className="row" style={{ gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
            <span className="t-small" style={{ fontSize: 12 }}>{u.from}: <b>{fmtUpdateValue(suggestion.current_value)}</b></span>
            <span className="t-small" style={{ fontSize: 12 }}>→</span>
            <span className="green" style={{ fontSize: 12, fontWeight: 700 }}>{u.to}: {fmtUpdateValue(suggestion.new_value)}</span>
          </div>
        )}

        {state === "applied" ? (
          <span className="green" style={{ fontSize: 12.5, fontWeight: 700 }}>{u.applied}</span>
        ) : state === "dismissed" ? (
          <span className="t-small" style={{ fontSize: 12.5 }}>{u.dismissed}</span>
        ) : suggestion.action === "choose" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <span className="t-small" style={{ fontSize: 12 }}>{u.choosePrompt}</span>
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              {(suggestion.options ?? []).map((opt) => (
                <button key={opt.entity_id} disabled={disabled} style={btn("ghost")} onClick={() => void apply(opt.entity_id)}>
                  {opt.label} ({fmtUpdateValue(opt.current_value)})
                </button>
              ))}
              <button disabled={disabled} style={btn("ghost")} onClick={() => setState("dismissed")}>{u.keep}</button>
            </div>
          </div>
        ) : (
          <div className="row" style={{ gap: 8 }}>
            <button disabled={disabled} style={btn("fill")} onClick={() => void apply(suggestion.entity_id ?? null)}>{u.apply}</button>
            <button disabled={disabled} style={btn("ghost")} onClick={() => setState("dismissed")}>{u.keep}</button>
            {state === "error" && <span style={{ fontSize: 12, color: "var(--clay, #b4541f)" }}>{u.failed}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

function ProfileUpdateCards({ updates, profileId }: { updates: ProfileUpdateSuggestion[]; profileId?: string | null }) {
  if (updates.length === 0) return null;
  return (
    <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
      {updates.map((s, i) => (
        <ProfileUpdateCard key={`${s.entity}-${s.field}-${i}`} suggestion={s} profileId={profileId} />
      ))}
    </div>
  );
}

function ChatBubble({ msg, breakdownTitle, isAr }: { msg: ChatMessageType; breakdownTitle: string; isAr: boolean }) {
  const bot = msg.role !== "user";
  const isError = msg.provider === "error";
  const hasBreakdown = !!msg.tax_breakdown && Object.keys(msg.tax_breakdown).length > 0;
  const updates = bot ? msg.profile_updates ?? [] : [];
  return (
    <div style={{ alignSelf: bot ? "flex-start" : "flex-end", maxWidth: hasBreakdown || updates.length > 0 ? "86%" : "78%" }}>
      <div
        style={{
          background: isError ? "var(--gold-tint)" : bot ? "var(--green-tint)" : "var(--paper-2)",
          border: `1px solid ${isError ? "var(--gold)" : bot ? "var(--green-tint2)" : "var(--line)"}`,
          borderStartStartRadius: bot ? 4 : 16,
          borderStartEndRadius: bot ? 16 : 4,
          borderEndStartRadius: 16,
          borderEndEndRadius: 16,
          padding: "12px 15px",
        }}
      >
        {isError && (
          <div className="row" style={{ gap: 6, marginBottom: 6, color: "var(--ink)", fontSize: 12, fontWeight: 700 }}>
            <Icon name="shield" size={13} color="var(--gold)" />
            <span>{isAr ? "تعذّر الرد من المزود" : "Provider response unavailable"}</span>
          </div>
        )}
        <p style={{ fontSize: 14.5, lineHeight: 1.6, color: "var(--ink)", whiteSpace: "pre-wrap" }}>{msg.content}</p>
        {bot && hasBreakdown && <BreakdownCard data={msg.tax_breakdown as Record<string, unknown>} title={breakdownTitle} />}
        {bot && updates.length > 0 && <ProfileUpdateCards updates={updates} profileId={msg.profile_id} />}
      </div>
      {bot && msg.sources && msg.sources.length > 0 && <CitationLine sources={msg.sources} />}
    </div>
  );
}

export default function Chat() {
  const { user } = useAuth();
  const { t, fill, lang } = useLang();
  const { profile, calculation, currentYear } = useTaxProfile();
  const {
    messages,
    currentSessionId,
    setCurrentSessionId,
    appendMessage,
    upsertSession,
    refreshSessions,
    refreshMessages,
    loadingMessages,
  } = useChatHistory();

  const [input, setInput] = useState("");
  const [selectedModel, setSelectedModel] =
    useState<ChatModelOption>(DEFAULT_CHAT_MODEL);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<PendingAttachment[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<string | null>(null);
  const [capabilities, setCapabilities] = useState<PublicCapabilities | null>(null);
  const [usage, setUsage] = useState<UserUsage | null>(null);
  const [availabilityError, setAvailabilityError] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const inFlightRef = useRef(false);
  const mountedRef = useRef(false);
  const currentUserIdRef = useRef(user?.id ?? "");

  useEffect(() => {
    currentUserIdRef.current = user?.id ?? "";
  }, [user?.id]);

  // App remounts the authenticated subtree on account changes. Stop a send
  // chain after unmount or account switch so its next request cannot use another account's token.
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const userTier = normalizeTier(user?.subscription_tier);
  const allowedModels = useMemo(() =>
    capabilities?.tiers.find((item) => item.name === userTier)?.allowed_models ?? [],
    [capabilities, userTier],
  );
  const allowedModelOptions = useMemo(
    () =>
      CHAT_MODEL_OPTIONS.filter((option) =>
        allowedModels.some((item) => item.provider === option.provider && item.model === option.model),
      ),
    [allowedModels],
  );
  const configuredProviders = capabilities?.ai?.configured_providers ?? [];
  const usableModelOptions = allowedModelOptions.filter((option) => configuredProviders.includes(option.provider));
  const selectedProviderReady = usableModelOptions.some((option) => option.model === selectedModel.model && option.provider === selectedModel.provider);

  useEffect(() => {
    if (!user?.id) return;
    let active = true;
    void Promise.allSettled([getPublicCapabilities(), getMyUsage()]).then(([caps, currentUsage]) => {
      if (!active) return;
      if (caps.status === "fulfilled") setCapabilities(caps.value);
      else setAvailabilityError(true);
      if (currentUsage.status === "fulfilled") setUsage(currentUsage.value);
    });
    return () => { active = false; };
  }, [user?.id]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const pickerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listboxRef = useRef<HTMLDivElement>(null);
  const openedViaKeyboardRef = useRef(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingStartRef = useRef(false);
  const currentSessionIdRef = useRef<string | null>(currentSessionId);

  const focusEnabledOption = (preferSelected = true) => {
    const listbox = listboxRef.current;
    if (!listbox) return;
    if (preferSelected) {
      const activeOption = listbox.querySelector<HTMLButtonElement>(
        'button[role="option"][aria-selected="true"]:not(:disabled)'
      );
      if (activeOption) {
        activeOption.focus();
        return;
      }
    }
    const firstEnabled = listbox.querySelector<HTMLButtonElement>(
      'button[role="option"]:not(:disabled)'
    );
    firstEnabled?.focus();
  };

  useEffect(() => {
    if (!pickerOpen) return;
    if (openedViaKeyboardRef.current) {
      openedViaKeyboardRef.current = false;
      focusEnabledOption(true);
    }
  }, [pickerOpen]);

  useEffect(() => {
    currentSessionIdRef.current = currentSessionId;
  }, [currentSessionId]);

  useEffect(() => {
    if (usableModelOptions.length > 0 && !selectedProviderReady) {
      setSelectedModel(usableModelOptions[0]);
    }
  }, [selectedProviderReady, usableModelOptions]);

  const showGreeting = messages.length === 0 && !currentSessionId;

  useEffect(() => {
    if (messages.length > 0) {
      messagesEndRef.current?.scrollIntoView?.({ behavior: "smooth" });
    }
  }, [messages]);

  // Close picker on outside click
  useEffect(() => {
    if (!pickerOpen) return;
    function onClick(e: MouseEvent) {
      if (!pickerRef.current?.contains(e.target as Node)) {
        setPickerOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [pickerOpen]);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  function pushLocal(
    role: ChatRole,
    content: string,
    kind: ChatKind = "text",
    targetSessionId: string | null = currentSessionIdRef.current,
  ) {
    appendMessage(localMessage(role, content, kind, targetSessionId));
  }

  function scheduleTitleRefresh() {
    // The backend generates a title via background task after the first turn.
    // Re-fetch the session list a couple of times so the sidebar picks it up.
    window.setTimeout(() => {
      void refreshSessions();
    }, 1800);
    window.setTimeout(() => {
      void refreshSessions();
    }, 5000);
  }

  const autoGrow = (el: HTMLTextAreaElement) => {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 192)}px`;
  };

  function resetTextareaHeight() {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  }

  function appendToInput(text: string) {
    const transcript = text.trim();
    if (!transcript) return;

    setInput((prev) => (prev.trim() ? `${prev.trimEnd()} ${transcript}` : transcript));
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      if (textareaRef.current) autoGrow(textareaRef.current);
    });
  }

  function attachmentText(attachments: PendingAttachment[]): string {
    const label = attachments.length === 1 ? "Attached document" : "Attached documents";
    return [
      `${label}:`,
      ...attachments.map((attachment) => `- ${attachment.file.name}`),
    ].join("\n");
  }

  async function uploadPendingAttachment(attachment: PendingAttachment) {
    const formData = new FormData();
    formData.append("file", attachment.file);
    formData.append("document_type", attachment.documentType);
    await api.post("/documents/upload", formData, {
      headers: { "Content-Type": "multipart/form-data", ...usageRequestHeaders() },
    });
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    const attachmentsToSend = pendingAttachments;
    const hasAttachments = attachmentsToSend.length > 0;
    if ((!text && !hasAttachments) || inFlightRef.current || isSending || isUploading || (text && !selectedProviderReady)) return;
    inFlightRef.current = true;
    setSendError(null);

    const initiatingUserId = user?.id ?? "";
    const isStillActive = () => mountedRef.current && currentUserIdRef.current === initiatingUserId;

    const q = [text, hasAttachments ? attachmentText(attachmentsToSend) : ""]
      .filter(Boolean)
      .join("\n\n");

    let sessionId = currentSessionIdRef.current;
    const isFirstTurn = !sessionId;
    setIsSending(Boolean(text));
    setIsUploading(hasAttachments);
    try {
      for (const attachment of attachmentsToSend) {
        await uploadPendingAttachment(attachment);
        if (!isStillActive()) return;
        setPendingAttachments((current) => current.filter((item) => item.id !== attachment.id));
      }

      // Create the session only after uploads pass validation/quota checks.
      if (!sessionId) {
        try {
          const fresh = await createChatSession();
          if (!isStillActive()) return;
          upsertSession(fresh);
          if (currentSessionIdRef.current === null) {
            setCurrentSessionId(fresh.id);
            currentSessionIdRef.current = fresh.id;
          }
          sessionId = fresh.id;
        } catch {
          // Couldn't pre-create; chat can still create one, but upload-only logs stay local.
        }
      }

      if (!isStillActive()) return;

      pushLocal("user", q, hasAttachments ? "upload" : "text", sessionId);
      setInput("");
      setPendingAttachments([]);
      resetTextareaHeight();

      if (!text) {
        const aiContent =
          attachmentsToSend.length === 1
            ? `I've saved ${attachmentsToSend[0].file.name} to your documents. Add a question whenever you're ready.`
            : `I've saved ${attachmentsToSend.length} documents. Add a question whenever you're ready.`;

        if (sessionId) {
          try {
            await logChatMessage(sessionId, {
              role: "user",
              kind: "upload",
              content: q,
            });
            if (!isStillActive()) return;
            pushLocal("assistant", aiContent, "upload", sessionId);
          } catch {
            if (!isStillActive()) return;
            pushLocal("assistant", aiContent, "upload", sessionId);
          }
        } else {
          pushLocal("assistant", aiContent, "upload", sessionId);
        }
        void refreshSessions();
        return;
      }

      const resp = await sendChat({
        question: q,
        provider: selectedModel.provider,
        model: selectedModel.model,
        lang,
        session_id: sessionId,
      });
      if (!isStillActive()) return;
      if (!sessionId) {
        // Pre-create failed earlier; adopt the backend-created session.
        const now = new Date().toISOString();
        upsertSession({
          id: resp.session_id,
          user_id: user?.id ?? "",
          title: "New chat",
          created_at: now,
          updated_at: now,
        });
        if (currentSessionIdRef.current === null) {
          setCurrentSessionId(resp.session_id);
          currentSessionIdRef.current = resp.session_id;
        }
      }
      appendMessage({
        id: resp.assistant_message_id,
        session_id: resp.session_id,
        role: "assistant",
        kind: "text",
        content: resp.answer,
        sources: resp.sources,
        tax_breakdown: resp.tax_breakdown ?? null,
        profile_updates: resp.profile_updates ?? null,
        profile_id: resp.profile_id ?? null,
        provider: resp.provider,
        model: resp.model ?? null,
        created_at: new Date().toISOString(),
      });
      if (resp.provider === "error" && currentSessionIdRef.current === resp.session_id) {
        setSendError(isAr ? "تعذّر توليد الرد. رسالتك محفوظة؛ جرّب بعد تفعيل مزود AI أو اختر نموذجًا آخر." : "The reply failed. Your message was saved; try again after AI is configured or choose another model.");
      }
      await refreshMessages(resp.session_id).catch(() => undefined);
      if (!isStillActive()) return;
      void getMyUsage().then(setUsage).catch(() => undefined);
      if (isFirstTurn) {
        scheduleTitleRefresh();
      } else {
        void refreshSessions();
      }
    } catch (error) {
      if (!isStillActive()) return;
      if (currentSessionIdRef.current === sessionId) {
        setSendError(getApiErrorMessage(
          error,
          hasAttachments
            ? "Sorry, I couldn't upload or send that. Please try again."
            : "Sorry, the chat is unavailable. Try a different model or try again.",
        ));
        if (text) setInput(text);
      }
      // Even on timeout, the backend may have committed state — refresh so the
      // sidebar reflects what's actually in the DB.
      void refreshSessions();
      if (sessionId) void refreshMessages(sessionId).catch(() => undefined);
    } finally {
      if (isStillActive()) {
        setIsSending(false);
        setIsUploading(false);
      }
      inFlightRef.current = false;
    }
  }

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;

    setPendingAttachments((current) => [
      ...current,
      ...files.map(makePendingAttachment),
    ]);
    if (fileInputRef.current) fileInputRef.current.value = "";
    requestAnimationFrame(() => textareaRef.current?.focus());
  }

  async function startRecording() {
    if (isRecording || recordingStartRef.current || isSending || isUploading || !capabilities?.ai?.voice) return;
    recordingStartRef.current = true;
    setSendError(null);

    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      setSendError(isAr ? "المتصفح لا يدعم التسجيل الصوتي؛ اكتب سؤالك بدلًا من ذلك." : "This browser does not support voice recording. Please type your question.");
      recordingStartRef.current = false;
      return;
    }

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setSendError(isAr ? "تعذّر فتح الميكروفون. راجع إذن المتصفح أو اكتب سؤالك." : "Microphone access was denied. Check browser permission or type your question.");
      recordingStartRef.current = false;
      return;
    }
    try {
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      });
      recorder.start();
      setIsRecording(true);
    } catch {
      stream.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setSendError(isAr ? "تعذّر بدء التسجيل. جرّب الكتابة بدلًا من ذلك." : "Could not start recording. Please type your question instead.");
    } finally {
      recordingStartRef.current = false;
    }
  }

  async function stopRecording() {
    if (!isRecording) return;
    setIsRecording(false);

    const recorder = recorderRef.current;
    if (!recorder) return;
    if (recorder.state === "inactive") return;

    await new Promise<void>((resolve) => {
      recorder.addEventListener("stop", () => resolve(), { once: true });
      recorder.stop();
    });
    recorderRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    if (chunksRef.current.length === 0) {
      return;
    }

    const recordedBlob = new Blob(chunksRef.current, {
      type: recorder.mimeType || "audio/webm",
    });

    let wavBlob: Blob;
    try {
      wavBlob = await blobToMonoWav(recordedBlob);
    } catch {
      setSendError(isAr ? "تعذّر تجهيز التسجيل. جرّب متصفحًا آخر أو اكتب سؤالك." : "Could not prepare the recording. Try another browser or type your question.");
      setVoiceStatus(null);
      return;
    }
    if (wavBlob.size > 8 * 1024 * 1024) {
      setSendError(isAr ? "التسجيل أكبر من 8 ميغابايت. سجّل مقطعًا أقصر." : "Recording exceeds 8 MB. Please record a shorter clip.");
      return;
    }

    setVoiceStatus("transcribing");
    try {
      const audio_b64 = await blobToBase64(wavBlob);
      const transcript = await transcribeAudio(
        audio_b64,
        lang,
        wavBlob.type,
      );
      appendToInput(transcript);
    } catch (error) {
      setSendError(getApiErrorMessage(error, isAr ? "تعذّر تحويل الصوت إلى نص. حاول مرة أخرى أو اكتب سؤالك." : "Transcription failed. Try again or type your question."));
    } finally {
      setVoiceStatus(null);
    }
  }

  const micDisabled = isSending || isUploading || !!voiceStatus || !capabilities?.ai?.voice;
  const pickerDisabled = isRecording || isSending || isUploading;

  const isAr = t.dir === "rtl";
  const fmtJD = (n: number) => new Intl.NumberFormat(isAr ? "ar-JO" : "en-US", { maximumFractionDigits: 0 }).format(n);
  const ctx: { k: string; v: string }[] = [];
  if (profile) {
    ctx.push({ k: isAr ? "السنة الضريبية" : "Tax year", v: String(profile.tax_year ?? currentYear) });
    ctx.push({
      k: isAr ? "الحالة" : "Status",
      v:
        (profile.marital_status === "married" ? t.settings.married : t.settings.single) +
        (profile.num_dependents ? ` · ${profile.num_dependents} ${isAr ? "معالين" : "deps"}` : ""),
    });
    if (calculation) ctx.push({ k: t.dashboard.stat1, v: `${fmtJD(calculation.gross_income)} JD` });
  }

  const sendDisabled = (!input.trim() && pendingAttachments.length === 0) || isSending || isRecording || isUploading || (!!input.trim() && !selectedProviderReady);

  let sendDisabledReason = t.chat.send;
  if (isSending || isUploading) {
    sendDisabledReason = isAr ? "جارٍ الإرسال والمعالجة…" : "Sending and processing…";
  } else if (isRecording) {
    sendDisabledReason = isAr ? "التسجيل الصوتي قيد التشغيل" : "Voice recording in progress";
  } else if (!input.trim() && pendingAttachments.length === 0) {
    sendDisabledReason = isAr ? "اكتب سؤالًا أو أرفق مستندًا للإرسال" : "Type a question or attach a document to send";
  } else if (!!input.trim() && !selectedProviderReady) {
    sendDisabledReason = isAr ? "النموذج المحدد غير مفعّل أو غير متاح في خطتك" : "Selected model is not configured or not available on your plan";
  }

  return (
    <main className="wrap" style={{ maxWidth: 1180, paddingBlock: "26px 52px" }}>
      <div
        style={{ display: "grid", gridTemplateColumns: "auto minmax(0,1fr)", gap: 20, alignItems: "start" }}
        className="max-md:!grid-cols-1"
      >
        <ChatHistorySidebar />

        {/* Chat card */}
        <div className="card fade-up" style={{ display: "flex", flexDirection: "column", height: CHAT_CARD_H, overflow: "hidden", minWidth: 0 }}>
          {/* header */}
          <div className="row-between" style={{ padding: "16px 22px", borderBottom: "1px solid var(--line)", flex: "none" }}>
            <div className="row" style={{ gap: 12 }}>
              <div style={{ width: 40, height: 40, borderRadius: 11, background: "var(--green-tint)", display: "grid", placeItems: "center", flex: "none" }}>
                <Mark size={24} />
              </div>
              <div>
                <div className="t-h3" style={{ fontSize: 16.5 }}>{t.chat.title}</div>
                <div className="row" style={{ gap: 6 }}>
                   <span className="dot" style={{ background: selectedProviderReady ? "var(--green)" : "var(--attention)" }} />
                   <span className="t-small">{selectedProviderReady ? t.chat.online : (isAr ? "بانتظار تفعيل AI" : "AI setup needed")}</span>
                </div>
              </div>
            </div>
            <span className="chip chip-green" style={{ fontSize: 11.5 }}>
              <Icon name="scale" size={13} />
              {t.chat.lawGrounded}
            </span>
          </div>

          {(availabilityError || (capabilities && usableModelOptions.length === 0)) && (
            <div role="alert" style={{ padding: "10px 22px", background: "var(--gold-tint)", color: "var(--ink)", borderBottom: "1px solid var(--line)", fontSize: 13 }}>
              {availabilityError
                ? (isAr ? "تعذّر التحقق من جاهزية المحادثة. تأكد من اتصال التطبيق بالخادم." : "Could not check chat availability. Check the app's server connection.")
                : (isAr ? "المحادثة الذكية تحتاج تفعيل مزود AI من مسؤول النظام. يمكنك تجهيز ملفك ورفع مستنداتك الآن." : "AI chat needs a provider configured by the operator. You can still prepare your profile and upload documents.")}
            </div>
          )}

          {/* context strip */}
          {ctx.length > 0 && (
            <div className="row hide-scrollbar" style={{ gap: 18, padding: "11px 22px", borderBottom: "1px solid var(--line)", overflowX: "auto", flex: "none" }}>
              {ctx.map((c, i) => (
                <div key={i} className="row" style={{ gap: 7, flex: "none" }}>
                  <span className="t-small faint" style={{ fontSize: 11.5 }}>{c.k}</span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)", whiteSpace: "nowrap" }}>{c.v}</span>
                  {i < ctx.length - 1 && <span style={{ width: 1, height: 14, background: "var(--line)", marginInlineStart: 11 }} />}
                </div>
              ))}
            </div>
          )}

          {/* thread */}
          <div className="hide-scrollbar" style={{ flex: 1, overflowY: "auto", padding: 22, display: "flex", flexDirection: "column", gap: 16, scrollBehavior: "smooth" }}>
            {showGreeting && (
              <div style={{ alignSelf: "flex-start", maxWidth: "78%" }}>
                <div style={{ background: "var(--green-tint)", border: "1px solid var(--green-tint2)", borderStartStartRadius: 4, borderStartEndRadius: 16, borderEndStartRadius: 16, borderEndEndRadius: 16, padding: "12px 15px" }}>
                  <p style={{ fontSize: 14.5, lineHeight: 1.6, color: "var(--ink)", whiteSpace: "pre-wrap" }}>{t.chat.greetingContent}</p>
                </div>
              </div>
            )}

            {loadingMessages && messages.length === 0 && !showGreeting && (
              <div className="t-small faint center" style={{ padding: "32px 0" }}>
                {t.common.loading}
              </div>
            )}

            {messages.map((msg) => (
              <ChatBubble key={msg.id} msg={msg} breakdownTitle={t.chat.breakdownTitle} isAr={isAr} />
            ))}

            {isSending && (
              <div style={{ alignSelf: "flex-start" }}>
                <div style={{ padding: "14px 16px", background: "var(--green-tint)", border: "1px solid var(--green-tint2)", borderRadius: 16, borderStartStartRadius: 4 }}>
                  <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: 999, background: "var(--green)", marginInlineEnd: 4, animation: "bpulse 1s infinite" }} />
                  <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: 999, background: "var(--green)", marginInlineEnd: 4, animation: "bpulse 1s infinite", animationDelay: "200ms" }} />
                  <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: 999, background: "var(--green)", animation: "bpulse 1s infinite", animationDelay: "400ms" }} />
                  <style>{`@keyframes bpulse{0%,100%{opacity:.3}50%{opacity:1}}`}</style>
                </div>
              </div>
            )}
            {voiceStatus && (
              <div role="status" className="t-eyebrow center" style={{ color: "var(--clay)" }}>
                {isAr ? "جارٍ تحويل الصوت إلى نص…" : "Transcribing audio…"}
              </div>
            )}
            <div ref={messagesEndRef} style={{ height: 4 }} />
          </div>

          {/* composer */}
          <div style={{ padding: "12px 22px 16px", borderTop: "1px solid var(--line)", flex: "none" }}>
            {sendError && <p role="alert" style={{ marginBottom: 10, padding: "9px 12px", borderRadius: 9, background: "var(--gold-tint)", color: "var(--ink)", fontSize: 13 }}>{sendError}</p>}
            {pendingAttachments.length > 0 && (
              <div className="row" style={{ gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
                {pendingAttachments.map((attachment) => (
                  <span key={attachment.id} className="row" style={{ gap: 9, padding: "6px 9px", borderRadius: 10, border: "1px solid var(--line)", background: "var(--paper-2)" }}>
                    <span style={{ width: 26, height: 26, borderRadius: 7, background: "var(--green-tint)", display: "grid", placeItems: "center", flex: "none" }}>
                      <Icon name="doc" size={14} color="var(--green)" />
                    </span>
                    <span style={{ lineHeight: 1.15, minWidth: 0 }}>
                      <span style={{ display: "block", fontSize: 12.5, fontWeight: 600, color: "var(--ink)", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{attachment.file.name}</span>
                      <span className="t-small faint" style={{ fontSize: 10.5 }}>{formatFileSize(attachment.file.size)}</span>
                    </span>
                    <button
                      type="button"
                      onClick={() => setPendingAttachments((current) => current.filter((item) => item.id !== attachment.id))}
                      disabled={isUploading || isSending}
                      title={t.chat.remove}
                      style={{ width: 20, height: 20, borderRadius: 6, border: "none", background: "none", display: "grid", placeItems: "center", color: "var(--ink-soft)", flex: "none" }}
                    >
                      <Icon name="x" size={13} color="currentColor" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {/* suggestion pills */}
            <div className="row hide-scrollbar" style={{ gap: 8, marginBottom: 11, overflowX: "auto" }}>
              {t.chat.suggestions.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  className="pill"
                  onClick={() => {
                    setInput(s);
                    requestAnimationFrame(() => textareaRef.current?.focus());
                  }}
                  style={{ flex: "none", fontSize: 12.5, cursor: "pointer", padding: "7px 12px", whiteSpace: "nowrap" }}
                >
                  {s}
                </button>
              ))}
            </div>

            <input type="file" ref={fileInputRef} className="hidden" onChange={handleFileUpload} accept=".jpg,.jpeg,.png,.pdf" multiple />

            <form onSubmit={handleSend} className="row" style={{ gap: 8, alignItems: "flex-end" }}>
              {/* attach */}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading || isSending || isRecording}
                title={t.chat.attach}
                style={{ width: 44, height: 44, flex: "none", borderRadius: 12, border: "1px solid var(--line)", background: "var(--paper)", display: "grid", placeItems: "center", color: "var(--ink-soft)", opacity: isUploading || isSending || isRecording ? 0.5 : 1 }}
              >
                <Icon name={isUploading ? "refresh" : "clip"} size={18} color="currentColor" />
              </button>

              {/* input */}
              <textarea
                ref={textareaRef}
                className="input hide-scrollbar"
                style={{ flex: 1, minWidth: 0, resize: "none", minHeight: 44, maxHeight: 120, lineHeight: 1.5, paddingBlock: 11 }}
                placeholder={isRecording ? t.chat.listening : t.chat.inputPh}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onInput={(e) => autoGrow(e.currentTarget)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend(e as unknown as React.FormEvent);
                  }
                }}
                rows={1}
              />

              {/* mic */}
              <button
                type="button"
                onClick={() => { if (isRecording) void stopRecording(); else void startRecording(); }}
                disabled={micDisabled}
                aria-label={isRecording ? (isAr ? "إيقاف التسجيل" : "Stop recording") : t.chat.mic}
                title={!capabilities?.ai?.voice ? (isAr ? "الإملاء الصوتي يحتاج تفعيل AI" : "Voice requires AI setup") : isRecording ? (isAr ? "إيقاف التسجيل" : "Stop recording") : t.chat.mic}
                style={{
                  width: 44,
                  height: 44,
                  flex: "none",
                  borderRadius: 12,
                  display: "grid",
                  placeItems: "center",
                  userSelect: "none",
                  opacity: micDisabled ? 0.4 : 1,
                  border: "1px solid " + (isRecording ? "var(--clay)" : "var(--line)"),
                  background: isRecording ? "var(--clay)" : "var(--paper)",
                  color: isRecording ? "#FFFCF5" : "var(--ink-soft)",
                  animation: isRecording ? "bayyanPulse 1.4s ease-in-out infinite" : "none",
                }}
              >
                <Icon name="mic" size={18} color="currentColor" />
              </button>

              {/* model picker */}
              <div style={{ position: "relative" }} ref={pickerRef}>
                <button
                  ref={triggerRef}
                  type="button"
                  onClick={() => setPickerOpen((p) => !p)}
                  disabled={pickerDisabled}
                  className="row"
                  title={t.chat.chooseModel}
                  aria-expanded={pickerOpen}
                  aria-haspopup="listbox"
                  onKeyDown={(e) => {
                    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                      e.preventDefault();
                      if (!pickerOpen) {
                        openedViaKeyboardRef.current = true;
                        setPickerOpen(true);
                      } else {
                        focusEnabledOption(true);
                      }
                    } else if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
                      e.preventDefault();
                      if (!pickerOpen) {
                        openedViaKeyboardRef.current = true;
                        setPickerOpen(true);
                      } else {
                        setPickerOpen(false);
                        triggerRef.current?.focus();
                      }
                    } else if (e.key === "Escape" && pickerOpen) {
                      e.preventDefault();
                      setPickerOpen(false);
                      triggerRef.current?.focus();
                    }
                  }}
                  style={{ gap: 7, height: 44, padding: "0 12px", borderRadius: 12, border: "1px solid var(--line)", background: "var(--paper)", color: "var(--ink)", fontSize: 13, fontWeight: 600, flex: "none", opacity: pickerDisabled ? 0.5 : 1 }}
                >
                  <Icon name="spark" size={15} color="var(--green)" />
                  <span className="max-md:hidden">{selectedModel.label}</span>
                  <Icon name="chevron" size={14} color="var(--ink-soft)" style={{ transform: pickerOpen ? "rotate(-90deg)" : "rotate(90deg)" }} />
                </button>
                {pickerOpen && (
                  <div
                    ref={listboxRef}
                    className="card"
                    role="listbox"
                    aria-label={t.chat.chooseModel}
                    tabIndex={-1}
                    onKeyDown={(e) => {
                      const listbox = listboxRef.current;
                      if (!listbox) return;
                      const enabledOptions = Array.from(
                        listbox.querySelectorAll<HTMLButtonElement>('button[role="option"]:not(:disabled)')
                      );
                      if (enabledOptions.length === 0) return;

                      const currentIndex = enabledOptions.indexOf(document.activeElement as HTMLButtonElement);

                      if (e.key === "ArrowDown") {
                        e.preventDefault();
                        const nextIndex = currentIndex < 0 || currentIndex >= enabledOptions.length - 1 ? 0 : currentIndex + 1;
                        enabledOptions[nextIndex]?.focus();
                      } else if (e.key === "ArrowUp") {
                        e.preventDefault();
                        const prevIndex = currentIndex <= 0 ? enabledOptions.length - 1 : currentIndex - 1;
                        enabledOptions[prevIndex]?.focus();
                      } else if (e.key === "Home") {
                        e.preventDefault();
                        enabledOptions[0]?.focus();
                      } else if (e.key === "End") {
                        e.preventDefault();
                        enabledOptions[enabledOptions.length - 1]?.focus();
                      } else if (e.key === "Escape") {
                        e.preventDefault();
                        e.stopPropagation();
                        setPickerOpen(false);
                        triggerRef.current?.focus();
                      } else if (e.key === "Tab") {
                        setPickerOpen(false);
                      }
                    }}
                    style={{ position: "absolute", bottom: "calc(100% + 8px)", insetInlineEnd: 0, zIndex: 30, width: 264, padding: 6, boxShadow: "var(--shadow-lg)" }}
                  >
                    <div className="t-eyebrow" style={{ fontSize: 10, padding: "6px 10px 8px", opacity: 0.75 }}>
                      {fill(t.chat.planNote, { tier: t.chat.tiers[userTier] })}
                    </div>
                    {CHAT_MODEL_OPTIONS.map((option) => {
                      const active = selectedModel.model === option.model;
                      const locked = !allowedModels.some((item) => item.provider === option.provider && item.model === option.model);
                      const unconfigured = !configuredProviders.includes(option.provider);
                      const unlockTier = modelUnlockTier(option.model, capabilities);
                      const isHighestTier = userTier === "Premium";
                      const lockText = isHighestTier || TIER_ORDER.indexOf(userTier) >= TIER_ORDER.indexOf(unlockTier)
                        ? (isAr ? "غير مدعوم بخطتك" : "Unavailable on plan")
                        : fill(t.chat.lockedHint, { tier: t.chat.tiers[unlockTier] });
                      return (
                        <button
                          key={option.model}
                          type="button"
                          role="option"
                          aria-selected={active}
                          disabled={locked || unconfigured}
                          onKeyDown={(e) => {
                            if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
                              if (locked || unconfigured) return;
                              e.preventDefault();
                              setSelectedModel(option);
                              setPickerOpen(false);
                              triggerRef.current?.focus();
                            }
                          }}
                          onClick={() => {
                            if (locked || unconfigured) return;
                            setSelectedModel(option);
                            setPickerOpen(false);
                            triggerRef.current?.focus();
                          }}
                          className="row-between"
                          style={{ width: "100%", padding: "9px 10px", borderRadius: 9, border: "none", marginBottom: 1, gap: 8, cursor: locked || unconfigured ? "not-allowed" : "pointer", background: active ? "var(--green-tint)" : "transparent" }}
                        >
                          <span style={{ textAlign: "start", opacity: locked ? 0.55 : 1 }}>
                            <span className="row" style={{ gap: 7 }}>
                              <span style={{ fontSize: 13.5, fontWeight: active ? 700 : 500, color: active ? "var(--green-deep)" : "var(--ink)" }}>{option.label}</span>
                              {active && <Icon name="check" size={14} stroke={3} color="var(--green)" />}
                            </span>
                            <span className="t-small" style={{ fontSize: 11, marginTop: 1, display: "block", textTransform: "capitalize" }}>{option.provider}</span>
                          </span>
                          {locked && (
                            <span className="row" style={{ gap: 4, flex: "none", fontSize: 10.5, fontWeight: 600, color: "var(--gold)", padding: "3px 7px", borderRadius: 999, background: "var(--gold-tint)" }}>
                              <Icon name="lock" size={11} color="var(--gold)" />
                              {lockText}
                            </span>
                          )}
                          {!locked && unconfigured && <span className="t-small" style={{ fontSize: 10.5 }}>{isAr ? "غير مهيأ" : "Not configured"}</span>}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* send */}
              <button
                type="submit"
                disabled={sendDisabled}
                aria-label={t.chat.send}
                title={sendDisabledReason}
                className="btn btn-primary"
                style={{ height: 44, padding: "0 16px", flex: "none" }}
              >
                <Icon name="arrow" size={18} color="currentColor" className="i-arrow" />
              </button>
            </form>

            <p className="t-small faint" style={{ marginTop: 10, fontSize: 11.5 }}>
              {t.chat.disclaimer}{usage && ` · ${isAr ? "الرسائل المتبقية" : "Messages left"}: ${usage.messages.remaining}/${usage.messages.limit}`}
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}

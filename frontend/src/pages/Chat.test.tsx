// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Chat from "./Chat";
import { AuthContext, LanguageContext, TaxProfileContext, ChatHistoryContext } from "../contexts/hooks";
import type { AuthContextType } from "../contexts/AuthContext";
import type { TaxProfileContextValue } from "../contexts/TaxProfileContext";
import type { ChatHistoryContextType } from "../contexts/ChatHistoryContext";
import { STRINGS, fill } from "../i18n/strings";
import * as apiModule from "../services/api";
import type { PublicCapabilities, UserUsage, User } from "../types/api";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    api: {
      post: vi.fn(),
      get: vi.fn(),
      delete: vi.fn(),
      put: vi.fn(),
    },
    createChatSession: vi.fn(),
    logChatMessage: vi.fn(),
    sendChat: vi.fn(),
    getPublicCapabilities: vi.fn(),
    getMyUsage: vi.fn(),
    listChatSessions: vi.fn(),
    getChatSession: vi.fn(),
    transcribeAudio: vi.fn(),
  };
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
});

const defaultCapabilities: PublicCapabilities = {
  product: "BAYYAN",
  tier_changes: "admin_only",
  official_filing: false,
  legal_corpus: "demo",
  ai: {
    configured_providers: ["gemini"],
    document_extraction: true,
    advisor: true,
    voice: true,
  },
  tiers: [
    {
      name: "Premium",
      max_messages_per_month: 500,
      max_docs_per_month: 150,
      max_tokens: 2048,
      max_extractions_per_month: 50,
      max_advisor_runs_per_month: 20,
      max_voice_clips_per_month: 20,
      allowed_models: [
        { provider: "gemini", model: "gemini-2.5-flash" },
        { provider: "gemini", model: "gemini-2.5-pro" },
      ],
    },
  ],
};

const defaultUsage: UserUsage = {
  tier: "Premium",
  usage_month: "2026-09",
  messages: { used: 0, limit: 500, remaining: 500 },
  docs: { used: 0, limit: 150, remaining: 150 },
  allowed_models: [
    { provider: "gemini", model: "gemini-2.5-flash" },
    { provider: "gemini", model: "gemini-2.5-pro" },
  ],
  max_tokens: 2048,
};

function renderChat(
  userId = "user-a",
  authOverrides?: Partial<AuthContextType>,
  chatHistoryOverrides?: Partial<ChatHistoryContextType>,
  langOverride?: { lang: "ar" | "en"; dir: "rtl" | "ltr" },
) {
  const user: User = {
    id: userId,
    username: `${userId}@example.com`,
    name: "Test User",
    phone: null,
    preferences: {},
    avatar_url: null,
    subscription_tier: "Premium",
    is_active: true,
    is_admin: true,
    created_at: new Date().toISOString(),
  };

  const authVal: AuthContextType = {
    user,
    loading: false,
    login: async () => undefined,
    signup: async () => undefined,
    logout: async () => undefined,
    refreshUser: async () => undefined,
    ...authOverrides,
  };

  const lang = langOverride?.lang ?? "en";
  const dir = langOverride?.dir ?? (lang === "ar" ? "rtl" : "ltr");
  const langVal = {
    lang,
    dir,
    t: STRINGS[lang],
    fill,
    setLang: () => undefined,
    toggleLang: () => undefined,
  };

  const taxProfileVal: TaxProfileContextValue = {
    currentYear: 2026,
    availableYears: [2026],
    selectYear: () => undefined,
    profile: null,
    incomeSources: [],
    deductions: [],
    calculation: null,
    version: 1,
    loading: false,
    error: null,
    refreshTaxProfile: async () => ({
      profile: null,
      incomeSources: [],
      deductions: [],
      calculation: null,
      version: 1,
    }),
  };

  const chatHistoryVal: ChatHistoryContextType = {
    sessions: [],
    currentSessionId: null,
    messages: [],
    selectSession: async () => undefined,
    newChat: () => undefined,
    deleteSession: async () => undefined,
    renameSession: async () => undefined,
    appendMessage: vi.fn(),
    setMessages: vi.fn(),
    upsertSession: vi.fn(),
    refreshSessions: async () => undefined,
    refreshMessages: async () => undefined,
    setCurrentSessionId: vi.fn(),
    loadingSessions: false,
    loadingMessages: false,
    ...chatHistoryOverrides,
  };

  return render(
    <MemoryRouter>
      <AuthContext.Provider value={authVal}>
        <LanguageContext.Provider value={langVal}>
          <TaxProfileContext.Provider value={taxProfileVal}>
            <ChatHistoryContext.Provider value={chatHistoryVal}>
              <Chat />
            </ChatHistoryContext.Provider>
          </TaxProfileContext.Provider>
        </LanguageContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>
  );
}

describe("Chat Card G-CHAT01 — Account switch during upload tests", () => {
  beforeEach(() => {
    vi.mocked(apiModule.getPublicCapabilities).mockResolvedValue(defaultCapabilities);
    vi.mocked(apiModule.getMyUsage).mockResolvedValue(defaultUsage);
    vi.mocked(apiModule.listChatSessions).mockResolvedValue([]);
  });

  it("does not call createChatSession, logChatMessage, or sendChat if component unmounts during delayed upload", async () => {
    let finishUpload: () => void = () => undefined;
    const slowUploadPromise = new Promise<{ data: { id: string } }>((resolve) => {
      finishUpload = () => resolve({ data: { id: "doc-1" } });
    });

    vi.mocked(apiModule.api.post).mockImplementation((url) => {
      if (url === "/documents/upload") {
        return slowUploadPromise;
      }
      return Promise.resolve({ data: {} });
    });

    const { unmount, container } = renderChat("user-a");

    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    // Attach a file
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    expect(fileInput).toBeTruthy();

    const file = new File(["dummy content"], "salary_slip.pdf", { type: "application/pdf" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    // Verify attachment badge appears
    await waitFor(() => {
      expect(screen.getByText("salary_slip.pdf")).toBeTruthy();
    });

    // Enter text and submit
    const textarea = screen.getByPlaceholderText(STRINGS.en.chat.inputPh);
    fireEvent.change(textarea, { target: { value: "Review my attached document" } });

    const sendBtn = screen.getByRole("button", { name: STRINGS.en.chat.send });
    fireEvent.click(sendBtn);

    // Verify upload was started
    await waitFor(() => {
      expect(apiModule.api.post).toHaveBeenCalledWith(
        "/documents/upload",
        expect.any(FormData),
        expect.any(Object)
      );
    });

    // Unmount before upload finishes (simulates account switch unmounting the subtree)
    unmount();

    // Now resolve the delayed upload
    await act(async () => {
      finishUpload();
      await slowUploadPromise;
    });

    // Verify downstream calls were NEVER invoked by the old chain
    expect(apiModule.createChatSession).not.toHaveBeenCalled();
    expect(apiModule.logChatMessage).not.toHaveBeenCalled();
    expect(apiModule.sendChat).not.toHaveBeenCalled();
  });

  it("does not proceed with downstream actions if user account changes in-place during delayed upload", async () => {
    let finishUpload: () => void = () => undefined;
    const slowUploadPromise = new Promise<{ data: { id: string } }>((resolve) => {
      finishUpload = () => resolve({ data: { id: "doc-1" } });
    });

    vi.mocked(apiModule.api.post).mockImplementation((url) => {
      if (url === "/documents/upload") {
        return slowUploadPromise;
      }
      return Promise.resolve({ data: {} });
    });

    const userA: User = {
      id: "user-a",
      username: "user-a@example.com",
      name: "User A",
      phone: null,
      preferences: {},
      avatar_url: null,
      subscription_tier: "Premium",
      is_active: true,
      is_admin: false,
      created_at: new Date().toISOString(),
    };

    const userB: User = {
      id: "user-b",
      username: "user-b@example.com",
      name: "User B",
      phone: null,
      preferences: {},
      avatar_url: null,
      subscription_tier: "Premium",
      is_active: true,
      is_admin: false,
      created_at: new Date().toISOString(),
    };

    let currentUser = userA;
    const authVal: AuthContextType = {
      get user() {
        return currentUser;
      },
      loading: false,
      login: async () => undefined,
      signup: async () => undefined,
      logout: async () => undefined,
      refreshUser: async () => undefined,
    };

    const langVal = {
      lang: "en" as const,
      dir: "ltr" as const,
      t: STRINGS["en"],
      fill,
      setLang: () => undefined,
      toggleLang: () => undefined,
    };

    const taxProfileVal: TaxProfileContextValue = {
      currentYear: 2026,
      availableYears: [2026],
      selectYear: () => undefined,
      profile: null,
      incomeSources: [],
      deductions: [],
      calculation: null,
      version: 1,
      loading: false,
      error: null,
      refreshTaxProfile: async () => ({
        profile: null,
        incomeSources: [],
        deductions: [],
        calculation: null,
        version: 1,
      }),
    };

    const chatHistoryVal: ChatHistoryContextType = {
      sessions: [],
      currentSessionId: null,
      messages: [],
      selectSession: async () => undefined,
      newChat: () => undefined,
      deleteSession: async () => undefined,
      renameSession: async () => undefined,
      appendMessage: vi.fn(),
      setMessages: vi.fn(),
      upsertSession: vi.fn(),
      refreshSessions: async () => undefined,
      refreshMessages: async () => undefined,
      setCurrentSessionId: vi.fn(),
      loadingSessions: false,
      loadingMessages: false,
    };

    const { container, rerender } = render(
      <MemoryRouter>
        <AuthContext.Provider value={authVal}>
          <LanguageContext.Provider value={langVal}>
            <TaxProfileContext.Provider value={taxProfileVal}>
              <ChatHistoryContext.Provider value={chatHistoryVal}>
                <Chat />
              </ChatHistoryContext.Provider>
            </TaxProfileContext.Provider>
          </LanguageContext.Provider>
        </AuthContext.Provider>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    // Attach file
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["content"], "receipt.png", { type: "image/png" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText("receipt.png")).toBeTruthy();
    });

    // Submit attachment
    const sendBtn = screen.getByRole("button", { name: STRINGS.en.chat.send });
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(apiModule.api.post).toHaveBeenCalledWith(
        "/documents/upload",
        expect.any(FormData),
        expect.any(Object)
      );
    });

    // Switch account in-place before upload resolves
    currentUser = userB;
    rerender(
      <MemoryRouter>
        <AuthContext.Provider value={{ ...authVal, user: userB }}>
          <LanguageContext.Provider value={langVal}>
            <TaxProfileContext.Provider value={taxProfileVal}>
              <ChatHistoryContext.Provider value={chatHistoryVal}>
                <Chat />
              </ChatHistoryContext.Provider>
            </TaxProfileContext.Provider>
          </LanguageContext.Provider>
        </AuthContext.Provider>
      </MemoryRouter>
    );

    // Resolve upload
    await act(async () => {
      finishUpload();
      await slowUploadPromise;
    });

    // Downstream actions must NOT have run for the previous user's chain
    expect(apiModule.createChatSession).not.toHaveBeenCalled();
    expect(apiModule.logChatMessage).not.toHaveBeenCalled();
    expect(apiModule.sendChat).not.toHaveBeenCalled();
  });

  it("proceeds normally with session creation and chat send when upload succeeds on the same account", async () => {
    vi.mocked(apiModule.api.post).mockResolvedValue({ data: { id: "doc-1" } });
    vi.mocked(apiModule.createChatSession).mockResolvedValue({
      id: "session-new",
      user_id: "user-a",
      title: "New chat",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    vi.mocked(apiModule.sendChat).mockResolvedValue({
      session_id: "session-new",
      user_message_id: "usr-1",
      assistant_message_id: "ast-1",
      answer: "I reviewed your salary slip.",
      provider: "gemini",
      model: "gemini-2.5-flash",
      sources: [],
    });

    const { container } = renderChat("user-a");

    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    // Attach file
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["test pdf"], "my_salary.pdf", { type: "application/pdf" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(screen.getByText("my_salary.pdf")).toBeTruthy();
    });

    // Type text question
    const textarea = screen.getByPlaceholderText(STRINGS.en.chat.inputPh);
    fireEvent.change(textarea, { target: { value: "Can you analyze this salary slip?" } });

    const sendBtn = screen.getByRole("button", { name: STRINGS.en.chat.send });
    fireEvent.click(sendBtn);

    // Should upload attachment
    await waitFor(() => {
      expect(apiModule.api.post).toHaveBeenCalledWith(
        "/documents/upload",
        expect.any(FormData),
        expect.any(Object)
      );
    });

    // Should create chat session
    await waitFor(() => {
      expect(apiModule.createChatSession).toHaveBeenCalledTimes(1);
    });

    // Should send chat
    await waitFor(() => {
      expect(apiModule.sendChat).toHaveBeenCalledWith(
        expect.objectContaining({
          question: expect.stringContaining("my_salary.pdf"),
          provider: "gemini",
          model: "gemini-2.5-flash",
          session_id: "session-new",
        })
      );
    });
  });
});

describe("Chat Card G-CHAT02 — Usability, lock hints, and disabled state tests", () => {
  beforeEach(() => {
    vi.mocked(apiModule.getPublicCapabilities).mockResolvedValue(defaultCapabilities);
    vi.mocked(apiModule.getMyUsage).mockResolvedValue(defaultUsage);
    vi.mocked(apiModule.listChatSessions).mockResolvedValue([]);
  });

  it("shows disabled explanation title on send button when input is empty", async () => {
    renderChat("user-a");
    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    const sendBtn = screen.getByRole("button", { name: STRINGS.en.chat.send });
    expect(sendBtn.hasAttribute("disabled")).toBe(true);
    expect(sendBtn.getAttribute("title")).toBe("Type a question or attach a document to send");
  });

  it("unlocks Gemini 2.5 Pro for Premium tier without false upgrade messages", async () => {
    renderChat("user-a");
    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    const pickerBtn = screen.getByTitle(STRINGS.en.chat.chooseModel);
    fireEvent.click(pickerBtn);

    const listbox = screen.getByRole("listbox");
    expect(listbox).toBeTruthy();

    const proBtn = screen.getByText("Gemini 2.5 Pro").closest("button");
    expect(proBtn).toBeTruthy();
    expect(proBtn?.hasAttribute("disabled")).toBe(false);
    expect(proBtn?.textContent).not.toContain("Upgrade to Premium");
  });

  it("distinguishes error responses with a provider unavailable warning badge", async () => {
    const errorMsg = {
      id: "err-msg-1",
      session_id: "session-1",
      role: "assistant" as const,
      kind: "text" as const,
      content: "Could not generate response from provider.",
      provider: "error",
      model: null,
      created_at: new Date().toISOString(),
    };

    renderChat("user-a", undefined, {
      messages: [errorMsg],
      currentSessionId: "session-1",
    });

    await waitFor(() => {
      expect(screen.getByText("Provider response unavailable")).toBeTruthy();
      expect(screen.getByText("Could not generate response from provider.")).toBeTruthy();
    });
  });
});

describe("Chat Card G-CHAT-A11Y01 — Model picker keyboard navigation and accessibility", () => {
  beforeEach(() => {
    vi.mocked(apiModule.getPublicCapabilities).mockResolvedValue(defaultCapabilities);
    vi.mocked(apiModule.getMyUsage).mockResolvedValue(defaultUsage);
    vi.mocked(apiModule.listChatSessions).mockResolvedValue([]);
  });

  it("moves focus to the active enabled option when opened via keyboard", async () => {
    renderChat("user-a");
    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    const trigger = screen.getByTitle(STRINGS.en.chat.chooseModel);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    // Open via ArrowDown
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    const listbox = screen.getByRole("listbox");
    expect(listbox).toBeTruthy();

    // Focus moves to active enabled option (Gemini 2.5 Flash)
    await waitFor(() => {
      expect(document.activeElement?.getAttribute("role")).toBe("option");
      expect(document.activeElement?.textContent).toContain("Gemini 2.5 Flash");
    });
  });

  it("traverses only enabled options with ArrowDown and ArrowUp, skipping locked/unconfigured models", async () => {
    renderChat("user-a");
    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    const trigger = screen.getByTitle(STRINGS.en.chat.chooseModel);
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    const listbox = screen.getByRole("listbox");
    expect(listbox).toBeTruthy();

    // Initially focused on Gemini 2.5 Flash
    await waitFor(() => {
      expect(document.activeElement?.textContent).toContain("Gemini 2.5 Flash");
    });

    // Press ArrowDown -> moves to next enabled option: Gemini 2.5 Pro
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toContain("Gemini 2.5 Pro");

    // Press ArrowDown again -> wraps back to Gemini 2.5 Flash, skipping locked GPT-5.4, Claude, etc.
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toContain("Gemini 2.5 Flash");

    // Press ArrowUp -> moves back to Gemini 2.5 Pro
    fireEvent.keyDown(listbox, { key: "ArrowUp" });
    expect(document.activeElement?.textContent).toContain("Gemini 2.5 Pro");
  });

  it("selects focused option on Enter, closes picker, updates trigger label, and restores trigger focus", async () => {
    renderChat("user-a");
    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    const trigger = screen.getByTitle(STRINGS.en.chat.chooseModel);
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    const listbox = screen.getByRole("listbox");
    // Move to Gemini 2.5 Pro
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toContain("Gemini 2.5 Pro");

    // Press Enter to select
    fireEvent.keyDown(document.activeElement!, { key: "Enter" });

    // Picker closes
    expect(screen.queryByRole("listbox")).toBeNull();

    // Trigger focus is restored
    expect(document.activeElement).toBe(trigger);

    // Trigger now displays Gemini 2.5 Pro
    expect(trigger.textContent).toContain("Gemini 2.5 Pro");
  });

  it("closes picker and restores trigger focus on Escape key", async () => {
    renderChat("user-a");
    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    const trigger = screen.getByTitle(STRINGS.en.chat.chooseModel);
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    expect(screen.getByRole("listbox")).toBeTruthy();

    // Press Escape from focused option
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });

    // Picker closes
    expect(screen.queryByRole("listbox")).toBeNull();

    // Trigger focus is restored
    expect(document.activeElement).toBe(trigger);
  });

  it("supports Home and End keys to jump between first and last enabled options", async () => {
    renderChat("user-a");
    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    const trigger = screen.getByTitle(STRINGS.en.chat.chooseModel);
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    const listbox = screen.getByRole("listbox");

    // Press End -> jumps to Gemini 2.5 Pro (last enabled)
    fireEvent.keyDown(listbox, { key: "End" });
    expect(document.activeElement?.textContent).toContain("Gemini 2.5 Pro");

    // Press Home -> jumps to Gemini 2.5 Flash (first enabled)
    fireEvent.keyDown(listbox, { key: "Home" });
    expect(document.activeElement?.textContent).toContain("Gemini 2.5 Flash");
  });

  it("opens model picker via Enter and Space keys on trigger and moves focus to enabled option", async () => {
    renderChat("user-a");
    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    const trigger = screen.getByTitle(STRINGS.en.chat.chooseModel);
    trigger.focus();

    // 1. Open via Enter
    fireEvent.keyDown(trigger, { key: "Enter" });
    expect(screen.getByRole("listbox")).toBeTruthy();
    await waitFor(() => {
      expect(document.activeElement?.getAttribute("role")).toBe("option");
      expect(document.activeElement?.textContent).toContain("Gemini 2.5 Flash");
    });

    // Close via Escape to reset
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(trigger);

    // 2. Open via Space
    fireEvent.keyDown(trigger, { key: " " });
    expect(screen.getByRole("listbox")).toBeTruthy();
    await waitFor(() => {
      expect(document.activeElement?.getAttribute("role")).toBe("option");
      expect(document.activeElement?.textContent).toContain("Gemini 2.5 Flash");
    });
  });

  it("selects focused option on Space key, closes picker, updates trigger label, and restores trigger focus", async () => {
    renderChat("user-a");
    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    const trigger = screen.getByTitle(STRINGS.en.chat.chooseModel);
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    const listbox = screen.getByRole("listbox");
    // Move focus to Gemini 2.5 Pro
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toContain("Gemini 2.5 Pro");

    // Select with Space key
    fireEvent.keyDown(document.activeElement!, { key: " " });

    // Picker closes
    expect(screen.queryByRole("listbox")).toBeNull();

    // Trigger focus is restored and shows updated model
    expect(document.activeElement).toBe(trigger);
    expect(trigger.textContent).toContain("Gemini 2.5 Pro");
  });

  it("preserves Arabic RTL layout, displays localized locked text, and navigates enabled options in RTL", async () => {
    const basicUser: User = {
      id: "user-basic",
      username: "user-basic@example.com",
      name: "Basic User",
      phone: null,
      preferences: {},
      avatar_url: null,
      subscription_tier: "Basic",
      is_active: true,
      is_admin: false,
      created_at: new Date().toISOString(),
    };

    const basicUsage: UserUsage = {
      tier: "Basic",
      usage_month: "2026-09",
      messages: { used: 0, limit: 100, remaining: 100 },
      docs: { used: 0, limit: 10, remaining: 10 },
      allowed_models: [
        { provider: "gemini", model: "gemini-2.5-flash" },
      ],
      max_tokens: 1024,
    };

    vi.mocked(apiModule.getMyUsage).mockResolvedValue(basicUsage);

    renderChat(
      "user-basic",
      { user: basicUser },
      undefined,
      { lang: "ar", dir: "rtl" },
    );

    await waitFor(() => {
      expect(apiModule.getPublicCapabilities).toHaveBeenCalled();
    });

    // In Arabic, title attribute is from STRINGS.ar.chat.chooseModel ("اختر نموذجاً")
    const trigger = screen.getByTitle(STRINGS.ar.chat.chooseModel);
    trigger.focus();

    // Open via Enter key
    fireEvent.keyDown(trigger, { key: "Enter" });

    const listbox = screen.getByRole("listbox");
    expect(listbox).toBeTruthy();
    // RTL positioning: insetInlineEnd: 0
    expect(listbox.getAttribute("style")).toMatch(/inset-inline-end:\s*0/i);

    // Locked model displays localized Arabic upgrade/locked hint
    expect(listbox.textContent).toContain("ترقية إلى بريميوم");

    // Active enabled option is focused
    await waitFor(() => {
      expect(document.activeElement?.textContent).toContain("Gemini 2.5 Flash");
    });

    // ArrowDown wraps around back to Gemini 2.5 Flash because it's the only enabled option in Basic tier
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    expect(document.activeElement?.textContent).toContain("Gemini 2.5 Flash");

    // Escape closes picker and restores trigger focus
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});

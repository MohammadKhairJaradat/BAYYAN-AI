import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  deleteChatSession as apiDeleteChatSession,
  getChatSession,
  listChatSessions,
  renameChatSession as apiRenameChatSession,
} from "../services/api";
import type { ChatMessage, ChatSession } from "../types/api";
import { ChatHistoryContext, useAuth } from "./hooks";

const CURRENT_KEY_PREFIX = "bayyan.currentSessionId.";

export interface ChatHistoryContextType {
  sessions: ChatSession[];
  currentSessionId: string | null;
  messages: ChatMessage[];
  loadingSessions: boolean;
  loadingMessages: boolean;

  refreshSessions: () => Promise<void>;
  refreshMessages: (id: string) => Promise<void>;
  newChat: () => void;
  selectSession: (id: string) => Promise<void>;
  setCurrentSessionId: (id: string | null) => void;
  appendMessage: (m: ChatMessage) => void;
  setMessages: (msgs: ChatMessage[]) => void;
  upsertSession: (s: ChatSession) => void;
  renameSession: (id: string, title: string) => Promise<void>;
  deleteSession: (id: string) => Promise<void>;
}

export function ChatHistoryProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionsOwnerId, setSessionsOwnerId] = useState<string | null>(null);
  const [currentSessionId, _setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const hydrationToken = useRef(0);
  const sessionsRequestToken = useRef(0);
  const currentSessionIdRef = useRef<string | null>(null);
  const currentUserIdRef = useRef(userId);
  currentUserIdRef.current = userId;

  const setCurrentSessionId = useCallback((id: string | null) => {
    if (currentUserIdRef.current !== userId) return;
    if (currentSessionIdRef.current === id) return;
    hydrationToken.current += 1;
    currentSessionIdRef.current = id;
    _setCurrentSessionId(id);
    setMessages([]);
    if (!userId) return;
    const key = `${CURRENT_KEY_PREFIX}${userId}`;
    if (id) localStorage.setItem(key, id);
    else localStorage.removeItem(key);
  }, [userId]);

  const refreshSessions = useCallback(async () => {
    if (!userId) return;
    const token = ++sessionsRequestToken.current;
    setLoadingSessions(true);
    try {
      const list = await listChatSessions();
      if (token === sessionsRequestToken.current && currentUserIdRef.current === userId) {
        setSessions(list);
        setSessionsOwnerId(userId);
      }
      // A list request can precede a newly created session. The selected
      // thread's own GET handles a genuine 404; an older list must not clear it.
    } catch {
      // Keep the current thread visible through a transient list failure.
    } finally {
      if (token === sessionsRequestToken.current && currentUserIdRef.current === userId) {
        setLoadingSessions(false);
      }
    }
  }, [userId]);

  const refreshMessages = useCallback(async (id: string) => {
    if (currentUserIdRef.current !== userId || currentSessionIdRef.current !== id) return;
    const token = ++hydrationToken.current;
    setLoadingMessages(true);
    try {
      const session = await getChatSession(id);
      if (token === hydrationToken.current && currentUserIdRef.current === userId && currentSessionIdRef.current === id) {
        setMessages(session.messages);
      }
    } finally {
      if (token === hydrationToken.current && currentUserIdRef.current === userId) setLoadingMessages(false);
    }
  }, [userId]);

  // Hydrate sessions when the user changes.
  useEffect(() => {
    hydrationToken.current += 1;
    sessionsRequestToken.current += 1;
    setSessions([]);
    setSessionsOwnerId(null);
    setLoadingSessions(false);
    if (!userId) {
      currentSessionIdRef.current = null;
      _setCurrentSessionId(null);
      setMessages([]);
      return;
    }
    const storedId = localStorage.getItem(`${CURRENT_KEY_PREFIX}${userId}`);
    currentSessionIdRef.current = storedId;
    _setCurrentSessionId(storedId);
    setMessages([]);
    void refreshSessions();
  }, [userId, refreshSessions]);

  // When currentSessionId changes, fetch its messages.
  useEffect(() => {
    if (!currentSessionId || !userId) {
      setMessages([]);
      setLoadingMessages(false);
      return;
    }
    const token = ++hydrationToken.current;
    setLoadingMessages(true);
    getChatSession(currentSessionId)
      .then((s) => {
        if (token === hydrationToken.current && currentSessionIdRef.current === currentSessionId) {
          setMessages(s.messages);
        }
      })
      .catch(() => {
        if (token === hydrationToken.current && currentSessionIdRef.current === currentSessionId) {
          // Session vanished — clear it.
          setCurrentSessionId(null);
          setMessages([]);
        }
      })
      .finally(() => {
        if (token === hydrationToken.current) setLoadingMessages(false);
      });
  }, [currentSessionId, setCurrentSessionId, userId]);

  const newChat = useCallback(() => {
    setCurrentSessionId(null);
    setMessages([]);
  }, [setCurrentSessionId]);

  const selectSession = useCallback(
    async (id: string) => {
      setCurrentSessionId(id);
    },
    [setCurrentSessionId],
  );

  const appendMessage = useCallback((m: ChatMessage) => {
    if (currentUserIdRef.current !== userId) return;
    if (m.session_id !== (currentSessionIdRef.current ?? "")) return;
    setMessages((prev) => [...prev, m]);
  }, [userId]);

  const upsertSession = useCallback((s: ChatSession) => {
    if (currentUserIdRef.current !== userId || s.user_id !== userId) return;
    setSessionsOwnerId(userId);
    setSessions((prev) => {
      const idx = prev.findIndex((x) => x.id === s.id);
      if (idx === -1) return [s, ...prev];
      const next = prev.slice();
      next[idx] = s;
      // Re-sort so newly-updated session floats up.
      next.sort(
        (a, b) =>
          new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
      );
      return next;
    });
  }, [userId]);

  const renameSession = useCallback(async (id: string, title: string) => {
    if (currentUserIdRef.current !== userId) return;
    const updated = await apiRenameChatSession(id, title);
    if (currentUserIdRef.current !== userId) return;
    setSessions((prev) => prev.map((s) => (s.id === id ? updated : s)));
  }, [userId]);

  const deleteSession = useCallback(
    async (id: string) => {
      if (currentUserIdRef.current !== userId) return;
      await apiDeleteChatSession(id);
      if (currentUserIdRef.current !== userId) return;
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (currentSessionId === id) {
        setCurrentSessionId(null);
        setMessages([]);
      }
    },
    [currentSessionId, setCurrentSessionId, userId],
  );

  const value: ChatHistoryContextType = {
    sessions: sessionsOwnerId === userId ? sessions : [],
    currentSessionId,
    messages,
    loadingSessions,
    loadingMessages,
    refreshSessions,
    refreshMessages,
    newChat,
    selectSession,
    setCurrentSessionId,
    appendMessage,
    setMessages,
    upsertSession,
    renameSession,
    deleteSession,
  };

  return (
    <ChatHistoryContext.Provider value={value}>
      {children}
    </ChatHistoryContext.Provider>
  );
}

// @vitest-environment jsdom
import { useEffect } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { getChatSession, listChatSessions } from "../services/api";
import type { ChatMessage, ChatSession, User } from "../types/api";
import type { AuthContextType } from "./AuthContext";
import { ChatHistoryProvider } from "./ChatHistoryContext";
import { AuthContext, useChatHistory } from "./hooks";

vi.mock("../services/api", () => ({
  getChatSession: vi.fn(), listChatSessions: vi.fn(),
  deleteChatSession: vi.fn(), renameChatSession: vi.fn(),
}));

const sessions = ["a", "b"].map((id) => ({ id, user_id: "user-a" })) as ChatSession[];
const message = (sessionId: string): ChatMessage => ({
  id: `message-${sessionId}`, session_id: sessionId, role: "assistant", kind: "text",
  content: `Answer ${sessionId}`, created_at: new Date().toISOString(),
});

function Probe() {
  const { sessions: visibleSessions, currentSessionId, messages, selectSession, appendMessage } = useChatHistory();
  return <div>
    <span data-testid="thread">{currentSessionId ?? "none"}:{messages.map((item) => item.content).join(",")}</span>
    <span data-testid="sessions">{visibleSessions.map((item) => item.id).join(",")}</span>
    <button onClick={() => void selectSession("b")}>Switch to B</button>
    <button onClick={() => appendMessage(message("a"))}>Late A message</button>
  </div>;
}

afterEach(() => { cleanup(); localStorage.clear(); vi.resetAllMocks(); });

it("keeps the chosen conversation when an older fetch or reply finishes late", async () => {
  localStorage.setItem("bayyan.currentSessionId.user-a", "a");
  let finishA: (value: ChatSession & { messages: ChatMessage[] }) => void = () => undefined;
  const slowA = new Promise<ChatSession & { messages: ChatMessage[] }>((resolve) => { finishA = resolve; });
  vi.mocked(listChatSessions).mockResolvedValue(sessions);
  vi.mocked(getChatSession).mockImplementation((id) => id === "a" ? slowA : Promise.resolve({ ...sessions[1], messages: [message("b")] }));
  const auth = { user: { id: "user-a" } as User, loading: false } as AuthContextType;
  render(<AuthContext.Provider value={auth}><ChatHistoryProvider><Probe /></ChatHistoryProvider></AuthContext.Provider>);
  await waitFor(() => expect(getChatSession).toHaveBeenCalledWith("a"));
  fireEvent.click(screen.getByText("Switch to B"));
  await waitFor(() => expect(screen.getByTestId("thread").textContent).toBe("b:Answer b"));
  finishA({ ...sessions[0], messages: [message("a")] });
  fireEvent.click(screen.getByText("Late A message"));
  await waitFor(() => expect(screen.getByTestId("thread").textContent).toBe("b:Answer b"));
  expect(localStorage.getItem("bayyan.currentSessionId.user-a")).toBe("b");
});

it("never shows a previous account's sessions after an account switch", async () => {
  let finishA: (value: ChatSession[]) => void = () => undefined;
  const slowA = new Promise<ChatSession[]>((resolve) => { finishA = resolve; });
  const userBSessions = [{ id: "b-only", user_id: "user-b" }] as ChatSession[];
  vi.mocked(listChatSessions)
    .mockReturnValueOnce(slowA)
    .mockResolvedValueOnce(userBSessions);
  const authA = { user: { id: "user-a" } as User, loading: false } as AuthContextType;
  const authB = { user: { id: "user-b" } as User, loading: false } as AuthContextType;
  const view = (auth: AuthContextType) => (
    <AuthContext.Provider value={auth}><ChatHistoryProvider><Probe /></ChatHistoryProvider></AuthContext.Provider>
  );
  const { rerender } = render(view(authA));
  await waitFor(() => expect(listChatSessions).toHaveBeenCalledTimes(1));
  rerender(view(authB));
  await waitFor(() => expect(screen.getByTestId("sessions").textContent).toBe("b-only"));
  await act(async () => {
    finishA(sessions);
    await slowA;
  });
  expect(screen.getByTestId("sessions").textContent).toBe("b-only");
});

it("clears the previous account's sidebar while the next account loads", async () => {
  let finishB: (value: ChatSession[]) => void = () => undefined;
  const slowB = new Promise<ChatSession[]>((resolve) => { finishB = resolve; });
  vi.mocked(listChatSessions)
    .mockResolvedValueOnce(sessions)
    .mockReturnValueOnce(slowB);
  const authA = { user: { id: "user-a" } as User, loading: false } as AuthContextType;
  const authB = { user: { id: "user-b" } as User, loading: false } as AuthContextType;
  const view = (auth: AuthContextType) => (
    <AuthContext.Provider value={auth}><ChatHistoryProvider><Probe /></ChatHistoryProvider></AuthContext.Provider>
  );
  const { rerender } = render(view(authA));
  await waitFor(() => expect(screen.getByTestId("sessions").textContent).toBe("a,b"));
  rerender(view(authB));
  await waitFor(() => expect(screen.getByTestId("sessions").textContent).toBe(""));
  await act(async () => {
    finishB([{ id: "b-only", user_id: "user-b" }] as ChatSession[]);
    await slowB;
  });
  expect(screen.getByTestId("sessions").textContent).toBe("b-only");
});

it("ignores a session created by a stale callback from another account", async () => {
  vi.mocked(listChatSessions).mockResolvedValue([]);
  let upsert: ReturnType<typeof useChatHistory>["upsertSession"] = () => undefined;
  function CaptureUpsert() {
    const currentUpsert = useChatHistory().upsertSession;
    useEffect(() => { upsert = currentUpsert; }, [currentUpsert]);
    return null;
  }
  const view = (id: string) => (
    <AuthContext.Provider value={{ user: { id } as User, loading: false } as AuthContextType}>
      <ChatHistoryProvider><CaptureUpsert /><Probe /></ChatHistoryProvider>
    </AuthContext.Provider>
  );
  const { rerender } = render(view("user-a"));
  await waitFor(() => expect(listChatSessions).toHaveBeenCalledTimes(1));
  const staleUpsert = upsert;
  rerender(view("user-b"));
  await waitFor(() => expect(listChatSessions).toHaveBeenCalledTimes(2));
  act(() => staleUpsert({ id: "a-late", user_id: "user-a" } as ChatSession));
  expect(screen.getByTestId("sessions").textContent).toBe("");
  act(() => upsert({ id: "b-new", user_id: "user-b" } as ChatSession));
  expect(screen.getByTestId("sessions").textContent).toBe("b-new");
});

import { useEffect, useRef, useState } from "react";
import { useChatHistory } from "../../contexts/hooks";
import { useLang } from "../../contexts/hooks";
import type { ChatSession } from "../../types/api";
import { Icon } from "../brand";

const COLLAPSED_KEY = "taxai.chatSidebarCollapsed";

type Bucket = "Today" | "Yesterday" | "Last 7 days" | "Earlier";
const BUCKET_KEY: Record<Bucket, "today" | "yesterday" | "week" | "earlier"> = {
  Today: "today",
  Yesterday: "yesterday",
  "Last 7 days": "week",
  Earlier: "earlier",
};

function bucketFor(date: Date): Bucket {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dayDiff = Math.round((today.getTime() - target.getTime()) / (1000 * 60 * 60 * 24));
  if (dayDiff <= 0) return "Today";
  if (dayDiff === 1) return "Yesterday";
  if (dayDiff <= 7) return "Last 7 days";
  return "Earlier";
}

function groupSessions(sessions: ChatSession[]): Record<Bucket, ChatSession[]> {
  const groups: Record<Bucket, ChatSession[]> = { Today: [], Yesterday: [], "Last 7 days": [], Earlier: [] };
  for (const s of sessions) groups[bucketFor(new Date(s.updated_at))].push(s);
  return groups;
}

const BUCKET_ORDER: Bucket[] = ["Today", "Yesterday", "Last 7 days", "Earlier"];

export function ChatHistorySidebar() {
  const { t } = useLang();
  const C = t.chat;
  const { sessions, currentSessionId, newChat, selectSession, renameSession, deleteSession, loadingSessions } = useChatHistory();

  const [collapsed, setCollapsed] = useState<boolean>(() => localStorage.getItem(COLLAPSED_KEY) === "1");
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState<string>("");
  const menuRef = useRef<HTMLDivElement>(null);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0");
      return next;
    });
    setMenuOpenId(null);
  }

  useEffect(() => {
    if (!menuOpenId) return;
    function onClick(e: MouseEvent) {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpenId(null);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [menuOpenId]);

  function startRename(s: ChatSession) {
    setEditingId(s.id);
    setEditingTitle(s.title);
    setMenuOpenId(null);
  }

  async function commitRename(id: string) {
    const trimmed = editingTitle.trim();
    if (trimmed) {
      try {
        await renameSession(id, trimmed);
      } catch {
        /* ignore */
      }
    }
    setEditingId(null);
    setEditingTitle("");
  }

  async function handleDelete(s: ChatSession) {
    setMenuOpenId(null);
    if (!confirm(`${C.delete} "${s.title}"?`)) return;
    try {
      await deleteSession(s.id);
    } catch {
      /* ignore */
    }
  }

  const grouped = groupSessions(sessions);

  return (
    <aside
      className="card max-md:hidden"
      style={{
        flex: "none",
        width: collapsed ? 64 : 268,
        height: "clamp(560px, 76vh, 780px)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        padding: 0,
        transition: "width .2s",
      }}
    >
      {/* Header */}
      <div className="row" style={{ gap: 8, padding: 12, alignItems: "center", flexDirection: collapsed ? "column" : "row" }}>
        <button
          type="button"
          onClick={newChat}
          title={C.newChat}
          className="row"
          style={{
            gap: 8,
            height: 42,
            borderRadius: 11,
            border: "1px solid var(--green-tint2)",
            background: "var(--green-tint)",
            color: "var(--green-deep)",
            flex: collapsed ? "none" : 1,
            width: collapsed ? 40 : "auto",
            justifyContent: "center",
            padding: collapsed ? 0 : "0 14px",
            fontWeight: 600,
            fontSize: 14,
          }}
        >
          <Icon name="plus" size={17} />
          {!collapsed && <span>{C.newChat}</span>}
        </button>
        <button
          type="button"
          onClick={toggleCollapsed}
          style={{ width: 40, height: 40, flex: "none", borderRadius: 11, border: "1px solid var(--line)", background: "var(--paper)", display: "grid", placeItems: "center", color: "var(--ink-soft)" }}
          title={collapsed ? "Expand" : "Collapse"}
        >
          <Icon name="sidebar" size={16} color="currentColor" />
        </button>
      </div>

      {/* Body */}
      <div className="hide-scrollbar" style={{ flex: 1, overflowY: "auto", padding: "0 8px 12px" }}>
        {loadingSessions && sessions.length === 0 && !collapsed && (
          <div className="t-small faint center" style={{ padding: "16px 0" }}>
            {t.common.loading}
          </div>
        )}

        {collapsed
          ? sessions.slice(0, 12).map((s) => {
              const active = s.id === currentSessionId;
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => selectSession(s.id)}
                  title={s.title}
                  style={{
                    width: 40,
                    height: 40,
                    margin: "0 auto 4px",
                    borderRadius: 11,
                    display: "grid",
                    placeItems: "center",
                    border: "none",
                    background: active ? "var(--green-tint)" : "transparent",
                    color: active ? "var(--green)" : "var(--ink-faint)",
                  }}
                >
                  <Icon name="chat" size={16} color="currentColor" />
                </button>
              );
            })
          : BUCKET_ORDER.map((bucket) => {
              const items = grouped[bucket];
              if (items.length === 0) return null;
              return (
                <div key={bucket} style={{ marginBottom: 12 }}>
                  <div className="t-eyebrow" style={{ color: "var(--ink-faint)", fontSize: 10, padding: "4px 8px" }}>
                    {C.buckets[BUCKET_KEY[bucket]]}
                  </div>
                  {items.map((s) => {
                    const isActive = s.id === currentSessionId;
                    const isEditing = editingId === s.id;
                    return (
                      <div
                        key={s.id}
                        className="group"
                        style={{ position: "relative", borderRadius: 9, marginBottom: 2, background: isActive ? "var(--green-tint)" : "transparent" }}
                      >
                        {isEditing ? (
                          <input
                            autoFocus
                            value={editingTitle}
                            onChange={(e) => setEditingTitle(e.target.value)}
                            onBlur={() => commitRename(s.id)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") commitRename(s.id);
                              if (e.key === "Escape") {
                                setEditingId(null);
                                setEditingTitle("");
                              }
                            }}
                            className="input"
                            style={{ padding: "6px 8px", fontSize: 14 }}
                          />
                        ) : (
                          <button
                            type="button"
                            onClick={() => selectSession(s.id)}
                            title={s.title}
                            style={{
                              width: "100%",
                              textAlign: "start",
                              padding: "8px 8px",
                              paddingInlineEnd: 32,
                              fontSize: 14,
                              border: "none",
                              background: "transparent",
                              color: isActive ? "var(--green)" : "var(--ink-soft)",
                              whiteSpace: "nowrap",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                            }}
                          >
                            {s.title || (t.dir === "rtl" ? "بدون عنوان" : "Untitled")}
                          </button>
                        )}

                        {!isEditing && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setMenuOpenId(menuOpenId === s.id ? null : s.id);
                            }}
                            className="group-hover:opacity-100"
                            style={{
                              position: "absolute",
                              insetInlineEnd: 4,
                              top: "50%",
                              transform: "translateY(-50%)",
                              width: 24,
                              height: 24,
                              borderRadius: 7,
                              display: "grid",
                              placeItems: "center",
                              border: "none",
                              background: "transparent",
                              color: "var(--ink-faint)",
                              opacity: menuOpenId === s.id ? 1 : 0,
                            }}
                            title="More"
                          >
                            <Icon name="dots" size={16} color="currentColor" />
                          </button>
                        )}

                        {menuOpenId === s.id && (
                          <div
                            ref={menuRef}
                            style={{
                              position: "absolute",
                              insetInlineEnd: 4,
                              top: 36,
                              zIndex: 30,
                              minWidth: 140,
                              borderRadius: 10,
                              border: "1px solid var(--line)",
                              background: "var(--paper)",
                              boxShadow: "var(--shadow-lg)",
                              overflow: "hidden",
                            }}
                          >
                            <button type="button" onClick={() => startRename(s)} style={{ width: "100%", textAlign: "start", padding: "9px 12px", fontSize: 14, border: "none", background: "transparent", color: "var(--ink)" }}>
                              {C.rename}
                            </button>
                            <button type="button" onClick={() => handleDelete(s)} style={{ width: "100%", textAlign: "start", padding: "9px 12px", fontSize: 14, border: "none", background: "transparent", color: "var(--danger)" }}>
                              {C.delete}
                            </button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}

        {!collapsed && !loadingSessions && sessions.length === 0 && (
          <div className="t-small faint center" style={{ padding: "32px 12px", lineHeight: 1.6 }}>
            {t.dir === "rtl" ? "ما في محادثات بعد." : "No chats yet."}
          </div>
        )}
      </div>
    </aside>
  );
}

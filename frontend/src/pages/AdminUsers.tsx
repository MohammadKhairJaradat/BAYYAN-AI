import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getApiErrorMessage, listAdminUsers } from "../services/api";
import type { AdminUserList, AdminUserListQuery, SubscriptionTier } from "../types/api";
import { useLang } from "../contexts/hooks";

const TIERS: SubscriptionTier[] = ["Basic", "Pro", "Premium"];
const PAGE_SIZE = 25;

function TierBadge({ tier }: { tier: string }) {
  const cls: Record<string, string> = {
    Basic: "chip",
    Pro: "chip chip-green",
    Premium: "chip chip-gold",
  };
  return <span className={cls[tier] ?? "chip"}>{tier}</span>;
}

export default function AdminUsers() {
  const { t, fill } = useLang();
  const A = t.admin;
  const [q, setQ] = useState("");
  const [tier, setTier] = useState<SubscriptionTier | "">("");
  const [active, setActive] = useState<"" | "true" | "false">("");
  const [page, setPage] = useState(1);

  const [data, setData] = useState<AdminUserList | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const totalPages = useMemo(() => {
    if (!data) return 1;
    return Math.max(1, Math.ceil(data.total / data.page_size));
  }, [data]);

  useEffect(() => {
    let alive = true;
    const query: AdminUserListQuery = { page, page_size: PAGE_SIZE };
    if (q.trim()) query.q = q.trim();
    if (tier) query.tier = tier;
    if (active === "true") query.active = true;
    if (active === "false") query.active = false;

    listAdminUsers(query)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((err) => {
        if (alive) setErrorMsg(getApiErrorMessage(err, t.common.error));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [q, tier, active, page, t.common.error]);

  function beginRefresh() {
    setLoading(true);
    setErrorMsg(null);
  }

  const th: React.CSSProperties = {
    textAlign: "start",
    padding: "12px 16px",
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: ".06em",
    textTransform: "uppercase",
    color: "var(--ink-faint)",
    borderBottom: "1px solid var(--line)",
  };
  const td: React.CSSProperties = { padding: "12px 16px", borderBottom: "1px solid var(--line)" };

  return (
    <div className="wrap wrap-app" style={{ paddingBlock: "40px 64px" }}>
      <div className="row-between" style={{ marginBottom: 24, alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 className="display t-h1" style={{ marginBottom: 6 }}>
            {A.usersTitle}
          </h1>
          <p className="t-body">{A.usersSub}</p>
        </div>
        <Link to="/admin" className="green t-small" style={{ fontWeight: 600 }}>
          ← {A.title}
        </Link>
      </div>

      <div className="card card-pad" style={{ padding: 16, marginBottom: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }} className="max-md:!grid-cols-1">
          <input
            type="text"
            className="input"
            value={q}
            onChange={(e) => {
              beginRefresh();
              setPage(1);
              setQ(e.target.value);
            }}
            placeholder={A.searchPh}
          />
          <select className="select" value={tier} onChange={(e) => { beginRefresh(); setPage(1); setTier(e.target.value as SubscriptionTier | ""); }}>
            <option value="">{A.allTiers}</option>
            {TIERS.map((ti) => (
              <option key={ti} value={ti}>
                {ti}
              </option>
            ))}
          </select>
          <select className="select" value={active} onChange={(e) => { beginRefresh(); setPage(1); setActive(e.target.value as "" | "true" | "false"); }}>
            <option value="">{A.allAccounts}</option>
            <option value="true">{A.activeOnly}</option>
            <option value="false">{A.inactiveOnly}</option>
          </select>
          <div className="row t-small faint" style={{ justifyContent: "flex-end" }}>
            {data ? `${data.total} ${A.totalSuffix}` : ""}
          </div>
        </div>
      </div>

      {loading ? (
        <div className="card card-pad center" style={{ color: "var(--ink-soft)" }}>
          {t.common.loading}
        </div>
      ) : errorMsg ? (
        <div className="card card-pad" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
          {errorMsg}
        </div>
      ) : data ? (
        <>
          <div className="card" style={{ overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr>
                  <th style={th}>{A.colUser}</th>
                  <th style={th}>{A.colTier}</th>
                  <th style={th}>{A.colStatus}</th>
                  <th style={th}>{A.colAdmin}</th>
                  <th style={th}>{A.colJoined}</th>
                  <th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ ...td, textAlign: "center", color: "var(--ink-faint)", padding: "40px 16px" }}>
                      {A.noMatch}
                    </td>
                  </tr>
                ) : (
                  data.items.map((u) => (
                    <tr key={u.id}>
                      <td style={td}>
                        <div style={{ color: "var(--ink)", fontWeight: 600 }}>{u.name}</div>
                        <div className="t-small faint">{u.username}</div>
                      </td>
                      <td style={td}>
                        <TierBadge tier={u.subscription_tier} />
                      </td>
                      <td style={td}>
                        <span className="t-small" style={{ fontWeight: 600, color: u.is_active ? "var(--positive)" : "var(--danger)" }}>
                          {u.is_active ? A.statusActive : A.statusInactive}
                        </span>
                      </td>
                      <td style={td}>
                        {u.is_admin ? (
                          <span className="t-small gold" style={{ fontWeight: 600 }}>
                            {A.adminYes}
                          </span>
                        ) : (
                          <span className="t-small faint">—</span>
                        )}
                      </td>
                      <td style={{ ...td, color: "var(--ink-soft)", fontSize: 12.5 }}>
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ ...td, textAlign: "end" }}>
                        <Link to={`/admin/users/${u.id}`} className="green t-small" style={{ fontWeight: 600 }}>
                          {A.manage} →
                        </Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div className="row-between" style={{ marginTop: 16 }}>
            <div className="t-small faint">{fill(A.pageOf, { page: data.page, total: totalPages })}</div>
            <div className="row" style={{ gap: 8 }}>
              <button
                disabled={data.page <= 1}
                onClick={() => { beginRefresh(); setPage((p) => Math.max(1, p - 1)); }}
                className="btn btn-ghost btn-sm"
                style={{ opacity: data.page <= 1 ? 0.4 : 1 }}
              >
                ← {A.prev}
              </button>
              <button
                disabled={data.page >= totalPages}
                onClick={() => { beginRefresh(); setPage((p) => p + 1); }}
                className="btn btn-ghost btn-sm"
                style={{ opacity: data.page >= totalPages ? 0.4 : 1 }}
              >
                {A.next} →
              </button>
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

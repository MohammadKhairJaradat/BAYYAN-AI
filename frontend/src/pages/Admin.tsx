import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getAdminStats, getApiErrorMessage } from "../services/api";
import type { AdminStats } from "../types/api";
import { useLang } from "../contexts/hooks";
import { Button } from "../components/brand";

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card card-pad" style={{ padding: 18 }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)", fontSize: 10.5, marginBottom: 8 }}>
        {label}
      </div>
      <div className="num" style={{ fontSize: 26, fontWeight: 600 }}>
        {value}
      </div>
    </div>
  );
}

export default function Admin() {
  const { t } = useLang();
  const A = t.admin;
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    getAdminStats()
      .then((data) => {
        if (alive) setStats(data);
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
  }, [t.common.error]);

  return (
    <div className="wrap wrap-app" style={{ paddingBlock: "40px 64px" }}>
      <div className="row-between" style={{ marginBottom: 24, alignItems: "flex-end", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 className="display t-h1" style={{ marginBottom: 6 }}>
            {A.title}
          </h1>
          <p className="t-body">{A.sub}</p>
        </div>
        <Link to="/admin/users">
          <Button variant="ghost" size="sm" iconRight="arrow">
            {A.manageUsers}
          </Button>
        </Link>
      </div>

      {loading ? (
        <div className="card card-pad center" style={{ color: "var(--ink-soft)" }}>
          {t.common.loading}
        </div>
      ) : errorMsg ? (
        <div className="card card-pad" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
          {errorMsg}
        </div>
      ) : stats ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 16 }} className="max-md:!grid-cols-2">
            <StatCard label={A.totalUsers} value={stats.total_users} />
            <StatCard label={A.active} value={stats.active_users} />
            <StatCard label={A.inactive} value={stats.inactive_users} />
            <StatCard label={A.admins} value={stats.admins} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 16 }} className="max-md:!grid-cols-2">
            <StatCard label={A.signups} value={stats.signups_this_month} />
            <StatCard label={A.messagesMonth} value={stats.messages_this_month} />
            <StatCard label={A.docsMonth} value={stats.docs_this_month} />
            <StatCard label={A.sessions} value={stats.total_chat_sessions} />
          </div>

          <div className="card card-pad">
            <div className="t-eyebrow" style={{ marginBottom: 16 }}>
              {A.bySubscription}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16 }} className="max-md:!grid-cols-1">
              {stats.tier_counts.map((tc) => (
                <div key={tc.tier} style={{ borderRadius: 12, background: "var(--paper-2)", border: "1px solid var(--line)", padding: 16 }}>
                  <div className="t-small">{tc.tier}</div>
                  <div className="num" style={{ fontSize: 30, fontWeight: 600 }}>
                    {tc.count}
                  </div>
                </div>
              ))}
            </div>
            <div className="t-small faint" style={{ marginTop: 16 }}>
              {A.totalDocs}: {stats.total_documents}
            </div>
          </div>
        </>
      ) : null}
    </div>
  );
}

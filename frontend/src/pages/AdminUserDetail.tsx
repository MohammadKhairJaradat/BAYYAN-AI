import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../contexts/hooks";
import { getAdminUser, getApiErrorMessage, patchAdminUser, resetAdminUserUsage } from "../services/api";
import type { AdminUserDetail, SubscriptionTier } from "../types/api";
import { useLang } from "../contexts/hooks";

const TIERS: SubscriptionTier[] = ["Basic", "Pro", "Premium"];

function UsageBar({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  return (
    <div>
      <div className="row-between t-small faint" style={{ marginBottom: 4 }}>
        <span className="num">
          {used} / {limit}
        </span>
        <span className="num">{pct}%</span>
      </div>
      <div style={{ height: 8, borderRadius: 999, background: "var(--line)", overflow: "hidden" }}>
        <div style={{ height: "100%", background: "var(--green)", width: `${pct}%` }} />
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="card card-pad" style={{ padding: 16 }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)", fontSize: 10.5, marginBottom: 6 }}>
        {label}
      </div>
      <div className="num" style={{ fontSize: 24, fontWeight: 600 }}>
        {value}
      </div>
    </div>
  );
}

export default function AdminUserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user: me } = useAuth();
  const { t, fill } = useLang();
  const A = t.admin;
  const [data, setData] = useState<AdminUserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      setData(await getAdminUser(id));
    } catch (err) {
      setErrorMsg(getApiErrorMessage(err, t.common.error));
    } finally {
      setLoading(false);
    }
  }, [id, t.common.error]);

  useEffect(() => {
    load();
  }, [load]);

  function flash(msg: string) {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3000);
  }

  async function changeTier(tier: SubscriptionTier) {
    if (!id || !data || tier === data.subscription_tier) return;
    setSaving(true);
    setErrorMsg(null);
    try {
      setData(await patchAdminUser(id, { subscription_tier: tier }));
      flash(fill(A.toastTier, { tier }));
    } catch (err) {
      setErrorMsg(getApiErrorMessage(err, t.common.error));
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive() {
    if (!id || !data) return;
    setSaving(true);
    setErrorMsg(null);
    try {
      const updated = await patchAdminUser(id, { is_active: !data.is_active });
      setData(updated);
      flash(updated.is_active ? A.toastReactivated : A.toastDeactivated);
    } catch (err) {
      setErrorMsg(getApiErrorMessage(err, t.common.error));
    } finally {
      setSaving(false);
    }
  }

  async function resetUsage() {
    if (!id) return;
    if (!window.confirm(A.confirmReset)) return;
    setResetting(true);
    setErrorMsg(null);
    try {
      setData(await resetAdminUserUsage(id));
      flash(A.toastReset);
    } catch (err) {
      setErrorMsg(getApiErrorMessage(err, t.common.error));
    } finally {
      setResetting(false);
    }
  }

  const segBtn = (active: boolean): React.CSSProperties => ({
    padding: "8px 13px",
    borderRadius: 9,
    fontSize: 13,
    fontWeight: 600,
    border: "1px solid " + (active ? "var(--green)" : "var(--line-strong)"),
    background: active ? "var(--green-tint)" : "var(--paper)",
    color: active ? "var(--green)" : "var(--ink-soft)",
  });

  return (
    <div className="wrap wrap-app" style={{ maxWidth: 920, paddingBlock: "40px 64px" }}>
      <div className="row-between" style={{ marginBottom: 20, gap: 16 }}>
        <Link to="/admin/users" className="t-small" style={{ color: "var(--ink-soft)", fontWeight: 600 }}>
          ← {A.back}
        </Link>
        {toast && <span className="chip chip-green">{toast}</span>}
      </div>

      {loading ? (
        <div className="card card-pad center" style={{ color: "var(--ink-soft)" }}>
          {t.common.loading}
        </div>
      ) : errorMsg && !data ? (
        <div className="card card-pad" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
          {errorMsg}
        </div>
      ) : data ? (
        <>
          <div className="card card-pad" style={{ marginBottom: 20 }}>
            <div className="row-between" style={{ alignItems: "flex-start", gap: 16 }}>
              <div>
                <h1 className="display t-h2">{data.name}</h1>
                <p className="t-small" style={{ marginTop: 2 }}>
                  {data.username}
                </p>
                <p className="t-small faint" style={{ marginTop: 8 }}>
                  {A.joined} {new Date(data.created_at).toLocaleDateString()}
                  {data.phone ? ` · ${data.phone}` : ""}
                </p>
              </div>
              <div className="t-small faint" style={{ textAlign: "end" }}>
                <div>{A.idLabel}</div>
                <div className="num" style={{ color: "var(--ink-soft)" }}>
                  {data.id.slice(0, 8)}…
                </div>
              </div>
            </div>
          </div>

          {errorMsg && (
            <div className="t-small" style={{ color: "var(--danger)", background: "var(--clay-tint)", borderRadius: 10, padding: "10px 14px", marginBottom: 16 }}>
              {errorMsg}
            </div>
          )}

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 20 }} className="max-md:!grid-cols-1">
            <div className="card card-pad">
              <div className="t-eyebrow" style={{ marginBottom: 12 }}>
                {A.subscription}
              </div>
              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                {TIERS.map((ti) => {
                  const isCurrent = ti === data.subscription_tier;
                  return (
                    <button key={ti} disabled={saving || isCurrent} onClick={() => changeTier(ti)} style={segBtn(isCurrent)}>
                      {ti}
                      {isCurrent && ` · ${A.current}`}
                    </button>
                  );
                })}
              </div>
              <p className="t-small faint" style={{ marginTop: 12 }}>
                {A.tierNote}
              </p>
            </div>

            <div className="card card-pad">
              <div className="t-eyebrow" style={{ marginBottom: 12 }}>
                {A.accountState}
              </div>
              <div className="row-between" style={{ gap: 12, alignItems: "flex-start" }}>
                <div>
                  <div className="t-body" style={{ color: "var(--ink)", fontWeight: 600 }}>
                    {data.is_active ? A.statusActive : A.statusInactive}
                  </div>
                  <div className="t-small">{data.is_active ? A.activeDesc : A.inactiveDesc}</div>
                </div>
                <button
                  disabled={saving || data.id === me?.id}
                  onClick={toggleActive}
                  style={{ ...segBtn(false), opacity: saving || data.id === me?.id ? 0.5 : 1 }}
                  title={data.id === me?.id ? A.cantSelf : ""}
                >
                  {data.is_active ? A.deactivate : A.reactivate}
                </button>
              </div>
              {data.is_admin && (
                <div className="t-small gold" style={{ marginTop: 12, fontWeight: 600 }}>
                  {A.isAdminNote}
                </div>
              )}
            </div>
          </div>

          <div className="card card-pad" style={{ marginBottom: 20 }}>
            <div className="row-between" style={{ marginBottom: 16 }}>
              <div>
                <div className="t-eyebrow">{A.usageTitle}</div>
                <div className="t-small faint" style={{ marginTop: 4 }}>
                  {fill(A.monthOf, { month: data.usage_month })}
                </div>
              </div>
              <button disabled={resetting} onClick={resetUsage} style={{ ...segBtn(false), opacity: resetting ? 0.5 : 1 }}>
                {resetting ? A.resetting : A.resetCounters}
              </button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }} className="max-md:!grid-cols-1">
              <div>
                <div className="t-small" style={{ marginBottom: 6 }}>
                  {A.messagesLbl}
                </div>
                <UsageBar used={data.messages.used} limit={data.messages.limit} />
              </div>
              <div>
                <div className="t-small" style={{ marginBottom: 6 }}>
                  {A.documentsLbl}
                </div>
                <UsageBar used={data.docs.used} limit={data.docs.limit} />
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16 }} className="max-md:!grid-cols-2">
            <MiniStat label={A.docCount} value={data.document_count} />
            <MiniStat label={A.taxProfiles} value={data.tax_profile_count} />
            <MiniStat label={A.msgsUsed} value={data.messages.used} />
            <MiniStat label={A.docsUsed} value={data.docs.used} />
          </div>
        </>
      ) : null}
    </div>
  );
}

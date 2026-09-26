import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/hooks";
import { useLang } from "../contexts/hooks";
import { api, deleteAvatar, getMyUsage, updateMe, uploadAvatar } from "../services/api";
import type { TaxProfile, UserUsage } from "../types/api";
import { ImageCropperModal } from "../components/ui/image-cropper";
import { Button } from "../components/brand";

type FilingStatus = "individual" | "joint";

function usagePercent(used: number, limit: number): number {
  if (limit <= 0) return used > 0 ? 100 : 0;
  return Math.min(100, Math.round((used / limit) * 100));
}

function formatUsageMonth(value: string): string {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

export default function Profile() {
  const { user, refreshUser } = useAuth();
  const { t } = useLang();
  const S = t.settings;
  const isAr = t.dir === "rtl";

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [filingStatus, setFilingStatus] = useState<FilingStatus>("individual");

  const [currentProfile, setCurrentProfile] = useState<TaxProfile | null>(null);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [usage, setUsage] = useState<UserUsage | null>(null);
  const [usageLoading, setUsageLoading] = useState(true);

  const [cropOpen, setCropOpen] = useState(false);
  const [pendingObjectUrl, setPendingObjectUrl] = useState<string | null>(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    return () => {
      if (pendingObjectUrl) URL.revokeObjectURL(pendingObjectUrl);
    };
  }, [pendingObjectUrl]);

  useEffect(() => {
    if (!user) return;
    setName(user.name ?? "");
    setPhone(user.phone ?? "");
  }, [user]);

  const refreshUsage = useCallback(async () => {
    setUsageLoading(true);
    try {
      setUsage(await getMyUsage());
    } catch {
      setUsage(null);
    } finally {
      setUsageLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    void refreshUsage();
  }, [user, refreshUsage]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await api.get<TaxProfile[]>("/tax-profiles/");
        if (cancelled) return;
        const currentYear = new Date().getFullYear();
        const profile = resp.data.find((p) => p.tax_year === currentYear) ?? null;
        setCurrentProfile(profile);
        if (profile?.filing_status === "joint") setFilingStatus("joint");
        else if (profile?.filing_status === "individual") setFilingStatus("individual");
      } catch {
        /* ignore — profile load is best-effort */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!user) return;
    setSaving(true);
    setErrorMsg(null);
    setToast(null);
    try {
      await updateMe({ name: name.trim(), phone: phone.trim() || null });
      if (currentProfile && currentProfile.filing_status !== filingStatus) {
        await api.put(`/tax-profiles/${currentProfile.id}`, { filing_status: filingStatus });
      }
      await refreshUser();
      setToast(isAr ? "تم حفظ الملف." : "Profile saved.");
      setTimeout(() => setToast(null), 3000);
    } catch {
      setErrorMsg(t.common.error);
    } finally {
      setSaving(false);
    }
  }

  if (!user) {
    return (
      <div className="wrap" style={{ display: "grid", placeItems: "center", paddingBlock: 120 }}>
        <div style={{ width: 32, height: 32, borderRadius: 999, border: "3px solid var(--green-tint2)", borderTopColor: "var(--green)", animation: "spin 1s linear infinite" }} />
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      </div>
    );
  }

  const initial = (user.name || user.username || "U").trim().charAt(0).toUpperCase();
  const currentTier = usage?.tier ?? user.subscription_tier ?? "Basic";

  return (
    <form onSubmit={handleSave} className="wrap" style={{ maxWidth: 860, paddingBlock: "40px 64px" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 className="display t-h1" style={{ marginBottom: 6 }}>
          {S.profileTitle}
        </h1>
        <p className="t-body">{S.sub}</p>
      </div>

      <div className="card card-pad" style={{ display: "flex", flexDirection: "column", gap: 24 }}>
        {/* Avatar */}
        <div className="row" style={{ gap: 22, paddingBottom: 22, borderBottom: "1px solid var(--line)" }}>
          {user.avatar_url ? (
            <img src={user.avatar_url} alt="Avatar" style={{ width: 88, height: 88, borderRadius: 999, objectFit: "cover", border: "2px solid var(--green-tint2)" }} />
          ) : (
            <div style={{ width: 88, height: 88, borderRadius: 999, background: "var(--green-tint)", border: "2px solid var(--green-tint2)", display: "grid", placeItems: "center", color: "var(--green)", fontWeight: 700, fontSize: 32 }}>
              {initial}
            </div>
          )}
          <div>
            <input
              ref={fileRef}
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (!f) return;
                if (pendingObjectUrl) URL.revokeObjectURL(pendingObjectUrl);
                setPendingObjectUrl(URL.createObjectURL(f));
                setCropOpen(true);
              }}
            />
            <div className="row" style={{ gap: 8 }}>
              <Button type="button" variant="ghost" size="sm" disabled={avatarBusy} onClick={() => fileRef.current?.click()}>
                {user.avatar_url ? (isAr ? "تغيير الصورة" : "Replace photo") : isAr ? "رفع صورة" : "Upload photo"}
              </Button>
              {user.avatar_url && (
                <Button
                  type="button"
                  variant="quiet"
                  size="sm"
                  disabled={avatarBusy}
                  onClick={async () => {
                    setAvatarBusy(true);
                    setErrorMsg(null);
                    setToast(null);
                    try {
                      await deleteAvatar();
                      await refreshUser();
                      setToast(isAr ? "تمت إزالة الصورة." : "Avatar removed.");
                      setTimeout(() => setToast(null), 3000);
                    } catch {
                      setErrorMsg(t.common.error);
                    } finally {
                      setAvatarBusy(false);
                    }
                  }}
                >
                  {isAr ? "إزالة" : "Remove"}
                </Button>
              )}
            </div>
            <p className="t-small faint" style={{ marginTop: 8 }}>
              PNG, JPEG, WebP · ≤ 10 MiB
            </p>
          </div>
        </div>

        <ImageCropperModal
          open={cropOpen}
          onClose={() => {
            setCropOpen(false);
            if (pendingObjectUrl) {
              URL.revokeObjectURL(pendingObjectUrl);
              setPendingObjectUrl(null);
            }
          }}
          initialImageUrl={pendingObjectUrl ?? user.avatar_url ?? null}
          defaultAspect="1:1"
          lockAspect
          title={S.profileTitle}
          onSave={async (blob) => {
            const file = new File([blob], "avatar.jpg", { type: blob.type || "image/jpeg" });
            await uploadAvatar(file);
            await refreshUser();
            setToast(isAr ? "تم تحديث الصورة." : "Avatar updated.");
            setTimeout(() => setToast(null), 3000);
          }}
        />

        {/* Subscription + usage */}
        <div style={{ paddingBottom: 22, borderBottom: "1px solid var(--line)" }}>
          <div className="row-between" style={{ marginBottom: 16, flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
            <div>
              <div className="row" style={{ gap: 10 }}>
                <h2 className="t-h3" style={{ fontSize: 18 }}>
                  {S.title === "Settings" ? "Subscription" : t.admin.subscription}
                </h2>
                <span className="chip chip-green">{currentTier}</span>
              </div>
              <p className="t-small faint" style={{ marginTop: 4 }}>
                {usage ? `${t.admin.monthOf.replace("{month}", formatUsageMonth(usage.usage_month))}` : ""}
              </p>
            </div>
            <Link to="/pricing">
              <Button type="button" variant="ghost" size="sm" iconRight="arrow">
                {t.nav.pricing}
              </Button>
            </Link>
          </div>

          {usageLoading ? (
            <div className="t-small faint">{t.common.loading}</div>
          ) : usage ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }} className="max-md:!grid-cols-1">
              {[
                { label: t.admin.messagesLbl, counter: usage.messages },
                { label: t.admin.documentsLbl, counter: usage.docs },
              ].map(({ label, counter }) => (
                <div key={label} style={{ borderRadius: 12, border: "1px solid var(--line)", background: "var(--paper-2)", padding: 16 }}>
                  <div className="row-between t-small" style={{ marginBottom: 8 }}>
                    <span style={{ color: "var(--ink)" }}>{label}</span>
                    <span className="num faint">
                      {counter.used}/{counter.limit}
                    </span>
                  </div>
                  <div style={{ height: 8, borderRadius: 999, background: "var(--line)", overflow: "hidden" }}>
                    <div style={{ height: "100%", borderRadius: 999, background: "var(--green)", width: `${usagePercent(counter.used, counter.limit)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="t-small faint">—</div>
          )}
        </div>

        {/* Fields */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }} className="max-md:!grid-cols-1">
          <div className="field">
            <label className="field-label">{S.name}</label>
            <input type="text" className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="field">
            <label className="field-label">{t.onboarding.fUsername}</label>
            <input type="text" className="input" value={user.username} readOnly title="Username cannot be changed" style={{ opacity: 0.6 }} />
          </div>
          <div className="field">
            <label className="field-label">{S.phone}</label>
            <input type="tel" className="input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+962 7XX XXX XXXX" />
          </div>
          <div className="field">
            <label className="field-label">{S.marital}</label>
            <select
              className="select"
              value={filingStatus}
              onChange={(e) => setFilingStatus(e.target.value as FilingStatus)}
              disabled={!currentProfile}
              style={!currentProfile ? { opacity: 0.5 } : undefined}
            >
              <option value="individual">{isAr ? "فردي" : "Individual"}</option>
              <option value="joint">{isAr ? "مشترك" : "Joint"}</option>
            </select>
          </div>
        </div>

        {errorMsg && (
          <div className="t-small" style={{ color: "var(--danger)", background: "var(--clay-tint)", borderRadius: 10, padding: "10px 14px" }}>
            {errorMsg}
          </div>
        )}
        {toast && (
          <div className="t-small" style={{ color: "var(--positive)", background: "var(--green-tint)", borderRadius: 10, padding: "10px 14px" }}>
            {toast}
          </div>
        )}

        <div className="row" style={{ justifyContent: "flex-end" }}>
          <Button type="submit" variant="primary" disabled={saving}>
            {saving ? t.common.loading : S.save}
          </Button>
        </div>
      </div>
    </form>
  );
}

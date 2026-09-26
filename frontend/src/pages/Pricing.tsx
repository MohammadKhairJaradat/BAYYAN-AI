import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLang } from "../contexts/hooks";
import { Icon, Button } from "../components/brand";
import { getPublicCapabilities } from "../services/api";
import type { PublicCapabilities, SubscriptionTier } from "../types/api";

const PLAN_COPY: Record<SubscriptionTier, { ar: string; en: string }> = {
  Basic: { ar: "الأساسية", en: "Basic" },
  Pro: { ar: "برو", en: "Pro" },
  Premium: { ar: "بريميوم", en: "Premium" },
};

export default function Pricing() {
  const { t, dir } = useLang();
  const navigate = useNavigate();
  const isAr = dir === "rtl";
  const [capabilities, setCapabilities] = useState<PublicCapabilities | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let active = true;
    getPublicCapabilities()
      .then((result) => {
        if (active) setCapabilities(result);
      })
      .catch(() => {
        if (active) setLoadError(true);
      });
    return () => { active = false; };
  }, []);

  return (
    <div className="wrap" style={{ paddingBlock: "72px 96px" }}>
      <div className="center" style={{ maxWidth: 660, marginInline: "auto", marginBottom: 48 }}>
        <div className="t-eyebrow" style={{ marginBottom: 12 }}>{t.nav.pricing}</div>
        <h1 className="display t-h1" style={{ marginBottom: 14 }}>
          {isAr ? "مستويات الوصول في بيان" : "BAYYAN access levels"}
        </h1>
        <p className="t-lead">
          {isAr
            ? "الحساب الضريبي الحتمي متاح لكل حساب. حدود المحادثة والمستندات أدناه تأتي مباشرة من إعدادات الخادم؛ تغيير المستوى يتم بواسطة مسؤول النظام. لا توجد عملية دفع داخل التطبيق."
            : "Deterministic tax calculation is available to every account. Chat and document limits below come from the server; an administrator changes access levels. There is no in-app payment flow."}
        </p>
      </div>

      {loadError && (
        <p role="alert" className="card card-pad center" style={{ maxWidth: 620, marginInline: "auto" }}>
          {isAr ? "تعذر تحميل حدود المستويات من الخادم. جرّب مرة أخرى بعد تشغيل الباكند." : "Could not load access limits from the server. Try again when the backend is available."}
        </p>
      )}
      {!loadError && !capabilities && (
        <p role="status" className="center t-body">
          {isAr ? "جارٍ تحميل الحدود…" : "Loading access limits…"}
        </p>
      )}

      {capabilities && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 20, alignItems: "start", maxWidth: 1040, marginInline: "auto" }} className="max-md:!grid-cols-1">
          {capabilities.tiers.map((tier) => {
            const popular = tier.name === "Pro";
            const features = [
              isAr ? `${tier.max_messages_per_month} رسالة محادثة شهريًا` : `${tier.max_messages_per_month} chat messages / month`,
              tier.max_docs_per_month === 0
                ? (isAr ? "رفع المستندات غير متاح" : "Document uploads unavailable")
                : (isAr ? `${tier.max_docs_per_month} مستندًا شهريًا` : `${tier.max_docs_per_month} documents / month`),
              isAr ? `${tier.max_extractions_per_month} معالجة مستند شهريًا` : `${tier.max_extractions_per_month} document extractions / month`,
              isAr ? `${tier.max_advisor_runs_per_month} تشغيل مستشار شهريًا` : `${tier.max_advisor_runs_per_month} advisor runs / month`,
              isAr ? `${tier.max_voice_clips_per_month} مقطع صوتي شهريًا` : `${tier.max_voice_clips_per_month} voice clips / month`,
              isAr ? "حساب ضريبي حتمي من بياناتك المحفوظة" : "Deterministic tax estimate from your saved data",
              isAr
                ? `${tier.allowed_models.length} خيارات محادثة عند تهيئة مزوديها`
                : `${tier.allowed_models.length} chat model choices when providers are configured`,
            ];
            return (
              <div
                key={tier.name}
                className="card card-pad"
                style={{ position: "relative", borderColor: popular ? "var(--green)" : "var(--line)", boxShadow: popular ? "var(--shadow-glow)" : "var(--shadow-sm)" }}
              >
                <h2 className="t-h3" style={{ marginBottom: 8 }}>
                  {PLAN_COPY[tier.name][isAr ? "ar" : "en"]}
                </h2>
                <p className="t-small" style={{ marginBottom: 18 }}>
                  {tier.name === "Basic"
                    ? (isAr ? "المستوى الافتراضي للحساب الجديد." : "Default level for a new account.")
                    : (isAr ? "يحدده مسؤول النظام للحسابات الفردية." : "Assigned by an administrator for individual accounts.")}
                </p>
                {tier.name === "Basic" ? (
                  <Button variant="primary" style={{ width: "100%", marginBottom: 20 }} onClick={() => navigate("/register")}>
                    {isAr ? "أنشئ حسابًا" : "Create an account"}
                  </Button>
                ) : (
                  <p className="chip" style={{ marginBottom: 20 }}>
                    {isAr ? "لا يوجد اشتراك ذاتي حاليًا" : "No self-service upgrade"}
                  </p>
                )}
                <ul className="stack" style={{ ["--gap"]: "10px", listStyle: "none", margin: 0, padding: 0 } as React.CSSProperties}>
                  {features.map((feature) => (
                    <li key={feature} className="row" style={{ gap: 9, alignItems: "flex-start" }}>
                      <Icon name="check" size={16} stroke={2.5} color="var(--green)" style={{ marginTop: 2, flex: "none" }} />
                      <span className="t-small" style={{ color: "var(--ink)" }}>{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}

      <p className="center t-small" style={{ marginTop: 36, maxWidth: 720, marginInline: "auto" }}>
        {isAr
          ? "المعرفة القانونية المرفقة حاليًا تجريبية، ولا يقدّم بيان إقرارًا رسميًا لدائرة ضريبة الدخل. راجع الأرقام والمصادر مع مختص قبل الاعتماد عليها."
          : "The bundled legal knowledge base is a demo. BAYYAN does not submit official tax returns. Review figures and sources with a qualified professional before relying on them."}
      </p>
    </div>
  );
}

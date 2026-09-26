import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { useLang } from "../../contexts/hooks";
import marketingTaxExample from "../../data/marketing-tax-example.json";
import { useTheme } from "../../contexts/hooks";
import { Mark, Icon, Button, Tatreez, SevenStar, MosaicBand, type IconName } from "../brand";

function scrollToId(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  const top = el.getBoundingClientRect().top + window.scrollY - 76;
  window.scrollTo({ top, behavior: "smooth" });
}

function SectionHead({
  eyebrow,
  title,
  sub,
  center = true,
}: {
  eyebrow: string;
  title: string;
  sub?: string;
  center?: boolean;
}) {
  return (
    <div
      className={center ? "center" : ""}
      style={{ maxWidth: center ? 680 : "none", marginInline: center ? "auto" : 0, marginBottom: 44 }}
    >
      <div className="t-eyebrow" style={{ marginBottom: 12 }}>
        {eyebrow}
      </div>
      <h2 className="display t-h2" style={{ marginBottom: 14, color: "var(--ink)" }}>
        {title}
      </h2>
      {sub && <p className="t-lead">{sub}</p>}
    </div>
  );
}

function HeroStatement() {
  const { dir } = useLang();
  const isAr = dir === "rtl";
  const stats = [
    { l: isAr ? "إجمالي الدخل" : "Gross income", v: isAr ? "١٨٬٠٠٠" : "18,000" },
    { l: isAr ? "الإعفاءات" : "Exemptions", v: isAr ? "١٠٬٠٠٠" : "10,000" },
    { l: isAr ? "النفقات المؤهلة" : "Eligible expenses", v: isAr ? "٢٬٤٠٠" : "2,400" },
    { l: isAr ? "النسبة الفعلية" : "Effective rate", v: isAr ? "٤٫٢٪" : "4.2%" },
  ];
  return (
    <div
      className="card fade-up"
      style={{
        borderRadius: 22,
        padding: 24,
        boxShadow: "var(--shadow-lg)",
        maxWidth: 440,
        marginInline: "auto",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <Tatreez scale={34} opacity={0.4} />
      <div style={{ position: "relative" }}>
        <div className="row-between" style={{ marginBottom: 18 }}>
          <div className="row" style={{ gap: 9 }}>
            <Mark size={26} />
            <span className="display" style={{ fontSize: 16, fontWeight: 600 }}>
              {isAr ? "البيان الضريبي ٢٠٢٥" : "Tax Statement · 2025"}
            </span>
          </div>
          <span className="chip chip-green">
            <Icon name="check" size={13} stroke={3} />
            {isAr ? "متوافق" : "Compliant"}
          </span>
        </div>

        <div style={{ marginBottom: 6 }} className="t-eyebrow">
          {isAr ? "استرداد متوقّع" : "Estimated refund"}
        </div>
        <div className="num" style={{ fontSize: 46, fontWeight: 600, color: "var(--green)", lineHeight: 1 }}>
          {isAr ? "١٬٢٤٠" : "1,240"}{" "}
          <span style={{ fontSize: 18, color: "var(--ink-soft)", fontWeight: 500 }}>{isAr ? "د.أ" : "JD"}</span>
        </div>
        <div className="t-small" style={{ marginTop: 8 }}>
          {isAr ? "إجمالي الالتزام ٢٬٠١٠ د.أ · المقتطع ٣٬٢٥٠ د.أ" : "Gross liability 2,010 JD · withheld 3,250 JD"}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 18 }}>
          {stats.map((s, i) => (
            <div key={i} style={{ background: "var(--paper-2)", border: "1px solid var(--line)", borderRadius: 12, padding: "11px 13px" }}>
              <div className="t-eyebrow" style={{ color: "var(--ink-faint)", fontSize: 10.5, marginBottom: 3 }}>
                {s.l}
              </div>
              <div className="num" style={{ fontSize: 18, fontWeight: 600 }}>
                {s.v}
              </div>
            </div>
          ))}
        </div>

        <div className="row" style={{ gap: 9, marginTop: 16, padding: "11px 13px", background: "var(--green-tint)", borderRadius: 12 }}>
          <Icon name="scale" size={17} color="var(--green)" />
          <span className="t-small" style={{ color: "var(--green)", fontWeight: 500 }}>
            {isAr ? "قواعد الحساب الحالية تشير إلى المادة ٩ · مثال تجريبي" : "Current calculation rules reference Article 9 · demo example"}
          </span>
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  const { t, dir } = useLang();
  const { theme } = useTheme();
  const navigate = useNavigate();
  const L = t.landing;
  const isAr = dir === "rtl";
  const accent = theme === "dark" ? "#BE9442" : "#B23A2E";

  const proofs: [string, string][] = [
    [L.proof1Num, L.proof1Lab],
    [L.proof2Num, L.proof2Lab],
    [L.proof3Num, L.proof3Lab],
    [L.proof4Num, L.proof4Lab],
  ];
  const smallFeatures: [IconName, string, string][] = [
    ["search", L.f3Title, L.f3Body],
    ["chart", L.f4Title, L.f4Body],
    ["shield", L.f5Title, L.f5Body],
  ];
  const docCards: { tag: string; c: string; r: number }[] = [
    { tag: isAr ? "كشف راتب" : "Salary slip", c: "green", r: -4 },
    { tag: isAr ? "تم التحقق" : "Verified", c: "gold", r: 3 },
    { tag: isAr ? "إيصال" : "Receipt", c: "clay", r: -2 },
  ];
  const security: [IconName, number][] = [
    ["lock", 0],
    ["shield", 1],
    ["doc", 2],
    ["refresh", 3],
  ];
  const audience: [IconName, number][] = [
    ["briefcase", 0],
    ["bolt", 1],
    ["building", 2],
  ];

  return (
    <main>
      {/* ===== HERO ===== */}
      <section className="sun-wash" style={{ position: "relative", overflow: "hidden", paddingBlock: "92px 80px" }}>
        <Tatreez scale={36} opacity={0.5} fade />
        <div className="wrap" style={{ position: "relative" }}>
          <div
            style={{ display: "grid", gridTemplateColumns: "minmax(0,1.05fr) minmax(0,.95fr)", gap: 56, alignItems: "center" }}
            className="max-md:!grid-cols-1"
          >
            <div className="fade-up">
              <div className="pill pill-green" style={{ marginBottom: 24 }}>
                <SevenStar size={14} color={accent} /> {L.badge}
              </div>
              <h1 className="display t-display" style={{ color: "var(--ink)", marginBottom: 22 }}>
                {L.heroLine1}
                <br />
                <span style={{ color: "var(--green)", position: "relative" }}>
                  {L.heroLine2}
                  <svg
                    viewBox="0 0 300 12"
                    preserveAspectRatio="none"
                    style={{ position: "absolute", insetInlineStart: 0, bottom: -8, width: "100%", height: 11 }}
                    aria-hidden="true"
                  >
                    <path d="M2 8 Q 75 2 150 7 T 298 6" stroke="var(--gold)" strokeWidth="3" fill="none" strokeLinecap="round" opacity="0.8" />
                  </svg>
                </span>
              </h1>
              <p className="t-lead" style={{ maxWidth: 520, marginBottom: 32 }}>
                {L.heroSub}
              </p>
              <div className="row" style={{ gap: 13, flexWrap: "wrap" }}>
                <Button variant="primary" size="lg" iconRight="arrow" onClick={() => navigate("/register")}>
                  {L.ctaPrimary}
                </Button>
                <Button variant="ghost" size="lg" icon="eye" onClick={() => scrollToId("how")}>
                  {L.ctaSecondary}
                </Button>
              </div>
              <div className="row" style={{ gap: 9, marginTop: 24 }}>
                <Icon name="shield" size={16} color="var(--green)" />
                <span className="t-small">{L.trustNote}</span>
              </div>
            </div>
            <HeroStatement />
          </div>
        </div>
      </section>

      {/* ===== PROOF STRIP ===== */}
      <section style={{ borderBlock: "1px solid var(--line)", background: "var(--paper)" }}>
        <div className="wrap" style={{ paddingBlock: 30 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)" }} className="max-md:!grid-cols-2 max-md:gap-6">
            {proofs.map((p, i) => (
              <div key={i} style={{ textAlign: "center", paddingInline: 14, borderInlineStart: i ? "1px solid var(--line)" : "none" }}>
                <div className="num" style={{ fontSize: 26, fontWeight: 600, color: "var(--green)", marginBottom: 5 }}>
                  {p[0]}
                </div>
                <div className="t-small faint" style={{ lineHeight: 1.4 }}>
                  {p[1]}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== FEATURES ===== */}
      <section id="features" className="wrap" style={{ paddingBlock: 88 }}>
        <SectionHead eyebrow={L.featuresEyebrow} title={L.featuresTitle} sub={L.featuresSub} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 20 }} className="max-md:!grid-cols-1">
          {/* Big card 1 — documents */}
          <div className="card card-hover" style={{ overflow: "hidden" }}>
            <div
              style={{
                height: 196,
                background: "var(--paper-2)",
                position: "relative",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderBottom: "1px solid var(--line)",
              }}
            >
              <Tatreez scale={26} opacity={0.4} />
              <div className="row" style={{ gap: 14, position: "relative" }}>
                {docCards.map((d, i) => (
                  <div key={i} className="card" style={{ width: 92, height: 122, padding: 11, transform: `rotate(${d.r}deg)`, boxShadow: "var(--shadow-md)" }}>
                    <div style={{ height: 6, width: "70%", background: "var(--line-strong)", borderRadius: 3, marginBottom: 7 }} />
                    <div style={{ height: 6, width: "100%", background: "var(--line)", borderRadius: 3, marginBottom: 7 }} />
                    <div style={{ height: 6, width: "55%", background: "var(--line)", borderRadius: 3, marginBottom: 16 }} />
                    <div className={`chip chip-${d.c}`} style={{ fontSize: 10, padding: "3px 7px" }}>
                      {d.tag}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div className="card-pad">
              <span className="chip chip-green" style={{ marginBottom: 12 }}>
                <Icon name="eye" size={13} />
                {L.f1Tag}
              </span>
              <h3 className="t-h3" style={{ margin: "4px 0 8px" }}>
                {L.f1Title}
              </h3>
              <p className="t-body">{L.f1Body}</p>
            </div>
          </div>
          {/* Big card 2 — advisor */}
          <div className="card card-hover" style={{ overflow: "hidden" }}>
            <div
              style={{
                height: 196,
                background: "var(--paper-2)",
                position: "relative",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderBottom: "1px solid var(--line)",
                padding: 22,
              }}
            >
              <Tatreez scale={26} opacity={0.4} />
              <div className="stack" style={{ ["--gap"]: "10px", position: "relative", width: "100%", maxWidth: 320 } as CSSProperties}>
                <div style={{ alignSelf: "flex-start", maxWidth: "85%", background: "var(--green-tint)", border: "1px solid var(--green-tint2)", borderRadius: "14px 14px 14px 4px", padding: "10px 13px" }}>
                  <p className="t-small" style={{ color: "var(--green)" }}>
                    {isAr ? "ما حالتك الاجتماعية وعدد المعالين؟" : "What's your marital status and dependents?"}
                  </p>
                </div>
                <div style={{ alignSelf: "flex-end", maxWidth: "85%", background: "var(--paper)", border: "1px solid var(--line)", borderRadius: "14px 14px 4px 14px", padding: "10px 13px" }}>
                  <p className="t-small">{isAr ? "متزوّج وطفلان" : "Married, two children"}</p>
                </div>
                <div style={{ alignSelf: "flex-start", maxWidth: "90%", background: "var(--green-tint)", border: "1px solid var(--green-tint2)", borderRadius: "14px 14px 14px 4px", padding: "10px 13px" }}>
                  <p className="t-small" style={{ color: "var(--green)" }}>
                    {isAr
                      ? `مثال تجريبي لمتزوّج ومعالَيْن ومصاريف طبية ${new Intl.NumberFormat("ar-JO").format(marketingTaxExample.inputs.deductions.medical)} د.أ: الإعفاء العائلي المحسوب ${new Intl.NumberFormat("ar-JO").format(marketingTaxExample.expected.family_exemption)} د.أ.`
                      : `Demo: married with two dependents and ${marketingTaxExample.inputs.deductions.medical.toLocaleString("en-US")} JD medical expenses. Calculated family exemption: ${marketingTaxExample.expected.family_exemption.toLocaleString("en-US")} JD.`}
                  </p>
                </div>
              </div>
            </div>
            <div className="card-pad">
              <span className="chip chip-clay" style={{ marginBottom: 12 }}>
                <Icon name="scale" size={13} />
                {L.f2Tag}
              </span>
              <h3 className="t-h3" style={{ margin: "4px 0 8px" }}>
                {L.f2Title}
              </h3>
              <p className="t-body">{L.f2Body}</p>
            </div>
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 20 }} className="max-md:!grid-cols-1">
          {smallFeatures.map((f, i) => (
            <div key={i} className="card card-hover card-pad">
              <div style={{ width: 46, height: 46, borderRadius: 12, background: "var(--green-tint)", display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
                <Icon name={f[0]} size={22} color="var(--green)" />
              </div>
              <h3 className="t-h3" style={{ fontSize: 18, marginBottom: 8 }}>
                {f[1]}
              </h3>
              <p className="t-body" style={{ fontSize: 14.5 }}>
                {f[2]}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ===== HOW IT WORKS — pipeline ===== */}
      <section id="how" style={{ background: "var(--sand-deep)", borderBlock: "1px solid var(--line)" }}>
        <div className="wrap" style={{ paddingBlock: 88 }}>
          <SectionHead eyebrow={L.howEyebrow} title={L.howTitle} sub={L.howSub} />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 18 }} className="max-md:!grid-cols-1">
            {L.steps.map((s, i) => (
              <div key={i} className="card card-pad" style={{ position: "relative" }}>
                <div className="row-between" style={{ marginBottom: 14 }}>
                  <span className="num display" style={{ fontSize: 30, fontWeight: 600, color: "var(--gold)" }}>
                    {isAr ? ["١", "٢", "٣", "٤", "٥", "٦"][i] : "0" + (i + 1)}
                  </span>
                  <span style={{ width: 10, height: 10, borderRadius: 2, transform: "rotate(45deg)", background: i < 2 ? "var(--green)" : i < 4 ? "var(--gold)" : "var(--clay)" }} />
                </div>
                <h3 className="t-h3" style={{ fontSize: 18, marginBottom: 7 }}>
                  {s.t}
                </h3>
                <p className="t-body" style={{ fontSize: 14.5 }}>
                  {s.d}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== SECURITY ===== */}
      <section id="security" className="wrap" style={{ paddingBlock: 88 }}>
        <SectionHead eyebrow={L.secEyebrow} title={L.secTitle} sub={L.secSub} />
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 18 }} className="max-md:!grid-cols-2">
          {security.map(([ic, idx]) => (
            <div key={idx} className="card card-pad center">
              <div style={{ width: 48, height: 48, borderRadius: 14, background: "var(--gold-tint)", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px" }}>
                <Icon name={ic} size={22} color="var(--gold)" />
              </div>
              <h4 className="t-h3" style={{ fontSize: 16.5, marginBottom: 7 }}>
                {L.sec[idx].t}
              </h4>
              <p className="t-small">{L.sec[idx].d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ===== AUDIENCE ===== */}
      <section style={{ background: "var(--sand-deep)", borderBlock: "1px solid var(--line)" }}>
        <div className="wrap" style={{ paddingBlock: 88 }}>
          <SectionHead eyebrow={L.audienceEyebrow} title={L.audienceTitle} />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 20 }} className="max-md:!grid-cols-1">
            {audience.map(([ic, idx]) => (
              <div key={idx} className="card card-hover card-pad">
                <Icon name={ic} size={26} color="var(--clay)" style={{ marginBottom: 16 }} />
                <h3 className="t-h3" style={{ fontSize: 19, marginBottom: 8 }}>
                  {L.aud[idx].t}
                </h3>
                <p className="t-body" style={{ fontSize: 14.5 }}>
                  {L.aud[idx].d}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== CTA ===== */}
      <section className="wrap" style={{ paddingBlock: 96 }}>
        <div
          className="card"
          style={{ position: "relative", overflow: "hidden", borderRadius: 26, padding: "64px 32px", textAlign: "center", background: "var(--green)", borderColor: "var(--green-deep)" }}
        >
          <Tatreez scale={30} opacity={0.55} tone="rgba(255,252,245,.5)" />
          <div style={{ position: "relative" }}>
            <MosaicBand onDark style={{ marginBottom: 26 }} />
            <h2 className="display t-h1" style={{ color: "#FFFCF5", marginBottom: 14 }}>
              {L.ctaTitle}
            </h2>
            <p className="t-lead" style={{ color: "rgba(255,252,245,.85)", maxWidth: 480, margin: "0 auto 30px" }}>
              {L.ctaSub}
            </p>
            <button className="btn btn-lg" style={{ background: "#FFFCF5", color: "var(--green-deep)" }} onClick={() => navigate("/register")}>
              {L.ctaButton}
              <Icon name="arrow" size={18} className="i-arrow" />
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}

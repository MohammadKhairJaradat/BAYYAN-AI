import { Link } from "react-router-dom";
import { useLang } from "../contexts/hooks";
import { Button } from "../components/brand";

export default function About() {
  const { t, dir } = useLang();
  const isAr = dir === "rtl";

  const cards = isAr
    ? [
        { t: "هدفنا", d: "مساعدة الأفراد في الأردن على تنظيم بياناتهم الضريبية وفهم تقدير ضريبتهم. بيان أداة تحضير ومراجعة، ولا يقدّم إقرارًا رسميًا." },
        { t: "الحساب والمصادر", d: "المبالغ تُحسب في محرك Python الحتمي. المحادثة قد تعرض شروحًا ومصادر، لكن قاعدة المعرفة المرفقة تجريبية وتحتاج الرجوع إلى المصدر الرسمي." },
        { t: "البيانات والذكاء الاصطناعي", d: "المستندات الخاصة تُطلب عبر مسارات مرتبطة بحسابك. عند استخدام المحادثة أو الصوت أو الاستخراج قد تُرسل بيانات إلى مزود ذكاء اصطناعي خارجي مهيأ للخدمة." },
        { t: "أصل العمل", d: "بدأ بيان مشروع تخرّج أنجزه فريق طلابي. نحافظ على مساهماتهم وهويته العربية والأردنية؛ تفاصيل النسبة والأصول تُراجع مع الفريق قبل النشر العام." },
      ]
    : [
        { t: "Our purpose", d: "Help individuals in Jordan organize tax information and understand a calculated estimate. BAYYAN supports preparation and review; it does not submit official returns." },
        { t: "Calculations and sources", d: "Tax amounts come from the deterministic Python engine. Chat may show explanations and sources, but the bundled legal knowledge base is a demo and must be checked against official sources." },
        { t: "Data and AI", d: "Private documents are retrieved through account-scoped routes. Using chat, voice or extraction may send content to configured external AI providers." },
        { t: "Project origins", d: "BAYYAN began as a team graduation project. This edition preserves the team's contributions and Jordanian Arabic identity; credits and asset rights will be reviewed with the team before public release." },
      ];

  return (
    <div className="wrap" style={{ maxWidth: 960, paddingBlock: "72px 96px" }}>
      <div className="t-eyebrow" style={{ marginBottom: 12 }}>
        {t.nav.about} · {t.brand}
      </div>
      <h1 className="display t-h1" style={{ marginBottom: 16 }}>
        {isAr ? "وضوح ضريبي للأردن" : "Tax clarity, built for Jordan"}
      </h1>
      <p className="t-lead" style={{ maxWidth: 620, marginBottom: 48 }}>
        {t.landing.heroSub}
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginBottom: 56 }} className="max-md:!grid-cols-1">
        {cards.map((c) => (
          <div key={c.t} className="card card-pad">
            <h3 className="t-h3" style={{ marginBottom: 10 }}>
              {c.t}
            </h3>
            <p className="t-body">{c.d}</p>
          </div>
        ))}
      </div>

      <div className="center">
        <h2 className="display t-h2" style={{ marginBottom: 18 }}>
          {t.landing.ctaTitle}
        </h2>
        <Link to="/pricing">
          <Button variant="primary" size="lg" iconRight="arrow">
            {t.nav.pricing}
          </Button>
        </Link>
      </div>
    </div>
  );
}

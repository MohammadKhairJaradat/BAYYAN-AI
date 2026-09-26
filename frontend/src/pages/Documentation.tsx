import { Link } from "react-router-dom";
import { useLang } from "../contexts/hooks";
import { Icon, Button } from "../components/brand";

export default function Documentation() {
  const { t, dir } = useLang();
  const isAr = dir === "rtl";

  const sections = isAr
    ? [
        { title: "البداية", items: [
          { name: "أنشئ حساباً", desc: "سجّل وجهّز ملفّك الضريبي بمعلومات أساسية." },
          { name: "ارفع المستندات", desc: "إذا سمح مستوى حسابك، ارفع الإيصالات وكشوف الرواتب للمعالجة والمراجعة." },
          { name: "ابدأ محادثة", desc: "اسأل «بيان» عن بياناتك وتقديرك، وراجع الإجابات قبل الاعتماد عليها." },
        ]},
        { title: "دليل المزايا", items: [
          { name: "معالجة المستندات", desc: "الاستخراج الآلي يقترح بيانات؛ تحقّق منها على الأصل، فقد يخطئ." },
          { name: "مراجعة الخصومات", desc: "أدخل نفقاتك وراجع أثرها في الحساب الحتمي وفق القواعد الحالية." },
          { name: "سيناريوهات المستشار", desc: "مقارنات توضيحية داخل تحليل المستشار، وليست ملفّات مستقلة محفوظة." },
          { name: "مراجعة النواقص", desc: "قد يعرض المستشار نواقص ومقترحات، لا شهادة امتثال أو تدقيق." },
        ]},
        { title: "حدود النسخة التجريبية", items: [
          { name: "المصادر القانونية", desc: "قاعدة المعرفة المرفقة تجريبية وليست منشورات رسمية معتمدة." },
          { name: "قواعد السنة", desc: "المحرك الحالي لا يختار قواعد مختلفة تلقائيًا حسب السنة الضريبية." },
          { name: "تقديم الإقرار", desc: "لا يتصل بيان بدائرة ضريبة الدخل لتقديم إقرار رسمي." },
          { name: "الخدمات الخارجية", desc: "المحادثة والصوت والاستخراج قد تستخدم مزودي ذكاء اصطناعي خارجيين." },
        ]},
      ]
    : [
        { title: "Getting started", items: [
          { name: "Create an account", desc: "Sign up and set up your tax profile with basic information." },
          { name: "Upload documents", desc: "If your account level allows uploads, add receipts and salary slips for processing and review." },
          { name: "Start a conversation", desc: "Ask Bayyan about your saved data and estimate; review answers before relying on them." },
        ]},
        { title: "Features guide", items: [
          { name: "Document processing", desc: "AI extraction suggests data; check the original document because it can be wrong." },
          { name: "Deduction review", desc: "Enter expenses and review their effect under the current deterministic rules." },
          { name: "Advisor scenarios", desc: "Illustrative comparisons in an advisor report, not independently saved scenarios." },
          { name: "Review gaps", desc: "The advisor may suggest gaps; it does not certify compliance or perform an audit." },
        ]},
        { title: "Demo limitations", items: [
          { name: "Legal sources", desc: "The bundled knowledge-base files are demo fixtures, not approved official publications." },
          { name: "Year-specific rules", desc: "The current engine does not automatically select a different ruleset by tax year." },
          { name: "Official submission", desc: "BAYYAN does not connect to the ISTD to submit a tax return." },
          { name: "External services", desc: "Chat, voice and extraction may use configured external AI providers." },
        ]},
      ];

  return (
    <div className="wrap" style={{ maxWidth: 920, paddingBlock: "72px 96px" }}>
      <div className="t-eyebrow" style={{ marginBottom: 12 }}>
        {t.nav.docs}
      </div>
      <h1 className="display t-h1" style={{ marginBottom: 16 }}>
        {isAr ? "كل ما تحتاج معرفته" : "Everything you need to know"}
      </h1>
      <p className="t-lead" style={{ maxWidth: 600, marginBottom: 48 }}>
        {isAr
          ? "ابدأ بملفك الضريبي وتعرّف حدود هذه النسخة."
          : "Get started with your tax profile and understand this edition's limits."}
      </p>

      <div className="stack" style={{ ["--gap"]: "48px" } as React.CSSProperties}>
        {sections.map((section) => (
          <div key={section.title}>
            <h2 className="display t-h3" style={{ fontSize: 22, marginBottom: 18 }}>
              {section.title}
            </h2>
            <div className="stack" style={{ ["--gap"]: "12px" } as React.CSSProperties}>
              {section.items.map((item) => (
                <div key={item.name} className="card card-hover card-pad row" style={{ gap: 14, alignItems: "flex-start" }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: "var(--green-tint)", display: "grid", placeItems: "center", flex: "none" }}>
                    <Icon name="doc" size={18} color="var(--green)" />
                  </div>
                  <div>
                    <h3 className="t-h3" style={{ fontSize: 16, marginBottom: 4 }}>
                      {item.name}
                    </h3>
                    <p className="t-small">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="card card-pad center" style={{ marginTop: 48 }}>
        <h3 className="t-h3" style={{ marginBottom: 8 }}>
          {isAr ? "عن المشروع" : "About the project"}
        </h3>
        <p className="t-small" style={{ marginBottom: 18 }}>
          {isAr ? "اقرأ هدف بيان وأصل العمل." : "Read about BAYYAN's purpose and origins."}
        </p>
        <Link to="/about">
          <Button variant="ghost">{t.nav.about}</Button>
        </Link>
      </div>
    </div>
  );
}

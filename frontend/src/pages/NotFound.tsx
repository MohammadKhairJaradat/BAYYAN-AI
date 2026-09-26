import { Link } from "react-router-dom";
import { useLang } from "../contexts/hooks";

export default function NotFound() {
  const { lang } = useLang();
  const isAr = lang === "ar";
  return (
    <main className="wrap" style={{ minHeight: "55vh", display: "grid", placeItems: "center", textAlign: "center", paddingBlock: 64 }}>
      <div>
        <p style={{ color: "var(--clay)", fontWeight: 700, marginBottom: 10 }}>404</p>
        <h1 className="display t-h2">{isAr ? "الصفحة غير موجودة" : "Page not found"}</h1>
        <p className="t-body" style={{ marginBlock: 12, maxWidth: 420 }}>
          {isAr ? "قد يكون الرابط تغير. يمكنك العودة إلى بداية بيان." : "This link may have changed. Return to the BAYYAN home page."}
        </p>
        <Link className="btn btn-primary" to="/">{isAr ? "العودة للرئيسية" : "Back to home"}</Link>
      </div>
    </main>
  );
}

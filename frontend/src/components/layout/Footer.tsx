import { Link } from "react-router-dom";
import { useLang } from "../../contexts/hooks";
import { Logo, MosaicBand } from "../brand";

export default function Footer() {
  const { t } = useLang();
  const L = t.landing;

  const columns: { heading: string; links: [string, string][] }[] = [
    {
      heading: L.footerProduct,
      links: [
        ["/pricing", t.nav.pricing],
        ["/docs", t.nav.docs],
        ["/#security", t.nav.security],
      ],
    },
    {
      heading: L.footerCompany,
      links: [
        ["/about", t.nav.about],
        ["/docs", t.nav.docs],
      ],
    },
    {
      heading: L.footerLegal,
      links: [
        ["/about", t.nav.about],
        ["/docs", t.nav.docs],
      ],
    },
  ];

  return (
    <footer style={{ background: "var(--sand-deep)", borderTop: "1px solid var(--line)" }}>
      <div className="wrap" style={{ paddingBlock: 56 }}>
        <MosaicBand count={13} style={{ marginBottom: 40 }} />
        <div
          style={{
            display: "grid",
            gap: 40,
            gridTemplateColumns: "1.6fr 1fr 1fr 1fr",
            alignItems: "start",
          }}
          className="max-md:!grid-cols-2"
        >
          <div>
            <Link to="/" aria-label={t.brand}>
              <Logo size="md" />
            </Link>
            <p className="t-small" style={{ marginTop: 14, maxWidth: 280 }}>
              {L.footerTagline}
            </p>
          </div>
          {columns.map((col) => (
            <div key={col.heading}>
              <h5 style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", marginBottom: 14 }}>
                {col.heading}
              </h5>
              <ul className="stack" style={{ ["--gap" as string]: "10px", listStyle: "none", padding: 0, margin: 0 }}>
                {col.links.map(([to, label], i) => (
                  <li key={`${to}-${i}`}>
                    <Link to={to} className="t-small" style={{ color: "var(--ink-soft)" }}>
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <hr className="divider" style={{ marginBlock: 32 }} />
        <p className="t-small faint" style={{ maxWidth: 720 }}>
          {L.footerNote}
        </p>
        <p className="t-small faint" style={{ marginTop: 12 }}>
          © {new Date().getFullYear()} {t.brand}.
        </p>
      </div>
    </footer>
  );
}

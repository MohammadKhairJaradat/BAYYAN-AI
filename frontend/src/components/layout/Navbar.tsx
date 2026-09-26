import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useLang } from "../../contexts/hooks";
import { Logo, Button, ChromeControls } from "../brand";

function scrollToId(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  const top = el.getBoundingClientRect().top + window.scrollY - 76;
  window.scrollTo({ top, behavior: "smooth" });
}

export default function Navbar() {
  const { t } = useLang();
  const navigate = useNavigate();
  const location = useLocation();
  const onLanding = location.pathname === "/";
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 12);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  const goAnchor = (id: string) => {
    if (onLanding) scrollToId(id);
    else navigate(`/#${id}`);
  };

  const anchors: [string, string][] = [
    ["features", t.nav.features],
    ["how", t.nav.how],
    ["security", t.nav.security],
  ];
  const routeLinks: [string, string][] = [
    ["/pricing", t.nav.pricing],
    ["/docs", t.nav.docs],
    ["/about", t.nav.about],
  ];

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 40,
        background: scrolled ? "color-mix(in srgb, var(--sand) 88%, transparent)" : "transparent",
        backdropFilter: scrolled ? "blur(12px)" : "none",
        borderBottom: scrolled ? "1px solid var(--line)" : "1px solid transparent",
        transition: "background .3s, border-color .3s",
      }}
    >
      <div className="wrap row-between" style={{ height: 68 }}>
        <Link to="/" aria-label={t.brand}>
          <Logo size="md" />
        </Link>

        <nav className="row max-md:hidden" style={{ gap: 26 }}>
          {onLanding &&
            anchors.map(([id, label]) => (
              <button
                key={id}
                onClick={() => goAnchor(id)}
                style={{
                  fontSize: 14.5,
                  fontWeight: 500,
                  background: "none",
                  border: "none",
                  color: "var(--ink-soft)",
                }}
              >
                {label}
              </button>
            ))}
          {routeLinks.map(([to, label]) => (
            <Link
              key={to}
              to={to}
              style={{ fontSize: 14.5, fontWeight: 500, color: "var(--ink-soft)" }}
            >
              {label}
            </Link>
          ))}
        </nav>

        <div className="row" style={{ gap: 10 }}>
          <ChromeControls />
          <Link
            to="/login"
            className="max-sm:hidden"
            style={{ fontSize: 14.5, fontWeight: 600, color: "var(--ink)" }}
          >
            {t.nav.signin}
          </Link>
          <Button variant="primary" size="sm" onClick={() => navigate("/register")}>
            {t.nav.start}
          </Button>
        </div>
      </div>
    </header>
  );
}

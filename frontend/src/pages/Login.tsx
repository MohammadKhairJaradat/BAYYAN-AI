import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../contexts/hooks";
import { useLang } from "../contexts/hooks";
import { Logo, Mark, Tatreez, MosaicBand } from "../components/brand";

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  const { t } = useLang();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ username, password });
      const redirectTo =
        (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || "/chat";
      navigate(redirectTo, { replace: true });
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || t.login.failed);
      } else {
        setError(t.login.failed);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const L = t.login;

  return (
    <div className="wrap" style={{ paddingBlock: "64px 96px" }}>
      <div
        className="card"
        style={{
          maxWidth: 940,
          marginInline: "auto",
          overflow: "hidden",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          padding: 0,
          boxShadow: "var(--shadow-lg)",
        }}
      >
        {/* Form side */}
        <div className="card-pad" style={{ padding: "44px 40px" }}>
          <Link to="/" aria-label={t.brand}>
            <Logo size="md" />
          </Link>
          <h1 className="display t-h2" style={{ marginTop: 28, marginBottom: 8 }}>
            {L.title}
          </h1>
          <p className="t-body" style={{ marginBottom: 28 }}>
            {L.sub}
          </p>

          <form onSubmit={handleLogin} className="stack" style={{ ["--gap"]: "18px" } as React.CSSProperties}>
            <div className="field">
              <label className="field-label" htmlFor="username">
                {L.email}
              </label>
              <input
                type="text"
                id="username"
                className="input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
                placeholder={L.emailPh}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="password">
                {L.password}
              </label>
              <input
                type="password"
                id="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="t-small" style={{ color: "var(--danger)" }} role="alert">
                {error}
              </p>
            )}

            <button type="submit" disabled={submitting} className="btn btn-primary" style={{ width: "100%" }}>
              {submitting ? L.submitting : L.button}
            </button>
          </form>

          <p className="t-small" style={{ marginTop: 24 }}>
            {L.noAccount}{" "}
            <Link to="/register" className="green" style={{ fontWeight: 600 }}>
              {L.createOne}
            </Link>
          </p>
        </div>

        {/* Heritage aside */}
        <div
          style={{
            position: "relative",
            overflow: "hidden",
            background: "var(--green)",
            color: "#FFFCF5",
            padding: "44px 40px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
          className="max-md:hidden"
        >
          <Tatreez scale={30} opacity={0.5} tone="rgba(255,252,245,.5)" />
          <div style={{ position: "relative" }}>
            <Mark size={40} tone="#FFFCF5" accent="var(--gold)" />
          </div>
          <div style={{ position: "relative" }}>
            <p className="display" style={{ fontSize: 24, lineHeight: 1.4, marginBottom: 18 }}>
              {L.asideQuote}
            </p>
            <p style={{ fontSize: 14.5, color: "rgba(255,252,245,.8)" }}>{L.asideNote}</p>
          </div>
          <div style={{ position: "relative" }}>
            <MosaicBand onDark style={{ justifyContent: "flex-start" }} />
          </div>
        </div>
      </div>
    </div>
  );
}

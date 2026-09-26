import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../contexts/hooks";
import { useLang } from "../contexts/hooks";
import { Logo, Mark, Tatreez, MosaicBand } from "../components/brand";

export default function Register() {
  const navigate = useNavigate();
  const { signup } = useAuth();
  const { t } = useLang();
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const O = t.onboarding;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError(t.dir === "rtl" ? "كلمتا المرور غير متطابقتين" : "Passwords do not match");
      return;
    }

    setSubmitting(true);
    try {
      await signup({ username, password, name });
      navigate("/chat", { replace: true });
    } catch (err) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || O.failed);
      } else {
        setError(O.failed);
      }
    } finally {
      setSubmitting(false);
    }
  };

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
              {t.login.asideQuote}
            </p>
            <p style={{ fontSize: 14.5, color: "rgba(255,252,245,.8)" }}>{O.s1Sub}</p>
          </div>
          <div style={{ position: "relative" }}>
            <MosaicBand onDark style={{ justifyContent: "flex-start" }} />
          </div>
        </div>

        {/* Form side */}
        <div className="card-pad" style={{ padding: "44px 40px" }}>
          <Link to="/" aria-label={t.brand}>
            <Logo size="md" />
          </Link>
          <h1 className="display t-h2" style={{ marginTop: 28, marginBottom: 8 }}>
            {O.s1Title}
          </h1>
          <p className="t-body" style={{ marginBottom: 28 }}>
            {O.s1Sub}
          </p>

          <form onSubmit={handleSubmit} className="stack" style={{ ["--gap"]: "16px" } as React.CSSProperties}>
            <div className="field">
              <label className="field-label" htmlFor="name">
                {O.fName}
              </label>
              <input
                type="text"
                id="name"
                className="input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder={O.fNamePh}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="username">
                {O.fUsername}
              </label>
              <input
                type="text"
                id="username"
                className="input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoComplete="username"
                placeholder={O.fUsernamePh}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="password">
                {O.fPass}
              </label>
              <input
                type="password"
                id="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                placeholder={O.fPassPh}
              />
            </div>
            <div className="field">
              <label className="field-label" htmlFor="confirm_password">
                {t.dir === "rtl" ? "تأكيد كلمة المرور" : "Confirm password"}
              </label>
              <input
                type="password"
                id="confirm_password"
                className="input"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                autoComplete="new-password"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="t-small" style={{ color: "var(--danger)" }} role="alert">
                {error}
              </p>
            )}

            <button type="submit" disabled={submitting} className="btn btn-primary" style={{ width: "100%" }}>
              {submitting ? O.submitting : O.s1Title}
            </button>
          </form>

          <p className="t-small" style={{ marginTop: 22 }}>
            {O.haveAccount}{" "}
            <Link to="/login" className="green" style={{ fontWeight: 600 }}>
              {O.signIn}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

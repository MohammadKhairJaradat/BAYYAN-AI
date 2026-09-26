import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/hooks";

export default function RequireAdmin() {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: "var(--sand)" }}>
        <div className="animate-spin" style={{ width: 32, height: 32, borderRadius: 999, border: "3px solid var(--green-tint2)", borderTopColor: "var(--green)" }} />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (!user.is_admin) {
    return <Navigate to="/dashboard" replace />;
  }

  return <Outlet />;
}

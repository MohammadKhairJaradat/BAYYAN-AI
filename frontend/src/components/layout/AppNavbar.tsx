import { useState } from "react";
import { NavLink, Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../contexts/hooks";
import { useLang } from "../../contexts/hooks";
import { useDocumentProcessing } from "../../contexts/hooks";
import { UserAvatar } from "../ui/avatar";
import { Logo, Icon, ChromeControls, type IconName } from "../brand";

export default function AppNavbar() {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const { user, logout } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const { hasAnyActivity, isBulkProcessing, bulkProgress, processingIds } = useDocumentProcessing();
  const D = t.dashboard;

  const navItems: { to: string; label: string; icon: IconName }[] = [
    { to: "/dashboard", label: D.navHome, icon: "home" },
    { to: "/chat", label: D.navChat, icon: "chat" },
    { to: "/advisor", label: D.navAdvisor, icon: "chart" },
    { to: "/files", label: D.navFiles, icon: "folder" },
    { to: "/calendar", label: D.navCalendar, icon: "calendar" },
  ];
  if (user?.is_admin) navItems.push({ to: "/admin", label: D.navAdmin, icon: "users" });

  const handleLogout = async () => {
    setIsDropdownOpen(false);
    try {
      await logout();
      navigate("/login");
    } catch {
      window.alert("Could not sign out. Please try again.");
    }
  };

  return (
    <header
      style={{
        position: "sticky",
        top: 0,
        zIndex: 40,
        background: "color-mix(in srgb, var(--sand) 90%, transparent)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--line)",
      }}
    >
      <div className="wrap wrap-app row-between" style={{ height: 64 }}>
        <div className="row" style={{ gap: 28 }}>
          <Link to="/dashboard" aria-label={t.brand}>
            <Logo size="sm" />
          </Link>
          <nav className="row max-md:hidden" style={{ gap: 4 }}>
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                title={item.label}
                className="row"
                style={({ isActive }) => ({
                  gap: 8,
                  padding: "8px 13px",
                  borderRadius: 10,
                  fontSize: 14,
                  fontWeight: 600,
                  background: isActive ? "var(--green-tint)" : "transparent",
                  color: isActive ? "var(--green)" : "var(--ink-soft)",
                })}
              >
                <Icon name={item.icon} size={17} />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className="row" style={{ gap: 10 }}>
          {hasAnyActivity && (
            <Link
              to="/files"
              className="chip chip-gold max-md:hidden"
              title={t.files.processing}
              style={{ textDecoration: "none" }}
            >
              <Icon name="refresh" size={14} />
              {isBulkProcessing && bulkProgress
                ? `${Math.min(bulkProgress.completed + 1, bulkProgress.total)} / ${bulkProgress.total}`
                : `${processingIds.size}`}
            </Link>
          )}

          <ChromeControls />

          <Link
            to="/notifications"
            title={D.attention}
            style={{
              width: 40,
              height: 40,
              borderRadius: 11,
              border: "1px solid var(--line)",
              background: "var(--paper)",
              display: "grid",
              placeItems: "center",
            }}
          >
            <Icon name="bell" size={18} color="var(--ink-soft)" />
          </Link>

          <div className="relative">
            <button
              className="focus:outline-none"
              onClick={() => setIsDropdownOpen((v) => !v)}
              aria-label="Open account menu"
              style={{ width: 40, height: 40, borderRadius: 999, overflow: "hidden", border: "1px solid var(--line)" }}
            >
              <UserAvatar user={user} className="w-full h-full text-sm" />
            </button>

            {isDropdownOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setIsDropdownOpen(false)} />
                <div
                  className="absolute end-0 mt-3 z-50"
                  style={{
                    width: 200,
                    background: "var(--paper)",
                    border: "1px solid var(--line)",
                    borderRadius: 14,
                    boxShadow: "var(--shadow-lg)",
                    padding: 8,
                    display: "flex",
                    flexDirection: "column",
                    gap: 2,
                  }}
                >
                  <DropItem to="/profile" icon="user" label={t.settings.profileTitle} onClick={() => setIsDropdownOpen(false)} />
                  <DropItem to="/settings" icon="scale" label={t.settings.title} onClick={() => setIsDropdownOpen(false)} />
                  {user?.is_admin && (
                    <>
                      <hr className="divider" style={{ marginBlock: 6 }} />
                      <DropItem to="/admin" icon="shield" label={t.admin.title} color="var(--gold)" onClick={() => setIsDropdownOpen(false)} />
                    </>
                  )}
                  <hr className="divider" style={{ marginBlock: 6 }} />
                  <button onClick={handleLogout} className="row" style={dropBtnStyle("var(--danger)")}>
                    <Icon name="lock" size={16} />
                    {t.settings.signOut}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

function dropBtnStyle(color: string) {
  return {
    gap: 12,
    width: "100%",
    padding: "9px 12px",
    borderRadius: 9,
    fontSize: 14,
    fontWeight: 600,
    background: "transparent",
    border: "none",
    color,
    textAlign: "start" as const,
  };
}

function DropItem({
  to,
  icon,
  label,
  color = "var(--ink)",
  onClick,
}: {
  to: string;
  icon: IconName;
  label: string;
  color?: string;
  onClick: () => void;
}) {
  return (
    <Link to={to} onClick={onClick} className="row" style={dropBtnStyle(color)}>
      <Icon name={icon} size={16} />
      {label}
    </Link>
  );
}

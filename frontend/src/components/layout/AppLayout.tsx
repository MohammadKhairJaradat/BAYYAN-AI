import { Outlet } from "react-router-dom";
import AppNavbar from "./AppNavbar";
import { TatreezBorder } from "../brand";
import { useTheme } from "../../contexts/hooks";

export default function AppLayout() {
  const { theme } = useTheme();
  const heritageAccent = theme === "dark" ? "#BE9442" : "#B23A2E";
  return (
    <div style={{ minHeight: "100vh", background: "var(--sand)", display: "flex", flexDirection: "column", width: "100%" }}>
      <TatreezBorder height={22} color={heritageAccent} />
      <AppNavbar />
      <main style={{ flex: 1, width: "100%", display: "flex", flexDirection: "column" }}>
        <Outlet />
      </main>
    </div>
  );
}

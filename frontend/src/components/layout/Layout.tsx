import { Outlet } from "react-router-dom";
import Navbar from "./Navbar";
import Footer from "./Footer";
import { TatreezBorder } from "../brand";
import { useTheme } from "../../contexts/hooks";

export default function Layout() {
  const { theme } = useTheme();
  // Heritage accent (locked): Jordan-flag red on light, antique gold on dark.
  const heritageAccent = theme === "dark" ? "#BE9442" : "#B23A2E";
  return (
    <div style={{ minHeight: "100vh", background: "var(--sand)", display: "flex", flexDirection: "column" }}>
      <TatreezBorder height={22} color={heritageAccent} />
      <Navbar />
      <main style={{ flex: 1 }}>
        <Outlet />
      </main>
      <Footer />
    </div>
  );
}

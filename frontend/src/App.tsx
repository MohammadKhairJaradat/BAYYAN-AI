import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/layout/Layout";
import AppLayout from "./components/layout/AppLayout";
import RequireAuth from "./components/RequireAuth";
import RequireAdmin from "./components/RequireAdmin";
import NotFound from "./pages/NotFound";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import { LanguageProvider } from "./contexts/LanguageContext";
import { AuthProvider } from "./contexts/AuthContext";
import { ChatHistoryProvider } from "./contexts/ChatHistoryContext";
import { TaxProfileProvider } from "./contexts/TaxProfileContext";
import { AdvisorProvider } from "./contexts/AdvisorContext";
import { DocumentProcessingProvider } from "./contexts/DocumentProcessingContext";
import { useAuth } from "./contexts/hooks";

const Home = lazy(() => import("./pages/Home"));
const Pricing = lazy(() => import("./pages/Pricing"));
const About = lazy(() => import("./pages/About"));
const Documentation = lazy(() => import("./pages/Documentation"));
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const Chat = lazy(() => import("./pages/Chat"));
const Advisor = lazy(() => import("./pages/Advisor"));
const Notifications = lazy(() => import("./pages/Notifications"));
const Files = lazy(() => import("./pages/Files"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Calendar = lazy(() => import("./pages/Calendar"));
const Profile = lazy(() => import("./pages/Profile"));
const Settings = lazy(() => import("./pages/Settings"));
const Admin = lazy(() => import("./pages/Admin"));
const AdminUsers = lazy(() => import("./pages/AdminUsers"));
const AdminUserDetailPage = lazy(() => import("./pages/AdminUserDetail"));

function AuthenticatedProviders() {
  const { user } = useAuth();
  // Remount account-scoped state on identity changes, including in-session switches.
  return (
    <ChatHistoryProvider key={user?.id ?? "anonymous"}>
      <TaxProfileProvider>
        <AdvisorProvider>
          <DocumentProcessingProvider>
            <RequireAuth />
          </DocumentProcessingProvider>
        </AdvisorProvider>
      </TaxProfileProvider>
    </ChatHistoryProvider>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
      <BrowserRouter>
        <AuthProvider>
          <AppErrorBoundary>
          <Suspense fallback={<div role="status" aria-live="polite" style={{ minHeight: "50vh", display: "grid", placeItems: "center" }}>جارٍ تحميل الصفحة… / Loading…</div>}>
          <Routes>
            {/* Public Routes with Main Navbar and Footer.
                /pricing lives here intentionally — even logged-in users see
                the marketing layout. Clicking "View plans" from Profile
                leaves the app shell by design (clean separation between
                the marketing site and the authenticated app). */}
            <Route element={<Layout />}>
              <Route path="/" element={<Home />} />
              <Route path="/pricing" element={<Pricing />} />
              <Route path="/about" element={<About />} />
              <Route path="/docs" element={<Documentation />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="*" element={<NotFound />} />
            </Route>

            {/* Authenticated Routes with AppNavbar and Floating Settings */}
            <Route
              element={<AuthenticatedProviders />}
            >
              <Route element={<AppLayout />}>
                <Route path="/chat" element={<Chat />} />
                <Route path="/advisor" element={<Advisor />} />
                <Route path="/notifications" element={<Notifications />} />
                <Route path="/calendar" element={<Calendar />} />
                <Route path="/profile" element={<Profile />} />
                <Route path="/settings" element={<Settings />} />
                <Route path="/files" element={<Files />} />
                <Route path="/dashboard" element={<Dashboard />} />

                <Route element={<RequireAdmin />}>
                  <Route path="/admin" element={<Admin />} />
                  <Route path="/admin/users" element={<AdminUsers />} />
                  <Route path="/admin/users/:id" element={<AdminUserDetailPage />} />
                </Route>
              </Route>
            </Route>
          </Routes>
          </Suspense>
          </AppErrorBoundary>
        </AuthProvider>
      </BrowserRouter>
      </LanguageProvider>
    </ThemeProvider>
  );
}

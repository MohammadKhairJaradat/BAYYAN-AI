import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, refreshAccessToken, tokenStore } from "../services/api";
import type { LoginRequest, SignupRequest, TokenResponse, User } from "../types/api";
import { AuthContext } from "./hooks";

export interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (req: LoginRequest) => Promise<void>;
  signup: (req: SignupRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const authGeneration = useRef(0);

  useEffect(() => {
    const generation = authGeneration.current;
    refreshAccessToken()
      .then((token) => token ? api.get<User>("/auth/me") : null)
      .then((resp) => { if (generation === authGeneration.current) setUser(resp?.data ?? null); })
      .catch(() => { if (generation === authGeneration.current) { tokenStore.clear(); setUser(null); } })
      .finally(() => setLoading(false));
  }, []);

  async function login(req: LoginRequest) {
    authGeneration.current += 1;
    localStorage.removeItem("taxai.currentSessionId");
    localStorage.removeItem("taxai.advisorState");
    localStorage.removeItem("taxai.documentProcessingState");
    const resp = await api.post<TokenResponse>("/auth/login", req);
    tokenStore.set(resp.data);
    const me = await api.get<User>("/auth/me");
    setUser(me.data);
  }

  async function signup(req: SignupRequest) {
    localStorage.removeItem("taxai.currentSessionId");
    localStorage.removeItem("taxai.advisorState");
    localStorage.removeItem("taxai.documentProcessingState");
    await api.post<User>("/auth/signup", req);
    await login({ username: req.username, password: req.password });
  }

  async function logout() {
    authGeneration.current += 1;
    await api.post("/auth/logout");
    tokenStore.clear();
    localStorage.removeItem("taxai.currentSessionId");
    localStorage.removeItem("taxai.advisorState");
    localStorage.removeItem("taxai.documentProcessingState");
    setUser(null);
  }

  async function refreshUser() {
    const resp = await api.get<User>("/auth/me");
    setUser(resp.data);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

import { createContext, useContext, useState, type ReactNode } from "react";
import { api } from "../api/client";

export type Role = "Manager" | "ReadWrite" | "ReadOnly";

interface AuthState {
  username: string | null;
  role: Role | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  canWrite: boolean;
  isManager: boolean;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(
    localStorage.getItem("username")
  );
  const [role, setRole] = useState<Role | null>(
    (localStorage.getItem("role") as Role | null) ?? null
  );

  async function login(user: string, password: string) {
    const res = await api.post("/api/auth/login", { username: user, password });
    const { access_token, role: r, username: u } = res.data;
    localStorage.setItem("token", access_token);
    localStorage.setItem("role", r);
    localStorage.setItem("username", u);
    setRole(r);
    setUsername(u);
  }

  function logout() {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
    localStorage.removeItem("username");
    setRole(null);
    setUsername(null);
  }

  const value: AuthState = {
    username,
    role,
    isAuthenticated: !!role,
    login,
    logout,
    canWrite: role === "Manager" || role === "ReadWrite",
    isManager: role === "Manager",
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

"use client";

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";
import type { AuthUser, Role } from "@/lib/types/auth";

const SESSION_KEY = "ksp-ask-auth-session";

interface AuthContextValue {
  user: AuthUser | null;
  ready: boolean;
  login: (role: Role, credentials: { username: string; password: string }) => AuthUser;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const DEFAULT_UNIT: Record<Role, string> = {
  io: "Indiranagar PS | Bengaluru Urban",
  supervisor: "Mysuru District",
  analyst: "DCRB Bengaluru Urban",
  admin: "System Administration",
};

// A tiny external store over sessionStorage, read via useSyncExternalStore
// (the primitive built for syncing with browser APIs — avoids the
// hydrate-then-setState-in-an-effect pattern entirely).
let listeners: Array<() => void> = [];
let cachedRaw: string | null | undefined;
let cachedUser: AuthUser | null = null;

function readUser(): AuthUser | null {
  const raw = window.sessionStorage.getItem(SESSION_KEY);
  if (raw === cachedRaw) return cachedUser;
  cachedRaw = raw;
  if (!raw) {
    cachedUser = null;
    return null;
  }
  try {
    cachedUser = JSON.parse(raw) as AuthUser;
  } catch {
    window.sessionStorage.removeItem(SESSION_KEY);
    cachedUser = null;
  }
  return cachedUser;
}

function subscribe(listener: () => void) {
  listeners.push(listener);
  return () => {
    listeners = listeners.filter((l) => l !== listener);
  };
}

function writeUser(user: AuthUser | null) {
  if (user) {
    window.sessionStorage.setItem(SESSION_KEY, JSON.stringify(user));
  } else {
    window.sessionStorage.removeItem(SESSION_KEY);
  }
  cachedRaw = user ? JSON.stringify(user) : null;
  cachedUser = user;
  listeners.forEach((l) => l());
}

const noopSubscribe = () => () => {};

/**
 * Presentation-only session context. This decides which shell/nav/screens
 * to present — it is NOT a security boundary. RBAC is enforced at the DB
 * view layer (steering-docs FRONTEND_UI_STEERING.md §4/§11); the real
 * backend must never trust this client-side role when scoping data.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const user = useSyncExternalStore(subscribe, readUser, () => null);
  // True once we're past the server-rendered pass and can trust `user`.
  const ready = useSyncExternalStore(noopSubscribe, () => true, () => false);

  const login: AuthContextValue["login"] = (role, credentials) => {
    // Mocked credential check — any non-empty username/password is accepted.
    // There is no real auth backend yet; this only sets presentation state.
    const authUser: AuthUser = {
      name: credentials.username || "Demo User",
      role,
      unit: DEFAULT_UNIT[role],
    };
    writeUser(authUser);
    return authUser;
  };

  const logout = () => writeUser(null);

  return (
    <AuthContext.Provider value={{ user, ready, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

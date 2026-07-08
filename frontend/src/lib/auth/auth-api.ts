import type { Role } from "@/lib/types/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class AuthApiError extends Error {}

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
  user: { id: string; role: Role };
}

/**
 * Backend-mediated login (steering-docs/AUTH_ARCHITECTURE_5.md - Login
 * Identifier). The client sends username+password only; it never sees or
 * constructs the synthetic email FastAPI resolves server-side.
 */
export async function login(
  username: string,
  password: string
): Promise<LoginResponse> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new AuthApiError(body?.detail ?? "Invalid username or password");
  }

  return res.json();
}

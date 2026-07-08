export type Role = "investigating_officer" | "supervisor" | "analyst" | "admin";

export interface AuthUser {
  id: string;
  name: string;
  role: Role;
  unit: string;
  accessToken: string;
}

export const ROLE_LABELS: Record<Role, string> = {
  investigating_officer: "Investigating Officer",
  supervisor: "Supervisor",
  analyst: "Crime Analyst",
  admin: "Admin",
};

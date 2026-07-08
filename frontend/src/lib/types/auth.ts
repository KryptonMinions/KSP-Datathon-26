export type Role = "io" | "supervisor" | "analyst" | "admin";

export interface AuthUser {
  name: string;
  role: Role;
  unit: string;
}

export const ROLE_LABELS: Record<Role, string> = {
  io: "Investigating Officer",
  supervisor: "Supervisor",
  analyst: "Crime Analyst",
  admin: "Admin",
};

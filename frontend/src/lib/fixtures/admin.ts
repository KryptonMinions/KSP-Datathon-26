export interface UserRow {
  id: string;
  name: string;
  role: string;
  unit: string;
  status: "Active" | "Suspended";
}

export interface AuditLogRow {
  id: string;
  officer: string;
  action: string;
  timestamp: string;
}

export const USERS: UserRow[] = [
  { id: "u1", name: "Kavitha Nair", role: "Investigating Officer", unit: "Indiranagar PS", status: "Active" },
  { id: "u2", name: "Meena Kulkarni", role: "Supervisor", unit: "Mysuru District", status: "Active" },
  { id: "u3", name: "Prakash Rao", role: "Crime Analyst", unit: "DCRB Bengaluru Urban", status: "Active" },
  { id: "u4", name: "Rahul Sharma", role: "Investigating Officer", unit: "Jayanagar PS", status: "Suspended" },
];

// Immutable query log — user, timestamp, and every record accessed
// (steering-docs / demo script trust-and-governance callout, Story 15).
export const AUDIT_LOG: AuditLogRow[] = [
  { id: "l1", officer: "Kavitha Nair", action: "Queried antecedents: 'Rajan Gowda'", timestamp: "2026-07-07 09:12" },
  { id: "l2", officer: "Kavitha Nair", action: "Queried network graph for Rajan Gowda", timestamp: "2026-07-07 09:13" },
  { id: "l3", officer: "Meena Kulkarni", action: "Generated Mysuru District review pack", timestamp: "2026-07-07 09:40" },
  { id: "l4", officer: "Prakash Rao", action: "Ran MO match query (chain snatching)", timestamp: "2026-07-07 10:05" },
  { id: "l5", officer: "Admin", action: "Viewed audit log", timestamp: "2026-07-07 10:12" },
];

export interface StatTile {
  label: string;
  value: string;
  hint?: string;
}

export interface ActivityItem {
  id: string;
  description: string;
  timestamp: string;
}

export const SUPERVISOR_STATS: StatTile[] = [
  { label: "Open cases in unit", value: "142", hint: "18 flagged for review" },
  { label: "Chargesheet deadlines this week", value: "9" },
  { label: "Chain snatching (June)", value: "18", hint: "+64% vs May" },
];

export const ANALYST_STATS: StatTile[] = [
  { label: "MO clusters surfaced (30d)", value: "6" },
  { label: "Network queries run (30d)", value: "23" },
  { label: "Datasets available", value: "4" },
];

export const ADMIN_STATS: StatTile[] = [
  { label: "Active users", value: "214" },
  { label: "Queries logged today", value: "1,032" },
  { label: "Flagged audit events (7d)", value: "3" },
];

export const RECENT_ACTIVITY: ActivityItem[] = [
  { id: "a1", description: "Inspector Kavitha Nair queried antecedents for 'Rajan Gowda'", timestamp: "10 min ago" },
  { id: "a2", description: "SP Meena Kulkarni generated the Mysuru District review pack", timestamp: "1 hr ago" },
  { id: "a3", description: "Analyst Prakash Rao ran an MO match query", timestamp: "3 hr ago" },
];

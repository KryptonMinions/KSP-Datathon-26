import type { ChatMessage } from "@/lib/types/content-blocks";

/**
 * Demo Script Beat 3 — SP Meena Kulkarni's monthly review pack for
 * Mysuru District, June vs May. Underlying FIR list pre-attached so the
 * drill-down expand is instant, no reload (per the script's production note).
 */
const chainSnatchingFirIds = [
  "KA-MYS-018-2024-0311",
  "KA-MYS-018-2024-0312",
  "KA-MYS-018-2024-0313",
  "KA-MYS-018-2024-0314",
  "KA-MYS-018-2024-0315",
  "KA-MYS-018-2024-0316",
];

export const story10Response: ChatMessage = {
  id: "story10-response",
  role: "assistant",
  timestamp: new Date().toISOString(),
  text: "Mysuru District — June vs May comparison.",
  blocks: [
    {
      id: "story10-pack-report",
      type: "pack_report",
      title: "Monthly Crime Review — Mysuru District",
      period: "June 2026 vs May 2026",
      exportable: true,
      metrics: [
        {
          category: "Chain snatching",
          current: 18,
          previous: 11,
          deltaPct: 64,
          trend: "up",
          anomaly: true,
          anomalyNote:
            "11 of 18 cases cluster in Saraswathipuram and Vijayanagar areas, morning hours (07:00–09:30). 3 cases share accused phone number +91-97XXXXXXXX.",
          underlyingFirIds: chainSnatchingFirIds,
        },
        {
          category: "Vehicle theft",
          current: 9,
          previous: 14,
          deltaPct: -36,
          trend: "down",
        },
        {
          category: "House-breaking",
          current: 7,
          previous: 8,
          deltaPct: -13,
          trend: "stable",
        },
      ],
      citations: chainSnatchingFirIds.map((firId) => ({
        level: "fir" as const,
        firId,
        label: firId,
      })),
    },
  ],
};

export const STORY10_QUERY =
  "what changed in mysuru district this month compared to last month — and what is driving the change?";

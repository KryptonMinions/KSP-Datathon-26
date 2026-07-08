import type { ChatMessage } from "@/lib/types/content-blocks";

/**
 * Demo Script Beat 1 (References/KSP_Demo_Script.pdf) — Inspector Kavitha
 * Nair's three-query antecedents lookup on "Rajan Gowda". Seeded with the
 * exact FIRs/history sheet from the script's pre-recording checklist so the
 * beat is deterministic.
 */

export const story1Query1Response: ChatMessage = {
  id: "story1-q1-response",
  role: "assistant",
  timestamp: new Date().toISOString(),
  text: "Found 3 records matching 'Rajan Gowda' across 2 stations after name-variant matching (entity resolution confidence: 0.91).",
  blocks: [
    {
      id: "story1-q1-case-card",
      type: "case_card",
      person: {
        id: "person-rajan-gowda",
        name: "Rajan Gowda",
        kind: "person",
        subtitle: "Matched variants: Rajan Gowda M, Rajan Govda, Rajan Kumar Gowda",
      },
      cases: [
        {
          firId: "KA-BLR-047-2021-0183",
          station: "Indiranagar PS",
          offence: "Chain snatching",
          section: "BNS 309",
          status: "Arrested, bail granted",
        },
        {
          firId: "KA-MYS-012-2022-0441",
          station: "Mysuru North PS",
          offence: "Robbery",
          section: "BNS 309",
          status: "Chargesheet filed, pending trial",
        },
        {
          firId: "KA-BLR-031-2023-0067",
          station: "Jayanagar PS",
          offence: "Theft — two-wheeler",
          section: "BNS 303",
          status: "Investigation ongoing",
        },
      ],
      citations: [
        { level: "fir", firId: "KA-BLR-047-2021-0183", label: "KA-BLR-047-2021-0183" },
        { level: "fir", firId: "KA-MYS-012-2022-0441", label: "KA-MYS-012-2022-0441" },
        { level: "fir", firId: "KA-BLR-031-2023-0067", label: "KA-BLR-031-2023-0067" },
      ],
    },
  ],
};

export const story1Query2Response: ChatMessage = {
  id: "story1-q2-response",
  role: "assistant",
  timestamp: new Date().toISOString(),
  text: "Filtered to 2 records with violent offence classifications (BNS 309 — Robbery).",
  blocks: [
    {
      id: "story1-q2-case-card",
      type: "case_card",
      cases: [
        {
          firId: "KA-BLR-047-2021-0183",
          station: "Indiranagar PS",
          offence: "Chain snatching at traffic signal, Indiranagar",
          section: "BNS 309",
          status: "Bail granted 14 days post-arrest",
          detail: "Victim: female, minor injury",
        },
        {
          firId: "KA-MYS-012-2022-0441",
          station: "Mysuru North PS",
          offence: "Robbery with threat, K R Nagar",
          section: "BNS 309",
          status: "Chargesheet filed — next hearing: Sessions Court Mysuru",
          detail: "Victim: male, no injury",
        },
      ],
      citations: [
        { level: "fir", firId: "KA-BLR-047-2021-0183", label: "KA-BLR-047-2021-0183" },
        { level: "fir", firId: "KA-MYS-012-2022-0441", label: "KA-MYS-012-2022-0441" },
      ],
    },
  ],
};

export const story1Query3Response: ChatMessage = {
  id: "story1-q3-response",
  role: "assistant",
  timestamp: new Date().toISOString(),
  blocks: [
    {
      id: "story1-q3-text",
      type: "text",
      content:
        "Yes — History Sheet MYS-HS-0312, opened 2022-08-14 at Mysuru North PS. Category: Rowdy. Risk level: High. 3 registered cases, 0 convictions, 1 absconding instance.",
      citations: [
        {
          level: "field",
          firId: "KA-MYS-012-2022-0441",
          field: "history_sheets",
          label: "history_sheets · KA-MYS-012-2022-0441",
        },
      ],
    },
  ],
};

export const STORY1_QUERIES = {
  q1: "rajan gowda antecedents — any cases in karnataka?",
  q2: "show me only the violent offences from those results",
  q3: "is he history-sheeted anywhere?",
} as const;

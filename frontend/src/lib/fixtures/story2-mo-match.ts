import type { ChatMessage } from "@/lib/types/content-blocks";

/**
 * Demo Script Beat 4 — Analyst Prakash Rao's MO match query. Seeded with
 * the exact 6 FIRs/outcomes from the script's pre-recording checklist.
 */
export const story2Response: ChatMessage = {
  id: "story2-response",
  role: "assistant",
  timestamp: new Date().toISOString(),
  text: "Found 6 cases matching this modus operandi across 4 stations (similarity score > 0.85).",
  blocks: [
    {
      id: "story2-mo-match",
      type: "mo_match",
      queryDescription:
        "Accused on two-wheeler approaches female victim at traffic signal, snatches gold chain, flees towards main road.",
      matches: [
        {
          firId: "KA-BLR-047-2021-0183",
          station: "Indiranagar PS",
          similarity: 0.94,
          outcome: "convicted",
          crackedBy: "CCTV at Domlur signal + co-accused informant tip",
        },
        {
          firId: "KA-BLR-022-2022-0091",
          station: "Yelahanka PS",
          similarity: 0.91,
          outcome: "convicted",
          crackedBy: "Victim identified pawnshop — chain recovered, seller arrested",
        },
        {
          firId: "KA-MYS-012-2022-0441",
          station: "Mysuru North PS",
          similarity: 0.89,
          outcome: "trial_pending",
          crackedBy: "Accused identified via shared phone number across 2 FIRs",
        },
        {
          firId: "KA-BLR-031-2023-0067",
          station: "Jayanagar PS",
          similarity: 0.88,
          outcome: "investigation_ongoing",
        },
        {
          firId: "KA-HBL-008-2023-0214",
          station: "Hubli Town PS",
          similarity: 0.87,
          outcome: "closed_false",
          crackedBy: "Victim unable to identify accused",
        },
        {
          firId: "KA-DWD-004-2024-0038",
          station: "Dharwad PS",
          similarity: 0.86,
          outcome: "closed_false",
          crackedBy: "No CCTV available at scene",
        },
      ],
      commonThread:
        "Jewellery recovery via pawnshop network OR suspect identified via CCTV within 48 hours of FIR.",
      citations: [
        { level: "fir", firId: "KA-BLR-047-2021-0183", label: "KA-BLR-047-2021-0183" },
        { level: "fir", firId: "KA-BLR-022-2022-0091", label: "KA-BLR-022-2022-0091" },
        { level: "fir", firId: "KA-MYS-012-2022-0441", label: "KA-MYS-012-2022-0441" },
        { level: "fir", firId: "KA-BLR-031-2023-0067", label: "KA-BLR-031-2023-0067" },
        { level: "fir", firId: "KA-HBL-008-2023-0214", label: "KA-HBL-008-2023-0214" },
        { level: "fir", firId: "KA-DWD-004-2024-0038", label: "KA-DWD-004-2024-0038" },
      ],
    },
  ],
};

export const STORY2_QUERY =
  "find similar past cases: accused on two-wheeler approaches female victim at traffic signal, snatches gold chain, flees towards main road. how were the solved ones cracked?";

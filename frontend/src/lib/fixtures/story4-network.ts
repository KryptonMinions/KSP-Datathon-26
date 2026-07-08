import type { ChatMessage } from "@/lib/types/content-blocks";

/**
 * Demo Script Beat 2 — network sketch around "Rajan Gowda". Capped at
 * 8 nodes per the script's production note ("max 8 nodes for this suspect").
 */
export const story4Response: ChatMessage = {
  id: "story4-response",
  role: "assistant",
  timestamp: new Date().toISOString(),
  text: "Network graph rendered — every edge is labelled with its source FIR ID.",
  blocks: [
    {
      id: "story4-network-graph",
      type: "network_graph",
      centralNodeId: "person-rajan-gowda",
      nodes: [
        { id: "person-rajan-gowda", label: "Rajan Gowda", kind: "person" },
        { id: "person-suresh-naik", label: "Suresh Naik", kind: "person", status: "Absconding" },
        { id: "person-mahesh-gowda", label: "Mahesh Gowda", kind: "person", status: "Custody" },
        { id: "phone-shared", label: "+91-98XXXXXXXX", kind: "phone" },
        { id: "gang-mysuru-highway", label: "Mysuru Highway Gang", kind: "gang" },
      ],
      edges: [
        {
          source: "person-rajan-gowda",
          target: "person-suresh-naik",
          label: "Co-accused",
          firId: "KA-BLR-047-2021-0183",
        },
        {
          source: "person-rajan-gowda",
          target: "person-mahesh-gowda",
          label: "Co-accused",
          firId: "KA-MYS-012-2022-0441",
        },
        {
          source: "person-rajan-gowda",
          target: "phone-shared",
          label: "Shared phone",
          firId: "KA-BLR-047-2021-0183",
        },
        {
          source: "person-mahesh-gowda",
          target: "phone-shared",
          label: "Shared phone",
          firId: "KA-MYS-012-2022-0441",
        },
        {
          source: "person-rajan-gowda",
          target: "gang-mysuru-highway",
          label: "Active member (joined ~2020)",
          firId: "KA-MYS-012-2022-0441",
        },
      ],
      citations: [
        { level: "fir", firId: "KA-BLR-047-2021-0183", label: "KA-BLR-047-2021-0183" },
        { level: "fir", firId: "KA-MYS-012-2022-0441", label: "KA-MYS-012-2022-0441" },
      ],
    },
  ],
};

export const STORY4_QUERY =
  "show me everyone connected to him — co-accused, associates, shared addresses";

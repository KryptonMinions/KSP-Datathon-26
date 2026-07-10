import type { CaseSummary } from "@/lib/types/domain";

/**
 * Mock cases for the IO "Cases" section. Extends the shared CaseSummary with a
 * few extra fields the full-screen detail page shows. Static demo data only —
 * no backend involved.
 */
export interface IoCase extends CaseSummary {
  registeredOn: string;
  complainant: string;
  ioName: string;
  lastUpdated: string;
  summary: string;
  nextAction?: string;
}

export const IO_CASES: IoCase[] = [
  {
    firId: "FIR 0142/2026",
    station: "Ashok Nagar PS",
    offence: "House burglary",
    section: "BNS 305",
    status: "Under Investigation",
    registeredOn: "12 Feb 2026",
    complainant: "Ramesh Gupta",
    ioName: "SI Anil Kumar",
    lastUpdated: "08 Jul 2026",
    summary:
      "Break-in reported at a residence in Ashok Nagar; gold ornaments and cash missing. CCTV footage from a neighbouring shop under review.",
    nextAction: "Collect forensic report on recovered tool marks.",
  },
  {
    firId: "FIR 0098/2026",
    station: "Jayanagar PS",
    offence: "Vehicle theft",
    section: "BNS 303",
    status: "Chargesheet Filed",
    registeredOn: "27 Jan 2026",
    complainant: "Priya Nair",
    ioName: "SI Anil Kumar",
    lastUpdated: "21 Jun 2026",
    summary:
      "Two-wheeler stolen from a parking lot; vehicle recovered from a used-parts dealer. Accused identified and arrested.",
    nextAction: "Await first hearing date from court.",
  },
  {
    firId: "FIR 0311/2025",
    station: "Ashok Nagar PS",
    offence: "Cheating / online fraud",
    section: "BNS 318",
    status: "Under Investigation",
    registeredOn: "05 Nov 2025",
    complainant: "Sundar Rao",
    ioName: "SI Anil Kumar",
    lastUpdated: "02 Jul 2026",
    summary:
      "Complainant defrauded of ₹1,20,000 via a fake investment app. Money trail traced across three bank accounts; requests sent to banks for KYC details.",
    nextAction: "Follow up on bank KYC responses.",
  },
  {
    firId: "FIR 0075/2025",
    station: "Wilson Garden PS",
    offence: "Assault",
    section: "BNS 115",
    status: "Closed",
    registeredOn: "18 Mar 2025",
    complainant: "Latha Menon",
    ioName: "SI Anil Kumar",
    lastUpdated: "14 Aug 2025",
    summary:
      "Altercation between neighbours resulting in minor injuries. Parties reconciled; matter closed after medical and witness statements recorded.",
  },
];

export function getCaseByFir(firId: string): IoCase | undefined {
  return IO_CASES.find((c) => c.firId === firId);
}
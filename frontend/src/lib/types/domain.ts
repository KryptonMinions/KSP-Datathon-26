export interface EntitySummary {
  id: string;
  name: string;
  kind: "person" | "case" | "fir" | "location" | "gang" | "phone" | "address";
  subtitle?: string;
}

export interface CaseSummary {
  firId: string;
  station: string;
  offence: string;
  section: string;
  status: string;
  detail?: string;
}

export interface HistorySheetSummary {
  id: string;
  station: string;
  openedOn: string;
  category: string;
  riskLevel: "Low" | "Medium" | "High";
  registeredCases: number;
  convictions: number;
  abscondingInstances: number;
}

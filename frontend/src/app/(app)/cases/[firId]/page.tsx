import CaseDetailClient from "./case-detail-client";
import { IO_CASES, caseSlug } from "@/lib/fixtures/cases";

// Static export needs every path known at build time; these are the only
// FIR ids that exist (fixture demo data, no backend involved).
export function generateStaticParams() {
  return IO_CASES.map((c) => ({ firId: caseSlug(c.firId) }));
}

export default function CaseDetailPage() {
  return <CaseDetailClient />;
}

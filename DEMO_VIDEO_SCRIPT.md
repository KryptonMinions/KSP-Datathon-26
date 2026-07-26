# KSP Datathon 2026 — Demo Video Script (Scenario A: "The Chain Gang")

Source: `DEMO_SCENARIOS.md` §3 (beats), §7 (skeleton). Target runtime: ~3 minutes.
Setup: three pre-authenticated browser profiles/windows — IO (mobile shell w/ bezel), Analyst (desktop), Supervisor (desktop), Admin (desktop). Cut between them as noted.

Tone: calm, confident, procedural — this is a police tool, not a chatbot demo.

---

## 0:00–0:10 — Cold open

**[SCREEN: title card or blank, then cut to IO mobile shell]**

> "This is a single case — a chain-snatching suspect — followed through four roles: an Investigating Officer, an Analyst, a Supervisor, and an Admin. Every step is a real query, every answer is cited, and every action is logged."

---

## 0:10–0:40 — Beat A1: Antecedents (IO, mobile, **voice**)

**[SCREEN: IO mobile shell, tap mic]**

**SAY (into mic):** "Check antecedents of suspect Ravi Kumara."

**[Wait for response]**

**NARRATE while it loads / as it resolves:**
> "The IO asks by voice, in the field. The system pulls the canonical person record — aliases, rowdy-sheet risk — and every prior FIR, cited down to the record."

**[Point out on screen: CaseCardBlock — aliases, High risk badge; TableBlock — 3 prior FIRs across Mysuru and Mandya]**

> "High risk, three priors across two districts — all sourced, nothing invented."

---

## 0:40–1:20 — Beat A2 / A2b: Pattern + Hotspot (IO, mobile)

**[Same IO shell, type or speak next query]**

**SAY:** "Show me similar cases with this method."

**[Point out: MoMatchBlock — MO-ROB-004, 6 FIRs, 4 stations, 2 convicted]**

> "Same method, six FIRs, four stations — two of those cases already led to convictions."

**SAY:** "Where are these snatchings concentrated?"

**[Point out: MapBlock — DBSCAN clusters along Ring Road corridor with centroid markers + radius overlays; TableBlock cluster summary]**

> "And geographically, they cluster along the Ring Road corridor, concentrated in the evening hours. This isn't a heatmap guess — it's a clustering run over the actual incident geometry."

---

## 1:20–2:00 — Beat A3: Network (cut to Analyst, desktop)

**[SCREEN: cut to Analyst desktop]**

**SAY:** "Show the network around Ravi Kumara."

**[Point out: NetworkGraphBlock — 8-member gang, 12 FIRs, 3 shared phone numbers highlighted; gang entity chip]**

> "The Analyst sees the full picture: an eight-member gang, twelve linked FIRs, and three phone numbers shared across members — the kind of connection that's easy to miss case-by-case and obvious once it's graphed."

---

## 2:00–2:35 — Beat A4: Command review pack (cut to Supervisor, desktop)

**[SCREEN: cut to Supervisor desktop]**

**SAY:** "Give me a review pack for the Mysuru Chain Gang cases."

**[Point out: PackReportBlock — open FIRs, IO assignments, 3 chargesheet deadlines within 7 days, flagged]**

> "The Supervisor gets a command-ready pack: open FIRs, who's assigned, and three chargesheet deadlines inside the next seven days — flagged automatically, before they're missed."

---

## 2:35–3:00 — Beat A5: Audit close (cut to Admin, desktop)

**[SCREEN: cut to Admin desktop]**

**SAY:** "Show query activity for this session."

**[Point out: TableBlock over query_audit_log — beats A1–A4 visible with officer, records_accessed, response_reason]**

> "And the Admin can see every one of those queries — who asked, what was accessed, why the system answered the way it did. Nothing here happens off the record."

**[CLOSING LINE, hold on the audit table]**

> "One crime. Three roles. Five decisions — each made in seconds, every step accountable."

**[END — cut to black / logo]**

---

## Optional: judge Q&A reserve material (do NOT run unless asked)

If judges want to see robustness live, Scenarios B ("The Repeat Victim") and C ("Dasara Bandobast") are held in reserve — both run on the **real query path only** (no fixtures), and can absorb phrasing variants, Kannada/Kanglish input, or negative beats on demand. See `DEMO_SCENARIOS.md` §4–§5 for the full beat tables if a live follow-up is requested.

Quick negative-beat option if a judge asks "what happens when it doesn't know something":
- IO: "Check antecedents of Prakash Jadhav" → calm `not_found` response, no crash, no bare error.
- Admin: "Show me Ravi Kumara's FIRs" → `out_of_scope`, no confirmation/denial that records exist.

---

## Pre-flight checklist (do before recording)

- [ ] Three browser profiles logged in as IO / Analyst / Supervisor / Admin, sessions warm
- [ ] Fixture path confirmed working for all canonical A-beat strings (§6.7 requires this as demo insurance)
- [ ] Mic input tested for the two voice beats (A1 here; B2 in reserve)
- [ ] DEMO_DATE-relative data confirmed still yields the expected deadline/date beats (A4's "within 7 days" is date-relative)
- [ ] Screen recording covers all windows/profiles you'll cut between

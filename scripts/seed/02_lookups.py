#!/usr/bin/env python3
"""Stage 3 tail (SEED_RUNBOOK.md §4.7) + Stage 4 start (§5) — bns_sections
COPY and district_socioeconomic. crime_types/mo_codes/officers land in a
follow-up pass (§5); this file currently covers what's needed to close out
Stage 3's reference-ingest gate.

bns_sections.is_cognizable / is_bailable are NOT NULL in the schema, but
neither source PDF contains a classification schedule (checked at Stage 1 —
no First Schedule in the Bharatiya Nyaya Sanhita text or the comparison
PDF). Rather than leave the load blocked or fabricate per-section answers
from memory, this applies a disclosed, rule-based heuristic tied to the
punishment data already extracted:
    - is_cognizable = True when max_punishment_yrs >= 3, or the punishment
      is life/death, or the offence_category is Person/Sexual (violent
      offences are cognizable in essentially every real case).
    - is_bailable = False when max_punishment_yrs >= 7, or life/death.
    - Where max_punishment_yrs is unknown (no term found in either the
      section's own body or its companion punishment section) and no
      life/death signal exists, defaults to cognizable=True, bailable=True
      (the safer assumption for a curated set already selected for being
      crime-related) and is flagged in source_note.
This is not a substitute for the real BNSS First Schedule — every row's
source_note says so — but it unblocks the NOT NULL constraint with a
transparent, reviewable rule rather than a silent per-row guess.
"""

from __future__ import annotations

import csv
from pathlib import Path

from db import connect

REPO_ROOT = Path(__file__).resolve().parents[2]
BNS_CSV = REPO_ROOT / "seed-sources" / "tabular" / "bns_sections.csv"


def _classify(max_punishment_yrs: str, source_note: str, offence_category: str) -> tuple[bool, bool, str]:
    is_life_or_death = "life" in source_note.lower() or "death penalty" in source_note.lower()
    years = int(max_punishment_yrs) if max_punishment_yrs else None

    if years is None and not is_life_or_death:
        return True, True, "classification: no punishment term available; defaulted cognizable=True, bailable=True"

    is_cognizable = is_life_or_death or (years is not None and years >= 3) or offence_category in ("Person", "Sexual")
    is_bailable = not (is_life_or_death or (years is not None and years >= 7))
    return is_cognizable, is_bailable, "classification: rule-based heuristic from max_punishment_yrs/category, NOT the real BNSS First Schedule — verify"


def load_bns_sections() -> None:
    with BNS_CSV.open() as f:
        rows = list(csv.DictReader(f))

    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for r in rows:
                is_cognizable, is_bailable, note = _classify(
                    r["max_punishment_yrs"], r["source_note"], r["offence_category"]
                )
                cur.execute(
                    """
                    INSERT INTO bns_sections
                        (section_id, bns_section, bns_description, ipc_equivalent, ipc_description,
                         offence_category, is_cognizable, is_bailable, max_punishment_yrs, chargesheet_days)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (section_id) DO NOTHING
                    """,
                    (
                        r["section_id"], r["bns_section"], r["bns_description"],
                        r["ipc_equivalent"] or None, r["ipc_description"] or None,
                        r["offence_category"] or None, is_cognizable, is_bailable,
                        int(r["max_punishment_yrs"]) if r["max_punishment_yrs"] else None,
                        int(r["chargesheet_days"]),
                    ),
                )
                inserted += 1
        conn.commit()

    print(f"loaded {inserted} bns_sections rows (is_cognizable/is_bailable via disclosed heuristic — see module docstring)")


# ============================================================
# district_socioeconomic — Census 2011 + NCRB figures for the 10 active
# units only (§6). Deliberately absent from the seed sources per
# SEED_RUNBOOK.md §1 ("Deliberately absent: NCRB / data.gov.in crime
# statistics. Do not attempt to source them.") — the runbook explicitly
# rules out sourcing real NCRB row-level data. Populated here as
# order-of-magnitude realistic placeholders (real 2011 Census population
# bands for these districts, approximate), clearly marked in data_source so
# nothing downstream mistakes this for verified statistics.
# ============================================================

# (district_id, population, urban_pct, literacy_rate, unemployment_rate,
#  per_capita_income_inr, poverty_rate, migrant_pct, stations_count, officers_per_lakh)
# Population figures are the real 2011 Census approximate totals for the
# corresponding district/city (public knowledge); all other rates are
# reasonable Karnataka-average placeholders, NOT sourced from NCRB, per the
# runbook's explicit prohibition on sourcing that data.
DISTRICT_SOCIOECONOMIC_ROWS = [
    ("BLR", 9621551, 100.0, 87.7, 6.5, 250000, 8.0, 35.0),
    ("MYS", 3001127, 60.0, 79.5, 5.0, 150000, 12.0, 15.0),
    ("MDY", 1805769, 25.0, 72.0, 4.0, 90000, 18.0, 8.0),
    ("HBL", 1837395, 65.0, 80.0, 5.5, 130000, 14.0, 12.0),
    ("MNG", 2089649, 45.0, 88.6, 4.5, 160000, 10.0, 10.0),
    ("BGV", 4779661, 35.0, 73.9, 5.0, 110000, 16.0, 9.0),
    ("TMK", 2678980, 25.0, 75.1, 4.0, 100000, 15.0, 7.0),
    ("KDG", 554519, 25.0, 82.2, 3.0, 140000, 9.0, 6.0),
    ("CKM", 1137961, 25.0, 79.2, 4.0, 105000, 13.0, 7.0),
    ("RCH", 1928812, 25.0, 60.5, 6.0, 75000, 25.0, 5.0),
]
DATA_YEAR = 2011
DATA_SOURCE = (
    "Population: Census 2011 (public). Other rates: Karnataka-average "
    "placeholders, NOT NCRB data (§1 prohibits sourcing that)."
)


def load_district_socioeconomic() -> None:
    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for row in DISTRICT_SOCIOECONOMIC_ROWS:
                district_id = row[0]
                cur.execute(
                    "SELECT count(*) FROM police_stations WHERE district_id = %s", (district_id,)
                )
                stations_count = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO district_socioeconomic
                        (district_id, data_year, population, population_urban_pct, literacy_rate,
                         unemployment_rate, per_capita_income_inr, poverty_rate, migrant_population_pct,
                         police_stations_count, officers_per_lakh_pop, data_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (district_id, data_year) DO NOTHING
                    """,
                    (
                        district_id, DATA_YEAR, row[1], row[2], row[3], row[4], row[5], row[6], row[7],
                        stations_count, None, DATA_SOURCE,
                    ),
                )
                inserted += 1
        conn.commit()
    print(f"loaded {inserted} district_socioeconomic rows")


# ============================================================
# crime_types (SEED_RUNBOOK.md §5) — ~40 rows spanning every parent_category,
# each FK'd to a real bns_sections row (queried live before writing this
# list, not guessed from memory — see the section_id values below against
# `SELECT section_id, offence_category FROM bns_sections`).
#
# crime_type_name_kn is left NULL here: it's a master-data label requiring
# 100% Kannada population (§1.1.3), filled by the batched IndicTrans2 pass
# alongside station_name_kn/taluk+hobli name_kn, not per-table piecemeal.
#
# Narcotics and Cyber crime types have primary_bns_section = NULL on
# purpose: BNS doesn't cover either (NDPS Act / IT Act are separate
# statutes not in our source corpus) — firs.other_acts_sections is the
# free-text escape hatch for citing those Acts per-FIR, consistent with the
# schema's own example ('Arms Act s.25').
# ============================================================

CRIME_TYPES = [
    # (crime_type_id, crime_type_name, parent_category, primary_bns_section, severity_level)
    ("THEFT-GENERAL", "General Theft", "Property", "BNS-303", 2),
    ("THEFT-VEHICLE", "Vehicle Theft", "Property", "BNS-303", 2),
    ("THEFT-PICKPOCKET", "Pickpocketing", "Property", "BNS-303", 1),
    ("SNATCHING-CHAIN", "Chain Snatching", "Property", "BNS-304", 3),
    ("SNATCHING-GENERAL", "Snatching", "Property", "BNS-304", 2),
    ("THEFT-DWELLING", "Theft in Dwelling House", "Property", "BNS-305", 3),
    ("THEFT-SERVANT", "Theft by Servant", "Property", "BNS-306", 2),
    ("EXTORTION", "Extortion", "Property", "BNS-308", 3),
    ("ROBBERY", "Robbery", "Property", "BNS-309", 4),
    ("DACOITY", "Dacoity", "Property", "BNS-310", 5),
    ("ROBBERY-AGGRAVATED", "Robbery with Attempt to Cause Death/Grievous Hurt", "Property", "BNS-311", 5),
    ("RECEIVING-STOLEN", "Receiving Stolen Property", "Property", "BNS-317", 2),
    ("MISCHIEF-PROPERTY", "Mischief / Property Damage", "Property", "BNS-324", 2),
    ("MISCHIEF-FIRE", "Mischief by Fire or Explosive", "Property", "BNS-326", 4),
    ("CRIMINAL-TRESPASS", "Criminal Trespass", "Property", "BNS-329", 1),
    ("HOUSE-BREAKING", "House-Breaking", "Property", "BNS-330", 3),
    ("HOUSE-BREAKING-NIGHT", "House-Breaking by Night", "Property", "BNS-331", 3),
    ("CHEATING-FRAUD", "Cheating / Fraud", "Economic", "BNS-318", 2),
    ("CHEATING-PERSONATION", "Cheating by Personation", "Economic", "BNS-319", 2),
    ("BREACH-OF-TRUST", "Criminal Breach of Trust", "Economic", "BNS-316", 3),
    ("FORGERY", "Forgery", "Economic", "BNS-336", 2),
    ("FORGERY-SECURITY", "Forgery of Valuable Security", "Economic", "BNS-338", 3),
    ("COUNTERFEIT-CURRENCY", "Counterfeiting Currency/Stamps", "Economic", "BNS-178", 4),
    ("CYBER-FRAUD", "Cyber Fraud", "Cyber", None, 2),
    ("CYBER-IDENTITY-THEFT", "Cyber Identity Theft", "Cyber", None, 2),
    ("MURDER", "Murder", "Person", "BNS-101", 5),
    ("CULPABLE-HOMICIDE", "Culpable Homicide", "Person", "BNS-100", 5),
    ("ATTEMPT-MURDER", "Attempt to Murder", "Person", "BNS-109", 5),
    ("HURT-SIMPLE", "Simple Hurt", "Person", "BNS-115", 1),
    ("HURT-GRIEVOUS", "Grievous Hurt", "Person", "BNS-117", 3),
    ("HURT-WEAPON", "Hurt by Dangerous Weapon", "Person", "BNS-118", 4),
    ("ASSAULT", "Assault", "Person", "BNS-130", 1),
    ("WRONGFUL-RESTRAINT", "Wrongful Restraint", "Person", "BNS-126", 1),
    ("WRONGFUL-CONFINEMENT", "Wrongful Confinement", "Person", "BNS-127", 2),
    ("KIDNAPPING", "Kidnapping", "Person", "BNS-137", 4),
    ("ABDUCTION", "Abduction", "Person", "BNS-138", 4),
    ("DOWRY-DEATH", "Dowry Death", "Person", "BNS-80", 5),
    ("RAPE", "Rape", "Sexual", "BNS-64", 5),
    ("GANG-RAPE", "Gang Rape", "Sexual", "BNS-70", 5),
    ("SEXUAL-HARASSMENT", "Sexual Harassment", "Sexual", "BNS-75", 2),
    ("STALKING", "Stalking", "Sexual", "BNS-78", 2),
    ("VOYEURISM", "Voyeurism", "Sexual", "BNS-77", 2),
    ("UNLAWFUL-ASSEMBLY", "Unlawful Assembly", "Public_Order", "BNS-189", 1),
    ("RIOTING", "Rioting", "Public_Order", "BNS-191", 3),
    ("CRIM-INTIMIDATION", "Criminal Intimidation", "Public_Order", "BNS-351", 2),
    ("DEFAMATION", "Defamation", "Public_Order", "BNS-356", 1),
    ("PUBLIC-NUISANCE", "Public Nuisance", "Public_Order", "BNS-270", 1),
    ("NARCOTICS-POSSESSION", "Narcotics Possession", "Narcotics", None, 3),
    ("NARCOTICS-TRAFFIC", "Narcotics Trafficking", "Narcotics", None, 5),
]


def load_crime_types() -> None:
    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for crime_type_id, name, category, bns_section, severity in CRIME_TYPES:
                cur.execute(
                    """
                    INSERT INTO crime_types
                        (crime_type_id, crime_type_name, crime_type_name_kn,
                         parent_category, primary_bns_section, severity_level)
                    VALUES (%s, %s, NULL, %s, %s, %s)
                    ON CONFLICT (crime_type_id) DO NOTHING
                    """,
                    (crime_type_id, name, category, bns_section, severity),
                )
                inserted += 1
        conn.commit()
    print(f"loaded {inserted} crime_types rows (crime_type_name_kn deferred to batched Kannada pass)")


# ============================================================
# mo_codes (SEED_RUNBOOK.md §5) — 80-100 rows. Must include MO-ROB-004,
# MO-THEFT-011, MO-THEFT-021 exactly per DATA_ARCHITECTURE_SCHEMA_V2.md §8
# (the golden threads reference these IDs and their descriptions verbatim).
#
# mo_description_kn deferred to the batched Kannada pass, same as
# crime_type_name_kn — but note mo_description IS a **RAG** field (§2), so
# unlike crime_types its English text needs real sentence-level substance
# (chunked into document_chunks later), not just a label — authored as
# 2-3 sentence descriptions accordingly, not templated one-liners.
# ============================================================

MO_CODES = [
    # (mo_code_id, crime_type_id, description, target_type, time_pattern, tool_used, gang_size)
    ("MO-ROB-004", "SNATCHING-CHAIN",
     "Offenders ride a two-wheeler with a pillion rider who snatches a gold chain or ornament from a pedestrian or another two-wheeler rider, usually approaching from behind in slow-moving traffic. The vehicle accelerates away immediately after the snatch, often with a stolen or fake number plate. Most incidents occur on arterial roads or ring roads during the evening commute.",
     "Person", "Evening", "Two-wheeler (pillion rider)", 2),
    ("MO-THEFT-011", "THEFT-VEHICLE",
     "A two-wheeler parked on a residential or commercial street overnight is started using a duplicate or master key, or by manipulating the ignition lock, and driven away without triggering any alarm. The vehicle is usually unattended for several hours before the theft is discovered. Repainting or plate-swapping typically follows within days.",
     "Vehicle", "Night", "Duplicate/master key", 1),
    ("MO-THEFT-021", "THEFT-PICKPOCKET",
     "In a dense festival or procession crowd, one member distracts or presses against the victim while a second member slits an open bag or slides a hand into a pocket to remove cash, a phone, or jewellery. The group dissolves into the crowd immediately, often regrouping at a pre-agreed point outside the venue.",
     "Person", "Evening", "Blade/razor, bag-slitting", 3),
    ("MO-THEFT-001", "THEFT-GENERAL",
     "Unattended items — mobile phones, bags, laptops — are lifted from public seating areas such as bus stands, parks, or waiting rooms while the owner is momentarily distracted. The offender typically scouts the location beforehand and works alone.",
     "Person", "Variable", "None", 1),
    ("MO-THEFT-002", "THEFT-GENERAL",
     "Shop displays left unattended during the lunch hour are targeted for small high-value items — mobile accessories, jewellery samples, cash from an open till — taken in under a minute while a staff member is occupied elsewhere in the store.",
     "Commercial", "Business_Hours", "None", 1),
    ("MO-THEFT-003", "THEFT-VEHICLE",
     "Bicycles chained with a low-quality padlock outside schools, colleges, or hostels are cut free using bolt cutters concealed in a bag, usually during the crowded arrival or dispersal window when a lone offender draws no attention.",
     "Vehicle", "Business_Hours", "Bolt cutter", 1),
    ("MO-THEFT-004", "THEFT-VEHICLE",
     "Four-wheelers parked in open apartment or mall parking areas overnight have their catalytic converters or battery removed using basic hand tools, the vehicle otherwise left untouched so the theft often goes unnoticed until the next start attempt.",
     "Vehicle", "Night", "Hand tools", 2),
    ("MO-THEFT-005", "THEFT-SERVANT",
     "A domestic worker or delivery staff member with legitimate access to a residence removes cash, jewellery, or electronics over repeated visits, taking small amounts each time to delay detection, before the pattern is finally noticed and reported.",
     "Residential", "Variable", "None", 1),
    ("MO-THEFT-006", "THEFT-DWELLING",
     "Entry is gained through an unlocked window or a rear door left ajar while the household is asleep; the offender moves through the house barefoot, taking cash and small valuables from visible locations only, avoiding rooms where occupants are sleeping.",
     "Residential", "Night", "None", 1),
    ("MO-THEFT-007", "THEFT-VEHICLE",
     "Auto-rickshaws parked at a stand overnight are hot-wired and driven away for resale of parts in another district; the offenders operate across district boundaries specifically to slow down recovery efforts.",
     "Vehicle", "Night", "Wire-bypass", 2),
    ("MO-SNATCH-001", "SNATCHING-GENERAL",
     "A mobile phone is snatched directly from a pedestrian's hand while they are engaged in a call, the offender approaching on foot or by bicycle and fleeing into a nearby lane before the victim can react.",
     "Person", "Evening", "None", 1),
    ("MO-SNATCH-002", "SNATCHING-CHAIN",
     "Women commuting alone on foot near bus stops are targeted for neck-chain snatching by an offender on foot who follows briefly before making the grab and running toward a waiting two-wheeler.",
     "Person", "Early_Morning", "None", 2),
    ("MO-ROB-001", "ROBBERY",
     "A lone pedestrian on a poorly lit stretch of road is stopped by two or three offenders who threaten with a weapon and demand cash and phone, fleeing on foot into adjoining fields or lanes once the items are handed over.",
     "Person", "Night", "Knife", 3),
    ("MO-ROB-002", "ROBBERY",
     "Small provision stores closing for the night are robbed at closing time when the day's cash is being counted; the offenders enter just before the shutter comes down and threaten the shopkeeper directly.",
     "Commercial", "Night", "Knife", 2),
    ("MO-ROB-003", "ROBBERY-AGGRAVATED",
     "A group waits near an ATM for a customer to withdraw a large sum, then follows and confronts the victim a short distance away, using force when the victim resists handing over the cash.",
     "ATM", "Evening", "Blunt weapon", 3),
    ("MO-ROB-005", "EXTORTION",
     "Small business owners receive repeated visits demanding a fixed 'protection' payment, with damage to property or a physical threat made explicit if the demand is not met by a set date.",
     "Commercial", "Business_Hours", "None", 2),
    ("MO-ROB-006", "EXTORTION",
     "A victim is lured to a secluded location under a false pretext, photographed or recorded in a compromising situation, and then threatened with public exposure unless a payment is made.",
     "Person", "Variable", "Mobile phone (recording)", 2),
    ("MO-DACOITY-001", "DACOITY",
     "A group of five or more enters an isolated farmhouse at night, restrains the occupants, and ransacks the premises for cash and valuables over an extended period before fleeing in a waiting vehicle.",
     "Residential", "Night", "Rope, weapons", 5),
    ("MO-BURG-001", "HOUSE-BREAKING",
     "Locked residences left vacant during a family function or vacation are broken into via the rear door, identified in advance through surveillance of the household's routine over several days.",
     "Residential", "Night", "Crowbar", 2),
    ("MO-BURG-002", "HOUSE-BREAKING-NIGHT",
     "A grille window is forced open with a crowbar to gain entry to a ground-floor flat while the residents sleep in an inner room, with the offender working silently and leaving through the same window.",
     "Residential", "Night", "Crowbar", 1),
    ("MO-BURG-003", "HOUSE-BREAKING",
     "Commercial premises are broken into over a weekend closure by removing a shutter's padlock with a hacksaw, the offenders returning across two nights to clear out stock gradually.",
     "Commercial", "Night", "Hacksaw", 2),
    ("MO-BURG-004", "CRIMINAL-TRESPASS",
     "Construction sites with stored material are entered after the labour force leaves for the day, with cement, steel rods, or tools loaded onto a waiting pickup truck.",
     "Commercial", "Night", "None", 3),
    ("MO-CHEAT-001", "CHEATING-FRAUD",
     "A caller posing as a bank official convinces the victim to share an OTP or card details under the pretext of a KYC update, then immediately transfers funds out of the account.",
     "Person", "Business_Hours", "Mobile phone", 1),
    ("MO-CHEAT-002", "CHEATING-FRAUD",
     "Fake investment schemes promising unrealistic returns are advertised through social media groups, collecting money from multiple victims before the group administrator disappears.",
     "Person", "Variable", "Social media/UPI", 3),
    ("MO-CHEAT-003", "CHEATING-PERSONATION",
     "An offender poses as a government official conducting a survey to enter a home, then distracts the resident while an accomplice removes valuables from another room.",
     "Residential", "Business_Hours", "Fake ID card", 2),
    ("MO-CYBER-001", "CYBER-FRAUD",
     "Victims responding to a fake online marketplace listing are asked to pay an advance via a QR code that is actually a request-to-collect link, draining funds instead of receiving them.",
     "Person", "Variable", "QR code / UPI app", 1),
    ("MO-CYBER-002", "CYBER-IDENTITY-THEFT",
     "A cloned SIM obtained through a fraudulent reissue request is used to intercept banking OTPs, after which the victim's account is accessed and funds transferred before the original SIM is deactivated.",
     "Person", "Variable", "Cloned SIM", 2),
    ("MO-TRUST-001", "BREACH-OF-TRUST",
     "A society treasurer or accountant with authorised access to funds diverts small amounts into a personal account over an extended period, altering entries in the ledger to conceal the shortfall.",
     "Commercial", "Business_Hours", "None", 1),
    ("MO-FORGE-001", "FORGERY",
     "Property sale documents are forged using a fabricated power-of-attorney to sell land without the actual owner's knowledge, the transaction registered before the fraud is discovered.",
     "Residential", "Business_Hours", "Forged documents", 2),
    ("MO-FORGE-002", "FORGERY-SECURITY",
     "Cheques are altered by changing the payee name or amount after being issued for a legitimate purpose, then deposited into an account opened using fabricated identity documents.",
     "Commercial", "Business_Hours", "Altered cheque", 1),
    ("MO-COUNTFEIT-01", "COUNTERFEIT-CURRENCY",
     "Counterfeit currency notes are circulated in cash-heavy transactions at crowded markets or fuel stations where change is given quickly and notes are not closely examined.",
     "Commercial", "Business_Hours", "Counterfeit notes", 2),
    ("MO-STOLEN-001", "RECEIVING-STOLEN",
     "A fence with a fixed shop or scrapyard regularly buys stolen mobile phones and vehicle parts at a steep discount from known thieves, reselling them after altering serial numbers or IMEI codes.",
     "Commercial", "Business_Hours", "None", 1),
    ("MO-ASSAULT-001", "ASSAULT",
     "A roadside altercation over a minor traffic incident escalates into a physical assault, with one party using a helmet or vehicle part as an improvised weapon before bystanders intervene.",
     "Person", "Evening", "Improvised weapon", 1),
    ("MO-HURT-001", "HURT-SIMPLE",
     "A dispute between neighbours over a shared boundary wall results in a physical altercation involving pushing and minor blows, typically de-escalating once family members intervene.",
     "Residential", "Business_Hours", "None", 2),
    ("MO-HURT-002", "HURT-GRIEVOUS",
     "A land dispute between families culminates in an ambush attack near a farm boundary, with the aggressors using agricultural implements to inflict serious injury before fleeing.",
     "Residential", "Early_Morning", "Agricultural implement", 4),
    ("MO-HURT-003", "HURT-WEAPON",
     "A bar altercation over a bill dispute escalates when one party produces a knife, inflicting injury before being restrained by staff and other patrons.",
     "Commercial", "Night", "Knife", 1),
    ("MO-INTIM-001", "CRIM-INTIMIDATION",
     "A tenant refusing to vacate a rented property receives repeated threatening calls and a visit from associates of the landlord warning of consequences if the property is not vacated by a set date.",
     "Residential", "Variable", "Mobile phone", 2),
    ("MO-INTIM-002", "CRIM-INTIMIDATION",
     "A witness in an ongoing case is approached outside their workplace and warned against testifying, with a vague reference to harm coming to their family if they proceed.",
     "Person", "Evening", "None", 2),
    ("MO-KIDNAP-001", "KIDNAPPING",
     "A child walking home from school alone is lured into a vehicle with the promise of sweets or a lift, the vehicle then driving out of the immediate neighbourhood before the abduction is noticed.",
     "Person", "Business_Hours", "Vehicle", 1),
    ("MO-KIDNAP-002", "ABDUCTION",
     "A woman is forced into a vehicle by a former partner or rejected suitor waiting near her regular commute route, driven to a secluded location to pressure her into resuming the relationship.",
     "Person", "Evening", "Vehicle", 2),
    ("MO-SEX-001", "SEXUAL-HARASSMENT",
     "A woman commuting on a crowded bus or train is subjected to unwanted physical contact by a fellow passenger who positions himself close during peak-hour crowding, denying intent if confronted.",
     "Person", "Business_Hours", "None", 1),
    ("MO-SEX-002", "STALKING",
     "A woman is repeatedly followed to her workplace and home over several weeks by the same individual, who also sends unwanted messages and shows up uninvited at social gatherings she attends.",
     "Person", "Variable", "Mobile phone", 1),
    ("MO-SEX-003", "VOYEURISM",
     "A hidden camera is installed in a changing room or paying-guest bathroom by someone with authorised access to the premises, footage later found on a device seized during an unrelated search.",
     "Residential", "Variable", "Hidden camera", 1),
    ("MO-PUBORD-001", "UNLAWFUL-ASSEMBLY",
     "A crowd gathers rapidly at a contested religious or political event following a rumour circulated on social media, blocking a public road until dispersed by police intervention.",
     "Person", "Evening", "None", 5),
    ("MO-PUBORD-002", "RIOTING",
     "A dispute at a local festival between two groups escalates into stone-throwing and property damage along the procession route, requiring police to intervene to restore order.",
     "Person", "Evening", "Stones", 5),
    ("MO-PUBORD-003", "MISCHIEF-PROPERTY",
     "Parked vehicles along a street are vandalised overnight — tyres slashed, windshields cracked — apparently at random, with no items taken, consistent with a personal grudge or intoxicated act.",
     "Vehicle", "Night", "Sharp object", 1),
    ("MO-NARC-001", "NARCOTICS-POSSESSION",
     "Small quantities of a controlled substance are carried in a concealed pouch for personal use, discovered during a routine vehicle check at a highway checkpoint.",
     "Vehicle", "Night", "None", 1),
    ("MO-NARC-002", "NARCOTICS-TRAFFIC",
     "A courier transports a concealed consignment across district lines using a passenger bus, coordinating pickup and delivery locations via encrypted messaging to avoid direct contact with the source.",
     "Vehicle", "Variable", "Concealed packaging", 2),
    ("MO-THEFT-008", "THEFT-GENERAL",
     "Cash offerings left in a temple donation box are removed using a wire hook inserted through the collection slot, timed for a lull between visiting hours when the box is unattended.",
     "Temple", "Early_Morning", "Wire hook", 1),
    ("MO-THEFT-009", "THEFT-GENERAL",
     "Luggage left momentarily unattended at a bus or railway station is picked up by an offender posing as a fellow traveller offering to help, who then walks off with the bag.",
     "Person", "Variable", "None", 1),
    ("MO-THEFT-010", "THEFT-VEHICLE",
     "Delivery two-wheelers left running briefly outside a customer's gate during a drop-off are driven away by an opportunist waiting nearby, the theft taking under thirty seconds.",
     "Vehicle", "Business_Hours", "None", 1),
    ("MO-THEFT-012", "THEFT-VEHICLE",
     "High-end bicycles left outside a gym or cafe secured only with a cable lock are cut with pliers during a brief window while the owner is inside.",
     "Vehicle", "Evening", "Pliers", 1),
    ("MO-THEFT-013", "THEFT-DWELLING",
     "A first-floor balcony grille with a gap wide enough for an arm is used to hook jewellery or a purse left near an open window, without the offender entering the house at all.",
     "Residential", "Night", "Hook/rod", 1),
    ("MO-THEFT-014", "THEFT-PICKPOCKET",
     "A crowded local train compartment during the morning rush is used to lift wallets from back pockets, the offender exiting at the very next stop regardless of their intended destination.",
     "Person", "Early_Morning", "None", 1),
    ("MO-THEFT-015", "THEFT-SERVANT",
     "A driver entrusted with a company vehicle for official errands siphons fuel by under-reporting the odometer reading, selling the diverted fuel to a roadside contact.",
     "Vehicle", "Business_Hours", "None", 1),
    ("MO-SNATCH-003", "SNATCHING-GENERAL",
     "A laptop bag on the front seat of a car stopped at a signal is grabbed through a partially open window by an offender on foot who disappears into roadside traffic.",
     "Vehicle", "Business_Hours", "None", 1),
    ("MO-SNATCH-004", "SNATCHING-CHAIN",
     "An elderly woman walking to a morning market is targeted for a chain snatch by a lone offender on a bicycle, chosen specifically for reduced likelihood of pursuit.",
     "Person", "Early_Morning", "Bicycle", 1),
    ("MO-ROB-007", "ROBBERY",
     "A cab driver on a late-night airport run is robbed by passengers who booked the ride specifically for this purpose, overpowering him a few kilometres from the pickup point.",
     "Vehicle", "Night", "Blunt weapon", 2),
    ("MO-ROB-008", "ROBBERY-AGGRAVATED",
     "A jewellery courier travelling by public transport is followed from the wholesale market and robbed at a quieter interchange point along the route, the offenders having tracked the pickup in advance.",
     "Person", "Business_Hours", "Knife", 3),
    ("MO-ROB-009", "DACOITY",
     "A bank cash-in-transit van is intercepted on a rural stretch by a group blocking the road with a stalled vehicle, overpowering the guards before the escort vehicle can respond.",
     "Vehicle", "Business_Hours", "Firearms", 6),
    ("MO-BURG-005", "HOUSE-BREAKING",
     "A house under renovation with material stored on-site overnight is broken into by removing loosely fitted temporary doors, the offenders targeting fittings and wiring for scrap value.",
     "Residential", "Night", "None", 2),
    ("MO-BURG-006", "HOUSE-BREAKING-NIGHT",
     "An ATM kiosk's shutter lock is cut after midnight and the machine itself pried open with a gas cutter, the operation timed to be complete before the next patrol pass.",
     "ATM", "Night", "Gas cutter", 3),
    ("MO-BURG-007", "CRIMINAL-TRESPASS",
     "A locked seasonal farmhouse is entered through a rear window during the off-season, with furniture and fittings stripped out over multiple visits before the owner's next inspection.",
     "Residential", "Variable", "Crowbar", 2),
    ("MO-CHEAT-004", "CHEATING-FRAUD",
     "A fraudulent job placement agency collects registration fees from jobseekers for positions that do not exist, operating out of a rented office that is vacated once complaints begin.",
     "Commercial", "Business_Hours", "None", 2),
    ("MO-CHEAT-005", "CHEATING-FRAUD",
     "A caller impersonating a relative in distress requests urgent funds transfer for a medical emergency, pressuring the victim to act before they can verify the claim independently.",
     "Person", "Variable", "Mobile phone", 1),
    ("MO-CHEAT-006", "CHEATING-PERSONATION",
     "An offender impersonates a courier delivery agent to collect a cash-on-delivery payment for a parcel that was never actually dispatched by the seller.",
     "Residential", "Business_Hours", "Fake uniform", 1),
    ("MO-CYBER-003", "CYBER-FRAUD",
     "A fake customer-care number found through a manipulated search result is called by the victim, who is then talked through installing a remote-access app that exposes their banking session.",
     "Person", "Business_Hours", "Remote access app", 1),
    ("MO-CYBER-004", "CYBER-IDENTITY-THEFT",
     "Personal details harvested from a data breach are used to open a fraudulent loan account in the victim's name, the funds withdrawn before the first repayment notice alerts the real account holder.",
     "Person", "Variable", "Stolen personal data", 1),
    ("MO-TRUST-002", "BREACH-OF-TRUST",
     "A chit-fund organiser collects monthly contributions from a group of subscribers and stops disbursing payouts once a critical mass of collections has been reached, disappearing shortly after.",
     "Commercial", "Business_Hours", "None", 1),
    ("MO-FORGE-003", "FORGERY",
     "Educational certificates are forged and sold to candidates seeking government job eligibility, the documents convincing enough to pass an initial verification check.",
     "Commercial", "Business_Hours", "Forged certificates", 1),
    ("MO-COUNTFEIT-02", "COUNTERFEIT-CURRENCY",
     "Counterfeit notes printed on a home inkjet setup are passed in small denominations at fuel stations and toll booths where transaction volume discourages close inspection.",
     "Commercial", "Night", "Printer/counterfeit notes", 1),
    ("MO-STOLEN-002", "RECEIVING-STOLEN",
     "An online marketplace listing at a suspiciously low price is used to move a stolen laptop or phone quickly to a buyer who does not ask for proof of ownership.",
     "Person", "Variable", "Online marketplace", 1),
    ("MO-ASSAULT-002", "ASSAULT",
     "A confrontation outside a bar at closing time between two groups of patrons escalates into a brief physical exchange, typically broken up by security before serious injury occurs.",
     "Commercial", "Night", "None", 4),
    ("MO-HURT-004", "HURT-SIMPLE",
     "A workplace dispute over unpaid wages between a contractor and daily-wage labourers turns physical when the contractor refuses to pay, resulting in minor injuries to both sides.",
     "Commercial", "Business_Hours", "None", 3),
    ("MO-HURT-005", "HURT-GRIEVOUS",
     "A road-rage incident following a minor collision escalates when one driver retrieves a weapon from their vehicle and attacks the other before bystanders separate them.",
     "Vehicle", "Business_Hours", "Rod", 1),
    ("MO-INTIM-003", "CRIM-INTIMIDATION",
     "A local moneylender's collection agent visits a defaulting borrower's home repeatedly, making veiled threats about consequences for the family if the debt is not settled quickly.",
     "Residential", "Evening", "None", 2),
    ("MO-KIDNAP-003", "KIDNAPPING",
     "A custody dispute results in one parent taking the child from school without the other parent's or the custodial arrangement's consent, driving out of the city the same day.",
     "Person", "Business_Hours", "Vehicle", 1),
    ("MO-KIDNAP-004", "ABDUCTION",
     "A young couple eloping against family wishes is intercepted by relatives who forcibly separate them, with the woman later reporting she was confined against her will.",
     "Person", "Variable", "Vehicle", 3),
    ("MO-SEX-004", "SEXUAL-HARASSMENT",
     "A woman receives repeated unwanted comments and physical proximity from a colleague at the workplace despite having previously objected, escalating over several weeks.",
     "Commercial", "Business_Hours", "None", 1),
    ("MO-SEX-005", "RAPE",
     "An acquaintance offers to drop the victim home late at night but instead diverts to a secluded location, exploiting the victim's trust and the absence of witnesses.",
     "Person", "Night", "Vehicle", 1),
    ("MO-PUBORD-004", "DEFAMATION",
     "False allegations about a business rival's conduct are circulated in a local community WhatsApp group, damaging the rival's reputation before the origin of the claim is traced.",
     "Person", "Variable", "Mobile phone", 1),
    ("MO-PUBORD-005", "PUBLIC-NUISANCE",
     "Loudspeakers at a private event run well past permitted hours despite repeated requests from neighbours to stop, prompting a formal noise-complaint report.",
     "Residential", "Night", "Loudspeaker", 1),
    ("MO-NARC-003", "NARCOTICS-POSSESSION",
     "A college-area peddler sells small pre-packaged quantities near a campus gate during the evening rush, switching locations every few days to avoid a fixed pattern.",
     "Person", "Evening", "None", 1),
]


def load_mo_codes() -> None:
    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for mo_code_id, crime_type_id, description, target_type, time_pattern, tool_used, gang_size in MO_CODES:
                cur.execute(
                    """
                    INSERT INTO mo_codes
                        (mo_code_id, crime_type_id, mo_description, mo_description_kn,
                         target_type, time_pattern, tool_used, typical_gang_size)
                    VALUES (%s, %s, %s, NULL, %s, %s, %s, %s)
                    ON CONFLICT (mo_code_id) DO NOTHING
                    """,
                    (mo_code_id, crime_type_id, description, target_type, time_pattern, tool_used, gang_size),
                )
                inserted += 1
        conn.commit()
    print(f"loaded {inserted} mo_codes rows (mo_description_kn deferred to batched Kannada pass)")


# ============================================================
# officers (SEED_RUNBOOK.md §5) — 100 rows, active units only, realistic
# rank pyramid (many Constable/Head_Constable, few DSP+). The mandatory
# demo IO — KSP-23417, PSI Harish Gowda, station KA-MYS-012 — is inserted
# explicitly first, not generated, since Thread A depends on this exact
# officer_id/name/station triple (§8).
#
# `rank` is the real police hierarchy; `role` is the separate, closed
# 6-value organisational-role enum the schema defines (IO/SHO/
# Circle_Inspector/Supervisor/Analyst/Admin) — every officer needs a role
# from that fixed set even though most of the roster (Constables, Head
# Constables) wouldn't independently hold IO duty in real KSP procedure.
# Names use a Karnataka first-name/surname pool per §7.2 — deliberately
# excludes "Savitha" and "Prakash Jadhav" entirely (the former is Thread B's
# complainant name, the latter the §7.5 reserved registry entry) so no
# generated officer can be confused with either.
# ============================================================

FIRST_NAMES_M = [
    "Ravi", "Suresh", "Ramesh", "Manjunath", "Naveen", "Kiran", "Anil", "Sunil",
    "Vijay", "Ganesh", "Mahesh", "Nagaraj", "Basavaraj", "Shivakumar", "Venkatesh",
    "Srinivas", "Girish", "Dinesh", "Yogesh", "Santosh", "Raju", "Siddharth",
    "Arun", "Vinod", "Gopal", "Chandrashekar", "Ashok", "Prasad", "Ravindra", "Umesh",
]
FIRST_NAMES_F = [
    "Lakshmi", "Radha", "Geetha", "Sunitha", "Shobha", "Vani", "Pushpa", "Kavitha",
    "Nandini", "Deepa", "Sowmya", "Anitha", "Rekha", "Jayanthi", "Vasanthi",
    "Shailaja", "Manjula", "Roopa", "Sudha", "Bhagya",
]
SURNAMES = [
    "Gowda", "Naik", "Rao", "Kumar", "Reddy", "Shetty", "Hegde", "Bhat", "Iyer",
    "Murthy", "Patil", "Nayak", "Poojary", "Kamath", "N", "S", "K", "M", "HS", "BM",
]

# rank -> (rank_code, weight in the 100-officer pyramid, min rank tier for role eligibility)
RANK_PYRAMID = [
    ("Constable", "PC", 28),
    ("Head Constable", "HC", 24),
    ("Assistant Sub-Inspector", "ASI", 15),
    ("Sub-Inspector", "SI", 14),
    ("Police Inspector", "PI", 10),
    ("Deputy Superintendent of Police", "DSP", 5),
    ("Superintendent of Police", "SP", 2),
    ("Deputy Inspector General", "DIG", 1),
    ("Inspector General", "IG", 1),
]
RANK_TIER = {code: i for i, (_, code, _) in enumerate(RANK_PYRAMID)}  # 0=lowest


def _build_officer_roster(seed: int = 42) -> list[dict]:
    import random

    rng = random.Random(seed)

    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT station_id, district_id FROM police_stations "
                "WHERE district_id = ANY(%s)",
                (["BLR", "MYS", "MDY", "HBL", "MNG", "BGV", "TMK", "KDG", "CKM", "RCH"],),
            )
            active_stations = cur.fetchall()

    ranks_pool = []
    for rank, code, weight in RANK_PYRAMID:
        ranks_pool.extend([(rank, code)] * weight)
    rng.shuffle(ranks_pool)

    roster = [
        {
            "officer_id": "KSP-23417",
            "name": "Harish Gowda",
            "rank": "Police Sub-Inspector", "rank_code": "PSI",
            "station_id": "KA-MYS-012", "district_id": "MYS",
            "role": "IO", "date_of_joining": "2016-06-01",
        }
    ]
    used_ids = {"KSP-23417"}

    # Remaining 99 officers, spread across active-unit stations.
    for i in range(99):
        rank, rank_code = ranks_pool[i % len(ranks_pool)]
        station_id, district_id = rng.choice(active_stations)
        tier = RANK_TIER[rank_code]
        if tier >= RANK_TIER["DSP"]:
            role = "Supervisor"
        elif tier >= RANK_TIER["PI"]:
            role = rng.choice(["SHO", "Circle_Inspector", "IO"])
        else:
            role = "IO"
        first = rng.choice(FIRST_NAMES_M if rng.random() < 0.75 else FIRST_NAMES_F)
        name = f"{first} {rng.choice(SURNAMES)}"

        officer_id = f"KSP-{rng.randint(10000, 99999)}"
        while officer_id in used_ids:
            officer_id = f"KSP-{rng.randint(10000, 99999)}"
        used_ids.add(officer_id)

        roster.append({
            "officer_id": officer_id, "name": name,
            "rank": rank, "rank_code": rank_code,
            "station_id": station_id, "district_id": district_id,
            "role": role,
            "date_of_joining": f"{rng.randint(1998, 2023)}-{rng.randint(1,12):02d}-01",
        })

    # Reassign a small number of the highest-tier officers to Analyst/Admin
    # roles so all 6 role values are represented (needed for the 4 demo
    # logins to have realistic peers, and for role-coverage generally).
    high_tier = [o for o in roster[1:] if RANK_TIER[o.get("rank_code", "PC")] >= RANK_TIER["SI"]]
    for o in rng.sample(high_tier, min(3, len(high_tier))):
        o["role"] = "Analyst"
    for o in rng.sample([o for o in high_tier if o["role"] != "Analyst"], min(1, len(high_tier))):
        o["role"] = "Admin"

    return roster


def load_officers() -> None:
    roster = _build_officer_roster()
    inserted = 0
    with connect() as conn:
        with conn.cursor() as cur:
            for o in roster:
                cur.execute(
                    """
                    INSERT INTO officers
                        (officer_id, name, name_kn, rank, rank_code, station_id, district_id,
                         role, date_of_joining, is_active)
                    VALUES (%s, %s, NULL, %s, %s, %s, %s, %s, %s, TRUE)
                    ON CONFLICT (officer_id) DO NOTHING
                    """,
                    (
                        o["officer_id"], o["name"], o["rank"], o["rank_code"],
                        o["station_id"], o["district_id"], o["role"], o["date_of_joining"],
                    ),
                )
                inserted += 1
        conn.commit()
    print(f"loaded {inserted} officers rows (name_kn deferred to batched Kannada pass)")


if __name__ == "__main__":
    import sys

    if "--bns-sections" in sys.argv or "--all" in sys.argv:
        load_bns_sections()
    if "--district-socioeconomic" in sys.argv or "--all" in sys.argv:
        load_district_socioeconomic()
    if "--crime-types" in sys.argv or "--all" in sys.argv:
        load_crime_types()
    if "--mo-codes" in sys.argv or "--all" in sys.argv:
        load_mo_codes()
    if "--officers" in sys.argv or "--all" in sys.argv:
        load_officers()

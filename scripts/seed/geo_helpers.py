"""Thread-agnostic geo + deterministic-value helpers, shared across the
golden threads (A/B/C) and the background corpus generator (SEED_RUNBOOK.md
§6.2). Split out of 03_synthetic.py during the Thread A narrative-quality
retrofit so Thread B/C and background don't reimplement locality resolution,
bearing/distance math, or reproducible-without-RNG-replay value picks.
"""

from __future__ import annotations

import hashlib
import math

EARTH_RADIUS_KM = 6371.0088

COMPASS_POINTS = [
    "North", "North-East", "East", "South-East",
    "South", "South-West", "West", "North-West",
]


def resolve_locality(
    cur, lat: float, lon: float, named_localities: dict[str, str], threshold_m: float = 500.0
) -> tuple[str, str]:
    """Resolve an incident point to a locality_id + locality_name.

    `named_localities` maps a thread's own hand-authored corridor/cluster
    locality names to (center_lat, center_lon, locality_id) — checked first
    since golden-thread points are deliberately jittered close to these
    centers. Falls back to nearest-match against the full `localities` table
    via its centroid GiST index for points outside every named locality
    (e.g. Thread A's scattered MDY/BLR incidents).
    """
    for name, (center_lat, center_lon, locality_id) in named_localities.items():
        distance_km, _ = bearing_distance(lat, lon, center_lat, center_lon)
        if distance_km * 1000 <= threshold_m:
            return locality_id, name

    cur.execute(
        """
        SELECT locality_id, locality_name
        FROM localities
        ORDER BY centroid <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
        LIMIT 1
        """,
        (lon, lat),
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("resolve_locality: no localities rows exist to nearest-match against")
    return row[0], row[1]


def bearing_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, str]:
    """Great-circle distance (km, haversine) and compass bearing (point 2
    relative to point 1, bucketed to 8-point compass) between two points.

    Used for `firs.direction_distance_from_ps` — a genuinely computed value
    from the station's real coordinates to the incident point, not a
    fabricated string (SEED_RUNBOOK.md §3 D1 / FORM IF-1 item 5(a)).
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    distance_km = 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))

    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    bearing_deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    compass = COMPASS_POINTS[round(bearing_deg / 45) % 8]

    return distance_km, compass


def format_direction_distance(distance_km: float, compass: str) -> str:
    """'2.3 km South-East' style string for direction_distance_from_ps."""
    return f"{distance_km:.1f} km {compass}"


def _stable_unit_float(seed_key: str) -> float:
    """Deterministic float in [0, 1) from a string key — same technique as
    narrative_gen._should_populate_kn(), reused here so retrofit/UPDATE-only
    scripts can reproduce "random" values without replaying the original
    generation run's exact RNG call order.
    """
    digest = hashlib.sha256(seed_key.encode()).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


def deterministic_draw(seed_key: str, low: float, high: float) -> float:
    """Deterministic value in [low, high), keyed by seed_key."""
    return low + _stable_unit_float(seed_key) * (high - low)


def deterministic_int(seed_key: str, low: int, high: int) -> int:
    """Deterministic integer in [low, high] inclusive, keyed by seed_key."""
    return low + int(_stable_unit_float(seed_key) * (high - low + 1))


def deterministic_choice(seed_key: str, options: list):
    """Deterministic pick from options, keyed by seed_key."""
    if not options:
        raise ValueError("deterministic_choice: options must be non-empty")
    idx = int(_stable_unit_float(seed_key) * len(options))
    return options[min(idx, len(options) - 1)]


def deterministic_weighted_choice(seed_key: str, options: list[tuple], ) -> object:
    """Deterministic weighted pick. `options` is a list of (value, weight)
    pairs, e.g. [("Oral", 0.65), ("Written", 0.35)].
    """
    total = sum(w for _, w in options)
    r = _stable_unit_float(seed_key) * total
    upto = 0.0
    for value, weight in options:
        upto += weight
        if r <= upto:
            return value
    return options[-1][0]

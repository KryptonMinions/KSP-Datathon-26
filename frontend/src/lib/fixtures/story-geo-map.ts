import type { ChatMessage } from "@/lib/types/content-blocks";

/**
 * Geospatial demo beat — theft FIRs within 500 m of MG Road police station in
 * the last 3 months. Coords are real-ish Bengaluru (MG Road ≈ 12.9756, 77.6068),
 * FIR markers jittered inside the ring, dates within Apr–Jul 2026 relative to the
 * project date. Mirrors story4-network.ts's shape; every marker is FIR-cited.
 */
const STATION = { lat: 12.9756, lng: 77.6068 };

export const storyGeoResponse: ChatMessage = {
  id: "story-geo-response",
  role: "assistant",
  timestamp: new Date().toISOString(),
  text: "6 theft FIRs found within 500 m of MG Road PS in the last 3 months — every marker is FIR-cited.",
  blocks: [
    {
      id: "story-geo-map",
      type: "map",
      title: "Theft FIRs · within 500 m of MG Road PS · last 3 months",
      center: STATION,
      zoom: 15,
      radius: {
        centerLat: STATION.lat,
        centerLng: STATION.lng,
        radiusMeters: 500,
        label: "500 m of MG Road PS",
      },
      markers: [
        {
          id: "marker-station",
          lat: STATION.lat,
          lng: STATION.lng,
          kind: "station",
          label: "MG Road Police Station",
        },
        {
          id: "marker-fir-1",
          lat: 12.9772,
          lng: 77.6081,
          kind: "fir",
          label: "KA-BLR-021-2026-0517",
          firId: "KA-BLR-021-2026-0517",
          offence: "Theft — IPC 379",
          date: "2026-04-18",
          status: "Under investigation",
        },
        {
          id: "marker-fir-2",
          lat: 12.9741,
          lng: 77.6049,
          kind: "fir",
          label: "KA-BLR-021-2026-0563",
          firId: "KA-BLR-021-2026-0563",
          offence: "Theft — IPC 379",
          date: "2026-05-02",
          status: "Chargesheet filed",
        },
        {
          id: "marker-fir-3",
          lat: 12.9769,
          lng: 77.6042,
          kind: "fir",
          label: "KA-BLR-021-2026-0604",
          firId: "KA-BLR-021-2026-0604",
          offence: "Theft — IPC 379",
          date: "2026-05-27",
          status: "Under investigation",
        },
        {
          id: "marker-fir-4",
          lat: 12.9738,
          lng: 77.6088,
          kind: "fir",
          label: "KA-BLR-021-2026-0651",
          firId: "KA-BLR-021-2026-0651",
          offence: "Theft (two-wheeler) — IPC 379",
          date: "2026-06-11",
          status: "Accused arrested",
        },
        {
          id: "marker-fir-5",
          lat: 12.9781,
          lng: 77.6063,
          kind: "fir",
          label: "KA-BLR-021-2026-0698",
          firId: "KA-BLR-021-2026-0698",
          offence: "Theft — IPC 379",
          date: "2026-06-29",
          status: "Under investigation",
        },
        {
          id: "marker-fir-6",
          lat: 12.9749,
          lng: 77.6071,
          kind: "fir",
          label: "KA-BLR-021-2026-0725",
          firId: "KA-BLR-021-2026-0725",
          offence: "Theft (mobile phone) — IPC 379",
          date: "2026-07-07",
          status: "Under investigation",
        },
      ],
      citations: [
        { level: "fir", firId: "KA-BLR-021-2026-0517", label: "KA-BLR-021-2026-0517" },
        { level: "fir", firId: "KA-BLR-021-2026-0563", label: "KA-BLR-021-2026-0563" },
        { level: "fir", firId: "KA-BLR-021-2026-0604", label: "KA-BLR-021-2026-0604" },
        { level: "fir", firId: "KA-BLR-021-2026-0651", label: "KA-BLR-021-2026-0651" },
        { level: "fir", firId: "KA-BLR-021-2026-0698", label: "KA-BLR-021-2026-0698" },
        { level: "fir", firId: "KA-BLR-021-2026-0725", label: "KA-BLR-021-2026-0725" },
      ],
    },
  ],
};

export const STORY_GEO_QUERY =
  "show all theft firs filed within 500 meters of mg road police station in the last 3 months";

"use client";

import { useMemo } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, Circle, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type {
  MapBlock as MapBlockType,
  MapMarkerKind,
} from "@/lib/types/content-blocks";
import { CitationChip } from "@/components/shared/CitationChip";

/**
 * Marker palette shares NetworkGraphBlock's KIND_COLOR language — navy for
 * primary entities, gold for the anchor (here the station), grey otherwise.
 */
const KIND_COLOR: Record<MapMarkerKind, string> = {
  fir: "#28406b",
  station: "#b8934a",
  hotspot: "#6b7280",
};

/**
 * Leaflet's default marker PNGs 404 under bundlers, so we render each marker as
 * a colored divIcon keyed on its kind instead of relying on the default asset.
 */
function iconFor(kind: MapMarkerKind): L.DivIcon {
  const color = KIND_COLOR[kind];
  const size = kind === "station" ? 18 : 14;
  return L.divIcon({
    className: "",
    html: `<span style="display:block;width:${size}px;height:${size}px;border-radius:9999px;background:${color};border:2px solid #ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.4)"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

/**
 * The react-leaflet subtree. Imported by MapBlock via next/dynamic with
 * `ssr: false` because Leaflet touches `window`/`document` at module load.
 */
export default function MapCanvas({ block }: { block: MapBlockType }) {
  const icons = useMemo(
    () => ({
      fir: iconFor("fir"),
      station: iconFor("station"),
      hotspot: iconFor("hotspot"),
    }),
    [],
  );

  return (
    <MapContainer
      center={[block.center.lat, block.center.lng]}
      zoom={block.zoom ?? 14}
      scrollWheelZoom
      style={{ width: "100%", height: "100%" }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />

      {block.radius && (
        <Circle
          center={[block.radius.centerLat, block.radius.centerLng]}
          radius={block.radius.radiusMeters}
          pathOptions={{
            color: "#b8934a",
            fillColor: "#b8934a",
            fillOpacity: 0.08,
            weight: 1.5,
          }}
        />
      )}

      {block.markers.map((m) => (
        <Marker key={m.id} position={[m.lat, m.lng]} icon={icons[m.kind]}>
          <Popup>
            <div className="space-y-1 text-xs">
              <div className="font-medium">{m.label}</div>
              {m.offence && <div>{m.offence}</div>}
              {m.date && <div className="tabular-nums">Filed: {m.date}</div>}
              {m.status && <div>{m.status}</div>}
              {m.firId && (
                <div className="pt-1">
                  <CitationChip
                    citation={{ level: "fir", firId: m.firId, label: m.firId }}
                  />
                </div>
              )}
            </div>
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}

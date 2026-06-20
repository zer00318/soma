from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


GPS_HINT_RE = re.compile(
    r"GPS\s+(?P<lat>-?\d+(?:\.\d+)?),\s*(?P<lon>-?\d+(?:\.\d+)?)(?:,\s*accuracy\s*~?(?P<accuracy>\d+)m)?",
    re.I,
)


@dataclass(frozen=True)
class PlaceCandidate:
    provider: str
    provider_place_id: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None
    metadata: dict[str, Any] | None = None


class PlaceResolver:
    """Builds text-only place records from GPS hints.

    This resolver prioritizes Apple/CoreLocation strings. Future adapters (e.g., OpenStreetMap)
    can be added as fallbacks.
    """

    @staticmethod
    def _validate_and_cast(data: dict[str, Any]) -> dict[str, Any]:
        """Ensure required fields exist and are of correct type."""
        if not all(key in data for key in ("gps_lat", "gps_lon", "accuracy_radius_meters", "place_candidate")):
            raise ValueError("Missing one or more required location fields.")
        return {
            "gps_lat": float(data["gps_lat"]),
            "gps_lon": float(data["gps_lon"]),
            "accuracy_radius_meters": float(data["accuracy_radius_meters"]),
            "place_candidate": str(data["place_candidate"]).strip(),
        }

    @classmethod
    def from_json_packet(cls, json_input: str) -> PlaceCandidate:
        import json
        data = json.loads(json_input)
        clean_data = cls._validate_and_cast(data)
        
        place_candidate_str = clean_data["place_candidate"]
        lat = clean_data["gps_lat"]
        lon = clean_data["gps_lon"]
        accuracy = clean_data["accuracy_radius_meters"]

        if not place_candidate_str:
            # TODO: Implement OpenStreetMap reverse‑geocode lookup here as fallback.
            pass

        return PlaceCandidate(
            provider="apple_core_location" if place_candidate_str else "gps",
            provider_place_id=f"apple:{lat:.4f},{lon:.4f}",
            name=place_candidate_str if place_candidate_str else f"GPS {lat:.5f}, {lon:.5f}",
            latitude=lat,
            longitude=lon,
            accuracy_m=accuracy
        )

    def from_payload(self, payload: dict[str, Any]) -> PlaceCandidate | None:
        location = payload.get("location")
        if isinstance(location, dict):
            candidate = self._from_location_dict(location)
            if candidate:
                return candidate

        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            hint = metadata.get("location_hint") or metadata.get("gps_hint")
            if isinstance(hint, str):
                candidate = self.from_hint(hint)
                if candidate:
                    return candidate

        hint = payload.get("location_hint") or payload.get("gps_hint")
        if isinstance(hint, str):
            return self.from_hint(hint)
        return None

    def from_hint(self, hint: str) -> PlaceCandidate | None:
        match = GPS_HINT_RE.search(hint)
        if not match:
            return None
        lat = float(match.group("lat"))
        lon = float(match.group("lon"))
        accuracy = float(match.group("accuracy")) if match.group("accuracy") else None
        return PlaceCandidate(
            provider="gps",
            provider_place_id=f"gps:{lat:.4f},{lon:.4f}",
            name=self._name_from_hint(hint, lat, lon),
            latitude=lat,
            longitude=lon,
            accuracy_m=accuracy,
            metadata={"raw_hint": hint},
        )

    def _from_location_dict(self, location: dict[str, Any]) -> PlaceCandidate | None:
        lat = self._float_or_none(location.get("latitude") or location.get("lat"))
        lon = self._float_or_none(location.get("longitude") or location.get("lon"))
        name = str(location.get("name") or location.get("place_name") or "").strip()
        provider = str(location.get("provider") or "gps").strip() or "gps"
        place_id = str(location.get("place_id") or location.get("provider_place_id") or "").strip()
        accuracy = self._float_or_none(location.get("accuracy_m") or location.get("accuracy"))
        if not place_id and lat is not None and lon is not None:
            place_id = f"{provider}:{lat:.4f},{lon:.4f}"
        if not name and lat is not None and lon is not None:
            name = f"GPS {lat:.5f}, {lon:.5f}"
        if not place_id or not name:
            return None
        return PlaceCandidate(
            provider=provider,
            provider_place_id=place_id,
            name=name,
            latitude=lat,
            longitude=lon,
            accuracy_m=accuracy,
            metadata={key: value for key, value in location.items() if key not in {"latitude", "lat", "longitude", "lon"}},
        )

    def _name_from_hint(self, hint: str, lat: float, lon: float) -> str:
        for separator in (" | ", "; place:", "; Place:", "; near:", "; Near:"):
            if separator in hint:
                candidate = hint.split(separator, 1)[1].strip()
                if candidate:
                    return candidate
        return f"GPS {lat:.5f}, {lon:.5f}"

    def _float_or_none(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

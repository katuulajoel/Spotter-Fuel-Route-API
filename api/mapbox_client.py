import json
from typing import Dict, Optional, Sequence, Tuple
from urllib.parse import quote

import requests
from django.conf import settings


class MapboxClientError(Exception):
    """Raised when Mapbox returns a non-successful response."""


class MapboxClient:
    BASE_URL = "https://api.mapbox.com"

    def __init__(self, access_token: Optional[str] = None):
        token = access_token or settings.MAPBOX_ACCESS_TOKEN
        if not token:
            raise MapboxClientError("MAPBOX_ACCESS_TOKEN is not configured.")
        self.access_token = token

    def geocode(self, query: str) -> Optional[Tuple[float, float]]:
        """Returns (lat, lon) for a query or None if nothing is found."""
        url = f"{self.BASE_URL}/geocoding/v5/mapbox.places/{quote(query)}.json"
        params = {"access_token": self.access_token, "limit": 1, "country": "US"}
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            raise MapboxClientError(f"Geocoding failed: {response.text}")
        data = response.json()
        features = data.get("features") or []
        if not features:
            return None
        lon, lat = features[0]["center"]
        return (lat, lon)

    def reverse_geocode(self, lat: float, lon: float, timeout: float = 5.0) -> Optional[Dict]:
        """
        Return a dict with city and state short code for a given coordinate.
        Example: {"city": "Bridgeport", "state": "MI"}
        """
        url = f"{self.BASE_URL}/geocoding/v5/mapbox.places/{lon},{lat}.json"
        params = {
            "access_token": self.access_token,
            "limit": 1,
            "types": "place,region,locality",
            "country": "US",
        }
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code != 200:
            raise MapboxClientError(f"Reverse geocoding failed: {response.text}")
        data = response.json()
        features = data.get("features") or []
        if not features:
            return None
        feature = features[0]
        city = feature.get("text")
        state = None
        for ctx in feature.get("context", []):
            if ctx.get("id", "").startswith("region.") and "short_code" in ctx:
                state_code = ctx["short_code"].split("-")[-1].upper()
                state = state_code
                break
        if not city and feature.get("place_type") == ["region"]:
            city = feature.get("text")
        if city and state:
            return {"city": city, "state": state}
        return None

    def directions(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
    ) -> Dict:
        """Fetch driving directions and return the raw Mapbox payload."""
        start_lon, start_lat = start[1], start[0]
        end_lon, end_lat = end[1], end[0]
        coords = f"{start_lon},{start_lat};{end_lon},{end_lat}"
        url = f"{self.BASE_URL}/directions/v5/mapbox/driving/{coords}"
        params = {
            "access_token": self.access_token,
            "geometries": "geojson",
            "overview": "full",
            "steps": "true",
            "annotations": "distance,duration",
        }
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            raise MapboxClientError(f"Directions failed: {response.text}")
        payload = response.json()
        if not payload.get("routes"):
            raise MapboxClientError("No routes returned by Mapbox.")
        return payload["routes"][0]

    def _downsample(self, coordinates: Sequence[Sequence[float]], max_points: int = 200):
        if len(coordinates) <= max_points:
            return list(coordinates)
        step = max(1, len(coordinates) // max_points)
        reduced = list(coordinates[::step])
        if reduced[-1] != coordinates[-1]:
            reduced.append(coordinates[-1])
        return reduced

    def _encode_polyline(self, coordinates: Sequence[Sequence[float]]) -> str:
        """
        Encode a list of [lon, lat] coords into a polyline string (lat, lon order).
        """
        def _encode(value: int) -> str:
            value = ~(value << 1) if value < 0 else value << 1
            chunks = []
            while value >= 0x20:
                chunks.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            chunks.append(chr(value + 63))
            return "".join(chunks)

        output = []
        prev_lat = prev_lon = 0
        for lon, lat in coordinates:
            lat_i = int(round(lat * 1e5))
            lon_i = int(round(lon * 1e5))
            output.append(_encode(lat_i - prev_lat))
            output.append(_encode(lon_i - prev_lon))
            prev_lat, prev_lon = lat_i, lon_i
        return "".join(output)

    def build_static_map_url(
        self,
        geometry: Dict,
        stop_points: Optional[Sequence[Tuple[float, float]]] = None,
        start_point: Optional[Tuple[float, float]] = None,
        end_point: Optional[Tuple[float, float]] = None,
        width: int = 800,
        height: int = 400,
    ) -> str:
        """Return a Mapbox static map URL with the route and stops drawn."""
        coords = geometry.get("coordinates") or []
        downsampled = self._downsample(coords, max_points=180)
        encoded = self._encode_polyline(downsampled)
        path_overlay = f"path-4+0066ff-0.7({quote(encoded, safe='')})"

        pin_overlays = []
        if start_point:
            s_lat, s_lon = start_point
            pin_overlays.append(f"pin-s-a+00aa55({s_lon},{s_lat})")
        if end_point:
            e_lat, e_lon = end_point
            pin_overlays.append(f"pin-s-b+111111({e_lon},{e_lat})")
        if stop_points:
            for lat, lon in stop_points:
                pin_overlays.append(f"pin-s+f44({lon},{lat})")

        overlay = ",".join([path_overlay, *pin_overlays])
        return (
            f"{self.BASE_URL}/styles/v1/mapbox/streets-v12/static/"
            f"{overlay}/auto/{width}x{height}"
            f"?access_token={self.access_token}"
        )

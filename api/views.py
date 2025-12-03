import json
from typing import Any, Dict, Tuple

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from .fuel_data import load_fuel_stations, index_by_city_state, index_by_state
from .fuel_optimizer import FuelPlanner
from .mapbox_client import MapboxClient, MapboxClientError
from .station_locator import StationLocator
import math


def _filter_stations_by_bbox(stations, coordinates, margin_miles: float = 100.0):
    if not coordinates:
        return stations
    lats = [lat for _, lat in coordinates]
    lons = [lon for lon, _ in coordinates]
    min_lat, max_lat = min(lats), max(lats)
    min_lon, max_lon = min(lons), max(lons)
    mid_lat = (min_lat + max_lat) / 2
    lat_margin = margin_miles / 69.0
    lon_margin = margin_miles / (69.0 * max(math.cos(math.radians(mid_lat)), 0.1))
    lo_lat = min_lat - lat_margin
    hi_lat = max_lat + lat_margin
    lo_lon = min_lon - lon_margin
    hi_lon = max_lon + lon_margin
    return [
        s
        for s in stations
        if s.coordinates
        and lo_lat <= s.coordinates[0] <= hi_lat
        and lo_lon <= s.coordinates[1] <= hi_lon
        or not s.coordinates  # keep if unknown; may geocode into range
    ]


def _parse_location(value: Any, mapbox: MapboxClient) -> Tuple[float, float]:
    """
    Accepts:
    - {"lat": 40.1, "lon": -73.9}
    - [lat, lon]
    - "lat,lon"
    - free-form address (geocoded via Mapbox)
    Returns (lat, lon).
    """
    if value is None:
        raise ValueError("Location is required.")
    if isinstance(value, dict) and "lat" in value and "lon" in value:
        return float(value["lat"]), float(value["lon"])
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return float(value[0]), float(value[1])
    if isinstance(value, str) and "," in value:
        lat, lon = value.split(",", 1)
        try:
            return float(lat.strip()), float(lon.strip())
        except ValueError:
            # If not numeric, treat as a free-form address.
            pass
    coords = mapbox.geocode(str(value))
    if coords:
        return coords
    raise ValueError(f"Could not geocode location: {value}")


@method_decorator(csrf_exempt, name="dispatch")
class RoutePlanningView(View):
    def post(self, request):
        try:
            payload = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)

        start_raw = payload.get("start")
        end_raw = payload.get("end")
        allow_station_geocoding = True
        vehicle_range = float(payload.get("range_miles", settings.DEFAULT_RANGE_MILES))
        mpg = float(payload.get("mpg", settings.DEFAULT_MPG))
        radius = float(payload.get("station_radius_miles", 50))
        geocode_budget = int(payload.get("geocode_budget_per_stop", 50))
        use_reverse_geocoding = True

        if not start_raw or not end_raw:
            return JsonResponse({"error": "Both 'start' and 'end' are required."}, status=400)

        try:
            mapbox = MapboxClient()
            start = _parse_location(start_raw, mapbox)
            end = _parse_location(end_raw, mapbox)
        except (ValueError, MapboxClientError) as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        try:
            route = mapbox.directions(start, end)
        except MapboxClientError as exc:
            return JsonResponse({"error": str(exc)}, status=502)

        geometry = route["geometry"]
        route_distance_miles = route["distance"] / 1609.344
        stations = load_fuel_stations()
        stations = _filter_stations_by_bbox(
            stations, geometry.get("coordinates", []), margin_miles=radius + 100
        )
        station_index = index_by_city_state(stations)
        state_index = index_by_state(stations)
        locator = StationLocator(
            stations,
            mapbox,
            city_state_index=station_index,
            state_index=state_index,
        )
        planner = FuelPlanner(
            locator=locator,
            mapbox_client=mapbox,
            route_geometry=geometry,
            vehicle_range_miles=vehicle_range,
            mpg=mpg,
            search_radius_miles=radius,
            geocode_budget_per_stop=geocode_budget,
            explicit_distance_miles=route_distance_miles,
            use_reverse_geocoding=use_reverse_geocoding,
        )
        stops = planner.plan_stops(allow_station_geocoding=allow_station_geocoding)
        summary = planner.cost_breakdown(stops)

        stop_points = [
            (stop.station.coordinates[0], stop.station.coordinates[1])
            if stop.station and stop.station.coordinates
            else stop.route_coordinate
            for stop in stops
        ]
        static_map_url = mapbox.build_static_map_url(
            geometry,
            stop_points=stop_points,
            start_point=start,
            end_point=end,
        )

        response: Dict[str, Any] = {
            "route": {
                "distance_miles": round(route_distance_miles, 2),
                "duration_minutes": round(route["duration"] / 60, 2),
                "geometry": geometry,
                "static_map_url": static_map_url,
            },
            "fuel_plan": {
                "stops": planner.stops_with_metadata(stops),
                "summary": summary,
                "vehicle_range_miles": vehicle_range,
                "mpg": mpg,
                "station_radius_miles": radius,
                "allow_station_geocoding": allow_station_geocoding,
            },
        }
        return JsonResponse(response, status=200)

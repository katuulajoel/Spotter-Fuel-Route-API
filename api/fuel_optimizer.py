from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .geometry import accumulate_distances_miles, interpolate_point, nearest_point_distance_miles, downsample_polyline
from .fuel_data import FuelStation
from .station_locator import StationLocator
from .mapbox_client import MapboxClient
import math


@dataclass
class FuelStop:
    mile_marker: float
    route_coordinate: Tuple[float, float]
    station: Optional[FuelStation]
    price_per_gallon: Optional[float]
    note: Optional[str] = None


def build_mile_markers(distance_miles: float, range_miles: float) -> List[float]:
    markers = [0.0]
    if distance_miles <= 0:
        return markers
    mile = range_miles
    while mile < distance_miles:
        markers.append(round(mile, 2))
        mile += range_miles
    markers.append(round(distance_miles, 2))
    return markers


class FuelPlanner:
    def __init__(
        self,
        locator: StationLocator,
        mapbox_client: MapboxClient,
        route_geometry: Dict,
        vehicle_range_miles: float,
        mpg: float,
        search_radius_miles: float = 50.0,
        geocode_budget_per_stop: int = 50,
        explicit_distance_miles: Optional[float] = None,
        use_reverse_geocoding: bool = True,
    ):
        self.locator = locator
        self.mapbox = mapbox_client
        self.geometry = route_geometry
        self.vehicle_range_miles = vehicle_range_miles
        self.mpg = mpg
        self.search_radius_miles = search_radius_miles
        self.geocode_budget_per_stop = geocode_budget_per_stop
        self.use_reverse_geocoding = use_reverse_geocoding
        self._coordinates = route_geometry["coordinates"]
        self._cumulative = accumulate_distances_miles(self._coordinates)
        self._fallback_polyline = downsample_polyline(self._coordinates, max_points=400)
        self.total_distance_miles = (
            explicit_distance_miles if explicit_distance_miles is not None else self._cumulative[-1]
        )

    def _coordinate_at(self, mile_marker: float) -> Tuple[float, float]:
        return interpolate_point(self._coordinates, self._cumulative, mile_marker)

    def plan_stops(self, allow_station_geocoding: bool) -> List[FuelStop]:
        markers = build_mile_markers(self.total_distance_miles, self.vehicle_range_miles)
        stops: List[FuelStop] = []
        # We fuel at every marker except the destination.
        for mile_marker in markers[:-1]:
            coord = self._coordinate_at(mile_marker)
            candidates = []
            if self.use_reverse_geocoding:
                try:
                    city_state = self.mapbox.reverse_geocode(coord[0], coord[1])
                    print(f"[marker {mile_marker:.2f}] reverse geocode -> {city_state}")
                except Exception as exc:
                    city_state = None
                    print(f"[marker {mile_marker:.2f}] reverse geocode failed: {exc}")
                if city_state:
                    candidates = self.locator.stations_for_city_state(
                        city_state.get("city"), city_state.get("state")
                    )
                    if not candidates:
                        candidates = self.locator.stations_for_state(city_state.get("state"))
                        if candidates:
                            print(f"[marker {mile_marker:.2f}] falling back to state-only stations")

            station = self.locator.cheapest_nearby(
                coord,
                radius_miles=self.search_radius_miles,
                allow_geocode=allow_station_geocoding,
                geocode_budget=self.geocode_budget_per_stop,
                candidates=candidates,
            )
            note = None
            if station is None:
                station = self.locator.nearest_to_point(coord)
                note = "Fallback to nearest station to marker; no nearby city/state match with coords."
            if station is None:
                station = self.locator.nearest_on_route(self._fallback_polyline)
                note = note or "Fallback to nearest station along route; no nearby coordinates available."
            price = station.retail_price if station else None
            stops.append(
                FuelStop(
                    mile_marker=round(mile_marker, 2),
                    route_coordinate=coord,
                    station=station,
                    price_per_gallon=price,
                    note=note,
                )
            )
        return stops

    def cost_breakdown(self, stops: List[FuelStop]) -> Dict:
        markers = [stop.mile_marker for stop in stops]
        markers.append(self.total_distance_miles)

        segments = []
        total_cost = 0.0
        total_gallons = 0.0
        unknown_cost = False
        for idx in range(len(markers) - 1):
            start_mile = markers[idx]
            end_mile = markers[idx + 1]
            miles = end_mile - start_mile
            gallons = miles / self.mpg if self.mpg else None
            price = stops[idx].price_per_gallon if idx < len(stops) else None
            cost = None
            if gallons is not None and price is not None:
                cost = round(gallons * price, 2)
                total_gallons += gallons
                total_cost += cost
            else:
                unknown_cost = True
            segments.append(
                {
                    "from_mile": round(start_mile, 2),
                    "to_mile": round(end_mile, 2),
                    "miles": round(miles, 2),
                    "gallons_needed": gallons,
                    "price_per_gallon": price,
                    "fuel_cost": cost,
                }
            )
        trip_gallons = self.total_distance_miles / self.mpg if self.mpg else None
        return {
            "total_cost": None if unknown_cost else round(total_cost, 2),
            "gallons_needed": trip_gallons,
            "priced_gallons": round(total_gallons, 2),
            "segments": segments,
        }

    def stops_with_metadata(self, stops: List[FuelStop]) -> List[Dict]:
        serialized = []
        for stop in stops:
            serialized.append(
                {
                    "mile_marker": stop.mile_marker,
                    "route_coordinate": {
                        "lat": stop.route_coordinate[0],
                        "lon": stop.route_coordinate[1],
                    },
                    "station": None
                    if stop.station is None
                    else {
                        "name": stop.station.name,
                        "address": stop.station.address,
                        "city": stop.station.city,
                        "state": stop.station.state,
                        "retail_price": stop.station.retail_price,
                        "coordinates": {
                            "lat": stop.station.coordinates[0],
                            "lon": stop.station.coordinates[1],
                        }
                        if stop.station.coordinates
                        else None,
                    },
                    "price_per_gallon": stop.price_per_gallon,
                    "note": stop.note,
                }
            )
        return serialized

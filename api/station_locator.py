from typing import Dict, Iterable, List, Optional, Tuple

from .geometry import haversine_miles
from .mapbox_client import MapboxClient
from .fuel_data import FuelStation, StationCache, stations_sorted_by_price
from .geometry import nearest_point_distance_miles
from math import inf
from itertools import islice


class StationLocator:
    def __init__(
        self,
        stations: Iterable[FuelStation],
        cache: Optional[StationCache],
        mapbox_client: MapboxClient,
        city_state_index: Optional[Dict[str, List[FuelStation]]] = None,
        state_index: Optional[Dict[str, List[FuelStation]]] = None,
    ):
        self.stations = list(stations)
        self.sorted_by_price = stations_sorted_by_price(self.stations)
        self.city_state_index = city_state_index or {}
        self.state_index = state_index or {}
        self.cache = cache
        self.mapbox = mapbox_client
        self._session_coords: Dict[str, Tuple[float, float]] = {}

    def _ensure_coords(
        self, station: FuelStation, allow_geocode: bool = False
    ) -> Tuple[Optional[Tuple[float, float]], bool]:
        """
        Returns (coords, attempted_geocode_flag).
        """
        if station.coordinates:
            return station.coordinates, False
        if station.cache_key in self._session_coords:
            coords = self._session_coords[station.cache_key]
            station.coordinates = coords
            return coords, False
        if self.cache:
            cached = self.cache.get(station.cache_key)
            if cached:
                station.coordinates = cached
                self._session_coords[station.cache_key] = cached
                return cached, False
        if not allow_geocode:
            return None, False
        coords = self.mapbox.geocode(
            f"{station.address}, {station.city}, {station.state}, USA"
        )
        if coords:
            station.coordinates = coords
            self._session_coords[station.cache_key] = coords
            if self.cache:
                self.cache.set(station.cache_key, coords)
            return coords, True

        # Fallback: geocode city/state centroid if precise address failed.
        centroid = self.mapbox.geocode(f"{station.city}, {station.state}, USA")
        if centroid:
            station.coordinates = centroid
            self._session_coords[station.cache_key] = centroid
            if self.cache:
                self.cache.set(station.cache_key, centroid)
        return centroid, True

    def stations_for_city_state(self, city: Optional[str], state: Optional[str]) -> List[FuelStation]:
        if not city or not state:
            return []
        key = f"{city.lower().strip()}|{state.lower().strip()}"
        return self.city_state_index.get(key, [])

    def stations_for_state(self, state: Optional[str]) -> List[FuelStation]:
        if not state:
            return []
        key = state.lower().strip()
        return self.state_index.get(key, [])

    def cheapest_nearby(
        self,
        target: Tuple[float, float],
        radius_miles: float,
        allow_geocode: bool,
        geocode_budget: int,
        candidates: Optional[List[FuelStation]] = None,
    ) -> Optional[FuelStation]:
        """
        Return the cheapest station within radius_miles of the target.
        Will attempt geocoding until budget is exhausted.
        """
        budget_left = geocode_budget
        cheapest: Optional[FuelStation] = None
        pool = candidates if candidates is not None else self.sorted_by_price
        pool = stations_sorted_by_price(pool)  # ensure cheapest-first
        for station in pool:
            coords, attempted = self._ensure_coords(
                station, allow_geocode=allow_geocode and budget_left > 0
            )
            if attempted:
                budget_left -= 1
            if coords is None:
                continue
            if haversine_miles(coords, target) <= radius_miles:
                cheapest = station
                break
        if cheapest:
            return cheapest

        # Secondary fallback: try geocoding a small slice of the global cheapest
        # stations if we haven't used the budget.
        if allow_geocode and budget_left > 0:
            for station in islice(self.sorted_by_price, budget_left):
                coords, attempted = self._ensure_coords(station, allow_geocode=True)
                if not coords:
                    continue
                if haversine_miles(coords, target) <= radius_miles:
                    return station
        return None

    def cheapest_with_coords(self) -> Optional[FuelStation]:
        for station in self.sorted_by_price:
            coords, _ = self._ensure_coords(station, allow_geocode=False)
            if coords:
                return station
        return None

    def nearest_on_route(
        self, polyline: List[List[float]], max_distance_miles: Optional[float] = None
    ) -> Optional[FuelStation]:
        """
        Return the station with coordinates closest to the given polyline.
        If max_distance_miles is set, ignore stations farther than that.
        """
        closest_station = None
        closest_distance = inf
        for station in self.stations:
            coords, _ = self._ensure_coords(station, allow_geocode=False)
            if not coords:
                continue
            distance = nearest_point_distance_miles(coords, polyline)
            if max_distance_miles is not None and distance > max_distance_miles:
                continue
            if distance < closest_distance:
                closest_distance = distance
                closest_station = station
        return closest_station

    def nearest_to_point(self, target: Tuple[float, float]) -> Optional[FuelStation]:
        """
        Return the station with coordinates closest to a specific point.
        """
        closest_station = None
        closest_distance = inf
        for station in self.stations:
            coords, _ = self._ensure_coords(station, allow_geocode=False)
            if not coords:
                continue
            dist = haversine_miles(coords, target)
            if dist < closest_distance:
                closest_distance = dist
                closest_station = station
        return closest_station

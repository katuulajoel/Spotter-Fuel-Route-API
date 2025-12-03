import logging
from typing import Iterable

from django.conf import settings

from .fuel_data import StationCache, FuelStation, load_fuel_stations
from .mapbox_client import MapboxClient, MapboxClientError

logger = logging.getLogger(__name__)


def preload_station_coords(limit: int) -> None:
    """
    Geocode up to `limit` stations that are missing coordinates and persist to cache.
    This is best-effort; failures are logged and do not block startup.
    """
    if limit <= 0:
        return
    try:
        cache = StationCache(settings.STATION_CACHE_PATH)
        stations: Iterable[FuelStation] = load_fuel_stations(cache=cache)
        to_geocode = [s for s in stations if not s.coordinates][:limit]
        if not to_geocode:
            logger.info("Preload: all stations already have coordinates; nothing to do.")
            return
        client = MapboxClient()
        count = 0
        for station in to_geocode:
            try:
                query = f"{station.address}, {station.city}, {station.state}, USA"
                coords = client.geocode(query)
                if coords:
                    station.coordinates = coords
                    cache.set(station.cache_key, coords)
                    count += 1
            except MapboxClientError as exc:
                logger.warning("Preload: geocoding failed for %s (%s)", station.name, exc)
        logger.info("Preload: geocoded %s station(s) on startup", count)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Preload: skipping due to error: %s", exc)

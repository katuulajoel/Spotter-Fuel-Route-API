import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from django.conf import settings


@dataclass
class FuelStation:
    opis_id: str
    name: str
    address: str
    city: str
    state: str
    rack_id: str
    retail_price: float
    coordinates: Optional[Tuple[float, float]] = None  # (lat, lon)
    cache_key: str = field(init=False)

    def __post_init__(self):
        self.cache_key = f"{self.opis_id}-{self.address}-{self.city}-{self.state}"


class StationCache:
    def __init__(self, path: str):
        self.path = Path(path)
        self._data: Dict[str, Tuple[float, float]] = {}
        self._loaded = False

    def load(self):
        if self._loaded:
            return
        if self.path.exists():
            try:
                with open(self.path) as fp:
                    self._data = json.load(fp)
            except json.JSONDecodeError:
                # Corrupt cache; reset.
                self._data = {}
        self._loaded = True

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as fp:
            json.dump(self._data, fp)

    def get(self, cache_key: str) -> Optional[Tuple[float, float]]:
        self.load()
        coords = self._data.get(cache_key)
        return tuple(coords) if coords else None

    def set(self, cache_key: str, coords: Tuple[float, float]):
        self.load()
        self._data[cache_key] = coords
        self.save()


def load_fuel_stations(path: Optional[str] = None, cache: Optional[StationCache] = None) -> List[FuelStation]:
    csv_path = Path(path or settings.FUEL_DATA_PATH)
    if not csv_path.exists():
        raise FileNotFoundError(f"Fuel data file not found at {csv_path}")

    stations_by_key: Dict[str, FuelStation] = {}
    with open(csv_path, newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            try:
                price = float(row["Retail Price"])
            except (TypeError, ValueError):
                continue
            station = FuelStation(
                opis_id=row["OPIS Truckstop ID"].strip(),
                name=row["Truckstop Name"].strip(),
                address=row["Address"].strip(),
                city=row["City"].strip(),
                state=row["State"].strip(),
                rack_id=row["Rack ID"].strip(),
                retail_price=price,
            )
            key = station.cache_key
            existing = stations_by_key.get(key)
            if existing is None or price < existing.retail_price:
                stations_by_key[key] = station
    return list(stations_by_key.values())


def stations_sorted_by_price(stations: Iterable[FuelStation]) -> List[FuelStation]:
    return sorted(stations, key=lambda s: s.retail_price)


def index_by_city_state(stations: Iterable[FuelStation]) -> Dict[str, List[FuelStation]]:
    index: Dict[str, List[FuelStation]] = {}
    for station in stations:
        key = f"{station.city.lower().strip()}|{station.state.lower().strip()}"
        index.setdefault(key, []).append(station)
    return index


def index_by_state(stations: Iterable[FuelStation]) -> Dict[str, List[FuelStation]]:
    index: Dict[str, List[FuelStation]] = {}
    for station in stations:
        key = station.state.lower().strip()
        index.setdefault(key, []).append(station)
    return index

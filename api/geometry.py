import math
from typing import List, Sequence, Tuple


def haversine_miles(point_a: Tuple[float, float], point_b: Tuple[float, float]) -> float:
    """Calculate the great-circle distance between two points in miles."""
    lat1, lon1 = point_a
    lat2, lon2 = point_b
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(
        d_lambda / 2
    ) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    miles = 3958.8 * c
    return miles


def accumulate_distances_miles(points: Sequence[Sequence[float]]) -> List[float]:
    """Return cumulative miles along the polyline."""
    distances = [0.0]
    for idx in range(1, len(points)):
        prev = (points[idx - 1][1], points[idx - 1][0])
        current = (points[idx][1], points[idx][0])
        distances.append(distances[-1] + haversine_miles(prev, current))
    return distances


def interpolate_point(
    points: Sequence[Sequence[float]],
    cumulative: Sequence[float],
    target_miles: float,
) -> Tuple[float, float]:
    """
    Return the (lat, lon) point along the polyline at the requested distance.
    """
    if target_miles <= 0:
        return points[0][1], points[0][0]
    if target_miles >= cumulative[-1]:
        return points[-1][1], points[-1][0]
    for idx in range(1, len(cumulative)):
        if cumulative[idx] >= target_miles:
            prev_mile = cumulative[idx - 1]
            seg_length = cumulative[idx] - prev_mile
            ratio = (target_miles - prev_mile) / seg_length if seg_length else 0
            lon = points[idx - 1][0] + (points[idx][0] - points[idx - 1][0]) * ratio
            lat = points[idx - 1][1] + (points[idx][1] - points[idx - 1][1]) * ratio
            return (lat, lon)
    return points[-1][1], points[-1][0]


def nearest_point_distance_miles(
    target: Tuple[float, float], points: Sequence[Sequence[float]]
) -> float:
    """Return the closest distance in miles from the target point to a polyline."""
    closest = float("inf")
    for idx in range(1, len(points)):
        segment_start = (points[idx - 1][1], points[idx - 1][0])
        segment_end = (points[idx][1], points[idx][0])
        distance = _point_to_segment_distance_miles(target, segment_start, segment_end)
        closest = min(closest, distance)
    return closest


def _point_to_segment_distance_miles(
    point: Tuple[float, float],
    start: Tuple[float, float],
    end: Tuple[float, float],
) -> float:
    """
    Approximate the shortest distance from a point to a line segment on Earth.
    Uses naive projection in Cartesian space, good enough for short distances.
    """
    lat, lon = point
    lat1, lon1 = start
    lat2, lon2 = end
    # Convert to Cartesian for the projection
    x0, y0 = lon, lat
    x1, y1 = lon1, lat1
    x2, y2 = lon2, lat2

    dx, dy = x2 - x1, y2 - y1
    if dx == dy == 0:
        return haversine_miles(point, start)
    t = ((x0 - x1) * dx + (y0 - y1) * dy) / (dx * dx + dy * dy)
    t_clamped = max(0, min(1, t))
    proj = (x1 + t_clamped * dx, y1 + t_clamped * dy)
    return haversine_miles(point, (proj[1], proj[0]))


def downsample_polyline(points: Sequence[Sequence[float]], max_points: int = 400) -> List[List[float]]:
    """Reduce number of polyline points to cap CPU work; preserves endpoints."""
    pts = list(points)
    if len(pts) <= max_points:
        return pts
    step = max(1, len(pts) // max_points)
    reduced = pts[::step]
    if reduced[-1] != pts[-1]:
        reduced.append(pts[-1])
    return reduced

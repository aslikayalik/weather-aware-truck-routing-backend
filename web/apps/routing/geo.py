"""Small geometry helpers. Coordinates are (lat, lon) tuples in degrees."""

import math
from bisect import bisect_left

LatLon = tuple[float, float]

EARTH_RADIUS_MILES = 3958.8
MILES_PER_DEG_LAT = 69.0


def haversine_miles(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def cumulative_miles(coords: list[LatLon]) -> list[float]:
    total = 0.0
    result = [0.0]
    for a, b in zip(coords, coords[1:]):
        total += haversine_miles(a, b)
        result.append(total)
    return result


def interpolate(cum: list[float], values: list[float], at: float) -> float:
    """Linearly interpolate `values` (aligned with ascending `cum`) at position `at`."""
    if at <= cum[0]:
        return values[0]
    if at >= cum[-1]:
        return values[-1]
    i = bisect_left(cum, at)
    span = cum[i] - cum[i - 1]
    t = 0.0 if span == 0 else (at - cum[i - 1]) / span
    return values[i - 1] + (values[i] - values[i - 1]) * t


def points_at_miles(
    coords: list[LatLon], cum: list[float], miles: list[float]
) -> list[LatLon]:
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    return [(interpolate(cum, lats, m), interpolate(cum, lons, m)) for m in miles]


def bearing_deg(a: LatLon, b: LatLon) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(
        lon2 - lon1
    )
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def destination_point(origin: LatLon, bearing: float, miles: float) -> LatLon:
    lat1, lon1 = map(math.radians, origin)
    brg = math.radians(bearing)
    d = miles / EARTH_RADIUS_MILES
    lat2 = math.asin(
        math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(brg)
    )
    lon2 = lon1 + math.atan2(
        math.sin(brg) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), (math.degrees(lon2) + 540) % 360 - 180


def decode_polyline(encoded: str, precision: int = 6) -> list[LatLon]:
    """Decode a Google-style encoded polyline (Valhalla uses precision 6)."""
    factor = 10**precision
    coords: list[LatLon] = []
    index = lat = lon = 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lat / factor, lon / factor))
    return coords


def simplify_indices(coords: list[LatLon], tolerance_deg: float) -> list[int]:
    """Douglas-Peucker simplification; returns the indices of the points to keep."""
    if len(coords) < 3:
        return list(range(len(coords)))
    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    while stack:
        start, end = stack.pop()
        (y1, x1), (y2, x2) = coords[start], coords[end]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        max_dist, max_i = 0.0, start
        for i in range(start + 1, end):
            y0, x0 = coords[i]
            if norm == 0:
                dist = math.hypot(x0 - x1, y0 - y1)
            else:
                dist = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / norm
            if dist > max_dist:
                max_dist, max_i = dist, i
        if max_dist > tolerance_deg:
            keep[max_i] = True
            stack.append((start, max_i))
            stack.append((max_i, end))
    return [i for i, k in enumerate(keep) if k]


def overlap_ratio(
    route: list[LatLon],
    other: list[LatLon],
    cum: list[float],
    tolerance_miles: float = 1.0,
) -> float:
    """Share of `route` (sampled every ~5 miles) that lies within `tolerance_miles` of `other`."""
    samples = points_at_miles(route, cum, list(frange(0.0, cum[-1], 5.0)))
    if not samples:
        return 1.0
    other_samples = other[:: max(1, len(other) // 2000)]
    lat_tol = tolerance_miles / MILES_PER_DEG_LAT
    close = 0
    for lat, lon in samples:
        lon_tol = lat_tol / max(math.cos(math.radians(lat)), 0.1)
        if any(
            abs(lat - olat) <= lat_tol and abs(lon - olon) <= lon_tol
            for olat, olon in other_samples
        ):
            close += 1
    return close / len(samples)


def frange(start: float, stop: float, step: float):
    """start, start+step, ... up to and including stop (no float drift)."""
    for i in range(int((stop - start) // step) + 1):
        yield start + i * step

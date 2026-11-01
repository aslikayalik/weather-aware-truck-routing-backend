"""Place search via Photon (OpenStreetMap data, no API key)."""

import hashlib
import logging

import requests
from django.conf import settings
from django.core.cache import cache

from apps.routing.services.http import default_headers

logger = logging.getLogger(__name__)

RESULT_LIMIT = 6
CACHE_TTL_SECONDS = 24 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 10


class GeocodingError(Exception):
    pass


def _label(props: dict) -> str:
    name = props.get("name") or " ".join(
        filter(None, (props.get("housenumber"), props.get("street")))
    )
    parts = [name, props.get("city"), props.get("state"), props.get("country")]
    unique = []
    for part in parts:
        if part and part not in unique:
            unique.append(part)
    return ", ".join(unique)


def search_places(query: str) -> list[dict]:
    query = query.strip()
    cache_key = "geocode:v2:" + hashlib.sha256(query.lower().encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        response = requests.get(
            f"{settings.PHOTON_URL.rstrip('/')}/api/",
            params={"q": query, "limit": RESULT_LIMIT, "lang": "en"},
            headers=default_headers(),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        features = response.json().get("features", [])
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError(f"Geocoding failed: {exc}") from exc

    results = []
    seen_labels = set()
    for feature in features:
        label = _label(feature.get("properties", {}))
        # A city and its county often share a label; the first (best) match is enough.
        if label in seen_labels:
            continue
        seen_labels.add(label)
        lon, lat = feature["geometry"]["coordinates"]
        results.append({"label": label, "lat": lat, "lon": lon})
    cache.set(cache_key, results, CACHE_TTL_SECONDS)
    return results

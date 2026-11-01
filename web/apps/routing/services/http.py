from django.conf import settings


def default_headers() -> dict[str, str]:
    """Public OSM-based services reject anonymous clients; identify the app."""
    return {"User-Agent": settings.HTTP_USER_AGENT}

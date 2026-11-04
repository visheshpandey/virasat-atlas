"""Representative photos for sites, looked up from Wikipedia / Wikimedia Commons.

Called from the backend only. Results are cached for 10 minutes (failures for 1 minute)
and a failed lookup returns None so the UI simply shows no photo.
"""
import time
from collections import OrderedDict

import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia requires a descriptive User-Agent that says where to reach the project.
USER_AGENT = "VirasatAtlas/1.0 (https://github.com/visheshpandey/virasat-atlas; heritage map prototype)"

# Sites whose own name finds the wrong article: (source, search text).
OVERRIDES: dict[str, tuple[str, str]] = {
    "Patan Patola Weaving": ("commons", "Patan patola"),
}

_CACHE_TTL_OK = 600.0
_CACHE_TTL_FAIL = 60.0
_CACHE_MAX = 256
_cache: "OrderedDict[str, tuple[float, dict | None]]" = OrderedDict()


async def _from_wikipedia(client: httpx.AsyncClient, query: str) -> dict | None:
    resp = await client.get(WIKIPEDIA_API, params={
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} Gujarat", "gsrlimit": 4,
        "prop": "pageimages|info", "piprop": "thumbnail", "pithumbsize": 800,
        "inprop": "url", "redirects": 1,
    })
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {}).values()
    for page in sorted(pages, key=lambda p: p.get("index", 99)):
        thumb = page.get("thumbnail")
        if thumb:
            return {
                "image_url": thumb["source"],
                "page_url": page.get("fullurl"),
                "title": page["title"],
                "source": "Wikipedia",
            }
    return None


async def _from_commons(client: httpx.AsyncClient, query: str) -> dict | None:
    resp = await client.get(COMMONS_API, params={
        "action": "query", "format": "json", "generator": "search",
        "gsrnamespace": 6, "gsrsearch": query, "gsrlimit": 5,
        "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": 800,
    })
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {}).values()
    for page in sorted(pages, key=lambda p: p.get("index", 99)):
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("mime") in ("image/jpeg", "image/png") and info.get("thumburl"):
            title = page["title"]
            return {
                "image_url": info["thumburl"],
                "page_url": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
                "title": title.removeprefix("File:"),
                "source": "Wikimedia Commons",
            }
    return None


async def _lookup(name: str) -> dict | None:
    source, query = OVERRIDES.get(name, ("wikipedia", name))
    async with httpx.AsyncClient(timeout=8.0, headers={"User-Agent": USER_AGENT}) as client:
        if source == "wikipedia":
            found = await _from_wikipedia(client, query)
            if found:
                return found
        return await _from_commons(client, query)


async def get_site_image(name: str) -> dict | None:
    """Return {image_url, page_url, title, source} for a site, or None if nothing was found."""
    now = time.monotonic()
    cached = _cache.get(name)
    if cached and cached[0] > now:
        _cache.move_to_end(name)
        return cached[1]

    try:
        result = await _lookup(name)
        ttl = _CACHE_TTL_OK
    except Exception as exc:  # network error, rate limit, bad JSON: show no photo
        logger.warning(f"site_image_lookup_failed site={name!r} error={type(exc).__name__}")
        result, ttl = None, _CACHE_TTL_FAIL

    _cache[name] = (now + ttl, result)
    _cache.move_to_end(name)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return result

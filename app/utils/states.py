"""Helpers for the region (state) filter."""

ALL_VALUES = {"", "all", "all india", "india"}


def state_key(value: str | None) -> str | None:
    """Normalise a state name or URL slug ("Madhya-Pradesh") for comparison.

    Returns None for blank or "all"/"All India", meaning no state filter.
    """
    key = " ".join((value or "").strip().lower().replace("-", " ").replace("_", " ").split())
    return None if key in ALL_VALUES else key


def slugify(name: str) -> str:
    """URL-friendly form of a state name: "Madhya Pradesh" -> "madhya-pradesh"."""
    return "-".join(name.strip().lower().split())

"""Multilingual auto-tagger. Not yet implemented."""


def detect_language(text: str) -> str:
    """Return "hi", "gu" or "en" from the dominant Unicode script."""
    raise NotImplementedError


def tag_rules(text: str) -> dict:
    """Layer 1. Return TagOut-shaped dict: site_type, era, century, themes, language, source."""
    raise NotImplementedError


async def tag_text(text: str) -> dict:
    """Layer 1 plus optional Claude layer. Never raises because of the Claude call."""
    raise NotImplementedError

"""Helpers for rendering text that did not come from this code base."""
from __future__ import annotations

import re

# ![alt](url) and ![alt][ref]: an image makes the browser fetch a third-party URL as
# soon as the page renders, which leaks that the answer was viewed (a beacon).
_INLINE_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_REFERENCE_IMAGE = re.compile(r"!\[([^\]]*)\]\[[^\]]*\]")
_HTML_IMAGE = re.compile(r"(?i)<\s*img\b[^>]*>")


def strip_remote_images(text: str) -> str:
    """Replace markdown and HTML images with their alt text.

    Plain links are kept: they need a click. The text keeps its meaning without the
    image, and nothing is fetched on render.
    """
    if not isinstance(text, str):
        return text
    text = _INLINE_IMAGE.sub(lambda m: m.group(1), text)
    text = _REFERENCE_IMAGE.sub(lambda m: m.group(1), text)
    return _HTML_IMAGE.sub("", text)

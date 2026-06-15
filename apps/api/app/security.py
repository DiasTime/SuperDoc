"""Upload validation. Assume hostile users: never trust the client-declared
content-type — sniff magic bytes and only accept a known allowlist.
"""

from __future__ import annotations

# canonical content-type keyed by detector
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
    (b"BM", "image/bmp"),
]


def sniff_image_type(data: bytes) -> str | None:
    """Return canonical content-type if the bytes are a supported image, else None."""
    for sig, ctype in _SIGNATURES:
        if data.startswith(sig):
            return ctype
    # WEBP: "RIFF"...."WEBP"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None

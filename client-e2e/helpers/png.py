"""Minimal pure-stdlib PNG encoder for E2E failure screenshot diagnostics."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(data, crc) & 0xFFFFFFFF
    return struct.pack("!I", len(data)) + chunk_type + data + struct.pack("!I", crc)


def write_rgb_png(
    path: Path,
    width: int,
    height: int,
    raw_bytes: bytes,
    *,
    bgrx: bool = False,
) -> Path:
    """Write raw RGB or BGRX pixel bytes to an uncompressed-filter RGB PNG file."""
    if width <= 0 or height <= 0:
        raise ValueError(f"PNG dimensions must be positive, got {width}x{height}")

    if bgrx:
        expected = width * height * 4
        if len(raw_bytes) != expected:
            raise ValueError(f"Expected {expected} BGRX bytes for {width}x{height}, got {len(raw_bytes)}")
        rgb = bytearray(width * height * 3)
        rgb[0::3] = raw_bytes[2::4]
        rgb[1::3] = raw_bytes[1::4]
        rgb[2::3] = raw_bytes[0::4]
        rgb_bytes = bytes(rgb)
    else:
        expected = width * height * 3
        if len(raw_bytes) != expected:
            raise ValueError(f"Expected {expected} RGB bytes for {width}x{height}, got {len(raw_bytes)}")
        rgb_bytes = raw_bytes

    stride = width * 3
    scanlines = bytearray((stride + 1) * height)
    mv = memoryview(rgb_bytes)
    for row in range(height):
        dst = row * (stride + 1)
        scanlines[dst] = 0
        scanlines[dst + 1 : dst + 1 + stride] = mv[row * stride : (row + 1) * stride]

    ihdr = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(scanlines), level=6)
    png_data = (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_data)
    return path

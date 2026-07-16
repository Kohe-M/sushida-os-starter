#!/usr/bin/env python3
"""Reject blank QEMU PPM captures without pretending to recognize the UI."""

from pathlib import Path
import struct
import sys
import zlib


def fail(message: str) -> None:
    print(f"ERROR: screenshot: {message}", file=sys.stderr)
    raise SystemExit(1)


if len(sys.argv) not in (2, 3):
    fail("usage: check-screenshot.py PPM_PATH [PNG_PATH]")

path = Path(sys.argv[1])
try:
    with path.open("rb") as stream:
        if stream.readline().strip() != b"P6":
            fail("capture is not binary PPM (P6)")

        header: list[bytes] = []
        while len(header) < 3:
            line = stream.readline()
            if not line:
                fail("truncated PPM header")
            line = line.split(b"#", 1)[0]
            header.extend(line.split())

        width, height, maximum = (int(value) for value in header[:3])
        if width <= 0 or height <= 0 or maximum != 255:
            fail("invalid dimensions or channel maximum")
        pixels = stream.read()
except (OSError, ValueError) as error:
    fail(str(error))

expected = width * height * 3
if len(pixels) != expected:
    fail(f"pixel payload is {len(pixels)} bytes; expected {expected}")

total = width * height
dark = 0
bright = 0
bright_left = width
bright_right = -1
bright_top = height
bright_bottom = -1
bright_columns = bytearray(width)
bright_rows = bytearray(height)
for offset in range(0, len(pixels), 3):
    red, green, blue = pixels[offset : offset + 3]
    if max(red, green, blue) <= 32:
        dark += 1
    if min(red, green, blue) >= 180:
        bright += 1
        pixel = offset // 3
        x = pixel % width
        y = pixel // width
        bright_left = min(bright_left, x)
        bright_right = max(bright_right, x)
        bright_top = min(bright_top, y)
        bright_bottom = max(bright_bottom, y)
        bright_columns[x] = 1
        bright_rows[y] = 1

# The expected offline kiosk capture has a dark full-screen background plus
# bright explanatory text. These deliberately broad bounds reject uniform
# white/black firmware or compositor frames without claiming OCR-level proof.
if dark * 100 < total * 70:
    fail("capture is not predominantly dark")
if bright * 1000 < total:
    fail("capture lacks visible bright foreground content")

bright_width = bright_right - bright_left + 1
bright_height = bright_bottom - bright_top + 1
if bright_width * 5 < width or bright_height * 20 < height:
    fail("bright foreground is confined to a partial scanout")
occupied_columns = sum(bright_columns)
occupied_rows = sum(bright_rows)
if occupied_columns * 5 < width or occupied_rows * 20 < height:
    fail("bright foreground lacks spatial coverage")

if len(sys.argv) == 3:
    png_path = Path(sys.argv[2])

    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)

    rows = b"".join(
        b"\x00" + pixels[row * width * 3 : (row + 1) * width * 3]
        for row in range(height)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, level=9))
        + chunk(b"IEND", b"")
    )
    try:
        png_path.write_bytes(png)
    except OSError as error:
        fail(str(error))

print(
    f"Screenshot contrast passed: {width}x{height}, "
    f"dark={dark / total:.1%}, bright={bright / total:.1%}, "
    f"foreground={bright_width}x{bright_height}, "
    f"coverage={occupied_columns}x{occupied_rows}"
)

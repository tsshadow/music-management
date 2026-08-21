#!/usr/bin/env python3
"""Regenerate the placeholder screenshots for the in-app manual.

The Help screen shows one picture per chapter. Until a real screenshot exists, the chapter shows
a placeholder that says what belongs there, so a half-filled manual reads as a to-do list rather
than as a broken screen.

Every file this writes carries the marker MARKER in a PNG text chunk. A real screenshot does not,
which is how scripts/manual-screenshot-status.sh tells the two apart. Overwrite a placeholder with
a real capture and it drops off that report by itself.

Run it after adding a chapter to ManualChapter.kt: add the entry to CHAPTERS below, run this, and
the new chapter has a picture from the first build.

    python3 scripts/manual-placeholders.py

Needs Pillow. Regenerating is safe: it only writes files that are still placeholders, so a real
screenshot is never overwritten (pass --force to overwrite everything anyway).
"""

import argparse
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont, PngImagePlugin
except ImportError:  # pragma: no cover - depends on the machine, not on the code
    sys.exit("Pillow is missing. pip install pillow")

MARKER = "muma-manual-placeholder"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "app", "src", "main", "res", "drawable-nodpi")

BG = (18, 18, 18)
FRAME = (60, 60, 60)
INK = (170, 170, 170)
DIM = (110, 110, 110)
ACCENT = (30, 215, 96)

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

PHONE = (540, 1110)
CAR = (960, 600)

# name, heading, what to capture (one entry per line drawn), size
CHAPTERS = [
    (
        "manual_start",
        "Servers",
        ["The server list, with one server", "and the offline entry visible"],
        PHONE,
    ),
    (
        "manual_home",
        "Home",
        ["The home tab, two rows deep,", "Sets switch in the toolbar"],
        PHONE,
    ),
    (
        "manual_library",
        "Library",
        ["The tab strip plus the filter bar", "above a list"],
        PHONE,
    ),
    (
        "manual_favorites",
        "Favourites",
        ["The star tab, or a track row", "with its stars set"],
        PHONE,
    ),
    (
        "manual_search",
        "Search",
        ["A search with results in", "more than one group"],
        PHONE,
    ),
    (
        "manual_player",
        "Player",
        ["The full player,", "artwork side"],
        PHONE,
    ),
    (
        "manual_voice",
        "MuMa Voice",
        ["MuMa Voice listening, or the", "question asking which one you meant"],
        PHONE,
    ),
    (
        "manual_car",
        "Android Auto",
        ["The Android Auto browse screen", "(landscape)"],
        CAR,
    ),
    (
        "manual_offline",
        "Downloads",
        ["The downloads screen", "with something pinned"],
        PHONE,
    ),
    (
        "manual_settings",
        "Settings",
        ["The settings list,", "appearance section open"],
        PHONE,
    ),
    (
        "manual_update",
        "Updates",
        ["The update dialog offering", "a newer build"],
        PHONE,
    ),
    (
        "manual_trouble",
        "Log",
        ["The log viewer, or voice", "diagnostics with a trace"],
        PHONE,
    ),
]


def font(size):
    for path in FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def centered(draw, box, text, fnt, fill):
    left, top, right, bottom = box
    bbox = draw.textbbox((0, 0), text, font=fnt)
    x = left + ((right - left) - (bbox[2] - bbox[0])) / 2 - bbox[0]
    y = top + ((bottom - top) - (bbox[3] - bbox[1])) / 2 - bbox[1]
    draw.text((x, y), text, font=fnt, fill=fill)


def is_placeholder(path):
    if not os.path.exists(path):
        return True
    with open(path, "rb") as handle:
        return MARKER.encode("ascii") in handle.read()


def placeholder(name, title, wanted, size):
    width, height = size
    image = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(image)

    draw.rectangle([2, 2, width - 3, height - 3], outline=FRAME, width=3)
    # A hint of a screen: a toolbar strip on top and a nav strip at the bottom, so the
    # placeholder reads as "a screenshot goes here" and not as a broken image.
    draw.rectangle([3, 3, width - 4, 3 + int(height * 0.07)], fill=(30, 30, 30))
    draw.rectangle([3, height - 4 - int(height * 0.08), width - 4, height - 4], fill=(30, 30, 30))

    centered(draw, (0, int(height * 0.33), width, int(height * 0.40)), title, font(34), INK)
    centered(
        draw,
        (0, int(height * 0.42), width, int(height * 0.47)),
        "MISSING SCREENSHOT",
        font(26),
        ACCENT,
    )

    # What to capture goes on the picture itself: that is the one place the instruction is
    # guaranteed to be in front of whoever is holding the phone.
    top = int(height * 0.52)
    for line in wanted:
        centered(draw, (0, top, width, top + 34), line, font(21), DIM)
        top += 34

    centered(
        draw,
        (0, int(height * 0.80), width, int(height * 0.85)),
        "{}.png  ({}x{})".format(name, width, height),
        font(20),
        DIM,
    )

    meta = PngImagePlugin.PngInfo()
    meta.add_text("Comment", MARKER)
    image.save(os.path.join(OUT, name + ".png"), optimize=True, pnginfo=meta)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite real screenshots too, not only placeholders",
    )
    args = parser.parse_args()

    os.makedirs(OUT, exist_ok=True)
    written = 0
    kept = 0

    for name, title, wanted, size in CHAPTERS:
        path = os.path.join(OUT, name + ".png")
        if not args.force and not is_placeholder(path):
            print("kept  {}.png (real screenshot)".format(name))
            kept += 1
            continue
        placeholder(name, title, wanted, size)
        print("wrote {}.png".format(name))
        written += 1

    print("\n{} placeholder(s) written, {} real screenshot(s) left alone.".format(written, kept))


if __name__ == "__main__":
    main()

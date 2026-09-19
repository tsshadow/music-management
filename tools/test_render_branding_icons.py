"""The generator's output is committed, so it can drift from the generator."""

import re

from tools import render_branding_icons as render_icons


def test_the_middle_bar_is_the_shortest():
    tops = [top for _, top in render_icons.BARS]
    assert tops[2] == max(tops), "the middle bar must be shortest, or the M reads as a V"
    assert tops[0] == tops[4] == min(tops), "the outer bars must be tallest and equal"


def test_the_notification_glyph_fits_the_viewport():
    glyph = render_icons.render_notification_glyph()
    assert 'android:viewportWidth="24"' in glyph
    assert glyph.count("<path") == 5


def test_the_generator_matches_the_design_source():
    """docs/branding/muma-icon.svg is hand-authored; the constants here mirror it."""
    svg = (render_icons.BRANDING / "muma-icon.svg").read_text(encoding="utf-8")
    bars = [(float(x), float(top)) for x, top in re.findall(r'd="M([\d.]+) ([\d.]+) V[\d.]+"', svg)]
    bottoms = {float(b) for b in re.findall(r'd="M[\d.]+ [\d.]+ V([\d.]+)"', svg)}
    strokes = {float(s) for s in re.findall(r'stroke-width="([\d.]+)"', svg)}
    radii = {float(r) for r in re.findall(r'r="([\d.]+)"', svg)}

    assert bars == render_icons.BARS
    assert bottoms == {render_icons.BOTTOM}
    assert strokes == {render_icons.STROKE}
    assert radii == {render_icons.DISC_RADIUS}


def test_the_safe_zone_scale_reproduces_the_committed_green_icon():
    """The launcher foreground shrinks the mark to 0.83; getting that wrong crops the bars."""
    foreground = render_icons.render_launcher_foreground(render_icons.GREEN)
    assert 'android:pathData="M153.1 190.4 V321.6"' in foreground
    assert 'android:pathData="M256.0 271.8 V321.6"' in foreground
    assert 'android:strokeWidth="29.9"' in foreground
    assert "A176.0,176.0" in foreground


def test_every_committed_file_matches_the_generator():
    assert render_icons.main(["--check"]) == 0, "run python3 tools/render_branding_icons.py"


def test_the_debug_foreground_stays_inside_the_launcher_mask():
    """A launcher shows the middle 72 of 108dp; a badge that crosses that edge gets cropped."""
    mask_radius = 512 * 36 / 108
    badge_offset = (render_icons.BADGE_CENTRE - render_icons.CENTRE) * render_icons.SAFE_ZONE
    badge_reach = (badge_offset**2 * 2) ** 0.5 + render_icons.BADGE_RING_RADIUS * render_icons.SAFE_ZONE
    assert badge_reach < mask_radius

    foreground = render_icons.render_launcher_foreground(render_icons.DEBUG_GREY, debug=True)
    assert foreground.count("<path") == 1 + 5 + 3, "disc, five bars, ring, badge, D"
    assert render_icons.GREEN not in foreground and render_icons.INDIGO not in foreground


def test_the_release_foreground_carries_no_badge():
    foreground = render_icons.render_launcher_foreground(render_icons.GREEN)
    assert foreground.count("<path") == 1 + 5
    assert "strokeLineJoin" not in foreground

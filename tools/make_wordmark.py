"""
Makes the wordmark: the logo and "InsideLabel" in italic, the one wordmark at the top of every
website page and app screen (Sushil, 2026-10-02: "italic name for brand name everywhere and
logo and brand name each page in center").

Why an SVG and not a font: Bricolage Grotesque, the display face, has no italic, so the name is set
in DM Sans ExtraBold Italic (OFL; tools/wordmark/, from Fontsource, @fontsource/dm-sans 5.3.0). As
a web font it needed a second stylesheet and a font file, and as an SVG file another request: each
cost the website's mobile LCP in Lighthouse (an extra request is about one round trip in its 4G
model). So the letters are drawn here as outlines (shaped with HarfBuzz, so the font's kerning
applies; drawn with fontTools) into one inline SVG, written into each page between
<!--wordmark--> and <!--/wordmark-->. This file is the one definition; tests/test_site_desktop.py
checks every page carries the same copy. Light and dark follow prefers-color-scheme, in the
pages' own ink colours.

Run (dev only): pip install fonttools brotli uharfbuzz; python tools/make_wordmark.py

D-161: the Play listing's feature graphic (android/feature_graphic.png, 1024 x 500) is drawn from the
same wordmark, in the light ink, centred on the app's cream, so it changes when the wordmark does:
pip install fonttools brotli uharfbuzz cairosvg pillow; python tools/make_wordmark.py --feature-graphic
"""
import io
import os
import re
import sys

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "tools", "wordmark", "dm-sans-latin-800-italic.woff2")
ICON = os.path.join(ROOT, "web", "icon.svg")
PAGES = [os.path.join(ROOT, "web", "index.html")] + [
    os.path.join(ROOT, "web", "site", f"{n}.html") for n in ("index", "privacy", "about", "how")] + [
    # D-161: the reviewer screen's header. A Jinja template: base.html wraps the block in
    # {% raw %} ... {% endraw %}, outside the markers, so the SVG's braces are never read as
    # Jinja and the copy between the markers stays byte for byte the one every page has.
    os.path.join(ROOT, "src", "insidelabel", "review", "templates", "base.html")]
MARKS = re.compile(r"<!--wordmark-->.*?<!--/wordmark-->|<img src=\"[^\"]*wordmark\.svg\"[^>]*>", re.S)
NAME = "InsideLabel"
SIZE = 22            # px: the name's size, as the header's text was
MARK = 34            # px: the logo, as before
GAP = 8
INK, INK_DARK = "#244b6b", "#e0f2f6"     # --ink, light and dark (web/app.css, web/site/site.css)


def wordmark_svg(dark=True):
    """The wordmark as one inline SVG. dark=False leaves out the dark-mode ink (a raster has one look)."""
    font = TTFont(FONT)
    buf = io.BytesIO()
    font.flavor = None
    font.save(buf)
    face = hb.Face(buf.getvalue())
    hbfont = hb.Font(face)
    text = hb.Buffer()
    text.add_str(NAME)
    text.guess_segment_properties()
    hb.shape(hbfont, text, {"kern": True, "liga": True})

    upm = font["head"].unitsPerEm
    scale = SIZE / upm
    cap = font["OS/2"].sCapHeight * scale
    baseline = MARK / 2 + cap / 2                     # the capitals centred on the logo
    glyphs = font.getGlyphSet()
    order = font.getGlyphOrder()

    # whole numbers on a quarter-pixel grid (the path is drawn 4x and scaled back): sharp, and short
    pen = SVGPathPen(glyphs, ntos=lambda v: str(round(v)))
    q = 4
    x = 0
    for info, pos in zip(text.glyph_infos, text.glyph_positions):
        name = order[info.codepoint]
        ox = MARK + GAP + (x + pos.x_offset) * scale
        glyphs[name].draw(TransformPen(pen, (scale * q, 0, 0, -scale * q, ox * q, baseline * q)))
        x += pos.x_advance
    width = round(MARK + GAP + x * scale + 3)          # + the italic's overhang

    icon = open(ICON, encoding="utf-8").read()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", icon, re.S).group(1)
    inner = re.sub(r"<title>.*?</title>", "", inner)
    inner = re.sub(r'id="(\w+)"', r'id="wm-\1"', inner).replace("url(#", "url(#wm-")   # ids unique on the page
    dark_rule = f"@media (prefers-color-scheme:dark){{.wm-ink{{fill:{INK_DARK}}}}}" if dark else ""
    return (f'<svg class="wordmark-svg" role="img" aria-label="{NAME}" width="{width}" height="{MARK}" '
            f'viewBox="0 0 {width} {MARK}">'
            f"<style>.wm-ink{{fill:{INK}}}{dark_rule}</style>"
            f'<svg width="{MARK}" height="{MARK}" viewBox="0 0 512 512">{inner}</svg>'
            f'<path class="wm-ink" transform="scale(.25)" d="{pen.getCommands()}"/></svg>'), width


FEATURE = os.path.join(ROOT, "android", "feature_graphic.png")
FEATURE_SIZE = (1024, 500)
FEATURE_SHARE = 0.66      # the wordmark's width, of the graphic's: readable when Play shows it small
CREAM = "#FBF9EE"         # the app's background (web/app.css)


def feature_graphic():
    """D-161: the Play feature graphic. 24-bit PNG, no alpha (Play's rule): flattened onto the cream."""
    import cairosvg
    from PIL import Image

    svg, width = wordmark_svg(dark=False)
    svg = svg.replace('<svg class="wordmark-svg"', '<svg xmlns="http://www.w3.org/2000/svg" class="wordmark-svg"', 1)
    w = round(FEATURE_SIZE[0] * FEATURE_SHARE)
    h = round(w * MARK / width)
    mark = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=w, output_height=h)))
    out = Image.new("RGB", FEATURE_SIZE, CREAM)
    out.paste(mark, ((FEATURE_SIZE[0] - w) // 2, (FEATURE_SIZE[1] - h) // 2), mark.convert("RGBA"))
    out.save(FEATURE, "PNG", optimize=True)
    print(f"feature graphic: {FEATURE_SIZE[0]} x {FEATURE_SIZE[1]}, wordmark {w} x {h} px")


def main():
    if "--feature-graphic" in sys.argv[1:]:
        return feature_graphic()
    svg, width = wordmark_svg()
    block = f"<!--wordmark-->{svg}<!--/wordmark-->"
    for page in PAGES:
        html = open(page, encoding="utf-8").read()
        new, n = MARKS.subn(lambda m: block, html)
        assert n == 1, (page, n)
        if new != html:
            open(page, "w", encoding="utf-8").write(new)
    print(f"wordmark: {width} x {MARK} px, {len(svg.encode())} bytes, in {len(PAGES)} pages")

if __name__ == "__main__":
    main()

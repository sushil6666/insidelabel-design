"""D-153: the design system the redesign is built on.

One block of tokens and components sits, byte for byte, in both web/app.css and
web/site/site.css, so the app and the website can't drift apart. These tests keep
it that way, and check what a stylesheet can't check for itself: every token used
is defined, the values the block repeats from app.css still match, every text pair
passes WCAG AA in light and dark (computed here, not remembered), and the fonts are
our own files, each with its licence (D-110: no visitor IP leaves for a font).
"""
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
APP_CSS = os.path.join(WEB, "app.css")
SITE_CSS = os.path.join(WEB, "site", "site.css")
DESIGN = os.path.join(WEB, "design.html")

BEGIN = "/* ==== D-153 design system: begin"
END = "/* ==== D-153 design system: end ==== */"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def block(css):
    assert css.count(BEGIN) == 1 and css.count(END) == 1
    return css[css.index(BEGIN):css.index(END) + len(END)]


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def decls(css):
    """Custom properties set in a piece of CSS, in order (a later one wins)."""
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;}]+)", strip_comments(css)))


def split_modes(css):
    """(light, dark) custom properties of a stylesheet: :root rules outside any media
    query, and the :root rules inside prefers-color-scheme: dark."""
    css = strip_comments(css)
    dark, light_parts, i = {}, [], 0
    for m in re.finditer(r"@media \(prefers-color-scheme: dark\)\s*\{", css):
        depth, j = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        light_parts.append(css[i:m.start()])
        dark.update(decls(css[m.end():j - 1]))
        i = j
    light_parts.append(css[i:])
    light = {}
    for part in light_parts:
        for r in re.finditer(r":root\s*\{([^}]*)\}", part):
            light.update(decls(r.group(1)))
    return light, {**light, **dark}


def hex_rgb(value):
    v = value.strip().lstrip("#")
    assert re.fullmatch(r"[0-9a-fA-F]{6}", v), value
    return tuple(int(v[k:k + 2], 16) / 255 for k in (0, 2, 4))


def luminance(rgb):
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a, b):
    la, lb = sorted((luminance(hex_rgb(a)), luminance(hex_rgb(b))), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_the_block_is_identical_in_the_app_and_the_website():
    assert block(read(APP_CSS)) == block(read(SITE_CSS))


def test_the_block_repeats_app_values_unchanged():
    """A value the block repeats for the website must be the app's own value, in both modes."""
    app = read(APP_CSS)
    before = app[:app.index(BEGIN)]
    app_light, app_dark = split_modes(before)
    blk_light, blk_dark = split_modes(block(app))
    for mode, app_vals, blk_vals in (("light", app_light, blk_light), ("dark", app_dark, blk_dark)):
        for name, value in blk_vals.items():
            if name in app_vals:
                assert app_vals[name].strip() == value.strip(), (mode, name, app_vals[name], value)


def test_every_token_used_is_defined():
    for path in (APP_CSS, SITE_CSS):
        css = strip_comments(read(path))
        defined = set(decls(css))
        used = set(re.findall(r"var\((--[\w-]+)\)", css))   # var(--x, fallback) is set from JS
        assert not used - defined, (os.path.relpath(path, ROOT), sorted(used - defined))
    page_used = set(re.findall(r"var\((--[\w-]+)", read(DESIGN)))
    assert not page_used - set(decls(read(APP_CSS))), sorted(page_used - set(decls(read(APP_CSS))))


# Text on background, the smallest size each pair is used at. 4.5:1 for normal text, 3:1 for
# large text (24 px, or 18.66 px bold) and for the hero's green stroke behind 44 px+ words.
PAIRS = [
    ("--on-deep", "--deep", 4.5),          # words on the deep panel
    ("--on-deep-muted", "--deep", 4.5),    # sources and kickers on the panel
    ("--deep", "--deep-action", 4.5),      # the big button on the panel
    ("--brand-ink", "--brand", 4.5),       # the big button elsewhere
    ("--stop", "--stop-bg", 4.5),          # a person line on the avoid list
    ("--calm", "--calm-bg", 4.5),
    ("--unsure", "--unsure-bg", 4.5),
    ("--ink", "--surface-2", 4.5),         # the report table's header (--muted there is 4.27:1, so ink)
    ("--muted", "--bg", 4.5),              # sources, kickers, pending tags
    ("--muted", "--surface", 4.5),
    ("--ink", "--bg", 4.5),
    ("--on-deep", "--mark", 3.0),          # the hero's last words over the green stroke
]


def test_text_pairs_pass_wcag_aa_in_light_and_dark():
    light, dark = split_modes(read(APP_CSS))
    for mode, vals in (("light", light), ("dark", dark)):
        for fg, bg, need in PAIRS:
            ratio = contrast(vals[fg], vals[bg])
            assert ratio >= need, f"{mode}: {fg} on {bg} is {ratio:.2f}:1, needs {need}"


def test_fonts_are_ours_and_licensed():
    for path in (APP_CSS, SITE_CSS):
        css = read(path)
        for url in re.findall(r'url\("([^"]+\.woff2)"\)', css):
            local = os.path.join(WEB, url[len("/app/"):]) if url.startswith("/app/") \
                else os.path.join(os.path.dirname(path), url)
            assert os.path.exists(local), (os.path.relpath(path, ROOT), url)
    families = {"source-serif-4", "ibm-plex-mono", "dm-sans", "bricolage-grotesque"}
    for fam in families:
        assert os.path.exists(os.path.join(WEB, "fonts", f"OFL-{fam}.txt")), fam
        assert "SIL Open Font License" in read(os.path.join(WEB, "fonts", f"OFL-{fam}.txt"))
    for f in glob.glob(os.path.join(WEB, "**", "*.*"), recursive=True):
        if f.endswith((".css", ".html", ".js")):
            text = read(f)
            assert "fonts.googleapis" not in text and "fonts.gstatic" not in text, f


def test_both_stylesheets_name_the_same_new_faces():
    faces = lambda css: sorted(re.findall(r'font-family: "([^"]+)"; font-weight: (\d+)', css))
    new = [f for f in faces(read(APP_CSS)) if f[0] in ("Source Serif 4", "IBM Plex Mono")]
    assert new == [f for f in faces(read(SITE_CSS)) if f[0] in ("Source Serif 4", "IBM Plex Mono")]
    assert new == [("IBM Plex Mono", "400"), ("Source Serif 4", "400"), ("Source Serif 4", "600")]


def test_the_reference_sheet_is_worded_like_the_app_and_stays_out_of_search():
    from test_wording import assert_clean
    import html
    page = read(DESIGN)
    assert '<meta name="robots" content="noindex">' in page
    text = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"<style>.*?</style>", " ", page, flags=re.S)))
    assert_clean([" ".join(text.split())], "web/design.html")

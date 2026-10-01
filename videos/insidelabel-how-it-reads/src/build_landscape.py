"""The 16:9 cut (1920x1080). Builds index.html and compositions/*.html; run it through ./make.sh.

Read MOTION.md first. The 9:16 cut is src/build_vertical.py; keep the two in step.

The phone does the explaining: a real-looking InsideLabel flow plays on it, and the words on
screen are 2 to 4 per beat. The phone sits in the same place in every scene, so scene cuts
are seamless; the camera zooms to the one thing that matters, then holds still.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOTAL = 41

FONTS = """
      @font-face { font-family: "Bricolage Grotesque"; font-weight: 800; src: url("assets/fonts/bricolage-grotesque-800.woff2") format("woff2"); }
      @font-face { font-family: "DM Sans"; font-weight: 400; src: url("assets/fonts/dm-sans-400.woff2") format("woff2"); }
      @font-face { font-family: "DM Sans"; font-weight: 600; src: url("assets/fonts/dm-sans-600.woff2") format("woff2"); }
      @font-face { font-family: "DM Sans"; font-weight: 700; src: url("assets/fonts/dm-sans-700.woff2") format("woff2"); }"""

TOKENS = """
        --bg: #fbf9ee; --surface: #ffffff; --ink: #244b6b; --muted: #57768c; --line: #c9e3ec;
        --brand: #048149; --brand-ink: #fcfcf8; --ring: #008cba;
        --stop: #c92324; --stop-bg: #ffe5e0; --unsure: #6c380d; --unsure-bg: #ffefcd; --unsure-line: #f59e3b;
        --calm: #194860; --calm-bg: #d5f7f4;
        --display: "Bricolage Grotesque", "DM Sans", sans-serif; --font: "DM Sans", sans-serif;"""

# Everything below is in canvas pixels except inside .app, which is the app's own CSS pixels
# (390 wide) scaled 1.159 onto the phone's 452 px screen.
CSS = """
      .cam { position: absolute; inset: 0; transform-origin: 0 0; }
      .phone { position: absolute; left: 1060px; top: 50px; width: 480px; height: 980px; border-radius: 76px;
               background: #10202c; box-shadow: 0 2px 6px rgba(16, 32, 44, .2), 0 60px 120px -40px rgba(36, 75, 107, .45); }
      .screen { position: absolute; left: 14px; top: 14px; width: 452px; height: 952px; border-radius: 62px; overflow: hidden;
                background: var(--bg); }
      .island { position: absolute; left: 171px; top: 14px; width: 110px; height: 32px; border-radius: 16px; background: #0b151d; z-index: 5; }
      .app { position: absolute; left: 0; top: 0; width: 390px; height: 821px; transform: scale(1.159); transform-origin: 0 0;
             font-family: var(--font); color: var(--ink);
             background: radial-gradient(60% 40% at 10% 5%, rgba(196, 246, 212, .7), rgba(196, 246, 212, 0) 70%), var(--bg); }
      .layer { position: absolute; inset: 0; }
      .a-status { height: 40px; }
      .a-head { display: flex; align-items: center; justify-content: space-between; padding: 4px 12px 10px; border-bottom: 1px solid var(--line); }
      .a-brand { display: flex; align-items: center; gap: 7px; font-weight: 700; font-size: 17px; }
      .a-mark { width: 26px; height: 26px; display: block; background: url("assets/icon.svg") center / contain no-repeat; }
      .a-pills span { display: inline-block; border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 5px 10px;
                      font-size: 12px; font-weight: 700; margin-left: 5px; }
      .a-body { padding: 14px 16px; }
      .a-pack { font-size: 14px; font-weight: 700; color: var(--muted); margin-bottom: 10px; }
      .a-card { position: relative; border-radius: 14px; padding: 12px 14px 13px 19px; margin-bottom: 10px; overflow: hidden; }
      .a-card::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 5px; background: var(--bar); }
      .a-who { font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--who); margin-bottom: 5px; }
      .a-card p { font-size: 17px; font-weight: 700; line-height: 1.38; }
      .a-stop { background: var(--stop-bg); --bar: var(--stop); --who: var(--stop); }
      .a-unsure { background: var(--unsure-bg); --bar: var(--unsure-line); --who: var(--unsure); }
      .a-h { font-family: var(--display); font-weight: 800; font-size: 21px; line-height: 1.18; margin: 14px 0 10px; }
      .a-tile { position: relative; display: flex; align-items: center; gap: 11px; border-radius: 14px; padding: 10px 12px; margin-bottom: 8px; border: 1px solid; }
      .a-tile.stop { background: var(--stop-bg); border-color: var(--stop); }
      .a-tile.unsure { background: var(--unsure-bg); border-color: var(--unsure-line); }
      .a-disc { width: 26px; height: 26px; border-radius: 999px; flex: none; display: flex; align-items: center; justify-content: center;
                font-weight: 800; font-size: 16px; }
      .stop .a-disc { background: var(--stop); color: #fff; }
      .unsure .a-disc { background: var(--unsure-line); color: var(--unsure); }
      .a-t { font-size: 15px; font-weight: 700; line-height: 1.3; }
      .a-c { font-size: 13px; font-weight: 600; margin-top: 2px; }
      .stop .a-c { color: var(--stop); } .unsure .a-c { color: var(--unsure); }
      .a-chev { margin-left: auto; width: 18px; height: 18px; flex: none; display: block; }
      .a-note { border-radius: 14px; border: 1px solid var(--unsure-line); background: var(--unsure-bg); padding: 12px 14px; font-size: 14px; line-height: 1.45; color: var(--unsure); }
      .a-btn { display: inline-block; margin-top: 10px; background: #fff; border: 1px solid var(--muted); border-radius: 999px; padding: 9px 16px;
               font-size: 14px; font-weight: 700; color: var(--ink); }
      .a-back { font-size: 15px; font-weight: 700; color: var(--brand); margin-bottom: 14px; }
      .a-title { font-family: var(--display); font-weight: 800; font-size: 25px; line-height: 1.15; margin: 4px 0 10px; }
      .a-pill { display: inline-block; border-radius: 999px; padding: 4px 10px; font-size: 13px; font-weight: 700; background: var(--stop-bg); color: var(--stop); }
      .a-notice { position: relative; margin: 12px 0 14px; border-radius: 14px; border: 1px solid var(--stop); background: var(--stop-bg);
                  padding: 11px 14px 12px 19px; font-size: 14px; line-height: 1.45; overflow: hidden; }
      .a-notice::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 5px; background: var(--stop); }
      .a-k { font-size: 11px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 12px 0 4px; }
      .a-v { font-size: 15px; line-height: 1.45; }
      .a-quote { font-size: 15px; line-height: 1.45; font-style: normal; }
      /* camera */
      .a-cam { position: absolute; inset: 0; background: #0f1c26; }
      .a-photo { position: absolute; left: 36px; top: 170px; width: 318px; padding: 18px 18px 22px; border-radius: 10px; background: #fffaf0;
                 font-size: 13px; line-height: 1.5; color: #3b3a33; }
      .a-photo b { font-weight: 700; }
      .a-frame { position: absolute; left: 22px; top: 156px; width: 346px; height: 230px; display: block; }
      .a-corner { position: absolute; width: 40px; height: 40px; border: 0 solid #6dc88f; display: block; }
      .k1 { left: 0; top: 0; border-top-width: 4px; border-left-width: 4px; border-top-left-radius: 14px; }
      .k2 { right: 0; top: 0; border-top-width: 4px; border-right-width: 4px; border-top-right-radius: 14px; }
      .k3 { left: 0; bottom: 0; border-bottom-width: 4px; border-left-width: 4px; border-bottom-left-radius: 14px; }
      .k4 { right: 0; bottom: 0; border-bottom-width: 4px; border-right-width: 4px; border-bottom-right-radius: 14px; }
      .a-shutter { position: absolute; left: 160px; top: 690px; width: 70px; height: 70px; border-radius: 999px; border: 5px solid #fff;
                   display: block; }
      .a-shutter i { position: absolute; inset: 5px; border-radius: 999px; background: #fff; display: block; }
      .a-flash { position: absolute; inset: 0; background: #fff; display: block; opacity: 0; }
      /* waiting */
      .a-wait { display: flex; flex-direction: column; align-items: center; padding: 50px 26px 0; text-align: center; }
      .a-wdisc { width: 88px; height: 88px; border-radius: 999px; background: #f1eee2; display: flex; align-items: center; justify-content: center; }
      .a-bars { display: flex; gap: 6px; margin: 22px 0 18px; }
      .a-bar { width: 116px; height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; display: block; }
      .a-bar i { display: block; width: 100%; height: 100%; background: #6aa9a0; transform-origin: 0 50%; }
      .a-wt { position: relative; width: 100%; height: 36px; }
      .a-wt span { position: absolute; left: 0; right: 0; top: 0; font-family: var(--display); font-weight: 800; font-size: 22px; }
      .a-wb { font-size: 15px; line-height: 1.5; color: var(--muted); margin-top: 6px; }
      .a-sec { position: relative; width: 60px; height: 24px; margin-top: 16px; }
      .a-sec span { position: absolute; left: 0; right: 0; top: 0; font-size: 15px; color: var(--ink); opacity: 0; }
      .a-sec .on { opacity: 1; }
      .finger { position: absolute; right: 60px; top: 50%; width: 44px; height: 44px; margin-top: -22px; border-radius: 999px;
                background: rgba(36, 75, 107, .28); border: 2px solid rgba(255, 255, 255, .9); display: block; }
      /* words on the left */
      .left { position: absolute; left: 140px; top: 0; width: 720px; height: 1080px; }
      .k { position: absolute; left: 0; top: 50%; width: 720px; font-family: var(--display); font-weight: 800; font-size: 112px;
           line-height: 1.02; letter-spacing: -0.02em; color: var(--ink); transform: translateY(-50%); }
      .k .w, .w { display: inline-block; margin-right: .24em; }
      .k em { font-style: normal; color: var(--brand); }
"""

LABEL_TEXT = ("Wheat flour (maida), Sugar, Edible vegetable oil (palm), Hydrogenated vegetable fat, Milk solids, "
              "Invert syrup, Raising agents (503(ii), 500(ii)), Iodised salt, Colour (102), "
              "Flour treatment agent (924a), Emulsifier (322).")

HEAD = """<div class="a-status"></div>
            <div class="a-head"><div class="a-brand"><i class="a-mark"></i>InsideLabel</div>
              <div class="a-pills"><span>Compare</span><span>Household</span></div></div>"""

CHEV = '<svg class="a-chev" viewBox="0 0 24 24" fill="none" stroke="#244b6b" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6" /></svg>'
PACK_ICON = ('<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#57768c" stroke-width="2" stroke-linecap="round" '
             'stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="2" /><path d="M5 9h14M9 13h6M9 16h4" /></svg>')


def camera(c, blurred=False):
    blur = ' style="filter: blur(2.6px)"' if blurred else ""
    photo_id = f' id="{c}-photo"'
    return f"""<div class="layer a-cam" id="{c}-cam-screen" data-layout-allow-overlap data-layout-allow-occlusion>
            <div class="a-photo"{photo_id}{blur}><b>INGREDIENTS:</b> {LABEL_TEXT}</div>
            <div class="a-frame" id="{c}-frame"><span class="a-corner k1"></span><span class="a-corner k2"></span><span class="a-corner k3"></span><span class="a-corner k4"></span></div>
            <div class="a-shutter" id="{c}-shutter"><i></i></div>
            <span class="a-flash" id="{c}-flash"></span>
          </div>"""


def waiting(c, title_on, secs, first_on):
    titles = "".join(f'<span id="{c}-wt{i}" style="opacity:{1 if i == title_on else 0}">{t}</span>'
                     for i, t in enumerate(["Sending the photo…", "Reading the ingredient list…"]))
    on = ' class="on"'
    secs_html = "".join(f'<span id="{c}-s{n}"{on if n == first_on else ""}>{n} s</span>' for n in secs)
    return f"""<div class="layer" id="{c}-wait" data-layout-allow-overlap data-layout-allow-occlusion>{HEAD}
            <div class="a-wait"><div class="a-wdisc">{PACK_ICON}</div>
              <div class="a-bars"><span class="a-bar"><i id="{c}-b1"></i></span><span class="a-bar"><i id="{c}-b2"></i></span></div>
              <div class="a-wt">{titles}</div>
              <p class="a-wb">The first read of a pack takes about 8 to 15 seconds. Once a pack is in our catalogue, its barcode gives the result at once.</p>
              <div class="a-sec">{secs_html}</div></div>
          </div>"""


def result(c, finger=False):
    f = f'<span class="finger" id="{c}-finger"></span>' if finger else ""
    return f"""<div class="layer" id="{c}-result" data-layout-allow-overlap data-layout-allow-occlusion>{HEAD}
            <div class="a-body">
              <div class="a-pack {c}-r">Sample biscuits</div>
              <div class="a-card a-stop {c}-r" id="{c}-allergen"><div class="a-who">You</div><p>Contains milk. It's on your avoid list.</p></div>
              <div class="a-h {c}-r2">Has Potassium bromate, an additive with higher concern.</div>
              <div class="a-tile stop {c}-r2" id="{c}-tile1"><span class="a-disc">&#215;</span><div><div class="a-t">Potassium bromate (flour treatment 924a)</div><div class="a-c">Not permitted in India</div></div>{CHEV}{f}</div>
              <div class="a-tile unsure {c}-r2"><span class="a-disc">!</span><div><div class="a-t">Tartrazine (colour 102)</div><div class="a-c">Worth knowing</div></div>{CHEV}</div>
              <div class="a-tile unsure {c}-r2"><span class="a-disc">!</span><div><div class="a-t">Hydrogenated fat</div><div class="a-c">4th of 11</div></div>{CHEV}</div>
            </div>
          </div>"""


def tile_page(c):
    return f"""<div class="layer" id="{c}-page" data-layout-allow-overlap data-layout-allow-occlusion>{HEAD}
            <div class="a-body">
              <div class="a-back">&#8249; Back to the result</div>
              <div class="a-pack">Sample biscuits</div>
              <div class="a-title">Potassium bromate (flour treatment 924a)</div>
              <span class="a-pill">Not permitted in India</span>
              <div class="a-notice">An additive on this label isn't in FSSAI's permitted list. We read "INS 924a" on the label. Check the pack: if we misread it, tap Report a mistake.</div>
              <div class="a-k">What it is</div><div class="a-v">Potassium bromate is a flour treatment, INS 924a.</div>
              <div class="a-k">What the sources say</div><div class="a-v">Flour treatment agent. Not permitted as a food additive in India.</div>
              <div id="{c}-onlabel"><div class="a-k">On the label</div><div class="a-quote">“Flour treatment agent (924a)”</div></div>
            </div>
          </div>"""


def unsure(c):
    return f"""<div class="layer" id="{c}-unsure" data-layout-allow-overlap data-layout-allow-occlusion>{HEAD}
            <div class="a-body">
              <div class="a-pack {c}-u">Sample biscuits</div>
              <div class="a-card a-unsure {c}-u" id="{c}-ucard"><div class="a-who">You</div><p>We couldn't read the label clearly enough to check for milk. Please retake the ingredients photo.</p></div>
              <div class="a-h {c}-u">We could read only part of the ingredient list.</div>
              <div class="a-note {c}-u">Part of the ingredient list was cut off or hard to read. Retake it to check the rest.<br /><span class="a-btn">Retake the ingredients photo</span></div>
            </div>
          </div>"""


def phone(c, layers):
    return f"""<div class="cam" id="{c}-camw" data-layout-allow-overflow>
        <div class="phone"><div class="screen"><div class="island"></div><div class="app">
          {layers}
        </div></div></div>
      </div>"""


def words(c, lines):
    out = []
    for i, html in enumerate(lines):
        out.append(f'<div class="k" id="{c}-k{i}">{html}</div>')
    return '<div class="left">' + "".join(out) + "</div>"


def w(text):
    return "".join(f'<span class="w">{x}</span>' for x in text.split())


# Shared timeline helpers, written into every scene script.
JS_HELPERS = """
      const E = { duration: 0.6, ease: "power3.out" };
      function wordsIn(tl, sel, t) {
        tl.fromTo(sel + " .w", { opacity: 0, y: 46 }, { opacity: 1, y: 0, stagger: 0.09, duration: 0.55, ease: "power3.out" }, t);
      }
      function wordsOut(tl, sel, t) {
        tl.to(sel + " .w", { opacity: 0, y: -40, stagger: 0.04, duration: 0.3, ease: "power2.in" }, t);
      }
      // zoom-to-target: put canvas point (px, py) at (tx, ty) at scale k (camera origin 0 0).
      // (px, py) come from src/measure.mjs: a paused render may not have laid the scene out yet.
      function zoomTo(tl, cam, px, py, k, tx, ty, t, d) {
        tl.to(cam, { scale: k, x: tx - k * px, y: ty - k * py, duration: d, ease: "power3.inOut" }, t);
      }
      function zoomOut(tl, cam, t, d) {
        tl.to(cam, { scale: 1, x: 0, y: 0, duration: d, ease: "power3.inOut" }, t);
      }"""


def comp(c, dur, body, script, extra_css=""):
    return f"""<!doctype html>
<html lang="en">
  <head><meta charset="UTF-8" /><!-- generated by src/build_landscape.py; read MOTION.md first --></head>
  <body>
    <template>
      <style>{FONTS}
      #{c} {{ position: absolute; inset: 0; overflow: hidden; font-family: var(--font); color: var(--ink);{TOKENS}
      }}{CSS}{extra_css}
      </style>
      <div id="{c}" data-composition-id="{c}" data-width="1920" data-height="1080" data-duration="{dur}">
      {body}
      </div>
      <script>
      document.fonts.ready.then(() => {{{JS_HELPERS}
      const tl = gsap.timeline({{ paused: true }});
      const cam = document.getElementById("{c}-camw");
{script}
      window.__timelines["{c}"] = tl;
      }});
      </script>
    </template>
  </body>
</html>
"""


scenes = []

# 1. Hook, then the photo (0 to 11): the viewer hunts for the milk in a real-size label, then the
#    label shrinks into the phone's camera (scale-swap), and one photo is taken.
c = "c1"
macro_css = """
      #c1-macro { position: absolute; inset: 0; background: #fffaf0; padding: 90px 150px; display: block; }
      #c1-macro p { font-size: 50px; line-height: 1.42; color: #3b3a33; font-weight: 400; margin-bottom: 26px; }
      #c1-macro b { font-weight: 700; letter-spacing: .02em; }
      #c1-q { position: absolute; left: 150px; bottom: 110px; background: var(--ink); color: #fff; border-radius: 36px; padding: 30px 52px 36px;
              font-family: var(--display); font-weight: 800; font-size: 96px; letter-spacing: -0.02em; }
      #c1-q .w { display: inline-block; margin-right: .24em; }"""
body = (phone(c, camera(c) + waiting(c, 0, range(1, 5), 0)) +
        words(c, [w("One photo.")]) +
        f'<div id="c1-macro" data-layout-allow-overlap><p><b>INGREDIENTS:</b> {LABEL_TEXT}</p><p>Contains permitted synthetic food colour and added flavours (nature identical flavouring substances). Store in a cool and dry place. Best before 6 months from manufacture.</p><div id="c1-q">{w("Can you find the milk?")}</div></div>')
script = """
      tl.fromTo("#c1-q", { opacity: 0, y: 40 }, { opacity: 1, y: 0, ...E }, 0.3);
      tl.fromTo("#c1-q .w", { opacity: 0 }, { opacity: 1, stagger: 0.12, duration: 0.4, ease: "power2.out" }, 0.4);
      tl.to("#c1-q", { opacity: 0, y: 30, duration: 0.3, ease: "power2.in" }, 3.5);
      // scale-swap: the whole label shrinks into the phone's viewfinder
      tl.fromTo("#c1-macro", { scale: 1, x: 0, y: 0, opacity: 1 }, { scale: 0.19, x: 340, y: -120, duration: 1.3, ease: "power3.inOut" }, 3.8);
      tl.to("#c1-macro", { opacity: 0, duration: 0.3, ease: "power2.in" }, 4.85);
      // card-morph-anchor: the viewfinder's own photo appears only as the shrinking label fades
      tl.fromTo("#c1-photo", { opacity: 0 }, { opacity: 1, duration: 0.35, ease: "power2.out" }, 5.15);
      tl.fromTo("#c1 .phone", { opacity: 0, y: 80 }, { opacity: 1, y: 0, duration: 0.9, ease: "power3.out" }, 4.2);
      wordsIn(tl, "#c1-k0", 5.0);
      tl.fromTo("#c1-frame", { opacity: 0, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.7, ease: "power3.out" }, 5.4);
      tl.to("#c1-shutter", { scale: 0.88, duration: 0.12, ease: "power2.in" }, 6.5);
      tl.to("#c1-shutter", { scale: 1, duration: 0.3, ease: "power3.out" }, 6.62);
      tl.to("#c1-flash", { opacity: 0.85, duration: 0.1, ease: "power2.out" }, 6.6);
      tl.to("#c1-flash", { opacity: 0, duration: 0.45, ease: "power2.in" }, 6.72);
      tl.to("#c1-cam-screen", { opacity: 0, duration: 0.25, ease: "power2.inOut" }, 7.1);
      tl.to("#c1-wait", { opacity: 1, duration: 0.25, ease: "power2.inOut" }, 7.1);
      tl.fromTo("#c1-b1", { scaleX: 0 }, { scaleX: 1, duration: 1.8, ease: "power1.inOut" }, 7.2);
      tl.set("#c1-s1", { opacity: 1 }, 7.2);
      for (let n = 2; n <= 4; n++) { tl.set("#c1-s" + (n - 1), { opacity: 0 }, 6.2 + n); tl.set("#c1-s" + n, { opacity: 1 }, 6.2 + n); }
      tl.set("#c1-wt0", { opacity: 0 }, 9.0);
      tl.set("#c1-wt1", { opacity: 1 }, 9.0);
      tl.fromTo("#c1-b2", { scaleX: 0 }, { scaleX: 0.35, duration: 2.0, ease: "none" }, 9.0);
      wordsOut(tl, "#c1-k0", 10.55);"""
scenes.append((c, 0, 11, body, script, macro_css))

# 2. AI reads, rules decide (11 to 17): the read becomes quoted chips; then each gets the rule's tag.
c = "c2"
rows_css = """
      #c2-rows { position: absolute; left: 140px; top: 600px; width: 840px; display: flex; flex-direction: column; gap: 22px; }
      .row { display: flex; align-items: center; gap: 22px; }
      .q { display: block; background: #fff; border: 2px solid var(--line); border-radius: 999px; padding: 12px 26px; font-size: 32px; font-weight: 600;
           color: var(--ink); box-shadow: 0 10px 30px -14px rgba(36, 75, 107, .3); }
      .arrow { width: 40px; height: 40px; flex: none; display: block; }
      .tag { display: block; border-radius: 999px; padding: 12px 24px; font-size: 30px; font-weight: 700; }
      .tag.stop { background: var(--stop-bg); color: var(--stop); }
      .tag.unsure { background: var(--unsure-bg); color: var(--unsure); }
      #c2-src { position: absolute; left: 140px; top: 968px; font-size: 28px; color: var(--muted); }
      #c2-left .k { top: 330px; font-size: 104px; }"""
ARROW = '<svg class="arrow" viewBox="0 0 24 24" fill="none" stroke="#57768c" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>'
rows = [("“Milk solids”", "stop", "On your avoid list"),
        ("“Colour (102)”", "unsure", "Worth knowing"),
        ("“Flour treatment agent (924a)”", "stop", "Not permitted in India")]
rows_html = "".join(f'<div class="row"><span class="q c2-q">{q}</span><span class="c2-t" style="display:flex;align-items:center;gap:22px">{ARROW}<span class="tag {k}">{t}</span></span></div>'
                    for q, k, t in rows)
body = (phone(c, waiting(c, 1, range(4, 11), 4)) +
        f'<div class="left" id="c2-left"><div class="k" id="c2-k0">{w("AI reads.")}</div><div class="k" id="c2-k1">{w("Rules <em>decide.</em>")}</div></div>' +
        f'<div id="c2-rows">{rows_html}</div><div id="c2-src">Rules checked against FSSAI\'s regulations.</div>')
script = """
      tl.set("#c2-b1", { scaleX: 1 }, 0);
      tl.fromTo("#c2-b2", { scaleX: 0.35 }, { scaleX: 0.95, duration: 6, ease: "none" }, 0);
      for (let n = 5; n <= 10; n++) { tl.set("#c2-s" + (n - 1), { opacity: 0 }, n - 4.8); tl.set("#c2-s" + n, { opacity: 1 }, n - 4.8); }
      wordsIn(tl, "#c2-k0", 0.15);
      tl.fromTo(".c2-q", { opacity: 0, x: -40 }, { opacity: 1, x: 0, stagger: 0.32, ...E }, 0.7);
      wordsOut(tl, "#c2-k0", 2.4);
      wordsIn(tl, "#c2-k1", 2.65);
      tl.fromTo(".c2-t", { opacity: 0, x: -24 }, { opacity: 1, x: 0, stagger: 0.38, ...E }, 3.1);
      tl.fromTo("#c2-src", { opacity: 0 }, { opacity: 1, duration: 0.5, ease: "power2.out" }, 4.5);
      tl.to("#c2-left, #c2-rows, #c2-src", { opacity: 0, y: -30, duration: 0.35, ease: "power2.in" }, 5.6);"""
scenes.append((c, 11, 6, body, script, rows_css))

# 3. The result (17 to 25): the allergen line arrives first; the camera goes to it and holds.
c = "c3"
body = (phone(c, waiting(c, 1, [10], 10) + result(c)) +
        words(c, [w("Your avoid list <em>first.</em>")]))
script = """
      tl.set("#c3-b1", { scaleX: 1 }, 0);
      tl.set("#c3-b2", { scaleX: 0.95 }, 0);
      tl.to("#c3-b2", { scaleX: 1, duration: 0.25, ease: "power2.out" }, 0.05);
      tl.to("#c3-wait", { opacity: 0, duration: 0.25, ease: "power2.inOut" }, 0.3);
      tl.to("#c3-result", { opacity: 1, duration: 0.25, ease: "power2.inOut" }, 0.3);
      // MOTION.md: the allergen card only fades in with a small rise, then holds still
      tl.fromTo(".c3-r", { opacity: 0, y: 14 }, { opacity: 1, y: 0, stagger: 0.12, ...E }, 0.4);
      zoomTo(tl, cam, 1300, 248, 1.7, 1330, 520, 1.0, 1.0);   // #c3-allergen
      wordsIn(tl, "#c3-k0", 1.5);
      zoomOut(tl, cam, 4.4, 1.0);
      tl.fromTo(".c3-r2", { opacity: 0, y: 18 }, { opacity: 1, y: 0, stagger: 0.14, ...E }, 5.0);
      wordsOut(tl, "#c3-k0", 7.45);"""
scenes.append((c, 17, 8, body, script, ""))

# 4. Tap a tile (25 to 31): the page quotes the label, word for word.
c = "c4"
body = (phone(c, result(c, finger=True) + tile_page(c)) +
        words(c, [w("We quote <em>the</em> <em>label.</em>")]))
script = """
      tl.fromTo("#c4-finger", { opacity: 0, scale: 1.4 }, { opacity: 1, scale: 1, duration: 0.4, ease: "power3.out" }, 0.4);
      tl.to("#c4-finger", { scale: 0.8, duration: 0.12, ease: "power2.in" }, 0.95);
      tl.to("#c4-tile1", { scale: 0.98, duration: 0.1, ease: "power2.in" }, 0.95);
      tl.to("#c4-tile1", { scale: 1, duration: 0.2, ease: "power3.out" }, 1.07);
      tl.to("#c4-finger", { opacity: 0, scale: 1.2, duration: 0.3, ease: "power2.out" }, 1.1);
      tl.to("#c4-result", { opacity: 0, x: -30, duration: 0.3, ease: "power2.in" }, 1.25);
      tl.fromTo("#c4-page", { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.45, ease: "power3.out" }, 1.4);
      wordsIn(tl, "#c4-k0", 1.6);
      zoomTo(tl, cam, 1300, 600, 1.7, 1330, 560, 2.3, 1.0);   // between the notice and #c4-onlabel (653)
      zoomOut(tl, cam, 5.0, 0.8);
      wordsOut(tl, "#c4-k0", 5.45);"""
scenes.append((c, 25, 6, body, script, ""))

# 5. A blurry photo (31 to 37): the app says it can't confirm, rather than guess.
c = "c5"
body = (phone(c, camera(c, blurred=True) + unsure(c)) +
        words(c, [w("Blurry photo?"), w("We won't <em>guess.</em>")]))
script = """
      tl.fromTo("#c5-cam-screen", { opacity: 0 }, { opacity: 1, duration: 0.35, ease: "power2.out" }, 0.0);
      wordsIn(tl, "#c5-k0", 0.2);
      tl.fromTo("#c5-frame", { opacity: 0, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.6, ease: "power3.out" }, 0.3);
      tl.to("#c5-shutter", { scale: 0.88, duration: 0.12, ease: "power2.in" }, 1.2);
      tl.to("#c5-shutter", { scale: 1, duration: 0.3, ease: "power3.out" }, 1.32);
      tl.to("#c5-flash", { opacity: 0.85, duration: 0.1, ease: "power2.out" }, 1.3);
      tl.to("#c5-flash", { opacity: 0, duration: 0.45, ease: "power2.in" }, 1.42);
      tl.to("#c5-cam-screen", { opacity: 0, duration: 0.3, ease: "power2.inOut" }, 1.9);
      tl.to("#c5-unsure", { opacity: 1, duration: 0.3, ease: "power2.inOut" }, 1.9);
      tl.fromTo(".c5-u", { opacity: 0, y: 14 }, { opacity: 1, y: 0, stagger: 0.12, ...E }, 2.0);
      wordsOut(tl, "#c5-k0", 2.2);
      wordsIn(tl, "#c5-k1", 2.45);
      zoomTo(tl, cam, 1300, 275, 1.6, 1330, 520, 2.6, 1.0);   // #c5-ucard
      tl.to("#c5 .phone", { opacity: 0, y: 60, duration: 0.45, ease: "power2.in" }, 5.5);
      wordsOut(tl, "#c5-k1", 5.45);"""
scenes.append((c, 31, 6, body, script, ""))

# 6. Close (37 to 41).
c = "c6"
end_css = """
      #c6-end { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 34px; text-align: center; }
      #c6-end img { width: 170px; height: 170px; display: block; }
      #c6-t { font-family: var(--display); font-weight: 800; font-size: 120px; letter-spacing: -0.02em; line-height: 1.05; }
      #c6-t .w { display: inline-block; margin: 0 .12em; }
      #c6-url { font-size: 46px; font-weight: 700; color: var(--brand); }"""
tagline = w("See what's inside the pack")
body = f'<div class="cam" id="c6-camw"></div><div id="c6-end"><img id="c6-logo" src="assets/icon.svg" alt="" /><div id="c6-t">{tagline}</div><div id="c6-url">insidelabel.ai</div></div>'
script = """
      tl.fromTo("#c6-logo", { opacity: 0, scale: 0.86 }, { opacity: 1, scale: 1, duration: 0.7, ease: "power3.out" }, 0.1);
      wordsIn(tl, "#c6-t", 0.45);
      tl.fromTo("#c6-url", { opacity: 0, y: 20 }, { opacity: 1, y: 0, ...E }, 1.3);"""
scenes.append((c, 37, 4, body, script, end_css))

GROUND = f"""<!doctype html>
<html lang="en">
  <head><meta charset="UTF-8" /><!-- generated by src/build_landscape.py --></head>
  <body>
    <template>
      <style>
      #ground {{ position: absolute; inset: 0; background: #fbf9ee; overflow: hidden; }}
      .glow {{ position: absolute; border-radius: 50%; display: block; }}
      #glow-mint {{ width: 1400px; height: 1100px; left: -420px; top: -460px;
                   background: radial-gradient(closest-side, rgba(196, 246, 212, .85), rgba(196, 246, 212, 0)); }}
      #glow-blue {{ width: 1300px; height: 1100px; right: -300px; bottom: -520px;
                   background: radial-gradient(closest-side, rgba(201, 227, 236, .9), rgba(201, 227, 236, 0)); }}
      </style>
      <div id="ground" data-composition-id="ground" data-width="1920" data-height="1080" data-duration="{TOTAL}">
        <span class="glow" id="glow-mint" data-layout-allow-overflow></span>
        <span class="glow" id="glow-blue" data-layout-allow-overflow></span>
      </div>
      <script>
      // HIG audit: the ground never moves (a stationary frame of reference)
      window.__timelines["ground"] = gsap.timeline({{ paused: true }});
      </script>
    </template>
  </body>
</html>
"""

comps = ROOT / "compositions"
for f in comps.glob("*.html"):
    f.unlink()
(comps / "ground.html").write_text(GROUND)
hosts = [f'      <div id="ground-host" data-composition-id="ground" data-composition-src="compositions/ground.html" '
         f'data-start="0" data-duration="{TOTAL}" data-track-index="0" data-width="1920" data-height="1080"></div>']
HIDDEN = ["c1-wait", "c3-result", "c4-page", "c5-unsure"]
for c, start, dur, body, script, extra in scenes:
    for h in HIDDEN:
        body = body.replace(f'id="{h}" data-layout', f'id="{h}" style="opacity:0" data-layout')
    (comps / f"{c}.html").write_text(comp(c, dur, body, script, extra))
    hosts.append(f'      <div id="{c}-host" data-composition-id="{c}" data-composition-src="compositions/{c}.html" '
                 f'data-start="{start}" data-duration="{dur}" data-track-index="1" data-width="1920" data-height="1080"></div>')

(ROOT / "index.html").write_text(f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>How InsideLabel checks a label</title>
    <!-- generated by src/build_landscape.py. Style: MOTION.md. Every sentence: BRIEF.md source table. -->
    <script src="assets/gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: 1920px; height: 1080px; overflow: hidden; background: #fbf9ee; }}
      #root {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #fbf9ee; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{TOTAL}" data-width="1920" data-height="1080">
{chr(10).join(hosts)}
      <audio id="music" src="assets/music.m4a" data-start="0" data-duration="{TOTAL}" data-track-index="2" data-volume="1"></audio>
    </div>
    <script>
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
""")
print("built", len(scenes), "scenes,", TOTAL, "s")

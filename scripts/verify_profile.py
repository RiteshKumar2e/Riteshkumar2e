#!/usr/bin/env python3
"""Verify the generated profile SVGs.

Static lint, then real-browser renders (Chrome via Playwright):
  * SVG document frozen at t = 0, 2, 5, 9, 13 s (SMIL + CSS clocks)
  * animation removed (CSS animation:none + SMIL elements deleted)
  * prefers-reduced-motion: reduce
  * as <img> elements at README width (830px) and phone width (375px)
Collects every network request, checks transparency outside the rounded
card, text bounds and text overlaps, and writes contact sheets.

Run:  python scripts/verify_profile.py OUT_DIR
"""
from __future__ import annotations

import base64
import io
import re
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
NAMES = ["hero", "about-life", "stack", "id-dashboard", "connect"]
PREFIX = {"hero": "hr", "about-life": "ab", "stack": "st", "id-dashboard": "id", "connect": "cn"}
TIMES = [0, 2, 5, 9, 13]

problems: list[str] = []


def fail(msg: str):
    problems.append(msg)
    print("  FAIL", msg)


def lint(name: str, svg: str):
    p = PREFIX[name]
    if re.search(r"<script|<foreignObject|\son[a-z]+=", svg, re.I):
        fail(f"{name}: script/foreignObject/event handler present")
    for m in re.finditer(r'(?:href|src)="([^"#][^"]*)"|url\((?!#|data:)([^)]*)\)', svg):
        ref = m.group(1) or m.group(2)
        if not ref.startswith("data:"):
            fail(f"{name}: external reference {ref[:80]}")
    if re.search(r"@import|https?://(?!www\.w3\.org/)", svg):
        fail(f"{name}: http(s) URL or @import in document")
    ids = re.findall(r'\sid="([^"]+)"', svg)
    bad = [i for i in ids if not i.startswith(p + "-")]
    if bad:
        fail(f"{name}: un-namespaced ids {bad[:5]}")
    if len(ids) != len(set(ids)):
        fail(f"{name}: duplicate ids")
    for b in re.findall(r'begin="([^"]*)"', svg):
        if b != "0s":
            fail(f"{name}: SMIL begin={b}")
    for decl in re.findall(r"animation:([^;}]+)", svg):
        if "none" in decl:
            continue
        if "both" not in decl:
            fail(f"{name}: animation without fill-mode both: {decl}")
    # embedded images: decode and report alpha
    for uri in re.findall(r'xlink:href="data:image/png;base64,([^"]+)"', svg):
        im = Image.open(io.BytesIO(base64.b64decode(uri)))
        info = f"{im.mode} {im.size}"
        if im.mode == "RGBA":
            a = im.getchannel("A")
            hist = a.histogram()
            info += f" alpha: {hist[0] / sum(hist):.1%} fully transparent"
        print(f"    image {info}")
    fonts = re.findall(r"font-family:'(RK\w+)';font-weight:(\d+)", svg)
    print(f"    fonts {fonts}  size {len(svg.encode()) / 1024:,.0f} KB")


FREEZE = """t => {
  const s = document.documentElement;
  if (s.pauseAnimations) { s.pauseAnimations(); s.setCurrentTime(t); }
  for (const a of document.getAnimations({subtree: true})) { a.pause(); a.currentTime = t * 1000; }
}"""

STRIP = """() => {
  const st = document.createElementNS('http://www.w3.org/2000/svg', 'style');
  st.textContent = '*{animation:none!important}';
  document.documentElement.appendChild(st);
  document.querySelectorAll('animate,animateTransform,animateMotion,set').forEach(e => e.remove());
}"""

# Visible text boxes (ignores <defs> originals; opacity-0 groups count as hidden).
TEXTS = """() => {
  const out = [];
  for (const t of document.querySelectorAll('text')) {
    if (t.closest('defs')) continue;
    if (!t.checkVisibility({opacityProperty: true, visibilityProperty: true})) continue;
    let o = 1, n = t;
    while (n && n.nodeType === 1) { o *= parseFloat(getComputedStyle(n).opacity || 1); n = n.parentElement; }
    if (o < 0.05) continue;
    const r = t.getBoundingClientRect();
    out.push({s: t.textContent.slice(0, 40), x: r.x, y: r.y, w: r.width, h: r.height});
  }
  return out;
}"""


def sheet(frames: list[tuple[str, Image.Image]], path: Path, cols: int = 2, scale: float = .5):
    ims = [(lbl, im.resize((int(im.width * scale), int(im.height * scale)))) for lbl, im in frames]
    w = max(i.width for _, i in ims)
    h = max(i.height for _, i in ims)
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (cols * (w + 12) + 12, rows * (h + 34) + 12), (40, 44, 52))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(out)
    for k, (lbl, im) in enumerate(ims):
        x, y = 12 + (k % cols) * (w + 12), 12 + (k // cols) * (h + 34)
        dr.text((x, y), lbl, fill=(255, 255, 255))
        bg = Image.new("RGB", im.size, (255, 255, 255))
        if im.mode == "RGBA":
            bg.paste(im, mask=im.getchannel("A"))
        else:
            bg = im.convert("RGB")
        out.paste(bg, (x, y + 18))
    out.save(path)


def overlaps(boxes, name, label):
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            ix = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
            iy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
            if ix > 2 and iy > 0.3 * min(a["h"], b["h"]):
                fail(f"{name} [{label}]: text overlap {a['s']!r} / {b['s']!r}")


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    print("== static lint")
    sizes = {}
    for n in NAMES:
        svg = (ROOT / "assets" / f"{n}.svg").read_text(encoding="utf8")
        m = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
        sizes[n] = (int(m.group(1)), int(m.group(2)))
        print(f"  {n}")
        lint(n, svg)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        requests: list[str] = []

        def track(page):
            page.on("request", lambda r: requests.append(r.url))

        for n in NAMES:
            W, H = sizes[n]
            url = (ROOT / "assets" / f"{n}.svg").as_uri()
            print(f"== {n} ({W}x{H})")
            frames = []
            for mode in ("timeline", "static", "reduced"):
                ctx = browser.new_context(viewport={"width": W, "height": H},
                                          reduced_motion="reduce" if mode == "reduced" else "no-preference")
                page = ctx.new_page()
                track(page)
                page.goto(url)
                page.evaluate("document.fonts.ready.then(() => document.fonts.size)")
                fonts_ok = page.evaluate("[...document.fonts].every(f => f.status === 'loaded')")
                if not fonts_ok:
                    fail(f"{n}: font faces not loaded")
                if mode == "timeline":
                    for t in TIMES:
                        page.evaluate(FREEZE, t)
                        page.wait_for_timeout(120)
                        png = page.screenshot(omit_background=True)
                        im = Image.open(io.BytesIO(png)).convert("RGBA")
                        im.save(out / f"{n}-t{t:02d}.png")
                        frames.append((f"t={t}s", im))
                        if t == 13:
                            boxes = page.evaluate(TEXTS)
                            overlaps(boxes, n, "t=13")
                else:
                    if mode == "static":
                        page.evaluate(STRIP)
                    page.wait_for_timeout(400)
                    png = page.screenshot(omit_background=True)
                    im = Image.open(io.BytesIO(png)).convert("RGBA")
                    im.save(out / f"{n}-{mode}.png")
                    frames.append((mode, im))
                    boxes = page.evaluate(TEXTS)
                    for b in boxes:
                        if b["x"] < 8 or b["y"] < 4 or b["x"] + b["w"] > W - 8 or b["y"] + b["h"] > H - 4:
                            fail(f"{n} [{mode}]: text near/over edge {b}")
                    overlaps(boxes, n, mode)
                    # transparency: outside rounded corner is clear, inside is opaque
                    a_out, a_in = im.getpixel((1, 1))[3], im.getpixel((W // 2, H // 2))[3]
                    if a_out != 0 or a_in != 255:
                        fail(f"{n} [{mode}]: transparency corner={a_out} centre={a_in}")
                ctx.close()
            sheet(frames, out / f"sheet-{n}.png")

        print("== as <img> (README 830px and phone 375px)")
        imgs = "".join(f'<img src="{(ROOT / "assets" / f"{n}.svg").as_uri()}?v=1" style="display:block;width:100%;margin:0 0 16px">'
                       for n in NAMES)
        html = out / "img-host.html"
        html.write_text(f"<!doctype html><body style='margin:0;padding:16px;background:#0d1117'>{imgs}</body>", encoding="utf8")
        for width in (830, 375):
            ctx = browser.new_context(viewport={"width": width + 32, "height": 4200})  # keep every image on-screen
            page = ctx.new_page()
            track(page)
            page.goto(html.as_uri())
            page.wait_for_load_state("load")
            ok = page.evaluate("[...document.images].every(i => i.complete && i.naturalWidth > 0)")
            if not ok:
                fail(f"img@{width}: an image failed to load")
            sw = page.evaluate("document.documentElement.scrollWidth")
            if sw > width + 32:
                fail(f"img@{width}: horizontal overflow {sw}")
            shots = [0, 2, 5, 9, 13] if width == 830 else [13]
            last = 0
            for t in shots:
                page.wait_for_timeout((t - last) * 1000)
                last = t
                page.screenshot(path=str(out / f"img{width}-t{t:02d}.png"), full_page=True)
            ctx.close()

        ext = [u for u in requests if not u.startswith(("file:", "data:"))]
        files = sorted({u.split("?")[0].rsplit("/", 1)[-1] for u in requests if u.startswith("file:")})
        print(f"  requests: {len(requests)} total; file: {files}")
        if ext:
            fail(f"external requests: {ext[:5]}")
        else:
            print("  external requests: 0")
        browser.close()

    print("== result")
    if problems:
        print(f"{len(problems)} problem(s)")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main(Path(sys.argv[1]))

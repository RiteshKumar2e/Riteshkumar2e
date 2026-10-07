#!/usr/bin/env python3
"""Build the animated GitHub profile: five self-contained SVGs, README.md,
preview.html and an upload-ready ZIP.

Inputs live in scripts/vendor (fonts, Simple Icons, LinkedIn brand mark) and
the two portraits at the repo root. Every SVG embeds its fonts (WOFF2) and
images (PNG) as data URIs, uses CSS + SMIL only, and makes no network requests.

Run:  python scripts/build_profile.py
"""
from __future__ import annotations

import base64
import io
import json
import math
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools import subset as ftsubset
from fontTools.ttLib import TTFont
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "scripts" / "vendor"
ASSETS = ROOT / "assets"
DIST = ROOT / "dist"

# ---------------------------------------------------------------- tokens ---
NAVY = "#070b16"
BLUE = "#247bff"
CRIMSON = "#ff354f"
INK = "#f3f0e8"      # off-white text
MUTED = "#a6afc4"
DIM = "#76809a"
CARD_INK = "#0b1020"  # dark text on the light ID card

# Facts supplied by the user, plus GitHub API data read on AS_OF.
AS_OF = "07 Oct 2026"
PERSON = {
    "name": "Ritesh Kumar",
    "github": "RiteshKumar2e",
    "role": "Research Intern",
    "lab": "Machine Vision & Intelligence Lab",
    "org": "NIT Jamshedpur",
    "location": "Jamshedpur, Jharkhand, India",
    "pitch": ("AI/ML and software developer building practical computer vision, "
              "intelligent automation, and AI-powered applications."),
    "roles": ["ML Engineer", "AI/ML Engineer", "Computer Vision Engineer", "Software Engineer"],
}
GH_API = {"public_repos": 77, "member_since": "Aug 2023"}  # api.github.com/users/RiteshKumar2e
LINKS = [
    # (key, platform, display text, href)
    ("linkedin", "LinkedIn", "linkedin.com/in/riteshkumar-tech", "https://linkedin.com/in/riteshkumar-tech"),
    ("github", "GitHub", "github.com/RiteshKumar2e", "https://github.com/RiteshKumar2e"),
    ("gmail", "Email", "riteshkumar90359@gmail.com", "mailto:riteshkumar90359@gmail.com"),
    ("globe", "Portfolio", "riteshkr.info", "https://riteshkr.info"),
]
PROJECTS = [
    # (name, description, highlights, repo, primary language per GitHub API)
    ("QuickFix",
     "AI-powered troubleshooting platform that helps users identify technical problems "
     "and provides actionable, step-by-step solutions.",
     "AI troubleshooting · step-by-step fixes",
     "customer-complaint-agent_new", "Python"),
    ("Steel Defect Detection",
     "Deep-learning computer vision system for detecting and classifying surface defects "
     "in steel using CNNs, MobileNetV2, FPN, and attention-based feature processing.",
     "CNNs · MobileNetV2 · FPN · attention",
     "Steel_Surface_Defect_NEU_DET-DATASET", "Jupyter Notebook"),
    ("Community AI",
     "AI-powered community platform that helps users connect, share knowledge, discover "
     "relevant information, and receive intelligent assistance.",
     "Community knowledge · AI assistance",
     "Community-Empowering-2.0", "JavaScript"),
]
LANG_COLORS = {"Python": "#3572A5", "Jupyter Notebook": "#DA5B0B", "JavaScript": "#f1e05a"}

# ----------------------------------------------------------------- fonts ---
FONT_FILES = {
    "d5": "space-grotesk-latin-500-normal.woff2",
    "d7": "space-grotesk-latin-700-normal.woff2",
    "m5": "jetbrains-mono-latin-500-normal.woff2",
    "m7": "jetbrains-mono-latin-700-normal.woff2",
}
FAMILY = {"d": "RKDisplay", "m": "RKMono"}
FALLBACK = {"d": "'Space Grotesk',ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif",
            "m": "'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"}


class Metrics:
    def __init__(self, path: Path):
        tt = TTFont(path)
        self.cmap = tt.getBestCmap()
        self.hmtx = tt["hmtx"]
        self.upm = tt["head"].unitsPerEm

    def width(self, s: str, size: float, ls: float = 0.0) -> float:
        total = 0
        for ch in s:
            gid = self.cmap.get(ord(ch))
            if gid is None:
                raise ValueError(f"glyph {ch!r} (U+{ord(ch):04X}) missing from font")
            total += self.hmtx[gid][0]
        return total / self.upm * size + ls * size * len(s)


METRICS = {k: Metrics(VENDOR / "fonts" / f) for k, f in FONT_FILES.items()}


def measure(cls: str, s: str, size: float, ls: float = 0.0) -> float:
    return METRICS[cls].width(s, size, ls)


def wrap(s: str, cls: str, size: float, maxw: float) -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if measure(cls, trial, size) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def font_face(cls: str, chars: set[str]) -> str:
    tt = TTFont(VENDOR / "fonts" / FONT_FILES[cls])
    opts = ftsubset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "calt"]
    opts.name_IDs = ["*"]          # keep copyright + license strings in the font
    opts.name_languages = ["*"]
    opts.notdef_outline = True
    sub = ftsubset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars | {" "})))
    sub.subset(tt)
    buf = io.BytesIO()
    tt.flavor = "woff2"
    tt.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode()
    fam, weight = FAMILY[cls[0]], int(cls[1]) * 100
    return (f"@font-face{{font-family:'{fam}';font-weight:{weight};font-style:normal;"
            f"font-display:block;src:url(data:font/woff2;base64,{b64}) format('woff2')}}")


# ----------------------------------------------------------------- images ---
def png_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def resized(img: Image.Image, width: int) -> Image.Image:
    """Resize without changing the image's own alpha (premultiplied resample)."""
    h = round(img.height * width / img.width)
    if img.mode == "RGBA":
        return img.convert("RGBa").resize((width, h), Image.LANCZOS).convert("RGBA")
    return img.resize((width, h), Image.LANCZOS)


ID_PNG = Image.open(ROOT / "id.png").convert("RGBA")              # true alpha, kept as-is
POINT_PNG = Image.open(ROOT / "right_pointing.png").convert("RGB")  # no alpha channel in source
LI_PNG = Image.open(VENDOR / "brand" / "LI-In-Bug.png").convert("RGBA")

# ------------------------------------------------------------------ icons ---
ICON_META = json.loads((VENDOR / "icons" / "meta.json").read_text(encoding="utf8"))


def si_path(slug: str) -> str:
    svg = (VENDOR / "icons" / f"{slug}.svg").read_text(encoding="utf8")
    return re.search(r'<path d="([^"]+)"', svg).group(1)


STACK = [
    # label, Simple Icons title (None = generic glyph), slug
    ("Python", "Python", "python"), ("C++", "C++", "cplusplus"),
    ("TensorFlow", "TensorFlow", "tensorflow"), ("PyTorch", "PyTorch", "pytorch"),
    ("Keras", "Keras", "keras"), ("OpenCV", "OpenCV", "opencv"),
    ("Scikit-learn", "scikit-learn", "scikitlearn"), ("NumPy", "NumPy", "numpy"),
    ("Pandas", "pandas", "pandas"), ("FastAPI", "FastAPI", "fastapi"),
    ("Node.js", "Node.js", "nodedotjs"), ("Express.js", "Express", "express"),
    ("React", "React", "react"), ("REST APIs", None, None),
    ("MongoDB", "MongoDB", "mongodb"), ("MySQL", "MySQL", "mysql"),
    ("PostgreSQL", "PostgreSQL", "postgresql"), ("Docker", "Docker", "docker"),
    ("Git", "Git", "git"),
]
STACK_BY_LABEL = {s[0]: s for s in STACK}


def luminance(hexc: str) -> float:
    r, g, b = (int(hexc.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


CHIP_DARK = "#121a2e"


def brand(label: str) -> tuple[str, str, str]:
    """(icon path or '', brand hex, chip background with the better contrast)."""
    _, title, slug = STACK_BY_LABEL[label]
    if title is None:
        return "", BLUE, INK
    hexc = "#" + ICON_META[title]["hex"]
    bg = INK if contrast(hexc, INK) >= contrast(hexc, CHIP_DARK) else CHIP_DARK
    return si_path(slug), hexc, bg


# Simple line glyphs drawn for this profile (24-unit grid, stroked).
GLYPH = {
    "pin": '<path d="M12 21.5s-7-6.3-7-11.8a7 7 0 0 1 14 0c0 5.5-7 11.8-7 11.8z"/><circle cx="12" cy="9.6" r="2.6"/>',
    "flask": '<path d="M9 3h6M10 3v6.2L4.6 18.6A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.4-2.4L14 9.2V3M7.3 15h9.4"/>',
    "building": '<path d="M4 21V6.5L12 3l8 3.5V21M2.5 21h19M9 9.5h.01M15 9.5h.01M9 13.5h.01M15 13.5h.01M10 21v-4h4v4"/>',
    "briefcase": '<rect x="3" y="7" width="18" height="13" rx="2.5"/><path d="M9 7V5.2A1.7 1.7 0 0 1 10.7 3.5h2.6A1.7 1.7 0 0 1 15 5.2V7M3 12.5h18"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.6 2.8 3.9 5.8 3.9 9s-1.3 6.2-3.9 9c-2.6-2.8-3.9-5.8-3.9-9S9.4 5.8 12 3z"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "chev": '<path d="M9 5l7 7-7 7"/>',
    "down": '<path d="M12 4v15M6 13l6 6 6-6"/>',
    "braces": '<path d="M8.5 4C6.6 4 6 5 6 6.6v2.3c0 1.3-.7 2.1-2 2.1v2c1.3 0 2 .8 2 2.1v2.3C6 19 6.6 20 8.5 20M15.5 4c1.9 0 2.5 1 2.5 2.6v2.3c0 1.3.7 2.1 2 2.1v2c-1.3 0-2 .8-2 2.1v2.3c0 1.6-.6 2.6-2.5 2.6"/>',
}


def glyph(name: str, x: float, y: float, size: float, color: str, sw: float = 1.8) -> str:
    s = size / 24
    return (f'<g transform="translate({x:g} {y:g}) scale({s:.4f})" fill="none" stroke="{color}" '
            f'stroke-width="{sw / s:.2f}" stroke-linecap="round" stroke-linejoin="round">{GLYPH[name]}</g>')


def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------- document ---
BASE_CSS = """
.d5{font-family:'RKDisplay',%(d)s;font-weight:500}
.d7{font-family:'RKDisplay',%(d)s;font-weight:700}
.m5{font-family:'RKMono',%(m)s;font-weight:500}
.m7{font-family:'RKMono',%(m)s;font-weight:700}
text{font-kerning:normal}
.still{display:none}
.fu{animation:fu .9s cubic-bezier(.2,.75,.2,1) both}
.fi{animation:fi .9s ease-out both}
@keyframes fu{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
@keyframes fi{from{opacity:0}to{opacity:1}}
@media (prefers-reduced-motion:reduce){
  *{animation:none!important}
  .motion{display:none}
  .still{display:inline}
  .typed{clip-path:none}
  .caret{display:none}
}
""" % FALLBACK


class Doc:
    def __init__(self, prefix: str, w: int, h: int, title: str, desc: str):
        self.p, self.W, self.H, self.title, self.desc = prefix, w, h, title, desc
        self.used: dict[str, set[str]] = {k: set() for k in FONT_FILES}
        self.defs: list[str] = []
        self.body: list[str] = []
        self.css: list[str] = []
        self.texts: list[tuple[str, float]] = []

    def i(self, name: str) -> str:
        return f"{self.p}-{name}"

    def u(self, name: str) -> str:
        return f"url(#{self.p}-{name})"

    def text(self, x, y, s, cls="d5", size=16.0, fill=INK, anchor="start", ls=0.0,
             attrs="", maxw=None, extra_cls="") -> str:
        w = measure(cls, s, size, ls)
        if maxw is not None and w > maxw + 0.5:
            raise ValueError(f"[{self.p}] text too wide ({w:.0f} > {maxw:.0f}px): {s!r}")
        self.used[cls].update(s)
        self.texts.append((s, size))
        extra = ""
        if anchor != "start":
            extra += f' text-anchor="{anchor}"'
        if ls:
            extra += f' letter-spacing="{fmt(ls * size)}"'
        if attrs:
            extra += " " + attrs
        klass = f"{cls} {extra_cls}".strip()
        return (f'<text class="{klass}" x="{fmt(x)}" y="{fmt(y)}" font-size="{fmt(size)}" '
                f'fill="{fill}"{extra}>{escape(s)}</text>')

    # standard backdrop: navy card, glows, dot texture, gradient hairline
    def frame_defs(self):
        p, W, H = self.p, self.W, self.H
        self.defs.append(f"""
<clipPath id="{p}-clip"><rect width="{W}" height="{H}" rx="28"/></clipPath>
<pattern id="{p}-dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="11" cy="11" r="1.1" fill="{INK}" fill-opacity=".07"/></pattern>
<radialGradient id="{p}-glowb" gradientUnits="userSpaceOnUse" cx="{W * .12:g}" cy="0" r="{max(W, H) * .62:g}"><stop offset="0" stop-color="{BLUE}" stop-opacity=".26"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></radialGradient>
<radialGradient id="{p}-glowr" gradientUnits="userSpaceOnUse" cx="{W * .94:g}" cy="{H:g}" r="{max(W, H) * .5:g}"><stop offset="0" stop-color="{CRIMSON}" stop-opacity=".17"/><stop offset="1" stop-color="{CRIMSON}" stop-opacity="0"/></radialGradient>
<linearGradient id="{p}-hair" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE}"/><stop offset=".45" stop-color="{INK}" stop-opacity=".16"/><stop offset=".6" stop-color="{INK}" stop-opacity=".16"/><stop offset="1" stop-color="{CRIMSON}"/></linearGradient>
<linearGradient id="{p}-hair2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE}" stop-opacity=".75"/><stop offset=".5" stop-color="{INK}" stop-opacity=".1"/><stop offset="1" stop-color="{CRIMSON}" stop-opacity=".6"/></linearGradient>
<linearGradient id="{p}-panel" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#121b33" stop-opacity=".92"/><stop offset="1" stop-color="#0b1122" stop-opacity=".92"/></linearGradient>
""")

    def panel(self, x, y, w, h, r=20, attrs="") -> str:
        return (f'<rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" rx="{r}" '
                f'fill="{self.u("panel")}" stroke="{self.u("hair2")}" stroke-width="1.2" {attrs}/>')

    def eyebrow(self, x, y, num, label) -> str:
        return (self.text(x, y, num, "m7", 13.5, CRIMSON, ls=.14)
                + f'<rect x="{fmt(x + measure("m7", num, 13.5, .14) + 6)}" y="{fmt(y - 5.5)}" width="22" height="1.6" fill="{CRIMSON}"/>'
                + self.text(x + measure("m7", num, 13.5, .14) + 36, y, label, "m7", 13.5, MUTED, ls=.2))

    def render(self) -> str:
        p, W, H = self.p, self.W, self.H
        faces = "\n".join(font_face(k, v) for k, v in self.used.items() if v)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
            f'aria-labelledby="{p}-title {p}-desc">\n'
            f'<title id="{p}-title">{escape(self.title)}</title>\n'
            f'<desc id="{p}-desc">{escape(self.desc)}</desc>\n'
            f'<style>\n{faces}\n{BASE_CSS}\n{"".join(self.css)}\n</style>\n'
            f'<defs>{"".join(self.defs)}</defs>\n'
            f'<g clip-path="url(#{p}-clip)">\n'
            f'<rect width="{W}" height="{H}" fill="{NAVY}"/>'
            f'<rect width="{W}" height="{H}" fill="url(#{p}-glowb)"/>'
            f'<rect width="{W}" height="{H}" fill="url(#{p}-glowr)"/>'
            f'<rect width="{W}" height="{H}" fill="url(#{p}-dots)"/>\n'
            + "\n".join(self.body) +
            f'\n</g>\n<rect x=".75" y=".75" width="{W - 1.5}" height="{H - 1.5}" rx="27.25" fill="none" '
            f'stroke="url(#{p}-hair)" stroke-width="1.5"/>\n</svg>\n')


def delay(s: float) -> str:
    return f'style="animation-delay:{s:g}s"'


# ================================================================== HERO ===
def build_hero() -> Doc:
    W, H = 1000, 668
    d = Doc("hr", W, H, "Ritesh Kumar — ML Engineer",
            f"Hi, I'm Ritesh Kumar. {' / '.join(PERSON['roles'])}. {PERSON['pitch']} "
            f"{PERSON['role']}, {PERSON['lab']}, {PERSON['org']}. {PERSON['location']}.")
    d.frame_defs()
    p = d.p
    X = 64
    COL = 500  # left column width

    # --- portrait (id.png, alpha preserved) -------------------------------
    ph = 580
    pw = round(ph * ID_PNG.width / ID_PNG.height)
    px, py = W - pw - 8, H - ph
    portrait = png_uri(resized(ID_PNG, 560))
    cx, cy = px + pw / 2, py + 210
    d.defs.append(f"""
<radialGradient id="{p}-halo" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="{BLUE}" stop-opacity=".55"/><stop offset=".55" stop-color="{BLUE}" stop-opacity=".16"/><stop offset="1" stop-color="{BLUE}" stop-opacity="0"/></radialGradient>
<linearGradient id="{p}-fade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{NAVY}" stop-opacity="0"/><stop offset="1" stop-color="{NAVY}" stop-opacity=".92"/></linearGradient>
<linearGradient id="{p}-ring" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{CRIMSON}"/></linearGradient>""")
    d.css.append(f"""
.{p}-spin{{transform-box:fill-box;transform-origin:center;animation:{p}-spin 40s linear infinite both}}
@keyframes {p}-spin{{to{{transform:rotate(360deg)}}}}
.{p}-pt{{animation:{p}-pt 1.3s .25s cubic-bezier(.2,.75,.2,1) both}}
@keyframes {p}-pt{{from{{opacity:0;transform:translateY(40px)}}to{{opacity:1;transform:none}}}}
.{p}-rise{{animation:{p}-rise 1.15s cubic-bezier(.16,1,.3,1) both}}
@keyframes {p}-rise{{from{{transform:translateY(150px)}}to{{transform:none}}}}
.{p}-bar{{transform-box:fill-box;transform-origin:left center;animation:{p}-bar .9s 1.45s cubic-bezier(.2,.75,.2,1) both}}
@keyframes {p}-bar{{from{{transform:scaleX(0)}}to{{transform:none}}}}
.caret{{animation:{p}-blink 1.05s steps(1,end) infinite both}}
@keyframes {p}-blink{{0%{{opacity:1}}50%{{opacity:0}}}}
.{p}-role{{animation:{p}-role 10s 1.6s cubic-bezier(.2,.75,.2,1) infinite both}}
@keyframes {p}-role{{0%{{opacity:0;transform:translateY(46px)}}4%,25%{{opacity:1;transform:none}}29%,100%{{opacity:0;transform:translateY(-46px)}}}}
""")
    d.body.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="270" fill="url(#{p}-halo)"/>')
    d.body.append(f'<g class="{p}-spin"><circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="214" fill="none" '
                  f'stroke="url(#{p}-ring)" stroke-width="1.4" stroke-dasharray="2 9" stroke-opacity=".8"/></g>')
    d.body.append(f'<circle cx="{fmt(cx)}" cy="{fmt(cy)}" r="176" fill="none" stroke="{INK}" stroke-opacity=".1"/>')
    d.body.append(f'<g class="{p}-pt"><image x="{px}" y="{py}" width="{pw}" height="{ph}" '
                  f'preserveAspectRatio="xMidYMax meet" xlink:href="{portrait}"/></g>')
    d.body.append(f'<rect x="{px - 40}" y="{H - 90}" width="{pw + 60}" height="90" fill="url(#{p}-fade)"/>')

    # GitHub handle chip, top right
    hp, hx, hc = si_path("github"), 0, f"@{PERSON['github']}"
    cw = measure("m7", hc, 14) + 54
    hx = W - 32 - cw
    d.body.append(f'<g class="fi" {delay(1.2)}><rect x="{fmt(hx)}" y="30" width="{fmt(cw)}" height="36" rx="18" '
                  f'fill="{NAVY}" fill-opacity=".72" stroke="url(#{p}-hair2)"/>'
                  f'<path transform="translate({fmt(hx + 14)} 39) scale(.75)" d="{hp}" fill="{INK}"/>'
                  + d.text(hx + 42, 53, hc, "m7", 14, INK) + "</g>")

    # --- typed greeting (SMIL, discrete keyTimes from 0s) ----------------
    gy, gs = 100, 24
    prompt = ">"
    typed = "hi there, I'm"
    tx = X + measure("m7", prompt, gs) + 14
    d.body.append(d.text(X, gy, prompt, "m7", gs, BLUE))
    full = measure("m5", typed, gs)
    n = len(typed)
    start, step = 0.35, 0.075
    dur = start + n * step + 0.05
    widths = [0.0] + [measure("m5", typed[:k], gs) + 1 for k in range(1, n + 1)]
    times = [0.0] + [(start + k * step) / dur for k in range(1, n + 1)]
    vals = ";".join(fmt(w) for w in widths)
    kts = ";".join(f"{t:.4f}" for t in times)
    xvals = ";".join(fmt(tx + w + 3) for w in widths)
    d.defs.append(f'<clipPath id="{p}-type"><rect x="{fmt(tx - 2)}" y="{gy - 30}" width="{fmt(full + 3)}" height="40">'
                  f'<animate attributeName="width" begin="0s" dur="{dur:.3f}s" calcMode="discrete" '
                  f'values="{vals}" keyTimes="{kts}" fill="freeze"/></rect></clipPath>')
    d.body.append(f'<g class="typed" clip-path="url(#{p}-type)">' + d.text(tx, gy, typed, "m5", gs, INK) + "</g>")
    d.body.append(f'<rect class="caret" x="{fmt(tx + full + 3)}" y="{gy - 21}" width="12" height="25" fill="{CRIMSON}">'
                  f'<animate attributeName="x" begin="0s" dur="{dur:.3f}s" calcMode="discrete" values="{xvals}" '
                  f'keyTimes="{kts}" fill="freeze"/></rect>')

    # --- name with rising mask -------------------------------------------
    ns = 126
    l1, l2 = "Ritesh", "Kumar"
    b1, b2 = 228, 346
    for i, (line, base) in enumerate(((l1, b1), (l2, b2))):
        d.defs.append(f'<clipPath id="{p}-n{i}"><rect x="{X - 10}" y="{base - ns}" width="{COL + 20}" '
                      f'height="{ns * 1.12:g}"/></clipPath>')
    d.body.append(f'<g clip-path="url(#{p}-n0)">'
                  + d.text(X - 4, b1, l1, "d7", ns, INK, ls=-.035, maxw=COL, extra_cls=f"{p}-rise", attrs=delay(.5))
                  + "</g>")
    kumar = d.text(X - 4, b2, l2, "d7", ns, BLUE, ls=-.035, maxw=COL - 40,
                   extra_cls=f"{p}-rise", attrs=delay(.68))
    dot_x = X - 4 + measure("d7", l2, ns, -.035) + 4
    dot = f'<rect class="{p}-rise" {delay(.8)} x="{fmt(dot_x)}" y="{b2 - 22}" width="22" height="22" rx="3" fill="{CRIMSON}"/>'
    d.body.append(f'<g clip-path="url(#{p}-n1)">{kumar}{dot}</g>')
    d.body.append(f'<rect class="{p}-bar" x="{X}" y="{b2 + 30}" width="96" height="5" rx="2.5" fill="{CRIMSON}"/>'
                  f'<rect class="{p}-bar" style="animation-delay:1.6s" x="{X + 104}" y="{b2 + 30}" width="30" height="5" rx="2.5" fill="{BLUE}"/>')

    # --- cycling roles -----------------------------------------------------
    ry, rs = 432, 36
    d.defs.append(f'<clipPath id="{p}-roles"><rect x="{X}" y="{ry - rs - 6}" width="{COL + 20}" height="{rs + 20}"/></clipPath>')
    d.body.append(f'<g class="fi" {delay(1.4)}>' + d.text(X, ry - 2, "//", "m7", 22, CRIMSON) + "</g>")
    roles = []
    for k, role in enumerate(PERSON["roles"]):
        base = "" if k == 0 else ' opacity="0"'
        roles.append(f'<g class="{p}-role" style="animation-delay:{1.6 + k * 2.5:g}s"{base}>'
                     + d.text(X + 40, ry, role, "d5", rs, INK, ls=-.01, maxw=COL - 40) + "</g>")
    d.body.append(f'<g clip-path="url(#{p}-roles)">' + "".join(roles) + "</g>")

    # --- pitch -------------------------------------------------------------
    py0 = 482
    for j, line in enumerate(wrap(PERSON["pitch"], "d5", 20, COL)):
        d.body.append(f'<g class="fu" {delay(1.75 + j * .08)}>' + d.text(X, py0 + j * 29, line, "d5", 20, MUTED, maxw=COL) + "</g>")

    # --- company / location pills -------------------------------------------
    def pill(x, y, icon, label, color=INK, dl=0.0):
        w = measure("d5", label, 15.5) + 52
        g = (f'<g class="fu" {delay(dl)}><rect x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="36" rx="18" '
             f'fill="{INK}" fill-opacity=".045" stroke="{INK}" stroke-opacity=".14"/>'
             + glyph(icon, x + 13, y + 8, 20, color) + d.text(x + 40, y + 23.5, label, "d5", 15.5, INK) + "</g>")
        return g, w
    rows = [[("flask", f"{PERSON['role']} — {PERSON['lab']}", BLUE)],
            [("building", PERSON["org"], BLUE), ("pin", PERSON["location"], CRIMSON)]]
    y = 570
    for r, row in enumerate(rows):
        x = X
        for icon, label, color in row:
            g, w = pill(x, y, icon, label, color, 2.0 + r * .1 + (x - X) / 2000)
            d.body.append(g)
            x += w + 10
        if x - 10 > X + COL + 20:
            raise ValueError(f"hero pill row {r} overflows: {x}")
        y += 44
    return d


# ============================================================ ABOUT/LIFE ===
CAPS = [
    ("Computer vision", "Defect detection & classification with CNNs"),
    ("Intelligent automation", "Model output turned into step-by-step fixes"),
    ("AI-powered applications", "End-to-end products: FastAPI, Node.js, React"),
    ("Applied ML research", f"{PERSON['role']}, {PERSON['lab']}"),
]


def build_about() -> Doc:
    W, H = 1000, 520
    d = Doc("ab", W, H, "About Ritesh Kumar",
            "What I build: " + "; ".join(f"{a} — {b}" for a, b in CAPS)
            + ". Interests: AI/ML research, hackathons, open source.")
    d.frame_defs()
    p = d.p
    X = 64
    d.body.append(f'<g class="fi">{d.eyebrow(X, 78, "01", "ABOUT")}</g>')
    d.body.append(f'<g class="fu" {delay(.1)}>' + d.text(X - 2, 140, "What I build.", "d7", 56, INK, ls=-.03) + "</g>")

    y0, step = 184, 76
    for k, (title, line) in enumerate(CAPS):
        y = y0 + k * step
        c = BLUE if k % 2 == 0 else CRIMSON
        d.body.append(
            f'<g class="fu" {delay(.25 + k * .12)}>'
            f'<rect x="{X}" y="{y}" width="50" height="50" rx="14" fill="{c}" fill-opacity=".14" stroke="{c}" stroke-opacity=".55"/>'
            + d.text(X + 25, y + 31, f"0{k + 1}", "m7", 16, INK, anchor="middle")
            + d.text(X + 70, y + 21, title, "d7", 21, INK, maxw=440)
            + d.text(X + 70, y + 45, line, "d5", 16.5, MUTED, maxw=450)
            + "</g>")

    # --- interests carousel -------------------------------------------------
    cx0, cy0, cw, ch = 590, 52, 346, 418
    ix = cx0 + 28
    iw = cw - 56
    d.body.append(f'<g class="fi" {delay(.3)}>' + d.panel(cx0, cy0, cw, ch, 24) + "</g>")
    d.css.append(f"""
.{p}-s0{{animation:{p}-s0 12s linear infinite both}}
.{p}-s1{{animation:{p}-s1 12s linear infinite both}}
.{p}-s2{{animation:{p}-s2 12s linear infinite both}}
@keyframes {p}-s0{{0%{{opacity:0;transform:translateX(22px)}}3%,30%{{opacity:1;transform:none}}33.33%,100%{{opacity:0;transform:translateX(-22px)}}}}
@keyframes {p}-s1{{0%,33.33%{{opacity:0;transform:translateX(22px)}}36.33%,63.33%{{opacity:1;transform:none}}66.67%,100%{{opacity:0;transform:translateX(-22px)}}}}
@keyframes {p}-s2{{0%,66.67%{{opacity:0;transform:translateX(22px)}}69.67%,96.67%{{opacity:1;transform:none}}100%{{opacity:0;transform:translateX(-22px)}}}}
.{p}-g0,.{p}-g1,.{p}-g2{{transform-box:fill-box;transform-origin:left center}}
.{p}-g0{{animation:{p}-g0 12s linear infinite both}}
.{p}-g1{{animation:{p}-g1 12s linear infinite both}}
.{p}-g2{{animation:{p}-g2 12s linear infinite both}}
@keyframes {p}-g0{{0%{{transform:scaleX(0)}}33.33%,100%{{transform:scaleX(1)}}}}
@keyframes {p}-g1{{0%,33.33%{{transform:scaleX(0)}}66.67%,100%{{transform:scaleX(1)}}}}
@keyframes {p}-g2{{0%,66.67%{{transform:scaleX(0)}}100%{{transform:scaleX(1)}}}}
.{p}-scan{{animation:{p}-scan 2.6s ease-in-out infinite alternate both}}
@keyframes {p}-scan{{from{{transform:translateY(-100px)}}to{{transform:none}}}}
.caret2{{animation:{p}-blink 1s steps(1,end) infinite both}}
@keyframes {p}-blink{{0%{{opacity:1}}50%{{opacity:0}}}}
""")
    # segment progress bars
    gap = 8
    sw = (iw - 2 * gap) / 3
    for k in range(3):
        sx = ix + k * (sw + gap)
        base = "" if k == 0 else ' transform="scale(0 1)"'
        d.body.append(f'<rect class="fi" {delay(.3)} x="{fmt(sx)}" y="{cy0 + 26}" width="{fmt(sw)}" height="4" rx="2" fill="{INK}" fill-opacity=".14"/>'
                      f'<rect class="{p}-g{k}" x="{fmt(sx)}" y="{cy0 + 26}" width="{fmt(sw)}" height="4" rx="2" fill="{BLUE}"{base}/>')

    art_y = cy0 + 92
    slides = [
        ("AI/ML Research",
         f"{PERSON['role']} at the {PERSON['lab']}, {PERSON['org']}.",
         "Computer vision"),
        ("Hackathons",
         "Hack Horizon 2.0 brought together 170+ teams and 750+ participants.",
         "2026"),
        ("Open Source",
         f"{GH_API['public_repos']} public repositories on GitHub, built in the open.",
         f"As of {AS_OF}"),
    ]

    def art(k: int) -> str:
        x, y, w, h = ix, art_y, iw, 132
        if k == 0:  # vision: image tile with detection boxes + scan line (NEU-DET class names)
            d.defs.append(f'<clipPath id="{p}-art0"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14"/></clipPath>'
                          f'<linearGradient id="{p}-steel" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#26324f"/><stop offset="1" stop-color="#151d33"/></linearGradient>'
                          f'<pattern id="{p}-grain" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M0 8L8 0" stroke="{INK}" stroke-opacity=".06"/></pattern>')
            return (f'<g clip-path="url(#{p}-art0)"><rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#{p}-steel)"/>'
                    f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#{p}-grain)"/>'
                    f'<path d="M{x + 40} {y + 40}l38 22M{x + 52} {y + 36}l30 18" stroke="{INK}" stroke-opacity=".35" stroke-width="2" stroke-linecap="round"/>'
                    f'<circle cx="{x + 196}" cy="{y + 86}" r="7" fill="{INK}" fill-opacity=".28"/><circle cx="{x + 214}" cy="{y + 94}" r="4" fill="{INK}" fill-opacity=".22"/>'
                    f'<rect x="{x + 26}" y="{y + 24}" width="72" height="50" rx="4" fill="none" stroke="{CRIMSON}" stroke-width="2"/>'
                    f'<rect x="{x + 26}" y="{y + 10}" width="{fmt(measure("m7", "scratches", 11) + 12)}" height="16" rx="3" fill="{CRIMSON}"/>'
                    + d.text(x + 32, y + 22, "scratches", "m7", 11, INK)
                    + f'<rect x="{x + 178}" y="{y + 70}" width="54" height="40" rx="4" fill="none" stroke="{BLUE}" stroke-width="2"/>'
                    f'<rect x="{x + 178}" y="{y + 56}" width="{fmt(measure("m7", "inclusion", 11) + 12)}" height="16" rx="3" fill="{BLUE}"/>'
                    + d.text(x + 184, y + 68, "inclusion", "m7", 11, INK)
                    + f'<g class="{p}-scan"><rect x="{x}" y="{y + 118}" width="{w}" height="2" fill="{BLUE}" fill-opacity=".9"/>'
                    f'<rect x="{x}" y="{y + 120}" width="{w}" height="12" fill="{BLUE}" fill-opacity=".12"/></g></g>')
        if k == 1:  # hackathon: terminal window
            bars = [(0, 120, BLUE), (18, 168, INK), (18, 92, CRIMSON), (36, 140, INK), (0, 70, BLUE)]
            out = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="#0b1224" stroke="{INK}" stroke-opacity=".14"/>'
                   f'<path d="M{x} {y + 30}h{w}" stroke="{INK}" stroke-opacity=".1"/>'
                   f'<circle cx="{x + 18}" cy="{y + 15}" r="4.5" fill="{CRIMSON}"/><circle cx="{x + 34}" cy="{y + 15}" r="4.5" fill="#ffb547"/><circle cx="{x + 50}" cy="{y + 15}" r="4.5" fill="#3ddc97"/>')
            for j, (ind, bw, c) in enumerate(bars):
                out += f'<rect x="{x + 18 + ind}" y="{y + 44 + j * 16}" width="{bw}" height="7" rx="3.5" fill="{c}" fill-opacity="{.85 if c != INK else .3}"/>'
            out += f'<rect class="caret2" x="{x + 18 + 70 + 8}" y="{y + 44 + 4 * 16 - 2}" width="9" height="11" fill="{INK}"/>'
            return out
        # open source: branch graph
        my = y + 84
        nodes = [x + 20, x + 70, x + 120, x + 170, x + 220, x + 270]
        out = (f'<path d="M{x + 8} {my}H{x + w - 8}" stroke="{BLUE}" stroke-width="3" stroke-linecap="round"/>'
               f'<path d="M{x + 70} {my}C{x + 95} {my} {x + 95} {my - 48} {x + 120} {my - 48}H{x + 170}'
               f'C{x + 195} {my - 48} {x + 195} {my} {x + 220} {my}" fill="none" stroke="{CRIMSON}" stroke-width="3"/>'
               f'<path d="M{x + 120} {my}C{x + 140} {my} {x + 140} {my + 34} {x + 160} {my + 34}H{x + 190}" fill="none" stroke="{INK}" stroke-opacity=".45" stroke-width="2.5" stroke-dasharray="1 6" stroke-linecap="round"/>')
        for nx in nodes:
            out += f'<circle cx="{nx}" cy="{my}" r="7" fill="{NAVY}" stroke="{BLUE}" stroke-width="3"/>'
        for nx in (x + 120, x + 170):
            out += f'<circle cx="{nx}" cy="{my - 48}" r="7" fill="{NAVY}" stroke="{CRIMSON}" stroke-width="3"/>'
        out += f'<circle cx="{x + 270}" cy="{my}" r="11" fill="none" stroke="{BLUE}" stroke-opacity=".4" stroke-width="2"/>'
        return out

    for k, (title, body, meta) in enumerate(slides):
        base = "" if k == 0 else ' opacity="0"'
        g = f'<g class="{p}-s{k}"{base}>'
        g += d.text(ix, cy0 + 64, "INTERESTS", "m7", 12.5, MUTED, ls=.18)
        g += d.text(ix + iw, cy0 + 64, f"0{k + 1} / 03", "m7", 12.5, INK, anchor="end", ls=.08)
        g += art(k)
        g += d.text(ix, art_y + 182, title, "d7", 32, INK, ls=-.02, maxw=iw)
        for j, line in enumerate(wrap(body, "d5", 16.5, iw)):
            g += d.text(ix, art_y + 212 + j * 23, line, "d5", 16.5, MUTED, maxw=iw)
        mw = measure("m7", meta.upper(), 12, .1) + 26
        g += (f'<rect x="{ix}" y="{cy0 + ch - 54}" width="{fmt(mw)}" height="28" rx="14" fill="{CRIMSON}" fill-opacity=".13" stroke="{CRIMSON}" stroke-opacity=".6"/>'
              + d.text(ix + 13, cy0 + ch - 35.5, meta.upper(), "m7", 12, INK, ls=.1))
        g += "</g>"
        if len(wrap(body, "d5", 16.5, iw)) > 3:
            raise ValueError(f"slide {k} body too long")
        d.body.append(g)
    return d


# ================================================================= STACK ===
GROUPS = [
    ("Languages", ["Python", "C++"]),
    ("ML & Vision", ["TensorFlow", "PyTorch", "Keras", "Scikit-learn", "OpenCV"]),
    ("Data", ["NumPy", "Pandas"]),
    ("Backend & Web", ["FastAPI", "Node.js", "Express.js", "React", "REST APIs"]),
    ("Databases", ["MongoDB", "MySQL", "PostgreSQL"]),
    ("DevOps & Tools", ["Docker", "Git"]),
]
ORBITS = [
    # rx, ry, tilt (deg), period (s), labels
    (196, 88, -9, 36, ["Python", "PyTorch", "TensorFlow", "OpenCV", "C++"]),
    (322, 156, -5, 52, ["Keras", "Scikit-learn", "NumPy", "Pandas", "FastAPI", "React"]),
    (450, 224, -2, 68, ["Node.js", "Express.js", "REST APIs", "MongoDB", "MySQL", "PostgreSQL", "Docker", "Git"]),
]


def orbit_gap() -> float:
    """Smallest distance between neighbouring orbits (they must never cross)."""
    def pts(rx, ry, tilt):
        t = math.radians(tilt)
        return [(rx * math.cos(a) * math.cos(t) - ry * math.sin(a) * math.sin(t),
                 rx * math.cos(a) * math.sin(t) + ry * math.sin(a) * math.cos(t))
                for a in (2 * math.pi * i / 720 for i in range(720))]
    return min(min(math.dist(u, v) for u in pts(*a[:3]) for v in pts(*b[:3]))
               for a, b in zip(ORBITS, ORBITS[1:]))


def build_stack() -> Doc:
    W = 1000
    gap = orbit_gap()
    if gap < 62:  # icon (42px) + label (~18px) must clear the next orbit
        raise ValueError(f"orbits too close: {gap:.0f}px")
    # chips layout first (to know height)
    colw = 418
    cols_x = (64, 64 + colw + 36)
    chip_h, chip_gap, row_gap = 36, 10, 10

    def chip_w(label):
        return measure("d5", label, 15.5) + 54

    def layout(groups):
        y, out = 0, []
        for gname, items in groups:
            out.append(("label", gname, 0, y))
            y += 22
            x = 0
            for it in items:
                w = chip_w(it)
                if x + w > colw:
                    x, y = 0, y + chip_h + row_gap
                out.append(("chip", it, x, y))
                x += w + chip_gap
            y += chip_h + 34
        return out, y - 34

    left, lh = layout(GROUPS[:3])
    right, rh = layout(GROUPS[3:])
    chips_top = 760
    H = int(chips_top + max(lh, rh) + 52)
    d = Doc("st", W, H, "Tech stack",
            "Tech stack. " + "; ".join(f"{g}: {', '.join(i)}" for g, i in GROUPS) + ".")
    d.frame_defs()
    p = d.p
    d.body.append(f'<g class="fi">{d.eyebrow(64, 78, "02", "STACK")}</g>')
    d.body.append(f'<g class="fu" {delay(.1)}>' + d.text(62, 138, "Tools I build with.", "d7", 52, INK, ls=-.03) + "</g>")
    d.body.append(f'<g class="fu" {delay(.2)}>' + d.text(W - 64, 136, f"{len(STACK)} tools · 3 orbits", "m5", 14, MUTED, anchor="end", ls=.04) + "</g>")

    # icon symbols
    R = 21
    for label, *_ in STACK:
        path, hexc, bg = brand(label)
        sid = d.i("ic-" + re.sub(r"[^a-z0-9]", "", label.lower()))
        if path:
            icon = f'<path transform="translate(-12 -12)" d="{path}" fill="{hexc}"/>'
        else:
            icon = glyph("braces", -12, -12, 24, BLUE, 2.2)
        stroke = f' stroke="{INK}" stroke-opacity=".25"' if bg == CHIP_DARK else ""
        d.defs.append(f'<g id="{sid}"><circle r="{R}" fill="{bg}"{stroke}/>{icon}'
                      + d.text(0, R + 17, label, "d7", 13.5, INK, anchor="middle",
                               attrs=f'stroke="{NAVY}" stroke-width="5" stroke-linejoin="round" paint-order="stroke"')
                      + "</g>")

    cx, cy = W / 2, 420
    d.defs.append(f"""
<radialGradient id="{p}-core" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#3d8bff"/><stop offset=".6" stop-color="{BLUE}"/><stop offset="1" stop-color="#173a8a"/></radialGradient>
<linearGradient id="{p}-orb" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{BLUE}" stop-opacity=".9"/><stop offset=".5" stop-color="{INK}" stop-opacity=".12"/><stop offset="1" stop-color="{CRIMSON}" stop-opacity=".85"/></linearGradient>""")
    d.css.append(f"""
.{p}-pulse{{transform-box:fill-box;transform-origin:center;animation:{p}-pulse 3.2s ease-in-out infinite both}}
@keyframes {p}-pulse{{0%,100%{{transform:scale(1);opacity:.5}}50%{{transform:scale(1.18);opacity:0}}}}
""")
    orbit_svg, motion, still = [], [], []
    for oi, (rx, ry, tilt, period, labels) in enumerate(ORBITS):
        orbit_svg.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" transform="rotate({tilt} {cx} {cy})" '
                         f'fill="none" stroke="url(#{p}-orb)" stroke-width="1.3" stroke-opacity=".75"/>')
        orbit_svg.append(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" transform="rotate({tilt} {cx} {cy})" '
                         f'fill="none" stroke="{INK}" stroke-opacity=".12" stroke-dasharray="2 7"/>')
        t = math.radians(tilt)
        n = len(labels)

        def pt(a, rx=rx, ry=ry, t=t):
            ex, ey = rx * math.cos(a), ry * math.sin(a)
            return cx + ex * math.cos(t) - ey * math.sin(t), cy + ex * math.sin(t) + ey * math.cos(t)
        # equal arc-length spacing; paced animateMotion keeps that spacing forever
        samples = [2 * math.pi * i / 3600 for i in range(3601)]
        arc = [0.0]
        for a0, a1 in zip(samples, samples[1:]):
            arc.append(arc[-1] + math.dist(pt(a0), pt(a1)))
        starts = []
        for k in range(n):
            target = (arc[-1] * (k / n + oi * 0.07)) % arc[-1]
            starts.append(samples[min(range(len(arc)), key=lambda i: abs(arc[i] - target))])
        for k, label in enumerate(labels):
            th = starts[k]
            x0, y0 = pt(th)
            x1, y1 = pt(th + math.pi)
            rel = (f"M0 0A{rx} {ry} {tilt} 1 1 {fmt(x1 - x0)} {fmt(y1 - y0)}"
                   f"A{rx} {ry} {tilt} 1 1 0 0")
            sid = d.i("ic-" + re.sub(r"[^a-z0-9]", "", label.lower()))
            motion.append(f'<g transform="translate({fmt(x0)} {fmt(y0)})"><g>'
                          f'<animateMotion begin="0s" dur="{period}s" repeatCount="indefinite" path="{rel}"/>'
                          f'<use xlink:href="#{sid}"/></g></g>')
            still.append(f'<use xlink:href="#{sid}" transform="translate({fmt(x0)} {fmt(y0)})"/>')
    d.body.append(f'<g class="fi" {delay(.2)}>' + "".join(orbit_svg) + "</g>")
    d.body.append(f'<circle class="{p}-pulse" cx="{cx}" cy="{cy}" r="46" fill="none" stroke="{BLUE}" stroke-width="2"/>'
                  f'<circle cx="{cx}" cy="{cy}" r="42" fill="url(#{p}-core)"/>'
                  f'<circle cx="{cx}" cy="{cy}" r="42" fill="none" stroke="{INK}" stroke-opacity=".35"/>'
                  + d.text(cx, cy + 3, "AI/ML", "d7", 19, INK, anchor="middle", ls=-.01)
                  + d.text(cx, cy + 19, "CORE", "m7", 9.5, INK, anchor="middle", ls=.25, attrs='fill-opacity=".75"'))
    d.body.append(f'<g class="motion fi" {delay(.35)}>' + "".join(motion) + "</g>")
    d.body.append('<g class="still">' + "".join(still) + "</g>")

    # grouped chips
    d.body.append(f'<path d="M64 {chips_top - 34}H{W - 64}" stroke="url(#{p}-orb)" stroke-opacity=".5"/>')
    k = 0
    for colx, items in zip(cols_x, (left, right)):
        for kind, label, x, y in items:
            ax, ay = colx + x, chips_top + y
            if kind == "label":
                d.body.append(f'<g class="fi" {delay(.5)}>' + d.text(ax, ay + 4, label.upper(), "m7", 12.5, CRIMSON, ls=.16) + "</g>")
                continue
            path, hexc, bg = brand(label)
            w = chip_w(label)
            ic = (f'<path transform="translate({fmt(ax + 13)} {fmt(ay + 17)}) scale({18 / 24:.4f})" d="{path}" fill="{hexc}"/>'
                  if path else glyph("braces", ax + 13, ay + 17, 18, BLUE, 2.2))
            dstroke = f' stroke="{INK}" stroke-opacity=".25"' if bg == CHIP_DARK else ""
            d.body.append(f'<g class="fu" {delay(.55 + k * .035)}>'
                          f'<rect x="{fmt(ax)}" y="{fmt(ay + 8)}" width="{fmt(w)}" height="{chip_h}" rx="{chip_h / 2}" fill="{INK}" fill-opacity=".05" stroke="{INK}" stroke-opacity=".14"/>'
                          f'<circle cx="{fmt(ax + 22)}" cy="{fmt(ay + 26)}" r="13.5" fill="{bg}"{dstroke}/>'
                          + ic
                          + d.text(ax + 44, ay + 31.5, label, "d5", 15.5, INK) + "</g>")
            k += 1
    return d


# ======================================================== ID + DASHBOARD ===
CODE39 = {
    "0": "nnnwwnwnn", "1": "wnnwnnnnw", "2": "nnwwnnnnw", "3": "wnwwnnnnn", "4": "nnnwwnnnw",
    "5": "wnnwwnnnn", "6": "nnwwwnnnn", "7": "nnnwnnwnw", "8": "wnnwnnwnn", "9": "nnwwnnwnn",
    "A": "wnnnnwnnw", "B": "nnwnnwnnw", "C": "wnwnnwnnn", "D": "nnnnwwnnw", "E": "wnnnwwnnn",
    "F": "nnwnwwnnn", "G": "nnnnnwwnw", "H": "wnnnnwwnn", "I": "nnwnnwwnn", "J": "nnnnwwwnn",
    "K": "wnnnnnnww", "L": "nnwnnnnww", "M": "wnwnnnnwn", "N": "nnnnwnnww", "O": "wnnnwnnwn",
    "P": "nnwnwnnwn", "Q": "nnnnnnwww", "R": "wnnnnnwwn", "S": "nnwnnnwwn", "T": "nnnnwnwwn",
    "U": "wwnnnnnnw", "V": "nwwnnnnnw", "W": "wwwnnnnnn", "X": "nwnnwnnnw", "Y": "wwnnwnnnn",
    "Z": "nwwnwnnnn", "-": "nwnnnnwnw", ".": "wwnnnnwnn", " ": "nwwnnnwnn", "*": "nwnnwnwnn",
}


def code39(data: str, x: float, y: float, h: float, narrow: float, wide: float, color: str) -> tuple[str, float]:
    out, cx = [], x
    for ch in f"*{data}*":
        pat = CODE39[ch]
        assert pat.count("w") == 3, ch
        for i, e in enumerate(pat):
            w = wide if e == "w" else narrow
            if i % 2 == 0:
                out.append(f'<rect x="{fmt(cx)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}"/>')
            cx += w
        cx += narrow  # inter-character gap
    return f'<g fill="{color}">{"".join(out)}</g>', cx - narrow - x


def build_id() -> Doc:
    W, H = 1000, 744
    d = Doc("id", W, H, "ID card and verified dashboard",
            f"Lanyard ID for {PERSON['name']}, {PERSON['role']}, {PERSON['lab']}, {PERSON['org']}. "
            "Verified, dated metrics: B.Tech CSE CGPA 8.47 (May 2026); Naukri Young Turks 2025, 98.61 percentile, "
            "rank 7,122; Hack Horizon 2.0, 170+ teams and 750+ participants (2026); "
            f"{GH_API['public_repos']} public GitHub repositories as of {AS_OF}.")
    d.frame_defs()
    p = d.p
    PX = 250            # pivot x (lanyard top)
    cxL, cyT, cw, chh = PX - 150, 214, 300, 470   # card box
    d.defs.append(f"""
<linearGradient id="{p}-metal" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#5d6679"/><stop offset=".3" stop-color="#f4f7fb"/><stop offset=".55" stop-color="#9aa3b4"/><stop offset=".8" stop-color="#e9edf3"/><stop offset="1" stop-color="#6b7487"/></linearGradient>
<linearGradient id="{p}-strap" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#b8122b"/><stop offset=".5" stop-color="{CRIMSON}"/><stop offset="1" stop-color="#b8122b"/></linearGradient>
<linearGradient id="{p}-cardbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbf9f4"/><stop offset="1" stop-color="#e9e5dc"/></linearGradient>
<linearGradient id="{p}-head" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="#1446b8"/></linearGradient>
<linearGradient id="{p}-photo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1c4fd1"/><stop offset=".55" stop-color="#0d1530"/><stop offset="1" stop-color="#b3142e"/></linearGradient>
<linearGradient id="{p}-foil" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9ad8ff"/><stop offset=".3" stop-color="#c9b2ff"/><stop offset=".55" stop-color="#ffb3cf"/><stop offset=".8" stop-color="#ffe7a3"/><stop offset="1" stop-color="#a5f5d2"/></linearGradient>
<linearGradient id="{p}-sweep" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".5" stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<clipPath id="{p}-cardclip"><rect x="{cxL}" y="{cyT}" width="{cw}" height="{chh}" rx="22"/></clipPath>
<clipPath id="{p}-photoclip"><rect x="{PX - 80}" y="{cyT + 104}" width="160" height="180" rx="18"/></clipPath>
<mask id="{p}-slot" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}"><rect width="{W}" height="{H}" fill="#fff"/><rect x="{PX - 26}" y="{cyT + 16}" width="52" height="10" rx="5" fill="#000"/></mask>
<path id="{p}-strapL" d="M{PX - 58} -40L{PX - 14} 150"/>
<path id="{p}-strapR" d="M{PX + 58} -40L{PX + 14} 150"/>""")
    d.css.append(f"""
.{p}-sweep{{animation:{p}-sweep 6s 2.4s cubic-bezier(.4,0,.2,1) infinite both}}
@keyframes {p}-sweep{{0%{{transform:translateX(0)}}30%,100%{{transform:translateX(560px)}}}}
.{p}-holo{{animation:{p}-holo 5s linear infinite both}}
@keyframes {p}-holo{{0%,100%{{filter:hue-rotate(0deg)}}50%{{filter:hue-rotate(70deg)}}}}
""")
    # --- lanyard + card (one symbol, used by motion + still layers) ---------
    portrait = png_uri(resized(ID_PNG, 300))
    strap_txt = ("RITESHKUMAR2E  ·  " * 6).strip()
    L = []
    # straps (drawn from far above so the drop never reveals an end)
    for side in ("L", "R"):
        sx = -58 if side == "L" else 58
        L.append(f'<path d="M{PX + sx} -800L{PX + sx * 14 / 58} 150" stroke="url(#{p}-strap)" stroke-width="24" stroke-linecap="butt"/>'
                 f'<path d="M{PX + sx} -800L{PX + sx * 14 / 58} 150" stroke="{NAVY}" stroke-opacity=".35" stroke-width="24" stroke-dasharray="1 3" />')
    for side in ("L", "R"):
        L.append(f'<text class="m7" font-size="9.5" fill="{INK}" fill-opacity=".9" letter-spacing="1.4">'
                 f'<textPath xlink:href="#{p}-strap{side}" startOffset="8">{escape(strap_txt)}</textPath></text>')
    d.used["m7"].update(strap_txt)
    # clasp: crimp, swivel ring, trigger hook, split ring through the slot
    L.append(f'<rect x="{PX - 22}" y="140" width="44" height="22" rx="5" fill="url(#{p}-metal)" stroke="#4a5263" stroke-width=".8"/>'
             f'<path d="M{PX - 22} 151h44" stroke="#4a5263" stroke-opacity=".5"/>'
             f'<rect x="{PX - 4}" y="160" width="8" height="10" fill="url(#{p}-metal)"/>'
             f'<ellipse cx="{PX}" cy="176" rx="9" ry="7" fill="none" stroke="url(#{p}-metal)" stroke-width="3.5"/>'
             f'<path d="M{PX - 7} 182 v18 a7 7 0 0 0 14 0 v-14" fill="none" stroke="url(#{p}-metal)" stroke-width="4.5" stroke-linecap="round"/>'
             f'<path d="M{PX + 7} 186 l-6 6" stroke="#4a5263" stroke-width="2" stroke-linecap="round"/>')
    # card
    card = [f'<g mask="url(#{p}-slot)">',
            f'<rect x="{cxL}" y="{cyT}" width="{cw}" height="{chh}" rx="22" fill="url(#{p}-cardbg)"/>',
            f'<g clip-path="url(#{p}-cardclip)">',
            f'<rect x="{cxL}" y="{cyT}" width="{cw}" height="90" fill="url(#{p}-head)"/>',
            f'<rect x="{cxL}" y="{cyT + 90}" width="{cw}" height="4" fill="{CRIMSON}"/>',
            d.text(cxL + 22, cyT + 56, "RESEARCH INTERN", "m7", 12.5, INK, ls=.16),
            d.text(cxL + 22, cyT + 76, PERSON["org"], "d5", 14, INK, attrs='fill-opacity=".85"'),
            f'<g class="{p}-holo"><rect x="{cxL + cw - 66}" y="{cyT + 38}" width="44" height="40" rx="9" fill="url(#{p}-foil)"/>'
            f'<path d="M{cxL + cw - 66} {cyT + 70}l34-32M{cxL + cw - 56} {cyT + 78}l34-32" stroke="#fff" stroke-opacity=".5"/>'
            + d.text(cxL + cw - 44, cyT + 64, "RK", "d7", 15, CARD_INK, anchor="middle", attrs='fill-opacity=".55"') + "</g>",
            f'<rect x="{PX - 80}" y="{cyT + 104}" width="160" height="180" rx="18" fill="url(#{p}-photo)"/>',
            f'<g clip-path="url(#{p}-photoclip)"><image x="{PX - 92}" y="{cyT + 112}" width="184" height="{round(184 * ID_PNG.height / ID_PNG.width)}" xlink:href="{portrait}"/></g>',
            f'<rect x="{PX - 80}" y="{cyT + 104}" width="160" height="180" rx="18" fill="none" stroke="{CARD_INK}" stroke-opacity=".12"/>',
            d.text(PX, cyT + 322, "RITESH KUMAR", "d7", 27, CARD_INK, anchor="middle", ls=.01, maxw=cw - 30),
            d.text(PX, cyT + 346, "AI/ML · Computer Vision", "d5", 14.5, "#3b4560", anchor="middle"),
            f'<path d="M{cxL + 22} {cyT + 364}H{cxL + cw - 22}" stroke="{CARD_INK}" stroke-opacity=".18" stroke-dasharray="3 4"/>',
            d.text(PX, cyT + 386, PERSON["lab"], "d5", 13, "#3b4560", anchor="middle", maxw=cw - 30),
            ]
    bars, bw = code39(PERSON["github"].upper(), 0, 0, 34, 1.05, 2.55, CARD_INK)
    bx = PX - bw / 2
    card.append(f'<g transform="translate({fmt(bx)} {cyT + 400})">{bars}</g>')
    card.append(d.text(PX, cyT + 452, f"*{PERSON['github'].upper()}*", "m5", 10.5, "#3b4560", anchor="middle", ls=.25))
    card.append(f'<g transform="translate({cxL - 120} 0) rotate(18 {cxL} {cyT})"><g class="{p}-sweep">'
                f'<rect x="{cxL - 60}" y="{cyT - 80}" width="90" height="{chh + 160}" fill="url(#{p}-sweep)"/></g></g>')
    card.append('</g>')
    card.append(f'<rect x="{cxL + .5}" y="{cyT + .5}" width="{cw - 1}" height="{chh - 1}" rx="21.5" fill="none" stroke="#fff" stroke-opacity=".6"/>')
    card.append('</g>')
    # split ring passing through the slot (drawn over card)
    ring = (f'<path d="M{PX - 7} 196 C{PX - 7} 206 {PX - 12} {cyT + 21} {PX} {cyT + 21}" fill="none" stroke="url(#{p}-metal)" stroke-width="4"/>'
            f'<path d="M{PX + 7} 196 C{PX + 7} 206 {PX + 12} {cyT + 21} {PX} {cyT + 21}" fill="none" stroke="url(#{p}-metal)" stroke-width="4"/>')
    d.defs.append(f'<g id="{p}-lanyard">' + "".join(L) + "".join(card) + ring + "</g>")

    # shadow on the panel, then the hanging group
    d.body.append(f'<ellipse cx="{PX}" cy="{cyT + chh + 22}" rx="120" ry="10" fill="#000" fill-opacity=".35"/>')
    # drop (translate), damped pendulum (rotate), steady swing (rotate) — all SMIL from 0s
    drop = ("0 -780;0 -780;0 0;0 -18;0 0", "0;.1;.52;.7;1", ".5 0 1 .6;.5 0 1 .6;.2 .7 .4 1;.6 0 .8 .4")
    land, total, A, period, zeta = 1.25, 7.0, 7.0, 1.6, 0.85
    ts = [round(i * 0.05, 2) for i in range(int(total / 0.05) + 1)]
    angles = [0.0 if t < land else A * math.exp(-zeta * (t - land)) * math.sin(2 * math.pi * (t - land) / period) for t in ts]
    angles[-1] = 0.0
    rv = ";".join(f"{a:.2f} {PX} 0" for a in angles)
    rk = ";".join(f"{t / total:.4f}" for t in ts)
    swing = ";".join(f"{a} {PX} 0" for a in (0, 1.7, 0, -1.7, 0))
    d.body.append(
        f'<g class="motion"><g>'
        f'<animateTransform attributeName="transform" type="translate" begin="0s" dur="1.3s" values="{drop[0]}" keyTimes="{drop[1]}" calcMode="spline" keySplines="{drop[2]}" fill="freeze"/>'
        f'<g><animateTransform attributeName="transform" type="rotate" begin="0s" dur="{total}s" values="{rv}" keyTimes="{rk}" fill="freeze"/>'
        f'<g><animateTransform attributeName="transform" type="rotate" begin="0s" dur="4.4s" repeatCount="indefinite" values="{swing}" keyTimes="0;.25;.5;.75;1" calcMode="spline" keySplines=".37 0 .63 1;.37 0 .63 1;.37 0 .63 1;.37 0 .63 1"/>'
        f'<use xlink:href="#{p}-lanyard"/></g></g></g></g>'
        f'<g class="still"><use xlink:href="#{p}-lanyard"/></g>')

    # --- dashboard -----------------------------------------------------------
    DX = 468
    DW = W - 56 - DX
    d.body.append(f'<g class="fi" {delay(.4)}>{d.eyebrow(DX, 78, "03", "VERIFIED")}</g>')
    d.body.append(f'<g class="fu" {delay(.5)}>' + d.text(DX - 2, 136, "By the numbers.", "d7", 50, INK, ls=-.03, maxw=DW) + "</g>")
    d.body.append(f'<g class="fu" {delay(.6)}>' + d.text(DX, 166, f"Dated facts only · GitHub data read {AS_OF}", "m5", 13, MUTED, maxw=DW) + "</g>")
    tiles = [
        ("MAY 2026", "8.47", "CGPA", ["B.Tech, Computer Science", "& Engineering"]),
        ("2025", "98.61", "percentile", ["Naukri Young Turks 2025", "Rank 7,122"]),
        ("2026", "170+", "teams", ["Hack Horizon 2.0", "750+ participants"]),
        (AS_OF.upper(), str(GH_API["public_repos"]), "public repos", ["GitHub · @" + PERSON["github"], f"Member since {GH_API['member_since']}"]),
    ]
    tw, th, tg = (DW - 14) / 2, 140, 14
    for k, (tag, num, unit, meta) in enumerate(tiles):
        x = DX + (k % 2) * (tw + tg)
        y = 192 + (k // 2) * (th + tg)
        c = BLUE if k in (0, 3) else CRIMSON
        g = f'<g class="fu" {delay(.7 + k * .12)}>' + d.panel(x, y, tw, th, 18)
        g += f'<rect x="{fmt(x + 20)}" y="{y + 20}" width="8" height="8" rx="2" fill="{c}"/>'
        g += d.text(x + 36, y + 28.5, tag, "m7", 11.5, MUTED, ls=.14, maxw=tw - 50)
        g += d.text(x + 18, y + 78, num, "d7", 44, INK, ls=-.03)
        nw = measure("d7", num, 44, -.03)
        g += d.text(x + 18 + nw + 8, y + 78, unit, "d7", 15, c, maxw=tw - nw - 34)
        for j, m in enumerate(meta):
            g += d.text(x + 20, y + 104 + j * 20, m, "d5", 14.5, MUTED, maxw=tw - 36)
        d.body.append(g + "</g>")

    ry0 = 192 + 2 * (th + tg) + 18
    d.body.append(f'<g class="fi" {delay(1.2)}>' + d.text(DX, ry0 + 8, f"FEATURED REPOS · GITHUB API · {AS_OF.upper()}", "m7", 11.5, MUTED, ls=.12, maxw=DW) + "</g>")
    for k, (name, _desc, _hl, repo, lang) in enumerate(PROJECTS):
        y = ry0 + 22 + k * 56
        lw = measure("d5", lang, 13.5)
        g = (f'<g class="fu" {delay(1.3 + k * .1)}><rect x="{DX}" y="{y}" width="{DW}" height="48" rx="12" fill="{INK}" fill-opacity=".04" stroke="{INK}" stroke-opacity=".1"/>'
             + d.text(DX + 16, y + 21, name, "d7", 15.5, INK))
        g += d.text(DX + 16, y + 38.5, repo, "m5", 11.5, MUTED, maxw=DW - lw - 64)
        g += f'<circle cx="{fmt(DX + DW - 16 - lw - 12)}" cy="{y + 24}" r="5" fill="{LANG_COLORS[lang]}"/>'
        g += d.text(DX + DW - 16, y + 28.5, lang, "d5", 13.5, MUTED, anchor="end")
        d.body.append(g + "</g>")
    return d


# =============================================================== CONNECT ===
def build_connect() -> Doc:
    W, H = 1000, 600
    d = Doc("cn", W, H, "Connect with Ritesh Kumar",
            "Let's connect: " + "; ".join(f"{pl} — {txt}" for _, pl, txt, _ in LINKS)
            + ". Clickable links are listed below this image.")
    d.frame_defs()
    p = d.p
    X = 56
    d.body.append(f'<g class="fi">{d.eyebrow(X + 8, 78, "04", "CONNECT")}</g>')
    d.body.append(f'<g class="fu" {delay(.1)}>' + d.text(X + 6, 140, "Let's build something.", "d7", 54, INK, ls=-.03) + "</g>")

    # framed photo — exact pixels, cropped to the person + pointing hand
    crop = POINT_PNG.crop((40, 0, 1452, 1024))
    fy = 176
    cards_x = 584
    ch, cg = 70, 20
    block_h = 4 * ch + 3 * cg
    fh = block_h
    fw = round(fh * crop.width / crop.height)
    fx = X
    photo = png_uri(resized(crop, 640))
    d.defs.append(f'<clipPath id="{p}-photo"><rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" rx="22"/></clipPath>')
    d.css.append(f"""
.{p}-nudge{{animation:{p}-nudge 2.4s cubic-bezier(.45,0,.2,1) infinite both}}
@keyframes {p}-nudge{{0%,55%,100%{{transform:translateX(0)}}75%{{transform:translateX(7px)}}}}
.{p}-chev{{animation:{p}-chev 1.8s ease-in-out infinite both}}
@keyframes {p}-chev{{0%,100%{{opacity:.25;transform:translateX(-3px)}}50%{{opacity:1;transform:translateX(3px)}}}}
""")
    d.body.append(f'<g class="fu" {delay(.2)}><g clip-path="url(#{p}-photo)">'
                  f'<image x="{fx}" y="{fy}" width="{fw}" height="{fh}" preserveAspectRatio="none" xlink:href="{photo}"/></g>'
                  f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" rx="22" fill="none" stroke="url(#{p}-hair2)" stroke-width="2"/></g>')
    if fx + fw > cards_x - 50:
        raise ValueError(f"connect photo too wide: {fx + fw}")
    # chevrons from the fingertip to the cards
    tip_y = fy + fh * 545 / 1024
    gx0 = fx + fw + 8
    for j in range(3):
        d.body.append(f'<g class="{p}-chev" style="animation-delay:{j * .2:g}s">'
                      + glyph("chev", gx0 + j * ((cards_x - gx0 - 26) / 3), tip_y - 11, 22, CRIMSON if j == 2 else BLUE, 2.6)
                      + "</g>")

    li_uri = png_uri(resized(LI_PNG, 96))
    cw = W - 40 - cards_x
    for k, (key, platform, txt, _href) in enumerate(LINKS):
        y = fy + k * (ch + cg)
        g = f'<g class="fu" {delay(.35 + k * .12)}>' + d.panel(cards_x, y, cw, ch, 20)
        tx, ty = cards_x + 14, y + 11
        g += f'<rect x="{tx}" y="{ty}" width="48" height="48" rx="13" fill="{INK}"/>'
        if key == "linkedin":
            lw = 30
            lh = lw * LI_PNG.height / LI_PNG.width
            g += f'<image x="{tx + 9}" y="{fmt(ty + (48 - lh) / 2)}" width="{lw}" height="{fmt(lh)}" xlink:href="{li_uri}"/>'
        elif key == "globe":
            g += glyph("globe", tx + 11, ty + 11, 26, BLUE, 2)
        else:
            hexc = "#" + ICON_META["GitHub" if key == "github" else "Gmail"]["hex"]
            g += f'<path transform="translate({tx + 11} {ty + 11}) scale({26 / 24:.4f})" d="{si_path(key)}" fill="{hexc}"/>'
        g += d.text(tx + 64, y + 30, platform, "d7", 19, INK)
        g += d.text(tx + 64, y + 52, txt, "d5", 15, MUTED, maxw=cw - 64 - 14 - 48)
        ax = cards_x + cw - 50
        g += (f'<g class="{p}-nudge" style="animation-delay:{1.4 + k * .3:g}s"><circle cx="{ax + 19}" cy="{y + ch / 2}" r="16" fill="{BLUE if k % 2 == 0 else CRIMSON}" fill-opacity=".16" '
              f'stroke="{BLUE if k % 2 == 0 else CRIMSON}" stroke-opacity=".7"/>' + glyph("arrow", ax + 10, y + ch / 2 - 9, 18, INK, 2.2) + "</g>")
        d.body.append(g + "</g>")
    d.body.append(f'<g class="fi" {delay(1.1)}>'
                  + d.text(cards_x + 4, fy + block_h + 46, "Clickable links are listed right below this card", "m5", 13, MUTED)
                  + glyph("down", cards_x + 4 + measure("m5", "Clickable links are listed right below this card", 13) + 8, fy + block_h + 34, 15, CRIMSON, 2.2)
                  + "</g>")
    return d


# ========================================================= README / misc ===
IMAGES = [("hero", "Intro — Ritesh Kumar, ML Engineer, Jamshedpur"),
          ("about-life", "About — what I build and my interests"),
          ("stack", "Stack — the tools I build with"),
          ("id-dashboard", "ID — lanyard card and verified, dated metrics"),
          ("connect", "Connect — LinkedIn, GitHub, email and portfolio")]


def readme() -> str:
    img = {k: f"![{alt}](./assets/{k}.svg?v=1)" for k, alt in IMAGES}
    rows = "\n".join(
        f"| **{name}** | {desc} | {hl} | {lang} | [{repo}](https://github.com/{PERSON['github']}/{repo}) |"
        for name, desc, hl, repo, lang in PROJECTS)
    links = " &nbsp;·&nbsp; ".join(f'<a href="{href}">{pl}</a>' for _, pl, _, href in LINKS)
    link_list = "\n".join(f"- **{pl}:** [{txt}]({href})" for _, pl, txt, href in LINKS)
    return f"""<!-- Generated by scripts/build_profile.py. Animated SVGs live in ./assets. -->

{img['hero']}

{img['about-life']}

{img['stack']}

{img['id-dashboard']}

## Projects

| Project | What it does | Highlights | Language | Repository |
| --- | --- | --- | --- | --- |
{rows}

<sub>Repository languages from the GitHub API, read {AS_OF}.</sub>

## GitHub activity

<p align="center">
  <img src="https://streak-stats.demolab.com/?user={PERSON['github']}&theme=tokyonight" height="150" alt="GitHub contribution streak for {PERSON['github']}" />
</p>

<p align="center">
  <img src="./assets/space-shooter.gif" alt="Space shooter game generated from my contribution graph" />
</p>

{img['connect']}

### Connect

{link_list}

<p align="center">{links}</p>
"""


PREVIEW = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Profile Preview</title>
<style>
:root{--bg:#ffffff;--fg:#1f2328;--line:#d0d7de;--muted:#59636e}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0d1117;--fg:#e6edf3;--line:#30363d;--muted:#9198a1}}
:root[data-theme="dark"]{--bg:#0d1117;--fg:#e6edf3;--line:#30363d;--muted:#9198a1}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
header{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:space-between;max-width:1260px;margin:0 auto;padding:16px}
header h1{font-size:16px;margin:0}
button{font:inherit;background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer}
.wrap{display:flex;flex-wrap:wrap;gap:32px;justify-content:center;padding:0 16px 48px}
.col{border:1px solid var(--line);border-radius:6px;padding:16px;min-width:0}
.desk{width:830px;max-width:100%}.mob{width:375px;max-width:100%}
.col h2{font-size:12px;font-weight:600;color:var(--muted);margin:0 0 12px;text-transform:uppercase;letter-spacing:.06em}
.col img{display:block;max-width:100%;height:auto;margin:0 0 16px}
</style></head><body>
<header><h1>GitHub profile preview: README width (830px) and phone width (375px)</h1>
<span><button data-t="light">Light</button> <button data-t="dark">Dark</button> <button data-t="">System</button></span></header>
<div class="wrap">
<section class="col desk"><h2>Desktop README column</h2>__IMGS__</section>
<section class="col mob"><h2>Phone</h2>__IMGS__</section>
</div>
<script>
document.querySelectorAll('button[data-t]').forEach(b=>b.addEventListener('click',()=>{
  const t=b.dataset.t; if(t) document.documentElement.dataset.theme=t; else delete document.documentElement.dataset.theme;}));
</script>
</body></html>
"""


def licenses_md() -> str:
    rows = "\n".join(f"| {label} | {title or '—'} | {'#' + ICON_META[title]['hex'] if title else '—'} | {ICON_META[title]['source'] if title else 'Generic braces glyph drawn for this profile (not a brand mark)'} |"
                     for label, title, _ in STACK)
    return f"""# Third-party assets and licenses

All five SVGs in this folder embed their fonts and images as data URIs. Rendering them makes no network requests.

## Fonts (embedded as subset WOFF2)

| Font | Weights | License | Source |
| --- | --- | --- | --- |
| Space Grotesk (display) | 500, 700 | SIL Open Font License 1.1, see `OFL-SpaceGrotesk.txt` | https://github.com/floriankarsten/space-grotesk via @fontsource/space-grotesk 5.3.0 |
| JetBrains Mono (mono) | 500, 700 | SIL Open Font License 1.1, see `OFL-JetBrainsMono.txt` | https://github.com/JetBrains/JetBrainsMono via @fontsource/jetbrains-mono 5.3.0 |

The fonts are subset to the characters each SVG uses. The OFL allows embedding and subsetting. The embedded fonts keep their original names, copyright notices and license strings.

## Icons

Brand icons come from **Simple Icons 16.34.0** (https://simpleicons.org, npm `simple-icons`). The icon data is released under **CC0 1.0**, see `LICENSE-simple-icons.md`. The brands themselves remain trademarks of their owners, and the icons are used here only to identify each technology or platform.

| Label | Simple Icons title | Colour | Upstream source (from Simple Icons metadata) |
| --- | --- | --- | --- |
{rows}
| GitHub (connect) | GitHub | #181717 | {ICON_META['GitHub']['source']} |
| Email (connect) | Gmail | #EA4335 | {ICON_META['Gmail']['source']} |

* **Git logo:** by Jason Long, licensed under **CC BY 3.0** (https://git-scm.com/downloads/logos).
* **LinkedIn:** Simple Icons no longer ships a LinkedIn icon. The connect card uses LinkedIn's official "In" bug, `LI-In-Bug.png`, unmodified apart from resizing. It comes from the `in-logo.zip` package on LinkedIn's brand site, https://brand.linkedin.com/downloads, downloaded {AS_OF}. LinkedIn and the In logo are trademarks of LinkedIn Corporation. Use follows https://brand.linkedin.com/policies.
* **Other glyphs:** the pin, flask, building, globe, arrow, chevron and braces glyphs are simple line drawings made for this profile.

## Photos

`id.png` and `right_pointing.png` are the profile owner's own images. They are embedded unmodified apart from resizing and, for the pointing photo, cropping. `id.png` keeps its original alpha channel. `right_pointing.png` has no alpha channel, so it is shown in a rounded photo frame exactly as supplied.
"""


def main():
    ASSETS.mkdir(exist_ok=True)
    builders = {"hero": build_hero, "about-life": build_about, "stack": build_stack,
                "id-dashboard": build_id, "connect": build_connect}
    for name, fn in builders.items():
        svg = fn().render()
        (ASSETS / f"{name}.svg").write_text(svg, encoding="utf8")
        print(f"assets/{name}.svg  {len(svg.encode()) / 1024:,.0f} KB")
    lic = ASSETS / "licenses"
    lic.mkdir(exist_ok=True)
    for src, dst in [("fonts/OFL-SpaceGrotesk.txt", "OFL-SpaceGrotesk.txt"),
                     ("fonts/OFL-JetBrainsMono.txt", "OFL-JetBrainsMono.txt"),
                     ("icons/LICENSE-simple-icons.md", "LICENSE-simple-icons.md")]:
        (lic / dst).write_bytes((VENDOR / src).read_bytes())
    (lic / "README.md").write_text(licenses_md(), encoding="utf8")
    (ROOT / "README.md").write_text(readme(), encoding="utf8")
    imgs = "".join(f'<img src="assets/{k}.svg?v=1" alt="{escape(a)}" width="1000">' for k, a in IMAGES)
    (ROOT / "preview.html").write_text(PREVIEW.replace("__IMGS__", imgs), encoding="utf8")
    DIST.mkdir(exist_ok=True)
    zpath = DIST / "RiteshKumar2e-profile.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "README.md", "README.md")
        for k, _ in IMAGES:
            z.write(ASSETS / f"{k}.svg", f"assets/{k}.svg")
        for f in sorted(lic.iterdir()):
            z.write(f, f"assets/licenses/{f.name}")
    print(f"{zpath.relative_to(ROOT)}  {zpath.stat().st_size / 1024:,.0f} KB")


if __name__ == "__main__":
    main()

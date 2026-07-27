#!/usr/bin/env python3
"""Generate the deployable publish/ folder from the source files.

Sources (edit these):     Outputs (generated — do not edit):
  re8-spec.html             publish/index.html
  re8-console-spec.html     publish/re8-console-spec.html
  renders/*.png             publish/renders/*.webp
  brand/, social-preview    publish/brand/, publish/social-preview.png
"""
import re, shutil, subprocess, pathlib, sys

ROOT = pathlib.Path(__file__).parent
PUB  = ROOT / "publish"
SITE = "https://re8.dev/"

def log(m): print(f"  {m}")

# ---------- 1. renders → webp ----------
def build_renders():
    out = PUB / "renders"; out.mkdir(parents=True, exist_ok=True)
    made = 0
    for png in sorted((ROOT / "renders").glob("*.png")):
        webp = out / (png.stem + ".webp")
        if webp.exists() and webp.stat().st_mtime >= png.stat().st_mtime:
            continue
        try:
            subprocess.run(["cwebp", "-quiet", "-q", "82", str(png), "-o", str(webp)], check=True)
            made += 1
        except (FileNotFoundError, subprocess.CalledProcessError):
            try:                                # fallback: Pillow
                from PIL import Image
                Image.open(png).save(webp, "WEBP", quality=82, method=6)
                made += 1
            except Exception as e:
                shutil.copy2(png, out / png.name)
                log(f"webp conversion unavailable ({e}) — copied {png.name}")
    for stray in out.glob("*.png"):
        if (out / (stray.stem + ".webp")).exists():
            stray.unlink()
    log(f"renders: {made} converted, {len(list(out.iterdir()))} present")

# ---------- 2. marketing page ----------
def build_index():
    h = (ROOT / "re8-spec.html").read_text()
    # point image references at the webp derivatives
    h = re.sub(r'(renders/[a-z0-9-]+)\.png', r'\1.webp', h)
    # absolute canonical/OG urls for deployment
    h = h.replace('<meta property="og:image" content="social-preview.png">',
                  f'<meta property="og:image" content="{SITE}social-preview.png">')
    h = h.replace('<meta name="twitter:image" content="social-preview.png">',
                  f'<meta name="twitter:image" content="{SITE}social-preview.png">')
    if 'rel="canonical"' not in h:
        h = h.replace("</title>", f'</title>\n<link rel="canonical" href="{SITE}">', 1)
    if 'rel="icon"' not in h:
        h = h.replace("</title>", '</title>\n<link rel="icon" type="image/svg+xml" href="brand/re8-mark.svg">', 1)
    (PUB / "index.html").write_text(h)
    log(f"index.html: {len(h)//1024} KB")

# ---------- 3. specification page ----------
def build_spec():
    src = ROOT / "re8-console-spec.html"
    if not src.exists():
        log("re8-console-spec.html missing — run tools-build-spec-html.py first"); return
    h = src.read_text()
    if 'rel="icon"' not in h:
        h = h.replace("</title>", '</title>\n<link rel="icon" type="image/svg+xml" href="brand/re8-mark.svg">', 1)
    (PUB / "re8-console-spec.html").write_text(h)
    log(f"re8-console-spec.html: {len(h)//1024} KB (diagrams inlined)")

# ---------- 4. static assets ----------
def build_assets():
    (PUB / "brand").mkdir(parents=True, exist_ok=True)
    for f in ("re8-mark.svg", "re8-mark-reverse.svg"):
        p = ROOT / "brand" / f
        if p.exists(): shutil.copy2(p, PUB / "brand" / f)
    sp = ROOT / "social-preview.png"
    if sp.exists(): shutil.copy2(sp, PUB / "social-preview.png")
    log("assets: brand marks + social preview")

# ---------- 5. verify ----------
def verify():
    idx = (PUB / "index.html").read_text()
    problems = []
    for m in re.finditer(r'(?:src|href)="(?!https?:|#|mailto:)([^"]+)"', idx):
        ref = m.group(1).split("#")[0]
        if ref and not (PUB / ref).exists(): problems.append(ref)
    for stale in ("8 MHz", "4-channel", "LQFP-64", "35-pin", "MMC3", "15kHz VGA"):
        if stale in idx: problems.append(f"stale copy: {stale!r}")
    if problems:
        print("  ✗ " + "\n  ✗ ".join(problems)); sys.exit(1)
    total = sum(f.stat().st_size for f in PUB.rglob("*") if f.is_file())
    log(f"verified: all references resolve · {total/1024/1024:.2f} MB total")

if __name__ == "__main__":
    print("building publish/ from source…")
    PUB.mkdir(exist_ok=True)
    build_renders(); build_index(); build_spec(); build_assets(); verify()
    print("done.")

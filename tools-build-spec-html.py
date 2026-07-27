import re, markdown, html, pathlib, base64

src = pathlib.Path("re8-console-spec.md").read_text()

# ---- pull title & strip H1 ----
title_line = src.split("\n",1)[0].lstrip("# ").strip()
_v = re.search(r'\*\*Version ([\d.]+)\*\*\s*·\s*([\d-]+)', src)
VERSION, VDATE = (_v.group(1), _v.group(2)) if _v else ("—", "")
body_md = src.split("\n",1)[1]

# ---- ensure a blank line precedes every list (markdown needs it, or the
# ---- list is absorbed into the preceding paragraph as lazy continuation) ----
def normalise_lists(text):
    LIST = re.compile(r'^\s{0,3}(?:[-*+]\s|\d+\.\s)')
    out, fence = [], False
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            fence = not fence
        elif not fence and LIST.match(line) and out:
            prev = out[-1]
            if (prev.strip() and not LIST.match(prev) and not prev.lstrip().startswith("|")
                    and not prev.startswith("#") and not prev.strip().startswith(">")
                    and not prev.startswith("    ")):
                out.append("")
        out.append(line)
    return "\n".join(out)

body_md = normalise_lists(body_md)

# ---- inline the SVG diagrams so the page is self-contained ----
_dg = {"n":0}
def inline_svg(m):
    alt, path = m.group(1), m.group(2)
    _dg["n"] += 1
    did = f"dg{_dg['n']}"
    svg = pathlib.Path(path).read_text()
    svg = re.sub(r'<\?xml[^>]*\?>', '', svg).strip()
    # scope every rule in the SVG's <style> block so the six diagrams cannot
    # override one another once inlined into a single document
    def scope(sm):
        css = sm.group(1)
        css = re.sub(r'(^|[},])\s*(\.[A-Za-z][\w-]*)', lambda x: f"{x.group(1)}#{did} {x.group(2)}", css)
        return f"<style>{css}</style>"
    svg = re.sub(r'<style>(.*?)</style>', scope, svg, flags=re.S)
    svg = svg.replace("<svg ", f'<svg id="{did}" ', 1)
    return f'<figure class="diagram">{svg}<figcaption>{html.escape(alt)}</figcaption></figure>'

body_md = re.sub(r'!\[([^\]]*)\]\((diagrams/[^)]+)\)', inline_svg, body_md)

md = markdown.Markdown(extensions=["tables","fenced_code","attr_list","toc","sane_lists"],
                       extension_configs={"toc":{"toc_depth":"2-3","anchorlink":False}})
body = md.convert(body_md)

# ---- wrap tables for horizontal scroll ----
body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")

# ---- build TOC from the generated heading ids (authoritative) ----
toc=[]
for m in re.finditer(r'<h([23]) id="([^"]+)">(.*?)</h\1>', body, re.S):
    lvl,slug,inner = int(m.group(1)), m.group(2), m.group(3)
    txt = html.unescape(re.sub(r'<[^>]+>','',inner)).strip()
    mm = re.match(r'^(\d+(?:\.\d+)*)\.?\s+(.*)$', txt)
    num, label = (mm.group(1), mm.group(2)) if mm else ("", txt)
    toc.append(f'<a class="t{lvl}" href="#{slug}"><span class="n">{html.escape(num)}</span>{html.escape(label)}</a>')
toc_html="\n".join(toc)

mark = pathlib.Path("brand/re8-mark.svg").read_text()
mark = re.sub(r'<\?xml[^>]*\?>','',mark).strip()

CSS = """
:root{
  --deep:#0a4f47; --base:#0e7a6c; --bright:#2fbfa9; --light:#8fe3d6; --mist:#e6f5f2; --white:#fff;
  --bg:#f7fbfa; --card:#ffffff; --ink:#1c2b28; --ink-soft:#48605b; --ink-faint:#7e948f;
  --line:#d9e8e4; --line-dark:#0a4f47; --code-bg:#1d2229; --code-text:#d5dbe3; --amber:#b9770e;
  --radius:14px; --maxw:1180px;
  --mono:'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --head:'Space Grotesk', sans-serif; --body:'Inter', system-ui, -apple-system, sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth; scroll-padding-top:74px}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--body);line-height:1.68;-webkit-font-smoothing:antialiased}
a{color:var(--base)}
::selection{background:rgba(47,191,169,.22)}

header.nav{position:sticky;top:0;z-index:60;background:rgba(247,251,250,.93);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.nav-inner{max-width:var(--maxw);margin:0 auto;padding:12px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px}
.brand{display:flex;align-items:center;gap:10px;font-family:var(--head);font-weight:700;font-size:19px;color:var(--ink);text-decoration:none}
.brand svg{width:26px;height:26px;border-radius:7px}
.brand .sub{font-family:var(--mono);font-size:11px;font-weight:500;color:var(--ink-faint);letter-spacing:.08em;text-transform:uppercase;padding-left:10px;margin-left:4px;border-left:1px solid var(--line)}
.navlinks{display:flex;gap:2px}
.navlinks a{font-family:var(--mono);font-size:12.5px;color:var(--ink-soft);text-decoration:none;padding:8px 12px;border-radius:8px}
.navlinks a:hover{color:var(--deep);background:var(--mist)}

.shell{max-width:var(--maxw);margin:0 auto;padding:0 24px;display:grid;grid-template-columns:266px 1fr;gap:44px;align-items:start}
aside{position:sticky;top:74px;max-height:calc(100vh - 90px);overflow-y:auto;padding:26px 0 40px;scrollbar-width:thin}
aside::-webkit-scrollbar{width:6px}
aside::-webkit-scrollbar-thumb{background:var(--line);border-radius:3px}
.toc-h{font-family:var(--mono);font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--base);font-weight:700;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid var(--bright);list-style:none;cursor:default}
.toc-h::-webkit-details-marker{display:none}
@media(max-width:1000px){.toc-h{cursor:pointer;display:flex;justify-content:space-between;align-items:center}
 .toc-h::after{content:'▾';font-size:13px;transition:.2s}
 details[open] .toc-h::after{transform:rotate(180deg)}}
aside a{display:block;text-decoration:none;color:var(--ink-soft);border-radius:7px;transition:.13s}
aside a:hover{background:var(--mist);color:var(--deep)}
aside a.t2{font-size:13.5px;font-weight:600;padding:7px 9px;margin-top:5px;color:var(--ink)}
aside a.t3{font-size:12.2px;padding:4px 9px 4px 26px;color:var(--ink-soft)}
aside a .n{font-family:var(--mono);color:var(--base);font-size:11px;font-weight:700;margin-right:7px}
aside a.active{background:var(--mist);color:var(--deep)}

main{padding:34px 0 90px;min-width:0}
.doc-title{font-family:var(--head);font-weight:700;font-size:clamp(1.9rem,4vw,2.7rem);line-height:1.1;letter-spacing:-.02em;margin:0 0 10px}
.doc-kicker{display:inline-flex;align-items:center;gap:9px;font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--base);border:1.5px solid var(--base);background:var(--mist);padding:5px 12px;border-radius:4px;margin-bottom:20px}

main h2{font-family:var(--head);font-weight:700;font-size:clamp(1.4rem,2.6vw,1.85rem);letter-spacing:-.015em;color:var(--ink);
  margin:66px 0 18px;padding-top:22px;border-top:1px solid var(--line)}
main h3{font-family:var(--head);font-weight:600;font-size:1.12rem;color:var(--deep);margin:38px 0 12px}
main h4{font-family:var(--head);font-weight:600;font-size:1rem;color:var(--ink);margin:26px 0 8px}
main p{margin:0 0 15px;text-wrap:pretty}
main ul,main ol{margin:0 0 16px;padding-left:22px}
main li{margin:0 0 7px}
main li>p{margin:0 0 7px}
strong{color:var(--ink);font-weight:600}
em{color:var(--ink-soft)}
hr{border:none;border-top:1px solid var(--line);margin:34px 0}

code{font-family:var(--mono);font-size:.845em;background:var(--mist);color:var(--deep);padding:1.5px 5px;border-radius:4px;border:1px solid #cfe7e1}
pre{background:var(--code-bg);color:var(--code-text);padding:18px 20px;border-radius:var(--radius);overflow-x:auto;font-family:var(--mono);font-size:12.4px;line-height:1.6;margin:0 0 18px}
pre code{background:none;border:none;color:inherit;padding:0;font-size:inherit}

.table-wrap{overflow-x:auto;border:1px solid var(--line-dark);border-radius:var(--radius);background:var(--card);margin:0 0 20px}
table{width:100%;border-collapse:collapse;font-size:.855rem;min-width:460px}
thead th{text-align:left;font-family:var(--mono);font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--mist);background:var(--deep);padding:10px 14px;font-weight:500}
tbody td{padding:10px 14px;border-bottom:1px solid var(--line);color:var(--ink-soft);vertical-align:top}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:rgba(47,191,169,.05)}
td code{color:var(--amber);background:#fdf6e9;border-color:#f0e2c6}

figure.diagram{margin:26px 0 30px;padding:20px 20px 12px;background:var(--card);border:1px solid var(--line-dark);border-radius:var(--radius)}
figure.diagram svg{width:100%;height:auto;display:block}
figure.diagram figcaption{margin-top:14px;padding-top:11px;border-top:1px solid var(--line);font-family:var(--mono);font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--ink-faint)}

main>p:first-of-type{font-size:1.06rem;color:var(--ink-soft)}
footer{border-top:1px solid var(--line);margin-top:40px;padding:26px 0 60px;font-size:12.5px;color:var(--ink-faint);font-family:var(--mono)}
@media(max-width:1000px){.shell{grid-template-columns:1fr;gap:0;padding:0 18px}
 aside{position:static;max-height:none;border-bottom:1px solid var(--line);margin-bottom:6px;padding:16px 0 12px}
 .navlinks{display:none}
 main{padding-top:20px}
 .doc-title{font-size:1.75rem}
 figure.diagram{padding:12px 12px 8px;margin-left:-4px;margin-right:-4px}
 table{font-size:.8rem}}
"""

JS = """
if(matchMedia('(max-width:1000px)').matches){const d=document.getElementById('toc'); if(d) d.open=false;}
const links=[...document.querySelectorAll('aside a')];
const map=new Map(links.map(a=>[a.getAttribute('href').slice(1),a]));
const obs=new IntersectionObserver(es=>{
 es.forEach(e=>{if(e.isIntersecting){links.forEach(l=>l.classList.remove('active'));
  const a=map.get(e.target.id); if(a){a.classList.add('active');}}});
},{rootMargin:'-70px 0px -75% 0px',threshold:0});
document.querySelectorAll('main h2[id],main h3[id]').forEach(h=>obs.observe(h));
"""

out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title_line)} v{VERSION} — re8</title>
<meta name="description" content="Normative technical specification for the re8 console: W65C02S CPU, oito custom ASIC, memory map, register file, timing, BOM and conformance contract.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<header class="nav"><div class="nav-inner">
  <a class="brand" href="index.html">{mark}<span>re8</span><span class="sub">Spec v{VERSION}</span></a>
  <nav class="navlinks">
    <a href="index.html">Overview</a>
    <a href="#5-memory-map">Memory map</a>
    <a href="#6-oito-custom-asic">oito</a>
    <a href="#14-sdk-and-tooling">SDK</a>
    <a href="#16-conformance-validation">Conformance</a>
  </nav>
</div></header>

<div class="shell">
  <aside><details id="toc" open><summary class="toc-h">Contents</summary><div class="toclist">{toc_html}</div></details></aside>
  <main>
    <div class="doc-kicker">Normative specification · v{VERSION}</div>
    <h1 class="doc-title">{html.escape(title_line)}</h1>
    {body}
    <footer>re8 console — normative specification · <strong>version {VERSION}</strong> · {VDATE} · rationale and resolution history in <code>re8-design-history.md</code></footer>
  </main>
</div>
<script>{JS}</script>
</body>
</html>"""

pathlib.Path("re8-console-spec.html").write_text(out)
print("wrote re8-console-spec.html", len(out)//1024, "KB;", len(toc), "headings;", out.count("<figure"), "diagrams inlined")

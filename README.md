<p align="center">
  <img src="brand/re8-mark.svg" width="72" height="72" alt="re8 mark">
</p>

<h1 align="center">re8</h1>
<p align="center"><strong>a boutique 2D console built from factory-fresh parts</strong></p>
<p align="center"><a href="https://re8.dev">re8.dev</a></p>

---

**re8** is a ground-up 2D games console specified around a W65C02S CPU and a single custom ASIC (**oito**) — video, 16-voice audio, cartridge mapping and system glue in one chip. No New Old Stock: every part is currently manufactured. This repo holds the normative specification, design history, diagrams and brand assets.

## Contents

| Path | What it is |
|---|---|
| `re8-console-spec.md` / `.html` | The normative technical specification |
| `re8-design-history.md` | Rationale, decision log and review registers |
| `re8-spec.html` | Marketing / landing page source |
| `diagrams/` | System, timing and arbitration diagrams (SVG) |
| `renders/` | Product renders |
| `brand/` | Logo mark and brand guidelines |
| `RE-8 Console.blend` | Blender source for the console renders |
| `build-publish.py`, `tools-build-spec-html.py` | Build scripts that generate the deployable `publish/` site |

## Status

Architecture draft, version 0.1 (2026-07-26). See `re8-console-spec.md` for the current outstanding items before compatibility freeze.

## Building the site

```
python3 build-publish.py
```

Generates `publish/` from the HTML/Markdown sources, renders and brand assets. Requires `cwebp` for image optimization (falls back to PNG if unavailable). `publish/` is what's deployed live at [re8.dev](https://re8.dev); it's gitignored here since it's generated output.

## License

No license has been chosen yet — content is shared for reference only.

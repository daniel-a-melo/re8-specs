<p align="center">
  <img src="brand/re8-mark.svg" width="72" height="72" alt="re8 mark">
</p>

<h1 align="center">re8</h1>
<p align="center"><strong>a boutique 2D console built from factory-fresh parts</strong></p>
<p align="center"><a href="https://re8.dev">re8.dev</a></p>

<p align="center">
  <img src="renders/re8-hero.png" width="820" alt="re8 console, hero render">
</p>

---

> **A note on reality:** re8 isn't a real product — not yet, anyway. It's a detailed design exercise, and none of this hardware has been built. Any partnership shown in this repo is imagined: the companies named have no knowledge of, or involvement in, this project, and all trademarks remain theirs.

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
| `requirements.txt` | Pinned Python dependencies (`markdown`) |
| `artefacts/bus-traces.md` | Bus conformance traces — generated, not edited |

### The scripts

Six Python files, in the order the build runs them. None is optional; `build-publish.py` invokes
the first four and aborts on any failure.

| Script | What it does |
|---|---|
| `tools-model.py` | **The arithmetic.** ~30 design choices in one `CHOICES` dict; everything else is derived from them — bandwidth totals, tile throughput, sprite budgets, PCM tax, OAM DMA floor *and* ceiling, ASRC increment and servo poles, PHI2 margins, pin/package/header counts. Run it to print the table. Nothing in it is a decision; it exists so no figure in the spec is typed by hand. |
| `tools-bus-model.py` | **The behaviour.** The CPU bus contract as one `step()` function, exhaustively checked over its ~12,500 reachable states. Ten properties, plus every historical bus blocker reintroduced as a mutation that must break its named property. Also emits `artefacts/bus-traces.md`. |
| `tools-bus-inject.py` | Writes the bus model's tables into the spec between `<!-- GENERATED … -->` markers, so §6.5's and §8.5's timing tables are **output** rather than prose. `--check` reports staleness without writing. |
| `tools-build-spec-html.py` | Renders `re8-console-spec.md` → `.html`, inlining the SVG diagrams so the page is self-contained. |
| `tools-verify.py` | **The consistency check** — eight classes, listed below. Reads every document, the diagrams and the marketing page. Exit code 1 on any failure. `RE8_SKIP_BUS=1` skips the 12 s bus run when iterating on prose; the build never sets it. |
| `tools-mutate.py` | **Checks the checks.** Reintroduces each guard's target defect in a **throwaway copy** of the repo and reports any guard that fails to fire. `--list` shows the suite. The live tree is never modified. |
| `build-publish.py` | Orchestrates: bus model → inject → HTML → verify → `publish/`. |

### The parts ledger

`re8-parts-ledger.json` is the evidence file behind every component the spec names — **30 active
parts and 4 removed**. Each entry records the `claim` the spec makes about the part, the `source`
URL, and the date that source was **actually read**. It exists because v0.9 shipped an input
polyfuse that does not exist, invented while resolving a review finding and entered in a document
with no place to check it.

Verification is **four orthogonal fields**, not one flag, because a single boolean conflated things
that fail independently:

| Field | Meaning |
|---|---|
| `opn_complete` | Is `part` an orderable number, or a base/family number needing a suffix **chosen**? *(4 are not orderable.)* |
| `suffix_evidence` | `exact-page` (a part-details page for this suffix, 9) · `datasheet` (read, but its ordering table not matched to the suffix, 6) · `family-page` (cannot establish a suffix at all, 15) |
| `electrical_evidence` | Were the claims in `claim` read from a datasheet, or not? |
| `lifecycle_evidence` | Written production status. Five newly selected Nexperia interface parts carry exact-page evidence; the other 25 remain `none` rather than inferred from a URL. |

`tools-verify.py` **generates §16.2's three parts queues from these fields** and fails if the spec's
lists drift. A previous hand-typed version said "21 parts" and wrongly included four whose sources
were already exact part-details pages.

## Status

Architecture draft, **version 0.23.1** (2026-07-30). **Twenty-two adversarial reviews performed, twenty-two dispositioned** — `tools-verify.py` derives both from the review files and the design-history registers and fails if any document states a different one. See `re8-console-spec.md` §16.2 for the staged SDK, schematic, tapeout, prototype and release gates, and `re8-design-history.md` for how each design decision was dispositioned.

## Setup

```
python3 -m pip install -r requirements.txt
```

`markdown` is required — `build-publish.py` generates the spec HTML before verifying, so
without it the build aborts on a clean checkout. `cwebp` is the optional one (image
optimisation falls back to PNG).

## Validating before you publish

Run these four, in order, and read the output rather than the exit code alone.

```
python3 tools-bus-model.py     # 1. behaviour: properties + historical regressions
python3 tools-mutate.py        # 2. the checks themselves still fire
python3 tools-verify.py        # 3. consistency across every document
python3 build-publish.py       # 4. generate publish/ (re-runs 1, 3 and aborts on failure)
```

**What each must say.** `build-publish.py` alone is not sufficient — it runs steps 1 and 3 but not
step 2, and step 2 is what tells you the other two are still capable of failing.

| Step | Pass looks like | Stop if |
|---|---|---|
| 1 | every property `HOLDS`, every regression `caught`, the mechanism test `correct` | any `FAILS` or `NOT CAUGHT` — a property has been weakened, or the contract is broken |
| 2 | every mutation `caught`, `The live tree was never modified.` | any `NOT CAUGHT` (the guard is weaker than it looks) or `ANCHOR MISSING` (the mutation's anchor text moved, so it has been testing nothing) |
| 3 | `verified: model, facts, parts, artefacts — N warning(s)` | any line beginning `FAIL` |
| 4 | `done.` | any `build aborted:` |

**Warnings are not failures, but they are not noise either.** The expected 25 are all parts-ledger
items with a matching gate in §16.2 — unresolved suffixes, family-page sources, incomplete orderable
numbers. If the count *rises*, read the new one: three permanent false warnings were removed in v0.16
precisely so a real one would stand out.

**Two habits worth keeping.**

- **After changing a rule, add its mutation.** A guard that has never been observed to fail is not
  evidence of anything, and step 2 is where that gets tested. Three guards have been found
  ineffective this way, one of which did not exist at all.
- **Never edit the spec by document-wide `text.index()`.** The front-page outstanding list holds a
  one-cell copy of every §16.2 row title, so an unanchored index match lands there and is then
  overwritten when that list regenerates. Two §16.2 gates were lost exactly this way, and two
  decisions claimed them for a whole revision. Slice the section first.

## Checking one thing at a time

```
python3 tools-model.py                      # print every derived quantity
python3 tools-bus-inject.py --check         # are the generated tables stale?
python3 tools-mutate.py --list              # what the mutation suite covers
RE8_SKIP_BUS=1 python3 tools-verify.py      # fast consistency pass, no bus run
```

`RE8_SKIP_BUS=1` adds one warning of its own — `BUS property run SKIPPED` — so expect **26**
rather than 25. It is there so a skipped check cannot be mistaken for a passed one.

## What the verifier checks

Through round seven (v0.7, 2026-07-27) the reviews had found roughly 250 defects, and the largest
single class was numbers written by hand that could have been derived — which is why these tools
exist. That figure is a **dated snapshot of the motivation, not a running total**; current review
status is in Status above and the per-round findings are in `re8-design-history.md`.

`tools-verify.py`'s eight classes, run against every document, the diagrams and the marketing page:

| Check | Catches |
|---|---|
| **MODEL** | a published figure that no longer matches its derivation, and invariants: display load exceeding slot capacity, a sprite budget falling below its floor, an unstable servo, a phase increment that overflows, a PHI2 margin that goes negative |
| **STRUCT** | a *second, incompatible rule* — two PHI2 origins, two read-capture rules, a stalled cycle that "retires", fixed-64 filter arithmetic outside the marked rejected block, a NAND in a live cartridge population, a §16.2 blocker missing from the front-page summary, a parts queue that has drifted from the ledger |
| **HTML** | the generated spec page carrying a different version from the Markdown |
| **DIAGRAM** | a superseded fact inside an SVG *text node* — these are inlined into the normative HTML, so a figure's caption ships as part of the contract |
| **COUNT** | review status stated as one number when *performed* and *dispositioned* differ |
| **FACTS** | a superseded value reappearing anywhere — `LQFP-144`, `DVI-D`, a transposed part suffix. A sentence *about* the supersession is allowed |
| **PARTS** | a part number named in the spec but absent from `re8-parts-ledger.json`, or a ledger entry with no source URL and date it was actually read |
| **ARTEFACTS** | a deliverable described in the present tense when the file does not exist |

`build-publish.py` proves the bus properties, regenerates the bus tables and the spec HTML, runs
the verifier, then publishes — **in that order, so what is checked is what ships.** Earlier it copied
a checked-in HTML instead of generating it, and shipped a v0.8 contract beside a v0.11 README.

**What it does not do.** The first version of this verifier passed while seven contradictions sat
in the documents, because it checked that desired values were *present* and never that superseded
ones were *absent*. The second passed while six more stood, because presence and absence are both
substring tests and neither can see a contradiction that lives three paragraphs away — and because
its supersession exemption worked on whole paragraphs, so one "…is deleted" clause could excuse a
live requirement in the same line. **STRUCT** exists for that class, its exemptions are scoped to
sentences, and every guard in it has been tested by reintroducing the defect it targets.

That last habit earns its keep, and it now has its own tool. `tools-mutate.py` reintroduces each
defect in a **temp copy** of the repo and reports any guard that fails to fire. It exists because
round seventeen found two decisions and a version-history row claiming §16.2 gates that were not in
the document — the edits had landed in the front-page list, whose rows are one-cell copies of the
same titles, and were then overwritten by its regeneration. Mutating the live file is how work gets
reverted; mutating a copy is not. Its first run found two guards weaker than believed and one that
did not exist.

The sentence splitter added for the second problem was itself broken — a markdown `*` between the
full stop and the space defeated the split, so an exempt clause still swallowed the next requirement
— and it was found only because a guard that should have fired didn't. **A guard that has never been
observed to fail is not evidence of anything.** A checker is still a floor, not a guarantee:
anything it does not encode, it does not catch.

## The bus model

```
python3 tools-bus-model.py    # exhaustive state-space check + generated traces
```

Of the 19 blockers found in review rounds 10–14, **13 were in the CPU bus contract**, and each
was one of three shapes: two transitions given for the same state, a rule whose consequences
weren't propagated, or a rule quantified over one agent instead of all. Prose cannot prevent any
of those.

`tools-bus-model.py` holds the contract as a single `step()` function and enumerates the
**complete reachable state space** — ~12,500 states across nine cycle kinds and both external halt
requesters (three parties share the `RDY` pin; the CPU's own `WAI` is exempt, and the model
says why) — checking ten properties: one strobe, one grant and one commit per transaction; nothing
commits at a hold edge; a takeover preserves the transaction; no producer event is ever erased; a
held external read keeps its chip select; every owner reaches the memory it is documented to use;
ownership is one-hot; and every owner's accesses can commit. §6.5's and §8.5's tables are
**generated from it**, so a sentence can no longer contradict a table.

All eleven historical bus blockers are reintroduced as model mutations and must break their named
property, so the properties are demonstrated to be capable of failing rather than merely passing:

| Reintroduced | Property that catches it |
|---|---|
| R10-CPU1 capture at the preceding edge | `one_grant_per_txn` |
| R11-CPU1 suppressing term cleared at grant | `one_grant_per_txn` |
| R11-DMA1 effects fire at every edge | `no_effect_at_hold_edge` |
| R12-BUS1 takeover ends the transaction | `txn_survives_takeover` |
| R12-BUS2 external writes stalled | `ext_strobe_once` |
| R13-READ1 commit uses live state | `no_event_lost` |
| R14-BUS1 rule bound to oito alone | `ext_strobe_once` |
| R15-BUS1 validity made to depend on `RDY` | `read_select_held` |
| R15-BUS2 decode term named only the CPU | `decode_owner_complete` |
| R16-BUS4 CPU-only acceptance condition | `probe_can_commit` |
| R16-BUS5 driver enables keyed on wired-AND `BE` | `one_hot_ownership` |

And one **mechanism test**, which is a stronger claim than a regression: remove the scheduling rule
*and* add the late validity gating, and `ext_strobe_once` must **still fail**. If it passed, the
property would be satisfied by something silicon cannot do — suppressing a pulse that has already
been emitted.

It does **not** cover the ASRC filter, the parts ledger or the prog8 pipeline — different
problems, unhelped by this notation.

**And it has not closed the class.** Rounds 15 and 16 each found bus blockers the model was silent
on, because each found its next missing dimension: round 15, that it had no decode; round 16, that
it modelled `owner` as a label rather than a contended resource, and acceptance as one condition
rather than a family. Both gaps are now represented — which is why the state space went from ~1,900
to ~12,500. The gaps are getting more specific, which is progress of a kind, but **a model's scope
is a claim and deserves the same scepticism as any other claim here.**

## Building the site

```
python3 build-publish.py
```

Generates `publish/` from the HTML/Markdown sources, renders and brand assets. Requires `cwebp` for image optimization (falls back to PNG if unavailable). `publish/` is what's deployed live at [re8.dev](https://re8.dev); it's gitignored here since it's generated output.

## License

No license has been chosen yet — content is shared for reference only.

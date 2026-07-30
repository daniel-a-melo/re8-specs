#!/usr/bin/env python3
"""
re8 consistency verifier.

Six checks, run over every document in the repo — INCLUDING the generated
re8-console-spec.html, whose omission is how a v0.8 contract once shipped beside
a v0.11 README while this script printed "verified":

  1. MODEL     — figures in the spec must match tools-model.py
  2. STRUCT    — structural invariants: one PHI2 origin, one read-capture rule,
                 RDY-held retirement distinguished from sampling, fixed ASRC
                 dimensions confined to the marked rejected block, no NAND in a
                 live cartridge population, the front-page outstanding list equal
                 to §16.2, and the §16.2 parts queues generated from the ledger
  3. HTML      — the generated spec page must carry the Markdown's version
  4. FACTS     — one canonical value per fact; superseded values are banned
  5. PARTS     — every named part in the ledger, with four ORTHOGONAL evidence
                 fields rather than one boolean
  6. ARTEFACTS — files named as deliverables must exist, or be future-tense

Checks 1 and 4 test whether a string is present or absent. That is not enough on
its own: round ten found this script passing while six contradictions stood,
because a second, incompatible rule three paragraphs away is invisible to a
substring search. Check 2 exists for those, and every guard in it has been
tested by deliberately reintroducing the defect it is meant to catch.

Exit code 1 on any failure. Run before every commit; run before every release.
"""
import json
import pathlib
import re
import sys

# The model is exec'd from source rather than imported: importlib caches bytecode in
# __pycache__, and a verifier that can silently check a stale model is worse than none.
class _Mod:
    pass


_mod = _Mod()
_src = pathlib.Path(__file__).with_name("tools-model.py").read_text()
exec(compile(_src, "tools-model.py", "exec"), _mod.__dict__)
M = _mod.model()

ROOT = pathlib.Path(__file__).parent
SPEC = ROOT / "re8-console-spec.md"
SPEC_HTML = ROOT / "re8-console-spec.html"
# The generated spec HTML is the page README calls normative, so it is checked
# like any other document. Omitting it is how a v0.8 contract shipped beside a
# v0.11 README while this script printed "verified".
DOCS = [SPEC, ROOT / "README.md", ROOT / "re8-spec.html", SPEC_HTML] \
     + sorted(ROOT.glob("diagrams/*.svg"))
# The version-history table records what earlier revisions said, deliberately.
HISTORY_ROW = re.compile(r"^\| \*\*\d+\.\d+(?:\.\d+)?\*\* \|")
# A superseded value may legitimately appear in a sentence *about* its supersession.
# SCOPED, not permissive: an earlier version of this regex matched "not the" and
# "earlier revision" anywhere in arbitrary prose, which let a line stay exempt
# while remaining a current requirement. A line is exempt only if it BOTH names a
# supersession AND is not phrased as an active requirement.
SUPERSESSION = re.compile(
    r"rather than|no longer|replaced|superseded|withdrawn|used to|formerly|"
    r"does not exist|earlier revision|is deleted|previous revision|"
    r"does not describe|no longer describes|is withdrawn|are withdrawn|"
    r"rejected baseline|NON-NORMATIVE", re.I)
REQUIREMENT = re.compile(r"\bMUST\b|\bmust be\b|\bshall\b|\bis normative\b")
# Blocks whose contents are explicitly non-normative history. Fixed dimensions of
# the rejected filter may appear here and nowhere else.
REJECTED_BLOCK = ("#### 8.4.1", "#### 8.4.2")

fails, warns = [], []

# ── inventories the structural checks quantify over ───────────────────────────
# Enumerated as DATA rather than baked into one sentence pattern, because a guard
# shaped like a sentence checks that sentence and nothing else.
RDY_PULLERS = [
    ("oito", "asserts RDY for PCM refills and OAM DMA"),
    ("probe", "asserts RDY for host halt, crash freeze, register capture, "
              "live access and dev bootstrap"),
]
BUS_OWNERS = ["CPU", "oito", "probe"]
W1C_REGISTERS = [
    ("IRQ_STATUS",   "interrupt acknowledge"),
    ("STATUS", "sprite overflow, plus a frame-boundary auto-clear"),
    ("INPUT_STATUS", "port/keyboard/mouse change"),
    ("KBD_STATUS",   "keyboard FIFO overflow"),
]
PROG8_ORIGINS = [("$8040", "bank 0"), ("$8000", "other switchable banks"),
                 ("$C000", "fixed bank")]

# Named §16.2 gates that MUST exist. This inventory is the answer to the worst
# defect of round seventeen: the v0.18 history row and decisions D447/D448 both
# claimed §16.2 rows that were NOT in the document -- a mutation-test restore had
# reverted them from a stale snapshot, and nothing re-checked afterwards.
#
# A claim to have added a gate now means adding its title here, and this check
# makes the claim and the document fail or pass together. Prose asserting that a
# gate exists is not evidence; this list is.
REQUIRED_GATES = [
    ("Held external-read persistence", "R16-VAL1 / D447"),
    ("Snapshot-and-commit traces",     "R16-VAL2 / D448"),
    ("External-write scheduling",      "R14-VAL1 / D435"),
    ("`cpu_transfer_accept`, once per transaction", "R12 / D397"),
    ("ASRC filter design",             "R9 / deferred, \u00a716.2.1"),
    ("prog8 RAM arena ownership",      "R13-SW1 / D419"),
    ("prog8 initialised-data transformation", "R13-SW1 / D419"),
    ("CH7035B I\u00b2S voltage domain", "R11-HW1 / D404"),
    ("Probe bus ownership and transfers", "R17-VAL3 / D455"),
]

VALIDATION_HEADING = "### 16.2 Open implementation, qualification and release gates"


def validation_section(text):
    return text.split(VALIDATION_HEADING)[1].split("### 16.2.1")[0]


def validation_gate_titles(section):
    """Return only the main gate table's Item cells, not the preceding stage table."""
    table = section.split("| Item | Stage | Completion evidence | Ref |")[1]
    return [line.split("|")[1].strip() for line in table.split("\n")
            if line.startswith("|") and not line.startswith("|---")]


def exempt(line):
    return bool(SUPERSESSION.search(line)) and not REQUIREMENT.search(line)


def segments(text):
    """Sentences and table cells, not whole lines.

    A Markdown paragraph is one line, so line-granularity exemption let a single
    "…is deleted" clause at the end of a paragraph excuse a live requirement at
    its start. Round ten's "non-saving carts carry NOR + a single NAND" sat in
    exactly such a paragraph and passed. Splitting on sentence and cell
    boundaries makes an exemption cover only the clause that earns it.

    Emphasis markers must be allowed to sit between the full stop and the space:
    "...same paragraph.* **The build..." ends a sentence, but a naive
    (?<=[.;:])\\s never fires, because the character before the space is '*'.
    That defect hid a live requirement behind an exempt clause in this very
    function's first version - the same shape it exists to catch.
    """
    SPLIT = re.compile(r"(?<=[.;:])[*_`)\]]*\s+(?=[*_`#\[—]*[A-Z])")
    for line in text.split("\n"):
        parts = line.split("|") if line.startswith("|") else [line]
        for part in parts:
            for s in SPLIT.split(part):
                if s.strip():
                    yield s.strip()


def body(path):
    """File text with version-history rows removed — they are a record, not a claim."""
    t = path.read_text()
    if path.suffix == ".md":
        return "\n".join(l for l in t.split("\n") if not HISTORY_ROW.match(l))
    if path == SPEC_HTML:
        # The generated page carries the same version-history table, rendered.
        # Cut from its heading to the end; nothing normative follows it.
        m = re.search(r"<h2[^>]*>\s*(?:<[^>]+>)*\s*18\.?\s*Version history", t, re.I)
        if m:
            t = t[:m.start()]
    return t


def live_body(path):
    """Spec text with the marked non-normative rejected block removed as well."""
    t = body(path)
    if path == SPEC and REJECTED_BLOCK[0] in t and REJECTED_BLOCK[1] in t:
        a, b = t.index(REJECTED_BLOCK[0]), t.index(REJECTED_BLOCK[1])
        t = t[:a] + t[b:]
    return t


# ── 1. model figures ──────────────────────────────────────────────────────────
def check_model():
    t = body(SPEC)
    hi, lo = M["hi"], M["lo"]
    expect = [
        (f"{hi['blanking']:,}",        "hi-res blanking-only accesses"),
        (f"{lo['blanking']:,}",        "lo-res blanking-only accesses"),
        (f"{hi['interleaved']:,}",     "hi-res interleaved accesses"),
        (f"{lo['interleaved']:,}",     "lo-res interleaved accesses"),
        (str(hi["tiles_blanking"]),    "hi-res blanking-only tiles"),
        (str(lo["tiles_blanking"]),    "lo-res blanking-only tiles"),
        (f"{hi['tiles_interleaved']:,}", "hi-res interleaved tiles"),
        (f"{lo['tiles_interleaved']:,}", "lo-res interleaved tiles"),
        (str(hi["sprite_budget"]),     "hi-res sprite byte budget"),
        (str(hi["line261_free"]),      "hi-res line-261 free ticks"),
        (str(lo["line261_free"]),      "lo-res line-261 free ticks"),
        (str(M["pin_signals"]),        "oito signal pin count"),
        (str(M["cart_contacts"]),      "cartridge contacts"),
        (str(M["pin_total_est"]),      "oito package pins used"),
        (str(M["pin_spare"]),          "oito spare pins"),
        (str(M["header_positions"]),   "probe header positions"),
        (str(M["header_signals"]),     "probe header non-power signals"),
        (M["asrc_increment_hex"],      "ASRC phase increment"),
        (f"{M['oam_full_min']:,}",     "OAM DMA full transfer floor"),
        (f"{M['oam_full_max']:,}",     "OAM DMA full transfer ceiling"),
        (str(M["oam_six_min"]),        "OAM DMA six entries floor"),
        (str(M["oam_six_max"]),        "OAM DMA six entries ceiling"),
        (f"{M['oam_full_active_min']:,}", "OAM DMA active-display floor"),
        (f"{M['oam_full_active_max']:,}", "OAM DMA active-display ceiling"),
        (str(M["oam_six_active_min"]), "OAM DMA active six-entry floor"),
        (str(M["oam_six_active_max"]), "OAM DMA active six-entry ceiling"),
        (str(M["snapshot_cpu_cycles"]), "snapshot CPU cycles"),
        (f"{M['pcm_tax_pct']:.1f}",    "PCM worst-case tax"),
    ]
    for value, what in expect:
        if value not in t:
            fails.append(f"MODEL   {what}: model says {value}, not found in spec")

    # invariants that must hold, independent of the prose
    for mode in ("hi", "lo"):
        d = M[mode]
        if not d["fits"]:
            fails.append(f"MODEL   {mode}-res display load {d['worst_line']} exceeds "
                         f"slot capacity {d['capacity']}")
        if not d["sprite_floor_ok"]:
            fails.append(f"MODEL   {mode}-res sprite budget fell to {d['sprite_budget']} bytes "
                         f"(floor {_mod.C['SPRITE_FLOOR']}) — a capability regression, not a detail")
    if M["phi2_half_margin_ns"] <= _mod.C["PHI2_MARGIN_MIN_NS"]:
        fails.append(f"MODEL   PHI2 margin {M['phi2_half_margin_ns']:.1f} ns does not clear "
                     f"the W65C02S pulse-width minima")
    if M["decode_to_rdy_ns"] <= 0:
        fails.append("MODEL   no time between address-valid and the RDY setup deadline")
    if not M["servo_stable"]:
        fails.append("MODEL   ASRC servo poles are outside the unit circle")
    if not M["asrc_trim_fits"]:
        fails.append("MODEL   ASRC trim range overflows the phase increment")
    if M["read_1cycle_possible"]:
        warns.append("MODEL   a 1-cycle VRAM read now closes — §6.5's 2-cycle rule could relax")
    if M["read_margin_ns"] <= 0:
        fails.append(f"MODEL   the 2-cycle VRAM read does not close "
                     f"(margin {M['read_margin_ns']:+.1f} ns)")
    # A deferred item must stay visibly deferred in BOTH places, or it is forgotten.
    if not M["asrc_designed"]:
        if "16.2.1" not in t or "deferred, not dropped" not in t:
            fails.append("MODEL   the ASRC filter is undesigned but the spec no longer "
                         "carries its deferral record (§16.2.1)")
        for claim in ("coefficient ROM is published", "filter passes", "ASRC is designed"):
            if claim in t:
                fails.append(f"MODEL   spec claims '{claim}' while the model says the "
                             f"filter is undesigned")
    if M["phi2_whole_ok"]:
        warns.append("MODEL   whole-tick PHI2 now meets the minima — half-tick edges may be unnecessary")

    # PCM steal placement must be the model's, not prose left over from an
    # earlier edge convention. Every row is compared, not just one.
    for r, v in M["pcm_phase"].items():
        if f"{v['setup_ns']:.1f} ns" not in t:
            fails.append(f"MODEL   PCM phase {r}: model says {v['setup_ns']:.1f} ns setup, "
                         f"not found in spec")
    span = f"{M['pcm_steal_min_tick']}–{M['pcm_steal_max_tick']} ticks after the mix tick"
    if span not in t:
        fails.append(f"MODEL   PCM steal onset: model says '{span}', not found in spec")
    if M["pcm_any_phase_defers"]:
        fails.append("MODEL   a PCM phase defers its halt but the spec's uniform rule assumes none does")


# ── 1b. structural invariants ─────────────────────────────────────────────────
# These check the SHAPE of a claim, not the presence of a string. Round ten found
# this script passing while six contradictions stood, because substring presence
# cannot see a second, incompatible rule sitting three paragraphs away.
def check_structure():
    live = live_body(SPEC)

    # (a) One PHI2 origin. Half-tick falling edges are withdrawn everywhere.
    HALF_EDGE = re.compile(r"falls at .{0,12}[+-]\s?\d*\.5|edge at .{0,12}[+-]\s?\d*\.5|"
                           r"\bm[+-]0\.5\b|\bm\+1\.5\b|\b3k\+1\.5 (?:falls|edge)")
    for line in segments(live):
        if HALF_EDGE.search(line) and not exempt(line):
            fails.append(f"STRUCT  half-tick falling edge outside history: {line.strip()[:80]}")

    # (b) Exactly ONE read request-capture rule. The withdrawn one-cycle mechanism
    #     created the request at the edge of the PRECEDING cycle.
    for phrase in ("edge of the *preceding* cycle", "edge of the preceding cycle"):
        for line in segments(live):
            if phrase in line and not exempt(line):
                fails.append(f"STRUCT  a second read-capture rule survives: {line.strip()[:80]}")

    # (c) RDY-held retirement, tested PER SENTENCE. A document-wide existence test
    #     passes as soon as ONE place qualifies retirement, so it cannot see an
    #     unconditional "the second fall retires cycle k" three sections away.
    if "retires only if" not in live.lower() and "does not retire" not in live.lower():
        fails.append("STRUCT  the spec never says a cycle held by RDY does not retire - "
                     "'the cycle retires' unconditionally leaves a stalled read undefined")
    # Narrow to the SHAPE that was wrong: "<a falling edge> retires <the cycle>".
    # A blanket ban on the word "retire" produces noise, and R12-TOOL1's other
    # half is that persistent false warnings hide real ones.
    RETIRE_EDGE = re.compile(r"(fall|edge)[^.;:]{0,60}\bretires?\b[^.;:]{0,30}cycle", re.I)
    QUALIFIED = re.compile(r"RDY|only if|does not retire|accept|held|hold edge", re.I)
    for line in segments(live):
        if RETIRE_EDGE.search(line) and not QUALIFIED.search(line) and not exempt(line):
            fails.append(f"STRUCT  an edge said to retire a cycle with no RDY condition: "
                         f"{line.strip()[:80]}")

    # (d) While the ASRC is undesigned, fixed filter dimensions may appear ONLY
    #     inside the marked rejected block. This is the invariant that would have
    #     caught 'P and T are design outputs' sitting beside ROM[ph*64 .. +63].
    if not M["asrc_designed"]:
        FIXED = (r"ph \* 64", r"hist\[63\]", r"16 × 18 → 34", r"64 phases × 64 taps",
                 r"64 × 64 / 18-bit set below")
        for pat in FIXED:
            for line in segments(live):
                if re.search(pat, line) and not exempt(line):
                    fails.append(f"STRUCT  fixed-dimension ASRC operation outside §8.4.1: "
                                 f"{line.strip()[:80]}")
        # and the invalid acceptance criterion must not return
        for line in segments(live):
            if re.search(r"(every|all).{0,30}phases?.{0,40}assembled polyphase prototype", line, re.I) \
                    and not exempt(line):
                fails.append(f"STRUCT  the withdrawn per-phase-on-the-prototype acceptance rule "
                             f"is back: {line.strip()[:80]}")
        # startup must not demand more retention than the FIFO has
        if re.search(r"accept input frames until \*\*`T \+ 16` have been received", live):
            fails.append("STRUCT  ASRC startup still buffers T+16 frames before moving any to "
                         "history — impossible for T > 16 in a 32-frame FIFO")

    # (e0) One acceptance condition. A held cycle re-presents itself, so anything
    #      that says a low-RDY cycle "completes"/"finishes" reopens double side
    #      effects — two FIFO pops, two strobes, two pointer increments.
    # The acceptance event is now OWNER-PARAMETERISED (R16-BUS4): the probe holds
    # RDY low while it owns the bus, so a CPU-only condition commits none of its
    # register accesses. Both the general form and the CPU instance must exist.
    if not re.search(r"cpu_transfer_accept\s*[=\u2261]\s*PHI2 falling edge", live):
        fails.append("STRUCT  the cpu_transfer_accept DEFINITION is missing - held-cycle "
                     "side effects become undefined")
    acc = next((m.group(0) for m in re.finditer(r"```[^`]*?```", live, re.S)
                if "owner_transfer_accept(cpu)" in m.group(0)), None)
    if acc is None:
        fails.append("STRUCT  owner_transfer_accept is never DEFINED in a block - a mention "
                     "in prose is not a definition")
    else:
        for ownr in ("cpu", "oito", "probe"):
            if f"owner_transfer_accept({ownr})" not in acc:
                fails.append(f"STRUCT  the owner_transfer_accept definition has no '{ownr}' "
                             f"case - that owner's register accesses have no commit event")
    # A low-RDY edge is a HOLD edge. Anything that asks such a cycle to finish,
    # complete, or "reach its acceptance edge" is asking for an event that
    # cpu_transfer_accept makes false by definition.
    HELD_COMPLETES = re.compile(
        r"in-flight (CPU )?cycle (finish|complete)|cycle in progress completes|"
        r"let the in-flight cycle finish|"
        r"RDY.{0,40}low.{0,60}(acceptance edge|cpu_transfer_accept)|"
        r"(acceptance edge|cpu_transfer_accept).{0,60}RDY.{0,20}low|"
        r"reach its acceptance edge|first cycle is a fresh transaction|"
        r"resumption the first cycle is a fresh", re.I)
    # "not cpu_transfer_accept" / "is NOT accepted" are the CORRECT statements.
    NEGATED = re.compile(r"\bnot\b\s*`?cpu_transfer_accept|is not accepted|"
                         r"not an acceptance edge|cannot reach its acceptance|"
                         r"never low|RDY.{0,12}high", re.I)
    for line in segments(live):
        if HELD_COMPLETES.search(line) and not NEGATED.search(line) and not exempt(line):
            fails.append(f"STRUCT  a low-RDY cycle asked to complete or accept: {line.strip()[:80]}")
    # The three edge terms must be distinguished by name, not by context.
    for term in ("sample edge", "hold edge", "acceptance edge"):
        if term not in live:
            fails.append(f"STRUCT  '{term}' is not defined — one word for all three edge "
                         f"kinds is how a bus master came to wait for an impossible event")
    # An asynchronous write pulse cannot be retracted by a later edge, so the
    # external-write strobes must be SCHEDULED around, not gated at acceptance.
    # Name the three strobes exactly. Matching only the phrase "external write
    # strobe" was too easy to evade: "every write strobe ... gated by
    # cpu_transfer_accept" reinstated the unimplementable rule and passed.
    STROBE = re.compile(r"external write strobe|every write strobe|"
                        r"RAM_W\u0304\u0112|BOOT_W\u0304\u0112|CART_W\u0304\u0112|"
                        r"RAM_WE|BOOT_WE|CART_WE", re.I)
    GATED = re.compile(r"fires? at acceptance|gated by `?cpu_transfer_accept|"
                       r"only when `?cpu_transfer_accept|at acceptance and nowhere else|"
                       r"commit(s)? at `?cpu_transfer_accept", re.I)
    EXCLUDED = re.compile(r"excluded|never gated|not gated|scheduling rule|"
                          r"explicitly excluded|rather than by acceptance", re.I)
    for line in segments(live):
        if STROBE.search(line) and GATED.search(line) and not EXCLUDED.search(line) \
                and not exempt(line):
            fails.append(f"STRUCT  an external write strobe gated at the acceptance edge - "
                         f"its PHI2-high pulse is already 54.8 ns elapsed: {line.strip()[:70]}")
    # The rule must bind EVERY RDY puller, enumerated as data. A guard shaped like
    # one sentence about oito passed a document that left the debug probe -- the
    # other open-drain puller -- free to halt an external write and repeat it.
    # Matched at LINE granularity, not segment: a table row associates a puller in
    # one cell with its obligation in the next, and segments() splits on "|" --
    # correct for scoping an exemption, wrong for reading a row as one statement.
    # Require the obligation to appear as a TABLE ROW, not anywhere on a line.
    # Matching loose prose let an explanatory paragraph -- which happens to
    # contain "probe", "external write" and the word "never" -- satisfy a guard
    # that should have needed the normative row. Found by mutation-testing this
    # guard: deleting the probe's row left it passing.
    OBLIGATION = re.compile(r"defer|waits? for the first|must not assert", re.I)
    for puller, why in RDY_PULLERS:
        rows = [s for s in live.split("\n")
                if s.lstrip().startswith("|") and puller in s
                and re.search(r"external[- ]write|RAM_W|BOOT_W|CART_W", s)]
        if not any(OBLIGATION.search(s) for s in rows):
            fails.append(f"STRUCT  no normative row binds '{puller}' to the external-write "
                         f"no-stall rule ({why})")
    # Every bus owner named in the cartridge truth table must be covered by the
    # strobe qualifier. "a valid CPU cycle" excluded the PCM and probe rows the
    # same table enables.
    if "valid CPU cycle" in live and "bus_cycle_valid" not in live:
        fails.append("STRUCT  cartridge strobes qualified by 'a valid CPU cycle' while the "
                     "truth table enables PCM and probe bus-master rows, during which no "
                     "CPU cycle is valid at all")
    # find the DEFINITION (the fenced block), not the first mention
    dfn = re.search(r"```[^`]*?bus_cycle_valid\s*\u2261.*?```", live, re.S)
    if dfn:
        blk = dfn.group(0)
        for owner in BUS_OWNERS:
            if owner.lower() not in blk.lower():
                fails.append(f"STRUCT  the bus_cycle_valid definition does not name the "
                             f"'{owner}' owner")
    elif "bus_cycle_valid" in live:
        fails.append("STRUCT  bus_cycle_valid is used but never defined")
    # R15-BUS1: ownership validity must not depend on RDY or on being held.
    # Checked against the DEFINITION BLOCK, because the offending clause sits on
    # its own line inside the fence and carries no other keyword.
    # Narrowed: "held" appears innocently in prose like "maintained by oito".
    # The defect is validity qualified on RDY or on the held/accepted state.
    if dfn and re.search(r"not held|is held\b|\bRDY\b|cpu_transfer_accept", dfn.group(0)):
        fails.append("STRUCT  the bus_cycle_valid definition is qualified on RDY or on "
                     "being held - a held external read would lose its chip select, and "
                     "a strobe cannot be retracted by a later edge anyway")
    # R15-READ1: the commit table heading is normative on its own
    if re.search(r"\|\s*Accumulated during the hold\s*\|", live):
        fails.append("STRUCT  the commit table still says 'Accumulated during the hold' - "
                     "the interval is snapshot-to-acceptance and exists with no hold at all")
    # R16-BUS1/BUS2: one meaning per symbol, one polarity per pin. Checked as
    # structure because the defect was a NAME COLLISION and a sign, neither of
    # which a behavioural model can see.
    for sym, why in (("write_phase", "the physical write pulse"),
                     ("cart_we_enable", "the ROM-space command arm")):
        if sym not in live:
            fails.append(f"STRUCT  '{sym}' ({why}) is not defined - the bare name `we` "
                         f"meant both, so either command protection was bypassed or "
                         f"system-RAM writes depended on a cartridge gate")
    if re.search(r"^\s*we\s*[=\u2261]", live, re.M):
        fails.append("STRUCT  the bare symbol `we` is defined again - it collided between "
                     "SAVE_CTRL.4 and the physical write phase")
    # Every named active-low pin must be the inversion of a predicate. Pin names
    # are read FROM the document rather than hardcoded: they carry combining
    # macrons, and a hardcoded literal that fails to match is a guard that
    # silently checks nothing -- which is how the first version of this one
    # passed a deliberately inverted equation.
    # Not anchored to line start: the pin block puts two equations per line, and
    # an anchored pattern found 4 of 9 while reporting nothing wrong.
    PIN_EQ = re.compile(r"([^\s=|`]*[\u0304\u0112\u014c][^\s=|`]*)\s*=\s*(\S)")
    # Scoped to the pin-equation fence. Applied document-wide it flagged
    # `IRQ\u0304 = NOT(...)`, which is a legitimate spelling elsewhere -- a guard
    # too broad is as useless as one too narrow, just noisier.
    # Anchored on TWO pins, because §2 has a one-line fence containing RAM_C\u0112
    # and the single-equation match there reported "only 1 pin equation found" --
    # a true statement about the wrong block.
    pin_block = next((m.group(0) for m in re.finditer(r"```[^`]*?```", live, re.S)
                      if "RAM_C\u0112" in m.group(0)
                      and "CART_W\u0304\u0112" in m.group(0)), None)
    pins = PIN_EQ.findall(pin_block) if pin_block else []
    if pin_block is None:
        fails.append("STRUCT  the active-low pin-equation block is missing - every pin "
                     "must be defined as the inversion of a positive predicate")
    if len(pins) < 6:
        fails.append(f"STRUCT  only {len(pins)} active-low pin equations found - the pin "
                     f"block should define at least 9")
    for pin, first in pins:
        if first != "!":
            fails.append(f"STRUCT  {pin} is active-low but its equation starts with "
                         f"'{first}', not '!' - it evaluates to 1 for a selected access")
    # R17-BUS4: cart_write must carry the window term, or a write to $C000-$FFFF
    # asserts FLASH_CE# and FLASH_WE# together in the read-only fixed bank.
    m_cw = re.search(r"cart_write\s*=(.*?)(?:\n\s*\n|invariant|```)", live, re.S)
    if not m_cw:
        fails.append("STRUCT  cart_write is not defined")
    elif "cart_A" not in m_cw.group(1):
        fails.append("STRUCT  cart_write has no cart_A window term - a write to $C000-$FFFF "
                     "would assert FLASH_CE# and FLASH_WE# in the read-only fixed bank")
    if not re.search(r"cart_F(_visible)?\s*->\s*!cart_write", live):
        fails.append("STRUCT  the invariant cart_F -> !cart_write is not stated")

    # R20-BUS4: BANK0-5 are mapper outputs, never bus-master lines. Assigning them
    # to the probe named pins that are not on the header; grouping them with A/RW
    # as "only while owner = oito" would undrive them for ordinary CPU reads.
    if not re.search(r"cartridge mapper outputs\*?\*? \u2014 `BANK0\u2013BANK5`", live):
        fails.append("STRUCT  BANK0-BANK5 are not identified as cartridge mapper outputs - "
                     "grouping them with the host-bus-master outputs undrives the "
                     "cartridge's high address bits for ordinary CPU accesses")
    for line in segments(live):
        if re.search(
                r"probe.{0,80}(?:"
                r"(?:may |can |shall |must )?drives?\s+(?:the\s+)?bank|"
                r"(?:may |can |shall |must )?drives?\s+address,\s*bank|"
                r"probe_drive[_a-z0-9]*bank)",
                line, re.I) and not exempt(line):
            fails.append(f"STRUCT  a probe drive term includes bank - those pins are not on "
                         f"the expansion header: {line.strip()[:70]}")
    # R20-BUS1: DBACK must be defined for the jam state, or jamming is impossible
    if not re.search(r"DEBUG jam active\D*\|\s*\*\*1\*\*", live):
        fails.append("STRUCT  DBACK is not high in the DEBUG-jam state - jam_drive = "
                     "DBACK && BE is then false throughout DEBUG and instruction jamming "
                     "is impossible")

    # R19-DEC1: the on-die stub is a data source and needs an evaluable predicate
    if not re.search(r"stub_read\s*[=\u2261]", live):
        fails.append("STRUCT  the internal boot stub has no stub_read predicate - the "
                     "at-most-one-source invariant cannot be evaluated, and jamming cannot "
                     "be shown to have every ordinary source off")
    else:
        m = re.search(r"stub_select\s*[=\u2261]([^\n]*(?:\n\s+[^\n-][^\n]*)*)", live)
        for need in ("bus_cycle_valid", "access_phase", "boot_window_address"):
            if m and need not in m.group(1):
                fails.append(f"STRUCT  stub_select omits {need} - it would drive during "
                             f"reset or outside the overlay window")
    # R18-BUS5: the overlay must mask the cartridge, not only select the boot source
    if "cart_F_visible" not in live:
        fails.append("STRUCT  the fixed cartridge window is not split - $E000-$FFFF would be "
                     "cartridge-enabled underneath the stub or boot flash")
    elif not re.search(r"cart_F_high\s*[=\u2261].*BOOT_SRC|cart_F_high\s*[=\u2261].*"
                       r"cart_overlay_selected", live):
        fails.append("STRUCT  cart_F_high has no BOOT_SRC term - the cartridge is not masked "
                     "under the boot overlay")
    # R18-BUS4 / R19-BUS1 / R21-BUS1..4: DBACK must revoke OUTBOUND enables in
    # hardware, while the fixed console->probe receive path stays enabled. The
    # receive-buffer output and outbound-value source must be different MCU nets.
    if "DBACK" in live:
        for term in ("probe_drive_addr", "probe_drive_rw", "probe_drive_data"):
            m = re.search(re.escape(term) + r"\s*=([^\n]*)", live)
            if not m:
                fails.append(f"STRUCT  {term} is not defined - the probe's outbound drive "
                             f"has no hardware authorisation term")
            elif "DBACK" not in m.group(1):
                fails.append(f"STRUCT  {term} does not contain DBACK - a frozen probe MCU "
                             f"could hold it and oito could not revoke the bus")
        for equation, need in (
                (r"/OE_ARW\s*=\s*nDBACK\s+OR\s+BE", "active-low A/RW enable equation"),
                (r"/OE_DATA\s*=\s*nDBACK\s+OR\s+\(BE\s+XOR\s+R/W\u0304\)",
                 "active-low data enable equation")):
            if not re.search(equation, live):
                fails.append(f"STRUCT  no {need} - DBACK polarity or jam-write exclusion "
                             f"is not implementable")
        if not re.search(r"receive A0\u2013A15.*74LVC245APW,118.*`/OE` tied low", live):
            fails.append("STRUCT  receive-buffer /OE is not tied enabled - passive sniffing "
                         "would disappear whenever the probe lacks ownership")
        if "No net joins two push-pull outputs" not in live:
            fails.append("STRUCT  probe topology does not forbid shared push-pull outputs - "
                         "an always-enabled receiver may be tied to an MCU output")
        if "37 input/direct GPIO + 8 data-drive GPIO + 3 latch-control GPIO = 48" not in live:
            fails.append("STRUCT  probe GPIO accounting is not the separate-net 37+8+3 map")
        if not re.search(r"DEBUG jam active.*CPU stack write.*\|\s*1\s*\|\s*1\s*\|\s*0"
                         r".*off", live):
            fails.append("STRUCT  jam stack-write state does not force the D driver off")
        if "ACQUIRE_WAIT \u2192 OWNED_GRANT" not in live:
            fails.append("STRUCT  first-transfer timer has no explicit grant transition")
        if "high-Z **at the connector**, then wait `t_TA`" not in live:
            fails.append("STRUCT  release path has no connector-high-Z plus t_TA wait before "
                         "the CPU is re-enabled")
        for required in ("the **current** oito-owned OAM transfer or PCM burst completes",
                         "pending OAM DMA",
                         "pending PCM refill"):
            if required not in live:
                fails.append(f"STRUCT  host arbitration is missing '{required}'")
        if not re.search(r"owner_transfer_accept\(oito\)\s*=\s*PHI2 falling edge "
                         r"that latches one", live):
            fails.append("STRUCT  host arbitration is missing 'owner_transfer_accept(oito)' "
                         "at a physical PCM/OAM byte edge")
    # R18-BUS3: read data must outlive the accepting edge
    if "t_PHD" not in live:
        fails.append("STRUCT  no data-hold interval past the probe's accepting edge - the "
                     "memory may stop driving before the probe samples")
    # R18-BUS1: acceptance must exclude the acquisition acknowledgement
    if "probe_transfer_pending" not in live:
        fails.append("STRUCT  probe acceptance is not qualified by a pending transfer - the "
                     "acquisition DBACK rise would fire a commit with no transfer")
    for stale in ("cycle-complete", "ext_commit"):
        for line in segments(live):
            if stale in line and not exempt(line):
                fails.append(f"STRUCT  withdrawn probe term '{stale}' is still live: "
                             f"{line.strip()[:70]}")

    # R16-BUS7: boot_win must contain BOOT_SRC, not just an address range
    if not re.search(r"boot_win\s*[=\u2261].*(BOOT_SRC|external_boot_selected)", live):
        fails.append("STRUCT  boot_win is an address range with no BOOT_SRC term - the "
                     "external flash would be selected beside the internal stub at reset "
                     "and beside the cartridge after handoff")
    # R16-BUS3: the boot-write refusal must be a term, not a table row
    if "boot_program_owner" not in live:
        fails.append("STRUCT  boot_program_owner is not defined - the probe boot-write "
                     "refusal is prose only, and BOOT_FLASH_WE may be left set")
    elif not re.search(r"boot_write\s*=.*boot_program_owner", live):
        fails.append("STRUCT  boot_write does not include boot_program_owner - a probe can "
                     "assert BOOT_W\u0304\u0112 whenever BOOT_FLASH_WE happens to be set")

    # R15-BUS2: the motherboard decode must use the owner-aware term
    for line in segments(live):
        if "cpu_memory_cycle" in line and not exempt(line):
            fails.append("STRUCT  the motherboard decode still uses the undefined, CPU-only "
                         "'cpu_memory_cycle' - OAM DMA and the probe cannot reach system RAM")
    # Which byte, not just when.
    if "commit token" not in live or "read data" not in live:
        fails.append("STRUCT  held reads promise a stable value with no snapshot or commit "
                     "token - the CPU can receive $00 and pop a byte that arrived later")
    # Every side-effect class needs a REPRESENTABLE token. A bit mask alone cannot
    # express a re-set of a bit that was already 1, and cannot express a signed
    # saturating accumulator at all.
    for need, why in (
        ("set by an event* after the snapshot",
         "post-snapshot SET mask - clearing the snapshotted mask loses a second "
         "event on a bit that was already 1"),
        ("consume-on-read accumulator",
         "commit type for the signed saturating accumulator (MOUSE_WHEEL)"),
        ("non-invertible",
         "statement that subtracting the snapshot cannot work under saturation"),
        ("read_data & clear_on_read_mask",
         "narrowed clear mask - an unmasked S would clear MOUSE_STATUS's `present` bit "
         "on every read"),
        ("clear_on_read_mask",
         "per-register clear mask table"),
    ):
        if need.replace("*", "") not in live.replace("*", ""):
            fails.append(f"STRUCT  the read snapshot has no {why}")
    # W1C: semantic, over the register inventory. The previous guard rejected the
    # exact string "clear-on-read or W1C", so the live list "clear-on-read, W1C"
    # passed -- a punctuation change was enough to evade it.
    READ_SIDE = re.compile(r"read side effects?\s*\(([^)]*)\)", re.I)
    for mlist in READ_SIDE.findall(live):
        if "W1C" in mlist:
            fails.append(f"STRUCT  W1C appears in a READ-side effect list ('{mlist[:50]}') - "
                         f"its mask comes from the CPU's write data")
    if "W1C precedence order" not in live:
        fails.append("STRUCT  no single W1C precedence order is published, so coincident "
                     "set / auto-clear / CPU-acknowledge is per-register folklore")
    for reg, why in W1C_REGISTERS:
        if not any(reg in s for s in segments(live)
                   if "W1C" in s or "precedence" in s):
            fails.append(f"STRUCT  W1C family '{reg}' ({why}) is not covered by the "
                         f"precedence rule")
    # Prog8: every origin class needs a selected mechanism, not just a required value
    for origin, cls in PROG8_ORIGINS:
        if f"%address {origin}" not in live:
            fails.append(f"STRUCT  prog8 origin {origin} ({cls}) has no selected mechanism - "
                         f"-target overrides only the RAM ceiling, so it would compile at "
                         f"the base target's pc_start")
    # (e1) The read transaction needs a suppressing term that outlives the grant.
    if "suppressed while either `pending` or `serviced` is set" not in live:
        fails.append("STRUCT  the read state machine has no suppressing term that survives "
                     "grant — clearing the request at grant re-arms the still-held access, "
                     "giving two VRAM reads and two pointer increments for one instruction")
    # (e2) Same-tick grant: the event order and the read table must agree.
    if "first arbitrated slot | **3k+3**" in live:
        fails.append("STRUCT  first arbitrated slot is 3k+3 while detection is step 2 of "
                     "3k+2 and arbitration is step 3 of the same tick — the event order "
                     "promises a same-tick grant")
    # (e3) The rejected ASRC baseline must not be called a proven failure, and the
    #      live table must not point at its formula as today's oracle.
    if not M["asrc_designed"]:
        for line in segments(live):
            # deliberately NOT exemptible: there is no wording in which asserting
            # this failure is correct while the measurement behind it is withdrawn
            if re.search(r"(failed|fails) its own .{0,20}80 dB", line):
                fails.append(f"STRUCT  the rejected baseline is called a proven failure, but "
                             f"the measurement behind it is withdrawn: {line.strip()[:70]}")
            if re.search(r"normative today is the formula|the \*\*literal formula below\*\*", line):
                fails.append(f"STRUCT  the live ASRC table names the rejected formula as the "
                             f"current oracle: {line.strip()[:70]}")
        # accumulator bound: the model owns the formula, not the prose
        if "W + 16 + ⌊log₂T⌋" not in live:
            fails.append("STRUCT  the accumulator bound is not the corrected "
                         "W + 16 + floor(log2 T) form")
        if "15 + W + ⌈log₂T⌉ bits signed" in live:
            fails.append("STRUCT  the one-bit-short accumulator bound is back")

    # (e) Cartridge board populations. The NAND was disproved in this same document.
    for line in segments(live):
        if "NAND" in line and not exempt(line):
            fails.append(f"STRUCT  NAND in a current cartridge description: {line.strip()[:80]}")

    # (f) The front-page outstanding list must equal §16.2's gate sequence exactly.
    #     Missing gates hid blockers; permitting extras duplicated the ASRC gate.
    try:
        sec = validation_section(live)
        want = validation_gate_titles(sec)
        head = live.split("**Explicitly outstanding")[1].split("## 1.")[0]
        have = [l.split("|")[1].strip() for l in head.split("\n")
                if l.startswith("|") and not l.startswith("|---") and "| Item |" not in l]
        if have != want:
            missing = [w for w in want if w not in have]
            extra = [h for h in have if h not in want]
            fails.append("STRUCT  front-page outstanding list does not exactly match §16.2 "
                         f"(missing={missing[:3]}, extra={extra[:3]}, "
                         f"front={len(have)}, gates={len(want)})")
        # R15-DOC1: the table declares ONE column. A row copied wholesale from
        # §16.2 brings its criterion and reference cells with it, and the source
        # Markdown is then structurally invalid whatever a renderer recovers.
        widths = {l.count("|") for l in head.split("\n")
                  if l.strip().startswith("|") and not l.startswith("|---")}
        if len(widths) > 1:
            fails.append(f"STRUCT  the front-page outstanding table is malformed: rows have "
                         f"{sorted(widths)} cell separators; generate every row from the "
                         f"\u00a716.2 Item cell only")
    except (IndexError, ValueError):
        fails.append("STRUCT  could not locate the front-page outstanding list or §16.2")

    # (f2) Every gate this project has CLAIMED to add must actually be in §16.2.
    try:
        sec = validation_section(live)
    except IndexError:
        sec = ""
    for title, origin in REQUIRED_GATES:
        if title not in sec:
            fails.append(f"STRUCT  \u00a716.2 has no '{title}' gate, but it is recorded as "
                         f"added ({origin}) - a disposition claiming a gate that does not "
                         f"exist is worse than the missing gate")
    if "The **6.6 ns one-cycle capture path is rejected and unused**" not in sec \
            or "is not a closure target" not in sec:
        fails.append("STRUCT  §16.2 does not exclude the rejected 6.6 ns one-cycle path "
                     "from timing sign-off")

    # (g) The §16.2 parts queues must be generated from the ledger, not typed.
    ledger_path = ROOT / "re8-parts-ledger.json"
    if ledger_path.exists():
        led = json.loads(ledger_path.read_text())["parts"]
        for field, value, label in (("suffix_evidence", "family-page", "family page"),
                                    ("suffix_evidence", "datasheet", "datasheet"),
                                    ("opn_complete", False, "incomplete OPN")):
            want = sorted(e["part"] for e in led if e.get(field) == value)
            try:
                queue = validation_section(live)
            except IndexError:
                continue
            # Membership is checked INSIDE §16.2, not anywhere in the document.
            # Every one of these parts is named elsewhere in the spec, so a
            # whole-document search could never see one fall out of the queue —
            # which is exactly the weakness that let the hand-typed "21 parts"
            # list stay wrong.
            for part in want:
                if f"`{part}`" not in queue:
                    fails.append(f"STRUCT  {part} is {label} in the ledger but is not listed "
                                 f"in the spec's §16.2 queue")
        lifecycle_closed = sum(1 for e in led if e.get("lifecycle_evidence") == "exact-page")
        lifecycle_open = len(led) - lifecycle_closed
        lifecycle_claim = (f"exact-page lifecycle evidence for {lifecycle_closed} active "
                           f"Nexperia interface parts and `none` for the other "
                           f"**{lifecycle_open}** active parts")
        if lifecycle_claim not in queue:
            fails.append("STRUCT  §16.2 lifecycle queue does not match the ledger "
                         f"({lifecycle_closed} exact-page, {lifecycle_open} open)")


# ── 1b2. review status: PERFORMED vs DISPOSITIONED ────────────────────────────
WORDS = {10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
         15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
         19: "nineteen", 20: "twenty", 21: "twenty-one", 22: "twenty-two",
         23: "twenty-three", 24: "twenty-four", 25: "twenty-five",
         26: "twenty-six", 27: "twenty-seven", 28: "twenty-eight",
         29: "twenty-nine", 30: "thirty"}
# Two adversarial reviews were resolved before v0.1 and are recorded in that
# version-history row; the first has no report file (its register is §2.A–D) and
# the second's file is no longer in the repository. Counting filenames alone was
# off by one against the document's own history.
PRE_V01_REVIEWS = 2


def review_status():
    """(performed, dispositioned).

    performed    — reports that exist, plus the two recorded before v0.1
    dispositioned — review registers written up in re8-design-history.md

    These are DIFFERENT numbers whenever a report is present but unresolved,
    which is the state this repository is in for the duration of every round.
    A checker with only one number has no truthful state at that moment.
    """
    performed = PRE_V01_REVIEWS + len(
        list(ROOT.glob("re8-sol-adversarial-review-round*.md")))
    hist = ROOT / "re8-design-history.md"
    n = 0
    if hist.exists():
        # [A-Z]+ , not [A-Z]: the register letters ran past Z at review twenty
        # ("### AA."), so a single-letter pattern silently stopped counting and
        # the COUNT check reported the documents wrong rather than itself.
        # [\w-]+ , not \w+ : the ordinal became hyphenated at review twenty-one
        # ("Twenty-first"), so \w+ silently stopped counting -- the same class of
        # boundary bug as the single-letter register prefix at review twenty.
        n = len(re.findall(r"^### [A-Z]+\. [\w-]+ adversarial review",
                           hist.read_text(), re.M))
    dispositioned = n + 1          # +1: the first review, registers §2.A–D
    return performed, dispositioned


def check_review_count():
    """Validate BOTH labelled totals, not just one.

    v0.15 published "Fourteen ... performed, fourteen dispositioned" while a
    fifteenth report sat unresolved. The checker computed both numbers and then
    validated only the dispositioned one, so the false half of a sentence it had
    the data to reject went through as a warning.
    """
    performed, dispositioned = review_status()
    if performed != dispositioned:
        warns.append(f"COUNT   {performed} performed, {dispositioned} dispositioned - "
                     f"{performed - dispositioned} report(s) outstanding (expected mid-round)")
    for label, n in (("performed", performed), ("dispositioned", dispositioned)):
        word = WORDS.get(n)
        if not word:
            warns.append(f"COUNT   {n} reviews {label}, no word form known")
            continue
        # LONGEST FIRST: "twenty" is a prefix of "twenty-one", and regex
        # alternation is first-match-wins, so unsorted alternatives made
        # every hyphenated ordinal read as its own prefix.
        _alts = "|".join(sorted(WORDS.values(), key=len, reverse=True))
        pat = re.compile(r"\b(" + _alts + r")\b[^.|]{0,60}?" + label, re.I)
        for path in (SPEC, ROOT / "README.md"):
            if not path.exists():
                continue
            for line in segments(body(path)):
                mm = pat.search(line)
                if mm and mm.group(1).lower() != word and not exempt(line):
                    fails.append(f"COUNT   {path.name}: labels '{mm.group(1)} ... {label}' "
                                 f"but {n} are {label} ('{word}')")
    # the unlabelled legacy phrasing is a claim about what is DISPOSITIONED
    word = WORDS.get(dispositioned)
    if word:
        for path in (SPEC, ROOT / "README.md"):
            if not path.exists():
                continue
            for line in segments(body(path)):
                for other in sorted(WORDS.values(), key=len, reverse=True):
                    if other != word and f"{other} adversarial review" in line \
                            and "performed" not in line and not exempt(line) \
                            and word not in line:
                        fails.append(f"COUNT   {path.name}: says '{other} adversarial "
                                     f"reviews', but {dispositioned} are dispositioned "
                                     f"('{word}')")


# ── 1b2b. the generated bus tables must be current ────────────────────────────
def check_bus_blocks():
    """A generated table cannot contradict the model -- unless it is stale.

    RE8_SKIP_BUS=1 skips the exhaustive property run (~12 s) when iterating on
    prose. The build never sets it, so what ships is always fully checked.
    """
    import os, subprocess
    if os.environ.get("RE8_SKIP_BUS"):
        warns.append("BUS     property run SKIPPED (RE8_SKIP_BUS=1)")
        return
    r = subprocess.run([sys.executable, "tools-bus-inject.py", "--check"],
                       cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode:
        for line in r.stdout.strip().split("\n"):
            if line.strip():
                fails.append(line.strip())
    r = subprocess.run([sys.executable, "tools-bus-model.py"],
                       cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode:
        fails.append("BUS     a bus property or historical regression failed - "
                     "run tools-bus-model.py")


# ── 1b3. diagram text is normative once inlined ───────────────────────────────
# tools-build-spec-html.py inlines every SVG into re8-console-spec.html, so a
# figure's text nodes ship inside the normative page. A stale "OAM DMA (~683
# cycles)" sat in one of them across ten revisions because nothing read them.
SVG_STALE = [
    (re.compile(r"683\s*cycles", re.I), "OAM DMA cost superseded since v0.3"),
    (re.compile(r"LQFP-144|LQFP-64"), "superseded oito package"),
    (re.compile(r"DVI-D|TOSLINK|DIT4192"), "superseded digital A/V"),
    (re.compile(r"\b9\s*V\b(?!GA)"), "superseded input rail"),
    (re.compile(r"20-bit accumulator"), "superseded mixer accumulator"),
    (re.compile(r"\bMCLK\b"), "the scaler has no MCLK pin"),
    # found by the round-20 diagram audit: three SVGs carried superseded facts,
    # and a figure inlined into the normative HTML ships as contract.
    (re.compile(r"11[0-9]\s*signal pins|12[0-6]\s*signal pins"),
     "stale oito signal-pin count (the model derives it)"),
    (re.compile(r"64\s*\u00d7\s*(32|64)\s*taps"),
     "ASRC tap counts are a REJECTED baseline, not a design"),
    (re.compile(r"2\s*\u00b7\s*Blitter"),
     "VRAM priority order: display > CPU/DMA > blitter, so the blitter is third"),
    (re.compile(r"free for blitter \+ CPU"),
     "superseded per-frame budget wording"),
]
TEXT_NODE = re.compile(r"<(?:text|tspan|title|desc)\b[^>]*>(.*?)</(?:text|tspan|title|desc)>",
                       re.S | re.I)


def check_diagrams():
    for svg in sorted(ROOT.glob("diagrams/*.svg")):
        for node in TEXT_NODE.findall(svg.read_text()):
            # HTML-unescape first: the SVGs mix literal characters and entities
            # (&#215; for x), so a pattern written with the literal character
            # matched one file and silently missed the other.
            import html as _html
            flat = _html.unescape(re.sub(r"<[^>]+>", "", node)).strip()
            if not flat:
                continue
            for pat, why in SVG_STALE:
                if pat.search(flat):
                    fails.append(f"DIAGRAM {svg.name}: {why} - \"{flat[:60]}\"")
    ownership = ROOT / "diagrams/bus-ownership.svg"
    if ownership.exists():
        text = ownership.read_text()
        for need in ("/OE_ARW = !DBACK OR BE",
                     "/OE_DATA = !DBACK OR (BE XOR R/W\u0304)",
                     "finish current oito transfer",
                     "PCM acceptance = cartridge-byte falling edge"):
            if need not in text:
                fails.append(f"DIAGRAM bus-ownership.svg omits current contract: {need}")


# ── 1c. generated HTML must be current ────────────────────────────────────────
def check_html_current():
    if not SPEC_HTML.exists():
        fails.append("HTML    re8-console-spec.html missing — build-publish.py generates it")
        return
    sv = VERSION_RE.search(SPEC.read_text())
    hv = VERSION_RE.search(SPEC_HTML.read_text())
    if sv and hv and sv.group(1) != hv.group(1):
        fails.append(f"HTML    re8-console-spec.html is v{hv.group(1)} but the Markdown is "
                     f"v{sv.group(1)} — regenerate it; it is the page README calls normative")


# ── 2. canonical facts ────────────────────────────────────────────────────────
# (description, required substring or None, [banned substrings])
FACTS = [
    ("oito package",        "LQFP-176",        ["LQFP-144", "LQFP-64"]),
    ("system/video SRAM",   "IS61WV1288",      ["IS61C256AL", "IS61C1024AL"]),
    ("cartridge flash",     "MX29LV800C",      ["SST39VF080"]),
    ("cartridge OE# gate",  "74LVC1G04GV",     ["74LVC1G00", "74LVC2G00"]),
    ("controller/probe buffer", "74LVC244APW,118", []),
    ("probe receive buffer", "74LVC245APW,118", []),
    ("probe address latch",  "74LVC595APW,118", []),
    ("current-limit switch", "TPS2553DBVR-1",  ["TPS2553-1DBVR", "`TPS2553`"]),
    ("audio line driver",   "NJM4556AM",       ["NJM4556AD"]),
    ("digital A/V",         "HDMI",            ["DVI-D", "TOSLINK", "DIT4192"]),
    ("scaler audio pins",   "I2S_CK",          ["MCLK/BCLK", "MCLK` to the CH7035B"]),
    ("input rail",          "12V DC",          ["9V DC"]),
    ("mixer accumulator",   "24-bit",          ["20-bit accumulator"]),
    ("fetch tier",          None,              ["Tier 2 refinement", "Tier-2 refinement"]),
    ("frame latch line",    "line 261",        ["latched at the start of line 0"]),
    ("port protection",     None,              ["polyfuse per port", "polyfuse trip"]),
    # superseded NUMBERS are as dangerous as superseded part names
    ("CPU decode budget",   "84.7 ns",         ["24.8 ns"]),
    ("OAM start phases",    None,              ["8N + 7", "8N \u00d7 4 + 7", "1,031"]),
    ("cursor latch",        None,              ["per frame at line 0"]),
    ("ASRC stopband edge",  "27,940",          ["stopband begins at the input Nyquist"]),
    ("input PTC",           None,              ["0ZCJ0150FF2E"]),
    ("ASRC design status",  "blocking deliverable", []),
    # superseded PCM arithmetic, from the withdrawn half-tick edge convention
    ("PCM phase-1 budget",  None,              ["8.3 ns", "1–4 ticks after the mix tick"]),
    ("PCM phase deferral",  None,              ["Phases 1 and 2 both defer"]),
    # cartridge board population
    ("plain cart",          None,              ["a plain cart is NOR only"]),
    # the strobe qualifier that excluded the non-CPU bus owners it also enables
    ("strobe qualifier",    "bus_cycle_valid", ["a valid CPU cycle", "valid **CPU cycle**"]),
    # OAM DMA became a RANGE when the external-write deferral landed
    ("OAM DMA cost",        None,              ["always costs `8N + 6`", "always costs 8N + 6",
                                                "unconditional `8N + 6`"]),
    # superseded prog8 build model and post-link relocation claim
    ("prog8 build passes",  None,              ["build therefore runs in two passes"]),
    ("initialised data",    None,              ["copy table the packer emits"]),
    # an open-drain pad cannot drive high
    ("BE pad drive",        None,              ["driven **high** — the CPU keeps its bus"]),
    # withdrawn read-return margin, from the later arbitration slot
    ("read return margin",  "114.7 ns",        ["68.1 ns of return margin"]),
]

# Documents that must agree on the version number.
VERSION_RE = re.compile(r"[Vv]ersion \*{0,2}(\d+\.\d+(?:\.\d+)?)")


def check_facts():
    for path in DOCS:
        if not path.exists():
            continue
        t = body(path)
        for what, need, banned in FACTS:
            for b in banned:
                for line in segments(t):
                    if b in line and not exempt(line):
                        fails.append(f"FACTS   {path.name}: superseded '{b}' ({what})"
                                     f" in: {line.strip()[:70]}")
        # the required value only has to appear in the spec itself
        if path == SPEC:
            for what, need, _ in FACTS:
                if need and need not in t:
                    fails.append(f"FACTS   canonical value for {what} ('{need}') missing from spec")


# ── 3. part ledger ────────────────────────────────────────────────────────────
def check_version():
    spec_v = VERSION_RE.search(SPEC.read_text())
    if not spec_v:
        fails.append("VERSION spec has no version string")
        return
    v = spec_v.group(1)
    for path in (ROOT / "README.md",):
        if not path.exists():
            continue
        found = {m.group(1) for m in VERSION_RE.finditer(path.read_text())}
        if found and v not in found:
            fails.append(f"VERSION {path.name} says {sorted(found)}, spec says {v}")


def check_parts():
    ledger_path = ROOT / "re8-parts-ledger.json"
    if not ledger_path.exists():
        fails.append("PARTS   re8-parts-ledger.json missing")
        return
    ledger = json.loads(ledger_path.read_text())
    known = set()
    for e in ledger["parts"] + ledger.get("removed", []):
        known.add(e["part"])
        known.update(e.get("aliases", []))
    t = body(SPEC)
    # any token that looks like an orderable part number
    pattern = re.compile(r"`([A-Z]{2,}[A-Z0-9]*[0-9][A-Z0-9./-]{2,})`")
    seen = {m.group(1) for m in pattern.finditer(t)}
    for part in sorted(seen):
        if part not in known:
            warns.append(f"PARTS   '{part}' named in spec but not in the ledger")
    GENERIC = ("/products/", "/product-category/", "/circuit-protection",
               "Pages/default.aspx", "/support/", "/en-us/products")
    for p in ledger["parts"]:
        src = p.get("source", "")
        if not src:
            fails.append(f"PARTS   {p['part']}: no source URL recorded")
        # Four orthogonal fields replace one boolean. The single flag conflated
        # exact-suffix identity with electrical verification and lifecycle, which
        # is how the §16.2 gate came to list parts whose source was already an
        # exact part-details page.
        for field in ("opn_complete", "suffix_evidence", "electrical_evidence",
                      "lifecycle_evidence"):
            if field not in p:
                fails.append(f"PARTS   {p['part']}: missing evidence field '{field}'")
        se = p.get("suffix_evidence")
        if se == "exact-page":
            # claimed exact - the URL must actually be part-specific
            nexperia_exact = bool(re.search(
                r"^https://www\.nexperia\.com/product/[^/?#]+$", src))
            if (any(g in src for g in GENERIC) or src.rstrip("/").count("/") <= 3) \
                    and not nexperia_exact:
                fails.append(f"PARTS   {p['part']}: suffix_evidence 'exact-page' but the "
                             f"source is a family/landing page ({src})")
        elif se == "family-page":
            warns.append(f"PARTS   {p['part']}: family page only - must appear in spec §16.2")
        elif se == "datasheet":
            warns.append(f"PARTS   {p['part']}: datasheet read, ordering table not matched "
                         f"to the suffix - spec §16.2")
        if p.get("opn_complete") is False:
            warns.append(f"PARTS   {p['part']}: not an orderable number - a suffix must be "
                         f"CHOSEN, not merely verified")
        if not p.get("checked"):
            fails.append(f"PARTS   {p['part']}: never verified against its datasheet")
        # Structured facts, compared as NUMBERS with units. Searching for the
        # literal "40.0" warned that a value was absent while the spec said
        # "40 ns" - a false warning on every numeric fact, which is exactly how
        # a real new warning gets lost in the noise.
        for k, v in (p.get("facts") or {}).items():
            if p.get("status") == "removed":
                continue
            if isinstance(v, (int, float)):
                unit = "ns" if k.endswith("_NS") else ""
                # accept 40, 40.0, 40.5 -> any spelling of the same magnitude
                # accept "62 ns", "62.0 ns" and list forms like "62/63 ns"
                num = re.escape(f"{v:g}") + r"(?:\.0+)?"
                pat = re.compile(r"\b" + num + (r"(?:\s*/\s*[\d.]+)*\s*" + unit
                                                if unit else r"\b"))
                found = bool(pat.search(body(SPEC)))
            else:
                found = str(v) in body(SPEC)
            if not found:
                warns.append(f"PARTS   {p['part']}: ledger fact {k}={v} not found in spec")


# ── 4. artefacts ──────────────────────────────────────────────────────────────
def check_artefacts():
    t = SPEC.read_text()
    named = set(re.findall(r"`(re8-[a-z0-9-]+-<ver>[a-z0-9./{},]*)`", t))
    present_tense = re.compile(
        r"(?<!will be )(?<!to be )(is|are) (published|checked in|generated) ", re.I)
    # A sentence stating a POLICY ("metrics are generated from the binary") is
    # not a claim that a named file already exists. Requiring the artefact token
    # on the same line removes a permanent false positive.
    POLICY = re.compile(r"no longer publishes|are generated from|must be generated|"
                        r"will be|policy|rather than hand-counted", re.I)
    for line in t.split("\n"):
        if "<ver>" in line and present_tense.search(line) and not POLICY.search(line):
            warns.append(f"ARTEF   present tense about an artefact that does not exist: {line.strip()[:90]}")
    if named and not (ROOT / "artefacts").exists():
        # expected: none of them exist yet, and the spec must say so
        if "None of them exists yet" not in t and "none of the artefacts" not in t.lower():
            fails.append("ARTEF   named artefacts do not exist and the spec does not say so")


def main():
    check_model()
    check_structure()
    check_review_count()
    check_bus_blocks()
    check_diagrams()
    check_html_current()
    check_facts()
    check_version()
    check_parts()
    check_artefacts()

    for w in warns:
        print(f"warn  {w}")
    for f in fails:
        print(f"FAIL  {f}")
    print("-" * 60)
    if fails:
        print(f"{len(fails)} failure(s), {len(warns)} warning(s)")
        return 1
    print(f"verified: model, facts, parts, artefacts — {len(warns)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

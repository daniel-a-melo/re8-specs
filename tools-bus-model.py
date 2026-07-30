#!/usr/bin/env python3
"""
re8 executable bus model — the CPU transaction contract as a state machine.

WHY THIS FILE EXISTS
--------------------
Of the 19 blockers found in adversarial review rounds 10-14, **13 were in the
bus contract** and every one of them was one of three shapes:

  * two transitions given for the same state      (R10-CPU1, R11-CPU2, R13-BUS1)
  * a rule whose consequences were not propagated (R11-DMA1, R13-DMA1, R14-DMA1)
  * a rule quantified over one agent, not all     (R14-BUS1, R14-BUS2)

Prose has no mechanism to prevent any of those. A state machine does: there is
one `step()`, so a second transition cannot exist; effects are returned by that
one function, so a consequence cannot be missed; and agents are a LIST, so a
property that loops over it cannot be true of only one of them.

WHAT IS AUTHORITATIVE
---------------------
This file is authoritative for the transition rules. The specification's timing
tables are GENERATED from it (see render_* and tools-bus-inject.py), so a
sentence in the spec cannot contradict a table any more, because the table is
not a sentence.

Numbers (tick positions, setup times) come from tools-model.py, which stays
authoritative for arithmetic. This file adds behaviour.

Run directly:  properties, historical regressions, generated tables, traces.
"""
import itertools
import pathlib
from dataclasses import dataclass, replace, field

# ── the numeric model is the single source of tick arithmetic ─────────────────
class _M:
    pass


_m = _M()
exec(compile(pathlib.Path(__file__).with_name("tools-model.py").read_text(),
             "tools-model.py", "exec"), _m.__dict__)
NUM = _m.model()
C = _m.C

# ── the agents. THIS LIST IS THE POINT. ───────────────────────────────────────
# R14-BUS1 was "the no-stall-on-external-write rule binds only oito", found by a
# human because the rule was a sentence about oito. Here the rule is a loop over
# PULLERS, so adding an agent extends every property that quantifies over it.
# THREE electrical parties sit on the open-drain line, not two. R15-BUS3 caught
# this file calling two agents "every puller" while §2 documented a third on the
# same pin. The distinction that matters is not who can pull it, but who can
# asynchronously halt a cycle they did not choose.
ELECTRICAL_PULLERS = [
    ("oito",    "VRAM stalls, OAM DMA, PCM steals"),
    ("probe",   "breakpoints, host halt, crash freeze, live access, bootstrap"),
    ("cpu_wai", "the CPU drives RDY low during WAI"),
]
# Only these can halt a cycle chosen by someone else, so only these are bound by
# the external-write scheduling rule. `cpu_wai` is exempt for a stated reason,
# not by omission: WAI is the CPU's own instruction, so the cycle it stops IS a
# WAI cycle -- it can never be an external write in progress.
HALT_REQUESTERS = ["oito", "probe"]
PULLERS = HALT_REQUESTERS            # kept: the scheduling rule quantifies over these
OWNERS = ["cpu"] + HALT_REQUESTERS   # who can own the bus

# ── what the CPU can be doing in a cycle ──────────────────────────────────────
# `ext` = emits one of RAM_WE / BOOT_WE / CART_WE, an ASYNCHRONOUS PHI2-high
# pulse that no later edge can retract. That single flag is what makes
# ext_strobe_once a non-trivial property.
CYCLES = {
    #  name             ext    side effect committed at acceptance
    # NOTE: no acceptance-gated effect. The external strobe is SCHEDULED (a PHI2-high
    # pulse), never gated, so listing an "ext_commit" under acceptance contradicted
    # the very rule the next paragraph states. R18-BUS1 caught it in the generated
    # table, where it had no definition anywhere.
    "ext_write":       (True,  None),
    "ext_read":        (False, None),
    "reg_write":       (False, "reg_commit"),
    "reg_read":        (False, None),
    "fifo_read":       (False, "fifo_pop"),
    "sticky_read":     (False, "sticky_clear"),
    "accum_read":      (False, "accum_consume"),
    "vram_read":       (False, "ptr_increment"),
    "vram_write":      (False, "ptr_increment"),
}
SIDE_EFFECT_READS = ("fifo_read", "sticky_read", "accum_read")


def emits_external_strobe(kind):
    return CYCLES[kind][0]


# ── configuration flags, so historical defects can be REINTRODUCED ────────────
# Each flag turns one repaired rule back off. `REGRESSIONS` below asserts that
# doing so breaks a named property. A property nobody has watched fail is not
# evidence of anything (README), and that applies to this file too.
@dataclass(frozen=True)
class Rules:
    # R12-BUS2 / R14-BUS1: no puller may stall a cycle emitting an external strobe
    schedule_around_ext_write: bool = True
    # ...and it binds EVERY puller, not just oito
    ext_rule_binds: tuple = tuple(PULLERS)
    # R11-CPU1: the suppressing term survives grant, not just until it
    serviced_survives_grant: bool = True
    # R11-DMA1 / R13-BUS1: nothing commits at a hold edge
    effects_only_at_accept: bool = True
    # R12-BUS1: a takeover preserves the transaction; only RES aborts
    preserve_across_takeover: bool = True
    # R13-READ1: post-snapshot sets are recorded separately from the snapshot
    post_snapshot_accumulator: bool = True
    # R10-CPU1: the request is captured at exactly one point
    capture_at_preceding_edge: bool = False
    # R15-BUS1: ownership validity must NOT depend on RDY. Turning this on is the
    # "BE high AND the cycle is not held" formulation, which drops a held read's
    # chip select and pretends to gate a strobe that has already fired.
    valid_requires_not_held: bool = False
    # R15-BUS2: the decode must admit every owner, not only the CPU
    decode_owners: tuple = tuple(OWNERS)
    # R16-BUS5: ownership is a ONE-HOT state, not an expression over wired-AND BE.
    # Turning this off models "BE low means whoever asked may drive", which lets
    # oito and the probe enable their drivers at the same time.
    one_hot_ownership: bool = True
    # R16-BUS4: the acceptance event is parameterised by owner. Turning this off
    # models a CPU-only condition, which commits nothing while the probe -- which
    # holds RDY low for its whole interval -- owns the bus.
    accept_is_owner_parameterised: bool = True


DEFAULT = Rules()


# ── state ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class S:
    tick: int = 0                 # 0,1,2 within the CPU cycle
    kind: str = "reg_read"        # what the CPU is presenting
    live: bool = False            # a CPU transaction is in progress
    pending: bool = False         # VRAM request awaiting grant
    serviced: bool = False        # granted; data + token latched
    snapped: bool = False         # read snapshot taken
    rdy_low: frozenset = frozenset()   # which agents pull RDY
    owner: str = "cpu"
    # producer bookkeeping, for no_event_lost
    events_in: int = 0            # events that have arrived
    events_out: int = 0           # events delivered to the CPU
    events_queued: int = 0        # events still available to a later read
    snapshot_events: int = 0      # events the snapshot represents
    # per-TRANSACTION counters. Properties are invariants over these, so the
    # exhaustive check is a proof over reachable states rather than a sample of
    # traces -- and "once per transaction" is expressible at all, which it is
    # not when a trace spans several transactions.
    strobes: int = 0              # external strobes this transaction
    grants: int = 0               # VRAM grants this transaction
    commits: int = 0              # side-effect commits this transaction
    took_over: bool = False       # a takeover has happened since reset
    # R15-BUS1/BUS2: the DECODE, which the first version of this model did not
    # represent at all -- which is why both round-fifteen blockers landed inside
    # the bus contract and outside the model.
    select: bool = False          # the external device's chip select is asserted
    select_dropped_while_live: bool = False   # ...and was deasserted mid-transaction
    # R16-BUS4/BUS5: ownership and probe-side commits, which the previous version
    # of this model also did not represent -- the same lesson as R15, one layer on.
    drivers: frozenset = frozenset()   # who currently has address/data drivers on
    probe_pending: bool = False        # a probe-owned register access is outstanding
    probe_commits: int = 0             # ...and how many times it committed


@dataclass
class Inputs:
    """One tick of environment."""
    want_halt: frozenset = frozenset()   # agents wishing to halt the CPU
    grant: bool = False                  # arbitration grants this tick
    event: bool = False                  # a producer event arrives this tick
    reset: bool = False


def step(s: S, i: Inputs, R: Rules = DEFAULT):
    """The ONLY transition rule. Returns (next_state, effects).

    Effects are the things that are observable outside the CPU: commits,
    strobes, pops, clears, increments, retirement.
    """
    fx = set()

    if i.reset:
        return S(kind=s.kind), {"abort"}

    # ── producer events arrive on any tick ────────────────────────────────────
    events_in = s.events_in + (1 if i.event else 0)
    queued = s.events_queued + (1 if i.event else 0)
    s = replace(s, events_in=events_in, events_queued=queued)

    # ── step 0 of a cycle: the falling edge ───────────────────────────────────
    if s.tick == 0 and s.owner == "cpu":
        if not s.rdy_low:
            # ACCEPTANCE EDGE
            if s.live:
                fx.add("accept")
                eff = CYCLES[s.kind][1]
                if eff:
                    fx.add(eff)
                    s = replace(s, commits=s.commits + 1)
                delivered = s.events_out
                q = s.events_queued
                if s.kind in SIDE_EFFECT_READS:
                    # DELIVERED and CONSUMED are different quantities, and
                    # conflating them is exactly R13-READ1. The CPU always
                    # receives the SNAPSHOT -- that is what "the same value
                    # across held edges" means. What the commit REMOVES from the
                    # producer depends on the rule: the snapshot (correct) or the
                    # live state (the defect, which erases every event that
                    # arrived after the snapshot without the CPU ever seeing it).
                    consumed = s.snapshot_events if R.post_snapshot_accumulator \
                        else s.events_queued
                    consumed = min(consumed, s.events_queued)
                    delivered = s.events_out + min(s.snapshot_events, s.events_queued)
                    q = s.events_queued - consumed
                s = replace(s, live=False, pending=False, serviced=False,
                            snapped=False, snapshot_events=0,
                            events_out=delivered, events_queued=q)
            # a new cycle begins on this same edge: counters reset with it
            s = replace(s, live=True, strobes=0, grants=0, commits=0)
        else:
            # HOLD EDGE — the cycle is re-presented, nothing commits
            if not R.effects_only_at_accept:
                # the defect R11-DMA1/R13-BUS1 described: acting on every edge
                eff = CYCLES[s.kind][1]
                if eff:
                    fx.add(eff)
                    s = replace(s, commits=s.commits + 1)
            # R10-CPU1's withdrawn rule: capture at the edge that retires the
            # PRECEDING cycle, which re-arms a held transaction every edge.
            if R.capture_at_preceding_edge and s.kind.startswith("vram"):
                s = replace(s, pending=True, serviced=False)

    # ── the decode: is this owner's cycle valid, and is the select asserted? ──
    # bus_cycle_valid depends on OWNERSHIP and on debug suppression -- never on
    # RDY. The mutation valid_requires_not_held reintroduces the round-fifteen
    # formulation so the properties below can be shown to catch it.
    owner_ok = s.owner in R.decode_owners
    valid = owner_ok and not (R.valid_requires_not_held and bool(s.rdy_low))
    was_selected = s.select
    s = replace(s, select=valid and s.live)
    if was_selected and not s.select and s.live:
        s = replace(s, select_dropped_while_live=True)

    # ── PHI2 high: the asynchronous external strobe, if any ───────────────────
    # It fires on EVERY presentation of the cycle. That is physics, not policy:
    # 54.8 ns of a 69.8 ns pulse has reached the memory before RDY need even be
    # valid. Preventing a second one is a SCHEDULING duty, checked by
    # ext_strobe_once.
    # NOTE the absence of `and valid` here, and it is deliberate. The pulse is a
    # physical consequence of presenting the cycle; qualifying it on a
    # falling-edge-derived term would model the very late gating §6.5 proves
    # impossible, and would make ext_strobe_once pass for the wrong reason.
    if s.tick == 1 and s.owner == "cpu" and s.live and emits_external_strobe(s.kind):
        fx.add("ext_strobe")
        s = replace(s, strobes=min(s.strobes + 1, 3))

    # ── tick 2: request capture, and the RDY decision ─────────────────────────
    if s.tick == 2 and s.owner == "cpu":
        # VRAM request capture: once. Detection is suppressed while EITHER
        # pending or serviced is set (R11-CPU1).
        if s.kind.startswith("vram"):
            suppress = s.pending or (s.serviced if R.serviced_survives_grant else False)
            if not suppress:
                s = replace(s, pending=True)

        # who may pull RDY for the edge at the next tick 0
        pulls = set()
        for a in i.want_halt:
            if emits_external_strobe(s.kind) and R.schedule_around_ext_write \
                    and a in R.ext_rule_binds:
                continue          # defer: this cycle would pulse a strobe
            pulls.add(a)
        # a VRAM read holds itself until its data returns
        if s.kind == "vram_read" and (s.pending or s.serviced) and not s.snapped:
            pulls.add("oito")
        s = replace(s, rdy_low=frozenset(pulls))

    # ── arbitration grant (any tick) ──────────────────────────────────────────
    if i.grant and s.pending:
        s = replace(s, pending=False, serviced=True, grants=min(s.grants + 1, 3))
        fx.add("vram_grant")
        if not s.snapped:
            s = replace(s, snapped=True, snapshot_events=s.events_queued)

    # ── read snapshot for register reads: at decode completion, tick 2 ────────
    if s.tick == 2 and s.live and s.kind in SIDE_EFFECT_READS and not s.snapped:
        s = replace(s, snapped=True, snapshot_events=s.events_queued)

    # ── probe-owned register access: does it have an acceptance event? ────────
    # The probe holds RDY low the whole time it owns the bus, so a CPU-only
    # condition never fires. With the owner-parameterised form it commits once per
    # probe-driven cycle, independent of RDY.
    if s.owner == "probe":
        if not s.probe_pending:
            s = replace(s, probe_pending=True)
        elif s.tick == 0:
            if R.accept_is_owner_parameterised:
                fx.add("probe_accept")
                s = replace(s, probe_pending=False,
                            probe_commits=min(s.probe_commits + 1, 2))
            # else: nothing fires -- the access is simply lost, which is the defect

    # ── driver enables: one-hot, or "whoever saw BE low" ──────────────────────
    if R.one_hot_ownership:
        drivers = frozenset([s.owner]) if s.owner != "cpu" else frozenset()
    else:
        # the defect: BE low is a wired-AND request, so every requester enables
        drivers = frozenset(s.rdy_low) if s.rdy_low else frozenset()
    s = replace(s, drivers=drivers)

    # ── bus takeover ──────────────────────────────────────────────────────────
    if s.tick == 0 and s.rdy_low and s.owner == "cpu":
        newowner = sorted(s.rdy_low)[0]
        if R.preserve_across_takeover:
            s = replace(s, owner=newowner, took_over=True)
        else:
            # the defect: treat resumption as a fresh transaction
            s = replace(s, owner=newowner, took_over=True, live=False,
                        pending=False, serviced=False, snapped=False,
                        snapshot_events=0)
    elif s.owner != "cpu" and not i.want_halt:
        s = replace(s, owner="cpu", rdy_low=frozenset())

    return replace(s, tick=(s.tick + 1) % 3), fx


# ── exhaustive exploration of the reachable state space ───────────────────────
# BFS, not sampled traces. The state space is small enough to enumerate
# completely, so a property that holds here holds for EVERY input sequence, not
# for the ones a test happened to try. Counters are capped so the space stays
# finite; hitting a cap IS the violation, so nothing is lost by capping.
EVENT_CAP = 3   # 2 events must be observable below the cap for R13-READ1


def inputs_alphabet():
    for halt in (frozenset(), frozenset(["oito"]), frozenset(["probe"]),
                 frozenset(["oito", "probe"])):
        for grant in (False, True):
            for event in (False, True):
                yield Inputs(want_halt=halt, grant=grant, event=event)


def normalise(s):
    """Cap every counter so the reachable set is finite.

    The per-transaction counters cap at 2: anything above 1 is already a
    violation, so counting higher adds states without adding information. A
    mutation that increments one unboundedly would otherwise exhaust memory
    instead of reporting a counterexample -- which is how the first run of this
    file died.
    """
    return replace(s,
                   events_in=min(s.events_in, EVENT_CAP),
                   events_out=min(s.events_out, EVENT_CAP),
                   events_queued=min(s.events_queued, EVENT_CAP),
                   snapshot_events=min(s.snapshot_events, EVENT_CAP),
                   strobes=min(s.strobes, 2),
                   grants=min(s.grants, 2),
                   commits=min(s.commits, 2))


def explore(kind, R=DEFAULT, on_edge=None):
    """Visit every reachable state, calling on_edge for each transition.

    Edges are consumed as they are produced rather than collected: the set of
    transitions is far larger than the set of states, and materialising it is
    what makes an exhaustive check look expensive when it is not.
    """
    start = normalise(S(kind=kind, live=True))
    seen = {start: []}
    queue = [start]
    while queue:
        s = queue.pop()
        for i in inputs_alphabet():
            if s.events_in >= EVENT_CAP and i.event:
                continue
            nxt, fx = step(s, i, R)
            nxt = normalise(nxt)
            if on_edge is not None:
                on_edge(s, i, nxt, fx, seen)
            if nxt not in seen:
                seen[nxt] = seen[s] + [i]
                queue.append(nxt)
    return seen


# ── properties, as INVARIANTS over reachable states and transitions ───────────
def inv_one_strobe(s, i, nxt, fx):
    """R12-BUS2 / R14-BUS1 — one external pulse per transaction, every puller."""
    return nxt.strobes <= 1


def inv_one_grant(s, i, nxt, fx):
    """R10-CPU1 / R11-CPU1 — one grant, one pointer increment, per access."""
    return nxt.grants <= 1


def inv_one_commit(s, i, nxt, fx):
    """R11-CPU1 — a side effect commits once per transaction."""
    return nxt.commits <= 1


def inv_no_effect_at_hold(s, i, nxt, fx):
    """R11-DMA1 / R13-BUS1 — a hold edge commits nothing."""
    if s.tick == 0 and s.owner == "cpu" and s.rdy_low:
        return not (fx - {"ext_strobe", "vram_grant"})
    return True


def inv_txn_survives_takeover(s, i, nxt, fx):
    """R12-BUS1 — a takeover holds the CPU, it does not delete its access."""
    if s.live and nxt.owner != "cpu":
        return nxt.live
    return True


def inv_no_event_lost(s, i, nxt, fx):
    """R13-READ1 — an event is delivered or still queued; never erased."""
    if nxt.events_in >= EVENT_CAP:
        return True                    # capped; not a real observation
    return nxt.events_out + nxt.events_queued == nxt.events_in


def inv_read_select_held(s, i, nxt, fx):
    """R15-BUS1 — a held external read keeps its chip select.

    §6.5 promises a held cycle re-presents address and direction unchanged and
    re-drives read data. Dropping the select mid-transaction breaks that, and
    leaves a 70 ns cartridge or FRAM as little as 15 ns after RDY release.
    """
    return not nxt.select_dropped_while_live


def inv_decode_owner_complete(s, i, nxt, fx):
    """R15-BUS2 — every bus owner can reach the memory it is documented to use.

    OAM DMA reads its source block from system RAM and the probe reads and
    writes it, both with BE low. A CPU-only decode term deasserts the select in
    exactly those cases.
    """
    if nxt.live and nxt.owner in OWNERS and nxt.tick != 0:
        return nxt.select or nxt.owner not in OWNERS
    return True


def inv_one_hot_ownership(s, i, nxt, fx):
    """R16-BUS5 — at most one master may have its drivers enabled.

    `BE` is open-drain and wired-AND: a low level says SOMEONE asked the CPU to
    release the bus. It does not say who may drive it, so keying driver enables on
    it lets a probe live-memory request and a PCM steal both turn theirs on.
    """
    return len(nxt.drivers) <= 1


def inv_probe_can_commit(s, i, nxt, fx):
    """R16-BUS4 — a probe-owned register access must have an acceptance event.

    §13 has the probe driving the VRAM and palette ports and arming
    CART_WE_ENABLE, while holding RDY low throughout. A CPU-only acceptance
    condition commits none of it.
    """
    # a probe access that became outstanding must eventually commit; here,
    # expressed as: we never reach a state where the probe owned the bus across a
    # falling edge and nothing ever committed.
    if s.owner == "probe" and s.tick == 0 and s.probe_pending:
        return "probe_accept" in fx
    return True


PROPERTIES = [
    ("one_hot_ownership", inv_one_hot_ownership,
     "R16-BUS5 — two masters both saw wired-AND `BE` low and enabled their "
     "address/data drivers into each other"),
    ("probe_can_commit", inv_probe_can_commit,
     "R16-BUS4 — a probe-owned register or port access never commits, because the "
     "acceptance condition requires `RDY` high and the probe holds it low"),
    ("read_select_held", inv_read_select_held,
     "R15-BUS1 — a held external read lost its chip select, so the device stops "
     "driving the value the CPU is about to sample"),
    ("decode_owner_complete", inv_decode_owner_complete,
     "R15-BUS2 — a bus owner cannot reach the memory it is documented to use, "
     "because the decode term names only the CPU"),
    ("ext_strobe_once", inv_one_strobe,
     "R12-BUS2 / R14-BUS1 — an asynchronous PHI2-high pulse cannot be retracted, "
     "so a held external write is pulsed twice into FRAM/NOR/flash"),
    ("one_grant_per_txn", inv_one_grant,
     "R10-CPU1 / R11-CPU1 — two VRAM reads and two pointer increments for one "
     "CPU instruction"),
    ("one_commit_per_txn", inv_one_commit,
     "R11-CPU1 — a held read pops two FIFO bytes for one access"),
    ("no_effect_at_hold_edge", inv_no_effect_at_hold,
     "R11-DMA1 / R13-BUS1 — a held cycle re-presents itself; committing on "
     "every falling edge acts more than once per access"),
    ("txn_survives_takeover", inv_txn_survives_takeover,
     "R12-BUS1 — a takeover holds the CPU; it does not delete the access the "
     "CPU is in the middle of"),
    ("no_event_lost", inv_no_event_lost,
     "R13-READ1 — a second event on an already-set sticky bit is erased by a "
     "clear the CPU never observed"),
]


class _Found(Exception):
    pass


def check(R=DEFAULT, kinds=None, stop_on=None):
    """Exhaustive. Returns {property: (kind, witness) or None} and a state count.

    `stop_on` aborts as soon as that property is violated. A regression only needs
    ONE counterexample, and the full sweep is 10x more work than finding it -- the
    difference between a 5 s build step and a 50 s one.
    """
    kinds = kinds or list(CYCLES)
    bad = {name: None for name, _, _ in PROPERTIES}
    total = 0
    try:
        for kind in kinds:
            def on_edge(s, i, nxt, fx, seen, _k=kind):
                for name, fn, _ in PROPERTIES:
                    if bad[name] is None and not fn(s, i, nxt, fx):
                        bad[name] = (_k, seen.get(s, []) + [i])
                        if stop_on == name:
                            raise _Found
            total += len(explore(kind, R, on_edge))
    except _Found:
        pass
    return bad, total


# ── historical regressions ────────────────────────────────────────────────────
# Every blocker this file exists to prevent, reintroduced as a rule change, with
# the property that must catch it. This is the model's own mutation test: a
# property nobody has watched fail is not evidence of anything, and that applies
# here more than anywhere, because these properties are the whole argument for
# replacing prose.
#
# If a mutation stops breaking its property, the property has been weakened and
# the regression fails LOUDLY — which is the point. It is not enough that the
# current model is correct; the checks must be able to tell that it is.
REGRESSIONS = [
    ("R10-CPU1", "request captured at the edge that retires the preceding cycle",
     dict(capture_at_preceding_edge=True), "one_grant_per_txn"),
    ("R11-CPU1", "the suppressing term cleared at grant instead of at acceptance",
     dict(serviced_survives_grant=False), "one_grant_per_txn"),
    ("R11-DMA1", "side effects fire at every falling edge, held or not",
     dict(effects_only_at_accept=False), "no_effect_at_hold_edge"),
    ("R12-BUS1", "a takeover treated as ending the CPU transaction",
     dict(preserve_across_takeover=False), "txn_survives_takeover"),
    ("R12-BUS2", "external writes stalled like any other cycle",
     dict(schedule_around_ext_write=False), "ext_strobe_once"),
    ("R13-READ1", "the commit uses live state instead of the snapshot",
     dict(post_snapshot_accumulator=False), "no_event_lost"),
    ("R14-BUS1", "the external-write rule bound to oito alone, leaving the probe free",
     dict(ext_rule_binds=("oito",)), "ext_strobe_once"),
    ("R15-BUS1", "bus_cycle_valid made ownership depend on RDY, dropping a held "
                 "read's chip select",
     dict(valid_requires_not_held=True), "read_select_held"),
    ("R15-BUS2", "the decode term named only the CPU, so OAM DMA and the probe "
                 "could not reach system RAM",
     dict(decode_owners=("cpu",)), "decode_owner_complete"),
    ("R16-BUS4", "a CPU-only acceptance condition, so probe-owned register and "
                 "port accesses never commit",
     dict(accept_is_owner_parameterised=False), "probe_can_commit"),
    ("R16-BUS5", "driver enables keyed on wired-AND BE instead of a one-hot owner",
     dict(one_hot_ownership=False), "one_hot_ownership"),
]

# A regression of a different kind: not "does the property catch the defect", but
# "does the property catch it for the RIGHT REASON". R15-BUS1's deepest point is
# that suppressing a strobe on a held cycle is not a fix — the pulse has already
# fired. So: remove the scheduling rule AND add the validity gating. If
# ext_strobe_once still fails, uniqueness genuinely comes from scheduling. If it
# passes, the model is being saved by late gating, which hardware cannot do.
MECHANISM_TESTS = [
    ("R15-BUS1-mechanism",
     "strobe uniqueness must come from SCHEDULING, not from marking a held cycle "
     "invalid — a physical pulse cannot be retracted by a later edge",
     dict(schedule_around_ext_write=False, valid_requires_not_held=True),
     "ext_strobe_once", True),      # True = the property must STILL fail
]


def mechanism_tests():
    out = []
    for tid, why, mutation, prop, must_fail in MECHANISM_TESTS:
        bad, _ = check(replace(DEFAULT, **mutation), stop_on=prop)
        failed = bad[prop] is not None
        out.append((tid, why, prop, failed == must_fail))
    return out


def regressions():
    """Returns [(id, description, property, caught?)]."""
    out = []
    for rid, why, mutation, expect in REGRESSIONS:
        bad, _ = check(replace(DEFAULT, **mutation), stop_on=expect)
        out.append((rid, why, expect, bad[expect] is not None))
    return out


# ── generated specification tables ────────────────────────────────────────────
# These are what §6.5 and §8.5 publish. They are OUTPUT, injected between
# markers by tools-bus-inject.py, so a sentence elsewhere in the document can no
# longer contradict them: the table is not a sentence.
def render_read_timeline():
    tick = NUM["tick_ns"]
    av = NUM["addr_valid_tick"]
    slot = NUM["capture_tick"]
    rows = [
        ("PHI2 falls, cycle *k* begins", "3k+0.00", "**sample edge**"),
        ("CPU address and `R/W̄` valid", f"3k+{av:.2f}", f"`t_ADS` = {C['T_ADS_NS']:.0f} ns from that edge"),
        ("oito's decoded selects valid", "≈3k+1.3", "input pad, `$4044` decode, synchroniser"),
        ("`pending` sets (step 2)", f"3k+{slot}", f"{(slot - av) * tick:.1f} ns after address validity"),
        ("**grant** (step 3, same tick)", f"3k+{slot}", "`pending` clears, `serviced` sets, read data and commit token latched"),
        ("`RDY` driven low", f"3k+{NUM['rdy_by_tick']:.2f}", f"`t_PCS` = {C['T_PCS_NS']:.0f} ns before the edge at 3k+3"),
        ("VRAM data at oito", f"3k+{slot + 1:.2f}", f"one master tick, {C['SRAM_NS']:.0f} ns SRAM"),
        ("…at the CPU data pins", f"3k+{slot + 1 + C['PAD_MUX_NS'] / tick:.2f}", f"+{C['PAD_MUX_NS']:.0f} ns pad, mux and board"),
        ("edge at 3k+3", "3k+3.00", "**hold edge** — `RDY` low, cycle held and re-presented, **nothing commits**"),
        ("data must be valid", f"3k+{6 - C['T_DSR_NS'] / tick:.2f}", f"`t_DSR` = {C['T_DSR_NS']:.0f} ns before the retiring edge"),
        ("`RDY` released", f"3k+{6 - C['T_PCS_NS'] / tick:.2f}", f"high `t_PCS` before the edge at 3k+6"),
        ("edge at 3k+6", "3k+6.00", "**acceptance edge** — CPU samples, pointer increments once, cycle retires, `serviced` clears"),
    ]
    out = ["| Event | Tick | Note |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    out.append("")
    out.append(f"Return margin **{NUM['read_margin_ns']:+.1f} ns**; the read takes "
               f"**{NUM['read_cycles']} CPU cycles** and the binding constraint is the "
               f"*request* path, not the return path.")
    return "\n".join(out)


def render_effect_matrix():
    """Which effects fire at which edge, BY OWNER.

    R17-BUS7: the previous single table said a falling edge with RDY low fires
    "nothing" -- but probe acceptance IS a falling edge with RDY low, so the table
    contradicted the owner-parameterised rule a few paragraphs above it. Two facts
    are simultaneously true at such an edge and have to be stated separately: the
    CPU does not retire, AND the current owner may accept.
    """
    fx = ", ".join(sorted({e for _, e in CYCLES.values() if e}))
    return "\n".join([
        "| Owner | Edge | Condition | What fires |", "|---|---|---|---|",
        "| any | **sample edge** | every PHI2 falling edge | the current owner samples "
        "read data; oito samples address, `R/W\u0304` and write data |",
        "| **cpu** | **hold edge** | `RDY` **low** | **the CPU does not retire** and no "
        "CPU-owned effect commits. The cycle is re-presented with address and direction "
        "unchanged |",
        f"| **cpu** | **acceptance edge** | `RDY` **high** | "
        f"`owner_transfer_accept(cpu)`: {fx}, and CPU retirement |",
        f"| **probe** | **acceptance edge** | the **falling edge of the PHI2 cycle oito "
        f"generates** for a request, while `owner = probe` **and `probe_transfer_pending`**. "
        f"`RDY` is low throughout, and that is **not** a hold for the probe. *The "
        f"acquisition `DBACK` rise is excluded \u2014 no transfer is pending then* | "
        f"`owner_transfer_accept(probe)`: {fx}. **No CPU retirement** \u2014 the CPU stays "
        f"halted with its pins released |",
        "| **oito** | **acceptance edge** | PCM: the PHI2 falling edge that latches one "
        "cartridge byte. OAM: the PHI2 falling edge that latches one system-RAM source "
        "byte | `owner_transfer_accept(oito)`: one host byte accepted. The later OAM "
        "VRAM write is a private-bus grant, not a host acceptance; no CPU-visible "
        "commit |",
        "| any | *(PHI2 high, any presentation)* | the cycle emits an external strobe | "
        "`RAM_W\u0304\u0112` / `BOOT_W\u0304\u0112` / `CART_W\u0304\u0112` \u2014 "
        "**asynchronous, not gated**, which is why no halt requester may hold such a "
        "cycle |",
    ])


def render_pcm_phases():
    out = ["| `m mod 3` | Cycle in progress at step 8 of *m* | Next falling edge | "
           "Ticks away | Setup after `t_PCS` = 15 ns |", "|---|---|---|---:|---:|"]
    began = {0: "began at *m* (edge was step 0 of *m*)", 1: "began at *m*−1",
             2: "began at *m*−2"}
    for r, v in NUM["pcm_phase"].items():
        out.append(f"| **{r}** | {began[r]} | *m*+{v['edge_delta_ticks']} | "
                   f"{v['edge_delta_ticks']} | **{v['setup_ns']:.1f} ns** |")
    return "\n".join(out)


def render_pullers():
    """All THREE electrical parties, with the exemption stated rather than implied."""
    how = {
        "oito": "**bound.** It has `R/W̄` and its decode by ≈3k+1.3, well before the "
                "3k+2.68 deadline, so it sees that cycle *k* is an external write and "
                "evaluates cycle *k*+1 instead",
        "probe": "**bound.** It must sample `R/W̄` and the address window and **defer "
                 "the halt to the first non-external-write cycle**, then assert `RDY` "
                 "in time for that cycle's falling edge (§13)",
        "cpu_wai": "**exempt, for a stated reason.** `WAI` is the CPU's *own* "
                   "instruction, so the cycle it stops is a `WAI` cycle and can never "
                   "be an external write in progress. The CPU does not asynchronously "
                   "halt a cycle it did not choose, which is what the rule guards "
                   "against",
    }
    out = ["| Electrical party on `RDY` | Pulls low for | External-write rule |",
           "|---|---|---|"]
    for name, why in ELECTRICAL_PULLERS:
        out.append(f"| **{name}** | {why} | {how[name]} |")
    out.append("")
    out.append(f"**{len(ELECTRICAL_PULLERS)} parties share the pin; "
               f"{len(HALT_REQUESTERS)} of them are *external halt requesters* and are "
               f"bound by the scheduling rule.** Those are different sets, and calling "
               f"the smaller one \"every puller\" is what an earlier revision did while "
               f"§2 documented a third party on the same line.")
    return "\n".join(out)


def render_ownership_svg():
    """The §6.9 ownership diagram, GENERATED so it cannot drift.

    Round 20's audit found three SVGs carrying superseded facts, one of them a
    pin count 11 short and one asserting ASRC tap counts that are a rejected
    baseline. A figure inlined into the normative HTML is contract; this one is
    output.
    """
    W, H = 900, 520
    P = []
    P.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
             f'font-family="ui-sans-serif,system-ui,sans-serif">')
    P.append('<style>'
             '.t{fill:var(--fg,#111)} .m{fill:var(--muted,#555);font-size:11px}'
             '.b{fill:none;stroke:var(--fg,#111);stroke-width:1.4}'
             '.d{fill:none;stroke:var(--muted,#777);stroke-width:1;'
             'stroke-dasharray:4 3} .h{font-size:13px;font-weight:600}'
             '.k{font-size:11px;font-family:ui-monospace,monospace}'
             '</style>')
    P.append(f'<text class="t h" x="14" y="24">re8 \u2014 BUS OWNERSHIP '
             f'(generated from tools-bus-model.py)</text>')
    P.append('<text class="m" x="14" y="42">One-hot host-bus owner. '
             'The private VRAM bus has a single master and is arbitrated by slot '
             'priority, not ownership.</text>')

    # one-hot owner states
    boxes = [("none", 30, "RES\u0304 asserted \u00b7 no selects"),
             ("cpu", 245, "normal execution"),
             ("oito", 460, "PCM refill \u00b7 OAM DMA"),
             ("probe", 675, "live memory \u00b7 bootstrap")]
    for name, x, sub in boxes:
        P.append(f'<rect class="b" x="{x}" y="62" width="195" height="52" rx="6"/>')
        P.append(f'<text class="t k" x="{x+12}" y="84">owner = {name}</text>')
        P.append(f'<text class="m" x="{x+12}" y="102">{sub}</text>')
    for x in (225, 440, 655):
        P.append(f'<path class="d" d="M{x} 88 h20"/>')

    # what each owner may drive
    P.append('<text class="t h" x="14" y="150">What each owner drives</text>')
    rows = [
        ("cpu",   "A0\u2013A15, D0\u2013D7, R/W\u0304"),
        ("oito",  "A0\u2013A15, D0\u2013D7, R/W\u0304 (BE low)"),
        ("probe", "A0\u2013A15 + R/W\u0304 from storage latches; D0\u2013D7 on writes"),
        ("oito, ALWAYS", "BANK0\u2013BANK5 \u2014 mapper outputs, never released"),
    ]
    y = 172
    for who, what in rows:
        P.append(f'<text class="t k" x="24" y="{y}">{who}</text>')
        P.append(f'<text class="m" x="185" y="{y}">{what}</text>')
        y += 20

    # the grant lifecycle
    P.append('<text class="t h" x="14" y="278">DBACK \u2014 outbound hardware '
             'grant, in every state</text>')
    grant = [("NORMAL", "0", "receive only"),
             ("DEBUG entry", "0", "receive only"),
             ("DEBUG jam/read", "1", "D0\u2013D7 injected \u00b7 BE HIGH"),
             ("DEBUG jam/write", "1", "D driver OFF \u00b7 capture stack byte"),
             ("ACQUIRE_WAIT", "0", "owner = none during turnaround"),
             ("OWNED", "1", "BE low"),
             ("timeout / RES\u0304", "0", "revoked before BE is released")]
    y = 300
    for st, v, note in grant:
        P.append(f'<text class="m" x="24" y="{y}">{st}</text>')
        P.append(f'<text class="t k" x="190" y="{y}">DBACK = {v}</text>')
        P.append(f'<text class="m" x="300" y="{y}">{note}</text>')
        y += 19

    P.append(f'<text class="m" x="480" y="300">Receive-buffer outputs and drive-buffer '
             f'inputs use DIFFERENT MCU pins.</text>')
    P.append(f'<text class="m" x="480" y="319">/OE_ARW = !DBACK OR BE</text>')
    P.append(f'<text class="m" x="480" y="338">/OE_DATA = !DBACK OR '
             f'(BE XOR R/W\u0304)</text>')
    P.append(f'<text class="m" x="480" y="357">Every /OE has a passive pull-up; '
             f'DBACK revocation is hardware-effective.</text>')
    P.append(f'<text class="m" x="480" y="376">t_TA \u2265 1 PHI2 cycle = '
             f'{NUM["cpu_cycle_ns"]:.1f} ns, starting after connector high-Z.</text>')
    P.append('<text class="t h" x="14" y="438">Host request priority</text>')
    P.append('<text class="m" x="24" y="460">RES\u0304  &gt; finish current oito '
             'transfer  &gt; DEBUG / probe ACQUIRE  &gt; OAM DMA  &gt; PCM  &gt; CPU</text>')
    P.append('<text class="m" x="24" y="481">Every master change: old outputs high-Z '
             '\u2192 owner = none \u2192 t_TA \u2192 new owner. No suspend/resume.</text>')
    P.append('<text class="m" x="24" y="502">PCM acceptance = cartridge-byte falling '
             'edge; OAM acceptance = system-RAM-byte falling edge.</text>')
    P.append('</svg>')
    return "\n".join(P)


BLOCKS = {
    "bus.read_timeline": render_read_timeline,
    "bus.effect_matrix": render_effect_matrix,
    "bus.pcm_phases": render_pcm_phases,
    "bus.rdy_pullers": render_pullers,
}


# ── conformance traces (§16.2 owes these) ─────────────────────────────────────
def trace(kind, script, R=DEFAULT):
    s = S(kind=kind, live=True)
    rows = []
    for n, i in enumerate(script):
        before = s
        s, fx = step(s, i, R)
        edge = ""
        if before.tick == 0 and before.owner == "cpu":
            edge = "HOLD" if before.rdy_low else "ACCEPT"
        rows.append((n, before.tick, edge, sorted(fx) or ["—"],
                     f"pending={s.pending} serviced={s.serviced} owner={s.owner}"))
    return rows


TRACES = {
    "held_read_then_accept": ("vram_read", [
        Inputs(), Inputs(), Inputs(grant=True), Inputs(), Inputs(), Inputs()]),
    "held_empty_then_arrival": ("fifo_read", [
        Inputs(want_halt=frozenset(["oito"])), Inputs(), Inputs(),
        Inputs(event=True), Inputs(), Inputs(), Inputs()]),
    "external_write_not_stalled": ("ext_write", [
        Inputs(want_halt=frozenset(["oito"])), Inputs(), Inputs(),
        Inputs(want_halt=frozenset(["probe"])), Inputs(), Inputs()]),
    "takeover_preserves_txn": ("vram_read", [
        Inputs(want_halt=frozenset(["oito"])), Inputs(), Inputs(),
        Inputs(), Inputs(grant=True), Inputs(), Inputs(), Inputs()]),
}


def write_ownership_svg(out=None):
    out = out or (pathlib.Path(__file__).parent / "diagrams" / "bus-ownership.svg")
    out.parent.mkdir(exist_ok=True)
    out.write_text(render_ownership_svg() + "\n")
    return out


def write_traces(out=None):
    """Emit the conformance traces §16.2 owes, as a checked-in artefact.

    These were IOUs: "published traces proving exactly one acceptance ... for all
    five shapes". They are now a by-product of the model that already has to
    enumerate them, and the same file is the Tier-1 emulator fixture.
    """
    out = out or (pathlib.Path(__file__).parent / "artefacts" / "bus-traces.md")
    out.parent.mkdir(exist_ok=True)
    lines = ["# re8 bus conformance traces", "",
             "**Generated by `tools-bus-model.py` — do not edit.** Each trace is the "
             "tick-by-tick behaviour of one CPU transaction under a scripted "
             "environment, taken from the same `step()` the specification's tables "
             "are generated from.", ""]
    for name, (kind, script) in TRACES.items():
        lines += [f"## {name}", "", f"Cycle kind: `{kind}`", "",
                  "| tick | in-cycle | edge | effects | state |", "|---:|---:|---|---|---|"]
        for n, tk, edge, fx, st in trace(kind, script):
            lines.append(f"| {n} | {tk} | {edge or ''} | {', '.join(fx)} | {st} |")
        lines.append("")
    out.write_text("\n".join(lines))
    return out


def main():
    p = print
    p("re8 bus model — exhaustive state-space check\n" + "=" * 62)
    bad, states = check()
    p(f"{states} reachable states across {len(CYCLES)} cycle kinds; "
      f"{len(ELECTRICAL_PULLERS)} electrical RDY parties, of which "
      f"{len(HALT_REQUESTERS)} are external halt requesters bound by the "
      f"scheduling rule\n")
    for name, why in ELECTRICAL_PULLERS:
        role = "halt requester" if name in HALT_REQUESTERS else "EXEMPT (own instruction)"
        p(f"    {name:9} {role:26} {why}")
    p("")
    ok = True
    for name, _, why in PROPERTIES:
        if bad[name] is None:
            p(f"  HOLDS   {name}")
        else:
            ok = False
            kind, path = bad[name]
            p(f"  FAILS   {name}  ({kind}, {len(path)} ticks)")
            p(f"          {why}")
    p("\nhistorical regressions — each defect reintroduced must break its property")
    for rid, why, prop, caught in regressions():
        mark = "caught" if caught else "*** NOT CAUGHT ***"
        if not caught:
            ok = False
        p(f"  {rid:10} {prop:24} {mark}")
        p(f"             {why}")
    p("")
    svg = write_ownership_svg()
    p(f"\ngenerated diagram: diagrams/{svg.name}")
    f = write_traces()
    p(f"\nconformance traces written: {f.relative_to(f.parent.parent)} "
      f"({len(TRACES)} traces)")
    p("\nmechanism tests — the property must fail for the RIGHT REASON")
    for tid, why, prop, good in mechanism_tests():
        if not good:
            ok = False
        p(f"  {tid:20} {prop:24} {'correct' if good else '*** WRONG MECHANISM ***'}")
        p(f"             {why}")
    p("")
    p("A property nobody has watched fail is not evidence of anything; the block")
    p("above is this file applying that rule to itself.")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

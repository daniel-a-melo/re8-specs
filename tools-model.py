#!/usr/bin/env python3
"""
re8 executable model — every derived quantity in the specification, computed.

Nothing in here is a design choice; everything is a consequence of the choices
in CHOICES below. If a number appears in re8-console-spec.md and can be derived,
it should be derived here and checked by tools-verify.py.

Run directly to print the full table.
"""
import math

# ── design choices (the only free parameters) ──────────────────────────────────
CHOICES = dict(
    MASTER_HZ      = 21_477_270,   # 6 x NTSC colourburst
    CPU_DIV        = 3,
    TONE_DIV       = 12,
    MIX_DIV        = 448,
    LINE_TICKS     = 1365,
    LINES          = 262,
    ACTIVE_LINES   = 224,
    SNAPSHOT_LINE  = 224,
    SNAPSHOT_TICKS = 1024,
    SUPERCYCLE     = 13,
    DISPLAY_TICKS  = {"hi": 11, "lo": 10},   # of each supercycle
    COLS           = {"hi": 40, "lo": 32},
    TEXT_CELLS     = {"hi": 80, "lo": 64},
    SPRITE_CAP     = 512,
    SPRITE_FLOOR   = 480,          # a change that drops the sprite budget below
                                   # this is a capability regression, not a detail
    PHI2_MARGIN_MIN_NS = 0.0,      # must clear the CPU's pulse-width minima

    TILE_ACCESSES  = 64,           # 32 B tile, one read + one write per byte
    AUDXI_HZ       = 12_288_000,
    ASRC_TRIM_PPM  = 1000,
    SERVO_K        = 4096,
    SERVO_KP       = 2**18,
    SERVO_KI       = 2**14,
    # W65C02S @3.3V, 8 MHz grade
    T_PWH_MIN_NS   = 62.0,
    T_PWL_MIN_NS   = 63.0,
    T_DSR_NS       = 15.0,
    T_PCS_NS       = 15.0,
    T_ADS_NS       = 40.0,          # 3.3 V column, referenced to the PHI2 FALLING edge
    SRAM_NS        = 10.0,
    PAD_MUX_NS     = 10.0,
    DECODE_MIN_NS  = 20.0,         # input pad + $4044 decode + synchroniser + arbitrate         # oito pad + data mux + board, read return path
    # jtag+debug gained DBACK in v0.19: the probe acquisition and per-transfer
    # handshake needed an oito-driven acknowledgement, and DBG is defined as
    # probe-only open-drain. Inventing a "reply phase" on a one-directional wire
    # was the alternative, and it was not implementable.
    PIN_ROWS       = {"host bus": 29, "vram bus": 28, "mem control": 10,
                      "video": 17, "audio": 7, "cart mapper": 9,
                      "controllers": 18, "clock+reset": 3, "jtag+debug": 6},
    CART_CONTACTS  = {"data": 8, "addr": 14, "bank": 6, "control": 5, "power": 4},
)
C = CHOICES


def model():
    m = {}
    M = C["MASTER_HZ"]
    m["master_hz"]  = M
    m["cpu_hz"]     = M / C["CPU_DIV"]
    m["tick_ns"]    = 1e9 / M
    m["cpu_cycle_ns"] = 1e9 / m["cpu_hz"]
    m["tone_hz"]    = M / C["TONE_DIV"]
    m["mix_hz"]     = M / C["MIX_DIV"]
    m["line_cpu_cycles"] = C["LINE_TICKS"] // C["CPU_DIV"]
    m["frame_ticks"]     = C["LINES"] * C["LINE_TICKS"]
    m["frame_cpu_cycles"] = m["frame_ticks"] // C["CPU_DIV"]
    # why two counters are required
    m["frame_mod_mix"]  = m["frame_ticks"] % C["MIX_DIV"]
    m["frame_mod_tone"] = m["frame_ticks"] % C["TONE_DIV"]

    # PHI2: a 3-tick cycle cannot be split on whole ticks
    m["phi2_half_ns"] = m["cpu_cycle_ns"] / 2
    m["phi2_whole_hi_ns"] = 2 * m["tick_ns"]
    m["phi2_whole_lo_ns"] = 1 * m["tick_ns"]
    m["phi2_whole_ok"] = (m["phi2_whole_hi_ns"] >= C["T_PWH_MIN_NS"]
                          and m["phi2_whole_lo_ns"] >= C["T_PWL_MIN_NS"])
    m["phi2_half_margin_ns"] = m["phi2_half_ns"] - max(C["T_PWH_MIN_NS"], C["T_PWL_MIN_NS"])

    # supercycle
    assert C["LINE_TICKS"] % C["SUPERCYCLE"] == 0
    m["supercycles_per_line"] = C["LINE_TICKS"] // C["SUPERCYCLE"]

    for mode in ("hi", "lo"):
        n = m["supercycles_per_line"]
        cap   = n * C["DISPLAY_TICKS"][mode]
        spare = n * (C["SUPERCYCLE"] - C["DISPLAY_TICKS"][mode])
        # fine scroll costs one extra column per plane
        bg    = (C["COLS"][mode] + 1) * 6 * 2
        text  = C["TEXT_CELLS"][mode] * 2
        spr   = min(C["SPRITE_CAP"], cap - bg - text)
        load  = bg + text + spr
        line261_free = C["LINE_TICKS"] - load
        blanking = (C["LINE_TICKS"] - C["SNAPSHOT_TICKS"])            # line 224
        blanking += (C["LINES"] - C["SNAPSHOT_LINE"] - 2) * C["LINE_TICKS"]  # 225..260
        blanking += line261_free                                       # line 261
        interleaved = m["frame_ticks"] - C["ACTIVE_LINES"] * load - C["SNAPSHOT_TICKS"]
        m[mode] = dict(capacity=cap, spare_per_line=spare, bg=bg, text=text,
                       sprite_budget=spr, worst_line=load, line261_free=line261_free,
                       blanking=blanking, interleaved=interleaved,
                       tiles_blanking=blanking // C["TILE_ACCESSES"],
                       tiles_interleaved=interleaved // C["TILE_ACCESSES"],
                       sprites_32px=spr // 16, cpu_wait_ticks=C["DISPLAY_TICKS"][mode])
        # invariants recorded rather than raised, so the verifier can report them all
        m[mode]["fits"] = load <= cap
        m[mode]["sprite_floor_ok"] = spr >= C["SPRITE_FLOOR"]

    # ── CPU bus, falling edges on INTEGER ticks ───────────────────────────────
    # Cycle k occupies ticks [3k, 3k+3). PHI2 falls at 3k, rises at 3k+1.5, and
    # falls again at 3k+3 — that second fall retires cycle k and starts k+1.
    tick = m["tick_ns"]
    addr_valid   = C["T_ADS_NS"] / tick               # ticks after the fall at 3k
    m["addr_valid_tick"] = addr_valid
    # Could the request be captured in time for the tick-1 slot (a 1-cycle read)?
    m["capture_slack_tick1_ns"] = (1 - addr_valid) * tick
    m["read_1cycle_possible"]   = m["capture_slack_tick1_ns"] >= C["DECODE_MIN_NS"]
    # Realisable capture tick, and the resulting completion
    m["capture_tick"]   = 2                            # 53.1 ns after address valid
    m["capture_slack_ns"] = (m["capture_tick"] - addr_valid) * tick
    # Arbitration is step 3 and detection step 2 OF THE SAME TICK, so the first
    # eligible slot is the capture tick itself. An earlier revision published
    # slot 3 here, contradicting the event order the same document relies on for
    # its 11/10-tick request-to-grant bound.
    slot                = m["capture_tick"]
    data_ready          = slot + 1 + C["PAD_MUX_NS"] / tick
    data_by             = 6.0 - C["T_DSR_NS"] / tick   # sampling edge of cycle k+1
    m["read_margin_ns"] = (data_by - data_ready) * tick
    m["read_cycles"]    = 2
    m["rdy_by_tick"]    = 3.0 - C["T_PCS_NS"] / tick
    m["decode_to_rdy_ns"] = (m["rdy_by_tick"] - addr_valid) * tick

    # ── PCM steal placement, derived from the SAME integer-edge origin ────────
    # A refill request is raised at step 8 of mix tick m. Falling edges are at
    # integer ticks 3k, and for m mod 3 == 0 the edge at m is step 0 of m and has
    # already passed. So the next edge is always the next multiple of 3 above m.
    # Deriving all three rows from one expression is the point: the previous
    # half-tick table (m+1.5 / m+0.5 / m-0.5) survived three revisions as prose
    # because no tool recomputed it, and it produced an 8.3 ns phase-1 budget and
    # a normative "phases 1 and 2 defer" freeze from edges that do not exist.
    m["pcm_phase"] = {}
    for r in range(3):
        delta = 3 - r                        # 3*(floor(m/3)+1) - m for m mod 3 == r
        setup = delta * tick - C["T_PCS_NS"]
        m["pcm_phase"][r] = dict(edge_delta_ticks=delta, setup_ns=setup,
                                 steal_begins_tick=delta + 1)
    # oito never stalls a cycle that emits an external write strobe (spec 6.5), so
    # the halt can be deferred past a run of them. The longest such run a 65C02
    # produces is the interrupt/BRK push sequence: PCH, PCL, P -- three writes to
    # the stack, which lives in system RAM.
    m["max_consecutive_ext_writes"] = 3
    m["halt_defer_max_cycles"] = m["max_consecutive_ext_writes"]
    m["halt_defer_max_ticks"]  = m["halt_defer_max_cycles"] * C["CPU_DIV"]
    m["pcm_min_setup_ns"]   = min(v["setup_ns"] for v in m["pcm_phase"].values())
    m["pcm_worst_phase"]    = min(m["pcm_phase"], key=lambda r: m["pcm_phase"][r]["setup_ns"])
    m["pcm_steal_min_tick"] = min(v["steal_begins_tick"] for v in m["pcm_phase"].values())
    m["pcm_steal_max_tick"] = max(v["steal_begins_tick"] for v in m["pcm_phase"].values())
    m["pcm_steal_max_tick_deferred"] = m["pcm_steal_max_tick"] + m["halt_defer_max_ticks"]
    # Does any phase defer the halt beyond the cycle in progress? With integer
    # edges, no: every phase's next edge retires the cycle already running.
    m["pcm_any_phase_defers"] = False

    # OAM DMA. BOTH endpoints come from one function, because publishing only the
    # floor is how "always costs 8N + 6" survived after the external-write
    # deferral turned it into a range.
    # `mult` is 1 in blanking and 4 under active display, where each byte's VRAM
    # write waits the full slot bound. The startup deferral is added ONCE either
    # way: it happens before the transfer begins and does not scale with it.
    def oam(n, defer, mult=1):
        return 8 * n * mult + 6 + defer
    m["oam_defer_max"]       = m["halt_defer_max_cycles"]
    m["oam_active_mult"]     = 4
    m["oam_full_min"]        = oam(128, 0)
    m["oam_full_max"]        = oam(128, m["oam_defer_max"])
    m["oam_six_min"]         = oam(6, 0)
    m["oam_six_max"]         = oam(6, m["oam_defer_max"])
    mu = m["oam_active_mult"]
    m["oam_full_active_min"] = oam(128, 0, mu)
    m["oam_full_active_max"] = oam(128, m["oam_defer_max"], mu)
    m["oam_six_active_min"]  = oam(6, 0, mu)
    m["oam_six_active_max"]  = oam(6, m["oam_defer_max"], mu)
    m["oam_is_range"]        = m["oam_defer_max"] > 0
    # retained names, now explicitly the FLOOR rather than "the" cost
    m["oam_full_phase0"] = m["oam_full_min"]
    m["oam_six_entries"] = m["oam_six_min"]
    m["snapshot_cpu_cycles"] = math.ceil(C["SNAPSHOT_TICKS"] / C["CPU_DIV"])

    # PCM refill
    m["pcm_burst_bytes"] = 8
    m["pcm_burst_cycles"] = m["pcm_burst_bytes"] + 2
    m["pcm_tax_pct"] = 100 * m["pcm_burst_cycles"] * m["mix_hz"] / m["cpu_hz"]

    # ASRC
    fin, fout = m["mix_hz"], C["AUDXI_HZ"] / 256
    m["asrc_fin"], m["asrc_fout"] = fin, fout
    inc = round(2**32 * fin / fout)
    m["asrc_increment"] = inc
    m["asrc_increment_hex"] = f"${inc:08X}"
    m["asrc_headroom_ppm"] = (2**32 - 1) / inc * 1e6 - 1e6
    m["asrc_trim_fits"] = inc * (1 + C["ASRC_TRIM_PPM"] / 1e6) < 2**32
    # The filter itself is UNDESIGNED. The 64x64 Kaiser set is a REJECTED
    # BASELINE, and the reason is "never validated under the normative five-part
    # procedure" -- NOT "measured -72.8 dB". That number came from measuring each
    # phase as though it were the assembled prototype, which spec 8.4 identifies
    # as a category error, and three formulations of it gave -72.8, -25.7 and
    # -45.3 dB with no coefficient changing. A figure from a withdrawn
    # measurement cannot be evidence under the procedure that replaced it.
    # No tap count, window or attenuation is modelled here, because modelling the
    # rejected design as if it were the design is what let it look verified.
    # Only the rate arithmetic survives.
    m["asrc_stopband_edge_hz"] = fin - 20000        # first image of the protected band
    m["asrc_designed"] = False
    # servo poles
    g = C["SERVO_K"] / 2**32
    a = g * C["SERVO_KP"] + g * C["SERVO_KI"] - 2
    c = 1 - g * C["SERVO_KP"]
    d = a * a - 4 * c
    roots = ([(-a + math.sqrt(d)) / 2, (-a - math.sqrt(d)) / 2] if d >= 0
             else [complex(-a / 2, math.sqrt(-d) / 2)])
    m["servo_poles"] = [abs(x) for x in roots]
    m["servo_stable"] = all(abs(x) < 1 for x in roots)

    # pins and contacts
    m["pin_signals"] = sum(C["PIN_ROWS"].values())
    m["pin_supply_est"] = 24
    m["pin_total_est"] = m["pin_signals"] + m["pin_supply_est"]
    m["pin_spare"] = 176 - m["pin_total_est"]
    # The probe header: 16 address + 8 data + 4 JTAG + 8 CPU control + DBACK,
    # then 4 power and 1 reserved position. Derived, because an earlier revision
    # had the BOM, 6.4, 13, 16.2, an SVG and the marketing page disagreeing.
    m["header_signals"] = 16 + 8 + 4 + 8 + 1
    m["header_positions"] = m["header_signals"] + 4 + 1
    m["cart_contacts"] = sum(C["CART_CONTACTS"].values())
    return m


def main():
    m = model()
    p = print
    p("re8 derived quantities\n" + "=" * 60)
    p(f"master {m['master_hz']:,} Hz   CPU {m['cpu_hz']:,.0f} Hz   tick {m['tick_ns']:.2f} ns")
    p(f"line {C['LINE_TICKS']} ticks = {m['line_cpu_cycles']} CPU cycles"
      f"   frame {m['frame_ticks']:,} ticks")
    p(f"frame mod mix-div = {m['frame_mod_mix']}  -> "
      f"{'raster and audio counters MUST be separate' if m['frame_mod_mix'] else 'one counter would do'}")
    p(f"PHI2 whole-tick split legal? {m['phi2_whole_ok']}"
      f"   50% duty {m['phi2_half_ns']:.1f} ns, margin {m['phi2_half_margin_ns']:.1f} ns")
    p(f"VRAM read: {m['read_cycles']} CPU cycles. 1-cycle possible? {m['read_1cycle_possible']} "
      f"(only {m['capture_slack_tick1_ns']:.1f} ns to capture, needs {C['DECODE_MIN_NS']:.0f})")
    p(f"  capture at tick {m['capture_tick']} ({m['capture_slack_ns']:.1f} ns slack), "
      f"return margin {m['read_margin_ns']:+.1f} ns")
    p(f"decode->RDY budget {m['decode_to_rdy_ns']:.1f} ns")
    p("PCM steal placement (integer falling edges):")
    for r, v in m["pcm_phase"].items():
        p(f"  m mod 3 = {r}: next edge +{v['edge_delta_ticks']} ticks, "
          f"{v['setup_ns']:.1f} ns after t_PCS, steal begins m+{v['steal_begins_tick']}")
    p(f"  worst phase {m['pcm_worst_phase']} at {m['pcm_min_setup_ns']:.1f} ns; "
      f"steal begins {m['pcm_steal_min_tick']}-{m['pcm_steal_max_tick']} ticks after the mix tick")
    p(f"  external-write deferral: up to {m['halt_defer_max_cycles']} CPU cycles "
      f"({m['halt_defer_max_ticks']} ticks) -> worst-case onset "
      f"{m['pcm_steal_max_tick_deferred']} ticks")
    p(f"pins {m['pin_signals']} signals + ~{m['pin_supply_est']} supply = ~{m['pin_total_est']} "
      f"of 176 ({m['pin_spare']} spare)   cartridge {m['cart_contacts']} contacts   "
      f"header {m['header_positions']} positions ({m['header_signals']} non-power)")
    p("-" * 60)
    for mode in ("hi", "lo"):
        d = m[mode]
        p(f"{mode}-res: capacity {d['capacity']}  BG {d['bg']}  text {d['text']}  "
          f"sprites {d['sprite_budget']} ({d['sprites_32px']} x 32px)")
        p(f"         worst line {d['worst_line']}  line261 free {d['line261_free']}")
        p(f"         blanking {d['blanking']:,} -> {d['tiles_blanking']} tiles   "
          f"interleaved {d['interleaved']:,} -> {d['tiles_interleaved']} tiles")
    p("-" * 60)
    p(f"OAM DMA active-display full {m['oam_full_active_min']}-{m['oam_full_active_max']}   "
      f"6 entries {m['oam_six_active_min']}-{m['oam_six_active_max']}")
    p(f"OAM DMA full {m['oam_full_min']}-{m['oam_full_max']} cycles "
      f"(one trigger phase, external-write deferral 0-{m['oam_defer_max']})   "
      f"6 entries {m['oam_six_min']}-{m['oam_six_max']}   "
      f"snapshot {m['snapshot_cpu_cycles']}")
    p(f"PCM burst {m['pcm_burst_bytes']} B = {m['pcm_burst_cycles']} cycles -> "
      f"{m['pcm_tax_pct']:.1f}% max tax")
    p(f"ASRC inc {m['asrc_increment_hex']} headroom +{m['asrc_headroom_ppm']:.1f} ppm  "
      f"trim ±{C['ASRC_TRIM_PPM']} fits: {m['asrc_trim_fits']}")
    p(f"ASRC filter: NOT DESIGNED — stopband edge {m['asrc_stopband_edge_hz']:,.0f} Hz "
      f"(f_in - 20 kHz); tap count, window and width are design outputs")
    p(f"servo poles {[round(x,3) for x in m['servo_poles']]} stable: {m['servo_stable']}")
    if not m["asrc_designed"]:
        p("")
        p("!! DEFERRED, OWED: the HDMI audio resampler filter is undesigned (spec 16.2.1).")
        p("!! The ASRC specifically blocks oito RTL freeze and HDMI audio.")
        # "Everything else is unblocked" was a project-status claim this tool has
        # no basis for: spec 16.2 carries many independent gates on schematic
        # freeze and tape-out. Scope the sentence to the ASRC and point at the
        # real list rather than implying it is empty.
        try:
            import pathlib, re as _re
            _t = pathlib.Path(__file__).with_name("re8-console-spec.md").read_text()
            _sec = _t.split("### 16.2 Hardware validation still outstanding")[1] \
                     .split("### 16.2.1")[0]
            _n = sum(1 for l in _sec.split("\n")
                     if l.startswith("|") and not l.startswith("|---")
                     and "| Item |" not in l)
            p(f"!! It does NOT clear the other {_n} independent gates in spec 16.2 "
              f"(CH7035B, AD725,")
            p("!! pinout, waveforms, HDMI licensing, part suffix/lifecycle evidence, and more).")
        except Exception:
            p("!! Other independent gates in spec 16.2 remain open.")


if __name__ == "__main__":
    main()

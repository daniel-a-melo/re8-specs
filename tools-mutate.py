#!/usr/bin/env python3
"""
Run mutation tests in a THROWAWAY COPY of the repository.

WHY THIS EXISTS
---------------
Round seventeen found that decisions D447/D448 and the v0.18 version-history row
all claimed §16.2 gates that were **not in the document**. The mechanism was the
mutation-test workflow itself:

  * mutations were applied to the LIVE specification and undone with `cp` from a
    snapshot in /tmp;
  * the snapshot was sometimes older than the work in progress; and
  * two of those edits had silently landed in the WRONG PLACE to begin with,
    because the front-page outstanding list contains a one-cell copy of every
    §16.2 row title, so `text.index("| **Snapshot-and-commit traces** |")` finds
    the front-page copy, not the §16.2 row. The front-page regeneration that ran
    afterwards then overwrote them.

Every part of that is avoidable by never mutating the file you intend to keep.
This script copies the repo to a temp directory, mutates there, runs the verifier
there, and throws the copy away. The live tree is opened read-only.

    python3 tools-mutate.py                # run the registered mutation suite
    python3 tools-mutate.py --list         # show it

A mutation that does not produce a FAIL is reported as NOT CAUGHT, which is the
result that matters: a guard nobody has watched fail is not evidence of anything.
"""
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).parent
COPY_FILES = ["re8-console-spec.md", "README.md", "re8-parts-ledger.json",
              "tools-model.py", "tools-verify.py", "tools-bus-model.py",
              "tools-bus-inject.py", "re8-design-history.md",
              "re8-console-spec.html", "re8-spec.html"]

# (id, file, find, replace, what it must break)
MUTATIONS = [
    ("R13-BUS1", "re8-console-spec.md",
     "Every **oito register** write and every **font-RAM** write is timed from **step 0**",
     "Every register write oito performs and every write strobe it generates is gated by "
     "`cpu_transfer_accept` from step 0",
     "external write strobe gated"),
    ("R15-BUS1", "re8-console-spec.md",
     "bus_cycle_valid  ≡  owner ≠ none",
     "bus_cycle_valid  ≡  BE high AND the CPU cycle is not held",
     "qualified on RDY"),
    ("R16-BUS1", "re8-console-spec.md",
     "cart_we_enable          ≡ SAVE_CTRL.4",
     "we                      ≡ SAVE_CTRL.4",
     "bare symbol `we`"),
    ("R16-BUS2", "re8-console-spec.md",
     "ROM_CĒ  = !rom_select", "ROM_CĒ  = rom_select",
     "active-low but its equation"),
    ("R16-BUS3", "re8-console-spec.md",
     "boot_write    = boot_select && write_phase && boot_program_owner",
     "boot_write    = boot_select && write_phase",
     "does not include boot_program_owner"),
    ("R16-BUS4", "re8-console-spec.md",
     "owner_transfer_accept(probe)  = the falling edge of the PHI2 cycle oito GENERATES",
     "owner_transfer_unspecified   = nothing",
     "no 'probe' case"),
    ("R16-BUS7", "re8-console-spec.md",
     "boot_win                ≡ external_boot_selected && boot_window_address",
     "boot_win                ≡ boot_window_address",
     "no BOOT_SRC term"),
    ("R17-BUS4", "re8-console-spec.md",
     "cart_write    = bus_cycle_valid && write_phase && cart_A",
     "cart_write    = bus_cycle_valid && write_phase",
     "cart_A"),
    ("R17-VAL1", "re8-console-spec.md",
     "**Held external-read persistence:**", "Held-read placeholder:",
     "has no 'Held external-read persistence' gate"),
    ("R17-VAL3", "re8-console-spec.md",
     "| **Probe bus ownership and transfers** |", "| Probe placeholder |",
     "has no 'Probe bus ownership and transfers' gate"),
    ("front-page shape", "re8-console-spec.md",
     "| prog8 ROM and multi-bank toolchain fixture |",
     "| prog8 ROM and multi-bank toolchain fixture | criterion | §14.1 |",
     "front-page outstanding table is malformed"),
    ("front-page extra", "re8-console-spec.md",
     "| **ASRC filter design** |\n| CPU bus pre-tapeout timing sign-off |",
     "| **ASRC filter design** |\n| HDMI audio resampler — duplicate |\n"
     "| CPU bus pre-tapeout timing sign-off |",
     "front-page outstanding list does not exactly match"),
    ("lifecycle queue", "re8-console-spec.md",
     "`none` for the other **25** active parts",
     "`none` for the other **24** active parts",
     "lifecycle queue does not match the ledger"),
    ("rejected path gate", "re8-console-spec.md",
     "The **6.6 ns one-cycle capture path is rejected and unused**",
     "The **6.6 ns one-cycle capture path must close**",
     "does not exclude the rejected 6.6 ns one-cycle path"),
    ("R18-BUS5", "re8-console-spec.md",
     "cart_F_high             ≡ boot_window_address && cart_overlay_selected",
     "cart_F_high             ≡ boot_window_address",
     "not masked under the boot overlay"),
    # R18-BUS4 is RETIRED, not lost. Its anchor was the sentence "every probe
    # transceiver has its OE tied to DBACK" -- which round 19 showed to be the
    # defect, not the fix, so the anchor is gone by design. Its safety intent
    # ("a frozen MCU cannot drive") is now R19-BUS1, and the OE half is R19-BUS1b.
    # Recorded here because a silently deleted mutation is indistinguishable
    # from a forgotten one.
    ("R18-BUS3", "re8-console-spec.md",
     "t_PHD", "t_NOHOLD",
     "no data-hold interval"),
    ("R18-BUS1", "re8-console-spec.md",
     "probe_transfer_pending", "nothing_in_particular",
     "not qualified by a pending transfer"),
    ("R19-BUS1", "re8-console-spec.md",
     "probe_drive_addr = DBACK && !BE", "probe_drive_addr = mcu_dir_addr",
     "does not contain DBACK"),
    ("R19-BUS1b", "re8-console-spec.md",
     "`/OE` tied low",
     "`/OE` tied to DBACK",
     "receive-buffer /OE is not tied enabled"),
    ("R19-DEC1", "re8-console-spec.md",
     "stub_read               ≡ stub_select && R/W̄",
     "stub_unnamed            = nothing",
     "no stub_read predicate"),
    ("R20-BUS4", "re8-console-spec.md",
     "oito's cartridge mapper outputs** \u2014 `BANK0\u2013BANK5`",
     "oito's bus-master outputs including BANK0-BANK5",
     "BANK"),
    ("probe-bank guard", "re8-console-spec.md",
     "probe drives address, `R/W̄` and (for a write) data",
     "probe drives address, bank, `R/W̄` and (for a write) data",
     "a probe drive term includes bank"),
    ("R20-BUS1", "re8-console-spec.md",
     "| **DEBUG jam active** | cpu | high | **1** |",
     "| **DEBUG jam active** | cpu | high | **0** |",
     "jam"),
    ("R21-BUS1", "re8-console-spec.md",
     "No net joins two push-pull outputs",
     "A net may join two push-pull outputs",
     "does not forbid shared push-pull outputs"),
    ("R21-BUS2", "re8-console-spec.md",
     "/OE_ARW = nDBACK OR BE",
     "/OE_ARW = DBACK OR BE",
     "active-low A/RW enable equation"),
    ("R21-BUS3", "re8-console-spec.md",
     "/OE_DATA = nDBACK OR (BE XOR R/W\u0304)",
     "/OE_DATA = nDBACK OR BE",
     "active-low data enable equation"),
    ("R21-BUS4", "re8-console-spec.md",
     "ACQUIRE_WAIT \u2192 OWNED_GRANT",
     "any DBACK rise",
     "first-transfer timer has no explicit grant transition"),
    ("R21-TIM1", "re8-console-spec.md",
     "high-Z **at the connector**, then wait `t_TA`",
     "high-Z at the connector and immediately continue",
     "release path has no connector-high-Z plus t_TA"),
    ("R21-BUS6", "re8-console-spec.md",
     "owner_transfer_accept(oito)   = PHI2 falling edge that latches one",
     "owner_transfer_accept(oito)   = the granted slot completes",
     "host arbitration is missing 'owner_transfer_accept(oito)'"),
    ("R21-BUS6b", "re8-console-spec.md",
     "the **current** oito-owned OAM transfer or PCM burst completes",
     "the current oito-owned operation may be suspended",
     "host arbitration is missing 'the **current** oito-owned OAM transfer or PCM burst completes'"),
    ("diagram: pin count", "diagrams/system-block.svg",
     "127 signal pins", "116 signal pins",
     "stale oito signal-pin count"),
    ("diagram: probe OE", "diagrams/bus-ownership.svg",
     "/OE_DATA = !DBACK OR (BE XOR R/W\u0304)",
     "/OE_DATA = DBACK",
     "omits current contract"),
    ("diagram: ASRC taps", "diagrams/audio-chain.svg",
     "P &#215; T &#8212; NOT YET DESIGNED", "64 &#215; 32 taps",
     "REJECTED baseline"),
    ("diagram: VRAM priority", "diagrams/compositor-arbitration.svg",
     "2 \u00b7 CPU VRAM port / OAM DMA", "2 \u00b7 Blitter",
     "VRAM priority order"),
    ("review count", "README.md",
     "adversarial reviews performed", "adversarial reviews performedX",
     None),      # expected to change nothing; a control
    ("patch version", "re8-console-spec.md",
     "**Version 0.23.1**", "**Version 0.23.2**",
     "but the Markdown is v0.23.2"),
]


def run_one(mid, fname, find, repl, expect):
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        for f in COPY_FILES:
            src = ROOT / f
            if src.exists():
                shutil.copy2(src, tmp / f)
        (tmp / "diagrams").mkdir(exist_ok=True)
        for svg in (ROOT / "diagrams").glob("*.svg"):
            shutil.copy2(svg, tmp / "diagrams" / svg.name)

        target = tmp / fname
        text = target.read_text()
        if find not in text:
            return "ANCHOR MISSING", f"{find[:60]!r} not found"
        # replace EVERY occurrence: a presence guard asserts the term exists
        # somewhere, so a single-site edit does not test it. Two mutations
        # reported NOT CAUGHT for exactly this reason.
        target.write_text(text.replace(find, repl))

        r = subprocess.run([sys.executable, str(tmp / "tools-verify.py")],
                           cwd=str(tmp), capture_output=True, text=True,
                           env={"RE8_SKIP_BUS": "1", "PATH": "/usr/bin:/bin"})
        fails = [l for l in r.stdout.split("\n") if l.startswith("FAIL")]
        if expect is None:
            return ("control", f"{len(fails)} failure(s)")
        hit = next((l for l in fails if expect in l), None)
        return ("caught" if hit else "*** NOT CAUGHT ***",
                (hit or (fails[0] if fails else "no failure at all"))[:110])


def main():
    if "--list" in sys.argv:
        for m in MUTATIONS:
            print(f"  {m[0]:18} {m[1]:22} expects {m[4]!r}")
        return 0
    print(f"mutation suite — {len(MUTATIONS)} mutations, each in a throwaway copy")
    print("=" * 72)
    bad = 0
    for mid, fname, find, repl, expect in MUTATIONS:
        status, detail = run_one(mid, fname, find, repl, expect)
        if "NOT CAUGHT" in status or status == "ANCHOR MISSING":
            bad += 1
        print(f"  {mid:18} {status:20} {detail}")
    print("=" * 72)
    print("The live tree was never modified." if not bad else
          f"{bad} mutation(s) did not behave as expected.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

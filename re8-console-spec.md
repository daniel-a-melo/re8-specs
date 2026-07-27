# re8 console — high-level technical specification

**Document purpose.** This is the normative specification of the re8 console: a boutique 2D games machine built from currently-manufactured parts, comprising a W65C02S CPU and a single custom ASIC (**oito**) that integrates the video display processor, a 16-voice audio unit, the cartridge mapper and all system glue.

It defines everything an implementer needs to build the hardware or a **Tier 1 (compatibility) reference emulator** (§14.5): machine-visible behaviour, electrical interfaces and bill of materials, timing, file and tool ABI, and the conformance contract.

**Version 0.1** · 2026-07-26 · *architecture draft*. Revision history and the versioning rules are in §18.

**Document map.** This specification is normative; rationale and history live in **`re8-design-history.md`**.

| Concern | Sections |
|---|---|
| **1. Machine-visible behaviour** | §4 CPU · §5 memory map & registers · §6 oito (VDP, arbitration, formats, raster, text) · §8 APU · §9 input · §10 interrupts |
| **2. Electrical interfaces & BOM** | §2 BOM & power tree · §6.2–6.3 video bus & pins · §7 video outputs · §11 cartridge · §12 expansion header · §13 debug probe |
| **3. Timing** | §3 clocks · §6.5 VRAM arbitration · §6.7 raster · §11.1.1 handoff state |
| **4. File & tool ABI** | §11.0 ROM image · §11.2 header · §11.4 saves · §14 SDK & toolchain |
| **5. Conformance & limits** | §15 restrictions · §16 conformance & validation |
| **Revision** | §17 design history (separate document) · §18 version history |

Diagrams accompanying this document are in `diagrams/` and are referenced from the sections they illustrate.

**Requirement keywords.** **MUST**, **MUST NOT**, **SHOULD** and **MAY** are used in the RFC 2119 sense and **only** for requirements; all other prose is descriptive and carries no obligation. Performance figures carry either a stated workload or the label *estimate*; no cross-machine comparisons are made.

**Scope.**

- *In scope:* all active components (BOM), console capabilities and restrictions, how active elements operate and interconnect (including pin/signal mapping and voltage domains), memory map, interrupts, debug-probe operation, SDK and tooling ABI, and the conformance contract. **Analog video and audio buffering is in scope** — buffers and line drivers are active components.
- *Out of scope:* PCB layout, ASIC internals (gate/RTL level), passive component values, mechanical/enclosure design, and production economics.

**Status (2026-07-26): architecture draft.** The memory map, register file, subsystem behaviour and BOM are specified to a level intended to support emulator implementation and schematic capture. The design has been through two adversarial reviews, both resolved in full; the decision log and review registers live in **`re8-design-history.md`**.

**Explicitly outstanding before compatibility freeze or tape-out** (full criteria in §16.2):

| Item |
|---|
| CH7035B qualification (custom 240p input, nearest-neighbour, latency, EDID-free operation) |
| AD725 240p validation (colour lock, burst, vertical lock) |
| prog8 ROM-ability validation (`%option romable` + build gate + fixture) |
| Typed-symbol source against the pinned compiler |
| Debug-info pipeline proof fixtures, per host |
| W65C02S instruction-jamming validation on silicon |
| Full 144-pin package table (pad types, per-state directions) |
| HDMI/DVI/S-PDIF licensing review by counsel |
| Closure package (register CSV, golden vectors, conformance ROMs) |

---

## 1. System overview

![re8 system block diagram](diagrams/system-block.svg)

re8 is a boutique 2D game console built exclusively from currently-manufactured ("factory-fresh") components — no New Old Stock. Its architecture deliberately sits between the 8-bit era (NES, Master System, PC Engine) and early-90s arcade hardware (Capcom CPS-1):

- **CPU:** WDC W65C02S, 8-bit, fully static CMOS, single 3.3V rail.
- **oito:** one custom ASIC (SkyWater 130nm, **LQFP-144, custom pad ring**) combining a Video Display Processor (hybrid tile renderer + mini-blitter, hardware sprites, hardware collision) and a **16-voice APU** (PSG + wavetable + PCM).
- **Memory:** 16KB system SRAM (CPU bus) + 128KB VRAM (private bus to oito).
- **Media:** parallel NOR flash cartridges, 36-pin edge connector, **console-side fixed-plus-switchable 16KB mapper**; optional battery-free on-cart FRAM saves (§11.4).
- **Video out:** one digital pipeline (12-bit RGB + syncs from oito) fanned out to five simultaneous outputs: composite, S-Video, RGB SCART, **15 kHz analog RGBHV on DE-15** (not VGA timing), and 1080p60 DVI-D on an HDMI-type connector.
- **Input:** two DB9 ports, Sega Genesis/Mega Drive controller compatible; optional **PS/2 keyboard and mouse** through a port via a passive adaptor (§9.1/§9.2), the mouse with a fully hardware-rendered cursor.
- **Developer hardware:** 40-pin expansion header (CPU bus + oito JTAG) driving a USB debug probe.
- **SDK:** prog8 language → 64tass → flat ROM binary; `re8.*` event-driven library; VS Code extension with source-level debugging, VRAM inspector, and a WASM reference emulator.

**Core philosophy.**

1. *Zero-emulation:* real silicon executes game code; no soft-cores or interpretation layers.
2. *No NOS:* every part must be orderable new (this single rule drove the CPU, sound, video-encoder and flash choices).
3. *First-time-right silicon:* oito is 100% digital; every analog function (video encoding, DACs, audio filtering) lives on the motherboard in proven off-the-shelf parts, because analog blocks on a low-volume ASIC are hard to verify and risky.
4. *ROM is cheap, RAM is precious:* the SDK trades ROM space freely to preserve the 16KB RAM budget.

---

## 2. Bill of materials — active components

| # | Component | Part | Function | Voltage | Bus/interfaces |
|---|-----------|------|----------|---------|----------------|
| 1 | CPU | WDC **W65C02S6TPG-14** | 8-bit host processor | 3.3V (datasheet AC table: 14MHz @5V, **8MHz @3.3V**) | 16-bit address, 8-bit data, PHI2, R/W̄, SYNC, RDY, BE, RES̄, IRQ̄ |
| 2 | Custom ASIC | **oito** (re8-vdp-8001, SkyWater 130nm, **custom pad ring, LQFP-144**, ~134–138 pins used (signal budget, not a sign-off pinout —)) | VDP (tiles, sprites, blitter, collision, scroll) + 16-voice APU + cartridge mapper + address decode + joypad read | 1.8V core / 3.3V I/O | CPU bus slave; private VRAM bus master; 12-bit digital RGB + syncs out; PWM audio out; I²S out; 2× controller ports; JTAG |
| 3 | System RAM | **`IS61C256AL`** (32K×8, 10 ns, 3.3V) with **A14 tied low — only 16KB is decoded** (32KB parts are far more available than 16KB). Alternative: 2× `AS6C6264` (8K×8). **A 55 ns part is an acceptable substitute** (see timing note) | CPU work RAM | 3.3V | CPU bus |
| 4 | VRAM | **`IS61C1024AL`** (128K×8, 10 ns, 3.3V) — exact fit, 17 address lines matching VA0–VA16 | Video memory | 3.3V | Private bus to oito only |
| 5 | Cartridge flash | **`SST39VF040`** (512KB, TSOP-32/PLCC-32) **or `SST39VF080`** (1MB = 8Mbit×8, **TSOP-40** — 20 address lines do not fit a 32-pin package). Both 3.0–3.6V, **70 ns**, JEDEC program/erase. *Same SST39 family as the boot flash, so **one JEDEC driver serves cartridge, boot flash and updater**. "Macronix" was a vendor name, not a selectable item —* | Game ROM (in cartridge) | 3.3V | Cartridge slot (D0–D7, A0–A13, BANK0–BANK5) |
| 6 | Boot ROM | internal oito stub (~2KB on-die mask ROM, unbrickable) **+** external boot flash **SST39VF010** (128KB parallel NOR, 3.3V, PLCC-32/TSOP-32) | Two-stage boot firmware — stub → updateable firmware → cartridge (§11.1) | on-die / 3.3V | internal / CPU bus |
| 7 | Video encoder | Analog Devices **AD725** *(provisionally selected — 240p operation requires bench validation)* | Analog RGB → **NTSC** composite + S-Video (Y/C) (the part's PAL mode is unused) | 5V (§2.1) | Analog RGB in (from R-2R DACs), CSYNC, subcarrier clock (14.318MHz NTSC / 17.734MHz PAL) |
| 8 | DVI transmitter | Chrontel **CH7035B** | 240p digital RGB → scaled 1080p60 **DVI-D (video only, no audio)** over HDMI-shaped connector (§7.1) | **1.8V `DVDD`/`AVDD_PLL` + 3.3V `VDDH`/`AVDD`/`VDDMQ`/`VDDMS`/`VDDIO`** | **24-bit RGB-888 parallel in, fed by oito's 12 lines with bit replication** + HSYNC/VSYNC + pixel clock; I²C slave (SPC/SPD); I²C master (SPCM/SPDM); TMDS out |
| 8a | Digital-audio transmitter | **TI `DIT4192`** (24-bit/192kHz I²S→S/PDIF/AES3 transmitter, active production) — *replaces the WM8805 example, which Cirrus marks **end-of-life** and which therefore violated the console's founding no-NOS rule*. Alternative kept on file: encode S/PDIF in a CPLD or in oito (biphase-mark is simple, but costs an ASIC pin and risk) | APU I²S → S/PDIF (§8.4); royalty-free | 3.3V | I²S in; S/PDIF out |
| 8b | Optical transmitter | current-production **3.3V TOSLINK transmitter module** (Everlight PLT133 / Sharp GP1FAV31TK0F class), with its **drive current and series resistor specified** by the module datasheet | electrical S/PDIF → optical out | 3.3V | S/PDIF in; TOSLINK out |
| 9 | Config ROM | Chrontel **CH9904 — an 8KB (8192×8) I²C boot ROM** (*not* a sub-1KB device). Substitute: a generic 8-pin I²C EEPROM (24C64-class, 8KB) **only if** it matches address **`0x57`**, the CH7035B master's byte/page-read protocol, and is readable before `RESETB` releases | holds the CH7035B power-on register image; the configuration binary is a **versioned release artefact** | 3.3V | I²C at address `0x57` (to CH7035B master port) |
| 9a | CH7035B reference crystal | **27.000 MHz** crystal (+ load caps) | scaler timebase on XI/XO | — | CH7035B XI/XO |
| 10 | Controller port front-end | per port: 1× **74LVC244A** octal buffer (receive) **+** a bidirectional path on 2 lines (~4.7kΩ pull-ups to 5V + open-drain pull-down); **shared: 1× `SN74AHCT125` (5V-powered) driving both ports' SELECT**. PS/2 lines: 4.7kΩ pull-up to 5V + 1kΩ series into the LVC receiver + **BSS138 gate-driven pull-down** (drain on the 5V line, source GND, gate from oito) + ≤10pF TVS — | 244 buffers the **4 joystick-only data lines** inbound (5V→3.3V, LVC inputs 5V-tolerant at 3.3V). **SELECT is driven outbound by an `SN74AHCT125` powered at 5V**: a 3.3V LVC output cannot guarantee the ~3.5V CMOS high a 5V-powered 74HC157 requires, whereas AHCT has TTL-level inputs (V_IH 2.0V) and a ~4.9V CMOS output. The **2 PS/2-capable lines** need *bidirectional* drive for the mouse-enable command and keyboard LEDs (§9.1/§9.2), which a unidirectional 244 cannot provide | 3.3V rail, 5V-tolerant inputs | DB9 data (6/port) + SELECT → oito; 2 lines also driven low by oito |
| 11 | Debug probe MCU *(accessory, not in console)* | Raspberry Pi **RP2350B** (QFN-80, **48 GPIO**, 3× PIO @150MHz) — *RP2040 has only 30 GPIO and cannot reach the header's 36 signals* | Bus sniffing, breakpoints, instruction jamming, JTAG, USB bridge | 3.3V (powered from header) | 40-pin header; USB-C to host PC |
| 11a | Analog video buffers | **2× `THS7374`** (4-channel video amplifier, integrated reconstruction filters, **2× gain**, single-supply) — one for SCART, one for VGA (RGB + CSYNC each) | buffers the shared R-2R ladder so no destination double-loads it; 2× gain into a 75Ω series resistor gives standard **0.7 Vₚₚ into 75Ω** | 5V | analog RGB + CSYNC in/out |
| 11b | AD725 input buffer | unity-gain video buffer (triple) | the AD725 needs **~0.714 V full-scale, AC-coupled** with its own bias — a different requirement from driving a 75Ω line, so it cannot share the THS7374 outputs | 5V | ladder → AD725 |
| 11d | Analog audio line driver | **`NJM4556`-class dual audio op-amp** + 3rd-order active reconstruction filter (−3 dB @20 kHz), output coupling and mute control | turns the APU's 2× delta-sigma PWM into a real line output: 1 Vᵣₘₛ, ≤100 Ω, separately series-fed to the 3.5 mm jack and SCART audio, muted until rails/APU are up | 5V | PWM in; line-out + SCART audio |
| 11c | SCART control drivers | divider for pin 16 (fast-switch, 1–3V) + small transistor stage for pin 8 (status, 9.5–12V from the 9V input rail, signalling 4:3) | forces RGB mode and reports aspect | 5V / 9V | SCART pins 8, 16 |
| 12 | Power management | 2× buck (5V, 3.3V) + **1× LDO (1.8V)** + PLL filters + voltage-supervisor/reset IC (or a PMIC) — *the former ~1.2V LDO is deleted; the CH7035B has no such mandatory core rail* | Rail generation, power-on reset, brownout (§2.1) | 9V in | — |

Notes:

- **SRAM timing margin:** at 7.159 MHz the CPU cycle is 139.7 ns with roughly half available for the access, so a **10 ns** SRAM has enormous margin and even a **55 ns** part meets timing — stated because it widens the sourcing pool considerably. The VRAM bus runs at 21.477 MHz (46.6 ns/cycle), where a 10 ns part leaves ≈36 ns of margin.
- **The 16KB system-RAM limit is a *design* limit, not a component limit.** With a 32KB part fitted the upper half is physically present but **never decoded** — oito's `RAM_CĒ` ignores A14 — which keeps §15.1 and prog8's `ram_end=3FFF` honest. A future revision *could* enable it without a board change; that is **not** promised here.
- **Rail budget:** each SRAM draws roughly **~30 mA active / <5 mA standby**, included in the 3.3V budget alongside the probe allowance.
- The motherboard also carries R-2R resistor-ladder DACs (passive, out of scope) that convert oito's digital RGB to analog RGB, buffered per destination for SCART / DE-15 / AD725 (§7).
- Controllers themselves contain a 74HC157 multiplexer (3-button pads) powered at 5V from DB9 pin 5.
- **PS/2 keyboard/mouse adaptor *(passive accessory, not in console)*** — a wiring-only DB9↔mini-DIN-6 adaptor (no MCU), serving keyboard and mouse alike (§9.1/§9.2); on the two PS/2-capable data lines per port the console adds ~4.7kΩ pull-ups + an open-drain driver (bidirectional PS/2, for mouse-enable and keyboard LEDs).
- An earlier design used a TI TFP410 serializer for digital video; it was superseded by the CH7035B and appears only historically.

### 2.1 Power tree, reset & protection

**A single 3.3V rail was never feasible** — the design has always needed 5V (AD725, controllers) and 1.8V (oito core); the CH7035B needs 1.8V and 3.3V domains. So the board is **multi-rail**. What survives is the digital core: **CPU + oito + all SRAM/flash + glue share one 3.3V rail** (no level shifters in the CPU/memory domain — the original benefit). The extra rails serve only the analog/video/core-voltage parts, which is normal.

**Input:** 9V DC barrel jack, ≥1.5A recommended (typical board draw ~3–5W, to be confirmed by measurement/synthesis). Protection: series reverse-polarity FET (or Schottky), input fuse/PTC, TVS on the jack.

**Rails:**

| Rail | Source | Regulator | Feeds |
|---|---|---|---|
| 5V | 9V | buck | AD725 + controller ports (DB9 pin 5). **Accessory allowance: 250mA per port, 350mA total across both** (not 2× the per-port figure — simultaneous maximum draw is not a design case). Protection: **500mA polyfuse per port as the *trip* target**, distinct from the budget |
| 3.3V (main) | 5V (or 9V) | buck | oito I/O, W65C02S, system + VRAM SRAM, cartridge + boot flash, 74LVC244A, **CH7035B `VDDH`/`AVDD`/`VDDMQ`/`VDDMS`/`VDDIO`** (VDDIO = 3.3V because oito drives 3.3V RGB), glue, **plus ≤300 mA for an attached debug probe** |
| 1.8V | 3.3V | LDO | oito core; **CH7035B `DVDD`**. Sharing this rail with oito is permitted **only after noise/current/sequencing analysis** — the scaler's SDRAM interface is a switching load |
| 1.8V analog (CH7035B `AVDD_PLL`) | 1.8V via ferrite + caps | filter | CH7035B PLL — a clean supply, mirroring oito's PLL treatment |
| 1.8V analog (oito VDDA_PLL) | 1.8V via ferrite + caps | filter | oito PLL (clean supply for the pixel/core-clock PLL) |

(A single multi-output PMIC could consolidate the bucks/LDOs to save board area — an implementation option.)

**Sequencing & reset.** A dedicated **voltage-supervisor / reset controller** holds CPU RES̄, oito RES̄ **and CH7035B `RESETB`** asserted until every rail is up and stable (plus a settle delay), and re-asserts on **brownout**.

- **CH7035B requirements:** stable power for **≥20 ms before `RESETB` release**, plus a **≥100 µs** asserted pulse.
- **Ordering constraint:** the scaler self-boots from its configuration EEPROM at reset release (§7.1), so the **EEPROM MUST be powered and stable before `RESETB` is released** — otherwise it boots a blank configuration.
- **Rail order:** core 1.8V comes up before or with I/O 3.3V, per oito's requirement. oito may additionally hold its own core in reset via an internal power-on reset, but the *system* reset is driven by the supervisor.
- RES̄ is also exposed on the expansion header (§12).

**Controller-port power policy.** Typical draws: 3-button pad <5 mA, 6-button pad <10 mA, PS/2 mouse 20–50 mA, PS/2 keyboard 100–150 mA.

- **Budget:** **250 mA per port, 350 mA total** across both — simultaneous maximum draw on both ports is not a design case.
- **Protection:** a **500 mA polyfuse per port**, which is the *trip* target, not the budget. A polyfuse holds at its rating and trips above it, so the two numbers are deliberately different.
- **Connector:** the DB9 contact rating (~3 A) is never the limit; the polyfuse and the PCB trace are.
- **Short-circuit:** the polyfuse trips, that port collapses, the console keeps running, and recovery is by power-cycle. This is explicitly **not** a hot-swap-safe design.
- **Inrush:** keyboards with bulk capacitance draw a brief surge, so the 5V buck needs headroom or soft-start (bring-up item).
- **Out of scope:** backlit or hub keyboards, unpowered USB hubs, and USB-style high-power devices via passive adaptors are **not supported**.

**Thermal & protection:** ~3–5W is passively cooled (no fan); the buck regulators and CH7035B want small copper pours / thermal vias. Connector ESD protection on the controller, cartridge and AV ports; cartridge-insertion current-limit.

**Emulator note:** power/reset is board-level and does not affect emulation; captured here for BOM correctness and to retire the "all-3.3V" misconception.

---

## 3. Clocks and frame timing

| Clock | Value | Notes |
|---|---|---|
| **Master clock (oito)** | **21.47727 MHz** (= 6 × NTSC colorburst 3.579545 MHz) | PINNED. NTSC-locked so the frame rate lands cleanly near 60Hz |
| **CPU PHI2** | **master ÷ 3 = 7.15909 MHz** | PINNED. Synchronous to oito, fixed 3:1 ratio; fastest integer divisor under the W65C02S 8MHz@3.3V rating (~12% margin) |
| Dot clock, lo-res | ~5.365MHz (341 dots/line, PLL) | 256×224 active — §6.7 |
| Dot clock, hi-res | ~6.702MHz (426 dots/line, PLL) | 320×224 active — §6.7 |
| Frame rate | **60.055Hz (fixed)** | progressive 240p, never 480i; 60Hz-only worldwide — no 50Hz PAL; HDMI re-timed to 1080p60 by CH7035B — §6.7 |
| HSYNC rate | 15.734kHz (both H-modes share it) | standard NTSC 240p line rate |
| Lines per frame | 262 total, 224 active, 38 VBLANK (lines 224–261) | |
| Line duration | **1,365 master ticks = 455 CPU cycles = 63.56µs** | 1365 ÷ 3 = 455 exactly |
| Frame duration | **357,630 master ticks = 119,210 CPU cycles** | 262 × 1,365; VBLANK ≈ 51,870 ticks = 17,290 CPU cycles |
| **CH7035B reference** | **27.000 MHz** (dedicated crystal on XI/XO) | the conventional reference for this class of converter; divides cleanly to standard pixel/TMDS rates incl. 148.5MHz for 1080p60. **Deliberately independent of the 21.477MHz master** — the scaler frame-buffers and re-times anyway (§6.7), so coupling them would buy nothing and risk noise |
| AD725 subcarrier | **14.318MHz (NTSC)** | dedicated crystal to AD725 (regenerates color independent of master). *The part also supports a 17.734MHz PAL subcarrier — an unused capability of the chip, not an re8 feature (60Hz-only).* |

Emulator-relevant derived facts: **CPU runs at exactly master/3**, so 455 CPU cycles per scanline and 119,210 per frame. VBLANK ≈ 17,290 CPU cycles (~2.4ms).

**Determinism caveat.** Those figures are an exact **bus** budget, not a guaranteed instruction budget: three mechanisms **stall the CPU with RDY** and reduce the cycles actually available to code — the CPU VRAM port under contention (§6.5), OAM DMA (§5.1), and **PCM sample fetch** (§8.3, ~3–6% when four voices stream). The line/frame *timing* remains exact and deterministic; the CPU's *work per line* varies with those stalls. Cycle-exact raster code should account for them or suspend PCM (§14.2). The exact line-total/porch/sync timing and the 60.00-vs-59.94 selection are a separate video-timing item needed only for a cycle-accurate emulator; the baseline above is sufficient to run software.

---

## 4. CPU subsystem (W65C02S)

**Choice rationale.** By 2026 the W65C02S and W65C816S are the only classic-bus CPUs still in production: Z80 survives only as the bus-incompatible eZ80; 68000 only as ColdFire. The 65C816 was evaluated and rejected: its 16-bit data bus + 24-bit address bus would have pushed oito past the (then-assumed) LQFP-64 pin budget. *Note: the move to LQFP-144 (§6.3) weakens that pin-count argument — an 816's extra host lines would still fit — so the W65C02S choice now rests on the remaining reasons: a simpler 8-bit bus matching the SDK's memory model, and the fully static core that is the foundation of the debug strategy (clock to 0Hz with full state retention). Revisiting the CPU is not proposed here.* (Marketing copy calling the W65C02S "the last standalone classic-bus CPU" is inaccurate — the W65C816S is also in production; see.)

**Electrical/operating decisions:**

- Runs at 3.3V specifically so no level shifters are needed between CPU, oito, SRAM and flash (all 3.3V). 3.3V operation derates the max clock from 14MHz (5V) to **8MHz** (WDC AC characteristics).
- **Clocked at master ÷ 3 = 7.159 MHz** (§3, PINNED): synchronous to oito for determinism, ~12% below the 8MHz rating for timing margin.
- Performance at 7.16MHz: **~1.8–2.7 MIPS** — *arithmetic from cycle counts (2–4 cycles/instruction), not a benchmark*. Cross-machine comparisons are deliberately not made here.

**Signals used by the system (pin mapping):**

| Signal | Direction | Used for |
|---|---|---|
| A0–A15 | out | 64KB address space; sniffed by probe (header pins 1–16) |
| D0–D7 | bidir | data bus; **the only lines the probe drives during instruction jamming** (BE stays high); header pins 17–24 |
| PHI2 | in | system clock; probe can take over and single-cycle it |
| R/W̄ | out (tri-stated by BE) | write detect (probe uses it for ghost-port sniffing). **oito drives it read-high while bus-mastering** |
| SYNC | out | high during opcode fetch; probe breakpoint qualifier |
| RDY | **bidirectional, open-drain** | pulled low by the probe (breakpoints) and by oito (VRAM stalls, OAM DMA, PCM steals); **the CPU itself drives it low during `WAI`** — hence wired-AND with an external pull-up |
| BE | in (open-drain drivers) | pulled low by the probe or oito to tri-state the CPU off the bus; pull-up keeps buses enabled by default |
| RES̄ | in | system reset (also on debug header) |
| IRQ̄ | in | single interrupt line, driven by oito |
| NMĪ | — | **not used** (never mentioned in any conversation) |

Standard 6502 conventions apply: zero page $0000–$00FF, hardware stack $0100–$01FF, vectors at $FFFA–$FFFF (reset $FFFC/D, IRQ/BRK $FFFE/F).

**Control-line termination.** The modern W65C02S has **no internal pull-up on RDY, and RDY is bidirectional** because `WAI` drives it low. re8 has three parties on that line (CPU via WAI, oito for VRAM/OAM-DMA/PCM stalls, probe for breakpoints), so termination must be specified rather than assumed. "Unused" is a design statement, not an electrical connection — every unused input **MUST** be terminated.

| Signal | Termination |
|---|---|
| **RDY** | **open-drain, wired-AND, external ~10 kΩ pull-up to 3.3 V.** oito and the probe may only **pull low**, never drive high — this is what lets the CPU's own `WAI` pull-low coexist with them (§10 recommends `WAI`, so this is not hypothetical) |
| **BE** | external ~10 kΩ **pull-up** (buses enabled by default); oito and probe pull low. Fail-safe: an absent or unpowered probe cannot tri-state the CPU |
| **IRQ̄** | driven by oito; **pull-up** so a floating input cannot storm interrupts while oito is held in reset |
| **NMĪ** | **tied high through a pull-up** — a floating NMI is a classic intermittent-crash source |
| **SOB** | tied high (unused, must not float) |
| **RES̄** | driven by the supervisor (§2.1) with a **pull-up**, so the line is defined before the supervisor is alive |

**Implementation constraint:** oito's **RDY and BE pads are open-drain outputs**, not push-pull (recorded for the pad-ring table, §6.3).

Note: an early section of the debug-probe design referenced a "HALT̄" pin; the later, corrected design uses RDY/BE/SYNC (the W65C02S has no HALT pin). The RDY/BE/SYNC version is normative.

---

## 5. Memory map

![CPU address space, register blocks and VRAM layout](diagrams/memory-map.svg)

Canonical CPU address space (final iteration):

| Range | Size | Region | Notes |
|---|---|---|---|
| $0000–$00FF | 256B | Zero page | $0000–$001F re8 runtime reservation (§5.0); $0020–$007F prog8 compiler variables; $0080–$00FF free |
| $0100–$01FF | 256B | Hardware stack | |
| $0200–$3FFF | ~15.5KB | General RAM | flattened globals, game state. *(Address-range size; **≈14.4 KB (14,704 B) is actually available to game code** after SDK allocations — budget in.)* |
| $4000–$7FFF | 16KB window | oito register I/O space | canonical register file at $4000–$40FF (§5.1); **all unmapped space reads $00, writes ignored**; $4FFF Ghost Debug Port |
| $8000–$BFFF | 16KB | Cartridge window 1 — **bank-switchable** | driven by BANK0–BANK5 via oito mapper. Also the **save window**: while SAVE_CTRL.0 ($4081) is set this range addresses the cart's FRAM instead of ROM |
| $C000–$FFFF | 16KB | Cartridge window 2 — **fixed** | cartridge code + vectors at $FFFA–$FFFF (after boot handoff). At power-on $E000–$FFFF is overlaid per `BOOT_SRC` (internal stub → external firmware → disabled) — §11.1 |

### 5.0 Zero-page allocation

**Nothing in oito or the CPU decodes zero page** — `$0000–$00FF` is ordinary system SRAM. The source `re8.properties` comment calling `$0000–$001F` "reserved for internal chip logic" was a misnomer; it is a **software convention**: the re8 runtime and prog8 boot stub reserve these 32 bytes for fast (single-byte-address) variables, and prog8's allocator is told to start user/compiler variables at `$0020` (`zeropage_start=0020`). For an emulator this needs no special handling — it is plain RAM.

Runtime reservation `$0000–$001F` (illustrative; finalized when the library is written):

| Addr | Use |
|---|---|
| $00–$01 | IRQ dispatcher scratch |
| $02 | event/VBLANK flags (bit0 = VBLANK since last poll) |
| $03–$04 | frame counter (16-bit) |
| $05–$06 | joypad-1 / joypad-2 previous-state shadow (software edge detection) |
| $07–$09 | VRAM auto-increment pointer shadow (mirrors $4040–$4042) |
| $0A | cartridge bank shadow (mirrors $4080, write-mostly register) |
| $0B–$0F | runtime indirect-addressing pointers (ptr0, ptr1 — 2 bytes each) + RNG seed |
| $10–$13 | debug/REPL mailbox [command_id, arg0, arg1, arg2] |
| $14–$15 | **IRQ handler RAM vector** — the syslib IRQ trampoline calls through this cell (pushed return + `JMP ($14)`); `sys.set_irq()` updates it |
| $16–$1F | reserved for future runtime use |

`$0020–$007F` = prog8 compiler zero-page variables (96 bytes). `$0080–$00FF` = free zero page (128 bytes) for hand-assigned fast variables. A pure bare-metal program that does not link the re8 runtime may reclaim `$0000–$001F`.

**System RAM budget.** The compile-time overflow check (§14.1) is only meaningful if every consumer of the 16 KB is declared. Several were added after that promise was written — notably the **1 KB shadow-OAM buffer** that the shadow-OAM design makes mandatory — so the real figure is published here:

| Consumer | Size | Owner |
|---|---:|---|
| Zero page — runtime reservation ($00–$1F) | 32 B | SDK |
| Zero page — prog8 compiler variables ($20–$7F) | 96 B | compiler |
| Zero page — free for hand-assignment ($80–$FF) | 128 B | user |
| Hardware stack ($0100–$01FF) | 256 B | CPU |
| **Shadow-OAM staging buffer** | **1,024 B** | SDK *(only when `re8.sprites` is linked)* |
| Keyboard FIFO + layout state | ~64 B | SDK |
| Callback tables (input / collision / mouse) | ~64 B | SDK |
| Bank stack (8-deep) + IRQ state | ~16 B | SDK |
| ROM→RAM initialised data | variable | compiler |
| **Available to game globals/BSS** | **14,704 B ≈ 14.4 KB** | user |

- **§15.1's "≈15.5 KB usable" is corrected to ≈14.4 KB (14,704 B)** — the shadow OAM alone accounts for the difference.
- **SDK regions are declared to the build**, so the **linker/map fails on overlap** rather than silently colliding, and the memory-allocation meter (§14.3) reports against the **real remainder**, not the gross 16 KB.
- **The shadow-OAM kilobyte is reclaimed automatically** by dead-code elimination when a game never links `re8.sprites`.

### 5.1 oito register map

The window `$4000–$40FF` is the register file (low 8 bits decode the register); `$4FFF` is the deliberately-isolated Ghost Debug Port. Everything unmapped follows the single rule below. All multi-byte fields are little-endian. **R = read-only, W = write-only, R/W = both.** Unlisted addresses read **$00** and ignore writes — see the unmapped-access table below.

**Base-register width.** Every "2KB units" base register (`BG0/BG1_MAP_BASE`, `BG0/BG1_PAT_BASE`, `OAM_BASE`, `SPR_PAT_BASE`, `TEXT_MAP_BASE`) is 8-bit but VRAM is 128KB = **64 × 2KB**, so **only bits 0–5 are significant; bits 6–7 are not wired — ignored on write, read back as 0.** Bases therefore always land inside VRAM (no undefined aliasing), and hardware and emulator agree by construction. `CURSOR_TILE_LO/HI` is a **12-bit tile index** (matching the name-table/OAM index width, §6.6); its VRAM byte address is `index × 32`.

**Design conventions.** The CPU never touches VRAM or palette RAM directly — both are reached through auto-incrementing address/data *ports*. OAM (sprite attributes) and name-tables live *in* VRAM; a small dedicated **palette RAM (64×12-bit) lives inside oito** and has its own port. IRQ status bits are **write-1-to-clear**.

**Block layout ($40xx):**

| Range | Block |
|---|---|
| $4000–$400F | System / video control & status / IRQ |
| $4010–$401F | Background scroll |
| $4020–$402F | Blitter |
| $4030–$403F | Collision |
| $4040–$404F | VRAM access port |
| $4050–$405F | Palette access port |
| $4060–$406F | Sprite / OAM control |
| $4070–$407F | Input (joypads) |
| $4080–$408F | Cartridge mapper |
| $4090–$409F | Text overlay layer (§6.8) |
| $40A0–$40AF | APU audio port (16-voice APU — §8) |
| $40B0–$40BF | Mouse & hardware cursor (§9.2) |
| $40C0–$40CF | Hit-test / pick (§9.2) |
| $4FFF | Ghost Debug Port |

**System / video / IRQ ($4000–$400F):**

| Addr | Name | R/W | Bits |
|---|---|---|---|
| $4000 | VIDEO_CTRL | W | 0=screen enable · 1=resolution (0=256×224, 1=320×224) · 2=Plane A (BG0) enable · 3=sprite enable · **4 = reserved** (was "render mode"; **deleted** — the blitter writes tiles into VRAM and is not a display layer, so the bit had no defined visible effect) · 5=Plane B (BG1) enable · 6–7 reserved |
| $4001 | IRQ_ENABLE | W | 0=VBLANK · 1=collision · 2=joypad-change · 3=raster-compare · 4=blitter-done · 5–7 reserved |
| $4002 | IRQ_STATUS | R / W1C | read: pending bits (same bit order as IRQ_ENABLE). Write-1-to-clear each bit (acknowledge). **`IRQ̄ = NOT(any(IRQ_STATUS & IRQ_ENABLE))`, combinational; masked events still set status; same-cycle set beats W1C-clear** (full state machine in §10) |
| $4003 | STATUS | R / **bit3 W1C** | 0=in VBLANK · 1=in HBLANK · 2=blitter busy · **3=sprite overflow — reports the *completed* frame; set on any line where a 33rd sprite was dropped; cleared at the start of the next active frame (line 0) or by writing 1** · 4–7 reserved |
| $4004 | RASTER_CMP | W | scanline number (0–261) that raises the raster-compare IRQ (low 8 bits; bit 8 in $4005) |
| $4005 | RASTER_CMP_HI / CUR_LINE_HI | R/W | write: raster-compare bit 8. read: current scanline bit 8 |
| $4006 | CUR_LINE | R | current scanline, low 8 bits |
| $4007 | BOOT_CTRL | R/W | bits0–1 = **`BOOT_SRC`** — what occupies the $E000–$FFFF overlay: **0 = internal 2KB stub, mirrored 4×** (reset default; $FFFC/D is the stub's reset vector) · **1 = external boot-flash page** selected by BOOT_BANK · **2 = overlay disabled**, cartridge fixed bank visible · 3 = ignored. 0↔1 may be switched freely during boot (firmware validation and recovery require it); **writing 2 is one-way until RES̄**. bit2 = **`BOOT_FLASH_WE`** — boot-flash write enable; **cleared at reset**, and while 0 oito never asserts `BOOT_W̄Ē`, so no stray write can program the firmware. The updater sets it immediately before erase/program and clears it after (same idiom as `SAVE_CTRL`'s write-protect). bits3–7 reserved |
| $4008 | BOOT_BANK | R/W | bits0–3 = which **8KB page** of the external boot flash appears at $E000–$FFFF while the overlay is enabled (16 pages → 128KB; reset = 0 = resident page). Applies only while `BOOT_SRC = 1`; inert otherwise |
| $4009–$400F | reserved | | |

**Background scroll ($4010–$401F):**

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4010 | BG0_SCROLL_X_LO | W | Plane A X scroll bits 0–7 |
| $4011 | BG0_SCROLL_X_HI | W | Plane A X scroll bit 8 (9-bit, wraps over the 512px-wide map) |
| $4012 | BG0_SCROLL_Y | W | Plane A Y scroll, **8-bit** (0–255, wraps over the 256px-tall map) |
| $4013 | *reserved* | — | **Y scroll is 8-bit — there is no bit 8** (the map is 256px tall). Writes ignored, reads 0 |
| $4014 | BG0_MAP_BASE | W | Plane A name-table base, 2KB units (§6.6) |
| $4015 | BG0_PAT_BASE | W | Plane A tile pattern base, 2KB units |
| $4016–$4019 | BG1_SCROLL_* | W | Plane B X (9-bit) / Y (8-bit) scroll — same layout as $4010–$4013, with **$4019 reserved** |
| $401A | BG1_MAP_BASE | W | Plane B name-table base, 2KB units |
| $401B | BG1_PAT_BASE | W | Plane B tile pattern base, 2KB units |
| $401C–$401F | reserved | | |

**Blitter ($4020–$402F)** — operates VRAM→VRAM on the private bus (never touches the CPU bus):

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4020 | BLIT_SRC0/1/2 | W | source VRAM address, 17-bit ($4020 lo, $4021 mid, $4022 bit0=A16) |
| $4023 | BLIT_DST0/1/2 | W | destination VRAM address, 17-bit ($4023/$4024/$4025) |
| $4026 | BLIT_W | W | width (tiles or pixels — unit set by BLIT_MODE) |
| $4027 | BLIT_H | W | height |
| $4028 | BLIT_MODE | W | **bits0–1 = operation enum** (0 = copy · 1 = transparent copy, per-nibble skip of index 0 · 2 = fill · 3 = masked) · bit2 = unit (0 = tiles, 1 = pixels) · bit3 = interleave during active display (else blanking-only, §6.5) · bits4–7 reserved. *(Was an ambiguous mix of enum values and flags.)* |
| $4029 | BLIT_FILL | W | fill colour index in the **low nibble**; high nibble **ignored**; the byte written is the nibble duplicated |
| $402A | BLIT_CTRL | R/W | write 1 → start (**ignored while busy**); read bit0 = busy (mirrors STATUS.2) |
| $402B | BLIT_SRC_PITCH | W | bytes added to the source address per row (0 = contiguous) |
| $402C | BLIT_DST_PITCH | W | bytes added to the destination address per row (0 = contiguous) |
| $402D–$402F | BLIT_MASK_SRC | W | 17-bit VRAM address of the **1bpp mask** used by masked mode (1 bit/pixel, MSB = leftmost) |

**Collision ($4030–$403F):**

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4030 | COLLIDE_STATUS | R | 0=collision latched · 1=overflow (≥2 pairs since last clear) |
| $4031 | COLLIDE_A | R | first colliding sprite ID (0–127) |
| $4032 | COLLIDE_B | R | second colliding sprite ID |
| $4033 | COLLIDE_CLEAR | W | write 1 → clear latch and re-arm |

**VRAM access port ($4040–$404F) interface:**

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4040/$4041/$4042 | VRAM_ADDR0/1/2 | W | 17-bit pointer ($4042 bit0 = A16) |
| $4043 | VRAM_CTRL | W | 0=auto-increment enable · 1=direction (0=+, 1=−) · **2–4=stride select, all eight values defined: 0→1, 1→2, 2→4, 3→8, 4→32, 5→64, 6→128, 7→256** · 5–7 reserved |
| $4044 | VRAM_DATA | R/W | read or write the byte at the pointer; pointer post-increments per VRAM_CTRL. Full semantics in the note below. |

**VRAM port semantics.** This is the CPU's only path to VRAM, so its behaviour is pinned rather than sketched:

- **Stride values** as tabulated above — chosen to match the data structures: 2 = a name-table cell, 4 = one 4bpp tile row, 8 = an OAM entry, 32 = a whole tile, 128 = a name-table row (64 cells × 2 B).
- **Every successful access — read *or* write — post-increments the pointer exactly once**, after the transfer, by the selected stride and direction. Reads and writes behave identically.
- **Reads are true reads: there is no prefetch/read-buffer.** `VRAM_DATA` returns the content at the *current* pointer, not a previously latched byte. Stated explicitly because NES-style VRAM ports **do** use a read buffer, and an implementer steeped in that would otherwise guess wrong.
- **The pointer wraps modulo 128 KB (17 bits)**, consistent with the blitter and base-register arithmetic.
- **`VRAM_ADDR2` bits 1–7 are ignored** (only bit 0 is A16) and read back 0.
- **Pointer registers are latched when an access begins**, so writing them while an access is RDY-stalled **cannot redirect the in-flight transfer**; the stalled access completes at its original address.
- **Back-to-back accesses arbitrate independently** (§6.5), so a burst may stall per byte during active display.

**Palette access port ($4050–$405F)** — dedicated internal 64×12-bit palette RAM:

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4050 | PAL_INDEX | W | entry 0–63 (4 sub-palettes × 16). **Masked to 6 bits**; bits 6–7 ignored, read back 0 |
| $4051 | PAL_DATA_LO | R/W | color bits: 7–4 = G[3:0], 3–0 = B[3:0]. **Writing LO does not increment** |
| $4052 | PAL_DATA_HI | R/W | 3–0 = R[3:0]; **writing** HI post-increments PAL_INDEX (**wrapping 63 → 0**); **reading HI does not increment**. Color = R<<8 \| G<<4 \| B (12-bit 4:4:4) |

**Palette port semantics.**

- **Increment happens only on a `PAL_DATA_HI` *write*, and wraps 63 → 0**, so the LO/HI pair is the natural unit and a stray LO write cannot desynchronise the index. **Reads never increment**, so a game may read an entry back without disturbing the pointer.
- **LO and HI are independently visible:** writing LO changes G/B immediately rather than being held until HI arrives. This keeps the port stateless; the cost is one transient intermediate colour if a game separates the writes, which the SDK avoids by writing them adjacently.
- **Changes take effect at the very next pixel composited** — palette RAM is read per pixel by the compositor, not latched per line or per frame. **Mid-scanline palette swaps therefore work** (the classic trick for exceeding 64 on-screen colours); the practical limit is how many writes the CPU can issue per 455-cycle line.
- **Emulator consequence (important):** a scanline renderer **must sample palette state per pixel**, not cache it once per line — caching silently breaks raster palette effects.

**Sprite / OAM control ($4060–$406F)** — OAM lives in VRAM; fast-path DMA from CPU RAM:

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4060 | OAM_BASE | W | OAM base in VRAM, 2KB units (§6.6) |
| $4061 | OAM_DMA_SRC | W | **1KB block number** in bits 0–3 (0–15): source address = **`block << 10`**. Bits 4–7 ignored, read 0. All 16 values are valid, since 16KB of RAM is exactly sixteen 1KB blocks. Writing this register **triggers** the OAM DMA burst CPU-RAM → VRAM OAM |
| $4062 | OAM_DMA_CTRL | R/W | read bit0 = DMA busy |
| $4063 | SPR_PAT_BASE | W | sprite tile pattern base, 2KB units |
| $4064 | OAM_DMA_LEN | W | transfer length in **8-byte OAM entries**: 0 = all 128; 1–128 = that many; **129–255 clamp to 128** |
| $4065 | OAM_DMA_OFS | W | **starting OAM entry index (0–127)** for the transfer; source and destination advance together, so the burst copies `LEN` entries from `src_block + OFS×8` into `OAM + OFS×8`. `OFS+LEN` past entry 127 **wraps within OAM** |
| $4066–$406F | reserved | | |

**Input ($4070–$407F)** — pad state latched inside oito (§9); active-high (1 = pressed):

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4070 | JOYPAD_1 | R | 0=Up 1=Down 2=Left 3=Right 4=A 5=B 6=C 7=Start |
| $4071 | JOYPAD_1_EXT | R | 0=X 1=Y 2=Z 3=Mode (6-button pads) · 4–7 reserved |
| $4072 | JOYPAD_2 | R | as JOYPAD_1, port 2 |
| $4073 | JOYPAD_2_EXT | R | as JOYPAD_1_EXT, port 2 |
| $4074 | INPUT_STATUS | R/W1C | 0=port1 changed · 1=port2 changed · 2=keyboard scan-code available (§9.1) · 3=**mouse event** (move, button change or wheel — read MOUSE_STATUS $40B0 to distinguish; §9.2) · 4–7 reserved. Write-1-to-clear. All four are **always latched here** (so any source can be polled); which of them actually raise the input-change IRQ (IRQ_STATUS bit 2) is selected by `INPUT_IRQ_MASK` |
| $407C | PORT_MODE | R/W | bits0–1 = port 1 mode, bits2–3 = port 2 mode: **0 = joystick (reset default), 1 = PS/2**, 2–3 reserved. **oito's open-drain PS/2 transmitters are released only in PS/2 mode** — the non-circular form of the joystick-safety invariant. Set by boot firmware (persisted in boot flash) or by the SDK |
| $407B | INPUT_IRQ_MASK | W | per-source IRQ enable, same bit order as INPUT_STATUS (0=port1 · 1=port2 · 2=keyboard · 3=mouse). Reset 0 = poll-only. Lets a game take joypad IRQs but poll the mouse each frame instead of being interrupted at its 40–200Hz report rate — **without** hiding the cursor, since display enable (`CURSOR_CTRL`.0) and interrupt enable are deliberately separate concerns |
| $4075 | KBD_STATUS | R | 0=keyboard present · 1=scan-code available (FIFO non-empty) · **2=FIFO overflow (sticky, write 1 to clear)** · 3=keyboard on port 2 (else port 1) · **4=`PORT_HINT` port 1, 5=`PORT_HINT` port 2** — a valid unsolicited PS/2 frame (e.g. BAT `$AA`) was received while the port is still in joystick mode, i.e. a PS/2 device may be attached; receive-only, nothing is ever driven · 6–7 reserved |
| $4076 | KBD_SCAN | R | pop next raw Set-2 make/break byte from the **16-byte FIFO** (0 if empty); reading advances it. On overflow **new bytes are dropped** (never overwriting a partially-consumed sequence) and `KBD_STATUS`.2 sets |
| $4077 | KBD_MODS | R | live modifiers/locks: 0=Shift · 1=Ctrl · 2=Alt · 3=CapsLock · 4=NumLock |
| $4078 | KBD_CTRL | W | 0=keyboard enable · 1=key→joypad passthrough enable · 2=passthrough target (0=player 1, 1=player 2) · 3–7 reserved |
| $4079 | KBD_MAP_IDX | W | key→joypad map slot: **bits0–6 = scan code, bit7 = `E0` extended prefix** → **256 slots** covering plain *and* extended codes. Without the flag, `E0 4B` (right arrow) and `4B` would collide — and the arrow keys are precisely what the injection maps. Firmware loads defaults at boot |
| $407A | KBD_MAP_VAL | R/W | joypad assignment for the selected slot: **bits0–3 = bit index (0–7), bit4 = target `_EXT` register** (so X/Y/Z/Mode are reachable); **$00 = unmapped** |

**Cartridge mapper ($4080–$408F):**

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4080 | BANK_SELECT | R/W | 6-bit bank (0–63) for the $8000–$BFFF window. *(Moved from gen-C's $4020; the SDK hides the address, and `extsub` codegen must emit `STA $4080`.)* |
| $4082 | CART_CONFIG_BANKS | R/W | bits0–2 = **bank-count log2** (0–6 → 1…64 × 16KB); bits3–6 reserved; bit7 = lock status (read-only mirror of `CART_LOCK`). Programmed by boot firmware from header $16. Reset 0 = a 1-bank/16KB cartridge |
| $4083 | CART_CONFIG_SAVE | R/W | bit0 = has-save · bits1–2 = save type · bits3–5 = save-size code — the header $17 values, loaded by boot firmware. `SAVE_CTRL` is honoured only when bit0 is set |
| $4084 | CART_LOCK | W | write **$A5** once → `CART_CONFIG_BANKS`/`CART_CONFIG_SAVE` become **read-only until RES̄**. Boot firmware locks them before the cartridge handoff, so a game cannot restate its own geometry |
| $4081 | SAVE_CTRL | R/W | 0 = save-window enable (accesses to $8000–$BFFF assert SAVE_CĒ instead of ROM_CĒ — §11.4) · 1 = write-protect (reset = 1) · 2–3 = size code (mirrors header $17) · 4–7 reserved. Honoured only when `CART_CONFIG_SAVE`.0 (has-save) is set — oito learns that bit from firmware, not from the header |

**Text overlay ($4090–$409F)** — the top-priority character layer (§6.8); the char map lives in VRAM, glyphs in on-die font RAM reached through an indirect font port:

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4090 | TEXT_CTRL | W | 0=layer enable · 1=narrow (0=8×8/40-col, 1=4×8/80-col) · 2=font_sel (0=default bank, 1=cart bank) · 3=blink enable · 4=caret enable · **5–6=sub-palette select (0–3)** · 7 reserved |
| $4091 | TEXT_MAP_BASE | W | char-map base in VRAM, 2KB units; the map is a fixed **80×28 grid, 160-byte row stride, 4,480 B total** in every mode |
| $4092 | TEXT_SCROLL_X | W | whole-plane fine X offset (pixels) |
| $4093 | TEXT_SCROLL_Y | W | whole-plane fine Y offset (pixels) |
| $4094 | TEXT_CARET_X | W | hardware **caret** cell column (text layer; distinct from the mouse CURSOR_* block) |
| $4095 | TEXT_CARET_Y | W | hardware caret cell row |
| $4096 | FONT_ADDR_LO | W | font-RAM address bits 0–7 |
| $4097 | FONT_ADDR_HI | W | bits0–3 = font-RAM address bits 8–11 (**3KB bank**: $000–$7FF = 8×8 set, $800–$BFF = 4×8 set) · bits4–6 reserved · **bit7 = write-bank select: 0 = default bank 0, 1 = cart bank 1** — independent of `TEXT_CTRL.font_sel`, which selects the *display* bank. **Bank-0 writes are honoured only while the boot overlay is active (`BOOT_SRC ≠ 2`)**; after handoff they are silently ignored |
| $4098 | FONT_DATA | W | write glyph byte at [FONT_ADDR]; auto-increments (upload cart font from cart ROM) |

**Mouse & hardware cursor ($40B0–$40BF)** — §9.2; oito accumulates position from PS/2 deltas and renders the cursor; the game reads state + sets the cursor graphic:

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $40B0 | MOUSE_STATUS | R | 0=mouse present · 1=moved · 2=button changed · 3=wheel moved — **bits 1–3 clear on a read of *this* register**, not on X/Y/button reads · 4–7 reserved |
| $40B1 | MOUSE_X_LO | R | cursor X (at hotspot), bits 0–7. **Reading this latches X_HI and Y into a shadow**, so LO→HI→Y always returns one coherent position |
| $40B2 | MOUSE_X_HI | R | cursor X bit 8 (0–319) |
| $40B3 | MOUSE_Y | R | cursor Y (0–223) |
| $40B4 | MOUSE_BUTTONS | R | 0=Left · 1=Right · 2=Middle · 3=btn4 · 4=btn5 |
| $40B5 | MOUSE_WHEEL | R | signed wheel delta accumulator, **saturating at ±127**; **clears on read** |
| $40B6 | CURSOR_CTRL | W | 0=cursor enable · 1=size (0=8×8, 1=16×16) · 2–3=sub-palette · 4–5=pointer source (0=auto: mouse-if-present else D-pad fallback · 1=mouse only · 2=D-pad fallback only · 3=off) · 6=bounds enable · 7=fallback player (0=P1, 1=P2) |
| $40B7 | CURSOR_TILE_LO | W | cursor pattern **tile index** bits 0–7 (VRAM byte address = index × 32) |
| $40B8 | CURSOR_TILE_HI | W | tile index bits 8–11 (**12-bit index**, as name-table/OAM); bits 4–7 ignored. **In 16×16 mode the index addresses the first of four consecutive tiles and its low 2 bits are ignored** (quad must be 4-aligned) |
| $40B9 | CURSOR_HOTSPOT_X | W | hotspot pixel within tile (0–15) |
| $40BA | CURSOR_HOTSPOT_Y | W | hotspot pixel within tile (0–15) |
| $40BB | CURSOR_SCALE | W | velocity/sensitivity, **4.4 fixed-point** (1.0 = $10; 0 is treated as 1.0); **bit 7 = acceleration enable** (|delta| > 4 doubles the scaled result). Fractional remainders persist between packets |
| $40BC | CURSOR_BOUND_SEL | W | bits0–2 select the bounds field: **0=X0_LO · 1=X0_HI (bit 8) · 2=Y0 · 3=X1_LO · 4=X1_HI (bit 8) · 5=Y1**; 6–7 unused. Six fields give real 9-bit X without new addresses |
| $40BD | CURSOR_BOUND_VAL | W | value written to the field selected by CURSOR_BOUND_SEL. **Bounds are inclusive**; an invalid rectangle (X1 < X0 or Y1 < Y0) **disables clamping** rather than trapping the cursor |

**Hit-test / pick ($40C0–$40CF)** — §9.2; oito samples the compositor at the cursor hotspot (or PICK_X/Y) once per frame and latches what's under the pointer (cursor/text layers excluded):

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $40C0 | HIT_STATUS | R | 0=sprite under point · 1=plane A opaque · 2=plane B opaque · **3–4 = visible winner (0=backdrop, 1=plane B, 2=plane A, 3=sprite)** · **5=sample valid — set when the raster passes the pick point, cleared at the start of each frame** · 6–7 reserved |
| $40C1 | HIT_SPRITE | R | topmost opaque sprite index under point (0–127; 0xFF = none) |
| $40C2 | HIT_A_COL | R | plane A name-table column under point (0–63; scroll/wrap applied) |
| $40C3 | HIT_A_ROW | R | plane A name-table row (0–31) |
| $40C4 | HIT_A_TILE | R | plane A tile ID **bits 0–7** (high nibble in HIT_TILE_HI) |
| $40C5 | HIT_B_COL | R | plane B column under point |
| $40C6 | HIT_B_ROW | R | plane B row |
| $40C7 | HIT_B_TILE | R | plane B tile ID **bits 0–7** (high nibble in HIT_TILE_HI) |
| $40C8 | PICK_CTRL | W | 0=pick source (0=follow cursor hotspot, 1=use PICK_X/Y) · 1–7 reserved |
| $40C9 | PICK_X_LO | W | probe X bits 0–7 (when PICK_CTRL.0=1) |
| $40CA | PICK_X_HI | W | probe X bit 8 |
| $40CB | PICK_Y | W | probe Y (0–223) |
| $40CC | HIT_TILE_HI | R | high nibbles of both hit tile IDs — bits0–3 = plane A tile[11:8], bits4–7 = plane B tile[11:8]. With HIT_A_TILE/HIT_B_TILE this reports the full **12-bit** index |

**APU — audio port ($40A0–$40AF)** — the 16-voice APU (§8) is reached through an indirect port into an internal 16-bit-addressed register file + wave RAM; the CPU-visible footprint is tiny:

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $40A0 | AUDIO_ADDR_LO | W | internal APU address bits 0–7 |
| $40A1 | AUDIO_ADDR_HI | W | internal APU address bits 8–15 |
| $40A2 | AUDIO_DATA | R/W | read/write internal register or wave RAM at [AUDIO_ADDR]; auto-increments per AUDIO_CTRL |
| $40A3 | AUDIO_CTRL | W | 0 = auto-increment enable · 1 = APU master enable · 2–7 reserved |
| $40A4 | AUDIO_STATUS | R | 0 = any PCM DMA busy · 1–7 reserved |

**Ghost Debug Port:**

| Addr | Name | R/W | Notes |
|---|---|---|---|
| $4FFF | GHOST_LOG | W | write-only; no storage; 4 CPU cycles per write; snooped by probe/emulator; inert otherwise (reads $00; a write with no probe/emulator attached has no effect) |

**Unmapped reads & writes.** One rule, no open bus, no mirroring:

| Range / case | Read returns | Write |
|---|---|---|
| Unlisted register inside `$4000–$40FF` | **$00** | ignored |
| Read of a **write-only** register | **$00** | — |
| `$4100–$4FFE` | **$00** | ignored |
| `$4FFF` (Ghost Debug Port) | **$00** | consumed by probe/emulator (§13) |
| `$5000–$7FFF` | **$00** | ignored |

**Rationale.** Open bus (returning the last value on the data bus) is period-authentic but *timing-dependent*, and is historically the largest single source of emulator divergence on comparable systems; oito is synchronous and can simply drive **$00**, which is free to implement, deterministic, and trivially conformance-testable. Mirroring the register file across `$5000–$7FFF` was also rejected: it would invite games to depend on aliases and permanently constrain register-space expansion.

**Consequence.** A write-only register **cannot be read back**, so software must shadow any value it needs to read-modify-write. The runtime already keeps ZP shadows for `BANK_SELECT` and the VRAM pointer (§5.0), and the SDK does the same for `VIDEO_CTRL`.

**Reset state.** All registers clear to 0 at RES̄ **with one non-zero exception: `SAVE_CTRL`.1 = 1** (save write-protect engaged — §11.4). Two zero values are load-bearing rather than incidental and are called out for clarity: `BOOT_CTRL.BOOT_SRC` = 0 selects the internal boot stub and `BOOT_CTRL.BOOT_FLASH_WE` = 0 disables boot-flash writes. *(`CURSOR_CTRL` source = 0 was previously listed as an "exception" although 0 is the general reset value — corrected.)* Everything else is zero: screen off, all IRQs disabled and clear, blitter idle, scroll 0, bank 0, BOOT_BANK 0, cartridge geometry unprogrammed (`CART_CONFIG_*` = 0, unlocked), save window closed, boot-flash writes disabled (`BOOT_FLASH_WE`=0), PSG muted, text and cursor layers off. The boot code must enable video, program the palette, load VRAM, and enable IRQs before anything is displayed.

---

## 6. oito (custom ASIC)

### 6.1 Functions

oito integrates, on one 130nm die:

1. **Video Display Processor** — hybrid architecture:
 - *Tile-based line renderer* (NES/Genesis lineage): 8×8 tiles, tile grids 32×28 (lo-res) / 40×28 (hi-res); **two independent background planes** (Plane A / Plane B), each a 64×32-cell name-table (512×256px) with pixel-perfect scrolling (9-bit X, 8-bit Y). Full data formats, plane priority and VRAM layout are in §6.6.
 - *Mini-blitter*: writes raw pixels into a "Dynamic Tile Pool" region of VRAM, **sharing the single private VRAM bus at priority 2** (behind display fetch — §6.5; it is not a separate bus); throughput **≥1,000 tiles/frame interleaved (≥350 blanking-only)** under the §6.5 benchmark workload; a full 320×224 background is 1,120 tiles, so a whole-screen redraw per frame is possible **only under the §6.5 benchmark workload**, and sits just above the ≥1,000 floor.
2. **Sprites** — 128 hardware-tracked sprites, **up to 32 per scanline**, evaluated from an on-die shadow OAM with a line-buffer cache. Within that per-line budget rendering is flicker-free; the **33rd and beyond are dropped for that line** — "zero flicker" is a property of staying inside the budget, not an unconditional guarantee.
3. **Hardware collision** — compares opaque sprite pixels during line rendering (index 0 ignored); on overlap latches both sprite IDs into COLLIDE_A/B and asserts IRQ. Latch/overflow/priority semantics are defined in §6.6.
4. **Color** — 4-bit indexed pixels; 12-bit master palette (4:4:4 = 4,096 colors); 4 sub-palettes × 16 colors = 64 simultaneous; palettes 0–1 backgrounds, 2–3 sprites/blitter; color 0 transparent.
5. **APU** — a 16-voice audio unit (4 enhanced PSG + 8 wavetable + 4 PCM), full detail in §8; outputs (a) dual high-speed PWM lines (stereo) for the analog path and (b) I²S digital audio (+MCLK) to the S/PDIF transmitter and an optional on-board DAC — **not** to the CH7035B, whose audio inputs are unconnected.
6. **Cartridge mapper** — a **console-side fixed-plus-switchable 16KB mapper**: the bank register drives BANK0–BANK5 (64 × 16KB = 1MB addressable), swapping the $8000–$BFFF window in under a clock cycle while $C000–$FFFF stays fixed. *Banking model resembles **UxROM** (fixed + switchable PRG window); it implements **none** of MMC3's PRG modes, CHR banking, scanline IRQ or serial write protocol — raster interrupts come from the VDP's `RASTER_CMP` instead (§5.1). The distinctive choice is that banking lives in the **console**, not the cartridge, which is why carts are one chip.*
7. **Address decoding / glue** — decodes the $4000+ I/O window; drives the DB9 SELECT lines and reads the (always-enabled 74LVC244A-translated) controller data directly (§9).
8. **JTAG** — boundary scan into VDP internals (palette state, line-buffer flags, blitter status), independent of the CPU-side debug path. (Standard IEEE 1149.1 boundary scan only exposes I/O-cell state; reading internal registers requires custom JTAG instructions/data registers — a debug TAP — that were never specified. See.)

### 6.2 Video output bus (all-digital rule)

oito never produces analog video. It outputs:

- 12-bit parallel digital RGB: R[3:0], G[3:0], B[3:0]
- HSYNC, VSYNC (both **active-low**), and chip-generated **CSYNC = HSYNC XNOR VSYNC** = `NOT(HSYNC XOR VSYNC)`, **active-low**. With active-low inputs this is the standard formulation — horizontal pulses invert during vertical sync, which is what CRTs expect; the previously written "XNOR/AND combination" named two mutually exclusive gates and the AND form is simply wrong for active-low signals. Because SCART pin 20 and the VGA path need CSYNC too, generating it once in oito serves **three** outputs, and every consumer sees an identical waveform.
- **DE (data enable)** — marks the active rectangle for the CH7035B
- pixel clock (to CH7035B path)

Rationale: NTSC/PAL subcarrier generation on unproven low-volume silicon was judged too risky (an off-by-fraction error yields rolling B&W pictures); analog encoding is delegated to the AD725 (a proven, in-production encoder).

### 6.3 Pin budget — LQFP-144

The original LQFP-64 tally was unbuildable. The 64-pin package is abandoned; oito targets **LQFP-144** (0.5mm pitch, 20×20mm, standard OSAT part) on a **custom pad ring** (no Efabless Caravel harness — see §6.4). The complete signal budget, counting every interface the design actually requires:

| Interface | Signals | Pins |
|---|---|---:|
| 6502 host bus | A0–A15 (16, **bidirectional** — oito drives them when bus-mastering, §8.3), D0–D7 (8, bidir), PHI2, **R/W̄ (bidirectional** — BE tri-states the CPU's RWB too, so oito must drive read-high during steals**)**, IRQ̄, **RDY**, **BE** | 29 |
| Private VRAM bus (128KB, **8-bit data**) | VA0–VA16 (17), VD0–VD7 (8), /CE, /OE, /WE | 28 |
| **CPU-bus memory control** (oito is the address decoder, §6.1) | RAM_CĒ, RAM_ŌĒ, RAM_W̄Ē (16KB system SRAM), BOOT_CĒ, BOOT_ŌĒ, **BOOT_W̄Ē** (boot flash program/erase) | 6 |
| Video output | RGB 4:4:4 (12), HSYNC, VSYNC, CSYNC, **DE**, PCLK | 17 |
| Audio output | PWM L/R (2), I²S BCLK/LRCLK/SDATA + **MCLK** (4) | 6 |
| Cartridge mapper | BANK0–BANK5 (6), ROM_CĒ, **SAVE_CĒ** (§11.4) | 8 |
| Controllers (data into oito) | 2 ports × (6 data + 1 SELECT) | 14 |
| Clock + reset | XIN, XOUT, RES̄ | 3 |
| JTAG + debug | TCK, TMS, TDI, TDO, DBḠ (probe debug-request; §13) | 5 |
| **Signal subtotal** | | **116** |
| Power / ground (derivation below) | I/O VDD/VSS pairs (~8), core VDD/VSS (~2 pairs), PLL VDDA/VSSA (1 isolated pair) | **~18–22** |
| **Total** | | **~134–138** (of 144) |

**6–10 pins spare** — adequate for ECO headroom, **not** room for another subsystem.

**This is a signal budget, not a sign-off pinout.** It answers one question — *does the design fit LQFP-144?* — and the answer is yes. It is **not** a pad-ring specification. Power/ground is *derived*, not measured: **≥1 VDD/VSS pair per ~8 simultaneously-switching outputs** (~60 outputs → ~8 I/O pairs), plus separate **core** pairs, plus an **isolated PLL VDDA/VSSA** pair behind its own ferrite. The true count depends on the foundry I/O cell library, ESD clamp strategy, SSO current, bond-wire inductance and lead assignment — none of which are available until the fab route of §6.4 is engaged.

**Owed before tapeout (deliverable, not an estimate):** a complete **144-pin table** giving, per pin — number, name, **direction in every bus-ownership state** (normal / oito bus-master / probe bus-master / debug), **pad type** (open-drain for RDY and BE), drive class, I/O bank supply, corner cells, no-connects, and the exposed-pad decision. *(This is the reconciled count.)*

**Key resolutions captured here:**

- **VRAM is 8-bit data + 17 address = a real 128KB** (2¹⁷ × 8 bits). The earlier 4-bit "nibble-wide" bus is dropped — it addressed only 64KB and halved blitter bandwidth.
- **Controllers are read into oito** (6 data + 1 SELECT per port), so the joypad register.
- **PLL assumed** to derive PCLK (5.37/6.71MHz) and the render-core clock from one crystal (XIN/XOUT), hence the analog PLL supply pair.

### 6.4 Production strategy (context)

RTL synthesized with open-source OpenLane against the open SkyWater 130nm PDK. **The Efabless Caravel harness / chipIgnite base flow is abandoned** (decision 2026-07): its ~38 user I/O cannot carry oito's **116 signal pins** (§6.3), its base shuttle delivers ~100 QFN prototypes rather than a low-thousands LQFP-144 supply, and its RISC-V management core is dead weight in this console. oito therefore needs a **custom pad ring and its own LQFP-144 package**, taped out on SKY130 as a full-custom (bring-your-own-pad-ring) project — through a commercial MPW/fab engagement rather than the stock Caravel wrapper.

*Open:* which specific full-custom SKY130 route/foundry/shuttle, and its real NRE, per-unit cost and deliverable quantity. The earlier Caravel-based figures (~$115K NRE, ~$4.50/unit at 5K, 1,000–5,000 parts/run) are **now stale** — a custom pad ring + LQFP-144 raises NRE and per-unit cost, to be re-quoted (economics is out of scope for this spec).

### 6.5 VRAM bus arbitration & bandwidth

![Pixel priority ladder and VRAM bus arbitration](diagrams/compositor-arbitration.svg)

The single 8-bit VRAM bus (VA0–16, VD0–7, 10 ns SRAM) has three masters. This section defines who wins, when the CPU can touch VRAM, and the resulting bandwidth — the last emulator-blocking unknown in the graphics path.

**Bus clock & budget.** The VRAM bus runs at the oito master clock (**21.47727 MHz, 1 byte-access per cycle**). Per frame that is **357,630 accesses** (262 lines × 1,365 cycles); per scanline **1,365**. At lo-res there are ~4 master cycles per output pixel (~3.2 at hi-res), and display fetch needs well under one access per pixel on average — so **active display leaves spare VRAM cycles**, and blanking lines are entirely free. (Note the CPU runs at master ÷ 3, so 1 CPU cycle = 3 VRAM-bus cycles.)

**Masters & fixed priority** (highest first):

1. **Display fetch** — the line renderer reading name-tables, tile rows, sprite patterns and OAM to fill the line buffer. Always wins; the picture is never corrupted by contention.
2. **Blitter** — VRAM→VRAM. Two modes, selected by `BLIT_MODE` bit 4:
 - *Blanking-only* (default): runs during HBLANK + VBLANK only → **≥350 tiles/frame** guaranteed (benchmark below).
 - *Interleaved*: additionally steals the spare VRAM cycles during active display → **≥1,000 tiles/frame** guaranteed (benchmark below).
3. **CPU VRAM port** (`VRAM_DATA` $4044, and the `OAM_DMA` burst) — lowest priority.

**CPU access rule.** The CPU may read/write `VRAM_DATA` **at any time**, but oito grants it only on a free VRAM cycle. If the bus is busy, oito **stalls the CPU by pulling RDY low** until a slot opens (the W65C02S honors RDY on both reads and writes). During HBLANK/VBLANK the grant is immediate; during active display the stall is bounded by the display fetch in progress (exact counts are a Tier 2 refinement, §14.5). This replaces the NES-style "VRAM only in VBLANK" limitation — access is always legal, just occasionally slowed. *(RDY is shared with the debug probe and with the CPU's own `WAI`; all three are wired-AND open-drain with an external pull-up.)* The `OAM_DMA` ($4061) is a CPU-stalling burst (128 entries copied CPU-RAM→VRAM) best issued in VBLANK.

**Blitter operational definition.** The register list alone left eleven externally-visible behaviours undefined; this is the reference implementation.

```
blit: # all VRAM addresses are 17-bit, wrapping mod 128KB
 if BLIT_W == 0 or BLIT_H == 0: return # zero means NO-OP (not 256)
 unit_bytes = 32 if unit==tiles else 1 # tile = 32B; pixel unit = one nibble
 src = BLIT_SRC ; dst = BLIT_DST ; msk = BLIT_MASK_SRC
 for row in 0.. BLIT_H-1: # rows ascend; bytes within a row ascend
 s = src ; d = dst ; m = msk
 for i in 0.. (BLIT_W * unit_bytes) - 1:
 match op:
 copy: write(d, read(s))
 transparent: b = read(s) # per-NIBBLE test
 hi = (b>>4) ; lo = b & 15
 o = read(d)
 if hi != 0: o = (o & 0x0F) | (hi<<4)
 if lo != 0: o = (o & 0xF0) | lo
 write(d, o)
 fill: write(d, (BLIT_FILL & 15) * 0x11) # nibble duplicated
 masked: apply per-pixel using 1bpp mask bits from m, MSB = leftmost
 s += 1 ; d += 1
 src += BLIT_W*unit_bytes + BLIT_SRC_PITCH
 dst += BLIT_W*unit_bytes + BLIT_DST_PITCH
 msk +=... # mask advances 1 bit per pixel
 STATUS.2 = 0 ; raise blitter-done IRQ # latches on the final byte write
```

- **Nibble order:** high nibble = left pixel (as §6.6). An **odd start-X or odd width performs a read-modify-write** on the boundary byte so the untouched nibble is preserved.
- **Overlap:** the copy is strictly **ascending**, so overlapping regions with `dst > src` corrupt — the caller's responsibility, exactly as period blitters behaved.
- **Busy semantics:** a start while busy is **ignored**; register writes while busy are **ignored**. `BLIT_CTRL`.0 and `STATUS`.2 both read busy; the **blitter-done IRQ latches on the cycle the final byte is written**.
- **Timing:** consumption follows the bandwidth model below. Since software can observe the blitter only through busy/IRQ, an emulator may complete a blit instantly and then set done, or model per-line consumption — both must produce identical visible results.

**Shadow OAM.** oito keeps a **1 KB on-die copy of OAM**. Per-line sprite evaluation (§6.6) scans that internal copy, so **sprite evaluation costs zero VRAM accesses**; only the *pattern rows* of the ≤32 winning sprites are fetched from VRAM. This is standard VDP practice (the NES copies OAM internally; the Genesis caches the sprite list) and removes the largest, most variable term in the budget — a naive per-line scan of 128 VRAM entries would cost 57 K–229 K accesses/frame by itself.

- **Snapshot event: at the start of line 224**, the first VBLANK line, oito copies the 1 KB VRAM OAM into the on-die shadow. That is the single named event; "once per frame during VBLANK" was too vague to implement.
- **Sprite evaluation for every visible line of frame N uses the shadow captured at line 224 of frame N−1.** A VRAM-port OAM write therefore lands on the **next** frame — which is precisely what "next frame" meant.
- **OAM DMA writes both** — CPU RAM into the VRAM OAM *and* into the shadow in the same pass — so its effect is visible on **all lines rendered after the burst completes**, not on lines already drawn. (The earlier "takes effect on the current frame" was too broad.) The dual write is why the ~683-cycle cost in §6.6 counts one read and one write per byte.
- **Consequence, documented rather than discovered:** a **mid-frame DMA tears** — sprites above the raster line show old positions, below show new. This is why the SDK issues OAM DMA in VBLANK.
- **Emulator rule:** schedule the snapshot at line 224 and apply DMA effects at the cycle the burst completes; both are ordinary events in the scanline loop.
- **Semantic consequence:** OAM edits made through the VRAM port take effect **on the next frame**, not mid-frame — the classic shadow-OAM behaviour, and precisely why OAM DMA exists. Emulators **MUST** model this one-frame latency.

**Bandwidth.** Per-frame budget at 320×224, two planes, text layer on, against **357,630** accesses:

| Consumer | Accesses/frame |
|---|---:|
| BG planes A + B (name-table + tile rows) | ~110 K |
| Sprite patterns (typical 8–16 px sprites) | ~29–57 K |
| Text overlay (≤80 codes + attributes per line) | ~36 K |
| Sprite evaluation / OAM scan | **0** (on-die shadow) |
| **Display total (typical)** | **~175–200 K (~50–56 %)** |
| **Free for blitter + CPU port** | **~157–182 K** |

**Blitter throughput — a benchmark, not a slogan.** Throughput is quoted only against a defined workload, with guaranteed minimums:

- **Benchmark transaction:** **opaque copy, tile units, 8×8 tiles (32 B), source and destination pitch 0, no odd-edge RMW**, measured with **both BG planes enabled, text layer off, zero sprites**.
- **Guaranteed minimums under that workload:** **≥350 tiles/frame blanking-only**, **≥1,000 tiles/frame interleaved** (each tile costs 64 B of bus — one read + one write per byte — against the ~157–182 K free accesses/frame above).
- **Everything else is an estimate, and the spec says so:** transparent and masked modes cost more (read-modify-write), sprite-heavy lines leave fewer spare cycles, and enabling the text layer subtracts ~36 K accesses/frame.

The correct characterisation of the margin remains **adequate, not large**. A worst-case line (both planes plus 32 full-width 32 px sprites) can approach saturation; the renderer's contract in that case is unchanged — display always wins, and the blitter/CPU simply get fewer spare cycles that line.

**Emulator guidance (Tier 1 — §14.5).** Model per scanline: run the CPU for the line's cycle budget; service `VRAM_DATA`/OAM-DMA writes immediately (optionally add a small stall model for accuracy); process queued blitter work against the per-frame or per-line bandwidth budget; render the scanline from VRAM state at that line. Cycle-exact fetch patterns and stall counts are a later cycle-accurate refinement, not needed to boot software.

**Residual (cycle-accurate pass only):** the exact per-pixel/per-tile display fetch schedule, the precise RDY stall-cycle counts, and OAM-DMA duration. These refine timing but do not block a working emulator.

### 6.6 Graphics data formats & rendering

Everything the display-fetch model (§6.5) reads from VRAM, plus the sprite overflow/priority/collision contract — the complete renderer specification.

**VRAM address arithmetic — one rule.** **Every VRAM address computation wraps modulo 128 KB (17 bits).** This is not an edge case: a **12-bit tile index alone spans the whole 128 KB** (4096 × 32 B = 131,072 B), so *any* non-zero pattern base can carry a high index past 17 bits — a game using tile 4000 with a 2 KB base is already out of range.

- The rule applies uniformly to `pattern_base + index × 32`, name-table fetches, sprite pattern fetches, the cursor tile (§9.2), the text char-map (§6.8), blitter addressing and the CPU VRAM port — previously three separate statements, now one.
- **No clamping, no "invalid tile" case, no error flag.** Wrapping is simply what the hardware does — the address bus is 17 bits wide and the high bits do not exist — so it is free, deterministic, and matches era-appropriate VDPs. Clamping would need comparison logic that buys nothing.
- **Consequence, documented rather than hidden:** base and index spaces **overlap**, so a large base plus a large index aliases back into low VRAM. That is the programmer's responsibility; the SDK's asset packer warns when a bank's tile range would wrap.

**Pixel & tile format.** 4bpp indexed. One 8×8 tile = **32 bytes** = 8 rows × 4 bytes; each byte holds two pixels, **high nibble = left pixel, low nibble = right pixel**; row 0 = top. Color index 0 = transparent. Tiles are addressed by a **12-bit index** relative to a pattern base: VRAM address = **(pattern_base + index × 32) mod 128 KB** (base registers are in 2KB units → 64 tiles/step; wrap rule).

**Palette (recap §5.1).** Internal 64×12-bit RAM = 4 sub-palettes × 16 colors. Background planes use sub-palette 0 or 1; sprites use sub-palette 2 or 3. Index 0 of any sub-palette is transparent. The **backdrop** (shown where every layer is transparent) is sub-palette 0, entry 0.

**Background: two planes.** **Plane A (BG0)** and **Plane B (BG1)**, independent, each:

- name-table **64 × 32 cells** (512 × 256 px), 2 bytes/cell = 4KB, at BGn_MAP_BASE; wraps.
- pixel-perfect scrolling: **X is 9-bit** (0–511, wrapping the 512px map width), **Y is 8-bit** (0–255, wrapping the 256px height) — Y needs no ninth bit because the map has no 257th row.
- enabled by VIDEO_CTRL bit 2 (A) / bit 5 (B); tiles from BGn_PAT_BASE.

**Name-table cell (16-bit, little-endian):**

| Bits | Field |
|---|---|
| 0–11 | tile index (relative to that plane's pattern base) |
| 12 | horizontal flip |
| 13 | vertical flip |
| 14 | sub-palette select (0 or 1) |
| 15 | priority (0 = low, 1 = high) |

**OAM DMA.** OAM is **128 × 8 = 1024 bytes**, so the DMA source is a **1KB-aligned block of CPU RAM** (`OAM_DMA_SRC` $4061 holds the block number 0–15; address = `block << 10`) — not a 256-byte page. The SDK reserves one 1KB shadow-OAM buffer and always passes it, so games never compute the address. Entry size stays 8 bytes: it is fully spent on 9-bit X/Y, a 12-bit tile index, independent W/H, flip, palette and priority, and 1KB of the 16KB RAM budget is proportionally *less* than the NES spends (256B of 2KB).

- **Cost:** a full transfer moves 1024 bytes (read + write per byte) ≈ **2,048 master cycles ≈ 683 CPU cycles ≈ 1.5 scanlines**, during which the CPU is RDY-stalled. It comfortably fits the 38-line VBLANK (17,290 CPU cycles) but is expensive mid-frame — **it SHOULD be issued in VBLANK**. Once started it is **not abortable**; `OAM_DMA_CTRL`.0 reads busy.
- **Partial updates:** `OAM_DMA_LEN` ($4064) sets the entry count and **`OAM_DMA_OFS` ($4065) sets the starting entry**, so a run anywhere in OAM can be refreshed — with a length register alone only a **prefix** could be updated, making the saving illusory for sprites at high indices. Six moved entries = 48 bytes ≈ **32 CPU cycles instead of 683, at any index**. `OFS+LEN` past entry 127 wraps within OAM; lengths 129–255 clamp to 128. Single entries can still be written through the ordinary VRAM port.

**Sprites — OAM (in VRAM at OAM_BASE, 128 entries × 8 bytes = 1KB):**

| Byte | Contents |
|---|---|
| 0 | Y[7:0] |
| 1 | X[7:0] |
| 2 | tile index [7:0] |
| 3 | [0–3] tile index [11:8] · [4] H-flip · [5] V-flip · [6] sub-palette (2 or 3) · [7] priority |
| 4 | [0] Y[8] · [1] X[8] · [2–3] width (0=8, 1=16, 2=32 px) · [4–5] height (same encoding) · [6] enable · [7] reserved |
| 5–7 | reserved (future: link/scale) |

- **Position:** X,Y are 9-bit; the display origin sits at sprite-coordinate **(32,32)** — an on-screen pixel = (X−32, Y−32) — so a maximum (32px) sprite can be positioned fully off the top/left edge.
- **Size:** width and height independently ∈ {8,16,32}px (1/2/4 tiles). A W×H-tile sprite occupies W·H consecutive tiles from its index in **row-major** order (left→right, then top→bottom).
- Sprites use sub-palette 2 or 3; index 0 transparent.

**Recommended VRAM layout** (all bases are register-relocatable):

| Region | Size | Notes |
|---|---|---|
| Plane A name-table | 4KB | |
| Plane B name-table | 4KB | |
| OAM | 1KB | |
| Tile/pattern space | ~119KB | BG + sprite patterns + the blitter's dynamic tile pool (all just tiles); up to ~3,700 distinct tiles |

Palette RAM is internal to oito, not in VRAM.

**Per-pixel priority ladder (front → back).** The topmost opaque pixel wins, tested in this fixed order:

| Level | Layer |
|---:|---|
| 1 | **hardware mouse cursor** (§9.2) — absolute top when enabled |
| 2 | **text overlay layer** (§6.8) — above all graphics and sprites |
| 3 | sprite, priority 1 |
| 4 | Plane A, priority 1 |
| 5 | Plane B, priority 1 |
| 6 | sprite, priority 0 |
| 7 | Plane A, priority 0 |
| 8 | Plane B, priority 0 |
| 9 | backdrop colour (sub-palette 0, entry 0) |

**Sprite per-line evaluation & overflow.**

- Each scanline, oito scans **its on-die shadow OAM** (§6.5 — not VRAM) index 0→127 and collects sprites whose vertical span covers that line, **up to 32**. Only the winners' pattern rows are fetched from VRAM. *(Evaluation reads the shadow snapshotted at line 224 of the previous frame, so VRAM-port OAM writes land next frame; OAM DMA updates the shadow immediately.)* The **33rd and beyond are dropped for that line** — lower OAM index always wins. `STATUS.3` sets if any line in the frame overflows and **remains readable throughout VBLANK**, clearing at the start of the next active frame (line 0) or on a write-1 — previously it cleared at VBLANK start, i.e. exactly when a game first looks at it.
- The per-line limit is **32 sprites, full stop — there is no separate per-line tile/pixel budget**; a wide sprite costs one slot like any other. (An adversarial line of 32 full-width 32px sprites may hit a pattern-fetch bandwidth ceiling pinned only in the cycle-accurate pass; the baseline renderer ignores it.)
- Where sprites overlap on a line, **lower OAM index draws on top** (sprite 0 frontmost).

**Collision.**

- A collision registers wherever **two rendered sprites both have an opaque (non-0) pixel at the same screen location** — independent of which is visually on top and independent of the background. Sprites dropped by per-line overflow do not participate on that line.
- COLLIDE_A / COLLIDE_B ($4031/2) latch the **first** colliding pair in raster order (top→bottom, left→right) since the last COLLIDE_CLEAR; COLLIDE_A = lower index, COLLIDE_B = higher. COLLIDE_STATUS.1 (overflow) sets if further *distinct* pairs collide before the clear. The collision IRQ fires on the first latch.

**Emulator note.** A standard scanline renderer suffices: per visible line, evaluate the ≤32 sprites, then compose each pixel through the priority ladder (backdrop → BG/sprite levels → text overlay §6.8 → mouse cursor §9.2 on absolute top) from VRAM + palette state, registering collisions among opaque sprite overlaps. Correct output needs no cycle accuracy; exact fetch scheduling is a Tier 2 refinement (§14.5).

### 6.7 Raster timing

![Frame and line timing for both H-modes](diagrams/raster-timing.svg)

Both H-modes share **identical line and frame timing** — only the dot clock (hence horizontal resolution) changes — so switching resolution never re-syncs the display or the CH7035B. The CPU clock and the dot clocks are independent PLL outputs from the 21.47727 MHz master, so the dot count per line is exact even though the dot clock isn't a whole divisor of the master.

**Common line & frame (both modes):**

- Line = **1,365 master ticks = 455 CPU cycles = 63.56 µs**; HSYNC rate **15.734 kHz** (standard NTSC 240p).
- Frame = **262 lines = 357,630 master ticks = 119,210 CPU cycles**; refresh **60.055 Hz**.
- Vertical: **224 active + 38 blank** (3 front porch, 3 VSYNC, 32 back porch). VBLANK = lines 224–261.

**Horizontal — lo-res (256):** dot clock ≈ **5.365 MHz**, **341 dots/line** = 256 active + 9 front porch + 25 HSYNC + 51 back porch.

**Horizontal — hi-res (320):** dot clock ≈ **6.702 MHz**, **426 dots/line** = 320 active + 14 front porch + 32 HSYNC + 60 back porch.

(Porch/sync splits are oito's canonical values; they may be fine-tuned within the fixed blanking budget without changing the line or frame rate.)

**Refresh, tolerance & compatibility.** 60.055 Hz is the native rate — an NTSC-locked 240p line count does not land on an exact 60.00/59.94 with the ÷3 CPU line. The previous claim that "every 60 Hz display tolerates it" was an untestable universal and is replaced by a specification:

- **Digital output is exact, not tolerant.** The **CH7035B frame-buffers and re-times to standard 1080p60 (60.000 Hz)**, so the sink always receives a compliant timing regardless of the input rate. This is *why* the digital path is compatible — a specification rather than a hope.
- **Cadence:** input and output differ by **0.09 %**, so the scaler repeats or drops approximately **one frame per ~1,100** (≈1 every 18 s). Stated as a number rather than "negligible".
- **Analog outputs carry the native rate, quoted as a tolerance:** **60.055 Hz ±0.01 % (+0.19 % relative to 59.94 Hz)**, line rate **15.734 kHz within ±0.1 % of NTSC**. A display either accepts that or does not; the spec no longer asserts that all do.
- **Compatibility is a test matrix, not an adjective.** Validation set: consumer NTSC CRTs, PVMs, SCART CRTs, RetroTINK/OSSC-class upscalers, and capture devices — the same equipment as the AD725 240p validation, with results recorded.

**Emulator note.** Model 262 lines × 455 CPU cycles/line; VBLANK on lines 224–261 (drives the VBLANK IRQ). Exact porch values matter only for mid-scanline raster tricks and CH7035B input modeling — the active/blank split is what the renderer needs.

### 6.8 Text overlay layer

An optional **monochrome character layer composited above both BG planes and all sprites** — **level 2** of the §6.6 priority ladder, beneath only the hardware mouse cursor (§9.2). It reuses the proven tile-plane and BG-scroll machinery; it has its own font, does not consume a BG plane, and its characters **do not count against the 128-sprite / 32-per-line budgets**. Characters cannot move independently or collide (§9 collision ignores this layer).

**Transparent by default.** The layer is a true overlay: each cell is transparent unless a glyph pixel is lit or the cell opts into an opaque background (textbox, below). When disabled (`TEXT_CTRL.enable=0`) the layer costs nothing.

**Glyphs & font RAM.** Characters are 8 pixels tall, **1bpp** (glyph pixel = on/off). oito carries **two 3 KB font-RAM banks** (6 KB total; bank 0 = system default, bank 1 = cart font). Each bank holds **both densities**:

- **8×8 set — 2 KB** (256 chars × 8 rows × 1 byte), used in 40-column mode;
- **4×8 set — 1 KB** (256 chars × 8 rows × 4 bits, **two glyph-rows packed per byte**), used in 80-column mode. A 4-pixel-wide glyph is a genuinely different bitmap, not a squeezed 8×8, so it is stored rather than derived — column-dropping an 8×8 face would mangle the letterforms.
- `FONT_ADDR` therefore spans **12 bits** (0–3071) within the selected bank; the 4×8 set begins at offset $800.
- At boot, firmware copies the **region default charset** (ISO-8859-1 base; regional builds may ship Cyrillic/Kana) from the boot flash into bank 0 — **3 KB per region** (both densities). Default font always survives, so system text (no-cart / error screens) works even mid-game. A cart font need only upload the densities it actually uses.
- A game uploads its own 256-glyph font from cartridge ROM into **bank 1** through the font port (§5.1) — selecting the write bank with `FONT_ADDR_HI` bit 7, which is **separate from the display bank** so a game may rewrite the cart font while the default is on screen — then sets `TEXT_CTRL.font_sel=1` to switch. The swap is instant and non-destructive.
- **Only firmware may write bank 0.** Bank-0 writes are accepted solely while the boot overlay is active (`BOOT_SRC ≠ 2`) and are **silently ignored after handoff**, which is what actually enforces the guarantee above that the default font always survives for system text. Without the gate, a game could overwrite bank 0 and break the no-cart/error screens.

**Glyph width — two column densities (no new video timing):**

- **40-column, 8×8** (default): 320/8 = 40 cols × 28 rows on hi-res; 32 cols on lo-res. Most legible.
- **80-column, 4×8** (`TEXT_CTRL.narrow=1`): a 4-pixel-wide glyph gives 320/4 = **80 cols × 28 rows** at the *same* dot clock — this is how the 80×25 "2000-cell screen" is reached without a 640px mode. (A true 640px 8×8 text mode would need a second ~10.7 MHz dot clock and a 640-wide path through the CH7035B/DACs — deliberately **not** implemented; it would break the §6.7 shared-raster design.)

**Placement — grid + fine scroll (not a second sprite engine):**

- **Cell grid (coarse) — fixed 80-cell stride:** a character map in VRAM, one entry per cell = char code (1 byte) + attribute (1 byte). The map is a **fixed 80 × 28 = 2,240-cell (4,480-byte)** region with a **row stride of 80 cells (160 bytes) in every mode**; narrower configurations (`cols` = 32, 40 or 64) simply use the **leftmost `cols` cells of each row** and ignore the remainder.
 - **Why fixed rather than per-mode:** a live resolution or narrow-mode switch then changes only **how many cells are displayed, never where a cell lives** — text at (col 5, row 3) occupies the same address in all four configurations, so switching mid-game never scrambles the screen or forces a re-layout. The cost is at most 4,480 B of 128 KB, partly unused in narrow modes: a trivial price for that property. *(The earlier "always cols × 28" left the stride undefined, since `cols` varies 32/40/64/80.)*
 - **No wrapping:** cells beyond `cols` are not fetched, and rows beyond 27 do not exist.
 - **Scroll sign & range:** `TEXT_SCROLL_X/Y` are **unsigned 0–255**, applied as a positive offset that shifts content **up and left** (so incrementing Y scrolls text upward — the natural direction for credits). Larger offsets simply push content off-screen.
 - **Off-screen cells are not fetched** and cost no bandwidth: fine scroll moves the sampling window, it does not wrap content.
 - Cells snap to the 8px lattice (4px in narrow mode).
- **Whole-plane fine scroll:** `TEXT_SCROLL_X/Y` apply a per-pixel offset to the **entire** text plane during compositing (same path as BG scroll, §6.2), positioning a text *block* at any exact pixel coordinate and enabling smooth credits/subtitles/tickers. It shifts all cells together; it does not move characters relative to each other.
- **Free-floating single glyphs** (a damage number, a bouncing letter) are drawn as ordinary 8×8 **sprites** from the font — a handful at most — rather than a 2000-entry per-line evaluator. re8 therefore does **not** build a character-OAM; arbitrary independent per-glyph positioning is out of scope by design.

**Attribute byte (per cell)) was not a real encoding: three bits cannot hold a 4-bit background entry *plus* inverse *plus* blink. Actual allocation, all colours drawn from the layer sub-palette (`TEXT_CTRL` bits 5–6):

| Bits | Field |
|---|---|
| 0–3 | **foreground** colour index (any of the 16 sub-palette entries) |
| 4–5 | **background** colour index — restricted to **entries 0–3** of that sub-palette |
| 6 | **opaque background** (0 = cell transparent, 1 = fill with the background entry first) |
| 7 | **blink** this cell (gated by the `TEXT_CTRL`.3 global enable) |

*Per-cell **inverse** is deliberately dropped: it is exactly "swap the two colours", which an author encodes directly by choosing fg and bg in the same byte — spending a bit on a redundant operation would have cost background range.* Four background entries is sufficient in practice (a panel colour plus a highlight for the selected row), and those entries can be *chosen* per sub-palette; foreground keeps all 16. The 2-byte cell stride is preserved — a 3-byte cell would have grown an 80×28 map from 4,480 to 6,720 bytes and broken easy addressing.

**Blink & caret timing.**

- **One global 1 Hz counter with 50 % duty** drives all blinking; its phase **resets when `TEXT_CTRL`.3 transitions 0→1**, so blink is deterministic and emulator-reproducible rather than free-running.
- A blinking cell alternates between its normal rendering and its background (transparent if attribute bit 6 = 0).
- The **hardware caret** (`TEXT_CARET_X/Y`) shares that counter and renders as a filled cell in the foreground colour — provided for REPL, dev-menu and console use, pairing with the Ghost Debug Port (§13).
- **Textbox:** a rectangular run of opaque-background cells paints a solid dialogue or menu panel *and* its text within the text plane alone — no BG tiles, no sprites — and can slide in via fine scroll.

**Cost & impact.** Grid mode's per-line fetch ≈ one BG plane's worth (≤80 char codes + attributes; font rows come from on-die font RAM, not VRAM) — counted in the §6.5 budget, where text joins *display* priority. Silicon: +1 compositor level, **+6 KB font RAM** (2 banks × 3 KB), +char-map fetch, ~9 registers. VRAM: char map is a fixed **4,480 B** (80×28) of 128 KB. **No pins, no external parts, no video-timing change.** Boot flash: **+3 KB per regional charset** (8×8 + 4×8).

**Emulator note.** A deterministic top-layer composite: per visible line, for each of the ≤80 cells on that text row, fetch the char code + attribute, index the selected font bank, and overlay the 1bpp row (honouring transparent/opaque, blink phase, and the `SCROLL_X/Y` pixel offset) after the sprite/BG composite. No cycle accuracy required.

---

## 7. Video output subsystem

**Region: 60Hz-only, single global timing.** No 50Hz PAL mode — games run full-speed worldwide and the HDMI output is region-agnostic 1080p60. Composite/S-Video use **NTSC** color (AD725 + 14.318MHz crystal); **RGB SCART, DE-15 RGBHV and HDMI are region-agnostic** (raw RGB / digital, no subcarrier) and work on any 60Hz-capable display. The only unsupported case is pure composite/S-Video into a 50Hz-only vintage PAL CRT.

One digital pipeline feeds all outputs **simultaneously** (no switching). *(The former claim that "digital fan-out costs almost zero current" is removed: it contradicted this section's own analog-buffer requirement — one source cannot drive five outputs, which is why §7's analog stage specifies three buffer paths — and was an unmeasured performance claim without a workload.)* **Analog output stage.** A single R-2R ladder cannot drive five outputs, so the buffering is specified rather than deferred (it consists of *active* parts and is therefore in scope — see the corrected scope rule in §1):

- **One R-2R ladder set (R, G, B)** is the sole source and is **never loaded directly**; each destination has its own buffer, so nothing double-loads.
- **SCART and VGA:** one **THS7374** each — 4 channels (RGB + CSYNC), integrated reconstruction filters, **2× gain**, 5V single supply; 2× gain into a 75Ω series resistor produces the standard **0.7 Vₚₚ into 75Ω**.
- **AD725:** a separate **unity-gain buffer**, because it requires **~0.714 V full-scale AC-coupled** inputs with its own bias — which is why it cannot share the THS7374 outputs.
- **SCART control:** pin **16** held at **1–3V** by a divider (forces RGB mode); pin **8** driven to **9.5–12V** from the 9V input rail via a small transistor stage (signals 4:3).
- **Filtering:** the THS7374's integrated filters suit 240p; a passive reconstruction filter follows the AD725 output.
- The analog stage runs from **5V** and is included in that rail's budget (§2.1).

| Output | Connector | Path | Notes |
|---|---|---|---|
| Composite (CVBS) | RCA | R-2R DACs → analog RGB + **oito CSYNC on the AD725's composite-sync input** (its other sync input tied to the static level per datasheet; the encoder's *internal* H/V combination is deliberately unused) → **AD725** → CVBS | vintage TVs — **AD725 is provisionally selected pending 240p validation** |
| S-Video (Y/C) | 4-pin mini-DIN | same AD725 produces Y/C simultaneously | |
| RGB SCART | Euro-SCART | R-2R DACs + CSYNC on pin 20; pin 16 held at 1–3V to force RGB mode | PVMs/EU CRTs |
| **15 kHz analog RGBHV (DE-15)** | DE-15 | buffered ladder (THS7374, §7 analog stage) → **RGB 0.7 Vₚₚ into 75Ω**, source-terminated 75Ω; separate **H and V sync on pins 13/14, active-low, 3.3V logic**. CSYNC is available on the sync pin as a build option, since oito generates it anyway — many PVMs/upscalers prefer it | **Not VGA timing** (VGA is 31.5 kHz): this is 15.734 kHz for CRTs, PVMs and upscalers, and standard PC monitors will not sync |
| Digital video | 19-pin HDMI-Type-A receptacle | 12-bit RGB (replicated to RGB-888) + syncs + pixel clock → **CH7035B** → TMDS | strict **DVI-D, video only** (no audio, no HDCP) → genuinely royalty-free; audio is separate (§8.4) |

**AD725 240p qualification.** The AD725's application material specifies **interlaced RGB at TV-standard rates** and discusses equalisation/serration in composite sync, whereas re8 feeds it **262-line progressive 240p with a plain 3-line VSYNC and no equalisation pulses** — the classic "240p is not a broadcast standard" situation. CRTs are tolerant; the *encoder* still has to lock subcarrier and vertical timing to a waveform its datasheet never promised. Two specific risks: **colour-burst insertion and subcarrier phase** across a 262-line frame (NTSC's 4-field colour sequence assumes 525-line interlace), and **vertical lock** without equalisation.

- **Status: provisionally selected, pending bench validation** — the same treatment as the CH7035B. **Go/no-go:** colour lock on 240p; correct burst insertion; stable vertical lock; acceptable output on representative CRTs **and** capture devices/upscalers (which are markedly less tolerant than CRTs, and are how most users will actually view this output).
- **Sync waveform is normative, not implied:** oito emits **negative-polarity HSYNC/VSYNC/CSYNC**, standard 240p line/frame timing per §6.7, and **deliberately omits equalisation and serration pulses** — the "non-interlaced NTSC" convention used by consoles of the era.
- **Defined fallback (a selected design):** if colour lock fails, oito emits **true interlaced 480i on the AD725 path only**, leaving 240p intact on RGB SCART, VGA and HDMI. Cost: an interlace mode in oito's timing generator, and an honest quality change — 480i instead of 240p on composite/S-Video.
- **If that is unacceptable,** select an encoder explicitly qualified for 240p.
- **Risk is contained:** this affects only the composite/S-Video path; SCART RGB, VGA and the digital output are unaffected.

### 7.1 CH7035B path (final digital-video design)

- **Why a companion chip:** 1080p60 needs a 148.5MHz pixel clock and 1.485GHz TMDS bit clock — impossible/uneconomical on the 130nm ASIC. DVI minimum pixel clock is 25MHz, so even raw 240p pass-through needs help. Candidate approaches rejected: RP2350/small-FPGA scaler (720p ceiling, RAM limits, 6-layer PCB for 1080p), plain serializers TFP410/ADV7513 (no scaling → TV compatibility risk at 240p), DisplayPort (no TV inputs), analog-only (pushes cost to user).
- **What CH7035B provides:** fixed-function display converter with integrated SDRAM frame buffer + frame-rate conversion, hardware scaler, DVI transmitter (to 1080p), DDC master for EDID, hot-plug detect, and I²S/S-PDIF audio inputs (unused here — §8.4). Few dollars, no FPGA.
- **Input-format mapping.** The CH7035B's parallel input supports **RGB-565 / RGB-666 / RGB-888** — **not** RGB-444 — so oito's 12-bit 4:4:4 bus cannot connect one-to-one. The scaler is therefore configured for **24-bit RGB-888 input**, and oito's 12 lines fan out on the PCB with **bit replication**: `R[7:4]←R[3:0]` *and* `R[3:0]←R[3:0]` (same for G and B). Replication — not zero-fill — is required so full-scale white maps $F→$FF (100%) rather than $F0 (94%, a visibly dull white); it makes the 12-bit palette land exactly on the 8-bit range with correct endpoints. Cost: **no extra parts and no oito pins** — each of the 12 oito outputs drives two scaler inputs (fan-out of 2). The **CH9904 EEPROM config must select 24-bit RGB-888 input** (Strategy A, below). *(RGB-666 with `R[3:0]→R[5:2]` + replication would also work and saves 6 traces; 888 is chosen as the cleanest mapping.)*
- **Configuration:** self-boot — CH7035B acts as I²C master (SPCM/SPDM pins) and loads a fixed config from the **CH9904 8KB I²C boot ROM at address `0x57`** at power-on (that config selects **24-bit RGB-888 input** and the fixed 1080p60 output; the image is a versioned release artefact/E6). Zero CPU involvement; video alive even if the CPU crashed; no memory-map presence. The single shipping output mode is **1080p60** (the earlier 480p/720p/1080p flip-flop is resolved: one fixed mode, no runtime switching). *(Strategy B — CPU bit-bangs the CH7035B slave port for runtime mode changes — is dropped; not worth the BIOS-ROM dependency for a fixed-output console.)*
- **Sink handshake — fixed output, no EDID dependency.** The earlier claim that the CH7035B autonomously reads EDID and "confirms 1080p60" is **withdrawn**: the public brief describes HPD as raising an **interrupt to a processor** and EDID as read **through programmed registers** — both presuppose a host, and Strategy A deliberately gives the scaler none. re8 therefore **does not depend on EDID at all**:
 - the scaler is configured once from EEPROM and drives **1080p60 unconditionally whenever powered** — legitimate for a fixed-function console, since 1080p60 is the most universally supported digital TV mode and there is nothing to negotiate;
 - **failure mode, stated plainly:** a sink that cannot accept 1080p60 shows nothing on the digital output; the remedy is the analog outputs, which is part of why re8 ships five;
 - **HPD is not acted upon** — the output never varies, so nothing needs to change on hot-plug; if the part requires HPD to gate TMDS, the EEPROM config sets it to free-run;
 - **connector-side requirements (previously missing):** the HDMI receptacle's **+5 V pin**, **DDC pull-ups**, **HPD level handling**, and **ESD protection on all TMDS pairs plus DDC/HPD**.
 **CEC is not implemented** (a fixed-function console needs no consumer-electronics control, and CEC is an HDMI feature the strict-DVI link does not carry anyway).

- **Mode-switch tracking.** Shared line/frame *timing* alone is **not** sufficient: constant HSYNC/VSYNC frequency does not tell a scaler where the active pixels are, and the two modes differ in dot clock (5.365 vs 6.703 MHz), total dots (341 vs 426) and active width. Resolution — **two dot clocks are retained (§6.7 stands) and `DE` carries the active window**:
 1. **oito outputs `DE` (data enable)** — previously missing from the video bus — marking the active rectangle explicitly in **both** modes, so the scaler locates active video by signal rather than by inference. Cost: **+1 pin**.
 2. **Both H-modes keep their native dot clock**, so **256-mode still fills the screen on analog outputs** (256 px at 5.365 MHz = 47.7 µs, identical to 320 px at 6.703 MHz). *An earlier draft of this item proposed a single fixed 426-dot container with 256-mode pillarboxed; that was withdrawn because oito drives the analog R-2R ladder from the same RGB bus, so the pillarbox would have appeared on CRT as well as HDMI — a visible product regression, not an HDMI-only cost.*
 3. **The burden therefore moves to the scaler**: the CH7035B must track two input geometries from DE without reprogramming. This is **added to the go/no-go qualification list (§16.2)** rather than assumed, since the part is already provisional. If it cannot, the line-doubling fallback (§7.1) applies (oito line-doubles to a single fixed 480p timing), which removes the dual-geometry question entirely.

- **Scaling:** nearest-neighbor/integer only (bilinear explicitly banned for pixel art). 240p → 1080p60. 240p → 1080p60: 4× integer = 1280×896 inside the 1080p raster; 5× with overscan crop = 1600×1120. Note: true integer scaling fills only a letterboxed/pillarboxed region (1280×896 inside a 1920×1080 raster), not the full frame. Whether the CH7035B actually accepts these custom input timings (256×224 / 320×224 at 5.37–6.71MHz) and performs genuine nearest-neighbor scaling is a **gated qualification item** (see "Qualification status" above; not emulator-blocking): the CH7035B input is pinned to a datasheet-supported progressive-RGB timing that oito generates, and the scaler is set to nearest-neighbor/integer (bilinear disabled). If a given part won't accept the exact micro-timing, oito pads the 240p active region into the nearest supported input raster; worst case is a mild non-integer scale, documented but acceptable.
- **Audio — NOT on the video link:** the digital output is a **strict DVI-D stream that carries no audio** (no TERC4 data islands — those are HDMI technology). Audio leaves the console on its own royalty-free paths: an **optical S/PDIF (TOSLINK)** digital jack fed by an I²S→S/PDIF transmitter, plus the analog line-out/SCART audio (§8.4). This removes the old technical contradiction — no HDMI-only mechanism (TERC4, HDCP) is emitted — though the licensing conclusion itself requires counsel.
- **Cable & connector:** the console uses a **standard HDMI Type-A receptacle, and an ordinary HDMI cable works** — DVI-D and HDMI share identical TMDS electrical signaling (the same data/clock pairs + DDC/HPD pins), so any HDMI sink displays the DVI-D stream with no adapter. HDMI's extras (TERC4 audio, InfoFrames, HDCP) are optional layers on top of the DVI-compatible base; omitting them just means the cable carries **video only** — sound comes from the optical S/PDIF or analog jack (§8.4). This is standard industry behavior (every passive DVI↔HDMI adapter relies on it), and using an HDMI *cable*/connector triggers no fee — the HDMI Adopter agreement is triggered by implementing HDMI *technology and trademarks*, not by the connector shape.
- **Licensing position.** *Engineering facts (verifiable):* the digital port emits a **DVI-compatible TMDS stream carrying video only** — **no TERC4 audio, no HDCP, no CEC, no HDMI InfoFrames** — on an HDMI-shaped receptacle labelled "Digital Video Out (DVI-D)", and the product uses **no HDMI name or logo**. DVI-D and S/PDIF are **commonly described as royalty-free**.
 *Legal position (not an engineering conclusion):* **the licensing and trademark position requires counsel and written confirmation before commercialisation.** HDMI Licensing Administrator materials treat **connectors and sources as licensed product categories**, not only trademarks and feature sets, so whether this particular DVI-on-Type-A implementation avoids every relevant claim is a specialist question. The previous categorical assertions — "license-clean", "needs no license **at any volume**" — are **withdrawn**; they were legal determinations stated with unearned confidence.
 *On comparisons:* community MiSTer boards emit real HDMI audio via an ADV7513; re8 does not. That is the factual difference — this document makes no compliance judgement about third-party products.
 *Scale-up option retained:* becoming a low-volume HDMI Adopter (≈$5K/yr + per-unit fee + compliance testing) and enabling the CH7035B's HDMI audio; not the shipping design.

---

## 8. Audio subsystem — the oito APU

The original 4-channel PSG was 8-bit-tier and badly mismatched to the VDP. It is replaced by a **16-voice hybrid APU** integrated in oito — enhanced PSG + wavetable + PCM — sized to the graphics system. It needs **no extra pins** (output is still 2× PWM + I²S) and **no external RAM** (small on-die wave RAM; PCM streams from cartridge ROM).

### 8.1 Voice complement (16 total)

| Block | Voices | Synthesis |
|---|---|---|
| **PSG** | 4 (3 pulse + 1 noise) | variable-duty pulse; 15-bit LFSR noise; per-voice ADSR envelope, frequency sweep, stereo volume |
| **Wavetable** | 8 | 32-sample × 8-bit user waveforms from on-die wave RAM; per-voice ADSR, stereo volume, pitch |
| **PCM** | 4 | 8-bit signed PCM or 4-bit IMA-ADPCM, streamed from cartridge ROM; per-voice pitch, loop, stereo volume |

All 16 voices feed an internal digital mixer → stereo → **I²S** (clean multi-bit, to the `DIT4192` S/PDIF transmitter and an optional motherboard audio DAC — not to the CH7035B) and a **2nd-order delta-sigma PWM** stereo pair at master ÷ 8 (feeding the active analog stage). Nominal output/mix rate **≈ 48 kHz (master ÷ 448 = 47.94 kHz)**.

### 8.2 Internal register file (via the $40A0 port, 16-bit internal address)

| Range | Contents |
|---|---|
| $0000–$001F | PSG voices 0–3 (8 bytes each) |
| $0020–$005F | Wavetable voices 0–7 (8 bytes each) |
| $0060–$009F | PCM voices 0–3 (16 bytes each) |
| $00A0–$00AF | globals — enumerated in §8.5 (16 voice-active flags need **two** bytes, not one) |
| $0100–$02FF | Wave RAM: 16 slots × 32 bytes (512 B) |

**PSG voice (8 bytes):** +0 period[7:0] · +1 **pulse:** [0–3] period[11:8] (**12-bit period**), [6–7] duty (12.5/25/50/75%) / **noise:** [0–2] noise rate, [3] LFSR mode (0=15-bit long, taps 0⊕1; 1=short/periodic, taps 0⊕6) · +2 L volume (5-bit) · +3 R volume (5-bit) · +4 ADSR attack[7:4]/decay[3:0] · +5 sustain-level[7:4]/release[3:0] · +6 sweep shift[2:0]/dir[3]/rate[6:4]/enable[7] · +7 key-gate[0]/enable[1]/retrigger[2].

**Wavetable voice (8 bytes):** +0 period[7:0] · +1 [0–3] period[11:8] (**12-bit**, same ÷12 tone clock) · +2 L volume · +3 R volume · +4 wave slot[3:0] (0–15 into wave RAM) · +5 ADSR attack/decay · +6 sustain/release · +7 key-gate[0]/enable[1]/loop[2].

**PCM voice (16 bytes):** +0..2 start address (**20-bit linear cartridge-ROM** byte address = the full 1MB cart space; stored in 3 bytes, **top 4 bits reserved/must-be-0**) · +3..5 loop address · +6..8 end address · +9..10 pitch (16-bit playback-rate multiplier, 1.0 = source rate) · +11 L volume · +12 R volume · +13 format[0] (0=8-bit PCM, 1=4-bit IMA-ADPCM)/loop-enable[1]/key-gate[2]/enable[3] · +14..15 **(now +13..15)** current-position readback, **20-bit**.

### 8.3 Behavior details (emulator-grade)

- **Tone clock.** Pulse and wavetable voices are clocked from a **÷12 prescaler off the master clock: 21.47727 MHz ÷ 12 = 1.7897725 MHz** — *exactly* the NES APU clock, because both derive from the same 3.579545 MHz colorburst. Using the master clock directly (as originally written) put the lowest tone at 655 Hz ≈ E5 and made bass impossible.
- **Pulse:** **12-bit** period → **freq = 1.789773 MHz / (16 × (period+1))**, giving **27.3 Hz (period 4095, below A0) to ~112 kHz (period 0)** — a full musical range with an octave of headroom below the NES. Existing NES period tables port unchanged for 11-bit values. Duty as above. **Noise:** 15-bit LFSR clocked from its own noise-rate divider (unaffected); long mode taps 0⊕1, short mode 0⊕6.
- **ADSR envelope** (all voices): 4-bit attack/decay/release **rate indices** into a 16-entry ticks-per-step table, 4-bit sustain level; advanced per output sample; key-gate starts attack / release. Exact table and semantics in **§8.5**.
- **Sweep** (PSG): NES-style, clocked at a fixed **239.70 Hz (mix rate ÷ 200)** — each tick period ± (period ≫ shift); rate 0 disables; out-of-range mutes (§8.5).
- **Wavetable:** phase accumulator indexes the selected 32-sample slot; sample is 8-bit signed; pitch via the 12-bit period field on the same ÷12 tone clock. Wave RAM is CPU-writable through the audio port (live waveform morphing allowed).
- **PCM — sample fetch by CPU-bus cycle-stealing.** Sample data lives in cartridge ROM at **20-bit linear addresses** spanning the whole 1MB cart. Because the cartridge is addressed by **the CPU's own A0–A13**, oito cannot fetch samples "independently"; instead **oito briefly becomes a bus master**, exactly as the NES 2A03's DMC channel does for DPCM:
 1. a voice's read-ahead FIFO runs low → oito asserts **RDY** low (halt the CPU at a cycle boundary), then **BE** low (tri-state the CPU off the bus);
 2. oito drives **A0–A15** (its host-bus address pads are **bidirectional**) and **BANK0–BANK5** to the sample's linear address, asserts ROM_CĒ, and reads a **burst (~16 bytes)** into the FIFO;
 3. oito restores the CPU's bank value, releases BE and RDY; the CPU resumes exactly where it stalled.

 **Bus-master timing (normative).** WDC specifies that `BE` low tri-states Address, Data **and R/W̄**, so the cartridge would otherwise see a *floating* strobe while `ROM_CĒ` is asserted — a potential write into flash. oito's `R/W̄` pad is therefore **bidirectional** and is driven **high (read)** for the whole steal. Sequence:

 1. assert **RDY** low; let the in-flight CPU cycle finish;
 2. assert **BE** low → the CPU releases A, D and R/W̄;
 3. oito drives **A0–A15**, **BANK0–BANK5** and **R/W̄ = high**, then asserts **ROM_CĒ**;
 4. sample D0–D7 after the flash access time (≥70 ns ⇒ one full CPU cycle per byte);
 5. deassert ROM_CĒ; repeat from 3 for the remainder of the burst;
 6. restore the CPU's bank value, then **MUST release BE before releasing RDY** — the CPU must regain its buses before it resumes clocking, or it would execute a cycle with its outputs still tri-stated.
 A steal always asserts **ROM_CĒ** explicitly, so sample fetch is unaffected by `SAVE_CTRL` (§11.4) — that register redirects **CPU** accesses to $8000–$BFFF only, never oito's own bus-master cycles. PCM therefore keeps streaming correctly while a game has the save window open.
 A NOR read (~70 ns) does not fit one 46.6 ns master cycle, so each stolen access occupies a full CPU cycle (139.7 ns); bursting amortises the arbitration. 8-bit = signed raw; 4-bit = IMA-ADPCM (standard predictor + step-index table). Pitch resamples via the phase accumulator; loop between loop-address and end-address when loop-enabled. **Because oito drives the bank lines during a steal, a sample may exceed 16KB and cross bank boundaries freely** — unlike anything reachable through the CPU's window.

- **Cost of streaming (a real, documented CPU tax).** **Workload:** 4 PCM voices, 8-bit samples, 48 kHz, 16-byte bursts. That is ≈**192 K byte-fetches/s** against 7.159 M CPU cycles/s → ≈**2.7 % of cycles**, rising to ≈**6 %** with per-burst arbitration overhead and shorter bursts. Fewer or 4-bit ADPCM voices cost proportionally less. Consequence: with PCM active the CPU's *instruction* throughput is below the nominal 455 cycles/line — see the determinism note in §3. Games needing a cycle-exact raster window can suspend PCM (`audio.pcm_suspend`, §14.2).
- **Mixer:** each voice → L/R accumulators (voice sample × envelope × side volume); sum 16 into a 20-bit accumulator → master L/R volume → **hard-clamp (saturate)** to 16-bit → I²S (§8.5); the same stream delta-sigma modulates the 2 PWM pins.

### 8.4 Output paths

![Audio signal chain from APU to outputs](diagrams/audio-chain.svg)

Audio does **not** ride the digital-video cable: the link is strict DVI-D (video only — §7.1), so audio has its own royalty-free outputs.

**Digital audio format.** Every clock divides from the master, so the whole chain is synchronous by construction:

| Signal | Value | Derivation |
|---|---|---|
| **LRCLK (fs)** | **47,940.3 Hz** | master ÷ 448 |
| **BCLK** | **3.0682 MHz** | master ÷ 7 = **64 × fs** (32 bits per channel) |
| **MCLK** | **6.1364 MHz** | **128 × fs** = 2 × BCLK, PLL-generated (as the dot clocks are, §6.7) |

- **oito is clock master** for all three; the `DIT4192` is a slave. MCLK occupies its own pin (§6.3).
- **Format: standard I²S** — one-BCLK delay after the LRCLK transition, **MSB first**, **LRCLK low = left**, **16-bit samples left-aligned in 32-bit slots** with trailing bits zero.
- **Channel status:** consumer format, category "general", **copy permitted**, **no pre-emphasis**, 16-bit word length, and the sample rate declared as **48 kHz with the accuracy field set to "level II / variable"**. This is the honest encoding of a **47,940.3 Hz** stream: S/PDIF has no code for that rate, every receiver recovers the actual clock from the biphase signal, and its PLL tracks the 0.12 % offset without difficulty — whereas "sample rate not indicated" causes some equipment to refuse to lock.
- **The I²S pins are physically unconnected to the CH7035B.** Cable audio is not used (§7.1).

- **Digital (optical S/PDIF):** the APU's I²S feeds a **`DIT4192` S/PDIF transmitter** driving a **3.3V TOSLINK optical module** (IEC 60958 / S/PDIF — commonly described as royalty-free; to be confirmed by the licensing review (§16.2)). Clean multi-bit digital audio to AVRs/soundbars/optical-in TVs. The same I²S can also feed an optional on-board DAC → analog jack.
**Analog audio output stage.** "PWM → RC → jack" is a filter with hopes attached, not a line output: wrong output impedance, no DC blocking, no defined level, and one node shared by two destinations that would load each other. Specified instead:

- **PWM parameters (previously undefined):** **2nd-order delta-sigma, 1-bit, clocked at master ÷ 8 = 2.685 MHz**. Stating order and clock is what makes the filter designable and completes the emulator's output model.
- **Reconstruction filter:** **3rd-order active low-pass, −3 dB at 20 kHz**, built around the line driver rather than a bare RC, so the carrier is attenuated hard instead of leaving noise in and above the audible band.
- **Line driver:** **`NJM4556`-class dual audio op-amp**, 5V single supply, **1 Vᵣₘₛ nominal output**, **≤100 Ω output impedance**, feeding the **3.5 mm jack and the SCART audio pins through separate series resistors** so the two destinations cannot interact.
- **DC blocking / bias:** output coupling capacitors sized for **20 Hz into 10 kΩ**; mid-rail bias for single-supply operation.
- **Mute/pop:** the driver stays **muted until the supervisor releases reset and the APU is enabled**, and re-mutes on brownout, so power cycling does not thump the speakers.
- **Protection:** series resistance plus coupling capacitors make the outputs tolerant of an indefinitely shorted jack.
- The DE-15 output carries no audio.

**Emulator model.** Per output sample (~48 kHz): advance each active voice's phase accumulator and envelope, fetch its sample (pulse/noise/wave-RAM/PCM-from-ROM), apply envelope × L/R volume, sum all 16, apply master volume, emit stereo. Fully deterministic; no cycle accuracy required. **The exact integer model is §8.5.**

### 8.5 APU reference model

Voice layouts alone cannot produce identical audio across implementations; this section is the arithmetic contract. All values are integers; the mix rate is **master ÷ 448 = 47,940.3 Hz** and every "per sample" step below occurs once per mix tick.

**Global registers ($00A0–$00AF).**

| Addr | Contents |
|---|---|
| $A0 / $A1 | master volume L / R (0–255, unity = 128) |
| $A2 | output enable (bit0 = APU on) |
| **$A3 / $A4** | **voice-active flags, voices 0–7 and 8–15** (16 flags do not fit in one byte) |
| $A5 | PCM FIFO status (bit *n* = voice *n* underran since last read; read-clears) |
| $A6–$AF | reserved, read $00 |

**Envelope (ADSR, all voices).** Attack/decay/release are 4-bit **rate indices** into a 16-entry table giving *mix ticks per step*; the envelope level is 8-bit. Attack adds one step per interval to $FF; decay falls to `sustain<<4`; release falls to 0. The table is geometric, ≈ `ticks[r] = round(2 ^ (r/2)) * 4` (r = 0…15 → 4…512 ticks/step), i.e. a **lookup table, not a runtime exponential**. Key-gate 1 starts attack; 0 starts release.

**Pulse.** `freq = 1,789,772.5 / (16 × (period+1))` (§8.3); duty 12.5/25/50/75 %. Output ±1 scaled by envelope.

**Noise.** 15-bit LFSR, **shifted right**, feedback into bit 14 = `bit0 XOR bit1` (long) or `bit0 XOR bit6` (short). **Reset seed = $0001**; the all-zero state is unreachable by construction. Clocked by the noise-rate divider off the same ÷12 tone clock.

**Sweep (PSG).** Clocked at **239.70 Hz = mix rate ÷ 200** (a fixed integer frame-sequencer divider — not "frames"). *An exact 240 Hz would require ÷199.75, which no divider can produce; nothing musical depends on the 0.13 % difference.* Each tick `period ± (period >> shift)`; **rate 0 disables**; a result below 8 or above $FFF **mutes the voice** until re-keyed.

**Wavetable.** Phase accumulator indexes the 32-sample slot; **no interpolation** (nearest sample — matches the aesthetic and is cheaper); phase **resets to 0 on key-on**; samples are 8-bit signed.

**PCM.**

- **Pitch** is **8.8 fixed-point** (`$0100` = source rate).
- **End address is exclusive**; on loop the position returns to the loop address.
- **FIFO underrun holds the last output sample** (no click) and sets the `$A5` flag.
- **IMA-ADPCM:** standard predictor/step-index tables, **low nibble consumed first**, with per-voice predictor and index stored. At the loop point the predictor/index **snapshot taken when the loop address was first passed is restored** — without which looped ADPCM drifts.
- **`current-position` is 20-bit (3 bytes)**, wide enough to express a 20-bit sample address.

**Mixer.** Each voice yields a 16-bit signed sample = `waveform × envelope × side-volume` (right-shifted to 16-bit). All 16 sum into a **20-bit accumulator**; master volume is applied; the result is **hard-clamped** to signed 16-bit — clamping is saturation to $7FFF/$8000, replacing the untestable phrase "soft-clamp". That stream feeds I²S directly and the delta-sigma PWM pair.

**Reset.** All voice registers, envelopes and phases zero; `$A0/$A1` = 128; output disabled. **Wave RAM is undefined at power-on** and is zeroed by boot firmware (§11.1).

**Conformance.** A golden test hashes the PCM output of a fixed register-write script plus a fixed sample ROM; any implementation must reproduce the hash bit-exactly.

---

## 9. Controller input

- **2× DB9 (DE-9) front ports**, Sega Genesis/Mega Drive pinout; 3-button and 6-button pads supported (including modern remakes/clones).
- Controllers are powered at **5V** (their internal 74HC157 needs it); each port's **4 joystick-only data lines** pass inbound through a **74LVC244A** translating 5V→3.3V into oito; the **2 PS/2-capable data lines** use the specified bidirectional front-end (4.7kΩ pull-up to 5V, 1kΩ series into the receiver, BSS138 gate-driven pull-down) so oito can also drive them low without ever seeing 5V; and **SELECT is driven outbound by a 5V-powered `SN74AHCT125`** — a 3.3V LVC output does **not** guarantee the ~0.7 × V_CC ≈ 3.5V high that the controller's 5V 74HC157 needs, which would make the 3-button multiplex and the 6-button handshake unreliable. One quad AHCT125 serves both ports' SELECT with channels to spare. LVC inputs are 5V-tolerant when the part is powered at 3.3V, so there is no clamp-diode conduction; per-port series resistors and ESD/TVS protection are added at the connector (board-level). The buffers are always-enabled translators (oito reads the pad state directly — §6.3).
- Read protocol (3-button): console toggles SELECT (DB9 pin 7); two button banks appear on the same six data lines:

| Pin | Signal | SELECT high | SELECT low |
|---|---|---|---|
| 1 | D0 | Up | Up |
| 2 | D1 | Down | Down |
| 3 | D2 | Left | logic 0 |
| 4 | D3 | Right | logic 0 |
| 5 | VCC | +5V | +5V |
| 6 | D4 | Button B | Button A |
| 7 | SEL | console output | console output |
| 8 | GND | ground | ground |
| 9 | D5 | Button C | Start |

- **Architecture:** controller data lines are routed **into oito** (6 data + 1 SELECT per port; §6.3), not onto the CPU data bus. oito latches pad state, exposes it in **JOYPAD_1/2 ($4070/$4072)** and their `_EXT` companions (§5.1), performs the SELECT toggling, and does edge detection in silicon — which is what makes the input-change IRQ (**IRQ_STATUS bit 2**, flagged per-source in INPUT_STATUS $4074) real. External LVC-class buffers still translate 5V→3.3V feeding oito. 
- Software model: read **$4070–$4073** (canonical §5.1). Edge detection (`pressed = current & ~previous`) is available either in the SDK's VBLANK handler or directly from oito's change latch.
- **6-button protocol.** oito performs the Sega handshake in hardware; the pad's internal counter advances on each TH toggle. Pad outputs are **active-low on the wire** (0 = pressed) and oito **inverts** them, so `JOYPAD_x` reads active-high (§5.1). TH = DB9 pin 7. One acquisition is **8 samples with ≥2 µs settling after every TH change**:

| # | TH | D0 | D1 | D2 | D3 | D4 | D5 |
|---:|:--:|---|---|---|---|---|---|
| 1 | 1 | Up | Down | Left | Right | B | C |
| 2 | 0 | Up | Down | **0** | **0** | A | Start |
| 3 | 1 | Up | Down | Left | Right | B | C |
| 4 | 0 | Up | Down | **0** | **0** | A | Start |
| 5 | 1 | Up | Down | Left | Right | B | C |
| 6 | 0 | Up | Down | **0** | **0** | A | Start |
| 7 | 1 | **Z** | **Y** | **X** | **Mode** | B | C |
| 8 | 0 | **1** | **1** | **1** | **1** | A | Start |

 **Device identification:**

 - **6-button** ⟺ sample 8 reads **D0–D3 = 1111**. A 3-button pad drives D2/D3 = 0 on every TH-low, so it can never produce this signature.
 - **3-button** ⟺ signature absent → `JOYPAD_x_EXT` = 0; samples 1–2 carry every button.
 - **Master System pad** ⟺ no TH multiplexing (TH is its Light-Phaser input), so samples do not vary with TH → treated as 2-button (mapped to A/B), EXT = 0.
 - **Unplugged** ⟺ all lines idle high through the pull-ups → no buttons and no signature; deliberately indistinguishable from "nothing pressed".
 - **Malformed/unknown** → oito reports only the sample-1/2 subset and clears EXT; garbage is never latched into EXT.

 **Timeouts:** the pad counter self-resets after ~1.5 ms of TH-high, so the mandated **>2 ms idle** guarantees each acquisition begins at counter state 0; an acquisition aborted mid-sequence simply retries after the idle. Game code never sees the protocol.

- **Scan rate & latency:** the earlier "~250 µs / ~4 kHz" figure **violated the six-button protocol** — Sega's acquisition sequence requires **TH to remain high for >2 ms between acquisitions** so the pad's internal counter resets, which a 250 µs cadence never permits; original and clone pads would misreport. Corrected timing:
 - one full sequence ≈ **50 µs** (8 TH transitions with **≥2 µs settling** after each change), followed by the mandated **>2 ms TH-high idle** → an acquisition cycle of **≈2.5 ms per port (≈400 Hz)**;
 - **worst-case button-to-register latency ≈2.5 ms**, not ≤250 µs. Still well inside one 16.6 ms frame, so the "sub-frame, invisible to games" conclusion holds — but the honest figure is 2.5 ms;
 - the same cadence is used for 3-button pads (which have no such constraint) so there is **one timing model** to verify and emulate;
 - **validation required** against representative original and modern clone pads.
 Registers reflect the most recent acquisition; INPUT_STATUS / change-IRQ fires when a polled state differs from the last.

- **Emulator input model.** "Present pad state each frame" is **not conformant**: the hardware acquires at **≈400 Hz (≈2.5 ms)** and raises change IRQs asynchronously, so a frame-granular model cannot reproduce sub-frame transitions, mid-frame IRQ timing, or a press-and-release inside one frame (entirely possible at 2.5 ms granularity). Since the change IRQ is a headline feature that games will use, its timing must match. Instead:
 - Input is a queue of **`(timestamp, device, state)` events**, timestamped in **CPU cycles since frame start**, applied during the scanline loop exactly as raster and blitter events already are.
 - The **acquisition cadence is modelled, not the protocol**: the emulator samples host input at ≈2.5 ms intervals and emits an event only on change — reproducing latency and change-IRQ timing **without simulating a single TH edge** (TH sequencing stays internal to oito, as above).
 - **Keyboard and mouse events carry their own timestamps** from the PS/2 stream, driving `KBD_SCAN` / `MOUSE_*` / `INPUT_STATUS` at the correct cycle.
 - **Tiers:** Tier 1 may quantise events to acquisition boundaries (~2.5 ms); Tier 2 places them at exact cycles. **Both must fire the change IRQ at the modelled time** — frame-granular input is conformant at neither.

### 9.1 Keyboard input — PS/2, via the controller ports

re8 supports a **PS/2 keyboard** with **no dedicated connector and no new oito pins** — it reuses a controller port. This unlocks keyboard-native genres (strategy, simulation, text/RPG, dev tools) while keeping all existing joystick games playable on a keyboard.

**Bidirectional PS/2 host in oito.** oito contains a small PS/2 host state machine on two of a port's data lines. On receive, the device drives the clock (~10–16 kHz) and DATA; oito samples DATA on each CLK falling edge, assembles the 11-bit frame (start + 8 data + parity + stop), checks parity, and pushes the byte into a small FIFO (KBD_SCAN, §5.1). On transmit (host→device — the mouse enable command §9.2, keyboard LEDs/config, and the identification sequence below), oito pulls CLK then DATA low via **open-drain drive** and clocks out its command frame per the state machine below. The two lines therefore carry **~4.7 kΩ pull-ups to 5V** and an **open-drain (pull-low-only) driver** — a small front-end change on just those two of the six data lines (the other four data lines + SELECT keep the plain 74LVC244A input path). oito is only ever in the 3.3 V domain; it drives *low* through the open-drain device and reads through the 5V-tolerant path. *(This supersedes an earlier receive-only sketch — bidirectional is required by the mouse and, as a bonus, restores keyboard LEDs and host configuration.)*

**PS/2 line circuit.** Per line (CLK, DATA), per port — a specified circuit, not a menu of alternatives:

| Element | Specification |
|---|---|
| **Pull-up** | **4.7 kΩ to +5 V**, on the **console PCB** (not in the adaptor, so a bare adaptor cannot leave lines floating) |
| **Receive** | line → **1 kΩ series** → **74LVC244A** input (5V-tolerant at a 3.3V rail); the series resistor limits fault current into the clamp |
| **Transmit** | **BSS138 N-channel MOSFET — drain = the 5V line, source = GND, gate = oito's 3.3V open-drain output.** Gate high pulls the line low; gate released lets the 5V pull-up restore the high |
| **ESD** | ≤10 pF/line TVS to GND at the connector |
| **Power-off** | oito unpowered ⇒ gate low ⇒ FET off ⇒ line idles high through the pull-up; **no path from 5V into oito in any power state** |

**Why gate-driven rather than the classic BSS138 bidirectional shifter:** in this topology **oito's pin never sees 5V** — only the FET drain does, while the gate stays in the 3.3V domain and the source is grounded. The familiar bidirectional level-shifter arrangement ties both rails through the FET body diode, which is acceptable for 3.3V↔5V I²C but would give 5V a route toward the ASIC. **Rise-time budget:** PS/2 runs at 10–16.7 kHz (≥30 µs half-period); 4.7 kΩ with a realistic 50 pF gives τ ≈ 235 ns and a full rise ≈1 µs (~2 % of a half-period), and even a pessimistic 150 pF gives ≈3 µs.

**Port mode & joystick-safety invariant.** The earlier rule was **circular**: transmitters were to stay high-Z until a port was "positively identified as PS/2", yet identification was specified as *sending* PS/2 Reset — which requires driving the lines. It also assumed a **plug-detect event the DB9 does not provide**. Replaced by explicit mode selection:

- **Every port is in joystick mode at reset**, and **oito never transmits in joystick mode** — the open-drain drivers stay high-Z. The invariant is now non-circular: *drive only where software has declared the port to be PS/2.*
- **`PORT_MODE` ($407C)** holds 2 bits per port: **0 = joystick (reset default), 1 = PS/2**. Only PS/2 mode releases the transmitters.
- **Who sets it:** the **boot firmware's setup menu** (a keyboard or mouse is a deliberate accessory purchase, so a one-time setting is reasonable), persisted in the boot flash; a game may also request it through `re8.keyboard`/`re8.mouse`.
- **Passive hint — receive only, never drive.** A PS/2 device spontaneously transmits its **BAT-completion `$AA`** ≈0.5 s after power-up with no host action. In joystick mode oito may therefore *listen*: a well-formed 11-bit frame with valid parity on an otherwise idle port sets **`PORT_HINT`** in `KBD_STATUS`, meaning "a PS/2 device may be attached here". Firmware can offer to switch modes. This recovers most of the convenience of auto-detection **with zero risk to a joystick**, since nothing is ever driven.
- **Identification proper** (Reset/Identify handshake, §9.1 below) runs **only after** the port is in PS/2 mode.
- Because the drivers can only pull *low* and are gated off in joystick mode, a controller's push-pull outputs are never contended; the weak 5V pull-ups do not disturb joystick lines (a controller's push-pull output overrides a 4.7 kΩ pull-up) and are conventional for such inputs. Ports are independent, so **mouse on one + joystick on the other** (or keyboard + mouse) run without interaction.

**PS/2 protocol & identification state machine.** Runs **only** once `PORT_MODE` = PS/2. The earlier text conflated two distinct operations — **Reset** returns `$FA` (ACK) then `$AA` (BAT pass); it is **`$F2` Identify** that returns ID bytes.

*Host→device frame:* pull **CLK low ≥100 µs** (inhibit) → pull **DATA** low (request-to-send) → release CLK → the device clocks out 11 bits (start, 8 data, **odd parity**, stop) → device returns an ACK bit → host releases both lines.

| Step | Host sends | Expected reply |
|---|---|---|
| 1 | `$FF` Reset | `$FA`, then `$AA` (BAT pass) within ~750 ms |
| 2 | `$F2` Identify | `$FA`, then **`$AB $83`** = keyboard · **`$00`** = mouse · **`$03`** = wheel mouse |
| 3a | *(mouse)* `$F3 $C8`, `$F3 $64`, `$F3 $50`, then `$F2` | `$03` ⇒ IntelliMouse wheel present (the "knock") |
| 3b | *(mouse)* `$F4` Enable Data Reporting | `$FA`; device begins streaming packets |
| 3c | *(keyboard)* `$F0 $02` Set Scan Code Set 2 | `$FA` |

*Error and recovery states:*

- **`$FE` RESEND received** → retransmit the last byte, **maximum 3 attempts**.
- **Parity error on receive** → host sends `$FE`; same retry cap.
- **Timeout** — ~750 ms for Reset, ~25 ms for other commands — → mark the port **failed**.
- **BAT failure (`$FC`)** → treat as a failed device.
- **Hot-unplug** — no valid frame for ~2 s while enabled → clear `present()`, flush the scan FIFO, and drop this port as a pointer source (§9.2 arbitration).
- **Failure is always safe:** on any failed or timed-out state oito **releases the transmitters (high-Z) and stops driving**, falling back to `PORT_HINT`-only listening — so a mis-declared port can never contend with a joystick.

**Passive DB9↔PS/2 adaptor (no MCU).** The DB9 already carries **+5V and GND**, and PS/2 keyboards are 5V devices, so the adaptor is pure wiring: DB9 pin 5→PS/2 +5V, DB9 GND→PS/2 GND, and two DB9 data pins→PS/2 CLK and DATA (mini-DIN-6). When a keyboard is on a port, oito routes those two data pins to the PS/2 host instead of the joypad mux (mode set explicitly via `PORT_MODE`; KBD_STATUS.present flags a device once identified); the port's other lines and SELECT are unused. The same passive adaptor serves a **mouse** (§9.2) — identical wiring, since a PS/2 mouse is the same 4-wire interface.

**Keyboard resource rules.**

- **FIFO depth 16 bytes** — ample at ≈2.5 ms per frame against a VBLANK-rate drain, including multi-byte sequences and burst typing.
- **Two keyboards:** if both ports are in PS/2 keyboard mode, the **lower-numbered port owns the scan FIFO** and the other's data is discarded — merging two streams buys nothing for a degenerate case.
- **Hot-unplug** (the ~2 s timeout, §9.1) **flushes the FIFO, clears `present()`, and clears every injected joypad bit**, so a yanked cable cannot leave a button stuck on.

**Key→joypad injection (compatibility).** When a port is a keyboard, oito can map a fixed key set (arrows→D-pad, and e.g. Z/X→A/B, Enter→Start) straight into a chosen player's JOYPAD registers (KBD_CTRL bits 1–2; map in KBD_MAP_IDX/VAL, firmware-loaded defaults). The mapping happens **below the game**, so *every* existing joystick title becomes keyboard-playable with **zero game or SDK cooperation** — a raw `$4070` read just sees buttons. Keyboard-aware games disable passthrough (`joypad_passthrough(false)`) while taking text, so typing keys don't also fire buttons.

**SDK & firmware.** Keyboard-aware games use the `re8.keyboard` module (§14.2) for cooked characters, a line-input field widget (echoes into the §6.8 text overlay + hardware caret), raw make/break key events, and modifier state. Scan-code→character translation uses a **region keyboard-layout table in the boot flash**, selected to match — and shipped alongside — the §6.8 region charset (US/UK/DE/…). Cooked characters are **Latin-1 codes, identical to the §6.8 glyph indices**, so echoing typed text is a direct write.

**Impact.**

- **oito:** bidirectional PS/2 host, scan FIFO, key→joypad LUT and the KBD registers ($4075–$407A) — **no new pins and no new connector**.
- **Board:** on the two PS/2 lines per port, the circuit specified in §9.1 (shared with the mouse, §9.2). The **5V rail budgets 250 mA per port / 350 mA total** for accessories, with a 500 mA polyfuse trip point.
- **Firmware:** region layout tables (small).
- **Restrictions:** **PS/2 only** — USB-HID would need a host stack, which is out of scope. With two ports total, keyboard use is typically **one joystick + one keyboard**. Simultaneous-key limits come from the **keyboard's own matrix ghosting**, not the interface: PS/2 is NKRO-capable.

**Emulator note.** Host keystrokes → the KBD_SCAN FIFO (Set-2 make/break) + the same key→joypad injection; layout translation and the field widget are SDK-side. Fully deterministic; the PS/2 bit-timing is internal to oito and need not be simulated.

### 9.2 Mouse input & hardware cursor

re8 supports a **PS/2 mouse** on a controller port (same passive adaptor, §9.1) with a **fully hardware-rendered cursor**: the game sets a cursor graphic once and thereafter only receives move/click events — **oito owns all cursor rendering and all mouse-hardware interaction.**

**Why the §9.1 host is bidirectional.** Unlike a keyboard, a PS/2 mouse reports nothing until the host sends **Enable Data Reporting (0xF4)** (plus optional sample-rate/resolution and the Microsoft wheel "knock" sequence). That host→device path is exactly the bidirectional PS/2 upgrade folded into §9.1; the mouse is the reason for it. After the `$F4` enable (§9.1 state machine), the mouse streams **3-byte packets** (button byte + signed X delta + signed Y delta), or **4-byte** once the IntelliMouse wheel is enabled by the 200/100/80 sample-rate knock and confirmed by an Identify returning `$03`.

**oito maintains the cursor; the game does nothing to draw it.**

- **Position from deltas.** Mouse motion is *relative*. oito accumulates the signed deltas, scales them by the game-set **velocity/sensitivity** (`CURSOR_SCALE`, fixed-point) with an optional 2-tier acceleration, and clamps to the active screen (or to `CURSOR_BOUNDS` if a sub-rect is set). The game never handles raw deltas unless it wants them.
- **The cursor is the new top-most composite layer** — above *everything*, including the §6.8 text overlay, so the pointer is always visible. It draws from VRAM at `CURSOR_TILE` (4bpp, index-0 transparent, sub-palette selectable): **one 32-byte tile in 8×8 mode, or four consecutive tiles (128 bytes) in 16×16 mode**, arranged **row-major — index+0 top-left, +1 top-right, +2 bottom-left, +3 bottom-right**, the same convention as multi-tile sprites (§6.6). A 16×16 4bpp image is 128 bytes, so the earlier "one tile" claim was arithmetically impossible. **No H/V flip is provided** — a pointer never needs it. It is positioned so the game-specified **hotspot pixel** (`CURSOR_HOTSPOT_X/Y`, the pointer tip within the tile) lands on the logical cursor coordinate. Reported click coordinates are at the hotspot. It does **not** count against the sprite budget. Changing the pointer graphic (arrow→hand→busy) is a single `CURSOR_TILE` write.
- **Events only.** The game reads `MOUSE_X/Y` (absolute, at hotspot), `MOUSE_BUTTONS` (L/M/R + btn4/5), `MOUSE_WHEEL` (signed accumulator), and is notified on move / button-change via the input-change IRQ (INPUT_STATUS, shared with joypad/keyboard).

**Cursor arithmetic.** Cursor feel is immediately noticeable to players, so none of this is left to implementers:

- **`CURSOR_SCALE` is 4.4 fixed-point** (1.0 = `$10`), usable range **0.25–15.9**. **A value of 0 is treated as 1.0**, never as "frozen" — a pointer stuck by a zeroed register is a nasty failure mode. **Fractional remainders are retained between packets**, so slow movement is not lost to truncation; this is what makes fine positioning feel correct.
- **Acceleration** (`CURSOR_SCALE` bit 7): when `|delta| > 4` in a packet the scaled result is **doubled**. One threshold, one multiplier — deliberately simple and exactly reproducible.
- **Rounding truncates toward zero** after scaling; results **saturate at the clamp/bounds** rather than wrapping.
- **Mouse Y is inverted on input** (PS/2 reports +Y as *up*, the screen counts downward), and a packet's **X/Y overflow bits mean "discard this delta"** — an overflowed delta carries no usable magnitude.
- **D-pad fallback** (no mouse present): **1 px per frame initially, accelerating to 4 px per frame after 250 ms held**; diagonals move both axes at the full rate (no √2 compensation — simpler, and indistinguishable at these speeds).
- **`MOUSE_STATUS` bits 1–3 clear on a read of `MOUSE_STATUS` itself**, not on reads of X/Y/buttons — "since last read" now names which read.
- **Coordinate atomicity:** reading **`MOUSE_X_LO` latches `MOUSE_X_HI` and `MOUSE_Y`** into a shadow, so a packet arriving mid-sequence cannot tear the pair; LO→HI→Y always yields one coherent position.
- **`MOUSE_WHEEL` saturates at ±127** rather than wrapping, and **clears on read**.

**Pointer ownership — mouse-first, single source.** Several devices can *potentially* move the cursor, so oito arbitrates to exactly **one authoritative source at a time**, defaulting to the physically-connected pointing device:

1. **A detected PS/2 mouse owns the pointer** — D-pad and keyboard cannot move it (two mice: lower port wins).
2. **With no mouse present**, the pointer follows the game-designated **fallback = a chosen player's D-pad** (`CURSOR_CTRL` bit 7). Keyboard arrow keys reach that D-pad through the §9.1 key→joypad injection, so "keyboard moves the pointer" needs no separate path.
3. **Hot-plug takes over**: attaching a mouse seizes the pointer; removing it reverts to the fallback. Never additive.

**System pointer without a mouse.** Because oito already turns *deltas* into a rendered cursor, menus and point-and-click UIs get a working pointer via the D-pad fallback even with no mouse attached, at zero extra game cost. The game may override the default arbitration with `CURSOR_CTRL.source` (auto / mouse-only / D-pad-only / off) for accessibility or a deliberate control scheme.

**Hit-test sampling timing.** "Once per frame" did not say *when*, and the answer determines which scroll and sprite state the result reflects:

- **The sample is taken when the raster reaches the pick point** — during that active pixel — latching whatever the compositor computed there. This is the natural implementation (it taps the existing compositor) and automatically yields the **scroll, OAM and palette state in effect at that pixel**, with no extra bookkeeping.
- **The pick coordinates are latched at the start of line 0**, so mid-frame writes to `PICK_X/Y` (or moves of the cursor hotspot) take effect **next frame**. Otherwise a game writing `PICK_X` after the raster had passed that line would receive a result for a point the beam never sampled — nondeterministic and unreproducible.
- **`HIT_STATUS`.5 ("sample valid") sets when the raster passes the pick point and clears at the start of each frame.** A pick point outside the active area simply never sets it that frame — a defined "no result" rather than stale data.
- **Results persist until the next frame's sample overwrites them**, so the natural read time is **during VBLANK**, right after a click is noticed.

*This deliberately mirrors the shadow-OAM decision: one named event, inputs latched at frame start, results read in VBLANK — two features sharing a single timing idiom.*

**Hardware hit-testing ("pick").** oito already computes, per pixel, which sprite and which BG cell win the composite — so it reports **what is under the pointer at the cost of one coordinate comparator and a few latches**. Once per frame — at the moment the raster reaches the cursor hotspot or the game-set pick point (timing above) — oito latches into the pick registers ($40C0–$40CF, §5.1): the **topmost opaque sprite index** under the point (`HIT_SPRITE`, 0xFF = none → maps to a game object); for **each BG plane, the name-table cell (col,row) and the tile ID** under the point, with **scroll/wrap already applied** (→ indexes a tile-grid map array directly); and `HIT_STATUS` flags (sprite present / plane-A opaque / plane-B opaque / a 2-bit **winner** field naming the layer that actually shows). On a click the game reads these directly — **no pixel→cell math, no scroll compensation, no per-object bounding-box tests on the CPU** — turning "what did the player click?" into a register read. The pick point defaults to the hotspot; a game may set an arbitrary `PICK_X/Y` to probe any location (e.g. what lies ahead of a projectile), making it a general hit-test facility. The cursor and text-overlay layers are excluded (you get what's *under* the pointer). *Silicon cost: one coordinate comparator plus the latches listed in §5.1, tapping the existing compositor.*

**SDK.** `re8.mouse` (§14.2): `present()`, `set_cursor(TILE, hotx, hoty)`, `set_speed(n)`, `set_bounds(...)`, `show()`/`hide()`, `on_move(&fn(x,y))`, `on_button(&fn(buttons))`, `on_wheel(&fn(delta))`, and pollable `x()`/`y()`/`buttons()`.

**Impact:** oito +mouse-packet parser + position accumulator/scaler/clamp + the top-layer cursor compositor (1 tile in 8×8, 4 in 16×16) + the MOUSE/CURSOR registers ($40B0–$40BF, §5.1); the bidirectional PS/2 host is already counted in §9.1. **No new connector; no new pins** (the two PS/2 lines are the same bidirectional port I/O). Board: shares §9.1's pull-ups + open-drain drive; a PS/2 mouse draws only 20–50 mA, well within the §2.1 per-port allowance. VRAM: the cursor is one existing tile (8×8) or four (16×16). Restrictions: **PS/2 only**; a mouse occupies one of the two ports (so joystick + mouse, or keyboard + mouse — not all three).

**Emulator note.** Host mouse deltas → the scaled position accumulator → top-tile cursor composite; buttons/wheel → events. Fully deterministic; the PS/2 packet timing is internal to oito.

---

## 10. Interrupts

- **Single IRQ line** from oito to the CPU. NMI unused ($FFFA/B → the address of a real `RTI` instruction in the fixed bank). Vectors at $FFFA–$FFFF: at power-on these are the **boot ROM's** (overlay active); after the boot handoff (§11.1) they are the **cartridge's** (reset $FFFC/D → game entry; IRQ $FFFE/F → the syslib `__irq_entry` trampoline, which *calls* the RAM-installed handler via a pushed return address + `JMP ($14)` — §14.4/).
- **IRQ sources — five, matching IRQ_ENABLE/IRQ_STATUS (§5.1):** bit0 **VBLANK** (60Hz), bit1 **sprite collision** (mid-frame, at the overlap moment), bit2 **input change** (joypad 1/2, keyboard scan-code, or mouse event — INPUT_STATUS $4074 says which; §9/§9.1/§9.2), bit3 **raster-compare** (RASTER_CMP $4004), bit4 **blitter-done**. *(The old three-source list predated raster-compare and blitter-done.)*
- **Dispatcher contract (per canonical map §5.1):** read IRQ_STATUS ($4002); bit0 = VBLANK, bit1 = collision (then read COLLIDE_A/B $4031/2, then write 1 to COLLIDE_CLEAR $4033), bit2 = input change (read INPUT_STATUS $4074 to see which of joypad-1/2, keyboard or mouse; then read JOYPAD_x / KBD_SCAN / MOUSE_* and write 1 to the serviced INPUT_STATUS bits), bit3 = raster-compare, bit4 = blitter-done. Acknowledge by writing 1 to the serviced IRQ_STATUS bits. prog8 binding: `sys.set_irqd()` → `sys.set_irq(&dispatcher)` → `sys.clear_irqd()`; handler returns 0 (consume) or 1 (fall through to system routine).
- **Acknowledge & priority:** `IRQ_STATUS` is write-1-to-clear and there is no fixed hardware priority — the dispatcher reads `IRQ_STATUS` and services bits in whatever order it chooses. The exact semantics, all software-observable:
 - **`IRQ̄ = NOT(any(IRQ_STATUS & IRQ_ENABLE))`** — asserted low, **purely combinational** from the two registers, not an edge or a latch of its own. ("ORs enabled+pending onto IRQ̄" was imprecise.)
 - **Masked events still set `IRQ_STATUS`.** The mask gates *assertion*, never *recording* — which is exactly why a source can be polled while its interrupt is disabled (the basis of `INPUT_IRQ_MASK`).
 - **Enabling a mask for an already-pending event asserts IRQ̄ immediately**, which follows from the combinational definition and is what prevents lost interrupts.
 - **Set and W1C-clear in the same cycle: the set wins** (the bit stays set). Losing an event to a coincident acknowledgement would be a silent, unreproducible bug; the worst case here is one spurious re-entry.
 - **`IRQ_STATUS` bits are edge-latched**: set by the event, cleared **only** by W1C. VBLANK latches at line 224, blitter-done at the final byte written, raster-compare at the start of the compared line. *(They are deliberately **not** level-derived: a level-derived VBLANK bit would re-set the instant it was acknowledged during VBLANK, producing an interrupt storm.)*
 - **`STATUS` ($4003) bits 0–1 are level**, not events — they report *in VBLANK* / *in HBLANK*, i.e. current raster position, and are not acknowledged.
 - **`INPUT_STATUS`.2 re-latches immediately if keyboard FIFO data remains**, because it reflects *FIFO non-empty* — a level. **A handler MUST drain the FIFO, not merely acknowledge.**
 - **Raster-compare fires at the start of the compared line** (`CUR_LINE == RASTER_CMP`, evaluated at line start). **Values > 261 never fire.** Writing `RASTER_CMP` **after** that line has passed takes effect **next frame** — there is no retroactive firing.
- **Timing:** VBLANK window = 38 lines ≈ 52,000 master ticks; conversation's collision latency storyboard: silicon detect at t=0, IRQ ~1µs, dispatch ~3µs, user callback ~5µs.
- Main loops either `while true` (event-driven model) or the `WAI` instruction to sleep until VBLANK. **Handlers set flags; the main loop does the work** — the normative idiom, since only `@irqsafe` routines may be called from interrupt context.

---

## 11. Cartridge subsystem

- **Slot: 36-pin card edge** — D0–D7 (8), A0–A13 (14; fixed 16KB window addressing), BANK0–BANK5 (6; driven by oito mapper), R/W̄ + PHI2 + ROM_CĒ + SAVE_CĒ (4; SAVE_CĒ for on-cart FRAM saves, §11.4 — NC on non-saving carts), power/ground (4).
- Cartridge PCB: 2-layer, gold fingers, **one chip** on a plain game cart — **`SST39VF040` (512KB, TSOP-32)** or **`SST39VF080` (1MB, TSOP-40)**; the board must accommodate the **larger TSOP-40 footprint** for 1MB titles, which matters because the cartridge shell is a fixed manufactured part. Access time **70 ns**, comfortably inside both the 139.7 ns CPU cycle and the ≥70 ns PCM-steal budget; a **saving** cart adds an **`FM18W08` parallel FRAM** on SAVE_CĒ (§11.4). No mapper hardware on cartridge; all banking logic in oito.
### 11.0 ROM image construction & banked calls

prog8 compiles into **one flat 64KB address space**; nothing in the compiler places code into 64 overlapping $8000–$BFFF banks or produces a 1MB image. re8 therefore defines a **build model** rather than depending on compiler capability:

- **Banked calls use SDK fixed-bank wrappers, not `extsub @bank`.** Upstream documents transparent banked calls only for targets with *implemented* bank support and states that emitted code is target-specific — a `.properties` file does not establish it for re8. The normative mechanism is **`far_call(bank, addr)`** in the fixed bank: save current bank → write `BANK_SELECT` → `JSR` → restore. Explicit, testable, and auditable from IRQ context. *(If upstream banked-call support is later validated against the pinned compiler, it becomes an optimisation — never a dependency.)*
- **One compilation unit per bank.** Each bank is compiled separately to a 16KB binary; a **post-link packer** assembles the ROM image, places the fixed bank last, fills unused space, and emits the build map. This mirrors how period cartridge toolchains worked.
- **Header placement (fixes the `pc_start` collision).** Bank 0 begins with the **64-byte header** (§11.2) at ROM offset $0000 = CPU **$8000–$803F**, so **bank-0 code starts at `pc_start=$8040`**. The earlier `pc_start=8000` put code and header at the same address.
- **Vectors** are emitted by the packer into the **fixed bank's top 6 bytes**: reset → the cartridge entry, IRQ → `__irq_entry` (§14.4), NMI → the address of a real `RTI`.
- **Conformance tests (required before SDK freeze):** nested far calls; 8-deep bank-stack overflow/underflow; far calls attempted from an IRQ handler (**forbidden**); and far calls attempted while the **save window is open** (**forbidden** — the window hides the ROM bank, §11.4).

- **Banking model:** $8000–$BFFF = switchable window; $C000–$FFFF = fixed window holding engine code + vectors. oito learns the cartridge's geometry from **`CART_CONFIG_BANKS`/`CART_CONFIG_SAVE`** ($4082/$4083), which the **boot firmware parses out of the header** (§11.2) and then **locks** via `CART_LOCK` ($4084) before handoff — oito itself never parses the header. From that:
 - **Fixed bank = `bank_count − 1`** — the cartridge's last physical 16KB bank. (Without this, every ROM smaller than 1MB mis-maps its own vectors.)
 - **`BANK_SELECT` is masked** by `bank_count − 1`, so out-of-range values **mirror** rather than selecting absent flash (classic mapper behaviour, trivially emulatable — not open bus).
 - **`BANK0–BANK5` are combinational physical address bits**, sourced per access: masked `BANK_SELECT` for $8000–$BFFF, the fixed bank for $C000–$FFFF, and oito's own sample address during a PCM bus-master steal. *(The earlier "the bank register drives them" was incomplete.)*
 - **Emulator note:** these registers reset to 0 (a 1-bank cartridge), so a fast-booting emulator must program them from the ROM header exactly as firmware would, then treat them as locked. Call mechanism: **SDK `far_call(bank, addr)` wrappers in the fixed bank** — `extsub … @bank N` is **not** relied upon on re8. The SDK also offers scoped `use_data_bank(n)`/`restore_data_bank()` with an 8-deep bank stack for data access.
- **ROM image:** offset 0 = CPU $8000, beginning with the 64-byte **cartridge header** (§11.2); bank-0 code therefore starts at **$8040** (§11.0); vectors at the image top of the fixed bank; `launcher=none` (no BASIC stub).
- **Cartridge interface passes reads *and* writes — behind a gate:** oito propagates CPU R/W̄ and PHI2 to the cartridge, but **only asserts the cartridge write path while `SAVE_CTRL.CART_WE_ENABLE` ($4081 bit 4) is set, which resets to 0**. Smart carts (flash / SD / dev) set it deliberately to use NOR unlock sequences and flashcart command registers; retail games never do, so a wild pointer cannot program the cartridge. This is the same reset-cleared write-enable idiom as `BOOT_FLASH_WE` and the save write-protect. The "one connector, no console-side modes" property is preserved because the gate is a **register**, not a mode.
- **Bank register** is $4080 (§5.1); banked code/data live in the switchable window $8000–$BFFF.

### 11.1 Boot ROM & power-on handoff

![Boot sequence and overlay states](diagrams/boot-sequence.svg)

re8 boots in two stages: an **unbrickable internal stub** in oito hands off to an **updateable external boot ROM**, which initializes the system and launches the cartridge. (This replaces the earlier "boot straight into the cartridge, no firmware" model.)

**Storage — hybrid, brick-safe:**

- **Internal oito boot stub — ~2KB on-die mask ROM, unbrickable.** Owns the reset vector at power-on (`BOOT_SRC=0`, §5.1). Minimal: bring up clock/bus, verify the external boot ROM checksum, jump to it; if the external ROM is blank/corrupt, enter recovery.
- **External boot flash — 128KB parallel NOR, `SST39VF010` (3.3V, PLCC-32/TSOP-32)** on the CPU bus, decoded by oito via **BOOT_CĒ / BOOT_ŌĒ / BOOT_W̄Ē** (§6.3; the earlier "no extra oito pins" claim was self-contradictory since oito performs the decode). Deliberately the **same SST39 family as the cartridge flash**, so one JEDEC program/erase implementation serves both.
 - **Programmability.** `BOOT_W̄Ē` is the write strobe the field-update story requires; it is *not* shared with `RAM_W̄Ē`, because a shared strobe would let a mis-decoded stray write program the firmware and defeat the brick-safe design. oito asserts `BOOT_W̄Ē` **only while `BOOT_CTRL.BOOT_FLASH_WE` (bit 2) is set**, which resets to 0.
 - **Algorithm:** standard JEDEC software-data-protection sequences — unlock writes to $5555/$2AAA, **sector erase** (4KB) and **byte program**, with completion detected by `DQ7` data-polling or `DQ6` toggle. The updater necessarily executes **from system RAM** (already required by §11.3), since the flash cannot be read while it is being programmed. Holds the real firmware plus the region default text charset(s) (§6.8) and keyboard layout table(s) (§9.1), and is field-**updateable** (§11.3).

**Boot-flash paging.** The overlay window is only 8KB but the flash is 64–128KB, so the firmware pages itself through that window using the same fixed+banked idiom as the cartridge:

- **`BOOT_BANK` ($4008)** selects which **8KB page** of boot flash appears at **$E000–$FFFF** while `BOOT_SRC = 1`. 4 bits → 16 pages → **128KB** (a 64KB device uses 8). Reset value 0.
- **Page 0 is resident**: it holds the reset/IRQ vectors, the page-switch trampoline and the core routines, so changing pages never pulls the executing code out from under itself. Pages 1…N hold *data and secondary routines* — logo bitmap, self-test, on-screen messages, the **region charsets** (§6.8), the **keyboard layout tables** (§9.1) and the flash updater — which resident code reads a page at a time (the charset/layout uploads into oito are page-local, so nothing must span a page boundary).
- `BOOT_BANK` applies only while **`BOOT_SRC = 1`**, and is inert once the overlay is disabled, so after handoff the boot ROM is entirely invisible to the game, exactly as below.
- *Emulator contract:* a read at `$E000+n` with `BOOT_SRC=1` returns `boot_flash[(BOOT_BANK << 13) + n]`.

**Stage 0 — internal stub and firmware validation.** The overlay's contents are selected by `BOOT_SRC` (`BOOT_CTRL` bits 0–1), *not* a single enable bit:

1. At RES̄ **`BOOT_SRC = 0`**: the **internal 2KB stub is mapped at $E000–$FFFF, mirrored 4×** (so every read in the window is defined and $FFFC/D is the stub's reset vector). External flash is not visible. `BOOT_BANK = 0`.
2. The stub brings up minimal clock/bus state and **copies a small loader into system RAM**, then jumps to it — the same RAM-trampoline technique used for the cartridge handoff below, because the code must survive remapping its own window.
3. From RAM the loader sets **`BOOT_SRC = 1`** (external flash page visible), walks every page via `BOOT_BANK`, and verifies the firmware checksum.
4. **Valid** → it leaves `BOOT_SRC = 1` and jumps to the external firmware's entry point; the firmware continues at step 1 of the handoff below.
5. **Blank/corrupt** → it restores **`BOOT_SRC = 0`** and enters **recovery**: the stub reads a firmware image **through the cartridge window** ($8000–$BFFF, `BANK_SELECT` operating normally — the plain-update, SD and dev cartridges all present as ROM there) and reflashes the boot flash. The debug probe remains an alternative recovery path, since it can halt the CPU and drive system RAM directly (§13). The internal stub is mask ROM and cannot be erased, so recovery always exists.

**Reset overlay & handoff (Game-Boy-style):**

1. With `BOOT_SRC = 1` the boot firmware owns $E000–$FFFF, so reset/IRQ vectors are the firmware's.
2. The firmware runs: hardware init, logo + APU jingle, controller poll (self-test combo), read + validate the cartridge header via the switchable window.
3. To launch the game it copies a tiny stub to system RAM and jumps to it; the stub writes **`BOOT_SRC = 2`** (one-way until next reset) — un-mapping the boot ROM and restoring the cartridge fixed bank at $C000–$FFFF — then `JMP ($FFFC)` into the cartridge. Running the handoff from RAM avoids pulling the code out from under itself.
4. After handoff the memory map is exactly §5 (cartridge owns $C000–$FFFF + vectors); the boot ROM is invisible.

**Boot ROM responsibilities.**

- Boot logo + APU jingle.
- **Full hardware init** — video mode, default palette, VRAM/RAM clear, APU reset, controllers up — so cartridge code starts from a known state.
- **Self-test / diagnostics** via a power-on button combo: RAM/VRAM march test, video test patterns, audio test, controller and port test. *This doubles as the factory production test.*
- No-cartridge and bad-cartridge screens.
- **Cartridge-header validation**, then **programming `CART_CONFIG_BANKS`/`CART_CONFIG_SAVE` from the header and locking them via `CART_LOCK`**, then entry launch.
- Region/refresh and output defaults.
- **Loading the region default charset into text-layer font-RAM bank 0** (§6.8).
- No CH7035B initialisation is needed — it self-boots from its own EEPROM (§7.1).
- **Deliberately NOT:** a resident system API (games static-link the SDK), and **not** a DRM or lockout system (header magic check only).

### 11.1.1 Handoff state

**The canonical boot image is the compatibility contract.** Machine state at cartridge launch is defined as *"whatever boot firmware version X produces"*. **Fast-boot** (skipping the firmware, as GB emulators skip the DMG ROM) remains supported, but only against the table below, which is **generated from the canonical image and must match it byte-for-byte** — it is not hand-written. Without this, two emulators could fast-boot the same cartridge into different states and a game relying on firmware leftovers would diverge.

| Domain | State at handoff |
|---|---|
| **oito registers** | all $00 except: `BOOT_CTRL` `BOOT_SRC` = **2** (overlay off), `CART_CONFIG_BANKS`/`CART_CONFIG_SAVE` = programmed from the header and **locked**, `VIDEO_CTRL` = screen enabled + resolution per firmware default, `SAVE_CTRL` = window closed + write-protected |
| **System RAM** | **$0000–$3FFF cleared to $00**, including the ZP runtime area — no leftover garbage |
| **VRAM** | cleared to $00 |
| **Palette RAM** | default 64-colour set loaded (published as data in the SDK) |
| **Font RAM** | bank 0 = region charset (both densities); **bank 1 undefined** |
| **Mapper** | `BANK_SELECT` = 0; save window closed |
| **APU** | all voices off, wave RAM zeroed, master volume 128 |
| **CPU** | SP = $FF; **I set**, **D clear**; A/X/Y **undefined (explicitly so)**; PC = cartridge reset vector |

**Versioning consequence.** Because the table is *derived from* the firmware, any firmware revision that changes it is a **compatibility-relevant change** and MUST bump a documented **handoff-state version**, which the SDK and emulator both record. This is the price of permitting fast-boot, and it is stated rather than hidden.

**Emulator note:** execute the canonical boot image, or fast-boot directly to the table above and jump to the cartridge entry. Both paths must be indistinguishable to a conforming cartridge.

### 11.2 Cartridge header

64 bytes at ROM image offset $0000 (= $8000 in bank 0), read by the boot ROM via the switchable window:

| Offset | Size | Field |
|---|---|---|
| $00 | 4 | magic `"re8\x1a"` |
| $04 | 1 | header version |
| $05 | 16 | title (ASCII, space-padded) |
| $15 | 1 | region tag — advisory metadata (title origin); the console is 60Hz-only, so this does not switch a hardware mode |
| $16 | 1 | bank count (log2 of 16KB banks, 0–6 → up to 1MB) |
| $17 | 1 | save flags (§11.4): bit0 has-save; bits1–2 save type (**0 = none, 1 = FRAM, 2–3 reserved** — EEPROM removed); bits3–5 save-size code (**0 = none, 3 = 16KB; 1–2 reserved**); bits6–7 reserved |
| $18 | 2 | entry point (CPU address) — **advisory/tooling only**; launch uses the reset vector `JMP ($FFFC)` |
| $1A | 2 | header checksum |
| $1C | 4 | ROM CRC32 |
| $20 | 32 | reserved |

**Checksum & version definitions.** Both are **format ABI**: a packer and a boot ROM that disagree reject valid cartridges, so they are pinned exactly.

- **Header checksum ($1A, 2 bytes)** — 16-bit **sum of bytes mod 2¹⁶**, stored **little-endian**, computed over header offsets **$00–$19 and $1C–$3F**, i.e. **excluding the checksum field itself**. A plain sum rather than CRC-16 is deliberate: the boot stub must verify it in a few hundred cycles with trivial code, and it guards only against a blank or corrupt header, not against tampering.
- **ROM CRC32 ($1C, 4 bytes)** — **standard CRC-32 (IEEE 802.3 / zlib / PNG)**: polynomial **0x04C11DB7**, **reflected in and out**, **init 0xFFFFFFFF**, **final XOR 0xFFFFFFFF**, so every existing tool computes it correctly. **Coverage: the entire physical ROM image including padding**, with the **CRC32 field itself taken as four zero bytes** during computation — making the value a true identity for the image, which matters because the emulator keys `.sav` files on it. **Not verified at boot**: tooling, save-keying and self-test only.
- **Header version ($04)** — the boot ROM accepts any header with version **≤ the version it knows**, ignoring unrecognised fields (reserved bytes are zero-filled). A **higher** version is **rejected** with the bad-cartridge screen rather than guessed at.

Invalid magic/checksum → the boot ROM shows the bad-cartridge screen.

**Validation scope.** At boot the firmware verifies **only the 2-byte header checksum** ($1A) — cheap and instant. The **ROM CRC32** ($1C) is *not* scanned at boot (1MB at 7.16MHz would cost seconds); it exists for the SDK/tooling, as the emulator's `.sav` key (§11.4), and for optional self-test. **Entry is `JMP ($FFFC)`** — the cartridge reset vector is normative; the header's entry-point field ($18) is **advisory metadata for tooling** and is not used to launch (same treatment as the region byte).

### 11.3 Smart-cartridge family (accessories)

Because the connector passes reads and writes (above), one interface serves four cartridge types with **no console-side modes**:

- **Game cartridge** — one **factory-programmed NOR** device (the retail product). *Not "read-only": an SST39VF part is in-system programmable, so retail boards additionally **tie `WĒ` inactive at the footprint***, making the cartridge unprogrammable even if `CART_WE_ENABLE` were wrongly set.
- **Dev cartridge** — writable SRAM; the **debug probe fills it over the expansion-header CPU bus** (the dev-bootstrap path — no console USB port, no cable). Runs any streamed game or the firmware updater. Tiny test programs can alternatively load straight into the 16KB system RAM.
- **Plain update cartridge** — a normal ROM cart carrying `[updater + firmware image]`; run once to reflash the console's boot ROM (Wii-update-disc model).
- **SD cartridge (flagship accessory)** — SD slot + MCU + ~2MB PSRAM + CPLD/FPGA bus interface + a built-in menu/loader ROM. Two jobs: (1) **digital games** — copy the game `.bin` onto the SD, pick it from the on-screen menu, the cart loads it into PSRAM and the console runs it as a normal banked cartridge; (2) **firmware updates** — put `firmware.bin` on the SD and reflash the boot ROM. Commands (select/load) travel as flashcart-style bus writes the cart's logic watches for. (Everdrive-class model.)

**One updater, three deliveries.** There is a single boot-flash updater routine: it copies itself to RAM, sets `BOOT_CTRL.BOOT_FLASH_WE`, runs the JEDEC erase/program sequences (§11.1) against the external boot flash from an image in the cartridge window, verifies, clears `BOOT_FLASH_WE`, and reboots. It is delivered by the plain update cartridge, the dev cartridge (loaded via probe), or the SD cartridge — the console's own CPU always does the flashing; the internal stub guarantees no brick.

*Security note (out of scope):* side-loading unsigned games via SD is a piracy/authenticity consideration; optional cartridge/firmware signing could be added later but conflicts with the open "copy bits to SD" flow — deferred.

### 11.4 Save / persistent storage

**Normative save medium: on-cart FRAM, battery-free — and the *only* save device.** A saving cartridge carries a **parallel FRAM** (`FM18W08`, §11.4 below) alongside its NOR. FRAM is nonvolatile, SRAM-fast, ~10¹³-write endurance, and needs **no battery** — deliberately rejecting battery-backed SRAM, whose coin cell dies in 10–20 years and takes the save with it (the classic retro failure re8 refuses to ship).

**EEPROM is removed as a supported type.** Parallel EEPROM has ~5 ms page-program delays, page-write rules, **~10⁵ endurance** and **busy polling**, so it cannot share FRAM's software contract: it would force **two save protocols** on every game, the SDK *and* the emulator (which would need a commit-timing model, since software can observe the busy state — making EEPROM part of the compatibility contract, not just the BOM). It also undercuts the battery-free-durability rationale: at 10⁵ writes a game autosaving every 30 s exhausts an EEPROM in about a month, whereas FRAM effectively never wears out. The BOM saving is small beside shell, PCB, flash and assembly. **Result: `re8.save.write` has one contract — immediate, no polling, no busy state.**

**How it's wired — the save chip maps over the switchable window.** The CPU map (§5) is fully allocated, so saves get **no new address space**; instead they temporarily replace the ROM bank, the standard cartridge-RAM idiom (Genesis/Mega Drive SRAM-over-ROM, GB MBC):

- `SAVE_CTRL` bit 0 (**$4081**, mapper block) enables the **save window**. While set, CPU accesses to **$8000–$BFFF** assert **SAVE_CĒ** instead of **ROM_CĒ** — the FRAM appears in place of the current ROM bank, driven by the A0–A13 + D0–D7 + R/W̄ + PHI2 lines already at the connector (§11).
- The **16KB aperture matches A0–A13 exactly**. Parts smaller than 16KB (2KB/8KB) **alias/mirror** through the window; hardware and emulator must mirror identically.
- `SAVE_CTRL` bit 1 is a **write-protect** guard (default on) so stray writes can't corrupt a save; bits 2–3 mirror the size code held in `CART_CONFIG_SAVE`.
- oito honours the window only when **`CART_CONFIG_SAVE`.0** is set (loaded from header $17 by boot firmware and then locked — §11); otherwise SAVE_CĒ never asserts.
- Access is naturally **rare and bursty** (swap in → transfer a few hundred bytes → swap out), so the loss of ROM visibility is bounded to that transfer; code MUST NOT execute from $8000–$BFFF while the window is open. The SDK hides the sequence entirely (`re8.save.*`, §14.2). *Code **MUST NOT** execute from $8000–$BFFF while the window is open* — the SDK's helpers run from the fixed bank.

**Save device & timing.** The normative part is **Infineon `FM18W08`** (32 K×8, 3.3 V, parallel, active production). A real FRAM is **not** an always-selected SRAM, so the access model is specified:

- **`SAVE_CĒ` is pulsed per access, never held** across the window. FM18W08 requires a **falling `CE` edge for every operation** plus a minimum **`CE`-high precharge**; oito's mapper asserts `SAVE_CĒ` for the access phase and releases it between CPU cycles, which supplies both.
- **Timing budget:** 70 ns access, **130 ns cycle time**, against a **139.7 ns CPU cycle** → **one save access per CPU cycle with no wait states, 9.7 ns of margin.** Recorded explicitly because the margin is small: raising the CPU clock (e.g. the rejected 8 MHz / 125 ns option) would break it and require wait states.
- **Density:** the part is 32 KB but only **16 KB is exposed — `A14` tied low deterministically**, matching the 16 KB save window.
- **Save sizes:** FRAM saves are **16 KB**; the header's 2 KB/8 KB size codes describe the cheaper **EEPROM** path.

The FRAM sits directly on those lines with no glue logic; **non-saving carts leave SAVE_CĒ unconnected and remain a single chip.** So the connector is **36-pin** (was 35): a saving cart is NOR + FRAM, a plain cart is NOR only. Save size is **16 KB** (`FM18W08` with A14 low); smaller codes are reserved. Declared in the header and mirrored into `CART_CONFIG_SAVE`.

**Digital (SD) games** don't use cart FRAM — the SD cartridge (§11.3) writes each game's save as a **`.sav` file on the SD card**, keyed to the game, using its own MCU + storage. So retail carts save to on-cart FRAM; digital titles save to SD files. **No console-side shared NVRAM** — it would tie saves to the console (not portable), need an allocation/management layer, and risk mixing with the boot flash; rejected.

**Virgin contents.** FRAM is **not** flash: it has no erased state, and a factory-fresh `FM18W08` powers up holding whatever the die settled at (commonly $00, **not guaranteed**). The spec therefore declares **virgin save contents *unspecified***, with the consequence stated plainly: **a game MUST validate its own save** using its own magic/checksum rather than assuming a blank pattern. This is a property of the hardware, not a modelling convenience. Separately — and not to be confused with it — **an emulator initialises a newly created `.sav` to $00** for determinism.

**Emulator persistence contract.** The save is a flat image of the 16KB FRAM region (one contract — immediate writes, no busy state).

- **Size is always exactly 16,384 bytes.** A shorter file is **zero-padded**, a longer one **truncated**, each with a warning — never an error, so a save is never lost to a size mismatch.
- **File key: `<sanitised-title>_<crc32>.sav`**, where the CRC32 is **recomputed from the ROM image, never taken from the header** — trusting the header field would let a wrong or malicious value mis-key a save or collide with another title's. Including the title also disambiguates the improbable-but-possible 32-bit collision.
- **Writes are atomic:** write to a temporary file, flush/`fsync`, then rename. Games commonly save at exactly the moment a user quits, so a crash mid-write must never leave a truncated `.sav`. On write (and at exit) the emulator serializes it to a host **`.sav` file keyed by the recomputed ROM CRC32** and reloads it on launch — a battery-backed-cart model, deterministic and portable. This is separate from optional emulator **save-states** (full-machine snapshots), which are a convenience feature, not the game's save mechanism.

---

## 12. Expansion header (40-pin)

2×20, 2.54mm pitch, unpopulated on retail units. Taps existing signals (costs oito only its 4 JTAG pins; costs the CPU nothing):

| Pins | Group | Signals |
|---|---|---|
| 1–16 | Address bus | A0–A15 |
| 17–24 | Data bus | D0–D7 |
| 25–28 | oito JTAG | TCK, TMS, TDI, TDO |
| 29–36 | CPU control | PHI2, R/W̄, RES̄, RDY, BE, SYNC, IRQ̄, DBḠ (probe debug-request to oito) |
| 37–40 | Power | 2× 3.3V, 2× GND — **≤300 mA budget for an attached probe** |

Pin assignment is **final:** 8 control pins (29–36) carry every signal the probe needs — RDY/SYNC/BE for breakpoints and jamming, PHI2 + `DBḠ` for oito-mediated single-step (§13), RES̄, R/W̄, and IRQ̄ (so the probe can observe/inject interrupts). NMĪ is unused system-wide and not brought out. The header still costs oito only its 4 JTAG pins; the CPU-bus and control signals are already exposed.

---

## 13. Debug probe

**Hardware:** external accessory; **RP2350B** MCU — **48 GPIO** in QFN-80, so all **36 non-power header signals connect simultaneously** (16 address + 8 data + 4 JTAG + 8 control) with ~12 pins left for transceiver direction, status and spare; no multiplexing, so address-match-on-SYNC, RDY assertion, data jamming and JTAG all operate concurrently. **RP2040 was insufficient — 30 GPIO cannot reach 36 signals.** 3× PIO at 150 MHz gives extra margin for the breakpoint timing budget. oito JTAG also usable with J-Link/FT2232H + OpenOCD; ribbon cable to the 40-pin header; USB-C to PC; powered from header 3.3V. Sniffs the bus passively at full bus speed.

**Probe electrical design.** An MCU must not drive a 24-line CPU bus directly through a ribbon cable, and an accessory that can be unpowered or USB-connected while the console runs needs defined behaviour in every state:

- **Bus transceivers:** 2× **74LVC245** for A0–A15 and 1× for D0–D7, direction driven by the MCU and **defaulting to receive (sniff)**. Control lines (RDY, BE, DBḠ) connect directly but are **open-drain**.
- **Series damping ≈33 Ω** at the source of every header signal — standard practice for 2.54 mm ribbon at a 7.16 MHz bus rate, which would otherwise ring badly.
- **Defined power-off state:** every transceiver `OE` is **pulled to the disabled level**, so a probe that is unpowered, in reset, or not yet initialised is **high-impedance on all lines**. Plugging in a powered-off probe therefore cannot load or crash a running console — without this, MCU protection diodes on 36 lines would clamp the bus.
- **Power domain / back-powering:** the probe is powered **only from the header's 3.3 V**, with a **series Schottky or ideal-diode** blocking USB VBUS from back-feeding the console. Otherwise a USB-connected probe would energise oito and the SRAMs through their I/O pins with the console switched off — the classic way to destroy a debug target.
- **Header current budget: ≤300 mA at 3.3 V** for the probe; the console's 3.3 V buck (§2.1) is sized to include it.

**Capabilities (all exploiting the fully-static W65C02S):**

1. **Hardware breakpoints (timing budget):** PC address sent from IDE; the probe state machine matches the address bus *with SYNC high* (opcode fetch, not data access) **and, for addresses in the switchable window, the shadowed `BANK_SELECT` value** — the probe tracks writes to $4080 off the bus, so a breakpoint in bank 3 does not fire in the other 63 and pulls **RDY** low; zero ROM/software overhead; the game runs at full speed until the breakpoint. The former claim of asserting RDY "within nanoseconds" is replaced by an actual budget at 7.159 MHz (cycle = 139.7 ns):

 | Element | Budget |
 |---|---:|
 | Address/SYNC valid after PHI2↑ (CPU t<sub>ADS</sub>) | ~30 ns |
 | Inbound: transceiver + ~30 cm ribbon | ~15 ns |
 | PIO detect + assert (RP2350B @150 MHz, ~2 cycles) | ~14 ns |
 | Outbound: open-drain pull-down + RC on RDY | ~20 ns |
 | **Total** | **~79 ns** |
 | Available before PHI2↓ within the *same* cycle | ~70 ns |

 **~79 ns does not fit in ~70 ns**, so same-cycle stopping is *not* claimed. The probe instead **asserts RDY for the following cycle**, giving the full 139.7 ns against the ≈79 ns path — ≈61 ns of margin. **Consequence:** the CPU halts having *fetched* the breakpoint opcode but before the instruction completes; the probe reports the breakpoint PC from the latched fetch address and resumes by releasing RDY, after which the instruction executes normally. This is ordinary bus-level-breakpoint behaviour and is invisible to the developer. RDY pull-up/RC values are chosen to keep the outbound edge inside the budget, and the whole path **MUST be validated on a logic analyser against real silicon before probe-firmware freeze**.

2. **Single-stepping:** oito is the clock master (§3) and gates its own PHI2 — no board-level clock mux, and **PHI2 remains an oito output at all times**, so the probe never drives it and there is no contention. The one `DBḠ` wire carries both the mode and the step requests:
 - **`DBḠ` low = debug mode**: oito stops free-running PHI2 and holds it in the low phase.
 - **Each rising edge on `DBḠ` = "advance one cycle"**: oito emits exactly one complete PHI2 cycle, then halts again.
 - **`DBḠ` held high** exits debug mode and resumes free-running.
 - **Acknowledgement is implicit** — the probe observes the PHI2 pulse it requested; no extra pin is needed (the 40-pin header is fixed, §12).
 - Entry and exit are **sampled at a PHI2 cycle boundary**, so a cycle is never truncated mid-phase and CPU timing is never violated.
 The static core preserves all state between pulses.

3. **Register capture — "instruction jamming":** freeze (RDY) → probe raises `DBḠ` → oito **suppresses every external chip select** (RAM, boot flash, cartridge, its own register decode) so nothing else drives the data bus → **the probe drives only D0–D7**, jamming PHA ($48)/PHX ($DA)/PHY ($5A)/PHP ($08) in place of fetches to capture A/X/Y/P as they are pushed, or PLA/PLX/PLY/PLP with probe-supplied bytes to modify; restore PC and release.
 - **`BE` stays HIGH throughout.** WDC specifies BE low makes Address, Data **and R/W̄** high-impedance; since the data buffer is bidirectional, tri-stating it plausibly disables the CPU's data *input* path, in which case the CPU could never consume an injected opcode. Holding BE high also **preserves A0–A15 and SYNC**, so the probe can still see the fetch address and qualify injection on SYNC — information the earlier BE-based scheme discarded.
 - **Clean separation of mechanisms:** **chip-select suppression** is what makes jamming contention-free; **`BE` is reserved for true bus mastering** — when the probe, or oito during a PCM steal, must *own* the address bus.
 - **Validation required:** this rests on CPU-internal data-path behaviour that no datasheet states explicitly. It **MUST be validated on real W65C02S silicon with published cycle waveforms before RTL freeze.**
4. **Function injection (REPL):** jam context-save, jam `JMP $target` (e.g. `game.skipLevel`), run to RTS, jam context-restore, jam `JMP back`. Parameters pass through a **4-byte RAM mailbox at $0010–$0013** (in the runtime ZP reservation §5.0): [command_id, arg0, arg1, arg2] — e.g. `spawnEnemy(type,x,y)` → [cmd, type, x, y].
5. **Live memory access:** while the CPU is halted (RDY) and the probe owns the bus via BE, it reads/writes system RAM and drives VRAM/palette through their ports directly; VRAM/tile dumps can also be streamed. No "bus idle" guessing — halting via RDY + oito CS-control gives the probe deterministic bus ownership.
6. **Autonomous crash detection (best-effort):** configurable heuristics, each disable-able: (a) *hang* = the same ≤3-address cycle repeating for > a threshold (default ~250ms) with no I/O writes; (b) *out-of-bounds execution* = a SYNC-high fetch from an address the IDE's symbol map marks non-code; (c) *stack overflow* = a push after SP wraps below a watermark. These cannot be provably correct for every program (a legitimate idle-loop can look like a hang), so they are advisory: on trigger, freeze + snapshot PC/SP/regs + report; the developer can tune or disable each.
7. **Execution trace:** a rolling ring buffer of the **last 1,024 executed opcode-fetch addresses**, rendered as a call-stack-style timeline in VS Code.
8. **Ghost Debug Port:** probe watches for writes to $4FFF and streams the data byte to the IDE console. 4 CPU cycles per character; zero RAM; inert without a probe attached. Same contract implemented by the emulator.
9. **oito debug TAP (JTAG):** beyond IEEE 1149.1 boundary scan, oito implements a **custom debug TAP**: JTAG instructions select an internal debug address space that mirrors the register file, wave RAM, and a VRAM read window, so palette/line-buffer/blitter/APU state can be read (and injected) over JTAG independent of the CPU. Usable via the probe or off-the-shelf J-Link/FT2232H + OpenOCD.
10. **Dev bootstrap (§11.3):** with a writable **dev cartridge** inserted, the probe halts the CPU and writes a streamed game image (or the firmware updater) into the cart's SRAM over the expansion-header CPU bus — cartridge-less development and firmware flashing with no console USB port and no cable. Small test programs can instead be loaded straight into the 16KB system RAM.

**Shared control lines.** Both the probe and oito can assert **RDY** and **BE**: oito for VRAM-port stalls, OAM DMA and PCM sample steals (§6.5/§8.3); the probe for breakpoints and jamming. Both are therefore **wired-AND / open-drain, asserted-low, either master may pull**. During probe jam cycles oito's debug mode already suppresses chip-selects and **MUST** likewise hold off its own bus-master steals, so a jammed instruction is never interleaved with a PCM fetch. (Practically: entering debug mode pauses PCM streaming; long halts may underrun the audio FIFOs, which is expected while stopped at a breakpoint and self-corrects on resume.)

**Host protocol:** the probe (RP2350B) exposes a **USB CDC/vendor interface speaking a compact binary command set** — halt/run, single-step, read/write memory, set/clear breakpoint, read trace, jam-registers, ghost-port stream, JTAG passthrough. The **VS Code extension's debug adapter translates DAP ↔ this protocol**, so the IDE side is standard Debug Adapter Protocol. Probe firmware uses the MCU's **PIO** to meet the bus timing (a 7.16MHz bus cycle is ~140ns; PIO at 150MHz has ample margin to sample SYNC/address and assert RDY within a cycle).

---

## 14. SDK and tooling

### 14.1 prog8 toolchain (normative language choice)

- **Pipeline:** prog8 (`prog8c -target re8.properties -srcdirs …`) → 6502 assembly → **64tass** → flat `game.bin`. No ELF/DWARF natively; prog8 emits VICE-style label files (`-dumpsymbols`/`-dumpvars`).
- **Why prog8:** (1) static allocation only — no GC, no heap, fixed-size everything, compile-time RAM overflow errors against the declared budget (§5.0), e.g. "15,102 bytes required, 14,720 available"; (2) static parameter cells instead of a software argument stack (a call ≈ one STA) — consequence: **ordinary prog8 subroutines are non-reentrant and do not support automatic recursive parameters**; *manual* recursion remains possible at the programmer's own risk by explicitly saving state, though the **256-byte hardware stack** (§15.10) limits depth far more than the language does. This same non-reentrancy underlies the IRQ-safe subset rule (§14.4); (3) native ubyte/uword types map directly to 6502 registers/ZP arithmetic; (4) machine-agnostic retargeting via a `.properties` file — no compiler fork.
- **Alternatives considered (not pursued):** cc65 (C), LLVM-MOS (C/C++, native DWARF), custom TypeScript-subset transpiler (via C/LLVM-MOS), interpreted languages (rejected outright: interpreter wouldn't fit 16KB). The TypeScript-subset "mass-adoption front-end" idea is **dropped:** prog8 is the single, normative SDK language. A one-language toolchain keeps the debugger, symbol model, and examples coherent and avoids maintaining a second front-end for a solo/boutique project; the LLVM-MOS C path likewise remains only a historical alternative, not a supported SDK target.
- **`re8.properties` — the authoritative file is a versioned artefact in the SDK repository, not this document.** What the target must *achieve* is normative: **65C02 CPU; RAM $0000–$3FFF; zero page $0020–$007F; `pc_start` = $8040** (the header occupies $8000–$803F); **no launcher**; **`romable`**; symbol dumps enabled. The **exact key spellings are not asserted here** — they were never verified against the compiler, so transcribing them would present illustrative text as specification. Instead the SDK repo holds the real file, **versioned as a pair with the pinned `prog8c` hash** (so an upstream key rename cannot silently change a build), and **CI compiles a minimal game against the pinned toolchain on every change** — the only thing that actually validates key names. That CI job also runs the ROM-safety gate and conformance fixture.

Illustrative snippet only: `cpu=65c02`, `pc_start=8040` (header occupies $8000–$803F), `launcher=none`, `ram_start=0000`, `ram_end=3FFF`, `zeropage_start=0020`, `zeropage_end=007F`, `symbols=true`, plus **`romable`**. Custom boot stub emits vectors; custom `syslib.prg` replaces the C64 KERNAL layer (plus suggested `vdp.prg`, `audio.prg`).

- Compiler behaviors relied on: dead-code elimination on the final call tree (unused SDK functions cost nothing; input handlers ≈ <150 bytes), aggressive inlining of register pokes (`set_video_mode` → `LDA/STA`), cross-module constant folding, source-level modules (never binary libraries).
- IRQ ABI: handler returns ubyte in A — 0 = consumed, 1 = run system default (this matches upstream prog8's documented convention exactly). Runtime install mechanism is the RAM-vector trampoline in §14.4.
- **What re8's `syslib` must provide.** Upstream ships `sys.set_irq()`/`sys.restore_irq()` **only for the built-in targets** (c64/c128/pet32/cx16) — they are *target library* routines, not language builtins. A custom target must supply its own, so **re8's `syslib` implements them** over the §14.4 trampoline. (`set_irqd`/`clear_irqd` *are* genuine builtins and are used as-is.) Likewise, prog8 documents that **bank switching is not built into the language** for general data access — only `extsub … @bank N` *calls* are made transparent by the compiler — so `use_data_bank(n)` / `restore_data_bank()` (§14.2) are **re8 SDK routines**, not compiler features.
- **ROM execution — `%option romable` is normative.** A cartridge executes from **flash**, so nothing in the image may be written at runtime. Upstream prog8's ordinary 6502 output **may contain self-modifying code and inline variables**, which is fine for RAM-loaded C64 programs and fatal here; ROM-safe output requires **`%option romable`**, which upstream marks **experimental** and which requires BSS to be placed explicitly in RAM. Therefore:
 1. **`%option romable` MUST be set by the re8 target**; BSS is located in **$0200–$3FFF**.
 2. **Initialised mutable data lives in ROM and is copied to RAM before `main`** by a startup routine, driven by a copy table the build emits. Read-only data stays in ROM.
 3. **Build-time ROM-safety gate:** the toolchain **MUST fail the build** if any relocation, initialised-data write target, or self-modifying construct resolves outside **$0000–$3FFF**. This gate — not the compiler's reputation — is the actual guarantee.
 4. **Conformance fixture:** a representative SDK + game sample is compiled and its **map, startup stub and generated assembly published as a versioned artefact** that this spec links to.
- **Validation status (honest statement).** Until items 3 and 4 pass with the pinned compiler, **prog8 is the *selected* SDK language whose ROM-ability is pending validation**, not a settled property. If `romable` proves inadequate for a 1MB banked cartridge, the fallbacks are a compiler patch (upstream is a single receptive maintainer) or revisiting the language choice in favour of cc65/LLVM-MOS. This is recorded now rather than discovered at SDK bring-up.
- **Version pin:** the SDK is built against an **exact pinned toolchain — a named prog8 release *and* its commit hash, a named 64tass version, and the required JVM** — recorded in the SDK repository and bundled with the VS Code extension (§14.3). A floor such as "≥ 12.0" is **not** a pin: it admits future incompatible behaviour, contradicting the "known-good bundled binary" intent. Language features the SDK depends on: the function-reference type (`subref`/`subref[]` callback tables), `struct`, memory-mapped vars (`@ $ADDR`), and the `-dumpvars`/`-dumpsymbols` symbol dumps. *(`extsub … @bank N` is no longer a dependency — re8 uses SDK far-call wrappers.)* Any example syntax (subref arrays, string params) is authoritative only against the pinned binary; the bundled compiler is the source of truth, and SDK examples are validated against it at build time.

### 14.2 re8 library (`re8` / `re8_engine` modules)

Design rule: *game code never contains a hex address* — all registers are private `const uword` inside SDK modules; hardware revisions only update the SDK.

Documented API surface (final, event-driven style):

- `re8.input`: `set_handler(JOYSTICK_BUTTON_A, &fn)` (constants incl. JOYSTICK_BUTTON_A/B/START; internally a `subref[8]` callback table indexed by button, dummy-initialized), `button_pressed(id) -> bool`, `input.held(...)` (tooling mockups).
- `re8.collision`: `set_handler(&fn(ubyte a, ubyte b))`; an earlier design sketched a richer per-type registry (`sprite_type_registry[32]`) + type×type callback matrix (18 bytes RAM for 3 types) + `on_collision(TypeA, TypeB, cb)` — retained as an optional SDK convenience layer over the base handler.
- `re8.sprites`: `kind(id)`, `set_anim(id, ANIM)`, `destroy(id)`, `draw_sprite(asset_id, x, y)`.
- `re8.psg` / audio: `play(SFX_ID)` / `play_sfx(id)`; **PCM (§8.3):** `play_pcm(SAMPLE_ID, voice)` / `stop_pcm(voice)` resolving through an asset-pipeline **sample table** (20-bit linear cart address + loop/end per sample — samples may exceed 16KB and cross banks); `pcm_suspend()` / `pcm_resume()` to guarantee a steal-free window for cycle-exact raster code.
- Video: `set_video_mode(VIDEO_LOW_RES|VIDEO_HI_RES)`, `draw_graphic(ASSET_ID, x, y)`.
- `re8.text` (text overlay, §6.8): `enable()`/`disable()`, `put(col,row,str)`, `put_char(c)`, `scroll(x,y)` (whole-plane fine offset), `set_font(FONT_CART)` (bank select), `caret(col,row)`; the opaque-bg attribute drives dialogue/menu panels.
- `re8.keyboard` (§9.1): detection `present()` / `on_connect()`/`on_disconnect()`; cooked input `get_char() -> ubyte` (Latin-1 = §6.8 glyph index) and `on_char(&fn)`; raw `on_key(&fn(code,flags))` (MAKE/BREAK) with `KEY_*` constants; modifiers `shift_held()`/`ctrl_held()`/`caps_on()`; **line-input field widget** `field_begin(buf,maxlen,col,row)` / `field_poll() -> EDITING|DONE|CANCEL` / `field_end()` (echoes into `re8.text` + hardware caret); `set_layout(LAYOUT_US|…)`; `joypad_passthrough(bool)`.
- `re8.mouse` (§9.2): `present()`; hardware cursor `set_cursor(TILE, hotx, hoty)`, `set_speed(n)`, `set_bounds(x0,y0,x1,y1)`, `set_source(AUTO|MOUSE|DPAD|OFF, player)` (pointer arbitration — default AUTO = mouse-first), `show()`/`hide()` (game does no cursor drawing); events `on_move(&fn(x,y))`, `on_button(&fn(buttons))`, `on_wheel(&fn(delta))`; pollable `x()`/`y()`/`buttons()`; **hardware hit-test** `hit_sprite->ubyte` (0xFF none), `hit_cell(plane) -> (col,row)`, `hit_tile(plane) -> uword` (full 12-bit index), `pick_at(x,y)` / `pick_follow_cursor()` — read on a click to learn the clicked sprite/tile with no CPU math.
- Banking: `use_data_bank(n)` / `restore_data_bank()` (8-deep stack); asset tables map level IDs → (bank, offset) → `copy_to_vram(src, len)`.
- `re8.save`: `available() -> bool`, `read(dst, offset, len)`, `write(src, offset, len)`, `size()`. Each call runs from the fixed bank and wraps the whole sequence — clear write-protect → open the save window ($4081) → transfer → close → re-protect — so game code never sees the window swap.
- `debug`/`re8.log(string)` → pokes $4FFF per character; static strings live in ROM `.rodata`.
- `engine.run()` main-loop primitive; `game_over()`, score, etc. shown in examples.

### 14.3 VS Code extension

- Commands: `re8.project.create`, `re8.emulator.launch`, `re8.vram.inspect`, `re8.hardware.connect`.
- Zero-config build (bundled toolchain binaries; `re8-config.json`; memory-allocation meter; readable overflow errors).
- **Source-level debugging without an OS:** post-processor parses the 64tass listing (**`-L <file>` / `--list=<file>`**, optionally with `--line-numbers`/`--verbose-list` — *not* `--make-list`, which is not a 64tass option) (`Line 42 (main.prg) → $80A2 …`), synthesizes a dummy assembly file of `.file/.loc/.byte` directives, compiles it with `clang -g` into a **code-free ELF whose DWARF line tables are real**; the debugger loads this ELF for symbols while hardware runs `game.bin`. The synthesized ELF supplies **line tables only**; variable watch/hover comes from a separate typed-symbol model (§14.4).
- **Debug-info pipeline status — pending validation.** The synthesized-ELF approach is a **plan with a fallback**, not a verified pipeline:
 - **Bank-aware identity is mandatory.** With per-bank compilation the address `$8100` exists in **all 64 banks**, so breakpoints and symbols are keyed on **(bank, address)** — never address alone, matching the symbol rule of. The probe's hardware breakpoint therefore qualifies on address **AND** current bank; it can do so with no new signal, because it already sniffs the bus and sees writes to `$4080`, letting it shadow `BANK_SELECT` in real time. Without this a breakpoint set in bank 3 would fire in every bank.
 - **Proof fixtures required:** a sample project whose generated artefacts are checked in and validated in **CI on each supported host** (Linux/macOS/Windows) and debugger, exercising line tables, function names, breakpoint set/hit, **stepping**, and **banked duplicate addresses**.
 - **Fallback, entirely under our control:** if a code-free `clang -g` ELF proves unreliable across debuggers, the adapter serves line information **directly from its own map file over DAP**, bypassing DWARF altogether. That this fallback exists is why the plan is acceptable to carry.
- Debug UX: breakpoints/step/current-line highlight, hover value inspection via live USB reads, watch streaming during VBLANK, crash overlay with structured diagnostics, trace-based call timeline.
- **VRAM inspector:** live tile grid (decode: 32 bytes/tile, two 4-bit pixels per byte), sub-palette selector, hover address/index, active-scanline highlight, OAM/sprite list with positions and collision flags; identical data bridge from either the WASM emulator or the physical probe.
- REPL/immediate console: `player.hp = 99`, `game.skipLevel`, `spawnEnemy(type,x,y)` etc., implemented as raw memory writes or probe function injection.
- Asset pipeline: PNG/`.r8a` editor webview constrained to hardware limits (16 colors/tile from 12-bit palette); file watcher packs 4-bit indexed tile binaries and regenerates autocompletion headers.
- Hot reload: new binary fed into the running WASM emulator without restart.

### 14.4 Runtime IRQ vectoring & debug-info model

**IRQ install on bare metal.** The cartridge's fixed-bank vector at $FFFE/F is set at build time to a small syslib stub, `__irq_entry`, *not* to the user handler directly. The stub **calls** the RAM-vectored handler by pushing a synthetic return address before an indirect jump — a plain `JMP ($0014)` would have been a *jump*, leaving the handler's `RTS` to pop the interrupted code's return address :

```
__irq_entry: ; $FFFE/F → here, in the fixed bank
 PHA
 TXA : PHA
 TYA : PHA
 CLD ; 6502 IRQs do NOT clear decimal mode; prog8 assumes binary
 LDA #>(__irq_ret-1) ; push return address − 1, high byte first
 PHA
 LDA #<(__irq_ret-1)
 PHA
 JMP ($0014) ; handler's RTS returns here
__irq_ret:
 CMP #0 ; A = handler result: 0 = consumed, 1 = chain
 BEQ +
 JSR __sdk_default_irq
+ PLA : TAY
 PLA : TAX
 PLA
 RTI
```

**IRQ-safe subset.** This is the root cause behind the re-entrancy caveats elsewhere in this section. prog8 subroutines are **non-reentrant because parameters live in fixed cells**, so a callback that calls an SDK routine the main program is already inside **overwrites that routine's parameters mid-call**. Since the SDK's headline feature is event-driven callbacks, "event-driven" was doing rhetorical work that "safe" had not earned.

- **Rule:** an IRQ handler **MUST** call only routines marked `@irqsafe`. These use **no shared static parameter cells** — arguments pass in registers or in the IRQ-only scratch at ZP **$00–$01** (already reserved in §5.0).
- **In the safe subset:** reading `IRQ_STATUS` / `INPUT_STATUS` / `JOYPAD_*` / `KBD_SCAN` / `MOUSE_*`, acknowledging IRQ bits, setting flags in the handler's own variables, and single register pokes.
- **Excluded:** `far_call`, `use_data_bank()`, `re8.save.*`, `re8.text.put`, blitter helpers, and anything taking a string.
- **Documented idiom, now normative:** a handler should **set a flag and return**, with the real work done in the main loop — §10 hinted at this but never required it.
- **Nested IRQs MUST NOT occur:** the wrapper does not re-enable interrupts, so a handler cannot preempt itself.
- **Dispatcher clobber list:** ZP **$00–$01** (scratch), **$02** (event flags), **$03–$04** (frame counter), **$0A** (bank shadow). A handler **MUST NOT** assume these survive.
- **Enforcement is mechanical:** `@irqsafe` is checked at build time by walking the handler's call tree — the same analysis the SDK's dead-code elimination already performs.

**Bank safety across interrupts.** `BANK_SELECT` ($4080) is global mutable state with three parties: main-line code (`far_call`, `use_data_bank()`), IRQ handlers, and **oito itself during PCM steals** — only the PCM path already restores the bank explicitly (§8.3). The dangerous case is concrete: main code selects bank 7 to read level data, an IRQ fires and switches to bank 3, and on return the main code keeps reading **bank 3** believing it is bank 7 — silent corruption.

- **`__irq_entry` saves and restores `BANK_SELECT`** via the ZP bank shadow ($0A, §5.0): push on entry, restore before `RTI`. ≈8 bytes and ≈12 cycles on top of the prologue, and it makes handlers safe **by construction rather than by discipline**.
- **`far_call` MUST NOT be used inside IRQ handlers.** The save/restore is a **safety net, not a licence** — a handler making far calls still depends on prog8's non-reentrant static cells, so the SDK's IRQ-safe subset excludes it.
- **Bank-stack updates are atomic:** `use_data_bank(n)` / `restore_data_bank()` wrap the push/pop in **SEI/CLI**, so an interrupt can never observe or corrupt a half-updated stack.
- **Overflow/underflow saturates and sets an SDK-readable error flag** rather than wrapping — silent wrap-around would corrupt bank state invisibly, the worst available outcome.
- **`far_call` MUST NOT be used while the save window is open** (§11.0), since the window hides the ROM bank; debug builds assert on it.

**ABI (normative).** The wrapper saves and restores **A, X, Y** (the CPU stacks P and PC); handlers need not preserve them. **`CLD` is issued by the wrapper** — the 6502 does not clear decimal mode on interrupt, and prog8 assumes binary arithmetic. The consume/chain result is sampled from **A immediately on return**, before any restore. Cost ≈ 13 bytes, ≈ 20 cycles of prologue. The **NMI vector points at the address of a real `RTI` instruction** in the fixed bank (not "conceptually a bare RTI"). *Re-entrancy caveat:* because the handler is a called routine, it may call **only `@irqsafe` SDK routines** — see the IRQ-safe subset in §14.4. The RAM vector is initialized to a default handler (VBLANK frame-counter tick, else `RTI`). `sys.set_irq(&fn)` is then simply an **atomic write of that RAM cell** — wrapped by `sys.set_irqd()`/`sys.clear_irqd()` (SEI/CLI) so an interrupt can't fire mid-update. This is the classic C64 CINV pattern retargeted to a fixed RAM cell instead of a KERNAL vector; no OS is required. (NMI is unused system-wide; its $FFFA/B vector points at the address of a real `RTI` instruction.) The handler's ubyte return (§14.1: 0 = consumed, 1 = fall through) lets the stub optionally chain to the SDK default before `RTI`.

**Variable watch/hover.** prog8 uses **static allocation with no runtime stack frames** — every variable and every subroutine parameter lives at a fixed address. A flat, typed symbol table therefore describes *all* program state; there are no stack-relative locals needing DWARF frame-base computation. So the debug adapter does **not** synthesize `.debug_info` for the prog8 path. Instead it builds its own symbol model from prog8's **`-dumpvars`** output (name → address → prog8 type: ubyte/uword/byte/word/bool/arrays/structs) and serves watch/hover by reading memory (live USB read or emulator) and formatting per that type. **Typed-symbol source — an open dependency with a defined resolution path.** The typed-symbol model is sound, but its *data source* is unconfirmed: `-dumpvars` may carry only names and addresses rather than types. This is closed by **choosing**, not hoping:

1. **Capture reality first** — run the pinned `prog8c`, record the actual `-dumpvars`/`-dumpsymbols` formats, and archive samples as **versioned fixtures**.
2. **Select one source, in preference order:** (a) `-dumpvars` if it genuinely carries types; (b) otherwise **the SDK build emits its own type table** alongside the symbol dump — mechanical and entirely under our control; (c) a small upstream patch only if neither suffices.
3. **Version the schema.** Whatever the source, the debug adapter consumes a **versioned typed-symbol schema**, so a compiler change fails the build visibly instead of silently mis-rendering watch values.
4. **Required test coverage:** arrays, structs, aliases, private/nested scope names, and **banked symbols** — the last matters because per-bank compilation means the same CPU address exists in several banks, so **symbol identity is (bank, address), not address alone**. Breakpoint identity has the same requirement and shares the fix.

Until this is settled against the pinned binary it remains a **dependency, not an established fact**. The two symbol inputs each have exactly one job — the 64tass listing gives line↔address (for stepping/breakpoints via the synthesized ELF), `-dumpvars` gives typed symbols (for inspection) — so they're complementary, not competing (this retires the old "two symbol paths" concern). With the TypeScript/LLVM-MOS front-end dropped, this typed-symbol model is the single debug-info path.

### 14.5 Reference emulator

**Accuracy tiers.** The front matter has always said "non-cycle-perfect emulator" while this section asked for "cycle-accurate" line rendering — a contradiction that survived every revision. Two named tiers replace it, and **Tier 1 is what "the reference emulator" means**:

**Tier 1 — compatibility (the conformance target).** Runs any conforming cartridge correctly:

- instruction-correct CPU, with the documented RDY stalls (VRAM port, OAM DMA, PCM steals — §3/§6.5/§8.3) modelled **in aggregate** rather than cycle-exactly;
- **scanline-timed VDP**, with **per-pixel palette sampling**, the **shadow-OAM snapshot at line 224**, and **hit-test sampled at the pick pixel**;
- **sample-accurate APU** per §8.5, reproducing the golden audio hash;
- blitter work completing against the §6.5 bandwidth budget;
- **input as timestamped events**, quantised to the ~2.5 ms acquisition cadence.

**Tier 2 — cycle-exact (optional refinement).** Adds exact display-fetch scheduling and arbitration, precise RDY stall counts, mid-scanline raster effects at cycle resolution, and exact placement of DMA and PCM steals.

**Golden conformance ROMs validate Tier 1.** Tier 2 is explicitly **not required for compatibility**.

C++ or Rust core compiled to WASM, hosted in a VS Code webview; **Tier 1** line-rendering/blitting behaviour (Tier 2 cycle-exactness is a later, optional refinement — see the tiers above); host keyboard/USB-gamepad input mapped through the **timestamped input-event model**, not sampled once per frame; ghost-port hook (`if (addr == 0x4FFF) send_to_console(byte)`); shares the VRAM-inspector bridge with the probe. Internal architecture (scheduler, timing granularity, PSG model, save states, accuracy validation) entirely unspecified — that is precisely what the emulator-planning stage must define.

---

## 15. Known restrictions (hard limits)

1. 16,384 bytes system RAM total — **≈14.4 KB (14,704 B) available to game code** after ZP, hardware stack, the 1 KB shadow-OAM buffer and SDK structures (full budget in §5.0; the former "≈15.5 KB" predated shadow OAM). Compile-time enforced against the *real* remainder.
2. No dynamic memory. **Ordinary subroutines are non-reentrant** (static parameter cells): no *automatic* recursion. **Manual** recursion is possible with programmer-managed state, bounded in practice by the 256-byte hardware stack (restriction 10).
3. 64KB CPU address space; cartridge access only through one switchable + one fixed 16KB window.
4. 64 simultaneous colors (4 × 16 sub-palettes) from 4,096; color 0 of each sprite palette transparent; 16 colors max within one tile.
5. 128 hardware sprites; 32 per scanline.
6. 240p progressive only (256×224 / 320×224 @60Hz); no interlace, no 480i; **60Hz-only worldwide, no 50Hz PAL mode**.
7. 16-voice APU: 4 PSG (3 pulse + 1 noise) + 8 wavetable + 4 PCM/ADPCM (§8); no FM operators (deliberate — flexibility + emulability over Genesis-style FM).
8. Blitter throughput: **≥1,000 tiles/frame interleaved / ≥350 blanking-only**, guaranteed under the §6.5 benchmark workload (opaque tile copy, pitch 0, both BG planes, no sprites, text off). Other modes and loads are lower — see §6.5.
9. CPU reaches VRAM only through the $4044 port and is RDY-stalled during bus contention (§6.5); bulk VRAM work is fastest in the 38-line VBLANK window but is legal any time.
9a. **PCM streaming steals CPU cycles**: oito bus-masters the CPU bus to fetch samples from cart ROM, costing ≈**2.7–6 % of CPU cycles** under the §8.3 workload (4 voices, 8-bit, 48 kHz). PCM sample addresses are **20-bit (1MB, the cart limit)**. The nominal 455 cycles/line is a *bus* budget; RDY stalls from PCM, the VRAM port and OAM DMA reduce instruction throughput (§3).

10. Single IRQ, no NMI; 256-byte hardware stack (callback nesting is the documented "interrupt hell" risk).
11. Digital video is **DVI-D 1080p60, video-only** (no HDMI/HDCP/TERC4-audio/CEC), fixed via CH7035B Strategy-A self-boot — no runtime mode changes. Digital audio is a separate royalty-free **optical S/PDIF** output (§8.4); the design carries no HDMI-only signalling; the **licensing conclusion itself requires counsel**.
12. Saves use **on-cart FRAM only** (`FM18W08`, battery-free, 16KB), oito-decoded via a per-access-pulsed SAVE_CĒ (§11.4); **no EEPROM**, no battery-backed SRAM, no console-side shared NVRAM. Digital/SD titles save to `.sav` files on the SD card.
13. Keyboard & mouse are **PS/2 only** (no USB-HID), reached through a controller port via a passive adaptor (§9.1/§9.2); the PS/2 host is bidirectional, so keyboard LEDs are supported. With two ports total, a keyboard or mouse occupies one — the realistic combinations are joystick+keyboard, joystick+mouse, or keyboard+mouse, never all three. Simultaneous-key limits come from the keyboard's own matrix ghosting rather than the interface, which is NKRO-capable. Each port supplies ≤250 mA at 5V (§2.1).
14. Mouse cursor is **hardware-rendered by oito** as an absolute-top layer (§9.2) — **one VRAM tile in 8×8 mode, four consecutive tiles in 16×16 mode**, not a sprite; the game supplies only the tile, hotspot, and velocity and receives move/click/wheel events (no software cursor drawing).
15. The DE-15 output carries **15 kHz analog RGBHV, not VGA timing** — standard PC monitors will not sync (it targets CRTs/PVMs/upscalers) — and carries no audio.
16. Cartridge max 1MB (64 × 16KB banks) as designed.

---

## 16. Conformance & validation

This section is the **acceptance contract**: what an implementation must reproduce, and what must still be proven on real parts.

### 16.1 Emulator conformance (Tier 1)

An implementation claiming Tier 1 (§14.5) **MUST** reproduce:

| Artefact | Definition |
|---|---|
| **Register model** | every register in §5.1 with its reset value, mask, read/write side effects and unmapped behaviour (**$00**, §5.1) |
| **Golden framebuffer hashes** | per-frame hashes for conformance ROMs exercising both BG planes, all sprite sizes, priority ladder, collision, blitter modes, text overlay and cursor/pick |
| **Golden audio hash** | PCM output of a fixed register-write script plus sample ROM, bit-exact (§8.5) |
| **IRQ trace** | ordered `(cycle, source)` list for a fixed program — VBLANK, collision, input, raster-compare, blitter-done |
| **Bank/save behaviour** | `BANK_SELECT` masking, fixed-bank derivation, save-window swap, `.sav` image and CRC keying (§11) |
| **Reset & handoff state** | the §11.1.1 handoff table, byte-identical between canonical-boot and fast-boot paths |

Tier 2 (cycle-exact) is **OPTIONAL** and is not required for compatibility.

### 16.2 Hardware validation still outstanding

These are **unproven on real parts** and gate schematic freeze or tape-out:

| Item | Criterion | Ref |
|---|---|---|
| CH7035B qualification | accepts both native geometries via `DE`; true nearest-neighbour; 1080p60 out; latency ≤1 frame; register image archived | §7.1 |
| AD725 240p operation | colour lock, burst insertion, vertical lock on CRTs **and** capture devices/upscalers | §7 |
| W65C02S instruction jamming | opcode injection with `BE` high and chip-selects suppressed, on silicon, with published waveforms | §13 |
| Breakpoint timing | RDY asserted within the following cycle, measured on a logic analyser | §13 |
| prog8 ROM-ability | `%option romable` output with **no** write target outside $0000–$3FFF, proven by the build gate and a published fixture | §14.1 |
| Typed-symbol source | actual `-dumpvars` format captured; typed-symbol schema selected and versioned | §14.4 |
| Debug-info pipeline | line tables, stepping and **banked duplicate addresses** proven per host | §14.3 |
| Package pinout | full 144-pin table: per-state directions, pad types, drive classes, bank supplies | §6.3 |
| Licensing position | HDMI/DVI/S-PDIF review by counsel before commercialisation | §7.1 |

### 16.3 Rules that keep this document honest

- **Every performance figure MUST carry a stated workload or the label *estimate*.** No cross-machine comparisons.
- **This document states only current values.** Superseded values, alternatives and rationale live in `re8-design-history.md`.
- **Rationale, alternatives and resolution history live in `re8-design-history.md`, which is not normative.**

---

## 17. Design history

The architectural decision log, the gaps & inconsistencies registers from both adversarial reviews, and the source provenance live in **`re8-design-history.md`**.

That document records *why* each choice was made and what was rejected. It is **not normative**: where it and this specification disagree, this specification wins and the disagreement is a defect.

---

## 18. Version history

This specification is versioned so that a cartridge, an emulator or a board revision can state precisely which contract it was built against.

### 18.1 Versioning rules

| Change | Effect |
|---|---|
| **Machine-visible behaviour** — any register, bit field, reset value, timing, data format, memory-map or ABI change | **MUST** bump the version. Before 1.0 this is a **minor** bump; after 1.0 it is a **major** bump and **MUST** carry a compatibility note naming what breaks |
| **New capability** that does not alter existing behaviour | minor bump |
| **Clarification, correction of an error, or editorial work** that leaves behaviour unchanged | recorded in the table below; a **patch** bump (0.1.1) is used when a released version needed correcting |
| **Rationale, alternatives, review history** | no bump — these live in `re8-design-history.md`, which is not normative |

**Milestones.** **0.x** are pre-freeze drafts: machine-visible behaviour may still change between them. **1.0** is the *compatibility freeze* — it is issued only once every item in §16.2 has been validated on real parts, and from that point the register map, timing and file formats are fixed for the life of the platform.

**Related versions.** Two artefacts carry their own version numbers because software can observe them independently: the **handoff-state version** (§11.1.1), bumped whenever boot firmware changes the state a cartridge starts in, and the **cartridge header version** ($04, §11.2). Neither is implied by this document's version.

### 18.2 Revisions

| Version | Date | Summary |
|---|---|---|
| **0.1** | 2026-07-26 | **First tagged version.** Establishes the complete baseline: W65C02S at 7.159 MHz with the oito ASIC (LQFP-144); the canonical `$4000–$40FF` register file; 128 KB VRAM with defined arbitration; two BG planes, 128 sprites, blitter, collision and the priority ladder; the text overlay and hardware cursor with hit-testing; the 16-voice APU with its reference model; five simultaneous video outputs plus optical S/PDIF; PS/2 keyboard and mouse over the controller ports; the two-stage boot ROM, cartridge format and FRAM saves; the prog8 toolchain and debug probe; and the conformance contract of §16. Incorporates the resolution of two adversarial reviews (see `re8-design-history.md`). |

*Add each subsequent revision as a new row at the top of this table, newest first.*

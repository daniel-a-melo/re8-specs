#!/usr/bin/env python3
"""
Inject the bus model's generated tables into re8-console-spec.md.

Blocks are delimited by HTML comments, which survive Markdown rendering
invisibly:

    <!-- GENERATED bus.read_timeline -->
    ...table...
    <!-- END GENERATED -->

`--check` verifies the file is current without writing (used by
tools-verify.py); with no argument it rewrites the blocks.

The point of generation is narrow and worth stating: these tables were the
subject of 13 of the 19 blockers found in rounds 10-14, always because a
sentence somewhere else described a different machine. A generated table cannot
disagree with the model, so that failure mode is closed by construction rather
than by another checker pattern.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).parent
SPEC = ROOT / "re8-console-spec.md"

# exec'd from SOURCE, not imported. importlib caches bytecode in __pycache__, so
# an injector that imports can silently inject a STALE model -- which it did:
# render_effect_matrix was rewritten and this script reported "0 regenerated".
# tools-verify.py was fixed for exactly this in round 9; the lesson did not
# travel to the next script that needed it.
class _Bus:
    pass


bus = _Bus()
# __file__ must be supplied: tools-bus-model.py uses it to locate tools-model.py.
bus.__dict__["__file__"] = str(ROOT / "tools-bus-model.py")
bus.__dict__["__name__"] = "bus"
exec(compile((ROOT / "tools-bus-model.py").read_text(), "tools-bus-model.py", "exec"),
     bus.__dict__)

BLOCK = re.compile(
    r"(<!-- GENERATED (?P<name>[\w.]+) -->\n)(?P<body>.*?)(<!-- END GENERATED -->)",
    re.S)


def rewrite(text):
    missing, changed = [], []

    def sub(m):
        name = m.group("name")
        if name not in bus.BLOCKS:
            missing.append(name)
            return m.group(0)
        new = bus.BLOCKS[name]() + "\n"
        if new != m.group("body"):
            changed.append(name)
        return m.group(1) + new + m.group(4)

    out = BLOCK.sub(sub, text)
    return out, missing, changed


def main():
    text = SPEC.read_text()
    out, missing, changed = rewrite(text)
    present = {m.group("name") for m in BLOCK.finditer(text)}
    absent = sorted(set(bus.BLOCKS) - present)

    if "--check" in sys.argv:
        problems = []
        if missing:
            problems.append(f"unknown generated block(s): {missing}")
        if absent:
            problems.append(f"model block(s) not placed in the spec: {absent}")
        if changed:
            problems.append(f"stale generated block(s): {changed} — "
                            f"run tools-bus-inject.py")
        for p in problems:
            print(f"  BUS     {p}")
        return 1 if problems else 0

    if out != text:
        SPEC.write_text(out)
    print(f"  bus tables: {len(present)} block(s), "
          f"{len(changed)} regenerated" + (f", MISSING {absent}" if absent else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

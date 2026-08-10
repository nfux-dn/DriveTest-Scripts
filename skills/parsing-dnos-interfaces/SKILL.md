---
name: parsing-dnos-interfaces
description: Correctly discover and parse interfaces from DNOS `show interfaces description` inside a DriveTest test. Use when a test needs to list interfaces, filter by name (e.g. `ge`), read/verify interface descriptions, or when parsing DNOS show-command tables. Prevents the common bug where a naive split() reads the table border `|` as the interface name and matches nothing.
disable-model-invocation: true
---

# Parsing DNOS interfaces

## The gotcha (why a naive parser returns zero interfaces)

Real DNOS `show interfaces description` is a **pipe-delimited, bordered table**
with a `Legend:` line, a header row, and `+---` separators:

```text
Legend: i - inner vlan, b - interface disabled due to breakout, ...

| Interface        |  Admin   | Operational | Description |
+------------------+----------+-------------+-------------+
| ge800-0/0/0      | enabled  | down        |             |
| ge800-0/0/20     | disabled | not-present |             |
| ge400-0/0/20/0   | enabled  | up          |             |
| ge100-0/0/28/7   | enabled  | up          | uplink-7    |
```

A naive `line.split()[0]` returns `|` (the border), so `startswith("ge")` matches
**nothing** and the test does nothing. The simulated dev device prints a plain
whitespace table instead, so code that "worked in dev" silently fails on a real box.

## Use a parser that handles both formats

```python
def parse_interfaces(text: str) -> dict[str, dict[str, str]]:
    """{name: {"oper": ..., "description": ...}} from `show interfaces description`.
    Handles the real DNOS pipe table AND the plain whitespace table."""
    result: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("+") or line.lower().startswith("legend:"):
            continue
        if line.startswith("|"):                      # pipe-delimited (real DNOS)
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 3 or cells[0].lower() == "interface":
                continue
            name, oper = cells[0], cells[2]
            description = cells[3] if len(cells) > 3 else ""
        else:                                          # whitespace table (simulator)
            low = line.lower()
            if low.startswith("interface") and "description" in low:
                continue
            parts = line.split(None, 3)
            if not parts:
                continue
            name, oper = parts[0], (parts[2] if len(parts) > 2 else "")
            description = parts[3].strip() if len(parts) > 3 else ""
        result[name] = {"oper": oper, "description": description}
    return result
```

## Filtering rules

- Match by **name prefix** (e.g. `name.startswith("ge")`). DNOS names look like
  `ge800-0/0/0`, `ge400-0/0/20/0`, `ge100-0/0/28/7`, `ge25-0/0/65`.
- **Skip `oper == "not-present"`** — these are breakout parent ports that are split
  into children (e.g. `ge800-0/0/20` -> `ge400-0/0/20/0`, `ge400-0/0/20/1`).
  Configuring the not-present parent errors on commit.
- Both the parent and its broken-out children appear in the table; you usually want
  the present children, not the not-present parent.

```python
interfaces = parse_interfaces(dut.run("show interfaces description"))
targets = [n for n, i in interfaces.items()
           if n.startswith("ge") and i["oper"] != "not-present"]
```

## Getting the output (device access)

Always via the Run-owned session (never your own SSH):

```python
from drivetest import ExecutionContext
dut = ExecutionContext.from_env().device("dut")
text = dut.run("show interfaces description")
```

If a box paginates long show output with a `--More--` pager, request
`dut.run("show interfaces description | no-more")` (`| no-more` is a DNOS show-only
suffix; do not use it inside `configure`).

## Verify-after-config pattern (descriptions)

Capture the description map before and after, and compare per interface:

```python
def descriptions(parsed): return {n: i["description"] for n, i in parsed.items()}

before = descriptions(parse_interfaces(dut.run("show interfaces description")))
# ... configure + commit ...
after = descriptions(parse_interfaces(dut.run("show interfaces description")))
mismatches = {n: (want[n], after.get(n)) for n in want if after.get(n) != want[n]}
```

## Worked example

`suites/interfaces/tests/interface-description-change/test.py` uses exactly this
parser and filter to set, verify, and roll back interface descriptions.

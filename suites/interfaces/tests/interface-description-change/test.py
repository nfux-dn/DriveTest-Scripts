"""interface-description-change (DNOS).

Flow (spec section 51 - device access via ExecutionContext, never direct SSH):
1. show interfaces description (baseline)
2. for every present 'ge' interface, choose a random description and set it
3. commit
4. show interfaces description and verify each ge interface applied
5. rollback 1 + commit
6. show interfaces description and verify it returned to baseline
"""

import random

from drivetest import ExecutionContext


def parse_interfaces(text: str) -> dict[str, dict[str, str]]:
    """Parse `show interfaces description` into {name: {oper, description}}.

    Handles the real DNOS pipe-delimited table AND the plain whitespace table.
    """
    result: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("+") or line.lower().startswith("legend:"):
            continue

        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 3 or cells[0].lower() == "interface":
                continue
            name = cells[0]
            oper = cells[2] if len(cells) > 2 else ""
            description = cells[3] if len(cells) > 3 else ""
        else:
            low = line.lower()
            if low.startswith("interface") and "description" in low:
                continue
            parts = line.split(None, 3)
            if not parts:
                continue
            name = parts[0]
            oper = parts[2] if len(parts) > 2 else ""
            description = parts[3].strip() if len(parts) > 3 else ""

        result[name] = {"oper": oper, "description": description}
    return result


def descriptions(parsed: dict[str, dict[str, str]]) -> dict[str, str]:
    return {name: info["description"] for name, info in parsed.items()}


def main() -> None:
    ctx = ExecutionContext.from_env()
    dut = ctx.device("dut")

    baseline = parse_interfaces(dut.run("show interfaces description"))
    # Present 'ge' interfaces only (skip breakout parents marked not-present).
    ge_interfaces = [
        name
        for name, info in baseline.items()
        if name.startswith("ge") and info["oper"] != "not-present"
    ]

    if not ge_interfaces:
        ctx.write_result(
            {
                "execution_status": "COMPLETED",
                "test_id": ctx.test_id or "interface-description-change",
                "test_verdict": "FAILED",
                "measurements": {"ge_interfaces": 0},
                "observations": ["No configurable 'ge' interfaces found."],
                "evidence": [],
                "artifacts": [],
            }
        )
        return

    planned = {name: f"drivetest-{random.randint(1000, 9999)}" for name in ge_interfaces}

    tree: list[str] = ["interfaces"]
    for name, description in planned.items():
        tree += [f"  {name}", f'    description "{description}"', "  !"]
    tree += ["!"]
    dut.configure(tree)
    dut.commit()

    after = descriptions(parse_interfaces(dut.run("show interfaces description")))
    applied_mismatches = {
        name: {"expected": planned[name], "actual": after.get(name)}
        for name in planned
        if after.get(name) != planned[name]
    }

    dut.rollback(1)
    dut.commit()

    baseline_desc = descriptions(baseline)
    reverted = descriptions(parse_interfaces(dut.run("show interfaces description")))
    revert_mismatches = {
        name: {"expected": baseline_desc.get(name, ""), "actual": reverted.get(name)}
        for name in planned
        if reverted.get(name) != baseline_desc.get(name, "")
    }

    applied_ok = not applied_mismatches
    reverted_ok = not revert_mismatches
    verdict = "PASSED" if (applied_ok and reverted_ok) else "FAILED"

    ctx.write_result(
        {
            "execution_status": "COMPLETED",
            "test_id": ctx.test_id or "interface-description-change",
            "test_verdict": verdict,
            "measurements": {
                "ge_interfaces": len(planned),
                "applied_ok": applied_ok,
                "reverted_ok": reverted_ok,
                "apply_mismatch_count": len(applied_mismatches),
                "revert_mismatch_count": len(revert_mismatches),
            },
            "observations": [
                f"Configured {len(planned)} present ge interface(s) with unique descriptions.",
                "All descriptions applied as configured." if applied_ok else f"Apply mismatches: {dict(list(applied_mismatches.items())[:5])}",
                "State restored to baseline after rollback 1." if reverted_ok else f"Revert mismatches: {dict(list(revert_mismatches.items())[:5])}",
            ],
            "evidence": [
                {"source": "sample_planned", "details": dict(list(planned.items())[:5])},
            ],
            "artifacts": [],
        }
    )


if __name__ == "__main__":
    main()

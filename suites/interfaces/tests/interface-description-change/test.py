"""interface-description-change (DNOS).

Flow (spec section 51 - device access via ExecutionContext, never direct SSH):
1. show interfaces description (baseline)
2. for every 'ge' interface, choose a random description and set it
3. commit
4. show interfaces description and verify each ge interface applied
5. rollback 1 + commit
6. show interfaces description and verify it returned to baseline
"""

import random

from drivetest import ExecutionContext


def parse_descriptions(text: str) -> dict[str, str]:
    """Parse `show interfaces description` into {interface_name: description}."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        low = line.lower()
        if low.startswith("interface") and "description" in low:
            continue  # header row
        parts = line.split(None, 3)
        if not parts:
            continue
        name = parts[0]
        description = parts[3].strip() if len(parts) > 3 else ""
        result[name] = description
    return result


def main() -> None:
    ctx = ExecutionContext.from_env()
    dut = ctx.device("dut")

    baseline_raw = dut.run("show interfaces description")
    baseline = parse_descriptions(baseline_raw)
    ge_interfaces = [name for name in baseline if name.startswith("ge")]

    if not ge_interfaces:
        ctx.write_result(
            {
                "execution_status": "COMPLETED",
                "test_id": ctx.test_id or "interface-description-change",
                "test_verdict": "FAILED",
                "measurements": {"ge_interfaces": 0},
                "observations": ["No 'ge' interfaces found to configure."],
                "evidence": [baseline_raw.strip()[:500]],
                "artifacts": [],
            }
        )
        return

    # 2) choose a random description per ge interface
    planned = {name: f"drivetest-{random.randint(1000, 9999)}" for name in ge_interfaces}

    # 3) configure + commit
    tree: list[str] = ["interfaces"]
    for name, description in planned.items():
        tree += [f"  {name}", f'    description "{description}"', "  !"]
    tree += ["!"]
    dut.configure(tree)
    dut.commit()

    # 4) verify applied
    after = parse_descriptions(dut.run("show interfaces description"))
    applied_mismatches = {
        name: {"expected": planned[name], "actual": after.get(name)}
        for name in planned
        if after.get(name) != planned[name]
    }

    # 5) rollback + commit
    dut.rollback(1)
    dut.commit()

    # 6) verify reverted to baseline
    reverted = parse_descriptions(dut.run("show interfaces description"))
    revert_mismatches = {
        name: {"expected": baseline.get(name, ""), "actual": reverted.get(name)}
        for name in planned
        if reverted.get(name) != baseline.get(name, "")
    }

    applied_ok = not applied_mismatches
    reverted_ok = not revert_mismatches
    verdict = "PASSED" if (applied_ok and reverted_ok) else "FAILED"

    observations = [
        f"Configured {len(planned)} ge interface(s) with unique descriptions.",
        "All descriptions applied as configured." if applied_ok else f"Apply mismatches: {applied_mismatches}",
        "State restored to baseline after rollback 1." if reverted_ok else f"Revert mismatches: {revert_mismatches}",
    ]

    ctx.write_result(
        {
            "execution_status": "COMPLETED",
            "test_id": ctx.test_id or "interface-description-change",
            "test_verdict": verdict,
            "measurements": {
                "ge_interfaces": len(planned),
                "applied_ok": applied_ok,
                "reverted_ok": reverted_ok,
            },
            "observations": observations,
            "evidence": [
                {"source": "planned", "details": planned},
                {"source": "after_commit", "details": {n: after.get(n) for n in planned}},
                {"source": "after_rollback", "details": {n: reverted.get(n) for n in planned}},
            ],
            "artifacts": [],
        }
    )


if __name__ == "__main__":
    main()

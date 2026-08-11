"""interfaces-admin-state-disabled (DNOS).

Flow (spec section 51 - device access via ExecutionContext, never direct SSH):
1. show interfaces description (baseline)
2. identify every present interface that is NOT administratively disabled
3. set 'admin-state disabled' on each of them, then commit
4. show interfaces description and verify each target is now admin 'disabled'
   AND operationally 'down'
5. rollback 1 + commit
6. poll `show interfaces description` once per second (up to 10 minutes) until every
   target returned to its baseline admin + operational state, since bringing an
   interface back up can take time; report how long it took
"""

import time

from drivetest import ExecutionContext

# Interfaces can take a while to transition back to 'up' after re-enabling.
# Poll once per second up to this many seconds before giving up.
REVERT_TIMEOUT_S = 600
REVERT_POLL_INTERVAL_S = 1.0


def parse_interfaces(text: str) -> dict[str, dict[str, str]]:
    """Parse `show interfaces description` into {name: {admin, oper, description}}.

    Handles the real DNOS pipe-delimited table AND the plain whitespace table.
    Columns are: Interface | Admin | Operational | Description.
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
            admin = cells[1] if len(cells) > 1 else ""
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
            admin = parts[1] if len(parts) > 1 else ""
            oper = parts[2] if len(parts) > 2 else ""
            description = parts[3].strip() if len(parts) > 3 else ""

        result[name] = {"admin": admin, "oper": oper, "description": description}
    return result


def main() -> None:
    ctx = ExecutionContext.from_env()
    dut = ctx.device("dut")

    baseline = parse_interfaces(dut.run("show interfaces description"))

    # Every present interface that is NOT administratively disabled.
    # Skip breakout parents marked 'not-present' (configuring them errors on
    # commit) and skip management interfaces so we never sever the Run-owned
    # session that the test itself depends on.
    targets = [
        name
        for name, info in baseline.items()
        if info["admin"].lower() != "disabled"
        and info["oper"].lower() != "not-present"
        and not name.lower().startswith("mgmt")
    ]

    if not targets:
        ctx.write_result(
            {
                "execution_status": "COMPLETED",
                "test_id": ctx.test_id or "interfaces-admin-state-disabled",
                "test_verdict": "FAILED",
                "measurements": {"target_interfaces": 0},
                "observations": ["No non-disabled interfaces found to disable."],
                "evidence": [],
                "artifacts": [],
            }
        )
        return

    tree: list[str] = ["interfaces"]
    for name in targets:
        tree += [f"  {name}", "    admin-state disabled", "  !"]
    tree += ["!"]
    dut.configure(tree)
    dut.commit()

    after = parse_interfaces(dut.run("show interfaces description"))
    # Each target must be admin 'disabled' AND operationally 'down'.
    disable_mismatches = {
        name: {
            "expected": {"admin": "disabled", "oper": "down"},
            "actual": {
                "admin": after.get(name, {}).get("admin"),
                "oper": after.get(name, {}).get("oper"),
            },
        }
        for name in targets
        if after.get(name, {}).get("admin", "").lower() != "disabled"
        or after.get(name, {}).get("oper", "").lower() != "down"
    }

    dut.rollback(1)
    dut.commit()

    def compute_revert_mismatches(reverted: dict[str, dict[str, str]]) -> dict:
        return {
            name: {
                "expected": {
                    "admin": baseline[name]["admin"],
                    "oper": baseline[name]["oper"],
                },
                "actual": {
                    "admin": reverted.get(name, {}).get("admin"),
                    "oper": reverted.get(name, {}).get("oper"),
                },
            }
            for name in targets
            if reverted.get(name, {}).get("admin", "").lower()
            != baseline[name]["admin"].lower()
            or reverted.get(name, {}).get("oper", "").lower()
            != baseline[name]["oper"].lower()
        }

    # Bringing an interface back up after re-enabling is not instantaneous, so
    # poll once per second until every target matches its baseline again or the
    # timeout expires.
    revert_start = time.monotonic()
    while True:
        reverted = parse_interfaces(dut.run("show interfaces description"))
        revert_mismatches = compute_revert_mismatches(reverted)
        revert_wait_s = time.monotonic() - revert_start
        if not revert_mismatches or revert_wait_s >= REVERT_TIMEOUT_S:
            break
        time.sleep(REVERT_POLL_INTERVAL_S)

    disabled_ok = not disable_mismatches
    reverted_ok = not revert_mismatches
    verdict = "PASSED" if (disabled_ok and reverted_ok) else "FAILED"

    ctx.write_result(
        {
            "execution_status": "COMPLETED",
            "test_id": ctx.test_id or "interfaces-admin-state-disabled",
            "test_verdict": verdict,
            "measurements": {
                "target_interfaces": len(targets),
                "disabled_ok": disabled_ok,
                "reverted_ok": reverted_ok,
                "disable_mismatch_count": len(disable_mismatches),
                "revert_mismatch_count": len(revert_mismatches),
                "revert_wait_seconds": round(revert_wait_s, 1),
                "revert_timeout_seconds": REVERT_TIMEOUT_S,
            },
            "observations": [
                f"Disabled {len(targets)} previously non-disabled interface(s).",
                "All targets transitioned to admin disabled and operationally down."
                if disabled_ok
                else f"Disable mismatches: {dict(list(disable_mismatches.items())[:5])}",
                f"All targets restored to baseline admin/oper state {round(revert_wait_s, 1)}s after rollback 1 commit."
                if reverted_ok
                else f"Targets did NOT restore to baseline within {REVERT_TIMEOUT_S}s "
                f"(waited {round(revert_wait_s, 1)}s). Revert mismatches: {dict(list(revert_mismatches.items())[:5])}",
            ],
            "evidence": [
                {"source": "sample_targets", "details": targets[:5]},
                {
                    "source": "sample_baseline",
                    "details": {n: baseline[n] for n in targets[:5]},
                },
            ],
            "artifacts": [],
        }
    )


if __name__ == "__main__":
    main()

"""Template test. Talk to devices only via ExecutionContext (spec section 51)."""

from drivetest import ExecutionContext


def main() -> None:
    ctx = ExecutionContext.from_env()
    dut = ctx.device("dut")  # role comes from a prerequisite field's device_role

    output = dut.run("show interfaces description")
    passed = bool(output.strip())

    ctx.write_result(
        {
            "execution_status": "COMPLETED",
            "test_id": ctx.test_id or "my_test",
            "test_verdict": "PASSED" if passed else "FAILED",
            "measurements": {},
            "observations": ["Describe what was checked."],
            "evidence": [output.strip().splitlines()[-1] if output.strip() else "no output"],
            "artifacts": [],
        }
    )


if __name__ == "__main__":
    main()

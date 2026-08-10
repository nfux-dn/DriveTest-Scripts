---
name: authoring-suite-tests
description: Author DriveTest test packages that run under a suite - suite.yaml, prerequisites (including device_role bindings), tests/<id>/test.py using the ExecutionContext SDK, and test.yaml. Use when writing or adding a DriveTest test, creating a suite, wiring prerequisites, or when the user mentions DriveTest tests, test packages, suites, or the interfaces/DNOS tests in this repo.
disable-model-invocation: true
---

# Authoring DriveTest test packages

Write the components a test needs to run under a suite on the DriveTest platform.
The platform clones this repo at a chosen commit, opens Run-owned device sessions,
then runs each test as an isolated subprocess. Tests talk to devices ONLY through
the `drivetest` ExecutionContext SDK (never open their own SSH) and write a
`result.json`. See the repo `README.md` for the full contract; this skill is the
quick authoring guide.

## Required components

For a suite `S` and test `T`, create:

```
suites/S/suite.yaml                         # id, name, description, ordered tests list
suites/S/README.md                          # suite purpose + connectivity scheme
suites/S/tests/T/test.py                    # the test (required)
suites/S/tests/T/test.yaml                  # AI review metadata (recommended)
prerequisites/S/common.yaml                 # device inputs the user fills at run time
```

Copy the skeletons in `templates/` and adapt. Keep `T` in `suite.yaml`'s `tests:`
list identical to the folder name. There is no environment object and no
platform/system layering: the user runs a suite and simply enters device
addresses in the Environment tab.

The Environment tab shows two things: your suite `README.md` (a `## Suite details`
section and a `## Connectivity` section) and the dynamic prerequisite form.

## Device sessions come from prerequisites

SSH sessions are owned by the Run and reused by every test (spec section 51). You
do NOT open connections in a test. You declare devices in the prerequisites: mark
a field with `device_role`, and the platform opens one session to the host the
user enters, addressable by that role.

```yaml
- id: dut_management_ip
  label: DUT Management IP
  type: ip
  required: true
  device_role: dut          # opens a session to this host as role "dut"
```

More `device_role` fields = more sessions. The operator picks the hostnames at run
time. Credentials, if needed, come from a `secret_reference` field named via
`credential_ref` (or a platform default).

## The device API (ExecutionContext)

```python
from drivetest import ExecutionContext

ctx = ExecutionContext.from_env()
dut = ctx.device("dut")               # role declared via device_role

out = dut.run("show interfaces description")   # operational show
dut.configure(["interfaces", "  ge0", '    description "x"', "  !", "!"])  # stage candidate
dut.commit()                          # apply
dut.rollback(1)                       # load previous committed config
dut.commit()                          # apply the rollback

ctx.values        # prerequisite values the user supplied (no raw secrets)
ctx.test_id       # current test id
ctx.write_result({...})   # writes result.json (see result contract)
```

For DNOS CLI shapes (config trees, `!` markers, commit, rollback, show), see
[dnos-patterns.md](dnos-patterns.md).

## Verdict model (what to put in result.json)

- Set `test_verdict` to `"PASSED"`/`"FAILED"` when the test can decide, or `null`
  to let AI judge. A deterministic `FAILED` is never overridden to PASS.
- Populate `measurements`, `observations`, `evidence` so the AI reviewer has real
  data. Sparse results tend to become `REVIEW_REQUIRED`.
- Raise/exit non-zero for real bugs (recorded as `SCRIPT_ERROR`). Use
  `execution_status: "INFRA_ERROR"` for device/reachability problems.

## Verify-change-then-rollback pattern

For config tests, prove both the change AND the revert:

```
Task Progress:
- [ ] Capture baseline: show <state> (parse it)
- [ ] Compute intended change (e.g. per interface)
- [ ] configure(...) the candidate; commit()
- [ ] Re-show; verify each item matches what you set
- [ ] rollback(1); commit()
- [ ] Re-show; verify state returned to the baseline
- [ ] write_result with measurements/evidence and a verdict
```

## Authoring workflow

1. Pick suite id `S` and test id `T`.
2. `suites/S/suite.yaml`: set `id`, `name`, `description`, and add `T` to `tests:`.
3. `suites/S/README.md`: write `## Suite details` and `## Connectivity` sections.
4. `prerequisites/S/common.yaml`: add inputs; mark device hosts with `device_role`.
5. `suites/S/tests/T/test.py`: use ExecutionContext; write result.json.
6. `suites/S/tests/T/test.yaml`: name/description/expected_behavior/evaluation_instructions.
7. Validate locally where possible (see repo README "Test it locally"), then run
   it via the platform.

## Checklist

- [ ] `T` folder has `test.py`; `T` is listed in `suites/S/suite.yaml`.
- [ ] `suites/S/README.md` has `## Suite details` and `## Connectivity`.
- [ ] Device access uses `ctx.device(role)` (role declared via `device_role`) - no direct SSH.
- [ ] `test.py` writes valid `result.json` with a deliberate `test_verdict`.
- [ ] `measurements`/`observations`/`evidence` populated for the AI reviewer.
- [ ] `test.yaml` gives the AI clear expected behavior + evaluation instructions.
- [ ] No secrets committed.

## Worked example

The `interfaces` suite's `interface-description-change` test is a complete example
of the verify-change-then-rollback pattern against DNOS. Read
`suites/interfaces/tests/interface-description-change/test.py`.

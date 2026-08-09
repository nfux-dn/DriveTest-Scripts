# DriveTest Scripts

This repository holds the **test packages** that the
[DriveTest platform](https://github.com/nfux-dn/DriveTest-App) pulls and executes.

You put your network validation tests here, organized into **Suites**. The platform lets a
user pick a Suite, pick a compatible Environment, fill in prerequisites, choose an exact Git
revision **of this repo**, and then runs each test in the Suite one at a time. Every test
produces a structured result; the platform adds an AI review and computes a final verdict.

You do not run these scripts by hand in production — the platform runs them for you in an
isolated workspace. This README explains the contract so the scripts you write here work
correctly when the platform executes them.

## Contents

- [How the platform runs your scripts](#how-the-platform-runs-your-scripts)
- [Repository structure](#repository-structure)
- [A Suite: `suite.yaml`](#a-suite-suiteyaml)
- [A Test: `test.py` + `test.yaml`](#a-test-testpy--testyaml)
- [The execution contract](#the-execution-contract)
- [The result contract (`result.json`)](#the-result-contract-resultjson)
- [Verdict model: who decides pass/fail](#verdict-model-who-decides-passfail)
- [Execution status and errors](#execution-status-and-errors)
- [Prerequisites](#prerequisites)
- [Write your first test (step by step)](#write-your-first-test-step-by-step)
- [Test it locally](#test-it-locally)
- [Rules and best practices](#rules-and-best-practices)
- [Checklist for adding a test](#checklist-for-adding-a-test)

## How the platform runs your scripts

1. The user selects a Suite and a compatible Environment and fills the prerequisite form.
2. The user selects a branch/commit **of this repository**.
3. The platform clones this repo at that exact commit into a temporary, isolated workspace.
4. For each test id listed in the Suite, in order, the platform:
   - launches `python3 test.py` **as a separate process** (never inside the platform),
   - passes context (environment + prerequisite values) via a JSON file,
   - waits with a timeout, captures stdout/stderr,
   - reads the `result.json` your test wrote,
   - classifies the execution (completed vs. error), then runs an AI review,
   - stores everything and computes the final verdict.

Tests run sequentially and are evaluated independently.

## Repository structure

The platform expects this layout. The important path is
`suites/<suite_id>/tests/<test_id>/test.py`.

```
DriveTest-Scripts/
├── suites/
│   └── <suite_id>/
│       ├── suite.yaml                 # suite definition (requirements + ordered test list)
│       ├── README.md                  # optional: what the suite validates
│       └── tests/
│           └── <test_id>/
│               ├── test.py            # REQUIRED: the executable test
│               ├── test.yaml          # optional: definition + AI evaluation instructions
│               └── README.md          # optional: notes for humans
│
├── prerequisites/
│   └── <suite_id>/
│       ├── common.yaml                # base prerequisite form
│       ├── <platform>/default.yaml    # optional platform overrides
│       └── <platform>/<system>.yaml   # optional platform+system overrides
│
├── framework/                         # optional shared helpers you vendor in (see notes)
└── schemas/                           # optional JSON schemas / reference docs
```

- `suite_id`, `test_id`, and `platform`/`system` are lowercase identifiers (letters, digits,
  underscores). The `test_id` in `suite.yaml` must match the folder name under `tests/`.

## A Suite: `suite.yaml`

A Suite is a collection of related tests plus the requirements an Environment must meet to
run it. Example `suites/pwhe_shaping/suite.yaml`:

```yaml
id: pwhe_shaping
name: PWHE Shaping
description: Validate PWHE shaping behavior.

# Requirements decide whether an Environment is even allowed to run this Suite.
requirements:
  min_devices: 2
  traffic_generator: true
  capabilities:
    - qos
    - shaping
    - pwhe

supported_platforms:
  - platform_a
  - platform_b

# Ordered list of test ids. Each must be a folder under tests/.
tests:
  - max_bandwidth
  - high_priority_queue
  - congestion_behavior
```

## A Test: `test.py` + `test.yaml`

`test.py` is the only required file in a test folder. It runs, gathers evidence, optionally
decides a verdict, and writes `result.json`.

`test.yaml` is optional but recommended — it gives the AI reviewer context. Only these keys
are used:

```yaml
id: max_bandwidth
name: Max bandwidth shaping
description: Validate that measured bandwidth stays within the configured shaping range.
expected_behavior: Measured rate should be at or below the configured rate within a small tolerance.
evaluation_instructions: Treat measured rate exceeding configured by more than 5% as a failure.
```

## The execution contract

When the platform runs `test.py`:

- **Working directory** is the test's own folder (`suites/<suite_id>/tests/<test_id>/`).
- **Runtime** is Python 3.12. The environment is minimal — assume only the Python **standard
  library** is available (see [best practices](#rules-and-best-practices) about dependencies).
- The following **environment variables** are provided (and little else):

  | Variable                 | Meaning                                                        |
  | ------------------------ | -------------------------------------------------------------- |
  | `DRIVETEST_RESULT_PATH`  | Absolute path where your test MUST write `result.json`.        |
  | `DRIVETEST_CONTEXT_PATH` | Absolute path to a JSON file with the run context (read-only). |
  | `DRIVETEST_TEST_ID`      | The test id the platform is running.                           |

- The **context file** (`DRIVETEST_CONTEXT_PATH`) contains:

  ```json
  {
    "run_id": "…",
    "suite_id": "pwhe_shaping",
    "environment": {
      "id": "lab_23",
      "platform": "platform_a",
      "system_type": "pwhe",
      "software_version": "25.2"
    },
    "test_id": "max_bandwidth",
    "values": {
      "dut_management_ip": "10.10.1.20",
      "customer_port": "ge800-31/0/17",
      "traffic_generator": "ixia"
    }
  }
  ```

  `values` are the prerequisite inputs the user filled in for this run. Use them to know how
  to reach the device under test, which ports/generators to use, etc.

- There is a **timeout** (default 300s). Exceeding it is recorded as `TIMEOUT`.
- stdout/stderr are captured (bounded in size) and stored as artifacts.

## The result contract (`result.json`)

Your test must write a JSON object to `DRIVETEST_RESULT_PATH`. Fields:

| Field              | Type                                   | Required | Notes                                                        |
| ------------------ | -------------------------------------- | -------- | ------------------------------------------------------------ |
| `test_id`          | string                                 | yes      | Should match `DRIVETEST_TEST_ID`.                            |
| `execution_status` | string                                 | no       | Defaults to `COMPLETED`. See [errors](#execution-status-and-errors). |
| `test_verdict`     | `"PASSED"` \| `"FAILED"` \| `null`     | no       | `null` means "let AI decide" (see verdict model).            |
| `measurements`     | object                                 | no       | Numeric/structured data the AI and report can use.           |
| `observations`     | string[]                               | no       | Human-readable notes.                                        |
| `evidence`         | array                                  | no       | What supports your conclusion (log lines, values).           |
| `artifacts`        | string[]                               | no       | Filenames you produced in the working directory.             |

Example (a test that decides its own verdict):

```json
{
  "execution_status": "COMPLETED",
  "test_id": "max_bandwidth",
  "test_verdict": "PASSED",
  "measurements": {
    "configured_bandwidth_mbps": 1000,
    "measured_bandwidth_mbps": 998
  },
  "observations": ["Queue stayed within configured shaping range."],
  "evidence": ["show qos queue statistics output"],
  "artifacts": ["qos_stats.txt"]
}
```

Example (a test that punts the verdict to AI — set `test_verdict` to `null`):

```json
{
  "execution_status": "COMPLETED",
  "test_id": "complex_log_analysis",
  "test_verdict": null,
  "evidence": ["routing_engine.log excerpt"],
  "artifacts": ["routing_engine.log"]
}
```

If `result.json` is missing or does not match this schema, the platform records a
`SCRIPT_ERROR` (see below).

## Verdict model: who decides pass/fail

Every test runs in one of two modes:

- **Mode A — the test decides.** Set `test_verdict` to `"PASSED"` or `"FAILED"`. The AI still
  reviews and gives its own opinion.
- **Mode B — AI decides.** Set `test_verdict` to `null`. Provide good `evidence`/`artifacts`;
  the AI reads them and decides.

The platform computes the **final verdict** (you do not). The rule (enforced server-side):

| test_verdict | AI verdict     | final verdict     |
| ------------ | -------------- | ----------------- |
| PASSED       | PASSED         | PASSED            |
| FAILED       | PASSED         | FAILED            |
| PASSED       | FAILED         | FAILED            |
| FAILED       | FAILED         | FAILED            |
| null         | PASSED         | PASSED            |
| null         | FAILED         | FAILED            |
| PASSED       | INCONCLUSIVE   | REVIEW_REQUIRED   |
| FAILED       | INCONCLUSIVE   | FAILED            |
| null         | INCONCLUSIVE   | REVIEW_REQUIRED   |

Key point: a deterministic `FAILED` can never be turned into `PASSED` by the AI. So if your
test is sure something failed, set `test_verdict: "FAILED"` and it stays failed.

## Execution status and errors

The platform separates *did the test run* from *did the product pass*:

- **Just raise / exit non-zero for bugs.** If your `test.py` throws an unhandled exception or
  exits with a non-zero code, the platform records `SCRIPT_ERROR` (an application/script bug),
  which is NOT a product failure. You do not need to catch-and-format script errors.
- **Signal infrastructure problems** (device unreachable, SSH/auth failure, traffic generator
  down) by exiting `0` and writing `result.json` with `"execution_status": "INFRA_ERROR"`.
- **Timeouts** are detected automatically as `TIMEOUT`.
- Valid non-`COMPLETED` statuses you may set: `INFRA_ERROR`, `SKIPPED`. Do not set `COMPLETED`
  if the test did not actually finish its work.

When execution is not `COMPLETED`, there is no product verdict and the result can never be
`PASSED`.

## Prerequisites

Prerequisites are the runtime inputs a user must supply before a Suite can run (IPs, ports,
traffic generator, confirmations, and automatic checks). They are **declarative YAML** under
`prerequisites/<suite_id>/`. The platform merges, in order (later overrides earlier):

```
prerequisites/<suite_id>/common.yaml
prerequisites/<suite_id>/<platform>/default.yaml
prerequisites/<suite_id>/<platform>/<system_type>.yaml
```

Example `prerequisites/pwhe_shaping/common.yaml`:

```yaml
id: pwhe_shaping_common
version: 1

sections:
  - id: connectivity
    title: Connectivity
    fields:
      - id: dut_management_ip
        label: DUT Management IP
        type: ip
        required: true

      - id: customer_port
        label: Customer Port
        type: interface
        required: true
        placeholder: ge800-31/0/17

  - id: traffic
    title: Traffic Generator
    fields:
      - id: traffic_generator
        label: Traffic Generator
        type: select
        required: true
        options: [ixia, spirent]

      - id: ixia_chassis_ip
        label: Ixia Chassis IP
        type: ip
        required: true
        # Conditional field: only shown/required when the answer above is "ixia".
        visible_when:
          field: traffic_generator
          equals: ixia

  - id: physical
    title: Physical Validation
    fields:
      - id: topology_verified
        label: Physical topology verified
        type: confirmation
        required: true

  - id: checks
    title: Automatic Checks
    fields:
      - id: ssh_connectivity
        label: Verify SSH connectivity to DUT
        type: check
        required: true
        remediation: Ensure the DUT management IP is reachable and SSH is enabled.
        check:
          handler: ssh_connectivity
          target: ${dut_management_ip}   # ${field_id} is substituted from the user's answers
```

**Supported field types:** `text`, `textarea`, `number`, `integer`, `boolean`,
`confirmation`, `select`, `multiselect`, `ip`, `interface`, `secret_reference`, `check`.

**Automatic check handlers** (referenced by `check.handler`) are implemented on the platform,
not here — YAML can never run arbitrary commands. Available handlers:
`ssh_connectivity`, `tcp_port`, `traffic_generator_reachable`. Use `target: ${some_field}` to
point a check at a value the user entered.

The values the user fills in are delivered to your `test.py` in the context file under
`values` (see the execution contract).

## Write your first test (step by step)

1. Create the folders:

   ```
   suites/demo/suite.yaml
   suites/demo/tests/ping_check/test.py
   suites/demo/tests/ping_check/test.yaml
   prerequisites/demo/common.yaml
   ```

2. `suites/demo/suite.yaml`:

   ```yaml
   id: demo
   name: Demo Suite
   description: Minimal example suite.
   requirements:
     min_devices: 1
     traffic_generator: false
     capabilities: []
   supported_platforms: [platform_a]
   tests:
     - ping_check
   ```

3. `suites/demo/tests/ping_check/test.py`:

   ```python
   import json
   import os
   import subprocess

   # 1) Read context (environment + prerequisite values).
   with open(os.environ["DRIVETEST_CONTEXT_PATH"], encoding="utf-8") as fh:
       context = json.load(fh)
   values = context.get("values", {})
   target_ip = values.get("dut_management_ip", "127.0.0.1")

   # 2) Do the work. Uncaught exceptions -> SCRIPT_ERROR (that's fine for bugs).
   proc = subprocess.run(
       ["ping", "-c", "3", "-W", "2", target_ip],
       capture_output=True, text=True, timeout=30,
   )
   reachable = proc.returncode == 0
   print(proc.stdout)  # captured as an artifact

   # 3) Decide a verdict (Mode A) and write result.json.
   result = {
       "execution_status": "COMPLETED",
       "test_id": os.environ["DRIVETEST_TEST_ID"],
       "test_verdict": "PASSED" if reachable else "FAILED",
       "measurements": {"reachable": reachable},
       "observations": [f"Pinged {target_ip}."],
       "evidence": [proc.stdout.strip().splitlines()[-1] if proc.stdout else "no output"],
       "artifacts": [],
   }
   with open(os.environ["DRIVETEST_RESULT_PATH"], "w", encoding="utf-8") as fh:
       json.dump(result, fh)
   ```

4. `suites/demo/tests/ping_check/test.yaml`:

   ```yaml
   id: ping_check
   name: Ping reachability
   description: Confirm the DUT management IP responds to ICMP.
   expected_behavior: The DUT should reply to pings.
   evaluation_instructions: Treat any packet loss as a warning; total unreachability as failure.
   ```

5. `prerequisites/demo/common.yaml`:

   ```yaml
   id: demo_common
   version: 1
   sections:
     - id: connectivity
       title: Connectivity
       fields:
         - id: dut_management_ip
           label: DUT Management IP
           type: ip
           required: true
   ```

Commit and push. In the DriveTest app, select this repo's branch/commit for a run of the
Demo Suite.

## Test it locally

You can run a test exactly the way the platform does, without the platform:

```bash
cd suites/demo/tests/ping_check

# Provide the context the platform would normally build:
cat > /tmp/context.json <<'JSON'
{ "run_id": "local", "suite_id": "demo", "test_id": "ping_check",
  "environment": {"id": "lab_23", "platform": "platform_a", "system_type": "pwhe", "software_version": "25.2"},
  "values": { "dut_management_ip": "127.0.0.1" } }
JSON

DRIVETEST_CONTEXT_PATH=/tmp/context.json \
DRIVETEST_RESULT_PATH=/tmp/result.json \
DRIVETEST_TEST_ID=ping_check \
python3 test.py

cat /tmp/result.json   # inspect what the platform would ingest
```

If `python3 test.py` exits non-zero or `/tmp/result.json` is missing/invalid, the platform
would classify that run as `SCRIPT_ERROR`.

## Rules and best practices

- **Self-contained.** Each test folder should stand on its own. Read only from the context;
  write only `result.json` (and any artifact files) into the working directory.
- **Standard library only (MVP).** The platform does not install per-test dependencies. If you
  need shared helpers, vendor plain-Python modules under `framework/` and import them with a
  path relative to the repo, or copy them into the test folder. Do not rely on the platform's
  own packages.
- **No secrets in this repo.** Never commit passwords, tokens, or private keys. Sensitive
  runtime values come through prerequisite fields (`secret_reference` / `sensitive: true`) and
  are handled by the platform — do not print them or write them into `result.json`.
- **Deterministic verdicts when you can.** If the test can objectively decide, set
  `test_verdict`. Reserve `null` (AI-judged) for genuinely subjective/log-analysis cases.
- **Give the AI good evidence.** Populate `measurements`, `observations`, and `evidence`. The
  AI must use only what you supply; sparse results lead to `INCONCLUSIVE` → `REVIEW_REQUIRED`.
- **Keep output bounded.** stdout/stderr and artifacts are size-limited. Print what matters.
- **Separate bugs from product failures.** Let real bugs raise (→ `SCRIPT_ERROR`). Use
  `test_verdict: "FAILED"` only for genuine product failures, and `INFRA_ERROR` for
  environment/connectivity problems.
- **Idempotent and clean.** Don't leave the device in a broken state; clean up what you change.

## Checklist for adding a test

- [ ] Folder `suites/<suite_id>/tests/<test_id>/` with `test.py`.
- [ ] `<test_id>` added to the `tests:` list in `suites/<suite_id>/suite.yaml`.
- [ ] `test.py` reads `DRIVETEST_CONTEXT_PATH` and writes valid JSON to `DRIVETEST_RESULT_PATH`.
- [ ] `test_verdict` is `"PASSED"`, `"FAILED"`, or `null` (deliberately chosen).
- [ ] `measurements`/`observations`/`evidence` populated for the AI reviewer.
- [ ] `test.yaml` describes the test and gives evaluation instructions (recommended).
- [ ] New prerequisite inputs (if any) added under `prerequisites/<suite_id>/`.
- [ ] Ran it locally with the env vars above and inspected `result.json`.
- [ ] No secrets committed.

# DNOS CLI patterns

Reference for writing DNOS commands inside a DriveTest test. Send these lines
through the ExecutionContext (`ctx.device(role).run/configure/commit/rollback`);
never open your own SSH. (This is general DNOS knowledge, independent of any
other tooling.)

## Modes and prompts

- Operational: prompt ends `#`. Use for `show ...`.
- Config: prompt ends `(cfg)#` or `(cfg-...)#`. Entered with `configure`.

## Reading state

```
show interfaces description
```
Returns a table of interfaces with admin/oper status and description. Parse
tolerantly (split columns; last column is the description, which may be empty).

## Configuring (candidate) with a config tree

DNOS is YANG-style. Walk into containers; close each block that has children with
`!`. Plural container plus inline key on one line is NOT valid - put the key on
its own line.

```
interfaces
  ge100-0/0/0
    description "uplink to spine"
  !
!
```

With the SDK:

```python
dut.configure([
    "interfaces",
    "  ge100-0/0/0",
    '    description "uplink to spine"',
    "  !",
    "!",
])
```

`configure(...)` enters config mode and stages the candidate; it does NOT commit.

## Committing

```python
dut.commit()      # sends: commit
```

## Rolling back

Each successful commit creates a transaction with a rollback id (0 = current, 1 =
previous, ...). To revert to the previous committed config and apply it:

```python
dut.rollback(1)   # sends: rollback 1
dut.commit()
```

## Removing a leaf

Prefix the leaf with `no` inside the config tree (e.g. `no description ...`), then
`commit`.

## Gotchas

- Close every container/list-key block with `!` or the next line lands in the
  wrong context and DNOS returns `ERROR:`.
- Do not append `| no-more` to config-mode lines.
- Treat an `ERROR:`/unreachable response as a stop; surface it (for reachability
  problems, write `execution_status: "INFRA_ERROR"`).

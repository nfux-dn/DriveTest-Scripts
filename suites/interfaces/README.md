# Interfaces

## Suite details

Validates interface configuration on a DNOS device. The `interface-description-change`
test sets a unique description on every `ge` interface, commits, verifies each was applied,
then rolls back one transaction, commits, and verifies the device returned to its baseline.

The `interfaces-admin-state-disabled` test discovers every present interface that is not
already administratively disabled, sets `admin-state disabled` on each, commits, and verifies
each transitioned to admin `disabled` and operationally `down`. It then rolls back one
transaction, commits, and verifies every interface returned to its baseline admin/oper state.
Management (`mgmt`) and `not-present` interfaces are excluded so the Run-owned session is never
severed.

You provide the device in the Environment tab: enter the **DUT Management IP**. That is the
only device this suite needs (opened as role `dut`).

## Connectivity

```text
        +-------------------+
        |   DUT (role: dut) |
        |   DNOS device     |
        +---------+---------+
                  |
             management
             network
                  |
             +----+----+
             | DriveTest|
             +---------+
```

- Connect the DUT management port to the management network reachable by DriveTest.
- No traffic generator or second device is required for this suite.
- Ensure SSH is enabled on the DUT management IP you provide.

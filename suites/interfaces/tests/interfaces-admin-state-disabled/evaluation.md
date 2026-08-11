# Interface admin-state disable and rollback

Expected behavior: the test discovers every present interface that is not already
administratively disabled, sets `admin-state disabled` on each, and commits. After
that commit, every targeted interface must report Admin `disabled` **and**
Operational `down`. After `rollback 1` + commit, every targeted interface must
return to the exact Admin and Operational state it had in the baseline capture.
Because an interface can take time to come back up after being re-enabled, the
test polls `show interfaces description` once per second for up to 10 minutes and
reports how long the revert took (`revert_wait_seconds`).

Evaluation instructions: pass only if every targeted interface transitioned to
admin `disabled` and operationally `down` after the commit AND every targeted
interface reverted to its baseline admin/oper state within the 10-minute revert
window. Any interface that failed to disable, failed to go operationally down, or
failed to revert to baseline before the timeout is a failure. The time taken to
revert (`revert_wait_seconds`) is informational and does not by itself fail the
test as long as it is within the window. Management (`mgmt`) and `not-present`
interfaces are intentionally excluded and must not be considered.

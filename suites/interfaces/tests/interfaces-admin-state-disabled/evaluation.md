# Interface admin-state disable and rollback

Expected behavior: the test discovers every present interface that is not already
administratively disabled, sets `admin-state disabled` on each, and commits. After
that commit, every targeted interface must report Admin `disabled` **and**
Operational `down`. After `rollback 1` + commit, every targeted interface must
return to the exact Admin and Operational state it had in the baseline capture.

Evaluation instructions: pass only if every targeted interface transitioned to
admin `disabled` and operationally `down` after the commit AND every targeted
interface reverted to its baseline admin/oper state after the rollback. Any
interface that failed to disable, failed to go operationally down, or failed to
revert is a failure. Management (`mgmt`) and `not-present` interfaces are
intentionally excluded and must not be considered.

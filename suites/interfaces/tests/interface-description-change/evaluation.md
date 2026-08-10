# Interface description change and rollback

Expected behavior: after commit, each `ge` interface shows exactly its configured
description; after `rollback 1` + commit, every `ge` interface returns to its
baseline description.

Evaluation instructions: pass only if every `ge` interface matched its configured
description after commit AND all reverted to the baseline after rollback. Any
mismatch is a failure.

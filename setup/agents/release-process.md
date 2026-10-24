# Review, gate and release

How a change gets from a branch to users, with the least waiting and the fewest paid runs. Every agent follows it; `~/AGENTS.md` points here.

Branches: reviewed PRs land on `{{setup.repos.integration_branch}}`. Users get `{{setup.repos.release_branch}}`. When the two are the same branch there is no release PR: the last step below is skipped.

## Review once

- A normal PR gets one review when it enters `{{setup.repos.integration_branch}}`, and no other reviewer.
- A big or easy-to-break change (a security boundary, a migration, code that writes into a user's files) also goes through {{setup.review.risky_uses}}. So does a release PR.
- A paid review bot ({{setup.review.paid_bot|none set}}) reviews only the final release head, never each push.

## Gate in batches

- Before a push a PR branch gets only quick checks: {{setup.gates.quick|typecheck and the tests it touches}}. Never a full gate per PR.
- The full gate ({{setup.gates.full|the repo's full test run}}) runs once on a merge train: every reviewed PR merged into one branch with real merges, gated together, then landed.
- On red: fix the PR the failing tests point to, rerun only the failed part, then the full gate once more.
- Test runners use {{setup.machine.test_workers}} workers.

## Release

- A nightly full run ({{setup.gates.nightly|every test, with repeats to find random failures}}) is reused. It counts while it is younger than {{setup.gates.nightly_max_age_hours}} hours.
- A release head runs only what changed since that nightly run, once. No repeats on the head.
- The release PR goes from `{{setup.repos.integration_branch}}` to `{{setup.repos.release_branch}}`. The captain reviews it on {{setup.captain.review_surface}} and merges it.

## While a release check runs

- Coding goes on.
- No test runs, no builds and no pushes, so the check has the machine and the head stays still.
- Commit locally and leave a short resume note. Push when the check has ended.

## When a page beats text

A plan, a comparison or a diff that is easier to see than to read goes on a reviewable page (a Lavish page, say), not into a long message.

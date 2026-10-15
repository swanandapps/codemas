# Lambda guardrails (single function) — 2026-10-04

Amends `2026-10-03-job-pipeline-design.md`. Decision by the owner after the go-live smoke test.

**Live 2026-10-05.** Python and JS grade through SQS and this Lambda; no `JOB_SIGNING_SECRET` was readable in the smoke test (secret rotated at cutover). R1 (egress open) and R2 (role credentials readable) are present, as accepted below.

## Why

The first production smoke test (2026-10-04) showed that inside the `codemas-exec` Lambda, student code
can (a) read `JOB_SIGNING_SECRET` and the role's AWS credentials from `/proc/2/environ`, and (b) open
internet connections (Lambda refuses the seccomp filter; self-check `egress_blocked=false`). The
expected outputs were also inside the Lambda (claim payload). Python/JS were rolled back to Celery.

The owner chose to keep **one Lambda** (SQS-triggered, as built) and add guardrails, rather than split
grader and runner into two functions.

## Guardrails

1. **No expected outputs leave Django.** The claim response carries `tests: [{id, input}]` only.
   Django's `apply_result` already does the comparison. The handler's "never trim a correct output"
   exception goes away (it needed the expected output); when a `/complete/` body is over the cap, every
   output and error is trimmed alike. A correct output can then only be lost if the whole body exceeds
   ~2 MB (≈30+ tests near the 64 KB cap) — documented limit.
2. **No shared secret in the Lambda.** The Lambda no longer has `JOB_SIGNING_SECRET` and no longer signs
   requests.
   - The relay (Railway, trusted) puts a per-job token in each SQS message:
     `token = HMAC-SHA256(JOB_SIGNING_SECRET, "job:" + job_id)` (hex). Same for the local transport.
   - `POST /internal/jobs/claim/` takes `{job_id, token}`; Django recomputes and compares with
     `hmac.compare_digest`. Wrong/missing token → 401. The existing 409/410/404/400 semantics stay.
   - `/complete/` and `/fail/` take `{job_id, token, lease_token, …}`; both must match (the lease token is
     the fresh random value claim returned, so it still fences stale writers).
   - The `X-Timestamp`/`X-Signature` request signing is removed from the handler and the views.
     `jobs.signing` keeps `secret_problem()` and gains `job_token(job_id)` / `token_ok(job_id, token)`.
   - Django and the relay keep `JOB_SIGNING_SECRET` (the E001 startup guard stays). The CloudFormation
     template, `deploy.sh` and the README drop the Lambda's secret parameter and the rotate logic.
   - A token leaked to student code only works for that one job. A student can't pass their own
     submission without correct output, but a job claimed through R2 below can be forged.
3. **Unchanged:** rlimits, per-test timeout, output cap, empty child env, killpg, the warm-container
   scrub, prctl (harmless), the seccomp attempt (fail-soft) and its self-check log, MaximumConcurrency 5,
   3 attempts per question, the submission throttle.

## Accepted residual risks (documented, not fixed)

- **R1 — Egress.** Student code can reach the internet from the Lambda. Abuse volume is bounded by CPU
  time per test, concurrency 5, attempts, throttle.
- **R2 — Role credentials.** Lambda always injects the role's credentials, and student code can read
  them. The trigger role can `sqs:ReceiveMessage`, `sqs:DeleteMessage` and
  `sqs:ChangeMessageVisibility` on `codemas-exec`. So a determined student with a working solution
  could take a classmate's queued message (job id and token), claim that job first, read the
  classmate's code and test inputs, and post outputs that forge a pass or a fail. The classmate's
  real delivery then gets 409 `done`, so nothing looks wrong. They can also delete or hide queued
  messages, delaying other students' grading until the 30-minute sweep. Exposure is highest under an
  exam-deadline backlog (concurrency 5), when every queued message waits longest.
  What still holds: the signing secret and the expected answers never enter the Lambda, and a
  student can't pass their own submission without correct output.

The real fix for both is the two-function split, the standard pattern for online judges: a runner
Lambda with a zero-permission role, in a VPC with no NAT or internet gateway and a security group with
no outbound rules, invoked by the grader, which reads its return value. Recorded as future work.

## Smoke test changes

- Leak probe: **fail** if `JOB_SIGNING_SECRET` is found anywhere; `AWS_*` names → **warning** (R2).
- Egress probe: `EGRESS_OPEN` / `EGRESS_FILTER_OFF` → **warning** (R1).
- Python and JavaScript correct answers must still pass.

## Docs

`Codemas-SYSTEM_DESIGN.md` (§5 security, honest limits, §19–20 interview scripts), the job-pipeline
spec's As-built section, `docs/demo-runbook.md`, `docs/dev-pipeline.md`, `deploy/aws/README.md`, and the
two pipeline HTML pages where they mention signing or the Lambda's secret.

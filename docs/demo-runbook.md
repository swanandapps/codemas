# Submission pipeline: demo runbook

How to answer "show me…" questions during a live demo, with the exact clicks, URLs, commands and SQL. Every step works locally (`JOB_TRANSPORT=local`).

> **The AWS pipeline is live (since 2026-10-05).** Production grades Python and JavaScript through outbox → relay (Railway) → SQS `codemas-exec` → Lambda `codemas-exec` (arm64, ap-southeast-1), with `PIPELINE_LANGUAGES=python,javascript` on Railway backend. The go-live smoke test graded Python and JS through it and found no `JOB_SIGNING_SECRET` in the Lambda; R1 and R2 are still present (see Honest limits). The AWS steps were rehearsed read-only on 2026-10-05: every `aws …` command, the three CloudWatch log filters (against real submission 1340), the queue/DLQ/alarm state, the trigger settings, the Lambda's environment and its deployed files (`handler.py`, `sandbox.py`). The console views show the same data but weren't clicked through. Two gaps found: prod Postgres has **no public endpoint** (no `psql` from the laptop: use the deployed admin), and the seeded `trainer` is **not staff** (superuser `codemas-admin` was created for the admin demo).
>
> **Before touching any Railway variable**, read "Railway deploy rules" in `deploy/aws/README.md`. A variable change without `--skip-deploys` silently reverts production to the old pre-pipeline code.

Related: [dev-pipeline.md](dev-pipeline.md) (how to run it), `Codemas-SYSTEM_DESIGN.md` §5 (design), `submission_animation.html` (step-through diagram).

---

## The flow in one breath

> "The submit request writes the submission and a job row in one Postgres transaction. That job row is the outbox. A relay process picks up pending jobs with `SKIP LOCKED` and sends only the job id and a per-job token to the queue. The executor has no database credentials, no shared secret and no answers: it claims the job from Django with that token, gets the code and test inputs plus a lease token, runs each test in a resource-limited child process, and posts the raw outputs back. Django decides pass or fail and writes the results, but only if that lease token still owns the job. The browser polls a status endpoint the whole time. Locally, the relay runs that executor code itself, in a thread pool. In production the same code runs as a Lambda fed by SQS, live for Python and JavaScript since October 5th. AI feedback, hints, plagiarism, and C++ and Java execution are still on Celery."

---

## Pre-demo checklist

**Use a dedicated demo exam and a dedicated demo student.** Demo submissions use up that student's attempts. They also feed plagiarism scoring when the exam closes. Never demo with a real student's account or on a real cohort's exam.

**Local demo** (about 15 minutes before)
- [ ] Postgres and Redis up.
- [ ] `runserver` on :8000, `run_relay` running (prints `relay: transport=local …`), Celery worker running, Vite running.
- [ ] Logged in to Django admin as a superuser in one tab (`http://localhost:8000/admin/jobs/job/`), and as the demo student, with attempts left on the active demo exam, in another.
- [ ] Browser DevTools open on the student tab, **Network** panel filtered to `status`, so you can read the submission id (see "Show me this submission being executed").
- [ ] A `dbshell` (`cd backend && venv/bin/python manage.py dbshell`) open with the outbox query below ready to paste.
- [ ] One test submission graded end to end (the tracker reaches Grade, the job row is `succeeded`).
- [ ] The question you will use has test cases. A question with none ends as `error` ("can't be graded").
- [ ] Expect "Hidden" in the Input and Expected cells of the student results: the demo questions' test cases are all hidden, so students see only their own output, time and pass/fail.
- [ ] Use Python or JavaScript. C++ and Java are still in the language picker, but they run on the Celery path (see Honest limits).

**AWS demo (live since 2026-10-05)**, in addition:
- [ ] Live code is the CLI upload, not the old GitHub commit: `railway deployment list -s <svc> --json` for backend, worker and relay; each active deployment's `meta` has `cliMessage`, not `commitHash`.
- [ ] `PIPELINE_LANGUAGES=python,javascript` on Railway backend (set, not deleted).
- [ ] Prod's open exam is "Python Binary Search Exam" (re-seeded 2026-10-05; see Re-seed below if the seed changes).
- [ ] Honest limits reread: R1 (egress open) and R2 (role credentials readable) are still present, C++/Java still on Celery with no sandbox. Say them before you're asked.

The rest (checked read-only on 2026-10-05 unless noted):
- [ ] The relay runs with `JOB_TRANSPORT=sqs`, `JOB_QUEUE_URL` set, `AWS_REGION=ap-southeast-1`.
- [ ] The web service's `JOB_SIGNING_SECRET` equals the relay's (the Lambda has none). It must not be the default `dev-only-change-me` (with `DEBUG` off, web wouldn't start: system check `jobs.E001`).
- [ ] Deployed admin open in a tab: `https://<railway-web-host>/admin/jobs/job/`, logged in.
- [ ] Superuser `codemas-admin` exists on prod (created 2026-10-05; password in `~/.codemas/admin-password` on the owner's laptop). Log in at `/admin/jobs/job/` once before the demo. The seeded `trainer` is not staff.
- [ ] **No `psql` on prod:** the Railway Postgres has no public endpoint (and the image has no `psql` client). Show the outbox on prod in the deployed admin (`/admin/jobs/job/`); keep the SQL for the local demo. Enabling a TCP proxy on Postgres would make `psql` possible but exposes the database to the internet: don't, just for a demo.
- [ ] `smoke.sh` was run with a **throwaway student, never the demo student**. Its probe submissions stay on the open exam graded `failed`, appear in trainer dashboards, and feed plagiarism when the exam closes.
- [ ] The throwaway student was **enrolled in the open exam** before `smoke.sh` ran: as the trainer, `POST /api/exams/<id>/enrollments/` with `{"username": "<throwaway student>"}` (expect 201). Students only see and submit to exams they are enrolled in; without it the exam list is empty and `smoke.sh` stops with "not enrolled". Full command: "Smoke test" in `deploy/aws/README.md`.
- [ ] The function's `CODEMAS_API_URL` is the public web URL, and that URL answers.
- [ ] The CLI is pointed at the right account and region: `aws sts get-caller-identity` and `export AWS_DEFAULT_REGION=ap-southeast-1`. The AWS CLI reads `AWS_DEFAULT_REGION`; alternatively, pass `--region ap-southeast-1` on every command.
- [ ] `QUEUE_URL=$(aws sqs get-queue-url --queue-name codemas-exec --query QueueUrl --output text)` and `DLQ_URL=$(aws sqs get-queue-url --queue-name codemas-exec-dlq --query QueueUrl --output text)` set in the terminal.
- [ ] The event-source mapping is enabled and reports batch item failures.
- [ ] Console tabs open: SQS → `codemas-exec`; Lambda → `codemas-exec` → **Code** tab only; CloudWatch → Log groups → `/aws/lambda/codemas-exec`. The function's Configuration → Environment variables holds only `CODEMAS_API_URL` and `PATH`: no secret.
- [ ] The DLQ is empty, or you know why it isn't.
- [ ] **Just before you start**, not 15 minutes earlier, grade one warm-up submission through AWS, so the first live one doesn't pay a Lambda cold start.

### Rollback (Python and JS back to Celery)

```bash
railway variable set "PIPELINE_LANGUAGES=" -s backend --skip-deploys && railway up -s backend --detach
```

Run it from the repo root. Set the variable to empty; **never delete it** (unset, it defaults to `python,javascript`). The Railway services are disconnected from GitHub (2026-10-05), so a variable change can no longer pull old code; keep `--skip-deploys` + `railway up` anyway, so the variable and the code go live together. Don't use `railway redeploy` or the dashboard Deploy button to pick up a config change: both reuse the previous deployment's config. Full rules: "Railway deploy rules" in `deploy/aws/README.md`.

### Re-seed (owner only)

Prod was re-seeded on 2026-10-05 (98 students, open exam "Python Binary Search Exam", real Phase 2 plagiarism run); `smoke.sh` passed against it. Re-run these steps only after changing the seed. In the current seed, Phase 2 runs through the real exam-close path on every closed exam; planted copying cases are caught from Phase 1 suspects. Prod still holds the 2026-10-05 data until it is re-seeded.

1. Railway dashboard → backend → Settings → Deploy → **Pre-deploy command**: `python manage.py seed_data --clear`. (Superuser `codemas-admin` already exists; re-seeding keeps staff accounts.)
2. From the repo root: `railway up -s backend --detach`. **Not** the dashboard Deploy/Redeploy button: a redeploy reuses the previous deployment's config, so the pre-deploy command wouldn't run (that is exactly how the first re-seed attempt silently did nothing).
3. When it finishes, **clear the pre-deploy command**, then run `railway up -s backend --detach` once more: the live deployment keeps its own copy of the pre-deploy command, and a dashboard Redeploy of it would wipe the data again.
4. Check that the open exam is "Python Binary Search Exam", and that `codemas-admin` can still log in at `/admin/jobs/job/`.
5. Fill in the AI layer the seed skips. The seed writes submissions and results directly, so the per-submission `after_grading` hook (rubric review, and a hint on failed attempts) never fired for them, and nothing has a weekly recommendation yet. Run both on the **backend** service (the worker lacks `JOB_SIGNING_SECRET`, so Django's checks stop management commands there):
   - `railway ssh -s backend -- python manage.py backfill_ai_feedback`: queues the same `score_rubric` / `generate_hint` tasks live grading uses, for every graded submission missing one (about 2,000 calls at the 2026-10-05 seed; the worker clears them in roughly an hour). Re-running skips ones already done.
   - `railway ssh -s backend -- python manage.py generate_weekly_recommendations`
   - (Only for data seeded before 2026-10-06) `railway ssh -s backend -- python manage.py apply_starter_code`: sets the open exam's starter code; a new seed does it itself.: this week's recommendation for every student with a graded exam (about 98 calls).

   If asked why seeded history has reviews: "Rubric scoring fires per submission right after grading. The seed inserts history directly, so we backfill it through the same task."

### Rehearse, then reset (same exam, same students)

Rehearse on the real open exam with the exact accounts you will demo with, then put them back to "never attempted":

1. Dry run (shows what would go): `railway ssh -s backend -- python manage.py reset_exam_attempts --exam 21 --users riya_verma,kabir_malhotra,meera_iyer`
2. Delete: add `--yes` (this also undoes **Submit exam** for those students). It removes those students' submissions on that exam and everything tied to them (results, rubric reviews, hints, behavioural flags, similarity pairs and their AI explanations, execution jobs, review-log entries, disputes, cached exam summaries) plus the exam's **manual** plagiarism reruns. Nobody else's data changes, and attempts come back.
3. In every browser profile you rehearsed in: clear site data for `codemas.up.railway.app` (code drafts are saved in the browser, so the editor would otherwise open with the rehearsal code).
4. If a Monday 07:00 IST passed during rehearsal, those students' weekly recommendation was written from rehearsal results; re-run `generate_weekly_recommendations` after the reset only if that matters.

To trigger plagiarism during a rehearsal: Investigation → the exam → **Rerun** (the reset removes these manual runs). A copier is compared when their weighted risk reaches the Policy page's "Compare code from risk score" (default 35%) or 3+ signals fire. With default weights, pasting ≥70% of the code alone scores 40%, so it is enough; submitting within ~20% of the baseline (medium: about 48 s) alone scores 30%, so pair it with another signal (tab switches 5+, or a partial paste). Signals: paste ≥70% (weight 40%), very fast submit (30%), 5+ tab switches (15%), unusual attempt pattern (15%).

---

## Demo questions

### "Show me the outbox table"

**Admin:** `http://localhost:8000/admin/jobs/job/`.
- Use the **By status** filter on the right (`?status__exact=pending`, `queued`, `running`, `succeeded`, `failed`, `dead`).
- Search takes a submission id or a job id.
- The list is read-only: no add, no delete.
- Columns: id, kind, subject_id (the submission id), status, attempt, published_at, started_at, finished_at, lease_expires_at, created_at.

**SQL** (local demo only: `venv/bin/python manage.py dbshell`. Prod Postgres has no public endpoint, so on prod show the same data in the deployed admin):

```sql
select id, status, attempt, published_at, started_at, finished_at
from jobs_job order by created_at desc limit 10;
```

Useful follow-ups:

```sql
-- the job for one submission
select id, status, attempt, lease_expires_at, last_error
from jobs_job where kind = 'execute_submission' and subject_id = <submission_id>
order by created_at desc;

-- what is waiting in the outbox right now
select id, subject_id, attempt, last_error, created_at
from jobs_job where status = 'pending' order by created_at;

-- overall shape
select status, count(*) from jobs_job group by status;
```

What to point out:
- `pending` is the outbox: committed, not yet published. The relay marks a job `queued` with `published_at` only after the transport accepted it.
- `attempt` counts claims. It is 1 for a normal run.
- A partial unique index allows only one active (`pending`, `queued` or `running`) job per submission.

### "Show me the SQS queue"

**Console:** SQS → Queues → `codemas-exec`. The queue list and the queue's Monitoring tab show *Messages available* and *Messages in flight*. The dead-letter queue is `codemas-exec-dlq`.

**CLI:**

```bash
aws sqs get-queue-attributes --queue-url "$QUEUE_URL" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible
aws sqs get-queue-attributes --queue-url "$DLQ_URL" \
  --attribute-names ApproximateNumberOfMessages
```

What to point out:
- A message is only `{"job_id": "<uuid>", "kind": "execute_submission"}`, with message attributes `job_id` and `language`. No code, no test answers. Postgres stays the source of truth.
- In normal operation both counts are near 0. Lambda should pick a message up within about a second.
- CloudWatch → Alarms → `codemas-exec-dlq-not-empty` is the DLQ at a glance: OK means the DLQ is empty, In alarm means it holds at least one message. It has no notification action; it is only a console indicator.

**Don't use "Poll for messages" on `codemas-exec` during the demo.** Receiving a message in the console hides it from Lambda for the visibility timeout (540 s), so that submission would wait about 9 minutes. To show a message body, poll the DLQ (if it has anything), or show `_message()` in `backend/jobs/transports.py`.

**Locally** there is no queue: the relay hands the same message to a thread pool that calls the handler. Say so, and show `LocalTransport` in `backend/jobs/transports.py`.

### "Show me the code in the Lambda"

**Repo (works today):** `lambda/exec/handler.py` and `lambda/exec/sandbox.py`. This is the code deployed to the function, and the local transport imports this same `handler.py`.

**Console:** Lambda → Functions → `codemas-exec` → **Code** tab. Configuration → Environment variables holds only `CODEMAS_API_URL` and `PATH`; the function has no secret to show. The Code tab should show two files: `handler.py` (claim, run, complete) and `sandbox.py` (the child process and its limits). The runtime is Python 3.12 on arm64 (Graviton). JavaScript runs with `node` from the `codemas-node22` layer.

What to point out in `handler.py`:
- No database credentials, no shared secret, no expected outputs and no third-party packages. Everything goes through Django's internal API with the per-job token from the SQS message (`HMAC-SHA256(JOB_SIGNING_SECRET, "job:" + job_id)`, minted by the relay). A token read by student code works only for that one job.
- `_run_tests()`: the first student timeout marks the rest "Not run". If the Lambda itself runs out of time first, the job is released with `/fail/`. That is never a failing grade.
- `_post()`: the token rides in the JSON body of claim, complete and fail. Complete and fail also need the lease token, so a stale run can't overwrite a newer one.
- `_complete_body()`: the result is sent as UTF-8 JSON and kept under 2,000,000 bytes (Django refuses bodies over 2.5 MB). Huge student output is trimmed with `[output truncated]` and still graded, never turned into an infrastructure failure. Every output is trimmed alike, because the handler never sees the expected outputs.

### "Show me this submission being executed"

**Get the submission id.** The student UI doesn't show it. Use either:
- **DevTools → Network** on the student tab. The polling requests are `/api/submissions/<id>/status/`, and the number in the path is the submission id.
- The **newest row's `subject_id`** in the Jobs admin, or `select subject_id from jobs_job order by created_at desc limit 1;`.

The handler prints one JSON line per graded job:

```
{"job_id": "…", "submission_id": 17565, "language": "python", "tests": 3, "submission_status": "passed", "complete": 200, "duration_ms": 164}
```

**Locally**, these JSON lines print in the relay's terminal.

**CloudWatch, CLI** (all three filters verified on 2026-10-05):

```bash
aws logs tail /aws/lambda/codemas-exec --since 5m --filter-pattern '{ $.submission_id = <id> }'
```

To see every line for one job: claim refusals, grader errors and releases carry `job_id` but not `submission_id`.

```bash
aws logs tail /aws/lambda/codemas-exec --since 30m --filter-pattern '{ $.job_id = "<job uuid>" }'
```

One more line type can't be found by either filter. When the handler fails before it can read the job, it logs `{"messageId": "…", "error": "…"}`. Typical causes are Django being unreachable during the claim, or an unreadable message. On SQS, `messageId` is the SQS message id, not the job id. Find these lines by their key:

```bash
aws logs tail /aws/lambda/codemas-exec --since 30m --filter-pattern messageId
```

Locally, the transport sets `messageId` to the job id.

**Console:** CloudWatch → Log groups → `/aws/lambda/codemas-exec` → Search all log streams, with the same filters.

The JSON filters assume the function's default Text log format, where each `print()` line is the log message.

### "What happens if something is down?" Live: stop the relay

**Local demo only.** On a deployed system, stopping the relay halts grading for every student, not just yours.

1. Stop the relay (Ctrl-C). It prints `relay: stopping`.
2. Submit as the demo student. The POST still returns 201 at once: the request never touches the queue.
3. The tracker sits on **Queue** ("Waiting in line"). After 10 s it adds "Taking longer than usual… you are still in line."
4. Show the job in admin (status filter **pending**) or with SQL: `status = 'pending'`, `published_at` empty, `attempt = 0`.
5. Start the relay again. It prints `relay: published 1`, and the row goes `queued` → `running` → `succeeded`.
   - If you restart within 2 minutes, the tracker moves to Execute and then Grade within a few seconds.
   - After 2 minutes of waiting, the page polls only every 10 s, so the tracker can lag the database by up to 10 s. Keep the stop short, or point at the admin row while the tracker catches up.

The point: the outbox makes "row written but message lost" impossible. Nothing is published until the transaction commits, and nothing committed is lost while the relay or queue is away.

### "Show me the tests"

```bash
cd backend && venv/bin/python manage.py test jobs          # 85 tests
python3 -m unittest discover -s lambda/exec/tests          # 80 tests (16 Linux-only skipped on a Mac)
```

Good ones to open:
- `jobs/tests/test_api.py`: claim state machine, stale lease, bad or another job's token (401), no `expected` in the claim.
- `jobs/tests/test_e2e.py`: duplicate deliveries graded once, a grader crash released and regraded, an out-of-attempts job dies and frees the attempt.
- `jobs/tests/test_relay.py`: `SKIP LOCKED` concurrency, sweep behaviour per transport.

---

## What happens on a crash, a grader error, or when the queue is down

Use this when asked "what if…". It matches the code as built. The SQS rows describe the AWS behaviour the code implements. The live stack has graded the normal path; these failure paths haven't been exercised on it yet.

**Words used below:**
- **Attempt** means a claim. Every claim adds 1 to `jobs_job.attempt`, and the limit is 3.
- **Lease** is 150 s, longer than the 90 s Lambda timeout.
- **Student attempts** are separate. Any submission that ends with `status = 'error'` (a dead job, or a question with no tests) does not count against the student's attempt limit.

| Situation | What happens | What the student sees |
|---|---|---|
| **Relay down** | Jobs wait as `pending`. They publish on the first tick after it restarts. | "Waiting in line", then "Taking longer than usual…" |
| **Queue down** (SQS unreachable or refusing) | The publish fails, so the job stays `pending` with `last_error` `publish failed: …`. Every tick retries. One failed chunk stops that tick, so the relay doesn't spend a timeout per batch. | Same as relay down |
| **Grader error** (exception in the grader, not the student's code) | The handler calls `/fail/`. The job goes back to `pending` (the attempt still counts) and the relay republishes it on the next tick. The handler then **acknowledges** the message, so SQS doesn't retry it as well. | "Retrying… This does not use another attempt." |
| **Lambda out of time** before any student timeout | Treated as a grader error: `/fail/`, never a failing grade. | "Retrying…" |
| **Crash or Lambda timeout** (no `/fail/` sent) | **SQS:** nothing acknowledged the message, so it reappears after the 540 s visibility timeout (about 9 minutes). The new delivery claims the expired lease with a new token. A late `complete` from the old token gets 409 `stale` and writes nothing. **Local:** the transport redelivers after 2 s and 5 s; after that the sweep requeues the job once the 150 s lease has expired. | "Retrying…" once the retry claims it |
| **Duplicate delivery** | A second claim gets 409 `done` (the message is acknowledged) or 409 `busy` (it is retried later). Only the lease holder can complete. | Nothing |
| **Third attempt fails** | The next claim returns 410 `dead`. If the third was a crash, the sweep marks the job `dead` when its lease expires at the limit. The submission becomes `error` and the student gets the attempt back. | "We couldn't grade this submission because of a problem on our side. It doesn't count as an attempt, so please submit again." |
| **Wrong answer, error, or student timeout** | A normal `succeeded` job with a failing grade. Never retried. After the first student timeout, the remaining tests are "Not run". | The failing result |
| **Huge or garbage output** (e.g. megabytes of invalid UTF-8) | The handler trims each test's output and error until the `/complete/` body is under 2,000,000 bytes, then completes normally. | The failing result, with `[output truncated]` |

**The dead-letter queue, precisely.** `codemas-exec-dlq` holds messages whose delivery wasn't acknowledged 3 times. The handler leaves a message unacknowledged (it reports it in `batchItemFailures`, or the invocation dies) when:
- the invocation crashed or hit the 90 s timeout;
- the claim got anything other than `done`, `gone` or `dead`. That includes `busy`, 401 (job token refused), 404 (unknown job) and 5xx;
- Django was unreachable;
- the `/fail/` call itself failed;
- `complete` returned anything other than 200 or 409;
- less than 30 s of Lambda time was left, so it skipped the claim.

Each of those spends one receive. On the third, SQS moves the message to the DLQ.

A job released through `/fail/` has its message acknowledged, so it **dies in Postgres with no DLQ message**. In short:
- An empty DLQ does not mean no job died. Check `select … where status = 'dead'`.
- A DLQ message does not always mean a dead job. A delivery that never claimed doesn't spend an attempt. The sweep backstop republishes such jobs:
  - a `queued` job unclaimed for more than 30 minutes;
  - a `running` job whose lease expired more than 30 minutes ago.

**Sweep, by transport** (runs every 60 s inside the relay):
- **Local:** requeues expired leases, marks them `dead` at the attempt limit, and requeues jobs `queued` for more than 10 minutes.
- **SQS:**
  - It leaves expired leases below the limit to SQS redelivery.
  - It still marks them `dead` at the limit.
  - It requeues jobs `queued` for more than 30 minutes.
  - As a backstop, it requeues `running` jobs whose lease expired more than 30 minutes ago.
  - 30 minutes is longer than SQS's own retries (3 × 540 s ≈ 27 minutes).

---

## Honest limits (say these before you're asked)

- **The AWS pipeline is live, but young.** Since 2026-10-05 production grades Python and JavaScript on Lambda (`PIPELINE_LANGUAGES=python,javascript`); the go-live smoke test is the only production run so far. Locally the relay runs the executor code in-process (`JOB_TRANSPORT=local`). Don't claim live AWS numbers: none have been measured.
- **C++ and Java are not sandboxed.** Both are selectable in the exam's language picker. They go through the legacy Celery task, which runs them with `run_local` (`backend/execution/tasks.py`) **on the Celery worker host with no sandbox**. The docstring says so: development only. All it does is:
  - strip the environment;
  - apply a 10 s timeout;
  - drop to `nobody` when the worker runs as root.

  There are no rlimits and no isolation from the host. Don't claim C++/Java run in the Lambda sandbox, or are safe in production.
- **Python and JavaScript isolation is process-level.** One Lambda; the handler runs student code in a constrained child process (rlimits, an empty environment, its own process group) inside the function's Firecracker microVM. There is no kernel boundary between the grader and the child. Locally the scrub is off, so student code runs on the developer's machine under rlimits only.
- **Guardrails, not isolation.** No secrets or answers in the Lambda (it never has `JOB_SIGNING_SECRET` or expected outputs) and per-job tokens. **Known limits, accepted (2026-10-04 smoke test, still present at the 2026-10-05 go-live):**
  - **R1, egress.** Real Lambda refuses the seccomp filter (`egress_blocked=false`), so student code can reach the internet. Bounded by CPU time per test, concurrency 5, attempts and the submission throttle.
  - **R2, role credentials.** Student code can read the role's AWS credentials (another runtime process exposes them in `/proc/<pid>/environ`), and the role can `ReceiveMessage`, `DeleteMessage` and `ChangeMessageVisibility` on `codemas-exec`. A determined student with a working solution could take a classmate's queued message, claim that job first, read the classmate's code and test inputs, and post outputs that forge a pass or a fail. They can also delay other students' grading by deleting or hiding messages. Exposure is highest under an exam-deadline backlog (concurrency 5).
  - **Still holds:** the signing secret and the expected answers never enter the Lambda, and a student can't pass their own submission without correct output. The real fix is the two-function split (see Future work).
- **The SQS crash retry is slow:** about 9 minutes, the cost of the 540 s visibility timeout. Grader errors retry at once through `/fail/`.
- **Still on Celery:** C++ and Java execution (chosen per language by `PIPELINE_LANGUAGES`), AI rubric feedback, hints, plagiarism, and Beat.
- **Capacity numbers are planning estimates.** No load test has been run on this pipeline.

---

## Future work

- Split the Lambda in two, the standard pattern for online judges: the grader invokes a runner with a zero-permission role, in a VPC with no NAT or internet gateway and a security group with no outbound rules, and reads its return value. That closes R1 (egress) and R2 (role credentials).

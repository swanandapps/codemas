# Job pipeline on the latest architecture: design

Date: 2026-10-03
Status: revised 2026-10-03 for a live, demoable AWS build; awaiting approval
Related: [Exam supporting material](2026-10-03-exam-supporting-material-design.md), which is the second job type on this pipeline.

## As built (2026-10-04)

Phase 1 is built and running with the local transport, and live on AWS (`codemas-pipeline`, ap-southeast-1) for Python and JavaScript since 2026-10-05. The body below is the design as approved and is kept as written. Where it disagrees with the code, the code wins, and this list and the [failure table](#failure-handling-summarised) describe the code. Full detail is in `Codemas-SYSTEM_DESIGN.md` §5 and `docs/demo-runbook.md`.

- **Go-live (2026-10-05).** Python and JavaScript grade through outbox → relay (Railway) → SQS `codemas-exec` → Lambda `codemas-exec` (arm64) with `PIPELINE_LANGUAGES=python,javascript` on Railway backend; the secret was rotated at cutover. The smoke test graded both through the pipeline and found no `JOB_SIGNING_SECRET`; R1 and R2 are present, as accepted. C++ and Java stay on Celery.
- **Railway gotcha.** The Railway services track GitHub branch `feature/ai-features` at the old pre-pipeline commit `902417d`; live code is a `railway up` CLI upload. Any variable change needs `--skip-deploys` then `railway up -s <service> --detach`, or it silently redeploys the old commit. Rollback: `railway variable set "PIPELINE_LANGUAGES=" -s backend --skip-deploys && railway up -s backend --detach` (empty, never deleted). Rules: `deploy/aws/README.md`.

- **Lambda guardrails** (§4, §5; amended by `2026-10-04-lambda-guardrails.md` after the first production smoke test). One Lambda; the handler runs student code in a constrained child process. Guardrails:
  - **No expected outputs leave Django.** The claim returns `tests: [{id, input}]`; `apply_result` compares.
  - **No shared secret in the Lambda.** The relay puts `token = HMAC-SHA256(JOB_SIGNING_SECRET, "job:" + job_id)` (hex) in each message, next to `job_id` and `kind`. Claim takes `{job_id, token}`; complete and fail take `{job_id, token, lease_token, …}`. Wrong or missing token → 401. The `X-Timestamp`/`X-Signature` signing is gone. Code: `jobs/signing.py` `job_token`/`token_ok`, `jobs/views.py`, `jobs/transports.py` `_message`, `lambda/exec/handler.py`.
  - **Known limits, accepted:** R1 egress (Lambda refuses the seccomp filter, so student code can reach the internet) and R2 role credentials (student code can read them, and with `sqs:ReceiveMessage` could take another queued job's id and token). The fix for both, the two-function split (grader invokes a runner Lambda with no secrets, no permissions, no internet), is future work.
- **Network egress is blocked only where seccomp works** (§4). On Linux the sandboxed child runs under a seccomp-BPF filter: `socket()` is allowed for `AF_UNIX` only, so `AF_INET`/`AF_INET6` get `EACCES`. It fails open if the kernel refuses seccomp, **which real Lambda does** (`egress_blocked=false`, smoke probe `EGRESS_OPEN`): accepted risk R1. Code: `lambda/exec/sandbox.py`.
- **Sweep differs per transport** (§2). It runs every 60 s inside the relay.
  - Local: requeues expired leases; requeues jobs `queued` for more than 10 min.
  - SQS: leaves expired leases below the attempt limit to SQS redelivery; requeues jobs `queued` for more than 30 min; a backstop requeues `running` jobs whose lease expired more than 30 min ago.
  - Both mark a job `dead` when its lease expires at the attempt limit.
  - Code: `jobs/relay.py` `sweep_stuck`.
- **Publishing** (§3). `send_message_batch` with 10 per call, not `send_message`. The botocore client has connect 3 s / read 5 s timeouts and 3 attempts, because the relay holds row locks while publishing. A failed chunk leaves the rest `pending`. An unknown `JOB_TRANSPORT` raises. Code: `jobs/transports.py`.
- **`/fail/`** (§5). It puts the job back to `pending`, not merely "releases the lease", so the relay republishes it on its next tick in either transport. The attempt still counts. Code: `jobs/services.py` `fail`.
- **The handler acknowledges the message after a successful `/fail/`** (§4). Once the job is `pending`, the relay owns the retry. The handler reports the message for retry only if `/fail/` itself fails. Code: `lambda/exec/handler.py` `_release`.
- **Log line** (§4). The line is `{job_id, submission_id, language, tests, submission_status, complete, duration_ms}`. It has no `attempt` or `passed`. Claim refusals, grader errors and releases log `job_id` only. A failure before the job id is known logs `messageId` only.
- **Claim mechanics** (§5). Claim is not one conditional `UPDATE`. It is one `SELECT … FOR UPDATE`, then a decision in code:
  - terminal → 409 `done`;
  - live lease → 409 `busy`;
  - subject deleted → job `failed`, 410 `gone`;
  - `attempt` already 3 → `dead`, 410;
  - otherwise lease, token and `attempt += 1`.

  Refusals are raised after commit, so the `gone`/`dead` writes persist. Code: `jobs/services.py` `claim`.
- **Polling** (§7). Poll at once, then 1 s ×5, 2 s ×2, then every 3 s. After 2 minutes it slows to every 10 s. The tracker never moves backwards. It shows "Retrying…" when `attempt` shows a re-claim, and "Taking longer than usual…" after 10 s. Code: `ExamTakeView.vue` `listenForResult`.
- **`failed` versus `error`** (§1). Job `failed` is set only when the submission was deleted (claim `gone`). A wrong answer is still a `succeeded` job. Submission `error` is set three ways:
  - a claim that finds the job out of attempts (`dead`);
  - the sweep, when a lease expires at the limit;
  - `complete` on a question with no tests.
- **`status='error'` never counts as an attempt** (§6, failure table). The create view excludes every `error` submission from the count, not only dead-job ones. It locks the student's `User` row, not a (student, question) count.
- **Sandbox hardening beyond §4:**
  - `prctl(PR_SET_DUMPABLE, 0)` at handler import, so student code can't read the grader's own `/proc/<ppid>/environ`. On real Lambda another runtime process (`/proc/2/environ`) still exposes the role's credentials: accepted risk R2.
  - On Lambda, or with `CODEMAS_EXEC_SCRUB=1`, the temp dir is wiped and leftover same-uid processes are killed between runs.
  - The Node heap is capped at `--max-old-space-size=192`. Python has `RLIMIT_AS` 256 MB.

- **Time budget** (§4). The handler won't claim with less than 30 s of Lambda time left. After the first student timeout, the remaining tests are reported "Not run". If the Lambda's own time runs out with no student timeout, the job goes to `/fail/`, never a failing grade. The local transport has no time-budget guard.
- **Old code** (§10). The four `lambda/*_runner.py` files still exist, pending the owner's decision to delete them. `run_in_lambda` is gone from `execution/tasks.py`.
- **arm64 (Graviton), not x86_64** (§4). The function and its layer are arm64: the architecture the seccomp egress filter is proven on natively, and about 20% cheaper per GB-second. The filter is proven natively on arm64 (aarch64), the architecture the Lambda runs on; the x86_64 branch is a fallback, checked only by the BPF-interpreter test. Code: `deploy/aws/pipeline.yaml`, `deploy/aws/build.sh`.
- **Signing secret guard** (§5). The secret is held by web and relay only. With `DEBUG` off (`JOB_SIGNING_SECRET_REQUIRED`), an empty, default or shorter-than-32-character secret fails system check `jobs.E001` (stops `migrate` and `run_relay`) and the internal API answers 503. Code: `jobs/checks.py`.
- **`complete` body cap** (§4). UTF-8 JSON (`ensure_ascii=False`), kept under 2,000,000 bytes by halving the cap for every output and error alike (with `[output truncated]`) until it fits; the handler can't spare a correct output because it never sees the expected one, so a correct output is lost only when the whole body exceeds ~2 MB (about 30+ tests near the 64 KB cap). Django's 2.5 MB `DATA_UPLOAD_MAX_MEMORY_SIZE` would otherwise answer 400 and the job would die as an infrastructure failure. Code: `lambda/exec/handler.py` `_complete_body`.
- **Status-poll index** (§1). `jobs_job_subject_idx` on (`subject_id`, `kind`), because the partial unique index can't serve a lookup with no status predicate. Migration `jobs/0002`.
- **SSE removed** (§7). `submissions/sse.py`, its `/stream/` route and the legacy task's Redis publishes are gone; every language is polled.
- **Duplicate attempts** (§6). `submissions/0008` renumbers any duplicate (student, question, attempt_number) rows by (`submitted_at`, `id`), only in affected groups, before adding the unique constraint.
- **Node 22, not Node 20** (§4). Node 20 reached end of life on 2026-04-30, so the layer is `codemas-node22`: the official Node.js v22.23.3 (LTS) Linux arm64 binary at `/opt/bin/node`, with its SHA256 pinned in `deploy/aws/build.sh` and checked against nodejs.org's `SHASUMS256.txt`. Code: `deploy/aws/build.sh`, `deploy/aws/pipeline.yaml`.

## Goal

Move submission execution, and the new exam-material generation, off Celery onto the documented latest CodeMas architecture:

```
request → Postgres (row + outbox job, one transaction) → relay → SQS → Lambda
        → Django internal API (claim / complete) → Postgres → browser polls status
```

Two requirements shape everything below:

1. **Real and demoable.** In the live demo every hop can be shown on request: the outbox rows in Postgres, the SQS queue and its dead-letter queue, the Lambda function's code in the AWS console, and that invocation's log line in CloudWatch, all for the submission just made.
2. **Works before AWS exists.** On a laptop, a local transport runs the same handler code in-process, so development and tests need no AWS account. Switching to SQS and Lambda is configuration only.

The live demo runs on **Railway (web, relay, Postgres) plus AWS (SQS, Lambda) in ap-southeast-1**. Lambda calls back to Railway's public URL.

Build order: **phase 1** is submission execution (this spec). **Phase 2** is exam-material generation as a second job kind on the same pipeline, per the material spec.

## Scope

| Work | Path after this change |
|---|---|
| Submission execution, Python and JavaScript | Job pipeline |
| Submission execution, C++ and Java | Legacy Celery path, behind a per-language switch (needs a heavier Lambda image; later) |
| Exam material generation | Job pipeline, phase 2 |
| AI rubric, hints, plagiarism, Celery Beat schedules | Celery, unchanged for now. The demo says so openly. |

## Components

### 1. `jobs` Django app: the outbox and the lease

Model `Job`:

| Field | Notes |
|---|---|
| `id` | UUID. This is the only thing the queue message carries. |
| `kind` | `execute_submission` or `generate_material` |
| `subject_id` | Submission ID or Question ID |
| `status` | `pending` → `queued` → `running` → `succeeded` / `failed` / `dead` |
| `attempt` | Incremented on every claim |
| `lease_token`, `lease_expires_at` | Who may finish the job, and until when |
| `published_at`, `created_at`, `updated_at` | |
| `last_error` | Short text for operators |

Meaning of each status:

- `pending`: committed to Postgres, not yet published. This is the outbox.
- `queued`: the transport accepted it.
- `running`: a handler holds a live lease.
- `succeeded` and `failed`: terminal. `failed` means the job finished but produced a failure result, for example material generation that could not produce a solution. A wrong student answer is still `succeeded`; the grade lives on the submission.
- `dead`: infrastructure failure after the maximum number of attempts (3). This is the dead-letter state.

`Job` is registered in Django admin (read-only list with filters by kind and status, search by submission), which is how the outbox is shown in a demo.

Constraint: at most one active job (`pending`, `queued` or `running`) per (`kind`, `subject_id`), enforced with a partial unique index.

`jobs.enqueue(kind, subject_id)` must be called inside the same `transaction.atomic()` block that creates or changes the subject row. It writes the job and never publishes. If the transaction rolls back, neither row exists.

### 2. Relay: `manage.py run_relay`

A long-running process, deployed as its own Railway service named `relay`.

- Every 0.5 s it selects up to 50 `pending` jobs with `SELECT … FOR UPDATE SKIP LOCKED`, publishes each one through the configured transport, and marks it `queued` with `published_at`. Several relay replicas never claim the same rows.
- A crash after publishing but before marking can publish a job twice. That is safe because claiming is idempotent (below).
- A recovery sweep, once a minute, handles stuck jobs:
  - `queued` for more than 10 minutes without being claimed, or `running` with an expired lease: reset to `pending` if `attempt` < 3, otherwise mark `dead`.
  - In SQS mode this mostly duplicates what SQS redelivery already does. It stays as a safety net, since claiming is idempotent.

### 3. Transports (`JOB_TRANSPORT` setting)

- **`local`** (laptops, tests): the relay hands the message to a thread pool inside the relay process, which calls the same `handler(event, context)` function the Lambda runs, with an SQS-shaped event. The handler code is identical to what is deployed; JavaScript uses the machine's `node`.
- **`sqs`** (Railway demo): `boto3` `send_message` to a single queue, `codemas-exec`, for every language. It has one dead-letter queue, `codemas-exec-dlq` (`maxReceiveCount=3`), and one event-source mapping to the executor function.

The message body is only `{"job_id": "<uuid>", "kind": "execute_submission"}`, plus message attributes `job_id` and `language` so a queue's messages can be inspected meaningfully during the demo.

### 4. Lambda function: `lambda/exec/` (no Django, no third-party dependencies)

One **zip-packaged** Python 3.12 function, `codemas-exec`, runs both Python and JavaScript submissions. Its code (`handler.py`, `sandbox.py`) uses only the standard library (`urllib`, `hmac`, `subprocess`, `resource`), so it is small and readable in the Lambda console's Code tab. JavaScript runs with `node` from a **Node.js layer**: the official Node.js 20 Linux x64 binary, built into a layer by the deploy script and attached to the function. The layer holds no CodeMas code.

The handler, for every SQS record:
1. `claim` the job from Django (signed request). The response carries the language, the code, the tests `[{id, input, expected}]` and the limits.
2. Run each test in a child process through the one sandbox below (`python3 main.py` or `node main.js`).
3. `complete` with the per-test results.
4. Log one structured line per job, `{"job_id", "submission_id", "language", "attempt", "tests", "passed", "duration_ms"}`, so CloudWatch shows exactly which submission an invocation graded.

The function holds only `CODEMAS_API_URL` and `JOB_SIGNING_SECRET`: no database credentials and no other secrets. Phase 2 adds a separate material-generation function that also holds the OpenAI key, so student code never runs where that key is readable.

**Sandbox (`sandbox.py`), the same for both languages.** `subprocess.Popen` with `shell=False`, a fixed command, a temporary working directory and an empty environment. In the child (`preexec_fn`), `resource.setrlimit` caps memory (`RLIMIT_AS`, 256 MB; raised for Node's address-space needs if tests show it must be), CPU time, number of processes and file size. A wall-clock timeout kills the process group, and output is capped at 64 KB.

What this does not give: per-job network isolation, or a kernel boundary between the handler and the child. Inside Lambda the whole function shares one Firecracker microVM. The docs say so plainly. Splitting into one queue and function per language (for isolation or separate scaling) is a later option, not needed at this scale.

### 5. Internal API (`jobs` app)

Every request is signed: `X-Signature: sha256=<HMAC(JOB_SIGNING_SECRET, timestamp + "." + body)>` plus `X-Timestamp`. Requests more than 300 s old are rejected. These endpoints are not reachable with user session or JWT authentication.

| Endpoint | Behaviour |
|---|---|
| `POST /internal/jobs/claim/` `{job_id}` | One conditional `UPDATE`: if status is `queued` or `pending`, or `running` with an expired lease, and the job is not terminal, set `running`, a new `lease_token`, `lease_expires_at = now + lease` (executor 150 s, longer than the 90 s function timeout; material 300 s) and `attempt += 1`. If the attempt limit is exceeded, mark `dead` and return 410. On success return `{lease_token, payload}`. A terminal job returns 409 `done`, so the handler acknowledges the message. A live lease held by another handler returns 409 `busy`. |
| `POST /internal/jobs/complete/` `{job_id, lease_token, result}` | In one transaction: check that `lease_token` matches and status is `running`, apply the result for that kind, and mark the job `succeeded` or `failed`. A stale or unknown token returns 409, and nothing is written. |
| `POST /internal/jobs/fail/` `{job_id, lease_token, error}` | Records `last_error` and releases the lease early, so a retry can claim at once. |

Applying an `execute_submission` result:
- `Result` rows are written. The existing unique constraint on (`submission`, `test_case`) makes a duplicate completion harmless.
- The submission becomes `passed` or `failed`, and `execution_time_ms` is set.
- Then, on commit, the existing side effects still run: code normalisation, `notify_result_ready`, and the Celery rubric and hint tasks.

### 6. Submission flow changes

`SubmissionCreateView`:

1. In one transaction: lock the (student, question) attempt count with `select_for_update`, create the submission as `pending`, and call `jobs.enqueue('execute_submission', id)` if the language is in `PIPELINE_LANGUAGES` (default `python,javascript`). Otherwise use the legacy `execute_submission.delay` on commit.
2. Add a unique constraint on (`student`, `question`, `attempt_number`). This closes today's check-then-insert race.
3. `GET /api/submissions/<id>/status/` returns:
   ```json
   {
     "status": "...",
     "job": {"status": "...", "attempt": 1, "queued_at": "...", "started_at": "...", "finished_at": "..."},
     "results_ready": true
   }
   ```
   Students only see their own submissions.

### 7. Frontend

`ExamTakeView` replaces SSE with polling of `/status/` for every language, since the legacy path also updates `submission.status`. It polls every 1 s for the first 5 s, then backs off to 2 s and then 3 s. It stops at a terminal state, and resumes after a page refresh using the last submission ID.

The pipeline tracker maps real states:

| Tracker stage | Signal |
|---|---|
| Submit | POST accepted |
| Queue | job `pending` / `queued` |
| Execute | job `running` |
| Grade | job `succeeded`, results written |
| Feedback | rubric arrives |

The tracker shows stage names only. Product screens never name internal technology; the mapping to outbox, SQS and Lambda lives in the docs and the demo runbook.

### 8. Deployment

**Laptop (development):** `JOB_TRANSPORT=local`. Run `python manage.py run_relay` next to `runserver`. No AWS needed.

**Railway + AWS (demo):**
- Railway services: `web`, `relay` (new, same image, command `python manage.py run_relay`), `worker` (Celery: rubric, hints, plagiarism, Beat, and C++/Java execution), `postgres`, `redis`.
- `relay` variables: `JOB_TRANSPORT=sqs`, `AWS_REGION=ap-southeast-1`, AWS credentials for an IAM user that may only `sqs:SendMessage` to `codemas-exec`, `PIPELINE_LANGUAGES=python,javascript`.
- `web` variables: `JOB_SIGNING_SECRET` (shared with Lambda).
- AWS, defined in one **CloudFormation template** (`deploy/aws/pipeline.yaml`) so the whole setup is reviewable and repeatable:
  - the `codemas-exec` queue and `codemas-exec-dlq`; visibility timeout 6× the function timeout
  - the `codemas-exec` Lambda function (zip) and its Node.js layer, with an execution role allowed to read the queue and write logs, nothing else
  - one event-source mapping, batch size 1, with partial batch failure reporting
  - reserved concurrency of 20
  - environment `CODEMAS_API_URL` (Railway's public URL) and `JOB_SIGNING_SECRET`
- `deploy/aws/deploy.sh` builds the Node layer, packages the function zip, deploys the stack and updates function code. `deploy/aws/README.md` lists the one-time IAM setup.

**Rollback:** `PIPELINE_LANGUAGES=""` sends every language back to Celery immediately, with no redeploy.

### 9. Demoability

Everything a reviewer may ask to see, with how to show it (written up in `docs/demo-runbook.md`):

| Ask | Show |
|---|---|
| "Show me the outbox table" | Django admin, **Jobs** (`/admin/jobs/job/`): one row per job with kind, submission, status, attempt, lease, `published_at` and timestamps, filterable by status, read-only. The same rows via SQL on `jobs_job`. |
| "Show me the SQS queue" | AWS console, SQS, `codemas-exec`: messages available and in flight, and the DLQ `codemas-exec-dlq`. Or `aws sqs get-queue-attributes`. Don't poll the live queue during a demo: receiving a message hides it from Lambda for the 540 s visibility timeout. |
| "Show me the code in the Lambda" | AWS console, Lambda, `codemas-exec`, Code tab: `handler.py` and `sandbox.py`. The same files in `lambda/exec/` in the repo, which the local transport also runs. |
| "Show me this submission being executed" | CloudWatch Logs for `/aws/lambda/codemas-exec`: the JSON line with this `job_id` and `submission_id` (`aws logs tail … --filter-pattern '{ $.submission_id = <id> }'`). Locally, the same line prints in the relay's terminal. |
| "What happens if something is down?" | Stop the relay, submit, and show the job waiting as `pending` in admin. Start the relay again and it is graded. |
| "What happens on a crash or duplicate?" | Django admin, a job's `attempt` and `last_error`; the claim, complete and end-to-end tests. Precisely: a grader error goes through `/fail/` and is republished at once by the relay, and its message is acknowledged. A crash or timeout in SQS mode waits for the 540 s visibility timeout (about 9 minutes) before the retry. The DLQ holds only messages that were never processed (crashes, timeouts, deliveries that couldn't claim). A job released through `/fail/` dies in Postgres with no DLQ message, so check `status = 'dead'`, not the DLQ, for dead jobs. |

### 10. Old code

`lambda/*_runner.py` (synchronous invoke, Python `exec` inside the handler) and `run_in_lambda` in `execution/tasks.py` are deleted and replaced by `lambda/exec/`. `run_local` stays only for the legacy Celery path.

## Failure handling, summarised

As built. Where this differs from §2, §5 and §7 above, this table and the code win.

| Failure | What happens |
|---|---|
| Database commit fails | Neither the submission nor the job exists; the user sees an error |
| Relay down | Jobs wait as `pending` and publish when it returns. The UI shows "Waiting in line", then "Taking longer than usual…" after 10 s. |
| Queue unreachable (SQS mode) | The publish fails, so the job stays `pending` with `publish failed: …` in `last_error` and is retried on every relay tick |
| Duplicate delivery | The second claim gets 409 `done` (the message is acknowledged) or 409 `busy` (it is retried later), so the code is not run twice to completion |
| Grader error, or the Lambda running out of time before any student timeout | The handler calls `/fail/`. The job goes back to `pending` (the attempt still counts) and the relay republishes it on its next tick, in either transport. The handler acknowledges the message, so SQS doesn't retry it as well. Never a failing grade. |
| Handler crash or timeout (no `/fail/`) | **SQS:** the message reappears after the 540 s visibility timeout (about 9 minutes). The claim accepts the expired 150 s lease and issues a new token; a late `complete` from the old token returns 409. The sweep leaves these leases to SQS, with a backstop that requeues a lease expired more than 30 min ago. **Local:** the transport redelivers after 2 s and 5 s, then the sweep requeues the expired lease. |
| Three infrastructure failures | `dead` in the database, either from the next claim (410) or from the sweep when a lease expires at the limit. The submission becomes `error`. The UI shows "We couldn't grade this submission because of a problem on our side. It doesn't count as an attempt, so please submit again." Every `error` submission (a dead job, or a question with no tests) is excluded from the attempt count. **DLQ:** in SQS mode a message reaches `codemas-exec-dlq` only after 3 receives that were never processed: crashes, timeouts, or deliveries that could not claim the job. A job whose failures went through `/fail/` dies in Postgres with no DLQ message. A DLQ message without a dead job is possible too, because deliveries that never claimed don't spend attempts. The sweep republishes those jobs after 30 min. |
| Wrong answer, compile error, student timeout | A normal `succeeded` job with a failing grade. Never retried. After the first student timeout, the remaining tests are reported "Not run". |

## Docs

Following the standing rule, `Codemas-SYSTEM_DESIGN.md`, `submission_flow.html` and `submission_animation.html` are updated to this flow, including the local versus SQS transport and what stays on Celery.

## Testing

- **Claim state machine:** first claim, duplicate claim (`busy`), claim after expiry with a new token, claim on a terminal job (`done`), attempt limit reached (`dead`).
- **Complete:** a valid token writes results, a stale token writes nothing, a second complete is a no-op.
- **Relay:** `SKIP LOCKED` publishing, marking `queued`, the sweep (reset versus `dead`).
- **Signatures:** a wrong signature, an expired timestamp and a missing header each get 401.
- **Sandbox runner:** an infinite loop is killed at the timeout, memory over the limit fails, a fork bomb is capped, oversized output is truncated, and the environment is empty.
- **End to end (local transport):** create a submission, run one relay tick, the handler runs it, and the status endpoint shows `passed` with results. For both Python and JavaScript.
- **Sandbox for JavaScript:** the same limit cases (infinite loop, memory, fork bomb, output size, empty environment) with `node` as the child.
- **AWS smoke test** (`deploy/aws/smoke.sh`, once the stack exists): submit one Python and one JavaScript solution through the Railway API and confirm each reaches `passed`, two messages passed through `codemas-exec`, and the function logged both `job_id`s.
- **Attempt race:** two concurrent creates for the last attempt produce one success and one 403.
- **Frontend:** type-check, build, and a browser check of the exam flow, including a refresh in the middle of grading.

## Out of scope

- C++ and Java on Lambda
- Moving the rubric, hints and plagiarism off Celery
- Load testing. The capacity numbers stay labelled as planning estimates.

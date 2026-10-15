# Submission pipeline: local development

How to run the job pipeline on a laptop, what each setting does, how to run the executor tests, and how to send a language back to Celery.

Status: **live in production since 2026-10-05** for Python and JavaScript (relay on Railway with `JOB_TRANSPORT=sqs` → SQS `codemas-exec` → Lambda `codemas-exec`, arm64, ap-southeast-1; `PIPELINE_LANGUAGES=python,javascript` on Railway backend). Locally it runs with `JOB_TRANSPORT=local`. C++ and Java stay on Celery. Accepted risks R1 (egress open) and R2 (role credentials readable) are still present: `deploy/aws/README.md`.

> **Production variable changes:** follow "Railway deploy rules" in `deploy/aws/README.md` (`--skip-deploys`, then `railway up`). The services are disconnected from GitHub (CLI upload only, since 2026-10-05).

```
POST /api/submissions/create/
  └─ one transaction: Submission row + Job row (status pending)   ← the outbox
run_relay (every 0.5 s)
  └─ SELECT … FOR UPDATE SKIP LOCKED → transport.publish_many → status queued
transport
  ├─ local: thread pool inside the relay calls lambda/exec/handler.py
  └─ sqs:   send_message_batch to codemas-exec → SQS triggers the codemas-exec Lambda
handler (same code in both)
  └─ POST /internal/jobs/claim/ → sandbox runs each test → POST /internal/jobs/complete/
browser
  └─ polls GET /api/submissions/<id>/status/ until passed / failed / error
```

Python and JavaScript use this pipeline. C++ and Java still go through the legacy Celery task (see [Flip a language back to Celery](#flip-a-language-back-to-celery)).

---

## 1. Run it locally

Prerequisites: Postgres and Redis running, `backend/venv` set up, `node` on your `PATH` (JavaScript submissions run with your machine's `node`).

Settings are read from the environment. `codemas/settings.py` calls `load_dotenv()`, so values in `backend/.env` are picked up too. None of the pipeline settings are needed locally: the defaults are a working local setup.

Open four terminals.

| # | Process | Command (from `backend/` unless noted) | Why |
|---|---|---|---|
| 1 | Django | `venv/bin/python manage.py runserver` | API, admin, and the internal `/internal/jobs/` endpoints the handler calls back to |
| 2 | Relay | `venv/bin/python manage.py run_relay` | Publishes `pending` jobs. With `JOB_TRANSPORT=local` it also **executes** them, in a thread pool |
| 3 | Celery worker | `venv/bin/python -m celery -A codemas worker --loglevel=info` | Still needed: AI rubric feedback and hints, plagiarism, and C++/Java execution |
| 4 | Vite | `npm run dev` (from `frontend/`) | Student and trainer UI. Vite prints its URL (`:5173`, or `:5174` if 5173 is taken) |

Optional: `venv/bin/python -m celery -A codemas beat --loglevel=info` for the exam auto-open/close schedule.

The relay prints `relay: transport=local interval=0.5s` on start, then `relay: published N` whenever it sends jobs, and `relay: sweep {...}` when the once-a-minute sweep changed anything.

**One-shot relay** (useful in scripts and when checking the pipeline by hand): `venv/bin/python manage.py run_relay --once` runs one tick and one sweep, waits for the local handler threads to finish, and exits.

### What runs where in local mode

- `runserver` must be reachable at `CODEMAS_API_URL` (default `http://127.0.0.1:8000`). The handler, running inside the relay process, calls back to it over HTTP to claim and complete, exactly as the Lambda does.
- The relay copies `CODEMAS_API_URL` from Django settings into its own environment. It does **not** export `JOB_SIGNING_SECRET`: the handler uses only the per-job token in each message (`token = HMAC-SHA256(JOB_SIGNING_SECRET, "job:" + job_id)`, minted by the relay) and sends it back on claim, complete and fail. Unlike on Lambda, though, the handler runs inside the relay process, which holds the secret in its environment and settings, and student code runs as the same user. The local transport is not a security boundary; never run it with a production secret.
- The local transport calls `handler(event, None)`. With no Lambda context there is **no time-budget guard**. Each test still has its 10 s limit, but nothing caps the run as a whole. A test set that takes longer than the 150 s lease (for example, 15 or more tests that each run close to 10 s) can lose its lease mid-run. The sweep can then requeue the job while the first run is still going. Only one run can complete it, because the old token gets 409 `stale`, but the work is done twice and the attempt count goes up.
- It emulates SQS redelivery: a delivery the handler reports as failed is retried after 2 s and then 5 s (3 deliveries at most). Anything still unfinished comes back through `/fail/` (job goes back to `pending`) or the sweep.
- The between-run scrub (temp dir wipe and killing leftover processes) is **off** locally. It only turns on when `AWS_LAMBDA_FUNCTION_NAME` is set or `CODEMAS_EXEC_SCRUB=1`, and only on Linux. **Never set either on your own machine:** the scrub empties the temp dir and kills every same-user process started after the grader.
- Student code runs on your machine under rlimits, with an empty environment, in its own process group. That is fine for development, but it is not the Lambda microVM boundary.

### Check it works

Submit a Python answer in the UI, then:

```bash
venv/bin/python manage.py dbshell
```
```sql
select id, status, attempt, published_at, started_at, finished_at
from jobs_job order by created_at desc limit 10;
```

You should see a `succeeded` row with `attempt = 1`. Django admin shows the same rows at `http://localhost:8000/admin/jobs/job/` (read-only, filter by status).

---

## 2. Settings

| Setting | Default | Used by | What it does |
|---|---|---|---|
| `JOB_TRANSPORT` | `local` | relay | `local` runs the handler in a thread pool inside the relay. `sqs` sends job ids to the queue. Anything else raises `ImproperlyConfigured`: there is no silent fallback, so a typo never starts running student code on the web host. |
| `PIPELINE_LANGUAGES` | `python,javascript` | web (create view) | Comma-separated languages that go through the job pipeline. Every other language uses the legacy Celery task. Empty (`""`) sends every language to Celery. |
| `JOB_SIGNING_SECRET` | `dev-only-change-me` | web, relay | Key for the per-job tokens that authenticate `/internal/jobs/claim/`, `/complete/` and `/fail/`. Web and relay must hold the same value; **the executor (Lambda) never has it**. **Set a real secret anywhere public.** With `DEBUG` off (`JOB_SIGNING_SECRET_REQUIRED`), an empty, default or shorter-than-32-character secret fails system check `jobs.E001`, which stops `migrate` and `run_relay`, and the internal API answers 503. Locally (`DEBUG=True`) the default is fine. |
| `CODEMAS_API_URL` | `http://127.0.0.1:8000` | relay (local), Lambda | Where the handler calls back to Django. On Lambda this is the public URL of the web service. |
| `JOB_QUEUE_URL` | empty | relay (sqs) | URL of the `codemas-exec` queue. `JOB_TRANSPORT=sqs` refuses to start without it. |
| `AWS_REGION` | `ap-southeast-1` | relay (sqs) | Region for the SQS client. |
| `RELAY_INTERVAL_S` | `0.5` | relay | Sleep between relay ticks. |
| `JOB_LEASE_SECONDS` | `150` | web (claim) | How long a claim's lease lasts. On Lambda it outlives the 90 s function timeout, so a live handler never loses its lease mid-run. Locally there is no such cap (see §1): a long test set can outlive the lease. |
| `LAMBDA_EXEC_DIR` | `<repo>/lambda/exec` | relay (local) | Where the local transport loads `handler.py` from. |

Fixed in code, not settings:

| Value | Where | Meaning |
|---|---|---|
| `MAX_ATTEMPTS = 3` | `jobs/models.py` | Claims per job. The claim after the third marks the job `dead` and the submission `error`. |
| Limits `timeout_s 10`, `python_memory_mb 256`, `node_heap_mb 192`, `output_kb 64` | `jobs/execute.py` | Sent to the handler with every claim. |
| Sweep every 60 s | `run_relay.py` | Local: requeue expired leases and jobs `queued` over 10 min. SQS: see the runbook's failure section. |
| Per-job token | `jobs/signing.py` | Claim, complete and fail must carry `token = HMAC-SHA256(JOB_SIGNING_SECRET, "job:" + job_id)`, else 401. Complete and fail also need the current `lease_token`. A token works only for its own job. |
| `/complete/` body ≤ 2,000,000 bytes | `lambda/exec/handler.py` | UTF-8 JSON (`ensure_ascii=False`). If larger, every test's output and error are halved (with `[output truncated]`) until it fits, so Django's 2.5 MB `DATA_UPLOAD_MAX_MEMORY_SIZE` never turns a student's output into a 400 and a dead job. Every output is trimmed alike: the handler never sees expected outputs, so a correct output is lost only when the whole body is over ~2 MB (about 30+ tests near the 64 KB cap). |

There is no `backend/.env.example` in the repo, so these defaults are the reference.

---

## 3. Executor tests (`lambda/exec`)

The handler and sandbox use only the standard library, so the tests need no install.

**On the Mac** (from the repo root):

```bash
python3 -m unittest discover -s lambda/exec/tests
```

Expect `Ran 82 tests … OK (skipped=16)`. The 16 skips are Linux-only checks: memory and file-size rlimits, Python and JavaScript fork bombs, the parent-environ check (`prctl`), the scrub tests, the seccomp egress filter and `/proc`.

**In Docker (Linux, nothing skipped):**

```bash
cd lambda/exec
docker build -f Dockerfile.test -t codemas-exec-test .
docker run --rm codemas-exec-test
```

Expect `Ran 82 tests … OK (skipped=1)`; the one skip is the macOS-only self-check test. The image is Python 3.12 on Debian bookworm with `nodejs`, running as a non-root user with `CODEMAS_EXEC_SCRUB=1`, so the scrub tests run.

**Backend side** (claim/complete/fail, relay, sweep, transports, and an end-to-end run through the local transport):

```bash
cd backend
venv/bin/python manage.py test jobs
```

Expect `Ran 91 tests … OK`. The handler's JSON log lines print during the run; that is expected.

---

## 4. Flip a language back to Celery

`PIPELINE_LANGUAGES` decides, per submission, which path it takes. It is read when Django starts.

```bash
# only Python on the pipeline; JavaScript goes back to Celery
PIPELINE_LANGUAGES=python venv/bin/python manage.py runserver

# everything on Celery (full rollback, no code change)
PIPELINE_LANGUAGES= venv/bin/python manage.py runserver
```

- Set it on the **web** process. The relay doesn't read it.
- **In production**, roll back with `railway variable set "PIPELINE_LANGUAGES=" -s backend --skip-deploys && railway up -s backend --detach`. Set it empty, never delete it: unset, it defaults to `python,javascript`.
- Restart the web process after changing it.
- It affects new submissions only. Jobs already in the outbox finish on the pipeline, so keep the relay running until `select count(*) from jobs_job where status in ('pending','queued','running');` is 0.
- A Celery worker must be running for any language not in the list. The legacy task executes with `run_local` in `execution/tasks.py`, a development-only subprocess executor, not the Lambda sandbox.
- The browser doesn't care which path ran: it polls `/status/` either way. A legacy submission's status response has `"job": null`.

---

## 5. SQS and Lambda (live since 2026-10-05)

Only the relay changes. The web service keeps `JOB_SIGNING_SECRET` (the relay needs the same value to mint job tokens) and `PIPELINE_LANGUAGES`.

| Relay variable | Value |
|---|---|
| `JOB_TRANSPORT` | `sqs` |
| `JOB_QUEUE_URL` | the `codemas-exec` queue URL |
| `AWS_REGION` | `ap-southeast-1` |
| AWS credentials | an identity that may send to `codemas-exec` |
| `JOB_SIGNING_SECRET` | the same value as web |

The AWS side (CloudFormation stack `codemas-pipeline`): queue `codemas-exec` with dead-letter queue `codemas-exec-dlq` (`maxReceiveCount` 3, visibility timeout 540 s), and function `codemas-exec` (Python 3.12 zip plus the `codemas-node22` Node 22 layer, arm64 (Graviton), 90 s timeout) whose environment holds only `CODEMAS_API_URL` (no secret). The event-source mapping must report partial batch failures, because the handler returns `batchItemFailures`.

The SQS client uses short timeouts (connect 3 s, read 5 s, 3 attempts) because the relay holds its row locks while publishing. It sends 10 messages per `send_message_batch` call.

---

## 6. Troubleshooting

| Symptom | Look at | Likely cause |
|---|---|---|
| Tracker stays on "Waiting in line" | `jobs_job` row is `pending` | Relay not running. Start it; the job publishes on the next tick. |
| Job `pending`, `last_error` starts `publish failed:` | relay output | Transport refused it (SQS unreachable, bad `JOB_QUEUE_URL`, credentials). It retries every tick. |
| Relay exits with `JOB_TRANSPORT must be 'local' or 'sqs'` | env | Typo in `JOB_TRANSPORT`. |
| Handler logs `"claim": 401` | relay output | The job token was refused: `JOB_SIGNING_SECRET` differs between web and relay (or was rotated while the message was queued). |
| Handler logs a connection error | relay output | `runserver` not running, or not at `CODEMAS_API_URL`. |
| Tracker shows "Retrying…" | `jobs_job.attempt`, `last_error` | The previous attempt hit an infrastructure problem and the job was released or requeued. It doesn't use a student attempt. |
| Job `dead`, submission `error` | `last_error` | Three claims without a result. The student gets the attempt back. |
| C++/Java submission never finishes | Celery worker output | Celery worker not running. |

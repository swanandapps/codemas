# Job Pipeline (phase 1: submission execution) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grade Python and JavaScript submissions through a Postgres outbox, a relay, one SQS queue and one Lambda function (`codemas-exec`), with the browser polling for the result; runnable locally without AWS, and on Railway plus AWS by configuration.

**Architecture:** Creating a submission writes a `Job` row (the outbox) in the same transaction. A relay process publishes pending jobs through a transport: `local` (calls the Lambda handler in-process) or `sqs` (boto3 → SQS → Lambda). The Lambda handler claims the job from Django over signed HTTPS, runs each test in a resource-limited child process, and completes the job with per-test output; Django records results only if the lease token still owns the job. The frontend polls a status endpoint.

**Tech Stack:** Django 5.2 + DRF (Python 3.10, `backend/venv`), PostgreSQL, Vue 3 + TS (Vite), Lambda Python 3.12 with a Node.js 20 layer (standard library only), boto3 (relay only), AWS CloudFormation + AWS CLI.

**Spec:** `docs/superpowers/specs/2026-10-03-job-pipeline-design.md` (read it before any task).

## Global Constraints

- Never run git commands that change the working tree or index (no `stash`, `checkout`, `restore`, `reset`, `clean`, `pull`, `commit`). Other agents and the user share this checkout. Commits happen only when the coordinator says the user approved them.
- Backend tests: `cd backend && venv/bin/python manage.py test <app>`; the full suite must stay green (233 tests at the start of this plan).
- Frontend checks: `cd frontend && npx vue-tsc --build 2>&1 | grep -c "error TS"` must stay at **44** (pre-existing); `npm run build-only` must pass.
- Lambda code in `lambda/exec/` uses the Python **standard library only** (no pip packages, no Django imports).
- Product screens never name internal technology (no "Django", "SQS", "Lambda", "Postgres", "Celery" in UI copy). Tracker stages stay: Submit, Queue, Execute, Grade, Feedback.
- Frontend follows the existing light theme tokens in `frontend/src/assets/theme.css` and helpers in `frontend/src/utils/format.ts`.
- Pipeline languages come from setting `PIPELINE_LANGUAGES` (default `python,javascript`); every other language keeps the legacy Celery path unchanged.
- Limits (exact values): per-test wall-clock timeout 10 s; Python child `RLIMIT_AS` 256 MB; Node child heap `--max-old-space-size=192` (no `RLIMIT_AS` for Node); CPU 10 s; processes 32 (Linux only); file size 1 MB; output cap 64 KB per stream; Lambda function timeout 90 s; job lease 150 s; SQS visibility timeout 540 s; `maxReceiveCount` 3; `MAX_ATTEMPTS` 3; signature max age 300 s.
- Names (exact): queue `codemas-exec`, DLQ `codemas-exec-dlq`, function `codemas-exec`, layer `codemas-node20`, stack `codemas-pipeline`, region `ap-southeast-1`.
- Do not touch Railway or AWS resources unless a task says so and the coordinator confirms the user approved it.

## Review Focus

1. **Student code that reads more stdin than given** must see EOF, not hang until the timeout → sandbox closes stdin after writing the input (test in Task 4).
2. **Huge or non-UTF-8 output** (e.g. `print('x'*10**7)`, `sys.stdout.buffer.write(b'\xff')`) must be truncated to 64 KB and decoded with replacement, never crash the handler → Task 4 tests.
3. **A question with zero test cases** must not grade as passed → submission becomes `error`, results_ready true, UI says the question has no tests yet (Task 2 test + Task 6 copy).
4. **Clock skew** between Lambda and Django: a signature 299 s old is accepted, 301 s rejected, a timestamp 299 s in the future accepted (Task 2 tests).
5. **The submission row deleted while its job is queued** (trainer deletes a student): claim returns 410 `gone`, the handler acknowledges, nothing is written (Task 2 + Task 4 tests).

---

## File Structure

```
backend/jobs/                      NEW Django app: outbox, lease, internal API, relay
  __init__.py, apps.py
  models.py                        Job model (outbox row + lease)
  migrations/0001_initial.py       generated
  admin.py                         read-only Jobs list (demo: "show me the outbox")
  signing.py                       HMAC sign/verify (Django side)
  services.py                      enqueue / claim / complete / fail / sweep (state machine)
  execute.py                       execute_submission kind: payload_for(), apply_result()
  views.py                         /internal/jobs/claim|complete|fail/
  urls.py
  transports.py                    LocalTransport, SqsTransport, get_transport()
  relay.py                         tick(), sweep_stuck() used by the command
  management/commands/run_relay.py
  tests/  test_models.py test_signing.py test_api.py test_relay.py test_e2e.py
backend/submissions/
  views.py                         MODIFY: transactional create + enqueue, status view
  urls.py                          MODIFY: add <id>/status/
  models.py                        MODIFY: UniqueConstraint(student, question, attempt_number)
  migrations/000X_unique_attempt.py generated
  tests.py                         MODIFY: add create/race/status tests
backend/codemas/settings.py        MODIFY: INSTALLED_APPS += jobs; job settings
backend/codemas/urls.py            MODIFY: path('internal/jobs/', include('jobs.urls'))
backend/requirements.txt           MODIFY: + boto3
backend/execution/tasks.py         MODIFY: delete run_in_lambda and commented Docker/Lambda blocks
lambda/exec/                       NEW Lambda function source (zip root)
  handler.py                       SQS event → claim → run → complete
  sandbox.py                       child-process runner with limits
  tests/test_sandbox.py, tests/test_handler.py   (unittest, no Django)
  Dockerfile.test                  Linux test image (python:3.12-slim + nodejs)
lambda/*_runner.py                 DELETE (old synchronous runners)
frontend/src/views/ExamTakeView.vue MODIFY: poll /status/ instead of SSE; resume after refresh
deploy/aws/pipeline.yaml           NEW CloudFormation stack
deploy/aws/deploy.sh               NEW package + deploy
deploy/aws/smoke.sh                NEW end-to-end check against Railway + AWS
deploy/aws/README.md               NEW one-time IAM setup
docs/demo-runbook.md               NEW how to show each hop in a demo
docs/dev-pipeline.md               NEW how to run the pipeline locally
Codemas-SYSTEM_DESIGN.md, submission_animation.html, submission_flow.html  MODIFY (docs rule)
```

---

### Task 1: `jobs` app — the outbox model, enqueue and admin

**Files:**
- Create: `backend/jobs/__init__.py`, `backend/jobs/apps.py`, `backend/jobs/models.py`, `backend/jobs/admin.py`, `backend/jobs/services.py` (enqueue only in this task), `backend/jobs/tests/__init__.py`, `backend/jobs/tests/test_models.py`
- Modify: `backend/codemas/settings.py` (INSTALLED_APPS, job settings)

**Interfaces:**
- Produces: `jobs.models.Job` with fields `id` (UUID pk), `kind`, `subject_id`, `status`, `attempt`, `lease_token`, `lease_expires_at`, `published_at`, `started_at`, `finished_at`, `last_error`, `created_at`, `updated_at`; constants `Job.KIND_EXECUTE = 'execute_submission'`, `Job.ACTIVE = ('pending', 'queued', 'running')`, `Job.TERMINAL = ('succeeded', 'failed', 'dead')`, `MAX_ATTEMPTS = 3`.
- Produces: `jobs.services.enqueue(kind: str, subject_id: int) -> Job` (raises `RuntimeError` if not inside `transaction.atomic()`).
- Produces settings: `JOB_TRANSPORT` (default `'local'`), `JOB_SIGNING_SECRET` (default `'dev-only-change-me'`), `CODEMAS_API_URL` (default `'http://127.0.0.1:8000'`), `JOB_QUEUE_URL` (default `''`), `AWS_REGION` (default `'ap-southeast-1'`), `PIPELINE_LANGUAGES` (set, default `{'python','javascript'}`), `RELAY_INTERVAL_S` (default `0.5`), `JOB_LEASE_SECONDS` (default `150`), `LAMBDA_EXEC_DIR` (default `BASE_DIR.parent / 'lambda' / 'exec'`).

- [ ] **Step 1: Write the failing tests** — `backend/jobs/tests/test_models.py`

```python
from django.db import IntegrityError, transaction
from django.test import TestCase

from jobs.models import Job
from jobs.services import enqueue


class EnqueueTest(TestCase):
    def test_enqueue_creates_pending_job(self):
        with transaction.atomic():
            job = enqueue(Job.KIND_EXECUTE, 42)
        job.refresh_from_db()
        self.assertEqual(job.status, 'pending')
        self.assertEqual(job.attempt, 0)
        self.assertEqual(job.subject_id, 42)
        self.assertIsNone(job.published_at)

    def test_enqueue_outside_transaction_is_refused(self):
        # TestCase wraps each test in a transaction, so simulate "outside" by checking the guard directly
        from jobs import services
        with self.assertRaises(RuntimeError):
            services._require_atomic(in_atomic=False)

    def test_one_active_job_per_subject(self):
        with transaction.atomic():
            enqueue(Job.KIND_EXECUTE, 7)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                enqueue(Job.KIND_EXECUTE, 7)

    def test_a_new_job_is_allowed_after_the_previous_one_finished(self):
        with transaction.atomic():
            first = enqueue(Job.KIND_EXECUTE, 8)
        Job.objects.filter(pk=first.pk).update(status='succeeded')
        with transaction.atomic():
            second = enqueue(Job.KIND_EXECUTE, 8)
        self.assertNotEqual(first.pk, second.pk)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && venv/bin/python manage.py test jobs`
Expected: error `No module named 'jobs'` / app not installed.

- [ ] **Step 3: Implement**

`backend/jobs/apps.py`:
```python
from django.apps import AppConfig


class JobsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'jobs'
```

`backend/jobs/models.py`:
```python
import uuid

from django.db import models
from django.db.models import Q

MAX_ATTEMPTS = 3


class Job(models.Model):
    """One unit of background work: the transactional outbox row plus its execution lease.

    pending   committed, not yet published (the outbox)
    queued    the transport accepted it
    running   a handler holds a live lease
    succeeded / failed   terminal; failed = the job finished but produced a failure result
    dead      infrastructure failed MAX_ATTEMPTS times
    """
    KIND_EXECUTE = 'execute_submission'
    KINDS = [(KIND_EXECUTE, 'Execute submission')]
    STATUSES = [(s, s) for s in ('pending', 'queued', 'running', 'succeeded', 'failed', 'dead')]
    ACTIVE = ('pending', 'queued', 'running')
    TERMINAL = ('succeeded', 'failed', 'dead')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=40, choices=KINDS)
    subject_id = models.PositiveIntegerField()  # submission id for execute_submission
    status = models.CharField(max_length=12, choices=STATUSES, default='pending')
    attempt = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'created_at'])]
        constraints = [
            models.UniqueConstraint(
                fields=['kind', 'subject_id'],
                condition=Q(status__in=('pending', 'queued', 'running')),
                name='one_active_job_per_subject',
            ),
        ]

    def __str__(self):
        return f'{self.kind} #{self.subject_id} [{self.status}]'
```

`backend/jobs/services.py` (this task adds only enqueue; later tasks append):
```python
from django.db import transaction

from .models import Job


def _require_atomic(in_atomic=None):
    if in_atomic is None:
        in_atomic = transaction.get_connection().in_atomic_block
    if not in_atomic:
        raise RuntimeError('enqueue() must be called inside transaction.atomic() with the row it belongs to')


def enqueue(kind, subject_id):
    """Write the outbox row. Never publishes; the relay does that after commit."""
    _require_atomic()
    return Job.objects.create(kind=kind, subject_id=subject_id)
```

`backend/jobs/admin.py`:
```python
from django.contrib import admin

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """Read-only view of the outbox. This is what you open when asked "show me the outbox table"."""
    list_display = ('id', 'kind', 'subject_id', 'status', 'attempt', 'published_at', 'started_at',
                    'finished_at', 'lease_expires_at', 'created_at')
    list_filter = ('status', 'kind')
    search_fields = ('=subject_id', '=id')
    ordering = ('-created_at',)
    readonly_fields = [f.name for f in Job._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
```

`backend/codemas/settings.py`: add `"jobs",` to `INSTALLED_APPS` after `"ai",`, and append:
```python
# ── Job pipeline (outbox → relay → transport → executor) ─────────────────────
JOB_TRANSPORT = os.getenv('JOB_TRANSPORT', 'local')                 # 'local' or 'sqs'
JOB_SIGNING_SECRET = os.getenv('JOB_SIGNING_SECRET', 'dev-only-change-me')
CODEMAS_API_URL = os.getenv('CODEMAS_API_URL', 'http://127.0.0.1:8000')
JOB_QUEUE_URL = os.getenv('JOB_QUEUE_URL', '')
AWS_REGION = os.getenv('AWS_REGION', 'ap-southeast-1')
PIPELINE_LANGUAGES = {l.strip() for l in os.getenv('PIPELINE_LANGUAGES', 'python,javascript').split(',') if l.strip()}
RELAY_INTERVAL_S = float(os.getenv('RELAY_INTERVAL_S', '0.5'))
JOB_LEASE_SECONDS = int(os.getenv('JOB_LEASE_SECONDS', '150'))
LAMBDA_EXEC_DIR = Path(os.getenv('LAMBDA_EXEC_DIR', BASE_DIR.parent / 'lambda' / 'exec'))
```
(`Path` and `BASE_DIR` already exist at the top of settings.py; confirm before editing.)

- [ ] **Step 4: Generate the migration and run tests**

Run: `cd backend && venv/bin/python manage.py makemigrations jobs && venv/bin/python manage.py test jobs`
Expected: 4 tests pass.

- [ ] **Step 5: Checkpoint** — `venv/bin/python manage.py migrate jobs` on the local DB, open http://localhost:8000/admin/jobs/job/ as the trainer superuser (`admin`) and confirm the empty Jobs list renders. Full suite green.

---

### Task 2: Signing, the claim/complete/fail API and the execute_submission kind

**Files:**
- Create: `backend/jobs/signing.py`, `backend/jobs/execute.py`, `backend/jobs/views.py`, `backend/jobs/urls.py`, `backend/jobs/tests/test_signing.py`, `backend/jobs/tests/test_api.py`
- Modify: `backend/jobs/services.py` (append claim/complete/fail), `backend/codemas/urls.py`

**Interfaces:**
- Consumes: `Job`, `MAX_ATTEMPTS`, settings from Task 1.
- Produces: `jobs.signing.sign(secret: str, timestamp: str, body: bytes) -> str` returning `'sha256=<hex>'`; `jobs.signing.verify(secret, timestamp_header, signature_header, body, now=None, max_age=300) -> bool`.
- Produces endpoints (all `POST`, JSON, signed with headers `X-Timestamp` and `X-Signature`):
  - `/internal/jobs/claim/` body `{"job_id": str}` → 200 `{"job_id", "lease_token", "kind", "submission_id", "language", "code", "tests": [{"id", "input", "expected"}], "limits": {"timeout_s": 10, "python_memory_mb": 256, "node_heap_mb": 192, "output_kb": 64}}`; 409 `{"error": "done"}` (terminal); 409 `{"error": "busy"}` (live lease); 410 `{"error": "gone"}` (subject deleted; job marked `failed`); 410 `{"error": "dead"}` (attempts exhausted; job marked `dead`); 401 bad signature; 404 unknown job.
  - `/internal/jobs/complete/` body `{"job_id", "lease_token", "results": [{"test_id": int, "output": str, "error": str, "ms": int, "timed_out": bool}]}` → 200 `{"status": "succeeded", "submission_status": "passed"|"failed"|"error"}`; 409 `{"error": "stale"}`.
  - `/internal/jobs/fail/` body `{"job_id", "lease_token", "error": str}` → 200; 409 stale.
- Produces: `jobs.execute.payload_for(submission) -> dict` and `jobs.execute.apply_result(submission, results: list[dict]) -> str` (returns the submission status).

- [ ] **Step 1: Write the failing signing tests** — `backend/jobs/tests/test_signing.py`

```python
import time

from django.test import SimpleTestCase

from jobs.signing import sign, verify

SECRET = 's3cret'
BODY = b'{"job_id": "abc"}'


class SigningTest(SimpleTestCase):
    def test_round_trip(self):
        ts = str(int(time.time()))
        self.assertTrue(verify(SECRET, ts, sign(SECRET, ts, BODY), BODY))

    def test_wrong_secret_or_body_fails(self):
        ts = str(int(time.time()))
        sig = sign(SECRET, ts, BODY)
        self.assertFalse(verify('other', ts, sig, BODY))
        self.assertFalse(verify(SECRET, ts, sig, b'{"job_id": "xyz"}'))

    def test_age_window_is_300_seconds_both_ways(self):
        now = 1_800_000_000
        for offset, ok in ((-299, True), (-301, False), (299, True), (301, False)):
            ts = str(now + offset)
            self.assertEqual(verify(SECRET, ts, sign(SECRET, ts, BODY), BODY, now=now), ok, offset)

    def test_missing_or_garbage_headers_fail(self):
        self.assertFalse(verify(SECRET, None, None, BODY))
        self.assertFalse(verify(SECRET, 'not-a-number', 'sha256=00', BODY))

    def test_matches_the_lambda_implementation(self):
        import importlib.util
        from django.conf import settings
        spec = importlib.util.spec_from_file_location('lambda_handler', settings.LAMBDA_EXEC_DIR / 'handler.py')
        if spec is None:
            self.skipTest('lambda/exec/handler.py not written yet (Task 4)')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.sign(SECRET, '1800000000', BODY), sign(SECRET, '1800000000', BODY))
```

- [ ] **Step 2: Implement `backend/jobs/signing.py`**

```python
import hashlib
import hmac
import time


def sign(secret, timestamp, body):
    """HMAC-SHA256 over "<timestamp>.<body>". The Lambda handler has an identical copy."""
    msg = timestamp.encode() + b'.' + body
    return 'sha256=' + hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def verify(secret, timestamp_header, signature_header, body, now=None, max_age=300):
    if not timestamp_header or not signature_header:
        return False
    try:
        ts = int(timestamp_header)
    except (TypeError, ValueError):
        return False
    now = int(time.time()) if now is None else now
    if abs(now - ts) > max_age:
        return False
    return hmac.compare_digest(sign(secret, timestamp_header, body), signature_header)
```

Run: `venv/bin/python manage.py test jobs.tests.test_signing` → 4 pass, 1 skipped.

- [ ] **Step 3: Write the failing API tests** — `backend/jobs/tests/test_api.py`

```python
import json
import time
import uuid
from datetime import timedelta

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from exams.models import Exam, Question, TestCase as QTest
from jobs.models import Job
from jobs.services import enqueue
from jobs.signing import sign
from results.models import Result
from submissions.models import Submission

SECRET = 'test-secret'


@override_settings(JOB_SIGNING_SECRET=SECRET)
class InternalApiTest(TestCase):
    def setUp(self):
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.student = User.objects.create_user(username='s', password='pw', role='student', cohort='C')
        exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60, is_active=True,
                                   start_time=timezone.now() - timedelta(hours=1),
                                   end_time=timezone.now() + timedelta(hours=1))
        self.q = Question.objects.create(exam=exam, title='Q', description='d', difficulty='easy')
        self.t1 = QTest.objects.create(question=self.q, input_data='1', expected_output='2')
        self.t2 = QTest.objects.create(question=self.q, input_data='2', expected_output='3')
        self.sub = Submission.objects.create(student=self.student, exam=exam, question=self.q,
                                             code='print(int(input())+1)', language='python', attempt_number=1)
        with transaction.atomic():
            self.job = enqueue(Job.KIND_EXECUTE, self.sub.id)
        Job.objects.filter(pk=self.job.pk).update(status='queued')

    def post(self, path, payload, secret=SECRET, ts=None):
        body = json.dumps(payload).encode()
        ts = ts or str(int(time.time()))
        return self.client.post(path, data=body, content_type='application/json',
                                HTTP_X_TIMESTAMP=ts, HTTP_X_SIGNATURE=sign(secret, ts, body))

    def claim(self):
        return self.post('/internal/jobs/claim/', {'job_id': str(self.job.id)})

    def complete(self, token, outputs):
        results = [{'test_id': tid, 'output': out, 'error': '', 'ms': 5, 'timed_out': False}
                   for tid, out in outputs]
        return self.post('/internal/jobs/complete/', {'job_id': str(self.job.id), 'lease_token': token,
                                                       'results': results})

    # ── claim ──
    def test_claim_returns_code_and_tests_and_leases_the_job(self):
        r = self.claim()
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['code'], 'print(int(input())+1)')
        self.assertEqual([t['id'] for t in data['tests']], [self.t1.id, self.t2.id])
        self.assertEqual(data['tests'][0], {'id': self.t1.id, 'input': '1', 'expected': '2'})
        self.assertEqual(data['limits']['timeout_s'], 10)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'running')
        self.assertEqual(self.job.attempt, 1)
        self.assertEqual(str(self.job.lease_token), data['lease_token'])
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, 'running')

    def test_second_claim_while_leased_is_busy(self):
        self.claim()
        self.assertEqual(self.claim().json(), {'error': 'busy'})

    def test_claim_after_lease_expiry_gets_a_new_token(self):
        first = self.claim().json()['lease_token']
        Job.objects.filter(pk=self.job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        second = self.claim().json()['lease_token']
        self.assertNotEqual(first, second)

    def test_claim_on_terminal_job_is_done(self):
        Job.objects.filter(pk=self.job.pk).update(status='succeeded')
        r = self.claim()
        self.assertEqual((r.status_code, r.json()), (409, {'error': 'done'}))

    def test_claim_past_max_attempts_marks_dead(self):
        Job.objects.filter(pk=self.job.pk).update(attempt=3)
        r = self.claim()
        self.assertEqual((r.status_code, r.json()), (410, {'error': 'dead'}))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'dead')
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, 'error')

    def test_claim_for_deleted_submission_is_gone(self):
        self.sub.delete()
        r = self.claim()
        self.assertEqual((r.status_code, r.json()), (410, {'error': 'gone'}))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'failed')

    def test_bad_signature_is_401(self):
        r = self.post('/internal/jobs/claim/', {'job_id': str(self.job.id)}, secret='wrong')
        self.assertEqual(r.status_code, 401)

    def test_unknown_job_is_404(self):
        r = self.post('/internal/jobs/claim/', {'job_id': str(uuid.uuid4())})
        self.assertEqual(r.status_code, 404)

    # ── complete ──
    def test_complete_records_results_and_status(self):
        token = self.claim().json()['lease_token']
        r = self.complete(token, [(self.t1.id, '2\n'), (self.t2.id, '4')])
        self.assertEqual(r.json(), {'status': 'succeeded', 'submission_status': 'failed'})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, 'failed')
        self.assertEqual(self.sub.execution_time_ms, 10)
        passed = dict(Result.objects.filter(submission=self.sub).values_list('test_case_id', 'passed'))
        self.assertEqual(passed, {self.t1.id: True, self.t2.id: False})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'succeeded')
        self.assertIsNotNone(self.job.finished_at)

    def test_complete_with_stale_token_writes_nothing(self):
        self.claim()
        r = self.complete(str(uuid.uuid4()), [(self.t1.id, '2'), (self.t2.id, '3')])
        self.assertEqual((r.status_code, r.json()), (409, {'error': 'stale'}))
        self.assertEqual(Result.objects.filter(submission=self.sub).count(), 0)

    def test_second_complete_is_a_no_op(self):
        token = self.claim().json()['lease_token']
        self.complete(token, [(self.t1.id, '2'), (self.t2.id, '3')])
        r = self.complete(token, [(self.t1.id, 'x'), (self.t2.id, 'y')])
        self.assertEqual(r.status_code, 409)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, 'passed')

    def test_question_without_tests_is_an_error_not_a_pass(self):
        QTest.objects.filter(question=self.q).delete()
        token = self.claim().json()['lease_token']
        r = self.complete(token, [])
        self.assertEqual(r.json()['submission_status'], 'error')

    # ── fail ──
    def test_fail_releases_the_lease_for_an_immediate_retry(self):
        token = self.claim().json()['lease_token']
        self.post('/internal/jobs/fail/', {'job_id': str(self.job.id), 'lease_token': token, 'error': 'boom'})
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.last_error), ('queued', 'boom'))
        self.assertEqual(self.claim().status_code, 200)
```

Run: `venv/bin/python manage.py test jobs.tests.test_api` → errors (no URLs).

- [ ] **Step 4: Implement `backend/jobs/execute.py`**

```python
"""The execute_submission job kind: what a claim hands over and how a completion is recorded."""
from django.db import transaction

from results.models import Result
from submissions.models import Submission

LIMITS = {'timeout_s': 10, 'python_memory_mb': 256, 'node_heap_mb': 192, 'output_kb': 64}


def payload_for(submission):
    tests = list(submission.question.test_cases.order_by('id').values('id', 'input_data', 'expected_output'))
    return {
        'submission_id': submission.id,
        'language': submission.language,
        'code': submission.code,
        'tests': [{'id': t['id'], 'input': t['input_data'], 'expected': t['expected_output']} for t in tests],
        'limits': LIMITS,
    }


def apply_result(submission, results):
    """Write Result rows and the submission status. Same pass rule as the legacy executor:
    output.strip() == expected.strip(). Returns the new submission status."""
    expected = dict(submission.question.test_cases.values_list('id', 'expected_output'))
    if not expected:
        submission.status = 'error'
        submission.save(update_fields=['status'])
        return submission.status

    all_passed, total_ms = True, 0
    for r in results:
        if r['test_id'] not in expected:
            continue
        passed = (r.get('output') or '').strip() == expected[r['test_id']].strip()
        all_passed = all_passed and passed
        total_ms += int(r.get('ms') or 0)
        Result.objects.update_or_create(
            submission=submission, test_case_id=r['test_id'],
            defaults={'passed': passed, 'actual_output': r.get('output') or '',
                      'execution_time_ms': int(r.get('ms') or 0), 'error_message': r.get('error') or ''},
        )
    missing = set(expected) - {r['test_id'] for r in results}
    submission.status = 'passed' if all_passed and not missing else 'failed'
    submission.execution_time_ms = total_ms
    submission.save(update_fields=['status', 'execution_time_ms'])
    transaction.on_commit(lambda: after_grading(submission.id))
    return submission.status


def after_grading(submission_id):
    """Same side effects the legacy Celery task runs after grading."""
    from codemas.notifications import notify_result_ready
    from plagiarism.tasks import normalize_code
    sub = Submission.objects.select_related('student', 'question').get(pk=submission_id)
    sub.normalized_code = normalize_code(sub.code, sub.language)
    sub.save(update_fields=['normalized_code'])
    notify_result_ready(sub)
    try:
        from ai.tasks import score_rubric, generate_hint
        score_rubric.delay(sub.id)
        if sub.status == 'failed':
            generate_hint.delay(sub.id)
    except Exception as e:  # AI feedback is best-effort and must never affect grading
        print(f'[JOBS] could not queue AI feedback for submission {sub.id}: {e}')
```

Check `backend/execution/tasks.py` `execute_submission` for the exact side effects before writing `after_grading` and mirror them (normalize, notify, rubric, hint). If they differ from the code above, follow the existing task.

- [ ] **Step 5: Append claim/complete/fail to `backend/jobs/services.py`**

```python
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import MAX_ATTEMPTS


class JobDone(Exception): pass
class JobBusy(Exception): pass
class JobGone(Exception): pass
class JobDead(Exception): pass
class StaleLease(Exception): pass


def _subject(job):
    from submissions.models import Submission
    return Submission.objects.select_related('question').filter(pk=job.subject_id).first()


@transaction.atomic
def claim(job_id):
    """Take the lease. One locked read decides every outcome, so two claims can't both win."""
    job = Job.objects.select_for_update().get(pk=job_id)  # DoesNotExist → 404 in the view
    now = timezone.now()
    if job.status in Job.TERMINAL:
        raise JobDone
    if job.status == 'running' and job.lease_expires_at and job.lease_expires_at > now:
        raise JobBusy
    subject = _subject(job)
    if subject is None:
        job.status, job.finished_at, job.last_error = 'failed', now, 'subject deleted'
        job.save()
        raise JobGone
    if job.attempt >= MAX_ATTEMPTS:
        job.status, job.finished_at = 'dead', now
        job.save()
        subject.status = 'error'
        subject.save(update_fields=['status'])
        raise JobDead
    job.status = 'running'
    job.attempt += 1
    job.lease_token = uuid.uuid4()
    job.lease_expires_at = now + timedelta(seconds=settings.JOB_LEASE_SECONDS)
    job.started_at = job.started_at or now
    job.save()
    subject.status = 'running'
    subject.save(update_fields=['status'])
    return job, subject


@transaction.atomic
def complete(job_id, lease_token, results):
    from .execute import apply_result
    job = Job.objects.select_for_update().get(pk=job_id)
    if job.status != 'running' or str(job.lease_token) != str(lease_token):
        raise StaleLease
    subject = _subject(job)
    submission_status = apply_result(subject, results) if subject else 'gone'
    job.status, job.finished_at, job.lease_token, job.lease_expires_at = 'succeeded', timezone.now(), None, None
    job.save()
    return job, submission_status


@transaction.atomic
def fail(job_id, lease_token, error):
    job = Job.objects.select_for_update().get(pk=job_id)
    if job.status != 'running' or str(job.lease_token) != str(lease_token):
        raise StaleLease
    job.status, job.lease_token, job.lease_expires_at = 'queued', None, None
    job.last_error = (error or '')[:2000]
    job.save()
    return job
```

- [ ] **Step 6: Implement `backend/jobs/views.py` and `backend/jobs/urls.py`; mount under `/internal/jobs/`**

```python
import json

from django.conf import settings
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from . import services
from .execute import payload_for
from .models import Job
from .signing import verify


@method_decorator(csrf_exempt, name='dispatch')
class SignedView(View):
    """Internal endpoints for the executor. Authenticated only by the HMAC signature."""

    def post(self, request):
        if not verify(settings.JOB_SIGNING_SECRET, request.headers.get('X-Timestamp'),
                      request.headers.get('X-Signature'), request.body):
            return JsonResponse({'error': 'bad signature'}, status=401)
        try:
            data = json.loads(request.body or b'{}')
            return self.handle(data)
        except Job.DoesNotExist:
            return JsonResponse({'error': 'unknown job'}, status=404)
        except (ValueError, KeyError) as e:
            return JsonResponse({'error': f'bad request: {e}'}, status=400)


class ClaimView(SignedView):
    def handle(self, data):
        try:
            job, submission = services.claim(data['job_id'])
        except services.JobDone:
            return JsonResponse({'error': 'done'}, status=409)
        except services.JobBusy:
            return JsonResponse({'error': 'busy'}, status=409)
        except services.JobGone:
            return JsonResponse({'error': 'gone'}, status=410)
        except services.JobDead:
            return JsonResponse({'error': 'dead'}, status=410)
        return JsonResponse({'job_id': str(job.id), 'lease_token': str(job.lease_token), 'kind': job.kind,
                             **payload_for(submission)})


class CompleteView(SignedView):
    def handle(self, data):
        try:
            job, submission_status = services.complete(data['job_id'], data['lease_token'], data.get('results', []))
        except services.StaleLease:
            return JsonResponse({'error': 'stale'}, status=409)
        return JsonResponse({'status': job.status, 'submission_status': submission_status})


class FailView(SignedView):
    def handle(self, data):
        try:
            services.fail(data['job_id'], data['lease_token'], data.get('error', ''))
        except services.StaleLease:
            return JsonResponse({'error': 'stale'}, status=409)
        return JsonResponse({'status': 'released'})
```

`backend/jobs/urls.py`:
```python
from django.urls import path

from .views import ClaimView, CompleteView, FailView

urlpatterns = [
    path('claim/', ClaimView.as_view()),
    path('complete/', CompleteView.as_view()),
    path('fail/', FailView.as_view()),
]
```

`backend/codemas/urls.py`: add `path('internal/jobs/', include('jobs.urls')),` to `urlpatterns`.

- [ ] **Step 7: Run the tests**

Run: `venv/bin/python manage.py test jobs` → all pass (signing Lambda-compat test still skipped).

- [ ] **Step 8: Checkpoint** — full backend suite green.

---

### Task 3: Transactional submission create, attempt lock, status endpoint

**Files:**
- Modify: `backend/submissions/views.py` (SubmissionCreateView; add SubmissionStatusView), `backend/submissions/urls.py`, `backend/submissions/models.py` (constraint), `backend/submissions/tests.py`
- Create: migration via `makemigrations submissions`

**Interfaces:**
- Consumes: `jobs.services.enqueue`, `Job`, settings `PIPELINE_LANGUAGES`.
- Produces: `GET /api/submissions/<id>/status/` → `{"id", "status", "results_ready": bool, "job": null | {"status", "attempt", "queued_at", "started_at", "finished_at"}}` (owner or trainer only; 403 otherwise).
- Produces: attempt numbering = `max(attempt_number) + 1`; the attempt-limit count excludes submissions whose job is `dead`.

- [ ] **Step 1: Check existing data can take the constraint**

Run in a shell:
```bash
cd backend && venv/bin/python manage.py shell -c "from django.db.models import Count; from submissions.models import Submission as S; print(S.objects.values('student','question','attempt_number').annotate(n=Count('id')).filter(n__gt=1).count())"
```
Expected: `0`. If not 0, stop and report to the coordinator (the seed would need a fix first).

- [ ] **Step 2: Write the failing tests** — append to `backend/submissions/tests.py` (keep existing tests)

```python
import threading
from datetime import timedelta

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, Question, TestCase as QTest
from jobs.models import Job
from submissions.models import Submission


def make_world():
    trainer = User.objects.create_user(username='tr', password='pw', role='trainer')
    student = User.objects.create_user(username='st', password='pw', role='student', cohort='C')
    exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60, is_active=True,
                               start_time=timezone.now() - timedelta(hours=1), end_time=timezone.now() + timedelta(hours=1))
    q = Question.objects.create(exam=exam, title='Q', description='d', difficulty='easy')
    QTest.objects.create(question=q, input_data='1', expected_output='2')
    return trainer, student, q


@override_settings(PIPELINE_LANGUAGES={'python', 'javascript'})
class PipelineCreateTest(TestCase):
    def setUp(self):
        self.trainer, self.student, self.q = make_world()
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def submit(self, language='python'):
        return self.api.post('/api/submissions/create/', {'question': self.q.id, 'code': 'print(2)', 'language': language},
                             format='json')

    def test_python_submission_writes_an_outbox_job_in_the_same_transaction(self):
        r = self.submit()
        self.assertEqual(r.status_code, 201)
        job = Job.objects.get(subject_id=r.data['id'])
        self.assertEqual((job.kind, job.status), (Job.KIND_EXECUTE, 'pending'))

    def test_non_pipeline_language_uses_the_legacy_path_and_no_job(self):
        from unittest import mock
        with mock.patch('submissions.views.execute_submission') as legacy:
            with self.captureOnCommitCallbacks(execute=True):
                r = self.submit(language='cpp')
        self.assertFalse(Job.objects.filter(subject_id=r.data['id']).exists())
        legacy.delay.assert_called_once_with(r.data['id'])

    def test_status_endpoint_reports_job_progress(self):
        sid = self.submit().data['id']
        data = self.api.get(f'/api/submissions/{sid}/status/').data
        self.assertEqual(data['status'], 'pending')
        self.assertEqual(data['job']['status'], 'pending')
        self.assertFalse(data['results_ready'])

    def test_status_endpoint_is_private(self):
        sid = self.submit().data['id']
        other = User.objects.create_user(username='o', password='pw', role='student', cohort='C')
        api = APIClient(); api.force_authenticate(other)
        self.assertEqual(api.get(f'/api/submissions/{sid}/status/').status_code, 403)

    def test_dead_job_does_not_use_up_an_attempt(self):
        sid = self.submit().data['id']
        Job.objects.filter(subject_id=sid).update(status='dead')
        Submission.objects.filter(pk=sid).update(status='error')
        self.submit(); self.submit()
        r = self.submit()   # 4 submissions, but the dead one is not counted against max_attempts=3
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['attempt_number'], 4)


@override_settings(PIPELINE_LANGUAGES={'python'})
class AttemptRaceTest(TransactionTestCase):
    def test_two_concurrent_submits_for_the_last_attempt_only_one_wins(self):
        _, student, q = make_world()
        for n in (1, 2):
            Submission.objects.create(student=student, exam=q.exam, question=q, code='x', language='python', attempt_number=n)
        codes = []

        def go():
            api = APIClient(); api.force_authenticate(student)
            codes.append(api.post('/api/submissions/create/', {'question': q.id, 'code': 'print(2)', 'language': 'python'},
                                  format='json').status_code)
            connection.close()

        threads = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(sorted(codes), [201, 403])
```

Note: `max_attempts` comes from `PlagiarismPolicy.get().max_attempts` (default 3); confirm in `plagiarism/models.py`. The submission serializer must expose `id`, `status` and `attempt_number` in the create response (check `SubmissionSerializer`).

Run: `venv/bin/python manage.py test submissions` → new tests fail.

- [ ] **Step 3: Implement**

In `backend/submissions/models.py` `Submission.Meta`, add:
```python
        constraints = [
            models.UniqueConstraint(fields=['student', 'question', 'attempt_number'], name='unique_attempt_per_question'),
        ]
```
Run `venv/bin/python manage.py makemigrations submissions`.

Replace the body of `SubmissionCreateView.post` from the `max_attempts = ...` line to the `return` with:
```python
        from django.conf import settings
        from django.db import IntegrityError, transaction
        from django.db.models import Max
        from accounts.models import User
        from jobs.models import Job
        from jobs.services import enqueue

        max_attempts = PlagiarismPolicy.get().max_attempts
        try:
            with transaction.atomic():
                # Lock this student's row so concurrent submits for the same student queue up here
                User.objects.select_for_update().get(pk=request.user.pk)
                mine = Submission.objects.filter(student=request.user, question=question)
                dead_ids = Job.objects.filter(kind=Job.KIND_EXECUTE, status='dead').values('subject_id')
                if mine.exclude(id__in=dead_ids).count() >= max_attempts:
                    return Response({'error': 'Max attempts reached'}, status=status.HTTP_403_FORBIDDEN)
                attempt_number = (mine.aggregate(m=Max('attempt_number'))['m'] or 0) + 1
                submission = serializer.save(student=request.user, exam=question.exam,
                                             attempt_number=attempt_number, ip_address=request.META.get('REMOTE_ADDR'))
                if submission.language in settings.PIPELINE_LANGUAGES:
                    enqueue(Job.KIND_EXECUTE, submission.id)
                else:
                    transaction.on_commit(lambda: execute_submission.delay(submission.id))
        except IntegrityError:
            return Response({'error': 'Another submission for this question is being saved. Try again.'},
                            status=status.HTTP_409_CONFLICT)
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)
```

Add to `backend/submissions/views.py`:
```python
class SubmissionStatusView(APIView):
    """Lightweight status for polling: the submission's state and its job's progress."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from jobs.models import Job
        sub = Submission.objects.filter(pk=pk).first()
        if not sub:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role != 'trainer' and sub.student_id != request.user.id:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        job = Job.objects.filter(kind=Job.KIND_EXECUTE, subject_id=sub.id).order_by('-created_at').first()
        return Response({
            'id': sub.id,
            'status': sub.status,
            'results_ready': sub.status in ('passed', 'failed', 'error'),
            'job': None if job is None else {
                'status': job.status, 'attempt': job.attempt, 'queued_at': job.published_at,
                'started_at': job.started_at, 'finished_at': job.finished_at,
            },
        })
```
and in `backend/submissions/urls.py` add `path('<int:pk>/status/', SubmissionStatusView.as_view()),` (import it).

- [ ] **Step 4: Run tests** — `venv/bin/python manage.py test submissions jobs` → pass. Full suite green.

- [ ] **Step 5: Checkpoint** — apply migrations locally (`manage.py migrate`).

---

### Task 4: The Lambda function — sandbox and handler (stdlib only)

**Files:**
- Create: `lambda/exec/handler.py`, `lambda/exec/sandbox.py`, `lambda/exec/tests/__init__.py`, `lambda/exec/tests/test_sandbox.py`, `lambda/exec/tests/test_handler.py`, `lambda/exec/Dockerfile.test`
- Delete: `lambda/cpp_runner.py`, `lambda/java_runner.py`, `lambda/javascript_runner.py`, `lambda/python_runner.py`

**Interfaces:**
- Consumes: the claim/complete/fail contract from Task 2 (exact JSON shapes there).
- Produces: `handler.handler(event, context) -> {"batchItemFailures": [{"itemIdentifier": messageId}, ...]}` (SQS partial batch response); `handler.sign(secret, timestamp, body) -> str` identical to `jobs.signing.sign`; `sandbox.run(language: str, code: str, stdin: str, limits: dict) -> dict` returning `{"output": str, "error": str, "ms": int, "timed_out": bool}`.
- Environment: `CODEMAS_API_URL`, `JOB_SIGNING_SECRET`.

- [ ] **Step 1: Write the failing sandbox tests** — `lambda/exec/tests/test_sandbox.py`

```python
import shutil
import sys
import unittest

sys.path.insert(0, __file__.rsplit('/tests/', 1)[0])
import sandbox  # noqa: E402

LIMITS = {'timeout_s': 3, 'python_memory_mb': 256, 'node_heap_mb': 192, 'output_kb': 64}
LINUX = sys.platform.startswith('linux')
HAS_NODE = shutil.which('node') is not None


class PythonSandboxTest(unittest.TestCase):
    def run_py(self, code, stdin=''):
        return sandbox.run('python', code, stdin, LIMITS)

    def test_reads_stdin_and_prints(self):
        r = self.run_py('print(int(input()) + 1)', '41\n')
        self.assertEqual((r['output'].strip(), r['error'], r['timed_out']), ('42', '', False))

    def test_reading_past_the_input_gets_eof_not_a_hang(self):
        r = self.run_py('import sys\nprint(len(sys.stdin.read()))', 'ab')
        self.assertEqual(r['output'].strip(), '2')
        self.assertFalse(r['timed_out'])

    def test_infinite_loop_is_killed_at_the_timeout(self):
        r = self.run_py('while True: pass')
        self.assertTrue(r['timed_out'])
        self.assertIn('Time limit exceeded', r['error'])

    def test_runtime_error_is_reported(self):
        r = self.run_py('raise ValueError("nope")')
        self.assertIn('ValueError', r['error'])

    def test_environment_is_empty(self):
        r = self.run_py('import os\nprint(sorted(k for k in os.environ if k not in ("LC_CTYPE",)))')
        self.assertEqual(r['output'].strip(), '[]')

    def test_huge_output_is_truncated(self):
        r = self.run_py("print('x' * 10_000_000)")
        self.assertLessEqual(len(r['output']), 64 * 1024 + 100)
        self.assertIn('output truncated', r['output'])

    def test_non_utf8_output_does_not_crash(self):
        r = self.run_py("import sys\nsys.stdout.buffer.write(b'\\xff\\xfe ok')")
        self.assertIn('ok', r['output'])

    @unittest.skipUnless(LINUX, 'RLIMIT_AS is only enforced on Linux (Lambda)')
    def test_memory_limit(self):
        r = self.run_py('x = bytearray(600 * 1024 * 1024)\nprint("allocated")')
        self.assertNotIn('allocated', r['output'])

    @unittest.skipUnless(LINUX, 'RLIMIT_NPROC is only applied on Linux')
    def test_fork_bomb_is_capped(self):
        r = self.run_py('import os\nfor _ in range(200):\n    try:\n        os.fork()\n    except OSError:\n        break\nprint("done")')
        self.assertFalse(r['timed_out'])


@unittest.skipUnless(HAS_NODE, 'node not installed')
class NodeSandboxTest(unittest.TestCase):
    def run_js(self, code, stdin=''):
        return sandbox.run('javascript', code, stdin, LIMITS)

    def test_reads_stdin_and_prints(self):
        code = "const d=require('fs').readFileSync(0,'utf8'); console.log(Number(d)+1)"
        self.assertEqual(self.run_js(code, '41').get('output').strip(), '42')

    def test_infinite_loop_is_killed(self):
        self.assertTrue(self.run_js('while(true){}')['timed_out'])

    def test_heap_limit(self):
        r = self.run_js("const a=[]; while(true){ a.push(new Array(1e6).fill(1)) }")
        self.assertNotEqual(r['error'], '')
        self.assertFalse(r['timed_out'] and 'heap' not in r['error'].lower() and r['output'])


class UnsupportedLanguageTest(unittest.TestCase):
    def test_unsupported_language(self):
        r = sandbox.run('cobol', 'x', '', LIMITS)
        self.assertIn('Unsupported language', r['error'])


if __name__ == '__main__':
    unittest.main()
```

Run: `cd lambda/exec && python3 -m unittest discover -s tests -v` → fails (`No module named sandbox`).

- [ ] **Step 2: Implement `lambda/exec/sandbox.py`**

```python
"""Run one test of student code in a resource-limited child process. Standard library only."""
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time

IS_LINUX = sys.platform.startswith('linux')


def _preexec(language, limits):
    def apply():
        os.setsid()  # own process group, so a timeout kills everything the code spawned
        cpu = int(limits['timeout_s'])
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
        if language == 'python':
            mem = int(limits['python_memory_mb']) * 1024 * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            except (ValueError, OSError):
                pass  # not enforceable on macOS; Lambda is Linux
        if IS_LINUX:
            resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
        if hasattr(os, 'geteuid') and os.geteuid() == 0:
            os.setgid(65534)
            os.setuid(65534)
    return apply


def _command(language, workdir, limits):
    if language == 'python':
        return [sys.executable, '-I', os.path.join(workdir, 'main.py')], 'main.py'
    if language == 'javascript':
        node = shutil.which('node')
        if not node:
            return None, 'main.js'
        return [node, f"--max-old-space-size={int(limits['node_heap_mb'])}", os.path.join(workdir, 'main.js')], 'main.js'
    return None, None


def _decode(data, cap):
    text = data[:cap].decode('utf-8', errors='replace')
    return text + ('\n[output truncated]' if len(data) > cap else '')


def run(language, code, stdin, limits):
    start = time.monotonic()
    ms = lambda: int((time.monotonic() - start) * 1000)  # noqa: E731
    workdir = tempfile.mkdtemp(prefix='job-')
    try:
        cmd, filename = _command(language, workdir, limits)
        if filename is None:
            return {'output': '', 'error': f'Unsupported language: {language}', 'ms': 0, 'timed_out': False}
        if cmd is None:
            return {'output': '', 'error': f'Runtime not available for {language}', 'ms': 0, 'timed_out': False}
        with open(os.path.join(workdir, filename), 'w') as f:
            f.write(code)
        os.chmod(workdir, 0o755)
        cap = int(limits['output_kb']) * 1024
        proc = subprocess.Popen(cmd, cwd=workdir, env={}, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, preexec_fn=_preexec(language, limits), close_fds=True)
        try:
            out, err = proc.communicate(input=(stdin or '').encode(), timeout=int(limits['timeout_s']))
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return {'output': '', 'error': 'Time limit exceeded', 'ms': ms(), 'timed_out': True}
        error = _decode(err, cap)
        if proc.returncode != 0 and not error:
            error = f'Exited with code {proc.returncode}'
        return {'output': _decode(out, cap), 'error': error, 'ms': ms(), 'timed_out': False}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
```

Notes for the implementer: `communicate(input=...)` writes stdin then closes it, which is what makes "reading past the input gets EOF" pass. Very large outputs are read fully by `communicate` before truncation; if the 10 MB test is slow, switch to reading stdout with a bounded loop. `-I` runs Python isolated (ignores env and user site).

Run the tests on the Mac: `cd lambda/exec && python3 -m unittest discover -s tests -v` → pass, Linux-only tests skipped.

- [ ] **Step 3: Linux test image** — `lambda/exec/Dockerfile.test`

```dockerfile
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends nodejs && rm -rf /var/lib/apt/lists/*
WORKDIR /exec
COPY . .
RUN useradd -m runner
USER runner
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
```

Run: `cd lambda/exec && docker build -f Dockerfile.test -t codemas-exec-test . && docker run --rm codemas-exec-test`
Expected: all tests pass, including memory and fork-bomb (running as non-root like Lambda).

- [ ] **Step 4: Write the failing handler tests** — `lambda/exec/tests/test_handler.py`

```python
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, __file__.rsplit('/tests/', 1)[0])
import handler  # noqa: E402


class FakeDjango(BaseHTTPRequestHandler):
    claims = {}      # job_id -> (status, body)
    completed = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        ok = handler.sign('secret', self.headers['X-Timestamp'], body) == self.headers['X-Signature']
        data = json.loads(body)
        if not ok:
            code, out = 401, {'error': 'bad signature'}
        elif self.path == '/internal/jobs/claim/':
            code, out = self.claims[data['job_id']]
        elif self.path == '/internal/jobs/complete/':
            FakeDjango.completed.append(data)
            code, out = 200, {'status': 'succeeded', 'submission_status': 'passed'}
        else:
            code, out = 200, {'status': 'released'}
        payload = json.dumps(out).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class HandlerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), FakeDjango)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        handler.os.environ['CODEMAS_API_URL'] = f'http://127.0.0.1:{cls.server.server_port}'
        handler.os.environ['JOB_SIGNING_SECRET'] = 'secret'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def event(self, *job_ids):
        return {'Records': [{'messageId': f'm-{j}', 'body': json.dumps({'job_id': j, 'kind': 'execute_submission'})}
                            for j in job_ids]}

    def test_claims_runs_and_completes(self):
        FakeDjango.claims['j1'] = (200, {
            'job_id': 'j1', 'lease_token': 'tok', 'kind': 'execute_submission', 'submission_id': 5,
            'language': 'python', 'code': 'print(int(input())*2)',
            'tests': [{'id': 1, 'input': '2', 'expected': '4'}, {'id': 2, 'input': '5', 'expected': '10'}],
            'limits': {'timeout_s': 3, 'python_memory_mb': 256, 'node_heap_mb': 192, 'output_kb': 64}})
        FakeDjango.completed.clear()
        resp = handler.handler(self.event('j1'), None)
        self.assertEqual(resp, {'batchItemFailures': []})
        done = FakeDjango.completed[-1]
        self.assertEqual((done['job_id'], done['lease_token']), ('j1', 'tok'))
        self.assertEqual([(r['test_id'], r['output'].strip()) for r in done['results']], [(1, '4'), (2, '10')])

    def test_done_busy_gone_dead_are_acknowledged_not_retried(self):
        for jid, code, err in (('d', 409, 'done'), ('g', 410, 'gone'), ('x', 410, 'dead')):
            FakeDjango.claims[jid] = (code, {'error': err})
        self.assertEqual(handler.handler(self.event('d', 'g', 'x'), None), {'batchItemFailures': []})

    def test_busy_is_retried_later(self):
        FakeDjango.claims['b'] = (409, {'error': 'busy'})
        self.assertEqual(handler.handler(self.event('b'), None), {'batchItemFailures': [{'itemIdentifier': 'm-b'}]})

    def test_unreachable_django_is_a_retry(self):
        handler.os.environ['CODEMAS_API_URL'] = 'http://127.0.0.1:9'
        try:
            self.assertEqual(handler.handler(self.event('z'), None), {'batchItemFailures': [{'itemIdentifier': 'm-z'}]})
        finally:
            handler.os.environ['CODEMAS_API_URL'] = f'http://127.0.0.1:{self.server.server_port}'


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 5: Implement `lambda/exec/handler.py`**

```python
"""codemas-exec: grades one submission per SQS message.

1. claim the job from Django (signed request) -> code, tests, limits, lease token
2. run every test in the sandbox
3. complete the job with each test's output (Django decides pass/fail and records it)

No database credentials and no third-party packages: everything goes through Django over HTTPS.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request

import sandbox

ACK = ('done', 'gone', 'dead')  # the job needs no more work: acknowledge the message


def sign(secret, timestamp, body):
    msg = timestamp.encode() + b'.' + body
    return 'sha256=' + hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _post(path, payload):
    body = json.dumps(payload).encode()
    ts = str(int(time.time()))
    req = urllib.request.Request(
        os.environ['CODEMAS_API_URL'].rstrip('/') + path, data=body, method='POST',
        headers={'Content-Type': 'application/json', 'X-Timestamp': ts,
                 'X-Signature': sign(os.environ['JOB_SIGNING_SECRET'], ts, body)})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def _grade(job_id):
    """Returns True when the message can be acknowledged, False to have SQS retry it."""
    started = time.monotonic()
    status, job = _post('/internal/jobs/claim/', {'job_id': job_id})
    if status != 200:
        print(json.dumps({'job_id': job_id, 'claim': status, 'error': job.get('error')}))
        return job.get('error') in ACK
    try:
        results = [{'test_id': t['id'], **sandbox.run(job['language'], job['code'], t['input'], job['limits'])}
                   for t in job['tests']]
    except Exception as e:  # infrastructure problem in the grader itself
        _post('/internal/jobs/fail/', {'job_id': job_id, 'lease_token': job['lease_token'], 'error': repr(e)})
        return False
    status, done = _post('/internal/jobs/complete/', {'job_id': job_id, 'lease_token': job['lease_token'],
                                                       'results': results})
    print(json.dumps({'job_id': job_id, 'submission_id': job['submission_id'], 'language': job['language'],
                      'tests': len(results), 'submission_status': done.get('submission_status'),
                      'complete': status, 'duration_ms': int((time.monotonic() - started) * 1000)}))
    return status in (200, 409)  # 409 stale: a newer lease owns it; nothing for us to retry


def handler(event, context):
    failures = []
    for record in event.get('Records', []):
        try:
            ok = _grade(json.loads(record['body'])['job_id'])
        except Exception as e:  # unreachable Django, bad message: let SQS retry, then DLQ
            print(json.dumps({'messageId': record.get('messageId'), 'error': repr(e)}))
            ok = False
        if not ok:
            failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': failures}
```

Run: `cd lambda/exec && python3 -m unittest discover -s tests -v` → pass. Then `cd backend && venv/bin/python manage.py test jobs.tests.test_signing` → the Lambda-compat test now runs and passes.

- [ ] **Step 6: Delete the old runners** — remove `lambda/cpp_runner.py`, `lambda/java_runner.py`, `lambda/javascript_runner.py`, `lambda/python_runner.py` (use `rm`, not git). In `backend/execution/tasks.py` delete `run_in_lambda` and the commented Docker/Lambda call blocks and the commented `import boto3`; keep `run_local` and `execute_submission` (legacy path). Run the full backend suite.

- [ ] **Step 7: Checkpoint** — Docker Linux test run green; full backend suite green.

---

### Task 5: Relay and transports (local first, SQS ready)

**Files:**
- Create: `backend/jobs/transports.py`, `backend/jobs/relay.py`, `backend/jobs/management/__init__.py`, `backend/jobs/management/commands/__init__.py`, `backend/jobs/management/commands/run_relay.py`, `backend/jobs/tests/test_relay.py`, `backend/jobs/tests/test_e2e.py`
- Modify: `backend/requirements.txt` (add `boto3==1.40.*` — pin the exact latest patch you install; run `venv/bin/pip install boto3` and record the version)

**Interfaces:**
- Consumes: `Job`, `MAX_ATTEMPTS`, settings `JOB_TRANSPORT`, `JOB_QUEUE_URL`, `AWS_REGION`, `LAMBDA_EXEC_DIR`, `CODEMAS_API_URL`, `JOB_SIGNING_SECRET`, `RELAY_INTERVAL_S`; Lambda `handler.handler(event, context)`.
- Produces: `jobs.transports.get_transport() -> Transport` with `publish(job: Job) -> None`; `jobs.relay.tick(transport, batch=50) -> int` (jobs published); `jobs.relay.sweep_stuck(now=None) -> dict` (`{"requeued": n, "dead": m}`); command `python manage.py run_relay [--once]`.

- [ ] **Step 1: Write the failing relay tests** — `backend/jobs/tests/test_relay.py`

```python
from datetime import timedelta

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from jobs.models import Job
from jobs.relay import sweep_stuck, tick
from jobs.services import enqueue


class FakeTransport:
    def __init__(self, fail_on=None):
        self.sent, self.fail_on = [], fail_on

    def publish(self, job):
        if job.subject_id == self.fail_on:
            raise ConnectionError('queue down')
        self.sent.append(job.subject_id)


class RelayTest(TestCase):
    def make(self, sid):
        with transaction.atomic():
            return enqueue(Job.KIND_EXECUTE, sid)

    def test_tick_publishes_pending_jobs_and_marks_them_queued(self):
        a, b = self.make(1), self.make(2)
        t = FakeTransport()
        self.assertEqual(tick(t), 2)
        self.assertEqual(sorted(t.sent), [1, 2])
        for j in (a, b):
            j.refresh_from_db()
            self.assertEqual(j.status, 'queued')
            self.assertIsNotNone(j.published_at)

    def test_a_failed_publish_leaves_the_job_pending_for_the_next_tick(self):
        a = self.make(3)
        tick(FakeTransport(fail_on=3))
        a.refresh_from_db()
        self.assertEqual(a.status, 'pending')

    def test_sweep_requeues_expired_leases_and_kills_after_max_attempts(self):
        stuck, worn = self.make(4), self.make(5)
        past = timezone.now() - timedelta(minutes=1)
        Job.objects.filter(pk=stuck.pk).update(status='running', attempt=1, lease_expires_at=past)
        Job.objects.filter(pk=worn.pk).update(status='running', attempt=3, lease_expires_at=past)
        self.assertEqual(sweep_stuck(), {'requeued': 1, 'dead': 1})
        stuck.refresh_from_db(); worn.refresh_from_db()
        self.assertEqual((stuck.status, worn.status), ('pending', 'dead'))

    def test_sweep_republishes_jobs_queued_too_long(self):
        j = self.make(6)
        Job.objects.filter(pk=j.pk).update(status='queued', published_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(sweep_stuck()['requeued'], 1)
```

- [ ] **Step 2: Implement `backend/jobs/relay.py`**

```python
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import MAX_ATTEMPTS, Job

QUEUED_TOO_LONG = timedelta(minutes=10)


def tick(transport, batch=50):
    """Publish pending jobs. SKIP LOCKED lets several relays run without taking the same rows."""
    published = 0
    with transaction.atomic():
        jobs = list(Job.objects.select_for_update(skip_locked=True)
                    .filter(status='pending').order_by('created_at')[:batch])
        for job in jobs:
            try:
                transport.publish(job)
            except Exception as e:  # stays pending; retried next tick
                Job.objects.filter(pk=job.pk).update(last_error=f'publish failed: {e!r}'[:2000])
                continue
            Job.objects.filter(pk=job.pk).update(status='queued', published_at=timezone.now())
            published += 1
    return published


def sweep_stuck(now=None):
    """Safety net for lost messages and crashed handlers. Claiming is idempotent, so a duplicate is harmless."""
    from submissions.models import Submission
    now = now or timezone.now()
    requeued = dead = 0
    with transaction.atomic():
        expired = Job.objects.select_for_update(skip_locked=True).filter(status='running', lease_expires_at__lt=now)
        for job in expired:
            if job.attempt >= MAX_ATTEMPTS:
                Job.objects.filter(pk=job.pk).update(status='dead', finished_at=now, lease_token=None)
                Submission.objects.filter(pk=job.subject_id).update(status='error')
                dead += 1
            else:
                Job.objects.filter(pk=job.pk).update(status='pending', lease_token=None, lease_expires_at=None)
                requeued += 1
        requeued += (Job.objects.filter(status='queued', published_at__lt=now - QUEUED_TOO_LONG)
                     .update(status='pending'))
    return {'requeued': requeued, 'dead': dead}
```

- [ ] **Step 3: Implement `backend/jobs/transports.py`**

```python
import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings


def _message(job):
    return json.dumps({'job_id': str(job.id), 'kind': job.kind})


class LocalTransport:
    """Runs the real Lambda handler code in a thread pool. For laptops and tests: no AWS needed."""

    def __init__(self, workers=4):
        os.environ.setdefault('CODEMAS_API_URL', settings.CODEMAS_API_URL)
        os.environ.setdefault('JOB_SIGNING_SECRET', settings.JOB_SIGNING_SECRET)
        spec = importlib.util.spec_from_file_location('codemas_exec_handler', settings.LAMBDA_EXEC_DIR / 'handler.py',
                                                      submodule_search_locations=[str(settings.LAMBDA_EXEC_DIR)])
        import sys
        sys.path.insert(0, str(settings.LAMBDA_EXEC_DIR))  # so handler's `import sandbox` resolves
        self.handler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.handler)
        self.pool = ThreadPoolExecutor(max_workers=workers)

    def publish(self, job):
        event = {'Records': [{'messageId': str(job.id), 'body': _message(job)}]}
        self.pool.submit(self.handler.handler, event, None)


class SqsTransport:
    """Sends the job ID to the codemas-exec queue. Lambda is triggered by SQS."""

    def __init__(self):
        import boto3
        self.client = boto3.client('sqs', region_name=settings.AWS_REGION)
        self.url = settings.JOB_QUEUE_URL

    def publish(self, job):
        language = ''
        if job.kind == job.KIND_EXECUTE:
            from submissions.models import Submission
            language = Submission.objects.filter(pk=job.subject_id).values_list('language', flat=True).first() or ''
        self.client.send_message(
            QueueUrl=self.url, MessageBody=_message(job),
            MessageAttributes={'job_id': {'DataType': 'String', 'StringValue': str(job.id)},
                               'language': {'DataType': 'String', 'StringValue': language or 'unknown'}})


def get_transport():
    if settings.JOB_TRANSPORT == 'sqs':
        return SqsTransport()
    return LocalTransport()
```

- [ ] **Step 4: Implement the command** — `backend/jobs/management/commands/run_relay.py`

```python
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from jobs.relay import sweep_stuck, tick
from jobs.transports import get_transport


class Command(BaseCommand):
    help = 'Publish pending jobs from the outbox to the configured transport (local or sqs).'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Run one tick and one sweep, then exit.')

    def handle(self, *args, **opts):
        transport = get_transport()
        self.stdout.write(f'relay: transport={settings.JOB_TRANSPORT} interval={settings.RELAY_INTERVAL_S}s')
        last_sweep = 0.0
        while True:
            close_old_connections()
            n = tick(transport)
            if n:
                self.stdout.write(f'relay: published {n}')
            if time.monotonic() - last_sweep > 60:
                swept = sweep_stuck()
                if any(swept.values()):
                    self.stdout.write(f'relay: sweep {swept}')
                last_sweep = time.monotonic()
            if opts['once']:
                return
            time.sleep(settings.RELAY_INTERVAL_S)
```

Run: `venv/bin/python manage.py test jobs.tests.test_relay` → pass.

- [ ] **Step 5: End-to-end test through the real handler and a live server** — `backend/jobs/tests/test_e2e.py`

```python
import shutil
import time
from datetime import timedelta

from django.test import LiveServerTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, Question, TestCase as QTest
from jobs.models import Job
from jobs.relay import tick
from jobs.transports import LocalTransport


@override_settings(JOB_SIGNING_SECRET='e2e-secret', PIPELINE_LANGUAGES={'python', 'javascript'})
class LocalPipelineE2E(LiveServerTestCase):
    def setUp(self):
        import os
        os.environ['CODEMAS_API_URL'] = self.live_server_url
        os.environ['JOB_SIGNING_SECRET'] = 'e2e-secret'
        trainer = User.objects.create_user(username='tr', password='pw', role='trainer')
        self.student = User.objects.create_user(username='st', password='pw', role='student', cohort='C')
        exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60, is_active=True,
                                   start_time=timezone.now() - timedelta(hours=1), end_time=timezone.now() + timedelta(hours=1))
        self.q = Question.objects.create(exam=exam, title='Double', description='d', difficulty='easy')
        QTest.objects.create(question=self.q, input_data='2', expected_output='4')
        QTest.objects.create(question=self.q, input_data='5', expected_output='10')
        self.api = APIClient(); self.api.force_authenticate(self.student)

    def grade(self, language, code):
        sid = self.api.post('/api/submissions/create/', {'question': self.q.id, 'code': code, 'language': language},
                            format='json').data['id']
        transport = LocalTransport(workers=1)
        self.assertEqual(tick(transport), 1)
        transport.pool.shutdown(wait=True)
        return self.api.get(f'/api/submissions/{sid}/status/').data

    def test_python_submission_is_graded_end_to_end(self):
        data = self.grade('python', 'print(int(input()) * 2)')
        self.assertEqual((data['status'], data['job']['status'], data['results_ready']), ('passed', 'succeeded', True))

    def test_wrong_answer_fails(self):
        self.assertEqual(self.grade('python', 'print(int(input()) + 2)')['status'], 'failed')

    def test_javascript_submission_is_graded_end_to_end(self):
        if not shutil.which('node'):
            self.skipTest('node not installed')
        code = "const n=Number(require('fs').readFileSync(0,'utf8')); console.log(n*2)"
        self.assertEqual(self.grade('javascript', code)['status'], 'passed')
```

Run: `venv/bin/python manage.py test jobs` → all pass. Full suite green.

- [ ] **Step 6: Checkpoint (manual, local)** — with `runserver` running: `cd backend && venv/bin/python manage.py run_relay` in a second terminal; submit as a student in the browser (Python Binary Search Exam); confirm the Jobs admin shows the row moving `pending → queued → running → succeeded` and the relay prints `published 1`.

---

### Task 6: Frontend — poll the status endpoint instead of SSE

**Files:**
- Modify: `frontend/src/views/ExamTakeView.vue` (replace `listenForResult` and its SSE use)

**Interfaces:**
- Consumes: `GET /submissions/<id>/status/` (Task 3) → `{status, results_ready, job: {status, attempt, ...} | null}`; existing `finalizeResult(submissionId, status)`, `stage` ref, `stopElapsedClock()`.

- [ ] **Step 1: Replace `listenForResult`** (keep `finalizeResult`, rubric and hint polling as they are)

```ts
// Poll the submission's status until it is graded. Works the same for the job pipeline and the
// legacy path, and resumes after a page refresh (the id is kept in sessionStorage per question).
let statusTimer: ReturnType<typeof setTimeout> | null = null
const POLL_DELAYS_MS = [1000, 1000, 1000, 1000, 1000, 2000, 2000, 3000]

function pollKey(questionId: number) {
    return `codemas:pending-submission:${route.params.id}:${questionId}`
}

function listenForResult(submissionId: number): void {
    if (statusTimer) clearTimeout(statusTimer)
    const qid = currentQuestion.value?.id
    if (qid) {
        try { sessionStorage.setItem(pollKey(qid), String(submissionId)) } catch { /* storage unavailable */ }
    }
    let attempt = 0
    const poll = async (): Promise<void> => {
        try {
            const { data } = await api.get(`/submissions/${submissionId}/status/`)
            const jobStatus: string | undefined = data.job?.status
            if (jobStatus === 'dead') {
                stopElapsedClock()
                stage.value = 'idle'
                submissionStatus.value = ''
                submitError.value = "We couldn't grade this submission. It wasn't counted against your attempts."
                clearPending(qid)
                return
            }
            if (data.status === 'error' && data.results_ready) {
                stopElapsedClock()
                stage.value = 'idle'
                submissionStatus.value = ''
                submitError.value = "This question has no test cases yet, so it can't be graded. Tell your trainer."
                clearPending(qid)
                return
            }
            if (data.status === 'passed' || data.status === 'failed') {
                submissionStatus.value = data.status
                stage.value = 'grade'
                clearPending(qid)
                await finalizeResult(submissionId, data.status)
                return
            }
            stage.value = jobStatus === 'running' || data.status === 'running' ? 'execute' : 'queue'
        } catch {
            // transient network error: keep polling
        }
        const delay = POLL_DELAYS_MS[Math.min(attempt, POLL_DELAYS_MS.length - 1)] ?? 3000
        attempt += 1
        statusTimer = setTimeout(poll, delay)
    }
    void poll()
}

function clearPending(questionId: number | undefined) {
    if (!questionId) return
    try { sessionStorage.removeItem(pollKey(questionId)) } catch { /* storage unavailable */ }
}
```

Then:
- Delete the `eventSource` variable, its `close()` calls and the `API_BASE_URL` import if nothing else uses it.
- In `onUnmounted`, clear `statusTimer`.
- On mount, after questions load, resume: for the current question, read `sessionStorage.getItem(pollKey(q.id))`; if present, set `stage.value = 'queue'`, start the elapsed clock and call `listenForResult(Number(id))`.
- Keep stage meanings: `queue` while the job is pending or queued, `execute` while running, `grade` once passed or failed, then `feedback`/`done` as today.

- [ ] **Step 2: Verify types and build**

Run: `cd frontend && npx vue-tsc --build 2>&1 | grep -c "error TS"` → `44`; `npm run build-only` → built.

- [ ] **Step 3: Browser check (local)** — runserver + `run_relay` + Vite. As `aarav_sharma0` / `student123`: open the open exam, submit a correct Python answer, watch Submit → Queue → Execute → Grade → Feedback; refresh mid-grading and confirm it resumes; submit JavaScript too. Then stop the relay, submit, confirm the tracker waits at Queue ("Waiting for a free worker"), start the relay and confirm it completes.

---

### Task 7: Local dev wiring and docs

**Files:**
- Create: `docs/dev-pipeline.md`, `docs/demo-runbook.md`
- Modify: `Codemas-SYSTEM_DESIGN.md` (submission pipeline section), `submission_animation.html` (replace with the step-through diagram, marked as built), `submission_flow.html` (flow text), `backend/.env` example comments if an `.env.example` exists (do not edit the real `.env` secrets)

- [ ] **Step 1: `docs/dev-pipeline.md`** — how to run locally: `runserver`, `run_relay` (local transport), Celery worker (still needed for AI feedback, plagiarism and C++/Java), Vite; the settings table (`JOB_TRANSPORT`, `PIPELINE_LANGUAGES`, `JOB_SIGNING_SECRET`, `CODEMAS_API_URL`); how to run `lambda/exec` tests on the Mac and in Docker; how to flip a language back to Celery.

- [ ] **Step 2: `docs/demo-runbook.md`** — for each demo question, exact clicks/commands:
  - Outbox: `/admin/jobs/job/` filtered by status; SQL `select id, status, attempt, published_at, started_at, finished_at from jobs_job order by created_at desc limit 10;`
  - Queue: AWS console → SQS → `codemas-exec` (available / in flight), DLQ `codemas-exec-dlq`; CLI `aws sqs get-queue-attributes --queue-url <url> --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible`
  - Lambda code: console → Lambda → `codemas-exec` → Code; repo `lambda/exec/handler.py`
  - This submission's execution: `aws logs tail /aws/lambda/codemas-exec --since 5m --filter-pattern '"submission_id": <id>'`
  - Failure story: stop the relay, submit, show the job waiting as `pending`; start it again.

- [ ] **Step 3: Update `Codemas-SYSTEM_DESIGN.md`** pipeline section to the built flow (outbox, relay, transports, claim/complete, sandbox limits, polling), stating what stays on Celery. Replace `submission_animation.html` with the step-through diagram from https://claude.ai/artifact/JDsZrSjoCLVuqC2GCseLEL (source: `/private/tmp/claude-501/-Users-swanandkadam-Desktop-Codemas-claude/a4a07351-c60a-4524-9ce8-c6e80a483b00/scratchpad/grading-pipeline.html`), adding `<!doctype html><html><head><meta charset="utf-8">…</head><body>` and changing the status note from "Target design" to "Built: local transport; SQS and Lambda once deployed".

- [ ] **Step 4: Checkpoint** — docs reviewed by the coordinator.

---

### Task 8: AWS — CloudFormation, deploy and smoke scripts (needs the user's AWS account)

**Files:**
- Create: `deploy/aws/pipeline.yaml`, `deploy/aws/deploy.sh`, `deploy/aws/smoke.sh`, `deploy/aws/README.md`

**Interfaces:**
- Consumes: `lambda/exec/` (zip root), the Node.js 20 Linux x64 release.
- Produces: stack `codemas-pipeline` outputs `QueueUrl`, `DlqUrl`, `FunctionName`, `RelayUserName`; a relay access key written to `deploy/aws/.relay-credentials` (mode 600, git-ignored) for the user to paste into Railway themselves.

- [ ] **Step 1: `deploy/aws/pipeline.yaml`**

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: CodeMas grading pipeline - one queue, one dead-letter queue, one Lambda function (codemas-exec).

Parameters:
  CodemasApiUrl:
    Type: String
    Description: Public base URL of the Django backend (Railway), e.g. https://codemas-api.up.railway.app
  JobSigningSecret:
    Type: String
    NoEcho: true
    MinLength: 32

Resources:
  ExecDLQ:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: codemas-exec-dlq
      MessageRetentionPeriod: 1209600

  ExecQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: codemas-exec
      VisibilityTimeout: 540
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt ExecDLQ.Arn
        maxReceiveCount: 3

  NodeLayer:
    Type: AWS::Lambda::LayerVersion
    Properties:
      LayerName: codemas-node20
      Description: Node.js 20 runtime binary at /opt/bin/node (no CodeMas code)
      Content: ../../build/node-layer.zip
      CompatibleRuntimes: [python3.12]
      CompatibleArchitectures: [x86_64]

  ExecRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal: { Service: lambda.amazonaws.com }
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
      Policies:
        - PolicyName: read-exec-queue
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action: [sqs:ReceiveMessage, sqs:DeleteMessage, sqs:GetQueueAttributes, sqs:ChangeMessageVisibility]
                Resource: !GetAtt ExecQueue.Arn

  ExecFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: codemas-exec
      Runtime: python3.12
      Handler: handler.handler
      Code: ../../build/exec
      Role: !GetAtt ExecRole.Arn
      Timeout: 90
      MemorySize: 1024
      Architectures: [x86_64]
      Layers: [!Ref NodeLayer]
      Environment:
        Variables:
          CODEMAS_API_URL: !Ref CodemasApiUrl
          JOB_SIGNING_SECRET: !Ref JobSigningSecret

  ExecTrigger:
    Type: AWS::Lambda::EventSourceMapping
    Properties:
      EventSourceArn: !GetAtt ExecQueue.Arn
      FunctionName: !Ref ExecFunction
      BatchSize: 1
      FunctionResponseTypes: [ReportBatchItemFailures]
      ScalingConfig:
        MaximumConcurrency: 5

  RelayUser:
    Type: AWS::IAM::User
    Properties:
      UserName: codemas-relay
      Policies:
        - PolicyName: send-to-exec-queue
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action: sqs:SendMessage
                Resource: !GetAtt ExecQueue.Arn

Outputs:
  QueueUrl: { Value: !Ref ExecQueue }
  DlqUrl: { Value: !Ref ExecDLQ }
  FunctionName: { Value: !Ref ExecFunction }
  RelayUserName: { Value: !Ref RelayUser }
```

`Code:` points at `build/exec/`, which `deploy.sh` fills with only `handler.py` and `sandbox.py`, so tests and the Docker test file never reach Lambda.

- [ ] **Step 2: `deploy/aws/deploy.sh`** (bash, `set -euo pipefail`; region `ap-southeast-1`)
  1. Require `aws sts get-caller-identity` to succeed; require `CODEMAS_API_URL` and `JOB_SIGNING_SECRET` env vars (refuse if the secret is shorter than 32 chars).
  2. `build/exec/`: copy `lambda/exec/handler.py` and `lambda/exec/sandbox.py`.
  3. `build/node-layer.zip`: download `https://nodejs.org/dist/latest-v20.x/` `node-v20.*-linux-x64.tar.xz`, verify its SHA256 against `SHASUMS256.txt`, extract `bin/node` into `build/layer/bin/node`, zip as `bin/node`.
  4. Artifact bucket `codemas-artifacts-<account-id>-ap-southeast-1` (create if missing, block public access).
  5. `aws cloudformation package --template-file deploy/aws/pipeline.yaml --s3-bucket <bucket> --output-template-file build/packaged.yaml`
  6. `aws cloudformation deploy --stack-name codemas-pipeline --template-file build/packaged.yaml --capabilities CAPABILITY_NAMED_IAM --parameter-overrides CodemasApiUrl=$CODEMAS_API_URL JobSigningSecret=$JOB_SIGNING_SECRET`
  7. Print stack outputs. If `deploy/aws/.relay-credentials` doesn't exist, `aws iam create-access-key --user-name codemas-relay` and write it there with `chmod 600`; print only the file path, never the secret.
  8. Add `build/` and `deploy/aws/.relay-credentials` to `.gitignore`.

- [ ] **Step 3: `deploy/aws/smoke.sh`** — inputs `CODEMAS_API_URL`, a student username/password; logs in (`POST /api/auth/login/`), finds the open exam's first question, submits a correct Python and a correct JavaScript solution for "Find Target in Sorted Array" (binary search reading `n`, the array, the target), polls `/status/` until terminal (timeout 60 s), and then prints `aws logs tail /aws/lambda/codemas-exec --since 5m --filter-pattern '"submission_id"'` lines for the two submission ids. Exit non-zero if either isn't `passed`.

- [ ] **Step 4: `deploy/aws/README.md`** — one-time setup: create the AWS account, root MFA, budget alert, IAM user `codemas-deployer` (AdministratorAccess), `aws configure` (region ap-southeast-1), then `CODEMAS_API_URL=… JOB_SIGNING_SECRET=$(openssl rand -hex 32) deploy/aws/deploy.sh`; what to set on Railway afterwards (Task 9).

- [ ] **Step 5: Validate without deploying** — `aws cloudformation validate-template --template-body file://deploy/aws/pipeline.yaml` once the user's credentials exist (skip and note it if they don't). Run `bash -n` on both scripts. Do **not** run `deploy.sh` until the coordinator confirms the user approved deploying.

---

### Task 9: Railway + AWS go-live (gated: the user approves each step)

Not for a subagent to start on its own. The coordinator runs these with the user's explicit OK at each step:

Order matters (corrected after the final review; matches `deploy/aws/README.md` "After deploy"):

1. Generate the signing secret once: `openssl rand -hex 32` (keep it in a password manager, never on a command line).
2. Railway `web`, **before the branch is pushed**: set `JOB_SIGNING_SECRET=<it>` and `PIPELINE_LANGUAGES=` (empty); confirm `DEBUG` is unset or not `True`. With `DEBUG` off, a missing/default/short secret fails system check `jobs.E001`, so `migrate` (and the web deploy) stops.
3. Push/deploy the branch (migrations run on start). `submissions.0008` renumbers any duplicate attempts before adding its unique constraint, so it needs no manual pre-check; the optional read-only check is `select student_id, question_id, attempt_number, count(*) from submissions_submission group by 1, 2, 3 having count(*) > 1;`.
4. Run `deploy/aws/deploy.sh` with Railway's backend URL and the same secret; set `CODEMAS_API_URL` on web.
5. Railway: add service `relay` from the same repo, root directory `backend`, same Dockerfile, start command `python manage.py run_relay`, no public domain, variables `JOB_TRANSPORT=sqs` (mandatory: the default `local` crash-loops), `JOB_QUEUE_URL=<QueueUrl output>`, `AWS_REGION=ap-southeast-1`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` from `.relay-credentials` (the user pastes these in Railway themselves), `JOB_SIGNING_SECRET` (the same value: `run_relay` runs the `jobs.E001` check too), `CODEMAS_API_URL`, plus the same DB/Redis/`SECRET_KEY` variables as `web`. Check its logs show `relay: transport=sqs`.
6. Railway data: re-seed (or at minimum: policy reset, admin role, one open exam) and re-run plagiarism checks on closed exams. Re-seeding deletes non-staff students, so create the throwaway smoke student afterwards, and make sure a superuser exists for the admin demo.
7. Only now set `PIPELINE_LANGUAGES=python,javascript` on `web`.
8. Run `deploy/aws/smoke.sh` against Railway straight away, with the throwaway student (never the demo student). If it fails, set `PIPELINE_LANGUAGES=` back to empty.
9. Update `docs/demo-runbook.md` and `docs/dev-pipeline.md` where they say nothing runs on AWS yet; open the demo runbook and walk every "show me" item once.

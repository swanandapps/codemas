# CodeMas — System Design Knowledge Base

**Author:** Swanand Kadam  
**Date:** May 2026

---

## Table of Contents

1. [What Is CodeMas](#1-what-is-codemas)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Tech Stack Decisions](#3-tech-stack-decisions)
4. [Data Models](#4-data-models)
5. [Submission Pipeline — The Core Flow](#5-submission-pipeline--the-core-flow)
6. [Execution Engine — Docker Sandbox](#6-execution-engine--docker-sandbox)
7. [Real-Time Result Delivery — SSE](#7-real-time-result-delivery--sse)
8. [Plagiarism Detection System](#8-plagiarism-detection-system)
   - 8.1 [Policy Versioning and Changelog](#81-policy-versioning-and-changelog)
   - 8.2 [Cohort Investigation and Cheating Ring Detection](#82-cohort-investigation-and-cheating-ring-detection)
9. [Code Similarity Search](#9-code-similarity-search)
   - 9.5 [AI Features Layer (Async GPT)](#95-ai-features-layer-async-gpt)
10. [Auto-Exam Lifecycle — Celery Beat](#10-auto-exam-lifecycle--celery-beat)
11. [Trainer Dashboard and Monitoring](#11-trainer-dashboard-and-monitoring)
12. [Cost Analysis Engine](#12-cost-analysis-engine)
13. [Authentication and Authorization](#13-authentication-and-authorization)
14. [Concurrency and Scaling](#14-concurrency-and-scaling)
15. [Infrastructure Cost Comparison — EC2 vs Fargate vs Lambda](#15-infrastructure-cost-comparison--ec2-vs-fargate-vs-lambda)
17. [Known Gaps and Honest Limitations](#17-known-gaps-and-honest-limitations)
18. [Testing Strategy](#18-testing-strategy)

---

## 1. What Is CodeMas

CodeMas is a real-time coding exam platform built to demonstrate systems thinking for a Senior Full-Stack role. Students write code in a browser editor, submit it, and receive test-case results in under 10 seconds. Trainers monitor their cohort live, review plagiarism flags, and manage exam lifecycle.

### Primary User Flows

**Student Flow:**
1. Log in, see active exams
2. Enter exam — countdown timer starts
3. Write code in browser (CodeMirror editor)
4. Submit — receives pass/fail with per-test-case breakdown in <10 seconds
5. Up to 3 attempts per question (configurable)

**Trainer Flow:**
1. Build exam — add questions, test cases (hidden), set duration
2. Pick who takes it — the whole cohort (default) or some sections (`Exam.sections`, matched against each student's `User.cohort`). Going live (Activate now on a draft's exam report, the scheduler's auto-open, or creating it live) enrolls that audience automatically; nobody is ever un-enrolled, and the per-student API (`/api/exams/{id}/enrollments/`) stays for exceptions
3. Monitor the live exam on its exam report (`/dashboard/history/<id>`: attempts and latest submission per student, End exam); trainers opening `/exams/<id>` are sent there, and the old exam operations URL redirects there
4. After exam closes (end_time, Close exam, or the last enrolled student submits the exam) — or any time via **Run plagiarism check** on the exam report — review plagiarism flags (behavioural + similarity)
5. Review individual submission detail, confirm/dismiss with a note — the student sees the verdict and note on their results page

### Scale Target
10,000 concurrent students. This is the load number that informs every design decision.

---

## 2. High-Level Architecture

```
                           ┌─────────────────────────────────────────────┐
                           │              BROWSER (Vue 3 + Vite)          │
                           │                                               │
                           │  CodeMirror 6   Pinia Store   ECharts        │
                           │  (editor)       (state)       (charts)       │
                           │                                               │
                           │  Axios  ──────────────→ REST API             │
                           │  polls GET /submissions/{id}/status/         │
                           └────────────────┬─────────────────────────────┘
                                            │ HTTP/REST (JWT)
                                            ▼
                           ┌─────────────────────────────────────────────┐
                           │            Django 4.2 + DRF + Gunicorn       │
                           │                                               │
                           │  /api/submissions/create/        POST        │
                           │  /api/submissions/{id}/status/   GET (poll)  │
                           │  /api/plagiarism/flags/          GET         │
                           │  /api/plagiarism/search/         POST        │
                           │  /api/dashboard/                 GET         │
                           │  /internal/jobs/claim|complete|fail  POST    │
                           │    (per-job token, for the executor only)    │
                           │                                               │
                           │  Simple JWT auth   |   Role-based guards     │
                           └────────┬─────────────────────┬───────────────┘
                                    │                      │
                    ┌───────────────▼──┐      ┌──────────▼──────────────┐
                    │   PostgreSQL     │      │         Redis            │
                    │   (ACID writes)  │      │                          │
                    │                 │      │  Broker (Celery queue)   │
                    │  Users          │      │  Cache (10s TTL)         │
                    │  Exams          │      │  JWT blacklist           │
                    │  Questions      │      └──────────┬───────────────┘
                    │  Submissions    │                 │
                    │  Jobs (outbox)  │      ┌──────────▼───────────────┐
                    │  BehaviouralFlag│      │    Celery Workers        │
                    │  PlagiarismFlag │      │                          │
                    │  PlagiarismPolicy│     │  execute_submission      │
                    └───────┬──────────┘    │    (C++ / Java only)     │
                            │               │  score_rubric, hints     │
                            │ pending jobs  │  run_exam_plagiarism_    │
                            │ SKIP LOCKED   │    check (Phase 1+2)     │
                    ┌───────▼──────────┐    │  auto_manage_exams       │
                    │  Relay           │    │    (Celery Beat, 60s)    │
                    │  manage.py       │    └──────────────────────────┘
                    │  run_relay       │
                    └───────┬──────────┘
                            │ {job_id} only
                    ┌───────▼──────────────────────────────────────────┐
                    │  Executor: lambda/exec/handler.py + sandbox.py    │
                    │  local:  thread pool inside the relay             │
                    │  live (2026-10-05): SQS codemas-exec → Lambda     │
                    │                    codemas-exec (arm64, Py+Node)  │
                    │  claims code + tests from Django, runs each test  │
                    │  in an rlimited child process, posts outputs back │
                    └──────────────────────────────────────────────────┘
```

### Django App Structure

```
backend/
├── accounts/        # User model (Student / Trainer / Admin roles)
├── exams/           # Exam, Question, TestCase, ExamEnrollment models
│                    # + auto_manage_exams Celery Beat task
├── submissions/     # Submission model, create/list/detail/status views
│                    # (the SSE stream, sse.py, was removed; the frontend polls /status/)
├── jobs/            # Job outbox model, relay (run_relay), transports (local / sqs),
│                    # claim/complete/fail API for the executor (per-job token)
├── execution/       # legacy execute_submission Celery task — C++ and Java only
│                    # (run_local: dev-only subprocess executor, no sandbox)
├── results/         # Result model — per-test-case outcome
├── plagiarism/      # BehaviouralFlag, PlagiarismFlag, PlagiarismPolicy
│                    # + all detection tasks + code similarity search
├── dashboard/       # Trainer KPI view, student detail, exam history
│                    # + CostAnalysisView (Fargate pricing model)
├── leaderboard/     # Student score/streak views
├── analytics/       # metrics.py — the single source of truth for every rate
│                    # (success rate = students who passed, flagged students, took, flags to review, risk)
├── ai/              # Async GPT features (additive layer, off the critical path):
│                    # rubric scoring, Socratic hints, plagiarism explanations
│                    # — models, tasks, shared OpenAI client (llm.py), read-only API
└── codemas/         # settings.py, urls.py, celery.py, signals.py

lambda/exec/         # the executor: handler.py + sandbox.py (standard library only);
                     # run by the relay's local transport locally, and live as the codemas-exec Lambda since 2026-10-05
```

---

## 3. Tech Stack Decisions

### Decision Table

| Layer | Choice | Alternatives Considered | Reason for Choice |
|---|---|---|---|
| Frontend framework | Vue 3 + Vite | React, Angular | Composition API, fast HMR, familiar |
| Code editor | CodeMirror 6 | Monaco, Ace | Modular, tree-shakeable, great mobile support |
| State management | Pinia | Vuex, Redux | Lighter, TypeScript-native |
| Charts | ECharts | Chart.js, D3 | Large dataset performance (10k students) |
| Result delivery | Polling `/status/` (1 s → 3 s backoff) | SSE, WebSockets | Survives refresh and needs no open connection or pub/sub; SSE was the original choice (§7) |
| Backend framework | Django 4.2 + DRF | FastAPI, Node.js | ORM, migrations, admin, batteries included |
| Authentication | Simple JWT | Session auth, OAuth | Stateless, works for mobile/SPA clients |
| Async jobs | Transactional outbox + relay for execution (SQS, live since 2026-10-05); Celery + Redis for AI, plagiarism, Beat and C++/Java | Celery for everything | The outbox makes "saved but never queued" impossible; Beat and the plagiarism batch still need a long-lived worker |
| Code execution | Python/JS: `lambda/exec` sandbox (local thread pool in dev, Lambda in production since 2026-10-05). C++/Java: legacy Celery `run_local` | Docker, vm2, Judge0 | See §5.6 and §6 |
| Primary DB | PostgreSQL | MySQL, MongoDB | ACID transactions — critical for attempt counting |
| Unstructured data | MongoDB | PostgreSQL JSONB | Flexible schema for code blobs and logs |
| Cache + broker | Redis | Memcached, RabbitMQ | Celery broker plus the cache, in one service |
| Plagiarism scoring | TF-IDF + cosine | CodeBERT, MOSS, AST | Fast, no GPU, interpretable at 2k submissions |
| Deployment model | Docker image on Railway: web, Celery worker and relay (deployed by `railway up`; see §5 Railway deploy rules); SQS + Lambda on AWS for the executor | EC2, Fargate | See section 15 for the original cost breakdown |

---

## 4. Data Models

### Core Models (PostgreSQL)

**Terminology (2026-10-06).** A **section** is one class group (Section A–D, one
instructor each). The **cohort** is all sections together. `User.cohort` stores the
student's *section* (seed values `Section A`…`Section D`, renamed from `Batch-A-2025`…
by migration `accounts.0003`); the field and API names stay `cohort`. In the UI:
"Section rank" = rank within the section, "Cohort rank" = rank across all sections
(the leaderboard's "Whole cohort" view). Trainers are not tied to a section: every
trainer sees every student. Plagiarism compares everyone who answered a question,
across sections, and the "Cohort investigation" pages are per exam, across sections.

```
┌──────────────────────────────────────┐
│              User                    │
├──────────────────────────────────────┤
│ id (BigAutoField PK)                 │
│ username, email, password            │
│ role: student | trainer | admin      │
│ cohort: CharField(100)  ← section    │
│                                      │
│ @property score → points from        │
│   passed unique questions, minus     │
│   confirmed plagiarism (metrics)     │
│ @property current_streak → days      │
│   with consecutive submissions       │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│              Exam                    │
├──────────────────────────────────────┤
│ id, title, description               │
│ created_by → FK(User)                │
│ duration_minutes                     │
│ is_active: BooleanField              │
│ start_time, end_time: DateTimeField  │
│   (null = manual control)            │
│ created_at                           │
│                                      │
│ pre_save signal: when is_active      │
│ changes False → queue plagiarism     │
│ batch check                          │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│            Question                  │
├──────────────────────────────────────┤
│ id, exam → FK(Exam)                  │
│ title, description                   │
│ language: python|javascript|java|cpp │
│ difficulty: easy|medium|hard         │
│ tags: CharField (comma-separated)    │
│ max_attempts: PositiveIntegerField   │
│ @property points: easy=10, med=20,   │
│   hard=30                            │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│            TestCase                  │
├──────────────────────────────────────┤
│ question → FK(Question)              │
│ input_data: TextField                │
│ expected_output: TextField           │
│ is_hidden: BooleanField (default=True│
│   hidden = student never sees it)    │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│           Submission                 │
├──────────────────────────────────────┤
│ student → FK(User)                   │
│ exam → FK(Exam)                      │
│ question → FK(Question)              │
│ code: TextField                      │
│ language: CharField(20)              │
│ attempt_number: PositiveIntegerField │
│ status: pending|running|passed|      │
│         failed|error                 │
│ submitted_at: DateTimeField          │
│ time_remaining_seconds               │
│ execution_time_ms                    │
│ plagiarism_score                     │
│ ip_address: GenericIPAddressField    │
│                                      │
│ -- Behavioural signals (from browser)│
│ had_paste_event: BooleanField        │
│ paste_char_count: IntegerField       │
│ time_to_complete_seconds             │
│ tab_switch_count                     │
│                                      │
│ -- Processing status flags           │
│ behavioural_check_done: BooleanField │
│ similarity_check_done: BooleanField  │
│                                      │
│ -- Pre-computed for search           │
│ normalized_code: TextField           │
│   (stored at submission time after   │
│   execution completes)               │
│                                      │
│ @property percent_time_used          │
│   = (total - remaining) / total      │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│              Result                  │
├──────────────────────────────────────┤
│ submission → FK(Submission)          │
│ test_case → FK(TestCase)             │
│ passed: BooleanField                 │
│ actual_output: TextField             │
│ execution_time_ms                    │
│ error_message: TextField             │
└──────────────────────────────────────┘
```

### Plagiarism Models

```
┌──────────────────────────────────────┐
│         BehaviouralFlag              │
├──────────────────────────────────────┤
│ submission → OneToOneField           │
│ risk_score: FloatField (0.0–1.0)     │
│ confidence: low | medium | high      │
│   (confidence flag = misconduct)     │
│   HIGH = 3+ signals (most suspicious)│
│   MED  = 2 signals                   │
│   LOW  = 1 signal (least suspicious) │
│                                      │
│ -- Individual signal scores (0–1.0)  │
│ paste_score                          │
│ time_score                           │
│ snapshot_score  (reused for tab)     │
│ submission_score                     │
│                                      │
│ signals_triggered: JSONField         │
│   human-readable list e.g.:          │
│   ["Pasted 68% of code",             │
│    "Solved hard in 2m 14s"]          │
│                                      │
│ review_status: pending|confirmed|    │
│               dismissed              │
│ review_note: TextField               │
│ reviewed_by → FK(User, null=True)    │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│          PlagiarismFlag              │
├──────────────────────────────────────┤
│ submission_1 → FK(Submission)        │
│ submission_2 → FK(Submission)        │
│ UNIQUE(submission_1, submission_2)   │
│                                      │
│ similarity_score: FloatField         │
│ flagged: BooleanField                │
│ detection_method: CharField          │
│   (auditable — methods evolve)       │
│                                      │
│ review_status: pending|confirmed|    │
│               dismissed              │
│ review_note: TextField               │
│ reviewed_by → FK(User, null=True)    │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│       PlagiarismPolicy (singleton)   │
├──────────────────────────────────────┤
│ paste_weight:       0.40             │
│ time_weight:        0.30             │
│ tab_weight:         0.15             │
│ submission_weight:  0.15             │
│ min_risk_score:     0.20             │
│ similarity_threshold: 0.80           │
│ easy_baseline_s:    90               │
│ medium_baseline_s:  240              │
│ hard_baseline_s:    480              │
│ updated_by, updated_at               │
│                                      │
│ @classmethod get() → get_or_create   │
│   pk=1 (singleton pattern)           │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│          PolicyVersion               │
├──────────────────────────────────────┤
│ changed_by → FK(User, null=True)     │
│ changed_at: DateTimeField(auto_now_  │
│   add=True)                          │
│ change_reason: TextField             │
│ snapshot_before: JSONField           │
│   {field: value, ...} for all 9     │
│   POLICY_FIELDS at time of change   │
│ snapshot_after: JSONField            │
│   full state after the save         │
│                                      │
│ ordering: ['-changed_at']            │
│                                      │
│ Active period of each version:       │
│   from changed_at until the next     │
│   newer version's changed_at         │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│          ReviewAuditLog              │
├──────────────────────────────────────┤
│ flag_type: behavioural | similarity  │
│ flag_id: IntegerField                │
│ action: confirmed | dismissed        │
│ note: TextField                      │
│ reviewed_by → FK(User)               │
│ created_at                           │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│          PlagiarismRun               │
├──────────────────────────────────────┤
│ exam → FK(Exam)                      │
│ triggered_by → FK(User, null=True)   │
│ trigger: exam_close | manual_rerun   │
│ status: running | completed | failed │
│ ran_at: DateTimeField(auto_now_add)  │
│ completed_at: DateTimeField(null)    │
│                                      │
│ -- Policy snapshot at time of run    │
│ policy_snapshot: JSONField           │
│   full copy of all 9 policy fields   │
│                                      │
│ -- Exam performance context          │
│ total_submissions: IntegerField      │
│ unique_students: IntegerField        │
│ pass_rate: FloatField(null)          │
│ avg_execution_ms: FloatField(null)   │
│ avg_solve_time_s: FloatField(null)   │
│ avg_attempts: FloatField(null)       │
│ avg_time_remaining: FloatField(null) │
│                                      │
│ -- Behavioural phase results         │
│ b_flags_total: IntegerField          │
│ b_flags_new: IntegerField            │
│ b_high_confidence: IntegerField      │
│ b_medium_confidence: IntegerField    │
│ b_low_confidence: IntegerField       │
│ b_avg_risk_score: FloatField(null)   │
│                                      │
│ -- Similarity phase results          │
│ s_flags_total: IntegerField          │
│ s_flags_new: IntegerField            │
│ s_pairs_90_plus: IntegerField        │
│ s_pairs_80_90: IntegerField          │
│ s_avg_similarity: FloatField(null)   │
│ questions_total: IntegerField        │
│ questions_done: IntegerField         │
│                                      │
│ ordering: ['-ran_at']                │
└──────────────────────────────────────┘
```

### ExamEnrollment

```
┌──────────────────────────────────────┐
│         ExamEnrollment               │
├──────────────────────────────────────┤
│ exam → FK(Exam)                      │
│ student → FK(User)                   │
│ enrolled_at                          │
│ UNIQUE(exam, student)                │
└──────────────────────────────────────┘
```

---

## 5. Submission Pipeline — The Core Flow

This is the end-to-end journey of a single code submission from browser to result.

**Status: live since 2026-10-05.** Production grades Python and JavaScript through outbox → relay (Railway) → SQS `codemas-exec` → Lambda `codemas-exec` (arm64, ap-southeast-1), switched on by `PIPELINE_LANGUAGES=python,javascript` on Railway backend. The Lambda holds no signing secret and authenticates with per-job tokens; the secret was rotated at cutover. The go-live smoke test graded Python and JS through the pipeline and found no `JOB_SIGNING_SECRET`; R2 (role credentials readable) and R1 (egress open) are still present, as accepted (§5.6). Locally the same code runs with `JOB_TRANSPORT=local`.
- Python and JavaScript use the job pipeline below.
- C++ and Java still use the legacy Celery task. The path is chosen per language by `PIPELINE_LANGUAGES`.

> **Railway deploy rules (critical).** The Railway services (backend, worker, frontend, relay) are deployed by `railway up` only; they were disconnected from GitHub on 2026-10-05 after a variable change twice redeployed the old pre-pipeline commit (`902417d`) over the live upload. Any variable change: `railway variable set KEY=VALUE -s <service> --skip-deploys`, then `railway up -s <service> --detach`, from the repo root (no `--path-as-root`, no `railway redeploy`). Check: `railway deployment list -s <svc> --json`, whose active deployment's `meta` must have `cliMessage`, not `commitHash`. Details: `deploy/aws/README.md`.

Related docs: `docs/dev-pipeline.md` (run it locally), `docs/demo-runbook.md` (demo and failure answers), `submission_animation.html` (step-through diagram) and `submission_flow.html` (the code at each step).

```
BROWSER            DJANGO                 POSTGRES          RELAY             SQS / LOCAL        LAMBDA codemas-exec
  │ POST /api/submissions/create/           │                 │                  │                    │
  │──────────────────►│ one transaction:     │                 │                  │                    │
  │                   │ lock User row,       │                 │                  │                    │
  │                   │ count attempts,      │                 │                  │                    │
  │                   │ INSERT submission ──►│                 │                  │                    │
  │                   │ INSERT jobs_job  ───►│ (pending)       │                  │                    │
  │◄── 201 {id} ──────│                      │                 │                  │                    │
  │                   │                      │◄─ SKIP LOCKED ──│ every 0.5 s      │                    │
  │                   │                      │                 │─ {job_id,token}─►│                    │
  │                   │                      │◄─ queued ───────│                  │── trigger ────────►│
  │                   │◄────────────── POST /internal/jobs/claim/ {job_id, token} ─────────────────────│
  │                   │ lease 150 s ────────►│ (running)       │                  │                    │
  │                   │──────────── code + test inputs + limits + lease_token ───────────────────────►│
  │                   │                      │                 │                  │     sandbox runs   │
  │                   │◄────────────── POST /internal/jobs/complete/ (token, outputs) ─────────────────│
  │                   │ grade, Result rows ─►│ (succeeded)     │                  │                    │
  │ GET /api/submissions/<id>/status/  (1 s → 2 s → 3 s, 10 s after 2 min)                             │
  │──────────────────►│                      │                 │                  │                    │
  │◄── passed/failed ─│  then GET /api/results/<id>/           │                  │                    │
```

### 5.1 The outbox: `jobs.Job` (`backend/jobs/models.py`, table `jobs_job`)

| Field | Meaning |
|---|---|
| `id` (UUID) | The only thing a queue message carries |
| `kind` | `execute_submission` |
| `subject_id` | The submission id |
| `status` | `pending` → `queued` → `running` → `succeeded`; also `failed` (subject deleted) and `dead` (out of attempts) |
| `attempt` | Claims so far. The limit is `MAX_ATTEMPTS = 3` |
| `lease_token`, `lease_expires_at` | Who may finish the job, and until when |
| `published_at`, `started_at`, `finished_at`, `created_at`, `updated_at` | Timestamps (`queued_at` in the status API is `published_at`) |
| `last_error` | Handler error first, then relay/sweep notes, one per line, capped at 2000 chars |

A partial unique index (`one_active_job_per_subject`) allows only one `pending`/`queued`/`running` job per (`kind`, `subject_id`). The status poll (`filter(kind=, subject_id=)`, no status predicate) can't use it, so a plain index `jobs_job_subject_idx` on (`subject_id`, `kind`) backs that lookup (migration `jobs/0002`). Django admin shows the table read-only at `/admin/jobs/job/`, filterable by status.

`jobs.services.enqueue()` raises unless it runs inside `transaction.atomic()`. The submission and its job commit together or not at all, and nothing is published until the commit.

### 5.1b Exam page basics (2026-10-06)

- **Languages:** JavaScript (default) and Python only; `SubmissionCreateSerializer` rejects anything else with 400.
- **Starter code (HackerRank-style):** `Question.starter_code_javascript` / `starter_code_python` read stdin in the question's input format and call one function the student completes. Empty = the generic starter in `exams/starter_code.py` (every input line handed to `solve(lines)`). The API exposes `starter_code` (with the fallback) and accepts the raw fields on create; the AI exam generator writes both. The editor opens with the starter when there is no saved draft and swaps it on a language change if the code is untouched. `manage.py apply_starter_code` fills the demo exam's questions (by title) where empty.
- **Submit exam** (finish early): `POST /api/exams/{id}/finish/` sets `ExamEnrollment.finished_at`; after that the create path returns 403 "You have already submitted this exam.", the exam page sends the student to My results, and the exam list shows "Submitted". `reset_exam_attempts` also clears `finished_at` for the named students.

### 5.2 Create path (`SubmissionCreateView`)

Students can only submit while the exam is open (`is_active` and now inside `[start_time, end_time)`, a null bound is unbounded, the same rule `auto_manage_exams` uses); otherwise 403 ("This exam has ended." / "hasn't started yet" / "isn't open") before the transaction, and nothing is created. Students must be enrolled in the exam to see or submit to it. Before the transaction, an unenrolled student gets 403 `{"error": "You're not enrolled in this exam."}` and nothing is created; the exam list shows a student only active exams they are enrolled in, and exam detail/questions return 404 for an unenrolled student.

In one transaction:
1. Lock the student's `User` row (`select_for_update`). Concurrent submits from the same student queue up here.
2. Count this question's submissions, **excluding `status='error'`**. A dead job, or a question with no tests, never costs the student an attempt. If the count is already at `PlagiarismPolicy.max_attempts`, return 403.
3. `attempt_number = max(existing) + 1`. A second concurrent submit from the same student waits on the lock, then counts the first: it becomes the next attempt, or gets 403 at the limit. A unique constraint on (`student`, `question`, `attempt_number`) is the backstop for any writer outside the lock, and a violation returns 409 ("try again").
4. Save the submission as `pending`. If the language is in `PIPELINE_LANGUAGES`, write the job row with `enqueue()`. Otherwise, hand it to `execute_submission.delay()` on commit (legacy Celery).

### 5.3 Relay: `manage.py run_relay` (`backend/jobs/relay.py`)

- **Tick, every `RELAY_INTERVAL_S` (0.5 s).** Select up to 50 `pending` jobs, oldest first, `FOR UPDATE SKIP LOCKED`, and call `transport.publish_many()`. Only jobs the transport accepted become `queued` with `published_at`. The rest stay `pending` with `publish failed: …` in `last_error`. A crash between sending and marking can publish a job twice; that is harmless because claiming is idempotent.
- **Sweep, every 60 s.** It depends on the transport, so Postgres and the SQS dead-letter queue agree on what is dead.

| | Local transport | SQS transport |
|---|---|---|
| `running`, lease expired, `attempt` < 3 | Back to `pending` | Left to SQS redelivery (claim accepts an expired lease). Backstop: back to `pending` once the lease expired more than 30 min ago |
| `running`, lease expired, `attempt` ≥ 3 | `dead`; submission → `error` | Same |
| `queued` with no claim | Back to `pending` after 10 min | Back to `pending` after 30 min (longer than SQS's own 3 × 540 s ≈ 27 min of retries) |

`--once` runs one tick and one sweep, waits for local handler threads, and exits.

### 5.4 Transports (`JOB_TRANSPORT`, `backend/jobs/transports.py`)

Both send only `{"job_id": "<uuid>", "kind": "execute_submission", "token": "<hex>"}`. The token is `HMAC-SHA256(JOB_SIGNING_SECRET, "job:" + job_id)`, minted by the relay (trusted, on Railway); the executor never holds the secret.

- **`local`** (laptops and tests; the built default). The relay loads `lambda/exec/handler.py` and calls `handler(event, None)` in a 4-thread pool, with an SQS-shaped event. It emulates SQS redelivery: up to 3 deliveries, with 2 s and 5 s backoff. With no Lambda context there is no time-budget guard.
- **`sqs`** (production, live since 2026-10-05). `send_message_batch` to `codemas-exec`, 10 per call, with message attributes `job_id` and `language`. The botocore client has connect 3 s / read 5 s timeouts and 3 attempts, because the relay holds its row locks while publishing. A failed chunk leaves the rest of the batch `pending` for the next tick.
- Any other value raises `ImproperlyConfigured`. There is no silent fallback that would run student code on the web host.

AWS side (live since 2026-10-05):
- One queue, `codemas-exec`, with DLQ `codemas-exec-dlq` (`maxReceiveCount` 3) and a visibility timeout of 540 s.
- One function, `codemas-exec`: a Python 3.12 zip plus the `codemas-node22` Node 22 layer, on **arm64 (Graviton)**, with a 90 s timeout. The only configured variable is `CODEMAS_API_URL` (plus a pinned `PATH`): no secret. Lambda also injects the execution role's temporary AWS credentials into the environment, and student code can read them (accepted risk R2, §5.6).

### 5.5 Internal API (`/internal/jobs/…`, `backend/jobs/views.py`)

Every request carries the **per-job token** from the SQS message in its JSON body:
- Django recomputes `HMAC-SHA256(JOB_SIGNING_SECRET, "job:" + job_id)` and compares with `hmac.compare_digest`. A wrong or missing token gets 401. A malformed body or a non-UUID `job_id` gets 400.
- `complete` and `fail` also need the `lease_token` that claim returned, so a stale run can't overwrite a newer one.
- A token works only for its own job. There is no request signing (`X-Timestamp`/`X-Signature` were removed on 2026-10-04: they needed the secret inside the Lambda).
- User sessions and JWTs are not accepted.
- `JOB_SIGNING_SECRET` lives on web and relay only. With `DEBUG` off, an empty, default (`dev-only-change-me`) or shorter-than-32-character secret fails system check `jobs.E001`, so `migrate` (web start) and `run_relay` refuse to run; a process started with `--skip-checks` still answers 503 on every internal endpoint.
- The handler sends UTF-8 JSON (`ensure_ascii=False`) and keeps the `complete` body under 2,000,000 bytes, below Django's 2.5 MB `DATA_UPLOAD_MAX_MEMORY_SIZE`: while it is larger, the cap for every output and error is halved alike, with an `[output truncated]` marker. The handler never sees expected outputs, so it can't spare a correct one: a correct output is lost only when the whole body exceeds ~2 MB (about 30+ tests near the 64 KB cap), a documented limit. Huge student output is therefore graded, never a 400 that ends as a dead job.

| Endpoint | Behaviour |
|---|---|
| `POST claim/ {job_id, token}` | One locked read (`select_for_update`) decides every outcome. Terminal job → 409 `done`. Live lease → 409 `busy`. Subject deleted → job `failed`, 410 `gone`. `attempt` already 3 → job `dead`, submission `error`, 410 `dead`. Otherwise: `running`, new `lease_token`, `lease_expires_at = now + JOB_LEASE_SECONDS` (150 s, longer than the 90 s function timeout), `attempt += 1`, submission `running`. Returns the lease token plus `submission_id`, `language`, `code`, `tests [{id, input}]` (**no expected outputs**: they never leave Django) and `limits` (`timeout_s` 10, `python_memory_mb` 256, `node_heap_mb` 192, `output_kb` 64). |
| `POST complete/ {job_id, token, lease_token, results}` | One transaction. The lease token must match a `running` job, or 409 `stale` and nothing is written. Django grades, with the legacy pass rule `output.strip() == expected.strip()`. It writes `Result` rows (`update_or_create`) and sets the submission to `passed`/`failed`. A question with no tests becomes `error`, never a pass. The job becomes `succeeded`. On commit, `after_grading()` runs the legacy side effects: normalise the code, `notify_result_ready`, and queue the Celery rubric task, plus the hint task if the answer failed. |
| `POST fail/ {job_id, token, lease_token, error}` | The handler gave up (an infrastructure problem). Release the lease and put the job back to **`pending`**, so the relay republishes it on the next tick in either transport. The attempt still counts. |

### 5.6 Executor: `lambda/exec/handler.py` + `sandbox.py`

Standard library only. No database credentials, no shared secret, no expected outputs. The same file runs on Lambda and inside the local transport.

For each record, the handler:
1. **Checks its time.** If less than 30 s of Lambda time is left, it doesn't claim, because a claim would spend an attempt. Instead it returns the record in `batchItemFailures`. The message comes back after the 540 s visibility timeout, and the skip spends one receive toward the DLQ.
2. **Claims** with the message's `job_id` and `token`. `done`, `gone` and `dead` are acknowledged. Anything else, including `busy`, is reported in `batchItemFailures` so SQS retries it.
3. **Runs the tests in order.** After the **first student timeout** the remaining tests are reported "Not run". The grade is already decided, so they don't each burn 10 s. If the **Lambda's own time** runs out before any student timeout, the handler raises `BudgetExhausted` and calls `/fail/`. That is an infrastructure limit, never a failing grade. Any other grader exception also goes to `/fail/`.
4. **Acknowledges after a successful `/fail/`.** Once the job is `pending`, the relay owns the retry, and an SQS retry on top would only push the message toward the DLQ. If `/fail/` itself fails, the message is reported for retry.
5. **Completes,** then logs one JSON line: `job_id`, `submission_id`, `language`, `tests`, `submission_status`, `complete` (HTTP status) and `duration_ms`. A 409 `stale` on complete is acknowledged.

**Sandbox (`sandbox.py`), per test.**
- **Process.** `subprocess.Popen` with no shell, `env={}` and a fresh temp working directory. Python runs `python -I main.py`; JavaScript runs `node --max-old-space-size=192 main.js`.
- **Session and limits.** The child gets its own session (`start_new_session`). `preexec_fn` sets these rlimits:
  - CPU = `timeout_s`
  - file size 1 MB
  - address space 256 MB (Python only)
  - 32 processes (Linux)
  - If running as root, it drops to `nobody`.
- **Timeout and output.** A 10 s wall-clock timeout, then `killpg(SIGKILL)` on the whole group, which always runs. stdout and stderr are each read through a 64 KB-capped buffer.
- **No network where the kernel allows it (Linux; not real Lambda).** Last in `preexec_fn`, the child sets `PR_SET_NO_NEW_PRIVS` and installs a seccomp-BPF filter (x86_64 and aarch64). The filter is proven natively on arm64 (aarch64), the architecture the Lambda runs on; the x86_64 branch is a fallback, checked only by the BPF-interpreter test. `socket()` is allowed for `AF_UNIX` only; every other family, including `AF_INET`/`AF_INET6`, gets `EACCES`. `io_uring_setup` gets `EPERM`, and any non-native syscall ABI (x32, i386, arm32) kills the process. It fails open if the kernel refuses the filter. The handler logs `{"event": "sandbox_selfcheck", "egress_blocked": …}` at each cold start, and the smoke test's egress probe checks it on real Lambda. **Real Lambda refuses it** (`egress_blocked=false`): accepted risk R1 below.
- **Grader protection.** At import, the handler calls `prctl(PR_SET_DUMPABLE, 0)`, so student code can't read the grader's own `/proc/<ppid>/environ` or `/proc/<ppid>/mem`. On real Lambda that is not enough: another runtime process (`/proc/2/environ`) still exposes the role's AWS credentials (R2 below). There is no secret left to steal there: the grader holds only the current job's token.
- **Between runs on Lambda** (`AWS_LAMBDA_FUNCTION_NAME` set) **or with `CODEMAS_EXEC_SCRUB=1`:** the whole temp dir is wiped, including directories the student locked with `chmod`. Every same-uid process started after the grader is SIGKILLed, which catches `setsid()` escapees. This is off elsewhere, because on a developer's machine it would kill their processes.

**Security model: one Lambda, guardrails, known limits** (decided 2026-10-04 after the first production smoke test; spec `docs/superpowers/specs/2026-10-04-lambda-guardrails.md`). One Lambda; the handler runs student code in a constrained child process. Guardrails: no secrets or answers in the Lambda, per-job tokens. Known limits, **accepted, not fixed**:
- **R1, egress.** Real Lambda refuses the seccomp filter (`egress_blocked=false`; smoke probe `EGRESS_OPEN`), so student code can open internet connections. Abuse is bounded by CPU time per test, maximum concurrency 5, 3 attempts per question and the submission throttle.
- **R2, role credentials.** Lambda always injects the role's credentials, and student code can read them. The trigger role can `sqs:ReceiveMessage`, `sqs:DeleteMessage` and `sqs:ChangeMessageVisibility` on `codemas-exec`. So a determined student with a working solution could take a classmate's queued message (job id and token), claim that job first, read the classmate's code and test inputs, and post outputs that forge a pass or a fail; the classmate's real delivery then gets 409 `done`, so nothing looks wrong. They can also delete or hide queued messages, delaying other students' grading until the 30-minute sweep. Exposure is highest under an exam-deadline backlog (concurrency 5), when every queued message waits longest.
- What still holds: the signing secret and the expected answers never enter the Lambda, and a student can't pass their own submission without correct output.
- There is no kernel boundary between grader and child (the whole function shares one Firecracker microVM).

The real fix for R1 and R2 is future work: the two-function split, the standard pattern for online judges. A runner with a zero-permission role, in a VPC with no NAT or internet gateway and a security group with no outbound rules, is invoked by the grader, which reads its return value.

### 5.7 Status endpoint and polling

`GET /api/submissions/<id>/status/` (owner or trainer) returns `{id, status, results_ready, job: {status, attempt, queued_at, started_at, finished_at} | null}`. `job` is `null` on the legacy Celery path. The browser uses this for every language: the exam page no longer opens an SSE stream.

`ExamTakeView` polling:
- Poll at once, then every 1 s for 5 polls, every 2 s for 2 polls, then every 3 s. After 2 minutes, every 10 s.
- The submission id is kept per question in `sessionStorage`, so polling resumes after a refresh.
- The tracker (Submit → Queue → Execute → Grade → Feedback) **never moves backwards**. A `/fail/` sends the job from `running` back to `pending`, but the student keeps seeing the furthest stage reached.
- "Retrying…" shows when `job.attempt` says this is not the first claim. "Taking longer than usual…" shows after 10 s.
- A `dead` job ends the run with "couldn't grade … doesn't count as an attempt". On `passed`/`failed`, the page fetches `GET /api/results/<id>/`.

### 5.8 Failure handling

| Failure | What happens |
|---|---|
| Commit fails | Neither the submission nor the job exists; the student sees an error and the attempt isn't used |
| Relay down | Jobs wait as `pending` and publish on the first tick after restart. The UI shows "Waiting in line", then "Taking longer than usual…" |
| Queue unreachable | Publish fails; the job stays `pending` with `publish failed: …` and is retried every tick |
| Duplicate delivery | The second claim gets 409 `done` (acknowledged) or `busy` (retried). Only the lease holder can complete |
| Grader error, or Lambda out of time before any student timeout | `/fail/` puts the job back to `pending` and the relay republishes it on the next tick. The message is acknowledged. The attempt counts |
| Crash or Lambda timeout (no `/fail/`) | **SQS:** the message reappears after the 540 s visibility timeout (about 9 minutes) and the expired lease is reclaimed with a new token. A late `complete` with the old token gets 409. **Local:** redelivery after 2 s and 5 s, then the sweep requeues the expired lease |
| Three attempts used | The next claim (410), or the sweep for an expired lease at the limit, marks the job `dead` and the submission `error`. That submission doesn't count against the student's attempts |
| Wrong answer, runtime error, student timeout | A normal `succeeded` job with a failing grade. Never retried |

**Dead-letter queue semantics.** `codemas-exec-dlq` holds messages whose delivery wasn't acknowledged 3 times. A delivery is left unacknowledged (reported in `batchItemFailures`, or the invocation died) when:
- the invocation crashed or timed out;
- Django was unreachable;
- the claim got anything other than `done`, `gone` or `dead`. That includes `busy`, 401, 404 and 5xx;
- the `/fail/` call itself failed;
- `complete` answered with anything other than 200 or 409;
- less than 30 s of Lambda time was left, so it skipped the claim.

A job released through `/fail/` dies in Postgres with no message in the DLQ. A message can also reach the DLQ without its job dying, because deliveries that never claimed don't spend attempts. The SQS-mode sweep backstop republishes those jobs after 30 minutes.

### 5.9 What stays on Celery

- C++ and Java execution: the legacy `execution.tasks.execute_submission`. **Since 2026-10-06 students can't pick them:** the exam offers JavaScript (default) and Python only, and `SubmissionCreateSerializer` rejects any other language with 400, so this unsandboxed path is reachable only for Python/JS during a `PIPELINE_LANGUAGES=""` rollback. The task runs them with `run_local` **on the Celery worker host with no sandbox**: it strips the environment, applies a 10 s timeout, and drops to `nobody` when running as root, and nothing else. Its docstring marks it development only.
- AI rubric feedback and hints, queued from `after_grading()`.
- Plagiarism (Phase 1 and 2) and the Celery Beat schedules.

`PIPELINE_LANGUAGES=""` sends every language back to Celery with no code change. In production: `railway variable set "PIPELINE_LANGUAGES=" -s backend --skip-deploys && railway up -s backend --detach`. Set it empty, never delete it: unset, it defaults to `python,javascript`.

### Attempt Limiting — Row Lock + Unique Constraint

The race to prevent: two simultaneous submits both count 2 attempts and both create a 3rd.

- **The fix is in Postgres, not a cache.** The create transaction locks the student's `User` row before counting, so a second request for the same student waits until the first commits, then counts it.
- **A database invariant backs it.** The unique constraint on (`student`, `question`, `attempt_number`) holds even if the lock were bypassed; the loser gets 409.
- **Ungradable runs are refunded by the count itself.** Submissions in `error` (dead job, or no test cases) are excluded from the count, so no refund bookkeeping is needed. `attempt_number` keeps increasing (it is `max + 1`), so the constraint never collides with an excluded row.

### Rate Limiting (DRF Throttle)

Beyond per-question attempt limits, the submission endpoint has its own rate throttle:

```python
class SubmissionThrottle(UserRateThrottle):
    scope = 'submissions'  # maps to 30/hour in DEFAULT_THROTTLE_RATES
```

General API: 2000/hour. Anonymous: 20/hour. Submissions specifically: 30/hour. This prevents burst abuse at the API level before even reaching the attempt logic.

---

## 6. Execution Engine — Docker Sandbox

> **Status (October 2026):** this section is the original execution design. Python and JavaScript now run through the job pipeline's executor (`lambda/exec`, process-level sandboxing, §5.6). Locally, the relay runs that handler code itself. In production, Python and JavaScript have run on Lambda (stack `codemas-pipeline`, ap-southeast-1) since 2026-10-05, with `PIPELINE_LANGUAGES=python,javascript`. C++ and Java still go through the legacy Celery task, which executes with `run_local`, a development-only subprocess executor with no sandbox. The Docker container settings below are not what runs today.

### Why Not the Alternatives

#### vm2 (JavaScript sandbox)
- Rejected. JavaScript cannot safely sandbox JavaScript. An unfixable escape was found in 2023 and the library was deprecated by its own maintainers. Running arbitrary student code in the same Node.js process as the backend is not an option.

#### Judge0
- Rejected. It is an external API dependency during a live exam. Any outage of Judge0 would immediately fail all student submissions — unacceptable for a high-stakes exam scenario.
- Additionally, Judge0 had 3 CVEs published in April 2024: symlink attacks and SSRF vulnerabilities that could be used to steal AWS credentials. Using it would mean accepting someone else's security patch timeline during live exams.

#### AWS Lambda (seriously evaluated)
- Lambda was evaluated seriously. The free tier covers 5.2 million invocations/month — which would make execution essentially free.
- **Why Lambda was not chosen:** SSE needs a persistent connection that Lambda cannot hold (Lambda invocations are stateless and terminate). Celery Beat (the auto-close scheduler) needs an always-running process. Cold start time for Lambda is 8–15 seconds vs Docker's ~500ms warm start — over the 10-second SLA for results. A Lambda migration would require replacing Celery with SQS, Celery Beat with EventBridge, and SSE with API Gateway WebSockets — a complete rewrite for $0.29/month savings. Not worth it at this scale.

- **Revisited (October 2026):** Python and JavaScript execution moved to a Lambda-shaped executor after all, without the rewrite listed above. The same handler code runs locally inside the relay, and on Lambda in production (live since 2026-10-05, `PIPELINE_LANGUAGES=python,javascript`). The browser polls a status endpoint instead of holding SSE, Celery Beat stays on Celery, and a transactional outbox plus relay feeds the queue. See §5.

#### Docker — Chosen
Works on Mac (local development), portable to any Linux host, uses kernel namespaces and cgroups for isolation, explicit deny-everything security posture.

### Security Constraints (every container)

```
docker run
  --memory=128m         # mem_limit in docker-py
  --cpus=0.5            # nano_cpus=500_000_000
  --network=none        # network_disabled=True — cannot call home
  --pids-limit=10       # prevents fork bombs
  --read-only           # read-only filesystem — no writing to disk
  --user nobody         # non-root user — cannot escalate
  --rm                  # auto-remove after exit — no container persistence
  [5s timeout]          # killed with SIGKILL after 5 seconds
```

### Language Configuration

```python
language_config = {
    'python': {
        'image': 'python:3.11-alpine',
        'command': ['python3', '-c', wrapped_python]
    },
    'javascript': {
        'image': 'node:18-alpine',
        'command': ['node', '-e', wrapped_js]
    },
    'java': {
        'image': 'openjdk:17-slim',
        'command': ['sh', '-c', java_cmd]
    },
    'cpp': {
        'image': 'gcc:12',
        'command': ['sh', '-c', cpp_cmd]
    },
}
```

### Two-File Pattern

For Python and JavaScript, input is injected directly:

```python
# Python wrapper — stdin injected before student code
wrapped_python = f"import sys, io\nsys.stdin = io.StringIO({repr(input_data + chr(10))})\n{code}"

# JavaScript wrapper — stdin piped before student code  
wrapped_js = f"process.stdin.push({repr(input_data + chr(10))});\nprocess.stdin.push(null);\n{code}"
```

For compiled languages (Java, C++), the pattern is: write source to `/tmp`, compile, pipe input, execute.

The student never sees the test case inputs that the container runs against — only `is_hidden=False` test cases are exposed in the UI. The runner (judge) is fully server-side.

Hidden test data never reaches a student from any endpoint: for non-staff viewers, exam detail/list/questions send a hidden test only as an `{id, is_hidden: true}` stub (so the test count stays right), `/api/results/<id>/` nulls its `test_case_input`/`test_case_expected`, and the AI hint prompt omits it.

### Lambda Executor (built; replaces the old stub)

`run_in_lambda()` and the commented-out switch in `execution/tasks.py` are gone. The executor is now `lambda/exec/` (`handler.py` and `sandbox.py`, standard library only). It is reached through the job pipeline (outbox → relay → SQS → Lambda), not by a synchronous invoke from a Celery task. The design is in §5.4 to §5.6.

### Container Cost Formula

Cost is tracked per submission using Fargate pricing as the model:

```
cost = hours × vCPU × $0.04048/hr
     + hours × GB   × $0.004445/hr

where hours = (exec_ms + cold_start_ms) / 3_600_000
      vCPU = 0.5  (matches --cpus=0.5)
      GB = 0.125  (matches --memory=128m)
      cold_start_ms = 10,000  (realistic Fargate task init)
```

---

## 7. Real-Time Result Delivery — SSE

> **Status (October 2026):** the exam page no longer opens an SSE stream. It polls `GET /api/submissions/<id>/status/` for every language (§5.7). `submissions/sse.py`, its `/stream/` route and the legacy Celery task's Redis publish have been removed (nothing published to the channel for pipeline submissions, so an open stream held a web thread forever). This section describes the earlier design.

### Why SSE and not WebSockets

WebSockets are bidirectional. Result delivery is strictly server-to-client. SSE (Server-Sent Events) is the correct tool when you only need one direction. It works over standard HTTP, requires no handshake protocol, needs no library, and reconnects automatically on drop.

### SSE vs Polling Comparison

| Aspect | SSE | Long Polling | Short Polling |
|---|---|---|---|
| Direction | Server→Client | Server→Client | Server→Client |
| Connection overhead | One HTTP connection per stream | New connection per poll cycle | New connection per N seconds |
| Latency | Event-driven, immediate | Up to poll cycle latency | Up to interval latency |
| Server load at 2000 students | 2000 open connections | 2000 × (polls/min) requests | 2000 × (1/interval) req/s |
| Reconnect on drop | Automatic via Last-Event-ID | Manual | Not applicable |
| Implementation | Django StreamingHttpResponse | Standard HTTP | Standard HTTP |

### Implementation — Server Side

```python
# submissions/sse.py

def event_stream():
    r = redis.Redis.from_url(os.environ.get('REDIS_URL'))
    pubsub = r.pubsub()
    channel = f"submission:{submission_id}"
    pubsub.subscribe(channel)

    # immediately send "waiting" to confirm stream is open
    yield f"data: {json.dumps({'status': 'waiting'})}\n\n"

    for message in pubsub.listen():
        if message['type'] == 'message':
            yield f"data: {message['data'].decode('utf-8')}\n\n"
            break  # one message is enough — result is final

    pubsub.unsubscribe(channel)

response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
response['Cache-Control'] = 'no-cache'
response['X-Accel-Buffering'] = 'no'  # disable nginx buffering — critical
```

### Implementation — Client Side (Vue)

```typescript
// ExamTakeView.vue

function listenForResult(submissionId: number): void {
    const token = localStorage.getItem('access_token')
    
    // SSE (EventSource) does not support custom headers
    // JWT must be passed as query param
    eventSource = new EventSource(
        `http://localhost:8000/api/submissions/${submissionId}/stream/?token=${token}`
    )

    eventSource.onmessage = async (event) => {
        const data = JSON.parse(event.data)
        submissionStatus.value = data.status

        if (data.status === 'passed' || data.status === 'failed') {
            // fetch full per-test-case results now that execution is done
            const resultsRes = await api.get(`/results/?submission=${submissionId}`)
            results.value = resultsRes.data
            eventSource?.close()
        }
    }
}
```

### SSE Auth — The Token-in-Query-Param Problem

`EventSource` is a browser API. It does not support custom headers. The standard way to authenticate SSE is to pass the JWT as a query parameter: `?token={jwt}`. Django's SSE view reads this from `request.GET.get('token')` before falling back to the `Authorization` header. This is a deliberate design choice, not a security gap — the token is validated identically.

### The Full SSE Flow

```
BROWSER                  DJANGO (SSE endpoint)         CELERY WORKER         REDIS
  │                              │                            │                  │
  │ GET /stream/?token={jwt}     │                            │                  │
  ├─────────────────────────────►│                            │                  │
  │                              │ subscribe(submission:{id}) │                  │
  │                              ├───────────────────────────────────────────►  │
  │                              │                            │                  │
  │ data: {"status":"waiting"}   │                            │                  │
  │◄─────────────────────────────┤                            │                  │
  │                              │                            │                  │
  │          (waiting...)        │                   (Docker runs...)            │
  │                              │                            │                  │
  │                              │              publish(submission:{id},         │
  │                              │              {"status":"passed"})             │
  │                              │                            ├─────────────────►│
  │                              │                            │                  │
  │                              │◄───────────────────────────────────────────── │
  │                              │ message received on channel                   │
  │                              │                            │                  │
  │ data: {"status":"passed"}    │                            │                  │
  │◄─────────────────────────────┤                            │                  │
  │                              │ unsubscribe, stream closes │                  │
  │                              │                            │                  │
  │ GET /results/?sub={id}       │                            │                  │
  ├─────────────────────────────►│                            │                  │
  │◄─────────────────────────────┤                            │                  │
  │ per-test-case results        │                            │                  │
```

### Replay on Refresh (Last-Event-ID)

If a student refreshes during execution, the browser automatically sends `Last-Event-ID` in the reconnect request. The result is cached in Redis with a 1-hour TTL, so if execution has already completed, the status is returned immediately without waiting.

---

## 8. Plagiarism Detection System

This is the most technically sophisticated feature and the one most worth discussing in depth.

### The Core Problem

Naive all-pairs comparison: every submission against every other submission. At 10,000 students, that is 10,000² / 2 = **50 million comparisons**. Running TF-IDF and cosine similarity 50 million times is not feasible on exam close.

The solution: a two-layer filter that cuts the real work to O(K×N) where K is a small subset of suspected students.

### Layer 1 — Behavioural Scoring (O(N) per exam, runs at exam close)

Runs post-exam in batch. Called synchronously (not via `.delay()`) inside `run_exam_plagiarism_check` for every submission before Phase 2 is queued. Does not compare against other students — looks only at each student's own signals.

**Why post-exam, not per-submission:** All submission data is final, cross-question patterns are visible, no false positives from partial data, and there is no actionable surface for trainers mid-exam. Running synchronously inside the batch task guarantees Phase 1 records exist before Phase 2 queries them.

```
EXAM CLOSES → run_exam_plagiarism_check starts
         │
         ▼
    for each submission in exam:
        run_behavioural_check(sub.id)  ← direct call, not .delay()
         │
         ├─► paste_signal()
         │     paste_ratio = paste_char_count / len(code)
         │     ≥ 0.70 → 1.0   (weight: 0.40)
         │     ≥ 0.50 → 0.7
         │     ≥ 0.30 → 0.3
         │     < 0.30 → 0.0
         │
         ├─► time_signal()
         │     ratio = elapsed / DIFFICULTY_BASELINE
         │     baselines: policy.easy_baseline_s / medium / hard  (defaults: 90s / 240s / 480s)
         │     ≤ 0.20 → 1.0   (weight: policy.time_weight, default 0.30)
         │     ≤ 0.40 → 0.7
         │     ≤ 0.60 → 0.3
         │     > 0.60 → 0.0
         │
         ├─► tab_switch_signal()
         │     ≥ 5 switches → 1.0   (weight: policy.tab_weight, default 0.15)
         │     ≥ 3 switches → 0.5
         │     ≥ 1 switch   → 0.2
         │     0 switches   → 0.0
         │
         └─► submission_surprise_signal()
               compare current code vs previous attempt
               using SequenceMatcher.ratio()
               if ratio < 0.25 AND status == 'passed' → 1.0  (weight: policy.submission_weight, default 0.15)
               if ratio < 0.40 → 0.6
               if ratio < 0.55 → 0.2

         policy = get_policy()  # Redis cache hit (60s TTL); falls back to DB on miss
         risk_score = policy.paste_weight*paste + policy.time_weight*time
                    + policy.tab_weight*tab   + policy.submission_weight*surprise

         signals_fired = count(score > 0 for each signal)
         confidence = HIGH (3+ signals — most suspicious) | MEDIUM (2) | LOW (1 — least suspicious)
         # flag confidence = confidence that the flag indicates misconduct

         if risk_score > policy.min_risk_score:  # default 0.20
             BehaviouralFlag.objects.update_or_create(...)
         
         Submission.behavioural_check_done = True
```

**Why default weights are set this way:**
- Paste (0.40): most direct evidence. If 70% of your code arrived via paste, that is hard to misinterpret.
- Time (0.30): strong signal. A hard problem solved in 18 seconds is statistically impossible for genuine work.
- Tab switch (0.15): corroborating evidence only. 1-2 switches is normal (documentation). 5+ is suspicious.
- Submission surprise (0.15): useful context, but only applies when a prior attempt exists (attempt 1 has nothing to compare against).

All weights and thresholds are runtime-configurable via the `PlagiarismPolicy` singleton. Trainers adjust them from the Detection Policy UI without redeploying. The policy is cached in Redis (60s TTL); a PUT to `/api/plagiarism/policy/` saves to Postgres and immediately calls `cache.delete('plagiarism_policy')` so the next task picks up fresh values.

**Why min_risk_score threshold (default 0.20) to store:**
Storing every clean submission wastes database space and creates noise in the trainer UI. Only store when there is something to review. Trainers can lower this threshold to catch more borderline cases or raise it to reduce false positives.

### Layer 2 — Targeted Cross-Comparison (O(K×N), runs at exam close)

```
EXAM CLOSES (manual or auto-close via Celery Beat)
         │
         ▼
    Exam.pre_save signal fires
         │
         ▼
    run_exam_plagiarism_check.delay(exam_id)
         │
         ▼
    Phase 1 (synchronous loop — runs before queuing Phase 2):
    for each submission in exam:
        run_behavioural_check(sub.id)  ← direct call, not .delay()
    → BehaviouralFlag records now exist for all submissions
         │
         ▼
    Phase 2 (queued per question, staggered):
    for each question in exam:
        run_question_plagiarism_check.apply_async(
            args=[question_id],
            countdown=i * 30  ← staggered to avoid CPU spike
        )
```

```
run_question_plagiarism_check(question_id):
         │
         ▼
    Query HIGH flag confidence suspects (Phase 1 data must exist first):
    # 'high' = 3+ signals fired = most likely misconduct
    high_risk_ids = BehaviouralFlag
                    .filter(question=q, confidence='high')
                    .values_list('submission__student_id')

         │
         ▼
    Phase 2: Pull best submission for EVERY student
    (passed attempt if exists, else latest attempt)
    → all_subs list (N items, one per student: the DISTINCT student query
      clears Submission's default -submitted_at ordering, otherwise a
      multi-attempt student appears once per attempt and pairs with themselves)

         │
         ▼
    Phase 3: AST-normalize all N submissions
    normalize_code(sub.code, sub.language)
    → strip variable names → VAR_0, VAR_1...
    → strip comments, docstrings
    → unparse back to source

         │
         ▼
    Phase 4: TF-IDF vectorize full cohort ONCE
    vectorizer = TfidfVectorizer()
    matrix = vectorizer.fit_transform(normalized)
    sim_matrix = cosine_similarity(matrix)
    → O(N·V) time, O(N²) space for sim_matrix

         │
         ▼
    Phase 5: Upper-triangle comparison
    Only check pair (i, j) if:
      all_subs[i].student_id IN high_risk_ids
      OR
      all_subs[j].student_id IN high_risk_ids

    if sim_matrix[i][j] >= policy.similarity_threshold:  # default 0.80, read from Redis cache
        _save_pair_flag(question, sub_a, sub_b, sim)   # one flag per (question, lower student id, higher student id)
        notify_plagiarism_flagged(pf)                  # only when the pair is new
    
    Submission.similarity_check_done = True
    for all subs in this question
```

### Why Suspects vs Full Cohort (not Suspects vs Suspects)

This is a subtle but critical design decision.

If you compare only flagged suspects against each other, you miss the source student. A student who typed slowly and didn't paste has clean behavioural signals. If a flagged student copied from them, they appear nowhere in the behavioural flags. Suspects-vs-suspects would never find that pair.

The correct approach: suspects are the **query set**, the full cohort is the **search space**.

**Who is a suspect (changed 2026-10-06).** A flagged student whose weighted risk score is at least the policy's `compare_min_risk` (default 0.35), **or** who fired 3+ signals (high confidence). Before this, only 3+-signal students were compared, so the weights never decided who was compared: a student who pasted 100% of the code but did nothing else (1 signal, risk 0.40) was flagged yet never compared. Now raising a weight on the Policy page and rerunning brings new students into the comparison. A rerun under a stricter policy also removes behavioural flags that no longer reach `min_risk_score`, but only flags still `pending` with no dispute (a legacy per-flag one, or an appeal on that exam by that student); reviewed or disputed flags keep the trainer's decision. Policy changes apply forward: past runs keep their policy snapshot, and old exams change only when a trainer presses Rerun (which can add pairs and clear unreviewed flags).

```
SUSPECTS vs SUSPECTS (wrong):
  K=10 suspects, 10 sources never flagged
  → 10×10 = 100 comparisons
  → MISSES all 10 sources

SUSPECTS vs FULL COHORT (correct):
  K=10 suspects, N=200 total students
  → 10×200 = 2,000 comparisons
  → CATCHES sources regardless of their own behaviour signals
```

### Complexity Comparison

| Approach | Complexity | 10k students, 5% flag rate |
|---|---|---|
| All-pairs naive | O(N²) | 50,000,000 comparisons |
| Suspects vs suspects | O(K²) | 250,000 comparisons, misses sources |
| **Our approach (suspects vs cohort)** | **O(K×N)** | **5,000,000 comparisons** |

At 5% K/N ratio: our approach is 10x cheaper than naive while catching the cases that suspects-vs-suspects misses.

### Code Normalization — AST Variable Renaming

Before TF-IDF comparison, all user-defined names are replaced with sequential tokens. This catches the most common evasion technique: renaming variables.

```python
# Original student code:
def twoSum(nums, target):
    seen = {}
    for i, val in enumerate(nums):
        complement = target - val
        if complement in seen:
            return [seen[complement], i]
        seen[val] = i

# After AST normalization:
def VAR_0(VAR_1, VAR_2):
    VAR_3 = {}
    for VAR_4, VAR_5 in enumerate(VAR_1):
        VAR_6 = VAR_2 - VAR_5
        if VAR_6 in VAR_3:
            return [VAR_3[VAR_6], VAR_4]
        VAR_3[VAR_5] = VAR_4
```

Now TF-IDF sees the same token stream regardless of what the student named their variables. Comments and docstrings are stripped before normalization.

Python uses `ast.parse()` + `ast.NodeTransformer` + `ast.unparse()` — structural transformation. JavaScript uses regex substitution (not AST, since Python's `ast` module only handles Python).

### Auto-Close Trigger Chain

```
Celery Beat
(every 60 seconds)
     │
     ▼
auto_manage_exams()
     │
     ├── find exams where end_time < now AND is_active=True
     │
     ├── for each: exam.is_active = False; exam.save()
     │                    │
     │                    ▼
     │          pre_save signal on Exam model fires
     │          (codemas/signals.py)
     │                    │
     │                    ▼
     │          run_exam_plagiarism_check.delay(exam_id)
     │
     └── find exams where start_time <= now AND is_active=False
         for each: exam.is_active = True; exam.save()
```

This means manual close and auto-close behave identically. The signal is the single source of truth for triggering plagiarism detection.

### Pre-Save Signal (Django Signals)

```python
# codemas/signals.py

@receiver(pre_save, sender=Exam)
def on_exam_close(sender, instance, **kwargs):
    if instance.pk:
        old = Exam.objects.get(pk=instance.pk)
        # only fire when transitioning from active → inactive
        if old.is_active and not instance.is_active:
            from plagiarism.tasks import run_exam_plagiarism_check
            run_exam_plagiarism_check.delay(instance.pk)
```

This pattern ensures the plagiarism job is always triggered regardless of how the exam was closed (manual trainer action, Celery Beat scheduler, or admin panel).

### Plagiarism Review Workflow

```
DETECTION                TRAINER UI                    AUDIT LOG
     │                       │                              │
     ▼                       │                              │
BehaviouralFlag created  ──► Exam case file (Investigation)│
(risk > policy.min_risk_score)│                             │
                             │  Trainer sees:               │
PlagiarismFlag created  ───► │  - risk_score bar            │
(similarity >= policy.similarity_threshold) │ - which signals fired │
                             │  - signal scores             │
                             │  - matched students          │
                             │  - similarity %              │
                             │  - "View" to jump to         │
                             │    other submission          │
                             │                              │
                             │  Trainer clicks:             │
                             │  [Confirm] or [Dismiss]      │
                             │     │                        │
                             │     ▼                        │
                             │  PATCH /plagiarism/          │
                             │        flags/{id}/review/    │
                             │     │                        │
                             │     ▼                        │
                             │  ReviewAuditLog.create() ───►│
                             │  (flag_type, flag_id,        │
                             │   action, note,              │
                             │   reviewed_by, timestamp)    │
```

---

## 8.1 Policy Versioning and Changelog

### Why Versioning Matters

The `PlagiarismPolicy` singleton stores eleven configurable values (weights, baselines, minimum risk, compare-from risk, similarity threshold, max attempts). When a trainer changes these values mid-cohort, the algorithm's scoring changes immediately for all future submissions. Without a changelog, a disputed flag from two weeks ago cannot be audited — the trainer cannot know what weights were in effect when the flag was generated.

### Snapshot vs Diff Approach

Full JSON snapshots were chosen over field-level diffs for three reasons:

1. **The model is small** — nine float/int fields. Storing the complete state before and after every change wastes negligible space.
2. **Point-in-time query is trivial** — "what policy was active on date X?" = find the latest `PolicyVersion` with `changed_at <= X`. One lookup, no reconstruction from a chain of diffs.
3. **Dispute resolution is unambiguous** — a `snapshot_before` contains the exact values the algorithm used to generate a flag, with no dependency on intermediate state.

### PolicyVersion Model

```python
POLICY_FIELDS = [
    'paste_weight', 'time_weight', 'tab_weight', 'submission_weight',
    'min_risk_score', 'similarity_threshold',
    'easy_baseline_s', 'medium_baseline_s', 'hard_baseline_s',
]
```

Every `PUT /api/plagiarism/policy/` call:
1. Reads current state → `snapshot_before`
2. Saves updated policy to Postgres
3. Calls `cache.delete('plagiarism_policy')` — next Celery task picks up new values immediately
4. Reads new state → `snapshot_after`
5. Creates a `PolicyVersion` record with both snapshots and the trainer's `change_reason`

### Affected Exam Detection

The changelog view computes which exams overlapped each policy's active window:

```
Each PolicyVersion is active from its changed_at
until the next newer version supersedes it.

Active period: [period_start, period_end)
  period_start = v.changed_at
  period_end   = versions[i-1].changed_at  (the newer version)
               = now                        (for the current version)

Temporal overlap query:
  Exam.objects.filter(
      start_time__lt=period_end,
      end_time__gt=period_start,
  )

Overlap means: the exam started before the policy ended
               AND the exam ended after the policy started.
```

Each overlapping exam is labeled:
- **"started under this policy"** — exam started after the policy took effect
- **"in-flight at change"** — exam was already running when the policy changed

This gives trainers full context for dispute resolution: "this student was flagged under policy v3, which had a paste_weight of 0.40 and similarity_threshold of 0.75."

---

## 8.2 Cohort Investigation and Cheating Ring Detection

### The Problem with Flat Flag Queues

The annotation queue shows individual flags in isolation. A trainer reviewing 40 pending flags has no way to know whether those flags cluster around one exam (indicating a systemic problem) or are spread uniformly. Worse, they cannot see whether the flagged students form a group — if A copied from B who copied from C, the queue shows three separate flags with no indication they're connected.

### Three-Level Investigation Model

```
Level 1 — Cohort Health Feed  (/plagiarism/cohorts/)
  Investigation page (first item under Integrity; the old Flags page URL
  /dashboard/plagiarism redirects here). One list of exams; no tabs.
  All exams ranked by flag rate
  Flag rate = flagged_students / total_submissions
  Health: green (<10%), amber (10–25%), red (>25%)

Level 2 — Cohort Deep Dive  (/plagiarism/cohorts/<exam_id>/)
  KPI strip: total students, flagged count, flag rate, ring count
  Cheating rings (connected components)
  Student risk ranking

Level 3 — Student page  (/dashboard/students/<id>)
  One student page (Overview, Integrity, Disputes tabs) — linked from both rings and
  student table. The old student case URL /dashboard/support/student/<id> redirects here.
```

### Combined Risk Score

Each student in a cohort gets a `combined_risk` score computed from both signal types:

```
b_risk     = behavioural flag risk_score (0.0–1.0), or 0 if none
sim_factor = min(similarity_pairs_count / 5.0, 1.0)

combined_risk = b_risk * 0.6 + sim_factor * 0.4
```

Weight rationale: behavioural signals are direct evidence from this student's own session (60%); similarity pairs are cross-student evidence that requires context (40%). A student with both a high behavioural score and multiple similarity matches ranks highest.

### Cheating Ring Detection — Connected Components

The core insight: if A has a similarity flag with B, and B has a similarity flag with C, then A, B, and C are likely in the same plagiarism ring — even if A and C never directly matched. A flat flag queue cannot surface this because it only shows pairs.

Implementation: BFS on the similarity flag adjacency graph.

```
Build adjacency list from all PlagiarismFlags in this exam:
  adj = {student_id: {other_student_id, ...}}

  for each PlagiarismFlag(submission_1, submission_2, flagged=True):
      adj[s1.student_id].add(s2.student_id)
      adj[s2.student_id].add(s1.student_id)

BFS connected components:
  visited = set()
  for start_id in adj:
      if start_id in visited: continue
      
      component = []
      stack = [start_id]
      while stack:
          node = stack.pop()
          if node in visited: continue
          visited.add(node); component.append(node)
          stack.extend(adj[node] - visited)
      
      if len(component) >= 2:
          emit ring(members=component, ...)

Ring stats:
  avg_similarity — mean similarity score across all edges in component
  max_similarity — highest single pair score
  confirmed      — how many edges have been confirmed by a trainer
```

### Why This Catches Cases the Flag Queue Misses

```
Scenario: 5 students, 4 similarity flags
  A ─── B ─── C ─── D ─── E

Flag queue shows: 4 separate pairs (A-B, B-C, C-D, D-E)
Ring detection shows: one ring of 5 members

Without ring detection:
  Trainer reviews A-B, dismisses if only 84% similar
  Never realizes A-B-C-D-E are one network

With ring detection:
  Ring of 5 appears immediately — trainer investigates the whole group
```

### Recidivism Tracking

For each flagged student, `past_flags` counts how many similarity or behavioural flags they have in **other** exams. A student who has been flagged in three consecutive exams is a different risk profile from a first-time flag.

```python
past_sim = PlagiarismFlag.objects.filter(
    flagged=True,
    Q(submission_1__student_id=sid) | Q(submission_2__student_id=sid)
).exclude(
    Q(submission_1_id__in=sub_ids_this_exam) | Q(submission_2_id__in=sub_ids_this_exam)
).count()

past_b = BehaviouralFlag.objects.filter(
    submission__student_id=sid
).exclude(submission__exam=exam).count()

student['past_flags'] = past_sim + past_b
```

---

## 8.3 Policy Impact Tracking — Run History

### The Problem

When a trainer changes the similarity threshold from 0.80 to 0.75, or increases the paste weight from 0.40 to 0.55, what actually changed in the detection results? Without a per-run audit record, there is no way to answer that question — you only see the current flags, not how they evolved across policy iterations.

### PlagiarismRun — Per-Run Audit Record

Every execution of `run_exam_plagiarism_check` creates a `PlagiarismRun` record before any detection starts. It captures three categories of data:

**1. Policy Snapshot**
Full JSON copy of all 9 `PlagiarismPolicy` fields at the moment the run started. Even if a trainer changes policy immediately after, the run record preserves exactly what weights and thresholds were active.

**2. Exam Performance Context**
Fixed metrics that don't change between runs for the same exam:
- `unique_students` — distinct student count (NOT total submission rows)
- `pass_rate` — students who passed ≥1 question / unique_students
- `avg_execution_ms` — average submission execution time (`execution_time_ms`, summed across a submission's tests)
- `avg_solve_time_s` — average time for passed submissions
- `avg_attempts` — average attempts per student per question (not total submissions)
- `avg_time_remaining` — average time left on clock at submission

**3. Detection Results**
Updated atomically as tasks complete:
- Phase 1 counts: total flags, per-confidence-level breakdown, avg risk score
- Phase 2 counts: total pairs, 90%+ pairs, 80–90% pairs, avg similarity
- Progress: `questions_done / questions_total` — shown as live progress when status=RUNNING

### Atomic Updates with F() Expressions

Phase 2 queues one Celery task per question. All tasks run in parallel and write back to the same `PlagiarismRun` row. Without atomic updates, two tasks completing simultaneously could both read `questions_done=2`, both write `3`, losing an increment.

```python
PlagiarismRun.objects.filter(pk=run_id).update(
    s_flags_new=F('s_flags_new') + new_flags,
    questions_done=F('questions_done') + 1,  # atomic in Postgres
)
```

`F()` pushes the arithmetic into the SQL `UPDATE` statement, making it atomic. The "last question to finish" pattern: after incrementing, check `questions_done >= questions_total`. The task that crosses the threshold finalises the run.

### Manual Re-run

```
POST /api/plagiarism/cohorts/<exam_id>/rerun/
```

Triggers a fresh `run_exam_plagiarism_check` with `trigger='manual_rerun'`. This is how trainers apply a new policy to past exams. Behaviour on re-run:

- **Phase 1 (behavioural):** `update_or_create` on `BehaviouralFlag` — existing flags are recalculated with new weights. Confidence levels and risk scores update.
- **Phase 2 (similarity):** one flag per (question, student pair), students ordered by id. An existing pair is updated in place (its submissions move to each student's current best attempt, and its `similarity_score` is refreshed), so a pair confirmed during a live-exam check is not brought back as pending by the exam-close run. New pairs are created. **Old pairs that no longer meet the threshold are NOT deleted.** Trainer review decisions (`review_status`, `review_note`) are always preserved.
- A new `PlagiarismRun` record is always created — giving a before/after comparison in Run History.

### Why Exam Context Doesn't Change Between Runs

`pass_rate`, `avg_execution_ms`, `avg_solve_time_s` are calculated from `Submission` records, which are immutable after the exam closes. These values are identical across every run for the same exam. They are stored in `PlagiarismRun` to give the trainer full context without needing to cross-reference another view.

### Phase 2 Task Staggering

```python
for i, question in enumerate(exam.questions.all()):
    run_question_plagiarism_check.apply_async(
        args=[question.id, run.pk],
        countdown=i * 30,  # Q1=0s, Q2=30s, Q3=60s...
    )
```

Questions are staggered by 30 seconds to avoid all questions hitting TF-IDF vectorization simultaneously — a CPU spike that would block the Celery worker pool.

---

## 9. Code Similarity Search

A separate feature distinct from plagiarism detection. Trainers can paste any code snippet and find the most similar submissions across all exams and all students.

### Why This Exists

- Investigating a suspected source of plagiarism: paste the common code to find who originally had it
- Searching across exam boundaries: plagiarism that spans multiple exams (student reuses old code)
- Debugging: finding which students are using a specific anti-pattern

### Algorithm

```
TRAINER pastes query code
         │
         ▼
    POST /api/plagiarism/search/
    {code: "...", language: "python", top_k: 15}

         │
         ▼
    1. Normalize query: normalize_code(query, language)

         │
         ▼
    2. Fetch corpus: Submission.objects[:2000]
       (cap at 2000 for memory — TF-IDF matrix grows with N)

         │
         ▼
    3. For each submission: use pre-stored normalized_code
       if empty (old submission): normalize on the fly

         │
         ▼
    4. Check Redis cache:
       cache_key = 'tfidf:' + MD5(
           ','.join(f'{s.id}:{s.language}' for s in submissions)
       )
       
       CACHE HIT:  deserialize (vectorizer, corpus_matrix) from pickle
                   query_vec = vectorizer.transform([query])
       
       CACHE MISS: vectorizer = TfidfVectorizer()
                   corpus_matrix = vectorizer.fit_transform(corpus)
                   cache.set(key, pickle.dumps((vectorizer, corpus_matrix)),
                             timeout=300)
                   query_vec = vectorizer.transform([query])

         │
         ▼
    5. scores = cosine_similarity(query_vec, corpus_matrix)[0]

         │
         ▼
    6. Sort descending, return top_k where score > 0.1
```

### Two Critical Optimizations

**Optimization 1: Pre-computed normalized_code**

At submission time, after execution completes, the code is normalized and stored:

```python
# execution/tasks.py
from plagiarism.tasks import normalize_code
submission.normalized_code = normalize_code(submission.code, submission.language)
submission.save()
```

This means at search time, we do not need to normalize 2000 submissions. We just read the pre-stored normalized text. At 2000 submissions, this saves approximately 2000 × (AST parse + unparse) calls per search.

**Optimization 2: TF-IDF matrix cached in Redis**

The vectorizer and corpus matrix are serialized with pickle and cached for 5 minutes. The cache key is the MD5 hash of all submission IDs and languages — it automatically invalidates when a new submission is created (the hash changes).

```
Without cache:  every search call → fit_transform(2000 docs) → ~50ms
With cache:     subsequent searches → transform([1 doc]) → ~2ms
                Cache invalidates when new submissions arrive
```

### Why Not a Vector Database (pgvector, FAISS, Pinecone)

This is a common question and the answer has an important subtlety:

**TF-IDF vectors are corpus-relative.** The IDF score for a token depends on how many documents in the corpus contain it. If you compute a TF-IDF vector for a submission on Day 1 and store it, that vector is **stale** on Day 30 when 200 more submissions have been added. The IDF denominators have changed.

**Neural embeddings (CodeBERT) are corpus-independent.** The model weights don't change. An embedding computed at submission time is valid forever. This is when a vector database makes sense — pre-compute the embedding once, store it, search at query time.

**pgvector** was attempted on PostgreSQL 15 on macOS. The extension could not be built. This is a known macOS build issue, not an architectural blocker.

**At current scale (2000 submissions):** TF-IDF runs in ~50ms. This is not a bottleneck.

**Migration path to vector DB (at 100k+ submissions):**
1. Add CodeBERT embedding (400MB model, GPU-preferred)
2. Compute embedding at submission time, store in `Submission.embedding` column
3. Use pgvector or FAISS index for approximate nearest-neighbour search
4. Search becomes: embed query → FAISS.search(query_vec, k=15) → sub-millisecond

### View Code — Line-by-Line Comparison (Separate from TF-IDF)

The TF-IDF score decides *whether* to flag a pair. The View Code panel decides *what to show* when a trainer clicks into a flagged pair. These are completely different algorithms.

**How line-by-line comparison works (frontend, `utils/codeCompare.ts`, shown in the exam case file on Investigation):**

```typescript
function findMatchedLines(lines1, lines2) {
    // Step 1: build a lookup map from submission 2
    // key = trimmed line text, value = [line indices where it appears]
    const set2 = new Map<string, number[]>()
    lines2.forEach((line, i) => {
        if (line.trim().length > 2)  // skip blank/tiny lines
            set2.set(line.trim(), [...(set2.get(line.trim()) || []), i])
    })

    // Step 2: walk submission 1 line by line
    lines1.forEach((line, i) => {
        if (line.trim().length > 2 && set2.has(line.trim())) {
            matched1.add(i)             // highlight this line green in sub1
            set2.get(line.trim())
                .forEach(j => matched2.add(j))  // highlight matching lines in sub2
        }
    })
}
```

**Algorithm:** exact string match after trimming whitespace. A line in submission 1 that matches any line in submission 2 (same text, ignoring leading/trailing spaces) gets highlighted green in both panels.

**Why not TF-IDF for this:** TF-IDF gives a single score for the whole document — it cannot tell you which specific lines matched. Line-by-line exact match is O(N) per submission (hash lookup) and directly answers "what did they copy?"

**The two-layer display:**

| | TF-IDF cosine | Line-by-line match |
|---|---|---|
| Purpose | Decide whether to flag the pair | Show trainer exactly which lines matched |
| Input | Normalized code (VAR_0, VAR_1...) | Original code (raw text) |
| Output | Score 0.0–1.0 | Set of highlighted line indices |
| Runs | Backend, at detection time | Frontend, when trainer clicks "View Code" |
| Algorithm | Vector angle | Hash lookup per line |

### Similarity Techniques Reference

| Technique | What It Detects | Complexity | Used In CodeMas |
|---|---|---|---|
| TF-IDF + cosine | Token frequency similarity | O(N·V) build, O(V) query | Yes — similarity search |
| AST comparison | Structural equivalence (for→while) | O(N) per pair | Yes — normalization step |
| CodeBERT embeddings | Semantic meaning | O(1) per query if pre-built | Future path |
| MOSS token fingerprinting | Partial copying (substrings) | O(N·W) | Not implemented |
| Levenshtein / SequenceMatcher | Character-level edit distance | O(M×N) per pair | Yes — submission_surprise signal |

---

## 9.5 AI Features Layer (Async GPT)

Three GPT-backed features live in the `ai` Django app. The governing rule:
**none of them touch the critical result-delivery path.** CodeMas's headline
metric is sub-10s result delivery at 10k concurrent students; every AI feature
fires *after* the grade is committed, as a separate Celery task, and appears in
the UI a few seconds later. Any failure (no API key, provider down, malformed
output) is logged and swallowed — the student's pass/fail result is never affected.

### Shared Design

- **`ai/llm.py`** — one OpenAI client wrapper. Reads `OPENAI_API_KEY`; if absent
  it raises `LLMUnavailable` so every task degrades to a clean no-op (the app runs
  fine with no key configured). All calls force `response_format=json_object` for
  structured output. Model is `OPENAI_MODEL` (default `gpt-4o-mini`); timeout via
  `OPENAI_TIMEOUT`.
- **Idempotent tasks** — each result is a `OneToOne` on its source row, and every
  task early-returns if a row already exists, so retries / page refreshes never
  regenerate or double-bill.
- **Backfill for seeded history** — `manage.py backfill_ai_feedback` queues
  `score_rubric` (and `generate_hint` for failed attempts) for every graded submission
  missing one. Needed because the demo seed writes submissions directly, so the
  per-submission `after_grading` hook never fired for them. Run after every seed.
- **Read-only polled API** — frontend polls `GET` endpoints that return
  `{"status": "pending"}` until the row exists, then the data. Bounded polling
  (≈15 × 2s) gives up quietly if a feature is unavailable.

### The Three Features

| Feature | Trigger | Task | Stored on | API (auth) |
|---|---|---|---|---|
| Rubric scoring | Every submission, after delivery | `score_rubric` | `RubricScore` (1:1 Submission) | `GET /api/ai/rubric/<submission_id>/` (owner/trainer) |
| Socratic hint | Failed submissions only | `generate_hint` | `AIHint` (1:1 Submission) | `GET /api/ai/hint/<submission_id>/` (owner/trainer) |
| Plagiarism explanation | New flagged pair at exam close | `explain_plagiarism` | `PlagiarismExplanation` (1:1 PlagiarismFlag) | `GET /api/ai/plagiarism-explanation/<flag_id>/` (trainer) |
| Exam summary | First view of an exam on My results | `generate_exam_summary` (inline, cached) | `ExamSummary` (unique student + exam) | `GET /api/ai/exam-summary/<exam_id>/` (owner/trainer) |
| Weekly recommendation | Celery beat, Monday 07:00 IST | `weekly_recommendations_task` | `WeeklyRecommendation` (unique student + week_start) | `GET /api/ai/recommendation/me/` (owner; 204 until the first one) |

- **Rubric** — one GPT call scores 4 dimensions (correctness, code quality,
  approach, edge cases) 0–2 each (total 0–8) with per-dimension justifications +
  overall feedback. Enqueued once grading commits. For Python and JavaScript that
  is `jobs.execute.after_grading`, run on commit by the executor's `complete`
  call. For C++ and Java it is the legacy `execution.tasks.execute_submission`. Shown as a collapsible "AI Feedback" panel under
  the result in `ExamTakeView`.
- **Hint** — enqueued from the same place but gated on `status == 'failed'`. Uses
  the first failed test case (input/expected/actual/error) + code as context.
  Socratic — never reveals the fix. Shown behind a "Show Hint" toggle, hidden by
  default.
- **Plagiarism explanation** — enqueued from `plagiarism.tasks` only when a *new*
  `PlagiarismFlag` is created above threshold, alongside the existing Layer 2
  TF-IDF pass. Inputs: both submissions' code, the question, similarity score, and
  each student's behavioural signals. Returns summary + 2–3 concrete observations
  + confidence (low/medium/high). Surfaced as an "AI Explanation" toggle on each
  similarity pair in the trainer review UI — explicitly framed as *evidence, not a
  verdict*; the trainer still decides.

### Weekly recommendation (added 2026-10-06)

One call per student per week that reads **all of the student's exams together**,
separate from the per-exam summary (which stays).

- **Schedule** — `CELERY_BEAT_SCHEDULE['weekly-recommendations']`,
  `crontab(minute=30, hour=1, day_of_week='mon')` (TIME_ZONE is UTC, so 07:00 IST).
  Runs on the existing worker (`celery -A codemas worker -B`), where all AI work lives.
- **Who** — every student (role `student`, not superuser) with at least one graded
  attempt (`passed`/`failed`/`error`). About 98 calls a week at the current seed.
- **Input** (`weekly_recommendation_input`) — per exam with a graded attempt: score /
  available, the exam result (passed = solved at least half the questions; a question voided for
  confirmed plagiarism is not counted, and the line says how many were not), rank of cohort, and the questions sorted
  into `passed_first_try` / `passed_after_retries` / `not_passed` / `not_attempted`
  (failed first time = retries + not passed; still unsolved = not passed + not
  attempted), so the model never has to work out "first try" itself. Built
  from `leaderboard/exam_stats.py:student_exam_stats`, the same helper behind
  `/api/leaderboard/me/exams/`, so the prompt sees the numbers the page shows.
- **Output** — a one-sentence headline and three cards (`keep` / `work` / `next`:
  Keep doing, Work on, Next step), each `{text, evidence}` where evidence quotes the
  real results. Prompt rules: every claim from the supplied numbers, name questions
  and topics, no tool/vendor names, 1–2 sentences per card.
- **Storage** — `ai.WeeklyRecommendation(student, week_start, headline, cards JSON,
  input_digest, model_used, created_at)`, unique on (student, week_start). `week_start`
  is the IST Monday. `input_digest` is a sha256 of the input; if the numbers have not
  changed since the last row, the row is carried forward with no model call.
- **Failure** — a failed or malformed call writes nothing, and the API keeps returning
  the latest good row. One student's failure never stops the loop.
- **Backfill** — `python manage.py generate_weekly_recommendations` writes this week's
  row for every eligible student now (run once after deploy and after a re-seed so the
  demo shows one before the first Monday). Re-running keeps existing rows.
- **UI** — top of My results, under the KPI tiles and above the difficulty tiles,
  inside the shared `AiGlow` component: "Updated Tue, 6 Oct · next Mon, 12 Oct".
  Empty state: "Your first weekly recommendation arrives the Monday after your first
  exam is graded."

### AI glow (`frontend/src/components/AiGlow.vue`)

Every AI-written block (weekly recommendation, exam summaries, rubric reviews, hints)
renders inside `AiGlow`: a slow conic-gradient border (Masai red → violet → orange),
a soft blurred halo and a sparkle icon with `aria-label="Generated by AI"`. It replaces
the old "Written by a model from your results." caption. The animation stops under
`prefers-reduced-motion`.

### Why off the critical path

The enqueue calls are wrapped in `try/except` at the call site, so even failing to
*enqueue* an AI task cannot break grading. On the job pipeline, `after_grading` also
runs as a robust on-commit hook, after the result is already committed. Python and
JavaScript execution doesn't touch Celery at all, so a slow GPT call can't delay
their grading. C++ and Java execution shares the Celery workers, but as separate
task invocations, so a slow GPT call backs up only the AI work.

---

## 10. Auto-Exam Lifecycle — Celery Beat

### Celery Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                       Celery Setup                                  │
│                                                                     │
│  settings.py:                                                       │
│    CELERY_BROKER_URL = REDIS_URL                                   │
│    CELERY_RESULT_BACKEND = REDIS_URL                               │
│    CELERY_BEAT_SCHEDULE = {                                        │
│        'auto-manage-exams': {                                      │
│            'task': 'exams.tasks.auto_manage_exams',               │
│            'schedule': 60.0,  # every 60 seconds                  │
│        },                                                          │
│        'weekly-recommendations': {                                 │
│            'task': 'ai.tasks.weekly_recommendations_task',        │
│            'schedule': crontab(mon 01:30 UTC = 07:00 IST),        │
│        },                                                          │
│    }                                                               │
└────────────────────────────────────────────────────────────────────┘

                     ┌─────────────────────────────────────┐
                     │            Redis                     │
                     │                                     │
                     │  Queue: celery (default)            │
                     │    - execute_submission (C++/Java)   │
                     │    - score_rubric, generate_hint     │
│    - weekly_recommendations_task     │
                     │    - run_exam_plagiarism_check       │
                     │    - run_question_plagiarism_check   │
                     │                                     │
                     │  Pub/Sub: submission:{id} (legacy   │
                     │    task still publishes; unused)    │
                     └────────────────┬────────────────────┘
                                      │
                     ┌────────────────▼────────────────────┐
                     │         Celery Worker               │
                     │  (python -m celery -A codemas       │
                     │   worker --loglevel=info)           │
                     │                                     │
                     │  + Celery Beat                      │
                     │  (python -m celery -A codemas       │
                     │   beat --loglevel=info)             │
                     └─────────────────────────────────────┘
```

### What Moved Off Celery, and What Stayed

The original argument against Lambda was that it would mean a full rewrite: SSE needed a persistent pub/sub listener, and Beat needed an always-on process. The decision actually taken avoids that rewrite by moving only the piece that benefits.

1. **Submission execution for Python and JavaScript moved to the job pipeline** (§5): a transactional outbox, a relay, and an executor written as a Lambda handler.
   - Locally the relay runs the handler in-process (`JOB_TRANSPORT=local`).
   - In production, since 2026-10-05, the same code runs as the `codemas-exec` Lambda behind SQS.
   - The SSE dependency went away because the browser now polls `/status/`, so nothing needs a long-lived subscription.

2. **Celery Beat stays.** `auto_manage_exams` still runs every 60 seconds on Celery Beat. EventBridge could replace it later, but nothing forces that.

3. **AI and plagiarism work stays on Celery.** That covers the rubric, hints, plagiarism explanations and the exam-close plagiarism batch. They are long-running, best-effort, and not on the student's critical path.

4. **C++ and Java execution stays on Celery for now.** It needs a heavier executor image. It is chosen per language by `PIPELINE_LANGUAGES`, and today it runs through `run_local` with no sandbox (see §17).

### Task Staggering on Exam Close

When an exam closes, it may have 10+ questions. All plagiarism checks are staggered with a `countdown` delay to avoid a CPU spike:

```python
for i, question in enumerate(exam.questions.all()):
    run_question_plagiarism_check.apply_async(
        args=[question.id],
        countdown=i * 30,  # 0s, 30s, 60s, 90s...
    )
```

This distributes CPU load across time rather than hitting all questions simultaneously.

`seed_data` uses this same entry point for demo data: Phase 2 runs through the real exam-close path on every closed exam (`run_exam_plagiarism_check(exam_id, trigger='exam_close', notify=False)`, Celery in eager mode, `notify` passed through to every per-question task); planted copying cases are caught from Phase 1 suspects.

---

## 11. Trainer Dashboard and Monitoring

### Dashboard KPIs

```
GET /api/dashboard/

Returns:
  kpis:
    total_students         ← User.objects.filter(role='student').count()
    total_submissions      ← Submission.objects.count()
    pass_rate              ← passed / total * 100
    plagiarism_flags       ← PlagiarismFlag.filter(flagged=True, review_status='pending').count()

  timeline:
    last 14 days, per-day: {date, total, passed}
    gaps filled with 0s — no missing dates in chart

  question_stats:
    per question: pass_rate, avg_exec_time, avg_attempts_to_pass

  language_distribution:
    {python: N, javascript: N, java: N, cpp: N}

  cohort_comparison:
    per cohort: student_count, total_submissions, pass_rate

  top_performers (top 5 by pass rate)
  struggling_students (pass_rate < 40%, up to 5)
```

### Submission Detail View

The most information-dense view in the system. Shows:

```
┌─────────────────────────────────────────────────────────────────┐
│ Student: alice | Exam: Week 3 | Q2: Two Sum | Attempt 2         │
├─────────────────────────────────────────────────────────────────┤
│ KPIs: exec_time=234ms | time_used=67% | test_cases=3/3         │
│       ip_address=10.0.0.45 | behav_done=✓ | sim_done=✓         │
├─────────────────────────────────────────────────────────────────┤
│ CODE:                                                            │
│ def solution(nums, target): ...                                  │
├─────────────────────────────────────────────────────────────────┤
│ TEST CASES:                                                      │
│ [1] input=[2,7,11,15], target=9 | expected=[0,1] | got=[0,1] ✓ │
│ [2] input=[3,2,4], target=6     | expected=[1,2] | got=[1,2] ✓  │
│ [3] input=[3,3], target=6       | expected=[0,1] | got=[0,1] ✓  │
├─────────────────────────────────────────────────────────────────┤
│ BEHAVIOURAL FLAGS:                                               │
│ risk_score: 0.73 ████████████░░ HIGH flag confidence            │
│ Signals: "Pasted 68% of code (142 chars)"                       │
│          "Solved medium in 1m 12s (baseline 4m)"               │
│ [Confirm Plagiarism]  [Dismiss]                                  │
├─────────────────────────────────────────────────────────────────┤
│ SIMILARITY FLAGS:                                                │
│ Matched: bob | 87% similar | [View Submission #142]             │
│ Status: pending review                                           │
└─────────────────────────────────────────────────────────────────┘
```

### Flag review

Flags are reviewed on each exam's case file (Investigation → exam), one at a time or in bulk. The separate Annotation queue page was removed 2026-10-08: it sent the same `review_status` and `review_note` to the same review endpoint, so nothing it recorded is lost; `/dashboard/plagiarism/queue` redirects to Investigation. Every review action is written to `ReviewAuditLog` for a full audit trail.

**A confirmed case costs the student their points (2026-10-08).** On the next page load
(no caching), the student's points for the question are withheld when they have a confirmed
behavioural flag on it, or a confirmed similarity pair plus a behavioural flag (not dismissed)
of their own on it; a classmate who only matched keeps their points. One rule in
`analytics/metrics.py` (`voided_pairs`, used by `points_by_student` and `solve_times`), so the
score and rank drop identically on the exam report, the student page, My results, Home and the
leaderboard. The exam report marks the student "Points withheld · plagiarism confirmed · −N";
a student with a pending flag is marked "Under review" with the rank unchanged. The student
sees the outcome in the Trainer review box on My results (see "Appeals" below); the
leaderboard shows no markers. **A voided question is not solved either** (owner decision
2026-10-08): `metrics.exam_results` leaves it out of `solved` and reports `voided`, so the pass
rule can fail the exam when that drops the student below half (3 of 4 with one voided still
passes), and every success rate, the trend dot, students who need help and the question success
rate (`question_success_by`) follow. Pages say why: My results ("Tests passed on attempt N · Not
counted: plagiarism", the Result card's "Plagiarism confirmed by your trainer"), the exam report
("Not passed · plagiarism", or "Passed" with "N not counted"), the student page trend tooltip,
and the AI summary / weekly recommendation result line. Dismissing or overturning restores it;
the matched side of a pair keeps the solve. See `docs/metrics.md`. The log is kept (`GET /api/plagiarism/audit/`, latest 200) but no trainer page shows it since 2026-10-08 (owner removed the Audit trail tab to keep Investigation to one story).

**Past exams arrive reviewed (2026-10-08).** `manage.py settle_past_reviews` decides every pending
flag on an ENDED exam as the trainer would have: a high-confidence behaviour flag of a student in a
code-match pair is confirmed (note: points withheld), a pair is confirmed when either side's behaviour
flag was (a neutral note true for both students), everything else is dismissed without a note. It
uses the review endpoints' own steps (reviewed_by, `ReviewAuditLog`, summary refresh) and dates the
audit entries a day after the exam ended. The seed runs it, so Investigation starts with no backlog
while every past case stays visible as decided history. Dry run unless `--yes`; re-running is a no-op.

**Reaching a case from a student (2026-10-08).** Cases are built in one place,
`plagiarism.views.exam_cases(exam_id)` (with `case_keys`), used by the investigation detail, the
student page (`integrity_cases`: one entry per exam the student has flags on, with status,
withheld points, code matches, the decided note and the `case_key`) and the exam report rows
(`case_key`). The report's "Under review" badge and the student page's Integrity tab link straight
to that case; the case file takes `from=student:<id>` / `from=report:<id>` / `from=dispute:<id>`
to show a back button (highlighting the student when opened from their page) and return there
after a decision.

**Notes to students.** Confirm/Dismiss case sends one group note, or separate notes per student.
A student's note is stored on their own behavioural flags; a similarity pair carries a note only
when both of its students get the same one, otherwise an empty note, so no student sees a
classmate's note. Matched-only students (no behavioural flag of their own on the exam) get no
note unless the trainer ticks them, mirroring the points rule. My results (`GET
/api/plagiarism/mine/`) shows each note text once per exam.

### Appeals (disputes) — one round per exam (2026-10-08)

Model `support.DisputeRequest`, one row per (student, exam) (`UniqueConstraint` on student + exam
for rows without a `flag_id`). Fields: `exam` (FK), `student_note` (≤ 1,000 characters, required),
`decision_note` (the trainer's notes on the student's confirmed flags when the appeal was filed:
an overturn rewrites the flags' notes, so the original is kept here), `status` open / upheld /
overturned, `resolution_note`, `resolved_by`, `resolved_at`. `flag_type` / `flag_id` are set only
on legacy rows filed per flag before this change.

| Endpoint | Who | What |
|---|---|---|
| `POST /api/support/disputes/` `{exam_id, student_note}` | student | Files the appeal. 404 when the student didn't take the exam; 400 without a confirmed decision there (their own behavioural flag, or a similarity pair on either side), with an empty or over-long response, or when the exam already has an appeal. |
| `GET /api/support/disputes/mine/` | student | Their appeals, newest first; `is_new` = ruled after `integrity_seen_at`. |
| `GET /api/support/disputes/?status=open\|upheld\|overturned\|all` | trainer | The queue (default open): student, exam, filed date, status, response, decision note, `case_key` for the case-file link. |
| `GET/PATCH /api/support/disputes/<id>/` `{decision: uphold\|overturn, resolution_note}` | trainer | Rules on an OPEN appeal; the reply is required; a ruling is final (a second PATCH is 400, and no second appeal can be filed on that exam). |
| `GET /api/support/attention/`, `POST /api/support/attention/seen/` | both / student | Badge counts (see `docs/metrics.md`); seen sets `User.integrity_seen_at`. |

**Rulings.** *Uphold* changes no flag. *Overturn* sets every non-dismissed behavioural flag of the
appellant on that exam to dismissed, with the ruling as the review note, `reviewed_by` the trainer
and a `ReviewAuditLog` entry, like any review. Similarity pairs are not touched, so a classmate in
the same case keeps their outcome; by `metrics.voided_pairs` the appellant's points return on the
exam report, My results, Home and the leaderboard. Overturning a legacy row with no exam is refused
(it can only be upheld). Rules live in `support/integrity.py`.

**Student side.** My results shows one Trainer review block per exam with a decision: a headline
(`Points withheld: plagiarism confirmed (−N)` / `Plagiarism confirmed: no points withheld` /
`Reviewed — no action taken` / `Decision overturned: points restored`, from
`integrity_outcomes` → `integrity` on `/api/leaderboard/me/exams/`), the trainer's note once, then
the appeal area ("Respond to this decision" → response + Submit, or the status: waiting / upheld /
overturned with the trainer's reply); per-attempt lines sit in a collapsed Details disclosure. A
Disputes page (`/disputes`, students only) lists their appeals with the decision, their response,
the ruling and a link to the exam's review box (`/results?exam=<id>`).

**Trainer side.** Disputes (`/dashboard/support/disputes`) filters Open / Upheld / Overturned / All;
each row links the case file (`from=dispute:<id>`). The appeal page shows the original decision note,
the response, the case link and Uphold / Overturn, each with a required reply; Overturn says "Their
behaviour flags on this exam become dismissed; their points are restored. Classmates are not
affected." The case file (`appeals` on the investigation detail) and the student page's Integrity
tab (`appeal` on each `integrity_cases` entry) show "Appeal pending" with the response and a link.

**Attention signals.** Sidebar badges: student My results = new decisions, Disputes = new rulings;
trainer Investigation = cases to decide, Disputes = open appeals. The student's Home shows the newest
new item as a banner; the trainer's Overview says "N appeals and M cases waiting for you". Counts are
fetched once per page visited (no polling). Opening My results or Disputes marks everything seen.

**AI exam summary.** The input ends with the student's integrity outcome on the exam (points withheld
after a plagiarism review / decision overturned / confirmed with no points withheld / reviewed with no
action, plus an appeal under review or upheld), and withheld questions are marked in the per-question
lines; a `Result:` line gives the counted outcome (a voided question is not solved, and the line
says how many were not counted); the prompt says to state a withholding neutrally, never praise a
withheld score, and never call a not-counted question solved. The stored
summary is deleted whenever that outcome changes (either flag review endpoint, filing an appeal,
uphold, overturn), so it is rewritten on the next view.

**Migration** (`support/0002_appeals_per_exam`): `resolved` → `upheld`, `escalated` → `open` (it was
never decided), `exam` backfilled from the flag's submission where the flag still exists (left null
otherwise, shown by the flag's exam or "Exam no longer available"), `decision_note` from that flag's
note; it prints the counts. `accounts/0004_user_integrity_seen_at` sets existing accounts' seen time
to the migration time so old decisions don't all show as new.

### Integrity Monitoring — Model Accuracy Dashboard

```
GET /api/plagiarism/monitoring/
```

A meta-layer that answers: "how well is the plagiarism detection system itself performing?" — not what it detected, but how accurate and complete the detection is.

**Top-level KPIs:**
- **Pending Review** — flags awaiting trainer decision (the backlog)
- **Behavioural Precision** — `confirmed / (confirmed + dismissed)` for reviewed behavioural flags. NOT `confirmed / total_fired`. The denominator is only flags a trainer actually acted on. With 205 pending and 3 reviewed, precision is based on 3 data points — statistically meaningless until more flags are reviewed.
- **Similarity Precision** — same formula for similarity pairs
- **Behavioural Coverage** — `submissions with behavioural_check_done=True / total submissions`. Tells you whether the pipeline ran, not how many were flagged.
- **Similarity Coverage** — same for `similarity_check_done`. Will never reach 100% by design — Phase 2 only processes suspects (risk ≥ `compare_min_risk` or 3+ signals).

**Signal Effectiveness table:**
Per signal (paste, time, tab_switch, submission_surprise), shows:
- **Fired** — how many BehaviouralFlags have this signal's score > 0
- **Reviewed** — `confirmed + dismissed` for that subset (the denominator)
- **Confirmed** — how many a trainer confirmed as real cheating
- **Precision** — `confirmed / reviewed` (not `confirmed / fired`)

Why this matters: Paste fired on 127 flags but only 3 were reviewed (2 confirmed + 1 dismissed) → 66.7% precision. The other 124 are still pending. Precision numbers are only meaningful after sufficient trainer review volume.

**Confidence Breakdown:**
Shows confirmation rate split by flag `confidence` level (confidence that the flag indicates misconduct). If HIGH confidence (3+ signals) has lower precision than LOW confidence (1 signal), the confidence model is miscalibrated. The UI label is "Flag confidence" everywhere, coloured high = red, medium = amber, low = neutral (`frontend/src/utils/metrics.ts`).

**Similarity by Score Range:**
Breaks down pairs into 0.9–1.0, 0.8–0.9, 0.5–0.8 buckets with confirmed counts. Shows where in the similarity range actual cheating concentrates — informs threshold tuning.

**Coverage Gaps by Exam:**
For each exam, shows what % of submissions have `behavioural_check_done=True` and `similarity_check_done=True`. 0% behavioural = pipeline never ran. The two sources of truth can diverge: `BehaviouralFlag` records may exist (from seed data or old runs) but `behavioural_check_done` is False because the check was not done through the Celery task.

**Drift Detection:**
Compares behavioural flag count in the last 7 days vs the prior 7 days. A sudden spike (e.g., "flags doubled: 0 → 138") can indicate a new cheating vector or a policy change that caught a previously-missed pattern.

---


### Metrics — One Source of Truth

Every rate a page shows comes from `backend/analytics/metrics.py`, never from a
view's own arithmetic. Before this, the same exam showed 60.5% "accepted" on
exam history (passed ÷ all attempts) and 76% on exam ops (students whose latest
attempt passed ÷ students), and the flag rate was 65.3% on one page and 11.2%
on another (different denominators).

- **Success rate** (since 2026-10-07) = how many students passed the exam. A student passes
  an exam by solving at least half of its questions (all of them count, attempted or not;
  pending ignored, refunded errors never solve; a question voided for confirmed plagiarism is
  not solved, since 2026-10-08). Exam = students who passed ÷ took; student =
  exams passed ÷ exams taken; section = per exam, its students who passed ÷ took; question =
  students who solved it ÷ attempted it. API field still `accepted_rate`. The separate
  "Solved" rate (pairs solved ÷ pairs attempted) and the old passed ÷ graded submissions
  definition are gone.
- **Flagged students** = students with a behavioural flag ÷ students who took the exam (the only integrity rate)
- **Took the exam** = students who submitted ÷ enrolled
- **Flags to review** = pending behavioural flags; **Risk** = risk_score × 100

Population is always `role='student'` and not superuser. `exam_summaries()`
returns all exam-level fields in four grouped queries; exam history, exam ops,
investigations and the overview spread the same dict, and
`analytics/tests_consistency.py` asserts every endpoint returns identical values
for the same exam. Health thresholds for flagged students: watch at 30%, at risk
at 50%. Full table: `docs/metrics.md`.

## 12. Cost Analysis Engine

### Cost Formula

```python
# dashboard/views.py

_FARGATE_VCPU_PER_HOUR = 0.04048   # USD per vCPU-hour
_FARGATE_GB_PER_HOUR   = 0.004445  # USD per GB-hour
_CONTAINER_VCPU        = 0.5       # matches --cpus=0.5
_CONTAINER_GB          = 0.125     # matches --memory=128m
_COLD_START_MS         = 10000     # Fargate task init (conservative)

def _cost_for_ms(exec_ms):
    total_ms = (exec_ms or 500) + _COLD_START_MS
    hours = total_ms / 3_600_000
    return (hours * _CONTAINER_VCPU * _FARGATE_VCPU_PER_HOUR +
            hours * _CONTAINER_GB    * _FARGATE_GB_PER_HOUR)
```

Note: the 10-second cold start dominates for fast code (sub-second Python). Most of the cost is container spin-up, not execution. This is exposed as an optimization suggestion in the UI.

### Fixed Monthly Infrastructure

| Component | Monthly Cost | Notes |
|---|---|---|
| Redis (ElastiCache t3.micro) | $13.00 | us-east-1, on-demand |
| PostgreSQL (RDS t3.micro) | $26.00 | us-east-1, on-demand |
| Celery worker | $0.00 | Fargate model — no dedicated machine |
| **Fixed total** | **$39.00** | |

### Optimization Suggestions (Auto-Generated)

The cost view generates context-aware suggestions based on actual submission data:

1. **High failed-submission cost**: if >35% of compute is on failed submissions → add partial feedback
2. **High retry rate**: if >30% of submissions are retries → show compiler errors inline
3. **Cold start dominance**: if cold start is >60% of total time → pre-warm containers
4. **Slow languages**: if avg exec > 2000ms for a language → stricter time limits
5. **Low pass rate**: if overall <50% → review question difficulty calibration
6. **Spot instances**: if >500 total submissions → switch Celery workers to EC2 Spot

---

## 13. Authentication and Authorization

### JWT with Simple JWT

```
ACCESS_TOKEN_LIFETIME  = 1 day   (development; production should be 15min)
REFRESH_TOKEN_LIFETIME = 7 days

Flow:
  POST /api/token/       → returns {access, refresh}
  POST /api/token/refresh/ → returns {access} using refresh token
```

### Role-Based Guards

All views check `request.user.role` explicitly. There is no Django permission framework in use — role is checked inline:

```python
if request.user.role != 'trainer':
    return Response({'error': 'Forbidden'}, status=403)
```

Roles: `student`, `trainer`, `admin`.

### SSE Authentication Special Case (legacy)

The exam page no longer uses SSE. It polls `GET /api/submissions/{id}/status/` with the normal `Authorization: Bearer` header, so result delivery needs no token in the URL. The old stream endpoint has been removed; it authenticated this way:

```
GET /api/submissions/{id}/stream/?token={access_token}
```

EventSource (browser SSE API) does not support custom headers, so the SSE view reads both the `HTTP_AUTHORIZATION` header and the `?token=` query param, validating both identically via `AccessToken(token_str)`.

The executor's internal endpoints (`/internal/jobs/…`) accept neither: they are authenticated only by a per-job token in the body, `HMAC-SHA256(JOB_SIGNING_SECRET, "job:" + job_id)`, which only the relay can mint; complete and fail also need the lease token (§5.5).

### Rate Limiting

```python
# settings.py
'DEFAULT_THROTTLE_RATES': {
    'anon':        '20/hour',   # login attempts, unauthenticated
    'user':        '2000/hour', # general authenticated use (dashboards make many reads per view)
    'submissions': '30/hour',   # submission endpoint specifically
}
```

Submission throttle is tighter because each submission runs untrusted code against every test case. Unthrottled, one user's submissions would be a compute denial-of-service on the executor.

---

## 14. Concurrency and Scaling

### How 10,000 Concurrent Students Was Approached

**Job queue architecture is the key.** Without a queue, 2000 simultaneous submissions would each run student code inside a Django request, exhausting the web workers immediately.

With the job pipeline (§5), for Python and JavaScript:
1. Django receives the submission and writes it, plus its outbox job, in one transaction. The request never calls the queue.
2. It returns 201 to the student immediately.
3. The relay publishes pending jobs in batches, and the executor drains them at a controlled concurrency.

C++ and Java take the same shape through Celery + Redis.

```
10,000 students submit simultaneously
           │
           ▼
Django (Gunicorn, N workers)
  - validate auth
  - lock the student's User row, count attempts (row lock + unique constraint, not a Redis counter)
  - INSERT Submission + INSERT jobs_job (pending), one transaction
  - return 201
           │
           ▼
Postgres outbox absorbs the spike
  - 10,000 pending jobs, 0 dropped: they exist as soon as the request commits
           │
           ▼
Relay publishes (SKIP LOCKED, up to 50 per tick, every 0.5 s)
  - local: a thread pool in the relay runs the handler
  - production (live 2026-10-05): SQS codemas-exec buffers, Lambda scales per message
           │
           ▼
Executor drains
  - one job = claim → run each test in a sandboxed child → complete
  - results reach the browser on its next status poll (1 s → 3 s)
```

### Dashboard Polling Cache

The trainer cohort dashboard was polling every 10 seconds. With 300 real students, this produced 30 requests/second hitting the database. Fixed by Redis caching the dashboard response with a 10-second TTL and adding jitter to prevent all clients polling synchronously:

```python
# Dashboard response cached 10s
cache_key = f"dashboard:trainer:{request.user.id}"
cached = cache.get(cache_key)
if cached:
    return Response(cached)
# ... compute ...
cache.set(cache_key, data, timeout=10)
```

Jitter: students submit at different times, so their submission status polls (1 s backing off to 3 s, then 10 s after 2 minutes) start at different moments and spread out naturally.

### The 2000 Concurrent User Number

This is a real usage number from running CodeMas with actual students at Masai School, not a synthetic load test. It is both a strength (validated against real load) and a limitation (not tested beyond 2000 with instrumented load testing).

**What would be added from day one now:**
- k6 load tests simulating 2000 VUs all submitting simultaneously
- Measure p95 latency on the submission endpoint AND on submit-to-result (status poll shows a grade)
- Deadline spike scenario: all users submit in a 30-second window
- Set pass/fail thresholds in CI pipeline
- The 30-second spike is the hardest pattern and the primary justification for the job queue

### Concurrency Tests Written

- Jest unit tests: score parser, attempt limiter, result storage
- Integration tests: full submit-to-result flow through the local transport, running the real executor handler and sandbox (`jobs/tests/test_e2e.py`)
- Real exam sessions: monitored EC2 CPU, memory, container count, scaled gradually

---

## 15. Infrastructure Cost Comparison — EC2 vs Fargate vs Lambda

### At 5,000 Submissions Per Month

```
COST COMPARISON (5,000 submissions/month)

EC2 (t3.small)
  Redis ElastiCache:  $13.00
  RDS t3.micro:       $26.00
  EC2 t3.small:       $15.00 (always on, regardless of submissions)
  Compute:            included in EC2
  ─────────────────────────────────
  TOTAL: $54.00/month

Fargate (containers on demand)
  Redis ElastiCache:  $13.00
  RDS t3.micro:       $26.00
  Celery worker:       $0.00 (no dedicated EC2)
  5k submissions:      $0.30
  ─────────────────────────────────
  TOTAL: $39.30/month  (saves $14.70 vs EC2)

Lambda (serverless functions)
  Redis ElastiCache:  $13.00
  RDS t3.micro:       $26.00
  Lambda 5k invokes:   $0.007
  ─────────────────────────────────
  TOTAL: $39.01/month  (saves $14.29 vs EC2)
```

### Crossover Point: EC2 vs Fargate

```
EC2 fixed cost:    $54.00/month (flat)
Fargate:           $39.00 + ($0.30 / 5000) × N

Solve for N where Fargate == EC2:
  39.00 + (0.30/5000) × N = 54.00
  (0.00006) × N = 15.00
  N = 250,000 submissions/month

Below 250,000: Fargate is cheaper
Above 250,000: EC2 becomes cheaper (flat cost amortized)
```

```
COST vs SUBMISSIONS

Cost ($)
  │
60│  EC2 (flat $54) ─────────────────────────────────────────────
  │                                          ╱ Fargate
50│                                        ╱
  │                                      ╱
40│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─╱
  │  Fargate ($39 + compute)         ╱ crossover ~250k submissions
30│                                ╱
  │                              ╱
20│                            ╱
  │                          ╱  Lambda ≈ Fargate at this scale
10│                        ╱    (Lambda wins on compute cost
  │                      ╱      but requires full rewrite)
  └────────────────────────────────────────────────────────────►
       50k    100k    150k    200k    250k   300k   submissions
```

### Lambda Tradeoffs Summary

| Factor | Lambda | Docker/EC2 |
|---|---|---|
| Cold start | 100ms | 500ms warm, 8-15s cold (Fargate) |
| Persistent connections | Cannot hold (no longer needed: results are polled) | Yes |
| Always-running process | Cannot (terminates per invoke) | Yes (Celery Beat) |
| Free tier | 5.2M invocations/month | No |
| Rewrite required | Only for execution (outbox + relay + SQS); Beat, AI and plagiarism stay on Celery | No |
| Cost at 5k/month | $39.01 | $39.30 (Fargate), $54 (EC2) |
| Savings vs EC2 | $14.99/month | $14.70/month (Fargate) |
| Verdict at this scale | Not worth rewrite | Fargate is right choice |

**Revisited (October 2026):** the full rewrite was never needed. Polling removed the persistent-connection requirement, and only execution moved: Python and JavaScript run on the job pipeline, whose executor runs as a Lambda in production since 2026-10-05 (`PIPELINE_LANGUAGES=python,javascript`). Beat, AI and plagiarism stay on Celery (§10). The costs above are the original estimates and haven't been re-measured.

---

## 17. Known Gaps and Honest Limitations

Being clear about limitations demonstrates better engineering judgment than overselling.

### Plagiarism Detection Gaps

| Scenario | Detection Status | Why |
|---|---|---|
| Manual retyping (no paste events) | **Not detected by paste signal** | No clipboard event fires. Time signal may catch it if fast enough. |
| AI-generated code (typed slowly) | **Not detected** | Looks like genuine work if pasted manually or typed. No corpus of "AI output" to compare against. |
| Pre-exam memorization | **Not detected** | Cannot detect without a reference corpus of solutions memorized before the exam. |
| Collusion between two slow typists | **Not detected by either layer** | Both have clean behavioural signals. Neither is a suspect. O(K×N) approach misses pairs where K=0. |
| Cross-language copying (Python→JavaScript) | **Not detected** | Normalization is language-specific. Cross-language similarity requires semantic analysis (CodeBERT). |

### Technical Debt

1. **JavaScript normalization uses regex, not AST**: Python normalization uses `ast.parse()` which is structural. JavaScript normalization uses regex-based identifier substitution — it cannot handle all syntax correctly. A proper JS AST normalizer (using `esprima` or similar) would be more accurate.

2. **`snapshot_score` field name is misleading**: The field was intended for code-growth monitoring but was repurposed for tab switch score to avoid a database migration. A future migration should rename it to `tab_score`.

3. **TF-IDF at scale**: At 2000 submissions, TF-IDF runs in ~50ms. At 100,000+ submissions, this becomes a bottleneck. The migration path is CodeBERT embeddings stored at submission time and pgvector/FAISS at query time.

4. **No load testing framework**: Real-world 2000 concurrent users was the validation, not instrumented load tests. k6 tests from day one would provide p95 SLAs and regression detection.

5. **JWT access token lifetime is 1 day**: This is a development setting. Production should be 15 minutes with refresh token rotation.

6. **Dashboard queries are N+1**: The `DashboardView` has a loop over all students to compute stats. At 10,000 students, this is 10,000 ORM queries. Production fix: use `annotate()` with subqueries or a materialized view.

### Infrastructure Gaps

1. **No horizontal scaling configuration**: Gunicorn runs a fixed `gthread` pool (`--workers 2 --threads 8`, see `backend/Dockerfile`) on one Railway instance; there is no autoscaling rule. Result delivery is now short status polls, so no long-lived connections need async workers.

2. **Executor cold start not measured**: the Lambda is live (2026-10-05), and the first submission after an idle period pays a cold start. It hasn't been measured yet; a warm-up submission or provisioned concurrency are the options.

3. **No circuit breaker on the executor**: if Django is unreachable from the executor, every delivery fails, and on SQS each message heads for the DLQ after 3 receives. The jobs themselves are safe in Postgres, and the sweep backstop republishes them, but nothing pauses the relay or tells students "execution unavailable".

4. **C++ and Java are not sandboxed**: both are selectable in the exam UI. They run through the legacy Celery task's `run_local` on the Celery worker host, with no sandbox. All it does is strip the environment, apply a 10 s timeout, and drop to `nobody` when running as root. There are no rlimits and no isolation from the host. It is marked development only. Moving them onto the executor needs a heavier image with a compiler and a JDK.

5. **Python/JavaScript isolation is process-level**: one Lambda; the handler runs student code in a constrained child process (rlimits, empty environment) inside the function's Firecracker microVM. There is no kernel boundary between grader and child. Guardrails: no secrets or answers in the Lambda, per-job tokens. Two known limits are **accepted**, found by the 2026-10-04 production smoke test and still present at the 2026-10-05 go-live:
   - **R1, egress.** Real Lambda refuses the seccomp socket filter, so student code can reach the internet. Bounded by CPU time per test, concurrency 5, 3 attempts and the submission throttle.
   - **R2, role credentials.** Student code can read the role's AWS credentials, and the role can `ReceiveMessage`, `DeleteMessage` and `ChangeMessageVisibility` on `codemas-exec`. A determined student with a working solution could take a classmate's queued message, claim that job first, read the classmate's code and test inputs, and post outputs that forge a pass or a fail. They can also delay other students' grading by deleting or hiding messages. Exposure is highest under an exam-deadline backlog (concurrency 5).
   - Still holds: the signing secret and the expected answers never enter the Lambda, and a student can't pass their own submission without correct output.

   The real fix is future work: the two-function split used by online judges, where the grader invokes a runner with a zero-permission role, in a VPC with no NAT or internet gateway and a security group with no outbound rules, and reads its return value.

---

## 18. Testing Strategy

The test suite covers two layers: unit tests for pure algorithmic functions (no database), and integration tests for the full API request-response cycle against a real test database.

---

### Test Stack

| Tool | Purpose |
|---|---|
| `django.test.SimpleTestCase` | Unit tests — no DB, fastest possible |
| `django.test.TestCase` | Integration tests — spins up a real test DB, wraps each test in a transaction and rolls back |
| `rest_framework.test.APIClient` | Makes HTTP calls to API views; uses `force_authenticate()` to bypass JWT in tests |
| `unittest.mock.MagicMock` | Fakes Django ORM querysets for pure function tests — avoids any DB dependency |
| `unittest.mock.patch` | Patches Celery `.delay()` calls so tasks don't actually run during tests |

Run command:
```bash
venv/bin/python manage.py test plagiarism
```

---

### Layer 1 — Unit Tests (46 tests, ~0.02s)

Located in `plagiarism/tests.py`. No database. Each signal function is a pure function — it takes a submission object and returns a `(float, list[str])` tuple. Tests use `SimpleNamespace` to construct fake submission objects without any model machinery.

**What's covered:**

| Test Class | Tests | What it verifies |
|---|---|---|
| `PasteSignalTest` | 7 | All paste ratio thresholds: 0%, 30%, 50%, 70% boundaries |
| `TimeSignalTest` | 8 | All time ratio thresholds across easy/medium/hard difficulty baselines |
| `TabSwitchSignalTest` | 7 | All switch count thresholds including `None` edge case |
| `SubmissionSurpriseSignalTest` | 6 | All similarity bands; passed vs. failed status interaction |
| `ComputeBehaviouralRiskTest` | 7 | Flag confidence from signal count (1 → low, 2 → medium, 3+ → high), weighted score math, result shape |
| `Phase2SuspectSelectionTest` | 7 | Phase 2 compares the 3-signal (high confidence) student, not a 1-signal one below `compare_min_risk` (fast only, risk 0.30); a multi-attempt student is vectorised once (no self-pairs); `notify=False` (used by seed_data) skips the trainer email and AI explanation, also when passed to the exam-close entry point, which still records a completed `PlagiarismRun` (default stays `notify=True`) |
| `PolicyDecidesWhoIsComparedTest` | 3 | A 100% paste alone (risk 0.40) is compared and its pair flagged; raising the tab weight and rerunning brings a tab-switch-only student into the comparison; a stricter rerun clears a pending flag but keeps confirmed and disputed ones |
| `NormalizePythonTest` | 7 | Variable renaming, builtin preservation, comment/docstring stripping, identical-logic equality |
| `NormalizeJavascriptTest` | 5 | Same coverage for JS: keyword preservation, comment stripping, renaming |

**Key test — identical logic, different names:**
```python
def test_same_logic_different_variable_names_normalize_equal(self):
    code_a = "def solve(nums):\n    total = 0\n    for n in nums:\n        total += n\n    return total"
    code_b = "def compute(values):\n    acc = 0\n    for v in values:\n        acc += v\n    return acc"
    self.assertEqual(normalize_python(code_a), normalize_python(code_b))
```
This is the core guarantee the plagiarism system depends on: two functionally identical solutions with different variable names must produce the same normalized form for TF-IDF to flag them.

---

### Layer 2 — Integration Tests (40 tests, ~30s)

Each test class inherits from `BaseViewTest` which creates a shared fixture:
- 1 trainer, 2 students (alice, bob)
- 1 exam, 1 question
- 3 submission rows: alice has 2 attempts (failed → passed), bob has 1

The 3-row / 2-unique-student setup is intentional — it directly exercises the bug that was fixed in `CohortListView`.

**Coverage by view:**

| Test Class | Tests | Key assertions |
|---|---|---|
| `PolicyViewTest` | 7 | GET returns all policy fields; PUT updates DB, invalidates Redis cache, creates `PolicyVersion` with before/after snapshot |
| `BehaviouralFlagListViewTest` | 4 | 401/403 guards; `?status=` filter works |
| `BehaviouralFlagReviewViewTest` | 5 | Review updates `review_status`, `reviewed_by`, `review_note`; creates `ReviewAuditLog`; invalid status → 400 |
| `PlagiarismFlagReviewViewTest` | 3 | Same pattern for similarity flags |
| `CohortListViewTest` | 6 | Unique student count; ring detection; health color thresholds |
| `CohortDetailViewTest` | 3 | 404 on missing exam; response structure; rings built from similarity graph |
| `RerunExamChecksViewTest` | 3 | 202 + Celery `.delay()` called with correct args; 404 on missing exam |
| `PlagiarismRunListViewTest` | 4 | Returns all runs; `?exam_id=` filter; `policy_snapshot` in response |
| `MonitoringViewTest` | 5 | Precision formula; `None` when nothing reviewed; coverage tracks `behavioural_check_done` field |

---

### Regression Tests — Bugs That Were Actually Fixed

These tests encode real production bugs. If the fixes are reverted, these tests fail immediately.

**Bug 1 — Inflated student count:**
```python
def test_unique_student_count_not_submission_row_count(self):
    # alice has 2 attempts, bob has 1 → 3 rows but only 2 students
    resp = self.api.get('/api/plagiarism/cohorts/')
    row = next(r for r in resp.data if r['exam_id'] == self.exam.id)
    self.assertEqual(row['total_submissions'], 2)  # must be unique students
```
The old code used `.count()` which returned 3. The fix: `.values('student_id').distinct().count()`.

**Bug 2 — Precision denominator wrong:**
```python
def test_precision_uses_reviewed_denominator_not_total_fired(self):
    # 3 flags: 1 confirmed, 1 dismissed, 1 pending
    # precision = confirmed / (confirmed + dismissed) = 1/2 = 0.5
    # NOT 1/3 (which would count the pending flag in the denominator)
    precision = resp.data['summary']['behavioural']['precision']
    self.assertAlmostEqual(precision, 0.5)
```

---

### What's Not Tested (and Why)

| Area | Why excluded |
|---|---|
| `run_exam_plagiarism_check` task end-to-end | Runs Celery + spawns Phase 2 sub-tasks; requires a live Redis broker. Manual testing sufficient for a portfolio project. |
| Executor on real Lambda | No automated test; live since 2026-10-05, verified only by the go-live smoke test (`deploy/aws/smoke.sh`: Python and JS graded through the pipeline, no `JOB_SIGNING_SECRET` readable, R1 and R2 present as accepted). The handler and sandbox have their own suite (`lambda/exec/tests`, 79 tests, run on macOS and in a Linux Docker image). The pipeline is tested end to end through the local transport (`jobs/tests/test_e2e.py`). |
| C++/Java legacy execution (`run_local`) | External process on the Celery worker. Integration-tested manually; mocked in unit tests. |
| SSE stream (legacy) | Removed. `submissions/tests.py` checks the `/stream/` route now 404s. |
| Frontend Vue components | Vitest scaffolded (`App.spec.ts` exists); View Code algorithm is the highest-value candidate for unit tests given it's pure JS. |

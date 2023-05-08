# CodeMas — Product Requirements Document
### Real-Time Coding Exam Platform · Built for Entrupy Interview Prep
**Author:** Swanand Kadam · **Interviewer:** Drew Barclay, Senior Engineering Manager, Entrupy · **Date:** May 2026

---

## Why This Document Exists

This PRD is two things at once:

1. **A technical spec** for building CodeMas — a real-time coding exam platform for 10,000 concurrent students
2. **An interview map** — every feature is framed against what Entrupy actually builds, so Drew immediately sees you think like his team

> Every section has a **🔷 Entrupy Parallel** — the moment where Drew thinks *"oh, this is exactly what we do."*

---

## 1. Product Vision

### How to introduce this to Drew

> "CodeMas is an internal training, assessment, and knowledge-operations dashboard. It automates coding exam workflows, student account management and progress tracking. It helps trainer and expert teams create structured evaluations, process student submissions automatically, monitor cohort health, investigate weak spots, and expose explainable results through dashboards."

Every word in that introduction maps directly to Entrupy's job description. Drew will recognise all of it.

---

### Keyword Map

| What you say | Entrupy job description keyword |
|---|---|
| Internal training platform | *"Internal training platforms"* |
| Data annotation tool (test case builder) | *"Data annotation tools"* |
| Trainers encode expert knowledge into structured test cases | *"Tools to encode + expose knowledge for authentication team"* |
| Monitoring system that flags where students struggle | *"Monitoring systems to flag areas where knowledge is lacking"* |
| Similarity search across submissions (plagiarism) | *"Creating image search systems — similarity searching"* |
| Submission investigation tool | *"Custom search systems and data investigation tools"* |
| Result breakdown — explains why submission passed/failed | *"Interfaces to explain ML and expert system output"* |
| Trainer cohort dashboard | *"Internal dashboards"* |
| Role-based access (student/trainer) | *"Account management systems"* |
| Exam lifecycle, attempt policies | *"Policy tracking and change management systems"* |

---

### The actual product

CodeMas is a secure, scalable internal tooling platform for coding education — where students write code in a browser editor, submit it, and receive automated evaluation results in under 10 seconds, powered by an isolated Docker execution pipeline. Trainers use a suite of internal tools to build assessments, monitor cohort performance live, and investigate submission authenticity.

**One-line vision:** Remove all human bottlenecks from coding assessment at scale.

**Inspired by:** HackerRank, LeetCode, QingdaoU/OnlineJudge

### The Problem

| Before CodeMas | After CodeMas |
|---|---|
| Manual evaluation takes 5–7 trainer days per exam | Results in under 10 seconds |
| Weekly exams = 312 trainer-days/year on grading | Zero grading time — one FTE saved |
| 100 students max before quality degrades | 10,000 concurrent students |
| Plagiarism caught manually or not at all | Automated similarity detection |
| Feedback delayed by days | Feedback while problem is fresh |

### Business Case for CEO

- **Team:** 2.5 engineers (1 senior full-stack, 1 mid frontend, 0.5 DevOps)
- **Timeline:** 7 weeks to V1
- **Infrastructure cost:** ~$415/month for 10,000 concurrent students
- **ROI:** Eliminates one full-time trainer role spent purely on grading

---

## 2. Users & Roles

### 2.1 Student
Takes exams, writes and submits code, views results and performance history.

### 2.2 Trainer
Creates exams and questions, monitors cohort live, reviews plagiarism flags, views analytics.

### 2.3 Permissions Matrix

| Feature | Student | Trainer |
|---|---|---|
| View upcoming exams | ✓ | ✓ |
| Enter exam room | ✓ | ✓ (monitor only) |
| Submit code | ✓ | ✗ |
| View own results | ✓ | ✗ |
| View all students' results | ✗ | ✓ |
| Create exams + questions | ✗ | ✓ |
| View cohort dashboard | ✗ | ✓ |
| Review plagiarism flags | ✗ | ✓ |

> 🔷 **Entrupy Parallel:** Role-based access is the same pattern as Entrupy's internal tools — authentication experts vs. account managers vs. engineers all see different views of the same data. Drew builds this daily.

---

## 3. Feature Specifications

---

### Feature 1: Authentication System

**What it does:** Secure login with JWT access tokens and refresh tokens.

**How it works:**
- User registers with name, email, password, role (student/trainer)
- Password hashed with bcrypt — never stored in plaintext
- Login returns:
  - JWT access token (1 hour expiry) — sent in Authorization header
  - Refresh token (7 days) — stored in httpOnly cookie, never accessible to JavaScript
- Every API endpoint requires valid JWT. Unauthenticated = 401. Wrong role = 403.
- Logout invalidates refresh token in Redis blacklist

**Why httpOnly cookie for refresh token?**
JavaScript cannot read httpOnly cookies. Even if a student injects malicious JS into the page (XSS), they cannot steal the refresh token. This is defense in depth.

**Why short JWT expiry (1 hour)?**
If a JWT is stolen, it expires in 1 hour. Refresh tokens are stored server-side (Redis blacklist) so they can be revoked instantly on logout.

> 🔷 **Entrupy Parallel:** Entrupy serves enterprise customers in 60 countries — luxury brands, retailers, e-commerce platforms. Their internal tools handle sensitive authentication data. The same JWT + refresh token pattern protects their internal dashboards and customer support tools.

---

### Feature 2: Exam & Question Management

**What it does:** Trainers build exams with questions, test cases, difficulty levels, and time limits.

**How it works:**
- Trainer creates exam: title, description, scheduled date, duration
- Exam has a lifecycle: `draft → live → ended`
- Only `live` exams visible to students — draft = invisible
- Each question has:
  - **Sample test cases** — visible to students (they can test against these)
  - **Hidden test cases** — never sent to frontend, only fetched inside Docker container
- Test cases stored as JSON: `{ input: [], expected_output: "" }`
- Each question has configurable `time_limit_seconds` and `memory_limit_mb`

**Why hidden test cases matter:**
If test cases are sent to the frontend, a student can open DevTools, see the expected output, and hardcode it. The entire evaluation is compromised. Hidden test cases only exist in PostgreSQL and are fetched by the Celery worker inside the execution container — they never cross a network boundary to the student's browser.

> 🔷 **Entrupy Parallel:** This is exactly Entrupy's **data annotation tools** and **knowledge encoding systems**. Trainers encode expert knowledge (test cases, expected outputs) into a structured database. Authentication experts at Entrupy do the same — encoding what "authentic" looks like into structured data that drives automated decisions.

---

### Feature 3: Code Submission & Attempt Limiting

**What it does:** Students submit code, get instant acknowledgement, maximum 3 attempts per question.

**How it works:**
```
Student submits → API checks attempt count (PostgreSQL, atomic) →
if attempts >= 3: return 403, no execution triggered →
else: create Submission(status=pending) → push Celery job → return submission_id in <100ms
```

**Why attempt limiting must be server-side only:**
The frontend shows "2 attempts remaining" — but this is just UI. A student can open Postman and POST directly to the API, bypassing the UI entirely. The server must enforce the limit independently. We use PostgreSQL with an atomic check — no race conditions possible.

**Why does the API return in <100ms without waiting for results?**
Docker execution takes up to 10 seconds. If the API waited, 10,000 students submitting simultaneously = 10,000 Django threads blocked for 10 seconds = server crash. The API queues the job and returns `submission_id` immediately. The student's browser then independently opens an SSE connection to wait for results.

**Why PostgreSQL and not MongoDB for attempt counting?**
MongoDB doesn't support ACID transactions the same way. If two requests check the attempt count simultaneously (race condition), both see "2 attempts used" and both allow submission — student gets 4 attempts. PostgreSQL's atomic transactions prevent this: only one transaction can increment the count at a time.

> 🔷 **Entrupy Parallel:** Entrupy's authentication system has the same trust problem. Can you trust that a submitted authentication request is legitimate? Server-side enforcement, not client-side trust. Their **policy tracking systems** enforce business rules the same way our attempt limiter does — the client never gets to decide.

---

### Feature 4: The Execution Engine (Docker)

**What it does:** Runs student code in complete isolation against hidden test cases.

**Why Docker — the full story:**

We evaluated every option:

| Option | Why rejected |
|---|---|
| `exec(student_code)` in Python | No isolation — student can destroy your server |
| Node.js `vm2` module | JavaScript can't sandbox JavaScript. Unfixable escape vulnerability found 2023. Maintainers deprecated it. |
| Judge0 (hosted) | External API = external dependency during live exam. 3 critical CVEs in April 2024 — symlink attacks + SSRF to steal AWS credentials. Root cause: unsafe default configuration. |
| Isolate (bare C sandbox) | Strongest performance (~50ms startup vs Docker's ~500ms), used by Codeforces and IOI. But Linux-only — doesn't run on Mac dev machines. V2 candidate. |
| Docker | Works on Mac, portable, isolation via Linux namespaces + cgroups, explicit deny-everything defaults we control. **V1 choice.** |

**The two-file pattern:**
```
/tmp/{submission_id}/
  ├── student_solution.py   ← exactly what student submitted
  └── runner.py             ← trainer's judge (student never sees this)
                               imports student function,
                               calls it with each test case input,
                               prints PASS/FAIL + SCORE to stdout
```

**Container security constraints:**
```
--memory=50m          → prevents memory exhaustion
--cpus=0.5            → prevents CPU monopoly
--network=none        → no internet, no SSRF attacks
--timeout=5s          → kills infinite loops
--pids-limit=10       → prevents fork bombs
--read-only           → no symlink attacks on host filesystem
--user=sandboxuser    → non-root, can't escalate privileges
--env=none            → no host environment variables exposed
```

**Why this matters beyond CodeMas:**
This is the same architecture as any async processing pipeline — image processing, ML inference, video transcoding. The pattern is: receive job → queue it → worker processes in isolation → return result. The "Docker container" could be replaced with "ML model inference call" and the architecture is identical.

> 🔷 **Entrupy Parallel:** Entrupy processes authentication requests through an AI + computer vision pipeline. A submitted image goes into a processing queue, a worker runs the ML model against it, results come back. That's exactly our Celery + Docker pipeline. When Drew sees this, he sees someone who already understands how their image processing infrastructure works.

---

### Feature 5: Real-Time Result Delivery (SSE)

**What it does:** Student sees results within 10 seconds of submitting, with no polling.

**Why SSE and not WebSockets:**
WebSockets are bidirectional — both sides can send messages. For result delivery, only the server ever sends to the client. SSE is unidirectional (server → client only) and much simpler. No WebSocket handshake, no connection management library, works over standard HTTP.

**How it works:**
```
1. Student submits → gets submission_id
2. Frontend opens: GET /api/submissions/{id}/stream/
   (This is an SSE connection — stays open)
3. Django subscribes to Redis channel: result:{submission_id}
4. Celery finishes execution → publishes result to Redis channel
5. Django receives Redis event → pushes SSE event to browser
6. Vue receives event → updates UI → SSE connection closes
```

**What if student refreshes mid-execution?**
- Code auto-saved to localStorage every 30 seconds
- SSE supports `Last-Event-ID` header — on reconnect, Django replays missed events
- Result cached in Redis with 1hr TTL — reconnection always finds the result

> 🔷 **Entrupy Parallel:** Entrupy's authentication tools need to show results to operators in real-time as items are processed. The same SSE pattern — or a polling equivalent — drives their **monitoring systems** and **internal dashboards** that show authentication pipeline status live.

---

### Feature 6: Plagiarism Detection (The Trust Layer)

**What it does:** Automatically flags suspiciously similar code submissions for trainer review.

**Why this is the most Entrupy-relevant feature:**
Entrupy's entire business is built on trust and authenticity verification. One fake luxury bag authenticated as genuine destroys a brand relationship. On CodeMas, one plagiarised exam result destroys the certification's credibility. Same problem, different domain.

**How it works:**
```
Step 1: Tokenize submitted code
        → strip comments
        → normalize whitespace  
        → extract tokens (keywords, operators, identifiers)

Step 2: Build token frequency vector for each submission
        → { "for": 3, "if": 5, "return": 2, "sum": 4 ... }

Step 3: Compare vectors using cosine similarity
        → measures angle between vectors, not absolute values
        → handles different code lengths fairly

Step 4: If similarity score > 85% → create PlagiarismFlag
        → stores both submission IDs + similarity score

Step 5: Trainer reviews flag → marks as reviewed or dismissed
        → auto-disqualification NEVER happens
        → human review always required
```

**Why cosine similarity?**
Two submissions might solve the problem identically but one is 20 lines and one is 40 lines (more comments, different variable names). Raw token count comparison would miss this. Cosine similarity compares the *shape* of the token distribution, not the absolute count — fairer comparison.

**Why async? Why not block the student's result?**
Plagiarism detection has to compare against ALL other submissions for the same question. At 10,000 students, that's potentially 9,999 comparisons per submission. Running this synchronously would add minutes to result delivery. It runs as a separate Celery job after the result is stored — student gets their result in 10 seconds, plagiarism check happens in the background.

**The false positive story:**
> "We deliberately chose not to auto-disqualify. A similarity score above 85% could mean plagiarism — or it could mean two students independently chose the same elegant solution to a simple problem. The flag surfaces it for human review. The trainer makes the call. Our job is to make the trainer's review efficient, not to replace their judgment."

> 🔷 **Entrupy Parallel:** Entrupy's AI returns an authentication confidence score — but a human expert makes the final call on edge cases. Their system **explains ML output** to authentication experts who review flagged items. Our plagiarism flag is the same pattern: AI surfaces the signal, human applies judgment.

---

### Feature 7: Trainer Cohort Dashboard

**What it does:** Live view of the entire exam cohort — submissions, scores, flags — updating every 10 seconds.

**How it works:**
```
Trainer opens dashboard
       ↓
Every 10 seconds: GET /api/exams/{id}/cohort/
       ↓
Django checks Redis: exam:{examId}:cohort (TTL: 10 seconds)
       ↓
Cache hit → return cached JSON (no DB query)
Cache miss → query PostgreSQL → store in Redis → return
       ↓
Vue renders:
  - Total enrolled / submitted / not yet submitted
  - Score distribution histogram
  - Submissions per minute timeline
  - Plagiarism flags with similarity scores
  - Per-student drill-down
```

**Why polling and not SSE/WebSockets for the dashboard?**
10-second staleness is acceptable for a monitoring dashboard — trainers don't need millisecond updates. Polling is simpler to implement, simpler to cache, and easier to scale. 100 trainers polling every 10 seconds = 10 requests/second hitting a Redis cache. Trivial load.

**Why Redis cache with 10-second TTL?**
Without the cache, every trainer poll hits PostgreSQL — aggregating submissions, calculating score distributions, counting by-minute rates. Complex queries, high load during peak exam time. With Redis: first trainer to poll triggers the DB query, result cached for 10 seconds. Next 99 trainers hit cache. PostgreSQL barely notices.

> 🔷 **Entrupy Parallel:** This is literally Entrupy's **monitoring systems and analytics work** — flagging areas where knowledge is lacking, tracking authentication volume, showing distribution of results. Drew builds dashboards exactly like this. He will recognise this pattern immediately.

---

## 4. Architecture Decisions Summary

| Decision | Chosen | Rejected | Why |
|---|---|---|---|
| Code sandbox | Docker | vm2 (JS escape 2023), Judge0 (3 CVEs 2024), Isolate (Linux-only) | Portable, secure defaults, explainable |
| Real-time results | SSE | WebSockets | One-way push, simpler, no library needed |
| Job queue | Celery + Redis | Django threads, Lambda | Absorbs 10k spike, retries, horizontal scaling |
| Structured DB | PostgreSQL | MongoDB | ACID transactions for attempt counting |
| Unstructured data | MongoDB | PostgreSQL JSONB | Code blobs, logs — flexible schema |
| Cache + broker | Redis | Memcached | Pub/sub needed for SSE channel |
| Plagiarism | Cosine similarity | MOSS, AST analysis | No external dependency, runs async |
| Frontend | Vue 3 SPA | SSR, SSG | Authenticated app, no SEO needed |

---

## 5. Data Models

### PostgreSQL

**Users**
```
id              UUID, primary key
email           VARCHAR(255), unique, indexed
password_hash   VARCHAR(255), bcrypt
name            VARCHAR(100)
role            ENUM: student / trainer
batch_id        VARCHAR(50), nullable
created_at      TIMESTAMP
```

**Exams**
```
id                UUID, primary key
title             VARCHAR(255)
description       TEXT
scheduled_at      TIMESTAMP
duration_minutes  INTEGER
status            ENUM: draft / live / ended
created_by        UUID, FK → Users
```

**Questions**
```
id                  UUID, primary key
exam_id             UUID, FK → Exams
title               VARCHAR(255)
description         TEXT
function_name       VARCHAR(100)
difficulty          ENUM: easy / medium / hard
marks               INTEGER
time_limit_seconds  INTEGER, default 5
memory_limit_mb     INTEGER, default 50
```

**TestCases**
```
id               UUID, primary key
question_id      UUID, FK → Questions
input            JSONB
expected_output  TEXT
is_hidden        BOOLEAN
order_index      INTEGER
```

**Submissions**
```
id               UUID, primary key
student_id       UUID, FK → Users
question_id      UUID, FK → Questions
exam_id          UUID, FK → Exams
language         VARCHAR(20)
attempt_number   INTEGER (1–3)
status           ENUM: pending / running / completed / error
submitted_at     TIMESTAMP
```

**Results**
```
id                UUID, primary key
submission_id     UUID, FK → Submissions
passed_cases      INTEGER
total_cases       INTEGER
score             DECIMAL(5,2)
execution_time_ms INTEGER
error_message     TEXT, nullable
```

**PlagiarismFlags**
```
id                UUID, primary key
submission_id_1   UUID, FK → Submissions
submission_id_2   UUID, FK → Submissions
similarity_score  DECIMAL(5,4)  ← 0.0 to 1.0
flagged_at        TIMESTAMP
reviewed          BOOLEAN, default false
reviewed_by       UUID, FK → Users, nullable
```

### MongoDB

**submission_logs**
```
submission_id     → ref to PostgreSQL Submissions.id
code              full student code
stdout            raw container output
stderr            error output
test_case_results [ { input, expected, actual, passed } ]
container_logs    full Docker logs
```

**execution_metrics**
```
submission_id       → ref to PostgreSQL
container_startup_ms
execution_ms
memory_used_mb
worker_id
```

### Redis Keys

```
result:{submissionId}       JSON result. TTL: 1 hour
exam:{examId}:cohort        JSON cohort summary. TTL: 10 seconds
blacklist:{token}           "1" — invalidated JWT. TTL: token expiry
attempts:{studentId}:{questionId}  Integer count. TTL: exam duration + 1hr
```

---

## 6. API Endpoints

### Auth
```
POST /api/auth/register/     Register
POST /api/auth/login/        Login → JWT + refresh token
POST /api/auth/refresh/      Refresh access token
POST /api/auth/logout/       Invalidate refresh token
```

### Exams
```
GET    /api/exams/                    List exams
POST   /api/exams/                    Create exam (trainer)
GET    /api/exams/{id}/               Exam details
PATCH  /api/exams/{id}/               Update exam (trainer, draft only)
GET    /api/exams/{id}/questions/     List questions
POST   /api/exams/{id}/questions/     Add question (trainer)
GET    /api/exams/{id}/cohort/        Live cohort stats (trainer)
```

### Submissions
```
POST   /api/submissions/              Submit code
GET    /api/submissions/{id}/         Result
GET    /api/submissions/{id}/stream/  SSE stream
GET    /api/submissions/?exam_id={id} Student history
```

### Plagiarism
```
GET    /api/plagiarism/?exam_id={id}  List flags (trainer)
PATCH  /api/plagiarism/{id}/review/   Mark reviewed (trainer)
```

---

## 7. Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | Vue 3 + Vite | Composition API, fastest build, Entrupy stack |
| State | Pinia | Vue 3 native, simpler than Vuex |
| Editor | CodeMirror 6 | Best browser code editor |
| Charts | ECharts | Handles large datasets |
| HTTP | Axios | JWT interceptors, error handling |
| Real-time | Native EventSource (SSE) | One-way push, no library |
| Backend | Django 4.2 + DRF | Batteries included, Celery native |
| Auth | Simple JWT | Industry standard |
| Async | Celery | Django native, proven at scale |
| Broker | Redis | Also cache + pub/sub |
| Structured DB | PostgreSQL | ACID for attempt counting |
| Unstructured DB | MongoDB | Code blobs, execution logs |
| Sandbox | Docker | Isolation, Mac dev support |
| App server | Gunicorn + Uvicorn workers | Async request handling |
| Proxy | Nginx | Static files, SSL, proxy |

---

## 8. Build Order

| Phase | What ships | Why this order |
|---|---|---|
| 1 | Django setup + all models | Foundation everything else depends on |
| 2 | Auth (JWT + refresh tokens) | Every endpoint needs this |
| 3 | Exam + Question CRUD | Trainers need data before students can submit |
| 4 | Submission API + attempt counting | Core student action |
| 5 | Celery + Redis job queue | Decouple API from execution |
| 6 | Docker execution engine | The hardest, most impressive part |
| 7 | SSE result delivery | Completes the submission loop |
| 8 | Plagiarism detection | Trust layer — high Entrupy relevance |
| 9 | Vue frontend + CodeMirror | Student-facing exam room |
| 10 | Trainer cohort dashboard | Monitoring layer |

---

## 9. Non-Functional Requirements

| Requirement | Target |
|---|---|
| API response time (non-execution) | < 200ms p95 |
| Submission acknowledgement | < 100ms |
| End-to-end result delivery | < 10 seconds |
| Concurrent students | 10,000 |
| Submission success rate | > 99% |
| Container failure rate | < 1% |
| API uptime during live exam | 99.9% |

---

## 10. Security Architecture

**The principle:** Default deny everything. Student code is hostile until proven otherwise.

| Threat | Mitigation |
|---|---|
| Attempt limit bypass | Server-side enforcement only. Frontend is supplementary. |
| Hidden test case exposure | Never sent to frontend. Fetched inside Docker only. |
| Container escape (vm2 style) | Docker uses kernel namespaces — not JS-level sandboxing |
| Container escape (Judge0 symlink CVE) | `--read-only` filesystem mount |
| SSRF attacks (Judge0 metadata CVE) | `--network=none` — no network access at all |
| Fork bombs | `--pids-limit=10` |
| Memory exhaustion | `--memory=50m` hard limit |
| Infinite loops | 5-second container timeout |
| JWT theft | Short expiry (1hr) + httpOnly refresh tokens |
| XSS stealing tokens | Refresh token in httpOnly cookie, inaccessible to JS |
| Submission spam | Rate limiting per student on submission endpoint |
| Large payload attacks | Code submissions size-limited to 50KB before Docker spawn |

---

## 11. Out of Scope (V1)

- Mobile app
- Email notifications
- Payment / billing
- Video proctoring
- Auto-scaling (manual EC2 sizing for V1)
- AST-based plagiarism (token similarity is V1, AST is V2)
- More than Python + JavaScript

---

## 12. The Entrupy Interview Story

When Drew asks "walk me through your architecture" — connect every layer back:

| CodeMas | Entrupy equivalent |
|---|---|
| Docker execution pipeline | Image processing / ML inference pipeline |
| Celery job queue | Async authentication request processing |
| Plagiarism detection (cosine similarity) | Image similarity search across millions of items |
| Trainer cohort dashboard | Internal monitoring + analytics dashboards |
| Exam builder | Data annotation tools + knowledge encoding |
| Hidden test cases | Protected ground truth data |
| Attempt limiting | Policy enforcement systems |
| SSE result delivery | Real-time status updates in internal tools |
| Role-based auth | Account management systems |

**The one sentence that wins the interview:**

> "CodeMas is structurally the same problem Entrupy solves — you receive untrusted input, process it asynchronously through an isolated pipeline, return a trusted result in real-time, and surface anomalies for human review. We built it for code. You build it for luxury goods."

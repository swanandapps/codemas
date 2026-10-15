# Exam supporting material: design

Date: 2026-10-03
Status: proposed, awaiting approval
Runs on: [Job pipeline](2026-10-03-job-pipeline-design.md), as job kind `generate_material`. No Celery.

## Goal

Every question in every exam gets a complete, checked material pack when the exam is created:

1. Reference solution (trainer only)
2. Test cases whose expected outputs are produced by running the reference solution
3. Starter code shown in the student's editor
4. Constraints and examples as structured content on the exam screen
5. Editorial (approach and complexity): trainer only until the exam ends, then visible to students

This applies to both creation paths: the AI draft and manually written questions.

## Why

Today `generate_exam_draft` (backend/ai/tasks.py:371) asks the model for question text plus exactly three test cases, and stores the model's expected outputs as written. Nothing executes a solution, so one hallucinated expected output marks correct student code as wrong. Manually written questions get no generated material at all, and constraints and examples live only as prose inside `description`.

The principle: the model proposes, code decides. Expected outputs come from executing the reference solution, never from the model's text.

## Data model

`exams.Question`, new fields:

| Field | Type | Notes |
|---|---|---|
| `reference_solution` | TextField, blank | In the question's language. Never sent to students. |
| `starter_code` | TextField, blank | Input/output boilerplate plus a function stub. |
| `constraints` | TextField, blank | One constraint per line. |
| `editorial` | TextField, blank | Approach, edge cases, time and space complexity. |
| `material_status` | CharField | `none`, `generating`, `ready`, `needs_review`, `failed`. Default `none`. |
| `material_report` | JSONField, default `{}` | Validation results (see below). |
| `material_updated_at` | DateTimeField, null | |

`exams.TestCase`, new fields:

| Field | Type | Notes |
|---|---|---|
| `label` | CharField(80), blank | For example "empty list", "duplicates", "large n". |
| `source` | CharField | `manual` or `ai`. Default `manual`. |
| `validated` | BooleanField | True when the reference solution produced `expected_output` for this input. |

Examples shown to students are the test cases with `is_hidden=False`; no separate examples field.

One migration in `exams`. Existing rows keep working: new fields are blank or default.

## Pipeline

Generation is a `generate_material` job on the job pipeline. `jobs.enqueue('generate_material', question_id)` sets `material_status = generating` in the same transaction. The material handler (its own Lambda function, or the local transport) does steps 2 to 3 and returns everything through `complete`; Django does steps 4 to 6 when it applies the result.

1. On `claim`, the handler receives the question's title, description, language, difficulty and its manual tests (`[{id, input, expected}]`).
2. One model request with the question title, description, language and difficulty. Required JSON:
   ```json
   {
     "starter_code": "...",
     "reference_solution": "...",
     "constraints": ["..."],
     "editorial": "...",
     "tests": [{"label": "...", "input": "...", "expected_output": "...", "visible": true}]
   }
   ```
   The prompt asks for 2 visible examples and 6 to 8 hidden tests that cover edge cases, in the same stdin/stdout format the judge uses (output compared after `.strip()`, as in `execution/tasks.py:49`).
3. Validate by execution, using the shared child-process runner `handlers/sandbox.py` (memory, CPU, process and output limits; see the pipeline spec):
   - Run the reference solution on every generated input, twice. Outputs that differ between runs mark the test non-deterministic.
   - `expected_output` is set to the solution's actual stdout. The model's proposed output is kept only in the report.
   - A test is `validated` when both runs succeed (no stderr, no timeout) and agree.
   - Also run the solution against the question's existing manual tests. A mismatch there usually means a typo in the trainer's test, so it is reported, not overwritten.
   - Python starter code is syntax-checked with `compile()`.
4. Replace this question's previous `source=ai` tests with the new ones. Manual tests are never deleted or changed.
5. Set the status:
   - `ready`: the solution ran on every input, at least 2 visible and 5 hidden tests are validated, and there are no disagreements with manual tests.
   - `needs_review`: anything validated but imperfect: model and actual output disagreed, a test errored and was dropped, the minimum counts were not met, or a manual test disagrees with the solution.
   - `failed`: the model is unavailable, or the solution failed on every input.
6. Save `material_report`:
   ```json
   {
     "model": "gpt-4o-mini",
     "tests_generated": 9, "tests_validated": 8,
     "model_disagreements": [{"label": "...", "model": "...", "actual": "..."}],
     "errors": [{"label": "...", "stderr": "..."}],
     "manual_mismatches": [{"test_case_id": 12, "expected": "...", "actual": "..."}],
     "nondeterministic": []
   }
   ```

Generation for one question is idempotent: rerunning replaces AI tests and material, and leaves manual tests alone.

## API

| Method and path | Who | Purpose |
|---|---|---|
| `POST /api/exams/<id>/generate-material/` | trainer | Enqueue one `generate_material` job per question, in one transaction. Returns 202. |
| `POST /api/exams/<id>/questions/<qid>/generate-material/` | trainer | Enqueue or regenerate one question. If an active job already exists for it, returns 409. Returns 202 otherwise. |
| `GET /api/exams/<id>/material-status/` | trainer | `[{question_id, material_status, material_updated_at, summary}]` for polling. |

Serializer rules (enforced and tested):

- Trainers get every new field and every test case.
- Students get `starter_code`, `constraints` and visible test cases only. They never receive `reference_solution`, `material_report` or hidden test inputs and outputs.
- Students get `editorial` only after the exam's `end_time`.

The current student-facing question payload must be checked during implementation: if it already exposes hidden test data, that is fixed as part of this work.

## Frontend

**Create exam (CreateExamView.vue).** Generation starts automatically in both paths:
- AI path: "Save draft" becomes "Save and generate material". It calls `create-full`, then `generate-material`, then opens the exam detail page.
- Manual path: "Finish" calls `generate-material` before leaving.

**Exam detail for trainers (ExamDetailView.vue).** One card per question:
- A status pill: Generating, Ready, Needs review or Failed. The page polls `material-status` every 3 seconds while anything is generating.
- Tabs: Solution (dark code block), Tests (label, visible or hidden, validated, source), Starter code, Constraints, Editorial.
- For "needs review", the report in plain language. Example: "The model expected [1, 2] for 'duplicates' but the solution printed [0, 1]."
- A "Regenerate" button per question.
- Publishing an exam that has questions not marked Ready shows a warning listing them, but is allowed.

**Exam screen for students (ExamTakeView.vue).**
- The editor opens with `starter_code` when the student has no code yet for that question.
- The problem panel shows Constraints and Examples sections, built from the visible tests.

**My results (MyResultsView.vue).** Shows the editorial once the exam has ended.

## Error handling

- Model unavailable: status `failed` with the reason. The exam can still be published with manual tests.
- Solution timeout (10 s per run, the sandbox limit) or crash on an input: that test is dropped and reported, and the status becomes `needs_review`.
- Handler crash or timeout: the job's lease expires and the pipeline retries it (up to 3 attempts). After that the job is `dead` and the question becomes `failed` with "Generation didn't finish; try again".

## Security note

The reference solution is model-written code. It runs in the material handler through the same child-process runner as student code, with memory, CPU, process and output limits. The material handler is a separate Lambda function from the student-code executor, because it holds the OpenAI key. The remaining gap is the same as for student code: no per-job network isolation inside the function.

## Testing

Backend (Django tests, model calls mocked):
- The material handler with a real Python solution through the sandbox runner, driven by the local transport: expected outputs come from execution, and disagreements, errors and non-determinism are recorded.
- Status rules: ready, needs_review and failed cases.
- Manual tests are never modified, and mismatches against them are reported.
- Serializer permissions: a student never receives `reference_solution`, `material_report` or hidden tests, and gets `editorial` only after `end_time`.
- Endpoints: trainer only, return 202, enqueue a job in the same transaction, 409 when one is already active.

Frontend: type-check and build, then a browser check of both creation paths, the exam detail review, and starter code plus examples on the exam screen.

## Out of scope

- Solutions in more than one language per question
- Generating rubric criteria per question
- Comparing student code against the reference solution for plagiarism

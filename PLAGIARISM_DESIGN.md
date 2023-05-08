# CodeMas Plagiarism Detection — Design Document

**Audience:** CTO, CEO, Technical Leadership
**Status:** Implemented
**Authors:** Engineering

---

## Executive Summary

Plagiarism detection in a coding exam platform is a harder problem than it looks. The obvious approach — comparing every student's code against every other student's code — breaks down at scale, produces false positives on correct solutions, and tells you the wrong thing. This document covers how we thought through the problem, what we rejected and why, what we built, and what it costs to run.

**Bottom line:** We moved from a naive O(N²) similarity engine to a two-layer behavioural + targeted comparison system. It is cheaper, faster, more accurate, and scales linearly rather than quadratically.

---

## 1. The Problem Statement

A coding exam has 200 students. Each student submits code for 5 questions. That is 1,000 submissions.

The naive question is: "Are any two submissions similar?"
The better question is: "Did this student write this code themselves?"

This reframe changes everything — architecture, cost, accuracy, and what you show trainers.

---

## 2. Options We Considered

### Option A — Naive String Comparison (Rejected)

**How it works:** For every submission, compare its raw code string against every other submission using edit distance or simple diff.

| | |
|---|---|
| Time complexity | O(N² · L) where L = average code length |
| Space complexity | O(N²) to store all pairs |
| 200 students, 5 questions | 200,000 comparisons per exam |
| 10,000 students | 500 million comparisons |

**Why we rejected it:**
- Does not survive whitespace, variable rename, or comment changes — students trivially bypass it
- Quadratic growth makes it unusable at any serious scale
- Not meaningful: two students independently writing `for i in range(n)` look identical

---

### Option B — TF-IDF + Cosine Similarity, Per Submission (Rejected)

**How it works:** Convert each code submission into a term-frequency vector over code tokens. Compute cosine similarity between all pairs. Flag pairs above a threshold (0.85).

This is what many academic plagiarism tools do (Moss, JPlag use variants of this).

| | |
|---|---|
| Time complexity | O(N² · V) where V = vocabulary size |
| Space complexity | O(N · V) for the TF-IDF matrix |
| 200 students, 5 questions | 100,000 pair comparisons per exam |
| Trigger | Every submission — real-time |

**Pros:**
- Catches structural similarity even after variable renaming if vocabulary is large
- Well-understood algorithm with published benchmarks
- Easy to implement with scikit-learn

**Cons:**
- Still O(N²) — does not scale to 10,000 students
- False positives: correct solutions to the same problem often share tokens (`return`, `dp`, `left`, `right`). A bubble sort by Student A looks like a bubble sort by Student B because both are bubble sorts.
- Runs per submission, so the worst time is at peak load — exactly when the system is most stressed
- Comparing a late submission against 999 previous ones means comparison cost grows throughout the exam
- Does not distinguish a student who typed their code slowly from one who pasted it in 2 seconds

---

### Option C — MinHash + Locality-Sensitive Hashing (Considered, Not Implemented)

**How it works:** Represent code as a set of k-shingles (overlapping character n-grams). MinHash converts these sets to compact signature vectors. LSH groups signatures into buckets so only similar ones are compared.

| | |
|---|---|
| Time complexity | O(N · k) for hashing + O(bucket_size²) for comparison |
| Space complexity | O(N · num_hash_functions) |
| Best case | Near-linear — only similar pairs get compared |

**Pros:**
- Sub-quadratic at scale — designed for millions of documents
- Used by Google, Spotify for near-duplicate detection
- Probabilistic guarantees on recall

**Cons:**
- Same false positive problem as TF-IDF: structurally similar correct code still hashes similarly
- Significant implementation complexity and tuning overhead
- Overkill at current scale (< 10,000 students)
- Still does not answer the real question: did this student write this?

**Decision:** Good tool for the wrong problem. Shelved for now. If we reach 1M+ submissions, MinHash/LSH is the right cross-comparison layer.

---

### Option D — AST Normalization + Cosine Similarity (Partially Implemented, Supporting Layer)

**How it works:** Parse the submitted code into an Abstract Syntax Tree. Walk the tree and rename all variables to VAR_0, VAR_1... in order of first appearance. Strip comments. Vectorize the normalized code.

```
Student A:                     Student B:
def solve(nums, target):       def find(arr, k):
    left = 0                       l = 0
    right = len(nums) - 1          r = len(arr) - 1

After AST normalization, both become:
def VAR_0(VAR_1, VAR_2):
    VAR_3 = 0
    VAR_4 = len(VAR_1) - 1
```

**Pros:**
- Eliminates the most common bypass: variable renaming
- Eliminates comment noise
- Higher signal-to-noise in cosine similarity

**Cons:**
- Still O(N²) pairwise comparison — does not solve scale
- Students who independently solve a problem the same way still normalize to the same code
- Does not catch paste-and-rename at a higher level if the logic structure is the same

**Decision:** Kept as the comparison method inside our targeted layer. Used only after behavioural filtering reduces the candidate set.

---

### Option E — Behavioural Scoring + Targeted Comparison (Implemented)

This is what we built. The key insight: **instead of comparing all students against each other, first identify which students are suspicious, then only compare those.**

More importantly, behavioural signals can flag plagiarism that code comparison cannot — a student who pasted 800 characters in 3 seconds is suspicious regardless of whether their code looks like anyone else's.

---

## 3. The Architecture We Built

### Layer 1 — Behavioural Scoring (O(N) per exam, runs at exam close)

Runs post-exam in batch, inside `run_exam_plagiarism_check`, synchronously before Phase 2 is queued. Scores four signals per submission:

#### Signal 1: Paste Ratio
```
paste_char_count / final_code_length
```
- ≥ 70% pasted → score 1.0 (high risk)
- ≥ 50% pasted → score 0.7 (medium risk)
- ≥ 30% pasted → score 0.3 (low risk)

**Why this matters:** A student typing their own solution pastes almost nothing. A student who copied from a friend or ChatGPT pastes most of it.

**Weight in final score:** 40% (highest — strongest single signal)

#### Signal 2: Time-to-Complete vs Difficulty Baseline
```
elapsed_seconds / difficulty_baseline_seconds
```
Baselines: Easy = 90s, Medium = 240s, Hard = 480s

- Solved in ≤ 20% of baseline → score 1.0 (e.g., hard problem in under 96s)
- Solved in ≤ 40% of baseline → score 0.7
- Solved in ≤ 60% of baseline → score 0.3

**Why this matters:** Genuine problem-solving takes time. Someone who solves a hard problem in 2 minutes either memorised the solution or pasted it.

**Weight in final score:** 30%

#### Signal 3: Submission Surprise (Attempt N vs Attempt N-1)
```
1 - SequenceMatcher(attempt_n-1, attempt_n).ratio()
```
- Ratio < 0.25 and solution passed → score 1.0 (completely different code that suddenly works)
- Ratio < 0.40 → score 0.6
- Ratio < 0.55 → score 0.2

**Why this matters:** Students iterate. If their second attempt shares less than 25% of characters with their first attempt AND passes all tests, they likely discarded their own work and submitted someone else's.

**Weight in final score:** 20%

#### Final Risk Score
```
risk_score = (0.40 × paste) + (0.30 × time) + (0.15 × tab_switch) + (0.15 × submission)
```

Confidence levels based on how many signals fired:
- 3+ signals fired → LOW confidence (low confidence they wrote it themselves — most suspicious)
- 2 signals fired → MEDIUM confidence
- 1 signal fired → HIGH confidence (high confidence they wrote it themselves — least suspicious)

Note: the naming is counterintuitive. "LOW confidence" = most suspicious. It refers to our confidence that the student is innocent, not our confidence that they cheated. Phase 2 queries students with LOW confidence (3+ signals) as starting suspects.

Only stored if risk_score > 0.2 (avoids polluting the DB with noise).

---

### Layer 2 — Targeted Cross-Comparison (O(K × N) where K << N)

Runs in batch when the exam closes.

**The key insight here:** a flagged student may have copied from someone with clean behaviour signals — someone who typed slowly, took the right amount of time, had no paste events. The source would be invisible if we only compared suspects against each other.

So we compare each suspect against the **entire cohort**, not just other suspects.

| Approach | Comparisons (100 students, 12 suspects) |
|---|---|
| All pairs (Option B) | 100 × 100 = 10,000 |
| Suspects vs suspects (old Layer 2) | 12 × 12 = 144 — misses unflagged sources |
| **Suspects vs everyone (current)** | **12 × 100 = 1,200 — catches the source** |

Steps:
1. Identify HIGH-confidence behavioural suspects (K students)
2. Pull final submissions for ALL students who answered the question (N students)
3. AST-normalize all code (strip variable names, comments)
4. TF-IDF vectorize the full cohort once
5. Loop upper triangle — skip any pair where neither side is a suspect
6. Store pairs with similarity > 0.80 as `PlagiarismFlag`, labelling each side as "suspect" or "source"

---

## 4. Complexity Comparison

| Approach | Time Complexity | Space Complexity | Trigger |
|---|---|---|---|
| Naive string diff (Option A) | O(N² · L) | O(N²) | Per submission |
| TF-IDF all pairs (Option B) | O(N² · V) | O(N · V) | Per submission |
| MinHash + LSH (Option C) | O(N · k) avg | O(N · h) | Per submission |
| Behavioural only (Layer 1) | **O(N)** | **O(N)** | Once on exam close |
| Suspects vs suspects (old) | O(K²) | O(K · V) | Once on exam close |
| **Suspects vs everyone (current)** | **O(K · N)** | **O(N · V)** | **Once on exam close** |
| **Our system (L1 + L2)** | **O(N) + O(K · N)** | **O(N · V)** | **Once on exam close** |

At 10,000 students with a 5% flag rate (K=500):
- Option B (all pairs): 50,000,000 comparisons
- Old Layer 2 (suspects vs suspects): 125,000 comparisons — but misses unflagged sources
- **Current Layer 2 (suspects vs everyone): 5,000,000 comparisons — full coverage**
- Still 10x fewer than all-pairs, and catches the student who typed someone else's code slowly

---

## 5. False Positive Analysis

This is where behavioural detection wins over code comparison alone.

**Scenario:** Two students independently write a correct binary search. Their code is structurally identical because there are only so many ways to write binary search.

| System | Result |
|---|---|
| Pure TF-IDF cosine similarity | Flags both — high similarity score, looks like plagiarism |
| Our behavioural system | Does NOT flag either — both typed gradually, took expected time, no paste events |

**Scenario:** A student pastes code from a friend but changes all variable names.

| System | Result |
|---|---|
| Naive string diff | Misses it — strings differ |
| TF-IDF without normalization | May miss it |
| TF-IDF with AST normalization | Catches it via similarity |
| Our behavioural system | Catches it via paste ratio — pasteCharCount / codeLength is high |

**The behavioural layer catches dishonest students who evade code comparison, and does not flag honest students who happen to write similar code.**

---

## 6. What We Do Not Detect (Known Gaps)

| Gap | Explanation |
|---|---|
| Manual retyping | A student who copies code by manually retyping it character by character generates no paste events. Time signal may still catch it if unrealistically fast. Accepted gap — disciplined enough to retype 200 lines deserves to pass. |
| AI-generated code | ChatGPT output typed slowly. Time signal may flag it if unrealistically fast; otherwise it looks like genuine work. AI detection is a separate problem. |
| Pre-exam memorisation | A student who memorised a solution before the exam will have correct behaviour signals. Cannot detect without a reference corpus of memorised solutions. |
| Collusion between high-risk students who both type slowly | If two students share the same solution and both type it slowly with no paste, neither behavioural nor code comparison flags them. |

Honest assessment: no automated system catches 100% of academic dishonesty. Our system raises the cost and reduces the reward of cheating for the common cases.

---

## 7. Business Impact

### Trainer Time
Before: trainers had no plagiarism tools — manually reviewing suspicious submissions or ignoring the problem entirely.
After: trainers see a ranked list of flagged students with specific, auditable reasons. "Pasted 73% of code, solved hard problem in 94 seconds" is actionable. "Similarity: 0.87" is not.

### Platform Trust
For a coding assessment platform, credibility is the product. If certifications can be gamed, the platform becomes worthless. A visible, explainable plagiarism system is a trust signal to enterprise customers and to honest students.

### Candidate Fairness
A student who studied hard and performs well loses if others cheat unpunished. Detection protects honest users, not just the platform's reputation.

### Scalability as a Selling Point
"We check every submission against every other submission" sounds impressive but costs exponentially more as the platform grows. "We run a two-phase post-exam batch: behavioural scoring for every submission, then targeted cross-comparison for suspects only" is more accurate, more scalable, and better engineering.

---

## 8. Cost Efficiency

### Per Exam Cost (Layer 1)
Layer 1 runs synchronously inside `run_exam_plagiarism_check` after the exam closes. It reads 4 fields from each Submission and does arithmetic.

| Operation | Cost per submission |
|---|---|
| DB read (1 row) | ~1ms |
| Python arithmetic | < 1ms |
| DB write (BehaviouralFlag) | ~2ms |
| **Total per submission** | **~5ms** |

At 10,000 students: 10,000 × 5ms = 50 seconds of total Layer 1 CPU time, running synchronously in one Celery worker before Phase 2 is queued. This runs once on exam close, not during the exam — no impact on submission latency.

### Per Exam Cost (Layer 2)
Runs once when the exam closes. Suspects (5% flag rate) compared against full cohort.

| Exam Size | Suspects (5%) | Pairs Checked | Estimated Time |
|---|---|---|---|
| 50 students | ~3 | 150 | < 1 second |
| 200 students | ~10 | 2,000 | ~2 seconds |
| 1,000 students | ~50 | 50,000 | ~15 seconds |
| 10,000 students | ~500 | 5,000,000 | ~20 minutes |

At 10,000 students, the batch runs once per exam at a quiet time (exam close). 5 minutes of compute on a single worker is acceptable.

Compare to Option B (all-pairs per submission):
- 10,000 students × each submission triggers comparison against all previous
- Total comparisons across the exam: ~50 million
- Estimated time: 4-8 hours of compute

---

## 9. Infrastructure

| Component | Role |
|---|---|
| Django + DRF | API layer, signal handler |
| Celery | Background task queue |
| Redis | Celery broker |
| `pre_save` signal on Exam | Triggers batch when exam closes |
| PostgreSQL | Stores BehaviouralFlag, PlagiarismFlag |
| Vue 3 frontend | Trainer UI with two-tab review interface |

**Signal reliability:** The batch plagiarism check is triggered by a Django `pre_save` signal on the Exam model, not by a view or API call. This means it fires regardless of how the exam is closed — Django admin, REST API, management command, or future dashboard.

---

## 10. Future Improvements (Prioritised)

| Priority | Improvement | Rationale |
|---|---|---|
| High | Keyboard event telemetry (keystrokes) | Would strengthen time signal — distinguish typing from thinking pauses |
| High | AI-generated code detection | Growing problem; separate model or API (e.g., GPT-Zero) |
| Medium | Reference corpus for known solutions | Compare against published LeetCode solutions to flag memorisation |
| Medium | MinHash/LSH at scale | If student base exceeds 50,000 per exam, Layer 2 needs sub-quadratic comparison |
| Low | Cross-exam detection | Detect students reusing code across different exam sessions |
| Low | Network graph visualisation | Show clusters of suspected colluders to trainers |

---

## 11. Decision Summary

| Question | Answer |
|---|---|
| Why not compare all submissions in real-time? | O(N²) — breaks at scale, peaks during load, wrong question |
| Why behavioural signals over code similarity? | Behavioural signals catch what code comparison misses (paste, speed) and do not flag what code comparison gets wrong (same correct solution) |
| Why compare suspects against everyone, not just each other? | A suspect may have copied from a student with clean behaviour signals. Suspects-vs-suspects misses the source. Suspects-vs-everyone catches it at O(K·N) instead of O(N²). |
| Why not compare all 10,000 students against all 10,000? | O(N²) — 50M comparisons at 10k students. Our approach: 5M comparisons, same coverage for real cases. |
| Why does Layer 1 run at exam close, not per-submission? | Full-exam context: all submissions are final, cross-question patterns visible, no false positives from partial data mid-exam. No actionable surface for trainers during the exam. Running post-exam also keeps submission latency clean — no extra task per submit. |
| Why does Layer 1 run synchronously (not queued) inside the batch? | Phase 2 filters by HIGH-confidence BehaviouralFlags. Those records must exist before Phase 2 queries them. Synchronous call guarantees ordering without needing Celery chords or chains. |
| Why Django signals over API hook? | Signals fire regardless of how the exam is closed; views would miss admin panel and management commands |
| What is the cost at 10,000 students? | Layer 1: ~50s total, once at exam close. Layer 2: ~5 min total, once per exam |

---

## 12. Policy Impact Tracking — Run History

### The Problem

When a trainer raises the similarity threshold from 0.80 to 0.85 and asks "did that reduce false positives?", there was previously no way to answer. You could see current flags but not how detection results changed across policy iterations.

### PlagiarismRun Record

Every batch execution creates a `PlagiarismRun` row before any detection runs:
- **Policy snapshot** — full JSON copy of all 9 policy fields at run time
- **Exam context** — students, pass rate, avg execution time, avg solve time (fixed for a given exam — doesn't change between runs)
- **Phase 1 results** — total flags, per-confidence-level counts, avg risk score
- **Phase 2 results** — total pairs, 90%+ similarity count, 80–90% count, avg similarity, progress (questions_done/questions_total)

### Comparing Two Runs

A trainer can now see:
- Run 1 (similarity_threshold=0.80): 45 pairs flagged, avg similarity 0.91
- Run 2 (similarity_threshold=0.85): 18 pairs flagged, avg similarity 0.94

That drop from 45 to 18 with a threshold change from 0.80 to 0.85 tells you the 27 dropped pairs were borderline (0.80–0.85 similarity) — likely legitimate independent solutions to the same problem.

### Manual Re-run Behaviour

Re-running is non-destructive to trainer review decisions:
- Behavioural flags: recalculated with new weights (`update_or_create`)
- Similarity pairs: scores updated, new pairs created, old pairs below new threshold **NOT deleted**
- `review_status` and `review_note` on every flag: **always preserved**

The reason: a trainer who confirmed a pair should not have their decision undone by a policy change. The audit log stays clean.

---

## 13. Integrity Monitoring

### What It Measures

Not how many students cheated — how well the system is detecting cheating. Two axes: precision (are your flags accurate?) and coverage (are you checking all submissions?).

### Signal Precision Formula

```
precision = confirmed / (confirmed + dismissed)
```

NOT `confirmed / total_fired`. The denominator is only flags a trainer has actually reviewed. If 127 paste flags fired and only 3 were reviewed (2 confirmed, 1 dismissed), precision = 66.7% — based on 3 data points. The number is meaningless until review volume increases.

This is the most important thing to understand about the monitoring numbers: they look decisive but are statistically weak until the backlog is cleared.

### Coverage vs Flags — Two Different Things

- `BehaviouralFlag` records existing for an exam ≠ coverage = 100%
- Coverage = % of `Submission` rows where `behavioural_check_done=True`
- A flag can exist (from seed data, old runs, or direct DB writes) while coverage shows 0% because the Celery task never ran

Both must be checked: flags tell you what was found, coverage tells you whether the search was complete.

### Drift Alert

Compares behavioural flag volume in the last 7 days vs the prior 7 days. A sudden doubling (e.g., 0 → 138) with no policy change is a signal that either:
1. A new exam ran with different student behaviour patterns
2. A new cheating vector is spreading through the cohort

Worth investigating before the next exam runs.

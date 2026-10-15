# CodeMas metrics

One definition per number. Every endpoint computes these through
`backend/analytics/metrics.py`; nothing else may compute its own version.
UI labels and one-line help text live in `frontend/src/utils/metrics.ts`.

**Population.** Students are users with `role='student'` and `is_superuser=False`.
Every metric filters to this population. Rates are percentages rounded to 1
decimal, and `null` when the denominator is 0 (shown as "—").

Section vs cohort: `User.cohort` holds the student's **section** (Section A–D). "Section
rank" ranks within the section (`rank`, `cohort_size`); "Cohort rank" ranks across all
sections (`overall_rank`, `overall_size`, from `metrics.all_scores()`, the same numbers as
the leaderboard's "Whole cohort" view). Both rank by score; equal scores are split by average solve time (seconds to a passing submission, `metrics.solve_times`, the exam report's "Avg solve"), faster first. Students share a rank only when score and time are both equal, and a student with no timed pass counts as slowest (tie-break added 2026-10-08: on a 1-question exam everyone who passed used to tie at #1).
The trainer's student page shows the same section rank. Per exam, My results ranks by points
on that exam among the section's students who **took** it (had a submission; "#2 of 3", where 3
is how many took it); the exam report ranks by the same points across every enrolled student
(all sections, labelled so), with the same rule (`metrics.exam_standing`: `metrics.competition_rank`
with `metrics.solve_times`). On both, a student with **0 points on the exam** (nothing solved, or
all of it withheld) is **not ranked**: `rank` is `null`, shown as "Not ranked" (the report shows
"—" for a student who never submitted). Changed 2026-10-08: My results used to rank against the
whole section, so a student who skipped the exam still counted in "of N".

**Confirmed plagiarism withholds points (owner decision 2026-10-08).** A student's points
for a question are withheld (the question is *voided*, `metrics.voided_pairs`) when, on that
question, the student has (a) a **confirmed** behavioural flag on any of their submissions, or
(b) a **confirmed** similarity pair on one of their submissions **and** a behavioural flag (not
dismissed) of their own. A confirmed pair alone never voids: the classmate whose code merely
matched a suspect keeps their points. `metrics.points_by_student` leaves voided questions out,
so every score and rank drops with it (exam report, student page, My results, Home,
leaderboard), and `metrics.solve_times` ignores voided passes in the tie-break. Confirming
takes effect on the next page load (nothing is cached). `metrics.withheld_points` /
`points_withheld_by_student` give what was lost: `points_withheld` on the exam report row,
the student page (student, per exam in `performance_trend`, per question), My results (per
exam and per question), Home stats (`/api/leaderboard/me/`), and `withheld` per difficulty in
`difficulty_progress`. The leaderboard shows no marker (privacy). **Under review**: a student
with any *pending* flag on the exam's submissions (behavioural, or a similarity pair on either
side, `metrics.under_review`); rank unchanged, shown on trainer pages only. The exam report's
`integrity_status` is `withheld` (any voided question on the exam), else `under_review`, else
`null`, shown as a badge next to the student's name.

**A voided question is not solved (owner decision 2026-10-08, later the same day).** Its tests
still passed, but it neither scores nor counts toward the pass rule, so it can drop the student
below half and fail the exam (2 of 4 solved with one voided: 1 of 4, not passed; 3 of 4 with one
voided: 2 of 4, still passed). `metrics.exam_results` leaves voided pairs out of `solved` and
reports `voided` (how many *solved* questions were not counted; a voided question the student
never solved costs nothing), so the pass, every success rate (exam, student, section), the trend
dot and students who need help follow; `metrics.question_success_by` leaves the student out of
the question's solvers (still an attempter); `difficulty_progress` leaves it out of `solved`.
Pages say why: My results (per exam `questions_voided`; per question `voided`, "Tests passed on
attempt N · Not counted: plagiarism"; the Result card's reason line), the exam report
(`questions_voided`; Result "Not passed · plagiarism", or "Passed" with "N not counted"), the
student page trend (`questions_voided`; tooltip "plagiarism confirmed: N questions not counted"),
and the AI exam summary and weekly recommendation inputs (the result line says how many were
not counted). Dismissing the flag or overturning the appeal restores it everywhere; the matched
side of a confirmed pair keeps the solve.

**Appeals (2026-10-08).** A student may appeal a confirmed decision once per exam; a trainer
upholds (nothing changes) or overturns it. Overturning dismisses the appellant's own behavioural
flags on that exam and leaves similarity pairs alone, so by the voided-pairs rule above the
appellant's points come back everywhere while a classmate in the same case who keeps a confirmed
behavioural flag stays withheld. No metric reads the appeal itself; it acts only through the flags.

**Attention counts** (`GET /api/support/attention/`, `support/integrity.py`; sidebar badges, Home
banner, Overview line). Student: `new_decisions` = exams where a trainer decided one of the
student's flags in a way My results shows (confirmed, or dismissed with a note) after
`User.integrity_seen_at`, timed by the review log (`ReviewAuditLog.created_at`); an exam whose
appeal was ruled after that counts under `new_rulings` instead (= appeals upheld or overturned
after it). `integrity_seen_at` is set to now when the student opens My results or Disputes; null
means everything logged is new (existing accounts were set to the migration time). Trainer:
`open_appeals` = appeals with status open; `cases_to_decide` = the sum over exams of the case
file's "Cases to decide" (`plagiarism.views.cases_to_decide`, grouping only exams with a pending
flag). Live, no seen state; fetched once per page visited.

**Dismissed flags.** A flag a trainer dismissed (`review_status='dismissed'`) no longer
counts as flagged, behavioural or similarity alike (`metrics.FLAGGED`,
`metrics.behavioural_flags()`, `metrics.similarity_flags()`). Every count, badge and
confidence level leaves it out: flagged students, the students list and
student page confidence, exam report and investigation flag counts and rings, the student
page's per-attempt similarity badge, students needing help. The exam case file on
Investigation still lists it, marked Dismissed.

**Attempts.** An `error` submission (couldn't be graded) is refunded: it never counts as an
attempt, on the exam page, My results, the trainer's student page or the exam report. The limit is
`PlagiarismPolicy.max_attempts` for every question; the question API returns it as
`max_attempts`.

| Metric (UI label) | Definition | API fields | Shown on |
|---|---|---|---|
| Success rate | **How many students passed the exam** (changed 2026-10-07; before, it was passed submissions ÷ graded submissions, and a separate "Solved" rate was shown next to it; both are gone). **Pass rule:** a student passed an exam when they solved *at least half* of the exam's questions, counted against every question in the exam, attempted or not (a 1-question exam: solved it = passed; 1 of 2, 2 of 3 and 2 of 4 pass, 1 of 3 does not; rule chosen by the owner 2026-10-07 over "more than half", which put the 2-question past exams near 0%). Solved = at least one `passed` submission on the question, unless the question is voided for confirmed plagiarism (see above, 2026-10-08); `pending`/`running` are ignored and a refunded `error` never solves one (`metrics.passes`, `metrics.exam_results`). One rule at every level, from `metrics.success_by` ((student, exam) pairs passed ÷ pairs taken): **exam** = students who passed ÷ students who took it (the same `took` as "Took the exam"); **student** = exams passed ÷ exams taken (students list, student page, students who need help, struggling/thriving bands, leaderboard, Home, My results); **section** = per exam, the section's students who passed ÷ the section's students who took it (overview cards, sparkline, "vs last 3 exams" delta, health states). **Question** = students who solved it ÷ students who attempted it (a `passed` or `failed` submission; `metrics.question_success_by`), for per-question rows and the hardest question. Per student per exam the API returns `passed` (true/false) with the questions-solved count, not a percentage; the student page's trend dot is the same pass. The API field keeps the name `accepted_rate`. | `accepted_rate`, `passed_students` (exam / section); `exams_passed`, `exams_taken` (student page, My results); per question `accepted_rate`, `solved_students`, `attempted_students`; per student per exam `passed`, `questions_solved` (counted), `questions_voided`, `total_questions` / `questions_total`; `hardest_accepted_rate` | Overview (section cards, sparkline, students who need help), exam history (list, report, per question, per student result), investigations, students, student detail (KPI, trend dot), leaderboard, my results, student Home |
| Flagged students | Students with at least one behavioural flag (not dismissed) on the exam's submissions ÷ students who submitted on the exam. The only integrity rate anywhere. Similarity pairs are reported separately as counts. | `flagged_students_rate`, `flagged_students` | Overview (cohort cards, health reasons), exam history, investigations list and detail |
| Flags to review | Count of behavioural flags with `review_status='pending'`, scoped to the page (cohort, exam, everything). | `flags_to_review` | Overview cohort cards, exam report, investigation detail, monitoring |
| Took the exam | Students who submitted at least once (any status) ÷ students enrolled. The same `took` is the flagged-students denominator. An unenrolled submitter counts in `took`. | `took`, `enrolled`, `took_rate` | Overview, exam history, investigations |
| Hardest question | The question with the lowest question success rate (students who solved it ÷ students who attempted it) among questions someone attempted; a tie goes to the lowest question id (`metrics.hardest_question`). | `hardest_question`, `hardest_accepted_rate` | Exam history |
| Solve time | `time_to_complete_seconds` (seconds from exam start to the submission). Rows without it fall back to exam length − `time_remaining_seconds`. The exam report averages passed submissions with a known time. | `solve_time_seconds`, `avg_solve_s` | Student detail, exam history |
| Exam status | `draft`, `live` or `ended` (`exams.models.exam_status`): ended once `end_time` has passed; live while `is_active` and not past `end_time` (with or without one); otherwise draft. | `status` on exam rows, the exam API and exam ops | Exam history and report, student exam page, policy re-run list |
| Risk | `risk_score × 100`, rounded half-up to a whole number, for one behavioural flag. | `risk` (`max_risk` on the students list); raw `risk_score` is still returned | Students, student detail, investigation detail, disputes, submission detail |
| Compared in Phase 2 | A flagged student is a Phase 2 suspect (code compared with everyone who answered the question) when `risk_score` ≥ policy `compare_min_risk` (default 0.35) or confidence is `high`. | `compare_min_risk` on `/api/plagiarism/policy/` | Policy page |
| Flag confidence | Confidence that a behavioural flag indicates misconduct, from how many of the four signals fired: `high` = 3 or more (most suspicious), `medium` = 2, `low` = 1. Set by `compute_behavioural_risk`; Phase 2 similarity checks compare `high` students. A student's level is their most suspicious flag that was not dismissed. Shown as a badge: high red, medium amber, low neutral. Help: "How strongly the signals point to misconduct: high means 3 or more signals." | `confidence` per flag; `max_confidence` and `confidence_rank` (high 3, medium 2, low 1, none 0) on the students list; `behavioural_confidence` on investigation detail; `confidence_breakdown` on monitoring; `b_high_confidence` / `b_medium_confidence` / `b_low_confidence` on plagiarism runs | Students, student detail, flags, investigation detail, monitoring, disputes, submission detail, policy runs |

## Health thresholds

`HEALTH_RULES` in `backend/dashboard/health.py`, echoed by `GET /api/dashboard/health/` as `rules`.
"Latest graded exam" is a section's newest exam with graded submissions (`graded_submissions`
in the summary; so it can differ from the newest exam on the Exams page); the overview labels
it that way. Every success rate below uses the 2026-10-07 definition: a section's rate on an
exam is its students who passed ÷ its students who took it, and a student's overall rate is
exams passed ÷ exams taken.

| Rule | Watch | At risk |
|---|---|---|
| Latest graded exam success rate below | 55% | 40% |
| Flagged students on the latest graded exam at or above | 30% | 50% |
| Students struggling (success rate, exams passed ÷ taken, under 40%) at or above | 20% | 25% |
| Took the latest graded exam below | 85% | 60% |
| Success rate drop vs the previous three exams | 8 points | |

The investigations list and detail colour each exam with the same flagged-students
thresholds (`integrity_health`: amber at watch, red at at-risk).

## Where the shared summary is used

`metrics.exam_summaries(exam_ids)` returns every exam-level field above in four
queries. The exam history list and detail, exam ops, investigations list and
detail, and the overview exam rows all spread this same dict, and
`analytics/tests_consistency.py` asserts they return identical values. It also asserts that a
student's success rate is identical on the students list, student page, leaderboard, My results
and students who need help, and that one student's pass on one exam is identical on the exam
report, the student page trend and My results.

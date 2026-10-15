"""
Canonical CodeMas metrics: the single source of truth for every rate and
count shown on a page. Views must call these functions instead of computing
their own version, so the same data shows the same number everywhere.

Every function accepts a Submission (or ExamEnrollment) queryset that sets
the scope (an exam, a cohort, a student, everything) and applies the student
population filter itself, so callers can pass `Submission.objects.filter(exam=x)`
and get the canonical number.

Rates are percentages rounded to 1 decimal, or None when the denominator is 0.
The `*_by(qs, *keys)` variants group by one or more fields in one query and
return {key: result} (key is the field value, or a tuple for several keys).

See docs/metrics.md for the definitions table and which pages show each one.
"""
import math

from django.db.models import Count, Max, Q, Sum

from accounts.models import User
from exams.models import ExamEnrollment, Question
from submissions.models import Submission


GRADED_STATUSES = ('passed', 'failed', 'error')   # pending/running are not graded yet

# A flag a trainer dismissed no longer counts as flagged (behavioural and similarity alike);
# the Flags page still lists it under Dismissed.
COUNTED_REVIEW_STATUSES = ('pending', 'confirmed')

_PASSED = Q(status='passed')
_GRADED = Q(status__in=GRADED_STATUSES)
_ATTEMPTED = Q(status__in=('passed', 'failed'))   # a question attempt: refunded 'error' and ungraded ones are not
FLAGGED = Q(behavioural_flag__review_status__in=COUNTED_REVIEW_STATUSES)   # on a Submission queryset
_TO_REVIEW = Q(behavioural_flag__review_status='pending')


# ── basics ───────────────────────────────────────────────────────────────────

def pct(numerator, denominator):
    """numerator / denominator as a percentage rounded to 1 decimal; None when the denominator is 0."""
    if not denominator:
        return None
    return round(numerator / denominator * 100, 1)


def risk(score):
    """Risk shown for one behavioural flag: risk_score × 100, rounded to a whole number."""
    if score is None:
        return None
    return int(math.floor(score * 100 + 0.5 + 1e-9))   # half-up, same as Math.round in the UI


def student_q(prefix='student'):
    """Q filter for the student population (role 'student', not a superuser) through `prefix`."""
    return Q(**{f'{prefix}__role': 'student', f'{prefix}__is_superuser': False})


def students():
    """The student population: users with role 'student' who are not superusers."""
    return User.objects.filter(role='student', is_superuser=False)


def student_submissions(submissions=None):
    """Submissions made by the student population (defaults to all submissions)."""
    qs = Submission.objects.all() if submissions is None else submissions
    return qs.filter(student_q())


def student_enrollments(enrollments=None):
    """Exam enrolments of the student population (defaults to all enrolments)."""
    qs = ExamEnrollment.objects.all() if enrollments is None else enrollments
    return qs.filter(student_q())


def _key(row, keys):
    return row[keys[0]] if len(keys) == 1 else tuple(row[k] for k in keys)


def _grouped(qs, keys, **aggregates):
    """{key: row} of aggregates per group, or {None: row} when no keys are given."""
    if not keys:
        return {None: qs.aggregate(**aggregates)}
    rows = qs.order_by().values(*keys).annotate(**aggregates)
    return {_key(r, keys): r for r in rows}


# ── success rate ─────────────────────────────────────────────────────────────
# A student PASSED an exam when they solved at least half of its questions (a
# 1-question exam: solved it). Solved = at least one 'passed' submission on the
# question; pending, running and refunded 'error' submissions never solve one. It
# counts against every question in the exam, attempted or not.
#
# A question VOIDED for confirmed plagiarism (voided_pairs, below) is not solved either
# (changed 2026-10-08): its tests still passed, but it neither scores nor counts toward the
# pass, so it can drop the student below half. exam_results reports how many solved
# questions were voided (`voided`) so pages can say why; question_success_by leaves the
# student out of the question's solvers. Dismissing or overturning restores it.
#
# Success rate = (student, exam) pairs passed ÷ pairs taken, where taken = at least
# one submission of any status (the same population as "Took the exam"). Grouped by
# exam that is students who passed ÷ students who took it; by student, exams passed ÷
# exams taken; by section and exam, the section's students who passed ÷ who took it.
# The API keeps the field name `accepted_rate` for it (changed 2026-10-07).

def passes(solved, total):
    """The pass rule: at least half of the exam's questions solved (1 of 2, 2 of 3, 2 of 4).
    An exam with no questions is never passed."""
    return total > 0 and solved * 2 >= total


def _solved_pairs(submissions, *keys):
    """({(student_id, question_id): row} counted solves, same for voided ones) over the questions
    with at least one passed submission; row holds `keys`. Four queries."""
    voided = voided_pairs(submissions)
    fields = list(dict.fromkeys(('student_id', 'question_id', *keys)))
    counted, lost = {}, {}
    for r in student_submissions(submissions).filter(_PASSED).order_by().values(*fields).distinct():
        pair = (r['student_id'], r['question_id'])
        (lost if pair in voided else counted)[pair] = r
    return counted, lost


def exam_results(submissions, *keys):
    """One row per (student, exam) taken: {'student_id', 'exam_id', *keys, 'solved', 'voided',
    'total', 'passed'}. total is every question in the exam; solved leaves out voided questions;
    voided is how many solved questions were not counted for confirmed plagiarism. Six queries."""
    fields = list(dict.fromkeys(('student_id', 'exam_id', *keys)))
    rows = list(student_submissions(submissions).order_by().values(*fields).distinct())
    counted, lost = _solved_pairs(submissions, 'exam_id')
    tally = {}
    for which, pairs in (('solved', counted), ('voided', lost)):
        for r in pairs.values():
            t = tally.setdefault((r['student_id'], r['exam_id']), {'solved': 0, 'voided': 0})
            t[which] += 1
    totals = dict(
        Question.objects.filter(exam_id__in={r['exam_id'] for r in rows}).order_by()
        .values('exam_id').annotate(n=Count('id')).values_list('exam_id', 'n')
    )
    for r in rows:
        r.update(tally.get((r['student_id'], r['exam_id']), {'solved': 0, 'voided': 0}))
        r['total'] = totals.get(r['exam_id'], 0)
        r['passed'] = passes(r['solved'], r['total'])
    return rows


def _success(passed, taken):
    return {'passed': passed, 'taken': taken, 'accepted_rate': pct(passed, taken)}


def success_by(submissions, *keys):
    """Success rate = (student, exam) pairs passed ÷ pairs taken, per group. Keys must be
    fixed for a (student, exam) pair: 'exam_id', 'student_id', 'student__cohort'."""
    totals = {}
    for r in exam_results(submissions, *keys):
        t = totals.setdefault(_key(r, keys) if keys else None, [0, 0])
        t[0] += r['passed']
        t[1] += 1
    return {k: _success(p, n) for k, (p, n) in totals.items()}


def success(submissions):
    """Success rate for one scope (see success_by)."""
    return success_by(submissions).get(None, _success(0, 0))


def _question_success(solved_n, attempted):
    return {'solved_students': solved_n, 'attempted_students': attempted, 'accepted_rate': pct(solved_n, attempted)}


def question_success_by(submissions, *keys):
    """Question success rate = students who solved the question ÷ students who attempted it
    (a passed or failed submission), keyed by question_id, or (*keys, question_id). A student
    whose question is voided for confirmed plagiarism attempted it but did not solve it."""
    rows = _grouped(
        student_submissions(submissions).filter(_ATTEMPTED), (*keys, 'question_id'),
        attempted=Count('student_id', distinct=True),
    )
    solved = {}
    for r in _solved_pairs(submissions, *keys)[0].values():
        k = _key(r, (*keys, 'question_id'))
        solved[k] = solved.get(k, 0) + 1
    return {k: _question_success(solved.get(k, 0), r['attempted']) for k, r in rows.items()}


# ── flagged students, took, flags to review ─────────────────────────────────

CONFIDENCE_RANK = {'high': 3, 'medium': 2, 'low': 1}   # most suspicious = highest; no flag = 0


def behavioural_flags(flags=None):
    """Behavioural flags that count: every flag except the ones a trainer dismissed."""
    from plagiarism.models import BehaviouralFlag
    qs = BehaviouralFlag.objects.all() if flags is None else flags
    return qs.filter(review_status__in=COUNTED_REVIEW_STATUSES)


def similarity_flags(flags=None):
    """Similarity pairs that count: above the threshold (flagged) and not dismissed by a trainer."""
    from plagiarism.models import PlagiarismFlag
    qs = PlagiarismFlag.objects.all() if flags is None else flags
    return qs.filter(flagged=True, review_status__in=COUNTED_REVIEW_STATUSES)


def max_confidence_by_student(flags=None):
    """{student_id: {'max_confidence', 'max_risk_score'}} over the counted behavioural flags
    (student population only): a student's level is their most suspicious flag."""
    out = {}
    for r in (
        behavioural_flags(flags).filter(student_q('submission__student')).order_by()
        .values('submission__student_id', 'confidence').annotate(mx=Max('risk_score'))
    ):
        row = out.setdefault(r['submission__student_id'], {'max_confidence': None, 'max_risk_score': 0})
        if CONFIDENCE_RANK.get(r['confidence'], 0) > CONFIDENCE_RANK.get(row['max_confidence'], 0):
            row['max_confidence'] = r['confidence']
        row['max_risk_score'] = max(row['max_risk_score'], r['mx'] or 0)
    return out


def _flagged(flagged, took):
    return {'flagged_students': flagged, 'took': took, 'flagged_students_rate': pct(flagged, took)}


def _student_counts_by(submissions, keys):
    return _grouped(
        student_submissions(submissions), keys,
        took=Count('student_id', distinct=True),
        flagged=Count('student_id', distinct=True, filter=FLAGGED),
        to_review=Count('id', filter=_TO_REVIEW),
        graded=Count('id', filter=_GRADED),
    )


def flagged_students_by(submissions, *keys):
    """Flagged students = students with at least one behavioural flag (not dismissed) ÷ students who submitted, per group."""
    rows = _student_counts_by(submissions, keys)
    return {k: _flagged(r['flagged'] or 0, r['took'] or 0) for k, r in rows.items() if r['took']}


def flagged_students(submissions):
    """Flagged students = students with at least one behavioural flag (not dismissed) ÷ students who submitted."""
    return flagged_students_by(submissions).get(None, _flagged(0, 0))


def took_by(submissions, *keys):
    """Took = number of distinct students with at least one submission (any status), per group."""
    return {k: v['took'] for k, v in flagged_students_by(submissions, *keys).items()}


def flags_to_review_by(submissions, *keys):
    """Flags to review = behavioural flags still pending review on these submissions, per group."""
    rows = _student_counts_by(submissions, keys)
    return {k: r['to_review'] or 0 for k, r in rows.items() if r['took']}


def flags_to_review(submissions=None):
    """Flags to review = behavioural flags still pending review (on all student submissions by default)."""
    return flags_to_review_by(student_submissions(submissions)).get(None, 0)


# ── participation ────────────────────────────────────────────────────────────

def enrolled_by(enrollments, *keys):
    """Enrolled = students enrolled, per group."""
    rows = _grouped(student_enrollments(enrollments), keys, n=Count('student_id', distinct=True))
    return {k: r['n'] or 0 for k, r in rows.items() if r['n']}


def _participation(took, enrolled):
    return {'took': took, 'enrolled': enrolled, 'took_rate': pct(took, enrolled)}


def participation_by(submissions, enrollments, *keys):
    """Took the exam = students who submitted ÷ students enrolled, per group (keys must exist on both querysets)."""
    took = took_by(submissions, *keys)
    enrolled = enrolled_by(enrollments, *keys)
    return {k: _participation(took.get(k, 0), enrolled.get(k, 0)) for k in set(took) | set(enrolled)}


def participation(submissions, enrollments):
    """Took the exam = students who submitted ÷ students enrolled."""
    return participation_by(submissions, enrollments).get(None, _participation(0, 0))


# ── one-call summaries (what list and detail pages spread into their payload) ─

EMPTY_SUMMARY = {
    **_participation(0, 0),
    'passed_students': 0, 'accepted_rate': None,
    'graded_submissions': 0,   # decides a section's "latest graded exam" on the overview
    'flagged_students': 0, 'flagged_students_rate': None,
    'flags_to_review': 0,
}


def summary_by(submissions, enrollments, *keys):
    """Every canonical metric for each group in 4 queries: participation, success rate,
    flagged students, flags to review. Keys must be fixed for a (student, exam) pair."""
    counts = _student_counts_by(submissions, keys)
    succ = success_by(submissions, *keys)
    enrolled = enrolled_by(enrollments, *keys)
    out = {}
    for k in set(counts) | set(enrolled):
        c = counts.get(k) or {}
        took, flagged = c.get('took') or 0, c.get('flagged') or 0
        out[k] = {
            **EMPTY_SUMMARY,
            **_participation(took, enrolled.get(k, 0)),
            'passed_students': succ.get(k, {}).get('passed', 0),   # taken == took: the same students
            'accepted_rate': succ.get(k, {}).get('accepted_rate'),
            'graded_submissions': c.get('graded') or 0,
            'flagged_students': flagged,
            'flagged_students_rate': pct(flagged, took),
            'flags_to_review': c.get('to_review') or 0,
        }
    return out


def summary(submissions, enrollments):
    """Every canonical metric for one scope (see summary_by)."""
    return summary_by(submissions, enrollments).get(None, dict(EMPTY_SUMMARY))


def exam_summaries(exam_ids=None):
    """{exam_id: summary} for the given exams (all exams when None); exams with no data get EMPTY_SUMMARY."""
    subs = Submission.objects.all()
    enr = ExamEnrollment.objects.all()
    if exam_ids is not None:
        exam_ids = list(exam_ids)
        subs = subs.filter(exam_id__in=exam_ids)
        enr = enr.filter(exam_id__in=exam_ids)
    out = summary_by(subs, enr, 'exam_id')
    for eid in exam_ids or []:
        out.setdefault(eid, dict(EMPTY_SUMMARY))
    return out


def exam_summary(exam_id):
    """Every canonical metric for one exam."""
    return exam_summaries([exam_id])[exam_id]


def hardest_question(rows_by_question):
    """(question_id, row) with the lowest question success rate among questions someone
    attempted; a tie goes to the lowest question id. None when nothing was attempted."""
    graded = [(qid, row) for qid, row in rows_by_question.items() if row.get('accepted_rate') is not None]
    return min(graded, key=lambda kv: (kv[1]['accepted_rate'], kv[0]), default=None)


# ── integrity health band (investigation list and detail) ────────────────────

def integrity_health(flagged_students_rate):
    """'red' / 'amber' / 'green' from the flagged-students rate, using the overview's at-risk / watch thresholds."""
    from dashboard.health import HEALTH_RULES
    if flagged_students_rate is None:
        return 'green'
    if flagged_students_rate >= HEALTH_RULES['at_risk']['flagged_students_pct']:
        return 'red'
    if flagged_students_rate >= HEALTH_RULES['watch']['flagged_students_pct']:
        return 'amber'
    return 'green'


# ── Plagiarism: withheld points and under review ─────────────────────────────
# Confirmed plagiarism costs the student their points (and so their rank). A
# (student, question) is VOIDED when, on that question, the student has
#   (a) a CONFIRMED behavioural flag on any of their submissions, or
#   (b) a CONFIRMED similarity pair on one of their submissions AND a behavioural flag
#       (not dismissed) of their own.
# A confirmed pair alone never voids: it protects the classmate whose code merely
# matched a suspect's. Pending flags never cost points; trainer pages mark the student
# "Under review" instead. Pass every submission in scope (not only the passed ones):
# the flag may sit on a failed attempt.

_CONFIRMED_BEHAVIOUR = Q(behavioural_flag__review_status='confirmed')
_CONFIRMED_SIMILARITY = (
    Q(plagiarism_as_first__flagged=True, plagiarism_as_first__review_status='confirmed')
    | Q(plagiarism_as_second__flagged=True, plagiarism_as_second__review_status='confirmed')
)
_PENDING_SIMILARITY = (
    Q(plagiarism_as_first__flagged=True, plagiarism_as_first__review_status='pending')
    | Q(plagiarism_as_second__flagged=True, plagiarism_as_second__review_status='pending')
)


def voided_pairs(submissions):
    """{(student_id, question_id)} whose points are withheld for confirmed plagiarism (rule above). Three queries."""
    subs = student_submissions(submissions).order_by()

    def pairs(q):
        return set(subs.filter(q).values_list('student_id', 'question_id').distinct())

    return pairs(_CONFIRMED_BEHAVIOUR) | (pairs(_CONFIRMED_SIMILARITY) & pairs(FLAGGED))


def under_review(submissions):
    """Student ids with a flag still pending review on these submissions: a behavioural flag,
    or a similarity pair on either side. Shown on trainer pages only; the rank is unchanged."""
    return set(
        student_submissions(submissions).filter(_TO_REVIEW | _PENDING_SIMILARITY)
        .order_by().values_list('student_id', flat=True).distinct()
    )


def _solved_points(submissions):
    """{(student_id, question_id): points} for every question solved (at least one passed
    submission), worth Question.points (easy 10, medium 20, hard 30)."""
    rows = (
        student_submissions(submissions).filter(status='passed')
        .order_by()  # the model's default ordering would otherwise defeat distinct()
        .values_list('student_id', 'question_id', 'question__difficulty').distinct()
    )
    return {(sid, qid): Question.POINTS_MAP.get(d, 20) for sid, qid, d in rows}


def _split_points(submissions):
    """({pair: points} earned, {pair: points} withheld) over the solved (student_id, question_id) pairs."""
    voided = voided_pairs(submissions)
    earned, withheld = {}, {}
    for pair, pts in _solved_points(submissions).items():
        (withheld if pair in voided else earned)[pair] = pts
    return earned, withheld


def earned_points(submissions):
    """{(student_id, question_id): points} that count: solved and not voided. The per-question
    view of points_by_student (a student page sums it per exam)."""
    return _split_points(submissions)[0]


def withheld_points(submissions):
    """{(student_id, question_id): points} the student solved but lost to confirmed plagiarism.
    A voided question the student never solved withholds nothing and is left out."""
    return _split_points(submissions)[1]


def points_withheld_by_student(submissions):
    """{student_id: points withheld}, only students who lost points (see withheld_points)."""
    out = {}
    for (sid, _), pts in withheld_points(submissions).items():
        out[sid] = out.get(sid, 0) + pts
    return out


# ── Score and rank (student-facing: Home, My results, Leaderboard) ─────────────

def points_by_student(submissions):
    """Points per student: every question with at least one passed submission counts once,
    worth Question.points (easy 10, medium 20, hard 30), except questions voided for confirmed
    plagiarism (see voided_pairs). Superusers excluded."""
    out = {}
    for (sid, _), pts in earned_points(submissions).items():
        out[sid] = out.get(sid, 0) + pts
    return out


def competition_rank(scores, student_id, times=None):
    """Tie-aware rank from {student_id: score}: rank = 1 + students ahead, ahead_of = students
    behind. With `times` ({student_id: average solve seconds}, from solve_times), equal scores
    are split by speed, faster first; students share a rank only when both are equal, and a
    student with no timed pass counts as slowest. Every page that shows a rank passes the times
    for the same students and submissions, so the report, My results, Home and the leaderboard agree."""
    times = times or {}

    def key(sid):
        t = times.get(sid)
        return (scores.get(sid, 0), -(t if t is not None else float('inf')))

    mine = key(student_id)
    keys = [key(sid) for sid in scores]
    return {
        'rank': 1 + sum(1 for k in keys if k > mine),
        'ahead_of': sum(1 for k in keys if k < mine),
        'size': len(scores),
    }


def exam_standing(scores, student_id, times=None):
    """A rank on ONE exam (the exam report and My results): competition_rank over `scores`,
    the students who took the exam (My results: those in the student's section), except that
    a student with no points on it (nothing solved, or everything withheld) is not ranked:
    rank None, shown as "Not ranked". size is how many took it ("#2 of 3")."""
    standing = competition_rank(scores, student_id, times)
    if scores.get(student_id, 0) <= 0:
        standing['rank'] = None
    return standing


def solve_times(submissions):
    """{student_id: average seconds to a passing submission}: the rank tie-break after points,
    the same number as the exam report's "Avg solve". Passes on questions voided for confirmed
    plagiarism don't count. Students with no timed pass are left out."""
    voided = voided_pairs(submissions)
    totals = {}
    for r in (
        student_submissions(submissions).filter(status='passed', time_to_complete_seconds__gt=0)
        .order_by().values('student_id', 'question_id')
        .annotate(total=Sum('time_to_complete_seconds'), n=Count('id'))
    ):
        if (r['student_id'], r['question_id']) in voided:
            continue
        t = totals.setdefault(r['student_id'], [0, 0])
        t[0] += r['total']
        t[1] += r['n']
    return {sid: total / n for sid, (total, n) in totals.items()}


def scores_for(student_ids, submissions=None):
    """{student_id: points} for the given students, 0 for students who solved nothing.
    Pass `submissions` to score a subset (e.g. one exam)."""
    ids = list(student_ids)
    subs = Submission.objects.filter(student_id__in=ids) if submissions is None else submissions.filter(student_id__in=ids)
    earned = points_by_student(subs)
    return {sid: earned.get(sid, 0) for sid in ids}


def cohort_scores(cohort, submissions=None):
    """{student_id: points} for every student in the cohort, 0 for students who solved nothing.
    Pass `submissions` to score a subset (e.g. one exam)."""
    return scores_for(students().filter(cohort=cohort).values_list('id', flat=True), submissions)


def all_scores():
    """{student_id: points} for every student in every cohort, 0 for students who solved
    nothing: the population behind the leaderboard's All view and the overall rank."""
    return scores_for(students().values_list('id', flat=True))


def available_questions(student):
    """Questions the student can earn points from: every question in exams they are enrolled in
    that have started (or are open), plus any question they have already attempted."""
    from django.utils import timezone
    from exams.models import Question
    now = timezone.now()
    return Question.objects.filter(
        Q(exam__enrollments__student=student) & (Q(exam__start_time__lte=now) | Q(exam__is_active=True))
        | Q(submissions__student=student)
    ).distinct()


def difficulty_progress(student):
    """Per difficulty: questions solved, questions available, points earned, and points
    withheld for confirmed plagiarism (tests passed, but neither solved nor in the points)."""
    from exams.models import Question
    available = available_questions(student)
    mine = Submission.objects.filter(student=student)
    solved_ids = set(mine.filter(status='passed').order_by().values_list('question_id', flat=True).distinct())
    voided = {qid for _, qid in voided_pairs(mine)}
    out = {d: {'solved': 0, 'available': 0, 'points': 0, 'withheld': 0} for d in Question.POINTS_MAP}
    for q_id, difficulty in available.values_list('id', 'difficulty'):
        bucket = out.setdefault(difficulty, {'solved': 0, 'available': 0, 'points': 0, 'withheld': 0})
        bucket['available'] += 1
        if q_id in solved_ids:
            bucket['solved'] += q_id not in voided   # a voided question is not solved (see exam_results)
            bucket['withheld' if q_id in voided else 'points'] += Question.POINTS_MAP.get(difficulty, 20)
    return out


def score_available(student):
    """Total points the student could have earned so far (see available_questions)."""
    from exams.models import Question
    # Select the id too: DISTINCT over difficulty alone would collapse questions that share a difficulty
    return sum(Question.POINTS_MAP.get(d, 20) for _, d in available_questions(student).values_list('id', 'difficulty'))

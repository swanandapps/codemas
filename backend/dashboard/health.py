"""
Cohort and exam health rules for the trainer Overview page.

The pure rule functions (band_for_accepted, compute_delta, classify_cohort,
classify_exam) take plain numbers and have no DB dependency, so they are
unit-tested directly in dashboard/tests_health.py without touching the
database. build_dashboard_health() does the DB aggregation and calls the
pure functions to decide each cohort/exam's health state. All rates come
from analytics.metrics (the single source of truth, see docs/metrics.md).
"""
from django.db.models import Count, Q

from analytics import metrics
from exams.models import Exam, ExamEnrollment, Question
from submissions.models import Submission


# These are *defaults* — there is no trainer-facing override yet, but the
# endpoint echoes this dict back as `rules` so the UI can print the exact
# thresholds it is using, without hardcoding them twice.
# Every rate here is the canonical one from analytics.metrics.
HEALTH_RULES = {
    'at_risk': {
        'latest_accepted_pct': 40,     # latest exam success rate (section's students who passed) below this
        'struggling_share_pct': 25,    # % of students struggling at/above this
        'flagged_students_pct': 50,    # flagged students / students who took the latest exam, at/above this
        'participation_pct': 60,       # took/enrolled below this (only when enrolled > 0)
    },
    'watch': {
        'latest_accepted_pct': 55,
        'delta_pts': -8,               # latest - previous_avg at/below this
        'struggling_share_pct': 20,
        'flagged_students_pct': 30,
        'participation_pct': 85,
    },
}


def _round1(v):
    return round(v, 1) if v is not None else None


def band_for_accepted(accepted_pct):
    """Bucket a single student's success rate (exams passed ÷ exams taken) into a health band."""
    if accepted_pct is None:
        return 'no_submissions'
    if accepted_pct >= 70:
        return 'thriving'
    if accepted_pct >= 40:
        return 'steady'
    return 'struggling'


def compute_delta(series):
    """series: success rate per exam, ordered oldest -> newest (latest last).

    Returns (previous_avg, delta) where previous_avg is the mean of up to
    the 3 exams before the latest, and delta = latest - previous_avg.
    Both are None when there is no previous exam to compare against.
    """
    series = [v for v in series if v is not None]
    if len(series) < 2:
        return None, None
    latest = series[-1]
    previous = series[-4:-1]
    if not previous:
        return None, None
    avg = sum(previous) / len(previous)
    return _round1(avg), _round1(latest - avg)


def _below(value, threshold):
    return value is not None and value < threshold


def _at_least(value, threshold):
    return value is not None and value >= threshold


def classify_exam(accepted_rate, flagged_students_rate):
    """Exam-level health: only uses the exam's own success rate and flagged-students rate.
    A None rate (nothing graded / nobody took it) never fires a rule."""
    r = HEALTH_RULES['at_risk']
    w = HEALTH_RULES['watch']
    if _below(accepted_rate, r['latest_accepted_pct']) or _at_least(flagged_students_rate, r['flagged_students_pct']):
        return 'at_risk'
    if _below(accepted_rate, w['latest_accepted_pct']) or _at_least(flagged_students_rate, w['flagged_students_pct']):
        return 'watch'
    return 'on_track'


def _flagged_reason(rate):
    return f"{rate}% of students who took the latest exam were flagged"


def classify_cohort(latest_accepted, delta, struggling_share_pct, flagged_students_rate, participation_pct):
    """Cohort-level health with plain-English reasons for every rule that fired.

    participation_pct is None when the cohort has no one enrolled in the
    latest exam (participation rules are skipped in that case). A None
    success or flagged-students rate also never fires its rule.
    """
    r = HEALTH_RULES['at_risk']
    reasons = []
    if _below(latest_accepted, r['latest_accepted_pct']):
        reasons.append(f"the latest exam's success rate is {latest_accepted}%, below {r['latest_accepted_pct']}%")
    if struggling_share_pct >= r['struggling_share_pct']:
        reasons.append(f"{struggling_share_pct}% of students are struggling")
    if _at_least(flagged_students_rate, r['flagged_students_pct']):
        reasons.append(_flagged_reason(flagged_students_rate))
    if _below(participation_pct, r['participation_pct']):
        reasons.append(f"only {participation_pct}% of enrolled students took the latest exam")
    if reasons:
        return 'at_risk', reasons

    w = HEALTH_RULES['watch']
    reasons = []
    if _below(latest_accepted, w['latest_accepted_pct']):
        reasons.append(f"the latest exam's success rate is {latest_accepted}%, below {w['latest_accepted_pct']}%")
    if delta is not None and delta <= w['delta_pts']:
        reasons.append(f"success rate fell {abs(delta)} points against the previous three exams")
    if struggling_share_pct >= w['struggling_share_pct']:
        reasons.append(f"{struggling_share_pct}% of students are struggling")
    if _at_least(flagged_students_rate, w['flagged_students_pct']):
        reasons.append(_flagged_reason(flagged_students_rate))
    if _below(participation_pct, w['participation_pct']):
        reasons.append(f"only {participation_pct}% of enrolled students took the latest exam")
    if reasons:
        return 'watch', reasons

    return 'on_track', []


_STATE_ORDER = {'at_risk': 0, 'watch': 1, 'on_track': 2}

# canonical exam-level fields shown on the overview (exam rows and each cohort's latest exam)
_EXAM_ROW_FIELDS = (
    'took', 'enrolled', 'took_rate',
    'passed_students', 'accepted_rate',
    'flagged_students', 'flagged_students_rate',
)


def build_dashboard_health():
    """DB-backed aggregation for GET /api/dashboard/health/. Every number comes
    from analytics.metrics (grouped queries, no N+1), so the overview shows the
    same success rate / took / flagged students as every other page."""

    population = metrics.students()
    unassigned_students = population.filter(Q(cohort='') | Q(cohort__isnull=True)).count()
    in_cohorts = population.exclude(cohort='').exclude(cohort__isnull=True)
    cohort_names = sorted(set(in_cohorts.values_list('cohort', flat=True)))
    students_in_cohorts = in_cohorts.count()

    all_subs = Submission.objects.all()

    # --- per-student success rate (exams passed / exams taken) and flag count over ALL their submissions ---
    student_accepted = {
        sid: row['accepted_rate'] for sid, row in metrics.success_by(all_subs, 'student_id').items()
    }
    flag_rows = (   # dismissed flags don't count
        metrics.behavioural_flags().filter(metrics.student_q('submission__student'))
        .values('submission__student_id').annotate(n=Count('id')).order_by()
    )
    student_flags = {row['submission__student_id']: row['n'] for row in flag_rows}
    student_info = {s['id']: s for s in population.values('id', 'username', 'cohort')}

    # --- exams, ordered oldest -> newest, excluding ones without a start_time ---
    all_exams = list(
        Exam.objects.filter(start_time__isnull=False)
        .order_by('start_time')
        .values('id', 'title', 'start_time')
    )
    exam_order = {e['id']: i for i, e in enumerate(all_exams)}
    exam_by_id = {e['id']: e for e in all_exams}

    # hardest question per exam = lowest question success rate among attempted questions, ties to the lowest id
    question_titles = dict(Question.objects.filter(exam_id__in=exam_order).values_list('id', 'title'))
    questions_by_exam = {}
    for (exam_id, question_id), row in metrics.question_success_by(all_subs, 'exam_id').items():
        questions_by_exam.setdefault(exam_id, {})[question_id] = row
    hardest_by_exam = {}
    for exam_id, rows in questions_by_exam.items():
        question_id, row = metrics.hardest_question(rows)
        hardest_by_exam[exam_id] = {
            'hardest_question': question_titles.get(question_id),
            'hardest_accepted_rate': row['accepted_rate'],
        }

    # --- cohort x exam canonical numbers (success rate = the section's students who passed the
    # exam / who took it), and flags to review per cohort ---
    cohort_subs = all_subs.exclude(student__cohort='')
    cohort_exam = metrics.summary_by(
        cohort_subs, ExamEnrollment.objects.exclude(student__cohort=''),
        'student__cohort', 'exam_id',
    )
    cohort_to_review = metrics.flags_to_review_by(cohort_subs, 'student__cohort')

    # exams each cohort has graded submissions on (only exams with a start_time)
    cohort_exam_ids = {}
    for (cohort, exam_id), row in cohort_exam.items():
        if exam_id in exam_order and row['graded_submissions']:
            cohort_exam_ids.setdefault(cohort, set()).add(exam_id)

    cohort_student_ids = {}
    for student_id, info in student_info.items():
        cohort_student_ids.setdefault(info['cohort'], set()).add(student_id)

    cohorts_out = []
    latest_exam_overall = None  # tracked for the summary (most recent exam across all cohorts)

    for cohort in cohort_names:
        exam_ids = sorted(cohort_exam_ids.get(cohort, set()), key=lambda eid: exam_order[eid])
        exam_ids = exam_ids[-6:]  # keep the last 6

        series = [{
            'exam_id': eid,
            'title': exam_by_id[eid]['title'],
            'start_time': exam_by_id[eid]['start_time'],
            'accepted_rate': cohort_exam[(cohort, eid)]['accepted_rate'],
        } for eid in exam_ids]

        cohort_students = cohort_student_ids.get(cohort, set())
        n_students = len(cohort_students)

        # bands over ALL submissions, for this cohort's students
        bands = {'thriving': 0, 'steady': 0, 'struggling': 0, 'no_submissions': 0}
        for sid in cohort_students:
            bands[band_for_accepted(student_accepted.get(sid))] += 1

        if not exam_ids:
            # no graded exam history for this cohort at all
            cohorts_out.append({
                'cohort': cohort,
                'students': n_students,
                'state': 'on_track',
                'reasons': [],
                'latest': None,
                'previous_avg': None,
                'delta': None,
                'series': [],
                'bands': bands,
                'flags_to_review': cohort_to_review.get(cohort, 0),
            })
            continue

        latest_eid = exam_ids[-1]
        previous_avg, delta = compute_delta([s['accepted_rate'] for s in series])
        latest = cohort_exam[(cohort, latest_eid)]
        struggling_share_pct = metrics.pct(bands['struggling'], n_students) or 0

        state, reasons = classify_cohort(
            latest_accepted=latest['accepted_rate'],
            delta=delta,
            struggling_share_pct=struggling_share_pct,
            flagged_students_rate=latest['flagged_students_rate'],
            participation_pct=latest['took_rate'],
        )

        latest_exam_info = exam_by_id[latest_eid]
        if latest_exam_overall is None or latest_exam_info['start_time'] > latest_exam_overall['start_time']:
            latest_exam_overall = latest_exam_info

        cohorts_out.append({
            'cohort': cohort,
            'students': n_students,
            'state': state,
            'reasons': reasons,
            'latest': {
                'exam_id': latest_eid,
                'title': latest_exam_info['title'],
                'start_time': latest_exam_info['start_time'],
                **{k: latest[k] for k in _EXAM_ROW_FIELDS},
            },
            'previous_avg': previous_avg,
            'delta': delta,
            'series': series,
            'bands': bands,
            'flags_to_review': cohort_to_review.get(cohort, 0),
        })

    cohorts_out.sort(key=lambda c: (_STATE_ORDER[c['state']], c['cohort']))

    # --- exams: last 6 by start_time desc, numbers identical to the exam pages ---
    exams_desc = sorted(all_exams, key=lambda e: e['start_time'], reverse=True)[:6]
    exam_summ = metrics.exam_summaries([e['id'] for e in exams_desc])
    exams_out = []
    for e in exams_desc:
        row = exam_summ[e['id']]
        hardest = hardest_by_exam.get(e['id']) or {}
        exams_out.append({
            'exam_id': e['id'],
            'title': e['title'],
            'start_time': e['start_time'],
            **{k: row[k] for k in _EXAM_ROW_FIELDS},
            'hardest_question': hardest.get('hardest_question'),
            'hardest_accepted_rate': hardest.get('hardest_accepted_rate'),
            'health': classify_exam(row['accepted_rate'], row['flagged_students_rate']),
        })

    # --- students needing help: success rate (exams passed / taken) < 40, up to 8, ascending ---
    needing_help = []
    for sid, rate in student_accepted.items():
        if rate is not None and rate < 40:
            info = student_info.get(sid)
            if not info:
                continue
            needing_help.append({
                'student_id': sid,
                'username': info['username'],
                'cohort': info['cohort'],
                'accepted_rate': rate,
                'flags': student_flags.get(sid, 0),
            })
    needing_help.sort(key=lambda s: s['accepted_rate'])
    needing_help = needing_help[:8]

    summary = {
        'students': students_in_cohorts,
        'cohorts': len(cohort_names),
        'unassigned_students': unassigned_students,
        'latest_exam': (
            {
                'id': latest_exam_overall['id'],
                'title': latest_exam_overall['title'],
                'start_time': latest_exam_overall['start_time'],
            }
            if latest_exam_overall else None
        ),
    }

    return {
        'summary': summary,
        'cohorts': cohorts_out,
        'exams': exams_out,
        'students_needing_help': needing_help,
        'rules': HEALTH_RULES,
    }

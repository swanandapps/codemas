"""A student's integrity outcome per exam, appeals, and the attention counts behind the
sidebar badges. One definition each; My results, the AI exam summary, the Disputes pages
and the badges all read from here.

Points themselves (withheld or not) always come from analytics.metrics.voided_pairs.
"""
from django.db.models import Q

from analytics import metrics
from plagiarism.models import BehaviouralFlag, PlagiarismFlag, ReviewAuditLog
from plagiarism.views import SHOWN_TO_STUDENT, _log_review, cases_to_decide
from submissions.models import Submission

from .models import DisputeRequest

APPEAL_NOTE_MAX = 1000   # characters in a student's response


def _mine(student_id):
    """Q for a similarity pair with the student on either side."""
    return Q(submission_1__student_id=student_id) | Q(submission_2__student_id=student_id)


def has_confirmed_decision(student_id, exam_id):
    """True when the student has a CONFIRMED flag on the exam: their own behaviour flag, or a
    similarity pair on either side. Only such a decision can be appealed."""
    return (
        BehaviouralFlag.objects.filter(submission__student_id=student_id, submission__exam_id=exam_id,
                                       review_status='confirmed').exists()
        or PlagiarismFlag.objects.filter(_mine(student_id), submission_1__exam_id=exam_id,
                                         review_status='confirmed').exists()
    )


def decision_note(student_id, exam_id):
    """The trainer's notes on the student's confirmed flags on the exam, each once, newest
    decision first: what the appeal answers (kept on the appeal, as an overturn rewrites them)."""
    notes = list(
        BehaviouralFlag.objects.filter(submission__student_id=student_id, submission__exam_id=exam_id,
                                       review_status='confirmed').exclude(review_note='')
        .order_by('-submission__submitted_at').values_list('review_note', flat=True)
    ) + list(
        PlagiarismFlag.objects.filter(_mine(student_id), submission_1__exam_id=exam_id, review_status='confirmed')
        .exclude(review_note='').order_by('-id').values_list('review_note', flat=True)
    )
    return '\n\n'.join(dict.fromkeys(n.strip() for n in notes if n.strip()))


def integrity_outcomes(student_id, exam_ids=None):
    """{exam_id: {'outcome', 'points_withheld', 'appeal', 'can_appeal'}} for each exam where the
    student has a decision they can see (SHOWN_TO_STUDENT) or an appeal. Outcome, first match:
        'withheld'    points withheld for confirmed plagiarism (metrics.withheld_points)
        'overturned'  the decision was overturned on appeal: points restored
        'confirmed'   plagiarism confirmed, but no points withheld (e.g. the matched side of a pair)
        'dismissed'   reviewed, no action taken (dismissed with a note)
    appeal is the status of the student's appeal on the exam (None when there is none);
    can_appeal: a confirmed decision and no appeal yet (one round per exam)."""
    subs = Submission.objects.filter(student_id=student_id)
    b_flags = BehaviouralFlag.objects.filter(SHOWN_TO_STUDENT, submission__student_id=student_id)
    pairs = PlagiarismFlag.objects.filter(SHOWN_TO_STUDENT & _mine(student_id))
    appeals = DisputeRequest.objects.filter(student_id=student_id, exam__isnull=False)
    if exam_ids is not None:
        exam_ids = list(exam_ids)
        subs = subs.filter(exam_id__in=exam_ids)
        b_flags = b_flags.filter(submission__exam_id__in=exam_ids)
        pairs = pairs.filter(submission_1__exam_id__in=exam_ids)
        appeals = appeals.filter(exam_id__in=exam_ids)

    withheld = {}
    exam_of = dict(subs.order_by().values_list('question_id', 'exam_id').distinct())
    for (_, qid), pts in metrics.withheld_points(subs).items():
        withheld[exam_of[qid]] = withheld.get(exam_of[qid], 0) + pts

    statuses = {}   # exam_id -> set of the shown review statuses
    for exam_id, review_status in b_flags.order_by().values_list('submission__exam_id', 'review_status'):
        statuses.setdefault(exam_id, set()).add(review_status)
    for exam_id, review_status in pairs.order_by().values_list('submission_1__exam_id', 'review_status'):
        statuses.setdefault(exam_id, set()).add(review_status)
    appeal_of = {}
    for exam_id, status in appeals.order_by('created_at').values_list('exam_id', 'status'):
        appeal_of[exam_id] = status   # legacy rows can be several on one exam: the newest wins

    out = {}
    for exam_id in set(statuses) | set(appeal_of) | set(withheld):
        seen = statuses.get(exam_id, set())
        if withheld.get(exam_id):
            outcome = 'withheld'
        elif appeal_of.get(exam_id) == 'overturned':
            outcome = 'overturned'
        elif 'confirmed' in seen:
            outcome = 'confirmed'
        elif seen:
            outcome = 'dismissed'
        else:
            continue   # an appeal on an exam whose decision is gone: nothing to show
        out[exam_id] = {
            'outcome': outcome,
            'points_withheld': withheld.get(exam_id, 0),
            'appeal': appeal_of.get(exam_id),
            'can_appeal': 'confirmed' in seen and exam_id not in appeal_of,
        }
    return out


def overturn(appeal, trainer, note):
    """Overturn the decision the appeal answers: every behaviour flag of the appellant on the
    exam that still counts becomes dismissed, with the ruling as its note and an audit entry,
    like any review. Similarity pairs are left alone, so a classmate in the same case keeps
    their outcome; by the voided-pairs rule the appellant's points come back."""
    flags = BehaviouralFlag.objects.filter(
        submission__student_id=appeal.student_id, submission__exam_id=appeal.exam_id,
    ).exclude(review_status='dismissed')
    for flag in flags:
        flag.review_status = 'dismissed'
        flag.review_note = note
        flag.reviewed_by = trainer
        flag.save(update_fields=['review_status', 'review_note', 'reviewed_by'])
        _log_review(trainer, 'behavioural', flag.id, 'dismissed', note)


# ── attention (sidebar badges, Home banner) ─────────────────────────────────────

def student_attention(student):
    """What's new for the student since integrity_seen_at (None: everything is new).

    new_decisions: exams where a trainer decided one of the student's flags (a decision My
      results shows) after it, by the review log's time. An exam whose appeal was ruled on
      after it counts as a ruling instead (the overturn's flag changes are part of the ruling).
    new_rulings: the student's appeals upheld or overturned after it.
    latest: the newest of those, for the Home banner, or None."""
    seen = student.integrity_seen_at

    def after(qs, field):
        return qs.filter(**{f'{field}__gt': seen}) if seen else qs

    rulings = list(after(DisputeRequest.objects.filter(
        student=student, status__in=('upheld', 'overturned'), resolved_at__isnull=False,
    ), 'resolved_at').select_related('exam').order_by('-resolved_at'))
    ruled_exams = {r.exam_id for r in rulings}

    flag_exam = {}
    for fid, exam_id in BehaviouralFlag.objects.filter(SHOWN_TO_STUDENT, submission__student=student) \
            .values_list('id', 'submission__exam_id'):
        flag_exam[('behavioural', fid)] = exam_id
    for fid, exam_id in PlagiarismFlag.objects.filter(SHOWN_TO_STUDENT & _mine(student.id)) \
            .values_list('id', 'submission_1__exam_id'):
        flag_exam[('similarity', fid)] = exam_id
    decided = {}   # exam_id -> newest decision time
    logs = after(ReviewAuditLog.objects.filter(
        Q(flag_type='behavioural', flag_id__in=[i for k, i in flag_exam if k == 'behavioural'])
        | Q(flag_type='similarity', flag_id__in=[i for k, i in flag_exam if k == 'similarity'])
    ), 'created_at')
    for flag_type, flag_id, at in logs.order_by().values_list('flag_type', 'flag_id', 'created_at'):
        exam_id = flag_exam[(flag_type, flag_id)]
        if exam_id not in ruled_exams and (exam_id not in decided or at > decided[exam_id]):
            decided[exam_id] = at

    items = [{'kind': 'ruling', 'exam_id': r.exam_id, 'exam_title': r.exam.title if r.exam else None,
              'appeal_id': r.id, 'status': r.status, 'at': r.resolved_at} for r in rulings]
    if decided:
        from exams.models import Exam
        titles = dict(Exam.objects.filter(id__in=decided).values_list('id', 'title'))
        items += [{'kind': 'decision', 'exam_id': eid, 'exam_title': titles.get(eid), 'at': at}
                  for eid, at in decided.items()]
    latest = max(items, key=lambda i: i['at'], default=None)
    return {
        'new_decisions': len(decided),
        'new_rulings': len(rulings),
        'latest': {**latest, 'at': latest['at'].isoformat()} if latest else None,
    }


def trainer_attention():
    """Live counts of what's waiting for a trainer (no seen state)."""
    return {
        'open_appeals': DisputeRequest.objects.filter(status='open').count(),
        'cases_to_decide': cases_to_decide(),
    }

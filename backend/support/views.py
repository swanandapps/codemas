from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from . import integrity
from .models import DisputeRequest
from .serializers import DisputeRequestSerializer, MyAppealSerializer
from ai.tasks import forget_exam_summaries
from exams.models import newest_exam_first


# ── Student 360 Case View ────────────────────────────────────────────────────

class StudentCaseView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from accounts.models import User
        student = User.objects.filter(pk=student_id, role='student').first()
        if not student:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

        from submissions.models import Submission
        from plagiarism.models import BehaviouralFlag, PlagiarismFlag
        from plagiarism.models import ReviewAuditLog

        subs = Submission.objects.filter(student=student).select_related('exam', 'question').order_by('-submitted_at')

        submission_rows = []
        for s in subs:
            submission_rows.append({
                'id':              s.id,
                'exam':            s.exam.title,
                'exam_id':         s.exam_id,
                'question':        s.question.title,
                'language':        s.language,
                'attempt':         s.attempt_number,
                'status':          s.status,
                'submitted_at':    s.submitted_at.isoformat(),
                'behavioural_done': s.behavioural_check_done,
                'similarity_done':  s.similarity_check_done,
            })

        # Behavioural flags
        b_flags = BehaviouralFlag.objects.filter(
            submission__student=student
        ).select_related('submission__exam', 'submission__question', 'reviewed_by').order_by(
            newest_exam_first('submission__exam__'), '-risk_score', '-id')

        behavioural_rows = []
        for f in b_flags:
            behavioural_rows.append({
                'flag_id':       f.id,
                'submission_id': f.submission_id,
                'exam':          f.submission.exam.title,
                'question':      f.submission.question.title,
                'risk_score':    round(f.risk_score, 3),
                'confidence':    f.confidence,
                'signals':       f.signals_triggered,
                'review_status': f.review_status,
                'review_note':   f.review_note,
                'reviewed_by':   f.reviewed_by.username if f.reviewed_by else None,
                'created_at':    f.created_at.isoformat(),
            })

        # Similarity flags (student appears on either side)
        sim_qs = PlagiarismFlag.objects.filter(flagged=True).filter(
            submission_1__student=student
        ) | PlagiarismFlag.objects.filter(flagged=True).filter(
            submission_2__student=student
        )
        sim_qs = sim_qs.select_related(
            'submission_1__student', 'submission_2__student',
            'submission_1__exam', 'submission_2__exam',
        ).order_by(newest_exam_first('submission_1__exam__'), '-similarity_score', '-id')

        similarity_rows = []
        for f in sim_qs:
            is_first = f.submission_1.student_id == student.id
            other_sub = f.submission_2 if is_first else f.submission_1
            similarity_rows.append({
                'flag_id':          f.id,
                'submission_id':    f.submission_1_id if is_first else f.submission_2_id,
                'other_student':    other_sub.student.username,
                'other_student_id': other_sub.student_id,
                'exam':             f.submission_1.exam.title,
                'similarity_score': round(f.similarity_score, 3),
                'review_status':    f.review_status,
                'review_note':      f.review_note,
            })

        # Open disputes by this student
        disputes = DisputeRequest.objects.filter(student=student).values(
            'id', 'exam_id', 'flag_type', 'flag_id', 'student_note', 'status',
            'resolution_note', 'created_at',
        )

        return Response({
            'student': {
                'id':         student.id,
                'username':   student.username,
                'email':      student.email,
                'joined':     student.date_joined.isoformat() if hasattr(student, 'date_joined') else None,
                'total_submissions': len(submission_rows),
                'open_disputes':     DisputeRequest.objects.filter(student=student, status='open').count(),
            },
            'submissions':  submission_rows,
            'behavioural':  behavioural_rows,
            'similarity':   similarity_rows,
            'disputes':     list(disputes),
        })


# ── Appeals: trainer queue / student filing ─────────────────────────────────
# One round per exam: a student responds once to a confirmed plagiarism decision, a trainer
# upholds or overturns it, and the ruling is final (support.integrity holds the rules).

def _case_keys_by_exam(exam_ids):
    """{exam_id: {student_id: case key}}: where each appeal's case-file link opens."""
    from plagiarism.views import case_keys, exam_cases
    return {eid: case_keys(exam_cases(eid)) for eid in set(exam_ids) if eid}


def _legacy_flag_context(d):
    """Short context for a dispute filed on a single flag before appeals were per exam."""
    if d.flag_type == 'behavioural':
        from plagiarism.models import BehaviouralFlag
        bf = BehaviouralFlag.objects.filter(pk=d.flag_id).select_related(
            'submission__exam', 'submission__question'
        ).first()
        if not bf:
            return {}
        return {
            'risk_score':  round(bf.risk_score, 3),
            'confidence':  bf.confidence,
            'signals':     bf.signals_triggered,
            'exam':        bf.submission.exam.title,
            'question':    bf.submission.question.title,
            'submission_id': bf.submission_id,
            'language':    bf.submission.language,
        }
    from plagiarism.models import PlagiarismFlag
    sf = PlagiarismFlag.objects.filter(pk=d.flag_id).select_related(
        'submission_1__exam', 'submission_1__question'
    ).first()
    if not sf:
        return {}
    return {
        'similarity_score': round(sf.similarity_score, 3),
        'exam':             sf.submission_1.exam.title,
        'question':         sf.submission_1.question.title,
        'submission_id':    sf.submission_1_id,
    }


def _trainer_row(d, keys):
    row = DisputeRequestSerializer(d).data
    row['case_key'] = keys.get(d.exam_id, {}).get(d.student_id)
    if d.flag_id is not None:
        row['flag_context'] = _legacy_flag_context(d)
    return row


class DisputeListView(APIView):
    """GET (trainer): appeals, ?status=open (default) | upheld | overturned | all.
    POST (student): {exam_id, student_note} files the one appeal on that exam."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        filter_status = request.query_params.get('status', 'open')
        qs = DisputeRequest.objects.select_related('student', 'resolved_by', 'exam')
        if filter_status != 'all':
            qs = qs.filter(status=filter_status)
        appeals = list(qs)
        keys = _case_keys_by_exam(d.exam_id for d in appeals)
        return Response([_trainer_row(d, keys) for d in appeals])

    def post(self, request):
        if request.user.role != 'student':
            return Response({'error': 'Only students can appeal a decision.'}, status=status.HTTP_403_FORBIDDEN)

        from exams.models import Exam
        from submissions.models import Submission
        exam_id = request.data.get('exam_id')
        note = str(request.data.get('student_note') or '').strip()

        exam = Exam.objects.filter(pk=exam_id).first() if str(exam_id).isdigit() else None
        if not exam or not Submission.objects.filter(student=request.user, exam=exam).exists():
            return Response({'error': "We couldn't find that exam in your results."}, status=status.HTTP_404_NOT_FOUND)
        if not note:
            return Response({'error': 'Write your response before sending it.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(note) > integrity.APPEAL_NOTE_MAX:
            return Response({'error': f'Keep your response to {integrity.APPEAL_NOTE_MAX:,} characters or fewer.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if not integrity.has_confirmed_decision(request.user.id, exam.id):
            return Response({'error': "There's no plagiarism decision on this exam to respond to."},
                            status=status.HTTP_400_BAD_REQUEST)
        already = Response({'error': "You've already responded to the decision on this exam. "
                                     "Each decision can be appealed once."}, status=status.HTTP_400_BAD_REQUEST)
        if DisputeRequest.objects.filter(student=request.user, exam=exam).exists():
            return already
        try:
            with transaction.atomic():
                appeal = DisputeRequest.objects.create(
                    student=request.user, exam=exam, student_note=note,
                    decision_note=integrity.decision_note(request.user.id, exam.id),
                )
        except IntegrityError:   # a second request raced the first
            return already
        forget_exam_summaries([request.user.id], exam.id)   # the outcome now has an appeal under review
        return Response(MyAppealSerializer(appeal).data, status=status.HTTP_201_CREATED)


class MyDisputesView(APIView):
    """GET /api/support/disputes/mine/ (student): their own appeals, newest first. is_new marks a
    ruling made since they last looked (integrity_seen_at)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'student':
            return Response({'error': 'Only students have appeals.'}, status=status.HTTP_403_FORBIDDEN)
        seen = request.user.integrity_seen_at
        rows = []
        for d in DisputeRequest.objects.filter(student=request.user).select_related('exam').order_by('-created_at'):
            row = MyAppealSerializer(d).data
            row['is_new'] = bool(d.resolved_at and (seen is None or d.resolved_at > seen))
            rows.append(row)
        return Response(rows)


def _build_dispute_detail(dispute):
    """The trainer's appeal page: the decision, the student's response and the case link.
    A legacy per-flag dispute also carries that flag and its code, as before."""
    data = _trainer_row(dispute, _case_keys_by_exam([dispute.exam_id]))
    if dispute.flag_id is None:
        return data

    if dispute.flag_type == 'behavioural':
        from plagiarism.models import BehaviouralFlag
        bf = BehaviouralFlag.objects.filter(pk=dispute.flag_id).select_related(
            'submission__exam', 'submission__question', 'submission__student', 'reviewed_by'
        ).first()
        if bf:
            s = bf.submission
            data['flag_detail'] = {
                'risk_score':    round(bf.risk_score, 3),
                'confidence':    bf.confidence,
                'signals':       bf.signals_triggered,
                'paste_score':   round(bf.paste_score, 3),
                'time_score':    round(bf.time_score, 3),
                'snapshot_score': round(bf.snapshot_score, 3),
                'review_status': bf.review_status,
                'review_note':   bf.review_note,
                'reviewed_by':   bf.reviewed_by.username if bf.reviewed_by else None,
            }
            data['submission'] = {
                'id':          s.id,
                'exam':        s.exam.title,
                'exam_id':     s.exam_id,
                'question':    s.question.title,
                'description': s.question.description[:500],
                'language':    s.language,
                'attempt':     s.attempt_number,
                'status':      s.status,
                'submitted_at': s.submitted_at.isoformat(),
                'code':        s.code,
                'had_paste':   s.had_paste_event,
                'paste_chars': s.paste_char_count,
                'tab_switches': s.tab_switch_count,
                'time_to_complete_s': s.time_to_complete_seconds,
            }
    else:
        from plagiarism.models import PlagiarismFlag
        sf = PlagiarismFlag.objects.filter(pk=dispute.flag_id).select_related(
            'submission_1__student', 'submission_1__exam', 'submission_1__question',
            'submission_2__student', 'reviewed_by'
        ).first()
        if sf:
            data['flag_detail'] = {
                'similarity_score': round(sf.similarity_score, 3),
                'detection_method': sf.detection_method,
                'review_status':    sf.review_status,
                'review_note':      sf.review_note,
                'reviewed_by':      sf.reviewed_by.username if sf.reviewed_by else None,
            }
            s1, s2 = sf.submission_1, sf.submission_2
            data['submission'] = {
                'id':           s1.id,
                'exam':         s1.exam.title,
                'exam_id':      s1.exam_id,
                'question':     s1.question.title,
                'language':     s1.language,
                'attempt':      s1.attempt_number,
                'submitted_at': s1.submitted_at.isoformat(),
                'code':         s1.code,
            }
            data['matched_submission'] = {
                'id':         s2.id,
                'student':    s2.student.username,
                'student_id': s2.student_id,   # the student page is by user id, not submission id
                'code':       s2.code,
            }
    return data


class DisputeDetailView(APIView):
    """GET (trainer): one appeal. PATCH (trainer): {decision: 'uphold' | 'overturn',
    resolution_note} rules on an OPEN appeal; the reply is required and the ruling is final."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        dispute = DisputeRequest.objects.filter(pk=pk).select_related('student', 'resolved_by', 'exam').first()
        if not dispute:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_build_dispute_detail(dispute))

    def patch(self, request, pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can rule on appeals.'}, status=status.HTTP_403_FORBIDDEN)

        decision = request.data.get('decision')
        note = str(request.data.get('resolution_note') or '').strip()
        if decision not in ('uphold', 'overturn'):
            return Response({'error': 'Choose to uphold or overturn the decision.'}, status=status.HTTP_400_BAD_REQUEST)
        if not note:
            return Response({'error': 'Write a reply to the student: they see it with your ruling.'},
                            status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            dispute = DisputeRequest.objects.select_for_update().filter(pk=pk).first()
            if not dispute:
                return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
            if dispute.status != 'open':
                return Response({'error': 'This appeal has already been ruled on. A ruling is final.'},
                                status=status.HTTP_400_BAD_REQUEST)
            if decision == 'overturn':
                if dispute.exam_id is None:
                    return Response({'error': "This appeal isn't linked to an exam any more, so it can only be upheld."},
                                    status=status.HTTP_400_BAD_REQUEST)
                integrity.overturn(dispute, request.user, note)
            dispute.status          = 'overturned' if decision == 'overturn' else 'upheld'
            dispute.resolution_note = note
            dispute.resolved_by     = request.user
            dispute.resolved_at     = timezone.now()
            dispute.save()

        if dispute.exam_id:
            forget_exam_summaries([dispute.student_id], dispute.exam_id)
        dispute = DisputeRequest.objects.select_related('student', 'resolved_by', 'exam').get(pk=dispute.pk)
        return Response(_build_dispute_detail(dispute))


# ── Attention: sidebar badges and the Home banner ────────────────────────────

class AttentionView(APIView):
    """GET /api/support/attention/ — what's waiting. A student: new decisions and rulings since
    they last looked, and the newest one; a trainer: open appeals and cases to decide."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role == 'trainer':
            return Response(integrity.trainer_attention())
        if request.user.role == 'student':
            return Response(integrity.student_attention(request.user))
        return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)


class AttentionSeenView(APIView):
    """POST /api/support/attention/seen/ — the student opened My results or Disputes: what's
    there now is seen, so the badges and the Home banner clear."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'student':
            return Response({'error': 'Only students mark decisions as seen.'}, status=status.HTTP_403_FORBIDDEN)
        request.user.integrity_seen_at = timezone.now()
        request.user.save(update_fields=['integrity_seen_at'])
        return Response({'seen_at': request.user.integrity_seen_at.isoformat()})


# ── Exam Operations Live Panel ───────────────────────────────────────────────

class ExamOpsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from exams.models import Exam
        exam = Exam.objects.filter(pk=exam_id).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        from submissions.models import Submission
        from plagiarism.models import BehaviouralFlag
        from django.db.models import Count, Q
        from analytics import metrics
        from exams.models import exam_status

        # One row per student who submitted on this exam (student population only)
        subs = metrics.student_submissions(Submission.objects.filter(exam=exam))
        # a submission that couldn't be graded ('error') is refunded, so it isn't an attempt
        attempts = {
            r['student_id']: r for r in
            subs.order_by().values('student_id', 'student__username')
            .annotate(attempts=Count('id', filter=~Q(status='error')))
        }
        latest_by_student = {}
        for sub in subs.order_by('student_id', '-submitted_at', '-id').only('student_id', 'status', 'submitted_at'):
            latest_by_student.setdefault(sub.student_id, sub)
        flagged_ids = set(subs.filter(metrics.FLAGGED).values_list('student_id', flat=True))   # dismissed flags don't count

        student_rows = []
        # most recent submitter first
        for sid, row in sorted(attempts.items(), key=lambda kv: latest_by_student[kv[0]].submitted_at, reverse=True):
            latest = latest_by_student.get(sid)
            student_rows.append({
                'student_id':   sid,
                'username':     row['student__username'],
                'attempts':     row['attempts'],
                'last_status':  latest.status if latest else None,
                'submitted_at': latest.submitted_at.isoformat() if latest else None,
                'has_flag':     sid in flagged_ids,
            })

        # Recent behavioural flags for this exam
        recent_flags = BehaviouralFlag.objects.filter(
            metrics.student_q('submission__student'), submission__exam=exam,
        ).select_related('submission__student', 'submission__question').order_by('-created_at')[:20]

        flag_rows = []
        for f in recent_flags:
            flag_rows.append({
                'flag_id':       f.id,
                'student':       f.submission.student.username,
                'student_id':    f.submission.student_id,
                'question':      f.submission.question.title,
                'submission_id': f.submission_id,
                'risk_score':    round(f.risk_score, 3),
                'risk':          metrics.risk(f.risk_score),
                'confidence':    f.confidence,
                'signals':       f.signals_triggered,
                'review_status': f.review_status,
                'created_at':    f.created_at.isoformat(),
            })

        summary = metrics.exam_summary(exam.id)

        # Time context: live with no end time means open until a trainer ends it (no countdown)
        now = timezone.now()
        status_now = exam_status(exam, now)
        time_info = {
            'status':            status_now,
            'is_live':           status_now == 'live',
            'ends_at':           exam.end_time.isoformat() if exam.end_time else None,
            'seconds_remaining': max(0, int((exam.end_time - now).total_seconds())) if exam.end_time else None,
        }

        return Response({
            'exam': {
                'id':               exam.id,
                'title':            exam.title,
                'duration_minutes': exam.duration_minutes,
                'is_active':        exam.is_active,
                'start_time':       exam.start_time.isoformat() if exam.start_time else None,
                **time_info,
            },
            'student_ops':   student_rows,
            'recent_flags':  flag_rows,
            # canonical exam metrics: identical to exam history, overview and investigations
            **summary,
            'integrity_health': metrics.integrity_health(summary['flagged_students_rate']),
        })

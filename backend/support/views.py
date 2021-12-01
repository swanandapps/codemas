from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from .models import DisputeRequest
from .serializers import DisputeRequestSerializer


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
        ).select_related('submission__exam', 'submission__question', 'reviewed_by')

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
        )

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
            'id', 'flag_type', 'flag_id', 'student_note', 'status',
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


# ── Dispute Queue (trainer) / Submit Dispute (student) ──────────────────────

class DisputeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        filter_status = request.query_params.get('status', 'open')
        qs = DisputeRequest.objects.select_related('student', 'resolved_by')
        if filter_status != 'all':
            qs = qs.filter(status=filter_status)

        # Attach flag context inline
        rows = []
        for d in qs:
            row = DisputeRequestSerializer(d).data
            # pull flag risk/score for quick context
            if d.flag_type == 'behavioural':
                from plagiarism.models import BehaviouralFlag
                bf = BehaviouralFlag.objects.filter(pk=d.flag_id).select_related(
                    'submission__exam', 'submission__question'
                ).first()
                if bf:
                    row['flag_context'] = {
                        'risk_score':  round(bf.risk_score, 3),
                        'confidence':  bf.confidence,
                        'signals':     bf.signals_triggered,
                        'exam':        bf.submission.exam.title,
                        'question':    bf.submission.question.title,
                        'submission_id': bf.submission_id,
                        'language':    bf.submission.language,
                    }
                else:
                    row['flag_context'] = {}
            else:
                from plagiarism.models import PlagiarismFlag
                sf = PlagiarismFlag.objects.filter(pk=d.flag_id).select_related(
                    'submission_1__exam', 'submission_1__question'
                ).first()
                if sf:
                    row['flag_context'] = {
                        'similarity_score': round(sf.similarity_score, 3),
                        'exam':             sf.submission_1.exam.title,
                        'question':         sf.submission_1.question.title,
                        'submission_id':    sf.submission_1_id,
                    }
                else:
                    row['flag_context'] = {}
            rows.append(row)

        return Response(rows)

    def post(self, request):
        # Students submit disputes
        if request.user.role != 'student':
            return Response({'error': 'Only students can file disputes'}, status=status.HTTP_403_FORBIDDEN)

        flag_type = request.data.get('flag_type')
        flag_id   = request.data.get('flag_id')
        note      = request.data.get('student_note', '').strip()

        if flag_type not in ('behavioural', 'similarity'):
            return Response({'error': 'flag_type must be behavioural or similarity'}, status=status.HTTP_400_BAD_REQUEST)
        if not flag_id or not note:
            return Response({'error': 'flag_id and student_note are required'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify the flag belongs to this student
        if flag_type == 'behavioural':
            from plagiarism.models import BehaviouralFlag
            flag = BehaviouralFlag.objects.filter(pk=flag_id, submission__student=request.user).first()
        else:
            from plagiarism.models import PlagiarismFlag
            flag = PlagiarismFlag.objects.filter(
                pk=flag_id, flagged=True
            ).filter(
                submission_1__student=request.user
            ).first() or PlagiarismFlag.objects.filter(
                pk=flag_id, flagged=True, submission_2__student=request.user
            ).first()

        if not flag:
            return Response({'error': 'Flag not found or does not belong to you'}, status=status.HTTP_404_NOT_FOUND)

        if DisputeRequest.objects.filter(student=request.user, flag_type=flag_type, flag_id=flag_id).exists():
            return Response({'error': 'You already filed a dispute for this flag'}, status=status.HTTP_400_BAD_REQUEST)

        dispute = DisputeRequest.objects.create(
            student=request.user,
            flag_type=flag_type,
            flag_id=int(flag_id),
            student_note=note,
        )
        return Response(DisputeRequestSerializer(dispute).data, status=status.HTTP_201_CREATED)


def _build_dispute_detail(dispute):
    """Build the full detail payload for a single dispute."""
    data = DisputeRequestSerializer(dispute).data

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
                'id':       s2.id,
                'student':  s2.student.username,
                'code':     s2.code,
            }
    return data


class DisputeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        dispute = DisputeRequest.objects.filter(pk=pk).select_related('student', 'resolved_by').first()
        if not dispute:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_build_dispute_detail(dispute))

    def patch(self, request, pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can resolve disputes'}, status=status.HTTP_403_FORBIDDEN)

        dispute = DisputeRequest.objects.filter(pk=pk).select_related('student', 'resolved_by').first()
        if not dispute:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        if new_status not in ('resolved', 'escalated'):
            return Response({'error': 'status must be resolved or escalated'}, status=status.HTTP_400_BAD_REQUEST)

        dispute.status          = new_status
        dispute.resolution_note = request.data.get('resolution_note', '')
        dispute.resolved_by     = request.user
        dispute.resolved_at     = timezone.now()
        dispute.save()

        return Response(_build_dispute_detail(dispute))


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
        from django.db.models import Count, Max

        # All students enrolled (who have ≥1 submission for this exam)
        sub_summary = (
            Submission.objects
            .filter(exam=exam)
            .values('student_id', 'student__username')
            .annotate(
                attempts=Count('id'),
                last_status=Max('status'),
            )
            .order_by('student__username')
        )

        student_rows = []
        for row in sub_summary:
            latest = Submission.objects.filter(
                exam=exam, student_id=row['student_id']
            ).order_by('-submitted_at').first()

            student_rows.append({
                'student_id':   row['student_id'],
                'username':     row['student__username'],
                'attempts':     row['attempts'],
                'last_status':  latest.status if latest else None,
                'submitted_at': latest.submitted_at.isoformat() if latest else None,
                'has_flag':     BehaviouralFlag.objects.filter(
                    submission__exam=exam,
                    submission__student_id=row['student_id'],
                ).exists(),
            })

        # Recent behavioural flags for this exam
        recent_flags = BehaviouralFlag.objects.filter(
            submission__exam=exam
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
                'confidence':    f.confidence,
                'signals':       f.signals_triggered,
                'review_status': f.review_status,
                'created_at':    f.created_at.isoformat(),
            })

        # Time context
        now = timezone.now()
        time_info = {}
        if exam.end_time:
            remaining = (exam.end_time - now).total_seconds()
            time_info['ends_at']           = exam.end_time.isoformat()
            time_info['seconds_remaining'] = max(0, int(remaining))
            time_info['is_live']           = exam.is_active and remaining > 0

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
            'total_students':  len(student_rows),
            'flagged_count':   sum(1 for r in student_rows if r['has_flag']),
            'passed_count':    sum(1 for r in student_rows if r['last_status'] == 'passed'),
        })

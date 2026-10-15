from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.pagination import PageNumberPagination
from .models import Submission
from .serializers import SubmissionSerializer, SubmissionCreateSerializer
from exams.models import ExamEnrollment, Question
from execution.tasks import execute_submission
from plagiarism.models import PlagiarismPolicy


def exam_window_error(exam, now=None):
    """None when the exam is open for submissions, else a plain message.

    Open means is_active and now inside [start_time, end_time); a null bound is
    unbounded on that side. Same rule auto_manage_exams uses to open/close exams.
    """
    from django.utils import timezone
    now = now or timezone.now()
    if exam.start_time and now < exam.start_time:
        return "This exam hasn't started yet."
    if exam.end_time and now >= exam.end_time:
        return 'This exam has ended.'
    if not exam.is_active:
        return "This exam isn't open."
    return None


class SubmissionThrottle(UserRateThrottle):
    scope = 'submissions'  # rate in DEFAULT_THROTTLE_RATES['submissions']


class SubmissionCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SubmissionThrottle]

    def post(self, request):
        question_id = request.data.get('question')
        if not question_id:
            return Response({'error': 'question is required'}, status=status.HTTP_400_BAD_REQUEST)

        question = Question.objects.filter(pk=question_id).first()
        if not question:
            return Response({'error': 'Question not found'}, status=status.HTTP_404_NOT_FOUND)

        # Students may only submit to exams they are enrolled in (checked before the lock: nothing is created)
        if request.user.role == 'student':
            enrollment = ExamEnrollment.objects.filter(exam_id=question.exam_id, student=request.user).first()
            if not enrollment:
                return Response({'error': "You're not enrolled in this exam."}, status=status.HTTP_403_FORBIDDEN)
            if enrollment.finished_at:
                return Response({'error': 'You have already submitted this exam.'}, status=status.HTTP_403_FORBIDDEN)

        # Students may only submit while the exam is open (also before the lock: nothing is created)
        if request.user.role == 'student':
            closed = exam_window_error(question.exam)
            if closed:
                return Response({'error': closed}, status=status.HTTP_403_FORBIDDEN)

        serializer = SubmissionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        from django.conf import settings
        from django.db import IntegrityError, transaction
        from django.db.models import Max
        from accounts.models import User
        from jobs.models import Job
        from jobs.services import enqueue

        max_attempts = PlagiarismPolicy.get().max_attempts
        try:
            with transaction.atomic():
                # Lock this student's row so concurrent submits for the same student queue up here
                User.objects.select_for_update().get(pk=request.user.pk)
                mine = Submission.objects.filter(student=request.user, question=question)
                # A submission that couldn't be graded ('error': dead job or no test cases) doesn't count
                if mine.exclude(status='error').count() >= max_attempts:
                    return Response({'error': 'Max attempts reached'}, status=status.HTTP_403_FORBIDDEN)
                attempt_number = (mine.aggregate(m=Max('attempt_number'))['m'] or 0) + 1
                submission = serializer.save(student=request.user, exam=question.exam,
                                             attempt_number=attempt_number, ip_address=request.META.get('REMOTE_ADDR'))
                if submission.language in settings.PIPELINE_LANGUAGES:
                    enqueue(Job.KIND_EXECUTE, submission.id)
                else:
                    transaction.on_commit(lambda: execute_submission.delay(submission.id))
        except IntegrityError:
            return Response({'error': 'Another submission for this question is being saved. Try again'},
                            status=status.HTTP_409_CONFLICT)
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)


class SubmissionStatusView(APIView):
    """Lightweight status for polling: the submission's state and its job's progress."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from jobs.models import Job
        sub = Submission.objects.filter(pk=pk).first()
        if not sub:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role != 'trainer' and sub.student_id != request.user.id:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        job = Job.objects.filter(kind=Job.KIND_EXECUTE, subject_id=sub.id).order_by('-created_at').first()
        return Response({
            'id': sub.id,
            'status': sub.status,
            'results_ready': sub.status in ('passed', 'failed', 'error'),
            'job': None if job is None else {
                'status': job.status, 'attempt': job.attempt, 'queued_at': job.published_at,
                'started_at': job.started_at, 'finished_at': job.finished_at,
            },
        })


class SubmissionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        sub = Submission.objects.filter(pk=pk).select_related('student', 'question', 'exam').first()
        if not sub:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        # students can only view their own; trainers can view all
        if request.user.role != 'trainer' and sub.student != request.user:
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return Response(SubmissionSerializer(sub).data)


class SubmissionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role == 'trainer':
            qs = Submission.objects.select_related('student', 'question', 'exam').all()
        else:
            qs = Submission.objects.select_related('student', 'question', 'exam').filter(student=request.user)

        # search and filter
        search = request.query_params.get('search', '').strip()
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(student__username__icontains=search) |
                Q(question__title__icontains=search) |
                Q(exam__title__icontains=search)
            )

        lang = request.query_params.get('language')
        if lang:
            qs = qs.filter(language=lang)

        sub_status = request.query_params.get('status')
        if sub_status:
            qs = qs.filter(status=sub_status)

        exam_id = request.query_params.get('exam')
        if exam_id:
            qs = qs.filter(exam_id=exam_id)

        student_id = request.query_params.get('student')
        if student_id and request.user.role == 'trainer':
            qs = qs.filter(student_id=student_id)

        # Test counts for "Passed · 3 of 3 tests" without fetching every submission's results
        from django.db.models import Count, Q
        qs = qs.annotate(
            tests_total=Count('results'),
            tests_passed=Count('results', filter=Q(results__passed=True)),
        ).order_by('-submitted_at')

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = SubmissionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

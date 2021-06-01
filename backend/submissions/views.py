from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle
from rest_framework.pagination import PageNumberPagination
from .models import Submission
from .serializers import SubmissionSerializer, SubmissionCreateSerializer
from exams.models import Question
from execution.tasks import execute_submission
from plagiarism.models import PlagiarismPolicy


class SubmissionThrottle(UserRateThrottle):
    scope = 'submissions'  # maps to DEFAULT_THROTTLE_RATES['submissions'] = 30/hour


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

        serializer = SubmissionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        max_attempts = PlagiarismPolicy.get().max_attempts
        attempt_number = Submission.objects.filter(
            student=request.user, question=question
        ).count() + 1

        if attempt_number > max_attempts:
            return Response({'error': 'Max attempts reached'}, status=status.HTTP_403_FORBIDDEN)

        submission = serializer.save(
            student=request.user,
            exam=question.exam,
            attempt_number=attempt_number,
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        execute_submission.delay(submission.id)

        return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)


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

        qs = qs.order_by('-submitted_at')

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = SubmissionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

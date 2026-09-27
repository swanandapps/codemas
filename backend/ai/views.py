from rest_framework import status  # HTTP status codes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from submissions.models import Submission
from plagiarism.models import PlagiarismFlag
from .models import RubricScore, AIHint, PlagiarismExplanation
from .serializers import (
    RubricScoreSerializer, AIHintSerializer, PlagiarismExplanationSerializer,
)


class RubricScoreView(APIView):
    """GET /api/ai/rubric/{submission_id}/

    The frontend polls this after the test result is shown. While the async
    scoring task is still running it returns {"status": "pending"}; once stored
    it returns the full rubric. Same ownership rules as the rest of the app:
    students see only their own, trainers see all.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        submission = Submission.objects.filter(pk=submission_id).select_related('student').first()
        if not submission:
            return Response({'error': 'Submission not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role != 'trainer' and submission.student != request.user:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)

        rubric = RubricScore.objects.filter(submission=submission).first()
        if not rubric:
            # Not scored yet (or unavailable) — tell the client to keep waiting.
            return Response({'status': 'pending'})

        return Response(RubricScoreSerializer(rubric).data)


class AIHintView(APIView):
    """GET /api/ai/hint/<submission_id>/

    Polled by the frontend after a FAILED result. Returns {"status": "pending"}
    until the async hint is stored, then the hint. Same ownership rules.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        submission = Submission.objects.filter(pk=submission_id).select_related('student').first()
        if not submission:
            return Response({'error': 'Submission not found'}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role != 'trainer' and submission.student != request.user:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)

        hint = AIHint.objects.filter(submission=submission).first()
        if not hint:
            return Response({'status': 'pending'})

        return Response(AIHintSerializer(hint).data)


class PlagiarismExplanationView(APIView):
    """GET /api/ai/plagiarism-explanation/<flag_id>/

    Trainer-only. Returns the GPT explanation for a flagged pair, or
    {"status": "pending"} while the async task is still running.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, flag_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)

        flag = PlagiarismFlag.objects.filter(pk=flag_id).first()
        if not flag:
            return Response({'error': 'Flag not found'}, status=status.HTTP_404_NOT_FOUND)

        explanation = PlagiarismExplanation.objects.filter(flag=flag).first()
        if not explanation:
            return Response({'status': 'pending'})

        return Response(PlagiarismExplanationSerializer(explanation).data)


class ExamSummaryView(APIView):
    """GET /api/ai/exam-summary/<exam_id>/

    Returns the requesting student's AI summary for an exam, generating it on
    first request (synchronous, then cached). Trainers may pass ?student=<id>
    to view a specific student's summary.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        student_id = request.user.id
        if request.user.role == 'trainer':
            student_id = request.query_params.get('student', request.user.id)

        from .tasks import generate_exam_summary
        summary = generate_exam_summary(student_id, exam_id)
        if not summary:
            return Response({'status': 'unavailable'})

        return Response({
            'exam_id': int(exam_id),
            'summary': summary.summary,
            'model_used': summary.model_used,
            'created_at': summary.created_at,
        })


class GenerateExamView(APIView):
    """POST /api/ai/generate-exam/  (trainer-only)

    Generates a DRAFT exam (questions + test cases) via GPT and returns it
    WITHOUT persisting. The trainer reviews/edits, then saves via
    /api/exams/create-full/ — that review step is the human-in-the-loop QA.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can generate exams'}, status=status.HTTP_403_FORBIDDEN)

        topic = (request.data.get('topic') or '').strip()
        if not topic:
            return Response({'error': 'topic is required'}, status=status.HTTP_400_BAD_REQUEST)
        language = request.data.get('language', 'python')
        num_questions = request.data.get('num_questions', 3)
        difficulty = request.data.get('difficulty', 'medium')

        from .tasks import generate_exam_draft
        from .llm import LLMUnavailable
        try:
            draft = generate_exam_draft(topic, language, num_questions, difficulty)
        except LLMUnavailable as e:
            return Response({'error': f'AI generation unavailable: {e}'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(draft)

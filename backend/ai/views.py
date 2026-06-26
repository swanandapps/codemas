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

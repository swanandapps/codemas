from rest_framework import status  # HTTP status codes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from submissions.models import Submission
from .models import RubricScore
from .serializers import RubricScoreSerializer


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

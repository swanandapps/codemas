from rest_framework import status  # HTTP status codes
from rest_framework.response import Response  # JSON response wrapper
from rest_framework.views import APIView  # base class for API views
from rest_framework.permissions import IsAuthenticated  # requires valid JWT token
from .models import Result  # Result model
from .serializers import ResultSerializer  # our serializer
from submissions.models import Submission  # to look up the submission


class SubmissionResultsView(APIView):
    permission_classes = [IsAuthenticated]  # must be logged in

    def get(self, request, submission_id):  # GET /api/results/{submission_id}/
        submission = Submission.objects.filter(pk=submission_id).first()  # find the submission
        if not submission:
            return Response({'error': 'Submission not found'}, status=status.HTTP_404_NOT_FOUND)

        # students can only see their own results, trainers can see all
        if request.user.role != 'trainer' and submission.student != request.user:
            return Response({'error': 'Not allowed'}, status=status.HTTP_403_FORBIDDEN)

        results = Result.objects.filter(submission=submission)  # all test case results for this submission
        serializer = ResultSerializer(results, many=True)
        return Response(serializer.data)

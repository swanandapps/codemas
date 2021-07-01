from django.urls import path  # URL routing
from .views import SubmissionResultsView  # our view

urlpatterns = [
    path('<int:submission_id>/', SubmissionResultsView.as_view()),  # GET /api/results/{submission_id}/
]

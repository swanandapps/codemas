from django.urls import path
from .views import (
    RubricScoreView, AIHintView, PlagiarismExplanationView, ExamSummaryView,
    GenerateExamView,
)

urlpatterns = [
    path('rubric/<int:submission_id>/', RubricScoreView.as_view()),  # GET rubric for a submission
    path('hint/<int:submission_id>/', AIHintView.as_view()),         # GET Socratic hint for a failed submission
    path('plagiarism-explanation/<int:flag_id>/', PlagiarismExplanationView.as_view()),  # GET explanation for a flagged pair
    path('exam-summary/<int:exam_id>/', ExamSummaryView.as_view()),  # GET AI summary of a student's exam performance
    path('generate-exam/', GenerateExamView.as_view()),              # POST generate a draft exam (trainer)
]

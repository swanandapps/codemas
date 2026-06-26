from django.urls import path
from .views import RubricScoreView, AIHintView, PlagiarismExplanationView

urlpatterns = [
    path('rubric/<int:submission_id>/', RubricScoreView.as_view()),  # GET rubric for a submission
    path('hint/<int:submission_id>/', AIHintView.as_view()),         # GET Socratic hint for a failed submission
    path('plagiarism-explanation/<int:flag_id>/', PlagiarismExplanationView.as_view()),  # GET explanation for a flagged pair
]

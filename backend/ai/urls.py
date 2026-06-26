from django.urls import path
from .views import RubricScoreView, AIHintView

urlpatterns = [
    path('rubric/<int:submission_id>/', RubricScoreView.as_view()),  # GET rubric for a submission
    path('hint/<int:submission_id>/', AIHintView.as_view()),         # GET Socratic hint for a failed submission
]

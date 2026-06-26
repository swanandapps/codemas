from django.urls import path
from .views import RubricScoreView

urlpatterns = [
    path('rubric/<int:submission_id>/', RubricScoreView.as_view()),  # GET rubric for a submission
]

from django.urls import path
from .views import LeaderboardView, MyStatsView, MyExamStatsView

urlpatterns = [
    path('', LeaderboardView.as_view()),
    path('me/', MyStatsView.as_view()),
    path('me/exams/', MyExamStatsView.as_view()),
]

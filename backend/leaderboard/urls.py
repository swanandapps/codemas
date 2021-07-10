from django.urls import path
from .views import LeaderboardView, MyStatsView

urlpatterns = [
    path('', LeaderboardView.as_view()),
    path('me/', MyStatsView.as_view()),
]

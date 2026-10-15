from django.urls import path
from .views import SubmissionCreateView, SubmissionListView, SubmissionDetailView, SubmissionStatusView

urlpatterns = [
    path('', SubmissionListView.as_view()),
    path('create/', SubmissionCreateView.as_view()),
    path('<int:pk>/', SubmissionDetailView.as_view()),
    path('<int:pk>/status/', SubmissionStatusView.as_view()),
]
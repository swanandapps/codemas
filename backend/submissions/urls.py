from django.urls import path
from .views import SubmissionCreateView, SubmissionListView, SubmissionDetailView
from .sse import submission_stream

urlpatterns = [
    path('', SubmissionListView.as_view()),
    path('create/', SubmissionCreateView.as_view()),
    path('<int:pk>/', SubmissionDetailView.as_view()),
    path('<int:submission_id>/stream/', submission_stream),
]
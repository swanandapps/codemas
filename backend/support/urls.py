from django.urls import path
from .views import (
    StudentCaseView, DisputeListView, MyDisputesView, DisputeDetailView, ExamOpsView,
    AttentionView, AttentionSeenView,
)

urlpatterns = [
    path('student/<int:student_id>/', StudentCaseView.as_view()),
    path('disputes/',                 DisputeListView.as_view()),
    path('disputes/mine/',            MyDisputesView.as_view()),   # student: their own appeals
    path('disputes/<int:pk>/',        DisputeDetailView.as_view()),
    path('attention/',                AttentionView.as_view()),    # badge counts
    path('attention/seen/',           AttentionSeenView.as_view()),
    path('exam/<int:exam_id>/ops/',   ExamOpsView.as_view()),
]

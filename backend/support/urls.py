from django.urls import path
from .views import StudentCaseView, DisputeListView, DisputeDetailView, ExamOpsView

urlpatterns = [
    path('student/<int:student_id>/', StudentCaseView.as_view()),
    path('disputes/',                 DisputeListView.as_view()),
    path('disputes/<int:pk>/',        DisputeDetailView.as_view()),
    path('exam/<int:exam_id>/ops/',   ExamOpsView.as_view()),
]

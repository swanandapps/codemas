from django.urls import path
from .views import DashboardView, StudentsListView, StudentDetailView, ExamHistoryView, ExamDetailView, CostAnalysisView

urlpatterns = [
    path('', DashboardView.as_view()),
    path('students/', StudentsListView.as_view()),
    path('students/<int:student_id>/', StudentDetailView.as_view()),
    path('exams/', ExamHistoryView.as_view()),
    path('exams/<int:exam_id>/', ExamDetailView.as_view()),
    path('costs/', CostAnalysisView.as_view()),
]

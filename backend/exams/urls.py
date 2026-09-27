from django.urls import path
from .views import ExamListCreateView, ExamFullCreateView, ExamDetailView, QuestionListCreateView, TestCaseCreateView, ExamExportView, EnrollmentView

urlpatterns = [
    path('', ExamListCreateView.as_view()),
    path('create-full/', ExamFullCreateView.as_view()),  # create exam + questions + test cases atomically
    path('<int:pk>/', ExamDetailView.as_view()),
    path('<int:pk>/export/', ExamExportView.as_view()),
    path('<int:pk>/enrollments/', EnrollmentView.as_view()),
    path('<int:exam_pk>/questions/', QuestionListCreateView.as_view()),
    path('<int:exam_pk>/questions/<int:question_pk>/testcases/', TestCaseCreateView.as_view()),
]

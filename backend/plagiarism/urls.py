from django.urls import path
from .views import (
    PlagiarismFlagListView, PlagiarismFlagReviewView,
    BehaviouralFlagListView, BehaviouralFlagReviewView,
    PolicyView, PolicyChangelogView, AuditLogView, CodeSimilaritySearchView,
    SubmissionPlagiarismView, MonitoringView,
    CohortListView, CohortDetailView, RerunExamChecksView, PlagiarismRunListView,
)

urlpatterns = [
    path('', PlagiarismFlagListView.as_view()),
    path('<int:pk>/review/', PlagiarismFlagReviewView.as_view()),
    path('behavioural/', BehaviouralFlagListView.as_view()),
    path('behavioural/<int:pk>/review/', BehaviouralFlagReviewView.as_view()),
    path('policy/', PolicyView.as_view()),
    path('policy/changelog/', PolicyChangelogView.as_view()),
    path('audit/', AuditLogView.as_view()),
    path('search/', CodeSimilaritySearchView.as_view()),
    path('submission/<int:submission_id>/', SubmissionPlagiarismView.as_view()),
    path('monitoring/', MonitoringView.as_view()),
    path('cohorts/', CohortListView.as_view()),
    path('cohorts/<int:exam_id>/', CohortDetailView.as_view()),
    path('cohorts/<int:exam_id>/rerun/', RerunExamChecksView.as_view()),
    path('runs/', PlagiarismRunListView.as_view()),
]

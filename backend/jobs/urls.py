from django.urls import path

from .views import ClaimView, CompleteView, FailView

urlpatterns = [
    path('claim/', ClaimView.as_view()),
    path('complete/', CompleteView.as_view()),
    path('fail/', FailView.as_view()),
]

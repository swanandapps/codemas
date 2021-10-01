from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, LoginView, StudentManagementView, StudentDetailManagementView

urlpatterns = [
    path('register/', RegisterView.as_view()),
    path('login/', LoginView.as_view()),
    path('refresh/', TokenRefreshView.as_view()),
    path('students/', StudentManagementView.as_view()),
    path('students/<int:pk>/', StudentDetailManagementView.as_view()),
]

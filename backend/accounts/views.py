from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .serializers import RegisterSerializer, UserSerializer
from .models import User


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        if user:
            refresh = RefreshToken.for_user(user)
            return Response({
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data
            })
        return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)


class StudentManagementView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        students = User.objects.filter(role='student').order_by('username')
        return Response(UserSerializer(students, many=True).data)

    def post(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        data = {**request.data, 'role': 'student'}
        serializer = RegisterSerializer(data=data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentDetailManagementView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        student = User.objects.filter(pk=pk, role='student').first()
        if not student:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
        cohort = request.data.get('cohort')
        if cohort is not None:
            student.cohort = cohort
            student.save(update_fields=['cohort'])
        return Response(UserSerializer(student).data)

    def delete(self, request, pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        student = User.objects.filter(pk=pk, role='student').first()
        if not student:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)
        student.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

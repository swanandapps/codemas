import csv
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import Exam, Question, TestCase, ExamEnrollment
from .serializers import ExamSerializer, ExamCreateSerializer, QuestionSerializer, TestCaseSerializer


class ExamListCreateView(APIView):
    permission_classes = [IsAuthenticated]  # must be logged in to access

    def get(self, request):
        if request.user.role == 'trainer':
            exams = Exam.objects.filter(created_by=request.user)
        else:
            exams = Exam.objects.filter(is_active=True)
        serializer = ExamSerializer(exams, many=True)
        return Response(serializer.data)

    def post(self, request):  # POST /api/exams/ — create new exam
        if request.user.role != 'trainer':  # only trainers can create exams
            return Response({'error': 'Only trainers can create exams'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExamCreateSerializer(data=request.data)  # validate incoming data
        if serializer.is_valid():
            serializer.save(created_by=request.user)  # set created_by from logged in user, not from request
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ExamFullCreateView(APIView):
    """POST /api/exams/create-full/ — create an exam with questions AND test cases
    in one atomic call. Used to persist an (AI-generated, trainer-reviewed) draft.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can create exams'}, status=status.HTTP_403_FORBIDDEN)

        from django.db import transaction
        d = request.data
        title = (d.get('title') or '').strip()
        if not title:
            return Response({'error': 'title is required'}, status=status.HTTP_400_BAD_REQUEST)
        default_language = d.get('language', 'python')

        try:
            with transaction.atomic():
                exam = Exam.objects.create(
                    title=title[:200],
                    description=d.get('description', '') or '',
                    duration_minutes=int(d.get('duration_minutes', 60)),
                    created_by=request.user,
                )
                for q in d.get('questions', []):
                    question = Question.objects.create(
                        exam=exam,
                        title=str(q.get('title', 'Untitled'))[:300],
                        description=q.get('description', '') or '',
                        language=q.get('language', default_language),
                        difficulty=q.get('difficulty', 'medium'),
                        max_attempts=int(q.get('max_attempts', 3)),
                        tags=q.get('tags', '') or '',
                    )
                    for tc in q.get('test_cases', []):
                        TestCase.objects.create(
                            question=question,
                            input_data=str(tc.get('input_data', '')),
                            expected_output=str(tc.get('expected_output', '')),
                            is_hidden=tc.get('is_hidden', True),
                        )
        except (ValueError, TypeError) as e:
            return Response({'error': f'Invalid payload: {e}'}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'id': exam.id, 'title': exam.title, 'questions': exam.questions.count()},
                        status=status.HTTP_201_CREATED)


class ExamDetailView(APIView):
    permission_classes = [IsAuthenticated]  # must be logged in

    def get_object(self, pk):  # helper method — fetch exam or return None
        try:
            return Exam.objects.get(pk=pk)
        except Exam.DoesNotExist:
            return None

    def get(self, request, pk):  # GET /api/exams/{id}/ — get one exam with questions
        exam = self.get_object(pk)
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ExamSerializer(exam)  # single object, no many=True
        return Response(serializer.data)

    def put(self, request, pk):  # PUT /api/exams/{id}/ — update exam
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can update exams'}, status=status.HTTP_403_FORBIDDEN)
        exam = self.get_object(pk)
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ExamCreateSerializer(exam, data=request.data)  # pass existing instance for update
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):  # PATCH /api/exams/{id}/ — partial update (e.g. close exam)
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can update exams'}, status=status.HTTP_403_FORBIDDEN)
        exam = self.get_object(pk)
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ExamCreateSerializer(exam, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):  # DELETE /api/exams/{id}/ — delete exam
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can delete exams'}, status=status.HTTP_403_FORBIDDEN)
        exam = self.get_object(pk)
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        exam.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)  # 204 = success but no content to return


class QuestionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_pk):  # GET /api/exams/{exam_id}/questions/
        exam = Exam.objects.filter(pk=exam_pk).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        questions = Question.objects.filter(exam=exam)  # only questions belonging to this exam
        serializer = QuestionSerializer(questions, many=True)
        return Response(serializer.data)

    def post(self, request, exam_pk):  # POST /api/exams/{exam_id}/questions/
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can add questions'}, status=status.HTTP_403_FORBIDDEN)
        exam = Exam.objects.filter(pk=exam_pk).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = QuestionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(exam=exam)  # set exam from URL, not from request body
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class ExamExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can export results'}, status=status.HTTP_403_FORBIDDEN)

        exam = Exam.objects.filter(pk=pk).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        from submissions.models import Submission

        submissions = (
            Submission.objects
            .filter(exam=exam)
            .select_related('student', 'question')
            .order_by('student__username', 'question__id', 'attempt_number')
        )

        def rows():
            yield ['student', 'question', 'difficulty', 'attempt', 'status',
                   'language', 'time_to_complete_s', 'had_paste', 'paste_chars',
                   'tab_switches', 'submitted_at']
            for s in submissions:
                yield [
                    s.student.username,
                    s.question.title,
                    s.question.difficulty,
                    s.attempt_number,
                    s.status,
                    s.language,
                    s.time_to_complete_seconds,
                    s.had_paste_event,
                    s.paste_char_count,
                    s.tab_switch_count,
                    s.submitted_at.strftime('%Y-%m-%d %H:%M:%S'),
                ]

        def stream():
            for row in rows():
                yield ','.join(str(c) for c in row) + '\n'

        response = StreamingHttpResponse(stream(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="exam_{pk}_results.csv"'
        return response


class TestCaseCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_pk, question_pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can add test cases'}, status=status.HTTP_403_FORBIDDEN)

        question = Question.objects.filter(pk=question_pk, exam__pk=exam_pk).first()
        if not question:
            return Response({'error': 'Question not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = TestCaseSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(question=question)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EnrollmentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        """GET /api/exams/{id}/enrollments/ — trainer sees who is enrolled"""
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view enrollments'}, status=status.HTTP_403_FORBIDDEN)
        exam = Exam.objects.filter(pk=pk).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        enrollments = ExamEnrollment.objects.filter(exam=exam).select_related('student')
        data = [{'student_id': e.student.id, 'username': e.student.username, 'enrolled_at': e.enrolled_at} for e in enrollments]
        return Response(data)

    def post(self, request, pk):
        """POST /api/exams/{id}/enrollments/ — trainer enrolls a student by username"""
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can enroll students'}, status=status.HTTP_403_FORBIDDEN)
        exam = Exam.objects.filter(pk=pk).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        from django.contrib.auth import get_user_model
        User = get_user_model()
        username = request.data.get('username')
        student = User.objects.filter(username=username, role='student').first()
        if not student:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

        _, created = ExamEnrollment.objects.get_or_create(exam=exam, student=student)
        if not created:
            return Response({'error': 'Already enrolled'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'enrolled': username}, status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        """DELETE /api/exams/{id}/enrollments/ — trainer removes a student"""
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can remove enrollments'}, status=status.HTTP_403_FORBIDDEN)
        exam = Exam.objects.filter(pk=pk).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        username = request.data.get('username')
        deleted, _ = ExamEnrollment.objects.filter(exam=exam, student__username=username).delete()
        if not deleted:
            return Response({'error': 'Enrollment not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
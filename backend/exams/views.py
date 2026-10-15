import csv
from django.http import StreamingHttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from .models import Exam, Question, TestCase, ExamEnrollment, newest_exam_first
from .serializers import ExamSerializer, ExamCreateSerializer, QuestionSerializer, TestCaseSerializer, sees_hidden_tests


def hidden_from(user, exam):
    """True when a student isn't enrolled in the exam: they get a 404 so we don't confirm it exists."""
    return user.role == 'student' and not ExamEnrollment.objects.filter(exam=exam, student=user).exists()


class ExamListCreateView(APIView):
    permission_classes = [IsAuthenticated]  # must be logged in to access

    def get(self, request):
        if request.user.role == 'trainer':
            exams = Exam.objects.filter(created_by=request.user)
        elif request.user.role == 'student':  # only live exams they are enrolled in
            exams = Exam.objects.filter(is_active=True, enrollments__student=request.user)
        else:
            exams = Exam.objects.filter(is_active=True)
        exams = exams.order_by(newest_exam_first(), '-id')
        serializer = ExamSerializer(exams, many=True, context={'show_hidden': sees_hidden_tests(request.user)})
        data = serializer.data
        if request.user.role == 'student':  # mark the exams this student has already ended
            finished = dict(ExamEnrollment.objects.filter(student=request.user, finished_at__isnull=False)
                            .values_list('exam_id', 'finished_at'))
            for row in data:
                row['finished_at'] = finished.get(row['id'])
        return Response(data)

    def post(self, request):  # POST /api/exams/ — create new exam
        if request.user.role != 'trainer':  # only trainers can create exams
            return Response({'error': 'Only trainers can create exams'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ExamCreateSerializer(data=request.data)  # validate incoming data
        if serializer.is_valid():
            exam = serializer.save(created_by=request.user)  # set created_by from logged in user, not from request
            if exam.is_active:
                exam.enroll_audience()  # created live: the signal only sees draft → live
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
        default_language = d.get('language', 'javascript')

        try:
            with transaction.atomic():
                exam = Exam.objects.create(
                    title=title[:200],
                    description=d.get('description', '') or '',
                    duration_minutes=int(d.get('duration_minutes', 60)),
                    sections=[str(s) for s in (d.get('sections') or [])],
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
                        starter_code_javascript=str((q.get('starter_code') or {}).get('javascript') or ''),
                        starter_code_python=str((q.get('starter_code') or {}).get('python') or ''),
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
        if not exam or hidden_from(request.user, exam):
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ExamSerializer(exam, context={'show_hidden': sees_hidden_tests(request.user)})  # hidden tests redacted for students
        data = serializer.data
        if request.user.role == 'student':
            data['finished_at'] = (ExamEnrollment.objects.filter(exam=exam, student=request.user)
                                   .values_list('finished_at', flat=True).first())
        return Response(data)

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
            # Keep the schedule consistent with a manual open/close, or the scheduler undoes it:
            # closing early ends the window now; opening after the window cleared its stale end.
            extra = {}
            now = timezone.now()
            if 'is_active' in serializer.validated_data and 'end_time' not in serializer.validated_data:
                if not serializer.validated_data['is_active'] and (not exam.end_time or exam.end_time > now):
                    extra['end_time'] = now
                if serializer.validated_data['is_active'] and exam.end_time and exam.end_time <= now:
                    extra['end_time'] = None
            serializer.save(**extra)
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


class ExamFinishView(APIView):
    """POST /api/exams/{id}/finish/ — the student submits the exam early (Submit exam).

    After this, the student can't submit to the exam again; their results stay.
    Idempotent: ending twice keeps the first time. When the last enrolled student
    finishes, the exam closes now instead of waiting for end_time — nobody is left
    to submit, and closing is what starts the plagiarism checks.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != 'student':
            return Response({'error': 'Only students end exams'}, status=status.HTTP_403_FORBIDDEN)
        enrollment = ExamEnrollment.objects.filter(exam_id=pk, student=request.user).select_related('exam').first()
        if not enrollment:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        if not enrollment.finished_at:
            enrollment.finished_at = timezone.now()
            enrollment.save(update_fields=['finished_at'])
            exam = enrollment.exam
            if exam.is_active and not exam.enrollments.filter(finished_at__isnull=True).exists():
                exam.is_active = False  # pre_save signal queues the plagiarism checks
                if not exam.end_time or exam.end_time > enrollment.finished_at:
                    exam.end_time = enrollment.finished_at  # or the scheduler re-opens it
                exam.save()
        return Response({'exam_id': int(pk), 'finished_at': enrollment.finished_at})


class QuestionListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_pk):  # GET /api/exams/{exam_id}/questions/
        exam = Exam.objects.filter(pk=exam_pk).first()
        if not exam or hidden_from(request.user, exam):
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        questions = Question.objects.filter(exam=exam)  # only questions belonging to this exam
        serializer = QuestionSerializer(questions, many=True, context={'show_hidden': sees_hidden_tests(request.user)})
        return Response(serializer.data)

    def post(self, request, exam_pk):  # POST /api/exams/{exam_id}/questions/
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can add questions'}, status=status.HTTP_403_FORBIDDEN)
        exam = Exam.objects.filter(pk=exam_pk).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        serializer = QuestionSerializer(data=request.data, context={'show_hidden': True})  # trainer-only path
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

        serializer = TestCaseSerializer(data=request.data, context={'show_hidden': True})  # trainer-only path
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

class SectionListView(APIView):
    """GET /api/exams/sections/ — the cohort's sections with student counts, for picking an exam's audience."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view sections'}, status=status.HTTP_403_FORBIDDEN)
        from django.contrib.auth import get_user_model
        from django.db.models import Count
        rows = (get_user_model().objects.filter(role='student').exclude(cohort='')
                .values('cohort').annotate(students=Count('id')).order_by('cohort'))
        return Response([{'name': r['cohort'], 'students': r['students']} for r in rows])

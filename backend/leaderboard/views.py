from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Avg, Count
from django.utils import timezone
from datetime import timedelta
from accounts.models import User
from submissions.models import Submission
from exams.models import Question


class LeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cohort_filter = request.query_params.get('cohort', '')
        students = User.objects.filter(role='student')
        if cohort_filter:
            students = students.filter(cohort=cohort_filter)

        board = []
        for student in students:
            subs = Submission.objects.filter(student=student)
            total = subs.count()
            passed = subs.filter(status='passed').count()
            pass_rate = round(passed / total * 100, 1) if total else 0
            avg_exec = subs.filter(execution_time_ms__isnull=False).aggregate(a=Avg('execution_time_ms'))['a']
            board.append({
                'student_id': student.id,
                'username': student.username,
                'cohort': student.cohort or '',
                'score': student.score,
                'streak': student.current_streak,
                'total_submissions': total,
                'pass_rate': pass_rate,
                'avg_execution_time': round(avg_exec, 0) if avg_exec else None,
            })

        board.sort(key=lambda x: (-x['score'], -x['pass_rate']))
        for i, entry in enumerate(board):
            entry['rank'] = i + 1

        cohorts = list(User.objects.filter(role='student').values_list('cohort', flat=True).distinct())
        return Response({
            'leaderboard': board,
            'cohorts': [c for c in cohorts if c],
        })


class MyStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        subs = Submission.objects.filter(student=user)
        total = subs.count()
        passed = subs.filter(status='passed').count()

        # activity calendar — last 52 weeks
        since = timezone.now() - timedelta(weeks=52)
        activity = (
            subs.filter(submitted_at__gte=since)
            .values('submitted_at__date')
            .annotate(count=Count('id'))
            .order_by('submitted_at__date')
        )
        activity_map = {str(r['submitted_at__date']): r['count'] for r in activity}

        # beats X% — compare exec time vs cohort
        cohort_students = User.objects.filter(role='student', cohort=user.cohort).exclude(id=user.id)
        my_avg = subs.filter(execution_time_ms__isnull=False).aggregate(a=Avg('execution_time_ms'))['a']
        beats_pct = None
        if my_avg:
            cohort_execs = list(
                Submission.objects.filter(student__in=cohort_students, execution_time_ms__isnull=False)
                .values_list('execution_time_ms', flat=True)
            )
            if cohort_execs:
                slower_count = sum(1 for t in cohort_execs if t > my_avg)
                beats_pct = round(slower_count / len(cohort_execs) * 100, 1)

        # rank in cohort
        all_students = User.objects.filter(role='student', cohort=user.cohort)
        scores = sorted([(s.id, s.score) for s in all_students], key=lambda x: -x[1])
        rank = next((i + 1 for i, (sid, _) in enumerate(scores) if sid == user.id), None)

        # solved by difficulty
        solved_ids = subs.filter(status='passed').values_list('question_id', flat=True).distinct()
        difficulty_breakdown = {
            'easy': Question.objects.filter(id__in=solved_ids, difficulty='easy').count(),
            'medium': Question.objects.filter(id__in=solved_ids, difficulty='medium').count(),
            'hard': Question.objects.filter(id__in=solved_ids, difficulty='hard').count(),
        }

        return Response({
            'score': user.score,
            'streak': user.current_streak,
            'rank': rank,
            'cohort_size': len(scores),
            'total_submissions': total,
            'passed': passed,
            'pass_rate': round(passed / total * 100, 1) if total else 0,
            'beats_pct': beats_pct,
            'avg_execution_time': round(my_avg, 0) if my_avg else None,
            'activity_calendar': activity_map,
            'difficulty_breakdown': difficulty_breakdown,
        })

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from analytics import metrics
from submissions.models import Submission


class LeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cohort_filter = request.query_params.get('cohort', '')
        students = metrics.students()
        if cohort_filter:
            students = students.filter(cohort=cohort_filter)

        subs = Submission.objects.filter(student__in=students)
        accepted = metrics.success_by(subs, 'student_id')   # exams passed / exams taken
        points = metrics.points_by_student(subs)
        totals = {r['student_id']: r['total'] for r in subs.order_by().values('student_id').annotate(total=Count('id'))}

        board = []
        for student in students:
            board.append({
                'student_id': student.id,
                'username': student.username,
                'cohort': student.cohort or '',
                'score': points.get(student.id, 0),
                'streak': student.current_streak,
                'total_submissions': totals.get(student.id, 0),
                'accepted_rate': accepted.get(student.id, {}).get('accepted_rate'),
            })

        # Rank by score, then faster average solve (same rule as My results); the order follows the rank
        scores = {e['student_id']: e['score'] for e in board}
        times = metrics.solve_times(subs)
        for entry in board:
            entry['rank'] = metrics.competition_rank(scores, entry['student_id'], times)['rank']
        board.sort(key=lambda x: (x['rank'], x['username']))

        cohorts = list(metrics.students().values_list('cohort', flat=True).distinct())
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
        overall = metrics.success(subs)   # exams passed / exams taken

        # activity calendar — last 52 weeks
        since = timezone.now() - timedelta(weeks=52)
        activity = (
            subs.filter(submitted_at__gte=since)
            .values('submitted_at__date')
            .annotate(count=Count('id'))
            .order_by('submitted_at__date')
        )
        activity_map = {str(r['submitted_at__date']): r['count'] for r in activity}

        # Score and tie-aware cohort rank, from the same points the leaderboard uses
        scores = metrics.cohort_scores(user.cohort)
        standing = metrics.competition_rank(scores, user.id, metrics.solve_times(Submission.objects.filter(student__cohort=user.cohort)))
        overall_standing = metrics.competition_rank(  # all batches, as the leaderboard's All view
            metrics.all_scores(), user.id, metrics.solve_times(Submission.objects.all()))
        my_score = scores.get(user.id, metrics.points_by_student(subs).get(user.id, 0))

        return Response({
            'score': my_score,
            'score_available': metrics.score_available(user),
            'points_withheld': metrics.points_withheld_by_student(subs).get(user.id, 0),   # lost to confirmed plagiarism
            'streak': user.current_streak,
            'cohort': user.cohort,   # the student's section, e.g. "Section A"
            'rank': standing['rank'],
            'ahead_of': standing['ahead_of'],
            'cohort_size': standing['size'],
            'overall_rank': overall_standing['rank'],
            'overall_size': overall_standing['size'],
            'total_submissions': total,
            'exams_passed': overall['passed'],
            'exams_taken': overall['taken'],
            'accepted_rate': overall['accepted_rate'],   # shown as "Success rate"
            'activity_calendar': activity_map,
            'difficulty_progress': metrics.difficulty_progress(user),
        })




class MyExamStatsView(APIView):
    """GET /api/leaderboard/me/exams/

    Per-exam metrics for the requesting student, plus their rank within their
    cohort for each exam (ranked by points earned in that exam) and every
    question in the exam with their attempt count and outcome. Newest first.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .exam_stats import student_exam_stats
        return Response(student_exam_stats(request.user))

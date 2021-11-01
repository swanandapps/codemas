from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Count, Avg, Q, FloatField, ExpressionWrapper, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from accounts.models import User
from submissions.models import Submission
from plagiarism.models import PlagiarismFlag, BehaviouralFlag
from exams.models import Question, Exam, ExamEnrollment


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view dashboard'}, status=status.HTTP_403_FORBIDDEN)

        # --- KPI cards ---
        total_students = User.objects.filter(role='student').count()
        total_submissions = Submission.objects.count()
        passed = Submission.objects.filter(status='passed').count()
        pass_rate = round((passed / total_submissions * 100), 1) if total_submissions else 0
        plagiarism_flags = PlagiarismFlag.objects.filter(flagged=True, review_status='pending').count()

        # --- Submissions timeline — last 14 days ---
        since = timezone.now() - timedelta(days=13)
        timeline_qs = (
            Submission.objects
            .filter(submitted_at__gte=since)
            .annotate(day=TruncDate('submitted_at'))
            .values('day')
            .annotate(total=Count('id'), passed=Count('id', filter=Q(status='passed')))
            .order_by('day')
        )
        # fill in missing days with 0
        date_map = {str(r['day']): {'total': r['total'], 'passed': r['passed']} for r in timeline_qs}
        timeline = []
        for i in range(14):
            day = str((timezone.now() - timedelta(days=13 - i)).date())
            timeline.append({'date': day, **date_map.get(day, {'total': 0, 'passed': 0})})

        # --- Pass rate by question ---
        question_stats = []
        for q in Question.objects.all():
            subs = Submission.objects.filter(question=q)
            total = subs.count()
            p = subs.filter(status='passed').count()
            avg_exec = subs.filter(execution_time_ms__isnull=False).aggregate(a=Avg('execution_time_ms'))['a']
            avg_attempts = subs.values('student').annotate(c=Count('id')).aggregate(a=Avg('c'))['a']
            question_stats.append({
                'question_id': q.id,
                'question_title': q.title,
                'total_attempts': total,
                'pass_rate': round(p / total * 100, 1) if total else 0,
                'avg_execution_time': round(avg_exec, 0) if avg_exec else 0,
                'avg_attempts_to_pass': round(avg_attempts, 1) if avg_attempts else 0,
            })

        # --- Language distribution ---
        lang_qs = Submission.objects.values('language').annotate(count=Count('id'))
        language_distribution = {r['language']: r['count'] for r in lang_qs}

        # --- Cohort comparison ---
        cohorts = User.objects.filter(role='student').values_list('cohort', flat=True).distinct()
        cohort_comparison = []
        for cohort in cohorts:
            if not cohort:
                continue
            students = User.objects.filter(role='student', cohort=cohort)
            c_subs = Submission.objects.filter(student__in=students)
            c_total = c_subs.count()
            c_passed = c_subs.filter(status='passed').count()
            cohort_comparison.append({
                'cohort': cohort,
                'student_count': students.count(),
                'total_submissions': c_total,
                'pass_rate': round(c_passed / c_total * 100, 1) if c_total else 0,
            })

        # --- Top performers ---
        student_stats = []
        for student in User.objects.filter(role='student'):
            subs = Submission.objects.filter(student=student)
            total = subs.count()
            if total == 0:
                continue
            p = subs.filter(status='passed').count()
            avg_exec = subs.filter(execution_time_ms__isnull=False).aggregate(a=Avg('execution_time_ms'))['a']
            flags = PlagiarismFlag.objects.filter(
                Q(submission_1__student=student) | Q(submission_2__student=student), flagged=True
            ).count()
            student_stats.append({
                'student_id': student.id,
                'username': student.username,
                'cohort': student.cohort,
                'total_submissions': total,
                'pass_rate': round(p / total * 100, 1),
                'avg_execution_time': round(avg_exec, 0) if avg_exec else None,
                'plagiarism_flags': flags,
            })

        student_stats.sort(key=lambda x: x['pass_rate'], reverse=True)
        top_performers = student_stats[:5]
        struggling = [s for s in student_stats if s['pass_rate'] < 40][:5]

        return Response({
            'kpis': {
                'total_students': total_students,
                'total_submissions': total_submissions,
                'pass_rate': pass_rate,
                'plagiarism_flags': plagiarism_flags,
            },
            'timeline': timeline,
            'question_stats': question_stats,
            'language_distribution': language_distribution,
            'cohort_comparison': cohort_comparison,
            'top_performers': top_performers,
            'struggling_students': struggling,
        })


class StudentsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers'}, status=status.HTTP_403_FORBIDDEN)

        students = []
        for student in User.objects.filter(role='student').order_by('username'):
            subs = Submission.objects.filter(student=student)
            total = subs.count()
            passed = subs.filter(status='passed').count()
            b_flags = BehaviouralFlag.objects.filter(submission__student=student)
            if b_flags.filter(confidence='low').exists():
                max_conf = 'low'      # low = most suspicious (3+ signals)
            elif b_flags.filter(confidence='medium').exists():
                max_conf = 'medium'
            elif b_flags.filter(confidence='high').exists():
                max_conf = 'high'    # high = least suspicious (1 signal)
            else:
                max_conf = None
            top_risk = b_flags.order_by('-risk_score').values_list('risk_score', flat=True).first()
            students.append({
                'student_id': student.id,
                'username': student.username,
                'cohort': student.cohort or '',
                'total_submissions': total,
                'pass_rate': round(passed / total * 100, 1) if total else 0,
                'max_confidence': max_conf,
                'max_risk_score': round(top_risk * 100) if top_risk else None,
                'confidence_rank': {'low': 3, 'medium': 2, 'high': 1}.get(max_conf, 0),
            })
        return Response(students)


class StudentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view student details'}, status=status.HTTP_403_FORBIDDEN)

        student = User.objects.filter(pk=student_id, role='student').first()
        if not student:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

        submissions = Submission.objects.filter(student=student).select_related(
            'question', 'exam'
        ).order_by('question', 'attempt_number')

        # cohort rank
        cohort_students = User.objects.filter(role='student', cohort=student.cohort)
        cohort_rates = []
        for s in cohort_students:
            s_subs = Submission.objects.filter(student=s)
            t = s_subs.count()
            p = s_subs.filter(status='passed').count()
            cohort_rates.append((s.id, round(p / t * 100, 1) if t else 0))
        cohort_rates.sort(key=lambda x: x[1], reverse=True)
        my_rate = next((r for sid, r in cohort_rates if sid == student.id), 0)
        rank = next((i + 1 for i, (sid, _) in enumerate(cohort_rates) if sid == student.id), None)

        # performance trend — one point per weekly contest (exam), ordered by exam date
        exam_ids = submissions.values_list('exam_id', flat=True).distinct()
        exams_for_student = Exam.objects.filter(id__in=exam_ids).order_by('start_time')
        performance_trend = []
        for exam in exams_for_student:
            exam_subs = submissions.filter(exam=exam)
            exam_duration_s = exam.duration_minutes * 60
            pcts = []
            for s in exam_subs:
                if s.time_remaining_seconds is not None and exam_duration_s > 0:
                    pcts.append(round((exam_duration_s - s.time_remaining_seconds) / exam_duration_s * 100, 1))
            total = exam_subs.count()
            passed = exam_subs.filter(status='passed').count()
            performance_trend.append({
                'date': str(exam.start_time.date()),
                'exam': exam.title,
                'status': 'passed' if passed > total / 2 else 'failed',
                'pct_time_used': round(sum(pcts) / len(pcts), 1) if pcts else None,
                'questions_attempted': total,
                'questions_passed': passed,
            })

        # per-question breakdown
        questions_data = {}
        for sub in submissions:
            q_id = sub.question.id
            if q_id not in questions_data:
                questions_data[q_id] = {
                    'question_id': q_id,
                    'question_title': sub.question.title,
                    'max_attempts': sub.question.max_attempts,
                    'attempts': [],
                }

            flag = PlagiarismFlag.objects.filter(
                Q(submission_1=sub) | Q(submission_2=sub), flagged=True
            ).select_related('submission_1__student', 'submission_2__student').first()

            solve_time = None
            if sub.time_remaining_seconds is not None:
                exam_duration_seconds = sub.exam.duration_minutes * 60
                solve_time = exam_duration_seconds - sub.time_remaining_seconds

            try:
                bf = sub.behavioural_flag
                behavioural = {
                    'risk_score':    round(bf.risk_score, 2),
                    'confidence':    bf.confidence,
                    'paste_score':   round(bf.paste_score, 2),
                    'time_score':    round(bf.time_score, 2),
                    'tab_score':     round(bf.snapshot_score, 2),
                    'surprise_score': round(bf.submission_score, 2),
                    'signals':       bf.signals_triggered,
                }
            except Exception:
                behavioural = None

            matched_student = None
            if flag:
                matched_student = (
                    flag.submission_2.student.username
                    if flag.submission_1_id == sub.id
                    else flag.submission_1.student.username
                )

            questions_data[q_id]['attempts'].append({
                'submission_id':       sub.id,
                'attempt_number':      sub.attempt_number,
                'status':              sub.status,
                'language':            sub.language,
                'submitted_at':        sub.submitted_at,
                'execution_time_ms':   sub.execution_time_ms,
                'time_remaining_seconds': sub.time_remaining_seconds,
                'solve_time_seconds':  solve_time,
                'percent_time_used':   sub.percent_time_used,
                'paste_detected':      sub.had_paste_event,
                'paste_char_count':    sub.paste_char_count,
                'tab_switch_count':    sub.tab_switch_count,
                'behavioural':         behavioural,
                'plagiarism': {
                    'score':           flag.similarity_score,
                    'review_status':   flag.review_status,
                    'matched_student': matched_student,
                } if flag else None,
            })

        # aggregate stats
        all_subs = Submission.objects.filter(student=student)
        total = all_subs.count()
        passed = all_subs.filter(status='passed').count()
        avg_exec = all_subs.filter(execution_time_ms__isnull=False).aggregate(a=Avg('execution_time_ms'))['a']
        sim_flags = PlagiarismFlag.objects.filter(
            Q(submission_1__student=student) | Q(submission_2__student=student), flagged=True
        ).select_related('submission_1__student', 'submission_2__student', 'submission_1__question')
        b_flags = BehaviouralFlag.objects.filter(
            submission__student=student
        ).select_related('submission__question', 'submission__exam').order_by('-risk_score')

        return Response({
            'student': {
                'id': student.id,
                'username': student.username,
                'email': student.email,
                'cohort': student.cohort,
                'pass_rate': round(passed / total * 100, 1) if total else 0,
                'total_submissions': total,
                'avg_execution_time': round(avg_exec, 0) if avg_exec else None,
                'cohort_rank': rank,
                'cohort_size': len(cohort_rates),
            },
            'performance_trend': performance_trend,
            'questions': list(questions_data.values()),
            'plagiarism_flags': [{
                'id': f.id,
                'question': f.submission_1.question.title,
                'matched_student': f.submission_2.student.username if f.submission_1.student == student else f.submission_1.student.username,
                'similarity_score': f.similarity_score,
                'review_status': f.review_status,
            } for f in sim_flags],
            'behavioural_flags': [{
                'id': f.id,
                'question': f.submission.question.title,
                'exam': f.submission.exam.title,
                'risk_score': round(f.risk_score, 2),
                'confidence': f.confidence,
                'paste_score': round(f.paste_score, 2),
                'time_score': round(f.time_score, 2),
                'signals': f.signals_triggered,
                'review_status': f.review_status,
            } for f in b_flags],
        })


class ExamHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        exams = Exam.objects.prefetch_related('questions__test_cases', 'enrollments').order_by('-created_at')
        result = []

        for exam in exams:
            enrolled = exam.enrollments.count()
            questions = list(exam.questions.all())
            subs = Submission.objects.filter(exam=exam)
            total_subs = subs.count()

            # unique students who submitted at least once
            submitters = subs.values('student_id').distinct().count()
            submission_pct = round(submitters / enrolled * 100, 1) if enrolled else 0

            passed = subs.filter(status='passed').count()
            pass_pct = round(passed / total_subs * 100, 1) if total_subs else 0

            # behavioural flags touching this exam
            b_flags = BehaviouralFlag.objects.filter(
                submission__exam=exam
            ).count()
            flag_pct = round(b_flags / total_subs * 100, 1) if total_subs else 0

            # similarity pairs touching this exam (check both sides of the pair)
            sim_pairs = PlagiarismFlag.objects.filter(flagged=True).filter(
                Q(submission_1__exam=exam) | Q(submission_2__exam=exam)
            ).count()

            # avg solve time across passed submissions
            avg_solve = subs.filter(
                status='passed', time_to_complete_seconds__gt=0
            ).aggregate(a=Avg('time_to_complete_seconds'))['a']

            # avg execution time
            avg_exec = subs.filter(
                execution_time_ms__isnull=False
            ).aggregate(a=Avg('execution_time_ms'))['a']

            # per-question breakdown
            q_stats = []
            for q in questions:
                q_subs = subs.filter(question=q)
                q_total = q_subs.count()
                q_passed = q_subs.filter(status='passed').count()
                q_avg_solve = q_subs.filter(
                    status='passed', time_to_complete_seconds__gt=0
                ).aggregate(a=Avg('time_to_complete_seconds'))['a']
                q_flags = BehaviouralFlag.objects.filter(submission__question=q, submission__exam=exam).count()
                q_stats.append({
                    'question_id': q.id,
                    'title': q.title,
                    'difficulty': q.difficulty,
                    'total_attempts': q_total,
                    'pass_rate': round(q_passed / q_total * 100, 1) if q_total else 0,
                    'avg_solve_s': round(avg_solve, 0) if q_avg_solve else None,
                    'flag_count': q_flags,
                    'test_case_count': q.test_cases.count(),
                })

            # hardest question = lowest pass rate among attempted
            attempted_qs = [q for q in q_stats if q['total_attempts'] > 0]
            hardest = min(attempted_qs, key=lambda x: x['pass_rate'], default=None)

            # most popular language
            lang_counts = subs.values('language').annotate(n=Count('id')).order_by('-n')
            top_lang = lang_counts[0]['language'] if lang_counts else None

            # confirmed plagiarism cases (check both sides)
            confirmed_pairs = PlagiarismFlag.objects.filter(
                flagged=True, review_status='confirmed'
            ).filter(
                Q(submission_1__exam=exam) | Q(submission_2__exam=exam)
            ).count()

            now = timezone.now()
            if exam.end_time and exam.end_time < now:
                exam_status = 'ended'
            elif exam.is_active:
                exam_status = 'live'
            else:
                exam_status = 'draft'

            result.append({
                'exam_id': exam.id,
                'title': exam.title,
                'description': exam.description,
                'status': exam_status,
                'duration_minutes': exam.duration_minutes,
                'start_time': exam.start_time,
                'end_time': exam.end_time,
                'created_at': exam.created_at,
                'enrolled': enrolled,
                'submitters': submitters,
                'submission_pct': submission_pct,
                'total_submissions': total_subs,
                'pass_pct': pass_pct,
                'flag_pct': flag_pct,
                'behavioural_flags': b_flags,
                'similarity_pairs': sim_pairs,
                'confirmed_plagiarism': confirmed_pairs,
                'avg_solve_s': round(avg_solve, 0) if avg_solve else None,
                'avg_exec_ms': round(avg_exec, 0) if avg_exec else None,
                'top_language': top_lang,
                'question_count': len(questions),
                'hardest_question': hardest['title'] if hardest else None,
                'hardest_pass_rate': hardest['pass_rate'] if hardest else None,
                'questions': q_stats,
            })

        return Response(result)


class ExamDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        try:
            exam = Exam.objects.prefetch_related(
                'questions__test_cases', 'enrollments__student'
            ).get(pk=exam_id)
        except Exam.DoesNotExist:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        questions = list(exam.questions.all())
        subs = Submission.objects.filter(exam=exam)
        total_subs = subs.count()
        enrolled = exam.enrollments.count()

        submitters = subs.values('student_id').distinct().count()
        submission_pct = round(submitters / enrolled * 100, 1) if enrolled else 0

        passed = subs.filter(status='passed').count()
        pass_pct = round(passed / total_subs * 100, 1) if total_subs else 0

        b_flags = BehaviouralFlag.objects.filter(submission__exam=exam).count()
        flag_pct = round(b_flags / total_subs * 100, 1) if total_subs else 0

        sim_pairs = PlagiarismFlag.objects.filter(flagged=True).filter(
            Q(submission_1__exam=exam) | Q(submission_2__exam=exam)
        ).count()
        confirmed_pairs = PlagiarismFlag.objects.filter(
            flagged=True, review_status='confirmed'
        ).filter(
            Q(submission_1__exam=exam) | Q(submission_2__exam=exam)
        ).count()

        avg_solve = subs.filter(
            status='passed', time_to_complete_seconds__gt=0
        ).aggregate(a=Avg('time_to_complete_seconds'))['a']
        avg_exec = subs.filter(
            execution_time_ms__isnull=False
        ).aggregate(a=Avg('execution_time_ms'))['a']

        lang_counts = subs.values('language').annotate(n=Count('id')).order_by('-n')
        top_lang = lang_counts[0]['language'] if lang_counts else None

        # per-question breakdown
        q_stats = []
        for q in questions:
            q_subs = subs.filter(question=q)
            q_total = q_subs.count()
            q_passed = q_subs.filter(status='passed').count()
            q_avg_solve = q_subs.filter(
                status='passed', time_to_complete_seconds__gt=0
            ).aggregate(a=Avg('time_to_complete_seconds'))['a']
            q_flags = BehaviouralFlag.objects.filter(
                submission__question=q, submission__exam=exam
            ).count()
            q_stats.append({
                'question_id': q.id,
                'title': q.title,
                'difficulty': q.difficulty,
                'total_attempts': q_total,
                'pass_rate': round(q_passed / q_total * 100, 1) if q_total else 0,
                'avg_solve_s': round(q_avg_solve, 0) if q_avg_solve else None,
                'flag_count': q_flags,
                'test_case_count': q.test_cases.count(),
            })

        attempted_qs = [q for q in q_stats if q['total_attempts'] > 0]
        hardest = min(attempted_qs, key=lambda x: x['pass_rate'], default=None)

        now = timezone.now()
        if exam.end_time and exam.end_time < now:
            exam_status = 'ended'
        elif exam.is_active:
            exam_status = 'live'
        else:
            exam_status = 'draft'

        # per-student stats for all enrolled students
        student_stats = []
        for enrollment in exam.enrollments.all():
            student = enrollment.student
            s_subs = subs.filter(student=student)
            s_total = s_subs.count()
            q_passed_count = s_subs.filter(status='passed').values('question').distinct().count()
            q_attempted = s_subs.values('question').distinct().count()
            # pass rate = % of exam questions solved (at least one pass per question)
            s_pass_rate = round(q_passed_count / len(questions) * 100, 1) if questions else 0
            s_avg_solve = s_subs.filter(
                status='passed', time_to_complete_seconds__gt=0
            ).aggregate(a=Avg('time_to_complete_seconds'))['a']
            s_b_flags = BehaviouralFlag.objects.filter(
                submission__student=student, submission__exam=exam
            ).count()
            s_sim_flags = PlagiarismFlag.objects.filter(flagged=True).filter(
                Q(submission_1__student=student, submission_1__exam=exam) |
                Q(submission_2__student=student, submission_2__exam=exam)
            ).count()

            name = f"{student.first_name} {student.last_name}".strip()
            student_stats.append({
                'student_id': student.id,
                'username': student.username,
                'full_name': name or student.username,
                'submitted': s_total > 0,
                'questions_attempted': q_attempted,
                'questions_passed': q_passed_count,
                'total_questions': len(questions),
                'pass_rate': s_pass_rate,
                'avg_solve_s': round(s_avg_solve, 0) if s_avg_solve else None,
                'behavioural_flags': s_b_flags,
                'similarity_flags': s_sim_flags,
            })

        # rank by questions solved desc, then avg solve time asc
        student_stats.sort(key=lambda x: (-x['questions_passed'], x['avg_solve_s'] or 999999))
        for i, s in enumerate(student_stats):
            s['rank'] = i + 1

        top_performers = [s for s in student_stats if s['submitted']][:10]

        return Response({
            'exam_id': exam.id,
            'title': exam.title,
            'description': exam.description,
            'status': exam_status,
            'duration_minutes': exam.duration_minutes,
            'start_time': exam.start_time,
            'end_time': exam.end_time,
            'created_at': exam.created_at,
            'enrolled': enrolled,
            'submitters': submitters,
            'submission_pct': submission_pct,
            'total_submissions': total_subs,
            'pass_pct': pass_pct,
            'flag_pct': flag_pct,
            'behavioural_flags': b_flags,
            'similarity_pairs': sim_pairs,
            'confirmed_plagiarism': confirmed_pairs,
            'avg_solve_s': round(avg_solve, 0) if avg_solve else None,
            'avg_exec_ms': round(avg_exec, 0) if avg_exec else None,
            'top_language': top_lang,
            'question_count': len(questions),
            'hardest_question': hardest['title'] if hardest else None,
            'hardest_pass_rate': hardest['pass_rate'] if hardest else None,
            'questions': q_stats,
            'top_performers': top_performers,
            'students': student_stats,
        })


# ── Cost constants (AWS Fargate pricing, matches our Docker container config) ──
# Container config: nano_cpus=500_000_000 (0.5 vCPU), mem_limit='128m' (0.125 GB)
_FARGATE_VCPU_PER_HOUR   = 0.04048   # USD per vCPU-hour
_FARGATE_GB_PER_HOUR     = 0.004445  # USD per GB-hour
_CONTAINER_VCPU          = 0.5       # matches nano_cpus setting
_CONTAINER_GB            = 0.125     # matches mem_limit='128m'
_COLD_START_MS           = 10000     # Fargate task cold start (image pull + task init)
_REDIS_MONTHLY           = 13.00     # ElastiCache t3.micro on-demand us-east-1
_DB_MONTHLY              = 26.00     # RDS t3.micro PostgreSQL on-demand us-east-1
_CELERY_MONTHLY          = 0.00      # no dedicated worker machine — Fargate spins tasks on demand

def _cost_for_ms(exec_ms):
    total_ms = (exec_ms or 500) + _COLD_START_MS
    hours = total_ms / 3_600_000
    return (hours * _CONTAINER_VCPU * _FARGATE_VCPU_PER_HOUR +
            hours * _CONTAINER_GB    * _FARGATE_GB_PER_HOUR)


class CostAnalysisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        all_subs = Submission.objects.select_related('question', 'exam').all()
        total_subs = all_subs.count()

        # ── Compute cost per submission ───────────────────────────────────────
        submission_costs = []
        lang_buckets = {}
        for sub in all_subs:
            cost = _cost_for_ms(sub.execution_time_ms)
            submission_costs.append({
                'exam_id': sub.exam_id,
                'lang': sub.language,
                'exec_ms': sub.execution_time_ms or 500,
                'cost': cost,
                'passed': sub.status == 'passed',
                'attempt': sub.attempt_number,
            })
            if sub.language not in lang_buckets:
                lang_buckets[sub.language] = {'count': 0, 'total_ms': 0, 'total_cost': 0.0}
            lang_buckets[sub.language]['count'] += 1
            lang_buckets[sub.language]['total_ms'] += (sub.execution_time_ms or 500)
            lang_buckets[sub.language]['total_cost'] += cost

        total_compute_cost = sum(s['cost'] for s in submission_costs)
        avg_cost_per_sub = total_compute_cost / total_subs if total_subs else 0

        # ── Weekly / monthly estimates ────────────────────────────────────────
        since_7d = timezone.now() - timedelta(days=7)
        subs_last_7d = all_subs.filter(submitted_at__gte=since_7d)
        weekly_compute = sum(_cost_for_ms(s.execution_time_ms) for s in subs_last_7d)
        monthly_compute_projection = weekly_compute * 4.33

        fixed_monthly = _REDIS_MONTHLY + _DB_MONTHLY + _CELERY_MONTHLY
        total_monthly = monthly_compute_projection + fixed_monthly

        # ── Per-exam breakdown ────────────────────────────────────────────────
        by_exam = {}
        for s in submission_costs:
            eid = s['exam_id']
            if eid not in by_exam:
                by_exam[eid] = {'total': 0.0, 'wasted': 0.0, 'count': 0, 'retry_cost': 0.0}
            by_exam[eid]['total'] += s['cost']
            by_exam[eid]['count'] += 1
            if not s['passed']:
                by_exam[eid]['wasted'] += s['cost']
            if s['attempt'] > 1:
                by_exam[eid]['retry_cost'] += s['cost']

        exam_rows = []
        for exam in Exam.objects.all():
            d = by_exam.get(exam.id, {'total': 0, 'wasted': 0, 'count': 0, 'retry_cost': 0})
            enrolled = exam.enrollments.count()
            exam_rows.append({
                'exam_id': exam.id,
                'title': exam.title,
                'total_submissions': d['count'],
                'total_cost_usd': round(d['total'], 4),
                'avg_cost_per_sub': round(d['total'] / d['count'], 5) if d['count'] else 0,
                'wasted_cost_usd': round(d['wasted'], 4),
                'retry_cost_usd': round(d['retry_cost'], 4),
                'waste_pct': round(d['wasted'] / d['total'] * 100, 1) if d['total'] else 0,
                'cost_per_student': round(d['total'] / enrolled, 4) if enrolled else 0,
            })
        exam_rows.sort(key=lambda x: x['total_cost_usd'], reverse=True)

        # ── Language breakdown ────────────────────────────────────────────────
        by_language = {}
        for lang, b in lang_buckets.items():
            by_language[lang] = {
                'count': b['count'],
                'avg_exec_ms': round(b['total_ms'] / b['count']) if b['count'] else 0,
                'total_cost': round(b['total_cost'], 4),
                'avg_cost_per_sub': round(b['total_cost'] / b['count'], 6) if b['count'] else 0,
            }

        # ── Failed / retry analysis ───────────────────────────────────────────
        failed_subs = [s for s in submission_costs if not s['passed']]
        wasted_total = sum(s['cost'] for s in failed_subs)
        retry_subs = [s for s in submission_costs if s['attempt'] > 1]
        retry_total = sum(s['cost'] for s in retry_subs)

        # ── Pass rate (needed for suggestions) ───────────────────────────────
        passed_count = sum(1 for s in submission_costs if s['passed'])
        overall_pass_rate = round(passed_count / total_subs * 100, 1) if total_subs else 0
        avg_exec_ms = round(sum(s['exec_ms'] for s in submission_costs) / total_subs) if total_subs else 0

        # ── Optimisation suggestions ──────────────────────────────────────────
        suggestions = []

        if wasted_total / total_compute_cost > 0.35 if total_compute_cost else False:
            savings = round(wasted_total * 0.4, 2)
            suggestions.append({
                'type': 'high',
                'title': 'High failed-submission cost',
                'detail': f'{round(wasted_total / total_compute_cost * 100, 1)}% of compute spend ({_fmt_usd(wasted_total)}) is on submissions that failed. Improve test case visibility so students get better feedback before submitting.',
                'savings': f'~{_fmt_usd(savings)}/month',
                'action': 'Add partial test case feedback (show 1 public test case result before final submission)',
            })

        if len(retry_subs) / total_subs > 0.30 if total_subs else False:
            savings = round(retry_total * 0.5, 2)
            suggestions.append({
                'type': 'medium',
                'title': 'High retry rate driving cost',
                'detail': f'{round(len(retry_subs)/total_subs*100,1)}% of submissions are retries ({_fmt_usd(retry_total)} spend). Each retry spins a new container — reduce retries by showing compiler errors inline.',
                'savings': f'~{_fmt_usd(savings)}/month',
                'action': 'Show stderr output on failed submissions so students fix code locally before retrying',
            })

        if _COLD_START_MS / (avg_exec_ms + _COLD_START_MS) > 0.6:
            cold_start_cost = sum(
                _COLD_START_MS / ((s['exec_ms'] + _COLD_START_MS) or 1) * _cost_for_ms(s['exec_ms'])
                for s in submission_costs
            )
            savings = round(cold_start_cost * 0.7, 2)
            suggestions.append({
                'type': 'high',
                'title': 'Container cold starts dominate cost',
                'detail': f'Cold start overhead ({_COLD_START_MS}ms) is more than your average execution time ({avg_exec_ms}ms). Most of your bill is paying for container spin-up, not actual work.',
                'savings': f'~{_fmt_usd(savings)}/month',
                'action': 'Use pre-warmed container pools or switch to AWS Lambda with provisioned concurrency',
            })

        slow_langs = [(l, d) for l, d in by_language.items() if d['avg_exec_ms'] > 2000]
        for lang, d in slow_langs:
            suggestions.append({
                'type': 'low',
                'title': f'{lang.title()} submissions are slow',
                'detail': f'Average {lang} execution is {d["avg_exec_ms"]}ms vs Python/JS at ~500ms. Slower execution = higher per-submission cost (${d["avg_cost_per_sub"]:.5f} vs ~$0.00003).',
                'savings': '10–30% on affected exams',
                'action': f'Set stricter time limits for {lang} or offer language-specific container images that are pre-compiled',
            })

        if overall_pass_rate < 50:
            suggestions.append({
                'type': 'medium',
                'title': 'Low pass rate inflating costs',
                'detail': f'Only {overall_pass_rate}% of submissions pass. Each failure still runs a full container. Better question scoping or difficulty calibration would reduce wasteful executions.',
                'savings': '20–40% on compute',
                'action': 'Review hardest questions — consider adding easier warm-up test cases or reducing max_attempts on easy questions',
            })

        if total_subs > 500:
            batch_savings = round(total_compute_cost * 0.15, 2)
            suggestions.append({
                'type': 'low',
                'title': 'Switch to spot/preemptible instances for workers',
                'detail': f'At {total_subs} submissions, Celery workers running on EC2 Spot or GCP Spot VMs would cut compute by 60–80%.',
                'savings': f'~{_fmt_usd(batch_savings)}/month',
                'action': 'Move Celery workers to Spot instances with a fallback on-demand worker for reliability',
            })

        suggestions.append({
            'type': 'low',
            'title': 'Cache Docker images on worker nodes',
            'detail': 'Every new worker node pulls 200MB+ language images before execution. Image pre-caching eliminates this latency and reduces cold start from ~2s to ~200ms.',
            'savings': '~$2–5/month in egress + faster UX',
            'action': 'Use ECR pull-through cache or pre-bake images into a custom AMI for your Celery workers',
        })

        return Response({
            'summary': {
                'total_compute_cost': round(total_compute_cost, 4),
                'avg_cost_per_submission': round(avg_cost_per_sub, 6),
                'wasted_cost': round(wasted_total, 4),
                'retry_cost': round(retry_total, 4),
                'waste_pct': round(wasted_total / total_compute_cost * 100, 1) if total_compute_cost else 0,
                'weekly_compute_cost': round(weekly_compute, 4),
                'monthly_compute_projection': round(monthly_compute_projection, 2),
                'monthly_fixed_cost': round(fixed_monthly, 2),
                'monthly_total_projection': round(total_monthly, 2),
                'total_submissions': total_subs,
                'avg_exec_ms': avg_exec_ms,
            },
            'infrastructure': {
                'redis_monthly': _REDIS_MONTHLY,
                'database_monthly': _DB_MONTHLY,
                'celery_worker_monthly': _CELERY_MONTHLY,
                'container_vcpu': _CONTAINER_VCPU,
                'container_memory_gb': _CONTAINER_GB,
                'cold_start_ms': _COLD_START_MS,
                'pricing_basis': 'AWS Fargate us-east-1',
            },
            'by_exam': exam_rows,
            'by_language': by_language,
            'optimizations': suggestions,
        })


def _fmt_usd(v):
    if v >= 1:
        return f'${v:.2f}'
    return f'${v:.4f}'

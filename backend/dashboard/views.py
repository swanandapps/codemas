from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Count, Avg, F, Max, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta
from analytics import metrics
from submissions.models import Submission
from plagiarism.models import PlagiarismFlag, BehaviouralFlag, PlagiarismPolicy, ReviewAuditLog
from plagiarism.views import exam_cases, case_keys, _case_status
from exams.models import Question, Exam, ExamEnrollment, newest_exam_first, exam_status
from support.models import DisputeRequest
from .health import build_dashboard_health


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view dashboard'}, status=status.HTTP_403_FORBIDDEN)

        population = metrics.students()
        subs = metrics.student_submissions()

        # --- KPI cards ---
        overall = metrics.success(subs)
        plagiarism_flags = PlagiarismFlag.objects.filter(flagged=True, review_status='pending').count()

        # --- Submissions timeline — last 14 days ---
        since = timezone.now() - timedelta(days=13)
        timeline_qs = (
            subs
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

        # --- Success rate by question (students who solved it / attempted it) ---
        q_accepted = metrics.question_success_by(subs)
        q_rows = {
            r['question_id']: r for r in
            subs.order_by().values('question_id').annotate(total=Count('id'), avg_exec=Avg('execution_time_ms'))
        }
        q_attempts = {}
        for r in subs.order_by().values('question_id', 'student_id').annotate(c=Count('id')):
            q_attempts.setdefault(r['question_id'], []).append(r['c'])
        question_stats = []
        for q in Question.objects.all():
            row = q_rows.get(q.id, {})
            attempts = q_attempts.get(q.id, [])
            question_stats.append({
                'question_id': q.id,
                'question_title': q.title,
                'total_attempts': row.get('total', 0),
                'accepted_rate': q_accepted.get(q.id, {}).get('accepted_rate'),
                'avg_execution_time': round(row['avg_exec'], 0) if row.get('avg_exec') else 0,
                'avg_attempts_to_pass': round(sum(attempts) / len(attempts), 1) if attempts else 0,
            })

        # --- Language distribution ---
        lang_qs = subs.order_by().values('language').annotate(count=Count('id'))
        language_distribution = {r['language']: r['count'] for r in lang_qs}

        # --- Cohort comparison ---
        cohort_accepted = metrics.success_by(subs, 'student__cohort')
        cohort_sizes = {
            r['cohort']: r['n'] for r in
            population.exclude(cohort='').order_by().values('cohort').annotate(n=Count('id'))
        }
        cohort_totals = {
            r['student__cohort']: r['n'] for r in
            subs.order_by().values('student__cohort').annotate(n=Count('id'))
        }
        cohort_comparison = [{
            'cohort': cohort,
            'student_count': n,
            'total_submissions': cohort_totals.get(cohort, 0),
            'accepted_rate': cohort_accepted.get(cohort, {}).get('accepted_rate'),
        } for cohort, n in sorted(cohort_sizes.items())]

        # --- Top performers (success rate = exams passed / exams taken) ---
        student_accepted = metrics.success_by(subs, 'student_id')
        student_rows = {
            r['student_id']: r for r in
            subs.order_by().values('student_id').annotate(total=Count('id'), avg_exec=Avg('execution_time_ms'))
        }
        sim_counts = {}
        for side in ('submission_1__student_id', 'submission_2__student_id'):
            for r in metrics.similarity_flags().order_by().values(side).annotate(n=Count('id')):
                sim_counts[r[side]] = sim_counts.get(r[side], 0) + r['n']
        student_stats = []
        for student in population.filter(id__in=list(student_rows)):
            row = student_rows[student.id]
            student_stats.append({
                'student_id': student.id,
                'username': student.username,
                'cohort': student.cohort,
                'total_submissions': row['total'],
                'accepted_rate': student_accepted.get(student.id, {}).get('accepted_rate'),
                'avg_execution_time': round(row['avg_exec'], 0) if row['avg_exec'] else None,
                'plagiarism_flags': sim_counts.get(student.id, 0),
            })

        student_stats.sort(key=lambda x: x['accepted_rate'] if x['accepted_rate'] is not None else -1, reverse=True)
        top_performers = student_stats[:5]
        struggling = [s for s in student_stats if s['accepted_rate'] is not None and s['accepted_rate'] < 40][:5]

        return Response({
            'kpis': {
                'total_students': population.count(),
                'total_submissions': subs.count(),
                'accepted_rate': overall['accepted_rate'],
                'plagiarism_flags': plagiarism_flags,
                'flags_to_review': metrics.flags_to_review(),
            },
            'timeline': timeline,
            'question_stats': question_stats,
            'language_distribution': language_distribution,
            'cohort_comparison': cohort_comparison,
            'top_performers': top_performers,
            'struggling_students': struggling,
        })


class DashboardHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view dashboard'}, status=status.HTTP_403_FORBIDDEN)

        return Response(build_dashboard_health())


class StudentsListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers'}, status=status.HTTP_403_FORBIDDEN)

        subs = metrics.student_submissions()
        accepted = metrics.success_by(subs, 'student_id')   # exams passed / exams taken
        totals = {r['student_id']: r['n'] for r in subs.order_by().values('student_id').annotate(n=Count('id'))}

        # behavioural flags per student (dismissed ones don't count): most suspicious level and highest risk
        flags = metrics.max_confidence_by_student()

        students = []
        for student in metrics.students().order_by('username'):
            f = flags.get(student.id)
            # confidence of misconduct: high = most suspicious (3+ signals), low = 1 signal
            max_conf = f['max_confidence'] if f else None
            students.append({
                'student_id': student.id,
                'username': student.username,
                'cohort': student.cohort or '',
                'total_submissions': totals.get(student.id, 0),
                'accepted_rate': accepted.get(student.id, {}).get('accepted_rate'),
                'max_confidence': max_conf,
                'max_risk': metrics.risk(f['max_risk_score']) if f else None,
                'confidence_rank': metrics.CONFIDENCE_RANK.get(max_conf, 0),
            })
        return Response(students)


class StudentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view student details'}, status=status.HTTP_403_FORBIDDEN)

        student = metrics.students().filter(pk=student_id).first()
        if not student:
            return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

        # newest exam first, so the attempt just made isn't buried under past exams
        submissions = Submission.objects.filter(student=student).select_related(
            'question', 'exam'
        ).order_by(F('exam__start_time').desc(nulls_first=True), 'question', 'attempt_number')

        # section rank by score, then faster average solve: the same numbers as the student's Home and My results
        section_scores = metrics.cohort_scores(student.cohort)
        standing = metrics.competition_rank(section_scores, student.id,
                                            metrics.solve_times(Submission.objects.filter(student__cohort=student.cohort)))

        # performance trend — one point per weekly contest (exam), ordered by exam date
        my_subs = Submission.objects.filter(student=student)
        exam_results = {r['exam_id']: r for r in metrics.exam_results(my_subs)}
        # points the student lost to confirmed plagiarism, per question (already out of every score and rank)
        earned = {qid: pts for (_, qid), pts in metrics.earned_points(my_subs).items()}
        withheld = {qid: pts for (_, qid), pts in metrics.withheld_points(my_subs).items()}
        exam_ids = my_subs.values_list('exam_id', flat=True).distinct()
        exams_for_student = Exam.objects.filter(id__in=exam_ids).order_by('start_time')
        performance_trend = []
        for exam in exams_for_student:
            exam_subs = [s for s in submissions if s.exam_id == exam.id]
            exam_duration_s = exam.duration_minutes * 60
            solve_times = [_solve_seconds(s) for s in exam_subs]
            pcts = [
                round(t / exam_duration_s * 100, 1)
                for t in solve_times
                if t is not None and exam_duration_s > 0
            ]
            result = exam_results.get(exam.id, {'solved': 0, 'voided': 0, 'total': 0, 'passed': False})
            exam_qids = {s.question_id for s in exam_subs}
            performance_trend.append({
                'date': str(exam.start_time.date()) if exam.start_time else None,
                'exam': exam.title,
                # green dot = passed the exam: solved at least half of its questions (the success-rate rule);
                # a question voided for confirmed plagiarism is not solved, so it can turn the dot red
                'status': 'passed' if result['passed'] else 'failed',
                'pct_time_used': round(sum(pcts) / len(pcts), 1) if pcts else None,
                'questions_solved': result['solved'],
                'questions_voided': result['voided'],   # solved, but not counted: plagiarism confirmed
                'questions_total': result['total'],
                'points': sum(earned.get(q, 0) for q in exam_qids),
                'points_withheld': sum(withheld.get(q, 0) for q in exam_qids),
            })

        # per-question breakdown; the limit is the one the server enforces (see SubmissionCreateView)
        attempt_limit = PlagiarismPolicy.get().max_attempts
        questions_data = {}
        for sub in submissions:
            q_id = sub.question.id
            if q_id not in questions_data:
                questions_data[q_id] = {
                    'question_id': q_id,
                    'question_title': sub.question.title,
                    'exam': sub.exam.title,
                    'max_attempts': attempt_limit,
                    'points_withheld': withheld.get(q_id, 0),   # lost to confirmed plagiarism
                    'attempts_used': 0,   # 'error' attempts are refunded, so they don't use one up
                    'attempts': [],
                }
            if sub.status != 'error':
                questions_data[q_id]['attempts_used'] += 1

            flag = metrics.similarity_flags().filter(
                Q(submission_1=sub) | Q(submission_2=sub)
            ).select_related('submission_1__student', 'submission_2__student').first()

            solve_time = _solve_seconds(sub)

            try:
                bf = sub.behavioural_flag
                behavioural = {
                    'risk_score':    round(bf.risk_score, 2),
                    'risk':          metrics.risk(bf.risk_score),
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
        overall = metrics.success(my_subs)   # exams passed / exams taken
        avg_exec = my_subs.filter(execution_time_ms__isnull=False).aggregate(a=Avg('execution_time_ms'))['a']
        sim_flags = PlagiarismFlag.objects.filter(
            Q(submission_1__student=student) | Q(submission_2__student=student), flagged=True
        ).select_related('submission_1__student', 'submission_2__student', 'submission_1__question',
                         'submission_1__exam', 'reviewed_by').order_by(
            newest_exam_first('submission_1__exam__'), '-similarity_score', '-id')
        b_flags = BehaviouralFlag.objects.filter(
            submission__student=student
        ).select_related('submission__question', 'submission__exam', 'reviewed_by').order_by(
            newest_exam_first('submission__exam__'), '-risk_score', '-id')
        sim_flags, b_flags = list(sim_flags), list(b_flags)
        exam_of_question = {sub.question_id: sub.exam_id for sub in submissions}
        withheld_by_exam = {}
        for qid, pts in withheld.items():
            eid = exam_of_question.get(qid)
            withheld_by_exam[eid] = withheld_by_exam.get(eid, 0) + pts
        disputes = DisputeRequest.objects.filter(student=student).order_by('-created_at').values(
            'id', 'exam_id', 'flag_type', 'flag_id', 'student_note', 'status', 'resolution_note', 'created_at',
            exam_title=F('exam__title'))
        appeals = {}   # exam_id -> the student's appeal there (legacy rows can repeat: the newest wins)
        for d in list(disputes)[::-1]:
            if d['exam_id']:
                appeals[d['exam_id']] = {'id': d['id'], 'status': d['status'], 'student_note': d['student_note']}

        return Response({
            'student': {
                'id': student.id,
                'username': student.username,
                'email': student.email,
                'cohort': student.cohort,
                'accepted_rate': overall['accepted_rate'],
                'exams_passed': overall['passed'],
                'exams_taken': overall['taken'],
                'total_submissions': my_subs.count(),
                'avg_execution_time': round(avg_exec, 0) if avg_exec else None,
                'score': section_scores.get(student.id, 0),   # the score behind the section rank
                'points_withheld': sum(withheld.values()),
                'cohort_rank': standing['rank'],
                'cohort_size': standing['size'],
                'open_disputes': sum(1 for d in disputes if d['status'] == 'open'),
            },
            'performance_trend': performance_trend,
            'questions': list(questions_data.values()),
            'integrity_cases': _integrity_cases(student, sim_flags, b_flags, withheld_by_exam, appeals),
            'plagiarism_flags': [{
                'id': f.id,
                'question': f.submission_1.question.title,
                'exam': f.submission_1.exam.title,
                'exam_id': f.submission_1.exam_id,
                # this student's side of the pair, and the other student (linked by user id)
                'submission_id': f.submission_1_id if f.submission_1.student_id == student.id else f.submission_2_id,
                'matched_student': f.submission_2.student.username if f.submission_1.student_id == student.id else f.submission_1.student.username,
                'matched_student_id': f.submission_2.student_id if f.submission_1.student_id == student.id else f.submission_1.student_id,
                'similarity_score': f.similarity_score,
                'review_status': f.review_status,
                'review_note': f.review_note,
                'reviewed_by': f.reviewed_by.username if f.reviewed_by else None,
            } for f in sim_flags],
            'behavioural_flags': [{
                'id': f.id,
                'question': f.submission.question.title,
                'exam': f.submission.exam.title,
                'exam_id': f.submission.exam_id,
                'risk_score': round(f.risk_score, 2),
                'risk': metrics.risk(f.risk_score),
                'confidence': f.confidence,
                'paste_score': round(f.paste_score, 2),
                'time_score': round(f.time_score, 2),
                'signals': f.signals_triggered,
                'review_status': f.review_status,
                'review_note': f.review_note,
                'reviewed_by': f.reviewed_by.username if f.reviewed_by else None,
                'submission_id': f.submission_id,
            } for f in b_flags],
            'disputes': list(disputes),
        })


def _integrity_cases(student, sim_flags, b_flags, withheld_by_exam, appeals):
    """The student page's Integrity tab: one group per exam where the student has a flag
    (pending or decided), newest exam first. Status is the student's
    own flags there; case_key is the investigation case they are in on that exam, so the
    page can open it; review is the latest decision and the note the student was sent;
    appeal is the student's appeal on the exam ({id, status, student_note}) or None."""
    exams = {}

    def group(exam):
        return exams.setdefault(exam.id, {'exam': exam, 'pairs': [], 'behavioural': []})

    for f in sim_flags:
        group(f.submission_1.exam)['pairs'].append(f)
    for f in b_flags:
        group(f.submission.exam)['behavioural'].append(f)

    # when each flag was last decided, from the review audit log (seeded decisions have none)
    decided_at = {}
    for kind, flags in (('similarity', sim_flags), ('behavioural', b_flags)):
        ids = [f.id for f in flags if f.review_status != 'pending']
        for r in (ReviewAuditLog.objects.filter(flag_type=kind, flag_id__in=ids).order_by()
                  .values('flag_id').annotate(at=Max('created_at'))):
            decided_at[(kind, r['flag_id'])] = r['at']

    groups = []
    for exam_id, g in exams.items():
        exam = g['exam']
        pairs, behavioural = g['pairs'], g['behavioural']
        matches = {}
        for p in pairs:
            other = p.submission_2.student if p.submission_1.student_id == student.id else p.submission_1.student
            best = matches.get(other.id)
            if best is None or p.similarity_score > best['score']:
                matches[other.id] = {'student_id': other.id, 'username': other.username,
                                     'score': round(p.similarity_score, 3)}
        riskiest = max(behavioural, key=lambda f: f.risk_score, default=None)
        decided = sorted(
            [(decided_at.get(('similarity', f.id)), f) for f in pairs if f.review_status != 'pending']
            + [(decided_at.get(('behavioural', f.id)), f) for f in behavioural if f.review_status != 'pending'],
            key=lambda d: (d[0] is not None, d[0] or 0, bool(d[1].review_note)), reverse=True,
        )
        questions = [f.submission_1.question.title for f in pairs] + [f.submission.question.title for f in behavioural]
        groups.append({
            'exam_id': exam_id,
            'exam_title': exam.title,
            'exam_date': exam.start_time.isoformat() if exam.start_time else None,
            'questions': list(dict.fromkeys(questions)),
            'status': _case_status([f.review_status for f in pairs + behavioural]),
            'points_withheld': withheld_by_exam.get(exam_id, 0),
            'case_key': case_keys(exam_cases(exam_id)).get(student.id),
            'appeal': appeals.get(exam_id),
            'behaviour_flags': len(behavioural),
            'top_signals': (riskiest.signals_triggered or [])[:2] if riskiest else [],
            'code_matches': sorted(matches.values(), key=lambda m: (-m['score'], m['username'])),
            # the latest decision, with the note the student was sent (a later flag in the same
            # decision may carry none, e.g. a pair whose two students got different notes)
            'review': {
                'note': next((f.review_note for _, f in decided if f.review_note), ''),
                'reviewed_by': decided[0][1].reviewed_by.username if decided[0][1].reviewed_by else None,
                'reviewed_at': decided[0][0].isoformat() if decided[0][0] else None,
            } if decided else None,
        })
    # newest exam first, the same order as newest_exam_first
    groups.sort(key=lambda g: exams[g['exam_id']]['exam'].start_time or exams[g['exam_id']]['exam'].created_at,
                reverse=True)
    return groups


def _solve_seconds(sub):
    """Seconds from exam start to this submission (time_to_complete_seconds, as the exam report
    averages); older rows without it fall back to the exam clock. None when neither is known."""
    if sub.time_to_complete_seconds and sub.time_to_complete_seconds > 0:
        return sub.time_to_complete_seconds
    if sub.time_remaining_seconds is not None:
        return sub.exam.duration_minutes * 60 - sub.time_remaining_seconds
    return None


def _exam_rows(exams):
    """Exam history rows (shared by the list and the detail endpoint). The
    canonical metrics come from analytics.metrics.exam_summaries; the rest are
    descriptive aggregates over the same student-population submissions."""
    exam_ids = [e.id for e in exams]
    summaries = metrics.exam_summaries(exam_ids)
    subs = metrics.student_submissions(Submission.objects.filter(exam_id__in=exam_ids))
    passed_timed = Q(status='passed', time_to_complete_seconds__gt=0)

    exam_aggs = {
        r['exam_id']: r for r in subs.order_by().values('exam_id').annotate(
            total=Count('id'),
            avg_solve=Avg('time_to_complete_seconds', filter=passed_timed),
            avg_exec=Avg('execution_time_ms'),
        )
    }
    top_lang = {}
    for r in subs.order_by().values('exam_id', 'language').annotate(n=Count('id')).order_by('exam_id', '-n'):
        top_lang.setdefault(r['exam_id'], r['language'])

    q_accepted = metrics.question_success_by(subs)
    q_aggs = {
        r['question_id']: r for r in subs.order_by().values('question_id').annotate(
            total=Count('id'),
            avg_solve=Avg('time_to_complete_seconds', filter=passed_timed),
            flags=Count('id', filter=metrics.FLAGGED),
        )
    }

    sim = {
        r['submission_1__exam_id']: r for r in
        metrics.similarity_flags().filter(submission_1__exam_id__in=exam_ids).order_by()
        .values('submission_1__exam_id')
        .annotate(pairs=Count('id'), confirmed=Count('id', filter=Q(review_status='confirmed')))
    }
    b_flag_counts = {
        r['exam_id']: r['n'] for r in
        subs.filter(metrics.FLAGGED).order_by().values('exam_id').annotate(n=Count('id'))
    }

    now = timezone.now()
    rows = []
    for exam in exams:
        agg = exam_aggs.get(exam.id, {})
        q_stats = []
        for q in exam.questions.all():
            qa = q_aggs.get(q.id, {})
            qs = q_accepted.get(q.id, {})
            q_stats.append({
                'question_id': q.id,
                'title': q.title,
                'difficulty': q.difficulty,
                'total_attempts': qa.get('total', 0),
                'solved_students': qs.get('solved_students', 0),
                'attempted_students': qs.get('attempted_students', 0),
                'accepted_rate': qs.get('accepted_rate'),   # students who solved it / attempted it
                'avg_solve_s': round(qa['avg_solve'], 0) if qa.get('avg_solve') else None,
                'flag_count': qa.get('flags', 0),
                'test_case_count': len(q.test_cases.all()),
            })

        # hardest question = lowest question success rate among attempted questions, ties to the lowest id (as the overview)
        hardest = metrics.hardest_question({q['question_id']: q for q in q_stats})
        hardest = hardest[1] if hardest else None
        s = sim.get(exam.id, {})

        rows.append({
            'exam_id': exam.id,
            'title': exam.title,
            'description': exam.description,
            'status': exam_status(exam, now),
            'duration_minutes': exam.duration_minutes,
            'start_time': exam.start_time,
            'end_time': exam.end_time,
            'created_at': exam.created_at,
            **summaries[exam.id],
            'integrity_health': metrics.integrity_health(summaries[exam.id]['flagged_students_rate']),
            'total_submissions': agg.get('total', 0),
            'behavioural_flags': b_flag_counts.get(exam.id, 0),
            'similarity_pairs': s.get('pairs', 0),
            'confirmed_plagiarism': s.get('confirmed', 0),
            'avg_solve_s': round(agg['avg_solve'], 0) if agg.get('avg_solve') else None,
            'avg_exec_ms': round(agg['avg_exec'], 0) if agg.get('avg_exec') else None,
            'top_language': top_lang.get(exam.id),
            'question_count': len(q_stats),
            'hardest_question': hardest['title'] if hardest else None,
            'hardest_accepted_rate': hardest['accepted_rate'] if hardest else None,
            'questions': q_stats,
        })
    return rows


class ExamHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        exams = list(Exam.objects.prefetch_related('questions__test_cases').order_by(newest_exam_first(), '-id'))
        return Response(_exam_rows(exams))


class ExamDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        exam = Exam.objects.prefetch_related('questions__test_cases').filter(pk=exam_id).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        payload = _exam_rows([exam])[0]
        total_questions = payload['question_count']
        subs = Submission.objects.filter(exam=exam)

        # per-student numbers, grouped (one query each), same definitions as everywhere else
        results = {r['student_id']: r for r in metrics.exam_results(subs)}   # one row per student who took it
        avg_solve = metrics.solve_times(subs)   # also the rank tie-break: faster first on equal points
        b_flags = {
            r['student_id']: r['n'] for r in
            subs.filter(metrics.FLAGGED).order_by().values('student_id').annotate(n=Count('id'))
        }
        # live status: attempts (a refunded 'error' isn't one) and each student's latest submission
        attempts = {
            r['student_id']: r['n'] for r in
            subs.exclude(status='error').order_by().values('student_id').annotate(n=Count('id'))
        }
        latest = {}
        for sub in subs.order_by('student_id', '-submitted_at', '-id').only('student_id', 'status', 'submitted_at'):
            latest.setdefault(sub.student_id, sub)
        sim_flags = {}
        for side in ('submission_1', 'submission_2'):
            for r in (
                metrics.similarity_flags().filter(**{f'{side}__exam': exam}).order_by()
                .values(f'{side}__student_id').annotate(n=Count('id'))
            ):
                sid = r[f'{side}__student_id']
                sim_flags[sid] = sim_flags.get(sid, 0) + r['n']

        student_stats = []
        enrolled = list(metrics.student_enrollments(ExamEnrollment.objects.filter(exam=exam)).select_related('student'))
        # rank by points on this exam across every enrolled student (all sections), equal points split by
        # average solve time: the same score and tie rule as the student's My results
        scores = metrics.scores_for([e.student_id for e in enrolled], subs)
        # confirmed plagiarism withholds a question's points (already out of `scores`); a pending flag marks "Under review"
        withheld = metrics.points_withheld_by_student(subs)
        voided = {sid for sid, _ in metrics.voided_pairs(subs)}
        reviewing = metrics.under_review(subs)
        case_of = case_keys(exam_cases(exam.id))   # the badge opens the student's case
        for enrollment in enrolled:
            student = enrollment.student
            result = results.get(student.id)
            name = f"{student.first_name} {student.last_name}".strip()
            student_stats.append({
                'student_id': student.id,
                'username': student.username,
                'full_name': name or student.username,
                'submitted': result is not None,
                'questions_solved': result['solved'] if result else 0,   # counted: voided questions left out
                'questions_voided': result['voided'] if result else 0,   # solved, but not counted: plagiarism confirmed
                'total_questions': total_questions,
                'passed': result['passed'] if result else None,   # solved at least half: counts toward the success rate
                'points': scores[student.id],
                'rank': metrics.exam_standing(scores, student.id, avg_solve)['rank'],   # None: no points, not ranked
                'avg_solve_s': round(avg_solve[student.id], 0) if avg_solve.get(student.id) else None,
                'attempts': attempts.get(student.id, 0),
                'last_status': latest[student.id].status if student.id in latest else None,
                'last_submitted_at': latest[student.id].submitted_at if student.id in latest else None,
                'behavioural_flags': b_flags.get(student.id, 0),
                'similarity_flags': sim_flags.get(student.id, 0),
                'points_withheld': withheld.get(student.id, 0),
                'integrity_status': ('withheld' if student.id in voided
                                     else 'under_review' if student.id in reviewing else None),
                'case_key': case_of.get(student.id),
            })

        # best rank first; within a shared rank, the faster average solve first; the unranked last
        student_stats.sort(key=lambda x: (x['rank'] is None, x['rank'] or 0, x['avg_solve_s'] or 999999))

        payload['students'] = student_stats
        return Response(payload)


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

        # ── Share of submissions that failed (each still ran a container) ────
        failed_pct = metrics.pct(len(failed_subs), total_subs)
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

        if failed_pct is not None and failed_pct > 50:
            suggestions.append({
                'type': 'medium',
                'title': 'Failing submissions inflating costs',
                'detail': f'{failed_pct}% of submissions did not pass. Each failure still runs a full container. Better question scoping or difficulty calibration would reduce wasteful executions.',
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
            'detail': f'Every new worker node pulls 200MB+ language images before execution. Image pre-caching eliminates this latency and reduces cold start from ~{round(_COLD_START_MS / 1000)}s to ~200ms.',
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

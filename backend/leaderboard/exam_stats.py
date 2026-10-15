"""Per-exam results for one student: the numbers behind My results and the weekly
recommendation. Rates, points and ranks come from analytics.metrics so they match
every other page."""
from analytics import metrics
from submissions.models import Submission


def student_exam_stats(student):
    """One dict per exam the student has submitted to, newest exam first.

    Each exam lists every one of its questions, attempted or not, with the
    student's attempt count and the attempt number that first passed (if any).
    Attempts leave out 'error' submissions: they are refunded, as on the exam page."""
    from exams.models import Exam, ExamEnrollment, results_final_at

    all_mine = Submission.objects.filter(student=student)
    # passed = solved at least half; a question voided for confirmed plagiarism is not solved
    my_results = {r['exam_id']: r for r in metrics.exam_results(all_mine)}
    # points lost to confirmed plagiarism, per question: already out of the points and rank below
    withheld = {qid: pts for (_, qid), pts in metrics.withheld_points(all_mine).items()}

    # question_id -> {'attempts', 'first_status', 'passed_on'} from the student's own submissions
    per_question = {}
    for q_id, attempt, status in all_mine.order_by('question_id', 'attempt_number').values_list(
        'question_id', 'attempt_number', 'status'
    ):
        row = per_question.setdefault(q_id, {'attempts': 0, 'first_status': status, 'passed_on': None})
        if status != 'error':
            row['attempts'] += 1
        if status == 'passed' and row['passed_on'] is None:
            row['passed_on'] = attempt

    exam_ids = all_mine.order_by().values_list('exam_id', flat=True).distinct()
    finished = dict(ExamEnrollment.objects.filter(student=student).values_list('exam_id', 'finished_at'))
    from support.integrity import integrity_outcomes
    integrity = integrity_outcomes(student.id)   # the trainer's decision on each exam, if any
    out = []
    for exam in Exam.objects.filter(id__in=list(exam_ids)).prefetch_related('questions'):
        questions = sorted(exam.questions.all(), key=lambda q: q.id)

        # Rank the section's students who TOOK this exam by points earned in it, then faster average
        # solve (the exam report's rule); no points on it is "Not ranked" (metrics.exam_standing)
        section_subs = metrics.student_submissions(Submission.objects.filter(exam=exam, student__cohort=student.cohort))
        took = section_subs.order_by().values_list('student_id', flat=True).distinct()
        exam_scores = metrics.scores_for(took, section_subs)
        standing = metrics.exam_standing(exam_scores, student.id, metrics.solve_times(section_subs))

        result = my_results.get(exam.id, {'solved': 0, 'voided': 0, 'passed': False})

        q_rows = []
        for q in questions:
            mine = per_question.get(q.id)
            if not mine or not mine['attempts']:   # only refunded errors: never attempted
                state = 'not_attempted'
            elif mine['passed_on']:
                state = 'passed'
            else:
                state = 'failed'
            q_rows.append({
                'question_id': q.id,
                'title': q.title,
                'difficulty': q.difficulty,
                'points': q.points,
                'points_withheld': withheld.get(q.id, 0),
                'voided': q.id in withheld,   # tests passed, but not counted as solved: plagiarism confirmed
                'attempts': mine['attempts'] if mine else 0,
                'passed_on': mine['passed_on'] if mine else None,
                'status': state,
            })

        out.append({
            'exam_id': exam.id,
            'exam_title': exam.title,
            'exam_date': exam.start_time or exam.created_at,
            'questions_total': len(questions),
            'questions_solved': result['solved'],    # counted: voided questions left out
            'questions_voided': result['voided'],    # solved, but not counted: plagiarism confirmed
            'passed': result['passed'],   # this exam's pass/fail: what the success rate counts
            'points': exam_scores.get(student.id, 0),
            'points_available': sum(q.points for q in questions),
            'points_withheld': sum(withheld.get(q.id, 0) for q in questions),
            'attempts': all_mine.filter(exam=exam).exclude(status='error').count(),
            'rank': standing['rank'],          # None: no points on this exam, not ranked
            'cohort_size': standing['size'],   # students in the section who took this exam
            # the trainer's integrity decision here ({outcome, points_withheld, appeal, can_appeal}) or None
            'integrity': integrity.get(exam.id),
            'questions': q_rows,
            # the AI summary is written only once these results are final (see ai.tasks.generate_exam_summary)
            'summary_ready': results_final_at(exam, finished.get(exam.id)) is not None,
        })

    out.sort(key=lambda e: e['exam_date'], reverse=True)
    return out

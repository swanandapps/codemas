"""Async AI tasks. Every task here is best-effort and isolated from the core
result-delivery pipeline — failures are logged and swallowed, never re-raised
into the path that delivers pass/fail to the student.
"""
import logging
from celery import shared_task
from django.apps import apps

from .llm import call_json, LLMUnavailable

logger = logging.getLogger(__name__)


RUBRIC_SYSTEM_PROMPT = (
    "You are a senior software engineer grading a coding-exam submission. "
    "Score the submission on four dimensions, each an INTEGER from 0 to 2 "
    "(0 = poor, 1 = adequate, 2 = excellent):\n"
    "- correctness: does the code produce correct results? Judge this PRIMARILY "
    "on the TEST RESULTS provided. If all test cases pass, correctness is 2; if "
    "most pass, 1; if few or none pass, 0. Do NOT lower correctness just because "
    "the algorithm differs from a suggested technique — that belongs under approach.\n"
    "- code_quality: readability, naming, and structure\n"
    "- approach: how optimal or well-reasoned the algorithm is. You may note here "
    "(not under correctness) if a specifically requested technique was not used, but "
    "a correct, efficient alternative still deserves partial or full credit.\n"
    "- edge_cases: how well boundary conditions are handled\n"
    "Each dimension needs a single-sentence justification. Also give 2-3 "
    "sentences of overall, constructive feedback addressed to the student. Keep "
    "the tone fair: passing all tests is a strong result, even if the approach "
    "differs from what was suggested.\n"
    "Respond ONLY with a JSON object of this exact shape:\n"
    "{\n"
    '  "correctness": {"score": <0-2>, "note": "<one sentence>"},\n'
    '  "code_quality": {"score": <0-2>, "note": "<one sentence>"},\n'
    '  "approach": {"score": <0-2>, "note": "<one sentence>"},\n'
    '  "edge_cases": {"score": <0-2>, "note": "<one sentence>"},\n'
    '  "overall_feedback": "<2-3 sentences>"\n'
    "}"
)


def _clamp_score(value):
    """Coerce the model's score into a valid 0-2 integer, defensively."""
    try:
        return max(0, min(2, int(value)))
    except (TypeError, ValueError):
        return 0


@shared_task
def score_rubric(submission_id):
    """Generate and store a rubric score for one submission. Runs after delivery."""
    Submission = apps.get_model('submissions', 'Submission')
    Result = apps.get_model('results', 'Result')
    RubricScore = apps.get_model('ai', 'RubricScore')

    submission = Submission.objects.filter(pk=submission_id).select_related('question').first()
    if not submission:
        logger.warning('score_rubric: submission %s not found', submission_id)
        return

    # Idempotent — never double-score (e.g. retried task or re-run).
    if RubricScore.objects.filter(submission_id=submission_id).exists():
        return

    results = list(Result.objects.filter(submission=submission))
    passed = sum(1 for r in results if r.passed)
    total = len(results)

    user_prompt = (
        f"QUESTION:\n{submission.question.title}\n{submission.question.description}\n\n"
        f"LANGUAGE: {submission.language}\n\n"
        f"TEST RESULTS: {passed}/{total} test cases passed.\n\n"
        f"STUDENT CODE:\n{submission.code}"
    )

    try:
        data = call_json(RUBRIC_SYSTEM_PROMPT, user_prompt)
    except LLMUnavailable as e:
        # No key / provider down — skip silently. Core pipeline is unaffected.
        logger.info('score_rubric: skipped submission %s (%s)', submission_id, e)
        return

    try:
        from .llm import DEFAULT_MODEL
        RubricScore.objects.create(
            submission=submission,
            correctness_score=_clamp_score(data['correctness']['score']),
            correctness_note=data['correctness']['note'],
            code_quality_score=_clamp_score(data['code_quality']['score']),
            code_quality_note=data['code_quality']['note'],
            approach_score=_clamp_score(data['approach']['score']),
            approach_note=data['approach']['note'],
            edge_case_score=_clamp_score(data['edge_cases']['score']),
            edge_case_note=data['edge_cases']['note'],
            overall_feedback=data['overall_feedback'],
            model_used=DEFAULT_MODEL,
        )
        logger.info('score_rubric: stored rubric for submission %s', submission_id)
    except (KeyError, TypeError) as e:
        # Malformed model output — log and move on, don't poison the pipeline.
        logger.warning('score_rubric: bad LLM payload for %s: %s', submission_id, e)


HINT_SYSTEM_PROMPT = (
    "You are a patient coding tutor helping a student who just failed a test case. "
    "Give a SINGLE Socratic hint that nudges them toward the fix WITHOUT revealing "
    "the answer or writing any code. Point at the concept or approach they are "
    "missing. Keep it to 1-3 sentences in an encouraging tone.\n"
    "Respond ONLY with a JSON object: {\"hint\": \"<your hint>\"}"
)


@shared_task
def generate_hint(submission_id):
    """Generate and store a Socratic hint for a FAILED submission. Runs after delivery."""
    Submission = apps.get_model('submissions', 'Submission')
    Result = apps.get_model('results', 'Result')
    AIHint = apps.get_model('ai', 'AIHint')

    submission = Submission.objects.filter(pk=submission_id).select_related('question').first()
    if not submission:
        logger.warning('generate_hint: submission %s not found', submission_id)
        return

    # Only failed submissions get hints — passing ones never trigger this.
    if submission.status != 'failed':
        return

    # Idempotent — never regenerate (so a page refresh keeps the same hint).
    if AIHint.objects.filter(submission_id=submission_id).exists():
        return

    failed = Result.objects.filter(submission=submission, passed=False).select_related('test_case').first()
    if not failed:
        return  # nothing concrete to hint about

    # The hint is shown to the student, so a hidden test's input/expected output
    # never goes into the prompt (the model could echo it back).
    if failed.test_case.is_hidden:
        case_lines = "  (hidden test: its input and expected output are secret; do not guess them)\n"
    else:
        case_lines = (f"  input: {failed.test_case.input_data}\n"
                      f"  expected output: {failed.test_case.expected_output}\n")
    user_prompt = (
        f"QUESTION:\n{submission.question.title}\n{submission.question.description}\n\n"
        f"LANGUAGE: {submission.language}\n\n"
        f"FAILED TEST CASE:\n"
        + case_lines
        + f"  student's output: {failed.actual_output}\n"
        + (f"  error: {failed.error_message}\n" if failed.error_message else "")
        + f"\nSTUDENT CODE:\n{submission.code}"
    )

    try:
        data = call_json(HINT_SYSTEM_PROMPT, user_prompt)
    except LLMUnavailable as e:
        logger.info('generate_hint: skipped submission %s (%s)', submission_id, e)
        return

    hint_text = (data.get('hint') or '').strip() if isinstance(data, dict) else ''
    if not hint_text:
        logger.warning('generate_hint: empty hint for submission %s', submission_id)
        return

    from .llm import DEFAULT_MODEL
    AIHint.objects.create(submission=submission, hint=hint_text, model_used=DEFAULT_MODEL)
    logger.info('generate_hint: stored hint for submission %s', submission_id)


PLAGIARISM_SYSTEM_PROMPT = (
    "You are a plagiarism-review assistant for a coding exam. Two submissions "
    "were flagged as similar by an automated engine. Explain, for a human "
    "trainer, WHY this pair looks suspicious. Be concrete and cite specific "
    "evidence from the code and the behavioural signals provided. This is "
    "EVIDENCE, not a verdict — the trainer decides.\n"
    "Respond ONLY with a JSON object of this exact shape:\n"
    "{\n"
    '  "summary": "<one sentence on why this pair is suspicious>",\n'
    '  "matches": ["<concrete observation>", "<concrete observation>"],\n'
    '  "confidence": "low" | "medium" | "high"\n'
    "}\n"
    "Provide 2-3 items in matches. Base confidence on how strongly the code "
    "similarity AND behavioural signals combine."
)


def _behaviour_summary(submission):
    """Compact, human-readable behavioural signals for one submission."""
    parts = [
        f"paste: {'yes' if submission.had_paste_event else 'no'} "
        f"({submission.paste_char_count} chars)",
        f"time to complete: {submission.time_to_complete_seconds}s",
        f"tab switches: {submission.tab_switch_count}",
    ]
    flag = getattr(submission, 'behavioural_flag', None)
    if flag is not None:
        parts.append(f"behavioural risk: {flag.risk_score:.2f} "
                     f"({flag.confidence} confidence of misconduct)")
        if flag.signals_triggered:
            parts.append("signals: " + "; ".join(flag.signals_triggered))
    return " | ".join(parts)


@shared_task
def explain_plagiarism(flag_id):
    """Generate and store a natural-language explanation for one flagged pair."""
    PlagiarismFlag = apps.get_model('plagiarism', 'PlagiarismFlag')
    PlagiarismExplanation = apps.get_model('ai', 'PlagiarismExplanation')

    flag = (
        PlagiarismFlag.objects
        .filter(pk=flag_id)
        .select_related(
            'submission_1', 'submission_1__question', 'submission_1__behavioural_flag',
            'submission_2', 'submission_2__question', 'submission_2__behavioural_flag',
        )
        .first()
    )
    if not flag:
        logger.warning('explain_plagiarism: flag %s not found', flag_id)
        return

    # Idempotent — never re-explain the same pair.
    if PlagiarismExplanation.objects.filter(flag_id=flag_id).exists():
        return

    a = flag.submission_1
    b = flag.submission_2
    question = a.question

    user_prompt = (
        f"QUESTION:\n{question.title}\n{question.description}\n\n"
        f"SIMILARITY SCORE: {flag.similarity_score:.2f} (threshold-flagged)\n\n"
        f"SUBMISSION A — {a.student.username} ({a.language})\n"
        f"behavioural signals: {_behaviour_summary(a)}\n"
        f"code:\n{a.code}\n\n"
        f"SUBMISSION B — {b.student.username} ({b.language})\n"
        f"behavioural signals: {_behaviour_summary(b)}\n"
        f"code:\n{b.code}"
    )

    try:
        data = call_json(PLAGIARISM_SYSTEM_PROMPT, user_prompt)
    except LLMUnavailable as e:
        logger.info('explain_plagiarism: skipped flag %s (%s)', flag_id, e)
        return

    if not isinstance(data, dict) or not data.get('summary'):
        logger.warning('explain_plagiarism: bad LLM payload for flag %s', flag_id)
        return

    confidence = str(data.get('confidence', 'low')).lower()
    if confidence not in ('low', 'medium', 'high'):
        confidence = 'low'
    matches = data.get('matches') or []
    if not isinstance(matches, list):
        matches = [str(matches)]

    from .llm import DEFAULT_MODEL
    PlagiarismExplanation.objects.create(
        flag=flag,
        summary=data['summary'],
        matches=matches,
        confidence=confidence,
        model_used=DEFAULT_MODEL,
    )
    logger.info('explain_plagiarism: stored explanation for flag %s', flag_id)


EXAM_SUMMARY_SYSTEM_PROMPT = (
    "You are a coding instructor writing a short, encouraging performance summary "
    "for a student about how they did across one exam. Use the per-question "
    "outcomes and rubric scores provided. Write 3-4 sentences addressed to the "
    "student ('you'): note overall performance, a clear strength, and one concrete "
    "area to improve. Be specific and constructive, not generic.\n"
    "The input ends with the exam's integrity outcome. If points were withheld after a "
    "plagiarism review, say so neutrally in one sentence (e.g. '20 points were withheld "
    "after a plagiarism review'), without judging or speculating. Never praise a score, "
    "solution or question whose points were withheld. If a decision was overturned, the "
    "points count as normal. Do not mention the integrity outcome when there is none.\n"
    "The Result line is the exam's outcome: a question not counted for plagiarism is not "
    "solved, so never call it solved or call the exam passed when the line says not passed.\n"
    "Respond ONLY with a JSON object: {\"summary\": \"<3-4 sentences>\"}"
)


def result_line(result):
    """The exam's outcome in plain words, from a metrics.exam_results row: the pass rule over the
    counted solves, and why any solved question did not count (confirmed plagiarism)."""
    line = (f"{'passed' if result['passed'] else 'not passed'}: solved {result['solved']} "
            f"of {result['total']} questions (at least half passes)")
    if result['voided']:
        n = result['voided']
        line += (f"; {n} solved question{'s' if n != 1 else ''} not counted: "
                 f"plagiarism confirmed by the trainer")
    return line


def integrity_line(outcome):
    """The exam summary's last input line: the student's integrity outcome on the exam
    (support.integrity.integrity_outcomes), in plain words."""
    if not outcome:
        return 'Integrity: no plagiarism decision on this exam.'
    appeal = {
        'open': ' The student has appealed; the appeal is under review.',
        'upheld': ' The student appealed and the decision was upheld.',
    }.get(outcome['appeal'], '')
    kind = outcome['outcome']
    if kind == 'withheld':
        line = (f"{outcome['points_withheld']} points withheld after a plagiarism review confirmed by "
                f"the trainer; the score already leaves them out.")
    elif kind == 'overturned':
        line = 'A plagiarism decision on this exam was overturned on appeal: every point counts as normal.'
    elif kind == 'confirmed':
        line = 'The trainer confirmed a plagiarism finding on this exam; no points were withheld.'
    else:
        line = 'The trainer reviewed this exam for plagiarism and took no action.'
    return f'Integrity: {line}{appeal}'


def forget_exam_summaries(student_ids, exam_id):
    """Delete these students' stored summaries of the exam, so each is rewritten on its next
    view. Called whenever their integrity outcome there changes: a flag review (confirm or
    dismiss), an appeal filed, upheld or overturned."""
    ExamSummary = apps.get_model('ai', 'ExamSummary')
    ExamSummary.objects.filter(student_id__in=list(student_ids), exam_id=exam_id).delete()


def exam_summary_final_at(student_id, exam):
    """When the student's results on the exam became final (they submitted it, or it ended);
    None while they can still submit, so no summary is written yet."""
    from exams.models import ExamEnrollment, results_final_at
    finished_at = (ExamEnrollment.objects.filter(exam=exam, student_id=student_id)
                   .values_list('finished_at', flat=True).first())
    return results_final_at(exam, finished_at)


def generate_exam_summary(student_id, exam_id):
    """Generate and store an exam-level summary for one student. Returns the
    ExamSummary instance, or None if unavailable (results not final yet, no key,
    provider error).

    Written only once the results are final (the student submitted the exam or it
    ended), so it never freezes a mid-exam picture. A row written before that
    (by an older version) is rewritten.

    Safe to call inline from a view (synchronous) or as a Celery task.
    """
    Submission = apps.get_model('submissions', 'Submission')
    RubricScore = apps.get_model('ai', 'RubricScore')
    ExamSummary = apps.get_model('ai', 'ExamSummary')
    Exam = apps.get_model('exams', 'Exam')

    exam = Exam.objects.filter(pk=exam_id).first()
    if not exam:
        return None
    final_at = exam_summary_final_at(student_id, exam)
    if final_at is None:
        return None

    existing = ExamSummary.objects.filter(student_id=student_id, exam_id=exam_id).first()
    if existing and existing.created_at >= final_at:
        return existing

    subs = (
        Submission.objects
        .filter(student_id=student_id, exam_id=exam_id)
        .select_related('question').order_by('question_id', 'attempt_number')
    )
    if not subs:
        return None

    rubric_by_sub = {
        r.submission_id: r
        for r in RubricScore.objects.filter(submission__in=subs)
    }
    from analytics import metrics
    from support.integrity import integrity_outcomes
    withheld_qs = {qid for _, qid in metrics.withheld_points(subs)}
    outcome = integrity_outcomes(student_id, [exam_id]).get(exam_id)
    result = next(iter(metrics.exam_results(subs)), None)   # counted solves: voided questions left out

    lines = []
    for s in subs:
        line = f"- {s.question.title} (attempt {s.attempt_number}): {s.status}"
        if s.status == 'passed' and s.question_id in withheld_qs:
            line += ', points withheld (plagiarism confirmed)'
        r = rubric_by_sub.get(s.id)
        if r:
            line += (
                f"; rubric {r.total_score}/8 "
                f"(correctness {r.correctness_score}, quality {r.code_quality_score}, "
                f"approach {r.approach_score}, edge {r.edge_case_score})"
            )
        lines.append(line)

    user_prompt = (
        f"EXAM: {exam.title}\n\n"
        f"This student's submissions and rubric scores:\n" + "\n".join(lines)
        + (f"\n\nResult: {result_line(result)}." if result else '')
        + f"\n\n{integrity_line(outcome)}"
    )

    try:
        data = call_json(EXAM_SUMMARY_SYSTEM_PROMPT, user_prompt)
    except LLMUnavailable as e:
        logger.info('generate_exam_summary: skipped student %s exam %s (%s)', student_id, exam_id, e)
        return None

    summary_text = (data.get('summary') or '').strip() if isinstance(data, dict) else ''
    if not summary_text:
        return None

    from .llm import DEFAULT_MODEL
    if existing:
        existing.delete()   # written before the results were final; created_at must restamp
    obj, _ = ExamSummary.objects.get_or_create(
        student_id=student_id, exam_id=exam_id,
        defaults={'summary': summary_text, 'model_used': DEFAULT_MODEL},
    )
    return obj


@shared_task
def exam_summary_task(student_id, exam_id):
    """Celery wrapper so summaries can also be pre-generated in the background."""
    generate_exam_summary(student_id, exam_id)


EXAM_GEN_SYSTEM_PROMPT = (
    "You are an expert coding-exam author. Generate a coding exam as JSON. "
    "Every question must be solvable in the requested language by reading from "
    "stdin and printing to stdout. Write each description as plain text (no markdown) "
    "in this layout, each label starting its own line:\n"
    "<problem statement: 1-3 short paragraphs, separated by a blank line>\n"
    "Input format:\n<one line per stdin line, e.g. 'Line 1: an integer n, the array length'>\n"
    "Output format:\n<exactly what to print, e.g. 'Two indices separated by a space'>\n"
    "Constraints:\n<one constraint per line, e.g. '1 <= n <= 1000'>\n"
    "Do not put examples in the description: the first test case is shown to students "
    "as the example, so make it a typical, easy-to-follow case. Each question needs exactly 3 test "
    "cases with concrete input_data and the EXACT expected_output a correct "
    "program would print (no trailing prose). Keep inputs simple and "
    "unambiguous, and make the 3 test cases exercise different behaviour so a buggy "
    "solution fails at least one: a typical case, a boundary case (e.g. the answer at the "
    "first or last position, or a single-element input) and a negative case (e.g. the "
    "target is absent) where the problem allows.\n"
    "Each question also needs starter code in BOTH JavaScript and Python, like HackerRank: "
    "it reads stdin exactly in the stated input format (JavaScript: "
    "require('fs').readFileSync(0, 'utf8'); Python: sys.stdin.read()), parses the values, "
    "defines ONE function with a descriptive name whose body is only a comment "
    "'Write your code here' plus what to return (Python body ends with pass), then prints "
    "the function's return value in the exact output format. Students write only the body.\n"
    "Respond ONLY with a JSON object of this exact shape:\n"
    "{\n"
    '  "title": "<exam title>",\n'
    '  "description": "<one-line exam description>",\n'
    '  "questions": [\n'
    '    {\n'
    '      "title": "<question title>",\n'
    '      "description": "<statement, then Input format / Output format / Constraints lines>",\n'
    '      "difficulty": "easy" | "medium" | "hard",\n'
    '      "test_cases": [ {"input_data": "<stdin>", "expected_output": "<stdout>"} ],\n'
    '      "starter_code": {"javascript": "<starter code>", "python": "<starter code>"}\n'
    '    }\n'
    "  ]\n"
    "}"
)


def _draft_questions(data):
    """The draft's question list. The model sometimes answers with ONE question flattened into the
    exam itself (test_cases at the top level, no "questions"); that counts as a one-question list."""
    questions = data.get('questions') if isinstance(data, dict) else None
    if isinstance(questions, list) and questions:
        return [q for q in questions if isinstance(q, dict)]
    if isinstance(data, dict) and data.get('test_cases'):
        return [data]
    return []


def generate_exam_draft(topic, language, num_questions, difficulty):
    """Return a draft exam dict from GPT. Does NOT persist anything.

    Raises LLMUnavailable if no key / provider error so the view can 503.
    """
    num_questions = max(1, min(10, int(num_questions)))
    user_prompt = (
        f"Topic: {topic}\n"
        f"Language: {language}\n"
        f"Number of questions: {num_questions}\n"
        f"Overall difficulty: {difficulty}\n"
        f"Each question must have exactly 3 test cases."
    )
    data = call_json(EXAM_GEN_SYSTEM_PROMPT, user_prompt)
    if not _draft_questions(data):
        # Seen in prod: some topics come back with no question list. Ask once more, saying what was missing.
        data = call_json(EXAM_GEN_SYSTEM_PROMPT, user_prompt + (
            f'\nYour last answer had no questions. Return the JSON shape above with a "questions" '
            f'list of exactly {num_questions} question(s).'))

    # Normalize defensively so the frontend always gets a consistent shape.
    questions = []
    for q in _draft_questions(data)[:num_questions]:
        diff = str(q.get('difficulty', difficulty)).lower()
        if diff not in ('easy', 'medium', 'hard'):
            diff = 'medium'
        # The first case is a visible sample so students see the I/O format; the rest stay hidden.
        tcs = [
            {'input_data': str(tc.get('input_data', '')), 'expected_output': str(tc.get('expected_output', '')),
             'is_hidden': i > 0}
            for i, tc in enumerate(q.get('test_cases') or [])
        ]
        questions.append({
            'title': str(q.get('title', 'Untitled question'))[:300],
            'description': str(q.get('description', '')),
            'language': language,
            'difficulty': diff,
            'test_cases': tcs,
            'starter_code': {
                lang: str((q.get('starter_code') or {}).get(lang) or '')
                for lang in ('javascript', 'python')
            },
        })

    return {
        'title': str(data.get('title', topic))[:200],
        'description': str(data.get('description', '')),
        'questions': questions,
    }


# ── Weekly recommendation ─────────────────────────────────────────────────────

WEEKLY_RECOMMENDATION_SYSTEM_PROMPT = (
    "You are a coding coach writing a weekly study recommendation for one student. "
    "You get the numbers from ALL of their exams together. Rules:\n"
    "- Base every claim on the supplied numbers. Never invent a question, score or trend.\n"
    "- A question counts as 'first try' ONLY if it is listed under passed_first_try. "
    "Questions under passed_after_retries took more than one attempt.\n"
    "- Each card's text must agree with its evidence; the evidence quotes the input as given.\n"
    "- Name the specific questions, exams and topics. The headline must name at least one; "
    "no generic phrases like 'focus on your strengths' or 'practise more'.\n"
    "- Do not mention any programming tool, library, company, product or AI model by name.\n"
    "- Address the student as 'you'. Keep each card to 1-2 sentences.\n"
    "Write a one-sentence headline and three cards:\n"
    "- keep: a habit or strength the numbers show they should keep doing;\n"
    "- work: the most important weakness to work on;\n"
    "- next: one concrete next step for this week.\n"
    "Each card has 'text' (the advice) and 'evidence' (a short line quoting the real "
    "numbers it is based on, e.g. 'Two Sum: passed on attempt 1 in Arrays Basics').\n"
    "Respond ONLY with a JSON object of this exact shape:\n"
    "{\n"
    '  "headline": "<one sentence>",\n'
    '  "keep": {"text": "<1-2 sentences>", "evidence": "<short line>"},\n'
    '  "work": {"text": "<1-2 sentences>", "evidence": "<short line>"},\n'
    '  "next": {"text": "<1-2 sentences>", "evidence": "<short line>"}\n'
    "}"
)

WEEKLY_CARD_KINDS = ('keep', 'work', 'next')


def current_week_start():
    """Monday of the current week in India time (the recommendation's week key)."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from django.utils import timezone
    today = timezone.now().astimezone(ZoneInfo('Asia/Kolkata')).date()
    return today - timedelta(days=today.weekday())


def weekly_recommendation_input(student):
    """The numbers the model sees: every exam with at least one graded attempt.
    The result line uses the success-rate pass rule (at least half the questions solved, a
    question voided for confirmed plagiarism not counted) and says when one was not counted.

    Questions are pre-sorted into outcome lists so the model never has to work out
    "first try" itself. Failed first time = passed_after_retries + not_passed;
    still unsolved = not_passed + not_attempted."""
    from analytics import metrics
    from leaderboard.exam_stats import student_exam_stats
    graded = set(
        student.submissions.filter(status__in=metrics.GRADED_STATUSES).values_list('exam_id', flat=True)
    )
    exams = []
    for e in reversed(student_exam_stats(student)):  # oldest first, so trends read in order
        if e['exam_id'] not in graded:
            continue  # nothing graded yet in this exam
        qs = e['questions']
        exams.append({
            'exam': e['exam_title'],
            'score': f"{e['points']} / {e['points_available']} points",
            'result': result_line({'passed': e['passed'], 'solved': e['questions_solved'],
                                   'total': e['questions_total'], 'voided': e['questions_voided']}),
            'rank': f"{e['rank']} of {e['cohort_size']}" if e['rank'] else 'not ranked (no points on this exam)',
            'passed_first_try': [f"{q['title']} ({q['difficulty']})"
                                 for q in qs if q['passed_on'] == 1],
            'passed_after_retries': [f"{q['title']} ({q['difficulty']}): passed on attempt {q['passed_on']}"
                                     for q in qs if q['passed_on'] and q['passed_on'] > 1],
            'not_passed': [f"{q['title']} ({q['difficulty']}): {q['attempts']} attempts, never passed"
                           for q in qs if q['status'] == 'failed'],
            'not_attempted': [f"{q['title']} ({q['difficulty']})"
                              for q in qs if q['status'] == 'not_attempted'],
        })
    return exams


def generate_weekly_recommendation(student_id, week_start=None):
    """Write (or reuse) this week's recommendation for one student.

    Returns the WeeklyRecommendation, or None when the student has no graded exam or
    the model call fails (the page then keeps showing the last good one).
    Idempotent per (student, week). If the numbers have not changed since the last
    recommendation, it is carried forward without another model call.
    """
    import hashlib
    import json
    User = apps.get_model('accounts', 'User')
    WeeklyRecommendation = apps.get_model('ai', 'WeeklyRecommendation')

    student = User.objects.filter(pk=student_id).first()
    if not student:
        return None
    week_start = week_start or current_week_start()

    existing = WeeklyRecommendation.objects.filter(student=student, week_start=week_start).first()
    if existing:
        return existing

    exams = weekly_recommendation_input(student)
    if not exams:
        return None
    payload = json.dumps(exams, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()

    from .llm import DEFAULT_MODEL
    latest = WeeklyRecommendation.objects.filter(student=student).first()
    if latest and latest.input_digest == digest:
        obj, _ = WeeklyRecommendation.objects.get_or_create(
            student=student, week_start=week_start,
            defaults={'headline': latest.headline, 'cards': latest.cards,
                      'input_digest': digest, 'model_used': latest.model_used},
        )
        return obj

    try:
        data = call_json(WEEKLY_RECOMMENDATION_SYSTEM_PROMPT, f"STUDENT'S EXAMS (JSON):\n{payload}")
    except LLMUnavailable as e:
        logger.info('weekly_recommendation: skipped student %s (%s)', student_id, e)
        return None

    try:
        headline = str(data['headline']).strip()
        cards = [
            {'kind': k, 'text': str(data[k]['text']).strip(), 'evidence': str(data[k].get('evidence', '')).strip()}
            for k in WEEKLY_CARD_KINDS
        ]
    except (KeyError, TypeError, AttributeError) as e:
        logger.warning('weekly_recommendation: bad LLM payload for student %s: %s', student_id, e)
        return None
    if not headline or not all(c['text'] for c in cards):
        logger.warning('weekly_recommendation: empty fields for student %s', student_id)
        return None

    obj, _ = WeeklyRecommendation.objects.get_or_create(
        student=student, week_start=week_start,
        defaults={'headline': headline, 'cards': cards, 'input_digest': digest, 'model_used': DEFAULT_MODEL},
    )
    return obj


def weekly_recommendation_students():
    """Students with at least one graded attempt."""
    from analytics import metrics
    return (
        metrics.students()
        .filter(submissions__status__in=metrics.GRADED_STATUSES)
        .distinct().order_by('id')
    )


@shared_task
def weekly_recommendations_task():
    """Celery beat, Monday morning IST: one recommendation per student with a graded exam."""
    week_start = current_week_start()
    made = 0
    for student_id in weekly_recommendation_students().values_list('id', flat=True):
        try:
            if generate_weekly_recommendation(student_id, week_start):
                made += 1
        except Exception:  # one student's failure must not stop the rest
            logger.exception('weekly_recommendation: failed for student %s', student_id)
    logger.info('weekly_recommendations_task: %s recommendations for week %s', made, week_start)
    return made

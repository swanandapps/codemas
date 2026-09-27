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

    user_prompt = (
        f"QUESTION:\n{submission.question.title}\n{submission.question.description}\n\n"
        f"LANGUAGE: {submission.language}\n\n"
        f"FAILED TEST CASE:\n"
        f"  input: {failed.test_case.input_data}\n"
        f"  expected output: {failed.test_case.expected_output}\n"
        f"  student's output: {failed.actual_output}\n"
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
        parts.append(f"behavioural risk: {flag.risk_score:.2f} ({flag.confidence})")
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
    "Respond ONLY with a JSON object: {\"summary\": \"<3-4 sentences>\"}"
)


def generate_exam_summary(student_id, exam_id):
    """Generate and store an exam-level summary for one student. Returns the
    ExamSummary instance, or None if unavailable (no key / provider error).

    Safe to call inline from a view (synchronous) or as a Celery task.
    """
    Submission = apps.get_model('submissions', 'Submission')
    RubricScore = apps.get_model('ai', 'RubricScore')
    ExamSummary = apps.get_model('ai', 'ExamSummary')
    Exam = apps.get_model('exams', 'Exam')

    existing = ExamSummary.objects.filter(student_id=student_id, exam_id=exam_id).first()
    if existing:
        return existing

    exam = Exam.objects.filter(pk=exam_id).first()
    if not exam:
        return None

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

    lines = []
    for s in subs:
        line = f"- {s.question.title} (attempt {s.attempt_number}): {s.status}"
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
    "stdin and printing to stdout. The description MUST state the exact input "
    "format (per line) and output format. Each question needs exactly 3 test "
    "cases with concrete input_data and the EXACT expected_output a correct "
    "program would print (no trailing prose). Keep inputs simple and "
    "unambiguous.\n"
    "Respond ONLY with a JSON object of this exact shape:\n"
    "{\n"
    '  "title": "<exam title>",\n'
    '  "description": "<one-line exam description>",\n'
    '  "questions": [\n'
    '    {\n'
    '      "title": "<question title>",\n'
    '      "description": "<problem statement incl. input/output format>",\n'
    '      "difficulty": "easy" | "medium" | "hard",\n'
    '      "test_cases": [ {"input_data": "<stdin>", "expected_output": "<stdout>"} ]\n'
    '    }\n'
    "  ]\n"
    "}"
)


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

    # Normalize defensively so the frontend always gets a consistent shape.
    questions = []
    for q in (data.get('questions') or [])[:num_questions]:
        diff = str(q.get('difficulty', difficulty)).lower()
        if diff not in ('easy', 'medium', 'hard'):
            diff = 'medium'
        tcs = [
            {'input_data': str(tc.get('input_data', '')), 'expected_output': str(tc.get('expected_output', ''))}
            for tc in (q.get('test_cases') or [])
        ]
        questions.append({
            'title': str(q.get('title', 'Untitled question'))[:300],
            'description': str(q.get('description', '')),
            'language': language,
            'difficulty': diff,
            'test_cases': tcs,
        })

    return {
        'title': str(data.get('title', topic))[:200],
        'description': str(data.get('description', '')),
        'questions': questions,
    }

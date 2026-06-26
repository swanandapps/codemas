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
    "- correctness: how well the code solves the problem and passes the tests\n"
    "- code_quality: readability, naming, and structure\n"
    "- approach: how optimal or well-reasoned the algorithm is\n"
    "- edge_cases: how well boundary conditions are handled\n"
    "Each dimension needs a single-sentence justification. Also give 2-3 "
    "sentences of overall, constructive feedback addressed to the student.\n"
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

"""The execute_submission job kind: what a claim hands over and how a completion is recorded."""
from django.db import transaction

from results.models import Result
from submissions.models import Submission

LIMITS = {'timeout_s': 10, 'python_memory_mb': 256, 'node_heap_mb': 192, 'output_kb': 64}


def payload_for(submission):
    """What a claim hands the executor. No expected outputs: they never leave Django (apply_result
    compares), so student code running beside the handler can't read the answers."""
    tests = list(submission.question.test_cases.order_by('id').values('id', 'input_data'))
    return {
        'submission_id': submission.id,
        'language': submission.language,
        'code': submission.code,
        'tests': [{'id': t['id'], 'input': t['input_data']} for t in tests],
        'limits': LIMITS,
    }


def apply_result(submission, results):
    """Write Result rows and the submission status. Same pass rule as the legacy executor:
    output.strip() == expected.strip(). Returns the new submission status."""
    expected = dict(submission.question.test_cases.values_list('id', 'expected_output'))
    if not expected:
        submission.status = 'error'
        submission.save(update_fields=['status'])
        return submission.status

    all_passed, total_ms = True, 0
    for r in results:
        if r['test_id'] not in expected:
            continue
        passed = (r.get('output') or '').strip() == expected[r['test_id']].strip()
        all_passed = all_passed and passed
        total_ms += int(r.get('ms') or 0)
        Result.objects.update_or_create(
            submission=submission, test_case_id=r['test_id'],
            defaults={'passed': passed, 'actual_output': r.get('output') or '',
                      'execution_time_ms': int(r.get('ms') or 0), 'error_message': r.get('error') or ''},
        )
    missing = set(expected) - {r['test_id'] for r in results}
    submission.status = 'passed' if all_passed and not missing else 'failed'
    submission.execution_time_ms = total_ms
    submission.save(update_fields=['status', 'execution_time_ms'])
    # robust: grading is already committed, so a side-effect failure is logged, not a 500 to the Lambda
    transaction.on_commit(lambda: after_grading(submission.id), robust=True)
    return submission.status


def after_grading(submission_id):
    """Same side effects the legacy Celery task (execution.tasks.execute_submission) runs after
    grading, minus its Redis publish: normalize, notify, then best-effort AI feedback."""
    from codemas.notifications import notify_result_ready
    from plagiarism.tasks import normalize_code
    sub = Submission.objects.select_related('student', 'question').get(pk=submission_id)
    sub.normalized_code = normalize_code(sub.code, sub.language)
    sub.save(update_fields=['normalized_code'])
    notify_result_ready(sub)
    # AI feedback is best-effort and must never affect grading. Separate guards, as in the
    # legacy task, so a failure queueing the rubric doesn't also drop the hint.
    try:
        from ai.tasks import score_rubric
        score_rubric.delay(sub.id)
    except Exception as e:
        print(f'[JOBS] could not queue rubric scoring for submission {sub.id}: {e}')
    if sub.status == 'failed':
        try:
            from ai.tasks import generate_hint
            generate_hint.delay(sub.id)
        except Exception as e:
            print(f'[JOBS] could not queue hint for submission {sub.id}: {e}')

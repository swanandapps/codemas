import os
from celery import shared_task
from django.apps import apps


@shared_task
def execute_submission(submission_id):
    Submission = apps.get_model('submissions', 'Submission')
    Result = apps.get_model('results', 'Result')

    print(f"[TASK] picked up submission_id={submission_id}")

    submission = Submission.objects.get(id=submission_id)
    submission.status = 'running'
    submission.save()
    print(f"[TASK] status set to running")

    test_cases = submission.question.test_cases.all()
    print(f"[TASK] found {test_cases.count()} test cases")
    all_passed = True

    for test_case in test_cases:
        print(f"[EXEC] running test_case_id={test_case.id} input={test_case.input_data!r}")
        # Local subprocess executor — legacy/dev path only. The sandboxed production path is the
        # job pipeline: jobs outbox → SQS → the codemas-exec Lambda (lambda/exec/).
        output, error, exec_time = run_local(
            code=submission.code,
            language=submission.language,
            input_data=test_case.input_data,
        )
        print(f"[EXEC] output={output!r} error={error!r} exec_time={exec_time}ms")

        passed = (output.strip() == test_case.expected_output.strip())
        print(f"[RESULT] passed={passed} expected={test_case.expected_output!r} got={output.strip()!r}")
        if not passed:
            all_passed = False

        Result.objects.create(
            submission=submission,
            test_case=test_case,
            passed=passed,
            actual_output=output,
            execution_time_ms=exec_time,
            error_message=error,
        )

    submission.status = 'passed' if all_passed else 'failed'
    from plagiarism.tasks import normalize_code
    submission.normalized_code = normalize_code(submission.code, submission.language)
    submission.save()

    print(f"[TASK] final status={submission.status}")

    from codemas.notifications import notify_result_ready
    notify_result_ready(submission)

    # ── AI features (async, best-effort) ──────────────────────────────────────
    # These fire AFTER the result is recorded above (the exam page polls /status/ for it). They run as separate Celery
    # tasks so they never sit on the sub-10s delivery path, and any failure here
    # must not affect the result the student already received.
    try:
        from ai.tasks import score_rubric
        score_rubric.delay(submission_id)  # rubric scoring on every submission
    except Exception as e:
        print(f"[AI] failed to enqueue rubric scoring: {e}")

    if submission.status == 'failed':
        try:
            from ai.tasks import generate_hint
            generate_hint.delay(submission_id)  # Socratic hint only on failed submissions
        except Exception as e:
            print(f"[AI] failed to enqueue hint generation: {e}")


def run_local(code, language, input_data):
    """Run student code as a local subprocess. DEV-ONLY executor.

    SECURITY: this runs untrusted code directly on the host with no sandbox. It
    exists so the pipeline works on a dev machine without Docker/Lambda. The
    production path is the job pipeline's codemas-exec Lambda (lambda/exec/:
    isolated, resource-capped).
    Do NOT use this in production.
    """
    import subprocess, tempfile, time as _time
    start = _time.time()
    timeout = 10
    # Children get no inherited env, so student code can't read DB/API secrets via os.environ
    env = {'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'), 'LANG': 'C.UTF-8'}
    sandbox = {'env': env}
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        # In the container we run as root: drop children to nobody so they can't read /proc/1/environ
        sandbox.update(user=65534, group=65534, extra_groups=[])

    def elapsed():
        return int((_time.time() - start) * 1000)

    # Input goes in as a temp file, not a pipe: code that reopens /dev/stdin (node's
    # readFileSync('/dev/stdin'), Python's open('/dev/stdin')) gets EACCES on a root-owned pipe once
    # the child runs as nobody. A world-readable file can be reopened by any user.
    stdin_file = tempfile.TemporaryFile('w+')
    os.fchmod(stdin_file.fileno(), 0o644)
    stdin_file.write(input_data or '')
    stdin_file.flush()

    def feed():
        stdin_file.seek(0)
        return {'stdin': stdin_file}

    try:
        if language == 'python':
            proc = subprocess.run(['python3', '-c', code], **feed(),
                                  capture_output=True, **sandbox, text=True, timeout=timeout)
        elif language == 'javascript':
            proc = subprocess.run(['node', '-e', code], **feed(),
                                  capture_output=True, **sandbox, text=True, timeout=timeout)
        elif language in ('cpp', 'java'):
            with tempfile.TemporaryDirectory() as d:
                os.chmod(d, 0o777)  # writable by the unprivileged child (compiler output)
                if language == 'cpp':
                    src = os.path.join(d, 'main.cpp')
                    with open(src, 'w') as f:
                        f.write(code)
                    comp = subprocess.run(['g++', '-O2', '-o', os.path.join(d, 'a.out'), src],
                                          capture_output=True, **sandbox, text=True, timeout=timeout)
                    if comp.returncode != 0:
                        return '', comp.stderr or 'Compilation failed', elapsed()
                    proc = subprocess.run([os.path.join(d, 'a.out')], **feed(),
                                          capture_output=True, **sandbox, text=True, timeout=timeout)
                else:  # java
                    src = os.path.join(d, 'Main.java')
                    with open(src, 'w') as f:
                        f.write(code)
                    comp = subprocess.run(['javac', src], capture_output=True, **sandbox, text=True, timeout=timeout)
                    if comp.returncode != 0:
                        return '', comp.stderr or 'Compilation failed', elapsed()
                    proc = subprocess.run(['java', '-cp', d, 'Main'], **feed(),
                                          capture_output=True, **sandbox, text=True, timeout=timeout)
        else:
            return '', f'Unsupported language: {language}', 0

        if proc.returncode != 0:
            return proc.stdout, proc.stderr or 'Runtime error', elapsed()
        return proc.stdout, proc.stderr, elapsed()

    except subprocess.TimeoutExpired:
        return '', 'Time limit exceeded', timeout * 1000
    except FileNotFoundError as e:
        return '', f'Runtime not installed for {language}: {e}', elapsed()
    except Exception as e:
        return '', str(e), elapsed()
    finally:
        stdin_file.close()


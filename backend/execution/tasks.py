import os
# import boto3  # Lambda SDK — uncomment to switch to Lambda
import docker
import redis
import json
import time
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

    r = redis.Redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
    r.publish(f"submission:{submission_id}", json.dumps({'status': 'running'}))

    test_cases = submission.question.test_cases.all()
    print(f"[TASK] found {test_cases.count()} test cases")
    all_passed = True

    for test_case in test_cases:
        print(f"[EXEC] running test_case_id={test_case.id} input={test_case.input_data!r}")
        # Local subprocess executor — for dev machines without Docker/Lambda.
        # PROD path is run_in_docker / run_in_lambda (sandboxed); see below.
        output, error, exec_time = run_local(
            code=submission.code,
            language=submission.language,
            input_data=test_case.input_data,
        )
        # ── Docker executor (prod) — uncomment when a Docker daemon is available ─
        # output, error, exec_time = run_in_docker(
        #     code=submission.code, language=submission.language, input_data=test_case.input_data)
        # ── Lambda executor (prod) — uncomment to switch to Lambda ──────────────
        # output, error, exec_time = run_in_lambda(
        #     code=submission.code, language=submission.language, input_data=test_case.input_data)
        # ─────────────────────────────────────────────────────────────────────
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

    channel = f"submission:{submission_id}"
    payload = json.dumps({'status': submission.status})
    r.publish(channel, payload)
    print(f"[REDIS] published to channel={channel} payload={payload}")

    # ── AI features (async, best-effort) ──────────────────────────────────────
    # These fire AFTER the result is delivered above. They run as separate Celery
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
    production path is run_in_docker / run_in_lambda (isolated, resource-capped).
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

    try:
        if language == 'python':
            proc = subprocess.run(['python3', '-c', code], input=input_data,
                                  capture_output=True, **sandbox, text=True, timeout=timeout)
        elif language == 'javascript':
            proc = subprocess.run(['node', '-e', code], input=input_data,
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
                    proc = subprocess.run([os.path.join(d, 'a.out')], input=input_data,
                                          capture_output=True, **sandbox, text=True, timeout=timeout)
                else:  # java
                    src = os.path.join(d, 'Main.java')
                    with open(src, 'w') as f:
                        f.write(code)
                    comp = subprocess.run(['javac', src], capture_output=True, **sandbox, text=True, timeout=timeout)
                    if comp.returncode != 0:
                        return '', comp.stderr or 'Compilation failed', elapsed()
                    proc = subprocess.run(['java', '-cp', d, 'Main'], input=input_data,
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


def run_in_lambda(code, language, input_data):
    # Maps language to the deployed Lambda function name
    function_names = {
        'python':     'codemas-python-runner',
        'javascript': 'codemas-javascript-runner',
        'java':       'codemas-java-runner',
        'cpp':        'codemas-cpp-runner',
    }

    fn = function_names.get(language)
    if not fn:
        return '', f'Unsupported language: {language}', 0

    client = boto3.client(
        'lambda',
        region_name=os.environ.get('AWS_REGION', 'us-east-1'),
        aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    )

    payload = json.dumps({'code': code, 'input': input_data})

    print(f"[LAMBDA] invoking fn={fn}")
    start = time.time()
    try:
        response = client.invoke(
            FunctionName=fn,
            InvocationType='RequestResponse',  # synchronous — wait for result
            Payload=payload.encode('utf-8'),
        )
        exec_time = int((time.time() - start) * 1000)

        result = json.loads(response['Payload'].read())

        if response.get('FunctionError'):
            return '', result.get('errorMessage', 'Lambda error'), exec_time

        return result.get('stdout', ''), result.get('stderr', ''), exec_time

    except Exception as e:
        return '', str(e), int((time.time() - start) * 1000)


# ── Docker executor (fallback) ────────────────────────────────────────────────
# To switch back: comment out run_in_lambda() call above, uncomment run_in_docker() call
#
# def run_in_docker(code, language, input_data):
#     client = docker.from_env()  # connects to Docker daemon via Unix socket
#
#     wrapped_python = f"import sys, io\nsys.stdin = io.StringIO({repr(input_data + chr(10))})\n{code}"
#     wrapped_js = f"process.stdin.push({repr(input_data + chr(10))});\nprocess.stdin.push(null);\n{code}"
#
#     cpp_cmd = (
#         f"echo {repr(code)} > /tmp/main.cpp && "
#         f"g++ -o /tmp/main /tmp/main.cpp && "
#         f"echo {repr(input_data)} | /tmp/main"
#     )
#     java_cmd = (
#         f"echo {repr(code)} > /tmp/Main.java && "
#         f"javac /tmp/Main.java -d /tmp && "
#         f"echo {repr(input_data)} | java -cp /tmp Main"
#     )
#
#     language_config = {
#         'python':     {'image': 'python:3.11-alpine', 'command': ['python3', '-c', wrapped_python]},
#         'javascript': {'image': 'node:18-alpine',     'command': ['node', '-e', wrapped_js]},
#         'java':       {'image': 'openjdk:17-slim',    'command': ['sh', '-c', java_cmd]},
#         'cpp':        {'image': 'gcc:12',             'command': ['sh', '-c', cpp_cmd]},
#     }
#
#     config = language_config.get(language)
#     if not config:
#         return '', f'Unsupported language: {language}', 0
#
#     print(f"[DOCKER] spinning up image={config['image']}")
#     start = time.time()
#     try:
#         result = client.containers.run(
#             config['image'],
#             config['command'],
#             network_disabled=True,
#             mem_limit='128m',
#             nano_cpus=500_000_000,
#             remove=True,
#             stdout=True,
#             stderr=True,
#         )
#         exec_time = int((time.time() - start) * 1000)
#         return result.decode('utf-8'), '', exec_time
#     except docker.errors.ContainerError as e:
#         exec_time = int((time.time() - start) * 1000)
#         return '', e.stderr.decode('utf-8'), exec_time
#     except Exception:
#         return '', 'Execution failed', 10000
# ─────────────────────────────────────────────────────────────────────────────

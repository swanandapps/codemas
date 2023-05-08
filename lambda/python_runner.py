import sys
import io
import time
import traceback


def lambda_handler(event, context):
    code = event.get('code', '')
    input_data = event.get('input', '')

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    old_stdin  = sys.stdin

    sys.stdout = stdout_buf
    sys.stderr = stderr_buf
    sys.stdin  = io.StringIO(input_data + '\n')

    start = time.time()
    try:
        exec(compile(code, '<student>', 'exec'), {})
    except Exception:
        traceback.print_exc(file=stderr_buf)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        sys.stdin  = old_stdin

    exec_time = int((time.time() - start) * 1000)

    return {
        'stdout':   stdout_buf.getvalue(),
        'stderr':   stderr_buf.getvalue(),
        'exec_ms':  exec_time,
    }

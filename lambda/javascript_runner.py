import subprocess
import time
import json
import tempfile
import os


def lambda_handler(event, context):
    code = event.get('code', '')
    input_data = event.get('input', '')

    with tempfile.NamedTemporaryFile(suffix='.js', delete=False, mode='w') as f:
        f.write(code)
        tmp_path = f.name

    start = time.time()
    try:
        result = subprocess.run(
            ['node', tmp_path],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=9,
        )
        exec_time = int((time.time() - start) * 1000)
        return {
            'stdout':  result.stdout,
            'stderr':  result.stderr,
            'exec_ms': exec_time,
        }
    except subprocess.TimeoutExpired:
        return {'stdout': '', 'stderr': 'Time limit exceeded', 'exec_ms': 9000}
    except Exception as e:
        return {'stdout': '', 'stderr': str(e), 'exec_ms': int((time.time() - start) * 1000)}
    finally:
        os.unlink(tmp_path)

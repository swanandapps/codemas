import subprocess
import time
import tempfile
import os


def lambda_handler(event, context):
    code = event.get('code', '')
    input_data = event.get('input', '')

    tmp_dir = tempfile.mkdtemp()
    src_path = os.path.join(tmp_dir, 'main.cpp')
    bin_path = os.path.join(tmp_dir, 'main')

    with open(src_path, 'w') as f:
        f.write(code)

    start = time.time()
    try:
        # compile — g++ must be in Lambda layer
        compile_result = subprocess.run(
            ['g++', '-o', bin_path, src_path],
            capture_output=True, text=True, timeout=15,
        )
        if compile_result.returncode != 0:
            return {'stdout': '', 'stderr': compile_result.stderr, 'exec_ms': int((time.time() - start) * 1000)}

        # run
        run_result = subprocess.run(
            [bin_path],
            input=input_data,
            capture_output=True, text=True, timeout=9,
        )
        exec_time = int((time.time() - start) * 1000)
        return {
            'stdout':  run_result.stdout,
            'stderr':  run_result.stderr,
            'exec_ms': exec_time,
        }
    except subprocess.TimeoutExpired:
        return {'stdout': '', 'stderr': 'Time limit exceeded', 'exec_ms': 9000}
    except Exception as e:
        return {'stdout': '', 'stderr': str(e), 'exec_ms': int((time.time() - start) * 1000)}

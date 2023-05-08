import subprocess
import time
import tempfile
import os


def lambda_handler(event, context):
    code = event.get('code', '')
    input_data = event.get('input', '')

    # Java requires filename to match public class name — we enforce class Main
    tmp_dir = tempfile.mkdtemp()
    src_path = os.path.join(tmp_dir, 'Main.java')

    with open(src_path, 'w') as f:
        f.write(code)

    start = time.time()
    try:
        # compile
        compile_result = subprocess.run(
            ['javac', src_path],
            capture_output=True, text=True, timeout=15,
        )
        if compile_result.returncode != 0:
            return {'stdout': '', 'stderr': compile_result.stderr, 'exec_ms': int((time.time() - start) * 1000)}

        # run
        run_result = subprocess.run(
            ['java', '-cp', tmp_dir, 'Main'],
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

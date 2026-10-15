import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, __file__.rsplit('/tests/', 1)[0])
import sandbox  # noqa: E402

LIMITS = {'timeout_s': 3, 'python_memory_mb': 256, 'node_heap_mb': 192, 'output_kb': 64}
LINUX = sys.platform.startswith('linux')
HAS_NODE = shutil.which('node') is not None
# The between-run scrub (wipe the temp dir, kill leftover same-uid processes) only runs on Lambda
# or when explicitly enabled (Dockerfile.test does) -- never on a developer's machine.
SCRUB = LINUX and os.environ.get('CODEMAS_EXEC_SCRUB') == '1'
# Set by the platform, not inherited from us: Python's UTF-8 locale coercion (PEP 538) adds
# LC_CTYPE on Linux, and macOS adds __CF_USER_TEXT_ENCODING to every exec'd process.
PLATFORM_ENV = ('LC_CTYPE', '__CF_USER_TEXT_ENCODING')


class PythonSandboxTest(unittest.TestCase):
    def run_py(self, code, stdin=''):
        return sandbox.run('python', code, stdin, LIMITS)

    def test_reads_stdin_and_prints(self):
        r = self.run_py('print(int(input()) + 1)', '41\n')
        self.assertEqual((r['output'].strip(), r['error'], r['timed_out']), ('42', '', False))

    def test_result_shape(self):
        r = self.run_py('print(1)')
        self.assertEqual(set(r), {'output', 'error', 'ms', 'timed_out'})
        self.assertIsInstance(r['ms'], int)

    def test_reading_past_the_input_gets_eof_not_a_hang(self):
        r = self.run_py('import sys\nprint(len(sys.stdin.read()))', 'ab')
        self.assertEqual(r['output'].strip(), '2')
        self.assertFalse(r['timed_out'])

    def test_input_past_eof_raises_eoferror_not_a_hang(self):
        r = self.run_py('input()\ninput()', 'only one line\n')
        self.assertFalse(r['timed_out'])
        self.assertIn('EOFError', r['error'])

    def test_infinite_loop_is_killed_at_the_timeout(self):
        r = self.run_py('while True: pass')
        self.assertTrue(r['timed_out'])
        self.assertIn('Time limit exceeded', r['error'])

    def test_sleeping_code_is_killed_at_the_timeout(self):
        # wall-clock timeout, not just RLIMIT_CPU: a sleep burns no CPU
        start = time.monotonic()
        r = self.run_py('import time\ntime.sleep(60)')
        self.assertTrue(r['timed_out'])
        self.assertLess(time.monotonic() - start, LIMITS['timeout_s'] + 3)

    def test_runtime_error_is_reported(self):
        r = self.run_py('raise ValueError("nope")')
        self.assertIn('ValueError', r['error'])

    def test_silent_non_zero_exit_is_reported(self):
        r = self.run_py('import sys\nsys.exit(3)')
        self.assertIn('3', r['error'])

    def test_environment_is_empty(self):
        r = self.run_py(f'import os\nprint(sorted(k for k in os.environ if k not in {PLATFORM_ENV!r}))')
        self.assertEqual(r['output'].strip(), '[]')

    def test_huge_output_is_truncated(self):
        r = self.run_py("print('x' * 10_000_000)")
        self.assertLessEqual(len(r['output']), 64 * 1024 + 100)
        self.assertIn('output truncated', r['output'])
        self.assertFalse(r['timed_out'])

    def test_huge_stderr_is_truncated(self):
        r = self.run_py("import sys\nsys.stderr.write('e' * 5_000_000)")
        self.assertLessEqual(len(r['error']), 64 * 1024 + 100)
        self.assertIn('output truncated', r['error'])

    def test_endless_output_is_drained_until_the_timeout(self):
        # an output flood must neither block the child on a full pipe forever nor be buffered whole
        r = self.run_py("while True: print('x' * 10000)")
        self.assertTrue(r['timed_out'])

    def test_non_utf8_output_does_not_crash(self):
        r = self.run_py("import sys\nsys.stdout.buffer.write(b'\\xff\\xfe ok')")
        self.assertIn('ok', r['output'])
        self.assertIn('�', r['output'])

    def test_background_child_holding_the_pipe_does_not_hang(self):
        # the main program exits but leaves a grandchild with stdout open
        code = ('import subprocess, sys\n'
                'subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])\n'
                'print("bye")')
        start = time.monotonic()
        r = self.run_py(code)
        self.assertEqual(r['output'].strip(), 'bye')
        self.assertLess(time.monotonic() - start, LIMITS['timeout_s'] + 3)

    @unittest.skipUnless(LINUX, 'RLIMIT_AS is only enforced on Linux (Lambda)')
    def test_memory_limit(self):
        r = self.run_py('x = bytearray(600 * 1024 * 1024)\nprint("allocated")')
        self.assertNotIn('allocated', r['output'])
        self.assertIn('MemoryError', r['error'])

    @unittest.skipUnless(LINUX, 'RLIMIT_NPROC is only applied on Linux')
    def test_fork_bomb_is_capped(self):
        r = self.run_py('import os\nfor _ in range(200):\n    try:\n        os.fork()\n    except OSError:\n        break\nprint("done")')
        self.assertFalse(r['timed_out'])

    @unittest.skipUnless(LINUX, 'RLIMIT_FSIZE behaviour checked on Linux (Lambda)')
    def test_file_size_limit(self):
        r = self.run_py("f = open('big', 'wb')\nf.write(b'x' * (2 * 1024 * 1024))\nf.close()\nprint('wrote')")
        self.assertNotIn('wrote', r['output'])


@unittest.skipUnless(SCRUB, 'between-run scrub runs on Lambda / in the Linux test image only')
class WarmContainerIsolationTest(unittest.TestCase):
    """A warm Lambda container runs many students' code in turn: nothing may carry over."""

    def run_py(self, code):
        return sandbox.run('python', code, '', LIMITS)

    def test_temp_dir_is_wiped_between_runs(self):
        path = os.path.join(tempfile.gettempdir(), 'left-behind.txt')
        r = self.run_py(f'open({path!r}, "w").write("answers")\nprint("wrote")')
        self.assertEqual(r['output'].strip(), 'wrote')
        r = self.run_py(f'import os\nprint(os.path.exists({path!r}))')
        self.assertEqual(r['output'].strip(), 'False')
        self.assertEqual(os.listdir(tempfile.gettempdir()), [])

    def test_locked_directories_do_not_survive_the_wipe(self):
        # chmod 000 on a directory (and a nested one) must not let it outlive the scrub
        d = os.path.join(tempfile.gettempdir(), 'locked')
        r = self.run_py(f'import os\n'
                        f'os.makedirs(os.path.join({d!r}, "inner"))\n'
                        f'open(os.path.join({d!r}, "ans"), "w").write("42")\n'
                        f'open(os.path.join({d!r}, "inner", "ans"), "w").write("42")\n'
                        f'os.chmod(os.path.join({d!r}, "inner"), 0)\n'
                        f'os.chmod({d!r}, 0)\n'
                        f'print("locked")')
        self.assertEqual(r['output'].strip(), 'locked')
        self.assertEqual(os.listdir(tempfile.gettempdir()), [])
        r = self.run_py(f'import os\nos.chmod({d!r}, 0o700)\nprint(open(os.path.join({d!r}, "ans")).read())')
        self.assertNotIn('42', r['output'])
        self.assertIn('FileNotFoundError', r['error'])

    def test_setsid_escapee_does_not_survive_the_run(self):
        code = ('import subprocess, sys\n'
                'p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],\n'
                '                     start_new_session=True, stdin=subprocess.DEVNULL,\n'
                '                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n'
                'print(p.pid)')
        start = time.monotonic()
        r = self.run_py(code)
        self.assertLess(time.monotonic() - start, LIMITS['timeout_s'] + 3)
        pid = int(r['output'].strip())
        self.assertFalse(_alive(pid), f'escaped process {pid} is still running')


def _alive(pid):
    """True if pid exists and is not a zombie."""
    try:
        with open(f'/proc/{pid}/stat') as f:
            return f.read().rsplit(')', 1)[1].split()[0] != 'Z'
    except FileNotFoundError:
        return False


@unittest.skipUnless(HAS_NODE, 'node not installed')
class NodeSandboxTest(unittest.TestCase):
    def run_js(self, code, stdin=''):
        return sandbox.run('javascript', code, stdin, LIMITS)

    def test_reads_stdin_and_prints(self):
        code = "const d=require('fs').readFileSync(0,'utf8'); console.log(Number(d)+1)"
        self.assertEqual(self.run_js(code, '41').get('output').strip(), '42')

    def test_infinite_loop_is_killed(self):
        self.assertTrue(self.run_js('while(true){}')['timed_out'])

    def test_environment_is_empty(self):
        r = self.run_js(f'console.log(JSON.stringify(Object.keys(process.env).filter(k => !{list(PLATFORM_ENV)!r}.includes(k))))')
        self.assertEqual(r['output'].strip(), '[]')

    def test_huge_output_is_truncated(self):
        r = self.run_js("process.stdout.write('x'.repeat(10000000))")
        self.assertLessEqual(len(r['output']), 64 * 1024 + 100)
        self.assertIn('output truncated', r['output'])
        self.assertFalse(r['timed_out'])

    @unittest.skipUnless(LINUX, 'RLIMIT_NPROC is only applied on Linux')
    def test_fork_bomb_is_capped(self):
        code = (
            "const cp = require('child_process'); let ok = 0, failed = 0;\n"
            "for (let i = 0; i < 200; i++) {\n"
            "  try {\n"
            "    const c = cp.spawn(process.execPath, ['-e', 'setInterval(() => {}, 1000)'], {stdio: 'ignore'});\n"
            "    c.on('error', () => {}); c.unref();\n"
            "    if (c.pid) ok++; else failed++;\n"
            "  } catch (e) { failed++; }\n"
            "}\n"
            "setTimeout(() => { console.log(JSON.stringify({ok, failed})); process.exit(0); }, 300);")
        r = self.run_js(code)
        self.assertFalse(r['timed_out'])
        counts = json.loads(r['output'])
        self.assertGreater(counts['failed'], 0, counts)  # the process cap refused some spawns

    def test_heap_limit(self):
        # the heap cap stops runaway allocation: the process dies with a heap/memory error, not a timeout
        r = self.run_js("const a=[]; while(true){ a.push(new Array(1e6).fill(1)) }")
        self.assertFalse(r['timed_out'])
        self.assertRegex(r['error'].lower(), 'heap|memory')


class UnsupportedLanguageTest(unittest.TestCase):
    def test_unsupported_language(self):
        r = sandbox.run('cobol', 'x', '', LIMITS)
        self.assertIn('Unsupported language', r['error'])
        self.assertFalse(r['timed_out'])


if __name__ == '__main__':
    unittest.main()

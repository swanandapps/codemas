"""Run one test of student code in a resource-limited child process. Standard library only.

Isolation is process-level: own session/process group (killed as a group), rlimits on CPU,
file size, address space (Python) and process count (Linux), an empty environment, a fresh
temp working directory, and a wall-clock timeout. Output is read with a bounded buffer so a
flood can't exhaust the grader's memory.

Between runs (on Lambda, or when CODEMAS_EXEC_SCRUB=1) a warm container is scrubbed so nothing
carries over from one student to the next: every leftover same-uid process started after the
grader is SIGKILLed (this catches setsid() escapees the process-group kill misses) and the
whole temp dir is emptied. It is off elsewhere because on a developer's machine it would kill
their processes and wipe their temp dir.

On Linux the child also runs under a seccomp-BPF filter that refuses network sockets (see the
constant block below). It fails soft: if the kernel refuses the filter the child still runs, and
egress_blocked() -- logged by the handler at cold start -- reports it.
"""
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

IS_LINUX = sys.platform.startswith('linux')
FILE_LIMIT = 1024 * 1024   # RLIMIT_FSIZE: 1 MB
NPROC_LIMIT = 32           # RLIMIT_NPROC, Linux only
NOBODY = 65534
CHUNK = 64 * 1024
READER_GRACE_S = 2         # after the kill, how long the pipe readers get to finish, in total

# ── seccomp egress filter: kernel UAPI constants ───────────────────────────────────────────────
# Checked against linux-libc-dev (Debian bookworm) on both arches:
#   <linux/prctl.h>, <linux/seccomp.h>, <linux/audit.h> + <linux/elf-em.h>, <linux/bpf_common.h>,
#   <asm-generic/errno-base.h>, <x86_64-linux-gnu/asm/unistd_64.h>, <asm-generic/unistd.h> (arm64).
PR_SET_SECCOMP = 22
PR_SET_NO_NEW_PRIVS = 38
SECCOMP_MODE_FILTER = 2
SECCOMP_RET_KILL_PROCESS = 0x80000000
SECCOMP_RET_ERRNO = 0x00050000          # | errno in the low 16 bits
SECCOMP_RET_ALLOW = 0x7FFF0000
EPERM, EACCES = 1, 13
AF_UNIX = 1
AUDIT_ARCH_X86_64 = 0xC000003E          # EM_X86_64 (62) | __AUDIT_ARCH_64BIT | __AUDIT_ARCH_LE
AUDIT_ARCH_AARCH64 = 0xC00000B7         # EM_AARCH64 (183) | __AUDIT_ARCH_64BIT | __AUDIT_ARCH_LE
X32_SYSCALL_BIT = 0x40000000            # x86_64: x32-ABI syscalls arrive as nr | this bit
NR_SOCKET = {AUDIT_ARCH_X86_64: 41, AUDIT_ARCH_AARCH64: 198}
NR_IO_URING_SETUP = 425                 # same number on both
# struct seccomp_data { int nr; __u32 arch; __u64 instruction_pointer; __u64 args[6]; }
SECCOMP_DATA_NR, SECCOMP_DATA_ARCH, SECCOMP_DATA_ARG0 = 0, 4, 16   # arg0 low 32 bits (little-endian)
# classic BPF opcodes (struct sock_filter { __u16 code; __u8 jt; __u8 jf; __u32 k; })
BPF_LD_W_ABS, BPF_JEQ_K, BPF_JSET_K, BPF_RET_K = 0x20, 0x15, 0x45, 0x06


def _seccomp_program():
    """The filter as (code, jt, jf, k) tuples.

    - x86_64 and aarch64 (native ABIs): socket() is allowed for AF_UNIX only -- Node and Python
      need nothing else -- and refused with EACCES for every other family (AF_INET/AF_INET6, and
      also AF_PACKET, AF_NETLINK, AF_VSOCK...). io_uring_setup is refused with EPERM (io_uring can
      create sockets behind the filter's back). Everything else is allowed.
    - x32 syscalls on x86_64, and any other ABI (i386 via int 0x80 with socketcall, arm32 compat,
      unknown): the process is killed. Neither Python nor Node ever makes such a syscall, so only
      hand-made machine code gets here; killing it closes those whole syscall tables (with their
      different socket numbers) instead of keeping a deny list for each.
    """
    ops, fixups = [], []  # fixups: (index, true_label, false_label)

    def ld(offset):
        ops.append([BPF_LD_W_ABS, 0, 0, offset])

    def jump(code, k, jt, jf):
        fixups.append((len(ops), jt, jf))
        ops.append([code, 0, 0, k])

    labels = {}

    def label(name):
        labels[name] = len(ops)

    ld(SECCOMP_DATA_ARCH)
    jump(BPF_JEQ_K, AUDIT_ARCH_X86_64, 'x86_64', 'not_x86_64')
    label('not_x86_64')
    jump(BPF_JEQ_K, AUDIT_ARCH_AARCH64, 'aarch64', 'kill')
    label('x86_64')
    ld(SECCOMP_DATA_NR)
    jump(BPF_JSET_K, X32_SYSCALL_BIT, 'kill', 'x86_64_native')
    label('x86_64_native')
    jump(BPF_JEQ_K, NR_SOCKET[AUDIT_ARCH_X86_64], 'socket', 'x86_64_not_socket')
    label('x86_64_not_socket')
    jump(BPF_JEQ_K, NR_IO_URING_SETUP, 'eperm', 'allow')
    label('aarch64')
    ld(SECCOMP_DATA_NR)
    jump(BPF_JEQ_K, NR_SOCKET[AUDIT_ARCH_AARCH64], 'socket', 'aarch64_not_socket')
    label('aarch64_not_socket')
    jump(BPF_JEQ_K, NR_IO_URING_SETUP, 'eperm', 'allow')
    label('socket')
    ld(SECCOMP_DATA_ARG0)
    jump(BPF_JEQ_K, AF_UNIX, 'allow', 'eacces')
    label('allow')
    ops.append([BPF_RET_K, 0, 0, SECCOMP_RET_ALLOW])
    label('eacces')
    ops.append([BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | EACCES])
    label('eperm')
    ops.append([BPF_RET_K, 0, 0, SECCOMP_RET_ERRNO | EPERM])
    label('kill')
    ops.append([BPF_RET_K, 0, 0, SECCOMP_RET_KILL_PROCESS])

    for index, jt, jf in fixups:  # jt/jf are forward offsets from the next instruction
        ops[index][1] = labels[jt] - index - 1
        ops[index][2] = labels[jf] - index - 1
        assert 0 <= ops[index][1] <= 255 and 0 <= ops[index][2] <= 255
    return [tuple(op) for op in ops]


def _prepare_seccomp():
    """Build the filter once, in the grader: (prctl, address of struct sock_fprog, keep-alive).
    The child, between fork and exec, then only makes two prctl calls. None when unavailable."""
    if not IS_LINUX:
        return None
    try:
        import ctypes

        class SockFilter(ctypes.Structure):
            _fields_ = [('code', ctypes.c_uint16), ('jt', ctypes.c_uint8), ('jf', ctypes.c_uint8),
                        ('k', ctypes.c_uint32)]

        class SockFprog(ctypes.Structure):
            _fields_ = [('len', ctypes.c_ushort), ('filter', ctypes.POINTER(SockFilter))]

        program = _seccomp_program()
        insns = (SockFilter * len(program))(*(SockFilter(*op) for op in program))
        fprog = SockFprog(len(program), ctypes.cast(insns, ctypes.POINTER(SockFilter)))
        prctl = ctypes.CDLL(None, use_errno=True).prctl
        prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        prctl.restype = ctypes.c_int
        return prctl, ctypes.addressof(fprog), (insns, fprog)
    except Exception:
        return None


_SECCOMP = _prepare_seccomp()


def _apply_seccomp():
    """In the child. Fail soft: if either prctl fails the child runs without the filter (it can't
    log here -- its stderr is the student's); egress_blocked() is how the grader finds out."""
    if _SECCOMP is None:
        return
    prctl, fprog_address, _keepalive = _SECCOMP
    try:
        if prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            return
        prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, fprog_address, 0, 0)
    except Exception:
        pass


def _preexec(language, limits):
    """Runs in the child between fork and exec. start_new_session has already called setsid()."""
    def apply():
        cpu = int(limits['timeout_s'])
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_LIMIT, FILE_LIMIT))
        if language == 'python':
            mem = int(limits['python_memory_mb']) * 1024 * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
            except (ValueError, OSError):
                pass  # not enforceable on macOS; Lambda is Linux
        if IS_LINUX:
            resource.setrlimit(resource.RLIMIT_NPROC, (NPROC_LIMIT, NPROC_LIMIT))
        if hasattr(os, 'geteuid') and os.geteuid() == 0:  # never run student code as root
            os.setgroups([])
            os.setgid(NOBODY)
            os.setuid(NOBODY)
        _apply_seccomp()  # last: no network sockets from here on (Linux)
    return apply


def _command(language, workdir, limits):
    """(argv, source filename). argv None = runtime missing; filename None = unsupported language."""
    if language == 'python':
        return [sys.executable, '-I', os.path.join(workdir, 'main.py')], 'main.py'
    if language == 'javascript':
        node = shutil.which('node')
        if not node:
            return None, 'main.js'
        return [node, f"--max-old-space-size={int(limits['node_heap_mb'])}", os.path.join(workdir, 'main.js')], 'main.js'
    return None, None


def _decode(data, cap):
    text = data[:cap].decode('utf-8', errors='replace')
    return text + ('\n[output truncated]' if len(data) > cap else '')


def _feed(pipe, data):
    """Write all of stdin then close it, so reading past the input gets EOF instead of hanging."""
    try:
        pipe.write(data)
    except (BrokenPipeError, OSError):
        pass  # the program exited (or stopped reading) before consuming its input
    finally:
        try:
            pipe.close()
        except OSError:
            pass


def _drain(pipe, cap, sink):
    """Read until EOF, keeping at most cap + 1 bytes (the extra byte marks truncation)."""
    kept = bytearray()
    try:
        while True:
            chunk = pipe.read(CHUNK)
            if not chunk:
                break
            if len(kept) <= cap:
                kept += chunk[:cap + 1 - len(kept)]
    except (OSError, ValueError):
        pass
    sink.append(bytes(kept))


def _killpg(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def scrub_enabled():
    return IS_LINUX and bool(os.environ.get('AWS_LAMBDA_FUNCTION_NAME') or os.environ.get('CODEMAS_EXEC_SCRUB') == '1')


def _stat_fields(pid):
    """/proc/<pid>/stat fields from field 3 (state) on; the comm field may contain spaces or ')'."""
    with open(f'/proc/{pid}/stat') as f:
        return f.read().rsplit(')', 1)[1].split()


def _ancestors_and_self():
    pids, pid = set(), os.getpid()
    while pid > 0 and pid not in pids:
        pids.add(pid)
        try:
            pid = int(_stat_fields(pid)[1])  # field 4: ppid
        except (OSError, ValueError, IndexError):
            break
    return pids


def _kill_leftovers():
    """SIGKILL every same-uid process that started after this one and isn't us or an ancestor."""
    me, uid = os.getpid(), os.getuid()
    my_start = int(_stat_fields(me)[19])  # field 22: starttime, in clock ticks since boot
    keep = _ancestors_and_self()
    killed = set()
    for _ in range(5):  # repeat: something may have forked while we were scanning
        found = 0
        for name in os.listdir('/proc'):
            if not name.isdigit() or int(name) in keep:
                continue
            pid = int(name)
            try:
                fields = _stat_fields(pid)
                if fields[0] == 'Z' or os.stat(f'/proc/{pid}').st_uid != uid or int(fields[19]) <= my_start:
                    continue
                os.kill(pid, signal.SIGKILL)
                killed.add(pid)
                found += 1
            except (OSError, ValueError, IndexError):
                pass  # already gone, or not ours
        if not found:
            break
    # SIGKILL is asynchronous: wait (briefly) until each one is gone or a zombie, so nothing from
    # this run is still executing when the next one starts.
    deadline = time.monotonic() + 1
    while killed and time.monotonic() < deadline:
        killed = {pid for pid in killed if _running(pid)}
        if killed:
            time.sleep(0.01)


def _running(pid):
    try:
        return _stat_fields(pid)[0] != 'Z'
    except (OSError, IndexError):
        return False


def _reap():
    """Collect exited children. Orphans are re-parented to PID 1, which is this process when the
    grader runs as a container's entrypoint; unreaped zombies would count against RLIMIT_NPROC."""
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _wipe_tempdir():
    """Empty the temp dir, including directories the student locked with chmod. The temp root
    itself is never loosened."""
    root = os.path.realpath(tempfile.gettempdir())
    retried = set()

    def unlock(path):
        # restore owner access on a directory the student locked, and on its parent (never the root)
        parent = os.path.dirname(path)
        if os.path.realpath(parent) != root:
            os.chmod(parent, 0o700)
        if os.path.isdir(path) and not os.path.islink(path):
            os.chmod(path, 0o700)

    def force(func, path, _exc):
        if path in retried:  # unlocking didn't help: give up on this entry rather than loop
            return
        retried.add(path)
        try:
            unlock(path)
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, **{_ON_ERROR: force})
            elif os.path.lexists(path):
                func(path)
        except OSError:
            pass

    for name in os.listdir(root):
        path = os.path.join(root, name)
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path, **{_ON_ERROR: force})
            else:
                os.unlink(path)
        except OSError:
            pass


# shutil.rmtree's error hook: 'onerror' is deprecated from 3.12 in favour of 'onexc' (same use here)
_ON_ERROR = 'onexc' if sys.version_info >= (3, 12) else 'onerror'


def _result(output='', error='', ms=0, timed_out=False):
    return {'output': output, 'error': error, 'ms': ms, 'timed_out': timed_out}


def run(language, code, stdin, limits):
    start = time.monotonic()
    ms = lambda: int((time.monotonic() - start) * 1000)  # noqa: E731
    workdir = tempfile.mkdtemp(prefix='job-')
    try:
        cmd, filename = _command(language, workdir, limits)
        if filename is None:
            return _result(error=f'Unsupported language: {language}')
        if cmd is None:
            return _result(error=f'Runtime not available for {language}')
        with open(os.path.join(workdir, filename), 'w', encoding='utf-8') as f:
            f.write(code)
        os.chmod(workdir, 0o755)
        cap = int(limits['output_kb']) * 1024
        timeout = int(limits['timeout_s'])

        proc = subprocess.Popen(cmd, cwd=workdir, env={}, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, bufsize=0, close_fds=True, start_new_session=True,
                                preexec_fn=_preexec(language, limits))
        out, err = [], []
        threads = [threading.Thread(target=_feed, args=(proc.stdin, (stdin or '').encode('utf-8')), daemon=True),
                   threading.Thread(target=_drain, args=(proc.stdout, cap, out), daemon=True),
                   threading.Thread(target=_drain, args=(proc.stderr, cap, err), daemon=True)]
        for t in threads:
            t.start()
        try:
            proc.wait(timeout=timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
        elapsed = ms()
        # Always kill the whole group: on timeout, and also to reap anything the program left
        # running in the background (which would otherwise hold the pipes open).
        _killpg(proc.pid)
        proc.wait()
        if scrub_enabled():
            _kill_leftovers()  # setsid() escapees: also closes any pipe they still hold
        if IS_LINUX:
            _reap()
        deadline = time.monotonic() + READER_GRACE_S
        for t in threads:
            t.join(timeout=max(0, deadline - time.monotonic()))
        for pipe in (proc.stdout, proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass

        if timed_out or proc.returncode == -signal.SIGXCPU:  # SIGXCPU: the RLIMIT_CPU soft limit
            return _result(error='Time limit exceeded', ms=elapsed, timed_out=True)
        error = _decode(err[0] if err else b'', cap)
        if proc.returncode != 0 and not error:
            if proc.returncode < 0:
                try:
                    name = signal.Signals(-proc.returncode).name
                except ValueError:
                    name = str(-proc.returncode)
                error = f'Killed by signal {name}'
            else:
                error = f'Exited with code {proc.returncode}'
        return _result(_decode(out[0] if out else b'', cap), error, elapsed, False)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        if scrub_enabled():
            _wipe_tempdir()


EGRESS_CHECK = """import socket
try:
    socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()
    print('OPEN')
except PermissionError:
    print('BLOCKED')
"""
EGRESS_CHECK_LIMITS = {'timeout_s': 5, 'python_memory_mb': 256, 'node_heap_mb': 192, 'output_kb': 4}


def egress_blocked():
    """Run one tiny sandboxed child that tries socket(AF_INET). True if refused, False if it got a
    socket (the filter isn't active), None if not Linux or the check itself didn't work."""
    if not IS_LINUX:
        return None
    try:
        r = run('python', EGRESS_CHECK, '', EGRESS_CHECK_LIMITS)
    except Exception:
        return None
    return {'BLOCKED': True, 'OPEN': False}.get(r['output'].strip())

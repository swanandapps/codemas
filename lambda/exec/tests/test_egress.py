"""Egress hardening: the seccomp-BPF filter that stops student code opening network sockets."""
import shutil
import struct
import sys
import unittest
from unittest import mock

sys.path.insert(0, __file__.rsplit('/tests/', 1)[0])
import sandbox  # noqa: E402

LIMITS = {'timeout_s': 3, 'python_memory_mb': 256, 'node_heap_mb': 192, 'output_kb': 64}
LINUX = sys.platform.startswith('linux')
HAS_NODE = shutil.which('node') is not None

# Independent copies of the kernel UAPI values (checked against linux-libc-dev headers), so a
# typo in sandbox.py's constant block can't hide behind the same typo here.
X86_64, AARCH64, I386, ARM = 0xC000003E, 0xC00000B7, 0x40000003, 0x40000028
ALLOW, ERRNO, KILL_PROCESS = 0x7FFF0000, 0x00050000, 0x80000000
EPERM, EACCES = 1, 13
AF_UNIX, AF_INET, AF_INET6, AF_NETLINK, AF_PACKET, AF_VSOCK = 1, 2, 10, 16, 17, 40


def run_bpf(program, nr, arch, arg0=0):
    """A minimal classic-BPF interpreter for the opcodes a seccomp filter uses here. It lets the
    x86_64 branch be checked on any machine (the local Docker image is aarch64)."""
    data = struct.pack('<iIQ6Q', nr, arch, 0, arg0, 0, 0, 0, 0, 0)  # struct seccomp_data
    pc, acc, steps = 0, 0, 0
    while True:
        steps += 1
        assert steps <= len(program), 'filter loops'  # classic BPF only jumps forward
        code, jt, jf, k = program[pc]
        if code == 0x20:                     # BPF_LD | BPF_W | BPF_ABS
            acc = struct.unpack_from('<I', data, k)[0]
            pc += 1
        elif code == 0x15:                   # BPF_JMP | BPF_JEQ | BPF_K
            pc += 1 + (jt if acc == k else jf)
        elif code == 0x45:                   # BPF_JMP | BPF_JSET | BPF_K
            pc += 1 + (jt if acc & k else jf)
        elif code == 0x06:                   # BPF_RET | BPF_K
            return k
        else:
            raise AssertionError(f'unexpected opcode {code:#x} at {pc}')
        assert 0 <= pc < len(program), f'jump out of the program to {pc}'


class SeccompProgramTest(unittest.TestCase):
    """The filter's decisions, per architecture, without a kernel."""

    def setUp(self):
        self.prog = sandbox._seccomp_program()

    def decide(self, nr, arch, arg0=0):
        return run_bpf(self.prog, nr, arch, arg0)

    def test_program_is_well_formed(self):
        self.assertLessEqual(len(self.prog), 4096)  # BPF_MAXINSNS
        for code, jt, jf, k in self.prog:
            self.assertTrue(0 <= jt <= 255 and 0 <= jf <= 255 and 0 <= k <= 0xFFFFFFFF)

    def test_x86_64_socket_inet_and_inet6_get_eacces(self):
        for family in (AF_INET, AF_INET6):
            self.assertEqual(self.decide(41, X86_64, family), ERRNO | EACCES, family)

    def test_x86_64_only_af_unix_sockets_are_allowed(self):
        self.assertEqual(self.decide(41, X86_64, AF_UNIX), ALLOW)
        for family in (AF_NETLINK, AF_PACKET, AF_VSOCK, 0, 255):
            self.assertEqual(self.decide(41, X86_64, family), ERRNO | EACCES, family)

    def test_only_the_low_32_bits_of_the_family_count(self):
        # the kernel reads socket()'s family as an int: junk in the upper half can't smuggle AF_INET
        self.assertEqual(self.decide(41, X86_64, (0xDEAD << 32) | AF_INET), ERRNO | EACCES)
        self.assertEqual(self.decide(198, AARCH64, (1 << 32) | AF_INET6), ERRNO | EACCES)

    def test_x86_64_io_uring_setup_is_denied(self):
        self.assertEqual(self.decide(425, X86_64), ERRNO | EPERM)

    def test_x86_64_x32_abi_is_killed(self):
        for nr in (41, 425, 0, 60):
            self.assertEqual(self.decide(0x40000000 | nr, X86_64, AF_INET), KILL_PROCESS, nr)

    def test_x86_64_other_syscalls_are_allowed(self):
        # 198 is socket on aarch64 only; 53 is socketpair (AF_UNIX only in practice)
        for nr in (0, 1, 53, 59, 60, 198, 231):
            self.assertEqual(self.decide(nr, X86_64, AF_INET), ALLOW, nr)

    def test_aarch64_socket_rules(self):
        self.assertEqual(self.decide(198, AARCH64, AF_INET), ERRNO | EACCES)
        self.assertEqual(self.decide(198, AARCH64, AF_INET6), ERRNO | EACCES)
        self.assertEqual(self.decide(198, AARCH64, AF_UNIX), ALLOW)
        self.assertEqual(self.decide(425, AARCH64), ERRNO | EPERM)

    def test_aarch64_other_syscalls_are_allowed(self):
        # 41 is socket on x86_64 only; 199 is socketpair
        for nr in (41, 63, 64, 93, 199, 221):
            self.assertEqual(self.decide(nr, AARCH64, AF_INET), ALLOW, nr)

    def test_any_other_abi_is_killed(self):
        # i386 compat (int 0x80: socketcall 102, socket 359), arm32 compat, unknown
        for arch, nr in ((I386, 102), (I386, 359), (I386, 1), (ARM, 281), (0, 41), (0xFFFFFFFF, 198)):
            self.assertEqual(self.decide(nr, arch, AF_INET), KILL_PROCESS, (hex(arch), nr))


@unittest.skipUnless(LINUX, 'seccomp is Linux-only (Lambda)')
class EgressBlockedOnLinuxTest(unittest.TestCase):
    def run_py(self, code):
        return sandbox.run('python', code, '', LIMITS)

    def test_python_cannot_open_inet_sockets(self):
        for family in ('AF_INET', 'AF_INET6'):
            r = self.run_py(f'import socket\nsocket.socket(socket.{family}, socket.SOCK_STREAM)\nprint("opened")')
            self.assertNotIn('opened', r['output'], family)
            self.assertIn('PermissionError', r['error'], family)
            self.assertFalse(r['timed_out'], family)

    def test_python_gets_a_catchable_eacces_and_keeps_running(self):
        code = ('import errno, socket\n'
                'try:\n'
                '    socket.create_connection(("1.1.1.1", 443), timeout=3)\n'
                '    print("connected")\n'
                'except OSError as e:\n'
                '    print(errno.errorcode.get(e.errno))\n'
                'print(sum(range(10)))')
        r = self.run_py(code)
        self.assertEqual(r['output'].split(), ['EACCES', '45'])
        self.assertEqual(r['error'], '')

    def test_af_unix_and_socketpair_still_work(self):
        code = ('import socket\n'
                'a, b = socket.socketpair()\n'
                'a.sendall(b"hi")\n'
                'print(b.recv(2).decode())\n'
                'socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).close()\n'
                'print("unix ok")')
        r = self.run_py(code)
        self.assertEqual(r['output'].split(), ['hi', 'unix', 'ok'])
        self.assertEqual(r['error'], '')

    def test_normal_grading_still_works(self):
        r = sandbox.run('python', 'print(int(input()) * 2)', '21\n', LIMITS)
        self.assertEqual((r['output'].strip(), r['error']), ('42', ''))

    def test_selfcheck_reports_blocked(self):
        self.assertIs(sandbox.egress_blocked(), True)

    @unittest.skipUnless(HAS_NODE, 'node not installed')
    def test_node_starts_runs_and_gets_an_error_from_net_connect(self):
        code = ("const net = require('net');\n"
                "const s = net.connect(443, '1.1.1.1');\n"
                "s.on('error', e => console.log('ERR ' + e.code));\n"
                "s.on('connect', () => { console.log('CONNECTED'); s.destroy(); });\n"
                "console.log('still running ' + [1, 2, 3].map(x => x * 2).join(','));")
        r = sandbox.run('javascript', code, '', LIMITS)
        self.assertFalse(r['timed_out'])
        self.assertNotIn('CONNECTED', r['output'])
        self.assertIn('still running 2,4,6', r['output'])
        self.assertRegex(r['output'], r'ERR E(ACCES|PERM)')

    @unittest.skipUnless(HAS_NODE, 'node not installed')
    def test_node_normal_grading_still_works(self):
        code = "const d=require('fs').readFileSync(0,'utf8'); console.log(Number(d)*2)"
        r = sandbox.run('javascript', code, '21', LIMITS)
        self.assertEqual((r['output'].strip(), r['error']), ('42', ''))


class FailSoftTest(unittest.TestCase):
    """If the kernel refuses seccomp, the child still runs (and the self-check says so)."""

    def test_child_runs_when_prctl_fails(self):
        refusing = (lambda *args: -1, 0, None)
        with mock.patch.object(sandbox, '_SECCOMP', refusing):
            r = sandbox.run('python', 'print(6 * 7)', '', LIMITS)
        self.assertEqual((r['output'].strip(), r['error']), ('42', ''))

    def test_child_runs_when_prctl_raises(self):
        def boom(*args):
            raise OSError('no seccomp here')
        with mock.patch.object(sandbox, '_SECCOMP', (boom, 0, None)):
            r = sandbox.run('python', 'print(6 * 7)', '', LIMITS)
        self.assertEqual((r['output'].strip(), r['error']), ('42', ''))

    @unittest.skipUnless(LINUX, 'the self-check runs on Linux only')
    def test_selfcheck_reports_open_when_the_filter_is_not_installed(self):
        with mock.patch.object(sandbox, '_SECCOMP', (lambda *args: -1, 0, None)):
            self.assertIs(sandbox.egress_blocked(), False)

    @unittest.skipIf(LINUX, 'non-Linux behaviour')
    def test_selfcheck_is_none_off_linux(self):
        self.assertIsNone(sandbox.egress_blocked())


if __name__ == '__main__':
    unittest.main()

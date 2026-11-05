"""Exercise the real DLL in fresh child processes (no game install changes)."""
import ctypes
from pathlib import Path
import subprocess
import sys

DLL = Path(__file__).parent / 'build/gameforge_api64.dll'
PREFIX = '#127.0.0.1#25002#gf#offline:'


def child(expected):
    dll = ctypes.WinDLL(str(DLL.resolve()))
    for name in ('gfc_init', 'gfc_isClientRunning'):
        f = getattr(dll, name)
        f.argtypes, f.restype = [], ctypes.c_int
        assert bool(f()) == (expected != '-'), name
    values = {'AuthorizationCode': 'kuf2-offline:' + expected,
              'GameAccountId': expected, 'GameAccountNumericId': expected,
              'GameAccountName': 'Offline', 'ClientLocale': 'en_GB',
              'GameLocale': 'en_GB', 'GameDisplayLocale': 'en_GB',
              'CurrentBranch': 'b', 'GameRegion': 'EU'}
    for suffix, value in values.items():
        f = getattr(dll, 'gfc_query' + suffix)
        f.argtypes, f.restype = [ctypes.c_void_p, ctypes.c_size_t], ctypes.c_int
        assert not f(None, 100)
        for capacity in (0, 1, len(value), len(value) + 1, 128):
            buf = ctypes.create_string_buffer(b'!' * 256, 256)
            assert bool(f(ctypes.addressof(buf) + 8, capacity)) == (expected != '-' and capacity > len(value))
            assert buf.raw[:8] == b'!' * 8
            assert buf.raw[8 + capacity:] == b'!' * (248 - capacity)
            if capacity:
                assert buf.raw[8] == (value.encode()[0] if expected != '-' and capacity > len(value) else 0)
                if expected != '-' and capacity > len(value):
                    assert buf.raw[8:8 + len(value) + 1] == value.encode() + b'\0'
    dll.gfc_setErrorCallback.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    dll.gfc_setErrorCallback(None, None)
    dll.gfc_shutdown()


if __name__ == '__main__':
    if '--child' in sys.argv:
        child(sys.argv[2])
    else:
        cases = [('1', [PREFIX + '1']), ('2147483647', [PREFIX + '2147483647'])]
        cases += [('-', [PREFIX + s]) for s in ('0', '01', '-1', '', '2147483648', '9' * 100, '1#b', '1x')]
        cases += [('-', []), ('-', [PREFIX + '1', PREFIX + '2']),
                  ('-', [PREFIX.replace('127.0.0.1', '192.168.1.1') + '1']),
                  ('-', ['#127.0.0.1#25002#gf#steam#b'])]
        for expected, args in cases:
            subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', expected, *args], check=True)
        print(f'PASS: {len(cases)} command shapes, nine bounded string APIs, init/shutdown/callback ABI')

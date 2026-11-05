r"""Launch KUF2 against the local server (start `py server/main.py` first).

  py tools/launch.py                           start the game, logged in through Steam (Steam must be running)
  py tools/launch.py --offline-account 1       start it without Steam, as saved account 1 (after one Steam login)
  py tools/launch.py --game "D:\Games\Kingdom Under Fire 2"   the game's folder, when Steam doesn't list it
  py tools/launch.py --restore-eac             put the original EasyAntiCheat DLL back
  py tools/launch.py --restore-platform        put the original Gameforge platform DLL back
  py tools/launch.py --probe [--seconds 60]    TCP sink on the login port, log dialogs/connections, save first bytes
  py tools/launch.py --watch --seconds 60      start it and log its windows, then close it (testing)

The EAC stub is (re)installed on every launch; the original is kept as EasyAntiCheat_x64.dll.orig.
"""
import argparse, ctypes, ctypes.wintypes as W, datetime, hashlib, json, os, pathlib, shutil, socket, subprocess, sys, threading, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import pkg                                                   # noqa: E402  (the game's folder: Steam's, or --game)

GAME = pkg.GAME
STUB_DLL = ROOT / "stub" / "eac" / "build" / "eac_stub.dll"
EAC_ORIG_SHA = (ROOT / "tools" / "eac_original.sha256").read_text().strip()
LOGIN_HOST, LOGIN_PORT = "127.0.0.1", 25002
PLATFORM_ORIGINAL_SHA = "0ed8594dbe46d25b87db1e224dc88d507fb5af2cb45d726c2894f5c23d0e5d6f"


def sha256(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def eac_dll():
    return GAME / "EasyAntiCheat" / "EasyAntiCheat_x64.dll"


def eac_orig():
    return GAME / "EasyAntiCheat" / "EasyAntiCheat_x64.dll.orig"


def install_eac_stub():
    EAC_DLL, EAC_ORIG = eac_dll(), eac_orig()
    if not STUB_DLL.exists():
        sys.exit(f"missing {STUB_DLL}; run stub/eac/build.cmd or take it from the release")
    if not EAC_ORIG.exists():
        if sha256(EAC_DLL) != EAC_ORIG_SHA:
            sys.exit(f"{EAC_DLL} is neither the recorded original nor backed up; refusing to overwrite")
        shutil.copy2(EAC_DLL, EAC_ORIG)
    if sha256(EAC_DLL) != sha256(STUB_DLL):
        shutil.copy2(STUB_DLL, EAC_DLL)
    print("eac: stub installed")


def restore_eac():
    EAC_DLL, EAC_ORIG = eac_dll(), eac_orig()
    if EAC_ORIG.exists():
        shutil.copy2(EAC_ORIG, EAC_DLL)
    ok = sha256(EAC_DLL) == EAC_ORIG_SHA
    print("eac: original restored" if ok else "eac: RESTORE FAILED, hash mismatch")
    return ok


def install_local_platform(account_id):
    """Select an existing local account, then back up and install the local platform adapter."""
    if not isinstance(account_id, int) or not 1 <= account_id <= 0x7fffffff:
        raise ValueError("offline account must be a positive 32-bit local account ID")
    save = ROOT / "server/data/db.json"
    if not save.is_file():
        raise ValueError("no saved account yet: log in through Steam once first (py tools/launch.py)")
    db = json.loads(save.read_text())
    if sum(a.get("id") == account_id for a in db.get("accounts", {}).values()) != 1:
        raise ValueError(f"no saved account {account_id}: each account's id is in server/data/db.json")
    dll = GAME / "gameforge_api64.dll"
    original = GAME / "gameforge_api64.dll.orig"
    adapter = ROOT / "stub/platform/build/gameforge_api64.dll"
    if not adapter.is_file():
        raise FileNotFoundError(f"missing {adapter}; run stub/platform/build.cmd or take it from the release")
    if original.exists():
        if sha256(original) != PLATFORM_ORIGINAL_SHA:
            raise ValueError("platform backup hash mismatch; refusing to overwrite")
        if sha256(dll) not in (PLATFORM_ORIGINAL_SHA, sha256(adapter)):
            raise ValueError("unknown platform DLL; refusing to overwrite")
    else:
        if sha256(dll) != PLATFORM_ORIGINAL_SHA:
            raise ValueError("platform DLL is not the recorded original; refusing to overwrite")
        shutil.copy2(dll, original)
    if sha256(dll) != sha256(adapter):
        shutil.copy2(adapter, dll)
    print(f"platform: local adapter installed for saved account {account_id}")


def restore_platform():
    original = GAME / "gameforge_api64.dll.orig"
    if original.exists():
        if sha256(original) != PLATFORM_ORIGINAL_SHA:
            raise ValueError("platform backup hash mismatch; refusing to restore")
        dll = GAME / "gameforge_api64.dll"
        if not dll.exists() or sha256(dll) != PLATFORM_ORIGINAL_SHA:
            shutil.copy2(original, dll)
        print("platform: original restored")


def game_args(host=LOGIN_HOST, port=LOGIN_PORT, offline_account=None):
    if offline_account is not None:
        if host != "127.0.0.1" or port != 25002 or type(offline_account) is not int or not 1 <= offline_account <= 0x7fffffff:
            raise ValueError("local adapter requires loopback port 25002 and an existing local account ID")
        return f"#{host}#{port}#gf#offline:{offline_account}"
    # same shape Steam passes: #login.kuf2.gameforge.com#25002#gf#steam#b
    return f"#{host}#{port}#gf#steam#b"


def start_game(args):
    env = dict(os.environ, __COMPAT_LAYER="RunAsInvoker")  # the exe asks for admin; it does not need it
    return subprocess.Popen([str(GAME / "KUF2.exe"), args], cwd=str(GAME), env=env)


u32 = ctypes.WinDLL("user32")
EnumProc = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


def window_texts(pid):
    def text(h):
        n = u32.GetWindowTextLengthW(h)
        b = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(h, b, n + 1)
        c = ctypes.create_unicode_buffer(128)
        u32.GetClassNameW(h, c, 128)
        return c.value, b.value
    wins = []
    def cb(h, _):
        p = W.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            wins.append(h)
        return True
    u32.EnumWindows(EnumProc(cb), 0)
    out = []
    for h in wins:
        items = [text(h)]
        def ccb(ch, _):
            items.append(text(ch))
            return True
        u32.EnumChildWindows(h, EnumProc(ccb), 0)
        out.append(items)
    return out


class Sink:
    """Accepts connections on a port and records everything received, never replies."""
    def __init__(self, port, capture_path):
        self.port, self.capture_path, self.t0 = port, capture_path, time.time()
        self.srv = socket.create_server(("127.0.0.1", port))
        self.srv.settimeout(0.5)
        self.stop = False
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while not self.stop:
            try:
                c, a = self.srv.accept()
            except socket.timeout:
                continue
            print(f"{time.time() - self.t0:5.1f} accept {a}", flush=True)
            threading.Thread(target=self.handle, args=(c, a), daemon=True).start()

    def handle(self, c, a):
        c.settimeout(0.5)
        with open(self.capture_path, "a") as f:
            while not self.stop:
                try:
                    b = c.recv(65536)
                except socket.timeout:
                    continue
                except OSError as e:
                    print(f"conn error {e}", flush=True)
                    return
                if not b:
                    print(f"{time.time() - self.t0:5.1f} {a} closed", flush=True)
                    return
                print(f"{time.time() - self.t0:5.1f} recv {len(b)}: {b.hex()}", flush=True)
                f.write(f"{a} {len(b)} {b.hex()}\n")
                f.flush()


def probe(seconds):
    restore_platform()
    install_eac_stub()
    captures = ROOT / "captures"
    captures.mkdir(exist_ok=True)
    cap = captures / f"probe_{datetime.datetime.now():%Y%m%d_%H%M%S}.hex"
    sink = Sink(LOGIN_PORT, cap)
    p = start_game(game_args())
    print(f"game pid {p.pid}, args {game_args()}", flush=True)
    seen, t0 = set(), time.time()
    try:
        while time.time() - t0 < seconds and p.poll() is None:
            for w in window_texts(p.pid):
                k = repr(w)
                if k not in seen:
                    seen.add(k)
                    print(f"{time.time() - t0:5.1f} window {w}", flush=True)
            time.sleep(0.5)
    finally:
        if p.poll() is None:
            p.kill()
            print("game killed (probe timeout)")
        else:
            print(f"game exited rc={p.returncode}")
        sink.stop = True
    print(f"capture: {cap if cap.exists() else 'none'}")


def watch(seconds, offline_account=None):
    """Launch against an already-running server; log windows; kill after `seconds` (0 = leave running)."""
    if offline_account is None:
        restore_platform()
    else:
        install_local_platform(offline_account)
    install_eac_stub()
    args = game_args(offline_account=offline_account)
    p = start_game(args)
    print(f"game pid {p.pid}, args {args}", flush=True)
    if seconds == 0:
        return
    seen, t0 = set(), time.time()
    while time.time() - t0 < seconds and p.poll() is None:
        for w in window_texts(p.pid):
            k = repr(w)
            if k not in seen:
                seen.add(k)
                print(f"{time.time() - t0:5.1f} window {w}", flush=True)
        time.sleep(0.5)
    if p.poll() is None:
        p.kill()
        print("game killed (watch timeout)")
    else:
        print(f"game exited rc={p.returncode}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Start Kingdom Under Fire 2 against the local server (py server/main.py).")
    ap.add_argument("--game", help="the game's folder (default: found through Steam's library list)")
    ap.add_argument("--offline-account", type=int, help="start without Steam, as this saved account (1 = the first)")
    ap.add_argument("--restore-eac", action="store_true", help="restore the original EasyAntiCheat DLL")
    ap.add_argument("--restore-platform", action="store_true", help="restore the original Gameforge platform DLL")
    ap.add_argument("--probe", action="store_true", help="testing: a TCP sink instead of the server")
    ap.add_argument("--watch", action="store_true", help="testing: log the game's windows, close it after --seconds")
    ap.add_argument("--seconds", type=int, default=60, help="with --watch or --probe; 0 = leave it running")
    a = ap.parse_args()
    GAME = pkg.use_game(a.game)
    if a.restore_platform:
        restore_platform()
        sys.exit(0)
    if a.restore_eac:
        sys.exit(0 if restore_eac() else 1)
    try:
        if a.probe:
            probe(a.seconds)
        else:
            watch(a.seconds if a.watch else 0, a.offline_account)
    except (ValueError, FileNotFoundError) as e:     # the refusals above, as one line instead of a traceback
        sys.exit(f"launch: {e}")

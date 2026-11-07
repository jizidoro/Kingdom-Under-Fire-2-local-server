"""asyncio TCP plumbing: framed, encrypted sessions and a handler registry per server role; the journal."""
import asyncio, datetime, hashlib, json, logging, os, pathlib, re, struct, time, traceback

from . import timeline
from .crypt import Cipher, integrity_report
from .packet import Reader, Writer

log = logging.getLogger("kuf2")
LOG_DIR = pathlib.Path(__file__).resolve().parents[2] / "captures"

# The journal (LIVE-DEBUG-PLAN): what happens, one JSON line per event {"t": epoch ms, "k": kind, ...}, in
# JOURNAL_DIR/<server start>.jsonl, and the same events as readable lines (timeline) in LOGS_DIR/server_<start>.log;
# tools/live.py follows it beside the client's telemetry. main.py opens it; until then (tests, tools) journal()
# returns at once. The packet lines stay in the log.
JOURNAL_DIR = LOG_DIR / "journal"
LOGS_DIR = LOG_DIR / "logs"
journal_out = journal_log = None     # the open journal and its readable log
handling = None                  # (role, request id, handler) of the handler running now: what a refusal answers
HOME = os.path.expanduser("~")   # holds the Windows user name; players attach the journal and its log to public issues


def private(text):
    """text with the home folder as ~, plain or JSON-escaped (a traceback names the Python install and the project's
    files, which are under it when installed per user or unzipped in Downloads)."""
    for h in (HOME, json.dumps(HOME, ensure_ascii=False)[1:-1]):
        text = re.sub(re.escape(h), "~", text, flags=re.I)
    return text


def journal(k, **fields):
    """One journal line (event kind k) and its readable line; never raises into the caller."""
    if journal_out is None:
        return
    try:
        e = {"t": int(time.time() * 1000), "k": k, **fields}
        journal_out.write(private(json.dumps(e, ensure_ascii=False, default=str)) + "\n")
        journal_out.flush()
        journal_log.write(private(timeline.line(e, "SRV", timeline.server_text(e))) + "\n")
        journal_log.flush()
    except Exception:
        pass


def cause(why=None):
    """The reason an economy journal line (item, gold, exp) gives: its caller's, else the request handler running now
    (store_buy, drop_pick, take_item ...), else None (a timer's)."""
    return why or (handling[2] if handling else None)


class _Journaled(logging.Handler):
    """The handlers' own log lines the journal keeps: a refusal (the codebase's "refused" / "not understood" lines)
    with the request being handled, any other warning, and an exception with its traceback (a handler's, which ends
    its session, or a timer's, logged by asyncio). A line journaled where it is logged (extra journaled=True) is
    left alone."""
    def emit(self, record):
        try:
            if getattr(record, "journaled", False):
                return
            text, req = record.getMessage(), handling and dict(zip(("role", "id", "fn"), handling))
            if record.exc_info:
                journal("error", req=req, text=text[:300], tb="".join(traceback.format_exception(*record.exc_info)))
            elif "refused" in text or "not understood" in text:
                journal("refused", req=req, text=text[:300])
            elif record.levelno >= logging.WARNING:
                journal("warn", req=req, text=text[:300])
        except Exception:
            pass


_journaled = _Journaled(logging.INFO)
JOURNALED_LOGS = ("kuf2", "director", "asyncio")


def open_journal():
    """Start the journal: JOURNAL_DIR/<now>.jsonl and LOGS_DIR/server_<now>.log; the journal's path."""
    global journal_out, journal_log
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    start = f"{datetime.datetime.now():%Y%m%d_%H%M%S}"
    path = JOURNAL_DIR / f"{start}.jsonl"
    journal_out = open(path, "a", encoding="utf-8")
    journal_log = open(LOGS_DIR / f"server_{start}.log", "a", encoding="utf-8")
    for name in JOURNALED_LOGS:
        logging.getLogger(name).addHandler(_journaled)
    journal("boot", commit=commit())
    return path


def commit():
    """The git commit this server runs ("+" when the tree has changes), None outside a checkout: a run's logs say which
    code made them (the proof audit 2026-09-29: nothing did)."""
    import subprocess
    root = pathlib.Path(__file__).resolve().parents[2]
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True,
                              timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no", "--", "server"], cwd=root,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return (head + ("+" if dirty else "")) or None
    except (OSError, subprocess.SubprocessError):
        return None


def close_journal():
    global journal_out, journal_log
    for name in JOURNALED_LOGS:
        logging.getLogger(name).removeHandler(_journaled)
    for f in (journal_out, journal_log):
        if f is not None:
            f.close()
    journal_out = journal_log = None


class Session:
    def __init__(self, role, reader, writer, handlers, state):
        self.role, self.r, self.w, self.handlers, self.state = role, reader, writer, handlers, state
        self.rx, self.tx = Cipher(), Cipher()
        self.sent_digest = hashlib.md5()    # what the client's integrity report covers (frames since the last one)
        self.peer = writer.get_extra_info("peername")
        self.data = {}  # per-connection scratch (account, selected character, ...)
        LOG_DIR.mkdir(exist_ok=True)
        self.trace = open(LOG_DIR / f"{role}_{datetime.datetime.now():%Y%m%d_%H%M%S_%f}.log", "a")

    def _trace(self, direction, frame):
        proto = struct.unpack_from("<H", frame, 3)[0] if len(frame) >= 5 else -1
        self.trace.write(f"{datetime.datetime.now():%H:%M:%S.%f} {direction} 0x{proto:04x} {len(frame)} {bytes(frame).hex()}\n")
        self.trace.flush()

    def later(self, delay, fn):
        """Run fn after `delay` seconds if the connection is still open."""
        def run():
            if not self.w.is_closing():
                fn()
        asyncio.get_running_loop().call_later(delay, run)

    def send(self, pkt: Writer):
        frame = pkt.frame()
        self._trace("S2C", frame)
        log.info("%s S2C 0x%04x len %d", self.role, pkt.proto, len(frame))
        self.w.write(bytes(self.tx.encrypt(frame)))

    async def run(self):
        global handling
        log.info("%s connect %s", self.role, self.peer)
        journal("conn", role=self.role, ev="open")
        try:
            while True:
                hdr = await self.r.readexactly(2)
                size = struct.unpack("<H", hdr)[0]
                if size == 0:  # re-seed frame: 00 00 <u16 seed>; the client never sends one to us
                    await self.r.readexactly(2)
                    continue
                frame = bytearray(hdr + await self.r.readexactly(size - 2))
                if integrity_report(frame) and bytes(frame[5:]) == self.sent_digest.digest():
                    self._trace("C2S", frame)                  # the plain-text report, caught before decrypting it:
                    log.info("%s C2S integrity report (digest matches)", self.role)   # about 1 in 256 pass the
                    self.sent_digest = hashlib.md5()          # check byte, advance the seed and kill the session
                    continue                                  # (planning/client/room_troops.md)
                try:
                    self.rx.decrypt(frame)
                except ValueError:
                    if not integrity_report(frame):
                        raise
                    self._trace("C2S", frame)
                    log.info("%s C2S integrity report id 0x%04x (digest %s)", self.role,
                             struct.unpack_from("<H", frame, 3)[0],
                             "matches" if bytes(frame[5:]) == self.sent_digest.digest() else "differs")
                    self.sent_digest = hashlib.md5()
                    continue
                self.sent_digest.update(bytes(frame[3:]))
                self._trace("C2S", frame)
                pkt = Reader(bytes(frame))
                h = self.handlers.get(pkt.proto)
                if h is None:
                    log.warning("%s C2S 0x%04x len %d UNHANDLED %s", self.role, pkt.proto, len(frame),
                                bytes(frame[5:69]).hex(), extra={"journaled": True})
                    journal("unknown", role=self.role, id=pkt.proto, len=len(frame), head=bytes(frame[5:37]).hex())
                    continue
                log.log(logging.DEBUG if getattr(h, "quiet", False) else logging.INFO,
                        "%s C2S 0x%04x len %d -> %s", self.role, pkt.proto, len(frame), h.__name__)
                handling = (self.role, pkt.proto, h.__name__)
                h(self, pkt)
                handling = None
                await self.w.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            log.info("%s disconnect %s", self.role, self.peer)
        except Exception:
            log.exception("%s session error", self.role)
        finally:
            handling = None
            journal("conn", role=self.role, ev="close", spot=self.data.get("spot"))
            rooms = getattr(self.state, "game_sessions", {})    # a closed room is no room: every world reader sends on
            account = (self.data.get("account") or {}).get("id")   # it, and 0x4040's exit pops nothing (2026-11-06: a
            if rooms.get(account) is self:                      # level-up in town wrote here and killed the world link);
                del rooms[account]                              # a room change's next login already holds the entry
            self.trace.close()
            self.w.close()


class Role:
    """One listening server role (login / world / game) with its C2S handler table."""
    def __init__(self, name, port, state):
        self.name, self.port, self.state, self.handlers = name, port, state, {}

    def ignore(self, *protos):
        """Requests we decided not to answer (nothing waits on them): handled silently, logged at debug level."""
        def handler(s, pkt):
            pass
        handler.__name__ = "ignored"
        for p in protos:
            self.on(p, quiet=True)(handler)

    def empty_replies(self, table):
        """Answer each request in {request: (reply, body)} with a fixed reply (stubs and empty lists)."""
        from .packet import Writer

        def make(reply, body):
            def handler(s, pkt):
                s.send(Writer(reply).raw(body))
            handler.__name__ = f"empty_reply_{reply:04x}"
            return handler
        for req, (reply, body) in table.items():
            self.on(req)(make(reply, body))

    def on(self, proto, quiet=False):
        """Register a C2S handler; quiet=True logs its packets at debug level (frequent ones like movement)."""
        def deco(fn):
            fn.quiet = quiet
            self.handlers[proto] = fn
            return fn
        return deco

    async def serve(self, host="127.0.0.1"):
        async def accept(r, w):
            await Session(self.name, r, w, self.handlers, self.state).run()
        srv = await asyncio.start_server(accept, host, self.port)
        log.info("%s listening on %s:%d", self.name, host, self.port)
        return srv

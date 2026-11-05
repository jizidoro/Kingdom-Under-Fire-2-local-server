"""Login role (client connects here from the command line: #127.0.0.1#25002#gf#steam#b)."""
import ipaddress
import re
import socket

from . import settings
from .net import Role, journal, log
from .packet import Writer

C2S_LOGIN_STEAM = 0x103C
C2S_LOGIN_LOCAL = 0x1039       # original four-field Gameforge launcher path
S2C_LOCAL_TICKET = 0x103A     # cstr stored in lobby +0x17a8, later carried by 0x103b
S2C_LOGIN_RES = 0x1021          # client handler @ 0x140e61f00
C2S_SERVER_LIST = 0x1004        # empty body
S2C_SERVER_LIST = 0x1005        # client handler @ 0x140e7c790; entries read by 0x140e7e030 (u16 count, 13 bytes each)
C2S_SERVER_SELECT = 0x1006      # u32 server id: the chosen entry's +0, filled from its wire +4 (0x140e7b880)
S2C_SERVER_ADDRESS = 0x1007     # client handler @ 0x140e7ccb0 (ProcessPacket_ServerIPAddress)

# An entry's wire +0 is the key of the client's own name table (1 = "(EU) Curian", 8 = "(US) Leinhart", ...;
# tools/frida/servernames.js), wire +4 the server id (entry+0: 0x1006 sends it, the header's id pre-selects it;
# 0x140e7c8e2-0x140e7c91f, planning/client/session_lobby.md §3 0x1005)
SERVERS = [{"name": 1, "id": 1, "u8": 0, "open": True, "u11": 0}]
# Resent every 0.5 s for a minute until 0x1006: a list sent before UI 0x7e loads is kept but not shown (live, a 5 s
# step showed it 5 s late; session_lobby.md §5 7)
LIST_RESEND_DELAYS = tuple(k / 2 for k in range(1, 121))

# The 0x1021 service code: the client compares it with its settings' +0x358 (dump @ 0x140e6206a; mismatch -> message
# 0xea73 and quit), which its init fills from %Content's NationCode (GAMEFORGE 10000, as tools/frida/globals.js saw).
# after a successful login: 0 (default path @ 0x140e60090) = SetSubState(login -> server select); 1/2 open UI 0x7c; 3 = disconnect + back to login
NEXT_STEP = 0


def make(state, port, world_host, world_port):
    role = Role("login", port, state)
    # Login paths this client does not take (specs/session_account_worldmap.md): the clock echo 0x1000, other
    # publishers' and NHN logins (0x1002, 0x1013, 0x1020, 0x1022, 0x1033, 0x1035), the
    # second password (0x1025, 0x1027) and the server queue (0x1029, 0x102c; 0x1007 always admits), builders nothing
    # calls (0x1019, 0x101c, 0x101d, 0x1023, 0x1034). Registered so they are logged as decided, not as unknown.
    role.ignore(0x1000, 0x1002, 0x1013, 0x1020, 0x1022, 0x1033, 0x1035, 0x1025, 0x1027, 0x1029, 0x102c,
                0x1019, 0x101c, 0x101d, 0x1023, 0x1034)

    def admit(s, acct):
        s.data["account"] = acct
        journal("login", account=acct["id"])
        w = Writer(S2C_LOGIN_RES)
        w.u16(0).zeros(8)
        w.i32(acct["id"]).obool(False).i32(settings.get("NationCode")).i32(NEXT_STEP).zeros(10)
        w.cstr(acct["name"]).cstr("")
        s.send(w)

    @role.on(C2S_LOGIN_LOCAL)
    def login_local(s, pkt):
        # Local save selection, not a Gameforge credential or remote authentication.
        # The unchanged PSW wrapper hex-encodes the adapter's ASCII ticket.
        try:
            peer = ipaddress.ip_address(s.peer[0])
            ticket = pkt.cstr()
            build, flags = pkt.u32(), pkt.u32()
            if not peer.is_loopback or pkt.rest() or build != 0x0131602D or flags != 0x1C:
                raise ValueError("invalid local login context")
            if not re.fullmatch(r"[0-9a-fA-F]{2,80}", ticket) or len(ticket) % 2:
                raise ValueError("invalid local ticket encoding")
            identity = bytes.fromhex(ticket).decode("ascii")
            match = re.fullmatch(r"kuf2-offline:([1-9][0-9]{0,9})", identity)
            if match is None or int(match[1]) > 0x7FFFFFFF:
                raise ValueError("invalid local identity")
            acct = state.account_by_id(int(match[1]))
            if "account" in s.data:
                raise ValueError("already logged in")
        except (ValueError, KeyError, AttributeError, TypeError, IndexError):
            log.warning("local login refused")
            s.send(Writer(S2C_LOGIN_RES).u16(1).zeros(31).cstr("").cstr(""))
            return
        # Store an empty platform continuation string; no external token exists.
        s.send(Writer(S2C_LOCAL_TICKET).cstr(""))
        admit(s, acct)

    @role.on(C2S_LOGIN_STEAM)
    def login_steam(s, pkt):
        ticket = pkt.cstr()
        persona = pkt.cstr()
        locale = pkt.cstr()
        extra = pkt.cstr()
        steam_id = pkt.u64()
        build = pkt.u32()
        tail = pkt.rest()
        acct = state.account_for_steam(steam_id, persona)
        # the log names the local account, never the Steam ID or persona (players attach their logs to reports)
        log.info("login steam: account %d locale=%s build=0x%x extra=%r tail=%s ticket_len=%d",
                 acct["id"], locale, build, extra, tail.hex(), len(ticket))
        admit(s, acct)

    @role.on(C2S_SERVER_LIST)
    def server_list(s, pkt):
        def send_list():
            if s.data.get("server_chosen"):
                return
            w = Writer(S2C_SERVER_LIST)
            w.u32(SERVERS[0]["id"])             # last-used server id: the client pre-selects it
            w.u16(len(SERVERS))
            for sv in SERVERS:                  # 13-byte entries
                w.u32(sv["name"]).u32(sv["id"]).u16(sv["u8"]).obool(sv["open"]).u16(sv["u11"])
            s.send(w)
        # The client asks right after login, while the server-select UI (0x7e) is still loading, and
        # drops a list that arrives before the UI exists (handler @ 0x140e7c790). Answer again until it is up.
        send_list()
        for delay in LIST_RESEND_DELAYS:
            s.later(delay, send_list)

    @role.on(C2S_SERVER_SELECT)
    def server_select(s, pkt):
        server = pkt.u32()
        s.data["server_chosen"] = True
        acct = s.data["account"]
        key = state.issue_world_key(acct)
        log.info("server select id=%d -> world %s:%d key=%x", server, world_host, world_port, key)
        w = Writer(S2C_SERVER_ADDRESS)
        w.u16(0)                                # result
        w.u32(int.from_bytes(socket.inet_aton(world_host), 'big'))   # ip as a host-order u32 (0x7F000001)
        w.zeros(4).u64(key).u16(world_port)     # 18-byte struct: ip, pad, key, port
        s.send(w)

    return role

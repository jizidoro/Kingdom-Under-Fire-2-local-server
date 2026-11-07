"""The PvP waiting room of one: 0x3e42 and 0x3e61 open a real room (CommonSubPvpWaitingRoom, scene 0x57, sub-UI 0x8b)
with the player alone in it. planning/todo/CONTRACT-COMPLETE-PLAN.md, third wave; the dig and the verdicts:
planning/agents/reports/2026-11-05_contract3-roomofone.md. The room of PvP against AI is another thing: the client's
own, the server holds nothing for it (pvp.py), and it keeps every constant below.

The route (read 2026-11-05). A PvP spot's menu (0x140d49290: row +0x10 Spot_Type 6 PVP or 7 PVP_POINT, the table has
only PVP_POINT) opens the room list 0x6a (0x140d48fc0), its "RoomMaking" (0x140d83490) the window 0x6b; every
PVP_POINT row is Pvp_Only True (loader 0x141865c91 -> row +0xc9), so that callback sets list +0x89 and prefills the
window (0x140d3fd30). Its OK (0x140d40270; row +0x14 Spot_Sub_Type 7 PVP_AI goes to the client's AI room instead)
sends 0x3e42. The quick join 0x140d841c0 sends the same with its own title.

The spot. 0x3e42 names none: the client's is common+0x130, the world-map marker's (WorldMap Update 0x140d36950 writes
[+0x568]+0x78 there each tick, 0x140d36b4e), and the marker's arrival is the 0x3742 of 0x140d3b0a0, which world.py
keeps as s.data["target_spot"]. So that is the room's spot; one that is no PVP_POINT, or PVP_AI (which never sends
0x3e42), opens nothing and the request has its bare 0x3e43, as before. 0x3e61 names its spot.

Requests and answers (plain fields unless noted; "coded u32" = obf.u32 / obf.dec_u32):
  C2S 0x3e42 create (0x140f02db0): cstr name, flag has-password (T2[!flag]), u8 max (window +0x60), u8 troops (+0x64),
      [cstr password]. The name and the password stay the client's: nothing below carries them.
  S2C 0x3e43 (0x140cbeb80): reads nothing, clears window +0x91.
  S2C 0x3e45 enter (0x140cbebc0 -> Common -> list 0x140d84c20): i16, on 0 five bytes: coded u32 spot, u8 difficulty
      index. Spot -1 is the quiet refusal of the joins (world.EMPTY_REPLIES). Row +0x10 6 / 7 -> room type 1; list +0x89
      set -> 0x140d3ff40 builds the room info from the window (the title is the room's name), copies it to scene 0x57
      (0x1406283b0) and opens it, synchronously: the OnOpen 0x1406275a0 builds the seats from the spot (0x1406294b0:
      Limit_Party * 2 + 4 of them, 0xa0 bytes each), which is why this comes before 0x3e57. List +0x89 clear (the quick
      join): 0x140d84c20 opens it itself, the same way, with an empty name.
  S2C 0x3e57 Process_ResRoomInfo (0x14062a5b0; asserts when the room's sub-UI is missing, so never before 0x3e45): i16,
      on 0 (parser 0x14062bef0) 8 bytes: coded u32 spot, coded u32 X -> room +0x98, the deck the troop window edits
      (0x140653ab0); X != -1 sets room mode 1 (auto-start 0x140628ca0), so -1, which is also the main deck's key. Then
      (0x14062c160) u8 n, n members (0x14062c3d0): 8 bytes (u16 seat, u32 id, unread u8, u8 ready -> seat +0x94), cstr
      name, (0x14062c060) u8 m, m * 11 bytes: +0 u8 troop level, +1 u8 leader level, +2 coded u32 troop id, +6 u8 index
      0..8, +7 u32 leader id. An id equal to common+0xd4 seats the player (room +0xc8 = seat): without that the leave
      path indexes seat -1. Index 0 is the hero (level +0x4c[0], name): as EnterPvPAIRoom 0x140628e10 fills it, no troop
      id, leader id 0 (0x140d977e0's record +0x10); the troops are the main deck's slots (troops.room_deck), no
      officers (the seat draws only what +0x82 = Limit_Troop_1 allows, 0x1409ef220).
  S2C 0x3e4a new master (Common, scene 0x57 open -> 0x14062ac70 -> 0x1406297a0): u16 seat; seat +0x8f = 1, ready 1 -> 0,
      and 0x1409ef650 gives him the start button (master 0, otherwise 1 + (ready == 1)). 0x3e57 sets no master.
  C2S 0x3e61 create from the match window (0x140f03410 from 0x140622900, sets +0xc4): cstr name, coded u32 spot, u8,
      flag, u8, [cstr password]. Unreachable while 0x5749 lists no spot (owner's D1, no season); built on the code.
  S2C 0x3e65 (0x14061f1d0): clears +0xc4, i16, on 0 four unread bytes; 1 -> "You have failed to create a room." The
      room opens by the same 0x3e45 -> 0x14061f2b0, only while +0xc4 is set, so 0x3e65 comes last.
  C2S 0x3e53 move my seat (0x14062a250 from 0x1406279c0): u16 target, u32 own id. S2C 0x3e54 (0x14062acb0): i16; 0 ->
      u16 seat, u32 id; the client moves that id's seat to the target and re-marks the master itself. An id in no seat
      gives slot 0xffff, out of bounds (0x140629b80), so only the player's own id is ever echoed; a move onto his own
      seat would erase him (0x14062cc20 clears the old seat after copying). Refusal 0x1c2d -> text 7268.
  C2S 0x3e5a ready (0x140629e40): u8 (own ready != 1). S2C 0x3e5b (0x14062ab70): i16; 0 -> 8 bytes: u16 seat, u32 id,
      unread u8, u8 state -> 0x140629930. A master has no ready button (0x1409ef650), so a room of one should not send
      it; if it does, this is its answer.
  C2S 0x3e5c leave (0x14062a1e0 from 0x140628500): no body. S2C 0x3e5d (0x14062b480): i16; 0 hides the room and clears
      common+0x1628; anything else only asserts and strands him: always 0.

Nothing to answer:
  Start: the "start" callback 0x1406279c0 stops in the client: occupied seats < 2 -> text 0x1d87 = 7559 "Cannot start
      the game yet." (a not-ready non-master earlier: 0x1b91 = 7057). Nothing is sent. 0x3e4b stays ignored (world.py).
  Kick and hand over: "delMember" / "changeAuth" only open dialogs 0x1392 / 0x11193 and the room's dialog handler
      0x140628380 takes 0x1e1b / 0x1e1f alone; the kick push 0x14062b730 has no code reference. No request exists.
  Chat: the room opens the chat window on sub-UI 0x8b (0x140ddf8d0) and prints 0x1c8f "Can use the Party Chat."; a line
      is the ordinary 0x1042 and world.py's echo answers it. Channel 4 is dropped by the client in this sub-UI (0x140dded00).

Ours (no table, note or footage says):
  The creator's seat 0 (the client takes any seat it is told). A target past the two teams (seat >= Limit_Party * 2) is
  refused with 0x1c2d: the client lets him click one and never lets him off it (own seat < Limit_Party * 2 in
  0x1406279c0). A deck changed from inside the room shows at the next open: 0x1364 (0x14062af30), the seat's refresh, is
  not sent.

State: s.data["pvproom"] of the world session, never the save (the client tells the server when it leaves; a new
connection has no room). {"spot": id, "seat": n, "ready": 0 or 1}. With none, the seat, ready and leave requests are
the AI room's, and keep world.EMPTY_REPLIES's answers.
"""
import struct

from . import obf, tables, troops
from .net import log
from .packet import Writer

C2S_CREATE, S2C_CREATE = 0x3e42, 0x3e43
C2S_MATCH_CREATE, S2C_MATCH_CREATE = 0x3e61, 0x3e65
C2S_MOVE, S2C_MOVE = 0x3e53, 0x3e54
C2S_READY, S2C_READY = 0x3e5a, 0x3e5b
C2S_LEAVE = 0x3e5c
S2C_ENTER = 0x3e45
S2C_ROOM = 0x3e57
S2C_MASTER = 0x3e4a
MY_SEAT = 0                     # ours: the room's creator, alone in it
NONE = 0xFFFFFFFF               # coded -1: no troop on the hero's record; the main deck in the head
CREATE_FAILED = 1               # 0x3e65: "You have failed to create a room."


def spot_row(spot):
    """The spottable row of a spot a waiting room of people can stand on, else None."""
    row = tables.by_id("spottable").get(str(spot))
    return row if row and row.get("Spot_Type") == "PVP_POINT" and row.get("Spot_Sub_Type") != "PVP_AI" else None


def team_seats(room):
    """The seats of the two teams (seat < Limit_Party: team 0, < Limit_Party * 2: team 1; 0x1406279c0)."""
    return 2 * int(spot_row(room["spot"])["Limit_Party"])


def room_packet(c, room):
    """0x3e57: the one member, the hero's record and the deck the spot allows."""
    deck = troops.room_deck(c, room["spot"])
    w = Writer(S2C_ROOM).u16(0).raw(obf.u32(room["spot"])).raw(obf.u32(NONE)).u8(1)
    w.u16(room["seat"]).u32(c["id"]).u8(0).u8(room["ready"]).cstr(c["name"]).u8(1 + len(deck))
    w.u8(0).u8(c.get("level", 1)).raw(obf.u32(NONE)).u8(0).u32(0)
    for slot, t in deck:
        w.u8(t["level"]).u8(0).raw(obf.u32(t["id"])).u8(slot).u32(0)
    return w


def make(role, state):
    from .world import EMPTY_REPLIES

    def constant(s, request):
        reply, body = EMPTY_REPLIES[request]
        s.send(Writer(reply).raw(body))

    def open_room(s, spot):
        room = s.data["pvproom"] = {"spot": spot, "seat": MY_SEAT, "ready": 0}
        s.send(Writer(S2C_ENTER).u16(0).raw(obf.u32(spot)).u8(0))
        s.send(room_packet(s.data["char"], room))
        s.send(Writer(S2C_MASTER).u16(MY_SEAT))
        log.info("pvp room of one at spot %d", spot)

    @role.on(C2S_CREATE)
    def create(s, pkt):
        s.send(Writer(S2C_CREATE))
        spot = s.data.get("target_spot")
        if spot_row(spot) is not None:
            open_room(s, spot)

    @role.on(C2S_MATCH_CREATE)
    def match_create(s, pkt):
        b = pkt.rest()
        at = b.find(0) + 1
        spot = obf.dec_u32(b[at:at + 4]) if at and len(b) >= at + 4 else None
        if spot_row(spot) is None:
            s.send(Writer(S2C_MATCH_CREATE).u16(CREATE_FAILED))
            return
        open_room(s, spot)
        s.send(Writer(S2C_MATCH_CREATE).u16(0).zeros(4))

    @role.on(C2S_MOVE)
    def move(s, pkt):
        room, b = s.data.get("pvproom"), pkt.rest()
        seat = struct.unpack_from("<H", b)[0] if len(b) >= 2 else None
        if room is None or seat is None or seat == room["seat"] or seat >= team_seats(room):
            constant(s, C2S_MOVE)
            return
        room["seat"] = seat
        s.send(Writer(S2C_MOVE).u16(0).u16(seat).u32(s.data["char"]["id"]))

    @role.on(C2S_READY)
    def ready(s, pkt):
        room = s.data.get("pvproom")
        if room is None:
            constant(s, C2S_READY)
            return
        room["ready"] = 1 if pkt.rest()[:1] == b"\x01" else 0
        s.send(Writer(S2C_READY).u16(0).u16(room["seat"]).u32(s.data["char"]["id"]).u8(0).u8(room["ready"]))

    @role.on(C2S_LEAVE)
    def leave(s, pkt):
        s.data.pop("pvproom", None)
        constant(s, C2S_LEAVE)

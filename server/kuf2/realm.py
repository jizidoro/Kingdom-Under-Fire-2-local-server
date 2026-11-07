"""The realm ("camp") transfer, and the answers of a world where no war runs: the realm war (Grand Clash), the guild
territory war, the field capture (Fortress Conquest) and the war rewards (planning/todo/CONTRACT-COMPLETE-PLAN.md
family 8; report planning/agents/reports/2026-11-05_contract-realm.md). Read 2026-11-05 from re/decomp/{c2s,s2c} and
the client image's disassembly; text ids are textsystem_eng's unless marked.

The realm transfer (CommonSubRealmInfo, scene 0x5f; NPC menus REALM_TRANS_A 0x33 / REALM_TRANS_B 0x34: Mason 963 and
Jade 6235 in Accolade, shown after quest 1160433; world.npc_menu's 0x5a49 list carries the "allowed" flag +0x3c):
  the button (0x140635480) refuses on the client first, each through the mapper 0x140634f80: +0x3c clear -> 0xac08
      "The camp is full. Cannot join." (0x1ddc); no realm (common+0xd0 == 0) -> 0xac06 and already in the menu's realm
      -> 0xac02, both "Cannot use it." (0x1ff4); in a guild (scene 0x20 +0x145) -> 0xac07 "Cannot switch camp while in
      a guild." (0x1dde). Then the cost: wartable %Realm_Trans_Cost[LV = hero level] (0x1418b9980, an exact lookup):
      a row -> box 0x1dda "Do you want to use %1% x%2% to switch the camp?" (NeedItem's name, Value) and, on Yes, need
      > the bag's count (0x140dc8190) -> 0x445 "Insufficient %1%. Available in the Diamond Shop under 'Cubic Shop'."
      (0x1ddd) with nothing sent (0x140634d81); no row -> box 0x1ddb "Do you want to switch the camp?", no cost. All
      50 rows (LV 1..50) ask 1 x 351400040 Camp Change Ticket (REALM_CHANGE): one comes in each class's Level-up
      Celebration Chest [Lv 30] (item_container groups 106..506, the end of the chain a new hero starts with); the
      Cubic shop's good 8128000 (10,000) is hidden today (cubicshop.HIDDEN).
  C2S 0x5a46 (builder 0x140635c30; not while +0x3d is pending): one T2-coded byte, realm = T1[b] & 3 (menu - 0x32:
      1 A "Protection Alliance", 2 B "Revolution Coalition", textui 0x1ecc / 0x1ecd; the upper bits are stack junk).
  S2C 0x5a47 (0x1406362b0): clears +0x3d; i16 (under 2 bytes crashes); 0 -> one coded byte (under 3 bytes crashes):
      common+0xd0 = T1[b] & 0x80000003, a table's rows are selected again for the realm (0x1418b6f60, flags 0x10000 A
      / 0x20000 B; which table is not read), window 0x1a (the main HUD) is refreshed, "You're a member of %1%."
      (0x1ff3) is printed and the realm window is hidden: no other push is needed.
      Non-zero -> the mapper's text (the codes above; any other only logs an assert) and the window stays open.
  The client never takes the ticket: the bag is resent. The realm is c["realm"], told at login in the start-game
  reply's P[0] (world.py start_game) and set first by the join 0x5a44 (world.realm_join).

No war runs (the four ends of the other 17 requests are in the report's table):
  - wartable %Season's four seasons ran 2018-04-29 .. 2018-10-07, before this build's service (2019-11-14, whose
    launch notes say the faction battle was cut); %Phase is the weekly cycle the client labels 0 "[Base Establishment
    Period]", 1 "[War Declaration Period]", 2 "[War Preparation Period]", 3 "[War Period]" (panel 0x140d963eb) and 4
    nothing: 4 is what WarManager's constructor (0x140a7ca80) and reset (0x140a7ced0) set and what clears the
    registration lists in the 0x10f8 handler. What the live server sent between seasons is in no table or capture.
  - The War Info map (WorldMap scene 0x6d, [TAB]: 0x140d37070) opens only when tutorial War_RvR3's quest 1160455
    is in the finished list (0x140833eb0 -> 0x140834040; else "You can move to the War Map after completing the War
    tutorial.", 0x2002) and questtable ships 1160451 / 53 / 55 as Use_Quest No: its nine requests (0x1100 0x1102
    0x1104 0x1106 0x1108 0x110a 0x1115 0x10fc 0x10fe) and the queue button (0x111a) cannot be sent. 0x111c and
    0x111e need WarManager+0x138, written non-zero only by a non-zero S2C 0x111f (0x111c also +0x1a4, the waiting
    spot of a 0x1116 success): the server's own pushes of a running war.
  - Window 0x4d (Fortress Conquest: 0x1262 the list, 0x1260 the application, box 0x13880) opens only from NPC menu
    FIELD_PK_APPLICATION, whose one NPC (944 Karon, Sunstruck) spawns on FinishedQuest 1, a Use_Quest No row.
    Window 0x5a (war rewards: 0x5a42, 0x5a40) opens only from NPC menu WAR_REWARD, which no npctable row has.
  Each still has its safe answer below (WAR_REPLIES), the client's own "not now" text where its handler has one.
"""
import functools

from . import items, obf, tables
from .net import journal, log
from .packet import OBOOL_FALSE, Writer

C2S_TRANSFER, S2C_TRANSFER = 0x5a46, 0x5a47
REALMS = (1, 2)                 # A "Protection Alliance", B "Revolution Coalition"
# 0x5a47 result codes (mapper 0x140634f80; 0xac08 "The camp is full." is never sent: wartable %Realm_UserAdmin's
# balance starts at 400 users)
TICKET_SHORT = 0x445            # "Insufficient %1%. Available in the Diamond Shop under 'Cubic Shop'."
SAME_REALM = 0xac02             # "Cannot use it."
NO_REALM = 0xac06               # "Cannot use it." (the transfer of a character that never joined)
IN_A_GUILD = 0xac07             # "Cannot switch camp while in a guild." (c["guild"], guild.py's)
UNKNOWN_REALM = 1               # a realm byte the menus cannot send: the client only logs an assert

# WarManager's result mapper 0x140a80620: 0xa404 / 0xa406..0xa408 -> 0x1dae; any code it does not know -> 0x1c64
# "Cannot perform the action now. Please try again later."
NO_WAR_NOW = 0xa404             # "Cannot participate in the war at the moment. Please check the war program."
NO_CAPTURE_NOW = 0x4416         # 0x1261's mapper 0x1405c4bb0: "Can't apply for Fortress Conquest at the moment."
WAR_PHASE_NONE = 4              # WarManager+8 as constructed: no period label, the registration lists cleared


def _refuse(code):
    return code.to_bytes(2, "little")


# request -> (reply, body): what a server with no war and no capture answers. Only 0x10f7 is sent by this build's
# data (every world-map entry); the others are kept answered so a hand-made request finds a well-formed reply.
WAR_REPLIES = {
    # 0x10f8 (0x140a7db80, WarManager): one 0x29-byte read (shorter crashes): +0 u64, +8 u64, +0x10 i64 (clamped >= 0),
    # +0x18 u8 phase, +0x19 u64, +0x21 u64 (the phase's times). Phase 4 keeps the manager as constructed; the 41 zero
    # bytes sent before said phase 0, the "[Base Establishment Period]"
    0x10f7: (0x10f8, bytes(0x18) + bytes([WAR_PHASE_NONE]) + bytes(0x10)),
    # War Info map message boxes (0x140d85c50): 0x1d9b give up the territory -> 0x10fc; 0x1d98 / 0x1da5 declare war
    # (wartable %Spot Cost against the guild's points) -> 0x10fe. 0x10fd (0x140a7f440) / 0x10ff (0x140a7f300): i16
    # through the mapper; 0 -> 5 more bytes (the coded spot)
    0x10fc: (0x10fd, _refuse(NO_WAR_NOW)),
    0x10fe: (0x10ff, _refuse(NO_WAR_NOW)),
    # spot menu 5 "War Program" / 7 "Battlefield info" / 6 "Enter battlefield" -> 0x1100; 0x1101 (0x140a7f990): i16
    # through the mapper (the text, popup 0x6f closed); 0 -> three lists
    0x1100: (0x1101, _refuse(NO_WAR_NOW)),
    # spot menu 0 "Region info"; 0x1103 (0x140a7f570) has no result: 9 bytes (obool occupied, u64 a time), then 13
    # bytes + 2 cstr if occupied, else 1 byte; every part is read unchecked. Nobody holds a territory: "unoccupied"
    0x1102: (0x1103, bytes([OBOOL_FALSE]) + bytes(8) + bytes(1)),
    # spot menu 1 "Garrison info" (a guild member's, of an owned spot; not yet paid for: box 0x1d97, %Spot SearchGold
    # gold -> 0x110a), its player pick 0x1106 (no reply exists: world.py ignores it) and troop details 0x1108. 0x1105
    # (0x140d92cb0), 0x1109 (0x140d93b10), 0x110b (0x140a7eff0): i16, silent unless 0 (0 lists / marks the spot paid)
    0x1104: (0x1105, _refuse(1)),
    0x1108: (0x1109, _refuse(1)),
    0x110a: (0x110b, _refuse(1)),
    # the battlefield queue after a 0x1101 (WarManager 0x140a7da30, phase 3 only); 0x1116 (0x140a7f7f0): i16 through
    # the mapper; 0 -> "Waiting to enter Guild War."
    0x1115: (0x1116, _refuse(NO_WAR_NOW)),
    # the Grand Clash queue (panel 0x6c's button, hidden until S2C 0x1153 names a clash) and leaving it; 0x111b
    # (0x140a80010) / 0x111d (0x140a800d0): i16, silent unless 0 (0 -> u8 kind and "Registered in the Grand Clash
    # queue." / "Unregistered from the queue.")
    0x111a: (0x111b, _refuse(1)),
    0x111c: (0x111d, _refuse(1)),
    # the queue poll (every 5 s while WarManager+0x138 > 0); 0x111f (0x140a80210): 4 bytes (shorter crashes), the
    # i16 is the new state: 0 ends the polling
    0x111e: (0x111f, bytes(4)),
    # Fortress Conquest: the application (box 0x13880 answered Yes, 0x1405c29f0); 0x1261 (0x1405c2b40): i16; 0 ->
    # "Application for Fortress Conquest has been completed."; else the mapper's text (1 was silent)
    0x1260: (0x1261, _refuse(NO_CAPTURE_NOW)),
    # the applicants' list, one request a page; 0x1263 (0x1405c2db0): i16; 0 -> 9 bytes; then, for every result,
    # u8 n + n * (7 bytes, cstr, cstr). Non-zero shows nothing: the window stays empty
    0x1262: (0x1263, _refuse(1) + bytes(1)),
    # the war reward claim; 0x5a41 (0x140667ea0): i16; 0 -> a coded item id (6 bytes in all); 0x6402 bag full, 0xa41a
    # "You obtained the reward already.", 0xa41b "You used up all possible rewards.", other 0x1c64; it then asks the
    # list again. No code says "no such reward": the generic one
    0x5a40: (0x5a41, _refuse(1)),
    # the war reward list; 0x5a43 (0x140667b30): u8 grade (read unchecked: an empty body crashes), u8 n, n * 5 (state,
    # coded reward id). n = 0 -> "Cannot receive rewards because there's no territory that's been occupied." (0x1df2)
    # and the window closes: the client's own empty answer
    0x5a42: (0x5a43, bytes(2)),
}


@functools.cache
def transfer_costs():
    """{hero level: (item code, count)} of wartable %Realm_Trans_Cost."""
    return {int(r["LV"]): (int(r["NeedItem"]), int(r["Value"]))
            for r in tables.sections("wartable")["Realm_Trans_Cost"]}


def transfer_cost(level):
    """What a transfer takes at this hero level, (item code, count); None where the table has no row (the client
    then asks box 0x1ddb and the transfer is free)."""
    return transfer_costs().get(level)


def held(c, code):
    """How many of an item the bag holds (the client's count 0x140dc8190 over the item's bag range)."""
    return sum(it["count"] for it in c.get("bag", []) if it["code"] == code)


def transfer_refusal(c, realm):
    """The 0x5a47 code that refuses this character's transfer to `realm`, in the client's own order (0x140635480);
    0 when it may go."""
    if realm not in REALMS:
        return UNKNOWN_REALM
    if not c.get("realm"):
        return NO_REALM
    if c["realm"] == realm:
        return SAME_REALM
    if c.get("guild"):
        return IN_A_GUILD
    cost = transfer_cost(c.get("level", 1))
    if cost and held(c, cost[0]) < cost[1]:
        return TICKET_SHORT
    return 0


def make(role, state):
    from . import world

    role.empty_replies(WAR_REPLIES)

    @role.on(C2S_TRANSFER)
    def transfer(s, pkt):
        b = pkt.rest()
        realm = obf.T1[b[0]] & 3 if b else 0
        c = s.data["char"]
        refused = transfer_refusal(c, realm)
        if refused:
            log.info("realm transfer to %d refused: %#x (realm %s, level %s)", realm, refused, c.get("realm"),
                     c.get("level", 1))
            s.send(Writer(S2C_TRANSFER).u16(refused))
            return
        code, count = transfer_cost(c.get("level", 1)) or (0, 0)
        slots, left = [], count
        for it in sorted((it for it in c.get("bag", []) if it["code"] == code), key=lambda it: -it["slot"]):
            n = min(left, it["count"])              # the last stacks first, as world.remove_item
            if n:
                world.take_serial(c, it["serial"], n)
                slots.append(it["slot"])
                left -= n
        if count:
            journal("item", ev="spend", code=code, name=items.name(code), n=count, why="realm transfer")
        was, c["realm"] = c["realm"], realm
        state.save()
        s.send(Writer(S2C_TRANSFER).u16(0).u8(obf.via_t1(realm)))
        if slots:
            world.send_cargo(s, changed_slots=slots)
        log.info("realm transfer %d -> %d (%d x %d taken)", was, realm, count, code)

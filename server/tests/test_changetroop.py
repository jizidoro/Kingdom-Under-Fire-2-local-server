"""The battle HUD's troop slots on a %Point spot (BattleFieldSubChangeTroop, sub-scene 0x78; family 4 of
planning/todo/CONTRACT-COMPLETE-PLAN.md): Battle Points, troop change, upgrade, timed revival, summon and withdraw,
each through its registered handler. The numbers are the tables' (spottable %Point, trooptable, troopupgrade,
herotable, nptrooptable); the byte places are the client's reply handlers' (changetroop.py's docstring).
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import changetroop as ct, combat, game, obf, status, troops
from kuf2.packet import OBOOL_FALSE, OBOOL_TRUE
from test_army import NoSave, army, entered, pkt

STORY, RIFT, INVASION, PVP_AI, PLAIN = 10370, 10335, 20911, 20955, 10234
ME = struct.pack("<H", game.MY_SLOT)
INFANTRY, BOWMEN = 1, 2                      # contract sets: troop 100 (change 200, upgrade type 1001: 60 / 90 / 150)
                                             # and 113 (change 200, type 2004: 80 / 120 / 200)


def room(spot, sets=(INFANTRY, BOWMEN), deck=(1, 2, 3, 4), points=None):
    """A room entered on spot with one troop a contract set in main-deck slots `deck`, the family's handlers wired
    as the coordinator will (after game.make's)."""
    c, ts = army(*sets, deck=deck)
    role, s = entered(spot, c)
    ct.make(role, NoSave())
    restart(s, points)
    s.sent.clear()
    return role, s, ts


def restart(s, points=None):
    """The room back at its first second. game.load_progress runs changetroop.start itself (wired in 2026-11-05), and
    the fake scheduler's drain in test_army.entered then ran the timed income hundreds of times: a fresh record, the
    stale income timers dropped, the start again."""
    s.data.pop("changetroop", None)
    s.pending[:] = [(d, f) for d, f in s.pending if getattr(f, "__name__", "") != "income"]
    if points is not None:
        ct.room(s)["points"] = points
    ct.start(s)


def ask(role, s, proto, body=b""):
    before = len(s.sent)
    role.handlers[proto](s, pkt(proto, body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def only(replies, proto):
    got = [b for p, b in replies if p == proto]
    assert len(got) == 1, replies
    return got[0]


def pushed_points(replies):
    return [struct.unpack_from("<I", b, 5)[0] for p, b in replies if p == ct.S2C_POINTS]


def coded(uid):
    """A coded u16 as the client writes it (0x50f0's uids)."""
    return bytes([obf.T2[uid >> 8], obf.T1[uid & 255]])


def age(s, kind, uid, secs):
    ct.room(s)[kind][uid]["at"] -= secs


def wipe(s, uid):
    t = s.data["battle"].troops[uid]
    if t["hero"]:
        t["hp"] = 0
    else:
        t["units"] = [0] * len(t["units"])


def test_the_seventeen_requests_have_handlers_and_the_constants_stay_games():
    role = game.make(NoSave(), 0)                       # game.make wires the module in (2026-11-05)
    mine = {p for p, fn in role.handlers.items() if fn.__module__ == "kuf2.changetroop"}
    assert mine == {0x50ec, 0x50f0, 0x50f2, 0x50f7, 0x50f9, 0x5101, 0x5103, 0x5105, 0x5108, 0x510a, 0x510c, 0x5120,
                    0x5122, 0x5124, 0x5126, 0x5128, 0x512a}
    assert not mine & set(game.EMPTY_REPLIES)           # none had a constant answering it
    assert {0x511e, 0x512c, 0x512e} <= set(game.EMPTY_REPLIES)   # judged CONSTANT / SOLO: the constants stay game's
    assert all(role.handlers[p].__name__.startswith("empty_reply") for p in (0x511e, 0x512c, 0x512e))


def test_which_spots_open_the_hud_and_take_a_reserve():
    # GameStateBattleField::OnEnter 0x140cee71a: a %Point row with Troop_Change_Able or Troop_Upgrade_Able
    assert ct.opens(STORY) and ct.opens(RIFT) and ct.opens(INVASION) and ct.opens(PVP_AI)
    assert not ct.opens(PLAIN) and not ct.opens(20908)          # no row; a row with neither
    c, ts = army(INFANTRY, BOWMEN, INFANTRY, deck=(1, 4, 6))
    # the rift takes main-deck slots 1..3 (one filled) and Limit_SubTroop 7 of the rest; 10370 has Limit_SubTroop 0
    assert ct.reserve_for(c, RIFT, 0, {1: ts[0]}) == {4: ts[1], 6: ts[2]}
    assert ct.reserve_for(c, STORY, 0, {1: ts[0]}) == {} and ct.reserve_for(c, PLAIN, 0, {1: ts[0]}) == {}


def test_the_points_start_at_the_rows_default_and_come_by_time_and_kills():
    c, _ = army(INFANTRY)
    role, s = entered(STORY, c)                          # the room's start pushes them (game.load_progress)
    # 0x50d8 (0x140d1c7f0 -> 0x140d0b610): 11 bytes, the points at +5; 10370 BattlePointDefault 300, no timed income
    # 9 bytes here crashed the native client on its first mission with points (0x140d1c836, 2026-11-05: the reader
    # asks for 11, gets nothing and reads null + 5)
    assert [bytes(w.buf) for w in s.sent if w.proto == ct.S2C_POINTS] == [bytes(5) + struct.pack("<I", 300) + bytes(2)]
    s.sent.clear()
    ct.start(s)                                          # once a room
    assert not s.sent
    assert not [d for d, _ in s.pending if d == 5]
    # nptrooptable BattlePoint x %Point EnermyBattlePointRevision (1), the commander's npleadertable BattlePoint too
    from kuf2 import zone
    troop = next(t for t in zone.for_spot(STORY)["NPCTroopInfoData"]
                 if float((zone.np_troop(t["TroopTableID"]) or {}).get("BattlePoint", 0) or 0) > 0)
    worth = int(float(zone.np_troop(troop["TroopTableID"])["BattlePoint"]))
    assert ct.on_kill(s, troop["TroopTableID"]) == worth and ct.points(s) == 300 + worth
    ct.set_points(s, 5000)
    assert ct.points(s) == 2000                          # MaxBattlePoint
    # the invasion battle: 0 at the start, 10 every 5 s
    role, s = entered(INVASION, c)
    s.data.pop("changetroop", None)                      # the room's start ran it, and the drain its income: again
    s.sent.clear()
    s.pending.clear()
    ct.start(s)
    assert [d for d, _ in s.pending] == [5.0]
    s.pending.pop()[1]()
    assert pushed_points([(w.proto, bytes(w.buf)) for w in s.sent]) == [0, 10] and [d for d, _ in s.pending] == [5.0]
    # a spot with no %Point row: no points, no push
    role, s = entered(PLAIN, c)
    s.sent.clear()
    ct.start(s)
    assert not s.sent and ct.on_kill(s, 134060) == 0


def test_a_troop_upgrades_for_its_types_points_and_holds_the_rows_statuses():
    role, s, (inf, bow) = room(STORY)
    assert set(s.data["deck"]) == {1, 2}
    before = s.data["battle"].troops[1]["unit_max"]
    # 0x5101: u32 type, u32 level wanted, u16 uid -> 0x5102 (8 bytes): i16 0, u32 the level, u16 uid; 60 points taken
    got = ask(role, s, ct.C2S_UPGRADE, struct.pack("<IIH", 1001, 1, 1))
    assert pushed_points(got) == [240]
    assert only(got, ct.S2C_UPGRADE) == struct.pack("<HIH", 0, 1, 1)
    # its timer (TroopUpgradeCastTime 3 s) has not run on the server: 0x2c4f, the client asks again in 0.5 s
    assert only(ask(role, s, ct.C2S_UPGRADE_DONE, struct.pack("<IIH", 1001, 1, 1)), ct.S2C_UPGRADE_DONE) \
        == struct.pack("<HIH", ct.NOT_YET, 1, 1)
    assert ct.room(s)["levels"] == {}
    age(s, "upgrade", 1, 3)
    got = ask(role, s, ct.C2S_UPGRADE_DONE, struct.pack("<IIH", 1001, 1, 1))
    assert only(got, ct.S2C_UPGRADE_DONE) == struct.pack("<HIH", 0, 1, 1)
    assert ct.room(s)["levels"] == {1: 1}
    held = status.holding(s, 1)
    assert held[800280]["level"] == 1 and held[800290]["level"] == 1        # ATTACK +10 %, HP_MAX +10 %
    assert [p for p, _ in got] == [ct.S2C_UPGRADE_DONE, combat.S2C_STATUS_ADD, combat.S2C_STATUS_ADD]   # 0x5074 x2
    assert s.data["battle"].troops[1]["unit_max"] == round(before * 1.1)
    assert s.data["battle"].troops[1]["units"] == [before] * 10              # the cap rises, nothing is healed
    # level 2 costs 90, its statuses replace level 1's (+30 %)
    assert pushed_points(ask(role, s, ct.C2S_UPGRADE, struct.pack("<IIH", 1001, 2, 1))) == [150]
    age(s, "upgrade", 1, 3)
    ask(role, s, ct.C2S_UPGRADE_DONE, struct.pack("<IIH", 1001, 2, 1))
    assert status.holding(s, 1)[800290]["level"] == 2
    assert s.data["battle"].troops[1]["unit_max"] == round(before * 1.3)


def test_an_upgrade_is_refused_without_taking_points_and_a_cancel_gives_them_back():
    role, s, _ = room(STORY)
    refused = lambda body: only(ask(role, s, ct.C2S_UPGRADE, body), ct.S2C_UPGRADE)[:2] == struct.pack("<H", ct.REFUSED)
    assert refused(struct.pack("<IIH", 2004, 1, 1))             # the bowmen's type on the infantry
    assert refused(struct.pack("<IIH", 1001, 2, 1))             # not its next level
    assert refused(struct.pack("<IIH", 1001, 1, 7))             # no such troop
    assert refused(struct.pack("<IIH", 1001, 4, 1))             # no such row
    ct.room(s)["points"] = 59
    assert refused(struct.pack("<IIH", 1001, 1, 1)) and ct.points(s) == 59          # 60 needed
    ct.room(s)["points"] = 300
    assert not refused(struct.pack("<IIH", 2004, 1, 2)) and ct.points(s) == 220     # the bowmen: 80
    assert refused(struct.pack("<IIH", 2004, 1, 2))             # already upgrading
    # 0x5103 -> 0x5104 (8 bytes always): u16 0, u32, u16 uid; the 80 come back
    got = ask(role, s, ct.C2S_UPGRADE_CANCEL, struct.pack("<IIH", 2004, 1, 2))
    assert only(got, ct.S2C_UPGRADE_CANCEL) == struct.pack("<HIH", 0, 1, 2) and pushed_points(got) == [300]
    assert only(ask(role, s, ct.C2S_UPGRADE_CANCEL, struct.pack("<IIH", 2004, 1, 2)), ct.S2C_UPGRADE_CANCEL) \
        == struct.pack("<HIH", ct.REFUSED, 1, 2)
    assert only(ask(role, s, ct.C2S_UPGRADE_DONE, struct.pack("<IIH", 2004, 1, 2)), ct.S2C_UPGRADE_DONE) \
        == struct.pack("<HIH", ct.REFUSED, 1, 2)
    # a rift lets troops change, not upgrade (Troop_Upgrade_Able False)
    role, s, _ = room(RIFT)
    assert only(ask(role, s, ct.C2S_UPGRADE, struct.pack("<IIH", 1001, 1, 1)), ct.S2C_UPGRADE)[:2] == b"\x01\x00"
    assert ct.points(s) == 300


def test_a_reserve_troop_enters_an_empty_slot_when_its_change_ends():
    role, s, (inf, bow) = room(RIFT, deck=(1, 4))
    assert set(s.data["deck"]) == {1} and ct.reserve(s) == {4: bow}
    # 0x50f7: u16 uid in the slot (0xffff), u16 reserve uid, u8 slot -> 0x50f8 (9 bytes): i16 0, u16 player, the 5
    req = struct.pack("<HHB", ct.NO_TROOP, 4, 2)
    got = ask(role, s, ct.C2S_CHANGE_START, req)
    assert pushed_points(got) == [100]                           # trooptable TroopChangePoint 200 of the 300
    assert only(got, ct.S2C_CHANGE_START) == bytes(2) + ME + req
    assert 4 not in s.data["battle"].troops
    # 0x50ec: u8 slot, u16 uid -> 0x50ed: i16 0, u16 uid, u8 slot, u16 player; the troop is in the room's deck and
    # battle, with its passives' statuses
    got = ask(role, s, ct.C2S_CHANGE_ENTER, struct.pack("<BH", 2, 4))
    assert got[0] == (ct.S2C_CHANGE_ENTER, bytes(2) + struct.pack("<HB", 4, 2) + ME)
    assert set(s.data["deck"]) == {1, 4} and ct.reserve(s) == {}
    rec = s.data["battle"].troops[4]
    r = troops.room_row(s.data["char"], bow, live=False)
    assert rec["units"] == [troops.unit_hp(r)] * r["UNIT_COUNT"] and rec["c"]["team"] == game.PLAYER_TEAM
    assert ct.room(s)["change"] == {}


def test_a_reserve_troop_replaces_a_slots_troop_which_then_cools_down():
    role, s, (inf, bow) = room(RIFT, deck=(1, 4), points=1000)
    hurt = s.data["battle"].troops[1]
    hurt["units"][0] = 1
    req = struct.pack("<HHB", 1, 4, 1)
    assert only(ask(role, s, ct.C2S_CHANGE_START, req), ct.S2C_CHANGE_START) == bytes(2) + ME + req
    # 0x50f0: u8 slot, coded u16 old, coded u16 new -> 0x50f1: i16 0, u8 slot, u16 new, u16 old, u16 player
    got = ask(role, s, ct.C2S_CHANGE_REPLACE, bytes([1]) + coded(1) + coded(4))
    assert got[0] == (ct.S2C_CHANGE_REPLACE, bytes(2) + struct.pack("<BHH", 1, 4, 1) + ME)
    assert set(s.data["deck"]) == {4} and ct.reserve(s) == {1: inf}
    assert 1 not in s.data["battle"].troops and ct.room(s)["bench"][1] is hurt
    # the replaced troop cools down (trooptable TroopChangeCooldown 1 s): no change back until it has
    back = struct.pack("<HHB", 4, 1, 1)
    assert only(ask(role, s, ct.C2S_CHANGE_START, back), ct.S2C_CHANGE_START)[:2] == b"\x01\x00"
    assert ct.points(s) == 800
    ct.room(s)["cooldown"][1] -= 1
    assert only(ask(role, s, ct.C2S_CHANGE_START, back), ct.S2C_CHANGE_START)[:2] == bytes(2)
    ask(role, s, ct.C2S_CHANGE_REPLACE, bytes([1]) + coded(4) + coded(1))
    assert s.data["battle"].troops[1] is hurt and hurt["units"][0] == 1      # it comes back as it left


def test_a_change_is_refused_or_cancelled_with_the_points_whole():
    role, s, (inf, bow, third) = room(RIFT, sets=(INFANTRY, BOWMEN, INFANTRY), deck=(1, 4, 5))
    refused = lambda body: only(ask(role, s, ct.C2S_CHANGE_START, body), ct.S2C_CHANGE_START) \
        == struct.pack("<H", ct.REFUSED) + ME + body
    assert refused(struct.pack("<HHB", ct.NO_TROOP, 1, 2))      # deployed already
    assert refused(struct.pack("<HHB", ct.NO_TROOP, 6, 2))      # no such troop
    assert refused(struct.pack("<HHB", ct.NO_TROOP, 4, 4))      # no such slot
    assert refused(struct.pack("<HHB", 5, 4, 2))                # the slot's troop is not deployed
    ct.room(s)["points"] = 199
    assert refused(struct.pack("<HHB", ct.NO_TROOP, 4, 2)) and ct.points(s) == 199
    ct.room(s)["points"] = 300
    req = struct.pack("<HHB", ct.NO_TROOP, 4, 2)
    assert not refused(req) and ct.points(s) == 100
    assert refused(req)                                         # pending already
    # 0x50f9: u16 uid, u8 slot -> 0x50fa (7 bytes always): u16 0, u16 player, u16 uid, u8 slot; the 200 come back
    got = ask(role, s, ct.C2S_CHANGE_CANCEL, struct.pack("<HB", 4, 2))
    assert only(got, ct.S2C_CHANGE_CANCEL) == bytes(2) + ME + struct.pack("<HB", 4, 2) and pushed_points(got) == [300]
    assert only(ask(role, s, ct.C2S_CHANGE_CANCEL, struct.pack("<HB", 4, 2)), ct.S2C_CHANGE_CANCEL) \
        == struct.pack("<H", ct.REFUSED) + ME + struct.pack("<HB", 4, 2)
    # a timer's end the server knows no change for: refused, and the client's entry dropped (0x50fa 0)
    got = ask(role, s, ct.C2S_CHANGE_ENTER, struct.pack("<BH", 2, 4))
    assert got == [(ct.S2C_CHANGE_ENTER, struct.pack("<H", ct.REFUSED)),
                   (ct.S2C_CHANGE_CANCEL, bytes(2) + ME + struct.pack("<HB", 4, 2))]
    assert set(s.data["deck"]) == {1}


def test_an_empty_slot_is_taken_only_within_the_spots_troop_limit():
    # the PvP against AI tutorial 20954 takes one troop (Limit_Troop_1); a bare battle room has no deck
    role, s, _ = room(RIFT, sets=(INFANTRY, BOWMEN, INFANTRY, BOWMEN), deck=(1, 4, 5, 6), points=2000)
    assert ct.deploy_cap(s) == 3
    for uid, slot in ((4, 2), (5, 3)):
        assert only(ask(role, s, ct.C2S_CHANGE_START, struct.pack("<HHB", ct.NO_TROOP, uid, slot)),
                    ct.S2C_CHANGE_START)[:2] == bytes(2)
    # two on their way and one deployed: the third reserve finds no free slot (the client's text 0x11198)
    assert only(ask(role, s, ct.C2S_CHANGE_START, struct.pack("<HHB", ct.NO_TROOP, 6, 2)),
                ct.S2C_CHANGE_START)[:2] == b"\x01\x00"


def test_two_deployed_troops_swap_slots_by_an_echo():
    role, s, _ = room(STORY)
    # 0x50f2: u16 moved, u16 in the target slot, u8 target slot, u8 previous slot -> 0x50f3: i16 0 and the 6 bytes
    req = struct.pack("<HHBB", 1, 2, 2, 1)
    assert ask(role, s, ct.C2S_SWAP_SLOTS, req) == [(ct.S2C_SWAP_SLOTS, bytes(2) + req)]
    assert ask(role, s, ct.C2S_SWAP_SLOTS, struct.pack("<HHBB", 1, ct.NO_TROOP, 3, 2)) \
        == [(ct.S2C_SWAP_SLOTS, bytes(2) + struct.pack("<HHBB", 1, ct.NO_TROOP, 3, 2))]
    assert ask(role, s, ct.C2S_SWAP_SLOTS, struct.pack("<HHBB", 5, 2, 2, 1)) \
        == [(ct.S2C_SWAP_SLOTS, struct.pack("<H", ct.REFUSED))]


def hero_room(spot):
    """A bare battle room (a PVP_POINT map has no zone: no deck) with the hero dead."""
    c, _ = army(INFANTRY)
    role, s = entered(spot, c)
    ct.make(role, NoSave())
    restart(s)
    wipe(s, 0)
    s.sent.clear()
    return role, s


def test_the_timed_revival_is_paid_in_points_and_revives_when_its_timer_has_run():
    role, s = hero_room(PVP_AI)
    assert ct.points(s) == 3000 and game.revival(PVP_AI) == ("CUBIC", -1)    # no %Revival row: the 0x5108 path
    # 0x5108: u16 uid -> 0x5109 (4 bytes): u16 uid, i16 0; herotable BattlePoint 500 x TroopRevivalRevision 1
    got = ask(role, s, ct.C2S_REVIVAL, struct.pack("<H", 0))
    assert only(got, ct.S2C_REVIVAL) == struct.pack("<HH", 0, 0) and pushed_points(got) == [2500]
    assert only(ask(role, s, ct.C2S_REVIVAL, struct.pack("<H", 0)), ct.S2C_REVIVAL) == struct.pack("<HH", 0, ct.REFUSED)
    # 0x510c before TroopRevivalCastTime (3 s): 0x510d 0x2c4f; after it: 0, the hero back whole, one revival used
    assert only(ask(role, s, ct.C2S_REVIVAL_DONE, struct.pack("<H", 0)), ct.S2C_REVIVAL_DONE) \
        == struct.pack("<HH", 0, ct.NOT_YET)
    assert s.data["battle"].troops[0]["hp"] == 0
    age(s, "revival", 0, 3)
    got = ask(role, s, ct.C2S_REVIVAL_DONE, struct.pack("<H", 0))
    assert got[0] == (ct.S2C_REVIVAL_DONE, struct.pack("<HH", 0, 0))
    hero = s.data["battle"].troops[0]
    assert hero["hp"] == hero["max"] and s.data["revivals"] == 1
    assert {game.S2C_TROOP_DOWN, game.S2C_TROOP_BACK, game.S2C_TROOP_HP} <= {p for p, _ in got}
    assert ask(role, s, game.C2S_REVIVE_COUNT) == [(game.S2C_REVIVE_COUNT, struct.pack("<I", 1))]
    # alive: refused, nothing taken
    assert only(ask(role, s, ct.C2S_REVIVAL, struct.pack("<H", 0)), ct.S2C_REVIVAL) == struct.pack("<HH", 0, ct.REFUSED)
    assert ct.points(s) == 2500


def test_a_timed_revival_cancelled_gives_its_points_back_and_the_spots_limit_holds():
    role, s = hero_room(PVP_AI)
    ask(role, s, ct.C2S_REVIVAL, struct.pack("<H", 0))
    got = ask(role, s, ct.C2S_REVIVAL_CANCEL, struct.pack("<H", 0))
    assert only(got, ct.S2C_REVIVAL_CANCEL) == struct.pack("<HH", 0, 0) and pushed_points(got) == [3000]
    assert only(ask(role, s, ct.C2S_REVIVAL_CANCEL, struct.pack("<H", 0)), ct.S2C_REVIVAL_CANCEL) \
        == struct.pack("<HH", 0, ct.REFUSED)
    assert only(ask(role, s, ct.C2S_REVIVAL_DONE, struct.pack("<H", 0)), ct.S2C_REVIVAL_DONE) \
        == struct.pack("<HH", 0, ct.REFUSED)
    # a deployed troop on a rift: its change cost x TroopRevivalRevision 0 = free; the content's Limit_Revive 5 holds
    role, s, _ = room(RIFT)
    wipe(s, 1)
    s.data["revivals"] = 5
    assert only(ask(role, s, ct.C2S_REVIVAL, struct.pack("<H", 1)), ct.S2C_REVIVAL) == struct.pack("<HH", 1, ct.REFUSED)
    s.data["revivals"] = 4
    got = ask(role, s, ct.C2S_REVIVAL, struct.pack("<H", 1))
    assert only(got, ct.S2C_REVIVAL) == struct.pack("<HH", 1, 0) and pushed_points(got) == []
    age(s, "revival", 1, 0)                              # TroopRevivalCastTime 0 there
    got = ask(role, s, ct.C2S_REVIVAL_DONE, struct.pack("<H", 1))
    assert got[0] == (ct.S2C_REVIVAL_DONE, struct.pack("<HH", 1, 0)) and s.data["revivals"] == 5
    assert all(s.data["battle"].troops[1]["units"])


def test_a_reserve_troop_is_summoned_to_the_hero_and_withdrawn_for_free():
    role, s, (inf, bow) = room(INVASION, deck=(1, 4), points=500)
    place = bytes.fromhex("0102030405")
    # 0x5120: 5 packed x/z, u16 uid -> 0x5121: i16 0, the 5, u16 uid, u16 player; its change cost taken
    got = ask(role, s, ct.C2S_SUMMON, place + struct.pack("<H", 4))
    assert only(got, ct.S2C_SUMMON) == bytes(2) + place + struct.pack("<H", 4) + ME and pushed_points(got) == [300]
    assert only(ask(role, s, ct.C2S_SUMMON, place + struct.pack("<H", 4)), ct.S2C_SUMMON) == b"\x01\x00"
    # 0x5124 -> 0x5125 (11 bytes always): i16 0, the 5, u16 uid, u16 player
    got = ask(role, s, ct.C2S_SUMMON_DONE, place + struct.pack("<H", 4))
    assert got[0] == (ct.S2C_SUMMON_DONE, bytes(2) + place + struct.pack("<H", 4) + ME)
    # the units' TROOP_SUMMON action: only 0x5135 plays it (u16 uid, obool TRUE), last, the troop standing
    assert got[-1] == (ct.S2C_SUMMON_SHOW, struct.pack("<H", 4) + bytes([OBOOL_TRUE]))
    assert set(s.data["deck"]) == {1, 4} and ct.room(s)["summoned"] == {4} and 4 in s.data["battle"].troops
    # 0x5126 -> 0x5127: i16 0, u16 uid, u16 player; 0x512a -> 0x512b (6 bytes always); nothing paid or refunded
    assert ask(role, s, ct.C2S_WITHDRAW, struct.pack("<H", 4)) \
        == [(ct.S2C_WITHDRAW, bytes(2) + struct.pack("<H", 4) + ME)]
    got = ask(role, s, ct.C2S_WITHDRAW_DONE, struct.pack("<H", 4))
    assert got[:2] == [(ct.S2C_SUMMON_SHOW, struct.pack("<H", 4) + bytes([OBOOL_FALSE])),
                       (ct.S2C_WITHDRAW_DONE, bytes(2) + struct.pack("<H", 4) + ME)]    # TROOP_UNSUMMON, then disabled
    assert set(s.data["deck"]) == {1} and ct.reserve(s) == {4: bow} and ct.room(s)["summoned"] == set()
    assert ct.points(s) == 300 and 4 not in s.data["battle"].troops


def test_summon_and_withdraw_cancel_and_a_dead_troop_is_summoned_whole():
    role, s, (inf, bow) = room(INVASION, deck=(1, 4), points=500)
    place = bytes(5)
    ask(role, s, ct.C2S_SUMMON, place + struct.pack("<H", 4))
    # 0x5122 -> 0x5123 (4 bytes always): i16 0, u16 uid; the points back
    got = ask(role, s, ct.C2S_SUMMON_CANCEL, struct.pack("<H", 4))
    assert only(got, ct.S2C_SUMMON_CANCEL) == struct.pack("<HH", 0, 4) and pushed_points(got) == [500]
    assert ask(role, s, ct.C2S_SUMMON_CANCEL, struct.pack("<H", 4)) \
        == [(ct.S2C_SUMMON_CANCEL, struct.pack("<HH", 1, 4))]
    assert ask(role, s, ct.C2S_SUMMON_DONE, place + struct.pack("<H", 4)) \
        == [(ct.S2C_SUMMON_DONE, struct.pack("<H", 1) + place + struct.pack("<H", 4) + ME)]
    # a withdrawal called off: 0x5128 -> 0x5129 (4 bytes always); the troop stays
    assert ask(role, s, ct.C2S_WITHDRAW, struct.pack("<H", 1))[0][1][:2] == bytes(2)
    assert ask(role, s, ct.C2S_WITHDRAW_CANCEL, struct.pack("<H", 1)) \
        == [(ct.S2C_WITHDRAW_CANCEL, struct.pack("<HH", 0, 1))]
    assert ask(role, s, ct.C2S_WITHDRAW_DONE, struct.pack("<H", 1)) \
        == [(ct.S2C_WITHDRAW_DONE, struct.pack("<HH", 1, 1) + ME)]
    assert set(s.data["deck"]) == {1}
    # the infantry falls, is withdrawn, and summoned again: back whole (the official notes), revived on the client
    wipe(s, 1)
    ask(role, s, ct.C2S_WITHDRAW, struct.pack("<H", 1))
    ask(role, s, ct.C2S_WITHDRAW_DONE, struct.pack("<H", 1))
    assert ct.wiped(s, 1) and set(s.data["deck"]) == set()
    ask(role, s, ct.C2S_SUMMON, place + struct.pack("<H", 1))
    got = ask(role, s, ct.C2S_SUMMON_DONE, place + struct.pack("<H", 1))
    assert all(s.data["battle"].troops[1]["units"]) and not ct.wiped(s, 1)
    assert {game.S2C_TROOP_DOWN, combat.S2C_UNIT_LIVE, game.S2C_TROOP_HP} <= {p for p, _ in got}
    # a spot that lets no troop be summoned (the rifts)
    role, s, _ = room(RIFT, deck=(1, 4), points=500)
    assert ask(role, s, ct.C2S_SUMMON, place + struct.pack("<H", 4)) == [(ct.S2C_SUMMON, b"\x01\x00")]


@pytest.mark.parametrize("proto, body, reply, least", [
    (ct.C2S_CHANGE_START, struct.pack("<HHB", 9, 9, 9), ct.S2C_CHANGE_START, 9),
    (ct.C2S_CHANGE_ENTER, struct.pack("<BH", 9, 9), ct.S2C_CHANGE_ENTER, 2),
    (ct.C2S_CHANGE_REPLACE, bytes([9]) + coded(9) + coded(8), ct.S2C_CHANGE_REPLACE, 2),
    (ct.C2S_SWAP_SLOTS, struct.pack("<HHBB", 9, 8, 9, 9), ct.S2C_SWAP_SLOTS, 2),
    (ct.C2S_CHANGE_CANCEL, struct.pack("<HB", 9, 9), ct.S2C_CHANGE_CANCEL, 7),
    (ct.C2S_UPGRADE, struct.pack("<IIH", 9, 9, 9), ct.S2C_UPGRADE, 8),
    (ct.C2S_UPGRADE_CANCEL, struct.pack("<IIH", 9, 9, 9), ct.S2C_UPGRADE_CANCEL, 8),
    (ct.C2S_UPGRADE_DONE, struct.pack("<IIH", 9, 9, 9), ct.S2C_UPGRADE_DONE, 8),
    (ct.C2S_REVIVAL, struct.pack("<H", 9), ct.S2C_REVIVAL, 4),
    (ct.C2S_REVIVAL_CANCEL, struct.pack("<H", 9), ct.S2C_REVIVAL_CANCEL, 4),
    (ct.C2S_REVIVAL_DONE, struct.pack("<H", 9), ct.S2C_REVIVAL_DONE, 4),
    (ct.C2S_SUMMON, bytes(5) + struct.pack("<H", 9), ct.S2C_SUMMON, 2),
    (ct.C2S_SUMMON_CANCEL, struct.pack("<H", 9), ct.S2C_SUMMON_CANCEL, 4),
    (ct.C2S_SUMMON_DONE, bytes(5) + struct.pack("<H", 9), ct.S2C_SUMMON_DONE, 11),
    (ct.C2S_WITHDRAW, struct.pack("<H", 9), ct.S2C_WITHDRAW, 6),
    (ct.C2S_WITHDRAW_CANCEL, struct.pack("<H", 9), ct.S2C_WITHDRAW_CANCEL, 4),
    (ct.C2S_WITHDRAW_DONE, struct.pack("<H", 9), ct.S2C_WITHDRAW_DONE, 6),
])
@pytest.mark.parametrize("spot", [STORY, PLAIN])
def test_a_refusal_is_never_shorter_than_its_handler_reads(spot, proto, body, reply, least):
    # a request for a troop the room does not hold, on a %Point spot and on one with no row: a non-zero result of at
    # least the bytes the reply's handler dereferences whatever the result (the crash sizes), and nothing changed
    role, s, _ = room(spot)
    deck, records = dict(s.data["deck"]), set(s.data["battle"].troops)
    got = ask(role, s, proto, body)
    at = 2 if reply in (ct.S2C_REVIVAL, ct.S2C_REVIVAL_CANCEL, ct.S2C_REVIVAL_DONE) else 0
    b = next(b for p, b in got if p == reply)
    assert len(b) >= least and struct.unpack_from("<H", b, at)[0] == ct.REFUSED
    assert s.data["deck"] == deck and set(s.data["battle"].troops) == records
    assert ct.S2C_POINTS not in {p for p, _ in got}


SIZES = {ct.C2S_CHANGE_START: 5, ct.C2S_CHANGE_ENTER: 3, ct.C2S_CHANGE_REPLACE: 5, ct.C2S_SWAP_SLOTS: 6,
         ct.C2S_CHANGE_CANCEL: 3, ct.C2S_UPGRADE: 10, ct.C2S_UPGRADE_CANCEL: 10, ct.C2S_UPGRADE_DONE: 10,
         ct.C2S_REVIVAL: 2, ct.C2S_REVIVAL_CANCEL: 2, ct.C2S_REVIVAL_DONE: 2, ct.C2S_SUMMON: 7,
         ct.C2S_SUMMON_CANCEL: 2, ct.C2S_SUMMON_DONE: 7, ct.C2S_WITHDRAW: 2, ct.C2S_WITHDRAW_CANCEL: 2,
         ct.C2S_WITHDRAW_DONE: 2}


def test_short_bodies_and_a_session_with_no_room_change_nothing():
    # a body shorter than the builder writes is dropped (no reply the handler could misread); a connection that has
    # not logged into a room (no character, no spot, no battle) is refused or dropped, never an exception
    role, s, _ = room(RIFT, deck=(1, 4))
    for proto, size in SIZES.items():
        for n in range(size):
            assert ask(role, s, proto, bytes(n)) == []
    assert set(s.data["deck"]) == {1} and ct.points(s) == 300

    class Bare:
        def __init__(self):
            self.data, self.sent, self.pending = {}, [], []

        def send(self, w):
            self.sent.append(w)

        def later(self, delay, fn):
            self.pending.append((delay, fn))

    bare = Bare()
    for proto, size in SIZES.items():
        for body in (bytes(size), b"\xff" * size, bytes(range(1, size + 1))):
            for p, b in ask(role, bare, proto, body):
                assert p != ct.S2C_POINTS
                if p == ct.S2C_CHANGE_CANCEL and proto in (ct.C2S_CHANGE_ENTER, ct.C2S_CHANGE_REPLACE):
                    continue                             # the "drop your entry" that follows a refused entry
                at = 2 if p in (ct.S2C_REVIVAL, ct.S2C_REVIVAL_CANCEL, ct.S2C_REVIVAL_DONE) else 0
                assert struct.unpack_from("<H", b, at)[0] != 0
    assert bare.data.get("deck") is None and not bare.pending


def test_points_cannot_be_made_by_cancelling_twice_or_through_the_wrong_cancel():
    role, s, _ = room(INVASION, deck=(1, 4), points=500)
    ask(role, s, ct.C2S_SUMMON, bytes(5) + struct.pack("<H", 4))            # 200 taken
    assert ct.points(s) == 300
    ask(role, s, ct.C2S_WITHDRAW_CANCEL, struct.pack("<H", 4))             # not a withdrawal: nothing back
    ask(role, s, ct.C2S_CHANGE_CANCEL, struct.pack("<HB", 4, 1))           # not a change
    ask(role, s, ct.C2S_UPGRADE_CANCEL, struct.pack("<IIH", 2004, 1, 4))   # not an upgrade
    ask(role, s, ct.C2S_REVIVAL_CANCEL, struct.pack("<H", 4))              # not a revival
    assert ct.points(s) == 300
    ask(role, s, ct.C2S_SUMMON_CANCEL, struct.pack("<H", 4))
    ask(role, s, ct.C2S_SUMMON_CANCEL, struct.pack("<H", 4))
    assert ct.points(s) == 500
    # a summon that completed is not refunded by a late cancel, and the troop cannot be summoned twice
    ask(role, s, ct.C2S_SUMMON, bytes(5) + struct.pack("<H", 4))
    ask(role, s, ct.C2S_SUMMON_DONE, bytes(5) + struct.pack("<H", 4))
    ask(role, s, ct.C2S_SUMMON_CANCEL, struct.pack("<H", 4))
    ask(role, s, ct.C2S_SUMMON_DONE, bytes(5) + struct.pack("<H", 4))
    assert ct.points(s) == 300 and ct.room(s)["summoned"] == {4} and len(s.data["deck"]) == 2
    # a troop with something pending takes no second action
    ask(role, s, ct.C2S_WITHDRAW, struct.pack("<H", 4))
    assert only(ask(role, s, ct.C2S_WITHDRAW, struct.pack("<H", 4)), ct.S2C_WITHDRAW)[:2] == b"\x01\x00"
    assert only(ask(role, s, ct.C2S_UPGRADE, struct.pack("<IIH", 2004, 1, 4)), ct.S2C_UPGRADE)[:2] == b"\x01\x00"

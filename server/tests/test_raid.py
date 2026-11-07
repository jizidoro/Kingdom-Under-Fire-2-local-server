"""A raid's checkpoints, its binding, what a rift's notice carries and the camp revive under a ban
(planning/agents/reports/2026-11-05_contract3-raid.md; server/kuf2/raid.py, party.py, game.py), through the registered
handlers and the real game.troop_down. Reads the installed game's tables and zone files.
Run: py -m pytest -q server/tests"""
import json
import random
import struct

import pytest

from kuf2 import game, obf, party, pvp, raid, zone
from test_battle import NoSave, mission_room
from test_party import COOP, RAID, RIFT, ask, in_party, notice_body, player, setting, world_role

GRAVE = 20951                                   # Grave of Time
STONE, MANELOS, MANELOS_HARD, MANELOS_HELL = 10210, 10000, 10015, 10016     # 20950's zone troops
WARMACHINE = 25000                              # 20951's second boss
ALL = 0xFFFFFFFF
RIFT_STATE, RAID_STATE = 90, 100
SCHEDULE = (0, 5)                               # any: Monday 05:00 UTC


@pytest.fixture
def room(monkeypatch):
    """(role, troop_down): game.make's real closure, caught where it hands it to pvp."""
    caught = {}
    real = pvp.make_game

    def catch(role, state, down):
        caught["down"] = down
        return real(role, state, down)

    monkeypatch.setattr(pvp, "make_game", catch)
    role = game.make(NoSave(), 0)
    return role, caught["down"]


def stand(s, uid):
    """A troop the fallback holds back for a wave comes on the field."""
    assert game.spawn_zone_troop(s, next(t for t in zone.for_spot(s.data["spot"])["NPCTroopInfoData"]
                                         if t["TroopID"] == uid))


def sent(s, proto):
    return [bytes(w.buf) for w in s.sent if w.proto == proto]


def fallen_boss(down, spot=RAID, difficulty=0, uid=STONE):
    s = mission_room(spot, difficulty)
    stand(s, uid)
    down(s, uid)
    return s


def client_map(s):
    """The client's GamePlayInfo map after everything sent, read as 0x1406768f0 / 0x140676ae0 / 0x1406752a0 read it:
    {(spot, difficulty): (checkpoint id, completed)}."""
    m = {}
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto == raid.S2C_BINDINGS:
            n = struct.unpack_from("<H", b)[0]
            assert len(b) == 2 + 10 * n
            m, entries = {}, [b[2 + 10 * k:12 + 10 * k] for k in range(n)]
        elif w.proto == raid.S2C_BINDING:
            assert len(b) == 10
            entries = [b]
        elif w.proto == raid.S2C_BINDING_RESET:
            assert b == b""
            m, entries = {}, []
        else:
            continue
        for e in entries:
            m[obf.dec_u32(e[1:5]), e[0]] = struct.unpack_from("<I", e, 6)[0], bool(obf.T1[e[5]] & 1)
    return m


def client_gate(m, spot, difficulty):
    """The client's entry gate 0x140d6bec0 for Raid_16, over its map."""
    value, flag = m.get((spot, difficulty), (0, False))
    if flag:
        return raid.COMPLETED
    if value:
        return None
    return raid.BOUND_ELSEWHERE if any(m.get((spot, d), (0, False))[0] for d in range(3) if d != difficulty) else None


# Item 1: the checkpoints


def test_the_gate_of_0x5139_opens_on_the_partys_way_into_a_raid():
    # common+0x1674 is written by 0x4058's handler from team +0xa8 (0x5469's spot) for a Raid_16 spot of a team in a
    # party, then 0x405c copies the room over common: the order the gate needs
    role, _ = world_role()
    s = player()
    in_party(role, s, RAID)
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RAID))
    order = [w.proto for w in s.sent if w.proto in (party.S2C_CREATED, party.S2C_SETTING, party.S2C_ROOM_MADE,
                                                    party.S2C_ROOM_ENTER)]
    assert order == [party.S2C_CREATED, party.S2C_SETTING, party.S2C_ROOM_MADE, party.S2C_ROOM_ENTER]
    assert obf.dec_u32(sent(s, party.S2C_SETTING)[0][9:13]) == RAID
    row = party.spot_row(RAID)
    assert (row["Spot_Type"], row["Spot_Sub_Type"]) == ("Raid", "Raid_16")


def test_a_bosss_fall_arms_its_checkpoint_once(room):
    _, down = room
    s = mission_room(RAID)
    stand(s, STONE)
    assert not sent(s, raid.S2C_CHECKPOINT) and raid.armed(s) == []
    down(s, STONE)
    assert sent(s, raid.S2C_CHECKPOINT) == [struct.pack("<I", 295000)]
    assert [r["id"] for r in raid.armed(s)] == [295000] and raid.armed_points(s) == {100}
    raid.on_troop_down(s, NoSave(), s.data["zone_troops"][STONE])       # reported again, or respawned and felled again
    assert len(sent(s, raid.S2C_CHECKPOINT)) == 1 and len(raid.armed(s)) == 1


def test_the_boss_is_read_at_the_rooms_difficulty(room):
    # the zone names the Normal troop; %Check_Point's Hard and Hell rows name the variants
    _, down = room
    assert sent(fallen_boss(down, difficulty=1), raid.S2C_CHECKPOINT) == [struct.pack("<I", 295100)]
    assert sent(fallen_boss(down, difficulty=2), raid.S2C_CHECKPOINT) == [struct.pack("<I", 295200)]
    assert sent(fallen_boss(down, difficulty=1, uid=MANELOS_HARD), raid.S2C_CHECKPOINT) == [struct.pack("<I", 295140)]
    assert sent(fallen_boss(down, difficulty=2, uid=MANELOS_HELL), raid.S2C_CHECKPOINT) == [struct.pack("<I", 295240)]
    assert sent(fallen_boss(down, GRAVE, uid=WARMACHINE), raid.S2C_CHECKPOINT) == [struct.pack("<I", 296010)]


def test_which_checkpoints_the_rule_can_arm_and_which_it_cannot():
    # the report's list: a boss the fallback brings as a wave arms; a reward dummy never comes, 296040 names no boss
    def reach(spot, difficulty):
        plan = game.mission_plan(spot, difficulty)
        ids = {game.difficulty_troop(t["TroopTableID"], difficulty) for wave in plan["waves"] for t in wave}
        return [c["id"] for c in party.checkpoints(spot, difficulty) if c["boss"] in ids]

    assert reach(RAID, 0) == [295000, 295040]
    assert reach(RAID, 1) == [295100, 295140]
    assert reach(RAID, 2) == [295200, 295240]
    assert reach(GRAVE, 0) == [296010, 296020, 296030, 296050]
    assert all(isinstance(c["resurrections"], int) for spot, d in ((RAID, 0), (RAID, 1), (RAID, 2), (GRAVE, 0))
               for c in party.checkpoints(spot, d))         # raid.limit reads it unguarded


def test_the_armed_checkpoints_resurrections_are_the_rooms_limit(room):
    role, down = room
    s = fallen_boss(down, difficulty=2)                     # Hell: 295200 allows 1, the raid's default 3
    assert game.revival(RAID, 2) == ("CUBIC", 3) and raid.limit(s, 3) == 1
    s.data["char"]["cubic"] = 1000
    hero = s.data["battle"].troops[0]
    revive = lambda: next(r for r in ask(role, s, game.C2S_REVIVE_HERE, struct.pack("<H", 0) + obf.u32(ALL))
                          if r[0] == game.S2C_REVIVE_HERE)
    hero["hp"] = 0
    assert revive()[1][:2] == bytes(2) and s.data["revivals"] == 1
    hero["hp"] = 0
    assert revive() == (game.S2C_REVIVE_HERE, struct.pack("<HI", game.REVIVE_NONE_LEFT, 1))
    other = mission_room(RAID, 2)                           # nothing armed: the raid's own 3
    assert raid.limit(other, 3) == 3


def test_the_used_count_is_not_reset_by_an_arming(room):
    # 0x5139's handler writes the limit only; the count stays what 0x50f5 / 0x513c said
    _, down = room
    s = mission_room(RAID)
    s.data["revivals"] = 2
    stand(s, STONE)
    down(s, STONE)
    assert s.data["revivals"] == 2


def test_the_camp_revive_restarts_at_the_armed_point_and_only_there(room):
    role, down = room
    s = mission_room(RAID)
    point = next(p["StartPointInfoData"][0] for p in zone.for_spot(RAID)["PlayerStartPointInfoData"]
                 if p["StartPointID"] == 100)
    x, z = round(point["PosX"]), round(point["PosZ"])
    s.data["hero_pos"] = (x + 100, 0, z)
    before = game.revive_point(s)
    assert before != (x, 0, z)                              # unarmed: held back, as a raid that armed nothing
    stand(s, STONE)
    down(s, STONE)
    assert game.revive_point(s) == (x, 0, z)
    s.data["battle"].troops[0]["hp"] = 0
    reply = ask(role, s, game.C2S_REVIVE_CAMP)[0]
    assert reply == (game.S2C_REVIVE_CAMP, struct.pack("<HHff", 0, 0, z, x))
    far = next(p["StartPointInfoData"][0] for p in zone.for_spot(RAID)["PlayerStartPointInfoData"]
               if p["StartPointID"] == 104)
    s.data["hero_pos"] = (round(far["PosX"]), 0, round(far["PosZ"]))
    assert game.revive_point(s) == (x, 0, z)                # at 104's foot: 104 is not armed, 100 is the closest


def text_action(s):
    return [b for b in sent(s, game.S2C_SCRIPT_ACTION) if b[:4] == struct.pack("<I", raid.ACT_SYSTEM_TEXT)]


def test_with_no_resurrection_left_the_hero_is_told_of_the_closest_checkpoint(room):
    _, down = room
    s = fallen_boss(down, difficulty=2)                     # 295200: 1
    s.data["revivals"] = 1
    down(s, 0)
    assert text_action(s) == [struct.pack("<III", 0xc779, 0, 0x16068) + b"\0" + bytes(4)]
    assert sent(s, game.S2C_DEATH_WINDOW) == [b"\0"]        # the window still opens: its camp button is the move
    down(s, 0)                                              # the same fall reported again
    assert len(text_action(s)) == 1


def test_no_closest_checkpoint_text_with_one_left_or_none_armed(room):
    _, down = room
    s = fallen_boss(down, difficulty=2)
    down(s, 0)
    assert not text_action(s)                               # 0 of 1 used
    s = mission_room(RAID)
    s.data["revivals"] = 9
    down(s, 0)
    assert not text_action(s)                               # nothing armed


def test_a_non_raid_room_is_byte_identical(room, monkeypatch):
    # the same run with the raid's hooks on and with them gone: not a byte differs
    role, down = room

    def run():
        random.seed(7)
        s = mission_room(COOP)
        foe = next(u for u, t in s.data["zone_troops"].items() if game.hostile(t))
        s.data["hero_pos"] = (0, 0, 0)
        down(s, foe)
        down(s, 0)
        ask(role, s, game.C2S_REVIVE_CAMP)
        s.data["battle"].troops[0]["hp"] = 0
        ask(role, s, game.C2S_REVIVE_HERE, struct.pack("<H", 0) + obf.u32(ALL))
        return [(w.proto, bytes(w.buf)) for w in s.sent], s

    hooked, s = run()
    assert "raid_armed" not in s.data and "raid_binding" not in s.data["char"]
    new = {raid.S2C_CHECKPOINT, raid.S2C_BINDINGS, raid.S2C_BINDING, raid.S2C_BINDING_RESET}
    assert not new & {p for p, _ in hooked}
    for name in ("on_troop_down", "on_hero_down"):
        monkeypatch.setattr(raid, name, lambda *a: None)
    monkeypatch.setattr(raid, "limit", lambda s, default: default)
    monkeypatch.setattr(raid, "armed_points", lambda s: frozenset())
    assert run()[0] == hooked


# Item 2: the binding


def test_with_no_schedule_the_binding_sends_saves_and_refuses_nothing(room):
    assert raid.RESET_SCHEDULE is None
    role, down = room
    s = fallen_boss(down)
    c = s.data["char"]
    raid.on_login(s, NoSave(), c)
    raid.on_won(s, NoSave(), c, RAID, 0)
    assert not client_map(s) and not sent(s, raid.S2C_BINDINGS) and not sent(s, raid.S2C_BINDING)
    assert "raid_binding" not in c and not s.pending
    assert raid.refusal(c, RAID, 0) is None and raid.bound_checkpoint(c, RAID, 0) == 0


def test_a_saved_binding_is_inert_with_no_schedule():
    # the owner turns the schedule off again: what is saved stops counting
    c = {"raid_binding": {"period": 0, "raids": {"20950/0": {"checkpoint": 295000, "completed": True}}}}
    assert raid.raids(c) == {} and raid.refusal(c, RAID, 0) is None and raid.bound_checkpoint(c, RAID, 0) == 0


def test_a_checkpoint_binds_a_win_completes_and_the_client_map_follows(room, monkeypatch):
    monkeypatch.setattr(raid, "RESET_SCHEDULE", SCHEDULE)
    _, down = room
    s = fallen_boss(down)
    c = s.data["char"]
    assert client_map(s) == {(RAID, 0): (295000, False)}
    assert sent(s, raid.S2C_BINDING) == [b"\0" + obf.u32(RAID) + bytes([1]) + struct.pack("<I", 295000)]
    assert raid.bound_checkpoint(c, RAID, 0) == 295000 and raid.bound_checkpoint(c, RAID, 1) == 0
    raid.on_won(s, NoSave(), c, RAID, 0)
    assert client_map(s) == {(RAID, 0): (295000, True)}
    assert json.loads(json.dumps(c["raid_binding"])) == c["raid_binding"]       # the save's own format


def test_the_servers_refusal_is_the_clients_gate(monkeypatch):
    monkeypatch.setattr(raid, "RESET_SCHEDULE", SCHEDULE)
    s = mission_room(RAID)
    c, st = s.data["char"], NoSave()
    cases = lambda: [(spot, d) for spot in (RAID, GRAVE) for d in range(3)]
    assert all(raid.refusal(c, spot, d) is None for spot, d in cases())         # an empty map passes every gate
    raid.bind(s, st, c, RAID, 1, checkpoint=295100)
    raid.bind(s, st, c, GRAVE, 0, completed=True)
    m = client_map(s)
    assert all(raid.refusal(c, spot, d) == client_gate(m, spot, d) for spot, d in cases())
    assert raid.refusal(c, RAID, 1) is None and raid.refusal(c, RAID, 0) == raid.BOUND_ELSEWHERE
    assert raid.refusal(c, GRAVE, 0) == raid.COMPLETED


def test_the_login_sends_the_whole_map_and_starts_the_watch(monkeypatch):
    monkeypatch.setattr(raid, "RESET_SCHEDULE", SCHEDULE)
    s = mission_room(RAID)
    c, st = s.data["char"], NoSave()
    raid.on_login(s, st, c)
    assert sent(s, raid.S2C_BINDINGS) == [bytes(2)] and len(s.pending) == 1
    raid.bind(s, st, c, RAID, 0, checkpoint=295000)
    raid.bind(s, st, c, GRAVE, 0, checkpoint=296010, completed=True)
    world_session = mission_room(RAID)
    raid.on_login(world_session, st, c)
    assert client_map(world_session) == {(RAID, 0): (295000, False), (GRAVE, 0): (296010, True)}


class Clock:
    def __init__(self, t):
        self.t = t

    def time(self):
        return self.t


def test_a_reset_clears_the_map_when_it_falls_due(monkeypatch):
    monkeypatch.setattr(raid, "RESET_SCHEDULE", SCHEDULE)
    clock = Clock(1_780_000_000)
    monkeypatch.setattr(raid, "time", clock)
    s = mission_room(RAID)
    c, st = s.data["char"], NoSave()
    raid.on_login(s, st, c)
    raid.bind(s, st, c, RAID, 0, checkpoint=295000, completed=True)
    assert raid.refusal(c, RAID, 0) == raid.COMPLETED
    delay, due = s.pending.pop()
    assert 0 < delay <= raid.WEEK and delay == raid.next_reset()
    clock.t += delay
    due()
    assert sent(s, raid.S2C_BINDING_RESET) == [b""] and client_map(s) == {}
    assert "raid_binding" not in c and raid.refusal(c, RAID, 0) is None
    assert len(s.pending) == 1 and s.pending[0][0] == raid.WEEK                 # the next one is watched
    s.pending.pop()[1]()                                                        # (a clock not yet there: nothing)
    assert len(sent(s, raid.S2C_BINDING_RESET)) == 1


def test_a_reset_with_nothing_bound_says_nothing_and_a_reset_passed_offline_needs_no_0x5a4c(monkeypatch):
    monkeypatch.setattr(raid, "RESET_SCHEDULE", SCHEDULE)
    clock = Clock(1_780_000_000)
    monkeypatch.setattr(raid, "time", clock)
    s = mission_room(RAID)
    c, st = s.data["char"], NoSave()
    raid.reset(s, st, c)
    assert not sent(s, raid.S2C_BINDING_RESET)
    raid.bind(s, st, c, RAID, 0, checkpoint=295000)
    clock.t += raid.WEEK
    back = mission_room(RAID)
    raid.on_login(back, st, c)
    assert sent(back, raid.S2C_BINDINGS) == [bytes(2)] and not sent(back, raid.S2C_BINDING_RESET)
    assert "raid_binding" not in c


def test_a_watch_of_another_character_stays_quiet(monkeypatch):
    monkeypatch.setattr(raid, "RESET_SCHEDULE", SCHEDULE)
    clock = Clock(1_780_000_000)
    monkeypatch.setattr(raid, "time", clock)
    s = mission_room(RAID)
    c, st = s.data["char"], NoSave()
    raid.on_login(s, st, c)
    raid.bind(s, st, c, RAID, 0, checkpoint=295000)
    s.data["char"] = {"id": 2}
    clock.t += raid.WEEK
    s.pending.pop()[1]()
    assert not sent(s, raid.S2C_BINDING_RESET) and not s.pending


def test_a_bind_past_a_reset_tells_the_reset_first(monkeypatch):
    monkeypatch.setattr(raid, "RESET_SCHEDULE", SCHEDULE)
    clock = Clock(1_780_000_000)
    monkeypatch.setattr(raid, "time", clock)
    s = mission_room(RAID)
    c, st = s.data["char"], NoSave()
    raid.bind(s, st, c, RAID, 0, checkpoint=295000, completed=True)
    clock.t += raid.WEEK
    raid.bind(s, st, c, RAID, 0, checkpoint=295010)
    assert client_map(s) == {(RAID, 0): (295010, False)}


def test_the_schedule_falls_on_its_weekday_and_hour():
    import datetime
    from unittest import mock
    utc = datetime.timezone.utc
    with mock.patch.object(raid, "RESET_SCHEDULE", (0, 5)):                 # Monday 05:00 UTC
        sunday = datetime.datetime(2026, 11, 8, 23, 0, tzinfo=utc).timestamp()
        monday_early = datetime.datetime(2026, 11, 9, 4, 59, tzinfo=utc).timestamp()
        monday = datetime.datetime(2026, 11, 9, 5, 0, tzinfo=utc).timestamp()
        assert raid.period(sunday) == raid.period(monday_early) == raid.period(monday) - 1
        assert raid.next_reset(monday_early) == 60
        assert raid.next_reset(monday) == raid.WEEK


def test_the_bound_checkpoint_rides_the_partys_setting_and_a_start_is_refused(monkeypatch):
    monkeypatch.setattr(raid, "RESET_SCHEDULE", SCHEDULE)
    from test_army import army
    role, st = world_role()
    c, _ = army(1, deck=(1,))
    s = player()
    s.data["char"] = c
    c["name"] = "Aldric"
    in_party(role, s, RAID)
    assert struct.unpack_from("<I", sent(s, party.S2C_SETTING)[-1], 0x12)[0] == 0
    ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RAID))
    raid.bind(s, st, c, RAID, 0, checkpoint=295010)
    in_party(role, s, RAID)
    assert struct.unpack_from("<I", sent(s, party.S2C_SETTING)[-1], 0x12)[0] == 295010
    raid.bind(s, st, c, RAID, 0, completed=True)
    assert ask(role, s, party.C2S_START) == [(party.S2C_START, struct.pack("<H", raid.COMPLETED))]
    assert ask(role, s, party.C2S_NOTICE, notice_body(RAID)) == [(party.S2C_NOTICE, struct.pack("<H", raid.COMPLETED))]


def test_spottable_offers_a_raid_at_normal_only():
    # Mission_Diffi_2 / _3 are "-" on both raids: %Raid's Hard and Hell rows are data no room reaches, so 0x2408 (a
    # binding at another difficulty) has nothing to fire on today; a notice at Hard is refused as no mission
    role, _ = world_role()
    s = player()
    assert [party.has_difficulty(party.spot_row(RAID), d) for d in range(3)] == [True, False, False]
    assert [party.has_difficulty(party.spot_row(GRAVE), d) for d in range(3)] == [True, False, False]
    assert ask(role, s, party.C2S_NOTICE, notice_body(RAID, difficulty=1)) == \
        [(party.S2C_NOTICE, struct.pack("<H", party.NO_SUCH_NOTICE))]


# Item 3: what a rift's notice carries


def any_notice(category, wanted, difficulty=party.ANY_DIFFICULTY, title="All"):
    """The dialog's "All" row: spot -1 (0x1406d1cb8), difficulty 3 (0x1406d2657)."""
    b = bytearray(16)
    b[0], b[2], b[4] = category, obf.T2[1], 1
    b[5:9] = obf.u32(ALL)
    b[14], b[15] = wanted, difficulty
    return title.encode() + b"\0" + bytes(b)


def test_a_rifts_notice_names_no_map_and_its_party_still_gets_a_room():
    role, _ = world_role()
    s = player()
    replies = ask(role, s, party.C2S_NOTICE, any_notice(RIFT_STATE, 4, title="Crack"))
    assert replies == [(party.S2C_NOTICE, bytes(2)), (party.S2C_CREATED, bytes(2)),
                       (party.S2C_SETTING, setting(1, 1, RIFT, RIFT_STATE, 4, 0, b"Crack"))]
    # the client's Enter party room takes team +0xa8: 10335, and the room opens with no second setting
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RIFT)) == [
        (party.S2C_ROOM_MADE, bytes(2) + struct.pack("<IBB", RIFT, 0, 0)),
        (party.S2C_ROOM_ENTER, bytes(2) + struct.pack("<IB", s.data["char"]["id"], 0))]
    assert ask(role, s, party.C2S_STEP, b"\x01")[0] == (party.S2C_STEP, bytes(2) + b"\x01")


def test_a_rifts_notice_is_held_to_the_rifts_party_size():
    role, _ = world_role()
    s = player()
    assert ask(role, s, party.C2S_NOTICE, any_notice(RIFT_STATE, 5)) == [(party.S2C_NOTICE,
                                                                         struct.pack("<H", party.WRONG_NUMBER))]
    assert party.team(s)["notice"] is None


def test_all_under_another_state_stays_all_until_a_map_is_named():
    role, _ = world_role()
    s = player()
    replies = ask(role, s, party.C2S_NOTICE, any_notice(RAID_STATE, 16))
    assert replies[0] == (party.S2C_NOTICE, bytes(2))
    assert replies[-1] == (party.S2C_SETTING, setting(1, 1, ALL, RAID_STATE, 16, 3, b"All"))
    board = ask(role, s, party.C2S_BOARD, bytes(13))[0][1]
    assert obf.dec_u32(board[13:17]) == ALL and board[12] == 3
    # the world map's click names the spot: the room opens at it and the notice follows (0x140d48d00)
    assert ask(role, s, party.C2S_ROOM_ENTER, struct.pack("<I", RAID))[0][0] == party.S2C_SETTING
    assert party.team(s)["notice"]["spot"] == RAID and party.team(s)["room"]["spot"] == RAID


def test_all_is_refused_past_what_the_dialog_offers():
    role, _ = world_role()
    s = player()
    assert ask(role, s, party.C2S_NOTICE, any_notice(RAID_STATE, 17)) == [(party.S2C_NOTICE,
                                                                          struct.pack("<H", party.WRONG_NUMBER))]
    assert ask(role, s, party.C2S_NOTICE, any_notice(RAID_STATE, 16, difficulty=4)) == [
        (party.S2C_NOTICE, struct.pack("<H", party.NO_SUCH_NOTICE))]
    assert ask(role, s, party.C2S_NOTICE, any_notice(RAID_STATE, 0)) == [(party.S2C_NOTICE,
                                                                         struct.pack("<H", party.WRONG_NUMBER))]


# Item 4: the camp revive under a ban


def test_the_camp_revive_is_not_held_by_the_ban():
    # the client's button goes straight to the builder (0x14085a16e -> 0x140eff140): only the revive in place reads
    # the ban map (0x14068f286); the server answers the same
    s = mission_room(RAID)
    role = game.make(NoSave(), 0)
    party.on_troop_down(s, 0)
    assert party.ban_left(s, 0) > 0
    s.data["battle"].troops[0]["hp"] = 0
    here = ask(role, s, game.C2S_REVIVE_HERE, struct.pack("<H", 0) + obf.u32(ALL))
    assert here[0] == (game.S2C_REVIVE_HERE, struct.pack("<HI", game.REVIVE_NOT_NOW, 0))
    assert ask(role, s, game.C2S_REVIVE_CAMP)[0][1][:2] == bytes(2)

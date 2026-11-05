"""The army (ROADMAP wave 2 item 2: B1 deck troops in battle, B2 troop stats, B4 a player troop's combatant record, D13
troop mission exp and AP; Q34 the spot's troop limits). Every number is the tables' (trooptable, trooptype,
lvuptypetable %Troop, spottable, mission_reward); the byte places are the client's (troops.py, game.py).
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import combat, game, obf, status, tables, troops, world
from kuf2.packet import Reader


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


class NoSave:
    def save(self):
        pass


class Session:
    def __init__(self, spot, c):
        self.data = {"spot": spot, "char": c, "account": {"id": 1, "characters": [c]}}
        self.sent = []
        self.pending = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))

    def run_later(self, limit=500):
        # Like conftest.run_pending: permanent pool statuses can reschedule forever.
        # This fake scheduler does not advance the clock, so draining is unbounded.
        for _ in range(limit):
            if not self.pending:
                break
            self.pending.sort(key=lambda p: p[0])
            self.pending.pop(0)[1]()


def row(troop_id):
    return next(r for r in tables.sections("trooptable")["Contents"] if r["TROOP_ID"] == str(troop_id))


def army(*sets, level=30, deck=(1, 2, 3, 4)):
    """A character with one troop per contract set, the first four in main-deck slots `deck`."""
    c = {"id": 1, "class": 0, "level": level, "name": "T", "look": "00" * 0x33, "quests": {"active": {}, "done": []}}
    ts = [troops.grant(c, k)[0] for k in sets]
    slots = troops.lineup(c)["slots"]
    for t, slot in zip(ts, deck):
        slots[slot] = t["uid"]
    return c, ts


def entered(spot, c, difficulty=0):
    """A game session through the login (0x3f4e-0x3f50) and the loading's end, its timers run."""
    role = game.make(NoSave(), 0)
    s = Session(spot, c)
    s.data["difficulty"] = difficulty
    game.send_start_header(s, spot)
    role.handlers[game.C2S_LOAD_PROGRESS](s, pkt(game.C2S_LOAD_PROGRESS, bytes([100])))
    s.run_later()
    return role, s


@pytest.mark.parametrize('bound', (None, {0}, {0, 1}))
def test_owned_troops_are_enabled_before_later_handover_can_take_their_hud_slot(bound):
    # Native HUDTroopInfo ignores disabled troops (+0x94 bit4). OnAddPlayerTroop
    # takes the first empty HUD slot, even when a disabled roster troop owns it.
    # Grey Rock's old startup left infantry disabled until archers were handed over.
    c, _ = army(1, level=6)
    role = game.make(NoSave(), 0)
    s = Session(10234, c)
    if bound is not None:
        s.data['bound'] = set(bound)
    game.send_start_header(s, 10234)
    role.handlers[game.C2S_LOAD_PROGRESS](s, pkt(game.C2S_LOAD_PROGRESS, bytes([100])))
    initial = [fn for delay, fn in s.pending if delay == 1.0]
    assert len(initial) == 1
    initial[0]()
    assert enter_cells(s).keys() == {0, 1}
    if bound == {0}:
        assert s.data['await_bind'][1] == [[game.ACT_ENABLE_TROOP, 0, 1, 1, 1]]
        game.troop_bound(s, 1)
    enabled = []
    for w in s.sent:
        if w.proto != game.S2C_SCRIPT_ACTION:
            continue
        values = struct.unpack('<' + 'I' * (len(w.buf) // 4), bytes(w.buf))
        if values == (game.ACT_ENABLE_ALL_TROOPS, 1, 1):
            enabled.extend(enter_cells(s))
        elif values[:1] == (game.ACT_ENABLE_TROOP,) and values[1:2] == (0,) and values[3:4] == (1,):
            enabled.append(values[2])
    assert enabled == [1], 'Only the roster troop is enabled before the later NPC batch'


def start_records(s):
    """The 0x3f4e header's player records: (team, player, is-AI byte, troop count)."""
    b = bytes(next(w for w in s.sent if w.proto == game.S2C_SPOT_ROOM_START).buf)
    n = struct.unpack_from("<H", b, 1 + 0x1a)[0]
    return [struct.unpack_from("<HHBH", b, 1 + 0x1a + 2 + 7 * i) for i in range(n)]


def troop_entries(s):
    """The 0x3f50 entries' 40-byte T blocks and whether a leader block follows (write_troop)."""
    b = bytes(next(w for w in s.sent if w.proto == game.S2C_START_TROOP_INFO).buf)
    n, i, out = struct.unpack_from("<H", b)[0], 2, []
    for _ in range(n):
        t = b[i:i + 0x28]
        i += 0x28
        leader = obf.T1[b[i]] & 1
        i += 1 + (25 if leader else 0)
        k = struct.unpack_from("<H", b, i)[0]
        abilities = [struct.unpack_from("<BI", b, i + 2 + 5 * j) for j in range(k)]
        i += 2 + 5 * k
        i += 2 + 5 * struct.unpack_from("<H", b, i)[0]
        i += 2                                              # two FALSE obools
        stats = b[i + 2:i + 2 + struct.unpack_from("<H", b, i)[0]]
        i += 2 + len(stats)
        out.append({"slot": t[0], "slots": struct.unpack_from("<H", t, 1)[0], "id": obf.dec_u32(t[3:7]),
                    "barracks": struct.unpack_from("<Q", t, 9)[0], "units": struct.unpack_from("<H", t, 0x19)[0],
                    "uid": struct.unpack_from("<H", t, 0x23)[0], "hp": world_value(t, 0x15),
                    "max": world_value(t, 0x1f), "leader": bool(leader), "abilities": abilities, "stats": stats})
    assert i == len(b)
    return out


def world_value(b, off):
    hi, lo = struct.unpack_from("<HH", b, off)
    return (hi << 16) | lo


def enter_cells(s):
    """{uid: (team, troop id, units)} of the 0x50cb entries sent."""
    out = {}
    for w in s.sent:
        if w.proto != game.S2C_ENTER_CELL_TROOP:
            continue
        b = bytes(w.buf)
        st = b[3:3 + 0x3d]
        out[struct.unpack_from("<H", st, 0x11)[0]] = (struct.unpack_from("<h", st, 0)[0], obf.dec_u32(st[0x36:0x3a]),
                                                      st[0x13])
    return out


def ap_pushes(s):
    """[(uid, ap)] of every 0x1365 sent, in order."""
    out = []
    for w in s.sent:
        if w.proto == troops.S2C_AP:
            b = bytes(w.buf)
            assert struct.unpack_from("<h", b)[0] == 0
            out += [(struct.unpack_from("<Q", b, 5 + 10 * k)[0], struct.unpack_from("<h", b, 3 + 10 * k)[0])
                    for k in range(b[2])]
    return out


# --- B2: the troop's stats ---

def test_troop_stats_grow_by_level_from_the_trooptable():
    # trooptable 100 (the tutorial conscripts, contract set 1 at level 6): each stat is its column plus its Lv column
    # per level past the first (LvPhysicalAttack 7.4, LvPhysicalDefence 64.4, HPRevision 134.5 per unit), as the
    # hero's lvuptypetable %Hero growth; lvuptypetable %Troop row 449 (its LV_UP_TYPE) adds no stat
    r = row(100)
    at1, at6 = troops.level_row(100, 1), troops.level_row(100, 6)
    assert at1["ATTACK_PHYSICAL"] == pytest.approx(8.45) and at1["DEFENCE_PHYSICAL"] == 64
    assert at6["ATTACK_PHYSICAL"] == pytest.approx(8.45 + 7.4 * 5)
    assert at6["DEFENCE_PHYSICAL"] == pytest.approx(64 + 64.4 * 5)
    assert at6["HP_BASEUNIT"] == pytest.approx(211 + 134.5 * 5) and at6["UNIT_COUNT"] == int(r["UNIT_COUNT"]) == 10
    assert troops.troop_hp(100) == 2110 and troops.troop_hp(100, 6) == int(211 + 134.5 * 5) * 10 == 8830   # the tape's
    # the per-star rows add soldiers, not unit strength (Bersia Swordsmen 1-5 stars: 18 / 21 / 24 / 27 / 30 units)
    assert troops.level_row(1100115, 30)["HP_BASEUNIT"] == troops.level_row(1100111, 30)["HP_BASEUNIT"]
    assert troops.level_row(1100115, 30)["UNIT_COUNT"] == 30 and troops.level_row(1100111, 30)["UNIT_COUNT"] == 18


def test_the_template_stat_block_sits_where_the_client_reads_it():
    # 0x1549 (0x140da4670) copies its 0x88 bytes to the troop record +0x1c0, the block UpdateDetailInfo (0x140d9ce40,
    # base record +0x20) and the hero's 0x134b share: attack min / max in tenths at +0x78 / +0x18, close / ranged
    # physical defence +0x48 / +0x2c, ice +0x00, crit damage f32 +0x30, crit rate +0x50, move speed +0x34
    c, _ = army()
    role = troops_role()
    s = Session(10001, c)
    role.handlers[troops.C2S_TEMPLATE](s, pkt(troops.C2S_TEMPLATE, struct.pack("<IB", 2202311, 3)))
    out = bytes(s.sent[-1].buf)
    lv = troops.level_row(2202311, 3)
    i32 = lambda at: struct.unpack_from("<i", out, at)[0]
    assert len(out) == 0x96 and out[0x88:0x8c] == obf.u32(2202311) and out[0x8c] == 3
    assert i32(0x78) == i32(0x18) == round(lv["ATTACK_PHYSICAL"] * 10) == round((9 + 9 * 2) * 10)
    assert i32(0x38) == i32(0x64) == round(lv["ATTACK_MAGICAL"] * 10)
    assert i32(0x48) == i32(0x2c) == 32 * 3 and i32(0x00) == (32 + 103) * 3      # ice: the magical + its offset
    assert struct.unpack_from("<f", out, 0x30)[0] == pytest.approx(750) and i32(0x50) == 200
    assert i32(0x34) == 740 and i32(0x44) == 7000
    assert out[0x91:0x95] == world.stat_code(troops.troop_hp(2202311, 3))


def test_the_troop_detail_carries_its_level_stats_and_hp():
    c, ts = army(1)
    t = ts[0]
    role = troops_role()
    s = Session(10001, c)
    role.handlers[troops.C2S_DETAIL](s, pkt(troops.C2S_DETAIL, struct.pack("<Q", t["uid"])))
    b = bytes(s.sent[-1].buf)
    at = 2 + 8 + 1 + 6 * b[10]                          # past the skill list (u8 n, n x 6: its default 81001)
    block = b[at:at + troops.DETAIL_BLOCK]
    assert block[0x12:0x9a] == troops.stat_block(troops.level_row(100, 6))
    assert block[0x0e:0x12] == block[0x9a:0x9e] == world.stat_code(troops.troop_hp(100, 6))
    assert struct.unpack_from("<i", block, 0x12 + 0x48)[0] == round(64 + 64.4 * 5)


def test_a_badge_adds_its_traits_to_the_troop():
    # item_troop BASE_TRAIT_* ADD, target ALL: an attack badge raises the troop's attack by its value
    # (111 plain numbers, 79 "N%" shares of the stat: 301110100 ATTACK_PHYSICAL 1%)
    badge = next(r for r in tables.sections("item_troop")["Base"] if r["BASE_TRAIT_TYPE0"] == "ATTACK_PHYSICAL"
                 and r["BASE_OPERATION0"] == "ADD" and not r["BASE_VALUE0"].endswith("%"))
    plain = troops.level_row(100, 6)
    worn = troops.level_row(100, 6, badges=[int(badge["ItemCode"]), 301110100])
    assert worn["ATTACK_PHYSICAL"] == pytest.approx((plain["ATTACK_PHYSICAL"] + float(badge["BASE_VALUE0"])) * 1.01)
    c, ts = army(1)
    ts[0]["badges"] = [{"slot": 0, "code": 301110600, "serial": 9}]                 # HP_MAX 1%, per unit
    assert troops.hp_of(ts[0]) == round((211 + 134.5 * 5) * 1.01) * 10


def troops_role():
    from kuf2.net import Role
    role = Role("world", 0, None)
    troops.make(role, NoSave())
    return role


# --- B4: a deck troop's combatant record ---

def test_a_deck_troops_combatant_record_comes_from_its_level_stats_and_troop_type():
    # the archers 2202311 at level 10: attack 9 + 9 x 9, defence 32 + 32 x 9; trooptype 6018: main attack RANGE,
    # engage LOOSE, DEFENCE_TYPE 177, BRANCH ARCHER, RACE ELF; its %Combat slots name the volley's power rate
    rec = combat.combatant_troop(troops.level_row(2202311, 10))
    assert rec["level"] == 10 and rec["team"] == 0 and rec["atk"][combat.PHYSICAL] == (90.0, 90.0)
    assert rec["def"]["CLOSE"] == rec["def"]["RANGE"] == 320 and rec["def"]["ICE"] == 1350 and rec["def"]["FIRE"] == -210
    assert (rec["main"], rec["engage"], rec["defence_type"], rec["branch"], rec["race"]) == \
        ("RANGE", "LOOSE", "177", "ARCHER", "ELF")
    assert rec["main_rev"] == 1.5 and "ATTACK_LIGHT_RANGE" in rec["powers"]
    volley = combat.hit_attack(rec, combat.VOLLEY_ACTION)
    assert volley["type"] == "RANGE" and volley["pr"] == pytest.approx(rec["default_pr"] *
                                                                       rec["powers"]["ATTACK_LIGHT_RANGE"][0] * 1.5)


# --- B1: the deck in the room ---

def test_the_room_start_carries_the_deck_troops_the_spot_allows():
    # New Hampton 10235 takes 2 (spottable Limit_Troop_1; the client reads Limit_Troop_<difficulty>, never Limit_Troop):
    # the first two filled main-deck slots of 1-3 (0x140d6b3f0 walks slots 1..3 only); slot 4 stays home
    c, ts = army(1, 2202311, 1100111, 1)
    _, s = entered(10235, c)
    assert start_records(s) == [(game.PLAYER_TEAM, game.MY_SLOT, 1, 3)]
    hero, *deck = troop_entries(s)
    assert hero["uid"] == 0 and hero["leader"] and hero["id"] == game.HERO_TROOP_ID
    assert [(e["slot"], e["uid"], e["id"], e["barracks"], e["leader"]) for e in deck] == \
        [(1, 1, 100, ts[0]["uid"], False), (2, 2, 2202311, ts[1]["uid"], False)]
    assert [(e["units"], e["slots"], e["hp"], e["max"]) for e in deck] == \
        [(10, 10, troops.troop_hp(100, 6), troops.troop_hp(100, 6)),
         (16, 16, troops.troop_hp(2202311, 1), troops.troop_hp(2202311, 1))]
    # Tower 10233 takes none (Limit_Troop_1 0): the hero alone, as before
    c, _ = army(1)
    _, s = entered(10233, c)
    assert start_records(s) == [(game.PLAYER_TEAM, game.MY_SLOT, 1, 1)] and len(troop_entries(s)) == 1


def test_deck_troops_enter_the_cell_fight_for_the_player_and_take_hits():
    c, ts = army(1, 2202311)
    _, s = entered(10235, c)
    cells = enter_cells(s)
    assert cells[1] == (game.PLAYER_TEAM, 100, 6) and cells[2] == (game.PLAYER_TEAM, 2202311, 1)
    b = s.data["battle"]
    assert b.troops[1]["units"] == [int(211 + 134.5 * 5)] * 10          # 883: the unit's HP floored (T1.3)
    assert b.troops[1]["c"]["atk"][combat.PHYSICAL][0] == pytest.approx(8.45 + 7.4 * 5)
    assert status.players(s, 1) and status.players(s, 2) and s.data["deck"][1] is ts[0]
    assert status.side(s, 1) == status.side(s, 0) == 0             # the hero's ALLY statuses reach them, ENEMY ones not
    sight = [w for w in s.sent if w.proto == game.S2C_MISSION_TROOP_INFO]
    assert {struct.unpack_from("<H", bytes(w.buf), 0x11)[0] for w in sight} >= {0, 1, 2}
    # an enemy's hit on the archers lands on their units; their hit on it resolves from their record
    enemy = next(u for u, t in b.troops.items() if u >= 10000 and t.get("c") and t["c"]["team"] != 0
                 and t["c"]["branch"] != "PROP")               # not a building: those take nothing but siege (C5)
    before = sum(b.troops[2]["units"])
    combat.apply_hits(s, [(2, [0])], game.send_troop_hp, attacker=enemy, attack={"pr": 1.0, "ar": 1.0})
    assert sum(b.troops[2]["units"]) < before
    hp = sum(b.troops[enemy]["units"]) + b.troops[enemy].get("leader", 0)
    combat.apply_hits(s, [(enemy, [0])], game.send_troop_hp, attacker=2, attack=combat.hit_attack(b.troops[2]["c"]))
    assert sum(b.troops[enemy]["units"]) + b.troops[enemy].get("leader", 0) < hp
    assert enemy in s.data.get("fought_player", ())               # a deck troop's hit is the player's side's


def test_deck_troops_stand_at_their_start_points_and_follow_the_hero_to_the_scene():
    # the zone's player start point has 9 places, one per lineup slot (0 the hero); Grey Rock's opening scene moves
    # the hero to its bound (stage_hero), and his troops keep their places around him
    c, _ = army(1)
    _, s = entered(10234, c)
    from kuf2 import zone
    pts = zone.for_spot(10234)["PlayerStartPointInfoData"][0]["StartPointInfoData"]
    moved = [w for w in s.sent if w.proto == game.S2C_TROOP_BACK]
    uids = [struct.unpack_from("<H", bytes(w.buf), 7)[0] for w in moved]
    assert uids[:2] == [0, 1]
    hx, _, hz = s.data["hero_pos"]
    x, z = obf.dec_pos_xz(bytes(moved[1].buf)[0:4], bytes(moved[1].buf)[6])
    assert abs(x - (hx + pts[1]["PosX"] - pts[0]["PosX"])) < 64 and abs(z - (hz + pts[1]["PosZ"] - pts[0]["PosZ"])) < 64


def test_the_zone_troops_are_still_handed_over_beside_the_deck():
    # Grey Rock 10234 (Limit_Troop_1 1, Min_Limit_Troop 1) hands 10073 (the designers' 편입 row) as before, and the
    # first deck troop comes too: the hand-over stays our reading (game.hand_limit), the deck the client's (Q34)
    c, _ = army(1, 2202311)
    _, s = entered(10234, c)
    assert 10073 in s.data["plan"]["hand"] and list(s.data["deck"]) == [1]
    assert status.players(s, 10073) and status.players(s, 1) and not status.players(s, 2)


def test_the_deck_the_spot_takes_counts_filled_slots_one_to_three():
    c, ts = army(1, 2202311, 1100111, deck=(2, 3, 4))
    assert [(k, t["id"]) for k, t in troops.room_deck(c, 10235)] == [(2, 100), (3, 2202311)]
    assert [(k, t["id"]) for k, t in troops.room_deck(c, 10234)] == [(2, 100)]
    assert troops.room_deck(c, 10233) == [] and troops.room_deck(c, 10353) == []        # Normal 0 (Hard / Hell 3)
    assert [k for k, _ in troops.room_deck(c, 10353, difficulty=1)] == [2, 3]            # slot 4 is not a mission slot
    assert troops.room_deck({"id": 1}, 10235) == []


def test_the_journal_reads_the_deck_lines():
    from kuf2 import timeline
    text = lambda **e: timeline.server_text(dict(e, t=0))
    assert text(k="troop", ev="deploy", troops=[[1, 100, 6, 85]]) == "deck troops in the room: uid 1 troop 100 level 6 AP 85"
    assert text(k="troop", ev="ap", why="Troop_Death", troops=[[100, 80]]) == "troop AP (Troop_Death): troop 100 AP 80"
    assert text(k="troop", ev="exp", troop=100, add=375, level=7, up=1, exp=0, need=200) == \
        "troop 100 exp +375: level up to 7, 0/200"
    assert text(k="down", troop=1, deck=100, killer=20001) == "deck troop 1 (100) down by 20001"


# --- D13: exp and AP ---

def test_entering_a_mission_spends_the_troops_ap_and_says_so():
    # spottable Troop_Mission_Enter 15 at the start, Troop_Mission_Clear 5 at the win (the official notes' 20 AP a
    # mission); 0x1365 (NotifyActionPower 0x140da3b90: i16 0, u8 n, n x (i16 AP, u64 uid)) sets the troop's AP
    c, ts = army(1, 2202311)
    _, s = entered(10235, c)
    assert ap_pushes(s) == [(ts[0]["uid"], 85), (ts[1]["uid"], 85)] and ts[0]["ap"] == ts[1]["ap"] == 85


def test_a_fallen_deck_troop_pays_the_death_ap_once():
    # spottable Troop_Death 5 when the troop is wiped (the enemy's 0x5053 reports until its units are down), once
    from test_battle import enc_uid, hit_header
    c, ts = army(1)
    role, s = entered(10235, c)
    s.sent.clear()
    b = s.data["battle"]
    enemy = next(u for u, t in b.troops.items() if u >= 10000 and t.get("c") and t["c"]["team"] != 0
                 and t["c"]["branch"] != "PROP")               # not a building: those take nothing but siege (C5)
    body = lambda: (hit_header(troop=enemy) + struct.pack("<H", 1) + enc_uid(1) + struct.pack("<H", 10)
                    + b"".join(bytes([0, 0, 0, 0, k + 3, 0]) for k in range(10)) + struct.pack("<H", 0))
    for _ in range(2000):
        role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, body()))
        if not any(b.troops[1]["units"]):
            break
    assert not any(b.troops[1]["units"]) and ap_pushes(s) == [(ts[0]["uid"], 85 - 5)]
    role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, body()))
    assert ap_pushes(s) == [(ts[0]["uid"], 80)] and 1 in s.data["deck"]


def test_a_won_mission_pays_every_deployed_troop_the_same_exp_one_level_at_most():
    # mission_reward Troop_Exp (10235 Normal) to each deployed troop, dead or alive; a troop levels at most once a
    # mission and keeps need - 1 then (the official notes' "level up restriction", 99/100); the record's troop line is
    # the exp it kept (T2.3); a troop at its MAX_LEVEL keeps nothing, and the barracks pool gets one share a win
    # (floor(Troop_Exp x %ExpTypeRate BARRACK 0.25): the tape's 20304 / 20305 windows, two Lv 30 troops, one share)
    c, ts = army(1, 2202311, 1100111)
    ts[1]["exp"] = troops.troop_need(2202311, 1) - 1        # one short of level 2
    ts[0]["level"] = 30                                      # troop 100's MAX_LEVEL
    troops.lineup(c)["slots"][3] = 0
    _, s = entered(10235, c)
    s.data["started_at"] -= 600
    s.data["battle"].troops[2]["units"] = [0] * 16          # the archers fell: they are paid too
    game.mission_won(s, NoSave())
    s.run_later()                                           # the director's ending lines, then the win
    rec = bytes(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE).buf)[8:]
    paid = int(game.reward_row(10235, 0, rec[0x284])["Troop_Exp"])
    assert paid == 375                                      # every grade's, first clear
    kept = struct.unpack_from("<Q", rec, 0x3b + 0x44 * 2)[0]
    assert kept == 1 + troops.troop_need(2202311, 2) - 1    # the last point of level 1, then level 2 up to its cap
    assert struct.unpack_from("<Q", rec, 0x3b + 0x44)[0] == 0                   # the max-level troop: "Max XP"
    assert ts[1]["level"] == 2 and ts[1]["exp"] == min(paid - 1, troops.troop_need(2202311, 2) - 1)
    assert ts[0]["level"] == 30 and ts[0]["exp"] == 0 and c["barrack_exp"] == int(paid * 0.25)
    assert obf.dec_u32(rec[0x45 + 0x44:0x49 + 0x44]) == 100 and obf.dec_u32(rec[0x45 + 0x88:0x49 + 0x88]) == 2202311
    assert rec[0x53 + 0x88] == 1 and rec[0x32 + 0x88] == 2               # the archers' level before / after
    assert obf.dec_u32(rec[0x45 + 0xcc:0x49 + 0xcc]) == 0xFFFFFFFF      # the third slot stays empty
    assert ap_pushes(s)[-2:] == [(ts[0]["uid"], 80), (ts[1]["uid"], 80)]
    exp = [w for w in s.sent if w.proto == world.S2C_EXP][-1]
    slot2 = bytes(exp.buf)[5 + 17 * 2:5 + 17 * 3]
    assert struct.unpack_from("<BQ", slot2) == (2, ts[1]["exp"])       # 0x124a's deck slot 2 carries the new level

"""Loot, reward items and grades from the original's tables (ROADMAP D2, C5-C7, Q3; owner Q21 "roll from the tables";
planning/todo/ORIGINAL-RULES-PLAN.md part C): the drop slots and %SmartDrop, the %Table categories, the reward dummies
paid on a win, the result card from the grade's category, and %Mission_Grade against the footage's result windows.
Reads the installed game's tables and zone files. Run: py -m pytest -q server/tests"""
import random
import struct
from collections import Counter

import pytest

from kuf2 import combat, game, items, loot, obf, tables, zone
from kuf2.obf import T1, T2
from kuf2.packet import Reader
from conftest import run_pending

N = 20000                                    # rolls per distribution check
TOL = 0.02                                   # AC-C1: within 2 % (absolute) of the tables' odds
TOWER, NEW_HAMPTON, CHASM = 10233, 10235, 20915
GLEN_E040 = {101104113, 102104113, 151104113, 152104113, 153104113, 154104113, 155104113}    # 8016040 총E급_040


class State:
    def __init__(self):
        self.game_sessions = {}

    def save(self):
        pass


class Session:
    def __init__(self, c, spot):
        self.data = {"char": c, "account": {"id": 1, "characters": [c]}, "spot": spot, "difficulty": 0,
                     "battle": combat.Battle()}
        self.sent, self.pending = [], []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


def char(cls=0, level=4):
    return {"id": 1, "class": cls, "level": level, "exp": 0, "spot": 10354, "pos": [0, 0, 0], "gold": 0,
            "quests": {"active": {}, "done": []}}


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def card(s):
    """(item, count) of the last 0x404d reply."""
    out = bytes(next(w for w in reversed(s.sent) if w.proto == game.S2C_REWARD_CARD).buf)
    return obf.dec_u32(out[3:7]), obf.dec_u16(out[7:9])


def share(counts, keys):
    return sum(counts[k] for k in keys) / sum(counts.values())


def test_the_unnamed_drop_tables_are_read_by_their_hash():
    assert len(tables.by_hash(loot.DROPS)["Troop"]) == 1812 and len(tables.by_hash(loot.DROPS)["Leader"]) == 245
    assert len(tables.by_hash(loot.CATEGORIES)["Table"]) == 10471
    assert len(tables.by_hash(loot.SMART)["SmartDrop"]) == 96
    # 903151 `1-33_노말_E1N`, Tower's troops: F급_040 (a class piece) 10, four gems and ores 8 / 8 / 14 / 10
    assert loot.categories()[903151] == ((8007040, 10, 1, 1), (401000200, 8, 1, 1), (401100200, 8, 1, 1),
                                         (401200100, 14, 1, 1), (404000100, 10, 1, 1))
    assert loot.categories()[903126] == ()              # B6N weighs nothing: never an item


def test_a_category_gives_one_entry_by_its_weights():
    rng = random.Random(1)
    got = Counter(code for _ in range(N) for code, n in loot.roll_category(903151, rng.randrange))
    assert sum(got.values()) == N                       # always exactly one item, count 1
    f040 = {c for sub in (8017040, 8027040, 8037040, 8047040, 8057040) for c, _, _, _ in loot.categories()[sub]}
    for keys, weight in (({401200100}, 14), ({401000200}, 8), ({401100200}, 8), ({404000100}, 10), (f040, 10)):
        assert abs(share(got, keys) - weight / 50) < TOL, (keys, weight)
    # the nested F급_040 draws each class equally (1 each of 5), each piece equally (1 each of 7)
    classes = Counter(code // 100000 % 10 for code in got.elements() if code in f040)
    assert all(abs(n / sum(classes.values()) - 0.2) < TOL for n in classes.values()) and len(classes) == 5
    # B5N 903125: the troop coin 760000030 x 1..3
    counts = Counter(n for _ in range(3000) for code, n in loot.roll_category(903125, rng.randrange))
    assert set(counts) == {1, 2, 3} and all(abs(v / 3000 - 1 / 3) < 0.04 for v in counts.values())


def test_a_troop_drops_at_its_slot_chance_scaled_by_the_spot():
    # 133050 (Tower's troops and leaders): slot 1 903151 at 12766 in 100,000 (6 in 47)
    rng = random.Random(2)
    hits = lambda spot, tid=133050, lead=None: sum(bool(loot.roll_drops(spot, tid, lead, rng.randrange))
                                                   for _ in range(N)) / N
    assert abs(hits(TOWER) - 0.12766) < TOL                     # %SmartDrop 10233: 100000 / 100000
    assert loot.spot_scale(10306) == 50000 and loot.spot_scale(10306, common=True) == 25000
    assert abs(hits(10306) - 0.12766 / 2) < TOL                  # New Hampton Ramparts: PerPlayerDropProb 50000
    assert loot.spot_scale(10237) == loot.PROB                   # the Goblin Nest has no row: unscaled (ours)
    # a Common_Drop row takes CommonDropProb: Ochanku 118510 (the climax boss of 10318, 25000): its B1N at 100000
    row = next(r for r in tables.by_hash(loot.DROPS)["Troop"] if r["NPTroopID"] == "118510")
    assert row["Common_Drop"] == "True" and row["Drop_Category5"] == "911721" and row["Drop_Category5_Prob"] == "100000"
    d104 = {c for sub, _, _, _ in loot.categories()[8005104] for c, _, _, _ in loot.categories()[sub]}   # its B1N
    gear = sum(any(code in d104 for code, _ in loot.roll_drops(10318, 118510, roll=rng.randrange))
               for _ in range(4000)) / 4000
    assert abs(gear - 0.25) < 0.03
    # a leader's own row rolls too: 133040 leads Tower's troops with the same 12766
    assert abs(hits(TOWER, tid=None, lead=133040) - 0.12766) < TOL
    assert loot.roll_drops(TOWER, 133050, roll=lambda n: n - 1) == []     # the highest roll misses every slot


def test_event_tokens_do_not_drop_while_events_are_off():
    # the reward dummy 133260's slot 30 is B7N 916726: the Easter 2020 egg 760000044 x3 at 100000
    assert loot.categories()[916726] == ((760000044, 10, 3, 3),) and items.row(760000044)["Rarity"] == "EVENT"
    assert loot.roll_category(916726) == []
    got = loot.roll_drops(TOWER, 133260, roll=lambda n: 0)          # every slot hits, first entries picked
    assert [code for code, _ in got] == [101104113, 760000030]      # B1N's first piece, B5N's troop coin; no egg


def test_a_killed_troop_drops_its_normal_loot_on_the_ground(monkeypatch):
    # Mist Field zone 1's wolves (154080, zone troop 10099): slot 1 900151 at 5000; every roll 0 here: a hit, and the
    # category's first entry (F급_010 -> Glen's first piece)
    monkeypatch.setattr(random, "randrange", lambda n: 0)
    role = game.make(State(), 0)
    s = Session(char(), 10350)
    t = next(t for t in zone.for_spot(10350)["NPCTroopInfoData"] if t["TroopID"] == 10099)
    assert t["TroopTableID"] == 154080
    s.data["zone_troops"] = {t["TroopID"]: t}
    s.data["battle"].add_np(t["TroopID"], 1, 1)                           # one unit of 1 hp: one hit wipes it
    s.data["battle"].add_hero(0, 1000, c=game.hero_combatant(s.data["char"]))
    hit = bytes(8) + bytes([T2[0], T1[0]]) + struct.pack("<H", 29) + bytes(1) + struct.pack("<H", 72) + \
        struct.pack("<H", 1) + bytes([T2[t["TroopID"] >> 8], T1[t["TroopID"] & 0xff]]) + \
        struct.pack("<H", 1) + bytes([0, 0, 0, 0, 3, 0]) + struct.pack("<H", 0)
    role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit))
    first = loot.categories()[loot.categories()[loot.categories()[900151][0][0]][0][0]][0][0]
    assert list(s.data["drops"].values()) == [{0: (first, 1)}]
    assert any(w.proto == game.S2C_REWARD_BOX for w in s.sent)
    # an ally's kill of a troop the player's side never fought drops no normal loot (ours, as its exp: B7 kill credit)
    s = Session(char(), 10350)
    s.data["zone_troops"] = {t["TroopID"]: t}
    s.data["battle"].add_np(t["TroopID"], 1, 1)
    s.data["battle"].add_np(7, 1072, 19, c=combat.combatant(10, 1, atk=(100, 100)))    # an allied troop, not his
    role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, bytes(8) + bytes([T2[0], T1[7]]) + hit[10:]))
    assert game.S2C_KILL_FEED in [w.proto for w in s.sent]       # it fell
    assert not s.data.get("drops")


def test_a_win_drops_the_reward_dummys_loot_and_gold():
    assert [(t["TroopID"], tid) for t, tid in game.reward_dummies(TOWER, 0)] == [(39000, 133260)]
    assert [(t["TroopID"], tid) for t, tid in game.reward_dummies(NEW_HAMPTON, 0)] == [(25000, 135740)]
    assert [tid for _, tid in game.reward_dummies(CHASM, 1)] == [20263200]          # the Hard variant's own row
    assert [tid for _, tid in game.reward_dummies(TOWER, 1)] == [133260]            # no Hard row: the same dummy
    assert game.reward_dummies(10358, 0) == []
    s = Session(char(), TOWER)
    game.mission_won(s, State())
    run_pending(s)
    assert s.data.get("mission_won")
    # 133260: B1N 903121 (E급_040: a piece of any class) and B5N 903125 (the troop coin x 1..3) at 100000; B6N weighs
    # nothing; B7N is the event egg. item_drop_money 45..55 gold.
    (bag,) = s.data["drops"].values()
    (piece, one), (coin, n) = bag[0], bag[1]
    e040 = {c for sub, _, _, _ in loot.categories()[8006040] for c, _, _, _ in loot.categories()[sub]}
    assert piece in e040 and one == 1 and coin == 760000030 and 1 <= n <= 3
    (gold,) = s.data["gold_drops"].values()
    assert 45 <= gold <= 55
    boxes = [w.proto for w in s.sent]
    assert boxes.index(game.S2C_REWARD_BOX) < boxes.index(game.S2C_MISSION_COMPLETE)   # the kill, then the window


@pytest.mark.parametrize("cls, code", [(0, "GLEN"), (4, "REGNIER")])
def test_the_result_card_rolls_the_grades_category_for_the_hero_class(cls, code):
    st = State()
    c = char(cls)
    s = Session(c, TOWER)
    st.game_sessions[1] = s
    game.mission_won(s, st)                             # no room start: 0 s, S: 903111 `1-33_노말_A1N`
    run_pending(s)
    rec = bytes(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE).buf)[8:]
    assert rec[0x284] == 0 and rec[0x29f:0x2a1] == obf.u16(1)          # one card, as in the footage
    assert s.data["cards"]["category"] == 903111
    game.open_card(s, s, st, bytes([2]))
    item, n = card(s)
    assert items.row(item)["ReqHero"] == code and item % 1000 == 113 and n == 1     # E grade, the hero's class
    assert item in GLEN_E040 if code == "GLEN" else item // 100000 % 10 == 3       # 광 (Berserker) pieces: 10x304113
    assert [(i["code"], i["count"]) for i in c["bag"]] == [(item, 1)]
    assert s.sent[-1].proto == game.S2C_REWARD_CARD     # no auto-leave: the player presses Mission Complete
    game.open_card(s, s, st, bytes([1]))                # past the allowed one: empty
    assert card(s) == (game.EMPTY_CARD, 0)
    # D (903115): E급 7, F급 3 -> about 30 % old (F) pieces, all the hero's
    rng = random.Random(3)
    got = [loot.roll_category(903115, rng.randrange, hero=code)[0][0] for _ in range(5000)]
    assert all(items.row(i)["ReqHero"] == code for i in got)
    assert abs(sum(i % 1000 == 119 for i in got) / 5000 - 0.3) < TOL


def test_the_camp_card_is_its_rows_category_and_a_row_without_one_draws_the_entry_list():
    # the training camps' rows name their category in Category3: 10349's 12040002 `경험치_부대 전술 교본_1_3`, Troop
    # Strategy Book I x3 (the footage's spear camp card, part 12 7:52: "Troop Strategy Book I", selling price 3)
    st = State()
    s = Session(char(), 10349)
    game.mission_won(s, st)
    run_pending(s)
    assert s.data["cards"]["category"] == 12040002
    game.open_card(s, s, st, bytes([0]))
    assert card(s) == (351100010, 3)
    # 10302 (1-02) keeps rows without a category, as the rifts and extremes do: the entry list, else the nearest
    # mission's (ours)
    s = Session(char(), 10302)
    game.mission_won(s, st)
    run_pending(s)
    assert s.data["cards"]["category"] is None and s.data["cards"]["pool"] == game.fallback_pool(char(), 10302, 0)
    assert s.data["cards"]["allowed"] == 1


# The footage's result windows (planning/playthrough; frames read 2026-09-29): spot, seconds (Clear Time), damage,
# hero deaths -> Clear / Damage / Participants Points, Death Penalty, Total, grade
FOOTAGE = [
    (10233, 853, 0, 0, 100000, 100000, 20000, 0, 220000, "S"),     # part 2 19:14, Tower 14:13
    (10235, 989, 1, 5, 100000, 99687, 19968, 19968, 199687, "S"),  # part 3 41:46, New Hampton 16:29 (deaths inferred)
    (10212, 322, 0, 0, 120000, 80000, 20000, 0, 220000, "S"),      # part 6 6:00, 5:22
    (10328, 340, 0, 0, 100000, 100000, 20000, 0, 220000, "S"),     # part 8 10:54, Forest of Fog 5:40
    (10305, 644, 0, 0, 95222, 100000, 19522, 0, 214744, "S"),      # part 9 11:22, Stalker Forest 10:44
    (10323, 537, 0, 0, 75732, 100000, 17573, 0, 193305, "A"),      # part 11 9:28, Deathwood 8:57
    (10349, 267, 192, 0, 100000, 48800, 14880, 0, 163680, "C"),    # part 12 7:42, the spear camp 4:27
    (20303, 386, 0, 0, 100000, 100000, 20000, 0, 220000, "S"),     # part 16 8:52, 6:26
    (20304, 356, 18, 0, 100000, 97689, 19768, 0, 217457, "S"),     # part 17 6:36, Field of Veterans 5:56
]


@pytest.mark.parametrize("spot, secs, dmg, deaths, clear, damage, party, death, total, grade", FOOTAGE)
def test_the_original_grade_reproduces_the_footage(spot, secs, dmg, deaths, clear, damage, party, death, total, grade):
    p = loot.grade_points(loot.grade_row(spot, "Normal"), secs, dmg, deaths)
    assert (p["clear"], p["damage"], p["party"], p["death"], p["total"]) == (clear, damage, party, death, total)
    assert game.GRADES[p["grade"]] == grade


def test_tower_is_graded_by_its_mission_grade_row():
    row = loot.grade_row(TOWER, "Normal")               # 856-1,283 s, MaxDmg 110, S / A / B / C 0.85 / .75 / .65 / .55
    assert (row["MinTime"], row["MaxTime"], row["SRate"]) == ("856", "1283", "0.85")
    # 1,154 s is the video's position of the result window (part 2, 19:14), not a clear time: B there
    p = loot.grade_points(row, 1154)
    assert (p["clear"], p["party"], p["total"], game.GRADES[p["grade"]]) == (30210, 13021, 143231, "B")
    assert game.GRADES[loot.grade_points(row, 1283)["grade"]] == "D"          # 110,000 of 220,000: 0.5
    assert loot.grade_row(10358, "Normal") is None and loot.grade_row(10361, "Normal") is None


def test_the_unknown_corridor_grades_s_a_b_by_its_310_second_band():
    row = loot.grade_row(10540, "Normal")               # MaxTime 310, S 0.480, A 0.319, B / C 0; no damage, no party
    grades = {t: game.GRADES[loot.grade_points(row, t)["grade"]] for t in (0, 161, 162, 211, 212, 400)}
    assert grades == {0: "S", 161: "S", 162: "A", 211: "A", 212: "B", 400: "B"}


def test_the_win_record_carries_the_windows_numbers():
    s = Session(char(), TOWER)
    s.data["started_at"] = game.time.monotonic() - 1154.2
    s.data["hero_deaths"] = 1
    game.mission_won(s, State())
    run_pending(s)
    out = bytes(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE).buf)
    assert out[:3] == bytes(2) + bytes([1]) and struct.unpack_from("<I", out, 3)[0] == 1154    # Clear Time
    rec = out[8:]
    # 30210 + 100000, participants 13021, one death 2 % of 130210 = 2604: 140627 / 220000 = 0.639 -> C
    assert struct.unpack_from("<Q", rec, 0x287)[0] == 30210 and struct.unpack_from("<Q", rec, 0x274)[0] == 100000
    assert struct.unpack_from("<Q", rec, 0x28f)[0] == 13021 and struct.unpack_from("<q", rec, 0)[0] == -2604
    assert struct.unpack_from("<Q", rec, 0x27c)[0] == 140627 and rec[0x284] == 3
    assert struct.unpack_from("<Q", rec, 0x17)[0] == 131                 # 10233's C row: Hero_Exp 131


def test_a_mission_the_original_did_not_grade_keeps_our_par_grade():
    # the rift 10335: mission_reward rows but no %Mission_Grade row (the rifts 10335-10344 / 20351-20356, 20502, 20504,
    # 20909); a mission with neither (Grey Fog) shows no window at all (decision B2, test_rewards)
    s = Session(char(level=30), 10335)
    game.spawn_zone_troops(s)
    s.data["started_at"] = game.time.monotonic() - 1.25 * game.mission_par(s)
    game.mission_won(s, State())
    run_pending(s)
    rec = bytes(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE).buf)[8:]
    assert rec[0x284] == 1 and struct.unpack_from("<Q", rec, 0x27c)[0] == 0          # A on par time, no points
    assert s.data["cards"]["allowed"] == 1 and s.data["cards"]["category"] is None and s.data["cards"]["pool"]


def hit_to_wipe(role, s, uid):
    """The hero's one hit on troop uid (one unit of 1 hp): the kill path game.troop_down runs (C2S 0x50b3)."""
    s.data["battle"].add_np(uid, 1, 1)
    s.data["battle"].add_hero(0, 1000, c=game.hero_combatant(s.data["char"]))
    hit = bytes(8) + bytes([T2[0], T1[0]]) + struct.pack("<H", 29) + bytes(1) + struct.pack("<H", 72) + \
        struct.pack("<H", 1) + bytes([T2[uid >> 8], T1[uid & 0xff]]) + \
        struct.pack("<H", 1) + bytes([0, 0, 0, 0, 3, 0]) + struct.pack("<H", 0)
    role.handlers[combat.C2S_HIT](s, pkt(combat.C2S_HIT, hit))


def test_hard_and_hell_rows_come_from_the_change_tables():
    # %NP_Troop_Change (0x5cb86f03dea69d54) names each troop's Hard / Hell row: the 7-digit ids take the "20" / "30"
    # prefix (Essex Centre's boss 1091110 -> 201091110 `하드보스`, whose %Troop row has its own B slots), 2-12's Hell
    # uses its Hard row, the Goblin Nest's settings are other goblins, the story missions keep their Normal row
    assert game.difficulty_troop(1091110, 1) == 201091110 and game.difficulty_troop(1091110, 2) == 301091110
    assert loot.roll_drops(10322, 201091110, roll=lambda n: 0) != loot.roll_drops(10322, 1091110, roll=lambda n: 0)
    assert game.difficulty_troop(130010, 2) == 20130010 and game.difficulty_troop(131020, 2) == 20131020
    assert game.difficulty_troop(137010, 1) == 137030 and game.difficulty_troop(137020, 2) == 137060
    assert game.difficulty_troop(133080, 1) == 133080 == game.difficulty_troop(133080, 2)
    # no change row: the ids' own prefix where such a row exists (ours: the corridor 1-90, 1-18, 1-00 have them)
    assert game.difficulty_troop(190240, 1) == 20190240 and game.difficulty_troop(190240, 2) == 30190240
    assert game.difficulty_troop(103290, 2) == 103290               # the named Hell row is not in the table
    assert game.difficulty_troop(201091110, 1) == 201091110          # already a variant (a respawn)
    # %NP_Leader_Change the same way (Fort Valley's commander 106030; 111010 stays itself on every difficulty)
    assert [game.difficulty_leader(106030, d) for d in (0, 1, 2, 7)] == [106030, 20106030, 30106030, 106030]
    assert game.difficulty_leader(111010, 1) == 111010 and game.difficulty_leader(-100, 1) == -100
    assert game.difficulty_leader(130010, 2) == 20130010              # Hell on the Hard row, as its troops


def test_the_nest_setting_changes_what_its_goblins_drop():
    # the setting is the entry difficulty (rules.setting): Vision's goblins 137030 / 137040 carry visionstones,
    # Enchanter's 137050 / 137060 enchantment stones and grindstones (OFFICIAL-NOTES: "reward type = chosen difficulty")
    first = lambda tid: [items.name(c) for c, _ in loot.roll_drops(10237, tid, roll=lambda n: 0)]
    assert first(game.difficulty_troop(137010, 0)) == ["Silver Piece (1,000 Gold)"]
    assert first(game.difficulty_troop(137010, 1)) == ["Region Visionstone Bersia Mercenaries"]
    assert first(game.difficulty_troop(137010, 2)) == ["Hironeiden Enchantment Stone"]


def test_a_hard_leader_drops_from_its_hard_row(monkeypatch):
    # Fort Valley 10306 troop 20003 (106050, commander 106030) on Hard: the troop spawns as 20106050 and its leader's
    # loot is %Leader 20106030 (903741 at 30769) instead of 106030's (903641 at 40000); every roll 0 here
    monkeypatch.setattr(random, "randrange", lambda n: 0)
    role = game.make(State(), 0)
    s = Session(char(level=12), 10306)
    s.data["difficulty"] = 1
    t = next(t for t in zone.for_spot(10306)["NPCTroopInfoData"] if t["TroopID"] == 20003)
    assert game.spawn_zone_troop(s, t) and s.data["zone_troops"][20003]["TroopTableID"] == 20106050
    hit_to_wipe(role, s, 20003)
    (bag,) = s.data["drops"].values()
    assert list(bag.values()) == loot.roll_drops(10306, 20106050, 20106030, roll=lambda n: 0)
    assert loot.roll_drops(10306, 20106050, 20106030, roll=lambda n: 0)[-1] != \
        loot.roll_drops(10306, 20106050, 106030, roll=lambda n: 0)[-1]      # the Hard row's pick, not the Normal's
    assert s.data["zone_troops"][20003]["NPLeaderID"] == 106030     # his hp, skills and quest names: the Normal row
    # Hell: 30106050 and 30106030 hold rows with no slot filled: nothing drops
    assert loot.roll_drops(10306, 30106050, game.difficulty_leader(106030, 2), roll=lambda n: 0) == []

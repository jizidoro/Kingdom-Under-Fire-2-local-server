"""The troop rules the census found off (planning/rules/TROOPS.md; decisions A5 / B5 of 2026-09-30). Every expectation
is recomputed from the shipped tables (mission_reward, lvexptable %TroopExp / %ExpTypeRate, trooptable) or read off
the original's result windows and HUD (the tape), and the byte places are the client's:
- T2.4 / T2.5: every won mission puts floor(Troop_Exp x %ExpTypeRate BARRACK 0.25) into the barracks pool; the
  result record carries it at +0x297 (u64: ProcessPacket_PVEMissionEnd 0x14085b300 keeps +0x297 - the Noble share
  +0x80 at +0x78, which PlayExp 0x14085d650 hands the window as nBarrackExp, "Barracks Saved EXP"); the gauge reads the
  pool now (WorldMapTroopListMgr +0x18, 0x1363) against its cap (+0x20).
- T2.6: a max-level troop's exp is not a second share (20304 / 20305: two Lv 30 troops "Max XP", the pool one share).
- T2.3: the window's troop line is the exp the troop actually kept (one level a mission, held at need - 1).
- T1.3: a unit's HP is floored before x its units (the tape's 8,830 for the level-6 infantry).
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import game, obf, troops
from test_army import NoSave, army, entered


# --- T2.4: Barracks Saved EXP = floor(Troop_Exp x 0.25), one share a win ---

# the original's result windows: (spot, difficulty, grade, the window's number, the event multiplier on the tape).
# Parts 11 / 17 ran under the +100 % hero and troop XP event (MISSIONS F6; events are off here, Q9): the window
# shows 2 x the share, the share floored first (512 = 2 x 256, not floor(2052 x 0.25) = 513)
WINDOWS = [(10235, 0, "S", 93, 1),      # part 3 f_01258: Drafted Infantry + Grey Wood Bowman
           (10306, 0, "B", 120, 1),     # part 5 f_00481
           (10212, 0, "S", 144, 1),     # part 6 f_00184
           (10328, 0, "S", 170, 1),     # MISSIONS F9
           (10305, 0, "S", 180, 1),
           (10309, 0, "S", 196, 1),
           (10303, 0, "S", 127, 1),
           (10306, 1, "S", 122, 1),     # Hard
           (10327, 0, "S", 135, 1),
           (10323, 0, "A", 512, 2),     # part 11 f_00289
           (20304, 0, "S", 844, 2),     # part 17 f_00203: two Lv 30 troops ("Max XP") and a Lv 23: still one share
           (20305, 0, "D", 870, 2)]     # part 17 f_01433 (the census's 478 was a frame mid-count): the same


@pytest.mark.parametrize("spot, difficulty, grade, shown, event", WINDOWS)
def test_the_barracks_share_of_a_win_is_a_quarter_of_the_troop_exp(spot, difficulty, grade, shown, event):
    row = game.reward_row(spot, difficulty, game.GRADES.index(grade))
    amount = game.troop_mission_exp(spot, difficulty, row, 0)
    assert troops.barracks_share(amount) * event == shown


def won(c, spot=10235, difficulty=0):
    """A won room at spot: (the 0x5044 record, the session)."""
    _, s = entered(spot, c, difficulty)
    s.data["started_at"] -= 600
    game.mission_won(s, NoSave())
    s.run_later()                                           # the director's ending lines, then the win
    rec = bytes(next(w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE).buf)[8:]
    return rec, s


def slot(rec, k):
    """Troop slot k (1..3) of the record: (id, level before, level after, exp now, exp gained, start %, end %)."""
    at = 0x44 * k
    return (obf.dec_u32(rec[0x45 + at:0x49 + at]), rec[0x53 + at], rec[0x32 + at],
            *struct.unpack_from("<QQ", rec, 0x33 + at), rec[0x51 + at], rec[0x52 + at])


def test_the_win_fills_the_pool_and_the_records_barracks_field_and_pushes_the_pool_first():
    c, ts = army(1, 2202311)
    rec, s = won(c)
    share = troops.barracks_share(375)                      # 10235 Troop_Exp 375 on every grade
    assert share == 93 and c["barrack_exp"] == 93
    assert struct.unpack_from("<Q", rec, 0x297)[0] == 93    # "Barracks Saved EXP"
    protos = [w.proto for w in s.sent]
    pool = protos.index(troops.S2C_POOL)
    assert pool < protos.index(game.S2C_MISSION_COMPLETE)   # the gauge reads the pool now (mgr +0x18)
    assert struct.unpack_from("<Q", bytes(s.sent[pool].buf))[0] == 93


def test_a_max_level_troop_keeps_nothing_and_adds_no_second_share():
    c, ts = army(1, 2202311)
    ts[0]["level"] = 30                                     # troop 100's MAX_LEVEL
    rec, _ = won(c)
    assert slot(rec, 1)[:5] == (100, 30, 30, 0, 0)          # the window's "Max XP"
    assert c["barrack_exp"] == 93


def test_a_win_with_no_deck_troop_still_pays_the_share():
    c, _ = army(1, deck=())                                 # A5: every won mission
    rec, _ = won(c)
    assert c["barrack_exp"] == 93 and struct.unpack_from("<Q", rec, 0x297)[0] == 93


def test_the_share_stops_at_the_pools_cap_and_the_record_says_what_fitted():
    c, _ = army(1)
    cap = troops.pool_cap(c["level"])
    c["barrack_exp"] = cap - 10
    rec, _ = won(c)
    assert c["barrack_exp"] == cap and struct.unpack_from("<Q", rec, 0x297)[0] == 10


# --- T2.2 / T2.3: the window's troop exp is what the troop kept ---

# the tape's troop lines (troop, level, exp before, Troop_Exp) -> (shown gain, level after, exp after): one level at
# most, the exp held at the new level's need - 1 (lvexptable %TroopExp 1101 / 1200)
CAPS = [(100, 6, 43, 375, 369, 7, 231),           # 10235 S, part 3 f_01258: Drafted Infantry Lv 7 369
        (2202311, 1, 0, 375, 53, 2, 36),          # the Grey Wood Bowman Lv 2 53
        (100, 8, 289, 480, 353, 9, 352),          # 10306 B, part 5 f_00481: Infantry Lv 9 353
        (2202311, 2, 36, 480, 64, 3, 63),         # Bowman Lv 3 64
        (1100111, 10, 422, 576, 499, 11, 498),    # 10212 S, part 6 f_00184: Long Swordsman Lv 11 499
        (2202311, 4, 96, 576, 136, 5, 135),       # Bowman Lv 5 136
        (2202311, 3, 0, 20, 20, 3, 20)]           # no level: the whole amount


@pytest.mark.parametrize("tid, level, exp, amount, shown, after, kept", CAPS)
def test_the_troop_exp_shown_is_the_capped_gain(tid, level, exp, amount, shown, after, kept):
    t = {"uid": 1, "id": tid, "level": level, "exp": exp}
    assert troops.gain_exp({}, t, amount) == (level, shown)
    assert (t["level"], t["exp"]) == (after, kept)


def test_the_record_carries_the_kept_exp_and_the_gauges_percentages():
    c, ts = army(1, 2202311)
    ts[0]["level"], ts[0]["exp"] = 6, 43
    rec, _ = won(c)
    # +0x51 / +0x52: the gauge's start and end (PlayExp: AddExp = (after - before) x 100 - start + end, in percent)
    assert slot(rec, 1) == (100, 6, 7, 231, 369, 43 * 100 // 181, 231 * 100 // 232)
    assert slot(rec, 2) == (2202311, 1, 2, 36, 53, 0, 36 * 100 // 37)
    assert rec[0x32 + 0x44 * 1] > rec[0x53 + 0x44] and ts[0]["exp"] + 1 == troops.troop_need(100, 7)  # the
    # client's "(Level-up Restriction)" test (0x14085b300: need(after) <= exp + 1 after a level-up)


# --- T1.3: the unit's HP is floored ---

HP = [(100, 6, 8830),           # part 2 f_00920 / part 3 f_00811: Drafted Infantry Lv 6, floor(211 + 134.5 x 5) x 10
      (1100113, 21, 241920),    # part 11 f_00020: Long Swordsman 3★ Lv 21
      (2202313, 21, 126000),    # Grey Wood Bowman 3★ Lv 21
      (2202311, 1, 4800)]       # part 3 f_00840: Grey Wood Bowman ★1 Lv 1


@pytest.mark.parametrize("tid, level, hp", HP)
def test_a_troops_hp_is_its_floored_unit_hp_times_its_units(tid, level, hp):
    assert troops.troop_hp(tid, level) == hp
    assert troops.hp_of({"id": tid, "level": level}) == hp


# --- small exact ones: the cheer item's AP, a promotion's AP, the troop book ---

def world_session():
    from test_quest import Session, State
    from kuf2 import world
    return world.make(State(), 0, "127.0.0.1", 0), Session()


def wpkt(proto, body):
    from test_quest import pkt
    return pkt(proto, body)


def ap_list(w):
    """[(uid, AP)] of one 0x1365 (NotifyActionPower 0x140da3b90: i16 0, u8 n, n x (i16 AP, u64 uid))."""
    b = bytes(w.buf)
    return [(struct.unpack_from("<Q", b, 5 + 10 * k)[0], struct.unpack_from("<h", b, 3 + 10 * k)[0])
            for k in range(b[2])]


def test_the_cheer_item_shows_every_troops_ap_at_once():
    # T4.7: 0x1343 inserts only troops the client does not hold (0x140da82e0): the new AP goes out in 0x1365
    from kuf2 import world
    role, s = world_session()
    c = s.data["char"]
    c.update(level=10, bag=[{"code": 351500200, "slot": 0, "count": 1, "serial": 4, "bound": False}])
    ts = [troops.grant(c, 1)[0], troops.grant(c, 1)[0]]
    ts[0]["ap"], ts[1]["ap"] = 5, 60
    body = bytes(6) + obf.u32(351500200) + bytes(2) + obf.u64(4) + obf.u16(1) + bytes(5)
    role.handlers[world.C2S_USE_ITEM](s, wpkt(world.C2S_USE_ITEM, body))
    pushes = [w for w in s.sent if w.proto == troops.S2C_AP]
    assert len(pushes) == 1 and ap_list(pushes[0]) == [(ts[0]["uid"], 100), (ts[1]["uid"], 100)]


def test_a_promotion_refills_the_troops_ap_and_opens_its_book_page():
    # T12.5: the reply 0x140e40800 rebuilds the troop and sets its AP to the new row's ActingPower; T12.6: a troop type
    # new to the book goes out alone (0x1371, 0x140da5a20: one coded u32)
    role, s = world_session()
    c = s.data["char"]
    c.update(level=10, gold=100000, bag=[{"code": 354000000, "slot": 1, "count": 10, "serial": 92, "bound": True},
                                         {"code": 354100000, "slot": 2, "count": 10, "serial": 93, "bound": True}])
    t, _ = troops.grant(c, 1)                                   # troop 100, level 6
    t["ap"] = 35
    role.handlers[troops.C2S_PROMOTE](s, wpkt(troops.C2S_PROMOTE, struct.pack("<QQIQ", t["uid"], 0, 1000000, 0)))
    assert t["id"] == 1100111 and t["ap"] == int(troops.troop_row(1100111)["ActingPower"]) == 100
    assert 1100111 in c["troop_pedia"]
    one = [bytes(w.buf) for w in s.sent if w.proto == troops.S2C_PEDIA_ONE]
    assert one == [obf.u32(1100111)]


def test_the_troop_book_lists_the_troops_ever_held():
    # T12.6: 0x136f (every entry, 0x140d9b2c0) -> 0x1370 (0x140da5900): u16 n, n coded u32 ids; the client keeps
    # those above 999999 (the %TroopPedia ids)
    from kuf2 import world
    role, s = world_session()
    c = s.data["char"]
    c["troop_pedia"] = [100, 1100111, 2202311]
    role.handlers[troops.C2S_PEDIA](s, wpkt(troops.C2S_PEDIA, b""))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == troops.S2C_PEDIA
    assert out == struct.pack("<H", 3) + obf.u32(100) + obf.u32(1100111) + obf.u32(2202311)
    assert troops.C2S_PEDIA not in world.EMPTY_REPLIES


def test_a_contract_troop_new_to_the_book_is_sent_alone():
    from kuf2 import world
    role, s = world_session()
    c = s.data["char"]
    set_id = next(r["SetID"] for r in __import__("kuf2.tables", fromlist=["x"]).sections("troopsaletable")["Set"]
                  if r["TroopID"] == "1100111")
    code = 355000000
    c.update(level=10, bag=[{"code": code, "slot": 0, "count": 2, "serial": 7, "bound": False}])
    import kuf2.items as items_mod
    row = dict(items_mod.row(code))
    row["GainSetId"] = set_id
    orig = items_mod.row
    items_mod.row = lambda k: row if k == code else orig(k)
    try:
        body = bytes(6) + obf.u32(code) + bytes(2) + obf.u64(7) + obf.u16(1) + bytes(5)
        role.handlers[world.C2S_USE_ITEM](s, wpkt(world.C2S_USE_ITEM, body))
        c["cooldowns"]["6"][1] -= 1  # Contract cooldown elapsed before recruiting another of the same type.
        role.handlers[world.C2S_USE_ITEM](s, wpkt(world.C2S_USE_ITEM, body))       # the same type again: no page
    finally:
        items_mod.row = orig
    assert [t["id"] for t in c["troops"]] == [1100111, 1100111]
    assert [bytes(w.buf) for w in s.sent if w.proto == troops.S2C_PEDIA_ONE] == [obf.u32(1100111)]


# --- B5: the troops' Cubic services, the badge recovery price ---

def badge_rows():
    from kuf2 import tables
    return tables.sections("item_consume_sub")["ExtractBadge"]


def test_every_badges_recovery_price_is_the_clients_product():
    # T13.4: the item module's loader 0x14184a320 fills a [star][rarity] table: gold = UseGoldCount2(StarRating) x
    # UseGoldCount1(ItemRarity), Cubic = UseCubicCount2 x UseCubicCount1; the recovery window reads it
    # (0x140653160 -> 0x14184dbf0) before it sends 0x165a
    from kuf2 import items
    rows = badge_rows()
    by_rarity = {r["ItemRarity"]: r for r in rows}
    by_star = {r["StarRating"]: r for r in rows if r["StarRating"]}
    badges = [r for r in items._index().values() if r.get("ItemKind") == "TROOP_ITEM" and r.get("StarRating") in by_star
              and r.get("Rarity") in by_rarity]
    assert len(badges) > 250
    for r in badges:
        a, b = by_rarity[r["Rarity"]], by_star[r["StarRating"]]
        assert troops.badge_price(r["ItemCode"]) == int(a["UseGoldCount1"]) * int(b["UseGoldCount2"])
        assert troops.badge_cubic(r["ItemCode"]) == int(a["UseCubicCount1"]) * int(b["UseCubicCount2"])
    one = next(r["ItemCode"] for r in badges if r["Rarity"] == "NORMAL" and r["StarRating"] == "1")
    assert (troops.badge_price(one), troops.badge_cubic(one)) == (100 * 10, 29 * 1)


def badge_session(cubic):
    from kuf2 import items
    role, s = world_session()
    c = s.data["char"]
    code = int(next(r["ItemCode"] for r in items._index().values()
                    if r.get("ItemKind") == "TROOP_ITEM" and r.get("StarRating") == "2" and r.get("Rarity") == "NORMAL"))
    c.update(gold=0, cubic=cubic, bag=[])
    t, _ = troops.grant(c, 1)
    t["badges"] = [{"slot": 0, "code": code, "serial": 95, "bound": True}]
    return role, s, c, t, code


def test_a_badge_comes_back_for_cubic():
    from kuf2 import world
    role, s, c, t, code = badge_session(200)
    price = troops.badge_cubic(code)
    assert price == 29 * 2                                  # NORMAL 29 x ★2 2
    role.handlers[troops.C2S_BADGE_OFF](s, wpkt(troops.C2S_BADGE_OFF, struct.pack("<QHB", t["uid"], 0, 1)))
    assert bytes(next(w for w in s.sent if w.proto == troops.S2C_BADGE_OFF).buf) == bytes(2)
    assert c["cubic"] == 200 - price and t["badges"] == [] and c["bag"][0]["code"] == code
    assert any(w.proto == world.S2C_CUBIC for w in s.sent)


def test_a_badge_for_cubic_needs_the_cubic():
    from kuf2 import world
    role, s, c, t, code = badge_session(10)
    role.handlers[troops.C2S_BADGE_OFF](s, wpkt(troops.C2S_BADGE_OFF, struct.pack("<QHB", t["uid"], 0, 1)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.CUBIC_SHORT) and c["cubic"] == 10 and t["badges"]


def test_an_academy_level_priced_in_cubic_is_paid_in_cubic():
    # T5.5 / B5: item_currency TroopSkill_Levelup CostGroups 3-5 ask Cubic (the Grey Wood Bowmen's 70194: 6 for level 1)
    from kuf2 import world
    role, s = world_session()
    c = s.data["char"]
    c.update(gold=0, cubic=10)
    assert troops.tactics_price(70194, 1) == ("Cubic", 6)
    role.handlers[troops.C2S_TACTICS_UP](s, wpkt(troops.C2S_TACTICS_UP, obf.u32(70194)))
    assert troops.skill_level(c, 70194) == 1 and c["cubic"] == 4
    assert any(w.proto == world.S2C_CUBIC for w in s.sent)
    assert any(w.proto == troops.S2C_TACTICS_UP and bytes(w.buf)[:2] == bytes(2) for w in s.sent)
    role.handlers[troops.C2S_TACTICS_UP](s, wpkt(troops.C2S_TACTICS_UP, obf.u32(70194)))    # level 2: more than 4
    assert struct.unpack_from("<h", bytes(s.sent[-1].buf))[0] == world.CUBIC_SHORT and troops.skill_level(c, 70194) == 1


# --- T13.1 / T1.9 / T13.2: troop gear ---

def gear_troop(c, tid, level=1):
    c["next_serial"] = c.get("next_serial", 0) + 1
    t = {"uid": (1 << 32) | 0x20000 | c["next_serial"], "id": tid, "level": level, "exp": 0, "ap": 100,
         "favorite": False, "gear": [], "skills": [], "sp": 0, "leader": None}
    c.setdefault("troops", []).append(t)
    return t


# (troop, its rarity) -> the default gear the client builds (0x140d97150: TroopGrade above GRADE2, slot k from
# TroopRarity 3 + k, table 0x1422b2a08; the lowest rarity of the troop's group in that slot, +0)
DEFAULTS = [(3103121, []),                                   # GRADE3 RARITY1: none
            (3103123, [(0, 3103111, 0)]),                    # RARITY3: the weapon
            (3103124, [(0, 3103111, 0), (1, 3103121, 0)]),   # RARITY4: and the armour
            (3103125, [(0, 3103111, 0), (1, 3103121, 0), (2, 3103131, 0)]),
            (1100113, [])]                                   # GRADE1 (the tape's Long Swordsman): none


@pytest.mark.parametrize("tid, want", DEFAULTS)
def test_a_troop_carries_the_clients_default_gear(tid, want):
    t = gear_troop({}, tid)
    assert [(k, int(r["Equip_Id"]), e) for k, r, e in troops.gear(t)] == want


def test_gear_adds_its_base_and_enchant_traits():
    # troopequipment %EnchantTrait: Base + ENCHANT<level> (ADD); the MAGIC weapon 3103112 at +2: ATTACK_PHYSICAL
    # 38 + 13 ... read from the table; HP_MAX per unit as a badge's (ours)
    from kuf2 import tables
    t = gear_troop({}, 3103125, level=10)
    t["gear"] = [{"slot": 0, "enchant": 2, "rarity": 2}]
    rows = {r["Equip_Id"]: r for r in tables.sections("troopequipment")["EnchantTrait"]}
    add = int(rows["3103112"]["Base"]) + int(rows["3103112"]["ENCHANT2"])
    plain = troops.level_row(3103125, 10)
    worn = troops.troop_level_row(t)
    assert worn["ATTACK_PHYSICAL"] == pytest.approx(plain["ATTACK_PHYSICAL"] + add)
    assert worn["CRITICAL_REDUCE"] == pytest.approx(plain["CRITICAL_REDUCE"])     # the default accessory is +0 NORMAL
    t["gear"] = [{"slot": 1, "enchant": 5, "rarity": 1}]                           # NORMAL armour +5: HP_MAX 1080 a unit
    hp = int(rows["3103121"]["ENCHANT5"])
    assert troops.hp_of(t) == (troops.unit_hp(plain) + hp) * plain["UNIT_COUNT"]


def gear_session(tid, gold, bag):
    role, s = world_session()
    c = s.data["char"]
    c.update(gold=gold, bag=[{"code": code, "slot": i, "count": n, "serial": 500 + i, "bound": False}
                             for i, (code, n) in enumerate(bag)])
    return role, s, c, gear_troop(c, tid)


def test_enchanting_troop_gear_costs_the_clients_gold_and_grindstones():
    # CommonSubTroopEquipEnchant: 0x1148 (i8 levels, u8 slot, u64 troop) -> 0x1149 (0x14064e670: i16 0, i8, u8, u64);
    # the window's price (0x14064d980): the %EnchantCost row (TroopGrade, the slot's type, the gear's rarity) Enchant
    # <k>_Gold x BaseGold for each level passed, Enchant_Count Enchant_Material a level (0x14064d810)
    role, s, c, t = gear_session(3103123, 6000, [(405100100, 12)])
    role.handlers[troops.C2S_GEAR_ENCHANT](s, wpkt(troops.C2S_GEAR_ENCHANT, struct.pack("<bBQ", 2, 0, t["uid"])))
    out = bytes(next(w for w in s.sent if w.proto == troops.S2C_GEAR_ENCHANT).buf)
    assert out == struct.pack("<HbBQ", 0, 2, 0, t["uid"])
    assert c["gold"] == 6000 - 2500 - 3000 and sum(i["count"] for i in c["bag"]) == 2
    assert t["gear"] == [{"slot": 0, "enchant": 2, "rarity": 1}]
    b = bytes(troops.barracks_packet(c).buf)
    assert b.endswith(bytes([1, 0]) + struct.pack("<HB", 2, 1))       # m 1: slot 0, enchant 2, rarity NORMAL


@pytest.mark.parametrize("gold, stones, levels, code", [(1000, 12, 2, 0x6401),      # the gold (text 0x1b94)
                                                         (9000, 9, 2, 0x2c5d),      # the grindstones
                                                         (99999, 99, 6, 1)])        # past MaxEnchant 5
def test_an_enchant_short_of_its_price_is_refused(gold, stones, levels, code):
    role, s, c, t = gear_session(3103123, gold, [(405100100, stones)])
    role.handlers[troops.C2S_GEAR_ENCHANT](s, wpkt(troops.C2S_GEAR_ENCHANT, struct.pack("<bBQ", levels, 0, t["uid"])))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", code) and t["gear"] == [] and c["gold"] == gold


def test_a_fully_enchanted_piece_upgrades_to_the_next_rarity():
    # 0x114a (u8 slot, u64 troop) -> 0x114b (0x14064e820: i16 0, u8, u64); the client takes the next rarity of the
    # group's slot itself (0x1418ac110) at +0; the price (0x14064d980 / 0x14064d810 in mode 1): %Basic Upgrade_Gold and
    # Upgrade_Count Upgrade_Material of the piece worn
    role, s, c, t = gear_session(3103123, 20000, [(354100020, 60)])
    t["gear"] = [{"slot": 0, "enchant": 5, "rarity": 1}]
    role.handlers[troops.C2S_GEAR_UPGRADE](s, wpkt(troops.C2S_GEAR_UPGRADE, struct.pack("<BQ", 0, t["uid"])))
    out = bytes(next(w for w in s.sent if w.proto == troops.S2C_GEAR_UPGRADE).buf)
    assert out == struct.pack("<HBQ", 0, 0, t["uid"])
    assert t["gear"] == [{"slot": 0, "enchant": 0, "rarity": 2}] and c["gold"] == 10000
    assert sum(i["count"] for i in c["bag"]) == 10
    assert [int(r["Equip_Id"]) for _, r, _ in troops.gear(t)] == [3103112]


def test_an_upgrade_needs_the_full_enchant_and_a_next_rarity():
    role, s, c, t = gear_session(3103123, 99999, [(354100020, 9999)])
    t["gear"] = [{"slot": 0, "enchant": 4, "rarity": 1}]
    role.handlers[troops.C2S_GEAR_UPGRADE](s, wpkt(troops.C2S_GEAR_UPGRADE, struct.pack("<BQ", 0, t["uid"])))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", 1)
    t["gear"] = [{"slot": 0, "enchant": 5, "rarity": 3}]                           # RARE: GRADE3's last
    role.handlers[troops.C2S_GEAR_UPGRADE](s, wpkt(troops.C2S_GEAR_UPGRADE, struct.pack("<BQ", 0, t["uid"])))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", 1) and t["gear"][0]["rarity"] == 3


# --- T1.10: the troop set effect ---

def group_troop(group):
    """A trooptable id of TroopGroupID `group` (its first)."""
    from kuf2 import tables
    return int(next(r["TROOP_ID"] for r in tables.sections("trooptable")["Contents"] if r["TroopGroupID"] == group))


def set_lineup(set_id, groups, key=troops.MAIN_DECK):
    """A character whose lineup `key` holds one troop of each group in slots 1.., with set `set_id` chosen (0x1372)."""
    c = {"id": 1, "class": 0, "level": 30}
    lu = troops.lineup(c, key)
    for k, g in enumerate(groups, 1):
        t = gear_troop(c, group_troop(g))
        lu["slots"][k] = t["uid"]
    lu["set"] = set_id
    return c


SET_141 = ["32039", "32034", "32040", "33031"]          # trooptechtree %TroopSet 141: StatusEffectID 701960, 4 groups


def test_a_set_is_on_when_the_lineup_holds_every_component_group():
    # 0x140d9c860 (the deck window's "the set would break" check, message 100000): every ComponentTroop<n>ID is a
    # TroopGroupID with a troop among the lineup's slots 1..8 (0x1418bbbc0 lists a group's troops)
    assert troops.set_effect(set_lineup(141, SET_141)) == (701960, troops.SET_LEVEL)
    assert troops.set_effect(set_lineup(141, SET_141[:3])) is None                  # one group short
    assert troops.set_effect(set_lineup(0, SET_141)) is None                        # no set chosen
    assert troops.set_effect(set_lineup(141, SET_141, key="3")) is None             # another lineup's


def test_the_sets_status_goes_on_the_deck_troops_in_the_room():
    # the status (Target TROOP, held) on each deck troop the room takes; set 231's 701910 also takes M_DEFENCE_MAGICAL
    # 5 % off (SUBTRACT, Traitvalue021) in the troop's record
    from kuf2 import status
    comps = ["22026", "22027", "21026", "21027", "21028"]
    c = set_lineup(231, comps)
    assert troops.set_effect(c) == (701910, troops.SET_LEVEL)
    t = troops.find(c, troops.lineup(c)["slots"][1])
    plain = troops.level_row(t["id"], t["level"])
    row = troops.room_row(c, t)
    assert row["DEFENCE_MAGICAL"] == pytest.approx(plain["DEFENCE_MAGICAL"] * 0.95)
    c.update(name="T", look="00" * 0x33, quests={"active": {}, "done": []})
    _, s = entered(10306, c)                                   # New Hampton Ramparts: Limit_Troop 2
    held = s.data.get("statuses", {})
    deck = sorted(s.data["deck"])
    assert deck and all(701910 in status.holding(s, uid) for uid in deck)


# --- T11.2: the player's own troops in formation / charging ---

@pytest.mark.parametrize("tid, cls, state, attacker, kind, want", [
    (1100421, 5, "FRONTAL", 157, "MOUNTED", 0.1),   # a deck spear line (DEFENCE_TYPE 230 -> 213): cavalry x0.1
    (1100421, 0, "IDLE", 157, "MOUNTED", 1.0),
    (1100721, 4, "CHARGE", 154, "DENSE", 6.0)])     # a charging deck cavalry (205 -> 208): spears x6
def test_a_deck_troops_reported_state_picks_its_synastry_row(tid, cls, state, attacker, kind, want):
    # the host's 0x50b0 reports every troop of a solo room, the player's own too: flags & 0x7f is its state class
    # (combat.troop_states, 600a611); the census row T11.2 read "only MELEE / IDLE" from an older note
    from kuf2 import combat, game
    from test_army import pkt
    from test_battle import sync_body
    c = {"id": 1, "class": 0, "level": 30, "name": "T", "look": "00" * 0x33, "quests": {"active": {}, "done": []}}
    t = gear_troop(c, tid, level=10)
    troops.lineup(c)["slots"][1] = t["uid"]
    role, s = entered(10306, c)
    role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, sync_body((1, cls))))
    assert combat.state_of(s, 1) == state
    deck = s.data["battle"].troops[1]["c"]
    assert combat.synastry(combat.np_combatant(attacker, 1), deck, kind, combat.state_of(s, 1)) == pytest.approx(want)

"""Troop skills from their full table definitions (owner 2026-09-30 ~20:xx: "we need to load the schema for trop
skills"; the rules census planning/rules/TROOPS.md T5.3, T5.4, T5.8, T5.11 / T1.11). Every expectation here is
recomputed from the shipped tables (tacticsacademy, abilitycastinfo %Improvement, statuseffectinfo %Improvement,
trooptable %NewSkill / %SkillGroup) or read off the original's tape, and the byte places are the client's:
- T5.8: a player troop's cast costs the hero's SP (the tape, part 2 f_01098 -> f_01099: 570 -> 533 as the handed
  archers' Fire Arrow 500045, SP 40, goes off, + 3 regeneration); the client checks, the server spends.
- T5.3: a troop skill's level is the tactics academy's (0x10bd 0x140da5310 writes it into every troop's list; the
  equip window 0x1409b2a30 reads only the academy map).
- T1.11 / T5.11: a troop's passives (its skills in the passive slots 4..7, %NewSkill SkillGroupID_P_n) put their
  SELF statuses on it and their stats into its room record.
- T5.4: learning a troop skill in the equip window costs SkillOpenGold / SkillOpenCash (0 on every row: the client
  never sends 0x136d) and needs the academy to hold it.
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import combat, game, obf, skills, status, tables, troops
from test_army import NoSave, army, entered, pkt, troop_entries, troops_role
from test_battle import Even
from test_np_skills import execute
from test_troop_skills import WorldSession, detail_skills, info_block


def cast(role, s, caster, ability, target):
    """A troop's 0x505f (test_np_skills.cast's body); the serial of its 0x5060 (an SP push may follow it)."""
    body = obf.u16(target) + struct.pack("<H", caster) + obf.u32(ability) + bytes(7)
    n = len(s.sent)
    role.handlers[combat.C2S_TROOP_CAST](s, pkt(combat.C2S_TROOP_CAST, body))
    out = next(bytes(w.buf) for w in s.sent[n:] if w.proto == combat.S2C_TROOP_CAST)
    assert len(out) == 17 and struct.unpack_from("<H", out, 0xf)[0] == caster
    return struct.unpack_from("<H", out, 0xd)[0]


def manual_cast(role, s, caster, ability, target):
    """The HUD's0x5117 path, observed for native Grey Rock F1 Shield Use I."""
    body = (obf.u32(ability) + bytes(10) + obf.u16(target) + struct.pack("<H", caster)
            + bytes(7) + obf.u16(0) + bytes(3))
    n = len(s.sent)
    role.handlers[combat.C2S_USE_ABILITY](s, pkt(combat.C2S_USE_ABILITY, body))
    out = next(bytes(w.buf) for w in s.sent[n:] if w.proto == combat.S2C_USE_ABILITY)
    assert out[0] == 0 and struct.unpack_from("<H", out, 5)[0] == caster
    return struct.unpack_from("<H", out, 3)[0]


def sp_pushes(s, since):
    """The hero's SP values the server pushed (0x5138 stat 6) after sent[since]."""
    out = []
    for w in s.sent[since:]:
        if w.proto != combat.S2C_STATS:
            continue
        b = bytes(w.buf)
        for k in range(b[0]):
            value, sid = struct.unpack_from("<Ib", b, 1 + 7 * k)
            if sid == combat.STAT_SP:
                out.append(value)
    return out


def table_sp(ability, level):
    return int((status.cast_row(ability, level) or {}).get("SP", "0"))


# --- T5.8: the hero's SP pays the player's troops' casts ---

def room(spot, *sets, hand=()):
    c, ts = army(*sets)
    role, s = entered(spot, c)
    for uid in hand:
        game.hand_troop(s, uid)
    return c, ts, role, s


# the three troops seen live today and their skill: (spot, contract sets, handed, caster uid, ability, level, SP)
LIVE = [(10234, (1,), (), 1, 81001, 1, 50),               # Grey Rock's F1: the deck troop 100, Shield Use I (academy 1)
        (10234, (1,), (), 10073, 500045, 1, 40),          # Grey Rock's F2: the handed archers 134060, Fire Arrow
        (10233, (), (11006,), 11006, 200147, 8, 0)]       # Tower's archers 133120 (handed at the wyrms): 200147 Lv 8


@pytest.mark.parametrize("spot, sets, hand, caster, ability, level, sp", LIVE)
@pytest.mark.parametrize("send_cast", [cast, manual_cast])
def test_a_player_troops_cast_costs_the_heros_sp(spot, sets, hand, caster, ability, level, sp, send_cast):
    c, _, role, s = room(spot, *sets, hand=hand)
    assert status.players(s, caster) and status.cast_level(s, ability, caster) == level
    assert table_sp(ability, level) == sp                  # abilitycastinfo %Improvement SP at the cast's level
    pools = s.data["pools"]
    before = pools["sp"]
    n = len(s.sent)
    serial = send_cast(role, s, caster, ability, 20000)
    assert pools["sp"] == before - sp
    assert sp_pushes(s, n) == ([before - sp] if sp else [])   # the HUD and the client's own cost check follow
    execute(role, s, serial, [(caster, [])])
    assert pools["sp"] == before - sp                     # execute does not charge the cast again


def test_an_np_manual_cast_does_not_spend_the_players_sp():
    _, _, role, s = room(10234, 1)
    before = dict(s.data["pools"])
    n = len(s.sent)
    manual_cast(role, s, 10067, 500045, 20000)
    assert s.data["pools"] == before and sp_pushes(s, n) == []


def test_the_tapes_fire_arrow_takes_40_and_the_regeneration_gives_3():
    # part 2 f_01098 -> f_01099 (36:34 -> 36:36): SP 570 -> 533 as the F2 archers' Fire Arrow goes off, the hero with
    # the conscripts in Grey Rock regenerating 3 each 3 s (tests/test_hero_pools.py)
    c, _, role, s = room(10234, 1)
    pools = s.data["pools"]
    pools["sp"] = 570
    s.data["regen"] = False
    s.pending.clear()
    cast(role, s, 10073, 500045, 20000)
    assert pools["sp"] == 530 and pools["sp_rec"] == 3
    (delay, tick), = s.pending
    assert delay == combat.SP_TICK_S
    tick()
    assert pools["sp"] == 533


def test_an_np_or_the_heros_own_troop_cast_takes_no_sp():
    # Glen's fire archers 10067 (the same row as the handed 10073, but not the player's): their owner's SP is 0, the
    # client never fires their SP skills; the hero's own 0x505f (176, the aimed-shot trigger, Stack1 2) is paid by
    # his 0x5117 use
    c, _, role, s = room(10234, 1)
    pools = s.data["pools"]
    before = dict(pools)
    n = len(s.sent)
    cast(role, s, 10067, 500045, 20000)
    cast(role, s, 0, 176, 20000)
    assert (pools["sp"], pools["ammo"]) == (before["sp"], before["ammo"]) and sp_pushes(s, n) == []


@pytest.mark.parametrize("send_cast", [cast, manual_cast])
def test_a_cast_the_hero_cannot_pay_is_answered_and_takes_the_sp_to_0(send_cast):
    # the client refuses it (CanTargeting 0x140c23240 against the hero's SP); 0x5060 has no refusal form and an
    # unanswered cast freezes the troop, so one that arrives anyway (a race with the SP push) is answered
    c, _, role, s = room(10234, 1)
    s.data["pools"]["sp"] = 20
    send_cast(role, s, 1, 81001, 20000)
    assert s.data["pools"]["sp"] == 0


def test_a_manual_troop_skill_uses_its_academy_level_cost():
    c, _ = army(1)
    c["tactics"] = {"81001": {"level": 4, "exp": 0}}
    role, s = entered(10234, c)
    before = s.data["pools"]["sp"]
    manual_cast(role, s, 1, 81001, 1)
    assert s.data["pools"]["sp"] == before - table_sp(81001, 4)


# --- T5.3: the level is the tactics academy's ---

def test_every_academy_skill_starts_at_its_min_level():
    # tacticsacademy AbilityMinLevel 1 (116 rows) is held from the start, 0 (390) only once learned
    c, _ = army()
    for r in tables.sections("tacticsacademy")["Basic"]:
        assert troops.skill_level(c, r["AbilityID"]) == int(r["AbilityMinLevel"]), r["AbilityID"]
    listed = {obf.dec_u32(b[i:i + 4]): b[i + 8] for b in [bytes(troops.tactics_packet(c).buf)]
              for i in range(2, len(b), 9)}
    assert listed == {int(r["AbilityID"]): 1 for r in tables.sections("tacticsacademy")["Basic"]
                      if r["AbilityMinLevel"] == "1"}      # 0x10bc: the equip window shows them held


def test_every_packet_and_the_cast_carry_the_academys_level():
    # troop 100's Shield Use I 81001 levelled to 4 at the academy: the detail (0x1349), the troop's list (0x1749),
    # the room's ability list (0x3f50), the equip reply (0x1369), the cast's level and the status it puts (810010 at
    # the %Improvement Level1 of level 4)
    c, (t,) = army(1)
    c["tactics"] = {"81001": {"level": 4, "exp": 0}}
    assert detail_skills(t, c) == [(0, 4, 81001)]
    assert info_block(c, t) == [(0, 81001, 4)]
    role = troops_role()
    ws = WorldSession(c)
    role.handlers[troops.C2S_EQUIP_SKILL](ws, pkt(troops.C2S_EQUIP_SKILL, struct.pack("<QI", t["uid"], 81001)))
    out = bytes(ws.sent[-1].buf)
    assert ws.sent[-1].proto == troops.S2C_EQUIP_SKILL and struct.unpack_from("<hBIQB", out) == (0, 0, 81001, t["uid"], 4)
    game_role, s = entered(10234, c)
    _, deck = troop_entries(s)
    assert deck["abilities"] == [(4, 81001)]
    assert status.cast_level(s, 81001, 1) == 4 and s.data["battle"].troops[1]["c"]["skills"] == {81001: 4}
    st, lv = status.ability_statuses(81001, 4)[0][:2]
    serial = cast(game_role, s, 1, 81001, 1)
    execute(game_role, s, serial, [(1, [])])
    assert s.data["statuses"][1][st]["level"] == lv == int(status.cast_row(81001, 4)["Level1"])


def test_a_levelled_academy_skill_hits_at_its_level(monkeypatch):
    # the Grey Wood Bowmen's Advanced Archery 70194 (A_2, AbilityMinLevel 0): AttributeRate 677 at level 1, 786 at 4;
    # learned and levelled at the academy (Cubic there, CostGroup 3: here as a skill book leaves it), equipped, cast
    # on the kobolds in Grey Rock
    monkeypatch.setattr(combat, "random", Even())
    c, (t,) = army(2202311)
    c["tactics"] = {"70194": {"level": 4, "exp": 0}}
    troops.seat(t, troops.skill_slot(t["id"], 70194), 70194)
    role, s = entered(10234, c)
    b = s.data["battle"]
    rec, kobolds = b.troops[1]["c"], b.troops[20000]
    before = list(kobolds["units"])
    serial = cast(role, s, 1, 70194, 20000)
    execute(role, s, serial, [(20000, [0])])
    attack = combat.ability_attack(rec, 70194, 4, 1)
    assert attack["ar"] == pytest.approx(0.786)
    assert kobolds["units"][0] == before[0] - combat.resolve(rec, kobolds["c"], attack, state=combat.state_of(s, 20000))


def test_an_academy_level_up_pushes_0x10bd_at_the_next_levels_price():
    # 0x1750 on 81001 (held at 1 from the start, CostGroup 1): the level-2 price (item_currency TroopSkill_Levelup
    # CostGroup 1 Level 2 -> 580 gold), then 0x1751 and 0x10bd (the academy map and every troop's list take level 2);
    # Sharp Insight 70148 (AbilityMinLevel 0, CostGroup 2): learned for the level-1 price, 140; CostGroups 3-5 ask
    # Cubic (the Grey Wood Bowmen's 70194: 6): with no Cubic balance, "Not enough Cubics" (0x6430; B5 allows it)
    c, _ = army(1)
    c["gold"] = 1000
    role = troops_role()
    ws = WorldSession(c)
    assert troops.tactics_price(81001, 2) == ("Gold", 580) and troops.tactics_price(70148, 1) == ("Gold", 140)
    role.handlers[troops.C2S_TACTICS_UP](ws, pkt(troops.C2S_TACTICS_UP, obf.u32(81001)))
    assert c["gold"] == 420 and troops.skill_level(c, 81001) == 2
    assert [w.proto for w in ws.sent[-2:]] == [troops.S2C_TACTICS_UP, troops.S2C_TACTICS_ONE]
    one = bytes(ws.sent[-1].buf)
    assert len(one) == 9 and obf.dec_u32(one[:4]) == 81001 and one[8] == 2
    role.handlers[troops.C2S_TACTICS_UP](ws, pkt(troops.C2S_TACTICS_UP, obf.u32(70148)))
    assert c["gold"] == 280 and troops.skill_level(c, 70148) == 1
    role.handlers[troops.C2S_TACTICS_UP](ws, pkt(troops.C2S_TACTICS_UP, obf.u32(70194)))
    assert struct.unpack_from("<h", bytes(ws.sent[-1].buf))[0] == 0x6430 and troops.skill_level(c, 70194) == 0


# --- T1.11 / T5.11: passives ---

def swordsman(*learned):
    """A level-21 Long Swordsman (1100113, the tape's part 11 troop) with passives learned at the academy at the
    given levels and equipped in their slots."""
    c, (t,) = army(1)
    t.update(id=1100113, level=21, skills=[])
    c["tactics"] = {str(a): {"level": lv, "exp": 0} for a, lv in learned}
    for a, _ in learned:
        troops.seat(t, troops.skill_slot(t["id"], a), a)
    return c, t


def recomputed(abilities, level, unit="TROOP"):
    """The stats a troop's passives add, recomputed from the tables apart from the code under test: each AUTOMATIC
    ability's SELF status (abilitycastinfo %Improvement StatusEffectN, LevelN) and that status level's traits
    (statuseffectinfo %Improvement, TraitTarget ALL or the unit): ADD value_1 % and value_2, ADD_TARGET_LEVEL
    value_2 x the troop's level; speed traits are the client's."""
    ab = {r["AbilityId"]: r for r in tables.sections("abilitytypeinfo")["Basic"]}
    cast_rows = {(r["AbilityId"], r["Level"]): r for r in tables.sections("abilitycastinfo")["Improvement"]
                 if r["SpotFilter"] == "COMMON"}
    st_rows = {(r["Id"], r["Level"]): r for r in tables.sections("statuseffectinfo")["Improvement"]}
    out = []
    for a, lv in abilities.items():
        if ab[str(a)]["Category"] != "AUTOMATIC":
            continue
        row = cast_rows[(str(a), str(lv))]
        for i in (1, 2):
            if row[f"StatusEffectObject{i}"] != "SELF":
                continue
            st = st_rows[(row[f"StatusEffect{i}"], row[f"Level{i}"])]
            for j in ("01", "02"):
                name, fn = st[f"TraitType{j}"], st[f"FunctionType{j}"]
                if st[f"TraitTarget{j}"] not in ("ALL", unit) or name in ("MAX_MOVE_SPEED", "ATTACK_SPEED"):
                    continue
                p, f = float(st[f"Traitvalue{j}1"]), float(st[f"Traitvalue{j}2"])
                if fn == "ADD":
                    out += ([(name, p, True)] if p else []) + ([(name, f, False)] if f else [])
                elif fn == "ADD_TARGET_LEVEL":
                    out += [(name, f * level, False)] if f else []
    return out


def test_a_passive_goes_into_a_passive_slot():
    # %NewSkill SkillGroupID_P_1..4 are the client's slots 4..7 (the %NewSkill reader's suffix table "A_1".."P_4")
    assert troops.skill_slot(1100113, 70142) == 0 and troops.skill_slot(1100113, 70146) == 1
    assert troops.skill_slot(1100113, 70148) == 4 and troops.skill_slot(1100113, 70150) == 5
    assert troops.skill_slot(2202311, 70196) == 5


# (passive, its level, the stat, what it adds to a level-21 Long Swordsman's room row): Sharp Insight 701480
# M_CRITICAL_PROB ADD_TARGET_LEVEL 13 at level 1 (x 21), Stamina Training 701500 HP_MAX +14 % per unit at level 7
PASSIVES = [(70148, 1, "CRITICALPROB_PHYSICAL", 13 * 21), (70148, 1, "CRITICALPROB_MAGICAL", 13 * 21),
            (70148, 7, "CRITICALPROB_PHYSICAL", 28 * 21), (70150, 7, "HP_BASEUNIT", 0.14)]


@pytest.mark.parametrize("ability, level, stat, adds", PASSIVES)
def test_a_passive_adds_its_status_traits_to_the_troops_room_stats(ability, level, stat, adds):
    c, t = swordsman((ability, level))
    plain, inside = troops.troop_level_row(t), troops.room_row(c, t)
    assert troops.passives(c, t) == {ability: level}
    assert status.passive_traits({ability: level}, 21) == recomputed({ability: level}, 21)
    want = plain[stat] * (1 + adds) if isinstance(adds, float) else plain[stat] + adds
    assert inside[stat] == pytest.approx(want)


def test_the_passives_status_list_matches_the_tables_for_every_troop_passive():
    # T1.11's CHECKABLE row: the status list per passive, for every AUTOMATIC skill of every %NewSkill passive group
    t = tables.sections("trooptable")
    groups = {g["SkillGroupID"]: g for g in t["SkillGroup"]}
    cast_rows = {(r["AbilityId"], r["Level"]): r for r in tables.sections("abilitycastinfo")["Improvement"]
                 if r["SpotFilter"] == "COMMON"}
    seen = 0
    for r in t["NewSkill"]:
        for n in range(1, 5):
            for k in range(1, 6):
                a = (groups.get(r[f"SkillGroupID_P_{n}"]) or {}).get(f"SkillId_{k}", "-")
                if not a.isdigit() or int(a) not in status.automatic():
                    continue
                row = cast_rows[(a, "3")]
                want = [(int(row[f"StatusEffect{i}"]), int(row[f"Level{i}"])) for i in (1, 2)
                        if row[f"StatusEffectObject{i}"] == "SELF"]
                assert status.passive_statuses({int(a): 3}) == want, a
                seen += 1
    assert seen > 900


def test_the_room_carries_the_passives_their_statuses_and_their_stats():
    # the swordsman with Sharp Insight (level 1) and Stamina Training (level 7) in Grey Rock: the 0x3f50 entry lists
    # them in its second list and carries the HP with +14 %; the battle's units have that HP and the record the crit;
    # the two held statuses go on at the room start (0x5074, caster itself); the room's troop window (0x1367) shows
    # them, the barracks' (0x1349) does not ("Sharp Insight" applies only inside a mission [C])
    c, t = swordsman((70148, 1), (70150, 7))
    role, s = entered(10234, c)
    _, deck = troop_entries(s)
    inside, plain = troops.room_row(c, t), troops.troop_level_row(t)
    assert deck["hp"] == troops.unit_hp(inside) * inside["UNIT_COUNT"] > troops.unit_hp(plain) * plain["UNIT_COUNT"]
    rec = s.data["battle"].troops[1]
    assert rec["units"][0] == troops.unit_hp(inside)
    assert rec["c"]["passives"] == {70148: 1, 70150: 7}
    held = s.data["statuses"][1]
    # Sharp Insight's crit is read from the held status by the resolver (combat.RESOLVER_TRAITS), not the record's row
    assert rec["c"]["crit"][combat.PHYSICAL][0] == plain["CRITICALPROB_PHYSICAL"]
    assert combat.crit_chance(rec["c"], None, own=combat.held_levels(s, 1)) * 1000 == pytest.approx(
        plain["CRITICALPROB_PHYSICAL"] + 13 * 21)
    assert held[701480]["level"] == 1 and held[701500]["level"] == 7 and held[701480]["until"] is None
    assert second_lists(s)[1] == [(1, 70148), (7, 70150)]
    ws = WorldSession(c)
    troops_role().handlers[troops.C2S_BATTLE_DETAIL](ws, pkt(troops.C2S_BATTLE_DETAIL, struct.pack("<Q", t["uid"])))
    room_detail = bytes(ws.sent[-1].buf)[10:10 + troops.DETAIL_BLOCK]
    assert room_detail == troops.detail_block(t, inside) != troops.detail_block(t)


def second_lists(s):
    """[(level, ability)] of each 0x3f50 entry's second ability list (0x140d0deb0, slots 0x10 + place), in order."""
    b = bytes(next(w for w in s.sent if w.proto == game.S2C_START_TROOP_INFO).buf)
    n, i, out = struct.unpack_from("<H", b)[0], 2, []
    for _ in range(n):
        i += 0x28
        i += 1 + (25 if obf.T1[b[i]] & 1 else 0)
        i += 2 + 5 * struct.unpack_from("<H", b, i)[0]
        k = struct.unpack_from("<H", b, i)[0]
        out.append([struct.unpack_from("<BI", b, i + 2 + 5 * j) for j in range(k)])
        i += 2 + 5 * k + 2
        i += 2 + struct.unpack_from("<H", b, i)[0]
    return out


def test_an_attack_passive_counts_once(monkeypatch):
    # a status the resolver reads itself (ATTACK_* ADD on the attacker's held statuses, status_bonus) stays out of
    # the record's row and in the room window's: NP troop 145200 (Hironiden's) holds 500038 -> 943090, ATTACK_PHYSICAL
    # +22 %: its record's attack is the table's, its hits x 1.22 with the status held
    monkeypatch.setattr(combat, "random", Even())
    row = combat._rows_by("nptrooptable", "Contents", "NPTROOP_ID")["145200"]
    rec, _, traited, _ = game.np_records(145200, 1, row)
    assert rec["atk"][combat.PHYSICAL][0] == float(row["ATTACK_PHYSICAL"])
    assert ("ATTACK_PHYSICAL", 22.0, True) in status.passive_traits(rec["passives"], rec["level"])
    assert ("ATTACK_PHYSICAL", 22.0, True) not in status.passive_traits(rec["passives"], rec["level"], live=False)
    target = combat.np_combatant(134040, 0)
    attack = combat.hit_attack(rec)
    held = dict(status.passive_statuses(rec["passives"]))
    plain, buffed = combat.resolve(rec, target, attack), combat.resolve(rec, target, attack, own=held)
    assert buffed == round(plain * 1.22) or abs(buffed - plain * 1.22) <= 1


def test_a_leaders_passive_reaches_his_troop_and_the_troops_his(monkeypatch):
    # np_records merges the troop's and its leader's passives: TROOP / ALL traits into the troop's row, LEADER / ALL
    # into the leader's (no leader row of this build carries a stat passive: a leader given 145230's 500026, SELF
    # 3000267 M_DEFENCE_PHYSICAL ADD_TARGET_LEVEL)
    row = combat._rows_by("nptrooptable", "Contents", "NPTROOP_ID")["134040"]
    lead = combat._rows_by("npleadertable", "Contents", "NPLEADER_ID")["134010"]
    real = combat.combatant_leader
    monkeypatch.setattr(combat, "combatant_leader", lambda r, team=1: dict(real(r, team), passives={500026: 7}))
    rec, lead_rec, _, _ = game.np_records(134040, 1, row, lead)
    adds = sum(v for n, v, p in status.passive_traits({500026: 7}, rec["level"]) if n == "M_DEFENCE_PHYSICAL")
    # a defence trait of a held status is the resolver's (combat.RESOLVER_TRAITS): the row keeps the table's, the
    # troop holding the passive's status meets hits with both
    base = combat.np_combatant(134040, 1)["def"]["CLOSE"]
    assert adds and rec["def"]["CLOSE"] == base
    held = dict(status.passive_statuses({500026: 7}))
    assert combat._stat(rec, "DEFENCE_PHYSICAL_CLOSE", None, held, base) == pytest.approx(base + adds)


def test_a_zone_troops_passive_statuses_go_on_at_its_spawn():
    # Hironiden's 145200 (500038 -> 943090, 500039 -> 942170, held) spawned into a room: both on it, held
    from test_battle import mission_room
    s = mission_room(10234)
    t = dict(next(iter(s.data["zone_troops"].values())), TroopID=48000, TroopTableID=145200, NPLeaderID=-100)
    assert game.spawn_zone_troop(s, t)
    assert set(s.data["statuses"][48000]) == {943090, 942170}


# --- T5.4: learning in the equip window ---

def test_no_troop_skill_has_a_learn_price():
    # SkillOpenGold / SkillOpenCash, the equip window's LearnSkill prices: 0 on every row, so the client returns
    # before asking (0x140636b40) and never sends 0x136d
    assert {troops.learn_price(r["AbilityID"]) for r in tables.sections("tacticsacademy")["Basic"]} == {(0, 0)}


def test_learning_needs_the_academy_and_is_free():
    # Advanced Archery 70194 (AbilityMinLevel 0): refused until the academy holds it, then seated in its slot, free
    c, (t,) = army(2202311)
    c["gold"] = 50
    role = troops_role()
    ws = WorldSession(c)
    learn = lambda a: role.handlers[troops.C2S_LEARN_SKILL](ws, pkt(troops.C2S_LEARN_SKILL, struct.pack("<IQ", a, t["uid"])))
    learn(70194)
    assert struct.unpack_from("<h", bytes(ws.sent[-1].buf))[0] == 1 and len(t["skills"]) == 1
    c["tactics"] = {"70194": {"level": 1, "exp": 0}}
    t["id"] = 2202313  # SkillGrade 3 also needs the troop's RARITY3; the academy alone is insufficient.
    learn(70194)
    assert struct.unpack_from("<h", bytes(ws.sent[-1].buf))[0] == 0 and c["gold"] == 50
    assert {"slot": 1, "id": 70194} in t["skills"]


# --- table-driven: every player troop row ---

def test_every_troops_default_skills_come_from_its_groups_first_held_skill():
    t = tables.sections("trooptable")
    groups = {g["SkillGroupID"]: g for g in t["SkillGroup"]}
    minimum = {r["AbilityID"]: r["AbilityMinLevel"] for r in tables.sections("tacticsacademy")["Basic"]}
    skill_grades = {r["AbilityID"]: int(r["SkillGrade"]) for r in tables.sections("tacticsacademy")["Basic"]}
    rarities = {r["TROOP_ID"]: int(r["TroopRarity"].removeprefix("RARITY"))
                for r in t["Contents"] if r.get("TroopRarity", "").startswith("RARITY")}
    tops = {r["TROOP_ID"]: r.get("MaxActiveSkill", "0") for r in t["Contents"]}
    c, _ = army()
    n = 0
    for r in t["NewSkill"]:
        want = []
        for slot in range(min(4, int(float(tops.get(r["TROOP_ID"], "0") or 0)))):
            g = groups.get(r[f"SkillGroupID_A_{slot + 1}"]) or {}
            first = next((a for a in (g.get(f"SkillId_{k}", "-") for k in range(1, 6))
                          if minimum.get(a) == "1" and skill_grades[a] <= rarities.get(r["TROOP_ID"], 0)), None)
            if first:
                want.append({"slot": slot, "id": int(first)})
        assert troops.default_skills(c, r["TROOP_ID"]) == want, r["TROOP_ID"]
        n += bool(want)
    assert n > 500


def test_every_troop_skills_cost_is_its_tables_sp():
    # the SP a player troop's cast takes (combat.spend), for every skill of every %NewSkill group at levels 1 and 7
    t = tables.sections("trooptable")
    ids = {int(g[f"SkillId_{k}"]) for g in t["SkillGroup"] for k in range(1, 6) if g[f"SkillId_{k}"].isdigit()}

    class S:
        data = {}
        sent = []

        def send(self, w):
            self.sent.append(w)
    checked = 0
    for a in sorted(ids):
        for lv in (1, 7):
            row = status.cast_row(a, lv)
            if row is None:
                continue
            s = S()
            s.data = {"pools": {"sp": 10000, "sp_max": 10000, "ammo": 200, "ammo_max": 255, "fp": 0}}
            combat.spend(s, a, lv)
            assert s.data["pools"]["sp"] == 10000 - int(row["SP"]), (a, lv)
            checked += 1
    assert checked > 1000

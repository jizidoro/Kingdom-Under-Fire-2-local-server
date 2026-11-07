"""The rules census's combat rows (planning/rules/COMBAT.md) that a table can recompute: the hit roll and its words, the
guard, immunity, the revive's invincibility, the peace timer, the reaction copies, a skill's penetration, a leader's
0x5053 blow. Run: py -m pytest -q server/tests/test_combat_rules.py"""
import random
import struct
import time

import pytest

from kuf2 import combat, game, obf, status
from kuf2.obf import T1, T2
from conftest import run_pending
from test_battle import Even, FieldSession, NoSave, enc_uid, hero_record, pkt, record


class Seq:
    """A resolver roll: random() gives the listed values in turn (then 1.0: no miss, no crit), uniform the middle."""
    def __init__(self, *values):
        self.values = list(values)

    def uniform(self, a, b):
        return (a + b) / 2

    def random(self):
        return self.values.pop(0) if self.values else 1.0


def berserker(level=6):
    """The Berserker in his class kit (Old Novice: gloves ACCURACY 132, shoes MISS 88), as on the tape."""
    return game.hero_combatant({"id": 1, "class": 4, "level": level})


def room(hero_hp=5000):
    s = FieldSession({"active": {}, "done": []})
    s.data["battle"] = combat.Battle()
    s.data["battle"].add_hero(0, hero_hp, c=berserker())
    return s


def number_records(s):
    """[(troop, unit, flags, damage)] of every 0x507b sent."""
    out = []
    for w in s.sent:
        if w.proto != combat.S2C_DAMAGE_NUMBERS:
            continue
        b = bytes(w.buf)
        n, i = struct.unpack_from("<H", b, 1)[0], 3
        for _ in range(n):
            uid, m = struct.unpack_from("<HH", b, i)
            i += 4
            for _ in range(m):
                unit, _, flags, dmg = struct.unpack_from("<HBBi", b, i)
                out.append((uid, unit, flags, dmg))
                i += 8
    return out


def hero_numbers(s):
    """[(damage, flags)] of every 0x507d sent."""
    return [(struct.unpack_from("<i", bytes(w.buf))[0], bytes(w.buf)[6]) for w in s.sent
            if w.proto == combat.S2C_HERO_DAMAGE]


# --- the hit roll (census D7, B3, D9; decision A1) ---------------------------------------------------------------

@pytest.mark.parametrize("acc,miss,add_acc,chance", [
    (132, 380, 0, 0.248),       # the Berserker's kit against Grey Rock's kobolds 134030 (MISS 380): a quarter glance
    (221, 330, 0, 0.109),       # the Gunslinger's kit against the least evasive story foes
    (400, 88, 0, 0.0),          # the kobolds (ACCURACY 400) against the Berserker (MISS 88): they never glance
    (132, 380, 100000, 0.0),    # an ability with Add_Accuracy 100000 (224 rows) never glances
    (1764, 2763, 0, 0.999),     # OFFICIAL-NOTES F144: "vs 2,763 agility you need 1,764 hit for a 1 % hit chance"
    (0, 3000, 0, 1.0),          # capped at 1
])
def test_the_miss_chance_is_miss_minus_accuracy_per_mille(acc, miss, add_acc, chance):
    att, tgt = combat.combatant(6, 0, acc=acc), combat.combatant(6, 1, miss=miss)
    assert combat.miss_chance(att, tgt, {"add_acc": add_acc}) == pytest.approx(chance)


def test_the_tables_give_the_berserker_a_quarter_of_glances_on_kobolds_and_the_kobolds_none():
    hero, kobold = berserker(), combat.np_combatant(134030)
    assert (hero["acc"], hero["miss"], hero["evade_reduce"]) == (132, 88, 900)
    assert (kobold["acc"], kobold["miss"], kobold["evade_reduce"]) == (400, 380, 900)
    assert combat.miss_chance(hero, kobold) == pytest.approx(0.248)
    assert combat.miss_chance(kobold, hero) == 0.0
    # the Berserker's Iron Body 6201 (MISS +400 flat, LEADER) lets the kobolds glance on him: (88 + 400 - 400) / 1000
    assert combat.miss_chance(kobold, hero, held={6201: 1}) == pytest.approx(0.088)
    # the evade's 6321 (MISS +3000): every hit glances (it is invincible besides: status.invincible)
    assert combat.miss_chance(kobold, hero, held={6321: 1}) == 1.0


def test_a_glancing_hit_deals_a_tenth_with_the_miss_word_and_never_crits():
    # the tape: every "Miss" number is a tenth of its neighbours' (95 / 928, 145 / 1,457, 29 / 288, 50 / 493 ...):
    # EVADE_REDUCE 900 on the target (every hero, 12,481 nptrooptable rows)
    att = combat.combatant(30, 0, atk=(1000, 1000), crit=(1000, 1000))            # a sure crit
    tgt = combat.combatant(30, 1, miss=1000, evade_reduce=900)                       # a sure glance
    assert combat.resolve_hit(att, tgt, {"type": "LOOSE"}, rng=Seq(0.0, 0.0)) == (100, combat.FLAG_MISS)
    tgt["miss"] = 0                                                                  # no glance: the crit lands
    assert combat.resolve_hit(att, tgt, {"type": "LOOSE"}, rng=Seq(0.0)) == (2000, combat.FLAG_CRITICAL)


def test_a_miss_roll_rate_on_real_tables_is_its_chance():
    hero, kobold = berserker(), combat.np_combatant(134030)
    rng = random.Random(7)
    words = [combat.resolve_hit(hero, kobold, combat.hit_attack(hero), rng=rng)[1] for _ in range(4000)]
    assert 0.22 < sum(1 for w in words if w & combat.FLAG_MISS) / len(words) < 0.28


def test_the_numbers_carry_the_words_over_units_and_over_the_hero(monkeypatch):
    # 0x507b +3 and 0x507d +6: bit 0 Critical, bit 1 Miss, bit 2 Guard, bit 3 Dodge (readers 0x140c61610 / 0x140c63760
    # and 0x140c54aa0; TextNumMgr DAMAGE_TYPE)
    s = room()
    s.data["battle"].add_np(20001, 1000, 3, c=combat.combatant(6, 1, atk=(100, 100), miss=1000, evade_reduce=900))
    monkeypatch.setattr(combat, "random", Seq(0.0))                                  # the hero glances
    combat.apply_hits(s, [(20001, [0])], game.send_troop_hp, attacker=0, attack={"type": "HERO", "pr": 1, "ar": 1},
                      record=combat.combatant(6, 0, atk=(100, 100)))
    assert number_records(s) == [(20001, 0, combat.FLAG_MISS, 10)]
    s.sent.clear()
    monkeypatch.setattr(combat, "random", Seq(1.0, 0.0))                             # no glance, then a crit
    combat.apply_hits(s, [(0, [-1])], game.send_troop_hp, attacker=20001, attack={"type": "LOOSE"},
                      record=combat.combatant(6, 1, atk=(100, 100), crit=(1000, 500)))
    (dmg, flags), = hero_numbers(s)
    assert flags == combat.FLAG_CRITICAL and dmg > 100


def a_far_fight():
    """Two zone troops at each other far from the hero: the crash site's guards and bandits (10169 / 10019, 34 000 units
    from the camp, 2026-11-05 08:18)."""
    s = room()
    s.data["battle"].add_np(20001, 1000, 3, c=combat.combatant(6, 1, atk=(100, 100)))
    s.data["battle"].add_np(20002, 1000, 3, c=combat.combatant(6, 1, atk=(100, 100)))
    s.data["hero_pos"] = (70733, 0, 188453)
    s.data["last_pos"] = {20001: (98905, 0, 168976), 20002: (99012, 0, 168826)}
    return s


def npc_hit(s):
    return combat.apply_hits(s, [(20001, [0])], game.send_troop_hp, attacker=20002, attack={"type": "LOOSE"},
                             record=combat.combatant(6, 1, atk=(100, 100)))


def test_a_fight_out_of_the_heros_sight_draws_no_number_at_the_camp():
    # the client's consumer (0x140c63760) keeps the 50 nearest records and draws each where its unit projects, however
    # far: 172 and 186 floated around Glen with no fight in the camp
    s = a_far_fight()
    assert npc_hit(s) and not number_records(s)
    assert sum(s.data["battle"].troops[20001]["units"]) < 3000                               # the hit itself landed


def test_a_fight_near_the_hero_keeps_its_numbers():
    s = a_far_fight()
    s.data["last_pos"][20001] = (70733 + combat.NUMBERS_RANGE - 1, 0, 188453)
    npc_hit(s)
    assert number_records(s)


def test_the_players_own_hit_shows_its_number_at_any_range():
    s = a_far_fight()
    combat.apply_hits(s, [(20001, [0])], game.send_troop_hp, attacker=0, attack={"type": "HERO", "pr": 1, "ar": 1},
                      record=combat.combatant(6, 0, atk=(100, 100)))
    assert number_records(s)


@pytest.mark.parametrize("gone", ["hero_pos", "last_pos"])
def test_a_place_not_reported_yet_keeps_the_number(gone):
    s = a_far_fight()
    del s.data[gone]
    npc_hit(s)
    assert number_records(s)


# --- the guard (census D3, D4; decision A2) ------------------------------------------------------------------------

@pytest.mark.parametrize("byte5,kind", [(0x00, 0), (0x04, 1), (0x08, 2), (0x0c, 3), (0x02, 4), (0x06, 5), (0x0a, 6),
                                        (0xc5, 1)])      # bit 7 knock, bit 6 react, bit 0 the unit's ninth bit
def test_the_hit_kind_is_read_from_the_record(byte5, kind):
    assert combat.hit_kind(bytes([0, 0, 0, 0, 5, byte5])) == kind


@pytest.mark.parametrize("sid,level,held_s,rate", [
    (341, 1, 0, 90), (341, 1, 5.5, 85), (341, 1, 20, 70), (341, 1, 300, 70),        # Glen's guard: 90 -> 70, a point a s
    (341, 3, 300, 75),                                                               # levels 3-4 stop at 75
    (6040, 1, 10, 80),                                                               # the Berserker's guard
    (2001090, 1, 0, 100), (2001090, 1, 10, 85), (2001090, 1, 35, 55), (2001090, 1, 99, 50),   # Azilia's (100, 15, 50, 10)
    (6321, 1, 0, None),                                                              # no progress on the escape
])
def test_the_guard_progress_table(sid, level, held_s, rate):
    assert combat._progress(sid, level, 1000.0, 1000.0 + held_s) == rate


def guard_hit(s, kind, attacker=20001):
    """A 0x5053 of the NP troop on the hero's leader unit (-1) with the given hit kind."""
    b5 = ((kind & 3) << 2) | ((kind >> 2) << 1)
    header = bytes(8) + enc_uid(attacker) + struct.pack("<H", 29) + bytes(1) + struct.pack("<H", 72)
    target = enc_uid(0) + struct.pack("<H", 1) + bytes([0, 0, 0, 0, 2, b5])
    combat.on_hit(s, pkt(combat.C2S_HIT, header + struct.pack("<H", 1) + target + struct.pack("<H", 0)),
                  game.send_troop_hp)


def test_a_guarded_blow_takes_the_guard_datas_share_and_a_blow_from_behind_all(monkeypatch):
    # the guard 6040 (the Berserker's): GUARD_REDUCE 700 + its +300, x 90 % fresh -> a tenth taken (the tape's
    # "Defence 14" against the Mountain Troll's 142 / 164), x 70 % after 20 s -> three tenths; kind 0 (from behind,
    # 0x140a2ba40's facing test) is not guarded
    now = [5000.0]
    monkeypatch.setattr(combat.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(status.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(combat, "random", Even())
    s = room(hero_hp=100000)
    s.data["battle"].add_np(20001, 1000, 1, c=combat.combatant(6, 1, atk=(1000, 1000)))
    taken = []

    def blow(kind):
        before = s.data["battle"].troops[0]["hp"]
        guard_hit(s, kind)
        taken.append(before - s.data["battle"].troops[0]["hp"])

    blow(0)
    full = taken[-1]
    status.apply(s, [0], 6040, 1, 0, chant=604)
    blow(1)
    blow(0)
    now[0] += 20
    blow(1)
    assert taken[2] == full and abs(taken[1] - full * 0.1) <= 1 and abs(taken[3] - full * 0.3) <= 1
    assert [f for _, f in hero_numbers(s)] == [0, combat.FLAG_GUARD, 0, combat.FLAG_GUARD]


def test_a_guarding_unit_takes_three_tenths_with_the_guard_word(monkeypatch):
    # NP rows carry GUARD_REDUCE 700 (11,974 of 12,698) and no guard status: kind 3 (the unit in 148 DEFENSE_STANDING)
    # takes 30 %; the tape's white "Defence 23 / 21" by the hero's "80" (part 5), "757" among ~2,500 (part 14)
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["battle"].add_np(20001, 1000, 2, c=combat.combatant(6, 1, guard=700))
    s.data["battle"].add_np(20002, 1000, 1, c=combat.combatant(6, 1, atk=(100, 100)))
    for kind in (0, 3):
        header = bytes(8) + enc_uid(20002) + struct.pack("<H", 29) + bytes(1) + struct.pack("<H", 72)
        target = enc_uid(20001) + struct.pack("<H", 1) + bytes([0, 0, 0, 0, 3, (kind & 3) << 2])
        combat.on_hit(s, pkt(combat.C2S_HIT, header + struct.pack("<H", 1) + target + struct.pack("<H", 0)),
                      game.send_troop_hp)
    assert number_records(s) == [(20001, 0, 0, 100), (20001, 0, combat.FLAG_GUARD, 30)]


def test_an_ability_hit_on_a_guarding_hero_is_guarded_by_his_status(monkeypatch):
    # a report with no hit kind (0x5066, 0x505a) falls back to the guard status the target holds
    monkeypatch.setattr(combat, "random", Even())
    s = room(hero_hp=100000)
    s.data["battle"].add_np(20001, 1000, 1, c=combat.combatant(6, 1, atk=(1000, 1000)))
    combat.apply_hits(s, [(0, [-1])], game.send_troop_hp, attacker=20001, attack={"type": "LOOSE"})
    status.apply(s, [0], 6040, 1, 0, chant=604)
    combat.apply_hits(s, [(0, [-1])], game.send_troop_hp, attacker=20001, attack={"type": "LOOSE"})
    (full, plain), (dmg, flags) = hero_numbers(s)
    assert (plain, flags) == (0, combat.FLAG_GUARD) and abs(dmg - full * 0.1) <= 1


# --- immunity (census C5, gap 3) --------------------------------------------------------------------------------------

def test_a_wall_takes_nothing_but_siege_even_under_the_boost(monkeypatch):
    # New Hampton's wall 135200 (DEFENCE_TYPE 92: SIEGE 1, BLAST 0.2, every other column 0) took 1 a hit, 10,000 from
    # the boosted hero, and the archers 134060 chipped it
    wall = combat.np_combatant(135200)
    hero = berserker(30)
    assert combat.resolve(hero, wall, combat.hit_attack(hero), rng=Even()) == 0
    archers = combat.np_combatant(134060)
    assert combat.resolve(archers, wall, combat.hit_attack(archers, combat.VOLLEY_ACTION), rng=Even()) == 0
    assert combat.resolve(archers, wall, {"type": "SIEGE", "pr": 1, "ar": 1}, rng=Even()) > 0
    monkeypatch.setattr(combat, "HERO_DAMAGE_SCALE", 10000)
    s = room()
    s.data["battle"].add_np(30500, 5000, 1, c=wall)
    combat.apply_hits(s, [(30500, [0])], game.send_troop_hp, attacker=0, attack=combat.hit_attack(hero), record=hero)
    assert s.data["battle"].troops[30500]["units"] == [5000] and not number_records(s)


# --- the revive's invincibility (census J2; decision A8) -------------------------------------------------------------

def test_a_revived_hero_holds_status_33_for_5_s_and_takes_no_hits():
    s = room()
    s.data["battle"].add_np(20001, 1000, 1, c=combat.combatant(6, 1, atk=(100, 100)))
    t = s.data["battle"].troops[0]
    t["hp"], t["down"] = 0, True
    game.revive_hero(s, t, (0, 0, 0))
    b = next(bytes(w.buf) for w in s.sent if w.proto == combat.S2C_STATUS_ADD and
             struct.unpack_from("<I", bytes(w.buf), 10)[0] == 33)
    assert struct.unpack_from("<HxHH", b) == (1, 5, 0) and struct.unpack_from("<HB", b, 7) == (0xffff, 1)
    assert status.invincible(s, 0)
    combat.apply_hits(s, [(0, [-1])], game.send_troop_hp, attacker=20001, attack={"type": "LOOSE"})
    assert t["hp"] == t["max"]
    assert 5 in [d for d, fn in s.pending if "expire_status" in fn.__qualname__]


def test_a_revived_troop_holds_status_34_for_10_s():
    s = room()
    s.data["battle"].add_np(10070, 1000, 5, c=combat.combatant(6, 0))
    assert status.revive_invincible(s, 10070) == [10070]
    b = bytes(next(w for w in s.sent if w.proto == combat.S2C_STATUS_ADD).buf)
    assert struct.unpack_from("<HxHH", b) == (1, 10, 10070) and struct.unpack_from("<HBI", b, 7)[2] == 34


# --- the peace timer (decision B1) ------------------------------------------------------------------------------------

def request(s):
    b = enc_uid(0)
    combat.on_combat_mode(s, pkt(0x5132, b + bytes([T2[(1 + 2 * b[0]) & 0xff]])))


def modes(s):
    return [T1[bytes(w.buf)[3]] & 1 for w in s.sent
            if w.proto == combat.S2C_COMBAT_MODE and struct.unpack_from("<H", bytes(w.buf), 1)[0] == 0]


def advance(s, now, seconds):
    """Let `seconds` pass, running the timers that fall due."""
    end = now[0] + seconds
    while True:
        due = sorted((d, i) for i, (d, _) in enumerate(s.pending))
        if not due or now[0] + due[0][0] > end:
            break
        d, i = due[0]
        now[0] += d
        for j, (dd, fn) in enumerate(s.pending):
            s.pending[j] = (dd - d, fn)
        s.pending.pop(i)[1]()
    for j, (dd, fn) in enumerate(s.pending):
        s.pending[j] = (dd - (end - now[0]), fn)
    now[0] = end


def test_the_hero_leaves_combat_mode_after_a_quiet_spell_and_never_mid_fight(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(combat.time, "monotonic", lambda: now[0])
    s = room()
    for _ in range(15):                                  # 30 s of swinging: the client re-asks every 2 s
        request(s)
        advance(s, now, 2)
    assert modes(s) == [1] * 15                          # every request answered on, never an off in between
    advance(s, now, combat.PEACE_S - 2 - 0.5)
    assert modes(s)[-1] == 1                             # not yet
    advance(s, now, 1)
    assert modes(s)[-1] == 0 and not s.data["battle"].troops[0]["combat"]
    advance(s, now, 60)
    assert modes(s).count(0) == 1                        # one off only
    request(s)
    assert modes(s)[-1] == 1                             # his next swing draws again


def test_an_open_engagement_with_a_living_troop_keeps_the_pose_until_it_ends(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(combat.time, "monotonic", lambda: now[0])
    role = game.make(NoSave(), 0)
    s = room()
    s.data["battle"].add_np(20001, 1000, 1, c=combat.combatant(6, 1))
    role.handlers[combat.C2S_ENGAGE](s, pkt(combat.C2S_ENGAGE, obf.u16(20001) + bytes([1]) + obf.u16(0)))
    advance(s, now, 3 * combat.PEACE_S)
    assert modes(s) == [1]
    role.handlers[combat.C2S_ENGAGE](s, pkt(combat.C2S_ENGAGE, obf.u16(20001) + bytes([0]) + obf.u16(0)))
    advance(s, now, combat.PEACE_S + 1)
    assert modes(s) == [1, 0]


def test_a_held_guard_keeps_the_pose_until_it_ends(monkeypatch):
    # a guard held with no blow on it sends nothing after its start; it is not a quiet spell
    now = [100.0]
    monkeypatch.setattr(combat.time, "monotonic", lambda: now[0])
    s = room()
    request(s)
    status.apply(s, [0], 6040, 1, 0, chant=604)
    advance(s, now, 3 * combat.PEACE_S)
    assert modes(s) == [1]
    status.end(s, 0, 6040)
    advance(s, now, combat.PEACE_S + 1)
    assert modes(s) == [1, 0]


def test_other_troops_fighting_do_not_keep_the_heros_pose(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(combat.time, "monotonic", lambda: now[0])
    s = room()
    s.data["battle"].add_np(20001, 100000, 1, c=combat.combatant(6, 1, atk=(1, 1)))
    s.data["battle"].add_np(20002, 100000, 1, c=combat.combatant(6, 2, atk=(1, 1)))
    request(s)
    for _ in range(12):                                  # the allies and the enemy trade blows beside him
        combat.apply_hits(s, [(20002, [0])], game.send_troop_hp, attacker=20001, attack={"type": "LOOSE"})
        advance(s, now, 1)
    assert modes(s) == [1, 0]


# --- reaction copies, a skill's penetration, a leader's blow (census E2, A10, E4) ------------------------------------

SWING_504F = bytes.fromhex("ffff7f00e19f001000a865ab10c301001012030000ddbc0014c000ea03010bc000dd430110c00000")


def test_every_reaction_copy_is_skipped_and_an_np_0x504f_blow_lands(monkeypatch):
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["battle"].add_np(1, 1072, 19, c=combat.np_combatant(2))
    combat.on_hit(s, pkt(combat.C2S_HERO_HIT, SWING_504F), game.send_troop_hp)       # long after any cast
    assert s.data["battle"].troops[1]["units"] == [1072] * 19
    s.data["battle"].add_np(30002, 1000, 1, c=combat.combatant(6, 2, atk=(100, 100)))
    npc = struct.pack("<HH", 72, 1) + bytes([0, 0x1f]) + bytes(6) + obf.u16(30002) + SWING_504F[14:]
    combat.on_hit(s, pkt(combat.C2S_HERO_HIT, npc), game.send_troop_hp)
    assert s.data["battle"].troops[1]["units"] != [1072] * 19


def test_add_panetrate_takes_the_defence_away():
    # abilitycastinfo %Improvement Add_Panetrate (100000 on 45 rows, e.g. 172 / 118 / 415 / 740): D = max(0, def -
    # pen - Add_Panetrate)
    hero = hero_record(30)
    attack = next(atk for a, rows in combat._improvements().items()
                  if combat._f(rows.get("1", {}).get("Add_Panetrate")) >= 100000
                  for atk in [combat.ability_attack(hero, a, 1, 1)] if not atk["kill"] and atk["ar"] > 0)
    assert attack["add_pen"] >= 100000
    armoured, bare = record(0, 30, dfn=5000), record(0, 30, dfn=0)
    assert combat.resolve(hero, armoured, attack, rng=Even()) == combat.resolve(hero, bare, attack, rng=Even())
    plain = dict(attack, add_pen=0)
    assert combat.resolve(hero, armoured, plain, rng=Even()) < combat.resolve(hero, bare, plain, rng=Even())


def test_a_0x5053_blow_of_unit_minus_one_strikes_with_the_leaders_record(monkeypatch):
    monkeypatch.setattr(combat, "random", Even())
    s = room(hero_hp=100000)
    s.data["battle"].add_np(20001, 1000, 1, c=combat.combatant(6, 1, atk=(10, 10)), leader_hp=500,
                            leader_c=combat.combatant(6, 1, atk=(1000, 1000), leader=True))
    header = bytes(8) + enc_uid(20001) + struct.pack("<h", (-4 << 5) | 29) + bytes(1) + struct.pack("<H", 72)
    target = enc_uid(0) + struct.pack("<H", 1) + bytes([0, 0, 0, 0, 2, 0])
    assert combat.hit_source(header + struct.pack("<H", 1) + target, combat.C2S_HIT)[1] == combat.LEADER
    combat.on_hit(s, pkt(combat.C2S_HIT, header + struct.pack("<H", 1) + target + struct.pack("<H", 0)),
                  game.send_troop_hp)
    assert 100000 - s.data["battle"].troops[0]["hp"] > 500


def test_a_casters_fall_ends_the_statuses_bound_to_it():
    # statuseffectinfo %Basic RemoveWhenCasterDie True (7 rows: Pergos's stun 30146, the Yeti's frostbite 35030 ...)
    s = room()
    s.data["battle"].add_np(20001, 100, 1, c=combat.combatant(6, 1))
    s.data["battle"].add_np(20002, 1000, 1, c=combat.combatant(6, 1))
    status.apply(s, [0], 30146, 1, 20001)
    status.apply(s, [0], 35030, 1, 20002)
    assert {30146, 35030} <= set(s.data["statuses"][0])
    s.sent.clear()
    combat.apply_hits(s, [(20001, [0])], game.send_troop_hp, attacker=None, attack={"type": "HERO", "flat": 1000},
                      record=combat.combatant(6, 0, atk=(1000, 1000)))       # (the stunned hero strikes nothing: H14)
    assert not any(s.data["battle"].troops[20001]["units"])
    assert 30146 not in s.data["statuses"][0] and 35030 in s.data["statuses"][0]
    ends = [bytes(w.buf) for w in s.sent if w.proto == combat.S2C_STATUS_END]
    assert [struct.unpack_from("<I", b, 6)[0] for b in ends] == [30146]


# --- critical hits: the statuses' crit traits, the combos' CriticalRate (census B1, B2, B4; the hunt 2026-10-01) ---

@pytest.mark.parametrize("held,ability,per_mille", [
    ({}, 803, 150),               # the kit's CRITICALPROB 50 + a basic attack's hitsignalinfo CriticalRate 10 (+100)
    ({6200: 1}, 803, 350),        # + Burning Anger 6200 (the Madness stance, passive 643): M_CRITICAL_PROB percent 20
    ({6200: 1}, 806, 350),        # the fourth combo hit (AttributeRate 2000 = DamageRate 2): CriticalRate 10 too
    ({6200: 1}, 605, 250),        # a skill (Earth Splitter 605) has no CriticalRate: kit + stance
    ({}, 605, 50),                # the kit alone: 5 %
    ({6200: 1, 6371: 1}, 605, 350),     # + Sharpness 6371 (M_CRITICAL_PROB flat 100)
    ({6200: 1, 3337: 1}, 605, 310),     # + Battle Stance 3337 (M_CRITICAL_PROB ADD_TARGET_LEVEL 10 x Lv 6)
])
def test_the_berserkers_crit_chance_from_his_kit_his_stance_and_his_combos(held, ability, per_mille):
    # the tape (part 2 Grey Rock, 2 fps frames 31:25-41:20): 55 yellow "Critical" among 134 non-miss hero numbers (41 %);
    # his kit alone crits 5 %, his stance and combos 25-35 %
    hero = berserker()
    attack = combat.ability_attack(hero, ability)
    assert combat.crit_chance(hero, combat.np_combatant(134030), attack, combat.PHYSICAL, held) * 1000 == \
        pytest.approx(per_mille)


@pytest.mark.parametrize("status_id,points", [
    (57, 20), (58, 30), (59, 50),         # Speed Reload 1-3: CRITICALPROB_PHYSICAL percent 2 / 3 / 5, "Critical Rate +2%"
    (6200, 200),                          # Burning Anger: M_CRITICAL_PROB percent 20
    (6371, 100), (3394, 100),             # Sharpness / With a savage friend!: M_CRITICAL_PROB flat 100
])
def test_a_crit_rate_percent_is_points_not_a_share_of_the_stat(status_id, points):
    rec = combat.combatant(10, 0, crit=(50, 500), hero=True)       # 57-59 and 6200 are LEADER traits: the hero's
    assert combat._stat(rec, "CRITICALPROB_PHYSICAL", None, {status_id: 1}, 50.0) == pytest.approx(50 + points)


def test_the_berserkers_crit_rate_on_real_tables_is_the_tapes():
    # 4,000 combo hits of the Lv 6 Berserker in the Madness stance on Grey Rock's kobold infantry: 35 % of the hits that
    # do not glance crit (the tape: 41 % of 134, its binomial error 4 %; before this hunt ours was 5 %)
    hero, kobold = berserker(), combat.np_combatant(134030)
    attack, rng = combat.ability_attack(hero, 803), random.Random(11)
    words = [combat.resolve_hit(hero, kobold, attack, rng=rng, own={6200: 1})[1] for _ in range(4000)]
    landed = [w for w in words if not w & combat.FLAG_MISS]
    assert 0.32 < sum(1 for w in landed if w & combat.FLAG_CRITICAL) / len(landed) < 0.38


@pytest.mark.parametrize("white,yellow", [
    # (a plain number, a Critical of the same attack on the same foe, next to it): part 2 Grey Rock, 2 fps frames
    (125, 242), (113, 248), (112, 252), (119, 255),         # 31:25-33:17 (1885 f_00010 / f_00021, 2269 f_00004)
    (65, 146), (71, 157), (67, 155),                          # the second family (2269 f_00002, 2049 f_00004, 1951 f_00034)
    (420, 913), (434, 952),                                   # on the Mountain Troll (2429 f_00019)
])
def test_the_crit_multiplier_is_one_plus_the_kits_crit_damage_as_on_the_tape(white, yellow):
    # CRITICAL_PHYSICAL 500 (herotable) + the Old Novice weapon's 649 = 1149: x 2.149; the tape's pairs sit within the
    # two numbers' spreads (each x 0.9-1.1)
    hero = berserker()
    mult = 1 + hero["crit"][combat.PHYSICAL][1] / 1000
    assert mult == pytest.approx(2.149)
    assert 0.9 / 1.1 <= yellow / white / mult <= 1.1 / 0.9


def test_crit_damage_and_its_reduction_read_the_statuses_too():
    att = combat.combatant(30, 0, atk=(1000, 1000), crit=(1000, 500))
    tgt = combat.combatant(30, 1)
    base = combat.resolve_hit(att, tgt, {"type": "LOOSE"}, rng=Seq(0.0))
    assert base == (1500, combat.FLAG_CRITICAL)
    # Critical Wound 6373 (M_CRITICAL flat 30) on the attacker: x 1.53
    assert combat.resolve_hit(att, tgt, {"type": "LOOSE"}, rng=Seq(0.0), own={6373: 1})[0] == 1530
    # the Berserker's 6539 (CRITICAL_REDUCE flat 100, LEADER) on a leader target: x 1.4
    lead = combat.combatant(30, 1, leader=True)
    assert combat.resolve_hit(att, lead, {"type": "LOOSE"}, held={6539: 1}, rng=Seq(0.0))[0] == 1400


def test_a_passive_status_trait_counts_once_on_a_troop():
    # a held status's crit / defence traits are the resolver's (combat.RESOLVER_TRAITS): the record's row leaves them
    # out, so a deck troop's Sharp Insight (70148 -> 701480, M_CRITICAL_PROB ADD_TARGET_LEVEL 13 x its level) adds once
    live = status.passive_traits({70148: 1}, 21, live=True)
    kept = status.passive_traits({70148: 1}, 21, live=False)
    assert ("M_CRITICAL_PROB", 13 * 21, False) in live and not any(n == "M_CRITICAL_PROB" for n, _, _ in kept)


# --- the target's defence traits, race rates, absorption (census A17, A15, A18) ---------------------------------------

@pytest.mark.parametrize("held,kind,defence", [
    ({}, "LOOSE", 386),
    ({1004: 1}, "LOOSE", 386 * 0.7),          # Shock - Low: M_DEFENCE_PHYSICAL percent -30, "Reduces Physical Defence"
    ({9: 1}, "LOOSE", 0),                     # Shock: M_DEFENCE_PHYSICAL flat -400 (floor 0)
    ({1004: 1}, "RANGE", 386 * 0.7),          # the group stands for the ranged defence too
    ({102339: 1}, "LOOSE", 386 * 2),          # Increase Defence: +100 %
    ({1005: 1}, "LIGHTNING", 89 * 0.7),       # Poison - Low: M_DEFENCE_MAGICAL -30 % (every element)
    ({600131: 1}, "LIGHTNING", 89 * 0.8),     # Thunderbolt: Weakened: DEFENCE_MAGICAL_LIGHTNING -20 %
    ({600131: 1}, "FIRE", 89),                # ... not the fire defence
])
def test_the_targets_defence_traits_count(held, kind, defence):
    tgt = combat.combatant(6, 1, close=386, far=386, magical=dict.fromkeys(combat.ELEMENTS, 89.0))
    got = combat._stat(tgt, combat.defence_stat(kind), None, held, combat.defence(tgt, kind))
    assert max(0.0, got) == pytest.approx(defence)


def test_a_defence_debuff_raises_the_damage_by_the_formula():
    att = combat.combatant(6, 0, atk=(100, 100))
    tgt = combat.combatant(6, 1, close=3000)
    plain = combat.resolve(att, tgt, {"type": "LOOSE"}, rng=Seq())
    shocked = combat.resolve(att, tgt, {"type": "LOOSE"}, held={1004: 1}, rng=Seq())
    assert (plain, shocked) == (round(100 * 3000 / 6000), round(100 * 3000 / 5100))    # D 3000 -> 2100, Lv 6: 3000


def test_the_berserkers_berserk_halves_his_own_defence():
    # 620202 (the Madness stance's, with 6200): M_DEFENCE_PHYSICAL / _MAGICAL percent -50, LEADER
    hero = berserker()
    d = combat.defence(hero, "LOOSE")
    assert combat._stat(hero, "DEFENCE_PHYSICAL_CLOSE", None, {620202: 1}, d) == pytest.approx(d / 2)


@pytest.mark.parametrize("att_species,tgt_species,own,held,hero,factor", [
    (None, "ORCISH", {850110: 1}, {}, False, 1.12),   # Monster Hunter: "+12 %" on the Monster type (ORCISH)
    (None, "GIANT", {850110: 1}, {}, False, 1.0),     # ... not on a giant
    ("ORCISH", None, {}, {850120: 1}, False, 0.88),   # Monster Specialist on the target: "-12 %" from the Monster type
    (None, None, {}, {850190: 1}, True, 0.88),        # Hero Specialist: "-12 %" from the hero
    (None, None, {}, {850190: 1}, False, 1.0),        # ... not from a troop
    (None, "ORCISH", {1500100: 1}, {}, False, 1.08),  # Orc Hunter (Troop): flat 80, "+8 %" (@stv/10@)
])
def test_the_race_rates(att_species, tgt_species, own, held, hero, factor):
    att = combat.combatant(6, 0, species=att_species, hero=hero)
    tgt = combat.combatant(6, 1, species=tgt_species)
    assert combat.race_factor(att, tgt, own, held) == pytest.approx(factor)


def test_the_species_come_from_the_troop_types():
    # nptrooptype SpeciesId: 40001 (orc heavy infantry) ORCISH; NONE is none
    rows = combat._rows_by("nptrooptype", "System", "NPTroopType")
    assert combat._species(rows["40001"]["SpeciesId"]) == "ORCISH"
    assert combat._species(rows["40011"]["SpeciesId"]) is None


@pytest.mark.parametrize("held,level,dealt", [
    ({}, 6, 1500),
    ({703491: 1}, 6, 1000),     # Steely Stride: DAMAGE_ABSORB flat 500 (TROOP)
    ({812180: 1}, 10, 1100),    # Swift Ambush: DAMAGE_ABSORB 40 x the holder's level
])
def test_damage_absorption_takes_its_amount_off_each_hit(held, level, dealt):
    att = combat.combatant(30, 0, atk=(1500, 1500))
    tgt = combat.combatant(level, 1)
    assert combat.resolve(att, tgt, {"type": "LOOSE"}, held=held, rng=Seq()) == dealt


# --- damage and healing over time (census H13) ---------------------------------------------------------------------

def dot_room(monkeypatch):
    monkeypatch.setattr(combat, "random", Even())
    monkeypatch.setattr(status, "random", random.Random(1))
    s = room(hero_hp=100000)
    s.data["battle"].add_np(20001, 1000, 3, c=combat.combatant(6, 1))                 # the burning troop: no defence
    s.data["battle"].add_np(20002, 1000, 1, c=combat.combatant(6, 1, matk=(100, 100), atk=(40, 40)))   # the caster
    return s


def test_a_burn_ticks_every_unit_five_times_for_half_its_casters_magic_attack(monkeypatch):
    # 7 Burn level 1: "Inflicts Fire Damage equivalent to Magic Attack x 0.5 every 2 sec for 10 sec"
    s = dot_room(monkeypatch)
    status.apply(s, [20001], 7, 1, 20002)
    s.sent.clear()
    run_pending(s)
    ticks = [r for r in number_records(s) if r[0] == 20001]
    assert len(ticks) == 5 * 3 and {d for _, _, _, d in ticks} == {50} and {f for _, _, f, _ in ticks} == {0}
    assert s.data["battle"].troops[20001]["units"] == [750, 750, 750]


def test_a_bleed_uses_the_casters_physical_attack(monkeypatch):
    # 11 Bleeding level 1: "Physical Attack x 0.2 every 2 sec for 10 sec" (+ AttackTypeValue 1)
    s = dot_room(monkeypatch)
    status.apply(s, [20001], 11, 1, 20002)
    run_pending(s)
    assert s.data["battle"].troops[20001]["units"] == [1000 - 5 * 9] * 3          # 40 x 0.2 + 1 = 9 a tick


def test_the_kobold_sorcerers_poison_ticks_its_flat_value_on_the_hero(monkeypatch):
    # 102301 (nptrooptype %Combat of the kobold sorcerer 134020): NATURE flat 100 every 2 s for 10 s, rate 0
    s = dot_room(monkeypatch)
    status.apply(s, [0], 102301, 1, 20002)
    s.sent.clear()
    run_pending(s)
    d = combat.defence(s.data["battle"].troops[0]["c"], "NATURE")                    # the flat part meets his defence
    tick = round(100 * (1 - d / (d + combat.DEF_K_PER_LEVEL * 6)))                   # (the caster's level 6)
    assert 90 < tick <= 100 and [n for n, _ in hero_numbers(s)] == [tick] * 5
    assert s.data["battle"].troops[0]["hp"] == 100000 - 5 * tick


def test_a_second_application_restarts_the_ticks_and_a_removal_ends_them(monkeypatch):
    s = dot_room(monkeypatch)
    status.apply(s, [20001], 7, 1, 20002)
    status.apply(s, [20001], 7, 1, 20002)              # again: the first chain stops, the second runs its five
    run_pending(s)
    assert s.data["battle"].troops[20001]["units"] == [750, 750, 750]
    status.apply(s, [20001], 7, 1, 20002)
    status.end(s, 20001, 7)                             # removed (a cleanse, a group removal): no tick
    run_pending(s)
    assert s.data["battle"].troops[20001]["units"] == [750, 750, 750]


def test_a_burn_can_kill_and_credits_its_caster(monkeypatch):
    s = dot_room(monkeypatch)
    s.data["battle"].troops[20001]["units"] = [60, 60, 60]
    downs = []
    s.data["hit_callbacks"] = (game.send_troop_hp, lambda s_, uid: downs.append(uid))
    status.apply(s, [20001], 7, 1, 20002)
    run_pending(s)
    assert downs == [20001] and s.data["battle"].troops[20001]["units"] == [0, 0, 0]


def test_a_heal_over_time_restores_the_casters_magic_attack_share(monkeypatch):
    # 610040 Warmth : Enchanted level 1: "Recovers HP equivalent to 0.227 of Magic Attack every 3 sec for 15 sec"
    s = dot_room(monkeypatch)
    s.data["battle"].troops[20001]["units"] = [500, 500, 500]
    status.apply(s, [20001], 610040, 1, 20002)
    run_pending(s)
    assert s.data["battle"].troops[20001]["units"] == [500 + 5 * 23] * 3             # round(100 x 0.227) a tick


# --- NP blows that put a status (census D10) ------------------------------------------------------------------------

def test_the_kobold_sorcerers_bolt_poisons_what_it_hits(monkeypatch):
    # nptrooptype 1241 (134020, Grey Rock's Mountain Kobold Sorcerer) %Combat: StatusEffectAddActionEnum_1 SKILL_SKILL_101
    # (its ATTACK1), StatusEffectId_1 102301 level 1, Probability 1000
    monkeypatch.setattr(combat, "random", Even())
    sorcerer = combat.np_combatant(134020)
    assert sorcerer["onhit"]["SKILL_SKILL_101"] == [(102301, 1, 1000.0)]
    s = room(hero_hp=100000)
    s.data["battle"].add_np(20001, 400, 1, c=sorcerer)
    action = combat._action_names().index("SKILL_SKILL_101")
    combat.apply_hits(s, [(0, [combat.LEADER])], game.send_troop_hp, attacker=20001,
                      attack=combat.hit_attack(sorcerer, action), record=sorcerer)
    assert s.data["statuses"][0][102301]["caster"] == 20001
    run_pending(s)                                      # then it ticks: five times its 100 flat
    assert len(hero_numbers(s)) == 1 + 5


def test_a_blow_of_another_action_puts_nothing():
    sorcerer = combat.np_combatant(134020)
    s = room(hero_hp=100000)
    s.data["battle"].add_np(20001, 400, 1, c=sorcerer)
    action = combat._action_names().index("ATTACK_NORMAL_COMMON_4")
    combat.apply_hits(s, [(0, [combat.LEADER])], game.send_troop_hp, attacker=20001,
                      attack=combat.hit_attack(sorcerer, action), record=sorcerer)
    assert 102301 not in (s.data.get("statuses") or {}).get(0, {})


# --- abilities that cost HP (census F12) -----------------------------------------------------------------------------

@pytest.mark.parametrize("ability,units_after", [
    (60019, [800, 800, 1]),     # Stimulant 1: HP "20%" of each unit's max (a unit at 1 hp pays nothing)
    (70153, [600, 600, 1]),     # Blood Thrall: "40%"
    (81027, [950, 950, 1]),     # Blood Contract: "5%"
    (60020, [1000, 1000, 1]),   # a skill with no HP cost
])
@pytest.mark.parametrize("manual", [False, True])
def test_a_troop_skill_that_sacrifices_hp_takes_its_share(ability, units_after, manual):
    s = room()
    s.data["battle"].add_np(20001, 1000, 3, c=combat.combatant(6, 1))
    s.data["battle"].troops[20001]["units"][2] = 1
    if manual:
        body = (obf.u32(ability) + bytes(10) + obf.u16(20001) + struct.pack("<H", 20001)
                + bytes(7) + obf.u16(0) + bytes(3))
        combat.on_use_ability(s, pkt(combat.C2S_USE_ABILITY, body))
    else:
        body = obf.u16(20001) + struct.pack("<H", 20001) + obf.u32(ability) + bytes(7)
        combat.on_troop_cast(s, pkt(combat.C2S_TROOP_CAST, body))
    assert s.data["battle"].troops[20001]["units"] == units_after


def test_a_flat_hp_cost_takes_that_many():
    s = room()
    s.data["battle"].add_np(20001, 20000, 1, c=combat.combatant(6, 1))
    assert combat.pay_hp(s, 20001, 80020) == 13000                  # the tower's 타워_체력감소: HP 13000
    assert s.data["battle"].troops[20001]["units"] == [7000]


# --- the server-run status functions (census H14) ---------------------------------------------------------------------

def fn_room(monkeypatch):
    monkeypatch.setattr(combat, "random", Even())
    s = room(hero_hp=10000)
    s.data["battle"].add_np(20001, 1000, 3, c=combat.combatant(6, 1, atk=(300, 300)))
    return s


def blow(s, attacker, target, units, dmg=300):
    combat.apply_hits(s, [(target, units)], game.send_troop_hp, attacker=attacker, attack={"type": "LOOSE"},
                      record=combat.combatant(6, 1, atk=(dmg, dmg)))


def test_an_immortal_troop_stops_at_one_hp(monkeypatch):
    # 600391 Last-ditch Effort : Enchanted: IMMORTAL, "HP doesn't drop below 1 for n sec"
    s = fn_room(monkeypatch)
    status.apply(s, [20001], 600391, 1, 20001)
    s.data["battle"].troops[20001]["units"] = [100, 100, 100]
    blow(s, None, 20001, [0, 1, 2])
    assert s.data["battle"].troops[20001]["units"] == [1, 1, 1]
    s.data["battle"].troops[0]["hp"] = 50
    status.apply(s, [0], 600391, 1, 0)
    blow(s, 20001, 0, [combat.LEADER])
    assert s.data["battle"].troops[0]["hp"] == 1


def test_a_shield_takes_the_damage_until_its_pool_or_its_attacks_run_out(monkeypatch):
    # 6090 Dark Ward level 1 ["20", "10", "10%"]: a pool of 10 % of the max hp, gone after 10 attacks
    s = fn_room(monkeypatch)
    status.apply(s, [0], 6090, 1, 0)
    assert s.data["statuses"][0][6090]["shield"] == [1000.0, 10]
    blow(s, 20001, 0, [combat.LEADER], dmg=300)             # 300 a blow (no defence on the hero? his kit's is small)
    first = 10000 - s.data["battle"].troops[0]["hp"]
    assert first == 0 and s.data["statuses"][0][6090]["shield"][1] == 9
    for _ in range(4):
        blow(s, 20001, 0, [combat.LEADER], dmg=300)
    assert 6090 not in s.data["statuses"][0] and s.data["battle"].troops[0]["hp"] < 10000     # spent: the rest lands
    ends = [struct.unpack_from("<I", bytes(w.buf), 6)[0] for w in s.sent if w.proto == combat.S2C_STATUS_END]
    assert 6090 in ends


def test_a_reflection_sends_its_share_back_as_its_type(monkeypatch):
    # 6210 Rage level 1: REFLECT_DAMAGE ["FIRE", "30%", "1000"], "Reflects 30% of the damage as Fire Damage"
    s = fn_room(monkeypatch)
    status.apply(s, [0], 6210, 1, 0)
    before = sum(s.data["battle"].troops[20001]["units"])
    blow(s, 20001, 0, [combat.LEADER])
    took = 10000 - s.data["battle"].troops[0]["hp"]
    assert took > 0 and before - sum(s.data["battle"].troops[20001]["units"]) == round(took * 0.3)


def test_vampirism_heals_its_holder_by_its_share_of_what_it_dealt(monkeypatch):
    # 16 Vampirism level 1: BLOODSUCK ["30%", "1000", "5%", ...]: 30 % of the damage, at most 5 % of the max hp
    s = fn_room(monkeypatch)
    s.data["battle"].troops[20001]["units"] = [500, 500, 500]
    status.apply(s, [20001], 16, 1, 20001)
    blow(s, 20001, 0, [combat.LEADER], dmg=300)
    dealt = 10000 - s.data["battle"].troops[0]["hp"]
    healed = sum(s.data["battle"].troops[20001]["units"]) - 1500
    assert dealt > 0 and healed == 3 * min(round(dealt * 0.3), 150)             # each living unit, cap 3,000 x 5 %


def test_a_hit_status_goes_on_what_its_holder_strikes(monkeypatch):
    # 700000 Powerful Strike : Enchanted: HIT_ADD_STATUSEFFECT ["700012", "-", "-", "1000"]
    s = fn_room(monkeypatch)
    status.apply(s, [20001], 700000, 1, 20001)
    blow(s, 20001, 0, [combat.LEADER])
    assert 700012 in s.data["statuses"][0]


def test_a_stunned_troops_blows_land_nothing_but_its_skills_do(monkeypatch):
    # 3 COMMON_STUN: TROOP_NOATTACK_DPS (and %Forbidden Controllability); the revive's 33 / 34 and the escape's 6321 too
    s = fn_room(monkeypatch)
    status.apply(s, [20001], 3, 1, 0)
    blow(s, 20001, 0, [combat.LEADER])
    assert s.data["battle"].troops[0]["hp"] == 10000
    combat.apply_hits(s, [(0, [combat.LEADER])], game.send_troop_hp, attacker=20001,
                      attack={"type": "LOOSE", "ability": 1, "ar": 1.0}, record=combat.combatant(6, 1, atk=(300, 300)))
    assert s.data["battle"].troops[0]["hp"] < 10000


def test_healing_received_and_regeneration_are_cut_by_their_statuses(monkeypatch):
    # 1028 Demoralised: DEATHBLOW "40%" ("Reduces Received Healing Effect -40%"); 1009 Burn - Medium: HP_REGEN_REDUCE 60%
    s = fn_room(monkeypatch)
    s.data["battle"].troops[20001]["units"] = [100, 100, 100]
    status.apply(s, [20001], 1028, 1, 0)
    assert combat.heal_share(s, 20001) == pytest.approx(0.6)
    combat.apply_heals(s, [(20001, [0])], {"ar": 0.0, "flat": 100}, combat.combatant(6, 0), None, game.send_troop_hp)
    assert s.data["battle"].troops[20001]["units"][0] == 160
    status.apply(s, [0], 1009, 1, 20001)
    assert combat.regen_share(s, 0) == pytest.approx(0.4)


# --- the damage chains and conditional adds (census H12) ------------------------------------------------------------

def test_a_bleed_chain_steps_on_the_struck_enemy_with_every_execute(monkeypatch):
    # abilitytypeinfo 54 (the Gunslinger's low shot): STATUSEFFECT_CHAIN ["3", "1000", ...]: chain 3 6453 -> 6454 -> 6455
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["zone_troops"] = {20001: {"TeamNum": 1}}
    s.data["battle"].add_np(20001, 1000, 3, c=combat.combatant(6, 1))
    for want in (6453, 6454, 6455):
        combat.execute_chains(s, 0, 54, [(20001, [0])])
        assert want in s.data["statuses"][20001]
    assert 6453 not in s.data["statuses"][20001] and 6454 not in s.data["statuses"][20001]


def test_a_conditional_add_needs_its_status_on_the_target(monkeypatch):
    # 628 Meteor level 1: STATUSEFFECT_ADD_STATUSEFFECT ["LIVE_ENEMY", "6319", "LIVE_ENEMY", "6391", "1"]
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["zone_troops"] = {20001: {"TeamNum": 1}, 20002: {"TeamNum": 1}}
    s.data["battle"].add_np(20001, 1000, 1, c=combat.combatant(6, 1))
    s.data["battle"].add_np(20002, 1000, 1, c=combat.combatant(6, 1))
    status.apply(s, [20001], 6319, 1, 0)
    combat.execute_chains(s, 0, 628, [(20001, [0]), (20002, [0])])
    assert 6391 in s.data["statuses"][20001] and 6391 not in (s.data["statuses"].get(20002) or {})


# --- a status's own stack count (census H5) ---------------------------------------------------------------------------

def test_a_stackable_status_stacks_to_its_count_and_counts_once_a_stack(monkeypatch):
    # 1028 Demoralised (the raid's MDP penalty): %Basic Count 3, its ATTACK_PHYSICAL cut once a stack
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["battle"].add_np(20001, 1000, 1, c=combat.combatant(6, 1))
    for n in (1, 2, 3, 3):
        status.apply(s, [20001], 1028, 1, 0)
        assert s.data["statuses"][20001][1028]["stacks"] == n
    held = combat.held_levels(s, 20001)
    one = combat.status_bonus({1028: 1}, "ATTACK_PHYSICAL")
    assert one[0] < 0 and combat.status_bonus(held, "ATTACK_PHYSICAL") == (3 * one[0], 0.0)
    status.apply(s, [20001], 7, 1, 0)                   # Burn: Count 1, a second application refreshes, no stack
    status.apply(s, [20001], 7, 1, 0)
    assert s.data["statuses"][20001][7]["stacks"] == 1


def test_a_stacked_fire_twister_ticks_once_a_stack(monkeypatch):
    # 6293 Fire Twister (the Berserker's ABILITY_DARKNESS_DOT): Count 5
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["battle"].add_np(20001, 100000, 1, c=combat.combatant(6, 1))
    s.data["battle"].add_np(20002, 1000, 1, c=combat.combatant(6, 1, matk=(1000, 1000)))
    status.apply(s, [20001], 6293, 1, 20002)
    run_pending(s)
    one = 100000 - s.data["battle"].troops[20001]["units"][0]
    status.apply(s, [20001], 6293, 1, 20002)
    status.apply(s, [20001], 6293, 1, 20002)
    run_pending(s)
    assert one > 0 and 100000 - s.data["battle"].troops[20001]["units"][0] == pytest.approx(one * 3, abs=10)


# --- the kill counter (census I9) -----------------------------------------------------------------------------------

def kill_counts(s):
    return [struct.unpack_from("<IB", bytes(w.buf)) for w in s.sent if w.proto == combat.S2C_KILL_COUNT]


def test_the_heros_kills_count_up_and_start_again_after_twenty_seconds(monkeypatch):
    # herotable %ActionCount: KILL, MaxCount 99, InitializationTime 20; 0x50b9 (i32 count, u8 style)
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["battle"].add_np(20001, 10, 5, c=combat.combatant(6, 1))
    combat.apply_hits(s, [(20001, [0, 1, 2])], game.send_troop_hp, attacker=0, attack={"type": "HERO", "flat": 100},
                      record=combat.combatant(6, 0))
    assert kill_counts(s) == [(3, 0)]
    assert combat.kill_count(s, 1, now=s.data["kill_streak"][1] + 5) == 4
    assert combat.kill_count(s, 1, now=s.data["kill_streak"][1] + 21) == 1           # 20 s quiet: again from 1
    s.data["kill_streak"] = (98, s.data["kill_streak"][1])
    assert combat.kill_count(s, 5, now=s.data["kill_streak"][1] + 1) == 99            # MaxCount
    s.sent.clear()
    combat.apply_hits(s, [(20001, [3])], game.send_troop_hp, attacker=20002, attack={"type": "HERO", "flat": 100},
                      record=combat.combatant(6, 0))
    assert kill_counts(s) == []                                                       # not the hero's kill


# --- skill-group damage rates, unit-count and Stack2 damage (census A16, A8) -----------------------------------------

def test_a_skill_groups_rate_from_the_casters_gear_raises_that_groups_skills():
    # item_set 11021 (3 pieces): ABILITY_ADD_DAMAGE_RATE_03 +800; a skill tagged ABILITY_ADD_DAMAGE_RATE_03 1000
    att = combat.combatant(6, 0, rates={"ABILITY_ADD_DAMAGE_RATE_03": 800.0})
    tagged = {"groups": [("ABILITY_ADD_DAMAGE_RATE_03", 1000.0)]}
    other = {"groups": [("ABILITY_ADD_DAMAGE_RATE_07", 1000.0)]}
    assert combat.skill_rate_factor(att, tagged) == pytest.approx(1.8)
    assert combat.skill_rate_factor(att, other) == 1.0
    assert combat.skill_rate_factor(att, {}) == 1.0


def test_the_skill_groups_come_from_the_ability_rows():
    rows = [r for r in combat._improvements().values() for r in r.values()
            if r.get("Add_attributeType1") == "ABILITY_ADD_DAMAGE_RATE_01"]
    ability = int(rows[0]["AbilityId"])
    attack = combat.ability_attack(combat.combatant(6, 0), ability, int(rows[0]["Level"]))
    assert ("ABILITY_ADD_DAMAGE_RATE_01", 1000.0) in attack["groups"]


@pytest.mark.parametrize("ability,struck,factor", [
    (10650, 1, 1.0), (10650, 2, 0.5), (10650, 6, 0.02), (10650, 9, 0.02),   # the Behemoth's explosion, shared
    (35020, 1, 1.001), (35020, 3, 1.3),                                        # Pergos's fireball, growing
])
def test_a_unit_count_skill_scales_with_the_units_it_strikes(ability, struck, factor):
    assert combat.ability_modifiers(ability, 1, combat.combatant(20, 1), struck=struck) == pytest.approx(factor)


def test_a_spirit_command_adds_its_share_a_stack2():
    assert combat.ability_modifiers(1309, 1, combat.combatant(20, 1), stack2=2) == pytest.approx(3.0)
    assert combat.ability_modifiers(1312, 1, combat.combatant(20, 1), stack2=2) == pytest.approx(1.0)


# --- NP HP regeneration (census M2) -------------------------------------------------------------------------------------

def test_a_regenerating_troop_heals_its_hp_recovery_a_beat_until_full(monkeypatch):
    # nptrooptable 2 HUMAN_INFANTRY_FGT_N_LV1_1: HP_RECOVERY 6 -> 6 a unit every 3 s (TROOPS T1.14: the tape's deck troop
    # gains its HP_RECOVERY a unit a beat, not x 3)
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    rec = combat.np_combatant(2)
    assert rec["hp_rec"] == 6
    s.data["battle"].add_np(20001, 1072, 2, c=rec)
    combat.apply_hits(s, [(20001, [0])], game.send_troop_hp, attacker=None, attack={"type": "HERO", "flat": 50},
                      record=combat.combatant(6, 0))
    hurt = s.data["battle"].troops[20001]["units"][0]
    assert hurt < 1072
    s.pending.sort(key=lambda p: p[0])
    s.pending.pop(0)[1]()                               # one tick
    assert s.data["battle"].troops[20001]["units"][0] == min(1072, hurt + 6)
    run_pending(s)
    assert s.data["battle"].troops[20001]["units"] == [1072, 1072]


# --- the client's hit kinds: guard, counter, dodge (census D5, D6, D8); NP hit resist (D2); whole troops (E6) ---------

def kind_record(unit, kind):
    """A 6-byte hit record: +4 / +5 bit 0 unit + 3, +5 bits 2-3 kind & 3, bit 1 kind bit 2 (builder 0x140544710)."""
    code = unit + 3
    return bytes([0, 0, 0, 0, code & 0xff, (code >> 8) | ((kind & 3) << 2) | (((kind >> 2) & 1) << 1)])


@pytest.mark.parametrize("kind,flag,share", [
    (0, 0, 1.0), (1, combat.FLAG_GUARD, 0.3), (2, combat.FLAG_GUARD, 0.3), (3, combat.FLAG_GUARD, 0.3),
    (4, 0, 1.0), (6, combat.FLAG_DODGE, 0.0),
])
def test_each_hit_kind_takes_its_share_and_word(monkeypatch, kind, flag, share):
    # an NP unit (GUARD_REDUCE 700, no guard status): a guard (1), a guard and counter (2), DEFENSE_STANDING (3) take
    # three tenths with "Defence"; a dodge (6) nothing, with "Evasion" (the client's rolls: Unit::EvaluateGuard /
    # EvaluateDodge; client digs 2026-10-01)
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["battle"].add_np(20001, 10000, 2, c=combat.combatant(6, 1, guard=700))
    assert combat.hit_kind(kind_record(1, kind)) == kind
    combat.apply_hits(s, [(20001, [1])], game.send_troop_hp, attacker=None, attack={"type": "LOOSE", "flat": 1000},
                      record=combat.combatant(6, 0), kinds=[[kind]])
    assert number_records(s) == [(20001, 1, flag, round(1000 * share))]


def test_np_troops_carry_their_hit_resist_in_the_stat_block():
    # nptrooptype %Combat HITRESIST -> stat 40 of the troop's entries (the troll 134080's type 60, the sorcerer 30, the
    # kobold infantry 0: none); its leader's npleadertype HITRESIST in the leader's
    troll = combat._rows_by("nptrooptable", "Contents", "NPTROOP_ID")["134080"]
    assert game.np_stat_block(troll) == ({40: 60}, {})
    assert game.np_stat_block(combat._rows_by("nptrooptable", "Contents", "NPTROOP_ID")["134030"]) == ({}, {})
    lead = game.np_leader(134010)
    troop, leader = game.np_stat_block(troll, lead)
    assert leader == {40: int(combat._f(combat._rows_by("npleadertype", "Combat", "NPLeaderType")[
        lead["NPLeaderType"]]["HITRESIST"]))}
    block = game.encode_stats(leader, troop)
    assert block[0] == 1 and block[1:3] == game.encode_stat(40, 60)            # u8 troop count, the troop's entries


def test_a_whole_troop_record_strikes_every_living_unit_and_the_leader_by_its_share(monkeypatch):
    # a 0x5066 target record with flag 255 (AffectType TROOP): no unit list; the client hits every living unit and the
    # leader (0x140820200)
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["battle"].add_np(20001, 1000, 3, c=combat.combatant(6, 1), leader_hp=1000,
                            leader_c=combat.combatant(6, 1, leader=True))
    s.data["battle"].troops[20001]["units"][2] = 0
    body = bytes(7) + struct.pack("<H", 5) + struct.pack("<H", 1) + bytes([255]) + struct.pack("<H", 20001) + b"\0"
    targets = combat.ability_targets(body, 9)
    assert targets == [(20001, [0])] and targets[0][1].share == 1.0
    combat.apply_ability(s, 0, None, 1, targets, game.send_troop_hp)
    t = s.data["battle"].troops[20001]
    assert t["units"][0] < 1000 and t["units"][1] < 1000 and t["leader"] < 1000


# --- ability HP traits and reinforcement (census F6, F14) ---------------------------------------------------------------

def test_supplement_heals_its_ally_a_share_of_max_and_brings_back_fallen_members(monkeypatch):
    # 5012 Supplement (the Berserker's tactic): ALLY HP_BASEUNIT ADD 15% ("Restores target ally Troops by 15% of Max
    # HP"), REINFORCE_TROOP "30, 0, 100, 1" ("Replaces some fallen Troop Members")
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["battle"].add_np(10001, 1000, 10, c=combat.combatant(6, 0))                 # the player's side (team 0)
    t = s.data["battle"].troops[10001]
    t["units"] = [500] * 6 + [0] * 4
    combat.apply_ability(s, 0, 5012, 1, [(10001, combat.WholeTroop(255))], game.send_troop_hp)
    assert t["units"][:6] == [650] * 6                                                  # + 150 each
    assert t["units"][6:] == [1000, 1000, 0, 0]                                         # ceil(4 x 30 %) = 2 back, full
    lives = [bytes(w.buf) for w in s.sent if w.proto == combat.S2C_UNIT_LIVE]
    assert lives and struct.unpack_from("<HH", lives[-1])[1] == 2


def test_a_fixed_damage_trait_ignores_the_defence():
    # 60036: ENEMY HP_BASEUNIT SUBTRACT 5000 ("Inflicts 5000 damage on a selected enemy. Ignores its Defence")
    s = room()
    s.data["battle"].add_np(20001, 100000, 1, c=combat.combatant(6, 1, close=99999))
    combat.apply_ability(s, 0, 60036, 1, [(20001, [0])], game.send_troop_hp)
    assert s.data["battle"].troops[20001]["units"] == [100000 - 5000]


def test_a_commanders_fall_leaves_his_force_to_his_troops_own_300127(monkeypatch):
    # TROOPS T8.7 (the troop hunt, 2026-10-01): ability 10202 NPT_LEADER_DEATH ("Penalty If Commander Dies") is on no
    # nptrooptable / npleadertable list, so nothing casts it; the leader-death weakening is the troops' own 300127
    # (DEATH_SELF_LEADER, the client's AI: tests/test_troop_hunt.py). The force keeps its hp and gets no 10202
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    s.data["zone_troops"] = {20001: {"TroopTableID": 134030, "TeamNum": 1, "ForceNum": 7, "NPLeaderID": 134010},
                             20002: {"TroopTableID": 134030, "TeamNum": 1, "ForceNum": 7, "NPLeaderID": -100}}
    s.data["battle"].add_np(20001, 1000, 1, c=combat.combatant(6, 1))
    s.data["battle"].add_np(20002, 1000, 3, c=combat.combatant(6, 1))
    status.commander_down(s, 20001, s.data["zone_troops"][20001], credited=False)
    assert 10202 not in s.data.get("statuses", {}).get(20002, {})
    assert s.data["battle"].troops[20002]["units"] == [1000, 1000, 1000]


# --- vitality (census I5) ---------------------------------------------------------------------------------------------

def stamina_pushes(s):
    out = []
    for w in s.sent:
        if w.proto == combat.S2C_STAMINA:
            b = bytes(w.buf)
            out.append(struct.unpack_from("<BHHhI", b))
    return out


def commander_room(monkeypatch):
    # Grey Rock's kobold commander: npleadertable 134030 (STAMINA_MAX 41, KDOWN 3000208 level 5, HP 1028) over a troop
    monkeypatch.setattr(combat, "random", Even())
    s = room()
    lead = combat.combatant_leader(combat._rows_by("npleadertable", "Contents", "NPLEADER_ID")["134030"])
    s.data["battle"].add_np(20001, 171, 5, c=combat.np_combatant(134030), leader_hp=1028, leader_c=lead)
    return s


@pytest.mark.parametrize("ability,dealt,left", [
    (633, 31, 31),          # Dark Impact (GROGGY_RATE 50, Add_StaminaProb 2000): 62 -> the cap 10 (41 x 50 / 200)
    (633, 200, 31),         # ... whatever the damage (the tape: 10 a press for 7-200 damage)
    (608, 61, 35),          # Charging Slash (50, 100): 61 x 0.1 = 6 (the tape: 41 -> 35 for its "61")
    (710, 37, 39),          # Capture (10, 100): 3.7 -> the cap 2 (41 x 10 / 200; the tape: 27 -> 25)
    (803, 500, 41),         # a combo hit (0, 0): nothing ("Only skills consume Vitality")
])
def test_a_skill_drains_the_commanders_vitality_as_the_tape_shows(monkeypatch, ability, dealt, left):
    s = commander_room(monkeypatch)
    combat.drain_vitality(s, 20001, ability, 1, dealt)
    assert s.data["battle"].troops[20001]["vit"]["cur"] == left
    if left < 41:
        assert stamina_pushes(s)[-1] == (1, 20001, 1, -1, left)          # the leader unit (-1)


def test_at_zero_vitality_the_commander_is_exhausted_and_the_bar_refills_after(monkeypatch):
    s = commander_room(monkeypatch)
    for _ in range(4):
        combat.drain_vitality(s, 20001, 633, 1, 100)
    assert s.data["battle"].troops[20001]["vit"]["cur"] == 1                # four capped steps leave a sliver (the tape)
    combat.drain_vitality(s, 20001, 633, 1, 100)
    assert s.data["battle"].troops[20001]["vit"]["cur"] == 0
    assert s.data["statuses"][20001][3000208]["level"] == 5                 # STAMINA_OUT_STUN, 3 s + 5
    run_pending(s)
    assert s.data["battle"].troops[20001]["vit"]["cur"] == 41 and stamina_pushes(s)[-1][-1] == 41


def test_a_damaging_skill_execute_drains_and_the_spawn_shows_a_full_bar(monkeypatch):
    s = commander_room(monkeypatch)
    s.data["kit"] = {633: 1}
    combat.apply_ability(s, 0, 633, 1, [(20001, [combat.LEADER])], game.send_troop_hp)
    assert s.data["battle"].troops[20001]["vit"]["cur"] == 31
    troll = combat.np_combatant(134080)
    s.data["battle"].add_np(20002, 10232, 1, c=troll)
    combat.send_stamina(s, 20002)
    assert stamina_pushes(s)[-1] == (1, 20002, 1, 0, 3274)                   # the troll's own, unit 0


# --- which execute puts a cast's statuses (census F3, H2) ----------------------------------------------------------------

def test_a_casts_statuses_go_on_at_the_executes_its_process_list_marks(monkeypatch):
    # 106 (the Gunslinger's): ProcessRate "15 15 15 70 15", ProcessStatusEffect "0 0 0 1 0": its status 55 on the fourth
    monkeypatch.setattr(status, "random", random.Random(3))
    s = room()
    s.data["kit"] = {106: 1}
    s.data["zone_troops"] = {20001: {"TeamNum": 1, "TroopTableID": 134030}}
    s.data["battle"].add_np(20001, 100000, 1, c=combat.combatant(6, 1))
    row = status.cast_row(106, 1)
    sid, obj = int(row["StatusEffect1"]), row["StatusEffectObject1"]
    who = 0 if obj in ("SELF", "ALLY") else 20001
    for k in range(1, 6):
        status.on_execute(s, 77, 106, 0, [(20001, [0])])
        held = sid in (s.data.get("statuses") or {}).get(who, {})
        assert held == (k >= 4), k
    assert [status.process_flag({"ProcessStatusEffect": v}, k) for v, k in
            (("1 1 1", 2), ("0 1", 0), ("0 1", 1), ("0", 0), ("-", 3), ("1 1", 5))] == [True, False, True, False,
                                                                                      True, True]


# --- the hero's regeneration shows its number (census M1) ----------------------------------------------------------------

def test_the_heros_regeneration_tick_shows_a_green_number_every_three_seconds():
    # the tape (part 2 Grey Rock 38:42 / 38:45 / 38:48, mid-fight): "+24" in green over the hero every 3 s; the hero
    # number reader 0x140c54aa0 shows a negative amount as TextNumMgr type 10 (HealingText)
    s = room(hero_hp=1000)
    s.data["battle"].troops[0]["hp"] = 500
    s.data["battle"].troops[0]["combat"] = True         # mid-fight: the tick itself (x5 out of combat, census HERO P7)
    s.data["pools"] = {"sp": 100, "sp_max": 100, "sp_rec": 0, "hp_rec": 24}   # hero.regen_tick: the tick, not a rate
    combat.start_regen(s)
    assert s.pending[0][0] == combat.SP_TICK_S == 3.0
    s.pending.pop(0)[1]()
    assert s.data["battle"].troops[0]["hp"] == 524
    assert hero_numbers(s)[-1] == (-24, 0)


def test_every_troop_types_hit_resist_is_its_combat_rows():
    # nptrooptype / npleadertype / trooptype %Combat HITRESIST: the stat 40 of the stat block (a deck troop's too)
    for table, key in (("nptrooptype", "NPTroopType"), ("npleadertype", "NPLeaderType"), ("trooptype", "TroopType")):
        rows = combat._rows_by(table, "Combat", key)
        some = next(r for r in rows.values() if combat._f(r.get("HITRESIST")) > 0)
        assert game.hit_resist(table, some[key]) == int(combat._f(some["HITRESIST"])) > 0
    assert game.hit_resist("nptrooptype", "1288") == 60                  # the Grey Rock troll's type

"""Every NP troop's table skills (owner 2026-09-30 ~16:15: "do the most close the vanilla as possible"). A 0x50cb troop
holds only the abilities its entry's two lists name (MakeTroopGenInfoForBuild 0x140cf7080: list 1 slots 0.. by place,
list 2 slots 0x10 + place; the client never reads nptrooptable %Skill for it), and its AI (defaulttroop_ai.tai: every NP
program calls Act_TroopAi_RunAutoSkill / RunAutoSkill2 first) casts from them. So each zone troop, enemy or ally, comes
with its row's ACTIVESKILLnn in list 1 (packed, column order) and PASSIVESKILLnn in list 2; its casts arrive as C2S
0x505f with an NP caster, answered and applied as the hero's are (0x5060, 0x5065, 0x5067, the resolver's damage).
No capture holds an NP 0x505f (all 5 were the hero's), so the bodies here follow the builders (0x1404f9420: coded u16
target, u16 caster, coded u32 ability, packed position; 0x5066 0x1404faf10: position, u16 serial, target list, props).
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import combat, game, net, obf, timeline
from test_army import pkt
from conftest import run_pending
from test_battle import Even, NoSave, hero_record, mission_room


def cell_lists(s):
    """{uid: ([(level, ability)] list 1, [(level, ability)] list 2)} of every 0x50cb entry sent."""
    out = {}
    for w in s.sent:
        if w.proto != game.S2C_ENTER_CELL_TROOP:
            continue
        b = bytes(w.buf)
        st = b[3:3 + 0x3d]
        i = 3 + 0x3d
        i += 1 + (22 if obf.T1[b[i]] & 1 else 0)
        lists = []
        for _ in range(2):
            n = struct.unpack_from("<H", b, i)[0]
            lists.append([struct.unpack_from("<BI", b, i + 2 + 5 * k) for k in range(n)])
            i += 2 + 5 * n
        out[struct.unpack_from("<H", st, 0x11)[0]] = tuple(lists)
    return out


def cast(role, s, caster, ability, target, pos=bytes(7)):
    """A troop's 0x505f as the builder 0x1404f9420 writes it; returns the serial of its 0x5060."""
    body = obf.u16(target) + struct.pack("<H", caster) + obf.u32(ability) + pos
    role.handlers[combat.C2S_TROOP_CAST](s, pkt(combat.C2S_TROOP_CAST, body))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == combat.S2C_TROOP_CAST and len(out) == 17
    assert out[0:2] == obf.u16(target) and out[2:6] == obf.u32(ability) and out[6:13] == pos
    assert struct.unpack_from("<H", out, 0xf)[0] == caster
    return struct.unpack_from("<H", out, 0xd)[0]


def execute(role, s, serial, targets):
    """One 0x5066 of a cast: [(uid, [unit index])]; an empty unit list names the whole troop."""
    lst = struct.pack("<H", len(targets))
    for uid, units in targets:
        if units:
            lst += bytes([0]) + struct.pack("<HH", uid, len(units)) + b"".join(struct.pack("<H", u << 5) for u in units)
        else:
            lst += bytes([255]) + struct.pack("<H", uid)      # the whole troop (AffectType TROOP: 255)
    role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE,
                                                     bytes(7) + struct.pack("<H", serial) + lst + bytes([0])))


def echoes(s, proto):
    return [bytes(w.buf) for w in s.sent if w.proto == proto]


@pytest.fixture(scope="module")
def grey_rock():
    """Grey Rock 10234 at its start, then the sorcerer 20081, the kobold archers 20164, the troll 20082, the other
    fire archers 10067 (Glen's force) and the kobold commander's troop 20155 brought in; the player's side has a hero
    record."""
    s = mission_room(10234)
    run_pending(s)
    game.spawn_troops(s, [20081, 20164, 20082, 10067, 20155])
    s.data["battle"].troops[0]["c"] = hero_record(level=10)
    return s


def test_every_zone_troop_comes_with_its_table_skills(grey_rock):
    lists = cell_lists(grey_rock)
    assert lists[10073] == ([(1, 500045)], [])                   # the handed fire archers (134060), as before
    assert lists[10067] == ([(1, 500045)], [])                   # the same row in Glen's force: now too
    assert lists[10072] == ([(1, 81001)], [])                    # Glen's infantry 134070: Shield Use I
    assert lists[20081] == ([(1, 500043)], [(5, 42002), (5, 42008)])   # the kobold sorcerer: the poison floor
    assert lists[20164] == ([(1, 500044)], [])                   # the kobold archers: the poison arrows
    assert lists[20082] == ([], [(5, 42002), (5, 42008)])        # the Mountain Troll: its two immunities only
    assert lists[20000] == ([], [])                              # a kobold infantry row with no skill
    # an NP leader has no ability manager of its own (BuildNPLeader_New 0x140f6c260 fills only its stats): its
    # npleadertable %Skill goes in its troop's lists after the troop's own, and a LEADER-subject cast needs him alive
    # (the client's check). Glen 134010 on 10000 (134120: 81001): 200137 and his three passives
    assert lists[10000] == ([(1, 81001), (1, 200137)], [(5, 42102), (5, 42108), (5, 42026)])
    assert lists[20155] == ([(2, 300110)], [(5, 42102), (5, 42108)])   # the kobold commander 134040 on 134030
    s = mission_room(10233)                                      # Tower of Moonlight
    run_pending(s)
    game.spawn_troops(s, [30000])
    lists = cell_lists(s)
    assert lists[11004] == ([(8, 200147)], [])                   # Glen's CPU archers 133140: rapid fire (column 8)
    assert lists[20001] == ([(1, 300127)], [])                   # an Encablossian: the leader-buff removal
    assert lists[10100] == ([], [(5, 42002), (5, 42008)])        # the handed infantry 133270: passives only
    assert lists[30000] == ([], [(5, 42002), (5, 42008)])        # a winged wyrm: no active in its row


def test_an_enemy_cast_answers_and_hits_the_players_troop_and_hero(grey_rock, monkeypatch):
    # the kobold archers 20164 (134040: ATTACK_MAGICAL 5, level 6) cast their poison arrows 500044 (AttributeRate 4000,
    # NATURE) on the handed archers 10073 and the hero: 0x5060, the commit 0x5065 and the execute 0x5067 carry the
    # caster, and each unit hit is the resolver's (candidate A) with the ability's attack
    monkeypatch.setattr(combat, "random", Even())
    s, role = grey_rock, game.make(NoSave(), 0)
    b = s.data["battle"]
    serial = cast(role, s, 20164, 500044, 10073)
    commit = (bytes([9]) + struct.pack("<HI", 0, 500044) + bytes(7) + struct.pack("<H", serial) + obf.u16(10073)
              + bytes([0]))
    role.handlers[combat.C2S_COMMIT](s, pkt(combat.C2S_COMMIT, commit))
    assert s.sent[-1].proto == combat.S2C_COMMIT and struct.unpack_from("<H", bytes(s.sent[-1].buf), 0xc)[0] == 20164
    archers, hero = b.troops[10073], b.troops[0]
    before, hero_before = list(archers["units"]), hero["hp"]
    execute(role, s, serial, [(10073, [0, 1]), (0, [])])
    reply = echoes(s, combat.S2C_ABILITY_EXECUTE)[-1]
    assert struct.unpack_from("<H", reply, 0)[0] == serial and struct.unpack_from("<H", reply, 3)[0] == 20164
    kobold = combat.np_combatant(134040, 1)
    attack = combat.ability_attack(kobold, 500044, 1, 1)
    assert attack["type"] == "NATURE" and attack["ar"] == 4.0
    one = combat.resolve(kobold, archers["c"], attack)
    assert one > 0 and archers["units"][:2] == [before[0] - one, before[1] - one] and archers["units"][2:] == before[2:]
    assert hero["hp"] == hero_before - combat.resolve(kobold, hero["c"], attack)
    assert combat.S2C_HERO_DAMAGE in [w.proto for w in s.sent]  # the number over the hero


def test_an_allys_cast_hits_the_enemy_and_never_its_own_side(grey_rock, monkeypatch):
    # Glen's fire archers 10067 (134060, team 0) cast 500045 (FIRE) on the kobolds 20000; a friend in the list
    # (Glen's infantry 10072) takes nothing
    monkeypatch.setattr(combat, "random", Even())
    s, role = grey_rock, game.make(NoSave(), 0)
    b = s.data["battle"]
    kobolds, friends = list(b.troops[20000]["units"]), list(b.troops[10072]["units"])
    serial = cast(role, s, 10067, 500045, 20000)
    execute(role, s, serial, [(20000, [0]), (10072, [0])])
    archers = combat.np_combatant(134060, 0)
    hit = combat.resolve(archers, b.troops[20000]["c"], combat.ability_attack(archers, 500045, 1, 1))
    assert b.troops[20000]["units"][0] == kobolds[0] - hit and b.troops[10072]["units"] == friends


def test_a_leaders_skill_strikes_with_the_leaders_record(grey_rock, monkeypatch):
    # Glen's troop 10000 (134120) is led by Glen (npleadertable 134010: ACTIVESKILL01 200137 Lv 1, the "vitality
    # decrease" the troll fight's groggy wants): a cast of 200137 by the troop uid is Glen's, his attack and level,
    # not the troop's
    monkeypatch.setattr(combat, "random", Even())
    s, role = grey_rock, game.make(NoSave(), 0)
    b = s.data["battle"]
    troll = b.troops[20082]
    before = combat.Battle.total(troll)
    glen = b.troops[10000]["leader_c"]
    assert 200137 in glen["skills"] and 200137 not in b.troops[10000]["c"]["skills"]
    serial = cast(role, s, 10000, 200137, 20082)
    execute(role, s, serial, [(20082, [0])])
    hit = combat.resolve(glen, troll["c"], combat.ability_attack(glen, 200137, 1, 1))
    assert hit != combat.resolve(b.troops[10000]["c"], troll["c"], combat.ability_attack(b.troops[10000]["c"], 200137))
    assert combat.Battle.total(troll) == before - hit


def test_an_np_cast_spends_none_of_the_heros_sp(grey_rock):
    # the hero's SP pays his own casts (combat.spend, caster 0); an NP caster's 500045 (SP 40) is the troop's affair
    s, role = grey_rock, game.make(NoSave(), 0)
    s.data["pools"] = {"sp": 100, "sp_max": 100, "ammo": 0, "ammo_max": 0}
    n = len(s.sent)
    serial = cast(role, s, 10067, 500045, 20001)
    execute(role, s, serial, [(20001, [0])])
    assert s.data["pools"]["sp"] == 100 and combat.S2C_STATS not in [w.proto for w in s.sent[n:]]


def test_casts_of_several_troops_in_flight_keep_their_own_caster_and_ability(grey_rock, monkeypatch):
    # every NP troop casts on its own cooldown (the client's), so casts overlap: each serial keeps its caster, ability
    # and execute count; the executes of one never borrow another's
    monkeypatch.setattr(combat, "random", Even())
    s, role = grey_rock, game.make(NoSave(), 0)
    a = cast(role, s, 20164, 500044, 10073)
    c = cast(role, s, 20081, 500043, 10072)
    assert a != c
    execute(role, s, c, [(10072, [0])])
    execute(role, s, a, [(10073, [0])])
    replies = echoes(s, combat.S2C_ABILITY_EXECUTE)[-2:]
    assert [struct.unpack_from("<HxH", r) for r in replies] == [(c, 20081), (a, 20164)]
    runs = s.data["cast_runs"]
    assert (runs[c]["caster"], runs[c]["ability"]) == (20081, 500043)
    assert (runs[a]["caster"], runs[a]["ability"]) == (20164, 500044)


def test_an_np_cast_of_an_unknown_troop_or_ability_is_answered_not_dropped(grey_rock):
    # a caster the server never spawned (a script's), an ability with no table row: 0x5060 all the same (without it
    # the ability stays reserved in the troop), and its execute is echoed with no damage and no crash
    s, role = grey_rock, game.make(NoSave(), 0)
    serial = cast(role, s, 4321, 999999999, 10073)
    before = list(s.data["battle"].troops[10073]["units"])
    execute(role, s, serial, [(10073, [0])])
    assert struct.unpack_from("<H", echoes(s, combat.S2C_ABILITY_EXECUTE)[-1], 3)[0] == 4321
    assert s.data["battle"].troops[10073]["units"] == before


def test_an_np_cast_is_a_journal_line(tmp_path, monkeypatch):
    # the live check reads the journal: "enemy troop 20164 casts 500044 그레이록요새_독화살 (level 1) on troop 10073",
    # then the hits summary under the caster
    monkeypatch.setattr(net, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(net, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(net, "LOG_DIR", tmp_path)
    path = net.open_journal()
    try:
        s = mission_room(10234)
        run_pending(s)
        game.spawn_troops(s, [20164])
        cast(game.make(NoSave(), 0), s, 20164, 500044, 10073)
    finally:
        net.close_journal()
    import json
    import pathlib
    [e] = [x for x in map(json.loads, pathlib.Path(path).read_text(encoding="utf-8").splitlines()) if x["k"] == "cast"]
    assert (e["troop"], e["ability"], e["target"], e["side"]) == (20164, 500044, 10073, "enemy")
    assert timeline.server_text(e) == "enemy troop 20164 casts 500044 그레이록요새_독화살 (level 1) on troop 10073"

"""Statuses respect immunities (owner 2026-09-30: "as close to the vanilla original as possible"). Only the original
server decided them: the client's statuseffectinfo %Basic reader 0x14197ad10 takes 15 of the 31 columns (Id, Relation,
Target, Affect, IconName, ScreenControlId, Visible, Path, Group_1..3, StatusType, Ground_TargetRace / _TargetBranch,
Priority), never Immune_Type1..6; the 0x5074 path (0x140ca22f0 -> 0x140ca2c70 / 0x140ca2d70) puts whatever the server
sends; a status's traits reach the client only for speed (0x1407bc0c0 -> 0x140a04c90: 0x27 ATTACK_SPEED, 0xe
MAX_MOVE_SPEED). The tables say who resists what: a status's Immune_Type1..6 name the E_TraitTypes (stat enum
0x1434a74e0: IMMUNE_CAPTURE .. IMMUNE_DEBUFF 44-65, IMMUNE_HP_MAX 78, IMMUNE_BUFF 84, M_IMMUNE_* 106-109, 113-115)
that keep it off, in per mille, as the passives give them (42002 IMMUNE_NON_CONTROLLABLE: TraitType1
M_IMMUNE_NON_CONTROLLABLE 200 / 400 / 600 / 800 / 1000 at levels 1-5). The Mountain Troll 134080 holds 42002 and 42008
at level 5. Run: py -m pytest -q server/tests"""
import json
import pathlib

from kuf2 import combat, game, net, status, timeline
from conftest import run_pending
from test_battle import NoSave, added, hero_record, mission_room, use_ability
from test_np_skills import cast, execute

TROLL, KOBOLDS, SORCERER = 20082, 20000, 20081      # Grey Rock 10234: 134080, 134170 (no passive), 134020


def grey_rock(**kit):
    """Grey Rock at its start with the troll's force and the sorcerer brought in; the hero at level 6 (the tape's)."""
    s = mission_room(10234)
    run_pending(s)
    game.spawn_troops(s, [TROLL, SORCERER])
    s.data["battle"].troops[0]["c"] = hero_record(level=6)
    s.data["kit"] = {int(k[1:]): v for k, v in kit.items()}
    return game.make(NoSave(), 0), s


class Roll:
    """status.random with a fixed randrange draw."""
    def __init__(self, n):
        self.n = n

    def randrange(self, top):
        return self.n


def test_the_troll_is_immune_to_the_heros_stun(monkeypatch):
    # the flash grenade 5090 (Aldric's kit): ENEMY blind 6438 L2 (Immune_Type IMMUNE_DEBUFF) and stun 87 L3
    # (IMMUNE_PHYSICAL, IMMUNE_DEBUFF, IMMUNE_STUN, M_IMMUNE_NON_CONTROLLABLE). The troll holds
    # M_IMMUNE_NON_CONTROLLABLE 1000 (42002 at level 5): the blind lands, the stun does not; the kobolds take both
    lines = []
    monkeypatch.setattr(net, "journal", lambda k, **f: lines.append(dict(k=k, **f)))
    role, s = grey_rock(a5090=1)
    use_ability(role, s, 5090, [TROLL, KOBOLDS])
    assert (6438, 2, 20, [TROLL, KOBOLDS], 0) in added(s)
    assert (87, 3, 3, [KOBOLDS], 0) in added(s)
    assert 87 not in status.holding(s, TROLL) and 87 in status.holding(s, KOBOLDS)
    [e] = [x for x in lines if x["k"] == "immune"]
    assert (e["troop"], e["status"], e["level"], e["trait"], e["value"], e["caster"]) == (
        TROLL, 87, 3, "M_IMMUNE_NON_CONTROLLABLE", 1000, 0)
    assert timeline.server_text(e) == ("troop 20082 immune to status 87 기절_영웅용 (level 3) from troop 0: "
                                       "M_IMMUNE_NON_CONTROLLABLE 1000")


def test_an_immunity_below_1000_is_a_per_mille_roll(monkeypatch):
    # level 1 of 42002 gives 200: the stun is kept off on a draw below 200 of 1000 (the client's own trait chances
    # read so: PROBABILITY_COUNTER / _GUARD 0x14079b000, _DODGE 0x14079b060, rand % 1000 < value)
    role, s = grey_rock()
    kobolds = s.data["battle"].troops[KOBOLDS]
    kobolds["c"] = dict(kobolds["c"], passives={42002: 1})           # a copy: np_combatant's records are cached
    monkeypatch.setattr(status, "random", Roll(199))
    assert status.resisted(s, KOBOLDS, 87) == ("M_IMMUNE_NON_CONTROLLABLE", 200)
    monkeypatch.setattr(status, "random", Roll(200))
    assert status.resisted(s, KOBOLDS, 87) is None
    assert status.resisted(s, TROLL, 87) == ("M_IMMUNE_NON_CONTROLLABLE", 1000)
    assert status.resisted(s, TROLL, 6438) is None                  # IMMUNE_DEBUFF: the troll has none
    # the finish state names no Immune_Type: the troll still gets 32 COMMON_FINISH_TU at 10 % (the vitality lesson)
    assert status.immune_types(32) == () and status.resisted(s, TROLL, 32) is None


def test_an_np_cast_on_the_guarding_hero_keeps_its_debuff_off(monkeypatch):
    # the sorcerer's poison floor 500043 puts 1005 (IMMUNE_NATURE, IMMUNE_DEBUFF, IMMUNE_DEFENCE_DOWN) on its targets
    # (its 3000289 is a GROUND status: the client's 0x5075 asks for it); the hero's guard 341 holds IMMUNE_DEBUFF 1000
    # (TraitTarget LEADER: him). The handed fire archers 10073 beside him hold nothing
    role, s = grey_rock()
    status.apply(s, [0], 341, 1, 0)
    serial = cast(role, s, SORCERER, 500043, 0)
    execute(role, s, serial, [(0, []), (10073, [0])])
    assert [(st, uids) for st, _, _, uids, _ in added(s) if st == 1005] == [(1005, [10073])]
    assert status.resisted(s, 0, 1005) == ("IMMUNE_DEBUFF", 1000)
    assert status.resisted(s, 0, 3000289) is None                    # IMMUNE_NATURE / _NATURE_DOT: he has none


def test_the_meta_immunities_cover_what_their_name_says():
    # M_IMMUNE_STATUSEFFECT (42029 on walls and towers, the petrify 70361) and M_IMMUNE_DEBUFF (the escape 6321, the
    # revive's 33 / 34) are named in no Immune_Type but one: a holder resists every status naming an immunity / every
    # one naming IMMUNE_DEBUFF (ours, by the names). A trait that is no immunity in an Immune_Type column (the data's
    # ATTACK_PHYSICAL on 6425 / 6531 / 102310, M_DEFENCE_PHYSICAL on 946330) is no immunity
    assert "M_IMMUNE_STATUSEFFECT" in status.immune_types(87) and "M_IMMUNE_DEBUFF" in status.immune_types(87)
    assert "M_IMMUNE_DEBUFF" not in status.immune_types(3000289)
    assert "ATTACK_PHYSICAL" not in status.immune_types(6425)
    assert status.immune_types(946330) == ()
    role, s = grey_rock()
    status.apply(s, [0], 6321, 1, 0)                                   # the escape: M_IMMUNE_DEBUFF 1000
    assert status.resisted(s, 0, 87) == ("M_IMMUNE_DEBUFF", 1000)
    kobolds = s.data["battle"].troops[KOBOLDS]
    kobolds["c"] = dict(kobolds["c"], passives={42029: 5})           # a wall's
    assert status.resisted(s, KOBOLDS, 3000289) == ("M_IMMUNE_STATUSEFFECT", 1000)


def test_a_leaders_own_immunity_leaves_his_troop_open(monkeypatch):
    # an NP leader's 42102 / 42108 are TraitTarget LEADER (him only; the engine puts statuses on whole troops, so they
    # keep nothing off it); 42026 IMMUNE_HP_MAX is ALL. The kobold commander 134040 leads 20155 (42102, 42108); Glen
    # 134010 leads 10000 (42102, 42108, 42026)
    role, s = grey_rock()
    game.spawn_troops(s, [20155])
    names = status.immune_types(87) + ("IMMUNE_HP_MAX", "M_IMMUNE_SPEED_DOWN")
    assert status.immunity(s, 20155, names) == {}
    assert status.immunity(s, 10000, names) == {"IMMUNE_HP_MAX": 1000}
    assert status.resisted(s, 20155, 87) is None


def test_an_immunity_is_a_journal_line(tmp_path, monkeypatch):
    # the live check reads the journal: "troop 20082 immune to status 87 기절_영웅용 (level 3) from troop 0: ..."
    monkeypatch.setattr(net, "JOURNAL_DIR", tmp_path / "journal")
    monkeypatch.setattr(net, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(net, "LOG_DIR", tmp_path)
    path = net.open_journal()
    try:
        role, s = grey_rock(a5090=1)
        use_ability(role, s, 5090, [TROLL])
    finally:
        net.close_journal()
    [e] = [x for x in map(json.loads, pathlib.Path(path).read_text(encoding="utf-8").splitlines()) if x["k"] == "immune"]
    assert e["troop"] == TROLL and e["spot"] == 10234 and e["name"] == "기절_영웅용"

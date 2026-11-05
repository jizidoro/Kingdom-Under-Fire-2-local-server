"""The hero's HP regeneration (planning/rules/HERO.md P7): a tick every 3 s of floor(S + lvuptypetable %Hero LvHPRestore
0.05 x %Hero_HP LV_<level>), S = HP_RECOVERY from gear, passives, sets and titles (the herotable base left out); x5 out
of combat, in villages, fields and rooms alike (texttutorial Basic_HeroControl1: "While in Combat state ... HP regen
decrease significantly"). The tape (the owner's Berserker; hunt agent reads 2026-10-01): Lv.1 +4 in combat / +20 out
(tiouWoPSPks f_00230-00285), Lv.2 +5 / +25 (f_00674-00713, Grey Fog Street), Lv.6 +24 at Grey Rock between hits and +120
in the Mist Field village and after the fight (qeeQjhgO8ss 2 fps 2205_2217, f_00853, f_01112), Lv.6 in the Supplied
Trainee set +185 (6uClEdAS__k f_00012)."""
import pytest

from kuf2 import combat, game, hero, items
from test_battle import Session

BERSERKER = 4
ADVENTURER_BOTTOMS, SUPPLIED_TRAINEE_TOP = 152304113, 151306110
TRAINEE_SET = [101306110, 102306110, 151306110, 152306110, 153306110, 154306110, 155306110]


def berserker(level, swap=None, codes=None):
    if codes:
        return {"id": 1, "class": BERSERKER, "level": level,
                "equip": [{"code": x, "index": items.PARTS[items.row(x)["Parts"]] - 1, "serial": i + 1}
                          for i, x in enumerate(codes)]}
    c = {"id": 1, "class": BERSERKER, "level": level}
    for e in hero.equipment(c):
        if e["index"] in (swap or {}):
            e["code"] = swap[e["index"]]
    return c


TAPE = [   # (what, the character, the tape's tick in combat, out of combat)
    ("Lv.1 class kit (Old Novice Bottoms +3)", berserker(1), 4, 20),
    ("Lv.2 class kit", berserker(2), 5, 25),
    ("Lv.6 Adventurer Bottoms +15, 715 L1 +3", berserker(6, {2: SUPPLIED_TRAINEE_TOP, 3: ADVENTURER_BOTTOMS}), 24, 120),
    ("Lv.6 Supplied Trainee set (bottoms +23, 3-set +5)", berserker(6, codes=TRAINEE_SET), 37, 185),
]


@pytest.mark.parametrize("what, c, fighting, resting", TAPE, ids=[t[0] for t in TAPE])
def test_the_tick_is_the_tapes_in_and_out_of_combat(what, c, fighting, resting):
    assert hero.regen_tick(c) == fighting
    assert hero.regen_tick(c) * hero.HP_REGEN_OUT_OF_COMBAT == resting


@pytest.mark.parametrize("level, s, tape", [(14, 70, 94), (15, 70, 96), (16, 70, 98), (19, 95, 135), (20, 95, 140)])
def test_the_level_term_steps_the_tick_as_the_tape(level, s, tape):
    """The tape's ticks across level-ups with S held (tUb99Vs2t_g, RVJnrq3zPlo, rTitaEjTUoc): floor(S + 0.05 x Hero_HP)."""
    hp = float(hero._row("lvuptypetable", "Hero_HP", "ID", "REGNIER")[f"LV_{level}"])
    restore = float(hero._row("lvuptypetable", "Hero", "ID", "REGNIER")["LvHPRestore"])
    assert int(s + restore * hp) == tape


class Room(Session):
    def __init__(self, c, hp, fighting):
        super().__init__()
        self.pending = []
        self.data["char"] = c
        self.data["battle"].add_hero(0, 5000)
        t = self.data["battle"].troops[0]
        t["hp"], t["combat"] = hp, fighting
        self.data["pools"] = dict(game.pools_for(c, 10234), hp_rec=hero.regen_tick(c))

    def later(self, delay, fn):
        self.pending.append((delay, fn))


@pytest.mark.parametrize("fighting, gain", [(True, 24), (False, 120)])
def test_a_room_tick_heals_by_the_combat_state(fighting, gain):
    s = Room(berserker(6, {2: SUPPLIED_TRAINEE_TOP, 3: ADVENTURER_BOTTOMS}), 1000, fighting)
    combat.start_regen(s)
    delay, tick = s.pending[-1]
    assert delay == combat.SP_TICK_S == 3.0
    tick()
    assert s.data["battle"].troops[0]["hp"] == 1000 + gain


def test_the_room_start_sets_the_tick():
    c = berserker(6, {2: SUPPLIED_TRAINEE_TOP, 3: ADVENTURER_BOTTOMS})
    s = Room(c, 1000, True)
    s.data["pools"]["hp_rec"] = 0
    game.room_stats(s, c)
    assert s.data["pools"]["hp_rec"] == 24


# --- P13: the Berserker's Dark Energy, +1 every 3 s from his passive 616 -> status 6539 (OverTime 3, STACK1 +1) ---------

def test_dark_energy_rises_one_every_three_seconds_and_holds_at_99():
    """The tape (qeeQjhgO8ss): 15 (21:28) -> 24 (21:58) -> 34 (22:28) in the village, +1 at 25:58.0 / 26:01.5 / 26:04.5 /
    26:07.5 in the Fog Field; 99 held; 0 again in a new room (the pools start at %ApSp Stack1_Init 0)."""
    c = berserker(6)
    s = Room(c, 5000, False)
    assert (s.data["pools"]["ammo"], s.data["pools"]["ammo_max"]) == (0, 99)
    s.data.setdefault("statuses", {}).setdefault(0, {})[6539] = {"level": 1, "until": None, "groups": (),
                                                                 "since": 100.0}     # held from the room start
    assert combat.pool_ticks_due(s)
    assert combat.pool_ticks(s, now=102.0) == {}
    assert combat.pool_ticks(s, now=103.0) == {combat.STAT_AMMO: 1}                  # the first +1 3 s in
    assert combat.pool_ticks(s, now=130.0) == {combat.STAT_AMMO: 10}     # 27 s: nine more
    s.data["pools"]["ammo"] = 98
    combat.pool_ticks(s, now=160.0)
    assert s.data["pools"]["ammo"] == 99 and not combat.pool_ticks_due(s)


def test_the_regeneration_keeps_ticking_for_dark_energy_at_full_hp_and_sp():
    c = berserker(6)
    s = Room(c, 5000, False)
    s.data["battle"].troops[0]["max"] = 5000
    s.data.setdefault("statuses", {}).setdefault(0, {})[6539] = {"level": 1, "until": None, "groups": ()}
    combat.start_regen(s)
    assert s.pending and s.pending[-1][0] == combat.SP_TICK_S

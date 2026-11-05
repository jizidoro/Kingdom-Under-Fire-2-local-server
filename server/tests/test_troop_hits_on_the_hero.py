"""An enemy troop's hit on the hero against the original's tape (build/intake 2026-10-24; rules census COMBAT A1 / A9 /
A12, BATTLE-WIRING §3). The brief's premise, from order-c's decision 2: ours 9-21 a hit outside the prologue's gate, the
tape's three hits of 1, 3 and 6 in a minute, so ours 3-5 times too big. The 1, 3, 6 were HUD differences with the hero's
own regeneration inside them (+4 every 3 s at level 1, hero.regen_tick): at 10 fps the HUD reads 450 -> 442 (red "8"
over the hero at 5:02.6) -> 446 -> 450 -> 440 (red "10" at 5:09.15) -> 444 -> 448 -> 450. Every red number the tape
puts over the hero from a known enemy troop is what our resolver gives that troop against the hero in the tape's gear,
within the spread (V 0.9-1.1, no crit word, no miss word on any of them).

The tape (frames read 2026-10-24 at 10 fps from the cached part 2 mp4 and fetched spans of parts 1 and 3; the reads and
sheets in planning/agents/reports/2026-10-24_intake.md): the owner's Berserker (REGNIER, class 4) in the gear the HUD's
max HP and regeneration tick prove (tests/test_hero_hp.py, tests/test_hero_regen.py):
  part 1 tiouWoPSPks, the prologue 50116 outside the gate: Lv.1, the class kit (450 HP, defence 81)
  part 2 qeeQjhgO8ss, the Tower of Moonlight 10233: Lv.4, the Supplied Adventurer Top (958 HP, defence 186)
  part 2, Grey Rock 10234: Lv.6, the Supplied Trainee Top and Adventurer Bottoms (3,340 HP, tick +24, defence 392)
  part 3 6uClEdAS__k, the Lunawing Crash Site field 10351: Lv.8, the Supplied Trainee set (3,802 HP, tick +42, 821)
The defence-sensitive reads are the Lv.6 troll's and the Lv.8 ones (the attacker's penetration below the hero's
defence): together they hold the defence term's constant at level 8 between about 2,900 and 7,300 (364-913 a level);
ours is DEF_K_PER_LEVEL 500 x 8 = 4,000. A level-free 500 would make Bettor's plain blow 18-22 (the tape: 38, 41)."""
import pytest

from kuf2 import combat, game, hero, items

ADVENTURER_BOTTOMS, SUPPLIED_ADVENTURER_TOP, SUPPLIED_TRAINEE_TOP = 152304113, 151301110, 151306110
TRAINEE_SET = [101306110, 102306110, 151306110, 152306110, 153306110, 154306110, 155306110]


def berserker(level, swap=None, codes=None):
    if codes:
        return {"id": 1, "class": 4, "level": level,
                "equip": [{"code": x, "index": items.PARTS[items.row(x)["Parts"]] - 1, "serial": i + 1}
                          for i, x in enumerate(codes)]}
    c = {"id": 1, "class": 4, "level": level}
    for e in hero.equipment(c):
        if e["index"] in (swap or {}):
            e["code"] = swap[e["index"]]
    return c


HEROES = {   # the tape's hero: (character, HUD max HP, HUD regeneration tick in combat)
    "prologue Lv.1": (berserker(1), 450, 4),
    "Tower Lv.4": (berserker(4, {2: SUPPLIED_ADVENTURER_TOP}), 958, None),
    "Grey Rock Lv.6": (berserker(6, {2: SUPPLIED_TRAINEE_TOP, 3: ADVENTURER_BOTTOMS}), 3340, 24),
    "Crash Site Lv.8": (berserker(8, codes=TRAINEE_SET), 3802, 42),
}

PLAIN = ("ATTACK_NORMAL_COMMON_1",)
ANY = None                                   # any action of the attacker's %Combat slots (the blow is not identified)

# (where, frame (video time), the tape's red number over the hero, hero, [(attacker nptrooptable id, actions)])
TAPE = [
    ("prologue, F20200's 5-attack primitives in the mob (48-unit troops)", "p1 5:02.65", 8, "prologue Lv.1",
     [(111160, ANY), (111470, ANY)]),
    ("prologue, the gate's primitives 111310 (F20000 / F20010) or a 5-attack one's rush", "p1 5:09.15", 10,
     "prologue Lv.1", [(111310, PLAIN), (111160, ANY)]),
    ("Grey Rock bridge, a kobold archer (5 x MAIN_ATTACK_REVISION 2; the infantry's plain blow is 20-25)",
     "p2 33:15.75", 10, "Grey Rock Lv.6", [(134040, ANY)]),
    ("Grey Rock, the Mountain Troll's club", "p2 42:04.35", 128, "Grey Rock Lv.6", [(134080, PLAIN)]),
    ("Grey Rock, the troll's knock-up blow", "p2 42:09.45", 164, "Grey Rock Lv.6",
     [(134080, ("ATTACK_LIGHT_RUSH_COMBO_1", "ATTACK_LIGHT_RUSH_COMBO_2"))]),
    ("Grey Rock, the troll's club again", "p2 42:12.95", 128, "Grey Rock Lv.6", [(134080, PLAIN)]),
    ("Tower, the Encablossian Scorpion's first blow", "p2 16:27.75", 214, "Tower Lv.4", [(133220, PLAIN)]),
    ("Tower, two red numbers together (Encablossian archers / primitives)", "p2 16:44.15", 18, "Tower Lv.4",
     [(133070, ANY), (133060, ANY)]),
    ("Tower, the second of the pair", "p2 16:44.15", 16, "Tower Lv.4", [(133070, ANY), (133060, ANY)]),
    ("Tower, one red number", "p2 16:40.65", 18, "Tower Lv.4", [(133070, ANY), (133060, ANY)]),
    ("Crash Site, Bettor's special attack (SKILL_SKILL_111, POWERRATE 2.5)", "p3 20:55.05", 97, "Crash Site Lv.8",
     [(155340, ("SKILL_SKILL_111",))]),
    ("Crash Site, Bettor's blow", "p3 20:56.4", 38, "Crash Site Lv.8", [(155340, PLAIN)]),
    ("Crash Site, Bettor's next blow", "p3 20:58.0", 41, "Crash Site Lv.8", [(155340, PLAIN)]),
    ("Crash Site, a Sawtooth Mercenary Group Member (Lv.8, 887 HP: 155060 / 155070)", "p3 16:49.9", 55,
     "Crash Site Lv.8", [(155060, PLAIN), (155070, PLAIN)]),
]


class Edge:
    """An rng at one end of every draw: the spread at 0.9 or 1.1, never a miss or a crit (no word on these numbers)."""
    def __init__(self, end):
        self.end = end

    def uniform(self, a, b):
        return a + (b - a) * self.end

    def random(self):
        return 0.999999


def span(att, tgt, attack, guard=None):
    return tuple(combat.resolve_hit(att, tgt, attack, rng=Edge(end), guard=guard)[0] for end in (0.0, 1.0))


def spans(tid, actions, tgt, guard=None):
    """{action: (low, high)} of one attacker's blows on the hero: hit_attack of each action named (ANY: every action
    its %Combat slots name)."""
    att = combat.np_combatant(tid)
    names = combat._action_names()
    return {a: span(att, tgt, combat.hit_attack(att, names.index(a)), guard) for a in (actions or att["powers"])}


@pytest.mark.parametrize("hero_name", HEROES)
def test_the_tapes_hero_is_rebuilt_from_his_hud(hero_name):
    c, hp, tick = HEROES[hero_name]
    assert hero.char_stats(c)["HP_MAX"] == hp
    if tick is not None:
        assert hero.regen_tick(c) == tick


@pytest.mark.parametrize("where, frame, tape, hero_name, attackers", TAPE, ids=[f"{t[1]} {t[2]}" for t in TAPE])
def test_a_troops_hit_on_the_hero_is_the_tapes(where, frame, tape, hero_name, attackers):
    tgt = game.hero_combatant(HEROES[hero_name][0])
    found = {tid: spans(tid, actions, tgt) for tid, actions in attackers}
    assert any(lo <= tape <= hi for by in found.values() for lo, hi in by.values()), (where, frame, tape, found)


def test_the_troll_on_the_guarding_hero_is_the_tapes_defence_14():
    """p2 42:08.95: red "Defence 14" on the guarding Berserker between the troll's 128 and 164: a fresh guard takes
    (700 + 300) x 90 % (combat.guard_reduce) off the troll's club or its rush combo."""
    tgt = game.hero_combatant(HEROES["Grey Rock Lv.6"][0])
    found = spans(134080, PLAIN + ("ATTACK_LIGHT_RUSH_COMBO_1",), tgt, guard=900)
    assert any(lo <= 14 <= hi for lo, hi in found.values()), found


def test_a_level_free_defence_constant_misses_the_level_8_reads(monkeypatch):
    """The falsifier of DEF_K_PER_LEVEL: with 500 for every level (no level term) Bettor's plain blow on the Lv.8 hero
    in the Supplied Trainee set (defence 821, Bettor's penetration 0) is 18-22, the tape's 38 and 41 out of reach;
    with ours (500 x 8) it is 36-43."""
    tgt = game.hero_combatant(HEROES["Crash Site Lv.8"][0])
    assert spans(155340, PLAIN, tgt)[PLAIN[0]] == (36, 43)
    monkeypatch.setattr(combat, "DEF_K_PER_LEVEL", 500 / 8)
    lo, hi = spans(155340, PLAIN, tgt)[PLAIN[0]]
    assert hi < 38


def test_the_prologue_hud_is_two_hits_and_the_regeneration():
    """p1 5:00-5:16 at 10 fps: the HUD's 450, 442, 446, 450, 440, 444, 448, 450 are the red 8 (5:02.25) and 10 (5:09.15)
    and the Lv.1 tick of +4 every 3 s (5:03.85, 5:06.85, 5:09.85, 5:12.85, 5:15.85), capped at the max: not three hits
    of 1, 3 and 6 (order-c's reading of the differences)."""
    c, top, tick = HEROES["prologue Lv.1"]
    events = sorted([(302.25, -8), (309.15, -10)] + [(t, hero.regen_tick(c)) for t in (303.85, 306.85, 309.85,
                                                                                        312.85, 315.85)])
    hp, reads = top, [top]
    for _, change in events:
        hp = min(top, hp + change)
        if hp != reads[-1]:
            reads.append(hp)
    assert reads == [450, 442, 446, 450, 440, 444, 448, 450]

"""The hero's rules against the original (planning/rules/HERO.md, owner 2026-09-30: as close to the vanilla original as
possible). Each CHECKABLE row is recomputed from the tables; the tape rows name their frames (Sorrowh's Berserker,
REGNIER, class 4; captures/video/<video>_0_<length>_frames_0.5, f_<n> = (n - 1) x 2 s).

L9 (census gap 1, decision A4): the AutoLearn rows level with the hero. Part 9 34:44 (9NwV8ikwLYk f_01043): "The hero
levelled up." and "Hero Skill/Action Level-up success." (text 7126, the client's line for a 0x1761 entry of level 2 or
more, 0x140da4e79) in one frame at Lv.17, no skill window opened (it opens at f_01046); 716 is the only row whose cycle
lands at 17 (HeroLevel 2 + 5 x 3). The second such line at f_01051 follows a click in the tree ("Total of 1 skill points
and 0 Gold required", f_01050). Part 1 (tiouWoPSPks) at Lv.2: "Learned Capture skill. Learned Exile's Power skill."
(710, 716: text 7102 for a new 0x1761 entry); Lv.3 "Learned Exile's Resistance" (717); Lv.4 "Exile's Will" (715)."""
import json
import logging
import pathlib
import struct

import pytest

from kuf2 import combat, game, hero, items, net, skills, tables, timeline, titles, world
from test_battle import Session, pkt
from test_hero_gear import St, aldric, journal, qwe123   # noqa: F401 (journal is a fixture)

BERSERKER, SPELLSWORD, GUNSLINGER, HELENA = 4, 3, 0, 5


class State:
    def save(self):
        pass


def book_rows():
    return [(cls, r) for cls in range(6) for r in skills.book(cls).values() if r["AutoLearn"] == "True"]


@pytest.mark.parametrize("cls, r", book_rows(), ids=lambda v: str(v["AbilityId"]) if isinstance(v, dict) else str(v))
def test_every_autolearn_row_holds_the_level_the_trees_gate_allows_at_no_tp(cls, r):
    """CHECKABLE L9: at each hero level, the row's level is the highest the tree's gate (skills._refusal) lets a click
    reach, and the levels cost no TP (RequireLevelTP 0 on every row that grows)."""
    start, cycle, top = int(r["HeroLevel"]), int(r["RequireHeroLevelUpCycle"]), int(r["AbilityMaxLevel"])
    for level in range(1, 31):
        want = 0 if level < max(start, 1) else (min(top, 1 + (level - max(start, 1)) // cycle) if cycle else 1)
        assert skills.auto_level(r, level) == want
        c = {"id": 1, "class": cls, "level": level}
        if want:
            held = skills.hero_skills(c)
            assert held[int(r["AbilityId"])] >= want
            if want < top:                                  # one more is refused by the gate at this level
                assert skills._refusal(c, r, int(r["AbilityId"]), want + 1, held, 999) == skills.NOT_LEARNABLE
    if top > 1:
        assert int(r["RequireLevelTP"]) == 0


TAPE_LEVELS = [   # (video, frame, time, hero level, {ability: level the tape implies})
    ("9NwV8ikwLYk", "f_01043", "34:44", 17, {715: 3, 716: 4, 717: 3, 639: 1}),
    ("6uClEdAS__k", "f_01301", "43:20", 9, {715: 2, 716: 2, 717: 2}),          # 4,250 HP = ... + 715's 800
]


@pytest.mark.parametrize("video, frame, at, level, want", TAPE_LEVELS)
def test_the_berserkers_passives_follow_his_level(video, frame, at, level, want):
    held = skills.hero_skills({"id": 1, "class": BERSERKER, "level": level})
    assert {a: held[a] for a in want} == want


def test_at_lv17_one_row_lands_as_the_tape_shows_one_success_line():
    c = {"id": 1, "class": BERSERKER, "level": 17}
    assert skills.gained(c, 16) == [(716, 4)]


def exp_to(level, c):
    return sum(world.hero_need(lv) for lv in range(c["level"], level)) - c.get("exp", 0)


def learn_entries(w):
    b = bytes(w.buf)
    assert struct.unpack_from("<hH", b, 0)[0] == 0
    n = struct.unpack_from("<H", b, 2)[0]
    return [(b[4 + 6 * i + 1], struct.unpack_from("<I", b, 4 + 6 * i + 2)[0]) for i in range(n)]


@pytest.mark.parametrize("start, end, want", [
    (1, 2, [(1, 710), (1, 716)]),        # "Learned Capture skill. Learned Exile's Power skill." (part 1, Lv.2)
    (2, 3, [(1, 717)]),                  # "Learned Exile's Resistance" (part 1 30:5x)
    (3, 4, [(1, 635), (1, 715)]),        # "Learned True Dark Impact skill. Learned Exile's Will skill." (part 1 38:34)
    (16, 17, [(4, 716)]),                # "Hero Skill/Action Level-up success." (part 9 34:44)
    (7, 9, [(1, 609), (1, 627), (1, 737), (1, 760), (1, 642), (1, 656), (1, 655), (1, 657), (2, 717), (2, 715),
            (1, 745)]),                  # two levels at once: one push for both, with the follow-ups Lv.9 opens
])
def test_a_level_up_pushes_what_it_brings_as_the_original_did(start, end, want):
    s = Session()
    c = s.data["char"] = {"id": 1, "name": "Sorrowh", "class": BERSERKER, "level": start, "exp": 0}
    s.data.pop("battle")
    world.add_exp(s, State(), exp_to(end, c))
    assert c["level"] == end
    pushes = [w for w in s.sent if w.proto == skills.S2C_LEARN]
    assert len(pushes) == 1 and sorted(learn_entries(pushes[0]), key=lambda e: e[1]) == sorted(want, key=lambda e: e[1])
    raised = {str(a): skills.auto_level(r, end) for a, r in skills.book(BERSERKER).items()
              if r["AutoLearn"] == "True" and skills.auto_level(r, end) > 1}
    assert (c.get("skills") or {}) == raised                                 # the save records every risen row
    block = next(w for w in s.sent if w.proto == world.S2C_HERO_BLOCK)       # sent before or after, it holds them
    assert block is not None


TAPE_ANNOUNCED = [   # (video, frame, level reached, the chat's lines in order as (ability, level)) - skills.announced
    ("tiouWoPSPks", "f_00603", 2, [(710, 1), (716, 1)]),     # Capture, Exile's Power (not 711 / 746 under 710)
    ("tiouWoPSPks", "f_00919", 3, [(717, 1)]),               # Exile's Resistance
    ("tiouWoPSPks", "f_01158", 4, [(635, 1), (715, 1)]),     # True Dark Impact (under 633), Exile's Will
    ("qeeQjhgO8ss", "f_00673", 5, []),                       # "The hero levelled up." alone
    ("qeeQjhgO8ss", "f_00790", 6, [(605, 1), (5012, 1)]),    # Earth Cleaver (under 608), Supplement
    ("6uClEdAS__k", "f_00026", 7, [(716, 2)]),               # one "Hero Skill/Action Level-up success."
    ("_0FD8aKDxto", "f_00296", 10, [(739, 1), (691, 1)]),    # Dark Impact - Wave, then Land of Death (book rows 66, 67)
    ("m-CmO76YaoA", "f_00041", 11, []),
    ("9NwV8ikwLYk", "f_01043", 17, [(716, 4)]),
]


@pytest.mark.parametrize("video, frame, level, want", TAPE_ANNOUNCED, ids=[f"Lv{t[2]}" for t in TAPE_ANNOUNCED])
def test_a_level_up_announces_the_lines_the_tape_shows_in_its_order(video, frame, level, want):
    """L9's gap (linked follow-ups): the 0x1761 of a level-up lists the AutoLearn rows and the follow-ups the level
    opens under a parent held before it, in the book's row order, as the original's chat printed them."""
    s = Session()
    c = s.data["char"] = {"id": 1, "name": "Sorrowh", "class": BERSERKER, "level": level - 1, "exp": 0}
    s.data.pop("battle")
    world.add_exp(s, State(), exp_to(level, c))
    pushes = [w for w in s.sent if w.proto == skills.S2C_LEARN]
    assert [(a, lv) for lv, a in (learn_entries(pushes[0]) if pushes else [])] == want


def test_learning_a_passive_resends_the_hero_window_and_the_rooms_numbers():
    """S11: the tree's learn (0x1760) resends 0x134b, whose HP holds the passive; in a room 0x5138 and the record."""
    st = type("St", (), {"save": lambda self: None, "game_sessions": {}})()
    role = type("R", (), {"handlers": {}, "on": lambda self, p: (lambda f: self.handlers.__setitem__(p, f) or f)})()
    skills.make(role, st)
    s, g = Session(), Session()
    s.data.pop("battle")
    c = s.data["char"] = g.data["char"] = {"id": 1, "class": 0, "level": 30}
    s.data["account"] = g.data["account"] = {"id": 9, "characters": [c]}
    st.game_sessions[9] = g
    g.data["battle"].add_hero(0, 5000)
    g.data["battle"].troops[0]["max"] = 5000
    row = next(r for r in skills.book(0).values() if r["AutoLearn"] != "True" and int(r["RequireTP"] or 0) > 0
               and skills._refusal(c, r, int(r["AbilityId"]), 1, skills.hero_skills(c), 99) == 0)
    aid = int(row["AbilityId"])
    role.handlers[skills.C2S_LEARN](s, pkt(skills.C2S_LEARN, struct.pack("<HIB", 1, aid, 1)))
    assert c["skills"][str(aid)] == 1
    block = next(w for w in s.sent if w.proto == world.S2C_HERO_BLOCK)
    assert bytes(block.buf) == world.hero_block(c)
    assert any(w.proto == combat.S2C_STATS for w in g.sent) and aid in g.data["kit"]


def test_a_level_up_in_a_room_hands_the_new_abilities_to_the_room():
    s = Session()
    c = s.data["char"] = {"id": 1, "name": "Sorrowh", "class": BERSERKER, "level": 11, "exp": 0}
    s.data["battle"].add_hero(0, 5000)
    s.data["kit"] = skills.battle_abilities(c)
    world.add_exp(s, State(), exp_to(12, c))
    assert s.data["kit"] == skills.battle_abilities(c) and 639 in s.data["kit"]
    usable = [struct.unpack_from("<I", bytes(w.buf), 2)[0] for w in s.sent if w.proto == skills.S2C_ROOM_SKILL]
    assert 639 in usable and 636 in usable


def test_the_level_17_berserker_has_the_hp_of_his_passive_at_level_3():
    """715 Exile's Will: +400 at level 1, +1,200 at level 3 (Lv.17): the panel's max HP moves by 800."""
    c = {"id": 1, "class": BERSERKER, "level": 17}
    before = hero.stats(4, 17, hero.worn_codes(c), abilities={**skills.battle_abilities(c), 715: 1})["HP_MAX"]
    assert hero.stats(4, 17, hero.worn_codes(c), abilities=skills.battle_abilities(c))["HP_MAX"] - before == 800


def test_the_login_raises_aldrics_passives_once_journals_and_saves(journal, caplog):
    """Aldric (Gunslinger, level 30, nothing taught: his skills {} since his reset): 68 / 69 / 70 go from level 1 to 6
    (HeroLevel 3 / 4 / 2, cycle 5) and the groggy chain 60 to 4 (12, 6); 69's HP_MAX +300 -> +3,000. c["skills"]
    records them; a second login changes nothing."""
    st = St()
    role = world.make(st, 0, "127.0.0.1", 0)
    c = aldric()
    c.update(skills={}, tutorial_done=True, spot=world.START_SPOT, pos=list(world.START_POS))
    s = Session()
    s.data["account"] = {"characters": [c]}
    with caplog.at_level(logging.INFO, logger=net.log.name):
        role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 1, 0)))
    assert c["skills"] == {"60": 4, "68": 6, "69": 6, "70": 6}
    events = [json.loads(x) for x in pathlib.Path(journal).read_text(encoding="utf-8").splitlines()]
    ev = [e for e in events if e["k"] == "skill"]
    assert len(ev) == 1 and ev[0]["ev"] == "login" and ev[0]["levels"] == [[60, 1, 4], [68, 1, 6], [69, 1, 6], [70, 1, 6]]
    assert ev[0]["hp"][1] - ev[0]["hp"][0] == 3000 - 300
    assert timeline.server_text(ev[0]).startswith("character 1 'Aldric': hero skills 60 1 -> 4, 68 1 -> 6, 69 1 -> 6")
    assert any("Aldric" in r.getMessage() and "68" in r.getMessage() for r in caplog.records)
    saves = st.saves
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 1, 0)))
    events = [json.loads(x) for x in pathlib.Path(journal).read_text(encoding="utf-8").splitlines()]
    assert len([e for e in events if e["k"] == "skill"]) == 1 and st.saves == saves


def test_qwe123_at_level_6_has_nothing_to_raise():
    c = qwe123()
    assert skills.record_auto(c) == [] and "skills" not in c


def test_a_skill_reset_keeps_the_autolearn_levels_and_needs_a_taught_skill():
    role = type("R", (), {"handlers": {}, "on": lambda self, p: (lambda f: self.handlers.__setitem__(p, f) or f)})()
    skills.make(role, State())
    s = Session()
    s.data.pop("battle")
    c = s.data["char"] = {"id": 1, "class": GUNSLINGER, "level": 30, "gold": 10 ** 6, "skills": {"68": 6, "69": 6}}
    role.handlers[skills.C2S_RESET](s, pkt(skills.C2S_RESET, b""))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", skills.RESET_REFUSED) and c["gold"] == 10 ** 6
    c["skills"]["8"] = 1                                                     # a SKILLTREE1 skill
    role.handlers[skills.C2S_RESET](s, pkt(skills.C2S_RESET, b""))
    assert c["skills"] == {"68": 6, "69": 6} and skills.hero_skills(c)[70] == 6


# --- T3 (census gap 2): the worn title's effect -------------------------------------------------------------------

def titled():
    return [(int(r["Reward_Title_ID"]), int(r["Ability0_ID"]), int(r["Skill0_Level"]))
            for r in tables.sections("titletable")["Base"] if r["Ability0_ID"].isdigit()]


def test_180_titles_carry_an_ability_and_none_a_second():
    assert len(titled()) == 180
    assert all(r["Ability1_ID"] == "-" and r["Ability2_ID"] == "-" for r in tables.sections("titletable")["Base"])


@pytest.mark.parametrize("title, ability, level", titled())
def test_the_worn_titles_self_traits_count_in_the_heros_stats(title, ability, level):
    """CHECKABLE T3: wearing the title moves each stat by its ability's SELF traits at Skill0_Level (a number as is, an
    "x%" as that percent of the value before it); titles whose ability only carries ALLY statuses move nothing."""
    c = {"id": 1, "class": GUNSLINGER, "level": 30}
    bare = hero.char_stats(c)
    worn = hero.char_stats(dict(c, title=title))
    want = dict(bare)
    for name, value, percent in hero.passive_traits({ability: level}):
        for n in hero.GROUPS.get(name, (name,)):
            want[n] = want.get(n, 0.0) + (want.get(n, 0.0) * value / 100 if percent else value)
    moved = {k for k in set(worn) | set(bare) if abs(worn.get(k, 0) - bare.get(k, 0)) > 1e-9}
    assert all(abs(worn.get(k, 0) - want.get(k, 0)) < 1e-6 for k in set(want) | set(worn)
               if not k.startswith("ATTACK_") or k in ("ATTACK_PHYSICAL", "ATTACK_MAGICAL", "ATTACK_SPEED"))
    if not hero.passive_traits({ability: level}):
        assert moved == set()


@pytest.mark.parametrize("title, name, gain", [(60417, "Traveller", 3), (60418, "Adventurer", 5)])
def test_the_tapes_title_list_reads_the_titles_hp_recovery(title, name, gain):
    """Part 9 35:08 (9NwV8ikwLYk f_01055): "Current Title: Traveller  HP Recovery +3" ("In use"), "Adventurer  HP
    Recovery +5" listed: 5103 at levels 1 and 2."""
    c = {"id": 1, "class": BERSERKER, "level": 17}
    assert hero.char_stats(dict(c, title=title))["HP_RECOVERY"] - hero.char_stats(c)["HP_RECOVERY"] == gain


def roles(module, st):
    role = type("R", (), {"handlers": {}, "on": lambda self, p: (lambda f: self.handlers.__setitem__(p, f) or f)})()
    module.make(role, st)
    return role


def test_wearing_a_title_resends_the_info_windows_stats():
    role = roles(titles, State())
    s = Session()
    s.data.pop("battle")
    c = s.data["char"] = {"id": 1, "class": BERSERKER, "level": 17, "titles": [60417]}
    role.handlers[titles.C2S_WEAR_TITLE](s, pkt(titles.C2S_WEAR_TITLE, struct.pack("<I", 60417)))
    assert c["title"] == 60417 and bytes(s.sent[0].buf) == struct.pack("<hI", 0, 60417)
    block = bytes(next(w for w in s.sent if w.proto == world.S2C_HERO_BLOCK).buf)
    at = world.HERO_STAT_CODED_AT["HP_RECOVERY"]
    assert block[at:at + 4] == world.stat_code(round(hero.char_stats(c)["HP_RECOVERY"]))
    assert round(hero.char_stats(c)["HP_RECOVERY"]) == round(hero.char_stats(dict(c, title=0))["HP_RECOVERY"]) + 3


def test_a_title_worn_in_a_room_reaches_the_rooms_stats():
    st = type("St", (), {"save": lambda self: None, "game_sessions": {}})()
    role = roles(titles, st)
    s, g = Session(), Session()
    s.data.pop("battle")
    c = s.data["char"] = g.data["char"] = {"id": 1, "class": BERSERKER, "level": 17, "titles": [60102]}
    s.data["account"] = g.data["account"] = {"id": 9, "characters": [c]}
    st.game_sessions[9] = g
    g.data["battle"].add_hero(0, 5000)
    g.data["battle"].troops[0]["max"] = round(hero.char_stats(c)["HP_MAX"])
    role.handlers[titles.C2S_WEAR_TITLE](s, pkt(titles.C2S_WEAR_TITLE, struct.pack("<I", 60102)))   # 5102: HP +300
    assert g.data["battle"].troops[0]["max"] == round(hero.char_stats(c)["HP_MAX"])
    assert any(w.proto == combat.S2C_STATS for w in g.sent)


# --- S16 / P1 / P3 (census gap 8): gear, set and title SP in the room's pool ----------------------------------------

DESTROYER = [103100060, 153100030, 153100070]    # GLEN's Order Destroyer set 2201: pistol, top, trousers (3 pieces)


def wearing(cls, level, codes, **more):
    index = {"ACC2": 9}
    return dict({"id": 1, "class": cls, "level": level,
                 "equip": [{"code": code, "serial": i + 1,
                            "index": index.get(items.row(code)["Parts"], items.PARTS.get(items.row(code)["Parts"], 1) - 1)}
                           for i, code in enumerate(codes)]}, **more)


@pytest.mark.parametrize("worn, title, sp_max, sp_rec", [
    ((), None, 200, 3),                                  # the class's %ApSp, as the tape's 200 / 3 per 3 s
    ((203000070,), None, 225, 3),                        # Mana Guide's Holy Resistance Bracelet: SP_MAX 25
    ((105024500,), None, 200, 7),                        # Hero's Dazzling Pistol: SP_RECOVERY 4
    (tuple(DESTROYER), None, 234, 3),                    # set 2201's 3-piece tier: SP_MAX 34
    ((), 60099, 200, 5),                                 # a title with 5112: SP_RECOVERY +2
])
def test_the_rooms_sp_pool_counts_the_heros_gear_sets_and_title(worn, title, sp_max, sp_rec):
    c = wearing(GUNSLINGER, 30, worn, title=title)
    pools = game.pools_for(c, 10234, [{"id": 100}])       # + the conscripted infantry's SP_ADD 700 (tape: 900)
    assert (pools["sp"], pools["sp_max"], pools["sp_rec"]) == (sp_max, sp_max + 700, sp_rec)


# --- G5 / G2 (census gap 10): the sets' "N%." HP and the gear's second block ----------------------------------------

def test_a_set_tier_written_5_percent_raises_the_max_hp_by_5_percent():
    kit = skills.battle_abilities({"id": 1, "class": GUNSLINGER, "level": 30})
    one = hero.stats(0, 30, DESTROYER[:1], abilities=kit)["HP_MAX"]                   # tier 2 needs 2 pieces
    items_hp = sum(v for code in DESTROYER[1:] for n, v, _ in items.traits(code) if n == "HP_MAX")
    full = hero.stats(0, 30, DESTROYER, abilities=kit)["HP_MAX"]
    assert items.set_traits(DESTROYER) == [("HP_MAX", 5.0, True), ("SP_MAX", 34.0, False)]
    assert abs(full - (one + items_hp) * 1.05) < 1e-6


def second_block():
    out = []
    for name in ("item_weapon", "item_defence", "item_accessory"):
        for r in tables.load(name):
            block = [(r[f"TraitType{i}"], float(r[f"Value{i}"])) for i in range(5)
                     if r.get(f"TraitType{i}", "-") not in ("-", "") and r.get(f"Target{i}") == "LEADER"
                     and r.get(f"Operation{i}") == "ADD"]
            if block:
                out.append((int(r["ItemCode"]), block))
    return out


def test_899_wearables_carry_a_second_block_and_it_counts():
    """CHECKABLE G2: every weapon, armour piece and accessory's TraitType / Value block (Target LEADER, ADD) is in its
    traits, beside its BASE_TRAIT block."""
    rows = second_block()
    assert len(rows) == 275 + 590 + 34
    for code, block in rows:
        got = [(n, v) for n, v, _ in items.traits(code)]
        assert all(t in got for t in block)


def test_a_second_block_stat_reaches_the_panel():
    code, block = next((c, b) for c, b in second_block() if any(n == "ACCURACY" for n, _ in b))
    acc = sum(v for n, v, _ in items.traits(code) if n == "ACCURACY")
    assert acc >= sum(v for n, v in block if n == "ACCURACY") > 0
    assert hero.stats(0, 30, [code])["ACCURACY"] - hero.stats(0, 30, [])["ACCURACY"] == acc


def test_every_wearable_parses_including_the_percent_ring():
    for name in ("item_weapon", "item_defence", "item_accessory"):
        for r in tables.load(name):
            items.traits(int(r["ItemCode"]))
    assert ("HP_MAX", 10.0, True) in items.traits(200900027)            # Hero's Ring (Limited-time): "10%"
    base = hero.stats(0, 30, [])["HP_MAX"]
    assert abs(hero.stats(0, 30, [200900027])["HP_MAX"] - base * 1.1) < 1e-6


# --- S12 (census): the town HUD's SP is the pool full ----------------------------------------------------------------

@pytest.mark.parametrize("worn, sp", [((), 200), ((203000070,), 225)])
def test_the_town_block_sends_the_sp_pool_full(worn, sp):
    """Part 9 35:16 (9NwV8ikwLYk f_01059), Accolade, Lv.17: the HUD reads SP 200; ours sent %Contents SP_INIT 150
    (captures/live3_town.png)."""
    b = world.hero_block(wearing(BERSERKER, 17, worn))
    assert struct.unpack_from("<i", b, world.HERO_STAT_AT["SP_CURRENT"])[0] == sp
    assert struct.unpack_from("<i", b, world.HERO_STAT_AT["SP_MAX"])[0] == sp


# --- P12 / P13 / P14 (census gap 3): the class resources -------------------------------------------------------------
# The client spends and fills none of them itself (HERO-CONTROLS.md §3.3; the status functions ATTACK_GAIN_STACK1 / 2
# and HIT_ADD_STACK are empty cases of 0x140ca3570): it shows what 0x5138 sets, Stack1 stat 35 (Player +0x13c), Stack2
# stat 36 (+0x144), FSP stat 99 (+0x160, Helena's rune HUD 0x140690da0).

def room(cls, level=30, **pools):
    s = Session()
    s.data["char"] = {"id": 1, "class": cls, "level": level}
    s.data["battle"].add_hero(0, 5000)
    s.data["battle"].add_np(1, 1000, 5, c=combat.np_combatant(2))
    s.data["pools"] = dict(game.pools_for(s.data["char"]), **pools)
    s.later = lambda delay, f: None
    return s


def stats_sent(s):
    out = {}
    for w in s.sent:
        if w.proto == combat.S2C_STATS:
            b = bytes(w.buf)
            for i in range(b[0]):
                value, sid, _ = struct.unpack_from("<IbH", b, 1 + 7 * i)
                out[sid] = value
    return out


@pytest.mark.parametrize("cls, ability, pools, want", [
    (SPELLSWORD, 350, {"stack2": 6}, {"stack2": 3}),             # Lightning Spin Kick: 3 lightning runes
    (SPELLSWORD, 356, {"ammo": 2, "stack2": 2}, {"ammo": 1, "stack2": 1}),   # Rune Generation: one of each
    (2, 1297, {"stack2": 0}, {"stack2": 1}),                      # the Druid's 1297: STACK2_CURRENT +1, max 1
    (2, 1297, {"stack2": 1}, {"stack2": 1}),
    (HELENA, 1521, {}, {"fsp": 6}),                               # Helena's 1521: FSP_CURRENT +6 (FSP_Max 6)
    (HELENA, 1520, {"fsp": 6}, {"fsp": 6}),                       # 1520: +1, capped
    (HELENA, 1523, {"fsp": 6}, {"fsp": 0}),                       # 1523 costs 6
    (HELENA, 1522, {"fsp": 3}, {"fsp": 2}),                       # 1522 costs 1
])
def test_stack2_and_fsp_are_spent_and_refilled_as_the_ability_rows_say(cls, ability, pools, want):
    s = room(cls, **pools)
    combat.spend(s, ability)
    assert {k: s.data["pools"][k] for k in want} == want
    ids = {"ammo": combat.STAT_AMMO, "stack2": combat.STAT_STACK2, "fsp": combat.STAT_FSP}
    changed = {k for k in want if want[k] != dict(game.pools_for(s.data["char"]), **pools)[k]}
    assert {ids[k]: want[k] for k in changed} == {sid: v for sid, v in stats_sent(s).items() if sid in
                                                   (combat.STAT_AMMO, combat.STAT_STACK2, combat.STAT_FSP)}


def test_helenas_room_has_her_gauge_and_the_others_none():
    assert (game.pools_for({"id": 1, "class": HELENA, "level": 1})["fsp_max"],
            game.pools_for({"id": 1, "class": SPELLSWORD, "level": 1})["fsp_max"]) == (6, 0)


def land(s, attacker=0, target=1):
    combat.apply_hits(s, [(target, [0])], lambda *a: None, attacker=attacker,
                      attack=combat.hit_attack(s.data["battle"].troops[attacker]["c"] or combat.combatant(30)))


def test_the_ice_rune_status_gives_one_rune_on_the_next_landed_hit_and_ends():
    """305 Ice Blade puts 3321 ICE_RUNE (level 1: ATTACK_GAIN_STACK1 1, 1000, 1, 1, True) on the Spellsword for 2 s:
    her next landed hit adds 1 to Stack1 (her ice runes, max 6) and the status is used up (0x5078)."""
    s = room(SPELLSWORD, level=6)
    s.data["battle"].troops[0]["c"] = game.hero_combatant(s.data["char"])
    from kuf2 import status
    status.apply(s, [0], 3321, 1, 0)
    land(s)
    assert s.data["pools"]["ammo"] == 1 and stats_sent(s)[combat.STAT_AMMO] == 1
    assert 3321 not in combat.held_levels(s, 0) and any(w.proto == combat.S2C_STATUS_END for w in s.sent)
    land(s)
    assert s.data["pools"]["ammo"] == 1                              # used up: no second rune


def test_the_lightning_rune_fills_stack2():
    s = room(SPELLSWORD, level=6)
    s.data["battle"].troops[0]["c"] = game.hero_combatant(s.data["char"])
    from kuf2 import status
    status.apply(s, [0], 3322, 1, 0)
    land(s)
    assert s.data["pools"]["stack2"] == 1 and stats_sent(s)[combat.STAT_STACK2] == 1


def test_rampage_adds_fury_on_every_landed_hit_up_to_99():
    """6200 RAMPAGE (the Berserker's 643 passive and his Madness stance; ATTACK_GAIN_STACK1 1, 1000, 1, 100000, False):
    +1 Stack1 a landed hit, held, capped at %ApSp Stack1_Max 99."""
    s = room(BERSERKER, ammo=97)
    s.data["battle"].troops[0]["c"] = game.hero_combatant(s.data["char"])
    from kuf2 import status
    status.apply(s, [0], 6200, 1, 0)
    for _ in range(3):
        land(s)
    assert s.data["pools"]["ammo"] == 99 and 6200 in combat.held_levels(s, 0)


def test_iron_body_adds_fury_when_the_berserker_is_hit():
    """6201 IRON_BODY (737 Iron Wall stance; HIT_ADD_STACK Stack1, 1, 1000, 1) and the 6203 it adds (the same row):
    each gives +1 Stack1 for a hit taken, the data read literally [I]."""
    s = room(BERSERKER, ammo=0)
    s.data["battle"].troops[1]["c"] = combat.np_combatant(2)
    from kuf2 import status
    status.apply(s, [0], 6201, 1, 0)
    assert {6201, 6203} <= set(combat.held_levels(s, 0))
    land(s, attacker=1, target=0)
    assert s.data["pools"]["ammo"] == 2 and stats_sent(s)[combat.STAT_AMMO] == 2


def test_a_miss_or_no_rune_status_gains_nothing():
    s = room(SPELLSWORD, level=6)
    s.data["battle"].troops[0]["c"] = game.hero_combatant(s.data["char"])
    land(s)
    assert s.data["pools"]["ammo"] == 0 and combat.STAT_AMMO not in stats_sent(s)

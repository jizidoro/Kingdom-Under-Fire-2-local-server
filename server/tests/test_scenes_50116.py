"""The prologue Azilia Castle 50116's director table (kuf2/scenes/m50116.py) against the original's order
(planning/scripts/missions/50116.md, playthrough part 1 4:06-15:16): each beat on its trigger (the hero's places, a
lesson's key, a fall, the clock), its scenes with their cast in the room, the class's own rune lesson, and the end:
no result window, the room left for Glen's camp, the character's prologue done."""
import struct

import pytest

from kuf2 import director, game, obf, world
from kuf2.scenes import m50116 as table
from test_battle import FieldSession, NoSave, acts, mission_room, walk
from test_director import cutscenes, lines_shown, obey, press, prompts, queries, run_pending
from test_scenes_10233 import closes, tutorials

SPOT = world.TUTORIAL_SPOT
JAGER, BRENON = 10000, 10001                        # 예거_1 / 브레논_1 (F10000), each speaking as his NP leader
BERSERKER = 4                                       # the tape's hero


def room(cls=BERSERKER, c=None):
    """The prologue's room at its start for a hero of class cls (or the character c), as a new character enters it."""
    s = FieldSession({"active": {}, "done": []})
    if c is not None:
        s.data["account"] = {"characters": [c]}
    s.data.update(spot=SPOT, difficulty=0)
    s.data["char"] = s.data["account"]["characters"][0]
    if c is None:
        s.data["char"]["class"] = cls
    s.data["char"].setdefault("spot", world.NEW_CHAR_SPOT)
    s.data["char"].setdefault("mission", {"spot": SPOT, "back": world.NEW_CHAR_SPOT, "difficulty": 0})
    s.state = NoSave()
    s.data["battle"].add_hero(0, 1000)
    game.spawn_zone_troops(s)
    return s


def ids(s):
    return [line for _, _, line in lines_shown(s)]


def said(s):
    return [(uid, line) for uid, _, line in lines_shown(s)]


def enter(s, key):
    b = director.bound(SPOT, key)
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)


def notices(s):
    return [tuple(i for i in a[2:6] if i != director.NO_TEXT) for a in acts(s, director.ACT_NOTICE_WINDOW)]


def highlights(s):
    return [(a[1], a[3]) for a in acts(s, director.ACT_HIGHLIGHT_AREA)]


def marched(s):
    """{troop: area} of the ActTroopMoveToArea orders sent (the last for each troop)."""
    return {a[2]: a[3] for a in acts(s, director.ACT_MOVE_TO_AREA)}


def area(key):
    return director.bound(SPOT, key)["EventBoundID"]


def fell(s, *uids):
    for u in uids:
        game.mission_troop_down(s, NoSave(), u)
    run_pending(s)


def force(s, f):
    return [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == f]


def opened_props(s):
    """Props a 0x50d1 set open (game.switch_on): {prop id}."""
    from test_battle import opened
    return opened(s)


def up(s):
    """The keys prompted and not pressed yet."""
    return sorted(k for p, k in prompts(s).items() if k and p not in getattr(s, "pressed", set()))


def show(s):
    """The client answers each page asked: it shows (nothing scheduled runs)."""
    from test_director import answer
    for serial, _, _ in queries(s):
        if serial not in getattr(s, "answered", set()):
            s.answered = getattr(s, "answered", set()) | {serial}
            answer(s, serial, True)


def act(s):
    """The player does what the lessons ask now, once: each page asked shows, each key prompted is pressed; nothing
    scheduled runs."""
    show(s)
    for k in up(s):
        press(s, k)


def until(s, done, limit=400):
    """Run the room's timers one by one, the player doing what is asked whenever nothing is due, until done(s)."""
    for _ in range(limit):
        if done(s):
            return
        if s.pending:
            s.pending.sort(key=lambda p: p[0])
            s.pending.pop(0)[1]()
        else:
            act(s)
    raise AssertionError("never came")


def to_outside(s):
    obey(s)
    enter(s, table.TUTORIAL_CLOSE)
    enter(s, table.GATE_CROWD)
    enter(s, table.OUTSIDE)


def to_battlements(s):
    to_outside(s)
    obey(s)                                         # V, the left and right buttons, a skill key, F
    run_pending(s)                                  # the far view, the retreat, Brenon's orders
    enter(s, table.BATTLEMENTS)


def to_street(s):
    to_battlements(s)
    enter(s, table.QTE)
    obey(s)                                         # Space, Shift
    fell(s, table.COLOSSUS)
    enter(s, table.NE_STREET)


def to_town(s):
    to_street(s)
    obey(s)                                         # the rune lesson's key
    run_pending(s)                                  # the gate's clock, the reinforcements, "go to the Palace"
    enter(s, table.TOWN)


def play(s):
    """The prologue as the player plays it, to its end."""
    to_town(s)
    fell(s, 21000, 21031)
    enter(s, table.STAIRS)
    enter(s, table.YARD)
    fell(s, table.TYRANT)
    enter(s, table.END)
    run_pending(s)


def test_the_prologue_opens_with_the_move_lesson_and_the_panel_in_direct_control():
    # 4:07: "Move to the marked location." (MoveToArea, W A S D) over the panel (640 / 650-680: "Protect Azilia
    # Castle", "Let Hero die"), the first mark ahead; the hero walks (no troop of his yet: the archers come with Brenon)
    s = room()
    assert tutorials(s) == ["MoveToArea"] and lines_shown(s) == []
    assert [a[-1] for a in acts(s, game.ACT_SITUATION_LINE)] == [660, 680]
    assert highlights(s) == [(area(table.TUTORIAL_CLOSE), 1)]
    assert game.start_control_mode(SPOT) == 1
    assert s.data["plan"]["hand"] == () and table.ARCHERS in s.data["zone_troops"]
    # Jager and the courtyard's soldiers run ahead to the gate (0_Azilia_Invasion's own moves)
    m = marched(s)
    assert m[JAGER] == 30023 and {m[u] for u in force(s, 10005) + force(s, 10006)} == {area("Phase1_Troop_Actor1")}
    assert BRENON not in m


def test_the_first_mark_completes_the_card_and_jager_points_the_hero_to_the_gate():
    # 4:15.1-4:22.5: the mark reached, the card completes (one page: 0xc898, its circle), goes 1 s later (0xc897:
    # live 2026-10-24 a completed card stayed up to the gate), Jager's 10010, the next mark
    s = room()
    enter(s, table.TUTORIAL_CLOSE)                  # before the card shows: remembered, then fired
    obey(s)
    run_pending(s)
    assert closes(s) == [director.ACT_COMPLETE_TUTORIAL, director.ACT_FINISH_TUTORIAL] and said(s) == [(JAGER, 10010)]
    sent = [struct.unpack_from("<I", bytes(w.buf))[0] for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION]
    assert sent.index(director.ACT_FINISH_TUTORIAL) < sent.index(director.ACT_HELP_TEXT_BY_TROOP)
    assert highlights(s)[-2:] == [(area(table.TUTORIAL_CLOSE), 0), (area(table.GATE_CROWD), 1)]


def test_a_strip_crossed_between_two_position_reports_counts():
    # the courtyard's strip is 400 deep: a running hero (~800 units / 1.5 s report) is reported before and after it
    s = room()
    obey(s)
    walk(s, 149600, 189800)                         # north of Area_Tutorial_Close (z 188845-189245)
    assert 10010 not in ids(s)
    walk(s, 149600, 188600)                         # 1.2 k on: south of it
    run_pending(s)
    assert ids(s) == [10010]


def test_the_gate_opens_on_jagers_order_and_the_fight_outside_comes_in():
    # 4:31.5-4:44: the ring among the soldiers, "Open the gate! Now!", the gate, "Right then, let's fight!", the walls'
    # allies and the primitives (F10010 / F10011, F20000 / F20010) at the gate, everyone out with the hero
    s = room()
    obey(s)
    enter(s, table.TUTORIAL_CLOSE)
    walk(s, 149755, 179000)                         # by the gate before the order: it stays shut (HOLD_PROPS)
    assert not {10003, 10007} & opened_props(s)
    assert not force(s, 20010)
    enter(s, table.GATE_CROWD)
    assert ids(s) == [10010, 10020, 10030] and {10003, 10007} <= opened_props(s)
    assert force(s, 20010) and force(s, 20000) and force(s, 10010) and force(s, 10011)
    m = marched(s)
    assert {m[u] for u in force(s, 20000)} == {area(table.OUTSIDE)} and m[JAGER] == area(table.OUTSIDE)
    # F20010 stays in its pairs with the allies along the wall (138-162 k): marched at the gate, its 21 troops came
    # down on the hero (live 2026-10-24: two of them 2-3 hits a second; the tape's hero takes three small ones a minute)
    assert not set(force(s, 20010)) & set(m)


def test_the_lessons_outside_close_one_by_one_on_their_keys():
    # 4:44-5:27.5: 10050 + Enemy Identification (V), 10070 + Basic Attack (the left button), 10080 + Special Attack
    # (the right button), 10090 + the skill slots (1-8), each completed (one page) on its key; then 10500 and "Press F
    # to check!" with the F prompt
    s = room()
    obey(s)
    enter(s, table.TUTORIAL_CLOSE)
    enter(s, table.GATE_CROWD)
    enter(s, table.OUTSIDE)
    run_pending(s)
    assert tutorials(s)[-1] == "Command_V" and ids(s)[-1] == 10050
    for name, keys, line in (("Command_V", (director.KEY_FRIEND_AND_FOE,), 10070),
                             ("BaseAttack", (director.KEY_PAD_A,), 10080),
                             ("SubAttack", (director.KEY_PAD_X,), 10090),
                             ("UseSkill", director.KEY_SKILL_SLOTS, 10500)):
        until(s, lambda s, name=name: tutorials(s)[-1] == name)
        show(s)                                     # the page shows: its key is prompted
        assert up(s) == sorted(keys) and line not in ids(s)
        press(s, keys[-1])
        assert closes(s)[-1] == director.ACT_COMPLETE_TUTORIAL          # its circle
        until(s, lambda s: closes(s)[-1] == director.ACT_FINISH_TUTORIAL)
        assert line not in ids(s)                   # the card goes first (the tape: a quarter second before the line;
        until(s, lambda s, line=line: line in ids(s))   # 10500 comes later)
    until(s, lambda s: 10100 in ids(s))
    assert ids(s)[-2:] == [10500, 10100] and up(s) == [director.KEY_ACTION] and cutscenes(s) == []
    press(s, director.KEY_ACTION)                   # F: the far view, once the line has played
    until(s, lambda s: cutscenes(s))
    assert cutscenes(s) == [20]
    assert tutorials(s) == ["MoveToArea", "Command_V", "BaseAttack", "SubAttack", "UseSkill"]


def test_f_shows_the_far_view_then_the_retreat_plays_with_its_cast():
    # 5:32 F: the far view (20_AziliaCastle_Action_Cam1, 6 s, HUD up), the fight 7 s more, then the retreat
    # 2_Azilia_fallback (33 s) with "Enter the castle."; its SCRIPT enables F19100 / F19200 / F19300 / F39100 (in the
    # room before it plays) and, at its end, F19600 / F10015, which come in then
    s = room()
    to_outside(s)
    until(s, lambda s: cutscenes(s) == [20])
    assert min(d for d, _ in s.pending) >= 6 + 7 - 0.01
    seen = []
    send = game.send_actions

    def spy(room, *actions):
        seen.extend((a[1], set(room.data["zone_troops"])) for a in actions if a[0] == director.ACT_CUTSCENE)
        return send(room, *actions)
    game.send_actions = spy
    try:
        run_pending(s)
    finally:
        game.send_actions = send
    slot, here = seen[0]
    assert slot == 2 and {u for f in (19100, 19200, 19300, 39100) for u in force(s, f)} <= here
    assert not set(force(s, 19600)) & here and force(s, 19600)
    assert (5050,) in notices(s) and ids(s)[-2:] == [10120, 10130]
    assert notices(s)[-1] == (5060, 5061) and highlights(s)[-1] == (area(table.BATTLEMENTS), 1)
    assert table.ARCHERS in s.data["plan"]["hand"]  # "take the archers to the battlements"
    assert marched(s)[JAGER] == area(table.SPEARMEN)     # "Jager, take the northeast gate!"


def test_the_battlements_play_the_fire_arrow_scene_then_the_walk_to_the_colossus():
    # 6:41: 23_LEV_Azilia_FireArrowAttack (its own 10140-10200: the table says none of them) with the colossus in the
    # room; at its end (7:25) the red areas / Charge notice and the mark along the walkway
    s = room()
    to_battlements(s)
    assert cutscenes(s)[-1] == 23 and table.COLOSSUS in s.data["zone_troops"]
    assert not {10140, 10150, 10170, 10180, 10190, 10200} & set(ids(s))
    assert notices(s)[-1] == (5040, 5031) and highlights(s)[-1] == (area(table.QTE), 1)


def test_the_colossus_lessons_then_its_fall_breach_the_north_east_gate():
    # 7:47.5-8:57: Escape (Groggy: its page, then Space) and Block (Defence: its page, then Shift), each closed on its
    # key; 5030 / 5031 and "Attack it's arms!"; the colossus down: 10240, 10250, the green line to the street, the
    # north-east gate broken and its attackers in, 10260 / 10270
    s = room()
    to_battlements(s)
    enter(s, table.QTE)
    assert tutorials(s)[-1] == "Groggy"
    obey(s)
    assert tutorials(s)[-2:] == ["Groggy", "Defence"] and closes(s)[-2:] == [director.ACT_FINISH_TUTORIAL] * 2
    assert notices(s)[-1] == (5030, 5031) and ids(s)[-1] == 10230
    assert 10004 not in opened_props(s) and not force(s, 20450)
    fell(s, table.COLOSSUS)
    assert ids(s)[-4:] == [10240, 10250, 10260, 10270]
    assert said(s)[-4][0] == table.WALL_SOLDIER
    assert 10004 in opened_props(s) and force(s, 20450) and force(s, 11150)
    assert marched(s)[force(s, 20450)[0]] == area(table.NE_GATE_IN)
    assert highlights(s)[-1] == (area(table.NE_STREET), 1)


def test_the_colossus_falling_early_waits_for_the_lessons():
    s = room()
    to_battlements(s)
    fell(s, table.COLOSSUS)                         # before the walkway's lessons
    assert 10240 not in ids(s)
    enter(s, table.QTE)
    obey(s)
    assert 10240 in ids(s) and ids(s).index(10230) < ids(s).index(10240)


@pytest.mark.parametrize("cls, lessons", [(0, ["Rune_Skill_Glen"]),
                                          (1, ["Rune_Skill_Olivia", "ChargeShot_Olivia"]),
                                          (2, ["111_Summon_Skill_Druid", "111_Rune_Skill_Druid"]),
                                          (3, ["Rune_Skill_Isabella"]), (4, ["Rune_Skill_Regnier"]), (5, [])])
def test_each_class_gets_its_own_rune_lesson_and_then_the_gate_is_held(cls, lessons):
    # 9:02-9:14: the class's rune scene's pop-ups (8 / 14 / 21 / 10 / 12_Azilia_*_R), each closed on the key it waited
    # for; no other class's; then Jager's 10280. The Sorceress has none here
    s = room(cls)
    to_street(s)
    obey(s)
    run_pending(s)
    shown = [t for t in tutorials(s) if t.startswith(("Rune_", "ChargeShot", "111_"))]
    assert shown == lessons
    assert 10280 in ids(s)
    if cls == 1:                                    # the one-page ChargeShot_Olivia: its circle, then it goes
        assert closes(s)[-3:] == [director.ACT_FINISH_TUTORIAL, director.ACT_COMPLETE_TUTORIAL,
                                  director.ACT_FINISH_TUTORIAL]


def test_the_berserkers_lesson_waits_for_its_page_then_r():
    s = room()
    to_street(s)
    run_pending(s)
    assert tutorials(s)[-1] == "Rune_Skill_Regnier"
    asked = [q for q in queries(s) if q[1] == director.COND_TUTORIAL_PAST and q[2].startswith(b"Rune_Skill_Regnier")]
    assert asked and asked[-1][2].endswith(struct.pack("<I", 4))     # past page 4 (1275 "Let me give you ...")
    assert 10280 not in ids(s) and up(s) == []      # no key before its page
    show(s)
    assert up(s) == [director.KEY_RUNE]
    run_pending(s)
    assert 10280 not in ids(s)                      # the gate's defence waits for R
    press(s, director.KEY_RUNE)
    run_pending(s)
    assert closes(s)[-1] == director.ACT_FINISH_TUTORIAL and 10280 in ids(s)


def test_the_gate_holds_for_its_clock_then_the_reinforcements_and_the_way_to_the_palace():
    # 9:14-9:51: "Protect the Castle Gate" with its 00:00:20 clock, 5000 / 5001, the rest of the attack; at 0 the
    # reinforcements (F11160), 10290 by a spearman, 5070 / 5071; Jager's 10305
    s = room()
    to_street(s)
    until(s, lambda s: acts(s, 0xc80a))             # the lesson's key, Jager's line, the clock's first second
    assert ids(s)[-1] == 10280 and acts(s, 0xc80a)[0][2:] == [690, 700, table.HOLD_S]
    assert [a[2] for a in acts(s, game.ACT_SITUATION_GROUP)][-1] == 690
    assert not force(s, 11160) and force(s, 20400) and force(s, 20220) and force(s, 23000)
    run_pending(s)
    assert [a[-1] for a in acts(s, 0xc80a)] == list(range(table.HOLD_S, -1, -1)) + [0]     # + the stop's 00:00:00
    assert force(s, 11160) and said(s)[-2:] == [(table.SPEARMAN, 10290), (JAGER, 10305)]
    assert notices(s)[-2:] == [(5000, 5001), (5070, 5071)]
    # "Protect the Castle Gate" leaves the panel with the reinforcements (the tape: 00:00:00 from 9:35.1, the line
    # gone 9:39.9, the heading 9:40.9; live 2026-10-24 it stayed at 00:00:00 into the town)
    from kuf2 import rules
    assert [a[2:] for a in acts(s, rules.ACT_SITUATION_REMOVE_GROUP)] == [[690]]
    assert marched(s)[force(s, 11160)[0]] == area(table.SPEARMEN)


def test_the_town_marks_its_leaders_red_and_their_fall_sends_the_hero_to_the_palace():
    # 10:06-10:47: 5020 / 5021 and the red markers on F21000's leaders, 10360 at the first's fall, 10380 at the
    # Dainargate Commander's, the mark toward the palace stairs
    s = room()
    to_town(s)
    assert notices(s)[-1] == (5020, 5021) and force(s, 21000)
    marks = acts(s, director.ACT_HIGHLIGHT_TROOP)
    assert [(a[1], a[3]) for a in marks] == [(21000, 1), (21031, 1)]
    fell(s, 21000)
    assert said(s)[-1] == (table.SAVED, 10360) and 10380 not in ids(s)
    fell(s, 21031)
    assert said(s)[-1] == (table.SAVED2, 10380) and highlights(s)[-1] == (table.STAIRS, 1)


def test_the_palace_celes_the_tyrant_and_the_kings_end_win_with_no_window_for_glens_camp():
    # 10:54-15:16: 3_Azilia_CELLES at the stairs (the yard manned first), the tyrant at the yard, the wounded
    # infantryman's 10330 at the yard's end, 4_Azilia_destroy, 5_Azilia_destroy, then no result window: the room is
    # left for Glen's camp (0x4041 to 10352) and the character's prologue is done
    s = room()
    play(s)
    assert cutscenes(s)[-3:] == [3, 4, 5] and said(s)[-1] == (table.WOUNDED, 10330)
    assert s.data.get("mission_won") and not [w for w in s.sent if w.proto == game.S2C_MISSION_COMPLETE]
    leave = [bytes(w.buf) for w in s.sent if w.proto == game.S2C_MISSION_LEAVE]
    assert len(leave) == 1 and obf.dec_u32(leave[0][4:8]) == world.NEW_CHAR_SPOT
    c = s.data["char"]
    assert c["tutorial_done"] is True and c["spot"] == world.NEW_CHAR_SPOT and "mission" not in c
    assert str(SPOT) in c.get("cleared", {})


def test_the_scenes_play_in_the_tapes_order():
    s = room()
    play(s)
    assert cutscenes(s) == [20, 2, 23, 3, 4, 5]


def test_the_hero_cannot_die_and_the_knights_heal_him():
    # "YOU WONT DIE even if you do die", "you will just get Full Healed by Azillian Knights" (the walkthrough)
    s = room()
    assert SPOT in game.UNDYING_MISSIONS
    director.on_hp(s, 0, 100, 1000)
    run_pending(s)
    assert ids(s)[-1] == 10400


def test_the_original_events_all_show_in_the_tapes_order_but_the_two_late_reads():
    # tools/playthrough.py's measure for this room: the 55 scripted events of the tape (planning/playthrough/
    # initial.json) all shown; in order but one: the notice 5040 / 5031 (title and text in one window, one frame:
    # 7:21.4; read 7:22 / 7:24 the other way round). The panel's 660 (read at 4:20) is retimed by its frame (4:05.9,
    # playthrough.FRAMES, build/order-c)
    import json, pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    import sys
    sys.path.insert(0, str(root / "tools"))
    playthrough = pytest.importorskip("playthrough", reason="tools/playthrough.py (not published) reads the footage")
    want = [c["id"] for c in json.loads((root / "planning/playthrough/initial.json").read_text(encoding="utf-8"))
            if c.get("spot") == SPOT and c["kind"] in ("line", "cutscene", "tutorial", "objective", "notice")]
    got = [i for _, i in playthrough.headless(SPOT)]
    assert len(want) == 55 and set(want) <= set(got)
    assert playthrough.lcs(want, got) == 54

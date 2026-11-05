"""Troop Training Camp (Controls) 10331: the director's table (kuf2/scenes/m10331.py) in a mission room. No footage:
the lessons against the map's own lesson cutscene 1_Tab (planning/scripts/cutscenes.json), its pop-ups in its order,
each on the page and the key its script waited for."""
import struct

from kuf2 import director, game
from test_battle import NoSave, acts, mission_room, walk
from test_director import answer, lines_shown, press, prompts, queries, run_pending
from test_scenes_10233 import closes, tutorials
from test_scenes_10345 import handed, panel, said

SANCHEZ, JAGER = 14000, 14001
# 1_Tab: (the pop-up, CheckCompleteTutorialSub's page, the key System_CheckInputEvent waited for; InputEvent values)
TAB = (("Select_Mode_1", 1, 0x30), ("Select_TroopSlot1_Enter_1", 2, 0x35), ("Command_X_1", 2, 0x39),
       ("Command_C_1", 1, 0x3a), ("Command_Z_1", 1, 0x38), ("Select_TroopSlot2_Enter_1", 0, 0x36),
       ("Select_TroopSlot1_Move_1", 0, 0x84), ("Select_TroopSlot3_Enter", 0, 0x37), ("Test1", 1, 0x15),
       ("TroopSkill_Short_Cut1", 1, 0x23), ("Select_AllTroop", 1, 0x33))


def lesson(s, name, page, key):
    """Show the pop-up's pages (the client says page past `page` when asked), then press its key."""
    run_pending(s)
    assert tutorials(s)[-1] == name
    serial, cond, args = queries(s)[-1]
    assert cond == director.COND_TUTORIAL_PAST and args == name.encode() + b"\0" + struct.pack("<i", page)
    answer(s, serial, True)
    assert key in prompts(s).values()
    shut = len(closes(s))
    press(s, key)
    assert closes(s)[shut:] == [director.ACT_FINISH_TUTORIAL]


def test_the_controls_camp_hands_the_three_troops_its_lessons_command():
    # 1_Tab selects troop slots 1, 2, 3 (F1-F3); PC_Troop_1-3, not G5's four (PC_Troop_4 is an ally of the mock battle)
    s = mission_room(10331)
    assert sorted(handed(s)) == [11000, 11104, 11107] and 11108 not in s.data["zone_troops"]
    assert not {21000, 22000} & {t.get("ForceNum") for t in s.data["zone_troops"].values()}
    assert director.start_panel(10331) == (500700, ((500710, (500720, 500721)), (500730, (500740,))))


def test_the_lessons_come_in_1_tabs_order_each_on_its_key():
    s = mission_room(10331)
    for name, page, key in TAB:
        lesson(s, name, page, key)
    run_pending(s)
    assert tutorials(s) == [name for name, _, _ in TAB]
    assert said(s) == [510000, 510010, 510020, 511000, 511010, 511020, 511021, 511030, 511031, 511040, 511041,
                       511042, 511050, 511051, 511060, 511061, 511062]
    assert {uid for uid, _, line in lines_shown(s) if line == 511050} == {JAGER}
    assert {uid for uid, _, line in lines_shown(s) if line != 511050} == {SANCHEZ}
    assert panel(s)[1] == [500720]
    b = director.bound(10331, "유저이동지역")
    assert [a[1:] for a in acts(s, director.ACT_DIRECTION_TO_AREA)][-1] == [b["EventBoundID"], director.POINT_S]


def test_a_lesson_waits_for_its_own_key():
    # Select_Mode_1's key is Tab: the pop-up stays up and the next lesson waits through F1, X, Z
    s = mission_room(10331)
    run_pending(s)
    serial, _, _ = queries(s)[-1]
    answer(s, serial, True)
    for key in (0x35, 0x39, 0x38):
        press(s, key)
    run_pending(s)
    assert closes(s) == [] and tutorials(s) == ["Select_Mode_1"]


def test_the_mock_battle_comes_at_the_highlighted_place_and_the_camp_is_won_after_i_lost():
    s = mission_room(10331)
    s.state = NoSave()
    for name, page, key in TAB:
        lesson(s, name, page, key)
    run_pending(s)
    b = director.bound(10331, "유저이동지역")
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)
    assert said(s)[-2:] == [511070, 511071]
    assert {21000, 22000} <= {t.get("ForceNum") for t in s.data["zone_troops"].values()}
    for _ in range(3):
        for u in [u for u, t in s.data["zone_troops"].items() if game.hostile(t) and u not in s.data.get("down", ())]:
            game.mission_troop_down(s, NoSave(), u)
        run_pending(s)
    assert s.data.get("mission_won") and said(s)[-1] == 511100 and panel(s)[1][-1] == 500721

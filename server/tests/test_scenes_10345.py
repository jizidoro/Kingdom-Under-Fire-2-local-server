"""Training Camp (Archer) 10345: the director's table (kuf2/scenes/m10345.py) in a mission room, against the original's
run (playthrough part 4 25:20-30:04; the frames read in the table's docstring)."""
from kuf2 import combat, director, game
from test_battle import NoSave, acts, mission_room
from test_director import lines_shown, obey, press, prompts, run_pending, shown

JAGER, ARCHER, MOCK = 10148, 10087, (10153, 10154, 10155)
TARGET, MELEE, WING, WINGS = 10117, (10104, 10115, 10116), 10123, 10135
ALLIES = (10118, 10119, 10120, 10121)
RIGHT = director.KEY_RIGHT_ORDER


def said(s):
    return [line for _, _, line in lines_shown(s)]


def handed(s):
    return [a[2] for a in acts(s, game.ACT_CHANGE_FORCE)]


def panel(s):
    """The panel lines the steps added (group, line; the table's PANEL left out) and the conditions completed, in
    order."""
    start = {(g, line) for g, lines in (director.start_panel(s.data["spot"]) or (None, ()))[1] for line in lines}
    return ([tuple(a[2:4]) for a in acts(s, game.ACT_SITUATION_LINE) if tuple(a[2:4]) not in start],
            [a[2] for a in acts(s, game.ACT_SITUATION_DONE)])


def notices(s):
    return [tuple(i for i in a[2:6] if i != director.NO_TEXT) for a in acts(s, director.ACT_NOTICE_WINDOW)]


def left(s):
    return [a[2] for a in acts(s, game.ACT_ENABLE_TROOP) if a[3] == 0]


def hit(s, target, attacker):
    """A hit on every unit of target by attacker (combat.apply_hits: the director hears who struck)."""
    t = s.data["battle"].troops[target]
    combat.apply_hits(s, [(target, list(range(len(t["units"]))))], game.send_troop_hp, attacker=attacker,
                      attack={"pr": 1.0, "ar": 1.0})


def down(s, *uids):
    for u in uids:
        game.mission_troop_down(s, NoSave(), u)
    run_pending(s)


def to_the_mock_battle(s):
    """The lessons as the original's player did them: the archer's hit, the Bomber Wing down, the move away, every
    enemy of the lesson down."""
    run_pending(s)
    hit(s, TARGET, ARCHER)
    run_pending(s)
    down(s, WING)
    obey(s)                                             # the move order (the right button)
    down(s, TARGET, *MELEE, WINGS)


def test_the_archer_lesson_opens_on_one_archer_and_the_melee_in_front_of_it():
    # 25:38-25:44: F1 alone, the Elf Archer Unit 13,700 hp (20 x 685); four blue and four red banners locked in melee
    # across the river, the zone's only active enemy (10117) highlighted; Jager on the dais speaks
    s = mission_room(10345)
    troops = s.data["zone_troops"]
    assert handed(s) == [ARCHER] and s.data["battle"].troops[ARCHER]["max"] == 13700
    assert {TARGET, *MELEE, *ALLIES, JAGER} <= set(troops)
    assert not {WING, WINGS, *MOCK} & set(troops)                 # the Bomber Wings and the mock battle wait
    assert not {t.get("ForceNum") for t in troops.values()} & {30000, 30010, 30020, 12000}
    run_pending(s)
    assert lines_shown(s) == [(JAGER, 1, 20001), (JAGER, 1, 20002)] and notices(s) == [(12080, 12081)]
    assert game.mission_text(10345) != director.start_panel(10345) == (30000, ((30010, (30090,)), (30020, (30050,))))


def test_the_panel_comes_as_the_hud_returns_after_the_opening_line():
    # the tape (part 4, frames 2026-10-24): "Let's learn about the Archer" (20001) over the opening camera on the
    # archers (25:24-25:31, no HUD), black, then the HUD fades in with the whole panel (25:32.9: "Archer Training Camp",
    # "Basic Ranged Attack", "Let your Infantry Troop be eliminated"), Jager's 20002 (25:33.4) and the notice (25:33.9)
    s = mission_room(10345)
    assert not [x for x in shown(s) if x[0] in ("title", "group", "panel")]
    run_pending(s)
    seen = shown(s)
    order = [("line", 20001), ("title", 30000), ("panel", 30090), ("panel", 30050), ("line", 20002),
             ("notice", director.NOTICE_LEFT, (12080, 12081))]
    assert [x for x in seen if x in order] == order


def test_the_first_lesson_waits_for_the_archers_own_hit_on_the_highlighted_troop():
    # "Attack the highlighted enemy Troop from a distance": the allied infantry fighting it (25:38) is not the lesson;
    # the archer's hit is (25:44 "That's good"), then the Bomber Wing (25:50)
    s = mission_room(10345)
    run_pending(s)
    hit(s, TARGET, ALLIES[3])
    run_pending(s)
    assert 12413 not in said(s) and WING not in s.data["zone_troops"]
    hit(s, TARGET, ARCHER)
    run_pending(s)
    assert said(s)[2:] == [12413, 12414, 20004] and WING in s.data["zone_troops"]
    assert panel(s) == ([(30010, 30100)], [30090]) and notices(s)[-1] == (12088, 12089)


def test_the_highlighted_troop_felled_by_another_still_moves_the_lesson_on():
    s = mission_room(10345)
    run_pending(s)
    down(s, TARGET)
    assert 12413 in said(s)


def test_the_enemy_infantry_charge_the_archer_and_the_move_away_is_the_players_order():
    # 26:14-26:42: the Bomber Wing down, what to avoid, "Here come the enemy Infantrymen!" (they come at the archer),
    # "Move them over there."; the player's right-button order, then "Good! Now that they're far away" (26:50), the
    # second Bomber Wing and "Defeat all the enemies" (26:58)
    s = mission_room(10345)
    run_pending(s)
    hit(s, TARGET, ARCHER)
    run_pending(s)
    s.sent.clear()
    down(s, WING)
    assert said(s) == [20005, 12416, 12417, 12418, 12419]
    marched = {a[2] for a in acts(s, director.ACT_MOVE_TO_AREA)}
    assert marched == {TARGET, *MELEE}                            # all of F20009 standing, to the archer's start
    assert set(prompts(s).values()) >= set(RIGHT) and WINGS not in s.data["zone_troops"]
    press(s, RIGHT[0])
    run_pending(s)
    assert said(s)[-3:] == [12420, 12424, 20003] and WINGS in s.data["zone_troops"]
    assert panel(s) == ([(30010, 30110), (30010, 30120)], [30100, 30110]) and notices(s) == [(12020, 12022)]


def test_move_to_safety_joins_the_panel_as_jager_says_archers_can_stand_some_melee():
    # the panel (frames of part 4 26:12-26:52, every 4 s): "Bomber Wing Attacks (Complete)" by 26:16, "Move to a place
    # of safety" first at 26:36, with 12418 "Archers are not completely helpless ..." (26:34), not with 20005 (26:14)
    import struct
    s = mission_room(10345)
    run_pending(s)
    hit(s, TARGET, ARCHER)
    run_pending(s)
    s.sent.clear()
    down(s, WING)
    seq = []
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto != game.S2C_SCRIPT_ACTION:
            continue
        act = struct.unpack_from("<I", b)[0]
        if act == director.ACT_HELP_TEXT_BY_TROOP:
            seq.append(struct.unpack_from("<6I", b)[4])
        elif act == game.ACT_SITUATION_LINE:
            seq.append(("panel", struct.unpack_from("<4I", b)[3]))
    assert seq.index(12417) < seq.index(("panel", 30110)) < seq.index(12418)


def test_the_mock_battle_swaps_the_lesson_archer_for_the_three_and_brings_jagers_army():
    # 28:12-28:44: every enemy of the lesson down; the HUD then shows F1-F3 13,700 hp each and no lesson archer
    s = mission_room(10345)
    to_the_mock_battle(s)
    troops = s.data["zone_troops"]
    assert handed(s) == [ARCHER, *MOCK] and left(s) == [ARCHER] and s.data["plan"]["hand"][-3:] == MOCK
    assert all(s.data["battle"].troops[u]["max"] == 13700 for u in MOCK)
    assert {30000, 30010, 30020, 12000} <= {t.get("ForceNum") for t in troops.values()}
    assert said(s)[-5:] == [20011, 20000, 20010, 20020, 20130]
    assert (30010, 30040) in panel(s)[0] and notices(s)[-1] == (21000, 12022)
    assert not s.data.get("mission_won")


def test_your_infantry_troop_bar_follows_the_allied_infantry_from_the_mock_battle():
    # the tape: the HUD back after the mock battle's camera (28:37.4-28:37.6) shows "Win a mock battle with Jager" in
    # the panel and the "Your Infantry Troop" bar under the quest tracker (30070), with Jager's "Now everyone, attack!"
    # (20020) and the notice; the bar sinks slowly to ~80 % by 29:12 (the troops' hp summed: the force's bar, 0xc8b4
    # kind 2, over the allied infantry F12000, six troops; ours: which force, the only allied infantry there)
    s = mission_room(10345)
    to_the_mock_battle(s)
    seen = shown(s)
    infantry = sorted(u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 12000)
    bar = ("bar", 30070, game.TROOPS_BAR_FORCE, 12000, infantry[0])
    assert [x for x in seen if x[0] == "bar"] == [bar]
    assert seen.index(("line", 20010)) < seen.index(("panel", 30040)) < seen.index(bar) < seen.index(("line", 20020))


def test_the_camp_is_won_when_jagers_army_is_down_after_his_i_lost():
    s = mission_room(10345)
    s.state = NoSave()
    to_the_mock_battle(s)
    for _ in range(3):
        down(s, *[u for u, t in s.data["zone_troops"].items() if game.hostile(t) and u not in s.data.get("down", ())])
    assert s.data.get("mission_won") and sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1
    assert said(s)[-1] == 20050 and panel(s)[1][-1] == 30040


def test_the_lesson_is_not_won_before_the_mock_battle():
    # every enemy the room holds is the table's (HOLD): the lesson's last fall brings nothing by the wave rule
    s = mission_room(10345)
    run_pending(s)
    down(s, *MELEE)
    assert not s.data.get("mission_won") and WING not in s.data["zone_troops"]
    down(s, TARGET)                                     # the highlighted troop's fall moves the lesson on (the Wing)
    assert not s.data.get("mission_won") and WING in s.data["zone_troops"]
    assert not {30000, 30010, 30020} & {t.get("ForceNum") for t in s.data["zone_troops"].values()}

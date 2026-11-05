"""Tower of Moonlight 10233's scenes (kuf2/scenes/m10233.py)."""
import struct

from kuf2 import director, game, obf
from test_battle import NoSave, acts, down_all, mission_room, opened, walk
from test_director import answer, cutscenes, lines_shown, obey, press, prompts, queries, run_pending

GLEN, THOMPSON, SCOUT, ARCHERS = 10000, 10001, 10100, 11006
HILLTOP = 10100                                   # the bound where 8_TowerFound stages the party
TOWER_SEEN, RUINS, SCOUTING = (67095, 70662), (61351, 75388), (54510, 82564)   # 18020, 18021, 18023 (strips)
SUPPORT = (55464, 81397)                          # 18022, the third marked place (a 1.3 k square in 18023's strip)
CLEARING = 13011                                  # 가두기_윙드웜, the winged wyrms' clearing


def line_ids(s):
    return [line for _, _, line in lines_shown(s)]


def test_the_tower_opens_with_the_halt_and_the_scouting_orders():
    # 0_StartScene (35 s) voices "Everyone, halt!" ... (10100-10140); then Glen's strategy-mode lessons
    s = mission_room(10233)
    assert cutscenes(s) == [0] and lines_shown(s) == []
    run_pending(s)
    assert lines_shown(s) == [(THOMPSON, 1, 1000)]      # the first lesson waits for the player
    obey(s)
    assert lines_shown(s)[:5] == [(THOMPSON, 1, 1000), (THOMPSON, 1, 1010), (THOMPSON, 1, 1020),
                                  (SCOUT, 0, 1030), (THOMPSON, 1, 1040)]   # 1030 is the player's troop (6:22)


def test_the_panel_opens_under_the_missions_own_title():
    # the original's panel heads its conditions with the mission's name on the red bar, "Tower of Moonlight" (100;
    # frames of part 2 5:14, 8:40, 16:04, 19:46), above "Mission Success Conditions" / "Find the Tower of Moonlight"
    s = mission_room(10233)
    assert acts(s, game.ACT_SITUATION_TITLE) == [[game.ACT_SITUATION_TITLE, game.ALL_TEAMS, 100]]
    assert [a[2:] for a in acts(s, game.ACT_SITUATION_LINE)] == [[110, 120], [140, 150]]


def marched(s):
    return [a[2] for a in acts(s, director.ACT_MOVE_TO_AREA)]


def test_nobody_leaves_during_the_start_scene_and_the_lessons():
    # live 2026-09-28 23:52: the replay's hero walked into 18020 10 s into 0_StartScene, and the table told the tower
    # line and marched Glen, Thompson and the main forces off in the middle of the scene. The original: everyone
    # stands through the lessons (5:02-6:22); only Thompson goes with the hero (10130), after "Follow the Captain!"
    s = mission_room(10233)
    walk(s, *TOWER_SEEN)
    assert marched(s) == [] and lines_shown(s) == []
    shown = lines_shown
    while 1040 not in [line for _, _, line in shown(s)]:
        if not s.pending:                             # the lessons wait for the player: he does what they ask
            sent = len(s.sent)
            obey(s, rounds=1)
            assert s.pending or len(s.sent) > sent, "the lessons asked nothing more"
            continue
        s.pending.sort(key=lambda p: p[0])
        s.pending.pop(0)[1]()
        assert 1050 not in [line for _, _, line in shown(s)] or 1030 in [line for _, _, line in shown(s)]
    assert marched(s) == [THOMPSON]                   # to 18020, once the scouts are told
    run_pending(s)
    assert line_ids(s)[:5] == [1000, 1010, 1020, 1030, 1040]


def notices(s):
    """The (title, text) of every ActGuiShowNoticeWindow sent: [act, NoticeTable, 4 ids, seconds]."""
    return [tuple(a[2:4]) for a in acts(s, director.ACT_NOTICE_WINDOW)]


def test_the_camera_notice_comes_at_the_first_marked_place_and_no_tower_line():
    # harness report row '#17' (differs: ours a 12 s timer after the scouts' step) and 'tower seen' ("not on the
    # tape"); frames 6:32-6:48: the hero reaches the first mark's glow at 6:37, the pillar goes at 6:38 and "Control
    # the Camera in Strategy Mode" (8000 / 8010) replaces "Scout the forest." at 6:38-6:39; no help box then or until
    # 1060 at 7:40 (frames 6:46-7:42 every 2 s; the text read has no 1050 on any part)
    s = mission_room(10233)
    obey(s)                                           # the lessons, 1030 / 1040 and the first mark
    run_pending(s)
    assert (8020, 8030) in notices(s) and (8000, 8010) not in notices(s)
    walk(s, *TOWER_SEEN)
    run_pending(s)
    assert notices(s)[-1] == (8000, 8010)
    walk(s, *RUINS)
    run_pending(s)
    assert 1050 not in line_ids(s) and line_ids(s)[-1] == 1060


def highlights(s):
    """(area, on) of every ActGuiSetHighlightArea sent: [act, area, seconds, on]."""
    return [(a[1], a[3]) for a in acts(s, director.ACT_HIGHLIGHT_AREA)]


def test_the_third_mark_is_18022_and_2_support_request_starts_as_the_hero_reaches_it():
    # harness report rows 'ruins' (partly: ours played 2_SupportRequest with 1060 at 18021) and 'action mode'
    # (differs: ours 12_Ruins_Tab at 18023); frames 7:38-7:54: 1060 at the ruins (7:40), a new pillar ahead (7:42-7:46,
    # the minimap ring 7:41.75 1.1 px from 18022's point), the cutscene as the hero reaches it (7:51.5 -> 7:52); the
    # text read: 2_SupportRequest to its last line 1100 (8:11.75-8:14.25), 12_Ruins_Tab's card 8:15.25, Tab 8:18
    s = mission_room(10233)
    obey(s)                                           # the lessons
    walk(s, *TOWER_SEEN)
    run_pending(s)
    walk(s, *RUINS)
    run_pending(s)
    assert line_ids(s)[-1] == 1060 and cutscenes(s) == [0]
    assert highlights(s)[-2:] == [(18021, 0), (18022, 1)]
    walk(s, *SCOUTING)                                # 18023's strip, not the mark: nothing
    run_pending(s)
    assert cutscenes(s) == [0]
    walk(s, *SUPPORT)
    assert highlights(s)[-1] == (18022, 0)
    steps = director.script(10233)                    # the scene and its last line (1100 at 19.8 s, 4 s), then 12
    tab = next(st for st in steps if ("cutscene", 12, 2) in st.get("do", ()))
    scene = next(st for st in steps if ("cutscene", 2, 20) in st.get("do", ()))
    assert (tab["on"], tab["step"], tab["s"]) == ("after", scene["id"], 3) and scene["bound"] == 18022
    run_pending(s)
    assert cutscenes(s) == [0, 2, 12] and director.KEY_CHANGE_CONTROL_MODE in prompts(s).values()
    assert not {1070, 1080, 1090, 1180, 1100} & set(line_ids(s))   # the cutscene's own
    assert 18023 not in {a for a, _ in highlights(s)}


def test_the_archers_are_given_at_the_winged_wyrms():
    # at 5_WingedWorm_Appeared's end, with Glen's 1330 (the tape: 11:44, 2 s after the scene's 1320); no engage needed
    s = mission_room(10233)
    assert [a[2] for a in acts(s, game.ACT_CHANGE_FORCE)] == [SCOUT]
    enter_the_wyrms_clearing(s)
    run_pending(s)
    assert [a[2] for a in acts(s, game.ACT_CHANGE_FORCE)] == [SCOUT]
    end_the_wyrm_scene(s)
    assert [a[2] for a in acts(s, game.ACT_CHANGE_FORCE)] == [SCOUT, ARCHERS]
    assert ARCHERS in s.data["plan"]["hand"]


def test_the_camp_releases_its_lessons_wait():
    # 10_Defense_Camp locks input and waits on System_WaitState(-10) (8.0 s) before its Offensive lesson
    s = mission_room(10233)
    run_pending(s)
    steps = director.script(10233)
    director._state(s)["fired"].add(next(i for i, st in enumerate(steps) if st.get("id") == "uphill"))
    director.fire(s, next(i for i, st in enumerate(steps) if st.get("id") == "tower"))
    run_pending(s)
    assert [a[1] for a in acts(s, director.ACT_CAMERA_SET)] == [0xFFFFFFF6] and cutscenes(s)[-2:] == [9, 10]


def test_the_captain_falls_and_glen_comes_to_the_scouts():
    s = mission_room(10233)
    run_pending(s)
    game.wake(s, next(w for w in s.data["waves"] if w[0]["ForceNum"] == 20010), "test")
    run_pending(s)
    assert line_ids(s)[-1] == 1110                    # "That one looks like their captain!"
    moved = len([w for w in s.sent if w.proto == game.S2C_TROOP_BACK])
    down_all(s, [20014])
    run_pending(s)
    assert line_ids(s)[-2:] == [1120, 1130]           # Glen's own lines wait for his force in the fight
    glen = [w for w in s.sent if w.proto == game.S2C_TROOP_BACK][moved:]
    assert [struct.unpack_from("<H", bytes(w.buf), 7)[0] for w in glen][0] == GLEN    # in at his entry 글렌 진입
    director.on_engage(s, 11002, 20101)
    run_pending(s)
    assert line_ids(s)[-2:] == [1140, 1150]


def test_the_tower_plays_its_ending_before_the_victory_window():
    s = mission_room(10233)
    run_pending(s)
    game.mission_won(s, NoSave())
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) and not s.data.get("mission_won")
    assert 10001 not in opened(s)                     # the door waits for 3_SealedTower (104 s, 10800-10890)
    run_pending(s)
    assert 10001 in opened(s) and cutscenes(s)[-1] == 3   # Jade unseals the tower's door
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1 and s.data["mission_won"]


def test_a_hand_is_the_rooms_own():
    s = mission_room(10233)
    director.run(s, ("hand", ARCHERS))
    assert game.mission_plan(10233)["hand"] == (ARCHERS, SCOUT)          # the cached plan untouched
    assert mission_room(10233).data["plan"]["hand"] == (SCOUT,) and s.data["plan"]["hand"] == (SCOUT, ARCHERS)


def marches(s):
    """(uid, area, goal) of every ActTroopMoveToArea: [act, kind 0, uid, area, goal, engage, a6, move]."""
    return [(a[2], a[3], a[4]) for a in acts(s, director.ACT_MOVE_TO_AREA)]


def moved_to(s):
    """{uid: (x, z)} of the S2C 0x50c0 teleports (game.move_troop: 4 packed x/z bytes, i16 y, nibble, u16 uid)."""
    out = {}
    for w in s.sent:
        if w.proto == game.S2C_TROOP_BACK:
            b = bytes(w.buf)
            out[struct.unpack_from("<H", b, 7)[0]] = obf.dec_pos_xz(b[0:4], b[6])
    return out


def fire_step(s, sid):
    steps = director.script(10233)
    director.fire(s, next(i for i, st in enumerate(steps) if st.get("id") == sid))


def mark_fired(s, sid):
    """The step the next one needs counted as played (the tests start a stretch of the story in the middle)."""
    director._state(s)["fired"].add(next(i for i, st in enumerate(director.script(10233)) if st.get("id") == sid))


def test_the_ring_closes_on_the_scouts_at_the_scouting_places_centre():
    # live 2026-09-29 03:59: F20100's last troop 20112 obeyed its march (after its 0x50ab) and stood at (60914, 87758),
    # the strip 18023's north-east corner, 9 k from the hero: goal 1 of ActTroopMoveToArea is the area's point nearest
    # the troop (0x140b9eca0 -> 0x140b93380, area vt+0x70), and 18023 is a 16 k strip. Goal 0 is the area's centre
    # (0x140b9dce0, area +0x30), where 2_SupportRequest put the scouts (hero (53741, 84119), 1.6 k from it)
    s = mission_room(10233)
    run_pending(s)
    game.wake(s, next(w for w in s.data["waves"] if w[0]["ForceNum"] == 20010), "test")
    down_all(s, [20014])
    ring = [m for m in marches(s) if 20101 <= m[0] <= 20120]
    assert sorted(u for u, _, _ in ring) == list(range(20101, 20121))
    assert {(area, goal) for _, area, goal in ring} == {(18023, director.MOVE_CENTRE)}
    assert (GLEN, 18023, director.MOVE_CENTRE) in marches(s)              # from 글렌 진입 into the fight


def test_the_escort_still_follows_the_crossings():
    # the escort's marches go to the nearest point of the strip the hero crosses (goal 1), as before
    s = mission_room(10233)
    obey(s)                                           # the lessons
    walk(s, *TOWER_SEEN)
    run_pending(s)
    assert marches(s)[0] == (THOMPSON, 18020, director.MOVE_NEAREST)


def enter_the_wyrms_clearing(s):
    run_pending(s)
    director._state(s)["fired"].add(next(i for i, st in enumerate(director.script(10233)) if st.get("id") == "report"))
    b = director.bound(10233, "가두기_윙드웜")
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])


def asked(s, cond, args=b""):
    """The serials of the conditions asked (S2C 0x5086) of that kind and arguments, not answered yet."""
    return [serial for serial, c, a in queries(s) if c == cond and a.startswith(args)
            and serial not in getattr(s, "answered", set())]


def reply(s, serial, holds):
    s.answered = getattr(s, "answered", set()) | {serial}
    answer(s, serial, holds)


def end_the_wyrm_scene(s):
    """5_WingedWorm_Appeared to its end: the client shows its Defensive lesson's last page (133_Command_X, page 2: X),
    the player's X completes it (0xc760), and the scene plays its last 13 s (the queue's timers, run here)."""
    run_pending(s)
    [page] = asked(s, director.COND_TUTORIAL_PAST, b"133_Command_X\0")
    reply(s, page, True)
    [done] = asked(s, director.COND_TUTORIAL_COMPLETE)
    reply(s, done, True)
    run_pending(s)


def test_the_wyrms_come_to_the_party_in_the_clearing():
    # live 2026-09-29 (03:55 and the owner's 04:59 run): wyrm 30000 never left its place (35161, 91845), 10.7 k from
    # the party, beyond its 6000 acquisition (nptrooptable 133080 RANGE_ACQUISITION): "Only one left!" at 05:19:19,
    # then nothing. The original (part 2 11:45-12:42, the minimap channel): the wyrms come in from their places at the
    # scene's end and make their passes between the clearing and the archers. 30002, 1.4 k from the hero's place,
    # is not marched: marched, it held over the clearing's centre attacking nobody (live 2026-10-24 11:59:05-12:11)
    s = mission_room(10233)
    enter_the_wyrms_clearing(s)
    run_pending(s)
    assert 30000 not in s.data["zone_troops"]          # not before 5_WingedWorm_Appeared ends
    end_the_wyrm_scene(s)
    assert {30000, 30001, 30002} <= set(s.data["zone_troops"])
    wyrms = [m for m in marches(s) if m[0] in (30000, 30001, 30002)]
    assert sorted(wyrms) == [(u, 13011, director.MOVE_CENTRE) for u in (30000, 30001)]


def test_the_wyrm_scene_holds_what_follows_until_its_lesson_is_done():
    # live 2026-10-24: 5_WingedWorm_Appeared's Defensive lesson held the scene from 11:58:49 to the player's X at
    # 12:06:15 and the scene ended at 12:06:29 (telemetry "lesson" / "cut"), but ours sent what follows at the queue's
    # 25 s (11:59:02): the column's places, the wake and the march of the wyrms, 7 min 27 s early. The scene (its
    # SCRIPT track): the lesson starts at 11.766 s, the scene waits for X, completes the lesson at 12.076 s and ends at
    # 25.009 s; the client reports neither, so the table asks for the lesson's last page, then its completion
    s = mission_room(10233)
    enter_the_wyrms_clearing(s)
    run_pending(s)
    assert cutscenes(s)[-1] == 5
    following = lambda: (set(moved_to(s)) & {11000, 11004, ARCHERS}, 30000 in s.data["zone_troops"],
                         [m for m in marches(s) if m[0] in (30000, 30001)], ARCHERS in s.data["plan"]["hand"],
                         1330 in line_ids(s))
    assert following() == (set(), False, [], False, False)
    [page] = asked(s, director.COND_TUTORIAL_PAST, b"133_Command_X\0")
    assert queries(s)[-1][2] == b"133_Command_X\0" + struct.pack("<i", 1)      # at its third page (X) or past it
    reply(s, page, False)                              # still on its F pages: asked again, nothing follows
    run_pending(s)
    [page] = asked(s, director.COND_TUTORIAL_PAST, b"133_Command_X\0")
    assert following() == (set(), False, [], False, False)
    reply(s, page, True)
    [done] = asked(s, director.COND_TUTORIAL_COMPLETE)
    reply(s, done, False)                              # the X not pressed yet
    run_pending(s)
    assert following() == (set(), False, [], False, False)
    [done] = asked(s, director.COND_TUTORIAL_COMPLETE)
    reply(s, done, True)
    run_pending(s)
    places, woke, wyrms, handed, told = following()
    assert places == {11000, 11004, ARCHERS} and woke and len(wyrms) == 2 and handed and told


def test_the_wyrm_scenes_two_parts_are_its_own_track():
    # the queue holds 5_WingedWorm_Appeared to its lesson, and what follows comes the rest of the scene after the
    # lesson is done: 12 s and 13 s, from its SCRIPT track (planning/scripts/cutscenes.json) [data]
    import json
    import pathlib
    rows = json.loads((pathlib.Path(director.__file__).parents[2] / "planning" / "scripts" / "cutscenes.json")
                      .read_text(encoding="utf-8"))
    [scene] = [r for r in rows if r["name"] == "5_WingedWorm_Appeared"]
    at = lambda text: next(ms for ms, _, cmds in scene["script"] for c in cmds if text in c) / 1000
    start, done, end = at("System_StartTutorial(-1,13307)"), at("System_CompleteTutorial(2)"), scene["script"][-1][0] / 1000
    steps = {st.get("id"): st for st in director.script(10233)}
    assert ("cutscene", 5, round(start)) in steps["wyrm scene"]["do"]
    assert (steps["wyrms"]["step"], steps["wyrms"]["s"]) == ("defensive", round(end - done))
    assert steps["defensive page"]["cond"] == (director.COND_TUTORIAL_PAST, "133_Command_X", 1)
    assert steps["defensive"]["cond"] == (director.COND_TUTORIAL_COMPLETE,)


def test_the_column_and_the_archers_stand_in_the_clearing_after_the_cutscene():
    # live 2026-09-29: at the hand (the first engage with a wyrm) the archers 11006 stood 10-17 k back
    # ((52848, 81974) in the owner's run, (44077, 93112) at 04:13), stopped by the escort order or the hand; 11000 /
    # 11003 at the scouting area. The original: the column on the clearing's road at 1320 (tile #73, 11:44), the
    # archers there for "Archers, shoot down the Winged Wyrm!"; 5_WingedWorm_Appeared animates 11000-11003 (4.0 s,
    # 13.0 s), whose bounds 11000-11003 line that road
    # The archers stand on their own bounds 11004-11006, short of the clearing: the tape's allied group stood 800 from
    # 11006 through the fight (10:59-12:53, harness report "Where the tape shows the allies standing"; brief finding
    # 4), and once F2 is pressed the camera shows the archers in a grass field with the column and the wyrms overhead
    # (frames 11:58-12:47), not on the clearing's dirt road where the hero stands; ours put them at the clearing's
    # centre, 13.8 k off
    s = mission_room(10233)
    enter_the_wyrms_clearing(s)
    assert not set(moved_to(s)) & {11000, 11001, 11002, 11003, ARCHERS}
    end_the_wyrm_scene(s)
    at = moved_to(s)
    for u in (11000, 11001, 11002, 11003, 11004, 11005, ARCHERS):
        b = director.bound(10233, u)
        assert abs(at[u][0] - b["BoundCenterX"]) < 20 and abs(at[u][1] - b["BoundCenterZ"]) < 20


def test_the_column_goes_uphill_with_the_hero():
    # the original (tiles #89-#90, 13:16-13:30): Glen, Thompson and the main forces' column march up with the hero after
    # "Let's go!" (1400); the escort marches only at bound steps, and none comes before the tower's
    s = mission_room(10233)
    run_pending(s)
    game.spawn_force(s, 30000)
    fell_force(s, 30000)
    assert not [m for m in marches(s) if m[1] == HILLTOP]          # not before the lines
    run_pending(s)
    up = {u for u, area, goal in marches(s) if area == HILLTOP and goal == director.MOVE_CENTRE}
    assert {GLEN, THOMPSON, 11000, 11001, 11002, 11003, 11004, 11005, ARCHERS} <= up
    s2 = mission_room(10233)
    run_pending(s2)
    director.run(s2, ("hand", ARCHERS))                # the player's archers take their orders from him
    game.spawn_force(s2, 30000)
    fell_force(s2, 30000)
    run_pending(s2)
    assert ARCHERS not in {u for u, area, _ in marches(s2) if area == HILLTOP}


def test_glens_other_archers_shoot_the_wyrms():
    # the original (part 2 12:03-12:46, the damage builder's frames): the handed troop fires 12:03-12:11, then "Waiting
    # for command", and the wyrms fall to Glen's other archers 11004 / 11005 (one lost 62 % in 4.5 s); Glen's 1340:
    # "The other archer's job will to help the Commander's troop to attack!". Live 2026-09-29 (03:55 and 04:59) they
    # stopped at (64-65 k, 75-76 k) after shooting F20100 from afar (04:00:58, 05:05:18), 30 k from the wyrms; in the
    # 04:59 run they fired at a wyrm only when 30001 flew to them (05:13:27-05:13:51, 8 + 7 volleys; it fell 05:13:45)
    s = mission_room(10233)
    enter_the_wyrms_clearing(s)
    end_the_wyrm_scene(s)
    at = moved_to(s)
    for u in (11004, 11005):                           # on their own bounds (the tape; brief finding 4)
        b = director.bound(10233, u)
        assert abs(at[u][0] - b["BoundCenterX"]) < 20 and abs(at[u][1] - b["BoundCenterZ"]) < 20
    assert ARCHERS in s.data["plan"]["hand"]           # the player's own archers take his orders, from the scene's end
    assert acts(s, director.ACT_RANGE_ATTACK) == []    # not before the fight
    director.on_engage(s, 30002, GLEN)
    run_pending(s)
    assert acts(s, director.ACT_RANGE_ATTACK) == [[director.ACT_RANGE_ATTACK, 0, u, director.NEAREST_ENEMY, 1, 0]
                                                   for u in (11004, 11005)]


def fell_force(s, force):
    down_all(s, [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == force])


def test_the_camp_is_manned_for_its_scenes():
    # 8_TowerFound enables F13000 (16.0 s); 9_Camp shows the resting soldiers, then disables F14100-F14400 and
    # enables F14370 (28.0 s); 10_Defense_Camp enables F14370 / F14500 (0 s) and F16000 (16.5 s): the client acts on
    # troops it has. Ours joined them to the scorpions' wave (ally_pair): they came after the attack had begun
    s = mission_room(10233)
    run_pending(s)
    director._state(s)["fired"].add(next(i for i, st in enumerate(director.script(10233)) if st.get("id") == "uphill"))
    camp = {13000, 14100, 14200, 14300, 14310, 14320, 14330, 14340, 14360, 14370, 14400, 14500, 16000}
    assert not camp & {t.get("ForceNum") for t in s.data["zone_troops"].values()}
    fire_step(s, "tower")
    assert camp <= {t.get("ForceNum") for t in s.data["zone_troops"].values()} and 8 not in cutscenes(s)
    run_pending(s)
    assert cutscenes(s)[-3:] == [8, 9, 10]
    # 8_TowerFound disables Glen, Thompson and 11000-11005 (24.2 s): no enable-all may follow it through the camp
    # scenes (adversarial 2026-09-29: twelve camp wakes between 8_TowerFound and 9_Camp enabled them again); the
    # night attack's wake after 10_Defense_Camp still does (ActTroopSetEnableAllTroops, game.wake)
    order = [struct.unpack_from("<3I", bytes(w.buf))[1] if a == director.ACT_CUTSCENE else "all"
             for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
             for a in [struct.unpack_from("<I", bytes(w.buf))[0]] if a in (director.ACT_CUTSCENE, game.ACT_ENABLE_ALL_TROOPS)]
    assert "all" not in order[order.index(8):order.index(10)]


def test_a_force_a_step_brought_is_not_spawned_again_with_its_wave():
    s = mission_room(10233)
    run_pending(s)
    director.run(s, ("wake", 14100, 16000))
    n = sum(w.proto == game.S2C_ENTER_CELL_TROOP for w in s.sent)
    game.spawn_force(s, 40005)                          # its wave's allies: the camp (ally_pair)
    again = [w for w in s.sent[:] if w.proto == game.S2C_ENTER_CELL_TROOP][n:]
    uids = {struct.unpack_from("<H", bytes(w.buf), 2 + 1 + 0x11)[0] for w in again}
    assert 14100 not in uids and 16000 not in uids and 14370 in uids


def test_the_night_attack_marches_on_the_camp():
    # 9_Camp walks the attacking column to 10501 컷신이동 (22.0 s: Troop_MoveToArea(35001..35006, 10501, 0)) and
    # 10_Defense_Camp sends the hero to 10500 (16.5 s); the night attack is fought there (tiles #99-#108)
    # The scorpions F40005 and the head cannons F40100 come with the attack, not after F40000 falls (harness report
    # row 'scorpions'; frames 15:42-16:14: the scorpion in the melee at 16:08-16:13 and 1500 "Scorpion!" at 16:11, ten
    # seconds into the fight; the minimap's attacking column R3 holds 40001 / 40002 / 40030 / 40031 from 15:45)
    s = mission_room(10233)
    run_pending(s)
    fire_step(s, "camp")
    run_pending(s)
    assert 40003 in s.data["zone_troops"]
    f40000 = {u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 40000}
    attack = {m for m in marches(s) if m[0] in f40000}
    assert attack and {(a, g) for _, a, g in attack} == {(10501, director.MOVE_CENTRE)}
    later = {u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") in (40005, 40100)}
    assert later == {40001, 40002, 40029, 40030, 40031, 40032}
    assert {(a, g) for u, a, g in marches(s) if u in later} == {(10501, director.MOVE_CENTRE)}
    assert not f40000 & s.data.get("down", set())


def test_1490_and_the_scorpion_lines_wait_for_the_offensive_key():
    # harness report rows '#41' / 'scorpions' / 'hang on' / '#44' (differs, partly); frames 15:42-16:14 and the text
    # read: Glen's 1480 as 10_Defense_Camp opens (15:44.75), its Offensive lesson (13308, 7190 / 7210 15:51-15:58)
    # completed on Z at ~15:57.5 (the circle), Thompson's 1490 at 16:01.75, then 1500-1530, 1560 (16:34.75, 2 s after
    # 1530), 8140 / 8150 (16:35.75), 1570 (16:42), 1580 (16:50) as one run, and 11_Canon_Bomb 5.5 s after 1580
    # (16:57.5). Ours said 1490 straight after 1480 and held the scorpions' lines for F40000's fall
    s = mission_room(10233)
    run_pending(s)
    fire_step(s, "camp")
    run_pending(s)
    assert line_ids(s)[-1] == 1480 and 1490 not in line_ids(s) and not s.data.get("mission_won")
    assert director.KEY_AI_OFFENSIVE in prompts(s).values()
    shut = len(closes(s))
    press(s, director.KEY_AI_OFFENSIVE)
    assert closes(s)[shut:] == [director.ACT_FINISH_TUTORIAL]       # the card goes on its Z (as 12_Ruins_Tab's Tab)
    run_pending(s)
    assert line_ids(s)[-8:] == [1490, 1500, 1510, 1520, 1530, 1560, 1570, 1580]
    assert s.data.get("mission_won") and cutscenes(s)[-2:] == [11, 3]


def test_the_tower_is_won_when_golden_hammers_cannons_arrive():
    # the success condition is 130 "Survive until reinforcements arrive"; the original (part 2 16:58-19:14):
    # 11_Canon_Bomb (Golden Hammer, 10700), whose organ cannons F16100 fire on the invisible targets F46100 and which
    # disables the scorpions 40001 / 40002 (6.1 s), then 3_SealedTower, then the victory. F35000 is 9_Camp's column
    # (10_Defense_Camp disables it): not woken (its two scorpions stood 10 k west of the camp, the win waited on them)
    s = mission_room(10233)
    s.state = NoSave()
    run_pending(s)
    fire_step(s, "camp")
    run_pending(s)
    press(s, director.KEY_AI_OFFENSIVE)                 # 10_Defense_Camp's lesson
    fell_force(s, 40000)
    fell_force(s, 40100)
    assert not s.data.get("mission_won")                # the scorpions stand; the win is the table's
    run_pending(s)
    assert s.data.get("mission_won") and cutscenes(s)[-2:] == [11, 3]
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1
    assert 35001 not in s.data["zone_troops"]
    assert {16100, 16104, 46100, 46104} <= set(s.data["zone_troops"])
    gone = [a[2] for a in acts(s, game.ACT_ENABLE_TROOP) if a[3] == 0]
    assert gone == [40001, 40002] and {40001, 40002} <= s.data["down"]


def test_the_wyrms_fall_to_volleys_not_to_a_skill_cast():
    # owner 2026-09-29 15:40: the skill rule is dropped, the real damage decides (Q18: the synastry matrix, row 278
    # takes RANGE x3). A cast of the archers' skill 200147 (0x505f) is a buff, it fells nothing; Glen's archers'
    # volleys (0x505a, 42 arrows of 133140) bring a wyrm down in a few, as the original's 62 % in 4.5 s
    from kuf2 import combat
    from test_battle import pkt, enc_uid
    s = mission_room(10233)
    run_pending(s)
    game.spawn_force(s, 30000)
    director.run(s, ("hand", ARCHERS))
    role = game.make(NoSave(), 0)
    b = s.data["battle"]
    body = enc_uid(30002) + struct.pack("<H", ARCHERS) + obf.u32(200147) + bytes(7)
    role.handlers[combat.C2S_TROOP_CAST](s, pkt(combat.C2S_TROOP_CAST, body))
    run_pending(s)
    assert combat.Battle.total(b.troops[30002]) == 11453          # the skill fells nothing
    volleys = 0
    while combat.Battle.total(b.troops[30001]) > 0 and volleys < 20:
        body = enc_uid(11004) + struct.pack("<H", 1) + enc_uid(30001) + bytes([127 * 2])
        role.handlers[combat.C2S_AREA_DAMAGE](s, pkt(combat.C2S_AREA_DAMAGE, body))
        volleys += 1
    assert combat.Battle.total(b.troops[30001]) == 0 and volleys <= 5


def tutorials(s):
    return [bytes(w.buf)[4:].split(b"\0")[0].decode() for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
            and struct.unpack_from("<I", bytes(w.buf))[0] == director.ACT_START_TUTORIAL]


def closes(s):
    """The pop-up closings sent, in order: ActGuiFinishTutorial 0xc897 / ActGuiCompleteTutorial 0xc898."""
    shut = (director.ACT_FINISH_TUTORIAL, director.ACT_COMPLETE_TUTORIAL)
    return [a[0] for a in (list(struct.unpack_from("<I", bytes(w.buf))) for w in s.sent
                           if w.proto == game.S2C_SCRIPT_ACTION) if a[0] in shut]


def unanswered(s):
    return [q for q in queries(s) if q[0] not in getattr(s, "answered", set())]


# (pop-up, its step that waits for the player, the keys the original's lesson script waited for there, the closing)
# 1_TroopTutorial (planning/scripts/cutscenes.json): KEY_SelectTroop1 ` for the hero, KEY_MouseCameraRotEnd (the right
# button released), KEY_SceneToggleDown / Up (the wheel); "Move the camera" had no key there (the server released
# its wait): W / S / A / D; KEY_AIHeroSupport C. A one-step pop-up is completed, a longer one closed (0xc898 completes
# step 0 only, 0x140b5db70)
LESSONS = (("133_SelectHero", 2, (0x34,), director.ACT_FINISH_TUTORIAL),
           ("133_TroopCameraRotation_NoInfo", 0, (0x77,), director.ACT_COMPLETE_TUTORIAL),
           ("133_TroopCameraZoom_NoInfo", 0, (0x3f, 0x40), director.ACT_COMPLETE_TUTORIAL),
           ("133_TroopCameraMove_NoInfo", 0, (0x7c, 0x7d, 0x7e, 0x7f), director.ACT_COMPLETE_TUTORIAL),
           ("133_Command_C_NoInfo", 2, (0x3a,), director.ACT_FINISH_TUTORIAL))


def test_each_lesson_closes_when_the_player_does_what_it_asks():
    # live 2026-09-29 14:12: the lessons came on timers and the ones asking for a key but F / R never closed. Now each
    # pop-up's F pages are the client's own (0x14094e2d0), its last step is asked (0x5086 0xcb2b: the pop-up past
    # step n) and, once it shows, its key prompted (0x50c1); the player's key (0x50c2) closes it and the next follows
    s = mission_room(10233)
    run_pending(s)
    for name, step, keys, close in LESSONS:
        assert tutorials(s)[-1] == name
        shut = len(closes(s))
        [(serial, cond, args)] = unanswered(s)
        assert cond == director.COND_TUTORIAL_PAST and args == name.encode() + b"\0" + struct.pack("<i", step - 1)
        s.answered = getattr(s, "answered", set()) | {serial}
        answer(s, serial, False)                      # still on its F pages: nothing prompted, asked again
        run_pending(s)
        assert not [pid for pid, k in prompts(s).items() if k in keys and pid not in getattr(s, "pressed", set())]
        [(serial, _, _)] = unanswered(s)
        s.answered.add(serial)
        answer(s, serial, True)
        live = {pid: k for pid, k in prompts(s).items() if k and pid not in getattr(s, "pressed", set())}
        assert sorted(live.values()) == sorted(keys)
        run_pending(s)
        assert len(closes(s)) == shut and tutorials(s)[-1] == name     # nothing moves on without the key
        press(s, keys[-1])
        assert closes(s)[shut:] == [close]
        assert not {pid for pid, k in prompts(s).items() if k in keys} - s.pressed   # the others came down
        run_pending(s)
    assert line_ids(s)[:5] == [1000, 1010, 1020, 1030, 1040]
    assert [a[2] for a in acts(s, game.ACT_SITUATION_DONE)] == [210, 220, 230]   # the panel's three lessons


def test_a_lessons_panel_line_comes_a_moment_before_its_pop_up():
    # the tape (part 2): "Select Hero and change Strategy mode" in the panel at 5:07.75, the pop-up 7000 at 5:07.88;
    # "Use the Hero Support Strategy command" at 6:15.50, the pop-up 7120 at 6:15.62, each as Thompson's line goes
    # (build/order-b captures/order-b/p2_tower_210.jpg, p2_tower_230b.jpg); ours put the pop-up first
    s = mission_room(10233)
    obey(s)
    sent = [bytes(w.buf) for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION]
    act = lambda b: struct.unpack_from("<I", b)[0]
    for said, line, name in ((1000, 210, b"133_SelectHero"), (1020, 230, b"133_Command_C_NoInfo")):
        told = next(i for i, b in enumerate(sent) if act(b) == director.ACT_HELP_TEXT_BY_TROOP
                    and struct.unpack_from("<6I", b)[4] == said)
        shown = next(i for i, b in enumerate(sent) if act(b) == game.ACT_SITUATION_LINE
                     and struct.unpack_from("<4I", b)[3] == line)
        popped = next(i for i, b in enumerate(sent) if act(b) == director.ACT_START_TUTORIAL
                      and b[4:].split(b"\0")[0] == name)
        assert told < shown < popped, (said, line, name)


def test_the_archers_lesson_closes_on_f2():
    # "[F2] Select the Archer Troop." stayed up with the archers selected (live 2026-09-29 14:12). 133_SelectTroopSlot2's
    # three pages are the client's (F); its fourth waits for KEY_SelectTroop3 (F2, the second troop slot: the key the
    # original's 7_Tutorial_Range waited for); then the pop-up closes (0xc897; 0xc898 would show page 2 again)
    s = mission_room(10233)
    enter_the_wyrms_clearing(s)
    end_the_wyrm_scene(s)
    assert tutorials(s)[-1] == "133_SelectTroopSlot2"
    [(serial, _, args)] = [q for q in queries(s) if q[2].startswith(b"133_SelectTroopSlot2\0")]
    assert args == b"133_SelectTroopSlot2\0" + struct.pack("<i", 2)
    shut = len(closes(s))
    press(s, 0x36)                                    # before the lesson reaches it: no prompt, nothing
    assert len(closes(s)) == shut
    answer(s, serial, True)
    assert 0x36 in prompts(s).values()
    press(s, 0x35)                                    # F1 (the scouts): not what it asks
    assert len(closes(s)) == shut and 1340 not in line_ids(s)
    press(s, 0x36)
    assert closes(s)[shut:] == [director.ACT_FINISH_TUTORIAL]
    run_pending(s)                                    # Glen's 1340 on the F2 (frames 11:54-12:00: F2 at 11:58, 1340
    assert line_ids(s)[-3:] == [1330, 1340, 1350]     # at 11:59; harness report row 'wyrms', partly)


def test_a_wyrm_left_hovering_never_engaging_the_steps_still_come():
    # live 2026-10-24 11:59-12:12: no engage report came in the whole wyrm fight (0 C2S 0x5058 while Glen's archers'
    # volleys felled 30000 at 11:59:10 and 30001 at 11:59:44, and the wyrms hit 11005 and Thompson), and 30002 hovered
    # 0.1-2.4 k from the hero attacking nobody, hit by nobody: the archers' hand, 1330 and their lesson waited on an
    # engage and never came; the uphill path waits on the last wyrm's fall. Now the hand and the lesson come at the
    # scene's end, the F2 story and "Only one left!" follow without any engage, and the uphill path comes when 30002
    # falls, not before
    s = mission_room(10233)
    enter_the_wyrms_clearing(s)
    end_the_wyrm_scene(s)
    assert ARCHERS in s.data["plan"]["hand"] and line_ids(s)[-1] == 1330
    assert tutorials(s)[-1] == "133_SelectTroopSlot2"
    assert 30002 not in [m[0] for m in marches(s)]
    down_all(s, [30000])                               # to Glen's archers' own volleys
    down_all(s, [30001])
    run_pending(s)
    assert lines_shown(s)[-1] == (THOMPSON, 1, 1360)  # "Only one left!"
    [card] = asked(s, director.COND_TUTORIAL_PAST, b"133_SelectTroopSlot2\0")
    reply(s, card, True)
    press(s, director.KEY_SELECT_TROOP3)               # F2: the archers selected
    run_pending(s)
    assert {1340, 1350} <= set(line_ids(s)) and 30002 not in s.data.get("down", set())
    assert 1370 not in line_ids(s) and not [m for m in marches(s) if m[1] == HILLTOP]   # 30002 still flies
    assert acts(s, director.ACT_RANGE_ATTACK) == []    # no engage, no order: the archers' own program shoots
    down_all(s, [30002])
    run_pending(s)
    assert {1370, 1380, 1390, 1400} <= set(line_ids(s))    # "Whew, we took care of all the Winged Wyrms." ...
    assert {GLEN, THOMPSON} <= {u for u, area, _ in marches(s) if area == HILLTOP}


def test_only_one_left_is_thompsons_as_the_second_wyrm_falls():
    # harness report row '#34' (differs: its "no rule fits: the tape's gap" 12:11-12:29) refuted by the frames 12:28-
    # 12:30: the panel's count 1/3 at 12:29.0, 2/3 at 12:29.25 as the box comes in, "Only one left! Stay sharp!" under
    # Thompson's name and face at 12:29.5: the count's trigger, ours; the speaker is Thompson (ours had Glen)
    s = mission_room(10233)
    run_pending(s)
    game.spawn_force(s, 30000)
    down_all(s, [30000])
    run_pending(s)
    assert 1360 not in line_ids(s)
    down_all(s, [30001])
    run_pending(s)
    assert lines_shown(s)[-1] == (THOMPSON, 1, 1360)


def markers(s):
    """(troop, seconds, on) of every ActGuiSetHighlightTroop sent: [act, troop, seconds, on, leader]."""
    return [tuple(a[1:4]) for a in acts(s, director.ACT_HIGHLIGHT_TROOP)]


def test_glens_marker_shows_where_the_tape_shows_it():
    # the tape's blue (ALLIANCE) pillar and glow, ActGuiSetHighlightTroop (harness report "Effects": 9:21.25-9:23.25,
    # 10:38.75-11:07.75, 13:07.75-13:39.25; frames 9:20.5-9:24, 10:36-11:10, 13:06-13:40): a moment on Glen's arrival
    # after 1140; on him for "Follow Glen." until the clearing's scene; on him again up the hill after 1400 until the
    # hilltop's scene
    s = mission_room(10233)
    run_pending(s)
    director.run(s, ("wake", 20010))
    run_pending(s)
    down_all(s, [20014])
    run_pending(s)
    director.on_engage(s, 11001, 20105)               # his infantry reaches the ring
    assert markers(s) == []
    run_pending(s)
    assert markers(s) == [(GLEN, 2, 1)] and line_ids(s)[-2:] == [1140, 1150]
    mark_fired(s, "regroup")
    fire_step(s, "report")
    run_pending(s)
    assert markers(s)[-1] == (GLEN, 0, 1)             # "Follow Glen.": until taken down
    enter_the_wyrms_clearing(s)
    assert markers(s)[-1] == (GLEN, 0, 0)             # at the clearing, before its scene (11:07.75 -> 11:10)
    run_pending(s)
    game.spawn_force(s, 30000)
    fell_force(s, 30000)
    assert markers(s)[-1] == (GLEN, 0, 0)             # after "Let's go!" (1400), not before
    run_pending(s)
    assert markers(s)[-1] == (GLEN, 0, 1)
    fire_step(s, "tower")
    assert markers(s)[-1] == (GLEN, 0, 0)


def test_glen_alone_leads_to_the_clearing_and_his_column_goes_to_its_own_places():
    # brief finding 3 (tools/harness/tracks.py) and frames 10:36-11:10: "Follow Glen." puts one figure ahead under the
    # blue pillar (10:36-10:46) and the column comes from behind the hero (10:48-11:04); ours marched the whole of
    # F11000 to the clearing with Glen (b08931c). The column's own places: the infantry's bounds 11000-11003 on the
    # clearing's road (where 5_WingedWorm_Appeared animates them), the archers' 11004-11006 short of it (the tape's
    # group stood 800 from 11006, 10:59-12:53)
    s = mission_room(10233)
    run_pending(s)
    mark_fired(s, "regroup")
    fire_step(s, "report")
    run_pending(s)
    to = {(u, area) for u, area, _ in marches(s)}
    assert {u for u, area in to if area == CLEARING} == {GLEN}
    assert {(u, u) for u in range(11000, 11007)} <= to


def test_the_uphill_talk_follows_glen_up_the_hill():
    # harness report row '#36' (differs: ours 10 s after the uphill lines, the harness none): the tape's 1400 ends
    # 13:04.25, Glen's marker 13:07.75, the hero sets off behind him 13:08.5 (the minimap), 1420 at 13:10.0; no area
    # entered then (the trigger the tape does not show: kept a pause after the lines, cut to 3 s)
    steps = director.script(10233)
    talk = next(st for st in steps if st["on"] == "after" and st["step"] == "uphill")
    assert talk["s"] == 3 and ("say", "톰슨_1", 1420) in talk["do"]

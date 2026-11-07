"""Grey Rock Fortress 10234's director table (kuf2/scenes/m10234.py) against the original's order
(planning/scripts/missions/10234.md, playthrough part 2 29:46-43:28): the opening, the corpse kobolds, a wake and its
fall, the win; its lessons: the F4 lesson waits for the player's F4, the finisher lesson is the client's own F pages
and its panel line completes on the finishing attack."""
import math
import struct

import pytest

from kuf2 import director, game, obf, status, zone
from test_battle import NoSave, acts, down_all, mission_room, pkt, read_prop, walk
from test_director import (answer, cutscenes, lines_shown, obey, press, prompts, queries, rooms_at_cutscenes,
                           run_pending)
from test_scenes_10233 import closes, tutorials

GLEN, THOMPSON = 10000, 10071                       # 글렌 (his force's leader) and 톰슨 (troop 10071)
CHECK1 = "P1_S2_영웅 체크1"                          # the strip across the path out of the camp (10008)
ACTION_CAMERA = "P1_S3_액션 카메라"                  # the strip of the action camera (10009), its point marked
CORPSES = "P1_S2_액션 카메라 무시"                   # the bound of the corpse kobolds (force 20010)
TROLL = 20082                                       # the Mountain Troll (force 20080), the finisher lesson at its 10 %
SORCERER, TANK = 20078, 20184                       # the inner castle's sorcerer (F20073) and the tank behind (F20074)


def said(s):
    return [(uid, line) for uid, _, line in lines_shown(s)]


def ids(s):
    return [line for _, line in said(s)]


def highlights(s):
    """The area marks 0xc7b0 sent: (area id, on)."""
    return [(a[1], a[3]) for a in acts(s, director.ACT_HIGHLIGHT_AREA)]


def enter(s, key):
    b = director.bound(10234, key)
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])
    run_pending(s)


def sent_before(s, act, first, line):
    """Whether the script action `act` with first argument `first` went out before the help-box line `line`."""
    i = next(k for k, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION and len(w.buf) >= 8
             and struct.unpack_from("<2I", bytes(w.buf)) == (act, first))
    j = next(k for k, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION
             and struct.unpack_from("<I", bytes(w.buf))[0] == director.ACT_HELP_TEXT_BY_TROOP
             and struct.unpack_from("<6I", bytes(w.buf))[4] == line)
    return i < j


def sent_notice_before(s, title, line):
    """Whether the notice window titled `title` went out before the help-box line `line`."""
    i = next(k for k, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION
             and bytes(w.buf)[:4] == director.ACT_NOTICE_WINDOW.to_bytes(4, "little")
             and int.from_bytes(bytes(w.buf)[8:12], "little") == title)
    j = next(k for k, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION
             and struct.unpack_from("<I", bytes(w.buf))[0] == director.ACT_HELP_TEXT_BY_TROOP
             and struct.unpack_from("<6I", bytes(w.buf))[4] == line)
    return i < j


def notices(s):
    """The notice windows 0xc8f0 sent: (title id, text id)."""
    return [tuple(int.from_bytes(bytes(w.buf)[i:i + 4], "little") for i in (8, 12)) for w in s.sent
            if w.proto == game.S2C_SCRIPT_ACTION and bytes(w.buf)[:4] == director.ACT_NOTICE_WINDOW.to_bytes(4, "little")]


def panel(s):
    """The objective lines 0xc7f6 (ActGuiAddLineToMissionSituation) sent: the line ids."""
    return [int.from_bytes(bytes(w.buf)[12:16], "little") for w in s.sent if w.proto == game.S2C_SCRIPT_ACTION
            and bytes(w.buf)[:4] == game.ACT_SITUATION_LINE.to_bytes(4, "little")]


def done(s):
    """The panel lines completed (0xc828)."""
    return [a[2] for a in acts(s, game.ACT_SITUATION_DONE)]


def wake_force(s, force):
    wave = next((w for w in s.data["waves"] if w[0]["ForceNum"] == force), None)
    if wave is not None:                             # (in already: the hero's walk woke it)
        game.wake(s, wave, "test")
    assert any(t.get("ForceNum") == force for t in s.data["zone_troops"].values())


def test_the_panel_opens_under_the_fortresss_own_title():
    # the original's panel: "Greyrock Fortress" (100) on the red bar above "Winning Conditions" / "Enter Greyrock
    # Fortress" and the lesson "Select Entire Troop" (frame of part 2 30:40)
    s = mission_room(10234)
    assert acts(s, game.ACT_SITUATION_TITLE) == [[game.ACT_SITUATION_TITLE, game.ALL_TEAMS, 100]]


def test_the_fortress_opens_with_its_cutscene_the_march_orders_and_the_move_troop_notice():
    # the original (rows 3-10): 0_Start_CutScene (19000-19070), Glen's 1200, the F4 lesson (5000 / 5001), 1210 and the
    # notice "Move Troop" (6000 / 6001, the tape's frames 30:47-30:59); 1220 and "Switch to Action Mode" (6002 / 6003)
    # wait for the path (the next tests). The panel opens on "Enter Greyrock Fortress" (121), not the untitled 120
    # "Identify who hanged the corpses", which never shows
    s = mission_room(10234)
    assert cutscenes(s) == [0] and said(s) == [] and panel(s)[0] == 121 and 120 not in panel(s)
    run_pending(s)
    obey(s)                                         # the F4 lesson
    assert said(s) == [(GLEN, 1200), (THOMPSON, 1201), (GLEN, 1210)]
    assert notices(s) == [(6000, 6001)]
    assert 20000 in s.data["zone_troops"]           # the corpse kobolds (force 20010), the first wave, wait ahead


def test_the_f4_key_sends_glen_up_the_path_and_the_path_check_tells_the_hero_to_follow():
    # the tape (part 2, frames 30:45-31:03; harness report row #3, ours: 1220 and 6002 / 6003 2 s after the key): the F4
    # key (30:45.5), "Everyone, let's move!" (1210, 30:46), "Move Troop / Use @MRB to move." (6000 / 6001, 30:47),
    # Glen walking up the path ahead of the hero (the blue marker on him 30:46-30:49, his force's cyan marks
    # 30:44.5-31:10.5 ending 600 from P1_S2_방향지시1), the ground mark of the action camera's point (its minimap ring
    # 0.7 px from 10009's point at 30:52.2, the hero reaching it at 31:09); "Move along the path!" (1220) only at 30:59,
    # as the hero crosses P1_S2_영웅 체크1 (his reads 30:58.8 south of it, 30:59.8 in it), then "Switch to Action Mode"
    # (6002 / 6003, 31:01). The harness's 10011 (30:57.5) was the minimap arrowhead read on the mark's green dot
    s = mission_room(10234)
    run_pending(s)
    obey(s)                                         # the F4 lesson
    assert ids(s)[-1] == 1210 and 1220 not in ids(s) and notices(s) == [(6000, 6001)]
    assert highlights(s) == [(10009, 1)]
    marched = {o[2]: o[3] for o in acts(s, director.ACT_MOVE_TO_AREA)}
    assert {GLEN, 10004, 10005} <= set(marched) and {marched[u] for u in (GLEN, 10004, 10005)} == {10071}
    assert THOMPSON not in marched and not {10072, 10073} & set(marched)     # the player's own take his orders
    enter(s, CHECK1)
    assert said(s)[-1] == (GLEN, 1220) and notices(s)[-1] == (6002, 6003)
    assert ids(s).count(1220) == 1


def test_the_action_camera_shows_the_corpse_kobolds_when_the_hero_reaches_its_mark():
    # the tape (frames 31:05-31:33; harness report row #4 and the parts12 builder's case: 2110 / 1240 at 31:09.5, ours
    # on 액션 카메라 무시, entered 31:24.5): the hero walks into the mark of P1_S3_액션 카메라 (31:09.5, it goes),
    # Thompson's "General! Kobolds!" (2110, 31:10.0) with the F prompt "Look far" (31:10.0-31:11.25, hand-read in
    # build/order-a), the F (31:11.5) plays the action camera 2_Action_Camera (from 31:12.25; the minimap hidden
    # 31:12.5-31:18.5, its 6 s) with the looting kobold's "Where's shiny things?" (1240, 31:13) over it, Glen's 1250 as
    # it ends (31:18); on P1_S2_액션 카메라 무시 (31:24.5) the kobolds' 1260 (31:28.5) and the FP notice (6010 / 6011,
    # 31:32)
    s = mission_room(10234)
    run_pending(s)
    obey(s)
    enter(s, ACTION_CAMERA)                         # ahead of the path check: it waits for it
    assert 2110 not in ids(s) and cutscenes(s) == [0]
    assert director.KEY_ACTION not in prompts(s).values()
    enter(s, CHECK1)
    assert ids(s)[-2:] == [1220, 2110] and cutscenes(s) == [0]       # the camera waits for the F
    assert list(prompts(s).values()).count(director.KEY_ACTION) == 1
    press(s, director.KEY_ACTION)
    run_pending(s)
    assert ids(s)[-4:] == [1220, 2110, 1240, 1250] and cutscenes(s) == [0, 2]
    assert said(s)[-3:] == [(THOMPSON, 2110), (20000, 1240), (GLEN, 1250)]
    assert highlights(s) == [(10009, 1), (10009, 0)]
    assert sent_before(s, director.ACT_CUTSCENE, 2, 1240) and not sent_before(s, director.ACT_CUTSCENE, 2, 2110)
    assert 1260 not in ids(s)
    enter(s, CORPSES)
    assert said(s)[-1] == (20001, 1260) and notices(s)[-1] == (6010, 6011)


def test_walking_on_without_the_f_takes_the_look_far_prompt_down_and_plays_no_camera():
    # the strip after the mark is P1_S2_액션 카메라 무시, "action camera: ignore": a hero who walks on without the F
    # gets the fight (1260, the FP notice) and no camera; the prompt comes down (0x50c3) and a late F plays nothing
    s = mission_room(10234)
    run_pending(s)
    obey(s)
    enter(s, CHECK1)
    enter(s, ACTION_CAMERA)
    assert director.KEY_ACTION in prompts(s).values()
    enter(s, CORPSES)
    assert director.KEY_ACTION not in prompts(s).values()
    assert said(s)[-1] == (20001, 1260) and notices(s)[-1] == (6010, 6011)
    assert 2 not in cutscenes(s) and 1240 not in ids(s) and 1250 not in ids(s)
    pid = next(struct.unpack("<IBI", bytes(w.buf))[1] for w in s.sent if w.proto == game.S2C_KEY_PROMPT
               and struct.unpack("<IBI", bytes(w.buf))[0] == director.KEY_ACTION)
    director.on_prompt(s, pid)                      # a late answer to the prompt taken down
    run_pending(s)
    assert 2 not in cutscenes(s)


def test_the_fp_notice_held_behind_the_fights_call_comes_before_the_bridge_warning():
    # the tape: 1260 (31:28), the FP notice 6010 / 6011 (31:32), then, the corpse kobolds and the bridge front down,
    # the Hero Support notice 6004 / 6005 and Glen's 1270 (32:02). Both fall while 1260 still shows: the FP notice, held
    # behind 1260 since its step, still comes first (the queue's order: director._after_lines / _take_held)
    s = mission_room(10234)
    run_pending(s)
    obey(s)
    for place in (CHECK1, ACTION_CAMERA):
        enter(s, place)
    press(s, director.KEY_ACTION)
    run_pending(s)
    wake_force(s, 20011)
    b = director.bound(10234, CORPSES)
    walk(s, b["BoundCenterX"], b["BoundCenterZ"])  # the fight's call, 1260, queued behind the camera's lines
    down_all(s, force_of(s, 20010) + force_of(s, 20011))              # before 1260's timer runs
    run_pending(s)
    assert notices(s)[-2:] == [(6010, 6011), (6004, 6005)] and said(s)[-1] == (GLEN, 1270)
    assert sent_notice_before(s, 6004, 1270) and ids(s).index(1260) < ids(s).index(1270)


def test_the_kobold_commanders_force_is_called_out_when_it_comes_and_glen_moves_on_when_it_falls():
    # force 20013 (the kobold commander 20155): Thompson's 1290, the commander's 1300, the vitality notice (6020 /
    # 6021); its fall ("Defeat Enemy Commander" 32:57.0): Glen's "Kobold archers in the rear. Quickly! Take care of
    # them!" (1310, 32:58.0); the archers in the rear (F20014) down (the target frame gone 33:24.5): "We took care of
    # them all. Now, let's move again!" (1340, 33:26.5); hand-read in build/order-a
    s = mission_room(10234)
    run_pending(s)
    wake_force(s, 20013)
    run_pending(s)
    assert said(s)[-2:] == [(THOMPSON, 1290), (20155, 1300)] and notices(s)[-1] == (6020, 6021)
    wake_force(s, 20014)
    run_pending(s)
    assert 1310 not in ids(s)                       # not at the archers' coming any more
    force = force_of(s, 20013)
    down_all(s, force[:-1])
    run_pending(s)
    assert 1310 not in ids(s) and 1340 not in ids(s)
    down_all(s, force[-1:])
    run_pending(s)
    assert said(s)[-1] == (GLEN, 1310) and 1340 not in ids(s)
    down_all(s, force_of(s, 20014))
    run_pending(s)
    assert said(s)[-1] == (GLEN, 1340) and highlights(s)[-1] == (10014, 1)


def test_the_rear_archers_felled_first_leave_glens_two_lines_in_the_tapes_order():
    # a player who fells the archers in the rear (F20014) before the commander's force: 1310 and 1340 come with the
    # commander's fall, in that order, once each
    s = mission_room(10234)
    run_pending(s)
    wake_force(s, 20013)
    wake_force(s, 20014)
    run_pending(s)
    down_all(s, force_of(s, 20014))
    run_pending(s)
    assert 1340 not in ids(s) and 1310 not in ids(s)
    down_all(s, force_of(s, 20013))
    run_pending(s)
    assert ids(s)[-2:] == [1310, 1340] and ids(s).count(1340) == 1


def down_every_enemy(s):
    """Every enemy up to the troll's force: its fall wins the room (WIN = "table"), whatever still stands."""
    for _ in range(100):
        if 20082 in s.data.get("down", ()):
            break
        alive = [u for u, z in s.data["zone_troops"].items() if game.hostile(z) and u not in s.data.get("down", set())]
        if not alive:
            if not s.data["waves"]:
                break
            run_pending(s)                          # a held force comes with its step's lines: the tank F20074 after
            continue                                # the sorcerer's 2380 (HOLD)
        down_all(s, alive)


def test_the_ending_scene_is_sent_with_its_cast_in_the_room_after_the_lines(monkeypatch):
    # 13 is 13_EndScene: slot 13 of the map's cutscene list 1_GrayrockFortress.csset. The client plays the list's
    # entries by position (0x1408ad590 loads them in order; 0x140b6ce80 indexes the player's scene vector), and
    # 13_StartCut is not in the list. Its ACTOR tracks bind Glenn_1 19500, Thom_1 19501, Golden_1 19502 and Human_MG
    # 19503 (F19500, allies the zone starts inactive). A missing one leaves the scene at black for ever, as 11_Kobold
    # was left live on 2026-09-30. They come in with the scene, after Thompson's and Glen's lines (3130-3150); the
    # scene's script enables their force at 0 s
    s = mission_room(10234)
    run_pending(s)
    seen = rooms_at_cutscenes(monkeypatch)
    down_every_enemy(s)
    assert not any(slot == 13 for slot, _ in seen)
    run_pending(s)
    [room] = [room for slot, room in seen if slot == 13]
    assert {19500, 19501, 19502, 19503} <= room
    assert not sent_before(s, director.ACT_CUTSCENE, 13, 3150)


def test_the_fortress_is_won_when_the_trolls_force_falls():
    # the tape: the troll at 2 hp under the finisher at 42:37 with "Eliminate the enemy (Complete)" on the panel, 3130 at
    # 42:38, the ending from there, no walk back. Leg 5: every hostile had to fall, so the player went back for F20023,
    # the wall sorcerer and the wolves
    s = mission_room(10234)
    run_pending(s)
    game.spawn_force(s, 20080)
    run_pending(s)
    assert any(t.get("ForceNum") == 20023 for w in s.data.get("waves", ()) for t in w)
    down_all(s, [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == 20080])
    run_pending(s)
    assert s.data["mission_won"] and cutscenes(s)[-1] == 13


def use_prop(s, prop):
    role = game.make(NoSave(), 0)
    role.handlers[game.C2S_PROP_CAST](s, pkt(game.C2S_PROP_CAST, struct.pack("<H", 0) + obf.u32(prop)))
    role.handlers[game.C2S_PROP_CAST_DONE](s, pkt(game.C2S_PROP_CAST_DONE, b"\0\0" + obf.u32(prop)))


def test_the_battlement_archers_open_fire_after_the_left_flank_wherever_the_hero_walks():
    # the tape: the left flank at 35:38.5, the archers' shots and 2150 at 36:11-36:12; they stand at x 123,500, out of
    # WAKE_RANGE from the straight way to the inner gate, and 2150-2170 and the Troop skill notice went with them
    s = mission_room(10234)
    run_pending(s)
    assert not any(t.get("ForceNum") == 20052 for t in s.data["zone_troops"].values())
    wake_force(s, 20051)
    run_pending(s)
    assert any(t.get("ForceNum") == 20052 for t in s.data["zone_troops"].values())
    assert 2150 in ids(s) and (6026, 6027) in notices(s)


def test_the_crystal_stones_complete_use_interact():
    # the tape: "You can interact with the Crystal Stones through the F key." (6017, 39:43) with "Use Interact" on the panel,
    # complete by 40:40. Leg 5 and the run of 2026-11-05: the cast went through (0x5094-0x5097) and the panel stayed
    s = mission_room(10234)
    run_pending(s)
    bound = next(b for b in zone.for_spot(10234)["EventBound"] if b["EventBoundID"] == 10227)
    walk(s, bound["BoundCenterX"], bound["BoundCenterZ"])
    run_pending(s)
    assert 420 not in done(s)
    use_prop(s, 11011)
    run_pending(s)
    assert done(s).count(420) == 1


def test_a_crystal_used_before_the_lesson_counts_when_the_lesson_comes():
    s = mission_room(10234)
    run_pending(s)
    use_prop(s, 11000)
    run_pending(s)
    assert 420 not in done(s)
    bound = next(b for b in zone.for_spot(10234)["EventBound"] if b["EventBoundID"] == 10227)
    walk(s, bound["BoundCenterX"], bound["BoundCenterZ"])
    run_pending(s)
    assert done(s).count(420) == 1


def test_the_ending_plays_before_the_victory_window():
    # The shipped scene has a last fade command at46.730s; the previous native
    # run returned control46.94s after receipt. Do not restore the picture at46s.
    ending = next(st for st in director.script(10234) if st['on'] == 'won')
    length = next(a[2] for a in ending['do'] if a[:2] == ('cutscene', 13))
    assert length > 46.94
    # the ending plays first: Thompson's 3130, Glen's 3140 / 3150, 13_EndScene (19500-19550), then one victory window
    s = mission_room(10234)
    run_pending(s)
    down_every_enemy(s)
    assert 20082 in s.data["down"]                  # the Mountain Troll fell
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) and not s.data.get("mission_won")
    run_pending(s)
    lines = [line for _, line in said(s)]
    assert [line for line in lines if line in (3130, 3140, 3150)] == [3130, 3140, 3150] and cutscenes(s)[-1] == 13
    window = [i for i, w in enumerate(s.sent) if w.proto == game.S2C_MISSION_COMPLETE]
    assert len(window) == 1 and s.data["mission_won"]
    assert window[0] > max(i for i, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION
                           and bytes(w.buf)[:4] == director.ACT_CUTSCENE.to_bytes(4, "little"))
    # 13_EndScene deliberately ends with a black fade. Native 2026-10-09 kept
    # ShowLoadingWait over the result/cards until its240s timeout. Restore the
    # picture after the complete scene and before showing the result.
    ending_at = max(i for i, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION
                    and bytes(w.buf)[:4] == director.ACT_CUTSCENE.to_bytes(4, 'little'))
    fades = [i for i, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION
             and bytes(w.buf) == struct.pack('<4I', game.ACT_FADE, 1, 0, 1)]
    assert any(ending_at < i < window[0] for i in fades)
    s.state = NoSave()
    game.mission_troop_down(s, NoSave(), 20082)     # a late report of a fallen troop changes nothing
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1


def test_the_f4_lesson_waits_for_f4_then_the_troops_move_out():
    # live 2026-09-28 18:41 (captures/gr_now.png): "[F4] Select your Hero and entire Troop." still up 4 min after it
    # showed. The original's 1_F4_Check (planning/scripts/cutscenes.json): 13401's page 0 is the client's (F), then
    # it waits for KEY_Select_AllTroop (F4) and completes page 1. The footage (part 2 30:40-30:48): the F page, the F4
    # page, the box gone and "Select Entire Troop (Complete)" at 30:46, then Glen's "Everyone, let's move!" (1210)
    s = mission_room(10234)
    run_pending(s)
    assert tutorials(s) == ["134_SelectTroopSlot4"] and 1210 not in [line for _, line in said(s)]
    [(serial, cond, args)] = queries(s)
    assert cond == director.COND_TUTORIAL_PAST and args == b"134_SelectTroopSlot4\0" + struct.pack("<i", 0)
    press(s, 0x33)                                    # before its page: no prompt, nothing
    answer(s, serial, False)                          # still on its F page: asked again, nothing prompted
    run_pending(s)
    assert 0x33 not in prompts(s).values() and closes(s) == []
    [(serial, _, _)] = [q for q in queries(s) if q[0] != serial]
    answer(s, serial, True)
    assert 0x33 in prompts(s).values()
    press(s, 0x34)                                    # ` (the hero alone): not what it asks
    run_pending(s)
    assert closes(s) == [] and 410 not in done(s) and 1210 not in [line for _, line in said(s)]
    press(s, 0x33)                                    # F4: KEY_Select_AllTroop
    assert closes(s) == [director.ACT_FINISH_TUTORIAL] and done(s) == [410]    # two pages: closed (0xc898 would
    run_pending(s)                                                               # show page 1 again)
    assert said(s)[-1] == (GLEN, 1210) and 1220 not in ids(s)                  # 1220 waits for the path check


def test_finisher_pages_close_only_after_native_completion_and_execution_completes_the_objective():
    # Native 2026-10-09: both F pages completed (id13403,page1,done1), but the
    # final banner stayed visible. Completion and dismissal are separate operations.
    # First identify the last page so an earlier tutorial's done flag cannot close it.
    s = mission_room(10234)
    obey(s)                                           # the F4 lesson
    wake_force(s, 20080)
    top = s.data["battle"].troops[TROLL]["max"]
    asked, shut = len(queries(s)), len(closes(s))
    director.on_hp(s, TROLL, top // 20, top)
    run_pending(s)
    assert tutorials(s)[-1] == "134_GroggyFinish"
    serial, condition, args = queries(s)[-1]
    assert len(queries(s)) == asked + 1
    assert condition == director.COND_TUTORIAL_PAST
    assert args == b'134_GroggyFinish\0' + struct.pack('<i', 0)
    assert len(closes(s)) == shut
    answer(s, serial, True)                           # page1, not yet completed
    serial, condition, args = queries(s)[-1]
    assert condition == 0xc760 and args == b''        # original native completed flag
    answer(s, serial, False)
    run_pending(s)
    assert len(closes(s)) == shut                    # waiting is not completion
    serial = queries(s)[-1][0]
    assert (6018, 6019) not in notices(s)             # the original: the notice once the pages are done
    answer(s, serial, True)                           # second F completed page1
    assert closes(s)[shut:] == [director.ACT_FINISH_TUTORIAL]
    run_pending(s)                                    # (a notice waits for a line still showing)
    assert notices(s)[-1] == (6018, 6019)             # "Finishing Attack: Press E" (frames 42:31.5 -> 42:32.5)
    answer(s, serial, True)                           # duplicate cannot close again
    assert len(closes(s)) == shut + 1
    assert 430 not in done(s)
    status.execution(s, TROLL, 31, game.send_troop_hp, lambda s, u: game.mission_troop_down(s, NoSave(), u))
    assert 430 in done(s)


def test_a_troll_felled_without_the_finishing_attack_leaves_the_lesson_open():
    s = mission_room(10234)
    obey(s)
    wake_force(s, 20080)
    top = s.data["battle"].troops[TROLL]["max"]
    director.on_hp(s, TROLL, top // 20, top)
    run_pending(s)
    game.mission_troop_down(s, NoSave(), TROLL)
    run_pending(s)
    assert 430 not in done(s)


def test_victory_dismisses_an_unfinished_lesson_without_crediting_the_finisher():
    # Native07:03: a companion killed the troll, then the unfinished F banner
    # covered13_EndScene and rewards. Won rooms no longer poll lesson conditions.
    s = mission_room(10234)
    obey(s)
    wake_force(s, 20080)
    top = s.data["battle"].troops[TROLL]["max"]
    director.on_hp(s, TROLL, top // 20, top)
    run_pending(s)
    assert tutorials(s)[-1] == "134_GroggyFinish"
    shut = len(closes(s))
    down_every_enemy(s)
    run_pending(s)
    assert s.data["mission_won"]
    assert closes(s)[shut:] == [director.ACT_FINISH_TUTORIAL]
    assert 430 not in done(s)                        # dismissal is not execution
    packets = [(i, bytes(w.buf)) for i, w in enumerate(s.sent)
               if w.proto == game.S2C_SCRIPT_ACTION]
    close_at = max(i for i, b in packets if b[:4] == director.ACT_FINISH_TUTORIAL.to_bytes(4, "little"))
    scene_at = next(i for i, b in packets if b[:8] == struct.pack("<II", director.ACT_CUTSCENE, 13))
    assert close_at < scene_at


def force_of(s, force):
    return [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == force]


def test_glen_warns_of_the_bridge_once_the_corpse_kobolds_and_the_bridge_front_have_fallen():
    # the tape (frames 31:50-32:01; harness report row #5, ours on P1_S2_다리 코볼트 전투, entered 32:08.5; the harness's
    # "after 1260, 30 s" is its no-rule gap: the kobolds fought beside the hero are inside his sight halo, where the
    # minimap reader sees no red mark): the corpse fight's last kobold falls at 31:58-31:59, Glen's "Don't let your guard
    # down! There are more Kobolds across the bridge!" (1270) is up at 32:00, the Hero Support notice (6004 / 6005) at
    # 32:01. The corpse kobolds (F20010) and those before the bridge (F20011, 다리 앞 코볼트): whichever falls last
    for order in ((20010, 20011), (20011, 20010)):
        s = mission_room(10234)
        run_pending(s)
        obey(s)
        for place in (CHECK1, ACTION_CAMERA, CORPSES):              # the fight's call first (1260)
            enter(s, place)
        wake_force(s, 20011)
        down_all(s, force_of(s, order[0]))
        run_pending(s)
        assert 1270 not in ids(s)
        down_all(s, force_of(s, order[1]))
        run_pending(s)
        assert said(s)[-1] == (GLEN, 1270) and notices(s)[-1] == (6004, 6005)
        enter(s, "P1_S2_다리 코볼트 전투")                # its lines, not on the tape, stay on the bridge
        assert ids(s)[-2:] == [1280, 1330] and ids(s).count(1270) == 1


def test_the_entrance_kobolds_call_out_as_the_hero_comes_up_to_the_hill():
    # the tape (frames 33:27-33:44; harness report row #8, ours at the wake of F20091, the bridge's looters: 32:16.5 on
    # the tape's path, 75 s early): after the bridge Glen's "We took care of them all" (1340, 33:27) with the ground mark
    # of P1_S2_입구 진입 (glowing 33:28-33:31, walked into at 33:31, the area entered at 33:30.5); the entrance's
    # Mountain Kobold Commander (20120, F20025) "Find shiny things!" (1350, 33:34) as the hero enters 10150 (33:32.5), a
    # looting kobold's (F20020) "Keeeek! H-Humans!" (1360, 33:39) at 10128 (33:38.5)
    s = mission_room(10234)
    run_pending(s)
    wake_force(s, 20013)
    wake_force(s, 20014)
    run_pending(s)
    down_all(s, force_of(s, 20013) + force_of(s, 20014))
    run_pending(s)
    assert said(s)[-1] == (GLEN, 1340) and highlights(s)[-1] == (10014, 1)
    wake_force(s, 20091)
    run_pending(s)
    assert 1350 not in ids(s) and 1360 not in ids(s)
    enter(s, "P1_S2_입구 진입")
    assert highlights(s)[-1] == (10014, 0)
    enter(s, 10150)
    assert said(s)[-1] == (20120, 1350)
    enter(s, 10128)
    uid, line = said(s)[-1]
    assert line == 1360 and s.data["zone_troops"][uid]["ForceNum"] == 20020


def test_the_tanks_call_waits_for_the_looters_at_10128():
    # the tape: the looters' "Keeeek! H-Humans!" (1360, 33:38.75) at 10128, then Thompson's "General! Kobold tank!"
    # (4000, 33:44), the tank rolling into view 33:47-33:49. A tank in first (its proximity, or our fallback wake once
    # the field is empty, as the headless walker's instant kills make it) keeps its lines for after 1360
    s = mission_room(10234)
    run_pending(s)
    wake_force(s, 20021)
    run_pending(s)
    assert 4000 not in ids(s)
    enter(s, 10150)
    assert 4000 not in ids(s)
    enter(s, 10128)
    assert ids(s)[-4:] == [1360, 4000, 4010, 4020]


def test_the_tank_is_listed_before_the_kobold_leaders_strip_as_the_tape_plays_them():
    # the tape: the tank's fight (4000 33:44 - 4040 34:11) before the kobold leader's strip (1390, 34:32): the table
    # lists the story in that order, the order the headless walker takes it in (tools/playthrough.py headless)
    steps = director.script(10234)
    at = lambda pred: next(i for i, st in enumerate(steps) if pred(st))
    tank = at(lambda st: st["on"] == "down" and st.get("troop") == 20183)
    leader = at(lambda st: st.get("id") == "kobold leader")
    looters = at(lambda st: st.get("id") == "looters")
    assert looters < tank < leader


def test_the_fortress_gate_is_marked_and_glen_sends_everyone_in_after_the_mid_cutscene():
    # the tape (frames 34:24-35:24; harness report rows #13 and #14, ours: 1400 at P1_S2_다음 서브 with the cutscene, and
    # 2100 on 10156, which the hero never enters on the tape): Glen's "The Grayrock Fortress is right in front of us!
    # Forward!" (1400, 34:41) as the hero enters 10147 (34:41.5), with the ground mark ahead (34:41-34:46) walked into as
    # he enters P1_S2_다음 서브 (34:46.5): the mark down, 3_Mid_CutSCene (34:48-35:16), "We're entering the Fortress now.
    # Watch out for hidden enemies!" (2100) right after it (35:18) with the next mark, 10079's (glowing 35:19-35:23)
    s = mission_room(10234)
    run_pending(s)
    enter(s, 10147)                                 # (the entrance hill's F20021 wakes there too: its 4000-4020 after)
    assert (GLEN, 1400) in said(s) and highlights(s)[-1] == (10017, 1) and 3 not in cutscenes(s)
    enter(s, "P1_S2_다음 서브")
    assert cutscenes(s)[-1] == 3 and highlights(s)[-2:] == [(10017, 0), (10079, 1)]
    assert said(s)[-1] == (GLEN, 2100) and sent_before(s, director.ACT_CUTSCENE, 3, 2100) and 121 in done(s)


def test_the_courtyard_scene_plays_thompsons_call_and_the_gate_sorcerers_taunt():
    # the tape (frames 35:19-35:45; harness report row #15, ours: 2120 at the wake of F20050 by its commander 20021): the
    # hero reaches the mark on 10079 (35:23, entering it 35:24.5), 6_Troll_Come plays (the minimap hidden 35:26.5-35:37.5,
    # its 12 s) with Thompson's "General! Kobolds!" (2110 a second time, 35:28-35:32) and the Mountain Kobold Sorcerer's
    # "Filthy Humans, come here now! Crush their skulls!" (2120, 35:34-35:38) over it: the sorcerer at the courtyard's
    # far gate is 20174 (F20101; the zone's other sorcerers are the inner castle's 20078 and the troll's 20081)
    # (the F prompt "Look far" at the mark 35:24.0-35:25.25, the scene from 35:26.5: hand-read in build/order-a)
    s = mission_room(10234)
    run_pending(s)
    enter(s, "P1_S2_다음 서브")
    assert 6 not in cutscenes(s)
    enter(s, 10079)
    assert highlights(s)[-1] == (10079, 0) and 6 not in cutscenes(s) and 20174 in s.data["zone_troops"]
    assert director.KEY_ACTION in prompts(s).values()
    press(s, director.KEY_ACTION)
    run_pending(s)
    assert cutscenes(s)[-1] == 6
    assert said(s)[-2:] == [(THOMPSON, 2110), (20174, 2120)]
    assert sent_before(s, director.ACT_CUTSCENE, 6, 2110)


def test_the_left_flanks_attack_takes_the_unanswered_courtyard_prompt_down():
    # ours: no strip of the zone is named for the second camera; the left flank's attack (F20051's wake, 2130 "Kobolds
    # are coming from the left flank!") ends the offer: no scene in the fight
    s = mission_room(10234)
    run_pending(s)
    enter(s, "P1_S2_다음 서브")
    enter(s, 10079)
    assert director.KEY_ACTION in prompts(s).values()
    wake_force(s, 20051)
    run_pending(s)
    assert director.KEY_ACTION not in prompts(s).values() and 6 not in cutscenes(s)
    assert [x for x in ids(s) if x in (2130, 2140)] == [2130, 2140]


def test_the_bridge_warning_waits_for_the_corpse_fights_call():
    # the tape: the corpse fight's call (1260, 31:28.5) comes before its end and Glen's bridge warning (1270, 32:00);
    # the kobolds felled from outside P1_S2_액션 카메라 무시 keep that order
    s = mission_room(10234)
    run_pending(s)
    obey(s)
    wake_force(s, 20011)
    down_all(s, force_of(s, 20010) + force_of(s, 20011))
    run_pending(s)
    assert 1270 not in ids(s)
    enter(s, CHECK1)
    enter(s, ACTION_CAMERA)
    enter(s, CORPSES)
    assert ids(s).index(1260) < ids(s).index(1270) and ids(s).count(1270) == 1


def test_thompson_sees_the_caged_wolves_as_the_hero_comes_to_their_gate():
    # the tape: "There are Wolves in front of us!" (2300, 37:03) as the hero enters 10063 (37:02.5), Glen's 2310 (37:07)
    # and 2320 (37:12) after it (harness report row #20; ours at the wake of F20060, 36:58.5 on the tape's path)
    s = mission_room(10234)
    run_pending(s)
    wake_force(s, 20060)
    run_pending(s)
    assert 2300 not in ids(s)
    enter(s, 10063)                                 # (F20051 wakes there too: its 2130 / 2140 after)
    first = ids(s).index(2300)
    assert said(s)[first:first + 3] == [(THOMPSON, 2300), (GLEN, 2310), (GLEN, 2320)]


def test_the_inner_castle_sorcerer_taunts_in_his_scene_and_thompson_restores_the_troop():
    # the tape (frames 37:24-37:52; harness report rows #23, #24 and #35): the hero enters 10230 (37:28.5), Thompson's
    # "There are Kobolds in front of us!" (2330, 37:29), the sorcerer's scene (the minimap hidden 37:35.5-37:43.5, the
    # camera on the wall and his "Ha, ha! You managed to come this far." 2340 at 37:38.5; 5_Boss_CutScene or
    # 4_Kobold_Jump, 8 / 8.5 s with the same script, both leaving the hero at 10168, where the minimap has him at
    # 37:44.5), Glen's "The Kobold sorcerer is using magic!" (2350, 37:44), the pentacle notice (6008 / 6009, 37:45) and
    # Thompson's "Please pay attention to your Troop's HP as well. I'll restore it for now." (1010, 37:45) with the F1
    # troop's hp 5,423 -> 8,330 on the HUD at 37:45: a line of the scene with the troop at ~64 %, not a threshold (ours:
    # Glen's 1010 at each fall below 30 %, "the threshold is ours")
    s = mission_room(10234)
    run_pending(s)
    t = s.data["battle"].troops[10073]
    top = sum(t["units"])
    for i in range(len(t["units"]) - 1):
        t["units"][i] = 1
    director.on_hp(s, 10073, sum(t["units"]), top)
    run_pending(s)
    assert 1010 not in ids(s) and sum(t["units"]) < top // 2           # no hp step for it
    enter(s, 10230)
    assert SORCERER in s.data["zone_troops"] and cutscenes(s)[-1] == 5
    assert said(s)[-4:] == [(THOMPSON, 2330), (SORCERER, 2340), (GLEN, 2350), (THOMPSON, 1010)]
    assert notices(s)[-1] == (6008, 6009) and sum(t["units"]) > top * 0.9
    # the notice slides in under Glen's 2350 box (37:44.5), Thompson's 1010 after it (37:45.0): hand-read in
    # build/order-a, frames qeeQjhgO8ss_2259_2267_frames_2 f_00009-f_00013
    assert not sent_notice_before(s, 6008, 2350) and sent_notice_before(s, 6008, 1010)
    assert sent_before(s, director.ACT_CUTSCENE, 5, 2340) and not sent_before(s, director.ACT_CUTSCENE, 5, 2330)


def test_thompsons_scene_heals_both_owned_infantry_and_borrowed_archers():
    # Original f_01132 -> f_01134: F1 infantry5373 -> full, F2 archers605 ->2608.
    # The old fixture had no owned troop, hiding the missing F1 heal.
    from test_army import army, entered
    c, _ = army(1, level=6)
    _, s = entered(10234, c)
    battle = s.data["battle"]
    tops = {uid: sum(battle.troops[uid]["units"]) for uid in (1, 10073)}
    for uid in tops:
        t = battle.troops[uid]
        t["units"] = [max(1, hp // 2) for hp in t["units"]]
    enter(s, 10230)
    assert {uid: sum(battle.troops[uid]["units"]) for uid in tops} == tops


def test_the_fortress_transition_brings_the_owned_troop_to_its_original_mark():
    # Native05:44: hero/borrowed moved inside, owned1 stayed at87068,139764.
    # The table's inactive10072 placeholder is replaced by the real deck troop.
    from kuf2 import obf
    from test_army import army, entered
    c, _ = army(1, level=6)
    _, s = entered(10234, c)
    s.sent.clear()
    enter(s, "P1_S2_다음 서브")
    moved = {}
    for w in s.sent:
        if w.proto == game.S2C_TROOP_BACK:
            b = bytes(w.buf)
            moved[int.from_bytes(b[7:9], "little")] = obf.dec_pos_xz(b[:4], b[6])
    mark = director.bound(10234, "P2_S2_영웅 부대1 위치1")
    assert moved.get(1) == (round(mark["BoundCenterX"]), round(mark["BoundCenterZ"]))
    assert 10073 in moved


@pytest.mark.parametrize("executing", [True, False])
def test_a_native_lethal_finisher_completes_the_lesson_and_grants_its_buff_once(executing):
    # Native05:59:43:379's ordinary damage killed the troll before FINISH_KILL,
    # losing objective430 and FINISH_DEAD_PROC. Use the public cast/execute path.
    from test_army import army, entered
    from test_battle import added, execute, feed, use_ability
    c, _ = army(level=6)
    c["class"] = 3
    role, s = entered(10234, c)
    wake_force(s, 20080)
    troll = s.data["battle"].troops[TROLL]
    troll["units"] = [1]
    if executing:
        status.apply(s, [TROLL], 31, 1, 0)
    s.sent.clear()
    serial = use_ability(role, s, 379, [TROLL])
    assert troll["units"] == [0] and feed(s) == [(0, TROLL)]
    assert done(s).count(430) == int(executing)
    assert ({6410, 6411} <= {a[0] for a in added(s)}) == executing
    grants = len(added(s))
    execute(role, s, serial, [TROLL])
    assert done(s).count(430) == int(executing) and feed(s) == [(0, TROLL)]
    assert len(added(s)) == grants


def test_the_tank_behind_comes_with_the_released_wolves_not_as_the_hero_passes_it():
    # the tape: the tank 20184 (F20074, by the wolves' gate) shows its first red mark at 38:23.5, between Glen's "The
    # Wolves have been let loose!" (2380, 38:21) and "Drat! The wolves that we left behind will come for us, too!"
    # (2470, 38:26); "Wolves and tanks behind us!" (2490, 38:30) and the archers' notice (6028 / 6029, 38:34) close one
    # chain from the sorcerer's "Release the Wolves!" (2360, 38:12) (harness report row #27; ours at F20074's wake, the
    # hero passing 6,000 from the tank at 37:04.5 on the tape's path, 81 s early)
    s = mission_room(10234)
    run_pending(s)
    walk(s, 118493, 155974 + 2000)                  # beside the tank's stand
    run_pending(s)
    assert TANK not in s.data["zone_troops"] and 2470 not in ids(s)
    wake_force(s, 20073)
    top = s.data["battle"].troops[SORCERER]["max"]
    director.on_hp(s, SORCERER, top * 4 // 10, top)
    run_pending(s)
    assert TANK in s.data["zone_troops"]
    assert [x for x in ids(s) if x in (2360, 2370, 2380, 2470, 2490)] == [2360, 2370, 2380, 2470, 2490]
    assert notices(s)[-1] == (6028, 6029)


def test_thompson_sees_the_sorcerer_run_within_the_wolves_chain_once():
    # the tape (frames 38:13-38:30, the chat log at 38:24): "These blasted Humans! Release the Wolves!" (2360),
    # Thompson's "General, the sorcerer is running away!" (2370, 38:17-38:19), Glen's "The Wolves have been let loose!"
    # (2380, 38:24): one chain, not a later hp threshold of the sorcerer's
    s = mission_room(10234)
    run_pending(s)
    wake_force(s, 20073)
    top = s.data["battle"].troops[SORCERER]["max"]
    director.on_hp(s, SORCERER, top * 4 // 10, top)
    run_pending(s)
    director.on_hp(s, SORCERER, top // 10, top)
    run_pending(s)
    assert ids(s).count(2370) == 1 and ids(s).index(2360) < ids(s).index(2370) < ids(s).index(2380)


def test_thompson_spots_the_crystal_stones_past_the_obstacles_and_glen_sends_them_to_check():
    # the tape (frames 39:22-39:50; harness report row #28 and the parts12 builder's case: 2420 at 39:37, 4.5 s before
    # 10227): the barricade broken (39:33-39:35), the hero into 10065 (39:33.5), Thompson's "Hey, look! There are some
    # shining ores scattered over there!" (2420, 39:37) with the ring round the Crystal Stones' cart (10070's point,
    # glowing 39:37-39:46); into 10227 (39:41.5), Glen's "Crystal Stones, I bet. Commander! Thompson! Check them out."
    # (2430, 39:42) and the Interact notice (6016 / 6017, 39:44); the mark goes at the cart
    s = mission_room(10234)
    run_pending(s)
    enter(s, 10065)
    assert said(s)[-1] == (THOMPSON, 2420) and highlights(s)[-1] == (10070, 1) and 2430 not in ids(s)
    enter(s, 10227)
    assert ids(s)[-4:] == [2430, 2440, 2450, 2460] and notices(s)[-1] == (6016, 6017)
    enter(s, 10070)
    assert highlights(s)[-1] == (10070, 0)


def test_the_troll_yard_scene_starts_as_the_hero_comes_down_the_rails():
    # the tape (harness report row #29 and the parts12 builder's case): 11_Kobold (40:06-40:22, the minimap hidden
    # 40:07.5-40:22.5) as the hero enters 10195 (40:05.5); ours waited on 10060, 2,074 from where he stands then (the
    # scene's own script moves him into it 580 ms in)
    s = mission_room(10234)
    run_pending(s)
    enter(s, 10060)
    assert 11 not in cutscenes(s)
    enter(s, 10195)
    assert cutscenes(s)[-1] == 11 and 122 in done(s)


def test_the_troll_yard_scene_is_sent_with_its_troll_and_sorcerer_in_and_their_call_follows_it(monkeypatch):
    # live 2026-09-30 15:25 (qwe123; captures/logs/client_20260930_150936.log): 11_Kobold, sent at 15:25:20.683, never
    # started. The client faded to black and called ShowLoadingWait every frame from 15:25:24.7; the fade's own 240 s
    # limit brought the picture back at 15:29:21.7, with the scene still "playing" and the input locked. The scene's
    # ACTOR tracks bind the sorcerer 20081 (Ko_Ma) and the troll 20082 (TROLL), whose force F20080 our table only
    # brought in later, when the hero came near after the scene. A track whose troop the client does not have never
    # loads (TrackActorBase::IsCompleteLoad 0x140941f70), and the player does not start the scene until every track
    # has (0x1408b3360 -> 0x1408ac020). Their "Kill all the Humans!" (3100) and the troll's 3110 play 4 s after the
    # scene (the tape: scene 40:06-40:22, 3100 at 40:26), not when the force comes in
    s = mission_room(10234)
    run_pending(s)
    assert TROLL not in s.data["zone_troops"]
    in_at_send = []
    send = game.send_actions

    def spy(room, *actions):
        in_at_send.extend({20081, TROLL} <= set(room.data["zone_troops"]) for a in actions
                          if list(a[:2]) == [director.ACT_CUTSCENE, 11])
        return send(room, *actions)
    monkeypatch.setattr(game, "send_actions", spy)
    enter(s, 10195)
    assert in_at_send == [True]
    assert [x for x in said(s) if x[1] in (3100, 3110)] == [(20081, 3100), (TROLL, 3110)]
    assert sent_before(s, director.ACT_CUTSCENE, 11, 3100)
    step = next(st for st in director.script(10234) if (st.get("do") or [()])[0] == ("say", 20081, 3100))
    assert step["on"] == "after" and step["s"] == 4


def test_glen_is_marked_as_he_leads_up_the_path_after_the_f4_key():
    # the tape (part 2, 30:46-30:49): the blue pillar and glow on Glen as he walks ahead after the F4 key, the client's
    # troop marker (ActGuiSetHighlightTroop 0xc7ba; the refinement builder "greyrock", frames); for about 3 s
    step = next(st for st in director.script(10234) if st.get("id") == "all troops")
    assert ("highlight troop", "글렌", 1, 3) in step["do"]


INNER_GATE = {20074, 20075, 20076, 20077, 20078, 20079}  # the prisons (type 396) of the wolves of F20060
INNER_YARD = {20080, 20081, 20082, 20083, 20084}         # and those of F20061, around the sorcerer's yard
CAGES = INNER_GATE | INNER_YARD


def prop_states(s):
    """{prop id: state} of the props a one-record 0x50d1 changed (game.switch_on), the last state of each."""
    out = {}
    for w in s.sent:
        b = bytes(w.buf)
        if w.proto == game.S2C_PROP_LIST and struct.unpack_from("<H", b)[0] == 1:
            r = read_prop(b[2:])
            out[r["id"]] = r["state"]
    return out


def release_the_wolves(s):
    wake_force(s, 20073)
    top = s.data["battle"].troops[SORCERER]["max"]
    director.on_hp(s, SORCERER, top * 4 // 10, top)
    run_pending(s)


def test_the_wolves_stay_caged_until_the_sorcerer_releases_them():
    # the tape: "Since they're caged, they're not a threat to us at the moment." (2320, 37:12); a wolf behind closed
    # bars to 38:11, the cage front down on "Release the Wolves!" (2360, frames 38:12-38:17), a wolf outside at 38:21.
    # Live 2026-11-05: a closed cage holds its wolves still with the hero 1,300 away (F20060's 20047 / 20048), an open
    # one lets them chase: their force's wake opened the cages at the hero's first pass, eight minutes early
    s = mission_room(10234)
    run_pending(s)
    wake_force(s, 20060)
    walk(s, 116900, 152600)                         # beside the cages (BARRIER_NEAR)
    run_pending(s)
    assert any(t.get("ForceNum") == 20060 for t in s.data["zone_troops"].values())
    assert not CAGES & set(prop_states(s))
    release_the_wolves(s)
    assert {p: prop_states(s).get(p) for p in CAGES} == {p: game.PROP_SWUNG for p in CAGES}


def test_the_cages_by_the_sorcerer_stay_shut_when_their_wolves_come_in():
    # the tape's wolf behind bars at 38:09 stands by the sorcerer's yard, seen as the hero fights there, so F20061 is in
    # its cages before the release. Leg 5 (03:58:51): the five prisons opened with F20061's wake, 23 s before 2360
    s = mission_room(10234)
    run_pending(s)
    wake_force(s, 20061)
    walk(s, 129000, 155000)                         # the middle of the yard (BARRIER_NEAR of 20083)
    run_pending(s)
    assert any(t.get("ForceNum") == 20061 for t in s.data["zone_troops"].values())
    assert not INNER_YARD & set(prop_states(s))
    release_the_wolves(s)
    assert {p: prop_states(s).get(p) for p in INNER_YARD} == {p: game.PROP_SWUNG for p in INNER_YARD}


def wolves_in(s):
    wake_force(s, 20060)
    wake_force(s, 20061)
    run_pending(s)


def straight(s):
    return {a[2]: a[3] for a in acts(s, director.ACT_MOVE_STRAIGHT)}


def test_the_wolves_leave_their_cages_in_a_straight_line():
    # live 2026-11-05: an open cage is not enough. 12 of F20060's 18 wolf units stood on cells the client's pathfinder has
    # no route from, and stayed; ActTroopMoveToAreaIgnoringPolyline walked all of them out (ign.py: 20045's three stuck
    # units left OutOfTroop 6.5-7 s after it, positions continuous, no jump). The yard's own bounds: 10249 south, 10052
    # north, 10056 the middle of the sorcerer's yard
    s = mission_room(10234)
    run_pending(s)
    wolves_in(s)
    assert not straight(s)
    release_the_wolves(s)
    want = {20043: 10249, 20044: 10249, 20045: 10249, 20046: 10249, 20047: 10052, 20048: 10052}
    want |= {t: 10056 for t in range(20060, 20068)}
    assert straight(s) == want
    assert [a for a in acts(s, director.ACT_MOVE_STRAIGHT) if a[2] == 20045] == [
        [director.ACT_MOVE_STRAIGHT, 0, 20045, 10249, 0, director.MOVE_RUN]]


def test_a_wolf_killed_through_the_bars_gets_no_order():
    s = mission_room(10234)
    run_pending(s)
    wolves_in(s)
    s.data.setdefault("down", set()).update({20045, 20063})
    release_the_wolves(s)
    assert not {20045, 20063} & set(straight(s))


def test_the_cage_falls_on_the_sorcerers_order_and_the_wolves_go_with_the_next_line():
    # the tape: the cage front starts down on 2360 (38:12), is down by 38:17, a wolf outside at 38:21
    step = next(st for st in director.script(10234) if st["on"] == "hp" and st["troop"] == SORCERER and st["below"] == 50)
    kinds = [a[0] for a in step["do"]]
    said = step["do"].index(("say", 20078, 2360))
    assert set(kinds[:said]) == {"open"}
    assert kinds.index("march straight") > said


def test_the_wolves_left_behind_come_for_the_party():
    # "Drat! The wolves that we left behind will come for us, too!" (2470, 38:26). Live 2026-11-05: with the hero 8,000 away
    # 20047 / 20048 ran after him, the leashed 20043-20046 stood in the yard: the march is what makes the line true
    s = mission_room(10234)
    run_pending(s)
    wolves_in(s)
    release_the_wolves(s)
    gone = {a[2]: a[3] for a in acts(s, director.ACT_MOVE_TO_AREA) if a[2] in range(20043, 20049)}
    assert gone == {t: 10053 for t in range(20043, 20049)}


def test_a_cage_opens_in_the_state_that_shows_it_open():
    # live 2026-11-05 on prison 20075 (propset.py): state 0 closed with collision, 1 open with collision, 2 CLOSED to
    # look at without collision (the "closed-looking" cages of 2026-10-09), 3 open without collision
    s = mission_room(10234)
    game.switch_on(s, game.zone_prop(10234, 20075))
    assert prop_states(s)[20075] == game.PROP_SWUNG == 3
    wall = next(p for p in zone.for_spot(10234)["SmartPropData"] if p["SmartPropTypeID"] == 68)
    game.switch_on(s, wall)                         # the others as they were: state 2 takes their collision
    assert prop_states(s)[wall["SmartPropID"]] == game.PROP_OPEN == 2


def laid_out(s):
    """{troop: (direction byte, x, z)} of the S2C 0x50b7 records sent: byte 0 the direction, bytes 1-2 unread, then the 0x50c0
    position (4 packed bytes, i16 height, nibble byte), u16 troop (0x140cf4670)."""
    out = {}
    for w in s.sent:
        if w.proto == game.S2C_TROOP_PLACED:
            buf = bytes(w.buf)
            for i in range(struct.unpack_from("<H", buf)[0]):
                r = buf[2 + 12 * i:14 + 12 * i]
                out[struct.unpack_from("<H", r, 10)[0]] = (r[0], *obf.dec_pos_xz(r[3:7], r[9]))
    return out


def test_a_zone_troop_is_laid_out_at_the_zones_angle_as_it_comes_in():
    # 0x50cb has no direction, so the client builds a troop with its units on an axis-aligned square: in a narrow place that
    # puts units where the client's pathfinder has no route (live 2026-11-05: path 0 on every request from each stuck wolf,
    # the map of 0x1407a6970 from a grid of starts has every stuck unit on a dead cell and every free one on a live cell)
    s = mission_room(10234)
    run_pending(s)
    wake_force(s, 20060)
    assert not laid_out(s)                          # before its 0x50ab the client has no troop to lay out
    for uid in (20045, 20046, 20047, 20048):
        game.troop_bound(s, uid)
    assert {u: r[0] for u, r in laid_out(s).items()} == {20045: 224, 20046: 249, 20047: 64, 20048: 89}
    zt = s.data["zone_troops"]
    assert {u: r[1:] for u, r in laid_out(s).items()} == {u: (round(zt[u]["PosX"]), round(zt[u]["PosZ"])) for u in zt
                                                          if u in (20045, 20046, 20047, 20048)}


def test_the_angle_byte_turns_the_zones_compass_into_the_clients_circle():
    # zone Angle A: (sin A, 0, cos A) (0x140f685d0); 0x50b7 byte b: (cos, 0, sin) of b * 2 pi / 256 (0x140cf4828)
    assert [game.angle_byte(a) for a in (0, 90, 180, 270, 360)] == [64, 0, 192, 128, 64]
    for a in range(0, 360, 7):
        phi = game.angle_byte(a) * 2 * math.pi / 256
        assert abs(math.cos(phi) - math.sin(math.radians(a))) < 0.02 and abs(math.sin(phi) - math.cos(math.radians(a))) < 0.02
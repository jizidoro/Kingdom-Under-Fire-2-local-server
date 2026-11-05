"""Grey Rock Fortress 10234 (1_GrayrockFortress zone1), the director's table.
The original's script, from the playlist, with its storyboard and our marks: planning/scripts/missions/10234.md
(`py tools/mission_scripts.py 10234`).

Sources: the map's missiontext (lines 1000-4500, 10040-10470, 19000-19550; `py tools/recon/mission_sheet.py 10234`),
the zone's bounds and forces, the walkthrough (walkthrough_guide.txt L135-156: Glen and Thompson along, wolves,
"You really don't like Wolves, do you", the kobold tank and sorcerer, the Mountain Troll and the vitality tutorial at
10 %). The original's order and speakers checked against playthrough part 2 (planning/scripts/
10358-10233-10234-10235-10362_qeeQjhgO8ss_000.md, 29:46-43:36; read by video_script). Speakers: Thompson calls Glen "General", Glen calls the hero "Commander" (the lines' own words); kobold lines go
to a troop of the force that says them. Which bound or force starts each scene is ours, read from the bound names
(P1_S2_다리 코볼트 전투 "bridge kobold battle", P1_S2_입구 진입 "entrance approach", P1_S2_코볼트 리더 등장 "kobold
leader appears") and the place of the props the lines speak of (type 45 obstacles at (134.7k, 155.2k), type 481
crystal stones at (139k, 152.5k), type 541 mine carts in the troll's yard).

The lessons, as the original's lesson cutscenes ran them (planning/scripts/cutscenes.json) and the footage shows them
(part 2 30:40-30:48, 42:24-42:40): 1_F4_Check starts 134_SelectTroopSlot4, waits for its F page (the client's own),
then for KEY_Select_AllTroop (F4), then completes the last page; our step asks the client for that page (0xcb2b),
prompts F4 and closes the pop-up (0xc897: two pages, 0xc898 completes page 0 only). 7_Groggy_Finish's 134_GroggyFinish
has two F pages the client turns and completes itself: the server closes the banner after native completion; its panel line "Use
Finishing Attack" completes on the finishing attack (director "finish")."""
from ..director import COND_TUTORIAL_PAST as TUTORIAL_PAST, COND_TUTORIAL_COMPLETE, KEY_ACTION, KEY_SELECT_ALL_TROOP

GLEN, THOMPSON = "글렌", "톰슨"
# The panel as the original shows it (frames of playthrough part 2): under its title "Greyrock Fortress" (100, the red
# bar, 30:40), "Enter Greyrock Fortress" and the lesson "Select Entire Troop" at first (30:40; 120 "Identify who hanged
# the corpses" never shows), 121 complete and "Find Crystal Stone" inside the fortress (36:00), 122 complete and
# "Eliminate the enemy" at the troll's yard (40:40), the lessons "Use Interact" (by 40:40) and "Use Finishing Attack"
# (42:50), 123 complete at the end
PANEL = (100, ((110, (121,)), (200, (210,)), (400, (410,))))
ESCORT = {10000, 10001}          # Glen with his two troops, Thompson: they march to each story place and fight
# The tank F20074 (20184, by the wolves' gate) first shows on the tape's minimap at 38:23.5, with the sorcerer's chain
# of lines (2380 -> 2470); the hero passes 6,000 from it at 37:04.5, where our proximity wake would bring it in
HOLD = {20074}
# The refinement against playthrough part 2 (2026-09-30, the harness report captures/harness/10234_report.md "differs"
# rows): each step below says the tape time, what the frames or the minimap reads show, and which it came from
# ("frames": py -m video_script sheet over the cached video; "reads": the harness's channels file
# planning/playthrough/part_qeeQjhgO8ss.10234.channels.json; "rings" / "pillars": tools/harness/effects.read over the
# same span). Area marks ("highlight") only where the tape shows the ground glow and the hero walking into it as he
# enters that area; the player's own order pings on the minimap (37:11, 40:50) are not marks
CHECK1, ACTION_CAMERA = "P1_S2_영웅 체크1", "P1_S3_액션 카메라"    # the strips across the path out of the camp
FORTRESS = "P1_S2_다음 서브"                                         # the fortress gate: 3_Mid_CutSCene

STEPS = [
    # the opening cutscene 0_Start_CutScene (53 s, live 2026-09-28: the hanged corpses, Thompson and Glen voicing
    # 19000-19070), then the camp: move out (Glen's lines 1200 / 1210, Thompson's to the hero 1201)
    {"on": "start", "id": "camp", "do": [
        ("cutscene", 0, 53), ("say", GLEN, 1200), ("say", THOMPSON, 1201),
        ("tutorial", "134_SelectTroopSlot4")]},                                              # "Press F4 ..."
    # "Select your Hero and entire Troop.": its F page the client's, then F4; the box closes and the panel's "Select
    # Entire Troop" completes (30:46), then the troops move out (1210 "Everyone, let's move!", 30:48). Live
    # 2026-09-28 18:41 (captures/gr_now.png) the box stayed up 4 min, mid-fight
    {"on": "cond", "cond": (TUTORIAL_PAST, "134_SelectTroopSlot4", 0), "needs": "camp", "id": "select all"},
    # The F4 key (30:45.5, frames 30:45-30:49): the lesson closes, "Select Entire Troop (Complete)", Glen's "Everyone,
    # let's move!" (30:46) with the notice "Move Troop / Use @MRB to move." (6000 / 6001, 30:47-30:59); Glen walks up
    # the path ahead of the hero (the blue marker on him 30:46-30:49; his force's cyan marks 30:44.5-31:10.5 end 600
    # from P1_S2_방향지시1, reads); the action camera's point is marked (its minimap ring 0.7 px from 10009's point at
    # 30:52.2, rings; the ground glow the hero walks into at 31:09, frames), and the blue marker on Glen as he leads
    # (ActGuiSetHighlightTroop 0xc7ba, 30:46-30:49, frames)
    {"on": "prompt", "keys": (KEY_SELECT_ALL_TROOP,), "needs": "select all", "id": "all troops", "do": [
        ("finish",), ("done", 410), ("march", 10000, "P1_S2_방향지시1"), ("notice", 6000, 6001),
        ("say", GLEN, 1210), ("highlight troop", GLEN, 1, 3), ("highlight", ACTION_CAMERA)]},
    # "Move along the path!" (30:59) as the hero crosses the strip P1_S2_영웅 체크1 (reads: 30:58.8 south of it, 30:59.8
    # in it), "Switch to Action Mode" (6002 / 6003, 31:01). Was: 2 s after the key. The harness's 10011 (30:57.5) is
    # the arrowhead read on the mark's green dot, 0.9 px from 10011's point (30:52-30:59)
    {"on": "bound", "bound": CHECK1, "needs": "all troops", "id": "path", "do": [
        ("say", GLEN, 1220), ("notice", 6002, 6003)]},
    # the corpse kobolds (force 20010): the hero at the mark (31:09.5, it goes), Thompson's "General! Kobolds!" (2110,
    # 31:10.0; not the draft 1230) with the client's F prompt "Look far" (0x50c1, key F: textui 9000; up 31:10.0-31:11.25,
    # gone 31:11.5); the F plays the action camera 2_Action_Camera (from 31:12.25; the minimap hidden 31:12.5-31:18.5,
    # its 6 s) over the looting kobolds, one saying "Where's shiny things?" (1240, 31:13-31:18: 1 s in, to the scene's
    # end), Glen's 1250 as it ends (31:18). Hand-read, build/order-a (the part 2 mp4 at 2-4 fps), as the prologue's
    # "Look far" (m50116). Walking on into the next strip, P1_S2_액션 카메라 무시 ("action camera: ignore"), without the F
    # takes the prompt down: no camera (the strip's name; the tape's player pressed F). Was: the camera on the bound
    {"on": "bound", "bound": ACTION_CAMERA, "needs": "path", "id": "action camera", "do": [
        ("highlight", ACTION_CAMERA, 0), ("say", THOMPSON, 2110)]},
    {"on": "prompt", "keys": (KEY_ACTION,), "needs": "action camera", "unless": "corpse fight", "id": "look far",
     "do": [("cutscene", 2, 1), ("say", 20000, 1240, 5), ("say", GLEN, 1250)]},
    # on P1_S2_액션 카메라 무시 (31:24.5) the fight starts (31:26), "Kiaakk! Humans! Kill them!" (1260, 31:28.5), the FP
    # notice (6010 / 6011, 31:32)
    {"on": "bound", "bound": "P1_S2_액션 카메라 무시", "needs": "action camera", "id": "corpse fight", "do": [
        ("say", 20001, 1260), ("notice", 6010, 6011)]},
    # the bridge: the corpse fight's last kobold falls at 31:58-31:59 (frames), "Don't let your guard down! There are
    # more Kobolds across the bridge!" (1270) is up at 32:00, the Hero Support notice (6004 / 6005) at 32:01: the corpse
    # kobolds F20010 and those before the bridge F20011 (다리 앞 코볼트) both down, whichever last, after the fight's
    # call (1260). Was: the bound P1_S2_다리 코볼트 전투, entered 32:08.5
    {"on": "down", "force": 20010, "needs": "corpse fight", "id": "corpses cleared"},
    {"on": "down", "force": 20011, "needs": "corpses cleared", "do": [("notice", 6004, 6005), ("say", GLEN, 1270)]},
    {"on": "bound", "bound": "P1_S2_다리 코볼트 전투", "do": [("say", 20108, 1280), ("say", GLEN, 1330)]},  # not on the tape
    # the bridge's far side: our wake of F20013 at 32:28.5 on the tape's path (the fight from 32:31), Thompson's "Kobold
    # commander. Watch out!" (1290, frames 32:32-32:38, missed by the text channel), the commander's 1300 and the
    # Vitality notice (32:39): as it was (the harness's 10016 / 10138 split followed its missing 1290)
    {"on": "wake", "force": 20013, "do": [("say", THOMPSON, 1290), ("say", 20155, 1300), ("notice", 6020, 6021)]},
    {"on": "wake", "force": 20091, "do": [("say", 20155, 1320)]},     # not on the tape (frames 32:42-33:28: no 1320)
    # the commander's force down, the archers in the rear left (F20014, MOUNTAINKOBOLDARCHER): "Defeat Enemy Commander"
    # at 32:57.0 (the target frame gone 32:57.25), Glen's "Kobold archers in the rear. Quickly! Take care of them!"
    # (1310) slides in at 32:58.0; the archers fought (the target frame "Lv. 6 Mountain Kobold Archer" until 33:24.0,
    # gone 33:24.5), then "We took care of them all. Now, let's move again!" (1340, 33:26.5) with the ground mark of
    # P1_S2_입구 진입 (glowing 33:28-33:31, walked into at 33:31; reads: the area entered at 33:30.5). Hand-read,
    # build/order-a (the part 2 mp4 at 1-4 fps). Was: 1310 at F20014's wake (33:01.5 on the tape's path), 1340 at
    # F20013's fall (32:57): 1340 before 1310 on the tape's own path
    {"on": "down", "force": 20013, "id": "commander down", "do": [("say", GLEN, 1310)]},
    {"on": "down", "force": 20014, "needs": "commander down", "id": "bridge cleared", "do": [
        ("highlight", "P1_S2_입구 진입"), ("say", GLEN, 1340)]},
    {"on": "bound", "bound": "P1_S2_입구 진입", "needs": "bridge cleared", "do": [("highlight", "P1_S2_입구 진입", 0)]},
    # the entrance hill: its Mountain Kobold Commander (20120, F20025) "Find shiny things!" (1350, frames 33:34) as the
    # hero enters 10150 (33:32.5), a looting kobold's (F20020) "Keeeek! H-Humans!" (1360, 33:39) at 10128 (33:38.5);
    # each speaker brought in with its line (our proximity wake has them then too). Was: F20091's wake, the bridge's
    # looters, 32:16.5 on the tape's path
    {"on": "bound", "bound": 10150, "do": [("wake", 20025), ("say", 20120, 1350)]},
    {"on": "bound", "bound": 10128, "id": "looters", "do": [("wake", 20020), ("say", 20167, 1360)]},
    # the kobold tank of the entrance hill (troop 20183 in force 20021): Thompson's "General! Kobold tank!" (4000, 33:44)
    # 5 s after the looters' 1360, the tank rolling into view 33:47-33:49, its fall's 4030 / 4040 (34:05 / 34:11), all
    # before the kobold leader's strip (34:34.5). Its lines wait for 10128's step (the gaps10 report's decision 3): a
    # tank in first, by its proximity or by our fallback wake once the field is empty, keeps the tape's order. Listed
    # before the leader's strip, in the tape's order (the headless walker visits the story in the table's order)
    {"on": "wake", "force": 20021, "needs": "looters", "do": [
        ("say", THOMPSON, 4000), ("say", 20183, 4010), ("say", GLEN, 4020)]},
    {"on": "down", "troop": 20183, "do": [("say", THOMPSON, 4030), ("say", GLEN, 4040)]},
    # 1390 at 34:33 (frames), the hero into 10015 at 34:34.5 (reads; its name "kobold leader appears"): as it was
    {"on": "bound", "bound": "P1_S2_코볼트 리더 등장", "id": "kobold leader", "do": [
        ("wake", 20024), ("say", THOMPSON, 1370), ("say", GLEN, 1380), ("say", 20170, 1390)]},
    # "The Grayrock Fortress is right in front of us! Forward!" (1400, frames 34:41) as the hero enters 10147 (34:41.5,
    # reads), with the ground mark of the gate ahead (34:41-34:46), walked into as he enters P1_S2_다음 서브 (34:46.5).
    # Was: 1400 with the cutscene at the gate
    {"on": "bound", "bound": 10147, "do": [("highlight", FORTRESS), ("say", GLEN, 1400)]},
    # into the fortress: 3_Mid_CutSCene (29 s, live: "If I might ask, General. Why do you think the Kobolds took over
    # this place?", the entrance lines 10040-10090 voiced) ends with the hero, Glen and Thompson inside at the P2
    # places; the troops follow to theirs (P2_S2_..._위치1), as the script did (live, without the moves: the troops
    # stayed at the entrance hill and the hero stood alone in the courtyard)
    {"on": "bound", "bound": FORTRESS, "id": "into the fortress", "do": [
        ("highlight", FORTRESS, 0), ("cutscene", 3, 29), ("move", "hero", "P2_S2_영웅 위치1"), ("move", GLEN, "P2_S2_글렌 위치1"),
        ("move", THOMPSON, "P2_S2_톰슨 위치1"), ("move", "영웅부대1", "P2_S2_영웅 부대1 위치1"),
        ("move deck", 1, "P2_S2_영웅 부대1 위치1"),
        ("move", "영웅부대2", "P2_S2_영웅 부대2 위치1"), ("move", "글렌 부대1", "P2_S2_글렌 부대1 위치1"),
        ("move", "글렌 부대2", "P2_S2_글렌 부대2 위치1"),
        # the courtyard: "We're entering the Fortress now. Watch out for hidden enemies!" (2100, 35:18) right after the
        # scene (34:48-35:16), with the next mark, 10079's (glowing 35:19-35:23). Was: the bound 10156, which the
        # hero never enters on the tape
        ("highlight", 10079), ("say", GLEN, 2100), ("done", 121), ("panel", 110, 122)]},
    # the hero reaches the mark on 10079 (35:23, entering it 35:24.5): the mark goes and the client's F prompt "Look far"
    # is up (35:24.0-35:25.25, gone 35:25.5; hand-read, build/order-a, the part 2 mp4 at 4 fps); the F plays
    # 6_Troll_Come (from 35:26.5; the minimap hidden 35:26.5-35:37.5, its 12 s) with Thompson's "General! Kobolds!"
    # (2110 a second time, frames 35:28-35:32) and the Mountain Kobold Sorcerer's "Filthy Humans, come here now! Crush
    # their skulls!" (2120, 35:34-35:38) over it: the sorcerer at the courtyard's far gate, 20174 (F20101), brought in
    # with the mark (the scene's ACTOR0: the client starts no scene before its cast is in). The left flank's attack
    # (F20051's wake) takes an unanswered prompt down: no camera in the fight (ours: no strip of the zone is named for
    # it). Was: the camera on the bound; before that, 2120 by the commander 20021 at F20050's wake
    {"on": "bound", "bound": 10079, "needs": "into the fortress", "id": "troll mark", "do": [
        ("highlight", 10079, 0), ("wake", 20101)]},
    {"on": "prompt", "keys": (KEY_ACTION,), "needs": "troll mark", "unless": "left flank", "id": "look far 2",
     "do": [("cutscene", 6, 3), ("say", THOMPSON, 2110, 5), ("say", 20174, 2120, 4)]},
    # "Kobolds are coming from the left flank!" (2130, 35:43): our wake of F20051 (앞마당 코볼트) at 35:38.5 on the
    # tape's path: as it was
    {"on": "wake", "force": 20051, "id": "left flank", "do": [("say", GLEN, 2130), ("say", 20022, 2140)]},
    # the archers on the battlements (F20052) open fire at 36:11 (frames: their shots across the courtyard), Thompson's
    # "General! The Kobold archers on the battlements have got us pinned!" (2150, 36:12), Glen's 2160 (36:16), the
    # Troop skill notice (6026 / 6027, 36:19), an archer's taunt 2170 (36:24). Kept on their wake (35:52.5 on the tape's
    # path, 19 s early): no report says an archer shoots (engage is the melee state), and the harness's "down troop
    # 20114" is a commander picked by nearness (it puts 2170 and 2210 both on 20021)
    {"on": "wake", "force": 20052, "do": [
        ("say", THOMPSON, 2150), ("say", GLEN, 2160), ("notice", 6026, 6027), ("say", 20116, 2170), ("say", GLEN, 2180)]},
    {"on": "down", "force": 20052, "do": [("say", GLEN, 2200)]},
    {"on": "down", "force": 20051, "do": [("say", THOMPSON, 2210), ("say", GLEN, 2220)]},
    # the caged wolves at the inner gate (force 20060): "There are Wolves in front of us!" (2300, 37:03) as the hero
    # enters 10063 (37:02.5), 2310 / 2320 after it. Was: their wake, 36:58.5 on the tape's path
    {"on": "bound", "bound": 10063, "do": [("say", THOMPSON, 2300), ("say", GLEN, 2310), ("say", GLEN, 2320)]},
    {"on": "down", "force": 20060, "do": [("say", THOMPSON, 4500)]},
    # the inner castle: the hero into 10230 (37:28.5), "There are Kobolds in front of us!" (2330, 37:29), the
    # sorcerer's scene (the minimap hidden 37:35.5-37:43.5: the camera on the wall, his "Ha, ha! You managed to come
    # this far." 2340 at 37:38.5; 5_Boss_CutScene by its name: 4_Kobold_Jump has the same script and 8.5 s, both leave
    # the hero at 10168, where the minimap has him at 37:44.5), Glen's 2350 (37:43), the pentacle notice (6008 / 6009,
    # sliding in under Glen's box at 37:44.5: after 2350, frames qeeQjhgO8ss_2259_2267_frames_2 f_00009-f_00013, hand-read
    # in build/order-a), Thompson's "Please pay attention to your Troop's HP as well. I'll restore it for now." (1010,
    # 37:45) with
    # the F1 troop's hp 5,423 -> 8,330 on the HUD then (at ~64 %: a line of the scene, not a threshold). Was: 2330 at
    # F20070's wake (37:44.5), 2340 at F20073's (37:47.5), 1010 at each fall of the troop below 30 %
    {"on": "bound", "bound": 10230, "do": [
        ("wake", 20073), ("say", THOMPSON, 2330), ("cutscene", 5, 3), ("say", 20078, 2340, 5), ("say", GLEN, 2350),
        # This map allows one owned troop (room uid1). Both F1 infantry and F2
        # borrowed archers recover in original f_01132 -> f_01134.
        ("notice", 6008, 6009), ("heal", 1), ("heal", 10073), ("say", THOMPSON, 1010)]},
    # the sorcerer's chain (38:12-38:34, the lines 4-5 s apart): "Release the Wolves!" (2360), Thompson's "the sorcerer
    # is running away!" (2370), "The Wolves have been let loose!" (2380), the tank behind first on the minimap (38:23.5),
    # "Drat! The wolves that we left behind will come for us, too!" (2470), "Wolves and tanks behind us!" (2490), the
    # archers' notice (6028 / 6029). What starts it the tape cannot tell: the hero's target is a Mountain Kobold
    # Commander 37:56-38:15 (frames), so if it is the sorcerer's hp, someone else hurt him; his fall fires these too.
    # 2370 is in the chain (frames 38:13-38:24 and the chat log: 2360, 2370, 2380); it was a later step at 25 %
    {"on": "hp", "troop": 20078, "below": 50, "do": [
        ("say", 20078, 2360), ("say", THOMPSON, 2370), ("wake", 20061), ("say", GLEN, 2380), ("wake", 20074),
        ("say", GLEN, 2470), ("say", GLEN, 2490), ("notice", 6028, 6029)]},
    # the obstacles: "General, the path is blocked." (2400, 39:27), the hero into 10190 at 39:29.5 (reads), "These
    # obstacles are destructible." (2410, 39:31) with the barricade glowing: as it was
    {"on": "bound", "bound": 10190, "do": [("say", THOMPSON, 2400), ("say", GLEN, 2410)]},
    # the crystal stones and the railroad: the barricade broken (39:33-39:35), the hero into 10065 (39:33.5), "Hey,
    # look! There are some shining ores scattered over there!" (2420, 39:37) with the ring round the stones' cart
    # (10070's point, 39:37-39:46); into 10227 (39:41.5), "Crystal Stones, I bet." (2430, 39:42), the Interact notice
    # (6016 / 6017, 39:44). Was: 2420 at 10227
    {"on": "bound", "bound": 10065, "id": "ores", "do": [("highlight", 10070), ("say", THOMPSON, 2420)]},
    {"on": "bound", "bound": 10227, "do": [
        ("say", GLEN, 2430), ("notice", 6016, 6017), ("panel", 400, 420), ("say", THOMPSON, 2440), ("say", GLEN, 2450),
        ("say", GLEN, 2460)]},
    {"on": "bound", "bound": 10070, "needs": "ores", "do": [("highlight", 10070, 0)]},
    # the troll's yard: the mine carts, the sorcerer 20081 and the Mountain Troll 20082 (force 20080)
    # 11_Kobold (16 s, 40:06-40:22) voices "Watch out!", the mine cart, "General! Mountain Troll!" (10330-10470), as the
    # hero enters 10195 (40:05.5). Was: 10060, 2,074 from him then (the scene's own script moves him into it 580 ms in).
    # F20080 comes in first: the scene's ACTOR tracks Ko_Ma and TROLL bind 20081 and 20082, and the client does not
    # start a scene until every such troop is there (TrackActorBase::IsCompleteLoad 0x140941f70 via 0x1408b3360); live
    # 2026-09-30 15:25 it waited at black, the force still held for the hero's approach after the scene
    {"on": "bound", "bound": 10195, "id": "troll yard", "do": [
        ("wake", 20080), ("cutscene", 11, 16), ("done", 122), ("panel", 110, 123)]},
    # "Kill all the Humans!" (3100, 40:26) and the troll's 3110: 4 s after the scene (the tape's 40:22 end; the
    # harness's "after step 11_Kobold, s 4"). Was: F20080's wake, which now comes before the scene
    {"on": "after", "step": "troll yard", "s": 4, "do": [("say", 20081, 3100), ("say", 20082, 3110)]},
    # "The Troll's groggy!" (3120, 42:23): its groggy, our hp 10 % (live-proven 2026-09-29, the finisher lesson); the
    # harness's 10120, entered 26 s before, is no trigger of it
    {"on": "hp", "troop": 20082, "below": 10, "id": "groggy lesson", "do": [("say", GLEN, 3120), ("tutorial", "134_GroggyFinish"),
                                                            ("panel", 400, 430)]},
    # Native F completion sets the tutorial's done flag but leaves the last banner visible.
    # Identify this lesson's last page before reading done, so the preceding F4 lesson cannot
    # satisfy it while dialogue delays the new tutorial. Dismissal never completes objective430.
    # "Finishing Attack: Press E" (6018 / 6019) comes as the pages are done (frames 42:29.5 page 1, 42:30.5-42:31.5
    # page 2, 42:32.5 the pop-up gone and the notice in); it came with 3120, before the pop-up
    {"on": "cond", "cond": (TUTORIAL_PAST, "134_GroggyFinish", 0), "needs": "groggy lesson", "id": "finisher last page"},
    {"on": "cond", "cond": (COND_TUTORIAL_COMPLETE,), "needs": "finisher last page", "do": [
        ("finish",), ("notice", 6018, 6019)]},
    # "Use Finishing Attack (Complete)" with the finishing attack (42:38), before "Eliminate the enemy" (42:40)
    {"on": "finish", "troop": 20082, "do": [("done", 430)]},
    {"on": "down", "troop": 20081, "do": [("say", 20081, 3160)]},
    # "you won't die in this mission": Glen restores the hero (1000)
    {"on": "hp", "troop": "hero", "below": 15, "repeat": True, "do": [("say", GLEN, 1000), ("heal",)]},
    # the ending: Grayrock reclaimed, the Crystal Stones for Golden Hammer's Lunawing (19500-19550). 13 is
    # 13_EndScene, slot 13 of the map's list 1_GrayrockFortress.csset (13_StartCut is not in that list): Golden
    # Hammer's carts, voices 19500-19550. Its cast F19500 (Glenn_1 19500, Thom_1 19501, Golden_1 19502, Human_MG
    # 19503) comes in with it, after the lines. The scene's ACTOR tracks bind them, and the client starts no scene
    # until every such troop is there (0x1408b3360, as with 11_Kobold). The scene enables the force itself at 0 s
    {"on": "won", "do": [
        # A companion can kill the troll before its F pages are completed. The
        # won room stops polling those pages; dismiss the obsolete overlay before
        # the ending, without completing the execution objective430.
        ("finish",),
        ("done", 123), ("say", THOMPSON, 3130), ("say", GLEN, 3140), ("say", GLEN, 3150),
        # The scene ends black. Restore the picture before the results; otherwise
        # ShowLoadingWait masks the result and card UI until its240-second timeout.
        # Last shipped script command46.730s; native input returned46.94s after
        # receipt. Include the load/teardown interval before restoring the picture.
        ("wake", 19500), ("cutscene", 13, 48), ("fade", True, 1, 0)]},
]

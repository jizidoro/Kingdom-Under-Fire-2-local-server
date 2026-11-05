"""Tower of Moonlight 10233 (1_TowerOfMoonlight zone1), the director's table.
The original's script, from the playlist, with its storyboard and our marks: planning/scripts/missions/10233.md
(`py tools/mission_scripts.py 10233`).

Sources: the map's missiontext (lines 1000-1580, 10100-10890; `py tools/recon/mission_sheet.py 10233`), the zone's
bounds, forces and props, the walkthrough (walkthrough_guide.txt L89-115, planning/walkthrough/p2-grey-fog.md steps
10-16: the strategy-mode tutorial, Glen and Thompson along, the hero cannot die, Golden Hammer and Jade's organ cannons
at the end, Jade opens the tower). Speakers come from the original where a video shows them
(planning/scripts/10233_grey1080_1250.md: the uphill talk 1380-1470 alternates Glen and Thompson), else from the
lines' own words: Thompson calls Glen "General" (1170, 1390)
and the hero "Captain" (1030, 1290; the militia made the hero Captain in Grey Fog 10358, 3204); Glen calls the hero
"Commander" (1280, 1480, 10350), gives the tutorials (1000-1020, 1330-1350) and the orders (10130, 10340, 10860); Jade
is Moon Light's student (10330, 10870); Golden Hammer laughs "Mwa hah hah" (10700, 10830). The soldiers' questions to
the Captain go to troop 11001 (infantry of the main forces, F11000); who answers them is ours. There are no enemy lines.

Who goes where, from the original's own scripts and frames (playthrough part 2 4:28-8:20; the cutscenes' SCRIPT
tracks, planning/scripts/cutscenes.json): 0_StartScene marches the main forces (F11000) past the hero along path 10003
and halts them, Glen (10000) stands at 글렌위치1 and sends "#USERNAME#, take Thompson and your troops to scout the
area" (10130). Everyone stands through the lessons (5:02-6:22). "The time has come, scouts! Follow the Captain!" (1030)
is the player's own troop, Bersia Light Infantryman (10100, F1; the frame at 6:22), the only troop the player has
until the winged wyrms (the archers, 11006, first show as F2 at 12:10). Thompson goes with the hero; 2_SupportRequest
puts the hero, Thompson and 10100 at the scouting area with Thompson's 1070-1100 (7:52-8:14), then 12_Ruins_Tab is
the Action-mode lesson (13305, waiting on Tab; 8:16-8:20). Glen and the main forces come at "Everyone, support the
scouts!" (1140) and march with the story after 4_JoinTheMainForces ("Scouts, reunite with the main forces", 10230).
The lessons of 1_TroopTutorial stay our pop-ups (it waits on the server eight times, System_WaitState -1..-8); each
closes on the key its script waited for, which the client reports when asked (director "cond" / "prompt").

Which trigger starts each scene is ours, read from the places and checked on the tape (the video harness's report,
captures/harness/10233_report.md, its rows checked against the frames 2026-09-30): the scouts cross two parallel
strips on the way north-west, bounds 18020 and 18021 (the ruins), each marked ahead, then the third mark, 18022 (a
small square in 18023's strip, the scouting area where F20000 stands and the F20100 ring closes round it), where
2_SupportRequest starts; their captain is F20010 (troop 20014, led by 133040); the "Support Timer"
(panel 160 / 170) until Glen comes is 30 s of "after" steps, and Glen comes to his own bound 글렌 진입 ("Glen
enters"); the scouting ends when F20100, the largest group (20 troops), is down; the winged wyrms are F30000 in the
fenced bound 가두기_윙드웜 ("trap the winged wyrm"); 문라이트_에리어이동 ("Moonlight area move") is where the tower comes
in sight, bound 10012 the tower door (prop 10001, type 427 "the sealed door of the Moonlight tower"); the night attack
on the camp is F40000 with the scorpions F40005 and the head cannons F40100; Golden Hammer comes 5 s after the camp's
talk (1500-1580, after the Offensive lesson's Z) with 11_Canon_Bomb, and the room is won then (success condition 130
"Survive until reinforcements arrive"). Who the cutscenes act on, from their SCRIPT tracks: 8_TowerFound enables the
camp's F13000, 9_Camp walks F35000 to 10501 (the Encablossians coming, 10630) and swaps the camp's resting soldiers
for F14370, 10_Defense_Camp
disables F35000 again and enables F14370 / F14500 / F16000, 11_Canon_Bomb has the organ cannons F16100 fire on the
invisible F46100 and disables the scorpions 40001 / 40002, 3_SealedTower ends with F19300 (Glen, Thompson, Jade, Golden
Hammer) at the door (tile #112, 19:08). Every "s" is ours. Left
out: the panel (110-270), the tutorial pop-up texts (7000-7250) and the
guide notices the original does not show (8000-8210 but 8000, 8020, 8060, 8080, 8110, 8150, 8180, 8200), the
alternates 1241 and 10600-10630, the heal variants 1610-1630, and 1050 "Oh, I see a tower over there!" (no part of
the playlist shows it: the text read, and the frames 6:32-7:42 of part 2 between the first mark and 1060). F30000 is
held by no wave (staging hp, EXP_FACTOR 0): ("wake", 30000) brings it as a staging force (game.spawn_force)."""
from ..director import (COND_TUTORIAL_COMPLETE, COND_TUTORIAL_PAST as TUTORIAL_PAST, KEY_AI_HERO_SUPPORT,
                        KEY_AI_OFFENSIVE, KEY_CAMERA_MOVE, KEY_CAMERA_ROTATED, KEY_CHANGE_CONTROL_MODE, KEY_SELECT_HERO,
                        KEY_SELECT_TROOP3, KEY_ZOOM)

GLEN, THOMPSON = "글렌_1", "톰슨_1"
# Forces the steps bring in (ours; the proximity wake brought Golden Hammer's F35000 as soon as the scouts fell, 40k
# units early, and the camp's attackers F40000 / F40005 / F40100 as the hero marched past them, so the tower and camp
# scenes never came), and the tower door only Jade's ending unseals. F13100 / F19300 are extra 0-unit copies the plan
# stood at the start (Glen and Thompson three times, the authoring run): F13100 is left out, F19300 comes after
# 3_SealedTower (which enables it at 103.5 s: Jade and Golden Hammer at the door). F20100 is 1120's "Geez, there are
# more Encablossians!", after the captain falls (it stands 1k from bound 18023, so the proximity wake brought it
# before the scouting lines; tools/playthrough.py check). F35000 is 9_Camp's column, which 10_Defense_Camp disables: no
# step brings it (woken with the cannons, its two scorpions stood 10 k west of the camp and the win waited on them).
HOLD = {20100, 35000, 40000, 40005, 40100, 13100, 19300}
WIN = "table"                    # won when Golden Hammer's cannons come (130 "Survive until reinforcements arrive"),
                                 # not by the last hostile: 11_Canon_Bomb disables the scorpions in the client
COLUMN = (11000, 11001, 11002, 11003)    # the main forces' infantry; their own bounds 11000-11003 line the wyrms'
                                          # clearing's road, where 5_WingedWorm_Appeared animates them (4.0 s, 13.0 s)
BOWS = (11004, 11005, 11006)     # the main forces' archers (Glen's two, then the player's), on their own bounds
                                 # 11004-11006 short of the clearing for 1320 "Archers, shoot down the Winged Wyrm!"
                                 # (the tape part 2, 10:59-12:53: 800 from 11006)
CAMP = (14100, 14200, 14300, 14310, 14320, 14330, 14340, 14360, 14370, 14400, 14500, 16000)   # the camp's soldiers,
                                 # its archers and its Glen / Thompson (9_Camp, 10_Defense_Camp)
HILLTOP = 10100                  # the hilltop past the uphill path, where 8_TowerFound stages the party (the hero at
                                 # (58719, 117271) at 3.7 s) and the tower comes in sight: the scene's trigger. Not
                                 # 문라이트_에리어이동 (10500): behind the camp's red curtains, where 10_Defense_Camp puts
                                 # the hero later (two live runs 2026-09-29 stood at the hilltop, the scene unplayed)
ENTRY_GRID = ((0, 0), (700, 0), (-700, 0), (0, 700), (700, 700), (-700, 700), (0, 1400), (700, 1400))  # ours
UPHILL_WALL = 10015                 # the invisible wall (type 232) on the path up to it, at (39383, 109463)
ATTACKED = "컷신이동"             # 10501, where 9_Camp walks the attacking column (Troop_MoveToArea(35001..35006,
                                 # 10501, 0) at 22.0 s); 10_Defense_Camp sends the hero to 10500 beside it (16.5 s)
# The panel as the original shows it (frames of playthrough part 2): under its title "Tower of Moonlight" (100, the red
# bar: 5:14, 8:40, 16:04, 19:46), "Find the Tower of Moonlight" alone at first (5:14), "Defeat Winged Wyrms" with its
# 0/3 count at the wyrms (12:10), 120 complete and "Survive until reinforcements arrive" once the night attack is on
# (16:08, after 1490)
PANEL = (100, ((110, (120,)), (140, (150,))))
ESCORT = {THOMPSON}              # the scouting party; Glen and the main forces join after the report ("escort")
HOLD_PROPS = {10001}
SCOUT, ARCHERS = 10100, 11006    # the player's troops: the light infantry from the start, the archers at the wyrms
HAND_LATER = {ARCHERS}
GOLDEN_HAMMER, JADE = 16114, 16115   # with the organ cannons (force 16110, 133190 / 133200)

STEPS = [
    # the column halts: 0_StartScene (35 s; voices 10100-10140: Glen sends the hero and Thompson to scout), then
    # strategy mode (1000-1040). Cutscenes: planning/scripts/cutscenes.md (tools/recon/cutscenes.py)
    {"on": "start", "id": "halt", "do": [("cutscene", 0, 35)]},
    # Thompson's lessons, each with its tutorial pop-up: 1_TroopTutorial's own rows (13301, then the NoInfo ones
    # 13310-13313: the original shows 7040, 7080, 7120, 7140 and none of the info pages 7030 / 7050 / 7070 / 7130;
    # playthrough part 2 5:06-6:32). Each closes when the player does what it asks, the key the original's lesson
    # script (1_TroopTutorial, planning/scripts/cutscenes.json) waited for there, and the next follows it: a pop-up's
    # F pages are the client's own; the step asks the client for its last page ("cond", 0xcb2b), then prompts its key
    # ("prompt", 0x50c1 / 0x50c2). A one-page pop-up is completed (0xc898, the circle and sound), a longer one closed
    # (0xc897): 0xc898 completes page 0 only (planning/client/GAPS.md mission_script 5). The pause after each key is
    # the tape's too (frames: the card's completion circle, then the next: ` 5:42.4 -> 1010 5:44.5, right button
    # 5:55.8 -> the zoom card 6:00.0, wheel 6:00.8 -> the move card 6:04.0, W / A / S / D 6:06.8 -> 1020 6:11.5, C
    # 6:21.3 -> 1030 6:22.9; ours 2 s): the harness's report puts what follows into the key's own step (rows 'lesson2',
    # 'lesson3', 'lesson4', 'lesson6', 'scouts'), dating the key by what comes after it. The panel's lesson line comes
    # a moment before its pop-up (frames: 210 at 5:07.75, the pop-up 7000 at 5:07.88; 230 at 6:15.50, 7120 at 6:15.62;
    # planning/agents/reports/2026-10-24_order-b.md)
    {"on": "after", "step": "halt", "s": 2, "id": "lesson1", "do": [
        ("say", THOMPSON, 1000), ("panel", 200, 210), ("tutorial", "133_SelectHero")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "133_SelectHero", 1), "needs": "lesson1", "id": "select hero"},
    {"on": "prompt", "keys": (KEY_SELECT_HERO,), "needs": "select hero", "id": "hero", "do": [   # "Select your Hero":
        ("finish",), ("done", 210)]},                                                             # `
    {"on": "after", "step": "hero", "s": 2, "id": "lesson2", "do": [
        ("say", THOMPSON, 1010), ("tutorial", "133_TroopCameraRotation_NoInfo"), ("panel", 200, 220)]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "133_TroopCameraRotation_NoInfo", -1), "needs": "lesson2", "id": "rotate"},
    {"on": "prompt", "keys": (KEY_CAMERA_ROTATED,), "needs": "rotate", "id": "rotated", "do": [("complete",)]},
    {"on": "after", "step": "rotated", "s": 2, "id": "lesson3", "do": [("tutorial", "133_TroopCameraZoom_NoInfo")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "133_TroopCameraZoom_NoInfo", -1), "needs": "lesson3", "id": "zoom"},
    {"on": "prompt", "keys": KEY_ZOOM, "needs": "zoom", "id": "zoomed", "do": [("complete",)]},
    {"on": "after", "step": "zoomed", "s": 2, "id": "lesson4", "do": [("tutorial", "133_TroopCameraMove_NoInfo")]},
    # "Move the camera": the original's script had no key here (it waited on its server, System_WaitState(-5)); the
    # camera's own keys W / S / A / D are what the player does (a camera moved another way sends no key event); the tape
    # shows its card completing (the circle) as the view moves, 6:06.8 (frames 6:01-6:14; harness REVIEW: no key)
    {"on": "cond", "cond": (TUTORIAL_PAST, "133_TroopCameraMove_NoInfo", -1), "needs": "lesson4", "id": "move"},
    {"on": "prompt", "keys": KEY_CAMERA_MOVE, "needs": "move", "id": "moved", "do": [("complete",), ("done", 220)]},
    {"on": "after", "step": "moved", "s": 2, "id": "lesson6", "do": [
        ("say", THOMPSON, 1020), ("panel", 200, 230), ("tutorial", "133_Command_C_NoInfo")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "133_Command_C_NoInfo", 1), "needs": "lesson6", "id": "command c"},
    {"on": "prompt", "keys": (KEY_AI_HERO_SUPPORT,), "needs": "command c", "id": "hero support", "do": [
        ("finish",), ("done", 230)]},
    # the lessons done (the panel's three "(Complete)", 6:22), the player's troop calls the scouts (1030)
    # 1040 "Let me mark your path on the Map" marks the first place, and each place reached the next (the tape, part
    # 2 6:34-7:42: a highlighted area ahead that moves on; live 2026-09-29 23:47 none was marked)
    {"on": "after", "step": "hero support", "s": 2, "id": "scouts", "do": [
        ("say", SCOUT, 1030), ("say", THOMPSON, 1040), ("highlight", 18020), ("notice", 8020, 8030)]},
    # the forest: two strips, then the scouting area, where 2_SupportRequest (19 s) takes the party in: Thompson's
    # 1070 / 1080 / 1090 / 1180 / 1100, F20000 set on them (Troop_SetTroopAi 40000). Each place waits for the one
    # before (a hero who walks during the start scene or the lessons crossed 18020 before them: the replay of
    # 2026-09-28 23:52 told the line and marched the escort 10 s into 0_StartScene). The camera notice comes as the
    # first mark is reached (frames 6:32-6:48: the glow reached 6:37, the pillar gone 6:38, 8000 / 8010 at 6:38-6:39;
    # ours was a 12 s timer after the scouts' lines: harness report row '#17'); no line there (1050, "Oh, I see a
    # tower over there!", is on no part of the playlist: frames 6:46-7:42 show no help box until 1060)
    {"on": "bound", "bound": 18020, "id": "tower seen", "needs": "scouts", "do": [
        ("highlight", 18020, 0), ("highlight", 18021), ("notice", 8000, 8010)]},
    # the ruins (1060 at 7:40), and the third mark ahead (7:42-7:46; the minimap ring 7:41.75 1.1 px from 18022's
    # point, 18023's 3.9 px: harness report "Highlights"): 18022, where the scene starts as the hero reaches it
    # (7:51.5; ours played it with 1060 and marked 18023)
    {"on": "bound", "bound": 18021, "id": "ruins", "needs": "tower seen", "do": [
        ("highlight", 18021, 0), ("highlight", 18022), ("say", THOMPSON, 1060)]},
    {"on": "bound", "bound": 18022, "id": "scouting area", "needs": "ruins", "do": [
        ("highlight", 18022, 0), ("cutscene", 2, 20)]},
    # the Action-mode lesson (12_Ruins_Tab: 13305 133_SelectActionMode, then the player's Tab; the original 8:14.5-
    # 8:20) when 2_SupportRequest is done with its last line (1100 at 19.8 s for 4 s: the tape 8:11.75-8:14.25, the
    # card 8:15.25; ours waited for the hero in 18023: harness report row 'action mode')
    {"on": "after", "step": "scouting area", "s": 3, "id": "action mode", "do": [
        ("cutscene", 12, 2), ("panel", 200, 240)]},
    # the cutscene completes its lesson on the player's Tab (CompleteTutorial 2) but nothing hides the card: live
    # 2026-09-29 it stayed up 4 min 25 s asking for Tab (22:58:09 -> 23:02:34); the original's went within 2 s of the
    # Tab (tape part 2, 8:18 -> 8:20): the server closes it on that Tab, its trigger
    {"on": "prompt", "keys": (KEY_CHANGE_CONTROL_MODE,), "needs": "action mode", "do": [("finish",)]},
    {"on": "wake", "force": 20010, "do": [("say", THOMPSON, 1110), ("notice", 8060, 8070)]},   # no lesson (8:32-8:50)
    # more of them: hold until Glen comes with the main forces
    {"on": "down", "troop": 20014, "id": "hold", "do": [
        ("wake", 20100), ("march", 20100, 18023),                # the ring closes round the scouts (1180 "they're
                                                                 # coming from behind"; tiles #46-#58): to the strip's
                                                                 # centre, where 2_SupportRequest put them (to its
                                                                 # nearest point, 20112 stopped at the strip's far end,
                                                                 # 9 k off: live 2026-09-29 03:59)
        # "our main forces aren't far": Glen's force comes in at its entry, 글렌 진입 (7.9 k from the scouts), and
        # into the fight. The tape (part 2) has it join ~24 s after the notice (8:56 -> 9:20), walking from its spawn
        # by the start camp ((77980, 63678) -> (61590, 74789) 8:53.5-9:18.5, ~790 units/s: harness report "Marches");
        # live 2026-09-29 it marched from the start camp (34 k) and came in sight 2 min 13 s later (~255 units/s),
        # after the ring had fallen: the entry placement (the grid is ours) stays until a live run shows the marches
        # at the tape's pace (director.MOVE_MODE)
        *(("move", u, "글렌 진입", off) for u, off in zip((GLEN, *COLUMN, *BOWS), ENTRY_GRID)),
        ("march", GLEN, 18023), ("march", 11000, 18023),
        ("say", THOMPSON, 1120), ("say", THOMPSON, 1130), ("notice", 8080, 8090)]},
    # Glen's lines when his force reaches the ring, their trigger (a 30 s timer played them while he was 34 k away,
    # live 2026-09-29 22:59:34; the tape: 1140 at 9:16 as his force comes in, 1150 at 9:28), and his marker a moment
    # (the blue pillar over his arriving force 9:21.5-9:23.5, frames 9:20.5-9:24; harness report "Effects")
    {"on": "engage", "force": 20100, "by": (GLEN, *COLUMN, *BOWS), "needs": "hold", "do": [
        ("say", GLEN, 1140), ("highlight troop", GLEN, 1, 2), ("say", THOMPSON, 1150)]},
    # the scouting done: regroup, the situation report, then Moon Light and Jade on the way (1210-1250)
    # Glen leads both legs and the hero follows (the video harness, part 2: after 1160 / 1170 the allied mark walks
    # toward 18031 '상황보고' (10:00-10:13) and 4_JoinTheMainForces starts as the hero enters it (10:13.5); then
    # "Join the Main Forces: Follow Glen." at 10:38 and the column walks to the wyrms' clearing, 11:04). Ours played
    # the scene on a 3 s timer and made Glen's force escort the hero (owner: "the part where we have to follow glen")
    {"on": "down", "force": 20100, "id": "regroup", "do": [
        ("say", GLEN, 1160), ("say", THOMPSON, 1170), ("march", GLEN, 18031), ("march", 11000, 18031)]},
    {"on": "bound", "bound": 18031, "needs": "regroup", "id": "report", "do": [   # 4_JoinTheMainForces (10200-10230)
        ("cutscene", 4, 21)]},                                                    # "Scouts, reunite with the main forces"
    # "Follow Glen.": Glen alone ahead under his marker (frames 10:36-10:46: one figure under the blue pillar; harness
    # report "Effects" 10:38.75-11:07.75), his column from behind the hero to its own places (10:48-11:04 it comes up
    # past him; the tape's group stood 800 from 11006 through the wyrms, 10:59-12:53): the infantry to its bounds on
    # the clearing's road, the archers to theirs short of it. Ours marched the whole force ahead with Glen (b08931c).
    # On the tape the column set off ~9 k behind the hero (it stood short of 18031 after the regroup); ours comes
    # from 18031 with him (the ENTRY_GRID placement, kept until a live run proves the marches' pace)
    {"on": "after", "step": "report", "s": 0, "id": "follow glen", "do": [
        ("notice", 8180, 8190), ("highlight troop", GLEN), ("march", GLEN, "가두기_윙드웜"),
        *(("march", str(u), u) for u in (*COLUMN, *BOWS)),
        ("say", THOMPSON, 1210), ("say", GLEN, 1220), ("say", GLEN, 1230), ("say", THOMPSON, 1240), ("say", GLEN, 1250)]},
    # the winged wyrms (F30000): 5_WingedWorm_Appeared runs the scene itself (planning/scripts/cutscenes.json): its
    # lines 1260-1320 and the Defensive lesson 13307 (133_Command_X: 7160 and 7170 on F, 7180 on X), which waits on the
    # player's X (the table's own lesson closed it and the cutscene hung at black, live 2026-09-28 21:21). The lesson
    # holds the scene: it starts at 11.766 s (System_StartTutorial(-1, 13307), System_CutSceneInputFree), the scene
    # waits on X there and completes it (System_CompleteTutorial(2) at 12.076 s), then plays to its end at 25.009 s
    # [data]. The client reports neither the X nor the scene's end, so the scene holds the queue to its lesson (12 s)
    # and the table asks for the lesson's last page, then for its completion (0xc760, as Grey Rock's finisher), and the
    # scene's last 13 s follow. Ours queued it 25 s and sent what follows at the 25 s: live 2026-10-24 the wake, the
    # march and the column's places went at 11:59:02 while the scene stood on its lesson until the X at 12:06:15 and
    # ended at 12:06:29 [live: journal, telemetry "cut" / "lesson"]; Glen's archers felled 30000 / 30001 meanwhile
    # (11:59:10, 11:59:44)
    {"on": "bound", "bound": "가두기_윙드웜", "needs": "report", "id": "wyrm scene", "do": [
        ("highlight troop", GLEN, 0), ("cutscene", 5, 12)]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "133_Command_X", 1), "needs": "wyrm scene", "id": "defensive page"},
    {"on": "cond", "cond": (COND_TUTORIAL_COMPLETE,), "needs": "defensive page", "id": "defensive"},
    # After the scene, the column on the clearing's road (tile #73, 11:44) and the archers on their own bounds short of
    # it (the tape's group 800 from 11006 through the fight, 10:59-12:53; with F2 the camera shows the archers in a
    # grass field with the column, the wyrms overhead, frames 11:58-12:47; ours put them at the clearing's centre,
    # 13.8 k off: the brief's finding 4), placed there (they lagged 10-17 k back at the hand, live 2026-09-29); Glen's
    # marker comes down as the hero arrives (11:07.75, the scene 11:10). The wyrms come in at the scene's end, at
    # their places (the tape's minimap: red marks at 30001's and 30000's places at 11:45, then passes over the ground
    # between the clearing and the archers' bounds, 11:48-12:42 [tool: part_qeeQjhgO8ss.channels.json]): the two
    # beyond their 6000 acquisition of the party are marched to the clearing (unmarched, 30000 never left its place,
    # 10.7 k off: "Only one left!" and nothing more, the owner's run 2026-09-29 05:19); 30002, 1.4 k from the hero's
    # place 10002, is not: marched, it reached the clearing's centre 3 s after its wake and hovered over it (within
    # 0.1 k for 7 minutes, then drifting at ~10 units/s), attacking nobody with Thompson 0.4 k, Glen 0.7 k and the
    # column 1.8-4.2 k off, out of the archers' reach (live 2026-10-24 11:59:05-12:11) [live]; unmarched it fought
    # from its place (2026-09-29: it wiped 11001 at 05:15:02 and fell to 11006 at 05:19:19) [live]
    # Glen's 1330, the hand of the archers and their lesson come at the scene's end: the tape's 1330 is at 11:44, 2 s
    # after the scene's 1320, the lesson 7220 at 11:49 (the original's catalogue, frames 11:35-12:03) [tool, frames].
    # Ours waited for the first engage with a wyrm, and the client sent none in the live fight of 2026-10-24
    # (11:58-12:12: no 0x5058 while the archers' volleys felled two wyrms and the wyrms hit 11005 and Thompson: a
    # ranged, flying fight) [live]
    {"on": "after", "step": "defensive", "s": 13, "id": "wyrms", "do": [
        *(("move", u, u) for u in (*COLUMN, *BOWS)), ("wake", 30000),
        ("march", "30000", "가두기_윙드웜"), ("march", "30001", "가두기_윙드웜"),
        ("hand", ARCHERS), ("say", GLEN, 1330), ("tutorial", "133_SelectTroopSlot2"), ("panel", 200, 260)]},
    # Glen's other archers shoot the wyrms once the fight is on (1340 "The other archer's job will to help the
    # Commander's troop to attack!"; the original 12:03-12:46: the wyrms fall to their volleys while the handed troop
    # waits for command); live 2026-09-29 they stopped 30 k off after shooting F20100 from afar (04:00:58, 05:05:18),
    # and fired at a wyrm only when 30001 flew to them (05:13:27-05:13:51; it fell at 05:13:45). Live 2026-10-24, on
    # their bounds, their own program shot each wyrm that came within their 7200 (27 volleys, 11:59:04-11:59:44) and no
    # engage came to order them
    {"on": "engage", "force": 30000, "do": [("shoot", 11004, "nearest"), ("shoot", 11005, "nearest")]},
    {"on": "wake", "force": 30000, "do": [("panel", 200, 250)]},
    # "[F2] Select the Archer Troop.": its three pages the client's (F), then F2 (KEY_SelectTroop3, the second troop
    # slot), the key the original's 7_Tutorial_Range waited for; the pop-up is closed then (live 2026-09-29 14:12 it
    # stayed up with the archers selected). Glen's 1340 and what follows come on that F2 (frames 11:54-12:00: the card
    # 11:56-11:57, F2 at 11:58, 1340 at 11:59; the notice 12:03, the count 12:06, 1350 12:11, "Troop Skill: Press 1"
    # 12:16-12:28): ours said them with 1330, over the card (harness report row 'wyrms', partly)
    {"on": "cond", "cond": (TUTORIAL_PAST, "133_SelectTroopSlot2", 2), "needs": "wyrms", "id": "select archers"},
    {"on": "prompt", "keys": (KEY_SELECT_TROOP3,), "needs": "select archers", "do": [
        ("finish",), ("say", GLEN, 1340), ("notice", 8100, 8110), ("count", 180, 190, 30000), ("say", GLEN, 1350),
        ("notice", 8120, 8130)]},
    # the wyrms fall to the archers' volleys under the real damage (the synastry matrix: row 278 takes RANGE x3,
    # combat.synastry), mostly Glen's 11004 / 11005 as the original; the skill rule that felled a wyrm on the
    # archers' skill is dropped (owner 2026-09-29 15:40). "Only one left!" is Thompson's as the count turns 2/3 (frames
    # 12:28-12:30: 1/3 at 12:29.0, 2/3 at 12:29.25 as the box comes in, his name and face at 12:29.5; ours had Glen;
    # the harness found no rule: row '#34')
    {"on": "left", "force": 30000, "count": 1, "do": [("say", THOMPSON, 1360)]},
    # the invisible wall 10015 (232) on the uphill path comes down first: the column's orders sent while it stood found
    # no way and the column stood (live 2026-09-29 23:03:32; it opened only as the hero came near, after the orders).
    # After "Let's go!" (1400, the tape 13:01-13:04) Glen's marker (13:07.75) and the column up the hill with the hero
    # (tiles #89-#90, 13:16-13:30; frames 13:06-13:40: the column round him, the blue pillar ahead); the tape marks no
    # area up the hill (no MINE ring or pillar 12:45-13:41: ours marked the hilltop 10100)
    {"on": "down", "force": 30000, "id": "uphill", "do": [
        ("open", UPHILL_WALL), ("say", THOMPSON, 1370), ("say", GLEN, 1380), ("say", THOMPSON, 1390),
        ("say", GLEN, 1400), ("highlight troop", GLEN), ("march", GLEN, HILLTOP), ("march", THOMPSON, HILLTOP),
        ("march", 11000, HILLTOP)]},
    # the talk on the way up: 1420 at 13:10.0 as the hero follows Glen (he set off 13:08.5, 1400 ended 13:04.25); no
    # area entered then, the trigger the tape does not show (harness report row '#36'): a pause after the lines, 3 s
    # (ours was 10)
    {"on": "after", "step": "uphill", "s": 3, "do": [
        ("say", THOMPSON, 1420), ("say", GLEN, 1430), ("say", THOMPSON, 1440), ("say", GLEN, 1450),
        ("say", THOMPSON, 1460), ("say", GLEN, 1470)]},
    # the tower: 8_TowerFound (92 s; voices 10250-10350: in sight, the Lunawing, the ward, the messenger to Jade and
    # Golden Hammer), then 9_Camp (31 s; 10600-10630, "Encablossians are coming!") and 10_Defense_Camp (17 s), and
    # the night attack (the original, planning/scripts/10233_grey1080_1250.md: 13:46-15:41, then Glen's 1480)
    # the camp comes before 8_TowerFound, which enables and walks F13000 there (16.0 s), then disables Glen, Thompson
    # and 11000-11005 (24.2 s): a wake after it would enable those again (ActTroopSetEnableAllTroops); ours: the camp's
    # soldiers were joined to the scorpions' wave and came after the attack had begun
    {"on": "bound", "bound": HILLTOP, "id": "tower", "needs": "uphill", "do": [
        ("highlight troop", GLEN, 0), ("wake", 13000, *CAMP), ("cutscene", 8, 92)]},    # the marker off 13:39.25
    # 10_Defense_Camp holds the queue for its camera part (8.2 s): then it releases input to its own Offensive
    # lesson (13308, waiting on the player's Z) with the HUD up. Glen's 1480 comes as it opens (the text read
    # 15:44.75-15:49.25, the scene from 15:43.83; frames 15:42-16:14: his face over the camp at 15:45-15:48; ours said
    # it at the lesson, 8 s on: harness report row '#41'), in that camera part: the scene holds the queue 1 s, then the
    # line (6 s by its length) and 1 s more, and the night attack wakes 8 s in as before (after the scene's second
    # Troop_DisableForce(35000), 7.3 s; the live run of 2026-09-30 woke it there)
    # ("state", -10): 10_Defense_Camp locks input and waits at 8.0 s on System_WaitState(-10) before its lesson
    {"on": "after", "step": "tower", "s": 0, "id": "camp", "do": [
        ("state", -10), ("cutscene", 9, 31), ("cutscene", 10, 1), ("say", GLEN, 1480), ("panel", 200, 270)]},
    # the night attack on the camp: F40000 with its scorpions F40005 and head cannons F40100 (the tape: the attacking
    # column on the minimap from 15:45 holds 40001 / 40002 / 40030 / 40031 with F40000's; the scorpion is in the melee
    # at 16:08-16:13, ten seconds into the fight: harness report row 'scorpions'; ours brought them once F40000 fell)
    {"on": "after", "step": "camp", "s": 1, "id": "attack", "do": [
        ("wake", 40000, 40005, 40100), ("march", 40000, ATTACKED), ("march", 40005, ATTACKED),
        ("march", 40100, ATTACKED)]},
    # (the original, planning/scripts/10233_grey1080_1250.md: 10430 in the camp cutscene, then Glen's 1480; the
    # Offensive lesson 13308 is 10_Defense_Camp's own, waiting on the player's Z.) The tape: the lesson 15:51-15:58, Z
    # at ~15:57.5 (the card's circle), Thompson's 1490 at 16:01.75: 1490 a pause after the Z (ours said it straight
    # after 1480: row '#41'); the key is prompted once the attack is in (its wake, the step the Z waits on) and the card
    # closed on it, as 12_Ruins_Tab's on its Tab
    {"on": "wake", "force": 40000, "id": "night attack"},
    {"on": "prompt", "keys": (KEY_AI_OFFENSIVE,), "needs": "night attack", "id": "offensive", "do": [("finish",)]},
    {"on": "after", "step": "offensive", "s": 3, "id": "hold the camp", "do": [
        ("say", THOMPSON, 1490), ("done", 120), ("panel", 110, 130)]},
    # then the camp's talk in one run, after 1490 (the tape 16:11-16:52: 1500 "Scorpion!", 1510-1530, 1560 2 s after
    # 1530, the notice 8140 / 8150, 1570, 1580; ours held 1560-1580 for a 20 s timer: rows 'hang on' / '#44')
    {"on": "wake", "force": 40005, "needs": "hold the camp", "id": "scorpions", "do": [
        ("say", THOMPSON, 1500), ("say", THOMPSON, 1510), ("say", GLEN, 1520), ("say", GLEN, 1530),
        ("say", THOMPSON, 1560), ("notice", 8140, 8150), ("say", THOMPSON, 1570), ("say", GLEN, 1580)]},
    # 11_Canon_Bomb (Golden Hammer, 10700 / 10710): its organ cannons F16100 fire on the invisible F46100 in the camp
    # and it disables the scorpions (6.1 s); the reinforcements have come: the room is won (the original 16:58-19:14,
    # 5.5 s after 1580). A time, as the success condition is (130 "Survive until reinforcements arrive"): the
    # harness's "the Dainargate Commander 40019 falls" (row '#44') reads the target frame gone at 16:45, where the
    # player switched to Strategy mode (frames 16:40-16:52), not a fall
    {"on": "after", "step": "scorpions", "s": 5, "do": [
        ("wake", 16100, 46100), ("cutscene", 11, 27), ("leave", 40001), ("leave", 40002), ("win",)]},
    # "You cannot die": Glen restores the hero (1600)
    {"on": "hp", "troop": "hero", "below": 15, "repeat": True, "do": [("say", GLEN, 1600), ("heal",)]},
    # the ending: 3_SealedTower (104 s; voices 10800-10890: thanks to the dwarves, Jade unseals the tower), then F19300
    # at the door with the hero (tile #112, 19:08) and the door (prop 10001) open
    {"on": "won", "do": [("cutscene", 3, 104), ("wake", 19300), ("open", 10001)]},
    # "Mission Complete: press Alt, then the Mission Complete button": the original's from 19:32.5, when the victory
    # window had closed (19:32.0) and the HUD's button had come, not with the ending (the 2 fps set 1171-1175)
    {"on": "closed", "do": [("notice", 8200, 8210)]},
]

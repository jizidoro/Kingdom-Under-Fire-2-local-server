"""Lunawing Sortie II 10362 (1_NewHamptonHighway zone6), the director's table.
The original's script, from the playlist, with its storyboard and our marks: planning/scripts/missions/10362.md
(`py tools/mission_scripts.py 10362`; storyboard captures/scripts/10362/board_1.jpg, panel_1.jpg).

How it is reached: Sortie I's win goes on into it (m10361 NEXT = 622: warpinfo 622, MISSION, 10362 group 1, the only
warp to 10362 and used by nothing else in the data; no quest, NPC menu, SpotEvent or table names 10362). The tape,
part 3: Sortie I's last line 4:56, the loading screen "New Hampton Highway" 5:23 (board tile #6), this room's panel
5:58 (#7), no window and no field between. Its win ends where Sortie I's quest ends (1150703 EndSpot 10351, the crash
site: the tape's 9:04 "Lunawing Crash Site", tile #17), with no result window (no %Mission_Grade / mission_reward row).

The tape (part 3 5:58-9:04; the panel every 30 s, panel_1.jpg):
  5:58  the panel: Mission Success Conditions 6060 "Escape from the enemy's antiaircraft fire concentration point",
        Mission Failure Conditions 6070 "Let the Lunawing be destroyed", and the Lunawing Shield bar, full (6:00)
  6:00  Jade 6100 "We've left Azilia and entered Eastern Hironeiden." / 6:06 Jager 6110 "It's so dark ..."
  6:18  Thompson 6150 "Head Cannons! Enemies are everywhere!" (tile #10: the airship ringed by red marks)
  6:24  Glen 6160 "Bah! ... too many of them! Come on, let's get out of here!" / 6:30 Golden Hammer 6180 "Ah, noooh!
        My cutie!" (the shield bar at about 40 % at 6:30)
  6:46-8:14  cutscene 0_Lunarwing_fall (index 0 = its .csset position, 87.7 s; "Skip Video (ESC)")
  8:22-8:54  cutscene 11_Lunawing_Crash (index 11, 91.8 s; voices 7020, 7000, 7010, 7030, 7040, 7100-7160; the player
        skipped it at 8:54), black, then the field 10351 at 9:04
The Steam community walkthrough guide 2011029967 (local copy: planning/reference/kuf2-wt/walkthrough_guide.txt
L178-185): "Mission Survive to get to Accolade",
"Mission Switches to Cutscene", "Your Immune to all dmg regardless of what you do", "After shield Reaches 30% Cutscene
happens even if you defeat All encomblossians to prevent all dmg due to Dialogue of Characters"; the cutscene: the
barrage breaks the shield, Vert knocks the Lunawing down. Neither cutscene is named by any table (no warp EnterScript,
no quest CutScene column; Info.pkg and Script.pkg scanned): only the mission's own script played them, so they play
in this room, where the zone parks the hero (60066, 201630) beside the crash site the crash scene shows (10351's start
(70851, 188572)); its one actor, the Hero, is always in the room.

The steps, each on its trigger:
- start: the airship (10000 루나윙_본체, handed as in Sortie I: game.PLAYER_MARKS) immune (the guide; Sortie I's
  untouchable flag) and the shipped mission camera 30003 on it (1_NewHamptonHighway.cam has the same preset as
  1_MistField.cam: eye/target reference 5, input mask 38; decoded 2026-10-24), then Jade's and Jager's lines (the tape:
  2 s after the panel).
- the barrage: the head cannons of force 21000 come in (their wake, game's proximity rule, as Sortie I's 8240 on its
  own 21000; inactive in the zone, the type made for this scene, 1320 헤드캐논_루나윙연출) -> Thompson, Glen, Golden
  Hammer, one after another (the tape's 6 s spacing: 6:18, 6:24, 6:30, so one dialogue, the display times from it).
- the fall: the shield breaks in the dialogue's wake, whatever the player does (the guide's "even if you defeat All
  encomblossians"): 13 s after Golden Hammer's line (the tape: 6180 at 6:30, the fall at 6:46) the room is won, and
  its ending plays the fall and the crash before the room is left (a "won" step, as Tower's 3_... ending).
  The Lunawing Shield bar itself is not drawn (its widget, ActGuiAddTroopsBarToMissionSituation 0xc8b4, is still to
  probe live; Sortie I has the same gap): what it showed is the 28 s from the barrage to the fall.

Ours: the speakers come from the tape's own name plates (tiles #8-#12), so none is ours; the barrage's trigger (the
force's proximity wake: the zone's bounds 10000-10006 carry numbers, not names, and no line ties one to them); the 13 s
standing for the shield's scripted fall (the original's drain is not shipped; the guide says it did not depend on the
fight). WIN = "table": the 16 HUD-hidden primitives of force 20000 (166020, UI_Visible False, active) and the waves
are not this room's end. Left out (on the map, not on the tape): 6120 / 6130 / 6140 (the river, "too quiet", Golden
Hammer's boast: nothing was read between 6110 at 6:06-6:12 and 6150 at 6:18), 6170 "What the...?!" and 6190 "Thompson!
Tell the refugees to brace themselves" (nothing read after 6180 until the fall), 6000-6020 (another mission's panel,
"Move to Destination")."""
GLEN, THOMPSON, GOLDEN_HAMMER, JADE, JAGER = "글렌", "톰슨", "골든해머", "제이드", "예거"
LUNAWING = 10000                 # 루나윙_본체, force 10000: the airship the player flies
FALL, CRASH = 0, 11              # 0_Lunarwing_fall (87.7 s), 11_Lunawing_Crash (91.8 s): their .csset positions

WIN = "table"

STEPS = [
    # take-off over Eastern Hironeiden, in the dark (the tape 6:00, 6:06)
    {"on": "start", "do": [("untouchable troop", LUNAWING, 1), ("camera troop", LUNAWING, 30003),
                           ("say", JADE, 6100), ("say", JAGER, 6110)]},
    # the antiaircraft concentration point: the head cannons (force 21000) come in (6:18, 6:24, 6:30)
    {"on": "wake", "force": 21000, "id": "barrage", "do": [
        ("say", THOMPSON, 6150, 6), ("say", GLEN, 6160, 6), ("say", GOLDEN_HAMMER, 6180)]},
    # the shield gives out (6:46): the room is won, its ending is the fall and the crash
    {"on": "after", "step": "barrage", "s": 13, "do": [("win",)]},
    {"on": "won", "do": [("cutscene", FALL, 88), ("cutscene", CRASH, 92)]},
]

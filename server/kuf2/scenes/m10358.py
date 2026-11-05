"""Grey Fog Streets 10358 (1_MistField zone5, "Burning Grey Fog Street"), the director's table.
The original's script, from the playlist, with its storyboard and our marks: planning/scripts/missions/10358.md
(`py tools/mission_scripts.py 10358`).

Sources: the map's missiontext (7100-7140, 7200-7320; `py tools/recon/mission_sheet.py 10358`), the map's cutscenes
(Data/Map/1_MistField/Mission/*.csdata in Map43.pkg, read with tools/pkgfind.py), the zone's bounds and forces, the
walkthrough (walkthrough_guide.txt L59-76: you can't die, help the villagers, ally Thompson, the Encablossian Leader,
Glen saves you at the end with Stormy Blade).
- Thompson (troop 10000) speaks 7100-7140: the cutscene 9_GreySmoke_Dynamic1 voices them as 1_mistfield_thomson_7100
  ... _7140 and walks troop 10000 and the hero from the zone start (308474, 179444) towards the burning village. It is
  the mission's opening (warp 613 has no EnterScript, so the lost mission script started it); here its lines play
  alone at the start. "Captain" is the hero (3204 "Hail to the Captain!").
- Left out: the panel 7000-7040; 3300-3307 (voiced in 11_Village_chief, which the client plays on the way back: the
  return warp 30001's EnterScript on the field 10350, game.leave_mission -> world.send_field_entry); 3000-3500,
  5000-5970, 6000-6130 and 8000-8570 (the field, Glen's camp and Lunawing Sortie I: the playthrough's "8550 Defeat
  Encablossians" at 25:47.75 and "5050 Encablossian HP" at 26:12 are look-alike reads, frames 25:47.5 / 25:48.0 and
  26:11.5, tools/playthrough.py lookalike); 3400-3402 (12_GoldenHammer, quest 1150308's scene in the field, part 1
  37:32); 7205, nowhere on the tape.
- The tape (playthrough part 1, 21:58-29:00; the harness, captures/harness/10358_report.md, and its frames, py -m
  video_script sheet): each step below names the tape time and the frames or the harness row it follows (refinement
  2026-09-30). The areas it marks (green pillars and glowing ground, ActGuiSetHighlightArea) are read off the frames:
  part 1's minimap draws their rings pale, which the effects channel does not read.
- The route, from the zone: the north gap in the village wall (bounds 10002, then 10001) → the militiaman 11000 holding
  force 20000 → the isolated villagers (force 15000: 8 inside bound 10008, 12 north of bound 10000) → the central
  plaza (force 21000 against militia 12000) → the boss plaza (bound 10004; the Encablossian Leader 22003 "보스" in
  force 22000) → through the red curtain 10532 to the south-east street (bound 10007). The staging force 26000
  (inactive) stands in two clusters on either side of that street, and the cutscene GLG shows Glen, Thompson and the
  hero on that street among 87 Encablossian and 27 human extras, in slow motion. That is the finale: 7290 / 7300
  "sandwiched ... surrounded", then Glen's rescue. GLG has no subtitles.
Ours: every trigger below. The militiaman 11000 says 7210 / 7220 (7220 thanks Thompson, and 7230 answers "You protect
your villagers!"). A villager says 7240, Thompson 7310 ("Gah, I don't know what to do!", the original's box, 23:52; its
trigger is not on the tape, see its step); force 15000 (never spawned by the plan: staging civilians) comes at the start. 7250
plays when force 21000 is down, because the destroyable barricades 10346 / 10347 (type 64) wait on that force in
game.mission_plan. 7260 plays as the hero enters the boss plaza (bound 13001), 7270 when the boss falls (id order
7260 → 7270), 7280 after it (the original's order,
planning/scripts/10358-..._tiouWoPSPks_000.md 25:44-25:52; it had been bound 10010's). The guide notices are the
original's: 7820 / 7830 (the Oak Barrel) after 7220, 7800 / 7810 (the enemy commander) after 7260. The room is won
by the finale on the south-east street (WIN = "table"; the boss's fall no longer ends it: the pointer then leads to
bound 10007, the table's next place). The heal
at 15 % hp is Thompson's 7320 "Let me heal you!", this mission's "you can't die".
- The flight to 도망 (bound 10006, "flee", a 600 circle by the zone start). The tape (the minimap's allied marks,
  planning/playthrough/part_tiouWoPSPks.10358.channels.json; COMPANIONS-EVIDENCE §4): a group stands on the
  militiaman 11000's spawn from 22:17.5 (the frame 22:50: militia and villagers round the hero at the gate), runs at
  ~23:06 with 7230 "You protect your villagers!" east through the gate and along the road, (287474, 190593) 23:08.5,
  (289688, 189875) 23:12.5, (304218, 182035) 23:40.5, and is gone at 23:42.5. The zone's MissionPaths 10002-10021
  are that road: twenty lanes from the village (12 starting by the villagers north of bound 10000, 8 by those in
  10008) through the north gap to 도망. Ours: each villager its nearest lane, the militiaman the lane nearest his
  spawn (10004, joined where it passes him), the gate group with 7230 and the 10008 group after its 7240 (that beat
  is ours: the tape shows no mark of theirs); each leaves the battle when the host reports it inside 도망."""
THOMPSON = 10000                 # zone troop 10000 (162010 + NP leader "Thompson")
ESCORT = {10000}                 # Thompson goes along with the hero and fights
MILITIAMAN = 11000               # the village militiaman holding force 20000 inside the north gap
VILLAGER_B = 15014               # force 15000, the 8 villagers inside bound 10008
VILLAGER_A = 15001               # force 15000, the 12 villagers north of bound 10000
WIN = "table"                    # won by the finale, not by the boss's fall (the last hostile)
SANDWICH_S = 1                   # 7300 shows 26:08.75 (4 s in our queue), the picture dims from 26:13 and is black at
                                 # 26:14 (frames 26:11.5 / 26:13.0): Glen's rescue 1 s after the line
GLG = 2                          # Glen's rescue, the file GLG: place 2 of the map's cutscene list (1_MistField.csset,
                                 # cutscenes.json "slot"; the action's number is the list place, INVENTORY)
GLG_S = 85                       # its length (85,000 ms); it has no ACTOR track, so no cast must be in first
FLEE = 10006                     # bound 도망 "flee", where the twenty lanes end
GATE_FLIGHT = {MILITIAMAN: 10004,                     # the gate group with 7230: lane by nearest start (ours)
               15001: 10013, 15002: 10010, 15003: 10012, 15004: 10011, 15005: 10002, 15006: 10004,
               15007: 10009, 15008: 10006, 15009: 10003, 15010: 10008, 15011: 10007, 15012: 10005}
STREET_FLIGHT = {15013: 10020, 15014: 10021, 15015: 10017, 15016: 10016, 15017: 10019, 15018: 10018,
                 15019: 10015, 15020: 10014}           # the villagers in bound 10008, after their 7240

STEPS = [
    # the road: the village is burning: the opening cutscene 9_GreySmoke_Dynamic1 (28 s, voices 7100-7140; the
    # original plays it first, planning/scripts/10358-..._tiouWoPSPks_000.md 21:58). As it ends Thompson says 7200
    # (tape 22:16.5, the hero 3,835 outside bound 10002: harness report row #1, frames 22:12-22:18) and the north gap
    # is marked: a green pillar and glowing area ahead from 22:16 (frames; the effects channel's MINE pillars
    # 22:17-22:32, no ring: part 1's minimap draws it pale)
    {"on": "start", "id": "road", "do": [
        ("wake", 15000),                            # "Help the villagers" (walkthrough L61): they stand in the streets
        ("cutscene", 9, 28), ("say", THOMPSON, 7200), ("highlight", 10002)]},
    # the village wall: the north gap (10002 outside it, 10001 inside, force 20000 against the militiaman ahead). The
    # hero passes through the mark at 22:33 (bound 10002 at 22:33.5), it goes down and the gate's shows from 22:34 until
    # he enters 10001 at 22:40.5; nothing is said at the wall (frames 22:32-22:44). 7205 ("The Encablossians and the
    # village militiamen are fighting inside the village!"), which this step said, is nowhere on the tape
    {"on": "bound", "bound": 10002, "do": [("highlight", 10002, 0), ("highlight", 10001)]},
    {"on": "bound", "bound": 10001, "id": "gate", "do": [("highlight", 10002, 0), ("highlight", 10001, 0), ("say", MILITIAMAN, 7210)]},
    # force 20000 down: the last of its monsters falls among the militia at 23:01 (the target frame's last read
    # 23:01.5), 7220 at 23:01.75, then a green line towards the plaza (frames 22:58-23:04; the harness has no rule
    # for it: the fight near the hero is inside his sight halo on part 1's minimap, report row #3 a REVIEW timer)
    # With 7230 the militiaman and the villagers by the gate run for 도망 along the zone's lanes (the minimap: the group
    # on his spawn runs from ~23:06 and is gone at 23:42.5)
    {"on": "down", "force": 20000, "needs": "gate", "do": [
        ("say", MILITIAMAN, 7220), ("notice", 7820, 7830),
        *[("route", troop, lane, FLEE) for troop, lane in GATE_FLIGHT.items()], ("say", THOMPSON, 7230)]},
    # the isolated villagers: 8 at bound 10008 on the way to the plaza (they cry out, then take their lanes), 12 north
    # of bound 10000
    {"on": "bound", "bound": 10008, "do": [
        ("say", VILLAGER_B, 7240), *[("route", troop, lane, FLEE) for troop, lane in STREET_FLIGHT.items()]]},
    # OPEN (harness report row #5): the tape shows 7310 at 23:52 in the central plaza's fight with force 21000, the
    # hero at (278031, 192010), never near bound 10000 (10,000 away then; the route never comes within 2,225 of it),
    # and 7281 nowhere. No change the channels or the frames show comes before it: no area entered (the harness's
    # 10008, 44.5 s before, is past its ENTER_LAG_S), the hero's hp steady about 340 (HUD 23:46-23:55), Thompson's
    # bar full (frames 23:47-23:53), the Dainargate the hero fights (force 21000's 21002) at 141 hp and falling at
    # 23:55, after it. Its trigger is not on the tape: left as it was, for the owner
    {"on": "bound", "bound": 10000, "do": [("say", THOMPSON, 7281), ("say", THOMPSON, 7310)]},
    # the central plaza cleared (force 21000): its barricades. The hero fells its troops one by one near their zone
    # points (the target frame: Claw 23:21-23:31, Dainargate 23:42-23:55, Encablossian Primitive 24:01-24:07, Head
    # Cannon 24:11-24:16), the last at 24:16, then 7250 at 24:17.5 with a green line to the red-lit barricade (frames
    # 24:10-24:19; the harness: report row #6, a REVIEW timer for want of a rule)
    # live 2026-10-24 (AC3): the militia felled force 21000 alone a minute in, 7250 long before the hero came; the
    # tape's hero is at the plaza when it plays, so it also waits for the hero past the Oak Barrels (bound 10003, the
    # passage onto the central plaza; a fall before then fires as the hero arrives)
    {"on": "bound", "bound": 10003, "id": "central plaza"},
    {"on": "down", "force": 21000, "needs": "central plaza", "do": [("say", THOMPSON, 7250)]},
    # the boss plaza: the Encablossian Leader 22003. "There! That brawny one must be their captain" as the hero comes
    # down into the plaza: bound 13001 entered at 24:27.5, 7260 at 24:28 (harness report row #7, frames 24:25-24:31);
    # force 22000 had fought the militia 13000 there since 22:22 (the minimap's R1 / C1), so its engage is no cue.
    # The notice follows the line (24:33, read as Grey Rock's 6022 / 6023, the same texts)
    {"on": "bound", "bound": 13001, "id": "plaza", "do": [("say", THOMPSON, 7260), ("notice", 7800, 7810)]},
    # the boss down: "Phew", then the villagers still cut off (the original: 7270 at 25:43, 7280 at 25:48; his frame
    # at 0 hp 25:40, gone 25:42: harness report row #8, its "8550" a misread). With 7280 the south-east street is
    # marked: a green line and a pillar and glowing area there, the hero inside it at 26:02.5 (frames 25:48-26:03,
    # effects.pillars 25:52-25:59)
    {"on": "down", "troop": 22003, "needs": "plaza", "do": [("say", THOMPSON, 7270), ("say", THOMPSON, 7280), ("highlight", 10007)]},
    # "you can't die in this mission": Thompson restores the hero
    {"on": "hp", "troop": "hero", "below": 15, "repeat": True, "do": [("say", THOMPSON, 7320), ("heal",)]},
    # the finale, as the original plays it (playthrough part 1, frames 26:02-26:15 and the extracted script, its
    # storyboard 10358 #33-#41): on the south-east street the staging force 26000 swarms the hero, "sandwiched"
    # 26:03.75, "surrounded" 26:08.75, black at 26:14, then Glen's rescue, the scene GLG (26:15-27:48, "#36 26:24
    # cutscene GLG": the hero surrounded, Glen and the militia charging in), then the win with no result window
    # (decision B2: no mission_reward / %Mission_Grade row, game.end_without_window): the room is left at once, the
    # field loads (27:48-28:08) and the return warp 30001 plays 11_Village_chief there (28:08-29:00, 3300-3307), as
    # on the tape. The script's "Encablossian HP" (5050, 26:12) is the target frame of a selected enemy ("Lv. 2
    # Encablossian Primitive / HP 765", frame 26:11.5), no scripted notice
    {"on": "bound", "bound": 10007, "id": "sandwich", "do": [
        ("highlight", 10007, 0), ("say", THOMPSON, 7290), ("wake", 26000), ("say", THOMPSON, 7300)]},
    {"on": "after", "step": "sandwich", "s": SANDWICH_S, "do": [("cutscene", GLG, GLG_S), ("win",)]},
]

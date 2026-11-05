"""Azilia Castle 50116 (1_AziliaCastle zone1), the prologue: a new character's first mission, the director's table.
The original's script, from the playlist, with its storyboard: planning/scripts/missions/50116.md (part 1 4:06-13:08,
`py tools/mission_scripts.py 50116`); this table's evidence: planning/agents/reports/2026-10-24_prologue.md.

Sources: the map's missiontext (lines 108-1860, 5000-6320, 10000-10500, 60000-63030; `py tools/recon/mission_sheet.py
50116`), the zone's bounds, forces and props, the map's cutscenes' own scripts (planning/scripts/cutscenes.json), the
tape's frames at 2 fps (the parts12 video cache, part 1 tiouWoPSPks: 4:07-12:40 looked at frame by frame, the OCR of
every cached frame read), the owner's walkthrough (walkthrough_guide.txt L39-49: the colossus, "hit his arms", the
safe zone, "YOU WONT DIE", Celes and the elf, the tyrant, the knights' full heal, the king, the meteor storm, then
Misty Field's camp). Speakers from the tape's help box (name and face): Jager for the opening and the north-east gate,
Brenon after the retreat, an Azilia Archer in the fire-arrow scene (the scene's own lines), Azilia Infantrymen and an
Azilia Spearman for 10240 / 10290 / 10330 / 10360 / 10380 (each given to an infantry or spearman troop standing there:
ours).

The tape's flow and what each beat waits for (tape times, part 1):
- the courtyard (4:07): "Move to the marked location." (MoveToArea, W A S D) with the panel up (640-680, the room's
  mission_text; the event list's 4:20 for 660 is a late read: the 4:07 frame shows it), a green pillar far down the
  street; Jager and the soldiers run ahead (0_Azilia_Invasion's moves: Jager to 30023, the courtyard's soldiers
  11000-11046 to Phase1_Troop_Actor1). The hero walks into the mark at the strip Area_Tutorial_Close (4:14), the card
  goes, Jager's 10010 (4:16), the next mark ahead (4:22.5); in the ring among the soldiers at the gate
  (Phase1_Troop_Move2, 4:31.5) Jager's "Open the gate! Now!" (4:32.5), the gate opens, "Right then, let's fight!"
  (4:36.5), the fight outside (allies F10010 / F10011 against the primitives F20000 / F20010 along the wall).
- outside the gate (가두기2 entered, 4:44): 10050 and the lessons, each closed on the key it asks for, the next coming a
  moment after (frames: V at ~4:49.5 -> 10070 4:53; the left button ~4:58 -> 10080 4:59.5; the right button ~5:04 ->
  10090 5:05; a skill key ~5:11 -> 10500 5:21): Command_V (V), BaseAttack (the left button, KEY_Pad_A_Press),
  SubAttack (the right button, KEY_Pad_X_Press), UseSkill (1-8); then 10500, then "Press F to check!" (10100, 5:27.5)
  with the client's F prompt "Look far" (textui 9000: the 0x50c1 F icon, frame 5:27.5); the F (~5:32) shows the far
  view, HUD up (frame 5:33: the colossus and wyrms beyond the field: 20_AziliaCastle_Action_Cam1, 6 s); the fight goes on
  (5:38-5:45), then the retreat 2_Azilia_fallback (5:45-6:23, 33 s; "Enter the castle." 5050 read at 5:56): its SCRIPT
  enables F19100 / F19200 / F19300 / F39100 and walks them, runs the hero in through the gate, closes it, leaves the
  hero, Jager and Brenon inside, enables F19600, F10015 and the archers 12012 at its end.
- inside (6:23): Brenon's 10120 / 10130 ("take the archers to the battlements on the right side of the gate": the
  archers 12012 become the player's, HAND_LATER), "Follow the green line" (5060 / 5061, 6:33, a green pillar up the
  stairs): the hero walks to Phase2_Hero_Move1 on the west battlements (6:41) and 23_LEV_Azilia_FireArrowAttack plays
  (6:41.4-7:25: its own 10140-10200, the fire arrows, the colossus 10099 walked to the wall; dated by its 10180 at 7:04
  = 22.6 s in); then "Move while avoiding the areas marked red" / the Charge key (5040 / 5031, 7:25) with the next
  mark along the walkway, QTE존_진입 (7:29-7:36); there the Escape lesson (Groggy, 7:47.5: page 1600, then 1090 on
  Space) and the Block lesson (Defence, 7:57.5, Shift); "Avoid or defend the area marked red" (5030 / 5031, 8:03) and
  Brenon's "Attack it's arms!" (8:07.5); the colossus (197 hp, its bar 8:03 -> 48 % 8:23) falls (8:38): "The
  monster's down!" (8:39), Brenon's "go down to the north-east gate" (8:45), the green line again (8:47), Jager's "The
  gate has been breached!" / "Block the gate!" (8:51 / 8:57) as the hero walks down.
- the north-east gate (9:02): the class's rune lesson where the hero stands (the Berserker's Rune_Skill_Regnier pages
  9:03-9:13, "[F] Next", "+20" Dark Energy), Jager's 10280 (9:14), "Protect the Castle Gate" with a clock 00:00:20 in
  the panel (9:14 -> 00:00:00 at 9:36), "Hold your ground until ally Troops arrive" (5000 / 5001, 9:21.5), the fight
  at the gate; 10290 (an Azilia Spearman, 9:40), "Our reinforcements have arrived!" (5070 / 5071, 9:44, red-caped
  soldiers pouring in), Jager's "You go to the Palace now!" (9:51).
- the town (10:06): "Defeat the enemy highlighted in red" (5020 / 5021) over F21000's leaders (the red pillars 10:07-
  10:41), "Huh! Thank you!" (10360, 10:24), the Dainargate Commander 21031 (target frame 10:30-10:37), "We'll take care
  of this place. Please go to His Majesty now!" (10380, 10:43.5), a green mark (10:46.5); the palace stairs:
  3_Azilia_CELLES (10:54-11:38, Celes and the elf: lines 62000-62040; it leaves the hero at 40014 walking to 40019).
- the palace yard (11:44): the tyrant 10257 (F20500, 234 hp: "130 (55.5%)" 12:10) and its primitives; the green line
  (12:24); a wounded infantryman's "His Majesty... Up there..." (12:36.5), 4_Azilia_destroy (93.7 s: 63005 at 13:08),
  5_Azilia_destroy (the meteor storm, its KUF2 logo 15:03-15:06), then the Mist Field loading (15:16) and the camp
  (17:31): no result window (game.NO_WINDOW), the room left for 10352 (game.end_without_window, 0x4041), where the
  client's spot change away from 50116 sends 0x10d6 (world.prologue_done; the win sets tutorial_done too).

Which bound each beat waits on is ours, read from the bound names and the tape's places (each named above). Every
"s" is ours (the tape's pauses). Not played, with the reason: 0_Azilia_Invasion (the original's opening lesson
scene: thirteen System_WaitState holds -1..-9, -20, -21 its server stepped; INVENTORY "System_WaitState": several
waits cannot be released ahead), 24_LEV_Azilia_Evasion / 1_Azilia_Retreat (the colossus's grab, Groggy and Defence
inside the scene: waits -101 / -24 / -7 / -8 / -9 and System_CheckActionEvent, whose hold is not read), 6_Azilia_Phase4
(waits -10..-14), the class rune scenes 8 / 10 / 12 / 14 / 21 (waits -10..-13) and their combo scenes 9 / 11 / 13 / 15
(none on the tape: no 1290 / 1300 read, and their troop 21000 is the town's), 19_AziliaCastle, 22_LEV_Azilia_Retreat,
7 / 16 (the juggernaut, not on the tape), 17_Azilia_Boss_Stage (waits -100 / -110): their lessons are this table's
pop-ups, each closed on its key (cond 0xcb2b + prompt 0x50c1), as Tower's. The lost mission Lua's troop AI (the
staging rows are TROOPAI 50000, waiting to be hit) is not rebuilt: the enemies are marched at the hero's places
(engage 1) instead; the colossus's red areas and its grab are not."""
from ..director import (COND_TUTORIAL_PAST as TUTORIAL_PAST, KEY_ACTION, KEY_DASH, KEY_FRIEND_AND_FOE, KEY_GUARD,
                        KEY_PAD_A, KEY_PAD_X, KEY_PAD_X_HOLD, KEY_RUNE, KEY_SKILL_SLOTS)

JAGER, BRENON = "예거_1", "브레논_1"          # F10000: Jager at the hero's start, Brenon outside the gate
ARCHERS = 12012                          # 편입궁병2, the archers handed with Brenon's 10130 (F10020)
COLOSSUS = 10099                         # 연출거신체 (F40000, 111210 "Colossus", 197 hp, team 1): the one
                                         # 23_LEV_Azilia_FireArrowAttack walks to the wall (40022) and the hero fights;
                                         # QTE거신체 10100 (F44000, team 255) is the grab scenes' and stays out
TYRANT = 10257                           # F20500's 111290 "Tyrant" (234 hp) in the palace yard
WOUNDED = 19870                          # 대사용_부대 ("the troop for the line"): "His Majesty... Up there..."
WALL_SOLDIER = 19751                     # an infantryman at the colossus's end of the walkway (F19751)
SPEARMAN = 11161                         # F11160's first, a spearman (111560): "Our reinforcements have arrived"
SAVED, SAVED2 = 18011, 18012             # F19000, two infantrymen by the town's F21000 (10360, 10380)
# the beats' places (each a zone EventBound)
TUTORIAL_CLOSE = "Area_Tutorial_Close"   # the strip across the courtyard street (35036)
GATE_CROWD = "Phase1_Troop_Move2"        # the ring among the soldiers inside the main gate (35038)
OUTSIDE = "가두기2"                       # the field outside the main gate, its north edge the gate (30007)
BATTLEMENTS = "Phase2_Hero_Move1"        # on the battlements west of the gate (35004)
QTE = "QTE존_진입"                        # across the walkway where the colossus stands (40032)
NE_STREET = "Phase4_Hero_Move_1"         # below the walls by the north-east gate: 6_Azilia_Phase4 walks the hero
                                         # there (35006)
NE_GATE_IN = "타일런트이동"               # just inside the north-east gate, where its tyrant 10263 goes (40021)
SPEARMEN = "창병이동"                     # the spearmen's place inside the north-east gate (35016)
TOWN = "시가지쪽이동2"                    # the strip on the road into the town (35044)
STAIRS = 30021                           # below the palace stairs, where Celes comes (3_Azilia_CELLES ends at 40014)
YARD = "보스전"                           # ("boss fight") the strip across the palace yard (35047)
END = "End_Game"                         # the strip at the yard's far end (30016)
HOLD_S = 20                              # the Castle Gate Defence Timer: 00:00:20 (the tape 9:14-9:36)

HOLD_PROPS = {10003, 10007, 10004}       # the main gate (333 opening / 334 shaking, at one place) until Jager's
                                         # order; the north-east gate (335) until "The gate has been breached!"
HAND_LATER = {ARCHERS}
WIN = "table"                            # no troop of the zone is worth exp: the room is won by its last scene

# the class's rune lesson at the north-east gate (createcharacter HeroId -> the map's class rune scene): its pop-ups in
# order, each (missiontutorial row, the page its scene waited past (CheckCompleteTutorialSub), the keys it waited for
# (CheckInputEvent)): 8_Azilia_Glen_R (7, 2, R), 14_Azilia_Olivia_R (10, 4, R; then 31 ChargeShot_Olivia, the right
# button held), 21_Azilia_Druid_R (11101, 1, R; 11102, 2, R twice), 10_Azilia_Isa_R (8, 4, R), 12_Azilia_Reg_R (9, 4,
# R: the tape's). The Sorceress (5) has no scene here and no line of her Rune_Skill_Helena (10012) in this map's text
RUNE_LESSONS = {
    0: (("Rune_Skill_Glen", 2, (KEY_RUNE,)),),
    1: (("Rune_Skill_Olivia", 4, (KEY_RUNE,)), ("ChargeShot_Olivia", -1, (KEY_PAD_X_HOLD,))),
    2: (("111_Summon_Skill_Druid", 1, (KEY_RUNE,)), ("111_Rune_Skill_Druid", 2, (KEY_RUNE, KEY_RUNE))),
    3: (("Rune_Skill_Isabella", 4, (KEY_RUNE,)),),
    4: (("Rune_Skill_Regnier", 4, (KEY_RUNE,)),),
}
ONE_PAGE = {"ChargeShot_Olivia"}         # completed (0xc898); the others closed on their last key (0xc897)
# A completed card (0xc898: its circle and sound) stays up until it is closed (0xc897): live 2026-10-24 (the sandbox
# run of main 905a117) MoveToArea stayed to the gate and UseSkill until Groggy replaced it. The tape closes each one-page
# card after its circle (part 1, 4 fps, build/order-c captures/order-c/p1_*): MoveToArea 4:15.1 -> 4:16.1, Command_V
# 4:49.6 -> 4:50.6, BaseAttack 4:56.9 -> 4:58.9, SubAttack 5:04.1 -> 5:04.9, UseSkill 5:12.1 -> 5:14.1, the next line's
# box a quarter second after (10010, 10070, 10080, 10090; not 10500, 5:19)
CARD_SHOWN_S = 1                         # ours for the Ranger's ChargeShot_Olivia (no frames: the tape's hero is a
                                         # Berserker), the tape's other one-page cards 0.75-2 s


def rune_lessons():
    """The class lessons' steps: per class a pop-up a moment after the hero reaches the street, its page asked, its keys
    prompted in turn; the last key of each class is step "rune key", which the gate's defence follows."""
    out = []
    for cls, lessons in RUNE_LESSONS.items():
        before = ("after", "street")
        for k, (name, page, keys) in enumerate(lessons):
            shown, seen = f"lesson {cls}.{k}", f"page {cls}.{k}"
            out.append({"on": "after", "step": before[1], "s": 1, "class": cls, "id": shown,
                        "do": [("tutorial", name)]})
            out.append({"on": "cond", "cond": (TUTORIAL_PAST, name, page), "needs": shown, "class": cls, "id": seen})
            need = seen
            for j, key in enumerate(keys):
                last = j == len(keys) - 1
                sid = ("rune key" if k == len(lessons) - 1 else f"keys {cls}.{k}") if last else f"key {cls}.{k}.{j}"
                step = {"on": "prompt", "keys": (key,), "needs": need, "class": cls, "id": sid}
                if last:
                    step["do"] = [("complete",) if name in ONE_PAGE else ("finish",)]
                out.append(step)
                if last and name in ONE_PAGE:   # the circle, then the card goes
                    out.append({"on": "after", "step": sid, "s": CARD_SHOWN_S, "class": cls, "do": [("finish",)]})
                need = sid
            before = ("after", need)
    out.append({"on": "after", "step": "street", "s": 1, "class": 5, "id": "rune key"})
    return out


STEPS = [
    # the courtyard: the card and the first mark; Jager and the soldiers run ahead to the gate (0_Azilia_Invasion's
    # Troop_MoveToArea at 5-200 ms: 10000 to 30023, 11000-11049 to 35051)
    {"on": "start", "id": "start", "do": [
        ("tutorial", "MoveToArea"), ("highlight", TUTORIAL_CLOSE), ("march", JAGER, 30023),
        ("march", 10005, "Phase1_Troop_Actor1"), ("march", 10006, "Phase1_Troop_Actor1")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "MoveToArea", -1), "needs": "start", "id": "move shown"},
    # the mark reached (4:15.1): the card completes ("Area_Tutorial_Close"), it goes (4:16.1), Jager's 10010 (4:16.4),
    # the next mark (4:22.5)
    {"on": "bound", "bound": TUTORIAL_CLOSE, "needs": "move shown", "id": "first mark", "do": [
        ("complete",), ("highlight", TUTORIAL_CLOSE, 0)]},
    {"on": "after", "step": "first mark", "s": 1, "id": "card gone", "do": [
        ("finish",), ("say", JAGER, 10010), ("highlight", GATE_CROWD)]},
    # the ring at the gate (4:31.5): "Open the gate! Now!" (4:32.5), the gate opens and the fight outside comes in
    # (the walls' allies F10010 / F10011 and the primitives F20010, laid out in pairs along the wall, 138-162 k: they
    # fight there; F20000's three before the gate run at it), "Right then, let's fight!" (4:36.5) and everyone out with
    # the hero. Not F20010 at the gate: marched there (until 2026-10-24) its 21 troops converged on the hero, live two
    # of them (10321 / 10272, from the line's two ends) struck a level-1 Gunslinger 2-3 times a second for ~10 a hit
    # (373 -> 89 in 8 s), where the tape's hero (a level-1 Berserker, 450 hp) takes three hits of 1-6 in the minute
    # outside (4:44-5:45: 450, 447-446 at 5:03-5:07, 444 at 5:09.6, 448, 450 by 5:16; build/order-c's frames)
    {"on": "bound", "bound": GATE_CROWD, "needs": "first mark", "id": "gate", "do": [
        ("highlight", GATE_CROWD, 0), ("say", JAGER, 10020), ("open", 10003), ("open", 10007),
        ("wake", 10010, 10011, 20000, 20010), ("march", 20000, OUTSIDE),
        ("say", JAGER, 10030), ("march", JAGER, OUTSIDE), ("march", 10005, OUTSIDE), ("march", 10006, OUTSIDE)]},
    # outside (4:44): 10050 and Enemy Identification (V)
    {"on": "bound", "bound": OUTSIDE, "needs": "gate", "id": "outside", "do": [
        ("say", JAGER, 10050), ("tutorial", "Command_V")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "Command_V", -1), "needs": "outside", "id": "v shown"},
    {"on": "prompt", "keys": (KEY_FRIEND_AND_FOE,), "needs": "v shown", "id": "identified", "do": [("complete",)]},
    # the V card goes 1 s after its circle, "Get it now? Right, go wipe them out!" and Basic Attack (the left button)
    {"on": "after", "step": "identified", "s": 1, "id": "attack", "do": [
        ("finish",), ("say", JAGER, 10070), ("tutorial", "BaseAttack")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "BaseAttack", -1), "needs": "attack", "id": "attack shown"},
    {"on": "prompt", "keys": (KEY_PAD_A,), "needs": "attack shown", "id": "attacked", "do": [("complete",)]},
    # the card goes 2 s after its circle, "Come on, you can do more than this!" and Special Attack (the right button)
    {"on": "after", "step": "attacked", "s": 2, "id": "special", "do": [
        ("finish",), ("say", JAGER, 10080), ("tutorial", "SubAttack")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "SubAttack", -1), "needs": "special", "id": "special shown"},
    {"on": "prompt", "keys": (KEY_PAD_X,), "needs": "special shown", "id": "specialed", "do": [("complete",)]},
    # the card goes (0.75 s after its circle), "This time, use a Skill attack" and the skill slots (1-8)
    {"on": "after", "step": "specialed", "s": 1, "id": "skill", "do": [
        ("finish",), ("say", JAGER, 10090), ("tutorial", "UseSkill")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "UseSkill", -1), "needs": "skill", "id": "skill shown"},
    {"on": "prompt", "keys": KEY_SKILL_SLOTS, "needs": "skill shown", "id": "skilled", "do": [("complete",)]},
    {"on": "after", "step": "skilled", "s": 2, "do": [("finish",)]},          # the card goes 2 s after its circle
    # the finishing-blow reminder (5:21), then "The ground is shaking! Press F to check!" (5:27.5) and its F prompt
    {"on": "after", "step": "skilled", "s": 4, "id": "reminder", "do": [("say", JAGER, 10500)]},
    {"on": "after", "step": "reminder", "s": 0, "id": "shaking", "do": [("say", JAGER, 10100)]},
    {"on": "prompt", "keys": (KEY_ACTION,), "needs": "shaking", "id": "look", "do": [("cutscene", 20, 6)]},
    # the retreat (5:45): the scene's cast in first (the scene enables and walks them; it skips a troop not in the room),
    # "Enter the castle." with it
    {"on": "after", "step": "look", "s": 7, "id": "retreat", "do": [
        ("wake", 19100, 19200, 19300, 39100), ("notice", 5050), ("cutscene", 2, 34)]},
    # inside (6:23): the soldiers the scene enables at its end, Brenon's orders, the archers handed, the green line to
    # the battlements; Jager to the north-east gate ("Jager, take the northeast gate!")
    {"on": "after", "step": "retreat", "s": 0, "id": "split", "do": [
        ("wake", 19600, 10015), ("say", BRENON, 10120), ("march", JAGER, SPEARMEN), ("say", BRENON, 10130),
        ("hand", ARCHERS), ("notice", 5060, 5061), ("highlight", BATTLEMENTS), ("point", BATTLEMENTS)]},
    # the battlements (6:41): the fire-arrow scene with the colossus and the soldiers it uses (19700 it enables, the
    # walkway's 19750 / 19751)
    {"on": "bound", "bound": BATTLEMENTS, "needs": "split", "id": "battlements", "do": [
        ("highlight", BATTLEMENTS, 0), ("wake", 40000, 19700, 19750, 19751), ("cutscene", 23, 45)]},
    # its end (7:25): the red areas, the Charge key, the mark along the walkway
    {"on": "after", "step": "battlements", "s": 0, "id": "evade", "do": [
        ("notice", 5040, 5031), ("highlight", QTE), ("point", QTE)]},
    # at the colossus (7:47.5): Escape (Groggy: its F page, then Space) and Block (Defence: its F page, then Shift)
    {"on": "bound", "bound": QTE, "needs": "evade", "id": "qte", "do": [("highlight", QTE, 0), ("tutorial", "Groggy")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "Groggy", 0), "needs": "qte", "id": "groggy page"},
    {"on": "prompt", "keys": (KEY_DASH,), "needs": "groggy page", "id": "escaped", "do": [("finish",)]},
    {"on": "after", "step": "escaped", "s": 2, "id": "defence", "do": [("tutorial", "Defence")]},
    {"on": "cond", "cond": (TUTORIAL_PAST, "Defence", 0), "needs": "defence", "id": "defence page"},
    {"on": "prompt", "keys": (KEY_GUARD,), "needs": "defence page", "id": "blocked", "do": [
        ("finish",), ("notice", 5030, 5031), ("say", BRENON, 10230)]},
    # the colossus falls (8:38): 10240, 10250, the green line down to the street, the north-east gate breached (its gate
    # down, its attackers F20450 in, the defenders F11150 at them), 10260 / 10270
    {"on": "down", "troop": COLOSSUS, "needs": "blocked", "id": "colossus down", "do": [
        ("say", WALL_SOLDIER, 10240), ("say", BRENON, 10250), ("notice", 5060, 5061), ("highlight", NE_STREET),
        ("point", NE_STREET), ("open", 10004), ("wake", 20450, 11150), ("march", 20450, NE_GATE_IN),
        ("march", 11150, NE_GATE_IN), ("say", JAGER, 10260), ("say", JAGER, 10270)]},
    # the street (9:02): the class's rune lesson (rune_lessons)
    {"on": "bound", "bound": NE_STREET, "needs": "colossus down", "id": "street", "do": [("highlight", NE_STREET, 0)]},
    *rune_lessons(),
    # the gate held (9:14): Jager's 10280, the panel's "Protect the Castle Gate" and its clock, 5000 / 5001, the rest of
    # the attack through the gate (F20400, F20220, the lesson's F23000)
    {"on": "after", "step": "rune key", "s": 1, "id": "hold", "do": [
        ("say", JAGER, 10280), ("clock", 690, 700, HOLD_S), ("notice", 5000, 5001), ("wake", 20400, 20220, 23000),
        ("march", 20400, NE_GATE_IN), ("march", 20220, NE_GATE_IN), ("march", 23000, NE_GATE_IN)]},
    # the clock at 0 (9:35): the reinforcements (F11160, to the spearmen's place), "Protect the Castle Gate" leaves the
    # panel (its 00:00:00 gone 9:39.9, its heading 9:40.9, build/order-c's frames), 10290 (9:40.8), 5070 / 5071 (9:44)
    {"on": "after", "step": "hold", "s": HOLD_S, "id": "reinforcements", "do": [
        ("wake", 11160), ("march", 11160, SPEARMEN), ("clock off", 690), ("say", SPEARMAN, 10290),
        ("notice", 5070, 5071)]},
    # "I'll take care of this place. You go to the Palace now!" (9:51); the way into the town shown (ours: no mark on
    # the tape 9:52-10:06)
    {"on": "after", "step": "reinforcements", "s": 4, "id": "to the palace", "do": [
        ("say", JAGER, 10305), ("point", TOWN)]},
    # the town (10:06): F21000 and the street fight round it, its leaders marked red
    {"on": "bound", "bound": TOWN, "needs": "to the palace", "id": "town", "do": [
        ("wake", 21000, 28000, 18000, 19000, 19800), ("notice", 5020, 5021), ("highlight troop", 21000),
        ("highlight troop", 21031)]},
    {"on": "down", "troop": 21000, "needs": "town", "do": [("highlight troop", 21000, 0), ("say", SAVED, 10360)]},
    # the Dainargate Commander down (10:43.5): "Please go to His Majesty now!", the mark toward the palace (10:46.5)
    {"on": "down", "troop": 21031, "needs": "town", "id": "commander down", "do": [
        ("highlight troop", 21031, 0), ("say", SAVED2, 10380), ("highlight", STAIRS), ("point", STAIRS)]},
    # the palace stairs (10:54): the yard's soldiers and their foes in, Celes and the elf (3_Azilia_CELLES, 44 s)
    {"on": "bound", "bound": STAIRS, "needs": "commander down", "id": "celes", "do": [
        ("highlight", STAIRS, 0), ("wake", 18100, 28100, 19850), ("cutscene", 3, 44)]},
    # the yard (11:44): the tyrant and its primitives at the hero
    {"on": "bound", "bound": YARD, "needs": "celes", "id": "yard", "do": [("wake", 20500), ("march", 20500, YARD)]},
    # the tyrant down: the wounded infantryman in, the green line to the yard's end (12:24)
    {"on": "down", "troop": TYRANT, "needs": "yard", "id": "tyrant down", "do": [
        ("wake", 19870), ("highlight", END), ("point", END)]},
    # "His Majesty... Up there..." (12:36.5), the king's end (4_Azilia_destroy, 94 s), the meteor storm
    # (5_Azilia_destroy, 47 s), then the room is won: no window, the camp (game.end_without_window)
    {"on": "bound", "bound": END, "needs": "tyrant down", "id": "king", "do": [
        ("highlight", END, 0), ("say", WOUNDED, 10330), ("cutscene", 4, 94)]},
    {"on": "after", "step": "king", "s": 0, "do": [("cutscene", 5, 47), ("win",)]},
    # "you will just get Full Healed by Azillian Knights" (the walkthrough): healed when low (the speaker is ours)
    {"on": "hp", "troop": "hero", "below": 15, "repeat": True, "do": [("say", JAGER, 10400), ("heal",)]},
]

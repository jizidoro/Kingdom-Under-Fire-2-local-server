"""Fort Valley Castle 10306 (1_NewHamptonRamparts, [Lv 10] main quest 1010202, the Iron Armour Scorpion 1010203, Hard
9900228), the director's table. The original's script, with its storyboard and our marks:
planning/scripts/missions/10306.md (`py tools/mission_scripts.py 10306`); the whole reading:
planning/agents/reports/2026-11-05_fortvalley.md.

Sources, and how each row below says which it is:
- [N m:ss] / [H m:ss]: the tape, read frame by frame 2026-11-05. Playthrough part 5 (youtu.be/m-CmO76YaoA) is the NORMAL
  run: 3:20 to the result 15:56, Clear Time 743 s, grade B. Part 6 (youtu.be/WdCYx7-6sHA) is the HARD run: the entry
  window's toggle 7:05, 7:26 to the result 18:14, grade D. "to 33:40" is a world-map read, part 14 a mission list.
- [zone]: the map's bounds, forces, aliases and props (`py tools/recon/mission_sheet.py 10306`), and the map's text
  (1000-1032, 2000-2011, the notices 10110-10200).
- [guide]: walkthrough_guide.txt L401-418.
- [I]: ours: the original's trigger cannot be seen, this is the closest one.

The map has no cutscene list (no 1_NewHamptonRamparts.csset): the original's "Skip Video" scenes (3:25 the road, 8:30 the
wall, 9:26 the army, 10:02 the battlements, 10:36 the gate, 15:34 the flyover) were script-driven camera work and are
not played here; their lines are, as Flamegrass's.

The zone's names give the script's shape. 무적해제1-3 ("invincibility off") are the three fights the hero walks into;
예거 대사치기 ("Jager's lines") the bound of Jager's chain; 포병1-4-1차이동 / 포병1,2-2차이동 / 포병3,4-2차이동 the mortars' row and
the two battlements; 습격부대1/2목적지 the raiders' goals through the walls; 쇼크웨이브 the gate, 스콜피온이동위치 the Scorpion's stand,
오크 부대이동 the army's way in. The props: two fence gates (type 29), two walls (48), the castle gate (147), and five
transparent walls with collision the script took away (67 / 68: 20011 / 20012 / 20014 at the feet of the stairs,
20013 behind the right wall, 20015 just ahead of the start). Force 10502 유저부여용 is one mortar per player of a
four-player party: 리얼포병1 10308 is the solo player's; the others stand beside it and go up as the AI's.

Normal and Hard differ on the tape: Ukuron (F20110) at the second gate and the right wall with its raiders (F20700) are
Hard's alone (part 5 has no Ogre there; its log at 8:50 reads 2003, 1007, 1009 with no 1008), and 1032 too. The zone
marks neither force for Hard, so the steps do ("difficulty"). Normal never wakes them; WIN = "table" keeps the room
from waiting for them. Hell is not offered here (spottable Mission_Diffi_3 '-'), its forces stay out.

Not on either tape, so not played: 1014, 1019, 1021, 1022, 1024-1026, 1029, 1030, 2001, 2007, 3000, 10110-10160, 10180-10200,
20000-20110 (no-speaker copies; 20020 / 20060 reads are look-alikes). Ochanku's 3000 and bound 오찬쿠도망이벤트 belong to no
beat we can see. The failure line (640 "Let Hero and all ally Troops die") stays display only (Q2, no defeat yet)."""

JAGER, SANCHEZ = 10200, 10000    # 예거부대 (leader 106010), 산체스부대 (leader 106040)
INFANTRY = 10001                 # 인보 1차교전-2: "Human Infantry" on the tape (F10000: it cannot fall, so it can always speak)
ELF = 10102                      # 엘궁 2차교전-1, "Elf Archer Unit"
ORC = 20001                      # 오크 1차교전-2, "Orc Infantry Unit"
DARK_ARCHER = 20106              # F20100's 106080, "Dark Elf Archer Unit"
UKURON = 20105                   # F20110 (106100)
RAIDER, RAIDER_2 = 20600, 20700  # 습격부대1오크1, 습격부대2오크2: "Orc Infantry Unit"
YARD_ORC = (20303, 20504, 20301)  # F20300's orcs ("다크 4차교전1" is table 106050, an orc; the aliases are crossed)
COMMANDER = 30006                # F30000, led by 106030: "Orc Commander"
MORTAR = 10308                   # 리얼포병1 (F10502): the player's
MORTARMAN = (10309, 10310, 10311)   # 리얼포병2-4: "Human Mortarman"
SCORPION = "대규모스콜2"             # 30000 (106160, "Lv.10 Scorpion" on the tag, frame 10:32): the gate's
SCORPION_ID = 30000
IRON_SCORPION = "대규모스콜1"        # 30103 (106030, the boss bar "Iron Armour Scorpion" 11,086 at 11:54): 1010203's
IRON_SCORPION_ID = 30103
LEFT_MARK, RIGHT_MARK = "포병1,2-2차이동", "포병3,4-2차이동"
PLACE_S = 60                     # [I] how long the player has before the other mortars go up (tape: 26 s and 24 s)
GATE_S = 150                     # [I] the last word: the gate breaks by now whatever else happened
LATE_S = 30                      # [I] with the Scorpion on its way (17.5 s): a walk the closed gate blocks must not hang
RIGHT_WALL_S = 10                # [H 11:30-11:46] 1008 after 1007's line
CONTACT_S = 28                   # [N 10:40-11:08] 1023 if no engage report comes: the report is melee only
REINFORCE_S = 32                 # [N 11:08-11:46, H 13:54-14:38] after 1023's line: 38 s and 44 s from it; Hard's
                                 # troops have more hp and the time is the same: a clock, not a count of the fallen
STRONG_S = 24                    # [N 11:46-12:16, H 14:38-15:04] after 1027's line

HARD = (1, 2)                    # Hell is not offered here, but a room entered on it must not hang between the two
HOLD = {20100, 20110, 20300, 20400, 20500, 20600, 20700, 30000, 30100, 10502}
LATE_ALLIES = {10501, 10502, 10503}     # the mortars come with 1009, not with their group; F10503 성벽포병 is the scene's
                                        # (106140, staging at the row's marks; the tape's row is four): never
HAND = (MORTAR,)                 # the generic plan handed 10308 and 10309 at the start; the tape's F3 comes at 8:41, one
HAND_LATER = {MORTAR}            # [I] on Hard too; the zone's F11600 하드전용 mortars stay out
HARMLESS = {10000, 10200}        # [guide] "Normal Attacks Deal 0 Dmg!" (their armies')
HOLD_PROPS = {10000, 10001, 20000, 20001, 20010, 20011, 20012, 20013, 20014}    # the story's: not the hero's approach
                                 # nor a force waking (the generic G6), 20015 alone stays the generic rule's
WIN = "table"

ALLIES = (10000, 10100, 10200, 10300, 10400, 10510)     # all but the mortars; every allied march below is ours [I]:
                                                        # the tape shows where they fight, not their orders


def _march(forces, bound):
    return [("march", f, bound) for f in forces]


UNTOUCHABLE = [("untouchable troop", u, 1) for u in (10000, 10001, 10200, 10203, 10209)]    # [guide] "Immune to dmg"
# 1009 [N 8:36, H 11:52]: the row's four at the 1차이동 marks (the minimap 9:18-10:00, the player's the leftmost), the
# HUD's F3 at 8:41; 포병5-8 at the stairs' feet come with them [I]
MORTARS = [("wake", 10501, 10502), ("hand", MORTAR), ("say", MORTARMAN, 1009)]
UP = [("march", "리얼포병2", LEFT_MARK), ("march", "리얼포병3", RIGHT_MARK), ("march", "리얼포병4", RIGHT_MARK)]
INSIDE = [("wake", 30000), ("march", 30000, "스콜피온이동위치"), ("say", JAGER, 1020), ("say", INFANTRY, 1010),
          ("say", COMMANDER, 2002), ("say", JAGER, 1011), ("notice", 10121, 10120), ("open", 20011), ("open", 20012),
          ("open", 20014), ("highlight", LEFT_MARK), ("highlight", RIGHT_MARK)]
# the mortars placed: the marks down, the others up (the minimap: at 10:00 still in their row, at 10:32 on the walls, one
# left, two right) [N 10:02-10:14 the scene], "Our mortars are ready." (1017 [H 13:30]; [N] the log at 10:32) and 1031
# with the notice [N 10:18, H 13:32]; the Scorpion leaves its stand for the gate [I, but measured: from 스콜피온이동위치 to
# 쇼크웨이브's edge is 4,539 units, at its MAX_MOVE_SPEED 260 17.5 s: the tape's 18 s from 1031 to the gate, against 70 s
# and 40 s from the army's coming; the walk from its start to the stand, 30 s, ends before the mortars do (9:54)]
PLACED = [*UP, ("march", SCORPION, "쇼크웨이브"), ("say", MORTARMAN, 1017), ("highlight", LEFT_MARK, 0),
          ("highlight", RIGHT_MARK, 0), ("say", JAGER, 1031), ("notice", 10171, 10170)]
# the gate [N 10:36-10:40, H 13:45]: "Drat, the castle gate has broken. / Everyone, go out and fight!" (1012): the allies
# go out over the bridge [N 10:54-11:03], the army comes in by its zone mark [zone]
GATE = [("open", 20010), ("say", JAGER, 1012), *_march(ALLIES, "스콜피온강제이동"), ("march", 30000, "오크 부대이동")]

STEPS = [
    # [N 3:20, H 7:26] Jager over the opening camera; the panel as the HUD comes back [N 3:32.5, frame]; the chain's
    # spacing is the same on both tapes [N 3:32 / 3:38 / 3:44, H 7:32 / 7:38 / 7:42]. 20015 stands 1,400 ahead of the
    # start: on the tape the hero runs on [I: the script took it away]
    {"on": "start", "id": "start", "do": [
        *UNTOUCHABLE, ("open", 20015), ("say", JAGER, 10), ("panel start",), ("say", INFANTRY, 1000), ("say", ORC, 2000),
        ("say", SANCHEZ, 1100)]},
    # the first fence gate [N: the last orcs ~4:30, through it 4:33]; the trigger ours [I]: the generic rule's guard,
    # F20000 beside it [zone]
    {"on": "down", "force": 20000, "id": "first", "do": [("open", 10000), ("march", SANCHEZ, "무적해제2")]},
    # through it, into 무적해제2 [zone; N 4:36, H 8:14, the one chain: 1001, 1002, 2011 six seconds apart on both]: the
    # second fight, F20100 with its mirror F10100 (the elf archers "come to support you" [guide])
    {"on": "bound", "bound": "무적해제2", "needs": "first", "id": "second", "do": [
        ("wake", 20100), ("say", INFANTRY, 1001), ("say", ELF, 1002), ("say", DARK_ARCHER, 2011)]},
    # Normal: the second gate with the fight's end [N: kill 20 at 7:27, the gate's posts 7:28]
    {"on": "down", "force": 20100, "needs": "second", "difficulty": 0, "id": "gate 2", "do": [
        ("open", 10001), ("march", 10000, "예거 대사치기"), ("march", 10100, "예거 대사치기")]},
    # Hard: Ukuron first [H 9:40 "Ogres!", 9:46 "I'll crush you all!"; his hurt line H 10:00, the hp ours [I]; his fall
    # 10:02 "The Ogre has fallen!"]; his place on the fall of F20100 ours [I] (the second fight stops 9:30). His row stands
    # past the shut gate; 오우거목적지, the map's own bound, is on the hero's side [H 9:48: at the hero, the gate shut], and
    # the straight walk is the one a shut gate does not stop (plain, his AI took him to the yard: live 2026-11-06 08:56)
    {"on": "down", "force": 20100, "needs": "second", "difficulty": HARD, "id": "ukuron", "do": [
        ("wake", 20110), ("march straight", 20110, "오우거목적지"), ("say", INFANTRY, 1003), ("say", UKURON, 2005)]},
    {"on": "hp", "troop": UKURON, "below": 30, "do": [("say", UKURON, 2006)]},
    {"on": "down", "force": 20110, "needs": "ukuron", "id": "gate 2", "do": [
        ("open", 10001), ("say", INFANTRY, 1013), ("march", 10000, "예거 대사치기"), ("march", 10100, "예거 대사치기")]},
    # 예거 대사치기 [zone], the chain 1004, 1005, 1006 [N 7:28 / 7:34 / 7:38, H 10:14 / 10:20 / 10:24: the same spacing, and
    # 12 s after Hard's gate, 1 s after Normal's: the hero's arrival, not the gate's]; the yard's three forces with
    # their mirrors [the minimap's reds from 7:36; which moment of the walk ours [I]]
    {"on": "bound", "bound": "예거 대사치기", "needs": "gate 2", "id": "jager", "do": [
        ("wake", 20300, 20400, 20500), ("say", INFANTRY, 1004), ("say", JAGER, 1005), ("say", JAGER, 1006)]},
    {"on": "after", "step": "jager", "difficulty": HARD, "do": [("say", YARD_ORC, 2008)]},      # [H 10:32]
    # the left wall [N: the yard's Ogre falls 8:20, the fight to 8:28, 2003 and the wall 8:28-8:30; H 11:24]: on the fall of
    # the yard's first force [I: F20400 / F20500 fight on after it, the minimap's reds 8:43-9:05]. "Everyone, block the
    # left castle wall!": the raiders to their mark [zone], the allies to meet them. 1007 [N 8:32, H 11:30]
    {"on": "down", "force": 20300, "needs": "jager", "id": "left wall", "do": [
        ("wake", 20600), ("open", 20000), ("march", 20600, "습격부대1목적지"), *_march(ALLIES[:4], "습격부대1목적지"),
        ("say", RAIDER, 2003), ("say", JAGER, 1007)]},
    {"on": "after", "step": "left wall", "difficulty": 0, "id": "mortars", "do": MORTARS},
    # Hard: the right wall too [H 11:46 1008, 11:52 1009, 11:56 2004]; 20013 stands behind it
    {"on": "after", "step": "left wall", "s": RIGHT_WALL_S, "difficulty": HARD, "id": "mortars", "do": [
        ("wake", 20700), ("open", 20001), ("open", 20013), ("march", 20700, "습격부대2목적지"),
        ("march", 10400, "습격부대2목적지"), ("say", JAGER, 1008), *MORTARS, ("say", RAIDER_2, 2004)]},
    # "We've defeated all the enemies inside the castle!" (1020) [N 9:16, H 12:56]: every yard force down, in any order
    {"on": "down", "force": 20200, "id": "in 1"},
    {"on": "down", "force": 20400, "needs": "in 1", "id": "in 2"},
    {"on": "down", "force": 20500, "needs": "in 2", "id": "in 3"},
    {"on": "down", "force": 20600, "needs": "in 3", "id": "in 4"},
    # the army [N 9:24 / 9:26 / 9:36, H 13:02 / 13:06], over the scene of the torches; to the Scorpion's stand [zone];
    # 1011 with the notice [N 9:38-9:58, H 13:06-13:24] and the green pillars on the walls [N 9:39.5]; the transparent
    # walls at the stairs go [I: the only way up the tape's troop takes]
    {"on": "after", "step": "in 4", "difficulty": 0, "id": "inside", "do": INSIDE},
    {"on": "down", "force": 20700, "needs": "in 4", "difficulty": HARD, "id": "inside", "do": INSIDE},
    # the player's mortar on a battlement [N: the green line and the Manual Mode order 9:40-10:00, the scene 10:02;
    # H 13:30]. Only his troop moves until then
    {"on": "arrive", "force": 10502, "bound": LEFT_MARK, "needs": "inside", "unless": "placed", "id": "placed",
     "do": PLACED},
    {"on": "arrive", "force": 10502, "bound": RIGHT_MARK, "needs": "inside", "unless": "placed", "id": "placed",
     "do": PLACED},
    # [I] left below: the others go up by themselves, and their arrival is the same step
    {"on": "after", "step": "inside", "s": PLACE_S, "unless": "placed", "do": UP},
    # the Scorpion at the gate [zone: 쇼크웨이브; N 10:36, H 13:45]; [I] killed on the way (the player's mortars can) the
    # army comes all the same; [I] the last word, so that no lost report shuts the room
    {"on": "arrive", "force": 30000, "bound": "쇼크웨이브", "needs": "placed", "unless": "gate", "id": "gate", "do": GATE},
    {"on": "down", "troop": SCORPION_ID, "needs": "inside", "unless": "gate", "id": "gate", "do": GATE},
    {"on": "after", "step": "placed", "s": LATE_S, "unless": "gate", "id": "gate", "do": GATE},
    {"on": "after", "step": "inside", "s": GATE_S, "unless": "gate", "id": "gate", "do": GATE},
    # the army met [N 11:08, H 13:54]; [I] the engage report is melee only, so the tape's time from 1012 if none comes
    {"on": "engage", "force": 30000, "needs": "gate", "unless": "contact", "id": "contact",
     "do": [("say", JAGER, 1023)]},
    {"on": "after", "step": "gate", "s": CONTACT_S, "unless": "contact", "id": "contact",
     "do": [("say", JAGER, 1023)]},
    # the reinforcements with the Iron Scorpion [N 11:46, the bar 11:54; H 14:38]; he makes for his stand [zone] and
    # shocks from there ([guide] "Will Shockwave if your far away", "Acts like its in Defense mode")
    {"on": "after", "step": "contact", "s": REINFORCE_S, "id": "reinforcements", "do": [
        ("wake", 30100), ("march", 30100, "오크 부대이동"), ("march", IRON_SCORPION, "스콜피온이동위치"),
        ("say", JAGER, 1027)]},
    {"on": "after", "step": "reinforcements", "s": STRONG_S, "id": "strong", "do": [("say", INFANTRY, 1018)]},
    {"on": "after", "step": "strong", "difficulty": HARD, "do": [("say", JAGER, 1032)]},        # [H 15:08; N's log has none]
    # the Iron Scorpion down [N 15:11, 1028 15:14, "[Quest completed] Defeat Scorpion"; H 17:54 he was the last]
    {"on": "down", "troop": IRON_SCORPION_ID, "do": [("say", JAGER, 1028)]},
    # the win: the last of both armies [N: the reds gone 15:22 with 1015; no clock]
    {"on": "down", "force": 30000, "needs": "gate", "id": "army down"},
    {"on": "down", "force": 30100, "needs": "army down", "id": "all down", "do": [("win",)]},
    # [N 15:22 1015 with "(Complete)" on the panel, 15:30 1016 over the victory pose; H 17:54 / 17:58]
    {"on": "won", "do": [("say", JAGER, 1015), ("done", 620), ("say", JAGER, 1016)]},
]

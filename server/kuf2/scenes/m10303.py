"""Flamegrass Valley 10303 (1_FlamegrassValley zone1, [Lv 10] side mission, quest 1110501), the director's table.
The original's script, from the playlist, with its storyboard and our marks: planning/scripts/missions/10303.md
(`py tools/mission_scripts.py 10303`).

Sources: the map's missiontext (21000-21613, the panel 30000-30300; `py tools/recon/mission_sheet.py 10303`), the
zone's bounds, forces and props, the walkthrough (walkthrough_guide.txt L369-395: engage the scorpion, pick an Elf
Wizard, Ice left / Fire right, the Elf and Human commanders' armies, the ambush in the grass, "after 1st hit, NPC
allies will engage", pursue the Ogres "on the tow ... you will have 4 mins", the mud, kill the Ogres before they leave,
the boss; victory "Save Villagers & Defeat the Boss"), and the tape, read frame by frame (2026-10-24): playthrough part
4 (youtu.be/_0FD8aKDxto), the mission from the loading screen's end at 34:32 to "Mission Succeeded" at 44:51 (the
window's Clear Time 611 s). Before 34:32 the tape is in Accolade and on the world map: the script's 30202 / 21010 /
30000 reads at 30:30-31:54 are the quest tracker ("Rescuing Flamegrass Villagers", "Clear [Lv 10] Flamegrass Valley")
and an inventory read; the line at 34:35 is 21011 ("... We're a militia organised to rescue the prisoners.", the
same first line as 21010). The map has no cutscene list (no 1_FlamegrassValley.csset in the packages): the original's
two short scenes (the camera on the army 39:15-39:20, the ending 44:43-44:50 "Skip Video") were script-driven and are
not played here; their lines are.

Speakers, by the help box's name and face on the tape: Human Infantry is the militia's runner 31114 (본대알리미, "the
main force's messenger"), who meets the hero at the start and runs with him to the end; Elf Commander the envoys'
31113 (its NP leader 103030); Human Commander the militia's commander 13001 (leader 103020); Orc Commander a troop
led by 103010 (the scouts' 23004, the main force's 24203, the convoy's 24305); Orc Infantry Unit a troop without a
leader; Elf Wizard the wizard troop the player picked.

The zone's aliases and bounds carry the script's phase numbers and its places, which the steps follow (ours: which
place starts which beat, read from their names and the tape's timing):
- (0)/(1)/(2) the valley's mouth: the runner, the direction mark (0)시작방향지시 and its off switch (1)방향끄기, the
  orcs and the scorpion (F22000 / F22001 / F22100) around (2)시작, their flight to (2)오크도망, the wizards' places
  (2)법사냉기선택 / (2)법사화염선택 ("wizard ice / fire select") with the envoys' arrival marks.
- (3) the scouts (F23000, inactive in the zone) and the militia (F13000) at (3)멈추시오 ("Halt!").
- (4) the ambush: the meeting (4)본대만나기강조 / (4)본대만나기, the ambush marks (4)유저매복위치 (the hero), (4)유저부대1,
  (4)법사부대, (4)인간보병1/2, (4)박격포병2-0/2-1 (named as the mortars' aliases), the far side (4)건너편*. The orc main
  force (F24100 / F24200 / F24300 and the wagons F31100) is parked in the zone's south arm (40-43k, 31-37k), 25 000
  from anything of its story, like Grey Rock's parked cast (game.mission_staging); its aliases "(4)r-c..." name the
  column marks (7)본대위치r-c one for one (1-1 ... 3-5, the wagons (7)본대포로위치4-1): the script set it there.
- (5) the convoy F25000 (도망 "fleeing": its commander, left / right escorts, the three wagon Ogres 도망포로1-3, front
  and rear) in the pocket north of the valley behind the red curtain 10065 (opened by the convoy's fall in our generic
  rule, held here: HOLD_PROPS), and its places: (13)전망포로* and (13)전망2포로* (one mark per role, seen from the
  lookouts (13)전망1 / (10)전망2 in the shortcut), (13)마지막포로* where the hero meets it, (13)실패1_포로부대* at the guard
  post (the failure). The militia's chase marks (13)전망아군 / 전망2아군 / 아군.
- (10)/(13) the shortcut: the barricade (props 10002 / 10003, type 45, HP 50) with the transparent walls 10063 /
  10064 behind them, the mud marks (10)진흙강조1/2, the lookouts, the arrival checks (10)유저도착체크2 /
  (13)2번스킬쓰세요; the guard post's support force F25100 with Ochankin 24313 (Boss) behind the red curtain 10054.

The win: Ochankin down once the three wagon Ogres are (the walkthrough's "Save Villagers & Defeat the Boss"; the tape:
the wagons stopped 42:14, his bar 1 % at 44:42, black, "Mission Succeeded" 44:51 with "Rescue Flamegrass Villagers
(Complete)"). The parked and staging troops, the wolves and the treasure goblin do not decide it: WIN = "table".
The failure lines (30201, 30202, the clock 30300) stay display only (Q2, no defeat yet)."""
from ..director import KEY_ACTION

GUIDE = 31114                    # (0)본대알리미, Human Infantry
ELF = 31113                      # (0)영웅지원병엘프신관, the Elf Commander (leader 103030)
ICE, FIRE = 10201, 10204         # (0)영웅지원병냉기 / 화염: the wizard troops (103250 Ice, 103260 Fire)
WIZARD = (ICE, FIRE)             # a speaker: the one the player picked (the other has left)
COMMANDER = 13001                # (3)인간보병, the Human Commander (leader 103020)
ORC, ORC_2 = 22003, 22002        # (2)오크보병3 / 2 (F22000), Orc Infantry Unit
SCORPION = 22004                 # (2)스콜피온 (F22100)
SCOUT_LEADER = 23004             # (3)오크정찰대4 (F23000), led by 103010
MAIN = (24100, 24200, 24300, 31100)     # the orc main force and its wagons, the (4) aliases
MAIN_LEADER = 24203              # (4)2-3오크보병 (F24200), led by 103010
CONVOY, CONVOY_LEADER = 25000, 24305    # (5)도망지휘관, led by 103010
MILITIA = 13000
SUPPORT = 25100                  # (13)지원병력..., Ochankin's force at the guard post
BOSS = 24313                     # (13)보스, Ochankin (103290, Boss)
WAGONS = (31106, 31104, 31107)   # (5)도망포로1-3: the wagon-driving Ogres (103190, 0.15 hp, half speed)
BARRICADES = (10002, 10003)      # type 45 into the shortcut, with the transparent walls 10063 / 10064 behind them
CLOCK_S, CLOCK = 240, 30300      # "Arrive later than the enemy" 00:04:00 (the tape 39:46, frames)

HOLD = {23000, 10000}            # the scouts (and the militia joined to them, game.mission_plan G4) come at (3)멈추시오;
                                 # the envoys at the scorpion's fall (the tape 35:09): at their marks from the start the
                                 # client's AI casts on the scorpion, 6 000 away, 1 s in (live 2026-11-06). Force 10000's
                                 # runner comes with the start step
HOLD_PROPS = {10065, 10068}      # the pocket's red curtain and its north wall: only the story opens them (the hero's
                                 # approach would, 2 500 from the scouts' fight)
HAND_LATER = {ICE, FIRE}         # the wizard the player picks with F
ESCORT = {"(0)본대알리미"}        # the runner goes with the hero to each place (the tape: beside him 34:40, 36:54,
                                 # in the shortcut 39:56-40:38)
WIN = "table"

SPREAD = ((0, 0), (450, 0), (-450, 0), (0, 450), (0, -450), (450, 450), (-450, -450), (450, -450))


def _convoy_to(view):
    """The convoy onto one set of its marks: (13)<view>포로1-3 the wagons, 왼쪽1-3 / 오른쪽1-3 the escorts, 부대앞 / 부대뒤
    the front and rear; its commander to 주술사 where the set has one, else beside the front (ours)."""
    slots = {31106: "1", 31104: "2", 31107: "3", 31109: "왼쪽1", 31105: "왼쪽2", 31111: "왼쪽3", 24306: "오른쪽1",
             31108: "오른쪽2", 31112: "오른쪽3", 31134: "부대앞", 31132: "부대뒤"}
    out = [("move", uid, f"(13){view}포로{slot}") for uid, slot in slots.items()]
    if view == "마지막":
        return out + [("move", CONVOY_LEADER, "(13)마지막포로주술사")]
    return out + [("move", CONVOY_LEADER, f"(13){view}포로부대앞", (450, 0))]


def _militia_to(bound):
    """The militia's eight troops spread over one mark (the chase's (13)전망아군 / 전망2아군 / 아군)."""
    return [("move", uid, bound, d) for uid, d in zip((13001, 31129, 31130, 31131, 31115, 31116, 31117, 31118), SPREAD)]


# the main force into its column, alias "(4)r-c..." onto (7)본대위치r-c, the wagons onto (7)본대포로위치4-1
COLUMN = [("move", uid, f"(7)본대위치{rc}") for uid, rc in (
    (24101, "1-1"), (24104, "1-2"), (24102, "1-3"), (24308, "1-4"), (24103, "1-5"), (24201, "2-1"), (24202, "2-2"),
    (24203, "2-3"), (24301, "3-1"), (24106, "3-2"), (24303, "3-3"), (24304, "3-4"), (24302, "3-5"))] + [
    ("move", uid, "(7)본대포로위치4-1", d) for uid, d in ((31102, (0, 0)), (31101, (450, 0)), (31103, (-450, 0)))]
# the ambush marks (the mortars' by their aliases; the infantry and the far side ours)
AMBUSH = [("move", "hero", "(4)유저매복위치"), ("move deck", 1, "(4)유저부대1"), ("move deck", 2, "(4)유저부대1", (450, 0)),
          ("move deck", 3, "(4)유저부대1", (-450, 0)), ("move", ICE, "(4)법사부대"), ("move", FIRE, "(4)법사부대"),
          ("move", GUIDE, "(4)유저매복위치", (350, -350)), ("move", 13001, "(4)인간보병1"), ("move", 31129, "(4)인간보병2"),
          ("move", 31130, "(4)건너편인간보병1"), ("move", 31131, "(4)건너편인간보병2"), ("move", 31115, "(4)박격포병2-0"),
          ("move", 31116, "(4)박격포병2-1"), ("move", 31117, "(4)건너편박격포병1"), ("move", 31118, "(4)건너편박격포병2")]
# the hero meets the convoy's front (the tape 41:07-41:10): the clock stops (00:00:00, gone at 41:08), the wizard's
# "Once the wagons arrive there, it'll be difficult to rescue the villagers" (21410, 41:09), the convoy's commander's
# "Kweeek! Enemies ahead! Let the prisoners detour!" (21420, 41:10); the convoy onto its last marks ahead of him, the
# militia behind it, the pocket's north wall opened (nothing waits behind it now)
INTERCEPT = [("clock off", CLOCK), *_convoy_to("마지막"), *_militia_to("(13)아군"), ("open", 10068),
             ("say", WIZARD, 21410), ("say", CONVOY_LEADER, 21420)]

STEPS = [
    # the start (loading screen gone 34:32): the runner's "Sorrowh of the Bersia Mercenaries? We're a militia organised
    # to rescue the prisoners." (21011, 34:35, over the opening camera: no HUD), the HUD back with the whole panel
    # (34:37.9, build/order-c's frames: "panel start" after the opening's line) and "There are many Orcs around here.
    # Please be careful." (21013, the same frame to 34:42); a green pillar ahead 34:42-34:46 (the direction mark
    # (0)시작방향지시, its off switch (1)방향끄기 around it)
    {"on": "start", "id": "start", "do": [
        ("spawn", GUIDE), ("say", GUIDE, 21011), ("panel start",), ("say", GUIDE, 21013), ("highlight", "(0)시작방향지시")]},
    {"on": "bound", "bound": "(1)방향끄기", "do": [("highlight", "(0)시작방향지시", 0)]},
    # the orcs: "*Sniff, Sniff* Come on, look around!" (21030, 34:50) and "Who's there?!" (21040, 34:52-34:56), as the
    # hero comes up the mouth into (2)시작 (4 s after the pillar, at his speed its edge)
    {"on": "bound", "bound": "(2)시작", "id": "orcs", "do": [("say", ORC, 21030), ("say", ORC, 21040)]},
    # the scorpion's fall (35:04): "Uh-oh, the Scorpions are dead! They're strong. Run!" (21041), the orcs run for
    # (2)오크도망, towards the envoys, whose commander comes: "What are these Orcs doing in a place like this? They're
    # running away! Set a blizzard on them!" (21050, 35:09; their blizzard on the orcs 35:12-35:16); the envoys and
    # the runner talk (21051-21055, 35:15-35:34) while the wizards come to their marks
    {"on": "down", "troop": SCORPION, "id": "scorpion", "do": [
        ("spawn", ELF, ICE, FIRE), ("say", ORC_2, 21041), ("march", 22000, "(2)오크도망"), ("march", 22001, "(2)오크도망"), ("say", ELF, 21050),
        ("march", "(0)영웅지원병엘프신관", "(2)마법사선택_나이틀린"), ("march", "(0)영웅지원병냉기", "(2)법사냉기도착"),
        ("march", "(0)영웅지원병화염", "(2)법사화염도착"), ("say", ELF, 21051), ("say", GUIDE, 21052), ("say", ELF, 21053),
        ("say", GUIDE, 21054), ("say", ELF, 21055)]},
    # the choice (35:36): "Select either the Ice or Fire Troop. / Press [F] to make your selection." (21063 / 21064,
    # the banner at the top: the red seal centred above its band, 35:36-35:44; NoticeTable 6 MISSION_EVENT_OPEN_MID)
    # with a green pillar and glow at each wizard
    {"on": "after", "step": "scorpion", "id": "choose", "do": [
        ("banner", 21063, 21064), ("highlight", "(2)법사냉기선택"), ("highlight", "(2)법사화염선택")]},
    # at a wizard the F prompt ("[F] Investigate", 35:42-35:43); F there picks it: "The Ice Wizard Troop will support
    # you, Sorrowh. Then, we'll head for Accolade now." (21080, 35:45; 21081 for Fire), the troop is the player's, the
    # envoys go. F pressed at the other wizard puts the prompt up again
    {"on": "bound", "bound": "(2)법사냉기선택", "needs": "choose", "unless": "fire", "id": "by ice"},
    {"on": "prompt", "keys": (KEY_ACTION,), "in": "(2)법사냉기선택", "needs": "by ice", "unless": "fire", "id": "ice",
     "do": [("highlight", "(2)법사냉기선택", 0), ("highlight", "(2)법사화염선택", 0), ("hand", ICE), ("say", ELF, 21080),
            ("leave", FIRE), ("leave", ELF)]},
    {"on": "bound", "bound": "(2)법사화염선택", "needs": "choose", "unless": "ice", "id": "by fire"},
    {"on": "prompt", "keys": (KEY_ACTION,), "in": "(2)법사화염선택", "needs": "by fire", "unless": "ice", "id": "fire",
     "do": [("highlight", "(2)법사냉기선택", 0), ("highlight", "(2)법사화염선택", 0), ("hand", FIRE), ("say", ELF, 21081),
            ("leave", ICE), ("leave", ELF)]},
    # north through the wall (the next green pillar 35:48-35:51, at (3)삼페이즈강조): the scouts. "Those who went
    # inside, where are they?! We're all going to die without them!" (21130, 35:52), "Enemies behind us! Kill 'em!"
    # (21113, 35:54), "Enemies! Kill 'em!" (21121, 35:56), all Orc Commander; the militia comes with them (joined to
    # their wave). The convoy leaves its pocket now (from here on the tape never sees it there: "Uh-oh, I don't see
    # any prisoners!", 39:18): onto its first lookout marks, far north on the valley's rim
    {"on": "bound", "bound": "(3)멈추시오", "id": "scouts", "do": [
        ("wake", 23000), *_convoy_to("전망"), ("say", SCOUT_LEADER, 21130), ("say", SCOUT_LEADER, 21113),
        ("say", SCOUT_LEADER, 21121)]},
    # the scouts down (58 s of fighting): "We're almost where our main forces are. Please follow me." (21140, 36:54),
    # the runner leading on to the meeting (the hero and soldiers running east 36:56-37:03)
    {"on": "down", "force": 23000, "needs": "scouts", "id": "scouts down", "do": [
        ("say", GUIDE, 21140), ("highlight", "(4)본대만나기강조"), ("march", "(0)본대알리미", "(4)본대만나기강조")]},
    # the meeting: "Finally, the Mercenaries are here. Thank you for coming." (21141, 37:03), then black (37:04-37:06,
    # the script's fade): the wider bound (4)본대만나기 starts it too
    {"on": "bound", "bound": "(4)본대만나기강조", "needs": "scouts down", "unless": "meet", "id": "meet", "do": [
        ("highlight", "(4)본대만나기강조", 0), ("say", COMMANDER, 21141), ("fade", False, 1, 0)]},
    {"on": "bound", "bound": "(4)본대만나기", "needs": "scouts down", "unless": "meet", "id": "meet", "do": [
        ("highlight", "(4)본대만나기강조", 0), ("say", COMMANDER, 21141), ("fade", False, 1, 0)]},
    # out of the black (37:07) the hero lies in the flamegrass at his ambush mark, his troops, the wizard and the
    # militia at theirs; the orc column comes down from the pocket (its marks (7)본대위치, the curtain open) towards
    # the trap's middle (4)본대만나기; "There are too many enemies. Don't get caught!" (21180, 37:07-37:16), "Wait
    # until all of them are here so that we can bombard them with magic attacks and charge at them." (21190, 37:18).
    # The 2 s are the tape's black
    {"on": "after", "step": "meet", "s": 2, "id": "ambush", "do": [
        *AMBUSH, *COLUMN, ("open", 10065), *[("march", f, "(4)본대만나기") for f in MAIN], ("fade", True, 1, 0),
        ("say", COMMANDER, 21180), ("say", COMMANDER, 21190)]},
    # the column in the trap (the tactical view 37:24-37:26, its red marks in the valley): "Now! Cast Blizzard on the
    # enemy troops!" (21203, 37:27) and the notice "Use the Wizard Troop to cast Blizzard on the enemy. / Select the
    # Wizard Troop, and then press @K_1 to use its skill." (21204 / 21207); Fire's: "Now! Shoot Meteor at the
    # Scorpions!" (21201 / 21202)
    {"on": "arrive", "force": MAIN, "bound": "(4)본대만나기", "needs": "ice", "id": "now ice", "do": [
        ("say", COMMANDER, 21203), ("notice", 21204, 21207)]},
    {"on": "arrive", "force": MAIN, "bound": "(4)본대만나기", "needs": "fire", "id": "now fire", "do": [
        ("say", COMMANDER, 21201), ("notice", 21202, 21207)]},
    # not cast yet: "Our ambush operation is going to fail. Come on, use Blizzard on the enemy troops!" (21206, 37:31,
    # right after 21203; 21205 Meteor's)
    {"on": "after", "step": "now ice", "s": 1, "unless": "blizzard", "do": [("say", COMMANDER, 21206)]},
    {"on": "after", "step": "now fire", "s": 1, "unless": "meteor", "do": [("say", COMMANDER, 21205)]},
    # the spell on the column (37:33): "We've been ambushed!" (21260, Orc Commander, 37:33-37:36), "The enemies are
    # confused! Wipe them out at once!" (37:39-37:43; the text of 11262 / 21261 / 21262: 21261 for Blizzard, 21262 for
    # Meteor, ours), the militia charges ("After 1st hit, NPC allies will engage", the walkthrough)
    {"on": "skill", "troop": ICE, "force": MAIN, "needs": "now ice", "id": "blizzard", "do": [
        ("say", MAIN_LEADER, 21260), ("say", COMMANDER, 21261), ("march", MILITIA, "(4)본대만나기")]},
    {"on": "skill", "troop": FIRE, "force": MAIN, "needs": "now fire", "id": "meteor", "do": [
        ("say", MAIN_LEADER, 21260), ("say", COMMANDER, 21262), ("march", MILITIA, "(4)본대만나기")]},
    # the main force down (98 s): "Uh-oh, I don't see any prisoners! They must have moved them someplace else." (21300,
    # 39:18), "Sorrowh, we'll follow the prisoners. Please take the shortcut to stop the enemies from the front!"
    # (21306, 39:22-39:54), the notice "Destroy the barricade and enter the shortcut. / You can destroy the barricade
    # with Hero attacks." (21317 / 21318, 39:26); the militia after the convoy (into the pocket)
    {"on": "down", "force": 24100, "needs": "ambush", "id": "main 1"},
    {"on": "down", "force": 24200, "needs": "main 1", "id": "main 2"},
    {"on": "down", "force": 24300, "needs": "main 2", "id": "main 3"},
    {"on": "down", "force": 31100, "needs": "main 3", "id": "main down", "do": [
        ("say", COMMANDER, 21300), ("say", COMMANDER, 21306), ("notice", 21317, 21318),
        ("march", MILITIA, "(13)추격재배치_아군0")]},
    # the barricade broken (39:45-39:46, frames): the shortcut opens (the walls behind it) and "Arrive later than the
    # enemy" shows under the failure conditions, 00:04:00, counting down (39:46, frames)
    {"on": "broken", "prop": BARRICADES, "needs": "main down", "id": "breach", "do": [
        ("open", 10063), ("open", 10064), ("clock", CLOCK, CLOCK, CLOCK_S)]},
    # the first lookout: "Sorrowh, look to the right! The enemies have ditched their pursuers and are moving quickly
    # now." (21310, 39:56), "Please note that you can't run in the mud." (21319, 40:02), the mud marked; the militia
    # behind the convoy on the rim
    {"on": "bound", "bound": "(13)전망1", "needs": "main down", "id": "view 1", "do": [
        *_militia_to("(13)전망아군"), ("say", GUIDE, 21310), ("say", GUIDE, 21319), ("highlight", "(10)진흙강조1"),
        ("highlight", "(10)진흙강조2")]},
    # the second lookout: the convoy further west, "Sorrowh! Hurry! The enemies have gone that far already!" (21311,
    # 40:30-40:38)
    {"on": "bound", "bound": "(10)전망2", "needs": "main down", "id": "view 2", "do": [
        ("highlight", "(10)진흙강조1", 0), ("highlight", "(10)진흙강조2", 0), *_convoy_to("전망2"),
        *_militia_to("(13)전망2아군"), ("say", GUIDE, 21311)]},
    # out of the shortcut: the convoy's front (41:07); either arrival check, or the hero's own fight with the convoy
    {"on": "bound", "bound": "(10)유저도착체크2", "needs": "main down", "unless": "intercept", "id": "intercept",
     "do": INTERCEPT},
    {"on": "bound", "bound": "(13)2번스킬쓰세요", "needs": "main down", "unless": "intercept", "id": "intercept",
     "do": INTERCEPT},
    {"on": "engage", "force": CONVOY, "by": ("hero",), "needs": "main down", "unless": "intercept", "id": "intercept",
     "do": INTERCEPT},
    # the fight with the convoy: "Our forces are struggling! Let's go kill the Humans! Kweehhkk!" (21422, Orc
    # Commander, 41:18): the guard post's force comes out (its curtain opened), the militia attacks the rear
    {"on": "engage", "force": CONVOY, "needs": "intercept", "id": "struggle", "do": [
        ("say", CONVOY_LEADER, 21422), ("open", 10054), ("march", SUPPORT, "(13)마지막포로부대앞"),
        ("march", MILITIA, "(13)마지막포로부대뒤")]},
    # a wagon Ogre hit (the hero's critical on one 41:33): the notice "Take care of the Ogres first. / The Ogres are
    # running away with the prisoners in tow." (21434 the title, 21433 its line, 41:34), the wagons run for the guard
    # post
    {"on": "hp", "troop": WAGONS, "below": 99, "needs": "intercept", "id": "ogres run", "do": [
        ("notice", 21434, 21433), ("march", "(5)도망포로1", "(0)포로막기실패"), ("march", "(5)도망포로2", "(0)포로막기실패"),
        ("march", "(5)도망포로3", "(0)포로막기실패")]},
    # the three down: "The wagons have stopped! Let's eliminate the enemy and rescue the prisoners!" (21424, 42:14)
    {"on": "down", "troop": 31106, "needs": "intercept", "id": "wagon 1"},
    {"on": "down", "troop": 31104, "needs": "wagon 1", "id": "wagon 2"},
    {"on": "down", "troop": 31107, "needs": "wagon 2", "id": "wagons", "do": [("say", COMMANDER, 21424)]},
    # Ochankin (his name on the tape 42:18-43:16, his bar 1 % at 44:42): the villagers are saved
    {"on": "down", "troop": BOSS, "needs": "wagons", "id": "boss", "do": [("win",)]},
    # the ending (the original's script-driven scene 44:46-44:50 behind "Skip Video": the militia charging): "You
    # heinous monsters! Release the villagers!" (21500, Human Commander, 44:48), "Rescue Flamegrass Villagers
    # (Complete)" on the panel with "Mission Succeeded" (44:51)
    {"on": "won", "do": [("done", 30101), ("say", COMMANDER, 21500)]},
]

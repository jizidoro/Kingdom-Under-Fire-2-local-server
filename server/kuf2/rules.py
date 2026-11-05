"""Mission rules the original's unshipped scripts ran, rebuilt from the client's data and the official notes (ROADMAP
Next 3; owner 2026-09-29 21:20: Q16 build the Unknown Corridor's rule, Q33 the Treasure Goblin Nest's; Q2 no defeat).

The clock. ActGuiAddTimeObjectiveToMissionSituation 0xc80a (team, group, text, seconds) adds a condition of type 3 to
the mission panel (0x140b37860 -> 0x140b5d5a0 -> 0x140775a80 -> 0x140775890); HUDQuestInfo prints its value once as
"%02d:%02d:%02d" (hours, minutes, seconds: 0x1407795fc -> _root.widget18.C2A_setMSTimerCondition). The same group and
text sent again update it in place (value +0xc / +0x10, dirty flag +0x15), so the server sends it each second. The
client's own countdown condition (type 2, 0x140775a50) has no script action, and ActGuiShowMissionTimer 0xc7ce is a
stub (MISSIONS-WIRING G10). Read from the code 2026-09-29; not seen live.

The Unknown Corridor (spottable Spot_Contents_Type PVE_DAILY, 10540-10546): the day's boss must fall within the 5:00
clock from the start (ours: when the room's troops come in, 3 s after loading), graded by the time left
(OFFICIAL-NOTES "Grade rules"); mission_reward keeps S / A / B rows only, so C and D pay nothing. After 5:00 the
original failed the mission (missiontext "Let Dimensional Exit disappear", "The Dimensional Exit disappears, along with
the Dimension Keeper"); with no defeat (Q2) the boss stays, and one killed late wins the room with nothing paid and no
day's clear (ours). No resurrection: the client refuses it itself (spottable
%Revival PVE_DAILY IMPOSIBLE, planning/requests/battle.md 0x50f4). Weakness x2 (the "Hunter" days): no data found.

The Treasure Goblin Nest 10237 (Patch Notes 2019-12-17, OFFICIAL-NOTES "Per-mission rules"): the 5:00 clock starts
when the entrance door opens; three real goblins carry a chest on their back (the zone's 18 box goblins 137020 stand
in six forces of three, all inactive: the script woke one force, which is ours to pick at random); they get a beacon
with 2:00 left; the mission always runs the full 5:00. The 373 bag goblins 137010 are the fakes (active, NP_Grade Extra:
no target). The setting is the entry's difficulty (missiontext: Normal Golden, Hard Vision, Hell Enchanter; the
mission_reward Category 916811 / 916911 / 917011). %Mission_Grade 10237 has S / A / B / C rates of 0.001 and MaxTime
1,800 s: a trial passed is S.

The Dimensional Test 10238 (PVE_WEEKLY; OFFICIAL-NOTES "Per-mission rules": 50 levels, at most 3 units, no hero, no
revival, a reward every 5 levels paid at the end, once a day, enemies every 20 s; DESIGNER-NOTES F3). Its zone holds no
enemy: the eleven level bosses stand off the map as templates (F21000) beside the ten stage-reward troops (F20000
보상5단계 .. 보상50단계, 191660-191750 -> 917105 .. 917150 "Dimensional Test Level N ..." at 100000, the certificates
917116 / 917134 at 10000 from 15 / 30). The rule: a level is one dimension storm (8 storm props on 8 bounds north of the
start), opened STORM_S after the last level fell (missiontext 2060), with the troops of its tier (nptrooptable 1-91
싱글웨이브_N단계: levels 10N-9 .. 10N) or the boss named for the level (5, 10 .. 50); the entry's difficulty is the level
it starts from (1 / 16 / 31: textui 58043-58045, Hard / Hell paying the certificates of 15 / 30). The fiftieth level won
wins the room; its end pays, once a game day, the stage chest of each fifth level passed and the card (917100 troop
coins). Not built: the hero kept out (no deck troops in battle yet: ROADMAP B1), "at most 3 units" (the client's entry
check reads Limit_Troop 3), the end when every unit is down (Q2: no defeat), the storm countdown's number (missiontext
2040 "... in %1% sec." needs ActGuiShowNoticeWindowToTargetWithVariable 0xc8f3, whose first two args are not read).
Revival: the client refuses it (%Revival PVE_WEEKLY IMPOSIBLE).

Subjugation (PVE_REPEAT 10327 Grey Wood, 20329 Field of Watchtower, 20327 Jackdaw Canyon, 20326 Old Citadel's
Watchtower; OFFICIAL-NOTES: troops only, 6 waves or survive 3:30, a treasure goblin, 3 runs a day; the footage part 6
20:14-24:00, WdCYx7-6sHA, a Grey Wood run's frames): the notice "A Troop mission." / "Heroes cannot be controlled.",
the 3:30 clock and the wave count in the panel, the goblin (the zone's NP_Grade Extra troop held at the start) at 2:30
left for GOBLIN_STAY, the 60 s and 30 s notices; all the waves down wins (the wave rule), and so does the clock run out
(the footage: at 00:00:00 "Eliminate the remaining thieves (Complete)", the window S). The grade is %Mission_Grade's
(the footage's 3:50 window reproduced), the card the grade's category (the stone tables: Region Visionstones of the
map's regions or a 1-star troop), 3 entries a day (group 110-140 below). Waits on the army (ROADMAP B1, build/army):
the troops-only rule itself (the player's deck troops in the room, the hero out of control); "a hero entering finishes
it" (the guide) is not in the data. The clock starts with the room (ours: the footage's started 8-26 s after the start
notice, as the troops walked in; its trigger is not read).

The day limits (planning/client/world_travel.md gap 3): spottable %DayLimit groups (DayLimit_GroupID_<difficulty + 1>)
count a character's entries (Mission_Enter) or clears (Mission_Clear) per day; 0x10b3 gives the client the counts, whose
own entry check refuses a spent group (0x140d67d70, result 0x1c25), and so does the server's 0x3f48."""
import datetime
import functools
import math
import random
import re
import time

from . import net, tables
from .net import log
from .packet import Writer

ACT_SITUATION_TIME = 0xc80a      # ActGuiAddTimeObjectiveToMissionSituation (team, group, text, seconds): the clock line
# ActGuiSetHighlightTroop 0xc7ba (0x140b36aa0 -> 0x140b2e8d0): (troop, seconds as a float, on 0 / 1, leader 0 / 1); on
# -> 0x140b5cb30 -> HUD +0x88 0x140c569f0: a highlight entry {troop, seconds, forever when seconds <= 0, leader} with
# its minimap mark (0x140c78f30). Read 2026-09-29; not seen live.
ACT_HIGHLIGHT_TROOP = 0xc7ba
CLOCK_STEP = 0.02                # ours: a tick lands this long after the second it shows has turned

CORRIDOR = "PVE_DAILY"
CORRIDOR_S = 300                 # "the 5:00 clock" (OFFICIAL-NOTES Grade rules; the guide G-2011029967)
# (seconds left at least, grade index): S 2:30 (x3 rewards), A 1:15 (x2), B 1:00 (x1), C 0:30 and D 0:15 (nothing);
# under 0:15 left is D too (ours: the table stops there). The owner's decision Q16 names these numbers; the client's
# %Mission_Grade rows for 10540-10546 (S rate 0.48, A 0.319, B 0, MaxTime 310) read otherwise when their time points
# fall linearly (S up to 161 s, A up to 211 s, else B): how those points combine is not read.
CORRIDOR_GRADES = ((150, 0), (75, 1), (60, 2), (30, 3))
LATE = 4                         # the grade of a target that fell after the clock: D, nothing paid, no day's clear
# The corridor's texts, from the panel title "Unknown Corridor" at base + 100 (10540 / 10544: 10000, 10546: 50000, the
# others 20000): base + 120 its success line, + 200 "Dimensional Exit disappears in", + 210 "Timer", + 1000 / 1010 the
# start notice, + 3100 / 3110 "Defeated the Dimension Keeper before the Dimensional Exit disappears."
CORRIDOR_TITLE, CORRIDOR_WIN_LINE, CORRIDOR_TIME_TEXT, CORRIDOR_TIMER = 100, 120, 200, 210
CORRIDOR_START_NOTICE, CORRIDOR_WIN_NOTICE = (1000, 1010), (3100, 3110)
VARIANT = 10000000               # game.difficulty_troop: Hard 20000000 + id, Hell 30000000 + id

NEST = 10237
NEST_S = 300                     # "5-min limit starts when the entrance door opens"
BEACON_LEFT = 120                # "with 2 min left the real ones get a beacon"
BOX_GOBLIN = 137020              # 황금고블린_상자: the goblin with the chest on its back (the bag one, 137010, is the fake)
NEST_DOOR = (661, 662)           # the entrance: 661 스위치_열림_마법결계문 (the magic barrier door, 10 s cast) and 662
                                 # 정사각형투명프랍 (a hero-only 7 s switch beside it); casting either opens the trial (ours)
SETTING_STEP = 10                # missiontext 1_goblindungeon: each text + 10 x the setting (0 Golden, 1 Vision,
                                 # 2 Enchanter)
NEST_TITLE = 10000               # "Golden Goblin Nest" / "Vision ..." / "Enchanter ..."
NEST_TIME_TEXT, NEST_TIMER = 10100, 10110          # "Time until restoration:", "Timer"
NEST_DOOR_GROUP, NEST_DOOR_LINE = 20000, 20010     # "Goblin Nest Entrance": "Open the door and pass the ... Trial ..."
NEST_TRIAL_GROUP, NEST_TRIAL_LINE = 21000, 21010   # "Goblin Trial": "Defeat the true ... Goblin before the entrance"
NEST_DONE = (23000, 23010)                         # "Goblin Trial Complete", "The ... Goblin Trial has been completed."

DIMENSION = 10238
DIMENSION_TOP = 50               # "50 levels"
DIMENSION_START = (1, 16, 31)    # the entry's difficulty: textui 58043 "Level 1", 58044 "Level 16", 58045 "Level 31"
STORM_S = 20                     # "enemies every 20 s" (the guide G-2001618448), read as the wait after a level falls
                                 # (missiontext 2060 "The next dimension storm will open when there are no more
                                 # enemies remaining."): the reading is ours
DIMENSION_CODE = "1-91_"         # nptrooptable's single-wave rows (싱글웨이브, DESIGNER-NOTES §2: 75)
TIER = re.compile(r"싱글웨이브_(\d+)단계_")        # 1단계 .. 5단계: levels 1-10 .. 41-50
BOSS_AT = re.compile(r"\((\d+)단계\)")            # the boss named for its level: 리더(5단계) .. 스웜프맘모스(50단계)
STAGE = re.compile(r"^보상(\d+)단계$")             # the zone's stage-reward troops (F20000)
STORM_TYPE = 221                 # smartproptable 221 스위치_사라짐_소환폭풍 (the summoning storm; trigger-only, hidden)
DIMENSION_FORCE = 21000          # the zone's force of the level bosses (단계5보스 .. 단계50보스): the levels' template
DIMENSION_UID = 0xD000           # ours: the levels' troop uids, above the zone's (10000-10020), below the quest troops'
SPREAD = 600                     # ours: a level's troops side by side at its storm
DIM_TITLE, DIM_DETAILS, DIM_PROGRESS = 1000, (1010, 1020), (1030, 1040)    # "Dimensional Test", "Mission Details" /
DIM_NOTICE, DIM_STARTING, DIM_TIP = 2000, 2020, 2060                       # "Push yourself to the limit", "Progress"
DIM_OPENED, DIM_SOON = 2050, 2070                  # "A dimension storm has opened.", "... is about to open."

SUBJUGATION = "PVE_REPEAT"
SUBJUGATION_S = 210              # "survive 3:30" (the guide); the footage: 60 s left at 22:54, 00:00:00 at 23:52
GOBLIN_AT = 60                   # the treasure goblin comes this long into the clock: the footage's "Use your Troop to
                                 # collect Treasure Chests." at 00:02:30 (part 6 21:22; part 12 about 0:52 in; its
                                 # drop is the chest). The guide says "after 2 min"; the goblin itself is not seen
GOBLIN_STAY = 30                 # "for >= 30 s" (the guide): ours, it runs off then (the zone's 보물고블린_사라짐 bound)
TOWER_WORD = "감시탑"             # Field of Watchtower's six orc watchtowers (오크감시탑1 .. 3-3)
# spot: (clock group, text), (count group, text, kind), the start notice, the 60 s and 30 s notices, the goblin's
# notice; missiontext of each map. The count: "current" the wave on (the footage's "Wave Progression 1/6"),
# "remaining" the waves left, "towers" the watchtowers down.
SUBJUGATIONS = {
    10327: ((670, 680), (690, 700, "current"), (710, 711), (730, 731), (732,), (720, 721)),
    20326: ((660, 661), (670, 671, "current"), (700, 701), (710, 711), (720,), None),
    20327: ((730, 731), (740, 741, "remaining"), (800, 810), (820, 840), (830,), None),
    20329: ((730, 731), (740, 741, "towers"), (800, 810), (820, 840), (830,), None),
}

# Grey Hampton 10315 (1_KedingtonWall zone 2): "Destroy Dimension Storm Mana Supply Device", then "Survive until the
# Dimension Storm is closed". The tape part 14 (Us8IGwvuo5M): the hero breaks the relic's "Testing Device" about 5:20
# (f_00159: its bar at 20 %, in the storm's light), a cutscene 5:22-5:36, then from 5:38 "Dimension storm fully closed
# in" 00:02:30 with the notice 850 / 860 and the line 721; 00:00:00 at 8:14, 721 (Complete), "Mission Succeeded" 8:40
# (Clear Time 7:57). The device is the smartproptable 12 prop at the storm (219); the four others of that type stand at
# the room's corners. The clock starts at the break (the tape's starts after the 16 s cutscene we do not play).
# The panel shows a mission's clock or count as a group of its own, its label the heading and the value under it
# (the tape's Grey Hampton f_00176 "Dimension storm fully closed in / 00:02:18", Kedington f_00400, Essex f_00845
# "Totems Destroyed / 2/7", "Forest fully contaminated in / 00:03:48"): 0xc80a / 0xc800 with that label as the group
# (and as the text, which no frame shows).
ACT_SITUATION_REMOVE_GROUP = 0xc7ed   # ActGuiRemoveObjectiveGroupToMissionSituation (team, group): the group goes
# Outskirts of Essex Forest 10309 (the tape part 9, 24:20-32:10): "Totems Destroyed" n/7 from the start; the entrance
# ward's totem ([0-0]1토템, 26:40: 1030 "The ward has been lifted!") is followed by "Forest fully contaminated in" at
# 3:00 (26:55, after 1080 / 1040; ours: at that totem's fall); each of the seven other totems adds a minute (six jumps
# from 27:22 to 31:00, to 4:59; the guide's "30-60 s"); 7/7 at 31:00 (1350 "The ward has disappeared. Now, destroy the
# Chaos Wedge!"); the Wedge's fall wins (32:02, the clock frozen at 4:02), whoever else stands. At 0 the forest was
# contaminated, the original's defeat (650; Q2: nothing). The ward on the Wedge until the seventh totem is not built,
# so the Wedge's fall wins only once the seven are down; a Wedge felled before that leaves the win to the wave rule.
ESSEX = 10309
TOTEM, WEDGE = 109290, 109410    # 토템 (Totem of Corruption, EXP 0: no target), 혼돈의쐐기보스 (the Chaos Wedge, Boss)
TOTEM_ENTRANCE = "[0-0]"         # the alias of the entrance ward's totem: not one of the seven counted
CONTAMINATE_S, TOTEM_BONUS_S = 180, 60
ESSEX_COUNT, ESSEX_TIME = 660, 680
# Kedington Castle Wall 10320 (the tape part 12, 11:17-16:48; part 13 again): the notice 400 / 410 and "Operate Castle
# Gate Switchgear Lever within time limit" (650) at 00:05:00 (11:50; the first playable frame 11:31, ours: at the start),
# "Fail to open the castle gate within the time limit" (670) under the failure heading; the lever (230 스위치_열림_
# 케딩턴레버) pulled with 1:49 left (15:06); at 15:24 the 650 group and its clock are gone, no (Complete). At 0 the
# original failed (Q2: nothing). The gate's opening by the lever is the story's (not built here).
KEDINGTON = 10320
KED_LEVER_TYPE, KED_GATE_S, KED_CLOCK, KED_FAIL_LINE, KED_NOTICE = 230, 300, 650, 670, (400, 410)
FAIL_GROUP = 630                 # "Mission Failure Conditions" on both maps' panels

STORM = 10315
STORM_DEVICE_TYPE = 12          # smartproptable 12 "Testing Device" (TYPE_ATTACK, HP_AT 50, HC_AT 5)
STORM_PROP_TYPE = 219            # 스위치_사라짐_차원폭풍, the dimension storm (trigger-only)
STORM_CLOSE_S = 150              # "00:02:30" (the walkthrough's "3 minutes" is not the tape's)
STORM_GROUP, STORM_DEVICE_LINE, STORM_SURVIVE_LINE, STORM_TIME_TEXT = 710, 720, 721, 760
STORM_NOTICE = (850, 860)        # "A new item has been added to the Status window." / "Stay alive until ... closed."

# The Sunstruk Colosseum (2_SunstrokColosseum: 20302, 20319; hero only, Limit_Troop 0): opponents one round at a time,
# the next "15 sec." after a round is won (missiontext 60 / 61). The rounds are the troops' aliases (colosseum_rounds).
COLOSSEUM = (20302, 20319)
ROUND = re.compile(r"라운드(\d+)_|^보스_0(\d)")
ROUND_WAIT_S = 15                # 60 "Next match begins in 15 sec."
ROUND_SOON_S = 5                 # 61 "Next match begins in 5 sec."
NEXT_MATCH, NEXT_MATCH_SOON = 60, 61

C2S_DAY_LIMITS = 0x10b2          # at the first city entry of a session (0x140674690)
S2C_DAY_LIMITS = 0x10b3          # 0x140675ba0: u16 n, n x 13: +0 i32 DayLimit group, +4..+0xb unused, +0xc u8 used
S2C_DAY_LIMIT = 0x10b4           # 0x140675cf0 (Common): one such 13-byte entry, inserted or overwritten (shorter crashes)
DAY_ENTRY_PAD = 8
DAY_LIMIT_REFUSED = 0x1c25       # the 0x3f41 result of the client's own check: text 0xd061 = 53345 "You've reached the
                                 # max number of entry for today." (mission error map 0x140d680e0)
ENTER, CLEAR = "Mission_Enter", "Mission_Clear"
# The day starts at 07:00 UTC: spottable %SpotSchedule opens each Unknown Corridor from 07:00 of its day to 07:00 of
# the next (the client's gmtime, world.spot_schedule_packet), and the NA players' reset of the dailies, the Goblin
# Nest and the Corridor was "~11 pm PST" (OFFICIAL-NOTES "Daily and weekly limits": 07:00 UTC).
DAY_START_HOUR = 7


# --- targets ---

def corridor(spot):
    return (tables.by_id("spottable").get(str(spot)) or {}).get("Spot_Contents_Type") == CORRIDOR


@functools.cache
def day_bosses():
    """The Unknown Corridor's day bosses: the NP_Grade Boss troops of the PVE_DAILY spots' zones (troop 10000, alias
    보스: 190040 the bear, 190240 the lich, 190080 the earth spirit, 190110 the desert troll, 190270 the bandit boss,
    190190 the goblin slaughterer; 10545's four juggernauts 190150, aliases 노말보스 / 하드보스2 / 헬보스1 / 헬보스2, by
    difficulty). Every corridor troop has EXP 0, so the exp rule counted none (proof audit C)."""
    from . import zone
    out = set()
    for spot, row in tables.by_id("spottable").items():
        if row.get("Spot_Contents_Type") == CORRIDOR and zone.available(int(spot)):
            out |= {t["TroopTableID"] for t in zone.for_spot(int(spot))["NPCTroopInfoData"]
                    if (zone.np_troop(t["TroopTableID"]) or {}).get("NP_Grade") == "Boss"}
    return frozenset(out)


def target(t):
    """Whether a zone troop is a mission rule's win target whatever its exp or grade (game.hostile): a corridor's day
    boss (any difficulty variant), or a troop a rule spawned as one (the nest's real goblins)."""
    return bool(t.get("Target")) or t.get("TroopTableID", 0) % VARIANT in day_bosses()


# --- the clock ---

def start_clock(s, seconds, group, text):
    """A clock of `seconds` from now (time.monotonic) in the mission panel under group / text (None: no line)."""
    s.data["clock"] = {"t0": time.monotonic(), "limit": seconds, "group": group, "text": text, "shown": None}
    net.journal("rule", spot=s.data.get("spot"), ev="clock", secs=seconds)
    tick(s)


def time_left(s, now=None):
    """Seconds left on the room's clock (negative once it ran out; frozen once the room is won), or None."""
    c = s.data.get("clock")
    if c is None:
        return None
    at = c.get("stopped_at")
    if at is None:
        at = time.monotonic() if now is None else now
    return c["limit"] - (at - c["t0"])


def panel_time(s, group, text, seconds):
    """The clock line under group (shown first when not yet), set to `seconds`."""
    from . import game
    groups = s.data.setdefault("panel_groups", set())
    if group not in groups:
        groups.add(group)
        game.send_actions(s, [game.ACT_SITUATION_GROUP, game.ALL_TEAMS, group])
    game.send_actions(s, [ACT_SITUATION_TIME, game.ALL_TEAMS, group, text, seconds])


def tick(s):
    """The clock's second: the panel line when its value changed, the nest's beacon, and at 0 the end."""
    c = s.data.get("clock")
    if c is None or c.get("stopped_at") is not None or c.get("out"):
        return
    left = time_left(s)
    shown = max(0, math.ceil(left))
    if shown != c["shown"]:
        c["shown"] = shown
        if c["group"] is not None:
            panel_time(s, c["group"], c["text"], shown)
    if s.data.get("spot") == NEST and left <= BEACON_LEFT:
        beacon(s)
    if s.data.get("subjugation"):
        subjugation_tick(s, left)
    if left <= 0:
        c["out"] = True
        clock_out(s)
        return
    s.later(left - (shown - 1) + CLOCK_STEP, lambda: tick(s))


def clock_out(s):
    """The clock ran out: the nest ends its trial (won when the three real goblins are down); the corridor's exit would
    have closed (the original's fail, not built: Q2)."""
    from . import game
    spot = s.data.get("spot")
    net.journal("rule", spot=spot, ev="clock out")
    if spot == NEST and (s.data.get("nest") or {}).get("done"):
        d = setting(s)
        from . import director
        director.run(s, ("notice", NEST_DONE[0], NEST_DONE[1] + SETTING_STEP * d))
        game.mission_won(s, s.state)
    elif spot == NEST:
        log.info("mission %s: the entrance is restored before the real goblins fell (the original ended the trial; "
                 "no defeat, Q2)", spot)
    elif spot == STORM:                                 # the storm closed: survived, the room is won
        game.panel_done(s, STORM_SURVIVE_LINE)
        log.info("mission %s: the dimension storm closed", spot)
        game.mission_won(s, s.state)
    elif s.data.get("subjugation"):                     # survived: the success lines complete, the room is won
        got = game.mission_text(spot)
        for line in (got[1][0][1] if got and got[1] else ()):
            game.panel_done(s, line)
        log.info("mission %s: the subjugation's clock ran out: survived", spot)
        game.mission_won(s, s.state)
    elif spot in (ESSEX, KEDINGTON):
        log.info("mission %s: the clock ran out (the original failed the mission: %s; no defeat, Q2)", spot,
                 "the forest is contaminated" if spot == ESSEX else "the gate was not opened in time")
    else:
        log.info("mission %s: the clock ran out, the boss stands (the original failed the mission; no defeat, Q2)",
                 spot)


# --- the rooms ---

def plan(spot, p):
    """A mission room's plan (game.mission_plan) as a rule runs it (game.spawn_zone_troops): the Dimensional Test
    brings its levels itself, so the fallback holds no wave (its eleven boss templates and ten stage troops); the
    Sunstruk Colosseum fights its rounds (colosseum_rounds)."""
    if spot == DIMENSION:
        return dict(p, waves=())
    if spot in COLOSSEUM:
        return dict(p, waves=colosseum_rounds(p["waves"]))
    return p


@functools.cache
def storm_device(spot):
    """The prop id of Grey Hampton's relic device: its STORM_DEVICE_TYPE prop nearest the dimension storm prop."""
    from . import zone
    props = zone.for_spot(spot)["SmartPropData"]
    storm = next((p for p in props if p["SmartPropTypeID"] == STORM_PROP_TYPE), None)
    devices = [p for p in props if p["SmartPropTypeID"] == STORM_DEVICE_TYPE]
    if storm is None or not devices:
        return None
    return min(devices, key=lambda p: math.hypot(p["PosX"] - storm["PosX"], p["PosZ"] - storm["PosZ"]))["SmartPropID"]


def on_prop_broken(s, p):
    """An attackable prop broke (game's props_hit): Grey Hampton's relic device starts the storm's closing clock."""
    from . import director, game
    if s.data.get("spot") != STORM or p["SmartPropID"] != storm_device(STORM) or s.data.get("clock"):
        return
    game.panel_done(s, STORM_DEVICE_LINE)
    game.panel_line(s, STORM_GROUP, STORM_SURVIVE_LINE)
    director.run(s, ("notice", *STORM_NOTICE))
    log.info("mission %d: the relic device is down; the dimension storm closes in %d s", STORM, STORM_CLOSE_S)
    start_clock(s, STORM_CLOSE_S, STORM_TIME_TEXT, STORM_TIME_TEXT)   # its own heading, the time under it


def colosseum_rounds(waves):
    """The colosseum's rounds in order, from its troops' aliases (ROUND: 20302 라운드1..7, 20319 보스_0<round><k>);
    a held troop with no round number fights in none (20302's Exile 20011 and F22000's seven unnamed troops, the
    opponents of an older set of the announcer's lines, 1100-11400: the current set, 501100-511004, names the seven
    rounds' opponents and ends with the seventh, "Kugash conquered the colosseum")."""
    rounds = {}
    for t in (t for w in waves for t in w):
        m = ROUND.search(str(t.get("TroopAlias") or ""))
        if m:
            rounds.setdefault(int(m.group(1) or m.group(2)), []).append(t)
    return tuple(tuple(rounds[k]) for k in sorted(rounds))


def round_break(s):
    """The colosseum's break (game.mission_troop_down, when a round's last opponent fell and rounds remain): True
    while the next round waits. "Next match begins in 15 sec." now, "... in 5 sec." ten seconds on, and the next round
    ROUND_WAIT_S after the fall (missiontext 60 / 61; 112 "Next battle begins as soon as the result is confirmed").
    The notices on the left panel, as the director's, are ours: the tape shows no colosseum."""
    from . import director, game
    if s.data.get("spot") not in COLOSSEUM or not s.data.get("waves") or s.data.get("mission_won"):
        return False
    if s.data.get("round_break"):
        return True
    s.data["round_break"] = True
    net.journal("rule", spot=s.data.get("spot"), ev="round break", secs=ROUND_WAIT_S)
    director.run(s, ("notice", NEXT_MATCH))

    def soon():
        if s.data.get("round_break") and not s.data.get("mission_won"):
            director.run(s, ("notice", NEXT_MATCH_SOON))

    def begin():
        s.data["round_break"] = False
        if not s.data.get("mission_won"):
            game.next_wave(s)
    s.later(ROUND_WAIT_S - ROUND_SOON_S, soon)
    s.later(ROUND_WAIT_S, begin)
    return True


def start(s):
    """A mission room's rule at its start (game.spawn_zone_troops, after the panel and the director): the corridor's
    clock, the nest's panel, the Dimensional Test's first storm, a subjugation's clock."""
    spot = s.data.get("spot")
    if corridor(spot):
        start_corridor(s)
    elif spot == NEST:
        start_nest(s)
    elif spot == DIMENSION:
        start_dimension(s)
    elif subjugation(spot):
        start_subjugation(s)
    elif spot == ESSEX:
        s.data["totems"] = 0
        from . import game
        game.panel_count(s, ESSEX_COUNT, ESSEX_COUNT, 0, len(essex_totems(s.data.get("difficulty", 0))))
    elif spot == KEDINGTON:
        from . import director, game
        director.run(s, ("notice", *KED_NOTICE))
        game.panel_line(s, FAIL_GROUP, KED_FAIL_LINE)
        start_clock(s, KED_GATE_S, KED_CLOCK, KED_CLOCK)


@functools.cache
def essex_totems(difficulty):
    """TroopIDs of Essex's seven counted totems (the zone's TOTEM troops of the room's difficulty but the entrance's)."""
    from . import game, zone
    names = game.force_names(ESSEX)
    return tuple(t["TroopID"] for t in zone.for_spot(ESSEX)["NPCTroopInfoData"] if t["TroopTableID"] == TOTEM
                 and game.for_difficulty(t, names, difficulty)
                 and not str(t.get("TroopAlias") or "").startswith(TOTEM_ENTRANCE))


def on_down(s, uid, t):
    """A mission troop fell (game.mission_troop_down, before the win rule): Essex's totems count and feed the clock
    (the entrance's starts it, each other adds TOTEM_BONUS_S), its Chaos Wedge wins the room."""
    if s.data.get("spot") != ESSEX or t is None or s.data.get("mission_won"):
        return
    from . import game
    kind = t.get("TroopTableID", 0) % VARIANT
    if kind == WEDGE and s.data.get("totems", 0) >= len(essex_totems(s.data.get("difficulty", 0))):
        log.info("mission %d: the Chaos Wedge fell, its ward gone", ESSEX)          # (before that the original's ward
        game.mission_won(s, s.state)                    # kept it standing; ours has none: the wave rule decides then)
    elif kind == TOTEM and str(t.get("TroopAlias") or "").startswith(TOTEM_ENTRANCE):
        if s.data.get("clock") is None:
            start_clock(s, CONTAMINATE_S, ESSEX_TIME, ESSEX_TIME)
    elif kind == TOTEM:
        n = s.data["totems"] = s.data.get("totems", 0) + 1
        game.panel_count(s, ESSEX_COUNT, ESSEX_COUNT, n, len(essex_totems(s.data.get("difficulty", 0))))
        c = s.data.get("clock")
        if c is not None and not c.get("out") and c.get("stopped_at") is None:
            c["limit"] += TOTEM_BONUS_S                  # the clock's next tick shows it
        net.journal("rule", spot=ESSEX, ev="totem", n=n, left=c and round(time_left(s)))


def start_corridor(s):
    from . import director, game
    got = game.mission_text(s.data["spot"])
    base = got[0] - CORRIDOR_TITLE if got and got[0] is not None else None
    if base is not None:
        director.run(s, ("notice", *(base + n for n in CORRIDOR_START_NOTICE)))
    start_clock(s, CORRIDOR_S, base and base + CORRIDOR_TIMER, base and base + CORRIDOR_TIME_TEXT)   # as the troops
    s.data["clock"]["base"] = base                                        # come in: a full 5:00 shown (ours)


def corridor_grade(left):
    """Grade index of a corridor boss that fell with `left` seconds on the clock (CORRIDOR_GRADES)."""
    return next((g for need, g in CORRIDOR_GRADES if left >= need), LATE)


def setting(s):
    """The entry's difficulty 0..2: the nest's setting (0 Golden, 1 Vision, 2 Enchanter), the Dimensional Test's
    starting level."""
    d = s.data.get("difficulty", 0)
    return d if d in (0, 1, 2) else 0


def start_nest(s):
    from . import game
    d = setting(s)
    game.send_actions(s, [game.ACT_SITUATION_TITLE, game.ALL_TEAMS, NEST_TITLE + SETTING_STEP * d])
    game.panel_line(s, NEST_DOOR_GROUP, NEST_DOOR_LINE + SETTING_STEP * d)


def on_prop(s, p, roll=random.choice):
    """A prop the player cast (game.prop_cast_done): the nest's entrance opens the trial once: the other entrance prop
    opens too (game.switch_on), one of the six box-goblin forces comes in as the three real goblins (hidden from the
    pointer until the beacon), and the clock starts. Kedington's lever ends its clock: the group and the time go."""
    if s.data.get("spot") == KEDINGTON and p["SmartPropTypeID"] == KED_LEVER_TYPE:
        c = s.data.get("clock")
        if c is not None and c.get("stopped_at") is None and not c.get("out"):
            from . import game
            c["stopped_at"] = time.monotonic()
            s.data.get("panel_groups", set()).discard(KED_CLOCK)
            game.send_actions(s, [ACT_SITUATION_REMOVE_GROUP, game.ALL_TEAMS, KED_CLOCK])
            log.info("mission %d: the gate lever is pulled with %.0f s left", KEDINGTON, time_left(s))
            net.journal("rule", spot=KEDINGTON, ev="lever", left=round(time_left(s)))
        return
    if s.data.get("spot") != NEST or p["SmartPropTypeID"] not in NEST_DOOR or s.data.get("nest"):
        return
    from . import game, zone
    d = setting(s)
    z = zone.for_spot(NEST)
    for q in z["SmartPropData"]:
        if q["SmartPropTypeID"] in NEST_DOOR and q["SmartPropID"] != p["SmartPropID"]:
            game.switch_on(s, q)
    boxes = [t for t in z["NPCTroopInfoData"] if t["TroopTableID"] == BOX_GOBLIN]
    force = roll(sorted({t["ForceNum"] for t in boxes}))
    real = [t for t in boxes if t["ForceNum"] == force]
    for t in real:
        game.spawn_zone_troop(s, dict(t, Target=True, Hidden=True))
    game.send_actions(s, [game.ACT_ENABLE_ALL_TROOPS, 1, 1])
    s.data["nest"] = {"force": force, "real": [t["TroopID"] for t in real]}
    game.panel_done(s, NEST_DOOR_LINE + SETTING_STEP * d)
    game.panel_line(s, NEST_TRIAL_GROUP, NEST_TRIAL_LINE + SETTING_STEP * d)
    log.info("mission %d: the entrance opens (prop %d): the real goblins are force %d %s", NEST, p["SmartPropID"],
             force, s.data["nest"]["real"])
    net.journal("rule", spot=NEST, ev="door", prop=p["SmartPropID"], force=force, real=s.data["nest"]["real"])
    start_clock(s, NEST_S, NEST_TIMER, NEST_TIME_TEXT)


def beacon(s):
    """With 2:00 left the real goblins still standing light up (ActGuiSetHighlightTroop, until they fall) and the
    pointer may show them."""
    n = s.data.get("nest")
    if not n or n.get("beacon"):
        return
    from . import game
    n["beacon"] = True
    down, troops = s.data.get("down", set()), s.data.get("zone_troops", {})
    lit = [u for u in n["real"] if u in troops and u not in down]
    for u in lit:
        troops[u]["Hidden"] = False
        game.send_actions(s, [ACT_HIGHLIGHT_TROOP, u, 0, 1, 0])
    log.info("mission %d: the beacon on the real goblins %s", NEST, lit)
    net.journal("rule", spot=NEST, ev="beacon", troops=lit)
    game.point_to_enemy(s)


def holds_win(s):
    """Whether the rule holds the room's win after its last target fell (game.mission_troop_down): the nest's trial
    ends with its clock ("the mission always runs the full 5 min"); its trial line completes now. Not once the clock
    ran out: the third goblin falling late wins at once, with nothing paid (on_won). The Dimensional Test holds it until
    its fiftieth level (level_passed). Grey Hampton's win is the storm's clock (on_prop_broken, clock_out)."""
    if s.data.get("spot") == DIMENSION:
        return level_passed(s)
    if s.data.get("spot") == STORM:
        return True
    n = s.data.get("nest")
    left = time_left(s)
    if s.data.get("spot") != NEST or not n or left is None or left <= 0:
        return False
    if not n.get("done"):
        from . import game
        n["done"] = True
        game.panel_done(s, NEST_TRIAL_LINE + SETTING_STEP * setting(s))
        log.info("mission %d: the three real goblins are down with %.0f s left; the trial ends with the clock", NEST,
                 left)
        net.journal("rule", spot=NEST, ev="trial done", left=round(left))
    return True


def on_won(s, c):
    """The room is won (game.mission_won): the clock stops; a timed rule's (grade index, pays) or None (the general
    grade then); the day's clear counted unless the target fell late. The corridor's panel line completes and its
    notice shows; the Dimensional Test pays its stage chests (pay_dimension)."""
    from . import director, game
    spot, difficulty = s.data.get("spot"), s.data.get("difficulty", 0)
    left, ruled = time_left(s), None
    if spot == DIMENSION:
        ruled = pay_dimension(s, c)
    if left is not None:
        s.data["clock"]["stopped_at"] = time.monotonic()
        if corridor(spot):
            ruled = (corridor_grade(left), True) if left >= 0 else (LATE, False)
            base = s.data["clock"].get("base")
            if left >= 0 and base is not None:
                game.panel_done(s, base + CORRIDOR_WIN_LINE)
                director.run(s, ("notice", *(base + n for n in CORRIDOR_WIN_NOTICE)))
        elif spot == NEST:
            ruled = (0, True) if (s.data.get("nest") or {}).get("done") else (LATE, False)
        if ruled:
            log.info("mission %s: %.0f s left on the clock -> grade %s%s", spot, left, game.GRADES[ruled[0]],
                     "" if ruled[1] else " (late: nothing paid)")
            net.journal("rule", spot=spot, ev="graded", left=round(left), grade=game.GRADES[ruled[0]], pays=ruled[1])
    if ruled is None or ruled[1]:
        count_day(c, spot, difficulty, CLEAR, s=s)
    return ruled


# --- the Dimensional Test ---

@functools.cache
def dimension_rows():
    """({tier: [troop ids]}, {level: [boss troop ids]}) of nptrooptable's single-wave rows (1-91_존1_싱글웨이브_N단계):
    the 54 regulars of tiers 1-5 and the 11 bosses named for levels 5 .. 50 (35: two juggernauts); not the stage-reward
    rows (보상)."""
    tiers, bosses = {}, {}
    for r in tables.load("nptrooptable"):
        sid = str(r.get("StringID", ""))
        if not sid.startswith(DIMENSION_CODE) or "보상" in sid:
            continue
        tier, boss = TIER.search(sid), BOSS_AT.search(sid)
        if boss:
            bosses.setdefault(int(boss.group(1)), []).append(int(r["NPTROOP_ID"]))
        elif tier:
            tiers.setdefault(int(tier.group(1)), []).append(int(r["NPTROOP_ID"]))
    return tiers, bosses


def level_troops(level, roll=random.choice):
    """The troop ids of a level: the bosses named for it, else one regular of its tier (which one and how many: the
    unshipped script's; ours, one picked at random)."""
    tiers, bosses = dimension_rows()
    return list(bosses.get(level) or [roll(tiers[(level - 1) // 10 + 1])])


def show_prop(s, p, on):
    """One 0x50d1 record: a zone prop shown or hidden in its off state (the storm while its level stands)."""
    from . import game
    w = Writer(game.S2C_PROP_LIST).u16(1)
    game.write_prop(w, p["SmartPropID"], (round(p["PosX"]), round(p["PosZ"])), on)
    s.send(w)


def start_dimension(s):
    from . import director, game
    first = DIMENSION_START[setting(s)]
    s.data["dimension"] = {"first": first, "level": first - 1, "passed": first - 1, "uid": DIMENSION_UID}
    game.send_actions(s, [game.ACT_SITUATION_TITLE, game.ALL_TEAMS, DIM_TITLE])
    game.panel_line(s, *DIM_DETAILS)
    game.panel_count(s, *DIM_PROGRESS, first - 1, DIMENSION_TOP)
    director.run(s, ("notice", DIM_NOTICE, DIM_STARTING, DIM_TIP))
    net.journal("rule", spot=DIMENSION, ev="test", first=first)
    s.later(STORM_S, lambda: open_storm(s))


def open_storm(s, roll=random.choice):
    """The next level: its storm (one of the zone's eight, picked at random: ours) shows, and the level's troops come
    out of it (game.spawn_zone_troop, as the boss templates of F21000 with the level's table row); the pointer leads the
    hero there (the zone has no bound near the start for a march)."""
    dim = s.data.get("dimension")
    if not dim or dim.get("storm") or s.data.get("mission_won"):
        return
    from . import director, game, zone
    z = zone.for_spot(DIMENSION)
    dim["level"] += 1
    level = dim["level"]
    p = roll([q for q in z["SmartPropData"] if q["SmartPropTypeID"] == STORM_TYPE])
    dim["storm"] = p["SmartPropID"]
    show_prop(s, p, True)
    template = next(t for t in z["NPCTroopInfoData"] if t.get("ForceNum") == DIMENSION_FORCE)
    uids = []
    for i, tid in enumerate(level_troops(level, roll)):
        uid = dim["uid"]
        dim["uid"] += 1
        t = dict(template, TroopID=uid, TroopTableID=tid, TroopAlias=f"단계{level}", PosX=p["PosX"] + SPREAD * i,
                 PosZ=p["PosZ"], IsActivated=1, SpawnActivated=1, UnitNum=0, NPLeaderID=-100)
        if game.spawn_zone_troop(s, t):
            uids.append(uid)
    game.send_actions(s, [game.ACT_ENABLE_ALL_TROOPS, 1, 1])
    director.run(s, ("notice", DIM_NOTICE, DIM_OPENED))
    log.info("mission %d: level %d's storm %d opens: %s", DIMENSION, level, p["SmartPropID"], uids)
    net.journal("rule", spot=DIMENSION, ev="storm", level=level, prop=p["SmartPropID"], troops=uids)
    game.point_to_enemy(s)


def level_passed(s):
    """The open level's troops are down (holds_win): its storm closes, the progress counts it, and the next storm
    comes in STORM_S; True while levels are left, False at the fiftieth (the room is won)."""
    dim = s.data.get("dimension")
    if not dim:
        return False
    level = dim["level"]
    if level <= dim["passed"]:
        return level < DIMENSION_TOP
    from . import director, game
    dim["passed"] = level
    storm = dim.pop("storm", None)
    if storm is not None:
        show_prop(s, game.zone_prop(DIMENSION, storm), False)
    game.panel_count(s, *DIM_PROGRESS, level, DIMENSION_TOP)
    log.info("mission %d: level %d passed", DIMENSION, level)
    net.journal("rule", spot=DIMENSION, ev="level", level=level)
    if level >= DIMENSION_TOP:
        return False
    director.run(s, ("notice", DIM_NOTICE, DIM_SOON))
    s.later(STORM_S, lambda: open_storm(s))
    return True


@functools.cache
def stage_troops():
    """{level: zone troop} of the Dimensional Test's stage rewards (F20000 보상5단계 .. 보상50단계)."""
    from . import zone
    out = {}
    for t in zone.for_spot(DIMENSION)["NPCTroopInfoData"]:
        m = STAGE.match(str(t.get("TroopAlias") or ""))
        if m:
            out[int(m.group(1))] = t
    return out


def pay_dimension(s, c, now=None):
    """The run ends (on_won: the fiftieth level passed, or the room won otherwise): the first end of the game day
    (game_day) pays, at the hero's feet, the stage chest of each fifth level this run passed (the stage troop's %Troop
    loot, as the original's script killed it: "a reward every 5 levels paid at the end") and the card; a later run
    that day pays nothing ("rewards once, retries allowed"). (grade S, pays)."""
    from . import game, loot
    dim = s.data.get("dimension") or {}
    day = game_day(now)
    if c.get("dimension_paid") == day:
        log.info("mission %d: the day's rewards are paid already", DIMENSION)
        net.journal("rule", spot=DIMENSION, ev="paid today", passed=dim.get("passed"))
        return 0, False
    c["dimension_paid"] = day
    paid = []
    for level, t in sorted(stage_troops().items()):
        if dim.get("first", 1) <= level <= dim.get("passed", 0):
            game.drop_loot(s, loot.roll_drops(DIMENSION, t["TroopTableID"]), game.roll_gold(t["TroopTableID"]))
            paid.append(level)
    log.info("mission %d: levels %s-%s, the stage chests of %s", DIMENSION, dim.get("first"), dim.get("passed"), paid)
    net.journal("rule", spot=DIMENSION, ev="chests", passed=dim.get("passed"), stages=paid)
    return 0, True


# --- Subjugation ---

def subjugation(spot):
    return spot in SUBJUGATIONS and (tables.by_id("spottable").get(str(spot)) or {}).get(
        "Spot_Contents_Type") == SUBJUGATION


def subjugation_groups(s):
    """What the panel's count counts: the targets of the room's difficulty by wave (the plan's phase number, else
    ForceNum: 10327's 1웨이브..6웨이브, 20326's six forces, 20327's 1-x .. 9-x), or Field of Watchtower's towers."""
    from . import game, zone
    spot, difficulty = s.data["spot"], s.data.get("difficulty", 0)
    names, phases = game.force_names(spot), (s.data.get("plan") or {}).get("phases", {})
    towers = SUBJUGATIONS[spot][1][2] == "towers"
    groups = {}
    for t in zone.for_spot(spot)["NPCTroopInfoData"]:
        if not (game.hostile(t) and not game.staging(spot, t, names) and game.for_difficulty(t, names, difficulty)):
            continue
        if not towers:
            groups.setdefault(phases.get(t["TroopID"], ("force", t.get("ForceNum"))), set()).add(t["TroopID"])
        elif TOWER_WORD in str(t.get("TroopAlias") or ""):
            groups[t["TroopID"]] = {t["TroopID"]}
    return list(groups.values())


def start_subjugation(s):
    from . import director, game, zone
    spot = s.data["spot"]
    texts = SUBJUGATIONS[spot]
    names = game.force_names(spot)
    goblins = [t for t in zone.for_spot(spot)["NPCTroopInfoData"]
               if (zone.np_troop(t["TroopTableID"]) or {}).get("NP_Grade") == "Extra"
               and t["TroopID"] not in s.data.get("zone_troops", {})
               and game.for_difficulty(t, names, s.data.get("difficulty", 0))]
    s.data["subjugation"] = {"groups": subjugation_groups(s), "goblins": goblins, "done": set(), "count": None}
    director.run(s, ("notice", *texts[2]))
    start_clock(s, SUBJUGATION_S, *texts[0])


def subjugation_tick(s, left):
    """A subjugation's second (tick): the count when it changed, the goblin in at GOBLIN_AT and off GOBLIN_STAY later
    when still standing, the 60 s and 30 s notices."""
    from . import director, game
    sub, spot = s.data["subjugation"], s.data["spot"]
    texts = SUBJUGATIONS[spot]
    down = s.data.get("down", set())
    done, n = sum(1 for g in sub["groups"] if g <= down), len(sub["groups"])
    group, text, kind = texts[1]
    count = {"current": min(n, done + 1), "remaining": n - done, "towers": done}[kind], n
    if count != sub["count"]:
        sub["count"] = count
        game.panel_count(s, group, text, *count)
    elapsed = SUBJUGATION_S - left
    for mark, due, act in (("goblin", elapsed >= GOBLIN_AT, goblin_in), ("goblin off", elapsed >= GOBLIN_AT +
                           GOBLIN_STAY, goblin_off), ("60", left <= 60, texts[3]), ("30", left <= 30, texts[4])):
        if due and mark not in sub["done"]:
            sub["done"].add(mark)
            if callable(act):
                act(s)
            else:
                director.run(s, ("notice", *act))


def goblin_in(s):
    from . import director, game
    sub = s.data["subjugation"]
    uids = [t["TroopID"] for t in sub["goblins"] if game.spawn_zone_troop(s, t)]
    if not uids:
        return
    game.send_actions(s, [game.ACT_ENABLE_ALL_TROOPS, 1, 1])
    sub["goblin"] = uids
    notice = SUBJUGATIONS[s.data["spot"]][5]
    if notice:                                      # centred, as the footage's frame of 21:22 shows it
        game.send_actions(s, [director.ACT_NOTICE_WINDOW, director.NOTICE_MID, *notice,
                              *[director.NO_TEXT] * (4 - len(notice)), director.NOTICE_S])
    log.info("mission %s: the treasure goblin comes: %s", s.data["spot"], uids)
    net.journal("rule", spot=s.data["spot"], ev="goblin", troops=uids)


def goblin_off(s):
    from . import game
    down = s.data.get("down", set())
    for uid in [u for u in s.data["subjugation"].get("goblin", ()) if u not in down]:
        game.troop_leaves(s, uid)
        net.journal("rule", spot=s.data["spot"], ev="goblin off", troop=uid)


# --- day limits ---

@functools.cache
def day_groups():
    """{DayLimit group: (DayLimit_Type, DayLimit_Count)} (spottable %DayLimit: the corridor's 150 one clear, the nest's
    410 one clear, the subjugations' 110-140 three entries, the invasions' 301-303 two clears, the extremes' 100-102 one
    clear)."""
    return {int(r["GroupID"]): (r["DayLimit_Type"], int(r["DayLimit_Count"]))
            for r in tables.sections("spottable")["DayLimit"] if r["GroupID"].isdigit()}


def day_group(spot, difficulty):
    """The spot's DayLimit group on a difficulty (DayLimit_GroupID_<difficulty + 1>), or None."""
    difficulty = difficulty if difficulty in (0, 1, 2) else 0
    g = str((tables.by_id("spottable").get(str(spot)) or {}).get(f"DayLimit_GroupID_{difficulty + 1}", ""))
    return int(g) if g.isdigit() and int(g) in day_groups() else None


def game_day(now=None):
    """The date the day limits count for: the UTC date, the day starting at DAY_START_HOUR. The one day of the
    dailies, the repeat quests, the item day limits and the coin shop too (rules census L6, decision E7 (a))."""
    t = time.time() if now is None else now
    return datetime.datetime.fromtimestamp(t - DAY_START_HOUR * 3600, datetime.timezone.utc).date().isoformat()


def attendance_day(now=None):
    """The attendance calendar's date: the UTC date, the day starting at 00:00 UTC ("attendance ~4 pm PST" [C]
    SD-reset in planning/reference/OFFICIAL-NOTES.md; rules census L6)."""
    t = time.time() if now is None else now
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date()


def day_counts(c, now=None):
    """{group (str): used today} of the character, emptied on a new day."""
    day = game_day(now)
    if (c.get("day_limits") or {}).get("day") != day:
        c["day_limits"] = {"day": day, "counts": {}}
    return c["day_limits"]["counts"]


def day_refusal(c, spot, difficulty, now=None):
    """The 0x3f41 result refusing an entry whose day group is spent, or None."""
    g = day_group(spot, difficulty)
    if g is None:
        return None
    return DAY_LIMIT_REFUSED if day_counts(c, now).get(str(g), 0) >= day_groups()[g][1] else None


def count_day(c, spot, difficulty, kind, now=None, s=None):
    """One more of `kind` (ENTER at the entry, CLEAR at a win) for the spot's day group when the group counts that;
    the new count pushed to session s (0x10b4, census J4; 0x10b3 still resends them all at each town / field entry)."""
    g = day_group(spot, difficulty)
    if g is None or day_groups()[g][0] != kind:
        return
    counts = day_counts(c, now)
    counts[str(g)] = counts.get(str(g), 0) + 1
    if s is not None:
        s.send(Writer(S2C_DAY_LIMIT).i32(g).raw(bytes(DAY_ENTRY_PAD)).u8(min(counts[str(g)], 0xFF)))
    log.info("day limit group %d (%s %d): %d used today", g, kind, day_groups()[g][1], counts[str(g)])
    net.journal("rule", spot=spot, ev="day limit", group=g, kind=kind, used=counts[str(g)], top=day_groups()[g][1])


def day_limits_packet(c, now=None):
    """S2C 0x10b3: today's counts, replacing the client's map (the reply to 0x10b2, and at each city or field entry, so
    a day turned or a clear won in a room reaches it)."""
    counts = sorted((int(g), n) for g, n in day_counts(c, now).items() if n > 0)
    w = Writer(S2C_DAY_LIMITS).u16(len(counts))
    for g, n in counts:
        w.i32(g).raw(bytes(DAY_ENTRY_PAD)).u8(min(n, 0xFF))
    return w

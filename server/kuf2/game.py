"""Game (battle) role: the client connects here after world's 0x3f41 (battle server address).

Battles are host-simulated by a client (GameStateBattleField::Packet_HostChange, in-client AI and
mission scripts); offline, the only client is the host, so this role sets the battle up and relays.
"""
import functools
import math
import random
import re
import struct
import time

from . import combat, director, items, loot, net, obf, rules, skills, status, tables
from .net import Role, log
from .packet import OBOOL_FALSE, OBOOL_TRUE, Writer

C2S_GAME_LOGIN = 0x5084          # u32 character id (common+0xd4), u16, u32 echoed from 0x3f41 (sent on connect)
S2C_GAME_LOGIN_RES = 0x5085      # global handler @ 0x140cbf3f0: u16 result
S2C_SPOT_ROOM_START = 0x3f4e     # GameStateManager::ProcessPacket_SpotRoomGameStartHeader @ 0x140cbe9d0 -> 0x140d09380
S2C_START_PLAYER_INFO = 0x3f4f   # -> BattleField 0x140d09720 (Packet_SpotRoomGameStartPlayerInfo): u16 n, n * (191 bytes, cstr, cstr)
S2C_START_TROOP_INFO = 0x3f50    # -> BattleField 0x140d0a370 (Packet_SpotRoomGameStartTroopInfo): u16 n, n * troop (reader 0x140d0d5d0)
C2S_LOAD_PROGRESS = 0x5040       # u8 percent
S2C_LOAD_PROGRESS = 0x5041       # GameStateLoading::ProcessPacket_MissionLoad @ 0x140e59b20: u32 player id, u8
S2C_ALL_LOADED = 0x5042          # @ 0x140e59be0: obool late-join. true -> "Latejoin StartGame": jump straight to the
                                 # battle state, skipping InitInGame's world setup (black 3D view). false -> keep loading
                                 # (phase 6) until the mission script sends ActSystemRenderStart.
S2C_HOST_CHANGE = 0x50b5         # @ 0x140e59e20 (loading) / Packet_HostChange (battle): u16 host id; == my id -> I simulate
MY_SLOT = 0                      # header +1 slot id (= player id in the start records); also the host id. It must equal
                                 # the hero's troop uid: the client finds a troop's hero as the troop whose uid is the
                                 # troop's owner id (GetHeroTroop 0x140bac2b1 and three more sites), so with 1 here and
                                 # hero uid 0 no owned troop had a hero and Hero Support never followed (2026-11-06)
# The player's hero is the leader of the first troop in 0x3f50 (0x140d0a370 stores troop 0's leader id
# as the player's hero). For player heroes the leader id is the hero class: the leader-info map
# *0x1435a4ac8 holds keys 0..5 (tools/frida/mapkeys.js); leadertable 300-310 are AI companions.
HERO_TROOP_ID = 1100111          # trooptable: basic Bersia swordsman
PLAYER_TEAM = 0                  # tools/frida/startpoints.js: 1_TrainingCamp has one start point, team 0 group 0
S2C_ENTER_CELL_TROOP = 0x50cb    # GameStateBattleField::Packet_EnterCell_Troop @ 0x140d06b70: u16 n, entries (0x140d0d050)
S2C_TROOP_SIMULATION = 0x50cf   # 0x140d1c3f0: u16 target troop, u16 reference troop; simulate when reference is ours
S2C_TROOP_HP = 0x505d            # combat dispatcher 0x140d15230 -> 0x140d17a30: records until the end of the packet:
                                 # u8 flags, u16 uid, [troop hp], [leader hp], [u16]; see send_troop_hp
S2C_SET_SPAWN_AI = 0x5083        # Packet_SetSpawnAI @ 0x140d02f60: 26 bytes; +8 uid, +0x16 AI id (-1 = TAIBranch NPINIT)
C2S_PROP_CAST = 0x5094           # u16 caster troop uid, coded u32 prop id (SmartPropProcessor::CastBegin, 0x14091f900)
S2C_PROP_CAST = 0x5095           # 0x140d03480: coded prop id, i16 result, u16 caster; 0 starts the cast (0x140919e60)
C2S_PROP_CAST_DONE = 0x5096      # u16 caster, coded u32 prop id, when the cast bar ends (builder 0x14091fca0; live)
S2C_PROP_CAST_DONE = 0x5097      # Packet_SmartPropCastCompleteRes 0x140d035f0: u16 caster, coded prop id, i16 result;
                                 # on 0: 9 bytes (u32 new state at +5, applied by 0x140919b70 -> OnChangeSmartPropState),
                                 # u8 n * 8 bytes, u8 m * 8 bytes (0x140d0d8d0)
                                 # The 9 bytes: coded u40 gold (the item box's gold entry; bytes(5) read as ~8.4e11),
                                 # i32 state; the n items (coded u16 count, coded u32 code, coded u16 index) fill an
                                 # item box's loot window (0x1408d93b0), from which the player takes them (0x5098)
C2S_PROP_CANCEL = 0x50a6         # coded u32 prop id: a cast in progress was cancelled (moved, hit; 0x140919cf0); no reply
C2S_BOX_ITEM = 0x5098            # ItemRootingManager::ItemRooting 0x1408daaf0 (loot window mode 0), 14 bytes: coded u32
                                 # item, coded u32 box (prop) id, coded u16 index, coded u16 count, u16 caster; the client
                                 # checked the bag has room
S2C_BOX_ITEM = 0x5099            # 0x140dc33d0, 7 bytes (shorter crashes): coded u32 box id, obool silent, i16 result (0
                                 # removes the entry and says "obtained"; 0x6403 bag full); the bag must follow
C2S_BOX_GOLD = 0x509d            # the gold entry, 11 bytes: coded u40 gold, u16 caster, coded u32 box id
S2C_BOX_GOLD = 0x509e            # 0x140dc33b0, 6 bytes: coded u32 box id, i16 result (0x41a over the gold cap)
C2S_PROP_STATE = 0x50a1          # ReqChangeSmartPropState 0x14091d2d0 (the loot window closed or empty), 10 bytes: u32
                                 # state (2 = opened), u16 caster, coded u32 prop id
S2C_PROP_STATE = 0x50a2          # 0x140d038d0, 10 bytes: i16 result, u32 state, coded u32 prop id -> the prop's state
S2C_PROP_HP = 0x50a4             # 0x140d03bb0 -> HUD 0x74 (0x140555bf0): u16 n, n * (coded u32 prop id, i32 hp, i32 max)
S2C_PROP_SET_STATE = 0x50a3      # 0x140d039a0, 8 bytes: coded u32 prop id, i32 state -> OnChangeSmartPropState; an
                                 # attackable prop is broken at 2 (GameSmartPropAttack vt+0x218 0x1419b7460: usable
                                 # while state != 2)
PROP_BROKEN = 2
COMPOSITE_DESTROYED = 4          # SmartPropCompositeStateType: TYPE_NORMAL, _DAMAGED1-3, then TYPE_DESTORY (the client's spelling)
S2C_MISSION_COMPLETE = 0x5044    # GameStateBattleField::Packet_MissionCompletePVE (see mission_won)
MISSION_RECORD = 0x2a1           # 673 bytes a player
# E_MissionDifficult by value (name table 0x14353d0c0: Normal, Hard, Hell; index = value, inferred): the u8 of 0x3f48
# (the solo room's choice, world.enter_spot) names which MissionLevelClear conditions a win counts (ID1 ANY or
# that difficulty; exact match, inferred: no text says whether a harder clear also counts).
DIFFICULTY = ("NORMAL", "HARD", "HELL")
C2S_MISSION_LEAVE = 0x4040       # "ReqMissionOut" (builder 0x140eff1e0 via 0x140d61bc0), no payload: the HUD's Mission
                                 # Complete button (InGame.as btn_missionOut "@임무 완료", fscommand ReqMissionOut ->
                                 # 0x140c552a0: with unacquired drops (BattleField +0xca8 + +0xc98) the confirm box 0xd0d7
                                 # "There is an unidentified item. Do you want to leave the battlefield anyway?" first).
                                 # The button shows when the result window closes (0x140859c40 -> EnableMissionOut
                                 # 0x140c55240, after a win, window +0xc0 == 1), which it does by itself: its update
                                 # 0x14085ef60 counts from the end of the score animation, 3 s team info, 10 s the cards
                                 # with a 6 s timer (then 0x14085eec0 opens the allowed ones), 23 s the window closes
S2C_MISSION_LEAVE = 0x4041       # 0x140d003f0, see leave_mission
C2S_REWARD_CARD = 0x404c         # OpenSlot on the result screen (builder 0x140f06210): 1 plain byte, the card index 0..3;
                                 # the client sends only an unopened card while fewer than record +0x29f are open
S2C_REWARD_CARD = 0x404d         # 0x140d00350, 9 bytes always (shorter crashes): u16 player id, u8 card, coded u32 item
                                 # (-1 = an empty card), coded u16 count
S2C_AUTO_LEAVE = 0x50d2          # no body: window +0x38 = 5 s (0x14085abb0), then its update sends 0x4040 whatever the
                                 # player does; not sent (decision A10: the original waited for Mission Complete, tape
                                 # part 2 19:31-19:46, time to pick up the chests with Get All)
EMPTY_CARD = 0xFFFFFFFF
LAST_CARD = 3
# Loot on the ground (specs field_npc_travel.md "Loot on the ground", battle.md 0x50fb / 0x5136).
S2C_REWARD_BOX = 0x50eb          # Packet_RewardBoxCreate 0x140d04240 (reader 0x140d10790): u8 n, n * (21-byte header, u8 m,
                                 # m * item). Header: obool at the local hero (else the position that follows), packed
                                 # position (7), u16 owner (inferred), obool, coded u40 gold (type 1), i32 drop id, u8
                                 # type (1 = a gold pile for the gold-drop manager, else an item bag). Item: coded u16
                                 # count, coded u32 code (must have a table row), coded u16 index
C2S_DROP_PICK = 0x4052           # ItemRooting from a ground drop, 12 bytes: coded u16 count, u32 drop id, coded u32 item,
                                 # coded u16 index (the specs route it on the world connection: inferred)
S2C_DROP_PICK = 0x4053           # 0x140dc33f0, 14 bytes always (shorter crashes): i16, u32 drop id, coded u16 key, u16
                                 # (unused), coded u32 item. The client removes the picked item (0x140cf5a90) by code and
                                 # key = the drop entry's +8, which is the item record's FIRST field in 0x50eb (the
                                 # count as we send it, the pick's +0), not its index: a wrong key leaves the row and the
                                 # bag (live 2026-09-27). 0x6402 / 0x6403 "bag full", 0x6c1f quest item not needed
C2S_GOLD_PICK = 0x50fb           # the gold-drop manager's automatic pickup (0x140684a50), 6 bytes: u16 troop, i32 drop id
S2C_GOLD_PICK = 0x50fc           # 0x140683280: i16 + 6 bytes (u16, i32 id) read even on a refusal (under 8 crashes);
                                 # 0 plays the pickup, the gold total comes with the bag
C2S_GOLD_ALL = 0x5136            # collect all gold on the ground (the result screen closing), no payload
S2C_GOLD_ALL = 0x5137            # 0x140683e60: i16 (0 removes every pile)
C2S_LOOT_OWNER = 0x5140          # the name of a loot object I may not take: coded u32 id
S2C_LOOT_OWNER = 0x5141          # 0x140d05070, 6 bytes: i16, the id; 0 needs a cstr name; 1 = say nothing
DROP_BAG_FULL, QUEST_ITEM_FULL = 0x6402, 0x6c1f
DROP_GONE = 1                    # a result with no message (0x1408dcac0 shows texts only for 0x6402/3, 0x6c1f, 0x6c26)
FIRST_DROP_ID = 0x10000000       # above the zone prop ids (drops share the prop manager); never 0x7fffffff
TYPE_GOLD = 1
# Echoes a lone host still needs (specs/battle.md): each reply is the request's bytes, or as noted.
C2S_UNCHANT, S2C_UNCHANT = 0x5068, 0x5069          # end an active ability: coded u32 ability, u16 troop (6 bytes)
C2S_AREA_END, S2C_AREA_END = 0x5072, 0x5073        # a ground / aura effect ended: u16 event id first
C2S_CUTSCENE, S2C_CUTSCENE = 0x508b, 0x508c        # u32 cutscene id, keyed bool (T1[b4] & 1 = skip); reply u32 to a skip
C2S_MARK_TROOP, S2C_MARK_TROOP = 0x5142, 0x5143    # ping mark on a troop, 9 bytes (shorter crashes)
C2S_MARK_GROUND, S2C_MARK_GROUND = 0x5144, 0x5145  # ping mark on the ground, 8 bytes
C2S_PAUSE, S2C_PAUSE = 0x5149, 0x5148              # system menu Pause (1) / PauseRelease (0); 0x5148: u8 kind 0, u8
                                                   # T2[flag], cstr name (under 2 bytes crashes)
C2S_REVIVE_CAMP = 0x50d6         # "FieldMap_RevivalSystem" (free, at the nearest start point), no payload
S2C_REVIVE_CAMP = 0x50d7         # Packet_SystemRevivalRes 0x140d176d0: i16; 0 -> u16 troop, f32 z, f32 x; moves the hero
                                 # to the nearest start point but does not revive it outside PvP
S2C_TROOP_DOWN = 0x505c          # 0x140d17560, 8 bytes: 5 unread, obool dead, u16 troop (+ obool when dead): dead FALSE
                                 # = the revive (reset + Troop::Enable, closes the death window); push_B.md
S2C_DEATH_WINDOW = 0x50c6        # 0x140cffe00: u8, the window's countdown in seconds (ShowTimer; 0 times out at once over
                                 # its static "99"): the death window with the revive buttons
S2C_TROOP_LEAVE = 0x50cc         # LeaveCellTroop 0x140d06cc0: u16 n, n * u16 troop uid (sent before a respawn reuses it)
S2C_PROP_DELETE = 0x509c         # 0x140d03cf0: u16 n, n * coded u32 prop id (gone, out of the F targets)
S2C_PROP_REGEN = 0x509a          # Packet_SmartPropRegen 0x140d03f80, 7 bytes: u16 SmartPropTypeID, coded u32 prop id, byte
                                 # with T1[b] & 7 = the prop kind (2 attackable); recreates a deleted zone prop
PROP_KIND_ATTACK = 2
S2C_TROOP_BACK = 0x50c0          # 0x140d01ea0, 9 bytes: packed position (7), u16 troop -> moved there and vt+0x370(0), the
                                 # call NotiCompleteRevivalTroop uses (the revive; inferred, not observed)
S2C_TROOP_PLACED = 0x50b7        # Packet_MissionAllPlayerInfo 0x140cf4670: u16 n, n x 12: direction byte, 2 unread bytes, then
                                 # 0x50c0's 9 bytes. A troop that is not mine: SetPosition 0x1407e4bd0 at that direction and
                                 # InitPose vt+0x370(0), which lays its units on their slots (face_zone_angle)
C2S_REVIVE_HERE = 0x50f4         # HUDRevivalSystem::ReqTroopRevival (0x1406900e0), 6 bytes: u16 troop, coded u32 item
                                 # (0xffffffff = none; a kind-0x24 revival item otherwise)
S2C_REVIVE_HERE = 0x50f5         # 0x14068f960: i16; 0 -> u32 revivals used ("You are revived."); 0x7413 not now
C2S_REVIVE_COUNT = 0x513b        # the battle HUD's init (0x14068e280, builder 0x140eff190), 0 bytes
S2C_REVIVE_COUNT = 0x513c        # 0x140e10110: u32 revivals used, kept under my character key (HUD +0xd8 -> +0x38)
C2S_REVIVE_BANS = 0x513d         # the battle HUD's init outside Field / Field_PK rooms (builder 0x140f0ebe0), 0 bytes
S2C_REVIVE_BANS = 0x513e         # 0x140e101b0: u16 n, n x (u16 player, u32 revivals used), then 0x140690440: u16 m,
                                 # m x (u16 troop, i32 ms of revive ban left -> HUD +0xd8 -> +0x28, counted down)
S2C_FREE_REVIVES = 0x1089        # GameStateCommon 0x140d6ec80: u16 -> common+0x15c4, the free resurrections left (the
                                 # HUD's "Free Resurrection (xN)"; the confirm box then asks no price)
FREE_REVIVES = 3                 # a game day, the hero's and the deck troops' together (texttutorial Basic_FreeRevival
                                 # "3 times a day ... not accumulative"; the tape part 3 f_01166 "(x3)", f_01191 "(x1)")
BOX_BAG_FULL = 0x6403
GOLD_CAP_RESULT = 0x41a
PROP_REFUSED = 1                 # any non-zero result ends the cast with the client's error text (0x1409182d0)
PROP_OFF, PROP_ON = 0, 1         # switch states: the zone prop's two objects (e.g. sp_i_coc01 / sp_i_coc02)
PROP_OPEN = 2                    # a vanishing / breaking switch's state without collision (game.switch_on)
PROP_SWUNG = 3                   # a prison's open look without collision: live 2026-11-05 on 20075, 0 closed, 1 open with
                                 # collision, 2 CLOSED to look at, no collision, 3 open, no collision (open_state)
S2C_PROP_LIST = 0x50d1           # Packet_SmartPropUpdateList @ 0x140d062c0: u16 n, n * 23-byte record (write_prop)
S2C_MISSION_TROOP_INFO = 0x50b8  # Packet_MissionTroopInfo @ 0x140d052e0: 61-byte troop state (+u16 if flag 0x40), tail 0x140d0cdc0
# Troop-state flag byte (+0x3c), as 0x50b8 applies it: 0x04 create if missing, 0x10 sight on (Troop+0x94 bit 0x2000).
# The battle fog of war (0x140c08940 -> 0x140c05b90) blacks the screen out (Flash movie 0xbd, Fade_ColorA) unless the
# camera is inside the sight radius of a team troop that has that bit.
TROOP_ALIVE = 0x04               # clear -> 0x50b8 runs Troop::Die (0x1407e2ff0): no hero, Resurrection button
TROOP_SIGHT = 0x10               # sight (troop +0x94 0x2000; zone SharingSight)
TROOP_HOLD = 0x02                # hold position (troop +0x232; zone HoldMovement)
TROOP_FIRST_ATTACK = 0x08        # attacks first (troop +0x118e; zone FirstAttack). An aggressive troop's target check
                                 # 0x14080c3f0 takes only troops with this bit or ones that hate it, so the hero has it
                                 # too (planning/controls/ENEMY-AI.md §4.1)
HERO_FLAGS = TROOP_ALIVE | TROOP_SIGHT | TROOP_FIRST_ATTACK
NO_CAPTURE = 0xFFFF              # the troop-state tail's "not a capture point" (UiInGameTroopIcon's own default entry,
                                 # 0x140c68f70; write_troop_state)
# The client's stat enum (name table 0x1434a74e0 from its 5th entry, planning/features/BATTLE.md finding 5): the ids of
# the stats hero.stats computes, for the battle stat block and the in-room updates (0x5138)
STAT_IDS = {"HP_MAX": 0, "HP_RECOVERY": 2, "SP_CURRENT": 6, "SP_MAX": 7, "SP_RECOVERY": 8, "RANGE_SIGHT": 13,
            "MAX_MOVE_SPEED": 14, "ATTACK_PHYSICAL": 15, "ATTACK_MAGICAL": 16, "DEFENCE_PHYSICAL_CLOSE": 17,
            "DEFENCE_PHYSICAL_RANGE": 18, "DEFENCE_MAGICAL_FIRE": 19, "DEFENCE_MAGICAL_ICE": 20,
            "DEFENCE_MAGICAL_LIGHTNING": 21, "DEFENCE_MAGICAL_NATURE": 22, "DEFENCE_MAGICAL_HOLY": 23,
            "DEFENCE_MAGICAL_DARK": 24, "CRITICAL_PHYSICAL": 25, "CRITICAL_MAGICAL": 26, "CRITICALPROB_PHYSICAL": 27,
            "CRITICALPROB_MAGICAL": 28, "PHYSICAL_PENETRATE": 29, "ACCURACY": 31, "MISS": 32, "ATTACK_SPEED": 39,
            "HIT_RESIST": 40, "CRITICAL_REDUCE": 43, "CRITICALPROB_RESIST": 76, "MAGICAL_PENETRATE": 83}
S2C_LEVEL_UP = 0x508a            # Packet_NotifyLevelUp 0x140d1b7d0: u16 troop, obool leader, u8 level. True: the leader unit (+0x838) and the HUD record (+0x918 +0x5c), effect LEVEL_UP_UNIT; false: the troop, LevelUp_Troop
S2C_QUEST_ITEM_ALARM = 0x50aa   # QuestManager::Process_QuestItemDropAlarm 0x140d7c310: coded u32 box (prop) id, u8 n, n x
                                 # (coded u32 item, u16): marks the box and prints text 7233 "There is a box nearby that has
                                 # the quest item [%s] in it." per item (pushes_common.md)
S2C_KILL_FEED = 0x50fd           # kill message (0x140d07920): u16 killer, u16 victim, u8, obool TRUE (feed + chat line)
S2C_COMBAT_BONUS = 0x50da        # hero combat bonus (0x140d1c880): u8 kind (3 troop annihilated, 4 commander defeated ...),
                                 # u32 exp, u32, u32 SP; the Flash banner and the floating exp / SP numbers
HERO_HP = 1000
NP_TEAM = 1                      # experiment: enemy team
NP_OWNER = 0xfa                  # experiment: 0xfa is the "NPC" owner id in the 0x3f50 parse and the fog test
# Placeholder until mission placements come from the map's mission files (O5b): every battle gets one enemy troop
# beside the hero. nptrooptable 2 HUMAN_INFANTRY_FGT_N_LV1_1: 19 units x 1072 hp.
TEST_ENEMY = (2, 19 * 1072, 19)
# spot -> (x, y, z) spawn: spottable Start_X/Start_Z; y 0 (client snaps to terrain?)
# 10303 is the mission start point the client itself picked (read from the troop object, tools/frida/troops.js)
# (10331, the infantry camp, starts at its zone's start point through mission_start; (15000, 25000) was the minimap corner)
SPAWN_POS = {50116: (149730, 1919, 193754), 10303: (52588, 1047, 38209), 10305: (31500, 0, 24000)}
FIELD_TYPES = ("Field", "Field_PK")   # spottable Spot_Type of the open-world maps (FIELD-BATTLE-PLAN)
# Story missions the hero cannot die in, from the owner's walkthrough (Steam guide 2011029967): Grey Fog Streets 10358
# "You CANT Die in this mission", Tower of Moonlight 10233 "You Cannot Die - Regardless of dmg", Grey Rock Fortress
# 10234 "You wont die in this mission". No table says so (the original's mission Lua did it and is not shipped): this
# list and the rule (the hero's hp stops at 1, combat.Battle floor) are ours. The prologue 50116: "YOU WONT DIE even if
# you do die" (the colossus), "if you happen to die, you will just get Full Healed by Azillian Knights" (the tyrant;
# walkthrough_guide.txt L44, L47; its table heals the hero, m50116).
UNDYING_MISSIONS = (10358, 10233, 10234, 10361, 10362, 10235,   # + Lunawing I / II, New Hampton Castle (MISSIONS-WIRING G8)
                    50116)


def is_mission(spot):
    """A spot whose room is built from its zone file: a Battle spot (a quest's mission map, e.g. 10358), or an
    extreme (Spot_Type Raid, contents PVE_EXTREME: 20349, 20501, 20503), which the client opens for a lone player
    through the solo room (0x3f48) and the original made clearable by one player in February 2020 (OFFICIAL-NOTES;
    the party builder's report, 2026-11-05), or a 16-player raid (Spot_Type Raid, contents PVE_RAID: 20950, 20951;
    20952 has no zone file), which only a party's room starts (party.start). A raid runs on the rules of every room
    whose script is not shipped (mission_plan); its revive rules and reward dummies: party.py; its checkpoints and
    binding: raid.py."""
    from . import tables, zone
    row = tables.by_id("spottable").get(str(spot))
    kind = bool(row) and (row.get("Spot_Type") == "Battle" or
                          (row.get("Spot_Type") == "Raid"
                           and row.get("Spot_Contents_Type") in ("PVE_EXTREME", "PVE_RAID")))
    return kind and zone.available(spot)


def start_control_mode(spot, difficulty=0):
    """ActControlChangeControlMode at room start (MISSIONS-WIRING G7, ours from spottable): 1 (direct control) for a
    mission that takes no troops on this difficulty (Limit_Troop_<n> 0, TacticsSkillCheck False) and hands none over
    at the start (no players_troop in the zone but those its table hands later, HAND_LATER), else 0 (tactical): Grey
    Fog 10358, 10317, 20302, 20319, 20322, 10237, 10356, the prologue 50116 (its archers 12012 come with Brenon's
    "take the archers to the battlements"; the tape, part 1 4:07-4:31, walks the hero with W A S D)."""
    from . import tables, zone
    if not is_mission(spot):
        return 0
    row = tables.by_id("spottable").get(str(spot)) or {}
    limit = row.get(f"Limit_Troop_{difficulty + 1}", "-")
    limit = limit if limit.isdigit() else row.get("Limit_Troop", "-")
    if (limit.isdigit() and int(limit) > 0) or row.get("TacticsSkillCheck") == "True":
        return 0
    names, later = force_names(spot), director.hand_later(spot)
    if any(players_troop(spot, t, names) and t["TroopID"] not in later       # troops handed over at the start (G5)
           for t in zone.for_spot(spot)["NPCTroopInfoData"]):
        return 0
    return 1


def mission_start(spot):
    from . import zone
    pts = zone.for_spot(spot)["PlayerStartPointInfoData"] if zone.available(spot) else []
    if pts and pts[0]["StartPointInfoData"]:
        pt = pts[0]["StartPointInfoData"][0]
        return (round(pt["PosX"]), 0, round(pt["PosZ"]))
    return None


def is_field(spot):
    from . import tables
    row = tables.by_id("spottable").get(str(spot))
    return bool(row) and row.get("Spot_Type") in FIELD_TYPES


def room_kind(spot):
    """What a room is, for the journal: a mission, a field, else a bare battle room (the test enemy)."""
    return "mission" if is_mission(spot) else "field" if is_field(spot) else "battle"


def start_pos(s):
    """Where the hero enters: a measured battle start point, or on a field the character's saved position (the field
    is the same map the town state walked)."""
    spot = s.data["spot"]
    if spot in SPAWN_POS:
        return SPAWN_POS[spot]
    if is_mission(spot):
        return mission_start(spot)
    c = hero_char(s)
    if is_field(spot) and c.get("spot") == spot and c.get("pos"):
        return tuple(c["pos"])
    return (0, 0, 0)
# Mission-script actions: S2C 0x5087 = u32 action id + u32 args (MissionScriptMsgHandler @ 0x140b2b280;
# ids from re/actions.txt, args read by the script-arg reader 0x1406b4ff0 = plain u32).
S2C_SCRIPT_ACTION = 0x5087
# The client answers questions (planning/client/mission_script.md §5.1, §5.2): a condition S2C 0x5086 (0x140b2afc0: u32
# condition, u32 serial, u8 tag, u32 key, its arguments) is answered at once by C2S 0x5089 (ReturnCondition 0x140b2f0b0,
# 9 bytes, condition_answer); a key prompt S2C 0x50c1 (0x140b08c90: u32 InputEvent, u8 id, u32 value; 9 bytes, fewer
# crash) by C2S 0x50c2 (u8 id) when the player presses the key; S2C 0x50c3 (u8 id) takes one down
S2C_CONDITION, C2S_CONDITION = 0x5086, 0x5089
S2C_KEY_PROMPT, C2S_KEY_PROMPT, S2C_KEY_PROMPT_OFF = 0x50c1, 0x50c2, 0x50c3
CONDITION_MIX = 0x1c6f034d       # ReturnCondition's mask (0x140b2f13d)
C2S_TROOP_SYNC = 0x50b0          # the host's troop positions (troop_sync)
ACT_RENDER_START = 0xd322        # ActSystemRenderStart (0x140cbcde0): loading phase 6 -> battle state; only valid then
ACT_FADE = 0xd2fa                # ActSystemFade(seconds, ?, mode 1 = in)
ACT_ENABLE_INPUT = 0xcb2a        # ActControlSetEnableInput(on)
ACT_CONTROL_MODE = 0xcb3e        # ActControlChangeControlMode(mode <= 1) -> 0x140b5ece0: 0 ControlModeStrategy (tactical
                                 # view, click-to-move orders), 1 ControlModeEngage (direct hero control)
ACT_ENABLE_ALL_TROOPS = 0xea74   # ActTroopSetEnableAllTroops(1, on) -> 0x140ba3400 -> Troop::Enable (shows NP troops)
# The class kit a new hero wears: hero.starter_kit (herotable %Inventory). Class ids follow createcharacter.csv HeroId:
# 0 Glen, 1 Olivia, 2 Druid, 3 Isabella, 4 Regnier, 5 Helena. With no items equipped the hero has no meshes (invisible).
# Hero abilities per class, sent in the 0x3f50 leader's ability list (entries: u8 level, u32 ability id; the client
# stores (slot = index, id, level) at troop info +0x78, 0x140d0a370). Without them a click queues a combo key
# (0x140a48310) but no attack starts. heroskillbook AbilityBook rows with HeroLevel 1 that are basic attacks (평타),
# the right-click chain (우클릭) or AutoLearn; names from abilitytypeinfo. Class ids as above.
STARTER_ABILITIES = {
    0: (164, 165, 166, 167, 32, 77, 114, 1, 111, 62, 15, 9, 120),
    1: (1101, 1102, 1103, 1104, 984, 951, 952, 953, 904, 905, 915, 917, 919, 921, 916, 907, 1062, 950, 1028, 1134,
        908, 945, 935, 909),
    2: (1299, 1300, 1301, 1302, 1303, 1201, 1200, 1209, 1204, 1206, 1216, 1272),
    3: (443, 444, 445, 446, 447, 321, 300, 374, 375, 319, 304, 305, 336),
    4: (803, 804, 805, 806, 623, 600, 719, 720, 618, 622, 604, 643, 608, 633, 616, 738),
    5: (1520, 1521, 1522, 1523, 1524, 1501, 1506, 1272),
}
# Hero leader stats per class, {stat id: value}, sent in the troop-state stat block (0x50b8 / 0x50cb, see
# write_troop_state). Stat ids are the client's stat enum (0x1434a74e0, from HP_MAX = 0): 2 HP_RECOVERY,
# 3 STAMINA_MAX, 4 STAMINA_RECOVERY, 5 STAMINA_REDUCE, 13 RANGE_SIGHT, 14 MAX_MOVE_SPEED, 15/16 ATTACK_PHYSICAL/MAGICAL,
# 25/26 CRITICAL_*, 27/28 CRITICALPROB_*, 31 ACCURACY, 32 MISS, 39 ATTACK_SPEED, 41 EVADE_REDUCE, 42 GUARD_REDUCE,
# 79 CURRENT_STAMINA. Values: herotable (BASESTAMINA -> 3 and 79). Without stat 14 the hero's speed is 0 (leader data
# +0x3d4, read by vt+0x358 0x140a044c0) and he runs in place.
HERO_STATS = {
    0: {2: 3, 3: 600, 4: 10, 5: 100, 13: 7500, 14: 800, 15: 3, 25: 750, 26: 750, 27: 50, 28: 50, 39: 100, 41: 900,
        42: 700, 79: 600},
    1: {2: 2, 3: 600, 4: 10, 5: 100, 13: 12500, 14: 900, 15: 2, 16: 2, 25: 1000, 26: 1000, 27: 50, 28: 50, 31: 100,
        32: 100, 39: 100, 41: 900, 42: 700, 79: 600},
    2: {2: 1, 3: 300, 4: 10, 5: 100, 13: 10000, 14: 800, 15: 2, 16: 4, 25: 500, 26: 500, 27: 50, 28: 50, 39: 100,
        41: 900, 42: 700, 79: 300},
    3: {2: 2, 3: 300, 4: 10, 5: 100, 13: 10000, 14: 850, 15: 3, 16: 3, 25: 500, 26: 500, 27: 50, 28: 50, 39: 100,
        41: 900, 42: 700, 79: 300},
    4: {2: 4, 3: 600, 4: 10, 5: 100, 13: 7500, 14: 750, 15: 3, 16: 2, 25: 500, 26: 500, 27: 50, 28: 50, 39: 100,
        41: 900, 42: 700, 79: 600},
    5: {2: 1, 3: 300, 4: 10, 5: 100, 13: 7500, 14: 800, 15: 2, 16: 4, 25: 500, 26: 500, 27: 50, 28: 50, 39: 100,
        41: 900, 42: 700, 79: 300},
}
# Battle-start requests answered with empty data (planning/todo/REQUEST-MAP-PLAN.md R0). Request -> (reply, body).
EMPTY_REPLIES = {                        # (0x513d, the revive counts and bans, is revive_bans)
    0x5146: (0x5147, bytes(2)),          # 0x140c55ad0: u8 n, n * 9, then 0x14085f800: u8 n, n * 8
    0x3e40: (0x3e41, bytes(6)),          # PvP room lists (they may come on this connection): empty
    0x3e63: (0x3e64, bytes(6)),
    0x112c: (0x112d, bytes(4)),          # /escape check in a field room: go ahead (then 0x10b5)
    0x511e: (0x511f, bytes(1)),          # PvP spots only (specs/battle.md)
    0x512c: (0x512d, bytes.fromhex("01000000000000")),   # hero talent pick: PvP / test spots only
    0x512e: (0x512f, bytes(1)),
}
MODE_PVE = 0                     # header +7: (b & 0xfc)==0 && b != 1 -> game state 4 (Loading), else 3


def make(state, port):
    role = Role("game", port, state)
    role.empty_replies(EMPTY_REPLIES)
    from . import changetroop, party
    changetroop.make(role, state)                # sub 0x78 on %Point spots: troop change, upgrade, timed revival,
                                                 # summon, withdraw (0x50ec-0x512a; changetroop.py)
    # The sync-mode action request 0x50db and the 60 s timer 0x50fe: nothing waits on them. (0x5056, the hit-reaction
    # sync, carries the NP troops' melee blows: combat.on_hit_sync; 0x50ab says a troop is ready: troop_bound.)
    role.ignore(0x50db, 0x50fe)

    @role.on(C2S_TROOP_BOUND, quiet=True)
    def bound(s, pkt):
        troop_bound(s, struct.unpack_from("<H", pkt.rest(), 0)[0])

    @role.on(C2S_TROOP_SYNC, quiet=True)
    def troop_sync(s, pkt):
        """The host's troop positions (0x50b0, every 1.5 s solo; requests/battle.md): the hero's record (uid 0) keeps
        s.data["hero_pos"] (combat.hero_moved: the wake by area, the revive point, the enemy pointer).
        Nothing is sent back (the client expects no reply)."""
        flags = {}
        places = sync_positions(pkt.rest(), flags)
        combat.troop_states(s, flags)                    # each record's state class: the synastry row (A7)
        mine = (s.data.get("plan") or {}).get("hand", ())
        s.data["troop_pos"] = {u: p for u, p in places.items() if u in mine}
        s.data.setdefault("last_pos", {}).update(places)  # where each troop was last seen: its loot lies there
        director.on_troops(s, places)                    # a routed ally at its exit bound leaves (Grey Fog's 도망)
        director.on_arrive(s, places)                    # a table's "arrive" steps (Flamegrass's orc column)
        if 0 in places:
            combat.hero_moved(s, places[0])
        elif s.data["troop_pos"]:
            on_hero_position(s)                          # the player's troop moved (the Lunawing he flies)
    # specs/battle.md: relays for other players (the client knows it is alone: +0xb1), dev console / debug requests,
    # invasion, capture and raid paths, a background checksum.
    role.on(combat.C2S_CHARGE_STEP, quiet=True)(combat.on_charge_step)   # a charged skill's stage (0x5062)
    role.ignore(0x504c, 0x5042, 0x5046, 0x5049, 0x504a, 0x504d, 0x5051, 0x5054, 0x506f, 0x5081, 0x5092,
                0x509f, 0x50b1, 0x50b6, 0x50bc, 0x50c4, 0x50c7, 0x50c9, 0x50cd, 0x50d3, 0x50d4, 0x50dc, 0x50de,
                0x50df, 0x50e0, 0x50e1, 0x50e5, 0x50ea, 0x50ff, 0x5112, 0x513a, 0x513f)

    role.on(0x50e8)(combat.on_field_return)

    @role.on(C2S_CONDITION, quiet=True)
    def condition(s, pkt):
        """The answer to a condition the director asked (condition_answer); the script console's commands, which
        share the id, are dropped."""
        answer = condition_answer(pkt.rest())
        if answer is not None:
            director.on_condition(s, *answer)

    @role.on(C2S_KEY_PROMPT)
    def key_prompt(s, pkt):
        director.on_prompt(s, pkt.u8())

    @role.on(C2S_FORCE_LANDED)
    def force_landed(s, pkt):
        b = pkt.rest()
        if len(b) < 3:
            log.warning("force change ack not understood: %s", b.hex())
            return
        troop_landed(s, obf.dec_u16(b[1:3]), obf.T1[b[0]] & 1)

    @role.on(C2S_GAME_LOGIN)
    def game_login(s, pkt):
        char_id = pkt.u32()                     # the chosen character's id (it matched the account's while the
        unk = pkt.u16()                         # account had one character; live 2026-09-30 a second one failed)
        spot = pkt.u32()                        # echo of the u32 world sent in 0x3f41 (we put the spot there)
        s.data["account"], s.data["char"] = state.char_by_id(char_id)     # the hero every reader plays (hero_char)
        getattr(state, "game_sessions", {})[s.data["account"]["id"]] = s
        s.data["spot"] = spot
        s.data["difficulty"] = mission_difficulty(s.data["char"], spot)
        log.info("game login character=%d account=%d unk=0x%x spot=%d", char_id, s.data["account"]["id"], unk, spot)
        net.journal("room", ev="enter", spot=spot, difficulty=s.data["difficulty"], kind=room_kind(spot))
        s.send(Writer(S2C_GAME_LOGIN_RES).u16(0))
        party.take_aipc(s, state)                # the AI PCs a party's start left on the world session (party.py)
        send_start_header(s, spot)

    @role.on(C2S_LOAD_PROGRESS)
    def load_progress(s, pkt):
        pct = pkt.u8()
        log.info("load progress %d%%", pct)
        s.send(Writer(S2C_LOAD_PROGRESS).u32(MY_SLOT).u8(pct))
        if pct >= 100 and not s.data.get("started"):
            s.data["started"] = True
            s.data["started_at"] = time.monotonic()      # the mission clock the grade reads (mission_won)
            net.journal("room", ev="start", spot=s.data["spot"])
            snapshot(s, first=True)
            s.send(Writer(S2C_HOST_CHANGE).u16(MY_SLOT))
            s.send(Writer(S2C_ALL_LOADED).obool(False))
            send_actions(s, [ACT_RENDER_START])
            # the state switch lands on a later frame; the rest goes to the battle state
            s.later(1.0, lambda: (send_enter_cell(s), send_mission_troop_info(s), party.place_ai(s),
                                  status.room_start(s),
                                  changetroop.start(s),          # a %Point spot's Battle Points (nothing elsewhere)
                                  send_actions(s, [director.ACT_CAMERA_RESTORE_DEFAULT],
                                               [ACT_FADE, 1, 0, 1], [ACT_ENABLE_INPUT, 1])))
            battle = s.data["battle"] = combat.Battle()
            s.data["hit_callbacks"] = (send_troop_hp, troop_down)    # for hits the server starts itself (combat.dot_hit)
            char = hero_char(s)
            battle.add_hero(0, hero_max_hp(s), c=hero_combatant(char))
            deck_enters(s, state, battle)
            party.ai_enters(s, battle)                   # a party's AI PCs, on the player's team (party.py)
            # as the 0x3f4f struct started them, with the deck troops that take part
            s.data["pools"] = pools_for(char, s.data["spot"], (s.data.get("deck") or {}).values())
            from . import hero
            s.data["pools"]["hp_rec"] = hero.regen_tick(char)     # the 3 s tick in combat (census P7)
            s.data["kit"] = skills.battle_abilities(char)
            combat.start_regen(s)
            if s.data["spot"] in UNDYING_MISSIONS:
                battle.troops[0]["floor"] = 1
            if is_field(s.data["spot"]) or is_mission(s.data["spot"]):     # troops from the zone file
                c = hero_char(s)
                s.later(3.0, lambda: (spawn_zone_troops(s), send_zone_props(s, s.data["spot"], c),
                                      send_actions(s, [ACT_ENABLE_ALL_TROOPS, 1, 1],
                                                   [ACT_CONTROL_MODE, start_control_mode(s.data["spot"],
                                                                                        s.data.get("difficulty", 0))])))
                return
            x, y, z = start_pos(s)
            s.later(3.0, lambda: (send_np_troop(s, 1, TEST_ENEMY[0], (x + 1500, y, z), TEST_ENEMY[1], TEST_ENEMY[2]),
                                  send_actions(s, [ACT_ENABLE_ALL_TROOPS, 1, 1], [ACT_CONTROL_MODE, 0]),
                                  send_spawn_ai(s, 1)))
            battle.add_np(1, TEST_ENEMY[1] // TEST_ENEMY[2], TEST_ENEMY[2],
                          c=combat.np_combatant(TEST_ENEMY[0], NP_TEAM))

    @role.on(combat.C2S_COMBAT_MODE)
    def combat_mode(s, pkt):
        combat.on_combat_mode(s, pkt)

    @role.on(combat.C2S_ENGAGE)
    def engage(s, pkt):
        combat.on_engage(s, pkt)

    @role.on(combat.C2S_ABILITY_EXECUTE, quiet=True)
    def ability_execute(s, pkt):
        combat.on_ability_execute(s, pkt, send_troop_hp, troop_down, props_hit)

    @role.on(combat.C2S_CAST_DONE)
    def cast_done(s, pkt):
        combat.on_cast_done(s, pkt)

    @role.on(combat.C2S_ENGAGE_CLEAR)
    def engage_clear(s, pkt):
        combat.on_engage_clear(s, pkt)

    @role.on(combat.C2S_USE_ABILITY)
    def use_ability(s, pkt):
        combat.on_use_ability(s, pkt)

    @role.on(combat.C2S_HIT, quiet=True)
    def hit(s, pkt):
        combat.on_hit(s, pkt, send_troop_hp, troop_down, props_hit)

    @role.on(combat.C2S_HIT_SYNC, quiet=True)
    def hit_sync(s, pkt):
        combat.on_hit_sync(s, pkt, send_troop_hp, troop_down)

    @role.on(combat.C2S_HERO_HIT, quiet=True)
    def hero_hit(s, pkt):
        combat.on_hit(s, pkt, send_troop_hp, troop_down, props_hit)

    @role.on(combat.C2S_AREA_DAMAGE, quiet=True)
    def area_damage(s, pkt):
        combat.on_area_damage(s, pkt, send_troop_hp, troop_down)

    @role.on(C2S_PROP_CAST)
    def prop_cast(s, pkt):
        b = pkt.rest()
        if len(b) < 6:
            log.warning("prop cast not understood: %s", b.hex())
            return
        uid, prop_id = struct.unpack_from("<H", b)[0], obf.dec_u32(b[2:6])
        why = prop_refusal(s, prop_id)
        if why:
            log.info("prop %d cast refused: %s", prop_id, why)
            s.send(Writer(S2C_PROP_CAST).raw(obf.u32(prop_id)).u16(PROP_REFUSED).u16(uid))
            return
        s.data.setdefault("prop_casts", {})[prop_id] = uid
        s.send(Writer(S2C_PROP_CAST).raw(obf.u32(prop_id)).u16(0).u16(uid))

    @role.on(C2S_PROP_CAST_DONE)
    def prop_cast_done(s, pkt):
        b = pkt.rest()
        if len(b) < 6:
            log.warning("prop cast end not understood: %s", b.hex())
            return
        prop_id = obf.dec_u32(b[2:6])
        uid = s.data.get("prop_casts", {}).pop(prop_id, None)
        p = zone_prop(s.data["spot"], prop_id)
        if uid is None or p is None:                    # answer anyway: without a 0x5097 the client's prop manager
            log.warning("prop %d cast end without a cast", prop_id)   # stays in state 3 and ignores every later F
            s.send(Writer(S2C_PROP_CAST_DONE).u16(struct.unpack_from("<H", b, 0)[0]).raw(obf.u32(prop_id)).u16(1)
                   .raw(obf.u40(0)).i32(0).u8(0).u8(0))   # (planning/client/props_loot.md, 0x5096): refused
            return
        s.data.setdefault("prop_states", {})[prop_id] = PROP_ON
        row = prop_row(p["SmartPropTypeID"]) or {}
        loot = box_loot(row)                            # an item box: the loot window lists these; 0x5098 takes them
        if loot:
            s.data.setdefault("box_loot", {})[prop_id] = {i: item for i, item in enumerate(loot)}
        w = Writer(S2C_PROP_CAST_DONE).u16(uid).raw(obf.u32(prop_id)).u16(0).raw(obf.u40(0)).i32(PROP_ON)
        w.u8(len(loot))
        for i, (code, n) in enumerate(loot):
            w.raw(obf.u16(n)).raw(obf.u32(code)).raw(obf.u16(i))
        s.send(w.u8(0))
        from . import quest
        qids = quest.on_prop(s, state, p["SmartPropTypeID"]) or []
        if ambush_troop(row) is not None:               # the table names the troop the prop calls
            spawn_prop_ambush(s, p, row)
        else:
            spawn_prop_targets(s, p, qids)
        back = prop_back_after(row)
        if back is not None and not loot:              # an item box's time starts when its window closes (prop_state)
            s.later(back, lambda: prop_return(s, p))
        rules.on_prop(s, p)                             # the Goblin Nest's entrance starts its trial
        director.on_used(s, p["SmartPropID"])

    @role.on(C2S_PROP_CANCEL)
    def prop_cancel(s, pkt):
        b = pkt.rest()
        if len(b) >= 4:
            s.data.get("prop_casts", {}).pop(obf.dec_u32(b[0:4]), None)

    @role.on(C2S_BOX_ITEM)
    def box_item(s, pkt):
        b = pkt.rest()
        if len(b) < 12:
            return
        code, box, index, n = obf.dec_u32(b[0:4]), obf.dec_u32(b[4:8]), obf.dec_u16(b[8:10]), obf.dec_u16(b[10:12])
        entries = s.data.get("box_loot", {}).get(box, {})
        if entries.get(index) != (code, n):
            log.warning("box %d item %d x%d at %d: not in the box (%s)", box, code, n, index, entries)
            s.send(Writer(S2C_BOX_ITEM).raw(obf.u32(box)).obool(False).u16(PROP_REFUSED))
            return
        from . import world
        del entries[index]
        net.journal("loot", ev="pick", code=code, name=items.name(code), n=n, box=box)
        world.add_item(s, state, code, n)              # the bag refresh; ItemGain moves
        s.send(Writer(S2C_BOX_ITEM).raw(obf.u32(box)).obool(False).u16(0))
        log.info("box %d: took %d x%d", box, code, n)

    @role.on(C2S_BOX_GOLD)
    def box_gold(s, pkt):
        b = pkt.rest()
        if len(b) < 11:
            return
        box = obf.dec_u32(b[7:11])
        s.send(Writer(S2C_BOX_GOLD).raw(obf.u32(box)).u16(PROP_REFUSED))   # boxes carry no gold (0 is sent)

    @role.on(C2S_PROP_STATE)
    def prop_state(s, pkt):
        b = pkt.rest()
        if len(b) < 10:
            return
        new, prop_id = struct.unpack_from("<I", b, 0)[0], obf.dec_u32(b[6:10])
        states = s.data.setdefault("prop_states", {})
        was, states[prop_id] = states.get(prop_id), new
        looted = s.data.get("box_loot", {}).pop(prop_id, None) is not None   # what was left in it is gone with it
        s.send(Writer(S2C_PROP_STATE).u16(0).u32(new).raw(obf.u32(prop_id)))
        p = zone_prop(s.data["spot"], prop_id)
        back = prop_back_after(prop_row(p["SmartPropTypeID"]) or {}) if p else None
        if looted and was == PROP_ON and back is not None:
            # an item box's Regen_Time counts from its loot window's close (AC3 item 14, ours: timed from the cast's
            # end, a box left open came back while still open, and its late close marked it opened for good)
            s.later(back, lambda: prop_return(s, p))

    role.on(combat.C2S_TROOP_CAST)(combat.on_troop_cast)
    role.on(combat.C2S_COMMIT)(lambda s, pkt: combat.on_commit(s, pkt))

    @role.on(C2S_UNCHANT)
    def unchant(s, pkt):
        b = pkt.rest()
        if len(b) >= 6:
            s.send(Writer(S2C_UNCHANT).raw(b[:6]))
            combat.end_statuses(s, obf.dec_u32(b[0:4]), struct.unpack_from("<H", b, 4)[0])

    @role.on(C2S_AREA_END)
    def area_end(s, pkt):
        b = pkt.rest()
        if len(b) >= 2:
            s.send(Writer(S2C_AREA_END).raw(b[:2]))

    role.on(status.C2S_AREA_APPLY)(lambda s, pkt: status.on_area_apply(s, pkt))
    role.on(status.C2S_REMOVE)(lambda s, pkt: status.on_remove(s, pkt))

    @role.on(C2S_CUTSCENE)
    def cutscene(s, pkt):
        b = pkt.rest()
        if len(b) >= 5 and obf.T1[b[4]] & 1:            # a skip waits for the room's answer
            s.send(Writer(S2C_CUTSCENE).raw(b[:4]))

    @role.on(C2S_MARK_TROOP)
    def mark_troop(s, pkt):
        b = pkt.rest()
        if len(b) >= 9:
            s.send(Writer(S2C_MARK_TROOP).raw(b[:9]))

    @role.on(C2S_MARK_GROUND)
    def mark_ground(s, pkt):
        b = pkt.rest()
        if len(b) >= 8:
            s.send(Writer(S2C_MARK_GROUND).raw(b[:8]))

    @role.on(C2S_PAUSE)
    def pause(s, pkt):
        on = pkt.u8() == 1
        s.send(Writer(S2C_PAUSE).u8(0).u8(obf.T2[1 if on else 0]).cstr(""))

    @role.on(C2S_REVIVE_CAMP)
    def revive_camp(s, pkt):
        t = s.data.get("battle") and s.data["battle"].troops.get(0)
        if not t or t["hp"] > 0:
            s.send(Writer(S2C_REVIVE_CAMP).u16(1))
            return
        x, y, z = revive_point(s)
        s.send(Writer(S2C_REVIVE_CAMP).u16(0).u16(0).f32(z).f32(x))
        revive_hero(s, t, (x, y, z))

    @role.on(C2S_REVIVE_HERE)
    def revive_here(s, pkt):
        """The death window's revive in place (0x50f4): refused where the spot's %Revival row allows none
        (IMPOSIBLE: 0x7412) or its limit is used up (0x7411); a revival item the client names pays for it, else the
        Cubic price (revive_cost; the free camp revive is 0x50d6's). The troop it names (u16 +0): 0 the hero, else a
        wiped player-owned troop, including one handed over by the mission (the HUD's Resurrection button over
        its slot, priced by troop_revive_cost), brought
        back by revive_troop; one revivals-used count for both (the 0x50f5 reply's). Under a raid's revive ban
        (party.ban_left: 10 s from the fall, spottable %Revival PVE_RAID) it is refused with 0x7413, the code of the
        client's own text for the ban (0xd03d)."""
        from . import party, raid, world
        b = pkt.rest()
        uid = struct.unpack_from("<H", b, 0)[0] if len(b) >= 2 else 0
        battle = s.data.get("battle")
        t = battle and battle.troops.get(uid)
        deck = (s.data.get("deck") or {}).get(uid) if uid else None
        wiped = t and not t["hero"] and not any(t["units"]) and not t.get("leader")
        if len(b) < 6 or not t or (t["hp"] > 0 if uid == 0 else not (status.players(s, uid) and wiped)):
            s.send(Writer(S2C_REVIVE_HERE).u16(REVIVE_NOT_NOW).u32(s.data.get("revivals", 0)))
            return
        goods, limit = revival(s.data.get("spot"), s.data.get("difficulty", 0))
        limit = raid.limit(s, limit)                     # an armed checkpoint's own (raid.py)
        refusal = (REVIVE_NOT_HERE if goods == "IMPOSIBLE" else
                   REVIVE_NOT_NOW if party.ban_left(s, uid) > 0 else
                   REVIVE_NONE_LEFT if 0 <= limit <= s.data.get("revivals", 0) else None)
        item = obf.dec_u32(b[2:6])
        if refusal is None and item != 0xFFFFFFFF:
            # ReqTroopRevival0x1406900e0 asks the bag for ConsumeItemType0x24
            # (COUPON_REVIVAL). A missing or unrelated item cannot pay for a revive.
            coupon = items.row(item) or {}
            owned = any(it.get("code") == item and it.get("count", 0) > 0
                        for it in hero_char(s).get("bag", ()))
            if coupon.get("ConsumeItemType") != "COUPON_REVIVAL" or not owned:
                refusal = REVIVE_NOT_NOW
        if refusal is None and item == 0xFFFFFFFF and goods == "CUBIC":
            c = hero_char(s)                              # (spend_cubic reads s.data["char"])
            if free_revives(c):                           # the day's free ones first (census ECONOMY J5)
                c["free_revives"]["used"] += 1
                state.save()
                s.send(free_revives_packet(c))
            else:
                price = revive_cost() if uid == 0 else troop_revive_cost(deck)
                refusal = None if world.spend_cubic(s, state, price) else world.CUBIC_SHORT
        if refusal is not None:
            s.send(Writer(S2C_REVIVE_HERE).u16(refusal).u32(s.data.get("revivals", 0)))
            log.info("revive here refused (%#x): %s, %d of %d used", refusal, goods, s.data.get("revivals", 0), limit)
            return
        if item != 0xFFFFFFFF:
            world.remove_item(s, state, item, 1)
        s.data["revivals"] = s.data.get("revivals", 0) + 1
        s.send(Writer(S2C_REVIVE_HERE).u16(0).u32(s.data["revivals"]))
        if uid:
            revive_troop(s, uid, t)
        else:
            revive_hero(s, t, s.data.get("hero_pos") or start_pos(s))

    @role.on(C2S_REVIVE_COUNT)
    def revive_count(s, pkt):
        """The battle HUD's init (HUDRevivalSystem 0x14068e280, every room): the revivals this player has used in
        the room, the count revive_here keeps, so the revive confirm (0x14068f0b0) checks the spot's limit against
        it (text 0xd03d when used up). Under 4 bytes the reply handler crashes."""
        s.send(Writer(S2C_REVIVE_COUNT).u32(s.data.get("revivals", 0)))

    @role.on(C2S_REVIVE_BANS)
    def revive_bans(s, pkt):
        """The battle HUD's init outside the fields (0x14068e280): the other players' revive counts (none: one
        player; his own is 0x513c's) and the revive bans still running in the room (party.bans: a raid's 10 s from
        each fall, which the HUD otherwise starts itself, 0x14068e990), so a HUD that starts again counts them
        down from where they are. No ban: the four zero bytes sent before this handler."""
        from . import party
        left = party.bans(s)
        w = Writer(S2C_REVIVE_BANS).u16(0).u16(len(left))
        for uid, ms in left:
            w.u16(uid).i32(ms)
        s.send(w)

    @role.on(C2S_MISSION_LEAVE)
    def mission_leave(s, pkt):
        leave_mission(s, state)

    @role.on(C2S_REWARD_CARD)
    def reward_card(s, pkt):
        open_card(s, s, state, pkt.rest())

    @role.on(C2S_DROP_PICK)
    def drop_pick(s, pkt):
        pick_drop(s, s, state, pkt.rest())

    @role.on(C2S_GOLD_PICK)
    def gold_pick(s, pkt):
        b = pkt.rest()
        if len(b) < 6:
            return
        uid, drop_id = struct.unpack_from("<Hi", b, 0)
        gold = s.data.get("gold_drops", {}).pop(drop_id, 0)
        if gold:
            from . import world
            net.journal("loot", ev="pick", gold=gold, drop=drop_id)
            world.add_gold(s, state, gold)
        s.send(Writer(S2C_GOLD_PICK).u16(0).u16(uid).i32(drop_id))    # an unknown id: 0 clears the stray pile

    @role.on(C2S_GOLD_ALL)
    def gold_all(s, pkt):
        piles = s.data.pop("gold_drops", {})
        gold = sum(piles.values())
        if gold:
            from . import world
            net.journal("loot", ev="pick", gold=gold, drop=sorted(piles))
            world.add_gold(s, state, gold)
        s.send(Writer(S2C_GOLD_ALL).u16(0))

    @role.on(C2S_LOOT_OWNER)
    def loot_owner(s, pkt):
        b = pkt.rest()
        if len(b) >= 4:
            s.send(Writer(S2C_LOOT_OWNER).u16(1).raw(b[:4]))

    def props_hit(s, ids):
        """Hits on attackable props (TYPE_ATTACK): HP_AT, broken after HC_AT hits (inferred: HC = hit count), back
        after Regen_Time seconds; a break counts for PropKill."""
        hp = s.data.setdefault("prop_hp", {})
        states = s.data.setdefault("prop_states", {})
        for prop_id in ids:
            p = zone_prop(s.data["spot"], prop_id)
            row = prop_row(p["SmartPropTypeID"]) if p else None
            if not row or "HP_AT" not in row or states.get(prop_id) == PROP_BROKEN:
                continue
            top = int(row["HP_AT"]) if row["HP_AT"].isdigit() else 1
            left = max(0, hp.get(prop_id, top) - max(1, top // max(1, int(row["HC_AT"]) if row["HC_AT"].isdigit() else 1)))
            hp[prop_id] = left
            s.send(Writer(S2C_PROP_HP).u16(1).raw(obf.u32(prop_id)).i32(left).i32(top))
            if left:
                continue
            states[prop_id] = PROP_BROKEN
            s.send(Writer(S2C_PROP_DELETE).u16(1).raw(obf.u32(prop_id)))
            log.info("prop %d (type %s) broken", prop_id, p["SmartPropTypeID"])
            open_cleared_walls(s, p)
            rules.on_prop_broken(s, p)                  # Grey Hampton's relic device: the storm's clock
            director.on_broken(s, prop_id)              # a table's "broken" step (Flamegrass's barricade)
            from . import quest
            quest.count(s, state, "PropKill", "ID1", {str(p["SmartPropTypeID"])})
            if (row.get("Regen_Time") or "-").isdigit():
                s.later(max(1.0, float(row["Regen_Time"])), lambda p=p, top=top: prop_mend(s, p, top))

    def kill_feed(s, uid, killer):
        """0x50fd naming the troop whose hit felled uid (B7 / I9; it was always 0, the hero). The client (0x140d07920)
        drops a killer it does not know or one equal to the victim, and its three readers (the feed 0x140871fe0, the
        chat line 0x140dddb20, the per-player tally 0x140575220) all skip a victim uid above 9999: a zone troop's fall
        shows nothing; the hero's (victim 0) prints "The hero is dead." (text 0x2726) [R]. No known killer: none."""
        if killer is not None and killer != uid:
            s.send(Writer(S2C_KILL_FEED).u16(killer).u16(uid).u8(0).obool(True))

    def troop_down(s, uid):
        """A wiped troop: a zone troop counts for NPNameKill quests and comes back after its zone RespawnTime
        (read as seconds; inferred); the fallen hero gets the death window with the revive buttons. The kill feed names
        the troop that felled it; kill exp, the banner and a commander's SP go to the player when his side fought it
        (status.fights_player; the killer one of his own counts too)."""
        killer = s.data.get("killed_by", {}).pop(uid, None)
        from . import party, raid
        party.on_troop_down(s, uid)                  # a raid's revive ban starts for a player's troop (party.py)
        if uid in (s.data.get("deck") or {}):
            wiped = s.data.setdefault("deck_wiped", set())
            if uid not in wiped:                         # one wipe, however many hits report it: the result window's
                wiped.add(uid)                           # death count (the tape: 20305's 31, New Hampton's 5)
                s.data["troop_wipes"] = s.data.get("troop_wipes", 0) + 1
            deck_troop_down(s, state, uid, killer)
            kill_feed(s, uid, killer)
            return
        hero_t = s.data.get("battle") and s.data["battle"].troops.get(uid)
        if hero_t and hero_t.get("hero"):
            if not hero_t.get("down"):
                hero_t["down"] = True
                net.journal("down", spot=s.data.get("spot"), troop=uid, hero=True, killer=killer)
                s.data["hero_deaths"] = s.data.get("hero_deaths", 0) + 1     # each lowers the mission grade one step
                kill_feed(s, uid, killer)
                cooldown = hero_revival_cooldown(s.data.get("spot"))
                s.send(Writer(S2C_DEATH_WINDOW).u8(min(255, cooldown)))
                if cooldown:
                    token = s.data["hero_deaths"]
                    s.later(cooldown, lambda: cooldown_revival(s, hero_t, token))
                raid.on_hero_down(s)                     # no resurrection left: the closest checkpoint (raid.py)
                from . import world
                world.wear_down(s, state, "DIE")
            return
        t = s.data.get("zone_troops", {}).get(uid)
        if t is None:
            return
        raid.on_troop_down(s, state, t)              # a raid's checkpoint arms as its boss falls (raid.py)
        credited = status.players(s, killer) or status.fights_player(s, uid)
        if credited:                                 # a %Point spot's Battle Points for the kill (changetroop.py)
            from . import changetroop
            changetroop.on_kill(s, difficulty_troop(t["TroopTableID"], s.data.get("difficulty", 0)),
                                difficulty_leader(t.get("NPLeaderID"), s.data.get("difficulty", 0)))
        net.journal("down", spot=s.data.get("spot"), troop=uid, force=t.get("ForceNum"), table=t["TroopTableID"],
                    killer=killer, credited=credited)
        from . import quest
        quest.on_kill(s, state, t["TroopTableID"], leader=t.get("NPLeaderID"))
        from . import events                             # a boost event that is on (events.ACTIVE_BOOST): exp, gold
        exp = events.boosted("hero_exp", kill_exp(s.data["char"], difficulty_troop(t["TroopTableID"],
                                                                                    s.data.get("difficulty", 0)))) \
            if credited else 0
        kill_feed(s, uid, killer)
        sp = status.commander_down(s, uid, t, credited)  # a commander's troop: SP, FP, his force demoralized (B36)
        if exp or sp:                                    # 3 "Enemy troop Annihilated", 4 "Enemy Commander Defeated"
            from . import world
            s.send(Writer(S2C_COMBAT_BONUS).u8(4 if sp else 3).u32(exp).u32(0).u32(sp))
            if exp:
                world.add_exp(s, state, exp, why=f"kill {t['TroopTableID']}")
        got = quest.roll_drops(s, t["TroopTableID"], leader=t.get("NPLeaderID"))
        if credited:                                     # the normal loot (D2), for a fight the player's side took
            got += loot.roll_drops(s.data["spot"], t["TroopTableID"],                       # part in, as the exp (ours)
                                   difficulty_leader(t.get("NPLeaderID"), s.data.get("difficulty", 0)))
        drop_loot(s, got, events.boosted("gold", repeat_gold(
            s.data["char"], s.data["spot"], s.data.get("difficulty", 0),
            roll_gold(t["TroopTableID"])                    # the troop's row is the variant it spawned as,
            + roll_leader_gold(difficulty_leader(t.get("NPLeaderID"),               # and its leader's
                                                 s.data.get("difficulty", 0))))),
                  at=s.data.get("last_pos", {}).get(uid))
        if is_mission(s.data["spot"]):
            mission_troop_down(s, state, uid)
            return                               # nothing comes back in a mission
        delay = respawn_delay(s, uid, t)
        if delay is not None:
            s.later(delay, lambda: respawn_zone_troop(s, uid, t))

    from . import pvp
    pvp.make_game(role, state, troop_down)       # PvP against AI: its room's loading end and its win (pvp.py)
    return role


SNAPSHOT_S = 5.0                 # ours: the journal's room snapshot, this often while the room's connection is open


def snapshot(s, first=False):
    """The room now, into the journal ("snap"): its spot, the hero's place and hp, the troops standing per force, what
    the director waits for; again SNAPSHOT_S later (first: only the timer). Nothing while no journal is open."""
    if net.journal_out is None:
        return
    if not first:
        b = s.data.get("battle")
        hero, down, forces = b and b.troops.get(0), s.data.get("down", set()), {}
        for uid, t in s.data.get("zone_troops", {}).items():
            bt = b and b.troops.get(uid)
            if bt and uid not in down and combat.Battle.total(bt) > 0:
                forces[t.get("ForceNum")] = forces.get(t.get("ForceNum"), 0) + 1
        net.journal("snap", spot=s.data.get("spot"), hero=s.data.get("hero_pos"), hp=hero and [hero["hp"], hero["max"]],
                    forces=forces, waits=director.waits(s))
    s.later(SNAPSHOT_S, lambda: snapshot(s))


def send_start_header(s, spot):
    """Room start: 0x3f4e header (flag false), 0x3f4f player info, 0x3f50 troop info, 0x3f4e go (flag true).
    The header/player/troop parts must all arrive before the go flag (asserts in 0x140cbea60/0x140cbeaf0)."""
    acct = s.data["account"]
    char = hero_char(s)
    h = bytearray(0x1a)
    h[0x00] = 0                                  # -> common+0x165a
    struct.pack_into("<H", h, 0x01, MY_SLOT)     # my player id (+0x6dc)
    h[0x07] = MODE_PVE
    struct.pack_into("<H", h, 0x10, MY_SLOT)     # (+0x6de) compared with player records
    struct.pack_into("<H", h, 0x12, MY_SLOT)
    h[0x16:0x1a] = obf.u32(spot)                 # mission spot id
    from . import pvp
    if pvp.ai_room(spot):                        # PvP against AI: this header, then 16 players' records, structs
        return pvp.send_start(s, spot, h)        # and troops (pvp.py)
    from . import changetroop, party
    deck = deploy(s, spot)                       # the deck troops the room takes (B1): 1 + their count below
    reserve = {}                                 # the reserve: built after them, left disabled (changetroop.py). A bare
    if room_kind(spot) != "battle" and changetroop.reserve_limit(spot):     # battle room takes no deck: uid 1 its enemy
        reserve = changetroop.reserve_for(char, spot, s.data.get("difficulty", 0), deck)
        h[0x00] = changetroop.deploy_cap(s)      # the HUD slots' cap (sub 0x78)
    s.data["reserve"] = reserve
    ai = s.data.get("party_ai") or []            # a party's AI PCs: more players on the player's team (party.py)
    # 7-byte start record (0x140d09720 loop): u16 team, u16 player id, obool is-AI, u16 troop count (nonzero).
    # The team must match a mission start point (MissionInfo::FindPlayerStartPoint); single-player maps use team 0.
    # 0x140d0a370 gives each record's player its next `count` 0x3f50 entries, the first one his hero.
    rec = struct.pack("<HH", PLAYER_TEAM, MY_SLOT) + bytes([1]) + struct.pack("<H", 1 + len(deck) + len(reserve))
    s.send(Writer(S2C_SPOT_ROOM_START).obool(False).raw(bytes(h)).u16(1 + len(ai)).raw(rec + party.start_records(ai)))
    p = player_struct(char, spot, deck.values())
    from . import guild
    w = Writer(S2C_START_PLAYER_INFO).u16(1 + len(ai)).raw(bytes(p)).cstr(char["name"]).cstr(guild.name_of(char))
    party.write_players(w, ai, spot)
    s.send(w)
    w = Writer(S2C_START_TROOP_INFO).u16(1 + len(deck) + len(reserve) + sum(1 + len(a["troops"]) for a in ai))
    write_troop(w, slot=0, uid=1, troop_id=HERO_TROOP_ID, leader_id=char["class"], leader_level=char["level"],
                abilities=sorted(skills.battle_abilities(char).items()))
    for uid, t in (*deck.items(), *reserve.items()):
        write_deck_troop(w, uid, t, char)
    party.write_troops(w, ai)
    s.send(w)
    s.send(Writer(S2C_SPOT_ROOM_START).obool(True))


def deploy(s, spot):
    """The deck troops a room takes (troops.room_deck: main-deck slots 1..3, the first spottable
    Limit_Troop_<difficulty> of them), {room uid: troop}, kept in s.data["deck"]. The room uid is the deck slot (ours;
    a player troop's uid is below 10000, which the client's troop build 0x1408088e1 and the kill feed readers tell
    players' troops by; the hero is 0). A bare battle room (no zone file: its test enemy is uid 1) takes none."""
    from . import troops
    c = hero_char(s)
    deck = {} if room_kind(spot) == "battle" else dict(troops.room_deck(c, spot, s.data.get("difficulty", 0)))
    s.data["deck"] = deck
    return deck


def write_deck_troop(w, uid, t, c):
    """A deck troop's 0x3f50 entry: its deck slot, UNIT_COUNT unit places all alive, its trooptable id, its barracks uid
    (T+9: the troop finds its deck slot with it, 0x140cf7f44), its HP at its level with its passives (troops.room_row),
    no leader block (no officer), its equipped troop skills by slot (the ability list the hero's entry carries his
    abilities in) and those of its passive slots in the second list (0x10 + place, as a 0x50cb troop's passives), each
    at the tactics academy's level (troops.skill_level, T5.3), room uid T+0x23."""
    from . import troops
    r = troops.room_row(c, t)
    units = r["UNIT_COUNT"]
    write_troop(w, slot=uid, uid=units, troop_id=t["id"], leader_id=None, leader_level=0,
                hp=troops.unit_hp(r) * units, units=units,
                abilities=[(a, lv) for _, a, lv in troops.equipped(c, t)],
                passives=[(a, lv) for _, a, lv in troops.equipped(c, t, troops.PASSIVE_SLOTS)],
                barracks_uid=t["uid"], troop_uid=uid)


def write_troop(w, slot, uid, troop_id, leader_id, leader_level, hp=1000, units=1, abilities=(), barracks_uid=0,
                troop_uid=0, passives=()):
    """One 0x3f50 troop entry (reader 0x140d0d5d0): 40-byte T, then the optional-block chain. leader_id None: no leader
    block (a troop without an officer). The client's troop uid is T+0x23 (troop_uid: 0x140d0a370 copies it to the gen
    info +0x1a, 0x140f69ea0 to its build config +0x30, which Troop::SetUID 0x1407dbdf0 stores at troop +0x120, called
    at 0x1408088ac: the hero's 0 is why he binds as uid 0); T+1 (`uid`) is the troop's unit places
    (MakePlayerTroopGenInfo 0x140f674c0: +0x500, one alive bit each below T+0x19), 1 for the hero."""
    t = bytearray(0x28)
    t[0x00] = slot
    struct.pack_into("<H", t, 0x01, uid)              # unit places (the hero's 1)
    t[0x03:0x07] = obf.u32(troop_id)                   # trooptable TROOP_ID
    struct.pack_into("<Q", t, 0x09, barracks_uid)     # -> troop +0x7e0 (MakePlayerTroopGenInfo 0x140f674c0): the quick
                                                       # bar's gate compares it with the lineup record, 0 for the hero's
                                                       # page; uid 1 here refused every skill drag in rooms (text 7084,
                                                       # planning/wiring/UI-WIRING.md U1)
    pack_value(t, 0x15, hp)                            # hp?
    struct.pack_into("<H", t, 0x19, units)             # loop bound over units
    struct.pack_into("<H", t, 0x1b, 0xFFFF)            # ratio (/65535)
    struct.pack_into("<H", t, 0x1d, uid)               # troop 0: registered on the player (0x140b40d80); else troop
                                                       # +0x7f0 (meaning not pinned; the hero's value, T+1, kept)
    pack_value(t, 0x1f, hp)                            # max hp?
    struct.pack_into("<H", t, 0x23, troop_uid)         # the client's troop uid (+0x120)
    t[0x27] = 0                                        # bit1 clear: no 22-byte block
    w.raw(bytes(t))
    if leader_id is None:
        w.obool(False)                                 # 0x140d0d1b0: no leader (the gen info's leader id -1)
    else:
        lead = bytearray(25)
        struct.pack_into("<i", lead, 0, leader_id)
        lead[4] = leader_level
        pack_value(lead, 0x05, hp)                     # the hero's HP (-> troop data +0x30 -> CreateLeader InitHP);
        pack_value(lead, 0x09, hp)                     # zero here builds a dead hero. +0x09: max (-> +0x38)
        w.obool(True).raw(bytes(lead))                 # 0x140d0d1b0: leader block
    w.u16(len(abilities))                              # 0x140d0e0f0: n * (u8 level, u32 ability id)
    for a in abilities:
        aid, level = a if isinstance(a, tuple) else (a, 1)
        w.u8(level).raw(struct.pack("<I", aid))
    w.u16(len(passives))                               # 0x140d0deb0: n * 5, same layout, slots 0x10 + index
    for aid, level in passives:
        w.u8(level).raw(struct.pack("<I", aid))
    w.obool(False)                                     # 0x140d0d310
    w.obool(False)                                     # 0x140d0d470
    block = encode_stats({})                           # 0x140d0dad0: the stat block, as 0x50b8's (0x140cfbe30: u8 troop
    w.u16(len(block)).raw(block)                       # stat count, entries, leader entries to the end). Its count
                                                       # byte is read even from an empty block: sent empty, the last
                                                       # entry (the deck troop) took stats from past the packet, a
                                                       # stray HP_MAX its max (party bar, live 2026-09-30 15:13)


def send_ap(s, ts, why):
    """0x1365 with troops ts' AP now, journaled with the spottable column that spent it."""
    from . import troops
    s.send(troops.ap_packet(ts))
    net.journal("troop", ev="ap", why=why, troops=[[t["id"], t["ap"]] for t in ts])


def deck_won(s, state, c, amount):
    """A won mission for the deck troops (D13): each deployed troop, fallen or not, gains `amount` (troops.gain_exp: one
    level at most), the deck's levels go out in 0x124a (world.send_exp: its troop slots), and spottable
    Troop_Mission_Clear AP is spent (0x1365). Returns [(troop, level before, exp kept, exp percent before)] in room-uid
    order: the result record's troop slots (the kept exp, not the amount: T2.3)."""
    from . import troops, world
    deck = s.data.get("deck") or {}
    if not deck:
        return []
    paid = []
    for _, t in sorted(deck.items()):
        start = troops.exp_percent(t)
        paid.append((t, *troops.gain_exp(c, t, amount), start))
    if amount:
        world.send_exp(s)
    troops.spend_ap(deck.values(), troops.spot_cost(s.data["spot"], "Troop_Mission_Clear"))
    send_ap(s, [t for _, t in sorted(deck.items())], "Troop_Mission_Clear")
    log.info("deck troops won: %s", [(t["id"], before, t["level"], t["exp"], kept, t["ap"])
                                     for t, before, kept, _ in paid])
    return paid


TROOPS_SHORT = 0x1c21            # the 0x3f41 result "At least %1% troops must be organised in order to continue." (text
                                 # 7475, the Common error switch 0x140d673d0 at 0x140d6834b)


def entry_refusal(c, spot, difficulty):
    """The 0x3f41 result refusing an entry the original server refused and the client does not check, or None: fewer
    troops organised in the main deck's mission slots (troops.DECK_SLOTS, whatever the spot's allowance: Grey Rock's
    Hard allows none, Limit_Troop_2 "-") than spottable Min_Limit_Troop (51 spots: Grey Rock 10234 and the rifts 1, New
    Hampton 10235 2, the Dimensional Test 10238 and 20917 3; census A5, Q45). The client's loader keeps the column
    (SpotInfo +0x1a0) and checks only the upper allowance and the troops' AP."""
    from . import troops
    need = str((tables.by_id("spottable").get(str(spot)) or {}).get("Min_Limit_Troop", "0"))
    slots = ((c.get("lineups") or {}).get(troops.MAIN_DECK) or {}).get("slots") or []
    have = sum(1 for k in troops.DECK_SLOTS if k < len(slots) and slots[k] and troops.find(c, slots[k]))
    return TROOPS_SHORT if need.isdigit() and have < int(need) else None


def pay_entry(s, state, spot, difficulty):
    """What entering costs beyond AP: each spottable Require<j>_Type_<difficulty + 1> PayItem takes Value1 x Value2
    from the bag (the Dimensional Test 10238's Hard ticket 760000150, Hell 760000160, one each; census A7). The
    client's entry check (case 6 of 0x140d67d70) only looks for them in the bag."""
    from . import world
    row = tables.by_id("spottable").get(str(spot)) or {}
    for j in (1, 2):
        suffix = f"{j}_Type_{difficulty + 1}"
        if row.get(f"Require{suffix}") != "PayItem":
            continue
        code, n = row.get(f"Require{j}_Value1_{difficulty + 1}", ""), row.get(f"Require{j}_Value2_{difficulty + 1}", "")
        if code.isdigit() and n.isdigit():
            left = world.remove_item(s, state, int(code), int(n), why=f"entry {spot}")
            log.info("entry %d takes %d x%s%s", spot, int(code), n, f" ({left} missing)" if left else "")


def deck_aborted(s, state, g):
    """A mission room (game session g) left before its win (0x4048, world.escape_to_worldmap): spottable
    Troop_Mission_aborted AP from each deployed troop (15 on 78 story spots; census A4, Q45), told on s (0x1365).
    Nothing more after a win, and no gold (the client's "You lost %1% Gold" amount is not in the data: 0, ours)."""
    from . import troops
    deck, spot = g.data.get("deck") or {}, g.data.get("spot")
    cost = troops.spot_cost(spot, "Troop_Mission_aborted") if deck and not g.data.get("mission_won") else 0
    if not cost or not is_mission(spot):
        return
    troops.spend_ap(deck.values(), cost)
    send_ap(s, [t for _, t in sorted(deck.items())], "Troop_Mission_aborted")
    if state is not None:
        state.save()
    log.info("mission %d left before its win: Troop_Mission_aborted %d AP", spot, cost)


def deck_troop_down(s, state, uid, killer=None):
    """A deck troop wiped (its units all down): spottable Troop_Death AP, once a room (0x1365). It stays deployed: the
    win still pays it its mission exp (the dead get it too)."""
    from . import troops
    down = s.data.setdefault("deck_down", set())
    if uid in down:
        return
    down.add(uid)
    t = s.data["deck"][uid]
    troops.spend_ap([t], troops.spot_cost(s.data["spot"], "Troop_Death"))
    send_ap(s, [t], "Troop_Death")
    if state is not None:
        state.save()
    log.info("deck troop %d (%d) down: AP %d", uid, t["id"], t["ap"])
    net.journal("down", spot=s.data.get("spot"), troop=uid, deck=t["id"], killer=killer)


def pools_for(c, spot=None, deck=()):
    """The room's starting SP / SP max / ammo / ammo max, SP regeneration per tick (combat.SP_TICK_S) and finisher
    points. SP: the class's herotable %ApSp SP_MAX (the hero's own pool, full at the start) plus the trooptable SP_ADD
    of `deck`, the deck troops that take part in the room (troops.room_deck; the troops a mission hands over add
    nothing); regeneration %ApSp SP_RECOVERY plus theirs. The original's HUD, parts 1-5 (tests/test_hero_pools.py): 200
    outside missions and with no deck troop, 900 with the conscripted infantry (SP_ADD 700), 1,050 with the Grey Wood
    Bowmen too (150); 3 per 3 s, 5 with the bowmen (SP_RECOVERY 2); the start 200 in Grey Rock and New Hampton Castle,
    not spottable Default_SP (100) or %Contents SP_INIT (150), so `spot` no longer enters (kept for the callers).
    The hero's own SP max and recovery are his stats' (hero.char_stats: %ApSp plus his gear's, sets' and title's SP_MAX
    / SP_RECOVERY, rules census HERO S16; the tape's hero wore none, so its 200 / 3 hold).
    Ammo: Stack1_Init, max(Stack1_Max, Stack1_Init), Stack2; FP 0 of FP_Max (1000; the start at 0 is ours: no Init
    column); FSP (Helena's gauge, stat 99) 0 of FSP_Max (6; no Init column: ours)."""
    from . import hero, troops
    apsp = next((r for r in tables.sections("herotable")["ApSp"] if r["Hero"] == hero.HERO_CODE[c["class"]]), {})
    num = lambda v, d=0: int(v) if str(v).isdigit() else d
    rows = [troops.troop_row(t["id"]) or {} for t in deck]
    st = hero.char_stats(c)
    own = round(st.get("SP_MAX", num(apsp.get("SP_MAX"), 200)))
    return {"sp": own, "sp_max": own + sum(num(r.get("SP_ADD")) for r in rows),
            "ammo": min(255, num(apsp.get("Stack1_Init"))),
            "ammo_max": min(255, max(num(apsp.get("Stack1_Max")), num(apsp.get("Stack1_Init")))),
            "stack2": min(255, num(apsp.get("Stack2_Init"))), "stack2_max": min(255, num(apsp.get("Stack2_Max"))),
            "sp_rec": round(st.get("SP_RECOVERY", 0)) + sum(num(r.get("SP_RECOVERY")) for r in rows), "fp": 0,
            "fp_max": num(apsp.get("FP_Max"), 0), "fsp": 0, "fsp_max": num(apsp.get("FSP_Max"), 0)}


PLAYER_KEY_BASE = 0x10000


def player_key(c):
    """The room's player key, 0x3f4f +0x0f -> Player +0x54, which the client finds its Player by (0x140b42f80,
    0x140b427d0: the 0x5113 ride, a firework in the room 0x140de4a40, the party bar). Ours on purpose (owner,
    2026-09-30 16:5x: the party bar back in solo missions, a deviation from the original, which shows none): in a Battle
    spot HUDPartyInfo (0x14076e480) lists our Player when its key is not 0 and clears the list as "only me" when the
    key is the character id (common+0xd4, 0x5084's u32), so the key is neither; above 0xffff it is no u16 player id
    or NP owner (Player +0x50: our slot 0, NP_OWNER 0xfa, forces 10001..40040; their Players keep +0x54 = 0 from the
    reset 0x140b41730). Readers that look for the local player by the character id do not find it in a room (the
    escape echo 0x10b6 kind 3, the 'me' marker of the bar), as with the class we sent here before."""
    return PLAYER_KEY_BASE + c["id"]


def player_struct(c, spot=None, deck=()):
    """191-byte player struct (same layout SetPlayerInfoData 0x140cf9d70 reads for 0x50bd). It mirrors the
    character-list entry: colour UV pairs, the player key (the list's class slot), 21 face sliders, 21 part ids, 5 encoded colours; and the Player
    record's pools (planning/controls/HERO-CONTROLS.md §3.1; pools_for, with the room's deck troops): SP +0x01 (SetSP
    0x140b41090), SP max +0xb5, Stack1 (the Gunslinger's ammo) +0x13 and max +0x94, Stack2 +0x00 and max +0x7d; +0xb4
    is the scale (x 0.05, 0 renders 1.0)."""
    from . import hero
    look = bytes.fromhex(c["look"])
    p = bytearray(0xbf)
    pools = pools_for(c, spot, deck)
    struct.pack_into("<i", p, 0x01, pools["sp"])
    struct.pack_into("<i", p, 0xb5, pools["sp_max"])
    p[0x13], p[0x94], p[0x00], p[0x7d] = pools["ammo"], pools["ammo_max"], pools["stack2"], pools["stack2_max"]
    p[0x05:0x0f] = look[0x15:0x1f]               # 5 colour UV pairs -> 0x140b41490
    struct.pack_into("<I", p, 0x0f, player_key(c))   # -> player+0x54, the player key (player_key)
    p[0x14:0x29] = look[0x00:0x15]               # 21 face sliders -> 0x140b41520
    for i, code in enumerate(hero.look_codes(c)):  # 21 encoded item codes by equipment index -> 0x140b414e0
        p[0x29 + 4 * i:0x2d + 4 * i] = obf.u32(code)
    struct.pack_into("<I", p, 0x88, hero.look_shown(c))   # the parts shown -> 0x140b41500 (the hero window's boxes,
                                                          # 0x107f); 0: an equip in a room left the model as it was
                                                          # (live 2026-09-30 13:57, qwe123)
    p[0x95:0xa9] = look[0x1f:0x33]               # 5 encoded colours -> 0x140b41470
    p[0xad] = 1                                  # obool false
    return bytes(p)


def send_enter_cell(s):
    """Put our troop (uid 1 from 0x3f50) into the world: 0x50cb with one entry; then each deck troop's, at its start
    place, with its units."""
    w = Writer(S2C_ENTER_CELL_TROOP).u16(1)
    w.obool(False)                                     # no player block (it is our own troop)
    write_troop_state(w, start_pos(s), flags=HERO_FLAGS, stats=hero_stats(s), level=hero_level(s), hp=hero_max_hp(s))
    s.send(w)
    for uid in s.data.get("deck") or {}:
        w = Writer(S2C_ENTER_CELL_TROOP).u16(1)
        w.obool(False)
        write_deck_state(s, w, uid)
        s.send(w)
        # HUDTroopInfo excludes disabled troops. Enable the already-built roster
        # troop in this initial batch so its HUD slot is occupied before a later
        # NPC handover allocates the first empty slot (0x14078c1b0). The old
        # enable-all after NPC spawning let Grey Rock's archers overwrite F1.
        troop_order(s, uid, [ACT_ENABLE_TROOP, 0, uid, 1, 1])


def deck_enters(s, state, battle):
    """The deck troops (deploy) join the battle at the room start (B1, B4): each unit with its HP at the troop's level,
    its combatant record (combat.combatant_troop: its level stats, badges, passives (troops.room_row, T1.11; their
    statuses go on in status.room_start), trooptype, equipped skills at the academy's levels); spottable
    Troop_Mission_Enter AP spent and told (0x1365)."""
    from . import troops
    deck = s.data.get("deck") or {}
    if not deck:
        return
    c = hero_char(s)
    for uid, t in deck.items():
        r = troops.room_row(c, t, live=False)
        battle.add_np(uid, troops.unit_hp(r), r["UNIT_COUNT"], c=combat.combatant_troop(
            r, PLAYER_TEAM, {a: lv for _, a, lv in troops.equipped(c, t, range(8))}, troops.passives(c, t)))
    troops.spend_ap(deck.values(), troops.spot_cost(s.data["spot"], "Troop_Mission_Enter"))
    send_ap(s, list(deck.values()), "Troop_Mission_Enter")
    if state is not None:
        state.save()
    log.info("deck troops in the room: %s", [(uid, t["id"], t["level"], t["ap"]) for uid, t in deck.items()])
    net.journal("troop", ev="deploy", spot=s.data["spot"],
                troops=[[uid, t["id"], t["level"], t["ap"]] for uid, t in deck.items()])


def deck_offset(spot, slot):
    """(dx, dz) of deck slot `slot` from the hero: the zone's player start point lists 9 places, one per lineup slot
    (0 the hero's; every story mission's start point has 9) [I]; else 300 apart beside him (ours)."""
    from . import zone
    pts = zone.for_spot(spot)["PlayerStartPointInfoData"] if zone.available(spot) else []
    places = pts[0]["StartPointInfoData"] if pts else []
    if len(places) > slot:
        return places[slot]["PosX"] - places[0]["PosX"], places[slot]["PosZ"] - places[0]["PosZ"]
    return 300 * slot, 0


def write_deck_state(s, w, uid):
    """A deck troop's troop state (0x50cb entry / 0x50b8): the player's team, its room uid and table id, HP, level,
    its units, the hero's flags (alive, sight for the fog of war, attacks first), at its start place."""
    from . import troops
    t = s.data["deck"][uid]
    r = troops.room_row(hero_char(s), t)
    x, y, z = start_pos(s)
    dx, dz = deck_offset(s.data["spot"], uid)
    bt = (s.data.get("battle") and s.data["battle"].troops.get(uid)) or {}
    hp = round(combat.Battle.total(bt)) if bt else troops.unit_hp(r) * r["UNIT_COUNT"]
    resist = hit_resist("trooptype", r.get("TroopType"))
    write_troop_state(w, (round(x + dx), y, round(z + dz)), flags=HERO_FLAGS, uid=uid, troop_id=t["id"], hp=hp,
                      team=PLAYER_TEAM, units=r["UNIT_COUNT"], level=t["level"],
                      troop_stats={STAT_IDS["HIT_RESIST"]: resist} if resist > 0 else None)   # as an NP troop's (D2)


def hero_char(s):
    """The character this session plays: the one its game login named (0x5084); a session built without a login
    (the world's, the tests') takes the account's first, kept so later readers see the same one."""
    c = s.data.get("char")
    if c is None:
        c = s.data["char"] = s.data["account"]["characters"][0]
    return c


def hero_level(s):
    return hero_char(s).get("level", 1)


def hero_stat_values(c):
    """{stat id: value} of the hero in battle: the class's stamina and guard ids (HERO_STATS) and everything hero.stats
    computes from the tables, the level, the worn gear, the held passives and the worn title (the Info window's numbers)."""
    from . import hero
    out = dict(HERO_STATS.get(c["class"], {}))
    for name, value in hero.char_stats(c).items():
        if name in STAT_IDS:
            out[STAT_IDS[name]] = round(value)
    return out


def pool_stats(pools):
    """The room's SP and SP max (pools_for) as stat ids 6 / 7, in place of the table's (hero.stats: SP_INIT 150,
    %ApSp SP_MAX 200), which would cut a pool that the room's troops raised (Grey Rock's 900) back to 200."""
    return {sid: pools[k] for sid, k in ((combat.STAT_SP, "sp"), (STAT_IDS["SP_MAX"], "sp_max")) if k in (pools or {})}


def hero_stats(s):
    """hero_stat_values of the session's hero, with the room's SP pool (pool_stats) once the room has one."""
    return {**hero_stat_values(hero_char(s)), **pool_stats(s.data.get("pools"))}


def hero_combatant(c):
    """The hero's combatant record for the damage resolver (combat.combatant_hero): the named values hero_stat_values
    is built from (hero.stats, with the attack range ATTACK_*_MIN / _MAX) and the class's GUARD_REDUCE (HERO_STATS 42),
    at the character's level, on the player's team."""
    from . import hero
    named = hero.char_stats(c)          # the kit passives and the title, as the Info window (world.hero_block) counts
    named.setdefault("GUARD_REDUCE", HERO_STATS.get(c["class"], {}).get(42, 0))      # 42 GUARD_REDUCE
    return combat.combatant_hero(named, c.get("level", 1), c["class"], PLAYER_TEAM)


def hero_max_hp(s):
    return max(1, hero_stats(s).get(0, HERO_HP))


def room_level_up(s, c):
    """A level gained inside a room (kill exp, the clear's exp): the level-up effect over the hero (0x508a), his new
    numbers (0x5138), and a living hero healed to the new max (rules census HERO L10): the tape, rTitaEjTUoc f_00460
    -> f_00461 (15:18 -> 15:20), the Swidden Area's clear pays 11,504 exp, "The hero levelled up." and the HUD goes from
    9,690 (Lv.19, the bar ~73 %) to 13,402 full (Lv.20), no potion; a clear alone heals nothing (RVJnrq3zPlo 10:50 -
    11:22 holds 8,299 of 9,493)."""
    s.send(Writer(S2C_LEVEL_UP).u16(0).obool(True).u8(c.get("level", 1)))
    room_stats(s, c)
    t = s.data.get("battle") and s.data["battle"].troops.get(0)
    if t and t.get("hero") and not t.get("down") and t["hp"] > 0:     # at full hp too: room_stats' gain tells the HUD nothing
        t["hp"] = t["max"]
        send_troop_hp(s, 0, t["hp"], t["hp"])


def room_stats(s, c, hp_cap=None):
    """The hero's numbers in a room after a change (a level, the gear): 0x5138 with every stat, and the room's hp record
    follows a new max (BATTLE.md B04). SP, SP max, ammo and FP go out as the room's live pools, not the table's
    starting values: SP_INIT (150) after an equip left the client at 150 of a full 200 pool, and the regeneration,
    which stops at the cap, never corrected it (captures 2026-09-28 00:34 / 00:36, Mist Field). A level raises the HP
    by the max's gain; a gear change (gear_changed) passes hp_cap: the HP is not raised, it is cut to hp_cap and the
    new max, the HUD is told (0x505d), and the regeneration fills it from there."""
    stats = hero_stat_values(c)
    pools = s.data.get("pools")
    if pools:
        stats.update({combat.STAT_AMMO: pools["ammo"], combat.STAT_FP: pools["fp"], **pool_stats(pools)})
        from . import hero
        pools["hp_rec"] = hero.regen_tick(c)           # the gear, the level may change it (census P7)
    combat.send_stats(s, stats)
    t = s.data.get("battle") and s.data["battle"].troops.get(0)
    if t:
        t["c"] = hero_combatant(c)                     # the resolver hits with the new level and gear
        gain = stats.get(0, t["max"]) - t["max"]
        t["max"] = stats.get(0, t["max"])
        if hp_cap is None:
            t["hp"] = min(t["max"], t["hp"] + max(0, gain))
        else:
            t["hp"] = min(t["max"], t["hp"], hp_cap)
            send_troop_hp(s, 0, t["hp"], t["hp"])
            combat.start_regen(s)


def gear_changed(s, c, before):
    """The hero's gear changed in a room (world's 0x164e; before: the equipment entries worn before it). The original
    takes the old piece off, then puts the new one on, the HP following each max down but never up: part 2 27:35.5 ->
    27:36.0 (qeeQjhgO8ss_1655_1661_frames_2 f_00002 -> f_00003) the HUD went 994 -> 525, 994 less the Supplied
    Adventurer Top's 469, with the Supplied Trainee Top (+2,815) on and the max 3,340; it filled from there
    (tests/test_hero_pools.py). So the HP is cut to the max of the pieces worn both before and after (room_stats'
    hp_cap): a swap to 525 there, an equip into an empty place keeps it, an unequip cuts it to the lower max."""
    from . import hero
    kept = [e for e in hero.equipment(c) if any(e is b for b in before)]
    room_stats(s, c, hp_cap=hero_stat_values(dict(c, equip=kept)).get(0))


def send_mission_troop_info(s):
    """0x50b8 for our troop with the sight flag, so the fog of war counts it; the same for each deck troop."""
    w = Writer(S2C_MISSION_TROOP_INFO)
    write_troop_state(w, start_pos(s), flags=HERO_FLAGS, stats=hero_stats(s), level=hero_level(s), hp=hero_max_hp(s))
    s.send(w)
    for uid in s.data.get("deck") or {}:
        w = Writer(S2C_MISSION_TROOP_INFO)
        write_deck_state(s, w, uid)
        s.send(w)


def send_np_troop(s, uid, np_troop_id, pos, hp, units, team=None, zt=None, leader=None, abilities=(), passives=(),
                  ai=-1):
    """An NP (enemy) troop entering our cell: 0x140cfae60 EnterCellTroop builds unknown uids through
    MakeTroopGenInfoForBuild 0x140cf7080 (planning/INVENTORY.md). It is built disabled; ACT_ENABLE_ALL_TROOPS shows it.
    zt = its zone entry (flags, AI leash and paths); without one (quest spawns, the test enemy) it attacks first
    (the zone majority, 14,236 of 15,112; a rule of ours). ai = its program (table_ai) for the descriptor. The owner
    stays with its force; field simulation is granted separately after binding (FIELD-SIMULATION.md)."""
    from . import zone
    zt = zt or {}
    flags = (TROOP_ALIVE | TROOP_FIRST_ATTACK * bool(zt.get("FirstAttack", 1)) | TROOP_SIGHT * bool(zt.get("SharingSight"))
             | TROOP_HOLD * bool(zt.get("HoldMovement")))
    row = zone.np_troop(np_troop_id) or {}
    level = int(row.get("LEVEL_CURRENT", "0") or 0)
    troop_stats, leader_stats = np_stat_block(row, np_leader(leader[0]) if leader else None)
    w = Writer(S2C_ENTER_CELL_TROOP).u16(1)
    w.obool(False)                                     # no player block (NP troop)
    write_troop_state(w, pos, flags=flags, uid=uid, troop_id=np_troop_id, hp=hp,
                      team=NP_TEAM if team is None else team, owner=np_owner(zt),
                      np=True, units=units, level=level, np_block=np_block(zt, ai), leader=leader, abilities=abilities,
                      passives=passives, stats=leader_stats, troop_stats=troop_stats)
    s.send(w)

    # Fields register different-owner NPCs as remote even when we are host (0x140cf7fc0).
    # 0x50cf can grant simulation without changing their team, force or table AI. Both the
    # NPC and reference hero must exist first; never reuse a previous lifetime's bind.
    if uid != 0 and is_field(s.data.get("spot")):
        s.data.setdefault("bound", set()).discard(uid)
        s.data.setdefault("field_sim_pending", set()).add(uid)


def np_stat_block(row, lead=None):
    """({stat id: value} of an NP troop's units, of its leader) for the troop-state stat block (census D2, D8): stat 40
    HIT_RESIST = its nptrooptype %Combat HITRESIST (0 on 328 types, 30 on 218, 60 on 198, 9999999 on 187: the troll
    134080 60, the kobold sorcerer 134020 30, the infantry 0) and its leader's npleadertype %Combat HITRESIST (60 on
    174, 30 on 99), and stat 98 PROBABILITY_DODGE = nptrooptable DODGE where it is not 0. The client reads the column
    but its copy (gen +0x888) is never read: the stagger test reads troop +0x930 stat 40, which only this block, 0x507f
    or 0x5138 fill (TroopBuilder::InitializeTroop 0x140808820 copies GUARD / COUNTER and never it; client digs
    2026-10-01), and DODGE is in no client table (only the server's block can set it; Unit::EvaluateDodge 0x140a162a0).
    Until this block every NP unit had resist 0: every blow staggered it."""
    troop = {STAT_IDS["HIT_RESIST"]: hit_resist("nptrooptype", (row or {}).get("NPTroopType")),
             98: int(combat._f((row or {}).get("DODGE")))}
    leader = {STAT_IDS["HIT_RESIST"]: hit_resist("npleadertype", lead.get("NPLeaderType"))} if lead else {}
    return {k: v for k, v in troop.items() if v > 0}, {k: v for k, v in leader.items() if v > 0}


def hit_resist(table, type_id):
    """A troop type's %Combat HITRESIST (nptrooptype / npleadertype / trooptype, keyed by its first column): the stat 40
    its units (a deck troop's too) carry in the troop-state stat block (np_stat_block, write_deck_state; census D2)."""
    key = {"nptrooptype": "NPTroopType", "npleadertype": "NPLeaderType", "trooptype": "TroopType"}[table]
    return int(combat._f(combat._rows_by(table, "Combat", key).get(type_id, {}).get("HITRESIST")))


def sync_positions(b, flags=None):
    """{troop uid: (x, y, z)} from a 0x50b0 body: u16 n, then n records: 13 bytes (+0 flags, +1 direction, +2 u16 uid,
    +4 i16 speed, +6..+9 packed x/z, +10 i16 y, +12 nibble), 5 leader-position bytes when flags & 0x80, a formation
    byte, and when it has 0x80 a u8 count of 6-byte path points (read from captures 2026-09-27: a 52-record list at
    23:57 and the hero's own `81 01` + one point). The records read before a malformed one are kept."""
    out = {}
    try:
        n, i = struct.unpack_from("<H", b, 0)[0], 2
        for _ in range(n):
            f, uid = b[i], struct.unpack_from("<H", b, i + 2)[0]
            x, z = obf.dec_pos_xz(b[i + 6:i + 10], b[i + 12])
            out[uid] = (x, struct.unpack_from("<h", b, i + 10)[0], z)
            if flags is not None:                       # (planning/client/room_troops.md: +0 & 0x7f the state
                flags[uid] = f                          # class, 0 at rest; 0x80 leader position follows)
            i += 13 + (5 if f & 0x80 else 0)
            formation = b[i]
            i += 1
            if formation & 0x80:
                i += 1 + 6 * b[i]
    except (IndexError, struct.error):
        pass
    return out


def hero_sync_pos(b):
    """The hero's (x, y, z) from a 0x50b0 body, or None. His record is anywhere in the list: reading only the first
    missed it in every room with other troops (the draw and the wake by area never came, owner live 23:59)."""
    return sync_positions(b).get(0)


def np_owner(zt):
    """The owner id (troop state +0x30) of an NP troop: its zone ForceNum (10001..40040 in every zone; one team per
    force), else NP_OWNER (quest- and prop-spawned troops, all NP_TEAM). The client makes one Player per owner, with
    the team of the first troop that names it (0x140cf842a -> 0x140b42ab0(owner, team), both copied by
    MakeTroopGenInfoForBuild 0x140cf72e1..0x140cf72fb), and a troop's team is its Player's: with one owner for every
    NP troop, Grey Fog's first troop (Thompson 10000, team 0) made all its enemies team 0, allies that never fought
    (probe 2026-09-27 21:36, troop +0xa0 = 0 on 21000..22004; owner live 21:28 "the units ... are there just
    static"). ENEMY-AI.md finding 8 inferred ForceNum; the script actions also refuse owners below 5000."""
    force = int((zt or {}).get("ForceNum") or 0)
    return force if force >= 5000 else NP_OWNER


def dist_code(v):
    """A zone distance as the NP descriptor's u16 code (0x14053b360: up to 30000 the code is the value); -1 -> 0."""
    v = int(v or 0)
    return 0 if v < 0 else min(v, 30000)


def table_ai(np_troop_id):
    """The troop AI program (TAI_<id>) of an NP troop: its nptrooptable TROOPAI (41000 Grey Rock's archers, 50000 Mist
    Field's spiders, 0 New Hampton's boss Vert, 900000 the Goblin Nest's fleeing goblins), -1 for '-' or no row.
    Only the server can give it: the client decodes TROOPAI (row +0x60, parser 0x1418bdf98, '-' -> -1) in one place,
    BuildSpawnTroop's Invasion case (0x140cf98e2, 80000), and an AI id of -1 in the NP descriptor or 0x5083 gives the
    troop its TAIBranch row's +0x20 column instead (TROOPAI_NPINIT, 40000 on every troop branch; 0x140cf8645,
    0x140d02f60), so -1 for '-' is the table's own default (planning/controls/ENEMY-AI.md, 2026-09-30)."""
    from . import zone
    ai = str((zone.np_troop(np_troop_id) or {}).get("TROOPAI") or "-").strip()
    return int(ai) if ai.lstrip("-").isdigit() else -1


def np_block(zt, ai=-1):
    """The 22-byte NP descriptor after 0x50cb's NP flag (ENEMY-AI.md §4.2, read from 0x140cf85ce..0x140cf87ad):
    +0 u16 CombackDist, +2 u16 target troop, +4 u32 path 2, +8 u16 CombatDist, +0xa u16 fall-back area, +0xc i32 AI
    (the troop's program, table_ai; -1: its TAIBranch NPINIT), +0x10 u16 WanderingDist, +0x12 u32 path 1; "none" is
    0xffff / 0xffffffff."""
    none16 = lambda v: 0xffff if v is None or int(v) < 0 else int(v) & 0xffff
    none32 = lambda v: 0xffffffff if v is None or int(v) < 0 else int(v)
    return struct.pack("<HHIHHiHI", dist_code(zt.get("CombackDist")), none16(zt.get("TargetTroopID")),
                       none32(zt.get("DefaultPath2ID")), dist_code(zt.get("CombatDist")),
                       none16(zt.get("FallBackAreaID")), ai, dist_code(zt.get("WanderingDist")),
                       none32(zt.get("DefaultPath1ID")))


def spawn_zone_troops(s):
    """A field's NP troops from its zone file (zone.for_spot): every activated troop of NPCTroopInfoData at its place,
    uid = the zone's TroopID, units and unit hp from nptrooptable (UnitNum 0 = the table's UNIT_COUNT), default AI.
    They enter through 0x50cb like the battle troops (grid troops; 0x511a is for IgnoreCellGrid ones). A mission room
    follows its mission_plan: troops of another difficulty and later-phase ones stay out, held allies and the player's
    held troops that have nothing to wait for come at once, and the player's troops are handed over (G5)."""
    from . import zone
    spot = s.data["spot"]
    plan = mission_plan(spot, s.data.get("difficulty", 0)) if is_mission(spot) else None
    plan = plan and rules.plan(spot, plan)              # a rule that brings its own waves (the Dimensional Test)
    held, later = director.held(spot), director.hand_later(spot)
    n = 0
    for t in zone.for_spot(spot)["NPCTroopInfoData"]:
        active = t.get("IsActivated") and t.get("SpawnActivated")
        if plan is not None and (t["TroopID"] in plan["out"] or not (active or t["TroopID"] in plan["start"])):
            continue
        mine = plan is not None and t["TroopID"] in plan["hand"] and t["TroopID"] not in later
        if plan is not None and t.get("ForceNum") in held and not mine:
            continue                                    # the director's table brings it in (HOLD; a HAND_LATER troop
                                                        # of a held force with its "wake": the camps' mock battle)
        if plan is None and not active:
            continue
        if spawn_zone_troop(s, t):
            n += 1
            if mine:
                send_actions(s, [ACT_CHANGE_FORCE, 0, t["TroopID"], MY_SLOT, TROOPAITYPE_HEROSUPPORT])
                log.info("zone troop %d (%s) handed to the player", t["TroopID"], t["TroopTableID"])
                net.journal("hand", spot=spot, troop=t["TroopID"], start=True)
    log.info("field %d: %d zone troops spawned", spot, n)
    arrive_at_door(s)
    if plan is not None:
        stage_hero(s)
        s.data["plan"] = dict(plan, hand=tuple(u for u in plan["hand"] if u not in later)) if later else plan
        s.data["waves"] = [list(w) for w in plan["waves"]]
        s.data["wave_allies"] = {k: list(v) for k, v in plan["allies"].items()}
        s.data["barriers"] = dict(plan["barriers"])
        s.data["guards"] = {f: set(uids) for f, uids in plan["guards"].items()}
        if s.data["waves"] and not any(hostile(z) for z in s.data.get("zone_troops", {}).values()):
            next_wave(s)                                # nothing to fight at the start (10233, 10318, 20301 ...)
        mission_guide(s)
        director.start(s)
        rules.start(s)                                  # the Unknown Corridor's clock, the Goblin Nest's panel, the
                                                        # Dimensional Test's first storm, a subjugation's clock


# A mission's temporary troops ("incorporated": zone TroopAlias 편입_..., e.g. 1_NewHamptonCastle's trebuchet 135300 and
# organ cannon 135090, the walkthrough's "[Temporary Unit]: Trebuchet") are handed to the player as they spawn with
# ActTroopChangeForce(type 0 = a troop uid, uid, new owner, AI type 0..3) -> 0x140ba35f0 -> 0x140b437d0: the old
# Player drops the troop, Player::AddTroop 0x140b3fb30 adds it to mine (HUD slot, tactical selection 0x140b44430,
# orders 0x140708de0), then Troop::SetTroopAIType (read from code). That the original's mission script did this, and
# at the start, is inferred.
INCORPORATED = "편입"
ACT_CHANGE_FORCE = 0xea7e
# The AI type is the client's TROOPAITYPE (names at 0x14260ac88): ControlCenter::ChangeForceID (call at 0x140afe899)
# hands it to Troop::SetTroopAIType 0x1407e85e0, which installs that column of the troop's TAIBranch row (0x1407f5180,
# the troop type's TAIBranch) as its script AI and keeps the type at troop +0xd7c: 0 OFFENSIVE (TAI 10000: a ranged troop
# shoots what is already in its range, from where it stands), 1 DEFENSIVE (10010), 2 HEROSUPPORT (10020: goes with the
# hero and takes his target), 3 HOLD (10030). The client gives every troop of the local player 2 when it registers them at the room start
# (SyncManager::RegisterPlayerTroops 0x140c1651a), so the deck troops start on Hero Support; a handed troop takes the
# same (owner live 2026-09-30 16:50 Grey Rock: handed with 0, "archers don't move to be in position to attack they just
# start the atack from where they are"). The Z / X / C keys change it later (0x14078a5f0).
TROOPAITYPE_HEROSUPPORT = 2
# The player's troops (MISSIONS-WIRING F7 / G5, the designers' own marks): 편입 in the alias or the nptrooptable StringID
# (10233 133270 / 133120, 10310 편입1P..4P, 10321 110210, 10318 118390), a Force name 유저부여 (10306 F10502 "리얼포병"),
# aliases PC_Troop1-3 / PC_TutoTroop (camps 10346, 10347), 영웅부대1/2 (10234), 조작 (10345 상성조작궁병, "the archer you
# control"), 루나윙_본체 (the Lunawing, 10361 / 10362: P3-1 / P3-4), and inside the training camps 아군_PC / 아군PC급 (alias
# or StringID: 20357's PC-grade troops).
PLAYER_MARKS = (INCORPORATED, "PC_Troop", "PC_TutoTroop", "영웅부대", "조작", "루나윙_본체")
CAMP_MARKS, CAMP_MAPS = ("아군_PC", "아군PC급"), ("1_TrainingCamp", "2_TrainingCamp")
PLAYER_FORCE_MARK = "유저부여"
OTHER_SHARE = re.compile(r"[2-4]P$")   # 편입2P..4P: the shares of players 2-4 (the missions were built for four); solo
                                       # takes the 1P one (ours, [I])
HUD_TROOPS = 4                          # the HUD's four troop slots (HUDTroopInfo): the most troops handed at a time


C2S_TROOP_BOUND = 0x50ab   # GameStateBattleField::BindTroopRes (builder 0x14054b390): u16 plain troop uid, sent once a
                           # spawned troop is built and bound (planning/client/README.md)
C2S_FORCE_LANDED = 0x50e6  # builder 0x140f08560, 3 bytes: T2[(flag != 0) + 2 * b1], coded u16 troop uid; sent TRUE by
                           # ControlCenter::ChangeForceID 0x140afe8a7 when a troop joins my force (ActTroopChangeForce,
                           # S2C 0x5115), by ScriptTroop::SetTacticalCommand_Troop 0x140b99bf0, and by Lua bindings
                           # (0x140ba6770; 0x140bad790 FALSE). No reply: 0x50e7's handler is `ret 0`
                           # (planning/client/room_troops.md; live 19/13, all TRUE)


def troop_bound(s, uid):
    """0x50ab: the troop exists. Grant field simulation before releasing its held orders."""
    bound = s.data.setdefault("bound", set())
    bound.add(uid)
    waiting = s.data.setdefault("await_bind", {})
    pending = s.data.get("field_sim_pending", set())
    net.journal("bound", spot=s.data.get("spot"), troop=uid, orders=len(waiting.get(uid, [])))
    # A hero that finishes building last also releases NPCs already bound. The packet's
    # second word is the hero TROOP uid (0), which is also MY_SLOT (the Player id).
    ready = [uid] + (sorted(pending & bound) if uid == 0 else [])
    for ready_uid in ready:
        if ready_uid in pending:
            if 0 not in bound:
                continue
            s.send(Writer(S2C_TROOP_SIMULATION).u16(ready_uid).u16(0))
            pending.remove(ready_uid)                 # duplicates would reset the client's behavior
            net.journal("simulation_grant", spot=s.data.get("spot"), troop=ready_uid, reference=0)
        for act in waiting.pop(ready_uid, []):
            act(s) if callable(act) else send_actions(s, act)    # a callable: an order waiting for several troops


def troop_order(s, uid, act):
    """A script action aimed at one troop, once the client has it: an order sent before the troop's 0x50ab is lost
    (live 2026-09-29 02:27:12: F20100's 20 marches went at .559, the troops were bound at .569-.58, six never
    moved). Field NPCs also wait for simulation transfer. Outside fields, until the first 0x50ab of a room
    (tests, a client that never binds) orders go at once."""
    if "bound" in s.data and (uid not in s.data["bound"] or uid in s.data.get("field_sim_pending", ())):
        s.data.setdefault("await_bind", {}).setdefault(uid, []).append(act)
    else:
        send_actions(s, act)


def hand_troop(s, uid):
    """A zone troop to the player now (the director's "hand": Tower's archers at the winged wyrms, the original's
    F2 first shown there, playthrough part 2 12:10): ActTroopChangeForce as at the start, and it counts as his."""
    troop_order(s, uid, [ACT_CHANGE_FORCE, 0, uid, MY_SLOT, TROOPAITYPE_HEROSUPPORT])   # dropped by the client before
                                                                                         # the troop is bound
    count_as_players(s, uid)
    log.info("zone troop %d handed to the player", uid)
    net.journal("hand", spot=s.data.get("spot"), troop=uid)


def count_as_players(s, uid):
    """The troop is one of the player's in this room (the plan's hand, which troop_sync and the director read)."""
    plan = s.data.get("plan")
    if plan is not None and uid not in plan["hand"]:
        s.data["plan"] = dict(plan, hand=plan["hand"] + (uid,))


def troop_landed(s, uid, on):
    """The client's own word that a force change landed (0x50e6): TRUE, the troop now obeys the player, so it counts
    as his, as hand_troop counts it when it sends the order (ScriptTroop ChangeForce returns silently for a troop not
    built yet, 0x140ba3619, so this is the proof). FALSE (a Lua binding, never live) is only logged."""
    log.info("troop %d force change landed: %s", uid, "the player's" if on else "off")
    net.journal("landed", spot=s.data.get("spot"), troop=uid, on=bool(on))
    if on:
        count_as_players(s, uid)


def players_troop(spot, t, names):
    """Whether a zone troop is one the mission hands to the player (a team-0 troop only): 1 for PLAYER_MARKS, 2 for a
    camp's PC-grade troop (handed after the marked ones: 20358's 조작오우거 before its PC-grade infantry), 0 for none.
    A staging alias or Force name (ALLY_STAGING: 10345's 컷신용궁병, the cutscene archer) is none."""
    from . import tables, zone
    alias = str(t.get("TroopAlias") or "")
    force = names.get(t.get("ForceNum"), "")
    if t.get("TeamNum") != PLAYER_TEAM or any(w in alias or w in force for w in ALLY_STAGING):
        return 0
    text = alias + str((zone.np_troop(t["TroopTableID"]) or {}).get("StringID", ""))
    if PLAYER_FORCE_MARK in force or any(m in text for m in PLAYER_MARKS):
        return 1
    camp = (tables.by_id("spottable").get(str(spot)) or {}).get("Map_File") in CAMP_MAPS
    return 2 if camp and any(m in text for m in CAMP_MARKS) else 0


def hand_limit(spot, difficulty=0):
    """How many troops a room hands the player (G5, ours [I]): its Limit_Troop where set (10321: 2 of its 4 wizards),
    else the HUD's four; never above four. The client reads Limit_Troop_<difficulty> as the number of deck troops that
    take part (troops.deck_limit, Q34), so this second reading is ours; both apply (Grey Rock: 10073 handed and one
    deck troop)."""
    from . import tables
    row = tables.by_id("spottable").get(str(spot)) or {}
    limit = row.get(f"Limit_Troop_{difficulty + 1}", "-")
    limit = limit if limit.isdigit() else row.get("Limit_Troop", "-")
    return min(HUD_TROOPS, int(limit)) if limit.isdigit() and int(limit) > 0 else HUD_TROOPS


@functools.cache
def prop_row(type_id):
    """The smartproptable row of a prop type (ids are unique across the TYPE_* sections)."""
    from . import tables
    for name, rows in tables.sections("smartproptable").items():
        for r in rows:
            if name.startswith("TYPE_") and next(v for k, v in r.items() if k.startswith("ID_")) == str(type_id):
                return r
    return None


def trigger_only(row):
    """A mission-trigger-only prop (MissionTriggerOnly_SW): only the original server's mission scripts operated it."""
    return row.get("MissionTriggerOnly_SW", "False").lower() == "true"


def placed_trigger_only(row):
    """Trigger-only props that stand in the world anyway: those with a cast time (barricades 64, egg nests 553). The
    original's Glen's camp barricades are there, interactable, and never open; the player leaves the camp through
    1150301's accept warp (the owner, 2026-09-27, from original gameplay footage: "he never break the barricade
    after the quest complete he apear out of the initial camp, the barricades are iteble but he cant cross them").
    Those without a cast time (village walls 448-451, road-block trees 592-594) stay out: nothing offline removes them."""
    return trigger_only(row) and (row.get("CastTime_SW") or "-").replace(".", "", 1).isdigit()


STAGING_QUEST = "1"              # RequireQuestID_SW of the quest-staging switches: no quest has this id


def staging_prop(row):
    """A switch the original's quest scripts staged (RequireQuestID_SW "1": 12 types, e.g. 421 the stolen weapons
    store beside the Nameless Mercenary's Grave, 600-603 퀘스트연출용, 590 the staging anvil): shown, never usable, so it
    goes out in state 1, where the client's operable check (vt+0x218 0x141b65950: state 0 or 2) skips it. In state 0
    it took F from the grave NPC beside it (651, npctable 6502) and quest 1150316's Talk could not be done (owner live
    2026-09-28 00:40: "can't iteract properly with the mercenary grave"); in state 1 the NPC source picked 651 on 956
    of 956 frames and "[F] Talk" showed on the grave."""
    return row.get("RequireQuestID_SW") == STAGING_QUEST


def prop_shown(type_id, r):
    """Whether a zone prop is in the world for quest record r: a Hide prop when its emergence condition holds, any other
    prop always, except the trigger-only ones the player cannot open (trigger_only)."""
    from . import quest
    row = prop_row(type_id)
    if row is None:
        return True
    if row.get("Hide", "False").lower() == "true":
        return quest.emerged(row.get("Energence_Conditions", "-"), row.get("Energence_Conditions_Value", "-"), r)
    return not trigger_only(row) or placed_trigger_only(row)


def prop_pos(x, z):
    """5 packed bytes of a 0x50d1 record (+9..+13): signed 20-bit x/z as the reader decodes them,
    x = hi(T1[b0])<<16 | T1[b1]<<8 | T2[b4], z = lo(T1[b0])<<16 | T1[b2]<<8 | T2[b3]."""
    x &= 0xFFFFF
    z &= 0xFFFFF
    return bytes([obf.via_t1(((x >> 16) << 4) | (z >> 16)), obf.via_t1(x >> 8), obf.via_t1(z >> 8),
                  obf.via_t2(z), obf.via_t2(x)])


def write_prop(w, prop_id, pos, shown, alive=True, state=0):
    """A 0x50d1 record. For a prop the client already has (the zone's, read from the .clt) it applies +2 alive and +7
    shown (0x14091a710: shown moves the prop into the scene and the interactable map, 0x140ccf620; not shown takes it
    out, 0x140ccf7b0) and +14 state (vt+0x200 when it differs); the rest builds a prop it does not have (0x140ccfc20):
    +0 u16, +8 u8, +9 packed x/z, +18 u32, +22 u8."""
    w.u16(0).obool(alive).raw(obf.u32(prop_id)).obool(shown).u8(0).raw(prop_pos(*pos)).i32(state).u32(0).u8(0)


def send_zone_props(s, spot, c):
    """Every smart prop of the spot's zone (the client holds them all hidden until this list): shown when not hidden
    by the table or when its quest condition holds for character c."""
    from . import quest, zone
    r = quest.record(c)
    props = zone.for_spot(spot)["SmartPropData"]
    w = Writer(S2C_PROP_LIST).u16(len(props))
    shown = 0
    opened = s.data.get("prop_states", {})
    for p in props:
        on = prop_shown(p["SmartPropTypeID"], r)
        state = PROP_ON if staging_prop(prop_row(p["SmartPropTypeID"]) or {}) else PROP_OFF
        if p["SmartPropID"] in opened:      # switch_on ran while the troops spawned (a start step, a first wave): this
            on, state = True, open_state(p)     # list comes after it and would hide the prop, collision and all (10306's 20015)
        write_prop(w, p["SmartPropID"], (round(p["PosX"]), round(p["PosZ"])), on, state=state)
        shown += on
    s.send(w)
    log.info("field %d: %d of %d props shown", spot, shown, len(props))


def heal_hero(s, amount):
    """Raise the hero's hp in this battle room (up to its start hp) and send it (0x505d); False without a hero."""
    t = s.data.get("battle") and s.data["battle"].troops.get(0)
    if not t or not t.get("hero"):
        return False
    before = t["hp"]
    amount = int(amount * combat.heal_share(s, 0))     # e.g. the God's Blessing debuff 1027: 50-90 % (census B6)
    t["hp"] = min(t.get("max", HERO_HP), t["hp"] + amount)
    send_troop_hp(s, 0, t["hp"], t["hp"])
    if t["hp"] > before:                                # the heal number and "Troop %1%'s HP is restored by %2%"
        restored = bytearray(4)
        pack_value(restored, 0, t["hp"] - before)
        s.send(Writer(S2C_HEAL).u32(HEAL_NO_SOURCE).u16(0).u32(0).raw(bytes(restored)))
    log.info("hero healed by %d: hp %d", amount, t["hp"])
    return True


# 0x505e (0x140d1c350, requests/pushes_battle.md): u32 source kind, u16 troop, u32 source id, split HP amount. Kinds 0
# and 1 name the source from a map that is not pinned; 2 prints text 0x276c without one.
S2C_HEAL = 0x505e
HEAL_NO_SOURCE = 2


def zone_prop(spot, prop_id):
    """The zone's SmartPropData entry of a prop id, or None (also when the spot has no zone file)."""
    from . import zone
    if not zone.available(spot):
        return None
    return next((p for p in zone.for_spot(spot)["SmartPropData"] if p["SmartPropID"] == prop_id), None)


def prop_refusal(s, prop_id):
    """Why the player may not use a prop now (None when they may): unknown or not shown, trigger-only, its
    RequireQuestID_* quest or RequireItemID_* item not held, or already on or being cast."""
    from . import quest
    p = zone_prop(s.data["spot"], prop_id)
    if p is None:
        return "not a prop of this zone"
    r = quest.record(hero_char(s))
    row = prop_row(p["SmartPropTypeID"]) or {}
    if not prop_shown(p["SmartPropTypeID"], r):
        return "not shown"
    if trigger_only(row):
        return "mission trigger only"
    need = next((v for k, v in row.items() if k.startswith("RequireQuestID_")), "-")
    if need.isdigit() and need not in r["active"]:
        return f"quest {need} not held"
    item = next((v for k, v in row.items() if k.startswith("RequireItemID_")), "-")
    bag = hero_char(s).get("bag", [])
    if item.isdigit() and not any(str(it["code"]) == item for it in bag):     # e.g. 403 needs 451000231 (not used up;
        return f"item {item} not held"                                           # RequireQuestCo_* is not mapped)
    if s.data.get("prop_states", {}).get(prop_id, PROP_OFF) != PROP_OFF or prop_id in s.data.get("prop_casts", {}):
        return "already on"
    return None


def box_loot(row, roll=random.randrange):
    """An item box's items (TYPE_ITEMBOX GrantItem1..3_IB, each GrantItem<k>_Min..Max); [] for other props.
    GrantDropID1_IB (a drop table) is not read."""
    loot = []
    for k in (1, 2, 3):
        code = row.get(f"GrantItem{k}_IB", "-")
        if code.isdigit():
            lo = int(row.get(f"GrantItem{k}_Min") or 1)
            hi = max(lo, int(row.get(f"GrantItem{k}_Max") or lo))
            loot.append((int(code), lo + roll(hi - lo + 1)))
    return loot


def prop_back_after(row):
    """Seconds until a used prop is back to off: a switch's RechargeTime_SW when AutoReturn_SW, an item box's
    Regen_Time; None when it stays on."""
    if row.get("AutoReturn_SW", "False").lower() == "true":
        return max(1.0, float(row.get("RechargeTime_SW") or 0))
    if "GrantItem1_IB" in row and (row.get("Regen_Time") or "-").isdigit():
        return max(1.0, float(row["Regen_Time"]))
    return None


OBSERVER_MODEL = "TROOP_NHU_D_OBSERVER_INVISIBLE"     # nptrooptable r_BASE_RESOURCE of the scripts' invisible observers


# Staging troops are no win targets (MISSIONS-WIRING G2, ours): a Force name or TroopAlias with 연출 (staging), 실기
# (demo), 카메라 (camera), 컷신 (cutscene) or 대사 (dialogue), and three staging forces the names do not mark.
STAGING_WORDS = ("연출", "실기", "카메라", "컷신", "대사")
STAGING_FORCES = {10235: {49300}, 10322: {20540}, 20303: {30000}}


def staging(spot, t, names):
    return t.get("ForceNum") in STAGING_FORCES.get(spot, ()) or any(
        w in names.get(t.get("ForceNum"), "") for w in STAGING_WORDS)


def hostile(t):
    """A zone troop that must fall for a mission to be won: on another team than the player's and worth exp
    (nptrooptable EXP_FACTOR; the missions' staging civilians have 0). The original's mission scripts decided victory;
    they are not shipped, so this is the offline rule (owner, 2026-09-27: make the quest put us outside the camp).
    Invisible observers (model TROOP_NHU_D_OBSERVER_INVISIBLE, UI_Visible False, speed 0: the scripts' spectators, e.g.
    Engelberg Midpoint's 11 stacked at one point) are no one to fight, whatever their exp."""
    from . import zone
    if t.get("TeamNum", PLAYER_TEAM) == PLAYER_TEAM or t.get("Staging"):
        return False
    if any(w in str(t.get("TroopAlias") or "") for w in STAGING_WORDS):
        return False
    if rules.target(t):                               # a mission rule's, whatever its exp or grade: the Unknown
        return True                                   # Corridor's day boss, the Goblin Nest's real goblins
    row = zone.np_troop(t["TroopTableID"]) or {}
    if row.get("NP_Grade") == "Extra":               # treasure goblins and special-drop dummies (특수드랍): a bonus
        return False                                  # that runs, never a mission target
    if row.get("r_BASE_RESOURCE") == OBSERVER_MODEL:  # invisible observers the mission scripts used
        return False
    return str(row.get("EXP_FACTOR", "0")).strip() not in ("0", "", "-")


def break_composite(s, uid):
    """Wall troop uid (a UnitProp) fell: the composite wall its zone row links (LinkedComositeProp) goes, by 0x50a3, the only
    way to 0x14091a0f0, which walks a composite's links (+0x390) and drops the collision of the sub-roots between it and
    its neighbours. 0x50d1's state reaches vt+0x200 alone: the model changes and the collision stays. Live 2026-11-05: 19214
    in state 4 through 0x50d1's path stayed solid (NO_PATH); through this one the hero walked the breach. The zones also
    link ids they don't place (12039, 18004), and the wall stays whole through the bar's fall (part 3 26:50-27:22): one
    state, at the fall."""
    t = s.data.get("zone_troops", {}).get(uid, {})
    p = zone_prop(s.data["spot"], t.get("LinkedComositeProp", -1))
    if p is not None and "ID_CP" in (prop_row(p["SmartPropTypeID"]) or {}):
        s.send(Writer(S2C_PROP_SET_STATE).raw(obf.u32(p["SmartPropID"])).i32(COMPOSITE_DESTROYED))
        log.info("composite %d falls with troop %d", p["SmartPropID"], uid)
        net.journal("composite", spot=s.data.get("spot"), prop=p["SmartPropID"], troop=uid)


def mission_troop_down(s, state, uid):
    """A mission troop fell: once every spawned hostile troop is down the next held wave comes (next_wave), and the
    mission is won when no wave is left. Only a hostile troop's fall decides it: an ally's or a staging troop's decides
    nothing. The last of a start force opens the barriers that wait on it (G6)."""
    from . import zone
    down = s.data.setdefault("down", set())
    down.add(uid)
    break_composite(s, uid)
    director.on_down(s, uid)
    t = s.data.get("zone_troops", {}).get(uid)
    if t is not None and (zone.np_troop(t["TroopTableID"]) or {}).get("NP_Grade") == "Boss" and hostile(t):
        send_actions(s, [ACT_BOSS_STATUS, uid, 0])      # the bar closes
    rules.on_down(s, uid, t)                            # Essex's totems and its Chaos Wedge
    if t is None or not hostile(t) or s.data.get("mission_won"):
        return
    guard = s.data.get("guards", {}).get(t.get("ForceNum"))
    if guard is not None:
        guard.discard(uid)
        if not guard:
            open_barriers(s, ("force", t.get("ForceNum")), "its force is down")
    left = [u for u, z in s.data.get("zone_troops", {}).items() if hostile(z) and u not in down]
    if not left and rules.round_break(s):               # the colosseum: the next round 15 s after the last fell
        return
    if not left and not next_wave(s) and not director.table_wins(s.data.get("spot")):
        if not rules.holds_win(s):                      # (the Goblin Nest's trial ends with its clock)
            mission_won(s, state)                       # (WIN = "table": its ("win",) step decides, Grey Fog)
        return
    point_to_enemy(s)


def mission_waves(spot, difficulty=0):
    """The hostile troops a mission holds back for its (unshipped) script, as waves in the order the fallback brings
    them (mission_plan): the target troops not spawned at the start (IsActivated / SpawnActivated 0), and the active
    ones of a later phase (G3b), grouped by ForceNum (and by a phase number their aliases carry: 20302's 라운드1..7).
    Order: by phase number when numbers name at least half the groups (G3b: 20347, 20304, 20301, 10327, 20327, 20918),
    groups without one after those; else by ForceNum; a group with a Boss-grade troop after the others of its phase
    (20347's boss F50001, 10234's troll F20080 after the bridge looters). Forces named for Hard / Hell only (하드, 헬) are
    left out on Normal, Hell-only ones on Hard, staging ones (G2) always. The groups are the data's; the order and the
    timing are ours (Q1, MISSIONS-WIRING G3)."""
    return [list(w) for w in mission_plan(spot, difficulty)["waves"]]


def force_names(spot):
    from . import zone
    return {f.get("ForceID"): str(f.get("ForceName") or "") for f in zone.for_spot(spot).get("Force") or []}


def for_difficulty(t, names, difficulty):
    """Whether a zone troop belongs to the room's difficulty (MISSIONS-WIRING G1): its Force name or its TroopAlias
    marks Hard / Hell (하드, 헬: 하드전용, 하드_, 헬용 ...): those are left out on Normal, Hell-only ones on Hard. The
    alias reading is ours from the designers' own words; before, only the held waves were filtered and 21 missions
    spawned their Hard-only troops on Normal."""
    marks = names.get(t.get("ForceNum"), "") + " " + str(t.get("TroopAlias") or "")
    if difficulty == 0 and ("하드" in marks or "헬" in marks):
        return False
    if difficulty == 1 and "헬" in marks and "하드" not in marks:
        return False
    return True


# Held forces wake by area (MISSIONS-WIRING G3; owner decision Q1 2026-09-27: wake by area, the next wave as fallback).
# The zone files keep 281 named EventBounds that read as the Lua's wake triggers (F5): activation words, or a ForceNum
# (포스활성화_23000, 적등장_20600, 포스20700AI부여). Every number here is ours.
WAKE_RANGE = 6000                # a held group wakes when the hero comes this close to one of its troops
BOUND_REACH = 3000               # an activation bound wakes the held groups within this of its edge
WAKE_WORDS = ("활성화", "등장", "스폰", "소환", "진입", "AI", "웨이브", "습격", "기습")
FORCE_IN_NAME = re.compile(r"\d{5}")
# Phase numbers in Force names and aliases (G3b, F6), three spellings: Phase1_ / 페이즈2 / 2페이즈 (20347, 20304, 20301,
# 20315); 1차 웨이브 / 1웨이브 / 1st Wave / 웨이브1 / 라운드1_ (10215, 10327, 20918, 20302); 1-1 .. 9-2 (20327).
PHASE_PATTERNS = (
    (re.compile(r"(?:phase|페이즈)\s*(\d+)", re.I), re.compile(r"(\d+)\s*페이즈")),
    (re.compile(r"(\d+)\s*(?:차|웨이브|st\b|nd\b|rd\b|th\b)", re.I),
     re.compile(r"(?:웨이브|wave|라운드|round)\s*(\d+)", re.I)),
    (re.compile(r"^\[?(\d+)-(\d+)"),),
)
# Held allies (G4, ours): a held team-0 force joins with its mirror, its step, or the nearest held group; these words
# in its Force name or an alias make it staging (10306's 연출포병 F10500, 10233's 죽는 연출용 부대), never spawned, as are
# troops the HUD does not show (UI_Visible False: observers, NOUI civilians such as 10358's villagers). Not the StringID:
# 아군연출 tags plain allied soldiers too (20304's camp-capture orcs, 20310's Gorzaniks).
ALLY_STAGING = STAGING_WORDS + ("컷씬", "죽는", "투명")   # 컷씬: 10321's [컷씬용 부대]
MIRROR = 10000                   # F2: held ally F and hostile F + 10000 are paired (56 of 149; 10320's 2xxxx / 3xxxx)
STEP = re.compile(r"^\((\d+)\)")  # F1: 10303's step aliases "(3)..."
PAIR_REACH = 15000               # the nearest held group joined, and the nearest force a barrier waits on, within this
# Barriers (G6; owner decision Q4 2026-09-27: gates open with their wave or when the hero comes near): placed
# trigger-only props (placed_trigger_only) whose resource name (smartpropresidtable) is a barrier (F8). A one-record
# 0x50d1 with the on state opens them (switch_on); the cast stays refused (prop_refusal: trigger only).
BARRIER_WORDS = ("문", "목책", "벽", "담장", "바리케이트", "커튼", "결계", "다리", "돌무더기", "쓰러진나무", "무너진돌",
                 "철창", "감옥", "마차", "건초더미", "투명프랍_빈값", "수레", "시체더미", "블레드_바위",
                 "무너지는돌", "사라지는나무", "가옥")   # 2026-09-28: 벽 (was 성벽 / 석벽 / 방어벽: + 광산벽, the mine
                                                         # walls), 수레 (Grey Rock's 24 mine carts stopped the hero at
                                                         # the mine entrance, live), 시체더미 (wolf corpse piles), 블레드_바위 (the Bled rock; 바위 alone also names 소리바위사막 and the roar cover rocks)   # + those the mission blocks name: 20347's falling rocks
                                                                  # 105 / 517, 10309's trees 85, 20310's magic wall
                                                                  # 78, 10235's tall house 474
TRAP_WORDS = ("지뢰", "함정", "신호탄", "소환진")      # placed the same way, not barriers
BARRIER_NEAR = 2500              # ours: a barrier opens when the hero comes this close
# Destination wins (G11, ours): entering this EventBound wins, with or without the targets left. 10361 "Move to New
# Hampton" (목적지, 142k from the start, r 2300); 10214 "Reach the top of Engelberg" (미션승리_세르파, beyond the lich).
DESTINATIONS = {10361: "목적지", 10214: "미션승리_세르파"}


def phase_number(text, kind):
    """The phase number a name carries in spelling `kind` (PHASE_PATTERNS index), as a tuple, or None; the first one in
    the name ("2페이즈 1번째 전투" is phase 2)."""
    found = [m for m in (rx.search(text) for rx in PHASE_PATTERNS[kind]) if m]
    return tuple(int(g) for g in min(found, key=lambda m: m.start()).groups()) if found else None


@functools.lru_cache(maxsize=None)
def phase_kind(spot):
    """The phase spelling of a mission (G3b): the one that numbers the most target troops by Force name or alias
    (20304 names both 페이즈1 / 페이즈2 and 보스전 웨이브1: the phases win; 10215's 석판페이즈 1차 / 석판페이지 3차 read by
    the 차), or None when nothing is numbered (ours)."""
    from . import zone
    names = force_names(spot)
    targets = [t for t in zone.for_spot(spot)["NPCTroopInfoData"] if hostile(t) and not staging(spot, t, names)]
    counts = [sum(1 for t in targets if troop_phase(t, names, k)) for k in range(len(PHASE_PATTERNS))]
    best = max(range(len(counts)), key=lambda k: counts[k])
    return best if counts[best] else None


def troop_phase(t, names, kind):
    """A troop's phase number (G3b): its alias's (20302's rounds split force 22000), else its Force name's."""
    if kind is None:
        return None
    return phase_number(str(t.get("TroopAlias") or ""), kind) or phase_number(names.get(t.get("ForceNum"), ""), kind)


def _centre(ts):
    return (sum(t["PosX"] for t in ts) / len(ts), sum(t["PosZ"] for t in ts) / len(ts))


def inside_bound(b, x, z):
    """Whether (x, z) lies in an EventBound: its BoundPoint polygon (type 2), else its circle (type 3)."""
    pts = [(p["BoundPointX"], p["BoundPointZ"]) for p in b.get("BoundPoint") or []]
    if b.get("EventBoundType") == 2 and len(pts) >= 3:
        inside = False
        for (x1, z1), (x2, z2) in zip(pts, pts[1:] + pts[:1]):
            if (z1 > z) != (z2 > z) and x < x1 + (z - z1) * (x2 - x1) / (z2 - z1):
                inside = not inside
        return inside
    return math.hypot(x - b["BoundCenterX"], z - b["BoundCenterZ"]) <= b["BoundRadius"]


@functools.cache
def prop_res_name(type_id):
    """The smartpropresidtable name of a switch prop's resource (SmartPropResID_SW), e.g. 스위치_열림_공용인간목책문."""
    rid = (prop_row(type_id) or {}).get("SmartPropResID_SW")
    return next((r["StringID"] for r in tables.sections("smartpropresidtable")["Basic"] if r["SmartPropResID"] == rid), "")


def invisible_wall(p, props):
    """A hidden trigger-only switch with collision (not placed, so never shown), e.g. the vanishing collision mesh 232
    or the transparent square / rectangle props 67 / 68 (정사각형 / 직사각형투명프랍) the mission scripts fenced each
    phase with: its collision stands although hidden (+0x31a is set at load), and only the original's script took it
    away. Live 2026-09-28: Tower of Moonlight's 10015 (232) and Grey Rock's 20085 (68) stopped the hero (owner: "we are
    blocked in another invisible wall", "and another wall T_T"); shown in state 2 their collision went (switch_on).
    One among attackable props is the Grey Fog kind, opened when they are broken (open_cleared_walls), not here."""
    row = prop_row(p["SmartPropTypeID"]) or {}
    if (not trigger_only(row) or placed_trigger_only(row) or "SmartPropResID_SW" not in row
            or row.get("CheckCollision_SW", "False") != "True"):
        return False
    return not any(q is not p and "HP_AT" in (prop_row(q["SmartPropTypeID"]) or {})
                   and math.hypot(q["PosX"] - p["PosX"], q["PosZ"] - p["PosZ"]) <= WALL_GUARD_RANGE for q in props)


def barrier(type_id):
    """A placed trigger-only prop that blocks the way (G6: BARRIER_WORDS in its resource name, not a trap)."""
    name = prop_res_name(type_id)
    return (placed_trigger_only(prop_row(type_id) or {}) and any(w in name for w in BARRIER_WORDS)
            and not any(w in name for w in TRAP_WORDS))


@functools.lru_cache(maxsize=None)
def mission_plan(spot, difficulty=0):
    """How a mission room runs without its unshipped Lua, read once per spot and difficulty from the zone file
    (MISSIONS-WIRING §2; every rule here is ours, read from the designers' names and placements). Keys:
    waves     the held target groups in fallback order (mission_waves; G3 / G3b)
    phases    {TroopID: phase} of the targets whose names carry a number: a later phase waits for the earlier (G3b)
    bounds    ((EventBound, first TroopIDs of the groups it wakes), ...) (G3)
    hand      TroopIDs of the player's troops, handed over as they spawn at the start (G5)
    start     held troops that come at the start: the player's (G5) and allies with nothing to wait for (G4)
    allies    {first TroopID of a group: the held allies that come with it} (G4)
    out       troops not spawned at the start: another difficulty, waiting in a group or with one, 2P-4P shares,
              staging allies
    barriers  {prop id: (prop, unit)}: unit ("wave", first TroopID) opens when that group wakes, ("force", ForceNum)
              when that start force is down, ("skip", ForceNum) (a force of another difficulty) only when the hero comes
              near; every one also opens when he does (G6). Hidden invisible walls (invisible_wall) join them, with
              None when no group is within reach (only the hero's approach opens those)
    guards    {ForceNum: TroopIDs} of the start forces a barrier waits on
    destination the EventBound whose entry wins (G11), or None"""
    from . import zone
    d = zone.for_spot(spot)
    troops = d["NPCTroopInfoData"]
    names = force_names(spot)
    kind = phase_kind(spot)
    active = lambda t: bool(t.get("IsActivated") and t.get("SpawnActivated"))
    target = lambda t: hostile(t) and not staging(spot, t, names)
    kept = [t for t in troops if for_difficulty(t, names, difficulty)]
    kept_ids = {t["TroopID"] for t in kept}
    out = {t["TroopID"] for t in troops} - kept_ids
    # G3 / G3b: the waves. A target of a later phase than the zone's first waits even when the zone activates it
    # (10215 석판 2-4차, 20315 페이즈2, 20918 2nd-4th Wave, 20327 4-1..9-2).
    numbered = {t["TroopID"]: troop_phase(t, names, kind) for t in troops if target(t)}
    first = min((k[0] for k in numbered.values() if k), default=None)
    groups = {}
    for t in kept:
        if not target(t):
            continue
        k = numbered[t["TroopID"]]
        if active(t) and not (k and k[0] > first):
            continue
        groups.setdefault((t.get("ForceNum"), k), []).append(t)
    boss = lambda g: any((zone.np_troop(t["TroopTableID"]) or {}).get("NP_Grade") == "Boss" for t in groups[g])
    phase = lambda g: (g[1] is None, g[1] or ())
    if 2 * sum(1 for g in groups if g[1]) >= len(groups):     # numbers name the phases: they order the fallback
        order = lambda g: phase(g) + (boss(g), g[0] or 0)
    else:                                                     # a few numbered groups (10215's tablet, 20305's spirit
        order = lambda g: (boss(g), g[0] or 0) + phase(g)     # waves at the boss): ForceNum orders, numbers only gate
    waves = tuple(tuple(groups[g]) for g in sorted(groups, key=order))
    waiting = {t["TroopID"] for w in waves for t in w}
    out |= waiting
    phases = {u: k[0] for u, k in numbered.items() if k}
    # G3: the bounds. One naming a ForceNum wakes that force's groups; one with an activation word the groups near it.
    forces = {t.get("ForceNum") for t in troops}
    bounds = []
    for b in d.get("EventBound") or []:
        name = str(b.get("EventBoundName") or "")
        if not name or name == str(b.get("EventBoundID")):
            continue
        named = {int(n) for n in FORCE_IN_NAME.findall(name)} & forces
        if named:
            ids = {w[0]["TroopID"] for w in waves if w[0].get("ForceNum") in named}
        elif any(word in name for word in WAKE_WORDS):
            reach = BOUND_REACH + b["BoundRadius"]
            ids = {w[0]["TroopID"] for w in waves if any(
                math.hypot(t["PosX"] - b["BoundCenterX"], t["PosZ"] - b["BoundCenterZ"]) <= reach for t in w)}
        else:
            continue
        if ids:
            bounds.append((b, frozenset(ids)))
    # G5: the player's troops, the 1P share only, marked ones first, then those already on the field, up to the limit
    rank = {t["TroopID"]: players_troop(spot, t, names) for t in kept}
    players = [t for t in kept if rank[t["TroopID"]]]
    others = {t["TroopID"] for t in players if OTHER_SHARE.search(str(t.get("TroopAlias") or ""))}
    mine = sorted((t for t in players if t["TroopID"] not in others),
                  key=lambda t: (rank[t["TroopID"]], not active(t), t["TroopID"]))
    hand = [t["TroopID"] for t in mine[:hand_limit(spot, difficulty)]]
    if director.hand(spot):                             # the table's, from the original (the camps: one lesson troop,
        hand = [u for u in director.hand(spot) if u in kept_ids]    # then the mock battle's three)
        mine = [t for t in kept if t["TroopID"] in hand]
    out |= {t["TroopID"] for t in players if t["TroopID"] in others and not active(t)}
    start = {t["TroopID"] for t in mine if t["TroopID"] in hand and not active(t)}
    # G4: held allies join with their mirror, their step, the nearest held group, else at the start
    held = {}
    for t in kept:
        if t.get("TeamNum") == PLAYER_TEAM and not active(t) and t["TroopID"] not in out and t["TroopID"] not in hand:
            held.setdefault(t.get("ForceNum"), []).append(t)
    allies = {}
    for f, ts in held.items():
        out |= {t["TroopID"] for t in ts}
        if f in director.late_allies(spot):
            continue                                    # a step brings it in ("wake": spawn_force), not its group
        ts = [t for t in ts if not any(w in str(t.get("TroopAlias") or "") for w in ALLY_STAGING)
              and (zone.np_troop(t["TroopTableID"]) or {}).get("UI_Visible") != "False"]
        if not ts or any(w in names.get(f, "") for w in ALLY_STAGING):
            continue                                    # staging, observers and NOUI civilians stay out
        pair = ally_pair(f, ts, troops, kept_ids, waiting, waves)
        if pair is None:
            out -= {t["TroopID"] for t in ts}
            start |= {t["TroopID"] for t in ts}
        elif pair:
            allies.setdefault(pair, []).extend(ts)
    # G6: each barrier waits on the nearest held group, start force or other-difficulty force (centre within 15 000)
    units = [(("wave", w[0]["TroopID"]), _centre(w)) for w in waves]
    at_start, skipped = {}, {}
    for t in troops:
        if not target(t) or t["TroopID"] in waiting:
            continue
        if t["TroopID"] not in kept_ids:
            skipped.setdefault(t.get("ForceNum"), []).append(t)
        elif active(t):
            at_start.setdefault(t.get("ForceNum"), []).append(t)
    units += [(("force", f), _centre(ts)) for f, ts in at_start.items()]
    units += [(("skip", f), _centre(ts)) for f, ts in skipped.items()]
    barriers = {}
    for p in d["SmartPropData"]:
        wall = invisible_wall(p, d["SmartPropData"])
        if not (wall or barrier(p["SmartPropTypeID"])):
            continue
        if units:
            unit, (x, z) = min(units, key=lambda u: math.hypot(u[1][0] - p["PosX"], u[1][1] - p["PosZ"]))
            if math.hypot(x - p["PosX"], z - p["PosZ"]) <= PAIR_REACH:
                barriers[p["SmartPropID"]] = (p, unit)
                continue
        barriers[p["SmartPropID"]] = (p, None)            # no group to wait on: opens when the hero comes near (a
                                                          # barrier far from every group never opened: 21 of 161 red
                                                          # curtains, 13 of 32 barricades before 2026-09-28)
    guards = {f: frozenset(t["TroopID"] for t in at_start[f]) for f in
              {u[1] for _, u in barriers.values() if u and u[0] == "force"}}
    destination = next((b for b in d.get("EventBound") or [] if spot in DESTINATIONS
                        and b.get("EventBoundName") == DESTINATIONS[spot]), None)
    return {"waves": waves, "phases": phases, "bounds": tuple(bounds), "hand": tuple(hand), "start": frozenset(start),
            "allies": {k: tuple(v) for k, v in allies.items()}, "out": frozenset(out), "barriers": barriers,
            "guards": guards, "destination": destination}


def ally_pair(f, ts, troops, kept_ids, waiting, waves):
    """The held group a held ally force joins (G4, ours): its mirror F + 10000 (F2) when that is a held group, at the
    start (None) when the mirror stands from the start, never (0) when the mirror is of another difficulty (10324's
    Hard reinforcements F10200 / F10400); else the group of its step "(n)" (10303); else the held group nearest to it
    within PAIR_REACH; else the start (None). The group is named by its first TroopID."""
    mirror = [t for t in troops if t.get("ForceNum") == f + MIRROR and t.get("TeamNum") != PLAYER_TEAM]
    if mirror:
        w = next((w for w in waves if any(t.get("ForceNum") == f + MIRROR for t in w)), None)
        if w is not None:
            return w[0]["TroopID"]
        if any(t["TroopID"] in kept_ids and t["TroopID"] not in waiting and t.get("IsActivated") and
               t.get("SpawnActivated") for t in mirror):
            return None
        if not any(t["TroopID"] in kept_ids for t in mirror):
            return 0
    step = lambda t: (STEP.match(str(t.get("TroopAlias") or "")) or (None, None))[1]
    steps = {step(t) for t in ts} - {None}
    w = next((w for w in waves if any(step(t) in steps for t in w)), None)
    if w is not None:
        return w[0]["TroopID"]
    if waves:
        x, z = _centre(ts)
        w = min(waves, key=lambda w: math.hypot(_centre(w)[0] - x, _centre(w)[1] - z))
        if math.hypot(_centre(w)[0] - x, _centre(w)[1] - z) <= PAIR_REACH:
            return w[0]["TroopID"]
    return None


def on_hero_position(s):
    """The hero moved (combat.hero_moved, every 0x50b0), or a troop handed to the player did (troop_sync: the Lunawing
    he flies in Sortie I): in a mission room, entering its destination wins (G11); a held group wakes when one of them
    comes within WAKE_RANGE of one of its troops or enters a bound that wakes it (G3), unless an earlier phase still
    waits or stands (G3b) or the director's table holds its force (director.held); a barrier opens when one comes
    within BARRIER_NEAR of it (G6)."""
    plan = s.data.get("plan")
    pos = s.data.get("hero_pos")
    places = [(p[0], p[2]) for p in ([pos] if pos else []) + list(s.data.get("troop_pos", {}).values())]
    if plan is None or not places or s.data.get("mission_won"):
        return
    held = director.held(s.data.get("spot"))
    prev = s.data.get("hero_prev")
    for k, (x, z) in enumerate(places):
        director.on_position(s, x, z, (prev[0], prev[2]) if k == 0 and pos and prev else None)
        if plan["destination"] is not None and inside_bound(plan["destination"], x, z):
            log.info("mission %s: the hero reached %s", s.data.get("spot"), plan["destination"]["EventBoundName"])
            mission_won(s, s.state)
            return
        entered = {u for b, ids in plan["bounds"] if inside_bound(b, x, z) for u in ids}
        for wave in list(s.data.get("waves", ())):
            if wave[0].get("ForceNum") in held:
                continue
            if wave[0]["TroopID"] in entered or any(math.hypot(t["PosX"] - x, t["PosZ"] - z) <= WAKE_RANGE
                                                    for t in wave):
                if not phase_waits(s, wave):
                    wake(s, wave, "the hero came near")
        for prop_id, (p, unit) in list(s.data.get("barriers", {}).items()):
            if math.hypot(p["PosX"] - x, p["PosZ"] - z) <= BARRIER_NEAR and prop_id not in director.held_props(
                    s.data.get("spot")):
                open_barriers(s, unit, "the hero came near", only=prop_id)


def phase_waits(s, wave):
    """Whether a numbered group must wait (G3b): a group of an earlier phase is still held or standing."""
    phases = (s.data.get("plan") or {}).get("phases", {})
    p = phases.get(wave[0]["TroopID"])
    if p is None:
        return False
    held = {t["TroopID"] for w in s.data.get("waves", ()) for t in w}
    down, troops = s.data.get("down", set()), s.data.get("zone_troops", {})
    return any(q < p and (u in held or (u in troops and u not in down)) for u, q in phases.items())


def wake(s, wave, why):
    """Bring in a held group (built enabled) with the allies that join it (G4) and open its barriers (G6); the number of
    its troops that spawned. A group already brought in (a director step woke it meanwhile) brings nothing, nor does an
    ally a step brought before (Tower's camp soldiers, joined to the scorpions' wave, come for the camp scenes)."""
    if wave not in s.data.get("waves", ()):
        return 0
    s.data["waves"].remove(wave)
    n = sum(1 for t in wave if spawn_zone_troop(s, t))
    for t in s.data.get("wave_allies", {}).pop(wave[0]["TroopID"], ()):
        if t["TroopID"] not in s.data.get("zone_troops", {}):
            spawn_zone_troop(s, t)
    open_barriers(s, ("wave", wave[0]["TroopID"]), "its force woke")
    send_actions(s, [ACT_ENABLE_ALL_TROOPS, 1, 1])
    director.on_wake(s, {t.get("ForceNum") for t in wave})
    log.info("mission %s: force %s wakes (%s), %d troops (%d groups held)", s.data.get("spot"), wave[0].get("ForceNum"),
             why, n, len(s.data["waves"]))
    net.journal("wake", spot=s.data.get("spot"), force=wave[0].get("ForceNum"), why=why, n=n, held=len(s.data["waves"]))
    return n


def open_barriers(s, unit, why, only=None):
    """Open the barriers waiting on unit (or the one prop `only`): switch_on, and they wait no more (G6). Those the
    table holds (HOLD_PROPS) open only by name: a force waking or falling leaves them shut (Grey Rock's cages)."""
    held = director.held_props(s.data.get("spot"))
    for prop_id, (p, u) in list(s.data.get("barriers", {}).items()):
        if (prop_id == only) if only is not None else (u == unit and prop_id not in held):
            del s.data["barriers"][prop_id]
            switch_on(s, p)
            log.info("barrier %d (type %s) opens: %s", prop_id, p["SmartPropTypeID"], why)
            net.journal("barrier", spot=s.data.get("spot"), prop=prop_id, type=p["SmartPropTypeID"], why=why)


# The mission panel and the way to the enemy, which the unshipped mission Lua drew (BATTLE.md B61 / B74; handlers read
# 2026-09-27). ActGuiAddTitleToMissionSituation 0xc7ea (team, text) -> HUDQuestInfo 0x140775210, ActGuiAddObjective
# GroupToMissionSituation 0xc7ec (team, group) -> 0x140775290, ActGuiAddTextOnlyObjectiveToMissionSituation 0xc7f6
# (team, group, text) -> 0x1407756d0: every id is a missiontext id of the room's map (HUDQuestInfo::Update
# MissionSituation 0x1407793b0 looks up the group's and each line's); team 0xff = every player.
# ActGuiShowDirectionToTargetTroop 0xc74c (troop uid, seconds) -> GenericCamera::MissionMoveDirFxPlay 0x140aa6450:
# the direction effect toward a troop for that long.
ACT_SITUATION_TITLE, ACT_SITUATION_GROUP, ACT_SITUATION_LINE = 0xc7ea, 0xc7ec, 0xc7f6
# ActGuiAddGageObjectiveToMissionSituation 0xc81e (0x140b37c30; switch 0x140b2b2b2): (team, group, text, value, max)
# -> 0x140b5d690 -> HUDQuestInfo::SetMissionSituationGageConition 0x140775ab0: a condition of type 4 under the group,
# found by its text and updated (+0xc value, +0x10 max), or added. Read 2026-09-28; not seen live.
ACT_TROOP_USE_SKILL = 0xc3df      # ActTroopUseSkillbySkillID 0x140b33ce0: caster, target (0xffff none), a third, ability
ACT_SITUATION_GAUGE = 0xc81e
# ActGuiCompleteObjectiveToMissionSituation 0xc828 (0x140b37e50): (team, text, complete 1 / 0) -> 0x140b5d7b0 ->
# HUDQuestInfo 0x140775f40: the condition with that text shown "(Complete)", in green (the original's panel, frames of
# playthrough part 3 26:20-37:40). Read 2026-09-28; not seen live.
ACT_SITUATION_DONE = 0xc828
# ActGuiAddValueObjectiveToMissionSituation 0xc800 (0x140b37700): (team, group, text, value, max, kind): kind 0 ->
# 0x140b5d540, a count shown "value/max" (Tower's "Defeat Winged Wyrms 0/3", frames of part 2 12:10), kind 1 -> the
# gauge's 0x140b5d690. Read 2026-09-28; not seen live.
ACT_SITUATION_VALUE = 0xc800
# ActGuiAddTroopsBarToMissionSituation 0xc8b4 (0x140b38f70, read 2026-10-24): (team, group, text, ref kind, ref id, a6)
# -> 0x140b2e700 by kind (0 a troop: 0x140b5d850 -> HUD 0x140c54000 -> HUDQuestInfo 0x140776540, which drops the group,
# finds the troop by its u16 uid and hands its troop list to 0x14077a460: team 0xff or the player's, one bar per text,
# the troops' hp summed). UpdateTroopBar 0x140779f40 draws it below the quest tracker: the text from the map's
# missiontext, the bar at the troops' hp %, and a6 > 0 is a troop uid whose portrait is the bar's icon and the bar's
# key for its updates (0x140ec9450). The client follows the troops' hp itself; an absent troop leaves an empty bar.
ACT_SITUATION_TROOPS_BAR = 0xc8b4
TROOPS_BAR_TROOP = 0                       # ref kind 0: one troop by uid (1-3: 0x140b5d8e0 / d880 / d8b0, unread)
TROOPS_BAR_FORCE = 2                       # ref kind 2: a force: HUDQuestInfo::SetForceTroopBarToMissionSituation
                                           # (0x140c54020, read 2026-10-24): the Player of that owner id (the zone
                                           # ForceNum, np_owner) by 0x140b42f20, the troops it holds then (+0x178)
                                           # in the bar's list, their hp summed. 0x14077a460 returns at once when a
                                           # bar of that text is up: one bar per text, the first send's
ACT_DIRECTION_TO_TROOP = 0xc74c
# ActGuiSetBossStatusUi 0xc7e2 (troop uid, on 1 / off 0) -> 0x140c54d00: troop +0x11b8 = on and the HUD's boss bar
# 0x140d236a0 for that troop (B63, W149-153 the Mountain Troll's vitality bar). Shown for nptrooptable NP_Grade Boss
# hostile troops in mission rooms (ours: the Lua chose when).
ACT_BOSS_STATUS = 0xc7e2
ALL_TEAMS = 0xff
POINT_S = 8                      # ours: how long the pointer shows
POINT_BEYOND = 6000              # ours: point only when the nearest enemy is farther than this from the hero
SUCCESS_LABELS = ("Success Conditions", "Winning Conditions")
FAIL_LABELS = ("Failure Conditions", "Losing Conditions")
# Panels mission_text's matching cannot pick (MISSIONS-WIRING G12; ours, from each map's missiontext rows), in its
# shape (title id or None, ((group id, (line ids)), ...)): Death Woods' blocks under titles that are not the spot names
# (10312 1600 "Death Woods Swidden Area", 10323 1700 "Outside the Death Woods"); the camps' own blocks instead of the
# Controls camp's 700 (their objectives follow the failure heading in the text: 30010 / 30020 then 30030..30060),
# every camp with its mock battle (the walkthrough: "Mock Battle" in each camp); 10211 / 20357 / 20358 / 10362, whose
# success lines follow the failure heading too; 20318's failure lines 641 / 651 sit outside the ten ids after 630;
# 10235 has only "Mission Success" 200 / "Mission Failure" 300 headings; 20915 Borderline's block 130 / 140 under the
# title 200 that follows it; 20920 shares that map and none of its blocks is its own. The subjugations (rules.py):
# Grey Wood 10327's panel as the footage shows it (part 6 20:16 / 20:54: "Eliminate the remaining thieves" 621 alone
# under the success heading), Jackdaw Canyon 20327's 700 block, whose time limit and waves the troop-only notices
# 800-840 follow (the 600 block "Defend Jackdaw Canyon Base" names the hero; inferred).
MISSION_PANELS = {
    10327: (600, ((610, (621,)), (640, (650,)))),
    20327: (700, ((710, (711,)), (720, (721,)))),
    10312: (1600, ((1610, (1620,)), (1630, (1640,)))),
    10323: (1700, ((1710, (1720,)), (1730, (1740,)))),
    10345: (30000, ((30010, (30030, 30040)), (30020, (30050, 30060)))),
    10346: (None, ((530100, (530110, 530111, 530112, 530120)), (530200, (530210, 530220)))),
    10347: (540000, ((540100, (540110, 540111, 540112, 540120)), (540200, (540210, 540220)))),
    10348: (555000, ((555010, (555030, 555040)), (555020, (555050, 555060)))),
    10349: (566000, ((566010, (566030, 566040)), (566020, (566050, 566060)))),
    10211: (3000, ((3010, (3030,)), (3020, (3040,)))),
    20357: (15000, ((15010, (15030, 15040, 15050, 15060, 15070)), (15020, (15080,)))),
    20358: (21800, ((21810, (21830, 21840, 21850, 21860)), (21820, (21870,)))),
    10362: (6030, ((6040, (6060,)), (6050, (6070,)))),
    20318: (600, ((610, (620,)), (630, (640, 641, 651)))),
    10235: (None, ((200, (210, 220, 230, 240)), (300, (310,)))),
    20915: (200, ((130, (131, 132)), (140, (141,)))),
    20920: None,
    10315: (700, ((710, (711, 720)), (730, (740,)))),      # the tape part 14 4:40-5:40 (not the 19001 block)
    10309: (600, ((610, (620,)), (630, (640, 650)))),      # the tape part 9 f_00845 (rules.py adds 660 and 680)
}


def _plain(text):
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^\[[^\]]*\]\s*", "", str(text).lower()))


@functools.lru_cache(maxsize=None)
def spot_names():
    """{spot: [plain NAME, plain WAR_SPOT_NAME]} from text/eng/textspotname_eng."""
    out = {}
    for r in tables.sections(r"text\eng\textspotname_eng")["TextTable"]:
        key, text = list(r.values())[:2]
        spot, _, kind = str(key).partition("/")
        if kind in ("NAME", "WAR_SPOT_NAME") and _plain(text):
            out.setdefault(spot, []).append(_plain(text))
    return out


@functools.lru_cache(maxsize=None)
def mission_text(spot):
    """The mission panel of a spot from its map's missiontext (data/info/missiontext/eng/<Map_File>.csv): (title id or
    None, ((group id, (line ids)), ...)), or None. A block is a "... Success Conditions" row with its objectives up to
    the next "... Failure Conditions" row, and that row's lines (ids within 10 after it, else the next one). The block
    is the one whose title (the row before it) is the spot's name, else contains it; else a map's only block, else its
    only block without a title row; a title shows only when it names
    the spot. Spots sharing a map with other missions under other titles get no panel (10353, 10355). MISSION_PANELS
    names the block where this matching picks none or the wrong one."""
    if spot in MISSION_PANELS:
        return MISSION_PANELS[spot]
    row = tables.by_id("spottable").get(str(spot)) or {}
    try:
        table = tables.sections("missiontext\\eng\\" + str(row.get("Map_File", "")).lower())["TextTable"]
    except KeyError:
        return None
    rows = [(int(r["textID"]), str(r["text"]).strip()) for r in table if str(r.get("textID", "")).strip().isdigit()]
    text = dict(rows)
    ids = sorted(text)
    names = spot_names().get(str(spot), [])
    blocks = []
    for k, (i, t) in enumerate(rows):
        if not t.endswith(SUCCESS_LABELS):
            continue
        fail = next((j for j in ids if j > i and text[j].endswith(FAIL_LABELS)), None)
        if fail is None:
            continue
        title = rows[k - 1][0] if k and not rows[k - 1][1].endswith(SUCCESS_LABELS + FAIL_LABELS) else None
        plain = _plain(text[title]) if title is not None else ""
        named = 2 if plain in names else int(bool(plain) and any(n in plain or plain in n for n in names))
        wins = tuple(j for j in ids if i < j < fail and text[j])
        loses = tuple(j for j in ids if fail < j < fail + 10 and text[j]) or \
            tuple(j for j in ids if fail < j <= fail + 10 and text[j])
        groups = tuple(g for g in ((i, wins), (fail, loses)) if g[1])
        blocks.append((title if named else None, groups, named, title is None))
    untitled = [b for b in blocks if b[3]]
    pick = (max(blocks, key=lambda b: b[2]) if any(b[2] for b in blocks) else blocks[0] if len(blocks) == 1
            else untitled[0] if len(untitled) == 1 else None)
    return (pick[0], pick[1]) if pick and pick[1] else None


def mission_guide(s):
    """At a mission room's start: its panel (unless its table sends it with a step, director "panel start") and,
    when the enemy is out of sight, the pointer."""
    if not director.panel_later(s.data["spot"]):
        mission_panel(s)
    point_to_enemy(s)


def mission_panel(s):
    """The room's start panel: the table's PANEL, else mission_text."""
    got = director.start_panel(s.data["spot"]) or mission_text(s.data["spot"])
    if got:
        title, groups = got
        acts = [[ACT_SITUATION_TITLE, ALL_TEAMS, title]] if title is not None else []
        for group, lines in groups:
            acts.append([ACT_SITUATION_GROUP, ALL_TEAMS, group])
            s.data.setdefault("panel_groups", set()).add(group)
            acts += [[ACT_SITUATION_LINE, ALL_TEAMS, group, line] for line in lines]
        send_actions(s, *acts)
        log.info("mission %d: panel %s", s.data["spot"], got)
        net.journal("panel", spot=s.data["spot"], what="start", ids=[a[-1] for a in acts])


def panel_line(s, group, line):
    """A line added to the mission panel under group (director "panel"), the group first when not yet shown."""
    groups = s.data.setdefault("panel_groups", set())
    if group not in groups:
        groups.add(group)
        send_actions(s, [ACT_SITUATION_GROUP, ALL_TEAMS, group])
    send_actions(s, [ACT_SITUATION_LINE, ALL_TEAMS, group, line])
    log.info("mission %s: panel line %s / %s", s.data.get("spot"), group, line)
    net.journal("panel", spot=s.data.get("spot"), what="line", ids=[group, line])


def panel_gauge(s, group, text, value, top):
    """A bar in the mission panel under group (director "gauge"), the group first when not yet shown; sent again, it
    updates the bar."""
    groups = s.data.setdefault("panel_groups", set())
    if group not in groups:
        groups.add(group)
        send_actions(s, [ACT_SITUATION_GROUP, ALL_TEAMS, group])
    send_actions(s, [ACT_SITUATION_GAUGE, ALL_TEAMS, group, text, value, top])
    net.journal("panel", spot=s.data.get("spot"), what="gauge", ids=[group, text], value=value, top=top)


def panel_count(s, group, text, value, top):
    """A count in the mission panel under group, "value/top" (director "count"); sent again, it updates."""
    groups = s.data.setdefault("panel_groups", set())
    if group not in groups:
        groups.add(group)
        send_actions(s, [ACT_SITUATION_GROUP, ALL_TEAMS, group])
    send_actions(s, [ACT_SITUATION_VALUE, ALL_TEAMS, group, text, value, top, 0])
    net.journal("panel", spot=s.data.get("spot"), what="count", ids=[group, text], value=value, top=top)


def panel_troops_bar(s, text, uid):
    """A troop's hp bar under the quest tracker, labelled text, its portrait for an icon (director "troops bar"); sent
    once the client has the troop (troop_order), since the client builds the bar from the troop it finds then."""
    troop_order(s, uid, [ACT_SITUATION_TROOPS_BAR, ALL_TEAMS, 0, text, TROOPS_BAR_TROOP, uid, uid])
    log.info("mission %s: troops bar %s over troop %s", s.data.get("spot"), text, uid)
    net.journal("panel", spot=s.data.get("spot"), what="bar", ids=[text], troop=uid)


def panel_force_bar(s, text, force):
    """One hp bar under the quest tracker for a whole force (director "force bar"), its troops' hp summed by the
    client, the first troop's portrait its icon: sent once every troop of the force in the room is bound, since the
    client takes the troops its Player holds then (TROOPS_BAR_FORCE)."""
    down = s.data.get("down", set())
    uids = sorted(u for u, t in s.data.get("zone_troops", {}).items() if t.get("ForceNum") == force and u not in down)
    if not uids:
        return
    act = [ACT_SITUATION_TROOPS_BAR, ALL_TEAMS, 0, text, TROOPS_BAR_FORCE, force, uids[0]]
    bound = lambda: s.data["bound"] if "bound" in s.data else set(uids)   # a client that never binds (tests): at once
    sent = []

    def send(_s=None):
        if not sent and set(uids) <= bound():
            sent.append(True)
            send_actions(s, act)
            log.info("mission %s: troops bar %s over force %s", s.data.get("spot"), text, force)
            net.journal("panel", spot=s.data.get("spot"), what="bar", ids=[text], force=force)
    waiting = [u for u in uids if u not in bound()]
    for u in waiting:                              # troop_bound runs it at each bind; the last one sends
        s.data.setdefault("await_bind", {}).setdefault(u, []).append(send)
    if not waiting:
        send()


def panel_done(s, text):
    """The panel's condition with that text marked complete (director "done")."""
    send_actions(s, [ACT_SITUATION_DONE, ALL_TEAMS, text, 1])
    log.info("mission %s: panel %s complete", s.data.get("spot"), text)
    net.journal("panel", spot=s.data.get("spot"), what="done", ids=[text])


def point_to_enemy(s):
    """Point the hero at the nearest standing hostile troop (by its zone position) when it is beyond POINT_BEYOND:
    the original's scripts led the player on (W555 red path, arrows); the distance rule is ours."""
    down = s.data.get("down", set())
    alive = [(u, z) for u, z in s.data.get("zone_troops", {}).items()
             if hostile(z) and u not in down and not z.get("Hidden")]      # (the Goblin Nest's real goblins, to find)
    if not alive:
        director.point_ahead(s)                         # the story's next place, when its table waits on one
        return
    x, _, z = s.data.get("hero_pos") or start_pos(s)
    uid, t = min(alive, key=lambda a: (a[1]["PosX"] - x) ** 2 + (a[1]["PosZ"] - z) ** 2)
    if (t["PosX"] - x) ** 2 + (t["PosZ"] - z) ** 2 > POINT_BEYOND ** 2:
        send_actions(s, [ACT_DIRECTION_TO_TROOP, uid, POINT_S])
        log.info("mission %s: pointing at troop %d", s.data.get("spot"), uid)


def next_wave(s):
    """The fallback (Q1 b): bring in the next held group of a mission room in order (wake), the first whose phase does
    not wait (phase_waits: in ForceNum order a later phase can come first); False when none is left."""
    held = director.held(s.data.get("spot"))
    waves = s.data.get("waves")
    while waves:
        free = [w for w in waves if w[0].get("ForceNum") not in held]      # the table's own forces wait for it
        if not free:
            return True                                 # not won while the table still has forces to bring
        if wake(s, next((w for w in free if not phase_waits(s, w)), free[0]), "the fallback"):
            return True
    return False


def mission_difficulty(c, spot):
    """The difficulty the mission at spot was entered on (0 Normal, 1 Hard, 2 Hell): the 0x3f48 entry's byte kept in
    c["mission"] (world.enter_spot); 0 for any other room (quest-warp missions, fields)."""
    m = c.get("mission") or {}
    return m.get("difficulty", 0) if m.get("spot") == spot else 0


def kill_exp(c, np_troop_id):
    """Hero exp for a wiped NP troop: nptrooptable EXP_FACTOR x lvexptable %ExpAdjustMonster at LevelDiff = the troop's
    LEVEL_CURRENT - the hero's level (a bonus up to x1.15 for troops 1-5 levels above, 0 at +-10) x %ExpTypeRate HERO,
    rounded down. Pinned by the walkthrough's Sawtooth mercenaries (level 8, EXP_FACTOR 4 and 6: "Exp Worth: 3-6exp";
    the 3 needs a rate under 1 for a hero above the troop, hence the sign). Exp per troop wiped, not per unit, is
    inferred (the Mist Field and Sawtooth troops are one unit each)."""
    from . import zone
    row = zone.np_troop(np_troop_id) or {}
    factor = float(row.get("EXP_FACTOR", "0") or 0)
    if factor <= 0 or not str(row.get("LEVEL_CURRENT", "")).isdigit():
        return 0
    lv = tables.sections("lvexptable")
    diff = max(-10, min(10, int(row["LEVEL_CURRENT"]) - c.get("level", 1)))
    rate = next((float(r["ExpRate"]) for r in lv["ExpAdjustMonster"] if r["LevelDiff"] == str(diff)), 0.0)
    hero = next((float(r["ExpRate"]) for r in lv["ExpTypeRate"] if r["ExpType"] == "HERO"), 1.0)
    return int(factor * rate * hero + 1e-9)


# The difficulty variants: %NP_Troop_Change / %NP_Leader_Change (Info.pkg hash 0x5cb86f03dea69d54, INVENTORY "Unnamed
# tables"): each NP troop's (3,485) and leader's (576) Hard and Hell row. Mostly the id with a "20" / "30" in front
# (103080 -> 20103080, rift boss 1091110 -> 201091110), but not always: 2-12 / 2-13's Hell takes the Hard row
# (130010 -> 20130010; 131020 -> 20131020 though 30131020 exists), the Goblin Nest's settings are other goblins
# (137020 -> 137040 Vision, 137060 Enchanter), the story missions keep their Normal row (133080: DESIGNER-NOTES §1).
DIFFICULTY_CHANGE = 0x5cb86f03dea69d54
_CHANGES = {"troop": ("NP_Troop_Change", "NPTroop_StringID", "C_NPT_StringID_Hard", "C_NPT_StringID_Hell"),
            "leader": ("NP_Leader_Change", "NPLeader_StringID", "C_NPL_StringID_Hard", "C_NPL_StringID_Hell")}
VARIANT_PREFIX = ("", "20", "30")


@functools.lru_cache(maxsize=None)
def _changes(kind):
    section, key, hard, hell = _CHANGES[kind]
    return {r[key]: (r[hard], r[hell]) for r in tables.by_hash(DIFFICULTY_CHANGE)[section]}


def _variant(kind, base, difficulty, exists):
    """The kind's row for `base` on a difficulty (the change table's, else the id with its prefix), when `exists` has
    it; the id itself on Normal, for none (-100), an id already a variant, or a named row that does not exist."""
    if not 0 < difficulty < 3 or base in (None, -100, 0):
        return base
    row = _changes(kind).get(str(base))
    if row is not None:
        named = row[difficulty - 1]
        return int(named) if named.isdigit() and exists(int(named)) else base
    if base >= 10000000:                               # already a variant (a respawn, a reward dummy's own row)
        return base
    variant = int(VARIANT_PREFIX[difficulty] + str(base))     # no change row (ours: the Unknown Corridor 1-90, the
    return variant if exists(variant) else base               # climax 1-18 and 1-00 have Hard / Hell rows and none)


def difficulty_troop(np_troop_id, difficulty):
    """The nptrooptable row a zone troop is spawned as on a difficulty (the zone file names the Normal troop), from
    %NP_Troop_Change: 103080 -> 20103080 on Hard (hp 561 -> 1122), 1091110 -> 201091110; the id itself on Normal or
    when the named row does not exist (10303's Hell boss 30103290)."""
    from . import zone
    return _variant("troop", np_troop_id, difficulty, zone.np_troop)


@functools.lru_cache(maxsize=None)
def _unit_counts():
    return {r["NPTroop_StringID"]: (r["Unit_Count_Hard"], r["Unit_Count_Hell"])
            for r in tables.by_hash(DIFFICULTY_CHANGE)["NP_Troop_Change"]}


def difficulty_units(np_troop_id, units, difficulty):
    """The units of a zone troop (the zone's Normal NP troop id) on a difficulty: %NP_Troop_Change Unit_Count_Hard /
    _Hell (247 of 3,485 rows), read as the client's own loader does (0x1418becb0, parser 0x14193cd90): "n%" is a
    factor n / 100 with no count, anything else a count (atoi: "-" is 0) with the factor 1; units x factor (rounded
    down, ours) + count. Fort Valley's orc infantry 106050 "4" / "10", the climax 1-18's 20-unit troops "120%", an
    ally of 1-12 "-12" on Hard. That the count adds (not replaces) is read from the rows: every absolute one is on a
    troop the zone sizes (UNIT_COUNT 0, "0명"), 30-unit 132080 takes "5" on Hell, and a negative one is an ally's."""
    if not 0 < difficulty < 3:
        return units
    text = (_unit_counts().get(str(np_troop_id)) or ("-", "-"))[difficulty - 1].strip()
    if text.endswith("%"):
        return int(units * float(text[:-1]) / 100 + 1e-9)
    count = text.lstrip("-")
    return units + (int(text) if count.isdigit() else 0)


def difficulty_leader(leader_id, difficulty):
    """A zone troop's NP leader on a difficulty, from %NP_Leader_Change (Fort Valley's 106030 -> 20106030 / 30106030),
    for his %Leader loot row (loot.roll_drops). His hp, skills and quest names stay on the zone's Normal row
    (spawn_zone_troop): npname gives 10 variants other name ids than quests count (120030 -> 30120030 loses 2509)."""
    return _variant("leader", leader_id, difficulty, np_leader)


# The mission grade: the original's %Mission_Grade where the mission has a row (loot.grade_points: clear time and
# damage bands, participants, death penalty; pinned by the footage's result windows, 2026-09-29), else ours (ROADMAP
# Q3, decided by the owner 2026-09-27: BATTLE-WIRING's par-time proposal; the rule is ours, its inputs are data): par =
# the sum of nptrooptype %System MISSION_BASE_TIME (8..266; read as seconds, inferred) of the hostile troops the room
# spawned, waves included; a clear at or under par is S, then A / B / C up to 1.25 / 1.5 / 2 x par, D beyond; each
# hero death lowers it one grade. The index is the mission_reward %DATA Grade and record +0x284 (0x140c5bdb0: 0 ->
# rank icon 5, 1 -> 4, 2 -> 3, 3 -> 2, else 1; that the icons are S..D is inferred).
GRADES = ("S", "A", "B", "C", "D")
GRADE_PAR = (1.0, 1.25, 1.5, 2.0)
# Reward cards the result screen lets the player open (record +0x29f): one at every grade. The footage's five result
# windows (Tower S, Forest of Fog S, Deathwood S and A, the spear camp C) each open one of the four cards; the grade
# changes what the card holds (its mission_reward row's category), not how many.
CARDS = 1
# The victory window closes by the client's own clock (BattleFieldSubMissionResult's update 0x14085ef60, constants
# 0x142e31cd0..cdc: 3 / 10 / 16 / 23 s; its close 0x140859c40 shows the HUD's Mission Complete button); nothing is sent
# then. The tape (part 2, the 2 fps sets 1149-1155 and 1171-1175): "Mission Succeeded" first at 19:10.0 (19:09.5
# blank), the window gone at 19:32.0, Tower's "Mission Complete" notice from 19:32.5: 22.5-23 s after the record. A
# mission's "closed" steps (director.window_closed) play this long after 0x5044.
RESULT_CLOSE_S = 23
REWARD_DUMMY = "보상용"         # nptrooptable StringID mark of the designers' invisible reward troops (DESIGNER-NOTES F3)


@functools.lru_cache(maxsize=None)
def troop_type_times():
    """{nptrooptype NPTroopType: MISSION_BASE_TIME}."""
    return {r["NPTroopType"]: int(r["MISSION_BASE_TIME"]) if r["MISSION_BASE_TIME"].isdigit() else 0
            for r in tables.sections("nptrooptype")["System"]}


def mission_par(s):
    """The room's par time: MISSION_BASE_TIME of each hostile troop it spawned (s.data["zone_troops"], the difficulty
    variant's nptrooptable NPTroopType), summed. Grey Fog 10358: 640; Tower of Moonlight 10233: 2,658."""
    from . import zone
    times = troop_type_times()
    return sum(times.get((zone.np_troop(t["TroopTableID"]) or {}).get("NPTroopType"), 0)
               for t in s.data.get("zone_troops", {}).values() if hostile(t))


def mission_grade(elapsed, par, deaths=0):
    """Grade index 0 (S) .. 4 (D) of a clear in `elapsed` seconds against `par`, one lower per hero death. Without a par
    (no hostile troop with a MISSION_BASE_TIME) only the deaths grade (ours)."""
    step = next((i for i, k in enumerate(GRADE_PAR) if elapsed <= k * par), len(GRADE_PAR)) if par > 0 else 0
    return min(len(GRADES) - 1, step + max(0, deaths))


def reward_row(spot, difficulty, grade):
    """The mission_reward %DATA row (ID = spot, Difficulty Normal / Hard / Hell, Grade), or None: the camp and story
    tutorials (10358, 10353, 10355, 10356, 10361, 10362, 20920) have none, their quests pay; the Unknown Corridor
    (10540-10546) has no C / D rows."""
    name = DIFFICULTY[difficulty].title()
    return next((r for r in tables.sections("mission_reward")["DATA"]
                 if r["ID"] == str(spot) and r["Difficulty"] == name and r["Grade"] == GRADES[grade]), None)


def mission_exp(c, spot, difficulty, row, clears):
    """Hero exp of a won mission: its reward row's Hero_Exp x ExpRate (under 1 on some grades of 10327 and 20326) x
    lvexptable %ExpAdjustMission at LevelDiff = spottable Recom_Level_<difficulty + 1> - the hero's level (clamped to
    +-10, the sign as kill_exp's; no recommended level: x1, ours) x %Repeat_Penalty <Difficulty>_ExpRate at
    Enter_Number = `clears`, the clears of this spot on this difficulty before this one (capped at the last row) x
    %ExpTypeRate HERO, rounded down. The penalty and the level adjustment both apply only where spottable
    Repeat_Penalty_Control is True (most story and climax spots; False on 10327 and the other PVE_REPEAT, rift, camp and
    daily spots, which pay the full row at any level): the tape's 19 result windows (planning/rules/MISSIONS.md X1)
    reproduce so, among them the camps 10347 (2,228 at level 16, Recom 15) and 10349 (5,612 at 20-22, Recom 20) and
    the Grey Wood subjugation 10327 (1,100 to a hero of 20+, Recom 11). The client pins the index: its
    result handler 0x14085b300 reads the clear count (0x140674c20 -> 0x140674bb0, spot and difficulty) before
    0x140cffea0 bumps it (0x140674a80), and shows that row's integer as "clear bonus %d%%" (window +0x5c, the
    Actual_Value 300 / 200 / 150 / 100 by the int read; zeroed when record +0x017 is 0); its gate, spot row +0x401, is
    read as Repeat_Penalty_Control by name (inferred)."""
    lv = tables.sections("lvexptable")
    rate = float(row["ExpRate"] or 1)
    spot_row = tables.by_id("spottable").get(str(spot)) or {}
    recom = str(spot_row.get(f"Recom_Level_{difficulty + 1}", ""))
    if spot_row.get("Repeat_Penalty_Control") == "True" and recom.isdigit() and int(recom) > 0:
        diff = str(max(-10, min(10, int(recom) - c.get("level", 1))))
        rate *= next((float(r["ExpRate"]) for r in lv["ExpAdjustMission"] if r["LevelDiff"] == diff), 1.0)
    rate *= repeat_rate(spot, difficulty, clears)
    rate *= next((float(r["ExpRate"]) for r in lv["ExpTypeRate"] if r["ExpType"] == "HERO"), 1.0)
    return int(int(row["Hero_Exp"]) * rate + 1e-9)


def repeat_rate(spot, difficulty, clears):
    """lvexptable %Repeat_Penalty <Difficulty>_ExpRate at Enter_Number = clears (capped at the last row) where spottable
    Repeat_Penalty_Control is True, else 1 (mission_exp)."""
    if (tables.by_id("spottable").get(str(spot)) or {}).get("Repeat_Penalty_Control") != "True":
        return 1.0
    rows = sorted(tables.sections("lvexptable")["Repeat_Penalty"], key=lambda r: int(r["Enter_Number"]))
    pick = next((r for r in rows if int(r["Enter_Number"]) == clears), rows[-1])
    return float(pick[DIFFICULTY[difficulty].title() + "_ExpRate"])


def repeat_gold(c, spot, difficulty, gold):
    """Kill gold in a repeated mission (rules census ECONOMY B7): the pile x the room's repeat_rate (the %Repeat_Penalty
    ExpRate of the clears before this room, where Repeat_Penalty_Control is True), floored. The entry window's
    "EXP, Gold Bonus 300% / 200%" names both; the tape: Kedington Castle Wall 10320's ogre troop 120270 (543-664) paid
    193 + 177 + 186 = 556 on its first clear (part 12 TrE5TmRNJno f_00495, 16:28) and 133 + 134 + 116 = 383 = 0.66 x
    580 on the second ("200%", part 13 tNALOjTtbSI f_00199-f_00201; the "(+N)" there is that period's event bonus, also
    on every exp line), its 2-3 gold soldiers 2 on the first and 1 on the second."""
    if not gold or not 0 <= difficulty < len(DIFFICULTY):
        return gold
    clears = c.get("cleared", {}).get(str(spot), [0, 0, 0])[difficulty]
    return int(gold * repeat_rate(spot, difficulty, clears) + 1e-9)


def troop_mission_exp(spot, difficulty, row, clears):
    """Each deployed troop's exp of a won mission (D13): the reward row's Troop_Exp x ExpRate x %ExpTypeRate TROOP (1),
    at every clear: no repeat penalty (the tape's Kedington 10320: its second clear paid the hero int(20,309 x 0.9 x
    0.66) but each troop the full 1,191, doubled by the event: part 13 7:14 2,382; the first, part 12 17:00, 1,191).
    No level adjustment: every deployed troop gets the same (DATAMINE-ROUND2 §4.1), so the hero's %ExpAdjustMission is
    not applied (ours). `spot`, `difficulty` and `clears` are kept for the callers."""
    from . import troops
    v = str(row.get("Troop_Exp", "0"))
    base = int(v) if v.isdigit() else 0
    rate = float(row["ExpRate"] or 1) * troops.exp_type_rate("TROOP")
    return int(base * rate + 1e-9)


def card_pool(c, spot, difficulty):
    """The items a result card draws from where the grade's mission_reward row names no category (285 of 988 rows:
    the rifts 10335-10344 / 20351-20356, the extremes 20502 / 20504, 10302, 50116, 20908-20911 ...; ours, what those
    paid is not known): mission_reward_entranceui %Base for (spot, difficulty), the list the entry window shows
    (ItemType Normal: ItemCode; Category: %Category's <HERO>_ItemCode for the hero's class; 10233 Normal: Glen's
    101104113, 102104113, 151104113 .. 155104113). Where the row names a category (703 rows), the card rolls it
    through %Table instead (loot.reward_category, open_card). Codes without an item row are left out."""
    from . import hero
    ui = tables.sections("mission_reward_entranceui")
    cats = {r["CategoryID"]: r for r in ui["Category"]}
    column = hero.HERO_CODE[c["class"]] + "_ItemCode"
    pool = []
    for r in ui["Base"]:
        if r["SpotID"] != str(spot) or r["Difficulty"] != DIFFICULTY[difficulty].title():
            continue
        code = r["ItemCode"] if r["ItemType"] == "Normal" else cats.get(r["ItemCode"], {}).get(column, "")
        if code.isdigit() and items.row(int(code)):
            pool.append(int(code))
    return pool


def recom_level(spot, difficulty):
    """spottable Recom_Level_<difficulty + 1> (0 on the tutorials; Enter_Level is 1 everywhere)."""
    level = str((tables.by_id("spottable").get(str(spot)) or {}).get(f"Recom_Level_{difficulty + 1}", "0"))
    return int(level) if level.isdigit() else 0


def recom_party(spot, difficulty):
    """spottable Recom_Party_<difficulty + 1>, the entry window's "Rec. Players" and the divisor of the result
    window's Participants Points (loot.grade_points); "-" (91 graded rows) or none is 1."""
    n = str((tables.by_id("spottable").get(str(spot)) or {}).get(f"Recom_Party_{difficulty + 1}", ""))
    return int(n) if n.isdigit() and int(n) > 0 else 1


@functools.lru_cache(maxsize=None)
def pooled_missions(hero_class, difficulty):
    """[(recommended level, spot)] of the spots whose entry list has items for the class at the difficulty."""
    name = DIFFICULTY[difficulty].title()
    spots = {int(r["SpotID"]) for r in tables.sections("mission_reward_entranceui")["Base"] if r["Difficulty"] == name}
    return sorted((recom_level(sp, difficulty), sp) for sp in spots if card_pool({"class": hero_class}, sp, difficulty))


@functools.lru_cache(maxsize=None)
def _dummy_ids():
    return {int(r["NPTROOP_ID"]) for r in tables.load("nptrooptable") if REWARD_DUMMY in r.get("StringID", "")}


def reward_dummies(spot, difficulty):
    """[(zone troop, table id)] the invisible reward troops of `spot` its script killed on the win to pay the
    mission's reward (DESIGNER-NOTES F3): the zone troops whose nptrooptable row the designers marked 보상용, of the
    room's difficulty (for_difficulty), as its variant (difficulty_troop): 10233 39000 (133260 -> 903121
    `1-33_노말_B1N`), 10235 25000 (135740 -> 903321), 20915 / 20919 49158 (263200, Hard 20263200), and the raids'
    per-phase ones (20950, 20951). The footage's Tower win (part 2, 19:32-19:40) shows the result: after the cards, a
    loot bag at the hero with Adventurer Bottoms and Troop Coin (B1N's gear, B5N's 760000030) and its gold picked up."""
    from . import zone
    if not zone.available(spot):
        return []
    ids, names = _dummy_ids(), force_names(spot)
    return [(t, tid) for t in zone.for_spot(spot)["NPCTroopInfoData"]
            if for_difficulty(t, names, difficulty) and (tid := difficulty_troop(t["TroopTableID"], difficulty)) in ids]


def fallback_pool(c, spot, difficulty):
    """The cards of a mission without an entry list of its own (38 of 116 missions for every class: the story and camp
    tutorials, Grey Fog 10358, 10301 / 10304 / 10308, 10335-10344, 20311, 20351-20354 ...). The owner, 2026-09-28: "even
    at the end of mission you have to chose between the 4 cards to loot". What they held is not in the shipped data;
    ours: the list of the mission nearest in recommended level (the mission's, else the hero's) that has one for the
    hero's class (the lower level, then the lower spot, on a tie); a level-3 hero in Grey Fog gets Tower of Moonlight's
    level-4 set."""
    near = pooled_missions(c["class"], difficulty)
    if not near:
        return []
    level = recom_level(spot, difficulty) or c.get("level", 1)
    _, other = min(near, key=lambda e: (abs(e[0] - level), e[0], e[1]))
    return card_pool(c, other, difficulty)


def mission_won(s, state):
    """S2C 0x5044 (Packet_MissionCompletePVE): i16 0, u8 won 1, u32 (left 0), u8 n 1, one 673-byte player record: +0x285
    u16 player id, +0x10 i32 hero class, +0x16 / +0x20 level before / after (the troop slots' level-up mark compares the
    same pair, +0x53 / +0x32), +0x17 u64 hero exp, +0x284 grade, troop slots k = 1..3 at +0x44k (the deployed deck
    troops in room-uid order, else the coded -1 at +0x45), +0x297 u64 the barracks share, +0x29f coded u16 reward
    cards. The
    window's six numbers (UISceneMissionSuccess Init: the block's u32, +0x287, +0x274, +0x28f, +0x0, +0x27c) are
    read, in that order, as its six labels Clear
    Time (seconds), Clear Points, Damage Points, Participants Points, Death Penalty (negative) and Total (inferred
    from the order: the footage's window lists them so).
    The grade is a timed rule's (rules.on_won: the Unknown Corridor's time left, the Goblin Nest's trial; a target
    fallen after the clock pays nothing), else the original's where the mission has a %Mission_Grade row
    (loot.grade_points of the whole seconds since the room's start and the hero's deaths; the damage count is not
    measured: 0), else mission_grade of that time against mission_par, less the deaths (ours). The reward row pays
    mission_exp through world.add_exp before the record goes out (0x124a, a level-up in the room); the mission's
    reward dummies drop their loot and gold at the hero (reward_dummies, drop_loot); the cards (0x404c, open_card)
    roll the row's category (loot.reward_category), else draw from card_pool / fallback_pool. The deployed deck troops
    get the row's Troop_Exp (troop_mission_exp, deck_won: one level at most) and pay Troop_Mission_Clear AP;
    the barracks pool gets a quarter of it every win (troops.mission_pool, 0x1363 before the record). The victory
    window's button sends 0x4040. MissionLevelClear counts for conditions naming this mission (IngSpot) at the entry
    difficulty or ANY."""
    from . import quest, troops, world
    if s.data.get("mission_won"):                       # once: !win during the ending, then the ending's own finish
        return
    if director.before_win(s, state):                  # the mission's ending lines play first (director "won" steps)
        return
    s.data["mission_won"] = True
    c = hero_char(s)     # as game_login keeps it (world.add_exp)
    spot = s.data["spot"]
    difficulty = s.data.get("difficulty", mission_difficulty(c, spot))
    difficulty = difficulty if 0 <= difficulty < len(DIFFICULTY) else 0     # out of range is Normal, as the client's
                                                                            # entry check 0x140d68040 takes it
    now = time.monotonic()
    secs = int(now - s.data.get("started_at", now))                       # no room start: 0 s
    deaths = s.data.get("hero_deaths", 0)
    wipes = s.data.get("troop_wipes", 0)                # the window's death count: each deck troop wipe (the tape) and
                                                        # each hero death ([C]); our par grade takes the hero's only
    from . import party
    party.on_mission_won(s, state, c, spot, difficulty)  # a rift's cleared step and pay, a raid's dummy loot (party.py)
    ruled = rules.on_won(s, c)                          # a timed rule's (grade, pays); the day's clear counted
    if ruled is None and windowless(spot):
        end_without_window(s, state, c, spot, difficulty, secs)
        return
    band = None if ruled else loot.grade_row(spot, DIFFICULTY[difficulty].title())
    points = par = None
    if ruled:
        grade = ruled[0]
    elif band:                                                             # the original's grade
        points = loot.grade_points(band, secs, 0, deaths + wipes, recom_party(spot, difficulty))
        grade = points["grade"]
    else:                                                                  # ours (Q3), where the original had none
        par = mission_par(s)
        grade = mission_grade(secs, par, deaths)
    row = reward_row(spot, difficulty, grade) if ruled is None or ruled[1] else None
    before, start = c.get("level", 1), hero_exp_percent(c)
    clears = c.get("cleared", {}).get(str(spot), [0, 0, 0])[difficulty]
    from . import events                                 # a boost event that is on multiplies the rounded amounts
    exp = events.boosted("hero_exp", mission_exp(c, spot, difficulty, row, clears)) if row else 0
    if exp:
        world.add_exp(s, state, exp, why=f"mission {spot} grade {GRADES[grade]}")
    troop_exp = events.boosted("troop_exp", troop_mission_exp(spot, difficulty, row, clears)) if row else 0
    paid = deck_won(s, state, c, troop_exp)
    saved = troops.mission_pool(c, troop_exp)        # "Barracks Saved EXP": one share every win (T2.4, A5)
    if saved:
        s.send(troops.pool_packet(c))                # before the record: the window's gauge reads the pool now
    for t, tid in reward_dummies(spot, difficulty):     # the script killed them at the end: their loot at the hero
        got = loot.roll_drops(spot, tid, difficulty_leader(t.get("NPLeaderID"), difficulty))
        drop_loot(s, got, events.boosted("gold", repeat_gold(c, spot, difficulty, roll_gold(tid))))
        log.info("reward dummy %d (%d) dropped %s", t["TroopID"], tid, got)
    graded = any(r["ID"] == str(spot) for r in tables.sections("mission_reward")["DATA"])
    category = loot.reward_category(row) if row else None
    if category is None and (row or not graded):   # a spot with rows but none for this grade pays nothing (Unknown
        pool = card_pool(c, spot, difficulty) or fallback_pool(c, spot, difficulty)      # Corridor C / D on our grade)
    else:
        pool = []
    cards = min(CARDS, LAST_CARD + 1) if category is not None or pool else 0
    s.data["cards"] = {"allowed": cards, "pool": pool, "category": category, "open": {}}
    rec = bytearray(MISSION_RECORD)
    struct.pack_into("<i", rec, 0x10, c["class"])
    rec[0x16], rec[0x20] = before, c.get("level", 1)
    struct.pack_into("<Q", rec, 0x17, exp)
    rec[0x21], rec[0x1f] = start, hero_exp_percent(c)    # the hero gauge's percent before / after (as +0x51 / +0x52)
    for k in (1, 2, 3):
        rec[0x45 + 0x44 * k:0x49 + 0x44 * k] = obf.u32(0xFFFFFFFF)
    for k, (t, level_before, gained, start) in enumerate(paid[:3], 1):  # the troop slots (0x14085b300 reads them
        at = 0x44 * k                                                   # at +0x44k: +0x45 coded id, +0x53 / +0x32
        rec[0x45 + at:0x49 + at] = obf.u32(t["id"])                     # the level before / after, +0x3b u64 the
        rec[0x53 + at], rec[0x32 + at] = level_before, t["level"]       # exp kept, +0x33 u64 the exp now, +0x51 /
        struct.pack_into("<QQ", rec, 0x33 + at, t["exp"], gained)       # +0x52 the gauge's percent before / after)
        rec[0x51 + at], rec[0x52 + at] = start, troops.exp_percent(t)
    struct.pack_into("<Q", rec, 0x297, saved)   # Barracks Saved EXP (the window shows +0x297 less the Noble share)
    if points:                                  # the window's numbers (see above); Death Penalty shown negative
        struct.pack_into("<q", rec, 0x0, -points["death"])
        for off, key in ((0x274, "damage"), (0x27c, "total"), (0x287, "clear"), (0x28f, "party")):
            struct.pack_into("<Q", rec, off, points[key])
    rec[0x284] = grade
    struct.pack_into("<H", rec, 0x285, MY_SLOT)
    rec[0x29f:0x2a1] = obf.u16(cards)
    s.send(Writer(S2C_MISSION_COMPLETE).u16(0).u8(1).u32(secs).u8(1).raw(bytes(rec)))
    s.later(RESULT_CLOSE_S, lambda: director.window_closed(s))      # the table's "closed" steps (Tower's notice)
    quest.on_mission_clear(s, state, spot, difficulty)
    from . import guild
    guild.on_mission(s, state, row)                      # the reward row's Guild_Exp / Point / Contribution (guild.py)
    record_clear(c, spot, difficulty)
    count_state_clear(s, state, spot)
    state.save()
    log.info("mission %d won: %d s, %d hero deaths, %d troop wipes, %s -> grade %s, exp %d, %d cards of %s", spot,
             secs, deaths, wipes, points or (f"rule {ruled}" if ruled else f"par {par}"), GRADES[grade], exp, cards, category or pool)
    net.journal("room", ev="won", spot=spot, secs=secs, par=par, points=points and points["total"], grade=GRADES[grade],
                exp=exp, cards=cards, category=category)


def hero_exp_percent(c):
    """The hero's exp as a whole percent of his level's need (world.hero_need; 0 at the cap): the result record's hero
    gauge ends, +0x21 before / +0x1f after (0x14085b300 reads them with the levels +0x16 / +0x20; PlayExp 0x14085d650
    animates (after - before) x 100 - start + end, as troops.exp_percent's troop slots; the flooring is ours)."""
    from . import world
    level = c.get("level", 1)
    need = world.hero_need(level)
    if not need or level >= world.hero_max_level():
        return 0
    return min(100, c.get("exp", 0) * 100 // need)


@functools.lru_cache(maxsize=None)
def _graded_spots():
    return ({r["ID"] for r in tables.sections("mission_reward")["DATA"]}
            | {r["ID"] for r in tables.by_hash(loot.GRADES)["Mission_Grade"]})


# Missions with reward rows whose tape still shows no result window: the prologue 50116 (part 1: its last scenes
# 12:34-15:16, then "Mist Field" and the camp at 17:31; no window, no grade, no card in between)
NO_WINDOW = frozenset({50116})


def windowless(spot):
    """A mission the original ended with no result window (decision B2, owner 2026-09-30: "vanilla, no window"): no
    mission_reward row and no %Mission_Grade row on any difficulty (Grey Fog 10358, Lunawing I / II 10361 / 10362,
    10353, 10355, 10356, 20920 ...), and NO_WINDOW. The tape shows Grey Fog's (part 1): after the finale, loading
    (27:48-28:08), then the field's end scene 11_Village_chief and "[Field] Mist Field" at 29:02, no window, no grade,
    no card; its quest (1150301) paid the exp."""
    return spot in NO_WINDOW or str(spot) not in _graded_spots()


def end_without_window(s, state, c, spot, difficulty, secs):
    """The win of a windowless mission: the clear counts (the quest's MissionLevelClear, the clear list), the deck
    troops' clear as any win's (deck_won, no exp: no reward row), and the room is left at once: 0x4041 unasked
    (leave_mission; the client's handler 0x140d003f0 takes it without a request pending, as it takes the escape
    0x4049 from the game connection), to the quest's end spot, where the return warp's EnterScript plays the end
    scene. That the original left by this message is ours: only its effect is on the tape. A table that names the
    next mission (NEXT: Sortie I 10361 -> warp 622, Sortie II 10362) goes on into it instead (world.continue_mission;
    the tape part 3 5:23, Sortie I's end straight into the loading screen of Sortie II's map), keeping the quest's end
    spot for that one's win; an end spot that is a Field of the mission's own map is left as a field warp
    (world.leave_for_same_map_field: a 0x4041 would leave the client's same-map flag set there); without a world
    session it leaves as any other."""
    from . import quest, world
    deck_won(s, state, c, 0)
    quest.on_mission_clear(s, state, spot, difficulty)
    record_clear(c, spot, difficulty)
    count_state_clear(s, state, spot)
    if spot == world.TUTORIAL_SPOT:                     # the prologue played to its end: never again at the next
        c["tutorial_done"] = True                       # login (the client says so too, 0x10d6, as it leaves 50116)
    state.save()
    nxt = director.next_warp(spot)
    log.info("mission %d won: %d s, no result window (none in the original), %s", spot, secs,
             f"on through warp {nxt}" if nxt else "leaving")
    net.journal("room", ev="won", spot=spot, secs=secs, window=False, **({"next": nxt} if nxt else {}))
    if nxt is not None and world.continue_mission(s, state, nxt):
        return
    if world.leave_for_same_map_field(s, state):
        return
    leave_mission(s, state)


def open_card(s, g, state, b):
    """C2S 0x404c on session s (it may come on either connection) for the cards kept by the room session g -> S2C
    0x404d: one pick of the room's reward category for the hero's class (loot.roll_category, its count), else an item
    drawn from the room's pool (uniform, without putting it back: ours), count 1, into the bag (world.add_item; what
    does not fit is mailed). A card index past 3, a card beyond the allowed count, nothing to draw or no won room ->
    the empty card (code -1, still 9 bytes); the same index again shows its item again without a second grant. No
    auto-leave follows (decision A10): the room stays until the player presses Mission Complete (S2C_AUTO_LEAVE)."""
    if not b:
        log.warning("reward card not understood")
        return
    card = b[0]
    cards = g.data.get("cards") if g is not None else None
    reply = lambda code, n: s.send(Writer(S2C_REWARD_CARD).u16(MY_SLOT).u8(card).raw(obf.u32(code)).raw(obf.u16(n)))
    if not cards or card > LAST_CARD:
        reply(EMPTY_CARD, 0)
        return
    if card in cards["open"]:
        reply(*cards["open"][card])
        return
    if len(cards["open"]) >= cards["allowed"] or not (cards["pool"] or cards.get("category")):
        reply(EMPTY_CARD, 0)
        return
    from . import hero, world
    if cards.get("category"):
        c = hero_char(g)
        code, n = (loot.roll_category(cards["category"], hero=hero.HERO_CODE[c["class"]]) or [(EMPTY_CARD, 0)])[0]
    else:
        code, n = cards["pool"].pop(random.randrange(len(cards["pool"]))), 1
    cards["open"][card] = (code, n)
    net.journal("loot", ev="card", card=card, code=code, n=n, name=items.name(code) if n else None)
    if n:
        world.add_item(s, state, code, n, why=f"reward card {card}")
    reply(code, n)
    log.info("reward card %d: item %d x%d", card, code, n)


def count_state_clear(s, state, spot):
    """The region clear achievements (titletable %AchievementInfo StateMissionClear 31 / 32 / 96 / 114, Condition1 =
    spottable State 10 / 11 / 90 / 13: "Clear Eastern Settlement Mission %1% times", "Clear Hexter Mission ..."; rules
    census ECONOMY M2): every won mission counts once for its spot's State (the titles 60112 at 7, 60113 at 15 ...)."""
    from . import titles
    region = (tables.by_id("spottable").get(str(spot)) or {}).get("State")
    if region:
        titles.achieve(s, state, "StateMissionClear", add=1, cond={1: region})


def record_clear(c, spot, difficulty):
    """A won mission in the character's clear list c["cleared"][spot] = clears on Normal, Hard, Hell: what 0x108f
    (world.cleared_packet) sends. The client's SpotClear spot requirement (E_RequireType 11, 0x140d67fb5 ->
    0x140674b60) passes only when the required spot is in that list (20324 Urka North needs 20306, 20308 Daroka 20321,
    10324 10314, 10322 10309, 10212 10211); the counts by difficulty feed the repeat-penalty lookup (0x140674c20, called
    with the room's difficulty +0xa48). That they count every clear, not today's, is inferred."""
    c.setdefault("cleared", {}).setdefault(str(spot), [0, 0, 0])[difficulty] += 1


def return_group(back, qid):
    """(group, warp) a finished mission returns to on spot back: the FIELD warp on back that requires the mission's
    quest (warpinfo Require1 FinishOrDoingQuest; 30001: 1150301 -> 10350 group 0, EnterScript 11_Village_chief;
    30002: 1150406 -> group 2, 9_Refugee_camp, the refugee camp at the Tower of Moonlight where Glen 6009, Golden
    Hammer 6002 and Jade 6078 of the next quests stand), else (0, None). Reading these warps as the missions' way back
    is inferred from that match (no other FIELD warp requires a quest)."""
    from . import tables
    return next(((int(r["SPGroupID"]), int(r["ID"])) for r in tables.load("warpinfo")
                 if r["SpotID"] == str(back) and r["WARP_POSITION"] == "FIELD" and qid is not None
                 and r["Require1_Type"] == "FinishOrDoingQuest" and r["Require1_Value"] == str(qid)), (0, None))


def door_way_back(c, m):
    """(spot, pos) of the mission door the hero left by, when the win ends there, else None. The tape after Grey Rock
    (45:04-45:16): the hero stands at door 501 under "Greyrock Fortress Entrance", in the field he left (10359: the
    panel reads "Different Area", the quest's EndSpot being 10350), and Glen 6010 beside him takes 1150601; 1150602's
    SpotWarp 705 is what brings him to 10350. So a door mission ends at its door (zone start point of the mission's
    MISSION warp) in c["spot"], the field left, if the NPC who takes the quest stands there. Ours beyond the tape: a
    finisher elsewhere (1160113: Duran 6058 is not in 10351) leaves the end spot's rule to decide, so nobody is
    stranded, and a quest-less room keeps its old way back. No footage shows those. The client starts a field at the
    group's point whatever 0x4041 names (live 07:27:52), so the room moves him there: arrive_at_door."""
    from . import tables, zone
    left, row = c.get("spot"), tables.by_id("questtable").get(str(m.get("quest"))) or {}
    if row.get("Finish_Type") != "Npc" or left is None or not zone.available(left):
        return None
    z = zone.for_spot(left)
    if not any(str(n["TableID"]) == row.get("Finish_Value") for n in z["NPCInfo"]):
        return None
    doors = {int(r["ID"]) for r in tables.load("warpinfo")
             if r["SpotID"] == str(m.get("spot")) and r["WARP_POSITION"] == "MISSION"}
    for p in z["PlayerStartPointInfoData"]:
        if p.get("LongWarpID") in doors and p["StartPointInfoData"]:
            pt = p["StartPointInfoData"][0]
            return left, (round(pt["PosX"]), 0, round(pt["PosZ"]))
    return None


def mission_way_back(c):
    """Where a won mission ends, on the character (its record c["mission"] is used up): the mission's end spot (the
    quest's EndSpot, else the spot it was entered from) at its return group's first start point (return_group), that
    group as the next field entry's (field_group), and the return warp for that entry's 0x5641, once (mission_return;
    its EnterScript plays on the room's OnEnter); with no return warp, the door the hero left by when door_way_back
    finds one. Returns (spot, group, pos). Read by leave_mission (0x4040) and by an Esc exit after the win (world:
    0x4048 in a won room)."""
    from . import world
    m = c.pop("mission", None) or {}
    back = m.get("back", c.get("spot", world.START_SPOT))
    group, warp = return_group(back, m.get("quest"))
    door = door_way_back(c, m) if warp is None else None
    if door:
        back, pos = door
        c["door_return"] = {"spot": back, "pos": list(pos)}
    else:
        pos = ((group and world.zone_start(back, group)) or world.zone_start(back) or world.TOWN_ENTRY.get(back)
               or tuple(c.get("pos", world.START_POS)))
    c["spot"], c["pos"], c["field_group"] = back, list(pos), [back, group]
    if warp is not None:
        c["mission_return"] = {"spot": back, "group": group, "warp": warp}
    return back, group, pos


def leave_mission(s, state):
    """C2S 0x4040 after the result -> S2C 0x4041 (0x140d003f0; always 2 + 14 bytes, a non-zero result crashes): kind 0,
    destination 2 (town / field), coded spot, u8, packed position: mission_way_back's end spot and position; the
    client then loads it and enters its field room the usual way, at that group, with the return warp once. 0x4041
    itself names no group or warp (0x140d003f0, read); unlike 0x4049 it ends the battle and loads whatever the map
    (it has no common+0x1728 test, read; a same-map end spot such as Grey Fog's 10350 is not yet seen live)."""
    c = hero_char(s)
    back, _, pos = mission_way_back(c)
    state.save()
    x, y, z = pos
    q, p15 = obf.pos_xz(x, z)
    s.send(Writer(S2C_MISSION_LEAVE).u16(0).u8(0).u8(2).raw(obf.u32(back)).u8(0).raw(q).raw(struct.pack("<h", y))
           .u8(p15))
    log.info("left the mission for %d at %s", back, pos)
    net.journal("room", ev="leave", spot=s.data.get("spot"), back=back)


def _roll_money(section, key, value, roll):
    row = next((r for r in tables.sections("item_drop_money")[section] if r[key] == str(value)), None)
    if row is None or not row["DropGold_Max"].isdigit():
        return 0
    lo, hi = int(row["DropGold_Min"]), int(row["DropGold_Max"])
    return lo + (roll or random.randrange)(hi - lo + 1) if hi > lo else lo


def roll_gold(np_troop_id, roll=None):
    """item_drop_money %Troop DropGold_Min..Max of an NP troop (0 when it has no row): the troop's own row, which on
    Hard / Hell is the variant it spawned as (171 of the 701 variant rows pay otherwise: 20103290 85-105, 103290
    72-89)."""
    return _roll_money("Troop", "NPTroopID", np_troop_id, roll)


def roll_leader_gold(np_leader_id, roll=None):
    """item_drop_money %Leader DropGold_Min..Max of an NP leader (246 rows, 143 paying above 1: 107050 3-4), the
    difficulty's variant (difficulty_leader: Fort Valley's 106030 1-2, 20106030 0-1); 0 for none (-100) or no row. It
    goes on the troop's own pile when the troop is wiped (troop_down)."""
    return 0 if np_leader_id in (None, -100, 0) else _roll_money("Leader", "NPLeaderID", np_leader_id, roll)


def drop_loot(s, got, gold, at=None):
    """A wiped troop's loot where it fell (its quest drops and normal loot, loot.roll_drops): `at` its last 0x50b0
    position, the header's obool FALSE and the packed position (Packet_RewardBoxCreate 0x140d04240 places the bag and
    the gold there; the tape part 4 44:32 shows a chest several metres from the hero); no position (a reward dummy's
    on a win, a troop never synced): obool TRUE, at the local hero. An item bag (kept until picked, 0x4052) and a gold
    pile (0x50fb). One player: the loot is theirs (the 17.12.19 patch made general mission loot personal)."""
    from . import items
    got = [(code, n) for code, n in got if items.row(code)]      # an unknown code would assert on the client
    if at is not None:
        q, p15 = obf.pos_xz(at[0], at[2])
        place = bytes([OBOOL_FALSE]) + q + struct.pack("<h", at[1]) + bytes([p15])
    else:
        place = bytes([OBOOL_TRUE]) + bytes(7)
    records = []
    for kind, amount, entries in ((0, 0, got), (TYPE_GOLD, gold, [])):
        if not entries and not amount:
            continue
        drop_id = s.data["next_drop"] = s.data.get("next_drop", FIRST_DROP_ID - 1) + 1
        if kind == TYPE_GOLD:
            s.data.setdefault("gold_drops", {})[drop_id] = amount
        else:
            s.data.setdefault("drops", {})[drop_id] = {i: e for i, e in enumerate(entries)}
        rec = (place + struct.pack("<H", MY_SLOT) + bytes([1]) + obf.u40(amount)
               + struct.pack("<iB", drop_id, kind) + bytes([len(entries)]))
        for i, (code, n) in enumerate(entries):
            rec += obf.u16(n) + obf.u32(code) + obf.u16(i)
        records.append(rec)
    if records:
        s.send(Writer(S2C_REWARD_BOX).u8(len(records)).raw(b"".join(records)))
        log.info("loot on the ground: items %s, gold %d", got, gold)
        net.journal("loot", ev="drop", spot=s.data.get("spot"), items=[[c, n, items.name(c)] for c, n in got],
                    gold=gold, **({"at": [round(at[0]), round(at[2])]} if at is not None else {}))
        wanted = [(code, n) for code, n in got if (items.row(code) or {}).get("ItemKind") == "QUEST_ITEM"]
        if wanted and s.data.get("drops"):
            box = max(s.data["drops"])                  # the item bag just created
            w = Writer(S2C_QUEST_ITEM_ALARM).raw(obf.u32(box)).u8(len(wanted))
            for code, n in wanted:
                w.raw(obf.u32(code)).u16(n)
            s.send(w)


def pick_drop(s, g, state, b):
    """0x4052 on session s for the drops kept by the room session g (the same session when it arrives there)."""
    if len(b) < 12:
        log.warning("drop pick not understood: %s", b.hex())
        return
    n, drop_id, code, index = obf.dec_u16(b[0:2]), struct.unpack_from("<I", b, 2)[0], obf.dec_u32(b[6:10]), obf.dec_u16(b[10:12])
    drop = (g.data.get("drops", {}) if g is not None else {}).get(drop_id, {})
    reply = lambda result: s.send(Writer(S2C_DROP_PICK).u16(result).u32(drop_id).raw(obf.u16(n)).u16(index)
                                  .raw(obf.u32(code)))
    if drop.get(index) is None or drop[index][0] != code:
        reply(DROP_GONE)                        # already taken: no "bag full" message
        return
    from . import items, quest, world
    c = hero_char(s)
    r = quest.record(c)
    if (items.row(code) or {}).get("ItemKind") == "QUEST_ITEM" and not any(
            quest.item_needed(qid, q, str(code)) for qid, q in r["active"].items()):
        reply(QUEST_ITEM_FULL)
        return
    code, count = drop.pop(index)
    if not drop:
        g.data["drops"].pop(drop_id, None)
    net.journal("loot", ev="pick", code=code, name=items.name(code), n=count, drop=drop_id)
    world.add_item(s, state, code, count)
    reply(0)
    log.info("picked %d x%d from drop %#x", code, count, drop_id)


def respawn_delay(s, uid, t):
    """Seconds until a fallen field troop comes back, from its zone entry, or None when it does not: UseSpawnSystem 0
    or RespawnLoopNum 0 never, RespawnLoopNum n > 0 at most n times (-1 always), after RespawnTime +- RespawnNoiseTime
    (the spread is ours; the zone gives only the width)."""
    loops = t.get("RespawnLoopNum")
    loops = -1 if loops is None else loops
    if t.get("UseSpawnSystem", 1) == 0 or loops == 0:
        return None
    done = s.data.setdefault("respawns", {})
    if loops > 0 and done.get(uid, 0) >= loops:
        return None
    done[uid] = done.get(uid, 0) + 1
    noise = max(0, t.get("RespawnNoiseTime", 0) or 0)
    return max(1, (t.get("RespawnTime", 0) or 0) + random.uniform(-noise, noise))


def respawn_zone_troop(s, uid, t):
    """The dead troop leaves first (0x50cc), so the respawn under the same uid is a new troop; it is built disabled,
    so the enable action follows (as at room start; live: 34 respawns were never hit again). The new troop is not
    bound until its own 0x50ab (troop_order holds its orders)."""
    s.send(Writer(S2C_TROOP_LEAVE).u16(1).u16(uid))
    s.data.get("bound", set()).discard(uid)
    s.data.get("field_sim_pending", set()).discard(uid)
    if spawn_zone_troop(s, t):
        send_actions(s, [ACT_ENABLE_ALL_TROOPS, 1, 1])


REVIVE_NONE_LEFT, REVIVE_NOT_HERE, REVIVE_NOT_NOW = 0x7411, 0x7412, 0x7413   # 0x50f5 refusals (any shows 0xd03a)


def revival(spot, difficulty=0):
    """(Revival_Goods, Limit_Revive) of spottable %Revival for the spot's Spot_Contents_Type, as the battle HUD reads
    them (HUDRevivalSystem init 0x14068e280: the row by content type, its Limit_Revive at +0x24, -1 without a row;
    the spot's own Limit_Revive column is not read there): PVE_NORMAL / REPEAT / CLIMAX CUBIC -1, PVE_RIFT CUBIC 5,
    PVE_EXTREME / RAID CUBIC 3, PVE_INVASION FREE 3, PVE_DAILY / WEEKLY IMPOSIBLE. No row: CUBIC, no limit, as
    RevivalCostSetting 0x1406902f0 takes it (goods 1). The HUD refuses the same before sending (0xd03c, 0xd03d).
    In a 16-player raid (Spot_Type Raid, Spot_Sub_Type Raid_16) the HUD then takes the limit from table raid
    (0x14068e31d): %Raid Default_Number_Resurrection of the raid at the room's difficulty (3 on all five rows:
    party.raid_row); in the room an armed checkpoint's Number_Resurrection replaces it (raid.limit, in revive_here)."""
    from . import party
    ctype = (tables.by_id("spottable").get(str(spot)) or {}).get("Spot_Contents_Type")
    row = next((r for r in tables.sections("spottable")["Revival"] if r["ID"] == ctype), None)
    if row is None:
        return "CUBIC", -1
    limit = row["Limit_Revive"].strip()
    raid = (party.raid_row(spot, difficulty) or {}).get("Default_Number_Resurrection", "")
    return row["Revival_Goods"], int(raid) if raid.isdigit() else int(limit) if limit.lstrip("-").isdigit() else -1


def revive_point(s):
    """Where the free camp revive (0x50d6 -> 0x50d7, the position from the server) puts the hero: the zone's player
    start point (PlayerStartPointInfoData of the player's team, each entry's first point) nearest where he fell
    (s.data["hero_pos"]), else start_pos (census I3; "nearest" is the reading of FieldMap_RevivalSystem's name, the
    original's choice is not in the client). A raid's zone also holds its checkpoints' restart points (raid
    %Check_Point Restart_Point_ID: 20950's StartPointIDs 100-115, far inside the map): left out (party.restart_points)
    until their checkpoint is armed (raid.armed_points). So the camp revive stays among the points the party entered
    at and the armed ones, and with no resurrection left it is text 0x16068's move "to the closest checkpoint"."""
    from . import party, pvp, raid, zone
    spot, here = s.data.get("spot"), s.data.get("hero_pos")
    points = []
    if here and spot and zone.available(spot):
        held = party.restart_points(spot) - raid.armed_points(s)
        team = (pvp.room(s) or {}).get("team", PLAYER_TEAM)     # 20955 seats the player on the map's team 1
        points = [(round(p["StartPointInfoData"][0]["PosX"]), 0, round(p["StartPointInfoData"][0]["PosZ"]))
                  for p in zone.for_spot(spot)["PlayerStartPointInfoData"]
                  if p.get("LongTeamID", PLAYER_TEAM) == team and p["StartPointInfoData"]
                  and p.get("StartPointID") not in held]
    if not points:
        return start_pos(s)
    return min(points, key=lambda q: (q[0] - here[0]) ** 2 + (q[2] - here[2]) ** 2)


def free_revives(c, now=None):
    """The free resurrections left today (FREE_REVIVES a game day, rules.game_day; kept in c["free_revives"]; rules
    census ECONOMY J5): the revive in place spends them before the Cubic price, the hero's and the troops' alike."""
    from . import rules
    today = rules.game_day(now)
    if (c.get("free_revives") or {}).get("day") != today:
        c["free_revives"] = {"day": today, "used": 0}
    return max(0, FREE_REVIVES - c["free_revives"]["used"])


def free_revives_packet(c):
    return Writer(S2C_FREE_REVIVES).u16(free_revives(c))


def revive_cost():
    """The Cubic a hero's revive in place costs: item_currency %Base Resurrect Index 0 (70). The client's confirm box
    prices it so: RevivalCostSetting 0x1406902f0 -> 0x140690040 looks up ItemCurrencyInfoHolder (*0x1435a6240, RTTI)
    at (8 = Resurrect in the client's type names, index 0) for a hero, and the count at record +8 is what the box
    shows and the balance (common+0x118) is checked against. A troop's index is its grade and rarity (Troop_Resurrect
    1..26: 10-130; the troop revive is not built). item_consume_sub %Revive's 9 is read by no revive path."""
    return items.currency("Resurrect", 0)


def hero_revival_cooldown(spot):
    """The seconds the client counts before the fallen hero is back: %Point HeroRevivalCooldown, where the client reads
    it (HUDHeroInfo 0x140769180: a %Point row and Spot_Sub_Type not PVP_HERO -> "Resurrecting in %d seconds." and the
    hero bar's count). 30 on 20954-20956 and the other PVP_POINT maps, 0 on the PvE %Point spots, 0 without a row."""
    from . import changetroop, party
    row = changetroop.point_row(spot)
    if row is None or (party.spot_row(spot) or {}).get("Spot_Sub_Type") == "PVP_HERO":
        return 0
    try:
        return max(0, int(float(row.get("HeroRevivalCooldown") or 0)))
    except ValueError:
        return 0


def cooldown_revival(s, t, token):
    """The cooldown's end: the hero back, free (no points, not a counted revival), by the server's push, since the
    client sends nothing then (planning/agents/reports/2026-11-07_pvp-hero-revival-timer.md). Nothing when he is back
    already, fell again since (token = his death count at the fall), the room is won or gone, or a paid timed revival
    (0x5108) is in its cast: that one finishes it. Ours: where he stands up, revive_point (the camp revive's rule);
    the original's place is not in the client."""
    from . import changetroop
    battle = s.data.get("battle")
    if (s.data.get("hero_deaths") != token or not t.get("down") or s.data.get("mission_won")
            or not battle or battle.troops.get(0) is not t
            or 0 in (s.data.get("changetroop") or {}).get("revival", {})):
        return
    revive_hero(s, t, revive_point(s))


def revive_hero(s, t, pos):
    """Bring the dead hero back at pos with full hp: 0x505c dead FALSE (the revive; it closes the death window), 0x505b
    alive for his leader and unit 0, 0x50c0 (moves it there), 0x505d (hp). 0x505c resets the troop only: read live
    2026-11-05 09:13, troop 0's +0x838 leader (0x30226c) and +0x848 unit (0x206c) both kept the dead bit 0x20, the hero
    frozen and invisible; 0x140d17100's alive branch calls the unit's revive (vtable +0x5d8)."""
    x, y, z = pos
    q, p15 = obf.pos_xz(x, z)
    s.send(Writer(S2C_TROOP_DOWN).zeros(5).obool(False).u16(0))
    combat.send_unit_live(s, 0, [], [combat.LEADER, 0])
    s.send(Writer(S2C_TROOP_BACK).raw(q).raw(struct.pack("<h", y)).u8(p15).u16(0))
    t.pop("down", None)
    t["hp"] = t.get("max", HERO_HP)
    send_troop_hp(s, 0, t["hp"], t["hp"])
    status.revived(s)                                    # the revive cleared his statuses: the passives come back
    log.info("hero revived at %s", pos)


def troop_revive_cost(t):
    """The Cubic a troop's revive in place costs: item_currency %Base Resurrect at the Index %Troop_Resurrect
    gives its trooptable TroopGrade x TroopRarity (GRADE1 RARITY1 1: 10 .. GRADE5 RARITY5 25: 130; NONE NONE 26: 25),
    as the HUD prices it (RevivalCostSetting 0x1406902f0 -> 0x140690040, the index from 0x140c5b7f0).
    A handed NP troop has no roster record or TroopGrade/TroopRarity fields: it uses NONE/NONE."""
    from . import troops
    row = (troops.troop_row(t["id"]) if t else None) or {}
    key = (row.get("TroopGrade", "NONE"), row.get("TroopRarity", "NONE"))
    rows = tables.sections("item_currency")["Troop_Resurrect"]
    index = next((r["Index"] for r in rows if (r["TroopGrade"], r["TroopRarity"]) == key),
                 next((r["Index"] for r in rows if r["TroopGrade"] == "NONE"), "0"))
    return items.currency("Resurrect", index)


def revive_troop(s, uid, t):
    """A wiped owned or handed troop back in place (0x50f5 has no troop branch): 0x505c dead FALSE for
    it (0x1407e3900: its reset and Troop::Enable), 0x505b alive for its leader and every member (0x140d17100 revives
    each soldier), its full hp (0x505d; full is ours, as the hero's) and the revive's invincibility 34 (10 s). It
    counts again if it is wiped again (troop_down); its Troop_Death AP stays once a room (deck_troop_down)."""
    s.send(Writer(S2C_TROOP_DOWN).zeros(5).obool(False).u16(uid))
    top = t.get("unit_max") or 1
    t["units"] = [top] * len(t["units"])
    alive = list(range(len(t["units"])))
    if t.get("leader_max"):
        t["leader"] = t["leader_max"]
        alive = [combat.LEADER] + alive
    combat.send_unit_live(s, uid, [], alive)
    send_troop_hp(s, uid, sum(t["units"]), t.get("leader"))
    s.data.get("deck_wiped", set()).discard(uid)
    s.data.get("down", set()).discard(uid)               # it stands: the director's arrive steps read it again
    status.troop_revived(s, uid)                         # its passives and set status again, then 34 (TROOPS T14.4)
    from . import changetroop
    changetroop.upgrade_statuses(s, uid)                 # an upgraded troop's statuses (a %Point spot; else nothing)
    log.info("player troop %d revived in place", uid)
    net.journal("revive", spot=s.data.get("spot"), troop=uid)


def prop_mend(s, p, top):
    """A broken attackable prop back whole after its Regen_Time."""
    prop_id = p["SmartPropID"]
    s.data.get("prop_states", {}).pop(prop_id, None)
    s.data.get("prop_hp", {}).pop(prop_id, None)
    s.send(Writer(S2C_PROP_REGEN).u16(p["SmartPropTypeID"]).raw(obf.u32(prop_id)).u8(obf.T2[PROP_KIND_ATTACK]))


VANISH_WALL_RES = "185"          # smartpropresidtable 스위치_사라짐_충돌메쉬프랍: a switch whose "on" makes its collision mesh vanish
WALL_GUARD_RANGE = 600           # ours: the attackable props within this of such a wall are the ones that guard it


def open_cleared_walls(s, broken):
    """An invisible wall (a trigger-only switch of resource VANISH_WALL_RES, e.g. type 232) standing among attackable
    props opens once every one of them within WALL_GUARD_RANGE is broken: a one-record 0x50d1 turns it on, the state
    whose object has no collision. Grey Fog 10358's barrel barricade: wall 10528 in the middle of barrels
    10518-10527 (owner 2026-09-27 21:28: "after we destroy the barrels their block is still there"); the same shape
    at Posterus Green Centre (30051, three props of type 45) and Kedington Wall (type 12). The mission script opened
    them; the rule is ours, read from the placement. Not sending the wall (trigger-only props are hidden) left its
    collision standing."""
    from . import zone
    props = zone.for_spot(s.data["spot"])["SmartPropData"]
    states = s.data.setdefault("prop_states", {})
    near = lambda a, b: math.hypot(a["PosX"] - b["PosX"], a["PosZ"] - b["PosZ"]) <= WALL_GUARD_RANGE
    for w in props:
        row = prop_row(w["SmartPropTypeID"]) or {}
        if row.get("SmartPropResID_SW") != VANISH_WALL_RES or states.get(w["SmartPropID"]) == PROP_ON or not near(w, broken):
            continue
        guards = [q for q in props if q is not w and near(q, w) and "HP_AT" in (prop_row(q["SmartPropTypeID"]) or {})]
        if guards and all(states.get(q["SmartPropID"]) == PROP_BROKEN for q in guards):
            switch_on(s, w)
            log.info("wall %d opens: its %d props are broken", w["SmartPropID"], len(guards))


def switch_on(s, p):
    """A script-opened wall or barrier goes: a one-record 0x50d1, shown, alive, in PROP_OPEN. The record's state reaches
    the prop's vt+0x200 (0x1419b5d70, its state machine), and a vanishing or breaking switch drops its collision
    (+0x31a and every mesh collision object, 0x141a97d70 / 0x141e405e0) on entering state 2 or 3, only while in the
    scene: shown first, as the record apply 0x14091a710 does before the state. Live 2026-09-28 in Grey Fog: wall 10531
    (type 232) shown and put in state 2 lost its collision at once; types 131 / 64 / 94 lose it in 2 and 3, keep it in
    0 and 1; hidden props keep theirs in every state. Neither the on state (1: the hero stayed at x 281.4k, 23:57) nor
    alive false (0x14091a710 turns collision off only for ids in the prop world's +0xa8 set, empty here) opened wall
    10528; its collision off, the hero walked from x 281408 to 279542 in 3 s of W (tools/frida/propstate.js)."""
    s.data.setdefault("prop_states", {})[p["SmartPropID"]] = PROP_ON
    out = Writer(S2C_PROP_LIST).u16(1)
    write_prop(out, p["SmartPropID"], (round(p["PosX"]), round(p["PosZ"])), True, state=open_state(p))
    s.send(out)


def open_state(p):
    """The state switch_on opens prop p with: a prison (감옥, Grey Rock's eleven wolf cages) shows closed in PROP_OPEN, so it
    takes PROP_SWUNG. The other opening switches (열림 460-462, 492) stay as they were: not looked at in state 3."""
    return PROP_SWUNG if "감옥" in prop_res_name(p["SmartPropTypeID"]) else PROP_OPEN


def prop_return(s, p):
    """A switch back to off after its recharge (AutoReturn_SW): a one-record 0x50d1 with the off state."""
    from . import quest
    s.data.get("prop_states", {}).pop(p["SmartPropID"], None)
    shown = prop_shown(p["SmartPropTypeID"], quest.record(hero_char(s)))
    w = Writer(S2C_PROP_LIST).u16(1)
    write_prop(w, p["SmartPropID"], (round(p["PosX"]), round(p["PosZ"])), shown, state=PROP_OFF)
    s.send(w)


def send_quest_props(s, spot, c, qid):
    """After quest qid was accepted, completed or dropped: the zone props whose emergence condition names it, shown or
    not by the new quest state (e.g. the Spider Cocoons appear with 1150201)."""
    from . import quest, zone
    r = quest.record(c)
    props = [p for p in zone.for_spot(spot)["SmartPropData"]
             if (prop_row(p["SmartPropTypeID"]) or {}).get("Energence_Conditions_Value") == str(qid)]
    if not props:
        return
    w = Writer(S2C_PROP_LIST).u16(len(props))
    for p in props:
        write_prop(w, p["SmartPropID"], (round(p["PosX"]), round(p["PosZ"])), prop_shown(p["SmartPropTypeID"], r))
    s.send(w)
    log.info("field %d: %d props of quest %d re-sent", spot, len(props), qid)


PLACE_PHASE = re.compile(r"^P(\d+)_S(\d+)_(.*)$")
HERO_PLACE_LABELS = ("영웅 위치", "영웅위치", "영웅_시작위치", "영웅 시작위치")


@functools.lru_cache(maxsize=None)
def mission_staging(spot):
    """Where a mission's opening scene puts the hero and its cast, from the zone's placement bounds (EventBoundName
    "<phase>_<name> 위치"), which the original's mission script used: (hero (x, z) or None, {TroopID: (x, z)}). The
    hero's bound (영웅 위치 / 영웅_시작위치; the earliest phase), and when it names a phase, the troops whose alias the
    same phase's bounds name ("P1_S1_글렌 위치" -> alias 글렌). Grey Rock 10234 (owner live 2026-09-28: "it throw me to
    the wrong place at the start of the mission"): the hero 16 000 units from P1_S1_영웅 위치, Glen, Thompson and both
    troop pairs 45 000 away at their parking places; 10304 and 20318 have a hero bound only. Ours: the zone's start
    point is where the client puts the hero (the warp's group), the bound where the scene begins."""
    from . import zone
    if not zone.available(spot):
        return None, {}
    z = zone.for_spot(spot)
    heroes, by_phase = [], {}
    for b in z.get("EventBound") or []:
        name = str(b.get("EventBoundName", ""))
        m = PLACE_PHASE.match(name)
        phase, label = ((int(m.group(1)), int(m.group(2))), m.group(3)) if m else (None, name)
        if label in HERO_PLACE_LABELS:
            heroes.append(((phase or (0, 0)), phase, (b["BoundCenterX"], b["BoundCenterZ"])))
        elif phase and label.endswith("위치"):
            by_phase.setdefault(phase, {})[label[:-2].replace(" ", "")] = (b["BoundCenterX"], b["BoundCenterZ"])
    if not heroes:
        return None, {}
    _, phase, hero = min(heroes)
    names = by_phase.get(phase, {})
    troops = {t["TroopID"]: names[str(t.get("TroopAlias") or "").replace(" ", "")] for t in z["NPCTroopInfoData"]
              if str(t.get("TroopAlias") or "").replace(" ", "") in names}
    return hero, troops


def move_troop(s, uid, pos):
    """S2C 0x50c0 (0x140d01ea0): the troop to pos (SetPosition 0x1407e4bd0, the client puts it on the ground: live
    2026-09-28 the hero sent to (98488, 90014) at the start's height stood at the bound's own -2729), its units
    re-placed around it (vt+0x370)."""
    x, y, z = pos
    q, p15 = obf.pos_xz(round(x), round(z))
    s.send(Writer(S2C_TROOP_BACK).raw(q).raw(struct.pack("<h", int(y))).u8(p15).u16(uid))


def stage_hero(s):
    """At a mission's start, the hero to the opening scene's bound (mission_staging), where the rest of it stands."""
    spot = s.data.get("spot")
    hero, _ = mission_staging(spot) if is_mission(spot) else (None, {})
    if hero is not None:
        _, y, _ = start_pos(s)
        move_troop(s, 0, (hero[0], y, hero[1]))
        s.data["hero_pos"] = (round(hero[0]), y, round(hero[1]))
        for uid in s.data.get("deck") or {}:            # his deck troops keep their places around him
            dx, dz = deck_offset(spot, uid)
            move_troop(s, uid, (hero[0] + dx, y, hero[1] + dz))
        log.info("mission %d: the hero to the opening scene at (%d, %d)", spot, hero[0], hero[1])


def arrive_at_door(s):
    """A field entered from a won door mission (door_way_back): the hero to that door, once, as stage_hero moves him at
    a mission's start. The client's own entry names no door: what the original sent for it isn't known; 0x50c0 is ours."""
    c = hero_char(s)
    door = c.pop("door_return", None)
    if door is None or door["spot"] != s.data.get("spot"):
        return
    x, y, z = door["pos"]
    move_troop(s, 0, (x, y, z))
    s.data["hero_pos"] = (x, y, z)
    c["pos"] = [x, y, z]
    log.info("field %d: the hero back at the mission's door (%d, %d)", door["spot"], x, z)


ACT_ENABLE_TROOP = 0xea6a        # ActTroopSetEnableTroop (0x140b3d990 -> 0x140b2e030): (kind 0 = a troop uid, uid,
                                 # enable 1 / 0, flag); 0 -> 0x140ba3450 -> 0x1407e2bb0 (beside Troop::Die 0x1407e2ff0)


def troop_leaves(s, uid):
    """A troop leaves the battle (director "leave": Vert escaping at 20 %): disabled in the client (not seen live), its
    boss bar closed, down for the win rule and gone from the battle. One of the player's first goes back to its own force:
    the HUD's three troop slots are taken in order (OnAddPlayerTroop 0x14078c1b0) and a disabled troop keeps its slot,
    ChangeForce from the player's id clears it (0x140ba36e4 -> 0x140b3fca0): 10345's lesson archer held F1, so the three
    of the mock battle got F2, F3 and no slot (live 2026-11-06 08:17)."""
    t = s.data.get("zone_troops", {}).get(uid)
    if t is not None and uid in (s.data.get("plan") or {}).get("hand", ()):
        send_actions(s, [ACT_CHANGE_FORCE, 0, uid, t["ForceNum"], TROOPAITYPE_HEROSUPPORT])
    send_actions(s, [ACT_ENABLE_TROOP, 0, uid, 0, 0])
    from . import zone
    if t is not None and (zone.np_troop(t["TroopTableID"]) or {}).get("NP_Grade") == "Boss":
        send_actions(s, [ACT_BOSS_STATUS, uid, 0])
    s.data.setdefault("down", set()).add(uid)
    s.data.setdefault("left", set()).add(uid)
    s.data["battle"].troops.pop(uid, None)
    log.info("troop %d leaves the battle", uid)
    net.journal("left", spot=s.data.get("spot"), troop=uid)


def spawn_force(s, force):
    """Bring force n in now (director "wake"): its held groups (wake), then its troops that are neither in nor waiting
    (staging, inactive: Grey Fog's villagers 15000) of the room's difficulty; the number that came."""
    n = sum(wake(s, w, "the script") for w in [w for w in s.data.get("waves", ()) if w[0].get("ForceNum") == force])
    from . import zone
    spot = s.data["spot"]
    names, held = force_names(spot), {t["TroopID"] for w in s.data.get("waves", ()) for t in w}
    fresh = [t for t in zone.for_spot(spot)["NPCTroopInfoData"] if t.get("ForceNum") == force
             and t["TroopID"] not in s.data.get("zone_troops", {}) and t["TroopID"] not in held
             and for_difficulty(t, names, s.data.get("difficulty", 0))]
    n += sum(1 for t in fresh if spawn_zone_troop(s, t))
    if fresh:
        net.journal("wake", spot=spot, force=force, why="the script (not held)", n=len(fresh))
        send_actions(s, [ACT_ENABLE_ALL_TROOPS, 1, 1])
        director.on_wake(s, {force})                # a staging force has no wave: its "wake" steps (Tower F30000)
    return n


def spawn_troops(s, uids):
    """Bring these zone troops in now, one by one (director "spawn"): each out of its held group, whose other troops
    stay held (its allies stay with it); a troop in no group spawns as it is. The number that came."""
    from . import zone
    spot, n = s.data["spot"], 0
    names = force_names(spot)
    for uid in uids:
        if uid in s.data.get("zone_troops", {}):
            continue
        t = next((t for t in zone.for_spot(spot)["NPCTroopInfoData"] if t["TroopID"] == uid
                  and for_difficulty(t, names, s.data.get("difficulty", 0))), None)
        if t is None:
            continue
        for wave in [w for w in s.data.get("waves", ()) if any(x["TroopID"] == uid for x in w)]:
            first = wave[0]["TroopID"]
            wave[:] = [x for x in wave if x["TroopID"] != uid]
            allies = s.data.get("wave_allies", {}).pop(first, None)
            if not wave:
                s.data["waves"].remove(wave)
            elif allies is not None:                    # the group is named by its first troop
                s.data["wave_allies"][wave[0]["TroopID"]] = allies
        if spawn_zone_troop(s, t):
            n += 1
    if n:
        send_actions(s, [ACT_ENABLE_ALL_TROOPS, 1, 1])
        net.journal("wake", spot=spot, troops=list(uids), why="the script (one by one)", n=n)
    return n


def spawn_zone_troop(s, t):
    """One zone troop (NPCTroopInfoData entry) at its place with full hp, as the room's difficulty variant
    (difficulty_troop); False when its table row is missing. A troop the opening scene places (mission_staging)
    starts there. Every one, enemy or ally, comes with its nptrooptable %Skill and its NP leader's npleadertable
    %Skill (cell_abilities): the actives in its 0x50cb entry's first ability list, the passives in the second (the
    client reads no table skill for a 0x50cb troop, nor does its own local zone spawn 0x140d08120). The troop
    bar of one handed to the player shows the actives (the original: Grey Rock's archers 500045, Tower's 200147), and
    every NP troop's AI casts those with an abilitytypeinfo %AiCondition row (defaulttroop_ai.tai's RunAutoSkill,
    ScriptTroop::UseAutoSkill 0x140ba4ea0; owner 2026-09-30: "do the most close the vanilla as possible"), as C2S
    0x505f (combat.on_troop_cast). Its AI program is its own table row's (table_ai), in the descriptor and 0x5083: an
    AI id of -1 gave every troop the generic 40000; a troop handed to the player takes Hero Support after it."""
    from . import zone
    base = t["TroopTableID"]                            # the zone's Normal row (a respawn's is already the variant)
    tid = difficulty_troop(base, s.data.get("difficulty", 0))
    if tid != t["TroopTableID"]:
        t = dict(t, TroopTableID=tid)                   # a copy: the zone content is cached and shared
    spot = s.data.get("spot")
    placed = mission_staging(spot)[1].get(t.get("TroopID")) if is_mission(spot) else None
    if placed is not None:
        t = dict(t, PosX=placed[0], PosZ=placed[1])
    if "ForceNum" in t and is_mission(spot) and staging(spot, t, force_names(spot)):
        t = dict(t, Staging=True)
    row = zone.np_troop(t["TroopTableID"])
    if row is None:
        return False
    # the client's own zone spawn (LoadInitPlayerData 0x140d08120, ScriptTroop::RequestTroop 0x140b95540: no count to
    # MakeSpawnNPTroopGenInfo 0x140f67fb0 -> 0x140f6c780) takes the table's UNIT_COUNT (row +0xe8) when it is 1 or
    # more, else the zone entry's UnitNum (+0x40): New Hampton's single siege engines and staging Vert stay one (their
    # UnitNum 30 / 48), the 0-unit rows take the zone's size (Tower's archers 42, the tape's 98,700), and Flamegrass
    # 10303's orc infantry are the table's 9 (12 / 30 / 4 / 16 in the zone; the tape's full ~5,050 = 9 x 561, part 4
    # f_01056-f_01273; T9.3: 1,450 zone troops in 169 zones take their table's count, the prologue 50116's 9 among them)
    table = int(row["UNIT_COUNT"])
    units = table if table >= 1 else (t.get("UnitNum") or 0)
    if units > 0:                                       # Hard / Hell: the change row's unit count (a respawn's
        units = difficulty_units(base, units, s.data.get("difficulty", 0))       # variant id has no change row)
        if units <= 0:
            return False                                # "-12": an ally the harder difficulty leaves out
    lead = np_leader(t.get("NPLeaderID"))
    if not units and not lead and hostile(t):
        units = 1                               # a formation with no unit and no leader row: one unit, so it can fall
    uid = t["TroopID"]
    team = t.get("TeamNum", NP_TEAM)
    rec, lead_rec, row, lead = np_records(t["TroopTableID"], team, row, lead)
    if t.get("ForceNum") in director.harmless(spot) and uid not in director.hand(spot):   # a handed troop is the player's
        rec, lead_rec = dict(rec, harmless=True), lead_rec and dict(lead_rec, harmless=True)   # copies: they are shared
    unit_hp = max(1, int(float(row["HP_BASEUNIT"])))
    lead_hp = max(1, int(float(lead.get("HP_BASEUNIT") or 0) or 1)) if lead else 0
    actives, passives = cell_abilities(rec, lead_rec, uid)
    ai = table_ai(t["TroopTableID"])
    send_np_troop(s, uid, t["TroopTableID"], (round(t["PosX"]), 0, round(t["PosZ"])), unit_hp * units, units,
                  team=team, zt=t,                       # 0 / 1 monsters, 255 neutral (dummies, wildlife)
                  leader=(int(t["NPLeaderID"]), lead_hp) if lead else None, abilities=actives, passives=passives,
                  ai=ai)
    send_spawn_ai(s, uid, ai, zt=t)
    face_zone_angle(s, uid, t)
    ally_holds = team == PLAYER_TEAM and spot in UNDYING_MISSIONS
    s.data["battle"].add_np(uid, unit_hp, units, c=rec, leader_hp=lead_hp, leader_c=lead_rec,
                            leader_floor=1 if ally_holds else 0)
    combat.send_stamina(s, uid, shown_only=True)        # its vitality bar full (a commander's, a boss's: census I5)
    s.data.setdefault("zone_troops", {})[uid] = t
    status.troop_passives(s, uid, dict(passives))       # their held statuses (T1.11), the hero's way
    net.journal("spawn", spot=spot, troop=uid, table=t["TroopTableID"], force=t.get("ForceNum"), team=team, units=units)
    if row.get("NP_Grade") == "Boss" and hostile(t) and is_mission(s.data.get("spot")):
        send_actions(s, [ACT_BOSS_STATUS, uid, 1])      # its vitality bar (Mountain Troll 134080, Ochanku 118510)
    return True


def angle_byte(angle):
    """A zone Angle as 0x50b7's direction byte: Angle A faces (sin A, 0, cos A) (0x140f685d0), byte b faces (cos, 0, sin) of
    b * 2 pi / 256 (0x140cf4828)."""
    return round((90 - angle) * 256 / 360) % 256


def face_zone_angle(s, uid, t):
    """A zone troop stands at its zone Angle, its units laid out for it, once the client has it (its 0x50ab; before that
    there is nothing to lay out). 0x50cb has no direction, so the client builds it with its units on an axis-aligned square;
    the client's own zone spawn gives it the Angle at the build (0x140f67ac5, entry +0x74). 0xc382 turns the slots and leaves
    the units where they stood, this lays them on the slots (live 2026-11-05: d = 0 on all 18 of Grey Rock's wolves). It does
    not free units stuck in a narrow place: 12 of those 18 still started on cells with no route (13 on the square), so
    their scene walks them out in a straight line (m10234's WAYS_OUT)."""
    if t.get("Angle") is None:
        return

    def lay_out(s):
        q, p15 = obf.pos_xz(round(t["PosX"]), round(t["PosZ"]))
        s.send(Writer(S2C_TROOP_PLACED).u16(1).u8(angle_byte(t["Angle"])).u16(0).raw(q).raw(struct.pack("<h", 0)).u8(p15)
               .u16(uid))

    if uid in s.data.get("bound", ()) and uid not in s.data.get("field_sim_pending", ()):
        lay_out(s)
    else:
        s.data.setdefault("await_bind", {}).setdefault(uid, []).append(lay_out)


def np_records(np_troop_id, team, row, lead=None):
    """(troop record, leader record or None, troop row, leader row) of a zone troop (row: its nptrooptable row, lead
    its npleadertable row or None) with its passives' stats (T1.11):
    its nptrooptable %Skill passives and its NP leader's npleadertable ones, whose traits for TROOP or ALL go into the
    troop's row and for LEADER or ALL into the leader's (status.passive_traits with live False, combat.add_traits):
    a leader's passive reaches his troop, as the troop's reaches him. Without such a trait the cached np_combatant."""
    rec = combat.np_combatant(np_troop_id, team)
    lead_rec = combat.combatant_leader(lead, team) if lead else None
    held = {**(lead_rec or {}).get("passives", {}), **(rec or {}).get("passives", {})}
    traits = status.passive_traits(held, (rec or {}).get("level", 1), live=False)
    if traits and rec is not None:
        row = combat.add_traits(row, traits)
        rec = combat.combatant_np(row, team)
    traits = status.passive_traits(held, (lead_rec or {}).get("level", 1), "LEADER", live=False) if lead else []
    if traits:
        lead = combat.add_traits(lead, traits)
        lead_rec = combat.combatant_leader(lead, team)
    return rec, lead_rec, row, lead


CELL_SLOTS = 16                  # each 0x50cb ability list's slots: list 1 at 0..15, list 2 at 0x10 + the place
                                 # (MakeTroopGenInfoForBuild 0x140cf7080), the %Skill's 16 active columns


def cell_abilities(rec, leader=None, uid=None):
    """([(ability, level)] actives, [(ability, level)] passives) of an NP troop's 0x50cb lists: its nptrooptable %Skill
    in column order, then its NP leader's npleadertable %Skill (the leader has no ability manager of his own:
    BuildNPLeader_New 0x140f6c260 fills only his stats, so the troop's is the only one the cast path uses; a
    LEADER-subject skill needs him alive, the client's check), each ability once; past CELL_SLOTS an active would take
    a passive's slot, so it stays out (logged; no table pairing does)."""
    lists = []
    for kind in ("skills", "passives"):
        out = {}
        for r in (rec, leader):
            for aid, lv in ((r or {}).get(kind) or {}).items():
                out.setdefault(aid, lv)
        items = list(out.items())
        if len(items) > CELL_SLOTS:
            log.warning("troop %s: %d %s past the %d slots left out: %s", uid, len(items) - CELL_SLOTS, kind,
                        CELL_SLOTS, items[CELL_SLOTS:])
        lists.append(items[:CELL_SLOTS])
    return tuple(lists)


@functools.lru_cache(maxsize=None)
def _np_leaders():
    return {r["NPLEADER_ID"]: r for r in tables.sections("npleadertable")["Contents"]}


def np_leader(leader_id):
    """The npleadertable row of a zone troop's NPLeaderID (-100 / None: no leader), or None."""
    return _np_leaders().get(str(leader_id)) if leader_id not in (None, -100, 0) else None


QUEST_TROOP_UID = 0xE000         # uids of quest-spawned troops: above every zone TroopID (10000..49000 in the
                                 # zones read), below the 0xF000 + slot troops.md proposes for deck troops


PROP_TARGET_OFFSET = 500         # ours: how far from the used prop a prop-summoned quest target stands
PROP_RANGE_UNIT = 100            # ours [I]: world units per smartproptable SpawnNP_Range step (the unit is not known;
                                 # 100 puts 246's and 295's range 5 at the PROP_TARGET_OFFSET their quests' Redin had)


def ambush_troop(row):
    """The NP troop a prop calls when used: smartproptable ActiveSpawnNPTroop_ID, with SpawnNP_Rate / SpawnNP_Range
    beside it, columns only the server read (the client image names their sibling columns, not these;
    planning/client/props_loot.md gap 2). 10 switches (246, 262, 295, 299, 306, 435-437, 466, 605) and item box 276
    carry one, all at 100 %. None for the rest."""
    tid = row.get("ActiveSpawnNPTroop_ID") or "-"
    return int(tid) if tid.isdigit() else None


def spawn_prop_ambush(s, p, row, roll=random.randrange):
    """The used prop p calls its table's troop (ambush_troop) at SpawnNP_Rate % beside it, on the enemy team, shown
    like the room's first spawn, when the cast completes (0x5096): quest 1160403's switches 435-437 in 10351 / 10360
    (155280 / 155290 / 155270, its ItemGain 451000370's carriers), Lake Bled 10202's 246 (Redin 152620), 295
    (1521020) and 306 (152270), 20200's switch 466 and item box 276 (250370 / 250360). Ours [I]: the place
    (SpawnNP_Range steps of PROP_RANGE_UNIT along x), and one standing troop per prop (a use while it stands calls
    nothing; the RequireQuestCo_* that likely ended 246's and 295's use after their condition is not mapped). No
    respawn. True when a troop came."""
    tid, rate = ambush_troop(row), row.get("SpawnNP_Rate") or "-"
    if tid is None or not rate.isdigit() or roll(100) >= int(rate):
        return False
    troops = s.data.setdefault("zone_troops", {})
    battle = s.data["battle"].troops
    if any(t.get("Prop") == p["SmartPropID"] and any(battle.get(u, {}).get("units", ())) for u, t in troops.items()):
        log.info("prop %d: its troop %d still stands", p["SmartPropID"], tid)
        return False
    reach = row.get("SpawnNP_Range") or "-"
    reach = int(reach) if reach.isdigit() else 0
    uid = QUEST_TROOP_UID
    while uid in troops:
        uid += 1
    t = {"TroopID": uid, "TroopTableID": tid, "PosX": p["PosX"] + reach * PROP_RANGE_UNIT, "PosZ": p["PosZ"],
         "TeamNum": NP_TEAM, "UnitNum": 0, "RespawnLoopNum": 0, "Prop": p["SmartPropID"]}
    if not spawn_zone_troop(s, t):
        return False
    send_actions(s, [ACT_ENABLE_ALL_TROOPS, 1, 1])
    log.info("prop %d (type %d) calls troop %d as %d", p["SmartPropID"], p["SmartPropTypeID"], tid, uid)
    return True


def spawn_prop_targets(s, p, qids):
    """Quests whose PropActivate condition the used prop p just moved and whose NPNameKill target no troop of this
    zone carries: that target appears beside the prop, for props whose table row names no troop (ambush_troop: Lake
    Bled 10202's 246 -> Redin and 295 -> 1521020 are the column's): 1160413 type 423 in 10351 / 10360 -> 158030, name
    1000150. The script that summoned them is not shipped: the moment (the prop's use) and the place (the prop) are
    ours, inferred from the quests' order (prop, then the kill and its drop). No respawn."""
    from . import quest, zone
    if not qids or not zone.available(s.data.get("spot")):
        return
    here = {str(t["TroopTableID"]) for t in zone.for_spot(s.data["spot"])["NPCTroopInfoData"]}
    troops = s.data.setdefault("zone_troops", {})
    for qid in qids:
        row = tables.by_id("questtable").get(str(qid)) or {}
        for n in range(1, quest.CONDITIONS + 1):
            if row.get(f"Complete{n}_Type") != "NPNameKill":
                continue
            candidates = quest.name_troops(row.get(f"Complete{n}_ID2"))
            if not candidates or here & set(candidates) or any(t.get("Quest") == qid for t in troops.values()):
                continue
            uid = QUEST_TROOP_UID
            while uid in troops:
                uid += 1
            t = {"TroopID": uid, "TroopTableID": int(candidates[0]), "PosX": p["PosX"] + PROP_TARGET_OFFSET,
                 "PosZ": p["PosZ"], "TeamNum": NP_TEAM, "UnitNum": 0, "RespawnLoopNum": 0, "Quest": qid}
            if spawn_zone_troop(s, t):
                send_actions(s, [ACT_ENABLE_ALL_TROOPS, 1, 1])
                log.info("quest %s: troop %s appears at prop %d", qid, candidates[0], p["SmartPropID"])


def spawn_quest_troop(s, qid):
    """questtable QuestAccept_SpawnNPTroop_ID in the field room s: the quest's kill target (1160218 -> 155340 Bettor,
    1160219 -> 155290 Virgil; nothing else in the zone carries their NP names) appears where the quest's start NPC
    stands in the zone (NPCInfo), on the enemy team, shown like the room's first spawn (ActTroopSetEnableAllTroops;
    Troop::Enable 0x1407e2850 skips the scene part of troops already enabled). The NPC leaves by the client's rule
    (npctable NPC_Spawn_Hide FinishOrDoingQuest names the quest). It does not respawn; still standing after its
    nptrooptable QuestSpawnedNPDisable_Time seconds, it leaves (0x50cc). The place is ours, inferred: the NPC is the
    troop (his hide rule, and the quest text "Capture me if you can!"); the original server's rule is not shipped.
    Returns the uid, or None when nothing spawns (no spawn column, not a field room, the NPC not in this zone)."""
    from . import tables, zone
    quest = tables.by_id("questtable").get(str(qid)) or {}
    tid, spot = quest.get("QuestAccept_SpawnNPTroop_ID", "-"), s.data.get("spot")
    if not tid.isdigit() or quest.get("Start_Type") != "Npc" or "battle" not in s.data or not is_field(spot) \
            or not zone.available(spot):
        return None
    npc = next((n for n in zone.for_spot(spot)["NPCInfo"] if str(n["TableID"]) == quest.get("Start_Value")), None)
    row = zone.np_troop(tid)
    troops = s.data.setdefault("zone_troops", {})
    standing = [u for u, t in troops.items()
                if t.get("Quest") == qid and any(s.data["battle"].troops.get(u, {}).get("units", ()))]
    if npc is None or row is None or standing:
        log.info("quest %d: no spawn of troop %s (start NPC %s in zone: %s, standing %s)", qid, tid,
                 quest.get("Start_Value"), npc is not None, standing)
        return None
    uid = QUEST_TROOP_UID
    while uid in troops:
        uid += 1
    t = {"TroopID": uid, "TroopTableID": int(tid), "PosX": npc["PosX"], "PosZ": npc["PosZ"], "TeamNum": NP_TEAM,
         "UnitNum": 0, "RespawnLoopNum": 0, "Quest": qid}
    spawn_zone_troop(s, t)
    send_actions(s, [ACT_ENABLE_ALL_TROOPS, 1, 1])
    ttl = row.get("QuestSpawnedNPDisable_Time", "-")
    if ttl.isdigit() and int(ttl) > 0:
        s.later(int(ttl), lambda: quest_troop_gone(s, uid))
    log.info("quest %d: troop %s spawned as %d at NPC %s (%d, %d)", qid, tid, uid, quest["Start_Value"],
             round(npc["PosX"]), round(npc["PosZ"]))
    return uid


def quest_troop_gone(s, uid):
    """A quest-spawned troop's time is up: it leaves (0x50cc) unless it already fell."""
    units = (s.data.get("battle") and s.data["battle"].troops.get(uid) or {}).get("units", ())
    if uid not in s.data.get("zone_troops", {}) or not any(units):
        return
    s.send(Writer(S2C_TROOP_LEAVE).u16(1).u16(uid))
    s.data.get("bound", set()).discard(uid)
    s.data.get("field_sim_pending", set()).discard(uid)
    s.data["zone_troops"].pop(uid)
    s.data["battle"].troops.pop(uid, None)
    log.info("quest troop %d left (time up)", uid)


def send_troop_hp(s, uid, troop_hp, leader_hp=None):
    """0x505d record (reader 0x140d1fae0). flags low nibble n: 1..14 -> u16, hp = (n-1)*65536 + u16; 15 -> packed u32.
    Bits 4-5 the same for the leader's hp (1..2 -> u16, 3 -> packed). A troop with a leader gets leader hp 0 (dies)
    when it is left out."""
    w = Writer(S2C_TROOP_HP)
    flags, tail = 0, b""
    for hp, shift in ((troop_hp, 0), (leader_hp, 4)):
        if hp is None:
            continue
        hp = max(0, hp)
        if hp < (14 if shift == 0 else 2) * 0x10000:
            flags |= ((hp >> 16) + 1) << shift
            tail += struct.pack("<H", hp & 0xFFFF)
        else:
            flags |= 0xF << shift if shift == 0 else 0x30
            b = bytearray(4); pack_value(b, 0, hp); tail += bytes(b)
    w.u8(flags).u16(uid).raw(tail)
    s.send(w)


def send_spawn_ai(s, uid, ai_id=-1, zt=None):
    """0x5083 SetSpawnAI (0x140d02f60 -> 0x1407eb2c0; ENEMY-AI.md §4.3): +0 u16 path 1, +2 f32 CombackDist, +6 u16 path
    2, +8 uid, +0xa u16 fall-back area, +0xc f32 WanderingDist, +0x10 u16 target troop, +0x12 f32 CombatDist, +0x16
    i32 AI: the troop's program (table_ai; -1 = its TAIBranch row's TROOPAI_NPINIT, 40000, not nptrooptable TROOPAI).
    It overwrites the leash the NP descriptor set, so it carries the same zone values (zeros switched wandering and
    the return home off); "none" is 0xffff."""
    zt = zt or {}
    none16 = lambda v: 0xffff if v is None or int(v) < 0 else int(v) & 0xffff
    s.send(Writer(S2C_SET_SPAWN_AI).raw(struct.pack(
        "<HfHHHfHfi", none16(zt.get("DefaultPath1ID")), float(dist_code(zt.get("CombackDist"))),
        none16(zt.get("DefaultPath2ID")), uid, none16(zt.get("FallBackAreaID")), float(dist_code(zt.get("WanderingDist"))),
        none16(zt.get("TargetTroopID")), float(dist_code(zt.get("CombatDist"))), ai_id)))


def write_troop_state(w, pos, flags, uid=0, troop_id=HERO_TROOP_ID, hp=HERO_HP, team=0, owner=0, np=False, units=0,
                      stats=None, level=0, np_block=None, leader=None, abilities=(), passives=(), troop_stats=None):
    """61-byte troop state (0x140d0ce70) and the tail read by 0x140d0cdc0, shared by 0x50cb entries and 0x50b8.
    Fields as MakeTroopGenInfoForBuild 0x140cf7080 copies them: +0 i16, +0x11 uid, +0x30 u16, +0x32 u32 leader id,
    +0x36 troop id, +0x09/+0x0d leader hp max/cur, +0x14/+0x28 troop hp cur/max (packed), +0x3c flags.
    leader = (npleadertable id, hp) of an NP troop's leader: +0x32 plain LE (0x140cf7361; with the NP obool the
    builder looks it up in NPLeaderTable, TroopGenConfig::BuildNPLeader_New 0x140f6c260, and a miss builds no
    leader), his hp in the leader fields."""
    st = bytearray(0x3d)
    struct.pack_into("<h", st, 0x00, team)
    struct.pack_into("<H", st, 0x11, uid)              # troop uid in the client's TroopManager (our hero = 0)
    struct.pack_into("<H", st, 0x30, owner)
    st[0x36:0x3a] = obf.u32(troop_id)
    lead_hp = hp
    if np and leader is not None:
        struct.pack_into("<I", st, 0x32, leader[0])
        lead_hp = leader[1]
    for off in (0x09, 0x0d):                           # packed values 0x50b8 applies (leader +0x09/+0x0d via vtable
        pack_value(st, off, lead_hp)                   # +0x2b0/+0x2a8, troop +0x14/+0x28 via +0x2a8/+0x2a0): hp / max hp
    for off in (0x14, 0x28):
        pack_value(st, off, hp)
    st[0x06] = st[0x13] = min(255, level)              # leader / troop level (0x50b8 handler 0x140d052e0; the HUD
                                                       # showed Lv.0 with 0 here)
    st[0x3c] = flags                                   # 0x40 clear: no extra u16
    w.raw(bytes(st))
    x, y, z = pos
    q, p15 = obf.pos_xz(x, z)
    w.obool(np)                                        # 0x140d0cdc0: 22-byte block present = NP troop (gen[1])
    if np:
        w.raw(np_block if np_block is not None else bytes(22))   # the NP descriptor (np_block)
    w.u16(len(abilities))                              # 0x140d0e060: n * (u8 level, u32 ability): a new troop's only
    for aid, lv in abilities:                          # abilities (MakeTroopGenInfoForBuild 0x140cf7080: slot = the
        w.u8(lv).u32(aid)                              # place in the list; the table's are not read), slots 0-3 its
                                                       # C1-C4 on the HUD (0x1408ead40)
    w.u16(len(passives))                               # 0x140d0de10: n * (u8 level, u32 ability), slots 0x10 + the
    for aid, lv in passives:                           # place: the passives (an NP row's PASSIVESKILLnn after its 16
        w.u8(lv).u32(aid)                              # ACTIVESKILLnn)
    block = encode_stats(stats or {}, troop_stats)     # never empty: 0x140cfbe30 reads the count byte regardless
    w.u16(len(block)).raw(block)                       # 0x140d0dad0: stat block (encode_stats)
    w.u16(0)                                           # 0x140d0dc50: n*11
    w.obool(False)                                     # 0x140d0d260
    c = bytearray(17)                                  # 0x140d0cf00 block: the troop position
    c[1:5] = q; struct.pack_into("<h", c, 5, y); c[7] = p15
    struct.pack_into("<H", c, 0x0f, units)             # unit count; nonzero -> unit list (0x140d0e210)
    w.raw(bytes(c))
    if units:                                          # u16 n, n * (obool alive, 2 bytes, [alive: u16 m, m * 11])
        w.u16(units)
        for _ in range(units):
            w.obool(True).raw(bytes([0xFF, 0xFF])).u16(0)   # experiment: 2 bytes unknown (0xffff = full ratio?)
    w.obool(False)                                     # 0x140d0cf90: no 0x140d1ffe0 block, then 6 bytes that
    w.u16(NO_CAPTURE).obool(False).u8(0).u8(0).u8(0)   # MakeTroopGenInfoForBuild reads (0x140cf7c50..0x140cf7ca2):
                                                       # +0 u16 / +4 u8 a capture-point marker when not 0xffff / 0
                                                       # (UiInGameTroopIcon C2A_addCapture over the troop), +2 obool
                                                       # elite (troop +0x11b8: the minimap's EliteTroop skull,
                                                       # 0x140d31850). Zeros asked for both (0x00 is OBOOL_TRUE): a
                                                       # marker over every troop and a skull for every enemy (owner
                                                       # 2026-09-30 13:30, tests/test_troop_marks.py)


def pack_value(buf, off, v):
    """Packed u32 the client reads as u16[off] * 0x10000 + u16[off + 2] (little-endian u16s); top 2 bits pick a
    scale (x1, x2, x5, x10), so values below 2^30 are stored as is."""
    struct.pack_into("<HH", buf, off, v >> 16, v & 0xFFFF)


def encode_stat(stat_id, value):
    """One stat entry as 0x141593210 parses it (current = max): u8 id, u8 code, payload. Codes: 5..0x7f -> code - 0x42
    (-61..61); 0 -> u8 + 0x3e; 2 -> u16 + 0x13e; 4 -> i32 (1 and 3 are the negative forms)."""
    if -61 <= value <= 61:
        return bytes([stat_id, value + 0x42])
    if 0x3e <= value <= 0x3e + 0xff:
        return bytes([stat_id, 0, value - 0x3e])
    if 0x13e <= value <= 0x13e + 0xffff:
        return bytes([stat_id, 2]) + struct.pack("<H", value - 0x13e)
    return bytes([stat_id, 4]) + struct.pack("<i", value)


def encode_stats(leader, troop=None):
    """Stat block of the troop-state tail (0x50b8 handler 0x140d052e0): u8 troop stat count, the troop's entries, then
    the leader's entries up to the block end."""
    troop = troop or {}
    return (bytes([len(troop)]) + b"".join(encode_stat(k, v) for k, v in troop.items())
            + b"".join(encode_stat(k, v) for k, v in leader.items()))


def send_actions(s, *actions):
    """Each action: [id, arg, ...] in one 0x5087 packet: ints as u32s, strings as C strings (the handlers read those
    straight from the packet, 0x1415835b0: ActGuiStartTutorial's name)."""
    for act in actions:
        w = Writer(S2C_SCRIPT_ACTION)
        for v in act:
            if isinstance(v, str):
                w.cstr(v)
            else:
                w.u32(v)
        s.send(w)
        if act[0] == ACT_ENABLE_ALL_TROOPS:          # it reaches the reserve too: out again at once (changetroop.py),
            send_actions(s, *([ACT_ENABLE_TROOP, 0, uid, 0, 1] for uid in s.data.get("reserve") or ()),
                         *([ACT_ENABLE_TROOP, 0, uid, 0, 0] for uid in sorted(s.data.get("left") or ())))  # and who left


def send_condition(s, serial, cond, *args):
    """Ask the client a condition (S2C 0x5086): the serial comes back with the answer; tag and key 0 (only echoed);
    the arguments as u32s and C strings, as send_actions."""
    w = Writer(S2C_CONDITION).u32(cond).u32(serial).u8(0).u32(0)
    for v in args:
        if isinstance(v, str):
            w.cstr(v)
        else:
            w.u32(v)
    s.send(w)


def condition_answer(body):
    """(serial, holds) of a C2S 0x5089 condition answer: X, tag, Y with A = X ^ Y and the serial | holds << 31 =
    (A & ~M) | (Y & M) (ReturnCondition 0x140b2f0b0 mixes it with the query's key); None for the script console's
    longer form (header 0x140b2ce10)."""
    if len(body) != 9:
        return None
    x, _, y = struct.unpack("<IBI", body)
    s = ((x ^ y) & ~CONDITION_MIX | y & CONDITION_MIX) & 0xFFFFFFFF
    return s & 0x7FFFFFFF, bool(s >> 31)


def send_prompt(s, pid, key):
    """Put up a key prompt (S2C 0x50c1): the client answers C2S 0x50c2 (pid) when the player presses key (an
    InputEvent); key 0 is never checked. The value is only shown for the F key (0x32)."""
    s.send(Writer(S2C_KEY_PROMPT).u32(key).u8(pid).u32(0))


def cancel_prompt(s, pid):
    s.send(Writer(S2C_KEY_PROMPT_OFF).u8(pid))

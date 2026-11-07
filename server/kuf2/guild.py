"""The guild: a guild of one, kept in the save (planning/todo/CONTRACT-COMPLETE-PLAN.md family 3; CommonSubGuild scene
0x20, GuildRanking 0x21, GuildSearch 0x22, GuildInfo 0x23; planning/requests/guild_trade_realm.md G12, planning/client/
social.md). The character who creates a guild is its master and only member; what needs a second player takes the
original's own "nobody there" answer.

The client is in a guild while its PlayerInfo guild name is not empty (common+0x168, size common+0x178: the gate of
/inviteguild 0x1405d587f and of the login chain 0x140e793ff). At login that name is the second cstr of the character's
entry in the character list (lobby 0x140e78af0 -> LobbyCharacter+0x98, copied to PlayerInfo by 0x1405a79b0), so
world.write_char_entry must send name_of(c) there; with it the 0x1012 handler asks 0x3d40, 0x3d42, 0x3d82, 0x3d73 by
itself. In the session a 0x3d41 / 0x3d61 success sets it (CommonSubGuild::InitPlayerInfoGuildName 0x1405d7060).

Result codes go to CommonSubGuild::ShowErrorMSG 0x1405d61c0 (texts: Info.pkg text\\eng\\textsystem_eng):
  0x0412 -> 7076 "The player is not valid."         0x5401 -> 53287 "Not authorised to perform the action."
  0x5402 -> 53288 "The player is already in a guild, or has another character within the account that is already in a
  guild."     0x5404 -> 53289 "Already a guild member."     0x5405 -> 53290 "The player is not in a guild."
  0x5407 -> 53292 "Not an appropriate Unique ID for guild."   0x5409 -> 53254 "The guild name already exists ..."
  0x5415 -> nothing (no text, no assert)                    0x5418 -> 53403 "Not enough guild points."
Every reply's i16 is dereferenced unchecked: no reply is shorter than 2 bytes. "coded u32" = obf.u32, "time64" =
obf.time64 (Unix seconds). Strings are NUL-terminated and kept byte for byte (latin-1 in the save).

The rules and where they are:
  create        GuildCreateCost 10000 gold (%Content, client +0x360: 0x1405d5300 refuses first with text 53255); the
                name 2..20 characters without a space (texts 26, 250); one guild an account (text 53288)
  members       guild_point %Guild_Default_Member 20; +2 a step for %Guild_Population's Guild_Point, up to 60
  authorities   guild_point %Guild_Grade (9 rights x 5 grades), bit = the Flash AUTH_* index
  level         lvexptable %GuildExp (levels 1..10, the exp of each level; 10 has none)
  skills        guild_point %Guild_Skill (65 rows: an id a level; Skill_Type 1 hero, 2 troop, 3 utility; Guild_Point the
                price of that level), 17 skill points in all (the client's constant 0x1421922d0, one a level); a core
                skill needs 5 normal levels of its type, the second one 10 (Flash UpdateCoreSkillLock); a reset costs
                1,500,000 points and returns the points the skills cost (0x1405d4aa0, box 53417)
  shop goods    guild_point %Guild_ItemSale (28 goods): opened or extended for limit_Time seconds with Guild_Point
                points (Type Point) or one Guild_Item (Type Item)
  earning       the three Guild_* columns of a questtable row (743 quests) or a mission_reward row: Guild_Exp to the
                guild's exp, Guild_Point to its points, Guild_Contribution to the member (on_quest, on_mission)
The daily guild-point limit is the window's own line, "Can earn up to 10,000 points a day" (DAILY_POINTS; read off the
native window 2026-11-05: no table holds it). Which points it counts is ours: the Guild_Point a character earns in a
game day; exp and contribution go on past it. Not in any table, note or footage, so not kept: the 24-hour lock after
leaving (0x5414 is never sent).

What a learned skill does (each number from its row; the client's own arithmetic where it has one):
  hero          Skill_Type 1, Ability_ID 350001-350004 (abilitytypeinfo Category AUTOMATIC, Subject LEADER): the SELF
                traits of the abilitycastinfo row at the skill's level, 1..5 %: 350001 ATTACK_PHYSICAL and
                ATTACK_MAGICAL, 350002 M_DEFENCE_PHYSICAL, 350003 SP_MAX, 350004 M_DEFENCE_MAGICAL. hero_abilities ->
                hero.char_stats counts them as it counts the worn title's ability. After a learn or a reset the hero
                block goes out again (refresh_hero); the reset push 0x3d89 also makes the client ask 0x10b7.
                The two cores are not passives (Category MOTION): 350013 "Guild Defence" and 350014 "Guild Escape"
                change the hero's room kit (hero_kit -> skills.battle_abilities, the 0x3f50 leader list; in a room
                0x50a9, refresh_hero). The server lists the learned id alone, level 1. The client does the rest:
                adding an ability (0x14083e470) also adds its abilitytypeinfo %Link rows at the same level (350013:
                350005-350008, 350016; 350014: 350009-350012), and the guard key's resolver (0x140c213a0) casts the
                stanceactioninfo %CHANGE_SKILL id when the troop holds it (condition 8: GLEN 62 -> 350005, 14 ->
                350009, ISABELLA 304 -> 350006, 310 -> 350010, REGNIER 604 -> 350007, 614 -> 350011, OLIVIA 909 ->
                350008, 914 -> 350012). So the cast that arrives names the variant: its row gives 341 / 3040 / 6040 /
                6339 at level 3, whose GUARD_REDUCE ends at 75 ("from 70% to 75%"); the escapes CooldownTime 14 (the
                client's own clock), 6321 at level 1. Only the classes whose heroskillbook lists the core get it:
                the Druid has no book row and no %CHANGE_SKILL row (350016 is dead data), Helena neither and no guard
                or escape key; learning spends the guild's points all the same. No packet takes an ability away and
                the client's remove on a reset (0x1405d7cb0) passes guild skill ids, not abilities: after a reset
                or a dismiss in a room the variant stays until the next room, as the client has it.
  troops        Skill_Type 2, Ability_ID 75027 / 75028 / 75029 / 75034 and the cores 75031 / 75032 (AUTOMATIC, Subject
                LEADER, TargetType LIVE_ALLY, AffectType TROOP): the abilitycastinfo row's StatusEffect1 at Level1
                (750270 ATTACK_PHYSICAL / _MAGICAL +2..10 %, 750280 M_DEFENCE_PHYSICAL +6..30 x the troop's level,
                750290 HP_MAX +2..10 %, 750340 M_DEFENCE_MAGICAL +6..30 x level, 750310 MAX_MOVE_SPEED +10 %, 750320
                M_CRITICAL_PROB +5 x level) held by each deck troop its TargetBranch1 26 "all units" takes (every
                troop branch but OGRE and SCORPION): troop_statuses, as the main deck's troop set status goes on
                (troops.room_row, status.room_start, status.troop_revived).
  utility       Skill_Type 3, the %Util_Skill row of the same id (Skill_Effect, value); the client's lookup is
                0x1405d4ee0 (the learned ids, the first whose row has the effect: its value):
                Repair_Discount   CommonSubShop 0x140e2af90: the repair's total less trunc(value x total / 100)
                Enchant_Discount  the item enchant window 0x1405fa0f3: the gold less trunc(value x gold / 100)
                MakeCost_Discount the craft window 0x1405b1c49: %CraftLevelUP Gold_Rate (per mille) less 10 x value
                Auction_Discount  UISceneAuction 0x1409531e0 hands it to the sold-goods list only (0x140958ea0, where
                                  AuctionFeePerc is taken); text 13203: "Guild Auction Hall fee only applies to Item
                                  Collect Fee". Nothing sells on a server of one (market.py), so no gold is ever
                                  charged that it lowers; the register deposit is not discounted.
                TroopExp_Up       text 13205 "Troop Mission Reward EXP increased by 10%": each deployed troop's exp
                                  of a won mission (troops.gain_exp) plus value percent of it, rounded down as a
                                  boost event's (events.boosted). The barracks pool's share is not raised (no source).

The guild shop (NPC menu GUILD_STORE, npctable 314 / 315 / 806 / 1150, MENU_VALUE 1000; scene 0x24, CommonSubGuildShop
0x1405f2930): itemsaletable 1000's 33 slots. The window (0x1409806c0) leaves out a slot whose item is on the guild's
list (%Guild_ItemSale, 0x3d7c) and not open; the five slots that are not on it (the [Lv 1] potions 350550010 ..
350554010) are always there. A buy is the NPC shops' 0x1540 (0x140e47fc0 -> 0x140e4e880: +2 u32 scene+0x3c, +6 u32
the shop id 1000, +12 the itemsaletable slot), after the client's own check (0x1405f3670): the item's BuyPrice (item
record +0x78) x count against common+0x120, the member's contribution, else text 7034. Every good's item row is
MoneyType 3, which the builder reads as that currency (dnd+0x90 == 3). world.store_buy hands a MoneyType 3 good to
buy: the contribution falls by BuyPrice x count, the item goes to the bag, 0x1541's u64 is the contribution left.
0x1541 (0x140e50310) prints 7034 "Not enough balance. Cannot purchase the item." for 0x6401 and 34 "Item purchase
failed." for any code it has no case for: what a member with no guild or a good that is not open gets (which code
the original used is not known).

The Guild Name Change Form (item 351400030, ConsumeItemType GUILD_NAME = the client's type 0x19): a right-click in the
bag (0x140dd3d64) says 7298 "You are not in a guild." without one, else opens the input box 7570 "Enter the new guild
name." owned by the guild (window 9, 0x1407ad750); its answer goes to 0x1405d5c40 (the same name: 53254, a banned
word: 53253), which sends 0x3d8c with the slot's serial. No 0x4042 is sent: world.use_item is not on the path.

Requests and replies (C2S builder; S2C handler):
  0x3d40 (0x140ef5990) no body -> 0x3d41 (0x1405d7d40): i16; 0 -> the 0x3e-byte block, cstr guild name, cstr master
      name, cstr notice, cstr recruitment text (readers 0x1405dce80, 0x1405dcf70, 0x1405dd070). Block: +0 u8 level, +5
      i16 member cap, +7 u64 war points, +0xf u32 guild id, +0x13 u64 guild points, +0x1b u64 exp, +0x23 time64 notice
      time, +0x2b u32 skill points left, +0x2f i16 members, +0x31 u32 master's character id (== common+0xd4 makes the
      client the master), +0x36 time64 recruitment-text time; +1..+4 and +0x35 are not read. Any other code is ignored.
      0x3d61 (0x1405daf70) is the same body without the i16, as a push.
  0x3d90 (0x1405dc870) push, 0x14 bytes: five i32 right masks, wire order Regular, Novice, SubMaster, Senior, Captain;
      silent the first time, then text 53270. Sent after every 0x3d41 success (nothing else carries the rights).
  0x3d42 (0x140ef59e0) no body -> 0x3d43 (0x1405d8330): i16; 0 -> u16 n, n x (0x18 bytes, cstr name): +0 u32 character
      id, +4 coded u32 spot (-1: none), +8 u8 grade (0 master .. 5), +9 obool online, +0xa time64 last logout, +0x12 u8
      level, +0x13 u8 (a mode name when the spot is -1), +0x14 u32 class (readers 0x1405dd180, 0x1405e1cd0; UI
      0x140978140, status 0x14097d180).
  0x3d44 (0x140ef5a30) cstr name -> 0x3d45 (0x1405d8fd0): i16; 0 -> u32 (read, unused), text 53251, the client asks
      0x3d40.
  0x3d46 (0x140ef5db0) no body -> 0x3d47 (0x1405d8b00): i16; 0 -> text 53282, the guild cleared.
  0x3d48 (0x140ef5e00) cstr name -> 0x3d49 (0x1405d8c20): i16; always clears the pending invitation.
  0x3d4e (0x140ef64f0) u32 member, 0x3d51 (0x140ef6830) u8 grade + u32 member, 0x3d53 (0x140ef6b80) no body ->
      0x3d4f, 0x3d52, 0x3d54 (0x1405d8850, 0x1405d87d0, 0x1405d88c0): i16.
  0x3d57 (0x140ef6bd0) u32 first row (1-based), 0x3d59 (0x140ef6f10) cstr name -> 0x3d58, 0x3d5a (0x1405e4100,
      0x1405e4310): i16; 0 -> u32 rows in all, u16 n, n x (0x14 bytes, cstr name): +0 u32 row number, +4 u32 members,
      +8 u32 rank, +0xc u64 points (reader 0x1405e4720, UI 0x14097db50). A success with n = 0 reads a null vector
      (0x1405e42a8): never sent.
  0x3d5d (0x140ef7990) u8 -> 0x3d5e (0x1405db280): i16 (copy read); non-zero flips the client's flag back.
  0x3d5f (0x140ef7290) cstr, 0x3d71 (0x140ef7610) cstr -> 0x3d60, 0x3d72 (0x1405dac90, 0x1405dae00): i16; 0 -> time64
      of the change. The client keeps the text it sent. 0x3d93 / 0x3d94 (0x1405dc960 / 0x1405dc980) push, no body:
      texts 53394 / 53400.
  0x3d62 (0x140ef7cc0) no body -> 0x3d63 (0x1405da8d0): i16; 0 -> u8 "no join requests" flag, u16 n, n x (0x11, cstr).
  0x3d64 (0x1405e5770) cstr text -> 0x3d65 (0x1405e6290): i16; 0 -> u16 n, n x (0xe bytes, cstr master name, cstr guild
      name): +0 i16 member cap, +6 u32 guild id, +0xa u8 level, +0xb i16 members, +0xd u8 1 = takes no requests
      (reader 0x1405f18f0, UI 0x14097e8e0: "members / cap", "Recruiting" unless +0xd is 1).
  0x3d66 (0x1405e5b00) u32 guild, 0x3d6f (0x1405e5f30) u32 guild, 0x3d6b / 0x3d6d (0x140ef7d10 / 0x140ef8050) u32
      applicant -> 0x3d67, 0x3d70, 0x3d6c, 0x3d6e (0x1405e6660, 0x1405e6ea0, 0x1405db300, 0x1405db400): i16 and u32,
      both always read (6 bytes).
  0x3d69 (0x1405e5ec0) no body -> 0x3d6a (0x1405e6bd0): i16; non-zero does nothing.
  0x3d73 (0x140ef8390) no body -> 0x3d74 (0x1405db500): i16; 0 -> u64 today's guild points, u64 my contribution
      (common+0x120, the guild shop's money), u64 the daily limit. 0x3d75 (0x1405db5f0): the same 0x18 bytes, a push.
  0x3d76 (0x1405e3550) u32 guild -> 0x3d77 (0x1405e3890, scene 0x23 while open): i16; 0 -> 0xc bytes (read, unused),
      cstr recruitment text (reader 0x1405e3980, UI 0x14097d820). Non-zero does nothing.
  0x3d78 (0x140ef83e0) u32 guild, u32 -> 0x3d79 (0x1405db670): i16 (copy read); 0 -> the client raises its own cap to
      the next %Guild_Population row and prints 53404; non-zero does nothing.
  0x3d7b (0x140ef8730) no body -> 0x3d7c (0x1405db6f0): i16; 0 -> u16 n, n x (coded u32 item, i32 seconds left): the
      guild shop's open goods (the list the client made from %Guild_ItemSale, 0x1405d7a90).
  0x3d7d (0x140ef8780) coded u32 item (boxes 53398 "add the item to the guild shop?" / 53401 "extend ...?") -> 0x3d7e
      (0x1405db8c0): i16; 0 -> 8 bytes (read, unused). 0x3d7f (0x1405db980) push: coded u32 item, i32 seconds left,
      text 53402. 0x3d80 (0x1405dbab0) push: coded u32 item, closed: the client clears the entry and redraws an open
      window, no text; an item it does not hold is skipped, so a late one does nothing (watch_goods).
  0x3d82 (0x140ef8b00) no body -> 0x3d83 (0x1405dbd20): i16; 0 -> u16 n, n x u32 skill id (one a skill, its level's).
  0x3d84 (0x140ef8b50) u32 skill id, one request a level -> 0x3d85 (0x1405dbea0): i16 and u32, both always read; 0 ->
      the client swaps the lower level's id for this one. The broadcast 0x3d86 does the same swap again, so the
      learner is not sent it.
  0x3d87 (0x140ef8e80) no body -> 0x3d88 (0x1405dc420): i16 and u32 (both read); 0 -> the u32 is the skill points
      left. 0x3d89 (0x1405dc4e0) push, no body: the client empties its skills, text 53298.
  0x3d8c (0x140ef8ed0) coded u16 bag slot, coded u64 serial, cstr name -> 0x3d8d (0x1405dc5a0): i16. 0x3d8e
      (0x1405dc610) push: u32 guild id, cstr name -> the name, text 7571.
  0x3d91 (0x140ef93c0) five i32 masks in 0x3d90's order -> 0x3d92 (0x1405dc800): i16; the change comes by 0x3d90.
  0x3d56 (0x1405da480) push, 0x14 bytes: u32 guild id, u64 guild points, u64 war points.
  0x3d7a (0x1405da7e0) push, 0xd bytes: u32, u8 level, u64 exp; a new level prints 7020.
  0x3d5b (0x1405da500) push, 8 bytes: u32 points -> "<guild> acquired <n> Guild Points." (7140).
  0x3d4c (0x140ef6180), the answer to an invitation, is world.py's role.ignore: no invitation (0x3d4b) is ever pushed
      and its reply 0x3d4d has no refusal form.
"""
import functools
import struct
import time

from . import obf, rules, settings, tables
from .net import journal, log
from .packet import OBOOL_TRUE, Writer

C2S_INFO, S2C_INFO, S2C_INFO_PUSH = 0x3d40, 0x3d41, 0x3d61
C2S_MEMBERS, S2C_MEMBERS = 0x3d42, 0x3d43
C2S_CREATE, S2C_CREATE = 0x3d44, 0x3d45
C2S_DISMISS, S2C_DISMISS = 0x3d46, 0x3d47
C2S_INVITE, S2C_INVITE = 0x3d48, 0x3d49
C2S_KICK, S2C_KICK = 0x3d4e, 0x3d4f
C2S_GRADE, S2C_GRADE = 0x3d51, 0x3d52
C2S_LEAVE, S2C_LEAVE = 0x3d53, 0x3d54
C2S_RANKING, S2C_RANKING = 0x3d57, 0x3d58
C2S_RANKING_FIND, S2C_RANKING_FIND = 0x3d59, 0x3d5a
C2S_PREVENT, S2C_PREVENT = 0x3d5d, 0x3d5e
C2S_MEMO, S2C_MEMO, S2C_MEMO_CHANGED = 0x3d5f, 0x3d60, 0x3d93
C2S_APPLICANTS, S2C_APPLICANTS = 0x3d62, 0x3d63
C2S_SEARCH, S2C_SEARCH = 0x3d64, 0x3d65
C2S_JOIN, S2C_JOIN = 0x3d66, 0x3d67
C2S_MY_REQUESTS, S2C_MY_REQUESTS = 0x3d69, 0x3d6a
C2S_ACCEPT, S2C_ACCEPT = 0x3d6b, 0x3d6c
C2S_REFUSE, S2C_REFUSE = 0x3d6d, 0x3d6e
C2S_WITHDRAW, S2C_WITHDRAW = 0x3d6f, 0x3d70
C2S_NOTE, S2C_NOTE, S2C_NOTE_CHANGED = 0x3d71, 0x3d72, 0x3d94
C2S_POINTS, S2C_POINTS, S2C_POINTS_PUSH = 0x3d73, 0x3d74, 0x3d75
C2S_DETAIL, S2C_DETAIL = 0x3d76, 0x3d77
C2S_MORE_MEMBERS, S2C_MORE_MEMBERS = 0x3d78, 0x3d79
C2S_SHOP, S2C_SHOP = 0x3d7b, 0x3d7c
C2S_SHOP_OPEN, S2C_SHOP_OPEN, S2C_SHOP_OPENED = 0x3d7d, 0x3d7e, 0x3d7f
S2C_SHOP_CLOSED = 0x3d80
C2S_SKILLS, S2C_SKILLS = 0x3d82, 0x3d83
C2S_LEARN, S2C_LEARN = 0x3d84, 0x3d85
C2S_RESET, S2C_RESET, S2C_RESET_DONE = 0x3d87, 0x3d88, 0x3d89
C2S_RENAME, S2C_RENAME, S2C_RENAMED = 0x3d8c, 0x3d8d, 0x3d8e
C2S_RIGHTS, S2C_RIGHTS, S2C_RIGHTS_PUSH = 0x3d91, 0x3d92, 0x3d90
DAILY_POINTS = 10_000           # 0x3d74's third u64: the window's "Can earn up to 10,000 points a day" (module docstring)
S2C_GUILD_POINTS = 0x3d56
S2C_LEVEL = 0x3d7a
S2C_EARNED = 0x3d5b

NOT_VALID = 0x0412              # the texts are in the module docstring
NO_RIGHT = 0x5401
ACCOUNT_IN_GUILD = 0x5402
ALREADY_MEMBER = 0x5404
NOT_IN_GUILD = 0x5405
BAD_GUILD = 0x5407
NAME_EXISTS = 0x5409
SILENT = 0x5415
NO_POINTS = 0x5418

MASTER = 0                      # the member grades: 0 master, 1 SubMaster .. 5 Novice
GRADES = ("SubMaster", "Captain", "Senior", "Regular", "Novice")        # %Guild_Grade's columns, grades 1..5
RIGHT_BIT = {"Banish": 0, "ShopSetUp": 1, "MemberIncrease": 2, "JoinPermit": 3, "MemoWrite": 4, "InfoWrite": 5,
             "Invite": 6, "WarRegister": 7, "LeaveOccupySpot": 8}       # the Flash AUTH_* indexes (UI1 f11f77e1)
RIGHTS_WIRE = (3, 4, 0, 2, 1)   # 0x3d90 / 0x3d91: the five masks as Regular, Novice, SubMaster, Senior, Captain
ALL_RIGHTS = 0x1ff
SKILL_POINTS = 17               # _root.MAX_GUILD_SKILL_POINT, the double at 0x1421922d0
RESET_COST = 1_500_000          # 0x1405d4aa0: the reset is sent only above 1,499,999 points; box 53417 names 1500000
CORE_NEEDS = 5                  # normal levels of the type for each core skill (Flash UpdateCoreSkillLock: 5, then 10)
NAME_MIN, NAME_MAX = 2, 20      # text 26 "Name is limited from 2 to 20 characters."
TEXT_MAX = 2048                 # bytes of a notice the save takes (the client's own field limit is far below)


@functools.cache
def default_cap():
    return int(tables.sections("guild_point")["Guild_Default_Member"][0]["Guild_DefaultMember"])


@functools.cache
def populations():
    """[(member cap, guild points to reach it)], rising: %Guild_Population."""
    return sorted((int(r["Guild_Population"]), int(r["Guild_Point"]))
                  for r in tables.sections("guild_point")["Guild_Population"])


def next_cap(cap):
    """(the next member cap, its price), or None at the last one (the client's 0x1418a8840)."""
    return next(((n, price) for n, price in populations() if n > cap), None)


@functools.cache
def default_rights():
    """The five grades' right masks (SubMaster .. Novice) of a new guild: %Guild_Grade."""
    masks = [0] * len(GRADES)
    for r in tables.sections("guild_point")["Guild_Grade"]:
        for k, grade in enumerate(GRADES):
            if r[grade] == "True":
                masks[k] |= 1 << RIGHT_BIT[r["Grade_Type"]]
    return masks


@functools.cache
def exp_table():
    """{level: the exp that level needs}: lvexptable %GuildExp; the last level has none."""
    return {int(r["Level"]): int(r["Guild_Exp"]) for r in tables.sections("lvexptable")["GuildExp"]
            if r["Guild_Exp"].isdigit()}


@functools.cache
def skill_rows():
    """{Guild_Skill_ID: row} of %Guild_Skill. A skill's levels are consecutive ids (1..5, 11..15, 211..215)."""
    return {int(r["Guild_Skill_ID"]): r for r in tables.sections("guild_point")["Guild_Skill"]}


@functools.cache
def shop_rows():
    return {int(r["ItemCode"]): r for r in tables.sections("guild_point")["Guild_ItemSale"]}


def skill_level(skill):
    return int(skill_rows()[skill]["Skill_Level"])


def skill_price(skill):
    """The guild points a learned skill cost: its level's price and every level's below."""
    return sum(int(skill_rows()[skill - k]["Guild_Point"]) for k in range(skill_level(skill)))


def of(c):
    """Character c's guild (a dict in the save), or None."""
    return (c or {}).get("guild")


def name_of(c):
    """The guild name the character list entry carries (world.write_char_entry's second cstr); "" without one."""
    g = of(c)
    return g["name"] if g else ""


def contribution(c):
    """The member's contribution, the guild shop's money: 0x3d74's second u64 and 0x1541's u64 (common+0x120)."""
    g = of(c)
    return g.get("contribution", 0) if g else 0


def learned(c):
    """The %Guild_Skill rows the character's guild has learned, each at its level (Skill_Type 1: Ability_ID on the
    hero, 2: on its troops, 3: the %Util_Skill row of the same id). An id the table does not have is left out: the
    hero's and the troops' numbers read this at every login and room start."""
    g = of(c)
    return [skill_rows()[k] for k in g.get("skills", []) if k in skill_rows()] if g else []


def points_left(g):
    return SKILL_POINTS - sum(skill_level(k) for k in g.get("skills", []))


# --- what a learned skill does (module docstring) ---

@functools.cache
def util_rows():
    """{Guild_Skill_ID: row} of %Util_Skill: Skill_Effect and value of each utility skill level."""
    return {int(r["Guild_Skill_ID"]): r for r in tables.sections("guild_point")["Util_Skill"]}


def discount(c, effect):
    """The value of the character's guild's learned utility skill of `effect` (%Util_Skill Skill_Effect:
    Repair_Discount, Enchant_Discount, MakeCost_Discount, Auction_Discount, TroopExp_Up), a percent; 0 without one.
    As the client's 0x1405d4ee0: the learned ids in order, the first whose row has the effect."""
    for row in learned(c):
        util = util_rows().get(int(row["Guild_Skill_ID"])) if row["Skill_Type"] == "3" else None
        if util is not None and util["Skill_Effect"] == effect:
            return int(util["value"])
    return 0


def discounted(c, effect, cost):
    """`cost` gold less the guild's discount of `effect`, as the client's repair (0x140e2af90) and item enchant
    (0x1405fa0f3) windows show it: cost - trunc(percent x cost / 100)."""
    return cost - discount(c, effect) * cost // 100


def make_rate_off(c):
    """What MakeCost_Discount takes off the craft's %CraftLevelUP Gold_Rate, per mille: 10 x the percent (the craft
    window 0x1405b1c49 hands the Flash Gold_Rate - 10 x value as g_nCraftGoldDecRate)."""
    return 10 * discount(c, "MakeCost_Discount")


def troop_exp(c, amount):
    """A won mission's exp for one troop under TroopExp_Up: the percent added to the amount, rounded down (as
    events.boosted adds an event's)."""
    return amount + amount * discount(c, "TroopExp_Up") // 100


def hero_abilities(c):
    """{ability: level} of the learned hero skills (Skill_Type 1) that are passives (abilitytypeinfo Category AUTOMATIC:
    350001-350004); hero.char_stats reads their SELF traits. The cores 350013 / 350014 are MOTION abilities: left
    out (hero_kit)."""
    from .status import automatic
    return {int(r["Ability_ID"]): int(r["Skill_Level"]) for r in learned(c)
            if r["Skill_Type"] == "1" and r["Ability_ID"].isdigit() and int(r["Ability_ID"]) in automatic()}


def hero_kit(c):
    """{ability: level} the guild adds to the hero's room kit (skills.battle_abilities): the learned hero skills
    (Skill_Type 1) that are no passives, the cores 350013 / 350014, where the class's heroskillbook has the row (GLEN,
    ISABELLA, REGNIER, OLIVIA). Never their %Link rows: the client adds those itself (module docstring)."""
    from . import skills
    from .status import automatic
    cores = {int(r["Ability_ID"]): int(r["Skill_Level"]) for r in learned(c) if r["Skill_Type"] == "1"
             and r["Ability_ID"].isdigit() and int(r["Ability_ID"]) not in automatic()}
    book = skills.book(c["class"]) if cores else {}
    return {a: lv for a, lv in cores.items() if a in book}


@functools.cache
def _troop_branch(troop_id):
    """A deck troop type's branch: trooptype %System BRANCH of its trooptable TroopType."""
    kind = next((r.get("TroopType") for r in tables.sections("trooptable")["Contents"]
                 if r["TROOP_ID"] == str(troop_id)), None)
    return next((r.get("BRANCH", "") for r in tables.sections("trooptype")["System"] if r["TroopType"] == kind), "")


def troop_statuses(c, troop_id=None):
    """[(status, level)] the learned troop skills (Skill_Type 2) put on a deck troop of the character: the
    abilitycastinfo row's StatusEffect1 at Level1 for the skill's level, where its TargetBranch1 (abilitytypeinfo
    %TroopBranch, status.fits' rule: the branch's column is "O") takes the troop's branch. troop_id None: every one."""
    from . import status
    out = []
    for r in learned(c):
        if r["Skill_Type"] != "2" or not r["Ability_ID"].isdigit() or int(r["Ability_ID"]) not in status.automatic():
            continue
        row = status.cast_row(int(r["Ability_ID"]), int(r["Skill_Level"])) or {}
        st, lv = str(row.get("StatusEffect1", "")), str(row.get("Level1", ""))
        branch = str(row.get("TargetBranch1", ""))
        if not st.isdigit() or not lv.isdigit():
            continue
        takes = status._filter_rows("TroopBranch", "BranchId").get(branch) if troop_id is not None else None
        if takes is not None and takes.get(_troop_branch(troop_id).upper()) != "O":
            continue
        out.append((int(st), int(lv)))
    return out


def refresh_hero(s, state):
    """The hero's numbers after a learn or a reset, as a worn title's change sends them (titles.wear_title): the Info
    window's block (0x1081) and, with a room open, his stats there (0x5138)."""
    from . import world
    c = s.data["char"]
    s.send(Writer(world.S2C_HERO_BLOCK).raw(world.hero_block(c)))
    g = getattr(state, "game_sessions", {}).get((s.data.get("account") or {}).get("id"))
    if g is not None and "battle" in g.data and not g.w.is_closing():
        from . import game, skills
        if g.data.get("char") is c or (g.data.get("char") or {}).get("id") == c.get("id"):
            kit = g.data.get("kit") or {}           # a core learned here: 0x50a9, the client adds it and its %Link rows
            g.data["kit"] = skills.battle_abilities(c)
            for aid in sorted(set(g.data["kit"]) - set(kit)):
                g.send(Writer(skills.S2C_ROOM_SKILL).u16(0).u32(aid))
        game.room_stats(g, c)


def new(c, name, now=None):
    """A guild of one for character c: level 1, the table's member cap and rights, nothing learned or opened."""
    return {"id": c["id"], "name": name, "level": 1, "exp": 0, "point": 0, "contribution": 0, "cap": default_cap(),
            "memo": "", "memo_at": 0, "info": "", "info_at": 0, "prevent": False, "rights": list(default_rights()),
            "skills": [], "shop": {}, "created": int(now if now is not None else time.time())}


def valid_name(name):
    try:
        n = len(name.encode("latin-1").decode("utf-8"))
    except (UnicodeError, ValueError):
        n = len(name)
    return NAME_MIN <= n <= NAME_MAX and " " not in name


def world_guilds(account):
    """The guilds a player of this account can see: those of its characters (one at most), best first."""
    found = [(c, of(c)) for c in (account or {}).get("characters", []) if of(c)]
    return sorted(found, key=lambda cg: -cg[1].get("point", 0))


def open_goods(g, now=None):
    """{item code: seconds left} of the guild shop's open goods; what ran out is dropped from the save's dict."""
    now = time.time() if now is None else now
    shop = g.setdefault("shop", {})
    for code in [k for k, end in shop.items() if end <= now]:
        del shop[code]
    return {int(k): int(end - now) for k, end in shop.items()}


def watch_goods(s, g):
    """0x3d80 at the end of each open good this connection has not watched yet. Extending a good moves its end, so the
    earlier timer finds it still open and the new one closes it."""
    watched = s.data.setdefault("shop_watched", {})

    def close(code):
        if code not in open_goods(g):
            s.send(Writer(S2C_SHOP_CLOSED).raw(obf.u32(code)))

    for code, left in open_goods(g).items():
        end = g["shop"][str(code)]
        if watched.get(code) != end:
            watched[code] = end
            s.later(left, lambda code=code: close(code))


def cstr(text):
    return text.encode("latin-1") + b"\0"


def take_text(pkt):
    """The request's next NUL-terminated string, byte for byte (None when it has no NUL)."""
    rest = pkt.rest()
    end = rest.find(0)
    if end < 0:
        return None
    pkt.pos += end + 1
    return bytes(rest[:end]).decode("latin-1")


def info_body(c, g):
    """0x3d41's success body after the i16, and all of 0x3d61."""
    b = bytearray(0x3e)
    b[0] = g.get("level", 1)
    struct.pack_into("<h", b, 5, g.get("cap", default_cap()))
    struct.pack_into("<I", b, 0xf, g["id"])
    struct.pack_into("<Q", b, 0x13, g.get("point", 0))
    struct.pack_into("<Q", b, 0x1b, g.get("exp", 0))
    b[0x23:0x2b] = obf.time64(g.get("memo_at", 0))
    struct.pack_into("<I", b, 0x2b, points_left(g))
    struct.pack_into("<h", b, 0x2f, 1)
    struct.pack_into("<I", b, 0x31, c["id"])
    b[0x36:0x3e] = obf.time64(g.get("info_at", 0))
    return bytes(b) + cstr(g["name"]) + cstr(c.get("name", "")) + cstr(g.get("memo", "")) + cstr(g.get("info", ""))


def member_record(c):
    """The master, online where the save has it: 0x18 bytes and the name."""
    return (struct.pack("<I", c["id"]) + obf.u32(c.get("spot", 0)) + bytes([MASTER, OBOOL_TRUE]) + obf.time64(0)
            + bytes([c.get("level", 1), 0]) + struct.pack("<I", c.get("class", 0)) + cstr(c.get("name", "")))


def rights_packet(g):
    masks = g.get("rights") or default_rights()
    return Writer(S2C_RIGHTS_PUSH).raw(struct.pack("<5i", *(masks[k] for k in RIGHTS_WIRE)))


def today_points(c):
    """The Guild_Point the character earned this game day (rules.game_day)."""
    d = c.get("guild_day") or {}
    return d.get("point", 0) if d.get("day") == str(rules.game_day(time.time())) else 0


def my_points(c):
    """0x3d74 / 0x3d75's 0x18 bytes: today's points, my contribution, the daily limit (module docstring)."""
    return struct.pack("<QQQ", today_points(c), contribution(c), DAILY_POINTS if of(c) else 0)


def guild_points_packet(g):
    return Writer(S2C_GUILD_POINTS).raw(struct.pack("<IQQ", g["id"], g.get("point", 0), 0))


def ranking_body(account):
    """0x3d58 / 0x3d5a's success body after the i16; None with no guild to list (an empty success crashes)."""
    rows = world_guilds(account)
    if not rows:
        return None
    body = struct.pack("<IH", len(rows), len(rows))
    for k, (_, g) in enumerate(rows, 1):
        body += struct.pack("<IIIQ", k, 1, k, g.get("point", 0)) + cstr(g["name"])
    return body


def search_entry(c, g):
    return (struct.pack("<h", g.get("cap", default_cap())) + bytes(4) + struct.pack("<I", g["id"])
            + bytes([g.get("level", 1)]) + struct.pack("<h", 1) + bytes([1 if g.get("prevent") else 0])
            + cstr(c.get("name", "")) + cstr(g["name"]))


def earn(s, state, exp=0, point=0, gift=0, c=None):
    """Add guild exp, guild points and the member's contribution to the character's guild, save, and push what
    changed: 0x3d7a (level and exp; a new level prints its text), 0x3d56 (the guild's points), 0x3d75 (my
    contribution), 0x3d5b (the "acquired" line). False without a guild or with nothing to add. s is the world
    session; with c given it may be None (nobody to tell: the save alone changes)."""
    c = s.data["char"] if c is None else c
    g = of(c)
    point = min(point, DAILY_POINTS - today_points(c))
    if g is None or not (exp or point or gift):
        return False
    send = s.send if s is not None else (lambda w: None)
    need = exp_table()
    if exp and g.get("level", 1) in need:
        g["exp"] = g.get("exp", 0) + exp
        while g["level"] in need and g["exp"] >= need[g["level"]]:
            g["exp"] -= need[g["level"]]
            g["level"] += 1
        if g["level"] not in need:              # the last level has no exp of its own
            g["exp"] = 0
        send(Writer(S2C_LEVEL).raw(struct.pack("<IBQ", g["id"], g["level"], g["exp"])))
    if point:
        g["point"] = g.get("point", 0) + point
        c["guild_day"] = {"day": str(rules.game_day(time.time())), "point": today_points(c) + point}
        send(guild_points_packet(g))
        send(Writer(S2C_EARNED).raw(struct.pack("<II", point, 0)))
    if gift:
        g["contribution"] = g.get("contribution", 0) + gift
    if point or gift:
        send(Writer(S2C_POINTS_PUSH).raw(my_points(c)))
    state.save()
    journal("guild", ev="earn", guild=g["name"], exp=exp, point=point, contribution=gift, level=g["level"])
    return True


def _guild_columns(row):
    def number(key):
        v = str(row.get(key, ""))
        return int(v) if v.isdigit() else 0
    return number("Guild_Exp"), number("Guild_Point"), number("Guild_Contribution")


def on_quest(s, state, row):
    """A quest handed in (quest.hand_in): its questtable row's Guild_Exp, Guild_Point and Guild_Contribution go to
    the character's guild. s is the world session."""
    return earn(s, state, *_guild_columns(row))


def on_mission(s, state, row):
    """A mission won, with the mission_reward row that pays it (%DATA for the spot, difficulty and grade; None where
    the grade pays nothing): its Guild_Exp, Guild_Point and Guild_Contribution go to the hero's guild, as a quest's
    do. s is the room's game session (game.py's mission win) or the world session: the pushes are the guild
    window's, GameStateCommon's (dispatcher 0x140d58c40, the store reply 0x1541's too), so they go to the account's
    world session playing the same character, as a quest's do in a field; with none, the save alone changes and the
    client reads the numbers at its next 0x3d40 / 0x3d73. Not seen natively with a result window up."""
    if not row:
        return False
    c = s.data.get("char")
    if c is None:
        return False
    w = getattr(state, "world_sessions", {}).get((s.data.get("account") or {}).get("id"))
    if w is None and "battle" not in s.data:
        w = s                                   # called with the world session itself
    if w is not None and (w.data.get("char") is not c or getattr(getattr(w, "w", None), "is_closing", bool)()):
        w = None                                # another character's connection, or one that is going: nobody to tell
    return earn(w, state, *_guild_columns(row), c=c)


MONEY_CONTRIBUTION = 3          # an item row's MoneyType 3: priced in the member's contribution (0x140e4e880 reads
                                # dnd+0x90 == 3 as common+0x120; every good of itemsaletable 1000 is one)
SHOP_BAG_FULL = 0x6403          # 0x1541 (0x140e50310): text 52868 "Cannot receive the item because the inventory is
                                # full." (the window checks the bag itself first, 0x140dc9160: text 52867)


def buy(s, state, shop, slot, code, qty, cost, dst):
    """world.store_buy's 0x1540 for a good priced in contribution (the guild shop, module docstring): `qty` of item
    `code` from `slot` of itemsaletable `shop` for `cost`, into bag slot `dst`. Refused with 0x1541's own texts: 34
    for a character with no guild or a %Guild_ItemSale good the guild has not opened (the window does not list it),
    7034 short of contribution, 52868 when the bag cannot take it. A success takes the contribution, gives the item,
    answers with the contribution left (the handler stores the u64 at common+0x120) and sends the bag."""
    from copy import deepcopy

    from . import items, world
    c = s.data["char"]
    g = of(c)

    def reply(result):                          # the handler reads 15 bytes on every result
        s.send(Writer(world.S2C_STORE_BUY).u16(result).u64(contribution(c)).raw(obf.u40(c.get("gold", 0))))

    if g is None or (code in shop_rows() and code not in open_goods(g)):
        log.warning("guild shop %d slot %d (%d) refused: %s", shop, slot, code, "no guild" if g is None else "not open")
        return reply(NOT_IN_GUILD if g is None else NO_RIGHT)
    if g.get("contribution", 0) < cost:
        return reply(world.NOT_ENOUGH_GOLD)
    if not world.fits(c, [(code, qty)]):
        return reply(SHOP_BAG_FULL)
    before = {it["slot"]: deepcopy(it) for it in c.get("bag", [])}
    g["contribution"] -= cost
    world.add_item(s, state, code, qty, prefer_slot=dst, mail=False, refresh=False)
    journal("item", ev="buy", code=code, name=items.name(code), n=qty, shop=shop, slot=slot, price=cost,
            money="contribution")
    state.save()
    reply(0)
    after = {it["slot"]: it for it in c.get("bag", [])}
    world.send_cargo(s, changed_slots=sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k)))
    log.info("guild shop %d slot %d: bought %d x%d for %d contribution (%d left)", shop, slot, code, qty, cost,
             g["contribution"])


def make(role, state):
    from . import items, world

    def answer(s, reply, code, more=b""):
        s.send(Writer(reply).u16(code).raw(more))

    @role.on(C2S_INFO)
    def info(s, pkt):
        c = s.data["char"]
        g = of(c)
        if g is None:
            return answer(s, S2C_INFO, NOT_IN_GUILD)            # ignored by the handler: "no guild"
        open_goods(g)
        answer(s, S2C_INFO, 0, info_body(c, g))
        if s.data.get("rights_of") is not g:        # once: the handler prints its "changed" text over masks it has
            s.data["rights_of"] = g                 # (the record, not its id: a guild founded again keeps the id)
            s.send(rights_packet(g))

    @role.on(C2S_MEMBERS)
    def members(s, pkt):
        c = s.data["char"]
        if of(c) is None:
            return answer(s, S2C_MEMBERS, NOT_IN_GUILD)
        answer(s, S2C_MEMBERS, 0, struct.pack("<H", 1) + member_record(c))

    @role.on(C2S_CREATE)
    def create(s, pkt):
        c = s.data["char"]
        name = take_text(pkt)
        cost = settings.get("GuildCreateCost")
        others = [o for o in s.data["account"].get("characters", []) if o is not c and of(o)]
        if of(c) is not None:
            code = ALREADY_MEMBER
        elif others:
            code = ACCOUNT_IN_GUILD
        elif name is None or not valid_name(name) or not c.get("realm") or c.get("gold", 0) < cost:
            code = NO_RIGHT                     # each refused by the client before sending (texts 26, 250, 7647, 53255)
        else:
            code = 0                            # no other guild can hold the name: the account has none
        if code:
            log.warning("guild create %r refused: 0x%04x", name, code)
            return answer(s, S2C_CREATE, code)
        g = c["guild"] = new(c, name)
        answer(s, S2C_CREATE, 0, struct.pack("<I", g["id"]))
        world.add_gold(s, state, -cost, why="guild create")     # saves; the client takes no gold itself
        journal("guild", ev="create", guild=name, id=g["id"], cost=cost)
        log.info("guild %r created by %s for %d gold", name, c.get("name"), cost)

    @role.on(C2S_DISMISS)
    def dismiss(s, pkt):
        c = s.data["char"]
        g = of(c)
        if g is None:
            return answer(s, S2C_DISMISS, NOT_IN_GUILD)
        del c["guild"]
        state.save()
        answer(s, S2C_DISMISS, 0)
        if g.get("skills"):                     # its hero skills go with it
            refresh_hero(s, state)
        journal("guild", ev="dismiss", guild=g["name"], id=g["id"])
        log.info("guild %r dismissed", g["name"])

    @role.on(C2S_INVITE)
    def invite(s, pkt):
        # nobody else is on this server: the name is of no logged-in player (the account's other character cannot
        # be online at the same time)
        answer(s, S2C_INVITE, NOT_VALID if of(s.data["char"]) else NOT_IN_GUILD)

    @role.on(C2S_KICK)
    def kick(s, pkt):                           # the only member is the master, whom the menu does not offer
        answer(s, S2C_KICK, NOT_IN_GUILD)

    @role.on(C2S_GRADE)
    def grade(s, pkt):                          # the dropdown is disabled on one's own row
        answer(s, S2C_GRADE, NOT_IN_GUILD)

    @role.on(C2S_LEAVE)
    def leave(s, pkt):                          # a master cannot leave (0x1405d5e90, mcLeave disabled): dismiss
        answer(s, S2C_LEAVE, NO_RIGHT if of(s.data["char"]) else NOT_IN_GUILD)

    def ranking(s, reply, text=""):
        account = s.data["account"]
        if text:
            account = {"characters": [c for c, g in world_guilds(account) if text.lower() in g["name"].lower()]}
        body = ranking_body(account)
        if body is None:
            return answer(s, reply, SILENT)     # never a success without a row
        answer(s, reply, 0, body)

    @role.on(C2S_RANKING)
    def ranking_page(s, pkt):
        ranking(s, S2C_RANKING)

    @role.on(C2S_RANKING_FIND)
    def ranking_find(s, pkt):
        ranking(s, S2C_RANKING_FIND, take_text(pkt) or "")

    @role.on(C2S_PREVENT)
    def prevent(s, pkt):
        g = of(s.data["char"])
        b = pkt.rest()
        if g is None or not b:
            return answer(s, S2C_PREVENT, NOT_IN_GUILD)
        g["prevent"] = bool(b[0])
        state.save()
        answer(s, S2C_PREVENT, 0)

    def write(s, pkt, reply, changed, key):
        g = of(s.data["char"])
        text = take_text(pkt)
        if g is None:
            return answer(s, reply, NOT_IN_GUILD)
        if text is None or len(text) > TEXT_MAX:
            return answer(s, reply, NO_RIGHT)
        g[key], g[key + "_at"] = text, int(time.time())
        state.save()
        answer(s, reply, 0, obf.time64(g[key + "_at"]))
        s.send(Writer(changed))

    @role.on(C2S_MEMO)
    def memo(s, pkt):
        write(s, pkt, S2C_MEMO, S2C_MEMO_CHANGED, "memo")

    @role.on(C2S_NOTE)
    def note(s, pkt):
        write(s, pkt, S2C_NOTE, S2C_NOTE_CHANGED, "info")

    @role.on(C2S_APPLICANTS)
    def applicants(s, pkt):
        g = of(s.data["char"])
        if g is None:
            return answer(s, S2C_APPLICANTS, SILENT)
        answer(s, S2C_APPLICANTS, 0, bytes([1 if g.get("prevent") else 0]) + struct.pack("<H", 0))

    @role.on(C2S_SEARCH)
    def search(s, pkt):
        text = (take_text(pkt) or "").lower()
        rows = [(c, g) for c, g in world_guilds(s.data["account"]) if text in g["name"].lower()]
        answer(s, S2C_SEARCH, 0, struct.pack("<H", len(rows)) + b"".join(search_entry(c, g) for c, g in rows))

    @role.on(C2S_JOIN)
    def join(s, pkt):
        b = pkt.rest()
        wanted = struct.unpack_from("<I", b)[0] if len(b) >= 4 else 0
        if of(s.data["char"]) is not None:
            code = ALREADY_MEMBER
        elif world_guilds(s.data["account"]):
            code = ACCOUNT_IN_GUILD             # the only guilds listed are this account's
        else:
            code = BAD_GUILD
        answer(s, S2C_JOIN, code, struct.pack("<I", wanted))

    @role.on(C2S_MY_REQUESTS)
    def my_requests(s, pkt):                    # no request to join can be pending: the handler does nothing
        answer(s, S2C_MY_REQUESTS, SILENT)

    def echo(reply, code):
        def handler(s, pkt):
            answer(s, reply, code, pkt.rest()[:4].ljust(4, b"\0"))
        handler.__name__ = f"nobody_{reply:04x}"
        return handler
    role.on(C2S_ACCEPT)(echo(S2C_ACCEPT, NOT_IN_GUILD))         # no applicant can exist (0x3d63's list is empty)
    role.on(C2S_REFUSE)(echo(S2C_REFUSE, NOT_IN_GUILD))
    role.on(C2S_WITHDRAW)(echo(S2C_WITHDRAW, BAD_GUILD))        # no request of mine can exist (0x3d6a)

    @role.on(C2S_POINTS)
    def points(s, pkt):
        answer(s, S2C_POINTS, 0, my_points(s.data["char"]))

    @role.on(C2S_DETAIL)
    def detail(s, pkt):
        b = pkt.rest()
        wanted = struct.unpack_from("<I", b)[0] if len(b) >= 4 else 0
        g = next((g for _, g in world_guilds(s.data["account"]) if g["id"] == wanted), None)
        if g is None:
            return answer(s, S2C_DETAIL, BAD_GUILD)             # ignored by the handler
        answer(s, S2C_DETAIL, 0, struct.pack("<I", g["id"]) + bytes(8) + cstr(g.get("info", "")))

    @role.on(C2S_MORE_MEMBERS)
    def more_members(s, pkt):
        g = of(s.data["char"])
        step = next_cap(g.get("cap", default_cap())) if g else None
        if g is None or step is None:
            return answer(s, S2C_MORE_MEMBERS, NOT_IN_GUILD if g is None else NO_RIGHT)
        cap, price = step
        if g.get("point", 0) < price:
            return answer(s, S2C_MORE_MEMBERS, NO_POINTS)
        g["point"] -= price
        g["cap"] = cap
        state.save()
        answer(s, S2C_MORE_MEMBERS, 0)
        s.send(guild_points_packet(g))
        journal("guild", ev="members", guild=g["name"], cap=cap, price=price)

    @role.on(C2S_SHOP)
    def shop(s, pkt):
        g = of(s.data["char"])
        if g is None:
            return answer(s, S2C_SHOP, NOT_IN_GUILD)
        goods = open_goods(g)
        watch_goods(s, g)
        answer(s, S2C_SHOP, 0, struct.pack("<H", len(goods))
               + b"".join(obf.u32(code) + struct.pack("<i", left) for code, left in goods.items()))

    @role.on(C2S_SHOP_OPEN)
    def shop_open(s, pkt):
        c = s.data["char"]
        g = of(c)
        b = pkt.rest()
        row = shop_rows().get(obf.dec_u32(b[:4])) if len(b) >= 4 else None
        if g is None or row is None:
            return answer(s, S2C_SHOP_OPEN, NOT_IN_GUILD if g is None else NO_RIGHT)
        code, now, price, coin = int(row["ItemCode"]), int(time.time()), 0, None
        if row["Type"] == "Point":
            price = int(row["Guild_Point"])
            if g.get("point", 0) < price:
                return answer(s, S2C_SHOP_OPEN, NO_POINTS)
            g["point"] -= price
        else:                                   # Type Item: one of its Guild_Item (the slot's coin icon)
            coin = max((it for it in c.get("bag", []) if it["code"] == int(row["Guild_Item"])),
                       key=lambda it: it["slot"], default=None)
            if coin is None:
                return answer(s, S2C_SHOP_OPEN, NO_RIGHT)
            world.take_serial(c, coin["serial"], 1)
            journal("item", ev="spend", code=coin["code"], name=items.name(coin["code"]), n=1, why="guild shop goods")
        goods = g.setdefault("shop", {})
        goods[str(code)] = max(now, goods.get(str(code), 0)) + int(row["limit_Time"])
        left = int(goods[str(code)] - now)
        state.save()
        opened = obf.u32(code) + struct.pack("<i", left)
        answer(s, S2C_SHOP_OPEN, 0, opened)
        s.send(Writer(S2C_SHOP_OPENED).raw(opened))
        watch_goods(s, g)
        if coin is None:
            s.send(guild_points_packet(g))
        else:
            world.send_cargo(s, changed_slots=[coin["slot"]])
        journal("guild", ev="shop", guild=g["name"], code=code, name=items.name(code), price=price, seconds=left)

    @role.on(C2S_SKILLS)
    def skills(s, pkt):
        g = of(s.data["char"])
        if g is None:
            return answer(s, S2C_SKILLS, SILENT)                # the tab asks again at every open
        known = g.get("skills", [])
        answer(s, S2C_SKILLS, 0, struct.pack("<H", len(known)) + b"".join(struct.pack("<I", k) for k in known))

    def refuses_learning(g, skill):
        """The code that refuses learning this skill id now, or 0."""
        row = skill_rows().get(skill)
        known = g.get("skills", [])
        if row is None or points_left(g) < 1:
            return NO_RIGHT
        level, same_type = int(row["Skill_Level"]), [skill_rows()[k] for k in known
                                                     if skill_rows()[k]["Skill_Type"] == row["Skill_Type"]]
        if level > 1 and skill - 1 not in known:                # the level below first, and never twice or backwards
            return NO_RIGHT
        if level == 1 and any(skill <= k < skill + 5 and skill_rows()[k]["Ability_ID"] == row["Ability_ID"]
                              and skill_rows()[k]["Core_Skill"] == row["Core_Skill"] for k in known):
            return NO_RIGHT
        if row["Core_Skill"] == "True":
            cores = sum(1 for r in same_type if r["Core_Skill"] == "True")
            normal = sum(int(r["Skill_Level"]) for r in same_type if r["Core_Skill"] != "True")
            if normal < CORE_NEEDS * (cores + 1):
                return NO_RIGHT
        return NO_POINTS if g.get("point", 0) < int(row["Guild_Point"]) else 0

    @role.on(C2S_LEARN)
    def learn(s, pkt):
        g = of(s.data["char"])
        b = pkt.rest()
        skill = struct.unpack_from("<I", b)[0] if len(b) >= 4 else 0
        code = NOT_IN_GUILD if g is None else refuses_learning(g, skill)
        if code:
            log.warning("guild skill %d refused: 0x%04x", skill, code)
            return answer(s, S2C_LEARN, code, struct.pack("<I", skill))
        price = int(skill_rows()[skill]["Guild_Point"])
        known = g.setdefault("skills", [])
        if skill - 1 in known and skill_level(skill) > 1:
            known.remove(skill - 1)
        known.append(skill)
        g["point"] -= price
        state.save()
        answer(s, S2C_LEARN, 0, struct.pack("<I", skill))
        s.send(guild_points_packet(g))
        refresh_hero(s, state)                  # 0x3d85 asks nothing: a hero skill's numbers go out by themselves
        journal("guild", ev="skill", guild=g["name"], skill=skill, level=skill_level(skill), price=price)

    @role.on(C2S_RESET)
    def reset(s, pkt):
        g = of(s.data["char"])
        if g is None or not g.get("skills"):
            return answer(s, S2C_RESET, NOT_IN_GUILD if g is None else NO_RIGHT, bytes(4))
        if g.get("point", 0) < RESET_COST:
            return answer(s, S2C_RESET, NO_POINTS, bytes(4))
        back = sum(skill_price(k) for k in g["skills"])
        g["point"] += back - RESET_COST
        g["skills"] = []
        state.save()
        answer(s, S2C_RESET, 0, struct.pack("<I", SKILL_POINTS))
        s.send(Writer(S2C_RESET_DONE))
        s.send(guild_points_packet(g))
        refresh_hero(s, state)                  # 0x3d89 makes the client ask 0x10b7 (the attack) only
        journal("guild", ev="reset", guild=g["name"], back=back, price=RESET_COST)

    @role.on(C2S_RENAME)
    def rename(s, pkt):
        c = s.data["char"]
        g = of(c)
        b = pkt.rest()
        if g is None or len(b) < 11:
            return answer(s, S2C_RENAME, NOT_IN_GUILD)
        serial = obf.dec_u64(b[2:10])
        pkt.pos += 10
        name = take_text(pkt)
        form = world.bag_item(c, serial)
        if (form is None or (items.row(form["code"]) or {}).get("ConsumeItemType") != "GUILD_NAME"
                or name is None or not valid_name(name)):
            return answer(s, S2C_RENAME, NO_RIGHT)
        if any(name.lower() == other["name"].lower() for _, other in world_guilds(s.data["account"])):
            return answer(s, S2C_RENAME, NAME_EXISTS)           # its own name too (the client's text 53254)
        slot, old = form["slot"], g["name"]
        world.take_serial(c, serial, 1)
        g["name"] = name
        state.save()
        answer(s, S2C_RENAME, 0)
        s.send(Writer(S2C_RENAMED).raw(struct.pack("<I", g["id"]) + cstr(name)))
        world.send_cargo(s, changed_slots=[slot])
        journal("guild", ev="rename", guild=name, was=old, item=form["code"])

    @role.on(C2S_RIGHTS)
    def rights(s, pkt):
        g = of(s.data["char"])
        b = pkt.rest()
        if g is None or len(b) < 20:
            return answer(s, S2C_RIGHTS, NOT_IN_GUILD)
        wire = struct.unpack_from("<5i", b)
        masks = [0] * len(GRADES)
        for at, k in enumerate(RIGHTS_WIRE):
            masks[k] = wire[at] & ALL_RIGHTS
        g["rights"] = masks
        state.save()
        answer(s, S2C_RIGHTS, 0)
        s.send(rights_packet(g))

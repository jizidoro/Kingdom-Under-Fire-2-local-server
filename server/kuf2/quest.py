"""Quests (INVENTORY section 4 Quests; REQUEST-MAP-PLAN group G19, phase R1).

The client builds quest offers itself from its questtable and the finished list. The server keeps each character's
active and finished quests (character "quests": {"active": {id: {...}}, "done": [id, ...]}), answers accept / complete /
abandon, and moves the conditions (Complete1..5 in questtable).
"""
import functools
import random
import struct, time

from . import hero, items, obf, tables
from .net import journal, log
from .obf import T1
from .packet import Writer

S2C_ACTIVE = 0x5540     # 0x140d7c8a0: u16 n, n * 26-byte entry (write_active) -> AddPlayerQuestInfo 0x140d75290
S2C_FINISHED = 0x5541   # 0x140d7ca70: u16 n, n * (obool, coded id), u32
C2S_ACCEPT = 0x5542     # mode byte keyed with the id, coded id (builder 0x140f00d70)
S2C_ACCEPT = 0x5543     # 0x140e20d20: i16 result; 0 -> coded id -> QuestManager::QuestAccept 0x140d74840
C2S_COMPLETE = 0x5544   # coded id, u8 reward choice (0x1408ac770, after the hand-in scene)
S2C_COMPLETE = 0x5545   # 0x140e20950: i16 result; 0 -> obool (show the item rewards), coded id -> QuestComplete 0x140d74190
C2S_ABANDON = 0x5546    # coded id (0x140f014b0)
S2C_ABANDON = 0x5547    # 0x140e207e0: i16 result, coded id -> dropped from the active list
C2S_PROGRESS = 0x554b   # u16 count, coded id, u8 condition (0x140f01830; the accept reply sends it for JustCompleted)
S2C_PROGRESS = 0x554c   # 0x140d7b7c0: u8 state, 5 * i16 count, i16, coded id
C2S_TRACK = 0x554d      # coded id, obool keyed with the id (0x140f01bd0): HUD tracking on/off, no reply
C2S_TUTORIAL_SKIP = 0x5550  # coded id (0x140f02320): the tutorial skip 0x140833160 sends one per tutorialquest row the
                        # player does not hold; no reply handler (planning/client/town_quest_npc.md 0x5550)
C2S_FORCE_COMPLETE = 0x5551  # coded id (0x140f09c90): RTS.SetQuestForceComplete(id) of a shipped cutscene script
                        # (ScriptRTS::Register 0x140b62c60, thunk 0x140b6af00), not a developer command
S2C_FORCE_COMPLETE = 0x5552  # 0x140d7cd80: u16 n, n * 4 bytes into the quest manager's +0x40 list; `00 00` is safe
C2S_AREA = 0x5558       # coded u32 (GameStateCommon+0x130), plain u32 area (0x140f026a0): the hero entered a quest area
                        # in a battle map (watcher 0x140d7f1d0, BattleField state only); resent 3 times until answered
S2C_AREA = 0x5559       # 0x140d7d710: i16 result; 0 stops the resends
CONDITIONS = 5
RESULT_FAIL = 1         # any non-zero result shows a generic error text (0x140e20d20)
# Tutorial quests (Tutorial_Quest Yes, no Complete<n>_Type, a tutorialquest %TutorialQuest row) are run by the client
# (TutorialQuestManager common+0x58, one object per TutorialQuestType, events through 0x140833140), which reports the
# finished step with C2S 0x554f (troops.tutorial_count -> counts[0]) and then hands the quest in. The types whose
# trigger our flow reaches wait for that counter, as in the original (ROADMAP Q11; the record's "tutorial" flag, set
# on accept by tutorial_waits):
#   ItemEquip 9900118        the equip reply 0x164f raises event 0x4b with the item worn (0x140e50b5c); the step is done
#                            on the class's TutorialLink item (0x140830560); HELENA's is -1, so hers never is
#   VehicleGuide 9900123     mount item used (0x4043: event 0x4a), mount chosen (0x10f5: 0x48), ride cast ended
#                            (0x140657f50 sends 0x125e and raises 0x49) (0x140830810)
#   CheckActivation 9900103  the contract used, then a troop in the main deck (event 0x10) (0x14082d530)
#   TrainTroop 9900104       the Grey Wood Bowmen contract used, then TroopTrainingStart on that troop (event 0x18
#                            with its uid, 0x14082daa0; serials.troop_uid)
#   LearnSkill 9900125       the skill window's lesson pages closed (SkillDescOK 2: event 5, 0x14082cff0)
#   TeleportCrystal1 1150312 the crystal used from the map, CompleteID 4000 (Mist Field 10350) / 5001 (10351):
#   TeleportCrystal2 1160214 0x406a (Process_ResUsePortal 0x14089d0f0, world.warp_use) raises event 0x59 with the
#                            portal 0x4072 left pending (+0x118); counted when it is CompleteID (0x140832250). In a
#                            field room too: the tactical map's UsePortal (BattleFieldSubWarSituationMap 0x140576f10)
#                            asks box 0xcfa5 owned by CommonSubWorldMap 0x55, whose answer (vt+0x58 0x140891440)
#                            sends 0x4071 as in town, and all four handlers have a battle-state branch (corrected
#                            2026-10-24, build/crystal; live 2026-09-28 03:08:52 0x4071 / 0x4069, 03:08:58 0x554f
#                            1160214). 0x5640 with a %Portal id (world.crystal_warp) is the client's test-script
#                            ReqWarp only.
# The types of quests above level 10 are not checked against the client and are left done at accept.
TUTORIALS_COUNTED = ("ItemEquip", "VehicleGuide", "CheckActivation", "TrainTroop", "LearnSkill", "TeleportCrystal1",
                     "TeleportCrystal2")


def record(c):
    return c.setdefault("quests", {"active": {}, "done": []})


@functools.cache
def _titles():
    try:
        rows = tables.sections("text\\eng\\textquest_eng")["TextTable"]
    except KeyError:
        return {}
    return {r["TextID"][:-len("/Title")]: r["Text"] for r in rows if r["TextID"].endswith("/Title")}


def title(qid):
    """A quest's English title (textquest_eng <id>/Title), '' without one: the journal's quest lines name it."""
    return _titles().get(str(qid), "")


def _conds(qid, q):
    """[[type, id1, count, need]] of quest qid's conditions in its record q (the journal's quest and char lines; a
    record without its counts reads 0, as the char line is built at the character's login)."""
    quest, counts = tables.by_id("questtable").get(str(qid)) or {}, q.get("counts") or ()
    return [[kind, id1, counts[i] if i < len(counts) else 0, need]
            for i, (kind, id1, need) in enumerate(conditions(quest)) if kind]


def journal_quest(ev, qid, q=None, **more):
    """The journal's line for quest qid (ev accept / progress / done / hand-in / abandon / restart / skip): its title
    and, with its record q, each condition's count against its need."""
    journal("quest", ev=ev, id=int(qid), title=title(qid), conds=_conds(qid, q) if q else None, **more)


def held(c):
    """[[id, title, conds]] of the quests character c holds (the journal's char line: live.py now lists them)."""
    return [[int(qid), title(qid), _conds(qid, q)] for qid, q in record(c)["active"].items() if str(qid).isdigit()]


def reward_items(quest, cls):
    """[(item code, count)] a completed quest gives: questtable Item1..Item5 of type Normal (the item code) or
    NormalCategory (item_quest_reward_category, the column of the hero's class; the client resolves it the same way
    for its message, 0x1419390c0). A code with no item table row is logged and left out."""
    return _items(quest, cls, [(f"Item{n}_Type", f"Item{n}_ID", f"Item{n}_Value") for n in range(1, 6)])


def accept_items(quest, cls, flag=None):
    """[(item code, count)] handed over on accept (Accept_Reward_Type<n> Item / ItemCategory), optionally only those
    whose `flag` column is Yes. The columns are server-only (the client never reads them); by their names
    Accept_Reward_Collect<n> takes the item back on abandon and Accept_Reward_Finsh_Collect<n> on completion."""
    cols = [(f"Accept_Reward_Type{n}", f"Accept_Reward_ID{n}", f"Accept_Reward_Value{n}") for n in (1, 2)
            if flag is None or quest.get(f"{flag}{n}") == "Yes"]
    return _items(quest, cls, cols, {"Item": "Normal", "ItemCategory": "NormalCategory"})


def _items(quest, cls, cols, kinds=None):
    out = []
    for type_col, id_col, value_col in cols:
        kind, rid, value = quest.get(type_col), quest.get(id_col, ""), quest.get(value_col, "")
        kind = (kinds or {}).get(kind, kind)
        if kind == "Normal":
            code = rid
        elif kind == "NormalCategory":
            cat = tables.by_id("item_quest_reward_category").get(rid, {})
            code = cat.get(f"{hero.HERO_CODE[cls]}_ItemCode", "")
        else:
            continue
        if not code.isdigit() or items.row(code) is None:
            log.warning("quest %s reward %s %s: no item table row for %r, not given", quest["ID"], kind, rid, code)
            continue
        out.append((int(code), int(value) if value.isdigit() else 1))
    return out


def kill_names(np_troop_id):
    """The NP name ids a troop counts as for NPNameKill (npname %NPTroopName_String: name and group name)."""
    rows = tables.sections("npname")["NPTroopName_String"]
    return {v for r in rows if r["NPTroop_ID"] == str(np_troop_id) for v in (r["NPTroop_Name"], r["NPTroop_GroupName"])}


def count(s, state, kind, column, values, by=1, spot=None):
    """`by` more on every active quest condition of kind whose Complete<n>_<column> is in values (up to its
    Complete<n>_Value1); the moved quests' progress is sent. Returns the moved quest ids. With `spot`, only conditions
    whose IngSpot<n> is that spot (or unset) move: MissionLevelClear names its mission there (ID1 is the difficulty)."""
    from . import daily
    daily.on_event(s, state, kind, values, by, spot)                    # the same triggers move daily tasks
    moved = []
    c = s.data.get("char") or s.data["account"]["characters"][0]      # the session's hero (the game login sets it)
    for qid, q in record(c)["active"].items():
        quest = tables.by_id("questtable").get(qid)
        weapon = (quest or {}).get("EquipItem", "")
        if weapon.isdigit() and int(weapon) not in {e["code"] for e in hero.equipment(c)}:
            continue            # "Equip %1% and ..." (textui 20071): the client prints the gate, the server kept it
        for n in range(1, CONDITIONS + 1):
            if quest and quest.get(f"Complete{n}_Type") == kind and quest.get(f"Complete{n}_{column}") in values \
                    and (spot is None or quest.get(f"IngSpot{n}", "") in ("", "-", str(spot))):
                v = quest.get(f"Complete{n}_Value1") or ""
                need = int(v) if v.isdigit() else 1                    # "-" (Realm, TroopUpgrade): once
                if q["counts"][n - 1] < need:
                    q["counts"][n - 1] = min(need, q["counts"][n - 1] + by)
                    moved.append((int(qid), q))
    if moved:
        state.save()
        for qid, q in moved:
            send_progress(s, qid, q)
    return [qid for qid, _ in moved]


DIFFICULTIES = ("Normal", "Hard", "Hell")      # E_MissionDifficult names in enum order (strings at 0x14291d5b8)


def mission_clear_matches(id1, difficulty):
    """Whether a MissionLevelClear Complete<n>_ID1 (ANY / NORMAL / HARD / HELL, any case) takes a clear at difficulty
    0..2 (what on_mission_clear counts; tools/recon/chainwalk.py asks it too)."""
    need = (id1 or "").upper()
    return need == "ANY" or (0 <= difficulty < len(DIFFICULTIES) and need == DIFFICULTIES[difficulty].upper())


def on_mission_clear(s, state, spot, difficulty=0):
    """A mission won at spot on difficulty (0 Normal, 1 Hard, 2 Hell): the MissionLevelClear conditions whose IngSpot<n>
    is that spot and whose ID1 is ANY or that difficulty (questtable ID1 ANY / NORMAL / HARD / HELL in any case; every
    MissionLevelClear IngSpot is a Battle, Raid or PVP_POINT spot), and the AnyMissionClear daily tasks (ID1 NORMAL /
    HARD). Quests of other missions held at the same time do not move (1110501 and 1010202 are open together)."""
    name = DIFFICULTIES[difficulty] if 0 <= difficulty < len(DIFFICULTIES) else DIFFICULTIES[0]
    values = {v for n in ("Any", name) for v in (n, n.upper(), n.lower())}
    moved = count(s, state, "MissionLevelClear", "ID1", values, spot=spot)
    from . import daily
    daily.on_event(s, state, "AnyMissionClear", values)
    log.info("mission %d cleared on %s: quests %s", spot, name, moved or "none")
    return moved


def kill_groups(np_troop_id):
    """The NP group name ids of a troop (npname NPTroop_GroupName), what NPGroupKill counts (e.g. 1000102: the
    Mist Tribe kobold mage 154050 and soldier 154150 for 1150204, the walkthrough's goblins)."""
    rows = tables.sections("npname")["NPTroopName_String"]
    return {r["NPTroop_GroupName"] for r in rows if r["NPTroop_ID"] == str(np_troop_id)}


def leader_names(leader_id):
    """The NP name ids of an NP leader (npname %NPLeaderName_String by NPLEADER_ID; a zone troop's NPLeaderID, -100 =
    none): what NPNameKill counts when the troop it leads falls (1011103 "DarkElf_Leader_KW" 2509 = leader 120030)."""
    rows = tables.sections("npname")["NPLeaderName_String"]
    return {r["NPTroop_Name"] for r in rows if r["NPLEADER_ID"] == str(leader_id)} if leader_id not in (None, -100)         else set()


def on_kill(s, state, np_troop_id, leader=None):
    """A killed NP troop moves every active quest's NPNameKill condition naming it (Complete<n>_ID2 = NP name id; one
    quest, 2239805, names a group there) or its leader (the zone troop's NPLeaderID; the leader falls with its troop,
    inferred) and NPGroupKill condition on its group (Complete<n>_ID2 = group name id)."""
    from . import titles
    titles.achieve(s, state, "NPNameKill", add=1, cond={3: np_troop_id})
    moved = count(s, state, "NPNameKill", "ID2", kill_names(np_troop_id) | leader_names(leader))
    moved += count(s, state, "NPGroupKill", "ID2", kill_groups(np_troop_id))
    if moved:
        log.info("kill of troop %d: quests %s", np_troop_id, moved)


def on_item(s, state, code, n):
    """n of item code went into the bag: every active ItemGain condition on it (Complete<n>_ID1 = item code) moves."""
    moved = count(s, state, "ItemGain", "ID1", {str(code)}, n)
    if moved:
        log.info("item %d x%d gained: quests %s", code, n, moved)


def drop_items(s, state, np_troop_id, roll=random.randrange):
    """Quest drops of a killed NP troop straight into the bag (world.add_item); rooms drop them on the ground."""
    from . import world
    for item, n in roll_drops(s, np_troop_id, roll):
        world.add_item(s, state, item, n)


def roll_drops(s, np_troop_id, roll=random.randrange, leader=None):
    """[(item, count)] a killed NP troop drops for the held quests (item_drop_quest %Troop: Quest<k>, _Item, _Rate of
    100000, _Min, _Max; and %Leader by the zone troop's NPLeaderID, Quest1..10, no _Min/_Max past 5 = 1), each only
    while the quest's ItemGain condition on the item is not met yet."""
    got = []
    r = record(s.data.get("char") or s.data["account"]["characters"][0])
    rows = [(row, 5) for row in tables.sections("item_drop_quest")["Troop"] if row["NPTroopID"] == str(np_troop_id)]
    if leader not in (None, -100):
        rows += [(row, 10) for row in tables.sections("item_drop_quest")["Leader"] if row["NPLeaderID"] == str(leader)]
    for row, slots in rows:
        for k in range(1, slots + 1):
            qid, item = row.get(f"Quest{k}", "-"), row.get(f"Quest{k}_Item", "-")
            if qid not in r["active"] or not item.isdigit() or not item_needed(qid, r["active"][qid], item):
                continue
            if roll(100000) < int(row[f"Quest{k}_Rate"]):
                lo, hi = int(row.get(f"Quest{k}_Min", 1)), int(row.get(f"Quest{k}_Max", 1))
                got.append((int(item), lo + roll(hi - lo + 1) if hi > lo else lo))
    return got


def item_needed(qid, q, item):
    """Whether quest qid still has an ItemGain condition on item below its count."""
    quest = tables.by_id("questtable").get(qid) or {}
    return any(kind == "ItemGain" and id1 == item and q["counts"][i] < need
               for i, (kind, id1, need) in enumerate(conditions(quest)))


def on_prop(s, state, prop_type):
    """An activated smart prop moves every active quest's PropActivate condition on its type (Complete<n>_ID1 = the
    smartproptable id, e.g. 402 Spider Cocoon for 1150201)."""
    moved = count(s, state, "PropActivate", "ID1", {str(prop_type)})
    log.info("prop of type %d activated: quests %s", prop_type, moved or "none")
    return moved


def name_troops(name):
    """The NP troop ids whose npname %NPTroopName_String name is `name` (the reverse of kill_names, names only)."""
    return sorted(r["NPTroop_ID"] for r in tables.sections("npname")["NPTroopName_String"] if r["NPTroop_Name"] == str(name))


def on_level(s, state, send=True):
    """The hero's level moves every active HeroLevel condition (Complete<n>_Value1 = the level to reach, e.g. 2020111
    "Call from Raymond" 25): its count is 1 once the level reaches it, else 0 (the 0x554c handler 0x140d7b7c0 counts
    type 0x14 met only at count 1; planning/client/town_quest_npc.md Gap 2), which also rewrites a level stored as the
    count by older saves. The client reports only JustCompleted itself (the one caller of the 0x554b builder
    0x140f01830 is the accept reply 0x140e20ea2), so the server keeps these; called on accept, on a level-up and before
    the lists at town entry (send=False: the lists carry the counts)."""
    c = s.data.get("char") or s.data["account"]["characters"][0]
    level, moved = c.get("level", 1), []
    for qid, q in record(c)["active"].items():
        quest = tables.by_id("questtable").get(qid) or {}
        for i, (kind, _, _) in enumerate(conditions(quest)):
            goal = quest.get(f"Complete{i + 1}_Value1", "")
            met = int(level >= (int(goal) if goal.isdigit() else 1))
            if kind == "HeroLevel" and q["counts"][i] != met:
                q["counts"][i] = met
                moved.append((int(qid), q))
    if moved:
        state.save()
        log.info("hero level %d: quests %s", level, [qid for qid, _ in moved])
    for qid, q in moved if send else ():
        send_progress(s, qid, q)


def conditions(quest):
    """[(type name, id1, required count)] for Complete1..5; empty slots have type ''. HeroLevel needs 1: its Value1 is
    the level to reach, the count a met flag (on_level; 0x140d7b7c0)."""
    out = []
    for n in range(1, CONDITIONS + 1):
        kind = quest.get(f"Complete{n}_Type", "")
        value = quest.get(f"Complete{n}_Value1", "-")
        need = 1 if kind == "HeroLevel" or not value.lstrip("-").isdigit() else int(value)
        out.append((kind, quest.get(f"Complete{n}_ID1", "-"), need))
    return out


def done(quest, q):
    if q.get("tutorial"):                       # the client's tutorial counter (tutorial_waits)
        return q["counts"][0] >= 1
    return all(not kind or q["counts"][i] >= need for i, (kind, _, need) in enumerate(conditions(quest)))


def tutorial_waits(quest, cls):
    """Whether accepted quest `quest` waits for the client's tutorial counter 0x554f (TUTORIALS_COUNTED) for a hero of
    class cls: a tutorial quest with no condition whose tutorialquest type is counted; for ItemEquip, only when the
    class's TutorialLink item (Hero_<cls> of the row's CompleteID) exists."""
    if quest.get("Tutorial_Quest") != "Yes" or any(kind for kind, _, _ in conditions(quest)):
        return False
    rows = tables.sections("tutorialquest")
    row = next((r for r in rows["TutorialQuest"] if r["QuestId"] == quest["ID"]), None)
    if row is None or row["TutorialQuestType"] not in TUTORIALS_COUNTED:
        return False
    if row["TutorialQuestType"] == "ItemEquip":
        link = next((r for r in rows["TutorialLink"] if r["CompleteID"] == row["CompleteID"]), {})
        return link.get(f"Hero_{cls}", "-1") not in ("", "-1")
    return True


def emerged(kind, value, r):
    """A smart prop's emergence condition (smartproptable Energence_Conditions / _Value) for the quest record r.
    Get_Quest: the quest is held; FinishOrDoingQuest: held (doing or finished); FinishOrCompletedQuest: finished or
    handed in; NotFinished_Quest: neither. Item conditions (Carry_Item, Use_Item) are not mapped: False."""
    q = r["active"].get(str(value))
    quest = tables.by_id("questtable").get(str(value))
    finished = q is not None and quest is not None and done(quest, q)
    handed_in = str(value).isdigit() and int(value) in r["done"]
    if kind == "Get_Quest" or kind == "FinishOrDoingQuest":
        return q is not None
    if kind == "FinishOrCompletedQuest":
        return finished or handed_in
    if kind == "NotFinished_Quest":
        return not (finished or handed_in)
    return False


def field_props(s, qid):
    """In a field's battle room, the props that appear or go with quest qid (game.send_quest_props)."""
    from . import game
    spot = s.data.get("battle_spot")
    if spot and game.is_field(spot):            # a mission battle's props are not quest-driven (and not decoded here)
        game.send_quest_props(s, spot, s.data["char"], qid)


def spawn_troop(s, state, qid):
    """An accept spawn (QuestAccept_SpawnNPTroop_ID) goes into the player's live field room (game.spawn_quest_troop):
    the accept arrives on the world connection, the room is the game one."""
    from . import game
    acct = s.data.get("account")
    g = acct and getattr(state, "game_sessions", {}).get(acct.get("id"))
    if g is not None and not g.w.is_closing():
        game.spawn_quest_troop(g, qid)


def spot_warp(s, state, qid, when="Accept"):
    """Quest<when>_Action on accept or hand-in: SpotWarp <warpinfo id> or CurrentWarp <spot id> (the spot's default
    start). The client stores an accept warp before it sends 0x5542 (0x140d7a6d0) and plays its EnterScript when the
    server moves the hero (0x5641). A Field with a zone file is entered as its battle room at the warp's start-point
    group (world.send_field_entry; from inside a room through MissionEscape); a warp inside the town-state map the
    hero is on is a type-5 teleport to the measured start point. Mission warps (WARP_POSITION MISSION, Battle spots)
    wait for the mission battles (O5b) and are logged."""
    from . import game, world, zone
    quest = tables.by_id("questtable")[str(qid)]
    kind, value = quest.get(f"Quest{when}_Action"), quest.get(f"Quest{when}_Action_Value", "")
    if kind == "SpotWarp":
        warp = tables.by_id("warpinfo").get(value)
        spot, group = (int(warp["SpotID"]), int(warp["SPGroupID"])) if warp else (None, 0)
        field = bool(warp) and warp["WARP_POSITION"] == "FIELD"
    elif kind == "CurrentWarp" and value.isdigit():
        spot, group, field = int(value), 0, True
    else:
        return
    c = s.data["char"]
    if kind == "SpotWarp" and warp and warp["WARP_POSITION"] == "MISSION" and game.is_mission(spot):
        world.send_mission_entry(s, state, spot, qid)       # the quest's mission battle (e.g. 1150301 -> 10358)
        return
    if not (field and spot and game.is_field(spot) and zone.available(spot)):
        if field and spot == c.get("spot") and world.start_point(spot, group) is not None:
            c["pos"] = list(world.start_point(spot, group))       # a field the town state runs (no zone file)
            state.save()
            world.send_teleport(s, spot, c["pos"])
            return
        log.warning("quest %d %s %s not done: spot %s, group %s (mission warps wait for O5b)", qid, kind, value,
                    spot, group)
        return
    c["spot"] = spot
    c["field_group"] = [spot, group]
    state.save()
    log.info("quest %d %s %s: to field %d, start group %d", qid, kind, value, spot, group)
    world.send_field_entry(s, spot, group, leave_battle=bool(s.data.get("battle_spot")))


def write_active(w, qid, q):
    """26-byte entry: coded id, obool tracked, u64 accept time, u8 state (1 = ready to hand in), i16, 5 * i16 count."""
    state = 1 if done(tables.by_id("questtable")[str(qid)], q) else 0
    w.raw(obf.u32(qid)).obool(q.get("tracked", True)).u64(q.get("time", 0)).u8(state).raw(bytes(2))
    w.raw(struct.pack("<5h", *q["counts"]))


REPEAT_TYPES = ("Day", "Week", "Normal")      # questtable Retry_Type values in use that reopen a handed-in quest


def reopen(r, today=None, now=None):
    """Repeatable quests (Retry_Type Day 61, Week 6, Normal 1 in use) leave the finished list once their reset has
    passed, so the client offers them again: Day at the next game day (07:00 UTC, rules.game_day: the dailies' reset,
    census C6 / L6), Week in the next ISO week of game days (the weekly hour is not pinned: [I]), Normal at once.
    Returns the reopened ids."""
    import datetime
    from . import rules
    today = today or datetime.date.fromisoformat(rules.game_day(now))
    handed = r.get("handed", {})
    out = []
    for qid in list(r["done"]):
        kind = (tables.by_id("questtable").get(str(qid)) or {}).get("Retry_Type")
        if kind not in REPEAT_TYPES:
            continue
        when = handed.get(str(qid))
        day = datetime.date.fromisoformat(when) if when else None
        due = kind == "Normal" or day is None or (day < today if kind == "Day" else
                                                  day.isocalendar()[:2] != today.isocalendar()[:2])
        if due:
            r["done"].remove(qid)
            out.append(qid)
    return out


def send_lists(s):
    """Active and finished lists; the client clears and rebuilds its own lists from them."""
    r = record(s.data["char"])
    reopen(r)
    w = Writer(S2C_ACTIVE).u16(len(r["active"]))
    for qid, q in r["active"].items():
        write_active(w, int(qid), q)
    s.send(w)
    send_finished(s)


def send_finished(s):
    r = record(s.data["char"])
    w = Writer(S2C_FINISHED).u16(len(r["done"]))
    for qid in r["done"]:
        w.obool(False).raw(obf.u32(qid))
    s.send(w.u32(0))


def send_progress(s, qid, q):
    state = 1 if done(tables.by_id("questtable")[str(qid)], q) else 0
    s.send(Writer(S2C_PROGRESS).u8(state).raw(struct.pack("<5h", *q["counts"])).raw(bytes(2)).raw(obf.u32(qid)))
    journal_quest("done" if state else "progress", qid, q)


# Request body sizes; a shorter body is logged and dropped (a handler exception would end the session).
SIZE = {C2S_ACCEPT: 5, C2S_PROGRESS: 7, C2S_COMPLETE: 5, C2S_ABANDON: 4, C2S_TRACK: 5, C2S_AREA: 8,
        C2S_TUTORIAL_SKIP: 4, C2S_FORCE_COMPLETE: 4}


def body(pkt):
    b = pkt.rest()
    if len(b) < SIZE[pkt.proto]:
        log.warning("quest request 0x%04x too short: %s", pkt.proto, b.hex())
        return None
    return b


def make(role, state):
    @role.on(C2S_ACCEPT)
    def accept(s, pkt):
        b = body(pkt)
        if b is None:
            return
        mode, qid = (T1[b[0]] - 4 * b[1]) & 0xff, obf.dec_u32(b[1:5])
        r = record(s.data["char"])
        quest = tables.by_id("questtable").get(str(qid))
        reopen(r)
        if quest is not None and str(qid) in r["active"] and mode == 1:
            # a timed quest's FailOk (RemainTime ran out): the client re-sends the accept, which restarts it
            del r["active"][str(qid)]
            log.info("quest %d restarted (timed)", qid)
            journal_quest("restart", qid)
        if quest is None or str(qid) in r["active"] or qid in r["done"]:
            log.warning("quest %d accept refused (known %s, active %s, done %s)", qid, quest is not None,
                        str(qid) in r["active"], qid in r["done"])
            s.send(Writer(S2C_ACCEPT).u16(RESULT_FAIL))
            return
        r["active"][str(qid)] = {"counts": [0] * CONDITIONS, "time": int(time.time()), "tracked": True}
        if tutorial_waits(quest, s.data["char"]["class"]):
            r["active"][str(qid)]["tutorial"] = True
        state.save()
        log.info("quest %d accepted (mode %d): %s", qid, mode, [c for c in conditions(quest) if c[0]])
        journal_quest("accept", qid, r["active"][str(qid)])
        s.send(Writer(S2C_ACCEPT).u16(0).raw(obf.u32(qid)))
        on_level(s, state, qid)                                 # a HeroLevel condition the hero already meets
        from . import world
        for code, count in accept_items(quest, s.data["char"]["class"]):
            world.add_item(s, state, code, count)
        on_level(s, state)
        field_props(s, qid)
        spawn_troop(s, state, qid)
        spot_warp(s, state, qid)

    @role.on(C2S_PROGRESS)
    def progress(s, pkt):
        b = body(pkt)
        if b is None:
            return
        count, qid, cond = struct.unpack_from("<H", b)[0], obf.dec_u32(b[2:6]), b[6]
        q = record(s.data["char"])["active"].get(str(qid))
        if q is None or cond >= CONDITIONS:
            log.warning("quest %d progress on condition %d: not active", qid, cond)
            return
        kind, _, need = conditions(tables.by_id("questtable")[str(qid)])[cond]
        q["counts"][cond] = min(max(q["counts"][cond], count), need)
        state.save()
        log.info("quest %d condition %d (%s) at %d/%d", qid, cond, kind, q["counts"][cond], need)
        send_progress(s, qid, q)

    @role.on(C2S_COMPLETE)
    def complete(s, pkt):
        b = body(pkt)
        if b is None:
            return
        qid, reward = obf.dec_u32(b[:4]), b[4]
        if not hand_in(s, state, qid, reward):
            s.send(Writer(S2C_COMPLETE).u16(RESULT_FAIL))

    @role.on(C2S_ABANDON)
    def abandon(s, pkt):
        b = body(pkt)
        if b is None:
            return
        qid = obf.dec_u32(b[:4])
        was = record(s.data["char"])["active"].pop(str(qid), None)
        state.save()
        quest = tables.by_id("questtable").get(str(qid))
        if was is not None and quest is not None:
            from . import world
            for code, count in accept_items(quest, s.data["char"]["class"], "Accept_Reward_Collect"):
                world.take_back(s, state, code, count)
        log.info("quest %d abandoned", qid)
        journal_quest("abandon", qid)
        s.send(Writer(S2C_ABANDON).u16(0).raw(obf.u32(qid)))
        field_props(s, qid)

    @role.on(C2S_AREA)
    def area(s, pkt):
        """A QuestBound condition is met by entering the area whose id is its Complete<n>_ID1 (0x140d7f4f0 compares
        them before sending)."""
        b = body(pkt)
        if b is None:
            return
        who, area_id = obf.dec_u32(b[:4]), struct.unpack_from("<I", b, 4)[0]
        s.send(Writer(S2C_AREA).u16(0))
        met = []
        for qid, q in record(s.data["char"])["active"].items():
            for i, (kind, id1, need) in enumerate(conditions(tables.by_id("questtable")[qid])):
                if kind == "QuestBound" and id1 == str(area_id) and q["counts"][i] < need:
                    q["counts"][i] = need
                    met.append((int(qid), q))
        log.info("quest area %d entered (%d): %s", area_id, who, [qid for qid, _ in met] or "no QuestBound condition")
        if met:
            state.save()
        for qid, q in met:
            send_progress(s, qid, q)

    @role.on(C2S_TRACK)
    def track(s, pkt):
        b = body(pkt)
        if b is None:
            return
        qid, on = obf.dec_u32(b[:4]), (T1[b[4]] - 2 * b[0]) & 0xff
        q = record(s.data["char"])["active"].get(str(qid))
        if q is not None:
            q["tracked"] = bool(on)
            state.save()

    @role.on(C2S_TUTORIAL_SKIP)
    def tutorial_skip(s, pkt):
        """A skipped tutorial ("TutorialComplete" too) is finished without rewards and the finished list resent, so
        the client stops offering it (planning/client/town_quest_npc.md Gap 3; the meaning is read from the sender
        0x140833160, which also abandons the current tutorial by 0x5546 first). Only questtable rows with
        Tutorial_Quest Yes: some tutorialquest rows are not quests (9900101), and 0x5541 asserts on an unknown id."""
        b = body(pkt)
        if b is None:
            return
        qid = obf.dec_u32(b[:4])
        r = record(s.data["char"])
        quest = tables.by_id("questtable").get(str(qid))
        if quest is None or quest.get("Tutorial_Quest") != "Yes" or str(qid) in r["active"] or qid in r["done"]:
            log.info("tutorial skip of %d: not a tutorial quest, held or finished; ignored", qid)
            return
        r["done"].append(qid)
        state.save()
        log.info("tutorial %d skipped: finished", qid)
        journal_quest("skip", qid)
        send_finished(s)

    @role.on(C2S_FORCE_COMPLETE)
    def force_complete(s, pkt):
        """A cutscene script's RTS.SetQuestForceComplete(id) at its end (2_HexterOpening: 1002; the Accolade hero
        scene: 1001): the marker quest of a questtable %SpotEvent row is finished. While the row's NextQuest is not
        in the client's finished map, the world map sends the player into the row's opening room at every entry of
        its spot (0x1406f8d70: Sunstruck 20100 -> room 880416 while quest 1010232 is ready), so the finished list
        is resent. Only a marker quest: Use_Quest No and Complete1_Type JustCompleted (1001, 1002); the scripts
        also name 1003, a real main quest, and 1006, which is in no table: ignored (the original's rule is in no
        table; the silent builder's report, 2026-11-05). The reply is an empty list (0x5552: u16 n)."""
        b = body(pkt)
        if b is None:
            return
        qid = obf.dec_u32(b[:4])
        s.send(Writer(S2C_FORCE_COMPLETE).u16(0))
        r = record(s.data["char"])
        quest = tables.by_id("questtable").get(str(qid))
        if (quest is None or quest.get("Use_Quest") != "No" or quest.get("Complete1_Type") != "JustCompleted"
                or str(qid) in r["active"] or qid in r["done"]):
            log.info("force complete of %d: not a marker quest, held or finished; ignored", qid)
            return
        r["done"].append(qid)
        state.save()
        log.info("marker quest %d finished by its cutscene", qid)
        journal_quest("force", qid)
        send_finished(s)


# questtable Collect_Reward_Finish (server-only: no reader in the client, the dump has no such string): what the hand-in
# takes of each ItemGain condition's item. The tape shows collected quest items leave the bag at the hand-in (part 8
# RVJnrq3zPlo f_00459: the Quest tab reads "1 / 64" at Lv 15 after seven "All" ItemGain hand-ins, and quest items
# cannot be destroyed by the player; the removal prints nothing, part 1 tiouWoPSPks f_00645). All (764 in use: all 249
# of its items are QUEST_ITEM) = every held unit; Complete (9) and PARTIAL (11) = the condition's count (their quests
# exchange tokens, materials and event eggs the player may hold more of: inferred, the tape never shows the difference);
# NONE (7) and '' = nothing. Rules census C5.
COLLECT = {"All": "all", "Complete": "count", "PARTIAL": "count", "NONE": None, "": None}
LEFTOVERS_MIGRATION = "quest_items_collected"   # c["migrations"]: collect_leftovers ran for this character


def collected(quest, held):
    """[(item code, count)] the hand-in of `quest` takes by its Collect_Reward_Finish, given {code: count held}."""
    how = COLLECT.get(quest.get("Collect_Reward_Finish", ""))
    need = {}
    for kind, id1, n in conditions(quest):
        if kind == "ItemGain" and id1.isdigit():
            need[int(id1)] = need.get(int(id1), 0) + n
    out = []
    for code, n in need.items():
        take = held.get(code, 0) if how == "all" else min(n, held.get(code, 0)) if how == "count" else 0
        if take:
            out.append((code, take))
    return out


def held_counts(c):
    held = {}
    for it in c.get("bag", []):
        held[it["code"]] = held.get(it["code"], 0) + it["count"]
    return held


def collect_leftovers(c):
    """A save migration (owner decision E9 (a)): the collected items of quests handed in before the hand-in took them
    (Collect_Reward_Finish All: e.g. Aldric's Kobold Fire Powder of 1150203), out of the bag once per character, except
    an item an active quest still collects. Journaled; returns [(code, count)] taken (nothing on a second run)."""
    migrations = c.setdefault("migrations", [])
    if LEFTOVERS_MIGRATION in migrations:
        return []
    r = record(c)
    active = {int(id1) for qid in r["active"] for kind, id1, _ in
              conditions(tables.by_id("questtable").get(str(qid)) or {}) if kind == "ItemGain" and id1.isdigit()}
    taken = {}
    for qid in r["done"]:
        quest = tables.by_id("questtable").get(str(qid)) or {}
        if quest.get("Collect_Reward_Finish") != "All":
            continue
        for code, n in collected(quest, held_counts(c)):
            if code in active or code in taken:
                continue
            taken[code] = n
            for it in [it for it in c["bag"] if it["code"] == code]:
                c["bag"].remove(it)
            journal("item", ev="spend", code=code, name=items.name(code), n=n,
                    why=f"migration: quest {qid} was handed in before its collected items were taken")
    migrations.append(LEFTOVERS_MIGRATION)
    if taken:
        log.info("char %s: finished quests' items taken %s", c.get("id"), taken)
    return list(taken.items())


def hand_in(s, state, qid, reward=255):
    """Hand active quest qid in (C2S 0x5544 after the NPC's scene, or the owner's !questdone): its rewards, gold, exp,
    lent items taken back, finish warp; False when it is not active or not done."""
    r = record(s.data["char"])
    q = r["active"].get(str(qid))
    quest = tables.by_id("questtable").get(str(qid))
    if q is None or quest is None or not done(quest, q):
        log.warning("quest %d complete refused (active %s)", qid, q is not None)
        return False
    del r["active"][str(qid)]
    if quest.get("Retry_Type") in REPEAT_TYPES:      # a repeatable quest reopens after its reset (reopen)
        from . import rules
        r.setdefault("handed", {})[str(qid)] = rules.game_day()
    r["done"].append(qid)
    state.save()
    from . import world
    rewards = reward_items(quest, s.data["char"]["class"])
    log.info("quest %d completed (reward choice %d; gold %s, exp %s, items %s)", qid, reward, quest["Gold"],
             quest["Exp"], rewards)
    gold = int(quest["Gold"]) if quest.get("Gold", "").isdigit() else 0
    exp = int(quest["Exp"]) if quest.get("Exp", "").isdigit() else 0
    journal_quest("hand-in", qid, gold=gold, exp=exp, items=rewards)
    # the obool lets the client announce the reward items it reads from its own questtable
    s.send(Writer(S2C_COMPLETE).u16(0).obool(bool(rewards)).raw(obf.u32(qid)))
    for code, count in accept_items(quest, s.data["char"]["class"], "Accept_Reward_Finsh_Collect"):
        world.take_back(s, state, code, count)             # a lent weapon may be worn (EquipItem)
    for code, count in collected(quest, held_counts(s.data["char"])):
        world.remove_item(s, state, code, count, why=f"quest {qid} collected ({quest['Collect_Reward_Finish']})")
    for code, count in rewards:
        world.add_item(s, state, code, count, why=f"quest {qid}")
    if gold:
        world.add_gold(s, state, gold, why=f"quest {qid}")
    if exp:
        world.add_exp(s, state, exp, why=f"quest {qid}")
    from . import guild
    guild.on_quest(s, state, quest)                 # the quest's Guild_Exp / Guild_Point / Guild_Contribution
    field_props(s, qid)
    spot_warp(s, state, qid, "Finish")
    from . import titles
    titles.achieve(s, state, "ClearQuest", add=1)
    return True


def fill(s, state, qid):
    """The owner's !quest (2026-09-28: "another one to complete the quests ... to at least do some e2e"): every
    condition of active quest qid at its count and the progress pushed (0x554c), so it shows ready to hand in at its
    NPC; False when qid is not active."""
    q = record(s.data["char"])["active"].get(str(qid))
    quest = tables.by_id("questtable").get(str(qid))
    if q is None or quest is None:
        return False
    for i, (kind, _, need) in enumerate(conditions(quest)):
        if kind:
            q["counts"][i] = max(q["counts"][i], need)
    if q.get("tutorial"):
        q["counts"][0] = max(q["counts"][0], 1)
    state.save()
    send_progress(s, int(qid), q)
    log.info("quest %s filled by command", qid)
    return True

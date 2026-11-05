"""Daily tasks (DailyTaskManager = common[0x2c3]; the quest list's daily tab). Table dailytask: %TaskControl
(PlayerLevel, DailyTaskList = tasks a day, DailyTaskReward = rewards a day; the last row at or below the hero's level),
%DailyTask (DailyTask_ID, TaskLevelMin..Max, TaskProb, Complete_Type / _ID1 / _Value, Gold, Item1..4_ID / _Value).
The character keeps c["daily"] = {"date", "tasks": [{id, progress, state}], "rewarded"}; a new day rolls a new list.
Progress moves from the same triggers as quest conditions (quest.count calls on_event). Spec:
planning/requests/pushes_common.md 0x5600 / 0x5601 / 0x5606, field_npc_travel.md 0x5602 / 0x5604.

  S2C 0x5600 Process_List (0x14066bdd0) at start: u16 n, n * (u32 task id, i16 progress, u8 state: 0 open,
      1 done / reward waiting, 2 reward taken).   S2C 0x5601 (0x14066c0e0): u8 rewards taken today.
  S2C 0x5606 (0x14066c180), 7 bytes: one task's (u32 id, i16 progress, u8 state).
  C2S 0x5602 (0x140f0e680): u32 task id -> S2C 0x5603 (0x140e23bd0): i16; 0 -> u32 id (gold and item notices);
      0x5c18 = the day's rewards are used up.
  C2S 0x5604 (paid refresh, message 0x1c6f; the client checked item_currency DAILYTASK_REFRESH gold) -> S2C 0x5605:
      i16; the new list follows (0x5600, inferred)."""
import random

from . import tables
from .net import log
from .packet import Writer

S2C_LIST, S2C_REWARDED, S2C_PROGRESS = 0x5600, 0x5601, 0x5606
C2S_REWARD, S2C_REWARD = 0x5602, 0x5603
C2S_REFRESH, S2C_REFRESH = 0x5604, 0x5605
REWARDS_USED = 0x5c18
OPEN, DONE, TAKEN = 0, 1, 2


def num(v, d=0):
    return int(v) if str(v).lstrip("-").isdigit() else d


def control(level):
    rows = [r for r in tables.sections("dailytask")["TaskControl"] if num(r["PlayerLevel"]) <= level]
    return max(rows, key=lambda r: num(r["PlayerLevel"])) if rows else {}


def roll(level, rnd=random.Random()):
    count = num(control(level).get("DailyTaskList"))
    pool = [r for r in tables.sections("dailytask")["DailyTask"]
            if num(r["TaskLevelMin"]) <= level <= num(r["TaskLevelMax"]) and num(r["TaskProb"]) > 0]
    got = []
    while pool and len(got) < count:
        x = rnd.randrange(sum(num(r["TaskProb"]) for r in pool))
        for r in pool:
            x -= num(r["TaskProb"])
            if x < 0:
                got.append({"id": num(r["DailyTask_ID"]), "progress": 0, "state": OPEN})
                pool.remove(r)
                break
    return got


def record(c, now=None):
    """Today's list (the game day, 07:00 UTC: rules.game_day), rolled on the first read of a new day."""
    from . import rules
    today = rules.game_day(now)
    d = c.get("daily")
    if d is None or d.get("date") != today:
        d = c["daily"] = {"date": today, "tasks": roll(c.get("level", 1)), "rewarded": 0}
    top_up(c)
    return d


def top_up(c):
    """The day's list rolled at a lower level band gets the tasks the current band adds (TaskControl DailyTaskList;
    none below 17, so a character that levels past 17 had an empty list all day). Returns whether it grew."""
    d = c.get("daily")
    if d is None:
        return False
    want = num(control(c.get("level", 1)).get("DailyTaskList"))
    if len(d["tasks"]) >= want:
        return False
    have = {t["id"] for t in d["tasks"]}
    d["tasks"] += [t for t in roll(c.get("level", 1)) if t["id"] not in have][:want - len(d["tasks"])]
    return True


def row(task_id):
    return next((r for r in tables.sections("dailytask")["DailyTask"] if r["DailyTask_ID"] == str(task_id)), None)


def list_packets(c):
    d = record(c)
    w = Writer(S2C_LIST).u16(len(d["tasks"]))
    for t in d["tasks"]:
        w.u32(t["id"]).u16(t["progress"] & 0xFFFF).u8(t["state"])
    return [w, Writer(S2C_REWARDED).u8(d["rewarded"])]


def on_event(s, state, kind, values, by=1, spot=None):
    """A trigger of kind (a quest condition type) happened for one of values (at spot, when given: tasks with an
    IngSpot move only for that spot): the matching open tasks move."""
    c = s.data.get("char")
    if c is None or "daily" not in c:
        return
    for t in record(c)["tasks"]:
        r = row(t["id"])
        if not r or t["state"] != OPEN or r["Complete_Type"] != kind:
            continue
        if spot is not None and r.get("IngSpot", "-").isdigit() and r["IngSpot"] != str(spot):
            continue
        if r["Complete_ID1"] not in ("ANY", "-", "") and r["Complete_ID1"] not in values:
            continue
        need = max(1, num(r["Complete_Value"], 1))
        t["progress"] = min(need, t["progress"] + by)
        if t["progress"] >= need:
            t["state"] = DONE
        state.save()
        s.send(Writer(S2C_PROGRESS).u32(t["id"]).u16(t["progress"]).u8(t["state"]))


def make(role, state):
    from . import world

    @role.on(C2S_REWARD)
    def reward(s, pkt):
        task_id = pkt.u32()
        c = s.data["char"]
        d = record(c)
        t = next((x for x in d["tasks"] if x["id"] == task_id), None)
        r = row(task_id)
        if t is None or r is None or t["state"] != DONE:
            s.send(Writer(S2C_REWARD).u16(0x411))
            return
        if d["rewarded"] >= num(control(c.get("level", 1)).get("DailyTaskReward")):
            s.send(Writer(S2C_REWARD).u16(REWARDS_USED))
            return
        t["state"] = TAKEN
        d["rewarded"] += 1
        state.save()
        s.send(Writer(S2C_REWARD).u16(0).u32(task_id))
        if num(r["Gold"]):
            world.add_gold(s, state, num(r["Gold"]))
        for k in range(1, 5):
            if num(r[f"Item{k}_ID"]) > 0:
                world.add_item(s, state, num(r[f"Item{k}_ID"]), max(1, num(r[f"Item{k}_Value"], 1)))
        s.send(Writer(S2C_PROGRESS).u32(task_id).u16(t["progress"]).u8(TAKEN))
        s.send(Writer(S2C_REWARDED).u8(d["rewarded"]))
        log.info("daily task %d rewarded", task_id)

    @role.on(C2S_REFRESH)
    def refresh(s, pkt):
        c = s.data["char"]
        price = next((num(r["Gold_Count"]) for r in tables.sections("item_currency")["Base"]
                      if r["ItemCurrencyType"] == "DAILYTASK_REFRESH"), 0)
        if c.get("gold", 0) < price:
            s.send(Writer(S2C_REFRESH).u16(0x5c14))
            return
        d = record(c)
        d["tasks"] = roll(c.get("level", 1))
        if price:
            world.add_gold(s, state, -price)
        state.save()
        s.send(Writer(S2C_REFRESH).u16(0))
        for w in list_packets(c):
            s.send(w)

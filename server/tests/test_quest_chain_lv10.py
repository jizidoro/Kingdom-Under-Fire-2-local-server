"""AC2 of planning/todo/LEVEL10-PLAN.md: one new character walked through every in-use quest with AcquireLevel <= 10
(planning/research/MISSIONS-MATRIX.md §1b, 123 rows) in the original's chain order, through the real handlers.

Each quest must be offered when its turn comes (the client's own offer rule, read from questtable: Use_Quest, the
level, Require1..3, its giver placed in a zone), then is accepted (0x5542), each condition is met by the trigger that
moves it live, and it is handed in (0x5544) with its rewards:
  Talk                0x554b, the client's report after the NPC's dialog (its NPC placed in a zone)
  QuestBound          0x5558, the client's area report in a field room (the area in that field's zone)
  PropActivate        0x5094 / 0x5096 casts of that prop type in the field room
  NPNameKill / Group  0x5053 hit reports of the hero until the named troop falls in its room (game troop_down)
  ItemGain            the accept's item; or the quest drops of those kills picked up (0x4052); or a box's (0x5098)
  UseItem             0x4067, the quest item used on its target
  MissionLevelClear   the mission room played through (its table, lessons and waves) and won, at ID1's difficulty
  Realm               0x5a44, the realm join
  tutorial quests     the action the client's tutorial watches, through its handler where the server has one, then
                      the client's counter 0x554f (quest.TUTORIALS_COUNTED); TeleportCrystal1 / 2: the quest's crystal
                      used from its field room's map (0x4071 -> 0x4072, 0x4069 -> 0x406a, whose event 0x59 counts)
A level the hero lacks for the next quest is earned by hunting in the field (kill exp of real kills), as a player
would. Not walked: the trips between spots (the doors, warps and the world map have their own tests) and the rooms'
movement. The four hidden prologue quests (UNREACHABLE) are never offered by the table; their names are the prologue's
four phases, so the original's lost mission Lua likely gave them (LEVEL10-PLAN F1). Hidden and rewardless: not given."""
import collections
import functools
import random
import struct
import time

import pytest

from kuf2 import (combat, director, game, hero, items, obf, quest, serials, state as state_mod, tables, titles,
                  troops, world, zone)
from kuf2.obf import T2
from kuf2.packet import Reader
from conftest import run_pending
from test_battle import hit_header, hit_until_down
from test_director import obey

# MISSIONS-MATRIX §1b.1 (main story, 112) then §1b.2 (side, 11): the questtable requirements' order, ties by the
# original's playlist parts 1-4
CHAIN = (
    1003, 1150106, 1150109, 1150110, 1150201, 1150202, 1150205, 1150203, 1150204, 1150206, 1150301, 1150302, 1150304,
    9900118, 1150306, 1150303, 1150305, 1150307, 1150316, 1150312, 1150308, 1150309, 1150311, 1150310, 1150404,
    9900123, 1150401, 1150402, 1150403, 1150405, 1150406, 1150501, 1150503, 9900103, 1150502, 1150801, 1150802,
    1150803, 1150811, 1150804, 1150805, 1150806, 1150807, 1150808, 1150809, 1150810, 1150601, 1150602, 1150603,
    1150701, 1150702, 1150703, 1160105, 1160102, 1160108, 1160104, 1160103, 1160101, 1160106, 1160107, 1160200,
    1160201, 1160202, 1160203, 1160204, 1160205, 1160206, 1160207, 1160208, 1160209, 1160210, 1160211, 1160218,
    1160213, 1160219, 1160214, 1160212, 1160215, 1160216, 9900104, 1160113, 1160303, 1160305, 1160306, 1160301,
    1160413, 1160302, 1160415, 1160416, 1160304, 1160307, 1160403, 1160406, 1160407, 1160408, 1010101, 1010102,
    1021001, 1021002, 1081, 1021003, 1021006, 1021005, 1021004, 1160430, 1010201, 1010202, 1160431, 1160432, 1160433,
    1160434, 1160442, 9900284, 9900285, 9900286, 9900287,
    1010103, 9900125, 1010203, 9900221, 1110501, 1160435, 9900228,
)
UNREACHABLE = (9900284, 9900285, 9900286, 9900287)  # JustCompleted, Show_Quest No, no giver, Require FinishedQuest 1:
                                                    # quest 1 is AcquireLevel 100 at spot 880101, never finished
HERO_CLASS = 0                  # Glen (createcharacter HeroId 0)
GRIND_KILLS = 400               # the most kills a level gate may take before the walk calls it a gap
HITS = 10000                    # the most hit reports the hero spends on one troop, at the game's own damage
                                # (combat.HERO_DAMAGE_SCALE 1; 2026-11-05: 11 of the walk's 768 kills take more than 300,
                                # one of 1010203's 106030 troops in 10306 takes 4,828; the old 300 held only with the owner's
                                # 10000 hero, which this module-scoped walk used to inherit before it became an option)
KILL_ROUNDS = 60                # rounds of "down what matches, let the field respawn" per kill / drop condition
QT = tables.by_id("questtable")


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


class Sink:
    def __init__(self):
        self.sent, self.pending = [], []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


class Open:
    def is_closing(self):
        return False


class State:
    """The server state of the walk: the real State's db (the character was made there), no writes, rooms by
    account."""
    def __init__(self, real):
        self.db = real.db
        self.game_sessions = {}

    def save(self):
        pass


class Room(Sink):
    """A field or mission room of the walker's hero (game.make's handlers run on it)."""
    def __init__(self, state, acct, c, spot, difficulty=0):
        super().__init__()
        self.w, self.state = Open(), state
        self.data = {"battle": combat.Battle(), "spot": spot, "difficulty": difficulty, "account": acct, "char": c}
        self.data["battle"].add_hero(0, game.hero_max_hp(self), c=game.hero_combatant(c))
        game.spawn_zone_troops(self)


@functools.lru_cache(maxsize=None)
def placed(kind, spot):
    """What the zone of `spot` places: NPC table ids, quest bound ids, prop types, troop table ids."""
    if not zone.available(spot):
        return frozenset()
    z = zone.for_spot(spot)
    key = {"npc": ("NPCInfo", "TableID"), "bound": ("QuestBound", "QuestBoundID"),
           "prop": ("SmartPropData", "SmartPropTypeID"), "troop": ("NPCTroopInfoData", "TroopTableID")}[kind]
    return frozenset(e[key[1]] for e in z.get(key[0]) or [])


def spots_of(q):
    """The spots a quest names (Begin / End / IngSpot1..5), fields first."""
    out = []
    for col in ("BeginSpot", "EndSpot", *(f"IngSpot{n}" for n in range(1, 6))):
        v = q.get(col, "")
        if v.isdigit() and int(v) not in out:
            out.append(int(v))
    return sorted(out, key=lambda sp: not game.is_field(sp))


class Walk:
    def __init__(self, tmp):
        real = state_mod.State(tmp / "db.json")
        self.acct = real.account_for_steam(76561190000001010, "p")
        self.ws = Sink()
        self.ws.data = {"account": self.acct}
        look = bytearray(56)
        struct.pack_into("<I", look, 0x34, HERO_CLASS)
        self.call(world.C2S_CHAR_CREATE, b"Walker\0" + bytes(look), role=world.make(real, 0, "127.0.0.1", 0))
        self.st = State(real)
        self.role = world.make(self.st, 0, "127.0.0.1", 0)
        self.game = game.make(self.st, 0)
        self.c = self.acct["characters"][0]
        self.ws.data.update(char=self.c, battle_spot=self.c["spot"], game_addr=("127.0.0.1", 0))
        self.rooms = {}
        self.results = {}
        self.grind_log = []

    # --- the client's requests -------------------------------------------------------------------------------------
    def call(self, proto, body, s=None, role=None):
        (role or self.role).handlers[proto](s or self.ws, pkt(proto, body))

    def play(self, proto, body, s):
        self.call(proto, body, s, self.game)

    def record(self):
        return quest.record(self.c)

    def room(self, spot, difficulty=0, fresh=False):
        """The hero's room on `spot` (kept per field, so its troops' respawns follow; a mission is entered anew)."""
        if fresh or spot not in self.rooms or game.is_mission(spot):
            self.rooms[spot] = Room(self.st, self.acct, self.c, spot, difficulty)
        g = self.rooms[spot]
        self.st.game_sessions[self.acct["id"]] = g
        return g

    # --- the offer --------------------------------------------------------------------------------------------------
    def offered(self, q):
        """The client's offer of quest q (questtable, the finished list, the hero's level), and its giver placed."""
        r = self.record()
        if q["Use_Quest"] != "Yes" or q["ID"] in r["active"] or int(q["ID"]) in r["done"]:
            return False
        if int(q["AcquireLevel"]) > self.c.get("level", 1):
            return False
        return self.reqs_met(q) and self.giver_placed(q)

    def reqs_met(self, q):
        r = self.record()
        for n in (1, 2, 3):
            kind, v = q.get(f"Require{n}_Type", ""), q.get(f"Require{n}_Value", "")
            if kind == "FinishedQuest" and int(v) not in r["done"]:
                return False
            if kind == "FinishOrDoingQuest" and int(v) not in r["done"] and v not in r["active"]:
                return False
            if kind == "Realm" and not self.c.get("realm"):
                return False
            if kind not in ("", "FinishedQuest", "FinishOrDoingQuest", "Realm"):
                raise AssertionError(f"quest {q['ID']}: requirement {kind} not modelled")
        return True

    def giver_placed(self, q):
        return q["Start_Type"] == "Npc" and any(int(q["Start_Value"]) in placed("npc", sp) for sp in spots_of(q))

    # --- conditions -------------------------------------------------------------------------------------------------
    def count(self, qid, n):
        q = self.record()["active"].get(str(qid))
        return q["counts"][n] if q else None

    def drive(self, qid, n, res):
        q = QT[str(qid)]
        kind, id1, id2 = q[f"Complete{n + 1}_Type"], q[f"Complete{n + 1}_ID1"], q[f"Complete{n + 1}_ID2"]
        need = quest.conditions(q)[n][2]
        ing = q.get(f"IngSpot{n + 1}", "")
        spot = int(ing) if ing.isdigit() else None
        how = getattr(self, "by_" + kind.lower(), None)
        if how is None:
            return f"no driver for {kind}"
        return how(qid, n, id1, id2, need, spot, q)

    def by_talk(self, qid, n, npc, _id2, need, spot, q):
        where = [sp for sp in ([spot] if spot else []) + spots_of(q) if int(npc) in placed("npc", sp)]
        if not where:
            return f"NPC {npc} placed in none of {spots_of(q)}"
        self.call(quest.C2S_PROGRESS, struct.pack("<H", 1) + obf.u32(qid) + bytes([n]))
        return f"0x554b at NPC {npc} ({where[0]})"

    def by_questbound(self, qid, _n, area, _id2, _need, spot, q):
        where = [sp for sp in ([spot] if spot else []) + spots_of(q)
                 if game.is_field(sp) and int(area) in placed("bound", sp)]
        if not where:
            return f"area {area} in no field room of {spots_of(q)}"
        self.room(where[0])
        self.call(quest.C2S_AREA, obf.u32(where[0]) + struct.pack("<I", int(area)))
        return f"0x5558 area {area} in {where[0]}"

    def by_propactivate(self, qid, n, ptype, _id2, need, spot, q):
        where = [sp for sp in ([spot] if spot else []) + spots_of(q) if int(ptype) in placed("prop", sp)]
        if not where:
            return f"prop type {ptype} in none of {spots_of(q)}"
        g = self.room(where[0])
        props = [p["SmartPropID"] for p in zone.for_spot(where[0])["SmartPropData"]
                 if p["SmartPropTypeID"] == int(ptype)]
        for pid in props:
            if self.count(qid, n) >= need:
                break
            self.play(game.C2S_PROP_CAST, struct.pack("<H", 0) + obf.u32(pid), g)
            self.play(game.C2S_PROP_CAST_DONE, bytes(2) + obf.u32(pid), g)
        return f"0x5094/0x5096 casts of prop type {ptype} in {where[0]}"

    def matches(self, kind, name, t):
        if kind == "NPNameKill":
            return name in quest.kill_names(t["TroopTableID"]) | quest.leader_names(t.get("NPLeaderID"))
        return name in quest.kill_groups(t["TroopTableID"])

    def hunt(self, g, want, done, rounds=KILL_ROUNDS):
        """Fell the room's standing troops for which want(t) holds by the hero's hits until done(); between rounds the
        field's own respawns run. Returns the kills."""
        kills = 0
        for _ in range(rounds):
            if done():
                return kills
            standing = [u for u, t in g.data.get("zone_troops", {}).items()
                        if want(t) and u not in g.data.get("down", set()) | g.data.get("unhurt", set())
                        and any(g.data["battle"].troops[u]["units"])]
            for u in standing:
                if done():
                    return kills
                if not self.fell(g, u):
                    g.data.setdefault("unhurt", set()).add(u)
                    continue
                kills += 1
                self.pick_up(g)
            if not standing:
                if not g.pending:
                    return kills
                run_pending(g)
        return kills

    def fell(self, g, u, cap=HITS):
        """The hero's 0x5053 hits on troop u until it falls (the room's troop_down: quest kills, exp, drops); False when
        cap reports leave it standing (a scripted or untouchable troop)."""
        try:
            hit_until_down(self.game, g, u, hit_header(0), cap=cap)
        except AssertionError:
            return False
        return True

    def pick_up(self, g):
        """Take what the room's ground drops hold for the held quests (0x4052, the client's pick)."""
        for drop_id, entries in list(g.data.get("drops", {}).items()):
            for index, (code, n) in list(entries.items()):
                if (items.row(code) or {}).get("ItemKind") != "QUEST_ITEM":
                    continue
                body = obf.u16(n) + struct.pack("<I", drop_id) + obf.u32(code) + obf.u16(index)
                self.play(game.C2S_DROP_PICK, body, g)

    def by_npnamekill(self, qid, n, _id1, name, need, spot, q, kind="NPNameKill"):
        for sp in ([spot] if spot else []) + spots_of(q):
            if game.is_mission(sp):                 # a mission's troop: it falls while the mission is played
                won = self.win(sp)
                if self.count(qid, n) >= need:
                    return f"in the play of mission {sp}: {won}"
                continue
            if not (game.is_field(sp) and zone.available(sp)):
                continue
            g = self.room(sp)
            kills = self.hunt(g, lambda t: self.matches(kind, name, t), lambda: self.count(qid, n) >= need)
            if self.count(qid, n) >= need:
                return f"{kills} kills by hits in {sp}"
        return f"no troop named {name} fell in {spots_of(q)}"

    def by_npgroupkill(self, *a):
        return self.by_npnamekill(*a, kind="NPGroupKill")

    def by_itemgain(self, qid, n, code, _id2, need, spot, q):
        if self.count(qid, n) >= need:
            return "the accept's item"
        drops = {int(r["NPTroopID"]) for r in tables.sections("item_drop_quest")["Troop"]
                 for k in range(1, 6) if r.get(f"Quest{k}") == str(qid) and r.get(f"Quest{k}_Item") == code}
        leaders = {int(r["NPLeaderID"]) for r in tables.sections("item_drop_quest")["Leader"]
                   for k in range(1, 11) if r.get(f"Quest{k}") == str(qid) and r.get(f"Quest{k}_Item") == code}
        for sp in ([spot] if spot else []) + spots_of(q):
            if not (game.is_field(sp) and zone.available(sp)):
                continue
            g = self.room(sp)
            if drops or leaders:
                kills = self.hunt(g, lambda t: t["TroopTableID"] in drops or t.get("NPLeaderID") in leaders,
                                  lambda: self.count(qid, n) >= need)
                if self.count(qid, n) >= need:
                    return f"drops of {kills} kills in {sp}, picked up"
            boxes = [p for p in zone.for_spot(sp)["SmartPropData"]
                     if (game.prop_row(p["SmartPropTypeID"]) or {}).get("GrantItem1_IB") == code]
            for _ in range(need * 4):
                for p in boxes:
                    if self.count(qid, n) >= need:
                        return f"boxes of type {p['SmartPropTypeID']} in {sp}"
                    self.open_box(g, p["SmartPropID"])
                if self.count(qid, n) >= need or not boxes:
                    break
                run_pending(g)                  # the boxes come back
            if self.count(qid, n) >= need:
                return f"boxes in {sp}"
        return f"item {code}: no drop or box gave it in {spots_of(q)}"

    def open_box(self, g, pid):
        self.play(game.C2S_PROP_CAST, struct.pack("<H", 0) + obf.u32(pid), g)
        self.play(game.C2S_PROP_CAST_DONE, bytes(2) + obf.u32(pid), g)
        for index, (code, n) in list(g.data.get("box_loot", {}).get(pid, {}).items()):
            self.play(game.C2S_BOX_ITEM, obf.u32(code) + obf.u32(pid) + obf.u16(index) + obf.u16(n) + bytes(2), g)

    def by_useitem(self, qid, n, code, _id2, need, spot, q):
        row = items.row(code) or {}
        target = int(row.get("UseTargetID", "0") or 0)
        enc = obf.u32(int(code))
        for _ in range(need):
            self.call(world.C2S_QUEST_ITEM_USE, bytes([T2[(enc[0] * 8 + 1) & 0xff]]) + enc + obf.u32(target))
        return f"0x4067 x{need} on NPC {target}"

    def by_missionlevelclear(self, qid, n, diff, _id2, need, spot, q):
        difficulty = {"HARD": 1, "HELL": 2}.get(diff.upper(), 0)
        return self.win(spot, difficulty)

    def win(self, spot, difficulty=0):
        g = self.room(spot, difficulty)
        steps = director.script(spot)
        bounds = [director.bound(spot, st["bound"]) for st in steps if st["on"] == "bound"]
        awaited = {st["force"] for st in steps if st["on"] == "down" and st.get("force") is not None}
        for _ in range(200):
            if g.data.get("mission_won"):
                break
            for b in bounds:
                combat.hero_moved(g, (b["BoundCenterX"], 0, b["BoundCenterZ"]))
            alive = [u for u, z in g.data.get("zone_troops", {}).items()
                     if (game.hostile(z) or z.get("ForceNum") in awaited) and u not in g.data.get("down", set())]
            for u in alive:
                if g.data.get("mission_won"):
                    break
                if not (u in g.data["battle"].troops and any(g.data["battle"].troops[u]["units"])
                        and self.fell(g, u)):
                    game.mission_troop_down(g, self.st, u)        # the script's own fall (staging, untouchable)
                    g.data["scripted"] = g.data.get("scripted", 0) + 1
            run_pending(g)
            obey(g)
        run_pending(g)
        return f"mission {spot} won ({game.DIFFICULTY[difficulty]})" if g.data.get("mission_won") else \
            f"mission {spot} not won"

    def by_realm(self, qid, n, *_):
        self.call(world.C2S_REALM_JOIN, bytes([obf.via_t1(1)]))
        return "0x5a44 realm 1"

    # --- tutorials --------------------------------------------------------------------------------------------------
    def bag(self, code):
        return next((i for i in self.c.get("bag", []) if i["code"] == code), None)

    def use(self, code):
        """The bag's item used (0x4042); its reply's result (0 = used)."""
        it = self.bag(code)
        if it is None:
            return None
        for cooldown in self.c.get("cooldowns", {}).values():
            cooldown[1] = min(cooldown[1], time.time() - 1)   # the walk's actions are minutes apart, not microseconds
        return self.ask(world.C2S_USE_ITEM, bytes(6) + obf.u32(code) + bytes(2) + obf.u64(it["serial"]) + bytes(7),
                        world.S2C_USE_ITEM)

    def ask(self, proto, body, reply):
        """A request on the world connection and the i16 result of its reply (None: no reply)."""
        got = self.answer(proto, body, reply)
        return struct.unpack_from("<H", got)[0] if got is not None else None

    def answer(self, proto, body, reply):
        """A request on the world connection and its reply's body (None: no reply)."""
        mark = len(self.ws.sent)
        self.call(proto, body)
        got = [w for w in self.ws.sent[mark:] if w.proto == reply]
        return bytes(got[0].buf) if got else None

    def crystal(self, portal, at=None):
        """The hero uses crystal `portal` from the map of its field's room. The client sends what it sends in town
        (the tactical map's UsePortal asks its confirm through CommonSubWorldMap: quest.py "Tutorial quests"):
        0x4071 with the crystal's point (the zone's start point of that LongWarpID, else `at`) -> 0x4072, the cast,
        then 0x4069 -> 0x406a. Returns the portal the client's 0x406a handler raises tutorial event 0x59 with: the id
        0x4072 left pending (0x14089d920 sets +0x118 from the reply's coded id, 0x14089d0f0 raises it), or None when
        a reply refuses (the cast does not start, or the move fails)."""
        row = next(r for r in tables.sections("warpinfo")["Portal"] if r["Portal_ID"] == str(portal))
        spot = int(row["SpotID"])
        self.room(spot)
        point = next((p["StartPointInfoData"][0] for p in zone.for_spot(spot)["PlayerStartPointInfoData"]
                      if p.get("LongWarpID") == portal and p["StartPointInfoData"]), None)
        x, z = (point["PosX"], point["PosZ"]) if point else at
        q, p15 = obf.pos_xz(int(x), int(z))
        req = obf.u32(portal) + q + struct.pack("<h", 0) + bytes([p15])
        start = self.answer(world.C2S_WARP_START, req, world.S2C_WARP_START)
        if start is None or struct.unpack_from("<h", start, 8)[0] != 0:
            return None
        pending = obf.dec_u32(start[4:8])
        use = self.answer(world.C2S_WARP_USE, req, world.S2C_WARP_USE)     # the cast's end (0x14089b450)
        if use is None or struct.unpack_from("<h", use)[0] != 0:
            return None
        assert obf.dec_u32(use[2:6]) == pending                          # the handler's own assert (0x14089d0f0)
        return pending

    def tutorial(self, qid, res):
        """What the player does for the client's tutorial object (quest.TUTORIALS_COUNTED), through the server's
        handlers where the step has one, then the client's 0x554f. Returns how, or raises with why not."""
        row = next(r for r in tables.sections("tutorialquest")["TutorialQuest"] if r["QuestId"] == str(qid))
        kind = row["TutorialQuestType"]
        if kind == "ItemEquip":                     # the accept's weapon, dragged onto the hero (event 0x4b)
            code = quest.accept_items(QT[str(qid)], self.c["class"])[0][0]
            it = self.bag(code)
            index = items.PARTS[items.row(code)["Parts"]] - 1      # the equipment index is E_ItemParts - 1
            worn = next((e for e in hero.equipment(self.c) if e["index"] == index), None)
            got = self.ask(world.C2S_EQUIP, obf.u64(it["serial"]) + obf.u64(worn["serial"] if worn else 0)
                           + obf.u16(index) + obf.u16(it["slot"]), world.S2C_EQUIP)
            assert got == 0 and any(e["code"] == code for e in hero.equipment(self.c)), f"equip {code}: {got}"
            how = f"0x164e equips {code}"
        elif kind == "VehicleGuide":                # the horse used (0x4a), chosen (0x10f5: 0x48), ridden (0x49)
            assert self.use(int(row["CompleteID"])) == 0
            vehicle = int(next(iter(self.c["vehicles"])))
            assert self.ask(titles.C2S_RIDE_VEHICLE, struct.pack("<Hq", vehicle, -1), titles.S2C_RIDE_VEHICLE) == 0
            self.call(world.C2S_RIDE, struct.pack("<H", vehicle))
            assert self.c.get("vehicle") == vehicle
            how = f"mount {vehicle}: 0x4042, 0x10f4, 0x125e"
        elif kind == "CheckActivation":             # the contract used (0x4a), its troop into the deck (0x10)
            assert self.use(int(row["CompleteSubID"])) == 0
            t = self.c["troops"][-1]
            got = self.ask(troops.C2S_TO_DECK, bytes([1, 1]) + struct.pack("<Q", t["uid"]) + obf.u32(0xFFFFFFFF),
                           troops.S2C_TO_DECK)
            assert got == 0 and troops.lineup(self.c)["slots"][1] == t["uid"]
            how = f"contract {row['CompleteSubID']} used, troop {t['id']} into deck slot 1 (0x134c)"
        elif kind == "TrainTroop":                  # the Grey Wood Bowmen contract used (0x4a), then TroopTrainingStart
            used = self.use(int(row["CompleteSubID"]))                # on that troop (0x18 with its uid)
            t = next(t for t in self.c.get("troops", []) if t["id"] == int(row["CompleteID"]))
            low = t["uid"] & 0xffffffff             # what the tutorial keeps of the troop map's uid (0x14082dce3)
            res["uid_matches"] = (low - (1 << 32) if low & 0x80000000 else low) == t["uid"]
            cost = troops.troop_need(t["id"], t["level"]) - t["exp"]
            gold = troops.training_gold(t["id"], [t["level"]])
            if cost <= self.c.get("barrack_exp", 0) and gold <= self.c.get("gold", 0):
                level = t["level"]
                assert self.ask(troops.C2S_TRAIN, struct.pack("<QQQ", 0, cost, t["uid"]), troops.S2C_TRAIN) == 0
                how = f"troop {t['id']} (uid {t['uid']:#x}) trained {level} -> {t['level']} (0x1361)"
            else:                                   # the window checks the pool itself (0x140e3fbd0: text 8021, no
                how = (f"troop {t['id']} (uid {t['uid']:#x}): Train clicked; the pool's {self.c.get('barrack_exp', 0)}"
                       f" exp < the level's {cost}, so the client refuses the training itself (text 8021) and"
                       f" its tutorial still counts the click (event 0x18 follows TroopTrainingStart, 0x140e3cbf2)")
            how = f"contract {'used' if used == 0 else 'not in the bag'}, " + how
        elif kind in ("TeleportCrystal1", "TeleportCrystal2"):   # the quest's crystal used in its field's room
            portal = int(row["CompleteID"])
            gold = self.c.get("gold", 0)
            res["raised"] = self.crystal(portal)
            how = (f"crystal {portal} from the room's map: 0x4071 -> 0x4072, 0x4069 -> 0x406a (event 0x59 with"
                   f" {res['raised']}, {gold - self.c.get('gold', 0)} gold)")
        else:                                       # LearnSkill: the skill window's lesson pages (SkillDescOK 2)
            how = f"{kind}: the client's own window (no request)"
        res["early_hand_in"] = self.ask(quest.C2S_COMPLETE, obf.u32(qid) + b"\xff", quest.S2C_COMPLETE)
        if not self.client_counts(kind, row, res):
            return how + "; the client's tutorial would not count it: no 0x554f"
        self.call(troops.C2S_TUTORIAL_COUNT, struct.pack("<H", 1) + obf.u32(qid) + bytes(1))
        return how + ", then 0x554f"

    def client_counts(self, kind, row, res):
        """Whether the client's tutorial object counts the step just done (its check, read from the client): the
        walk sends 0x554f only then."""
        if kind == "ItemEquip":                     # the worn item is the class's TutorialLink item (0x140830560)
            link = next(r for r in tables.sections("tutorialquest")["TutorialLink"]
                        if r["CompleteID"] == row["CompleteID"])[f"Hero_{self.c['class']}"]
            return int(link) in {e["code"] for e in hero.equipment(self.c)}
        if kind == "VehicleGuide":                  # a chosen vehicle ridden (states 2 -> 3 -> the ride's 0x49)
            return bool(self.c.get("vehicle"))
        if kind == "CheckActivation":               # a troop in a main-deck slot 1..8 (event 0x10, 0x14082d6d0)
            return any(troops.lineup(self.c)["slots"][1:])
        if kind == "TrainTroop":                    # the clicked troop's uid equals its kept low 32 bits (0x14082dc48)
            return res["uid_matches"]
        if kind in ("TeleportCrystal1", "TeleportCrystal2"):    # event 0x59's portal is the row's CompleteID
            return res["raised"] == int(row["CompleteID"])      # (0x140832250 case 0x59)
        return True

    # --- the walk ---------------------------------------------------------------------------------------------------
    def holds(self, code):
        return sum(i["count"] for i in self.c.get("bag", []) if i["code"] == code)

    def mailed(self, code):
        """Units of code the overflow mail holds (world.add_item mails what the bag cannot take)."""
        return sum(i["count"] for m in self.c.get("mail", []) for i in m["items"] if i["code"] == code)

    def total_exp(self):
        return sum(world.hero_need(lv) for lv in range(1, self.c.get("level", 1))) + self.c.get("exp", 0)

    def grind(self, level, q):
        """Hunt in the giver's field until the hero reaches `level` (kill exp, the real kills)."""
        kills = 0
        for sp in spots_of(q):
            if not (game.is_field(sp) and zone.available(sp)) or game.is_mission(sp):
                continue
            g = self.room(sp)
            kills += self.hunt(g, game.hostile, lambda: self.c.get("level", 1) >= level or kills >= GRIND_KILLS,
                               rounds=GRIND_KILLS)
            if self.c.get("level", 1) >= level:
                break
        self.grind_log.append((int(q["ID"]), level, kills, self.c.get("level", 1)))
        return kills

    def take(self, qid):
        q = QT[str(qid)]
        res = {"id": qid, "offered": False, "accepted": False, "conds": [], "handed": False, "notes": []}
        self.results[qid] = res
        if int(q["AcquireLevel"]) > self.c.get("level", 1) and self.reqs_met(q):
            res["notes"].append(f"level {self.c.get('level', 1)} < {q['AcquireLevel']}: "
                                f"{self.grind(int(q['AcquireLevel']), q)} kills hunting")
        res["offered"] = self.offered(q)
        if not res["offered"]:
            res["notes"].append("not offered: level %s, requirements %s, giver %s" % (
                self.c.get("level", 1), self.reqs_met(q), self.giver_placed(q)))
            return res
        for sp in spots_of(q):          # the accept is made where the giver stands; a quest spawn joins that room
            if game.is_field(sp) and zone.available(sp) and int(q["Start_Value"]) in placed("npc", sp):
                self.room(sp)
                break
        self.call(quest.C2S_ACCEPT, bytes([T2[(obf.u32(qid)[0] * 4) & 0xff]]) + obf.u32(qid))
        rec = self.record()["active"].get(str(qid))
        res["accepted"] = rec is not None
        if rec is None:
            return res
        res["tutorial"] = "counter" if rec.get("tutorial") else (
            "accept" if q.get("Tutorial_Quest") == "Yes" else None)
        accepted = {str(code) for code, _ in quest.accept_items(q, self.c["class"])}
        for n, (kind, id1, need) in enumerate(quest.conditions(q)):
            if not kind:
                continue
            # the record starts at 0 (the accept's own item has counted already: its trigger is the accept)
            before = 0 if kind == "ItemGain" and id1 in accepted else self.count(qid, n)
            how = self.drive(qid, n, res)
            res["conds"].append({"kind": kind, "need": need, "before": before, "after": self.count(qid, n), "how": how})
        if rec.get("tutorial"):
            res["notes"].append(self.tutorial(qid, res))
        elif q.get("Tutorial_Quest") == "Yes":
            res["notes"].append("done at accept: the client's counter cannot come in our flow (quest.TUTORIALS_COUNTED)")
        gold, exp = self.c.get("gold", 0), self.total_exp()
        rewards = quest.reward_items(q, self.c["class"])
        held = {code: (self.holds(code), self.mailed(code)) for code, _ in rewards}
        mark = len(self.ws.sent)
        self.call(quest.C2S_COMPLETE, obf.u32(qid) + b"\xff")
        ok = [w for w in self.ws.sent[mark:] if w.proto == quest.S2C_COMPLETE and bytes(w.buf)[:2] == bytes(2)]
        res["handed"] = bool(ok) and qid in self.record()["done"]
        res["gold"] = self.c.get("gold", 0) - gold
        res["exp"] = self.total_exp() - exp
        res["items"] = {code: self.holds(code) - held[code][0] + self.mailed(code) - held[code][1]
                        for code, _ in rewards}
        res["mailed"] = [code for code, _ in rewards if self.mailed(code) > held[code][1]]
        if res["mailed"]:
            res["notes"].append(f"bag full ({len(self.c['bag'])} of {self.c['bag_slots']}): {res['mailed']} mailed")
        res["rewards"] = rewards
        return res

    def run(self):
        self.first = [qid for qid in CHAIN if self.offered(QT[str(qid)])]    # what a new character is offered
        for qid in CHAIN:
            self.take(qid)              # UNREACHABLE too: not offered (no giver, Require FinishedQuest 1)
        return self


@pytest.fixture(scope="module")
def walk(tmp_path_factory):
    kept = random.getstate()
    random.seed(20261024)                       # the quest drops' rolls (quest.roll_drops): one walk, every run
    try:
        return Walk(tmp_path_factory.mktemp("walk")).run()
    finally:
        random.setstate(kept)


def test_the_chain_is_the_matrix_list():
    lv = {qid for qid, r in QT.items() if r["AcquireLevel"].isdigit() and int(r["AcquireLevel"]) <= 10
          and r["Use_Quest"] == "Yes"}
    assert sorted(CHAIN) == sorted(int(q) for q in lv) and len(CHAIN) == len(set(CHAIN)) == 123


@pytest.mark.parametrize("qid", [q for q in CHAIN if q not in UNREACHABLE])
def test_each_quest_is_offered_met_by_its_triggers_and_handed_in(walk, qid):
    res = walk.results[qid]
    q = QT[str(qid)]
    num = lambda v: int(v) if v.isdigit() else 0
    assert res["offered"], res["notes"]
    assert res["accepted"]
    assert res["conds"] or q["Tutorial_Quest"] == "Yes"         # only a tutorial quest has no condition
    for cnd in res["conds"]:
        assert cnd["before"] < cnd["need"] <= cnd["after"], (cnd, res["notes"])
    if res.get("tutorial") == "counter":
        assert res["early_hand_in"] == quest.RESULT_FAIL, "handed in before the client's counter"
    assert res["handed"], res
    assert (res["gold"], res["exp"]) == (num(q["Gold"]), num(q["Exp"]))
    for code, n in res["rewards"]:
        assert res["items"][code] >= n, (code, n, res["items"])


def test_the_hidden_prologue_quests_are_never_offered(walk):
    one = QT["1"]
    assert (one["AcquireLevel"], one["BeginSpot"]) == ("100", "880101")
    for qid in UNREACHABLE:
        q = QT[str(qid)]
        assert (q["Require1_Type"], q["Require1_Value"], q["Complete1_Type"]) == ("FinishedQuest", "1", "JustCompleted")
        assert not walk.results[qid]["offered"] and not walk.results[qid]["handed"]


def test_the_walk_hands_in_every_reachable_quest(walk):
    handed = [qid for qid in CHAIN if walk.results[qid]["handed"]]
    assert len(handed) == len(CHAIN) - len(UNREACHABLE) == 119, [
        (qid, walk.results[qid]["notes"], walk.results[qid]["conds"]) for qid in CHAIN
        if not walk.results[qid]["handed"] and qid not in UNREACHABLE][:5]
    assert walk.first == [1003]                 # a new character is offered Sarah's first quest, nothing else
    assert walk.grind_log == [], walk.grind_log  # the quests' own kills and rewards carry the hero to each level gate
    assert walk.c["level"] >= 10


def test_the_tutorial_quests_wait_for_the_clients_counter_where_it_comes(walk):
    by = collections.defaultdict(list)
    for qid in CHAIN:
        if walk.results[qid].get("tutorial"):
            by[walk.results[qid]["tutorial"]].append(qid)
    assert by == {"counter": [9900118, 1150312, 9900123, 9900103, 1160214, 9900104, 9900125]}
    for qid, portal in ((1150312, 4000), (1160214, 5001)):     # each counted from its own crystal's 0x406a
        assert walk.results[qid]["raised"] == portal, walk.results[qid]["notes"]


def test_the_trained_bowman_completes_9900104_and_1160113_is_offered(walk):
    # live 2026-09-28: training the Grey Wood Bowmen twice left 9900104 open (`!questdone 9900104`): the tutorial
    # compares the low 32 bits of the troop's uid with the 64-bit uid the training window passes (serials.troop_uid)
    res = walk.results[9900104]
    assert res["uid_matches"] and res["handed"], res["notes"]
    bowman = next(t for t in walk.c["troops"] if t["id"] == 2202311)
    assert bowman["uid"] <= serials.TROOP_UID_MAX
    assert walk.results[1160113]["offered"] and walk.results[1160113]["handed"]


def test_helenas_equip_tutorial_stays_done_at_accept():
    # tutorialquest %TutorialLink row 5 (9900118's CompleteID) has no HELENA item (Hero_5 -1): the equip event never
    # matches for her, so the counter never comes (0x140830560)
    assert [quest.tutorial_waits(QT["9900118"], cls) for cls in range(6)] == [True] * 5 + [False]
    assert all(quest.tutorial_waits(QT["9900125"], cls) for cls in range(6))      # LearnSkill reads no link
    assert all(quest.tutorial_waits(QT[qid], cls) for qid in ("1150312", "1160214") for cls in range(6))
    assert not quest.tutorial_waits(QT["1003"], 0)


def test_a_counted_tutorial_is_handed_in_after_its_counter_and_a_saved_one_as_before(tmp_path):
    w = Walk(tmp_path)
    accept = lambda qid: w.call(quest.C2S_ACCEPT, bytes([T2[(obf.u32(qid)[0] * 4) & 0xff]]) + obf.u32(qid))
    accept(9900104)
    rec = w.record()["active"]["9900104"]
    assert rec["tutorial"]                      # flagged on accept
    assert w.ask(quest.C2S_COMPLETE, obf.u32(9900104) + b"\xff", quest.S2C_COMPLETE) == quest.RESULT_FAIL
    lists = Sink()
    lists.data = {"char": w.c}
    quest.send_lists(lists)                     # the town entry's list says "not ready" (the 0x5540 state byte)
    assert bytes(lists.sent[0].buf)[2 + 13] == 0
    w.call(troops.C2S_TUTORIAL_COUNT, struct.pack("<H", 1) + obf.u32(9900104) + bytes(1))
    assert w.ask(quest.C2S_COMPLETE, obf.u32(9900104) + b"\xff", quest.S2C_COMPLETE) == 0
    w.record()["active"]["9900103"] = {"counts": [0] * quest.CONDITIONS}        # accepted before the counter rule
    assert w.ask(quest.C2S_COMPLETE, obf.u32(9900103) + b"\xff", quest.S2C_COMPLETE) == 0
    accept(9900123)
    assert quest.fill(w.ws, w.st, 9900123) and quest.hand_in(w.ws, w.st, 9900123)     # the owner's !questdone


# Each crystal tutorial's own crystal, then crystals that must not count it: another of its field's crystals, the
# other tutorial's, another field's (the client's map lists only the room's own crystals; the server is not asked).
CRYSTAL_TUTORIALS = {1150312: (4000, (4010, 5001, 6200)), 1160214: (5001, (5002, 4000, 6201))}


@pytest.mark.parametrize("qid", sorted(CRYSTAL_TUTORIALS))
def test_a_crystal_tutorial_waits_for_its_crystal_and_only_its_own_counts(tmp_path, monkeypatch, qid):
    own, others = CRYSTAL_TUTORIALS[qid]
    w = Walk(tmp_path)
    w.c["gold"] = 1000                          # each crystal costs its Cost_Gold (10 / 20 / 0) when the cast ends
    seen = []
    monkeypatch.setattr(quest, "journal_quest", lambda ev, q, *a, **k: seen.append((ev, q)))
    lists = Sink()
    lists.data = {"char": w.c}

    def ready():                                # the 0x5540 state byte of the quest (the town or field entry's list)
        lists.sent.clear()
        quest.send_lists(lists)
        return bytes(lists.sent[0].buf)[2 + 13]

    row = next(r for r in tables.sections("tutorialquest")["TutorialQuest"] if r["QuestId"] == str(qid))
    assert int(row["CompleteID"]) == own

    def counted(portal):                        # the client's tutorial after the 0x406a: case 0x59 (0x140832250)
        raised = w.crystal(portal, at=(0, 0))
        if raised == int(row["CompleteID"]):
            w.call(troops.C2S_TUTORIAL_COUNT, struct.pack("<H", 1) + obf.u32(qid) + bytes(1))
        return raised

    w.call(quest.C2S_ACCEPT, bytes([T2[(obf.u32(qid)[0] * 4) & 0xff]]) + obf.u32(qid))
    assert w.record()["active"][str(qid)]["tutorial"] and ready() == 0      # not done at accept any more
    assert w.ask(quest.C2S_COMPLETE, obf.u32(qid) + b"\xff", quest.S2C_COMPLETE) == quest.RESULT_FAIL
    for portal in others:                       # used, and raised with their own id: never the quest's
        assert counted(portal) == portal
        assert ready() == 0 and w.ask(quest.C2S_COMPLETE, obf.u32(qid) + b"\xff", quest.S2C_COMPLETE) == 1
    gold = w.c["gold"]
    w.c["gold"] = 0                             # short of the crystal's cost: 0x4072 refuses, no cast, no 0x406a
    assert counted(own) is None and w.c["gold"] == 0 and ready() == 0
    w.c["gold"] = gold
    assert w.crystal(own) == own                # the 0x406a alone: the server counts nothing, the client's counter
    assert ready() == 0 and ("done", qid) not in seen                     # 0x554f is the trigger, as in vanilla
    w.call(troops.C2S_TUTORIAL_COUNT, struct.pack("<H", 1) + obf.u32(qid) + bytes(1))
    assert ready() == 1 and seen[-1] == ("done", qid)
    assert w.c["gold"] == gold - world.warp_cost(own) > 0
    assert seen.count(("done", qid)) == 1
    assert w.ask(quest.C2S_COMPLETE, obf.u32(qid) + b"\xff", quest.S2C_COMPLETE) == 0
    assert qid in w.record()["done"]


def test_a_crystal_tutorial_accepted_before_the_change_is_still_done_at_accept(tmp_path):
    w = Walk(tmp_path)
    w.record()["active"]["1150312"] = {"counts": [0] * quest.CONDITIONS}       # saved without the "tutorial" flag
    assert w.ask(quest.C2S_COMPLETE, obf.u32(1150312) + b"\xff", quest.S2C_COMPLETE) == 0


def test_a_troop_uid_is_the_serial_counters_low_word_and_items_continue_above_it():
    c = {"id": 3, "next_serial": 0x40000, "bag": [{"serial": (3 << 32) | 0x40001}]}
    uid = serials.troop_uid(c)
    assert uid == 0x40002 and c["next_serial"] == 0x40002
    c["troops"] = [{"uid": uid}]
    c["next_serial"] = 0                        # a save that lost its high-water mark still skips the troop's
    assert serials.allocate(c) == (3 << 32) | 0x40003
    with pytest.raises(OverflowError):
        serials.troop_uid({"id": 3, "next_serial": serials.TROOP_UID_MAX})

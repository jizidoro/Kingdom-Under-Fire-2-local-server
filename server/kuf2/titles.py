"""Titles, achievements and vehicles (hero window 0x5b, vehicle book 0x80). Tables: titletable %Base (Reward_Title_ID,
Complete1_ID / _Value, Complete2_ID / _Value), %AchievementInfo (Complete_ID, Complete_Type, Complete_Condition1..3),
vehicletable %Base (VehicleID). Items: item_consume GainTitleID (TITLE_ITEM), GainVehicleID (VEHICLE_ACQUIRE, all
PERMANENT). The character keeps c["titles"] (earned title ids), c["title"] (worn: its Ability0_ID counts in the hero's
stats, hero.title_ability; wearing one resends the Info window's block and, in a room, 0x5138), c["achievements"] {Complete_ID:
value}, c["vehicles"] {VehicleID: expiry (-1 = permanent)}, c["vehicle"] (ridden). Spec:
planning/requests/pushes_common.md 0x10f0-0x10f3, session_account_worldmap.md 0x10ee / 0x10f4.

  S2C 0x10f0 (0x1405f4f40) at start: u32 n, n * u32 owned title id (n = 0 changes nothing).
  S2C 0x10f2 (0x1405f4db0): u32 n, n * (u32 value, u32 Complete_ID) achievement counters.
  S2C 0x10f1 (0x140d6fd80): u32 n, n * u32 title id earned (the popup and HUD notice; town / field / battle only).
  C2S 0x10ee: u32 title (0 = take it off) -> S2C 0x10ef (0x140676780): i16; 0 -> u32 title.
  S2C 0x10f3 (0x1406586d0) at start: u16 ridden vehicle, u16 n, n * (u16 VehicleID, u64 expiry); never cleared.
  C2S 0x10f4: u16 vehicle (0 = get off), u64 expiry -> S2C 0x10f5 (0x1406584b0): i16; 0 -> u16 vehicle."""
from . import hero, tables
from .net import log
from .packet import Writer

S2C_TITLES, S2C_TITLE_EARNED, S2C_ACHIEVEMENTS = 0x10f0, 0x10f1, 0x10f2
C2S_WEAR_TITLE, S2C_WEAR_TITLE = 0x10ee, 0x10ef
S2C_VEHICLES = 0x10f3
C2S_RIDE_VEHICLE, S2C_RIDE_VEHICLE = 0x10f4, 0x10f5
PERMANENT = -1
NOT_OWNED = 0x9407


def num(v, d=0):
    return int(v) if str(v).lstrip("-").isdigit() else d


def titles_packet(c):
    owned = c.get("titles", [])
    w = Writer(S2C_TITLES).u32(len(owned))
    for t in owned:
        w.u32(t)
    return w


def achievements_packet(c, only=None):
    ach = {int(k): v for k, v in c.get("achievements", {}).items() if only is None or int(k) in only}
    w = Writer(S2C_ACHIEVEMENTS).u32(len(ach))
    for aid, value in sorted(ach.items()):
        w.u32(value).u32(aid)
    return w


def vehicles_packet(c):
    owned = c.get("vehicles", {})
    w = Writer(S2C_VEHICLES).u16(c.get("vehicle", 0)).u16(len(owned))
    for vid, expiry in sorted(owned.items()):
        w.u16(int(vid)).u64(expiry)
    return w


def login_packets(c):
    return [titles_packet(c), achievements_packet(c), vehicles_packet(c)]


def earn_title(s, c, title):
    owned = c.setdefault("titles", [])
    if title in owned:
        return
    owned.append(title)
    if s is not None:
        s.send(Writer(S2C_TITLE_EARNED).u32(1).u32(title))
    log.info("title %d earned", title)


def achieve(s, state, kind, value=None, add=0, cond=None):
    """An achievement event: counters of kind (whose conditions match cond, a dict {1: v, 2: v, 3: v} of the
    Complete_Condition columns that must equal) set to at least value, or raised by add; titles whose Complete1 is
    reached are earned (0x10f1)."""
    c = s.data.get("char") or s.data["account"]["characters"][0]
    ach = c.setdefault("achievements", {})
    changed = set()
    for r in tables.sections("titletable")["AchievementInfo"]:
        if r["Complete_Type"] != kind:
            continue
        if cond and any(r[f"Complete_Condition{k}"] != str(v) for k, v in cond.items()):
            continue
        aid = str(r["Complete_ID"])
        old = ach.get(aid, 0)
        new = max(old, value) if value is not None else old + add
        if new != old:
            ach[aid] = new
            changed.add(int(aid))
    if not changed:
        return
    s.send(achievements_packet(c, changed))
    for r in tables.sections("titletable")["Base"]:
        if num(r["Complete1_ID"], -1) in changed or num(r["Complete2_ID"], -1) in changed:
            done = all(ach.get(str(r[f"Complete{k}_ID"]), 0) >= num(r[f"Complete{k}_Value"])
                       for k in (1, 2) if r[f"Complete{k}_ID"] not in ("-", ""))
            if done:
                earn_title(s, c, num(r["Reward_Title_ID"]))
    state.save()


def grant_vehicle(s, state, c, vehicle):
    if not any(r["VehicleID"] == str(vehicle) for r in tables.sections("vehicletable")["Base"]):
        return False
    c.setdefault("vehicles", {})[str(vehicle)] = PERMANENT
    state.save()
    s.send(vehicles_packet(c))
    achieve(s, state, "VehicleCount", value=len(c["vehicles"]))
    return True


def make(role, state):
    @role.on(C2S_WEAR_TITLE)
    def wear_title(s, pkt):
        title = pkt.u32()
        c = s.data["char"]
        if title and title not in c.get("titles", []):
            s.send(Writer(S2C_WEAR_TITLE).u16(1))
            return
        c["title"] = title
        state.save()
        s.send(Writer(S2C_WEAR_TITLE).u16(0).u32(title))
        from . import game, world                     # its effect (hero.title_ability) in the Info window and the room
        s.send(Writer(world.S2C_HERO_BLOCK).raw(world.hero_block(c)))
        g = getattr(state, "game_sessions", {}).get((s.data.get("account") or {}).get("id"))
        if g is not None and "battle" in g.data:
            game.room_stats(g, c)
        log.info("title %d worn: %s", title, hero.title_ability(title))

    @role.on(C2S_RIDE_VEHICLE)
    def ride_vehicle(s, pkt):
        vehicle = pkt.u16()
        c = s.data["char"]
        if vehicle and str(vehicle) not in c.get("vehicles", {}):
            s.send(Writer(S2C_RIDE_VEHICLE).u16(NOT_OWNED))
            return
        c["vehicle"] = vehicle
        state.save()
        s.send(Writer(S2C_RIDE_VEHICLE).u16(0).u16(vehicle))

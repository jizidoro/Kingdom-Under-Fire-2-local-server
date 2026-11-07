"""PvP against AI (server/kuf2/pvp.py): the War Tutorial spots 20954 / 20955 / 20956 as a 16-player room with 15 AI
players, each request through its registered handler: the world role's start 0x3e5e, the game role's room start
(0x3f4e / 0x3f4f / 0x3f50), the loading's end, hits both ways, the win and its result 0x5043. The byte places are the
client's readers' (pvp.py's docstring); the rule for the win is ours and named so there. Reads the installed game's
tables and zone files. The dig and the verdicts: planning/agents/reports/2026-11-05_contract2-pvpai.md.
Run: py -m pytest -q server/tests"""
import socket
import struct

import pytest

from kuf2 import combat, game, hero, items, obf, pvp, status, tables, world, zone
from kuf2.packet import OBOOL_FALSE, OBOOL_TRUE, Reader
from test_army import army
from test_rewards import Session as WorldSession, State, char

FIELD, ATTACK, DEFENCE = 20954, 20955, 20956            # Field of Smash; Stonehall Siege attack / defence
SPOTS = {FIELD: 0, ATTACK: 8, DEFENCE: 0}               # aipctrooptable %AIPVP: the seat left to the player
ROOM = {FIELD: 0, ATTACK: 8, DEFENCE: 0}                # the seat the client gives player id 0 (pvp.seating)
GAME = ("127.0.0.1", 7777)
RESULT_WON = bytes([1, 5]) + bytes(8) + bytes(1)        # 0x5043: won, no match type, two unread u32, no reward


class Save:
    """The saved state a game role reads: one account, one character, the saves counted."""
    def __init__(self, c):
        self.c, self.account, self.saves, self.game_sessions = c, {"id": 1, "characters": [c]}, 0, {}

    def char_by_id(self, cid):
        return self.account, self.c

    def save(self):
        self.saves += 1


class Session:
    def __init__(self):
        self.data, self.sent, self.pending = {}, [], []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))

    def run_later(self, limit=500):
        for _ in range(limit):
            if not self.pending:
                break
            self.pending.sort(key=lambda p: p[0])
            self.pending.pop(0)[1]()


def pkt(proto, body=b""):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def ask(role, s, proto, body=b""):
    before = len(s.sent)
    role.handlers[proto](s, pkt(proto, body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def only(replies, proto):
    got = [b for p, b in replies if p == proto]
    assert len(got) == 1, [(hex(p), len(b)) for p, b in replies]
    return got[0]


def coded(uid):
    """A troop uid as the client writes it in hit reports (combat.dec_uid)."""
    return bytes([obf.T2[uid >> 8], obf.T1[uid & 255]])


def login(spot, c=None):
    """A game session through its login (0x5084): the room start's four packets."""
    c = c or army(1, 2)[0]
    c.setdefault("spot", world.START_SPOT)
    st = Save(c)
    role = game.make(st, 0)
    s = Session()
    start = ask(role, s, game.C2S_GAME_LOGIN, struct.pack("<IHI", c["id"], 0, spot))
    return role, s, st, c, start


def entered(spot, c=None):
    """The same through the loading's end, its timers run (the start troops placed, the zone's troops spawned)."""
    role, s, st, c, start = login(spot, c)
    ask(role, s, game.C2S_LOAD_PROGRESS, bytes([100]))
    s.run_later()
    return role, s, st, c


def records(body):
    """0x3f4e with the flag false: obool, the 26-byte header, u16 n, n x (u16 team, u16 player, obool, u16 troops)."""
    assert body[0] == OBOOL_FALSE
    n = struct.unpack_from("<H", body, 27)[0]
    assert len(body) == 29 + 7 * n
    return body[1:27], [struct.unpack_from("<HHBH", body, 29 + 7 * k) for k in range(n)]


def structs(body):
    """0x3f4f: u16 n, n x (191 bytes, cstr name, cstr)."""
    out, at = [], 2
    for _ in range(struct.unpack_from("<H", body)[0]):
        block = body[at:at + 0xbf]
        end = body.index(0, at + 0xbf)
        name = body[at + 0xbf:end].decode("latin-1")
        at = body.index(0, end + 1) + 1
        out.append((block, name))
    assert at == len(body)
    return out


def start_troops(body):
    """0x3f50: u16 n, n entries (game.write_troop): the 40-byte T, the leader block, the two ability lists, two obools,
    the stat block."""
    out, at = [], 2
    for _ in range(struct.unpack_from("<H", body)[0]):
        t = body[at:at + 0x28]
        at += 0x28
        leader = None
        if body[at] == OBOOL_TRUE:
            leader = (struct.unpack_from("<i", body, at + 1)[0], body[at + 5])
            at += 25
        at += 1
        n = struct.unpack_from("<H", body, at)[0]
        abilities = {struct.unpack_from("<I", body, at + 3 + 5 * k)[0]: body[at + 2 + 5 * k] for k in range(n)}
        at += 2 + 5 * n
        at += 2 + 5 * struct.unpack_from("<H", body, at)[0]
        at += 2
        at += 2 + struct.unpack_from("<H", body, at)[0]
        out.append({"slot": t[0], "places": struct.unpack_from("<H", t, 1)[0], "troop": obf.dec_u32(t[3:7]),
                    "units": struct.unpack_from("<H", t, 0x19)[0], "uid": struct.unpack_from("<H", t, 0x23)[0],
                    "hp": struct.unpack_from("<H", t, 0x15)[0] << 16 | struct.unpack_from("<H", t, 0x17)[0],
                    "leader": leader, "abilities": abilities})
    assert at == len(body)
    return out


def state(body, at=0):
    """One troop state (game.write_troop_state) at body[at:]: its fields and where it ends."""
    st = body[at:at + 0x3d]
    out = {"team": struct.unpack_from("<h", st, 0)[0], "uid": struct.unpack_from("<H", st, 0x11)[0],
           "owner": struct.unpack_from("<H", st, 0x30)[0], "troop": obf.dec_u32(st[0x36:0x3a]), "level": st[0x13],
           "hp": struct.unpack_from("<H", st, 0x14)[0] << 16 | struct.unpack_from("<H", st, 0x16)[0], "flags": st[0x3c]}
    at += 0x3d
    out["np"] = body[at] == OBOOL_TRUE
    at += 1 + (22 if out["np"] else 0)
    for _ in range(2):
        at += 2 + 5 * struct.unpack_from("<H", body, at)[0]
    out["stats"] = struct.unpack_from("<H", body, at)[0]
    at += 2 + out["stats"]
    at += 2 + 1
    c = body[at:at + 17]
    x, z = obf.dec_pos_xz(c[1:5], c[7])
    out["pos"], out["units"] = (x, z), struct.unpack_from("<H", c, 0x0f)[0]
    at += 17
    if out["units"]:
        at += 2 + 5 * out["units"]
    out["end"] = at + 7
    return out


def placed(s):
    """{uid: state} of every 0x50cb the room sent (one troop each)."""
    out = {}
    for w in s.sent:
        if w.proto == game.S2C_ENTER_CELL_TROOP:
            b = bytes(w.buf)
            assert struct.unpack_from("<H", b)[0] == 1 and b[2] == OBOOL_FALSE
            st = state(b, 3)
            assert st["end"] == len(b)
            out[st["uid"]] = st
    return out


def swing(attacker, targets, action=72):
    """A hero's hit report (0x504f): its 14-byte header (the action, the leader's blow, the coded attacker troop) and
    the target list [(troop uid, [unit index])]; unit -1 is the leader."""
    head = struct.pack("<HH", action, 1) + bytes([0, 0x80]) + bytes(6) + coded(attacker)
    body = struct.pack("<H", len(targets))
    for uid, units in targets:
        body += coded(uid) + struct.pack("<H", len(units)) + b"".join(bytes([0, 0, 0, 0, k + 3, 0]) for k in units)
    return head + body


def blow(attacker, uid, units, action=72):
    """A troop's hit report (0x5053): the coded attacker at +8, its unit and action, the same target list."""
    head = bytes(8) + coded(attacker) + struct.pack("<H", 29) + bytes(1) + struct.pack("<H", action)
    return head + struct.pack("<H", 1) + coded(uid) + struct.pack("<H", len(units)) \
        + b"".join(bytes([0, 0, 0, 0, k + 3, 0]) for k in units) + bytes(2)


def fell(role, s, uid, monkeypatch):
    """Troop uid down by the player's hero (0x504f under the server's own hero-damage option, so one swing fells a
    unit): every unit and the leader; the replies of the last swing."""
    monkeypatch.setattr(combat, "HERO_DAMAGE_SCALE", 10 ** 6)
    t = s.data["battle"].troops[uid]
    got = []
    for _ in range(40):
        if combat.Battle.total(t) <= 0:
            return got
        units = [i for i, hp in enumerate(t["units"]) if hp > 0] or [combat.LEADER]
        got = ask(role, s, combat.C2S_HERO_HIT, swing(0, [(uid, units)]))
    raise AssertionError(f"troop {uid} did not fall")


# --- the tables the room is built from ---

def test_every_ai_seat_names_a_preset_the_room_can_build():
    for spot, seat in SPOTS.items():
        assert pvp.ai_room(spot) and pvp.seats(spot).index(None) == seat and len(pvp.seats(spot)) == 16
        groups = {g["StartPointID"]: g for g in zone.for_spot(spot)["PlayerStartPointInfoData"]}
        for k in range(16):                     # the zone's 16 start groups: the seat's, its team the seat's half
            assert groups[k]["LongTeamID"] == k // 8 and len(groups[k]["StartPointInfoData"]) == 9
        # the client seats a player on his team's start point number id mod 8 (0x140cd6f20): id 0 on the first,
        # the seat the table leaves him on these spots, so the room is the table's
        table, room = pvp.seats(spot), pvp.seating(spot)
        assert pvp.my_seat(spot) == ROOM[spot] == seat + pvp.start_index(game.MY_SLOT) and room == table
    assert [pvp.start_index(p) for p in (0, 1, 7, 8, 9, 15, 16, 200, 201, 207, 208, 215)] ==         [0, 1, 7, 0, 1, 7, 0, 0, 1, 7, 0, 7]
    sets = {r["AIPCTAISet_Id"] for r in tables.sections("aipctrooptable")["AIPCTroopAISet"]}
    presets = {r["AIPC_ID"]: r for r in tables.sections("aipctrooptable")["AIPCPreset"]}
    for spot in SPOTS:
        for aipc in pvp.seats(spot):
            if aipc is not None:
                # the value the player struct carries at +0xa9 is a key of %AIPCTroopAISet (the client's lookup)
                assert presets[str(aipc)]["ActiveTroopAISet"] in sets and presets[str(aipc)]["ActiveSpot"] == str(spot)
    assert not pvp.ai_room(10234) and not pvp.ai_room(10380) and pvp.seats(10234) is None


def test_an_ai_hero_is_a_character_record_from_its_table_row():
    preset = next(r for r in tables.sections("aipctrooptable")["AIPCPreset"] if r["AIPC_ID"] == "230")   # 20955 seat 0
    c = pvp.ai_char(preset)
    assert (c["class"], c["level"], c["name"]) == (0, 21, "Roger")              # Glen 102102, textnpname 63
    worn = {e["index"]: (e["code"], e["enchant"]) for e in c["equip"]}
    # Officer's Dazzling Longsword +3 on the main weapon's index, the pistol beside it, the costume on 13..17
    assert worn[0] == (105030020, 3) and worn[1] == (105030080, 0) and worn[2] == (155100020, 3)
    assert [worn[k][0] for k in (13, 14, 15, 16, 17)] == [951007600, 951007700, 951007800, 951007900, 951008000]
    assert all(items.fits_index(code, index) for index, (code, _) in worn.items())
    look = bytes.fromhex(c["look"])
    assert [obf.dec_u32(look[0x1f + 4 * k:0x23 + 4 * k]) for k in range(2)] == [1, 1]      # customize %Hair 1, %Face 1
    assert look[0x15:0x1f] == bytes([10, 0, 56, 17, 118, 16, 118, 16, 255, 255])           # a new Glen's colours
    stats = hero.char_stats(c)
    assert stats["HP_MAX"] > hero.stats(0, 21, [])["HP_MAX"]                    # the gear counts
    kit = pvp.ai_kit(c)
    used = {int(r[f"Skill{k}"]) for r in tables.sections("hero_ai")["Glen"] for k in range(1, 11)
            if r[f"Skill{k}"].isdigit()}
    assert used - {4004, 4005} <= set(kit) and 4004 not in kit                  # what his AI casts, not its combo keys
    # a level-16 hero's row names no weapon; Olivia's LOOK_GAUNTLET 59002830 is no item: both left empty
    bare = pvp.ai_char(next(r for r in tables.sections("aipctrooptable")["AIPCPreset"] if r["AIPC_ID"] == "216"))
    assert bare["class"] == 1 and not {0, 1, 16} & {e["index"] for e in bare["equip"]}


# --- the world role: 0x3e5e ---

@pytest.fixture(scope="module")
def world_role():
    return world.make(State(), 0, *GAME)


def on_world_map(c=None):
    s = WorldSession(c or char(level=30))
    s.data["game_addr"] = GAME                  # as the town entry leaves it (world.enter_town)
    return s


@pytest.mark.parametrize("spot", SPOTS)
def test_the_ai_rooms_start_answers_zero_and_names_the_game_server(world_role, spot):
    s = on_world_map()
    s.data["char"]["mission"] = {"spot": 10234, "quest": None, "back": 10350}       # left by an escaped mission
    got = ask(world_role, s, pvp.C2S_AI_START, obf.u32(spot))
    # 0x3e5f i16 0, then 0x3f41: result 0, port, ip, the spot, u8 0 (world.send_game_server)
    assert got == [(pvp.S2C_AI_START, bytes(2)),
                   (world.S2C_GAME_SERVER, struct.pack("<HH", 0, GAME[1])
                    + struct.pack("<I", int.from_bytes(socket.inet_aton(GAME[0]), "big")) + struct.pack("<IB", spot, 0))]
    assert s.data["battle_spot"] == spot and "mission" not in s.data["char"]


def test_the_start_is_refused_where_no_ai_room_can_open(world_role):
    refused = [(pvp.S2C_AI_START, struct.pack("<H", 0x402))]        # text 5036 "Cannot enter the room."
    for spot in (10380, 10234, 0):                                  # a PvP spot with no %AIPVP row, a mission, none
        s = on_world_map()
        assert ask(world_role, s, pvp.C2S_AI_START, obf.u32(spot)) == refused and "battle_spot" not in s.data
    s = WorldSession(char(level=30))                                # no town entered: no game address known
    assert ask(world_role, s, pvp.C2S_AI_START, obf.u32(FIELD)) == refused
    s = on_world_map()
    s.data["entering"] = 10234                                      # a room change under way: its 0x3f41 is to come
    assert ask(world_role, s, pvp.C2S_AI_START, obf.u32(FIELD)) == refused and "battle_spot" not in s.data
    for body in (b"", b"\x01", obf.u32(FIELD)[:3]):                 # a short body names no spot
        assert ask(world_role, on_world_map(), pvp.C2S_AI_START, body) == refused


def test_the_local_rooms_seat_and_ready_requests_keep_their_refusals(world_role):
    # the server holds no waiting room (EnterPvPAIRoom sends nothing): the seat is the spot's and 0x3e5e names only
    # the spot, so a move is refused (0x1c2d -> text 7268) and so is a ready (1)
    s = on_world_map()
    assert ask(world_role, s, 0x3e53, struct.pack("<HI", 3, 1)) == [(0x3e54, struct.pack("<H", 0x1c2d))]
    assert ask(world_role, s, 0x3e5a, b"\x01") == [(0x3e5b, struct.pack("<H", 1))]
    assert ask(world_role, s, 0x3e42, b"room\0" + bytes([1, 4, 1])) == [(0x3e43, b"")]
    assert ask(world_role, s, 0x3e61, b"room\0" + obf.u32(FIELD) + bytes([0, 1, 0])) == [(0x3e65, struct.pack("<H", 1))]


# --- the game role: the room start ---

@pytest.mark.parametrize("spot", SPOTS)
def test_the_room_start_carries_sixteen_players_fifteen_of_them_ai(spot):
    role, s, st, c, start = login(spot)
    assert [p for p, _ in start] == [game.S2C_GAME_LOGIN_RES, game.S2C_SPOT_ROOM_START, game.S2C_START_PLAYER_INFO,
                                     game.S2C_START_TROOP_INFO, game.S2C_SPOT_ROOM_START]
    assert start[4][1] == bytes([OBOOL_TRUE])                       # the go, after the three parts
    header, recs = records(start[1][1])
    me = ROOM[spot]
    # the header is the solo room's: my id in the three places, the spot
    assert struct.unpack_from("<H", header, 1)[0] == struct.unpack_from("<H", header, 0x10)[0] == game.MY_SLOT
    assert struct.unpack_from("<H", header, 0x12)[0] == game.MY_SLOT and obf.dec_u32(header[0x16:0x1a]) == spot
    assert len(recs) == 16
    deck = len(s.data["deck"])
    assert deck == min(2, int(tables.by_id("spottable")[str(spot)]["Limit_Troop_1"]))
    for seat, (team, pid, flag, count) in enumerate(recs):
        # the team is the seat's half (the zone's LongTeamID); every record brings a player struct (obool FALSE)
        assert team == seat // 8 and flag == OBOOL_FALSE
        assert (pid, count) == ((game.MY_SLOT, 1 + deck) if seat == me else (pvp.AI_PLAYER + seat, 2))
    assert len({pid for _, pid, _, _ in recs}) == 16 and all(pid < 5000 and pid != game.NP_OWNER for _, pid, _, _ in recs)
    # the client's own pick of a start point for each id is the record's seat: nobody shares one, nobody is moved
    assert [pvp.start_index(pid) for _, pid, _, _ in recs] == [seat % 8 for seat in range(16)]

    blocks = structs(start[2][1])
    assert len(blocks) == 16
    sets = {r["AIPC_ID"]: int(r["ActiveTroopAISet"]) for r in tables.sections("aipctrooptable")["AIPCPreset"]}
    keys = set()
    for seat, (block, name) in enumerate(blocks):
        flag = struct.unpack_from("<I", block, 0xa9)[0]             # -> Player +0x358 / +0x35c: the AI player's set
        keys.add(struct.unpack_from("<I", block, 0x0f)[0])
        if seat == me:
            assert flag == 0 and name == c["name"] and block == game.player_struct(c, spot, s.data["deck"].values())
        else:
            aipc = pvp.seating(spot)[seat]
            assert flag == sets[str(aipc)] and flag in (1, 2) and name == s.data["pvp"]["players"][seat]["name"]
            assert block[0xad] == OBOOL_FALSE and struct.unpack_from("<i", block, 0x01)[0] > 0      # its SP
    assert len(keys) == 16 and 0 not in keys                        # every player key its own

    entries = start_troops(start[3][1])
    assert len(entries) == sum(count for _, _, _, count in recs)
    at, uids = 0, set()
    for seat, (_, pid, _, count) in enumerate(recs):
        mine, at = entries[at:at + count], at + count
        hero_entry = mine[0]                                        # each player's first troop is his hero
        assert hero_entry["leader"] is not None and hero_entry["troop"] == game.HERO_TROOP_ID
        assert (hero_entry["slot"], hero_entry["places"]) == (0, 1) and hero_entry["abilities"]
        if seat == me:
            assert hero_entry["uid"] == 0 and hero_entry["leader"] == (c["class"], c["level"])
            assert [e["uid"] for e in mine[1:]] == sorted(s.data["deck"])
        else:
            p = s.data["pvp"]["players"][seat]
            assert hero_entry["uid"] == pid == pvp.AI_PLAYER + seat
            assert hero_entry["leader"] == (p["char"]["class"], p["char"]["level"]) and hero_entry["hp"] == p["hp"]
            assert hero_entry["abilities"] == p["kit"]
            troop = mine[1]
            assert troop["leader"] is None and troop["uid"] == pvp.AI_TROOP + 10 * seat + 1
            assert (troop["troop"], troop["units"], troop["hp"]) == \
                (p["troops"][0]["id"], p["troops"][0]["units"], p["troops"][0]["unit_hp"] * p["troops"][0]["units"])
        uids |= {e["uid"] for e in mine}
    assert len(uids) == len(entries) and max(uids) < 10000          # players' troops: below the zone's ids


def test_the_loading_end_places_every_start_troop_and_spawns_the_zone():
    role, s, st, c = entered(ATTACK)
    r = s.data["pvp"]
    assert (r["seat"], r["team"]) == (8, 1)
    cells = placed(s)
    groups = {g["StartPointID"]: g["StartPointInfoData"] for g in zone.for_spot(ATTACK)["PlayerStartPointInfoData"]}
    at = lambda seat, k: (round(groups[seat][k]["PosX"]), round(groups[seat][k]["PosZ"]))
    for p in r["players"]:
        mine = cells[p["hero"]]
        # a hero stands on his seat's start group, on the map's team; an AI player's troops carry his id
        assert mine["pos"] == at(p["seat"], 0) and mine["team"] == p["team"] and not mine["np"]
        assert mine["flags"] == game.HERO_FLAGS and mine["stats"] > 1          # his stats: the speed is one of them
        for t in p["troops"]:
            troop = cells[t["uid"]]
            assert troop["pos"] == at(p["seat"], t["slot"]) and troop["team"] == p["team"]
            if p["ai"] is not None:
                assert (troop["owner"], troop["troop"], troop["units"], troop["level"]) == \
                    (p["pid"], t["id"], t["units"], t["level"])
    assert cells[0]["pos"] == at(8, 0) and cells[0]["hp"] == s.data["battle"].troops[0]["max"]
    assert s.data["hero_pos"] == (at(8, 0)[0], 0, at(8, 0)[1])
    # the same troops again as 0x50b8 (hp, level, stats), then the zone's: every activated troop, on the map's team
    told = [state(bytes(w.buf)) for w in s.sent if w.proto == game.S2C_MISSION_TROOP_INFO]
    assert {t["uid"] for t in told} == {u for p in r["players"] for u in [p["hero"]] + [t["uid"] for t in p["troops"]]}
    live = [t for t in zone.for_spot(ATTACK)["NPCTroopInfoData"] if t.get("IsActivated") and t.get("SpawnActivated")]
    assert len(live) == 119 and all(cells[t["TroopID"]]["np"] and cells[t["TroopID"]]["team"] == t["TeamNum"]
                                    for t in live)
    assert len(s.data["battle"].troops) == 16 + 15 + len(s.data["deck"]) + len(live)
    assert [w.proto for w in s.sent].count(game.S2C_PROP_LIST) == 1
    assert c["pvp_ai"] == {"played": 1, "won": 0} and st.saves >= 1


def test_the_servers_sides_are_relative_to_the_players_team():
    # 20955 seats the player on the map's team 1: the records and status.side put his team at 0 (game.PLAYER_TEAM)
    role, s, st, c = entered(ATTACK)
    battle, r = s.data["battle"], s.data["pvp"]
    assert battle.troops[0]["c"]["team"] == 0 and status.side(s, 0) == 0
    for p in r["players"]:
        want = 0 if p["team"] == 1 else 1
        for uid in [p["hero"]] + [t["uid"] for t in p["troops"]]:
            if uid:
                assert battle.troops[uid]["c"]["team"] == want and status.side(s, uid) == want
    ally = next(t["TroopID"] for t in zone.for_spot(ATTACK)["NPCTroopInfoData"] if t["TeamNum"] == 1)
    foe = next(t["TroopID"] for t in zone.for_spot(ATTACK)["NPCTroopInfoData"] if t["TeamNum"] == 0)
    assert (battle.troops[ally]["c"]["team"], status.side(s, ally)) == (0, 0)
    assert (battle.troops[foe]["c"]["team"], status.side(s, foe)) == (1, 1)
    assert combat.np_combatant(zone.for_spot(ATTACK)["NPCTroopInfoData"][0]["TroopTableID"], 1)["team"] == 1   # the
    # shared record keeps the map's team: the room's is a copy
    # 20954 seats him on team 0: the map's numbers are the server's
    role, s, st, c = entered(FIELD)
    for p in s.data["pvp"]["players"]:
        if p["ai"] is not None:
            assert s.data["battle"].troops[p["hero"]]["c"]["team"] == p["team"] == status.side(s, p["hero"])


# --- the fight ---

def test_hits_resolve_both_ways_between_the_player_the_ai_players_and_the_zone():
    role, s, st, c = entered(FIELD)
    battle, r = s.data["battle"], s.data["pvp"]
    foe, friend = r["players"][8], r["players"][2]
    # an AI hero's swing on the player's hero (0x504f from his troop): the hero's hp falls, his number shows
    before = battle.troops[0]["hp"]
    got = ask(role, s, combat.C2S_HERO_HIT, swing(foe["hero"], [(0, [combat.LEADER])]))
    assert battle.troops[0]["hp"] < before and combat.S2C_HERO_DAMAGE in [p for p, _ in got]
    # the player's swing on that AI hero: his own hp falls (kept as his troop's leader), told by 0x505d
    before = battle.troops[foe["hero"]]["leader"]
    got = ask(role, s, combat.C2S_HERO_HIT, swing(0, [(foe["hero"], [combat.LEADER])]))
    assert 0 < battle.troops[foe["hero"]]["leader"] < before
    assert struct.unpack_from("<H", only(got, game.S2C_TROOP_HP), 1)[0] == foe["hero"]
    # an AI troop's blow on an enemy AI troop, and an enemy AI hero's swing on an allied one
    target = foe["troops"][0]["uid"]
    before = sum(battle.troops[target]["units"])
    ask(role, s, combat.C2S_HIT, blow(friend["troops"][0]["uid"], target, [0, 1]))
    assert sum(battle.troops[target]["units"]) < before
    before = battle.troops[friend["hero"]]["leader"]
    ask(role, s, combat.C2S_HERO_HIT, swing(foe["hero"], [(friend["hero"], [combat.LEADER])]))
    assert battle.troops[friend["hero"]]["leader"] < before
    # a zone troop of the other team on the player's deck troop, and the deck troop's blow on an AI hero
    tower = next(t["TroopID"] for t in zone.for_spot(FIELD)["NPCTroopInfoData"]
                 if t["TeamNum"] == 1 and t.get("IsActivated") and t["TroopTableID"] == 254030)
    before = sum(battle.troops[1]["units"])
    ask(role, s, combat.C2S_HIT, blow(tower, 1, [0]))
    assert sum(battle.troops[1]["units"]) < before
    before = battle.troops[foe["hero"]]["leader"]
    ask(role, s, combat.C2S_HIT, blow(1, foe["hero"], [combat.LEADER]))
    assert battle.troops[foe["hero"]]["leader"] < before
    # an AI hero's cast is confirmed and its execute strikes with his own record and the ability's level in his list
    ability = next(a for a in foe["kit"] if a in (164, 443, 803, 1101))        # his class's first plain swing
    use = obf.u32(ability) + bytes(7) + bytes(3) + coded(0) + struct.pack("<H", foe["hero"]) + bytes(7) + bytes(2) \
        + bytes(2)
    serial = struct.unpack_from("<H", only(ask(role, s, combat.C2S_USE_ABILITY, use), combat.S2C_USE_ABILITY), 3)[0]
    before = battle.troops[0]["hp"]
    execute = bytes(7) + struct.pack("<H", serial) + struct.pack("<H", 1) + bytes([1]) + struct.pack("<H", 0) + bytes(1)
    got = ask(role, s, combat.C2S_ABILITY_EXECUTE, execute)
    assert struct.unpack_from("<H", only(got, combat.S2C_ABILITY_EXECUTE), 3)[0] == foe["hero"]
    assert battle.troops[0]["hp"] < before


def test_an_ai_heros_fall_is_a_troops_fall_and_not_the_players_death(monkeypatch):
    role, s, st, c = entered(FIELD)
    foe = s.data["pvp"]["players"][8]
    s.sent.clear()
    got = fell(role, s, foe["hero"], monkeypatch)
    protos = [p for p, _ in got]
    assert game.S2C_DEATH_WINDOW not in protos and s.data.get("hero_deaths", 0) == 0
    assert only(got, game.S2C_KILL_FEED)[:4] == struct.pack("<HH", 0, foe["hero"])     # the feed names the kill
    assert not status.alive(s, foe["hero"]) and status.alive(s, foe["troops"][0]["uid"])
    # one enemy down decides nothing; the host's next troop report (0x50b0) looks and finds seven still standing
    assert ask(role, s, game.C2S_TROOP_SYNC, struct.pack("<H", 0)) == [] and not s.data.get("mission_won")
    # the player's own death is the room's as before: the death window, no result
    hero_t = s.data["battle"].troops[0]
    ask(role, s, combat.C2S_HERO_HIT, swing(s.data["pvp"]["players"][9]["hero"], [(0, [combat.LEADER])]))
    hero_t["hp"] = 1
    for _ in range(200):
        if hero_t["hp"] <= 0:
            break
        got = ask(role, s, combat.C2S_HERO_HIT, swing(s.data["pvp"]["players"][9]["hero"], [(0, [combat.LEADER])]))
    assert hero_t["hp"] == 0 and game.S2C_DEATH_WINDOW in [p for p, _ in got]
    assert ask(role, s, game.C2S_TROOP_SYNC, struct.pack("<H", 0)) == [] and not s.data.get("mission_won")


@pytest.mark.parametrize("spot", SPOTS)
def test_the_room_is_won_when_the_other_teams_players_are_all_down(spot, monkeypatch):
    role, s, st, c = entered(spot)
    r = s.data["pvp"]
    foes = [p for p in r["players"] if p["team"] != r["team"]]
    assert len(foes) == 8 and pvp.enemies(s) == [u for p in foes for u in (p["hero"], p["troops"][0]["uid"])]
    for uid in pvp.enemies(s)[:-1]:
        fell(role, s, uid, monkeypatch)
    assert ask(role, s, game.C2S_TROOP_SYNC, struct.pack("<H", 0)) == [] and not s.data.get("mission_won")
    saves = st.saves
    fell(role, s, pvp.enemies(s)[-1], monkeypatch)
    # ours: every hero and troop of the other team's players down -> the result at the host's next troop report
    assert ask(role, s, game.C2S_TROOP_SYNC, struct.pack("<H", 0)) == [(pvp.S2C_PVP_RESULT, RESULT_WON)]
    assert s.data["mission_won"] and c["pvp_ai"] == {"played": 1, "won": 1} and st.saves == saves + 1
    assert ask(role, s, game.C2S_TROOP_SYNC, struct.pack("<H", 0)) == []        # once
    # no reward: nothing went into the bag, no exp, no card
    assert "cards" not in s.data and c.get("exp", 0) == 0 and not c.get("bag")
    # the result window's leave (0x4040) ends at the spot the hero left for the world map
    got = ask(role, s, game.C2S_MISSION_LEAVE)
    leave = only(got, game.S2C_MISSION_LEAVE)
    assert leave[:4] == bytes([0, 0, 0, 2]) and obf.dec_u32(leave[4:8]) == world.START_SPOT == c["spot"]


def test_the_zones_own_troops_decide_nothing():
    # ours: the other team's gate, towers and garrison standing or fallen, only its eight players count
    role, s, st, c = entered(FIELD)
    battle = s.data["battle"]
    for t in zone.for_spot(FIELD)["NPCTroopInfoData"]:
        bt = battle.troops.get(t["TroopID"])
        if bt is not None and t["TeamNum"] == 1:
            bt["units"] = [0] * len(bt["units"])
    assert ask(role, s, game.C2S_TROOP_SYNC, struct.pack("<H", 0)) == [] and not s.data.get("mission_won")


# --- what stays as it was ---

def test_other_rooms_start_and_load_as_before():
    # a mission's start: one record, one struct with no AI set, and the loading's end is game.load_progress's
    role, s, st, c, start = login(10234)
    _, recs = records(start[1][1])
    assert recs == [(game.PLAYER_TEAM, game.MY_SLOT, OBOOL_FALSE, 1 + len(s.data["deck"]))] and "pvp" not in s.data
    (block, _), = structs(start[2][1])
    assert struct.unpack_from("<I", block, 0xa9)[0] == 0
    got = ask(role, s, game.C2S_LOAD_PROGRESS, bytes([100]))
    assert got[0] == (game.S2C_LOAD_PROGRESS, struct.pack("<IB", game.MY_SLOT, 100)) and s.data["started"]
    assert ask(role, s, game.C2S_TROOP_SYNC, struct.pack("<H", 0)) == [] and "pvp_ai" not in c


def test_a_short_or_junk_request_never_raises():
    role, s, st, c, _ = login(FIELD)
    assert ask(role, s, game.C2S_LOAD_PROGRESS, b"") == [(game.S2C_LOAD_PROGRESS, struct.pack("<IB", game.MY_SLOT, 0))]
    assert not s.data.get("started")
    ask(role, s, game.C2S_TROOP_SYNC, b"")                          # before the loading's end: no battle yet
    ask(role, s, game.C2S_LOAD_PROGRESS, bytes([100, 7, 7]))
    assert s.data["started"]
    assert ask(role, s, game.C2S_LOAD_PROGRESS, bytes([100]))[0][0] == game.S2C_LOAD_PROGRESS     # once only
    assert c["pvp_ai"]["played"] == 1
    for body in (b"", b"\xff", bytes(40), b"\xff" * 9):
        ask(role, s, game.C2S_TROOP_SYNC, body)
        ask(role, s, combat.C2S_HERO_HIT, swing(pvp.AI_PLAYER + 8, [(0, [combat.LEADER])]) + body)


# The hero's own revival on a %Point spot with HeroRevivalCooldown (30 on 20954-20956): the client counts it itself
# (HUDHeroInfo +0x7c = %Point +0xc: "Aldric is dead. Resurrecting in 30 seconds." and the hero bar's 30 -> 1) and the
# death window counts 0x50c6's byte; when it ends the client sends nothing (planning/agents/reports/
# 2026-11-07_pvp-hero-revival-timer.md), so the revival is the server's push: 0x505c dead FALSE closes the window.

def hero_falls(role, s):
    hero_t = s.data["battle"].troops[0]
    hero_t["hp"] = 1
    foe = s.data["pvp"]["players"][9]["hero"]
    for _ in range(200):
        got = ask(role, s, combat.C2S_HERO_HIT, swing(foe, [(0, [combat.LEADER])]))
        if hero_t["hp"] <= 0:
            return got
    raise AssertionError("the hero did not fall")


def revival_timers(s):
    return [p for p in s.pending if p[0] == 30]


def test_the_fallen_hero_comes_back_free_when_the_spots_cooldown_ends():
    role, s, st, c = entered(FIELD)
    s.pending.clear()
    got = hero_falls(role, s)
    assert only(got, game.S2C_DEATH_WINDOW) == bytes([30])          # the window counts 30 down, not "99"
    assert len(revival_timers(s)) == 1
    points = s.data.get("changetroop", {}).get("points")
    before = len(s.sent)
    revival_timers(s)[0][1]()
    back = [(w.proto, bytes(w.buf)) for w in s.sent[before:]]
    assert (game.S2C_TROOP_DOWN, bytes(5) + bytes([OBOOL_FALSE]) + bytes(2)) in back
    hero_t = s.data["battle"].troops[0]
    assert not hero_t.get("down") and hero_t["hp"] == hero_t["max"]
    assert s.data.get("changetroop", {}).get("points") == points and s.data.get("revivals", 0) == 0   # free


def test_the_cooldowns_revival_does_nothing_once_he_is_back_or_fell_again():
    role, s, st, c = entered(FIELD)
    s.pending.clear()
    hero_falls(role, s)
    first = revival_timers(s)[0][1]
    hero_t = s.data["battle"].troops[0]
    game.revive_hero(s, hero_t, game.start_pos(s))                  # back first (a paid revival, a camp revive)
    status.forget(s, 0)                                             # (the revive's 5 s invincibility over)
    hero_falls(role, s)                                             # and down again: its own timer
    before = len(s.sent)
    first()
    assert s.sent[before:] == [] and hero_t.get("down")             # the first fall's timer is spent
    revival_timers(s)[-1][1]()
    assert not hero_t.get("down")


def test_a_paid_revival_in_flight_is_left_to_finish():
    from kuf2 import changetroop
    role, s, st, c = entered(FIELD)
    s.pending.clear()
    hero_falls(role, s)
    changetroop.room(s)["revival"][0] = {"cost": 500, "at": 0}       # 0x5108 accepted, its cast running
    before = len(s.sent)
    revival_timers(s)[0][1]()
    assert s.sent[before:] == [] and s.data["battle"].troops[0].get("down")

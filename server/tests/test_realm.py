"""The realm transfer and the answers of a world with no war (server/kuf2/realm.py; planning/todo/
CONTRACT-COMPLETE-PLAN.md family 8), each through its registered handler. Reads the installed game's tables.
Run: py -m pytest -q server/tests"""
import copy
import datetime
import struct

import pytest

from kuf2 import items, obf, realm, tables, world
from kuf2.packet import Reader
from test_rewards import Session, State, char

TICKET = 351400040              # Camp Change Ticket (wartable %Realm_Trans_Cost NeedItem)
A, B = 1, 2


class Saves(State):
    saves = 0

    def save(self):
        self.saves += 1


@pytest.fixture
def served():
    st = Saves()
    role = world.make(st, 0, "127.0.0.1", 0)
    realm.make(role, st)        # world.make calls it once wired in; a second call registers the same handlers
    return role, st


def ask(role, s, proto, body=b""):
    """Send one request through the role's handler table; returns the replies it made, [(id, body)]."""
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def to(realm_id, junk=0):
    """The 0x5a46 body as the builder 0x140635c30 writes it: T2[(junk << 2 | menu - 0x32) & 0xff]."""
    return bytes([obf.T2[(junk << 2 | realm_id) & 0xff]])


def hero(in_realm=None, tickets=(), level=10):
    c = char(level)
    if in_realm:
        c["realm"] = in_realm
    c["bag"] = [dict(code=TICKET, slot=slot, count=n, serial=0x50000 + slot) for slot, n in tickets]
    return Session(c)


def test_a_transfer_takes_one_ticket_and_moves_the_character(served):
    # 0x5a47 (0x1406362b0): i16 0 + one coded byte, common+0xd0 = T1[b] & 0x80000003; the client never takes the
    # ticket itself, so the bag follows the reply (the changed slot first, then the list)
    role, st = served
    s = hero(A, tickets=[(3, 2)])
    c = s.data["char"]
    out = ask(role, s, realm.C2S_TRANSFER, to(B, junk=0x15))        # the upper six bits are stack junk
    assert [p for p, _ in out] == [realm.S2C_TRANSFER, world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert out[0][1] == bytes(2) + bytes([obf.via_t1(B)]) and obf.T1[out[0][1][2]] & 0x80000003 == B
    assert c["realm"] == B and c["bag"] == [dict(code=TICKET, slot=3, count=1, serial=0x50003)] and st.saves == 1
    out = ask(role, s, realm.C2S_TRANSFER, to(A))                   # and back, with the last ticket
    assert out[0] == (realm.S2C_TRANSFER, bytes(2) + bytes([obf.via_t1(A)]))
    assert out[1] == (world.S2C_CARGO_CHANGE, struct.pack("<H", 1) + items.record(0xffffffff, 3, 0, count=0))
    assert c["realm"] == A and c["bag"] == [] and st.saves == 2
    assert ask(role, s, realm.C2S_TRANSFER, to(B)) == [(realm.S2C_TRANSFER, struct.pack("<H", realm.TICKET_SHORT))]
    assert c["realm"] == A and st.saves == 2


@pytest.mark.parametrize("in_realm, tickets, body, code", [
    (None, [(0, 5)], to(B), 0xac06),        # never joined: "Cannot use it." (the client's own check, 0x1406354cb)
    (A, [(0, 5)], to(A), 0xac02),           # already there: "Cannot use it." (0x1406354f3)
    (B, [(0, 5)], to(B), 0xac02),
    (A, [], to(B), 0x445),                  # "Insufficient %1%. Available in the Diamond Shop under 'Cubic Shop'."
    (A, [(0, 5)], bytes([obf.T2[3]]), 1),   # no menu sends realm 3 or 0: the client only logs it
    (A, [(0, 5)], bytes([obf.T2[0x40]]), 1),
    (A, [(0, 5)], b"", 1),
])
def test_a_refused_transfer_changes_nothing(served, in_realm, tickets, body, code):
    # every non-zero 0x5a47 is 2 bytes: the realm byte is read only on 0 (0x1406362b0)
    role, st = served
    s = hero(in_realm, tickets)
    before = copy.deepcopy(s.data["char"])
    assert ask(role, s, realm.C2S_TRANSFER, body) == [(realm.S2C_TRANSFER, struct.pack("<H", code))]
    assert s.data["char"] == before and st.saves == 0


def test_a_guild_member_cannot_switch_camp(served):
    # "Cannot switch camp while in a guild." (0xac07 -> text 0x1dde); the client refuses first when its guild window
    # knows the guild (0x140635518: scene 0x20 +0x145). The guild is c["guild"] (guild.py); leaving it frees the way
    role, st = served
    s = hero(A, tickets=[(0, 1)])
    c = s.data["char"]
    c["guild"] = {"id": 1, "name": "Alone"}
    assert ask(role, s, realm.C2S_TRANSFER, to(B)) == [(realm.S2C_TRANSFER, struct.pack("<H", 0xac07))]
    assert ask(role, s, realm.C2S_TRANSFER, to(A)) == [(realm.S2C_TRANSFER, struct.pack("<H", 0xac02))]   # its order
    assert c["realm"] == A and realm.held(c, TICKET) == 1 and st.saves == 0
    del c["guild"]
    assert ask(role, s, realm.C2S_TRANSFER, to(B))[0] == (realm.S2C_TRANSFER, bytes(2) + bytes([obf.via_t1(B)]))


def test_the_cost_is_the_war_tables_row_for_the_hero_level(served):
    # wartable %Realm_Trans_Cost: 50 rows, LV 1..50, each 1 x 351400040 (item_consume REALM_CHANGE "Camp Change
    # Ticket"); the client looks the row up by level (0x1418b9980) and, finding none, asks box 0x1ddb without a cost
    assert realm.transfer_costs() == {lv: (TICKET, 1) for lv in range(1, 51)}
    assert items.row(TICKET)["ConsumeItemType"] == "REALM_CHANGE" and items.name(TICKET) == "Camp Change Ticket"
    # the game gives one: each class's Level-up Celebration Chest [Lv 30], the end of the chain a new hero starts with
    for chest in (600000106, 600000206, 600000306, 600000406, 600000506):
        assert (TICKET, 1) in items.open_container(chest, lambda n: 0)[1], chest
    assert realm.transfer_cost(50) == (TICKET, 1) and realm.transfer_cost(51) is None
    role, st = served
    s = hero(A, level=51)
    assert ask(role, s, realm.C2S_TRANSFER, to(B)) == [(realm.S2C_TRANSFER, bytes(2) + bytes([obf.via_t1(B)]))]
    assert s.data["char"]["realm"] == B and st.saves == 1


def test_a_cost_of_several_is_taken_from_the_last_stacks_first(served, monkeypatch):
    role, st = served
    monkeypatch.setattr(realm, "transfer_costs", lambda: {10: (TICKET, 3)})
    s = hero(A, tickets=[(2, 2), (7, 2)])
    s.data["char"]["bag"].append(dict(code=350000010, slot=4, count=9, serial=0x60004))
    assert ask(role, hero(A, tickets=[(2, 2)]), realm.C2S_TRANSFER, to(B))[0][1] == struct.pack("<H", 0x445)
    out = ask(role, s, realm.C2S_TRANSFER, to(B))
    assert out[0][1][:2] == bytes(2) and struct.unpack_from("<H", out[1][1])[0] == 2       # both slots redrawn
    left = [(it["code"], it["slot"], it["count"]) for it in s.data["char"]["bag"]]
    assert left == [(TICKET, 2, 1), (350000010, 4, 9)]


NO_WAR = {      # request: (reply, body hex): the bytes on the wire, written out
    0x10f7: (0x10f8, "00" * 0x18 + "04" + "00" * 0x10),
    0x10fc: (0x10fd, "04a4"), 0x10fe: (0x10ff, "04a4"), 0x1100: (0x1101, "04a4"), 0x1115: (0x1116, "04a4"),
    0x1102: (0x1103, "01" + "00" * 9),
    0x1104: (0x1105, "0100"), 0x1108: (0x1109, "0100"), 0x110a: (0x110b, "0100"),
    0x111a: (0x111b, "0100"), 0x111c: (0x111d, "0100"), 0x111e: (0x111f, "00000000"),
    0x1260: (0x1261, "1644"), 0x1262: (0x1263, "010000"),
    0x5a40: (0x5a41, "0100"), 0x5a42: (0x5a43, "0000"),
}


@pytest.mark.parametrize("request_id", sorted(NO_WAR))
def test_no_war_and_no_capture_is_answered(served, request_id):
    role, _ = served
    reply, body = NO_WAR[request_id]
    assert ask(role, hero(A), request_id, bytes(9)) == [(reply, bytes.fromhex(body))]


def test_the_no_war_answers_are_never_shorter_than_their_handlers_read(served):
    r = {req: body for req, (_, body) in realm.WAR_REPLIES.items()}
    assert set(r) == set(NO_WAR)
    # 0x10f8: one 0x29-byte read; the phase byte at +0x18 is 4, WarManager's constructed value (0x140a7ca80): no
    # period label (0 would be the "[Base Establishment Period]"), and every time is 0
    assert len(r[0x10f7]) == 0x29 and r[0x10f7][0x18] == 4 and not any(r[0x10f7][:0x18] + r[0x10f7][0x19:])
    # 0x1103 has no result code: obool false (unoccupied; T1[b] & 1), u64, then the one byte of the false branch
    assert len(r[0x1102]) == 10 and obf.T1[r[0x1102][0]] & 1 == 0
    assert len(r[0x111e]) == 4 and struct.unpack_from("<h", r[0x111e])[0] == 0          # state 0: the poll stops
    assert r[0x5a42] == bytes(2)        # u8 grade (read unchecked), u8 n = 0: text 0x1df2, the window closes
    # every other reply is a refusal: a non-zero i16, so no handler goes on to read a success block
    for req in set(r) - {0x10f7, 0x1102, 0x111e, 0x5a42}:
        assert len(r[req]) >= 2 and struct.unpack_from("<H", r[req])[0] != 0, hex(req)
    assert len(r[0x1262]) == 3          # 0x1263 reads its list count after any result
    # the codes with a text of the client's own: WarManager's mapper 0x140a80620 and the capture window's 0x1405c4bb0
    assert struct.unpack("<H", r[0x1100])[0] == 0xa404 and struct.unpack("<H", r[0x1260])[0] == 0x4416


def test_all_eighteen_requests_of_the_family_have_their_end(served):
    role, _ = served
    family = [0x10f7, 0x10fc, 0x10fe, 0x1100, 0x1102, 0x1104, 0x1108, 0x110a, 0x1115, 0x111a, 0x111c, 0x111e, 0x1106,
              0x1260, 0x1262, 0x5a40, 0x5a42, 0x5a46]
    assert len(set(family)) == 18 and all(req in role.handlers for req in family)
    assert role.handlers[realm.C2S_TRANSFER].__name__ == "transfer"
    assert role.handlers[0x1106].__name__ == "ignored"          # no 0x1107 exists in the client: world.py's ignore
    assert ask(role, hero(A), 0x1106, bytes(9)) == []
    assert sorted(set(family) - {0x1106, realm.C2S_TRANSFER}) == sorted(realm.WAR_REPLIES)


def test_the_shipped_tables_leave_no_war_capture_or_reward_to_reach():
    """The facts the DEAD verdicts rest on (the report's section 2); a data change that opens one fails here."""
    war = tables.sections("wartable")
    # the four seasons ended a year before this build's service began (Gameforge launch 2019-11-14)
    ends = [datetime.datetime.strptime(r["StartDate"], "%Y%m%d").date()
            + datetime.timedelta(weeks=int(r["HowManyWeeks"])) for r in war["Season"]]
    assert len(ends) == 4 and max(ends) == datetime.date(2018, 10, 7) < datetime.date(2019, 11, 14)
    # the weekly cycle the client labels phases 0..3; phase 4 is what is left of the week (3 h of 10,080 min)
    phase = war["Phase"][0]
    assert [int(phase[f"Duration{k}"]) for k in (1, 2, 3, 4)] == [4320, 4320, 1020, 240]
    quests = {r["ID"]: r for r in tables.sections("questtable")["QuestTable"]}
    npcs = tables.sections("npctable")["NpcTable"]
    menus = [(r["ID"], r[f"MENU_TYPE{k}"], r[f"MENU_VALUE{k}"]) for r in npcs for k in range(1, 6)]
    # the war reward window 0x5a opens from NPC menu WAR_REWARD only (MenuOpen 0x140ea0730 case 0x2a): no NPC has it
    assert not [m for m in menus if m[1] == "WAR_REWARD"]
    # the Fortress Conquest window 0x4d opens from FIELD_PK_APPLICATION only (case 0x25): one NPC, never spawned
    assert [m for m in menus if m[1] == "FIELD_PK_APPLICATION"] == [("944", "FIELD_PK_APPLICATION", "20906")]
    karon = next(r for r in npcs if r["ID"] == "944")
    assert (karon["Npc_Spawn_Show"].strip(), karon["Npc_Spawn_Show_Value"]) == ("FinishedQuest", "1")
    assert quests["1"]["Use_Quest"] == "No"
    # the War Info map opens once tutorial War_RvR3's quest is finished (0x140833eb0 -> 0x140834040); the client
    # counts a tutorial done without it only when its quest row is missing or AcquireLevel is 100
    tutorials = {r["TutorialQuestType"]: r["QuestId"] for r in tables.sections("tutorialquest")["TutorialQuest"]}
    for kind in ("War_RvR1", "War_RvR2", "War_RvR3"):
        q = quests[tutorials[kind]]
        assert q["Use_Quest"] == "No" and q["AcquireLevel"] != "100", kind
    assert tutorials["War_RvR3"] == "1160455"
    # the realm NPCs offer the transfer, and no quest depends on which realm: 3 = either
    assert sorted(m[0] for m in menus if m[1] == "REALM_TRANS_A") == ["6235", "963", "99"]
    realm_values = {r[f"{col}{n}_{val}"] for r in quests.values()
                    for col, val, count in (("Require", "Value", 3), ("Complete", "ID1", 5))
                    for n in range(1, count + 1) if r.get(f"{col}{n}_Type") == "Realm"}
    assert realm_values == {"3"}

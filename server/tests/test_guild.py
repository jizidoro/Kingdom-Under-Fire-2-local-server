"""Family 3 of planning/todo/CONTRACT-COMPLETE-PLAN.md, the guild (server/kuf2/guild.py): a guild of one kept in the
save, each of the 30 answered requests through its registered handler (0x3d4c, the answer to an invitation nobody can
send, stays world.py's ignore); the reply's bytes and the saved state. Reads the installed game's tables.
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import guild, obf, tables, world
from kuf2.net import Role
from kuf2.packet import OBOOL_TRUE, Reader

FAMILY = (0x3d40, 0x3d42, 0x3d44, 0x3d46, 0x3d48, 0x3d4c, 0x3d4e, 0x3d51, 0x3d53, 0x3d57, 0x3d59, 0x3d5d, 0x3d5f,
          0x3d62, 0x3d64, 0x3d66, 0x3d69, 0x3d6b, 0x3d6d, 0x3d6f, 0x3d71, 0x3d73, 0x3d76, 0x3d78, 0x3d7b, 0x3d7d,
          0x3d82, 0x3d84, 0x3d87, 0x3d8c, 0x3d91)
NOW = 1_800_000_000
FORM = 351400030                # Guild Name Change Form (ConsumeItemType GUILD_NAME)
COIN = 760000110                # Tier 1 Hero Coins: %Guild_ItemSale's Guild_Item of 617200001
COIN_GOODS, POINT_GOODS = 617200001, 351300360          # Type Item (a week) and Type Point (1,500,000, a day)


class Session:
    def __init__(self, account, c):
        self.data = {"char": c, "account": account}
        self.sent, self.pending = [], []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


class State:
    """The save's shape: one account, its two characters."""
    def __init__(self):
        self.aldric = {"id": 1, "name": "Aldric", "class": 0, "level": 30, "gold": 25_000, "realm": 1, "spot": 10001,
                       "bag": [], "quests": {"active": {}, "done": []}}
        self.qwe = {"id": 2, "name": "qwe123", "class": 3, "level": 6, "gold": 50_000, "realm": 1, "spot": 10001,
                    "bag": [], "quests": {"active": {}, "done": []}}
        self.account = {"id": 1, "characters": [self.aldric, self.qwe]}
        self.game_sessions, self.world_sessions, self.saves = {}, {}, 0

    def save(self):
        self.saves += 1


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(guild.time, "time", lambda: NOW)
    state = State()
    role = Role("world", 0, state)
    guild.make(role, state)
    return role, state, Session(state.account, state.aldric)


def ask(role, s, proto, body=b""):
    """One request through the role's handler table; the replies it made, [(id, body)]."""
    before = len(s.sent)
    role.handlers[proto](s, Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body))
    return [(w.proto, bytes(w.buf)) for w in s.sent[before:]]


def cstr(text):
    return text.encode("latin-1") + b"\0"


def code(n):
    return struct.pack("<H", n)


def found(role, s, name="Ironwood"):
    assert ask(role, s, guild.C2S_CREATE, cstr(name))[0] == (guild.S2C_CREATE, bytes(2) + struct.pack("<I", 1))
    return s.data["char"]["guild"]


def test_every_request_of_the_family_has_its_handler_but_the_invitation_answer(server):
    role = server[0]
    assert sorted(role.handlers) == sorted(set(FAMILY) - {0x3d4c})


def test_the_rights_go_once_a_session_because_a_second_one_prints_a_change(server):
    """0x1405dc870 prints "Title authority setting has been changed." whenever its masks are already set: sent with
    every 0x3d41, the native window printed it at each open (2026-11-05). A real change still goes, and so do the
    masks of a guild founded again."""
    role, state, s = server
    g = found(role, s)
    pushes = lambda: [w for w in s.sent if w.proto == guild.S2C_RIGHTS_PUSH]
    ask(role, s, guild.C2S_INFO)
    assert len(pushes()) == 1
    ask(role, s, guild.C2S_INFO)
    assert len(pushes()) == 1
    ask(role, s, guild.C2S_RIGHTS, struct.pack("<5i", 1, 0, 0x1ff, 0b101, 0b11))
    assert len(pushes()) == 2
    ask(role, s, guild.C2S_INFO)
    assert len(pushes()) == 2
    assert ask(role, s, guild.C2S_DISMISS) == [(guild.S2C_DISMISS, bytes(2))]
    assert found(role, s) is not g and s.data["char"]["guild"]["id"] == g["id"]      # the id is the founder's: it comes back
    ask(role, s, guild.C2S_INFO)
    assert len(pushes()) == 3


def test_a_days_guild_points_stop_at_the_limit_the_window_prints(server, monkeypatch):
    """The guild window prints "Can earn up to 10,000 points a day" over its Daily Points bar, which read 0/0 with the
    limit unsent (native, 2026-11-05). The contribution and the guild exp are not points and go on; the next game
    day starts again."""
    role, state, s = server
    g = found(role, s)
    c = s.data["char"]
    assert guild.earn(s, state, point=9_900) is True
    assert guild.earn(s, state, exp=5, point=300, gift=7) is True
    assert g["point"] == 10_000 and guild.contribution(c) == 7
    assert ask(role, s, guild.C2S_POINTS) == [(guild.S2C_POINTS, bytes(2) + struct.pack("<QQQ", 10_000, 7, 10_000))]
    before = len(s.sent)
    assert guild.earn(s, state, point=50) is False and len(s.sent) == before     # spent: nothing to add, nothing said
    assert g["point"] == 10_000
    monkeypatch.setattr(guild.time, "time", lambda: NOW + 86_400)
    assert guild.earn(s, state, point=50) is True
    assert g["point"] == 10_050
    assert ask(role, s, guild.C2S_POINTS) == [(guild.S2C_POINTS, bytes(2) + struct.pack("<QQQ", 50, 7, 10_000))]


def test_without_a_guild_the_windows_get_what_the_constants_gave(server):
    role, state, s = server
    assert ask(role, s, guild.C2S_INFO) == [(guild.S2C_INFO, code(0x5405))]             # ignored by 0x1405d7d40
    assert ask(role, s, guild.C2S_MEMBERS) == [(guild.S2C_MEMBERS, code(0x5405))]
    assert ask(role, s, guild.C2S_APPLICANTS) == [(guild.S2C_APPLICANTS, code(0x5415))]  # silent, every window open
    assert ask(role, s, guild.C2S_POINTS) == [(guild.S2C_POINTS, bytes(26))]
    assert ask(role, s, guild.C2S_SKILLS) == [(guild.S2C_SKILLS, code(0x5415))]
    assert ask(role, s, guild.C2S_SEARCH, b"\0") == [(guild.S2C_SEARCH, bytes(4))]
    # a ranking success without a row reads a null vector (0x1405e42a8): an error code, never an empty list
    assert ask(role, s, guild.C2S_RANKING, struct.pack("<I", 1)) == [(guild.S2C_RANKING, code(0x5415))]
    assert ask(role, s, guild.C2S_RANKING_FIND, cstr("x")) == [(guild.S2C_RANKING_FIND, code(0x5415))]
    assert ask(role, s, guild.C2S_DISMISS) == [(guild.S2C_DISMISS, code(0x5405))]
    assert ask(role, s, guild.C2S_LEAVE) == [(guild.S2C_LEAVE, code(0x5405))]
    assert ask(role, s, guild.C2S_INVITE, cstr("qwe123")) == [(guild.S2C_INVITE, code(0x5405))]
    assert ask(role, s, guild.C2S_LEARN, struct.pack("<I", 1)) == [(guild.S2C_LEARN, code(0x5405) + struct.pack("<I", 1))]
    assert ask(role, s, guild.C2S_RESET) == [(guild.S2C_RESET, code(0x5405) + bytes(4))]
    assert guild.name_of(s.data["char"]) == "" and guild.contribution(s.data["char"]) == 0 and state.saves == 0


def test_creating_a_guild_costs_the_settings_10000_gold_and_makes_its_founder_the_master(server):
    role, state, s = server
    c = s.data["char"]
    out = ask(role, s, guild.C2S_CREATE, cstr("Ironwood"))
    # 0x3d45 (0x1405d8fd0): i16 0, u32; then the gold the client does not take itself (0x1658)
    assert out == [(guild.S2C_CREATE, bytes(2) + struct.pack("<I", 1)), (world.S2C_GOLD, obf.u40(15_000))]
    g = c["guild"]
    assert c["gold"] == 15_000 and state.saves >= 1
    assert (g["id"], g["name"], g["level"], g["exp"], g["point"], g["contribution"]) == (1, "Ironwood", 1, 0, 0, 0)
    assert g["cap"] == 20 and g["created"] == NOW and g["skills"] == [] and g["shop"] == {}
    # %Guild_Grade: SubMaster all but Banish ... Novice only Invite (bit = the Flash AUTH_* index)
    assert g["rights"] == [0b111111110, 0b001111000, 0b001101000, 0b001001000, 0b001000000]
    assert guild.name_of(c) == "Ironwood"
    assert ask(role, s, guild.C2S_CREATE, cstr("Second")) == [(guild.S2C_CREATE, code(0x5404))]     # already a member
    # one guild an account (text 53288): the other character is told so
    other = Session(state.account, state.qwe)
    assert ask(role, other, guild.C2S_CREATE, cstr("Second")) == [(guild.S2C_CREATE, code(0x5402))]
    assert "guild" not in state.qwe and state.qwe["gold"] == 50_000


@pytest.mark.parametrize("change,name", [({"gold": 9_999}, "Ironwood"), ({"realm": 0}, "Ironwood"), ({}, "I"),
                                         ({}, "Iron wood"), ({}, "I" * 21), ({}, None)])
def test_what_the_client_refuses_before_sending_is_refused_here_too(server, change, name):
    role, state, s = server
    c = s.data["char"]
    c.update(change)
    gold = c["gold"]
    body = b"no terminator" if name is None else cstr(name)
    assert ask(role, s, guild.C2S_CREATE, body) == [(guild.S2C_CREATE, code(0x5401))]
    assert "guild" not in c and c["gold"] == gold and state.saves == 0


def test_my_guild_is_the_block_the_client_reads_and_the_rights_follow_it(server):
    role, state, s = server
    g = found(role, s)
    g.update(level=3, exp=1234, point=777_000, cap=24, memo="Hello", memo_at=NOW - 60, info="Join us", info_at=NOW - 30,
             skills=[2, 100])
    (reply, body), (push, rights) = ask(role, s, guild.C2S_INFO)
    assert (reply, push) == (guild.S2C_INFO, guild.S2C_RIGHTS_PUSH) and body[:2] == bytes(2)
    b = body[2:2 + 0x3e]
    assert b[0] == 3 and struct.unpack_from("<h", b, 5)[0] == 24                    # level, member cap
    assert struct.unpack_from("<Q", b, 7)[0] == 0                                    # war points
    assert struct.unpack_from("<I", b, 0xf)[0] == 1                                  # guild id
    assert struct.unpack_from("<Q", b, 0x13)[0] == 777_000                           # guild points
    assert struct.unpack_from("<Q", b, 0x1b)[0] == 1234                              # exp
    assert obf.dec_time64(b[0x23:0x2b]) == NOW - 60 and obf.dec_time64(b[0x36:0x3e]) == NOW - 30
    assert struct.unpack_from("<I", b, 0x2b)[0] == 17 - 2 - 1                        # skill points left
    assert struct.unpack_from("<h", b, 0x2f)[0] == 1                                 # members
    assert struct.unpack_from("<I", b, 0x31)[0] == s.data["char"]["id"]             # the master: me
    assert body[2 + 0x3e:] == b"Ironwood\0Aldric\0Hello\0Join us\0"
    # 0x3d90 (0x1405dc870): Regular, Novice, SubMaster, Senior, Captain
    assert rights == struct.pack("<5i", 0b001001000, 0b001000000, 0b111111110, 0b001101000, 0b001111000)
    assert guild.info_body(s.data["char"], guild.new(s.data["char"], "A"))[0x23:0x2b] == obf.time64(0)


def test_the_member_list_holds_the_master_alone(server):
    role, state, s = server
    found(role, s)
    (reply, body), = ask(role, s, guild.C2S_MEMBERS)
    assert reply == guild.S2C_MEMBERS and body[:4] == bytes(2) + struct.pack("<H", 1)
    rec = body[4:4 + 0x18]
    assert struct.unpack_from("<I", rec)[0] == 1 and obf.dec_u32(rec[4:8]) == 10001      # id, spot
    assert rec[8] == 0 and rec[9] == OBOOL_TRUE                                           # master, online
    assert rec[0x12] == 30 and struct.unpack_from("<I", rec, 0x14)[0] == 0                # level, class
    assert body[4 + 0x18:] == b"Aldric\0"


def test_the_notice_and_the_recruitment_text_are_kept_with_their_time(server):
    role, state, s = server
    g = found(role, s)
    assert ask(role, s, guild.C2S_MEMO, cstr("Raid at nine\nBring potions")) == [
        (guild.S2C_MEMO, bytes(2) + obf.time64(NOW)), (guild.S2C_MEMO_CHANGED, b"")]
    assert ask(role, s, guild.C2S_NOTE, cstr("We take everyone")) == [
        (guild.S2C_NOTE, bytes(2) + obf.time64(NOW)), (guild.S2C_NOTE_CHANGED, b"")]
    assert (g["memo"], g["memo_at"], g["info"], g["info_at"]) == ("Raid at nine\nBring potions", NOW,
                                                                 "We take everyone", NOW)
    assert ask(role, s, guild.C2S_INFO)[0][1].endswith(b"Ironwood\0Aldric\0Raid at nine\nBring potions\0We take everyone\0")
    # a text arrives byte for byte (UTF-8 from the client) and goes back so
    raw = "Привет".encode("utf-8")
    ask(role, s, guild.C2S_MEMO, raw + b"\0")
    assert g["memo"].encode("latin-1") == raw
    assert ask(role, s, guild.C2S_MEMO, b"x" * 3000 + b"\0") == [(guild.S2C_MEMO, code(0x5401))]
    assert ask(role, s, guild.C2S_NOTE, b"no terminator") == [(guild.S2C_NOTE, code(0x5401))]


def test_the_join_request_switch_is_kept_and_sent_with_the_empty_applicant_list(server):
    role, state, s = server
    g = found(role, s)
    assert ask(role, s, guild.C2S_APPLICANTS) == [(guild.S2C_APPLICANTS, bytes(2) + b"\0" + bytes(2))]
    assert ask(role, s, guild.C2S_PREVENT, b"\x01") == [(guild.S2C_PREVENT, bytes(2))] and g["prevent"] is True
    assert ask(role, s, guild.C2S_APPLICANTS) == [(guild.S2C_APPLICANTS, bytes(2) + b"\x01" + bytes(2))]
    assert ask(role, s, guild.C2S_PREVENT, b"\x00") == [(guild.S2C_PREVENT, bytes(2))] and g["prevent"] is False


def test_the_ranking_and_the_search_hold_this_guild_and_never_an_empty_success(server):
    role, state, s = server
    g = found(role, s)
    g["point"] = 4321
    row = struct.pack("<IIIQ", 1, 1, 1, 4321) + b"Ironwood\0"       # row number, members, rank, points; name
    assert ask(role, s, guild.C2S_RANKING, struct.pack("<I", 1)) == [
        (guild.S2C_RANKING, bytes(2) + struct.pack("<IH", 1, 1) + row)]
    assert ask(role, s, guild.C2S_RANKING_FIND, cstr("iron")) == [
        (guild.S2C_RANKING_FIND, bytes(2) + struct.pack("<IH", 1, 1) + row)]
    assert ask(role, s, guild.C2S_RANKING_FIND, cstr("Nobody")) == [(guild.S2C_RANKING_FIND, code(0x5415))]
    # 0x3d65 (0x1405e6290): cap, 4 unread bytes, id, level, members, "takes no requests"; master name, guild name
    entry = struct.pack("<h", 20) + bytes(4) + struct.pack("<I", 1) + b"\x01" + struct.pack("<h", 1) + b"\0"
    assert ask(role, s, guild.C2S_SEARCH, b"\0") == [
        (guild.S2C_SEARCH, bytes(2) + struct.pack("<H", 1) + entry + b"Aldric\0Ironwood\0")]
    assert ask(role, s, guild.C2S_SEARCH, cstr("zzz")) == [(guild.S2C_SEARCH, bytes(4))]
    g.update(prevent=True, info="We take everyone")
    assert ask(role, s, guild.C2S_SEARCH, cstr("WOOD"))[0][1][2 + 2 + 0xd] == 1
    # the detail popup (0x1405e3890): 12 unread bytes and the recruitment text; an unknown id is ignored by the handler
    assert ask(role, s, guild.C2S_DETAIL, struct.pack("<I", 1)) == [
        (guild.S2C_DETAIL, bytes(2) + struct.pack("<I", 1) + bytes(8) + b"We take everyone\0")]
    assert ask(role, s, guild.C2S_DETAIL, struct.pack("<I", 9)) == [(guild.S2C_DETAIL, code(0x5407))]


def test_what_needs_a_second_player_gets_the_originals_nobody_there(server):
    role, state, s = server
    found(role, s)
    # an invitation by name: "The player is not valid." (0x0412 -> text 7076), and the pending request is cleared
    assert ask(role, s, guild.C2S_INVITE, cstr("Somebody")) == [(guild.S2C_INVITE, code(0x0412))]
    assert ask(role, s, guild.C2S_INVITE, cstr("qwe123")) == [(guild.S2C_INVITE, code(0x0412))]
    assert ask(role, s, guild.C2S_KICK, struct.pack("<I", 2)) == [(guild.S2C_KICK, code(0x5405))]
    assert ask(role, s, guild.C2S_GRADE, b"\x01" + struct.pack("<I", 2)) == [(guild.S2C_GRADE, code(0x5405))]
    assert ask(role, s, guild.C2S_LEAVE) == [(guild.S2C_LEAVE, code(0x5401))]            # a master dismisses
    assert ask(role, s, guild.C2S_MY_REQUESTS) == [(guild.S2C_MY_REQUESTS, code(0x5415))]
    # the replies that always read i16 + u32 carry the request's u32 back
    assert ask(role, s, guild.C2S_ACCEPT, struct.pack("<I", 7)) == [(guild.S2C_ACCEPT, code(0x5405) + struct.pack("<I", 7))]
    assert ask(role, s, guild.C2S_REFUSE, struct.pack("<I", 7)) == [(guild.S2C_REFUSE, code(0x5405) + struct.pack("<I", 7))]
    assert ask(role, s, guild.C2S_WITHDRAW, struct.pack("<I", 1)) == [(guild.S2C_WITHDRAW, code(0x5407) + struct.pack("<I", 1))]
    assert ask(role, s, guild.C2S_ACCEPT) == [(guild.S2C_ACCEPT, code(0x5405) + bytes(4))]      # never under 6 bytes
    assert ask(role, s, guild.C2S_JOIN, struct.pack("<I", 1)) == [(guild.S2C_JOIN, code(0x5404) + struct.pack("<I", 1))]
    # the account's other character sees the guild and is told why it cannot ask to join (text 53288)
    other = Session(state.account, state.qwe)
    assert ask(role, other, guild.C2S_SEARCH, b"\0")[0][1][:4] == bytes(2) + struct.pack("<H", 1)
    assert ask(role, other, guild.C2S_JOIN, struct.pack("<I", 1)) == [(guild.S2C_JOIN, code(0x5402) + struct.pack("<I", 1))]
    assert "guild" not in state.qwe
    lone = Session({"id": 2, "characters": [state.qwe]}, state.qwe)
    assert ask(role, lone, guild.C2S_JOIN, struct.pack("<I", 1)) == [(guild.S2C_JOIN, code(0x5407) + struct.pack("<I", 1))]


def test_a_quest_handed_in_pays_the_guild_its_three_columns(server):
    role, state, s = server
    c = s.data["char"]
    quest = next(r for r in tables.by_id("questtable").values() if r["Guild_Exp"] == "330")
    assert (quest["Guild_Point"], quest["Guild_Contribution"]) == ("330", "330")
    assert guild.on_quest(s, state, quest) is False and s.sent == []                  # no guild: nothing
    g = found(role, s)
    before, saves = len(s.sent), state.saves
    assert guild.on_quest(s, state, quest) is True
    assert (g["exp"], g["point"], g["contribution"], g["level"]) == (330, 330, 330, 1) and state.saves == saves + 1
    assert [(w.proto, bytes(w.buf)) for w in s.sent[before:]] == [
        (guild.S2C_LEVEL, struct.pack("<IBQ", 1, 1, 330)),                            # 0x3d7a: level, exp
        (guild.S2C_GUILD_POINTS, struct.pack("<IQQ", 1, 330, 0)),                     # 0x3d56: the guild's points
        (guild.S2C_EARNED, struct.pack("<II", 330, 0)),                               # 0x3d5b: "acquired 330"
        (guild.S2C_POINTS_PUSH, struct.pack("<QQQ", 330, 330, 10_000))]               # 0x3d75: today, mine, the limit
    assert ask(role, s, guild.C2S_POINTS) == [(guild.S2C_POINTS, bytes(2) + struct.pack("<QQQ", 330, 330, 10_000))]
    assert guild.contribution(c) == 330
    assert guild.on_quest(s, state, {"Guild_Exp": "0", "Guild_Point": "-", "Guild_Contribution": ""}) is False


def test_guild_exp_fills_the_levels_of_lvexptable(server):
    role, state, s = server
    g = found(role, s)
    assert guild.exp_table()[1] == 960_000 and guild.exp_table()[2] == 1_710_000 and 10 not in guild.exp_table()
    guild.earn(s, state, exp=959_999)
    assert (g["level"], g["exp"]) == (1, 959_999)
    guild.earn(s, state, exp=11)
    assert (g["level"], g["exp"]) == (2, 10)
    assert (s.sent[-1].proto, bytes(s.sent[-1].buf)) == (guild.S2C_LEVEL, struct.pack("<IBQ", 1, 2, 10))
    guild.earn(s, state, exp=10 ** 12)                                                # past the last level: none left
    assert (g["level"], g["exp"]) == (10, 0)
    sent = len(s.sent)
    guild.earn(s, state, exp=500)
    assert (g["level"], g["exp"]) == (10, 0) and len(s.sent) == sent


def test_more_members_cost_the_population_rows_guild_points(server):
    role, state, s = server
    g = found(role, s)
    body = struct.pack("<II", 1, 22)
    assert ask(role, s, guild.C2S_MORE_MEMBERS, body) == [(guild.S2C_MORE_MEMBERS, code(0x5418))] and g["cap"] == 20
    g["point"] = 250_000
    assert ask(role, s, guild.C2S_MORE_MEMBERS, body) == [
        (guild.S2C_MORE_MEMBERS, bytes(2)), (guild.S2C_GUILD_POINTS, struct.pack("<IQQ", 1, 150_000, 0))]
    assert (g["cap"], g["point"]) == (22, 150_000)                                    # 20 -> 22: 100,000
    assert ask(role, s, guild.C2S_MORE_MEMBERS, body)[0] == (guild.S2C_MORE_MEMBERS, bytes(2))
    assert (g["cap"], g["point"]) == (24, 40_000)                                     # 22 -> 24: 110,000
    g.update(cap=60, point=10 ** 9)
    assert ask(role, s, guild.C2S_MORE_MEMBERS, body) == [(guild.S2C_MORE_MEMBERS, code(0x5401))]
    assert (g["cap"], g["point"]) == (60, 10 ** 9)


def learn(role, s, skill):
    return ask(role, s, guild.C2S_LEARN, struct.pack("<I", skill))


def test_guild_skills_are_learned_a_level_at_a_time_for_guild_points(server):
    role, state, s = server
    g = found(role, s)
    assert learn(role, s, 1) == [(guild.S2C_LEARN, code(0x5418) + struct.pack("<I", 1))]         # 250,000 a level 1
    g["point"] = 1_000_000
    assert learn(role, s, 1)[:2] == [(guild.S2C_LEARN, bytes(2) + struct.pack("<I", 1)),     # then the hero's block
                                     (guild.S2C_GUILD_POINTS, struct.pack("<IQQ", 1, 750_000, 0))]  # (test_guildfx)
    assert learn(role, s, 3)[0] == (guild.S2C_LEARN, code(0x5401) + struct.pack("<I", 3))        # level 2 first
    assert learn(role, s, 1)[0] == (guild.S2C_LEARN, code(0x5401) + struct.pack("<I", 1))        # not twice
    assert learn(role, s, 9999)[0] == (guild.S2C_LEARN, code(0x5401) + struct.pack("<I", 9999))
    assert learn(role, s, 2)[0] == (guild.S2C_LEARN, bytes(2) + struct.pack("<I", 2))            # 460,000
    assert (g["skills"], g["point"]) == ([2], 290_000)
    assert learn(role, s, 1)[0][1][:2] == code(0x5401)                                           # nor backwards
    # 0x3d83 lists one id a skill, its level's; the block's skill points count the levels
    assert ask(role, s, guild.C2S_SKILLS) == [(guild.S2C_SKILLS, bytes(2) + struct.pack("<HI", 1, 2))]
    assert guild.points_left(g) == 15 and [r["Ability_ID"] for r in guild.learned(s.data["char"])] == ["350001"]


def test_a_core_skill_needs_five_normal_levels_of_its_type_and_the_points_end_at_17(server):
    role, state, s = server
    g = found(role, s)
    g.update(point=10 ** 9, skills=[4])                                               # hero skill 350001 at level 4
    assert learn(role, s, 100)[0][1][:2] == code(0x5401)                              # a core at 4 normal levels
    g["skills"] = [4, 111]                                                            # a troop level does not count
    assert learn(role, s, 100)[0][1][:2] == code(0x5401)
    g["skills"] = [5]
    assert learn(role, s, 100)[0][1][:2] == bytes(2)
    assert learn(role, s, 101)[0][1][:2] == code(0x5401)                              # the second core needs 10
    g["skills"] = [5, 15, 100]
    assert learn(role, s, 101)[0][1][:2] == bytes(2) and g["skills"] == [5, 15, 100, 101]
    g["skills"] = [5, 15, 25, 100, 101]                                               # 17 levels: none left
    assert guild.points_left(g) == 0 and learn(role, s, 31)[0][1][:2] == code(0x5401)


def test_a_reset_costs_1500000_points_and_returns_what_the_skills_cost(server):
    role, state, s = server
    g = found(role, s)
    g["point"] = 1_499_999
    assert ask(role, s, guild.C2S_RESET) == [(guild.S2C_RESET, code(0x5401) + bytes(4))]         # nothing learned
    g["skills"] = [2, 211]
    assert ask(role, s, guild.C2S_RESET) == [(guild.S2C_RESET, code(0x5418) + bytes(4))] and g["skills"] == [2, 211]
    g["point"] = 1_500_000
    assert ask(role, s, guild.C2S_RESET)[:3] == [                                    # then the hero's block (test_guildfx)
        (guild.S2C_RESET, bytes(2) + struct.pack("<I", 17)),                         # the skill points left
        (guild.S2C_RESET_DONE, b""),                                                  # 0x3d89 empties the client's list
        (guild.S2C_GUILD_POINTS, struct.pack("<IQQ", 1, 250_000 + 460_000 + 250_000, 0))]
    assert g["skills"] == [] and g["point"] == 960_000


def test_goods_that_run_out_are_closed_by_their_own_timer(server, monkeypatch):
    role, state, s = server
    g = found(role, s)
    g["point"] = 3_000_000
    ask(role, s, guild.C2S_SHOP_OPEN, obf.u32(POINT_GOODS))
    ask(role, s, guild.C2S_SHOP_OPEN, obf.u32(POINT_GOODS))     # extended: the first timer will find it open
    ask(role, s, guild.C2S_SHOP)                                # the window opened again adds no timer
    assert [delay for delay, _ in s.pending] == [86_400, 2 * 86_400]
    s.sent.clear()
    monkeypatch.setattr(guild.time, "time", lambda: NOW + 86_400)
    s.pending[0][1]()
    assert s.sent == []
    monkeypatch.setattr(guild.time, "time", lambda: NOW + 2 * 86_400)
    s.pending[1][1]()
    assert [(w.proto, bytes(w.buf)) for w in s.sent] == [(guild.S2C_SHOP_CLOSED, obf.u32(POINT_GOODS))]
    assert g["shop"] == {}


def test_shop_goods_are_opened_and_extended_for_points_or_a_coin(server):
    role, state, s = server
    c = s.data["char"]
    g = found(role, s)
    assert ask(role, s, guild.C2S_SHOP) == [(guild.S2C_SHOP, bytes(4))]
    assert ask(role, s, guild.C2S_SHOP_OPEN, obf.u32(POINT_GOODS)) == [(guild.S2C_SHOP_OPEN, code(0x5418))]
    g["point"] = 3_100_000
    opened = obf.u32(POINT_GOODS) + struct.pack("<i", 86_400)
    assert ask(role, s, guild.C2S_SHOP_OPEN, obf.u32(POINT_GOODS)) == [
        (guild.S2C_SHOP_OPEN, bytes(2) + opened),                                     # 0x3d7e: 8 bytes after the i16
        (guild.S2C_SHOP_OPENED, opened),                                              # 0x3d7f: coded item, seconds left
        (guild.S2C_GUILD_POINTS, struct.pack("<IQQ", 1, 1_600_000, 0))]
    assert g["shop"] == {str(POINT_GOODS): NOW + 86_400}
    ask(role, s, guild.C2S_SHOP_OPEN, obf.u32(POINT_GOODS))                           # extended by another day
    assert g["shop"] == {str(POINT_GOODS): NOW + 2 * 86_400} and g["point"] == 100_000
    # Type Item goods take one of their coin from the bag
    assert ask(role, s, guild.C2S_SHOP_OPEN, obf.u32(COIN_GOODS)) == [(guild.S2C_SHOP_OPEN, code(0x5401))]
    c["bag"] = [{"code": COIN, "slot": 3, "count": 2, "serial": 77, "bound": False}]
    out = ask(role, s, guild.C2S_SHOP_OPEN, obf.u32(COIN_GOODS))
    week = obf.u32(COIN_GOODS) + struct.pack("<i", 604_800)
    assert out[:2] == [(guild.S2C_SHOP_OPEN, bytes(2) + week), (guild.S2C_SHOP_OPENED, week)]
    assert [p for p, _ in out[2:]] == [world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert c["bag"][0]["count"] == 1 and g["point"] == 100_000
    assert ask(role, s, guild.C2S_SHOP) == [(guild.S2C_SHOP, bytes(2) + struct.pack("<H", 2)
                                             + obf.u32(POINT_GOODS) + struct.pack("<i", 2 * 86_400) + week)]
    assert ask(role, s, guild.C2S_SHOP_OPEN, obf.u32(12345)) == [(guild.S2C_SHOP_OPEN, code(0x5401))]
    assert guild.open_goods(g, NOW + 3 * 86_400) == {COIN_GOODS: 604_800 - 3 * 86_400}          # what ran out is gone
    assert list(g["shop"]) == [str(COIN_GOODS)]


def rename(slot, serial, name):
    return obf.u16(slot) + obf.u64(serial) + cstr(name)


def test_the_name_change_form_renames_the_guild_and_is_used_up(server):
    role, state, s = server
    c = s.data["char"]
    g = found(role, s)
    assert ask(role, s, guild.C2S_RENAME, rename(5, 99, "Oakheart")) == [(guild.S2C_RENAME, code(0x5401))]   # no form
    c["bag"] = [{"code": FORM, "slot": 5, "count": 1, "serial": 99, "bound": True},
                {"code": COIN, "slot": 6, "count": 1, "serial": 100, "bound": False}]
    assert ask(role, s, guild.C2S_RENAME, rename(6, 100, "Oakheart")) == [(guild.S2C_RENAME, code(0x5401))]  # not a form
    assert ask(role, s, guild.C2S_RENAME, rename(5, 99, "ironwood")) == [(guild.S2C_RENAME, code(0x5409))]   # its own name
    assert ask(role, s, guild.C2S_RENAME, rename(5, 99, "O")) == [(guild.S2C_RENAME, code(0x5401))]
    assert g["name"] == "Ironwood" and len(c["bag"]) == 2
    out = ask(role, s, guild.C2S_RENAME, rename(5, 99, "Oakheart"))
    assert out[:2] == [(guild.S2C_RENAME, bytes(2)),
                       (guild.S2C_RENAMED, struct.pack("<I", 1) + b"Oakheart\0")]    # 0x3d8e: the client's name
    assert [p for p, _ in out[2:]] == [world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert g["name"] == "Oakheart" and [it["code"] for it in c["bag"]] == [COIN] and guild.name_of(c) == "Oakheart"


def test_the_grades_rights_are_changed_by_the_master(server):
    role, state, s = server
    g = found(role, s)
    wire = (0b000000001, 0, 0x7fffffff, 0b101, 0b11)                # Regular, Novice, SubMaster, Senior, Captain
    assert ask(role, s, guild.C2S_RIGHTS, struct.pack("<5i", *wire)) == [
        (guild.S2C_RIGHTS, bytes(2)),
        (guild.S2C_RIGHTS_PUSH, struct.pack("<5i", 1, 0, 0x1ff, 0b101, 0b11))]       # 9 rights: the rest is dropped
    assert g["rights"] == [0x1ff, 0b11, 0b101, 1, 0]                # SubMaster, Captain, Senior, Regular, Novice
    assert ask(role, s, guild.C2S_RIGHTS, bytes(19)) == [(guild.S2C_RIGHTS, code(0x5405))]


def test_dismissing_the_guild_removes_it_from_the_save(server):
    role, state, s = server
    c = s.data["char"]
    found(role, s)
    saves = state.saves
    assert ask(role, s, guild.C2S_DISMISS) == [(guild.S2C_DISMISS, bytes(2))]        # 0x3d47 0: "Guild disbanded."
    assert "guild" not in c and state.saves == saves + 1 and c["gold"] == 15_000     # the fee is not returned
    assert ask(role, s, guild.C2S_INFO) == [(guild.S2C_INFO, code(0x5405))]
    assert ask(role, s, guild.C2S_RANKING, struct.pack("<I", 1)) == [(guild.S2C_RANKING, code(0x5415))]
    assert ask(role, Session(state.account, state.qwe), guild.C2S_CREATE, cstr("Second"))[0][1][:2] == bytes(2)


@pytest.mark.parametrize("with_guild", [False, True])
def test_no_handler_raises_on_a_short_or_junk_body_and_every_reply_keeps_what_its_handler_reads(server, with_guild):
    role, state, s = server
    c = s.data["char"]
    always = {guild.S2C_JOIN: 6, guild.S2C_ACCEPT: 6, guild.S2C_REFUSE: 6, guild.S2C_WITHDRAW: 6, guild.S2C_LEARN: 6,
              guild.S2C_RESET: 6, guild.S2C_POINTS: 26}             # read whatever the result (the spec's crash sizes)
    for proto in sorted(role.handlers):
        for body in (b"", b"\x01", b"\xff" * 3, b"\xff" * 64, bytes(64), b"A" * 5 + b"\0" + b"\xfe" * 30):
            c.pop("guild", None)                                    # each request meets the same state
            if with_guild:
                c["guild"] = dict(guild.new(c, "Ironwood"), point=10 ** 8, skills=[1])
            replies = ask(role, s, proto, body)
            assert replies, hex(proto)                              # and every one of them is answered
            for reply, sent in replies:
                assert len(sent) >= always.get(reply, 2) or reply in (guild.S2C_MEMO_CHANGED, guild.S2C_NOTE_CHANGED,
                                                                      guild.S2C_RESET_DONE), (hex(proto), body)
                if reply in (guild.S2C_RANKING, guild.S2C_RANKING_FIND) and sent[:2] == bytes(2):
                    assert struct.unpack_from("<H", sent, 6)[0] >= 1, hex(proto)        # never a success without a row


def test_the_tables_have_the_shape_the_module_reads():
    rows = guild.skill_rows()
    assert len(rows) == 65 and len(guild.shop_rows()) == 28 and guild.default_cap() == 20
    for k, r in rows.items():                                       # a skill's levels are consecutive ids
        if int(r["Skill_Level"]) > 1:
            below = rows[k - 1]
            assert (int(below["Skill_Level"]), below["Skill_Type"], below["Ability_ID"], below["Core_Skill"]) == (
                int(r["Skill_Level"]) - 1, r["Skill_Type"], r["Ability_ID"], r["Core_Skill"])
    assert guild.populations()[0] == (22, 100_000) and guild.populations()[-1] == (60, 1_740_000)
    assert guild.skill_price(5) == 250_000 + 460_000 + 880_000 + 1_700_000 + 3_400_000
    assert {r["Type"] for r in guild.shop_rows().values()} == {"Point", "Item"}

"""Walkthrough part 1: character creation, the prologue's hand-off and Glen's camp in Mist Field (10352) up to
1150301's mission warp (planning/walkthrough/p1-tutorial-camp.md). Reads the game tables from the installed game.
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import items, obf, quest, state as state_mod, tables, world, zone
from kuf2.obf import T1, T2
from kuf2.packet import Reader


class Session:
    def __init__(self):
        self.data = {"char": {"id": 1, "class": 0, "level": 1}}
        self.sent = []
        self.pending = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))

    def run_later(self):
        while self.pending:
            self.pending.pop(0)[1]()


class State:
    saves = 0

    def save(self):
        self.saves += 1


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def accept_body(qid, mode=0):
    enc = obf.u32(qid)
    return bytes([T2[(enc[0] * 4 + mode) & 0xff]]) + enc


@pytest.fixture
def world_role():
    st = State()
    return world.make(st, 0, "127.0.0.1", 0), st


def create(role, s, name=b"Isa", cls=3):
    """The lobby's character creation (0x100b; look +0x34 the class: createcharacter HeroId 3, the Spellsword)."""
    look = bytearray(56)
    struct.pack_into("<I", look, 0x34, cls)
    role.handlers[world.C2S_CHAR_CREATE](s, pkt(world.C2S_CHAR_CREATE, name + b"\0" + bytes(look)))
    return s.data["account"]["characters"][-1]


def test_a_new_character_plays_the_prologue_then_reaches_glens_camp(tmp_path):
    """Created: saved at Glen's camp with the prologue to play (tutorial_done False). Started: 0x3763, then the game
    server for 50116. The prologue played to its end (test_scenes_50116.play): no result window, 0x4041 to the camp,
    the prologue done; the client's 0x10d6 on the way out changes nothing more. Then the camp's field room, and at the
    next login the camp, never the prologue."""
    from test_scenes_50116 import play, room
    st = state_mod.State(tmp_path / "db.json")
    acct = st.account_for_steam(76561190000000001, "p")
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data = {"account": acct}
    c = create(role, s)
    assert (c["spot"], c["pos"], c["tutorial_done"]) == (10352, [329756, 0, 175403], False)
    assert state_mod.State(tmp_path / "db.json").db["accounts"][str(76561190000000001)]["characters"][0]["spot"] == 10352
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", c["id"], 0)))
    assert [w.proto for w in s.sent][-2:] == [world.S2C_ENTER_TUTORIAL, world.S2C_GAME_SERVER]
    assert struct.unpack_from("<I", bytes(s.sent[-1].buf), 8)[0] == world.TUTORIAL_SPOT
    r = room(c=c)                                       # the game role's room for this character
    play(r)
    from kuf2 import game
    leave = [bytes(w.buf) for w in r.sent if w.proto == game.S2C_MISSION_LEAVE]
    assert len(leave) == 1 and obf.dec_u32(leave[0][4:8]) == 10352 and c["tutorial_done"] is True
    assert c["spot"] == 10352 and not [w for w in r.sent if w.proto == game.S2C_MISSION_COMPLETE]
    s.data["char"] = c
    role.handlers[world.C2S_PROLOGUE_DONE](s, pkt(world.C2S_PROLOGUE_DONE, b""))     # the client, leaving 50116
    assert c["tutorial_done"] is True
    s.sent.clear()
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(10352)))   # the camp loaded
    s.run_later()
    assert s.sent[-1].proto == world.S2C_GAME_SERVER and s.data["battle_spot"] == 10352
    s.sent.clear()
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", c["id"], 0)))   # next login
    prep = bytes(next(w for w in s.sent if w.proto == world.S2C_PREPARE_ENTER_TOWN).buf)
    assert struct.unpack_from("<I", prep, 2)[0] == 10352 and world.S2C_ENTER_TUTORIAL not in [w.proto for w in s.sent]


def test_a_character_from_before_the_prologue_never_goes_back():
    """Only a character created for the prologue plays it: one without the key (created before it existed, the owner's
    qwe123 among them) or past it keeps its place."""
    role = world.make(None, 0, "127.0.0.1", 0)
    for done, prologue in ((None, False), (True, False), (False, True)):
        s = Session()
        c = {"id": 4, "name": "A", "class": 0, "level": 1, "bag_slots": world.CARGO_SLOTS, "spot": world.NEW_CHAR_SPOT,
             "pos": list(world.TOWN_ENTRY[world.NEW_CHAR_SPOT])}
        if done is not None:
            c["tutorial_done"] = done
        s.data["account"] = {"characters": [c]}
        role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 4, 0)))
        assert (world.S2C_ENTER_TUTORIAL in [w.proto for w in s.sent]) is prologue, done
        assert ("mission" in c) is prologue


def test_end_the_tutorial_leaves_the_prologue_for_glens_camp(world_role):
    """The system menu's "End the tutorial?" (text 90309) in the prologue: C2S 0x5640 with warp 205 (10352 group 1):
    out of the room into the camp's field at that group; the client then says the prologue is over (0x10d6)."""
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(name="A", tutorial_done=False, spot=10352, pos=[329756, 0, 175403],
             mission={"spot": world.TUTORIAL_SPOT, "back": 10352, "difficulty": 0})
    s.data.update(account={"id": 1, "characters": [c]}, battle_spot=world.TUTORIAL_SPOT, game_addr=("127.0.0.1", 0))
    q, p15 = obf.pos_xz(149797, 193754)
    body = q + struct.pack("<h", 1919) + bytes([p15, 0]) + struct.pack("<H", 0) + obf.u32(205) + bytes([0])
    role.handlers[world.C2S_WARP_REQUEST](s, pkt(world.C2S_WARP_REQUEST, body))
    assert [w.proto for w in s.sent][-2:] == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]
    assert c["field_group"] == [10352, 1]
    s.run_later()
    assert s.sent[-1].proto == world.S2C_GAME_SERVER and s.data["battle_spot"] == 10352
    role.handlers[world.C2S_PROLOGUE_DONE](s, pkt(world.C2S_PROLOGUE_DONE, b""))
    assert c["tutorial_done"] is True and "mission" not in c


def test_with_the_prologue_off_a_new_character_enters_the_camp_directly(tmp_path, monkeypatch):
    monkeypatch.setattr(world, "PROLOGUE_FOR_NEW_CHARACTERS", False)
    st = state_mod.State(tmp_path / "db.json")
    acct = st.account_for_steam(76561190000000001, "p")
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data = {"account": acct}
    c = create(role, s)
    assert c["tutorial_done"] is True
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", c["id"], 0)))
    prep = bytes(next(w for w in s.sent if w.proto == world.S2C_PREPARE_ENTER_TOWN).buf)
    assert struct.unpack_from("<I", prep, 2)[0] == 10352          # the field, entered the town way, then its room
    assert obf.dec_pos_xz(prep[6:10], prep[12]) == (329756, 175403)
    monkeypatch.setattr(world, "PROLOGUE_FOR_NEW_CHARACTERS", True)    # switched on later: he is past it
    s.sent.clear()
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", c["id"], 0)))
    assert world.S2C_ENTER_TUTORIAL not in [w.proto for w in s.sent]


def select_location(entry):
    """The character select's "Character Location" as the client picks it from a 0x100a entry (0x140ed7470 at
    0x140ed76c1, InfoBox.as UpdateCharDetailInfo $area): +0x4e false (LobbyCharacter +0x1539) -> spot 50116's name,
    the client's own constant 0xc3c4; else the plain u32 +0x0f (+0x14f8) unless 0 / -1 (text 20033); a name is kind 2
    of 0x140578a90, the spot's WAR_SPOT_NAME (live 2026-10-24: "Azilia Castle" for every hero, 50116's)."""
    spot = struct.unpack_from("<I", entry, 0x0f)[0]
    if entry[0x4e] != world.OBOOL_TRUE:
        spot = 0xc3c4
    elif spot in (0, 0xffffffff):
        return 20033
    names = {r["TextID"]: r["Text"] for r in tables.sections(r"text\eng\textspotname_eng")["TextTable"]}
    return names[f"{spot}/WAR_SPOT_NAME"]


def test_the_select_screen_names_where_each_hero_is_saved():
    """Live 2026-10-24: every hero read "Azilia Castle" (the entry sent no spot and +0x4e false). A hero past the
    prologue names its saved spot (Aldric and qwe123 at 10359: Mist Field), one from before the prologue too; a new
    hero with the prologue to play shows Azilia Castle, as the client itself names it for +0x4e false, and its entry
    names the spot its start goes to (50116, world.login_point)."""
    look = bytes(0x38).hex()
    heroes = {
        "Aldric": {"tutorial_done": None, "spot": 10359, "want": "Mist Field"},      # created before the prologue
        "qwe123": {"tutorial_done": True, "spot": 10359, "want": "Mist Field"},
        "proventen": {"tutorial_done": False, "spot": world.NEW_CHAR_SPOT, "want": "Azilia Castle"},
    }
    for name, h in heroes.items():
        c = {"id": 7, "class": 0, "level": 1, "name": name, "look": look, "spot": h["spot"]}
        if h["tutorial_done"] is not None:
            c["tutorial_done"] = h["tutorial_done"]
        w = world.Writer(world.S2C_CHAR_LIST)
        world.write_char_entry(w, c)
        entry = bytes(w.buf)[:0x58]
        assert select_location(entry) == h["want"], name
        assert struct.unpack_from("<I", entry, 0x0f)[0] == world.login_point(c)[1]
    assert world.login_point({"tutorial_done": False, "spot": 10352})[:2] == (True, world.TUTORIAL_SPOT)


def bar_page(w):
    """The hero bar of a 0x1747 page 0 (world.quick_slot_page_packet): [(bar slot, ability id, level)] of its type-0
    list (u8 n, n * (u64 hero uid, u8 kind, u8 slot, i16 handle, u32 id, u8 level))."""
    b = bytes(w.buf)
    assert b[0] == 0
    out, at = [], 2
    for _ in range(b[1]):
        kind, slot = b[at + 8], b[at + 9]
        assert kind == 1
        aid, level = struct.unpack_from("<IB", b, at + 12)
        out.append((slot, aid, level))
        at += 17
    return out


@pytest.mark.parametrize("cls, first", [(4, [608, 633]), (0, [15, 9]), (3, [305, 336]), (1, [908, 945]),
                                        (2, [1204, 1206]), (5, [])])
def test_a_new_heros_bar_holds_the_classs_first_two_skills_in_the_prologue(tmp_path, cls, first):
    """Live 2026-10-24: proventen's skill bar (keys 1-8) was empty at the prologue's UseSkill lesson ("Use skills in
    the Skill slots to attack enemies."). The tape (part 1, the Berserker) shows keys 1 and 2 filled when the lesson
    brings the bar up (5:10.5, 293_319 f_00036), key 1 used at 5:12.5 (f_00040) and showing "9" just after a use at
    19:26 (1157_1167 f_00020): Charging Slash 608's 9 s cooldown (633's is 8): the book's two level-1 AutoLearn
    quick-slot skills in its order (skills.bar_skills; the Sorceress has none). Seated at creation, they
    come back in the page 0 the client asks for on entering the prologue's battle field (0x1746 x9)."""
    st = state_mod.State(tmp_path / "db.json")
    acct = st.account_for_steam(76561190000000001, "p")
    role = world.make(st, 0, "127.0.0.1", 0)
    s = Session()
    s.data = {"account": acct}
    c = create(role, s, cls=cls)
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", c["id"], 0)))
    assert world.S2C_ENTER_TUTORIAL in [w.proto for w in s.sent]
    s.sent.clear()
    role.handlers[world.C2S_QUICK_SLOT_PAGE](s, pkt(world.C2S_QUICK_SLOT_PAGE, bytes([0])))
    page = next(w for w in s.sent if w.proto == world.S2C_QUICK_SLOT_PAGE)
    assert bar_page(page) == [(n, aid, 1) for n, aid in enumerate(first)]
    held = state_mod.State(tmp_path / "db.json").db["accounts"][str(76561190000000001)]["characters"][0]
    assert sorted(e["id"] for e in held["quick_slots"].values()) == sorted(first)       # in the save


def test_a_level_up_puts_the_new_skill_on_the_first_free_key():
    """The tape (part 1, Lv.2 in Glen's camp): "Learned Capture skill." (20:02, 1199_1207 f_00010) and Capture on key 3
    four seconds later (f_00016) with a dialogue open: no drag. After the 0x1761, a 0x1747 page 0 with it; a key the
    player emptied stays empty (only the new skill is seated), and a skill already on the bar is not seated twice."""
    from kuf2 import skills

    class Quiet:
        def save(self):
            pass

    s = Session()
    c = s.data["char"] = {"id": 1, "name": "Sorrowh", "class": 4, "level": 1, "exp": 0}
    assert world.seat_skills(c, skills.bar_skills(c)) == [608, 633]
    del c["quick_slots"]["0:0:0"]                       # the player took Charging Slash off key 1
    world.add_exp(s, Quiet(), world.hero_need(1))
    assert c["level"] == 2
    protos = [w.proto for w in s.sent]
    assert protos.index(world.S2C_QUICK_SLOT_PAGE) > protos.index(skills.S2C_LEARN)
    page = next(w for w in s.sent if w.proto == world.S2C_QUICK_SLOT_PAGE)
    assert bar_page(page) == [(0, 710, 1), (1, 633, 1)]
    assert world.seat_skills(c, [710, 633]) == []


class Quiet:
    def save(self):
        pass


# What each level seats, level 1-10 (bar slot, ability): keys 1-8 = slots 0-7, the lower (tactics) row = 100-107.
# The Berserker's is the tape's (planning/agents/reports/2026-10-24_skillbar.md); the other classes follow the same
# heroskillbook rule (AutoLearn + QuickSlotSituate, no ParentsLinkId; KeyType SLOT_TYPE_1 above, SLOT_TYPE_7_SERIES1
# below); the Sorceress has no such row.
BAR_BY_LEVEL = {
    4: {1: [(0, 608), (1, 633)], 2: [(2, 710)], 6: [(100, 5012)], 8: [(3, 745)]},
    0: {1: [(0, 15), (1, 9)], 2: [(2, 82)], 6: [(100, 5012)], 8: [(3, 95)]},
    1: {1: [(0, 908), (1, 945)], 2: [(2, 969)], 6: [(100, 5012)], 8: [(3, 1008)]},
    2: {1: [(0, 1204), (1, 1206)], 2: [(2, 1208)], 6: [(100, 5012)], 8: [(3, 1228)]},
    3: {1: [(0, 305), (1, 336)], 2: [(2, 314)], 6: [(100, 5012)], 8: [(3, 320)]},
    5: {},
}


@pytest.mark.parametrize("cls", sorted(BAR_BY_LEVEL))
def test_the_hero_bar_level_by_level_up_to_10_as_on_the_tape(cls):
    """The tape's Berserker, every level 1-10 read on the bar (exact grabs; the report names each frame): keys 1-2 at
    the prologue's lesson (part 1 293_319 f_00036); Capture on key 3 at Lv.2 (1199_1207 f_00016); nothing new at Lv.3,
    4 or 5 (2265_2287 f_00023, 2315_2321 f_00007 "Learned True Dark Impact skill." with the bar unchanged, part 2
    video 1440); Supplement on the lower row's first slot at Lv.6 (part 2 video 1548 empty -> 1551.5 filled, "Learned
    Earth Cleaver skill." / "Learned Supplement skill." in the chat, 1552); nothing at Lv.7; Extinction on key 4 at
    Lv.8 (part 3 video 718 empty -> 727 filled under the "Learned the new Hero Skill. / Extinction" card); nothing at
    Lv.9 or 10 (part 4 video 564 Lv.9, 592 "Learned Dark Impact - Wave skill." / "Learned Land of Death skill.", 604
    Lv.10: keys 1-4 and the lower row's Supplement). No drag at any level. Each level-up that seats a skill pushes one
    0x1747 page 0 after its 0x1761; a level that seats nothing pushes none."""
    from kuf2 import skills

    s = Session()
    c = s.data["char"] = {"id": 1, "name": "Sorrowh", "class": cls, "level": 1, "exp": 0}
    want = dict(BAR_BY_LEVEL[cls].get(1, []))
    world.seat_skills(c, skills.bar_skills(c))                      # char_create
    assert {int(k.split(":")[2]): e["id"] for k, e in c["quick_slots"].items()} == want
    for level in range(2, 11):
        s.sent.clear()
        world.add_exp(s, Quiet(), world.hero_need(c["level"]))
        assert c["level"] == level
        new = BAR_BY_LEVEL[cls].get(level, [])
        want.update(new)
        assert {int(k.split(":")[2]): e["id"] for k, e in c["quick_slots"].items()} == want, level
        protos = [w.proto for w in s.sent]
        pages = [w for w in s.sent if w.proto == world.S2C_QUICK_SLOT_PAGE]
        if new:
            assert len(pages) == 1 and protos.index(world.S2C_QUICK_SLOT_PAGE) > protos.index(skills.S2C_LEARN)
            assert sorted(bar_page(pages[0])) == [(n, aid, 1) for n, aid in sorted(want.items())], level
        else:
            assert pages == [], level


def test_a_tactics_skill_takes_the_lower_row_and_a_moved_skill_is_not_seated_twice():
    """Supplement (KeyType SLOT_TYPE_7_SERIES1) goes to slot 100 (MainControlWidget slot_100, the lower row) even with
    keys 1-8 all taken; with keys 1-8 full the Lv.8 skill finds no free key and is not seated (a full row takes no
    more); a bar skill the player moved elsewhere on the bar is not put back; First Aid 5098 (the same rule at Lv.12)
    takes the lower row's next slot."""
    from kuf2 import skills

    s = Session()
    c = s.data["char"] = {"id": 1, "name": "Sorrowh", "class": 4, "level": 5, "exp": 0}
    c["quick_slots"] = {f"0:0:{n}": {"kind": 1, "id": aid, "bag": skills.handle(c, aid)}     # any eight entries
                        for n, aid in enumerate([608, 633, 710, 604, 738, 643, 616, 717])}
    world.add_exp(s, Quiet(), world.hero_need(5))
    assert c["level"] == 6 and c["quick_slots"]["0:0:100"]["id"] == 5012
    for _ in range(2):
        world.add_exp(s, Quiet(), world.hero_need(c["level"]))
    assert c["level"] == 8 and 745 not in {e["id"] for e in c["quick_slots"].values()}
    c["quick_slots"]["0:0:7"] = c["quick_slots"].pop("0:0:100")           # the player moved Supplement to key 8
    assert world.seat_skills(c, skills.bar_skills(c, 8)) == []
    del c["quick_slots"]["0:0:3"]
    c["level"] = 12
    assert world.seat_skills(c, skills.bar_skills(c)) == [745, 5098]       # 636 (Lv.12, keys) finds no free key
    assert c["quick_slots"]["0:0:3"]["id"] == 745 and c["quick_slots"]["0:0:100"]["id"] == 5098
    assert skills.bar_row(c, 636) == 0 and skills.bar_row(c, 5098) == 100 and "0:0:101" not in c["quick_slots"]


def test_a_save_past_level_6_that_never_touched_the_bar_gets_both_rows(world_role):
    """A save with no quick_slots key (seated at start game by its level, test above) at Lv.8: keys 1-4 and Supplement
    on the lower row, as the tape's Berserker held them at Lv.8 (part 3 video 727)."""
    role, st = world_role
    s = Session()
    c = {"id": 4, "name": "A", "class": 4, "level": 8, "bag_slots": world.CARGO_SLOTS, "tutorial_done": True,
         "spot": world.NEW_CHAR_SPOT, "pos": list(world.TOWN_ENTRY[world.NEW_CHAR_SPOT])}
    s.data["account"] = {"characters": [c]}
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 4, 0)))
    assert {k: e["id"] for k, e in c["quick_slots"].items()} == {
        "0:0:0": 608, "0:0:1": 633, "0:0:2": 710, "0:0:3": 745, "0:0:100": 5012}


def test_a_save_that_never_touched_the_bar_gets_its_skills_once(world_role):
    """A character from before the bar was seeded (no quick_slots key: never registered, cleared or swapped a slot,
    as proventen created live today) gets what the bar would hold by its level at the next start; one whose player
    emptied the bar keeps it empty."""
    role, st = world_role
    for slots, want in ((None, [15, 9, 82]), ({}, [])):
        s = Session()
        c = {"id": 4, "name": "A", "class": 0, "level": 2, "bag_slots": world.CARGO_SLOTS, "tutorial_done": True,
             "spot": world.NEW_CHAR_SPOT, "pos": list(world.TOWN_ENTRY[world.NEW_CHAR_SPOT])}
        if slots is not None:
            c["quick_slots"] = slots
        s.data["account"] = {"characters": [c]}
        role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 4, 0)))
        assert [c["quick_slots"][f"0:0:{n}"]["id"] for n in range(len(want))] == want
        assert len(c["quick_slots"]) == len(want)


def test_seen_guides_come_back_in_the_start_game_reply(world_role):
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(name="A", exp=0, spot=10352, pos=[329756, 0, 175403])
    s.data["account"] = {"characters": [c]}
    for k in (0x57, 0x58, 0x57, 0x8e):                     # quest-list and bag notices; 0x8e cannot be carried
        role.handlers[world.C2S_GUIDE_SEEN](s, pkt(world.C2S_GUIDE_SEEN, bytes([k])))
    assert c["guides"] == [0x57, 0x58] and st.saves == 2
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 1, 0)))
    out = bytes(next(w for w in s.sent if w.proto == world.S2C_START_GAME_RES).buf)
    q = out[2 + 0x25:]
    assert len(q) == 0x20 and struct.unpack_from("<QQ", q, 2) == (0, (1 << 0x17) | (1 << 0x18))
    assert q[0x12] == 1                                    # the obool after the bits is unchanged


def test_a_guide_report_without_a_character_or_id_is_dropped(world_role):
    role, st = world_role
    s = Session()
    role.handlers[world.C2S_GUIDE_SEEN](s, pkt(world.C2S_GUIDE_SEEN, b""))      # a handler error would end the session
    del s.data["char"]
    role.handlers[world.C2S_GUIDE_SEEN](s, pkt(world.C2S_GUIDE_SEEN, b"W"))
    assert st.saves == 0 and s.sent == []


def test_a_character_without_guides_sends_no_seen_bits():
    role = world.make(None, 0, "127.0.0.1", 0)
    s = Session()
    c = {"id": 4, "name": "A", "class": 0, "level": 1, "bag_slots": world.CARGO_SLOTS, "spot": 10352,
         "pos": [329756, 0, 175403]}
    s.data["account"] = {"characters": [c]}
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 4, 0)))
    q = bytes(next(w for w in s.sent if w.proto == world.S2C_START_GAME_RES).buf)[2 + 0x25:]
    assert q[2:0x12] == bytes(16)


def test_the_camp_field_holds_1150106s_quest_bound():
    """QuestBound 6310 is a circle of zone 3 (the field 10352), next to its hand-in NPC 6049; the battle state reads
    the zone's QuestBound list into the watcher's regions (0x140cfd6b0 -> 0x140cd7750), so it is reported in the camp's
    field room. Zone 4 (battle 10353) has none."""
    bounds = {b["QuestBoundID"]: b for b in zone.for_spot(10352)["QuestBound"]}
    b = bounds[6310]
    assert (round(b["PosX"]), round(b["PosZ"]), b["RadiusX"]) == (333348, 170751, 2000.0)
    felix = next(n for n in zone.for_spot(10352)["NPCInfo"] if n["TableID"] == 6049)
    assert (felix["PosX"] - b["PosX"]) ** 2 + (felix["PosZ"] - b["PosZ"]) ** 2 < b["RadiusX"] ** 2
    assert zone.for_spot(10353)["QuestBound"] in ([], None)


def test_the_camp_quests_find_their_targets_in_the_camp_zone():
    z = zone.for_spot(10352)
    troops = [t["TroopTableID"] for t in z["NPCTroopInfoData"]]
    props = [p["SmartPropTypeID"] for p in z["SmartPropData"]]
    npcs = {n["TableID"] for n in z["NPCInfo"]}
    assert props.count(402) >= 2                                    # 1150201: two cocoons
    assert troops.count(154030) >= 3                                # 1150202: tarantulas (npname 1000086)
    assert {154050, 154150} <= set(troops)                          # 1150204: Mist Tribe kobolds (group 1000102)
    assert 154160 in troops                                         # 1150204: Sagarazu (npname 1000085)
    assert quest.kill_names(154030) >= {"1000086"} and quest.kill_groups(154150) == {"1000102"}
    assert "1000085" in quest.kill_names(154160)
    assert 6361 in npcs                                             # 1150203: the campfire (Talk 6361)
    assert {6013, 6018, 6011, 6049, 6003, 6292, 6028, 6029, 6293, 6199, 6089} <= npcs     # every giver / taker


@pytest.mark.parametrize("cls", range(5))
def test_camp_rewards_are_weapon_offhand_and_armour_for_every_class(cls):
    """Walkthrough: '[Equip Gear] -> Weapon, Offhand, Armor' (1150110, 1150202, 1150204 NormalCategory rewards)."""
    qt = tables.by_id("questtable")
    parts = [items.row(code)["Parts"] for qid in ("1150110", "1150202", "1150204")
             for code, _ in quest.reward_items(qt[qid], cls) if items.row(code)["Parts"] != "NONE"]
    assert parts == ["MAIN_WEAPON", "SUB_WEAPON", "UPPERBODY"]


def talk(role, s, qid, cond=0):
    role.handlers[quest.C2S_PROGRESS](s, pkt(quest.C2S_PROGRESS, struct.pack("<H", 1) + obf.u32(qid) + bytes([cond])))


def hand_in(role, s, qid):
    role.handlers[quest.C2S_COMPLETE](s, pkt(quest.C2S_COMPLETE, obf.u32(qid) + b"\xff"))
    done = next(w for w in s.sent if w.proto == quest.S2C_COMPLETE and obf.dec_u32(bytes(w.buf)[3:7]) == qid)
    assert bytes(done.buf)[:2] == b"\0\0", qid


def test_glens_camp_chain_from_1003_to_the_mission_warp(world_role):
    """Each condition from its trigger: Talk from the client (0x554b), the quest area (0x5558), cocoon casts
    (on_prop), kills (on_kill), the kobold powder picked up (the bag), then 1150301's accept enters mission 10358."""
    role, st = world_role
    s = Session()
    s.data.update(battle_spot=10352, game_addr=("127.0.0.1", 25004))
    s.data["char"].update(spot=10352, pos=[329756, 0, 175403], field_group=[10352, 0])
    s.data["account"] = {"id": 1, "characters": [s.data["char"]]}

    def accept(qid):
        role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(qid)))
        assert str(qid) in s.data["char"]["quests"]["active"], qid

    accept(1003); talk(role, s, 1003); hand_in(role, s, 1003)
    accept(1150106)
    role.handlers[quest.C2S_AREA](s, pkt(quest.C2S_AREA, obf.u32(10352) + struct.pack("<I", 6310)))
    hand_in(role, s, 1150106)
    accept(1150109); talk(role, s, 1150109); hand_in(role, s, 1150109)
    accept(1150110)                                     # SpotWarp 620: into the north of the field (group 2)
    assert s.data["char"]["field_group"] == [10352, 2]
    talk(role, s, 1150110); hand_in(role, s, 1150110)
    accept(1150201); accept(1150202)
    for _ in range(2):
        quest.on_prop(s, st, 402)                       # a cocoon cast completed (game.py 0x5096)
    for _ in range(3):
        quest.on_kill(s, st, 154030)                    # a Mist Forest Tarantula wiped
    hand_in(role, s, 1150201); hand_in(role, s, 1150202)
    accept(1150205); talk(role, s, 1150205); hand_in(role, s, 1150205)
    accept(1150203); accept(1150204)
    assert quest.roll_drops(s, 154050, lambda n: 0) == [(451000231, 1)]
    for _ in range(2):
        world.add_item(s, st, 451000231, 1)             # the kobold powder picked up (0x4052)
    assert quest.roll_drops(s, 154050, lambda n: 0) == []        # no more drops once the condition is met
    talk(role, s, 1150203, 1)                           # the campfire (NPC 6361)
    for t in (154050, 154150, 154050, 154160):
        quest.on_kill(s, st, t)
    hand_in(role, s, 1150203); hand_in(role, s, 1150204)
    accept(1150206); talk(role, s, 1150206); hand_in(role, s, 1150206)
    c = s.data["char"]
    assert c["quests"]["done"] == [1003, 1150106, 1150109, 1150110, 1150201, 1150202, 1150205, 1150203, 1150204,
                                   1150206]
    assert c["gold"] == 50 + 20 + 50 + 50 + 50 + 150 + 60 + 110 + 170 + 60
    bag_parts = {items.row(i["code"])["Parts"] for i in c["bag"]}
    assert {"MAIN_WEAPON", "SUB_WEAPON", "UPPERBODY"} <= bag_parts
    s.sent.clear()
    accept(1150301)                                     # SpotWarp 613 (MISSION): out of the camp through 10358
    assert [w.proto for w in s.sent][-3:] == [quest.S2C_ACCEPT, world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]
    assert c["mission"]["spot"] == 10358 and s.data["battle_spot"] == 10358
    s.run_later()
    assert s.sent[-1].proto == world.S2C_GAME_SERVER and struct.unpack_from("<I", bytes(s.sent[-1].buf), 8)[0] == 10358

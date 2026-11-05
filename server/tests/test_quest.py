"""Quest requests and lists (server/kuf2/quest.py). Reads questtable from the installed game's Info.pkg.
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import obf, quest, tables, world
from kuf2.obf import T1, T2
from kuf2.packet import Reader

TALK_QUEST = 1003       # Mist Field: Sarah 6013 -> Talk 6018 -> Brenon 6011
BOUND_QUEST = 1150106   # Complete1 QuestBound 6310 (an area of the battle map)


class Session:
    def __init__(self):
        self.data = {"char": {"id": 1, "class": 0}}
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


ACHIEVEMENT_PUSHES = (0x10f1, 0x10f2)     # titles.py counters and earned titles ride along with many events


def core(sent):
    """The packets a test is about, without the achievement pushes that follow gold, quests and levels."""
    return [w for w in sent if w.proto not in ACHIEVEMENT_PUSHES]


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def accept_body(qid, mode=0):
    """As the builder 0x140f00d70 writes it: mode byte keyed with the first id byte, then the coded id."""
    enc = obf.u32(qid)
    return bytes([T2[(enc[0] * 4 + mode) & 0xff]]) + enc


@pytest.fixture
def world_role():
    st = State()
    return world.make(st, 0, "127.0.0.1", 0), st


def test_talk_quest_accept_progress_complete(world_role):
    role, st = world_role
    s = Session()
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(TALK_QUEST, 2)))
    out = s.sent[-1]
    assert out.proto == quest.S2C_ACCEPT and bytes(out.buf) == b"\0\0" + obf.u32(TALK_QUEST)
    assert list(s.data["char"]["quests"]["active"]) == [str(TALK_QUEST)]

    role.handlers[quest.C2S_PROGRESS](s, pkt(quest.C2S_PROGRESS, struct.pack("<H", 1) + obf.u32(TALK_QUEST) + b"\0"))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == quest.S2C_PROGRESS and len(out) == 17
    assert out[0] == 1 and struct.unpack_from("<5h", out, 1) == (1, 0, 0, 0, 0) and obf.dec_u32(out[13:]) == TALK_QUEST

    role.handlers[quest.C2S_COMPLETE](s, pkt(quest.C2S_COMPLETE, obf.u32(TALK_QUEST) + b"\0"))
    sent = core(s.sent)
    out = bytes(sent[-3].buf)
    assert sent[-3].proto == quest.S2C_COMPLETE and out[:2] == b"\0\0" and T1[out[2]] & 1 == 0
    assert obf.dec_u32(out[3:7]) == TALK_QUEST
    assert s.data["char"]["quests"] == {"active": {}, "done": [TALK_QUEST]}
    assert [w.proto for w in sent[-2:]] == [world.S2C_GOLD, 0x124a]     # questtable 1003: Gold 50, Exp 13
    assert s.data["char"]["gold"] == 50 and s.data["char"]["exp"] == 13
    assert st.saves >= 5                    # achievements save as well


def test_complete_refused_until_conditions_are_met(world_role):
    role, _ = world_role
    s = Session()
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(TALK_QUEST)))
    role.handlers[quest.C2S_COMPLETE](s, pkt(quest.C2S_COMPLETE, obf.u32(TALK_QUEST) + b"\0"))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", quest.RESULT_FAIL)
    assert str(TALK_QUEST) in s.data["char"]["quests"]["active"]


@pytest.mark.parametrize("known,active,done", [(False, False, False), (True, True, False), (True, False, True)])
def test_accept_refused_for_unknown_active_or_done(world_role, known, active, done):
    role, st = world_role
    s = Session()
    qid = TALK_QUEST if known else 999999999
    s.data["char"]["quests"] = {"active": {str(qid): {"counts": [0] * 5}} if active else {},
                                "done": [qid] if done else []}
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(qid)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", quest.RESULT_FAIL) and st.saves == 0


def test_progress_is_capped_at_the_required_count(world_role):
    role, _ = world_role
    s = Session()
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(TALK_QUEST)))
    role.handlers[quest.C2S_PROGRESS](s, pkt(quest.C2S_PROGRESS, struct.pack("<H", 9) + obf.u32(TALK_QUEST) + b"\0"))
    assert s.data["char"]["quests"]["active"][str(TALK_QUEST)]["counts"][0] == 1


def test_lists_layout():
    s = Session()
    s.data["char"]["quests"] = {"active": {str(TALK_QUEST): {"counts": [1, 0, 0, 0, 0], "time": 7, "tracked": True}},
                                "done": [1150106, 1150107]}
    quest.send_lists(s)
    active, finished = (bytes(w.buf) for w in s.sent)
    assert s.sent[0].proto == quest.S2C_ACTIVE and s.sent[1].proto == quest.S2C_FINISHED
    assert struct.unpack_from("<H", active)[0] == 1 and len(active) == 2 + 26
    e = active[2:]
    assert obf.dec_u32(e[:4]) == TALK_QUEST and T1[e[4]] & 1 == 1 and struct.unpack_from("<Q", e, 5)[0] == 7
    assert e[13] == 1 and struct.unpack_from("<5h", e, 16) == (1, 0, 0, 0, 0)
    assert struct.unpack_from("<H", finished)[0] == 2 and len(finished) == 2 + 2 * 5 + 4
    assert obf.dec_u32(finished[3:7]) == 1150106 and obf.dec_u32(finished[8:12]) == 1150107


def test_new_character_lists_are_empty():
    s = Session()
    quest.send_lists(s)
    assert [bytes(w.buf) for w in s.sent] == [b"\0\0", b"\0\0" + bytes(4)]


def test_entering_the_bound_area_meets_the_questbound_condition(world_role):
    role, st = world_role
    s = Session()
    s.data["char"]["quests"] = {"active": {str(BOUND_QUEST): {"counts": [0] * 5}}, "done": [TALK_QUEST]}
    role.handlers[quest.C2S_AREA](s, pkt(quest.C2S_AREA, obf.u32(10353) + struct.pack("<I", 6310)))
    assert s.sent[0].proto == quest.S2C_AREA and bytes(s.sent[0].buf) == b"\0\0"
    out = bytes(s.sent[1].buf)
    assert s.sent[1].proto == quest.S2C_PROGRESS and out[0] == 1 and obf.dec_u32(out[13:]) == BOUND_QUEST
    assert s.data["char"]["quests"]["active"][str(BOUND_QUEST)]["counts"][0] == 1 and st.saves == 1


def test_other_areas_are_answered_without_progress(world_role):
    role, st = world_role
    s = Session()
    s.data["char"]["quests"] = {"active": {str(BOUND_QUEST): {"counts": [0] * 5}}, "done": []}
    role.handlers[quest.C2S_AREA](s, pkt(quest.C2S_AREA, obf.u32(10353) + struct.pack("<I", 11501021)))
    assert [w.proto for w in s.sent] == [quest.S2C_AREA] and st.saves == 0


@pytest.mark.parametrize("proto", [quest.C2S_ACCEPT, quest.C2S_PROGRESS, quest.C2S_COMPLETE, quest.C2S_ABANDON,
                                   quest.C2S_TRACK, quest.C2S_AREA])
def test_short_quest_requests_are_ignored(world_role, proto):
    role, st = world_role
    s = Session()
    role.handlers[proto](s, pkt(proto, b"\0\0\0"))
    assert s.sent == [] and st.saves == 0


WARP_QUEST = 1150110    # QuestAccept_Action SpotWarp 620 (10352, start point group 2)


def test_spotwarp_accept_enters_the_field_room_at_the_warp_group(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["game_addr"] = ("127.0.0.1", 25004)
    s.data["char"].update(spot=10352, pos=[0, 0, 0], quests={"active": {}, "done": [TALK_QUEST, BOUND_QUEST, 1150109]})
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(WARP_QUEST)))
    assert [w.proto for w in s.sent] == [quest.S2C_ACCEPT, world.S2C_WARP_PROCESS, world.S2C_GAME_SERVER]
    out = bytes(s.sent[1].buf)
    assert out[0] == 1 and obf.dec_u32(out[1:5]) == 620 and out[5] == world.WARP_KIND_FIELD
    c = s.data["char"]
    assert c["pos"] == [325660, 0, 184365] and c["field_group"] == [10352, 2] and s.data["battle_spot"] == 10352


def test_spotwarp_only_on_accept():
    s = Session()
    s.data["char"].update(spot=10352, pos=[1, 2, 3], quests={"active": {str(WARP_QUEST): {"counts": [0] * 5}}, "done": []})
    quest.send_lists(s)
    assert [w.proto for w in s.sent] == [quest.S2C_ACTIVE, quest.S2C_FINISHED] and s.data["char"]["pos"] == [1, 2, 3]


def test_completion_grants_the_reward_items_into_the_bag(world_role):
    from kuf2 import items, world
    role, st = world_role
    s = Session()
    s.data["char"]["quests"] = {"active": {str(BOUND_QUEST): {"counts": [1, 0, 0, 0, 0]}}, "done": [TALK_QUEST]}
    role.handlers[quest.C2S_COMPLETE](s, pkt(quest.C2S_COMPLETE, obf.u32(BOUND_QUEST) + b"\0"))
    protos = [w.proto for w in s.sent]
    assert protos[0] == quest.S2C_COMPLETE and world.S2C_CARGO in protos
    assert T1[bytes(s.sent[0].buf)[2]] & 1 == 1                     # the client announces the reward items
    serial = s.data["char"]["bag"][0]["serial"]
    assert serial >> 32 == s.data["char"]["id"] and serial & 0xffffffff
    assert s.data["char"]["bag"] == [{"code": 350000010, "slot": 0, "count": 1,
                                      "serial": serial, "bound": False}]   # questtable 1150106 Item3
    cargo = bytes(next(w for w in s.sent if w.proto == world.S2C_CARGO).buf)
    assert struct.unpack_from("<H", cargo, 7)[0] == 1
    assert items.decode_head(cargo[9:9 + items.HEAD]) == (350000010, 0, 1, serial)


@pytest.mark.parametrize("cls,code", [(0, 101101110), (3, 101201110), (5, 101501110)])
def test_category_rewards_follow_the_hero_class(cls, code):
    from kuf2 import tables
    assert quest.reward_items(tables.by_id("questtable")["1150110"], cls) == [(code, 1)]


def test_quest_without_items_is_not_announced(world_role):
    role, _ = world_role
    s = Session()
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(TALK_QUEST)))
    role.handlers[quest.C2S_PROGRESS](s, pkt(quest.C2S_PROGRESS, struct.pack("<H", 1) + obf.u32(TALK_QUEST) + b"\0"))
    role.handlers[quest.C2S_COMPLETE](s, pkt(quest.C2S_COMPLETE, obf.u32(TALK_QUEST) + b"\0"))
    out = next(bytes(w.buf) for w in s.sent if w.proto == quest.S2C_COMPLETE)
    assert T1[out[2]] & 1 == 0 and "bag" not in s.data["char"]


DELIVERY_QUEST = 1010907    # Accept_Reward Item 451000060 x1, Collect Yes, Finsh_Collect Yes


def test_accept_hands_over_the_accept_items_and_completion_takes_them_back(world_role):
    role, _ = world_role
    s = Session()
    quest_row = tables.by_id("questtable")[str(DELIVERY_QUEST)]
    assert quest.accept_items(quest_row, 0) == [(451000060, 1)]
    s.data["char"]["quests"] = {"active": {}, "done": []}
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(DELIVERY_QUEST)))
    assert [(i["code"], i["count"]) for i in s.data["char"]["bag"]] == [(451000060, 1)]
    s.data["char"]["quests"]["active"][str(DELIVERY_QUEST)]["counts"] = [99] * 5
    role.handlers[quest.C2S_COMPLETE](s, pkt(quest.C2S_COMPLETE, obf.u32(DELIVERY_QUEST) + b"\0"))
    assert all(i["code"] != 451000060 for i in s.data["char"]["bag"])


def test_abandon_takes_the_accept_items_back(world_role):
    role, _ = world_role
    s = Session()
    s.data["char"]["quests"] = {"active": {}, "done": []}
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(DELIVERY_QUEST)))
    role.handlers[quest.C2S_ABANDON](s, pkt(quest.C2S_ABANDON, obf.u32(DELIVERY_QUEST)))
    assert s.data["char"]["bag"] == [] and str(DELIVERY_QUEST) not in s.data["char"]["quests"]["active"]


def test_a_tarantula_kill_moves_the_kill_quest():
    s = Session()
    s.data["char"]["quests"] = {"active": {"1150202": {"counts": [0] * 5}}, "done": []}
    st = State()
    quest.on_kill(s, st, 154030)            # Mist Forest Tarantula: npname 1000086 = 1150202 Complete1_ID2
    assert s.data["char"]["quests"]["active"]["1150202"]["counts"][0] == 1 and st.saves == 1
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == quest.S2C_PROGRESS and struct.unpack_from("<h", out, 1)[0] == 1
    quest.on_kill(s, st, 154040)            # a small tarantula is another name
    assert s.data["char"]["quests"]["active"]["1150202"]["counts"][0] == 1


def test_spotwarp_in_a_field_room_reenters_at_the_warp_group(world_role):
    from kuf2 import game, world
    role, st = world_role
    s = Session()
    s.data.update(battle_spot=10352, game_addr=("127.0.0.1", 25004))
    s.data["char"].update(spot=10352, pos=[0, 0, 0], gold=1234,
                          quests={"active": {}, "done": [TALK_QUEST, BOUND_QUEST, 1150109]})
    role.handlers[quest.C2S_ACCEPT](s, pkt(quest.C2S_ACCEPT, accept_body(WARP_QUEST)))
    assert [w.proto for w in s.sent] == [quest.S2C_ACCEPT, world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]
    warp, esc = bytes(s.sent[1].buf), bytes(s.sent[2].buf)
    assert warp[0] == 1 and obf.dec_u32(warp[1:5]) == 620 and warp[5] == world.WARP_KIND_FIELD
    blk = esc[2:]
    assert esc[:2] == b"\0\0" and len(blk) == 0x1d and blk[0:5] == obf.u40(0)
    assert obf.dec_pos_xz(blk[7:11], blk[13]) == (325660, 184365)
    assert blk[0x16] == world.WARP_KIND_FIELD and obf.dec_u32(blk[0x17:0x1b]) == 10352
    assert struct.unpack_from("<H", blk, 0x1b)[0] == game.MY_SLOT
    s.run_later()                               # then the game server again
    assert s.sent[-1].proto == world.S2C_GAME_SERVER and struct.unpack_from("<H", bytes(s.sent[-1].buf), 2)[0] == 25004
    assert s.data["char"]["pos"] == [325660, 0, 184365]


# nearest group 2 or group 1; group 2's only warp is 620 (15_LEV_MistForest, quest 1150110's SpotWarp), which a plain
# entry would replay (BattleField OnEnter runs the pending warp's EnterScript every time): it takes group 1 instead
@pytest.mark.parametrize("pos, warp", [([330131, 0, 191680], 205), ([321653, 3911, 169056], 205)])
def test_entering_a_field_goes_on_to_its_battle_room_at_the_nearest_group(world_role, pos, warp):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["char"].update(spot=10352, pos=pos, quests={"active": {}, "done": []})
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(10352)))
    assert s.sent[0].proto == world.S2C_ENTER_TOWN and "battle_spot" not in s.data
    n = len(s.sent)
    s.run_later()
    out = s.sent[n:]
    assert [w.proto for w in out] == [world.S2C_WARP_PROCESS, world.S2C_GAME_SERVER]
    assert obf.dec_u32(bytes(out[0].buf)[1:5]) == warp and s.data["battle_spot"] == 10352


def test_entering_a_city_stays_in_the_town_state(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["char"].update(spot=world.START_SPOT, pos=list(world.START_POS), quests={"active": {}, "done": []})
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(world.START_SPOT)))
    assert s.pending == [] and s.sent[0].proto == world.S2C_ENTER_TOWN


def test_a_spider_kill_moves_the_group_kill_quest():
    s = Session()
    s.data["char"]["quests"] = {"active": {"1150204": {"counts": [0] * 5}}, "done": []}
    st = State()
    quest.on_kill(s, st, 154050)            # npname group 1000102 = 1150204 Complete1 NPGroupKill
    quest.on_kill(s, st, 154150)            # the other troop of the group
    quest.on_kill(s, st, 154160)            # 1000085: Complete2 NPNameKill of the same quest
    assert s.data["char"]["quests"]["active"]["1150204"]["counts"][:2] == [2, 1]
    quest.on_kill(s, st, 154030)            # a tarantula: neither
    assert s.data["char"]["quests"]["active"]["1150204"]["counts"][:2] == [2, 1]


KOBOLD_POWDER = 451000231   # 1150203 ItemGain x2; item_drop_quest: troop 154050 drops it at rate 100000 while held


def test_quest_drops_fill_the_itemgain_condition_then_stop():
    s = Session()
    s.data["char"].update(gold=0, quests={"active": {"1150203": {"counts": [0] * 5}}, "done": []})
    st = State()
    for _ in range(3):
        quest.drop_items(s, st, 154050)
    bag = s.data["char"]["bag"]
    assert [(i["code"], i["count"]) for i in bag] == [(KOBOLD_POWDER, 2)]       # the third kill drops nothing
    assert s.data["char"]["quests"]["active"]["1150203"]["counts"][0] == 2
    assert any(w.proto == quest.S2C_PROGRESS for w in s.sent)


def test_no_quest_drop_without_the_quest_or_below_the_rate():
    s = Session()
    s.data["char"].update(gold=0, quests={"active": {}, "done": []})
    quest.drop_items(s, State(), 154050)
    assert s.data["char"].get("bag", []) == []
    s.data["char"]["quests"]["active"]["1150203"] = {"counts": [0] * 5}
    quest.drop_items(s, State(), 154050, roll=lambda n: n - 1)      # the highest roll (99999) still hits rate 100000
    assert len(s.data["char"]["bag"]) == 1
    quest.drop_items(s, State(), 154030, roll=lambda n: 0)          # a tarantula has no drop for this quest
    assert s.data["char"]["bag"][0]["count"] == 1


def test_gold_inside_a_battle_room_goes_with_the_bag_refresh(world_role):
    from kuf2 import world
    s = Session()
    s.data["char"].update(gold=100, bag=[])
    world.add_gold(s, State(), 50)
    assert core(s.sent)[-1].proto == world.S2C_GOLD
    s.data["battle_spot"] = 10352
    world.add_gold(s, State(), 50)
    assert core(s.sent)[-1].proto == world.S2C_CARGO and bytes(core(s.sent)[-1].buf)[:5] == obf.u40(200)
    assert all(w.proto != world.S2C_GOLD for w in core(s.sent)[1:])


def test_a_field_without_a_zone_file_stays_in_the_town_state(world_role, monkeypatch):
    from kuf2 import world, zone
    role, st = world_role
    monkeypatch.setattr(zone, "available", lambda spot: False)
    s = Session()
    s.data["char"].update(spot=10352, pos=[330131, 0, 191680], quests={"active": {}, "done": []})
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(10352)))
    assert s.pending == [] and "battle_spot" not in s.data


def test_quest_changes_in_a_mission_battle_send_no_props():
    from kuf2 import zone
    s = Session()
    s.data.update(battle_spot=10303)
    before = zone.content.cache_info().misses
    quest.field_props(s, 1150201)
    assert s.sent == [] and zone.content.cache_info().misses == before


def test_a_mission_warp_enters_the_mission_and_field_currentwarp_enters_the_spot(world_role):
    from kuf2 import world
    s = Session()
    s.data.update(game_addr=("127.0.0.1", 25004), battle_spot=10352)
    s.data["char"].update(spot=10352, pos=[0, 0, 0], quests={"active": {}, "done": []})
    quest.spot_warp(s, State(), 1150301)                    # SpotWarp 613: 10358 MISSION (a mission battle)
    assert [w.proto for w in s.sent] == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]
    assert obf.dec_u32(bytes(s.sent[0].buf)[1:5]) == 613 and s.data["char"]["spot"] == 10352   # the room's group 0
    assert s.data["char"]["mission"] == {"spot": 10358, "quest": 1150301, "back": 10350}
    s.run_later()
    assert s.sent[-1].proto == world.S2C_GAME_SERVER and struct.unpack_from("<I", bytes(s.sent[-1].buf), 8)[0] == 10358
    s.sent.clear()
    s.data["battle_spot"] = 10352
    quest.spot_warp(s, State(), 1160416, "Finish")          # CurrentWarp 10360: New Hampton Highway zone 2 (Field)
    assert [w.proto for w in s.sent] == [world.S2C_WARP_PROCESS, world.S2C_MISSION_ESCAPE]
    assert obf.dec_u32(bytes(s.sent[0].buf)[1:5]) == 624                 # warpinfo 624: 10360 group 0
    s.run_later()
    assert s.sent[-1].proto == world.S2C_GAME_SERVER and s.data["char"]["spot"] == 10360
    assert s.data["char"]["field_group"] == [10360, 0]


def test_the_clients_enter_request_after_a_quests_mission_warp_does_not_enter_twice(world_role):
    # live 2026-09-30 13:44:12: accepting 1150301 in Glen's camp warped out to 10358; the client answered the warp with
    # its own 0x3f48 for 10358, the server ran the entry again (a second warp, a second escape), two 0x3f41 went out,
    # the client logged in to the game server twice (13:44:17, 13:44:18) and hung on the loading screen (owner: "after
    # leave the first area the game stuck when we go to the mission with thompson")
    role, st = world_role
    s = Session()
    s.data.update(game_addr=("127.0.0.1", 25004), battle_spot=10352)
    s.data["char"].update(spot=10352, pos=[0, 0, 0], quests={"active": {}, "done": []})
    quest.spot_warp(s, State(), 1150301)
    role.handlers[world.C2S_ENTER_SPOT](s, pkt(world.C2S_ENTER_SPOT, obf.u32(10358) + b"\x00"))
    s.run_later()
    sent = [w.proto for w in s.sent]
    assert sent.count(world.S2C_MISSION_ESCAPE) == 1 and sent.count(world.S2C_WARP_PROCESS) == 1
    assert sent.count(world.S2C_GAME_SERVER) == 1


def test_login_into_a_field_uses_the_last_entry_group(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["char"].update(spot=10350, pos=[278357, 0, 190736], field_group=[10350, 2],
                          quests={"active": {}, "done": []})
    role.handlers[world.C2S_ENTER_TOWN](s, pkt(world.C2S_ENTER_TOWN, obf.u32(10350)))
    s.run_later()
    assert obf.dec_u32(bytes(s.sent[-2].buf)[1:5]) == 607      # group 2, though the saved position is group 0's


# the owner's requests, live 2026-09-27 12:44: an HP potion from the quick slot, then the gift box in the bag
LIVE_USE = bytes.fromhex("9716971610c3b0664e20000010c7c7c3c7c3c3c3101210c3971610")
LIVE_OPEN = bytes.fromhex("10c7c7c387c3c3c31012011033")
LIVE_TAKE = bytes.fromhex("10c7c7c387c3c3c310120110330000")    # 0x1669 after the result window, live 13:24
POTION = {"code": 350000010, "slot": 0, "count": 1, "serial": 0x100010001, "bound": False}
BOX = {"code": 602001403, "slot": 2, "count": 1, "serial": 0x100010004, "bound": True}


def test_a_potion_from_the_quick_slot_is_used_up_and_heals_the_hero_in_the_room(world_role):
    from kuf2 import combat, world
    role, st = world_role
    room = Session()
    room.data["battle"] = combat.Battle()
    room.data["battle"].add_hero(0, 1000)
    room.data["battle"].troops[0]["hp"] = 300
    room.w = type("W", (), {"is_closing": lambda self: False})()
    st.game_sessions = {7: room}
    s = Session()
    s.data["account"] = {"id": 7}
    s.data["char"].update(gold=0, bag=[dict(POTION)])
    role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, LIVE_USE))
    out = bytes(s.sent[0].buf)
    assert s.sent[0].proto == world.S2C_USE_ITEM and out[:2] == bytes(2) and obf.dec_u32(out[2:6]) == 350000010
    assert s.data["char"]["bag"] == []
    assert [w.proto for w in s.sent[1:3]] == [world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert room.data["battle"].troops[0]["hp"] == 900 and room.sent[-2].proto == 0x505d        # +600
    heal = bytes(room.sent[-1].buf)                                 # 0x505e: kind 2, the hero, no source, 600
    assert room.sent[-1].proto == 0x505e and heal[:10] == struct.pack("<IHI", 2, 0, 0) and heal[10:] == bytes([0, 0, 0x58, 2])
    role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, LIVE_USE))                   # none left
    assert s.sent[-1].proto == world.S2C_USE_ITEM and bytes(s.sent[-1].buf) == struct.pack("<H", world.ITEM_USE_REFUSED)


def test_the_gift_box_opens_into_its_group_items(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["char"].update(gold=0, bag=[dict(POTION), dict(BOX)])
    role.handlers[world.C2S_OPEN_CONTAINER](s, pkt(world.C2S_OPEN_CONTAINER, LIVE_OPEN))
    assert sorted(i["code"] for i in s.data["char"]["bag"]) == [350000010, 602001403]      # shown, not given yet
    role.handlers[world.C2S_TAKE_CONTAINER](s, pkt(world.C2S_TAKE_CONTAINER, LIVE_TAKE))
    assert any(w.proto == world.S2C_TAKE_CONTAINER and bytes(w.buf) == bytes(2) for w in s.sent)
    res = next(w for w in s.sent if w.proto == world.S2C_OPEN_CONTAINER)
    b = bytes(res.buf)
    assert b[:2] == bytes(2) and b[2:7] == obf.u40(0) and struct.unpack_from("<H", b, 7)[0] == 2
    entries = [(obf.dec_u16(b[9 + 8 * i:11 + 8 * i]), obf.dec_u32(b[11 + 8 * i:15 + 8 * i])) for i in range(2)]
    assert sorted(entries) == [(1, 351100030), (1, 605002205)]                # item_container group 2001403
    codes = sorted(i["code"] for i in s.data["char"]["bag"])
    assert codes == [350000010, 351100030, 605002205]                          # the box is gone
    role.handlers[world.C2S_OPEN_CONTAINER](s, pkt(world.C2S_OPEN_CONTAINER, LIVE_OPEN))    # no box left
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.BAG_FULL)


def bag_req(proto, *parts):
    return pkt(proto, b"".join(parts))


def test_bag_moves_and_swaps_whole_stacks(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    a = {"code": 350000010, "slot": 0, "count": 5, "serial": 11, "bound": False}
    b = {"code": 100000001, "slot": 1, "count": 1, "serial": 12, "bound": True}
    s.data["char"].update(bag=[a, b])
    role.handlers[world.C2S_BAG_MOVE](s, bag_req(world.C2S_BAG_MOVE, obf.u16(0), obf.u16(7), obf.u64(11), obf.u64(0)))
    assert bytes(s.sent[-4].buf) == bytes(2) and a["slot"] == 7 and s.sent[-3].proto == world.S2C_QUICK_BAR_SLOT
    assert s.sent[-2].proto == world.S2C_CARGO_CHANGE
    assert s.sent[-1].proto == world.S2C_CARGO                         # 0x1647 moves nothing: the bag follows
    role.handlers[world.C2S_BAG_MOVE](s, bag_req(world.C2S_BAG_MOVE, obf.u16(7), obf.u16(1), obf.u64(11), obf.u64(12)))
    assert (a["slot"], b["slot"]) == (1, 7)
    role.handlers[world.C2S_BAG_MOVE](s, bag_req(world.C2S_BAG_MOVE, obf.u16(3), obf.u16(4), obf.u64(11), obf.u64(0)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.BAG_MOVE_REFUSED) and a["slot"] == 1   # not at slot 3


def test_bag_split_makes_a_new_stack_and_merges_onto_the_same_item(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    a = {"code": 350000010, "slot": 0, "count": 10, "serial": 11, "bound": False}
    s.data["char"].update(bag=[a])
    role.handlers[world.C2S_BAG_SPLIT](s, bag_req(world.C2S_BAG_SPLIT, obf.u16(0), obf.u16(4), obf.u64(11), obf.u16(3)))
    new = next(i for i in s.data["char"]["bag"] if i["slot"] == 4)
    assert a["count"] == 7 and new["count"] == 3 and new["serial"] != 11 and s.sent[-1].proto == world.S2C_CARGO
    role.handlers[world.C2S_BAG_SPLIT](s, bag_req(world.C2S_BAG_SPLIT, obf.u16(0), obf.u16(4), obf.u64(11), obf.u16(2)))
    assert a["count"] == 5 and new["count"] == 5
    role.handlers[world.C2S_BAG_SPLIT](s, bag_req(world.C2S_BAG_SPLIT, obf.u16(0), obf.u16(5), obf.u64(11), obf.u16(9)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.BAG_MOVE_REFUSED)       # only 5 there


def test_store_buy_takes_gold_and_puts_the_item_in_the_bag(world_role):
    from kuf2 import items, world
    role, st = world_role
    code, _ = items.sale_slot(103, 0)                   # npctable 6's STORE_CONSUME menu value
    price = items.buy_price(code)
    s = Session()
    s.data["char"].update(gold=price * 2, bag=[])
    body = obf.u16(6) + struct.pack("<I", 0) + struct.pack("<I", 103) + obf.u16(2) + bytes([0])
    role.handlers[world.C2S_STORE_BUY](s, pkt(world.C2S_STORE_BUY, body))
    out = bytes(next(w for w in s.sent if w.proto == world.S2C_STORE_BUY).buf)
    assert out[:2] == bytes(2) and len(out) == 15 and out[10:15] == obf.u40(0)
    assert [(i["code"], i["count"], i["slot"]) for i in s.data["char"]["bag"]] == [(code, 2, 6)]
    role.handlers[world.C2S_STORE_BUY](s, pkt(world.C2S_STORE_BUY, body))              # no gold left
    out = bytes(s.sent[-1].buf)                          # 15 bytes on a refusal too: the handler reads them all
    assert out[:2] == struct.pack("<H", world.NOT_ENOUGH_GOLD) and len(out) == 15


def test_selling_to_a_store_pays_the_sell_price(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["char"].update(gold=10, bag=[{"code": 350000010, "slot": 2, "count": 5, "serial": 21, "bound": False}])
    role.handlers[world.C2S_STORE_SELL](s, pkt(world.C2S_STORE_SELL, obf.u16(3) + obf.u16(2) + obf.u64(21)))
    assert s.data["char"]["gold"] == 10 + 3 * 8 and s.data["char"]["bag"][0]["count"] == 2      # SellPrice 8
    assert s.sent[-1].proto == world.S2C_CARGO
    role.handlers[world.C2S_STORE_SELL](s, pkt(world.C2S_STORE_SELL, obf.u16(3) + obf.u16(2) + obf.u64(21)))
    assert s.data["char"]["gold"] == 34                                              # only 2 left: refused


def test_a_potion_placed_on_the_quick_bar_comes_back_at_the_next_login(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["char"].update(bag=[dict(POTION, slot=5)])
    # the bag's register call (0x140dcde6d): group 0, bar slot 3, kind 0, bag slot 0, item code, type 2
    req = bytes([0, 2, 3, 0]) + struct.pack("<I", 350000010) + struct.pack("<h", 0) + bytes([0])
    role.handlers[world.C2S_QUICK_SLOT_SET](s, pkt(world.C2S_QUICK_SLOT_SET, req))
    assert [w.proto for w in s.sent] == [world.S2C_QUICK_SLOT_SET] and bytes(s.sent[0].buf)[:2] == bytes(2)
    role.handlers[world.C2S_QUICK_SLOT_PAGE](s, pkt(world.C2S_QUICK_SLOT_PAGE, bytes([0])))
    b = bytes(s.sent[-1].buf)
    assert b[:2] == bytes([0, 0])                                        # page 0, no type-0 slots
    assert b[2] == 1 and struct.unpack_from("<Q", b, 3)[0] == 1           # one type-2 slot for hero uid 1
    assert b[11:13] == bytes([0, 3]) and struct.unpack_from("<h", b, 13)[0] == 5   # kind 0, bar slot 3, bag slot now 5
    assert obf.dec_u32(b[15:19]) == 350000010 and len(b) == 19
    role.handlers[world.C2S_QUICK_SLOT_PAGE](s, pkt(world.C2S_QUICK_SLOT_PAGE, bytes([4])))
    assert bytes(s.sent[-1].buf) == bytes([4]) + struct.pack("<Q", 1) + bytes([0])
    role.handlers[world.C2S_QUICK_SLOT_CLEAR](s, pkt(world.C2S_QUICK_SLOT_CLEAR, bytes([3, 2, 0])))
    assert bytes(s.sent[-1].buf) == bytes(2) + bytes([3, 2, 0]) and s.data["char"]["quick_slots"] == {}


def test_the_warehouse_keeps_items_and_gold(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    a = {"code": 350000010, "slot": 0, "count": 10, "serial": 11, "bound": False}
    s.data["char"].update(gold=500, bag=[a])
    role.handlers[world.C2S_WAREHOUSE_LIST](s, pkt(world.C2S_WAREHOUSE_LIST, bytes([0])))
    out = bytes(s.sent[-1].buf)
    assert out[0] == 0 and struct.unpack_from("<h", out, 1)[0] == world.WAREHOUSE_SLOTS and out[3:8] == obf.u40(0)
    assert out[8:10] == bytes(2)                                                          # empty
    # 4 of the 10 potions into warehouse slot 2 (the builder's order: serial, target slot, target serial, count, slot)
    body = obf.u64(11) + obf.u16(2) + obf.u64(0) + obf.u16(4) + obf.u16(0)
    role.handlers[world.C2S_BAG_TO_WAREHOUSE](s, pkt(world.C2S_BAG_TO_WAREHOUSE, body))
    assert [w.proto for w in s.sent[-3:]] == [world.S2C_BAG_TO_WAREHOUSE, world.S2C_WAREHOUSE_LIST, world.S2C_CARGO]
    kept = s.data["char"]["warehouse"]
    assert a["count"] == 6 and [(i["code"], i["slot"], i["count"]) for i in kept] == [(350000010, 2, 4)]
    # all of it back onto the bag stack
    back = obf.u64(kept[0]["serial"]) + obf.u16(0) + obf.u64(11) + obf.u16(4) + obf.u16(2)
    role.handlers[world.C2S_WAREHOUSE_TO_BAG](s, pkt(world.C2S_WAREHOUSE_TO_BAG, back))
    assert bytes(s.sent[-3].buf) == bytes(2) and a["count"] == 10 and s.data["char"]["warehouse"] == []
    # a stale target serial is refused
    role.handlers[world.C2S_BAG_TO_WAREHOUSE](s, pkt(world.C2S_BAG_TO_WAREHOUSE, body))
    moved = s.data["char"]["warehouse"][0]
    stale = obf.u64(11) + obf.u16(2) + obf.u64(99) + obf.u16(1) + obf.u16(0)
    role.handlers[world.C2S_BAG_TO_WAREHOUSE](s, pkt(world.C2S_BAG_TO_WAREHOUSE, stale))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.WAREHOUSE_REFUSED) and moved["count"] == 4
    # inside the warehouse: whole move, then the sort packs it back to slot 0
    mv = obf.u16(2) + obf.u16(9) + obf.u64(moved["serial"]) + obf.u64(0)
    role.handlers[world.C2S_WAREHOUSE_MOVE](s, pkt(world.C2S_WAREHOUSE_MOVE, mv))
    assert bytes(s.sent[-2].buf) == bytes(2) and moved["slot"] == 9 and s.sent[-1].proto == world.S2C_WAREHOUSE_LIST
    role.handlers[world.C2S_WAREHOUSE_MOVE](s, pkt(world.C2S_WAREHOUSE_MOVE, obf.u16(9) + obf.u16(16) + mv[4:]))
    assert moved["slot"] == 9                                                           # past the open slots
    role.handlers[world.C2S_WAREHOUSE_SORT](s, pkt(world.C2S_WAREHOUSE_SORT, b""))
    assert moved["slot"] == 0 and s.sent[-1].proto == world.S2C_WAREHOUSE_LIST
    # gold: 200 in, 50 out, then more than is kept
    role.handlers[world.C2S_WAREHOUSE_GOLD](s, pkt(world.C2S_WAREHOUSE_GOLD, obf.u40(200) + bytes([0])))
    assert bytes(s.sent[-1].buf) == bytes(2) + obf.u40(200) + obf.u40(300)
    role.handlers[world.C2S_WAREHOUSE_GOLD](s, pkt(world.C2S_WAREHOUSE_GOLD, obf.u40(50) + bytes([1])))
    assert (s.data["char"]["gold"], s.data["char"]["warehouse_gold"]) == (350, 150)
    role.handlers[world.C2S_WAREHOUSE_GOLD](s, pkt(world.C2S_WAREHOUSE_GOLD, obf.u40(151) + bytes([1])))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.NOT_ENOUGH_GOLD)
    assert obf.dec_u40(obf.u40(0x12_3456_789A)) == 0x12_3456_789A


def test_a_whole_stack_onto_another_item_swaps_across_bag_and_warehouse(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    a = {"code": 350000010, "slot": 3, "count": 5, "serial": 11, "bound": False}
    b = {"code": 100000001, "slot": 7, "count": 1, "serial": 12, "bound": True}
    s.data["char"].update(bag=[a], warehouse=[b])
    part = obf.u64(11) + obf.u16(7) + obf.u64(12) + obf.u16(2) + obf.u16(3)          # part of it: refused
    role.handlers[world.C2S_BAG_TO_WAREHOUSE](s, pkt(world.C2S_BAG_TO_WAREHOUSE, part))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.WAREHOUSE_REFUSED) and (a["slot"], b["slot"]) == (3, 7)
    whole = obf.u64(11) + obf.u16(7) + obf.u64(12) + obf.u16(5) + obf.u16(3)
    role.handlers[world.C2S_BAG_TO_WAREHOUSE](s, pkt(world.C2S_BAG_TO_WAREHOUSE, whole))
    assert s.data["char"]["bag"] == [b] and s.data["char"]["warehouse"] == [a] and (a["slot"], b["slot"]) == (7, 3)


def test_lobby_and_account_requests(world_role):
    from kuf2 import world
    role, st = world_role
    c1, c2 = {"id": 1, "name": "Aldric", "class": 0}, {"id": 2, "name": "Other", "class": 0}
    acct = {"id": 7, "name": "a", "characters": [c1, c2]}
    st.db = {"accounts": {"k": acct}}
    s = Session()
    s.data["account"] = acct
    role.handlers[world.C2S_NAME_CHECK](s, pkt(world.C2S_NAME_CHECK, b"Aldric\0"))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.NAME_TAKEN)
    role.handlers[world.C2S_NAME_CHECK](s, pkt(world.C2S_NAME_CHECK, b"Nobody\0"))
    assert bytes(s.sent[-1].buf) == bytes(2)
    flag = next(b for b in range(256) if T1[b] & 1)                   # "delete", as the client codes it
    role.handlers[world.C2S_CHAR_DELETE](s, pkt(world.C2S_CHAR_DELETE, bytes([flag]) + struct.pack("<I", c2["id"])))
    out = bytes(s.sent[-1].buf)
    assert len(out) == 15 and out[0] == 0 and struct.unpack_from("<Ih", out, 1) == (c2["id"], 0)
    assert acct["characters"] == [c1] and acct["deleted"] == [c2]
    role.handlers[world.C2S_CHAR_DELETE](s, pkt(world.C2S_CHAR_DELETE, bytes([flag]) + struct.pack("<I", 999)))
    assert struct.unpack_from("<h", bytes(s.sent[-1].buf), 5)[0] == 1


def test_escape_options_and_prologue(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    q, p15 = obf.pos_xz(1000, -2000)
    req = q + struct.pack("<h", 55) + bytes([p15]) + struct.pack("<I", 1) + bytes([2])
    role.handlers[world.C2S_ESCAPE](s, pkt(world.C2S_ESCAPE, req))
    assert bytes(s.sent[-1].buf) == bytes(2) + req and s.data["char"]["pos"] == [1000, 55, -2000]
    role.handlers[world.C2S_OPTIONS](s, pkt(world.C2S_OPTIONS, bytes([2, 1, 0x15, 3, 0x40])))
    assert s.data["char"]["options"] == {"21": 1}                     # index 0x40 is past the 38 options
    role.handlers[world.C2S_PROLOGUE_DONE](s, pkt(world.C2S_PROLOGUE_DONE, b""))
    assert s.data["char"]["tutorial_done"] is True
    role.handlers[world.C2S_ATTACK_REFRESH](s, pkt(world.C2S_ATTACK_REFRESH, b""))
    assert [len(bytes(w.buf)) for w in s.sent[-2:]] == [18, 18]


def test_a_gacha_item_rolls_its_change_group(world_role):
    from kuf2 import items, world
    role, st = world_role
    # item 709000100: ChangeId 1 -> group 1 at 70% (355000000 x1) / group 2
    assert items.open_gacha(709000100, lambda n: 0) == (355000000, 1)
    s = Session()
    s.data["char"].update(level=6, bag=[{"code": 709000100, "slot": 4, "count": 2, "serial": 31, "bound": True}])
    role.handlers[world.C2S_OPEN_GACHA](s, pkt(world.C2S_OPEN_GACHA, struct.pack("<H", 4)))
    out = bytes(s.sent[-1].buf)
    assert out[:2] == bytes(2) and len(out) == 8 and s.sent[-2].proto == world.S2C_CARGO
    code, n = struct.unpack_from("<IH", out, 2)
    bag = s.data["char"]["bag"]
    assert bag[0]["count"] == 1 and any(i["code"] == code and i["count"] >= n for i in bag[1:])
    role.handlers[world.C2S_OPEN_GACHA](s, pkt(world.C2S_OPEN_GACHA, struct.pack("<H", 40)))    # nothing there
    assert bytes(s.sent[-1].buf) == struct.pack("<H", 1)


def test_crafting_a_potion_from_start_to_receive(world_role):
    from kuf2 import craft, world
    role, st = world_role
    s = Session()
    mats = [{"code": 404000100, "slot": 0, "count": 3, "serial": 41, "bound": False},
            {"code": 404000800, "slot": 1, "count": 6, "serial": 42, "bound": False}]
    s.data["char"].update(gold=5000, level=5, bag=mats)
    start = struct.pack("<II", 2, 7) + obf.u32(350000030)        # 2 crafts of recipe 350000030 (M_ALCHEMY)
    role.handlers[craft.C2S_START](s, pkt(craft.C2S_START, start))
    out = bytes(s.sent[-1].buf)
    assert out == bytes(2) + struct.pack("<i", 2) + obf.u32(350000030)
    c = s.data["char"]
    assert c["gold"] == 5000 - 1000 and [i["count"] for i in c["bag"]] == [1, 2]
    role.handlers[craft.C2S_START](s, pkt(craft.C2S_START, start))             # the group is busy
    assert bytes(s.sent[-1].buf) == struct.pack("<H", craft.REFUSED)
    role.handlers[craft.C2S_FINISH](s, pkt(craft.C2S_FINISH, struct.pack("<I", 7) + obf.u32(350000030)))
    out = bytes(s.sent[-1].buf)
    uid, level, group = struct.unpack_from("<QBi", out, 2)
    assert group == 3 and level == 1 and out[2 + 0xd:2 + 0x11] == obf.u32(350000030)
    assert struct.unpack_from("<H", out, 2 + 0x19)[0] == 1 and out[2 + 0x19 + 2:] == obf.u32(350000030) + obf.u16(20)
    role.handlers[craft.C2S_RECEIVE](s, pkt(craft.C2S_RECEIVE, struct.pack("<QI", uid, 7)))
    assert bytes(s.sent[-1].buf) == bytes(2) + struct.pack("<Q", uid)
    assert any(i["code"] == 350000030 and i["count"] == 20 for i in c["bag"]) and c["craft"]["running"] == {}
    head = bytes(craft.state_packet(c).buf)                     # alchemy is group 3: exp at +9, level at +0
    assert len(head) == 0x24 + 2 and head[0] == 1 and struct.unpack_from("<Q", head, 9)[0] == 2
    role.handlers[craft.C2S_FAVORITE](s, pkt(craft.C2S_FAVORITE, bytes([next(b for b in range(256) if obf.T1[b] & 1)]) + obf.u32(350000030)))
    assert bytes(s.sent[-1].buf) == bytes(2) + bytes([0]) + obf.u32(350000030) and c["craft"]["favorites"] == [350000030]


def test_sell_then_buy_back_and_destroy(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["char"].update(gold=0, bag=[{"code": 350000010, "slot": 2, "count": 5, "serial": 21, "bound": False}])
    role.handlers[world.C2S_STORE_SELL](s, pkt(world.C2S_STORE_SELL, obf.u16(5) + obf.u16(2) + obf.u64(21)))
    assert [w.proto for w in s.sent[-3:]] == [world.S2C_STORE_SELL, world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert bytes(s.sent[-3].buf) == obf.u40(40) + bytes(2) and s.data["char"]["bag"] == []
    role.handlers[world.C2S_REBUY_LIST](s, pkt(world.C2S_REBUY_LIST, b""))
    assert bytes(s.sent[-1].buf)[0] == 1
    role.handlers[world.C2S_REBUY](s, pkt(world.C2S_REBUY, obf.u16(3) + struct.pack("<H", 0)))
    assert [w.proto for w in s.sent[-3:]] == [world.S2C_REBUY, world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert bytes(s.sent[-3].buf) == obf.u40(0) + bytes(2)
    assert s.data["char"]["bag"] == [{"code": 350000010, "slot": 3, "count": 5, "bound": False, "enchant": 0,
                                      "serial": 21}]
    role.handlers[world.C2S_REBUY](s, pkt(world.C2S_REBUY, obf.u16(4) + struct.pack("<H", 0)))    # nothing left
    assert len(bytes(s.sent[-1].buf)) == 7
    role.handlers[world.C2S_DESTROY](s, pkt(world.C2S_DESTROY, obf.u16(3) + obf.u16(2) + obf.u64(21)))
    assert bytes(s.sent[-2].buf) == bytes(2) and s.data["char"]["bag"][0]["count"] == 3
    role.handlers[world.C2S_DESTROY](s, pkt(world.C2S_DESTROY, obf.u16(3) + obf.u16(4) + obf.u64(21)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.BAG_MOVE_REFUSED)


def test_arrange_the_bag_and_pick_from_a_choice_box(world_role):
    from kuf2 import items, world
    role, st = world_role
    s = Session()
    box = next(r["ItemCode"] for r in __import__("kuf2.tables", fromlist=["x"]).sections("item_choice_container")["Base"]
               if items.choice_container(int(r["ItemCode"])) and items.choice_container(int(r["ItemCode"]))[2])
    s.data["char"].update(gold=0, bag=[{"code": 350000010, "slot": 9, "count": 1, "serial": 21, "bound": False},
                                       {"code": int(box), "slot": 4, "count": 1, "serial": 22, "bound": True}])
    role.handlers[world.C2S_BAG_ARRANGE](s, pkt(world.C2S_BAG_ARRANGE, bytes([0])))
    out = bytes(next(w for w in s.sent if w.proto == world.S2C_BAG_ARRANGE).buf)
    assert out[:4] == bytes(2) + struct.pack("<H", 2) and sorted(i["slot"] for i in s.data["char"]["bag"]) == [0, 1]
    open_req = obf.u64(22) + obf.u16(1) + bytes([1]) + obf.u16(0)
    role.handlers[world.C2S_OPEN_CHOICE](s, pkt(world.C2S_OPEN_CHOICE, open_req))
    out = bytes(s.sent[-1].buf)
    n = struct.unpack_from("<H", out, 7)[0]
    assert out[:2] == bytes(2) and len(out) == 9 + 8 * n and n >= 1
    role.handlers[world.C2S_TAKE_CHOICE](s, pkt(world.C2S_TAKE_CHOICE, bytes([1]) + obf.u64(22) + obf.u16(0) + obf.u16(0)))
    assert bytes(s.sent[-1].buf) == bytes(2) and not any(i["code"] == int(box) for i in s.data["char"]["bag"])


def test_enchanting_a_bag_item_uses_stones_and_gold(world_role):
    from kuf2 import items, tables, world
    role, st = world_role
    weapon = next(int(r["ItemCode"]) for r in tables.sections("item_weapon")[next(iter(tables.sections("item_weapon")))]
                  if items.enchant_rule(int(r["ItemCode"]), 0) and items.enchant_rule(int(r["ItemCode"]), 0)["max"] > 0)
    rule = items.enchant_rule(weapon, 0)
    s = Session()
    s.data["char"].update(gold=rule["cost"] + 5, bag=[
        {"code": weapon, "slot": 3, "count": 1, "serial": 51, "bound": True},
        {"code": rule["material"], "slot": 4, "count": rule["count"] + 1, "serial": 52, "bound": False}])
    body = bytes([0]) + obf.u16(3) + obf.u32(rule["material"]) + obf.u64(51) + bytes([0])
    role.handlers[world.C2S_ENCHANT](s, pkt(world.C2S_ENCHANT, body))
    out = bytes(s.sent[-1].buf)
    new, outcome = struct.unpack_from("<hB", out, 2)
    assert out[:2] == bytes(2) and len(out) == 5 and s.sent[-2].proto == world.S2C_CARGO
    bag = s.data["char"]["bag"]
    assert bag[0]["enchant"] == new and bag[1]["count"] == 1 and s.data["char"]["gold"] == 5
    assert items.record(weapon, 3, 51, enchant=new)[31:33] == struct.pack("<h", new)
    role.handlers[world.C2S_ENCHANT](s, pkt(world.C2S_ENCHANT, body))           # one stone left, no gold
    assert bytes(s.sent[-1].buf) in (struct.pack("<H", world.ENCHANT_MATERIAL), struct.pack("<H", world.NOT_ENOUGH_GOLD),
                                     struct.pack("<H", world.ENCHANT_NOT_ALLOWED))


def test_dismantling_gives_the_rows_of_its_dismantle_id(world_role):
    from kuf2 import items, tables, world
    role, st = world_role
    ids = {r["DismantleId"] for r in tables.sections("item_dismantle")["Dismantle"]}
    weapon = next(int(r["ItemCode"]) for r in tables.sections("item_weapon")[next(iter(tables.sections("item_weapon")))]
                  if r.get("DismantleId") in ids)
    s = Session()
    s.data["char"].update(bag=[{"code": weapon, "slot": 3, "count": 1, "serial": 51, "bound": True}])
    role.handlers[world.C2S_DISMANTLE](s, pkt(world.C2S_DISMANTLE, obf.u16(3) + obf.u16(1) + obf.u64(51)))
    out = bytes(next(w for w in s.sent if w.proto == world.S2C_DISMANTLE).buf)
    assert out[:2] == bytes(2) and len(out) == 3 + 6 * out[2]
    assert not any(i["serial"] == 51 for i in s.data["char"]["bag"]) and core(s.sent)[-1].proto == world.S2C_CARGO


def test_the_coin_shop_rolls_goods_sells_once_and_refreshes(world_role):
    from kuf2 import coinshop, items, world
    role, st = world_role
    s = Session()
    s.data["char"].update(gold=100000, bag=[])
    role.handlers[coinshop.C2S_LIST](s, pkt(coinshop.C2S_LIST, struct.pack("<I", 55)))
    out = bytes(s.sent[-1].buf)
    n = struct.unpack_from("<H", out, 10)[0]
    assert out[:2] == bytes(2) and struct.unpack_from("<II", out, 2) == (0, 55) and n == 2 and len(out) == 12 + 8 * n
    code = s.data["char"]["coin_shop"]["55"]["items"][0][0]
    assert out[12:16] == obf.u32(code)
    price = int(items.row(code)["BuyPrice"])
    role.handlers[coinshop.C2S_BUY](s, pkt(coinshop.C2S_BUY, bytes([0]) + struct.pack("<II", 55, 6239)))
    out = bytes(s.sent[-1].buf)
    assert out[:2] == bytes(2) and len(out) == 10 and out[7] == 0          # sold flag = obool TRUE
    assert s.data["char"]["gold"] == 100000 - price and any(i["code"] == code for i in s.data["char"]["bag"])
    role.handlers[coinshop.C2S_BUY](s, pkt(coinshop.C2S_BUY, bytes([0]) + struct.pack("<II", 55, 6239)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", coinshop.BUY_FAILED)
    role.handlers[coinshop.C2S_REFRESH](s, pkt(coinshop.C2S_REFRESH, struct.pack("<I", 55)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", coinshop.NO_REFRESH)       # STORE_COIN2 has no free refresh


def test_the_skill_tree_lists_skills_with_tp_and_learns_by_the_book(world_role):
    from kuf2 import skills
    role, st = world_role
    s = Session()
    s.data["char"].update(level=15)                                  # TP from level 10: 6 points
    role.handlers[skills.C2S_INFO](s, pkt(skills.C2S_INFO, bytes(16)))
    out = bytes(s.sent[-1].buf)
    assert struct.unpack_from("<QQIH", out, 0) == (0, 1, 0, 6) and len(out) == 23 + 6 * out[22]
    # Glen's 119 (SKILLTREE1, no tree gate, 1 TP) then its level 2; 8 needs 12 TP spent in SKILLTREE1 first
    role.handlers[skills.C2S_LEARN](s, pkt(skills.C2S_LEARN, struct.pack("<HIB", 1, 119, 2)))
    assert bytes(s.sent[-2].buf) == struct.pack("<HHBBI", 0, 1, skills.handle(s.data["char"], 119), 2, 119)
    assert s.data["char"]["skills"] == {"119": 2}
    assert struct.unpack_from("<H", bytes(s.sent[-1].buf), 20)[0] == 4
    role.handlers[skills.C2S_LEARN](s, pkt(skills.C2S_LEARN, struct.pack("<HIB", 1, 8, 1)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", skills.NOT_LEARNABLE) and "8" not in s.data["char"]["skills"]
    role.handlers[skills.C2S_LEARN](s, pkt(skills.C2S_LEARN, struct.pack("<HIB", 1, 171, 1)))     # 119 restricts 171
    assert bytes(s.sent[-1].buf) == struct.pack("<H", skills.NOT_LEARNABLE)


def test_system_mail_lists_reads_and_hands_over_gold_and_items(world_role):
    from kuf2 import mail, world
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(gold=0, bag=[], name="Aldric")
    mail.deliver(s, st, c, "Reward", "Well done.", gold=100, grant=[(350000010, 3), (602001403, 1)])
    assert s.sent[-1].proto == mail.S2C_NEW and c["mail"][0]["id"] == 1
    role.handlers[mail.C2S_FLAG](s, pkt(mail.C2S_FLAG, b""))
    assert bytes(s.sent[-1].buf) == bytes([1])
    role.handlers[mail.C2S_LIST](s, pkt(mail.C2S_LIST, bytes([0])))
    out = bytes(s.sent[-1].buf)
    assert out[:4] == bytes([0, 1, 0, 1]) and out[4] == 2 and out[9] == 2 and out[-7:] == b"Reward\0"
    assert struct.unpack_from("<Q", out, 4 + 0x0d)[0] == 1
    role.handlers[mail.C2S_READ](s, pkt(mail.C2S_READ, struct.pack("<Q", 1)))
    out = bytes(s.sent[-1].buf)
    assert out[:6] == bytes(6) and out[6:17] == b"Well done.\0" and out[17:22] == obf.u40(100) and out[22] == 2
    assert len(out) == 23 + 2 * 18 and c["mail"][0]["read"]
    role.handlers[mail.C2S_TAKE_ITEM](s, pkt(mail.C2S_TAKE_ITEM, struct.pack("<QBH", 1, 1, 7)))
    assert bytes(s.sent[-1].buf) == bytes(2) and [(i["code"], i["slot"]) for i in c["bag"]] == [(602001403, 7)]
    receive = bytes([1]) + struct.pack("<IQ", 0, 1)
    role.handlers[mail.C2S_RECEIVE](s, pkt(mail.C2S_RECEIVE, receive))
    assert bytes(s.sent[-1].buf) == bytes(2) + bytes([1]) + struct.pack("<IQ", 0, 1)
    assert c["gold"] == 100 and any(i["code"] == 350000010 and i["count"] == 3 for i in c["bag"])
    role.handlers[mail.C2S_TAKE_GOLD](s, pkt(mail.C2S_TAKE_GOLD, struct.pack("<Q", 1)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", mail.TAKEN)
    role.handlers[mail.C2S_DELETE](s, pkt(mail.C2S_DELETE, bytes([1]) + struct.pack("<Q", 1)))
    assert c["mail"] == []


def test_a_grant_into_a_full_bag_is_mailed(world_role):
    from kuf2 import mail, world
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(bag=[{"code": 100000001, "slot": k, "count": 1, "serial": 100 + k, "bound": False}
                  for k in range(world.CARGO_SLOTS)])
    assert world.add_item(s, st, 350000010, 2) == 2
    assert c["mail"][0]["items"] == [{"code": 350000010, "count": 2, "taken": False}]


def test_leaving_a_field_room_and_the_town_for_the_world_map(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["char"].update(spot=10352, pos=[327931, 120, 188443], gold=7, field_group=[10352, 2])
    s.data["account"] = {"id": 3}
    s.data["battle_spot"] = 10352
    role.handlers[world.C2S_MISSION_ESCAPE](s, pkt(world.C2S_MISSION_ESCAPE, b""))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == world.S2C_MISSION_ESCAPE and len(out) == 2 + 0x1d and out[2 + 6] == 1
    assert out[2 + 0x16] == 0 and out[2 + 0x17:2 + 0x1b] == obf.u32(10352) and out[2:7] == obf.u40(0)   # gold lost by leaving: none
    assert "battle_spot" not in s.data and "field_group" not in s.data["char"]
    s.data["char"].update(spot=10001, pos=[100, 5, 200])
    role.handlers[world.C2S_LEAVE_TOWN](s, pkt(world.C2S_LEAVE_TOWN, b""))
    a, b = bytes(s.sent[-2].buf), bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == world.S2C_TO_WORLDMAP and len(a) == 13 and len(b) == 11 and a[2:9] == b[:7]
    assert struct.unpack_from("<I", a, 9)[0] == 10001 and b[7:] == obf.u32(10001)


def test_a_quest_item_used_on_its_npc_counts(world_role):
    from kuf2 import quest, world
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c["bag"] = [{"code": 451000203, "slot": 0, "count": 1, "serial": 61, "bound": True}]
    quest.record(c)["active"]["1150303"] = {"counts": [0] * quest.CONDITIONS}
    enc = obf.u32(451000203)
    body = bytes([obf.T2[(enc[0] * 8 + 1) & 0xff]]) + enc + obf.u32(6044)
    role.handlers[world.C2S_QUEST_ITEM_USE](s, pkt(world.C2S_QUEST_ITEM_USE, body))
    assert any(w.proto == world.S2C_QUEST_ITEM_USE and bytes(w.buf) == bytes(2) for w in s.sent)
    assert quest.record(c)["active"]["1150303"]["counts"][0] == 1
    wrong = bytes([obf.T2[(enc[0] * 8 + 1) & 0xff]]) + enc + obf.u32(6045)
    role.handlers[world.C2S_QUEST_ITEM_USE](s, pkt(world.C2S_QUEST_ITEM_USE, wrong))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.NOT_READY)


def test_npc_heal_charges_its_cost(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    s.data["char"].update(gold=15, bag=[])
    s.data["account"] = {"id": 3}
    body = struct.pack("<IB", 9, 1) + obf.u32(200083)
    role.handlers[world.C2S_NPC_BUFF](s, pkt(world.C2S_NPC_BUFF, body))
    assert bytes(s.sent[-1].buf) == bytes(2) and s.data["char"]["gold"] == 5
    role.handlers[world.C2S_NPC_BUFF](s, pkt(world.C2S_NPC_BUFF, body))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.NOT_ENOUGH_GOLD)
    role.handlers[world.C2S_NPC_BUFF](s, pkt(world.C2S_NPC_BUFF, struct.pack("<IB", 10, 1) + obf.u32(200083)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.BUFF_NO_ITEM)          # no potion to pay with


def test_joining_a_realm_counts_the_realm_quest(world_role):
    from kuf2 import quest, world
    role, st = world_role
    s = Session()
    c = s.data["char"]
    quest.record(c)["active"]["1160442"] = {"counts": [0] * quest.CONDITIONS}
    role.handlers[world.C2S_REALM_JOIN](s, pkt(world.C2S_REALM_JOIN, bytes([obf.T2[2 | 0x40]])))   # B, junk high bits
    assert c["realm"] == 2 and any(w.proto == world.S2C_REALM_JOIN and bytes(w.buf) == bytes(2) + bytes([obf.via_t1(2)])
                                   for w in s.sent)
    assert quest.record(c)["active"]["1160442"]["counts"][0] == 1
    role.handlers[world.C2S_REALM_JOIN](s, pkt(world.C2S_REALM_JOIN, bytes([obf.T2[1]])))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", 1) and c["realm"] == 2


def test_the_realm_window_lists_both_realms_so_the_join_is_sent_and_answered(world_role):
    """0x5a49 as 0x1406365a0 reads it: u8 n, n * (T1[b0] & 3 realm, b1 plain, T1[b2] & 1 join allowed); the menu's
    realm's bool becomes +0x3c, and clickJoin 0x140635240 refuses locally while it is 0 (planning/client/
    town_quest_npc.md 0x5a48, Gap 1). Then the 0x5a44 the Join button sends is answered 0x5a45 0 + the coded realm."""
    role, st = world_role
    s = Session()
    role.handlers[world.C2S_NPC_MENU](s, pkt(world.C2S_NPC_MENU, b""))
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == world.S2C_NPC_MENU and out[0] == 2 and len(out) == 1 + 3 * out[0]
    assert {T1[out[1 + 3 * i]] & 3: T1[out[3 + 3 * i]] & 1 for i in range(out[0])} == {1: 1, 2: 1}
    role.handlers[world.C2S_REALM_JOIN](s, pkt(world.C2S_REALM_JOIN, bytes([obf.T2[1]])))
    assert s.data["char"]["realm"] == 1
    assert any(w.proto == world.S2C_REALM_JOIN and bytes(w.buf) == bytes(2) + bytes([obf.via_t1(1)]) for w in s.sent)


def finished_ids(w):
    """The ids of a 0x5541 as 0x140d7ca70 reads it: u16 n, n * (obool, coded id), u32."""
    b = bytes(w.buf)
    return [obf.dec_u32(b[3 + 5 * i:7 + 5 * i]) for i in range(struct.unpack_from("<H", b)[0])]


def test_a_skipped_tutorial_is_finished_without_rewards_and_the_finished_list_resent(world_role):
    """0x5550 (0x140f02320, sent by the tutorial skip 0x140833160 for each tutorialquest row the player does not hold):
    the questtable row with Tutorial_Quest Yes goes on the finished list, 0x5541 is sent again (planning/client/
    town_quest_npc.md 0x5550, Gap 3). Tutorialquest rows missing from questtable (9900101: the 0x5541 reader asserts
    on them), held, finished and non-tutorial quests are left alone and get nothing."""
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c["gold"] = 5
    r = quest.record(c)
    r["active"]["9900103"] = {"counts": [0] * quest.CONDITIONS}
    r["done"].append(9900112)
    for qid in (9900101, 9900103, 9900112, TALK_QUEST):
        role.handlers[0x5550](s, pkt(0x5550, obf.u32(qid)))
    role.handlers[0x5550](s, pkt(0x5550, b"\0\0\0"))              # short: dropped
    assert s.sent == [] and r["done"] == [9900112] and st.saves == 0
    role.handlers[0x5550](s, pkt(0x5550, obf.u32(9900104)))       # TrainTroop, not held
    assert r["done"] == [9900112, 9900104] and "9900103" in r["active"] and c["gold"] == 5
    assert [w.proto for w in s.sent] == [quest.S2C_FINISHED] and finished_ids(s.sent[0]) == [9900112, 9900104]


def test_a_troop_contract_brings_a_troop_to_the_barracks_and_the_deck(world_role):
    from kuf2 import quest, skills, troops, world
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(bag=[{"code": 355000000, "slot": 2, "count": 1, "serial": 71, "bound": True}])
    role.handlers[troops.C2S_CAPACITY](s, pkt(troops.C2S_CAPACITY, b""))
    assert bytes(s.sent[-1].buf) == bytes([troops.BARRACK_BASE]) + bytes(8)
    use = bytes(6) + obf.u32(355000000) + bytes(2) + obf.u64(71) + bytes(7)                  # the 0x4042 layout
    role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, use))
    assert [w.proto for w in core(s.sent)[-4:]] == [world.S2C_USE_ITEM, troops.S2C_NEW_TROOP,
                                                 world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    assert bytes(core(s.sent)[-4].buf) == bytes(2) + obf.u32(355000000) + bytes(4)
    new = bytes(core(s.sent)[-3].buf)
    t = c["troops"][0]
    assert len(new) == 0x16 and new[0] == 6 and struct.unpack_from("<Q", new, 1)[0] == t["uid"] and new[0x15] == 1
    assert struct.unpack_from("<I", new, 0xd)[0] == 100 and c["bag"] == [] and c["troop_pedia"] == [100]
    role.handlers[troops.C2S_BARRACKS](s, pkt(troops.C2S_BARRACKS, b""))
    out = bytes(s.sent[-1].buf)
    assert struct.unpack_from("<HI", out, 0) == (1, 100) and struct.unpack_from("<Q", out, 2 + 0xd)[0] == t["uid"]
    assert len(out) == 2 + 0x18 + 1 and out[2 + 0x17] == 6
    role.handlers[troops.C2S_DETAIL](s, pkt(troops.C2S_DETAIL, struct.pack("<Q", t["uid"])))
    out = bytes(s.sent[-1].buf)
    # it comes with its default skill, 81001 in slot 0 (troops.default_skills): u8 n, (slot, level, ability)
    assert out[10] == 1 and struct.unpack_from("<BBI", out, 11) == (0, 1, 81001)
    assert len(out) == 2 + 8 + 1 + 6 + troops.DETAIL_BLOCK + 1 + 1 and struct.unpack_from("<Q", out, 17 + 0xa2)[0] == 181
    role.handlers[skills.C2S_INFO](s, pkt(skills.C2S_INFO, struct.pack("<QQ", t["uid"], 0)))
    assert bytes(s.sent[-1].buf) == struct.pack("<QHB", t["uid"], 0, 1) + struct.pack("<BIB", 0, 81001, 1) + bytes(12)
    # the tutorial: into deck slot 1 of the main deck (key -1), the client's counter for 9900103
    quest.record(c)["active"]["9900103"] = {"counts": [0] * quest.CONDITIONS}
    drag = bytes([1, 1]) + struct.pack("<Q", t["uid"]) + obf.u32(0xFFFFFFFF)
    role.handlers[troops.C2S_TO_DECK](s, pkt(troops.C2S_TO_DECK, drag))
    out = bytes(s.sent[-1].buf)
    assert out[:3] == bytes([0, 0, 1]) and struct.unpack_from("<Q", out, 3)[0] == t["uid"] and out[16:] == obf.u32(0xFFFFFFFF)
    assert c["lineups"]["-1"]["slots"][1] == t["uid"]
    role.handlers[troops.C2S_LINEUPS](s, pkt(troops.C2S_LINEUPS, b""))
    out = bytes(s.sent[-1].buf)
    assert out[8] == 1 and out[9 + 9] == 1 and out[9 + 10] == 1 and struct.unpack_from("<Q", out, 9 + 11)[0] == t["uid"]
    role.handlers[troops.C2S_TUTORIAL_COUNT](s, pkt(troops.C2S_TUTORIAL_COUNT, struct.pack("<H", 1) + obf.u32(9900103) + bytes(1)))
    assert quest.record(c)["active"]["9900103"]["counts"][0] == 1
    world.send_exp(s)
    exp = bytes(s.sent[-1].buf)[5:]
    assert struct.unpack_from("<BQQ", exp, 17) == (6, 0, 181)                                  # deck slot 1
    c["barrack_cap"] = 1
    c["cooldowns"]["6"][1] -= 1  # The contract's cooldown elapsed; now exercise the barracks-cap refusal.
    c["bag"] = [{"code": 355000000, "slot": 2, "count": 1, "serial": 72, "bound": True}]
    role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, bytes(6) + obf.u32(355000000) + bytes(2) + obf.u64(72) + bytes(7)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", troops.TROOP_CAP_REACHED) and len(c["troops"]) == 1


def test_quick_bar_follows_bag_moves_and_the_arrange(world_role):
    from kuf2 import world
    role, st = world_role
    s = Session()
    a = {"code": 350000010, "slot": 5, "count": 2, "serial": 11, "bound": False}
    b = {"code": 100000001, "slot": 1, "count": 1, "serial": 12, "bound": False}
    s.data["char"].update(bag=[a, b])
    role.handlers[world.C2S_BAG_MOVE](s, pkt(world.C2S_BAG_MOVE, obf.u16(5) + obf.u16(9) + obf.u64(11) + obf.u64(0)))
    assert bytes(s.sent[-3].buf) == bytes([1]) + struct.pack("<HH", 5, 9)
    assert [w.proto for w in s.sent[-2:]] == [world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    role.handlers[world.C2S_BAG_ARRANGE](s, pkt(world.C2S_BAG_ARRANGE, bytes([0])))   # 100000001 -> 0, potion -> 1
    assert (b["slot"], a["slot"]) == (0, 1)
    out = bytes(s.sent[-1].buf)
    assert s.sent[-1].proto == world.S2C_QUICK_BAR_SLOTS and out[0] == 2
    assert world.swap_pairs({1: 0, 9: 1}) == [(9, 1), (9, 0)]
    assert world.swap_pairs({0: 1, 1: 2, 2: 0}) == [(0, 1), (0, 2)]


def test_skill_reset_costs_gold_and_level_up_refreshes_the_hero(world_role):
    from kuf2 import skills, world
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=15, gold=100, skills={"119": 2})
    role.handlers[skills.C2S_RESET](s, pkt(skills.C2S_RESET, b""))
    assert c["skills"] == {} and c["skill_resets"] == 1 and c["gold"] == 90                 # Skill_Init index 0: 10
    assert any(w.proto == skills.S2C_RESET and bytes(w.buf) == bytes(2) for w in s.sent)
    assert bytes(skills.reset_count_packet(c).buf) == struct.pack("<I", 1) and skills.reset_price(1) == 50
    c.update(level=1, exp=0)
    world.add_exp(s, st, 10 ** 6)
    assert c["level"] > 1 and [w.proto for w in core(s.sent)[-5:]] == [world.S2C_EXP, skills.S2C_LEARN,   # the rows
                                                                      world.S2C_QUICK_SLOT_PAGE,   # its bar skills
                                                                      world.S2C_HERO_BLOCK, skills.S2C_TP]  # it brings
    assert len(bytes(core(s.sent)[-2].buf)) == world.HERO_BLOCK == 0xb5


def test_daily_tasks_roll_by_level_count_triggers_and_pay_out(world_role):
    from kuf2 import daily, quest, world
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=24, gold=0, bag=[])
    lst, rewarded = daily.list_packets(c)
    assert len(c["daily"]["tasks"]) == 4 and bytes(rewarded.buf) == bytes(1)             # TaskControl: 24 -> 4 a day
    assert len(bytes(lst.buf)) == 2 + 7 * 4
    enchant = next(r for r in __import__("kuf2.tables", fromlist=["x"]).sections("dailytask")["DailyTask"]
                   if r["Complete_Type"] == "AnyEnchant" and daily.num(r["TaskLevelMin"]) <= 24 <= daily.num(r["TaskLevelMax"]))
    c["daily"]["tasks"] = [{"id": int(enchant["DailyTask_ID"]), "progress": 0, "state": daily.OPEN}]
    for _ in range(int(enchant["Complete_Value"])):
        quest.count(s, st, "AnyEnchant", "ID1", {"", "-"})
    t = c["daily"]["tasks"][0]
    assert t["state"] == daily.DONE and s.sent[-1].proto == daily.S2C_PROGRESS
    role.handlers[daily.C2S_REWARD](s, pkt(daily.C2S_REWARD, struct.pack("<I", t["id"])))
    assert any(w.proto == daily.S2C_REWARD and bytes(w.buf) == bytes(2) + struct.pack("<I", t["id"]) for w in s.sent)
    assert t["state"] == daily.TAKEN and c["daily"]["rewarded"] == 1 and c["gold"] == int(enchant["Gold"])
    role.handlers[daily.C2S_REWARD](s, pkt(daily.C2S_REWARD, struct.pack("<I", t["id"])))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", 0x411)


def test_titles_vehicles_and_achievements(world_role):
    from kuf2 import titles, world
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=12, exp=0, bag=[{"code": 351300010, "slot": 0, "count": 1, "serial": 81, "bound": True}])
    use = bytes(6) + obf.u32(351300010) + bytes(2) + obf.u64(81) + bytes(7)
    role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, use))           # a mount (GainVehicleID 3)
    assert c["vehicles"] == {"3": -1} and c["bag"] == []
    out = bytes(next(w for w in s.sent if w.proto == titles.S2C_VEHICLES).buf)
    assert out == struct.pack("<HHHq", 0, 1, 3, -1)
    role.handlers[titles.C2S_RIDE_VEHICLE](s, pkt(titles.C2S_RIDE_VEHICLE, struct.pack("<Hq", 3, -1)))
    assert bytes(s.sent[-1].buf) == struct.pack("<HH", 0, 3) and c["vehicle"] == 3
    titles.achieve(s, st, "HeroLv", value=10)                                   # Complete_ID 10 >= 10: title 60086
    assert 60086 in c["titles"] and any(w.proto == titles.S2C_TITLE_EARNED for w in s.sent)
    role.handlers[titles.C2S_WEAR_TITLE](s, pkt(titles.C2S_WEAR_TITLE, struct.pack("<I", 60086)))
    assert bytes(s.sent[-2].buf) == struct.pack("<HI", 0, 60086) and s.sent[-1].proto == world.S2C_HERO_BLOCK
    out = bytes(titles.titles_packet(c).buf)
    assert struct.unpack_from("<I", out)[0] == len(c["titles"]) and struct.pack("<I", 60086) in out


def test_troop_training_from_strategy_books_and_promotion_by_the_techtree(world_role):
    from kuf2 import troops, world
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=10, gold=100000, bag=[{"code": 351100030, "slot": 0, "count": 1, "serial": 91, "bound": True},
                                         {"code": 354000000, "slot": 1, "count": 10, "serial": 92, "bound": True},
                                         {"code": 354100000, "slot": 2, "count": 10, "serial": 93, "bound": True}])
    t, _ = troops.grant(c, 1)                                                     # troop 100, level 6
    use = bytes(6) + obf.u32(351100030) + bytes(2) + obf.u64(91) + bytes(7)
    role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, use))
    assert c["barrack_exp"] == min(10000, troops.pool_cap(10)) > 0
    assert any(w.proto == troops.S2C_POOL for w in s.sent)
    cost = troops.troop_need(100, 6)                                              # exactly one level
    role.handlers[troops.C2S_TRAIN](s, pkt(troops.C2S_TRAIN, struct.pack("<QQQ", 0, cost, t["uid"])))
    out = bytes(next(w for w in reversed(s.sent) if w.proto == troops.S2C_TRAIN).buf)
    assert out[:2] == bytes(2) and len(out) == 2 + 0x29 and t["level"] == 7 and t["exp"] == 0
    assert struct.unpack_from("<Q", out, 2)[0] == c["barrack_exp"]
    role.handlers[troops.C2S_PROMOTE](s, pkt(troops.C2S_PROMOTE, struct.pack("<QQIQ", t["uid"], 0, 1000000, 0)))
    out = bytes(next(w for w in reversed(s.sent) if w.proto == troops.S2C_PROMOTE).buf)
    assert out[:2] == bytes(2) and t["id"] == 1100111 and struct.unpack_from("<QI", out, 4) == (t["uid"], 1100111)
    assert not any(i["code"] in (354000000, 354100000) for i in c["bag"])
    role.handlers[troops.C2S_PROMOTE](s, pkt(troops.C2S_PROMOTE, struct.pack("<QQIQ", t["uid"], 0, 1000000, 0)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", troops.PROMOTE_REFUSED)


def test_troop_offer_cheer_up_set_effect_and_battle_detail(world_role):
    from kuf2 import troops
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=10, gold=1000)
    ts = [troops.grant(c, 1)[0] for _ in range(4)]
    ts[0]["ap"] = 50
    role.handlers[0x1358](s, pkt(0x1358, struct.pack("<Q", ts[0]["uid"])))
    out = bytes(s.sent[-1].buf)
    cost = int(1.19 * 0.7 * 1 * 50)          # level 6: LevelTreatment row index 1 1.19, RARITY1 0.7, GRADE1 1, 50 AP missing
    assert out == struct.pack("<HBHQ", 0, 1, 100, ts[0]["uid"]) and c["gold"] == 1000 - cost
    role.handlers[troops.C2S_BATTLE_DETAIL](s, pkt(troops.C2S_BATTLE_DETAIL, struct.pack("<Q", ts[1]["uid"])))
    assert len(bytes(s.sent[-1].buf)) == 2 + 8 + troops.DETAIL_BLOCK + 1
    role.handlers[troops.C2S_SET_EFFECT](s, pkt(troops.C2S_SET_EFFECT, struct.pack("<I", 0) + obf.u32(0xFFFFFFFF) + b"\0"))
    assert bytes(s.sent[-1].buf) == bytes(2)
    role.handlers[troops.C2S_OFFER](s, pkt(troops.C2S_OFFER, struct.pack("<Q", ts[3]["uid"])))
    assert any(w.proto == troops.S2C_OFFER and bytes(w.buf) == bytes(2) for w in s.sent)
    assert len(c["troops"]) == 3 and c["barrack_exp"] > 0                  # 6 levels of exp x 300 / 1000
    role.handlers[troops.C2S_OFFER](s, pkt(troops.C2S_OFFER, struct.pack("<Q", ts[2]["uid"])))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", troops.OFFER_REFUSED)       # fewer than 4 left


def test_troop_skills_and_template(world_role):
    from kuf2 import troops
    role, st = world_role
    s = Session()
    c = s.data["char"]
    t, _ = troops.grant(c, 1)
    t["id"] = 1100111                                                        # a promoted troop with skill groups
    ability = int(next(g for g in __import__("kuf2.tables", fromlist=["x"]).sections("trooptable")["SkillGroup"]
                       if g["SkillGroupID"] == "11001111")["SkillId_1"])
    role.handlers[troops.C2S_LEARN_SKILL](s, pkt(troops.C2S_LEARN_SKILL, struct.pack("<IQ", ability, t["uid"])))
    assert bytes(s.sent[-1].buf) == bytes(2) and t["skills"] == [                # into slot 0; troop 100's default
        {"slot": troops.UNEQUIPPED, "id": 81001}, {"slot": 0, "id": ability}]   # stays with it (70142: academy level 1)
    role.handlers[troops.C2S_EQUIP_SKILL](s, pkt(troops.C2S_EQUIP_SKILL, struct.pack("<QI", t["uid"], ability)))
    assert bytes(s.sent[-1].buf) == struct.pack("<HBIQB", 0, 0, ability, t["uid"], 1)
    role.handlers[troops.C2S_TEMPLATE](s, pkt(troops.C2S_TEMPLATE, struct.pack("<IB", 100, 6)))
    out = bytes(s.sent[-1].buf)
    assert len(out) == 0x96 and out[0x88:0x8c] == obf.u32(100) and out[0x8c] == 6 and out[0x95] == 1


def test_badges_on_and_off_and_tactics_level_up(world_role):
    from kuf2 import items, tables, troops
    role, st = world_role
    s = Session()
    c = s.data["char"]
    badge = int(next(r["ItemCode"] for r in tables.sections("item_troop")["Base"] if r["ItemKind"] == "TROOP_ITEM"))
    c.update(gold=5000, bag=[{"code": badge, "slot": 4, "count": 1, "serial": 95, "bound": False}])
    t, _ = troops.grant(c, 1)
    role.handlers[troops.C2S_BADGE_ON](s, pkt(troops.C2S_BADGE_ON, obf.u16(4) + struct.pack("<QB", t["uid"], 0)))
    assert [w.proto for w in s.sent[-2:]] == [troops.S2C_BADGE_ON, 0x1656] and c["bag"] == [] and t["badges"][0]["code"] == badge
    role.handlers[troops.C2S_DETAIL](s, pkt(troops.C2S_DETAIL, struct.pack("<Q", t["uid"])))
    out = bytes(s.sent[-1].buf)
    assert out[11 + 6 * out[10] + troops.DETAIL_BLOCK] == 1                    # one badge record in the detail
    role.handlers[troops.C2S_BADGE_OFF](s, pkt(troops.C2S_BADGE_OFF, struct.pack("<QHB", t["uid"], 0, 0)))
    assert bytes(s.sent[-2].buf) == bytes(2) and c["bag"][0]["serial"] == 95 and t["badges"] == []
    assert c["gold"] == 5000 - troops.badge_price(badge)
    ability = int(tables.sections("tacticsacademy")["Basic"][0]["AbilityID"])
    role.handlers[troops.C2S_TACTICS_UP](s, pkt(troops.C2S_TACTICS_UP, obf.u32(ability)))    # 81001: held at 1 from
    assert bytes(s.sent[-2].buf) == bytes(2) + obf.u32(ability) + bytes([2]) and c["tactics"][str(ability)]["level"] == 2
    assert bytes(s.sent[-1].buf) == obf.u32(ability) + struct.pack("<IB", 0, 2)    # the start: to 2; then 0x10bd



def test_death_wears_armour_down_and_the_shop_repairs_it(world_role):
    from kuf2 import hero, items
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c["gold"] = 5
    eq = hero.equipment(c)                                  # starter kit: weapons without durability, armour 100
    armour = [e for e in eq if items.full_durability(e["code"]) > 0]
    world.wear_down(s, st, "DIE")
    assert [e.get("dur") for e in armour] == [96] * len(armour) and all("dur" not in e for e in eq if e not in armour)
    assert [w.proto for w in s.sent] == [world.S2C_EQUIP_ONE] * len(armour)
    out = bytes(s.sent[0].buf)
    assert obf.dec_u16(out[0:2]) == armour[0]["index"] and struct.unpack_from("<H", out, 2 + 0x0f)[0] == 96
    cost = items.repair_cost(armour[0])
    assert cost == int(1 * 0.175 * 3 * 4)                   # ARMOR 1, NORMAL 0.175, Gold 3 (ReqLevel 1), 4 missing
    req = lambda es: struct.pack("<H", len(es)) + b"".join(bytes([1]) + obf.u64(e["serial"]) + obf.u16(e["index"]) for e in es)
    s.sent.clear()
    role.handlers[world.C2S_REPAIR](s, pkt(world.C2S_REPAIR, req(armour)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.NOT_ENOUGH_GOLD) and armour[0]["dur"] == 96
    c["gold"] = 100
    s.sent.clear()
    role.handlers[world.C2S_REPAIR](s, pkt(world.C2S_REPAIR, req(armour + armour[:1])))       # a duplicate is paid once
    sent = core(s.sent)
    assert c["gold"] == 100 - cost * len(armour) and all("dur" not in e for e in armour)
    assert [w.proto for w in sent if w.proto in (world.S2C_REPAIR, world.S2C_EQUIP_ONE)] == \
        [world.S2C_REPAIR] + [world.S2C_EQUIP_ONE] * len(armour)



def test_a_magic_stone_goes_into_a_socket_and_back_out(world_role):
    from kuf2 import hero, items, tables
    role, st = world_role
    s = Session()
    c = s.data["char"]
    stone = 560010001                                         # RARE, ReqLevel 10, LEADER ATTACK_PHYSICAL +14
    weapon = int(next(r["ItemCode"] for r in tables.load("item_weapon") if r.get("ComposeSlotMax") == "1"
                      and r.get("Parts") == "MAIN_WEAPON"))
    eq = hero.equipment(c)
    main = next(e for e in eq if e["index"] == 0)
    main["code"] = weapon
    c.update(level=5, gold=5000, bag=[{"code": stone, "slot": 2, "count": 3, "serial": 77, "bound": False}])
    assert items.sockets(main) == [-1]
    rec = items.record(weapon, 0, main["serial"], sockets=items.sockets(main))
    assert rec[39:44] == bytes([1]) + b"\xff" * 4 and rec[44:] == b"\0"
    body = lambda: obf.u64(77) + bytes([1]) + obf.u64(main["serial"]) + bytes([0]) + obf.u16(2) + obf.u16(0)
    role.handlers[world.C2S_COMPOSE](s, pkt(world.C2S_COMPOSE, body()))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.COMPOSE_LEVEL) and c["bag"][0]["count"] == 3
    c["level"] = 10
    before = hero.stats(c["class"], 10, hero.worn_codes(c))["ATTACK_PHYSICAL"]
    s.sent.clear()
    role.handlers[world.C2S_COMPOSE](s, pkt(world.C2S_COMPOSE, body()))
    assert [w.proto for w in s.sent][:3] == [world.S2C_COMPOSE, world.S2C_CARGO, world.S2C_HERO_DETAIL]
    assert bytes(s.sent[0].buf) == bytes(2) and main["sockets"] == [stone] and c["bag"][0]["count"] == 2
    assert hero.stats(c["class"], 10, hero.worn_codes(c))["ATTACK_PHYSICAL"] == before + 14
    role.handlers[world.C2S_COMPOSE](s, pkt(world.C2S_COMPOSE, obf.u64(77) + bytes([1]) + obf.u64(main["serial"])
                                            + bytes([1]) + obf.u16(2) + obf.u16(0)))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.COMPOSE_REFUSED)        # no second socket
    cost = items.compose_cost(stone)
    assert cost == 1 * 1000                                                          # RARE: UseGoldCount2 1000
    s.sent.clear()
    role.handlers[world.C2S_DISARM](s, pkt(world.C2S_DISARM, bytes([0]) + obf.u16(0) + bytes([0])
                                          + obf.u64(main["serial"]) + bytes([1])))
    assert bytes(s.sent[0].buf) == bytes(2) and main["sockets"] == [-1] and c["gold"] == 5000 - cost
    assert sum(i["count"] for i in c["bag"] if i["code"] == stone) == 3
    role.handlers[world.C2S_DISARM](s, pkt(world.C2S_DISARM, bytes([0]) + obf.u16(0) + bytes([0])
                                          + obf.u64(main["serial"]) + bytes([1])))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.COMPOSE_REFUSED)        # the socket is empty now



def test_gear_stats_count_the_second_trait_block():
    # owner 2026-09-30 (rules census HERO G2): the TraitType / Value block counts beside BASE_TRAIT
    from kuf2 import items
    assert items.traits(153000100) == [("M_DEFENCE_PHYSICAL", 1080.0, False), ("M_DEFENCE_MAGICAL", 393.0, False),
                                       ("HP_MAX", 2152.0, False), ("GIANT_DEFENCE_RATE", 63.0, False)]



def test_hero_edit_takes_the_ticket_and_keeps_the_new_look(world_role):
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c["look"] = bytes(range(0x38)).hex()
    blk = bytes(0xff - k for k in range(0x34))
    role.handlers[world.C2S_HERO_EDIT](s, pkt(world.C2S_HERO_EDIT, blk))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", 1) and c["look"] == bytes(range(0x38)).hex()   # no ticket
    c["bag"] = [{"code": 358300050, "slot": 0, "count": 1, "serial": 12, "bound": True}]
    s.sent.clear()
    role.handlers[world.C2S_HERO_EDIT](s, pkt(world.C2S_HERO_EDIT, blk))
    assert bytes(s.sent[0].buf) == bytes(2) + blk and s.sent[1].proto == world.S2C_CARGO and c["bag"] == []
    look = bytes.fromhex(c["look"])
    assert look[0x00:0x15] == blk[0x1e:0x33] and look[0x15:0x1f] == blk[0x14:0x1e] and look[0x1f:0x33] == blk[0:0x14]
    assert look[0x33] == blk[0x33] and look[0x34:] == bytes(range(0x34, 0x38))                      # class kept


def use_body(code, serial, count=1):
    return bytes(6) + obf.u32(code) + bytes(2) + obf.u64(serial) + obf.u16(count) + bytes(5)


def test_item_uses_mapped_from_the_client(world_role):
    from kuf2 import troops, skills, hero, items
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=30, gold=0, spot=10001, bag=[
        {"code": 357000110, "slot": 0, "count": 2, "serial": 1, "bound": False},    # tactics book 150000, 100 exp
        {"code": 357900000, "slot": 1, "count": 1, "serial": 2, "bound": False},    # hero skill book: ability 45
        {"code": 351500400, "slot": 2, "count": 1, "serial": 3, "bound": False},    # repair coupon
        {"code": 351500200, "slot": 3, "count": 1, "serial": 4, "bound": False},    # troop cheer
        {"code": 351100010, "slot": 4, "count": 3, "serial": 5, "bound": False},    # barracks exp book
        {"code": 351000020, "slot": 5, "count": 1, "serial": 6, "bound": False}])   # teleport scroll to 20100
    use = lambda code, serial, n=1: role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, use_body(code, serial, n)))
    ok = lambda code: [w for w in s.sent if w.proto == world.S2C_USE_ITEM][-1].buf[:2] == bytes(2)
    use(357000110, 1, 2)                                   # both books: 200 exp -> level 0 +75 +250? 75 to level 1
    t = c["tactics"]["150000"]
    assert ok(357000110) and (t["level"], t["exp"]) == (1, 125) and not any(i["serial"] == 1 for i in c["bag"])
    assert s.sent[-2].proto == troops.S2C_TACTICS_ONE or any(w.proto == troops.S2C_TACTICS_ONE for w in s.sent)
    use(357900000, 2)
    assert ok(357900000) and c["skills"]["45"] == 1 and 45 in skills.battle_abilities(c)
    main = next(e for e in hero.equipment(c) if items.full_durability(e["code"]) > 0)
    main["dur"] = 10
    use(351500400, 3)
    assert ok(351500400) and "dur" not in main and any(w.proto == world.S2C_EQUIP_ONE for w in s.sent)
    tr, _ = troops.grant(c, 1)
    tr["ap"] = 5
    use(351500200, 4)
    assert ok(351500200) and tr["ap"] == troops.cheer_cost(tr)[1]
    assert [w.proto for w in s.sent[-3:]] == [troops.S2C_AP, world.S2C_CARGO_CHANGE, world.S2C_CARGO]
    c["cooldowns"]["4000"][1] -= 1  # The tactics book and strategy book share this cooldown group.
    use(351100010, 5, 2)
    assert ok(351100010) and next(i for i in c["bag"] if i["serial"] == 5)["count"] == 1
    use(351000020, 6)                                      # in town: the server travels (0x3745 prepare enter town)
    assert ok(351000020) and c["spot"] == 20100 and any(w.proto == world.S2C_PREPARE_ENTER_TOWN for w in s.sent)


def test_a_token_shop_charges_its_token_item(world_role):
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(gold=0, bag=[{"code": 760000030, "slot": 7, "count": 1500, "serial": 9, "bound": False}])
    body = obf.u16(0xffff) + bytes(4) + struct.pack("<I", 216) + obf.u16(1) + bytes([0])
    role.handlers[world.C2S_STORE_BUY](s, pkt(world.C2S_STORE_BUY, body))
    assert bytes(core(s.sent)[-2].buf)[:2] == bytes(2) or any(bytes(w.buf)[:2] == bytes(2) for w in s.sent if w.proto == world.S2C_STORE_BUY)
    assert next(i for i in c["bag"] if i["code"] == 760000030)["count"] == 500 and c["gold"] == 0
    assert any(i["code"] == 613700310 for i in c["bag"])



def warp_body(warp):
    return bytes(4) + struct.pack("<h", 0) + bytes(4) + obf.u32(warp) + bytes(1)


def test_in_room_doors_and_crystals_move_the_hero(world_role):
    from kuf2 import game
    role, st = world_role
    rows = tables.load("warpinfo")
    field = next(r for r in rows if r["WARP_POSITION"] == "FIELD" and r["SpotID"] == "10352" and "Quest" not in r["Require1_Type"])
    town = next(r for r in rows if r["WARP_POSITION"] == "TOWN" and r["SpotID"] == "10001")
    world_door = next(r for r in rows if r["WARP_POSITION"] == "WORLD")
    s = Session()
    s.data.update(battle_spot=10350, game_addr=("127.0.0.1", 25004))
    c = s.data["char"]
    c.update(spot=10350, pos=[0, 0, 0], gold=100000)
    s.data["account"] = {"id": 1, "characters": [c]}
    role.handlers[world.C2S_WARP_REQUEST](s, pkt(world.C2S_WARP_REQUEST, warp_body(int(field["ID"]))))
    esc = next(w for w in s.sent if w.proto == world.S2C_MISSION_ESCAPE)
    assert bytes(esc.buf)[2 + 0x16] == world.WARP_KIND_FIELD and c["spot"] == 10352
    s.sent.clear()
    role.handlers[world.C2S_WARP_REQUEST](s, pkt(world.C2S_WARP_REQUEST, warp_body(int(town["ID"]))))
    blk = bytes(s.sent[-1].buf)[2:]
    assert s.sent[-1].proto == world.S2C_MISSION_ESCAPE and blk[6] == world.ESCAPE_TO_TOWN and blk[0x16] == 0
    assert obf.dec_u32(blk[0x17:0x1b]) == 10001 and c["spot"] == 10001 and not s.data.get("on_worldmap")
    s.data["battle_spot"] = 10202
    role.handlers[world.C2S_WARP_REQUEST](s, pkt(world.C2S_WARP_REQUEST, warp_body(int(world_door["ID"]))))
    assert bytes(s.sent[-1].buf)[2 + 6] == world.ESCAPE_TO_WORLDMAP and s.data["on_worldmap"]



def test_repeatable_quests_reopen_after_their_reset():
    import datetime
    rows = tables.load("questtable")
    day = next(int(r["ID"]) for r in rows if r.get("Retry_Type") == "Day" and r.get("Use_Quest") == "Yes")
    week = next(int(r["ID"]) for r in rows if r.get("Retry_Type") == "Week" and r.get("Use_Quest") == "Yes")
    once = 1003
    today = datetime.date(2026, 9, 27)                         # a Sunday
    r = {"active": {}, "done": [day, week, once], "handed": {str(day): "2026-09-27", str(week): "2026-09-26",
                                                               str(once): "2026-09-01"}}
    assert quest.reopen(r, today) == [] and r["done"] == [day, week, once]
    assert quest.reopen(r, datetime.date(2026, 9, 28)) == [day, week] and r["done"] == [once]   # a new day and ISO week


def test_realm_rides_the_start_game_reply_and_the_daily_list_tops_up(world_role):
    from kuf2 import daily
    role, st = world_role
    c = {"id": 1, "class": 0, "level": 10, "daily": {"date": datetime_today(), "tasks": [], "rewarded": 0}}
    assert not daily.top_up(c)                                 # below 17: none
    c["level"] = 20
    assert daily.top_up(c) and len(c["daily"]["tasks"]) == daily.num(daily.control(20).get("DailyTaskList"))


def datetime_today():
    import datetime
    return __import__("kuf2.rules", fromlist=["game_day"]).game_day()



def test_a_skill_goes_on_the_quick_bar(world_role):
    from kuf2 import skills
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=30, skills={"8": 2})
    out = bytes(skills.info_packet(c).buf)
    n = out[22]
    handles = [out[23 + 6 * i] for i in range(n)]
    assert len(set(handles)) == n and 0xff not in handles                   # a distinct handle per skill
    a = skills.handle(c, 9)
    req = bytes([obf.T2[0]]) + bytes([0, 3, 1]) + struct.pack("<I", 9) + struct.pack("<H", a) + bytes([0])
    role.handlers[world.C2S_QUICK_SLOT_SET](s, pkt(world.C2S_QUICK_SLOT_SET, req))
    assert s.sent[-1].proto == world.S2C_QUICK_SLOT_SET
    assert bytes(s.sent[-1].buf) == bytes(2) + bytes([0]) + struct.pack("<H", a) + bytes([3, obf.T2[0], 1, 0])
    page = bytes(world.quick_slot_page_packet(c, 0).buf)
    assert struct.pack("<IB", 9, 1) in page and bytes([1, 3]) + struct.pack("<h", a) in page
    bad = req[:4] + struct.pack("<I", 123456) + req[8:]
    role.handlers[world.C2S_QUICK_SLOT_SET](s, pkt(world.C2S_QUICK_SLOT_SET, bad))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", 1)                 # not a held skill


def test_items_live_in_their_bag_tabs_and_costumes_equip(world_role):
    from kuf2 import hero
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(level=30, bag=[{"code": 450000003, "slot": 2, "count": 1, "serial": 70, "bound": False}])   # an old save
    assert world.normalize_bag(c) == 1 and c["bag"][0]["slot"] == 0x80                            # quest tab
    world.add_item(s, st, 359000050, 1)                                                            # a troop stone
    world.add_item(s, st, 955006200, 1)                                                            # a costume set
    world.add_item(s, st, 950009600, 1)                                                            # a costume hat
    slots = {i["code"]: i["slot"] for i in c["bag"]}
    assert slots[359000050] == 0xc0 and slots[955006200] == 0x100 and slots[950009600] == 0x101
    stone = next(i for i in c["bag"] if i["code"] == 359000050)
    move = obf.u16(0xc0) + obf.u16(5) + obf.u64(stone["serial"]) + obf.u64(0)
    role.handlers[world.C2S_BAG_MOVE](s, pkt(world.C2S_BAG_MOVE, move))
    assert bytes(s.sent[-1].buf) == struct.pack("<H", world.BAG_MOVE_REFUSED) and stone["slot"] == 0xc0   # not its tab
    for code, index in ((955006200, 13), (950009600, 11)):
        it = next(i for i in c["bag"] if i["code"] == code)
        body = obf.u64(it["serial"]) + obf.u64(0) + obf.u16(index) + obf.u16(it["slot"])
        role.handlers[world.C2S_EQUIP](s, pkt(world.C2S_EQUIP, body))
        assert bytes(s.sent[[w.proto for w in s.sent].index(world.S2C_EQUIP, len(s.sent) - 4)].buf)[:2] == bytes(2)
    assert {e["index"]: e["code"] for e in hero.equipment(c)}.get(13) == 955006200
    assert {e["index"]: e["code"] for e in hero.equipment(c)}.get(11) == 950009600
    role.handlers[world.C2S_BAG_ARRANGE](s, pkt(world.C2S_BAG_ARRANGE, bytes([3])))
    assert next(i for i in c["bag"] if i["code"] == 450000003)["slot"] == 0x80



def test_riding_in_a_room_mounts_the_hero_there(world_role):
    from kuf2 import combat, game, world
    role, st = world_role
    room = Session()
    room.data["battle"] = combat.Battle()
    room.w = type("W", (), {"is_closing": lambda self: False})()
    st.game_sessions = {7: room}
    s = Session()
    s.data["account"] = {"id": 7}
    s.data["char"].update(**{"id": 2, "class": 3})               # the room finds the Player by its key (+0x54),
    role.handlers[world.C2S_RIDE](s, pkt(world.C2S_RIDE, struct.pack("<H", 3)))       # the one 0x3f4f gave it
    key = game.player_key(s.data["char"])
    assert s.sent[-1].proto == world.S2C_RIDE                      # the town answer as before
    assert room.sent[-1].proto == world.S2C_ROOM_RIDE and bytes(room.sent[-1].buf) == struct.pack("<HI", 3, key)
    role.handlers[world.C2S_RIDE](s, pkt(world.C2S_RIDE, struct.pack("<H", 0)))       # dismount
    assert bytes(room.sent[-1].buf) == struct.pack("<HI", 0, key)
    st.game_sessions = {}
    n = len(room.sent)
    role.handlers[world.C2S_RIDE](s, pkt(world.C2S_RIDE, struct.pack("<H", 3)))       # in town: nothing to the room
    assert len(room.sent) == n



def test_cubic_bundles_fill_the_balance_and_start_game_shows_it(world_role):
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(gold=0, bag=[{"code": 358200010, "slot": 0, "count": 3, "serial": 1, "bound": False}])   # ChargeValue 10
    role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, use_body(358200010, 1, 2)))
    assert c["cubic"] == 20 and c["bag"][0]["count"] == 1
    push = next(w for w in s.sent if w.proto == world.S2C_CUBIC)
    assert bytes(push.buf) == obf.u32(20)
    assert bytes(world.cubic_packet({}).buf) == obf.u32(0)



def test_buff_potions_food_and_fireworks_are_spent(world_role):
    from types import SimpleNamespace
    from kuf2 import combat, game
    # their ability was cast by the client first; the 0x4042 only spends the item (ITEMS-WIRING I9 / I10)
    role, st = world_role
    s = Session()
    c = s.data["char"]
    room = Session()
    room.data["battle"] = combat.Battle()
    room.data["battle"].add_hero(0, 1000)
    room.w = SimpleNamespace(is_closing=lambda: False)
    s.data["account"] = {"id": 7}
    st.game_sessions = {7: room}
    c.update(level=10, gold=0, bag=[{"code": 350550010, "slot": 0, "count": 2, "serial": 1, "bound": False},   # buff potion
                          {"code": 350600010, "slot": 1, "count": 1, "serial": 2, "bound": False},   # food
                          {"code": 358910010, "slot": 2, "count": 1, "serial": 3, "bound": False}])  # firework
    use = lambda code, serial: role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, use_body(code, serial)))
    use(350550010, 1)
    reply = next(w for w in reversed(s.sent) if w.proto == world.S2C_USE_ITEM)
    assert bytes(reply.buf)[:2] == bytes(2) and c["bag"][0]["count"] == 1
    use(350600010, 2)
    assert not any(i["serial"] == 2 for i in c["bag"]) and s.sent[-1].proto == world.S2C_QUICK_BAR_SLOT
    use(358910010, 3)
    assert s.sent[-1].proto == world.S2C_FIREWORK and bytes(s.sent[-1].buf) == obf.u32(358910010) + struct.pack("<I", game.player_key(c))



def test_an_equip_item_quest_counts_kills_only_while_its_weapon_is_worn_and_takes_it_back(world_role):
    # 1140732 "[Ultimate Weapon] Finally a Success?": EquipItem 107005400, kills of NP name 8058 (WORLD-WIRING Q1)
    from kuf2 import hero
    role, st = world_role
    s = Session()
    c = s.data["char"]
    c.update(gold=0, bag=[], quests={"active": {"1140732": {"counts": [0] * 5}}, "done": []})
    hero.equipment(c)
    quest.count(s, st, "NPNameKill", "ID2", {"8058"})
    assert c["quests"]["active"]["1140732"]["counts"][0] == 0         # the starter weapon: not counted
    main = next(e for e in c["equip"] if e["index"] == 0)
    main["code"] = 107005400                                          # wearing the lent weapon
    quest.count(s, st, "NPNameKill", "ID2", {"8058"})
    assert c["quests"]["active"]["1140732"]["counts"][0] == 1
    assert world.take_back(s, st, 107005400, 1) == 0                  # not in the bag: the worn one goes
    assert not any(e["code"] == 107005400 for e in c["equip"])
    assert any(w.proto == world.S2C_DESTROY_WORN and bytes(w.buf) == b"\0\0" + obf.u16(0) for w in s.sent)



def test_a_crystal_in_a_room_reenters_the_field_and_charges_its_cost(world_role):
    # UI-WIRING U27: portal 4000 (warpinfo %Portal, 10350, 10 gold) is not a %Move id
    role, st = world_role
    s = Session()
    s.data.update(battle_spot=10350, game_addr=("127.0.0.1", 25004))
    c = s.data["char"]
    c.update(spot=10350, pos=[0, 0, 0], gold=100)
    s.data["account"] = {"id": 1, "characters": [c]}
    role.handlers[world.C2S_WARP_REQUEST](s, pkt(world.C2S_WARP_REQUEST, warp_body(4000)))
    esc = next(w for w in s.sent if w.proto == world.S2C_MISSION_ESCAPE)
    assert bytes(esc.buf)[2 + 0x16] == world.WARP_KIND_FIELD and c["spot"] == 10350 and c["gold"] == 90
    s.sent.clear()
    c["gold"] = 5
    role.handlers[world.C2S_WARP_REQUEST](s, pkt(world.C2S_WARP_REQUEST, warp_body(4000)))
    assert s.sent == [] and c["gold"] == 5                            # short of gold: nothing moves


def test_the_lobby_back_button_and_an_unknown_character_get_their_answers(world_role):
    # planning/client/session_lobby.md: "Back" from character select sends 0x5644 and waits for 0x5645; an unknown id
    # in 0x1011 must still be answered (0x1012 refusal 0x1407) or every select button stays dead
    role, _ = world_role
    s = Session()
    del s.data["char"]
    s.data["account"] = {"characters": [{"id": 1, "name": "A"}]}
    role.handlers[world.C2S_LEAVE_NOTICE](s, pkt(world.C2S_LEAVE_NOTICE, b""))
    assert [w.proto for w in s.sent] == [world.S2C_LEAVE_NOTICE]
    role.handlers[world.C2S_START_GAME](s, pkt(world.C2S_START_GAME, struct.pack("<IB", 99, 0)))
    assert s.sent[-1].proto == world.S2C_START_GAME_RES
    assert struct.unpack_from("<H", bytes(s.sent[-1].buf))[0] == world.START_REFUSED
    s.data["char"] = {"id": 1}                            # in game: the exit notice, nothing to answer
    n = len(s.sent)
    role.handlers[world.C2S_LEAVE_NOTICE](s, pkt(world.C2S_LEAVE_NOTICE, b""))
    assert len(s.sent) == n


def test_item_rows_come_from_the_real_tables_and_arrange_keeps_each_tab(world_role):
    # planning/client/items_troops_skills.md: item_cash (a shop catalog) shadowed 421 real rows (box 605002110 was
    # refused 0x447 live); the arrange tabs follow the client's switch 0x140dd0be0 (5 quest, 8 stones, 6 costumes)
    from kuf2 import items
    assert items.row(605002110)["ItemKind"] == "CONTAINER"
    role, _ = world_role
    s = Session()
    s.data["char"].update(bag=[{"code": 605002110, "slot": 0x85, "serial": 2, "count": 1},
                               {"code": 605002110, "slot": 0x90, "serial": 1, "count": 1}])
    role.handlers[world.C2S_BAG_ARRANGE](s, pkt(world.C2S_BAG_ARRANGE, bytes([5])))
    assert sorted(i["slot"] for i in s.data["char"]["bag"]) == [0x80, 0x81]

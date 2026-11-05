"""The last 6 bytes of every troop state (0x50cb / 0x50b8 tail, reader 0x140d0cf90) as the client's troop build reads
them, MakeTroopGenInfoForBuild 0x140cf7c50..0x140cf7ca2: +0 u16 and +4 u8 name a capture-point marker (u16 != 0xffff
or u8 != 0 -> 0x140c54dc0 -> UiInGameTroopIcon's capture map 0x140c69a80, drawn as `_root.C2A_addCapture` over the
troop, 0x140c6bda0 / 0x140c6b000), +2 is an obool "elite" (-> gen +0x7f -> troop +0x11b8, 0x140cf84c6), which the
minimap turns into the EliteTroop icon (0x140d31850: the UniqueEnemy horned-skull sprite, atlas image 91, instead of the
troop's red job square). Six zero bytes asked for both on every troop: 0x00 is OBOOL_TRUE (T1[0] = 0xc3). Owner
2026-09-30 13:30 in Glen's camp 10352: "remove the spawn makers from the ui ... in the minimap all enemies have the
boss marker"; the original's minimap there shows red squares (tiouWoPSPks 1154-1250 s, frames 578 / 587 / 622 / 626)."""
import struct

from kuf2 import game
from kuf2.obf import T1
from kuf2.packet import Writer
from test_battle import FieldSession, NoSave


def tail(buf):
    """(capture key u16, elite, capture value u8) of a state that ends the packet, read the client's way."""
    b = bytes(buf)[-6:]
    return struct.unpack_from("<H", b, 0)[0], bool(T1[b[2]] & 1), b[4]


def marked(buf):
    key, elite, value = tail(buf)
    return {"capture": key != 0xFFFF or value != 0, "elite": elite}


def camp():
    """Glen's camp 10352 as the owner entered it: the zone troops, the hero's 0x50b8."""
    s = FieldSession({"active": {}, "done": []})
    s.data["char"] = s.data["account"]["characters"][0]
    s.data["char"].update(level=1, name="T")
    s.state = NoSave()
    s.data["battle"].add_hero(0, 1000)
    game.spawn_zone_troops(s)
    game.send_mission_troop_info(s)
    return s


def test_no_camp_troop_is_elite_so_the_minimap_draws_its_job_square():
    s = camp()
    cells = [w for w in s.sent if w.proto == game.S2C_ENTER_CELL_TROOP]
    assert len(cells) == 132                                        # the zone's troops (INVENTORY, Field battle rooms)
    assert [marked(w.buf)["elite"] for w in cells] == [False] * 132


def test_no_troop_carries_a_capture_point_marker():
    s = camp()
    states = [w for w in s.sent if w.proto in (game.S2C_ENTER_CELL_TROOP, game.S2C_MISSION_TROOP_INFO)]
    assert any(w.proto == game.S2C_MISSION_TROOP_INFO for w in states)       # the hero's own state too
    assert [marked(w.buf)["capture"] for w in states] == [False] * len(states)


def test_the_state_tail_is_the_readers_layout():
    # 0x140d0cf90: obool (FALSE: no 0x140d1ffe0 block), then 6 bytes; "none" is 0xffff, FALSE, 0
    w = Writer(game.S2C_ENTER_CELL_TROOP)
    game.write_troop_state(w, (0, 0, 0), flags=game.TROOP_ALIVE, uid=10036, troop_id=154030, np=True, units=1)
    b = bytes(w.buf)
    assert not T1[b[-7]] & 1
    assert tail(b) == (0xFFFF, False, 0)

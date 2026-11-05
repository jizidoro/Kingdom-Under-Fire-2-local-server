"""Grey Fog Streets 10358: the director's table (kuf2/scenes/m10358.py) in a mission room."""
import struct

from kuf2 import director, game
from kuf2.scenes import m10358
from test_battle import NoSave, acts, down_all, mission_room, pkt, walk
from test_director import cutscenes, lines_shown, run_pending, sync_body

THOMPSON, MILITIAMAN, VILLAGER_B = 10000, 11000, 15014
HOSTILE = (20000, 20001, 21000, 21001, 21002, 21004, 22000, 22001, 22002, 22004, 22003)     # the boss last


def marks(s):
    """(area, on) of every ActGuiSetHighlightArea sent, in order."""
    return [(a[1], a[3]) for a in acts(s, director.ACT_HIGHLIGHT_AREA)]


def centre(bound):
    b = director.bound(10358, bound)
    return b["BoundCenterX"], b["BoundCenterZ"]


def test_grey_fog_opens_with_thompson_on_the_road():
    # the original opens with 9_GreySmoke_Dynamic1 (28 s), which voices Thompson's 7100-7140
    s = mission_room(10358)
    assert cutscenes(s) == [9] and lines_shown(s) == []


def test_thompson_speaks_as_the_opening_scene_ends_and_the_north_gap_is_marked():
    # harness report row #1 and frames 22:12-22:18: 7200 at 22:16.5, the scene's end, the hero still 3,835 outside
    # bound 10002 (he enters it at 22:33.5); a green (MINE) pillar and glowing area ahead from 22:16 (effects.pillars
    # 22:17-22:32), the hero passes through it at 22:33 and it goes down; the next shows at the gate from 22:34 until
    # he enters 10001 at 22:40.5 (frames 22:32-22:44), when the militiaman speaks
    s = mission_room(10358)
    assert min(d for d, _ in s.pending) > 27.9                  # 7200 waits for the scene's 28 s
    run_pending(s)
    assert lines_shown(s) == [(THOMPSON, 1, 7200)] and marks(s) == [(10002, 1)]
    walk(s, *centre(10002))
    run_pending(s)
    assert lines_shown(s) == [(THOMPSON, 1, 7200)]              # nothing said at the wall (frames 22:32-22:40)
    assert marks(s)[1:] == [(10002, 0), (10001, 1)]
    walk(s, *centre(10001))
    run_pending(s)
    assert lines_shown(s)[-1] == (MILITIAMAN, 0, 7210) and (10001, 0) in marks(s)[3:]


def test_the_militiaman_sends_the_hero_on_to_the_plaza_and_the_villagers_call_out():
    s = mission_room(10358)
    run_pending(s)
    walk(s, 288544, 190032)                      # bound 10001, inside the north gap
    down_all(s, [20000])
    run_pending(s)
    assert [line for _, _, line in lines_shown(s)] == [7200, 7210]
    down_all(s, [20001])                         # the last of force 20000
    run_pending(s)
    assert lines_shown(s)[-2:] == [(MILITIAMAN, 0, 7220), (THOMPSON, 1, 7230)]
    walk(s, 282953, 190227)                      # bound 10008: a villager of force 15000 (in since the start)
    run_pending(s)
    walk(s, 282953, 190227)
    run_pending(s)
    assert lines_shown(s)[-1] == (VILLAGER_B, 0, 7240)
    assert [line for _, _, line in lines_shown(s)].count(7240) == 1


def test_grey_fog_plays_the_boss_and_the_finale_before_the_room_ends():
    # the boss's fall does not end the room (WIN = "table"); the south-east street does, as the original: "sandwiched
    # ... surrounded", the sandwich force 26000, Glen's rescue (the scene GLG), then the win
    s = mission_room(10358)
    run_pending(s)
    s.state = NoSave()
    gate = director.bound(10358, 10001)                 # the route passes the gate and the boss plaza (live
    walk(s, gate["BoundCenterX"], gate["BoundCenterZ"])  # 2026-09-30); their lines come before the fights' ends
    run_pending(s)
    down_all(s, HOSTILE)
    run_pending(s)
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) and not s.data.get("mission_won")
    assert 26000 not in {t.get("ForceNum") for t in s.data["zone_troops"].values()}
    passage = director.bound(10358, 10003)              # past the Oak Barrels onto the central plaza
    walk(s, passage["BoundCenterX"], passage["BoundCenterZ"])
    run_pending(s)
    plaza = director.bound(10358, 13001)
    walk(s, plaza["BoundCenterX"], plaza["BoundCenterZ"])
    run_pending(s)
    street = director.bound(10358, 10007)
    walk(s, street["BoundCenterX"], street["BoundCenterZ"])
    run_pending(s)
    assert 26000 in {t.get("ForceNum") for t in s.data["zone_troops"].values()}
    # the scene's end, the gate, force 20000's, force 21000's, the plaza, the boss's, then the finale: once each
    assert [line for _, _, line in lines_shown(s)] == [7200, 7210, 7220, 7230, 7250, 7260, 7270, 7280, 7290, 7300]
    # no result window (decision B2, the original's): the room is left after the finale
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)
    leave = [i for i, w in enumerate(s.sent) if w.proto == game.S2C_MISSION_LEAVE]
    assert len(leave) == 1 and leave[0] > scene_sent_at(s, m10358.GLG) > line_sent_at(s, 7300) and s.data["mission_won"]
    # frames 25:48.5-26:03: a green line from the hero and a MINE pillar and glowing area on the south-east street
    # with 7280 (effects.pillars 25:52-25:59), the hero inside it at 26:02.5 (bound 10007)
    assert marks(s)[-2:] == [(10007, 1), (10007, 0)]


def test_thompson_points_out_the_captain_as_the_hero_enters_the_boss_plaza():
    # harness report row #7 and frames 24:25-24:31: the hero comes down into the plaza, enters bound 13001 at 24:27.5
    # and 7260 shows at 24:28 (with the boss's frame, 24:28); force 22000 had fought the militia 13000 there since
    # 22:22 on the minimap (tracks R1 / C1), so a fight with it cannot be the cue. The commander notice (7800 / 7810,
    # read at 24:33 as Grey Rock's 6022 / 6023, the same texts) follows the line
    s = mission_room(10358)
    run_pending(s)
    walk(s, *centre(13001))
    run_pending(s)
    assert lines_shown(s)[-1] == (THOMPSON, 1, 7260)
    notices = [tuple(a[2:4]) for a in acts(s, director.ACT_NOTICE_WINDOW)]
    assert (7800, 7810) in notices and line_sent_at(s, 7260) < notice_sent_at(s, 7800)


def notice_sent_at(s, title):
    return next(i for i, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION and
                bytes(w.buf)[:4] == director.ACT_NOTICE_WINDOW.to_bytes(4, "little") and
                int.from_bytes(bytes(w.buf)[8:12], "little") == title)


def line_sent_at(s, line):
    """Index in s.sent of the 0xc76f that showed `line`."""
    return next(i for i, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION and
                bytes(w.buf)[:4] == director.ACT_HELP_TEXT_BY_TROOP.to_bytes(4, "little") and
                int.from_bytes(bytes(w.buf)[16:20], "little") == line)


def test_a_fight_won_before_its_place_is_reached_waits_for_that_place():
    # live 2026-09-30 13:52:41: force 20000 fell before the hero reached the gate 10001, and 7220 played 6 s before
    # the gate's 7210; 13:53:30: the boss 22003 fell 0.9 s before the hero entered the plaza 13001, and 7270 / 7280
    # came before 7260. On the tape each place comes first (7210 22:4x, 7220 23:01.75; 7260 24:28, 7270 25:37)
    steps = director.script(10358)
    gate = next(st for st in steps if st["on"] == "bound" and st.get("bound") == 10001)
    plaza = next(st for st in steps if st["on"] == "bound" and st.get("bound") == 13001)
    fight = next(st for st in steps if st["on"] == "down" and st.get("force") == 20000)
    boss = next(st for st in steps if st["on"] == "down" and st.get("troop") == 22003)
    assert fight.get("needs") == gate.get("id") is not None
    assert boss.get("needs") == plaza.get("id") is not None


def scene_sent_at(s, index):
    """Index in s.sent of the ActCutScenePlayCutScene that played scene `index`."""
    return next(i for i, w in enumerate(s.sent) if w.proto == game.S2C_SCRIPT_ACTION and
                bytes(w.buf)[:8] == struct.pack("<II", director.ACT_CUTSCENE, index))


def routes(s, since=0):
    """{troop uid: path 1} of the SetSpawnAI 0x5083 sent after s.sent[since] with a path (layout game.send_spawn_ai)."""
    out = {}
    for w in s.sent[since:]:
        b = bytes(w.buf)
        if w.proto == game.S2C_SET_SPAWN_AI and struct.unpack_from("<H", b, 0)[0] != 0xffff:
            out[struct.unpack_from("<H", b, 8)[0]] = struct.unpack_from("<H", b, 0)[0]
    return out


def to_the_gate_fights_end(s):
    run_pending(s)
    walk(s, *centre(10001))
    run_pending(s)
    since = len(s.sent)
    down_all(s, [20000, 20001])
    run_pending(s)
    return since


def test_the_militiaman_and_the_villagers_by_the_gate_run_for_the_flee_point_with_7230():
    # the tape (the minimap's allied marks): the group on the militiaman 11000's spawn runs from ~23:06, with 7230
    # "You protect your villagers!", east through the gate along the road to 도망 (bound 10006) and is gone at
    # 23:42.5; the zone's lanes 10002-10013 start by the 12 villagers north of bound 10000. Each runs its lane under
    # its own program (0x5083 path 1, the COMPANIONS plan's option A), with 7230, after 7220 and the barrel notice
    s = mission_room(10358)
    since = to_the_gate_fights_end(s)
    assert routes(s, since) == m10358.GATE_FLIGHT
    first = next(i for i, w in enumerate(s.sent) if i >= since and w.proto == game.S2C_SET_SPAWN_AI)
    assert notice_sent_at(s, 7820) < first < line_sent_at(s, 7230)
    sent = next(bytes(w.buf) for w in s.sent[since:] if w.proto == game.S2C_SET_SPAWN_AI)
    assert struct.unpack_from("<i", sent, 0x16)[0] == game.table_ai(162010)      # the militiaman keeps his program


def test_the_villagers_at_bound_10008_cry_out_then_take_their_lanes():
    # lanes 10014-10021 start by the 8 villagers inside bound 10008; their beat is ours (no mark of theirs on the
    # tape): after their "H-help...!" (7240)
    s = mission_room(10358)
    to_the_gate_fights_end(s)
    since = len(s.sent)
    walk(s, *centre(10008))
    run_pending(s)
    assert routes(s, since) == m10358.STREET_FLIGHT
    first = next(i for i, w in enumerate(s.sent) if i >= since and w.proto == game.S2C_SET_SPAWN_AI)
    assert first > line_sent_at(s, 7240)


def test_a_fleeing_troop_reported_at_the_flee_point_leaves_the_battle():
    # the host's 0x50b0 positions (game.troop_sync): a routed troop inside 도망 is disabled and gone (the tape: the
    # mark gone at 23:42.5); one still on the road, or a troop never routed, stays
    s = mission_room(10358)
    to_the_gate_fights_end(s)
    role = game.make(NoSave(), 0)
    sync = lambda recs: role.handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, sync_body(recs)))
    flee = director.bound(10358, m10358.FLEE)
    x, z = round(flee["BoundCenterX"]), round(flee["BoundCenterZ"])
    sync([(15005, x - 3000, 0, z), (12000, x, 0, z)])
    gone = lambda: [a[2] for a in acts(s, game.ACT_ENABLE_TROOP) if a[3] == 0]
    assert gone() == []
    sync([(15005, x, 0, z), (m10358.MILITIAMAN, x + 200, 0, z)])
    assert sorted(gone()) == [m10358.MILITIAMAN, 15005] and {15005, m10358.MILITIAMAN} <= s.data["down"]
    assert 15005 not in s.data["battle"].troops
    sync([(15005, x, 0, z)])
    assert sorted(gone()) == [m10358.MILITIAMAN, 15005]          # once
    game.mission_troop_down(s, NoSave(), 15006)                   # one fallen on the road is not "left" again
    sync([(15006, x, 0, z)])
    assert sorted(gone()) == [m10358.MILITIAMAN, 15005] and 15006 not in s.data["director"]["exits"]


def test_the_finale_plays_glens_rescue_then_leaves_with_no_result_window():
    # 7300 at 26:08.75, black at 26:14, Glen's rescue GLG 26:15-27:48 (85 s, the map's cutscene list place 2, no
    # ACTOR track), then the field: no "Mission Succeeded" and no window (decision B2); the room is left once the
    # scene is over, and the field's entry carries the return warp 30001 whose EnterScript plays 11_Village_chief
    s = mission_room(10358)
    run_pending(s)
    street = director.bound(10358, 10007)
    walk(s, street["BoundCenterX"], street["BoundCenterZ"])
    steps = director.script(10358)
    after = next(st for st in steps if st["on"] == "after" and st["step"] == "sandwich")
    assert after["do"] == [("cutscene", 2, 85), ("win",)] and not any(st["on"] == "down" and st.get("force") == 26000
                                                                       for st in steps)
    run_pending(s)
    assert cutscenes(s) == [9, 2]
    assert not any(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent)
    leave = next(i for i, w in enumerate(s.sent) if w.proto == game.S2C_MISSION_LEAVE)
    assert leave > scene_sent_at(s, 2) > line_sent_at(s, 7300)

def test_the_barricade_line_waits_for_the_hero_at_the_central_plaza():
    # live 2026-10-24 (AC3): the militia felled force 21000 alone a minute in and 7250 played far from the hero; the
    # tape's hero is at the plaza for it (24:16 his last kill there, 7250 at 24:17.5)
    s = mission_room(10358)
    run_pending(s)
    s.state = NoSave()
    down_all(s, (21000, 21001, 21002, 21004))           # force 21000's four troops
    run_pending(s)
    assert 7250 not in [line for _, _, line in lines_shown(s)]
    passage = director.bound(10358, 10003)
    walk(s, passage["BoundCenterX"], passage["BoundCenterZ"])
    run_pending(s)
    assert [line for _, _, line in lines_shown(s)].count(7250) == 1

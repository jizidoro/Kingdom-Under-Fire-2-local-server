"""Flamegrass Valley 10303: the director's table (kuf2/scenes/m10303.py) in a mission room. The times quoted are the
original's (playthrough part 4, read frame by frame 2026-10-24; the table's docstring)."""
import struct

from kuf2 import combat, director, game, obf, quest, rules
from test_battle import NoSave, acts, down_all, mission_room, opened, pkt, walk
from test_director import lines_shown, press, prompts, run_pending, shown

SPOT = 10303
GUIDE, ELF, ICE, FIRE, COMMANDER = 31114, 31113, 10201, 10204, 13001
SCOUTS = (23002, 23003, 23004, 23005, 23006)
MAIN = (24100, 24200, 24300, 31100)
WAGONS = (31106, 31104, 31107)
BOSS = 24313


def centre(name):
    b = director.bound(SPOT, name)
    return b["BoundCenterX"], b["BoundCenterZ"]


def area(name):
    return director.bound(SPOT, name)["EventBoundID"]


def said(s):
    return [line for _, _, line in lines_shown(s)]


def by(s, line):
    """The speaker uid of a line shown."""
    return next(uid for uid, _, ln in lines_shown(s) if ln == line)


def marks(s):
    return [(a[1], a[3]) for a in acts(s, director.ACT_HIGHLIGHT_AREA)]


def notices(s, row=director.NOTICE_LEFT):
    """The notices shown: the left panel's (NoticeTable 10003), or row's (director.NOTICE_MID: the centred banner)."""
    return [tuple(i for i in a[2:6] if i != director.NO_TEXT) for a in acts(s, director.ACT_NOTICE_WINDOW)
            if a[1] == row]


def marches(s, to):
    """The troops ordered to march to that bound (ActTroopMoveToArea)."""
    return {a[2] for a in acts(s, director.ACT_MOVE_TO_AREA) if a[3] == area(to)}


def f_up(s):
    """The F prompts up: put up and neither taken down nor answered (the client drops the one pressed)."""
    return [p for p, k in prompts(s).items() if k == director.KEY_ACTION and p not in getattr(s, "pressed", set())]


def troops_of(s, force):
    return [u for u, t in s.data["zone_troops"].items() if t.get("ForceNum") == force]


def mine(s):
    return [a[2] for a in acts(s, game.ACT_CHANGE_FORCE)]


def left(s):
    return [a[2] for a in acts(s, game.ACT_ENABLE_TROOP) if a[3] == 0]


def room():
    s = mission_room(SPOT)
    s.state = NoSave()
    run_pending(s)
    return s


def to_choice(s):
    walk(s, *centre("(2)시작"))
    down_all(s, [22004])
    run_pending(s)


def pick(s, bound):
    walk(s, *centre(bound))
    run_pending(s)
    press(s, director.KEY_ACTION)
    run_pending(s)


def to_ambush(s):
    to_choice(s)
    pick(s, "(2)법사냉기선택")
    walk(s, *centre("(3)멈추시오"))
    run_pending(s)
    down_all(s, SCOUTS)
    run_pending(s)
    walk(s, *centre("(4)본대만나기강조"))
    run_pending(s)


def down_main(s, order=MAIN):
    for f in order:
        down_all(s, troops_of(s, f))
    run_pending(s)


def hit_prop(s, prop, times=5):
    role = game.make(NoSave(), 0)
    hit = bytes(7) + struct.pack("<HH", 1, 0) + bytes([1]) + obf.u32(prop)
    for _ in range(times):
        role.handlers[combat.C2S_ABILITY_EXECUTE](s, pkt(combat.C2S_ABILITY_EXECUTE, hit))


def sync_at(s, *records):
    """A 0x50b0 from the host: (uid, x, z) records (as test_battle.sync_body, at the given places)."""
    body = struct.pack("<H", len(records))
    for uid, x, z in records:
        q, p15 = obf.pos_xz(round(x), round(z))
        body += bytes([0, 0]) + struct.pack("<Hh", uid, 0) + q + struct.pack("<h", 0) + bytes([p15, 1])
    game.make(NoSave(), 0).handlers[game.C2S_TROOP_SYNC](s, pkt(game.C2S_TROOP_SYNC, body))


def test_the_runner_meets_the_hero_and_the_way_ahead_is_marked():
    # 21011 at 34:35 (the frame reads "... We're a militia organised to rescue the prisoners.", not 21010), 21013 at
    # 34:38, a green pillar ahead 34:42-34:46: the direction mark, taken down by its off switch around it
    s = room()
    assert lines_shown(s) == [(GUIDE, 0, 21011), (GUIDE, 0, 21013)]
    assert marks(s) == [(area("(0)시작방향지시"), 1)]
    walk(s, *centre("(1)방향끄기"))
    assert marks(s)[-1] == (area("(0)시작방향지시"), 0)


def test_the_room_shows_the_originals_whole_panel_as_the_hud_returns():
    # the tape: the runner's 21011 over the opening camera (34:34.9-34:37.6, no HUD), black, then the HUD with the
    # whole panel (34:37.9: "Flamegrass Valley", success "Rescue Flamegrass Villagers", failure "Let Hero and all
    # ally Troops die" / "Fail in rescuing Flamegrass Villagers") and the runner's 21013 in the same frame
    s = mission_room(SPOT)
    assert not acts(s, game.ACT_SITUATION_TITLE)            # not at the room's start
    run_pending(s)
    assert [a[2] for a in acts(s, game.ACT_SITUATION_TITLE)] == [30000]
    assert [a[2:] for a in acts(s, game.ACT_SITUATION_LINE)] == [[30100, 30101], [30200, 30201], [30200, 30202]]
    seen = shown(s)
    assert seen.index(("line", 21011)) < seen.index(("title", 30000)) < seen.index(("panel", 30202)) <         seen.index(("line", 21013))


def test_the_orcs_sniff_the_hero_out_as_he_comes_up_the_mouth():
    s = room()
    walk(s, *centre("(2)시작"))
    run_pending(s)
    assert lines_shown(s)[2:] == [(22003, 0, 21030), (22003, 0, 21040)]


def test_the_scorpions_fall_puts_the_orcs_to_flight_and_the_envoys_offer_a_wizard():
    s = room()
    to_choice(s)
    assert said(s)[2:] == [21030, 21040, 21041, 21050, 21051, 21052, 21053, 21054, 21055]
    assert [by(s, i) for i in (21041, 21050, 21052, 21055)] == [22002, ELF, GUIDE, ELF]
    assert set(troops_of(s, 22000) + troops_of(s, 22001)) <= marches(s, "(2)오크도망")
    assert {ELF} <= marches(s, "(2)마법사선택_나이틀린") and {ICE} <= marches(s, "(2)법사냉기도착")
    assert notices(s, director.NOTICE_MID) == [(21063, 21064)] and not notices(s)   # "Select either the Ice or Fire
    # Troop. / Press F ...": the banner at the top (the tape 35:36-35:44: the red seal centred above its band)
    assert {(area("(2)법사냉기선택"), 1), (area("(2)법사화염선택"), 1)} <= set(marks(s))
    assert not f_up(s)                                      # F only at a wizard


def test_f_at_the_ice_wizard_makes_it_the_players_and_the_envoys_leave():
    s = room()
    to_choice(s)
    walk(s, *centre("(2)법사냉기선택"))
    run_pending(s)
    assert len(f_up(s)) == 1                                # "[F] Investigate" (35:42)
    press(s, director.KEY_ACTION)
    run_pending(s)
    assert mine(s) == [ICE] and said(s)[-1] == 21080 and by(s, 21080) == ELF
    assert set(left(s)) == {FIRE, ELF}
    walk(s, *centre("(2)법사화염선택"))                       # the Fire branch is closed
    run_pending(s)
    assert not f_up(s) and 21081 not in said(s) and mine(s) == [ICE]


def test_a_blizzard_on_the_ground_counts_when_it_strikes_the_column():
    # live 2026-11-06 01:57:22: the client casts Blizzard on a place, "troop 10201 casts 10246 on troop 65535", and only
    # its executes name the troops it struck (24104, 24304): the step waited for a target the cast never has
    s = room()
    to_ambush(s)
    x, z = centre("(4)본대만나기")
    director.on_arrive(s, {24101: (x, 0, z)})
    director.on_skill(s, ICE, 0xffff, 10246)
    run_pending(s)
    assert 21260 not in said(s)
    combat.apply_ability(s, ICE, 10246, 1, [(24203, [0])], lambda *a: None, lambda *a: None)
    run_pending(s)
    assert said(s)[-2:] == [21260, 21261]


def test_the_envoys_come_only_at_the_scorpions_fall():
    # live 2026-11-06 01:40:14: placed at the zone's marks from the start, the Fire wizard's client AI threw Meteor on
    # the Scorpion 1 s into the room, 6 000 away: down at 01:40:17, before the hero had taken a step (the tape: the hero
    # kills it 35:04, the envoys come after it, 35:09)
    s = room()
    assert GUIDE in s.data["zone_troops"] and said(s)[0] == 21011
    assert not {ELF, ICE, FIRE} & set(s.data["zone_troops"])
    to_choice(s)
    assert {ELF, ICE, FIRE} <= set(s.data["zone_troops"])


def test_the_envoys_who_left_stay_gone_when_the_scouts_wake():
    # live 2026-11-06 01:42:34: the scouts' wake is an enable-all, which brought the Fire wizard back (it had left at
    # 01:42:24); telemetry had it enabled, its Meteor on the scouts every 12 s
    s = room()
    to_choice(s)
    pick(s, "(2)법사냉기선택")
    s.sent.clear()
    walk(s, *centre("(3)멈추시오"))
    run_pending(s)
    sent = [struct.unpack_from(f"<{len(bytes(w.buf)) // 4}I", bytes(w.buf)) for w in s.sent
            if w.proto == game.S2C_SCRIPT_ACTION and len(bytes(w.buf)) % 4 == 0]
    at = max(i for i, a in enumerate(sent) if a[:3] == (game.ACT_ENABLE_ALL_TROOPS, 1, 1))
    assert {a[2] for a in sent[at + 1:] if a[0] == game.ACT_ENABLE_TROOP and a[3] == 0} == {FIRE, ELF}


def test_f_pressed_away_from_a_wizard_is_put_up_again_and_the_other_is_picked():
    s = room()
    to_choice(s)
    walk(s, *centre("(2)법사냉기선택"))                       # its prompt up ...
    walk(s, *centre("(2)법사화염선택"))                       # ... then the Fire wizard's
    run_pending(s)
    press(s, director.KEY_ACTION)                           # the client answers both
    run_pending(s)
    assert mine(s) == [FIRE] and 21081 in said(s) and 21080 not in said(s)
    assert set(left(s)) == {ICE, ELF}
    assert not f_up(s)                                      # the Ice prompt, put up again, came down with its branch


def test_the_scouts_come_at_halt_with_the_militia_and_the_convoy_leaves_its_pocket():
    s = room()
    to_choice(s)
    pick(s, "(2)법사냉기선택")
    assert not set(SCOUTS) & set(s.data["zone_troops"])     # held (inactive in the zone)
    walk(s, *centre("(3)멈추시오"))
    run_pending(s)
    assert set(SCOUTS) | {COMMANDER, 31129, 31130, 31131} <= set(s.data["zone_troops"])
    assert said(s)[-3:] == [21130, 21113, 21121] and {by(s, i) for i in (21130, 21113, 21121)} == {23004}
    x, z = centre("(13)전망포로1")                            # the wagons onto the lookout's marks, far on the rim
    assert (s.data["zone_troops"][31106]["PosX"], s.data["zone_troops"][31106]["PosZ"]) == (round(x), round(z))


def test_the_meeting_fades_into_the_ambush_and_the_column_comes_down():
    s = room()
    to_ambush(s)
    assert said(s)[said(s).index(21140):] == [21140, 21141, 21180, 21190]
    assert by(s, 21141) == by(s, 21190) == COMMANDER
    fades = [(a[3], a[1]) for a in acts(s, game.ACT_FADE)]
    assert fades == [(0, 1), (1, 1)]                        # black (37:04-37:06), then the grass
    x, z = centre("(4)유저매복위치")
    assert s.data["hero_pos"][0] == round(x) and s.data["hero_pos"][2] == round(z)
    x, z = centre("(7)본대위치1-1")
    assert (s.data["zone_troops"][24101]["PosX"], s.data["zone_troops"][24101]["PosZ"]) == (round(x), round(z))
    assert 10065 in opened(s) and 10068 not in opened(s)    # out of the pocket; its north wall stays
    column = {u for f in MAIN for u in troops_of(s, f)}
    assert column <= marches(s, "(4)본대만나기")


def test_the_column_in_the_trap_calls_for_the_blizzard_and_the_commander_nags():
    s = room()
    to_ambush(s)
    sync_at(s, (24101, *centre("(7)본대위치1-1")))           # not there yet
    run_pending(s)
    assert 21203 not in said(s)
    sync_at(s, (24101, *centre("(4)본대만나기")))             # the host reports the column in the trap
    run_pending(s)
    assert said(s)[-2:] == [21203, 21206] and (21204, 21207) in notices(s)
    director.on_skill(s, ICE, 24203, 0)                     # the Blizzard
    run_pending(s)
    assert said(s)[-2:] == [21260, 21261] and by(s, 21260) == 24203 and by(s, 21261) == COMMANDER
    assert set(troops_of(s, 13000)) - set(s.data.get("down", ())) <= marches(s, "(4)본대만나기")


def test_a_blizzard_cast_at_once_needs_no_nagging():
    s = room()
    to_ambush(s)
    x, z = centre("(4)본대만나기")
    director.on_arrive(s, {24101: (x, 0, z)})
    director.on_skill(s, ICE, 24101, 0)
    run_pending(s)
    assert 21203 in said(s) and 21206 not in said(s) and said(s)[-2:] == [21260, 21261]


def test_the_main_forces_fall_sends_the_hero_to_the_barricade_whatever_falls_last():
    s = room()
    to_ambush(s)
    down_main(s, MAIN[::-1][:3])
    assert 21300 not in said(s)
    down_main(s, MAIN[:1])
    assert said(s)[-2:] == [21300, 21306] and notices(s)[-1] == (21317, 21318)


def test_the_barricade_opens_the_shortcut_and_starts_the_four_minute_clock():
    s = room()
    to_ambush(s)
    hit_prop(s, 10002)                                      # broken early: it waits for the main force's fall
    assert 10063 not in opened(s) and not acts(s, rules.ACT_SITUATION_TIME)
    down_main(s)
    assert {10063, 10064} <= opened(s)
    assert [30300] == [a[2] for a in acts(s, game.ACT_SITUATION_GROUP) if a[2] == 30300]
    assert acts(s, rules.ACT_SITUATION_TIME)[0][2:] == [30300, 30300, 240]


def test_the_convoys_front_stops_the_clock_and_meets_the_hero_once():
    s = room()
    to_ambush(s)
    down_main(s)
    hit_prop(s, 10003)
    walk(s, *centre("(13)전망1"))
    walk(s, *centre("(10)유저도착체크2"))
    run_pending(s)
    assert acts(s, rules.ACT_SITUATION_TIME)[-1][2:] == [30300, 30300, 0]
    assert [a[2] for a in acts(s, rules.ACT_SITUATION_REMOVE_GROUP)] == [30300]
    assert said(s)[-2:] == [21410, 21420] and by(s, 21410) == ICE and by(s, 21420) == 24305
    assert said(s).index(21310) < said(s).index(21410)       # the lookout's lines first
    x, z = centre("(13)마지막포로1")
    assert (s.data["zone_troops"][31106]["PosX"], s.data["zone_troops"][31106]["PosZ"]) == (round(x), round(z))
    walk(s, *centre("(13)2번스킬쓰세요"))                    # the other arrival check: nothing again
    run_pending(s)
    assert said(s).count(21420) == 1 and 10068 in opened(s)


def test_the_wagons_then_ochankin_win_the_room_and_its_quest():
    s = mission_room(SPOT)
    s.data["char"]["quests"] = {"active": {"1110501": {"counts": [0] * 5}}, "done": []}
    s.state = NoSave()
    run_pending(s)
    to_ambush(s)
    down_main(s)
    hit_prop(s, 10002)
    walk(s, *centre("(10)유저도착체크2"))
    run_pending(s)
    director.on_engage(s, 0, 31134)                         # the fight with the convoy
    run_pending(s)
    assert said(s)[-1] == 21422 and 10054 in opened(s) and set(troops_of(s, 25100)) <= marches(s, "(13)마지막포로부대앞")
    director.on_hp(s, 31104, 50, 100)                        # a wagon Ogre hit
    run_pending(s)
    assert notices(s)[-1] == (21434, 21433)                  # the title "Take care of the Ogres first." (41:34)
    assert {31104, 31106, 31107} <= marches(s, "(0)포로막기실패")
    down_all(s, [BOSS])                                     # Ochankin before the wagons: not yet
    run_pending(s)
    assert not s.data.get("mission_won")
    down_all(s, [31107, 31104, 31106])
    run_pending(s)
    assert said(s)[-2:] == [21424, 21500] and s.data.get("mission_won")
    assert [a[2] for a in acts(s, game.ACT_SITUATION_DONE)] == [30101]
    assert sum(w.proto == game.S2C_MISSION_COMPLETE for w in s.sent) == 1
    assert s.data["char"]["quests"]["active"]["1110501"]["counts"][0] == 1


def test_the_room_is_not_won_by_its_last_hostile():
    s = room()
    hostile = [u for u, t in s.data["zone_troops"].items() if game.hostile(t)]
    down_all(s, hostile)
    run_pending(s)
    assert not s.data.get("mission_won")


def test_the_fire_wizard_calls_for_meteor_on_the_scorpions():
    # 21081 / 21201 / 21202 / 21205 / 21262: the Fire branch's own lines; the Ice wizard, gone, casts nothing
    s = room()
    to_choice(s)
    pick(s, "(2)법사화염선택")
    walk(s, *centre("(3)멈추시오"))
    run_pending(s)
    down_all(s, SCOUTS)
    run_pending(s)
    walk(s, *centre("(4)본대만나기강조"))
    run_pending(s)
    sync_at(s, (24101, *centre("(4)본대만나기")))
    run_pending(s)
    assert said(s)[-2:] == [21201, 21205] and (21202, 21207) in notices(s)
    director.on_skill(s, ICE, 24101, 0)
    run_pending(s)
    assert 21260 not in said(s)
    director.on_skill(s, FIRE, 24101, 0)
    run_pending(s)
    assert said(s)[-2:] == [21260, 21262] and not {21080, 21203, 21206} & set(said(s))


def test_the_convoy_is_met_without_the_barricade_and_the_room_still_won():
    # a hero who slips past the barricade: no clock, but the convoy's front, the wagons and Ochankin win the room
    s = room()
    to_ambush(s)
    down_main(s)
    walk(s, *centre("(13)2번스킬쓰세요"))
    run_pending(s)
    assert 21420 in said(s) and not acts(s, rules.ACT_SITUATION_TIME)
    down_all(s, list(WAGONS) + [BOSS])
    run_pending(s)
    assert s.data.get("mission_won")


def test_wagons_and_ochankin_felled_before_the_convoys_front_win_only_after_it():
    s = room()
    to_ambush(s)
    down_main(s)
    hit_prop(s, 10002)
    down_all(s, list(WAGONS) + [BOSS])
    run_pending(s)
    assert not s.data.get("mission_won") and 21424 not in said(s)
    walk(s, *centre("(10)유저도착체크2"))
    run_pending(s)
    assert s.data.get("mission_won") and said(s).index(21420) < said(s).index(21424) < said(s).index(21500)

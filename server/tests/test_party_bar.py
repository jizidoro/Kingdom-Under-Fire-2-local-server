"""The party bar in a solo mission (owner, live 2026-09-30 15:13 in Grey Rock 10234, qwe123 ISABELLA: "bug in the ui for
hp of troops"; ScreenShot_683150_2026_9_30_15_13_39.jpg: a "1 Lv.6 qwe123" bar at the top left whose first troop HP
bar ran across the whole screen). The original shows no party bar in a solo mission (qeeQjhgO8ss, Grey Rock).

1. Why it showed: in a Battle spot HUDPartyInfo lists the players of its side from the player manager (0x14076e480 ->
   0x14076d530) and clears the list when it holds only the local player: its key, Player +0x54 = 0x3f4f struct +0x0f
   (0x140cf9d70), equal to common+0xd4, the character id the client names in its game login 0x5084 (0x140cbbeac).
   We sent the class there: 3 for qwe123 (character 2), so the bar listed her as another player. Aldric's class 0 kept
   him off the list (a key of 0 is skipped), which is why no bar showed before.
2. Why the troop bar ran off the screen: the bar is hp / max of the troop (vt+0x2c8 / vt+0x2c0 = troop +0xcf8 / +0xcd8).
   The stat parser 0x140cfbe30 reads a stat block's troop-stat count from the block's first byte even when the block
   is empty, then parses that many entries: our 0x3f50 entries sent the block empty (u16 0), so the last entry, the
   deck troop, took its count and stats from the bytes after the packet; a stat 0 (HP_MAX) among them goes to the
   troop's max through its stat listener (0x1407eb090 -> vt+0x2b0), a few points against 8,840 HP.
3. The owner's call (2026-09-30 16:5x, after the bar was gone): the bar comes back in solo missions, for every hero,
   with the right values: a deliberate deviation from the original. The key is game.player_key: never 0 (listed),
   never the character id (not cleared as "only me"), above every u16 player / owner id (Player +0x50: our slot 1,
   NP owners 0xfa and forces 10001..40040; NP owners' Players keep +0x54 = 0 from the reset 0x140b41730)."""
import struct

from kuf2 import game, obf
from test_army import army, entered, pkt, troop_entries
from test_battle import parse_stat
from test_multi_character import Session, two_character_state

GREY_ROCK = 10234


def party_bar_shows(key, my_id, ai=False, flag=0):
    """0x14076e480 for a solo Battle room with our one Player (team = the manager's, not in a party): listed when not AI
    and (+0x358 or key != 0), and the list is cleared when its one entry's key is common+0xd4 (the character id)."""
    listed = not ai and (flag != 0 or key != 0)
    return listed and key != my_id


def test_the_room_player_key_shows_the_party_bar_for_every_hero(tmp_path):
    st, acct, aldric, hero = two_character_state(tmp_path)
    aldric["class"], hero["class"] = 0, 3
    for c in (hero, aldric):
        s = Session()
        game.make(st, 0).handlers[game.C2S_GAME_LOGIN](s, pkt(game.C2S_GAME_LOGIN,
                                                              struct.pack("<IHI", c["id"], 0, GREY_ROCK)))
        b = bytes(next(w for w in s.sent if w.proto == game.S2C_START_PLAYER_INFO).buf)
        assert struct.unpack_from("<H", b)[0] == 1
        key = struct.unpack_from("<I", b, 2 + 0x0f)[0]              # -> Player +0x54
        assert key == game.player_key(c) and key > 0xffff             # no u16 player / owner id
        assert party_bar_shows(key, c["id"])                          # Aldric too (class 0 was key 0: left off)
    assert not party_bar_shows(1, 1) and not party_bar_shows(0, 1)    # the original's solo (key = id), Aldric's 0


def test_the_hero_is_found_by_the_same_key_in_the_room(tmp_path):
    """Readers that find the room's Player by key (0x140b42f80 / 0x140b427d0, and 0x140de4a40 for a firework in the
    battle state) get the key 0x3f4f gave it; in town the firework names the character id (0x140de4830)."""
    from kuf2 import combat, state, world
    from test_quest import Session as WorldSession, use_body
    st = state.State(tmp_path / "db.json")
    role = world.make(st, 0, "127.0.0.1", 0)
    s = WorldSession()
    s.data["account"] = {"id": 7}
    c = s.data["char"]
    c.update(id=2, bag=[{"code": 358910010, "slot": 2, "count": 2, "serial": 3, "bound": False}])   # firework
    use = lambda: role.handlers[world.C2S_USE_ITEM](s, pkt(world.C2S_USE_ITEM, use_body(358910010, 3)))
    use()
    assert s.sent[-1].proto == world.S2C_FIREWORK and bytes(s.sent[-1].buf)[4:] == struct.pack("<I", 2)   # town
    room = WorldSession()
    room.data["battle"] = combat.Battle()
    room.w = type("W", (), {"is_closing": lambda self: False})()
    st.game_sessions = {7: room}
    for entry in c["cooldowns"].values():
        entry[1] = 0  # A second firework after its cooldown, now in the room.
    use()
    assert s.sent[-1].proto == world.S2C_FIREWORK
    assert bytes(s.sent[-1].buf) == obf.u32(358910010) + struct.pack("<I", game.player_key(c))


def client_stats(block, after=b"\0" * 8):
    """The troop stats 0x140cfbe30 takes from a stat block: u8 count read from the block's first byte (the byte after
    the block when it is empty), then count entries. Returns (entries, bytes read)."""
    data = block + after
    n, i, out = data[0], 1, []
    for _ in range(n):
        sid, v, k = parse_stat(data[i:])
        out.append((sid, v))
        i += k
    return out, i


def state_stat_block(b, at):
    """The stat block of a troop-state tail (0x140d0cdc0) whose 61-byte state starts at `at`, and the bytes after it."""
    i = at + 0x3d
    np = obf.T1[b[i]] & 1
    i += 1 + (22 if np else 0)
    i += 2 + 5 * struct.unpack_from("<H", b, i)[0]             # 0x140d0e060
    i += 2 + 5 * struct.unpack_from("<H", b, i)[0]             # 0x140d0de10
    n = struct.unpack_from("<H", b, i)[0]
    return b[i + 2:i + 2 + n], b[i + 2 + n:]


def test_every_stat_block_carries_its_own_count():
    c, _ = army(1, level=6)
    _, s = entered(GREY_ROCK, c)
    hero, deck = troop_entries(s)
    assert deck["uid"] == 1 and deck["hp"] == deck["max"] == 8830     # the tape's (T1.3)
    for e in (hero, deck):                                     # 0x3f50: the deck troop is the packet's last entry
        assert len(e["stats"]) >= 1, f"troop {e['uid']}: empty block, its count comes from past the packet"
        assert client_stats(e["stats"], b"\x06\x00\x77\x4e\x3f")[1] <= len(e["stats"])
    for w in s.sent:                                           # 0x50cb / 0x50b8: the deck troop and the hero
        if w.proto in (game.S2C_ENTER_CELL_TROOP, game.S2C_MISSION_TROOP_INFO):
            b = bytes(w.buf)
            block, after = state_stat_block(b, 3 if w.proto == game.S2C_ENTER_CELL_TROOP else 0)
            assert len(block) >= 1 and client_stats(block, after)[1] <= len(block)
            assert 0 not in dict(client_stats(block, after)[0])     # no troop HP_MAX from a stray byte

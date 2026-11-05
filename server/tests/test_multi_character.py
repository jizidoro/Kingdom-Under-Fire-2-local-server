"""An account with two characters: the game server plays the one chosen. Live 2026-09-30 13:18:33: the owner's new
hero 'qwe123' (character 2 of account 1) entered Glen's camp and the game login (0x5084) failed with KeyError
'no account 2': the login's u32 is the character's id, which matched the account's only by chance while the account
had one character; the session then read the account's first character everywhere."""
import struct

from kuf2 import combat, game, state
from test_battle import pkt

MIST_FIELD_CAMP = 10352


def two_character_state(tmp_path):
    st = state.State(tmp_path / "db.json")
    acct = st.account_for_steam(1, "T")
    aldric = st.create_character(acct, "Aldric", 1, "00" * 0x40)
    hero = st.create_character(acct, "qwe123", 1, "00" * 0x40)   # a full appearance, as creation sends
    aldric["level"], hero["level"] = 30, 1
    return st, acct, aldric, hero


def test_a_character_is_found_by_its_id_with_its_account(tmp_path):
    st, acct, aldric, hero = two_character_state(tmp_path)
    assert st.char_by_id(hero["id"]) == (acct, hero)
    assert st.char_by_id(aldric["id"]) == (acct, aldric)


class Session:
    def __init__(self):
        self.data, self.sent, self.pending = {"battle": combat.Battle()}, [], []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        self.pending.append((delay, fn))


def test_the_game_login_plays_the_chosen_character_not_the_accounts_first(tmp_path):
    st, acct, aldric, hero = two_character_state(tmp_path)
    s = Session()
    game.make(st, 0).handlers[game.C2S_GAME_LOGIN](s, pkt(game.C2S_GAME_LOGIN,
                                                          struct.pack("<IHI", hero["id"], 0, MIST_FIELD_CAMP)))
    assert s.data["char"] is hero and s.data["account"] is acct
    assert game.hero_level(s) == 1                       # the new hero's, not Aldric's 30
    assert st.game_sessions[acct["id"]] is s             # the world finds the session by the account, as before


def test_the_hero_record_names_the_chosen_characters_hero_for_the_waiting_room(tmp_path):
    """Live 2026-09-30 14:24:43 / 14:47:25: qwe123 (ISABELLA, class 3, the account's second character) opened the
    solo waiting room at the Tower door and its Flash got `addMember 0 qwe123 0 4 ...`: $class 0, Glen's portrait.
    The room's own member (0x14065e0a0) takes +0x28 from the lineup's slot 0 record, which is the hero record at
    WorldMapTroopListMgr+0x30 (0x140d977e0); its +0x10 is 0x134b / 0x1081 block +0xac (0x140da1aad, 0x140da1d72),
    looked up in HeroTable (0x1409ef027..0x1409ef08e; keys = E_HeroCode). We sent 0 there, right only for Glen."""
    from kuf2 import world
    st, acct, aldric, hero = two_character_state(tmp_path)
    aldric["class"], hero["class"], hero["level"] = 0, 3, 4
    role = world.make(st, 0, "127.0.0.1", 0)
    for c, cls in ((hero, 3), (aldric, 0)):
        s = Session()
        s.data["char"] = c
        role.handlers[world.C2S_HERO_DETAIL](s, pkt(world.C2S_HERO_DETAIL, b""))
        out = bytes(s.sent[-1].buf)
        assert s.sent[-1].proto == world.S2C_HERO_DETAIL
        assert struct.unpack_from("<I", out, world.HERO_CLASS_AT)[0] == cls
        assert world.hero_block(c)[world.HERO_CLASS_AT] == cls            # 0x1081's block is the same one

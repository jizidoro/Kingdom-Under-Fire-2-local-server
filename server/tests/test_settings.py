"""The original's content settings (kuf2/settings.py: Info.pkg %Content, GAMEFORGE's column, ORIGINAL-RULES-PLAN B)
and the server rules that read them instead of keeping a copy: the character slots of 0x1003, the service code of
0x1021, the hero level cap, the craft level cap. Reads the game tables from the installed game.
Run: py -m pytest -q server/tests"""
import struct

import pytest

from kuf2 import craft, login, settings, world
from kuf2.packet import Reader


def pkt(proto, body=b""):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


class Session:
    def __init__(self):
        self.data = {}
        self.sent = []

    def send(self, w):
        self.sent.append(w)

    def later(self, delay, fn):
        pass

    def out(self, proto):
        return [bytes(w.buf) for w in self.sent if w.proto == proto]


class State:
    def __init__(self, acct=None):
        self.acct = acct

    def save(self):
        pass

    def account_by_id(self, i):
        return self.acct

    def char_by_id(self, i):
        return self.acct, self.acct["characters"][0]

    def account_for_steam(self, steam_id, persona):
        return self.acct


def test_the_settings_are_gameforges_column_of_the_content_table():
    col = settings.column()
    assert len(col) == 62
    assert settings.get("CharSlotMax") == 6 and settings.get("LockedCharSlot") == 2 and settings.get("Level") == 30
    assert settings.get("NationCode") == 10000 and settings.get("LocalBlock_Ext") == "_GAMEFORGE"
    assert settings.get("Event_Diary") == 20191114                  # GAMEFORGE's alone (DEV 20191010)
    assert settings.get("MailFeePerc") == 0.05 and settings.get("NoLeaderShip_MonsterDrop") == 0.7
    assert settings.get("AuctionRegisterFeePerc") == "0.1 0.2 0.4" and settings.get("StartPack") == ""
    with pytest.raises(KeyError, match="NoSuchSetting"):
        settings.get("NoSuchSetting")


def test_use_cubic_is_overridden_with_its_evidence():
    assert settings.original("UseCubic") == "0"                     # the column
    assert settings.get("UseCubic") == 1                            # the Steam game (OFFICIAL-NOTES, the exe)
    for name, (value, evidence) in settings.OVERRIDES.items():
        assert name in settings.column() and value != settings.original(name) and len(evidence) > 40


def world_login(chars):
    acct = {"id": 7, "characters": chars}
    role = world.make(State(acct), 0, "127.0.0.1", 0)
    s = Session()
    role.handlers[world.C2S_GROUP_LOGIN](s, pkt(world.C2S_GROUP_LOGIN, struct.pack("<IIIB", 7, 0, 0, 0)))
    out = s.out(world.S2C_GROUP_LOGIN_RES)[0]
    return out[10 + 0x0d], out[10 + 0x0e]


def test_the_world_login_opens_char_slot_max_less_the_locked_slots():
    # +0x0e -> player info +0x18, the open slots: the character select draws CharSlotMax slots from its own settings
    # and locks those at or past the open count (SelectCharacter.UserSlot($maxSlot, $openSlot), re/ui 91f2fdf2), the
    # cash shop sells CHARSLOT_EXPAND up to CharSlotMax - open (0x14059725c)
    assert world_login([]) == (6, 4)
    five = [{"id": i, "name": f"C{i}", "class": 0} for i in range(5)]
    assert world_login(five) == (6, 5)                              # ours: a character our older builds let in stays open


def test_the_login_reply_carries_the_nation_code_the_client_checks():
    # the client compares the 0x1021 service code with its settings' NationCode (+0x358) and quits on a mismatch
    role = login.make(State({"id": 7, "name": "Aldric"}), 0, "127.0.0.1", 0)
    s = Session()
    body = b"ticket\0Aldric\0en\0\0" + struct.pack("<QI", 1, 0)
    role.handlers[login.C2S_LOGIN_STEAM](s, pkt(login.C2S_LOGIN_STEAM, body))
    out = s.out(login.S2C_LOGIN_RES)[0]
    assert struct.unpack_from("<i", out, 10 + 5)[0] == settings.get("NationCode") == 10000


def test_the_hero_level_cap_is_the_level_setting(monkeypatch):
    assert world.hero_max_level() == 30
    monkeypatch.setitem(settings.column(), "Level", "3")
    assert world.hero_max_level() == 3
    s = Session()
    s.data["char"] = {"id": 1, "class": 0, "level": 1, "exp": 0}
    world.add_exp(s, State(), 10 ** 6)
    assert s.data["char"]["level"] == 3                             # the curve goes to 30; the setting stops it


def test_craft_levels_stop_at_max_craft_level():
    cr = craft.record({})
    craft.gain_exp(cr, 0, 10 ** 9)
    assert settings.get("MaxCraftLevel") == 9 and len(craft.level_rows()) == 15
    assert cr["level"][0] == 9                                      # %CraftLevelUP goes to 15; GAMEFORGE caps at 9

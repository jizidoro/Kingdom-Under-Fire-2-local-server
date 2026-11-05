"""Attendance diary (server/kuf2/diary.py). Run: py -m pytest -q server/tests"""
import datetime
import struct

import pytest

from kuf2 import diary, obf, world
from kuf2.obf import T1, T2
from kuf2.packet import Reader

DAY = datetime.date(2026, 9, 27)      # a Sunday, ISO week 39


class Session:
    def __init__(self):
        self.data = {"char": {"id": 1, "class": 0, "name": "A"}}
        self.sent = []

    def send(self, w):
        self.sent.append(w)


class State:
    saves = 0

    def save(self):
        self.saves += 1


def pkt(proto, body):
    return Reader(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


@pytest.fixture(autouse=True)
def fixed_day(monkeypatch):
    monkeypatch.setattr(diary, "today", lambda: DAY)


def attend(s, st, day=DAY):
    role = world.make(st, 0, "127.0.0.1", 0)
    role.handlers[diary.C2S_ATTEND](s, pkt(diary.C2S_ATTEND, struct.pack("<BHB", day.day, day.year, day.month)))
    return next(w for w in s.sent if w.proto == diary.S2C_ATTEND)


def test_diary_push_lists_the_week_and_month_days():
    s = Session()
    s.data["char"]["attended"] = ["2026-09-01", "2026-09-26", "2026-09-27", "2026-08-31"]
    diary.send_diary(s)
    out = bytes(s.sent[-1].buf)
    head, rest = out[:diary.HEADER], out[diary.HEADER:]
    assert head[3] == diary.ACCRUE_GROUP and struct.unpack_from("<H", head, 6)[0] == 3
    assert head[1] == int(diary.week_row(diary.today())["Week_Reward"])
    assert rest == bytes([1, 0]) + bytes([3, 1, 26, 27])     # week Sun 27th only (26th is Saturday of the last week)


def test_attending_today_records_it_and_answers_with_the_rewards():
    s, st = Session(), State()
    out = bytes(attend(s, st).buf)
    assert s.data["char"]["attended"] == ["2026-09-27"] and st.saves >= 1
    assert out[:2] == b"\0\0"
    block = out[2:2 + diary.REPLY_BLOCK]
    assert struct.unpack_from("<H", block, 0)[0] == 1 and block[3] == 27 and block[4] == diary.ACCRUE_GROUP
    n = out[2 + diary.REPLY_BLOCK]
    entries = out[3 + diary.REPLY_BLOCK:]
    assert n == 1 and len(entries) == 6
    assert obf.dec_u32(entries[:4]) == 602001403 and (T1[entries[4]] << 8 | T2[entries[5]]) == 1   # week 39 Sunday
    assert s.data["char"]["bag"][0]["code"] == 602001403


def test_attending_twice_or_another_day_is_refused():
    s, st = Session(), State()
    attend(s, st)
    s.sent.clear()
    assert bytes(attend(s, st).buf) == struct.pack("<H", diary.RESULT_REFRESH)
    s.sent.clear()
    assert bytes(attend(s, st, DAY - datetime.timedelta(days=1)).buf) == struct.pack("<H", diary.RESULT_REFRESH)
    assert s.data["char"]["attended"] == ["2026-09-27"]


def test_the_seventh_day_of_the_month_adds_the_accrue_rewards():
    c = {"attended": [f"2026-09-{d:02d}" for d in (1, 2, 3, 4, 5, 6)] + ["2026-09-27"]}
    assert diary.rewards(c, DAY)[1:] == ["20071", "20072", "20073"]     # Attendance_Accrue group 1, 7 days


def test_a_full_week_adds_the_all_week_reward():
    c = {"attended": [f"2026-09-{d:02d}" for d in range(20, 27)]}          # Sun 20th .. Sat 26th
    day = datetime.date(2026, 9, 26)
    row = diary.tables.sections("event_diary")["Attendance_Week"][38]            # ISO week 39
    assert diary.rewards(c, day)[:2] == [row["ItemReward_Sat"], row["ItemReward_All"]]    # then the 7-day accrue ones


def test_live_request_bytes_parse_as_day_year_month():
    s, st = Session(), State()
    role = world.make(st, 0, "127.0.0.1", 0)
    role.handlers[diary.C2S_ATTEND](s, pkt(diary.C2S_ATTEND, bytes.fromhex("1bea0709")))   # 2026-09-27, login 03:50
    assert s.data["char"]["attended"] == ["2026-09-27"]

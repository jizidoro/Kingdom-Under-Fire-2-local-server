"""Attendance diary (CommonSubDiary, common sub-object 0x49). The client opens the calendar on entering the city while
today is not among the month's attended days (HUD init 0x140781410 -> 0x140677470; it also needs the server clock,
0x1003), so a day is recorded when the player attends and pushed at every city entry. Tables: event_diary
(Attendance_Week, Attendance_Accrue, EventDiary_Reward: one row per reward group, Ratio 100000).

  S2C 0x10c0 (0x140677590): 8-byte header, u8 n + n days of the week attended (g_arrWeekAttendanceDay, Sunday = 0,
      inferred), u8 m + m days of the month attended (g_arrAttendanceDay). Header +3: the Attendance_Accrue group,
      +6 u16: days attended this month (UpdateAccumAttendanceInfo 0x140971a40); +0, +1, +2 are not mapped (0).
  C2S 0x10c1 (0x1405bdd00, "ReqAttendance" from the calendar 0x1405bc5d0): u8 day, u16 year, u8 month.
  S2C 0x10c2 (0x1405bcdc0): i16 result; on 0 a 10-byte block (+0 u16 days attended this month, +3 u8 the day,
      +4 u8 the accrue group; +2 and +5.. not mapped) and u8 n + n * (coded u32 item code, coded u16 count), shown as
      the rewards (0x1405be950). The client adds the day to its own sets.
  C2S 0x10c3 (0x1405be0e0, after the confirm 71004 "Do you want to use Cubics to completement the attendance?"): u8 n
      + n * (u8 day, u16 year, u8 month) past days of the month to make up; the calendar priced them (0x1405beec0:
      the k-th day item_currency Diary[min(this month's make-ups + k, 8)] = 20, 40, 70, 120, 180, 250, 350, 460, 580
      Cubic) and sent only when the Cubic covers it.
  S2C 0x10c4 (0x1405bd430): i16; 0 -> u8 accrue group, u16 days attended this month, u8 make-ups this month (the
      header's +2), u8 n + n * (u8 day, u8 month) (the calendar adds them); then text 71011 "Completed attendance
      check.<br>The reward will be sent via mail."; 0x40e a quiet refresh, 0x6430 "Not enough Cubics." (0xd01b).
Rewards: the day's ItemReward_<weekday> of Attendance_Week (row = ISO week, 52 rows; inferred), ItemReward_All once the
whole week is attended, and Attendance_Accrue ItemReward1..3 at 7/14/21/28 days of the month (group 1); a made-up
day's by mail (71011).
"""
import datetime
import struct

from . import items, obf, tables
from .net import log
from .packet import Writer

S2C_DIARY = 0x10c0
C2S_ATTEND = 0x10c1
S2C_ATTEND = 0x10c2
C2S_MAKEUP = 0x10c3
S2C_MAKEUP = 0x10c4
CUBIC_SHORT = 0x6430      # "Not enough Cubics." (0xd01b), every Cubic service's
HEADER = 8
REPLY_BLOCK = 10
ACCRUE_GROUP = 1
RESULT_REFRESH = 0x40E    # 0x1405be880: no message, the calendar re-reads the date (other codes print an error;
                          # the client asks twice at login, so a repeat must stay quiet)
WEEKDAYS = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


def today(now=None):
    """The calendar's day: the UTC date (attendance turns at 00:00 UTC, rules.attendance_day)."""
    from . import rules
    return rules.attendance_day(now)


def attended(c):
    return c.setdefault("attended", [])


def week_days(c, day):
    """Sunday-based weekday indexes of the days attended in the Sunday-to-Saturday week of `day`."""
    start = day - datetime.timedelta(days=(day.weekday() + 1) % 7)
    dates = {datetime.date.fromisoformat(d) for d in attended(c)}
    return [i for i in range(7) if start + datetime.timedelta(days=i) in dates]


def month_days(c, day):
    return sorted(int(d[8:]) for d in attended(c) if d[:7] == day.isoformat()[:7])


def makeups(c, day):
    """The make-ups bought in `day`'s month (the calendar's "This Month's Replenishment Count", header +2)."""
    return c.get("diary_makeups", {}).get(day.isoformat()[:7], 0)


def makeup_price(done, n):
    """The Cubic for n more make-up days after `done` this month, as the calendar sums it (0x1405beec0): the k-th day
    item_currency Diary at index min(done + k, the last index) (20, 40, 70, 120, 180, 250, 350, 460, 580)."""
    rows = sorted((r for r in tables.load("item_currency") if r["ItemCurrencyType"] == "Diary"),
                  key=lambda r: int(r["Index"]))
    return sum(int(rows[min(done + k, len(rows) - 1)]["Cubic_Count"]) for k in range(n))


def week_row(day):
    """The Attendance_Week row of `day`'s week: row = ISO week (52 rows; inferred)."""
    rows = tables.sections("event_diary")["Attendance_Week"]
    return rows[(day.isocalendar().week - 1) % len(rows)]


def send_diary(s, day=None):
    day = day or today()
    c = s.data["char"]
    week, month = week_days(c, day), month_days(c, day)
    head = bytearray(HEADER)
    head[1] = int(week_row(day)["Week_Reward"])   # the calendar's weekly reward set (0x10c5's field, Flash
    head[2] = makeups(c, day)                      # ChangeWeekRewardInfo; 0 matched no row); the month's make-ups
    head[3] = ACCRUE_GROUP                         # (diary +0x22, what the calendar prices the next ones from)
    struct.pack_into("<H", head, 6, len(month))
    s.send(Writer(S2C_DIARY).raw(bytes(head)).u8(len(week)).raw(bytes(week)).u8(len(month)).raw(bytes(month)))


def _group_items(group):
    """(item code, count) of an EventDiary_Reward group, or None when the group or its item is not in the tables."""
    row = next((r for r in tables.sections("event_diary")["EventDiary_Reward"] if r["DiaryGroupIDX"] == str(group)),
               None)
    if row is None or items.row(row["ItemCode"]) is None:
        log.warning("attendance reward group %s: %s, not given", group,
                    "no EventDiary_Reward row" if row is None else f"no item table row for {row['ItemCode']}")
        return None
    return int(row["ItemCode"]), int(row["ItemCount"])


def rewards(c, day):
    """Reward groups earned by attending `day` (already recorded)."""
    wr = week_row(day)
    groups = [wr[f"ItemReward_{WEEKDAYS[(day.weekday() + 1) % 7]}"]]
    if len(week_days(c, day)) == 7:
        groups.append(wr["ItemReward_All"])
    count = len(month_days(c, day))
    for r in tables.sections("event_diary")["Attendance_Accrue"]:
        if r["Attendance_GroupNum"] == str(ACCRUE_GROUP) and r["AttendanceCount"] == str(count):
            groups += [r[f"ItemReward{i}"] for i in (1, 2, 3) if r[f"ItemReward{i}"].isdigit()]
    return groups


def make(role, state):
    @role.on(C2S_ATTEND)
    def attend(s, pkt):
        b = pkt.take(4)
        day_no, year, month = b[0], struct.unpack_from("<H", b, 1)[0], b[3]
        day = today()
        c = s.data["char"]
        if (year, month, day_no) != (day.year, day.month, day.day) or day.isoformat() in attended(c):
            log.info("attendance for %04d-%02d-%02d refused (today %s, attended %s)", year, month, day_no, day,
                        day.isoformat() in attended(c))
            s.send(Writer(S2C_ATTEND).u16(RESULT_REFRESH))
            return
        attended(c).append(day.isoformat())
        got = [g for g in (_group_items(x) for x in rewards(c, day)) if g]
        state.save()
        log.info("attendance %s: rewards %s", day, got)
        block = bytearray(REPLY_BLOCK)
        struct.pack_into("<H", block, 0, len(month_days(c, day)))
        block[3], block[4] = day.day, ACCRUE_GROUP
        w = Writer(S2C_ATTEND).u16(0).raw(bytes(block)).u8(len(got))
        for code, count in got:
            w.raw(obf.u32(code)).raw(bytes([obf.via_t1(count >> 8), obf.via_t2(count)]))
        s.send(w)
        from . import world
        for code, count in got:
            world.add_item(s, state, code, count)

    @role.on(C2S_MAKEUP)
    def makeup(s, pkt):
        """Make-up days for Cubic (rules census ECONOMY L9): past, unattended days of this month, priced as the calendar
        priced them; each day's rewards (its weekday's, a completed week's, the month's count's) go by mail, as the
        client's closing text says (71011)."""
        from . import mail, world
        b = pkt.rest()
        n = b[0] if b else 0
        days = []
        for k in range(n):
            if len(b) < 1 + 4 * (k + 1):
                break
            d, year, month = b[1 + 4 * k], struct.unpack_from("<H", b, 2 + 4 * k)[0], b[4 + 4 * k]
            try:
                days.append(datetime.date(year, month, d))
            except ValueError:
                days = []
                break
        now, c = today(), s.data["char"]
        ok = (days and len(days) == n and len(set(days)) == n
              and all(d.year == now.year and d.month == now.month and d < now and d.isoformat() not in attended(c)
                      for d in days))
        if not ok:
            log.info("make-up of %s refused (today %s)", [d.isoformat() for d in days], now)
            s.send(Writer(S2C_MAKEUP).u16(RESULT_REFRESH))
            return
        price = makeup_price(makeups(c, now), n)
        if not world.spend_cubic(s, state, price):
            s.send(Writer(S2C_MAKEUP).u16(CUBIC_SHORT))
            return
        c.setdefault("diary_makeups", {})[now.isoformat()[:7]] = makeups(c, now) + n
        for d in sorted(days):
            attended(c).append(d.isoformat())
            got = [g for g in (_group_items(x) for x in rewards(c, d)) if g]
            mail.deliver(s, state, c, "Attendance Check", f"The reward of {d.isoformat()}.", grant=got)
        state.save()
        log.info("make-up of %s for %d Cubic", [d.isoformat() for d in days], price)
        w = Writer(S2C_MAKEUP).u16(0).u8(ACCRUE_GROUP).u16(len(month_days(c, now))).u8(makeups(c, now)).u8(n)
        for d in days:
            w.u8(d.day).u8(d.month)
        s.send(w)

"""Requests that need another player (planning/todo/CONTRACT-COMPLETE-PLAN.md family 2). Built here: letters, the
player mail of CommonSubMail (scene 0x1e, the POST NPC), between the characters this server holds: the save's two
(Aldric and qwe123) are one account's, and the original's codes forbid only a letter to oneself (0x417; the mail error
table 0x140dfe830 has no "same account" code, where the block list has one, 0x4c06). Everything else of the family
(friends, block list, trade, whisper, player info, report, by-name requests, the town relays) keeps the original's own
"nobody there" answer in world.EMPTY_REPLIES: planning/agents/reports/2026-11-05_contract-social.md.

A letter is {id, from, from_id, to, to_id, title, body, sent (Unix s), read, gold, gold_taken, pay (the fee is the
recipient's), fee_paid, items: [the bag record without slot and serial, count, taken] (five at most)}: the recipient
keeps it in c["letters"], the sender a copy in c["letters_sent"] (the Sent tab's row, which shows the recipient's
read / taken states), ids from state.db["next_letter_id"] (an i32 on the wire, counted from FIRST_ID). Both go
28 days after posting, as system mail does (mail.KEEP_DAYS; the client counts the days of every list the same way).

The fee (MailFeePerc 0.05, the client's settings +0x3c8; 0x140dfe4e0 / 0x140dfe600, single precision, truncated):
max(1, gold x rate) when gold is attached, plus per item count x max(1, SellPrice x rate) (the item row's +4 is
SellPrice: the loader 0x141838ac7 -> 0x141839332). A letter of text alone is free. The sender pays the gold and the
fee (0x140df8590 checks gold + fee against the bag's gold, text 0x1b94); with "at the expense of the recipient" (the
request's flag; text 7108 calls it C.O.D.) the sender pays the gold only and the recipient the fee, once, at the
first thing taken (the client asks 0x13c8 and marks the list node +0xa2: 0x140e05cce, 0x140e05e36).
An item goes by post only as the write window lets it (0x140df73d2): not bound (the record's +6, text 0x1c33), its
row Tradable (row +0x7c, text 0x1c34). 30 letters a day (text 0x1bc6 "You can send up to 30 mails per a day.").

  C2S 0x5240 (0x140ef9a70; with 0x5251 on opening the Received tab): u8 page (8 a page).
  S2C 0x5241 (0x140e01100): u8 page, u16 total; total != 0 -> u8 n, n * (16 bytes: obool read, u8 minute, u8 day,
      u8 hour, i32 id, u16 year, u8 month, u8 gold state 0 none / 1 taken / 2 pending, obool fee paid (node +0xa2),
      obool the recipient pays (+0xa1), u8 item state, obool returned (+0xac: "[Return]" before the title, textui
      54113; never set here); cstr sender, cstr title), reader 0x140e08d90; newest first. Under 3 bytes crashes.
  C2S 0x5242 (0x140ef9c10): u8 tab (0 Received, 1 Sent), u32 id.   S2C 0x5243 (0x140e02b40, only while the window is
      open): i16; 0 -> cstr body, coded u40 gold, u8 n, n * (the bag's item record, items.record, its slot field the
      read window's slot 0..4; obool taken: 0x140e08890); the client then marks it read and asks 0x524d. Any other
      code: text 0xce89 "You have failed to check the mail.".
  C2S 0x5244 (0x140dfed40, after the fee box 0x13c3): cstr to, cstr title, cstr body, 6 bytes (coded bool "the
      recipient pays", coded u40 gold), u8 n, n * 12 (coded u16 bag slot, coded u16 count, coded u64 serial).
  S2C 0x5245 (0x140e029a0): i16; 0 -> "You have successfully sent the mail!" (0xce87), the write page cleared; the
      bag resend takes the gold and the items. Under 2 bytes crashes.
  C2S 0x5246 (0x140df8a20): u8 tab, u8 n, n * u32 id.   S2C 0x5247 (0x140e03b00): i16; 0 -> "You have deleted the
      mail." and the list again.
  C2S 0x5248 (0x140efa0f0): u32 id.   S2C 0x5249 (0x140e05d20): i16; 0 -> the read window's gold cleared (the client
      changes no gold itself: the bag resend 0x1656 carries the new total).
  C2S 0x524a (0x140ef9d70): u32 id, coded u16 bag slot, u8 item 0..4.   S2C 0x524b (0x140e05aa0): i16; 0 -> the gain
      notice and the slot cleared (the bag resend 0x1656 puts the item in the bag).
  C2S 0x524d (0x140efa1c0, every town entry): no body.   S2C 0x524e (0x140e05f80): u8, non-zero lights the HUD icon.
  C2S 0x524f (0x140ef9b40): u8 page.   S2C 0x5250 (0x140e01d10): u8 page, u16 total; total != 0 -> u8 n, n * (14
      bytes: u8 hour, obool read by the recipient, u8 minute, u16 year, obool the recipient pays, u8 gold state,
      u8 item state, u8 month, u8 day, i32 id; cstr recipient, cstr title), reader 0x140e08c30.
  S2C 0x524c (0x140e05e90, no body) "You've got mail.": never sent, a letter's recipient is not logged in.
System mail's "receive all" (mail.py) carries letters too, so make() extends its two handlers, and must run after
mail.make: 0x525e's selection (u8 n, n * u64 system id, u8 m, m * u32 letter id) is answered in 0x525f by the
letters' part as well (u8 k, k * (coded u40 gold, i32 id, u8 m, m * (item record, obool)): 0x140e05fe0 sums the fee
from it and stops unless the entries follow the list's order); 0x5260's entry of a letter is (u32 id, u64 0) (builder
0x140e001c0), its 0x5261 i16, u8 1, u32 id, u64 0.
Codes (CommonSubMail::ShowErrorMSG 0x140dfe830; the texts as the English client's table textsystem_eng words them,
the mas csv's wording after the slash): 0x406 -> 7076 "The player is not valid." / "This player is invalid.", 0x417
-> 7097 "Cannot send the mail to yourself.", 0x3c01 -> 7060 "Not enough Gold.", 0x3c03 -> 52868 "Cannot receive the
item because the inventory is full.", 0x3c05 -> 52870 "You've already received the item.", 0x3c06 -> 7219 "Cannot
attach the bound item to the mail.", 0x3c07 -> 7220 "Cannot attach the non-tradable item to the mail.", 0x3c0a ->
7110 the 30 a day, 0x642a -> 7268 "Cannot perform the action now. Please try again later.". 0x3c09 -> 7109 "Cannot
send the mail. The recipient's mailbox is full." is never sent: the box's size is in no table.

0x5340 (0x140ef97d0: cstr name, u8 kind 0 friend / 1 block) -> 0x5341 (0x140dec2d0, a copied i16): add_by_name gives
the original's refusal for the name: a block of a character of the same account 0x4c06 -> text 5048 "Character in
your account cannot be added on the blacklist."; one's own name 0x417 (the client refuses it first); any other name
0x406 -> text 7227 "The player doesn't exist or is offline." (mapper 0x140deda30): a friend must accept through the
push 0x5348, and no one else is logged in. 0x5349 (the answer to that push) is ignored: 0x534a is the asker's
notice, not its reply."""
import struct
import time
from copy import deepcopy

from . import items, mail, obf, rules, serials, settings
from .net import journal, log
from .packet import OBOOL_FALSE, OBOOL_TRUE, Reader, Writer

C2S_LIST, S2C_LIST = 0x5240, 0x5241
C2S_READ, S2C_READ = 0x5242, 0x5243
C2S_SEND, S2C_SEND = 0x5244, 0x5245
C2S_DELETE, S2C_DELETE = 0x5246, 0x5247
C2S_TAKE_GOLD, S2C_TAKE_GOLD = 0x5248, 0x5249
C2S_TAKE_ITEM, S2C_TAKE_ITEM = 0x524a, 0x524b
S2C_NEW = 0x524c
C2S_FLAG, S2C_FLAG = 0x524d, 0x524e
C2S_SENT, S2C_SENT = 0x524f, 0x5250
C2S_ADD, S2C_ADD = 0x5340, 0x5341
C2S_FRIEND_ANSWER = 0x5349
KIND_BLOCK = 1
OWN_ACCOUNT = 0x4c06
NOBODY, SELF, NO_GOLD = 0x406, 0x417, 0x3c01
BOUND, UNTRADABLE, DAY_FULL = 0x3c06, 0x3c07, 0x3c0a
UNREADABLE = 1                  # 0x5243: any non-zero code is text 0xce89
TAB_SENT = 1
A_DAY = 30                      # text 0x1bc6 (above)
FIRST_ID = 0x40000000           # letter ids start above any system mail id (mail.py counts from 1 a character): the
                                # Received list holds both kinds, and the client looks a mail up by id alone (the
                                # fee-paid flag 0x140dfe4a0, the read mark in 0x140e02b40)
BOXES = {0: "letters", TAB_SENT: "letters_sent"}


def obool(v):
    return OBOOL_TRUE if v else OBOOL_FALSE


def _f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


def fee_part(value):
    """max(1, value x MailFeePerc), as the client rounds it (0x140dfe600: int -> float, mulss, truncated)."""
    return max(1, int(_f32(_f32(value) * _f32(settings.get("MailFeePerc")))))


def fee(gold, attached):
    """What posting (or, with "the recipient pays", receiving) this gold and these items costs."""
    return (fee_part(gold) if gold > 0 else 0) + sum(i["count"] * fee_part(items.sell_price(i["code"]))
                                                     for i in attached)


def due(m):
    """The fee the recipient still owes on letter m: what is left in it, as the read window sums it (0x140e02b40)."""
    if not m["pay"] or m["fee_paid"]:
        return 0
    return fee(0 if m["gold_taken"] else m["gold"], [i for i in m["items"] if not i["taken"]])


def find(c, box, mid):
    return next((m for m in c.get(box, []) if m["id"] == mid), None)


def characters(state):
    return [ch for a in state.db["accounts"].values() for ch in a["characters"]]


def both(state, m):
    """Letter m and the sender's copy of it (the Sent tab's row), while the sender keeps one."""
    sender = next((ch for ch in characters(state) if ch["id"] == m["from_id"]), None)
    copy = find(sender, "letters_sent", m["id"]) if sender else None
    return [m] + ([copy] if copy is not None and copy is not m else [])


def expire(c, now=None):
    """Delete character c's letters and sent copies older than mail.KEEP_DAYS (journaled). Returns the ids deleted."""
    now = time.time() if now is None else now
    out = []
    for box in BOXES.values():
        gone = [m for m in c.get(box, []) if now - m["sent"] > mail.KEEP_DAYS * 86400]
        for m in gone:
            c[box].remove(m)
            journal("mail", ev="expired", box=box, id=m["id"], title=m["title"], sent=m["sent"],
                    gold=0 if m["gold_taken"] else m["gold"],
                    items=[[i["code"], i["count"]] for i in m["items"] if not i["taken"]])
        out += [m["id"] for m in gone]
    if out:
        log.info("letters of %s expired: %s", c.get("name"), out)
    return out


def entry(m):
    gold, item = mail.states(m)
    t = time.localtime(m["sent"])
    return (bytes([obool(m["read"]), t.tm_min, t.tm_mday, t.tm_hour]) + struct.pack("<iH", m["id"], t.tm_year)
            + bytes([t.tm_mon, gold, obool(m["fee_paid"]), obool(m["pay"]), item, OBOOL_FALSE])
            + m["from"].encode("latin-1", "replace") + b"\0" + m["title"].encode("latin-1", "replace") + b"\0")


def sent_entry(m):
    gold, item = mail.states(m)
    t = time.localtime(m["sent"])
    return (bytes([t.tm_hour, obool(m["read"]), t.tm_min]) + struct.pack("<H", t.tm_year)
            + bytes([obool(m["pay"]), gold, item, t.tm_mon, t.tm_mday]) + struct.pack("<i", m["id"])
            + m["to"].encode("latin-1", "replace") + b"\0" + m["title"].encode("latin-1", "replace") + b"\0")


def item_bytes(k, i):
    """Item i of a letter for the read window's slot k: the bag's record, then obool taken."""
    return items.record(i["code"], k, i.get("serial", 0), i["count"], items.durability(i),
                        bound=i.get("bound", False), enchant=i.get("enchant", 0), sockets=items.sockets(i),
                        expiry=items.seconds_left(i), options=i.get("options", ())) + bytes([obool(i["taken"])])


def page_packet(proto, page, letters, row):
    letters = sorted(letters, key=lambda m: (-m["sent"], -m["id"]))
    w = Writer(proto).u8(page).u16(len(letters))
    if letters:
        shown = letters[page * mail.PAGE:page * mail.PAGE + mail.PAGE]
        w.u8(len(shown))
        for m in shown:
            w.raw(row(m))
    return w


def room(c, world, inst):
    """How many of item instance inst character c's bag can take: on its own stacks, then in free slots."""
    cap = items.max_stack(inst["code"])
    lo, hi = world.bag_range(c, inst["code"])
    bag = c.get("bag", [])
    return (sum(cap - i["count"] for i in bag if i["count"] < cap and items.can_stack(i, inst))
            + (hi - lo - len({i["slot"] for i in bag if lo <= i["slot"] < hi})) * cap)


def put_in_bag(c, world, inst, prefer_slot=None):
    """Move item instance inst (a bag record without slot and serial) into character c's bag as it is (enchant,
    options, sockets, wear, expiry): onto stacks of the same, then into prefer_slot or the first free slot of its
    range, under new serials of c. False, with nothing changed, when it does not all fit."""
    count = inst["count"]
    if room(c, world, inst) < count:
        return False
    cap = items.max_stack(inst["code"])
    bag = c.setdefault("bag", [])
    for i in bag:
        if count and i["count"] < cap and items.can_stack(i, inst):
            n = min(count, cap - i["count"])
            i["count"] += n
            count -= n
    lo, hi = world.bag_range(c, inst["code"])
    used = {i["slot"] for i in bag}
    first = [prefer_slot] if prefer_slot is not None and lo <= prefer_slot < hi and prefer_slot not in used else []
    free = iter(first + [k for k in range(lo, hi) if k not in used and k not in first])
    while count:
        n = min(count, cap)
        bag.append({**deepcopy({k: v for k, v in inst.items() if k not in ("taken", "serial")}), "slot": next(free),
                    "count": n, "serial": serials.allocate(c)})
        count -= n
    return True


def make(role, state):
    from . import quest, world

    def take_items(s, c, m, only=None):
        """Give letter m's untaken items (or item `only` = (index, bag slot)); stops at the first that does not fit.
        Returns 0 or a code."""
        for k, it in enumerate(m["items"]):
            if it["taken"] or (only is not None and k != only[0]):
                continue
            if not put_in_bag(c, world, it, only[1] if only else None):
                return mail.BAG_FULL
            journal("mail", ev="taken", box="letters", id=m["id"], title=m["title"], items=[[it["code"], it["count"]]])
            journal("item", ev="gain", code=it["code"], name=items.name(it["code"]), n=it["count"], mailed=0,
                    why=world.cause(f"letter {m['id']} from {m['from']}"))
            for x in both(state, m):
                x["items"][k]["taken"] = True
            if "expires" in it:
                world.arm_expiry(s, state)
            quest.on_item(s, state, it["code"], it["count"])
        return 0

    def pay_fee(c, m):
        """Take the fee of a "the recipient pays" letter at its first take; False when the gold is short."""
        owed = due(m)
        if c.get("gold", 0) < owed:
            return False
        if owed:
            world.change_gold(c, -owed, why=f"letter {m['id']} fee")
        for x in both(state, m):
            x["fee_paid"] = True
        return True

    def take_gold_of(s, c, m):
        """A letter's gold into the bag's: moved, not gained (world.add_gold would count it for the GoldGain titles),
        so the bag resend carries the new total."""
        for x in both(state, m):
            x["gold_taken"] = True
        journal("mail", ev="taken", box="letters", id=m["id"], title=m["title"], gold=m["gold"])
        world.change_gold(c, m["gold"], why=f"letter {m['id']} from {m['from']}")
        state.save()
        world.send_cargo(s)

    @role.on(C2S_LIST)
    def letter_list(s, pkt):
        c = s.data["char"]
        page = (pkt.rest() or b"\0")[0]                 # a body without its page byte: page 0, never a raise (the
                                                        # session would close; the constant before read nothing)
        if expire(c):
            state.save()
        s.send(page_packet(S2C_LIST, page, c.get("letters", []), entry))

    @role.on(C2S_SENT)
    def sent_list(s, pkt):
        c = s.data["char"]
        page = (pkt.rest() or b"\0")[0]
        if expire(c):
            state.save()
        s.send(page_packet(S2C_SENT, page, c.get("letters_sent", []), sent_entry))

    @role.on(C2S_FLAG)
    def flag(s, pkt):
        c = s.data["char"]
        if expire(c):
            state.save()
        s.send(Writer(S2C_FLAG).u8(any(not m["read"] for m in c.get("letters", []))))

    @role.on(C2S_READ)
    def read(s, pkt):
        b = pkt.rest()
        tab, mid = (b[0], struct.unpack_from("<I", b, 1)[0]) if len(b) >= 5 else (0, 0)
        m = find(s.data["char"], BOXES.get(tab, "letters"), mid)
        if m is None:
            s.send(Writer(S2C_READ).u16(UNREADABLE))
            return
        if tab != TAB_SENT and not m["read"]:
            for x in both(state, m):
                x["read"] = True
            journal("mail", ev="read", box="letters", id=m["id"], title=m["title"])
            state.save()
        w = Writer(S2C_READ).u16(0).cstr(m["body"]).raw(obf.u40(0 if m["gold_taken"] else m["gold"]))
        w.u8(len(m["items"]))
        for k, i in enumerate(m["items"]):
            w.raw(item_bytes(k, i))
        s.send(w)

    @role.on(C2S_SEND)
    def post(s, pkt):
        c = s.data["char"]
        try:
            to, title, body = pkt.cstr(), pkt.cstr(), pkt.cstr()
            head = pkt.take(6)
            wanted = [pkt.take(12) for _ in range(pkt.u8())]
        except ValueError:
            log.warning("letter not understood: %s", pkt.frame.hex())
            s.send(Writer(S2C_SEND).u16(mail.MISSING))
            return
        pay, gold = bool(obf.T1[head[0]] & 1), obf.dec_u40(head[1:6])
        target = next((ch for ch in characters(state) if ch["name"] == to), None)
        day = c.get("letters_day", [None, 0])
        code, attached, held = 0, [], {}
        if target is None:
            code = NOBODY
        elif target is c:
            code = SELF
        elif not title or not body or len(wanted) > mail.SLOTS:     # the write window refuses these itself
            code = mail.MISSING
        elif day[0] == rules.game_day() and day[1] >= A_DAY:
            code = DAY_FULL
        for e in wanted if not code else ():
            slot, n, serial = obf.dec_u16(e[0:2]), obf.dec_u16(e[2:4]), obf.dec_u64(e[4:12])
            it = world.bag_item(c, serial)
            held[serial] = held.get(serial, 0) + n
            if it is None or it["slot"] != slot or n < 1 or held[serial] > it["count"]:
                code = mail.MISSING
            elif it.get("bound"):
                code = BOUND
            elif (items.row(it["code"]) or {}).get("Tradable") == "False":
                code = UNTRADABLE
            if code:
                break
            attached.append({**deepcopy({k: v for k, v in it.items() if k != "slot"}), "count": n, "taken": False})
        cost = gold + (0 if pay else fee(gold, attached))
        if not code and c.get("gold", 0) < cost:
            code = NO_GOLD
        if code:
            log.info("letter of %s to %r refused: %#x", c.get("name"), to, code)
            s.send(Writer(S2C_SEND).u16(code))
            return
        for i in attached:
            world.take_serial(c, i["serial"], i["count"])
            journal("item", ev="spend", code=i["code"], name=items.name(i["code"]), n=i["count"],
                    why=world.cause(f"letter to {to}"))
        world.change_gold(c, -cost, why=f"letter to {to}")
        mid = state.db["next_letter_id"] = state.db.get("next_letter_id", FIRST_ID) + 1
        m = {"id": mid, "from": c["name"], "from_id": c["id"], "to": target["name"], "to_id": target["id"],
             "title": title, "body": body, "sent": int(time.time()), "read": False, "gold": gold,
             "gold_taken": False, "pay": pay and bool(gold or attached), "fee_paid": False, "items": attached}
        target.setdefault("letters", []).append(m)
        c.setdefault("letters_sent", []).append(deepcopy(m))
        c["letters_day"] = [rules.game_day(), day[1] + 1 if day[0] == rules.game_day() else 1]
        journal("mail", ev="posted", box="letters", id=mid, to=target["name"], title=title, gold=gold, fee=cost - gold,
                pay=m["pay"], items=[[i["code"], i["count"]] for i in attached])
        state.save()
        s.send(Writer(S2C_SEND).u16(0))
        world.send_cargo(s)
        log.info("letter %d of %s to %s: %r, gold %d, fee %d, items %s", mid, c["name"], target["name"], title, gold,
                 cost - gold, [(i["code"], i["count"]) for i in attached])

    @role.on(C2S_DELETE)
    def delete(s, pkt):
        b = pkt.rest()
        tab, n = (b[0], b[1]) if len(b) >= 2 else (0, 0)
        gone = {struct.unpack_from("<I", b, 2 + 4 * i)[0] for i in range(min(n, (len(b) - 2) // 4))}
        c, box = s.data["char"], BOXES.get(tab, "letters")
        dropped = [m for m in c.get(box, []) if m["id"] in gone]
        for m in dropped:
            c[box].remove(m)
            journal("mail", ev="deleted", box=box, id=m["id"], title=m["title"],
                    gold=0 if m["gold_taken"] else m["gold"],
                    items=[[i["code"], i["count"]] for i in m["items"] if not i["taken"]])
        if dropped:                                     # nothing named, nothing saved (a short or empty request)
            state.save()
        s.send(Writer(S2C_DELETE).u16(0))

    @role.on(C2S_TAKE_GOLD)
    def take_gold(s, pkt):
        c = s.data["char"]
        b = pkt.rest()
        m = find(c, "letters", struct.unpack_from("<I", b)[0]) if len(b) >= 4 else None    # short: no such letter
        if m is None or not m["gold"] or m["gold_taken"]:
            s.send(Writer(S2C_TAKE_GOLD).u16(mail.MISSING if m is None else mail.TAKEN))
            return
        if not pay_fee(c, m):
            s.send(Writer(S2C_TAKE_GOLD).u16(NO_GOLD))
            return
        take_gold_of(s, c, m)
        s.send(Writer(S2C_TAKE_GOLD).u16(0))

    @role.on(C2S_TAKE_ITEM)
    def take_item(s, pkt):
        b = pkt.rest()
        if len(b) < 7:
            s.send(Writer(S2C_TAKE_ITEM).u16(mail.MISSING))      # answered as the constant before: no such letter
            return
        mid, slot, k = struct.unpack_from("<I", b)[0], obf.dec_u16(b[4:6]), b[6]
        c = s.data["char"]
        m = find(c, "letters", mid)
        if m is None or k >= len(m["items"]) or m["items"][k]["taken"]:
            s.send(Writer(S2C_TAKE_ITEM).u16(mail.MISSING if m is None else mail.TAKEN))
            return
        if room(c, world, m["items"][k]) < m["items"][k]["count"]:
            s.send(Writer(S2C_TAKE_ITEM).u16(mail.BAG_FULL))
            return
        if not pay_fee(c, m):
            s.send(Writer(S2C_TAKE_ITEM).u16(NO_GOLD))
            return
        result = take_items(s, c, m, (k, slot))
        state.save()
        world.send_cargo(s)
        s.send(Writer(S2C_TAKE_ITEM).u16(result))

    @role.on(C2S_ADD)
    def add_by_name(s, pkt):
        try:
            name, kind = pkt.cstr(), pkt.u8()
        except ValueError:
            name, kind = "", 0
        c = s.data["char"]
        mine = any(ch["name"] == name for ch in s.data["account"]["characters"])
        code = SELF if name == c.get("name") else OWN_ACCOUNT if mine and kind == KIND_BLOCK else NOBODY
        s.send(Writer(S2C_ADD).u16(code))

    role.ignore(C2S_FRIEND_ANSWER)

    # mail.py's "receive all" for a selection that holds letters (above); its handlers stay the system mail's
    system_check, system_receive = role.handlers.get(mail.C2S_CHECK), role.handlers.get(mail.C2S_RECEIVE)
    if system_receive is None:
        log.warning("social.make ran before mail.make: a letter's 'receive all' stays the system mail's refusal")
        return
    if getattr(system_receive, "letters", False):
        return                                          # made twice: the handlers are extended already

    @role.on(mail.C2S_CHECK)
    def check(s, pkt):
        b = pkt.rest()
        n = min(b[0], (len(b) - 1) // 8) if b else 0
        at = 1 + 8 * n
        k = min(b[at], (len(b) - at - 1) // 4) if len(b) > at else 0
        ids = [struct.unpack_from("<I", b, at + 1 + 4 * i)[0] for i in range(k)]
        if not ids:
            system_check(s, pkt)
            return
        c = s.data["char"]
        w = Writer(mail.S2C_CHECK).u16(0).u8(n)
        for mid in struct.unpack_from(f"<{n}Q", b, 1):
            sm = mail.find(c, mid)
            w.u64(mid).raw(obf.u40(sm["gold"] if sm and not sm["gold_taken"] else 0)).u8(0)
        w.u8(len(ids))
        for mid in ids:
            m = find(c, "letters", mid) or {"gold": 0, "gold_taken": True, "items": []}
            left = [(k, i) for k, i in enumerate(m["items"]) if not i["taken"]]
            w.raw(obf.u40(0 if m["gold_taken"] else m["gold"])).raw(struct.pack("<I", mid)).u8(len(left))   # the id
            # as it came (an i32 writer raised on a junk id above 0x7fffffff, which would close the session)
            for k, i in left:
                w.raw(item_bytes(k, i))
        s.send(w)
    check.letters = True

    @role.on(mail.C2S_RECEIVE)
    def receive(s, pkt):
        b = pkt.rest()
        n = b[0] if b else 0
        entries = [b[1 + 12 * i:13 + 12 * i] for i in range(min(n, (len(b) - 1) // 12))]
        system = [e for e in entries if struct.unpack_from("<Q", e, 4)[0]]
        if system:
            body = bytes([len(system)]) + b"".join(system)
            system_receive(s, Reader(struct.pack("<HBH", 5 + len(body), 0, mail.C2S_RECEIVE) + body))
        c = s.data["char"]
        for e in entries:
            mid, sid = struct.unpack_from("<IQ", e)
            if sid:
                continue
            m = find(c, "letters", mid)
            if m is None:
                s.send(Writer(mail.S2C_RECEIVE).u16(mail.MISSING))
                continue
            gold = m["gold"] and not m["gold_taken"]
            first = next((i for i in m["items"] if not i["taken"]), None)
            if not gold and first is not None and room(c, world, first) < first["count"]:
                s.send(Writer(mail.S2C_RECEIVE).u16(mail.BAG_FULL))     # nothing would be taken: no fee either
                continue
            if not pay_fee(c, m):
                s.send(Writer(mail.S2C_RECEIVE).u16(NO_GOLD))
                continue
            if gold:
                take_gold_of(s, c, m)
            result = take_items(s, c, m)
            state.save()
            world.send_cargo(s)
            s.send(Writer(mail.S2C_RECEIVE).u16(result) if result else
                   Writer(mail.S2C_RECEIVE).u16(0).u8(1).u32(mid).u64(0))
    receive.letters = True

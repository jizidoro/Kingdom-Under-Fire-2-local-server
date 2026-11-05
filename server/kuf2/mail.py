"""System mail (CommonSubMail, scene 0x1e; the POST NPC menu opens it; player mail and packages are refused in
world.EMPTY_REPLIES). The server delivers mail with gold and up to five items (deliver()); the character keeps
c["mail"] = [{id, title, body, sent (Unix s), read, gold, gold_taken, items: [{code, count, taken}]}] and
c["next_mail_id"] (ids stay small: the client passes them through a double). A mail is deleted 28 days after it was
sent, what the client tells the player (textui 7509 "After 28 days, which is the expiration date, the mail will be
automatically deleted."; rules census N1): expire() at the list and the new-mail check. Spec: specs/pvp_mail_social.md
G16.

  C2S 0x5251 (0x140efa210, with 0x5240 on opening the Received tab): u8 page (8 mails a page).
  S2C 0x5252 (0x140e03ce0): u8 page, u16 total; total != 0 -> u8 n, n * entry (reader 0x140e08ef0, 21 bytes + cstr:
      u8 gold state 0 none / 1 taken / 2 pending, u8 minute, u16 year, u8 day, u8 item state, u8 hour, obool read,
      u8 month, u32 title text id (0 = the cstr), u64 id, cstr title); newest first.
  C2S 0x5253 (0x140efa2e0): u64 id.   S2C 0x5254 Process_SystemMailDetailInfo (0x140e04a10): i16; 0 -> u32 body text
      id, cstr body, coded u40 gold, u8 n, n * item (u8 option flag, coded u32 code, coded u16 count, obool taken, the
      record's 8-byte part, u8 0, u8 0); the client then asks 0x525c.
  C2S 0x5255 take gold: u64 id -> S2C 0x5256 i16.   C2S 0x5257 take an item: u64 id, u8 slot 0..4, u16 bag slot ->
      S2C 0x5258 i16 (the bag resend puts it in the bag).   C2S 0x5259 delete: u8 n, n * u64 -> S2C 0x525a i16.
  C2S 0x525c "new mail?" -> S2C 0x525d u8 (non-zero lights the HUD icon).   S2C 0x525b (no body): "You've got mail."
  C2S 0x525e pre-check of "receive selected": u8 n, n * u64, u8 m, m * u32 -> S2C 0x525f: i16 0, u8 n, n * (u64 id,
      coded u40 gold, u8 0), u8 0 (entries in the request's order, else the client stops silently).
  C2S 0x5260 receive all: u8 n, n * (u32 player-mail id, u64 system id) -> one S2C 0x5261 per mail: i16; 0 -> u8 1,
      u32 0, u64 id (fewer replies leave the window busy).
Codes: 0x3c03 "You can not get the item because your bag is full.", 0x3c05 "Item already received.", 0x642a
"Can't proceed."."""
import struct
import time

from . import items, obf
from .net import journal, log
from .packet import OBOOL_FALSE, OBOOL_TRUE, Writer

C2S_LIST, S2C_LIST = 0x5251, 0x5252
C2S_READ, S2C_READ = 0x5253, 0x5254
C2S_TAKE_GOLD, S2C_TAKE_GOLD = 0x5255, 0x5256
C2S_TAKE_ITEM, S2C_TAKE_ITEM = 0x5257, 0x5258
C2S_DELETE, S2C_DELETE = 0x5259, 0x525a
S2C_NEW = 0x525b
C2S_FLAG, S2C_FLAG = 0x525c, 0x525d
C2S_CHECK, S2C_CHECK = 0x525e, 0x525f
C2S_RECEIVE, S2C_RECEIVE = 0x5260, 0x5261
BAG_FULL, TAKEN, MISSING = 0x3c03, 0x3c05, 0x642a
PAGE = 8
SLOTS = 5
KEEP_DAYS = 28                  # textui 7509 (above)


def expire(c, now=None):
    """Delete character c's mail older than KEEP_DAYS, attachments and all (journaled). Returns the ids deleted."""
    now = time.time() if now is None else now
    gone = [m for m in c.get("mail", []) if now - m["sent"] > KEEP_DAYS * 86400]
    for m in gone:
        c["mail"].remove(m)
        journal("mail", ev="expired", id=m["id"], title=m["title"], sent=m["sent"],
                gold=0 if m["gold_taken"] else m["gold"], items=[[i["code"], i["count"]] for i in m["items"]
                                                                 if not i["taken"]])
    if gone:
        log.info("mail of %s expired: %s", c.get("name"), [m["id"] for m in gone])
    return [m["id"] for m in gone]


def deliver(s, state, c, title, body, gold=0, grant=()):
    """Mail gold and items to character c (five items a mail; more make more mails); tells an online client."""
    grant = [(code, n) for code, n in grant if n > 0]
    chunks = [grant[i:i + SLOTS] for i in range(0, len(grant), SLOTS)] or [[]]
    for i, chunk in enumerate(chunks):
        c["next_mail_id"] = c.get("next_mail_id", 0) + 1
        c.setdefault("mail", []).append({
            "id": c["next_mail_id"], "title": title, "body": body, "sent": int(time.time()), "read": False,
            "gold": gold if i == 0 else 0, "gold_taken": False,
            "items": [{"code": code, "count": n, "taken": False} for code, n in chunk]})
        journal("mail", ev="sent", id=c["next_mail_id"], title=title, gold=gold if i == 0 else 0, items=chunk)
    state.save()
    if s is not None:
        s.send(Writer(S2C_NEW))
    log.info("mail to %s: %r, gold %d, items %s", c.get("name"), title, gold, grant)


def states(m):
    gold = 0 if not m["gold"] else 1 if m["gold_taken"] else 2
    item = 0 if not m["items"] else 1 if all(i["taken"] for i in m["items"]) else 2
    return gold, item


def entry(m):
    gold, item = states(m)
    t = time.localtime(m["sent"])
    return (bytes([gold, t.tm_min]) + struct.pack("<H", t.tm_year) + bytes([t.tm_mday, item, t.tm_hour,
            OBOOL_TRUE if m["read"] else OBOOL_FALSE, t.tm_mon]) + struct.pack("<IQ", 0, m["id"])
            + m["title"].encode("latin-1", "replace") + b"\0")


def item_bytes(i):
    return (b"\0" + obf.u32(i["code"]) + obf.u16(i["count"]) + bytes([OBOOL_TRUE if i["taken"] else OBOOL_FALSE])
            + bytes(8) + b"\0\0")


def find(c, mid):
    return next((m for m in c.get("mail", []) if m["id"] == mid), None)


def make(role, state):
    from . import world

    def take_items(s, c, m, only=None):
        """Give the mail's untaken items (or item `only`); stops at the first that does not fit. Returns 0 or a code."""
        for k, it in enumerate(m["items"]):
            if it["taken"] or (only is not None and k != only[0]):
                continue
            if not world.fits(c, [(it["code"], it["count"])]):
                return BAG_FULL
            journal("mail", ev="taken", id=m["id"], title=m["title"], items=[[it["code"], it["count"]]])
            world.add_item(s, state, it["code"], it["count"], prefer_slot=only[1] if only else None, mail=False,
                           capped=False)       # a move: its gain was counted when it was mailed
            it["taken"] = True
        return 0

    @role.on(C2S_LIST)
    def mail_list(s, pkt):
        page = pkt.u8()
        if expire(s.data["char"]):
            state.save()
        mails = sorted(s.data["char"].get("mail", []), key=lambda m: (-m["sent"], -m["id"]))
        w = Writer(S2C_LIST).u8(page).u16(len(mails))
        if mails:
            shown = mails[page * PAGE:page * PAGE + PAGE]
            w.u8(len(shown))
            for m in shown:
                w.raw(entry(m))
        s.send(w)

    @role.on(C2S_READ)
    def read(s, pkt):
        m = find(s.data["char"], pkt.u64())
        if m is None:
            s.send(Writer(S2C_READ).u16(1))
            return
        m["read"] = True
        journal("mail", ev="read", id=m["id"], title=m["title"])
        state.save()
        w = Writer(S2C_READ).u16(0).u32(0).cstr(m["body"]).raw(obf.u40(0 if m["gold_taken"] else m["gold"]))
        w.u8(len(m["items"]))
        for i in m["items"]:
            w.raw(item_bytes(i))
        s.send(w)

    @role.on(C2S_TAKE_GOLD)
    def take_gold(s, pkt):
        c = s.data["char"]
        m = find(c, pkt.u64())
        if m is None or not m["gold"] or m["gold_taken"]:
            s.send(Writer(S2C_TAKE_GOLD).u16(MISSING if m is None else TAKEN))
            return
        m["gold_taken"] = True
        journal("mail", ev="taken", id=m["id"], title=m["title"], gold=m["gold"])
        world.add_gold(s, state, m["gold"])
        s.send(Writer(S2C_TAKE_GOLD).u16(0))

    @role.on(C2S_TAKE_ITEM)
    def take_item(s, pkt):
        b = pkt.rest()
        if len(b) < 11:
            return
        mid, k, slot = struct.unpack_from("<QBH", b, 0)
        c = s.data["char"]
        m = find(c, mid)
        if m is None or k >= len(m["items"]) or m["items"][k]["taken"]:
            s.send(Writer(S2C_TAKE_ITEM).u16(MISSING if m is None else TAKEN))
            return
        result = take_items(s, c, m, (k, slot))
        state.save()
        s.send(Writer(S2C_TAKE_ITEM).u16(result))

    @role.on(C2S_DELETE)
    def delete(s, pkt):
        b = pkt.rest()
        n = b[0] if b else 0
        gone = {struct.unpack_from("<Q", b, 1 + 8 * i)[0] for i in range(min(n, (len(b) - 1) // 8))}
        c = s.data["char"]
        c["mail"] = [m for m in c.get("mail", []) if m["id"] not in gone]
        state.save()
        s.send(Writer(S2C_DELETE).u16(0))

    @role.on(C2S_FLAG)
    def flag(s, pkt):
        if expire(s.data["char"]):
            state.save()
        s.send(Writer(S2C_FLAG).u8(any(not m["read"] for m in s.data["char"].get("mail", []))))

    @role.on(C2S_CHECK)
    def check(s, pkt):
        b = pkt.rest()
        n = b[0] if b else 0
        ids = [struct.unpack_from("<Q", b, 1 + 8 * i)[0] for i in range(min(n, (len(b) - 1) // 8))]
        c = s.data["char"]
        w = Writer(S2C_CHECK).u16(0).u8(len(ids))
        for mid in ids:
            m = find(c, mid)
            w.u64(mid).raw(obf.u40(m["gold"] if m and not m["gold_taken"] else 0)).u8(0)
        s.send(w.u8(0))

    @role.on(C2S_RECEIVE)
    def receive(s, pkt):
        b = pkt.rest()
        n = b[0] if b else 0
        c = s.data["char"]
        for i in range(min(n, (len(b) - 1) // 12)):
            mid = struct.unpack_from("<Q", b, 1 + 12 * i + 4)[0]
            m = find(c, mid)
            if m is None:
                s.send(Writer(S2C_RECEIVE).u16(MISSING))
                continue
            if m["gold"] and not m["gold_taken"]:
                m["gold_taken"] = True
                journal("mail", ev="taken", id=m["id"], title=m["title"], gold=m["gold"])
                world.add_gold(s, state, m["gold"])
            result = take_items(s, c, m)
            state.save()
            s.send(Writer(S2C_RECEIVE).u16(result) if result else
                   Writer(S2C_RECEIVE).u16(0).u8(1).u32(0).u64(mid))

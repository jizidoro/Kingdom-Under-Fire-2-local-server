"""Persistent per-character identities shared by items and recruited troops."""

TROOP_UID_MAX = 0x7fffffff      # a troop uid the client's training tutorial can match (troop_uid)


def allocate(c):
    """Reserve a new u64 without renumbering anything already saved.

    Legacy item/troop allocators ORed 0x10000/0x20000 into a shared counter,
    repeating IDs when those counter bits became set. Continue above both legacy
    prefixes and every held ID (including buyback and troop gear). next_serial is
    now the low-word high-water mark, so consumed IDs stay retired after reload.
    A troop uid without the character's high word (troop_uid) counts as well.
    """
    held = [it.get("serial") for box in ("bag", "warehouse", "equip", "buyback") for it in c.get(box, [])]
    for troop in c.get("troops", []):
        held.append(troop["uid"])
        held.extend(it.get("serial") for it in troop.get("gear", []))
    low = max([0x2ffff, c.get("next_serial", 0)] +
              [uid & 0xffffffff for uid in held if uid and uid >> 32 in (0, c["id"])]) + 1
    if low > 0xffffffff:
        raise OverflowError("character item/troop serial space exhausted")
    c["next_serial"] = low
    return (c["id"] << 32) | low


def troop_uid(c):
    """A new troop's uid: allocate's low word alone, at most TROOP_UID_MAX. The client's training tutorial
    (TutorialQuestTrainTroop, 9900104) keeps the low 32 bits of the uid it finds for its troop (troop map node +0x30,
    0x14082dce3) and compares them, sign-extended, with the 64-bit uid the training window's TroopTrainingStart passes
    (0x140e3cc20 -> event 0x18, 0x14082dc48): with the character id in the high word they never match, the tutorial
    never sends its 0x554f and the quest stays open (live 2026-09-28, `!questdone 9900104`). Saved troops keep their
    uids."""
    low = allocate(c) & 0xffffffff
    if low > TROOP_UID_MAX:
        raise OverflowError("character troop uid space exhausted")
    return low

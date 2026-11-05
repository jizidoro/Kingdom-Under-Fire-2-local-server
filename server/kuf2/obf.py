"""Client field obfuscation: two inverse byte permutations.

T1 is the static table @ 0x142606fe0 (buildid 4766023); T2 = T1^-1 (runtime table *0x1434a65b0, verified
with tools/frida/tables.js). The client decodes a byte b as T1[b] or T2[b] depending on the field.
"""
T1 = bytes.fromhex("c312332ad2fd97350862b98e6efaa7490019446a66e1734ab6c00dae9315d5e2f4ee5da28817e86c2cca4d8734842b3f1c96a0a8d354b84f53e68ca49fa9069bd9cd8f36b2f8f5c832f7c17cf024dc7b2674706b0f31e34c2255802dc7995a8b4758cc67b3e7487f86107eea57dabdc29dad77bad74b9cd009df0e28f981291f1d0b39611ebe1b045f689092c50c3765e52e0a20b55927ff02c650605e6fabc9406dafbf30b4aa5295fccbf1f2eba6de8aac5163fb46b7d6bb8214d4421a18ec25d8dba39e23d1013b75697103433c4e8d1379edef7256f63d9a45fee9c4a507769821f35bb1855cb07de4642f05389189417abccf3a837811dde03e94cea116")
T2 = bytes(T1.index(i) for i in range(256))


def via_t1(v):
    """byte b such that the client's T1[b] == v"""
    return T2[v & 0xFF]


def via_t2(v):
    """byte b such that the client's T2[b] == v"""
    return T1[v & 0xFF]


def u32(v):
    """4 bytes decoded by the client as ((T2[b1]<<24)|(T1[b2]<<16)|(T2[b3]<<8)|T1[b0])
    (spot id in 0x1012 @ 0x140e79030, colours in the character entry @ 0x140e78af0)."""
    v &= 0xFFFFFFFF
    return bytes([via_t1(v), via_t2(v >> 24), via_t1(v >> 16), via_t2(v >> 8)])


def u40(v):
    """5 bytes decoded as T1[b0]<<32 | T2[b2]<<24 | T1[b3]<<16 | T2[b1]<<8 | T1[b4] (gold in 0x1656, 0x140dce7d0)."""
    v &= 0xFFFFFFFFFF
    return bytes([via_t1(v >> 32), via_t2(v >> 8), via_t2(v >> 24), via_t1(v >> 16), via_t1(v)])


def pos_xz(x, z):
    """Packed signed 20-bit x/z as read by 0x1012 (P+0x0f..0x12 and P+0x15 nibbles).
    x = (hi(T1[p15])<<16) | T1[p12]<<8 | T2[p0f];  z = (lo(T1[p15])<<16) | T1[p10]<<8 | T2[p11]
    Returns (bytes for P+0x0f..0x12, byte for P+0x15)."""
    x &= 0xFFFFF
    z &= 0xFFFFF
    p0f = via_t2(x)
    p12 = via_t1(x >> 8)
    p10 = via_t1(z >> 8)
    p11 = via_t2(z)
    p15 = via_t1(((x >> 16) << 4) | (z >> 16))
    return bytes([p0f, p10, p11, p12]), p15


def dec_pos_xz(b, p15):
    """Inverse of pos_xz: (4 packed bytes, nibble byte) -> signed (x, z)."""
    n = T1[p15]
    x = ((n >> 4) << 16) | (T1[b[3]] << 8) | T2[b[0]]
    z = ((n & 0xF) << 16) | (T1[b[1]] << 8) | T2[b[2]]
    return tuple(v - 0x100000 if v > 0x7FFFF else v for v in (x, z))


# The item-move requests' u64 (0x164e builder 0x140f007a0): request byte k carries value byte n, table-coded so the
# client's T1 ('a') or its runtime table *0x1434a65b0 = T2 ('b') maps the value byte to it.
U64_ORDER = ((6, "b"), (4, "b"), (2, "b"), (3, "a"), (0, "b"), (1, "a"), (5, "a"), (7, "a"))


def u64(v):
    """8 bytes as the client codes a u64 in the item-move requests (for tests)."""
    return bytes(T1[(v >> 8 * n) & 0xFF] if t == "a" else T2[(v >> 8 * n) & 0xFF] for n, t in U64_ORDER)


def dec_u64(b):
    """The u64 of an item-move request (see U64_ORDER)."""
    return sum((T2[b[k]] if t == "a" else T1[b[k]]) << 8 * n for k, (n, t) in enumerate(U64_ORDER))


# The login reply's times (0x1003 +0x0f / +0x17, read by 0x1405aa3d0): the value's bytes, most significant first, are
# T2[b7], T1[b0], T2[b6], T1[b1], T2[b3], T1[b2], T2[b5], T1[b4].
TIME_ORDER = ((7, 2), (0, 1), (6, 2), (1, 1), (3, 2), (2, 1), (5, 2), (4, 1))


def time64(v):
    """8 bytes the client reads as the u64 v with 0x1405aa3d0."""
    out = bytearray(8)
    for n, (pos, table) in enumerate(TIME_ORDER):
        byte = (v >> 8 * (7 - n)) & 0xFF
        out[pos] = via_t2(byte) if table == 2 else via_t1(byte)
    return bytes(out)


def dec_time64(b):
    """What 0x1405aa3d0 reads from these 8 bytes."""
    v = 0
    for pos, table in TIME_ORDER:
        v = (v << 8) | (T2[b[pos]] if table == 2 else T1[b[pos]])
    return v


def u16(v):
    """2 bytes the client reads as (T1[b0] << 8) | T2[b1] (container results 0x1668, the requests' coded u16s)."""
    return bytes([via_t1(v >> 8), via_t2(v)])


def dec_u16(b):
    """A coded u16 as the client writes it: T2-coded high byte, then T1-coded low byte."""
    return (T1[b[0]] << 8) | T2[b[1]]


def dec_u40(b):
    """inverse of u40(): a coded 5-byte amount as the client writes it (warehouse gold 0x165e, builder 0x140e46350)"""
    return (T1[b[0]] << 32) | (T2[b[2]] << 24) | (T1[b[3]] << 16) | (T2[b[1]] << 8) | T1[b[4]]


def dec_u32(b):
    """inverse of u32(): what the client reads from these 4 bytes (it also encodes ids it sends this way)"""
    return (T2[b[1]] << 24) | (T1[b[2]] << 16) | (T2[b[3]] << 8) | T1[b[0]]

"""KUF2 packet cipher (client Crypt.cpp, dump 0x14158bd70 encrypt / 0x14158be60 decrypt, buildid 4766023).

Frame: u16 LE total size | u8 check | body...  (the first HDR_LEN bytes are not encrypted).
Each direction keeps its own seed: it starts at 0x3C00 and, after every packet, becomes the
sign-extended check byte of that packet (client call 0x14158bf80 with (i8)data[2]).

Integrity report (client send path 0x14158b0d0): every 1038 packets or 58732 bytes the client sends one frame in
plain text, without the cipher and without touching the seed: size 21, check byte = digest[packets & 0xf], an id
from the runtime global 0x1434a6588 (0x4f4a in one dump; it is not fixed across runs: a 02:30 drop carried another),
16-byte digest of every frame sent since the last report from offset 3 (0x14158c020 -> 0x141e07ea0 update,
0x14158c050 -> 0x141e07f70 final). A 21-byte frame that fails the check byte is that report; the server skips it.
"""
import struct

HDR_LEN = 3
INITIAL_SEED = 0x3C00
INTEGRITY_REPORT_SIZE = 21


def integrity_report(frame) -> bool:
    """True for a frame the size of the client's plain-text integrity report (call it after the check byte failed)."""
    return len(frame) == INTEGRITY_REPORT_SIZE


def _i32(x):
    x &= 0xFFFFFFFF
    return x - (1 << 32) if x & 0x80000000 else x


def _next(seed):
    """Advance the seed and return (seed, key_byte) exactly as the client's inlined code does."""
    seed = _i32(seed * 0x41A7)
    t = _i32(((seed & 0x7FFFFF) - 0x400000) * 0xFF)
    if t < 0 and (t & 0xFFFFFFFF) != 0xC0400000:
        t = _i32(t + 0x400000)
    return seed, ((t & 0xFFFFFFFF) >> 22) & 0xFF


class Cipher:
    def __init__(self, seed=INITIAL_SEED):
        self.seed = seed

    def encrypt(self, data: bytearray) -> bytearray:
        seed = self.seed
        data[2] = seed & 0xFF
        s = sum(data[:HDR_LEN]) & 0xFF
        for i in range(HDR_LEN, len(data)):
            seed, k = _next(seed)
            s = (s + data[i]) & 0xFF
            data[i] ^= k
        seed, k = _next(seed)
        data[2] = k ^ s
        self.seed = _i32(data[2] if data[2] < 0x80 else data[2] - 0x100)
        return data

    def decrypt(self, data: bytearray) -> bytearray:
        """Decrypt in place; raises ValueError on a bad check byte (data and state are left unchanged then)."""
        seed = self.seed
        out = bytearray(data)
        check = out[2]
        out[2] = seed & 0xFF
        s = sum(out[:HDR_LEN]) & 0xFF
        for i in range(HDR_LEN, len(out)):
            seed, k = _next(seed)
            out[i] ^= k
            s = (s + out[i]) & 0xFF
        seed, k = _next(seed)
        if (check ^ s) != k:
            raise ValueError(f"bad check byte (frame of {len(data)} bytes)")
        out[2] = check
        data[:] = out
        self.seed = check if check < 0x80 else check - 0x100
        return data

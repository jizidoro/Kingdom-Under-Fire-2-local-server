"""KUF2 packet framing: u16 LE total size | u8 check | u16 LE protocol id | body.

Fixed-size reads return raw bytes at the cursor; strings are NUL-terminated (client readers
0x141583ad0 / 0x1415835b0, buildid 4766023).
"""
import struct

HEADER = 5

# Many client bools are read as BOOL_TABLE[byte] & 1 (static table @ 0x142606fe0): byte 0 -> true, byte 1 -> false.
OBOOL_TRUE, OBOOL_FALSE = 0x00, 0x01


class Reader:
    def __init__(self, frame: bytes):
        self.frame = frame
        self.proto = struct.unpack_from("<H", frame, 3)[0]
        self.pos = HEADER

    def take(self, n):
        if self.pos + n > len(self.frame):
            raise ValueError(f"read past end: pos {self.pos} + {n} > {len(self.frame)}")
        b = self.frame[self.pos:self.pos + n]
        self.pos += n
        return b

    def u8(self): return self.take(1)[0]
    def u16(self): return struct.unpack("<H", self.take(2))[0]
    def u32(self): return struct.unpack("<I", self.take(4))[0]
    def i32(self): return struct.unpack("<i", self.take(4))[0]
    def u64(self): return struct.unpack("<Q", self.take(8))[0]

    def cstr(self):
        end = self.frame.index(0, self.pos)
        s = self.frame[self.pos:end]
        self.pos = end + 1
        return s.decode("latin-1")

    def rest(self):
        return self.frame[self.pos:]


class Writer:
    def __init__(self, proto: int):
        self.proto = proto
        self.buf = bytearray()

    def raw(self, b: bytes): self.buf += b; return self
    def u8(self, v): self.buf += struct.pack("<B", v & 0xFF); return self
    def u16(self, v): self.buf += struct.pack("<H", v & 0xFFFF); return self
    def u32(self, v): self.buf += struct.pack("<I", v & 0xFFFFFFFF); return self
    def i32(self, v): self.buf += struct.pack("<i", v); return self
    def u64(self, v): self.buf += struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF); return self
    def f32(self, v): self.buf += struct.pack("<f", v); return self
    def zeros(self, n): self.buf += bytes(n); return self
    def obool(self, v): return self.u8(OBOOL_TRUE if v else OBOOL_FALSE)

    def cstr(self, s: str):
        self.buf += s.encode("latin-1") + b"\0"
        return self

    def frame(self) -> bytearray:
        size = HEADER + len(self.buf)
        return bytearray(struct.pack("<HBH", size, 0, self.proto)) + self.buf

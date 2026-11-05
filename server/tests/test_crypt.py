"""Frame cipher (server/kuf2/crypt.py) against the client's send side. Run: py -m pytest -q server/tests"""
import hashlib
import struct

import pytest

from kuf2.crypt import Cipher, HDR_LEN, _next, integrity_report

REPORT_ID = 0x4F4A     # one run's value; the id changes between runs


def frame(proto, body):
    return bytearray(struct.pack("<HBH", 5 + len(body), 0, proto) + body)


def same(out, plain):
    """Decrypted frame equals the plaintext; byte 2 keeps the check byte."""
    return out[:2] == plain[:2] and out[3:] == plain[3:]


class Client:
    """The client's send path 0x14158b0d0: 0x14158bd70 encrypts, 0x14158bf80 sets the seed to the check byte, and
    every so often a plain-text integrity report goes out without touching the seed."""
    def __init__(self):
        self.seed = 0x3C00
        self.digest, self.sent = hashlib.md5(), 0

    def send(self, data):
        self.digest.update(bytes(data[HDR_LEN:]))
        self.sent += 1
        seed = self.seed
        data[2] = seed & 0xFF
        s = sum(data[:HDR_LEN]) & 0xFF
        for i in range(HDR_LEN, len(data)):
            seed, k = _next(seed)
            s = (s + data[i]) & 0xFF
            data[i] ^= k
        seed, k = _next(seed)
        data[2] = k ^ s
        self.seed = data[2] if data[2] < 0x80 else data[2] - 0x100
        return data

    def report(self):
        d = self.digest.digest()
        out = bytearray(struct.pack("<HBH", 21, d[self.sent & 0xF], REPORT_ID) + d)
        self.digest, self.sent = hashlib.md5(), 0
        return out


def test_server_encrypt_matches_the_client_and_decrypts():
    c, tx, rx = Client(), Cipher(), Cipher()
    for n in range(20):
        plain = frame(0x1040, bytes(range(n, n + 10)))
        sent = c.send(bytearray(plain))
        assert sent == tx.encrypt(bytearray(plain))
        assert same(rx.decrypt(sent), plain)


@pytest.mark.parametrize("at", [[0], [3], [2, 3], [5, 9]])
def test_integrity_reports_are_recognised_and_leave_the_key(at):
    c, rx = Client(), Cipher()
    for n in range(12):
        if n in at:
            rep = c.report()
            assert integrity_report(rep)
            with pytest.raises(ValueError):
                rx.decrypt(bytearray(rep))
        plain = frame(0x5000 + n, struct.pack("<I", n * 7919) + bytes(n))
        assert same(rx.decrypt(c.send(bytearray(plain))), plain)


def test_a_corrupt_frame_raises_and_keeps_the_state():
    c, rx = Client(), Cipher()
    rx.decrypt(c.send(frame(0x1040, bytes(10))))
    seed = rx.seed
    bad = c.send(frame(0x1040, bytes(10)))
    kept = bytes(bad)
    bad[7] ^= 0x55
    with pytest.raises(ValueError):
        rx.decrypt(bad)
    assert rx.seed == seed and not integrity_report(bad)
    assert len(kept) == 15

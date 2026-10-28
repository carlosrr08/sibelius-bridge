"""End-to-end test of clicktrack.py on a synthetic NotePerformer-style click export. Needs no Sibelius.

The fake export has everything that makes the real one unusable: a 0.4 s ring on every hit,
up to +-18 ms of drifting jitter, a 30 ms attack delay after the 1 s lead-in, and soft eighth clicks in 6/8
partly buried under the ring. Score: 8 bars of 6/8 at q.=120, then 4 bars of 4/4 at q=100.
"""
import os, struct, sys, tempfile
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import clicktrack as ct

SR, PPQ = 48000, 960


def write_midi(path, events):
    """format-0 MIDI with meta events [(tick, type, data)]"""
    def vlq(n):
        out = [n & 0x7F]
        while n > 127:
            n >>= 7; out.append(0x80 | (n & 0x7F))
        return bytes(reversed(out))
    body, last = b'', 0
    for tick, typ, data in sorted(events, key=lambda e: e[0]):
        body += vlq(tick - last) + bytes([0xFF, typ, len(data)]) + data; last = tick
    body += vlq(0) + b'\xff\x2f\x00'
    with open(path, 'wb') as f:
        f.write(b'MThd' + struct.pack('>IHHH', 6, 0, 1, PPQ) + b'MTrk' + struct.pack('>I', len(body)) + body)


def score():
    """expected clicks: (seconds after the lead-in, kind) with kind 0 accent, 1 beat, 2 soft"""
    clicks, t = [], 0.0
    for _ in range(8):                                   # 6/8, q.=120: two 0.5 s beats, soft eighths between
        for beat in range(2):
            clicks.append((t, 0 if beat == 0 else 1))
            clicks += [(t + 0.5 / 3, 2), (t + 1.0 / 3, 2)]
            t += 0.5
    for _ in range(4):                                   # 4/4, q=100: four beats, no subdivision
        for beat in range(4):
            clicks.append((t, 0 if beat == 0 else 1)); t += 0.6
    return clicks, t


def hit(freq, amp, rng):
    n = int(0.45 * SR); tt = np.arange(n) / SR
    ring = sum(a * np.sin(2 * np.pi * freq * m * tt) * np.exp(-tt / tau)  # ~0.4 s woodblock ring + overtones
               for m, a, tau in ((1, 0.8, 0.12), (2.7, 0.25, 0.05), (5.1, 0.1, 0.02)))
    burst = rng.standard_normal(n) * np.exp(-tt / 0.002)                 # broadband attack
    return amp * (ring + 0.5 * burst)


def fake_export(folder):
    """write raw.wav + score.mid into folder; return their paths and the expected clicks"""
    rng = np.random.default_rng(7)
    clicks, length = score()
    slow = np.clip(np.cumsum(rng.standard_normal(len(clicks))) * 0.0015, -0.008, 0.008)
    drift = slow + np.clip(rng.normal(0, 0.005, len(clicks)), -0.01, 0.01)   # +-18 ms at most, like NotePerformer
    x = rng.normal(0, 10 ** (-84 / 20), int((1.0 + length + 2.0) * SR))     # render noise floor
    for (t, kind), d in zip(clicks, drift):
        h = hit(1300 if kind == 0 else 950, 0.7 if kind < 2 else 0.14, rng)
        s = int((1.0 + 0.030 + t + d) * SR)
        x[s:s + len(h)] += h
    raw, mid = os.path.join(folder, 'raw.wav'), os.path.join(folder, 'score.mid')
    ct.save(raw, np.stack([x, x], axis=1) * 0.5, SR)
    bar68 = 6 * PPQ // 2
    write_midi(mid, [(0, 0x51, (500000 // 2 * 4 // 3).to_bytes(3, 'big')),   # q.=120 -> q=180
                     (0, 0x58, bytes([6, 3, 24, 8])),
                     (8 * bar68, 0x51, (600000).to_bytes(3, 'big')),           # q=100
                     (8 * bar68, 0x58, bytes([4, 2, 24, 8]))])
    return raw, mid, clicks


def main():
    with tempfile.TemporaryDirectory() as tmp:
        raw, mid, clicks = fake_export(tmp)
        out = os.path.join(tmp, 'out.wav')
        ct.main(raw, mid, out)
        y, _ = ct.load(out)
        got = ct.onsets(y, SR)
        want = np.array([round((1.0 + t) * SR) for t, _ in clicks])
        assert len(got) == len(want), (len(got), len(want))
        assert np.abs(got - want).max() <= 2, np.abs(got - want).max()
        assert [ct.kind(y, SR, o) for o in got] == [k for _, k in clicks], 'accent/beat/soft pattern differs'
    print(f'clicktrack: {len(clicks)} clicks back on the exact grid, jitter and ring removed')


if __name__ == '__main__':
    main()

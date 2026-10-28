#!/usr/bin/env python3
"""Dry, sample-exact click track from a Sibelius + NotePerformer click export.

    python3 clicktrack.py raw.wav score.mid out.wav

raw.wav:   File > Export > Audio with only the click strip soloed (WAV 24-bit)
score.mid: File > Export > MIDI of the same score (only its tempo/time-signature
           events are used, so muted instruments don't matter)

Every click Sibelius plays (accent, beat, soft beat-group click) is kept, but
snapped to its exact musical position (bar start from the MIDI time signatures,
then the nearest eighth, or 32nd in odd bars) and re-timed from the MIDI tempo map. That removes
NotePerformer's +-18 ms jitter; each hit is a ~60 ms dry copy of NotePerformer's
own woodblock, so the ring is gone too. Beat 1 stays at 1.000 s like every
NotePerformer export. Output: same rate/length as raw.wav, 24-bit, peak -1 dBFS.
"""
import sys, wave, struct
import numpy as np

T0, PRE, KEEP, FADE = 1.000, 0.002, 0.060, 0.025


def load(p):
    w = wave.open(p); sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    assert w.getsampwidth() == 3, 'export the raw click as 24-bit WAV'
    raw = np.frombuffer(w.readframes(n), dtype=np.uint8).reshape(-1, 3)
    v = raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16)
    return np.where(v >= 1 << 23, v - (1 << 24), v).reshape(-1, ch) / float(1 << 23), sr


def save(p, x, sr):
    b = (np.round(np.clip(x, -1, 1 - 2**-23) * (1 << 23)).astype(np.int32) & 0xFFFFFF).astype(np.uint32)
    o = wave.open(p, 'wb'); o.setnchannels(x.shape[1]); o.setsampwidth(3); o.setframerate(sr)
    o.writeframes(np.stack([b & 0xFF, (b >> 8) & 0xFF, (b >> 16) & 0xFF], -1).astype(np.uint8).tobytes()); o.close()


def read_midi(p):
    """ppq, tempo events [(tick, sec_per_quarter)], time signatures [(tick, num, den)] in file order"""
    d = open(p, 'rb').read(); assert d[:4] == b'MThd'
    _, ntr, ppq = struct.unpack('>HHH', d[8:14]); pos, tempo, sig = 14, [], []
    def vlq(q):
        v = 0
        while True:
            b = d[q]; q += 1; v = (v << 7) | (b & 0x7F)
            if b < 0x80: return v, q
    for _ in range(ntr):
        ln = struct.unpack('>I', d[pos + 4:pos + 8])[0]; q, end, t, rs = pos + 8, pos + 8 + ln, 0, 0
        while q < end:
            dt, q = vlq(q); t += dt; st = d[q]
            if st == 0xFF:
                typ = d[q + 1]; l, q = vlq(q + 2); data = d[q:q + l]; q += l
                if typ == 0x51: tempo.append((t, int.from_bytes(data, 'big') / 1e6))
                if typ == 0x58: sig.append((t, data[0], 2 ** data[1]))
            elif st in (0xF0, 0xF7):
                l, q = vlq(q + 1); q += l
            else:
                if st & 0x80: rs = st; q += 1
                q += 1 if (rs & 0xF0) in (0xC0, 0xD0) else 2
        pos = end
    key = lambda e: e[0]                              # stable: same-tick events keep file order, last one wins
    return ppq, sorted(tempo, key=key), sorted(sig, key=key)


class TempoMap:
    def __init__(self, ppq, tempo):
        ticks, spq = [], []
        for t, s in tempo:
            if ticks and ticks[-1] == t: spq[-1] = s
            else: ticks.append(t); spq.append(s)
        self.ppq, self.ticks, self.spq = ppq, np.array(ticks), np.array(spq)
        self.secs = np.concatenate([[0], np.cumsum(np.diff(self.ticks) * self.spq[:-1] / ppq)])
    def sec(self, tick):
        i = max(np.searchsorted(self.ticks, tick, side='right') - 1, 0)
        return self.secs[i] + (tick - self.ticks[i]) * self.spq[i] / self.ppq
    def tick(self, sec):
        i = max(np.searchsorted(self.secs, sec, side='right') - 1, 0)
        return self.ticks[i] + (sec - self.secs[i]) * self.ppq / self.spq[i]


def bar_starts(ppq, sig, last_tick):
    out = []
    for i, (t, n, d) in enumerate(sig):
        stop = sig[i + 1][0] if i + 1 < len(sig) else last_tick
        L = n * 4 * ppq / d
        while t < stop - 1: out.append(t); t += L
    return np.array(sorted(set(out)))


def onsets(x, sr):
    """attacks incl. soft clicks: 1 ms envelope jumps 2.5x above the previous ~20 ms;
    attack point = first sample over 20% of the hit's peak"""
    m = np.abs(x).max(axis=1); ms = sr // 1000; L = len(m) // ms
    e = m[:L * ms].reshape(L, ms).max(axis=1); on = []
    for t in range(25, L):
        if e[t] > 0.05 and e[t] > 2.5 * e[t - 25:t - 3].max() and (not on or t - on[-1] > 40):
            on.append(t)
    out = []
    for t in on:
        a = (t - 5) * ms; seg = m[a:a + 20 * ms]; out.append(a + int(np.argmax(seg > 0.2 * seg.max())))
    return np.array(out)


def kind(x, sr, o):
    """0 = accent (high woodblock), 1 = beat (low, loud), 2 = soft beat-group click"""
    f = np.fft.rfftfreq(1440, 1 / sr)[np.argmax(np.abs(np.fft.rfft(x[o:o + 1440, 0] * np.hanning(1440))))]
    if f > 1150: return 0
    return 2 if np.abs(x[o:o + 720]).max() < 10 ** (-7 / 20) else 1


def flux_probe(m, sr, s, n=512, hop=48, span=20):
    """max positive log-spectral flux (1.5-12 kHz) within +-span ms of sample s: a new attack
    shows up even under the previous click's ring, which only decays (negative flux). +-20 ms covers
    NotePerformer's per-click jitter around the position interpolated from the loud neighbours"""
    a = int(s) - (span + 1) * hop
    if a < 0 or a + (2 * span + 2) * hop + n > len(m): return 0.0
    fr = np.lib.stride_tricks.sliding_window_view(m[a:a + (2 * span + 2) * hop + n], n)[::hop][:2 * span + 2] * np.hanning(n)
    f = np.fft.rfftfreq(n, 1 / sr); band = (f > 1500) & (f < 12000)
    X = 20 * np.log10(np.abs(np.fft.rfft(fr, axis=1)) + 1e-7)[:, band]
    return float(np.maximum(np.diff(X, axis=0), 0).mean(axis=1).max())


def main(src, mid, dst):
    x, sr = load(src)
    x *= 10 ** (-1 / 20) / np.abs(x).max()           # click fader may be anywhere: normalize to -1 dBFS
    ppq, tempo, sig = read_midi(mid); tm = TempoMap(ppq, tempo)
    A = onsets(x, sr); K = np.array([kind(x, sr, o) for o in A])
    soft_env = A[K == 2]; A, K = A[K != 2], K[K != 2]  # soft clicks are re-found below on the eighth grid
    last = tm.tick(A[-1] / sr - T0) + 8 * ppq
    bars = bar_starts(ppq, sig, last); q8, q32 = ppq / 2, ppq / 8

    # loud clicks sit on eighths: snapping to 32nds lets NotePerformer's jitter mis-snap at fast
    # tempi (32nd = 38 ms at q.=130). Odd bars (e.g. 33/32) can put a click off the eighth grid;
    # only those fall back to 32nds
    sec = lambda ticks: np.array([tm.sec(s) for s in ticks])
    off = 0.030                                       # NotePerformer's attack delay, refined below
    for _ in range(3):
        est = np.array([tm.tick(t) for t in A / sr - T0 - off])
        b = np.maximum(np.searchsorted(bars, est + q32 / 2, side='right') - 1, 0)
        s8 = bars[b] + np.round((est - bars[b]) / q8) * q8
        s32 = bars[b] + np.round((est - bars[b]) / q32) * q32
        snap = np.where(np.abs(A / sr - T0 - off - sec(s8)) < 0.025, s8, s32)
        res = A / sr - T0 - sec(snap)
        off = float(np.median(res))
    res = (res - off) * 1000
    print(f'{len(A)} loud clicks ({(K==0).sum()} accents, {(K==1).sum()} beats), {len(bars)} bars; '
          f'NotePerformer delay {off*1000:.1f} ms, jitter sd {res.std():.1f} ms, max {np.abs(res).max():.1f} ms'
          + (f'; {(snap != s8).sum()} off the eighth grid' if (snap != s8).any() else ''))
    assert np.abs(res).max() < 25, 'a click does not sit near a 32nd: check the MIDI export matches the score'
    assert len(np.unique(snap)) == len(snap), 'two clicks snapped to one position'

    # soft clicks (Subdivide beats / irregular beat groups) fall on eighths between the loud ones;
    # NotePerformer's jitter is local, so place each probe by interpolating between its two neighbours
    # Sibelius' pattern is fixed per meter, so all eighths with the same (meter, beat-group length,
    # position) vote together; a soft eighth right after a loud click is buried in its ring and
    # would be ambiguous on its own
    m = x.mean(axis=1); e8 = ppq / 2; cand = []
    sig_t = np.array([s[0] for s in sig])
    for ta, tb, sa, sb in zip(snap, snap[1:], A, A[1:]):
        pos = lambda t: sa + (sb - sa) * (tm.sec(t) - tm.sec(ta)) / (tm.sec(tb) - tm.sec(ta))
        _, num, den = sig[np.searchsorted(sig_t, ta, side='right') - 1]
        k = 1
        while ta + k * e8 < tb - ppq / 8:
            t = ta + k * e8                            # control: the sixteenth before it, never clicked
            cand.append(((num, den, round((tb - ta) / e8 * 4) / 4, k), t,
                         flux_probe(m, sr, pos(t)), flux_probe(m, sr, pos(t - e8 / 2))))
            k += 1
    soft = []
    if cand:
        ctrl = np.array([c[3] for c in cand]); thr = np.percentile(ctrl, 99) + 0.3
        classes = {}
        for key, t, v, cv in cand: classes.setdefault(key, []).append((t, v, cv))
        for key, rows in sorted(classes.items()):
            v = np.array([r[1] for r in rows]); cv = np.array([r[2] for r in rows])
            if len(rows) >= 3:
                d = np.median(v) - np.median(cv)
                assert not 0.15 < d < 0.45, f'{key}: soft-click evidence ambiguous ({d:+.2f}), check by ear'
                hit = d >= 0.45
                if hit or d > 0.1:
                    print(f'  {key[0]}/{key[1]}, {key[2]:g}-eighth group, eighth {key[3]}: {len(rows)}x, '
                          f'probe {np.median(v):.2f} vs control {np.median(cv):.2f} -> {"soft click" if hit else "none"}')
                if hit: soft += [r[0] for r in rows]
            else:                                      # too few to vote: decide one by one
                soft += [r[0] for r in rows if r[1] > thr]
        print(f'eighth positions tested {len(cand)} in {len(classes)} classes: {len(soft)} soft clicks')
    soft = np.array(sorted(soft))
    pos_all = np.array([tm.sec(t) for t in soft])
    stray = [s / sr for s in soft_env if not len(pos_all) or np.abs(pos_all + T0 + off - s / sr).min() > 0.03]
    if stray: print(f'ignored {len(stray)} soft detections off the eighth grid (ring artifacts) at {np.round(stray, 2).tolist()} s')

    at_bar = np.isin(snap, bars)
    odd = [int(i) for i in np.flatnonzero((K == 0) != at_bar)]
    print(f'accents exactly on bar starts: {(at_bar & (K == 0)).sum()}/{len(bars)}')
    assert not odd, f'accents and MIDI bar starts disagree at clicks {odd[:10]}: the MIDI export does not match the audio'

    p = int(PRE * sr); hits = {}
    def cut(o):
        h = x[o - p:o + int(KEEP * sr)].copy()
        h[:p] *= np.linspace(0, 1, p)[:, None]
        h[-int(FADE * sr):] *= (0.5 * (1 + np.cos(np.linspace(0, np.pi, int(FADE * sr)))))[:, None]
        return h
    for k in (0, 1):
        hits[k] = cut(A[np.flatnonzero(K == k)[0]])
    if len(soft):                                      # cleanest soft hit: the one with the quietest ring before it
        clean = [s for s in soft_env if np.abs(m[s - int(0.03 * sr):s - int(0.005 * sr)]).max() < 0.03]
        hits[2] = cut(clean[0]) if clean else hits[1] * 10 ** (-12 / 20)
    snap = np.concatenate([snap, soft]); K = np.concatenate([K, np.full(len(soft), 2)])
    o = np.argsort(snap); snap, K = snap[o], K[o]
    assert len(np.unique(snap)) == len(snap)
    grid = np.round((T0 + np.array([tm.sec(s) for s in snap])) * sr).astype(int)
    out = np.zeros_like(x)
    for g, k in zip(grid, K):
        out[g - p:g - p + len(hits[k])] += hits[k]
    save(dst, out, sr)

    # check the file we wrote
    y, _ = load(dst); B = onsets(y, sr)
    gaps = [np.abs(y[g - p + len(hits[k]) + 1:g2 - p]).max() for g, g2, k in zip(grid, grid[1:], K) if g2 - g > len(hits[k])]
    assert len(B) == len(grid) and np.abs(B - grid).max() <= 2, 'clicks not on grid'
    assert np.array_equal(np.array([kind(y, sr, o) for o in B]), K), 'click types changed'
    assert max(gaps) == 0, 'sound between clicks'
    print(f'wrote {dst}: {len(B)} clicks on the exact grid, types kept, silence between clicks, {len(y)/sr:.3f} s')


if __name__ == '__main__':
    main(*sys.argv[1:4])

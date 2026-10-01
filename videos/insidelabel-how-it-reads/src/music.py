"""The film's music: an original track synthesised here, so it is free and needs no licence.

Plain Python (no numpy), deterministic (seeded noise), written to assets/music.wav; ffmpeg then
adds space, loudness (-16 LUFS for social) and fades, and makes assets/music.m4a.

Calm, light, 90 BPM in C. The sound follows the picture (cue times are the film's, shared by
the 16:9 and 9:16 cuts):
  0 to 5 s   pad only, the "can you find the milk?" question
  5 s        a plucked arpeggio starts as the phone arrives
  6.6 s      shutter click; 32.2 s the second (blurry) photo
  11 to 37 s a soft kick under "AI reads. Rules decide." onwards
  17.55 s    a two-note chime as the allergen card lands
  25.95 s    a soft tap as the finger presses the tile
  37 s       everything resolves on C major 9 for the end card, then fades
"""
import math
import pathlib
import random
import struct
import wave

ROOT = pathlib.Path(__file__).resolve().parent.parent
SR = 44100
LENGTH = 41.0
N = int(SR * LENGTH)
BEAT = 60 / 90
BAR = 4 * BEAT
END = 37.0

mix = [0.0] * N


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def add(start, samples, gain=1.0):
    i0 = int(start * SR)
    for i, v in enumerate(samples):
        j = i0 + i
        if 0 <= j < N:
            mix[j] += v * gain


CHORDS = [  # (pad notes, bass root), one per bar
    ((53, 57, 60, 64), 41),  # Fmaj7
    ((55, 59, 62, 67), 43),  # G
    ((52, 55, 59, 62), 40),  # Em7
    ((57, 60, 64, 67), 45),  # Am7
]
FINAL = ((48, 52, 55, 59, 62), 36)  # Cmaj9


def chord_at(t):
    return FINAL if t >= END else CHORDS[int(t // BAR) % len(CHORDS)]


def pad_note(m, dur, amp):
    f = hz(m)
    out = []
    att, rel = 0.6, 0.9
    for i in range(int((dur + rel) * SR)):
        t = i / SR
        env = min(1.0, t / att) if t < dur else max(0.0, 1 - (t - dur) / rel)
        env *= min(1.0, t / att)
        s = (math.sin(2 * math.pi * f * 0.9985 * t) + math.sin(2 * math.pi * f * 1.0015 * t)
             + 0.25 * math.sin(2 * math.pi * f * 2 * t))
        out.append(s * env * amp)
    return out


def pluck(m, amp, dur=0.9, seed=0):
    """Karplus-Strong: a short burst of seeded noise through a decaying delay line."""
    rnd = random.Random(seed)
    period = max(2, int(SR / hz(m)))
    buf = [rnd.uniform(-1, 1) for _ in range(period)]
    out = []
    for i in range(int(dur * SR)):
        v = buf[i % period]
        nxt = buf[(i + 1) % period]
        buf[i % period] = 0.996 * 0.5 * (v + nxt)
        fade = 1.0 if i < (dur - 0.15) * SR else max(0.0, (dur * SR - i) / (0.15 * SR))
        out.append(v * amp * fade)
    return out


def kick(amp):
    out, phase = [], 0.0
    for i in range(int(0.32 * SR)):
        t = i / SR
        f = 45 + 75 * math.exp(-t * 28)
        phase += 2 * math.pi * f / SR
        out.append(math.sin(phase) * math.exp(-t * 11) * amp)
    return out


def click(amp, seed):
    rnd = random.Random(seed)
    out, prev = [], 0.0
    for i in range(int(0.05 * SR)):
        n = rnd.uniform(-1, 1)
        hp = n - prev  # a cheap high-pass: a crisp shutter, not a thud
        prev = n
        out.append(hp * math.exp(-i / SR * 90) * amp)
    return out


def bell(notes, amp, dur=2.2):
    out = []
    for i in range(int(dur * SR)):
        t = i / SR
        s = sum(math.sin(2 * math.pi * hz(m) * t) * math.exp(-t * (2.2 + k)) for k, m in enumerate(notes))
        s += 0.3 * math.sin(2 * math.pi * hz(notes[0]) * 2.76 * t) * math.exp(-t * 6)  # a little metal
        out.append(s * amp)
    return out


# pad and bass, bar by bar, resolving at END
t = 0.0
while t < END:
    notes, root = chord_at(t)
    dur = min(BAR, END - t)
    for m in notes:
        add(t, pad_note(m, dur, 0.045))
    for b in (0, 2):
        if 5.0 <= t + b * BEAT < END:  # the bass waits for the phone; the hook is pad only
            add(t + b * BEAT, pluck(root, 0.32, dur=1.2, seed=int(t * 10) + b))
    t += BAR
for m in FINAL[0]:
    add(END, pad_note(m, LENGTH - END - 0.9, 0.05))
add(END, pluck(FINAL[1], 0.35, dur=2.5, seed=99))

# arpeggio in eighths from 5 s to the end card, one octave up
ORDER = (0, 1, 2, 3, 2, 1, 2, 3)
step, k = BEAT / 2, 0
t = 5.0
while t < END - 0.05:
    notes, _ = chord_at(t)
    m = notes[ORDER[k % len(ORDER)] % len(notes)] + 12
    lift = 0.6 if t < 11 else 1.0  # quieter until the beat comes in
    add(t, pluck(m, 0.13 * lift, seed=1000 + k))
    t += step
    k += 1

# soft kick on beats 1 and 3, 11 s to the end card
t = 11.0
while t < END - 0.1:
    add(t, kick(0.32))
    t += 2 * BEAT

# moments in the picture
add(6.6, click(0.5, 1))
add(32.2, click(0.5, 2))
add(25.95, click(0.22, 3))
add(17.55, bell((88, 95), 0.05))       # E6 + B6 as the allergen card lands
add(END + 0.1, bell((84, 91, 88), 0.045, dur=3.5))

peak = max(abs(v) for v in mix) or 1.0
with wave.open(str(ROOT / "assets/music.wav"), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h", int(v / peak * 0.89 * 32767)) for v in mix))
print("wrote assets/music.wav,", LENGTH, "s")

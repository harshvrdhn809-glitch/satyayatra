"""Fatafat Reel - poori Reel mein EK jaisi aawaaz (12 Oct 2026).

Harshvardhan: "jitne shots lag rahe unme voice tone change ho jaa rahi, ek
video mein saari voices ek hi pitch par honi chahiye".

KYUN BADALTI THI
================
Veo har tukde (khabar) ki aawaaz naye sire se banata hai - uske paas
"pichhli clip wali aawaaz" ka koi switch nahi. Prompt mein wahi aawaaz ka
vivran jaata hai (sy_fatafat_veo.VOICES), par wo nirdesh hai, taala nahi:
kisi tukde mein aawaaz thodi patli, kisi mein bhaari, kisi mein dheemi.

YAHAN KYA HOTA HAI
==================
1. Har tukde ki aawaaz ka PITCH naapa jaata hai (autocorrelation - bolne
   wale hisson ki median frequency).
2. Sab tukdon ka beech wala pitch "lakshya" banta hai, aur har tukda usi par
   khiskaya jaata hai - ffmpeg rubberband se, RAFTAAR BADLE BINA (isliye
   hont aur captions waise hi milte hain). Zyada se zyada MAX_SHIFT
   semitone - usse zyada kheenchne par aawaaz robot jaisi lagti hai.
3. Har tukde ka VOLUME (loudness) ek barabar.

Ye aawaaz ki banaavat (timbre) poori tarah ek nahi kar sakta - wo Veo ke
prompt (ek hi aawaaz ka vivran) aur sy_fatafat.one_voice (ek Reel mein
Veo aur Sarvam ki aawaaz mix nahi) ka kaam hai.

Kabhi throw nahi karta - kuch gadbad ho to aawaaz jaisi thi waisi.
"""
import os
import subprocess

TARGET_LUFS = -16.0
MAX_SHIFT = 3.0        # semitone - isse zyada khiskaana robotic lagta hai
MIN_SHIFT = 0.35       # isse kam farq kaan nahi pakadta - chhedo mat
RATE = 16000


def log(*a):
    print("[fatafat-voice]", *a, flush=True)


def _samples(path):
    """Aawaaz -> numpy float32 (16 kHz mono). None = nahi padhi."""
    try:
        import numpy as np
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(RATE),
             "-f", "s16le", "-"], capture_output=True, timeout=120).stdout
        if not raw:
            return None
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    except Exception as e:
        log("aawaaz nahi padhi:", e)
        return None


def pitch_hz(path, fmin=70.0, fmax=400.0):
    """Bolne wale hisson ka median pitch (Hz). 0 = naap nahi hua."""
    try:
        import numpy as np
    except Exception:
        return 0.0
    x = _samples(path)
    if x is None or len(x) < RATE // 2:
        return 0.0
    frame, hop = int(0.040 * RATE), int(0.020 * RATE)
    lo, hi = int(RATE / fmax), int(RATE / fmin)
    rms_all = float(np.sqrt(np.mean(x ** 2))) or 1e-9
    found = []
    win = np.hanning(frame).astype(np.float32)
    for i in range(0, len(x) - frame, hop):
        f = x[i:i + frame]
        if float(np.sqrt(np.mean(f ** 2))) < 0.5 * rms_all:
            continue                      # chuppi / saans
        f = (f - f.mean()) * win
        n = 1 << (2 * frame - 1).bit_length()
        spec = np.fft.rfft(f, n)
        ac = np.fft.irfft(spec * np.conj(spec), n)[:frame]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        seg = ac[lo:hi]
        k = int(np.argmax(seg))
        if seg[k] < 0.45:                 # saaf swar nahi (vyanjan/shor)
            continue
        found.append(RATE / float(lo + k))
    if len(found) < 5:
        return 0.0
    return float(np.median(found))


def semitones(src_hz, dst_hz):
    import math
    if src_hz <= 0 or dst_hz <= 0:
        return 0.0
    return 12.0 * math.log2(dst_hz / src_hz)


def _has_rubberband():
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"],
                             capture_output=True, text=True, timeout=30).stdout
        return " rubberband " in out
    except Exception:
        return False


def _fix(src, out, shift, rate=48000):
    """Pitch 'shift' semitone khiskao (raftaar wahi) + volume barabar."""
    ratio = 2.0 ** (shift / 12.0)
    chain = []
    if abs(shift) >= MIN_SHIFT:
        if _has_rubberband():
            chain.append("rubberband=pitch=%.5f:formant=preserved" % ratio)
        else:
            # Bina rubberband: sample-rate se pitch, atempo se raftaar wapas.
            chain.append("asetrate=%d,aresample=%d,atempo=%.5f"
                         % (int(rate * ratio), rate, 1.0 / ratio))
    chain.append("loudnorm=I=%.1f:TP=-1.5:LRA=7" % TARGET_LUFS)
    chain.append("aresample=%d" % rate)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", src, "-af", ",".join(chain), "-ac", "1",
                    "-c:a", "pcm_s16le", out], check=True, timeout=180)
    return out


def match(segs):
    """Reel ke sab tukdon ki aawaaz ek pitch aur ek volume par. Kitne tukde
    badle. seg["voice"] nayi file par aa jaata hai (lambai wahi)."""
    try:
        have = [s for s in segs if s.get("voice") and os.path.exists(s["voice"])]
        if len(have) < 2:
            return 0
        hz = {s["tag"]: pitch_hz(s["voice"]) for s in have}
        good = sorted(v for v in hz.values() if v > 0)
        target = good[len(good) // 2] if good else 0.0
        log("pitch (Hz): %s | lakshya %.0f" % (
            ", ".join("%s %.0f" % (k, v) for k, v in hz.items()), target))
        n = 0
        for s in have:
            shift = semitones(hz[s["tag"]], target) if target else 0.0
            if abs(shift) > MAX_SHIFT:
                log("tukda %s: %.1f semitone ka farq - %.0f tak hi khiskaya"
                    % (s["tag"], shift, MAX_SHIFT))
                shift = MAX_SHIFT if shift > 0 else -MAX_SHIFT
            out = s["voice"][:-4] + "_same.wav"
            try:
                _fix(s["voice"], out, shift)
            except Exception as e:
                log("tukda %s ki aawaaz nahi badli: %s" % (s["tag"], str(e)[:120]))
                continue
            s["voice"] = out
            s["pitch_shift"] = round(shift, 2)
            n += 1
        return n
    except Exception as e:
        log("aawaaz barabar karne mein gadbad (jaisi thi waisi):", str(e)[:200])
        return 0

"""Fatafat Reel ka anchor - Google Veo se (HeyGen ki jagah), Oct 2026.

KYUN
====
Harshvardhan: HeyGen ka API raasta mehenga lagta hai; Gemini ka naya video
(Veo) behtar banata hai. Gemini APP ka Pro subscription program se nahi
chalta (uski koi API nahi - API ka bill alag hota hai). Par WAHI Veo model
Google Cloud (Vertex AI) par pehle se juda hai (sy_anchor.veo_person_clip,
sy_veo.py) aur uska kharch Google Cloud ke credit se katta hai. Isliye
Reel ka anchor ab wahin se.

KAISE
=====
Har tukda (hook, har khabar, CTA) = Veo ka EK 8 second clip, jismein
presenter us tukde ki line KHUD Hindi mein bolti hai (aawaaz Veo ki - hont
apne aap milte hain, alag lip-sync ki zaroorat nahi). Chehra khabar ke tone
ke hisaab se: gambhir khabar par muskaan nahi, achhi par halki muskaan.

EK REEL, EK CHEHRA: pehla clip end-card wali presenter ki tasveer se
(image-to-video); Veo wo tasveer roke (photoreal chehra - ANCHOR.md) to
pehla clip sirf prompt se, aur BAAKI SAB CLIP usi pehle clip ke frame se -
taaki ek Reel mein ek hi ladki. Frame wala rasta bhi ruke to baaki tukde
bina anchor (Sarvam aawaaz) - doosra chehra kabhi nahi.

8 SECOND KI SEEMA: Veo ek clip mein 8 second tak. Isliye Veo wali Reel mein
har khabar ki line chhoti (~100 akshar, sy_fatafat WRITE niyam). Lambi line
wala tukda Veo nahi - Sarvam aawaaz, bina anchor.

KABHI NAHI ROKTA: koi bhi gadbad = wo tukda purane raste (Sarvam aawaaz,
footage + card + captions). Clip mein bolna na mile (chuppi) to bhi wahi.
"""
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import sy_config as cfg

LINE_MAX_CHARS = 105      # ~8 sec mein itna Hindi aaraam se (sy_explainer jaisa)
DAY_KEY = "ff_veo_day"
COUNT_KEY = "ff_veo_count"

TONE_FACE = {
    "serious": ("Her expression is serious and sombre throughout - absolutely "
                "no smile, lips relaxed, calm grave eyes, minimal head movement."),
    "neutral": ("Her expression is calm, neutral and professional - no big "
                "smile, small natural head movement."),
    "positive": ("She has a slight, warm, gentle smile - friendly but "
                 "composed, small natural nods."),
}


def log(*a):
    print("[fatafat-veo]", *a, flush=True)


# ----------------------------------------------------------- settings

def max_clips_per_day():
    return int(cfg.num("fatafat", "veo_max_clips_per_day", 21))


def resolution():
    return cfg.get("fatafat", "veo_resolution") or "1080p"


def workers():
    return max(1, int(cfg.num("fatafat", "veo_parallel", 3)))


def _today():
    return time.strftime("%Y-%m-%d")


def used_today():
    import sy_store as st
    if st.kv_get(DAY_KEY, "") != _today():
        return 0
    return int(st.kv_get(COUNT_KEY, 0) or 0)


def _note_clip():
    import sy_store as st
    if st.kv_get(DAY_KEY, "") != _today():
        st.kv_set(DAY_KEY, _today())
        st.kv_set(COUNT_KEY, 0)
    st.kv_set(COUNT_KEY, used_today() + 1)


def room():
    return max(0, max_clips_per_day() - used_today())


def ready():
    """(haan/nahi, wajah) - sasta, koi API nahi."""
    try:
        import sy_anchor
        if not sy_anchor.sa_path():
            return False, "GCP_SA_JSON (Veo ka service account) nahi"
        return True, ""
    except Exception as e:
        return False, "jaanch mein gadbad: %s" % e


def fits(text):
    return 0 < len(str(text or "").strip()) <= LINE_MAX_CHARS


# ----------------------------------------------------------- prompt

def _face():
    """Explainer wala chehra - par bina 'muskaan' ke (muskaan tone tay karta hai)."""
    import sy_explainer
    return sy_explainer.FACE.replace(
        "and a bright, friendly smile showing her upper teeth", "")


def speech(text, tone):
    return ("She looks straight into the camera and, starting right away, "
            "reads the news in clear, natural Hindi like a TV news anchor, at a "
            "brisk but clear pace: \"%s\" Then she stops speaking and stays "
            "silent. %s " % (str(text).replace('"', "'"),
                             TONE_FACE.get(tone, TONE_FACE["neutral"])))


def text_prompt(text, tone):
    import sy_explainer
    return ("Photorealistic video of %s, in %s. %s%s"
            % (_face(), sy_explainer.STUDIO, speech(text, tone), sy_explainer.TAIL))


def image_prompt(text, tone):
    import sy_explainer
    return ("The woman in the image, exactly as she looks in the image - same "
            "face, hair, clothes and studio. %sKeep her face, hair and outfit "
            "identical to the image. %s" % (speech(text, tone), sy_explainer.TAIL))


# ----------------------------------------------------------- ek clip

def _blocked(why):
    low = str(why or "").lower()
    return ("guideline" in low or "violat" in low or "person" in low
            or "video nahi mili" in low)


def _clip(text, tone, out, ref_b64=""):
    import sy_anchor
    p = image_prompt(text, tone) if ref_b64 else text_prompt(text, tone)
    # Kota ki ginti (database) yahan NAHI - ye threads mein chalta hai aur
    # SQLite ek thread ka connection doosre mein nahi maanta. make_all ginta hai.
    return sy_anchor.veo_person_clip(p, out, image_b64=ref_b64 or None,
                                     resolution=resolution())


def cut(raw, seg, lead, tail):
    """Bolne wala hissa kaat kar anchor.mp4 + voice_pad.wav. True/False.
    seg mein anchor_file, voice, dur, speech, anchor_cx bhar deta hai."""
    import sy_endcard
    import sy_explainer
    total = sy_endcard._duration(raw)
    a, b = sy_explainer._speech_span(raw)
    if total <= 0 or b - a < 1.0:
        log("tukda %s: clip mein bolna nahi mila" % seg["tag"])
        return False
    ws, we = max(0.0, a - lead), min(total, b + tail)
    anc = os.path.join(seg["dir"], "anchor.mp4")
    wav = os.path.join(seg["dir"], "voice_pad.wav")
    base = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", "%.3f" % ws, "-to", "%.3f" % we, "-i", raw]
    subprocess.run(base + ["-an", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "18", "-pix_fmt", "yuv420p", anc],
                   check=True, timeout=300)
    subprocess.run(base + ["-vn", "-ac", "1", "-ar", "48000",
                           "-c:a", "pcm_s16le", wav], check=True, timeout=120)
    seg.update(anchor=True, anchor_file=anc, voice=wav, veo=True,
               dur=round(we - ws, 3), speech=(round(a - ws, 3), round(b - ws, 3)),
               anchor_cx=sy_explainer._person_x(anc))
    return True


def _presenter_ref(workdir):
    """End-card presenter ki tasveer (base64), agar Veo ne pehle rok na lagayi ho."""
    import sy_store as st
    import sy_explainer
    if st.kv_get("explainer_img_blocked"):
        return ""
    try:
        return sy_explainer._reference_b64(workdir)
    except Exception:
        return ""


def _frame_ref(clip, workdir):
    try:
        import sy_explainer
        return sy_explainer._frame_b64(clip, 0.3, workdir, "ff_ref.jpg")
    except Exception as e:
        log("frame nahi nikla:", e)
        return ""


# ----------------------------------------------------------- bahar ka

def make_all(segs, workdir, lead=0.15, tail=0.30):
    """Har tukde ka Veo anchor clip. Kitne lage. Kabhi throw nahi.

    Jo tukda lage uske seg mein voice/dur/speech/anchor_file bhar jaate hain
    (aawaaz Veo ki); baaki ko caller Sarvam se bolwata hai."""
    try:
        ok, why = ready()
        if not ok:
            log("Veo anchor nahi:", why)
            return 0
        want = [s for s in segs if fits(s.get("text"))]
        for s in segs:
            if s not in want:
                log("tukda %s ki line %d akshar - 8 second mein nahi aayegi, "
                    "Sarvam aawaaz" % (s["tag"], len(str(s.get("text") or ""))))
        if not want:
            return 0
        if room() < len(want):
            log("aaj ka Veo anchor kota kam (%d bache, %d chahiye) - bina anchor"
                % (room(), len(want)))
            return 0

        def run(s, ref):
            raw = os.path.join(s["dir"], "veo_raw.mp4")
            t0 = time.time()
            ok, why = _clip(s["text"], s.get("tone") or "neutral", raw, ref)
            if not ok:
                return s, raw, why
            log("tukda %s (%s) ban gaya %.0fs mein" % (s["tag"], s.get("tone"),
                                                      time.time() - t0))
            return s, raw, ""

        ref = _presenter_ref(workdir)
        from_presenter = bool(ref)
        rest = list(want)
        done = []
        if not ref:
            # Pehla clip prompt se; baaki usi ke chehre se.
            first = rest.pop(0)
            s, raw, why = run(first, "")
            if not why:
                _note_clip()
            if why:
                log("pehla clip nahi bana - Reel bina anchor:", str(why)[:200])
                return 0
            done.append((s, raw))
            ref = _frame_ref(raw, workdir)
            if not ref:
                rest = []
        with ThreadPoolExecutor(max_workers=workers()) as ex:
            res = list(ex.map(lambda s: run(s, ref), rest))
        blocked = False
        for s, raw, why in res:
            if not why:
                _note_clip()
            if why:
                log("tukda %s par Veo nahi: %s" % (s["tag"], str(why)[:160]))
                blocked = blocked or _blocked(why)
                continue
            done.append((s, raw))
        if blocked and from_presenter:
            # Presenter ki tasveer par rok - agli Reel seedha prompt + frame.
            import sy_store as st
            st.kv_set("explainer_img_blocked", 1)
        n = 0
        for s, raw in done:
            try:
                if cut(raw, s, lead, tail):
                    n += 1
            except Exception as e:
                log("tukda %s kaatne mein gadbad: %s" % (s["tag"], e))
        log("Veo anchor %d/%d tukdon par (aaj %d/%d clip)"
            % (n, len(segs), used_today(), max_clips_per_day()))
        return n
    except Exception as e:
        log("Veo anchor mein gadbad (bina uske aage):", str(e)[:200])
        return 0


def desc_line():
    return ("इस वीडियो में दिखने वाली प्रस्तुतकर्ता और उसकी आवाज़ AI-जनित है "
            "(Google Veo) - कोई वास्तविक व्यक्ति नहीं।")

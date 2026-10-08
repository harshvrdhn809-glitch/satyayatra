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

# ALAG-ALAG CHEHRE (8 Oct 2026, Harshvardhan: "naye faces bhi video mein
# istemal kare"). Ek REEL mein ek hi chehra rehta hai (wahi purana usool -
# ek video mein doosra chehra nahi), par har Reel par baari-baari agla
# chehra. Sab kalpanik hain - kisi asli ya naamdaar vyakti jaise nahi.
# Sirf chehra/baal/kapde badalte hain; studio, camera aur andaaz wahi.
FACES = (
    ("a young Indian woman news presenter, about 25 years old, with an oval "
     "face and soft rounded jawline, warm medium wheatish-brown skin with "
     "natural texture, large expressive dark-brown almond-shaped eyes, "
     "well-defined naturally arched dark eyebrows, a straight medium nose, "
     "full lips with rose-pink lipstick, long straight dark-brown hair with a "
     "centre parting falling well past her shoulders, small gold jhumka "
     "earrings, a mustard-yellow cotton kurta with thin white piping at the "
     "neckline, a cream dupatta over both shoulders, and a small black lapel "
     "microphone"),
    ("an Indian woman news presenter in her early thirties, with a slightly "
     "square face and defined cheekbones, deeper brown skin with natural "
     "texture, dark eyes, neat straight eyebrows, a small nose stud, dark "
     "brown hair tied back in a low neat bun, small pearl studs, a deep teal "
     "silk-cotton kurta with a plain round neckline, and a small black lapel "
     "microphone"),
    ("a young Indian man news presenter, about 30 years old, with a lean face "
     "and trimmed short black beard, medium wheatish skin, dark eyes, short "
     "neatly combed black hair, a charcoal-grey shirt with the top button "
     "closed, and a small black lapel microphone"),
    ("an Indian woman news presenter about 28 years old, with a round face "
     "and warm fair-wheatish skin, dark eyes with subtle kajal, shoulder-"
     "length wavy dark hair worn open, small silver hoop earrings, a maroon "
     "kurta with a thin gold border at the neckline, and a small black lapel "
     "microphone"),
    ("an Indian man news presenter in his late thirties, clean shaven, with a "
     "broad face and medium-dark skin, short salt-and-pepper hair neatly "
     "combed, rectangular thin-rimmed glasses, a navy-blue formal shirt, and "
     "a small black lapel microphone"),
)
FACE_KEY = "ff_veo_face"

# Chehre ka bhaav - linga-nirpeksh shabdon mein (chehra stree ya purush,
# dono ho sakta hai - FACES dekhiye).
TONE_FACE = {
    "serious": ("The presenter's expression is serious and sombre throughout - "
                "absolutely no smile, lips relaxed, calm grave eyes, minimal "
                "head movement."),
    "neutral": ("The presenter's expression is calm, neutral and professional - "
                "no big smile, small natural head movement."),
    "positive": ("The presenter has a slight, warm, gentle smile - friendly but "
                 "composed, small natural nods."),
}

# Har prompt ke ant mein - camera, roshni aur do pakke niyam: koi asli
# vyakti jaisa nahi, aur screen par koi likhawat/logo nahi (hamara apna
# text render_core/sy_fatafat_render lagata hai).
TAIL = (
    "Static camera, medium shot from the waist up, the presenter stands "
    "slightly to the right of centre, broadcast lighting, shallow depth of "
    "field, natural skin texture. This is an ORIGINAL fictional person, not "
    "based on and not resembling any real, living or famous person. No "
    "on-screen text, no captions, no subtitles, no logos, no watermark, no TV "
    "channel logo or name in any corner. No background music - only the "
    "presenter's voice and quiet studio ambience.")


def log(*a):
    print("[fatafat-veo]", *a, flush=True)


# ----------------------------------------------------------- settings

def max_clips_per_day():
    return int(cfg.num("fatafat", "veo_max_clips_per_day", 21))


def resolution():
    return cfg.get("fatafat", "veo_resolution") or "1080p"


def face_mode():
    """rotate = har Reel par agla chehra (default, Harshvardhan ki maang),
    fixed = hamesha wahi end-card wali presenter."""
    m = (cfg.get("fatafat", "veo_faces") or "rotate").strip().lower()
    return m if m in ("rotate", "fixed") else "rotate"


def next_face():
    """Is Reel ka chehra - pichhli Reel wala nahi. (vivran, number)"""
    import sy_store as st
    # "or -1" NAHI: pehla chehra 0 hai aur 0 khaali jaisa lagta hai - us ek
    # galti se har Reel mein wahi pehla chehra aata tha (jaanch mein pakda).
    v = st.kv_get(FACE_KEY)
    k = int(v) if isinstance(v, (int, float)) else -1
    k = (k + 1) % len(FACES)
    st.kv_set(FACE_KEY, k)
    return FACES[k], k


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


# CHUPPI KA NIYAM (8 Oct 2026, Harshvardhan: "silence aa rahi video mein").
# Veo apne aap clip ko 8 second tak kheenchta hai - line chhoti ho to wo
# shuru mein saans leti hai, beech mein rukti hai aur ant mein chup khadi
# rehti hai. Prompt mein saaf mana, aur uske BAAD bhi kaat-chhant (cut())
# hoti hai - kyunki prompt ek nirdesh hai, taala nahi.
NO_PAUSE = (
    "The presenter begins speaking in the very first frame, with no pause "
    "before the first word. The presenter speaks continuously, without "
    "stopping between sentences - no long pauses, no hesitation, no waiting, "
    "no silent gaps anywhere. The presenter does not greet, introduce "
    "themselves or add any words of their own. ")


def speech(text, tone):
    return ("The presenter looks straight into the camera and reads this news "
            "in clear, natural Hindi like a TV news anchor, at a brisk but "
            "clear pace: "
            "\"%s\" %s%s " % (str(text).replace('"', "'"), NO_PAUSE,
                              TONE_FACE.get(tone, TONE_FACE["neutral"])))


def text_prompt(text, tone, face=""):
    import sy_explainer
    return ("Photorealistic video of %s, in %s. %s%s"
            % (face or _face(), sy_explainer.STUDIO, speech(text, tone), TAIL))


def image_prompt(text, tone):
    return ("The person in the image, exactly as they look in the image - same "
            "face, hair, clothes and studio. %sKeep their face, hair and outfit "
            "identical to the image. %s" % (speech(text, tone), TAIL))


# ----------------------------------------------------------- ek clip

def _blocked(why):
    low = str(why or "").lower()
    return ("guideline" in low or "violat" in low or "person" in low
            or "video nahi mili" in low)


def _clip(text, tone, out, ref_b64="", face=""):
    import sy_anchor
    p = image_prompt(text, tone) if ref_b64 else text_prompt(text, tone, face)
    # Kota ki ginti (database) yahan NAHI - ye threads mein chalta hai aur
    # SQLite ek thread ka connection doosre mein nahi maanta. make_all ginta hai.
    return sy_anchor.veo_person_clip(p, out, image_b64=ref_b64 or None,
                                     resolution=resolution())


# CHUPPI KAATNE KE NAAP. Veo clip ko 8 second tak kheenchta hai, isliye
# bolne ke aage-peeche aur beech-beech mein chuppi reh jaati hai. Prompt
# mana karta hai, par uspar bharosa nahi - yahan naap kar kaata jaata hai.
MAX_PAUSE = 0.34        # isse lambi chuppi beech se kat jaati hai
KEEP_PAUSE = 0.16       # kaatne ke baad itni chuppi bachti hai (saans)
VEO_LEAD = 0.10         # bolne se itna pehle se (munh khulta dikhe)
VEO_TAIL = 0.16         # bolne ke baad itni hi


def keep_spans(total, a, b, sil, lead, tail):
    """Clip ke wo hisse jo rakhne hain - beech ki lambi chuppi hata kar.
    [(shuru, ant)] second mein."""
    ws, we = max(0.0, a - lead), min(total, b + tail)
    spans, t = [], ws
    for s0, s1 in sorted(sil):
        s0, s1 = max(float(s0), ws), min(float(s1), we)
        if s1 - s0 <= MAX_PAUSE:
            continue
        ca, cb = s0 + KEEP_PAUSE / 2.0, s1 - KEEP_PAUSE / 2.0
        if cb <= ca or ca <= t + 0.05:
            continue
        spans.append((t, ca))
        t = cb
    if we - t > 0.05:
        spans.append((t, we))
    return [(round(x, 3), round(y, 3)) for x, y in spans if y - x > 0.05]


def _cut_cmd(raw, spans, out, audio):
    """Chune hue hisse jod kar ek file - video (bina aawaaz) ya sirf aawaaz."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", raw]
    if len(spans) == 1:
        s0, s1 = spans[0]
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-ss", "%.3f" % s0, "-to", "%.3f" % s1, "-i", raw]
        cmd += (["-vn", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le"] if audio
                else ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                      "-pix_fmt", "yuv420p"])
        subprocess.run(cmd + [out], check=True, timeout=300)
        return out
    parts, labels = [], ""
    for i, (s0, s1) in enumerate(spans):
        if audio:
            parts.append("[0:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS[a%d]"
                         % (s0, s1, i))
            labels += "[a%d]" % i
        else:
            parts.append("[0:v]trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS[v%d]"
                         % (s0, s1, i))
            labels += "[v%d]" % i
    parts.append("%sconcat=n=%d:v=%d:a=%d[o]"
                 % (labels, len(spans), 0 if audio else 1, 1 if audio else 0))
    cmd += ["-filter_complex", ";".join(parts), "-map", "[o]"]
    cmd += (["-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le"] if audio
            else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                  "-pix_fmt", "yuv420p"])
    subprocess.run(cmd + [out], check=True, timeout=300)
    return out


def cut(raw, seg, lead=VEO_LEAD, tail=VEO_TAIL):
    """Bolne wala hissa kaat kar anchor.mp4 + voice_pad.wav. True/False.

    Teen cheezein kat-ti hain: bolne se pehle ki chuppi, ant ki chuppi, aur
    beech ki har wo chuppi jo MAX_PAUSE se lambi ho. seg mein anchor_file,
    voice, dur, speech, anchor_cx bhar deta hai."""
    import sy_endcard
    import sy_explainer
    total = sy_endcard._duration(raw)
    a, b = sy_explainer._speech_span(raw)
    if total <= 0 or b - a < 1.0:
        log("tukda %s: clip mein bolna nahi mila" % seg["tag"])
        return False
    lead, tail = min(lead, VEO_LEAD), min(tail, VEO_TAIL)
    sil = sy_explainer._silences(raw, -32, 0.22)
    spans = keep_spans(total, a, b, sil, lead, tail)
    if not spans:
        log("tukda %s: kaatne ke baad kuch bacha hi nahi" % seg["tag"])
        return False
    dur = sum(y - x for x, y in spans)
    if dur < 0.8:
        log("tukda %s: bolna bahut chhota (%.1fs)" % (seg["tag"], dur))
        return False
    anc = os.path.join(seg["dir"], "anchor.mp4")
    wav = os.path.join(seg["dir"], "voice_pad.wav")
    _cut_cmd(raw, spans, anc, audio=False)
    _cut_cmd(raw, spans, wav, audio=True)
    # Naap dobara - jodne ke baad ki asli lambai (frame par baithti hai).
    got = sy_endcard._duration(anc) or dur
    cut_s = total - dur
    log("tukda %s: %.1fs mein se %.1fs chuppi kaati (%d tukde) - %.1fs bacha"
        % (seg["tag"], total, cut_s, len(spans), got))
    seg.update(anchor=True, anchor_file=anc, voice=wav, veo=True,
               dur=round(got, 3),
               speech=(round(lead, 3), round(max(lead + 0.3, got - tail), 3)),
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

def make_all(segs, workdir, lead=VEO_LEAD, tail=VEO_TAIL):
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

        # CHEHRA: rotate (default) = is Reel ka apna chehra, pichhli Reel
        # wala nahi; fixed = wahi end-card wali presenter. Dono mein EK REEL
        # MEIN EK HI CHEHRA - pehle clip ke baad baaki usi ke frame se.
        face, fno = ("", -1)
        if face_mode() == "rotate":
            face, fno = next_face()
            log("is Reel ka chehra: #%d" % (fno + 1))

        def run(s, ref):
            raw = os.path.join(s["dir"], "veo_raw.mp4")
            t0 = time.time()
            ok, why = _clip(s["text"], s.get("tone") or "neutral", raw, ref, face)
            if not ok:
                return s, raw, why
            log("tukda %s (%s) ban gaya %.0fs mein" % (s["tag"], s.get("tone"),
                                                      time.time() - t0))
            return s, raw, ""

        ref = "" if face_mode() == "rotate" else _presenter_ref(workdir)
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

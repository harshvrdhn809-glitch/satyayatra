"""AI anchor - bulletin ke sirf intro aur outro par ek chehra, Veo se.

YE FEATURE KYA HAI, AUR KYA NAHI
================================
Bulletin ki shuruaat mein "namaskar, dekhiye..." aur ant mein "...bane
rahiye" - itne hisse mein ab ek AI kirdaar screen par bol sakta hai. Beech
ki das khabrein waisi hi rehti hain jaisi pehle thi - sy_scenes/render_core
se bani, Sarvam ki aawaaz ke saath. Anchor sirf shuru aur ant ke 6-8-6-8
second ka hissa hai, poori video ka nahi.

YE KIRDAAR HAI, KISI GHATNA KA NAKLI FOOTAGE NAHI
==================================================
sy_veo.py mein ek sabse zaroori usool hai: "AADMI KABHI NAHI"
(personGeneration="dont_allow" hamesha) - kyunki wahan Veo khabar/gyan ke
DRISHYA banata hai, aur kisi asli ghatna ya vyakti ki AI se nakli tasveer
dikhana channel ke apne sach ke usool se seedha takrata hai.

Ye anchor us usool ko TOD NAHI raha - ye ek ALAG cheez hai. Ye ek
maana-hua, saaf-saaf synthetic KIRDAAR hai (jaise ek virtual presenter),
kisi asli ghatna ya asli vyakti ki nakal nahi. Isliye personGeneration
yahan alag hai (allow_adult) - par ye sirf ISI FILE tak seemit hai.
sy_veo.py ko haath tak nahi lagaya gaya; khabar/gyan/kaam ke chitran mein
"AADMI KABHI NAHI" bilkul waisa hi kaayam hai jaisa tha.

CHEHRA KAHAN SE AATA HAI
========================
Agar C:\SatyaYatra mein anchor_reference.jpg pehle se rakhi ho (khud
chuni ya banwai hui tasveer), to WAHI hamesha istemal hoti hai - ye
photoreal ho sakti hai, koi rok nahi. Ye tasveer kisi asli, pehchaane
jaane wale, jeevit ya naamdaar vyakti ki NAHI honi chahiye - koi bhi
naya/kalpanik chehra chahiye, chahe photoreal lage ya na lage.

Agar wo file wahan nahi hai, to REFERENCE_PROMPT se ek saaf 3D/graphic
(jaan-boojhkar photoreal NAHI) kirdaar apne aap ban jaata hai, taaki
bina kisi tasveer diye bhi anchor kaam kare.

Jo bhi chehra ho, wo roz WAHI rehta hai - kabhi badalta nahi, kyunki ek
baar ban jaane ke baad ye file dobara nahi banti.

KAISE JUDTA HAI
================
sy_produce.py mein render ke turant baad, sirf "bulletin" beat ke liye, ek
chhota hook hai jo wrap() bulata hai. wrap() intro aur outro clip banata
hai (Veo se, anchor ki ek hi reference tasveer ke saath, taaki chehra roz
ek jaisa rahe) aur ffmpeg se poori video ke aage-peechhe jod deta hai.
Kahin bhi kuch gadbad ho - reference na bane, clip na bane, jodne mein
dikkat - to wahi purani bina-anchor wali video chali jaati hai. Bulletin
kabhi is wajah se rukta nahi.

sy_bulletin.py apni TTS wali script se greeting/vida ki line hata deta hai
JAB anchor us din bolne wala ho (should_narrate_wrap() se pehle hi jaanch
lete hain) - taaki ek hi baat do aawazon mein do baar na sunayi de. Agar
baad mein anchor phir bhi na ban paya (kabhi-kabhi ho sakta hai), to us
din ka bulletin bina bole hi shuru/khatam hoga - dur ki baat nahi, kyunki
Telegram approval par aapki nazar phir bhi padegi.

PAISA - ALAG KOTA
==================
Anchor ka apna kota hai ([anchor] max_per_day), [veo] wale jaankari-chitran
kote se ALAG - taaki teen bulletin (roz 2 clip = intro+outro) us doosre
kaam ko na khaayein.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import time

import sy_config as cfg
import sy_net
import vertex

API = ("https://%s-aiplatform.googleapis.com/v1/projects/%s/locations/%s"
       "/publishers/google/models/%s:%s")


def log(*a):
    print("[anchor]", *a, flush=True)


# ----------------------------------------------------------- settings

def enabled():
    import sy_store as st
    override = st.kv_get("anchor_on")
    if override is not None:
        return bool(override)
    return cfg.num("anchor", "enabled", 0) == 1


def set_enabled(on):
    import sy_store as st
    st.kv_set("anchor_on", 1 if on else 0)


def model():
    return cfg.get("anchor", "model") or cfg.get("veo", "model") \
        or "veo-3.1-fast-generate-001"


def location():
    return cfg.get("anchor", "location") or cfg.get("veo", "location") \
        or "us-central1"


def image_model():
    return cfg.get("anchor", "image_model") or "gemini-2.5-flash-image"


def max_per_day():
    return cfg.num("anchor", "max_per_day", 6)


def sa_path():
    given = cfg.get("veo", "service_account")
    if given and os.path.exists(given):
        return given
    p = os.path.join(cfg.HERE, "satyayatra-sa.json")
    return p if os.path.exists(p) else ""


def reference_path():
    return os.path.join(cfg.HERE, "anchor_reference.jpg")


# ------------------------------------------------------- din ka hisaab

def _today():
    return time.strftime("%Y-%m-%d")


def used_today():
    import sy_store as st
    if st.kv_get("anchor_day", "") != _today():
        return 0
    return int(st.kv_get("anchor_count", 0) or 0)


def note_used():
    import sy_store as st
    if st.kv_get("anchor_day", "") != _today():
        st.kv_set("anchor_day", _today())
        st.kv_set("anchor_count", 0)
    st.kv_set("anchor_count", used_today() + 1)


def room_left():
    return max(0, max_per_day() - used_today())


def allowed():
    """Kya abhi anchor ke do clip (intro+outro) bana sakte hain?"""
    if not enabled():
        return False, "band hai ([anchor] enabled = 1 ya /anchor on)"
    if not sa_path():
        return False, "service account JSON nahi mili"
    if room_left() < 2:
        return False, "aaj ka kota poora ho chuka"
    return True, ""


def should_narrate_wrap():
    """sy_bulletin.py ke liye - ek halka, sasta pehle-se-jaanch.

    Asli clip yahan nahi bantI, sirf ye dekha jaata hai ki anchor chalu
    hai, kota bacha hai aur service account mili hai. Isi ke aadhar par
    sy_bulletin.py TTS script mein greeting/vida ki line rakhta hai ya
    nahi. (Reference tasveer abhi na bhi bani ho to chalega - wo turant
    ban jaati hai, sirf pehli baar der lagti hai.)
    """
    ok, _ = allowed()
    return ok


# ------------------------------------------------------- reference tasveer

REFERENCE_PROMPT = "\n".join([
    "A friendly professional virtual news presenter character for an",
    "Indian Hindi news channel, framed from the chest up, facing the",
    "camera directly, in a simple modern newsroom studio with soft blue",
    "and white studio light.",
    "",
    "STYLE: clearly a polished 3D-rendered / digitally illustrated",
    "CHARACTER - like a modern animated news-graphics avatar. NOT a",
    "photograph, NOT photorealistic. Smooth stylised features, obviously",
    "synthetic at a glance. Simple navy blazer, no id badge, no name tag,",
    "no text or logo anywhere on the person or in the studio background.",
    "",
    "This is an ORIGINAL fictional character, not based on and not",
    "resembling any real, living or named person.",
])


def ensure_reference():
    """Anchor ki reference tasveer - ek baar banti hai, phir hamesha wahi
    istemal hoti hai (taaki chehra roz na badle). (True, '') ya (False, wajah)."""
    p = reference_path()
    if os.path.exists(p) and os.path.getsize(p) > 20000:
        return True, ""
    sa = sa_path()
    if not sa:
        return False, "service account JSON nahi mili"
    log("anchor ki tasveer pehli baar bana rahe hain...")
    return vertex.generate(sa, cfg.get("veo", "project") or "", location(),
                           image_model(), REFERENCE_PROMPT, p)


# ------------------------------------------------------------ asli kaam

def _token():
    with open(sa_path(), encoding="utf-8") as f:
        sa = json.load(f)
    return vertex._access_token(sa), sa


def _clip_for_line(text_hi, out_path):
    """Ek line bolta hua anchor clip. (True, '') ya (False, wajah).
    Kabhi throw nahi karta."""
    try:
        with open(reference_path(), "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        return False, "reference tasveer padhi nahi gayi: %s" % e

    line = text_hi.replace('"', "'").strip()
    prompt = (
        "A virtual Hindi news presenter, matching the reference image "
        "exactly, standing in a simple TV news studio, looking directly "
        "into the camera and speaking clearly in Hindi with natural lip "
        'movement and a calm, confident news-anchor tone. The presenter '
        'says: "%s" Static camera, no camera movement, no on-screen '
        "text, no logos." % line
    )
    return veo_person_clip(prompt, out_path, image_b64=image_b64)


def veo_person_clip(prompt, out_path, image_b64=None, resolution="720p"):
    """Veo se ek insaani KIRDAAR wala clip (aawaaz ke saath). (True, '')
    ya (False, wajah). Kabhi throw nahi karta.

    image_b64 do to wo pehla frame banta hai (image-to-video); na do to
    sirf prompt se (text-to-video). sy_endcard.py (video ke ant ka
    like/subscribe presenter) bhi yahi istemal karta hai - dhyaan rahe:
    ANCHOR.md ke mutaabik Veo photoreal chehre wali TASVEER ko rok deta
    hai, par sirf prompt se kalpanik kirdaar banane par wo rok nahi hai.
    """
    try:
        token, sa = _token()
    except Exception as e:
        return False, "access token nahi mila: %s" % e

    pid = cfg.get("veo", "project") or sa.get("project_id") or ""
    if not pid:
        return False, "project id nahi mila"

    inst = {"prompt": prompt}
    if image_b64:
        inst["image"] = {"bytesBase64Encoded": image_b64, "mimeType": "image/jpeg"}
    params = {
        "sampleCount": 1,
        "durationSeconds": 8,
        "aspectRatio": "16:9",
        "resolution": resolution,
        # Yahi to anchor ki asli aawaaz hai - iske bina hilta hua mook
        # chehra hi rah jaayega.
        "generateAudio": True,
        # JAAN-BOOJHKAR sy_veo.py se ALAG - upar ki file-tippani dekhiye.
        "personGeneration": "allow_adult",
    }

    mdl = model()
    url = API % (location(), pid, location(), mdl, "predictLongRunning")

    # Wahi self-heal tareeka jo sy_veo.py mein hai: 400 aaye to jis
    # parameter par atka hai use gira kar dobara. Har naya/badla model
    # apna set khud tay karta hai, aur wo badalta rehta hai.
    KEEP = ("sampleCount", "durationSeconds", "aspectRatio")
    op, last = "", ""
    for _try in range(4):
        try:
            started = sy_net.post_json(
                url, {"instances": [inst], "parameters": params},
                headers={"Authorization": "Bearer " + token},
                timeout=120, retries=1)
            op = str(started.get("name") or "")
            break
        except sy_net.HttpError as e:
            body = str(getattr(e, "body", "") or "")
            last = "%s %s" % (e.status, body[:400])
            if e.status != 400:
                return False, "Veo ne mana kiya: " + last
            drop = ""
            for k in list(params.keys()):
                if k in KEEP:
                    continue
                if (("parameters." + k) in body or ("'%s'" % k) in body
                        or ('"%s"' % k) in body
                        or re.search(r"\b%s\b" % re.escape(k), body)):
                    drop = k
                    break
            if not drop:
                return False, "Veo ne mana kiya: " + last
            if drop == "personGeneration":
                log("CHETAVNI: ye model personGeneration nahi leta - "
                    "anchor phir bhi Veo ke apne default se banega.")
            elif drop == "generateAudio":
                log("CHETAVNI: ye model generateAudio nahi leta - clip "
                    "bina aawaaz ke ban sakta hai.")
            else:
                log("'%s' ye model nahi leta - hata kar dobara" % drop)
            params.pop(drop, None)
        except Exception as e:
            return False, "Veo tak baat nahi pahunchi: %s" % e
    if not op:
        return False, "Veo ne mana kiya: " + (last or "operation nahi bani")

    fetch = API % (location(), pid, location(), mdl, "fetchPredictOperation")
    waited, data = 0.0, {}
    while waited < 420:
        time.sleep(10)
        waited += 10
        try:
            data = sy_net.post_json(
                fetch, {"operationName": op},
                headers={"Authorization": "Bearer " + token},
                timeout=120, retries=1)
        except Exception as e:
            log("haal poochhne mein gadbad:", str(e)[:90])
            continue
        if data.get("done"):
            break
    if not data.get("done"):
        return False, "Veo ne %d second mein clip nahi di" % int(waited)
    if data.get("error"):
        return False, "Veo: %s" % str(data["error"])[:220]

    b64 = vertex._find_b64(data.get("response") or data)
    if not b64:
        return False, "jawab mein video nahi mili"
    try:
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(b64))
    except Exception as e:
        return False, "clip likhi nahi gayi: %s" % e
    if os.path.getsize(out_path) < 50000:
        return False, "clip bahut chhoti aayi"
    return True, ""


# ------------------------------------------------------------- jodna

def _area_and_labels(story):
    """story_id se area nikalo, aur uski intro/vida line sy_bulletin se
    hi lo - taaki wahi shabd do baar alag-alag jagah likhne se bachein."""
    import sy_bulletin
    sid = str(story.get("story_id") or "")
    area = ""
    for a in sy_bulletin.AREAS:
        if sid.startswith("bltn_%s_" % a):
            area = a
            break
    if not area:
        return "", "", ""
    return area, sy_bulletin.intro_line(area), sy_bulletin.outro_line(area)


def _concat(parts, out_path, workdir):
    """intro + beech ka bulletin + (agar bani ho to) outro - alag-alag
    jagah se aayi in clips ka naap/format ek jaisa nahi hota, isliye
    seedha jodna (concat demuxer) nahi - pehle sabko ek format mein
    laate hain (filter_complex), phir jodte hain."""
    W, H, FPS = 1920, 1080, 30
    inputs = []
    vlabels, alabels = [], []
    for i, p in enumerate(parts):
        inputs += ["-i", p]
        vlabels.append(
            "[%d:v]scale=%d:%d:force_original_aspect_ratio=decrease,"
            "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=%d,"
            "format=yuv420p[v%d]" % (i, W, H, W, H, FPS, i))
        alabels.append(
            "[%d:a]aformat=sample_rates=48000:channel_layouts=stereo[a%d]"
            % (i, i))
    concat_in = "".join("[v%d][a%d]" % (i, i) for i in range(len(parts)))
    filt = ";".join(vlabels + alabels) + (
        ";%s concat=n=%d:v=1:a=1[vout][aout]" % (concat_in, len(parts)))
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + inputs + [
        "-filter_complex", filt, "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "21",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart", out_path]
    subprocess.run(cmd, cwd=workdir, check=True, timeout=300)
    return out_path


def wrap(story, video_path, workdir):
    """sy_produce.py se render ke turant baad bulaya jaata hai.

    Kabhi throw nahi karta - kuch bhi gadbad ho to wahi purani video_path
    laut aati hai, bina anchor ke. Bulletin is wajah se kabhi nahi rukta.
    """
    if str(story.get("beat") or "") != "bulletin":
        return video_path

    ok, why = allowed()
    if not ok:
        log("anchor nahi laga (%s) - bulletin bina anchor ke jayega" % why)
        return video_path

    area, intro_line, outro_line = _area_and_labels(story)
    if not area:
        return video_path

    ok, why = ensure_reference()
    if not ok:
        log("reference tasveer nahi bani:", why, "- anchor is baar nahi")
        return video_path

    intro_path = os.path.join(workdir, "anchor_intro.mp4")
    outro_path = os.path.join(workdir, "anchor_outro.mp4")

    log("intro clip bana rahe hain...")
    ok, why = _clip_for_line(intro_line, intro_path)
    if not ok:
        log("intro clip nahi bani:", why, "- anchor is baar nahi")
        return video_path
    note_used()

    log("outro clip bana rahe hain...")
    ok, why = _clip_for_line(outro_line, outro_path)
    if not ok:
        log("outro clip nahi bani:", why, "- sirf intro ke saath jayega")
        outro_path = ""   # intro akela bhi poora chhodne se behtar
    else:
        note_used()

    parts = [intro_path, video_path] + ([outro_path] if outro_path else [])
    final_path = os.path.join(workdir, "bulletin_with_anchor.mp4")
    try:
        _concat(parts, final_path, workdir)
    except Exception as e:
        log("jodne mein gadbad:", e, "- anchor ke bina bhej rahe hain")
        return video_path

    if not os.path.exists(final_path) or os.path.getsize(final_path) < 100000:
        log("jodi hui video sahi nahi bani - anchor ke bina bhej rahe hain")
        return video_path

    try:
        import shutil
        shutil.copyfile(final_path, video_path)
    except Exception as e:
        log("aakhri video jagah par copy nahi hui:", e)
        return video_path

    log("anchor lag gaya - bulletin ab anchor ke saath")
    return video_path

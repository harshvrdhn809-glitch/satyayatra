"""HeyGen - hamari hi aawaaz (Sarvam) par anchor ke HONT milte hue (lip-sync).

KYA HOTA HAI (Oct 2026, Harshvardhan ka faisla)
===============================================
1. sy_edit tay karta hai ki kis tukde par anchor dikhegi (full / PIP).
2. Sirf unhi tukdon ki aawaaz voice.wav se kaat kar EK file mein jodi
   jaati hai (beech mein GAP ki chuppi) - poori aawaaz nahi. Paisa sirf
   anchor wale second ka lagta hai, aur poll karne ko sirf ek video.
3. HeyGen us aawaaz par presenter ki tasveer se bolta hua video banata hai.
   Aawaaz HeyGen ki NAHI - hamari Sarvam wali hi rehti hai; HeyGen ke
   video ki aawaaz phenk di jaati hai, sirf chehra/hont liye jaate hain.
4. Render (render_core) har khidki ke samay par us video ka sahi hissa
   footage ke upar bitha deta hai - full ya PIP. Hont mukhya aawaaz se
   milte hain kyunki dono ek hi voice.wav ke ek hi tukde se bane hain.

CHEHRA - KAUN SA AUR KAISE TIKTA HAI
====================================
Wahi end-card wali presenter (assets/endcard_presenter.mp4 ka saaf frame)
jo pasand aayi thi - sy_explainer._reference_b64 jaisa hi frame, kone ke
logo par channel ka badge.

HeyGen ka "photo avatar" (POST /v3/avatars type=photo) API se ban to jaata
hai, par HeyGen ke v3 dastavez ke mutaabik private avatar ko video mein
lagaane se PEHLE consent flow (browser mein, ek recording ke saath) poora
karna zaroori hai - wo program apne aap nahi kar sakta. Isliye:
  - [heygen] avatar_id (Secret HEYGEN_AVATAR_ID) diya ho - yaani aapne
    HeyGen dashboard mein isi tasveer se avatar bana kar consent kar diya
    hai - to wahi (type=avatar). Har video mein bilkul wahi.
  - warna type=image: wahi EK tasveer har baar (ek baar upload, asset id
    kv mein yaad) - avatar banane ki zaroorat hi nahi. Tasveer wahi to
    chehra bhi wahi.

KABHI NAHI ROKTA
================
Har bahar wala function kabhi throw nahi karta. Switch band, kota poora,
chaabi nahi, HeyGen fail/der - to anchor nahi, video pehle jaisi (footage /
studio / Veo anchor wala purana rasta). Video kabhi nahi rukti.

PAISA
=====
HeyGen per-minute credit leta hai. Roz ki seema [heygen] max_minutes_per_day
(kv mein din ka hisaab, sy_veo jaisa), har video ki apni seema
(max_seconds_short / max_seconds_long), aur /heygen on|off switch.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
import wave

import sy_config as cfg
import sy_net

API = "https://api.heygen.com"

# HeyGen ko bheji aawaaz mein do tukdon ke beech itni chuppi - taaki ek
# tukde ke aakhri shabd ka munh agle ke pehle shabd mein na ghule.
GAP = 0.40
# Har tukde ke aage-peeche itni aawaaz aur - munh bolne se zara pehle
# khulta hai; bina iske pehla akshar "kata hua" lagta hai.
PAD = 0.15
# Isse kam anchor ho to kharch ka matlab nahi.
MIN_SECONDS = 4.0

CREDIT = "AI प्रस्तुतकर्ता"


def log(*a):
    print("[heygen]", *a, flush=True)


# ----------------------------------------------------------- settings

def enabled():
    """Telegram ka /heygen switch config se UPAR (sy_veo.enabled jaisa)."""
    try:
        import sy_store as st
        override = st.kv_get("heygen_on")
        if override is not None:
            return bool(override)
    except Exception:
        pass
    return cfg.num("heygen", "enabled", 0) == 1


def set_enabled(on):
    import sy_store as st
    st.kv_set("heygen_on", 1 if on else 0)
    if on:
        # Credit bhar kar /heygen on - credit wali rok turant hatao.
        st.kv_set("heygen_no_credit_at", 0)


def api_key():
    return cfg.get("heygen", "api_key")


def avatar_id():
    return cfg.get("heygen", "avatar_id")


def _flt(key, default):
    try:
        return float(cfg.get("heygen", key) or default)
    except Exception:
        return float(default)


def max_minutes_per_day():
    return _flt("max_minutes_per_day", 3)


def max_seconds(long=False):
    return _flt("max_seconds_long" if long else "max_seconds_short",
                90 if long else 30)


def max_share(long=False):
    return _flt("max_share_long" if long else "max_share", 0.15 if long else 0.45)


def max_run():
    return _flt("max_run_seconds", 12)


def wait_minutes():
    return _flt("wait_minutes", 20)


def resolution():
    return cfg.get("heygen", "resolution") or "720p"


def ai_edit():
    return cfg.num("heygen", "ai_edit", 1) == 1


def long_on():
    return cfg.num("heygen", "long", 1) == 1


# ----------------------------------------------------------- din ka hisaab

def _today():
    return time.strftime("%Y-%m-%d")


def used_seconds_today():
    import sy_store as st
    if st.kv_get("heygen_day", "") != _today():
        return 0.0
    return float(st.kv_get("heygen_seconds", 0) or 0)


def note_used(secs):
    import sy_store as st
    if st.kv_get("heygen_day", "") != _today():
        st.kv_set("heygen_day", _today())
        st.kv_set("heygen_seconds", 0)
    st.kv_set("heygen_seconds", round(used_seconds_today() + float(secs), 1))


def room_seconds():
    return max(0.0, max_minutes_per_day() * 60.0 - used_seconds_today())


def line_slots(story):
    """fetch_shots se pehle: jaankari video mein kitne khaali tukde anchor
    ke liye rakhne hain (unpar Veo AI-chitran ka paisa nahi lagta - wahan
    anchor bolti hai). Khabar par 0 - wahan drishya ka pehra waisa hi rahe
    (sy_produce.visual_verdict anchor_planned ko bhara hua ginta hai)."""
    if str((story or {}).get("beat") or "") not in ("yojana", "kaam", "gyan", "tech"):
        return 0
    return max(0, cfg.num("heygen", "anchor_slots", 3))


# ----------------------------------------------------------- credit khatam
#
# 8 Oct 2026: HeyGen ne "HTTP 402 insufficient_credit" / "MOVIO_PAYMENT_
# INSUFFICIENT_CREDIT ... requires 'api' credits" diya - API ke credit
# (plan ke credit se ALAG) khatam. Tab har video par aawaaz chadhana aur
# 20 minute intezaar bekaar hai. Isliye credit ki galti dikhte hi kuch
# ghante HeyGen ki koshish band, aur Telegram par din mein ek baar saaf
# sandesh. Credit bharne ke baad /heygen on turant dobara kholta hai.
NO_CREDIT_KEY = "heygen_no_credit_at"
NO_CREDIT_HOURS = 6


def is_credit_error(text):
    t = str(text or "").lower()
    return "insufficient_credit" in t or "insufficient credit" in t or "http 402" in t


def note_credit_error(text):
    import sy_store as st
    st.kv_set(NO_CREDIT_KEY, time.time())
    log("HeyGen ka API credit khatam - %d ghante koshish band" % NO_CREDIT_HOURS)
    try:
        import sy_telegram
        sy_telegram._warn_once(
            "heygen_credit_warned",
            "<b>HeyGen ka API credit khatam</b>\n\nAnchor ki video nahi ban "
            "rahi (HeyGen: insufficient credit). Video aur Reel bina anchor ke "
            "ban rahi hain - rukti nahi.\n\napp.heygen.com -> Settings -> "
            "API / Billing mein <b>API credit</b> bhariye (plan ke credit se "
            "alag hote hain), phir <code>/heygen on</code>.")
    except Exception:
        pass


def credit_blocked():
    import sy_store as st
    at = float(st.kv_get(NO_CREDIT_KEY, 0) or 0)
    return bool(at) and time.time() - at < NO_CREDIT_HOURS * 3600


def ready(story=None, vertical=False):
    """(haan/nahi, wajah) - is video mein HeyGen anchor ki koshish ho sakti hai?
    Sasta: koi API call nahi."""
    try:
        if not enabled():
            return False, "band hai (/heygen on ya [heygen] enabled = 1)"
        if not api_key():
            return False, "HEYGEN_API_KEY Secret nahi hai"
        if credit_blocked():
            return False, "HeyGen ka API credit khatam (billing mein bhariye, phir /heygen on)"
        if vertical:
            # Purani bolly/viral Reel. Fatafat Reel apna rasta (sy_fatafat)
            # leti hai aur vertical=False se poochhti hai.
            return False, "bolly/viral Reel (9:16) par nahi - Fatafat Reel par haan"
        if room_seconds() < MIN_SECONDS:
            return False, "aaj ki seema (%.1f minute) poori" % max_minutes_per_day()
        return True, ""
    except Exception as e:
        return False, "jaanch mein gadbad: %s" % e


# ----------------------------------------------------------- HTTP

class HeyGenError(Exception):
    pass


def _headers(extra=None):
    h = {"x-api-key": api_key(), "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h


def _call(method, path, body=None, timeout=120, raw=None, ctype=None):
    """JSON lauta ta hai (poora envelope). Galti par HeyGenError."""
    url = path if path.startswith("http") else API + path
    hdr = _headers()
    data = None
    if raw is not None:
        data = raw
        hdr["Content-Type"] = ctype or "application/octet-stream"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        hdr["Content-Type"] = "application/json"
    try:
        out = sy_net.fetch(url, headers=hdr, data=data, method=method,
                           timeout=timeout, retries=1)
    except sy_net.HttpError as e:
        msg = "HTTP %s: %s" % (e.status, _err_text(e.body))
        if is_credit_error(msg):
            note_credit_error(msg)
        raise HeyGenError(msg)
    except Exception as e:
        raise HeyGenError("HeyGen tak baat nahi pahunchi: %s" % e)
    try:
        j = json.loads(out.decode("utf-8", "replace") or "{}")
    except Exception:
        raise HeyGenError("jawab JSON nahi tha")
    if isinstance(j, dict) and j.get("error"):
        raise HeyGenError(_err_text(j))
    return j


def _err_text(body):
    try:
        j = body if isinstance(body, dict) else json.loads(body or "{}")
        err = j.get("error") or {}
        if isinstance(err, dict):
            return ("%s %s" % (err.get("code") or "", err.get("message") or "")).strip() \
                or str(j)[:300]
        return str(err)[:300]
    except Exception:
        return str(body or "")[:300]


def _multipart(field, filename, blob, ctype):
    boundary = "----satyayatra" + uuid.uuid4().hex
    head = ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
            "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
            % (boundary, field, filename, ctype)).encode("utf-8")
    tail = ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    return head + blob + tail, "multipart/form-data; boundary=" + boundary


def upload_asset(path, ctype):
    """POST /v3/assets (multipart, field 'file', 32 MB tak) -> asset_id."""
    with open(path, "rb") as f:
        blob = f.read()
    raw, ct = _multipart("file", os.path.basename(path), blob, ctype)
    j = _call("POST", "/v3/assets", raw=raw, ctype=ct, timeout=300)
    aid = str(((j or {}).get("data") or {}).get("asset_id") or "")
    if not aid:
        raise HeyGenError("upload ke jawab mein asset_id nahi")
    return aid


def create_video(audio_asset, face, title="", res=None, motion_prompt="",
                 expressiveness=None):
    """POST /v3/videos -> video_id. face = {"kind": "avatar"|"image", ...}.

    motion_prompt / expressiveness: Fatafat Reel har khabar ke tone ke hisaab
    se deta hai (TONE_MOTION). Baaki video mein khaali - pehle jaisa."""
    body = {
        "aspect_ratio": "16:9",
        "resolution": res or resolution(),
        "audio_asset_id": audio_asset,
        "title": (title or "SatyaYatra anchor")[:90],
        # Background wahi jo tasveer mein hai (studio) - alag rang nahi.
    }
    if face.get("kind") == "avatar":
        body["type"] = "avatar"
        body["avatar_id"] = face["id"]
    else:
        body["type"] = "image"
        body["image"] = {"type": "asset_id", "asset_id": face["id"]}
    eng = (cfg.get("heygen", "engine") or "").strip()
    if eng:
        body["engine"] = {"type": eng}
    ex = (cfg.get("heygen", "expressiveness") or "").strip()
    if expressiveness is not None:
        ex = expressiveness
    if ex and eng != "avatar_v":
        body["expressiveness"] = ex
    if motion_prompt and eng != "avatar_v":
        body["motion_prompt"] = motion_prompt[:400]
    try:
        j = _call("POST", "/v3/videos", body=body)
    except HeyGenError as e:
        # motion_prompt Avatar IV (photo/tasveer) par hi chalta hai. Kisi
        # avatar/engine ne field na maani to bina uske ek baar - chehra phir
        # bhi us tone wale look ka hi rehta hai.
        if "motion_prompt" not in body or "motion" not in str(e).lower():
            raise
        log("motion_prompt nahi maana gaya - bina uske:", str(e)[:120])
        body.pop("motion_prompt", None)
        j = _call("POST", "/v3/videos", body=body)
    vid = str(((j or {}).get("data") or {}).get("video_id") or "")
    if not vid:
        raise HeyGenError("video_id nahi mila")
    return vid


def video_status(video_id):
    """GET /v3/videos/{id} -> data dict (status, video_url, duration, failure_*)."""
    j = _call("GET", "/v3/videos/%s" % video_id, timeout=60)
    return (j or {}).get("data") or {}


# ----------------------------------------------------------- chehra

def presenter_jpg(workdir):
    """End-card presenter ka saaf frame (badge ke saath) -> path, ya ""."""
    try:
        import sy_explainer
        b64 = sy_explainer._reference_b64(workdir)
        if not b64:
            return ""
        p = os.path.join(workdir, "explainer_ref.jpg")
        return p if os.path.exists(p) else ""
    except Exception as e:
        log("presenter ki tasveer nahi nikli:", e)
        return ""


def face(workdir, fresh=False):
    """Kaun sa chehra: {"kind": "avatar", "id"} ya {"kind": "image", "id"}.

    Image ek hi baar upload hoti hai - asset id kv mein yaad (tasveer ki chhap
    ke saath, taaki presenter badle to nayi upload ho). fresh=True par dobara."""
    aid = avatar_id()
    if aid:
        return {"kind": "avatar", "id": aid}
    import sy_store as st
    jpg = presenter_jpg(workdir)
    if not jpg:
        raise HeyGenError("presenter ki tasveer nahi (assets/endcard_presenter.mp4?)")
    with open(jpg, "rb") as f:
        sig = hashlib.sha1(f.read()).hexdigest()[:12]
    saved = st.kv_get("heygen_image") or {}
    if not fresh and saved.get("sig") == sig and saved.get("id"):
        return {"kind": "image", "id": saved["id"]}
    log("presenter ki tasveer HeyGen par chadha rahe hain (ek baar)...")
    asset = upload_asset(jpg, "image/jpeg")
    st.kv_set("heygen_image", {"id": asset, "sig": sig, "at": time.time()})
    return {"kind": "image", "id": asset}


# ----------------------------------------------------------- tone (Fatafat Reel)
#
# ANCHOR KA CHEHRA KHABAR KE HISAAB SE (Oct 2026, Harshvardhan): maut/haadsa/
# apraadh/aapda par gambhir chehra (muskaan bilkul nahi), achhi khabar par
# halki muskaan, aam khabar par neutral.
#
# HeyGen mein do raste hain, dono lagaye gaye hain:
#   1. LOOKS (sabse bharosemand) - ek hi presenter ke alag "look" (photo
#      avatar ke look), har ek ka apna id. Dashboard mein usi presenter se
#      teen look banaiye - gambhir, neutral, halki muskaan - aur unke id
#      Secrets HEYGEN_LOOK_SERIOUS / _NEUTRAL / _POSITIVE mein. Tasveer mein
#      jo chehra hai, video ka bhaav wahin se shuru hota hai.
#   2. motion_prompt + expressiveness (Avatar IV, POST /v3/videos) - har tone
#      ka apna nirdesh. HeyGen ke dastavez ise mukhya roop se HARKAT (sir,
#      haath) ke liye batate hain - chehre ke bhaav ki guarantee nahi. Look
#      na ho to sirf yahi lagta hai (ek hi tasveer, alag nirdesh).
TONES = ("serious", "neutral", "positive")

TONE_MOTION = {
    "serious": ("Composed news anchor delivering grave news. Serious, sombre "
                "face, absolutely no smile, lips relaxed, minimal head "
                "movement, steady eye contact with the camera."),
    "neutral": ("Calm professional news anchor. Neutral attentive expression, "
                "no big smile, small natural head movement, eye contact."),
    "positive": ("Warm news anchor sharing good news. A slight gentle smile, "
                 "relaxed and friendly, small natural nods, eye contact."),
}
TONE_EXPRESS = {"serious": "low", "neutral": "low", "positive": "medium"}


def look_for(tone):
    """Is tone ka look id (Secret se), ya ""."""
    tone = tone if tone in TONES else "neutral"
    return (cfg.get("heygen", "look_" + tone) or "").strip()


def looks_ready():
    """Teeno look diye gaye hain?"""
    return all(look_for(t) for t in TONES)


def tone_face(workdir, tone):
    """Tone wala look ho to wahi, warna wahi purana chehra (face())."""
    lk = look_for(tone)
    if lk:
        return {"kind": "avatar", "id": lk, "tone": tone}
    fc = dict(face(workdir))
    fc["tone"] = tone
    return fc


def reel_resolution():
    # Reel mein anchor ka 16:9 frame beech se kaat kar khada kiya jaata hai -
    # 1080p par kati hui jagah bhi saaf rehti hai.
    return cfg.get("heygen", "reel_resolution") or "1080p"


def submit_clip(wav, workdir, tone, title=""):
    """EK tukde (ek khabar) ki aawaaz par ek HeyGen video. video_id lauta ta
    hai, ya HeyGenError. Wahi aawaaz + wahi chehra pehle bheja ho to wahi id
    (dobara paisa nahi). Kota note_used() mein."""
    secs = _wav_dur(wav)
    mp3 = _to_mp3(wav, wav[:-4] + "_hg.mp3")
    fc = tone_face(workdir, tone)
    with open(mp3, "rb") as f:
        key = hashlib.sha1(f.read() + json.dumps(fc, sort_keys=True).encode()
                           ).hexdigest()[:16]
    import sy_store as st
    vid = (st.kv_get("heygen_job_" + key) or {}).get("id") or ""
    if vid:
        log("ye tukda pehle bhi bheja tha - wahi video:", vid)
        return vid
    audio = upload_asset(mp3, "audio/mpeg")
    kw = {"res": reel_resolution(), "motion_prompt": TONE_MOTION.get(tone, ""),
          "expressiveness": TONE_EXPRESS.get(tone, "low")}
    try:
        vid = create_video(audio, fc, title, **kw)
    except HeyGenError as e:
        if fc["kind"] != "image" or "asset" not in str(e).lower():
            raise
        fc = dict(face(workdir, fresh=True), tone=tone)
        vid = create_video(audio, fc, title, **kw)
    note_used(secs)
    st.kv_set("heygen_job_" + key, {"id": vid, "at": time.time()})
    log("HeyGen tukda (%s, %.1fs, %s) - video %s; aaj %.0f/%.0f sec"
        % (tone, secs, "look" if fc.get("kind") == "avatar" and look_for(tone)
           else fc["kind"], vid, used_seconds_today(), max_minutes_per_day() * 60))
    return vid


def fetch_clip(video_id, out_path, want_secs, minutes):
    """Taiyaar hone tak ruko aur utaaro. (path, cx) ya ("", wajah)."""
    url, dur = wait(video_id, minutes)
    if not url:
        return "", dur
    sy_net.download(url, out_path, max_bytes=300 * 1024 * 1024, timeout=600)
    got = _media_dur(out_path)
    if got and abs(got - want_secs) > 1.5:
        return "", "%.1fs ki aayi, %.1fs chahiye thi" % (got, want_secs)
    return out_path, _person_x(out_path)


# ----------------------------------------------------------- aawaaz ke tukde

def _wav_dur(path):
    with wave.open(path, "rb") as w:
        return w.getnframes() / float(w.getframerate() or 1)


def pieces_for(ranges, lead, vdur):
    """Edit ki ranges (video ke samay mein) -> aawaaz ke tukde.

    Har tukda: {"va", "vb" (voice.wav mein), "off" (HeyGen video mein
    shuruaat), "s", "e" (video mein), "spans": [(s, e, mode)]}."""
    out, cum = [], 0.0
    for s, e, spans in ranges:
        va = max(0.0, s - lead - PAD)
        vb = min(vdur, e - lead + PAD)
        if vb - va < 0.5:
            continue
        out.append({"va": round(va, 3), "vb": round(vb, 3), "off": round(cum, 3),
                    "s": s, "e": e, "spans": list(spans)})
        cum += (vb - va) + GAP
    return out


def billed_seconds(pieces):
    if not pieces:
        return 0.0
    return sum(p["vb"] - p["va"] for p in pieces) + GAP * (len(pieces) - 1)


def build_audio(voice, pieces, out_wav):
    """voice.wav ke tukde + beech ki chuppi -> ek WAV (seedha, bina ffmpeg)."""
    with wave.open(voice, "rb") as src:
        prm = src.getparams()
        rate = src.getframerate()
        frames = src.readframes(src.getnframes())
    step = prm.nchannels * prm.sampwidth
    gap = b"\x00" * (int(rate * GAP) * step)
    with wave.open(out_wav, "wb") as dst:
        dst.setparams(prm)
        for k, p in enumerate(pieces):
            if k:
                dst.writeframes(gap)
            a, b = int(p["va"] * rate) * step, int(p["vb"] * rate) * step
            dst.writeframes(frames[a:b])
    return out_wav


def _to_mp3(wav, mp3):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", wav, "-ac", "1", "-ar", "44100", "-b:a", "96k", mp3],
                   check=True, timeout=120)
    return mp3


def trim_to(ranges, secs):
    """Ranges ko kul 'secs' tak seemit - peeche se katao (hook bachta hai)."""
    out, used = [], 0.0
    for s, e, spans in ranges:
        d = e - s + 2 * PAD + (GAP if out else 0.0)
        if used + d <= secs:
            out.append((s, e, spans))
            used += d
    return out


# ----------------------------------------------------------- bahar ka

def plan(story, shots, workdir, lead, long=False):
    """RENDER SE PEHLE (sy_scenes.plan ke baad): edit decision + HeyGen ko
    aawaaz bhej do. dict lauta ta hai (finish() ke liye), ya None.

    Isi ke baad sy_scenes.build chalta hai - HeyGen usi beech apna kaam karta
    hai. Kabhi throw nahi."""
    try:
        ok, why = ready(story)
        if not ok:
            log("anchor nahi:", why)
            return None
        if not shots or len(shots) < 2:
            return None
        import sy_edit
        voice = os.path.join(workdir, "voice.wav")
        vdur = _wav_dur(voice)
        cap = min(max_seconds(long), room_seconds())
        modes = sy_edit.decide(shots, story, max_total=cap,
                               max_share=max_share(long), max_run=max_run(),
                               use_ai=ai_edit())
        log("edit:", sy_edit.describe(shots, modes))
        rngs = trim_to(sy_edit.ranges(shots, modes), cap)
        pieces = pieces_for(rngs, lead, vdur)
        secs = billed_seconds(pieces)
        if secs < MIN_SECONDS:
            log("anchor ka hissa bahut chhota (%.1fs) - is video mein nahi" % secs)
            return None

        cfg.put_ffmpeg_on_path()
        wav = build_audio(voice, pieces, os.path.join(workdir, "heygen_voice.wav"))
        mp3 = _to_mp3(wav, os.path.join(workdir, "heygen_voice.mp3"))

        fc = face(workdir)
        with open(mp3, "rb") as f:
            key = hashlib.sha1(f.read() + json.dumps(fc).encode()).hexdigest()[:16]
        import sy_store as st
        # Wahi aawaaz + wahi chehra pehle bhej chuke (beech mein run giri, ya
        # video dobara ban rahi hai) - to dobara paisa nahi, wahi video.
        vid = (st.kv_get("heygen_job_" + key) or {}).get("id") or ""
        if vid:
            log("ye aawaaz pehle bhi bheji thi - wahi HeyGen video:", vid)
        else:
            audio = upload_asset(mp3, "audio/mpeg")
            try:
                vid = create_video(audio, fc, story.get("story_id") or "")
            except HeyGenError as e:
                if fc["kind"] != "image" or "asset" not in str(e).lower():
                    raise
                # Purani tasveer ka asset shayad mit gaya - ek baar nayi.
                fc = face(workdir, fresh=True)
                vid = create_video(audio, fc, story.get("story_id") or "")
            note_used(secs)
            st.kv_set("heygen_job_" + key, {"id": vid, "at": time.time()})
            log("HeyGen ko %.1fs ki aawaaz bheji (%s) - video %s; aaj %.0f/%.0f sec"
                % (secs, fc["kind"], vid, used_seconds_today(),
                   max_minutes_per_day() * 60))
        for p in ("heygen_voice.wav",):
            try:
                os.remove(os.path.join(workdir, p))
            except Exception:
                pass
        return {"video_id": vid, "pieces": pieces, "seconds": secs,
                "modes": modes, "lead": lead, "submitted": time.time()}
    except Exception as e:
        log("HeyGen anchor nahi (bina uske aage):", str(e)[:300])
        return None


def wait(video_id, minutes):
    """Video taiyaar hone tak (ya minutes tak). (url, duration) ya ("", wajah)."""
    t_end = time.time() + minutes * 60.0
    last = ""
    while True:
        try:
            d = video_status(video_id)
        except HeyGenError as e:
            d, last = {}, str(e)
            log("haal nahi mila:", last[:150])
        stt = str(d.get("status") or "")
        if stt == "completed" and d.get("video_url"):
            return d["video_url"], float(d.get("duration") or 0)
        if stt == "failed":
            why = "HeyGen fail: %s %s" % (d.get("failure_code") or "",
                                         d.get("failure_message") or "")
            if is_credit_error(why):
                note_credit_error(why)
            return "", why
        if time.time() >= t_end:
            return "", "%d minute mein taiyaar nahi (%s)" % (minutes, stt or last)
        time.sleep(15)


def finish(plan_, workdir, minutes=None):
    """RENDER SE THEEK PEHLE: HeyGen video utaaro aur render ke liye
    khidkiyon ki list banao. [] = anchor nahi (video bina anchor ke).
    Kabhi throw nahi."""
    if not plan_:
        return []
    try:
        left = wait_minutes() - (time.time() - plan_.get("submitted", time.time())) / 60.0
        mins = minutes if minutes is not None else max(1.0, left)
        url, dur = wait(plan_["video_id"], mins)
        if not url:
            log("anchor nahi lagi:", dur)
            return []
        clip = os.path.join(workdir, "heygen.mp4")
        sy_net.download(url, clip, max_bytes=400 * 1024 * 1024, timeout=600)
        got = _media_dur(clip)
        want = billed_seconds(plan_["pieces"])
        if got and abs(got - want) > 1.5:
            log("HeyGen video %.1fs ki aayi, %.1fs chahiye thi - hont nahi milenge, "
                "anchor nahi" % (got, want))
            return []
        cx = _person_x(clip)
        lead = float(plan_["lead"])
        ovs = []
        for p in plan_["pieces"]:
            for s, e, mode in p["spans"]:
                # Video ka lamha t = voice.wav ka (t - lead); us tukde mein
                # wo HeyGen video ke off + (t - lead - va) par hai.
                off = p["off"] + (s - lead - p["va"])
                ovs.append({"file": clip, "off": round(max(0.0, off), 3),
                            "start": s, "end": e, "mode": mode, "cx": cx})
        log("%d anchor khidkiyan (%s)" % (len(ovs), ", ".join(
            "%s %.1f-%.1f" % (o["mode"], o["start"], o["end"]) for o in ovs)))
        return ovs
    except Exception as e:
        log("anchor video nahi utri (bina anchor ke aage):", str(e)[:300])
        return []


def _media_dur(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60)
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _person_x(clip):
    try:
        import sy_explainer
        return sy_explainer._person_x(clip)
    except Exception:
        return 0.6


def adjust_credits(credits, overlays):
    """Full anchor ke dauran footage ka credit nahi (footage dikh hi nahi rahi),
    aur har anchor khidki par 'AI प्रस्तुतकर्ता' - poori imaandari."""
    if not overlays:
        return credits
    fulls = [(o["start"], o["end"]) for o in overlays if o["mode"] == "anchor"]
    out = []
    for a, b, c in credits or []:
        pieces = [(float(a), float(b))]
        for fa, fb in fulls:
            nxt = []
            for x, y in pieces:
                if fb <= x or fa >= y:
                    nxt.append((x, y))
                    continue
                if x < fa:
                    nxt.append((x, fa))
                if fb < y:
                    nxt.append((fb, y))
            pieces = nxt
        out += [(x, y, c) for x, y in pieces if y - x > 0.8]
    for fa, fb in fulls:
        out.append((fa, fb, CREDIT))
    return sorted(out)


def cleanup(workdir):
    """HeyGen ki clip aur aawaaz render ke baad turant hatao - media cache
    (work/ bhi usme jaata hai) na badhe."""
    for n in ("heygen.mp4", "heygen_voice.mp3", "heygen_voice.wav"):
        try:
            os.remove(os.path.join(workdir, n))
        except Exception:
            pass


def desc_line():
    return ("इस वीडियो में दिखने वाली प्रस्तुतकर्ता AI-जनित है (कोई वास्तविक "
            "व्यक्ति नहीं); आवाज़ के साथ होंठ HeyGen से मिलाए गए हैं।")


def status_text():
    """/heygen ke liye haal."""
    on = enabled()
    rows = ["<b>HeyGen anchor (lip-sync): %s</b>" % ("CHALU" if on else "BAND")]
    rows.append("Chaabi: %s" % ("hai" if api_key() else "NAHI (HEYGEN_API_KEY Secret)"))
    if credit_blocked():
        rows.append("<b>API credit KHATAM</b> - billing mein bhariye, phir /heygen on")
    rows.append("Chehra: %s" % ("dashboard avatar (HEYGEN_AVATAR_ID)" if avatar_id()
                                else "presenter ki tasveer (image)"))
    rows.append("Fatafat Reel ke look (gambhir/neutral/muskaan): %s" % (
        "teeno" if looks_ready() else ", ".join(t for t in TONES if look_for(t)) or "nahi"))
    rows.append("Aaj: %.0f / %.0f second"
                % (used_seconds_today(), max_minutes_per_day() * 60))
    rows.append("Har video: chhoti %.0fs, lambi %.0fs tak"
                % (max_seconds(False), max_seconds(True)))
    if not on:
        rows.append("")
        rows.append("Chalu karne ke liye: <code>/heygen on</code>")
    return "\n".join(rows)

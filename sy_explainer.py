"""Jaankari wali videos (yojana / kaam / gyan / tech) ke shuru aur ant mein
wahi AI anchor - Harshvardhan ko end-card wali presenter pasand aayi, aur
maang thi ki yahi jaankari samjhaaye (retention ke liye).

EK VIDEO, EK CHEHRA - ISLIYE EK HI VEO CLIP
===========================================
Veo har naye clip mein naya chehra bana deta hai. Shuru aur ant ke liye do
alag clip banwaate to ek hi video mein do alag ladkiyan aa sakti thin - aur
Harshvardhan ka saaf niyam hai: "same video mein doosra chehra nahi aana
chahiye" (alag video mein alag chehra chal jaayega).

Isliye har video ke liye EK hi 8 second ka clip banta hai jismein anchor
pehle namaskar/vishay wali line bolti hai, ek pal rukti hai, phir
like/subscribe wali line. Us chuppi par clip ko do tukdon mein kaat dete
hain:
    shuru ka tukda -> mukhya video se PEHLE
    vida ka tukda  -> end-card ke peeche (roz wali presenter ki jagah - warna
                      wahi "doosra chehra" ho jaata)
Chuppi na mile to anchor is video mein lagti hi nahi - video pehle jaisi.

CHEHRA KAISE TIKTA HAI
======================
1. Pehle koshish: end-card presenter (jo pasand aayi) ki clip ka ek frame
   image-to-video mein bhejte hain - sab videos mein bilkul wahi chehra.
   ANCHOR.md ke mutaabik Veo photoreal chehre wali tasveer aksar rok deta
   hai; roke to ye yaad rakh lete hain aur aage se seedha doosra rasta.
2. Doosra rasta: sirf prompt se - FACE mein chehre ki banaavat bahut
   baareeki se likhi hai (usi pasand aayi presenter ko dekh kar), taaki har
   baar lagbhag wahi ladki bane. Bilkul hubahu ki guarantee nahi - par ek
   video ke andar ek hi clip hai, isliye ek hi chehra.

Beech ki script ki aawaaz TTS (Sarvam/ElevenLabs) ki hi rehti hai - anchor
sirf shuru aur ant mein (Harshvardhan ka chunaav, kharch kam rakhne ke liye).

KABHI NAHI ROKTA
================
make() kabhi throw nahi karta. Kuch bhi gadbad (kota, Veo mana, chuppi na
mile) to ("", "") aur video bina anchor ke, pehle ki tarah.
"""
import base64
import os
import re
import subprocess
import time

import sy_config as cfg

BEATS = ("yojana", "kaam", "gyan", "tech")

INTRO = {
    "yojana": "नमस्ते! आज एक बहुत काम की सरकारी योजना को आसान भाषा में समझते हैं।",
    "kaam": "नमस्ते! आज आपके काम की एक ज़रूरी बात, बिल्कुल आसान भाषा में।",
    "gyan": "नमस्ते! आज एक बड़ी दिलचस्प बात जानते हैं, ध्यान से सुनिए।",
    "tech": "नमस्ते! आज तकनीक की एक आसान सी बात समझते हैं, जो आपके काम आएगी।",
}
OUTRO = "अच्छा लगा हो तो लाइक, सब्सक्राइब और शेयर ज़रूर कीजिए!"

# Chehre ki banaavat - end-card wali presenter ko dekh kar likhi hai. Har
# shabd jaan-boojhkar hai: jitna baareek vivran, utna hi har baar milta-
# julta chehra.
FACE = (
    "a young Indian woman news presenter, about 25 years old, with an oval "
    "face and soft rounded jawline, warm medium wheatish-brown skin with "
    "natural texture, large expressive dark-brown almond-shaped eyes, "
    "well-defined naturally arched dark eyebrows, a straight medium nose, "
    "full lips with rose-pink lipstick and a bright, friendly smile showing "
    "her upper teeth, long straight dark-brown hair with a centre parting "
    "falling well past her shoulders, small gold jhumka earrings, a "
    "mustard-yellow cotton kurta with a thin white piping at the neckline, "
    "a cream-coloured dupatta draped over both shoulders, and a small black "
    "lapel microphone clipped to the kurta"
)

STUDIO = (
    "a modern bright TV news studio, softly blurred, with blue LED light "
    "strips, round ceiling spotlights and blue screens in the background"
)

TAIL = (
    "Static camera, medium shot from the waist up, she stands slightly to "
    "the right of centre, broadcast lighting, shallow depth of field, "
    "natural skin texture. She is an ORIGINAL fictional person, not based "
    "on and not resembling any real, living or famous person. No on-screen "
    "text, no captions, no subtitles, no logos, no watermark, absolutely no "
    "TV channel logo, channel name or 'HD' mark in any corner. No background "
    "music - only her voice and quiet studio ambience."
)


def log(*a):
    print("[explainer]", *a, flush=True)


def _assets():
    return os.path.join(cfg.HERE, "assets")


def enabled():
    return cfg.num("explainer", "enabled", 1) == 1


def max_per_day():
    return cfg.num("explainer", "max_per_day", 6)


def _mode():
    return (cfg.get("explainer", "mode") or "auto").strip().lower()


def _room_left():
    import sy_store as st
    today = time.strftime("%Y-%m-%d")
    if st.kv_get("explainer_day", "") != today:
        return max_per_day()
    return max(0, max_per_day() - int(st.kv_get("explainer_count", 0) or 0))


def _note_used():
    import sy_store as st
    today = time.strftime("%Y-%m-%d")
    if st.kv_get("explainer_day", "") != today:
        st.kv_set("explainer_day", today)
        st.kv_set("explainer_count", 0)
    st.kv_set("explainer_count", int(st.kv_get("explainer_count", 0) or 0) + 1)


# ------------------------------------------------------------ prompts

def _speech(intro, outro):
    return (
        "She looks straight into the camera and speaks clear, warm, "
        "friendly Hindi, like a kind teacher. First she says: \"%s\" Then "
        "she stops speaking and stays silent for one full second with a "
        "gentle smile. Then she says: \"%s\" and gives a small thumbs-up. "
        % (intro.replace('"', "'"), outro.replace('"', "'")))


def _text_prompt(intro, outro):
    return ("Photorealistic video of %s, in %s. %s%s"
            % (FACE, STUDIO, _speech(intro, outro), TAIL))


def _image_prompt(intro, outro):
    return ("The woman in the image, exactly as she looks in the image - "
            "same face, hair, clothes and studio. %s"
            "Keep her face, hair and outfit identical to the image. %s"
            % (_speech(intro, outro), TAIL))


def _reference_b64(workdir):
    """End-card presenter ka ek saaf frame (kone ke logo par apna badge)."""
    import sy_endcard
    src = sy_endcard.presenter_path()
    if not sy_endcard._ok_file(src, 200000):
        return ""
    out = os.path.join(workdir, "explainer_ref.jpg")
    badge = os.path.join(_assets(), sy_endcard.BADGE[0])
    try:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
               "-ss", "0.3", "-i", src]
        if sy_endcard._ok_file(badge, 1000):
            cmd += ["-i", badge, "-filter_complex",
                    "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                    "crop=1920:1080[b];[b][1:v]overlay=%d:%d"
                    % (sy_endcard.BADGE[1], sy_endcard.BADGE[2])]
        else:
            cmd += ["-vf", "scale=1920:1080:force_original_aspect_ratio=increase,"
                           "crop=1920:1080"]
        cmd += ["-frames:v", "1", "-q:v", "3", out]
        subprocess.run(cmd, check=True, timeout=60)
        with open(out, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        log("reference frame nahi nikla:", e)
        return ""


def _make_clip(beat, workdir):
    """(clip_path, tareeka) ya ("", wajah)."""
    import sy_anchor
    import sy_store as st
    intro = INTRO.get(beat) or INTRO["gyan"]
    clip = os.path.join(workdir, "explainer_raw.mp4")
    mode = _mode()

    try_image = mode in ("auto", "image") and not (
        mode == "auto" and st.kv_get("explainer_img_blocked"))
    if try_image:
        b64 = _reference_b64(workdir)
        if b64:
            log("anchor clip - pasand aayi presenter ki tasveer se (image-to-video)...")
            ok, why = sy_anchor.veo_person_clip(_image_prompt(intro, OUTRO), clip,
                                                image_b64=b64, resolution="1080p")
            if ok:
                return clip, "image"
            log("tasveer se nahi bana:", str(why)[:200])
            low = str(why).lower()
            if ("guideline" in low or "violat" in low or "person" in low
                    or "video nahi mili" in low):
                # Veo ka categorical rok - baar-baar koshish sirf samay khaati.
                st.kv_set("explainer_img_blocked", 1)
                log("aage se seedha prompt wala rasta (image mode yaad rakha: rok)")
        if mode == "image":
            return "", "image mode mein nahi bana"

    log("anchor clip - sirf prompt se, chehre ke baareek vivran ke saath...")
    ok, why = sy_anchor.veo_person_clip(_text_prompt(intro, OUTRO), clip,
                                        resolution="1080p")
    if ok:
        return clip, "text"
    return "", str(why)


# ------------------------------------------------------------ katna

def _silences(path, noise=-34, dur=0.30):
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
         "-af", "silencedetect=noise=%ddB:d=%.2f" % (noise, dur),
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=120)
    txt = out.stderr or ""
    starts = [float(x) for x in re.findall(r"silence_start:\s*([\d.]+)", txt)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", txt)]
    return list(zip(starts, ends))


def _split_point(path):
    """Beech ki sabse lambi chuppi ka madhya. None = nahi mili.

    PEHLE SIRF EK NAAP (-34 dB, 0.30s) THA - AUR WO CHOOK GAYA (Sep 2026)
    Time-zone wali video ke clip mein anchor 4.06-4.50s par saaf rukti hai
    (awaaz -46 se -61 dB), par us chuppi ke kinaare -35 dB ke aas-paas the,
    isliye -34 dB wala naap use chuppi maana hi nahi. Nateeja: Veo ka clip
    ban gaya (paisa laga), par video aur thumbnail dono mein anchor nahi
    lagi. Ab teen naap baari-baari - sakht se dheele tak - aur sirf beech
    ke hisse (shuru ke 2 sec aur aakhri 1.5 sec chhod kar) ki chuppi."""
    import sy_endcard
    total = sy_endcard._duration(path)
    for noise, dur in ((-34, 0.30), (-30, 0.25), (-27, 0.22)):
        best, best_len = None, 0.0
        for a, b in _silences(path, noise, dur):
            mid = (a + b) / 2.0
            if mid < 2.0 or mid > total - 1.5:
                continue
            if b - a > best_len:
                best, best_len = mid, b - a
        if best is not None:
            if noise != -34:
                log("chuppi %d dB naap par mili (%.2fs)" % (noise, best))
            return best
    return None


def _cut(src, a, b, out, workdir, W, H, rate, ch, fade_in=False):
    """src ka [a, b) hissa - badge + 'AI प्रस्तुतकर्ता' label ke saath,
    mukhya video ke naap/format mein."""
    import sy_endcard
    label = sy_endcard._write_label(workdir, W, H)
    badge = os.path.join(_assets(), sy_endcard.BADGE[0])
    dur = max(0.5, b - a)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-ss", "%.3f" % a, "-t", "%.3f" % dur, "-i", src]
    filt = ["[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,setsar=1[v0]"]
    if sy_endcard._ok_file(badge, 1000):
        cmd += ["-loop", "1", "-i", badge]
        filt.append("[v0][1:v]overlay=%d:%d:shortest=1[v1]"
                    % (sy_endcard.BADGE[1], sy_endcard.BADGE[2]))
    else:
        filt.append("[v0]null[v1]")
    filt.append("[v1]scale=%d:%d,fps=%d,ass=%s%s,format=yuv420p[vout]"
                % (W, H, sy_endcard.FPS, label,
                   ",fade=t=in:st=0:d=0.3" if fade_in else ""))
    layout = "stereo" if ch >= 2 else "mono"
    filt.append("[0:a]aresample=%d,aformat=sample_rates=%d:channel_layouts=%s,"
                "afade=t=out:st=%.2f:d=0.15[aout]"
                % (rate, rate, layout, max(0.0, dur - 0.15)))
    cmd += ["-filter_complex", ";".join(filt), "-map", "[vout]", "-map", "[aout]",
            "-t", "%.3f" % dur,
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-maxrate", "2400k", "-bufsize", "5000k",
            "-pix_fmt", "yuv420p", "-r", str(sy_endcard.FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", str(rate), "-ac", str(ch),
            "-movflags", "+faststart", out]
    subprocess.run(cmd, cwd=workdir, check=True, timeout=300)
    return out if sy_endcard._ok_file(out, 20000) else ""


# ------------------------------------------------------------ thumbnail

THUMB_STILL = "anchor_thumb.jpg"
# thumb.py mein anchor daayein 50% (640x720) mein baithti hai - wahi anupat.
STILL_ASPECT = 640.0 / 720.0


def _person_x(clip, W=480):
    """Frame mein anchor kahan khadi hai (0..1). Peeche ka studio sthir hai,
    wo hilti-bolti hai - kuch frame ka farak jodne par jahan sabse zyada
    halchal hai, wahi wo hai. Sirf PIL, koi naya package nahi."""
    from PIL import Image, ImageChops
    import tempfile
    d = tempfile.mkdtemp(prefix="expl_")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", clip, "-vf", "fps=2,scale=%d:-2,format=gray" % W,
                    os.path.join(d, "m%02d.png")], check=True, timeout=120)
    frames = sorted(f for f in os.listdir(d) if f.endswith(".png"))
    acc = None
    for a, b in zip(frames, frames[1:]):
        ia = Image.open(os.path.join(d, a))
        ib = Image.open(os.path.join(d, b))
        diff = ImageChops.difference(ia, ib)
        acc = diff if acc is None else ImageChops.add(acc, diff)
    import shutil
    shutil.rmtree(d, ignore_errors=True)
    if acc is None:
        return 0.6
    col = acc.resize((acc.size[0], 1), Image.BOX)
    vals = list(col.getdata())
    tot = float(sum(vals))
    if tot <= 0:
        return 0.6
    cx = sum(i * v for i, v in enumerate(vals)) / tot / len(vals)
    return max(0.2, min(0.8, cx))


def _still_at(clip, t, cx, workdir, name="anchor_frame.png"):
    """Clip ke 't' second ka frame, thumbnail ke daayein panel ke naap mein."""
    frame = os.path.join(workdir, name)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-ss", "%.3f" % max(0.0, t), "-i", clip, "-frames:v", "1",
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=increase,"
                           "crop=1920:1080", frame], check=True, timeout=60)
    from PIL import Image
    im = Image.open(frame).convert("RGB")
    ch = int(im.size[1] * 0.86)          # upar se - chehra bada dikhe
    cw = int(ch * STILL_ASPECT)
    left = int(cx * im.size[0] - cw / 2)
    left = max(0, min(im.size[0] - cw, left))
    return im.crop((left, 0, left + cw, ch))


def thumb_still(clip, at, workdir):
    """workdir/anchor_thumb.jpg - anchor ka kamar-se-upar hissa, thumbnail
    ke daayein panel ke anupat mein kata hua.

    AANKH KHULI HO (Sep 2026, Harshvardhan: "thumbnail mein aankhein band
    wali ladki nahi chalegi" - Konark wali thumbnail). Pehle frame theek
    'at' par liya jaata tha - yaani do line ke beech ki CHUPPI par, jo
    thik wahi lamha hai jab anchor muskura kar palak jhapkati/aankh moondti
    hai. Ab chuppi se hat kar 6 lamhe liye jaate hain, ek jaal (1-6) mein
    Claude ko dikhaye jaate hain, aur wahi chuna jaata hai jismein aankhein
    saaf khuli aur camera ki taraf hon. Jaanch na ho paaye to chuppi se
    0.8s pehle wala (bolte hue) frame - chuppi wala kabhi nahi."""
    cx = _person_x(clip)
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", clip],
            capture_output=True, text=True, timeout=60)
        dur = float((out.stdout or "0").strip() or 0)
    except Exception:
        dur = 0.0
    hi = max(0.4, dur - 0.4) if dur else at + 1.5
    ts = [min(hi, max(0.4, at + d)) for d in (-0.8, -1.6, 0.8, 1.6, -2.4, 2.4)]
    picks = []
    for k, t in enumerate(ts):
        try:
            picks.append(_still_at(clip, t, cx, workdir, "anchor_cand%d.png" % k))
        except Exception:
            pass
    if not picks:
        raise RuntimeError("anchor ka koi frame nahi nikla")
    best = 0
    try:
        from PIL import Image, ImageDraw
        tw, th = 320, 360
        grid = Image.new("RGB", (tw * 3, th * 2), (0, 0, 0))
        for k, im in enumerate(picks):
            g = im.resize((tw, th))
            dr = ImageDraw.Draw(g)
            dr.rectangle([0, 0, 56, 56], fill=(200, 16, 46))
            try:
                from PIL import ImageFont
                fnt = ImageFont.load_default(size=40)
            except Exception:
                fnt = None
            dr.text((16, 6), str(k + 1), fill=(255, 255, 255), font=fnt)
            grid.paste(g, ((k % 3) * tw, (k // 3) * th))
        gp = os.path.join(workdir, "anchor_cands.jpg")
        grid.save(gp, quality=88)
        import sy_ai
        j = sy_ai.ask_vision_json(
            "Aap ek news channel ke thumbnail editor hain. Sirf JSON lautaiye.",
            "Is jaal mein ek hi anchor ke %d frame hain, har ek par laal "
            "dabbe mein number. YouTube thumbnail ke liye sabse achha frame "
            "chuniye: DONO AANKHEIN SAAF KHULI hon, camera ki taraf dekh "
            "rahi ho, chehra dhundhla na ho. Aankh band/aadhi band ya "
            "palak jhapakta frame kabhi nahi. Koi bhi theek na ho to 0. "
            'JSON: {"best": number, "reason": "chhota karan"}' % len(picks),
            gp, max_tokens=120)
        n = int((j or {}).get("best") or 0)
        if 1 <= n <= len(picks):
            best = n - 1
        else:
            log("thumbnail: vision ko khuli aankh wala frame nahi mila (%s)"
                % str((j or {}).get("reason") or "")[:80])
    except Exception as e:
        log("thumbnail frame ki vision jaanch nahi hui (bolte hue frame liya):", e)
    picks[best].save(os.path.join(workdir, THUMB_STILL), quality=92)
    log("thumbnail ke liye anchor ki tasveer (x=%.2f, t=%.2fs)" % (cx, ts[best]))


# ------------------------------------------------- beech ki lines (Sep 2026)
#
# Harshvardhan: "jahan asli footage na mile, wahan ladki baaki ki lines
# bole." sy_media.fetch_shots() aise tukdon par "anchor_planned" ka nishan
# lagata hai (AI chitran ka paisa nahi lagata). Render ke baad yahan har
# aise tukde ke liye usi video wali anchor ka ek naya clip banta hai jismein
# wo usi tukde ki line apni aawaaz mein bolti hai, aur mukhya video ke us
# hisse (TTS aawaaz + studio) ki jagah wahi clip jud jaata hai.
#
# EK VIDEO, EK CHEHRA: ye clip HAMESHA image-to-video se banta hai, aur
# tasveer is video ke apne shuru wale anchor clip ka frame hoti hai - sirf
# prompt se banane par Veo naya chehra bana deta. Tasveer se na bane to wo
# tukda studio par hi chalta hai, kisi aur chehre ke saath kabhi nahi.
#
# Dhyaan: in hisson mein aawaaz Veo anchor ki hoti hai, baaki script ki TTS
# ki - ye Harshvardhan ka chuna hua samjhauta hai.

LINE_MAX_CHARS = 105      # ~8 sec mein itna Hindi aaraam se bola jaata hai


def max_line_clips():
    return cfg.num("explainer", "max_line_clips", 3)


def line_slots(story):
    """fetch_shots se pehle: kitne khaali tukde anchor ke liye rakhne hain.
    Sasta - koi API nahi, sirf switch/kota/beat."""
    try:
        if str(story.get("beat") or "") not in BEATS or not enabled():
            return 0
        import sy_anchor
        if not sy_anchor.sa_path():
            return 0
        # 1 clip shuru/vida ka + baaki lines ke
        return max(0, min(max_line_clips(), _room_left() - 1))
    except Exception:
        return 0


def _frame_b64(clip, at, workdir, name="line_ref.jpg"):
    import sy_endcard
    out = os.path.join(workdir, name)
    badge = os.path.join(_assets(), sy_endcard.BADGE[0])
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-ss", "%.3f" % max(0.0, at), "-i", clip]
    if sy_endcard._ok_file(badge, 1000):
        cmd += ["-i", badge, "-filter_complex",
                "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                "crop=1920:1080[b];[b][1:v]overlay=%d:%d"
                % (sy_endcard.BADGE[1], sy_endcard.BADGE[2])]
    else:
        cmd += ["-vf", "scale=1920:1080:force_original_aspect_ratio=increase,"
                       "crop=1920:1080"]
    cmd += ["-frames:v", "1", "-q:v", "3", out]
    subprocess.run(cmd, check=True, timeout=60)
    with open(out, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def _line_prompt(text):
    return ("The woman in the image, exactly as she looks in the image - "
            "same face, hair, clothes and studio. She looks into the camera "
            "and, starting right away, explains in clear, warm, natural Hindi "
            "at a normal conversational pace, like a kind teacher: \"%s\" "
            "Then she smiles and stays silent. Keep her face, hair and outfit "
            "identical to the image. %s" % (text.replace('"', "'"), TAIL))


def _speech_span(path):
    """(bolna shuru, bolna khatam) second mein - aage-peechhe ki chuppi hata kar."""
    import sy_endcard
    total = sy_endcard._duration(path)
    a, b = 0.0, total
    for s0, s1 in _silences(path, -32, 0.25):
        if s0 <= 0.05:
            a = max(a, s1 - 0.12)
        if s1 >= total - 0.05:
            b = min(b, s0 + 0.25)
    if b - a < 1.0:
        return 0.0, total
    return a, b


def _snap(t, sil, lead, win=0.7):
    """t ko aawaaz ki sabse paas wali chuppi par khiskao (vaakya ke beech na kate)."""
    best, bd = t, win
    for s0, s1 in sil:
        m = lead + (s0 + s1) / 2.0
        if abs(m - t) < bd:
            best, bd = m, abs(m - t)
    return best


def _speak_lines(story, video_path, workdir, prep, W, H, rate, ch):
    """Anchor_planned tukdon ki jagah anchor ke bolte clip. Kitne jude, lauta ta hai."""
    import json as _json
    import render_core
    import sy_anchor
    import sy_endcard
    try:
        shots = _json.loads(story.get("shots") or "[]")
    except Exception:
        return 0
    want = [sh for sh in shots if sh.get("anchor_planned") and not sh.get("file")]
    if not want:
        return 0
    lead = float(prep.get("lead") or render_core.LEAD)
    voice = os.path.join(workdir, "voice.wav")
    vdur = sy_endcard._duration(voice)
    sil = _silences(voice, -30, 0.15) if os.path.exists(voice) else []
    ref = _frame_b64(prep["clip"], 0.3, workdir)

    repl = []      # (s, e, segment_path)
    for n, sh in enumerate(want):
        if _room_left() <= 0:
            log("aaj ka anchor kota poora - baaki lines studio par")
            break
        text = re.sub(r"\s+", " ", str(sh.get("text") or "")).strip()
        if not text or len(text) > LINE_MAX_CHARS:
            log("line bahut lambi/khaali (%d akshar) - studio par" % len(text))
            continue
        raw = os.path.join(workdir, "line%d_raw.mp4" % n)
        ok, why = sy_anchor.veo_person_clip(_line_prompt(text), raw,
                                            image_b64=ref, resolution="1080p")
        if not ok:
            log("line clip nahi bani (studio par):", str(why)[:150])
            continue
        _note_used()
        a, b = _speech_span(raw)
        seg = _cut(raw, a, b, os.path.join(workdir, "line%d.mp4" % n),
                   workdir, W, H, rate, ch)
        if not seg:
            continue
        s = _snap(float(sh.get("start") or 0), sil, lead)
        e = _snap(float(sh.get("end") or 0), sil, lead)
        e = min(e, lead + vdur + 0.2)
        if e - s < 0.8:
            continue
        repl.append((s, e, seg))
        log("anchor line %d: %.1f-%.1fs ki jagah %.1fs ka clip" % (n + 1, s, e, b - a))
    if not repl:
        return 0

    repl.sort()
    # Ek hi ffmpeg: mukhya video ke tukde + anchor clip, baari-baari.
    total = sy_endcard._duration(video_path)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", video_path]
    filt, labels, k, t = [], [], 0, 0.0
    for idx, (s, e, seg) in enumerate(repl):
        if s - t > 0.05:
            filt.append("[0:v]trim=start=%.3f:end=%.3f,setpts=PTS-STARTPTS[v%d];"
                        "[0:a]atrim=start=%.3f:end=%.3f,asetpts=PTS-STARTPTS[a%d]"
                        % (t, s, k, t, s, k))
            labels.append("[v%d][a%d]" % (k, k))
            k += 1
        cmd += ["-i", seg]
        filt.append("[%d:v]setpts=PTS-STARTPTS[v%d];[%d:a]asetpts=PTS-STARTPTS[a%d]"
                    % (idx + 1, k, idx + 1, k))
        labels.append("[v%d][a%d]" % (k, k))
        k += 1
        t = e
    if total - t > 0.05:
        filt.append("[0:v]trim=start=%.3f,setpts=PTS-STARTPTS[v%d];"
                    "[0:a]atrim=start=%.3f,asetpts=PTS-STARTPTS[a%d]" % (t, k, t, k))
        labels.append("[v%d][a%d]" % (k, k))
        k += 1
    filt.append("%sconcat=n=%d:v=1:a=1[vo][ao]" % ("".join(labels), k))
    out = os.path.join(workdir, "with_lines.mp4")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[vo]", "-map", "[ao]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-maxrate", "2400k", "-bufsize", "5000k",
            "-pix_fmt", "yuv420p", "-r", str(sy_endcard.FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", str(rate), "-ac", str(ch),
            "-movflags", "+faststart", out]
    subprocess.run(cmd, cwd=workdir, check=True, timeout=900)
    if not sy_endcard._ok_file(out, 100000):
        return 0
    import shutil
    shutil.copyfile(out, video_path)
    return len(repl)


# ------------------------------------------------------------ bahar ka

def prepare(story, workdir):
    """RENDER SE PEHLE: shuru/vida wala anchor clip bana lo.

    Pehle banana isliye ki render ko pata ho ki aage anchor judegi - tab
    wo channel ka title card nahi lagata (render_core.set_intro_mode), aur
    anchor ke "namaste..." ke turant baad asli baat shuru hoti hai.
    dict lauta ta hai, ya None. Kabhi throw nahi."""
    beat = str(story.get("beat") or "")
    if beat not in BEATS or not enabled():
        return None
    try:
        import sy_anchor
        if not sy_anchor.sa_path():
            log("service account nahi mili - anchor nahi")
            return None
        if _room_left() <= 0:
            log("aaj ka anchor kota poora - is video mein anchor nahi")
            return None
        cfg.put_ffmpeg_on_path()
        workdir = os.path.abspath(workdir)
        clip, how = _make_clip(beat, workdir)
        if not clip:
            log("anchor clip nahi bani:", how[:200])
            return None
        _note_used()
        cut = _split_point(clip)
        if cut is None:
            log("clip mein beech ki chuppi nahi mili - do line alag nahi ho "
                "sakti, is video mein anchor nahi")
            return None
        try:
            thumb_still(clip, cut, workdir)
        except Exception as e:
            log("thumbnail ki tasveer nahi nikli (thumbnail pehle jaisa):", e)
        return {"clip": clip, "cut": cut, "how": how}
    except Exception as e:
        log("anchor mein gadbad (bina anchor ke aage):", str(e)[:200])
        return None


def attach(story, video_path, workdir, prep):
    """RENDER KE BAAD: beech ki lines, phir aage shuru wala tukda.
    Vida wala tukda lauta ta hai (end-card ke peeche), ya "". Kabhi throw nahi."""
    if not prep:
        return ""
    try:
        import sy_endcard
        cfg.put_ffmpeg_on_path()
        workdir = os.path.abspath(workdir)
        video_path = os.path.abspath(video_path)
        W, H, rate, ch = sy_endcard._probe(video_path)
        if H > W:
            return ""
        clip, cut = prep["clip"], prep["cut"]
        total = sy_endcard._duration(clip)
        intro = _cut(clip, 0.0, cut, os.path.join(workdir, "explainer_intro.mp4"),
                     workdir, W, H, rate, ch)
        outro = _cut(clip, cut, total, os.path.join(workdir, "explainer_outro.mp4"),
                     workdir, W, H, rate, ch, fade_in=True)
        if not intro or not outro:
            return ""
        try:
            n = _speak_lines(story, video_path, workdir, prep, W, H, rate, ch)
            if n:
                log("%d line anchor ne boli" % n)
        except Exception as e:
            log("beech ki lines nahi judi (studio par hi):", str(e)[:200])
        joined = os.path.join(workdir, "with_explainer.mp4")
        if not sy_endcard._join(intro, video_path, joined, workdir):
            log("shuru ka tukda jud nahi paya - anchor nahi")
            return ""
        import shutil
        shutil.copyfile(joined, video_path)
        log("anchor laga (%s): shuru %.1fs, vida %.1fs" % (prep.get("how"), cut, total - cut))
        return outro
    except Exception as e:
        log("anchor mein gadbad (bina anchor ke aage):", str(e)[:200])
        return ""


def make(story, video_path, workdir):
    """Purana ek-kadam rasta (render ke baad sab kuch). Naya rasta:
    prepare() render se pehle, attach() baad mein - sy_produce yahi karta hai."""
    prep = prepare(story, workdir)
    if prep:
        import render_core
        prep["lead"] = render_core.LEAD
    return attach(story, video_path, workdir, prep)

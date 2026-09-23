"""Video ke ant mein Like / Subscribe / Share - animation, aur ho sake to
ek AI presenter jo khud haath se ishaara karke yahi kehti hai.

KYA JUDTA HAI
=============
Har video (render + bulletin anchor ke baad) ke aakhir mein ~8 second:

  peeche  : AI presenter ka clip (assets/endcard_presenter.mp4) - ya wo na
            ho to channel ka studio background (assets/studio_bg.mp4)
  upar    : "ख़बर अच्छी लगी?" + teen button jo baari-baari aate hain -
            लाइक करें -> सब्सक्राइब करें (+ ghanti) -> शेयर करें - aur ek
            ungli wala haath har button ko "dabata" hai.
            (assets/cta_16x9.mp4, assets/cta_9x16.mp4 - pehle se bani
            animation; upar rang, neeche alpha - render par jodi jaati hai.
            Icons: Google Material Icons, Apache-2.0.)
  aawaaz  : presenter ki apni aawaaz; presenter na ho to ek baar TTS se
            bani line (assets/endcard_voice.wav), aur wo bhi na ho to chup.

PRESENTER KAHAN SE AATI HAI - EK HI BAAR
========================================
Pehli video par (sirf ek baar) Veo se ek 8 second ka clip banta hai -
sirf PROMPT se (text-to-video), kisi tasveer se nahi. Wajah ANCHOR.md mein
likhi hai: Veo photoreal chehre wali tasveer ko image-to-video mein rok
deta hai, par prompt se ek kalpanik kirdaar banane par wo rok nahi hai.
Ye kirdaar kisi asli vyakti jaisa nahi hai (prompt mein saaf likha hai).

Clip bante hi Telegram par jhalak aati hai. Pasand na aaye to
assets\\endcard_presenter.mp4 hata dijiye - agli video par naya ban jaayega
(din mein ek hi koshish, taaki fail hone par paisa baar-baar na kate).
Apna khud ka clip (jaise HeyGen se bana) usi naam se rakh dein to wahi
chalega - code use kabhi nahi chhedta.

Screen par chhota sa "AI प्रस्तुतकर्ता" label, aur description mein ek
line - wahi usool jo AI chitran aur anchor par hai: AI hai to bataya jaata
hai.

KABHI KUCH NAHI ROKTA
=====================
append() kabhi throw nahi karta. Koi bhi gadbad ho (asset na mile, ffmpeg
fail) to wahi purani video bina end-card ke aage chali jaati hai.

Band karna: config.ini mein [endcard] enabled = 0 (poora end-card), ya
presenter = 0 (sirf animation, studio par).
"""
import os
import shutil
import subprocess
import time

import sy_config as cfg

DUR = 8.0
FPS = 30

# (file, x, y) - animation frame mein kahan baithti hai. make_cta ke naap.
CTA = {
    "h": ("cta_16x9.mp4", 96, 256),
    "v": ("cta_9x16.mp4", 160, 1040),
}

LINE_HI = ("ख़बर अच्छी लगी हो तो वीडियो को लाइक कीजिए, चैनल को सब्सक्राइब "
           "कीजिए और अपनों के साथ शेयर ज़रूर कीजिए!")

PRESENTER_PROMPT = (
    "Photorealistic medium shot of a friendly young Indian woman TV news "
    "presenter, mid-twenties, shoulder-length straight dark hair, small "
    "gold earrings, wearing a mustard-yellow kurta with a cream dupatta. "
    "She is an ORIGINAL fictional person, not based on and not resembling "
    "any real, living or famous person. She stands on the RIGHT third of "
    "the frame in a modern TV news studio with soft blue and warm lights; "
    "the LEFT half of the frame is open, softly blurred studio background "
    "with no people. She looks straight into the camera with a warm, "
    "natural smile and says in clear, cheerful Hindi: \"%s\" While "
    "speaking she first gives a thumbs-up with her right hand, then points "
    "with her index finger toward the left side of the frame, and ends "
    "with an open, inviting hand gesture and a smile. Static camera, "
    "shallow depth of field, natural skin texture, broadcast lighting. "
    "No on-screen text, no captions, no subtitles, no logos, no watermark. "
    "Absolutely NO TV channel logo, channel name, station bug or 'HD' mark "
    "anywhere in the frame - especially not in any corner."
)

# Presenter clip (1920x1080 par laaya hua) ke upar-daayein kone ka badge:
# (file, x, y). Kyun - build_segment() mein likha hai.
BADGE = ("endcard_badge.png", 1700, 38)

DESC_LINE = ("वीडियो के अंत में दिखने वाली प्रस्तुतकर्ता AI-जनित है "
             "(कोई वास्तविक व्यक्ति नहीं)।")


def log(*a):
    print("[endcard]", *a, flush=True)


def _assets():
    return os.path.join(cfg.HERE, "assets")


def presenter_path():
    return os.path.join(_assets(), "endcard_presenter.mp4")


def voice_path():
    return os.path.join(_assets(), "endcard_voice.wav")


def enabled():
    try:
        return cfg.num("endcard", "enabled", 1) == 1
    except Exception:
        return False


def _presenter_on():
    return cfg.num("endcard", "presenter", 1) == 1


def _ok_file(p, min_bytes=100000):
    return bool(p) and os.path.isfile(p) and os.path.getsize(p) >= min_bytes


# ------------------------------------------------------------ presenter

def ensure_presenter():
    """Presenter clip ka path, ya "" (tab studio chalega). Pehli baar Veo
    se banata hai - din mein ek hi koshish."""
    p = presenter_path()
    if _ok_file(p, 200000):
        return p
    if not _presenter_on():
        return ""
    try:
        import sy_anchor
        import sy_store as st
    except Exception as e:
        log("presenter ka code nahi khula:", e)
        return ""
    if not sy_anchor.sa_path():
        return ""
    today = time.strftime("%Y-%m-%d")
    if st.kv_get("endcard_try_day", "") == today:
        return ""
    st.kv_set("endcard_try_day", today)

    os.makedirs(_assets(), exist_ok=True)
    tmp = p + ".new.mp4"
    log("presenter clip pehli baar bana rahe hain (Veo, ek hi baar)...")
    ok, why = sy_anchor.veo_person_clip(PRESENTER_PROMPT % LINE_HI, tmp,
                                        resolution="1080p")
    if not ok:
        log("presenter nahi bani:", why, "- studio par animation chalegi")
        try:
            import sy_telegram
            sy_telegram.send_message(
                "<b>End-card presenter nahi bani</b>\n\nWajah: "
                + sy_telegram._esc(str(why))[:500]
                + "\n\nVideo ke ant mein like/subscribe animation studio "
                  "background par chal rahi hai. Kal dobara koshish hogi.")
        except Exception:
            pass
        try:
            os.remove(tmp)
        except Exception:
            pass
        return ""
    try:
        os.replace(tmp, p)
    except Exception as e:
        log("presenter file rakhi nahi ja saki:", e)
        return ""
    log("presenter ban gayi:", p)
    try:
        import sy_telegram
        sy_telegram.send_video_file(
            p, "Naya end-card presenter (har video ke ant mein yahi aayegi). "
               "Pasand na aaye to assets\\endcard_presenter.mp4 hata dijiye - "
               "agle din naya banega.")
    except Exception:
        pass
    return p


def _ensure_voice():
    """Presenter na ho tab ke liye - ek baar TTS se line bana kar rakh lo."""
    p = voice_path()
    if _ok_file(p, 20000):
        return p
    try:
        import tempfile
        import sy_tts
        d = tempfile.mkdtemp(prefix="endcard_")
        out, _ = sy_tts.speak(LINE_HI, d)
        os.makedirs(_assets(), exist_ok=True)
        shutil.copyfile(out, p)
        shutil.rmtree(d, ignore_errors=True)
        return p
    except Exception as e:
        log("end-card ki aawaaz nahi bani (chup chalega):", str(e)[:150])
        return ""


# --------------------------------------------------------------- ffmpeg

def _probe(path):
    """(w, h, audio_rate, audio_channels)."""
    def q(sel, entries):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", sel,
             "-show_entries", "stream=" + entries, "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=60)
        return [x for x in (out.stdout or "").strip().split(",") if x]
    v = q("v:0", "width,height")
    a = q("a:0", "sample_rate,channels")
    w, h = int(v[0]), int(v[1])
    rate = int(a[0]) if a else 48000
    ch = int(a[1]) if len(a) > 1 else 2
    return w, h, rate, ch


def _duration(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60)
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _write_label(workdir, W, H):
    """Chhota 'AI प्रस्तुतकर्ता' label - libass se (Devanagari sahi judta hai)."""
    size = 34 if W >= H else 32
    ass = "\n".join([
        "[Script Info]", "ScriptType: v4.00+",
        "PlayResX: %d" % W, "PlayResY: %d" % H, "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: L,Noto Sans Devanagari,%d,&H00FFFFFF,&H00FFFFFF,&H00000000,"
        "&H99000000,0,0,0,0,100,100,0,0,3,8,0,3,40,40,40,1" % size, "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text",
        "Dialogue: 0,0:00:00.00,0:00:%05.2f,L,,0,0,0,,AI प्रस्तुतकर्ता" % DUR,
        ""])
    with open(os.path.join(workdir, "endcard.ass"), "w", encoding="utf-8") as f:
        f.write(ass)
    return "endcard.ass"


def build_segment(workdir, W, H, rate, ch, presenter=""):
    # presenter DUR se chhota ho (jaise explainer anchor ka 3-4 sec ka
    # vida wala hissa), to wo khatam hote hi dheere se studio par ghul
    # jaata hai - animation poore 8 second chalti rehti hai.
    """workdir/endcard.mp4 - wahi naap/format jo mukhya video ka hai, taaki
    bina dobara encode kiye jud sake. Path lauta ta hai, ya ""."""
    vertical = H > W
    cta_name, cx, cy = CTA["v" if vertical else "h"]
    cta = os.path.join(_assets(), cta_name)
    if not _ok_file(cta, 50000):
        log("animation file nahi mili:", cta)
        return ""

    out = os.path.join(workdir, "endcard.mp4")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    filt = []

    n_in = [0]

    def add_input(args):
        cmd.extend(args)
        n_in[0] += 1
        return n_in[0] - 1

    # 0: peeche ka drishya
    if presenter:
        i_p = add_input(["-i", presenter])
        # Pehle 1920x1080 par laate hain (Veo kabhi 720p deta hai), phir
        # upar-daayein kone par apna "सत्ययात्रा NEWS" badge.
        #
        # KYUN: Veo ne pehle clip mein, prompt mein mana karne ke baawajood,
        # upar-daayein kone mein kisi aur channel ka logo ("सोन NEWS HD")
        # bana diya tha. Wo hamesha usi jagah (x 1722-1905, y 55-165) aur
        # poore 8 second sthir tha. Badge us poore hisse ko dhak deta hai -
        # aur agla clip bina logo ke bhi aaye to bhi apna brand kone mein
        # rehna achha hi hai.
        filt.append("[%d:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                    "crop=1920:1080,setsar=1[pn]" % i_p)
        badge = os.path.join(_assets(), BADGE[0])
        if _ok_file(badge, 1000):
            i_b = add_input(["-loop", "1", "-i", badge])
            filt.append("[pn][%d:v]overlay=%d:%d:shortest=1[pb]"
                        % (i_b, BADGE[1], BADGE[2]))
        else:
            filt.append("[pn]null[pb]")
        plen = _duration(presenter)
        if 0.5 < plen < DUR - 0.3:
            import sy_scenes
            studio = sy_scenes.studio_path()
            if studio:
                i_st = add_input(["-stream_loop", "-1", "-i", studio])
                filt.append("[pb]fps=%d,format=yuv420p,settb=AVTB[pq]" % FPS)
                filt.append("[%d:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                            "crop=1920:1080,setsar=1,fps=%d,format=yuv420p,settb=AVTB[sq]"
                            % (i_st, FPS))
                filt.append("[pq][sq]xfade=transition=fade:duration=0.5:offset=%.3f[pbx]"
                            % max(0.1, plen - 0.5))
            else:
                filt.append("[pb]tpad=stop_mode=clone:stop_duration=%.2f[pbx]" % DUR)
        else:
            filt.append("[pb]null[pbx]")
        if vertical:
            # Khadi video: peeche dhundhla bhara hua, beech mein poora frame.
            filt.append(
                "[pbx]split[b0][f0];"
                "[b0]scale=%d:%d:force_original_aspect_ratio=increase,"
                "crop=%d:%d,boxblur=30:2,eq=brightness=-0.08[bb];"
                "[f0]scale=%d:-2[ff];[bb][ff]overlay=0:%d[bg0]"
                % (W, H, W, H, W, int(H * 0.16)))
        else:
            filt.append("[pbx]scale=%d:%d[bg0]" % (W, H))
    else:
        import sy_scenes
        studio = sy_scenes.studio_path()
        if studio:
            i_s = add_input(["-stream_loop", "-1", "-i", studio])
            filt.append("[%d:v]scale=%d:%d:force_original_aspect_ratio=increase,"
                        "crop=%d:%d[bg0]" % (i_s, W, H, W, H))
        else:
            i_s = add_input(["-f", "lavfi", "-i",
                             "color=c=0x0f1c30:s=%dx%d:r=%d" % (W, H, FPS)])
            filt.append("[%d:v]null[bg0]" % i_s)
    filt.append("[bg0]fps=%d,setpts=PTS-STARTPTS,format=yuv420p[bg]" % FPS)

    # animation (upar rang, neeche alpha)
    i_c = add_input(["-i", cta])
    filt.append("[%d:v]split[p][q];[p]crop=iw:ih/2:0:0[c];"
                "[q]crop=iw:ih/2:0:ih/2,format=gray[a];[c][a]alphamerge[cta]" % i_c)
    filt.append("[bg][cta]overlay=%d:%d:eof_action=pass:format=auto[v1]" % (cx, cy))
    if presenter:
        _write_label(workdir, W, H)
        filt.append("[v1]ass=endcard.ass,format=yuv420p[vout]")
    else:
        filt.append("[v1]format=yuv420p[vout]")

    # aawaaz
    layout = "stereo" if ch >= 2 else "mono"
    audio_in = None
    if presenter and _has_audio(presenter):
        audio_in = "%d:a" % i_p
    else:
        vp = "" if presenter else _ensure_voice()
        if vp:
            audio_in = "%d:a" % add_input(["-i", vp])
    if audio_in:
        filt.append("[%s]aresample=%d,aformat=sample_rates=%d:channel_layouts=%s,"
                    "apad,afade=t=out:st=%.2f:d=0.5[aout]"
                    % (audio_in, rate, rate, layout, DUR - 0.5))
    else:
        i_n = add_input(["-f", "lavfi", "-i", "anullsrc=r=%d:cl=%s" % (rate, layout)])
        filt.append("[%d:a]anull[aout]" % i_n)

    cmd += ["-filter_complex", ";".join(filt),
            "-map", "[vout]", "-map", "[aout]", "-t", "%.3f" % DUR,
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-maxrate", "2400k", "-bufsize", "5000k",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", str(rate), "-ac", str(ch),
            "-movflags", "+faststart", out]
    subprocess.run(cmd, cwd=workdir, check=True, timeout=600)
    return out if _ok_file(out, 50000) else ""


def _has_audio(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=60)
        return bool((out.stdout or "").strip())
    except Exception:
        return False


def _join(video, seg, out, workdir):
    """Pehle bina encode (tez). Lambai galat nikle to poora encode."""
    want = _duration(video) + _duration(seg)
    lst = os.path.join(workdir, "endcard_join.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.write("file '%s'\nfile '%s'\n" % (video.replace("\\", "/").replace("'", "'\\''"),
                                             seg.replace("\\", "/").replace("'", "'\\''")))
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", lst,
                        "-c", "copy", "-movflags", "+faststart", out],
                       cwd=workdir, check=True, timeout=300)
        got = _duration(out)
        if abs(got - want) < 0.6:
            return True
        log("seedha jodne par lambai %.1f (chahiye %.1f) - dobara encode" % (got, want))
    except Exception as e:
        log("seedha nahi juda (%s) - dobara encode" % str(e)[:100])
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", video, "-i", seg, "-filter_complex",
                    "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
                    "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "21",
                    "-pix_fmt", "yuv420p", "-r", str(FPS),
                    "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart", out],
                   cwd=workdir, check=True, timeout=900)
    return abs(_duration(out) - want) < 1.0


def append(story, video_path, workdir, presenter_override=""):
    """(video_path, presenter_laga). Kabhi throw nahi karta.

    presenter_override: is video ka apna anchor clip (sy_explainer ka vida
    wala hissa). Diya ho to wahi peeche chalta hai aur roz wali presenter
    NAHI aati - ek video mein ek hi chehra."""
    if not enabled():
        return video_path, False
    try:
        cfg.put_ffmpeg_on_path()
        workdir = os.path.abspath(workdir)
        video_path = os.path.abspath(video_path)
        W, H, rate, ch = _probe(video_path)
        presenter = presenter_override if _ok_file(presenter_override, 20000) \
            else ensure_presenter()
        seg = build_segment(workdir, W, H, rate, ch, presenter)
        if not seg:
            return video_path, False
        joined = os.path.join(workdir, "with_endcard.mp4")
        if not _join(video_path, seg, joined, workdir):
            log("jodi hui video sahi nahi bani - bina end-card ke")
            return video_path, False
        shutil.copyfile(joined, video_path)
        log("end-card lag gaya%s" % (" (AI presenter ke saath)" if presenter else ""))
        return video_path, bool(presenter)
    except Exception as e:
        log("end-card nahi laga (bina uske aage):", str(e)[:200])
        return video_path, False

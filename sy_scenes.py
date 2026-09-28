"""Tukdon ki timeline, aur usse ek katri hui background video.

Ye file ek hi sawaal ka jawab deti hai: jis lamhe par aawaaz ye baat keh
rahi hai, us lamhe par screen par kya chal raha hoga.

Teen cheezein isi timeline se chalti hain, isliye teenon ek saath badalti
hain - jo television mein sabse zaroori baat hai:
  1. peeche ka drishya
  2. screen par dikhne wale shabd
  3. neeche ka credit (har tasveer ka apna licence hota hai)

DO NAAP JO IS FILE MEIN BANDHE HAIN

Television news mein ek shot ausatan lagbhag 5 second ka hota hai. Hum har
5 second par ek nayi sacchi licence wali tasveer nahi jutaa sakte - itni
tasveerein hoti hi nahi, aur zabardasti laayi gayi tasveer jhooth ban jaati
hai. Par ek hi tasveer par 90 second baithna bhi television nahi hai.

Isliye do parat:
  - har baat par ek ALAG drishya (4-6 drishya ek bulletin mein)
  - aur ek hi drishya ke andar camera ka nazariya badalta rehta hai - door
    se dekha hua frame, phir usi tasveer ke andar ghusa hua frame. Isse cut
    lagbhag har 5-6 second par aata hai, bina koi nayi tasveer chahiye.

Ye koi chaalaki nahi hai - editing table par stills ke saath yahi kiya
jaata hai, aur isi wajah se us harkat ka naam hi "Ken Burns" pad gaya.
"""
import json
import os
import re
import subprocess

W, H = 1920, 1080
FPS = 30


def set_size(w, h):
    """Naap render_core se aata hai - bulletin 16:9, Reel 9:16.

    Ye zaroori hai: har tukda isi naap par bana kar joda jaata hai. Do
    alag naap ke tukde jodne par ffmpeg ya to mana kar deta hai ya ek ko
    kheench deta hai.
    """
    global W, H
    W, H = int(w), int(h)

MIN_SHOT = 4.0          # isse chhota tukda cut nahi, jhatka lagta hai
SUB_TARGET = 5.0        # ek nazariya kitni der - TV ka ausat shot itna hi hai
MIN_SUB = 3.2           # isse chhota nazariya aankh ko sambhalne nahi deta
MAX_SUBS = 3            # ek hi tasveer par teen se zyada nazariye jhooth lagte hain


def log(*a):
    print("[scenes]", *a, flush=True)


# STUDIO BACKGROUND - jahan footage nahi mila (Sep 2026)
#
# Pehle jis tukde ka drishya nahi milta tha, wo pichhle tukde ki tasveer
# naye nazariye se dobara dikha deta tha. Screen khaali nahi rehti thi,
# par ek hi tasveer baar-baar lautti thi - aur jahan shuru ka tukda hi
# khaali ho, wahan kuch tha hi nahi.
#
# Ab aise har tukde par channel ka apna chalta hua news-studio (ghoomta
# globe, khidki ke baahar din se raat) chalta hai. Ye kisi ghatna ka
# drishya hone ka daawa nahi karta - TV par bhi jab footage na ho to
# khabar studio se hi padhi jaati hai - isliye na credit, na AI label.
#
# Kram wahi rehta hai: asli tasveer/footage -> (Veo AI chitran, jahan
# chalu hai) -> STUDIO. Studio sirf aakhri sahara hai; visual_verdict()
# ise drishya nahi ginta, isliye kam-footage wali khabar pehle ki tarah
# hi rukti hai (Harshvardhan ka faisla).
#
# File: assets/studio_bg.mp4 (1920x1080, 30 fps, 30s ka seamless loop -
# aage chal kar ulta, taaki jod par jhatka na lage). Band karna ho to
# config.ini mein [media] studio = 0.
STUDIO_DEFAULT = os.path.join("assets", "studio_bg.mp4")
_studio_len_cache = {}


def studio_path():
    """Studio background ka poora path, ya "" agar band hai/file nahi."""
    try:
        import sy_config as cfg
        if cfg.num("media", "studio", 1) != 1:
            return ""
        p = cfg.get("media", "studio_bg") or STUDIO_DEFAULT
        if not os.path.isabs(p):
            p = os.path.join(cfg.HERE, p)
        if os.path.isfile(p) and os.path.getsize(p) > 100000:
            return p
    except Exception as e:
        log("studio background nahi mila:", e)
    return ""


def _studio_segment(workdir, src, out, dur, at):
    """Studio ka ek tukda - loop mein 'at' second se shuru.

    'at' video ki apni ghadi hai. Isse do studio tukde aas-paas aayein to
    globe wahin se ghoomta hai jahan ruka tha - har baar shuru se nahi."""
    n = _studio_len_cache.get(src)
    if n is None:
        n = _duration(src)
        _studio_len_cache[src] = n
    off = (at % n) if n > 1.0 else 0.0
    if off > n - 0.5:
        off = 0.0
    vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,fps=%d"
          % (W, H, W, H, FPS))
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-stream_loop", "-1", "-ss", "%.3f" % off, "-i", src,
         "-t", "%.3f" % dur,
         "-vf", vf, "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS), out],
        cwd=workdir, check=True, timeout=300)


# Camera ki harkat. Har nazariya alag dikhna chahiye - warna cut lagta to
# hai par kuch badalta nahi, aur wo cut se bhi bura hai.
# (z, x, y) - zoompan ke expression. iw/ih yahan 2880x1620 hain.
CENTRE_Y = "ih/2-(ih/zoom/2)"


def _wide(n_frames):
    """Poora drishya - kahan hain, kitna bada hai."""
    f = max(1, n_frames)
    return [
        # andar ghusta hua, beech se
        ("min(1.0+0.00030*on,1.15)", "iw/2-(iw/zoom/2)", CENTRE_Y),
        # baayein se daayein sarakta hua
        ("1.12", "(iw-iw/zoom)*min(1,on/%d)" % f, CENTRE_Y),
        # peechhe hatta hua - drishya khulta hai
        ("max(1.18-0.00032*on,1.02)", "iw/2-(iw/zoom/2)", CENTRE_Y),
        # daayein se baayein
        ("1.12", "(iw-iw/zoom)*(1-min(1,on/%d))" % f, CENTRE_Y),
    ]


def _tight(n_frames):
    """Usi tasveer ke andar ghusa hua frame - ab tafseel dikhti hai.

    Ye alag family jaan-boojhkar hai. Ek hi tasveer ke do nazariye agar
    lagbhag ek jaise hon, to cut par kuch badalta nahi aur wo cut galti
    lagta hai - jaise editing mein jhatka lag gaya ho. Isliye ek hi tasveer
    par nazariya hamesha chaude se tang ki taraf jaata hai, jaise camera
    aage badh gaya ho. Yahi wide-medium-tight ka purana usool hai.
    """
    f = max(1, n_frames)
    return [
        # daayein tihaai, aur andar
        ("min(1.34+0.00026*on,1.48)", "(iw-iw/zoom)*0.76", CENTRE_Y),
        # baayein tihaai, halka peechhe hatta hua
        ("max(1.46-0.00026*on,1.32)", "(iw-iw/zoom)*0.22", CENTRE_Y),
        # beech se tang, upar ki taraf
        ("1.40", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*0.28"),
        # tang, baayein se daayein sarakta hua
        ("1.38", "(iw-iw/zoom)*(0.15+0.7*min(1,on/%d))" % f, CENTRE_Y),
    ]


# --------------------------------------------------------------- timeline

def at_char(pos, timing, body_start, body_end):
    """Script ke is akshar par aawaaz kis lamhe pe hogi.

    timing sy_tts se aata hai: har bole gaye tukde ka asli samay. Do keelon
    ke beech seedhi lakeer se hisaab lagate hain - poora sach nahi, par har
    do-teen vaakya par ek pakki keel hai, aur wo akshar gin kar baantne se
    kahin behtar hai.
    """
    spans = (timing or {}).get("spans") or []
    if not spans:
        return None
    if pos <= spans[0][0]:
        return body_start + spans[0][2]
    for c0, c1, t0, t1 in spans:
        if pos <= c1:
            frac = (pos - c0) / float(max(1, c1 - c0))
            return body_start + t0 + frac * (t1 - t0)
    return min(body_start + spans[-1][3], body_end)


def find_char(text, needle):
    """Script mein ye hissa kahan se shuru hota hai. Na mile to -1."""
    a = re.sub(r"\s+", " ", str(text or ""))
    b = re.sub(r"\s+", " ", str(needle or "")).strip()
    if not b:
        return -1
    i = a.find(b)
    if i >= 0:
        return i
    # Poora na mile to shuruaati kuch shabd se dhoondh lete hain - script
    # thodi saaf ho chuki hoti hai (akhbaar ka naam hataya gaya hai).
    head = " ".join(b.split()[:5])
    return a.find(head) if len(head) > 12 else -1


def plan(shots, body_start, body_end, timing=None):
    """Har tukde ko uska samay do.

    Lambai script ke us tukde ke akshar ginkar tay hoti hai - jo baat bolne
    mein zyada der leti hai wo screen par bhi zyada der rehti hai. Ye ekdum
    sateek lip-sync nahi hai (Sarvam shabd-dar-shabd timing nahi deta), par
    darshak ko wahi drishya dikhta hai jis baat ki wo sun raha hai.
    """
    span = max(2.0, body_end - body_start)
    lens = [max(1, len(str(s.get("text") or ""))) for s in shots]
    total = float(sum(lens))

    d = [span * (n / total) for n in lens]
    # Bahut chhote tukde ko farsh tak uthao, phir sabko wapas span mein
    # samayo. Ek-do baar mein ye tham jaata hai.
    for _ in range(3):
        d = [max(MIN_SHOT, x) for x in d]
        s = sum(d)
        if abs(s - span) < 0.05:
            break
        d = [x * span / s for x in d]

    t = body_start
    for sh, dur in zip(shots, d):
        sh["start"] = round(t, 2)
        sh["end"] = round(min(t + dur, body_end), 2)
        t += dur
    if shots:
        shots[-1]["end"] = round(body_end, 2)

    # Agar aawaaz ki asli timing maujood hai to upar wala akshar-ginti wala
    # hisaab chhod kar wahi lagate hain - drishya theek us baat par badle
    # jispar aawaaz us waqt hai.
    text = (timing or {}).get("text") or ""
    if text and (timing or {}).get("spans"):
        prev = body_start
        ok = True
        marks = []
        for sh in shots:
            i = find_char(text, sh.get("text"))
            t0 = at_char(i, timing, body_start, body_end) if i >= 0 else None
            if t0 is None:
                ok = False
                break
            marks.append(max(prev, min(t0, body_end - MIN_SHOT)))
            prev = marks[-1]
        if ok and len(marks) == len(shots):
            for k, sh in enumerate(shots):
                sh["start"] = round(marks[k], 2)
                sh["end"] = round(marks[k + 1] if k + 1 < len(marks) else body_end, 2)
            shots[-1]["end"] = round(body_end, 2)
    return shots


def credit_spans(shots):
    """Har drishya ka apna credit, apne samay par.

    Ek hi credit poore video par chhod dena galat hota - us mein aadhe
    drishya kisi aur ke hain aur unka licence unke naam se hi bandha hai.
    """
    out = []
    for sh in shots:
        c = str(sh.get("credit") or "").strip()
        if not c:
            continue
        # Clip ke baad studio chala ho to credit wahin tak (build() dekhiye).
        end = min(sh["end"], sh.get("vis_end") or sh["end"])
        if out and out[-1][2] == c and out[-1][1] >= sh["start"] - 0.05:
            out[-1][1] = end            # wahi credit lagataar - jodh dete hain
            continue
        out.append([sh["start"], end, c])
    return [tuple(x) for x in out]


# ------------------------------------------------------------- background

def _subs(dur):
    """Ek drishya ko kitne nazariyon mein baanta jaye.

    Upar ki taraf gol karte hain, neeche ki taraf nahi: 9 second ka drishya
    do nazariyon mein behtar hai (4.5-4.5) bajaye ek 9 second ke sthir frame
    ke. Par koi nazariya MIN_SUB se chhota nahi hona chahiye.
    """
    n = int(dur / SUB_TARGET) + (1 if dur % SUB_TARGET > 0.01 else 0)
    n = max(1, min(MAX_SUBS, n))
    while n > 1 and dur / n < MIN_SUB:
        n -= 1
    return n


def _photo_segment(workdir, src, out, dur, move):
    frames = int(dur * FPS) + 2
    z, x, y = move
    vf = ("scale=2880:1620:force_original_aspect_ratio=increase,crop=2880:1620,"
          "zoompan=z='%s':x='%s':y='%s':d=%d:s=%dx%d:fps=%d"
          % (z, x, y, frames, W, H, FPS))
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-loop", "1", "-i", src, "-t", "%.3f" % dur,
         "-vf", vf, "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS), out],
        cwd=workdir, check=True, timeout=300)


def _clip_segment(workdir, src, out, dur):
    # Chalti footage par Ken Burns nahi lagta - wo pehle se chal rahi hai,
    # uspar aur zoom lagana sirf hilti hui tasveer banata hai. Bas frame
    # bharna hai: badi taraf se scale karke beech se crop, taaki khinche na.
    # Stock clip aksar 10-15 second ki hoti hai, isliye loop par.
    vf = ("scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,fps=%d"
          % (W, H, W, H, FPS))
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-stream_loop", "-1", "-i", src, "-t", "%.3f" % dur,
         "-vf", vf, "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", "-r", str(FPS), out],
        cwd=workdir, check=True, timeout=300)


def _duration(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60)
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _concat(workdir, segs, listing, out_name):
    with open(listing, "w", encoding="utf-8") as fh:
        for s in segs:
            fh.write("file '%s'\n" % s)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", os.path.basename(listing),
         "-c", "copy", out_name],
        cwd=workdir, check=True, timeout=300)


def _top_up(shots, kami, workdir, segs, listing, out_name, mi, studio="", clock=0.0):
    """Aakhri drishya ko thoda aur chala kar kami poori karo."""
    if kami <= 0.1:
        return False
    name = "seg%02d.mp4" % len(segs)
    # Aakhri tukda studio par tha - to wahi aage chale. Warna studio ke
    # baad achaanak koi purani tasveer laut aati.
    if studio and shots and shots[-1].get("studio"):
        try:
            _studio_segment(workdir, studio, name, kami, clock)
            segs.append(name)
            _concat(workdir, segs, listing, out_name)
            return True
        except Exception as e:
            log("studio aage nahi badhaya ja saka:", e)
            return False
    last = None
    for sh in shots:
        if sh.get("file"):
            last = sh
    if not last:
        return False
    try:
        if last.get("kind") == "clip":
            _clip_segment(workdir, last["file"], name, kami)
        else:
            _photo_segment(workdir, last["file"], name, kami,
                           _tight(int(kami * FPS))[mi % 4])
        segs.append(name)
        _concat(workdir, segs, listing, out_name)
        return True
    except Exception as e:
        log("aakhri drishya badhaya nahi ja saka:", e)
        return False


def build(shots, total, workdir, out_name="clip.mp4"):
    """Sab tukdon ko jod kar ek background video.

    Cut ke waqton ki list lauta ta hai (khaali list = nahi bani).

    Cut hain, ghulawat nahi. News mein shot cut hote hain - har badlaav par
    dissolve lagane se video shaadi ke album jaisi lagne lagti hai.

    Jis tukde par drishya nahi mila, us par studio background chalta hai
    (studio_path(), upar dekhiye). Studio file na ho ya band ho to purana
    rawaiya: wo tukda apne pichhle tukde ka drishya NAYE nazariye se le
    leta hai. Ek bhi drishya na ho to False, aur render_core apna backdrop
    (ya studio) bana lega.
    """
    if not shots:
        return []
    if not any(s.get("file") for s in shots):
        return []

    studio = studio_path()

    # Aakhir mein aadha second zyada - render ise -t se kaat dega. Kam pad
    # gaya to aakhri frame par video atak jaati hai, jo saaf dikhta hai.
    end_pad = 0.6
    segs = []
    cuts = [0.0]        # har naye frame ki shuruaat - screen text isi par bethega
    clock = 0.0
    mi = 0
    last_file, last_kind = "", ""

    # SAMAY KI KAMI WAHIN BHARO JAHAN HUI (Sep 2026).
    #
    # Pehle koi tukda fail hota (ffmpeg gira / file nahi mili) to chup-chaap
    # 'continue' - clock aage nahi badhta tha. Nateeja: baad ke saare
    # drishya aawaaz se AAGE khisak jaate, aur aakhir mein _top_up aakhri
    # tasveer ko 25-48 second tak ek jagah jamaa deta. Credit apne sahi
    # samay par chalta raha - yaani screen par ek tasveer aur neeche kisi
    # aur ka naam. gy_indus_202609 (naksha aur Dholavira dikhe hi nahi,
    # ruke hue khandhar par "Dmitry Anuchin" credit) aur st_9699961 (CHC,
    # nadi kinara, shok - teeno ki jagah 48s ek jami hui tasveer, neeche
    # "Pexels" credit). Ab har tukde se pehle hisaab: jitna samay ab tak
    # hona chahiye tha (target) usse clock peeche hai to kami wahin bharo -
    # studio se (jiska drishya dikha hi nahi, uska credit bhi hata kar),
    # warna pichhli safal tasveer CHALTE nazariye se.
    target = 0.0
    last_good = ("", "", "")        # (file, kind, credit) - jo sach mein bana

    def heal(sh_prev):
        nonlocal clock
        gap = target - clock
        if not segs or gap <= 0.3:
            return
        shown = bool((sh_prev or {}).get("_shown"))
        use_studio = bool(studio) and not shown
        if not use_studio and not last_good[0]:
            return
        name = "seg%02d.mp4" % len(segs)
        try:
            if use_studio:
                _studio_segment(workdir, studio, name, gap, clock)
            elif last_good[1] == "clip":
                _clip_segment(workdir, last_good[0], name, gap)
            else:
                _photo_segment(workdir, last_good[0], name, gap,
                               _wide(int(gap * FPS))[mi % 4])
        except Exception as e:
            log("%.1fs ki kami nahi bhari ja saki: %s" % (gap, e))
            return
        segs.append(name)
        clock += gap
        cuts.append(round(clock, 3))
        log("%.1fs ki kami bhari (%s)" % (gap, "studio" if use_studio else "pichhla drishya"))
        if sh_prev is not None and not shown:
            sh_prev["credit"] = "" if use_studio else last_good[2]
            sh_prev["studio"] = use_studio

    prev = None
    for idx, sh in enumerate(shots):
        heal(prev)
        prev = sh
        sh.pop("studio", None)
        sh.pop("vis_end", None)
        dur = float(sh["end"]) - float(sh["start"])
        if idx == 0:
            dur += float(sh["start"])        # title card bhi yahi drishya dhake
        if idx == len(shots) - 1:
            dur += end_pad
        target += dur

        if not sh.get("file") and studio:
            if dur <= 0.2:
                continue
            name = "seg%02d.mp4" % len(segs)
            try:
                _studio_segment(workdir, studio, name, dur, clock)
            except Exception as e:
                log("studio ka tukda nahi bana (%d): %s" % (idx + 1, e))
            else:
                sh["studio"] = True
                sh["_shown"] = True
                segs.append(name)
                clock += dur
                cuts.append(round(clock, 3))
                continue
            # Studio bhi na bana - neeche purane raste se pichhla drishya.

        f = sh.get("file") or last_file
        kind = sh.get("kind") if sh.get("file") else last_kind
        if not f:
            # Abhi tak kuch mila hi nahi - aage ka drishya udhaar nahi le
            # sakte, isliye ye tukda chhod dete hain. Agla tukda apne aap
            # is samay ko bhar lega.
            continue
        last_file, last_kind = f, kind

        if dur <= 0.2:
            continue

        src = os.path.join(workdir, f)
        if not os.path.exists(src):
            log("tukda %d ki file nahi mili: %s" % (idx + 1, f))
            continue

        if kind == "clip":
            # CLIP EK HI BAAR CHALE, LOOP NAHI (Sep 2026). 6-8 second ki Veo
            # clip 20 second ke tukde par teen baar dohrayi jaati thi -
            # Harshvardhan: "8 sec ka clip bar bar repeat karte rehte hain,
            # wo theek nahi". Ab clip apni lambai tak chalti hai, baaki samay
            # studio par (credit/AI label wahin ruk jaata hai - vis_end), aur
            # studio na ho to clip ke aakhri frame par chalta nazariya.
            name = "seg%02d.mp4" % len(segs)
            n_len = _duration(src)
            play = dur if not (n_len > 1.0 and dur > n_len + 1.0) else n_len - 0.1
            try:
                _clip_segment(workdir, f, name, play)
            except Exception as e:
                log("clip ka tukda nahi bana (%d): %s" % (idx + 1, e))
                continue
            segs.append(name)
            clock += play
            cuts.append(round(clock, 3))
            sh["_shown"] = True
            last_good = (f, kind, sh.get("credit") or "")
            rest = dur - play
            if rest > 0.2:
                name = "seg%02d.mp4" % len(segs)
                try:
                    if studio:
                        _studio_segment(workdir, studio, name, rest, clock)
                        sh["vis_end"] = round(clock, 2)
                    else:
                        still = "_still%d.jpg" % idx
                        subprocess.run(
                            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                             "-sseof", "-0.3", "-i", f, "-frames:v", "1", "-q:v", "3", still],
                            cwd=workdir, check=True, timeout=60)
                        _photo_segment(workdir, still, name, rest,
                                       _wide(int(rest * FPS))[mi % 4])
                except Exception as e:
                    log("clip ke baad ka samay nahi bhara (%d): %s" % (idx + 1, e))
                else:
                    segs.append(name)
                    clock += rest
                    cuts.append(round(clock, 3))
                    log("  %d: clip %.1fs ki thi, baaki %.1fs %s" % (
                        idx + 1, play, rest, "studio" if studio else "aakhri frame"))
            continue

        n = _subs(dur)
        each = dur / n
        frames = int(each * FPS)
        for k in range(n):
            name = "seg%02d.mp4" % len(segs)
            # Ek hi tasveer par: pehle chaura frame, phir tang. Alag
            # tasveeron par kram apne aap aage badhta rehta hai taaki do
            # padosi drishya ek jaisi harkat na karein.
            move = (_wide(frames)[mi % 4] if k % 2 == 0
                    else _tight(frames)[mi % 4])
            mi += 1
            try:
                _photo_segment(workdir, f, name, each, move)
            except Exception as e:
                log("tasveer ka tukda nahi bana (%d.%d): %s" % (idx + 1, k + 1, e))
                continue
            segs.append(name)
            clock += each
            cuts.append(round(clock, 3))
            sh["_shown"] = True
            last_good = (f, kind, sh.get("credit") or "")

    heal(prev)                      # aakhri tukda bhi fail hua ho to
    for sh in shots:
        sh.pop("_shown", None)
    if not segs:
        return []

    listing = os.path.join(workdir, "segs.txt")
    try:
        _concat(workdir, segs, listing, out_name)
    except Exception as e:
        log("tukde jud nahi paye:", e)
        return []

    # Jitna maanga tha, utna mila? Har tukda encode hone par ek-do frame
    # kam pad jaata hai, aur saat tukdon mein wo teen second tak pahunch
    # gaya tha. Us kami ko render ko sompna theek nahi - wahin se wo
    # dohrane wali gadbad shuru hoti hai jo poora render jamaa deti hai.
    made = _duration(os.path.join(workdir, out_name))
    if made and made < total + 0.2:
        kami = (total + 0.8) - made
        log("%.1fs bani, %.1fs chahiye - aakhri drishya %.1fs aur badha rahe hain"
            % (made, total, kami))
        if _top_up(shots, kami, workdir, segs, listing, out_name, mi,
                   studio, clock):
            made = _duration(os.path.join(workdir, out_name))

    n_studio = len([s for s in shots if s.get("studio")])
    log("%d drishya%s, %d cut, %.1f second" % (
        len([s for s in shots if s.get("file")]),
        (" + %d studio" % n_studio) if n_studio else "",
        len(segs), made or total))
    # Cut ke waqt wapas bhejte hain: screen ka text inhi par baithega.
    # Netflix ki timing guide ka niyam hai ki agar text shot badalne ke
    # aadhe second ke andar shuru ho raha ho to use shot ke pehle frame
    # par hi khiska do - warna aankh ek saath do jagah kheenchti hai.
    return cuts[:-1] if len(cuts) > 1 else cuts


def describe(shots):
    """Telegram par bhejne layak ek chhoti si shot list."""
    out = []
    for i, sh in enumerate(shots):
        mark = "•" if sh.get("file") else ("▣" if sh.get("studio") else "×")
        out.append("%s %d. %s  %s–%ss  %s" % (
            mark, i + 1, (sh.get("type") or "?"),
            int(sh.get("start") or 0), int(sh.get("end") or 0),
            (sh.get("brief") or "")[:52]))
    return "\n".join(out)

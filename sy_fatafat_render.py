"""Fatafat Khabar Reel ka 9:16 render - ek tukda (hook / khabar / CTA) ek clip.

ROOP (1080x1920)
================
  0-150     laal patti: "सत्ययात्रा न्यूज · फटाफट ख़बरें" + "ख़बर 2/4"
  150-162   progress ki dhaariyaan (har khabar ek, jo ho chuki wo safed)
  170-700   FOOTAGE KI KHIDKI - khabar ki tasveer/clip (anchor ke upar)
  ~560-760  BADA HEADLINE CARD (khidki ke neeche kinaare par chadha hua)
  700-1920  ANCHOR - mukhya. HeyGen ka 16:9 frame beech se (anchor jahan
            khadi hai, cx) kaat kar khada kiya jaata hai.
  ~1300-1560 CAPTIONS - bade, Devanagari, kaale box par (log bina aawaaz
            dekhte hain). Neeche ke ~320px Shorts ka apna UI leta hai.

Anchor na ho (HeyGen band/fail): footage poori screen par (halka andhera),
headline card beech mein, captions waise hi - Reel kabhi nahi rukti.

Devanagari ffmpeg drawtext se NAHI (wo matra todta hai) - saara text .ass
(libass + HarfBuzz) mein, jaise render_core mein.
"""
import os
import re
import subprocess

W, H = 1080, 1920
FPS = 30
FONT = "Noto Sans Devanagari"

HEAD_H = 150
BAR_Y, BAR_H = 150, 12
PANEL_Y, PANEL_H = 170, 530
ANCHOR_Y = PANEL_Y + PANEL_H            # 700
ANCHOR_H = H - ANCHOR_Y                 # 1220
CARD_Y = 600                            # headline card ka beech (anchor wala roop)
CARD_Y_FULL = 820                       # bina anchor
CAP_Y = 1430                            # captions ka beech
SAFE_BOTTOM = 320                       # Shorts UI

RED = "c8102e"
DEEP = "8c1225"
GOLD = "ffc61a"
INK = "111111"

CAP_CHARS = 26          # ek line - 62px Devanagari (~20px/akshar) par ~1000px mein aaraam se
CAP_LINES = 2
CARD_CHARS = 24
CARD_LINES = 2

BRAND = "सत्ययात्रा न्यूज"
SHOW = "फटाफट ख़बरें"


def log(*a):
    print("[fatafat-render]", *a, flush=True)


# ------------------------------------------------------------ text

def _esc(s):
    s = str(s or "").replace("\\", "⧵").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", s).strip()


def _col(hex_rgb, alpha=0):
    h = str(hex_rgb).lstrip("#")
    return "&H%02X%s%s%s&" % (alpha, h[4:6].upper(), h[2:4].upper(), h[0:2].upper())


def wrap(text, per_line, max_lines):
    """Shabd par todo; zyada ho to aakhri line '…' par khatam."""
    words = str(text or "").split()
    lines, cur = [], ""
    for wd in words:
        cand = (cur + " " + wd).strip()
        if len(cand) > per_line and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = cand
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip("।,") + "…"
    return lines


def caption_chunks(text, budget=CAP_CHARS * CAP_LINES):
    """Bole jaane wale text ke screen-tukde - vaakya par, phir shabd par.
    Har tukda zyada se zyada 'budget' akshar (do line)."""
    out = []
    for sent in re.split(r"(?<=[।!?\.])\s+", str(text or "").strip()):
        sent = sent.strip()
        if not sent:
            continue
        cur = ""
        for wd in sent.split():
            cand = (cur + " " + wd).strip()
            if len(cand) > budget and cur:
                out.append(cur)
                cur = wd
            else:
                cur = cand
        if cur:
            # Akela chhota latka shabd pichhle mein mila do.
            if out and len(cur) < 8 and len(out[-1]) + len(cur) + 1 <= budget + 8:
                out[-1] = out[-1] + " " + cur
            else:
                out.append(cur)
    return out


def caption_times(chunks, start, end):
    """Akshar ke anupaat mein samay. [(a, b, text)] - lagaataar, bina gap."""
    total = float(sum(len(c) for c in chunks)) or 1.0
    span = max(0.1, end - start)
    out, t = [], start
    for c in chunks:
        d = span * len(c) / total
        out.append((round(t, 2), round(t + d, 2), c))
        t += d
    return out


def _ts(sec):
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec - h * 3600 - m * 60
    return "%d:%02d:%05.2f" % (h, m, s)


def build_ass(seg, path):
    """Ek tukde ki .ass - patti ka text, headline card, captions, credit.

    seg: {"kind": hook|item|cta, "headline", "text", "dur", "speech":
    (a, b), "index", "count", "anchor": bool, "credit", "date"}"""
    dur = float(seg["dur"])
    anchor = bool(seg.get("anchor"))
    styles = [
        # Name, size, primary, outline, back, bold, borderstyle, outline, shadow, align
        ("Brand", 46, "ffffff", INK, "000000", -1, 1, 0, 0, 4),
        ("Show", 38, GOLD, INK, "000000", -1, 1, 0, 0, 4),
        ("Count", 58, "ffffff", INK, "000000", -1, 1, 0, 0, 6),
        ("Card", 74, "ffffff", DEEP, DEEP, -1, 3, 22, 0, 5),
        ("Kick", 40, INK, GOLD, GOLD, -1, 3, 10, 0, 5),
        ("Cap", 62, "ffffff", "000000", "000000", -1, 3, 14, 0, 5),
        ("Small", 30, "ffffff", "000000", "000000", 0, 1, 2, 0, 1),
        ("Label", 30, "ffffff", "000000", "000000", -1, 1, 2, 0, 3),
    ]
    doc = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: %d" % W,
           "PlayResY: %d" % H, "WrapStyle: 2", "ScaledBorderAndShadow: yes",
           "", "[V4+ Styles]",
           "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
           "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,"
           "ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,"
           "MarginR,MarginV,Encoding"]
    for n, size, pc, oc, bc, bold, bs, ol, sh, al in styles:
        doc.append("Style: %s,%s,%d,%s,%s,%s,%s,%d,0,0,0,100,100,0,0,%d,%d,%d,%d,40,40,0,1"
                   % (n, FONT, size, _col(pc), _col(pc), _col(oc), _col(bc, 0x30),
                      bold, bs, ol, sh, al))
    doc += ["", "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]

    def ev(style, a, b, text, layer=1):
        doc.append("Dialogue: %d,%s,%s,%s,,0,0,0,,%s"
                   % (layer, _ts(a), _ts(b), style, text))

    # Upar ki patti
    ev("Brand", 0, dur, "{\\pos(40,62)}" + _esc(BRAND))
    ev("Show", 0, dur, "{\\pos(42,120)}" + _esc(SHOW + ("  ·  " + seg["date"]
                                                        if seg.get("date") else "")))
    if seg["kind"] == "item":
        ev("Count", 0, dur, "{\\pos(1040,75)}ख़बर %d/%d"
           % (seg["index"] + 1, seg["count"]))

    # Headline card - shuru mein halka 'pop'
    cy = CARD_Y if anchor else CARD_Y_FULL
    head = wrap(seg.get("headline") or "", CARD_CHARS, CARD_LINES)
    if head:
        pop = "{\\an5\\pos(%d,%d)\\fscx86\\fscy86\\t(0,180,\\fscx100\\fscy100)}" % (W // 2, cy)
        ev("Card", 0, dur, pop + "\\N".join(_esc(l) for l in head), layer=2)
        if seg.get("kicker"):
            ky = cy - 50 - 46 * len(head)
            ev("Kick", 0, dur, "{\\an5\\pos(%d,%d)}%s" % (W // 2, ky, _esc(seg["kicker"])),
               layer=3)

    # Captions - bole shabd
    a, b = seg.get("speech") or (0.0, dur)
    for ca, cb, txt in caption_times(caption_chunks(seg.get("text") or ""), a, b):
        lines = wrap(txt, CAP_CHARS, CAP_LINES + 1)
        ev("Cap", ca, cb, "{\\an5\\pos(%d,%d)}" % (W // 2, CAP_Y)
           + "\\N".join(_esc(l) for l in lines), layer=4)

    # Imaandari ki chhoti likhai
    by = H - SAFE_BOTTOM - 10
    if seg.get("credit"):
        ev("Small", 0, dur, "{\\an1\\pos(30,%d)}%s" % (by, _esc(seg["credit"])[:60]))
    if anchor:
        ev("Label", 0, dur, "{\\an3\\pos(1050,%d)}AI प्रस्तुतकर्ता" % (ANCHOR_Y + 50))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(doc) + "\n")
    return path


# ------------------------------------------------------------ video

def _is_video(path):
    return str(path or "").lower().endswith((".mp4", ".mov", ".webm", ".mkv", ".ogv"))


def _bars(index, count):
    """Progress ki dhaariyaan (drawbox). index = abhi wali khabar (-1 = hook)."""
    if count <= 0:
        return ""
    gap, x0 = 10, 40
    bw = (W - 2 * x0 - gap * (count - 1)) // count
    out = []
    for k in range(count):
        col = "white" if k <= index else "white@0.30"
        out.append("drawbox=x=%d:y=%d:w=%d:h=%d:color=%s:t=fill"
                   % (x0 + k * (bw + gap), BAR_Y, bw, BAR_H, col))
    return "," + ",".join(out)


def render_segment(seg, out, workdir):
    """Ek tukda -> out (1080x1920, 30fps, h264 + aac 48k stereo).

    seg ke upar wale fields ke alawa: "voice" (wav), "anchor_file",
    "anchor_cx", "media" (photo/clip ya ""), "bg" (anchor na ho to peeche -
    studio clip ya "")."""
    dur = float(seg["dur"])
    ass = build_ass(seg, os.path.join(workdir, "seg_%s.ass" % seg["tag"]))
    anchor = bool(seg.get("anchor")) and os.path.exists(seg.get("anchor_file") or "")
    media = seg.get("media") or ""
    if media and not os.path.exists(media):
        media = ""

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i", "color=c=0x0b1220:s=%dx%d:r=%d:d=%.3f" % (W, H, FPS, dur)]
    fc = []
    n = 1
    last = "[0:v]"

    def add_input(path):
        nonlocal n
        if _is_video(path):
            cmd.extend(["-stream_loop", "-1", "-i", path])
        else:
            cmd.extend(["-loop", "1", "-framerate", str(FPS), "-i", path])
        n += 1
        return n - 1

    if anchor:
        k = n
        cmd.extend(["-i", seg["anchor_file"]])
        n += 1
        cx = max(0.15, min(0.85, float(seg.get("anchor_cx") or 0.5)))
        fc.append("[%d:v]trim=0:%.3f,setpts=PTS-STARTPTS,"
                  "crop=w='min(iw,ih*%d/%d)':h=ih:x='max(0,min(iw-ow,iw*%.3f-ow/2))':y=0,"
                  "scale=%d:%d,setsar=1,fps=%d[anc]"
                  % (k, dur, W, ANCHOR_H, cx, W, ANCHOR_H, FPS))
        fc.append("%s[anc]overlay=0:%d[b1]" % (last, ANCHOR_Y))
        last = "[b1]"
        box_y, box_h = PANEL_Y, PANEL_H
    else:
        box_y, box_h = 0, H

    src = media or seg.get("bg") or ""
    if src:
        k = add_input(src)
        big_w, big_h = int(W * 1.10), int(box_h * 1.10)
        # Ken Burns: chhoti si chaal - tasveer zinda lage. Clip par bhi wahi
        # (bas sthir crop) - halka sa zoom.
        # Vyakti ki tasveer (portrait) mein chehra upar ke hisse mein hota
        # hai - beech se kaatne par sir kat jaata tha. Wahan upar se ~18%.
        ypos = "(ih-%d)*0.18" % box_h if seg.get("media_kind") == "person" \
            else "(ih-%d)/2" % box_h
        move = ("x='(iw-%d)*t/%.3f':y='%s'" % (W, max(dur, 0.1), ypos)
                if not _is_video(src) else "x='(iw-%d)/2':y='%s'" % (W, ypos))
        dim = "" if anchor else ",eq=brightness=-0.12:saturation=0.9"
        fc.append("[%d:v]trim=0:%.3f,setpts=PTS-STARTPTS,"
                  "scale=%d:%d:force_original_aspect_ratio=increase,"
                  "crop=%d:%d:%s,setsar=1,fps=%d%s[med]"
                  % (k, dur, big_w, big_h, W, box_h, move, FPS, dim))
        fc.append("%s[med]overlay=0:%d[b2]" % (last, box_y))
        last = "[b2]"

    # Upar ki patti + progress + khidki ka kinaara, phir saara text
    deco = ("drawbox=x=0:y=0:w=%d:h=%d:color=0x%s:t=fill" % (W, HEAD_H, RED)
            + _bars(seg.get("index", -1) if seg["kind"] != "cta"
                    else seg.get("count", 0), seg.get("count", 0)))
    if anchor:
        deco += ",drawbox=x=0:y=%d:w=%d:h=6:color=0x%s:t=fill" % (ANCHOR_Y - 3, W, GOLD)
    fc.append("%s%s,ass=%s,format=yuv420p[v]"
              % (last, deco, os.path.basename(ass)))

    # Aawaaz: sirf hamari voice (HeyGen ki aawaaz kabhi nahi)
    vk = n
    cmd.extend(["-i", seg["voice"]])
    # voice pehle se aage-peeche chuppi ke saath (sy_fatafat.pad_wav) - wahi
    # file HeyGen ko gayi thi, isliye hont aur aawaaz 0 se hi milte hain.
    fc.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,"
              "apad,atrim=0:%.3f[a]" % (vk, dur))
    cmd += ["-filter_complex", ";".join(fc), "-map", "[v]", "-map", "[a]",
            "-t", "%.3f" % dur, "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-ac", "2", os.path.abspath(out)]
    r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=900)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("tukda render nahi hua: " + (r.stderr or "")[-600:])
    return out


def join(parts, out, workdir, music=""):
    """Tukde jodo; aawaaz ek saath -14 LUFS par; music ho to dheemi neeche."""
    listing = os.path.join(workdir, "ff_parts.txt")
    with open(listing, "w", encoding="utf-8") as f:
        for p in parts:
            f.write("file '%s'\n" % os.path.abspath(p).replace("'", "'\\''"))
    raw = os.path.join(workdir, "ff_raw.mp4")
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", raw],
                   check=True, timeout=600)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", raw]
    if music and os.path.exists(music):
        cmd += ["-stream_loop", "-1", "-i", music,
                "-filter_complex",
                "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[v];"
                "[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=-24dB[m];"
                "[v][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-map", "0:v", "-map", "0:a"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-movflags", "+faststart", os.path.abspath(out)]
    subprocess.run(cmd, check=True, timeout=600)
    try:
        os.remove(raw)
    except Exception:
        pass
    return out


def preview(src, out, max_mb):
    """Telegram ke liye chhoti jhalak (540x960). Choti ho to wahi file."""
    if os.path.getsize(src) <= max_mb * 1024 * 1024 * 0.5:
        return src
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-vf", "scale=540:960", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "28", "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart", out], check=True, timeout=600)
    return out if os.path.exists(out) else src

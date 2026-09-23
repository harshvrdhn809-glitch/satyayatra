"""
SatyaYatra thumbnail — 1280x720 JPEG, YouTube ke liye.

YouTube par click sabse pehle thumbnail par hota hai, aur mobile feed mein wo
thumbnail sirf ~210x118 px ka dikhta hai. Isliye do niyam poore design par
haavi hain:

  1. Teen se paanch shabd. Zyada shabd matlab chhota font matlab feed mein
     kuchh padha hi nahi jaata.
  2. Text ki lambai se font size tay hota hai, font size se text nahi. Wahi
     naapa hua Devanagari metric (CH_W) jo video mein lagta hai.

Text yahan bhi ffmpeg ke drawtext se nahi banta. Devanagari mein matra aur
conjunct shaping chahiye — wo libass (HarfBuzz) karta hai. Isliye tarika wahi
hai jo video mein hai: background plate PIL banata hai, uske upar ek .ass
file libass se burn hoti hai, aur ek hi frame JPEG mein nikal jaata hai.
PIL par text ka bhaar nahi daala kyunki har Pillow build mein complex-script
shaping (raqm) hoti hi nahi — libass mein hamesha hoti hai.
"""

import hashlib
import os
import re
import subprocess

from PIL import Image, ImageDraw, ImageOps

import sy_config as cfg

TW, TH = 1280, 720

# ------------------------------------------------- AI-BANI TOPIC-WISE ART
#
# Ab tak jab koi sacchi tasveer nahi milti thi, sirf ek programmatic
# "backdrop" (geometric pattern - dhaariyaan, grid) lagta tha. Wo kabhi
# GALAT nahi tha (koi jhooth nahi bolta), par aakarshak bhi nahi tha - aur
# YouTube par click sabse pehle thumbnail se aata hai. Ab uski jagah, jab
# saamaan chalu ho, ek Vertex-bani, us khabar ke VISHAY (category/entity/
# baat) ke hisaab se banayi gayi illustration istemal hoti hai - abhi bhi
# koi asli chehra ya asli ghatna ka "saboot" nahi (AADMI KABHI NAHI yahan
# bhi kaayam hai), sirf ek zyada khoobsurat, topic-anusaar backdrop.
#
# Apna alag kota hai (veo/anchor se bilkul alag) taaki thumbnail kabhi un
# doosre kaamon ka paisa na khaaye, aur koshish fail ho to chup-chaap
# purana geometric backdrop chal jaata hai - koi bhi gadbad thumbnail
# banna kabhi nahi rokti.
def _ai_on():
    return cfg.num("thumb", "ai_backdrop", 1) == 1


def _ai_model():
    return cfg.get("thumb", "image_model") or "gemini-2.5-flash-image"


def _ai_max_per_day():
    return cfg.num("thumb", "max_per_day", 20)


def _ai_sa_path():
    given = cfg.get("veo", "service_account")
    if given and os.path.exists(given):
        return given
    p = os.path.join(cfg.HERE, "satyayatra-sa.json")
    return p if os.path.exists(p) else ""


def _ai_location():
    return cfg.get("thumb", "location") or cfg.get("veo", "location") \
        or "us-central1"


def _today():
    import time
    return time.strftime("%Y-%m-%d")


def _ai_used_today():
    import sy_store as st
    if st.kv_get("thumb_ai_day", "") != _today():
        return 0
    return int(st.kv_get("thumb_ai_count", 0) or 0)


def _ai_note_used():
    import sy_store as st
    if st.kv_get("thumb_ai_day", "") != _today():
        st.kv_set("thumb_ai_day", _today())
        st.kv_set("thumb_ai_count", 0)
    st.kv_set("thumb_ai_count", _ai_used_today() + 1)


# Har category ka apna, jaana-pehchana drishya sanket - taaki AI khaali
# "news graphic" na bana de, balki category dekhte hi pehchaani jaaye.
_CATEGORY_HINT = {
    "politics": "a grand government building facade with national flag, "
                "columns and dramatic evening light",
    "crime": "a dark city street at night with red and blue emergency "
             "lights reflecting off wet pavement, silhouette of a police "
             "barricade",
    "education": "an open book, graduation cap and pencil composed in a "
                 "clean modern still life with soft classroom light",
    "economy": "stacks of Indian rupee coins and a rising bar-chart line "
               "graphic, warm gold light",
    "weather": "dramatic monsoon storm clouds over a river landscape, "
               "heavy rain and lightning",
    "sport": "a floodlit stadium at night from a low dramatic angle, "
             "motion blur suggesting speed",
    "civic": "a busy Indian city skyline at dusk with roads, streetlights "
             "and water towers",
    "tech": "a glowing abstract network of connected nodes and circuit-like "
            "lines over a dark background, futuristic soft blue and gold "
            "light, subtle digital interface elements",
}


def _ai_prompt(category, entity, key_fact, kicker):
    hint = _CATEGORY_HINT.get(str(category or "").lower(), _CATEGORY_HINT["civic"])
    subject = ", ".join(x for x in (entity, key_fact, kicker) if x)
    return (
        "A professional Indian Hindi TV news channel thumbnail background "
        "illustration, broadcast graphic design style, dramatic navy-blue "
        "and red color palette, cinematic lighting, high detail, no "
        "readable text anywhere in the image, no logos, no watermarks, "
        "no real recognizable human faces. Scene: " + hint + ". "
        "Topic context (do not render as text, only as mood/imagery): "
        + (subject or str(category or "news")) + ". "
        "Leave calm, less-busy negative space usable for a text overlay. "
        "16:9 wide composition."
    )


def ai_backdrop(category, entity, key_fact, kicker, workdir):
    """Vertex se ek topic-anusaar illustration. Path ya "" (kuch bhi galat
    ho - band ho, kota poora ho, SA na mile, banaate waqt fail ho)."""
    if not _ai_on():
        return ""
    if _ai_used_today() >= _ai_max_per_day():
        return ""
    sa = _ai_sa_path()
    if not sa:
        return ""
    try:
        import json
        with open(sa, encoding="utf-8") as f:
            sa_json = json.load(f)
        project = cfg.get("veo", "project") or sa_json.get("project_id") or ""
        if not project:
            return ""
        prompt = _ai_prompt(category, entity, key_fact, kicker)
        key = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:16]
        out = os.path.join(workdir or ".", "thumb_ai_%s.jpg" % key)
        if os.path.exists(out) and os.path.getsize(out) > 15000:
            return out
        import vertex
        ok, err = vertex.generate(sa, project, _ai_location(), _ai_model(),
                                  prompt, out)
        if ok:
            _ai_note_used()
            return out
        print("[thumb] AI backdrop nahi bani:", err, flush=True)
    except Exception as e:
        print("[thumb] AI backdrop mein gadbad:", e, flush=True)
    return ""

# REEL KI THUMBNAIL 9:16 HOTI HAI - AUR YE PEHLE GALAT THA
#
# Pehle yahan likha tha "thumbnail HAMESHA 1280x720 ka hota hai, Reel ki
# bhi". Wo galat tha, aur uska nuksaan dikhta bhi nahi tha: YouTube khud
# kehta hai ki khadi video par 16:9 wali custom thumbnail ko wo HATA kar
# apni banayi hui 4:5 wali laga deta hai (home, explore aur subscription
# tino jagah). Yaani har Reel par thumbnail ki saari mehnat phenki ja rahi
# thi - aur uski jagah machine ka kaata hua frame lag raha tha.
#
# Unka apna sujhaav: Shorts ke liye 9:16. Isliye ab do naap hain.
_VERT = False
_ANCHOR = False   # is thumbnail mein AI anchor daayein hai (build() tay karta hai)


def set_size(vertical=False):
    """Naap tay karo. Har jagah TW/TH se hi hisaab hota hai, isliye itna
    kaafi hai - aur yahi baat is file ko dono shakl mein chalne deti hai."""
    global TW, TH, _VERT
    _VERT = bool(vertical)
    TW, TH = (1080, 1920) if _VERT else (1280, 720)
    return TW, TH

FONT = "Noto Sans Devanagari"
CH_W = 0.32       # aam Devanagari - sirf tab jab naap na ho paaye
CH_W_SAFE = 0.45  # sabse chaudi naapi gayi baat se bhi upar
LINE_H = 0.85     # ek line ki oonchai

NAVY = (11, 18, 32)
RED = (200, 16, 46)
DEEP_RED = (140, 18, 37)
GOLD = (255, 198, 26)
PAPER = (245, 243, 238)

CHANNEL_HI = "सत्ययात्रा न्यूज"


# ---------- chhoti madad ----------

def _hx(rgb):
    return "&H00%02X%02X%02X&" % (rgb[2], rgb[1], rgb[0])   # ASS = BGR


def _esc(s):
    return str(s).replace("\\", "").replace("{", "").replace("}", "").strip()


def _wrap(text, max_chars):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if len(t) <= max_chars or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


_CHW_CACHE = {}


def _measure_ch_w(text, probe=100):
    """Is BAAT ki asli chaudai naapo - andaza mat lagao.

    YAHAN EK CHUPI HUI GALTI THI, AUR WO HAR THUMBNAIL PAR THI
    ==========================================================
    CH_W ek hi ankda tha: 0.32. Wo "aam" Devanagari ke liye naapa gaya tha
    aur aam baaton par theek baithta hai. Par chaudai baat-dar-baat badalti
    hai, aur bahut badalti hai. Maine paanch asli headline naapi:

        प्रयागराज में नई योजना शुरू      0.307
        नोएडा डीएम पर पांच लाख जुर्माना  0.325
        दो शिक्षक निलंबित                0.327
        भारत की भूमिका पर बड़ा बयान      0.346
        बीआरआईसीएस शिखर सम्मेलन          0.418   <- 30% chaudi

    Aakhri wali par har akshar poora chaudi jagah leta hai - koi matra
    upar-neeche nahi baithti, sab bagal mein failte hain. Aisi headline
    0.32 ke hisaab se "sama jayegi" maani jaati thi, par sach mein dono
    kinaron se bahar nikal jaati thi. Aur ASS ka WrapStyle 2 use todta
    nahi - wo use KAAT deta hai. Isliye shabd chup-chaap gayab ho rahe
    the, aur ye chaudi thumbnail par bhi ho raha tha, sirf Reel par nahi.

    Ab andaza hatta hai. Har baat ko ek baar wahi libass se chhaap kar uski
    asli chaudai naap lete hain, phir usi se size tay hota hai. Ek thumbnail
    par ye do baar chalta hai aur us par pal bhar lagta hai - ek kati hui
    headline ki keemat uss se kahin zyada hai.
    """
    key = str(text or "")
    if not key.strip():
        return CH_W
    if key in _CHW_CACHE:
        return _CHW_CACHE[key]

    val = CH_W_SAFE
    try:
        import tempfile
        from PIL import Image as _Im
        with tempfile.TemporaryDirectory() as d:
            doc = [
                "[Script Info]", "ScriptType: v4.00+",
                "PlayResX: 6000", "PlayResY: 300", "WrapStyle: 2",
                "ScaledBorderAndShadow: yes", "",
                "[V4+ Styles]",
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
                "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
                "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
                "Alignment,MarginL,MarginR,MarginV,Encoding",
                "Style: M,%s,%d,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,"
                "&H00000000&,-1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"
                % (FONT, probe),
                "", "[Events]",
                "Format: Layer,Start,End,Style,Name,MarginL,MarginR,"
                "MarginV,Effect,Text",
                "Dialogue: 0,0:00:00.00,0:00:10.00,M,,0,0,0,,"
                "{\\an7\\pos(20,20)}" + key.replace("\n", " "),
            ]
            ap = os.path.join(d, "m.ass")
            with open(ap, "w", encoding="utf-8") as f:
                f.write("\n".join(doc))
            r = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                 "-i", "color=c=black:s=6000x300", "-vf", "ass=m.ass",
                 "-frames:v", "1", "m.png"],
                cwd=d, capture_output=True)
            if r.returncode == 0:
                bb = _Im.open(os.path.join(d, "m.png")).convert("L") \
                        .point(lambda p: 255 if p > 40 else 0).getbbox()
                if bb and bb[2] > 30:
                    got = (bb[2] - 20) / float(len(key)) / float(probe)
                    # Bahut ajeeb naap aaye to use mat maniye.
                    if 0.15 <= got <= 0.90:
                        val = got * 1.04      # thodi si gunjaish
    except Exception:
        pass

    _CHW_CACHE[key] = val
    return val


def _chw_worst(text):
    """Poori baat ka AUSAT nahi - sabse chaudi SHABD ka naap.

    Ye doosri baar ki galti thi, aur wo pehli se bhi baareek hai. Poori
    headline naapne par ausat aaya 0.375 - aur wo sach tha. Par line todne
    ke baad pehli line bani "बीआरआईसीएस शिखर", aur wo akeli 0.418 chaudi
    thi. Ausat ke hisaab se wo sama jaani chahiye thi; asal mein kinare se
    bahar nikal gayi.

    Line kahan tootegi ye pehle se pata nahi hota, isliye sabse bure shabd
    ka naap hi mana jaata hai. Isse text kabhi-kabhi zaroorat se thoda
    chhota banta hai. Wo sauda theek hai: thoda chhota padha ja sakta hai,
    kata hua nahi.
    """
    words = [w for w in str(text or "").split() if w]
    if not words:
        return _measure_ch_w(text)
    return max([_measure_ch_w(text)] + [_measure_ch_w(w) for w in words])


def _fit(text, avail_px, band_px, max_size, min_size, max_lines):
    """Sabse bada size jisme text di gayi jagah mein poora sama jaaye."""
    chw = _chw_worst(text)
    size = max_size
    while size >= min_size:
        per_line = max(4, int(avail_px / (chw * size)))
        lines = _wrap(text, per_line)
        if len(lines) <= max_lines and len(lines) * size * LINE_H <= band_px:
            return size, lines
        size -= 2
    per_line = max(4, int(avail_px / (chw * min_size)))
    return min_size, _wrap(text, per_line)[:max_lines]


def _cover(img, w, h):
    """Crop karke bharo — squeeze mat karo."""
    sw, sh = img.size
    s = max(w / float(sw), h / float(sh))
    img = img.resize((max(1, int(sw * s)), max(1, int(sh * s))), Image.LANCZOS)
    sw, sh = img.size
    # chehre/vishay aam taur par beech-upar hote hain
    left = (sw - w) // 2
    top = int((sh - h) * 0.42)
    return img.crop((left, top, left + w, top + h))


def _grad(size, rgb, a0, a1, horizontal=False):
    """Ek taraf se doosri taraf ghulta hua parda. drawbox ki patti-jaisi
    kinaari nahi banti — isliye PIL se, ffmpeg se nahi."""
    w, h = size
    n = w if horizontal else h
    strip = Image.new("L", (n, 1))
    px = strip.load()
    for i in range(n):
        f = i / float(max(1, n - 1))
        px[i, 0] = int(a0 + (a1 - a0) * f)
    mask = strip.resize((w, h)) if horizontal else strip.transpose(
        Image.ROTATE_90).resize((w, h))
    layer = Image.new("RGB", (w, h), rgb)
    return layer, mask


# ---------- plate ----------

def _tint(img, strength=0.74):
    """Har tasveer ko channel ke rang mein dhaal do.

    Vertex kabhi halke slate background par illustration deta hai, kabhi
    gehre par; article ki photo to kuchh bhi ho sakti hai. Bina is kadam ke
    aadhe thumbnail neele aur aadhe safed dikhte — ek channel ki nahi lagte.
    Duotone poori tasveer ko ek hi paalette mein le aata hai, aur asli rang
    ka thoda hissa (laal jhanda, laal accent) blend se bacha rehta hai."""
    # White point jaan-boojhkar 255 nahi. Illustration ka khaali background
    # varna chamakdaar chaandi ban jaata tha aur text se dhyaan cheenta tha.
    g = ImageOps.grayscale(img)
    duo = ImageOps.colorize(g, black=(7, 12, 22), white=(146, 158, 178),
                            mid=(48, 63, 86))
    return Image.blend(img, duo, strength)


def _open_art(art_path, category="", style="grid", workdir="",
             entity="", key_fact="", kicker=""):
    """(image_or_None, ai_generated_bool). ai_generated sirf tab True jab
    ART SACH MEIN AI SE BANI HO - taaki caller sirf tabhi "AI चित्रण" label
    lagaaye, purane geometric backdrop par kabhi nahi (wo AI ka chitran
    nahi hai)."""
    if art_path and os.path.exists(art_path):
        try:
            return _tint(Image.open(art_path).convert("RGB")), False
        except Exception:
            pass

    # Koi sacchi tasveer nahi mili - pehle AI se bani, VISHAY ke hisaab se
    # illustration aazmaate hain (band ho, kota poora ho, ya kuch fail ho
    # jaaye to chup-chaap khaali laut aata hai, neeche wala purana rasta
    # chal jaata hai).
    try:
        ai_path = ai_backdrop(category, entity, key_fact, kicker, workdir)
        if ai_path and os.path.exists(ai_path):
            return _tint(Image.open(ai_path).convert("RGB"), strength=0.35), True
    except Exception as e:
        print("[thumb] AI backdrop istemal nahi ho paya:", e, flush=True)

    # Sabse aakhri sahara - wahi purana designed backdrop jo video mein
    # lagta hai. Koi jhooth nahi bolta (isliye ai_generated=False), bas
    # geometric pattern hai - "media mein blank kuchh nahi hota" wala
    # usool yahan bhi kaayam rehta hai.
    try:
        import backdrop
        # Backdrop ka naap wahi jo thumbnail ka hai.
        #
        # Ye line zaroori hai kyunki backdrop ka naap ek jagah rakha jaata
        # hai aur render use badal kar chhod deta hai. Pehle yahan hamesha
        # False tha - us waqt thumbnail hamesha chaudi hi banti thi, to wo
        # theek tha. Ab Reel ki thumbnail khadi banti hai, isliye backdrop
        # ko bhi wahi shakl chahiye - warna 16:9 ka backdrop 9:16 mein
        # katkar aata aur banavat bigad jaati.
        backdrop.set_size(_VERT)
        p = os.path.join(workdir or ".", "thumb_backdrop.png")
        backdrop.build(style or "grid", category or "civic", 7, p)
        return _tint(Image.open(p).convert("RGB"), strength=0.45), False
    except Exception:
        return None, False


def _plate_split(art):
    """A — 'Split card'. Baayein gehra panel + text, daayein tasveer.
    Sabse sanjeeda; bade national channels isi taraf jhukte hain."""
    im = Image.new("RGB", (TW, TH), NAVY)
    px = int(TW * 0.54)
    if art is not None:
        right = _cover(art, px, TH)
        layer, mask = _grad((px, TH), NAVY, 190, 40, horizontal=True)
        right.paste(layer, (0, 0), mask)
        im.paste(right, (TW - px, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([TW - px - 7, 0, TW - px, TH], fill=RED)          # seam
    d.rectangle([0, TH - 10, TW, TH], fill=DEEP_RED)              # base rule
    return im


def _slab_y():
    return int(TH * 0.539)


def _plate_slab(art):
    """B — 'Slab'. Poori tasveer, neeche mota laal takhta.
    Sabse zor-daar; Hindi news feed mein yahi shakl sabse jaani-pehchaani."""
    im = Image.new("RGB", (TW, TH), NAVY)
    # Takhta frame ke 54% par shuru hota hai. Pehle yahan 388 likha tha -
    # wo 720 ka 54% hi hai, bas jama hua tha. Anupat mein likhne se yahi
    # banavat khadi thumbnail par bhi apne aap sahi baith jaati hai.
    sy = _slab_y()
    if art is not None:
        # Tasveer ko sirf upar wale hisse mein rakho — takhte ke neeche wo
        # dikhti hi nahi, to poori frame bharna bekaar tha aur usme vishay
        # crop hokar kat jaata tha.
        im.paste(_cover(art, TW, sy), (0, 0))
    layer, mask = _grad((TW, sy), (0, 0, 0), 30, 130)
    im.paste(layer, (0, 0), mask)
    d = ImageDraw.Draw(im)
    d.rectangle([0, sy, TW, TH], fill=DEEP_RED)
    d.rectangle([0, sy, TW, sy + 9], fill=GOLD)                   # takhte ki dhaar
    return im


def _plate_poster(art):
    """C — 'Poster'. Gehra maidan, daayein tasveer ek panel mein baithi hui.
    Sabse saaf; explainer aur lambi khabar ke liye."""
    im = Image.new("RGB", (TW, TH), NAVY)
    d = ImageDraw.Draw(im)
    for i in range(0, TW + TH, 46):                               # halki dhaari
        d.line([(i, 0), (i - TH, TH)], fill=(17, 26, 44), width=1)
    if art is not None:
        # Pehle ise chaukor frame mein rakha tha — wo katkar chipkaayi hui
        # clip-art lagti thi. Ab tasveer daayein kinare se bahar nikalti hai
        # aur baayein taraf ghul kar background mein mil jaati hai.
        cw = 600
        col = _cover(art, cw, TH)
        layer, mask = _grad((cw, TH), NAVY, 255, 0, horizontal=True)
        col.paste(layer, (0, 0), mask)
        im.paste(col, (TW - cw, 0))
        d = ImageDraw.Draw(im)
    d.rectangle([0, TH - 76, TW, TH - 68], fill=RED)
    return im


PLATES = {"split": _plate_split, "slab": _plate_slab, "poster": _plate_poster}


def _plate_anchor(art, anchor):
    """D - 'Anchor'. Jaankari wali video ki apni AI anchor daayein, vishay
    ki tasveer baayein text ke peeche halki si. Chehra thumbnail par
    click-through badhata hai - aur ye wahi chehra hai jo video mein
    shuru aur ant mein dikhta hai, koi dhokha nahi. (Sep 2026)

    anchor = sy_explainer.thumb_still() ki tasveer, 640:720 anupat mein."""
    im = Image.new("RGB", (TW, TH), NAVY)
    if art is not None:
        # Vishay ki tasveer poori frame par, par gehri - text uske upar
        # padhna hai, aur daayein hissa anchor dhak degi.
        bg = _cover(art, TW, TH)
        layer, mask = _grad((TW, TH), NAVY, 150, 235, horizontal=True)
        bg.paste(layer, (0, 0), mask)
        im.paste(bg, (0, 0))
    pw = int(TW * 0.50)
    a = _cover(anchor, pw, TH)
    # Baayein kinaara dheere se ghul jaaye - chipkaayi hui patti na lage.
    m = Image.new("L", (pw, TH), 255)
    ramp = int(pw * 0.28)
    md = ImageDraw.Draw(m)
    for i in range(ramp):
        md.line([(i, 0), (i, TH)], fill=int(255 * (i / float(ramp)) ** 1.4))
    im.paste(a, (TW - pw, 0), m)
    d = ImageDraw.Draw(im)
    d.rectangle([0, TH - 10, TW, TH], fill=DEEP_RED)
    return im


# ---------- text ----------

def _stack(entity, rest, colw, band, max_size, min_size, max_lines):
    """Text ko do register mein baantta hai: pehchaan ka naam upar aur sabse
    bada, uska anjaam neeche.

    Kyun: news feed mein har thumbnail already khaas hota hai — sab par koi
    na koi thos baat likhi hai. Isliye aur zyada tafseel se farq nahi padta;
    farq is se padta hai ki kaun si tafseel sabse pehle padhi jaati hai. Jo
    naam dekhne wala pehle se jaanta hai, wahi ek pal mein pakad banata hai.
    'दो शिक्षक निलंबित' sach hai par kisi ko nahi jaanta; 'RSS' ko sab
    jaante hain. Isliye naam pehle, ghatna baad mein.

    Ye chamak-dhamak nahi hai. Naam wahi aata hai jo khabar mein sach mein
    hai — bada likhna alag baat hai, jhootha likhna alag."""
    if not entity:
        size, lines = _fit(rest, colw, band, max_size, min_size, max_lines)
        return [(ln, size, "w") for ln in lines]

    e_size, e_lines = _fit(entity, colw, int(band * 0.52), max_size, 74, 1)
    used = len(e_lines) * e_size * LINE_H + 12
    r_size, r_lines = _fit(rest, colw, max(70, band - used),
                           max(min_size, int(e_size * 0.76)), min_size,
                           max(1, max_lines - 1))
    return ([(ln, e_size, "g") for ln in e_lines]
            + [(ln, r_size, "w") for ln in r_lines])


def _events(style, text, place, keyword, ai_label, entity=""):
    """Har direction ka apna text-kshetra hai, isliye layout alag-alag."""
    white, gold, paper = _hx((255, 255, 255)), _hx(GOLD), _hx(PAPER)
    head, ev = [], []

    def st(name, size, col, align, outline=0, shadow=0, bcol=None, pad=0):
        # BorderStyle 3 = libass khud text ke naap ka thos dabba banata hai.
        # Dhyaan: us dabbe ka rang OutlineColour se aata hai, BackColour se
        # nahi — pehle yahi galti thi aur laal chip kaali ban gayi thi.
        bs = 3 if bcol else 1
        bd = pad if bcol else outline
        outc = bcol or "&H00000000&"
        head.append(
            "Style: %s,%s,%d,%s,%s,%s,&H00000000&,-1,0,0,0,100,100,0,0,%d,%d,%d,7,0,0,0,1"
            % (name, FONT, size, col, col, outc, bs, bd, shadow))

    def mark(line):
        # Entity ho to wahi chamak hai — do jagah sona lagana dono ko kamzor
        # kar deta hai. Keyword sirf tab jab koi jaana-pehchana naam hi na ho.
        if entity or not keyword:
            return line
        return re.sub(r"(^|\s)(%s)(\s|$)" % re.escape(keyword),
                      lambda m: m.group(1) + "{\\c" + gold + "}" +
                      m.group(2) + "{\\c" + white + "}" + m.group(3), line)

    def draw(rows, x, top, an):
        """Har line apne naap ki, isliye har line ka apna dialogue."""
        y = top
        for ln, size, col in rows:
            nm = "L%d%s" % (size, col)
            if nm not in seen:
                st(nm, size, gold if col == "g" else white,
                   align=7, outline=4, shadow=3)
                seen.add(nm)
            ev.append("Dialogue: 0,0:00:00.00,0:00:10.00,%s,,0,0,0,,"
                      "{\\%s\\pos(%d,%d)}%s" % (nm, an, x, y, mark(ln)))
            y += int(size * LINE_H)

    def height(rows):
        return sum(int(s * LINE_H) for _, s, _ in rows)

    seen = set()

    if style == "split":
        pad, colw = 62, int(TW * 0.46) - 110
        if _ANCHOR:
            # Anchor wali shakl: text ke liye thodi zyada jagah aur ek line
            # zyada - warna lamba vaakya aakhri shabd kho deta tha.
            colw = int(TW * 0.52) - 90
            rows = _stack(entity, text, colw, 470, 140, 52, 4)
        else:
            rows = _stack(entity, text, colw, 400, 148, 62, 3)
        draw(rows, pad, int((TH - height(rows)) / 2) + 18, "an7")
        if place:
            st("Chip", 46, white, align=7, bcol=_hx(RED), pad=15)
            ev.append("Dialogue: 0,0:00:00.00,0:00:10.00,Chip,,0,0,0,,"
                      "{\\an7\\pos(%d,%d)}%s" % (pad, 60, _esc(place)))
        st("Sig", 38, _hx((255, 210, 210)), align=7)
        ev.append("Dialogue: 0,0:00:00.00,0:00:10.00,Sig,,0,0,0,,"
                  "{\\an7\\pos(%d,%d)}%s" % (pad, TH - 92, CHANNEL_HI))

    elif style == "slab":
        colw = TW - 110
        # Takhte ke andar ki jagah - naap se nikali hui, jami hui nahi.
        # Chaudi thumbnail par ye wahi 262 aata hai jo pehle likha tha;
        # khadi par kahin zyada, aur wahi chahiye - wahan likhne ki jagah
        # sach mein zyada hai.
        top = _slab_y() + 12
        box = TH - top - 58
        rows = _stack(entity, text, colw, box, 156, 66, 3 if not _VERT else 5)
        draw(rows, TW // 2, top + int((box - height(rows)) / 2), "an8")
        if place:
            st("Chip", 50, white, align=7, bcol=_hx(RED), pad=16)
            ev.append("Dialogue: 0,0:00:00.00,0:00:10.00,Chip,,0,0,0,,"
                      "{\\an7\\pos(%d,%d)}%s" % (52, 44, _esc(place)))
        # Naam takhte ke andar, sabse neeche — pehle wo tasveer aur takhte ke
        # beech latak raha tha, kisi patti ka hissa nahi lagta tha.
        st("Sig", 36, _hx((255, 214, 214)), align=7)
        ev.append("Dialogue: 0,0:00:00.00,0:00:10.00,Sig,,0,0,0,,"
                  "{\\an1\\pos(%d,%d)}%s" % (52, TH - 22, CHANNEL_HI))

    else:  # poster
        colw = TW - 640
        rows = _stack(entity, text, colw, 420, 150, 58, 4)
        draw(rows, 60, int((TH - 74 - height(rows)) / 2) + 10, "an7")
        if place:
            st("Chip", 44, white, align=7, bcol=_hx(RED), pad=14)
            ev.append("Dialogue: 0,0:00:00.00,0:00:10.00,Chip,,0,0,0,,"
                      "{\\an7\\pos(%d,%d)}%s" % (60, 74, _esc(place)))
        st("Sig", 40, paper, align=7)
        ev.append("Dialogue: 0,0:00:00.00,0:00:10.00,Sig,,0,0,0,,"
                  "{\\an7\\pos(%d,%d)}%s" % (60, TH - 56, CHANNEL_HI))

    if isinstance(ai_label, str) and ai_label:
        # Anchor ke kapdon par (halka dupatta) saada safed text doob jaata
        # tha - isliye gehre dabbe mein.
        st("AiBox", 26, white, align=7, bcol="&H70000000&", pad=7)
        ev.append("Dialogue: 0,0:00:00.00,0:00:10.00,AiBox,,0,0,0,,"
                  "{\\an9\\pos(%d,%d)}%s" % (TW - 24, TH - 60, ai_label))
    elif ai_label:
        # Chhota hai par hai. Jo tasveer AI ne banayi hai wo thumbnail par bhi
        # AI ki hai — dekhne wale ko wahi bataya jaata hai jo sach hai.
        st("Ai", 26, _hx((225, 225, 225)), align=7)
        ev.append("Dialogue: 0,0:00:00.00,0:00:10.00,Ai,,0,0,0,,"
                  "{\\an9\\pos(%d,%d)}%s" % (TW - 22, TH - 58,
                      ai_label if isinstance(ai_label, str) else "AI चित्रण"))

    return head, ev


def _ass(style, text, place, keyword, ai_label, path, entity=""):
    head, ev = _events(style, _esc(text), place, keyword, ai_label, _esc(entity))
    doc = ["[Script Info]", "ScriptType: v4.00+",
           "PlayResX: %d" % TW, "PlayResY: %d" % TH,
           "WrapStyle: 2", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
           "[V4+ Styles]",
           "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
           "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,"
           "ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,"
           "MarginL,MarginR,MarginV,Encoding"]
    doc += head
    doc += ["", "[Events]",
            "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
    doc += ev
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(doc) + "\n")


# ---------- bahar ka darwaza ----------

def build(out_path, text, place="", keyword="", art_path="",
          style="split", ai_label=True, workdir="", category="",
          backdrop_style="grid", entity="", vertical=False,
          art_is_ai=False, anchor_path=""):
    """art_is_ai: caller ko pehle se pata ho ki art_path khud AI se bana
    hai (jaise Veo ke AI-chitran clip ka nikala hua frame) - file-hona se
    ye pata nahi chalta, isliye caller batata hai. Sirf tabhi zaroori hai
    jab art_path diya gaya ho; khud is file ke andar banayi gayi AI art
    (koi sacchi tasveer na milne par) apne aap sahi label paati hai."""
    """Ek thumbnail banao. (True, '') ya (False, wajah) laut'ta hai —
    thumbnail na banne se poori video ruk nahi sakti."""
    try:
        set_size(vertical)
        # Khadi thumbnail par sirf 'slab' chalta hai, aur ye rok soch kar
        # lagayi hai. Baaki do banavat chaudi frame ki hain: 'split' tasveer
        # ko daayein 54% mein rakhta hai aur 'poster' 600 pixel ke column
        # mein - dono khadi frame mein bemaani ho jaate hain. Slab ki shakl
        # (upar tasveer, neeche laal takhta) khadi frame mein waise hi
        # baithti hai jaise chaudi mein.
        if vertical:
            style = "slab"
        work = workdir or os.path.dirname(os.path.abspath(out_path))
        plate_p = os.path.join(work, "thumb_plate.png")
        ass_p = os.path.join(work, "thumb.ass")

        art, ai_generated = _open_art(art_path, category, backdrop_style, work,
                                       entity=entity, key_fact=text, kicker=keyword)
        global _ANCHOR
        _ANCHOR = False
        anchor = None
        if anchor_path and not vertical and os.path.exists(anchor_path):
            try:
                anchor = Image.open(anchor_path).convert("RGB")
            except Exception:
                anchor = None
        if anchor is not None:
            # Text baayein ke column mein - wahi jagah jo 'split' ki hai.
            style = "split"
            _ANCHOR = True
            _plate_anchor(art, anchor).save(plate_p)
        else:
            PLATES.get(style, _plate_split)(art).save(plate_p)
        # AI ka label sirf tab jab tasveer sach mein AI ki ho: ya to caller
        # ne pehle se bataya (art_is_ai - jaise Veo clip ka frame), ya
        # humne khud koi sacchi tasveer na milne par Vertex se banayi
        # (ai_generated). Purana geometric backdrop kabhi nahi - wo AI ka
        # chitran hai hi nahi, us par ye label jhootha hoga.
        # Entity text ke shuru mein aata hai to use dobara mat likho — wahi
        # upar wali badi line ban jaata hai.
        body = str(text or "").strip()
        ent = str(entity or "").strip()
        if ent and body.lower().startswith(ent.lower()):
            body = body[len(ent):].lstrip(" :-–—·,")
        if not body:
            body, ent = ent, ""

        lab = ai_label and (art_is_ai or ai_generated)
        if ai_label and anchor is not None:
            # Anchor AI ki hai - thumbnail par bhi bataya jaata hai.
            lab = "AI प्रस्तुतकर्ता" + (" · AI चित्रण" if lab else "")
        _ass(style, body, place, keyword, lab, ass_p, ent)

        # ffmpeg ko usi folder ke andar se chalate hain aur file ka sirf naam
        # dete hain — poora path NAHI.
        #
        # Kyun: Windows par path "C:\SatyaYatra\work\..." hota hai, aur ffmpeg
        # ke filter mein colon options ko alag karta hai. Us colon ko haath se
        # escape karne ki koshish ki thi aur wahi chup-chaap fail ho rahi thi
        # — thumbnail banti hi nahi thi aur wajah kahin dikhti bhi nahi thi.
        # render_core yahi tarika pehle se istemaal karta hai (ass=overlay.ass)
        # aur wahan kabhi ye samasya aayi hi nahi.
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", os.path.basename(plate_p),
               "-vf", "ass=" + os.path.basename(ass_p),
               "-frames:v", "1", "-q:v", "2", os.path.abspath(out_path)]
        r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out_path):
            return False, (r.stderr or "ffmpeg fail")[:300]
        # YouTube ki hadd 2 MB hai; q=2 par aam taur par ~250 KB aata hai.
        if os.path.getsize(out_path) > 2 * 1024 * 1024:
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", out_path,
                            "-q:v", "6", out_path + ".tmp.jpg"],
                           capture_output=True)
            os.replace(out_path + ".tmp.jpg", out_path)
        return True, ""
    except Exception as e:
        return False, repr(e)

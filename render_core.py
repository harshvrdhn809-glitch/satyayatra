"""
SatyaYatra render core — ek bulletin video banata hai.

Look aapke apne channel se liya gaya hai (purani videos ka screen recording
dekh kar): upar-baayein location bug, upar-daayein brand, neeche do-tehri
lower third — gehri laal patti mein headline, uske neeche safed patti mein
chalti hui ticker. Shuru mein title card, aakhir mein end card.

Footage ho to footage; na ho to designed backdrop. Baaki sajaawat dono mein
ek jaisi rehti hai — isliye video hamesha ek hi channel ki lagti hai.

Devanagari ke liye ffmpeg ka drawtext use NAHI hota: wo complex script
shaping nahi karta aur matra-conjunct todh deta hai. libass HarfBuzz se
shaping karta hai, isliye saara text ek .ass file mein banta hai.
"""

import json
import os
import re
import subprocess
import wave

import backdrop

# ==================== BRAND ====================
CHANNEL_HI = "सत्ययात्रा न्यूज"
CHANNEL_EN = "SatyaYatra News"
# Apna logo yahan daal sakte hain (PNG, gol, paardarshi background).
# Khaali chhodenge to naam text mein aayega.
LOGO_PATH = ""

STRAP_RED = "8c1225"      # headline patti - gehri laal
TICKER_BG = "f2f0eb"      # ticker patti - halka safed
TICKER_INK = "1a1a1a"
BUG_RED = "c8102e"

# Background music. Apni licensed track ka poora path yahan daaliye (mp3/m4a/wav).
# Khaali chhodenge to ek halka sa synthesized bed banega - saaf, bina licence
# ke jhanjhat ke, par ek asli composed track se kamtar. Dono haalat mein awaaz
# ke neeche duck hota hai, isliye khabar dabti nahi.
MUSIC_PATH = ""
MUSIC_DB = -26.0          # bed kitna dheema (awaaz ke saapeksh)

# ASLI MUSIC KA FOLDER (Sep 2026, Harshvardhan: "background music nahi,
# isliye videos sadi-sadi robotic lagti hain"). Upar ka synthesized bed teen
# sine suron ki ek gunjan bhar hai - wahi robotic ehsaas. Ab assets/music/
# mein licensed/royalty-free track (mp3/m4a/wav) rakhiye:
#   assets/music/gyan/   - jaankari video (gy_/kb_/tc_/yj_) ke liye
#   assets/music/khabar/ - khabar/bulletin ke liye (gambhir, dheemi dhun)
#   assets/music/        - dono ke liye, agar upar wala khaali ho
# Har video ko ek track milta hai (story id se tay - dobara render par
# wahi). Koi track na ho to purana synthesized bed hi chalta hai.
MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "music")
TRACK_DB = -22.0          # asli track ka star (sine bed se thoda upar)
_MUSIC_EXT = (".mp3", ".m4a", ".wav", ".aac", ".ogg")


def pick_music(job_id):
    """Is video ke liye ek track - beat ke folder se, warna saanjhe folder se."""
    jid = str(job_id or "")
    group = "gyan" if jid.startswith(("gy_", "kb_", "tc_", "yj_")) else "khabar"
    for d in (os.path.join(MUSIC_DIR, group), MUSIC_DIR):
        try:
            ts = sorted(f for f in os.listdir(d)
                        if f.lower().endswith(_MUSIC_EXT)
                        and os.path.isfile(os.path.join(d, f)))
        except OSError:
            ts = []
        if ts:
            k = sum(ord(c) for c in jid) % len(ts)
            return os.path.join(d, ts[k])
    return ""
# ===============================================

W, H = backdrop.W, backdrop.H
FPS = 30

# Lower third ki jagah
# Neeche se upar naapa gaya. Pehle ticker ke neeche 114px ki khaali gehri
# patti bach jaati thi - screen par wahi sabse chaudi lakeer lagti thi, jabki
# usmein sirf do chhote label the.
# Poora lower third 32px upar khiska diya gaya hai. Wajah: credit aur
# AI label neeche daayein-baayein baithte hain, aur badi ticker patti ke
# baad unke liye jagah hi nahi bachti thi - wo patti ke upar chadh kar
# uske halke rang par grey mein gum ho jaate the.
# NAAP EK HI JAGAH SE TAY HOTA HAI. Video 1920x1080 ki hai par dekhi phone
# par jaati hai, jahan poori chaudai lagbhag 360 point ki hoti hai - yaani
# jo yahan likha hai uska 0.1875 guna. 40px ka text wahan 7 point ka reh
# jaata hai; wo padha hi nahi jaata. Isliye har naap ke saamne uska phone
# wala naap likha hai, aur koi bhi padhne layak cheez 6.5 point se neeche
# nahi hai.
PHONE = 0.1875           # 1920 -> 360
# LAAL PATTI KA NAAP TAY NAHI HAI - HEADLINE KE HISAAB SE BANTA HAI.
#
# Pehle patti ki oonchai pakki thi aur text usme thoosa jaata tha. Do line
# wali headline patti se bahar nikal jaati thi, aur ek line wali headline
# ke neeche 98px khaali padi reh jaati thi - dono hi bure lagte the, aur
# dono ki wajah ek hi thi: patti pehle tay ho rahi thi, text baad mein.
#
# Ab ulta hai. Pehle headline ka naap tay hota hai, phir patti utni hi
# banti hai jitni chahiye - upar-neeche barabar saans ke saath. Patti ka
# NEECHE ka kinaara hamesha ek hi jagah rehta hai (STRAP_BOTTOM), isliye
# uske neeche ki accent lakeer aur ticker kabhi hilte nahi; patti sirf
# upar ki taraf badhti hai.
STRAP_BOTTOM = 906              # yahan patti khatam - ye kabhi nahi hilta
STRAP_PAD = 16                  # text ke upar aur neeche, dono taraf
# 22 se 16: patti ki oonchai wahi 112 rehti hai, par us oonchai ka
# 39% khaali gaddi mein ja raha tha. Ab wo jagah AKSHAR ko milti hai.
STRAP_MIN_H = 112               # patti itni to hamesha rahegi
STRAP_FONT = 96                 # phone par ~18 point - ek hi line, hamesha
STRAP_SPEED = 150.0             # chalne wali headline - px prati second
STRAP_Y, STRAP_H = 800, 106     # bina headline ke default (jaanch ke liye)
TICK_Y, TICK_H = 912, 96        # ticker patti - 60px text saans le sake
BOTTOM_MV = 14                  # credit / AI label ki neeche se doori
TICK_FONT = 72                  # phone par ~13 point - chalte hue bhi padha jaata hai

# Devanagari ka ek akshar font size ka itna guna chaudai leta hai. Ye asli
# render se naapa gaya hai (font 40/52/58/64 - chaaron par 0.320 nikla),
# andaaza nahi. Isi se tay hota hai ki headline kitni badi ho sakti hai.
CH_W = 0.32

# LINE_H = 0.85 yahan galat likha hua tha, aur usi ek ankde se laal patti
# ka text patti se bahar nikal raha tha.
#
# Asli naap libass se render karke naape gaye (font 52/66/78/92/104, ek se
# teen line tak - paanchon par wahi nikla):
#   - ek line ke akshar ki oonchai   = font ka 0.82 guna
#   - do line ke beech ki doori      = font ka 1.00 guna (0.85 nahi)
#
# Yaani N line ki kul oonchai = font * (0.82 + (N-1) * 1.00).
# Do line 78 par: 78 * 1.82 = 142px. Purana hisaab 132px batata tha, aur
# patti ke andar 134px hi jagah thi - isliye code ko lagta tha ki sama gaya
# hai, jabki screen par text patti ke upar chadh jaata tha.
INK_H = 0.82        # ek line ke akshar kitne oonche
LINE_ADV = 1.00     # do line ke beech kitni doori

# Aur ek baat jo aankh pakadti hai par hisaab nahi: libass jab beech mein
# rakhta hai to wo LINE BOX ko beech mein rakhta hai, akshar ko nahi. Box
# mein neeche descender ki jagah reserved rehti hai jo Devanagari mein
# aksar khaali jaati hai, isliye akshar dikhne mein upar khisak jaate hain -
# theek font ka 9.5%. Isi wajah se patti ke upar jagah nahi bachti thi aur
# neeche 13px khaali padi rehti thi. Ise utna hi neeche khiska kar theek
# karte hain.
INK_RISE = 0.095


# Wahi font jo har style line mein likha jaata hai. Ek jagah rakha
# gaya taaki naapne wala aur chhaapne wala kabhi alag na ho jayein.
FONT_NAME = "Noto Sans Devanagari"

_WPX_CACHE = {}


def text_width_px(text, size):
    """Is baat ki asli chaudai, usi libass se jo video par lagta hai.

    CH_W (0.32) asli naap hai par AUSAT hai. Devanagari mein kuch baatein
    us se 30% tak chaudi hoti hain - jinme matra upar-neeche nahi baithti
    aur har akshar poori jagah leta hai ("बीआरआईसीएस शिखर" par 0.418 naapa
    gaya). Aisi headline ausat ke hisaab se patti mein sama jaati thi, aur
    screen par uska aakhri hissa kat jaata tha.

    Ek render par ye ek baar chalta hai aur us par pal bhar lagta hai.
    Naap na ho paye to ausat par lautkar kaam chalta rehta hai - ye jaanch
    render girane ki wajah kabhi nahi banni chahiye.
    """
    key = (str(text or ""), int(size))
    if key in _WPX_CACHE:
        return _WPX_CACHE[key]
    fallback = int(len(key[0]) * CH_W * size)
    val = fallback
    try:
        import tempfile
        from PIL import Image as _Im
        probe = 100
        with tempfile.TemporaryDirectory() as d:
            doc = [
                "[Script Info]", "ScriptType: v4.00+",
                "PlayResX: 8000", "PlayResY: 300", "WrapStyle: 2",
                "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
                "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,"
                "ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
                "Alignment,MarginL,MarginR,MarginV,Encoding",
                "Style: M,%s,%d,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,"
                "&H00000000&,-1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"
                % (FONT_NAME, probe),
                "", "[Events]",
                "Format: Layer,Start,End,Style,Name,MarginL,MarginR,"
                "MarginV,Effect,Text",
                "Dialogue: 0,0:00:00.00,0:00:10.00,M,,0,0,0,,"
                "{\\an7\\pos(20,20)}" + key[0].replace("\n", " "),
            ]
            with open(os.path.join(d, "w.ass"), "w", encoding="utf-8") as f:
                f.write("\n".join(doc))
            r = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
                 "-i", "color=c=black:s=8000x300", "-vf", "ass=w.ass",
                 "-frames:v", "1", "w.png"], cwd=d, capture_output=True)
            if r.returncode == 0:
                bb = _Im.open(os.path.join(d, "w.png")).convert("L") \
                        .point(lambda p: 255 if p > 40 else 0).getbbox()
                if bb and bb[2] > 30:
                    got = int((bb[2] - 20) * size / float(probe))
                    if got > 0:
                        val = got
    except Exception:
        pass
    _WPX_CACHE[key] = val
    return val


def block_h(size, lines):
    """N line ka text kitni jagah legaa - naape hue naap se."""
    n = max(1, int(lines))
    return size * (INK_H + (n - 1) * LINE_ADV)


# ==================== REEL KA ROOP (9:16) ====================
#
# Reel sirf chhota kiya hua bulletin nahi hai. Uska apna roop hota hai, aur
# uski do wajah hain jo naap se aati hain:
#
# 1. SHORTS KA APNA UI SCREEN KHA JAATA HAI. Neeche lagbhag 300px mein
#    YouTube khud shirshak, channel ka naam aur buttons dikhata hai; daayein
#    kinaare like/comment/share ke buttons aate hain. Us jagah par hamara
#    kuch bhi rakha to wo dhak jayega. Isliye Reel mein ticker hai hi nahi -
#    uske liye jagah hai hi nahi, aur wo bulletin ka idiom hai, Reel ka
#    nahi.
#
# 2. CHAUDAI AADHI HAI. 1080 par ek line mein utne akshar nahi aate jitne
#    1920 par. Isliye caption chhote font par, kam akshar prati line, aur
#    teen line tak - warna ya to text kat jayega ya itna chhota ho jayega
#    ki phone par padha na jaye.
#
# Ek faayda bhi hai: Reel poori screen par dikhti hai, isliye 1080 ka har
# pixel lagbhag 0.333 point ka hai (bulletin mein 0.1875). Yaani wahi text
# kam pixel mein bhi bada dikhta hai.
LAYOUT_LAND = {
    "strap_bottom": 906, "strap_font": 96, "strap_min_h": 112,
    "tick_y": 912, "tick_h": 96, "tick_font": 72, "ticker": True,
    "bottom_mv": 14,
    "cap_chars": 42, "cap_lines": 2, "cap_max": 104, "cap_min": 68,
    "cap_y": 0.38, "hook_y": 0.40,
    "title_y": (500, 600), "end_y": (470, 580),
    "bug_font": 64, "brand_font": 58, "date_font": 44, "small_font": 40,
}

LAYOUT_REEL = {
    # Patti upar ki taraf - neeche ki jagah Shorts ka apna UI leta hai.
    "strap_bottom": 610, "strap_font": 70, "strap_min_h": 96,
    "ticker": False, "tick_y": 0, "tick_h": 0, "tick_font": 0,
    # Credit ko Shorts ke apne UI se upar rakhna hai, warna wo dhak jayega.
    "bottom_mv": 320,
    "cap_chars": 26, "cap_lines": 3, "cap_max": 76, "cap_min": 52,
    "cap_y": 0.44, "hook_y": 0.46,
    "title_y": (860, 980), "end_y": (880, 1010),
    "bug_font": 52, "brand_font": 46, "date_font": 38, "small_font": 34,
}

VERTICAL = False


def set_layout(vertical=False):
    """Poore render ka naap aur roop yahan se tay hota hai.

    Ek waqt mein ek hi video banti hai, isliye module ke naap badal dena
    surakshit hai - aur isi se ek hi renderer dono roop bana leta hai.
    """
    global W, H, VERTICAL, STRAP_BOTTOM, STRAP_FONT, STRAP_MIN_H
    global TICK_Y, TICK_H, TICK_FONT, BOTTOM_MV, TICKER_ON
    global CAP_CHARS, CAP_LINES, CAP_MAX_SIZE, CAP_MIN_SIZE
    global CAP_Y, HOOK_Y, TITLE_Y, END_Y
    global BUG_FONT, BRAND_FONT, DATE_FONT, SMALL_FONT

    VERTICAL = bool(vertical)
    W, H = backdrop.set_size(VERTICAL)
    import sy_scenes
    sy_scenes.set_size(W, H)

    L = LAYOUT_REEL if VERTICAL else LAYOUT_LAND
    STRAP_BOTTOM = L["strap_bottom"]
    STRAP_FONT = L["strap_font"]
    STRAP_MIN_H = L["strap_min_h"]
    TICK_Y, TICK_H, TICK_FONT = L["tick_y"], L["tick_h"], L["tick_font"]
    TICKER_ON = L["ticker"]
    BOTTOM_MV = L["bottom_mv"]
    CAP_CHARS, CAP_LINES = L["cap_chars"], L["cap_lines"]
    CAP_MAX_SIZE, CAP_MIN_SIZE = L["cap_max"], L["cap_min"]
    CAP_Y, HOOK_Y = L["cap_y"], L["hook_y"]
    TITLE_Y, END_Y = L["title_y"], L["end_y"]
    BUG_FONT, BRAND_FONT = L["bug_font"], L["brand_font"]
    DATE_FONT, SMALL_FONT = L["date_font"], L["small_font"]
    return W, H

# SHURUAAT KE TEEN NAAP - AUR EK KEEDA JO YAHIN CHHUPA THA
#
# TITLE_SECONDS : channel ka card. Iske baad parda uthta hai, patti aur
#                 ticker chalu ho jaate hain.
# HOOK_SECONDS  : ek badi baat (keyFact) - "12 teeke, bilkul muft".
# LEAD          : inhi dono ke baad AAWAAZ shuru hoti hai.
#
# Pehle LEAD naam ki koi cheez thi hi nahi. Aawaaz TITLE_SECONDS par shuru
# ho jaati thi, par hook card uske UPAR 2.6 second aur chalta tha - aur
# bole gaye shabd screen par tabhi aate the jab hook hat jaata tha.
#
# Nateeja ye tha ki har video ke shuru mein screen ka text aawaaz se DHAAI
# SECOND peechhe chalta tha, aur phir agle 15 second mein use wo 2.5 second
# pakadne hote the - isliye wahan cue tez-tez badalte the. Naapa hua:
# tikakaran wali video mein aawaaz 2.60 par bol rahi thi aur uska pehla
# shabd screen par 5.20 par aaya.
#
# Isiliye ab hook ka apna waqt hai. Aawaaz LEAD par shuru hoti hai, aur
# uska pehla shabd bhi wahin. Peechhe ka drishya aur patti pehle ki tarah
# TITLE_SECONDS par hi aa jaate hain - card ke baad screen khaali nahi
# rehti.
TITLE_SECONDS = 2.2
HOOK_SECONDS = 2.0
LEAD = TITLE_SECONDS + HOOK_SECONDS
END_SECONDS = 3.0

# HEYGEN ANCHOR KI KHIDKIYAN (Oct 2026, sy_heygen/sy_edit).
#
# job["anchorOverlays"] = [{"file", "off", "start", "end", "mode", "cx"}]
#   mode "anchor" - anchor poori screen (patti, ticker, bug USKE UPAR - TV
#                   studio jaisa); us dauran neeche ke bole-shabd nahi
#                   (anchor khud bol rahi hai, hont dikh rahe hain)
#   mode "pip"    - footage poori screen, anchor daayein khidki mein; bole-
#                   shabd baayein khisak jaate hain taaki khidki na dhakein
# Anchor parde (dim) ke BAAD lagti hai - uska chehra dhundhla nahi hota.
# Aawaaz wahi mix.wav - HeyGen video ki aawaaz kabhi nahi li jaati.
PIP_W, PIP_H = 416, 520         # 4:5 - kamar se upar
PIP_MARGIN = 48                 # daayein kinaare se
PIP_BORDER = 6


def _anchor_cue(job, a, b):
    """Bole-shabd ka ek tukda [a, b) anchor khidkiyon ke hisaab se.

    (a, b, pip) lauta ta hai - full anchor wala hissa kaat kar (bacha hua
    sabse lamba hissa), aur pip=True agar PIP khidki se zara bhi takraata
    ho. Kuch na bache (ya CAP_MIN se chhota) to None."""
    parts = [(float(a), float(b))]
    pip = False
    for o in job.get("anchorOverlays") or []:
        s, e = float(o["start"]), float(o["end"])
        if o.get("mode") == "pip":
            if s < float(b) and e > float(a):
                pip = True
            continue
        nxt = []
        for x, y in parts:
            if e <= x or s >= y:
                nxt.append((x, y))
                continue
            if x < s:
                nxt.append((x, s))
            if e < y:
                nxt.append((e, y))
        parts = nxt
    parts = [pt for pt in parts if pt[1] - pt[0] >= CAP_MIN]
    if not parts:
        return None
    x, y = max(parts, key=lambda pt: pt[1] - pt[0])
    return x, y, pip


def _pip_box(job):
    """(x, y) - PIP khidki (border samet) ka upar-baayan kona."""
    sy = int(job.get("_strapY") or STRAP_Y)
    return (W - PIP_W - 2 * PIP_BORDER - PIP_MARGIN,
            max(110, sy - PIP_H - 2 * PIP_BORDER - 28))


def set_intro_mode(anchor=False):
    """Anchor video ke aage judne wali ho to channel ka title card nahi.

    KYUN (Sep 2026, Harshvardhan): jaankari video anchor ke "namaste, aaj
    ... samajhte hain" se shuru hoti hai. Uske turant baad ye title card
    (channel ka naam, taareekh, phir hook) 4 second aata tha - anchor aur
    asli baat ke beech ek khaali deewar. Anchor khud hi shuruaat hai, to
    uske baad seedha khabar: drishya aur aawaaz lagbhag turant.

    Har render ke baad set_intro_mode(False) - warna agli khabar bhi bina
    card ke ban jaati. sy_produce.produce() ye finally mein karta hai."""
    global TITLE_SECONDS, LEAD
    if anchor:
        TITLE_SECONDS = 0.0
        LEAD = 0.35
    else:
        TITLE_SECONDS = 2.2
        LEAD = TITLE_SECONDS + HOOK_SECONDS


def _ass_colour(hex_rgb, alpha=0):
    """#RRGGBB -> &HAABBGGRR&  (ASS ulte kram mein, alpha 0 = thos)"""
    h = str(hex_rgb).lstrip("#")
    return "&H%02X%s%s%s&" % (alpha, h[4:6].upper(), h[2:4].upper(), h[0:2].upper())


def _esc(s):
    s = str(s or "")
    s = s.replace("\\", "⧵").replace("{", "(").replace("}", ")")
    return re.sub(r"\s+", " ", s).strip()


def audio_duration(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        pass
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


# AAWAAZ KA STAR - EK STHIR ANKDA, CHALTA-FIRTA FILTER NAHI
#
# Yahan pehle ffmpeg ka `loudnorm` lagta tha, seedha filter graph mein. Wo
# ek KEEDA tha, aur usne lighthouse wali video ki aawaaz kaat di thi.
#
# Kya hua tha (naapa hua, andaaza nahi):
#   - loudnorm ek-baar wale roop mein aage ka teen second pehle se apne
#     paas rakhta hai (lookahead). File khatam hone par wo teen second
#     bahar nikalta hai - aur unke samay ke thappe (timestamps) shuru se
#     dobara chalu ho jaate hain.
#   - mp4 likhne wala unhe girata hai. Nateeja: audio ki patti mein 52.29
#     second par THEEK 3.0 SECOND ka gaddha, aur uske baad ki poori aawaaz
#     1.9 second aage khisak jaati hai.
#   - Isliye aawaaz ka ek tukda gayab hua aur uske baad screen ka text
#     aawaaz se mel khana band kar gaya. Ye maine unki apni file par
#     dobara paida karke dekha, phir loudnorm hatakar dobara - gaddha
#     gaayab.
#
# Aur ek baat: loudnorm is aawaaz par kar bhi kuch nahi raha tha. Naapa to
# poore video par uska asar 2 dB se kam nikla. Yaani wo faayda kuch nahi de
# raha tha aur nuksaan poora kar raha tha.
#
# Ab: star pehle NAAP lete hain (ek chhoti, alag ffmpeg jaanch - sirf
# aawaaz par), aur graph mein ek saada `volume=` lagate hain. Ek sthir gain
# na kuch buffer karta hai, na koi lookahead rakhta hai, isliye samay ke
# thappe kabhi tootte nahi.
LOUD_TARGET = -14.0        # LUFS - YouTube isi par normalize karta hai
LOUD_PEAK = -1.5           # dBTP - isse upar clip hone ka khatra


def voice_gain_db(path, target=LOUD_TARGET, ceiling=LOUD_PEAK):
    """Is aawaaz ko kitne dB upar/neeche kiya jaye. Naap na ho to 0.

    loudnorm ko yahan sirf NAAPNE ke liye bulate hain (-f null), banane ke
    liye nahi. Naapna surakshit hai - uska koi output stream hi nahi hota.
    """
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", path,
             "-af", "loudnorm=I=%.1f:TP=%.1f:LRA=11:print_format=json"
             % (target, ceiling),
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=180)
        blob = (out.stderr or "") + (out.stdout or "")
        i = blob.rfind("{")
        j = blob.rfind("}")
        if i < 0 or j < i:
            return 0.0
        d = json.loads(blob[i:j + 1])
        cur_i = float(d.get("input_i"))
        cur_tp = float(d.get("input_tp"))
    except Exception as e:
        print("[render] aawaaz ka star naapa nahi ja saka:", e, flush=True)
        return 0.0
    if cur_i < -70:            # lagbhag chuppi - chhedna nahi
        return 0.0
    gain = target - cur_i
    # Chotee par sar na takraye: peak ko chhat se neeche rakho. ASLI
    # suraksha yahi ek line hai - iske baad aawaaz clip ho hi nahi sakti.
    gain = min(gain, ceiling - cur_tp)
    # Neeche wali seema -12 par hai aur upar wali 16 par - ye jaan-boojhkar
    # alag hain. Aawaaz ko GIRANA kabhi zaroori nahi hota (peak wali line
    # wo kaam pehle hi kar chuki hoti hai), par UTHANA aksar padta hai: TTS
    # ki aawaaz apne aap mein dheemi aati hai. Pehle dono 12 par thi, aur
    # target -16 se -14 karne par wo 12 wali chhat do dB aur paas aa gayi -
    # yaani dheemi aawaaz poore -14 tak pahunch hi na paati aur YouTube par
    # video dabi hui sunai deti.
    return max(-12.0, min(16.0, gain))


def media_duration(path):
    """Kisi bhi file ki lambai second mein. Pata na chale to 0."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60)
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def _extend_clip(clip, need, workdir):
    """Clip ko itna lamba bana do ki poori video dhak jaye. Naya path lauta ta hai.

    Jodne mein dobara encode nahi hota (stream copy), isliye ye lagbhag
    muft hai - 60 MB ki file bhi ek-do second mein jud jaati hai, aur
    tasveer ki quality bilkul waisi ki waisi rehti hai.
    """
    have = media_duration(clip)
    if have <= 0.2:
        return clip
    if have >= need - 0.05:
        return clip

    n = min(200, int(need / have) + 2)
    base = os.path.basename(clip)
    try:
        with open(os.path.join(workdir, "loop.txt"), "w", encoding="utf-8") as f:
            for _ in range(n):
                f.write("file '%s'\n" % base)
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", "loop.txt",
             "-c", "copy", "bg_long.mp4"],
            cwd=workdir, check=True, timeout=300)
        out = os.path.join(workdir, "bg_long.mp4")
        if media_duration(out) >= need - 0.05:
            print("[render] footage %.1fs thi, %.1fs chahiye - %d baar jodi"
                  % (have, need, n), flush=True)
            return out
    except Exception as e:
        print("[render] footage lambi nahi ki ja saki:", e, flush=True)
    return clip


def wrap_text(text, max_chars):
    words = str(text).split()
    lines, cur = [], ""
    for wd in words:
        cand = (cur + " " + wd).strip()
        if len(cand) > max_chars and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def balance2(text, per_line):
    """Do line ko lagbhag barabar karo.

    Lalchi wrap pehli line thoos deta hai aur doosri mein sirf "हैं।" bachta
    hai. Wo latka hua shabd screen par galti jaisa dikhta hai. Subtitle mein
    do line hamesha barabar ki jaati hain, isliye todhne ki jagah beech ke
    sabse kareeb wale shabd par le jaate hain - virām ho to wahan.
    """
    words = str(text or "").split()
    if len(words) < 2:
        return [text] if text else []
    best, best_score = None, None
    for k in range(1, len(words)):
        a = " ".join(words[:k])
        b = " ".join(words[k:])
        if len(a) > per_line or len(b) > per_line:
            continue
        score = abs(len(a) - len(b))
        if re.search(r"[,;:।]$", words[k - 1]):
            score -= 8
        if _binds(words[k - 1]) or _binds_next(words[k]):
            score += 14
        if best_score is None or score < best_score:
            best_score, best = score, (a, b)
    return list(best) if best else wrap_text(text, per_line)


def fit_lines(text, avail_px, band_px, max_size, min_size, max_lines,
              max_chars=0, balance=False):
    """Sabse bada font jo di gayi jagah mein sama jaye.

    Pehle font size tay tha aur wrap bhi tay tha, isliye chhoti headline par
    laal patti ka aadha hissa khaali reh jaata tha aur door se padhna mushkil
    tha. Ab patti pehle aati hai, font uske hisaab se chuna jaata hai."""
    text = str(text or "")
    if not text:
        return min_size, []
    size = max_size
    while size >= min_size:
        per_line = max(8, int(avail_px / (CH_W * size)))
        if max_chars:
            per_line = min(per_line, max_chars)
        lines = wrap_text(text, per_line)
        if len(lines) <= max_lines and block_h(size, len(lines)) <= band_px:
            if balance and len(lines) == 2:
                lines = balance2(text, per_line)
            return size, lines
        size -= 2
    per_line = max(8, int(avail_px / (CH_W * min_size)))
    return min_size, wrap_text(text, per_line)[:max_lines]


def _ts(sec):
    sec = max(0.0, sec)
    return "%d:%02d:%05.2f" % (int(sec // 3600), int((sec % 3600) // 60), sec % 60)


# ---------------------------------------------------------- screen text
#
# Ye naap andaaze se nahi hain. Subtitle par duniya bhar mein kaam hua hai
# aur Netflix ki apni Hindi guide mein saaf likha hai:
#
#   padhne ki raftaar  : 22 akshar prati second (badon ke liye)
#   ek line            : 42 akshar tak
#   line               : do se zyada nahi
#   sabse chhota samay : 20 frame (0.8 second)
#
# Aur ek baat jo hum ULTA kar rahe the: shabd-dar-shabd nikalne wala
# "typewriter". Wo dekhne mein achha lagta hai par padhne ke khilaf hai -
# har shabd tabhi aata hai jab wo bola jaata hai, isliye padhne wala aage
# dekh hi nahi sakta. Aur aage dekhna hi wo cheez hai jisse insaan tez
# padhta hai. Iske alawa lagataar hilta hua text kuch logon ko chakkar aur
# sar dard deta hai. Sujhaav saaf hai: poora vaakyansh ek saath dikhaiye,
# sthir, aur itni der ki aaram se padha ja sake.
#
# Isliye ab: ek baar mein ek poora tukda, do line se zyada nahi, 42 akshar
# prati line, halke se aata aur jaata hua - aur bas.
CAP_CPS = 22.0
CAP_CHARS = 42
CAP_LINES = 2
CAP_MIN = 0.85          # 20 frame - Netflix ka farsh
# Upar ki chhat guide mein nahi hai par kaam mein zaroori hai: 84 akshar
# ko darshak 4 second mein padh leta hai. Use 14 second tak screen par
# chhod dena padhna nahi, ghoorna hai - aur wo utna hi bura lagta hai
# jitna bahut tez badalta text. Isliye lamba hissa aage aur toota hai.
CAP_MAX = 6.5
CAP_ORPHAN = 24         # itne chhote tukde ko akela nahi chhodte
# Naap badalne par ye bhi badalta hai, isliye function hai - ek jama hua
# ankda Reel par galat ho jaata (42x2 ki jagah 26x3).
def cap_budget():
    return CAP_CHARS * CAP_LINES


CAP_BUDGET = CAP_CHARS * CAP_LINES


def _sentences(text):
    return [p.strip() for p in re.split(r"(?<=[।.!?])\s+", str(text or ""))
            if len(p.strip()) > 12]


# In shabdon ke BAAD line nahi todni chahiye - ye akele khade nahi hote,
# agle shabd ke saath hi arth banate hain. "आठ" ek line mein aur "वार्डों"
# doosri mein - padhne wala pehli line ke ant par ruk kar sochta hai ki
# aath kya. Subtitle ke har guide mein yahi baat hai: sankhya ko uski
# cheez se, aur parsarg ko apne shabd se alag mat kijiye.
BIND = set((
    "के की का को में से पर और या कि तक ने भी हुए हुई हुआ एक दो तीन चार "
    "पांच पाँच छह छे सात आठ नौ दस ग्यारह बारह सौ हजार हज़ार लाख करोड़ अरब "
    "प्रति लगभग करीब क़रीब बाद पहले साथ लिए जैसे यह वह इस उस अपने अपनी "
    "न ना नहीं मत बिना हर कुछ सभी सारे जो जब तब कोई किसी"
).split())


# In shabdon se PEHLE bhi nahi todna - ye apne se pehle wale shabd ke bina
# adhoore hain. "बयालीस" ek line mein aur "करोड़" doosri mein rakhne se
# aankada do tukdon mein bant jaata hai, aur khabar mein aankada hi sabse
# zaroori cheez hoti hai. Har Hindi ginti likhna mumkin nahi (बयालीस,
# सैंतालीस, तिरसठ...), isliye ulti taraf se pakadte hain - unit par.
BIND_NEXT = set((
    "करोड़ अरब लाख हजार हज़ार सौ प्रतिशत फीसदी फ़ीसदी रुपये रुपए किलो "
    "किलोमीटर मीटर एकड़ बीघा घंटे घंटा मिनट दिन महीने साल बजे बार गुना "
    "लोग लोगों वार्ड वार्डों जिले जिलों गांव गाँव"
).split())


def _binds_next(word):
    return str(word or "").strip(",;:।\"'()") in BIND_NEXT


def _binds(word):
    w = str(word or "").strip(",;:।\"'()")
    if not w:
        return False
    if re.search(r"[0-9०-९]$", w):       # sankhya - agla shabd usi ka hai
        return True
    return w in BIND


def _split_to_budget(text, budget=None):
    """Ek vaakya ko lagbhag BARABAR tukdon mein todo.

    Lalchi tareeke se todne par - "jab tak bharta jaye bharo, phir naya
    tukda" - hamesha ek bhara hua tukda banta hai aur uske baad ek thootha
    sa: 65 akshar, phir 27. Screen par ye jhoolta hua dikhta hai.
    Subtitle mein isi wajah se pehle ye ginte hain ki KITNE tukde chahiye,
    aur phir text ko utne barabar hisson mein baanta jaata hai.

    Todhne ki jagah shabd ki seema par hoti hai, aur virām ya comma ke baad
    ko tarjeeh milti hai - wahan vaakya khud saans leta hai.
    """
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    if len(text) <= budget:
        return [text]

    words = text.split()
    if len(words) < 2:
        return [text]

    # Har shabd ke baad ki jagah: wahan tak kitne akshar, wahan vaakya
    # saans le raha hai ya nahi, aur wahan todna mana to nahi hai.
    stops = []
    pos = 0
    for i, w in enumerate(words[:-1]):
        pos += len(w) + (1 if i else 0)
        stops.append((pos, i,
                      bool(re.search(r"[,;:।]$", w)),
                      _binds(w) or _binds_next(words[i + 1])))
    if not stops:
        return [text]

    n = int(len(text) / float(budget)) + (1 if len(text) % budget else 0)
    n = max(2, min(n, len(words)))
    target = len(text) / float(n)

    cuts, last = [], -1
    for k in range(1, n):
        ideal = k * target
        best, best_score = None, None
        for p, i, punct, bind in stops:
            if i <= last:
                continue
            # Virām ke baad todna 10 akshar ki chhoot ke barabar achha hai;
            # jis shabd ko agle se chipke rehna chahiye uske baad todna 16
            # akshar ke barabar bura. Comma ka faayda bandhan ki saza se
            # bada hai, isliye "मुट्ठीगंज," par todna ab bhi chalta hai.
            score = abs(p - ideal) - (10 if punct else 0) + (16 if bind else 0)
            if best_score is None or score < best_score:
                best_score, best = score, i
        if best is None:
            break
        cuts.append(best)
        last = best

    out, start = [], 0
    for c in cuts + [len(words) - 1]:
        out.append(" ".join(words[start:c + 1]))
        start = c + 1
    if start < len(words):
        out.append(" ".join(words[start:]))
    return [c for c in out if c]


def _no_orphans(chunks, budget):
    """Akele chhoot gaye chhote tukde padosi mein mila do.

    "हो गया है।" ko akele do second screen par rakhna kisi kaam ka nahi -
    wo ek adhoora vaakyansh hai, ek cue nahi. Subtitle mein aise tukde
    hamesha pichhle ya agle ke saath jode jaate hain.
    """
    out = []
    for c in chunks:
        if out and len(c) < CAP_ORPHAN and len(out[-1]) + len(c) + 1 <= budget:
            out[-1] = out[-1] + " " + c
        else:
            out.append(c)
    # Pehla tukda hi chhota ho to use aage wale se jodte hain - par tabhi
    # jab wo budget ke andar rahe, warna hum wahi lamba cue wapas bana
    # denge jise abhi toda tha.
    if len(out) > 1 and len(out[0]) < CAP_ORPHAN \
            and len(out[0]) + len(out[1]) + 1 <= budget:
        out[1] = out[0] + " " + out[1]
        out.pop(0)
    return out


def _find(hay, needle):
    a = re.sub(r"\s+", " ", str(hay or ""))
    b = re.sub(r"\s+", " ", str(needle or "")).strip()
    if not b:
        return -1
    i = a.find(b)
    if i >= 0:
        return i
    head = " ".join(b.split()[:5])
    return a.find(head) if len(head) > 12 else -1


def _time_at(pos, vm, lo, hi):
    """Script ke is akshar par aawaaz kis lamhe pe hai.

    voiceMap sy_tts se aata hai - har bole gaye tukde ka ASLI samay. Pehle
    yahan sirf akshar gine jaate the, maano aawaaz ek hi raftaar se chalti
    ho. Wo chalti nahi, aur isi wajah se screen ka text aawaaz se aage
    nikal jaata tha.
    """
    spans = vm.get("spans") or []
    base = float(vm.get("offset") or 0.0)
    if not spans or pos < 0:
        return lo
    if pos <= spans[0][0]:
        return max(lo, base + spans[0][2])
    for c0, c1, t0, t1 in spans:
        if pos <= c1:
            frac = (pos - c0) / float(max(1, c1 - c0))
            return max(lo, min(base + t0 + frac * (t1 - t0), hi))
    return hi


def _cues(job, hook_end, body_end):
    """Screen par dikhne wale tukde - [(shuru, ant, text)].

    Har tukda apne shot ke andar rehta hai, uske paar nahi jaata. Netflix
    ki timing guide isi baat par zor deti hai: shot badle to subtitle bhi
    wahin badle, warna aankh ek saath do jagah kheenchti hai.
    """
    cuts = sorted(float(c) for c in (job.get("cuts") or []))

    def snap(t):
        """Cut ke aadhe second ke andar ho to cut par hi khiska do.

        Netflix ki timing guide ka seedha niyam. Wajah saaf hai: agar
        tasveer 9.33 par badle aur text 9.50 par, to darshak ko do alag
        badlaav dikhte hain aur aankh do baar kheenchti hai. Ek saath honge
        to ek hi badlaav lagega.
        """
        for c in cuts:
            if abs(c - t) <= 0.5:
                return c
            if c > t + 0.5:
                break
        return t

    out = []
    for a, b, text in _speech_spans(job, hook_end, body_end):
        span = b - a
        if span < CAP_MIN or not text:
            continue
        # Is hisse mein aawaaz kitne akshar prati second bol rahi hai - usi
        # se tay hota hai ki ek cue mein kitna text daalein taaki wo CAP_MAX
        # se zyada der screen par na tike.
        rate = len(text) / span
        budget = int(max(24, min(cap_budget(), rate * CAP_MAX)))
        chunks = _no_orphans(_split_to_budget(text, budget), budget)
        if not chunks:
            continue
        chars = float(sum(len(c) for c in chunks)) or 1.0
        # Aawaaz ki asli timing ho to usi se - warna akshar ginkar.
        vm = job.get("voiceMap") or {}
        anchored = []
        if vm.get("spans") and vm.get("text"):
            pos = _find(vm["text"], text)
            if pos >= 0:
                off = 0
                for c in chunks:
                    p0 = vm["text"].find(c, pos + off)
                    anchored.append(p0 if p0 >= 0 else -1)
                    if p0 >= 0:
                        off = p0 - pos + len(c)
                if any(p < 0 for p in anchored):
                    anchored = []

        t = a
        for k, c in enumerate(chunks):
            if anchored:
                nxt = (_time_at(anchored[k + 1], vm, a, b)
                       if k + 1 < len(anchored) else b)
                t = max(a, min(_time_at(anchored[k], vm, a, b), b - CAP_MIN))
                end = min(max(nxt, t + CAP_MIN), b)
            else:
                end = min(t + span * (len(c) / chars), b)
            # Aakhri tukda hamesha shot ke ant par khatam - use khiskane se
            # wo agle shot mein ghus jaata.
            if k < len(chunks) - 1:
                end = min(max(snap(end), t + CAP_MIN), b)
            if end - t >= CAP_MIN:
                out.append((t, end, c))
            t = end
    return out


def _speech_spans(job, hook_end, body_end):
    """Screen par dikhne wale shabd - kab se kab tak. [(a, b, text)]

    Agar shot list maujood hai to shabd USI timeline par chalte hain jispar
    peeche ka drishya badalta hai. Ye is poore badlaav ki jaan hai: cut par
    tasveer bhi badalti hai aur shabd bhi, isliye darshak ko lagta hai ki
    dono ek hi baat kar rahe hain. Do alag hisaab rakhne par tasveer ek
    baat par badalti aur shabd doosri par, aur wo bikhra hua dikhta hai.

    Shot list na ho (purani khabar, ya picture editor se jawab na aaya) to
    wahi purana tareeka - script ko vaakyon mein todh kar unki lambai ke
    anupaat mein baant do.
    """
    out = []
    shots = job.get("shots") or []

    if shots:
        for sh in shots:
            a = max(float(sh.get("start") or 0), hook_end)
            b = min(float(sh.get("end") or 0), body_end)
            if b - a < 1.2:
                continue
            parts = _sentences(sh.get("text")) or [str(sh.get("text") or "")]
            chars = float(sum(len(p) for p in parts)) or 1.0
            t = a
            for p in parts:
                end = min(t + (b - a) * (len(p) / chars), b)
                if end - t >= 1.2:
                    out.append((t, end, p))
                t = end
        if out:
            return out

    parts = _sentences(job.get("ticker") or job.get("headline"))
    if not parts or body_end - hook_end <= 4:
        return []
    chars = float(sum(len(p) for p in parts)) or 1.0
    span = body_end - hook_end - 0.3
    t = hook_end
    for p in parts:
        share = max(1.8, span * (len(p) / chars))
        end = min(t + share, body_end)
        if end - t < 1.2:
            break
        out.append((t, end, p))
        t = end
    return out


def build_ass(job, dur, path):
    is_hi = job.get("lang") == "hi"
    pal = backdrop.palette(job.get("category"))
    accent = _ass_colour("%02x%02x%02x" % pal["accent"])
    white = _ass_colour("ffffff")
    ink = _ass_colour(TICKER_INK)
    grey = _ass_colour("d8dde4")
    shade = _ass_colour("000000", 0x60)
    channel = CHANNEL_HI if is_hi else CHANNEL_EN

    # HEADLINE HAMESHA EK HI LINE.
    #
    # Do line ki patti do wajah se galat thi. Ek, wo screen ka bada hissa
    # kha jaati hai. Do - aur ye zyada zaroori - koi news channel apni laal
    # patti mein do line nahi likhta. Wahan ek lakeer hoti hai, aur baat
    # lambi ho to wo lakeer CHALTI hai.
    #
    # Isliye ab naap ghata kar do line banane ke bajaye: agar headline ek
    # line mein sama gayi to sthir khadi rehti hai; nahi sami to ticker ki
    # tarah daayein se baayein chalti hai. Font dono haalat mein ek hi -
    # chhoti headline bade akshar mein aur lambi chhote mein, aisa ab nahi
    # hota.
    headline = _esc(job.get("headline"))
    hl_size = STRAP_FONT
    # Chaudai ANDAZE se nahi, NAAP se. CH_W (0.32) ek ausat hai aur ausat
    # yahan kaafi nahi: kuch headline uske hisaab se "sama jaati hai" par
    # sach mein nahi samati - aur ASS use todta nahi, KAAT deta hai. Yaani
    # patti par headline ka aakhri hissa chup-chaap gayab ho jaata tha,
    # chalti hui dikhne ke bajay. Yahi galti thumbnail par bhi thi.
    hl_px = text_width_px(headline, hl_size)
    strap_avail = W - 200
    strap_rolls = hl_px > strap_avail

    strap_h = block_h(hl_size, 1) + 2 * STRAP_PAD
    strap_h = int(max(STRAP_MIN_H, round(strap_h)))
    strap_y = STRAP_BOTTOM - strap_h
    job["_strapY"], job["_strapH"] = strap_y, strap_h

    key_fact = _esc(job.get("keyFact"))
    place = _esc(job.get("place") or job.get("ghost"))
    source_line = _esc(job.get("sourceLine"))
    credit = _esc(job.get("imageCredit"))
    date_str = _esc(job.get("dateStr"))
    banner = _esc(job.get("banner"))
    ai_label = "AI आवाज़" if is_hi else "AI voice"

    # Ticker: poori khabar ek lakeer mein, dayein se bayein chalti hui.
    #
    # Yahan pehle aakhir mein "स्रोत: अमर उजाला" jud jaata tha. Ab nahi.
    # Akhbaar ka naam video mein kahin nahi aata - na screen par, na
    # aawaaz mein. Uski jagah YouTube ka description hai, aur wahan wo
    # sy_youtube.upload() apne aap jodta hai, sampadak ke bharose nahi.
    ticker = _esc(job.get("ticker") or job.get("headline"))

    head = ["[Script Info]", "ScriptType: v4.00+",
            "PlayResX: %d" % W, "PlayResY: %d" % H,
            "WrapStyle: 2", "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709",
            "", "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
            "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding"]

    def stbox(name, size, col, boxcol, align, ml=0, mr=0, mv=0, pad=14):
        """BorderStyle=3 = libass khud text ke naap ka thos box banata hai.

        Pehle box drawbox se banta tha aur uski chaudai main akshar gin kar
        andaaz se nikalta tha - isliye text box ke beech mein nahi baithta tha
        aur daayein khaali jagah bach jaati thi. Ab box text ko chipak kar
        aata hai, aur text apne aap beech mein rehta hai."""
        return ("Style: %s,%s,%d,%s,%s,%s,%s,-1,0,0,0,100,100,0,0,3,%d,0,%d,%d,%d,%d,1"
                % (name, "Noto Sans Devanagari", size, col, col, boxcol, boxcol,
                   pad, align, ml, mr, mv))

    def st(name, size, col, bold, align, ml=0, mr=0, mv=0, shadow=2,
           font="Noto Sans Devanagari", outline=0):
        # Spacing hamesha 0 - Devanagari par letter-spacing conjunct todh deti
        # hai ("कर्नाटक" ko "कर् न ाटक" bana deti hai).
        return ("Style: %s,%s,%d,%s,%s,%s,%s,%d,0,0,0,100,100,0,0,1,%d,%d,%d,%d,%d,%d,1"
                % (name, font, size, col, col,
                   _ass_colour("000000", 0x40) if outline else shade, shade,
                   -1 if bold else 0, outline, shadow, align, ml, mr, mv))

    # Har naap ke aage uska phone wala naap. 360 point chaudi screen par
    # 6.5 point se chhota text padha nahi jaata - isliye yahan koi naap 36
    # se neeche nahi hai, aur jo cheezein door se dikhni chahiye (headline,
    # ticker, location, badge) wo 58 se upar hain.
    head.append(stbox("Bug", BUG_FONT, white, _ass_colour(BUG_RED), 7, 0, 0, 0, 18))
    head.append(st("Brand", BRAND_FONT, white, True, 9, 0, 64, 38))
    head.append(st("Strap", hl_size, white, True, 4, 100, 100, 0, 0))
    head.append(st("Tick", TICK_FONT, ink, True, 4, 0, 0, 0, 0))
    head.append(st("Date", DATE_FONT, grey, False, 9, 0, 64, 116))
    head.append(st("Credit", SMALL_FONT, grey, False, 3, 0, 46, BOTTOM_MV))
    head.append(st("AI", SMALL_FONT, grey, False, 1, 46, 0, BOTTOM_MV))
    head.append(st("TitleBig", CAP_MAX_SIZE, white, True, 5, 0, 0, 0, 4))
    head.append(st("TitleSub", BRAND_FONT, accent, True, 5, 0, 0, 0))
    head.append(st("Hook", int(CAP_MAX_SIZE * 0.92), white, True, 5, 0, 0, 0, 4))

    head.append(stbox("Badge", BRAND_FONT, white, _ass_colour(BUG_RED), 4, 0, 0, 0, 18))
    head.append(st("EndBig", int(CAP_MAX_SIZE * 0.85), white, True, 5, 0, 0, 0, 4))
    head.append(st("EndSub", BRAND_FONT, grey, False, 5, 0, 0, 0))
    head.append("")
    head.append("[Events]")
    head.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
                "Effect, Text")

    ev = []
    # fit_lines har vaakya ke liye alag size chun sakta hai, isliye styles
    # baad mein jodte hain - jo-jo size istemaal hue sirf unke.
    sizes_used = set()

    def L(sty, a, b, text, tags="", layer=0):
        if not text:
            return
        ev.append("Dialogue: %d,%s,%s,%s,,0,0,0,,%s%s"
                  % (layer, _ts(a), _ts(b), sty, tags, text))

    # Do alag shuruaat, aur ye farq hi is file ka sabse zaroori farq hai:
    #   show_start - parda uthta hai. Drishya, patti, ticker, bug - sab.
    #   body_start - AAWAAZ bolna shuru karti hai. Screen ke shabd bhi.
    show_start = TITLE_SECONDS
    body_start = LEAD
    body_end = max(body_start + 1.0, dur - END_SECONDS)

    # ---- Title card
    if TITLE_SECONDS > 0.5:     # anchor ke baad card nahi (set_intro_mode)
        L("TitleBig", 0.15, TITLE_SECONDS, channel, "{\\fad(400,450)\\pos(%d,%d)}" % (W // 2, TITLE_Y[0]))
        L("TitleSub", 0.6, TITLE_SECONDS, date_str, "{\\fad(450,450)\\pos(%d,%d)}" % (W // 2, TITLE_Y[1]))

    # ---- Beech ka hissa: pehle key fact, phir wahi baat jo bolі ja rahi hai.
    #
    # Media mein screen kabhi khaali nahi chhodi jaati - ye baat sahi hai.
    # Sarvam word-level timing nahi deta, isliye script ko vaakyon mein todh kar
    # unki lambai ke anupaat mein baant dete hain. Ye ekdum sateek lip-sync nahi
    # hai, par darshak ko wahi shabd dikhte hain jo us waqt sunai de rahe hain.
    # Hook card ab aawaaz se PEHLE, uske upar nahi. Iske peechhe pehla
    # drishya chal raha hota hai - screen khaali nahi rehti.
    if key_fact and body_start - show_start > 1.0:
        L("Hook", show_start + 0.1, body_start - 0.1, key_fact,
          "{\\fad(350,350)\\pos(%d,%d)}" % (W // 2, int(H * HOOK_Y)))

    over = 0
    for t, end, p in _cues(job, body_start, body_end):
        # Anchor poori screen par bol rahi hai - uske hont hi shabd hain,
        # us hisse mein neeche shabd nahi.
        cut = _anchor_cue(job, t, end)
        if cut is None:
            continue
        t, end, in_pip = cut
        # PIP khidki daayein hai - shabd baayein ki jagah mein.
        avail = W - (240 if not VERTICAL else 110)
        cx_cap = W // 2
        if in_pip:
            px, _py = _pip_box(job)
            avail = px - 120
            cx_cap = 60 + avail // 2
        # Do line, 42 akshar prati line - isse zyada ek nazar mein padha
        # nahi jaata. Font utna bada jitni jagah hai: 42 akshar 104 par
        # bhi poori chaudai mein sama jaate hain, isliye chhota rakhne ki
        # koi wajah nahi.
        sz, lines = fit_lines(_esc(p), avail,
                              250 if not VERTICAL else 460,
                              max_size=CAP_MAX_SIZE, min_size=CAP_MIN_SIZE,
                              max_lines=CAP_LINES,
                              max_chars=CAP_CHARS, balance=True)
        block = "\\N".join(lines)
        if len(p) / max(0.1, end - t) > CAP_CPS:
            over += 1
        # Sthir. Aata aur jaata halke se, taaki cut par jhatka na lage -
        # par beech mein kuch hilta nahi, kuch nikalta nahi.
        ev.append("Dialogue: 0,%s,%s,Spoken%d,,0,0,0,,{\\fad(160,160)"
                  "\\pos(%d,%d)}%s"
                  % (_ts(t), _ts(end), sz, cx_cap, int(H * CAP_Y), block))
        sizes_used.add(sz)
    if over:
        print("[render] %d tukde 22 akshar/second se tez hain - "
              "script us jagah lambi hai" % over, flush=True)

    # ---- "बड़ी खबर" jaisa badge, strap ke thoda upar.
    # Ye har 1.8 second par halka sa dhadakta hai - dhyan kheenchta hai par
    # chillata nahi. Art Director tay karta hai ki isme kya likha jaaye; wo
    # jaan-boojhkar har khabar ko "breaking" nahi kehta.
    if banner:
        bt = show_start + 0.15
        while bt < body_end - 0.4:
            be = min(bt + 1.8, body_end)
            L("Badge", bt, be, banner,
              "{\\pos(%d,%d)\\fscx100\\fscy100\\t(0,260,\\fscx107\\fscy107)"
              "\\t(260,620,\\fscx100\\fscy100)}" % (100, strap_y - 60))
            bt = be

    # ---- Sthayi sajaawat
    L("Bug", show_start, body_end, place or channel,
      "{\\fad(350,300)\\pos(72,40)}")
    if not LOGO_PATH:
        L("Brand", show_start, body_end, channel, "{\\fad(350,300)}")
    L("Date", show_start, body_end, date_str, "{\\fad(350,300)}")
    L("AI", show_start, body_end, ai_label, "{\\fad(400,300)}")
    # Credit har drishya ke saath badalta hai. Ek hi credit poore video par
    # chhod dena sirf badsoorti nahi, galat hai - us waqt screen par jo
    # tasveer hai wo kisi aur ki ho sakti hai, aur uska licence uske apne
    # naam se bandha hota hai.
    spans = job.get("creditSpans") or []
    if spans:
        for a, b, c in spans:
            a = max(float(a), show_start)
            b = min(float(b), body_end)
            if b - a > 0.8 and c:
                L("Credit", a, b, _esc(c), "{\\fad(300,250)}")
    elif credit:
        L("Credit", show_start, body_end, credit, "{\\fad(400,300)}")
    # PIP khidki ke andar chhota "AI प्रस्तुतकर्ता" - credit wali jagah par
    # footage ka apna credit chalta rehta hai.
    for o in job.get("anchorOverlays") or []:
        if o.get("mode") == "pip" and float(o["end"]) - float(o["start"]) > 0.8:
            px, py = _pip_box(job)
            L("Credit", float(o["start"]), float(o["end"]), "AI प्रस्तुतकर्ता",
              "{\\an1\\pos(%d,%d)}" % (px + PIP_BORDER + 10,
                                       py + PIP_H + PIP_BORDER - 8))

    # ---- Headline strap
    # Patti ke theek beech mein - AANKH ke hisaab se, box ke hisaab se nahi.
    strap_mid = strap_y + strap_h // 2 + int(round(hl_size * INK_RISE))

    if not strap_rolls:
        # Sama gayi - sthir khadi rehti hai, baayein se andar aakar.
        # \move alignment ke MarginL ko override kar deta hai, isliye ant ka
        # x khud dena padta hai.
        L("Strap", show_start + 0.25, body_end, headline,
          "{\\fad(300,300)\\move(%d,%d,%d,%d,%d,%d)}"
          % (-900, strap_mid, 100, strap_mid, 0, 600))
    else:
        # Nahi sami - to chalti hai, ticker ki tarah. Raftaar ticker se
        # dheemi hai: ye khabar ka SHIRSHAK hai, neeche ki chalti lakeer
        # nahi, aur ise darshak ko theek se padhna hota hai.
        one = headline + "          •          "
        one_px = max(400, int(len(one) * hl_size * CH_W))
        interval = one_px / STRAP_SPEED
        start = show_start + 0.25

        # Patti PEHLE SE BHARI HUI shuru hoti hai.
        #
        # Seedhe ticker ki tarah daayein se shuru karne par shuruaati kai
        # second tak laal patti lagbhag khaali dikhti thi - theek us waqt
        # jab darshak ko shirshak sabse zyada chahiye. Isliye ghadi ko
        # peeche le jaate hain: maano lakeer pehle se chal rahi thi aur
        # body shuru hote hi uska pehla shabd baayein kinaare (x=100) par
        # pahunch chuka hai.
        virtual = start - (W - 100) / STRAP_SPEED
        k = 0
        while True:
            tk = virtual + k * interval
            if tk >= body_end:
                break
            s0 = max(tk, start)
            x0 = W - STRAP_SPEED * (s0 - tk)      # is lamhe pe kahan hai
            if x0 > -one_px:
                travel = (x0 + one_px) / STRAP_SPEED
                L("Strap", s0, min(s0 + travel, body_end), one,
                  "{\\move(%d,%d,%d,%d,0,%d)}"
                  % (int(x0), strap_mid, -one_px, strap_mid, int(travel * 1000)))
            k += 1

    # ---- Ticker: ek lakeer, daayein se baayein.
    # Chaudai ka andaaza akshar ginti se - libass text ki naap nahi deta,
    # isliye thoda udaar rakhte hain taaki wo poori nikal jaye.
    # Text ko itni baar dohrate hain ki wo poore body ko bhar de. Pehle har
    # chakkar alag dialogue tha aur do chakkaron ke beech patti khaali dikh
    # jaati thi - ab ek hi lagataar lakeer hai.
    # Ticker ki raftaar ab sthir hai - pixel prati second. Pehle poori lambai
    # ko body ke samay mein baant diya jaata tha, isliye jitni copies badhti
    # thi utni hi raftaar bhi badh jaati thi. Isi wajah se footer bahut tez
    # bhaag raha tha.
    # Akshar bade hue to raftaar bhi badhani padi - warna wahi lakeer nikalne
    # mein kahin zyada waqt leti aur ticker rengta hua lagta. 125 px/s par
    # lagbhag utne hi akshar prati second guzarte hain jitne pehle 105 par
    # 40px ke text ke saath guzarte the.
    if not TICKER_ON:
        _finish(ev, head, sizes_used, path, st, white)
        return

    TICK_SPEED = 125.0
    tick_font = TICK_FONT      # Tick style ke size ke saath badalna zaroori hai
    tick_one = ticker + "          •          "
    # Devanagari ki prati-akshar chaudai ~0.27 (asli naap se milaan karke).
    one_px = max(400, int(len(tick_one) * tick_font * CH_W))
    tick_mid = TICK_Y + TICK_H // 2

    # Ek copy poore band ko lagataar nahi bhar sakti, isliye kai copies ek
    # doosre ke peechhe chalti hain: agli tabhi shuru hoti hai jab pichhli
    # apni poori chaudai aage badh chuki ho - beech mein khaali jagah nahi.
    interval = one_px / TICK_SPEED
    cycle = (W + one_px) / TICK_SPEED
    t0 = show_start + 0.4
    k = 0
    while t0 + k * interval < body_end:
        start = t0 + k * interval
        L("Tick", start, min(start + cycle, body_end), tick_one,
          "{\\move(%d,%d,%d,%d,0,%d)}"
          % (W, tick_mid, -one_px, tick_mid, int(cycle * 1000)))
        k += 1

    # ---- End card
    L("EndBig", body_end + 0.15, dur, channel,
      "{\\fad(400,400)\\pos(%d,%d)}" % (W // 2, END_Y[0]))
    # Alag animated end-card (sy_endcard) aage jud raha ho to ye line wahan
    # button ban kar aati hai - yahan dobara likhna do baar kehna hota.
    if not job.get("endcard"):
        L("EndSub", body_end + 0.4, dur,
          "सब्सक्राइब करें · लाइक करें · शेयर करें" if is_hi
          else "Subscribe  ·  Like  ·  Share",
          "{\\fad(450,400)\\pos(%d,%d)}" % (W // 2, END_Y[1]))

    # Styles [V4+ Styles] mein hi jaani chahiye - [Events] ke baad daalne par
    # libass unhe padhta hi nahi aur text Default style mein gir jaata hai.
    _finish(ev, head, sizes_used, path, st, white)


def _finish(ev, head, sizes_used, path, st, white):
    """Style jodo aur .ass file likh do.

    Ye alag isliye hai ki Reel mein ticker wala poora hissa chhod diya
    jaata hai - aur chhodne ke baad bhi file to likhni hi hai.
    """
    ins = head.index("[Events]") - 1
    for sz in sorted(sizes_used):
        # Outline 3 - sirf parchhai kaafi nahi thi. Ye text asli footage ke
        # upar baithta hai, aur footage kabhi chamakdaar hoti hai (safed
        # imaarat, aasman, deewar). Wahan safed akshar par safed background
        # aa jaata tha aur parchhai use bacha nahi paati thi. Kaali kinaari
        # har haal mein akshar ko background se alag kar deti hai - subtitle
        # mein yahi tareeka har jagah istemal hota hai.
        mg = 120 if not VERTICAL else 55
        head.insert(ins, st("Spoken%d" % sz, sz, white, True, 5, mg, mg, 0,
                            shadow=3, outline=3))

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(head + ev) + "\n")


def build_filter(dur, job, bar_idx):
    pal = backdrop.palette(job.get("category"))
    acc = "%02x%02x%02x" % pal["accent"]
    frames = int(dur * FPS) + FPS
    has_photo = bool(job.get("_hasPhoto"))
    has_clip = bool(job.get("_hasClip"))

    # Yahan TITLE_SECONDS hi sahi hai, LEAD nahi: ye tasveer ka parda aur
    # neeche ki pattiyan hain, jo card ke turant baad aa jaati hain. Aawaaz
    # LEAD par shuru hoti hai - wo baat build_ass ki hai.
    body_start = TITLE_SECONDS
    body_end = max(body_start + 1.0, dur - END_SECONDS)

    if has_clip:
        # Asli chalti hui footage. Ispar Ken Burns nahi lagta - clip khud
        # chal raha hai, uspar aur zoom lagana sirf hilti hui tasveer banata
        # hai. Bas frame bharna hai: badi taraf se scale karke beech se crop,
        # taaki tasveer khinche nahi. fps ek jaisa kar dete hain kyunki har
        # clip 30 par nahi hoti.
        p = ["[1:v]scale=%d:%d:force_original_aspect_ratio=increase,"
             "crop=%d:%d,fps=%d,setpts=PTS-STARTPTS[kb]" % (W, H, W, H, FPS),
             "[0:v][kb]overlay=0:0[bg]"]
    else:
        zoom = "0.00035" if has_photo else "0.00020"
        cap = "1.16" if has_photo else "1.09"
        # Crop ka anupat FRAME ke anupat ka hona chahiye. Reel mein 16:9 ka
        # crop lagane par tasveer ya to khinch jaati hai ya kinaare se kat
        # jaati hai - dono saaf dikhte hain.
        if VERTICAL:
            crop = "1620:2880" if has_photo else "1238:2200"
            scale = "-2:2880" if has_photo else "-2:2200"
        else:
            crop = "2880:1620" if has_photo else "2200:1238"
            scale = "2880:-2" if has_photo else "2200:-2"

        p = ["[1:v]scale=%s,crop=%s,"
             "zoompan=z='min(1.0+%s*on,%s)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
             ":d=%d:s=%dx%d:fps=%d[kb]" % (scale, crop, zoom, cap, frames, W, H, FPS),
             "[0:v][kb]overlay=0:0[bg]"]
    prev = "[bg]"

    if has_photo or has_clip:
        # Tasveer ke upar ek saman parda. Backdrop mein ye gradient PIL se
        # pehle se baked hai, par asli photo ya illustration kisi bhi rang ki
        # ho sakti hai - halke rang wali par safed text doob jaata hai.
        #
        # Ek hi saman parda jaan-boojhkar: pehle alag-alag gehrai ki teen
        # pattiyan lagayi thi aur unke kinaare frame mein saaf lakeer ki tarah
        # dikhne lage.
        #
        # PARDA ANDHERA KARTA THA - PAR RANG BHI CHOOS LETA THA (Sep 2026)
        #
        # Pehle yahan drawbox=color=black@0.46 tha. Studio background ki
        # jaanch mein pakda gaya ki wo sirf andhera nahi karta: YUV mein
        # rang (chroma) ko bhi lagbhag mita deta hai - laal-neela studio
        # bhoora-slaty ho gaya, aur yahi har asli tasveer/footage ke saath
        # bhi ho raha tha (sab kuch dhula-dhula). Ab lutyuv se wahi 46%
        # andhera, par rang apni jagah - roshni utni hi kam, text utna hi
        # padhne layak, bas tasveer bujhi hui nahi lagti.
        #
        # Poori video studio par ho to parda halka (28%): studio khud gehre
        # rang ka hai aur uske beech text ki jagah pehle se saaf hai.
        dim = 0.28 if job.get("_studioOnly") else 0.46
        k = 1.0 - dim
        p.append("%slutyuv=y='16+(val-16)*%.3f':u='128+(val-128)*%.3f'"
                 ":v='128+(val-128)*%.3f'[ph]" % (prev, k, k, k))
        prev = "[ph]"

    prev = _anchor_filters(p, prev, job)

    body = "between(t,%.2f,%.2f)" % (body_start, body_end)

    # Lower third ki dono pattiyan - sirf body ke dauran.
    # Laal patti ka naap build_ass ne headline dekh kar tay kiya hai.
    sy = int(job.get("_strapY") or STRAP_Y)
    sh = int(job.get("_strapH") or STRAP_H)
    p.append("%sdrawbox=x=0:y=%d:w=%d:h=%d:color=0x%s@0.94:t=fill:enable='%s'[s1]"
             % (prev, sy, W, sh, STRAP_RED, body))
    if TICKER_ON:
        p.append("[s1]drawbox=x=0:y=%d:w=%d:h=%d:color=0x%s@0.96:t=fill:enable='%s'[s2]"
                 % (TICK_Y, W, TICK_H, TICKER_BG, body))
    else:
        # Reel mein ticker nahi hai - uski jagah Shorts ka apna UI leta hai.
        p.append("[s1]null[s2]")
    # Patti ke neeche ek baareek accent lakeer
    p.append("[s2]drawbox=x=0:y=%d:w=%d:h=6:color=0x%s@1:t=fill:enable='%s'[s3]"
             % (sy + sh, W, acc, body))

    # Location bug aur badge ke laal box ab yahan nahi bante - libass unhe
    # khud text ke naap ka bana deta hai (BorderStyle=3). Pehle yahan drawbox
    # se bante the aur unki chaudai akshar gin kar andaaze se nikalti thi,
    # isliye text box ke beech mein nahi baithta tha.
    p.append("[s3]null[s5]")

    # Title aur end card ka parda
    p.append("[s5]drawbox=x=0:y=0:w=%d:h=%d:color=0x%02x%02x%02x@0.88:t=fill"
             ":enable='lt(t,%.2f)+gt(t,%.2f)'[s6]"
             % (W, H, pal["bg"][0], pal["bg"][1], pal["bg"][2], body_start, body_end))

    # Progress bar. drawbox ki width expression mein `t` ka matlab THICKNESS
    # hai, time nahi - isliye usse bharti hui bar banti hi nahi. overlay ki
    # x expression mein `t` asli time hai aur eval=frame se har frame par
    # dobara nikalti hai.
    p.append("[s6]drawbox=x=0:y=%d:w=%d:h=8:color=white@0.12:t=fill[p0]" % (H - 8, W))
    p.append("[p0][%d:v]overlay=eval=frame:x='%d*(t/%.3f-1)':y=%d[p1]"
             % (bar_idx, W, dur, H - 8))
    p.append("[p1]ass=overlay.ass[vout]")
    return ";".join(p)


def _anchor_filters(p, prev, job):
    """HeyGen anchor ki khidkiyan - har ek apne input se (render() ne
    '-ss off -t len -i heygen.mp4' jode hain, idx o["_idx"] mein)."""
    for k, o in enumerate(job.get("anchorOverlays") or []):
        idx = o.get("_idx")
        if idx is None:
            continue
        s, e = float(o["start"]), float(o["end"])
        lab = "[an%d]" % k
        head = "[%d:v]setpts=PTS-STARTPTS+%.3f/TB," % (idx, s)
        if o.get("mode") == "pip":
            # Kamar se upar ka hissa, jahan wo khadi hai (cx), 4:5 mein.
            ch = 864
            cw = int(ch * PIP_W / PIP_H)
            x0 = int(max(0, min(1920 - cw, float(o.get("cx") or 0.6) * 1920 - cw / 2)))
            p.append(head + "scale=1920:1080:force_original_aspect_ratio=increase,"
                     "crop=1920:1080,crop=%d:%d:%d:0,scale=%d:%d,"
                     "pad=%d:%d:%d:%d:color=white,format=yuv420p%s"
                     % (cw, ch, x0, PIP_W, PIP_H,
                        PIP_W + 2 * PIP_BORDER, PIP_H + 2 * PIP_BORDER,
                        PIP_BORDER, PIP_BORDER, lab))
            x, y = _pip_box(job)
        else:
            p.append(head + "scale=%d:%d:force_original_aspect_ratio=increase,"
                     "crop=%d:%d,format=yuv420p%s" % (W, H, W, H, lab))
            x, y = 0, 0
        out = "[ao%d]" % k
        p.append("%s%soverlay=%d:%d:enable='between(t,%.3f,%.3f)'"
                 ":eof_action=pass%s" % (prev, lab, x, y, s, e, out))
        prev = out
    return prev


def build_audio(audio, dur, workdir, track=""):
    """Aawaaz + bed ko pehle hi mila kar ek poori WAV bana do.

    YE ALAG KYUN CHALTA HAI - LIGHTHOUSE WALI VIDEO KA ASLI KEEDA
    =============================================================
    Pehle aawaaz ka saara hisaab usi ek bade filter graph mein hota tha
    jismein tasveer ka bhi kaam chal raha tha. Us haalat mein ffmpeg 6.x
    aawaaz ke frames ULTE KRAM mein aage bhej deta hai - encoder saaf
    kehta hai "Queue input is backward in time", aur mp4 likhne wala un
    frames ko gira deta hai.

    Lighthouse wali video mein wahi hua: aawaaz ki patti theek 52.29
    second par toot gayi, teen second ka gaddha bana, aur uske baad ki
    poori aawaaz 1.9 second aage khisak gayi. Isliye aawaaz ka ek tukda
    gayab hua aur screen ka text usse mel khana band kar gaya - wahi jo
    aapne dekha.

    Maine ye unki apni file par dobara paida karke dekha, aur do baat
    naapi:
      - wahi aawaaz ka graph AKELE chalaya jaye (bina tasveer ke) to poora
        67.192 second saaf aata hai, ek bhi gaddha nahi.
      - dono ek saath chalein to har baar wahi toot.

    Isliye ab dono alag: pehle sirf aawaaz banti hai (chhota, seedha,
    do-teen second ka kaam), phir badi render use ek saadi input ki tarah
    uthati hai - us bade graph mein aawaaz par ek bhi filter nahi rehta.

    Ek faayda aur: ab mix.wav workdir mein padi rehti hai, isliye aawaaz
    ko alag se sun kar jaancha ja sakta hai.
    """
    out = os.path.join(workdir, "mix.wav")
    music = MUSIC_PATH if (MUSIC_PATH and os.path.exists(MUSIC_PATH)) else ""
    if track and os.path.exists(track):
        music = track
    if music:
        print("[render] music:", os.path.basename(music), flush=True)

    ms = int(LEAD * 1000)
    # Star pehle NAAP liya, ab sirf ek sthir gain. voice_gain_db() ke upar
    # likha hai ki chalta-firta loudnorm yahan se kyun hataya gaya.
    gdb = voice_gain_db(audio)
    print("[render] aawaaz %+.1f dB" % gdb, flush=True)

    # Aawaaz do baar padhi jaati hai - jaan-boojhkar: ek mix ke liye, ek
    # sidechain ki chaabi ke liye. Ek hi dhaara ko asplit se do jagah
    # bhejne par graph ek doosre ka intezaar karte hue jam jaata tha.
    afilter = (
        "[0:a]adelay=%d|%d,volume=%.2fdB,"
        "apad=whole_dur=%.3f,atrim=0:%.3f[voice];"
        "[1:a]adelay=%d|%d,volume=%.2fdB,"
        "apad=whole_dur=%.3f,atrim=0:%.3f[vkey];"
        % (ms, ms, gdb, dur, dur, ms, ms, gdb, dur, dur))

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", audio, "-i", audio]
    if music:
        cmd += ["-stream_loop", "-1", "-i", music]
        # Shuru mein dheere ubhre, ant mein dheere doobe - jhatke se na kate.
        afilter += ("[2:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                    "volume=%.1fdB,atrim=0:%.3f,afade=t=in:d=1.5,"
                    "afade=t=out:st=%.3f:d=2.5[bedq];"
                    % (TRACK_DB if music == track else MUSIC_DB, dur,
                       max(0.0, dur - 2.5)))
    else:
        # Bina track ke ek halka bed khud bana lete hain: teen dheemi sur
        # (mool, panchan, ashtak) + bahut dheema tremolo. Ye kisi asli
        # composed track ka muqabla nahi karta - wo jagah khaali hai aur
        # MUSIC_PATH usi ke liye hai.
        afilter += (
            "sine=frequency=55:sample_rate=48000:duration=%.3f[m1];"
            "sine=frequency=82.41:sample_rate=48000:duration=%.3f[m2];"
            "sine=frequency=110:sample_rate=48000:duration=%.3f[m3];"
            "[m1][m2][m3]amix=inputs=3:normalize=0,"
            "tremolo=f=0.22:d=0.4,lowpass=f=320,volume=0.35[bedraw];"
            "[bedraw]volume=%.1fdB[bedq];"
            % (dur, dur, dur, MUSIC_DB + 6))

    # Sidechain: jab aawaaz bolti hai, bed apne aap dab jaata hai. Isi
    # wajah se music khabar ke upar nahi chadhta.
    afilter += ("[bedq][vkey]sidechaincompress=threshold=0.03:ratio=8"
                ":attack=20:release=400[bedduck];")
    afilter += "[voice][bedduck]amix=inputs=2:normalize=0:duration=shortest[aout]"

    cmd += ["-filter_complex", afilter, "-map", "[aout]",
            "-t", "%.3f" % dur,
            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", out]
    subprocess.run(cmd, cwd=workdir, check=True)

    # Bani hui aawaaz ko yahin jaanch lete hain. Ye wahi jaanch hai jo is
    # keede ko pehle hi pakad leti - "ban gayi" aur "poori bani" do alag
    # baatein hain, aur yahan sirf doosri wali chalti hai.
    got = media_duration(out)
    if got < dur - 0.35:
        raise RuntimeError(
            "aawaaz poori nahi bani: %.2f second aayi, %.2f chahiye thi"
            % (got, dur))
    return out


def render(job, workdir, out_path):
    # Naap sabse pehle - iske baad ka har hisaab isi par tika hai. job mein
    # "vertical" hone par Reel (1080x1920), warna bulletin (1920x1080).
    set_layout(bool(job.get("vertical")))

    workdir = os.path.abspath(workdir)
    out_path = os.path.abspath(out_path)
    audio = os.path.join(workdir, "voice.wav")
    photo = os.path.join(workdir, "photo.jpg")
    clip = os.path.join(workdir, "clip.mp4")

    # Kram: chalti hui footage sabse achhi, phir tasveer, phir designed
    # backdrop. Clip ho to photo ki zaroorat hi nahi.
    has_clip = os.path.exists(clip) and os.path.getsize(clip) > 20000
    has_photo = (not has_clip) and os.path.exists(photo) and os.path.getsize(photo) > 2048
    job["_hasClip"] = has_clip
    job["_hasPhoto"] = has_photo

    if not has_clip and not has_photo:
        backdrop.build(job.get("style") or "grid",
                       job.get("category"),
                       abs(hash(str(job.get("jobId")))) % 9973,
                       photo)
        # Koi footage nahi - to peeche channel ka chalta hua studio (Sep
        # 2026, sy_scenes.studio_path() dekhiye). Designed backdrop phir
        # bhi upar ban chuka hai: thumbnail ke liye photo.jpg wahi rehta
        # hai jo pehle tha, sirf video ke peeche studio chalta hai.
        studio = str(job.get("studio_bg") or "")
        if studio and os.path.isfile(studio):
            try:
                import shutil
                shutil.copyfile(studio, clip)
                has_clip = True
                has_photo = False
                job["_hasClip"] = True
                job["_hasPhoto"] = False
                job["_studioOnly"] = True
                print("[render] footage nahi - peeche studio background",
                      flush=True)
            except Exception as e:
                print("[render] studio nahi laga (designed backdrop):", e,
                      flush=True)

    dur = audio_duration(audio) + LEAD + END_SECONDS

    # Peeche ki footage poori lambai bhar deni chahiye - PEHLE se, file mein.
    #
    # Yahan pehle "-stream_loop -1" tha: ffmpeg khud clip ko dohra kar poori
    # lambai bhar de. Wo saalon se chalta aaya tha, par 97 second ki video par
    # ffmpeg theek 76 second par jam gaya - na aage badha, na mara, na koi
    # galti batayi. Ghante bhar wahi khada raha aur adhoori file chhodi jismein
    # moov atom tha hi nahi.
    #
    # Jaanch se saaf nikla: bilkul wahi filter, wahi clip, sirf stream_loop
    # hataya - to 97.6 second tak poori chali. stream_loop dohrate waqt
    # timestamp peeche le jaata hai ("non monotonically increasing dts"), aur
    # uske baad graph ek doosre ka intezaar karta reh jaata hai.
    #
    # Isliye ab dohrana ffmpeg ke bharose nahi chhodte: clip ko pehle hi
    # jodkar poori lambai ka bana lete hain, aur render ko ek seedhi, poori
    # file milti hai. Ye stream copy hai - koi dobara encode nahi hota.
    if has_clip:
        clip = _extend_clip(clip, dur, workdir)

    build_ass(job, dur, os.path.join(workdir, "overlay.ass"))

    mixed = build_audio(audio, dur, workdir, pick_music(job.get("jobId")))

    pal = backdrop.palette(job.get("category"))
    acc = "%02x%02x%02x" % pal["accent"]

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "lavfi", "-i",
           "color=c=0x%02x%02x%02x:s=%dx%d:r=%d:d=%.3f" % (pal["bg"] + (W, H, FPS, dur)),
    ]
    if has_clip:
        cmd += ["-i", clip]
    else:
        cmd += ["-loop", "1", "-i", photo]
    cmd += ["-f", "lavfi", "-i",
            "color=c=0x%s:s=%dx8:r=%d:d=%.3f" % (acc, W, FPS, dur),
            "-i", mixed]
    # HeyGen anchor - har khidki ke liye usi video ka sahi hissa. Aawaaz
    # nahi (-an): hont hamari mix.wav se milte hain, uski apni aawaaz se nahi.
    nxt = 4
    for o in job.get("anchorOverlays") or []:
        if VERTICAL or not os.path.exists(str(o.get("file") or "")):
            o["_idx"] = None
            continue
        cmd += ["-an", "-ss", "%.3f" % float(o["off"]),
                "-t", "%.3f" % (float(o["end"]) - float(o["start"]) + 0.2),
                "-i", o["file"]]
        o["_idx"] = nxt
        nxt += 1

    vfilter = build_filter(dur, job, 2)

    # Sirf TASVEER ka filter graph. Aawaaz par yahan ek bhi filter nahi -
    # wo upar build_audio() mein pehle hi ban chuki hai aur yahan seedhi
    # copy hokar aati hai. Wajah wahin likhi hai.
    cmd += ["-filter_complex", vfilter,
            "-map", "[vout]", "-map", "3:a",
            "-t", "%.3f" % dur,
            "-c:v", "libx264", "-preset", "medium", "-crf", "21",
            "-maxrate", "2400k", "-bufsize", "5000k",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            out_path]

    subprocess.run(cmd, cwd=workdir, check=True)
    return out_path, dur


if __name__ == "__main__":
    import sys
    wd = sys.argv[1] if len(sys.argv) > 1 else "."
    with open(os.path.join(wd, "job.json"), encoding="utf-8") as f:
        job = json.load(f)
    out, d = render(job, wd, os.path.join(wd, "out.mp4"))
    print("rendered %s (%.2fs)" % (out, d))

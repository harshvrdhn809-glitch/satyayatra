"""Reporter ki bheji khabar -> video (Google Form -> Sheet + Drive).

Hamare kai reporter kam padhe-likhe hain aur Telegram nahi chala sakte. Unke
paas sirf phone ka browser hai. Isliye ek Google Form hai (banane ka tareeka
REPORTER_FORM.md mein): reporter naam, jagah, kya hua, kisne kya kaha likhta
(ya bol kar type karta) hai aur video/photo chadha deta hai. Google khud
jawab ek Sheet ki line mein aur files ek Drive folder mein rakh deta hai.

Ye file us Sheet ko har kuch minute padhti hai:

  nayi line    -> sampadak (Claude) SIRF form ki baat se script likhta hai
                  -> khabar katar mein, sabse aage (FORCE_KEY, /khabar jaisa)
  video banate -> Drive se reporter ki clips utarti hain, khadi (9:16) video
                  16:9 mein blur-fill hoti hai, Claude frame dekh kar tay
                  karta hai ki kaunsi clip script ki kis baat par chale.
                  Jahan kami ho wahan pehle jaisa Commons/Pexels/studio.
  har baari    -> Sheet ki usi line mein "SatyaYatra स्थिति" column: ban
                  rahi / approval par / YouTube par chadh gayi <link> /
                  roki gayi - wajah.

Baaki sab waisa hi: Telegram par approval, phir YouTube, phir Facebook.

Chaabi: wahi service account (satyayatra-sa.json, cloud par GCP_SA_JSON
Secret se) jo Veo ke liye hai - bas scope alag (Sheets + Drive). Sheet ki
id config [report] sheet_id mein, cloud par REPORT_SHEET_ID Secret se.
Repo public hai - sheet id kahin code ya docs mein nahi likhni.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import sy_ai
import sy_config as cfg
import sy_store as st

BEAT = "report"
PREFIX = "rep_"
CREDIT = "SatyaYatra संवाददाता"
STATUS_HEADER = "SatyaYatra स्थिति"

SCOPES = ("https://www.googleapis.com/auth/spreadsheets "
          "https://www.googleapis.com/auth/drive.readonly")
SHEETS = "https://sheets.googleapis.com/v4/spreadsheets/"
DRIVE = "https://www.googleapis.com/drive/v3/files/"

# Reporter ki video ka naap - khabar 16:9 mein banti hai.
W, H = 1920, 1080
FPS = 30
# Ek clip ka ek tukda isse lamba nahi - sy_scenes clip ek hi baar chalata
# hai, baaki samay studio par. Lambi clip ke kai tukde alag baaton par.
PIECE_MAX = 25.0
# Ek khabar mein itni se zyada file nahi dekhte - Claude ko dikhane wali
# jhalak (contact sheet) bhi isi se bandhi hai.
MAX_MEDIA = 8


def log(*a):
    print("[report]", *a, flush=True)


# ------------------------------------------------------------------ config

def sheet_id():
    return cfg.get("report", "sheet_id")


def enabled():
    return bool(sheet_id()) and cfg.num("report", "enabled", 1) == 1


def check_minutes():
    return max(1, cfg.num("report", "check_minutes", 5))


def max_file_mb():
    return max(20, cfg.num("report", "max_file_mb", 1000))


def is_report(story_or_id):
    sid = story_or_id.get("story_id") if isinstance(story_or_id, dict) else story_or_id
    return str(sid or "").startswith(PREFIX)


# ------------------------------------------------ form ke sawal -> hamare naam
#
# Sheet ke column ka naam wahi hota hai jo form mein sawal ka text hai.
# Reporter form thoda badal bhi de (ek shabd, ek viram), to bhi pehchaan
# bani rahe - isliye poora text nahi, har sawal ke KHAAS shabd milate hain.
# Kram zaroori hai: pehle wo jinke shabd doosron mein bhi aa sakte hain
# ("बयान वाली वीडियो" mein "वीडियो" bhi hai aur "बयान" bhi).
FIELDS = [
    ("timestamp", ["timestamp", "टाइमस्टैम्प", "समय-चिह्न"]),
    ("status", ["satyayatra", "स्थिति"]),
    ("bayan_video", ["बयान वाली"]),
    ("ghatna_video", ["जगह की वीडियो", "घटना की वीडियो", "घटना / जगह"]),
    ("photo", ["फोटो", "फ़ोटो", "तस्वीर"]),
    ("ijazat", ["इजाजत", "इजाज़त", "अनुमति"]),
    ("chehra", ["चेहरा"]),
    ("bayan_kaun", ["किसने"]),
    ("bayan_kya", ["क्या कहा"]),
    ("naam", ["आपका नाम"]),
    ("mobile", ["मोबाइल"]),
    ("reporter_zila", ["आपका जिला", "आपका ज़िला"]),
    ("ek_line", ["एक लाइन"]),
    ("kya_hua", ["क्या हुआ"]),
    ("tareekh", ["तारीख"]),
    ("samay", ["समय"]),
    ("zila", ["किस जिले", "किस ज़िले", "जिला", "ज़िला"]),
    ("jagah", ["गांव", "गाँव", "मोहल्ला"]),
    ("log", ["जुड़े", "कौन-कौन", "कौन कौन"]),
    ("aankde", ["आंकड़े", "आँकड़े", "आंकडे"]),
]
FILE_FIELDS = ("ghatna_video", "bayan_video", "photo")


def _norm_hi(s):
    """Milaan ke liye: nukta hatao, chandrabindu = anusvaar, chhote akshar."""
    s = str(s or "").lower().replace("़", "")
    s = s.replace("ँ", "ं")
    return re.sub(r"\s+", " ", s).strip()


def map_headers(headers):
    """{column number: hamara naam}. Har naam ek hi column ko milta hai."""
    out, taken = {}, set()
    for key, needles in FIELDS:
        ns = [_norm_hi(n) for n in needles]
        for i, h in enumerate(headers):
            if i in out:
                continue
            hn = _norm_hi(h)
            if hn and any(n in hn for n in ns):
                out[i] = key
                taken.add(key)
                break
    return out


def status_col(headers, hmap):
    for i, k in hmap.items():
        if k == "status":
            return i
    return len(headers)


def parse_row(hmap, row):
    rec = {}
    for i, key in hmap.items():
        if key == "status":
            continue
        v = row[i] if i < len(row) else ""
        rec[key] = re.sub(r"[ \t]+", " ", str(v or "")).strip()
    return rec


def drive_ids(cell):
    """Form ke upload wale jawab mein Drive ke link hote hain, comma se
    alag: https://drive.google.com/open?id=XXXX (kabhi /file/d/XXXX/)."""
    out = []
    for m in re.finditer(r"(?:[?&]id=|/d/)([A-Za-z0-9_-]{20,})", str(cell or "")):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def yes(v):
    """Form ka "हाँ" / checkbox bhara hua. "नहीं" ya khaali = nahi."""
    v = _norm_hi(v)
    if not v or v.startswith(("नहीं", "नही", "nahi", "no")):
        return False
    return any(w in v for w in ("हां", "haan", "han", "yes", "ली है"))


def row_key(rec):
    """Line ki pehchaan - samay + mobile + khabar. Sheet ki line ka NUMBER
    nahi: koi Sheet ko sort kar de to number badal jaate hain."""
    raw = "|".join([rec.get("timestamp", ""), rec.get("mobile", ""),
                    rec.get("ek_line", "")[:80]])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def story_id_for(rec, key):
    day = re.sub(r"[^0-9]", "", time.strftime("%Y%m%d"))
    return "%s%s_%s" % (PREFIX, day, key[:6])


def usable(rec):
    """Form mein khabar hai bhi? (haan/nahi, wajah) - ahmiyat nahi dekhte."""
    text = (rec.get("ek_line", "") + " " + rec.get("kya_hua", "")).strip()
    if len(re.sub(r"\W+", "", text)) < 12:
        return False, "form mein khabar likhi hi nahi (ek line / kya hua khaali)"
    return True, ""


# -------------------------------------------------------------- Google API

def _sa():
    import sy_veo
    p = sy_veo.sa_path()
    if not p:
        raise RuntimeError("service account (satyayatra-sa.json) nahi mili")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def sa_email():
    try:
        return str(_sa().get("client_email") or "")
    except Exception:
        return ""


def _token():
    import vertex
    return vertex._access_token(_sa(), SCOPES)


def _api(url, body=None, method=None, timeout=60):
    data = None
    h = {"Authorization": "Bearer " + _token()}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            msg = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            msg = ""
        raise RuntimeError("Google %d: %s" % (e.code, msg))


_tab_cache = {}


def sheet_tab():
    """Jawab wala tab. Form khud ek tab banata hai ("Form Responses 1" ya
    Hindi mein "फ़ॉर्म के जवाब 1") - wo aam taur par pehla hota hai."""
    given = cfg.get("report", "sheet_tab")
    if given:
        return given
    sid = sheet_id()
    if sid in _tab_cache:
        return _tab_cache[sid]
    j = _api(SHEETS + urllib.parse.quote(sid) + "?fields=sheets.properties.title")
    titles = [s["properties"]["title"] for s in j.get("sheets") or []]
    pick = next((t for t in titles if "form" in t.lower() or "फ़ॉर्म" in t
                 or "फॉर्म" in t), titles[0] if titles else "Sheet1")
    _tab_cache[sid] = pick
    return pick


def _rng(a1):
    return urllib.parse.quote("'%s'!%s" % (sheet_tab().replace("'", "''"), a1), safe="")


def read_sheet():
    """(headers, rows) - rows mein pehli line (headers) nahi."""
    j = _api(SHEETS + urllib.parse.quote(sheet_id()) + "/values/" + _rng("A1:ZZ"))
    vals = j.get("values") or []
    if not vals:
        return [], []
    return [str(x) for x in vals[0]], vals[1:]


def col_letter(i):
    s, i = "", int(i) + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def write_cell(row_num, col, text):
    a1 = "%s%d" % (col_letter(col), int(row_num))
    _api(SHEETS + urllib.parse.quote(sheet_id()) + "/values/" + _rng(a1)
         + "?valueInputOption=RAW", body={"values": [[str(text)[:500]]]},
         method="PUT")


def drive_download(file_id, dest_dir):
    """Drive se file utaaro (tukdon mein, poori memory mein nahi). (path, naam, mime)."""
    meta = _api(DRIVE + urllib.parse.quote(file_id)
                + "?fields=name,mimeType,size&supportsAllDrives=true")
    name = str(meta.get("name") or file_id)
    mime = str(meta.get("mimeType") or "")
    size = int(meta.get("size") or 0)
    cap = max_file_mb() * 1024 * 1024
    if size > cap:
        raise RuntimeError("%s bahut badi hai (%d MB)" % (name, size // 1048576))
    ext = os.path.splitext(name)[1].lower()[:6] or (".mp4" if "video" in mime else ".jpg")
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, "f_%s%s" % (file_id[:10], ext))
    req = urllib.request.Request(
        DRIVE + urllib.parse.quote(file_id) + "?alt=media&supportsAllDrives=true",
        headers={"Authorization": "Bearer " + _token()})
    got = 0
    with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            got += len(chunk)
            if got > cap:
                raise RuntimeError("%s bahut badi hai" % name)
            f.write(chunk)
    return path, name, mime


# ---------------------------------------------------------------- status

def status_text(story):
    """Sheet mein kya likhein - Hinglish, taaki aap (aur reporter) samjhein."""
    if not story:
        return ""
    s = str(story.get("status") or "")
    err = re.sub(r"\s+", " ", str(story.get("error") or "")).strip()[:200]
    if s in ("pending", "producing"):
        return "ban rahi hai"
    if s == "awaiting":
        return "approval par (Telegram)"
    if s == "approved":
        return "approve ho gayi - YouTube ki baari"
    if s == "published":
        vid = str(story.get("youtube_id") or "")
        return "YouTube par chadh gayi" + (" https://youtu.be/" + vid if vid else "")
    if s == "rejected":
        return "roki gayi - sampadak ne approve nahi ki"
    return "roki gayi - " + (err or s or "wajah nahi likhi")


# ------------------------------------------------------------ sampadak

REPORT_SYSTEM = "\n".join([
    'Aap ek Indian digital news channel (SatyaYatra) ke senior editor hain. Aapke apne sthaniya samvaddata (reporter) ne ek form bhar kar zameeni khabar bheji hai. Aap usse Hindi broadcast script likhte hain.',
    '',
    'SABSE SAKHT NIYAM - SIRF FORM:',
    '1. Script mein SIRF wahi aaye jo form mein likha hai. Koi naam, number, jagah, tareekh, pad, quote ya pichhli ghatna khud se ya apni jaankari/internet se mat jodiye - chahe aapko wo "pata" ho.',
    '2. Jo form mein nahi hai, wo script mein nahi hai. Khaali jagah bharne ke liye "sootron ke mutabik", "bataya ja raha hai" jaisa kuch mat likhiye.',
    '3. Aarop, daawe aur bayan attribute kijiye - "गांव वालों का आरोप है कि...", "थाना प्रभारी ने कहा कि...". Kisi aarop ko sthapit tathya ki tarah mat likhiye.',
    '4. Nabalig (bachche) ya yaun hinsa ke peedit ka naam aur pehchaan kabhi mat likhiye, chahe form mein ho. Aam aaropi/peedit ka naam bhi tabhi jab wo police/adhikari ke bayan mein aaya ho.',
    '5. Motive par koi kalpana nahi, koi bhavishyavani nahi, koi rai nahi.',
    '',
    'AHMIYAT KA FAISLA AAPKA NAHI HAI. Ye khabar channel ke apne reporter ne bheji hai. In wajahon se publishable false KABHI mat kijiye:',
    '- khabar chhoti, sthaniya ya kam logon ke kaam ki lagti hai;',
    '- dikhane layak tasveer kam lagti hai (reporter ki video/photo hai, baaki studio se ban jayegi);',
    '- sirf ek hi srot (reporter) hai.',
    'publishable false SIRF tab: form mein koi thos tathya hi nahi (khaali, bekaar, samajh na aane wala), ya poori baat sirf afwaah/suni-sunaayi hai, ya khabar kisi par bina kisi aadhaar ke gambhir aarop hai. Tab kill_reason mein saaf Hinglish mein likhiye ki kya kami hai - wo Sheet mein reporter ke liye likha jayega.',
    '',
    'REPORTER KI BHASHA: form bol kar type (voice typing) se bhara ho sakta hai - galat matra, tute vaakya, Roman Hindi. Matlab samajh kar saaf Hindi mein likhiye, par matlab mat badliye. Jo baat saaf samajh na aaye, use chhod dijiye.',
    '',
    'GEHRAI: form mein jo bhi hai - kab, kahan (gaon/mohalla, zila), kaun, kitne (aankde), kisne kya kaha, ab kya - sab script mein aana chahiye. Tareekh ho to use swabhavik roop se boliye ("27 सितंबर को").',
    '',
    'BAYAN: agar form mein bayan (kisne kaha + kya kaha) hai, to script mein use naam aur pad ke saath attribute kijiye. Agar "BAYAN KI VIDEO HAI" likha ho, to script mein bayan se theek pehle EK chhota vaakya rakhiye jo darshak ko bayan sunne ke liye taiyar kare, jaise "इस बारे में थाना प्रभारी रमेश कुमार ने क्या कहा, सुनिए।" - aur wahi vaakya hoobahoo "bayan_intro" mein bhi likhiye. Us vaakya ke baad bayan ki asli video (unki apni aawaaz mein) chalegi, isliye uske baad bayan ko dobara shabdsha mat dohraiye - script aage ki baat se chalu rakhiye.',
    '',
    'REPORTER KA NAAM script mein mat likhiye - wo description mein apne aap judta hai.',
    '',
    'STYLE: neutral, saral, boli jaane wali Hindi (Devanagari). Chhote vaakya - ise ek synthetic anchor padhega.',
    'LAMBAI: form mein jitni jaankari hai utni - 60 se 200 shabd. Shabd bharne ke liye lambai mat badhaiye.',
    '',
    'Sirf ek JSON object return kijiye, bina markdown fence ke, in keys ke saath:',
    '{',
    '  "publishable": boolean, "kill_reason": string,',
    '  "headline_hi": string, "headline_en": string,',
    '  "script_hi": string,',
    '  "lower_third_hi": string,  (60 akshar se kam, ek hi baat)',
    '  "place_en": string,  (khabar ki jagah angrezi mein, jaise "Mirzapur" - tasveer khojne ke liye; gaon ho to "Village, District")',
    '  "bayan_intro": string,  (upar dekhiye; bayan video na ho to "")',
    '  "bayan_name": string, "bayan_pad": string,  (bayan dene wale ka naam aur pad, Devanagari mein, jaisa form mein hai; na ho to "")',
    '  "broll_keywords": [string],',
    '  "youtube_title_hi": string,  (90 akshar se kam, sacha, clickbait nahi)',
    '  "title_options_hi": [string, string, string],',
    '  "youtube_description_hi": string,  (khabar ke mukhya bindu 2-3 chhote paragraph mein)',
    '  "tags": [string]',
    '}',
])


def form_text(rec, has_bayan_video=False):
    """Sampadak ko form jaisa ka taisa - sawal ke naam ke saath."""
    rows = [
        ("Ek line mein khabar", rec.get("ek_line")),
        ("Kya hua (vistaar)", rec.get("kya_hua")),
        ("Tareekh", rec.get("tareekh")),
        ("Samay", rec.get("samay")),
        ("Zila", rec.get("zila") or rec.get("reporter_zila")),
        ("Gaon / mohalla / jagah", rec.get("jagah")),
        ("Kaun-kaun log / adhikari", rec.get("log")),
        ("Aankde", rec.get("aankde")),
        ("Bayan kisne diya (naam, pad)", rec.get("bayan_kaun")),
        ("Bayan mein kya kaha", rec.get("bayan_kya")),
    ]
    out = ["REPORTER KA FORM (yahi ek-maatra srot hai)", ""]
    for k, v in rows:
        v = str(v or "").strip()
        if v:
            out.append("%s: %s" % (k, v))
    out.append("")
    n_g = len(drive_ids(rec.get("ghatna_video")))
    n_p = len(drive_ids(rec.get("photo")))
    out.append("Reporter ne %d ghatna/jagah ki video aur %d photo bheji hai." % (n_g, n_p))
    if has_bayan_video:
        out.append("BAYAN KI VIDEO HAI - bayan_intro wala niyam lagu hai.")
    else:
        out.append("Bayan ki video NAHI hai - bayan_intro khaali rakhiye.")
    return "\n".join(out)


def bayan_video_ok(rec):
    """Bayan wali video asli aawaaz ke saath tabhi, jab video ho aur reporter
    ne ijaazat wala dabba bhara ho."""
    return bool(drive_ids(rec.get("bayan_video"))) and yes(rec.get("ijazat"))


def ingest(rec, key):
    """Ek form line se katar mein khabar. (story_id, wajah) - roki gayi to
    bhi story_id milta hai (status report_killed), taaki line dobara na uthe."""
    sid = story_id_for(rec, key)
    naam = rec.get("naam") or "?"
    base = {
        "story_id": sid, "beat": BEAT, "score": 20,
        "sources": CREDIT, "source_link": "",
        "attribution_line": "%s: %s" % (CREDIT, naam),
        "headline_hi": (rec.get("ek_line") or "reporter ki khabar")[:200],
    }
    ok, why = usable(rec)
    if not ok:
        st.add_story(dict(base, status="report_killed", error=why))
        return sid, why

    has_bv = bayan_video_ok(rec)
    j = sy_ai.ask_json(REPORT_SYSTEM, form_text(rec, has_bv), max_tokens=4000)
    if not j:
        # Jawab hi nahi aaya (net/API) - agli baari dobara. Teen baar ke baad bas.
        n = int(st.kv_get("report_try_" + key, 0) or 0) + 1
        st.kv_set("report_try_" + key, n)
        if n < 3:
            return "", "sampadak ka jawab nahi aaya - dobara koshish hogi"
        why = "sampadak ka jawab teen baar nahi aaya"
        st.add_story(dict(base, status="report_killed", error=why))
        return sid, why
    if j.get("publishable") is not True:
        why = str(j.get("kill_reason") or "sampadak ne roka")[:300]
        st.add_story(dict(base, status="report_killed", error=why))
        return sid, why
    script = re.sub(r"\s+", " ", str(j.get("script_hi") or "")).strip()
    if len(script) < 60:
        why = "script bahut chhoti bani - form mein aur jaankari chahiye"
        st.add_story(dict(base, status="report_killed", error=why))
        return sid, why

    desc = str(j.get("youtube_description_hi") or "").strip()
    desc += ("\n\nयह ख़बर SatyaYatra के संवाददाता की ज़मीनी रिपोर्ट पर आधारित है; "
             "वीडियो/फ़ोटो उन्हीं के भेजे हुए हैं।")
    st.add_story(dict(
        base,
        headline_hi=str(j.get("headline_hi") or base["headline_hi"])[:200],
        headline_en=str(j.get("headline_en") or "")[:200],
        lower_third_hi=str(j.get("lower_third_hi") or "")[:140],
        script_hi=script,
        yt_title=str(j.get("youtube_title_hi") or "")[:95],
        yt_description=desc.strip(),
        tags=", ".join(str(t) for t in (j.get("tags") or []))[:480],
    ))
    try:
        import sy_ingest
        sy_ingest.save_titles(sid, j, str(j.get("youtube_title_hi") or "")[:95])
    except Exception:
        pass
    # Video banate waqt chahiye: kaunsi file kahan hai, chehra, bayan.
    st.kv_set("report_" + sid, {
        "rec": rec, "key": key,
        "place_en": str(j.get("place_en") or "")[:60],
        "bayan_intro": str(j.get("bayan_intro") or "").strip() if has_bv else "",
        "bayan_name": str(j.get("bayan_name") or "")[:60],
        "bayan_pad": str(j.get("bayan_pad") or "")[:80],
    })
    return sid, ""


# -------------------------------------------------------------- har baari

def tick():
    """sy_main ka kadam. Sheet padho, nayi line katar mein, purani ki
    haalat Sheet mein. Ek baari mein ek hi nayi line (sampadak ka call)."""
    if not enabled():
        return []
    if not st.due("report_sheet", check_minutes()):
        return []
    try:
        headers, rows = read_sheet()
    except Exception as e:
        log("Sheet nahi padhi:", str(e)[:300])
        _warn_once("Reporter wali Google Sheet nahi padhi ja saki.\n\n<b>Wajah:</b> "
                   + str(e)[:400] + "\n\nREPORTER_FORM.md ka share wala kadam "
                   "dekhiye (Sheet service account ke saath Editor share ho: "
                   + sa_email() + ")")
        return []
    if not headers:
        return []
    hmap = map_headers(headers)
    scol = status_col(headers, hmap)
    if scol >= len(headers) or not str(headers[scol]).strip():
        try:
            write_cell(1, scol, STATUS_HEADER)
        except Exception as e:
            log("status column nahi bana:", str(e)[:200])
            _warn_once("Reporter Sheet mein likh nahi paa rahe - service account "
                       "ko Viewer nahi, <b>Editor</b> banaiye.\n\n" + str(e)[:300])
            return []

    index = st.kv_get("report_rows") or {}
    made = []
    new_done = False
    for n, row in enumerate(rows, start=2):
        rec = parse_row(hmap, row)
        if not any(rec.values()):
            continue
        key = row_key(rec)
        sid = index.get(key)
        if not sid and not new_done:
            new_done = True
            log("nayi reporter khabar (line %d): %s - %s"
                % (n, rec.get("naam"), rec.get("ek_line", "")[:60]))
            try:
                _set(n, scol, row, "padh rahe hain - script ban rahi hai")
                sid, why = ingest(rec, key)
            except Exception as e:
                log("reporter khabar par gadbad:", e)
                sid, why = "", str(e)
            if sid:
                index[key] = sid
                st.kv_set("report_rows", index)
                if not why:
                    made.append(sid)
                _notify(rec, sid, why)
        if sid:
            story = st.get(sid)
            if _needs_retry(story) and sid not in made:
                made.append(sid)
            try:
                _set(n, scol, row, status_text(st.get(sid)))
            except Exception as e:
                log("status nahi likha (line %d): %s" % (n, str(e)[:160]))
    return made


RETRIES = 3


def _needs_retry(story):
    """Video banate waqt gadbad hui thi (failed -> agli run mein pending).
    Teen baar tak phir se aage lagao, uske baad roko aur wajah likho -
    warna har run badi files dobara utarti aur dobara girti."""
    if not story:
        return False
    sid = story["story_id"]
    s = story.get("status")
    if s == "failed":
        st.kv_set("report_err_" + sid, str(story.get("error") or "")[:200])
        return False
    if s != "pending":
        return False
    force = str(st.kv_get("force_next", "") or "").split(",")
    if sid in force:
        return False
    n = int(st.kv_get("report_attempt_" + sid, 0) or 0)
    if n >= RETRIES:
        st.update(sid, status="report_killed", error=(
            "%d baar koshish ke baad bhi video nahi bani: %s"
            % (RETRIES, st.kv_get("report_err_" + sid, "") or "log dekhiye")))
        return False
    st.kv_set("report_attempt_" + sid, n + 1)
    return True


def _set(n, scol, row, text):
    cur = str(row[scol]) if scol < len(row) else ""
    if text and cur.strip() != text.strip():
        write_cell(n, scol, text)
        while len(row) <= scol:
            row.append("")
        row[scol] = text


def _warn_once(text):
    day = time.strftime("%Y-%m-%d")
    if st.kv_get("report_warned_day") == day:
        return
    st.kv_set("report_warned_day", day)
    try:
        import sy_telegram
        sy_telegram.send_message(text)
    except Exception:
        pass


def _notify(rec, sid, why):
    try:
        import sy_telegram
        e = sy_telegram._esc
        head = "<b>Reporter ki khabar aayi</b>\n\n%s (%s)\n%s\n\n" % (
            e(rec.get("naam") or "?"), e(rec.get("zila") or rec.get("reporter_zila") or ""),
            e(rec.get("ek_line") or "")[:200])
        if why:
            sy_telegram.send_message(head + "<b>Roki gayi:</b> " + e(why)[:400])
        else:
            sy_telegram.send_message(head + "Script ban gayi - video ab banegi, "
                                     "phir approval ka sandesh aayega.")
    except Exception:
        pass


# ------------------------------------------------------------ media

def _probe(path):
    """(duration, width, height, has_audio) - rotation ke baad ka naap."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height:stream_side_data=rotation"
             ":stream_tags=rotate", "-of", "json", path],
            capture_output=True, text=True, timeout=60)
        j = json.loads(out.stdout or "{}")
    except Exception:
        return 0.0, 0, 0, False
    dur = float((j.get("format") or {}).get("duration") or 0)
    w = h = 0
    audio = False
    for s in j.get("streams") or []:
        if s.get("codec_type") == "audio":
            audio = True
        if s.get("codec_type") == "video" and not w:
            w, h = int(s.get("width") or 0), int(s.get("height") or 0)
            rot = str((s.get("tags") or {}).get("rotate") or "")
            for sd in s.get("side_data_list") or []:
                if "rotation" in sd:
                    rot = str(sd.get("rotation"))
            if rot.strip().lstrip("-") in ("90", "270"):
                w, h = h, w
    return dur, w, h, audio


def fill_filter(w=W, h=H):
    """Koi bhi naap -> 16:9. Khadi phone video ke dono taraf usi video ka
    dhundhla, bada roop (TV channel yahi karte hain) - kaali patti nahi,
    aur kheench kar mota-patla bhi nahi."""
    return ("split=2[a][b];"
            "[a]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
            "boxblur=10:2,scale=%d:%d[bg];"
            "[b]scale=%d:%d:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p"
            % (w // 4, h // 4, w // 4, h // 4, w, h, w, h))


def is_video(path, mime=""):
    if str(mime).startswith("video/"):
        return True
    if str(mime).startswith("image/"):
        return False
    return os.path.splitext(path)[1].lower() in (
        ".mp4", ".mov", ".3gp", ".mkv", ".webm", ".m4v", ".avi")


def normalize_clip(src, out, start, dur, faces=False):
    """src ka [start, start+dur) hissa -> 1920x1080, bina aawaaz."""
    tmp = out + ".tmp.mp4" if faces else out
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-ss", "%.3f" % max(0.0, start), "-t", "%.3f" % dur, "-i", src,
         "-filter_complex", "[0:v]" + fill_filter() + ",fps=%d[v]" % FPS,
         "-map", "[v]", "-an",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
         "-pix_fmt", "yuv420p", tmp],
        check=True, timeout=900)
    if faces:
        blur_faces_video(tmp, out)
        try:
            os.remove(tmp)
        except Exception:
            pass
    return out


def normalize_photo(src, out, faces=False):
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
         "-filter_complex", "[0:v]" + fill_filter() + "[v]", "-map", "[v]",
         "-frames:v", "1", "-q:v", "2", out],
        check=True, timeout=300)
    if faces:
        blur_faces_image(out)
    return out


# ----------------------------------------------------- chehra chhupana
#
# Form mein "kisi ka chehra chhupana hai? - Haan" ho to reporter ki har
# clip/photo mein chehre dhundhle hote hain. OpenCV (opencv-python-headless)
# ke saamne aur bagal wale chehre ke detector se - har frame par, aur ek
# chehra do-chaar frame chhoot bhi jaye to pichhla dabba kuch der tak
# lagaa rehta hai. Ye PAKKA nahi hai: bheed, andhera, jhuka hua sar ya
# door ka chehra chhoot sakta hai. Isliye Telegram ke approval sandesh mein
# saaf chetavni jaati hai - approve karne se pehle dhyan se dekhiye.
#
# OpenCV na mile to poora frame dhundhla - chehra kabhi bina chhupaye nahi.

def _cv():
    try:
        import cv2
        return cv2
    except Exception:
        return None


_cascades = []


def _detectors(cv2):
    if not _cascades:
        base = getattr(getattr(cv2, "data", None), "haarcascades", "")
        for name in ("haarcascade_frontalface_default.xml",
                     "haarcascade_frontalface_alt2.xml",
                     "haarcascade_profileface.xml"):
            c = cv2.CascadeClassifier(os.path.join(base, name))
            if not c.empty():
                _cascades.append(c)
    return _cascades


def face_boxes(cv2, frame):
    """Chehre ke dabbe (x, y, w, h) - thode bade, taaki baal/thodi bhi dhake."""
    small_w = 640
    fh, fw = frame.shape[:2]
    k = fw / float(small_w) if fw > small_w else 1.0
    img = cv2.resize(frame, (int(fw / k), int(fh / k))) if k > 1 else frame
    gray = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    boxes = []
    for i, c in enumerate(_detectors(cv2)):
        found = c.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4,
                                   minSize=(18, 18))
        boxes += [tuple(b) for b in found]
        if i == 2:
            # bagal wala detector sirf ek taraf dekhta hai - ulta karke doosri taraf
            flip = cv2.flip(gray, 1)
            gw = gray.shape[1]
            for (x, y, w, h) in c.detectMultiScale(flip, 1.1, 4, minSize=(18, 18)):
                boxes.append((gw - x - w, y, w, h))
    out = []
    for (x, y, w, h) in boxes:
        pad = 0.35
        x0 = max(0, int((x - w * pad) * k))
        y0 = max(0, int((y - h * pad) * k))
        x1 = min(fw, int((x + w * (1 + pad)) * k))
        y1 = min(fh, int((y + h * (1 + pad)) * k))
        out.append((x0, y0, x1 - x0, y1 - y0))
    return out


def _pixelate(cv2, frame, boxes):
    for (x, y, w, h) in boxes:
        if w < 4 or h < 4:
            continue
        roi = frame[y:y + h, x:x + w]
        tiny = cv2.resize(roi, (max(1, w // 14), max(1, h // 14)))
        roi = cv2.resize(tiny, (w, h), interpolation=cv2.INTER_NEAREST)
        frame[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (0, 0), 6)
    return frame


def blur_faces_image(path):
    cv2 = _cv()
    if cv2 is None:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-i", path, "-vf", "boxblur=40:3", path + ".b.jpg"],
                       check=True, timeout=120)
        os.replace(path + ".b.jpg", path)
        return "poora frame"
    img = cv2.imread(path)
    if img is None:
        return ""
    boxes = face_boxes(cv2, img)
    cv2.imwrite(path, _pixelate(cv2, img, boxes))
    return "%d chehre" % len(boxes)


def blur_faces_video(src, out, audio_from=""):
    """Har frame par chehre dhundhle. audio_from diya ho to uski aawaaz jodi."""
    cv2 = _cv()
    amap = []
    if audio_from:
        amap = ["-i", audio_from, "-map", "0:v", "-map", "1:a?", "-c:a", "aac",
                "-b:a", "192k"]
    if cv2 is None:
        log("OpenCV nahi - poora frame dhundhla kar rahe hain")
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src]
        cmd += amap + ["-vf", "boxblur=40:3", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "21", "-pix_fmt", "yuv420p", out]
        subprocess.run(cmd, check=True, timeout=900)
        return
    cap = cv2.VideoCapture(src)
    fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or FPS
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "%dx%d" % (fw, fh),
           "-r", "%.3f" % fps, "-i", "-"] + amap + [
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
           "-pix_fmt", "yuv420p", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    hold = []           # (dabba, kitne frame aur)
    n = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if n % 2 == 0:
                fresh = face_boxes(cv2, frame)
                hold = [(b, 8) for b in fresh] + [(b, t - 2) for b, t in hold if t > 2]
            frame = _pixelate(cv2, frame, [b for b, _t in hold])
            p.stdin.write(frame.tobytes())
            n += 1
    finally:
        cap.release()
        try:
            p.stdin.close()
        except Exception:
            pass
        p.wait(timeout=900)
    if p.returncode != 0:
        raise RuntimeError("chehra dhundhla karne wala encode fail hua")


# ------------------------------------------------------- clip milaan

MATCH_SYSTEM = "\n".join([
    'Aap ek Indian news channel ke picture editor hain. Reporter ne ghatna-sthal se video/photo bheji hain. Aapko tay karna hai ki script ki kis baat par reporter ki kaunsi file chale.',
    'Tasveer mein har file ki ek line hai - line ke shuru mein mota number file ka number hai (video ho to uske teen frame).',
    'Niyam: jis baat par jo file sach mein mel khaati ho wahi. Pehli baat par jagah/ghatna dikhane wali file behtar. Bayan wali baat par bayan wali file. Ek file kai baaton par chal sakti hai (lambi video ke alag hisse). Koi file kisi baat se bilkul mel na khaaye to us baat ko 0 dijiye - wahan doosra drishya lagega.',
    'Bekaar file (kaala/dhundhla frame, galti se chadhi screenshot) ko "bekaar" mein daaliye.',
    'Sirf JSON: {"assign": [{"shot": 1, "file": 2}, ...], "bekaar": [number], "note": "ek line"}',
])


def contact_sheet(media, workdir, out_name="rep_sheet.jpg"):
    """Har file ki ek line (video ke teen frame), number ke saath - ek
    tasveer, ek vision call."""
    from PIL import Image, ImageDraw, ImageFont
    tw, th = 320, 180
    rows = []
    for i, m in enumerate(media, start=1):
        frames = []
        if m["kind"] == "clip":
            d = max(0.5, m.get("dur") or 1.0)
            for k, at in enumerate((0.15, 0.5, 0.85)):
                fp = os.path.join(workdir, "_cs%d_%d.jpg" % (i, k))
                try:
                    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                                    "-ss", "%.2f" % (d * at), "-i", m["src"],
                                    "-frames:v", "1", "-vf", "scale=%d:%d:force_original_aspect_ratio=decrease" % (tw, th),
                                    fp], check=True, timeout=60)
                    frames.append(fp)
                except Exception:
                    pass
        else:
            frames.append(m["src"])
        rows.append((i, frames))
    img = Image.new("RGB", (60 + 3 * tw, th * max(1, len(rows))), (20, 20, 20))
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
    except Exception:
        font = ImageFont.load_default()
    for r, (i, frames) in enumerate(rows):
        dr.text((10, r * th + th // 2 - 20), str(i), fill=(255, 220, 0), font=font)
        for c, fp in enumerate(frames[:3]):
            try:
                t = Image.open(fp).convert("RGB")
                t.thumbnail((tw, th))
                img.paste(t, (60 + c * tw, r * th))
            except Exception:
                pass
    path = os.path.join(workdir, out_name)
    img.save(path, quality=85)
    for f in os.listdir(workdir):
        if f.startswith("_cs"):
            try:
                os.remove(os.path.join(workdir, f))
            except Exception:
                pass
    return path


def ask_match(shots, media, sheet_path):
    lines = ["FILES:"]
    for i, m in enumerate(media, start=1):
        lines.append("%d. %s (%s%s)" % (
            i, {"ghatna": "ghatna/jagah ki video", "bayan": "bayan wali video",
                "photo": "photo"}.get(m["role"], m["role"]),
            m["kind"], (", %.0f sec" % m["dur"]) if m.get("dur") else ""))
    lines += ["", "SCRIPT KI BAATEIN:"]
    for i, sh in enumerate(shots, start=1):
        lines.append("%d. %s" % (i, sh.get("text")))
    return sy_ai.ask_vision_json(MATCH_SYSTEM, "\n".join(lines), sheet_path,
                                 max_tokens=700)


def assign(shots, media, answer=None):
    """{shot index: media index} (0 se). Claude ka jawab ho to wahi, warna
    (ya kami ho to) kram se. Reporter ki koi bhi achhi file bina chale nahi
    rehni chahiye - wo stock se hamesha behtar hai."""
    n_s, n_m = len(shots), len(media)
    bad = set()
    out = {}
    if isinstance(answer, dict):
        for b in answer.get("bekaar") or []:
            try:
                bad.add(int(b) - 1)
            except Exception:
                pass
        for a in answer.get("assign") or []:
            try:
                s, f = int(a.get("shot")) - 1, int(a.get("file")) - 1
            except Exception:
                continue
            if 0 <= s < n_s and 0 <= f < n_m and f not in bad and s not in out:
                out[s] = f
    good = [i for i in range(n_m) if i not in bad]
    # Jo achhi file kahin nahi lagi, wo pehle khaali tukde par.
    unused = [i for i in good if i not in out.values()]
    free = [s for s in range(n_s) if s not in out]
    # Jawab hi na mila ho to pehla tukda jagah ki video se (bayan wali nahi).
    if not isinstance(answer, dict):
        unused.sort(key=lambda i: (media[i]["role"] == "bayan", i))
    for s in free:
        if not unused:
            break
        out[s] = unused.pop(0)
    return out


def _pieces(assigned, media):
    """Ek hi file kai tukdon par ho to har tukde ko uska alag hissa.
    {shot: (start, dur)}."""
    by_file = {}
    for s in sorted(assigned):
        by_file.setdefault(assigned[s], []).append(s)
    out = {}
    for f, ss in by_file.items():
        m = media[f]
        if m["kind"] != "clip":
            for s in ss:
                out[s] = (0.0, 0.0)
            continue
        d = max(1.0, float(m.get("dur") or 1.0))
        each = d / len(ss)
        for k, s in enumerate(ss):
            out[s] = (k * each, min(PIECE_MAX, max(1.0, each)))
    return out


def _fallback_shots(script, place):
    """Picture editor shot list na de paye (chhoti script) - vaakyon se tukde."""
    parts = [p for p in re.split(r"(?<=[।\.\?!])\s+", script) if p.strip()]
    if not parts:
        return []
    n = max(1, min(4, len(parts)))
    size = -(-len(parts) // n)
    shots = []
    for k in range(0, len(parts), size):
        shots.append({"text": " ".join(parts[k:k + size]), "type": "place",
                      "brief": "reporter ki video", "queries": [place or "Uttar Pradesh"]})
    return shots


def load(story):
    return st.kv_get("report_" + str(story.get("story_id"))) or {}


def download_media(rec, rawdir):
    """Form ki saari file Drive se. [{src, kind, role, dur, w, h, audio}]"""
    media = []
    for role, field in (("ghatna", "ghatna_video"), ("bayan", "bayan_video"),
                        ("photo", "photo")):
        # Bayan dene wale ki ijaazat na ho to unki video kahin nahi - na
        # aawaaz ke saath, na chup b-roll mein.
        if role == "bayan" and not yes(rec.get("ijazat")):
            continue
        for fid in drive_ids(rec.get(field)):
            if len(media) >= MAX_MEDIA:
                break
            try:
                path, name, mime = drive_download(fid, rawdir)
            except Exception as e:
                log("file nahi utri (%s): %s" % (fid[:8], str(e)[:200]))
                continue
            vid = is_video(path, mime)
            dur, w, h, audio = _probe(path) if vid else (0.0, 0, 0, False)
            if vid and dur < 0.8:
                log("video khaali/khandit:", name)
                continue
            media.append({"src": path, "name": name, "role": role,
                          "kind": "clip" if vid else "photo",
                          "dur": dur, "w": w, "h": h, "audio": audio})
            log("  utri: %s (%s, %s)" % (name, role, "%.0fs" % dur if vid else "photo"))
    return media


def prepare_shots(story, workdir):
    """Reporter ki files ko shot list mein bhar do (produce() fetch_shots se
    pehle bulata hai). story["shots"] badalta hai. Kitne tukde bhare, wo
    lautata hai. Bayan wali video (asli aawaaz) ki taiyari bhi yahin."""
    import sy_media
    info = load(story)
    rec = info.get("rec") or {}
    faces = yes(rec.get("chehra"))
    rawdir = os.path.join(workdir, "rep")
    media = download_media(rec, rawdir)
    story["_report_faces"] = faces
    story["_report_media"] = len(media)

    # Bayan ki video asli aawaaz ke saath alag se judegi (sy_report.insert_bayan)
    # - use b-roll mein bhi chala dena ek hi chehra do baar dikhana hai.
    bayan = None
    if info.get("bayan_intro"):
        bayan = next((m for m in media if m["role"] == "bayan" and m.get("audio")), None)
        if bayan:
            try:
                story["_bayan_seg"] = build_bayan_segment(bayan, info, workdir, faces)
            except Exception as e:
                log("bayan wala hissa nahi bana (b-roll mein chalega):", str(e)[:200])
            if not story.get("_bayan_seg"):
                bayan = None
    broll = [m for m in media if m is not bayan]

    try:
        shots = json.loads(story.get("shots") or "[]")
    except Exception:
        shots = []
    for sh in shots:
        for k in ("reporter", "file", "kind", "credit", "source"):
            sh.pop(k, None)
    if not shots:
        shots = _fallback_shots(str(story.get("script_hi") or ""),
                                info.get("place_en") or "")
    if not shots or not broll:
        story["shots"] = json.dumps(shots, ensure_ascii=False)
        return 0

    answer = None
    try:
        sheet = contact_sheet(broll, workdir)
        answer = ask_match(shots, broll, sheet)
        if answer:
            log("clip milaan:", str(answer.get("note") or "")[:120])
    except Exception as e:
        log("clip milaan (vision) nahi hua - kram se:", str(e)[:160])
    amap = assign(shots, broll, answer)
    parts = _pieces(amap, broll)
    filled = 0
    for s, f in sorted(amap.items()):
        m = broll[f]
        sh = shots[s]
        try:
            if m["kind"] == "clip":
                name = "rshot%d.mp4" % s
                start, dur = parts[s]
                normalize_clip(m["src"], os.path.join(workdir, name), start, dur, faces)
            else:
                name = "rshot%d.jpg" % s
                normalize_photo(m["src"], os.path.join(workdir, name), faces)
        except Exception as e:
            log("  %d: reporter ki file taiyar nahi hui: %s" % (s + 1, str(e)[:160]))
            continue
        sh.update({"reporter": True, "file": name, "kind": m["kind"],
                   "credit": CREDIT, "source": "reporter"})
        filled += 1
        log("  %d. reporter ki %s <- %s" % (s + 1, m["role"], m["name"]))
    # Jagah ki khoj (bache tukdon ke liye) - khabar ki apni jagah.
    place = info.get("place_en") or ""
    if place:
        for sh in shots:
            if not sh.get("reporter") and place not in (sh.get("queries") or []):
                sh["queries"] = (sh.get("queries") or [])[:2] + [place]
    story["shots"] = json.dumps(shots, ensure_ascii=False)
    log("%d/%d tukdon par reporter ki file" % (filled, len(shots)))
    return filled


def approval_note(story):
    """Telegram ke approval sandesh mein - reporter aur chehre ki chetavni."""
    rec = load(story).get("rec") or {}
    bits = ["Reporter: %s, %s" % (rec.get("naam") or "?", rec.get("mobile") or "")]
    if story.get("_report_faces"):
        bits.append("CHEHRA CHHUPANA = HAAN: chehre apne aap dhundhle kiye "
                    "(pakka nahi) - approve se pehle dhyan se dekhiye")
    info = load(story)
    if drive_ids(rec.get("bayan_video")) and not yes(rec.get("ijazat")):
        bits.append("bayan ki video ijaazat ke bina thi - nahi lagayi")
    elif info.get("bayan_intro") and not story.get("_bayan_seg"):
        bits.append("bayan ki video nahi ban paayi")
    return " | ".join(bits)


def cleanup(workdir):
    """Reporter ki badi files render ke baad hata do - warna har run ke
    media cache (cloud/state.sh) mein sau-sau MB chadhte."""
    freed = 0
    try:
        for f in os.listdir(workdir):
            p = os.path.join(workdir, f)
            big = (f == "rep" or f.startswith("rshot") or f.startswith("bayan")
                   or f.startswith("seg") or f in ("clip.mp4", "rep_sheet.jpg",
                                                      "with_endcard.mp4", "endcard.mp4"))
            if not big:
                continue
            if os.path.isdir(p):
                for root, _d, fs in os.walk(p):
                    freed += sum(os.path.getsize(os.path.join(root, x)) for x in fs)
                shutil.rmtree(p, ignore_errors=True)
            else:
                freed += os.path.getsize(p)
                os.remove(p)
    except Exception as e:
        log("safai mein gadbad:", e)
    if freed > 1 << 20:
        log("reporter ki files hatayi (%.0f MB)" % (freed / 1048576.0))


# --------------------------------------------- bayan - asli aawaaz ke saath
#
# Reporter ki "bayan wali video" b-roll nahi hai - usme kisi adhikari/vyakti
# ki apni aawaaz hai, aur wahi sabse sacchi cheez hai jo hum dikha sakte
# hain. Isliye wo apni aawaaz ke saath chalti hai:
#
#   script: "... इस बारे में थाना प्रभारी रमेश कुमार ने क्या कहा, सुनिए।"
#   -> anchor ki aawaaz yahin rukti hai, bayan ki video (unki aawaaz,
#      neeche naam-pad ki patti) chalti hai -> phir anchor aage padhta hai.
#
# Sirf tab jab form mein ijaazat wala dabba tick ho (bayan_video_ok), aur
# sampadak ne bayan_intro vaakya diya ho. Kuch bhi gadbad ho to video bina
# bayan ke hi aage jaati hai - bayan kabhi poori video ko nahi girata.

def bayan_max_seconds():
    return max(5, cfg.num("report", "bayan_max_seconds", 45))


def _silences(path, noise=-34, dur=0.15):
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
             "-af", "silencedetect=noise=%ddB:d=%.2f" % (noise, dur),
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=300)
    except Exception:
        return []
    txt = out.stderr or ""
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", txt)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([\d.]+)", txt)]
    return list(zip(starts, ends))


def bayan_end(dur, silences, cap):
    """Bayan kahan tak chale: poora, ya cap se pehle ki aakhri chuppi par
    (vaakya beech mein na kate). Chuppi na mile to cap par."""
    if dur <= cap + 0.5:
        return dur
    best = None
    for s0, _e in silences:
        if cap * 0.6 <= s0 <= cap:
            best = s0
    return round((best + 0.15) if best else cap, 2)


def _ass_time(t):
    t = max(0.0, t)
    return "%d:%02d:%05.2f" % (int(t // 3600), int(t % 3600 // 60), t % 60)


def _ass_esc(t):
    return str(t or "").replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def lower_third_ass(name, pad, dur, path):
    """Naam-pad ki patti - pehle 7 second (ya bayan chhota ho to poore)."""
    end = min(dur, 7.0)
    lines = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: %d" % W, "PlayResY: %d" % H, "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        # Laal patti par safed naam, neeche kaali patti par pad.
        "Style: N,Noto Sans Devanagari,54,&H00FFFFFF,&H00FFFFFF,&H001A1AB4,"
        "&H001A1AB4,1,0,0,0,100,100,0,0,3,14,0,1,90,90,190,1",
        "Style: P,Noto Sans Devanagari,38,&H00FFFFFF,&H00FFFFFF,&H00141414,"
        "&H00141414,0,0,0,0,100,100,0,0,3,12,0,1,90,90,110,1",
        "Style: T,Noto Sans Devanagari,30,&H00FFFFFF,&H00FFFFFF,&H001A1AB4,"
        "&H001A1AB4,1,0,0,0,100,100,0,0,3,8,0,7,60,60,50,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        # Poore bayan par chhota "बयान" nishan - darshak jaane ye asli aawaaz hai.
        "Dialogue: 0,%s,%s,T,,0,0,0,,बयान" % (_ass_time(0), _ass_time(dur)),
    ]
    if name:
        lines.append("Dialogue: 1,%s,%s,N,,0,0,0,,{\\fad(250,250)}%s"
                     % (_ass_time(0.3), _ass_time(end), _ass_esc(name)[:60]))
    if pad:
        lines.append("Dialogue: 1,%s,%s,P,,0,0,0,,{\\fad(250,250)}%s"
                     % (_ass_time(0.3), _ass_time(end), _ass_esc(pad)[:80]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _split_bayan_kaun(text):
    """Form ka "सुरेश कुमार, थाना प्रभारी" -> (naam, pad)."""
    parts = [p.strip() for p in re.split(r"[,،\-–—(]", str(text or ""), maxsplit=1)]
    name = parts[0] if parts else ""
    pad = parts[1].rstrip(")").strip() if len(parts) > 1 else ""
    return name, pad


def build_bayan_segment(m, info, workdir, faces):
    """workdir/bayan_seg.mp4 - 1920x1080, asli aawaaz (barabar kiya hua),
    naam-pad ki patti. Path, ya "" agar nahi bani."""
    rec = info.get("rec") or {}
    name = info.get("bayan_name") or ""
    pad = info.get("bayan_pad") or ""
    if not name:
        name, pad2 = _split_bayan_kaun(rec.get("bayan_kaun"))
        pad = pad or pad2
    src = m["src"]
    dur = bayan_end(float(m.get("dur") or 0), _silences(src, -30, 0.35),
                    bayan_max_seconds())
    if dur < 2.0:
        return ""
    a = os.path.join(workdir, "bayan_a.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-t", "%.3f" % dur, "-i", src,
         "-filter_complex", "[0:v]" + fill_filter() + ",fps=%d[v]" % FPS,
         "-map", "[v]", "-map", "0:a:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", a],
        check=True, timeout=900)
    if faces:
        b = os.path.join(workdir, "bayan_b.mp4")
        blur_faces_video(a, b, audio_from=a)
        a = b
    ass = lower_third_ass(name, pad, dur, os.path.join(workdir, "bayan.ass"))
    out = os.path.join(workdir, "bayan_seg.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", a,
         "-vf", "ass=%s,format=yuv420p" % os.path.basename(ass),
         # Phone ki aawaaz aksar dheemi/oonchi hoti hai - anchor ke barabar.
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,"
                "afade=t=in:st=0:d=0.12,afade=t=out:st=%.2f:d=0.2" % max(0.0, dur - 0.2),
         "-t", "%.3f" % dur,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", out],
        cwd=workdir, check=True, timeout=900)
    got = _probe(out)
    if got[0] < 1.5 or not got[3]:
        return ""
    log("bayan taiyar: %.1fs (%s%s)" % (got[0], name or "naam nahi",
                                       ", chehre dhundhle" if faces else ""))
    return out


def insert_point(timing, intro, lead, silences=(), total=0.0):
    """Main video mein bayan kis second par judega.

    bayan_intro vaakya script mein dhoondho, uske ANT ka samay aawaaz ki
    timing se nikaalo, aur paas ki chuppi par bitha do (taaki anchor ka
    shabd beech mein na kate). Vaakya na mile to poori script ke baad."""
    import sy_scenes
    text = (timing or {}).get("text") or ""
    spans = (timing or {}).get("spans") or []
    if not spans:
        return None
    voice_end = spans[-1][3]
    t = None
    i = sy_scenes.find_char(text, intro) if intro else -1
    if i >= 0:
        # find_char spacing saaf karke dhoondhta hai - ant bhi usi hisaab se.
        n = len(re.sub(r"\s+", " ", intro.strip()))
        t = sy_scenes.at_char(i + n, timing, 0.0, voice_end)
    if t is None:
        t = voice_end
    # Paas ki chuppi (1.5 second ke andar) - uski shuruaat se thoda aage.
    best = None
    for s0, e0 in silences or ():
        if abs(s0 - t) <= 1.5 and (best is None or abs(s0 - t) < abs(best - t)):
            best = s0
    if best is not None:
        t = best + 0.12
    t = lead + max(0.5, min(t, voice_end + 0.2))
    if total:
        t = min(t, total - 0.5)
    return round(t, 3)


def insert_bayan(story, video_path, workdir, timing, lead):
    """Bani hui video mein bayan jodo. Nayi video ka path (ya purana hi)."""
    seg = story.get("_bayan_seg")
    if not seg or not os.path.exists(seg):
        return video_path
    import sy_endcard
    info = load(story)
    total = _probe(video_path)[0]
    voice = os.path.join(workdir, "voice.wav")
    sil = _silences(voice) if os.path.exists(voice) else []
    at = insert_point(timing, info.get("bayan_intro") or "", lead, sil, total)
    if at is None:
        log("aawaaz ki timing nahi - bayan nahi juda")
        story["_bayan_seg"] = ""
        story["visual_line"] = str(story.get("visual_line") or "") + " | bayan nahi juda"
        return video_path
    W_, H_, rate, ch = sy_endcard._probe(video_path)
    layout = "stereo" if ch >= 2 else "mono"
    seg_len = _probe(seg)[0]
    fx = ";".join([
        "[0:v]trim=0:%.3f,setpts=PTS-STARTPTS,setsar=1,fps=%d,format=yuv420p[v0]" % (at, FPS),
        "[0:a]atrim=0:%.3f,asetpts=PTS-STARTPTS,afade=t=out:st=%.3f:d=0.08[a0]"
        % (at, max(0.0, at - 0.08)),
        "[1:v]scale=%d:%d,setsar=1,fps=%d,format=yuv420p[v1]" % (W_, H_, FPS),
        "[1:a]aresample=%d,aformat=sample_rates=%d:channel_layouts=%s[a1]" % (rate, rate, layout),
        "[0:v]trim=start=%.3f,setpts=PTS-STARTPTS,setsar=1,fps=%d,format=yuv420p[v2]" % (at, FPS),
        "[0:a]atrim=start=%.3f,asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.08[a2]" % at,
        "[a0]aformat=sample_rates=%d:channel_layouts=%s[a0f]" % (rate, layout),
        "[a2]aformat=sample_rates=%d:channel_layouts=%s[a2f]" % (rate, layout),
        "[v0][a0f][v1][a1][v2][a2f]concat=n=3:v=1:a=1[v][a]",
    ])
    out = os.path.join(workdir, "with_bayan.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", video_path, "-i", seg, "-filter_complex", fx,
         "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "21",
         "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", "-ar", str(rate), "-ac", str(ch),
         "-movflags", "+faststart", out],
        cwd=workdir, check=True, timeout=1800)
    got = _probe(out)[0]
    if abs(got - (total + seg_len)) > 1.2:
        log("bayan ke saath lambai galat (%.1f, chahiye %.1f) - bina bayan"
            % (got, total + seg_len))
        story["_bayan_seg"] = ""
        story["visual_line"] = str(story.get("visual_line") or "") + " | bayan nahi juda"
        return video_path
    shutil.move(out, video_path)
    log("bayan %.1fs par juda (%.1fs)" % (at, seg_len))
    story["visual_line"] = (str(story.get("visual_line") or "")
                            + " | bayan (asli aawaaz) %d:%02d par, %.0fs"
                            % (int(at) // 60, int(at) % 60, seg_len))
    return video_path

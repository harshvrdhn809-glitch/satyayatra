"""LAMBI VIDEO - ek mudde ki A se Z jaankari, 8-10 minute.

YE KYA HAI (Sep 2026, Harshvardhan ka faisla)
=============================================
Chhoti video (60-90 second) ek khabar ek lekh se banti hai. Ye usse alag
rasta hai: EK DIN CHHOD KAR ek lambi video, us mudde par jo us waqt poore
Bharat mein charcha mein hai - Google par khoja ja raha hai, YouTube par
dekha ja raha hai, X (Twitter) par bola ja raha hai, aur akhbaaron mein
chhapa ja raha hai.

  1. MUDDA     Google Trends + YouTube trending + X trends (trends24.in) +
               GDELT (kitne akhbaar likh rahe hain). Jo 2+ jagah upar ho
               wo pehle. Claude aakhri suchi banata hai, Telegram par 2-3
               vikalp jaate hain; jawab na aaye to sabse upar wala.
  2. SCRIPT    Ek lekh nahi - 6-10 alag akhbaar + Wikipedia ki prishthbhoomi.
               Claude apni ORIGINAL script likhta hai, tay dhanche mein
               (hook, poori kahani, shuruaat/timeline, kaun-kaun, dono
               paksh, aankde, asar, aage kya). Tathya sirf srot se; srot
               takrayein to "daawa" ki tarah. Phir ek alag jaanch-call har
               vaakya ko srot se milati hai.
  3. DRISHYA   Pehle asli tasveer/footage (wahi sy_media.fetch_shots rasta,
               40-60 tukde). Jahan asli na mile wahan Veo se PRATEEKATMAK
               2D CARTOON - screen par "AI चित्रण" ke saath.
  4. RENDER    Aawaaz, drishya, render, end-card, thumbnail, YouTube
               chapters (script ke hisson se).
  5. APPROVAL  Telegram par chhoti jhalak (480p, 50 MB se kam) + thumbnail
               + chapters. Approve ke baad POORI video YouTube par (wahi
               sy_main.tick_upload).

KAAM KAI RUN MEIN BANTA HAI
===========================
GitHub Actions ki ek run ~15 minute ki hai. Lambi video ka poora kaam
(40-60 drishya dhoondhna, darjan-bhar Veo clip, 10 minute ka render) ek
run mein nahi samata. Isliye har kadam ek "stage" hai aur uski haalat
database (kv "lv_job" + stories table) mein rehti hai. Har run apne hisse
ka kaam (work_minutes tak) karke rukti hai; agli run wahin se uthati hai.
Kachcha saamaan work/<id>/ mein rehta hai, jo cloud/state.sh ki media
potli mein run se run tak jaata hai - render ke baad turant saaf.

CHHOTI VIDEO SE ALAG
====================
- beat "long", id "lv_...". Status bhi apne: lv_work (ban rahi hai),
  lv_awaiting (jhalak Telegram par), lv_failed. Isliye tick_produce,
  tick_offer, revive_failed, "producing" wali safai - koi ise nahi
  chhoota, aur ye chhoti video ki "ek waqt ek approval" wali rok mein
  nahi phansti. Approve hote hi aam "approved" - upload wahi purana.
- Din ki 4 wali ginti (max_uploads_per_day) mein ye bhi ginti hai -
  sy_main.in_flight_count() lv_work/lv_awaiting ko jodta hai.
- Veo: chhoti video ke niyam (ALLOWED_BEATS, din ki seema, "koi chehra
  nahi") BILKUL nahi badle. Yahan apna rasta hai: koi din ki seema nahi,
  sirf jahan asli na mile; cartoon mein prateekatmak insaani kirdaar chal
  sakte hain (Harshvardhan ka faisla), par kisi ASLI vyakti ki shakl kabhi
  nahi, aur photoreal kabhi nahi. Ek video par ek pakki chhat
  (veo_max_per_video) sirf kisi keede se bachne ke liye.

Chalana: sy_main.one_round() har chakkar mein tick() bulata hai.
Telegram: /lambi (haal), /lambi abhi, /lambi on|off, /lambi radd.
"""
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import time

import sy_config as cfg
import sy_net
import sy_store as st

BEAT = "long"
PREFIX = "lv_"
JOB_KEY = "lv_job"
LAST_DAY_KEY = "lv_last_day"
FORCE_KEY = "lv_force"
RETRY_KEY = "lv_retry_after"

# Apne status - chhoti video ke kisi raste mein nahi aate (upar dekhiye).
WORK = "lv_work"
WAIT = "lv_awaiting"
FAIL = "lv_failed"

# Telegram ke button. lk/lx = vishay chuna / aaj nahi. la/lr = jhalak par
# approve / reject.
VERDICTS = ("lk", "lx", "la", "lr")

# Script ka dhancha. Kram yahi rehta hai; kisi hisse ka material srot mein
# na ho to wo hissa chhota ya gayab ho sakta hai - bharne ke liye kuch
# gadha nahi jaata.
SECTIONS = [
    ("hook", "शुरुआत"),
    ("kahani", "पूरी कहानी"),
    ("shuruaat", "कैसे शुरू हुआ"),
    ("kaun", "कौन-कौन"),
    ("paksh", "दोनों पक्ष"),
    ("aankde", "आंकड़े"),
    ("asar", "असर"),
    ("aage", "आगे क्या"),
]
SECTION_KEYS = [k for k, _ in SECTIONS]

# Hindi ~13 akshar prati second boli jaati hai (sy_tts.CPS, naapa hua).
# 8 minute = ~6,200, 10 minute = ~7,800.
CHARS_WANT = (6500, 8000)
CHARS_MIN = 5000          # isse chhoti = 6.5 minute se kam - dobara likhwao
CHARS_FLOOR = 4200        # dobara bhi itni se chhoti = chhod do

# Ek tukda ~9 second (≈120 akshar). 8 second ki Veo clip lagbhag poora
# tukda dhak leti hai - clip dohrayi nahi jaati (sy_scenes.build).
CHARS_PER_SHOT = 120
SHOTS_MIN, SHOTS_MAX = 40, 60

AI_CREDIT = "AI चित्रण (प्रतीकात्मक) · सत्ययात्रा न्यूज"


def log(*a):
    print("[lambi]", *a, flush=True)


# ------------------------------------------------------------ settings

def enabled():
    """Telegram ka /lambi on|off config se upar - /veo jaisa hi."""
    v = st.kv_get("long_on")
    if v is not None:
        return bool(v)
    return cfg.num("long", "enabled", 0) == 1


def every_days():
    return max(1, int(cfg.num("long", "every_days", 2)))


def start_hour():
    return int(cfg.num("long", "start_hour", 7))


def work_minutes():
    return max(5.0, cfg.num("long", "work_minutes", 25))


def choice_wait_minutes():
    return cfg.num("long", "choice_wait_minutes", 60)


def approval_wait_hours():
    return cfg.num("long", "approval_wait_hours", 24)


def min_sources():
    return max(2, int(cfg.num("long", "min_sources", 4)))


def max_sources():
    return max(min_sources(), int(cfg.num("long", "max_sources", 10)))


def veo_max_per_video():
    return int(cfg.num("long", "veo_max_per_video", 40))


def veo_seconds():
    n = cfg.num("long", "veo_seconds", 8)
    return min((4, 6, 8), key=lambda v: abs(v - n))


def preview_mb():
    # Telegram bot 50 MB se badi file nahi bhej sakta - thodi jagah chhod kar.
    return min(48.0, cfg.num("long", "preview_mb", 45))


def veo_on():
    """Lambi video par cartoon chitran chalega?

    Apna switch ([long] veo) - chhoti video wala [veo] enabled isse alag
    hai. Par agar aapne Telegram par /veo off dabaya hai to wo "paisa roko"
    ka button hai - wo yahan bhi maana jaata hai.
    """
    if cfg.num("long", "veo", 1) != 1:
        return False
    if st.kv_get("veo_on") == 0:
        return False
    try:
        import sy_veo
        return bool(sy_veo.sa_path())
    except Exception:
        return False


def _today():
    return time.strftime("%Y-%m-%d")


def _days_since(day):
    try:
        d = datetime.date.fromisoformat(str(day))
    except Exception:
        return 999
    return (datetime.date.today() - d).days


def _yesterday():
    return (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


# ----------------------------------------------------------- mudda chunna
#
# Chaar jagah se: Google (khoj), YouTube (dekha ja raha), X (bola ja raha)
# aur GDELT (kitne akhbaar likh rahe). Facebook ka koi sarvajanik trend
# data nahi hai - wo jaan-boojhkar nahi hai.

X_TRENDS_URL = "https://trends24.in/india/"


def _split_tag(t):
    """#BiharElection2025 -> "Bihar Election 2025". Devanagari waisa hi."""
    t = str(t or "").strip().lstrip("#").replace("_", " ")
    if re.search(r"[ऀ-ॿ]", t):
        return re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", t)
    t = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_x_trends(html, limit=30):
    """trends24.in ke safhe se X ke trend. Pehla card = sabse taaza ghanta.

    Site ki shakl badal jaye to bas khaali suchi - baaki srot chalte rahenge.
    """
    html = str(html or "")
    out = []
    cards = re.findall(r'<ol[^>]*class="[^"]*trend-card__list[^"]*"[^>]*>(.*?)</ol>',
                       html, re.S)
    blob = "".join(cards[:2]) if cards else html
    found = re.findall(
        r'<a[^>]+href="https?://(?:www\.)?(?:twitter|x)\.com/search\?q=[^"]*"[^>]*>(.*?)</a>',
        blob, re.S)
    if not found:
        # Link ki shakl badli ho to bhi trend ka naam "trend-link" class mein.
        found = re.findall(r'<a[^>]*class="[^"]*trend-link[^"]*"[^>]*>(.*?)</a>', blob, re.S)
    for raw in found:
        term = _split_tag(re.sub(r"<[^>]+>", "", raw))
        term = (term.replace("&amp;", "&").replace("&#39;", "'")
                .replace("&quot;", '"').strip())
        if len(term) < 3 or term.lower() in (x.lower() for x in out):
            continue
        out.append(term)
        if len(out) >= limit:
            break
    return out


def x_trends(limit=30):
    """X (Twitter) par Bharat mein abhi kya chal raha hai. Kabhi girta nahi."""
    try:
        html = sy_net.get_text(X_TRENDS_URL, timeout=30)
    except Exception as e:
        log("X trends nahi khule (chhod rahe hain):", str(e)[:100])
        return []
    out = parse_x_trends(html, limit)
    log("X se %d trend" % len(out))
    return out


def gather():
    """Har srot ki suchi. {"google": [..], "youtube": [..], "x": [..]}."""
    import sy_trend
    got = {"google": [], "youtube": [], "x": []}
    links = {}
    try:
        for t in sy_trend.google_trends(limit=25):
            got["google"].append(t["term"])
            links[t["term"]] = t.get("links") or []
    except Exception as e:
        log("Google Trends:", e)
    try:
        got["youtube"] = [t["term"] for t in sy_trend.youtube_trending(limit=30, kind="news")]
    except Exception as e:
        log("YouTube trending:", e)
    try:
        got["x"] = x_trends()
    except Exception as e:
        log("X trends:", e)
    for k in got:
        got[k] = [t for t in got[k] if not sy_trend.TREND_BLOCK.search(t)]
    return got, links


_TOK_STOP = set("""this that with from have will what when your about after
their there were been into over news live today latest video videos hindi
update updates breaking full match india indian bharat official trailer
episode watch says said khabar samachar""".split())


def _tokens(s):
    words = re.findall(r"[a-z0-9]+|[ऀ-ॿ]+", str(s or "").lower())
    return set(w for w in words if len(w) >= 4 and w not in _TOK_STOP)


def merge_signals(got):
    """Seedha shabd-milaan: kaun sa vishay kitni jagah hai. Claude ke liye
    ishaara, aur Claude na chale to yahi suchi.

    [{"term", "signals": [..]}], sabse zyada jagah wale pehle.
    """
    rows = []
    for src in ("google", "x", "youtube"):
        for term in got.get(src) or []:
            tk = _tokens(term)
            key = re.sub(r"[^a-z0-9ऀ-ॿ]+", "", term.lower())
            hit = None
            for r in rows:
                common = tk & r["_tk"]
                if (key and (key in r["_key"] or r["_key"] in key) and min(len(key), len(r["_key"])) >= 5) \
                        or len(common) >= 2 or any(len(w) >= 6 for w in common):
                    hit = r
                    break
            if hit:
                if src not in hit["signals"]:
                    hit["signals"].append(src)
                hit["_tk"] |= tk
                continue
            rows.append({"term": term, "signals": [src], "_tk": set(tk), "_key": key})
    rows.sort(key=lambda r: -len(r["signals"]))
    for r in rows:
        r.pop("_tk", None)
        r.pop("_key", None)
    return rows


TOPIC_SYSTEM = "\n".join([
    "Aap ek Hindi news channel ke sampadak hain. Channel ek din chhod kar "
    "ek LAMBI (8-10 minute) video banata hai - us mudde ki A se Z jaankari "
    "jo us waqt poore Bharat mein charcha mein hai.",
    "",
    "Aapko teen suchiyan di jayengi: Google Trends (log kya KHOJ rahe hain), "
    "YouTube (kya DEKHA ja raha hai), X/Twitter (kya BOLA ja raha hai). "
    "Ek hi mudda alag suchiyon mein alag shabdon mein ho sakta hai - use "
    "ek hi mudda maaniye.",
    "",
    "Chuniye 5 tak MUDDE (kram se, sabse achha pehle):",
    "- Jo 2 ya zyada suchiyon mein ho use tarjeeh.",
    "- Bharat ke darshak ke liye ho (Bharat ki khabar, ya videshi baat jo "
    "Bharat ko chhooti ho).",
    "- Usme 8-10 minute layak GEHRAI ho: ek kahani, uska itihaas, log, "
    "paksh, asar. Sirf ek score, result link, trailer ya ek post wala "
    "vishay nahi.",
    "- Afwaah par tika vishay nahi.",
    "",
    "Sirf ek JSON object, aur kuch nahi:",
    '{"mudde": [{"mudda_hi": "mudde ka chhota Hindi naam (Devanagari, 40 '
    'akshar tak)", "query_en": "angrezi news search query, 3-6 shabd", '
    '"wiki_en": "prishthbhoomi ke liye sabse theek English Wikipedia lekh ka '
    'naam, na ho to khaali", "signals": ["google", "youtube", "x"], '
    '"kyun": "ek line"}]}',
])


def _ai_topics(got, mech):
    import sy_ai
    parts = []
    for src, name in (("google", "GOOGLE TRENDS"), ("youtube", "YOUTUBE"), ("x", "X / TWITTER")):
        parts.append(name + ":")
        parts += ["- " + t for t in (got.get(src) or [])[:30]] or ["(khaali)"]
        parts.append("")
    both = [r for r in mech if len(r["signals"]) >= 2][:12]
    if both:
        parts.append("SHABD-MILAAN SE 2+ JAGAH (sirf ishaara, galat bhi ho sakta hai):")
        parts += ["- %s  [%s]" % (r["term"], ", ".join(r["signals"])) for r in both]
    try:
        j = sy_ai.ask_json(TOPIC_SYSTEM, "\n".join(parts), max_tokens=1500)
    except Exception as e:
        log("mudde ki parakh nahi hui:", e)
        return []
    out = []
    for it in ((j or {}).get("mudde") or [])[:6]:
        if not isinstance(it, dict):
            continue
        q = re.sub(r"\s+", " ", str(it.get("query_en") or "")).strip()[:80]
        hi = re.sub(r"\s+", " ", str(it.get("mudda_hi") or "")).strip()[:60]
        if len(q) < 4:
            continue
        sig = [s for s in (it.get("signals") or []) if s in ("google", "youtube", "x")]
        out.append({"mudda_hi": hi or q, "query_en": q,
                    "wiki_en": str(it.get("wiki_en") or "").strip()[:100],
                    "signals": sorted(set(sig)), "kyun": str(it.get("kyun") or "")[:140]})
    return out


def _topic_key(t):
    return re.sub(r"[^a-z0-9]+", "", str(t or "").lower())[:40]


def news_volume(query):
    """GDELT: pichhle ek din mein is mudde par kitne ALAG akhbaar. (ginti, pate)"""
    import sy_trend
    try:
        urls = sy_trend._gdelt(query + " sourcecountry:india", timespan="1d", records=75)
    except Exception as e:
        log("GDELT:", e)
        urls = []
    seen, keep = set(), []
    for u in urls:
        h = sy_net.host(u)
        if h and h not in seen:
            seen.add(h)
            keep.append(u)
    return len(seen), keep[:20]


def rank_topics(cands):
    """Jitni zyada jagah, utna upar. Barabari par Claude ka kram."""
    return sorted(cands, key=lambda c: (-len(c.get("signals") or []), c.get("_i", 0)))


def pick_topics(want=3):
    """Telegram par bhejne layak 2-3 mudde. [] = aaj kuch nahi mila."""
    got, g_links = gather()
    if not any(got.values()):
        log("kisi srot se kuch nahi aaya")
        return []
    mech = merge_signals(got)
    cands = _ai_topics(got, mech)
    if not cands:
        # Claude nahi chala - shabd-milaan wali suchi hi sahi.
        cands = [{"mudda_hi": r["term"][:60], "query_en": r["term"][:80],
                  "wiki_en": "", "signals": r["signals"], "kyun": ""}
                 for r in mech[:6]]
    fresh = []
    for i, c in enumerate(cands):
        k = _topic_key(c["query_en"])
        if float(st.kv_get("lv_topic_" + k, 0) or 0) > time.time() - 10 * 86400:
            log("haal mein ban chuka - chhoda:", c["mudda_hi"])
            continue
        c["_i"] = i
        # Google ke apne lekh ke pate - srot mein kaam aayenge.
        for term, ls in g_links.items():
            if _tokens(term) & _tokens(c["query_en"]):
                c.setdefault("links", [])
                c["links"] += [u for u in ls if u not in c["links"]]
        fresh.append(c)
    fresh = fresh[:4]
    # Chauthi jagah - akhbaar. Sirf aakhri 4 par (GDELT har call ke beech
    # 20 second maangta hai).
    for c in fresh:
        n, urls = news_volume(c["query_en"])
        c["news"] = n
        c.setdefault("links", [])
        c["links"] += [u for u in urls if u not in c["links"]]
        if n >= 5 and "news" not in c["signals"]:
            c["signals"] = c["signals"] + ["news"]
    return rank_topics(fresh)[:want]


def _signal_text(c):
    names = {"google": "Google", "youtube": "YouTube", "x": "X", "news": "akhbaar"}
    s = " + ".join(names.get(x, x) for x in (c.get("signals") or []))
    if c.get("news"):
        s += " (%d akhbaar)" % c["news"]
    return s or "?"


# -------------------------------------------------------------- Telegram

def _tg():
    import sy_telegram
    return sy_telegram


def send_slate(slate, items):
    tg = _tg()
    lines = ["<b>LAMBI VIDEO (8-10 min) - kis mudde par?</b>", ""]
    rows = []
    for i, it in enumerate(items):
        lines.append("<b>%d.</b> %s\n   <i>%s</i>%s" % (
            i + 1, tg._esc(it["mudda_hi"]), tg._esc(_signal_text(it)),
            ("\n   " + tg._esc(it.get("kyun") or "")) if it.get("kyun") else ""))
        rows.append([{"text": "%d. %s" % (i + 1, it["mudda_hi"][:30]),
                      "callback_data": "lk:%s:%d" % (slate, i)}])
    lines += ["", "Jawab na aaye to %d minute baad pehla vishay khud chuna jayega."
              % int(choice_wait_minutes())]
    rows.append([{"text": "Aaj lambi video nahi", "callback_data": "lx:%s:0" % slate}])
    res = tg._post("sendMessage", {
        "chat_id": tg._chat(), "text": "\n".join(lines)[:4000], "parse_mode": "HTML",
        "reply_markup": json.dumps({"inline_keyboard": rows})}, timeout=60)
    return int(res.get("message_id") or 0)


def _progress(text):
    """Beech ke kadmon ki chhoti khabar - warna script se jhalak tak ghanton
    Telegram par kuch nahi aata aur pata nahi chalta kaam kahan hai."""
    _say("<b>Lambi video:</b> " + text)


def _say(text):
    try:
        _tg().send_message(text)
    except Exception as e:
        log("Telegram par nahi gaya:", e)


# ------------------------------------------------------------- srot + script

def _ask_long(system, user, max_tokens=16000, temperature=0.3):
    """sy_ai.ask jaisa, par lambe jawab ke liye lamba intezaar.

    8,000 akshar ki Hindi script ek lambi output hai - sy_ai.ask ka 240
    second ka intezaar uske liye kam pad sakta hai.
    """
    import sy_ai
    payload = {
        "model": cfg.get("anthropic", "model") or "claude-sonnet-4-6",
        "max_tokens": max_tokens, "temperature": temperature,
        "system": system, "messages": [{"role": "user", "content": user}],
    }
    try:
        data = sy_net.post_json(
            sy_ai.URL, payload,
            headers={"x-api-key": cfg.need("anthropic", "api_key"),
                     "anthropic-version": "2023-06-01"},
            timeout=600, retries=1)
    except Exception as e:
        sy_ai._raise_with_body(e)
    text = "".join(p.get("text") or "" for p in (data.get("content") or [])
                   if isinstance(p, dict) and p.get("type") == "text")
    if data.get("stop_reason") == "max_tokens":
        log("CHETAVNI: jawab max_tokens par kata")
    return sy_ai._extract_json(text)


def collect_sources(topic):
    """6-10 alag akhbaar ke lekh. [(host, url, text)]"""
    import sy_ingest
    import sy_trend
    q = topic["query_en"]
    links = list(topic.get("links") or [])
    try:
        links += sy_trend.search_links(q, limit=10)
    except Exception as e:
        log("khoj:", e)
    try:
        links += sy_trend._gdelt(q, timespan="7d", records=50)
    except Exception as e:
        log("GDELT 7d:", e)
    hosts = set(sy_net.host(u) for u in links if u)
    if len(hosts) < max_sources() + 4:
        try:
            links += sy_trend._bing_links(q)
        except Exception as e:
            log("Bing:", e)

    uniq, seen = [], set()
    for u in links:
        h = sy_net.host(u)
        if not h or h in seen:
            continue
        seen.add(h)
        uniq.append(u)
    uniq.sort(key=sy_ingest.link_rank)

    out = []
    for url in uniq[:20]:
        if len(out) >= max_sources():
            break
        if sy_ingest.link_rank(url) >= 3:
            continue
        try:
            text = sy_net.article_text(sy_net.get_text(url, timeout=40),
                                       min_chars=sy_ingest.MIN_ARTICLE)
        except Exception as e:
            log("  nahi khula:", sy_net.host(url), str(e)[:60])
            continue
        if text:
            out.append((sy_net.host(url).replace("www.", ""), url, text[:7000]))
            log("  srot %d: %s (%d akshar)" % (len(out), sy_net.host(url), len(text)))
    return out


def wiki_background(topic):
    import sy_ingest
    for t in (topic.get("wiki_en"), topic.get("query_en")):
        if not t:
            continue
        try:
            title, txt = sy_ingest._wiki_text(t)
        except Exception as e:
            log("Wikipedia:", e)
            continue
        if txt:
            log("  Wikipedia: %s (%d akshar)" % (title, len(txt)))
            return title, txt[:8000]
    return "", ""


LONG_SYSTEM = "\n".join([
    "Aap ek Hindi news channel ke senior explainer producer hain. Aapko ek "
    "mudde par 8-10 minute ki LAMBI video ki voiceover script likhni hai - "
    "darshak ko A se Z jaankari. Script ek AI aawaaz padhegi.",
    "",
    "PAKKE NIYAM - inka ullanghan matlab publishable false:",
    "1. Har tathya (naam, pad, ank, tareekh, jagah, bayan) SIRF diye gaye "
    "SROT se. Apni yaad se kuch nahi jodiye. Wikipedia sirf PRISHTHBHOOMI "
    "aur itihaas ke liye hai - aaj ki ghatna ke ank/bayan uske bharose nahi.",
    "2. Srot kisi baat par alag-alag kahein to kisi ek ko sach mat maaniye - "
    "dono ko DAAWE ki tarah rakhiye: \"कुछ रिपोर्टों में ... बताया गया है, "
    "जबकि कुछ में ...\". Aarop ko aarop hi kahiye (\"... का आरोप है\"), "
    "tathya nahi.",
    "3. Bayan hamesha us vyakti/sanstha ke naam se (\"गृह मंत्रालय के "
    "मुताबिक\"). Par AKHBAAR ka naam script mein kahin nahi - uska shreya "
    "YouTube description mein apne aap jaata hai.",
    "4. Koi rai, kayaas ya bhavishyavani nahi. \"आगे क्या\" mein sirf wahi "
    "jo srot mein tay/ghoshit hai (agli sunwai, tareekh, kisi ka kaha hua "
    "agla kadam).",
    "5. ORIGINAL likhiye - apne shabdon mein. Kisi srot ka vaakya jas ka tas "
    "nahi (kisi vyakti ka chhota, naam ke saath quote chalega).",
    "6. Srot mein thos jaankari itni hi nahi ki 8 minute ban sakein, ya "
    "mudda sirf afwaah par tika hai - to publishable false aur kill_reason.",
    "",
    "DHANCHA - inhi keys ke saath, isi kram mein hisse (sections):",
    "  hook     - 20-30 second. Sabse chaunkane wali SACCHI baat ya sawaal, "
    "aur ek line mein \"is video mein jaanenge...\". Namaskar ya "
    "like/subscribe nahi (wo video ke ant mein alag se aata hai).",
    "  kahani   - poori kahani saar mein: kya hua hai, abhi kya haal hai.",
    "  shuruaat - shuruaat aur timeline: kab kya hua, tareekhon ke saath.",
    "  kaun     - kaun-kaun shaamil hai - log, sansthayein, unki bhoomika.",
    "  paksh    - dono (ya sabhi) paksh: kaun kya keh raha hai, naam ke "
    "saath, santulit. Ek paksh ko zyada jagah nahi.",
    "  aankde   - srot ke ank, samjha kar (\"yaani har das mein se teen\").",
    "  asar     - aam aadmi, rajya, desh par asar - jitna srot kehte hain.",
    "  aage     - aage kya hoga (niyam 4), aur 2-3 line ka saaf saar.",
    "Kisi hisse ka material srot mein na ho to use chhota rakhiye ya chhod "
    "dijiye - khaali jagah bharne ke liye kuch mat gadhiye.",
    "",
    "LAMBAI: kul milakar 1300-1500 shabd (lagbhag 6,500-8,000 akshar) - "
    "yahi 8-10 minute hai. Chhote, bolne layak vaakya; saral Hindi "
    "(Devanagari). Ek hi baat dohra kar lambai mat badhaiye.",
    "",
    "Sirf ek JSON object, bina markdown ke:",
    "{",
    '  "publishable": true/false, "kill_reason": "",',
    '  "headline_hi": "video ka mukhya shirshak", "headline_en": "",',
    '  "lower_third_hi": "screen ki laal patti - 55 akshar tak, ek baat",',
    '  "youtube_title_hi": "90 akshar tak, sacha, clickbait nahi",',
    '  "title_options_hi": ["click wala par sacha", "seedha", "khoj wale shabd"],',
    '  "description_hi": "3-5 line ka saar (chapters aur srot code jodega)",',
    '  "tags": ["10-15 keywords"],',
    '  "sections": [{"key": "hook", "title_hi": "chapter ka naam, 40 akshar '
    'tak", "script_hi": "is hisse ki poori script", "drishya_en": ["3-5 '
    'English visual search phrases - jagah, sanstha, cheez, sarvajanik '
    'vyakti ka poora naam"]}]',
    "}",
])


def _source_block(srcs, wiki_title, wiki):
    parts = ["SROT (alag-alag akhbaar):", ""]
    for i, (h, u, t) in enumerate(srcs, 1):
        parts += ["[%d] %s - %s" % (i, h, u), t, ""]
    if wiki:
        parts += ["PRISHTHBHOOMI - Wikipedia: %s" % wiki_title, wiki, ""]
    return "\n".join(parts)


def parse_script(j):
    """Claude ke JSON se saaf hisse. (sections, kul akshar, galti)"""
    if not isinstance(j, dict):
        return [], 0, "jawab JSON nahi tha"
    if j.get("publishable") is not True:
        return [], 0, "sampadak ne roka: " + str(j.get("kill_reason") or "")[:300]
    got = {}
    for s in (j.get("sections") or []):
        if not isinstance(s, dict):
            continue
        key = str(s.get("key") or "").strip().lower()
        text = re.sub(r"\s+", " ", str(s.get("script_hi") or "")).strip()
        if key not in SECTION_KEYS or len(text) < 40 or key in got:
            continue
        default = dict(SECTIONS)[key]
        got[key] = {
            "key": key,
            "title_hi": re.sub(r"\s+", " ", str(s.get("title_hi") or default)).strip()[:60] or default,
            "script_hi": text,
            "drishya_en": [str(q).strip()[:60] for q in (s.get("drishya_en") or [])
                           if str(q).strip()][:5],
        }
    secs = [got[k] for k in SECTION_KEYS if k in got]
    if "hook" not in got or "aage" not in got or len(secs) < 5:
        return [], 0, "dhancha adhoora (%s)" % (", ".join(got) or "koi hissa nahi")
    total = len(" ".join(s["script_hi"] for s in secs))
    return secs, total, ""


CHECK_SYSTEM = "\n".join([
    "Aap ek fact-checker hain. Aapko SROT aur ek Hindi SCRIPT di jayegi.",
    "Script ka har vaakya srot se milaiye. Suchi banaiye un vaakyon ki jo:",
    "- koi naam, ank, tareekh, bayan ya ghatna kehte hain jo srot mein NAHI hai;",
    "- kisi aarop ya vivadit daawe ko pakke tathya ki tarah kehte hain;",
    "- kisi akhbaar ka naam lete hain;",
    "- rai ya bhavishyavani karte hain.",
    "Har ek ke liye \"sudhar\": srot ke hisaab se theek vaakya, ya khaali "
    "(\"\") agar vaakya hata dena chahiye. \"vaakya\" script mein se "
    "BILKUL JAS KA TAS copy kijiye.",
    'Sirf JSON: {"galtiyan": [{"vaakya": "...", "sudhar": "...", "kyun": "..."}]}',
    "Sab theek ho to khaali suchi.",
])


def apply_fixes(sections, fixes):
    """Fact-check ke sudhar script par lagao. Kitne lage, wo lautao."""
    n = 0
    for f in fixes or []:
        if not isinstance(f, dict):
            continue
        bad = re.sub(r"\s+", " ", str(f.get("vaakya") or "")).strip()
        good = re.sub(r"\s+", " ", str(f.get("sudhar") or "")).strip()
        if len(bad) < 10:
            continue
        for s in sections:
            if bad in s["script_hi"]:
                s["script_hi"] = re.sub(r"\s+", " ", s["script_hi"].replace(bad, good)).strip()
                n += 1
                break
    return n


def write_script(topic, srcs, wiki_title, wiki):
    """Srot se original script. (json, sections) ya (None, galti)"""
    block = _source_block(srcs, wiki_title, wiki)
    user = "\n".join([
        "MUDDA: " + topic["mudda_hi"],
        "Angrezi mein: " + topic["query_en"],
        "Ye mudda abhi Bharat mein charcha mein hai (%s)." % _signal_text(topic),
        "", block,
        "Upar ke %d srot aur prishthbhoomi se, niyamon ke hisaab se, lambi "
        "video ki script likhiye." % len(srcs),
    ])
    j = _ask_long(LONG_SYSTEM, user)
    secs, total, why = parse_script(j)
    if secs and total < CHARS_MIN:
        log("script chhoti (%d akshar) - ek baar aur" % total)
        j2 = _ask_long(LONG_SYSTEM, user + "\n\nPICHHLI KOSHISH SIRF %d AKSHAR KI "
                       "THI - 8 minute ke liye kam se kam %d akshar chahiye. "
                       "Srot mein jo jaankari chhoot gayi thi use jodiye (bina "
                       "kuch gadhe)." % (total, CHARS_WANT[0]))
        s2, t2, _w = parse_script(j2)
        if s2 and t2 > total:
            j, secs, total = j2, s2, t2
    if not secs:
        return None, why
    if total < CHARS_FLOOR:
        return None, "script sirf %d akshar ki bani - 8 minute ke layak srot nahi" % total

    # Doosri nazar: har vaakya srot se milao.
    try:
        import sy_ai
        script = "\n\n".join("[%s] %s" % (s["key"], s["script_hi"]) for s in secs)
        chk = sy_ai.ask_json(CHECK_SYSTEM, block + "\n\nSCRIPT:\n" + script, max_tokens=4000)
        fixes = (chk or {}).get("galtiyan") or []
        n = apply_fixes(secs, fixes)
        log("fact-check: %d sawaal, %d sudhar lage" % (len(fixes), n))
    except Exception as e:
        log("fact-check nahi chala (script waisi hi):", str(e)[:120])
    secs = [s for s in secs if len(s["script_hi"]) >= 40]
    return j, secs


def research(topic):
    """Mudde se story row. (story_id, "") ya ("", wajah)"""
    log("srot ikattha: %s (%s)" % (topic["mudda_hi"], topic["query_en"]))
    srcs = collect_sources(topic)
    if len(srcs) < min_sources():
        return "", "sirf %d akhbaar ke lekh khule (%d chahiye)" % (len(srcs), min_sources())
    wt, wiki = wiki_background(topic)
    j, secs = write_script(topic, srcs, wt, wiki)
    if not j:
        return "", secs
    script = " ".join(s["script_hi"] for s in secs)
    slug = re.sub(r"[^a-z0-9]+", "", topic["query_en"].lower())[:22]
    sid = "%s%s_%s" % (PREFIX, slug or "mudda", time.strftime("%m%d%H%M"))
    names = []
    for h, _u, _t in srcs:
        if h not in names:
            names.append(h)
    st.add_story({
        "story_id": sid, "beat": BEAT, "status": WORK, "score": 0,
        "sources": ", ".join(names),
        "source_link": srcs[0][1],
        "attribution_line": "स्रोत: " + " · ".join(names) + (" · विकिपीडिया" if wiki else ""),
        "headline_hi": str(j.get("headline_hi") or topic["mudda_hi"])[:200],
        "headline_en": str(j.get("headline_en") or topic["query_en"])[:200],
        "lower_third_hi": str(j.get("lower_third_hi") or topic["mudda_hi"])[:140],
        "script_hi": script,
        "yt_title": str(j.get("youtube_title_hi") or j.get("headline_hi") or "")[:95],
        "yt_description": str(j.get("description_hi") or "").strip()[:1500],
        "tags": ", ".join(str(t) for t in (j.get("tags") or []))[:480],
    })
    try:
        import sy_ingest
        sy_ingest.save_titles(sid, {"title_options_hi": j.get("title_options_hi")},
                              str(j.get("youtube_title_hi") or "")[:95])
    except Exception:
        pass
    st.kv_set("lv_sections_" + sid, secs)
    # Asli saar alag - render dobara chale to chapters do baar na judein.
    st.kv_set("lv_desc_" + sid, str(j.get("description_hi") or "").strip()[:1500])
    st.kv_set("lv_topic_" + _topic_key(topic["query_en"]), time.time())
    try:
        import sy_trend
        sy_trend.mark_used(topic["query_en"])
        sy_trend.mark_used(topic["mudda_hi"])
    except Exception:
        pass
    log("script taiyar: %s - %d hisse, %d akshar, %d srot"
        % (sid, len(secs), len(script), len(srcs)))
    return sid, ""


# ------------------------------------------------------------ shot list

def shot_counts(sections):
    """Har hisse ko kitne tukde. Kul 40-60, lambai ke anupat mein."""
    lens = [max(1, len(s["script_hi"])) for s in sections]
    total = sum(lens)
    want = int(max(SHOTS_MIN, min(SHOTS_MAX, round(total / float(CHARS_PER_SHOT)))))
    # Sabse bade bache hisse wale ko pehle - taaki jod theek "want" rahe
    # (seedha round() karne par 8 x 7.5 = 64 ho jaata tha, chhat se upar).
    raw = [want * n / float(total) for n in lens]
    out = [int(x) for x in raw]
    for i in sorted(range(len(raw)), key=lambda i: raw[i] - out[i], reverse=True):
        if sum(out) >= want:
            break
        out[i] += 1
    # Har tukda kam se kam ~50 akshar (4 second) ka ho, hisse mein 12 tak.
    return [max(1, min(k, n // 50 or 1, 12)) for k, n in zip(out, lens)]


def _split_sentences(text):
    return [p for p in re.split(r"(?<=[।\?!\.])\s+", str(text or "").strip()) if p]


def mech_shots(sec, n, topic, first=False):
    """AI ki shot list na bane to - vaakyon ko n tukdon mein baanto.

    Text script ka asli hissa hi rehta hai, isliye timing sahi rehti hai.
    """
    sents = _split_sentences(sec["script_hi"])
    if not sents:
        return []
    per = len(sec["script_hi"]) / float(max(1, n))
    groups, cur = [], ""
    for p in sents:
        cur = (cur + " " + p).strip()
        if len(cur) >= per and len(groups) < n - 1:
            groups.append(cur)
            cur = ""
    if cur:
        groups.append(cur)
    qs = list(sec.get("drishya_en") or []) or [topic["query_en"]]
    shots = []
    for i, g in enumerate(groups):
        shots.append({"text": g, "type": "place" if (first and i == 0) else "object",
                      "brief": sec.get("title_hi") or "",
                      "queries": [qs[i % len(qs)], topic["query_en"]][:2]})
    return shots


def section_shots(sec, n, topic, first=False):
    """Ek hisse ki shot list - sy_media ke picture editor wale niyam, par
    tukdon ki ginti lambi video ke hisaab se."""
    import sy_ai
    import sy_media
    rules = sy_media.SHOT_RULES.replace(
        "KAAM: script ko 4 se 6 tukdon mein toadiye",
        "KAAM: script ke is hisse ko %d se %d tukdon mein toadiye" % (max(1, n - 1), n + 1))
    note = ("Ye ek lambi (8-10 minute) video ka EK HISSA hai: \"%s\". " % sec["title_hi"])
    if not first:
        note += ("'JAGAH SABSE PEHLE' wala niyam sirf video ke pehle hisse par "
                 "hai - is hisse mein jo baat ho rahi hai, pehla drishya usi ka.")
    if sec.get("drishya_en"):
        note += "\nIs hisse ke liye sujhaaye gaye drishya: " + ", ".join(sec["drishya_en"])
    user = "\n".join([
        "MUDDA", topic["mudda_hi"], "", note, "",
        "SCRIPT KA YE HISSA (yahi boli jayegi):", sec["script_hi"],
        "", "NIYAM", rules,
        "", "ISI SHAPE MEIN JSON LAUTAIYE",
        json.dumps(sy_media.SHOT_SHAPE, ensure_ascii=False, indent=2),
    ])
    for _try in range(2):
        try:
            j = sy_ai.ask_json(sy_media.SHOT_SYSTEM, user, max_tokens=3500)
        except Exception as e:
            log("  shot list:", str(e)[:100])
            continue
        shots = check_shots(sec["script_hi"], (j or {}).get("shots"))
        if shots:
            return shots
    log("  '%s' ki shot list nahi bani - vaakyon se baant rahe hain" % sec["title_hi"])
    return mech_shots(sec, n, topic, first)


def check_shots(script, raw):
    """sy_media.shot_list jaisi jaanch: tukde jodne par script wapas bane."""
    import sy_media
    if not isinstance(raw, list) or not raw:
        return []
    shots, covered = [], ""
    for s in raw[:14]:
        if not isinstance(s, dict):
            continue
        text = re.sub(r"\s+", " ", str(s.get("text") or "")).strip()
        qs = [str(q).strip()[:60] for q in (s.get("queries") or [])[:3] if str(q).strip()]
        if len(text) < 15 or not qs:
            continue
        shots.append({"text": text, "type": str(s.get("type") or "place")[:20],
                      "brief": str(s.get("brief") or "")[:160], "queries": qs})
        covered += text
    a, b = sy_media._norm(covered), sy_media._norm(script)
    if not shots or not b:
        return []
    ratio = len(a) / float(len(b))
    if ratio < 0.85 or ratio > 1.15:
        log("  shot list ka text script se nahi milta (%.0f%%)" % (ratio * 100))
        return []
    return shots


def plan_shots(story, sections, topic):
    counts = shot_counts(sections)
    out = []
    for k, (sec, n) in enumerate(zip(sections, counts)):
        shots = section_shots(sec, n, topic, first=(k == 0))
        for sh in shots:
            sh["sec"] = k
            sh["done"] = False
        out += shots
        log("  hissa %d (%s): %d tukde" % (k + 1, sec["title_hi"], len(shots)))
    return out


# --------------------------------------------------------------- drishya

def _shrink(path):
    """Media potli chhoti rahe: badi tasveer/clip ko render layak naap par.

    Lambi video ke 40-60 drishya kai run tak cache mein rehte hain - ek-ek
    60 MB ki clip poori potli ko GB mein pahuncha deti.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size < 4 * 1024 * 1024:
        return
    tmp = path + ".small" + os.path.splitext(path)[1]
    if path.endswith(".mp4"):
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", path,
               "-t", "15", "-vf", "scale='min(1920,iw)':-2", "-an",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
               "-pix_fmt", "yuv420p", tmp]
    else:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", path,
               "-vf", "scale='min(2880,iw)':-2", "-q:v", "3", "-frames:v", "1", tmp]
    try:
        subprocess.run(cmd, check=True, timeout=300)
        if os.path.getsize(tmp) > 20000:
            os.replace(tmp, path)
    except Exception as e:
        log("  chhota nahi hua:", str(e)[:80])
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def fetch_section(story, shots, k, workdir):
    """Ek hisse ke tukdon ke asli drishya (sy_media.fetch_shots se)."""
    import sy_media
    bname = "b%02d" % k
    bdir = os.path.join(workdir, bname)
    os.makedirs(bdir, exist_ok=True)
    sub = {
        "story_id": story["story_id"], "beat": BEAT,
        "headline_hi": story.get("headline_hi"),
        "shots": json.dumps(shots, ensure_ascii=False),
        # Kendra ke sarvajanik chehre - pehle teen hisson mein (har hisse
        # mein ek hi chehra zabardasti nahi).
        "people_en": story.get("people_en") if k < 3 else "[]",
        "is_person": story.get("is_person") if k == 0 else 0,
    }
    got = sy_media.fetch_shots(sub, bdir) or []
    if not got:
        got = [dict(s, file="", credit="", source="") for s in shots]
    for sh in got:
        sh["sec"] = k
        sh["done"] = True
        if sh.get("file"):
            _shrink(os.path.join(bdir, sh["file"]))
            sh["file"] = bname + "/" + sh["file"]
    return got


CARTOON_SYSTEM = "\n".join([
    "Aap ek explainer video ke animation director hain. Kuch tukdon ka asli "
    "footage nahi mila - wahan ek chhota PRATEEKATMAK 2D cartoon chalega. "
    "Har tukde ke liye ek angrezi prompt likhiye (1-2 vaakya).",
    "",
    "NIYAM - koi chhoot nahi:",
    "1. Kisi ASLI vyakti ka naam ya shakl kabhi nahi - na netaa, na "
    "abhineta, na khiladi, na koi aur. Zaroorat ho to aam, kalpanik "
    "kirdaar: \"a cartoon government official\", \"a farmer character\".",
    "2. Kisi asli GHATNA ka nakli saboot nahi - baat ko prateek se dikhaiye "
    "(taraazu = nyay, graph = aankde, sadak/naksha = jagah, cheezein, "
    "prakriya), jaise explainer animation mein hota hai.",
    "3. Koi likhawat, akshar, logo, party ka nishaan ya jhanda nahi.",
    "4. Bachche nahi.",
    "5. Hinsa, khoon, laash, hathiyar ka drishya nahi - prateek se kahiye.",
    "",
    'Sirf JSON: {"prompts": [{"i": tukde_ka_number, "prompt": "..."}]}',
])

CARTOON_HEAD = ("Flat 2D cartoon animation, simple hand-drawn explainer "
                "illustration style, bold clean shapes, soft colours, gentle "
                "camera movement, clearly an illustration and not a "
                "photograph. Symbolic scene: ")
CARTOON_TAIL = (". Only generic stylized cartoon characters that do not "
                "resemble any real person. No text, no letters, no numbers, "
                "no logos, no flags, no signboards.")
CARTOON_NEG = ("photorealistic, photograph, realistic, live action, 3d render, "
               "real person, celebrity, politician likeness, text, letters, "
               "watermark, logo, subtitles, flag, children, blood, weapon")

_TYPE_PROMPT = {
    "place": "a stylized cartoon town street with small houses and trees",
    "institution": "a cartoon government building with pillars, people walking in",
    "people": "a generic cartoon official character speaking at a simple podium",
    "object": "cartoon objects on a table illustrating the idea",
    "document": "a cartoon paper document with a big stamp, no readable text",
    "map": "a simple cartoon map with a glowing location pin",
}


def scrub_names(prompt, names):
    """Prompt se asli logon ke naam hata do (Claude ne galti se likh diye hon)."""
    p = str(prompt or "")
    for n in names or []:
        for part in [n] + [w for w in str(n).split() if len(w) >= 4]:
            p = re.sub(r"\b%s\b" % re.escape(part), "a person", p, flags=re.I)
    return re.sub(r"\s+", " ", p).strip()


def cartoon_prompts(story, missing):
    """{shot_index: prompt}. Claude na chale to tukde ke type se."""
    import sy_ai
    names = []
    try:
        names = json.loads(story.get("people_en") or "[]")
    except Exception:
        pass
    got = {}
    lines = []
    for i, sh in missing:
        lines.append("%d. [%s] %s | dikhna chahiye: %s" % (
            i, sh.get("type") or "", sh.get("text", "")[:160], sh.get("brief") or ""))
    if lines:
        try:
            j = sy_ai.ask_json(CARTOON_SYSTEM, "MUDDA: %s\n\nTUKDE:\n%s"
                               % (story.get("headline_hi") or "", "\n".join(lines)),
                               max_tokens=3000)
            for it in ((j or {}).get("prompts") or []):
                try:
                    got[int(it.get("i"))] = str(it.get("prompt") or "")[:400]
                except Exception:
                    continue
        except Exception as e:
            log("  cartoon prompt nahi bane:", str(e)[:100])
    out = {}
    for i, sh in missing:
        body = got.get(i) or _TYPE_PROMPT.get(str(sh.get("type") or ""), _TYPE_PROMPT["object"])
        body = scrub_names(body, names)
        out[i] = CARTOON_HEAD + body.rstrip(". ") + CARTOON_TAIL
    return out


def make_cartoon(prompt, out_path):
    """Ek cartoon clip. (True, "") ya (False, wajah). Din ki seema nahi -
    chhoti video ka Veo kota (sy_veo.used_today) isse nahi kat-ta."""
    import sy_veo
    t0 = time.time()
    ok, why = sy_veo._clip(prompt, out_path, vertical=False,
                           people="allow_adult", negative=CARTOON_NEG,
                           secs=veo_seconds())
    if ok:
        day = "lv_veo_" + time.strftime("%Y-%m")
        st.kv_set(day, int(st.kv_get(day, 0) or 0) + 1)
        log("  cartoon bana (%.0f second)" % (time.time() - t0))
    return ok, why


# ---------------------------------------------------------------- render

def fmt_ts(sec):
    sec = int(max(0, sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def chapters(sections, timing, lead, body_end, min_gap=10.0):
    """Script ke hisson se YouTube chapters. [(second, naam)]

    YouTube ki shart: pehla 0:00 par, kam se kam teen, har ek 10 second se
    lamba. Na ho paaye to khaali - aadhe-adhoore chapters se kuch na hona
    behtar.
    """
    import sy_scenes
    text = re.sub(r"\s+", " ", (timing or {}).get("text") or "")
    out = []
    pos = 0
    for k, s in enumerate(sections):
        body = re.sub(r"\s+", " ", s["script_hi"]).strip()
        head = body[:60]
        # Agli khoj is hisse ke lagbhag ant se (thoda maarjin - TTS ke
        # tukde jodte waqt space idhar-udhar ho sakta hai).
        skip = int(len(body) * 0.9)
        if k == 0:
            out.append((0, s["title_hi"]))
            pos = skip
            continue
        # Pichhle hisse ke BAAD se khojo - warna koi line jo pehle bhi aa
        # chuki ho, chapter ko peeche kheench leti.
        i = text.find(head, pos)
        if i < 0:
            i = text.find(" ".join(head.split()[:5]), pos)
        t = sy_scenes.at_char(i, timing, lead, body_end) if i >= 0 else None
        if i >= 0:
            pos = i + skip
        if t is None:
            continue
        t = int(t)
        if t - out[-1][0] < min_gap:
            continue
        out.append((t, s["title_hi"]))
    return out if len(out) >= 3 else []


def chapters_text(ch):
    return "\n".join("%s %s" % (fmt_ts(t), name) for t, name in ch)


def _probe_dur(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", path],
                             capture_output=True, text=True, timeout=60)
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0


def make_preview(src, dst, max_mb=None, head_seconds=180):
    """Telegram ke liye jhalak: 480p, 50 MB se kam. (path, kya_hai) ya ("", wajah)

    Pehle POORI video kam naap par aazmate hain - aap poori dekh sakein. Wo
    bhi seema se badi bane to pehle 3 minute, thodi behtar quality mein.
    """
    max_mb = float(max_mb or preview_mb())
    limit = max_mb * 1024 * 1024
    dur = _probe_dur(src)
    if dur <= 0:
        return "", "video ki lambai nahi mili"
    kbps = int(limit * 8 * 0.92 / dur / 1000) - 64
    if kbps >= 220:
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
               "-vf", "scale=-2:480", "-c:v", "libx264", "-preset", "veryfast",
               "-b:v", "%dk" % kbps, "-maxrate", "%dk" % int(kbps * 1.3),
               "-bufsize", "%dk" % int(kbps * 2), "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", dst]
        try:
            subprocess.run(cmd, check=True, timeout=1800)
            if 0 < os.path.getsize(dst) <= limit:
                return dst, "poori video, 480p"
            log("poori jhalak %.1f MB bani - pehle %d second hi"
                % (os.path.getsize(dst) / 1048576.0, head_seconds))
        except Exception as e:
            log("poori jhalak nahi bani:", str(e)[:100])
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", src,
           "-t", str(int(head_seconds)), "-vf", "scale=-2:480",
           "-c:v", "libx264", "-preset", "veryfast", "-b:v", "900k",
           "-maxrate", "1200k", "-bufsize", "1800k", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "64k", "-movflags", "+faststart", dst]
    try:
        subprocess.run(cmd, check=True, timeout=900)
    except Exception as e:
        return "", "jhalak nahi bani: %s" % str(e)[:100]
    if os.path.getsize(dst) > limit:
        return "", "jhalak bhi %.0f MB ki bani" % (os.path.getsize(dst) / 1048576.0)
    return dst, "pehle %d minute, 480p" % (head_seconds // 60)


def _description(story, sections, ch, used_ai, presenter_used):
    desc = str(st.kv_get("lv_desc_" + story["story_id"])
               or story.get("yt_description") or "").strip()
    parts = [desc] if desc else []
    if ch:
        parts.append("अध्याय\n" + chapters_text(ch))
    if used_ai:
        parts.append("इस वीडियो में जिन हिस्सों की असली तस्वीर/फुटेज नहीं मिली, "
                     "वहाँ प्रतीकात्मक AI कार्टून चित्रण (स्क्रीन पर \"AI चित्रण\") "
                     "इस्तेमाल हुआ है - ये किसी असली व्यक्ति या घटना की तस्वीर "
                     "नहीं है।")
    if presenter_used:
        try:
            import sy_endcard
            parts.append(sy_endcard.DESC_LINE)
        except Exception:
            pass
    # sy_youtube.upload attribution_line aur disclaimer khud jodta hai, aur
    # 4900 par kaatta hai - chapters us kaat se pehle rahein.
    return "\n\n".join(parts)[:3800]


def render(story, workdir):
    """Aawaaz se Telegram tak. (True, "") ya (False, wajah)."""
    import render_core
    import sy_endcard
    import sy_media
    import sy_produce
    import sy_scenes
    import sy_tts
    import thumb

    sid = story["story_id"]
    sections = st.kv_get("lv_sections_" + sid) or []
    shots = json.loads(story.get("shots") or "[]")
    cfg.ensure_dirs()
    cfg.put_ffmpeg_on_path()
    render_core.set_intro_mode(False)
    # Naap pehle hi 16:9 - pichhli Reel ka 9:16 sy_scenes mein na reh jaye.
    render_core.set_layout(False)

    log("aawaaz (%d akshar)..." % len(story["script_hi"]))
    _vp, timing = sy_tts.speak(story["script_hi"], workdir, "teacher")
    secs = sy_tts.duration(os.path.join(workdir, "voice.wav"))
    lead, end = render_core.LEAD, render_core.END_SECONDS
    total = lead + secs + end
    log("aawaaz %.0f second (%.1f minute)" % (secs, secs / 60.0))

    credits, cuts = [], []
    if shots and any(s.get("file") for s in shots):
        sy_scenes.plan(shots, lead, total - end, timing)
        cuts = sy_scenes.build(shots, total, workdir)
        if cuts:
            credits = sy_scenes.credit_spans(shots)
        else:
            shots = []
    real = sum(1 for s in shots if s.get("file") and s.get("source") != "veo")
    ai = sum(1 for s in shots if s.get("source") == "veo")
    story["visual_line"] = "%d tukde: %d asli, %d AI चित्रण, %d studio" % (
        len(shots), real, ai, len(shots) - real - ai)

    out = os.path.join(cfg.OUTPUT_DIR, sid + "_hi.mp4")
    job = sy_produce.build_job(story, shots, credits, cuts, timing)
    job["studio_bg"] = sy_scenes.studio_path()
    job["endcard"] = sy_endcard.enabled()
    log("render (%.1f minute)..." % (total / 60.0))
    t0 = time.time()
    try:
        render_core.render(job, workdir, out)
    finally:
        render_core.set_intro_mode(False)
    if not os.path.exists(out) or os.path.getsize(out) < 1000000:
        return False, "video bani hi nahi"
    log("render %.0f second mein" % (time.time() - t0))
    out, presenter_used = sy_endcard.append(story, out, workdir)

    # Thumbnail - asli drishya pehle, AI chitran sabse baad.
    order = [s for s in shots if s.get("source") != "veo"] + \
            [s for s in shots if s.get("source") == "veo"]
    tsh = sy_media.thumb_art(order, workdir, story) if order else False
    thumb_is_ai = isinstance(tsh, dict) and tsh.get("source") == "veo"
    thumb_path = os.path.join(cfg.OUTPUT_DIR, sid + "_hi.jpg")
    art = os.path.join(workdir, "photo.jpg")
    ok, why = thumb.build(
        thumb_path, text=story.get("thumb_text") or story.get("key_fact") or "",
        place=story.get("ghost") or "", keyword=story.get("kicker") or "",
        art_path=art if os.path.exists(art) else "",
        style=story.get("thumb_style") or "slab", ai_label=True,
        art_is_ai=thumb_is_ai, workdir=workdir,
        category=story.get("category") or "politics",
        backdrop_style=story.get("style") or "grid",
        entity=story.get("thumb_entity") or "", vertical=False)
    if not ok:
        log("thumbnail nahi bani:", why)
        thumb_path = ""

    full = _probe_dur(out) or total
    ch = chapters(sections, timing, lead, lead + secs)
    desc = _description(story, sections, ch, ai > 0, presenter_used)
    st.update(sid, video_path=out, thumb_path=thumb_path, seconds=full,
              yt_description=desc, shots=json.dumps(shots, ensure_ascii=False))
    story.update(video_path=out, thumb_path=thumb_path, seconds=full, yt_description=desc)

    prev, what = make_preview(out, os.path.join(workdir, "preview.mp4"))
    mid = send_for_approval(story, prev, what, thumb_path, ch, ai)
    st.update(sid, status=WAIT, tg_message_id=mid, error="")
    log("jhalak Telegram par - approval ka intezaar:", sid)
    return True, ""


def send_for_approval(story, preview, what, thumb_path, ch, ai_clips):
    tg = _tg()
    sid = story["story_id"]
    mins = float(story.get("seconds") or 0) / 60.0
    cap = "\n".join([
        "<b>LAMBI VIDEO taiyar hai</b>", "",
        "<b>" + tg._esc(story.get("headline_hi") or "") + "</b>", "",
        "Poori video: %d:%02d minute, 1920x1080" % (int(mins), int((mins % 1) * 60)),
        "Ye jhalak: " + tg._esc(what or "nahi bani"),
        tg._esc(story.get("visual_line") or ""),
        tg._esc(story.get("attribution_line") or "")[:300],
        "Veo cartoon: %d clip" % ai_clips, "",
        "YouTube title: " + tg._esc(story.get("yt_title") or ""),
        "", "✅ dabane par POORI video YouTube par (unlisted) jayegi.",
    ])
    kb = {"inline_keyboard": [[
        {"text": "✅ Publish (poori video)", "callback_data": "la:" + sid},
        {"text": "❌ Reject", "callback_data": "lr:" + sid},
    ]]}
    fields = {"chat_id": tg._chat(), "caption": cap[:1024], "parse_mode": "HTML",
              "reply_markup": json.dumps(kb)}
    if preview and os.path.exists(preview):
        fields["supports_streaming"] = "true"
        res = tg._post("sendVideo", fields, files={"video": preview}, timeout=900)
    else:
        # Jhalak na bane to bhi faisla ruke nahi - thumbnail ke saath button.
        if thumb_path and os.path.exists(thumb_path):
            res = tg._post("sendPhoto", fields, files={"photo": thumb_path}, timeout=120)
            thumb_path = ""
        else:
            fields["text"] = fields.pop("caption")
            res = tg._post("sendMessage", fields, timeout=60)
    if thumb_path and os.path.exists(thumb_path):
        try:
            tg.send_photo(thumb_path, caption="Thumbnail - " + tg._esc(story.get("headline_hi") or "")[:200])
        except Exception as e:
            log("thumbnail nahi gayi:", e)
    if ch:
        _say("<b>Chapters</b> (description mein)\n<code>" + tg._esc(chapters_text(ch)) + "</code>")
    return int(res.get("message_id") or 0)


# ------------------------------------------------------------- job / stages

def _job():
    j = st.kv_get(JOB_KEY)
    return j if isinstance(j, dict) else None


def _save(job):
    job["updated"] = time.time()
    st.kv_set(JOB_KEY, job)


def _workdir(sid):
    return os.path.join(cfg.WORK_ROOT, sid)


def room_today():
    """Din ki 4 wali ginti mein jagah hai? (haan/nahi, wajah)"""
    cap = cfg.num("limits", "max_uploads_per_day", 5)
    if cap <= 0:
        return True, ""
    import sy_main
    used = sy_main.uploads_today() + sy_main.in_flight_count()
    if used >= cap:
        return False, "aaj ki %d ki jagah bhar chuki" % cap
    return True, ""


def due():
    """Kya nayi lambi video shuru karein? (haan/nahi, wajah)"""
    if not enabled():
        return False, "band hai"
    force = bool(st.kv_get(FORCE_KEY))
    if not force:
        if _days_since(st.kv_get(LAST_DAY_KEY, "")) < every_days():
            return False, "aaj baari nahi (ek din chhod kar)"
        if time.localtime().tm_hour < start_hour():
            return False, "%d baje ke baad" % start_hour()
        if time.time() < float(st.kv_get(RETRY_KEY, 0) or 0):
            return False, "pichhli koshish fail - thodi der baad"
    ok, why = room_today()
    if not ok:
        return False, why
    return True, ""


def start_job():
    ok, why = due()
    if not ok:
        return False
    st.kv_set(FORCE_KEY, None)
    log("naya mudda dhoondh rahe hain")
    items = pick_topics()
    if not items:
        _early_fail("koi trending mudda nahi mila")
        return False
    slate = "%x" % (int(time.time()) & 0xffffff)
    try:
        mid = send_slate(slate, items)
    except Exception as e:
        log("vikalp nahi bheje:", e)
        mid = 0
    job = {"stage": "choose", "slate": slate, "items": items, "at": time.time(),
           "mid": mid, "prev_day": st.kv_get(LAST_DAY_KEY, ""), "tried": [],
           "crashes": 0, "veo_made": 0}
    st.kv_set(LAST_DAY_KEY, _today())
    _save(job)
    log("%d mudde Telegram par" % len(items))
    return True


def _early_fail(why):
    """Script se pehle ki nakaami - aaj thodi der baad ek aur koshish."""
    key = "lv_tries_" + _today()
    n = int(st.kv_get(key, 0) or 0) + 1
    st.kv_set(key, n)
    if n < 2:
        st.kv_set(RETRY_KEY, time.time() + 3 * 3600)
        log("lambi video nahi bani (%s) - 3 ghante baad phir" % why)
    else:
        log("lambi video aaj nahi bani (%s) - kal phir" % why)
        st.kv_set(LAST_DAY_KEY, _yesterday())
        st.kv_set(RETRY_KEY, 0)


def fail_job(job, why):
    sid = job.get("sid")
    log("ROKA:", why)
    if sid:
        st.update(sid, status=FAIL, error=str(why)[:400])
        shutil.rmtree(_workdir(sid), ignore_errors=True)
        # Paisa lag chuka - aaj dobara nahi; kal ki baari.
        st.kv_set(LAST_DAY_KEY, _yesterday())
    else:
        st.kv_set(LAST_DAY_KEY, job.get("prev_day") or "")
        _early_fail(why)
    st.kv_set(JOB_KEY, None)
    _say("<b>Lambi video nahi ban payi</b>\n\n<b>Wajah:</b> " + _tg()._esc(str(why))[:600])


def _stage_choose(job, deadline):
    idx = job.get("chosen")
    if idx is None:
        if time.time() - float(job.get("at") or 0) < choice_wait_minutes() * 60:
            return False
        idx = 0
        _say("Lambi video ka jawab %d minute tak nahi aaya - pehla mudda khud chuna: <b>%s</b>"
             % (int(choice_wait_minutes()), _tg()._esc(job["items"][0]["mudda_hi"])))
    job["pick"] = int(idx)
    job["stage"] = "research"
    _save(job)
    return True


def _stage_research(job, deadline):
    items = job.get("items") or []
    order = [job.get("pick", 0)] + [i for i in range(len(items)) if i != job.get("pick", 0)]
    for i in order:
        if i in job["tried"] or i >= len(items):
            continue
        job["tried"].append(i)
        _save(job)
        sid, why = research(items[i])
        if sid:
            job["sid"] = sid
            job["topic"] = items[i]
            job["stage"] = "shots"
            _save(job)
            if i != job.get("pick", 0):
                _say("Chune hue mudde par kaafi srot nahi mile - agla mudda liya: <b>%s</b>"
                     % _tg()._esc(items[i]["mudda_hi"]))
            row = st.get(sid) or {}
            _progress("script taiyar - <b>%s</b>\n%s\nlagbhag %.0f minute. Ab drishya "
                      "dhoondh rahe hain (1-2 run lagengi)."
                      % (_tg()._esc(row.get("headline_hi") or ""),
                         _tg()._esc(row.get("attribution_line") or "")[:300],
                         len(row.get("script_hi") or "") / 13.0 / 60.0))
            return True
        log("mudda chhoda (%s): %s" % (items[i]["mudda_hi"], why))
        if time.time() > deadline:
            return False
    fail_job(job, "kisi bhi mudde par 8-10 minute layak srot nahi mile")
    return False


def _stage_shots(job, deadline):
    import sy_media
    sid = job["sid"]
    story = st.get(sid)
    sections = st.kv_get("lv_sections_" + sid) or []
    if not story or not sections:
        fail_job(job, "script kho gayi")
        return False
    if not story.get("category"):
        small = dict(story, script_hi=story["script_hi"][:2500])
        ad = sy_media.art_direction(small)
        st.update(sid, **ad)
        story.update(ad)
    log("shot list (%d hisse)..." % len(sections))
    shots = plan_shots(story, sections, job["topic"])
    if len(shots) < 10:
        fail_job(job, "shot list nahi bani")
        return False
    st.update(sid, shots=json.dumps(shots, ensure_ascii=False))
    os.makedirs(_workdir(sid), exist_ok=True)
    job["stage"] = "fetch"
    _save(job)
    log("%d tukde tay" % len(shots))
    return True


def _stage_fetch(job, deadline):
    sid = job["sid"]
    story = st.get(sid)
    shots = json.loads(story.get("shots") or "[]")
    workdir = _workdir(sid)
    os.makedirs(workdir, exist_ok=True)
    secs = sorted(set(int(s.get("sec", 0)) for s in shots))
    for k in secs:
        part = [s for s in shots if int(s.get("sec", 0)) == k]
        if all(s.get("done") for s in part):
            continue
        if time.time() > deadline:
            return False
        log("drishya: hissa %d/%d (%d tukde)" % (k + 1, len(secs), len(part)))
        got = fetch_section(story, part, k, workdir)
        rest = [s for s in shots if int(s.get("sec", 0)) != k]
        shots = sorted(rest + got, key=lambda s: int(s.get("sec", 0)))
        # Hisse ke andar kram wahi rehna chahiye - sorted() sthir hai, aur
        # got usi kram mein hai jo part ka tha.
        st.update(sid, shots=json.dumps(shots, ensure_ascii=False))
    real = sum(1 for s in shots if s.get("file"))
    log("asli drishya: %d/%d" % (real, len(shots)))
    miss = len(shots) - real
    _progress("asli drishya %d/%d tukdon par mile. %s" % (
        real, len(shots),
        ("Baaki %d par cartoon (Veo) ban raha hai." % miss) if miss and veo_on()
        else "Ab aawaaz aur render."))
    job["stage"] = "veo"
    _save(job)
    return True


def _stage_veo(job, deadline):
    sid = job["sid"]
    story = st.get(sid)
    shots = json.loads(story.get("shots") or "[]")
    missing = [(i, s) for i, s in enumerate(shots)
               if not s.get("file") and not s.get("veo_tried")]
    if missing and veo_on():
        workdir = _workdir(sid)
        vdir = os.path.join(workdir, "veo")
        os.makedirs(vdir, exist_ok=True)
        prompts = job.get("prompts") or {}
        need = [(i, s) for i, s in missing if str(i) not in prompts]
        if need:
            for i, p in cartoon_prompts(story, need).items():
                prompts[str(i)] = p
            job["prompts"] = prompts
            _save(job)
        for i, sh in missing:
            if time.time() > deadline:
                return False
            if job.get("veo_made", 0) >= veo_max_per_video():
                log("is video ki Veo chhat (%d) poori" % veo_max_per_video())
                break
            path = os.path.join(vdir, "c%02d.mp4" % i)
            ok, why = make_cartoon(prompts.get(str(i)) or (CARTOON_HEAD + _TYPE_PROMPT["object"] + CARTOON_TAIL), path)
            sh["veo_tried"] = True
            if ok:
                sh.update(file="veo/c%02d.mp4" % i, kind="clip", source="veo", credit=AI_CREDIT)
                job["veo_made"] = job.get("veo_made", 0) + 1
            else:
                log("  tukda %d par cartoon nahi: %s" % (i + 1, str(why)[:120]))
            st.update(sid, shots=json.dumps(shots, ensure_ascii=False))
            _save(job)
    elif missing:
        log("Veo band/SA nahi - %d tukde studio par" % len(missing))
    _progress("%sab aawaaz aur render (20-30 minute). Uske baad jhalak aayegi."
              % (("%d cartoon clip bani, " % job.get("veo_made", 0)) if job.get("veo_made") else ""))
    job["stage"] = "render"
    _save(job)
    return True


def _stage_render(job, deadline):
    sid = job["sid"]
    story = st.get(sid)
    workdir = _workdir(sid)
    try:
        ok, why = render(story, workdir)
    except Exception as e:
        ok, why = False, str(e)
    if not ok:
        # Render ki nakaami ek baar dobara - kabhi ffmpeg/aawaaz ki
        # kshanik dikkat hoti hai. Doosri baar bhi to chhod do.
        job["render_fails"] = job.get("render_fails", 0) + 1
        if job["render_fails"] >= 2:
            fail_job(job, "render nahi hua: " + str(why)[:300])
        else:
            log("render nahi hua (%s) - agli baari phir" % str(why)[:200])
            _save(job)
        return False
    # Kachcha saamaan ab kisi kaam ka nahi - sirf final video + thumbnail.
    shutil.rmtree(workdir, ignore_errors=True)
    job["stage"] = "wait"
    job["sent_at"] = time.time()
    _save(job)
    return False


def _stage_wait(job, deadline):
    sid = job.get("sid")
    story = st.get(sid) or {}
    if story.get("status") != WAIT:
        st.kv_set(JOB_KEY, None)         # faisla ho chuka
        return False
    hrs = approval_wait_hours()
    if hrs > 0 and time.time() - float(job.get("sent_at") or 0) > hrs * 3600:
        st.update(sid, status="expired",
                  error="lambi video par %.0f ghante tak jawab nahi aaya" % hrs)
        _drop_files(story)
        st.kv_set(JOB_KEY, None)
        _say("Lambi video par %.0f ghante tak jawab nahi aaya - chhod di (publish NAHI hui).\n\n%s"
             % (hrs, _tg()._esc(story.get("headline_hi") or "")))
    return False


STAGES = {
    "choose": _stage_choose, "research": _stage_research, "shots": _stage_shots,
    "fetch": _stage_fetch, "veo": _stage_veo, "render": _stage_render,
    "wait": _stage_wait,
}
HEAVY = ("research", "shots", "fetch", "veo", "render")


def tick():
    """sy_main.one_round() har chakkar mein. Kabhi throw nahi karta (bulane
    wala waise bhi pakadta hai)."""
    _sweep_done()
    job = _job()
    if not job:
        start_job()
        return
    # Pichhli run beech mein mar gayi (timeout/crash) - ginti. Teen baar
    # ek hi jagah atke to chhod do, warna har run wahi kharch dohrati.
    if job.get("running"):
        job["crashes"] = job.get("crashes", 0) + 1
        log("pichhli baar '%s' beech mein ruka tha (%d)" % (job["running"], job["crashes"]))
        if job["crashes"] >= 3:
            fail_job(job, "'%s' teen baar beech mein ruka" % job["running"])
            return
        job.pop("running", None)
        _save(job)
    deadline = time.time() + work_minutes() * 60
    while True:
        job = _job()
        if not job:
            return
        stage = job.get("stage")
        fn = STAGES.get(stage)
        if not fn:
            fail_job(job, "anjaan stage: %s" % stage)
            return
        if stage in HEAVY:
            job["running"] = stage
            _save(job)
        try:
            moved = fn(job, deadline)
        except Exception as e:
            import traceback
            traceback.print_exc()
            job = _job()
            if job:
                job.pop("running", None)
                job["crashes"] = job.get("crashes", 0) + 1
                _save(job)
                if job["crashes"] >= 3:
                    fail_job(job, "%s: %s" % (stage, str(e)[:300]))
            return
        job = _job()
        if job and job.get("running"):
            job.pop("running", None)
            _save(job)
        if not moved or not job or time.time() > deadline:
            return


def _drop_files(story):
    for k in ("video_path", "thumb_path"):
        p = str(story.get(k) or "")
        if p and os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
    shutil.rmtree(_workdir(story["story_id"]), ignore_errors=True)


def _sweep_done():
    """Nikal chuki lambi video ki file turant hatao - 180 MB ki file cache
    mein din bhar dhoti rehti."""
    rows = st.conn().execute(
        "SELECT * FROM stories WHERE beat = ? AND status IN "
        "('published','rejected','expired',?)", (BEAT, FAIL)).fetchall()
    for r in rows:
        row = dict(r)
        if any(os.path.isfile(str(row.get(k) or "")) for k in ("video_path", "thumb_path")) \
                or os.path.isdir(_workdir(row["story_id"])):
            _drop_files(row)
            log("safai:", row["story_id"])


# ------------------------------------------------------------- button / aadesh

def on_button(payload, verdict, cb_id, message):
    """sy_main.tick_decisions se - lk/lx/la/lr."""
    tg = _tg()
    job = _job() or {}
    if verdict in ("lk", "lx"):
        slate, _, idx = str(payload).partition(":")
        if job.get("stage") != "choose" or str(job.get("slate")) != slate:
            tg.acknowledge(cb_id, message, "Ye chunav pehle ho chuka")
            return
        if verdict == "lx":
            st.kv_set(JOB_KEY, None)
            st.kv_set(LAST_DAY_KEY, _yesterday())    # kal phir poochhenge
            tg.acknowledge(cb_id, message, "Theek hai - aaj lambi video nahi, kal phir")
            log("aaj lambi video nahi (aapne kaha)")
            return
        try:
            job["chosen"] = max(0, min(int(idx or 0), len(job["items"]) - 1))
        except Exception:
            job["chosen"] = 0
        _save(job)
        tg.acknowledge(cb_id, message, "Theek hai - ispar lambi video (kai run lagengi)")
        log("aapne chuna:", job["items"][job["chosen"]]["mudda_hi"])
        return

    sid = str(payload)
    story = st.get(sid)
    if not story or story.get("status") != WAIT:
        tg.acknowledge(cb_id, message, "Ispar faisla ho chuka hai")
        return
    if verdict == "la":
        st.update(sid, status="approved")
        tg.acknowledge(cb_id, message, "Theek hai - poori video upload ki baari par")
        log("approve:", sid)
    else:
        st.update(sid, status="rejected")
        _drop_files(story)
        tg.acknowledge(cb_id, message, "Theek hai, ye nahi jayegi")
        log("reject:", sid)
        try:
            import sy_feedback
            sy_feedback.record_reject(story)
            sy_feedback.ask(story)
        except Exception as e:
            log("wajah poochhne mein gadbad:", e)
    if job.get("sid") == sid:
        st.kv_set(JOB_KEY, None)


STAGE_HI = {"choose": "mudde ka chunav (aapke jawab ka intezaar)",
            "research": "srot aur script", "shots": "shot list",
            "fetch": "asli drishya dhoondhna", "veo": "cartoon chitran (Veo)",
            "render": "aawaaz aur render", "wait": "jhalak par aapka faisla"}


def short_status():
    """/haal ki ek line mein - "" jab kuch nahi ban raha."""
    job = _job()
    if not job:
        return ""
    return "lambi video: " + STAGE_HI.get(job.get("stage"), str(job.get("stage")))


def status_text():
    job = _job()
    lines = ["<b>Lambi video: %s</b>" % ("CHALU" if enabled() else "BAND")]
    if job:
        t = (job.get("topic") or {}).get("mudda_hi") or ""
        lines.append("Abhi: %s%s" % (STAGE_HI.get(job.get("stage"), job.get("stage")),
                                     (" - " + _tg()._esc(t)) if t else ""))
        if job.get("veo_made"):
            lines.append("Is video ke cartoon clip: %d" % job["veo_made"])
    else:
        ok, why = due()
        lines.append("Koi video nahi ban rahi. Agli: %s" % ("abhi" if ok else why))
    lines.append("Pichhli shuruaat: %s | har %d din | %d baje ke baad"
                 % (st.kv_get(LAST_DAY_KEY, "") or "kabhi nahi", every_days(), start_hour()))
    lines.append("Is mahine ke cartoon clip: %d" % int(st.kv_get("lv_veo_" + time.strftime("%Y-%m"), 0) or 0))
    return "\n".join(lines)


def do_command(rest):
    """/lambi | /lambi abhi | /lambi on|off | /lambi radd"""
    want = str(rest or "").strip().lower()
    if want in ("on", "chalu", "1", "haan"):
        st.kv_set("long_on", 1)
    elif want in ("off", "band", "0", "nahi"):
        st.kv_set("long_on", 0)
    elif want in ("abhi", "now", "turant"):
        if _job():
            _say("Ek lambi video pehle se ban rahi hai. <code>/lambi</code> se haal dekhiye.")
            return
        st.kv_set(FORCE_KEY, 1)
        st.kv_set(RETRY_KEY, 0)
        _say("Theek hai - agli baari mein lambi video ke mudde bhejta hoon "
             "(din ki jagah bachi ho tab).")
        return
    elif want in ("radd", "cancel", "roko"):
        job = _job()
        if not job:
            _say("Koi lambi video ban nahi rahi.")
            return
        fail_job(job, "aapne /lambi radd kiya")
        st.kv_set(LAST_DAY_KEY, _yesterday())    # aaj nahi - kal ki baari
        st.kv_set(RETRY_KEY, 0)
        return
    elif want:
        _say("<code>/lambi</code>, <code>/lambi abhi</code>, <code>/lambi on</code>, "
             "<code>/lambi off</code>, <code>/lambi radd</code>")
        return
    _say(status_text())

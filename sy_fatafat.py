"""FATAFAT KHABAR - din ki sabse badi 3-5 khabrein, ek minute se kam ki Reel.

KYUN (Oct 2026, Harshvardhan)
=============================
Lambi video aur bahut saare drishya wali video par views nahi aa rahe -
anchor par darshak tikta hi nahi. Isliye channel par ek REEL segment: 60
second ke andar din ki sabse trending/zaroori khabrein, fatafat. HeyGen ka
sabse achha istemal yahin hai - poori Reel mein anchor hi mukhya hai,
footage sirf upar ki chhoti khidki mein. 9:16 hai, isliye wahi video
YouTube Shorts, Facebook aur Instagram Reels teeno par jaati hai.

KRAM
====
1. build() (din mein [fatafat] hours ke hisaab se, default 8, 13 aur
   18 baje): pichhle ~18 ghante ke rashtriya akhbaaron ke shirshak
   (sy_long.NATIONAL_FEEDS) + Google/YouTube/X ke trend (sy_long.gather) ->
   Claude 3-5 khabrein chunta hai -> har khabar ke lekh khol kar Claude
   chhote vaakyon mein script likhta hai (TATHYA SIRF SROT SE) -> alag call
   har khabar ka TONE tay karti hai (serious / neutral / positive) -> pakki
   jaanch: script ka har ank srot mein hona chahiye, warna wo khabar
   chhodi jaati hai. Ek "story" row (beat = fatafat) katar mein sabse aage.
2. produce() (sy_produce.produce yahin bhejta hai): har tukda (hook, har
   khabar, CTA) ki ALAG aawaaz -> har khabar ki ek tasveer/clip (wahi
   sy_media.fetch_media, vision jaanch sahit) -> HeyGen: HAR TUKDA ALAG
   VIDEO, us tukde ke tone wale look/nirdesh se (gambhir khabar par muskaan
   nahi) -> 9:16 render (sy_fatafat_render) -> jodna -> thumbnail ->
   Telegram par chhoti jhalak + wahi ✅/❌.
3. ✅ ke baad wahi purana rasta: YouTube (#Shorts), phir sy_social se
   Facebook Page aur Instagram Reels.

KABHI NAHI RUKTI
================
HeyGen band / chaabi nahi / kota kam / fail ho to wo tukda bina anchor ke
(footage poori screen par, headline card, captions). Footage na mile to
channel ka studio. Din ki 4 video wali seema (max_uploads_per_day) mein
Fatafat bhi ginti hai - jagah na ho to us baari ki Reel nahi banti.
"""
import json
import os
import re
import shutil
import time
import wave

import sy_config as cfg
import sy_store as st

BEAT = "fatafat"
TONES = ("serious", "neutral", "positive")
TONE_HI = {"serious": "गंभीर", "neutral": "सामान्य", "positive": "अच्छी"}

HOOK_TONE = "neutral"
CTA_TONE = "neutral"
CTA_HI = "ऐसी ही फटाफट ख़बरों के लिए सत्ययात्रा न्यूज़ को सब्सक्राइब कीजिए।"
LEAD_PAD = 0.12        # har tukde ke aage chuppi (munh zara pehle khulta hai)
# Peeche - agle khabar se pehle ek chhoti saans. 0.30 se 0.18 (8 Oct 2026,
# Harshvardhan: "bahut lamba pause video mein nahi hona chahiye") - har
# khabar par 0.12 bachta hai, poori Reel mein lagbhag aadha second.
TAIL_PAD = 0.18
CPS = 13.0             # Sarvam ki raftaar (sy_tts.CPS) - andaaze ke liye
SLOT_KEY = "fatafat_slots"
USED_KEY = "fatafat_used"


def log(*a):
    print("[fatafat]", *a, flush=True)


# ----------------------------------------------------------- settings

def enabled():
    """Telegram ka /fatafat on|off config se upar (baaki switch jaisa)."""
    on = st.kv_get("fatafat_on")
    if on is not None:
        return bool(on)
    return cfg.num("fatafat", "enabled", 1) == 1


def set_enabled(on):
    st.kv_set("fatafat_on", 1 if on else 0)


def hours():
    """Din ke kis-kis ghante (India ka samay) ke baad ek Reel. "8, 13, 18"."""
    raw = cfg.get("fatafat", "hours") or "8, 13, 18"
    out = []
    for p in re.split(r"[,\s]+", raw):
        try:
            h = int(p)
        except ValueError:
            continue
        if 0 <= h <= 23 and h not in out:
            out.append(h)
    return sorted(out)


def min_items():
    return max(2, int(cfg.num("fatafat", "min_items", 3)))


def max_items():
    return max(min_items(), int(cfg.num("fatafat", "max_items", 5)))


def max_seconds():
    return float(cfg.num("fatafat", "max_seconds", 58))


def anchor_engine():
    """Reel ka anchor kaun banaye: "veo" (Google Veo, GCP credit se - Oct
    2026 se default), "heygen" (lip-sync, HeyGen API credit), "none"."""
    eng = str(st.kv_get("fatafat_anchor") or cfg.get("fatafat", "anchor")
              or "veo").strip().lower()
    if eng not in ("veo", "heygen", "none"):
        eng = "veo"
    if eng == "heygen" and cfg.num("fatafat", "heygen", 1) != 1:
        eng = "none"
    return eng


def set_anchor(eng):
    """Telegram: /fatafat anchor veo|heygen|none (config se upar)."""
    st.kv_set("fatafat_anchor", eng)


def hook_on():
    """Shuru ki "आज की चार बड़ी ख़बरें, फटाफट" wali line. 9 Oct 2026,
    Harshvardhan: "pehli clip hata dijiye, seedhe news wala part aaye" -
    isliye default BAND; Reel seedhe pehli khabar se shuru hoti hai."""
    return cfg.num("fatafat", "hook", 0) == 1


def use_heygen():
    return anchor_engine() == "heygen"


def short_lines():
    """Veo ek clip mein 8 second - tab har line chhoti."""
    return anchor_engine() == "veo"


def trim_line(line, limit):
    """Lambi line ko poore vaakyon par chhota karo (limit akshar tak).
    Pehla vaakya hi lamba ho to line waisi hi (wo tukda Sarvam se bolega)."""
    line = str(line or "").strip()
    if len(line) <= limit:
        return line
    out = ""
    for sent in re.split(r"(?<=[।!?])\s+", line):
        cand = (out + " " + sent).strip()
        if len(cand) > limit:
            break
        out = cand
    return out or line


def preview_mb():
    return float(cfg.num("fatafat", "preview_mb", 45))


def _today():
    return time.strftime("%Y-%m-%d")


# ----------------------------------------------------------- baari

def due_slot(now=None):
    """Abhi kaun si baari bakaya hai? ghanta ya None.

    Sirf AAKHRI beeti hui baari - subah wali chhoot gayi aur shaam ho gayi to
    sirf shaam wali (do Reel ek saath nahi)."""
    t = time.localtime(now) if now else time.localtime()
    passed = [h for h in hours() if t.tm_hour >= h]
    if not passed:
        return None
    h = passed[-1]
    done = st.kv_get(SLOT_KEY) or {}
    if done.get("day") != time.strftime("%Y-%m-%d", t):
        done = {}
    if h in (done.get("slots") or []):
        return None
    return h


def reels_left_today(now=None):
    """Aaj ki kitni Reel abhi banni baaki hain - abhi wali baari (agar
    bakaya) + aage ki baariyan. Band ho to 0.

    sy_main.production_allowed() inke liye din ki jagah AARAKSHIT rakhta
    hai: 8 Oct 2026 ko shaam 6 baje ki Reel isliye nahi bani kyunki din ki
    4 jagah aam video pehle hi le chuke the ("aaj ki jagah bhar chuki")."""
    if not enabled():
        return 0
    t = time.localtime(now) if now else time.localtime()
    done = st.kv_get(SLOT_KEY) or {}
    if done.get("day") != time.strftime("%Y-%m-%d", t):
        done = {}
    slots = set(done.get("slots") or [])
    hs = hours()
    passed = [h for h in hs if t.tm_hour >= h]
    # Pehle ki chhooti baariyan ab nahi banengi (due_slot sirf aakhri leta hai).
    start = passed[-1] if passed else -1
    return len([h for h in hs if h >= start and h not in slots])


def mark_slot(h):
    done = st.kv_get(SLOT_KEY) or {}
    if done.get("day") != _today():
        done = {"day": _today(), "slots": []}
    # Isse pehle ki chhooti baariyan bhi - wo ab nahi banengi.
    done["slots"] = sorted(set((done.get("slots") or [])
                               + [x for x in hours() if x <= h]))
    st.kv_set(SLOT_KEY, done)


# ----------------------------------------------------------- tone

# Pakka niyam (Claude kuch bhi kahe): in shabdon wali khabar par muskaan
# kabhi nahi. Shabd ki SHURUAAT milayi jaati hai ("हादसे", "मृतकों" bhi);
# chhote shabd (आग) poore milte hain - warna "आगे" bhi pakda jaata.
SERIOUS_STEMS = (
    "मौत", "मृत", "मारे", "हादस", "दुर्घटन", "हत्या", "कत्ल", "क़त्ल",
    "बलात्कार", "दुष्कर्म", "आतंक", "हमल", "विस्फोट", "धमाक", "बाढ़", "बाढ",
    "भूकंप", "भूस्खलन", "सूखा", "तूफ़ान", "तूफान", "चक्रवात", "घायल", "शहीद",
    "शव", "लाश", "आत्महत्या", "ख़ुदकुशी", "खुदकुशी", "अपहरण", "लूट", "डकैती",
    "दंगा", "दंगे", "महामारी", "मर्डर", "गोलीबारी", "फायरिंग", "डूब", "झुलस",
    "killed", "dead", "death", "accident", "murder", "rape", "terror",
    "attack", "flood", "earthquake", "blast", "injured")
SERIOUS_EXACT = ("आग", "मरे", "मरी", "जली", "जले")


def _words(text):
    return [w for w in re.split(r"[\s।,.!?\"'()\[\]:;\-–—|/]+", str(text or "").lower()) if w]


def is_grave(text):
    for w in _words(text):
        if w in SERIOUS_EXACT or any(w.startswith(s) for s in SERIOUS_STEMS):
            return True
    return False


def guard_tone(tone, text):
    """Claude ka tone + pakka niyam. Galat/khaali -> neutral."""
    tone = str(tone or "").strip().lower()
    if tone not in TONES:
        tone = "neutral"
    if is_grave(text):
        return "serious"
    return tone


TONE_SYSTEM = "\n".join([
    "Aap ek Hindi news channel ke producer hain. Har khabar ke liye tay "
    "kijiye ki AI anchor ka chehra kaisa ho:",
    '- "serious": maut, haadsa, apraadh, aapda, hinsa, beemari ka prakop, '
    'kisi ka nuksaan, tanaav/yuddh - gambhir chehra, muskaan bilkul nahi.',
    '- "positive": sach mein achhi khabar - kaamyaabi, inaam, rahat, bachav, '
    'nayi suvidha, khel mein jeet, tyohaar - halki muskaan.',
    '- "neutral": baaki sab - rajneeti, faisle, aankde, bayan, mausam ki '
    'aam jaankari.',
    "Shak ho to neutral. Kisi bhi khabar mein kisi ki maut/chot ho to "
    "hamesha serious, chahe baaki hissa achha ho.",
    'Sirf JSON: {"tones": ["serious|neutral|positive", ...]} - har khabar '
    "ke liye ek, usi kram mein.",
])


def tones_for(items):
    """Har khabar ka tone - Claude se, phir pakka niyam. Kabhi throw nahi."""
    got = []
    try:
        import sy_ai
        user = "\n".join("%d. %s - %s" % (i + 1, it.get("headline_hi", ""),
                                          it.get("line_hi", ""))
                         for i, it in enumerate(items))
        j = sy_ai.ask_json(TONE_SYSTEM, user, max_tokens=300, temperature=0.0)
        got = list((j or {}).get("tones") or [])
    except Exception as e:
        log("tone Claude se nahi mila (niyam se):", str(e)[:120])
    out = []
    for i, it in enumerate(items):
        t = got[i] if i < len(got) else ""
        out.append(guard_tone(t, "%s %s" % (it.get("headline_hi", ""),
                                           it.get("line_hi", ""))))
    return out


# ----------------------------------------------------------- tathya jaanch

_DEV = str.maketrans("०१२३४५६७८९", "0123456789")


def numbers_in(text):
    s = str(text or "").translate(_DEV)
    s = re.sub(r"(?<=\d)[,\s](?=\d{2,3}\b)", "", s)   # 1,200 / 1 200 -> 1200
    return set(re.findall(r"\d+(?:\.\d+)?", s))


def unsupported_numbers(line, source):
    """Script ke wo ank jo srot mein nahi. [] = sab theek."""
    have = numbers_in(source)
    return sorted(n for n in numbers_in(line) if n not in have)


# ----------------------------------------------------------- khabrein chunna

def fresh_heads(max_age_h=18):
    """Rashtriya akhbaaron ke taaze shirshak + summary + link."""
    import sy_long
    import sy_net
    now = time.time()
    out, seen = [], set()
    for name, url in sy_long.NATIONAL_FEEDS:
        try:
            items = sy_net.parse_rss(sy_net.get_text(url, timeout=30))
        except Exception as e:
            log("feed nahi khula (%s): %s" % (name, str(e)[:80]))
            continue
        for it in items[:30]:
            title = re.sub(r"\s+", " ", it.get("title") or "").strip()
            if len(title) < 20:
                continue
            ts = sy_net.parse_date(it.get("published"))
            if ts and now - ts > max_age_h * 3600:
                continue
            k = title.lower()[:80]
            if k in seen:
                continue
            seen.add(k)
            out.append({"src": name, "title": title, "link": it.get("link") or "",
                        "summary": (it.get("summary") or "")[:400]})
    return out


def trend_hints():
    try:
        import sy_long
        got, _links = sy_long.gather()
    except Exception as e:
        log("trend nahi mile:", str(e)[:100])
        return []
    out = []
    for src in ("google", "youtube", "x"):
        out += (got.get(src) or [])[:12]
    return out


def _used_recent():
    """Pichhli Reels ki khabrein (20 ghante) - dobara nahi."""
    rows = st.kv_get(USED_KEY) or []
    return [r for r in rows if isinstance(r, dict)
            and float(r.get("at") or 0) > time.time() - 20 * 3600]


def note_used(items):
    rows = _used_recent() + [{"h": it.get("headline_hi", ""), "at": time.time()}
                             for it in items]
    st.kv_set(USED_KEY, rows[-30:])


PICK_SYSTEM = "\n".join([
    "Aap ek Hindi news channel ke sampadak hain. Channel ek minute se kam "
    "ki 'फटाफट ख़बरें' Reel banata hai - din ki sabse BADI aur sabse zyada "
    "CHARCHA wali khabrein, aam Hindi darshak (UP/Bihar/MP/Rajasthan, "
    "chhote shehar) ke liye.",
    "Aapko aaj ke Bharat ke akhbaaron ke shirshak (number ke saath) aur "
    "Google/YouTube/X ke trending shabd milenge.",
    "Inmein se %(lo)d-%(hi)d alag khabrein chuniye, sabse badi pehle:",
    "- jo kai akhbaaron mein ho ya trending shabdon se mel khaye;",
    "- jiska asar bahut logon par ho (desh, paisa, suraksha, mausam/aapda, "
    "bada faisla, bada haadsa, khel ki badi jeet);",
    "- alag-alag vishay (ek hi maamle ki do khabrein nahi);",
    "- celebrity ki niji baat, rashifal, share bazaar ka roz ka haal, "
    "videsh ki chhoti sthaniya baat NAHI.",
    "'Pehle ja chuki' suchi wali khabar dobara tabhi jab usmein bada naya mod ho.",
    'Sirf JSON: {"khabrein": [{"heads": [shirshak number, ...], "query_en": '
    '"angrezi search query, 3-6 shabd", "kyun": "ek line"}]}',
])


def pick(heads, hints, used):
    import sy_ai
    parts = ["AAJ KE SHIRSHAK:"]
    parts += ["%d. [%s] %s" % (i, h["src"], h["title"]) for i, h in enumerate(heads[:200])]
    if hints:
        parts += ["", "TRENDING SHABD:", ", ".join(hints)]
    if used:
        parts += ["", "PEHLE JA CHUKI (pichhli Reel):"] + ["- " + u["h"] for u in used]
    j = sy_ai.ask_json(PICK_SYSTEM % {"lo": min_items(), "hi": max_items()},
                       "\n".join(parts), max_tokens=1200)
    out = []
    for it in ((j or {}).get("khabrein") or [])[:max_items() + 1]:
        if not isinstance(it, dict):
            continue
        idx = []
        for x in it.get("heads") or []:
            try:
                x = int(x)
            except (TypeError, ValueError):
                continue
            if 0 <= x < len(heads) and x not in idx:
                idx.append(x)
        if idx:
            out.append({"heads": idx[:4],
                        "query_en": str(it.get("query_en") or "")[:80]})
    return out


def collect(item, heads):
    """Is khabar ke srot: summary + 1-2 khule lekh. (text, hosts, links)"""
    import sy_ingest
    import sy_net
    texts, hosts, links = [], [], []
    for x in item["heads"]:
        h = heads[x]
        texts.append("[%s] %s. %s" % (h["src"], h["title"], h["summary"]))
        if h["link"]:
            links.append(h["link"])
    # GDELT (sy_trend.search_links) yahan JAAN-BOOJHKAR NAHI. 8 Oct 2026 ki
    # subah wali Reel ki script mein 35 minute lage - har khabar par GDELT
    # "saans le raha hai" (30/60 second) baar-baar. Shirshak ke apne lekh +
    # summary kaafi hain; lekh na khule to summary hi srot hai.
    got = 0
    for url in links:
        if got >= 2:
            break
        try:
            if sy_ingest.link_rank(url) >= 3:
                continue
            txt = sy_net.article_text(sy_net.get_text(url, timeout=30),
                                      min_chars=sy_ingest.MIN_ARTICLE)
        except Exception as e:
            log("  nahi khula:", sy_net.host(url), str(e)[:60])
            continue
        if txt:
            texts.append("[%s] %s" % (sy_net.host(url), txt[:2500]))
            hosts.append(sy_net.host(url).replace("www.", ""))
            got += 1
    for x in item["heads"]:
        if heads[x]["src"] not in hosts:
            hosts.append(heads[x]["src"])
    return "\n\n".join(texts)[:6000], hosts, links


WRITE_SYSTEM = "\n".join([
    "Aap 'फटाफट ख़बरें' Reel ki script likhte hain. Har khabar ~10-12 second "
    "mein boli jaayegi, ek AI anchor bolegi.",
    "",
    "HARD RULES:",
    "1. Har khabar mein SIRF wahi tathya jo us khabar ke SROT mein likhe hain. "
    "Koi naam, ank, jagah, tareekh khud se nahi. Ank wahi likhiye jo srot "
    "mein hai (ankon mein, jaise 12, 2026).",
    "2. line_hi: 2-3 CHHOTE vaakya, kul 18-28 shabd, bolchaal ki Hindi "
    "(Devanagari). Pehla vaakya seedha mukhya baat. Akhbaar/channel ka naam "
    "nahi, 'के मुताबिक' nahi.",
    "3. headline_hi: screen ke bade card ke liye, 3-6 shabd, 34 akshar tak.",
    "4. kicker_hi: jagah ya vishay, 1-2 shabd (jaise 'दिल्ली', 'क्रिकेट').",
    "5. photo_queries: 2-3 ANGREZI khoj - us jagah/sanstha/cheez ki tasveer "
    "ke liye (jaise 'Election Commission of India building'). Kisi aam "
    "aadmi ka chehra nahi.",
    "5b. people_en: agar khabar ke KENDRA mein koi jaana-maana vyakti hai "
    "(abhineta, neta, khiladi, udyogpati - jinka Wikipedia lekh ho), unka "
    "poora ANGREZI naam jaisa Wikipedia par likha hai (jaise 'Nana Patekar', "
    "'Rahul Gandhi'), zyada se zyada 2. Aam log, peedit, aaropi, ya jinka "
    "naam srot mein nahi - kabhi nahi. Na ho to [].",
    "6. hook_hi: shuru ki ek line, 6-10 shabd, khabron ki ginti ke saath, "
    "jaise 'आज की चार बड़ी ख़बरें, फटाफट।' - koi tathya nahi.",
    "7. Jis khabar ka srot adhoora ho use chhod dijiye (items mein mat "
    "daaliye).",
    "",
    'Sirf JSON: {"hook_hi": "", "items": [{"n": khabar ka number, '
    '"headline_hi": "", "kicker_hi": "", "line_hi": "", "photo_queries": [], '
    '"people_en": []}], '
    '"youtube_title_hi": "90 akshar tak", "tags": ["5-8 keyword"]}',
])


VEO_RULE = (
    "\n\nVEO NIYAM (sabse zaroori): har line_hi ek AI anchor 8 second ke "
    "clip mein bolegi - isliye line_hi 95 akshar (Devanagari) se ZYADA "
    "NAHI: 1-2 chhote vaakya, kul 10-15 shabd, sirf sabse badi baat. "
    "hook_hi bhi 50 akshar tak.")


def write(picked, srcs):
    import sy_ai
    parts = []
    for i, (p, (text, _h, _l)) in enumerate(zip(picked, srcs), 1):
        parts += ["=== KHABAR %d ===" % i, text, ""]
    system = WRITE_SYSTEM + (VEO_RULE if short_lines() else "")
    return sy_ai.ask_json(system, "\n".join(parts), max_tokens=2500)


def est_seconds(text):
    return len(str(text or "")) / CPS + LEAD_PAD + TAIL_PAD


def fit_items(items, hook, budget=None):
    """Andaaze se ek minute ke andar - peeche se khabrein hatao (kam se kam
    min_items)."""
    budget = budget if budget is not None else max_seconds()
    items = list(items)
    while len(items) > min_items():
        total = est_seconds(hook) + est_seconds(CTA_HI) + sum(
            est_seconds(it["line_hi"]) for it in items)
        if total <= budget:
            break
        items.pop()
    return items


NUM_HI = {2: "दो", 3: "तीन", 4: "चार", 5: "पाँच"}


def default_hook(n):
    return "आज की %s बड़ी ख़बरें, फटाफट।" % NUM_HI.get(n, str(n))


def people_in(names, source):
    """Claude ke bataye naam - sirf wo jo srot se mel khaate hon.

    Angrezi srot mein naam ka har hissa hona chahiye (koi aur vyakti na aa
    jaye). Srot lagbhag poora Hindi ho (Devanagari mein naam) to Claude ka
    angrezi roop maan lete hain - portrait() khud Wikipedia ke shirshak se
    naam ka har hissa milata hai, galat lekh nahi uthata."""
    src = str(source or "")
    low = src.lower()
    latin = len(re.findall(r"[A-Za-z]", src))
    out = []
    for nm in names or []:
        nm = re.sub(r"\s+", " ", str(nm or "")).strip()[:60]
        parts = [w for w in nm.lower().split() if len(w) > 2]
        if len(parts) < 2 or nm in out:
            continue
        if all(w in low for w in parts) or latin < 200:
            out.append(nm)
    return out[:2]


def make_items(j, picked, srcs):
    """Claude ka JSON -> jaanchi hui khabrein (tone ke bina)."""
    out = []
    for it in (j or {}).get("items") or []:
        if not isinstance(it, dict):
            continue
        try:
            n = int(it.get("n")) - 1
        except (TypeError, ValueError):
            continue
        if not 0 <= n < len(picked):
            continue
        line = re.sub(r"\s+", " ", str(it.get("line_hi") or "")).strip()
        if short_lines():
            import sy_fatafat_veo
            line = trim_line(line, sy_fatafat_veo.LINE_MAX_CHARS)
        head = re.sub(r"\s+", " ", str(it.get("headline_hi") or "")).strip()
        if len(line) < 25 or not head:
            continue
        text, hosts, links = srcs[n]
        bad = unsupported_numbers(line + " " + head, text)
        if bad:
            log("chhodi - ank srot mein nahi (%s): %s" % (", ".join(bad), head))
            continue
        q = [str(x)[:80] for x in (it.get("photo_queries") or []) if str(x).strip()][:3]
        out.append({"headline_hi": head[:60], "kicker_hi": str(it.get("kicker_hi") or "")[:20],
                    "line_hi": line, "photo_queries": q or [picked[n]["query_en"]],
                    "people_en": people_in(it.get("people_en"), text),
                    "hosts": hosts[:3], "link": (links or [""])[0]})
    return out


def build(slot=None):
    """Aaj ki is baari ki Reel ki script banao, katar mein daalo. sid ya ""."""
    sid = "ff_%s" % time.strftime("%Y%m%d_%H")
    if st.get(sid):
        return ""
    heads = fresh_heads()
    if len(heads) < 10:
        log("taaze shirshak bahut kam (%d)" % len(heads))
        return ""
    picked = pick(heads, trend_hints(), _used_recent())
    if len(picked) < min_items():
        log("Claude ne kaafi khabrein nahi chunin (%d)" % len(picked))
        return ""
    srcs = [collect(p, heads) for p in picked]
    j = write(picked, srcs)
    items = make_items(j, picked, srcs)
    if len(items) < min_items():
        log("jaanch ke baad kaafi khabrein nahi bachin (%d)" % len(items))
        return ""
    hook = str((j or {}).get("hook_hi") or "").strip()
    items = fit_items(items[:max_items()],
                      (hook or default_hook(len(items))) if hook_on() else "")
    if not hook or numbers_in(hook) - {str(len(items))} or len(hook) > 70:
        hook = default_hook(len(items))
    hook = re.sub(r"(चार|तीन|पाँच|पांच|दो|\d)\s+(बड़ी|बडी|अहम|ज़रूरी|जरूरी)",
                  NUM_HI.get(len(items), str(len(items))) + r" \2", hook)
    for it, tone in zip(items, tones_for(items)):
        it["tone"] = tone

    hosts = []
    for it in items:
        for h in it["hosts"]:
            if h not in hosts:
                hosts.append(h)
    title = str((j or {}).get("youtube_title_hi") or "").strip() \
        or ("फटाफट ख़बरें: " + items[0]["headline_hi"])
    desc = ["फटाफट ख़बरें - %s" % time.strftime("%d-%m-%Y"), ""]
    desc += ["%d. %s - %s" % (i + 1, it["headline_hi"], it["line_hi"])
             for i, it in enumerate(items)]
    tags = [str(t).strip() for t in ((j or {}).get("tags") or []) if str(t).strip()]
    tags = ["फटाफट ख़बरें", "Hindi News", "Shorts"] + tags[:8]
    plan = {"hook": hook, "items": items, "cta": CTA_HI, "slot": slot}
    row = {
        "story_id": sid, "beat": BEAT, "score": 19,
        "sources": ", ".join(hosts[:6]),
        "source_link": items[0].get("link") or "",
        "attribution_line": "स्रोत: " + " · ".join(hosts[:6]),
        "headline_hi": ("फटाफट: " + " | ".join(it["headline_hi"] for it in items))[:200],
        "headline_en": "Fatafat news reel",
        "lower_third_hi": items[0]["headline_hi"][:60],
        "script_hi": " ".join(([hook] if hook_on() else [])
                              + [it["line_hi"] for it in items] + [CTA_HI]),
        "yt_title": title[:85],
        "yt_description": "\n".join(desc),
        "tags": ", ".join(tags)[:480],
        "shots": json.dumps(plan, ensure_ascii=False),
    }
    st.add_story(row)
    note_used(items)
    log("Reel ki script taiyar: %s (%d khabrein: %s)" % (
        sid, len(items), ", ".join("%s/%s" % (it["headline_hi"][:24], it["tone"])
                                   for it in items)))
    return sid


# ----------------------------------------------------------- video

def segments(plan):
    """Plan -> tukde: [hook,] har khabar, CTA. Hook sirf [fatafat] hook = 1
    par - default Reel seedhe pehli khabar se (katar ki purani plan mein
    hook likha ho tab bhi)."""
    items = plan.get("items") or []
    n = len(items)
    segs = []
    if hook_on():
        segs.append({"tag": "hook", "kind": "hook", "index": -1, "count": n,
                     "text": plan.get("hook") or default_hook(n), "tone": HOOK_TONE,
                     "headline": "आज की %d बड़ी ख़बरें" % n, "kicker": ""})
    for i, it in enumerate(items):
        segs.append({"tag": "k%d" % i, "kind": "item", "index": i, "count": n,
                     "text": it["line_hi"], "tone": it.get("tone") or "neutral",
                     "headline": it["headline_hi"], "kicker": it.get("kicker_hi") or "",
                     "queries": it.get("photo_queries") or [],
                     "people": it.get("people_en") or []})
    segs.append({"tag": "cta", "kind": "cta", "index": n, "count": n,
                 "text": plan.get("cta") or CTA_HI, "tone": CTA_TONE,
                 "headline": "सब्सक्राइब करें", "kicker": "सत्ययात्रा न्यूज़"})
    return segs


def speech_only(src):
    """Aawaaz ke aage-peeche ki chuppi ka naap - (shuru, ant) second mein.
    Sarvam har tukde ke aage-peeche thodi chuppi chhod deta hai; teen-chaar
    tukdon mein wo jud kar saaf sunai deti hai (8 Oct 2026)."""
    try:
        import sy_explainer
        a, b = sy_explainer._speech_span(src)
        return (a, b) if b - a > 0.4 else (0.0, 0.0)
    except Exception as e:
        log("chuppi ka naap nahi hua:", str(e)[:80])
        return (0.0, 0.0)


def pad_wav(src, out, lead=LEAD_PAD, tail=TAIL_PAD):
    """Bolne wala hissa + aage-peeche utni hi chuppi jitni chahiye.

    Yahi file HeyGen ko bhi jaati hai aur render mein bhi - dono ka samay ek."""
    with wave.open(src, "rb") as w:
        prm = w.getparams()
        frames = w.readframes(w.getnframes())
        rate = w.getframerate()
    step = prm.nchannels * prm.sampwidth
    a, b = speech_only(src)
    if b > a:
        frames = frames[int(a * rate) * step:int(b * rate) * step]
    with wave.open(out, "wb") as d:
        d.setparams(prm)
        d.writeframes(b"\x00" * int(rate * lead) * step)
        d.writeframes(frames)
        d.writeframes(b"\x00" * int(rate * tail) * step)
    return out


def drop_to_fit(segs, budget):
    """Asli aawaaz ke baad: lambi ho to peeche ki khabar hatao (kam se kam
    min_items), aur ginti/number dobara."""
    def total():
        return sum(s["dur"] for s in segs)
    while total() > budget:
        items = [s for s in segs if s["kind"] == "item"]
        if len(items) <= min_items():
            log("min khabron par bhi %.1fs - aise hi" % total())
            break
        segs.remove(items[-1])
    n = len([s for s in segs if s["kind"] == "item"])
    for s in segs:
        s["count"] = n
        if s["kind"] == "cta":
            s["index"] = n
    return segs


PERSON_CLIP_MAX_MB = 60


def _ok_clip(path):
    """Utri clip chalti hai? (kam se kam 2 second ki video)"""
    try:
        import subprocess
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60)
        return float((out.stdout or "0").strip() or 0) >= 2.0
    except Exception:
        return False


def person_media(names, d):
    """PRASIDDH VYAKTI KI KHABAR PAR UNKA HI DRISHYA (8 Oct 2026, Harshvardhan:
    "famous hastiyon ki news par footage aani chahiye").

    Kram: (1) Commons par us vyakti ki apni category ka VIDEO (chalti
    footage, muft licence) -> (2) Wikipedia lekh ki mukhya tasveer
    (portrait - naam ka har hissa shirshak mein, warna nahi) -> (3) Commons
    category ki tasveer. Sirf wahi srot jinka licence saaf hai - news
    channel/YouTube ki footage NAHI (copyright strike). (path, credit,
    kind) - kind "clip" | "person"; kuch na mile to ("", "", "")."""
    import sy_media
    import sy_net
    for name in (names or [])[:2]:
        tries = (("clip", sy_media.commons_person_clip),
                 ("person", sy_media.portrait),
                 ("person", sy_media.commons_person_photo))
        for kind, fn in tries:
            try:
                url, credit = fn(name)
            except Exception as e:
                log("  %s (%s): %s" % (name, fn.__name__, str(e)[:80]))
                continue
            if not url:
                continue
            path = os.path.join(d, "clip.mp4" if kind == "clip" else "photo.jpg")
            try:
                size = sy_net.download(url, path, max_bytes=PERSON_CLIP_MAX_MB * 1024 * 1024)
            except Exception as e:
                log("  %s utra nahi: %s" % (name, str(e)[:80]))
                continue
            good = (_ok_clip(path) if kind == "clip"
                    else size > 2048 and sy_media.is_raster(path))
            if not good:
                try:
                    os.remove(path)
                except Exception:
                    pass
                continue
            if kind == "clip":
                # Thumbnail aur hook ke liye ek frame bhi.
                sy_media._frame_from_clip(d)
            log("  %s ka %s mila: %s" % (name, "footage" if kind == "clip" else "chitra", credit))
            return path, credit, kind
    return "", "", ""


def _media_for(seg, d):
    """Khabar ki tasveer/clip. Prasiddh vyakti ho to pehle UNKA (person_media),
    warna jagah/sanstha ki (fetch_media, vision jaanch sahit). (path, credit)."""
    if seg.get("people"):
        path, credit, kind = person_media(seg["people"], d)
        if path:
            seg["media_kind"] = kind
            return path, credit
    import sy_media
    mini = {"wants_photo": 1, "photo_queries": json.dumps(seg.get("queries") or []),
            "headline_hi": seg["headline"]}
    try:
        credit, source = sy_media.fetch_media(mini, d)
    except Exception as e:
        log("drishya nahi mila:", str(e)[:100])
        return "", ""
    for name in ("clip.mp4", "photo.jpg"):
        p = os.path.join(d, name)
        if source and os.path.exists(p):
            return p, credit
    return "", ""


def heygen_anchor(segs, workdir):
    """Har tukde ka HeyGen video (tone wala chehra). Kitne lage. Kabhi throw nahi."""
    if not use_heygen():
        log("[fatafat] heygen = 0 hai - bina anchor")
        return 0
    try:
        import sy_heygen
        ok, why = sy_heygen.ready({"beat": BEAT})
        if not ok:
            log("HeyGen anchor nahi:", why)
            return 0
        need = sum(s["dur"] for s in segs)
        if sy_heygen.room_seconds() < need:
            log("HeyGen ka aaj ka kota kam (%.0fs bache, %.0fs chahiye) - bina anchor"
                % (sy_heygen.room_seconds(), need))
            return 0
        jobs = []
        for s in segs:
            if sy_heygen.credit_blocked():
                log("HeyGen credit khatam - baaki tukde bina anchor")
                break
            try:
                vid = sy_heygen.submit_clip(s["voice"], s["dir"], s["tone"],
                                            "SatyaYatra fatafat " + s["tag"])
                jobs.append((s, vid))
            except Exception as e:
                log("HeyGen tukda %s nahi bheja: %s" % (s["tag"], str(e)[:160]))
        deadline = time.time() + sy_heygen.wait_minutes() * 60
        got = 0
        for s, vid in jobs:
            left = max(1.0, (deadline - time.time()) / 60.0)
            path, cx = sy_heygen.fetch_clip(
                vid, os.path.join(s["dir"], "heygen.mp4"), s["dur"], left)
            if path:
                s.update(anchor=True, anchor_file=path, anchor_cx=cx)
                got += 1
            else:
                log("tukda %s par anchor nahi: %s" % (s["tag"], cx))
        return got
    except Exception as e:
        log("HeyGen mein gadbad (bina anchor ke aage):", str(e)[:200])
        return 0


def produce(story):
    """Fatafat Reel banao aur Telegram par approval ke liye. True/False."""
    import render_core
    import sy_produce
    import sy_scenes
    import sy_telegram
    import sy_tts
    import thumb
    import sy_fatafat_render as R

    sid = story["story_id"]
    cfg.ensure_dirs()
    cfg.put_ffmpeg_on_path()
    workdir = os.path.join(cfg.WORK_ROOT, sid)
    shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir)
    st.update(sid, status="producing", error="")
    try:
        plan = json.loads(story.get("shots") or "{}")
        segs = segments(plan)
        if len([s for s in segs if s["kind"] == "item"]) < min_items():
            raise RuntimeError("plan mein kaafi khabrein nahi")

        for s in segs:
            s["dir"] = os.path.join(workdir, s["tag"])
            os.makedirs(s["dir"], exist_ok=True)
        n_veo = 0
        if anchor_engine() == "veo":
            # VEO ANCHOR: har tukde ka clip jismein presenter khud bolti hai -
            # jo tukda lage uski aawaaz Veo ki; baaki neeche Sarvam se.
            import sy_fatafat_veo
            log("Veo anchor (%d tukde)..." % len(segs))
            n_veo = sy_fatafat_veo.make_all(segs, workdir, LEAD_PAD, TAIL_PAD)

        log("aawaaz (%d tukde)..." % len([s for s in segs if not s.get("voice")]))
        for s in segs:
            if s.get("voice"):
                continue
            raw, _timing = sy_tts.speak(s["text"], s["dir"])
            s["voice"] = pad_wav(raw, os.path.join(s["dir"], "voice_pad.wav"))
            # Lambai padi hui file se - pad_wav kinaare ki chuppi kaat deta
            # hai, isliye wo aawaaz se chhoti ho sakti hai.
            total = sy_tts.duration(s["voice"])
            s["dur"] = round(total, 3)
            s["speech"] = (LEAD_PAD, round(max(LEAD_PAD + 0.3, total - TAIL_PAD), 3))
        n0 = len(plan.get("items") or [])
        segs = drop_to_fit(segs, max_seconds())
        n = segs[0]["count"]
        hooks = [s for s in segs if s["kind"] == "hook"]
        for h in hooks:
            h["headline"] = "आज की %d बड़ी ख़बरें" % n
        if hooks and n != n0:
            # Hook mein ginti badli - wahi ek line dobara (sasta).
            h = hooks[0]
            h["text"] = default_hook(n)
            # Veo wala hook purani ginti bol chuka - ab Sarvam, bina anchor.
            h["anchor"] = h["veo"] = False
            raw, _t = sy_tts.speak(h["text"], h["dir"])
            h["voice"] = pad_wav(raw, os.path.join(h["dir"], "voice_pad.wav"))
            total = sy_tts.duration(h["voice"])
            h["dur"] = round(total, 3)
            h["speech"] = (LEAD_PAD, round(max(LEAD_PAD + 0.3, total - TAIL_PAD), 3))

        log("drishya...")
        first = {}
        for s in segs:
            if s["kind"] == "item":
                s["media"], s["credit"] = _media_for(s, s["dir"])
                if s["media"] and not first:
                    first = s
        studio = sy_scenes.studio_path() or ""
        for s in segs:
            if s["kind"] == "hook":
                s["media"] = first.get("media") or ""
                s["media_kind"] = first.get("media_kind") or ""
            elif s["kind"] == "cta":
                s["media"] = ""
            s["bg"] = studio

        if use_heygen():
            n_anchor = heygen_anchor(segs, workdir)
        else:
            n_anchor = sum(1 for s in segs if s.get("anchor"))
        log("anchor (%s) %d/%d tukdon par" % (anchor_engine(), n_anchor, len(segs)))

        log("render...")
        date = sy_produce.date_hindi()
        parts = []
        for s in segs:
            s["date"] = date
            parts.append(R.render_segment(
                s, os.path.join(workdir, "seg_%s.mp4" % s["tag"]), workdir))
        out = os.path.join(cfg.OUTPUT_DIR, sid + "_reel.mp4")
        R.join(parts, out, workdir, music=render_core.pick_music(sid))
        total = sum(s["dur"] for s in segs)

        desc = str(story.get("yt_description") or "").strip()
        if any(s.get("veo") and s.get("anchor") for s in segs):
            import sy_fatafat_veo
            desc += "\n\n" + sy_fatafat_veo.desc_line()
        elif n_anchor:
            import sy_heygen
            desc += "\n\n" + sy_heygen.desc_line()
        items = [s for s in segs if s["kind"] == "item"]
        st.update(sid, yt_description=desc)
        story["yt_description"] = desc

        thumb_path = os.path.join(cfg.OUTPUT_DIR, sid + "_reel.jpg")
        art = ""
        for s in items:
            p = os.path.join(s["dir"], "photo.jpg")
            if os.path.exists(p):
                art = p
                break
        ok, why = thumb.build(thumb_path, text=items[0]["headline"],
                              keyword="फटाफट ख़बरें", art_path=art, style="slab",
                              ai_label=True, workdir=workdir, vertical=True)
        if not ok:
            log("thumbnail nahi bani:", why)
            thumb_path = ""

        vline = "anchor %d/%d tukde · %s" % (n_anchor, len(segs), " · ".join(
            "%d:%s" % (s["index"] + 1, TONE_HI.get(s["tone"], s["tone"])) for s in items))
        story.update(seconds=total, visual_line=vline,
                     shot_summary="\n".join("%d. %s%s" % (
                         s["index"] + 1, s["headline"][:40],
                         "" if s.get("media") else " (×)") for s in items))
        st.update(sid, video_path=out, thumb_path=thumb_path, seconds=total)
        prev = R.preview(out, os.path.join(workdir, "preview.mp4"), preview_mb())
        log("Telegram par bhej rahe hain (%.1fs, %.1f MB)"
            % (total, os.path.getsize(prev) / 1048576.0))
        mid = sy_telegram.send_video_for_approval(story, prev, thumb_path)
        st.update(sid, status="awaiting", tg_message_id=mid)
        for s in segs:   # bada kachcha saamaan turant hatao (media cache)
            shutil.rmtree(s["dir"], ignore_errors=True)
        return True
    except Exception as e:
        log("GADBAD:", e)
        st.update(sid, status="failed", error=str(e)[:400])
        try:
            sy_telegram.send_message("<b>Fatafat Reel nahi ban payi</b>\n\n<b>Wajah:</b>\n"
                                     + sy_telegram._esc(str(e))[:600])
        except Exception:
            pass
        return False


# ----------------------------------------------------------- Telegram

def status_text():
    rows = ["<b>Fatafat Khabar Reel: %s</b>" % ("CHALU" if enabled() else "BAND")]
    rows.append("Baari: %s baje (India)" % ", ".join(str(h) for h in hours()))
    rows.append("Khabrein: %d-%d, %.0f second tak" % (min_items(), max_items(), max_seconds()))
    eng = anchor_engine()
    rows.append("Anchor: %s" % {"veo": "Google Veo (GCP credit se, aawaaz Veo ki)",
                                "heygen": "HeyGen (lip-sync)", "none": "nahi"}[eng])
    if eng == "veo":
        try:
            import sy_fatafat_veo as V
            ok, why = V.ready()
            rows.append("Veo: %s | aaj %d/%d clip" % ("taiyaar" if ok else why,
                                                      V.used_today(), V.max_clips_per_day()))
        except Exception:
            pass
    try:
        import sy_heygen
        ok, why = sy_heygen.ready({"beat": BEAT})
        if eng == "heygen":
            rows.append("HeyGen: %s" % ("haan" if ok else "nahi - " + why))
            rows.append("Chehre ke look (gambhir/neutral/muskaan): %s" % (
                "teeno diye hain" if sy_heygen.looks_ready() else
                "nahi - ek hi chehra, sirf motion nirdesh (CLOUD.md dekhiye)"))
    except Exception:
        pass
    done = st.kv_get(SLOT_KEY) or {}
    if done.get("day") == _today():
        rows.append("Aaj ho chuki baari: %s" % (", ".join(map(str, done.get("slots") or [])) or "-"))
    rows += ["", "<code>/fatafat on|off</code> · <code>/fatafat abhi</code> - turant ek",
             "<code>/fatafat anchor veo|heygen|none</code> - anchor kaun banaye"]
    return "\n".join(rows)

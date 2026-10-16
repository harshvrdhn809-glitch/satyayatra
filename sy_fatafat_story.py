"""Fatafat Reel - EK KHABAR, EK MINUTE (16 Oct 2026).

Harshvardhan: "Reel version ab tak channel ke liye sabse taakatwar hai.
Ab ek Reel mein kai khabrein nahi - sirf EK viral khabar, ~1 minute ki,
tathyon ke saath saaf nichod: maamle mein kya hua, asli baat kya thi, aur
ant mein kya hua."

DHANCHA
=======
Ek Reel = ek khabar ke 4-6 HISSE, har hissa ek tukda (Veo par ek 8 second
ka clip, ~95 akshar). Upar patti mein hisse ka naam:

    क्या हुआ       - pehla, hamesha. Seedhe ghatna, sabse badi baat pehle.
    पूरा मामला     - (vaikalpik) shuruaat / prishthbhoomi.
    असली बात       - hamesha. Mudde ki jad - kyun ye badi baat hai.
    अहम तथ्य       - (vaikalpik) ank, naam, tareekh - jo srot mein hain.
    किसने क्या कहा - (vaikalpik) dono paksh / zimmedar ka bayan.
    अब आगे / नतीजा - aakhri, hamesha. Ab tak ka nateeja ya aage kya.

Ant mein wahi chhota subscribe (CTA). Tathya SIRF srot se - har hisse ka
har ank srot mein milna chahiye; na mile to wo hissa (vaikalpik ho) chhoot
jaata hai, ya (zaroori ho) poori khabar chhod kar agli umeedwaar.
"""
import re
import time

import sy_config as cfg

FIRST = "क्या हुआ"
CRUX = "असली बात"
LAST = ("अब आगे", "नतीजा")
OPTIONAL = ("पूरा मामला", "अहम तथ्य", "किसने क्या कहा")
LABELS = (FIRST, "पूरा मामला", CRUX, "अहम तथ्य", "किसने क्या कहा") + LAST


def log(*a):
    print("[fatafat-story]", *a, flush=True)


def parts_min():
    return max(3, int(cfg.num("fatafat", "story_parts_min", 4)))


def parts_max():
    return max(parts_min(), int(cfg.num("fatafat", "story_parts_max", 6)))


# ----------------------------------------------------------- chunav

PICK_ONE_SYSTEM = "\n".join([
    "Aap ek Hindi news channel ke sampadak hain. Channel 1 minute ki Reel "
    "banata hai - har Reel mein SIRF EK khabar, poori kahani ke saath: kya "
    "hua, asli mudda kya hai, aur ab tak ka nateeja.",
    "Aapko aaj ke Bharat ke akhbaaron ke shirshak (number ke saath) aur "
    "Google/YouTube/X ke trending shabd milenge.",
    "Aaj ki sabse VIRAL / sabse zyada charcha wali khabrein chuniye - "
    "zyada se zyada 3, sabse achhi pehle. Achhi khabar wo:",
    "- jo kai akhbaaron mein ho AUR/YA trending shabdon se mel khaye;",
    "- jiski ek KAHANI ho (kuch hua -> kyun badi baat -> nateeja/aage kya), "
    "sirf ek line ki suchna nahi;",
    "- jiske thos tathya (naam, ank, jagah) shirshakon mein dikhte hon;",
    "- aam Hindi darshak (UP/Bihar/MP/Rajasthan) ke liye maayne rakhe - "
    "desh, paisa, suraksha, bada faisla, bada haadsa, bada vivad, khel ki "
    "badi jeet, mashhoor vyakti se judi BADI ghatna.",
    "NAHI: celebrity ki niji gossip, rashifal, share bazaar ka roz ka haal, "
    "bina tathya ki afwah, videsh ki chhoti sthaniya baat.",
    "'Pehle ja chuki' suchi wali khabar dobara tabhi jab bada naya mod ho.",
    "Har khabar ke liye us EK khabar ke SAARE shirshak number dijiye.",
    'Sirf JSON: {"khabrein": [{"heads": [shirshak number, ...], "query_en": '
    '"angrezi search query, 3-6 shabd", "kyun": "ek line - kyun viral"}]}',
])


def pick_one(heads, hints, used):
    """Viral khabar ke 1-3 umeedwaar, sabse achha pehle."""
    import sy_ai
    parts = ["AAJ KE SHIRSHAK:"]
    parts += ["%d. [%s] %s" % (i, h["src"], h["title"]) for i, h in enumerate(heads[:200])]
    if hints:
        parts += ["", "TRENDING SHABD:", ", ".join(hints)]
    if used:
        parts += ["", "PEHLE JA CHUKI (pichhli Reel):"] + ["- " + u["h"] for u in used]
    j = sy_ai.ask_json(PICK_ONE_SYSTEM, "\n".join(parts), max_tokens=900)
    out = []
    for it in ((j or {}).get("khabrein") or [])[:3]:
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
            out.append({"heads": idx[:6], "query_en": str(it.get("query_en") or "")[:80],
                        "kyun": str(it.get("kyun") or "")[:140]})
    return out


# ----------------------------------------------------------- script

STORY_SYSTEM = "\n".join([
    "Aap 1 minute ki Hindi news Reel likhte hain - EK khabar ka saaf, tathyon "
    "wala nichod. Ek AI anchor ise bolegi; har HISSA alag ~8 second ka clip "
    "hai.",
    "",
    "HISSE (kram yahi; 4-6 hisse):",
    '1. "क्या हुआ" - HAMESHA pehla. Seedhe ghatna - kaun, kya, kahan. '
    "Pehle hi vaakya mein sabse badi baat (darshak yahin rukta hai).",
    '2. "पूरा मामला" - vaikalpik. Maamla kahan se shuru hua.',
    '3. "असली बात" - HAMESHA. Mudde ki jad: ye kyun badi baat hai, asli '
    "sawaal/vivad kya hai.",
    '4. "अहम तथ्य" - vaikalpik. Srot ke thos ank/naam/tareekh.',
    '5. "किसने क्या कहा" - vaikalpik. Zimmedar ya dono paksh ka bayan.',
    '6. "अब आगे" ya "नतीजा" - HAMESHA aakhri. Ab tak kya nateeja nikla, ya '
    "aage kya hoga (jitna srot mein hai).",
    "",
    "HARD RULES:",
    "1. SIRF wahi tathya jo SROT mein likhe hain. Koi naam, ank, jagah, "
    "tareekh khud se nahi. Ank ankon mein (12, 2026). Anumaan, raay, "
    "'shayad' nahi.",
    "2. line_hi: har hisse mein 1-2 CHHOTE vaakya, 95 akshar (Devanagari) se "
    "ZYADA NAHI, bolchaal ki Hindi. Hisse aapas mein jude hon - kahani aage "
    "badhe, wahi baat dohraayi na jaaye.",
    "3. card_hi: us hisse ki sabse badi baat screen ke card ke liye, 3-6 "
    "shabd, 34 akshar tak.",
    "4. photo_queries: har hisse ke liye 1-2 ANGREZI khoj - us jagah/"
    "sanstha/cheez ki tasveer (aam aadmi ka chehra nahi).",
    "5. headline_hi: poori khabar ka shirshak, 4-8 shabd. kicker_hi: jagah "
    "ya vishay, 1-2 shabd.",
    "6. people_en: khabar ke KENDRA ke jaane-maane vyakti (neta, abhineta, "
    "khiladi) ka poora angrezi naam jaisa Wikipedia par, zyada se zyada 2; "
    "aam log/peedit/aaropi nahi. Na ho to [].",
    "7. Akhbaar/channel ka naam nahi, 'के मुताबिक' nahi.",
    "8. Srot itna adhoora ho ki kahani na bane to {\"parts\": []} lautaiye.",
    "",
    'Sirf JSON: {"headline_hi": "", "kicker_hi": "", "people_en": [], '
    '"parts": [{"label": "क्या हुआ", "card_hi": "", "line_hi": "", '
    '"photo_queries": []}], "youtube_title_hi": "90 akshar tak, sawaal ya '
    'jigyasa jagane wala par sach", "tags": ["5-8 keyword"]}',
])


def write_story(src_text):
    import sy_ai
    return sy_ai.ask_json(STORY_SYSTEM, "=== SROT ===\n" + src_text, max_tokens=2000)


def _norm_label(lbl):
    lbl = re.sub(r"\s+", " ", str(lbl or "")).strip()
    for L in LABELS:
        if lbl == L or L in lbl:
            return L
    return ""


def make_story(j, src_text, line_limit=95):
    """Claude/Gemini ka JSON -> jaanchi hui khabar, ya None (wajah log mein).

    Kram aur zaroori hisse pakke: pehla "क्या हुआ", koi "असली बात", aakhri
    "अब आगे"/"नतीजा". Kisi hisse mein srot se bahar ka ank ho to wo hissa
    (vaikalpik ho) hat-ta hai, zaroori ho to poori khabar None."""
    import sy_fatafat as F
    parts = []
    for p in (j or {}).get("parts") or []:
        if not isinstance(p, dict):
            continue
        lbl = _norm_label(p.get("label"))
        line = re.sub(r"\s+", " ", str(p.get("line_hi") or "")).strip()
        card = re.sub(r"\s+", " ", str(p.get("card_hi") or "")).strip()
        if not lbl or len(line) < 15:
            continue
        line = F.trim_line(line, line_limit)
        bad = F.unsupported_numbers(line + " " + card, src_text)
        if bad:
            if lbl in OPTIONAL:
                log("hissa '%s' chhoda - ank srot mein nahi (%s)" % (lbl, ", ".join(bad)))
                continue
            log("zaroori hissa '%s' mein srot se bahar ank (%s) - khabar chhodi"
                % (lbl, ", ".join(bad)))
            return None
        q = [str(x)[:80] for x in (p.get("photo_queries") or []) if str(x).strip()][:2]
        parts.append({"label": lbl, "card_hi": (card or lbl)[:40], "line_hi": line,
                      "photo_queries": q})
    if not parts or parts[0]["label"] != FIRST:
        log("pehla hissa 'क्या हुआ' nahi")
        return None
    if parts[-1]["label"] not in LAST:
        log("aakhri hissa 'अब आगे/नतीजा' nahi")
        return None
    if not any(p["label"] == CRUX for p in parts):
        log("'असली बात' wala hissa nahi")
        return None
    head = re.sub(r"\s+", " ", str((j or {}).get("headline_hi") or "")).strip()
    if not head or F.unsupported_numbers(head, src_text):
        head = parts[0]["card_hi"]
    # Lambi ho to beech ke vaikalpik hisse peeche se hatao - pehla, asli
    # baat aur aakhri hamesha rehte hain.
    while len(parts) > parts_max():
        opt = [i for i, p in enumerate(parts) if p["label"] in OPTIONAL]
        if not opt:
            break
        parts.pop(opt[-1])
    if len(parts) < parts_min():
        log("sirf %d hisse - kahani adhoori" % len(parts))
        return None
    return {"headline_hi": head[:70],
            "kicker_hi": str((j or {}).get("kicker_hi") or "")[:20],
            "people_en": F.people_in((j or {}).get("people_en"), src_text),
            "parts": parts,
            "youtube_title_hi": str((j or {}).get("youtube_title_hi") or "").strip()[:85],
            "tags": [str(t).strip() for t in ((j or {}).get("tags") or []) if str(t).strip()][:8]}


def fit_parts(story, budget):
    """Andaaze se ek minute ke andar - vaikalpik hisse peeche se hatao."""
    import sy_fatafat as F
    parts = story["parts"]
    def total():
        return F.est_seconds(F.CTA_HI) + sum(F.est_seconds(p["line_hi"]) for p in parts)
    while total() > budget and len(parts) > parts_min():
        opt = [i for i, p in enumerate(parts) if p["label"] in OPTIONAL]
        if not opt:
            break
        parts.pop(opt[-1])
    return story


# ----------------------------------------------------------- bahar ka

def build(slot=None):
    """Is baari ki EK-KHABAR Reel ki script, katar mein. sid ya ""."""
    import json
    import sy_fatafat as F
    import sy_store as st
    sid = "ff_%s" % time.strftime("%Y%m%d_%H")
    if st.get(sid):
        return ""
    heads = F.fresh_heads()
    if len(heads) < 10:
        log("taaze shirshak bahut kam (%d)" % len(heads))
        return ""
    cands = pick_one(heads, F.trend_hints(), F._used_recent())
    if not cands:
        log("koi viral khabar nahi chuni gayi")
        return ""
    limit = 95 if F.short_lines() else 160
    story, src_text, hosts, links = None, "", [], []
    for c in cands:
        src_text, hosts, links = F.collect(c, heads, max_articles=3)
        if len(src_text) < 400:
            log("srot bahut kam (%d akshar) - agli khabar" % len(src_text))
            continue
        story = make_story(write_story(src_text), src_text, limit)
        if story:
            break
        log("is khabar ki kahani nahi bani - agli")
    if not story:
        return ""
    story = fit_parts(story, F.max_seconds())
    whole = " ".join(p["line_hi"] for p in story["parts"])
    story["tone"] = F.tones_for([{"headline_hi": story["headline_hi"], "line_hi": whole}])[0]

    title = story["youtube_title_hi"] or story["headline_hi"]
    desc = [story["headline_hi"], ""]
    desc += ["%s: %s" % (p["label"], p["line_hi"]) for p in story["parts"]]
    tags = ["Hindi News", "Shorts", "फटाफट ख़बर"] + story["tags"]
    plan = {"mode": "single", "story": story, "cta": F.CTA_HI, "slot": slot}
    row = {
        "story_id": sid, "beat": F.BEAT, "score": 19,
        "sources": ", ".join(hosts[:6]),
        "source_link": (links or [""])[0],
        "attribution_line": "स्रोत: " + " · ".join(hosts[:6]),
        "headline_hi": story["headline_hi"][:200],
        "headline_en": "Fatafat single-story reel",
        "lower_third_hi": story["headline_hi"][:60],
        "script_hi": " ".join([p["line_hi"] for p in story["parts"]] + [F.CTA_HI]),
        "yt_title": title[:85],
        "yt_description": "\n".join(desc),
        "tags": ", ".join(tags)[:480],
        "shots": json.dumps(plan, ensure_ascii=False),
    }
    st.add_story(row)
    F.note_used([{"headline_hi": story["headline_hi"]}])
    log("Reel ki script taiyar: %s - %s (%s, %d hisse: %s)" % (
        sid, story["headline_hi"][:40], story["tone"], len(story["parts"]),
        " > ".join(p["label"] for p in story["parts"])))
    return sid


def segments(plan):
    """EK-KHABAR plan -> tukde: har hissa ek 'item', phir CTA. Har hissa usi
    khabar ka - isliye ek hi tone, ek hi kicker; vyakti ki tasveer pehle
    hisse par (baaki par jagah/cheez ki)."""
    import sy_fatafat as F
    story = plan.get("story") or {}
    parts = story.get("parts") or []
    n = len(parts)
    tone = story.get("tone") or "neutral"
    segs = []
    for i, p in enumerate(parts):
        segs.append({"tag": "k%d" % i, "kind": "item", "index": i, "count": n,
                     "single": True, "badge": p["label"],
                     "text": p["line_hi"], "tone": tone,
                     "headline": p.get("card_hi") or p["label"],
                     "kicker": story.get("kicker_hi") or "",
                     "queries": p.get("photo_queries") or [],
                     "people": (story.get("people_en") or []) if i == 0 else []})
    segs.append({"tag": "cta", "kind": "cta", "index": n, "count": n, "single": True,
                 "text": plan.get("cta") or F.CTA_HI, "tone": F.CTA_TONE,
                 "headline": "सब्सक्राइब करें", "kicker": "सत्ययात्रा न्यूज़"})
    return segs

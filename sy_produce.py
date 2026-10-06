"""Ek pending khabar se ek taiyar video.

Kram: art direction -> tasveer/footage -> aawaaz -> video -> thumbnail ->
Telegram par approval ke liye.

Beech mein kuch toote to khabar 'failed' ho jaati hai aur wajah usi ke saath
likh di jaati hai - taaki baad mein dekha ja sake ki kya hua tha.
"""
import json
import os
import re
import shutil
import time

import render_core
import sy_config as cfg
import sy_ingest
import sy_media
import sy_scenes
import sy_endcard
import sy_store as st
import sy_telegram
import sy_tts
import thumb

M_HI = ['जनवरी', 'फ़रवरी', 'मार्च', 'अप्रैल', 'मई', 'जून', 'जुलाई', 'अगस्त',
        'सितंबर', 'अक्टूबर', 'नवंबर', 'दिसंबर']

SOURCE_NAMES = {
    "PTI": "PTI", "PRESS_TRUST_OF_INDIA": "PTI", "ANI": "ANI",
    "THE_HINDU": "The Hindu", "NDTV": "NDTV",
    "HINDUSTAN_TIMES": "Hindustan Times", "TIMES_OF_INDIA": "Times of India",
    "THE_INDIAN_EXPRESS": "The Indian Express", "SCROLL_IN": "Scroll.in",
    "PRESS_INFORMATION_BUREAU": "PIB", "AMAR_UJALA": "Amar Ujala",
    "NEWS18": "News18", "INDIA_TODAY": "India Today", "MINT": "Mint",
}


def log(*a):
    print("[produce]", *a, flush=True)


def pretty_source(slug):
    key = str(slug or "").strip().upper()
    key = "".join(ch if ch.isalnum() else "_" for ch in key).strip("_")
    if not key:
        return ""
    if key in SOURCE_NAMES:
        return SOURCE_NAMES[key]
    return " ".join(w[:1] + w[1:].lower() for w in key.split("_") if w)


def source_line(story):
    given = str(story.get("attribution_line") or "").strip()
    if given:
        return given
    names, seen = [], set()
    for raw in str(story.get("sources") or "").replace(";", ",").split(","):
        n = pretty_source(raw)
        if n and n not in seen:
            seen.add(n)
            names.append(n)
    return "स्रोत: " + (" · ".join(names) or "समाचार एजेंसी")


def date_hindi():
    t = time.localtime()
    return "%d %s %d" % (t.tm_mday, M_HI[t.tm_mon - 1], t.tm_year)


def build_job(story, shots=None, credits=None, cuts=None, timing=None):
    # voiceMap: aawaaz ki asli timing. Isse screen ka text aur peeche ka
    # drishya dono aawaaz ke saath chalte hain, akshar ginkar nahi.
    vm = dict(timing or {})
    if vm:
        vm["offset"] = render_core.LEAD
    return {
        # Reel 9:16 mein banti hai, bulletin 16:9 mein. Ye ek line poore
        # render ka naap aur roop tay karti hai (render_core.set_layout).
        "vertical": str(story.get("beat") or "") in REEL_BEATS,
        "shots": shots or [],
        "creditSpans": credits or [],
        "cuts": cuts or [],
        "voiceMap": vm,
        "jobId": story["story_id"],
        "lang": "hi",
        "headline": str(story.get("lower_third_hi")
                        or story.get("headline_hi") or "")[:140],
        "sourceLine": source_line(story),
        "dateStr": date_hindi(),
        "category": story.get("category") or "politics",
        "style": story.get("style") or "grid",
        "kicker": story.get("kicker") or "",
        "keyFact": story.get("key_fact") or "",
        "ghost": story.get("ghost") or "",
        "place": story.get("ghost") or "",
        "imageCredit": story.get("image_credit") or "",
        # Screen par neeche chalta rehne wala text - script hi hai.
        "ticker": str(story.get("script_hi") or "")[:420],
    }


# Akhbaar ka naam script mein Devanagari mein aata hai, slug mein nahi.
SOURCE_HI = {
    "AMAR_UJALA": "अमर उजाला", "AAJ_TAK": "आज तक",
    "DAINIK_JAGRAN": "दैनिक जागरण", "JAGRAN": "दैनिक जागरण",
    "LIVE_HINDUSTAN": "लाइव हिंदुस्तान", "HINDUSTAN_TIMES": "हिंदुस्तान टाइम्स",
    "NAVBHARAT_TIMES": "नवभारत टाइम्स", "TIMES_OF_INDIA": "टाइम्स ऑफ इंडिया",
    "THE_HINDU": "द हिंदू", "NDTV": "एनडीटीवी", "NEWS18": "न्यूज18",
    "INDIA_TODAY": "इंडिया टुडे", "THE_INDIAN_EXPRESS": "इंडियन एक्सप्रेस",
    "ANI": "एएनआई", "ANI_NEWS": "एएनआई",
    "PTI": "पीटीआई", "PRESS_TRUST_OF_INDIA": "पीटीआई",
    "PRESS_INFORMATION_BUREAU": "पीआईबी", "MINT": "मिंट",
    "SCROLL_IN": "स्क्रॉल", "BBC_HINDI": "बीबीसी",
}

# "<अखबार> के मुताबिक" / "के अनुसार" / "की रिपोर्ट के मुताबिक" / "के हवाले से"
_ATTR = r"\s*(की\s+रिपोर्ट\s+)?के\s+(मुताबिक|अनुसार|हवाले\s+से)\s*[,،]?\s*"

# Bina naam wala dhundhla zikr - "खबर के अनुसार", "रिपोर्ट के मुताबिक".
# Ye kuch batata hi nahi, sirf vaakya lamba karta hai.
_VAGUE = re.compile(r"(खबर|रिपोर्ट|समाचार|मीडिया\s+रिपोर्ट(ों)?)" + _ATTR)


def source_names_hi(story):
    """Is khabar ke akhbaaron ke Devanagari naam."""
    out = []
    for raw in str(story.get("sources") or "").replace(";", ",").split(","):
        key = "".join(ch if ch.isalnum() else "_"
                      for ch in str(raw).strip().upper()).strip("_")
        n = SOURCE_HI.get(key)
        if n and n not in out:
            out.append(n)
    return out


def tidy_attribution(story):
    """Script se baar-baar aane wala akhbaar ka naam hata do.

    NIRDESH KAAFI NAHI THA. Sampadak ke prompt mein likh dene se sirf NAYI
    script sudharti hai - jo script pehle likhi ja chuki hai wo database
    mein waisi hi padi rehti hai, aur video usi se banti hai. Katar mein
    solah khabrein thi, sab purani - isliye screen par kuch nahi badla.
    Wo baat maine pichhli baar saaf nahi kahi thi.

    Isliye ab ye kaam yahan hota hai, video banne se theek pehle - har
    khabar par, chahe wo kal likhi gayi ho ya aaj.

    Kya hatta hai: sirf AKHBAAR ka naam - "अमर उजाला के मुताबिक"।
    Kya BACHTA hai: har wo attribution jo asli hai - "नगर निगम के मुताबिक",
    "पुलिस के अनुसार", "डीआईजी ने कहा"। Wo hatana khabar ko kamzor karta,
    kyunki wahan ye batana zaroori hai ki baat kis ki hai.

    Aur aakhir mein ek line jud jaati hai: "इस खबर को <अखबार> ने रिपोर्ट
    किया है।" - ek baar, jahan uski jagah hai.
    """
    script = str(story.get("script_hi") or "").strip()
    if not script:
        return script, 0

    names = source_names_hi(story)
    removed = 0

    for n in names:
        # "<अखबार> के मुताबिक" / "की रिपोर्ट के अनुसार"
        script, k = re.compile(re.escape(n) + _ATTR).subn("", script)
        removed += k
        # "<अखबार> ने बताया कि" / "ने कहा कि" / "ने रिपोर्ट किया कि"
        script, k = re.compile(
            re.escape(n) + r"\s+ने\s+(बताया|कहा|लिखा|खबर\s+दी|रिपोर्ट\s+(किया|की))"
            r"\s+(है\s+)?कि\s+").subn("", script)
        removed += k

    script, k = _VAGUE.subn("", script)
    removed += k

    # Ab bhi naam kahin bacha hai to wo poora vaakya hi credit ka hai -
    # "इस खबर को अमर उजाला ने रिपोर्ट किया है।" jaisa. Upar wale kadam
    # tathya wale vaakyon se naam nikaal chuke hain, isliye jo bacha hai
    # use poora hata dena surakshit hai.
    if names:
        # Milaan space hata kar - script mein "आजतक" likha hota hai aur
        # hamari list mein "आज तक". Bina iske wo aakhri credit wali line
        # bach jaati thi; jaanch mein yahi pakda gaya.
        flat_names = [re.sub(r"\s+", "", n) for n in names]
        keep = []
        for part in re.split(r"(?<=।)\s*", script):
            flat = re.sub(r"\s+", "", part)
            if part.strip() and any(fn in flat for fn in flat_names):
                removed += 1
                continue
            keep.append(part)
        script = " ".join(p for p in keep if p.strip())

    # Safai: shuru mein bacha hua comma, dohre space, "। ," jaisa jod.
    script = re.sub(r"(^|।)\s*[,،]\s*", r"\1 ", script)
    script = re.sub(r"\s*,\s*,", ",", script)
    script = re.sub(r"[ \t]{2,}", " ", script).strip()

    # Aakhir mein koi credit ki line NAHI jodi jaati.
    #
    # Pehle yahan "इस खबर को <अखबार> ने रिपोर्ट किया है।" jud jaata tha aur
    # wo aawaaz mein bola bhi jaata tha. Ab akhbaar ka naam video mein
    # kahin nahi hai - na boli mein, na screen par.
    #
    # Shreya khatam nahi hui, jagah badli hai: sy_youtube.upload() har
    # video ke description mein attribution_line khud jodta hai. Wo code
    # se hota hai, sampadak ke likhe par nirbhar nahi - isliye chhootne ka
    # sawaal hi nahi.
    return script, removed


def attribution_count(story):
    """Script mein akhbaar ka naam kitni baar aaya.

    Sampadak ko kaha gaya hai ki naam sirf aakhiri vaakya mein ek baar aaye.
    Par ye ek nirdesh hai, taala nahi - isliye gin kar bata dete hain. Baar-
    baar "अमर उजाला के मुताबिक" bolne se bulletin aisa lagta hai jaise hum
    khud kuch nahi jaante, sirf kisi aur ki baat dohra rahe hain.
    """
    script = str(story.get("script_hi") or "")
    if not script:
        return 0, ""
    best, name = 0, ""
    for raw in str(story.get("sources") or "").replace(";", ",").split(","):
        n = pretty_source(raw)
        if len(n) < 3:
            continue
        # Angrezi naam script mein Devanagari mein aata hai, isliye
        # "के मुताबिक" jaise dhaanche bhi ginte hain.
        c = script.count(n)
        if c > best:
            best, name = c, n
    hits = len(re.findall(r"के\s+मुताबिक|के\s+अनुसार", script))
    if hits > best:
        best, name = hits, name or "स्रोत"
    return best, name


# Jin sources ki tasveer US CHEEZ ki hoti hai jiski khabar hai.
# Pexels/Pixabay isme nahi - wo prateekatmak hai, us ghatna ki nahi.
REAL_SOURCES = ("commons", "commons_video", "openverse")

# Ye beat khabar nahi hain, isliye inpar narmi hai.
#
# Farq soch ka hai, chhoot ka nahi. Khabar ye DAAWA karti hai ki jo dikh
# raha hai wo USI ghatna ka hai - wo daawa khokhla nikle to darshak turant
# pakad leta hai. "Aadhaar mein number kaise badlein" aisa koi daawa karti
# hi nahi; wahan ek aam daftar ya form imaandaar chitran hai, kisi gum
# saboot ki jagah bharna nahi. Uski keemat jaankari mein hai, tasveer mein
# nahi.
SOFT_BEATS = ("yojana", "kaam")

# Khabar par pehra ab pehle se SAKHT hai, aur uski wajah anupat hai.
#
# Jab paanch mein paanch video khabar thi, tab gate ko udaar rehna padta
# tha - warna channel chup ho jaata. Ab paanch mein sirf EK khabar chalni
# hai. Yaani hum chun sakte hain, aur chunna hi chahiye: jo ek khabar
# chale wo wahi ho jiska drishya sach mein maujood ho.
#
# Naya naap aapki apni 19 khabron par jaancha gaya hai:
#   - purana niyam (aadha bhara + 1 asli): 11 nikalti thi
#   - naya niyam (do-tihai bhara + 2 asli): 6 nikalti hain
# Chhah roz ke hisab se lagbhag ek hafte ki khabar - aur roz sirf ek
# khabar chahiye, isliye ye kaafi se zyada hai.
#
# Naya niyam wahi rokta hai jinpar aapne ungli rakhi thi (Saharanpur ki
# masjid - paanchon Pexels ke; Bhadohi ka saraafa - 0 asli; Bhadohi ki
# hockey - 3/6), aur wahi nikalta hai jo dikhne layak hai (MD factory 3
# asli, Ballia ke DM 3 asli, Kashi ki beti 2 asli).
KHABAR_BEATS = ("local", "news")

# Reel wale beat. In par do cheezein alag hoti hain: naap 9:16, aur drishya
# ka pehra bulletin jitna sakht nahi - Reel 45-60 second ki hoti hai aur
# usme 5-6 drishya nahi, 3-4 hi aate hain.
REEL_BEATS = ("bolly", "viral")

def sy_explainer_desc():
    return ("इस वीडियो की शुरुआत और अंत में दिखने वाली प्रस्तुतकर्ता AI-जनित "
            "है (कोई वास्तविक व्यक्ति नहीं)।")


# Shikshak wala andaaz (script aur aawaaz dono) - khabar ke alawa ye beat.
TEACHER_BEATS = ("yojana", "kaam", "gyan", "tech")


def visual_verdict(story, shots, photo_source=""):
    """Kya is khabar ko dikhaya ja sakta hai? (theek_hai, wajah, ek_line)

    SAKHT NIYAM, sirf khabar par: har video mein KAM SE KAM EK sacchi
    tasveer honi chahiye - us jagah ki, us sanstha ki, us cheez ki. Agar
    poore video mein sab kuch generic stock hai, to wo patrakarita nahi,
    sajaawat hai.

    Ye niyam aapki apni solah khabron par naap kar rakha gaya hai. Usse
    theek wahi saat rukti hain jinpar aapne ungli rakhi thi - shaheed ki
    maa (0 drishya), Bhadohi ki chori (0 asli), Saharanpur ki masjid
    (paanchon Pexels ke).
    """
    beat = str(story.get("beat") or "")
    n = len(shots or [])
    if n:
        # Anchor jo line khud bolegi, wo tukda bhi bhara hua ginte hain
        # (asli nahi - "real" mein nahi judta).
        filled = sum(1 for s in shots if s.get("file") or s.get("anchor_planned"))
        real = sum(1 for s in shots if s.get("source") in REAL_SOURCES)
    else:
        # Shot list bani hi nahi - ek hi tasveer wala purana rasta.
        filled = 1 if photo_source else 0
        real = 1 if photo_source in REAL_SOURCES else 0
        n = 1

    line = "%d/%d drishya, %d asli" % (filled, n, real)

    if beat in SOFT_BEATS:
        return True, "", line

    if beat in REEL_BEATS:
        # Reel par: aadha bhara aur kam se kam ek sacchi tasveer. Bollywood
        # par ye lagbhag hamesha mil jaati hai - har jaane-mane abhineta ki
        # muft licence wali tasveer Wikipedia par hoti hai (portrait()).
        if filled < (n + 1) // 2:
            return False, "%d/%d drishya hi mile - aadhe se kam" % (filled, n), line
        if real < 1:
            return False, "ek bhi SACCHI tasveer nahi", line
        return True, "", line

    if beat in KHABAR_BEATS:
        # Do-tihai drishya bhare hue, aur kam se kam do sacchi tasveerein.
        need = -(-2 * n // 3)
        need_real = 2 if n >= 4 else 1
        short = "do-tihai se kam"
    else:
        # gyan aur baaki: aadha bhara, ek asli. Ye khabar nahi hai, par
        # itihas aur bhugol par Commons udaar hai - isliye chhoot bhi nahi.
        need = (n + 1) // 2
        need_real = 1
        short = "aadhe se kam"

    if filled < need:
        return False, "%d/%d drishya hi mile - %s" % (filled, n, short), line
    if real < need_real:
        return False, ("sacchi tasveerein sirf %d - kam se kam %d chahiye"
                       % (real, need_real)), line
    return True, "", line


def asked_by_you(story_id):
    """/khabar se aapki maangi khabar? (sy_main.do_khabar "mera_" id deta hai)"""
    return str(story_id or "").startswith("mera_")


def produce(story):
    """Ek khabar ko video bana kar Telegram par bhej do. True/False."""
    sid = story["story_id"]
    cfg.ensure_dirs()
    cfg.put_ffmpeg_on_path()

    workdir = os.path.join(cfg.WORK_ROOT, sid)
    # Har baar saaf shuruaat. Pichhli adhoori koshish ki clip.mp4 ya
    # photo.jpg padi reh jaye to wo is khabar ke peeche chal jaayegi.
    if os.path.isdir(workdir):
        shutil.rmtree(workdir, ignore_errors=True)
    os.makedirs(workdir)

    st.update(sid, status="producing", error="")
    # Pichhli khabar beech mein gir gayi ho to bhi title card wapas.
    render_core.set_intro_mode(False)
    try:
        # BADE TABKE KA KAAM - sirf khabar/local par, sirf isliye ki
        # "random, kam kaam ki khabar" ki shikayat yahi thi. Gyan/kaam/
        # yojana/Reel/bulletin ko ye nahi chhoota - bulletin apni hi
        # sampadak-jaanch (sy_bulletin.py niyam 7) se guzarti hai, aur
        # baaki par ye shikayat thi hi nahi.
        # /khabar se aapki maangi khabar ("mera_") par ahmiyat ki ye
        # jaanch nahi lagti - wo faisla aap le chuke hain.
        if str(story.get("beat") or "") in ("local", "news") \
                and not asked_by_you(sid):
            ok_reach, why_reach = sy_ingest.audience_relevant(
                story.get("headline_hi"), story.get("script_hi"))
            if not ok_reach:
                log("ROKA (kam kaam ki) -", why_reach)
                st.update(sid, status="low_reach", error=why_reach)
                sy_telegram.send_message(
                    "<b>Ye khabar nahi banayi - bade tabke ke kaam ki nahi lagi</b>\n\n"
                    + sy_telegram._esc(story.get("headline_hi") or "")
                    + "\n\n<b>Wajah:</b> " + sy_telegram._esc(why_reach)
                    + "\n\nAgli khabar turant aazma li jaayegi.")
                return False

        if not story.get("category"):
            log("art direction...")
            ad = sy_media.art_direction(story)
            st.update(sid, **ad)
            story.update(ad)

        # Script ko drishyon mein todo. Pehle poore video par ek hi tasveer
        # padi rehti thi - wo television nahi, radio tha. Ab har baat ka
        # apna drishya hai aur wo baat badalne par badalta hai.
        if not story.get("shots"):
            log("shot list...")
            shots = sy_media.shot_list(story)
            # Khaali ho to darj nahi karte. Warna ek baar ki nakaami hamesha
            # ke liye chipak jaati aur ye khabar dobara koshish kiye bina
            # purane ek-tasveer wale raste par hi rehti.
            if shots:
                story["shots"] = json.dumps(shots, ensure_ascii=False)
                st.update(sid, shots=story["shots"])

        # Jaankari video mein jin tukdon ka asli drishya na mile, unmein se
        # kuch anchor khud bolegi (sy_explainer) - unpar AI chitran ka paisa
        # nahi lagta, sirf nishan lagta hai.
        #
        # HEYGEN (Oct 2026): lip-sync wali anchor chalu ho to wahi in tukdon
        # ko bolti hai (sy_heygen/sy_edit) - Veo wala explainer anchor tab
        # is video mein nahi lagta (ek video, ek chehra).
        hg_ok = False
        try:
            import sy_heygen
            hg_ok, hg_why = sy_heygen.ready(
                story, vertical=str(story.get("beat") or "") in REEL_BEATS)
            if not hg_ok:
                log("HeyGen anchor nahi:", hg_why)
        except Exception as e:
            log("HeyGen jaanch mein gadbad:", e)
        try:
            if hg_ok:
                slots = sy_heygen.line_slots(story)
            else:
                import sy_explainer
                slots = sy_explainer.line_slots(story)
        except Exception:
            slots = 0
        shots = sy_media.fetch_shots(story, workdir, anchor_slots=slots)
        thumb_is_ai = False
        if shots:
            tsh = sy_media.thumb_art(shots, workdir, story)
            credit = next((s.get("credit") for s in shots if s.get("credit")), "")
            source = next((s.get("source") for s in shots if s.get("source")), "")
            # thumb_art() usi pehle shot ko thumbnail banata hai jismein
            # file ho - yahin, ABHI, pakad lete hain ki wo Veo ka AI-chitran
            # tha ya nahi. Neeche 'shots' scene-building fail hone par
            # khaali ho sakta hai, isliye wahan se pata karna der ho jaati.
            # thumb_art ab vishay wala shot bhi chun sakta hai (pehla nahi
            # zaroori) - isliye jo shot SACH MEIN chuna gaya, usi se.
            thumb_is_ai = isinstance(tsh, dict) and tsh.get("source") == "veo"
        else:
            # Ek bhi drishya nahi mila - purana rasta, ek hi tasveer.
            log("shot-dar-shot kuch nahi mila, ek tasveer par aa rahe hain")
            credit, source = sy_media.fetch_media(story, workdir)
        st.update(sid, image_credit=credit, photo_source=source)
        story["image_credit"] = credit
        story["photo_source"] = source

        # AI-CHITRAN KA GHOSHNA - ab khabar/bulletin bhi Veo istemal kar
        # sakte hain (sy_veo.py, Sep 2026 se), isliye screen ke "AI चित्रण"
        # label ke saath-saath description mein bhi saaf likha rehta hai.
        # Sirf tab jab is video mein sach mein koi AI-bana shot laga ho.
        if shots and any(s.get("source") == "veo" for s in shots):
            ai_line = ("इस वीडियो में कुछ दृश्यों के लिए वास्तविक तस्वीर/फुटेज न "
                       "मिलने पर AI-जनित चित्रण इस्तेमाल किया गया है।")
            desc = str(story.get("yt_description") or "").strip()
            if ai_line not in desc:
                desc = (desc + "\n\n" + ai_line).strip()
                story["yt_description"] = desc
                st.update(sid, yt_description=desc)

        # YAHIN ROKTE HAIN - aawaaz banne se PEHLE.
        #
        # Ab tak system ek hi taraf chalta tha: sampadak tay karta tha ki
        # kya dikhna chahiye, khoj wo laa nahi paati thi, aur video phir
        # bhi ban jaati thi - jo mila usi se. Yaani yojana kagaz par banti
        # thi aur screen par upalabdhta chalti thi.
        #
        # Ye wahi kadam hai jo beech mein tha hi nahi: jo mila, usse ye
        # khabar kahi ja sakti hai ya nahi. Nahi ja sakti to video banti
        # hi nahi - aawaaz ka paisa bhi bachta hai aur wo video aapko
        # dekhni bhi nahi padti jo aap waise bhi reject karte.
        ok, why, vline = visual_verdict(story, shots, source)
        log("drishya:", vline)
        if not ok and asked_by_you(sid):
            # Aapki maangi khabar tasveer kam hone par bhi banti hai -
            # khaali jagah studio/graphics bharte hain.
            log("drishya kam (%s) - par aapki maangi khabar hai, ban rahi hai" % why)
            ok = True
        if not ok:
            log("ROKA -", why)
            st.update(sid, status="no_visual", error=why)
            sy_telegram.send_message(
                "<b>Ye khabar nahi banayi</b>\n\n"
                + sy_telegram._esc(story.get("headline_hi") or "")
                + "\n\n<b>Wajah:</b> " + sy_telegram._esc(why)
                + "\n\nKhabar wahi chalti hai jise theek se dikhaya ja sake.")
            return False
        story["visual_line"] = vline

        # Akhbaar ka naam script mein se hata do - aawaaz banne se PEHLE,
        # kyunki wahi script boli bhi jaati hai aur screen par bhi dikhti
        # hai. Saaf ki hui script database mein bhi likh dete hain, taaki
        # Telegram par bheji gayi jaankari aur video ek jaisi rahein.
        clean, removed = tidy_attribution(story)
        if clean and clean != story.get("script_hi"):
            story["script_hi"] = clean
            st.update(sid, script_hi=clean)
            log("script se akhbaar ka naam %d jagah se hataya, "
                "ek baar aakhir mein rakha" % removed)

        log("aawaaz...")
        # Khabar ke alawa sab (yojana/kaam/gyan/tech) shikshak ke andaaz mein
        # - script sy_ingest.TEACHER_STYLE se, aur aawaaz bhi thodi thehri.
        style = "teacher" if str(story.get("beat") or "") in TEACHER_BEATS else ""
        _vp, timing = sy_tts.speak(story["script_hi"], workdir, style)
        secs = sy_tts.duration(os.path.join(workdir, "voice.wav"))

        # JAANKARI WALI VIDEO KA ANCHOR - render se PEHLE, taaki render ko
        # pata ho ki aage anchor judegi: tab channel ka title card nahi
        # lagta aur aawaaz lagbhag turant shuru hoti hai. Pehle anchor ke
        # "namaste" aur asli baat ke beech 4 second ka card aata tha -
        # Harshvardhan ne kaha wo khabar se kaat deta hai.
        prep = None
        try:
            import sy_explainer
            if not hg_ok:
                prep = sy_explainer.prepare(story, workdir)
        except Exception as e:
            log("explainer anchor mein gadbad (bina uske aage):", e)
        render_core.set_intro_mode(bool(prep))
        if prep:
            prep["lead"] = render_core.LEAD

        # Ab jaakar lambai pata chali, aur tabhi tay ho sakta hai ki kaun sa
        # drishya kab tak chalega. Isi wajah se ye kadam aawaaz ke BAAD hai.
        total_len = render_core.LEAD + secs + render_core.END_SECONDS
        credits, cuts = [], []
        hg_plan = None
        if shots:
            # LEAD se - kyunki drishya us baat par badalna chahiye jispar
            # AAWAAZ hai, aur aawaaz LEAD par shuru hoti hai. Pehle wale
            # do second ka lead sy_scenes.build khud pehle drishya mein
            # jod deta hai, isliye peechhe ki screen kabhi khaali nahi.
            sy_scenes.plan(shots, render_core.LEAD,
                           total_len - render_core.END_SECONDS, timing)
            # EDIT DECISION + HeyGen ko aawaaz - samay ab pakka hai, aur
            # drishya kahan mila ye bhi. HeyGen apna video build() ke dauran
            # banata hai; render se theek pehle utha lete hain (finish).
            if hg_ok:
                hg_plan = sy_heygen.plan(story, shots, workdir, render_core.LEAD)
            cuts = sy_scenes.build(shots, total_len, workdir)
            if cuts:
                credits = sy_scenes.credit_spans(shots)
                story["shots"] = json.dumps(shots, ensure_ascii=False)
                story["shot_summary"] = sy_scenes.describe(shots)
                st.update(sid, shots=story["shots"])
                log("\n" + story["shot_summary"])
            else:
                shots = []

        log("video...")
        out = os.path.join(cfg.OUTPUT_DIR, sid + "_hi.mp4")
        job = build_job(story, shots, credits, cuts, timing)
        # Ek bhi drishya na mile to render_core peeche studio chalata hai
        # (designed backdrop ki jagah) - sy_scenes.studio_path() dekhiye.
        job["studio_bg"] = sy_scenes.studio_path()
        # Aakhir mein alag se like/subscribe/share end-card judega (neeche,
        # sy_endcard) - tab render ke apne end card par wahi line dobara
        # likhne ki zaroorat nahi, sirf channel ka naam.
        job["endcard"] = sy_endcard.enabled()
        # HeyGen anchor ki khidkiyan (full/PIP). Taiyaar na ho / fail ho to
        # [] - video bina anchor ke, pehle jaisi.
        hg_overlays = sy_heygen.finish(hg_plan, workdir) if (hg_plan and cuts) else []
        if hg_overlays:
            job["anchorOverlays"] = hg_overlays
            job["creditSpans"] = sy_heygen.adjust_credits(credits, hg_overlays)
            # Jaankari video ki thumbnail par wahi anchor (explainer jaisa).
            if str(story.get("beat") or "") in TEACHER_BEATS:
                try:
                    import sy_explainer
                    hclip = hg_overlays[0]["file"]
                    sy_explainer.thumb_still(
                        hclip, sy_endcard._duration(hclip) / 2.0, workdir)
                except Exception as e:
                    log("thumbnail ke liye anchor ki tasveer nahi:", e)
        try:
            render_core.render(job, workdir, out)
        finally:
            # Agli khabar par title card phir se (set_intro_mode dekhiye).
            render_core.set_intro_mode(False)
            if hg_plan:
                sy_heygen.cleanup(workdir)
        if not os.path.exists(out) or os.path.getsize(out) < 100000:
            raise RuntimeError("video bani hi nahi")

        # AI ANCHOR - sirf bulletin par, aur sirf yahan se aage kuch bhi
        # gadbad ho to bina anchor ke wahi purani video chali jaati hai.
        # sy_anchor.py poori tarah alag file hai; iske bina bhi ye poora
        # rasta waisa hi chalta hai jaisa pehle chalta tha.
        # HeyGen anchor lag chuki ho to ye alag (3D) anchor nahi - ek video,
        # ek chehra.
        if str(story.get("beat") or "") == "bulletin" and not hg_overlays:
            try:
                import sy_anchor
                out = sy_anchor.wrap(story, out, workdir)
            except Exception as e:
                log("anchor jodne mein gadbad (bina anchor ke aage badh rahe hain):", e)

        # LIKE / SUBSCRIBE / SHARE - har video ke bilkul ant mein (anchor
        # ke outro ke baad bhi). sy_endcard.append() kabhi throw nahi karta;
        # kuch gadbad ho to video bina end-card ke hi aage jaati hai.
        # JAANKARI WALI VIDEO (yojana/kaam/gyan/tech) - shuru mein AI anchor
        # vishay kholti hai, aur ant mein wahi (usi clip se) like/subscribe
        # kehti hai - ek video mein ek hi chehra. sy_explainer.py dekhiye.
        # Na bane to "" - aur end-card pehle ki tarah roz wali presenter se.
        anchor_outro = ""
        try:
            import sy_explainer
            anchor_outro = sy_explainer.attach(story, out, workdir, prep)
        except Exception as e:
            log("explainer anchor mein gadbad (bina uske aage):", e)

        out, presenter_used = sy_endcard.append(story, out, workdir,
                                                presenter_override=anchor_outro)
        if presenter_used or anchor_outro or hg_overlays:
            desc = str(story.get("yt_description") or "").strip()
            line = (sy_heygen.desc_line() if hg_overlays else
                    sy_explainer_desc() if anchor_outro else sy_endcard.DESC_LINE)
            if line not in desc:
                desc = (desc + "\n\n" + line).strip()
                story["yt_description"] = desc
                st.update(sid, yt_description=desc)

        thumb_path = os.path.join(cfg.OUTPUT_DIR, sid + "_hi.jpg")
        art = os.path.join(workdir, "photo.jpg")
        ok, why = thumb.build(
            thumb_path,
            text=story.get("thumb_text") or story.get("key_fact") or "",
            place=story.get("ghost") or "",
            keyword=story.get("kicker") or "",
            art_path=art if os.path.exists(art) else "",
            style=story.get("thumb_style") or "slab",
            # AI ka label ab chalu hai - is system mein ab do tarah se AI
            # tasveer aa sakti hai: khud thumb.py ka Vertex-bana backdrop
            # (koi sacchi tasveer na milne par), ya upar wala art_is_ai
            # (Veo chitran ka frame). Dono jagah thumb.py khud sahi label
            # lagata hai; asli photo/footage par kabhi nahi lagta.
            ai_label=True,
            art_is_ai=thumb_is_ai,
            # Jaankari video mein anchor laga ho to thumbnail par bhi wahi.
            anchor_path=(os.path.join(workdir, "anchor_thumb.jpg")
                         if (anchor_outro or hg_overlays) and os.path.exists(
                             os.path.join(workdir, "anchor_thumb.jpg")) else ""),
            workdir=workdir,
            category=story.get("category") or "politics",
            backdrop_style=story.get("style") or "grid",
            entity=story.get("thumb_entity") or "",
            # Reel khadi hai to uski thumbnail bhi khadi. YouTube khadi
            # video par 16:9 wali thumbnail rakhta hi nahi - wo use hata
            # kar apni kaati hui laga deta hai.
            vertical=str(story.get("beat") or "") in REEL_BEATS)
        if not ok:
            log("thumbnail nahi bani:", why)
            thumb_path = ""

        total = render_core.LEAD + secs + render_core.END_SECONDS
        try:
            total = sy_endcard._duration(out) or total
        except Exception:
            pass
        st.update(sid, video_path=out, thumb_path=thumb_path, seconds=total)
        story["seconds"] = total

        log("Telegram par bhej rahe hain (%.1f MB)"
            % (os.path.getsize(out) / 1048576.0))
        mid = sy_telegram.send_video_for_approval(story, out, thumb_path)
        st.update(sid, status="awaiting", tg_message_id=mid)
        log("approval ka intezaar:", sid)
        return True

    except Exception as e:
        log("GADBAD:", e)
        st.update(sid, status="failed", error=str(e)[:400])
        try:
            sy_telegram.send_message(
                "<b>Video nahi ban payi</b>\n\n"
                + sy_telegram._esc(story.get("headline_hi") or "")
                + "\n\n<b>Wajah:</b>\n" + sy_telegram._esc(str(e))[:600])
        except Exception:
            pass
        return False


if __name__ == "__main__":
    s = st.next_pending()
    if not s:
        print("koi pending khabar nahi hai")
    else:
        produce(s)

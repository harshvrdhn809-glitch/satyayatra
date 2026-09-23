"""Ek-kahani-ek-video ki jagah - din ki das zaroori khabrein, ek bulletin mein.

KYUN
====
Har khabar ke liye alag video banane mein do dikkatein thi: din bhar mein
jitni khabrein chalti hain unka bahut chhota hissa hi channel par aa paata
tha (upload ka kota seemit hai), aur aajkal darshak ka dhyaan itna chhota
ho gaya hai ki wo lambi khoj-khabar se zyada "kam waqt mein zyada cheezein"
wala format pasand karta hai.

Isliye ye teen roz ke bulletin - Mirzapur, Prayagraj, poora UP - shaam ko
ek-ek ghante ke antaral par. Har bulletin mein das chhoti khabrein, har ek
10-15 second ki. Poora bulletin EK video hai aur EK hi Telegram approval
maangta hai - alag-alag khabar ki tarah das baar poochha nahi jaata.

KAISE
=====
Ye render pipeline (sy_produce, sy_media, sy_scenes, render_core, thumb)
ko BILKUL NAHI chhedta. Bulletin bhi ek "story" row hi hai - bas uski
script_hi mein das khabrein ek ke baad ek jud jaati hain. Baaki sab
(art_direction, shot_list, aawaaz, video, thumbnail, Telegram approval,
YouTube upload, Facebook) wahi purana rasta hai jo ek khabar ke liye
banaya gaya tha - kyunki wo kisi khabar ki lambai ya ginti ki parwah
nahi karta, sirf script aur shots dekhta hai.

FOOTAGE KA NIYAM YAHAN HALKA HAI - JAAN-BOOJHKAR
=================================================
Beat ka naam "bulletin" hai, aur ye SOFT_BEATS/REEL_BEATS/KHABAR_BEATS
kisi mein nahi (sy_produce.py). Isliye visual_verdict() use apne aap
gyan/kaam wale halke niyam se naapta hai - aadha drishya bhara, ek sacchi
tasveer kaafi. Das khabron mein se har ek par sakht do-sacchi-tasveer
wala niyam lagane se aadhi khabrein chhoot jaatin. Ek video mein kam se
kam ek sacchi tasveer honi chahiye - itna kaafi hai.
"""
import re
import time

import sy_ai
import sy_config as cfg
import sy_ingest
import sy_net
import sy_store as st

AREAS = {
    "mirzapur": {"label": "मिर्ज़ापुर", "cities": ("मिर्ज़ापुर",)},
    "prayagraj": {"label": "प्रयागराज", "cities": ("प्रयागराज",)},
    "up": {
        "label": "उत्तर प्रदेश",
        # Poore UP ka bulletin - saare zilon ka mila-jula.
        "cities": ("प्रयागराज", "वाराणसी", "मिर्ज़ापुर", "भदोही", "लखनऊ",
                   "उत्तर प्रदेश"),
    },
}

WORDS = ("पहली", "दूसरी", "तीसरी", "चौथी", "पांचवीं", "छठी", "सातवीं",
         "आठवीं", "नौवीं", "दसवीं")


def log(*a):
    print("[bulletin]", *a, flush=True)


# ----------------------------------------------------------- settings

def enabled():
    on = st.kv_get("bulletin_on")
    if on is not None:
        return bool(on)
    return cfg.num("bulletin", "enabled", 0) == 1


def set_enabled(on):
    st.kv_set("bulletin_on", 1 if on else 0)


def want_items():
    return int(cfg.num("bulletin", "items", 10))


def hour_for(area):
    return int(cfg.num("bulletin", "hour_" + area, 0) or 0)


def _today():
    return time.strftime("%Y-%m-%d")


def due(area):
    """Aaj is area ka bulletin abhi tak nahi bana, aur uska waqt ho gaya?"""
    hour = hour_for(area)
    if hour <= 0:
        return False
    if int(time.strftime("%H")) < hour:
        return False
    return st.kv_get("bulletin_done_" + area, "") != _today()


def mark_done(area):
    st.kv_set("bulletin_done_" + area, _today())


# ------------------------------------------------------- khabrein chunna

def _candidates(area):
    """Is area ki aaj ki khabrein - Amar Ujala ke zila RSS se seedhe.

    normalise() poore desh ki feed padhta hai; hum usmein se sirf apne
    shehron ka hissa lete hain. Ek hi ghatna do baar na aaye isliye
    same_story() se aapas mein bhi chhaanti hoti hai.
    """
    cities = set(AREAS[area]["cities"])
    try:
        rows = [r for r in sy_ingest.normalise()
                if r.get("scope") == "local" and r.get("city") in cities]
    except Exception as e:
        log("khabrein nahi mil paayin:", e)
        return []

    # Naye pehle.
    rows.sort(key=lambda r: (r.get("age_hours") if r.get("age_hours")
                             is not None else 999))

    out = []
    for r in rows:
        title = str(r.get("title") or "")
        if any(sy_ingest.same_story(title, o["title"]) for o in out):
            continue
        out.append(r)
        if len(out) >= 20:   # AI ko chunne ke liye thoda zyada dete hain
            break
    return out


# PEHLE YAHAN EK KAMI THI: line_hi sirf shirshak ka Hindi mein dobara
# kahaa hua roop ban jaata tha - "Mirzapur mein sadak durghatna, do
# ghayal" jaisa, jabki neeche diya summary usmein KAHAN (Chunar kasbe
# mein, NH-35 par), KAB, KISKE BEECH (truck aur bike) aur AAGE KYA HUA
# (dono Ramnagar hospital mein bharti) jaisi thos jaankari rakhta tha.
# Prompt mein summary diya to zaroor jaata tha, par use MINE karne ka
# saaf hukum nahi tha - isliye model aksar sirf shirshak dohra deta tha,
# summary ki tafseel chhod deta tha. Ab niyam 4 isi ko seedha kehta hai,
# aur ek GALAT/SAHI udaharan bhi diya hai taaki farq saaf rahe.
BULLETIN_SYSTEM = "\n".join([
    'Aap ek Hindi news channel ke bulletin editor hain. Aapke saamne aaj '
    'ki das-baarah khabron ke shirshak aur summary hain. Aapko inmein se '
    'sabse zaroori chuni gayi khabron ka ek TEZ-RAFTAR bulletin banana hai '
    '- har khabar sirf ek vaakya mein, par us vaakya mein khabar ka asli '
    'tathya hona chahiye, sirf shirshak ka tarjuma nahi.',
    '',
    'HARD RULES:',
    '1. Sirf wahi likhiye jo diye gaye shirshak/summary mein hai. Koi '
    'number, naam ya tafseel khud se mat jodiye.',
    '2. Jis khabar ka summary itna chhota ya adhoora ho ki ek theek '
    'vaakya na bane, use chhod dijiye - bharti mat kijiye.',
    '3. Akhbaar ka naam (Amar Ujala) kisi bhi line mein kahin nahi aana '
    'chahiye - wo sirf credit mein jaata hai.',
    '4. line_hi SIRF shirshak ka Hindi mein dobara kahaa hua roop NAHI '
    'hona chahiye - summary mein jo bhi thos tathya maujood hon, unhe '
    'zaroor shaamil kijiye: KAHAN (jagah/sthaan/mohalla/sadak), KAB '
    '(din/tareekh/samay), KYA HUA (mukhya ghatna ya kaam), KAUN/KISKE '
    'BEECH (vyakti, sanstha, dono paksh, kiske saath), aur AAGE KYA HUA '
    '(giraftari, ilaaj, jaanch, faisla, muaavza, aankde) - in mein se JO '
    'BHI summary mein saaf likha ho, use ek hi vaakya mein piroiye. '
    'GALAT (sirf shirshak): "मिर्ज़ापुर में सड़क दुर्घटना, दो घायल।" SAHI '
    '(summary ki tafseel ke saath): "मिर्ज़ापुर के चुनार में एनएच-35 पर '
    'ट्रक-बाइक भिड़ंत में दो घायल, दोनों रामनगर अस्पताल में भर्ती।" Summary '
    'mein itni tafseel na ho to jo thos jaankari maujood hai wahi '
    'shaamil kijiye - khud se mat banaiye (niyam 1 yaad rakhiye).',
    '5. line_hi bolne layak Hindi mein ho, 14 se 22 shabd, ek hi vaakya - '
    'yaad rahe ise ek synthetic anchor tez raftaar mein padhega.',
    '6. Sabse badi/zaroori khabar sabse pehle rakhiye.',
    '7. CHUNAV KISKA KAAM KA HAI - is par bhi. Diye gaye 10-20 mein se sirf '
    'utni hi khabrein chuniye jo BADE TABKE (poore ilaake/shehar ke aam '
    'log) ke kaam ki hon - paisa, suraksha, sehat, mausam/baarish, sadak/'
    'traffic, bijli-pani, shiksha/pariksha, sarkari yojana/aadesh, bada '
    'hadsa ya apradh, chunav/prashasan. Aisi khabar jo sirf EK ghar/EK '
    'vyakti ki nitaant niji baat ho aur uska asar aur kisi par na padta ho '
    '(chhoti aapasi kahasuni, mamuli chori, ek-do logon ka jhagda) use '
    'tab tak mat chuniye jab tak uski wajah ya nateeja sach mein bade '
    'tabke ko chhue - sirf "khabar aayi hai" isliye nahi. Shak ho to us '
    'khabar ko chhod kar koi aisi khabar chuniye jiska asar zyada logon '
    'par ho.',
    '',
    'Sirf JSON lautaiye, in exact keys ke saath:',
    '{"items": [{"headline_hi": "40 akshar tak", '
    '"line_hi": "ek vaakya, 14-22 shabd, thos tathya sahit", '
    '"tags": ["1-2 keyword"]}],',
    ' "youtube_title_hi": "90 akshar tak",',
    ' "youtube_description_hi": "har khabar ki ek line, alag-alag"}',
])


def _draft(area, rows):
    label = AREAS[area]["label"]
    lines = []
    for i, r in enumerate(rows, 1):
        lines.append("%d. %s" % (i, r["title"]))
        if r.get("summary"):
            # 220 se 420 kiya - itni chhoti summary mein aksar KAHAN/KAB/
            # KISKE-SAATH jaisi tafseel beech mein hi kat jaati thi, aur
            # model ke paas sirf shirshak bacha rehta tha.
            lines.append("   Summary: " + r["summary"][:420])
    user = "\n".join([
        "ILAAKA: " + label, "",
        "AAJ KI KHABREIN (shirshak + summary):", "\n".join(lines), "",
        "Inmein se zyada se zyada %d chuniye, sabse zaroori pehle. Har "
        "chuni gayi khabar ke line_hi mein uske SUMMARY se thos tathya "
        "(kahan/kab/kiske beech/aage kya hua) zaroor shaamil kijiye."
        % want_items(),
    ])
    return sy_ai.ask_json(BULLETIN_SYSTEM, user, max_tokens=2500)


def intro_line(area):
    return "नमस्कार, देखिए %s की आज की ज़रूरी ख़बरें।" % AREAS[area]["label"]


def outro_line(area):
    return ("ये थीं %s की आज की अहम ख़बरें। सत्ययात्रा न्यूज़ पर बने रहिए।"
            % AREAS[area]["label"])


def _script(area, items, skip_intro_outro=False):
    """skip_intro_outro=True jab AI anchor khud ye do line bolega (sirf
    tab jab sy_anchor.should_narrate_wrap() haan kahe) - taaki wahi baat
    ek video mein do alag aawazon se do baar na sunayi de."""
    parts = [] if skip_intro_outro else [intro_line(area)]
    for i, it in enumerate(items):
        word = WORDS[i] if i < len(WORDS) else str(i + 1) + "वीं"
        parts.append("%s ख़बर। %s" % (word, it["line_hi"]))
    if not skip_intro_outro:
        parts.append(outro_line(area))
    return " ".join(parts)


def build(area):
    """Is area ka bulletin banao aur queue mein daal do. story_id ya ""."""
    if area not in AREAS:
        return ""

    rows = _candidates(area)
    if len(rows) < 3:
        log(area, "- aaj ki khabrein bahut kam hain (%d), chhod rahe hain"
            % len(rows))
        return ""

    j = _draft(area, rows)
    items = [it for it in ((j or {}).get("items") or [])
             if isinstance(it, dict) and len(str(it.get("line_hi") or "")) > 15]
    if len(items) < 3:
        log(area, "- sampadak ne kaafi khabrein nahi chunin")
        return ""
    items = items[:want_items()]

    label = AREAS[area]["label"]
    sid = "bltn_%s_%s" % (area, time.strftime("%Y%m%d"))
    if st.get(sid):
        return ""   # aaj is area ka bulletin pehle se bana hua hai

    try:
        import sy_anchor
        anchor_will_speak = sy_anchor.should_narrate_wrap()
    except Exception as e:
        log("sy_anchor jaanchi nahi gayi (bina anchor ke maan rahe hain):", e)
        anchor_will_speak = False
    script = _script(area, items, skip_intro_outro=anchor_will_speak)
    tags = []
    for it in items:
        for t in (it.get("tags") or [])[:2]:
            t = str(t or "").strip()
            if t and t not in tags:
                tags.append(t)
    tags = tags[:12]

    desc_lines = [str(j.get("youtube_description_hi") or "").strip()]
    desc_lines += ["", "आज की " + label + " की ज़रूरी ख़बरें एक बुलेटिन में।",
                   "", "स्रोत: अमर उजाला",
                   "यह वीडियो समाचार एजेंसी feeds से तैयार किया गया है।"]
    if anchor_will_speak:
        # Saaf disclosure - jab bhi anchor bol raha ho, description mein
        # saaf likha rahe ki ye ek AI se bana digital presenter hai.
        desc_lines += ["", "इस वीडियो में शुरुआत और अंत में एक AI-जनित "
                       "डिजिटल एंकर का इस्तेमाल किया गया है।"]

    row = {
        "story_id": sid,
        "beat": "bulletin",
        "score": 18,
        "sources": "AMAR_UJALA",
        "headline_hi": (label + " की आज की ज़रूरी ख़बरें")[:200],
        "headline_en": area.title() + " top news bulletin",
        "lower_third_hi": (label + " की आज की खबरें")[:60],
        "script_hi": script,
        "yt_title": (str(j.get("youtube_title_hi") or "")
                    or (label + " की आज की ज़रूरी ख़बरें"))[:95],
        "yt_description": "\n".join(l for l in desc_lines if l),
        "tags": ", ".join(tags)[:480],
    }
    st.add_story(row)
    # Chuni gayi khabrein "dekhi hui" chinh dete hain - taaki run_news()
    # inhi khabron ko dobara akeli khabar ki tarah na utha le.
    for r in rows[:len(items)]:
        st.mark_seen(r["story_id"])
        st.remember_title(r["title"])
    log(area, "- bulletin taiyar,", len(items), "khabrein:", sid)
    return sid

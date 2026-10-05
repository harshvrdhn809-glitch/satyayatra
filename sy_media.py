"""Video ka roop tay karna, aur uske liye tasveer ya chalti footage laana.

Do kaam:
  art_direction(story)     - picture editor se poochho: kya dikhna chahiye
  fetch_media(story, dir)  - wo cheez dhoondh kar workdir mein rakh do

Kram jaan-boojhkar hai. Prasiddh vyakti ki khabar par pehle Commons aur
Openverse - wahan unki asli, licence wali tasveer milti hai. Baaki khabron
par pehle chalti hui footage, phir tasveer. Kuch na mile to designed
backdrop - jo galat tasveer se hamesha behtar hai.
"""
import json
import os
import re
import shutil
import subprocess

import sy_ai
import sy_config as cfg
import sy_net
import sy_store as st

MAX_CLIP_MB = 60

# Ek shot par hum zyada se zyada itni tasveerein/frame Claude ko dikha kar
# jaanchte hain, phir chahe koi pass na hui ho. Isse kharch aur samay dono
# seemit rehte hain - band-baar naya candidate dekhte rehna kabhi khatam na
# hone wala loop ban sakta tha.
#
# Budget khatam hone par ab koi candidate BINA DEKHE nahi liya jaata (pehle
# liya jaata tha). Sep 2026, "Sindhu Ghati" (gy_indus_202609) reject: naali/
# eent wale shot par lakdi kaatti jigsaw ki Pixabay clip, Mohenjo-daro ke
# naam par kisi aur khandhar ki Pexels aerial - ye stock plan ke aakhir mein
# aate hain, jab budget khatam ho chuka hota hai, aur sirf shabd-milaan se
# paas ho jaate the. Ab budget khatam = khoj band, shot AAKHRI SAHARE par.
VISION_MAX_TRIES = 4

# Do Commons request ke beech kam se kam itne second.
WIKI_GAP = 1.2

# In do sources ki tasveer is ghatna ki nahi hoti - wo vishay ki hoti hai.
# Isliye screen par saaf label lagta hai. Ye chhupana beimani hogi.
REPRESENTATIVE = ("pexels_video", "pexels_photo",
                  "pixabay_video", "pixabay_photo")

# Jo source chalti hui footage dete hain - inka nateeja .mp4 mein jaata hai.
VIDEO_SOURCES = ("pexels_video", "pixabay_video", "commons_video")


def log(*a):
    print("[media]", *a, flush=True)


# ------------------------------------------------------- art direction

AD_SYSTEM = "\n".join([
    'Aap ek Indian news channel ke senior picture editor hain. Aapka kaam ek khabar ke liye visual treatment tay karna hai.',
    '',
    'Aap teen cheezon ke beech santulan bithate hain:',
    '1. Darshak pehle 3 second mein ruke - isliye kuch DIKHNA chahiye, sirf likha hua nahi.',
    '2. Khabar imaandaar rahe - koi cheez badha-chadha kar na kahi jaye, aur koi tasveer wo na kahe jo hui nahi.',
    '3. Video dekhne layak lage - ek news bulletin poore samay khaali screen par text nahi dikhata.',
    '',
    'Sirf JSON lautaiye, aur kuch nahi.',
])

AD_RULES = "\n".join([
    'category: khabar ka asli vishay. Isse rang chunta hai. politics | crime | education | economy | weather | sport | civic | tech',
    'style: grid = shaant, gambhir, neeti/shiksha/adalat jaisi khabrein. bands = urja, taazi ya tezi se badalti khabar. frame = sanstha, sarkari elaan, aankdon wali khabar.',
    'keyFact: khabar ki sabse thos baat - ek sankhya, ek faisla, ek naam. Ye 2.4 second bade akshar mein dikhega, isliye chhota rakhein. Headline dobara mat likhiye. Sansanikhez shabd nahi.',
    'kicker: jagah aur vishay, bahut chhota.',
    '',
    'VISUAL - yahan picture editor ki tarah sochiye, clerk ki tarah nahi.',
    'GALAT sawaal: "kya is ghatna ki asli tasveer mil jayegi?" SAHI sawaal: "darshak ko kya DIKHNA chahiye taaki khabar samajh aaye aur wo ruke?"',
    'Ye soch bilkul galat hai ki "laapata logon ki asli tasveer nahi milegi, isliye koi tasveer nahi chalegi". Nepal mein baadh ki khabar par paani dikhta hai - ubharta darya, doobi hui sadak, rahat naav. Adalat ke faisle par adalat ki imaarat. School ki khabar par classroom. Ye har news channel duniya bhar mein karta hai, aur isi ko file footage ya prateekatmak footage kehte hain.',
    'Isliye wantsPhoto lagbhag HAMESHA true rakhiye. False sirf tab jab khabar itni abstract ho ki koi bhi sacchi tasveer use galat bana de.',
    '',
    'ASLI CHEEZ KI ASLI TASVEER - ye sabse zaroori niyam hai.',
    'Khabar mein koi jaana-pehchana NAAM ho - koi sanstha (ISRO, RSS, SBI), koi yaan ya rocket (GSLV, Chandrayaan), koi imaarat ya sthal (Supreme Court, Sriharikota, Kedarnath), ya koi vyakti - to photoQueries mein PEHLI khoj wahi naam angrezi mein rakhiye.',
    'Kyun: aise har vishay ki asli, licence wali tasveerein Wikimedia Commons par hoti hain. ISRO ki khabar par ISRO ke rocket ki asli tasveer milti hai - kisi videshi rocket ka stock clip uske aage kuch nahi. Jahan ki khabar, wahan ki tasveer.',
    '',
    'PRASIDDH VYAKTI:',
    'Agar khabar ka kendra koi jaana-pehchana SARVAJANIK vyakti hai - koi mantri, mukhyamantri, pradhanmantri, nyayadhish, bada khiladi, kisi badi sanstha ka pramukh - to isPerson true kijiye aur photoQueries mein pehli khoj unka POORA NAAM angrezi mein likhiye.',
    'Kyun: aise logon ki sahi licence wali tasveerein Wikimedia Commons par maujood hoti hain. Itni badi khabar ko sirf likhe hue text par chhod dena sampadakiy galti hai - darshak wo chehra dekhna chahta hai jiski baat ho rahi hai.',
    '',
    'peopleEn: khabar ke KENDRA ke sarvajanik log - POORA NAAM angrezi mein, zyada se zyada do (jaise ["Anahat Singh"]). Khiladi jo desh ya rajya ke liye khelte/medal jeette hain, kalakar, netaa, adhikari (pad ke naate) - ye sab sarvajanik hain, UMAR CHAHE KUCH BHI HO. Kasauti: kya is vyakti ka apna Wikipedia lekh ho sakta hai? Haan to naam likhiye. Khabar ka hook aksar wahi chehra hota hai - uske bina video bekaar lagti hai. Aam nagrik, aaropi, peedit, gawah ka naam KABHI nahi - tab khaali list.',
    '',
    'NIJI VYAKTI - iska ulta:',
    'Jo vyakti sarvajanik nahi hai - aam nagrik, aaropi, peedit, gawah, karmchari, chhatra - unka naam khoj mein KABHI mat daaliye aur unka chehra kabhi mat dikhaiye. isPerson false rakhiye aur vishay ka drishya dikhaiye (school ki imaarat, adalat, thana, sadak).',
    '',
    'photoQueries: teen khoj, angrezi mein. Prasiddh vyakti ho to pehli khoj unka naam. Warna ghatna mat dhoondhiye - us ghatna ka DRISHYA dhoondhiye: "Nepal flood 13 missing" mat likhiye, wo kabhi nahi milega; "flooded river Nepal", "monsoon flood rescue boat" likhiye. Khaas se aam ki taraf badhiye.',
    '',
    'SAKHT SHART:',
    'Jo tasveer is ghatna ki nahi hai, use is ghatna ki tasveer banakar kabhi mat dikhaiye. Aisi har tasveer par screen par saaf label lagta hai - wo apne aap lag jaata hai. Isliye aisi tasveer chuniye jo vishay ke saath SACCHI ho.',
    'Kisi asli, pehchane jaane wale vyakti ka chehra jo is khabar ka hissa NAHI hai - kabhi nahi. Kisi doosri ghatna ki tabahi ko is ghatna ki tabahi banakar dikhana - kabhi nahi.',
    '',
    'THUMBNAIL - yahan sabse zyada dhyaan dijiye. YouTube par pehla faisla thumbnail par hota hai.',
    'thumbEntity: thumbnail ki sabse badi line. Khabar mein maujood wo naam jise sabse zyada log pehle se jaante hain - koi sanstha (RSS, ISRO, SBI, सुप्रीम कोर्ट), koi pad ya jaana-pehchana vyakti, koi yojana, ya koi bada sthal. Ek jaani-pehchani JAGAH bhi entity ban sakti hai (नेपाल, बिहार, प्रयागराज) jab khabar mein us se bada koi naam na ho. Khaali SIRF tab jab koi aisa naam ho hi na. Jo naam khabar mein nahi hai use kabhi mat jodiye.',
    'thumbText: entity ke NEECHE wali line - kya hua. 2 se 5 shabd. Entity ko dobara mat likhiye. Padhne par poora vaakya bane: "RSS" + "मार्च पर दो शिक्षक निलंबित".',
    'Thumbnail par sawal mat poochhiye aur adhoora suspense mat rakhiye. Hazaron shirshakon par kiye gaye adhyayan batate hain ki clickbait shirshak saade shirshak se zyada click nahi laate aur bharosa ghata dete hain.',
    'thumbStyle: split tabhi jab wantsPhoto true ho aur tasveer khud kahani kehti ho. Baaki har khabar par slab.',
])

AD_SHAPE = {
    "category": "politics | crime | education | economy | weather | sport | civic | tech",
    "style": "grid | bands | frame",
    "kickerHi": "जगह · विषय, 40 अक्षर तक",
    "keyFactHi": "सबसे ठोस बात, 22 अक्षर तक",
    "ghost": "सिर्फ जगह का नाम, देवनागरी में",
    "isPerson": False,
    "peopleEn": ["kendra ke sarvajanik vyakti ka poora naam, angrezi mein"],
    "wantsPhoto": True,
    "photoReason": "ek line - kya dikhana chahiye aur kyun",
    "photoQueries": ["drishya ya naam, angrezi mein 2-4 shabd", "doosri koshish", "teesri koshish"],
    "thumbEntityHi": "सबसे पहचाना नाम, 1-2 शब्द",
    "thumbTextHi": "उसके नीचे — क्या हुआ, 2 से 5 शब्द",
    "thumbStyle": "slab | split",
}

STYLES = ("grid", "bands", "frame")
CATS = ("politics", "crime", "education", "economy", "weather", "sport", "civic", "tech")


def _place(t):
    m = re.match(r"^([^|:—]{2,40})\s*[|:—]", str(t or ""))
    return m.group(1).strip() if m else ""


def art_direction(story):
    """Picture editor ka faisla. Jawab na aaye to shaant default."""
    fallback = {
        "category": "politics", "style": "grid",
        "kicker": _place(story["headline_hi"]) or "भारत",
        "key_fact": "", "ghost": _place(story["headline_hi"]) or "",
        "thumb_entity": "", "thumb_text": "", "thumb_style": "slab",
        "wants_photo": 0, "photo_reason": "art director se jawab nahi mila",
        "photo_queries": "[]", "is_person": 0, "people_en": "[]",
    }
    user = "\n".join([
        "KHABAR",
        "Headline (Hindi): " + str(story.get("headline_hi") or ""),
        "Headline (English): " + str(story.get("headline_en") or ""),
        "Sources: " + str(story.get("sources") or ""),
        "", "Script (Hindi):", str(story.get("script_hi") or "")[:900],
        "", "NIYAM", AD_RULES,
        "", "ISI SHAPE MEIN JSON LAUTAIYE",
        json.dumps(AD_SHAPE, ensure_ascii=False, indent=2),
    ])
    j = sy_ai.ask_json(AD_SYSTEM, user, max_tokens=1500)
    if not j:
        return fallback

    queries = []
    for q in (j.get("photoQueries") or [])[:4]:
        q = str(q or "").strip()
        if q:
            queries.append(q[:60])

    style = j.get("style") if j.get("style") in STYLES else "grid"
    cat = j.get("category") if j.get("category") in CATS else "politics"
    return {
        "category": cat,
        "style": style,
        "kicker": str(j.get("kickerHi") or fallback["kicker"])[:40],
        "key_fact": str(j.get("keyFactHi") or "")[:30],
        "ghost": str(j.get("ghost") or fallback["ghost"])[:20],
        # Entity chhota rakha jaata hai - wo frame ki sabse badi line banti
        # hai, aur lambi hui to font khud chhota ho jaayega aur wahi ek
        # faayda khatm ho jayega jiske liye use bada rakha tha.
        "thumb_entity": str(j.get("thumbEntityHi") or "").strip()[:16],
        "thumb_text": str(j.get("thumbTextHi") or j.get("keyFactHi") or "").strip()[:40],
        "thumb_style": "split" if j.get("thumbStyle") == "split" else "slab",
        "wants_photo": 1 if (j.get("wantsPhoto") is True and queries) else 0,
        "photo_reason": str(j.get("photoReason") or "")[:160],
        "photo_queries": json.dumps(queries, ensure_ascii=False),
        "is_person": 1 if (j.get("isPerson") is True or _people_list(j)) else 0,
        "people_en": json.dumps(_people_list(j), ensure_ascii=False),
    }


def _people_list(j):
    out = []
    for n in (j.get("peopleEn") or [])[:2]:
        n = re.sub(r"\s+", " ", str(n or "")).strip()
        # Kam se kam do shabd - ek shabd par galat chehra aa sakta hai
        # (portrait() bhi yahi maangta hai).
        if len(n) >= 4 and " " in n and n.lower() not in (x.lower() for x in out):
            out.append(n[:60])
    return out


def story_people(story):
    try:
        return [str(n) for n in json.loads(story.get("people_en") or "[]") if n]
    except Exception:
        return []


# ------------------------------------------------------------ shot list
#
# Yahan tak system ek khabar ke liye EK tasveer laata tha aur wahi 90 second
# tak screen par padi rehti thi. Wo radio hai, television nahi. Darshak ke
# saamne har baat par wahi ek tasveer rehti hai, isliye na wo baat yaad
# rehti hai na wo rukta hai.
#
# Duniya bhar ke newsroom ka usool ek hi hai: "the words omit what the
# pictures show and tell what the pictures omit" - yaani tasveer aur aawaaz
# do alag jaankari dete hain, ek doosre ko dohraate nahi. Television news
# mein ek shot ausatan lagbhag 5 second ka hota hai (812 ghante ki news par
# ki gayi ginti - 6 lakh se zyada shot). Hum har 5 second par nayi licence
# wali sacchi tasveer nahi jutaa sakte, par ek tasveer par 90 second bhi
# nahi baith sakte.
#
# Isliye beech ka rasta: script ko 4-6 baaton mein todo, har baat ka apna
# drishya laao, aur har drishya ke andar camera halka sa chalta rahe. Cut
# ghadi dekhkar nahi lagta - jahan baat badalti hai wahin lagta hai.

SHOT_SYSTEM = "\n".join([
    'Aap ek Indian news channel ke picture editor hain. Aapke saamne ek bulletin ki script hai jo bolkar sunai jayegi. Aapko tay karna hai ki jab ye script boli ja rahi ho, tab har lamhe par screen par KYA dikhega.',
    '',
    'Aap ek editing table par baithe hain, search box par nahi. Aap ye nahi sochte ki "kya mil jayega" - aap ye sochte hain ki "is baat par darshak ko kya dikhna chahiye".',
    '',
    'Sirf JSON lautaiye, aur kuch nahi.',
])

SHOT_RULES = "\n".join([
    'KAAM: script ko 4 se 6 tukdon mein toadiye, aur har tukde ke liye ek drishya tay kijiye.',
    '',
    'TUKDA KAHAN TOOTE:',
    'Cut wahan lagta hai jahan BAAT badalti hai - jagah se aankde par, aankde se aadmi par, aadmi se aage kya hoga par. Ghadi dekh kar barabar tukde mat kijiye. Ek tukda ek vaakya ka ho sakta hai, doosra teen vaakyon ka.',
    'Har tukde ka "text" script ke ASLI shabd hone chahiye, shuru se aakhir tak, bina kisi shabd ko badle, hataye ya jode. Saare tukde jod dene par poori script wapas banni chahiye. Ye sabse zaroori shart hai - isi se tay hota hai ki tasveer sahi lamhe par badlegi.',
    '',
    'HAR TUKDE PAR KYA DIKHE - yahi asli kaam hai:',
    'Tasveer wahi baat mat dohraiye jo aawaaz keh rahi hai. Aawaaz jo NAHI keh sakti, wo tasveer dikhaye - jagah kaisi hai, kitni badi baat hai, kis par beet rahi hai.',
    'Ek kramgat kram rakhiye, jaise koi bhi newsroom rakhta hai:',
    '  1. KAHAN - wo jagah, door se. Shehar, imaarat, nadi, sadak, sansthan.',
    '  2. KYA/KAUN - wo cheez ya wo log jinki baat ho rahi hai, paas se.',
    '  3. SABOOT - jis par baat tiki hai: aadesh ka kagaz, machine, khet, class, kataar, bhavan.',
    '  4. ASAR - jinpar beet raha hai: aam log, kisan, mareez, chhatra, dukandar, yatri.',
    'Har tukde ka drishya pichhle se ALAG hona chahiye. Ek hi cheez ke do shot ek jaise ho jayein to ek hata dijiye - wo screen bhar raha hai, kuch keh nahi raha.',
    '',
    'JAGAH SABSE PEHLE - ye niyam sabse zyada toota hai:',
    'PEHLE tukde ki PEHLI khoj us JAGAH ka naam honi chahiye jahan ki ye khabar hai, angrezi mein - "Varanasi", "Bhadohi", "Prayagraj Sangam", "Ballia". Sirf jagah, uske saath aur kuch nahi.',
    'Kyun: darshak ko sabse pehle ye pata chalna chahiye ki baat uske apne ilaake ki hai. Aur aisi jagahon ki asli tasveerein maujood hoti hain - jo bhi hum dikha sakte hain, unme sabse sachhi wahi hai.',
    'Ek khabar Varanasi ki thi aur pehla drishya Colombo ka chuna gaya tha, aur Varanasi kahin peechhe. Wo galti hai. Ghatna kahin bhi hui ho, khabar JISKI hai wo jagah pehle aayegi.',
    '',
    'KISI CHHOTI SI BAAT KO DRISHYA MAT BANAIYE:',
    'Script mein aayi kisi haashiye ki cheez par tukda mat banaiye. Ek khabar mein petrol pump ka zikr tha aur uska ek poora tukda petrol pump ka bana diya gaya - jabki khabar us ladki ki thi jo desh ka pratinidhitva karne gayi. Har tukda khabar ki MUKHYA baat se juda ho.',
    '',
    'KHOJ KAISE LIKHEIN:',
    'queries: har tukde ke liye do khoj, angrezi mein, 2-4 shabd. GHATNA mat dhoondhiye - us ghatna ka DRISHYA dhoondhiye. "Mirzapur road accident 3 dead" kabhi nahi milega; "Indian highway night traffic", "ambulance rural India" milega.',
    'Koi jaana-pehchana NAAM ho - sanstha (ISRO, SBI, Supreme Court), yaan (GSLV, Chandrayaan), sthal (Sangam Prayagraj, Kashi Vishwanath), ya koi bada sarvajanik vyakti - to us tukde ki pehli khoj wahi naam angrezi mein rakhiye. Aisi cheezon ki ASLI licence wali tasveerein maujood hoti hain, aur asli tasveer kisi bhi stock se behtar hai.',
    '',
    'IMAANDARI - ispar koi chhoot nahi:',
    'Jo tasveer is ghatna ki nahi hai, use is ghatna ki tasveer banakar mat dikhaiye. Screen par apne aap label lag jaata hai, par label bahana nahi hai - tasveer vishay ke saath SACCHI honi chahiye.',
    '',
    'CHEHRE - yahan do alag tarah ke log hain, aur inhe mila mat dijiye:',
    '',
    'SARVAJANIK PAD/PEHCHAN WALE LOG - inka chehra DIKHNA CHAHIYE, aur ye galti abhi tak ho rahi thi.',
    'Isme aate hain: Pradhanmantri, Mukhyamantri, mantri, sansad, vidhayak, kisi rajnaitik dal ya sangathan ke pad-dhaari, nyayadhish, sena/police ke bade adhikari (apne pad ke naate), aur wo khiladi, kalakar ya vaigyanik jo pehle se sarvajanik roop se jaane jaate hain.',
    'Aise vyakti ki baat ho to us tukde ka type "people" rakhiye aur PEHLI khoj sirf unka POORA NAAM angrezi mein likhiye - "Narendra Modi", "Yogi Adityanath", "Rahul Gandhi". Naam ke saath aur kuch nahi: na "speech", na "rally", na "photo".',
    'Kyun: aise har vyakti ki muft licence wali asli tasveer maujood hai, aur jab aawaaz unka naam le rahi ho tab unka chehra na dikhna sabse saaf dikhne wali kami hai.',
    'Doosri khoj us mauke ki rakh sakte hain ("Lok Sabha chamber", "Uttar Pradesh assembly").',
    '',
    'AAM LOG - inka chehra KABHI NAHI.',
    'Isme aate hain: aam nagrik, aaropi, peedit, gawah, chhatra, mareez, aur koi bhi vyakti jo sirf is ghatna ki wajah se khabar mein hai.',
    'Inka naam khoj mein kabhi mat likhiye. Unke tukde par jagah, sanstha ya cheez dikhaiye - aadmi nahi.',
    'Shak ho ki vyakti sarvajanik hai ya nahi, to aam maan lijiye aur naam mat likhiye. Par kasauti yaad rakhiye: jis vyakti ka apna Wikipedia lekh ho sakta hai (desh/rajya ke liye khelne wala khiladi - umar chahe kam ho, kalakar, netaa) wo sarvajanik hai - uska tukda "people" aur pehli khoj uska poora naam.',
    'Kisi doosri jagah ki tabahi ko is khabar ki tabahi banakar kabhi mat dikhaiye.',
    '',
    'type: place | institution | people | object | document | map - inhi mein se ek.',
])

SHOT_SHAPE = {
    "shots": [
        {"text": "script ke asli shabd, jitne is tukde mein aate hain",
         "type": "place | institution | people | object | document | map",
         "brief": "ek line - is baat par darshak ko kya dikhna chahiye aur kyun",
         "queries": ["angrezi mein 2-4 shabd", "doosri koshish"]},
    ]
}


def _norm(s):
    """Milaan ke liye - sirf akshar aur ank, baaki sab hata kar."""
    return re.sub(r"[^\w]+", "", str(s or ""), flags=re.UNICODE).lower()


def shot_list(story):
    """Script ko drishyon mein todo. List lautata hai, na ban paye to khaali.

    Har tukde ka text script se aana chahiye - hum ise jaanchte hain. Agar
    picture editor ne shabd badal diye ya kuch chhod diya, to timing galat
    ho jayegi: tasveer us baat par badlegi jo boli hi nahi ja rahi. Aisi
    haalat mein ek tukda bhi nahi lete - purana ek-tasveer wala rasta us
    galat timing se behtar hai.
    """
    script = str(story.get("script_hi") or "").strip()
    if len(script) < 120:
        return []

    user = "\n".join([
        "KHABAR", str(story.get("headline_hi") or ""), "",
        "Jagah: " + str(story.get("ghost") or "") ,
        "", "SCRIPT (yahi boli jayegi):", script,
        "", "NIYAM", SHOT_RULES,
        "", "ISI SHAPE MEIN JSON LAUTAIYE",
        json.dumps(SHOT_SHAPE, ensure_ascii=False, indent=2),
    ])
    j = sy_ai.ask_json(SHOT_SYSTEM, user, max_tokens=2500)
    raw = (j or {}).get("shots") or []
    if not isinstance(raw, list) or len(raw) < 2:
        return []

    shots, covered = [], ""
    for s in raw[:8]:
        if not isinstance(s, dict):
            continue
        text = re.sub(r"\s+", " ", str(s.get("text") or "")).strip()
        if len(text) < 15:
            continue
        qs = []
        for q in (s.get("queries") or [])[:3]:
            q = str(q or "").strip()
            if q:
                qs.append(q[:60])
        if not qs:
            continue
        shots.append({
            "text": text,
            "type": str(s.get("type") or "place")[:20],
            "brief": str(s.get("brief") or "")[:160],
            "queries": qs,
        })
        covered += text

    if len(shots) < 2:
        return []

    # Jaanch: tukdon ko jodne par script wapas banni chahiye. Thoda farq
    # chalta hai (virām, spacing), par 88% se kam mile to matlab picture
    # editor ne script dobara likh di - us timing par bharosa nahi kiya
    # ja sakta.
    a, b = _norm(covered), _norm(script)
    if not b:
        return []
    ratio = len(a) / float(len(b))
    if ratio < 0.88 or ratio > 1.12:
        log("shot list chhodi - text script se nahi milta (%.0f%%)" % (ratio * 100))
        return []
    return shots


# --------------------------------------------------------- khoj ki jaanch

QSTOP = set("""news india indian video footage scene view shot people live
latest breaking from with near over after into amid during their this that
than when what will been""".split())


def terms(query):
    """Khoj ke kaam ke shabd. Sirf pehle 5 akshar - taaki 'flood' aur
    'flooded' ek doosre se juda na reh jayein."""
    out = []
    for w in re.split(r"[^a-z]+", str(query or "").lower()):
        if len(w) >= 4 and w not in QSTOP:
            out.append(w[:5])
    return out


# Stock ki wo duniya jo Indian khabar par kabhi sach nahi hoti.
#
# Sahaaranpur ki masjid dhwast hone wali khabar par Pexels se do videshi
# corporate model chal gaye - suit pehne, American jhande ke saamne. Wo
# "generic" nahi tha, wo JHOOTH tha, aur sabse sanvedansheel khabar par.
#
# Wajah: purani jaanch mein khoj ka ek shabd mil jaana kaafi tha.
# "Indian government official circular letter closeup" mein se sirf
# "offic" kisi corporate office wali clip ke naam se mil gaya aur wo paas
# ho gayi. Ab do shabd chahiye, aur ye list wale nateeje seedhe kharij.
STOCK_BLOCK = re.compile(
    r"(business|corporate|entrepreneur|startup|boardroom|coworking|"
    r"handshake|teamwork|colleague|meeting-room|conference-room|"
    r"businessman|businesswoman|office-worker|manager|salesman|"
    r"model|fashion|studio-shot|portrait-of|smiling|happy-|posing|"
    r"laptop|macbook|keyboard-typing|headphone|podcast|"
    r"american|usa|new-york|london|europe)", re.I)


def proper_terms(query):
    """Khoj ke KHAAS naam - jagah, sanstha, vyakti.

    Picture editor ye naam bade akshar se likhta hai: "Bhadohi district
    stadium Uttar Pradesh" mein Bhadohi aur Uttar Pradesh naam hain,
    district aur stadium aam shabd. Yahi naam asli pehchan hain.
    """
    out = []
    for w in re.findall(r"\b[A-Z][a-zA-Z]{3,}", str(query or "")):
        low = w.lower()
        if low not in QSTOP:
            out.append(low[:5])
    return out


def relevant(hay, query, stock=True):
    """Kya ye nateeja sach mein us cheez ka hai jo hum dhoondh rahe the?

    DO ALAG TARAAZU, aur ye farq zaroori hai.

    Stock (Pexels/Pixabay) par sakhti chahiye: wahan nateeje ke naam lambe
    aur aam hote hain ("business-woman-in-office-3184291"), isliye ek shabd
    ka milna sanjog ho sakta hai. Wahan do shabd chahiye aur blocklist bhi.

    Commons/Openverse par wahi sakhti ULTA kaam karti hai - aur maine
    pichhli baar yahi galti ki. Wahan file ka naam chhota aur seedha hota
    hai: "Bhadohi_railway_station.jpg". "Bhadohi district stadium Uttar
    Pradesh" khoj par usme sirf EK shabd milta hai, aur meri do-shabd wali
    shart use kharij kar deti thi. Isi wajah se Bhadohi, Colombo, Varanasi
    - sabki asli tasveerein chhoot rahi thi aur screen par generic stock
    ya kuch bhi nahi aa raha tha.
    Wahan ek KHAAS NAAM ka milna hi kaafi hai. "Varanasi" ka kisi Commons
    file ke naam mein aana sanjog nahi hota.
    """
    h = str(hay or "").lower()
    ts = terms(query)
    if not ts:
        return False

    if stock:
        if STOCK_BLOCK.search(h):
            return False
        hits = sum(1 for t in set(ts) if t in h)
        return hits >= (2 if len(set(ts)) >= 2 else 1)

    # Asli source: khaas naam mil gaya to bas.
    for p in proper_terms(query):
        if p in h:
            return True
    hits = sum(1 for t in set(ts) if t in h)
    return hits >= 2


def narrow(query):
    """Khoj ko sirf khaas naamon tak samet do.

    Commons ka search lambe vaakya par kamzor hai aur chhote seedhe naam
    par achha. "Kashi Varanasi Ganga ghat" par kuch na mile to "Kashi
    Varanasi Ganga" aazmana ek alag, behtar koshish hai - wahi naam jo
    is khabar ki asli pehchan hain.
    """
    names = re.findall(r"\b[A-Z][a-zA-Z]{3,}(?:\s+[A-Z][a-zA-Z]{3,})*",
                       str(query or ""))
    out = " ".join(names).strip()
    if not out or out.lower() == str(query or "").strip().lower():
        return ""
    # "India", "Indian", "Uttar Pradesh" akele koi khoj nahi hai - Commons
    # par unpar laakhon file hain aur koi bhi is khabar ki nahi. Log mein
    # "gsrsearch=India" saaf dikh raha tha: ek poori request, har baar
    # bekaar. Aise naam tabhi chalte hain jab unke saath kuch aur ho.
    if out.lower() in ("india", "indian", "uttar pradesh", "up", "bharat"):
        return ""
    return out


# Kis tarah ke shot par stock chal sakta hai, aur kis par nahi.
#
# place  - nadi, sadak, shehar, bheed, barsaat. Aisi cheez ka prateekatmak
#          drishya sach ke kareeb reh sakta hai.
# object - machine, khet, kataar, bus. Wahi baat.
#
# institution / document / people / map par stock KABHI nahi. Wahan stock
# ka matlab hota hai: kisi aur desh ka daftar, kisi aur ka kagaz, kisi aur
# ka chehra - aur wo khabar ko jhootha bana deta hai. In par sirf Commons
# aur Openverse, jahan tasveer asli cheez ki hoti hai. Kuch na mile to
# kuch nahi - pichhla drishya chalta rahega. Khaali se bura sirf galat hai.
STOCK_OK_TYPES = ("place", "object")


# ------------------------------------------------------------- sources

def pexels_clip(query):
    key = cfg.get("pexels", "api_key")
    if not key:
        return "", ""
    try:
        data = sy_net.get_json(
            "https://api.pexels.com/videos/search?per_page=10&orientation=landscape"
            "&size=medium&query=" + sy_net.urllib.parse.quote(query),
            headers={"Authorization": key}, timeout=30)
    except Exception as e:
        log("pexels video:", e)
        return "", ""

    best, best_score = None, -1
    for v in (data.get("videos") or []):
        if float(v.get("duration") or 0) < 5:
            continue
        if not relevant(v.get("url"), query):
            continue
        for f in (v.get("video_files") or []):
            if f.get("file_type") != "video/mp4":
                continue
            w = int(f.get("width") or 0)
            if w < 960:
                continue
            # 1920 ke sabse kareeb, usse upar nahi - warna download hi
            # lamba ho jaata hai.
            score = w if w <= 1920 else (1920 - (w - 1920))
            if score > best_score:
                best_score, best = score, (f, v)
    if not best:
        return "", ""
    f, v = best
    return str(f.get("link") or ""), "Pexels / " + str((v.get("user") or {}).get("name") or "Pexels")


def pexels_photo(query):
    key = cfg.get("pexels", "api_key")
    if not key:
        return "", ""
    try:
        data = sy_net.get_json(
            "https://api.pexels.com/v1/search?per_page=10&orientation=landscape"
            "&size=large&query=" + sy_net.urllib.parse.quote(query),
            headers={"Authorization": key}, timeout=30)
    except Exception as e:
        log("pexels photo:", e)
        return "", ""
    for p in (data.get("photos") or []):
        if not relevant(str(p.get("alt") or "") + " " + str(p.get("url") or ""), query):
            continue
        src = p.get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if url:
            return str(url), "Pexels / " + str(p.get("photographer") or "Pexels")
    return "", ""


def is_raster(path):
    """Kya ye sach mein ek aisi tasveer hai jise ffmpeg khol sakta hai?

    URL ka naam jhooth bol sakta hai. Ek SVG ".jpg" naam se utar aayi thi
    aur render wahin toot gaya: "no decoder found for: svg". Naam par
    bharosa karne ke bajaye file ke pehle chand byte padh lete hain - har
    tarah ki tasveer apni pehchan wahi rakhti hai.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except Exception:
        return False
    return (head.startswith(b"\xff\xd8\xff")                       # JPEG
            or head.startswith(b"\x89PNG\r\n\x1a\n")               # PNG
            or head.startswith(b"GIF8")                            # GIF
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP")     # WebP
            or head.startswith(b"BM")                              # BMP
            or head[:4] in (b"II*\x00", b"MM\x00*"))               # TIFF


def _wiki(url):
    """Commons se ek jawab - unke apne niyam ke saath.

    Do cheezein zaroori hain, aur dono pehle nahi thi: apna naam-sampark
    bhejna (warna wo sabse sakht rate-limit lagate hain), aur do request
    ke beech thoda antar (wo ek-ek karke request maangte hain, jhund mein
    nahi). 429 ka yahi ilaaj hai.
    """
    sy_net.throttle("wikimedia", WIKI_GAP)
    return sy_net.get_json(url, headers=sy_net.wiki_headers(), timeout=30)


# SARVAJANIK CHEHRE - AUR EK KAMI JO MERI THI
#
# Aap ne likha ki Modi, Rahul Gandhi jaise chehre screen par nahi aate,
# aur ye ki itni buniyadi baat par system ka fail hona kharab hai. Aap
# sahi hain, par ek baat theek kar deta hoon kyunki wo aage kaam aayegi:
#
#   Mashhoor hone se tasveer par copyright nahi hatta. Kisi bhi tasveer ka
#   copyright usi ka hota hai jisne wo KHEENCHI - chahe usme Pradhanmantri
#   hon. Agar hum Google se koi tasveer utha lein to wo kisi photographer
#   ya agency ki hoti hai, aur channel par uska daawa aa sakta hai.
#
# Par aapki BAAT phir bhi sahi hai, kyunki asli tathya ye hai:
#
#   In sab logon ki MUFT LICENCE WALI tasveerein maujood hain, aur bahut
#   saari. PIB aur PMO apni tasveerein GODL-India ke tahat jaari karte
#   hain; Wikipedia par har netaa, har mantri, har khiladi ki tasveer usi
#   tarah ki hai. Yaani tasveer thi, aur hum use dhoondh nahi paa rahe the.
#
# Kyun nahi dhoondh paa rahe the - do wajah, dono meri:
#   1. Art director ko saaf kaha gaya tha ki kisi ka chehra mat dikhaiye.
#      Wo niyam aam nagrik, aaropi aur peedit ke liye tha, par usme ye
#      farq likha hi nahi tha ki sarvajanik pad par baithe log ISSE BAAHAR
#      hain. Isliye wo naam ki jagah "Indian politician" jaisi bekaar khoj
#      likhta tha.
#   2. Commons ki poore-text wali khoj naam par bharosemand nahi hai.
#
# Iska seedha ilaaj yahi hai: aadmi ka naam Wikipedia ke lekh se milao aur
# usi lekh ki MUKHYA tasveer utha lo. Wo tasveer hamesha Commons par hoti
# hai aur hamesha muft licence wali - Wikipedia par bina licence wali
# tasveer rehti hi nahi. Yahi wo tasveer hai jo duniya us aadmi ki pehchan
# maanti hai.
PORTRAIT_API = "https://en.wikipedia.org/w/api.php"
PORTRAIT_HI = "https://hi.wikipedia.org/w/api.php"


# WIKIMEDIA AB HAR FILE KE URL KE AAGE APNA NISHAN JOD DETA HAI
#
# Pehle unka jawab aisa aata tha:
#     .../Narendra_Modi_Portrait_2026.jpg
# Ab aisa aata hai:
#     .../Narendra_Modi_Portrait_2026.jpg?utm_source=en.wikipedia.org
#     &utm_campaign=api&utm_content=original
#
# Hamari jaanch "URL ke ANT mein .jpg hona chahiye" thi. Ab ant mein .jpg
# nahi, unka nishan hai - isliye har sacchi tasveer chup-chaap chhant kar
# nikal jaati thi. Jaanch mein teenon (Commons, Commons footage, Openverse)
# "chal raha hai (is khoj par kuch nahi)" keh rahe the, jabki Commons ne
# Prayagraj par chaar asli files lauta ai thi.
#
# Ye wahi kami ho sakti hai jiske chalte aapko har khabar par generic stock
# dikh raha tha - asli tasveer aa rahi thi aur hum use hi phenk rahe the.
#
# Ilaaj: sawaal ka nishan aane ke baad ka hissa hata kar dekho.
def _path_of(url):
    """URL ka sirf raasta - uske aage jude nishan ke bina."""
    return str(url or "").split("?", 1)[0].split("#", 1)[0]


def _is_pic_url(url):
    return bool(re.search(r"\.(jpg|jpeg|png)$", _path_of(url), re.I))


def _portrait_credit(fname):
    """Us tasveer ka banane wala aur uska licence - credit ke liye."""
    try:
        d = _wiki("https://commons.wikimedia.org/w/api.php?action=query"
                  "&format=json&prop=imageinfo&iiprop=extmetadata&titles="
                  + sy_net.urllib.parse.quote("File:" + fname))
    except Exception:
        return "चित्र: Wikimedia Commons"
    for p in ((d.get("query") or {}).get("pages") or {}).values():
        for ii in (p.get("imageinfo") or []):
            meta = ii.get("extmetadata") or {}
            artist = re.sub(r"<[^>]+>", "",
                            str((meta.get("Artist") or {}).get("value") or "")).strip()
            lic = str((meta.get("LicenseShortName") or {}).get("value") or "")
            out = "चित्र: " + (artist or "Wikimedia Commons")
            if lic:
                out += " / " + lic
            return out[:120]
    return "चित्र: Wikimedia Commons"


def portrait(name):
    """Kisi jaane-mane vyakti ki muft licence wali tasveer. (url, credit)

    Wikipedia ke lekh ki mukhya tasveer uthate hain. Wo tasveer Commons par
    hoti hai aur uska licence saaf hota hai.

    Do pehre, taaki galat chehra kabhi na aaye:
      - jo lekh khula uske SHIRSHAK mein naam ka har hissa hona chahiye.
        "Rahul Gandhi" khojne par "Rahul Dravid" ka lekh khul jaye to hum
        use nahi lete.
      - disambiguation wale safhe chhod dete hain.
    Shak ho to khaali - galat chehra dikhane se kuch na dikhana behtar hai.
    """
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if len(name) < 4 or " " not in name:
        # Ek hi shabd par bharosa nahi - "Yogi", "Modi" par kuch bhi khul
        # sakta hai. Poora naam chahiye.
        return "", ""

    parts = [w for w in re.split(r"\s+", name.lower()) if len(w) > 2]

    for api in (PORTRAIT_API, PORTRAIT_HI):
        try:
            sy_net.throttle("wikimedia", WIKI_GAP)
            d = sy_net.get_json(
                api + "?action=query&format=json&redirects=1"
                "&prop=pageimages|pageprops&piprop=original&titles="
                + sy_net.urllib.parse.quote(name),
                headers=sy_net.wiki_headers(), timeout=30)
        except Exception as e:
            log("portrait:", e)
            continue
        for p in ((d.get("query") or {}).get("pages") or {}).values():
            if "missing" in p:
                continue
            props = p.get("pageprops") or {}
            if "disambiguation" in props:
                continue
            title = str(p.get("title") or "").lower()
            if not all(w in title for w in parts):
                continue
            src = str(((p.get("original") or {}).get("source")) or "")
            if not _is_pic_url(src):
                continue
            # File ka naam: pehle pageimage, warna pageprops se, warna
            # URL ke raaste se. Ek hi jagah par bharosa nahi karte -
            # Wikimedia jawab ka aakar samay-samay par badalta rehta hai,
            # aur credit ke bina tasveer chalani nahi chahiye.
            fname = (str(p.get("pageimage") or "")
                     or str((p.get("pageprops") or {}).get("page_image_free") or "")
                     or _path_of(src).rsplit("/", 1)[-1])
            fname = sy_net.urllib.parse.unquote(fname)
            return src, (_portrait_credit(fname) if fname
                         else "चित्र: Wikimedia Commons")
    return _wikidata_portrait(name, parts)


WIKIDATA_API = "https://www.wikidata.org/w/api.php"


def _wikidata_portrait(name, parts):
    """Wikipedia lekh mein mukhya tasveer na ho, par Wikidata par us vyakti
    ki tasveer (P18) ho - naye khiladiyon ke saath aksar yahi hota hai.
    Wahi pehre: label mein naam ka har hissa ho, aur ek hi vyakti mile."""
    try:
        sy_net.throttle("wikimedia", WIKI_GAP)
        d = sy_net.get_json(
            WIKIDATA_API + "?action=wbsearchentities&format=json&language=en"
            "&type=item&limit=3&search=" + sy_net.urllib.parse.quote(name),
            headers=sy_net.wiki_headers(), timeout=30)
        hits = [h for h in (d.get("search") or [])
                if all(w in str(h.get("label") or "").lower() for w in parts)]
        if len(hits) != 1:
            return "", ""
        qid = str(hits[0].get("id") or "")
        sy_net.throttle("wikimedia", WIKI_GAP)
        e = sy_net.get_json(
            WIKIDATA_API + "?action=wbgetclaims&format=json&property=P18"
            "&entity=" + qid, headers=sy_net.wiki_headers(), timeout=30)
        claims = (e.get("claims") or {}).get("P18") or []
        fname = str(((claims[0].get("mainsnak") or {}).get("datavalue") or {})
                    .get("value") or "") if claims else ""
    except Exception as ex:
        log("wikidata portrait:", ex)
        return "", ""
    if not fname:
        return "", ""
    src = ("https://commons.wikimedia.org/wiki/Special:FilePath/"
           + sy_net.urllib.parse.quote(fname.replace(" ", "_")) + "?width=1600")
    return src, _portrait_credit(fname)


def ensure_people_shots(story, shots):
    """Khabar ke kendra ka sarvajanik vyakti ho to uska chehra pakka aaye.

    KYUN (Sep 2026): Asian Games ki khabar Anahat Singh par thi, par na
    video mein unki tasveer aayi na thumbnail mein - "hook hi gayab". Shot
    list banane wala unhe "shak ho to aam maan lo" wale niyam mein daal
    gaya, aur people wala tukda bana hi nahi. Ab art director ki peopleEn
    suchi ke har naam ke liye ek tukda "people" banta hai, pehli khoj wahi
    naam. Jis tukde ki baat us vyakti par ho (naam aata ho) wahi chuna jaata
    hai; na mile to - vyakti hi khabar ka kendra ho to pehla, warna doosra.
    Script ka text nahi badalta, isliye timing waisi hi rehti hai.
    """
    names = story_people(story)
    if not names or not shots:
        return shots
    for k, name in enumerate(names):
        low = name.lower()
        if any(str(s.get("type") or "") == "people"
               and low in " ".join(s.get("queries") or []).lower() for s in shots):
            continue
        free = [i for i, s in enumerate(shots) if str(s.get("type") or "") != "people"]
        if not free:
            break
        first = low.split()[0]
        hit = [i for i in free
               if first in (str(shots[i].get("brief") or "")
                            + " " + " ".join(shots[i].get("queries") or [])).lower()]
        if hit:
            i = hit[0]
        elif story.get("is_person") and k == 0 and 0 in free:
            i = 0
        else:
            i = free[1] if len(free) > 1 else free[0]
        sh = shots[i]
        sh["type"] = "people"
        sh["queries"] = [name] + [q for q in (sh.get("queries") or []) if q != name][:2]
        sh["brief"] = (name + " - " + str(sh.get("brief") or ""))[:160]
        log("  %d. %s ka chehra is tukde par" % (i + 1, name))
    return shots


def commons_photo(query):
    """Wikimedia Commons - asli, licence wali tasveerein.

    Sirf logon ke liye nahi. ISRO ka rocket, adalat ki imaarat, koi bandh,
    koi upgrah, koi shehar - in sabki asli tasveerein yahan hoti hain, saaf
    licence ke saath. Ye stock ki generic tasveer se hamesha behtar hai:
    khabar jis cheez ki hai, tasveer bhi usi cheez ki.
    """
    try:
        data = _wiki(
            "https://commons.wikimedia.org/w/api.php?action=query&format=json"
            "&generator=search&gsrnamespace=6&gsrlimit=6&prop=imageinfo"
            "&iiprop=url|extmetadata&iiurlwidth=1600&gsrsearch="
            + sy_net.urllib.parse.quote(query))
    except Exception as e:
        log("commons:", e)
        return "", ""
    pages = ((data.get("query") or {}).get("pages") or {})
    for p in pages.values():
        for ii in (p.get("imageinfo") or []):
            url = ii.get("thumburl") or ii.get("url")
            if not url or not _is_pic_url(ii.get("url")):
                continue
            # Commons ki khoj bhi kuch na kuch lauta deti hai. File ke apne
            # naam mein khoj ka koi shabd hona chahiye.
            if not relevant(str(p.get("title") or "") + " " + str(ii.get("url") or ""),
                            query, stock=False):
                continue
            meta = ii.get("extmetadata") or {}
            artist = re.sub(r"<[^>]+>", "",
                            str((meta.get("Artist") or {}).get("value") or "")).strip()
            lic = str((meta.get("LicenseShortName") or {}).get("value") or "")
            credit = "चित्र: " + (artist or "Wikimedia Commons")
            if lic:
                credit += " / " + lic
            return str(url), credit[:120]
    return "", ""


# --------------------------------------------- sarvajanik vyakti: aur srot
#
# Sep 2026, Harshvardhan: "bahut famous logon ke footage ke Indian free
# sources jo jo hain sabko jod lijiye". Sirf wahi srot jinka licence ya
# niti saaf kehti hai ki bina ijaazat, srot ka naam dekar chhap sakte hain:
#
#   - Wikimedia Commons par us vyakti ki APNI category ("Category:Anahat
#     Singh") - poore-text khoj se kahin pakki; tasveer aur video dono.
#     PIB/PMO ki bahut si tasveerein wahan GODL-India licence mein pehle se
#     hain.
#   - PIB (pib.gov.in): "Material featured on this website may be
#     reproduced free of charge ... no need for any prior approval"
#     (pib.gov.in ki Copyright Policy). Teesre paksh ki cheez is chhoot mein
#     nahi aati.
#   - PM India (pmindia.gov.in): muft, sahi roop mein, srot ka naam saaf
#     dekar; apmaanjanak ya bhramak sandarbh mein nahi.
#
# Jo NAHI joda, aur kyun: DD News / Prasar Bharati, Sansad TV, akhbaar aur
# agency (ANI/PTI) - inka copyright surakshit hai; YouTube se utaarna uske
# niyamon ke khilaaf hai. Inse video par copyright claim/strike aata hai.

def _commons_category(name, want_video):
    """Commons par "Category:<Naam>" ki files. (url, credit) ya ("", "")."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if len(name) < 4 or " " not in name:
        return "", ""
    try:
        data = _wiki(
            "https://commons.wikimedia.org/w/api.php?action=query&format=json"
            "&generator=categorymembers&gcmtype=file&gcmlimit=25"
            "&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=1600"
            "&gcmtitle=" + sy_net.urllib.parse.quote("Category:" + name))
    except Exception as e:
        log("commons category:", e)
        return "", ""
    pages = sorted(((data.get("query") or {}).get("pages") or {}).values(),
                   key=lambda p: int(p.get("index") or 0))
    for p in pages:
        for ii in (p.get("imageinfo") or []):
            mime = str(ii.get("mime") or "")
            url = str(ii.get("url") or "")
            if want_video:
                if not mime.startswith("video/"):
                    continue
                if int(ii.get("size") or 0) > MAX_CLIP_MB * 1024 * 1024:
                    continue
            else:
                if not _is_pic_url(url):
                    continue
                url = str(ii.get("thumburl") or url)
            meta = ii.get("extmetadata") or {}
            artist = re.sub(r"<[^>]+>", "",
                            str((meta.get("Artist") or {}).get("value") or "")).strip()
            lic = str((meta.get("LicenseShortName") or {}).get("value") or "")
            credit = ("फुटेज: " if want_video else "चित्र: ") + (artist or "Wikimedia Commons")
            if lic:
                credit += " / " + lic
            return url, credit[:120]
    return "", ""


def commons_person_photo(name):
    return _commons_category(name, want_video=False)


def commons_person_clip(name):
    return _commons_category(name, want_video=True)


# Sarkari safhe jinki niti muft chhaapne deti hai: (domain, credit, tasveer
# ke pate ka pehchaan-chinh).
GOV_SITES = (
    ("pib.gov.in", "चित्र: PIB, भारत सरकार", ("static.pib.gov.in", "/writereaddata/")),
    ("pmindia.gov.in", "चित्र: pmindia.gov.in", ("/wp-content/uploads/",)),
)
_GOV_SKIP = re.compile(r"logo|icon|emblem|banner|sprite|flag|social|share|arrow|"
                       r"g20|azadi|digital|swachh|footer|header", re.I)


# Ek run mein ek naam ki khoj ek hi baar - har khoj GDELT se do call hai
# aur GDELT har call par 20-90 second rukwata hai. Lambi video (sy_long) mein
# ek hi vyakti ke kai tukde hote hain; bina iske har tukda wahi minute khata.
_GOV_CACHE = {}


_gov_cache = {}


def gov_photo(name):
    """Ek hi naam par ek run mein ek hi baar khoj (lambi video mein wahi
    vyakti kai tukdon par aata hai)."""
    key = str(name or "").strip().lower()
    if key not in _gov_cache:
        _gov_cache[key] = _gov_photo(name)
    return _gov_cache[key]


def _gov_photo(name):
    key = re.sub(r"\s+", " ", str(name or "")).strip().lower()
    if key not in _GOV_CACHE:
        _GOV_CACHE[key] = _gov_photo(name)
    return _GOV_CACHE[key]


def _gov_photo(name):
    """PIB / PM India ke kisi safhe se us vyakti ki tasveer. (url, credit)

    Safha dhoondhna: GDELT/Bing se "<naam> site:<domain>". Pehra: safhe ke
    text mein naam ka har hissa hona chahiye - warna koi aur safha. Tasveer
    kaunsi: us site ke apne upload folder ki pehli badi jpg/png, logo/icon
    chhod kar. Chehra kiska hai ye vision gate aage dekhta hai (brief mein
    naam hota hai)."""
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if len(name) < 4 or " " not in name:
        return "", ""
    parts = [w for w in name.lower().split() if len(w) > 2]
    try:
        import sy_trend
    except Exception:
        return "", ""
    for domain, credit, marks in GOV_SITES:
        links = []
        try:
            links = sy_trend._gdelt('"%s" domain:%s' % (name, domain),
                                    timespan="3m", patient=False)
        except Exception as e:
            log("gov photo (gdelt):", e)
        if not links:
            try:
                links = sy_trend._bing_links("%s site:%s" % (name, domain))
            except Exception as e:
                log("gov photo (bing):", e)
        links = [u for u in links if sy_net.host(u).endswith(domain)][:3]
        for page in links:
            try:
                html = sy_net.get_text(page, timeout=40)
            except Exception as e:
                log("gov photo safha:", e)
                continue
            text = re.sub(r"<[^>]+>", " ", html).lower()
            if not all(w in text for w in parts):
                continue
            for src in re.findall(r"""<img[^>]+src=["']([^"']+)["']""", html, re.I):
                src = sy_net.urllib.parse.urljoin(page, src.strip())
                low = src.lower()
                if not any(m in low for m in marks) or _GOV_SKIP.search(low):
                    continue
                if not re.search(r"\.(jpe?g|png)(\?|$)", low):
                    continue
                return src, credit
    return "", ""


def commons_clip(query):
    """Wikimedia Commons par CHALTI HUI footage.

    Ye Pexels se alag cheez hai aur behtar hai: yahan jo milta hai wo us
    ASLI cheez ka hota hai jiski khabar hai - PIB ka jaari kiya video, kisi
    sarkari samaroh ki recording, kisi jagah ka drishya. Isliye ye "STOCK"
    ke niyam se bandha nahi hai - har tarah ke shot par chal sakta hai.

    Koi chaabi nahi chahiye.
    """
    try:
        data = _wiki(
            "https://commons.wikimedia.org/w/api.php?action=query&format=json"
            "&generator=search&gsrnamespace=6&gsrlimit=8&prop=imageinfo"
            "&iiprop=url|size|extmetadata&gsrsearch="
            + sy_net.urllib.parse.quote("filetype:video " + query))
    except Exception as e:
        log("commons video:", e)
        return "", ""
    for p in ((data.get("query") or {}).get("pages") or {}).values():
        for ii in (p.get("imageinfo") or []):
            url = str(ii.get("url") or "")
            if not re.search(r"\.(webm|ogv|ogg|mp4|mov)$", _path_of(url), re.I):
                continue
            # Commons par kai video ghanton ki hoti hain - unhe utaarna
            # bekaar hai, hume 15 second chahiye.
            if int(ii.get("size") or 0) > MAX_CLIP_MB * 1024 * 1024:
                continue
            if not relevant(str(p.get("title") or "") + " " + url, query, stock=False):
                continue
            meta = ii.get("extmetadata") or {}
            artist = re.sub(r"<[^>]+>", "",
                            str((meta.get("Artist") or {}).get("value") or "")).strip()
            lic = str((meta.get("LicenseShortName") or {}).get("value") or "")
            credit = "फुटेज: " + (artist or "Wikimedia Commons")
            if lic:
                credit += " / " + lic
            return url, credit[:120]
    return "", ""


def pixabay_clip(query):
    """Pixabay ki chalti footage. Chaabi ho to hi chalti hai."""
    key = cfg.get("pixabay", "api_key")
    if not key:
        return "", ""
    try:
        data = sy_net.get_json(
            "https://pixabay.com/api/videos/?per_page=10&safesearch=true&key="
            + key + "&q=" + sy_net.urllib.parse.quote(query), timeout=30)
    except Exception as e:
        log("pixabay video:", e)
        return "", ""
    for h in (data.get("hits") or []):
        hay = str(h.get("tags") or "") + " " + str(h.get("pageURL") or "")
        if not relevant(hay, query):
            continue
        vids = h.get("videos") or {}
        for size in ("large", "medium", "small"):
            v = vids.get(size) or {}
            if int(v.get("width") or 0) >= 960 and v.get("url"):
                return str(v["url"]), "Pixabay / " + str(h.get("user") or "Pixabay")
    return "", ""


def pixabay_photo(query):
    key = cfg.get("pixabay", "api_key")
    if not key:
        return "", ""
    try:
        data = sy_net.get_json(
            "https://pixabay.com/api/?image_type=photo&orientation=horizontal"
            "&per_page=10&safesearch=true&key=" + key
            + "&q=" + sy_net.urllib.parse.quote(query), timeout=30)
    except Exception as e:
        log("pixabay photo:", e)
        return "", ""
    for h in (data.get("hits") or []):
        hay = str(h.get("tags") or "") + " " + str(h.get("pageURL") or "")
        if not relevant(hay, query):
            continue
        url = h.get("largeImageURL") or h.get("webformatURL")
        if url:
            return str(url), "Pixabay / " + str(h.get("user") or "Pixabay")
    return "", ""


def openverse_photo(query):
    try:
        data = sy_net.get_json(
            "https://api.openverse.org/v1/images/?page_size=6&license_type=all&q="
            + sy_net.urllib.parse.quote(query), timeout=30)
    except Exception as e:
        log("openverse:", e)
        return "", ""
    for r in (data.get("results") or []):
        url = r.get("url")
        if not url:
            continue
        # SVG nahi. Openverse par zilon ke naksha aur chihn aksar SVG mein
        # hote hain - "Mirzapur" par wahi aaya tha. ffmpeg SVG kholta hi
        # nahi ("no decoder found for: svg"), aur wo poora drishya girata
        # hai. Yahan jaanch thi hi nahi; Commons par thi.
        if re.search(r"\.svgz?($|\?)", str(url), re.I) or \
                str(r.get("filetype") or "").lower() in ("svg", "svgz"):
            continue
        if not relevant(str(r.get("title") or "") + " " + str(r.get("tags") or ""),
                        query, stock=False):
            continue
        who = str(r.get("creator") or "Openverse")
        lic = str(r.get("license") or "").upper()
        return str(url), ("चित्र: %s / %s (Openverse)" % (who, lic))[:120]
    return "", ""


# ------------------------------------------------------------- laana

def _frame_from_clip(workdir):
    """Clip ka ek frame thumbnail ke liye. Isse thumbnail aur video ek hi
    drishya dikhate hain - do alag tasveerein rakhne se channel bikhra
    hua lagta hai."""
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", "2", "-i", "clip.mp4", "-frames:v", "1",
                        "-vf", "scale='max(1920,iw)':-2:flags=lanczos",
                        "-q:v", "3", "photo.jpg"],
                       cwd=workdir, check=True, timeout=120)
        return True
    except Exception as e:
        log("clip se frame nahi nikla:", e)
        return False


def _shot_plan(queries, shot_type="", place=""):
    """Ek tukde ke liye kis kram se dhoondhein.

    Pehle Commons aur Openverse - wahan asli, licence wali tasveer hoti hai
    aur "jahan ki khabar wahan ki tasveer" wahi se milti hai. Stock uske
    baad, aur sirf un shot par jinpar wo sach reh sakta hai.
    """
    plan = []
    # SARVAJANIK CHEHRA SABSE PEHLE.
    #
    # Agar tukda kisi aadmi ka hai, to pehli koshish uska NAAM hai - seedhe
    # Wikipedia ke lekh se uski apni tasveer. Ye Commons ki poore-text wali
    # khoj se kahin pakka hai: "Rahul Gandhi" par Commons ki khoj kuch bhi
    # laa sakti hai, par lekh ki mukhya tasveer wahi hoti hai jise duniya
    # us aadmi ki pehchan maanti hai.
    #
    # portrait() khud jaanchta hai ki lekh us naam ka hi hai; naam na mila
    # to wo khaali lauta ta hai aur neeche wali khoj apna kaam karti hai.
    # Aam nagrik ka naam yahan aata hi nahi - art director use naam se
    # likhta hi nahi (SHOT_RULES dekhiye).
    if str(shot_type or "").lower() == "people":
        # Pehli khoj us vyakti ka poora naam hoti hai (SHOT_RULES,
        # ensure_people_shots). Chalti footage mile to wo sabse pehle -
        # chehra bolta/chalta dikhe to tasveer se kahin zyada pakadta hai.
        if queries:
            plan.append(("commons_video", commons_person_clip, queries[0]))
        for q in queries:
            plan.append(("commons", portrait, q))
        if queries:
            plan.append(("commons", commons_person_photo, queries[0]))
            plan.append(("gov", gov_photo, queries[0]))

    # Pehle wo teen jagah jahan tasveer ASLI cheez ki hoti hai. Commons ki
    # chalti footage bhi yahin aati hai - wo stock nahi hai, wo asli
    # recording hai, isliye har tarah ke shot par chalti hai.
    #
    # Har khoj do baar jaati hai: poori, aur phir sirf KHAAS NAAM.
    # Commons ka search lambe vaakya par kamzor hai - "Bhadohi district
    # stadium Uttar Pradesh" par shaayad kuch na mile, par "Bhadohi Uttar
    # Pradesh" par mil jaye. Yahi wo doosri koshish hai jo pehle thi hi
    # nahi, aur isi wajah se jagah ki asli tasveerein chhoot rahi thi.
    # Commons ko ek khabar par darjanon baar nahi pukarte. Har request ke
    # beech ek second ka antar hai (unka apna niyam), aur har bekaar
    # request seedhe rate-limit ki taraf le jaati hai - wahi 429 tha.
    # Isliye: tasveer har khoj par, par CHALTI FOOTAGE sirf pehli khoj par
    # (Commons par video waise bhi kam hai), aur naam-wali chhoti khoj
    # sirf pehli do par.
    for i, q in enumerate(queries):
        plan.append(("commons", commons_photo, q))
        if i == 0:
            plan.append(("commons_video", commons_clip, q))
        plan.append(("openverse", openverse_photo, q))
        nq = narrow(q) if i < 2 else ""
        if nq:
            plan.append(("commons", commons_photo, nq))

    # Stock sirf un shot par jinpar wo sach reh sakta hai.
    if str(shot_type or "").lower() not in STOCK_OK_TYPES:
        return plan

    for q in queries:
        plan.append(("pexels_video", pexels_clip, q))
        plan.append(("pixabay_video", pixabay_clip, q))
    for q in queries:
        plan.append(("pexels_photo", pexels_photo, q))
        plan.append(("pixabay_photo", pixabay_photo, q))

    # Sabse aakhri sahara: khabar ki apni JAGAH. Agar is tukde par kuch
    # nahi mila, to us shehar ki ek sacchi tasveer bhi kuch na hone se
    # behtar hai - kam se kam darshak ko dikhta hai ki baat kahan ki hai.
    if place:
        plan.append(("commons", commons_photo, place))
        plan.append(("openverse", openverse_photo, place))
    return plan


# --------------------------------------------------- dekh kar jaanchna
#
# YAHAN TAK JO BHI CHUNAV THA WO SIRF TEXT KA THA - khoj ke shabd file ke
# naam/tag se milte the (relevant()), aur agar mil gaye to tasveer bina
# DEKHE hi le li jaati thi. Isi se galat/kharab tasveerein aur kamzor
# thumbnail aate the: shabd mil jaana ye zaroori nahi batata ki tasveer
# ACHHI hai ya SACCHI hai.
#
# Ab har chuni hui tasveer (ya clip ka ek frame) le liye jaane se PEHLE
# Claude ko khud dikhai jaati hai - jaise ek picture editor akhri nazar
# daalta hai. Ye poore pipeline ko badalta nahi, sirf ek aakhri, dekh-kar
# waali jaanch jodta hai, aur har jagah "band ho jaaye to bhi ruko mat"
# wale usool par - jaanch na ho paaye to purana bharosa (text-milaan) hi
# chalta hai.

VISION_SYSTEM = "\n".join([
    'Aap ek Indian news channel ke senior picture editor hain. Aapko ek '
    'tasveer dikhai gayi hai jise ek khabar/bulletin mein dikhaya jaana '
    'prastaawit hai. Use dekhkar bataiye ki ye istemal ke laayak hai ya nahi.',
    '', 'Sirf JSON lautaiye, aur kuch nahi:',
    '{"ok": true/false, "reason": "ek chhota vaajib karan, Hindi ya English"}',
])


def _vision_gate_on():
    return cfg.num("media", "vision_gate", 1) == 1


def _vision_prompt(brief, query, is_thumb):
    lines = [
        "Ye tasveer is drishya ke liye chuni gayi hai: " + str(brief or query or ""),
        "Khoj ka shabd tha: " + str(query or ""),
        "",
        "REJECT (ok=false) kijiye SIRF agar koi saaf wajah ho:",
        "- Tasveer bilkul kisi aur, be-mel vishay ki lagti hai (jaise ek "
        "videshi corporate office/model jabki khabar Bharat ki kisi asli "
        "jagah/ghatna ki hai).",
        "- Ek bada, sthai watermark/logo/stock-site ka nishan tasveer ka "
        "bada hissa dhaak raha ho.",
        "- Tasveer itni dhundhli, andheri, ya kati-phati hai ki kuch bhi "
        "saaf pehchana na ja sake.",
        "- Ye kisi asli, pehchaane jaane wale AAM vyakti (aaropi/peedit/"
        "gawah/aam nagrik) ka seedha, saaf chehra dikha rahi ho - aisa "
        "chehra kabhi nahi dikhna chahiye.",
        # Sep 2026, gy_indus_202609: "Mohenjo-daro ki naaliyan" par ek
        # patthar ki murti-numa cheez, aur "Sindhu Ghati ka vistaar" wale
        # naksha par 19vi sadi ka Misr/Mesopotamia/Ariana naksha paas ho
        # gaye - shabd mile, par drishya wo cheez dikhata hi nahi tha.
        "- Drishya jis KHAAS cheez/jagah ka naam leta hai (jaise koi "
        "prachin shehar, naali, naksha jisme koi ilaaka dikhna hai), wo "
        "tasveer mein dikhti hi nahi - sirf milta-julta vishay hai "
        "(kisi aur jagah ke khandhar, koi aur vastu, koi aur naksha).",
        # Sep 2026, st_9699961: Lucknow ke gaon mein teen mauton ke "shok"
        # par Pixabay ki videshi funeral - kaala suit, phoolon se dhaka
        # coffin - paas ho gayi, kyunki "grief" to dikh raha tha. Bharat
        # ki khabar par videshi reeti/pehnaawa pratikatmak bhi jhooth hai.
        "- Khabar Bharat ki hai par tasveer saaf videshi sanskriti/reeti "
        "dikhati hai (jaise coffin wali western funeral, church, videshi "
        "sadak/board/police) - pratikatmak tasveer par bhi ye reject.",
        "- Tasveer par kisi AUR jagah/sanstha ka padhne layak naam (board, "
        "signboard) likha ho jo is drishya ki jagah nahi hai.",
    ]
    if is_thumb:
        lines += [
            "",
            "Ye tasveer THUMBNAIL BANEGI - YouTube par darshak sabse pehle "
            "yahi dekhega. Isliye thodi zyada dhyaan se dekhiye: saaf, "
            "achhi roshni wali, ek nazar mein samajh aane wali honi chahiye.",
        ]
    lines += [
        "",
        "Baaki HAR haalat mein ok=true rakhiye - shak ho to true rakhiye. "
        "Yahan zaroorat se zyada sakht hona, kuch na dikhne se bura hai.",
    ]
    return "\n".join(lines)


def _vision_ok(path, brief, query, is_thumb, budget):
    """(ok, spent). spent=True matlab is check ne budget ka ek mauka liya.

    Jaanch band ho ya budget khatam ho to koshish hi nahi karte - us
    haalat mein ok=True (spent=False), kyunki wahan koi jaanch chali hi
    nahi.

    LEKIN agar jaanch chalayi aur wo khud hi gir gayi (API error, jawab
    na aaya, tasveer na khuli) - to ye is TASVEER ko paas nahi karte
    (ok=False, spent=True). Pehle yahan har asafal jaanch par ok=True
    aata tha - matlab agar jaanch hi na chal payi to jo bhi tasveer
    utri thi wo bina dekhe seedhe swikaar ho jaati thi, chahe wo drishya
    se bilkul be-mel ho (jaise "UP Roadways bus depot" ke brief par ek
    alag hi jashn ki aag ki tasveer chuni gayi - Sep 2026, Magh Mela
    video). Ab asafal jaanch ka matlab hai: is tasveer ko chhodo, agli
    koshish karo. Sabhi umeedwaar khatam ho jaayein tab bhi render nahi
    rukta - fetch_shots() us shot ke liye labeled AI chitran (AAKHRI
    SAHARA) par chala jaata hai, isliye "ok=false" kehna surakshit hai."""
    if not _vision_gate_on() or budget <= 0:
        return True, False
    try:
        j = sy_ai.ask_vision_json(VISION_SYSTEM, _vision_prompt(brief, query, is_thumb), path,
                                  max_tokens=200)
    except Exception as e:
        log("  vision jaanch nahi ho payi - ye tasveer chhod rahe hain:", e)
        return False, True
    if j is None:
        log("  vision jaanch se jawab nahi mila - ye tasveer chhod rahe hain")
        return False, True
    ok = j.get("ok") is not False
    if not ok:
        log("  vision ne mana kiya:", str(j.get("reason") or "")[:100])
    return ok, True


def _vision_ok_clip(clip_path, workdir, brief, query, is_thumb, budget):
    """Clip ke liye - pehle ek frame nikaalte hain, phir wahi tasveer jaanch."""
    if not _vision_gate_on() or budget <= 0:
        return True, False
    frame = os.path.join(workdir, "_vision_frame.jpg")
    try:
        subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                        "-ss", "1.5", "-i", clip_path, "-frames:v", "1",
                        "-vf", "scale='max(960,iw)':-2:flags=lanczos",
                        "-q:v", "5", frame],
                       check=True, timeout=60)
    except Exception as e:
        # Frame hi nahi nikla to clip bina dekhe paas nahi - _vision_ok ke
        # asafal-jaanch wale usool ki tarah (gy_indus_202609 ke baad).
        log("  vision ke liye frame nahi nikla - ye clip chhod rahe hain:", e)
        return False, True
    try:
        return _vision_ok(frame, brief, query, is_thumb, budget)
    finally:
        try:
            os.remove(frame)
        except Exception:
            pass


def fetch_shots(story, workdir, anchor_slots=0):
    """Har tukde ke liye ek alag drishya laao.

    Lauta ta hai wahi shot list, par har shot mein file aur credit jud kar.
    Jis shot par kuch na mile uski file khaali rehti hai - use aage jodne
    wale ko sambhalna hai, yahan use chhod dena galat hoga.

    Ek hi tasveer do shot par nahi lagti. Wo cut to dikhata hai par kuch
    kehta nahi - screen bhar raha hai, bas. Isliye jo url ek baar lag chuka
    hai wo dobara nahi liya jaata.
    """
    cfg.put_ffmpeg_on_path()
    try:
        shots = json.loads(story.get("shots") or "[]")
    except Exception:
        shots = []
    if not shots:
        return []
    shots = ensure_people_shots(story, shots)

    # Khabar ki apni jagah - angrezi mein, taaki khoj mein kaam aaye.
    place = ""
    for sh in shots:
        for q in (sh.get("queries") or []):
            n = narrow(q)
            if n:
                place = n.split()[0]
                break
        if place:
            break

    # Kaun sa beat aur kaun si shakl - dono AI chitran wale aakhri sahare
    # ke liye chahiye (neeche dekhiye). Khabar par wo chalta hi nahi.
    beat = str(story.get("beat") or "")
    vertical = beat in ("bolly", "viral")

    used_urls = set()
    anchor_left = int(anchor_slots or 0)
    got = 0
    for i, sh in enumerate(shots):
        sh["file"] = ""
        sh["credit"] = ""
        sh["source"] = ""
        sh.pop("anchor_planned", None)
        # Pehla tukda usually thumbnail bhi banta hai (thumb_art() shots
        # ko kram se dekhta hai) - isliye ispar vision jaanch zyada sakht.
        is_thumb = (i == 0)
        vbudget = VISION_MAX_TRIES
        found = False
        for name, fn, q in _shot_plan(sh.get("queries") or [], sh.get("type"), place):
            # Budget khatam - aage ka har candidate bina dekhe aata, isliye
            # yahin ruko (VISION_MAX_TRIES ke upar gy_indus_202609 dekhiye).
            if _vision_gate_on() and vbudget <= 0:
                log("  %d: %d tasveerein dekh li, koi sahi nahi - khoj band"
                    % (i + 1, VISION_MAX_TRIES))
                break
            try:
                url, credit = fn(q)
            except Exception as e:
                log("  %d/%s: %s" % (i + 1, name, e))
                continue
            if not url or url in used_urls:
                continue
            try:
                if name in VIDEO_SOURCES:
                    path = os.path.join(workdir, "shot%d.mp4" % i)
                    size = sy_net.download(
                        url, path, max_bytes=MAX_CLIP_MB * 1024 * 1024)
                    if size < 200000:
                        os.remove(path)
                        continue
                    sh["kind"] = "clip"
                else:
                    path = os.path.join(workdir, "shot%d.jpg" % i)
                    size = sy_net.download(url, path, max_bytes=25 * 1024 * 1024)
                    if size < 4096 or not is_raster(path):
                        if size >= 4096:
                            log("  %d: ye tasveer nahi thi (shaayad SVG) - chhoda" % (i + 1))
                        os.remove(path)
                        continue
                    sh["kind"] = "photo"
            except Exception as e:
                log("  %d: utri nahi (%s): %s" % (i + 1, name, e))
                continue

            brief = sh.get("brief") or sh.get("text")
            if sh["kind"] == "clip":
                ok, spent = _vision_ok_clip(path, workdir, brief, q, is_thumb, vbudget)
            else:
                ok, spent = _vision_ok(path, brief, q, is_thumb, vbudget)
            if spent:
                vbudget -= 1
            if not ok:
                try:
                    os.remove(path)
                except Exception:
                    pass
                continue

            if name in REPRESENTATIVE:
                credit = ("प्रतीकात्मक फुटेज · " if sh["kind"] == "clip"
                          else "प्रतीकात्मक तस्वीर · ") + credit
            used_urls.add(url)
            sh["file"] = os.path.basename(path)
            sh["credit"] = credit
            sh["source"] = name
            got += 1
            found = True
            log("  %d. %s <- %s (%s)" % (i + 1, sh.get("type") or "?", name, q))
            break
        if not found:
            log("  %d. %s <- kuch nahi mila" % (i + 1, sh.get("type") or "?"))
            # ANCHOR KHUD YE LINE BOLEGI (Sep 2026, sirf jaankari video) -
            # Harshvardhan: "jahan asli footage na mile wahan ladki baaki ki
            # lines bole". To yahan AI chitran ka paisa nahi lagate; tukda
            # khaali chhod kar nishan lagate hain, aur sy_explainer render ke
            # baad usi video wali anchor ka ek clip is jagah jod deta hai. Anchor
            # na ban paaye to ye tukda studio par chalta hai (sy_scenes).
            if anchor_left > 0:
                anchor_left -= 1
                sh["anchor_planned"] = True
                log("  (ye line anchor bolegi)")
                continue
            # AAKHRI SAHARA - muft srot mein is tukde ka koi drishya hai hi
            # nahi. Ab (Sep 2026) khabar/bulletin bhi isi sahare mein
            # shaamil hain, gyan/kaam/yojana ki tarah - saaf label ke
            # saath, kisi ghatna ka jhootha "saboot" banaye bina (poori
            # wajah aur teen shart sy_veo.py ke shuru mein hai). sy_veo
            # khud jaanchta hai ki beat allowed hai, din ki seema bachi hai
            # ya nahi, aur poora hissa chalu hai ya nahi.
            try:
                import sy_veo
                ok, why = sy_veo.allowed(beat)
                # beat bhi jaata hai - khabar par asli jagah ka naam prompt
                # mein nahi jaata (sy_veo NEWS_BEATS, st_9699961).
                prompt = sy_veo.prompt_for(sh, place, beat) if ok else ""
                if ok and not prompt:
                    # prompt_for khaali laut aaye to is tukde par kehne
                    # layak kuch hai hi nahi - Veo ko "kuch bhi bana do"
                    # kehna paisa aur samay dono ka nuksaan hai.
                    log("  (AI chitran nahi: is tukde par kuch thos nahi)")
                elif ok:
                    path = os.path.join(workdir, "shot%d.mp4" % i)
                    made, credit = sy_veo.make(
                        prompt, path, beat, vertical=vertical)
                    if made:
                        sh["kind"] = "clip"
                        sh["file"] = os.path.basename(path)
                        sh["credit"] = credit
                        sh["source"] = "veo"
                        got += 1
                        log("  %d. %s <- AI chitran" % (i + 1, sh.get("type") or "?"))
                elif "band hai" not in why:
                    log("  (AI chitran nahi: %s)" % why)
            except Exception as e:
                log("  (AI chitran mein gadbad: %s)" % str(e)[:90])

    log("%d/%d tukdon par drishya mila" % (got, len(shots)))
    return shots if got else []


def thumb_art(shots, workdir, story=None):
    """Thumbnail ke liye ek drishya photo.jpg mein rakh do. Jo shot chuna
    gaya wahi lautata hai (ya False).

    Thumbnail ka drishya video mein hona hi chahiye - warna darshak jis
    tasveer par click karta hai wo video mein milti hi nahi.

    VISHAY WALA DRISHYA PEHLE (Sep 2026): pehle hamesha pehla shot jaata
    tha. gy_konark_202609 mein pehla shot "zara sochiye aap samudra mein
    hain" wala hook tha - dolphin ki tasveer - aur thumbnail par "कोणार्क
    मंदिर" ke peeche dolphin tair rahi thi. Ab jaankari video (Wikipedia
    lekh wali) mein pehle wo shot jiski khoj mein lekh ka KHAAS NAAM ho
    (Konark...), phir baaki purane kram se. Khabar par kuch nahi badla.
    """
    order = list(shots or [])
    # KENDRA KA CHEHRA PEHLE: khabar kisi sarvajanik vyakti par ho aur uski
    # asli tasveer mili ho, to thumbnail wahi - wahi khabar ka hook hai.
    names = [n.lower() for n in story_people(story or {})]
    if names:
        faces = [sh for sh in order if sh.get("file") and sh.get("type") == "people"
                 and any(n in " ".join(sh.get("queries") or []).lower() for n in names)]
        order = faces + [sh for sh in order if sh not in faces]
    link = str((story or {}).get("source_link") or "")
    if "wikipedia.org/wiki/" in link:
        page = link.rsplit("/", 1)[-1].replace("_", " ")
        try:
            import urllib.parse
            page = urllib.parse.unquote(page)
        except Exception:
            pass
        key = proper_terms(page)
        if key:
            hit = [sh for sh in order if sh.get("file") and any(
                k in " ".join(sh.get("queries") or []).lower() for k in key)]
            order = hit + [sh for sh in order if sh not in hit]
    for sh in order:
        f = sh.get("file")
        if not f:
            continue
        src = os.path.join(workdir, f)
        dst = os.path.join(workdir, "photo.jpg")
        if sh.get("kind") == "photo":
            try:
                shutil.copyfile(src, dst)
                return sh
            except Exception as e:
                log("thumbnail ki tasveer nahi rakhi ja saki:", e)
                return False
        try:
            subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                            "-ss", "1.5", "-i", f, "-frames:v", "1",
                            "-vf", "scale='max(1920,iw)':-2:flags=lanczos",
                            "-q:v", "3", "photo.jpg"],
                           cwd=workdir, check=True, timeout=120)
            return sh
        except Exception as e:
            log("clip se frame nahi nikla:", e)
            return False
    return False


def fetch_media(story, workdir):
    """Video ke peeche kya chalega, wo laakar workdir mein rakh do.

    Lauta ta hai (image_credit, photo_source). Kuch na mile to dono khaali -
    us haalat mein render_core khud designed backdrop bana lega.
    """
    cfg.put_ffmpeg_on_path()
    try:
        queries = json.loads(story.get("photo_queries") or "[]")
    except Exception:
        queries = []
    if not story.get("wants_photo") or not queries:
        log("art director ne tasveer ki zaroorat nahi batayi")
        return "", ""

    # Kram hi asli faisla hai.
    #
    # Pehle Commons aur Openverse - HAR khabar par, sirf logon wali par
    # nahi. ISRO ki khabar par ISRO ke rocket ki asli tasveer wahan maujood
    # hai, licence ke saath. Pehle ye rasta sirf prasiddh vyakti ke liye
    # khula tha, aur isi wajah se ISRO ki khabar bina kisi tasveer ke chali
    # gayi - jabki uski asli tasveer ek khoj door thi. Wo meri hi galti thi.
    #
    # Jahan ki khabar, wahan ki tasveer. Uske baad hi chalti hui stock
    # footage, aur sabse aakhir mein generic stock tasveer.
    plan = []
    for q in queries[:2]:
        plan.append(("commons", commons_photo, q))
        plan.append(("commons_video", commons_clip, q))
        plan.append(("openverse", openverse_photo, q))
    for q in queries:
        plan.append(("pexels_video", pexels_clip, q))
        plan.append(("pixabay_video", pixabay_clip, q))
    for q in queries[2:]:
        plan.append(("commons", commons_photo, q))
        plan.append(("commons_video", commons_clip, q))
        plan.append(("openverse", openverse_photo, q))
    for q in queries:
        plan.append(("pexels_photo", pexels_photo, q))
        plan.append(("pixabay_photo", pixabay_photo, q))

    headline = str(story.get("headline_hi") or "")
    vbudget = VISION_MAX_TRIES
    for name, fn, q in plan:
        # Budget khatam to bina dekhe kuch nahi - designed backdrop galat
        # tasveer se behtar hai (gy_indus_202609, Sep 2026).
        if _vision_gate_on() and vbudget <= 0:
            break
        url, credit = fn(q)
        if not url:
            continue
        try:
            if name in VIDEO_SOURCES:
                path = os.path.join(workdir, "clip.mp4")
                size = sy_net.download(url, path, max_bytes=MAX_CLIP_MB * 1024 * 1024)
                if size < 200000:
                    os.remove(path)
                    continue
                if not _frame_from_clip(workdir):
                    os.remove(path)
                    continue
                # photo.jpg (abhi bana frame) hi thumbnail banega - isliye
                # is par is_thumb=True se jaanch hoti hai.
                thumb = os.path.join(workdir, "photo.jpg")
                ok, spent = _vision_ok(thumb, headline, q, True, vbudget)
                if spent:
                    vbudget -= 1
                if not ok:
                    for p in (path, thumb):
                        if os.path.exists(p):
                            os.remove(p)
                    continue
                log("clip mili (%.1f MB): %s" % (size / 1048576.0, credit))
                if name in REPRESENTATIVE:
                    credit = "प्रतीकात्मक फुटेज · " + credit
                return credit, name
            path = os.path.join(workdir, "photo.jpg")
            size = sy_net.download(url, path, max_bytes=25 * 1024 * 1024)
            if size < 2048 or not is_raster(path):
                os.remove(path)
                continue
            ok, spent = _vision_ok(path, headline, q, True, vbudget)
            if spent:
                vbudget -= 1
            if not ok:
                os.remove(path)
                continue
            log("tasveer mili (%s): %s" % (name, credit))
            if name in REPRESENTATIVE:
                credit = "प्रतीकात्मक तस्वीर · " + credit
            return credit, name
        except Exception as e:
            log("  utaari nahi ja saki (%s): %s" % (name, e))
            continue

    log("kuch nahi mila - designed backdrop chalega")
    return "", ""

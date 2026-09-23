"""Khabar dhoondhna aur script likhwana - dono beat ke liye.

  run_news()    - ilaake ki khabar pehle (Prayagraj, Varanasi, Mirzapur,
                  Bhadohi, Lucknow), rashtriya khabar seemit ginti mein
  run_yojana()  - chal rahi sarkari yojanaon ki jaankari - jagrukta ke liye,
                  sirf nayi ghoshna par nahi

Dono ka nateeja ek hi jagah jaata hai: sy_store mein ek pending story.
Uske aage video banane wala hissa dono ko ek jaisa hi bartata hai.
"""
import json
import re
import time
import urllib.parse

import sy_ai
import sy_config as cfg
import sy_net
import sy_store as st

# --------------------------------------------------------------- feeds

# Aapka darshak Prayagraj, Varanasi, Mirzapur, Bhadohi aur Lucknow mein hai.
# Isliye pehle uske apne ilaake ki khabar - wahi wo khabar hai jo wo kisi
# aur jagah se aasani se nahi paata. Rashtriya aur antarrashtriya khabar
# har jagah milti hai, isliye uski ginti seemit rakhi jaati hai.
#
# (source, url, sheher)
LOCAL_FEEDS = [
    ("AMAR_UJALA", "https://www.amarujala.com/rss/allahabad.xml", "प्रयागराज"),
    ("AMAR_UJALA", "https://www.amarujala.com/rss/varanasi.xml", "वाराणसी"),
    ("AMAR_UJALA", "https://www.amarujala.com/rss/mirzapur.xml", "मिर्ज़ापुर"),
    ("AMAR_UJALA", "https://www.amarujala.com/rss/bhadohi.xml", "भदोही"),
    ("AMAR_UJALA", "https://www.amarujala.com/rss/lucknow.xml", "लखनऊ"),
    ("AMAR_UJALA", "https://www.amarujala.com/rss/uttar-pradesh.xml", "उत्तर प्रदेश"),
]

# (source, url, wire, google_news)
NEWS_FEEDS = [
    # Wire - sabse tez, par inke link Google News ke opaque URL hote hain,
    # isliye inka poora lekh nahi padha ja sakta. Ye corroboration ke liye
    # hain, gehrai ke liye nahi.
    ("PTI", "https://news.google.com/rss/search?q=when:12h+site:ptinews.com"
            "&hl=en-IN&gl=IN&ceid=IN:en", True, True),
    ("ANI", "https://news.google.com/rss/search?q=when:12h+site:aninews.in"
            "&hl=en-IN&gl=IN&ceid=IN:en", True, True),
    # Inke link asli hote hain - script ki gehrai inhi se aati hai.
    ("THE_HINDU", "https://www.thehindu.com/news/national/feeder/default.rss",
     False, False),
    ("THE_HINDU", "https://www.thehindu.com/news/states/feeder/default.rss",
     False, False),
    ("HINDUSTAN_TIMES",
     "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml",
     False, False),
    # NDTV ka page Akamai se 403 deta hai - lekh nahi milta, par khabar ki
    # pushti ke liye wo phir bhi kaam ka hai.
    ("NDTV", "https://feeds.feedburner.com/ndtvnews-india-news", False, False),
    ("AAJ_TAK", "https://www.aajtak.in/rssfeeds/?id=home", False, False),
]

# Ek feed se itni hi khabrein - ye newest-first hoti hain, aur puri list
# uthane se clustering bewajah bhaari ho jaati hai.
PER_FEED = 30

# Rashtriya khabar ki roz ki seema. Ye channel ka faisla hai, technical
# majboori nahi: rashtriya khabar har jagah milti hai, ilaake ki nahi.
NATIONAL_PER_DAY = 2

TREND_FEED = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"

YOJANA_FEEDS = [
    ("PRESS_INFORMATION_BUREAU", "PIB",
     "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=2&Regid=3", 2),
    ("AMAR_UJALA", "Amar Ujala",
     "https://www.amarujala.com/rss/utility.xml", 0),
]

# Jaanch ka nateeja, andaza nahi: in publishers ke lekh sach mein khulte hain.
FETCHABLE = ("thehindu.com", "thehindubusinessline.com", "frontline.thehindu.com",
             "hindustantimes.com", "scroll.in")

STOP = set("""the and for with from that this says after over india news will
been into more amid ahead have has was were their they what when where which
about against among under above than then them these those""".split())


def log(*a):
    print("[ingest]", *a, flush=True)


# ----------------------------------------------------------- helpers

def tokens(s):
    words = re.sub(r"[^a-z0-9ऀ-ॿ ]", " ", str(s or "").lower()).split()
    return set(w for w in words if len(w) > 3 and w not in STOP)


def story_id(title, prefix="st_"):
    key = re.sub(r"[^a-z0-9ऀ-ॿ ]", "", str(title or "").lower())
    key = re.sub(r"\s+", " ", key).strip()
    h = 0
    for ch in key:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    if h >= 0x80000000:
        h -= 0x100000000
    return prefix + format(abs(h), "x")


def same_story(a, b):
    """Kya ye dono ek hi ghatna hain? Wahi niyam jo grouping mein lagta hai."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb)
    return overlap >= 3 and overlap / (min(len(ta), len(tb)) or 1) >= 0.4


def already_covered(title):
    """Ye khabar pehle dekhi ja chuki hai?

    Sirf hash se kaam nahi chalta - wo tabhi milta hai jab shirshak akshar
    dar akshar wahi ho. Asal mein kal ki khabar aaj thode alag shabdon mein
    aati hai, aur do outlets to hamesha alag likhte hain. Isliye shabdon ka
    milaan karte hain, wahi jo ek hi ghatna ki khabron ko jodne mein lagta
    hai.
    """
    for old in st.recent_titles():
        if same_story(title, old):
            return True
    return False


def link_rank(url):
    s = str(url or "")
    if not s:
        return 9
    if "news.google.com" in s:
        return 3
    for h in FETCHABLE:
        if h in s:
            return 0
    return 1


def read_feed(url, label):
    try:
        return sy_net.parse_rss(sy_net.get_text(url, timeout=40))
    except Exception as e:
        # Ek feed ke girne se poora run nahi girna chahiye.
        log("feed nahi mili (%s): %s" % (label, e))
        return []


# -------------------------------------------------------------- news

def normalise():
    out = []
    now = time.time()

    for source, url, city in LOCAL_FEEDS:
        for it in read_feed(url, city)[:PER_FEED]:
            title = it["title"]
            if len(title) < 20 or len(title.split()) < 4:
                continue
            if SLIDESHOW.search(it["link"]):
                continue
            ts = sy_net.parse_date(it["published"])
            out.append({
                "story_id": story_id(title),
                "title": title,
                "link": it["link"],
                "summary": re.sub(r"<[^>]*>", "", it["summary"])[:1200],
                "source": source,
                "publisher": source,
                "is_wire": False,
                "age_hours": (now - ts) / 3600.0 if ts else None,
                "scope": "local",
                "city": city,
            })

    for source, url, wire, gnews in NEWS_FEEDS:
        for it in read_feed(url, source)[:PER_FEED]:
            title = it["title"]
            publisher = ""
            src = source
            if gnews:
                # Google News ka title "Headline - Publisher" hota hai.
                cut = title.rfind(" - ")
                if cut > 20:
                    publisher = title[cut + 3:].strip()
                    src = re.sub(r"[^A-Z0-9]+", "_", publisher.upper())[:20]
                    title = title[:cut].strip()
            if len(title) < 20 or len(title.split()) < 4:
                continue
            if publisher and title.lower() == publisher.lower():
                continue
            if SLIDESHOW.search(it["link"]):
                continue

            ts = sy_net.parse_date(it["published"])
            # Aaj Tak ka feed rashtriya hai, par usmein UP ki khabrein bhi
            # aati hain - unhe link se pehchan kar local maan lete hain.
            scope = "national"
            city = ""
            if "/uttar-pradesh/" in it["link"]:
                scope, city = "local", "उत्तर प्रदेश"
            out.append({
                "story_id": story_id(title),
                "title": title,
                "link": it["link"],
                "summary": re.sub(r"<[^>]*>", "", it["summary"])[:1200],
                "source": src,
                "publisher": publisher or source,
                "is_wire": wire,
                "age_hours": (now - ts) / 3600.0 if ts else None,
                "scope": scope,
                "city": city,
            })
    return out


# ------------------------------------------------------- bade tabke ka kaam
#
# Ab tak khabar ki ranking sirf ginti se chalti thi - kitne akhbaaron ne
# chhaapi (corroboration), kitni taazi hai, trending shabd se kitna milti
# hai, aur local hai ya nahi (cluster() mein score). Inmein se kisi mein
# ye nahi dekha jaata tha ki khabar ka ASAR kitne logon par padta hai - ek
# mohalle ke do logon ki niji kahasuni bhi utni hi jagah paa sakti thi
# jitni poore shehar ko chhoone wali baat. Ye jaanch sirf itna dekhti hai:
# kya is khabar ka asar/kaam ek bade tabke tak jaata hai? Sirf khabar/
# local par lagti hai - gyan/kaam/yojana/Reel ka apna alag rasta hai aur
# unpar "random khabar" wali shikayat thi bhi nahi.
RELEVANCE_SYSTEM = "\n".join([
    'Aap ek Hindi news channel ke sampadak hain. Aapko ek khabar ka '
    'shirshak aur summary dikhaya jaayega.',
    '', 'Poochhna hai: kya is khabar ka asar ya kaam POORE SHEHAR/ZILE ke '
    'aam logon tak jaata hai - paisa, suraksha, sehat, mausam, sadak/'
    'traffic, bijli-pani, shiksha, sarkari yojana/aadesh, bada hadsa/'
    'apradh, chunav/prashasan jaisi baat? Ya ye sirf EK-DO vyakti/ghar ki '
    'nitaant niji, mamuli baat hai jiska asar kisi aur par nahi padta '
    '(chhoti aapasi kahasuni, mamuli chori, ek-do logon ka jhagda)?',
    '', 'Shak ho ya beech ki baat ho to relevant=true rakhiye - galti se '
    'ek achhi khabar chhootni, galti se ek mamuli khabar chalne se zyada '
    'buri hai.',
    '', 'Sirf JSON lautaiye: {"relevant": true/false, "reason": "ek '
    'chhota vaajib karan"}',
])


def audience_relevant(headline, summary=""):
    """(ok, reason). Jawab na aaye ya jaanch fail ho to hamesha ok=True -
    ye ek naram, aakhri jaanch hai, kabhi kisi khabar ko atkana nahi
    chahiye sirf isliye ki AI se jawab nahi mila."""
    user = "\n".join([
        "Shirshak: " + str(headline or ""),
        "Summary: " + str(summary or "")[:400],
    ])
    try:
        j = sy_ai.ask_json(RELEVANCE_SYSTEM, user, max_tokens=200)
    except Exception as e:
        return True, "jaanch nahi ho payi: %s" % str(e)[:80]
    if j is None:
        return True, "jawab nahi mila"
    if j.get("relevant") is False:
        return False, str(j.get("reason") or "bade tabke ke kaam ki nahi lagi")[:150]
    return True, ""


def trend_tokens():
    """Aaj kya bada chal raha hai - sirf boost ke liye, chhanti ke liye nahi."""
    tk = set()
    for it in read_feed(TREND_FEED, "trends"):
        tk |= tokens(it["title"])
    return tk


def cluster(stories, trends):
    """Ek hi ghatna par aayi alag-alag khabron ko ek jagah laana."""
    groups = []
    for s in stories:
        tk = tokens(s["title"])
        if not tk:
            continue
        placed = False
        for g in groups:
            overlap = len(tk & g["tokens"])
            denom = min(len(tk), len(g["tokens"])) or 1
            # 3 shabd match AND 40% overlap. 50% bahut sakht tha - alag
            # outlets ek hi khabar ka shirshak alag tarah likhte hain.
            if overlap >= 3 and overlap / denom >= 0.4:
                g["members"].append(s)
                g["tokens"] |= tk
                placed = True
                break
        if not placed:
            groups.append({"tokens": tk, "members": [s]})

    out = []
    for g in groups:
        members = g["members"]
        sources = sorted(set(m["source"] for m in members))
        links = sorted((m["link"] for m in members if m["link"]), key=link_rank)

        ages = [m["age_hours"] for m in members if m["age_hours"] is not None]
        age = min(ages) if ages else None
        # Tareekh na mile to freshness ka faayda nahi milta. Pehle aisi
        # khabar ko poora number mil jaata tha aur wo taazi khabar se aage
        # nikal jaati thi.
        fresh = 0.0 if age is None else max(0.0, 4.0 - age / 3.0)

        hits = len(g["tokens"] & trends)
        best = max(members, key=lambda m: (m["is_wire"], len(m["title"])))
        scope = "local" if any(m.get("scope") == "local" for m in members) else "national"
        city = ""
        for m in members:
            if m.get("city"):
                city = m["city"]
                break

        # Ilaake ki khabar ko bada badhawa. Ye channel ka faisla hai: wahi
        # khabar aapke darshak ko kahin aur se aasani se nahi milti.
        local_boost = 10 if scope == "local" else 0

        out.append({
            "story_id": best["story_id"],
            "src_title": best["title"],
            "title": best["title"],
            "summary": best["summary"],
            "sources": sources,
            "corroboration": len(sources),
            "links": links[:6],
            "scope": scope,
            "city": city,
            "score": round(len(sources) * 3 + fresh + min(hits, 3) + local_boost, 2),
        })
    out.sort(key=lambda x: -x["score"])
    return out


# Itne se chhota "lekh" lekh nahi hota. 400 par safhe ka title, menu aur
# "yah bhi padhein" ki list bhi paas ho jaati thi - aur wo sampadak ke paas
# "POORA LEKH" ka thappa lagakar jaati thi. Sampadak sahi keh kar mana kar
# deta ("koi thos reportable jaankari nahi hai... sirf page title, navigation")
# par tab tak khabar mari ja chuki hoti thi aur ek call ka paisa bhi lag
# chuka hota tha - jabki uske paas RSS ka summary maujood tha jisse wo ek
# chhoti si sahi script likh sakta tha.
#
# Ab itna text na mile to hum jhooth nahi bolte: summary ko summary kehkar
# bhejte hain, aur sampadak uspar chhoti script likh deta hai.
MIN_ARTICLE = 900


def pick_article(links):
    """Lekh laane ki teen koshish, sabse khulne wale link se shuru.

    Purane system mein sirf ek hi link aazmaya jaata tha - wo 403 de deta
    to script RSS ke chhote summary par ruk jaati thi, chahe doosra link
    khulta hi kyun na ho.
    """
    best = ("", "")
    # TEEN SE CHHAH.
    #
    # Pehle sirf teen link aazmaye jaate the. Us waqt link Google News se
    # aate the aur teen se zyada hote hi nahi the, isliye wo seema muft
    # dikhti thi. Ab pate GDELT se aate hain - ek hi vishay par 12 alag
    # akhbaar tak - aur teen par ruk jaana apne aap mein nuksan hai: teeno
    # 403 de dein to khabar chhod di jaati hai, jabki chautha khul raha
    # hota hai.
    #
    # Sabse khulne wale pehle - taaki chhah tak jaana kam hi pade.
    ordered = sorted(links, key=link_rank)
    for url in ordered[:6]:
        if link_rank(url) >= 3:
            continue
        try:
            text = sy_net.article_text(sy_net.get_text(url, timeout=45),
                                       min_chars=MIN_ARTICLE)
        except Exception as e:
            log("  lekh nahi khula:", sy_net.host(url), e)
            continue
        if text:
            log("  lekh mila (%d akshar): %s" % (len(text), sy_net.host(url)))
            return url, text
        # Kuch to mila par kaam layak nahi - agla link aazmate hain.
        log("  safha khula par lekh nahi mila (%d akshar se kam): %s"
            % (MIN_ARTICLE, sy_net.host(url)))
    return best


EDITOR_SYSTEM = "\n".join([
    'Aap ek Indian digital news channel ke senior editor hain. Aap source copy se Hindi aur English dono mein broadcast scripts likhte hain.',
    '',
    'HARD RULES - inka ullanghan matlab story kill:',
    '1. Sirf wahi likhein jo diye gaye source material mein hai. Koi number, naam, jagah, tareekh ya quote khud se mat jodiye.',
    '2. Agar sources kisi material fact par alag-alag hain, to kisi ek ko mat chuniye - publishable false kar dijiye aur kill_reason mein wajah likhiye.',
    '3. Agar story kisi chal rahi jaanch, mrityu sankhya, chunav parinaam, adalati faisle, ya sampradayik ghatna se judi hai aur do se kam sources sehmat hain, to publishable false kar dijiye.',
    '4. Vivadit daawon ko script mein hi attribute kijiye. Kisi aarop ko sthapit tathya ki tarah mat likhiye.',
    '',
    'AKHBAAR KA NAAM SCRIPT MEIN KABHI NAHI - ye sakht hai:',
    'Jis akhbaar ya agency se ye khabar li gayi hai, uska naam script_hi aur script_en mein KAHIN NAHI aana chahiye. Ek baar bhi nahi - na shuru mein, na beech mein, na aakhir mein.',
    'Na "अमर उजाला के मुताबिक", na "अमर उजाला ने बताया", na "इस खबर को अमर उजाला ने रिपोर्ट किया है".',
    'Wajah: script boli jaati hai aur screen par bhi dikhti hai. Doosre akhbaar ka naam bar-bar sunkar darshak ko lagta hai ki hum khud kuch nahi jaante. Uski shreya ki jagah YouTube ka description hai, aur wahan wo apne aap jud jaati hai.',
    'Script apni aawaaz mein seedhi likhiye: "आठ वार्डों में काम शुरू हो गया है".',
    '',
    'Par ye attribution BILKUL bani rehti hai - inhe hatana khabar ko kamzor karta hai:',
    '  (a) Koi AAROP ya vivadit daawa - "परिवार का आरोप है कि...", "पुलिस के मुताबिक...".',
    '  (b) Koi adhikari, vibhag ya vyakti ka bayan - "डीआईजी ने कहा", "नगर निगम के मुताबिक".',
    'Yaani jis SANSTHA ya VYAKTI ne baat kahi hai uska naam rahega. Sirf us AKHBAAR ka naam nahi jisse hume khabar mili.',
    '5. Motive par koi kalpana nahin, koi bhavishyavani nahin, koi rai nahin.',
    '6. AGAR IS KHABAR KO IMAANDARI SE DIKHAYA HI NAHI JA SAKTA, TO publishable false.',
    '   Ye ek television channel hai, akhbaar nahi. Kuch khabrein aisi hoti hain jinka poora vazan EK NIJI VYAKTI par tika hota hai - ek shaheed jiski tasveer hamare paas nahi, ek mahila jo sarvajanik roop se shikayat kar rahi hai, ek peedit parivaar. Aisi khabar mein wo chehra hi khabar hai.',
    '   Uska chehra hum dikha nahi sakte - wo niji vyakti hai, aur unki tasveer bina ijaazat dikhana galat hai. Aur uske bina screen par sirf koi aam imaarat ya sadak reh jaati hai, jiska khabar se koi lena-dena nahi. Darshak ko lagta hai ki hum kuch dikha hi nahi rahe.',
    '   Isliye poochhiye: is khabar ke saath aisa KYA hai jo sach mein dikhaya ja sakta hai - koi sanstha, koi jagah, koi daftar, koi kaam, koi cheez, koi bheed, koi ghatna-sthal? Agar HAAN, to khabar theek hai.',
    '   Agar khabar mein us vyakti ke bayan ke alawa dikhane layak kuch bhi nahi hai, to publishable false kar dijiye aur kill_reason mein likhiye: "dikhaane layak kuch nahi - poori khabar ek niji vyakti par tiki hai".',
    '   Ye kamzori nahi, chunaav hai. Ek channel wahi khabar uthata hai jise wo theek se keh sakta hai. Jo khabar bina sacchi tasveer ke chalegi wo darshak ko radio jaisi lagegi, aur uspar mehnat aur paisa dono bekaar jaate hain.',
    '',
    'REPORTING KI GEHRAI - ispar sabse zyada dhyaan dijiye:',
    'Jab aapko poora article text diya gaya ho, to script mein wo saari thos jaankari aani chahiye jo us text mein maujood hai. Kam se kam ye bindu, jitne source mein hain:',
    '- KAB: ghatna kab hui, aadesh kab jaari hua, kitne din pehle ka mamla hai.',
    '- KAUN: naam, pad, kitne log, kis zile/sansthan ke.',
    '- KISNE: kis adhikari ya vibhag ne karyavahi ki, kis niyam ya aadesh ke tahat.',
    '- KYUN: aadhikarik roop se jo wajah batayi gayi.',
    '- AB KYA: maujooda sthiti - jaanch chal rahi hai, appeal hui, kisi ne bayan diya, agla kadam kya hai. Rajnitik pratikriya ho to kisne kya kaha, attribution ke saath.',
    'Jo bindu source mein NAHI hai use chhod dijiye - khaali jagah bharne ke liye kuch mat likhiye, aur na hi "sootron ke mutabik" jaisa dhundhla vaakya jodiye.',
    'Par jo maujood hai use chhodiye BILKUL mat. Ek line likh kar ruk jaana - jaise sirf ye keh dena ki do log nilambit hue - us reporting ke saath insaaf nahi hai jo aapke saamne rakhi gayi hai. Darshak ko wahi samajh milni chahiye jo poora lekh padhne par milti.',
    'Agar aapke paas sirf RSS ka chhota summary hai (poora lekh nahi), to jitna hai utna hi likhiye aur script chhoti rakhiye - us haalat mein adhoori jaankari se lambi script banana galat hai.',
    '',
    'STYLE: neutral wire-service tone. Hindi script saral boli jaane wali Hindi mein (Devanagari) - ise ek synthetic anchor padhega, isliye lambe sahityik vakya mat likhiye, chhote vakya likhiye. English script plain Indian-English broadcast style mein.',
    'LAMBAI: poora lekh mila ho to har script 180-220 shabd (lagbhag 80-100 second). Sirf summary mila ho to 110-140 shabd. Shabd bharne ke liye lambai mat badhaiye.',
    '',
    'Sirf ek JSON object return kijiye, bina markdown fence ke, in exact keys ke saath:',
    '{',
    '  "publishable": boolean,',
    '  "kill_reason": string,',
    '  "confidence": "high" | "medium" | "low",',
    '  "headline_hi": string, "headline_en": string,',
    '  "script_hi": string, "script_en": string,',
    '  "lower_third_hi": string, "lower_third_en": string,',
    '     ^ Ye screen ki laal patti mein ek hi lakeer mein aata hai. 60 AKSHAR SE '
    'ZYADA MAT LIKHIYE - us se lambi lakeer ko chal kar dikhana padta hai, aur '
    'chalti hui lakeer padhne mein hamesha thodi mushkil hoti hai. Ek baat, '
    'sabse zaroori waali. Poori khabar isme mat bhariye - wo script ka kaam hai. '
    'Do baaton ko "|" se jodna aksar ek ki jagah do khabrein bana deta hai; '
    'us se bachiye.',
    '  "broll_keywords": [string],',
    '  "youtube_title_hi": string, "youtube_title_en": string,',
    '  "title_options_hi": [string, string, string],',
    '     ^ TEEN alag title, teen alag soch se - aur teeno asli khabar par '
    'sacche. Pehla: jo click khinche (sawaal ya sabse chaunkane wali sacchi '
    'baat). Doosra: seedha khabar wala, jaisa koi bulletin padhta hai. '
    'Teesra: khoj wala - wo shabd aage jinhe log sach mein type karte hain '
    '(jagah ka naam, yojana ka naam, vyakti ka naam). Koi bhi title jhooth '
    'ya bada-chadha kar mat likhiye - clickbait channel ka bharosa khaata '
    'hai, aur bharosa hi is channel ki poonji hai. youtube_title_hi inhi '
    'teen mein se pehla rahega.',
    '  "youtube_description_hi": string, "youtube_description_en": string,',
    '  "tags": [string],',
    '  "attribution_line": string',
    '}',
    '',
    'youtube_title_* 90 characters se kam ho, ALL CAPS ya multiple exclamation marks na ho. broll_keywords English mein hon (stock footage search ke liye). youtube_description_* mein khabar ke mukhya bindu 2-3 chhote paragraph mein hon. Uske baad SOURCE KA POORA ZIKR - kis akhbaar ya agency ne ye khabar di, naam ke saath ("स्रोत: अमर उजाला"). Description hi wo jagah hai jahan source ka poora shreya diya jaata hai, isliye use yahan mat chhodiye. Aakhir mein ye line ho: Yah video samachar agency feeds se taiyar kiya gaya hai.',
])


def national_room():
    """Aaj aur kitni rashtriya khabar li ja sakti hai."""
    if st.kv_get("nat_day", "") != time.strftime("%Y-%m-%d"):
        return NATIONAL_PER_DAY
    return max(0, NATIONAL_PER_DAY - int(st.kv_get("nat_count", 0) or 0))


def note_national():
    if st.kv_get("nat_day", "") != time.strftime("%Y-%m-%d"):
        st.kv_set("nat_day", time.strftime("%Y-%m-%d"))
        st.kv_set("nat_count", 0)
    st.kv_set("nat_count", int(st.kv_get("nat_count", 0) or 0) + 1)


def run_news(max_new=2):
    """Ek chakkar: feeds se khabar, chhanti, lekh, script, aur store mein."""
    st.forget_old_seen()
    raw = normalise()
    log("feeds se", len(raw), "khabrein")
    if not raw:
        return 0

    groups = cluster(raw, trend_tokens())

    # Corroboration ka niyam dono par ek jaisa nahi ho sakta.
    #
    # Rashtriya khabar par do alag source ki shart bani rehti hai - wahan
    # galat khabar ka nuksaan bada hai aur doosra source milta bhi hai.
    #
    # Par Bhadohi ya Mirzapur ki khabar sirf ek hi akhbaar ke reporter ne
    # likhi hoti hai. Wahan do source maangna ka matlab hai ki ilaake ki
    # koi khabar kabhi chalegi hi nahi - aur wahi khabar aapke darshak ke
    # liye sabse zyada kaam ki hai. Isliye local par ek source kaafi hai,
    # aur script mein wo source saaf naam se likha jaata hai.
    local = [g for g in groups if g["scope"] == "local"]
    national = [g for g in groups if g["scope"] == "national"
                and g["corroboration"] >= 2]
    log("%d ghatnaayein | ilaake ki %d, rashtriya %d (do-source)"
        % (len(groups), len(local), len(national)))

    room = national_room()
    # Ilaake ki khabar pehle. Rashtriya sirf tab, aur utni hi jitni bachi hai.
    order = local + (national[:room] if room else [])

    made = 0
    for g in order:
        if made >= max_new:
            break
        if st.get(g["story_id"]) or st.seen(g["story_id"]):
            continue
        if already_covered(g["title"]):
            continue

        log("%s: %s" % (g["city"] or ("rashtriya" if g["scope"] == "national"
                                      else "ilaaka"), g["title"][:60]))
        url, text = pick_article(g["links"])

        head = ["SOURCE MATERIAL", "",
                "Headline: " + g["title"],
                "Corroborating sources (%d): %s" % (g["corroboration"],
                                                    ", ".join(g["sources"])),
                "Source links: " + " | ".join(g["links"]), ""]
        if g["city"]:
            head.insert(1, "Yah " + g["city"] + " ki khabar hai.")
        if text:
            head += ["POORA LEKH (" + sy_net.host(url) + ", " + url + "):", text, "",
                     "Aapke paas poora lekh hai. Upar di gayi gehrai wali sabhi "
                     "baatein - kab, kaun, kisne, kyun, ab kya - jitni is lekh "
                     "mein hain, utni script mein aani chahiye."]
        else:
            head += ["Wire summary (poora lekh nahi mil paya): " + g["summary"], "",
                     "Aapke paas poora lekh NAHI hai, sirf ye chhota summary hai. "
                     "Isliye chhoti script likhiye aur koi bhi tafseel khud se "
                     "mat jodiye."]
        if g["corroboration"] < 2:
            head += ["", "Is khabar par sirf EK source hai: " + ", ".join(g["sources"])
                     + ". Uska naam script mein KAHIN NAHI aana chahiye - "
                     "wo YouTube description mein apne aap jud jaata hai. "
                     "Ek source hone ka matlab itna hai ki koi bhi vivadit "
                     "daawa poore bharose se mat likhiye."]
        head += ["", "Bilingual bulletin scripts likhiye."]

        j = sy_ai.ask_json(EDITOR_SYSTEM, "\n".join(head), max_tokens=5000)

        # Jo bhi ho - kill, kharab jawab, ya safal - is khabar ko dobara nahi
        # uthana. Warna har do ghante wahi story phir se sampadak ke paas
        # jaayegi aur wahi paisa dobara lagega.
        st.mark_seen(g["story_id"])
        st.remember_title(g["title"])

        if not j:
            log("  sampadak ka jawab JSON nahi tha - chhoda")
            continue
        if j.get("publishable") is not True:
            log("  sampadak ne roka:", str(j.get("kill_reason") or "")[:120])
            continue

        script = re.sub(r"\s+", " ", str(j.get("script_hi") or "")).strip()
        if len(script) < 200:
            log("  script bahut chhoti - chhoda")
            continue

        st.add_story({
            "story_id": g["story_id"],
            "beat": "local" if g["scope"] == "local" else "news",
            "score": int(g["score"]),
            "sources": ", ".join(g["sources"]),
            "source_link": url or (g["links"][0] if g["links"] else ""),
            "attribution_line": str(j.get("attribution_line") or ""),
            "headline_hi": str(j.get("headline_hi") or g["title"])[:200],
            "headline_en": str(j.get("headline_en") or "")[:200],
            "lower_third_hi": str(j.get("lower_third_hi") or "")[:140],
            "script_hi": script,
            "yt_title": str(j.get("youtube_title_hi") or "")[:95],
            "yt_description": str(j.get("youtube_description_hi") or ""),
            "tags": ", ".join(str(t) for t in (j.get("tags") or []))[:480],
        })
        save_titles(g["story_id"], j, str(j.get("youtube_title_hi") or "")[:95])
        if g["scope"] == "national":
            note_national()
        made += 1
        log("  queue mein:", g["story_id"])
    return made


# ==================== REEL (9:16) ====================
#
# Reel bulletin ka chhota roop nahi hai - uski likhaai hi alag hai.
#
# Bulletin mein darshak ne pehle hi chunkar kholi hai; Reel mein wo bas
# scroll kar raha hai aur uske paas aapke liye DO SECOND hain. Us do
# second mein wo ya to ruk jayega ya nikal jayega. Isliye:
#
#   - pehla vaakya hi sabse badi baat ho. "Bhoomika" jaisa kuch nahi.
#   - 100-130 shabd. 45-60 second. Isse lamba Reel chhoda jaata hai.
#   - koi "namaskar", koi "aaj hum baat karenge", koi "video ke ant mein".
REEL_SYSTEM = "\n".join([
    'Aap ek Hindi news channel ke liye 45-60 second ki Reel likhte hain - wo video jo log scroll karte hue dekhte hain.',
    '',
    'Aapka darshak Bharat ka aam mobile istemal karne wala hai. Usne ye video chuni nahi hai - ye uske saamne aa gayi hai. Uske paas aapke liye do second hain.',
    '',
    'Sirf JSON lautaiye, aur kuch nahi.',
])

REEL_RULES = "\n".join([
    'Sirf wahi likhiye jo neeche di gayi saamagri mein hai. Koi naam, ankda, tareekh ya daawa apni taraf se mat jodiye.',
    '',
    'REEL KI LIKHAAI - ye bulletin se alag hai:',
    '1. PEHLA VAAKYA hi sabse badi baat ho. Bhoomika bilkul nahi. "Namaskar", "aaj hum baat karenge", "is video mein" - inme se kuch bhi nahi.',
    '2. Uske baad do-teen thos baatein, ek-ek vaakya mein. Chhote vaakya - Reel mein lamba vaakya sunai nahi deta, kyunki screen par shabd bhi saath chalte hain.',
    '3. Aakhri vaakya mein wo baat jo yaad reh jaye. Koi sawaal nahi, koi "comment mein bataiye" nahi, koi "subscribe" nahi.',
    '',
    'Lambai: 100 se 130 shabd. Isse lamba mat likhiye - Reel 60 second se lambi ho gayi to log chhod dete hain.',
    'Bhasha: ghar ki Hindi. Angrezi shabd wahi jo log bolte hain.',
    '',
    'JIN LOGON KI BAAT HO RAHI HAI:',
    'Jaane-mane vyakti (abhineta, khiladi, netaa, gayak) ki baat ho to sirf wahi likhiye jo saamagri mein saaf likha hai.',
    '"Sootron ke mutabik", "charcha hai ki", "kaha ja raha hai" - aisi ek bhi baat nahi.',
    'Kisi ki niji zindagi par kayaasbaazi kabhi nahi. Sirf afwaah par tiki baat ho to usable false.',
    '',
    'usable false kab:',
    '- saamagri itni patli ho ki 100 shabd imaandari se na nikle.',
    '- baat sirf kisi ke post ya afwaah par tiki ho.',
    'Shak ho to false.',
    '',
    'Isi aakar mein JSON lautaiye:',
    '{"usable": true, "skipReason": "", "headline_hi": "55 अक्षर तक",',
    ' "headline_en": "the same headline in English",',
    ' "lower_third_hi": "45 अक्षर तक, एक ही लाइन",',
    ' "script_hi": "पूरी स्क्रिप्ट, एक पैराग्राफ, 100-130 शब्द",',
    ' "youtube_title_hi": "80 अक्षर तक", "youtube_description_hi": "3 से 5 लाइन",',
    ' "tags": ["10 तक keywords"]}',
])

REEL_BEATS = ("bolly", "viral")


def run_reel(kind, term, links):
    """Chuna hua Reel ka vishay -> katar mein ek khabar. story_id ya "".

    kind: "bolly" ya "viral".
    """
    links = [l for l in (links or []) if l]
    if not links:
        links = sy_trend_links(term)
    if not links:
        log("  is vishay par koi lekh nahi mila")
        return ""
    url, text = pick_article(links)
    if not text:
        log("  is vishay par poora lekh nahi khula")
        return ""

    sid = "%s_%s" % ("bl" if kind == "bolly" else "vr",
                     re.sub(r"[^a-z0-9]+", "", str(term).lower())[:24])
    if st.get(sid):
        return ""

    head = ["SOURCE MATERIAL", "",
            "Vishay: " + str(term or ""),
            "Ye vishay Bharat mein abhi sabse zyada khoja/dekha ja raha hai.",
            "Source links: " + " | ".join(links[:6]), "",
            "POORA LEKH (" + sy_net.host(url) + ", " + url + "):", text, "",
            "Akhbaar ka naam script mein KAHIN NAHI aana chahiye - wo "
            "YouTube ke description mein apne aap jud jaata hai.",
            "", "NIYAM", REEL_RULES]
    j = sy_ai.ask_json(REEL_SYSTEM, "\n".join(head), max_tokens=2500)
    st.mark_seen(sid)
    st.remember_title(str(term or ""))

    if not j or j.get("usable") is not True:
        log("  sampadak ne roka:", str((j or {}).get("skipReason") or "")[:120])
        return ""
    script = re.sub(r"\s+", " ", str(j.get("script_hi") or "")).strip()
    if len(script) < 150:
        log("  script bahut chhoti - chhoda")
        return ""

    head_hi = str(j.get("headline_hi") or term)[:200]
    st.add_story({
        "story_id": sid,
        "beat": kind,
        "score": 12,
        "sources": sy_net.host(url),
        "source_link": url,
        "attribution_line": str(j.get("attribution_line") or ""),
        "headline_hi": head_hi,
        "headline_en": str(j.get("headline_en") or "")[:200],
        "lower_third_hi": str(j.get("lower_third_hi") or head_hi)[:140],
        "script_hi": script,
        "yt_title": str(j.get("youtube_title_hi") or head_hi)[:95],
        "yt_description": str(j.get("youtube_description_hi") or ""),
        "tags": ", ".join(str(t) for t in (j.get("tags") or []))[:480],
    })
    log("Reel queue mein:", sid, "-", head_hi[:50])
    return sid


def sy_trend_links(term):
    """Us vishay par taaze lekh - Google News ki khoj se."""
    try:
        import sy_trend
        return sy_trend.search_links(term)
    except Exception as e:
        log("khoj nahi chali:", e)
        return []


def save_titles(story_id, j, fallback=""):
    """Teen title ke vikalp sambhaal kar rakho.

    Ye database ke stories table mein nahi jaate - us table ki shakl badalna
    ek purani chalti hui file par sabse bhaari kaam hai, aur uska faayda
    itna nahi. kv mein rakhna kaafi hai: ye sirf approval ke ek pal ke liye
    chahiye, aur upload ke baad inka koi kaam nahi.

    Sampadak har beat par ye nahi bhejta (yojana aur gyan ka apna alag
    prompt hai). Na bheje to kuch nahi bigadta - wahi ek title chalta hai
    jo pehle chalta tha.
    """
    opts = []
    for t in (j or {}).get("title_options_hi") or []:
        t = re.sub(r"\s+", " ", str(t or "")).strip()[:95]
        if t and t not in opts:
            opts.append(t)
    if fallback and fallback not in opts:
        opts.insert(0, str(fallback)[:95])
    if len(opts) > 1:
        st.kv_set("titles_" + str(story_id), opts[:3])
    return opts[:3]


def story_from_links(story_id, title, links, sources="",
                     scope="national", score=14):
    """Ek chune hue vishay par ek khabar bana do. story_id ya "".

    Ye run_news() se alag hai aur jaan-boojhkar. run_news feeds tatolta hai
    aur JO MILA usme se chunta hai. Ye ULTA chalta hai: vishay pehle se tay
    hai (aapne Telegram par chuna hai), aur uspar lekh ab dhoondha jaata
    hai.

    Isi ulte kram ki wajah se sampadak ka call sirf USI khabar par lagta
    hai jo sach mein banni hai. Pehle har pending khabar par lag chuka hota
    tha, chahe wo kabhi chale ya na chale.
    """
    links = [l for l in (links or []) if l]
    if not links:
        return ""
    url, text = pick_article(links)
    if not text:
        log("  is vishay par poora lekh nahi khula - chhoda")
        return ""

    head = ["SOURCE MATERIAL", "",
            "Headline: " + str(title or ""),
            "Ye vishay Bharat mein abhi sabse zyada khoja/dekha ja raha hai.",
            "Source links: " + " | ".join(links[:6]), "",
            "POORA LEKH (" + sy_net.host(url) + ", " + url + "):", text, "",
            "Aapke paas poora lekh hai. Upar di gayi gehrai wali sabhi "
            "baatein - kab, kaun, kisne, kyun, ab kya - jitni is lekh mein "
            "hain, utni script mein aani chahiye.",
            "",
            "Is khabar par sirf EK lekh hai. Uska naam script mein KAHIN "
            "NAHI aana chahiye - wo YouTube description mein apne aap jud "
            "jaata hai. Ek source hone ka matlab itna hai ki koi bhi "
            "vivadit daawa poore bharose se mat likhiye.",
            "",
            # Trending vishay ab khel aur manoranjan se bhi aate hain. Wo
            # khabrein achhi hain aur log unhe dekhte hain - par unke saath
            # afwaah bhi sabse zyada chalti hai, aur ek channel ki sabse
            # badi poonji uska bharosa hai.
            "AGAR YE KHABAR KISI JAANE-MANE VYAKTI KI HAI (khiladi, "
            "abhineta, netaa, gayak) - to ye bhi:",
            "- Sirf wahi likhiye jo is lekh mein saaf likha hai. 'sootron "
            "ke mutabik', 'charcha hai ki', 'kaha ja raha hai' - aisi ek "
            "bhi baat nahi.",
            "- Unki niji zindagi ki khabar tabhi, jab wo khud ya unke "
            "pratinidhi ne kahi ho, ya kisi adhikarik elaan se aayi ho. "
            "Kisi ke rishton, sehat ya paise par kayaasbaazi kabhi nahi.",
            "- Sirf afwaah ya kisi ke 'post' par tiki khabar ho to "
            "publishable false kar dijiye.",
            "", "Bilingual bulletin scripts likhiye."]

    j = sy_ai.ask_json(EDITOR_SYSTEM, "\n".join(head), max_tokens=5000)
    st.mark_seen(story_id)
    st.remember_title(str(title or ""))

    if not j:
        log("  sampadak ka jawab JSON nahi tha")
        return ""
    if j.get("publishable") is not True:
        log("  sampadak ne roka:", str(j.get("kill_reason") or "")[:120])
        return ""
    script = re.sub(r"\s+", " ", str(j.get("script_hi") or "")).strip()
    if len(script) < 200:
        log("  script bahut chhoti")
        return ""

    st.add_story({
        "story_id": story_id,
        "beat": "local" if scope == "local" else "news",
        "score": int(score),
        # Khaali ho to us akhbaar ka naam jiska lekh sach mein padha gaya.
        # Pehle yahan "Google News" likha jaata tha - wo galat tha: khoj
        # Google se hoti thi, lekh kisi aur ka hota tha, aur YouTube ke
        # description mein shreya galat jagah chali jaati thi.
        "sources": sources or sy_net.host(url),
        "source_link": url,
        "attribution_line": str(j.get("attribution_line") or ""),
        "headline_hi": str(j.get("headline_hi") or title)[:200],
        "headline_en": str(j.get("headline_en") or "")[:200],
        "lower_third_hi": str(j.get("lower_third_hi") or "")[:140],
        "script_hi": script,
        "yt_title": str(j.get("youtube_title_hi") or "")[:95],
        "yt_description": str(j.get("youtube_description_hi") or ""),
        "tags": ", ".join(str(t) for t in (j.get("tags") or []))[:480],
    })
    save_titles(story_id, j, str(j.get("youtube_title_hi") or "")[:95])
    log("  queue mein:", story_id)
    return story_id


# ------------------------------------------------------------ yojana
#
# Yojana wala hissa khabar nahi hai - jagrukta hai.
#
# Pehle ye galat bana tha: ye sirf NAYI ghoshna dhoondhta tha, aur sarkar
# koi elaan na kare to kuch banta hi nahi tha. Par darshak ke liye ek chalti
# hui yojana bhi nayi hi hoti hai, agar use uske baare mein pata nahi. Bharat
# mein zyadatar log in yojanaon ki jaankari kisi channel se nahi, ek-doosre
# se paate hain - aur wahi kami ye channel bhar sakta hai.
#
# Isliye ab do rasta hai:
#   1. PIB par koi taazi ghoshna ho - wo pehle.
#   2. Warna chal rahi yojanaon mein se agli wali, baari-baari se.

# Har yojana ka apna sarkari safha. Ye jaanche gaye hain - inpar rakam,
# patrata aur aavedan ka rasta teenon likhe milte hain.
SCHEMES = [
    ("pmkisan", "प्रधानमंत्री किसान सम्मान निधि",
     "https://pmkisan.gov.in/", "PM-KISAN, भारत सरकार"),
    ("pmjay", "आयुष्मान भारत — प्रधानमंत्री जन आरोग्य योजना",
     "https://nha.gov.in/PM-JAY", "राष्ट्रीय स्वास्थ्य प्राधिकरण"),
    ("pmay_urban", "प्रधानमंत्री आवास योजना (शहरी)",
     "https://pmay-urban.gov.in/about", "PMAY-U, भारत सरकार"),
    ("pmay_subsidy", "प्रधानमंत्री आवास योजना — ब्याज सब्सिडी",
     "https://pmaymis.gov.in/pmaymis2_2024/PmayFAQ.aspx", "PMAY, भारत सरकार"),
    ("pmuy", "प्रधानमंत्री उज्ज्वला योजना",
     "https://www.pmuy.gov.in/faq.html", "PMUY, भारत सरकार"),
    # UP ke zile apne safhe Hindi mein rakhte hain, rakam ke saath. Inmein
    # se koi na khule to chhod diya jaata hai - kuch nahi bigadta.
    ("up_prayagraj", "प्रयागराज में चल रही सरकारी योजनाएं",
     "https://prayagraj.nic.in/schemes/", "जिला प्रशासन प्रयागराज"),
    ("up_varanasi", "वाराणसी में चल रही सरकारी योजनाएं",
     "https://varanasi.nic.in/schemes/", "जिला प्रशासन वाराणसी"),
    ("up_mirzapur", "मिर्ज़ापुर में चल रही सरकारी योजनाएं",
     "https://mirzapur.nic.in/schemes/", "जिला प्रशासन मिर्ज़ापुर"),
]

# Ek yojana dobara kitne din baad. Wo purani nahi hoti, par ek hi cheez
# baar-baar dikhana bhi theek nahi.
SCHEME_REPEAT_DAYS = 60


# ==================== KAAM KI BAAT ====================
#
# Teesra beat. Khabar nahi, yojana bhi nahi - wo jaankari jo kabhi bhi
# dekhi jaye kaam ki lagti hai: sehat, padhai-naukri, paisa, aur roz ke
# kagaz.
#
# Ye is channel ki soch se seedhe judta hai. Aapka darshak khabar YouTube
# par share nahi karta, par "aadhaar mein mobile number kaise badlein" ya
# "1930 par thagi ki shikayat" - ye wo apne ghar ke WhatsApp group mein
# bhejta hai. Aisi video mahine baad bhi utni hi kaam ki rehti hai jitni
# aaj, isliye ye channel par jama hoti rehti hai - khabar ki tarah baasi
# nahi hoti.
#
# Har vishay ka apna SARKARI safha diya gaya hai. Script usi safhe se
# likhi jaati hai - yahan se koi baat apne aap nahi banti. Isi wajah se
# ye bharosemand rehti hai.
KAAM = [
    # ---- sehat: sirf hak, prakriya aur jagah. Ilaj ki salah KABHI nahi.
    ("ayushman_card", "आयुष्मान कार्ड कैसे बनवाएं",
     "https://beneficiary.nha.gov.in/", "राष्ट्रीय स्वास्थ्य प्राधिकरण", "sehat"),
    ("janaushadhi", "जन औषधि केंद्र — वही दवा, कम दाम पर",
     "https://janaushadhi.gov.in/ProductList.aspx", "जन औषधि, भारत सरकार", "sehat"),
    ("esanjeevani", "eSanjeevani — घर बैठे मुफ़्त डॉक्टर परामर्श",
     "https://esanjeevani.mohfw.gov.in/#/about", "स्वास्थ्य मंत्रालय", "sehat"),
    ("tikakaran", "बच्चों का टीकाकरण — कौन सा टीका कब",
     "https://nhm.gov.in/index1.php?lang=1&level=2&sublinkid=824&lid=220",
     "राष्ट्रीय स्वास्थ्य मिशन", "sehat"),

    # ---- padhai aur naukri
    ("ncs", "राष्ट्रीय करियर सेवा — मुफ़्त नौकरी पंजीकरण",
     "https://www.ncs.gov.in/Pages/default.aspx", "श्रम मंत्रालय", "career"),
    ("scholarship", "नेशनल स्कॉलरशिप पोर्टल — छात्रवृत्ति का आवेदन",
     "https://scholarships.gov.in/", "शिक्षा मंत्रालय", "career"),
    ("skill_india", "स्किल इंडिया — मुफ़्त हुनर प्रशिक्षण",
     "https://www.skillindiadigital.gov.in/", "कौशल विकास मंत्रालय", "career"),
    ("apprentice", "अप्रेंटिसशिप — सीखते हुए कमाई",
     "https://dgt.gov.in/apprenticeship_training", "प्रशिक्षण महानिदेशालय", "career"),
    ("up_rojgar", "यूपी रोजगार संगम — प्रदेश में नौकरी का पोर्टल",
     "https://rojgaarsangam.up.gov.in/", "सेवायोजन विभाग, उत्तर प्रदेश", "career"),

    # ---- paisa. Koi nivesh ki salah nahi - sirf sarkari yojana ke tathya.
    ("epfo_uan", "पीएफ का पैसा — UAN, बैलेंस और निकासी",
     "https://www.epfindia.gov.in/site_en/For_Employees.php", "EPFO", "paisa"),
    ("cyber_1930", "साइबर ठगी हो जाए तो — 1930 और शिकायत",
     "https://www.mha.gov.in/en/divisionofmha/cyber-and-information-security-cis-division",
     "गृह मंत्रालय", "paisa"),
    ("jansuraksha", "20 रुपये सालाना में बीमा — जन सुरक्षा योजनाएं",
     "https://www.jansuraksha.gov.in/", "वित्त मंत्रालय", "paisa"),
    ("sukanya", "सुकन्या समृद्धि — बेटी के नाम खाता",
     "https://www.nsiindia.gov.in/InternalPage.aspx?Id_Pk=89",
     "राष्ट्रीय बचत संस्थान", "paisa"),
    ("jan_dhan", "जन धन खाता — बिना पैसे के बैंक खाता",
     "https://pmjdy.gov.in/scheme", "वित्तीय सेवाएं विभाग", "paisa"),
    ("bank_shikayat", "बैंक से शिकायत — RBI लोकपाल तक कैसे जाएं",
     "https://cms.rbi.org.in/", "भारतीय रिज़र्व बैंक", "paisa"),

    # ---- roz ke kagaz
    ("aadhaar_update", "आधार में पता और मोबाइल नंबर कैसे बदलें",
     "https://uidai.gov.in/en/my-aadhaar/update-aadhaar.html", "UIDAI", "jeevan"),
    ("ration_onorc", "राशन कार्ड — वन नेशन वन राशन कार्ड",
     "https://nfsa.gov.in/portal/onorc", "खाद्य एवं सार्वजनिक वितरण विभाग", "jeevan"),
    ("janm_praman", "जन्म और मृत्यु प्रमाणपत्र — ऑनलाइन आवेदन",
     "https://crsorgi.gov.in/web/index.php/auth/login", "जनगणना कार्यालय", "jeevan"),
    ("rti", "आरटीआई — सरकार से जवाब माँगने का हक",
     "https://rtionline.gov.in/", "कार्मिक मंत्रालय", "jeevan"),
    ("upbhokta", "उपभोक्ता शिकायत — 1915 और ऑनलाइन दावा",
     "https://consumerhelpline.gov.in/", "उपभोक्ता मामले विभाग", "jeevan"),

    # ---- kanooni madad. Ye mujhse chhoot gaya tha aur ye sabse kaam ki
    # cheezon mein hai: gareeb aadmi ko wakeel MUFT milta hai, par ye baat
    # usi ko nahi pata jise iski zaroorat hai.
    ("nalsa", "मुफ़्त वकील का हक़ — राष्ट्रीय विधिक सेवा प्राधिकरण",
     "https://nalsa.gov.in/services/legal-aid",
     "राष्ट्रीय विधिक सेवा प्राधिकरण", "kanoon"),
    ("lok_adalat", "लोक अदालत — बिना फ़ीस, एक ही दिन में फ़ैसला",
     "https://nalsa.gov.in/lok-adalat",
     "राष्ट्रीय विधिक सेवा प्राधिकरण", "kanoon"),
    ("tele_law", "टेली-लॉ — गाँव के कॉमन सर्विस सेंटर से वकील की सलाह",
     "https://www.tele-law.in/", "न्याय विभाग", "kanoon"),
    ("nyaya_15100", "15100 — कानूनी मदद का हेल्पलाइन नंबर",
     "https://nalsa.gov.in/services/legal-aid/legal-services-clinic",
     "राष्ट्रीय विधिक सेवा प्राधिकरण", "kanoon"),

    # ---- padhai ke aur raaste
    ("swayam", "स्वयं — मुफ़्त ऑनलाइन कोर्स और सर्टिफिकेट",
     "https://swayam.gov.in/about", "शिक्षा मंत्रालय", "career"),
    ("nios", "एनआईओएस — स्कूल छूट गया तो भी बोर्ड की पढ़ाई",
     "https://www.nios.ac.in/about-us.aspx", "राष्ट्रीय मुक्त विद्यालयी शिक्षा संस्थान",
     "career"),
]

KAAM_REPEAT_DAYS = 90

# JIS VISHAY KA SAFHA MAR CHUKA HAI, USE ITNE DIN AAGE MAT LAANA
#
# Pehle mara hua safha teen din baad phir suchi mein aa jaata tha. Ab wo
# theek nahi baithta: 26 mein se 19 safhe ek saath toote hue nikle (kuch
# 404, kuch ka certificate poora nahi, aur kuch nayi tarah ke portal
# jinpar text hota hi nahi - sab kuch JavaScript se banta hai).
#
# Us haalat mein teen din ka intezaar ka matlab ye hota ki har slate par
# wahi mare hue vishay dobara-dobara aate rahein, aur aapka tap unhi par
# jaata rahe. Ek mahina theek hai: tab tak wo safha wapas bhi aa sakta
# hai, aur beech mein chalne wale vishay aage aa jaate hain.
KAAM_DEAD_DAYS = 30

YJ_MUST = ['योजना', 'किस्त', 'सब्सिडी', 'पेंशन', 'छात्रवृत्ति', 'स्कॉलरशिप',
           'भत्ता', 'आवास', 'अनुदान', 'लाभार्थी', 'आवेदन', 'मानदेय', 'निधि',
           'बीमा', 'कार्ड', 'ऋण', 'मुफ्त']
YJ_BONUS = ['रुपये', 'रुपए', 'हज़ार', 'हजार', 'लाख', 'करोड़', 'अंतिम तिथि',
            'पात्र', 'ऑनलाइन', 'पंजीकरण', 'रजिस्ट्रेशन', 'किसान', 'महिला',
            'छात्र', 'बुजुर्ग', 'श्रमिक', 'मजदूर', 'गरीब', 'ग्रामीण']
YJ_BAD = ['सीसीआई', 'अधिग्रहण', 'विलय', 'शोक', 'निधन', 'श्रद्धांजलि',
          'पुष्पांजलि', 'नियुक्ति', 'राशिफल', 'क्रिकेट', 'बॉलीवुड', 'ट्रेलर',
          'रेसिपी', 'वास्तु', 'टोटके']

# Slideshow aur video ke safhe kabhi lekh nahi hote - unpar sirf teen line
# ka teaser hota hai aur baaki paywall ke peeche.
SLIDESHOW = re.compile(r"/(photo-gallery|photo-story|web-stories|video|videos|shorts)/", re.I)

# SHIKSHAK WALA ANDAAZ (Sep 2026, Harshvardhan ki maang)
#
# Khabar (local/news/bulletin) ko chhod kar baaki sab - yojana, kaam ki
# baat, gyan, tech - aise likhe jaate hain jaise koi pyaara shikshak
# samjha raha ho: dheere, apnepan se, udaharan dekar, bharosa dilaate hue.
# Wahi komal ehsaas jo har kisi ko bachpan mein kuch naya seekhte waqt
# mila tha.
#
# Ye SIRF bolne ka andaaz hai. Dhaancha, lambaai, aur imaandaari ke niyam
# har beat ke apne *_RULES mein hain aur wahi upar rehte hain - yahan se
# koi naya tathya, sankhya ya daawa nahi aata. Khabar par ye kabhi nahi
# lagta: wahan ek sampadak ki seedhi, sadhi hui aawaaz hi sahi hai.
TEACHER_STYLE = "\n".join([
    'बोलने का अंदाज़ — एक प्यारे शिक्षक जैसा:',
    '- ऐसे समझाइए जैसे कोई धैर्यवान, अपनापन भरा शिक्षक या शिक्षिका समझाती हैं — वही जो हर किसी को बचपन में कभी न कभी मिले: जो डाँटते नहीं, धीरे-धीरे, प्यार से, उदाहरण देकर समझाते हैं, और यह भरोसा देते हैं कि "यह मुश्किल नहीं है, आप आसानी से समझ जाएँगे।"',
    '- दर्शक से सीधे, गर्मजोशी से जुड़िए — जैसे "चलिए, इसे एक आसान उदाहरण से समझते हैं", "ज़रा सोचिए...", "अब आप पूछेंगे कि...", "तो पहली बात समझ आ गई, अब दूसरी बात।" पर यह पूरी स्क्रिप्ट में दो-तीन बार काफ़ी है — हर वाक्य में नहीं।',
    '- समझाने के लिए रोज़ की ज़िंदगी से एक छोटी तुलना या उदाहरण दीजिए — घर, रसोई, खेत, बाज़ार, स्कूल की बात। यह उदाहरण सिर्फ़ समझाने के लिए है: इसमें कोई नई संख्या, रकम, तारीख़ या दावा नहीं आएगा — तथ्य सिर्फ़ मूल सामग्री से।',
    '- कोमलता का मतलब बच्चों वाली भाषा नहीं — आप बड़ों से बात कर रहे हैं। लहजा गर्म और सम्मान भरा हो। दर्शक को कभी नासमझ मत मानिए ("आपको पता नहीं होगा" जैसी बात नहीं), न उपदेश दीजिए, न भाषण।',
    '- वाक्य छोटे और बोलने में सहज हों, बीच में कॉमा और पूर्णविराम से ठहराव — यह स्क्रिप्ट आवाज़ में सुनी जाएगी।',
    '- आख़िर में एक छोटा सा हौसला या अपनापन — जैसे "बस, इतनी सी बात है।" नारा या नसीहत नहीं।',
    '- ऊपर के "नियम" — ढाँचा, लंबाई, ईमानदारी और मना की गई बातें — वैसे ही लागू हैं। अंदाज़ उनके ऊपर नहीं जाता; उनके अंदर रहकर बात कहने का तरीका है।',
])

YOJANA_SYSTEM = "\n".join([
    'आप एक हिंदी न्यूज़ चैनल के लिए सरकारी योजनाओं की जानकारी देते हैं।',
    'आपका दर्शक पूर्वी उत्तर प्रदेश में है — प्रयागराज, वाराणसी, मिर्ज़ापुर, भदोही, लखनऊ। वह एक ही बात जानना चाहता है — इसमें मेरे लिए क्या है, और मुझे करना क्या होगा।',
    'यह ख़बर नहीं, जागरूकता है। योजना पुरानी हो या नई — अगर वह अभी चल रही है, तो जिस दर्शक को उसकी जानकारी नहीं, उसके लिए वह नई ही है।',
    'सिर्फ JSON लौटाइए, और कुछ नहीं।',
])

YOJANA_RULES = "\n".join([
    'भाषा:',
    '- कक्षा 8 की हिंदी। एक वाक्य में एक बात। हर वाक्य 14 शब्द से छोटा।',
    '- दर्शक को "आप" कहिए।',
    '- रकम शब्दों में लिखिए — "छह हज़ार रुपये", अंकों में नहीं। स्क्रिप्ट बोली जाती है, पढ़ी नहीं जाती।',
    '- स्रोत अंग्रेज़ी में हो तो हिंदी में लिखिए, पर रकम और शर्तें बिल्कुल वही रखिए जो स्रोत में हैं।',
    '',
    'ईमानदारी — यही इस चैनल की पूँजी है:',
    '- जो स्रोत में नहीं है वह मत लिखिए। अंदाज़ा कभी नहीं।',
    '- किसी नेता, पार्टी या सरकार की तारीफ़ या आलोचना नहीं। सिर्फ़ यह कि दर्शक को क्या मिल सकता है और कैसे।',
    '- "मिलेगा" मत कहिए। "पात्र हैं तो आवेदन कर सकते हैं" कहिए।',
    '- यह मत कहिए कि योजना "नई है" या "अभी घोषित हुई है", जब तक स्रोत ऐसा न कहे। यह चल रही योजना की जानकारी है।',
    '',
    'script_hi का ढाँचा — 170 से 200 शब्द, लगभग 45 सेकंड:',
    '1. पहले दो वाक्य: सबसे ठोस फ़ायदा या रकम। यही वजह है जिससे दर्शक रुकेगा।',
    '2. फिर: कौन पात्र है — ठोस शर्तें।',
    '3. फिर: कितना मिलता है, और किस तरह।',
    '4. फिर: कहाँ आवेदन करें — वेबसाइट या दफ़्तर का नाम साफ़ बोलिए। नाम स्रोत में न हो तो लिखिए "अपने नज़दीकी जन सेवा केंद्र या ब्लॉक कार्यालय से पूछें"।',
    '5. आख़िरी वाक्य में आवेदन की जगह दोहराइए।',
    '',
    'usable कब false रखें:',
    '- स्रोत में दर्शक के काम की कोई ठोस बात न हो — न रकम, न पात्रता, न आवेदन का रास्ता।',
    '- स्रोत सिर्फ़ योजना का नाम गिनाता हो, विवरण न देता हो।',
    'शक हो तो false रखिए। एक वीडियो न बनने से चैनल का कुछ नहीं बिगड़ता; एक ग़लत रकम से भरोसा जाता है।',
    '',
    'इसी आकार में JSON लौटाइए:',
    '{"usable": true, "skipReason": "", "headline_hi": "60 अक्षर तक",',
    ' "headline_en": "the same headline in English",',
    ' "lower_third_hi": "55 अक्षर तक", "script_hi": "पूरी स्क्रिप्ट, एक पैराग्राफ",',
    ' "youtube_title_hi": "90 अक्षर तक", "youtube_description_hi": "3 से 5 लाइन",',
    ' "tags": ["10 तक keywords"]}',
])


def yojana_candidates():
    """PIB/Amar Ujala par koi taazi yojana khabar."""
    out = []
    for slug, name, url, weight in YOJANA_FEEDS:
        for it in read_feed(url, name):
            link = it["link"]
            if slug.startswith("PRESS"):
                # PIB apne hi feed mein galat link deta hai - IframePage 404
                # lautata hai. Sahi safha PressReleasePage hai, www ke saath;
                # aur lang=2 na ho to wo kabhi Marathi mein khul jaata hai.
                link = link.replace("PressReleaseIframePage.aspx",
                                    "PressReleasePage.aspx")
                link = link.replace("://pib.gov.in/", "://www.pib.gov.in/")
                if "lang=" not in link:
                    link += ("&" if "?" in link else "?") + "reg=3&lang=2"
            if not link.startswith("http") or SLIDESHOW.search(link):
                continue
            t = it["title"]
            score = (3 * sum(1 for w in YJ_MUST if w in t)
                     + sum(1 for w in YJ_BONUS if w in t)
                     - 5 * sum(1 for w in YJ_BAD if w in t) + weight)
            if score < 3:
                continue
            out.append({"story_id": story_id(t, "yj_"), "title": t, "link": link,
                        "source_slug": slug, "source_name": name, "score": score,
                        "kind": "khabar"})
    out.sort(key=lambda x: -x["score"])
    return out


def next_scheme():
    """Baari-baari se agli chal rahi yojana."""
    now = time.time()
    best, best_at = None, None
    for slug, name, url, source in SCHEMES:
        last = float(st.kv_get("scheme_last_" + slug, 0) or 0)
        if now - last < SCHEME_REPEAT_DAYS * 86400:
            continue
        if best_at is None or last < best_at:
            best, best_at = (slug, name, url, source), last
    if not best:
        return None
    slug, name, url, source = best
    return {"story_id": "yj_%s_%s" % (slug, time.strftime("%Y%m")),
            "title": name, "link": url, "slug": slug,
            "source_slug": "SARKARI", "source_name": source,
            "score": 6, "kind": "jankari"}


def _write_yojana(c, text):
    """Sampadak se script likhwa kar queue mein daalo. True/False."""
    label = ("स्रोत: " + c["source_name"]) if c["kind"] == "khabar" else \
            ("स्रोत: " + c["source_name"] + " की आधिकारिक वेबसाइट")
    user = "\n".join([
        "योजना / विषय: " + c["title"],
        "स्रोत: " + c["source_name"],
        ("यह एक ताज़ा सरकारी विज्ञप्ति है।" if c["kind"] == "khabar"
         else "यह इस योजना का आधिकारिक पेज है। योजना अभी चल रही है।"),
        "", "मूल सामग्री:", text, "", "नियम", YOJANA_RULES, "", TEACHER_STYLE])
    j = sy_ai.ask_json(YOJANA_SYSTEM, user, max_tokens=3000)

    if not j or j.get("usable") is not True:
        log("  sampadak ne roka:", str((j or {}).get("skipReason") or "")[:120])
        return False
    script = re.sub(r"\s+", " ", str(j.get("script_hi") or "")).strip()
    if len(script) < 200:
        log("  script bahut chhoti - chhoda")
        return False

    head = str(j.get("headline_hi") or c["title"])[:200]
    st.add_story({
        "story_id": c["story_id"],
        "beat": "yojana",
        "score": int(c["score"]),
        "sources": c["source_slug"],
        "source_link": c["link"],
        "attribution_line": label,
        "headline_hi": head,
        "headline_en": str(j.get("headline_en") or "")[:200],
        "lower_third_hi": str(j.get("lower_third_hi") or head)[:140],
        "script_hi": script,
        "yt_title": str(j.get("youtube_title_hi") or head)[:95],
        "yt_description": str(j.get("youtube_description_hi") or ""),
        "tags": ", ".join(str(t) for t in (j.get("tags") or []))[:480],
    })
    log("  queue mein:", c["story_id"])
    return True


def run_yojana():
    """Ek baar mein ek hi yojana - jab tak pichhli nikal na jaye."""
    in_flight = sum(st.count_status(s, "yojana")
                    for s in ("pending", "producing", "awaiting", "approved"))
    if in_flight:
        return 0

    # 1) PIB par koi taazi ghoshna ho to wo pehle.
    for c in yojana_candidates()[:10]:
        if st.get(c["story_id"]) or st.seen(c["story_id"]):
            continue
        if already_covered(c["title"]):
            continue
        try:
            text = sy_net.article_text(sy_net.get_text(c["link"], timeout=45),
                                       min_chars=900)
        except Exception as e:
            log("yojana lekh nahi khula:", e)
            continue
        st.mark_seen(c["story_id"])
        st.remember_title(c["title"])
        if not text:
            continue
        log("yojana khabar:", c["title"][:60])
        if _write_yojana(c, text):
            return 1

    # 2) Koi nayi ghoshna nahi - to chal rahi yojanaon mein se agli.
    c = next_scheme()
    if not c:
        return 0
    if st.get(c["story_id"]):
        return 0
    try:
        text = sy_net.article_text(sy_net.get_text(c["link"], timeout=45),
                                   min_chars=600)
    except Exception as e:
        log("yojana ka safha nahi khula (%s): %s" % (c["slug"], e))
        # Aaj is yojana ko chhod dete hain, par hamesha ke liye nahi -
        # ho sakta hai safha kal khul jaye.
        st.kv_set("scheme_last_" + c["slug"], time.time() - (SCHEME_REPEAT_DAYS - 3) * 86400)
        return 0
    if not text:
        log("yojana ke safhe par kaam ka text nahi mila:", c["slug"])
        st.kv_set("scheme_last_" + c["slug"], time.time() - (SCHEME_REPEAT_DAYS - 7) * 86400)
        return 0

    log("yojana jankari:", c["title"][:60])
    st.kv_set("scheme_last_" + c["slug"], time.time())
    return 1 if _write_yojana(c, text) else 0


# ----------------------------------------------------- kaam ki baat

KAAM_SYSTEM = "\n".join([
    'आप एक हिंदी न्यूज़ चैनल के लिए "काम की बात" लिखते हैं — वह जानकारी जो दर्शक अपने घरवालों को भेजता है।',
    '',
    'आपका दर्शक प्रयागराज, मिर्ज़ापुर, भदोही, वाराणसी और लखनऊ का आम आदमी है। वह सरकारी दफ़्तर की भाषा नहीं समझता, और उसके पास वक़्त कम है।',
    'वह एक ही चीज़ जानना चाहता है: मेरा इससे क्या लेना-देना, और मुझे करना क्या है।',
    '',
    'सिर्फ़ JSON लौटाइए, और कुछ नहीं।',
])

KAAM_RULES = "\n".join([
    'सिर्फ़ वही लिखिए जो नीचे दी गई सरकारी सामग्री में है। कोई रकम, तारीख़, पात्रता या नंबर अपनी तरफ़ से मत जोड़िए। याद से मत लिखिए — जो पेज पर है, बस वही।',
    '',
    'ढाँचा — इसी क्रम में:',
    '1. पहला वाक्य दर्शक की अपनी ज़िंदगी से शुरू हो, योजना के नाम से नहीं। "अगर आपका आधार पुराने पते पर है..." — ऐसे।',
    '2. फिर असल बात: क्या मिलता है, किसे मिलता है।',
    '3. फिर रास्ता: कहाँ जाना है, कौन सा कागज़ लगेगा, कितना खर्च।',
    '4. कोई सरकारी हेल्पलाइन नंबर या वेबसाइट सामग्री में हो तो वह ज़रूर बोलिए — यही सबसे काम की चीज़ है।',
    '5. आख़िरी वाक्य में वह एक काम दोहराइए जो दर्शक को करना है।',
    '',
    'भाषा: घर की हिंदी। "आवेदन प्रस्तुत करें" नहीं — "आवेदन कीजिए"। अंग्रेज़ी शब्द वही जो लोग बोलते हैं (ऑनलाइन, फॉर्म, वेबसाइट)।',
    'लंबाई: 150 से 200 शब्द।',
    '',
    'सेहत वाले विषय — यहाँ कोई ढील नहीं:',
    'आप डॉक्टर नहीं हैं और यह वीडियो लाखों लोगों तक जा सकती है।',
    '- किसी बीमारी की पहचान, इलाज, दवा का नाम या खुराक कभी मत लिखिए।',
    '- कोई घरेलू नुस्खा, कोई "इससे ठीक हो जाता है" जैसी बात कभी नहीं।',
    '- सिर्फ़ यह लिखिए: क्या सुविधा है, किसे मिलती है, कहाँ मिलती है, कैसे लें।',
    '- और आख़िर में यह ज़रूर हो कि इलाज के लिए डॉक्टर या नज़दीकी सरकारी अस्पताल से मिलें।',
    '',
    'पैसे वाले विषय — यहाँ भी:',
    '- कोई निवेश की सलाह नहीं। "यह लगाइए", "फ़ायदा होगा", "बेहतर रिटर्न" — ऐसा कुछ नहीं।',
    '- सिर्फ़ सरकारी योजना के तथ्य: ब्याज या रकम अगर पेज पर लिखी है तो वही, वरना छोड़ दीजिए।',
    '- ठगी वाले विषय पर डराइए मत — क्या करना है, वह साफ़ बताइए।',
    '',
    'usable false कब:',
    '- पेज पर दर्शक के काम की कोई ठोस बात न हो — न पात्रता, न रास्ता, न नंबर।',
    '- पेज सिर्फ़ लॉगिन या मेन्यू दिखाता हो।',
    'शक हो तो false। एक वीडियो न बनने से कुछ नहीं बिगड़ता; एक ग़लत जानकारी से भरोसा जाता है।',
    '',
    'इसी आकार में JSON लौटाइए:',
    '{"usable": true, "skipReason": "", "headline_hi": "60 अक्षर तक",',
    ' "headline_en": "the same headline in English",',
    ' "lower_third_hi": "55 अक्षर तक, एक ही लाइन",',
    ' "script_hi": "पूरी स्क्रिप्ट, एक पैराग्राफ",',
    ' "youtube_title_hi": "90 अक्षर तक", "youtube_description_hi": "3 से 5 लाइन",',
    ' "tags": ["10 तक keywords"]}',
])


def next_kaam():
    """Baari-baari se agla vishay. Ek hi vishay 90 din se pehle dobara nahi."""
    now = time.time()
    best, best_at = None, None
    for row in KAAM:
        slug = row[0]
        last = float(st.kv_get("kaam_last_" + slug, 0) or 0)
        if now - last < KAAM_REPEAT_DAYS * 86400:
            continue
        if best_at is None or last < best_at:
            best, best_at = row, last
    if not best:
        return None
    slug, title, url, source, topic = best
    return {"story_id": "kb_%s_%s" % (slug, time.strftime("%Y%m")),
            "title": title, "link": url, "slug": slug, "topic": topic,
            "source_name": source, "score": 7}


def kaam_by_slug(slug):
    """Ek KHAAS vishay - Telegram par chune jaane ke baad."""
    for row in KAAM:
        if row[0] == slug:
            s_, title, url, source, topic = row
            return {"story_id": "kb_%s_%s" % (s_, time.strftime("%Y%m")),
                    "title": title, "link": url, "slug": s_, "topic": topic,
                    "source_name": source, "score": 7}
    return None


def run_kaam(slug=""):
    """Ek baar mein ek hi - jab tak pichhli nikal na jaye.

    slug diya ho to baari ka hisaab nahi lagta - wahi vishay banta hai.
    Ye tab hota hai jab aapne use Telegram par khud chuna ho.
    """
    in_flight = sum(st.count_status(s, "kaam")
                    for s in ("pending", "producing", "awaiting", "approved"))
    if in_flight and not slug:
        return 0

    c = kaam_by_slug(slug) if slug else next_kaam()
    if not c:
        log("kaam ki baat: sab vishay abhi haal mein ho chuke hain")
        return 0
    if st.get(c["story_id"]):
        return 0

    try:
        text = sy_net.article_text(sy_net.get_text(c["link"], timeout=45),
                                   min_chars=500)
    except Exception as e:
        log("kaam ka safha nahi khula (%s): %s" % (c["slug"], e))
        # Aaj chhod diya, hamesha ke liye nahi - kal khul sakta hai.
        st.kv_set("kaam_last_" + c["slug"],
                  time.time() - (KAAM_REPEAT_DAYS - KAAM_DEAD_DAYS) * 86400)
        return 0
    if not text:
        log("kaam ke safhe par kaam ka text nahi mila:", c["slug"])
        st.kv_set("kaam_last_" + c["slug"],
                  time.time() - (KAAM_REPEAT_DAYS - KAAM_DEAD_DAYS) * 86400)
        return 0

    user = "\n".join([
        "विषय: " + c["title"],
        "श्रेणी: " + c["topic"],
        "स्रोत: " + c["source_name"] + " की आधिकारिक वेबसाइट",
        "", "मूल सामग्री:", text, "", "नियम", KAAM_RULES, "", TEACHER_STYLE])
    j = sy_ai.ask_json(KAAM_SYSTEM, user, max_tokens=3000)

    st.kv_set("kaam_last_" + c["slug"], time.time())

    if not j or j.get("usable") is not True:
        log("  sampadak ne roka:", str((j or {}).get("skipReason") or "")[:120])
        return 0
    script = re.sub(r"\s+", " ", str(j.get("script_hi") or "")).strip()
    if len(script) < 200:
        log("  script bahut chhoti - chhoda")
        return 0

    head = str(j.get("headline_hi") or c["title"])[:200]
    st.add_story({
        "story_id": c["story_id"],
        "beat": "kaam",
        "score": int(c["score"]),
        "sources": "SARKARI",
        "source_link": c["link"],
        "attribution_line": "स्रोत: " + c["source_name"],
        "headline_hi": head,
        "headline_en": str(j.get("headline_en") or "")[:200],
        "lower_third_hi": str(j.get("lower_third_hi") or head)[:140],
        "script_hi": script,
        "yt_title": str(j.get("youtube_title_hi") or head)[:95],
        "yt_description": str(j.get("youtube_description_hi") or ""),
        "tags": ", ".join(str(t) for t in (j.get("tags") or []))[:480],
    })
    log("kaam ki baat queue mein:", c["story_id"], "-", head[:50])
    return 1


# ==================== GYAN KI BAAT ====================
#
# Chautha beat: samjhane wali video. Itihas, bhugol, aur "ye cheez kaam
# kaise karti hai".
#
# YE BEAT KYUN BANA - SEEDHI BAAT
#
# Ye kisi soch se nahi, ek naap se nikla. Mirzapur ki ek sthaniya khabar ka
# sach mein uska apna drishya milne ki ummeed lagbhag shoonya hai - koi
# licence wali tasveer hoti hi nahi. Wahi "Konark Sun Temple" ya "jahaz
# samudra mein raasta kaise khojte hain" par Wikimedia Commons par darjanon
# saaf, licence wali tasveerein aur footage padi hain.
#
# Isliye vishay AISE chune gaye hain jinki tasveer maujood hai - tasveer ko
# vishay ke peechhe ghaseetne ki jagah. Ye ulta lag sakta hai, par yahi wo
# sawaal tha jo aapne poochha tha: "production ke hisab se footage dhoondhna
# ya footage ke hisab se production tay ho raha hai?" Khabar par jawab pehla
# hai - khabar sakht rehti hai, aur drishya na mile to wo banti hi nahi.
# Yahan jawab doosra hai, aur jaan-boojhkar: ye khabar nahi hai, isliye
# ismein ye chunav jayaz hai.
#
# SOURCE: en.wikipedia.org, uske apne API se saaf text mein. Angrezi isliye
# ki wahan lekh kahin zyada bhare hue aur hawale wale hain; script phir bhi
# Hindi mein hi likhi jaati hai. Wikimedia ka apna niyam yahan bhi lagta hai
# (wiki_headers + ek-ek karke request) - wahi niyam jiski anadekhi se Commons
# har baar 429 de raha tha.
GYAN_API = "https://en.wikipedia.org/w/api.php"
GYAN_REPEAT_DAYS = 240
GYAN_MIN_CHARS = 1200

# (slug, Hindi shirshak, Wikipedia ka lekh, shreni)
#
# Daayra: duniya bhar ka, par Bharat pehle - yahi aapne chuna. Isliye
# suchi mein Ganga aur Nil dono hain, Konark aur China ki deewar dono.
GYAN = [
    # ---------- ye kaise kaam karta hai
    ("navigation", "जहाज़ बीच समुद्र में रास्ता कैसे खोजते हैं",
     "Navigation", "kaise"),
    ("gps", "GPS आपकी जगह कैसे बता देता है", "Global Positioning System", "kaise"),
    ("lighthouse", "लाइटहाउस — समुद्र किनारे की सबसे पुरानी चेतावनी",
     "Lighthouse", "kaise"),
    ("atc", "हवाई जहाज़ आसमान में आपस में टकराते क्यों नहीं",
     "Air traffic control", "kaise"),
    ("desalination", "समुद्र का खारा पानी पीने लायक कैसे बनाया जाता है",
     "Desalination", "kaise"),
    ("water_purification", "नल तक आने से पहले पानी कहाँ-कहाँ से गुज़रता है",
     "Water purification", "kaise"),
    ("grid", "बिजलीघर से आपके स्विच तक — बिजली का जाल",
     "Electrical grid", "kaise"),
    ("cellular", "मोबाइल टावर आपके फ़ोन को कैसे ढूँढ लेता है",
     "Cellular network", "kaise"),
    ("sea_cable", "इंटरनेट समुद्र के नीचे बिछी तारों से चलता है",
     "Submarine communications cable", "kaise"),
    ("dam", "बाँध — पानी रोककर बिजली कैसे बनती है", "Dam", "kaise"),
    ("rail_signal", "रेल का सिग्नल — दो गाड़ियाँ एक पटरी पर क्यों नहीं आतीं",
     "Railway signalling", "kaise"),
    ("tbm", "मेट्रो की सुरंग ज़मीन के नीचे कैसे खोदी जाती है",
     "Tunnel boring machine", "kaise"),
    ("cold_chain", "टीका गाँव तक ठंडा कैसे पहुँचता है — कोल्ड चेन",
     "Cold chain", "kaise"),
    ("weather", "मौसम का पूर्वानुमान लगाया कैसे जाता है",
     "Weather forecasting", "kaise"),
    ("seismometer", "भूकंप की तीव्रता नापी कैसे जाती है", "Seismometer", "kaise"),
    ("banknote", "नोट कैसे छपते हैं और नकली की पहचान क्या है",
     "Banknote", "kaise"),
    ("barcode", "बारकोड की उन काली लकीरों में लिखा क्या होता है",
     "Barcode", "kaise"),
    ("refrigeration", "फ़्रिज ठंडा कैसे करता है", "Refrigeration", "kaise"),
    ("solar_panel", "सोलर पैनल धूप से बिजली कैसे बनाता है",
     "Solar panel", "kaise"),
    ("lightning", "बिजली आसमान से गिरती क्यों है", "Lightning", "kaise"),

    # ---------- bhugol
    ("monsoon", "मानसून आता कहाँ से है", "Monsoon", "bhugol"),
    ("himalaya", "हिमालय बना कैसे — और आज भी बढ़ रहा है", "Himalayas", "bhugol"),
    ("ganga", "गंगा — गोमुख से गंगासागर तक", "Ganges", "bhugol"),
    ("thar", "थार — रेगिस्तान होते हुए भी सबसे बसा हुआ",
     "Thar Desert", "bhugol"),
    ("sundarban", "सुंदरबन — जहाँ जंगल और समुद्र मिलते हैं",
     "Sundarbans", "bhugol"),
    ("western_ghats", "पश्चिमी घाट — मानसून को रोकने वाली दीवार",
     "Western Ghats", "bhugol"),
    ("nile", "नील — दुनिया की सबसे लंबी नदी", "Nile", "bhugol"),
    ("sahara", "सहारा — जो कभी हरा-भरा था", "Sahara", "bhugol"),
    ("amazon", "अमेज़न — धरती के फेफड़े", "Amazon rainforest", "bhugol"),
    ("tectonics", "ज़मीन के नीचे की प्लेटें — भूकंप की असली वजह",
     "Plate tectonics", "bhugol"),
    ("timezone", "पूरी दुनिया में एक ही वक़्त क्यों नहीं होता",
     "Time zone", "bhugol"),
    ("cyclone", "चक्रवात कैसे बनता है और उसे नाम कौन देता है",
     "Tropical cyclone", "bhugol"),
    ("glacier", "ग्लेशियर — जमी हुई नदियाँ जो चलती हैं", "Glacier", "bhugol"),
    ("mangrove", "मैंग्रोव — समुद्र की लहरों से गाँव बचाने वाले पेड़",
     "Mangrove", "bhugol"),

    # ---------- itihas
    ("indus", "सिंधु घाटी — पाँच हज़ार साल पुराने शहर",
     "Indus Valley Civilisation", "itihas"),
    ("ashoka", "सम्राट अशोक — युद्ध जीतकर युद्ध छोड़ देने वाला राजा",
     "Ashoka", "itihas"),
    ("nalanda", "नालंदा — दुनिया का सबसे पुराना विश्वविद्यालय",
     "Nalanda", "itihas"),
    ("konark", "कोणार्क — पत्थर का रथ", "Konark Sun Temple", "itihas"),
    ("gt_road", "ग्रैंड ट्रंक रोड — दो हज़ार साल पुरानी सड़क",
     "Grand Trunk Road", "itihas"),
    ("rail_history", "भारत में रेल कैसे आई", "History of rail transport in India",
     "itihas"),
    ("dandi", "दांडी मार्च — नमक से बनी आज़ादी की लड़ाई", "Salt March", "itihas"),
    ("samvidhan", "भारत का संविधान कैसे लिखा गया",
     "Constituent Assembly of India", "itihas"),
    ("green_revolution", "हरित क्रांति — भूख से आत्मनिर्भरता तक",
     "Green Revolution in India", "itihas"),
    ("operation_flood", "श्वेत क्रांति — दूध की वह क्रांति जो गाँव से चली",
     "Operation Flood", "itihas"),
    ("printing", "छापाखाना — वह मशीन जिसने पढ़ाई आम आदमी तक पहुँचाई",
     "Printing press", "itihas"),
    ("silk_road", "सिल्क रोड — व्यापार का वह रास्ता जिसने दुनिया जोड़ी",
     "Silk Road", "itihas"),
    ("great_wall", "चीन की दीवार — कितनी लंबी, और बनी क्यों",
     "Great Wall of China", "itihas"),
    ("suez", "स्वेज़ नहर — जिसने जहाज़ों का आधा रास्ता काट दिया",
     "Suez Canal", "itihas"),
    ("apollo11", "चाँद पर पहला कदम", "Apollo 11", "itihas"),

    # ---------- vigyan aur Bharat ki upalabdhiyan
    ("chandrayaan3", "चंद्रयान-3 — चाँद के दक्षिणी छोर पर पहुँचने वाला पहला देश",
     "Chandrayaan-3", "vigyan"),
    ("mangalyaan", "मंगलयान — पहली ही कोशिश में मंगल तक",
     "Mars Orbiter Mission", "vigyan"),
    ("isro", "इसरो — एक साइकिल से शुरू हुई कहानी",
     "Indian Space Research Organisation", "vigyan"),
    ("aryabhata", "आर्यभट — भारत का पहला उपग्रह",
     "Aryabhata (satellite)", "vigyan"),
    ("antarctica_india", "अंटार्कटिका में भारत के स्टेशन",
     "Indian Antarctic Programme", "vigyan"),
    ("penicillin", "पेनिसिलिन — एक भूल से मिली दवा जिसने करोड़ों जानें बचाईं",
     "Penicillin", "vigyan"),
    ("blood_type", "खून के ग्रुप — किसका खून किसे चढ़ सकता है",
     "Blood type", "vigyan"),
    ("photosynthesis", "पेड़ अपना खाना खुद कैसे बनाते हैं",
     "Photosynthesis", "vigyan"),
    ("eclipse", "ग्रहण क्यों लगता है", "Solar eclipse", "vigyan"),
    ("vaccine_how", "टीका शरीर के अंदर काम कैसे करता है", "Vaccine", "vigyan"),
]

GYAN_SYSTEM = "\n".join([
    'आप एक हिंदी न्यूज़ चैनल के लिए "जानने की बात" लिखते हैं — वह वीडियो जो कोई भी, कभी भी देखे तो कुछ नया समझ में आए।',
    '',
    'आपका दर्शक प्रयागराज, मिर्ज़ापुर, भदोही, वाराणसी और लखनऊ का आम आदमी है। वह पढ़ा-लिखा है पर वैज्ञानिक नहीं। उसे किताब नहीं चाहिए — उसे वह एक बात चाहिए जो समझ में आ जाए और जो वह किसी को बता सके।',
    '',
    'सिर्फ़ JSON लौटाइए, और कुछ नहीं।',
])

GYAN_RULES = "\n".join([
    'सिर्फ़ वही लिखिए जो नीचे दी गई सामग्री में है। कोई तारीख़, नाप, संख्या या नाम अपनी याद से मत जोड़िए — जो सामग्री में है, बस वही। सामग्री अंग्रेज़ी में है; लिखना हिंदी में है।',
    '',
    'ढाँचा — इसी क्रम में:',
    '1. पहला वाक्य एक सवाल या एक ऐसी बात हो जो रोक ले। "समुद्र के बीच में न सड़क होती है, न कोई निशान — फिर जहाज़ रास्ता कैसे पहचानता है?"',
    '2. फिर असल जवाब, सीधे-सादे शब्दों में। एक ही मुख्य बात — दस नहीं।',
    '3. फिर एक या दो ठोस तथ्य जो उसी सामग्री से हों (कितना लंबा, कितना पुराना, कितने लोग)।',
    '4. हो सके तो भारत से एक जोड़ — पर सिर्फ़ तभी जब वह सामग्री में सचमुच लिखा हो। ज़बरदस्ती मत जोड़िए।',
    '5. आख़िरी वाक्य एक बात याद रह जाने लायक हो। नारा नहीं, नसीहत नहीं।',
    '',
    'भाषा: घर की हिंदी। कठिन शब्द आए तो उसे एक बार आसान शब्दों में खोल दीजिए। अंग्रेज़ी शब्द वही जो लोग बोलते हैं।',
    'लंबाई: 150 से 200 शब्द।',
    '',
    'ये कभी नहीं:',
    '- कोई सेहत की सलाह, इलाज, दवा या खुराक। शरीर या बीमारी से जुड़ा विषय हो तो सिर्फ़ यह बताइए कि वह चीज़ काम कैसे करती है — यह कभी नहीं कि दर्शक को क्या करना चाहिए।',
    '- कोई धार्मिक या राजनीतिक दावा। इतिहास के विवाद वाले हिस्से पर मत जाइए।',
    '- "वैज्ञानिकों का मानना है", "कहा जाता है" जैसी बिना नाम की बातें।',
    '- कोई भी बात जो सामग्री में नहीं है।',
    '',
    'usable false कब:',
    '- सामग्री इतनी पतली हो कि उससे 150 शब्द ईमानदारी से न निकलें।',
    '- विषय ऐसा निकले जिस पर बिना विवाद के बात न हो सके।',
    'शक हो तो false।',
    '',
    'इसी आकार में JSON लौटाइए:',
    '{"usable": true, "skipReason": "", "headline_hi": "60 अक्षर तक",',
    ' "headline_en": "the same headline in English",',
    ' "lower_third_hi": "55 अक्षर तक, एक ही लाइन",',
    ' "script_hi": "पूरी स्क्रिप्ट, एक पैराग्राफ",',
    ' "youtube_title_hi": "90 अक्षर तक", "youtube_description_hi": "3 से 5 लाइन",',
    ' "tags": ["10 तक keywords"]}',
])


def _wiki_text(title):
    """Wikipedia ke lekh ka saaf text - uske apne API se.

    HTML ko chheelne ki koshish nahi karte. Wikipedia khud saaf text deta
    hai (explaintext), aur wahi kahin bharosemand hai.

    Naam thoda idhar-udhar ho to bhi kaam chale - isliye pehle seedha naam,
    aur wo na mile to Wikipedia ki apni khoj. Main saathhh sath ye bhi
    lauta ta hoon ki AAKHIR MEIN kaun sa lekh khula, taaki log mein dikhe
    aur galat lekh chup-chaap na nikal jaye.
    """
    def _ask(params):
        sy_net.throttle("wikipedia", 1.2)
        q = urllib.parse.urlencode(params)
        raw = sy_net.fetch(GYAN_API + "?" + q, headers=sy_net.wiki_headers(),
                           timeout=45)
        return json.loads(raw.decode("utf-8", "replace"))

    def _extract(title_):
        d = _ask({"action": "query", "format": "json", "redirects": "1",
                  "prop": "extracts", "explaintext": "1", "exsectionformat": "plain",
                  "titles": title_})
        pages = ((d.get("query") or {}).get("pages") or {})
        for _pid, p in pages.items():
            if "missing" in p:
                continue
            txt = str(p.get("extract") or "")
            if len(txt) >= GYAN_MIN_CHARS:
                return p.get("title") or title_, txt
        return "", ""

    got, txt = _extract(title)
    if txt:
        return got, txt

    d = _ask({"action": "query", "format": "json", "list": "search",
              "srsearch": title, "srlimit": "1"})
    hits = ((d.get("query") or {}).get("search") or [])
    if not hits:
        return "", ""
    return _extract(hits[0].get("title") or "")


def next_gyan():
    """Baari-baari se agla vishay - jo sabse der se nahi chala."""
    now = time.time()
    best, best_at = None, None
    for row in GYAN:
        last = float(st.kv_get("gyan_last_" + row[0], 0) or 0)
        if now - last < GYAN_REPEAT_DAYS * 86400:
            continue
        if best_at is None or last < best_at:
            best, best_at = row, last
    if not best:
        return None
    slug, title, page, topic = best
    return {"story_id": "gy_%s_%s" % (slug, time.strftime("%Y%m")),
            "title": title, "page": page, "slug": slug, "topic": topic,
            "score": 7}


def gyan_by_slug(slug):
    """Ek KHAAS vishay - Telegram par chune jaane ke baad."""
    for row in GYAN:
        if row[0] == slug:
            s_, title, page, topic = row
            return {"story_id": "gy_%s_%s" % (s_, time.strftime("%Y%m")),
                    "title": title, "page": page, "slug": s_, "topic": topic,
                    "score": 7}
    return None


def run_gyan(slug=""):
    """Ek baar mein ek hi - jab tak pichhli nikal na jaye.

    slug diya ho to baari ka hisaab nahi lagta - wahi vishay banta hai.
    """
    in_flight = sum(st.count_status(s, "gyan")
                    for s in ("pending", "producing", "awaiting", "approved"))
    if in_flight and not slug:
        return 0

    c = gyan_by_slug(slug) if slug else next_gyan()
    if not c:
        log("gyan: sab vishay abhi haal mein ho chuke hain")
        return 0
    if st.get(c["story_id"]):
        return 0

    try:
        page, text = _wiki_text(c["page"])
    except Exception as e:
        log("gyan ka lekh nahi khula (%s): %s" % (c["slug"], e))
        st.kv_set("gyan_last_" + c["slug"],
                  time.time() - (GYAN_REPEAT_DAYS - 3) * 86400)
        return 0
    if not text:
        log("gyan ka lekh khaali ya bahut chhota:", c["slug"])
        st.kv_set("gyan_last_" + c["slug"],
                  time.time() - (GYAN_REPEAT_DAYS - 30) * 86400)
        return 0
    if page and page.lower() != c["page"].lower():
        log("gyan: '%s' ki jagah '%s' lekh khula" % (c["page"], page))

    # Poora lekh nahi bhejte - shuruaati hissa hi wo hissa hai jismein
    # buniyadi baat hoti hai, aur usse aage lekh vishesagyon ke liye ho
    # jaata hai.
    user = "\n".join([
        "विषय: " + c["title"],
        "श्रेणी: " + c["topic"],
        "स्रोत: Wikipedia — " + (page or c["page"]),
        "", "मूल सामग्री:", text[:14000], "", "नियम", GYAN_RULES, "", TEACHER_STYLE])
    j = sy_ai.ask_json(GYAN_SYSTEM, user, max_tokens=3000)

    st.kv_set("gyan_last_" + c["slug"], time.time())

    if not j or j.get("usable") is not True:
        log("  sampadak ne roka:", str((j or {}).get("skipReason") or "")[:120])
        return 0
    script = re.sub(r"\s+", " ", str(j.get("script_hi") or "")).strip()
    if len(script) < 200:
        log("  script bahut chhoti - chhoda")
        return 0

    head = str(j.get("headline_hi") or c["title"])[:200]
    link = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
        (page or c["page"]).replace(" ", "_"))
    st.add_story({
        "story_id": c["story_id"],
        "beat": "gyan",
        "score": int(c["score"]),
        "sources": "WIKIPEDIA",
        "source_link": link,
        # Wikipedia CC BY-SA hai - uska naam dena shart hai, aur wo
        # description mein jaata hai. Aawaaz aur screen par nahi: wahi
        # niyam jo baaki har source par lagta hai.
        "attribution_line": "आधार: Wikipedia (CC BY-SA)",
        "headline_hi": head,
        "headline_en": str(j.get("headline_en") or "")[:200],
        "lower_third_hi": str(j.get("lower_third_hi") or head)[:140],
        "script_hi": script,
        "yt_title": str(j.get("youtube_title_hi") or head)[:95],
        "yt_description": str(j.get("youtube_description_hi") or ""),
        "tags": ", ".join(str(t) for t in (j.get("tags") or []))[:480],
    })
    log("gyan queue mein:", c["story_id"], "-", head[:50])
    return 1


# ==================== AI/TECH KI JAGRUKTA ====================
#
# Paanchwa "jaankari" beat - khaas taur par aapki apni maang se bana:
# darshak ko sirf ye nahi batana ki koi nayi ya purani technology KYA hai,
# balki ye bhi ki wo apne VYAPAR, kisi SEVA ya GHAR KE KAAM mein isse kaise
# fayda utha sakta hai. Baaki teen jaankari beat (yojana/kaam/gyan) suvidha
# aur itihas-bhugol par hain - ye beat khaas taur par AI/tech-jagrukta ke
# liye hai, taaki channel apne darshak ko is badalti duniya mein peeche na
# chhodein.
#
# Srot GYAN jaisa hi hai - wahi Wikipedia, wahi _wiki_text() function, wahi
# "tathya sirf wahi jo lekh mein hai" anushasan. Farq sirf itna hai: har
# script mein ek zaroori tukda jodna hai - "ise kaise istemal kar sakte
# hain" - jo aam, vyapak roop se maani gayi application hai (kisi ek
# company ka vigyapan nahi, koi jhoothi guarantee nahi). Sehat wale vishay
# (jaise ai_healthcare) par wahi purani chhoot nahi hai - GYAN jaisi hi
# saavdhaani (koi ilaaj/dawa ki salaah nahi, sirf technology kaise madad
# karti hai).
TECH_REPEAT_DAYS = 150

# (slug, Hindi shirshak, Wikipedia ka lekh, shreni: vyapar | seva | ghar | jagrukta)
TECH = [
    ("chatbot", "चैटबॉट — दुकान और सेवा में ग्राहक से बात करने वाली AI",
     "Chatbot", "seva"),
    ("genai", "जनरेटिव AI — लिखने, बनाने और डिज़ाइन करने वाली मशीन",
     "Generative artificial intelligence", "vyapar"),
    ("translate", "मशीन अनुवाद — भाषा की दीवार तोड़ने वाली तकनीक",
     "Machine translation", "seva"),
    ("speech_rec", "बोलकर लिखना — आवाज़ को शब्दों में बदलने वाली तकनीक",
     "Speech recognition", "ghar"),
    ("voice_assistant", "वॉइस असिस्टेंट — घर के काम अब सिर्फ़ आवाज़ से",
     "Virtual assistant", "ghar"),
    ("recommender", "नेटफ्लिक्स और अमेज़न आपकी पसंद कैसे जान लेते हैं",
     "Recommender system", "vyapar"),
    ("ocr", "OCR — कागज़ के दस्तावेज़ को कंप्यूटर में बदलने वाली तकनीक",
     "Optical character recognition", "seva"),
    ("facial_rec", "चेहरा पहचानने वाली तकनीक — कहाँ इस्तेमाल, क्या ख़तरा",
     "Facial recognition system", "jagrukta"),
    ("rpa", "रोबोटिक प्रोसेस ऑटोमेशन — दफ़्तर के दोहराए जाने वाले काम अब मशीन से",
     "Robotic process automation", "vyapar"),
    ("anomaly", "बैंक और ऐप धोखाधड़ी को तुरंत कैसे पकड़ लेते हैं",
     "Anomaly detection", "seva"),
    ("antispam", "स्पैम और फ़र्ज़ी मैसेज छानने वाली तकनीक",
     "Anti-spam techniques", "ghar"),
    ("tts", "टेक्स्ट-टू-स्पीच — लिखे हुए को आवाज़ में बदलने वाली तकनीक",
     "Speech synthesis", "seva"),
    ("computer_vision", "कंप्यूटर विज़न — मशीन को तसवीर 'दिखना' कैसे शुरू हुआ",
     "Computer vision", "vyapar"),
    ("llm", "लार्ज लैंग्वेज मॉडल — वह तकनीक जो सवाल पढ़कर जवाब लिखती है",
     "Large language model", "jagrukta"),
    ("deepfake", "डीपफेक — नकली तसवीर-वीडियो पहचानना क्यों ज़रूरी हो गया है",
     "Deepfake", "jagrukta"),
    ("home_automation", "स्मार्ट होम — घर के उपकरण अब आपस में जुड़े हुए",
     "Home automation", "ghar"),
    ("self_driving", "ख़ुद चलने वाली गाड़ी — तकनीक अभी कहाँ तक पहुँची",
     "Self-driving car", "jagrukta"),
    ("precision_ag", "खेत में AI — कम पानी, कम खाद, ज़्यादा पैदावार",
     "Precision agriculture", "vyapar"),
    ("telemedicine", "टेलीमेडिसिन — डॉक्टर की सलाह अब फ़ोन या वीडियो कॉल पर",
     "Telemedicine", "seva"),
    ("biometrics", "बायोमेट्रिक पहचान — उँगली और आँख से पहचान कैसे होती है",
     "Biometrics", "seva"),
    ("predictive_maint", "मशीन ख़राब होने से पहले ही पता चल जाए — यह तकनीक कैसे",
     "Predictive maintenance", "vyapar"),
    ("cloud_computing", "क्लाउड कंप्यूटिंग — दुकान का हिसाब अब इंटरनेट पर सुरक्षित",
     "Cloud computing", "vyapar"),
    ("3d_printing", "3D प्रिंटिंग — डिज़ाइन से सीधे असली चीज़ बनाने की तकनीक",
     "3D printing", "vyapar"),
    ("drone", "ड्रोन — खेत, डिलीवरी और निगरानी में इस्तेमाल",
     "Unmanned aerial vehicle", "vyapar"),
    ("fintech", "फिनटेक — मोबाइल से बैंकिंग और भुगतान की तकनीक",
     "Financial technology", "vyapar"),
    ("ai_healthcare", "अस्पतालों में AI — जाँच और इलाज में मदद कैसे",
     "Artificial intelligence in healthcare", "seva"),
]

TECH_SYSTEM = "\n".join([
    'आप एक हिंदी न्यूज़ चैनल के लिए "तकनीक की बात" लिखते हैं — यह बताने वाली वीडियो कि कोई तकनीक (ख़ासकर AI) क्या है, और आम आदमी अपने व्यापार, किसी सेवा या घर के काम में उससे कैसे फ़ायदा उठा सकता है।',
    '',
    'आपका दर्शक प्रयागराज, मिर्ज़ापुर, भदोही, वाराणसी और लखनऊ का है — छोटा दुकानदार, किसान, नौकरीपेशा, गृहिणी, विद्यार्थी। उसे कोई तकनीकी क्लास नहीं चाहिए, उसे बस यह समझ आना चाहिए कि यह चीज़ उसके काम की है या नहीं, और अगर है तो कैसे।',
    '',
    'सिर्फ़ JSON लौटाइए, और कुछ नहीं।',
])

TECH_RULES = "\n".join([
    'तकनीकी तथ्य — यह कब आई, कैसे काम करती है, कहाँ इस्तेमाल होती है — सिर्फ़ वही लिखिए जो नीचे दी गई सामग्री में है। सामग्री अंग्रेज़ी में है; लिखना हिंदी में है। कोई संख्या, तारीख़ या दावा अपनी तरफ़ से मत जोड़िए।',
    '',
    'ढाँचा — इसी क्रम में:',
    '1. पहला वाक्य एक ऐसी बात या सवाल हो जो रोक ले — किसी अपने आस-पास के काम से जुड़ा। "दुकान पर ग्राहक आधी रात को भी सवाल पूछे और जवाब तुरंत मिल जाए — यह अब मुमकिन है" — ऐसे।',
    '2. फिर बताइए यह तकनीक असल में है क्या और काम कैसे करती है — आसान शब्दों में, सामग्री के आधार पर।',
    '3. सबसे ज़रूरी हिस्सा: इसे कैसे इस्तेमाल करें। अपने व्यापार, किसी सेवा या घर के किसी काम में इसका एक ठोस, आम तौर पर जाना-पहचाना इस्तेमाल बताइए — जैसे ग्राहक सेवा में चैटबॉट, खेत की सिंचाई का हिसाब, दस्तावेज़ स्कैन करना। यह किसी एक कंपनी या ऐप का नाम लेकर विज्ञापन जैसा नहीं होना चाहिए — तकनीक के बारे में बताइए, ब्रांड के बारे में नहीं।',
    '4. एक संतुलन की बात भी जोड़िए — यह तकनीक क्या नहीं कर सकती, या कहाँ सावधानी ज़रूरी है (जैसे: निजी जानकारी शेयर करने से पहले सोचिए, हर सुझाव पर आँख मूँदकर भरोसा मत कीजिए)। यह डर फैलाने के लिए नहीं, ईमानदार तस्वीर देने के लिए है।',
    '5. आख़िरी वाक्य एक बात याद रह जाने लायक हो।',
    '',
    'भाषा: घर की हिंदी। तकनीकी शब्द आए तो उसे एक बार आसान शब्दों में खोल दीजिए। अंग्रेज़ी शब्द वही जो लोग बोलते हैं (ऐप, इंटरनेट, स्मार्टफ़ोन)।',
    'लंबाई: 150 से 200 शब्द।',
    '',
    'ये कभी नहीं:',
    '- किसी एक कंपनी, ऐप या प्रोडक्ट का नाम लेकर उसका प्रचार। तकनीक की बात कीजिए, ब्रांड की नहीं।',
    '- "यह ज़िंदगी बदल देगा", "यह सबसे अच्छा है" जैसे बिना आधार वाले दावे।',
    '- सेहत से जुड़े विषय पर कोई इलाज, दवा या जाँच की सलाह — सिर्फ़ यह बताइए कि तकनीक अस्पताल/डॉक्टर की मदद कैसे करती है, यह कभी नहीं कि दर्शक को क्या करना चाहिए। अंत में डॉक्टर या नज़दीकी अस्पताल से मिलने की बात ज़रूर हो।',
    '- कोई डरावना या "AI नौकरी छीन लेगी" जैसा बिना आधार वाला दावा।',
    '- कोई भी तथ्य जो सामग्री में नहीं है।',
    '',
    'usable false कब:',
    '- सामग्री इतनी पतली हो कि उससे 150 शब्द ईमानदारी से न निकलें।',
    '- तकनीक इतनी विशेषज्ञ/प्रयोगशाला-स्तर की हो कि आम दर्शक के किसी व्यापार, सेवा या घर के काम से उसका कोई सीधा, ईमानदार नाता ही न बनाया जा सके।',
    'शक हो तो false।',
    '',
    'इसी आकार में JSON लौटाइए:',
    '{"usable": true, "skipReason": "", "headline_hi": "60 अक्षर तक",',
    ' "headline_en": "the same headline in English",',
    ' "lower_third_hi": "55 अक्षर तक, एक ही लाइन",',
    ' "script_hi": "पूरी स्क्रिप्ट, एक पैराग्राफ",',
    ' "youtube_title_hi": "90 अक्षर तक", "youtube_description_hi": "3 से 5 लाइन",',
    ' "tags": ["10 तक keywords"]}',
])


def next_tech():
    """Baari-baari se agla vishay - jo sabse der se nahi chala."""
    now = time.time()
    best, best_at = None, None
    for row in TECH:
        last = float(st.kv_get("tech_last_" + row[0], 0) or 0)
        if now - last < TECH_REPEAT_DAYS * 86400:
            continue
        if best_at is None or last < best_at:
            best, best_at = row, last
    if not best:
        return None
    slug, title, page, topic = best
    return {"story_id": "tc_%s_%s" % (slug, time.strftime("%Y%m")),
            "title": title, "page": page, "slug": slug, "topic": topic,
            "score": 7}


def tech_by_slug(slug):
    """Ek KHAAS vishay - Telegram par chune jaane ke baad."""
    for row in TECH:
        if row[0] == slug:
            s_, title, page, topic = row
            return {"story_id": "tc_%s_%s" % (s_, time.strftime("%Y%m")),
                    "title": title, "page": page, "slug": s_, "topic": topic,
                    "score": 7}
    return None


def run_tech(slug=""):
    """Ek baar mein ek hi - jab tak pichhli nikal na jaye.

    slug diya ho to baari ka hisaab nahi lagta - wahi vishay banta hai.
    """
    in_flight = sum(st.count_status(s, "tech")
                    for s in ("pending", "producing", "awaiting", "approved"))
    if in_flight and not slug:
        return 0

    c = tech_by_slug(slug) if slug else next_tech()
    if not c:
        log("tech ki baat: sab vishay abhi haal mein ho chuke hain")
        return 0
    if st.get(c["story_id"]):
        return 0

    try:
        page, text = _wiki_text(c["page"])
    except Exception as e:
        log("tech ka lekh nahi khula (%s): %s" % (c["slug"], e))
        st.kv_set("tech_last_" + c["slug"],
                  time.time() - (TECH_REPEAT_DAYS - 3) * 86400)
        return 0
    if not text:
        log("tech ka lekh khaali ya bahut chhota:", c["slug"])
        st.kv_set("tech_last_" + c["slug"],
                  time.time() - (TECH_REPEAT_DAYS - 30) * 86400)
        return 0
    if page and page.lower() != c["page"].lower():
        log("tech: '%s' ki jagah '%s' lekh khula" % (c["page"], page))

    user = "\n".join([
        "विषय: " + c["title"],
        "श्रेणी: " + c["topic"],
        "स्रोत: Wikipedia — " + (page or c["page"]),
        "", "मूल सामग्री:", text[:14000], "", "नियम", TECH_RULES, "", TEACHER_STYLE])
    j = sy_ai.ask_json(TECH_SYSTEM, user, max_tokens=3000)

    st.kv_set("tech_last_" + c["slug"], time.time())

    if not j or j.get("usable") is not True:
        log("  sampadak ne roka:", str((j or {}).get("skipReason") or "")[:120])
        return 0
    script = re.sub(r"\s+", " ", str(j.get("script_hi") or "")).strip()
    if len(script) < 200:
        log("  script bahut chhoti - chhoda")
        return 0

    head = str(j.get("headline_hi") or c["title"])[:200]
    link = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
        (page or c["page"]).replace(" ", "_"))
    st.add_story({
        "story_id": c["story_id"],
        "beat": "tech",
        "score": int(c["score"]),
        "sources": "WIKIPEDIA",
        "source_link": link,
        "attribution_line": "आधार: Wikipedia (CC BY-SA)",
        "headline_hi": head,
        "headline_en": str(j.get("headline_en") or "")[:200],
        "lower_third_hi": str(j.get("lower_third_hi") or head)[:140],
        "script_hi": script,
        "yt_title": str(j.get("youtube_title_hi") or head)[:95],
        "yt_description": str(j.get("youtube_description_hi") or ""),
        "tags": ", ".join(str(t) for t in (j.get("tags") or []))[:480],
    })
    log("tech ki baat queue mein:", c["story_id"], "-", head[:50])
    return 1


if __name__ == "__main__":
    cfg.ensure_dirs()
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "news"
    if which == "yojana":
        print("nayi yojana khabrein:", run_yojana())
    elif which == "kaam":
        print("nayi kaam ki baat:", run_kaam())
    elif which == "gyan":
        print("nayi gyan ki baat:", run_gyan())
    elif which == "tech":
        print("nayi tech ki baat:", run_tech())
    else:
        print("nayi khabrein:", run_news())

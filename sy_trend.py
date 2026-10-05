"""Abhi Bharat mein kya chal raha hai - aur usme se kya banaya jaye.

YE FILE KYUN HAI

Ab tak vishay katar se uthta tha: feeds se jo aaya, usme se sabse zyada
ank wala. Us tarike mein ek buniyadi kami hai - wo ye bataata hi nahi ki
LOG kya dhoondh rahe hain. Ek achhi khabar jise koi khoj hi nahi raha, aur
ek aisi khabar jo aaj Bharat bhar mein khoji ja rahi hai - dono ek jaisi
dikhti thi.

Isliye do signal:

  1. Google Trends - Bharat mein abhi kya KHOJA ja raha hai.
     Google ka koi adhikarik API nahi hai. Ek sarvajanik RSS hai aur wahi
     hum padhte hain. Wo kabhi khaali bhi aa sakta hai, isliye ispar akela
     bharosa nahi kiya gaya - doosra signal saath chalta hai.

  2. YouTube - Bharat mein abhi kya DEKHA ja raha hai.
     Ye khoj nahi, asli views hain. Aur channel ka dhandha wahi hai,
     isliye is signal ko main zyada saccha maanta hoon. Chaabi pehle se
     hai (wahi jisse upload hoti hai) aur ek call ka kharch na ke barabar.

Dono ko milakar ek chhoti suchi banti hai, aur wo suchi Telegram par
buttons ban kar aapke paas jaati hai. Chunne ke BAAD hi lekh dhoondha
jaata hai aur script likhi jaati hai - isliye jo khabar chalni hi nahi,
uspar sampadak ka ek paisa nahi lagta.
"""
import json
import re
import time

import sy_config as cfg
import sy_net
import sy_store as st

GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=IN"
# YouTube ki "abhi Bharat mein sabse zyada dekhi ja rahi" suchi.
# Shreni ka number YouTube ka apna hai: 25 = News & Politics,
# 24 = Entertainment. Khaali chhodne par har shreni aati hai - viral
# section ke liye wahi chahiye, kyunki viral kisi ek shreni mein nahi
# hota.
YT_POPULAR = ("https://www.googleapis.com/youtube/v3/videos"
              "?part=snippet&chart=mostPopular&regionCode=IN"
              "&maxResults=30%s")
YT_CAT = {"news": "&videoCategoryId=25", "bolly": "&videoCategoryId=24",
          "viral": ""}
# GOOGLE NEWS AB YAHAN SE HAT CHUKA HAI - AUR YE JAANCH KA NATEEJA HAI
#
# Pehle is vishay par lekh Google News ke RSS se dhoondhe jaate the. Sep
# 2026 mein wo band ho gaya - band hone ki koi ghoshna nahi hui, bas
# chup-chaap kaam karna chhod diya:
#
#   - Uske har link ka roop ab "news.google.com/rss/articles/CBMi..." hai,
#     yaani Google ka apna beech ka pata.
#   - Purane roop mein us pate ke ANDAR asli pata base64 mein pada hota
#     tha. Naye mein kuch nahi hota - jaanch kar ke dekha.
#   - Us pate ko kholne par lekh nahi, Google ka khaali JS safha aata hai:
#     lagbhag 5,95,000 akshar, aur khabar ka ek shabd nahi.
#   - Upar se link_rank() us host ko pehle se chhod deta hai. Isliye
#     nakaami turant hoti thi - ek bhi link khola hi nahi jaata tha.
#
# Uski jagah GDELT hai. Ye ek muft suchkaank hai jo duniya bhar ki khabron
# ke PATE rakhta hai - koi chaabi nahi lagti, aur sabse badi baat: wo
# akhbaar ka SEEDHA pata deta hai. Jaanch mein 20 pate mile, 12 alag
# akhbaar, aur jitne kholne ki koshish ki gayi sab ke sab khule
# (3,000 se 9,000 akshar ke lekh).
#
# Google Trends ab bhi kaam mein hai - wo alag cheez hai aur uske saath
# akhbaar ka seedha pata pehle se aata hai (ht:news_item_url).
GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT KI ROK - AUR WO DO ROOP MEIN AATI HAI
#
# Pehle 6 second ka faasla rakha tha. Wo kam nikla: asli chalne par har
# /khabar par 429 aata raha. GDELT ki rok IP par hai aur kai minute tak
# chalti hai, isliye faasla 20 second kiya gaya - aur uske sath teen aur
# baatein.
#
# Doosri baat zyada zaroori hai: rok hamesha 429 ban kar nahi aati. Kai
# baar GDELT "200 theek hai" keh kar body mein JSON ki jagah saada text
# bhej deta hai. Tab program ne likha tha "jawab JSON nahi tha" aur wo
# nakaami samajh kar ruk gaya - jabki wo bhi rok hi thi aur ruk kar dobara
# poochhne se chal jaati. Ab dono ek hi cheez maani jaati hain.
GDELT_GAP = 20.0
_gdelt_last = 0.0

# Jo pate mil chuke unhe thodi der yaad rakh lete hain. Ek hi vishay par
# dobara poochhna sirf rok ke paas le jaata hai, naya kuch nahi deta.
GDELT_CACHE_MIN = 30
_cache = {}

# YAHAN PEHLE POORI-POORI SHRENIYAN KATI HUI THI - AUR WO GALAT THA
#
# Pehle yahan cricket, film, box office, trailer, share price, rashifal -
# sab shabd ke shabd rok diye gaye the. Wo ek sampadakiy faisla tha jo
# maine apne aap le liya tha, aur wo do wajah se galat tha:
#
#   1. Virat Kohli ya Shah Rukh Khan se judi khabar par log sach mein
#      aate hain, aur unki zindagi ki khabar bhi khabar hai. Ek shabd
#      "cricket" dekh kar poori khabar phenk dena view bhi phenkna hai.
#      Aur in logon ki MUFT LICENCE WALI tasveer maujood hoti hai, yaani
#      jo footage ki samasya baaki khabron mein hai, wo yahan hai hi nahi.
#
#   2. Aur asli baat: ab chunne wale AAP hain. Har vishay aapke button se
#      guzarta hai. Jab ek insaan har baar dekh raha hai, tab machine ko
#      pehle se shreniyan kaatne ki zaroorat hi nahi rehti - bekaar vikalp
#      ki keemat sirf screen par ek line hai.
#
# Isliye ab yahan sirf wo cheezein rukti hain jo KHABAR HO HI NAHI SAKTI -
# jinka jawab ek ankda ya ek link hota hai, koi kahani nahi. "India vs
# Australia live score" ek jaanch hai; "India ne Australia ko haraya" ek
# khabar hai, aur wo ab aayegi. "Admit card link" ek link hai; "is saal
# se exam ka tareeka badla" ek khabar hai.
TREND_BLOCK = re.compile(
    r"(live\s*score|score\s*card|scorecard|ball\s*by\s*ball|playing\s*(xi|11)|"
    r"full\s*highlights|match\s*highlights|"
    r"admit\s*card|answer\s*key|hall\s*ticket|merit\s*list|result\s*link|"
    r"cut\s*ऑफ|cut\s*off\s*(list|marks)|"
    r"lottery|sambad|"
    r"(share|stock|gold|silver|petrol|diesel)\s*(price|rate)\s*(today|आज)|"
    r"(nifty|sensex)\s*(today|live|now)|"
    r"full\s*movie|watch\s*online|free\s*download|torrent|"
    r"डाउनलोड|लाइव\s*स्कोर|एडमिट\s*कार्ड|आंसर\s*की)", re.I)


def log(*a):
    print("[trend]", *a, flush=True)


def _clean(s):
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    s = (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
         .replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'"))
    return re.sub(r"\s+", " ", s).strip()


def google_trends(limit=15):
    """Bharat mein abhi kya khoja ja raha hai. [{term, traffic, links}]

    Google Trends ka RSS aam RSS se thoda alag hai: har item ke andar uske
    apne namespace ke tag hote hain (ht:approx_traffic, ht:news_item), aur
    aam RSS parser unhe chhod deta hai. Isliye yahan seedha unhi tag ko
    padhte hain - aur news_item ka URL sone jaisa hai: wahi lekh baad mein
    script ka aadhaar banta hai, use dobara dhoondhna nahi padta.
    """
    try:
        raw = sy_net.get_text(GOOGLE_TRENDS_RSS, timeout=40)
    except Exception as e:
        log("Google Trends nahi khula:", e)
        return []
    out = []
    for block in re.findall(r"<item>(.*?)</item>", raw, re.S):
        mt = re.search(r"<title>(.*?)</title>", block, re.S)
        title = _clean(mt.group(1)) if mt else ""
        if not title:
            continue
        mtr = re.search(r"<ht:approx_traffic>(.*?)</ht:approx_traffic>", block, re.S)
        traffic = _clean(mtr.group(1)) if mtr else ""
        links = [_clean(u) for u in re.findall(
            r"<ht:news_item_url>(.*?)</ht:news_item_url>", block, re.S)]
        out.append({"term": title, "note": traffic, "links": links,
                    "signal": "Google"})
        if len(out) >= limit:
            break
    log("Google Trends se %d vishay" % len(out))
    return out


def youtube_trending(limit=15, kind="news"):
    """Bharat mein abhi kya DEKHA ja raha hai (News & Politics). [{term,...}]

    videos.list ka kharch ek unit hai - din bhar ke 10,000 mein se. Upload
    wali seema se iska koi lena-dena nahi.
    """
    try:
        import sy_youtube
        tok = sy_youtube.access_token()
    except Exception as e:
        log("YouTube ki chaabi nahi mili:", e)
        return []
    try:
        data = sy_net.get_json(YT_POPULAR % YT_CAT.get(kind, ""),
                               headers={"Authorization": "Bearer " + tok},
                               timeout=40)
    except Exception as e:
        log("YouTube trending nahi aaya:", e)
        return []
    out = []
    for it in (data.get("items") or []):
        sn = it.get("snippet") or {}
        title = _clean(sn.get("title"))
        if not title:
            continue
        out.append({"term": title, "note": _clean(sn.get("channelTitle")),
                    "links": [], "signal": "YouTube"})
        if len(out) >= limit:
            break
    log("YouTube (%s) se %d vishay" % (kind, len(out)))
    return out


def host_of(url):
    """URL ka akhbaar - button par dikhane ke liye."""
    m = re.match(r"https?://([^/]+)", str(url or ""))
    return (m.group(1).lower().replace("www.", "") if m else "")


def _key(term):
    return re.sub(r"[^a-z0-9]+", "", str(term or "").lower())[:40]


# Bollywood ke vishay pehchanne ke liye. Ye rok nahi hai - ye CHHANTI hai:
# bolly section mein sirf yahi aate hain, aur news section mein ye nahi
# aate (warna ek hi cheez do jagah chali jayegi).
FILM_HINT = re.compile(
    r"(bollywood|box\s*office|trailer|teaser|film|movie|cinema|actor|actress|"
    r"director|song|album|ott|netflix|prime\s*video|hotstar|"
    r"बॉलीवुड|फिल्म|फ़िल्म|ट्रेलर|अभिनेता|अभिनेत्री|सिनेमा|गाना)", re.I)


def topics_for(kind="news", want=3):
    """Kis section ke liye vishay chahiye - news, bolly, ya viral."""
    return news_topics(want=want, kind=kind)


def news_topics(want=2, kind="news"):
    """Dono signal milakar chunne layak vishay. Sabse upar sabse taaza.

    Ek hi vishay dono jagah aa sakta hai - use ek hi baar lete hain, par
    tab uska signal "Google + YouTube" ho jaata hai, aur wo sabse pakka
    vishay hota hai: log use khoj bhi rahe hain aur dekh bhi rahe hain.
    """
    # Google pehle, YouTube baad mein - jaan-boojhkar. Google ka vishay ek
    # saaf naam hota hai ("S. Jaishankar"), YouTube ka ek poora shirshak
    # ("S. Jaishankar on India-Russia ties | NDTV"). Dono ek hi baat hain,
    # par button par chhota naam hi padha jaata hai. Isliye Google ka naam
    # pehle jagah le leta hai aur YouTube uspar sirf apna signal jodta hai.
    items = google_trends() + youtube_trending(kind=kind)
    merged = {}
    for it in items:
        term = it["term"]
        if TREND_BLOCK.search(term):
            continue
        if len(term) < 4:
            continue
        # Film wale vishay sirf bolly mein, aur bolly mein sirf film wale.
        # Viral har cheez leta hai - wahi uska matlab hai.
        film = bool(FILM_HINT.search(term))
        if kind == "bolly" and not film:
            continue
        if kind == "news" and film:
            continue
        k = _key(term)
        if not k:
            continue

        # Wahi vishay pehle se hai? Poora naam ek jaisa hona zaroori nahi -
        # ek doosre ke andar aa jaana kaafi hai.
        hit = None
        for ek in merged:
            if ek == k or (len(ek) >= 8 and ek in k) or (len(k) >= 8 and k in ek):
                hit = ek
                break
        if hit:
            m = merged[hit]
            if it["signal"] not in m["signal"]:
                m["signal"] += " + " + it["signal"]
            m["links"] = (m["links"] or []) + (it["links"] or [])
            continue
        merged[k] = dict(it)

    # KRAM - AUR EK BAAT JO PEHLI RAAT MEIN SAAF DIKHI
    #
    # Google Trends Bharat ki suchi mein European football bahut aata hai:
    # "alex meret", "florian wirtz", "ferran torres". Un par khoj sach mein
    # hoti hai, par unka lekh bundesliga.com par hota hai - us khabar ka is
    # channel ke darshak se koi lena-dena nahi.
    #
    # Inhe ROKA nahi gaya hai - wo aapka faisla hai, aur aapne kaha tha ki
    # shreniyan mat kaatiye. Par kram badla gaya hai: jis vishay ka lekh
    # Bharat ke akhbaar par hai wo upar aayega, aur button par ab lekh ka
    # akhbaar bhi likha rehta hai - taaki dabane se PEHLE dikh jaye ki
    # khabar kahan ki hai.
    def _india(m):
        for u in (m.get("links") or []):
            h = host_of(u)
            if h.endswith(".in") or ".in/" in u or any(
                    k in h for k in ("india", "bharat", "ndtv", "aajtak",
                                     "amarujala", "jagran", "bhaskar",
                                     "hindustantimes", "timesofindia",
                                     "indianexpress", "livehindustan",
                                     "abplive", "news18", "zeenews")):
                return 1
        return 0

    # "BHARAT MEIN TRENDING" AUR "BHARAT KI KHABAR" EK CHEEZ NAHI HAI
    #
    # Ye farq is poore hisse ki jad hai. Google Trends ki Bharat wali suchi
    # mein wo sab aata hai jise Bharat mein log KHOJ rahe hain - aur usme
    # European football ke khiladi, videshi reality show, aur doosre deshon
    # ki apni sthaniya rajneeti sab shaamil hai. "alex meret" par sach mein
    # khoj hui thi. Par us khabar ka Prayagraj ke darshak se koi lena-dena
    # nahi.
    #
    # Pehle yahan sirf KRAM tha, chhanni nahi thi - aur kram bhi ulta tha:
    # "dono jagah trending" ko "Bharat ki khabar" se upar rakha gaya tha.
    # Yaani ek videshi vishay jo Google aur YouTube dono par tha, wo Bharat
    # ki us khabar se upar chala jaata tha jo sirf ek jagah thi. Isi wajah
    # se button par videshi vishay aa rahe the.
    #
    # Ab pehle sampadak ki nazar se ek chhanni lagti hai, phir kram.
    scored = _india_score(list(merged.values()))

    def rank(m):
        both = 1 if "+" in m["signal"] else 0
        # Bharat se judav SABSE UPAR. Uske baad hi baaki sab.
        return (scored.get(_key(m["term"]), 5), _india(m), both,
                1 if m.get("links") else 0)

    rows = sorted(merged.values(), key=rank, reverse=True)
    for m in rows:
        m["india"] = _india(m)
        m["where"] = host_of((m.get("links") or [""])[0])

    out = []
    for m in rows:
        k = _key(m["term"])
        # Jo vishay abhi haal mein chal chuka hai use dobara nahi.
        if float(st.kv_get("trend_last_" + k, 0) or 0) > time.time() - 3 * 86400:
            continue
        # Jise sampadak ne "Bharat ke darshak ke kaam ka nahi" kaha, wo
        # button par aata hi nahi. Ye shreni ki rok nahi hai - box office,
        # rashifal, share price sab chalte hain, agar wo Bharat ke hon.
        if scored.get(k, 5) < 4:
            log("chhoda (Bharat se matlab nahi): %s" % m["term"][:50])
            continue
        m["kind"] = kind
        m["score_in"] = scored.get(k, 5)
        out.append(m)
        if len(out) >= want:
            break
    return out


JUDGE_SYSTEM = (
    "Aap ek Hindi news channel ke sampadak hain. Channel ke darshak poorvi "
    "Uttar Pradesh ke hain - Prayagraj, Mirzapur, Bhadohi, Varanasi, "
    "Lucknow. Aapko trending vishayon ki suchi di jayegi. Har ek par ek "
    "ank dijiye: is vishay par banayi gayi video ko ye darshak dekhega ya "
    "nahi.\n\n"
    "0-3 = nahi dekhega. Kisi doosre desh ka apna andaruni maamla jiska "
    "Bharat se koi wasta nahi: videshi football league ka khiladi, kisi "
    "aur desh ki sthaniya rajneeti ya adalat, videshi reality show.\n"
    "4-6 = dekh sakta hai. Videshi baat jo Bharat ko chhooti hai - "
    "Bharat ki bhoomika, Bharatiya logon par asar (visa, tel ka daam, "
    "sona), ya koi Bharatiya vyakti us khabar mein.\n"
    "7-10 = zaroor dekhega. Bharat ki khabar, sarkari elaan aur yojana, "
    "Uttar Pradesh ya poorvi UP ka koi maamla, Bharatiya khiladi, "
    "abhineta, netaa - unke kaam ki bhi aur unki zindagi ki bhi.\n\n"
    "SHRENI ke aadhaar par ank mat ghataiye. Box office, film ka trailer, "
    "rashifal, share bazaar - ye sab chalte hain agar Bharat ke hon. "
    "Sirf ye dekhiye ki baat Bharat ke darshak se judti hai ya nahi.\n\n"
    "Sirf ek JSON object lautaiye, bina kisi aur baat ke:\n"
    '{"vishay": [{"term": "jaisa diya gaya waisa hi", "ank": 0-10}]}'
)


def _india_score(rows):
    """Har vishay par ek ank - Bharat ke darshak ke liye kitna kaam ka.

    Ek hi call poori suchi par. Nakaami par sab 5 - yaani koi chhanta nahi
    jaata aur purane jaisa kaam chalta rehta hai. Ye jaanch ek video banne
    se pehle lagti hai, isliye iska kharch us video se kahin kam hai jo
    bekaar ban jaati.
    """
    terms = [str(r.get("term") or "").strip() for r in rows]
    terms = [t for t in terms if t]
    if not terms:
        return {}
    out = {}
    try:
        import sy_ai
        j = sy_ai.ask_json(
            JUDGE_SYSTEM,
            "VISHAY:\n" + "\n".join("- " + t for t in terms[:25]),
            max_tokens=1200)
        for it in ((j or {}).get("vishay") or []):
            if not isinstance(it, dict):
                continue
            k = _key(str(it.get("term") or ""))
            if not k:
                continue
            try:
                out[k] = max(0, min(10, int(it.get("ank"))))
            except Exception:
                continue
    except Exception as e:
        log("vishayon ki parakh nahi ho payi:", e)
    return out


def _gdelt(query, timespan="3d", records=20, patient=True):
    """GDELT se lekh ke pate. Nakaami par khaali suchi - kabhi girta nahi.

    patient=False: rok mile to intezaar nahi, seedhe khaali. Tasveer ki
    khoj jaise chhote kaam ke liye - wahan 30+60 second rukna poori run
    kha jaata tha (Oct 2026, lambi video ki ek run 37 minute chali)."""
    global _gdelt_last
    wait = GDELT_GAP - (time.time() - _gdelt_last)
    if wait > 0:
        time.sleep(wait)

    url = (GDELT + "?query=" + sy_net.urllib.parse.quote(str(query)[:200])
           + "&mode=artlist&maxrecords=%d&format=json&timespan=%s"
           % (int(records), timespan))

    # Teen koshish, har baar pehle se lambi saans. GDELT ki rok kuch minute
    # rehti hai, isliye turant dobara poochhna use lambi hi karta hai.
    for pause in ((0, 30, 60) if patient else (0,)):
        if pause:
            log("GDELT saans le raha hai - %d second ruk kar dobara" % pause)
            time.sleep(pause)
        raw = ""
        try:
            raw = sy_net.get_text(url, timeout=45)
        except sy_net.HttpError as e:
            _gdelt_last = time.time()
            if e.status in (429, 503):
                continue
            log("GDELT nahi chala:", e)
            return []
        except Exception as e:
            _gdelt_last = time.time()
            log("GDELT nahi chala:", e)
            return []
        _gdelt_last = time.time()

        head = raw.lstrip()[:1]
        if head not in ("{", "["):
            # 200 aaya par JSON nahi - ye bhi rok hi hai, doosre roop mein.
            log("GDELT ne rok wala jawab bheja:",
                re.sub(r"\s+", " ", raw)[:90])
            continue

        try:
            arts = json.loads(raw).get("articles") or []
        except Exception as e:
            log("GDELT ka jawab toota hua tha:", str(e)[:60])
            return []
        return [str(a.get("url") or "") for a in arts if a.get("url")]

    log("GDELT teen baar rok par raha - abhi chhod rahe hain")
    return []


def _bing_links(term):
    """Doosra srot - tab ke liye jab GDELT saans le raha ho.

    Bing bhi apna beech ka pata deta hai, PAR Google ke ulat uske andar
    asli pata saaf pada hota hai (url= mein). Wo taala nahi, lifafa hai.
    Pehli jaanch mein yahi lifafa khulne se reh gaya tha - RSS mein "&"
    "&amp;" ban kar aata hai, isliye pata padha hi nahi ja raha tha. Wahi
    ek line ki galti thi jiski wajah se Bing "kaam ka nahi" dikha.
    """
    url = ("https://www.bing.com/news/search?q="
           + sy_net.urllib.parse.quote(str(term)[:120])
           + "&format=RSS&cc=IN")
    try:
        raw = sy_net.get_text(url, timeout=40)
    except Exception as e:
        log("Bing nahi chala:", e)
        return []

    out = []
    for block in re.findall(r"<item>(.*?)</item>", raw, re.S):
        m = re.search(r"<link>(.*?)</link>", block, re.S)
        if not m:
            continue
        link = _clean(m.group(1))          # &amp; -> & yahin hota hai
        try:
            q = sy_net.urllib.parse.urlparse(link).query
            v = sy_net.urllib.parse.parse_qs(q).get("url")
            if v and v[0].startswith("http"):
                out.append(sy_net.urllib.parse.unquote(v[0]))
        except Exception:
            pass
    return out


def search_links(term, limit=8):
    """Is vishay par taaze lekh - seedhe akhbaar ke pate.

    Do baar poochha jaata hai aur ye jaan-boojhkar hai: pehle sirf Bharat
    ke akhbaar, phir koi bhi. Wajah ye ki channel Bharat ka hai - wahi
    khabar ek Indian akhbaar mein milna behtar hai. Par jab baat Bharat se
    bahar ki ho (ya Indian akhbaar ne abhi likha na ho), to khabar chhod
    dene se achha hai kisi aur ka lekh le lena.

    Ek hi akhbaar ke kai pate nahi lautaye jaate. Ek safha na khule to
    doosre par jaana hi is poore intezaam ka matlab hai, aur wo tabhi kaam
    karta hai jab doosra pata kisi AUR akhbaar ka ho.
    """
    term = str(term or "").strip()
    if len(term) < 3:
        return []

    hit = _cache.get(term.lower())
    if hit and time.time() - hit[0] < GDELT_CACHE_MIN * 60:
        return list(hit[1])

    links = _gdelt(term + " sourcecountry:india")
    # Doosri call SIRF tab jab pehli poori tarah khaali gayi. Pehle ye
    # "teen se kam" par bhi chalti thi - yaani lagbhag har baar - aur wahi
    # rok ko bulawa de rahi thi.
    if not links:
        links = _gdelt(term)
    # GDELT chup hai to Bing se kaam chala lete hain. Ye utna achha nahi
    # (kam akhbaar, kam Bharat ke), par khabar chhod dene se behtar hai.
    if not links:
        links = _bing_links(term)

    # Ek akhbaar se ek hi. Aur wo pehle jinke lekh khulna jaancha hua hai.
    out, seen = [], set()
    for u in links:
        h = sy_net.host(u)
        if not h or h in seen:
            continue
        seen.add(h)
        out.append(u)
    out.sort(key=_rank)
    out = out[:limit]
    if out:
        _cache[term.lower()] = (time.time(), list(out))
    return out


def _rank(url):
    """Jinke lekh khulte hain unhe upar. Ye jaanch ka nateeja hai."""
    try:
        import sy_ingest
        return sy_ingest.link_rank(url)
    except Exception:
        return 1


def mark_used(term):
    st.kv_set("trend_last_" + _key(term), time.time())

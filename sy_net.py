"""Internet se cheezein laane wale saajha auzaar.

RSS padhna, lekh ka text nikalna, file utaarna - teenon jagah (khabar,
yojana, tasveer) ek hi code se hote hain, taaki ek sudhaar sab jagah lage.
Purane system mein yahi teen kaam teen alag n8n node mein bikhre hue the
aur unke regex bhi alag-alag the.
"""
import gzip
import io
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

# SARKARI SAFHE AUR CERTIFICATE KI EK ASLI DIKKAT
#
# Bahut se .gov.in safhe Python mein khulte hi nahi:
#     SSL: CERTIFICATE_VERIFY_FAILED - unable to get local issuer certificate
# jabki wahi safha browser mein aaram se khulta hai. Ye hamari galti nahi
# hai aur na hi wo safha nakli hai: un servers par BEECH WALA certificate
# (intermediate) laga hi nahi hota. Browser wo khud utha laata hai (AIA
# fetching), Python nahi uthata - isliye wo ruk jaata hai.
#
# Iska SAHI ilaaj jaanch band karna NAHI hai. Sahi ilaaj ye hai ki Python
# bhi wahi bharosa istemaal kare jo Windows khud karta hai - Windows ke
# paas wo beech wala certificate pehle se hota hai. `truststore` naam ka
# chhota package theek yahi karta hai.
#
# Wo install ho to laga dete hain; na ho to kuch nahi badalta aur wo safhe
# pehle ki tarah band rehte hain. Jaanch kahin se kahin tak dheeli nahi
# hoti - bas wo Windows ke haath mein chali jaati hai.
#
# Chaalu karne ke liye ek baar:      pip install truststore
try:
    import truststore as _ts
    _ts.inject_into_ssl()
    _TRUSTSTORE = True
except Exception:
    _TRUSTSTORE = False


def truststore_on():
    return _TRUSTSTORE


def _prefer_ipv4():
    """Pehle IPv4 aazmao, phir IPv6.

    Windows par jab IPv6 ka raasta banta to hai par chalta nahi, to har
    request pehle usi par lagbhag 20 second atakti hai aur uske baad IPv4
    par girti hai. Telegram ka har jawab isi wajah se 22 second le raha tha.
    IPv6 hataya nahi hai - sirf kram badla hai, taaki jahan wo sach mein
    chalta ho wahan bhi kaam chalta rahe.
    """
    real = socket.getaddrinfo

    def ordered(*a, **kw):
        res = real(*a, **kw)
        return sorted(res, key=lambda r: 0 if r[0] == socket.AF_INET else 1)

    socket.getaddrinfo = ordered


_prefer_ipv4()

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "hi-IN,hi;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip",
}


def is_offline_error(e):
    """Kya ye "internet hi nahi hai" wali galti hai?

    Windows par jab DNS jawab nahi deta to har request 11001
    (getaddrinfo failed) deti hai - har host par, ek jaisi. Wo koi program
    ki gadbad nahi hoti; us waqt karne ko kuch hota bhi nahi siwaye intezaar
    ke. Ise pehchanna isliye zaroori hai ki tab hum chup rahein aur baar-baar
    koshish na karein - warna har 20 second par wahi chaar laal lines aati
    hain aur asli galtiyan unme dab jaati hain.
    """
    if isinstance(e, socket.gaierror):
        return True
    t = str(e)
    return ("getaddrinfo failed" in t
            or "11001" in t                      # Windows: host nahi mila
            or "Errno -2" in t or "Errno -3" in t  # Linux: naam hal nahi hua
            or "Temporary failure in name resolution" in t)


# ------------------------------------------------- Wikimedia ka apna niyam
#
# Commons har request par HTTP 429 de raha tha - ek bhi tasveer nahi aa
# rahi thi. Wajah hamari taraf thi, unki nahi.
#
# Wikimedia ki apni policy hai: har apne-aap chalne wale program ko User-
# Agent mein apna NAAM aur SAMPARK ka pata bhejna hota hai. Jo aisa nahi
# karte unhe wo jaan-boojhkar sabse sakht rate-limit mein daal dete hain -
# "a restrictive rate limit tier designed to prevent anonymous scraping".
#
# Hum Chrome ka User-Agent bhej rahe the, yaani browser bankar. Wo sabse
# bura roop hai: na naam, na sampark, aur upar se bhes badla hua. Isi ka
# nateeja 429 tha.
#
# Ab hum apna naam batate hain. Sampark ka pata config.ini se aata hai -
# aur wo AAPKA hai, isliye maine wahan kuch apne se nahi bhara.
WIKI_HOSTS = ("wikimedia.org", "wikipedia.org", "wikidata.org")


def wiki_headers():
    contact = ""
    try:
        import sy_config as _cfg
        contact = (_cfg.get("contact", "email") or _cfg.get("contact", "url") or "")
    except Exception:
        pass
    who = "SatyaYatraNews/1.0"
    if contact:
        who += " (%s)" % contact
    else:
        who += " (Hindi news bulletin bot; sampark config.ini mein nahi bhara)"
    return {"User-Agent": who + " python-urllib/3",
            "Accept-Language": "hi,en;q=0.8",
            "Accept-Encoding": "gzip"}


_last_hit = {}


def throttle(key, seconds):
    """Ek hi jagah par do request ke beech kam se kam itna antar.

    Wikimedia kehta hai ki apne-aap chalne wale program ek-ek karke
    request bhejein, jhund mein nahi. Ek khabar par hum darjanon baar
    Commons ko pukarte hain - bina is rok ke wo jayaz hi rate-limit hai.
    """
    now = time.time()
    wait = _last_hit.get(key, 0) + seconds - now
    if wait > 0:
        time.sleep(wait)
    _last_hit[key] = time.time()


class HttpError(Exception):
    """4xx/5xx ki galti - status, url, aur server ne jo asli jawab diya
    (body) teeno rakhta hai.

    PEHLE YAHAN SIRF "HTTP 400: https://..." CHHAPTA THA
    ======================================================
    body hamesha yahan store hoti thi, par jo bhi is Exception ko seedhe
    log("...", e) kar deta (ya Telegram par "Wajah:" mein bhej deta), use
    sirf status aur url dikhta tha - server ne KYUN mana kiya (galat
    model, khatam hua balance, bigda hua JSON, waghera) kabhi nazar nahi
    aata tha. Ye galti ek jagah nahi thi - har naye caller (sy_ai.py,
    phir sy_tts.py mein Sarvam ka 402) mein alag se saamne aayi.

    Ab body seedhe is Exception ke apne message mein jud jaati hai,
    isliye koi bhi jagah jo sirf str(e) chhaapti hai use bhi asli wajah
    dikh jaati hai - alag se .body nikalna zaroori nahi."""
    def __init__(self, status, url, body=""):
        self.status = status
        self.url = url
        self.body = body
        msg = "HTTP %s: %s" % (status, url)
        b = (body or "").strip()
        if b:
            msg += " | " + b[:400]
        Exception.__init__(self, msg)


def _err_body(e):
    """Galti ka jawab padhne layak banao.

    YAHAN EK CHUPI HUI GALTI THI AUR USNE DEBUGGING MEHNGI KAR DI
    =============================================================
    Pehle yahan likha tha: e.read()[:800].decode(...). Usme do gadbad thi,
    aur dono ek saath chalti thi:

      1. Hum har request mein "Accept-Encoding: gzip" bhejte hain, isliye
         galti ka jawab bhi gzip mein aata hai. Theek jawab ko to upar
         khola jaata hai, par galti wale ko nahi - wo kabhi khola hi nahi
         gaya.
      2. Aur [:800] DABAANE SE PEHLE lag raha tha. Gzip ka aadha tukda
         kholna waise bhi namumkin hai, isliye jawab ka bachna bhi
         mushkil ho gaya.

    Nateeja: Google ne jab Veo par 400 kaha aur wajah bhi likhi, screen par
    sirf "���RPPJ-*�/R�R�r..." chhapa. Wajah ek request door thi aur padhi
    hi nahi ja saki.

    Ab: poora jawab padho, gzip ho to kholo (header dekh kar, aur na ho to
    pehle do byte dekh kar - kuch server header bhejte hi nahi), phir kaato.
    """
    raw = b""
    try:
        raw = e.read()
    except Exception:
        return ""
    try:
        enc = (e.headers.get("Content-Encoding") or "").lower()
    except Exception:
        enc = ""
    try:
        if enc == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        elif enc == "deflate":
            import zlib
            raw = zlib.decompress(raw)
    except Exception:
        pass
    return raw[:1500].decode("utf-8", "replace")


def fetch(url, headers=None, data=None, method=None, timeout=45, retries=2):
    """Ek request. Bytes lauta deta hai.

    Do baar dobara koshish karta hai, badhte hue intezaar ke saath. Ye
    isliye hai ki DNS kabhi-kabhi kshan bhar ke liye jawab nahi deta
    (EAI_AGAIN) - aur us ek jhatke se poora run marta tha.
    """
    h = dict(DEFAULT_HEADERS)
    if headers:
        h.update(headers)
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
        h.setdefault("Content-Type", "application/json")

    last = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as e:
            body = _err_body(e)
            # 4xx dobara koshish karne se theek nahi hota - wahin ruk jaate hain.
            if 400 <= e.code < 500 and e.code not in (408, 429):
                raise HttpError(e.code, url, body)
            if e.code == 429:
                # Server khud batata hai ki kitni der ruko - wahi maniye.
                try:
                    ra = float(e.headers.get("Retry-After") or 0)
                except Exception:
                    ra = 0
                time.sleep(min(30.0, ra if ra > 0 else 5.0 * (attempt + 1)))
            last = HttpError(e.code, url, body)
        except (urllib.error.URLError, socket.timeout, OSError) as e:
            last = e
        if attempt < retries:
            time.sleep(2 * (attempt + 1))
    raise last


def get_text(url, **kw):
    return fetch(url, **kw).decode("utf-8", "replace")


def get_json(url, **kw):
    return json.loads(fetch(url, **kw).decode("utf-8", "replace"))


def post_json(url, payload, headers=None, timeout=180, retries=1):
    raw = fetch(url, headers=headers, data=payload, method="POST",
                timeout=timeout, retries=retries)
    return json.loads(raw.decode("utf-8", "replace"))


def download(url, path, max_bytes=80 * 1024 * 1024, timeout=180):
    """File utaar kar rakh do. Bahut badi ho to chhod do."""
    raw = fetch(url, timeout=timeout)
    if len(raw) > max_bytes:
        raise HttpError(413, url, "file bahut badi hai")
    with open(path, "wb") as f:
        f.write(raw)
    return len(raw)


# ------------------------------------------------------------------- RSS

def _unescape(v):
    return (str(v or "")
            .replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))


def _tag(chunk, name):
    m = re.search(r"<%s[^>]*>([\s\S]*?)</%s>" % (name, name), chunk, re.I)
    if not m:
        return ""
    v = re.sub(r"<!\[CDATA\[([\s\S]*?)\]\]>", r"\1", m.group(1))
    v = re.sub(r"<[^>]+>", " ", v)
    return re.sub(r"\s+", " ", _unescape(v)).strip()


def parse_rss(xml):
    """RSS/Atom se items nikaalo: title, link, summary, published.

    Poora XML parser jaan-boojhkar nahi lagaya - kai Indian feeds mein
    tooti hui entity aur bina band hue tag hote hain, jinpar sakht parser
    poora feed chhod deta hai. Yahan ek kharab item chhootta hai, baaki
    chalte rehte hain.
    """
    out = []
    text = str(xml or "")
    blocks = re.split(r"<item[\s>]", text, flags=re.I)[1:]
    kind = "item"
    if not blocks:
        blocks = re.split(r"<entry[\s>]", text, flags=re.I)[1:]
        kind = "entry"
    for raw in blocks:
        chunk = re.split(r"</%s>" % kind, raw, flags=re.I)[0]
        title = _tag(chunk, "title")
        link = _tag(chunk, "link")
        if not link:
            m = re.search(r'<link[^>]*href="([^"]+)"', chunk, re.I)
            if m:
                link = _unescape(m.group(1))
        if not title or not link:
            continue
        out.append({
            "title": title,
            "link": link.strip(),
            "summary": (_tag(chunk, "description")
                        or _tag(chunk, "summary")
                        or _tag(chunk, "content:encoded"))[:1500],
            "published": (_tag(chunk, "pubDate") or _tag(chunk, "published")
                          or _tag(chunk, "updated")),
        })
    return out


def parse_date(s):
    """Feed ki tareekh -> epoch second. Na samajh aaye to None.

    None lautana zaroori hai. Purane system mein tareekh na milne par
    "abhi" maan liya jaata tha, jisse har purani khabar ko poora freshness
    score mil jaata tha aur wo taazi khabron se aage nikal jaati thi.
    """
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%d %H:%M:%S", "%d %b %Y %H:%M:%S %z"):
        try:
            import datetime
            d = datetime.datetime.strptime(s.replace("GMT", "+0000"), fmt)
            if d.tzinfo is None:
                d = d.replace(tzinfo=datetime.timezone.utc)
            return d.timestamp()
        except Exception:
            continue
    return None


# ------------------------------------------------------- lekh ka text

JUNK = re.compile(
    "(कॉपीराइट|सर्वाधिकार|सब्सक्राइब|सब्सक्रिप्शन|प्रीमियम मेंबरशिप|लॉग इन कर|"
    "ऐप डाउनलोड|डाउनलोड करें|यह भी पढ़|ये भी पढ़|संबंधित खबर|विज्ञापन|फॉलो कर|"
    "Copyright|Subscribe|Subscription|Follow us|Advertisement|Trending|"
    "Also Read|Read More|Sign in|newsletter)", re.I)


def article_text(html, min_chars=400):
    """Safhe se lekh nikaalo - menu, vigyapan aur 'yah bhi padhein' ke bina.

    Pehle <p> aazmate hain (aam news template), aur kam pade to poore safhe
    se lambi lines uthate hain (PIB jaisi jagah, jahan sab kuch div mein
    hota hai). Kam se kam min_chars na mile to khaali lautate hain - adhoore
    lekh par script likhwane se behtar hai kuch na likhwana.
    """
    src = str(html or "")
    if len(src) < 500:
        return ""

    body = src
    for tag in ("script", "style", "noscript", "nav", "header", "footer",
                "aside", "form"):
        body = re.sub(r"<%s[\s\S]*?</%s>" % (tag, tag), " ", body, flags=re.I)

    def clean(v):
        return re.sub(r"\s+", " ", _unescape(re.sub(r"<[^>]+>", " ", v))).strip()

    lines = []
    for m in re.finditer(r"<p[^>]*>([\s\S]*?)</p>", body, re.I):
        t = clean(m.group(1))
        if len(t) < 25 or JUNK.search(t):
            continue
        lines.append(t)
    text = "\n".join(lines)

    if len(text) < min_chars:
        raw = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/td)[^>]*>", "\n", body, flags=re.I)
        raw = _unescape(re.sub(r"<[^>]+>", " ", raw))
        alt = []
        for ln in raw.split("\n"):
            t = re.sub(r"\s+", " ", ln).strip()
            if len(t) < 40 or JUNK.search(t):
                continue
            alt.append(t)
        if len("\n".join(alt)) > len(text):
            text = "\n".join(alt)

    text = text[:9000]
    return text if len(text) >= min_chars else ""


def host(url):
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:
        return ""

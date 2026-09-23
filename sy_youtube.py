"""YouTube par upload - aapke apne OAuth client se.

Yahi wo badlav hai jiski kami se upload "too many requests" de raha tha.
n8n apne saajha OAuth app se bhejta tha, isliye quota duniya bhar ke n8n
users ke saath bantta tha aur aapke apne project ka 10,000 chhua tak nahi
gaya tha. Ab har upload aapke apne project se jaata hai.

Google ki koi library nahi lagai - sab kuch seedha HTTPS par hai. Ek
dependency kam, aur pip par kuch install karne ki zaroorat nahi.
"""
import json
import os
import time
import urllib.parse
import webbrowser

import sy_config as cfg
import sy_net

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
DEVICE = "https://oauth2.googleapis.com/device/code"
UPLOAD = ("https://www.googleapis.com/upload/youtube/v3/videos"
          "?uploadType=resumable&part=snippet,status")
THUMB = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId="
SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube"

# SERVER PAR SIGN-IN - BINA BROWSER KE
#
# Server par koi browser nahi hota, isliye purana tareeka (loopback par
# sunna aur browser kholna) wahan chal hi nahi sakta. Google ka apna
# "TV aur chhote input wale device" wala tareeka theek isi ke liye hai:
# server ek chhota code dikhata hai, aap wo code apne PHONE par daal kar
# ijaazat de dete hain.
#
# Do baatein jo Google ke apne kagaz se pakki ki gayi hain:
#
#   1. Iske liye OAuth client ka kism "TVs and Limited Input devices"
#      hona chahiye. Desktop wala client ismein nahi chalta - isliye
#      Google Cloud Console mein ek NAYA client banana padta hai (muft,
#      do minute ka kaam). Wo config.ini mein [youtube] device_client_id
#      / device_client_secret mein jaata hai.
#
#   2. Is tareeke mein sirf kuch scope milte hain - youtube.upload UNME
#      NAHI hai, par poora "youtube" scope hai. Upload usi se ho jaata
#      hai (videos.insert poore youtube scope par chalta hai), isliye
#      yahan wahi ek scope maangte hain.
DEVICE_SCOPE = "https://www.googleapis.com/auth/youtube"


def log(*a):
    print("[youtube]", *a, flush=True)


class RateLimited(Exception):
    """YouTube ne abhi mana kiya hai - baad mein khud koshish karenge."""


class SignInExpired(Exception):
    """Sign-in khatm ho gaya - dobara signin.bat chalana padega.

    App "Testing" mein hai, aur Google Testing wale app ka refresh token
    har 7 din mein khatam kar deta hai. Production mein le jaane ke liye
    website, privacy policy aur verified domain chahiye - wo abhi nahi hai.
    Isliye ye hafte mein ek baar hoga. Chup-chaap fail hone se bahut behtar
    hai ki system khud bata de.
    """


# ------------------------------------------------------------ sign-in

def _save(tok):
    with open(cfg.YT_TOKEN, "w", encoding="utf-8") as f:
        json.dump(tok, f)


def _load():
    if not os.path.exists(cfg.YT_TOKEN):
        return {}
    try:
        with open(cfg.YT_TOKEN, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def device_client():
    """TV-kism ka client - server wale sign-in ke liye. (id, secret)"""
    cid = cfg.get("youtube", "device_client_id")
    csec = cfg.get("youtube", "device_client_secret")
    if not cid or not csec:
        raise cfg.ConfigError(
            "config.ini mein [youtube] device_client_id aur "
            "device_client_secret bhariye. Ye 'TVs and Limited Input "
            "devices' kism ka client hai - Desktop wala yahan nahi chalta.")
    return cid, csec


def sign_in_device(notify=None):
    """Bina browser ke sign-in. Server ke liye - aur phone se hota hai.

    Server ek chhota code dikhata hai; aap phone par ek safha khol kar wo
    code daal dete hain aur ijaazat de dete hain. Bas.

    notify: ek function jo (sandesh) leta hai - isse code Telegram par bhi
    chala jaata hai, taaki aapko server dekhna hi na pade.
    """
    cid, csec = device_client()
    d = sy_net.post_json(DEVICE, urllib.parse.urlencode({
        "client_id": cid, "scope": DEVICE_SCOPE}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60)

    code = str(d.get("user_code") or "")
    url = str(d.get("verification_url") or d.get("verification_uri") or "")
    dev = str(d.get("device_code") or "")
    gap = float(d.get("interval") or 5)
    ttl = float(d.get("expires_in") or 1800)

    msg = ("YouTube sign-in:\n\n1. Phone par ye safha kholiye:\n%s\n\n"
           "2. Ye code daaliye:\n%s\n\n"
           "(Ye code %d minute mein bekaar ho jayega.)" % (url, code, ttl / 60))
    log(msg.replace("\n", " "))
    if notify:
        try:
            notify(msg)
        except Exception:
            pass

    stop = time.time() + ttl
    while time.time() < stop:
        time.sleep(gap)
        try:
            tok = sy_net.post_json(TOKEN, urllib.parse.urlencode({
                "client_id": cid, "client_secret": csec, "device_code": dev,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            }).encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=60, retries=0)
        except sy_net.HttpError as e:
            body = e.body or ""
            if "authorization_pending" in body:
                continue
            if "slow_down" in body:
                gap += 5
                continue
            if "expired_token" in body:
                raise SignInExpired("code ki miyaad khatam - dobara chalaiye")
            raise
        if tok.get("refresh_token"):
            tok["obtained_at"] = time.time()
            tok["device"] = True
            _save(tok)
            log("sign-in ho gaya")
            return True
    raise SignInExpired("code par koi jawab nahi aaya")


def sign_in():
    """Pehli baar. Browser khulega, aap sign in karenge, bas ek baar.

    Loopback par sunte hain (Desktop app ka tareeka) - isliye kisi public
    URL ya tunnel ki zaroorat nahi.
    """
    import http.server
    import socketserver

    cid, csec = cfg.youtube_client()
    holder = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            holder["code"] = (q.get("code") or [""])[0]
            holder["error"] = (q.get("error") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h2>Ho gaya. Ab ye tab band kar dijiye.</h2>".encode("utf-8"))

        def log_message(self, *a):
            pass

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
        # Hamesha ke liye intezaar nahi. Bina iske, agar koi browser mein
        # sign in na kare to program yahin ruka reh jaata.
        httpd.timeout = 300
        port = httpd.server_address[1]
        redirect = "http://127.0.0.1:%d/" % port
        url = AUTH + "?" + urllib.parse.urlencode({
            "client_id": cid, "redirect_uri": redirect,
            "response_type": "code", "scope": SCOPE,
            "access_type": "offline", "prompt": "consent"})
        log("browser mein sign in kijiye:")
        log(url)
        try:
            webbrowser.open(url)
        except Exception:
            pass
        httpd.handle_request()

    if holder.get("error") or not holder.get("code"):
        raise RuntimeError("sign-in poora nahi hua: " + str(holder.get("error")))

    tok = sy_net.post_json(TOKEN, urllib.parse.urlencode({
        "code": holder["code"], "client_id": cid, "client_secret": csec,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60)
    if not tok.get("refresh_token"):
        raise RuntimeError("refresh_token nahi mila - dobara sign in kijiye")
    tok["obtained_at"] = time.time()
    _save(tok)
    log("sign-in ho gaya")
    return tok


def access_token():
    """Chalta hua token. Sign-in yahan se KABHI shuru nahi hota.

    Kyun: sign-in browser kholta hai aur jawab ka intezaar karta hai. Agar
    ye main loop ke andar se ho jaye to poora program wahin ruk jaata hai -
    aur aap door hue to raat bhar ruka rehta hai. Isliye sign-in ek alag,
    jaan-boojhkar chalaya jaane wala kadam hai (signin.bat).
    """
    tok = _load()
    if not tok.get("refresh_token"):
        # SignInExpired, RuntimeError nahi: tick_upload isi ko pehchaan kar
        # khabar 'approved' par rakhta hai aur sign-in maangta hai. Pehle
        # yahan RuntimeError tha - token na hone par video 'failed' ho
        # jaati thi. Cloud par pehli run mein token hota hi nahi.
        raise SignInExpired(
            "YouTube sign-in nahi hua hai. Ek baar signin.bat chalaiye "
            "(server/cloud par Telegram se /signin).")
    age = time.time() - float(tok.get("obtained_at") or 0)
    if tok.get("access_token") and age < float(tok.get("expires_in") or 3600) - 120:
        return tok["access_token"]

    # Token device wale tareeke se aaya ho to usi client se refresh hota
    # hai - dono client alag hain aur ek ka refresh token doosre par nahi
    # chalta.
    if tok.get("device"):
        cid, csec = device_client()
    else:
        cid, csec = cfg.youtube_client()
    try:
        fresh = sy_net.post_json(TOKEN, urllib.parse.urlencode({
            "refresh_token": tok["refresh_token"], "client_id": cid,
            "client_secret": csec, "grant_type": "refresh_token",
        }).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=60)
    except sy_net.HttpError as e:
        # TOKEN ke darwaze par 400/401 ka matlab EK HI hota hai: ye sign-in
        # ab kaam ka nahi raha. Naya sign-in chahiye.
        #
        # Pehle yahan sirf "invalid_grant" shabd dhoondha jaata tha. Google
        # us haalat mein aur bhi shabd bhejta hai (invalid_client,
        # unauthorized_client, deleted_client) - aur jab unme se koi aaya,
        # to ye jaanch chook gayi aur log mein sirf ye dikha:
        #
        #     upload nahi hua: HTTP 400: https://oauth2.googleapis.com/token
        #
        # Us ek line se ye pata hi nahi chalta ki karna kya hai. Aur us
        # raste par wo saaf sandesh bhi nahi jaata tha jo Telegram par
        # "signin.bat chala dijiye" kehta hai - yaani ruki hui video wahin
        # padi rehti aur wajah kahin likhi hi nahi jaati.
        #
        # Isliye ab shabd nahi, DARWAZA dekhte hain. Asli wajah log mein
        # likh dete hain, taaki agli baar andaaza na lagana pade.
        if e.status in (400, 401):
            log("sign-in nahi chala:", (e.body or "")[:200])
            raise SignInExpired("sign-in ab kaam nahi kar raha")
        raise
    tok.update(fresh)
    tok["obtained_at"] = time.time()
    _save(tok)
    return tok["access_token"]


# ------------------------------------------------------------- upload

DISCLAIMER = (
    "\n\n---\n"
    "इस वीडियो की आवाज़ AI से बनाई गई है। समाचार की जानकारी ऊपर दिए गए "
    "स्रोतों से ली गई है। चित्र का श्रेय वीडियो में स्क्रीन पर दिया गया है।\n"
    "The voiceover in this video is AI-generated. The reporting is sourced "
    "from the news agencies credited above; the image credit appears on screen.")


def _is_rate_limit(err):
    body = getattr(err, "body", "") or str(err)
    return ("rateLimit" in body or "too many requests" in body.lower()
            or "userRateLimit" in body or getattr(err, "status", 0) == 429)


def upload(story, video_path):
    """Video chadhao. videoId lauta do.

    Rate limit par RateLimited uthata hai - bulane wala baad mein khud
    dobara koshish karta hai. Baaki galtiyan waise ki waise upar jaati hain.
    """
    token = access_token()
    desc = (str(story.get("yt_description") or "").strip() + "\n\n"
            + str(story.get("attribution_line") or "")).strip() + DISCLAIMER
    tags = [t.strip() for t in str(story.get("tags") or "").split(",") if t.strip()]

    beat = str(story.get("beat") or "")
    title = str(story.get("yt_title") or story.get("headline_hi") or "")

    # REEL KO SHORTS BANANA
    #
    # YouTube khud pehchanta hai ki video Short hai ya nahi - 9:16 ka naap
    # aur 3 minute se kam lambai kaafi hai. Par #Shorts likh dena ab bhi
    # madad karta hai, khaas kar shuruaati ghanton mein jab uska apna
    # hisaab lag raha hota hai. Isliye shirshak ke ant mein wo lagate hain.
    #
    # Shreni bhi badalti hai: bollywood Entertainment (24) mein jaati hai,
    # News & Politics (25) mein nahi - warna wo galat darshak ke saamne
    # jaati hai aur wahan chalti nahi.
    if beat in ("bolly", "viral"):
        if "#Shorts" not in title:
            title = (title[:80].rstrip() + " #Shorts")
        desc = desc + "\n\n#Shorts"
        cat = "24" if beat == "bolly" else "25"
    else:
        cat = "25"

    meta = {
        "snippet": {
            "title": title[:95],
            "description": desc[:4900],
            "tags": tags[:20],
            "categoryId": cat,
            "defaultLanguage": "hi",
        },
        "status": {
            # Pehle unlisted. Aap dekh kar khud public karte hain - ek
            # aakhri insaani nazar, galti nikal jaye to bhi wo sarvajanik
            # nahi hui hoti.
            "privacyStatus": "unlisted",
            "selfDeclaredMadeForKids": False,
        },
    }

    size = os.path.getsize(video_path)

    # Pehla kadam: jagah maango. Yahin rate limit pakda jaata hai, aur tab
    # poori video bheji hi nahi jaati - sirf ye chhoti si request jaati hai.
    #
    # Ye SIRF EK BAAR bhejni hai. Google session ka pata header mein deta
    # hai, isliye ise seedha urllib se kholte hain (sy_net headers nahi
    # lautata). Pehle yahan do request ja rahi thi - ek jaanch ke liye aur
    # ek pate ke liye - aur har upload ka quota do guna lag raha tha. Wahi
    # galti thi jiski wajah se pehle sab atka tha.
    import urllib.error
    import urllib.request
    req = urllib.request.Request(
        UPLOAD, data=json.dumps(meta).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4",
                 "X-Upload-Content-Length": str(size)})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            session = r.headers.get("Location")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read()[:800].decode("utf-8", "replace")
        except Exception:
            pass
        if _is_rate_limit(sy_net.HttpError(e.code, UPLOAD, body)):
            raise RateLimited(body[:300] or "rate limit")
        raise sy_net.HttpError(e.code, UPLOAD, body)
    if not session:
        raise RuntimeError("upload session nahi mila")

    with open(video_path, "rb") as f:
        body = f.read()
    try:
        res = sy_net.fetch(session, data=body, method="PUT",
                           headers={"Content-Type": "video/mp4",
                                    "Content-Length": str(size)},
                           timeout=900, retries=0)
    except sy_net.HttpError as e:
        if _is_rate_limit(e):
            raise RateLimited(e.body[:300] or "rate limit")
        raise
    data = json.loads(res.decode("utf-8", "replace"))
    vid = str(data.get("id") or "")
    if not vid:
        raise RuntimeError("videoId nahi mila")
    log("upload ho gaya:", vid)
    return vid


def set_thumbnail(video_id, thumb_path):
    """Thumbnail lagao. Fail ho to sirf batao - video to chadh hi chuki hai."""
    if not thumb_path or not os.path.exists(thumb_path):
        return False
    try:
        with open(thumb_path, "rb") as f:
            body = f.read()
        sy_net.fetch(THUMB + video_id, data=body, method="POST",
                     headers={"Authorization": "Bearer " + access_token(),
                              "Content-Type": "image/jpeg"},
                     timeout=180, retries=1)
        log("thumbnail lag gaya")
        return True
    except Exception as e:
        log("thumbnail nahi laga:", e)
        return False


if __name__ == "__main__":
    cfg.ensure_dirs()
    access_token()
    print("YouTube taiyar hai.")

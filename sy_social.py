"""Bani hui video Facebook Page aur Instagram par bhi.

YE KAB CHALTA HAI
=================
Sirf YouTube par chadh jaane ke BAAD. Yaani us video par aapka ✅ pehle hi
lag chuka hota hai. Koi naya gate nahi jodha gaya - ek hi approval teeno
jagah ke liye kaafi hai, aur usi ek jagah insaan khabar dekhta hai.

DO PLATFORM, DO ALAG TAREEKE - AUR YE FARQ POORE DESIGN KI JAD HAI
==================================================================
Facebook file LETA hai. Hum mp4 seedha chadha dete hain, baat khatam.

Instagram file nahi leta. Uska apna dastavez kehta hai: "media must be
hosted on a publicly accessible server". Yaani use ek PATA chahiye, file
nahi. Isliye Instagram ke liye video pehle Google Cloud Storage par
rakhni padti hai, phir uska link Instagram ko diya jaata hai, phir wo use
utaar kar post karta hai.

Isi wajah se Instagram ka hissa teen kadam ka hai (rakho, container
banao, publish karo) aur Facebook ka ek kadam ka.

INSTAGRAM PAR SIRF REEL
=======================
Ye faisla soch kar liya gaya hai. Aapki bolly/viral wali video 9:16 hain -
wo Instagram par jaisi ki taisi baithti hain. 16:9 wali khabar wahan
kat-ti hai ya uske upar-neeche kaali patti aati hai, aur wo dekhne mein
bekaar lagti hai. Adhoora dikhne se na dikhna behtar hai.

Facebook par ye rok nahi hai - wahan dono naap chalti hain.
"""
import json
import os
import time

import sy_config as cfg
import sy_net

GRAPH = "https://graph.facebook.com/v21.0"


def log(*a):
    print("[social]", *a, flush=True)


# ----------------------------------------------------------- settings

def enabled():
    """Telegram ka switch config se upar - wahi tareeka jo Veo mein hai."""
    import sy_store as st
    override = st.kv_get("social_on")
    if override is not None:
        return bool(override)
    return cfg.num("social", "enabled", 0) == 1


def set_enabled(on):
    import sy_store as st
    st.kv_set("social_on", 1 if on else 0)


def fb_on():
    return bool(cfg.get("social", "fb_page_id")) and bool(_fb_token())


def ig_on():
    return bool(cfg.get("social", "ig_user_id")) and bool(_fb_token())


def _fb_token():
    return cfg.get("social", "fb_token")


def bucket():
    return cfg.get("social", "gcs_bucket")


REEL_BEATS = ("bolly", "viral")


# ----------------------------------------------------------- Facebook

def post_facebook(video_path, caption):
    """Page par video. (True, post_id) ya (False, wajah)."""
    page = cfg.get("social", "fb_page_id")
    token = _fb_token()
    if not page or not token:
        return False, "Facebook ka page id ya token nahi hai"
    if not os.path.exists(video_path):
        return False, "video file nahi mili"

    # Video Page ke /videos par jaati hai, /feed par nahi - /feed sirf
    # text aur link leta hai.
    url = "%s/%s/videos" % (GRAPH, page)
    try:
        raw = _multipart_post(
            url, {"access_token": token, "description": caption[:2000]},
            {"source": video_path}, timeout=900)
        data = json.loads(raw.decode("utf-8", "replace"))
    except sy_net.HttpError as e:
        return False, "Facebook ne mana kiya: %s %s" % (
            e.status, str(getattr(e, "body", ""))[:300])
    except Exception as e:
        return False, "Facebook tak baat nahi pahunchi: %s" % e
    vid = str(data.get("id") or "")
    if not vid:
        return False, "Facebook ne id nahi di: " + str(data)[:200]
    return True, vid


# ----------------------------------------------------------- Instagram

def _gcs_put(local_path, token):
    """Video GCS par rakho aur uska sarvajanik pata lauta do.

    Instagram ko file nahi, PATA chahiye - upar wali tippani dekhiye. Ye
    file kuch din baad apne aap hat jaani chahiye; uska intezam bucket ki
    apni lifecycle setting se hota hai (SOCIAL.md mein likha hai), code se
    nahi - taaki galti se kisi aur ki file na hate.
    """
    bkt = bucket()
    if not bkt:
        return "", "GCS bucket ka naam config mein nahi hai"
    name = "reels/%d_%s" % (int(time.time()), os.path.basename(local_path))
    url = ("https://storage.googleapis.com/upload/storage/v1/b/%s/o"
           "?uploadType=media&name=%s"
           % (bkt, sy_net.urllib.parse.quote(name, safe="")))
    try:
        with open(local_path, "rb") as f:
            body = f.read()
        sy_net.fetch(url, headers={"Authorization": "Bearer " + token,
                                   "Content-Type": "video/mp4"},
                     data=body, method="POST", timeout=900, retries=0)
    except sy_net.HttpError as e:
        return "", "GCS par nahi chadhi: %s %s" % (
            e.status, str(getattr(e, "body", ""))[:200])
    except Exception as e:
        return "", "GCS par nahi chadhi: %s" % e
    return ("https://storage.googleapis.com/%s/%s"
            % (bkt, sy_net.urllib.parse.quote(name, safe="/")), "")


def post_instagram(video_path, caption):
    """Reel. (True, media_id) ya (False, wajah).

    Teen kadam: GCS par rakho, container banao, publish karo. Beech mein
    Instagram video utaarta aur jaanchta hai - us par do-teen minute lag
    sakte hain, isliye poochhte rehna padta hai.
    """
    ig = cfg.get("social", "ig_user_id")
    token = _fb_token()
    if not ig or not token:
        return False, "Instagram ka user id ya token nahi hai"

    try:
        import sy_veo
        gtoken, _sa = sy_veo._token()
    except Exception as e:
        return False, "Google ka token nahi mila (GCS ke liye): %s" % e

    link, why = _gcs_put(video_path, gtoken)
    if not link:
        return False, why
    log("GCS par rakh di:", link[:90])

    # 1) Container
    try:
        raw = _form_post(
            "%s/%s/media" % (GRAPH, ig),
            {"media_type": "REELS", "video_url": link,
             "caption": caption[:2000], "access_token": token},
            timeout=180)
        cid = str(json.loads(raw.decode("utf-8", "replace")).get("id") or "")
    except sy_net.HttpError as e:
        return False, "Instagram ne container nahi banaya: %s %s" % (
            e.status, str(getattr(e, "body", ""))[:300])
    except Exception as e:
        return False, "Instagram tak baat nahi pahunchi: %s" % e
    if not cid:
        return False, "container id nahi mili"

    # 2) Taiyar hone ka intezaar
    waited = 0
    status = ""
    while waited < 360:
        time.sleep(12)
        waited += 12
        try:
            raw = sy_net.fetch(
                "%s/%s?fields=status_code,status&access_token=%s"
                % (GRAPH, cid, sy_net.urllib.parse.quote(token)),
                timeout=60, retries=0)
            d = json.loads(raw.decode("utf-8", "replace"))
        except Exception as e:
            log("haal poochhne mein gadbad:", str(e)[:80])
            continue
        status = str(d.get("status_code") or "")
        if status == "FINISHED":
            break
        if status == "ERROR":
            return False, "Instagram ne video nahi maani: " + str(
                d.get("status") or "")[:250]
    if status != "FINISHED":
        return False, "Instagram %d second mein taiyar nahi hua" % waited

    # 3) Publish
    try:
        raw = _form_post(
            "%s/%s/media_publish" % (GRAPH, ig),
            {"creation_id": cid, "access_token": token}, timeout=120)
        mid = str(json.loads(raw.decode("utf-8", "replace")).get("id") or "")
    except sy_net.HttpError as e:
        return False, "Instagram ne publish nahi kiya: %s %s" % (
            e.status, str(getattr(e, "body", ""))[:300])
    except Exception as e:
        return False, "Instagram publish mein gadbad: %s" % e
    return (True, mid) if mid else (False, "media id nahi mili")


# ----------------------------------------------------------- caption

def caption_for(story, youtube_id=""):
    """Wahi baat, us jagah ke hisaab se.

    YouTube ka link JAAN-BOOJHKAR sirf Facebook par jaata hai. Instagram
    caption mein link chalta hi nahi (wo dabaya nahi ja sakta), aur wahan
    link likhna sirf jagah kharab karta hai.
    """
    head = str(story.get("headline_hi") or "").strip()
    tags = [t.strip() for t in
            str(story.get("tags") or "").split(",") if t.strip()][:6]
    bits = [head, ""]
    if youtube_id:
        bits.append("Poori khabar: https://youtu.be/" + youtube_id)
        bits.append("")
    bits.append("सत्ययात्रा न्यूज")
    if tags:
        bits.append(" ".join("#" + t.replace(" ", "") for t in tags))
    return "\n".join(bits)


def ig_caption_for(story):
    return caption_for(story, "")


# ----------------------------------------------------------- bahar ka rasta

def share(story, video_path, youtube_id=""):
    """YouTube ke baad. Kabhi throw nahi karta - lauta ta hai kya-kya hua."""
    out = []
    if not enabled():
        return out
    beat = str(story.get("beat") or "")

    if fb_on():
        ok, res = post_facebook(video_path, caption_for(story, youtube_id))
        out.append(("Facebook", ok, res))
        log("Facebook:", "ho gaya " + res if ok else "nahi - " + res)

    # Instagram par sirf 9:16. Wajah upar likhi hai.
    if ig_on():
        if beat in REEL_BEATS:
            ok, res = post_instagram(video_path, ig_caption_for(story))
            out.append(("Instagram", ok, res))
            log("Instagram:", "ho gaya " + res if ok else "nahi - " + res)
        else:
            log("Instagram: chhoda - ye 16:9 hai, Reel nahi")
    return out


def _form_post(url, fields, timeout=120):
    """Graph API form-encoded maangta hai, JSON nahi.

    sy_net.fetch ko dict do to wo use JSON bana deta hai - aur Graph us par
    chup-chaap galat bartav karta hai. Isliye yahan body khud banate hain.
    """
    body = sy_net.urllib.parse.urlencode(
        dict((k, str(v)) for k, v in fields.items())).encode("utf-8")
    return sy_net.fetch(
        url, headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=body, method="POST", timeout=timeout, retries=0)


def _multipart_post(url, fields, files, timeout=600):
    """Chhota multipart - wahi tareeka jo sy_telegram mein hai."""
    import uuid
    boundary = "----satyayatra" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                % (boundary, k, v)).encode("utf-8")
    for k, path in files.items():
        name = os.path.basename(path)
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                "filename=\"%s\"\r\nContent-Type: video/mp4\r\n\r\n"
                % (boundary, k, name)).encode("utf-8")
        with open(path, "rb") as f:
            out += f.read()
        out += b"\r\n"
    out += ("--%s--\r\n" % boundary).encode("utf-8")
    return sy_net.fetch(
        url, headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
        data=bytes(out), method="POST", timeout=timeout, retries=0)

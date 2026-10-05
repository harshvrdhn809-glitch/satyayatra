"""Telegram - video bhejna aur approval ka jawab lena.

Yahan koi webhook nahi hai. Program khud Telegram se poochhta rehta hai
(getUpdates). Isi wajah se poora system aapke computer par chal sakta hai:
bahar se koi request andar aane ki zaroorat nahi, na koi public URL chahiye,
na kisi tunnel ki.
"""
import json
import mimetypes
import os
import time
import urllib.parse
import uuid

import sy_config as cfg
import sy_net
import sy_store as st


def log(*a):
    print("[telegram]", *a, flush=True)


def _api(method):
    return "https://api.telegram.org/bot%s/%s" % (
        cfg.need("telegram", "bot_token"), method)


def _chat():
    return cfg.need("telegram", "chat_id")


def _multipart(fields, files):
    """multipart/form-data haath se banate hain - koi library nahi chahiye."""
    boundary = "----satyayatra" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                % (boundary, k, v)).encode("utf-8")
    for k, path in files.items():
        name = os.path.basename(path)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                % (boundary, k, name, ctype)).encode("utf-8")
        with open(path, "rb") as f:
            out += f.read()
        out += b"\r\n"
    out += ("--%s--\r\n" % boundary).encode("utf-8")
    return bytes(out), "multipart/form-data; boundary=" + boundary


def _post(method, fields, files=None, timeout=300):
    if files:
        body, ctype = _multipart(fields, files)
        raw = sy_net.fetch(_api(method), data=body, method="POST",
                           headers={"Content-Type": ctype}, timeout=timeout,
                           retries=1)
    else:
        # JSON body mein reply_markup ek object hona chahiye, string nahi.
        # multipart mein ulta hai - wahan wo JSON string hi chalti hai.
        # Isi farq ki wajah se button hatane par 400 aa raha tha, jabki
        # wahi keyboard bhejte waqt theek chal jaata tha.
        body = dict(fields)
        rm = body.get("reply_markup")
        if isinstance(rm, str):
            try:
                body["reply_markup"] = json.loads(rm)
            except Exception:
                body.pop("reply_markup")
        raw = sy_net.fetch(_api(method), data=body, method="POST",
                           timeout=timeout, retries=1)
    data = json.loads(raw.decode("utf-8", "replace"))
    if not data.get("ok"):
        raise RuntimeError("telegram: " + str(data.get("description")))
    return data.get("result") or {}


def send_message(text):
    return _post("sendMessage", {"chat_id": _chat(), "text": text[:4000],
                                 "parse_mode": "HTML"}, timeout=60)


def send_choices(items, note=""):
    """Vishayon ki suchi, har ek par ek button. message_id lauta ta hai.

    Ye publish wale gate ka jodidaar hai, par doosre sire par. Publish wala
    gate poochhta hai "ye chal sakti hai?" - ye poochhta hai "banayein kis
    par?". Beech ka saara kharch (lekh dhoondhna, sampadak ka call, aawaaz,
    render) tabhi shuru hota hai jab aap ek button daba dete hain.
    """
    lines = ["<b>Kis par video banayein?</b>", ""]
    rows = []
    for i, it in enumerate(items):
        tag = str(it.get("tag") or "")
        lines.append("<b>%d.</b> %s%s" % (i + 1, _esc(it.get("label") or ""),
                                          ("  <i>%s</i>" % _esc(tag)) if tag else ""))
        rows.append([{"text": "%d. %s" % (i + 1, str(it.get("button") or "")[:28]),
                      "callback_data": "pk:%s:%d" % (it.get("slate") or "0", i)}])
    if note:
        lines += ["", _esc(note)]
    rows.append([{"text": "Koi nahi - aage badho",
                  "callback_data": "sk:%s:0" % (items[0].get("slate") or "0")}])

    res = _post("sendMessage", {
        "chat_id": _chat(), "text": "\n".join(lines)[:4000],
        "parse_mode": "HTML",
        "reply_markup": json.dumps({"inline_keyboard": rows}),
    }, timeout=60)
    return int(res.get("message_id") or 0)


def send_audio(path, caption=""):
    """Sirf aawaaz bhejna - raftaar chunne ke liye (awaaz.bat)."""
    return _post("sendAudio", {"chat_id": _chat(), "caption": caption[:900],
                               "parse_mode": "HTML"},
                 files={"audio": path}, timeout=180)


def send_photo(path, caption=""):
    """Sirf ek tasveer - koi button nahi, koi approval nahi. Jhalak ke liye."""
    return _post("sendPhoto", {"chat_id": _chat(), "caption": caption[:900],
                               "parse_mode": "HTML"},
                 files={"photo": path}, timeout=120)


def send_video_file(path, caption=""):
    """Sirf ek video - koi button nahi. Test/jhalak ke liye, approval ke liye
    send_video_for_approval istemal kijiye."""
    return _post("sendVideo", {"chat_id": _chat(), "caption": caption[:900],
                               "parse_mode": "HTML"},
                 files={"video": path}, timeout=300)


def send_video_for_approval(story, video_path, thumb_path=""):
    """Video bheji jaati hai, uske neeche do button. message_id lauta ta hai."""
    cap = "\n".join([
        "<b>Bulletin taiyar hai</b>", "",
        "<b>" + _esc(story.get("headline_hi") or "") + "</b>", "",
        _esc(story.get("attribution_line") or ""),
        _esc(story.get("image_credit") or ""),
        "%ds  |  1920x1080  |  aapke PC par bani" % int(story.get("seconds") or 0),
        "", "YouTube title: " + _esc(story.get("yt_title") or ""),
    ])
    # Shot list bhi saath bhejte hain. Approve karne wale ko sirf ye nahi
    # dekhna hota ki khabar sahi hai - ye bhi dekhna hota hai ki kis baat
    # par kya dikhaya gaya. "×" ka matlab us baat par apna drishya nahi
    # mila aur pichhla drishya hi aage chala.
    # Kitne drishya asli hain - ye sabse pehle dikhna chahiye. Yojana aur
    # kaam ki baat par sakht rok nahi hai, isliye wahan ye line hi aapka
    # faisla lene ka aadhaar hai.
    vline = str(story.get("visual_line") or "").strip()
    if vline:
        cap += "\n" + _esc(vline)

    shots = str(story.get("shot_summary") or "").strip()
    if shots and len(cap) + len(shots) < 800:
        cap += "\n\n<b>Drishya</b>\n<code>" + _esc(shots) + "</code>"

    # TEEN TITLE - aur ye jaan-boojhkar button nahi hain.
    #
    # Button daalne par har video par do ki jagah paanch button ho jaate,
    # aur asli faisla (jaana hai ya nahi) unme dab jaata. Title badalna
    # kabhi-kabhi ka kaam hai, isliye wo ek likha hua aadesh hai. Jo kuch
    # na kare uska pehla title waise hi chala jayega.
    opts = st.kv_get("titles_" + str(story.get("story_id") or "")) or []
    if isinstance(opts, list) and len(opts) > 1 and len(cap) < 780:
        cap += "\n\n<b>Title</b>"
        for n, t in enumerate(opts[:3], 1):
            mark = " ←" if n == 1 else ""
            cap += "\n%d. %s%s" % (n, _esc(t)[:70], mark)
        cap += "\nBadalna ho to <code>/title 2</code> likhiye"

    keyboard = {"inline_keyboard": [[
        {"text": "✅ Publish karein", "callback_data": "ok:" + story["story_id"]},
        {"text": "❌ Reject", "callback_data": "no:" + story["story_id"]},
    ]]}
    res = _post("sendVideo", {
        "chat_id": _chat(), "caption": cap[:1024], "parse_mode": "HTML",
        "supports_streaming": "true",
        "reply_markup": json.dumps(keyboard),
    }, files={"video": video_path})

    if thumb_path and os.path.exists(thumb_path):
        try:
            _post("sendPhoto", {
                "chat_id": _chat(),
                "caption": "Thumbnail — " + _esc(story.get("headline_hi") or "")[:200],
                "parse_mode": "HTML",
            }, files={"photo": thumb_path}, timeout=120)
        except Exception as e:
            # Thumbnail na jaane se approval nahi rukna chahiye.
            log("thumbnail nahi gayi:", e)
    return int(res.get("message_id") or 0)


def _esc(s):
    return (str(s or "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _warn_once(key, text):
    """Din mein ek hi baar - har 20 minute ki run par wahi sandesh nahi."""
    day = time.strftime("%Y-%m-%d")
    if st.kv_get(key) == day:
        return
    st.kv_set(key, day)
    try:
        send_message(text)
    except Exception:
        pass


def _report_webhook():
    """Koi aur is bot par webhook laga deta hai to button ka jawab USKE paas
    jaata hai, hamare paas nahi - aur ye chup-chaap hota hai. Oct 2026:
    "Telegram se approve button kaam nahi kar rahi". Isliye hatane se PEHLE
    dekh lete hain ki kisi ne laga to nahi rakha tha, aur laga tha to batate
    hain (sirf host, poora pata nahi - usme kisi aur ki chaabi ho sakti hai)."""
    try:
        raw = sy_net.fetch(_api("getWebhookInfo"), timeout=30, retries=1)
        info = (json.loads(raw.decode("utf-8", "replace")).get("result") or {})
    except Exception as e:
        log("webhook ki jaankari nahi mili:", e)
        return
    url = str(info.get("url") or "")
    log("bot ka haal: webhook=%s, bina padhe %s"
        % (sy_net.host(url) or "koi nahi", info.get("pending_update_count")))
    if url:
        _warn_once("tg_webhook_warned",
                   "<b>Dhyaan: is bot par kisi aur ka webhook laga tha</b> ("
                   + _esc(sy_net.host(url)) + ")\n\n"
                   "Uske rehte aapke button ka jawab wahan chala jaata hai, "
                   "yahan nahi pahunchta. Maine hata diya hai, par wo program "
                   "(jaise purana n8n) chalu raha to phir laga dega - use band "
                   "kar dijiye.")


def ensure_polling():
    """Bot par laga hua webhook hata do.

    n8n ne is bot par apna webhook lagaya tha. Jab tak wo laga hai, Telegram
    getUpdates par 409 deta hai - "ek hi bot do jagah se nahi sun sakta".
    Purane, bina padhe update bhi gira dete hain: wo n8n ke zamane ke hain
    aur unpar ab koi kaam nahi karna.
    """
    # CLOUD PAR BINA PADHE UPDATE KABHI NAHI GIRANE.
    #
    # Laptop par ye program din mein ek-aadh baar chalu hota tha, isliye
    # purane update girana theek tha. Cloud par har run (~20 minute) ek
    # nayi shuruaat hai - aur do run ke beech dabaya gaya har button (video
    # ka approval bhi) yahin mit jaata tha. Jo padh liya gaya hai wo
    # database ke tg_offset se waise bhi dobara nahi aata.
    drop = "false" if cfg.CLOUD else "true"
    _report_webhook()
    try:
        _post("deleteWebhook", {"drop_pending_updates": drop}, timeout=30)
        log("webhook hataya (purane update %s)"
            % ("rakhe" if cfg.CLOUD else "giraye"))
        return True
    except Exception as e:
        log("webhook nahi hata:", e)
        return False


# Internet gayab hone par chup rehne ka intezaam.
#
# Ek DNS ki dikkat par log mein har 20 second par chaar laal lines aati thi.
# Aadhe ghante mein screen bhar jaati thi aur us shor mein asli galti dikhti
# hi nahi. Ab: jaate waqt ek line, wapas aate waqt ek line, aur beech mein
# koshish bhi minute mein ek baar - us haalat mein 20 second par koshish
# karne se kuch milta nahi hai.
_offline = False
_last_try = 0.0
OFFLINE_GAP = 60.0


def offline():
    return _offline


def _mark(e):
    """True lauta ta hai agar ye internet na hone wali galti hai."""
    global _offline
    if not sy_net.is_offline_error(e):
        return False
    if not _offline:
        log("internet nahi mil raha (DNS jawab nahi de raha). "
            "Chup-chaap koshish karte rahenge - kuch karna nahi hai.")
        _offline = True
    return True


def _clear():
    global _offline
    if _offline:
        log("internet wapas aa gaya")
        _offline = False


# Type kiye hue aadesh yahan jama hote hain. poll_decisions() inhe bharta
# hai, take_commands() inhe uthata hai. Ek hi getUpdates dono laata hai.
_cmds = []
_notes = []     # (saada sandesh, kis sandesh ka reply) - sy_feedback ke liye
_docs = []      # (file_id, file_name) - aapki bheji .db file (purana hisaab)


def take_commands():
    """Jo aadesh aaye the wo lauta kar khaali kar deta hai.

    [(aadesh, baaki_baat)] - jaise ("/khabar", "BRICS shikhar sammelan").
    Ek baar padha, phir gaya - warna wahi /update baar-baar chalta rehta.
    """
    global _cmds
    out = _cmds
    _cmds = []
    return out


def take_notes():
    """Aapke saade (bina '/') sandesh - ek baar padhe, phir gaye."""
    global _notes
    out = _notes
    _notes = []
    return out


def take_documents():
    """Aapki bheji hui .db file(en) - ek baar padhi, phir gayi."""
    global _docs
    out = _docs
    _docs = []
    return out


def download(file_id, dest):
    """Telegram par aayi file dest par utaar do. Bot 20 MB tak utaar sakta hai."""
    info = sy_net.get_json(_api("getFile") + "?file_id="
                           + urllib.parse.quote(file_id), timeout=60)
    fp = str((info.get("result") or {}).get("file_path") or "")
    if not fp:
        raise RuntimeError("Telegram ne file ka pata nahi diya")
    raw = sy_net.fetch("https://api.telegram.org/file/bot%s/%s"
                       % (cfg.need("telegram", "bot_token"), fp), timeout=120)
    with open(dest, "wb") as f:
        f.write(raw)
    return dest


def poll_decisions():
    """Naye button-press uthao. [(story_id, 'ok'|'no', callback_id)] lauta ta hai.

    offset database mein rehta hai, isliye program band karke dobara khola
    jaye to bhi wahi jawab do baar nahi padha jaata.
    """
    global _last_try
    # Internet nahi hai to minute mein ek hi baar tatolo.
    if _offline and time.time() - _last_try < OFFLINE_GAP:
        return []
    _last_try = time.time()

    offset = st.kv_get("tg_offset", 0)
    t0 = time.time()
    try:
        # callback_query = button dabna. message = aapka type kiya hua
        # aadesh (/update wagairah). Dono ek hi getUpdates se aate hain -
        # do alag call karna yahan chalta hi nahi, kyunki offset ek hi hai
        # aur doosri call pehli ke update nigal jaati.
        raw = sy_net.fetch(
            _api("getUpdates")
            + "?timeout=0&allowed_updates=%5B%22callback_query%22%2C%22message%22%5D"
            + ("&offset=%d" % offset if offset else ""),
            timeout=40, retries=1)
        data = json.loads(raw.decode("utf-8", "replace"))
        # Telegram turant jawab deta hai. Der lage to wo jaanne layak hai -
        # warna program chup dikhta hai aur lagta hai atak gaya.
        if time.time() - t0 > 5:
            log("Telegram ne %.0f second liye" % (time.time() - t0))
    except sy_net.HttpError as e:
        _clear()
        if e.status == 409:
            # Koi aur is bot ko sun raha hai - ya to webhook, ya koi DOOSRA
            # program usi bot se getUpdates kar raha hai (laptop wala
            # SatyaYatra). Doosre haal mein button usko milta hai, hume nahi.
            body = str(e.body or "")
            log("getUpdates 409:", body[:160])
            if "other getUpdates" in body:
                _warn_once("tg_conflict_warned",
                           "<b>Dhyaan: koi aur program isi bot ko padh raha hai</b>"
                           "\n\nAapke button usi ko mil rahe hain, cloud ko "
                           "nahi. Laptop par SatyaYatra chal raha ho to band "
                           "kar dijiye (window, Task Scheduler dono).")
            ensure_polling()
        else:
            log("getUpdates:", e)
        return []
    except Exception as e:
        if not _mark(e):
            log("getUpdates:", e)
        return []
    _clear()
    if not data.get("ok"):
        return []

    out = []
    last = offset
    for u in (data.get("result") or []):
        last = max(last, int(u.get("update_id") or 0) + 1)

        # Type kiya hua aadesh. Ye SIRF aapki apni chat se maana jaata hai.
        # Bot ka naam kisi ko bhi mil sakta hai aur koi bhi use sandesh
        # bhej sakta hai - agar chat id na jaanchein to anjaan aadmi
        # /update daba kar server par code chala sakta hai.
        msg = u.get("message")
        if msg:
            txt = str(msg.get("text") or "").strip()
            who = str((msg.get("chat") or {}).get("id") or "")
            doc = msg.get("document") or {}
            if doc and who == str(_chat()):
                name = str(doc.get("file_name") or "")
                if name.lower().endswith(".db") and doc.get("file_id"):
                    _docs.append((str(doc["file_id"]), name))
                continue
            if txt.startswith("/") and who == str(_chat()):
                # Pehla shabd aadesh, baaki poori baat - "/khabar BRICS
                # shikhar sammelan" mein vishay hi asli cheez hai.
                head, _, rest = txt.partition(" ")
                _cmds.append((head.split("@")[0].lower(), rest.strip()))
            elif txt and who == str(_chat()):
                # Saada likha hua sandesh - reject ki wajah apne shabdon
                # mein (sy_feedback). Pehle aise sandesh chup-chaap gir jaate
                # the.
                rt = int(((msg.get("reply_to_message") or {}).get("message_id")) or 0)
                _notes.append((txt, rt))
            continue

        cq = u.get("callback_query")
        if not cq:
            continue
        payload = str(cq.get("data") or "")
        if ":" not in payload:
            continue
        verdict, story_id = payload.split(":", 1)
        # ok/no  -> bani hui video par faisla
        # pk/sk  -> banane se PEHLE vishay ka chunav (story_id = "slate:index")
        # fb     -> reject ki wajah ka button (story_id = "code|story_id")
        # lk/lx/la/lr -> lambi video (sy_long): mudda chuna / aaj nahi /
        #           jhalak par approve / reject
        if verdict in ("ok", "no", "pk", "sk", "fb", "lk", "lx", "la", "lr"):
            out.append((story_id, verdict, str(cq.get("id") or ""),
                        cq.get("message") or {}))
    if last != offset:
        st.kv_set("tg_offset", last)
    return out


def acknowledge(callback_id, message, text):
    """Button dabne par turant jawab, aur button hata dena.

    Button hatana zaroori hai - warna wahi video dobara approve ki ja sakti
    hai aur do baar upload chali jaayegi.
    """
    # Telegram ka callback id lagbhag ek minute mein bekaar ho jaata hai.
    # Der ho gayi to ye 400 deta hai - par wo nakaami nahi hai: faisla
    # pehle hi darj ho chuka hota hai. Isliye ise chup-chaap chhod dete
    # hain, warna har approve par ek daraane wali laal line dikhti hai.
    try:
        _post("answerCallbackQuery",
              {"callback_query_id": callback_id, "text": text[:190]}, timeout=30)
    except sy_net.HttpError as e:
        if e.status != 400:
            log("answerCallback:", e)
    except Exception as e:
        log("answerCallback:", e)
    try:
        mid = int((message or {}).get("message_id") or 0)
        if mid:
            _post("editMessageReplyMarkup",
                  {"chat_id": _chat(), "message_id": mid,
                   "reply_markup": json.dumps({"inline_keyboard": []})},
                  timeout=30)
    except sy_net.HttpError as e:
        # "message is not modified" par Telegram 400 deta hai, aur wo tab
        # aata hai jab button PEHLE HI hat chuke hon - yaani do baar dabaya
        # gaya. Wo nakaami nahi hai, kaam ho chuka hota hai.
        #
        # Ye pehli raat ke log mein laal lines bhar raha tha aur dekhne mein
        # lagta tha ki kuch toota hua hai, jabki tootha kuch nahi tha.
        if e.status != 400:
            log("button nahi hata:", e)
    except Exception as e:
        log("button nahi hata:", e)

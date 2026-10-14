"""AI (Gemini ya Claude) se baat karne wala ek hi darwaza.

Sampadak, art director aur yojana - teenon isi se guzarte hain, isliye
model ka naam, timeout aur JSON nikalne ka tareeka ek jagah rehta hai.
"""
import base64
import json
import os
import re

import sy_config as cfg
import sy_net

URL = "https://api.anthropic.com/v1/messages"

# Tasveer ki pehli chand byte se uska asli roop - naam par bharosa nahi,
# jaise sy_media.is_raster() karta hai. Claude ko bhi wahi sach bhejna hai
# jo file mein hai, naam mein jo likha hai wo nahi.
_IMG_SIGS = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF8", "image/gif"),
)


def _image_mime(path):
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except Exception:
        return ""
    for sig, mime in _IMG_SIGS:
        if head.startswith(sig):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return ""


def _raise_with_body(e):
    """HTTP 4xx/5xx galti ka asli jawab (Claude ne jo wajah bataayi) saamne
    laao - taaki log mein sirf "HTTP 400: https://api.anthropic.com/..."
    na chhape, balki Anthropic ne khud jo kaha (galat model, prompt bahut
    lamba, JSON bigda hua, waghera) bhi dikhe.

    PEHLE YE NAHI THA
    =================
    sy_net.HttpError apne andar poora jawab (e.body) sambhal kar rakhta
    hai, par jab bhi koi upar wala code sirf "log(..., e)" karta tha to
    Python HttpError.__str__ chalata hai jo bas "HTTP %s: %s" % (status,
    url) deta hai - wajah kabhi screen par aati hi nahi thi. Isliye
    "khabar mein gadbad: HTTP 400: https://api.anthropic.com/v1/messages"
    jaisi lines dikhti thin jinse asli gadbad pata hi nahi chalti thi.

    Ab: agar ye sy_net.HttpError hai to uske body ka pehla hissa jodkar
    ek naya Exception banate hain, taaki jahan bhi bulaane wala sirf
    str(e) chhaapta ho, wahan bhi asli wajah dikhe.
    """
    if isinstance(e, sy_net.HttpError):
        body = (e.body or "").strip()
        if body:
            raise Exception("HTTP %s: %s | %s" % (e.status, e.url, body[:400])) from e
    raise e


def _claude_ask(system, user, max_tokens=5000, temperature=0.2, timeout=240):
    """Claude ko poochho, uska text lauta do."""
    key = cfg.need("anthropic", "api_key")
    model = cfg.get("anthropic", "model") or "claude-sonnet-4-6"
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    try:
        data = sy_net.post_json(
            URL, payload,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=timeout, retries=1)
    except Exception as e:
        _raise_with_body(e)
    if data.get("stop_reason") == "max_tokens":
        log("CHETAVNI: Claude ka jawab max_tokens par kata")

    out = []
    for part in (data.get("content") or []):
        if isinstance(part, dict) and part.get("type") == "text":
            out.append(part.get("text") or "")
    return "".join(out)


def _extract_json(text):
    if not text:
        return None
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip())
    a = text.find("{")
    b = text.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        return json.loads(text[a:b + 1])
    except Exception:
        return None


def ask_json(system, user, max_tokens=5000, temperature=0.2, timeout=240):
    """Wahi, par jawab JSON maan kar. Na mile to None.

    Model kabhi-kabhi JSON ke aage-peeche ek line likh deta hai ya use
    markdown fence mein daal deta hai. Isliye seedha json.loads nahi karte
    - pehle bahar ka kachra hata dete hain. None lautne par bulane wala
    chup-chaap ruk jaata hai; adhoore jawab par kaam aage badhana galat hai.
    """
    text = ask(system, user, max_tokens=max_tokens, temperature=temperature,
               timeout=timeout, want_json=True)
    return _extract_json(text)


def _claude_vision_json(system, user, image_path, max_tokens=800, temperature=0.0):
    """Claude ko ek tasveer DIKHAKAR poochho - jawab JSON maan kar.

    Ab tak sampadak/art-director/yojana teeno sirf TEXT dekhte the - koi
    tasveer khud dekhkar faisla nahi karta tha, sirf uska naam/keyword
    milaan hota tha. Photo/footage chunne ke liye ye ek alag darwaza hai
    jo tasveer ki asli sharton (file ke pehle byte se pehchaani gayi -
    naam se dhoka nahi khaate) ke saath vision-samarth model ko bhejta hai.

    Tasveer padhi na jaaye, ya jawab na aaye, ya JSON na bane - to None.
    Bulane wala isse "pata nahi, maan lo theek hai" jaisa le - is jaanch
    ki wajah se kabhi koi pipeline rukna nahi chahiye.
    """
    mime = _image_mime(image_path)
    if not mime:
        return None
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return None

    key = cfg.need("anthropic", "api_key")
    # Vision jaanch baar-baar, kai tasveeron par hoti hai - isliye ek
    # sasta/tez model alag se chuna ja sakta hai (config.ini mein
    # [anthropic] vision_model=...). Kuch na diya ho to wahi mukhya model.
    model = (cfg.get("anthropic", "vision_model")
             or cfg.get("anthropic", "model") or "claude-sonnet-4-6")
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": mime, "data": b64}},
                {"type": "text", "text": user},
            ],
        }],
    }
    try:
        data = sy_net.post_json(
            URL, payload,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=90, retries=1)
    except Exception as e:
        try:
            _raise_with_body(e)
        except Exception as e2:
            log("vision:", e2)
        return None

    out = []
    for part in (data.get("content") or []):
        if isinstance(part, dict) and part.get("type") == "text":
            out.append(part.get("text") or "")
    return _extract_json("".join(out))


def log(*a):
    print("[ai]", *a, flush=True)


# ================================================================ GEMINI
#
# Oct 2026, Harshvardhan: "mere paas Gemini pro hai - jo kaam abhi
# Anthropic API se ho raha, wo Gemini se ho". Isliye ab kaun sa AI chalega
# ye config.ini ke [ai] provider se tay hota hai:
#
#   provider = gemini     -> Gemini (neeche do raste, jo mile)
#   provider = anthropic  -> purana Claude wala rasta, waisa ka waisa
#
# Gemini tak do raste hain:
#   1. [gemini] api_key bhara ho (Google AI Studio ki chaabi) -> seedha
#      generativelanguage.googleapis.com.
#   2. Na ho, par Google Cloud ka service account ho (wahi jo Veo ke liye
#      laga hai) -> Vertex AI. Kharch Google Cloud ke credit se.
#
# DHYAAN: Gemini app ki "Pro" subscription (Google One) aur API alag cheez
# hain - subscription se API ka kota nahi milta. API ke liye AI Studio ki
# chaabi ya Google Cloud ka billing chahiye.
#
# [ai] fallback = 1 ho aur Claude ki chaabi bhari ho, to Gemini ke fail hone
# (galti/rok) par wahi sawal Claude se - video na ruke. 0 karne par sirf
# Gemini.

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent"
GEMINI_LIST = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
VERTEX_URL = ("https://%s/v1/projects/%s/locations/%s/publishers/google/"
              "models/%s:generateContent")

# Khabar mein maut, apraadh, hinsa ki baat aam hai - Gemini ka apna filter
# use rok na de. Ye filter band karna hai, sach ki jaanch nahi - wo hamare
# apne niyam (EDITOR_SYSTEM) karte hain.
_SAFETY = [{"category": c, "threshold": "BLOCK_NONE"} for c in (
    "HARM_CATEGORY_HARASSMENT", "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT", "HARM_CATEGORY_DANGEROUS_CONTENT")]


def provider():
    return (cfg.get("ai", "provider") or "anthropic").strip().lower()


def _fallback_ok():
    return cfg.num("ai", "fallback", 1) == 1 and bool(cfg.get("anthropic", "api_key"))


# Google purane model band karta rehta hai (Oct 2026: "gemini-2.5-pro is
# no longer available" - aur us din ek bhi khabar nahi bani). Isliye
# default "-latest" naam hain, jo hamesha us waqt ke sabse naye Pro/Flash
# par jaate hain. Aur config mein likha naam band ho chuka ho (404), to
# Google se chalu modelon ki suchi lekar sabse naya Pro/Flash khud chun
# lete hain (_replacement).
_swapped = {}


def _gemini_model(vision=False):
    if vision:
        m = (cfg.get("gemini", "vision_model") or cfg.get("gemini", "model")
             or "gemini-flash-latest")
    else:
        m = cfg.get("gemini", "model") or "gemini-pro-latest"
    return _swapped.get(m, m)


def _version(name):
    v = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(v.group(1)) if v else 0.0


def _replacement(dead, key):
    """Band ho chuke model ki jagah sabse naya chalu Pro (ya Flash)."""
    kind = "flash" if "flash" in dead else "pro"
    data = sy_net.get_json(GEMINI_LIST, headers={"x-goog-api-key": key},
                           timeout=30, retries=1)
    best = None
    for m in data.get("models") or []:
        name = str(m.get("name") or "").replace("models/", "")
        if "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        if not name.startswith("gemini-") or kind not in name:
            continue
        if any(x in name for x in ("image", "tts", "audio", "live", "lite",
                                    "embedding", "thinking", "robotics", "computer")):
            continue
        # sabse naya version; barabar ho to preview/experimental se pehle stable
        rank = (_version(name), "preview" not in name and "exp" not in name)
        if best is None or rank > best[0]:
            best = (rank, name)
    return best[1] if best else ""


def _thinking(model):
    """Gemini 2.5 pehle 'sochta' hai, aur wo soch bhi output ki ginti mein
    aati hai. Pro par soch band nahi hoti - use seemit rakhte hain; Flash
    par band (sasta, tez). Model naya ho aur ye na samjhe to None - tab
    wo apne hisaab se sochta hai, isliye _gemini_call output ki jagah
    badha deta hai."""
    m = model.lower()
    if "2.5-pro" in m:
        return 2048
    if "2.5-flash" in m:
        return 0
    return None


def _gemini_call(model, system, parts, max_tokens, temperature, timeout, want_json):
    gen = {"temperature": temperature, "maxOutputTokens": int(max_tokens)}
    budget = _thinking(model)
    if budget is not None:
        gen["thinkingConfig"] = {"thinkingBudget": budget}
        gen["maxOutputTokens"] = int(max_tokens) + budget
    else:
        # naya/anjaan model: soch bhi isi ginti mein aati hai - jagah do,
        # warna jawab beech mein kat jaata
        gen["maxOutputTokens"] = int(max_tokens) + 8192
    if want_json:
        gen["responseMimeType"] = "application/json"
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": gen, "safetySettings": _SAFETY}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    key = cfg.get("gemini", "api_key")
    if key:
        url, headers = GEMINI_URL % model, {"x-goog-api-key": key}
    else:
        url, headers = _vertex_target(model)
    try:
        try:
            data = sy_net.post_json(url, body, headers=headers,
                                    timeout=timeout, retries=1)
        except sy_net.HttpError as e:
            # model band ho gaya / naam badal gaya -> naya chunkar ek baar aur
            if not (key and e.status == 404):
                raise
            new = _replacement(model, key)
            if not new or new == model:
                raise
            log("model %s band hai - ab %s (config.ini [gemini] mein naam "
                "badal dijiye)" % (model, new))
            for k, v in list(_swapped.items()) + [(model, model)]:
                if v == model:
                    _swapped[k] = new
            data = sy_net.post_json(GEMINI_URL % new, body, headers=headers,
                                    timeout=timeout, retries=1)
    except Exception as e:
        _raise_with_body(e)

    cands = data.get("candidates") or []
    if not cands:
        why = (data.get("promptFeedback") or {}).get("blockReason") or "khaali jawab"
        raise Exception("Gemini ne jawab nahi diya: %s" % why)
    c = cands[0]
    reason = str(c.get("finishReason") or "")
    if reason == "MAX_TOKENS":
        log("CHETAVNI: Gemini ka jawab maxOutputTokens par kata")
    text = "".join(p.get("text") or "" for p in ((c.get("content") or {}).get("parts") or [])
                   if isinstance(p, dict) and not p.get("thought"))
    if not text and reason not in ("STOP", "MAX_TOKENS"):
        raise Exception("Gemini ne roka: %s" % reason)
    return text


def _vertex_target(model):
    """AI Studio ki chaabi na ho to Google Cloud (Vertex) se - Veo wala
    service account. (url, headers)"""
    import vertex
    path = cfg.get("veo", "service_account") or ""
    if not path:
        path = os.path.join(cfg.HERE, "satyayatra-sa.json")
    if not os.path.exists(path):
        raise cfg.ConfigError(
            "Gemini ke liye na [gemini] api_key hai na Google Cloud ka "
            "service account (satyayatra-sa.json / GCP_SA_JSON).")
    with open(path, encoding="utf-8") as f:
        sa = json.load(f)
    project = cfg.get("veo", "project") or sa.get("project_id")
    loc = cfg.get("gemini", "location") or "global"
    host = ("aiplatform.googleapis.com" if loc == "global"
            else "%s-aiplatform.googleapis.com" % loc)
    return (VERTEX_URL % (host, project, loc, model),
            {"Authorization": "Bearer " + vertex._access_token(sa)})


def ask(system, user, max_tokens=5000, temperature=0.2, timeout=240, want_json=False):
    """AI ko poochho, uska text lauta do. Kaun sa AI - [ai] provider."""
    if provider() == "gemini":
        try:
            return _gemini_call(_gemini_model(), system, [{"text": user}],
                                max_tokens, temperature, timeout, want_json)
        except Exception as e:
            if not _fallback_ok():
                raise
            log("Gemini nahi chala, Claude se:", str(e)[:200])
    return _claude_ask(system, user, max_tokens=max_tokens,
                       temperature=temperature, timeout=timeout)


def ask_vision_json(system, user, image_path, max_tokens=800, temperature=0.0):
    """Tasveer DIKHAKAR poochho - jawab JSON. Na bane to None (kabhi
    pipeline nahi rokta) - _claude_vision_json ka doc dekhiye."""
    if provider() == "gemini":
        mime = _image_mime(image_path)
        if not mime:
            return None
        try:
            with open(image_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            text = _gemini_call(
                _gemini_model(vision=True), system,
                [{"inlineData": {"mimeType": mime, "data": b64}}, {"text": user}],
                max_tokens, temperature, 90, True)
            return _extract_json(text)
        except Exception as e:
            log("vision (Gemini):", str(e)[:200])
            if not _fallback_ok():
                return None
    return _claude_vision_json(system, user, image_path,
                               max_tokens=max_tokens, temperature=temperature)

"""Claude se baat karne wala ek hi darwaza.

Sampadak, art director aur yojana - teenon isi se guzarte hain, isliye
model ka naam, timeout aur JSON nikalne ka tareeka ek jagah rehta hai.
"""
import base64
import json
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


def ask(system, user, max_tokens=5000, temperature=0.2):
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
            timeout=240, retries=1)
    except Exception as e:
        _raise_with_body(e)

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


def ask_json(system, user, max_tokens=5000, temperature=0.2):
    """Wahi, par jawab JSON maan kar. Na mile to None.

    Model kabhi-kabhi JSON ke aage-peeche ek line likh deta hai ya use
    markdown fence mein daal deta hai. Isliye seedha json.loads nahi karte
    - pehle bahar ka kachra hata dete hain. None lautne par bulane wala
    chup-chaap ruk jaata hai; adhoore jawab par kaam aage badhana galat hai.
    """
    text = ask(system, user, max_tokens=max_tokens, temperature=temperature)
    return _extract_json(text)


def ask_vision_json(system, user, image_path, max_tokens=800, temperature=0.0):
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

"""
Vertex AI se illustration — seedha service account JSON file se.

Kyun ye file: n8n ke credential box mein private key paste karna baar-baar
fail ho raha tha ("secretOrPrivateKey must be an asymmetric key when using
RS256") kyunki JSON mein key ke \\n asli line-break nahi hote aur copy-paste
mein toot jaate hain. Yahan wo samasya hai hi nahi — script JSON file khud
padhti hai, key kahin type karni hi nahi padti.

Kaam ka tarika: service account se ek RS256 JWT banao, Google se access token
lo, phir Vertex ka generateContent bulao.
"""

import base64
import hashlib
import json
import os
import shutil
import time
import urllib.parse
import urllib.request

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/cloud-platform"

# Har scope ka apna token - Vertex (cloud-platform) aur reporter wali
# Sheet/Drive (sy_report.py) ek hi service account se, alag scope ke saath.
_token_cache = {}


def _log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def available(sa_path):
    if not sa_path or not os.path.exists(sa_path):
        return False, "service account JSON nahi mili"
    try:
        import jwt  # noqa: F401
    except Exception:
        return False, "PyJWT nahi hai — chalaiye: python -m pip install \"pyjwt[crypto]\""
    return True, ""


def _access_token(sa, scope=SCOPE):
    """Ek ghante ka token, cache ke saath (har scope ka alag)."""
    now = int(time.time())
    got = _token_cache.get(scope) or {}
    if got.get("token") and got.get("expires", 0) - 60 > now:
        return got["token"]

    import jwt

    claims = {
        "iss": sa["client_email"],
        "scope": scope,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }
    # Yahan private key file se seedha aati hai — asli line-breaks ke saath.
    assertion = jwt.encode(claims, sa["private_key"], algorithm="RS256")

    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode("utf-8")

    req = urllib.request.Request(TOKEN_URL, data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read().decode("utf-8"))

    _token_cache[scope] = {"token": out["access_token"],
                           "expires": now + int(out.get("expires_in", 3600))}
    return out["access_token"]


def _find_b64(node, depth=0):
    """Response ka shape model ke saath badalta rehta hai, isliye base64 ko
    dhoondh lete hain, ek tay raaste par bharosa nahi karte."""
    if depth > 8 or node is None:
        return ""
    if isinstance(node, str):
        return node if len(node) > 5000 else ""
    if isinstance(node, list):
        best = ""
        for x in node:
            got = _find_b64(x, depth + 1)
            if len(got) > len(best):
                best = got
        return best
    if isinstance(node, dict):
        best = ""
        for v in node.values():
            got = _find_b64(v, depth + 1)
            if len(got) > len(best):
                best = got
        return best
    return ""


def generate(sa_path, project_id, location, model, prompt, out_path, timeout=420):
    """Illustration banao aur out_path par likh do. Kabhi throw nahi karta —
    (True, '') ya (False, wajah) laut ata hai.

    Timeout udaar rakha gaya hai: pehle dry run mein Vertex ne 199 second liye
    the, aur purana 180 ka default us se bhi kam tha."""
    ok, why = available(sa_path)
    if not ok:
        return False, why

    # Ek hi khabar ke Hindi aur English bulletin bilkul ek jaisa prompt bhejte
    # hain - wo ek hi khabar hai. Isliye prompt ke hash par cache rakhte hain:
    # doosri bhasha wali illustration dobara nahi banti. Dry run mein ek image
    # par 199 second aur asli paisa laga tha; dohrana dono ka nuksaan hai.
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "illustrations")
    key = hashlib.sha1(("%s|%s|%s" % (model, location, prompt)).encode("utf-8")).hexdigest()[:16]
    cached = os.path.join(cache_dir, key + ".jpg")
    if os.path.exists(cached) and os.path.getsize(cached) > 20000:
        try:
            shutil.copyfile(cached, out_path)
            return True, ""
        except Exception:
            pass

    try:
        with open(sa_path, encoding="utf-8") as f:
            sa = json.load(f)
    except Exception as e:
        return False, "service account JSON padhi nahi gayi: %s" % e

    pid = project_id or sa.get("project_id") or ""
    if not pid:
        return False, "project id nahi mila"

    try:
        token = _access_token(sa)
    except Exception as e:
        return False, "access token nahi mila: %s" % e

    url = ("https://%s-aiplatform.googleapis.com/v1/projects/%s/locations/%s"
           "/publishers/google/models/%s:generateContent"
           % (location, pid, location, model))

    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        # Bina aspectRatio ke model 1024x1024 (chaukor) deta hai, aur wo
        # 16:9 frame mein crop hokar aadhi kat jaati hai. Dry run mein yahi hua.
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "16:9"},
        },
    }).encode("utf-8")

    req = urllib.request.Request(url, data=body)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        return False, "Vertex ne %s diya: %s" % (e.code, detail)
    except Exception as e:
        return False, "Vertex tak pahunch nahi paye: %s" % e

    b64 = _find_b64(data)
    if not b64:
        return False, "Vertex ne image nahi bheji: " + json.dumps(data)[:300]

    try:
        raw = base64.b64decode(b64)
    except Exception as e:
        return False, "image decode nahi hui: %s" % e

    if len(raw) < 20000:
        return False, "image bahut chhoti aayi (%d bytes)" % len(raw)

    with open(out_path, "wb") as f:
        f.write(raw)

    try:
        os.makedirs(cache_dir, exist_ok=True)
        shutil.copyfile(out_path, cached)
    except Exception:
        pass

    return True, ""


def build_prompt(job):
    """Jaan-boojhkar photoreal nahi. News mein AI se asli jaisi tasveer banana
    ek aisi ghatna dikhana hai jo hui nahi — illustration imaandaar hai."""
    queries = job.get("photoQueries")
    if isinstance(queries, list) and queries:
        subject = ", ".join(str(q) for q in queries[:3])
    else:
        subject = str(job.get("headlineEn") or job.get("headline") or "Indian news")[:120]

    return " ".join([
        "Editorial illustration for an Indian news bulletin about: " + subject + ".",
        "Style: flat vector editorial illustration, muted newsroom palette of deep navy,",
        "slate grey and a single warm red accent.",
        "Clearly a stylised illustration, NOT a photograph and NOT photorealistic.",
        "No recognisable real people, no identifiable faces, no logos, no brand marks.",
        "No text, no letters, no numbers anywhere in the image.",
        "Wide 16:9 composition with calm negative space in the lower third.",
        "Dignified and factual in tone, not dramatic, not sensational.",
    ])

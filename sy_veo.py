"""Veo se drishya banana - sirf wahan jahan sach mein koi footage hai hi nahi.

YE FILE KAHAN LAGTI HAI
========================
Shuru mein ye sirf JAANKARI wale hisson (gyan, kaam ki baat, yojana) ke
liye thi - "ship navigation kaise kaam karta hai" jaisi baaton ka koi asli
clip duniya mein hai hi nahi. Ab (Sep 2026, aapki apni maang par) khabar
aur bulletin bhi ismein shaamil hain - JAB kisi tukde par koshish karne ke
baad bhi koi sacchi tasveer/clip na mile. Wajah wahi rahi: aisi jagah
khaali screen ya ek jaisi purani tasveer se AI-chitran behtar dikhta hai,
BASHARTE teen baatein hamesha kaayam rahein (neeche).

TEEN BAATEIN JO KABHI NAHI TOOTNI CHAHIYE - inhi teeno se channel ka sach
ka usool bachta hai, chahe khabar ho ya gyan:

  1. LABEL KABHI MAT CHHUPAIYE. Jo bhi drishya AI se bana ho, screen par
     saaf "AI चित्रण" likha rahega (render_core isi credit string se
     pehchaanta hai) - khabar par bhi, gyan par bhi. YouTube ka apna
     niyam bhi yahi kehta hai: realistic AI content par ghoshna zaroori
     hai, na karne par video par khud label lag sakta hai ya wo hat
     sakti hai.
  2. YE "GHATNA KA SABOOT" BANKAR KABHI PESH NAHI HOTA - sirf DRISHYA
     hai. Prompt hamesha jagah/cheez/mahaul ka hota hai ("sadak par raat
     ki traffic", "khet mein baarish"), kisi khaas GHATNA ka nakli
     "record" kabhi nahi ("fulaana sadak durghatna" jaisa kuch banane ki
     koshish nahi hoti - prompt_for() isi wajah se shot ke BRIEF/QUERIES
     se banta hai, headline se nahi).
  3. AADMI KABHI NAHI - neeche wahi purana, na-todha hua niyam.

AADMI KABHI NAHI. personGeneration hamesha "dont_allow" jaata hai. Jagah,
cheez, tareeka, prakriya - ye sab ban sakte hain. Chehre nahi. Isse do
cheezein ek saath sambhal jaati hain: kisi asli aadmi ki nakli tasveer
kabhi nahi banegi, aur "aam log ka chehra kabhi nahi" wala purana usool
yahan bhi kaayam rehta hai - khabar ho ya gyan, ye niyam kisi ne nahi
badla.

PAISA. Har clip par paisa lagta hai (credit se katta hai). Isliye:
  - din bhar ki ek sakht seema hai (veo_max_per_day),
  - ek hi prompt dobara nahi banta - bani hui clip cache mein rehti hai,
  - aur poora hissa config se BAND hai jab tak aap khud chalu na karein.
  Khabar/bulletin ab isi ek seema mein gyan/kaam/yojana ke saath jagah
  baantte hain - seema wahi ki wahi hai, sirf istemal karne wale ab zyada
  hain.
"""
import base64
import hashlib
import json
import os
import re
import time

import sy_config as cfg
import sy_net

# Ye beat aur koi nahi. Suchi yahan hai, config mein nahi - taaki koi ise
# galti se badha na de. "local"/"news" (khabar) aur "bulletin" YAHAN
# JAAN-BOOJHKAR HAIN - pehle sirf gyan/kaam/yojana the, ab khabar par bhi
# chalta hai jab koi sacchi tasveer na mile (upar docstring mein poori
# wajah aur teen shart likhi hai).
ALLOWED_BEATS = ("gyan", "kaam", "yojana", "tech", "local", "news", "bulletin")

API = ("https://%s-aiplatform.googleapis.com/v1/projects/%s/locations/%s"
       "/publishers/google/models/%s:%s")


def log(*a):
    print("[veo]", *a, flush=True)


def _cache_dir():
    d = os.path.join(cfg.HERE, "veo_clips")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


# ----------------------------------------------------------- settings

def enabled():
    """Chalu hai ya nahi. Telegram ka switch config se UPAR hai.

    Do wajah se:

    1. config.ini haath se kholni padti hai, aur uska ek namoona bhi rakha
       hai (config.ini.template) - dono ek jaise dikhte hain aur galat wali
       badal dena bahut aasan hai. Template ko program padhta hi nahi.
    2. Aur zyada zaroori: Veo par paisa lagta hai. Agar kabhi lage ki
       kharch bhaag raha hai, to use rokne ke liye phone kaafi hona
       chahiye - laptop kholna, file dhoondhna, line badalna, restart
       karna, ye sab nahi.

    kv mein kuch likha ho to wahi maana jaata hai. Kuch na ho to config.
    """
    import sy_store as st
    override = st.kv_get("veo_on")
    if override is not None:
        return bool(override)
    return cfg.num("veo", "enabled", 0) == 1


def set_enabled(on):
    import sy_store as st
    st.kv_set("veo_on", 1 if on else 0)


def model():
    return cfg.get("veo", "model") or "veo-3.1-fast-generate-001"


def location():
    return cfg.get("veo", "location") or "us-central1"


def seconds():
    # Veo 3 sirf 4, 6 ya 8 leta hai. Beech ka koi ankda bheja to wo mana
    # kar deta hai, isliye yahin sabse paas wale par bitha dete hain.
    n = cfg.num("veo", "seconds", 6)
    return min((4, 6, 8), key=lambda v: abs(v - n))


def resolution():
    return cfg.get("veo", "resolution") or "720p"


def max_per_day():
    return cfg.num("veo", "max_per_day", 6)


def image_to_video_on():
    return cfg.num("veo", "animate_photos", 0) == 1


def sa_path():
    given = cfg.get("veo", "service_account")
    if given and os.path.exists(given):
        return given
    p = os.path.join(cfg.HERE, "satyayatra-sa.json")
    return p if os.path.exists(p) else ""


# ----------------------------------------------------------- din ka hisaab

def _today():
    return time.strftime("%Y-%m-%d")


def used_today():
    import sy_store as st
    if st.kv_get("veo_day", "") != _today():
        return 0
    return int(st.kv_get("veo_count", 0) or 0)


def note_used():
    import sy_store as st
    if st.kv_get("veo_day", "") != _today():
        st.kv_set("veo_day", _today())
        st.kv_set("veo_count", 0)
    st.kv_set("veo_count", used_today() + 1)


def room_left():
    return max(0, max_per_day() - used_today())


def allowed(beat):
    """Kya is khabar par Veo chal sakta hai? (haan/nahi, wajah)"""
    if not enabled():
        return False, "band hai (config mein [veo] enabled = 1 kijiye)"
    if str(beat or "") not in ALLOWED_BEATS:
        return False, "is kism ki video par AI ka drishya nahi banta"
    if not sa_path():
        return False, "service account JSON nahi mili"
    if room_left() <= 0:
        return False, "aaj ki seema (%d clip) poori ho chuki" % max_per_day()
    return True, ""


# ----------------------------------------------------------- asli kaam

def _token():
    import vertex
    with open(sa_path(), encoding="utf-8") as f:
        sa = json.load(f)
    return vertex._access_token(sa), sa


def _post(url, token, body, timeout=120):
    """post_json pehle se parsed dict lautata hai - yahan dobara parse nahi."""
    return sy_net.post_json(
        url, body,
        headers={"Authorization": "Bearer " + token},
        timeout=timeout, retries=1)


def _why_empty(data):
    """Khaali jawab ki jhalak - bina video ke laakhon akshar chhape.

    Do cheezein dhoondhta hai: Veo ke filter ki wajah (RAI), aur jawab ke
    andar ke naam. Lambi string (yaani video) kaat di jaati hai.
    """
    def skim(node, depth=0):
        if depth > 6:
            return "..."
        if isinstance(node, str):
            return node[:120] if len(node) <= 200 else "<%d akshar>" % len(node)
        if isinstance(node, (int, float, bool)) or node is None:
            return node
        if isinstance(node, list):
            return [skim(x, depth + 1) for x in node[:3]]
        if isinstance(node, dict):
            return dict((k, skim(v, depth + 1)) for k, v in list(node.items())[:12])
        return str(type(node).__name__)

    try:
        blob = json.dumps(skim(data.get("response") or data),
                          ensure_ascii=False)
    except Exception:
        blob = str(list((data or {}).keys()))
    low = blob.lower()
    if "rai" in low or "filter" in low or "block" in low or "safety" in low:
        return "Veo ke apne filter ne roka lagta hai: " + blob[:400]
    return "jawab ki shakl: " + blob[:400]


def _clip(prompt, out_path, vertical=False, image_path=""):
    """Ek clip banao. (True, '') ya (False, wajah). Kabhi throw nahi karta."""
    try:
        token, sa = _token()
    except Exception as e:
        return False, "access token nahi mila: %s" % e

    pid = cfg.get("veo", "project") or sa.get("project_id") or ""
    if not pid:
        return False, "project id nahi mila"

    inst = {"prompt": prompt}
    task = "textToVideo"
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                inst["image"] = {
                    "bytesBase64Encoded":
                        base64.b64encode(f.read()).decode("ascii"),
                    "mimeType": "image/jpeg",
                }
            task = "imageToVideo"
        except Exception as e:
            log("tasveer padhi nahi gayi:", e)

    params = {
        "sampleCount": 1,
        "durationSeconds": seconds(),
        "aspectRatio": "9:16" if vertical else "16:9",
        "resolution": resolution(),
        # Aawaaz hum khud banate hain - Veo ki aawaaz ka koi kaam nahi, aur
        # jo cheez kaam ki nahi uska paisa bhi nahi dena.
        "generateAudio": False,
        # AADMI KABHI NAHI. Upar wali tippani dekhiye - ye is file ki sabse
        # zaroori line hai.
        "personGeneration": "dont_allow",
        "negativePrompt": "text, watermark, logo, subtitles, distorted faces",
    }
    # "task" JAAN-BOOJHKAR NAHI BHEJA JAATA.
    #
    # Dastavez mein wo likha hai (textToVideo / imageToVideo), par asli
    # model ne use mana kar diya: "Invalid task: textToVideo". Aur uski
    # zaroorat hai bhi nahi - dastavez khud kehta hai ki na bhejo to task
    # baaki input se taad liya jaata hai. Image di hai to imageToVideo,
    # nahi di to textToVideo. Jo cheez apne aap sahi hoti hai use haath se
    # bhejna sirf ek aur tootne ki jagah banata hai.
    _ = task

    mdl = model()
    url = API % (location(), pid, location(), mdl, "predictLongRunning")

    # JO PARAMETER YE MODEL NA MAANE, USE HATA KAR DOBARA.
    #
    # Veo ke har model ka apna set hai aur wo badalta rehta hai - kuch
    # naye model negativePrompt nahi lete, kuch resolution nahi, kuch task
    # khud taad lete hain. Har baar aadmi ko log padh kar ek line badalni
    # pade, ye theek nahi.
    #
    # Isliye: 400 aaye to Google ke apne jawab mein se us field ka naam
    # nikalo jispar wo atka hai, use gira do, aur dobara bhejo. Zaroori
    # cheezein (prompt, aspectRatio, durationSeconds) kabhi nahi girti -
    # unke bina clip ka koi matlab hi nahi.
    KEEP = ("sampleCount", "durationSeconds", "aspectRatio")
    op = ""
    last = ""
    for _try in range(4):
        try:
            started = _post(url, token,
                            {"instances": [inst], "parameters": params})
            op = str(started.get("name") or "")
            break
        except sy_net.HttpError as e:
            body = str(getattr(e, "body", "") or "")
            last = "%s %s" % (e.status, body[:400])
            if e.status != 400:
                return False, "Veo ne mana kiya: " + last
            drop = ""
            for k in list(params.keys()):
                if k in KEEP:
                    continue
                # Google ka sandesh field ka naam likhta hai, par do alag
                # shakl mein - dono dekhi hui hain:
                #   Invalid value at 'parameters.resolution'
                #   Unknown name "resolution" at 'parameters'
                # Google ka sandesh field ka naam teen shaklon mein likhta
                # hai - teeno dekhi hui hain:
                #   Invalid value at 'parameters.resolution'
                #   Unknown name "resolution" at 'parameters'
                #   Invalid task: textToVideo          <- naam khula hua
                # Isliye khule naam ko bhi pakadte hain, par poore shabd ke
                # roop mein (\b), taaki "seed" kisi "seeded" mein na mil jaye.
                if (("parameters." + k) in body
                        or ("'%s'" % k) in body
                        or ('"%s"' % k) in body
                        or re.search(r"\b%s\b" % re.escape(k), body)):
                    drop = k
                    break
            if not drop:
                return False, "Veo ne mana kiya: " + last
            if drop == "personGeneration":
                # Ye sirf ek parameter nahi hai - ye chehron wali rok hai.
                # Girne par bhi clip ban jayegi, par ab wo rok sirf prompt
                # ke bharose rahegi ("no people"), jo kamzor hai. Isliye
                # ise chup-chaap girne nahi dete - log mein saaf likha
                # jaata hai taaki ye baat aapki nazar se guzre.
                log("CHETAVNI: ye model personGeneration nahi leta. Chehron "
                    "wali rok ab sirf prompt se hai - clip dekh kar pakka "
                    "kar lijiye ki usme koi aadmi nahi hai.")
            else:
                log("'%s' ye model nahi leta - hata kar dobara" % drop)
            params.pop(drop, None)
        except Exception as e:
            return False, "Veo tak baat nahi pahunchi: %s" % e
    if not op:
        return False, "Veo ne mana kiya: " + (last or "operation nahi bani")

    # Poll. Veo ko ek clip par aam taur par ek-do minute lagte hain.
    fetch = API % (location(), pid, location(), mdl, "fetchPredictOperation")
    waited = 0.0
    data = {}
    while waited < 420:
        time.sleep(10)
        waited += 10
        try:
            data = _post(fetch, token, {"operationName": op})
        except Exception as e:
            log("haal poochhne mein gadbad:", str(e)[:90])
            continue
        if data.get("done"):
            break
    if not data.get("done"):
        return False, "Veo ne %d second mein clip nahi di" % int(waited)

    if data.get("error"):
        return False, "Veo: %s" % str(data["error"])[:220]

    import vertex
    b64 = vertex._find_b64(data.get("response") or data)
    if not b64:
        # "Video nahi mili" apne aap mein koi wajah nahi hai - wo sirf
        # itna kehta hai ki jo dhoondha wo mila nahi. Veo do alag tarah se
        # khaali haath lauta ta hai aur dono ka ilaaj alag hai:
        #
        #   1. Uske apne safety filter ne rok diya (RAI). Tab jawab mein
        #      raiMediaFilteredCount/Reasons aata hai - prompt badalna
        #      padta hai.
        #   2. Jawab ki shakl hi kuch aur hai (nayi model, naya field).
        #      Tab response ke andar ke naam dekhne padte hain.
        #
        # Isliye ab dono ki jhalak log mein jaati hai. Poora jawab nahi -
        # usme video ke laakhon akshar hote hain.
        return False, "jawab mein video nahi mili — " + _why_empty(data)
    try:
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(b64))
    except Exception as e:
        return False, "clip likhi nahi gayi: %s" % e
    if os.path.getsize(out_path) < 50000:
        try:
            os.remove(out_path)
        except Exception:
            pass
        return False, "clip bahut chhoti aayi"
    return True, ""


def make(prompt, out_path, beat, vertical=False, image_path=""):
    """Bahar se yahi bulaya jaata hai. (True, credit) ya (False, wajah).

    Cache prompt par hai: ek hi vishay dobara aaya to clip dobara nahi
    banti. Gyan ke vishay ghoomkar wapas aate hain (GYAN_REPEAT_DAYS 240),
    aur yojana to har mahine, isliye ye bachat asli hai.
    """
    ok, why = allowed(beat)
    if not ok:
        return False, why

    key = hashlib.sha1(
        ("%s|%s|%s|%s" % (model(), prompt, vertical,
                          os.path.basename(image_path or ""))
         ).encode("utf-8")).hexdigest()[:16]
    cached = os.path.join(_cache_dir(), key + ".mp4")
    if os.path.exists(cached) and os.path.getsize(cached) > 50000:
        try:
            import shutil
            shutil.copyfile(cached, out_path)
            log("cache se mili:", key)
            return True, CREDIT
        except Exception:
            pass

    log("bana rahe hain (%s, %ds): %s" % (model(), seconds(), prompt[:70]))
    t0 = time.time()
    ok, why = _clip(prompt, out_path, vertical=vertical, image_path=image_path)
    if not ok:
        log("nahi bani:", why)
        return False, why

    note_used()
    log("ban gayi %.0f second mein (aaj %d/%d)"
        % (time.time() - t0, used_today(), max_per_day()))
    try:
        import shutil
        shutil.copyfile(out_path, cached)
    except Exception:
        pass
    return True, CREDIT


# Screen par yahi likha jaata hai. Ye label chhota hai par ye sach hai, aur
# isi wajah se ye poora rasta imaandari se chal sakta hai.
CREDIT = "AI चित्रण · सत्ययात्रा न्यूज"


# KHABAR PAR ASLI JAGAH KA NAAM PROMPT MEIN NAHI (Sep 2026, st_9699961).
# "Mohanlalganj CHC" wale tukde par prompt mein naam gaya ("Mohanlalganj CHC
# community health centre ... in Mohanlalganj, India") aur Veo ne ek
# imaarat bana di jis par Devanagari jaisa nakli board tha - dekhne mein
# bilkul usi asli CHC ki photo. Ye usool 2 ka ulanghan hai: AI chitran
# kisi asli, naam wali jagah ka "saboot" ban gaya. Ab khabar/bulletin par
# sirf sabse AAM khoj (art director aakhri khoj aam rakhta hai) jaati hai,
# brief aur jagah ka naam nahi; aur har prompt mein board/likhawat mana.
NEWS_BEATS = ("local", "news", "bulletin")


def prompt_for(shot, place="", beat=""):
    """Shot ki apni baat se Veo ke liye ek prompt.

    Art director pehle se har tukde ka "brief" aur angrezi "queries" deta
    hai - wahi yahan prompt ban jaate hain. Ek nayi AI call ki zaroorat
    nahi: jo soch ho chuki hai use dobara karwana paisa aur samay dono ka
    nuksan hai.
    """
    brief = str(shot.get("brief") or "").strip()
    qs = [str(q).strip() for q in (shot.get("queries") or []) if str(q).strip()]
    bits = []
    if str(beat or "") in NEWS_BEATS:
        # Upar NEWS_BEATS wali tippani dekhiye - aam khoj, bina jagah ke naam.
        if qs:
            q = qs[-1]
            if place:
                q = re.sub(re.escape(place), "", q, flags=re.I)
            q = " ".join(q.split())
            if q:
                bits.append("a typical scene: " + q + ", somewhere in India")
    else:
        if qs:
            bits.append(qs[0])
        if brief:
            bits.append(brief)
        if place and place.lower() not in " ".join(bits).lower():
            bits.append("in %s, India" % place)
    body = ", ".join(bits)[:600]
    if len(body) < 12:
        # KHOKHLA PROMPT NAHI JAANA CHAHIYE.
        #
        # Jis tukde par kuch nahi mila, aksar uski queries bhi kamzor hoti
        # hain - aur dono ka karan ek hi hai. Aisi haalat mein prompt sirf
        # "Documentary style footage..." reh jaata tha, yaani Veo se ye
        # kaha ja raha tha ki "kuch bhi bana do". Uska nateeja ya to bekaar
        # drishya hota hai ya khaali jawab.
        #
        # Ab aisa prompt bhejte hi nahi. Tukde ka type ek aakhri sahara hai
        # - wo kam se kam ye to batata hai ki cheez kis kism ki hai.
        kind = str(shot.get("type") or "").lower()
        body = {
            "place": "an ordinary Indian town street in daylight",
            "institution": "a government office building in India, exterior",
            "object": "a desk with papers and a pen, close up",
            "document": "an official printed form on a wooden desk, close up",
            "map": "a paper map on a table, slow pan",
        }.get(kind, "")
        if not body:
            return ""      # kuch bhi thos nahi - to clip bhi nahi
    # Documentary ka roop - film jaisa nahi. Ye jaan-boojhkar hai: drishya
    # ko sach ke paas rehna chahiye, chahe wo chitran hi ho.
    # "no text" akela kaafi nahi tha - Veo ne phir bhi imaarat par nakli
    # board likh diya (st_9699961). Board/likhawat/logo saaf mana.
    return ("Documentary style footage, steady camera, natural daylight, "
            "no people, no text on screen, no signboards, no lettering or "
            "writing anywhere, no logos: " + body)

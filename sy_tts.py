"""Script se aawaaz - Sarvam ya ElevenLabs se.

config.ini ke [tts] provider se tay hota hai kaun sa chalega - "sarvam"
(purana wala, jo pehle se chal raha tha - koi [tts] section na ho tab bhi
yahi default hai) ya "elevenlabs" (Sep 2026 mein joda gaya, jab Sarvam ka
balance khatam hokar 402 aaya). Ek line badal kar switch kar sakte hain,
dono ka code yahin maujood rehta hai.

Dono provider text ko chhote tukdon mein bhej kar aawaaz banate hain, phir
un tukdon ko jodte hain - is jodne/samay-naapne wale hisse mein koi farak
nahi (_join_and_time), sirf "ek tukda kaise bolwaya jaaye" alag hai.
"""
import base64
import os
import re
import subprocess
import wave

import sy_config as cfg
import sy_net

SARVAM_URL = "https://api.sarvam.ai/text-to-speech"
ELEVEN_URL = "https://api.elevenlabs.io/v1/text-to-speech/%s"

# Sarvam ki apni seema se thoda neeche rakha hai, taaki Devanagari ke lambe
# akshar gin-ti mein upar na le jayein.
# Ek request mein itne akshar. 450 tha, aur wahi wo gadbad thi jahan
# "line poori kiye bina agli line shuru" ho jaati thi: Sarvam apni seema
# se lamba text CHUP-CHAAP kaat deta hai - na koi galti, na koi sandesh,
# bas aadha vaakya. 280 uski seema se kaafi neeche hai.
#
# Par sirf ankada ghata dena bharosa nahi hai. Isliye neeche har tukde ki
# lambai jaanchi bhi jaati hai - agar aawaaz apne text ke hisaab se bahut
# chhoti aayi, to wo kati hui hai, aur use todh kar dobara banate hain.
SARVAM_CHUNK = 280

# ElevenLabs chup-chaap kaatta nahi (na hi ye "kata hua" bug abhi tak
# dekha gaya hai), isliye itni chhoti seema ki zaroorat nahi. Bada tukda
# rakha hai taaki kam request lagein - par bahut bada bhi nahi, kyunki
# tukda jitna chhota utna hi barik screen ka text awaaz ke saath chalta
# hai (dekhiye _join_and_time).
ELEVEN_CHUNK = 500

# Hindi lagbhag itne akshar prati second boli jaati hai. Isse pata chalta
# hai ki ek tukde ki aawaaz kitni lambi honi CHAHIYE thi.
#
# YE ANKDA GALAT THA, AUR USNE JHOOTHA ALARM BAJAYA
#
# Pehle yahan 9.0 tha - ek andaaza, naap nahi. Asli videos mein naapa gaya
# to aawaaz 12.9 se 14.9 akshar prati second par nikli. Yaani 9.0 ne har
# tukde ki ummeed lagbhag 50% zyada lambi bana di.
#
# Nateeja: nalsa wali video mein ye line aayi -
#     tukda 1 kata hua laga (15.6s aayi, ~25.9s chahiye thi)
# jabki wo tukda KATA HUA THA HI NAHI. 233 akshar 15.6 second mein, yaani
# 14.9 akshar prati second - bilkul aam raftaar. Par 9.0 ke hisaab se
# "25.9 second chahiye thi", aur wo jhootha alarm baj gaya.
#
# Us jhoothe alarm ki keemat hai: wo tukda dobara banta hai (Sarvam ka
# doosra kharch) aur beech mein ek jod lag jaata hai jo sunai de sakta hai.
#
# Ab 13.0 - naapa hua ankda. Isse alarm tabhi bajega jab aawaaz 8 akshar
# prati second se bhi dheemi aaye, aur utni dheemi wahi hoti hai jo sach
# mein aadhi kati ho.
#
# Ye jaanch sirf Sarvam ke liye hai (ElevenLabs chup-chaap kaatta nahi).
CPS = 13.0
CUT_RATIO = 0.62        # isse chhoti aayi to maan lo kat gayi hai

# AAWAAZ KI RAFTAAR - AUR EK GALTI JO MAINE KI THI
#
# Pehle yahan ek "target 112 wpm" tha aur program har video ke baad apne
# aap pace ghata-badha kar us ankde ka peechha karta tha. Wo do wajah se
# galat tha:
#
# 1. 112 ka ankada ek kamzor jagah se aaya tha. Television news ka 143 wpm
#    aur radio ka 160-180 wpm sahi ankde hain, par wo ANGREZI ke hain.
#    Hindi ka ankada maine ek aam se calculator wali website se le liya
#    tha - use itna bharosa dena hi meri galti thi.
#
# 2. Aur ye baat ki TTS insaan nahi hai. Sarvam ki aawaaz pace 1.0 par
#    natural lagne ke liye hi bani hai. Use 0.70 par kheenchne se wo dheemi
#    nahi hoti - wo TOOT jaati hai. Har akshar khinch kar aata hai aur
#    aawaaz robot jaisi sunai deti hai. Wahi hua: peechha karte-karte pace
#    0.70 tak gir gaya.
#
# Isliye ab koi peechha nahi. Ek saada, sthir naap - engine ke natural ke
# bahut paas - aur badalna ho to ek line config.ini mein:
#
#     [sarvam]
#     pace = 0.90
#
# wpm sirf log mein dikhta hai, taaki pata rahe ki kya chal raha hai. Us
# par koi faisla apne aap nahi hota.
# 1.00 = Sarvam ki apni natural raftaar. Ispar aawaaz kheenchi ya dabaayi
# nahi jaati, isliye engine ke apne artifacts sabse kam hote hain. Ye naap
# Harshvardhan ne chuna hai.
DEFAULT_PACE = 1.00
PACE_FLOOR, PACE_CEIL = 0.65, 1.25

# Do tukdon ke beech ek chhoti saans. Bina iske jod par vaakya agle vaakya
# se chipak jaata hai aur khabar hadbadai hui sunai deti hai.
JOIN_PAUSE = 0.20


def log(*a):
    print("[tts]", *a, flush=True)


def split_script(text, limit):
    """Vaakya ki seema par todo. Ek bhi vaakya limit se bada ho to hi
    beech se todte hain."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[।\.\?!])\s+", text)
    out, cur = [], ""
    for p in parts:
        if len(cur) + len(p) + 1 <= limit:
            cur = (cur + " " + p).strip()
            continue
        if cur:
            out.append(cur)
        while len(p) > limit:
            cut = p.rfind(" ", 0, limit) or limit
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        cur = p
    if cur:
        out.append(cur)
    return out


def _flt(section, key, default):
    try:
        v = cfg.get(section, key)
        return float(v) if v else default
    except Exception:
        return default


def _wpm(script, path):
    secs = duration(path)
    words = len(str(script or "").split())
    if secs < 1 or not words:
        return 0.0
    return words / (secs / 60.0)


def _wav_seconds(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


# ---------------------------------------------------------------- Sarvam --

def _sarvam_say(chunk, key, model, speaker, pace):
    data = sy_net.post_json(
        SARVAM_URL, {"text": chunk, "target_language_code": "hi-IN",
              "speaker": speaker, "model": model, "pace": round(pace, 3)},
        headers={"api-subscription-key": key}, timeout=120, retries=2)
    audios = data.get("audios") or []
    if not audios:
        raise RuntimeError("Sarvam ne aawaaz nahi bheji")
    return base64.b64decode(audios[0])


def current_pace():
    """Abhi kis raftaar par bol rahe hain. config.ini upar hai."""
    try:
        fixed = cfg.get("sarvam", "pace")
        if fixed:
            return max(PACE_FLOOR, min(PACE_CEIL, float(fixed))), True
    except Exception:
        pass
    return DEFAULT_PACE, False


def _sarvam_say_verified(chunk, workdir, i, key, model, speaker, pace):
    """Ek tukde ki aawaaz - aur ye jaanch ki wo poori bani ya nahi.

    Sarvam lamba text chup-chaap kaat deta hai. Kati hui aawaaz apne text
    ke hisaab se bahut chhoti hoti hai - yahi pakadne ka tareeka hai.
    Pakde jaane par tukde ko aadha-aadha karke dobara bhejte hain.
    """
    p = os.path.join(workdir, "voice_%02d.wav" % i)
    with open(p, "wb") as f:
        f.write(_sarvam_say(chunk, key, model, speaker, pace))
    got = _wav_seconds(p)
    want = len(chunk) / CPS

    if want > 2.0 and got < want * CUT_RATIO:
        log("tukda %d kata hua laga (%.1fs aayi, ~%.1fs chahiye thi) - todh kar dobara"
            % (i + 1, got, want))
        half = split_script(chunk, max(80, len(chunk) // 2 + 20))
        if len(half) > 1:
            blobs = []
            for h in half:
                blobs.append(_sarvam_say(h, key, model, speaker, pace))
            # WAV header sirf pehle wale ka rakhte hain, baaki ka data jodte hain.
            parts = []
            for k, b in enumerate(blobs):
                q = os.path.join(workdir, "voice_%02d_%d.wav" % (i, k))
                with open(q, "wb") as f:
                    f.write(b)
                parts.append(q)
            with wave.open(parts[0], "rb") as w0:
                params = w0.getparams()
            with wave.open(p, "wb") as dst:
                dst.setparams(params)
                for q in parts:
                    with wave.open(q, "rb") as src:
                        dst.writeframes(src.readframes(src.getnframes()))
            for q in parts:
                try:
                    os.remove(q)
                except Exception:
                    pass
    return p


def _speak_sarvam(script, workdir, style=""):
    key = cfg.need("sarvam", "api_key")
    model = cfg.get("sarvam", "model") or "bulbul:v3"
    speaker = cfg.get("sarvam", "speaker") or "ritu"

    chunks = split_script(script, SARVAM_CHUNK)
    if not chunks:
        raise RuntimeError("script khaali hai")

    pace, fixed = current_pace()
    # SHIKSHAK WALA ANDAAZ AB SIRF SCRIPT MEIN HAI, AAWAAZ MEIN NAHI (Sep 2026)
    #
    # Pehle gyan/kaam/yojana/tech par pace 0.92 kar di jaati thi, "thodi
    # thehri aawaaz" ke liye. Harshvardhan ne suna aur kaha: aawaaz robotic
    # ho gayi. Wahi purani seekh dobara: Sarvam 1.0 par hi natural hai,
    # usse kheenchna use dheema nahi, bejaan banata hai (upar DEFAULT_PACE
    # ki tippani). Apnapan shabdon aur vaakyon se aata hai, raftaar ghata
    # kar nahi - isliye ab style se aawaaz ka koi naap nahi badalta.
    log("sarvam: %d tukde, pace %.2f%s%s" % (len(chunks), pace,
        " (haath se)" if fixed else "", " [shikshak]" if style == "teacher" else ""))

    paths = [_sarvam_say_verified(c, workdir, i, key, model, speaker, pace)
             for i, c in enumerate(chunks)]
    out, timing = _join_and_time(chunks, paths)
    _log_speed(script, out, "sarvam")
    return out, timing


# ------------------------------------------------------------ ElevenLabs --

def _eleven_say(chunk, key, voice_id, model, stability, similarity, speed):
    payload = {
        "text": chunk,
        "model_id": model,
        "voice_settings": {
            "stability": stability,
            "similarity_boost": similarity,
            "speed": speed,
        },
    }
    return sy_net.fetch(
        ELEVEN_URL % voice_id,
        headers={"xi-api-key": key, "Accept": "audio/mpeg"},
        data=payload, method="POST", timeout=120, retries=2)


def _eleven_say_to_wav(chunk, workdir, i, key, voice_id, model, stability, similarity, speed):
    """Ek tukde ki aawaaz. ElevenLabs MP3 deta hai - ffmpeg se ek pakki,
    sabhi tukdon mein samaan (44100 Hz, mono) WAV mein badalte hain, taaki
    _join_and_time bina kisi jaanch ke sabko jod sake."""
    mp3_path = os.path.join(workdir, "voice_%02d.mp3" % i)
    wav_path = os.path.join(workdir, "voice_%02d.wav" % i)
    raw = _eleven_say(chunk, key, voice_id, model, stability, similarity, speed)
    with open(mp3_path, "wb") as f:
        f.write(raw)
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-i", mp3_path, "-ar", "44100", "-ac", "1", wav_path],
                   check=True, timeout=60)
    try:
        os.remove(mp3_path)
    except Exception:
        pass
    return wav_path


def _speak_elevenlabs(script, workdir, style=""):
    cfg.put_ffmpeg_on_path()
    key = cfg.need("elevenlabs", "api_key")
    voice_id = cfg.need("elevenlabs", "voice_id")
    model = cfg.get("elevenlabs", "model") or "eleven_multilingual_v2"
    stability = _flt("elevenlabs", "stability", 0.5)
    similarity = _flt("elevenlabs", "similarity_boost", 0.75)
    speed = max(0.7, min(1.2, _flt("elevenlabs", "speed", 1.0)))
    # Shikshak wala andaaz yahan bhi sirf script mein - pehle stability 0.35
    # aur speed 0.94 kar dete the, aur usse aawaaz robotic/ajeeb ho gayi
    # (Sep 2026, Harshvardhan ki shikayat). Ab har beat par wahi naap.

    chunks = split_script(script, ELEVEN_CHUNK)
    if not chunks:
        raise RuntimeError("script khaali hai")

    log("elevenlabs: %d tukde, voice %s" % (len(chunks), voice_id))

    paths = [_eleven_say_to_wav(c, workdir, i, key, voice_id, model, stability, similarity, speed)
             for i, c in enumerate(chunks)]
    out, timing = _join_and_time(chunks, paths)
    _log_speed(script, out, "elevenlabs")
    return out, timing


# ------------------------------------------------- saanjha jodne wala hissa --

def _join_and_time(chunks, paths):
    """WAV tukdon ko jodo, ek voice.wav banao, aur samay ke nishaan banao.

    Do tukdon ke provider chahe alag hon, jodne aur samay naapne ka
    tareeka ek hi hai - isiliye ye function dono se saanjha hai.
    """
    out = os.path.join(os.path.dirname(paths[0]), "voice.wav")

    # WAV ko seedha jodte hain - ffmpeg ki zaroorat nahi, aur na hi
    # dobara encode karne se aawaaz ki quality girti hai.
    with wave.open(paths[0], "rb") as w0:
        params = w0.getparams()
    gap = b"\x00" * int(params.framerate * JOIN_PAUSE
                        * params.nchannels * params.sampwidth)
    # Jodte waqt hi ye bhi darj karte hain ki kaun sa tukda kab bola gaya.
    #
    # YAHI WO CHEEZ HAI JISKI KAMI SE SCREEN KA TEXT AAGE BHAAG RAHA THA.
    #
    # Na Sarvam, na ElevenLabs shabd-dar-shabd timing deta hai, isliye ab
    # tak screen ke shabd akshar GIN kar baante jaate the - maano aawaaz
    # poore video mein ek hi raftaar se chalti ho. Par wo chalti nahi: har
    # tukde ki apni raftaar hai, beech mein saans hai, aur engine khud
    # shuru-ant mein thodi chuppi jodta hai. Wo sab jud kar text ko aage
    # kar deta tha aur darshak ko padhne mein mehnat karni padti thi.
    #
    # Ab har tukde ka ASLI samay naapa jaata hai. Puri timing na sahi, par
    # har do-teen vaakya par ek pakki keel gad jaati hai - aur usse text
    # aawaaz ke saath chalta hai.
    spans = []          # (akshar shuru, akshar ant, samay shuru, samay ant)
    cpos = 0
    clock = 0.0
    with wave.open(out, "wb") as dst:
        dst.setparams(params)
        for i, p in enumerate(paths):
            if i:
                dst.writeframes(gap)
                clock += JOIN_PAUSE
                cpos += 1                      # jod ka space
            secs = _wav_seconds(p)
            spans.append((cpos, cpos + len(chunks[i]), clock, clock + secs))
            cpos += len(chunks[i])
            clock += secs
            with wave.open(p, "rb") as src:
                # Yahan pehle koi jaanch nahi thi. Agar koi ek tukde ki
                # aawaaz kisi aur sample rate par aa jaaye, to uske frames
                # seedhe jud jaate the aur wo tukda galat raftaar aur galat
                # sur mein bajta - yaani theek wahi "robot jaisi" aawaaz.
                if (src.getframerate(), src.getnchannels(),
                        src.getsampwidth()) != (params.framerate,
                                                params.nchannels,
                                                params.sampwidth):
                    raise RuntimeError(
                        "tukda %d alag naap ki aawaaz mein aaya (%d Hz vs %d Hz)"
                        % (i + 1, src.getframerate(), params.framerate))
                dst.writeframes(src.readframes(src.getnframes()))
    for p in paths:
        try:
            os.remove(p)
        except Exception:
            pass
    return out, {"text": " ".join(chunks), "spans": spans}


def _log_speed(script, out, provider):
    # Sirf batane ke liye - ispar koi faisla nahi hota. Aawaaz dheemi ya
    # tez lage to config.ini mein raftaar badal dijiye.
    #
    # Do naap dikhate hain, ek nahi. "Shabd prati minute" Hindi mein dhokha
    # deta hai kyunki Hindi ke shabd Angrezi se lambe hote hain; akshar
    # prati second zyada seedha naap hai. Hindi bulletin lagbhag 11-12
    # akshar prati second par padha jaata hai - usse upar jaate hi aawaaz
    # hadbadai hui lagne lagti hai, chahe raftaar ka ankada kuch bhi ho.
    secs = duration(out)
    wpm = _wpm(script, out)
    cps = (len(re.sub(r"\s+", " ", str(script or "")).strip()) / secs) if secs else 0
    if wpm:
        log("%.0f shabd prati minute, %.1f akshar prati second" % (wpm, cps))
    if cps > 12.5:
        if provider == "sarvam":
            pace, _ = current_pace()
            log("ye tez hai. Dheemi karni ho to config.ini mein: [sarvam] pace = %.2f"
                % max(PACE_FLOOR, round(pace * 11.5 / cps, 2)))
        else:
            speed = _flt("elevenlabs", "speed", 1.0)
            log("ye tez hai. Dheemi karni ho to config.ini mein: [elevenlabs] speed = %.2f"
                % max(0.7, round(speed * 11.5 / cps, 2)))


def speak(script, workdir, style=""):
    """voice.wav bana do. Path lauta do, ya fail hone par Exception.

    config.ini ke [tts] provider se tay - "sarvam" (default, section na ho
    tab bhi yahi chalega - purana rawaiya bina config.ini badle bacha
    rehta hai) ya "elevenlabs".

    style - ab sirf log ke liye. Shikshak wala andaaz script (sy_ingest
    TEACHER_STYLE) mein hai; aawaaz ka naap har beat par ek jaisa, kyunki
    naap badalne se aawaaz robotic ho gayi thi."""
    provider = (cfg.get("tts", "provider") or "sarvam").strip().lower()
    if provider == "elevenlabs":
        return _speak_elevenlabs(script, workdir, style)
    return _speak_sarvam(script, workdir, style)


def duration(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30)
        return float((out.stdout or "0").strip() or 0)
    except Exception:
        return 0.0

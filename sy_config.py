"""config.ini padhta hai. Chaabiyan sirf yahan se aati hain.

Kahin bhi API key seedha code mein nahi likhi jaati. Isse do faayde hain:
code kisi ko dikhaya ja sakta hai, aur chaabi badalni ho to ek hi jagah
badalni padti hai.
"""
import configparser
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INI = os.path.join(HERE, "config.ini")
TEMPLATE = os.path.join(HERE, "config.ini.template")

WORK_ROOT = os.path.join(HERE, "work")
OUTPUT_DIR = os.path.join(HERE, "output")
DB_PATH = os.path.join(HERE, "satyayatra.db")
LOG_PATH = os.path.join(HERE, "satyayatra.log")
YT_TOKEN = os.path.join(HERE, "youtube-token.json")

# CLOUD (GitHub Actions) PAR CHAL RAHA HAI YA NAHI.
#
# Wahan har run ek nayi, khaali machine par hoti hai aur kuch minute baad
# khatam ho jaati hai (sy_cloud.py). Isliye kuch cheezein alag bartav
# karti hain - jaise /naya aur /dobara, jo laptop/server par program ko
# band karke dobara chalate the. Cloud par wahi kaam har run khud karti hai.
CLOUD = os.environ.get("SY_CLOUD", "") == "1"


# WINDOWS PAR HINDI CHHAAPNE KI EK GADBAD - AUR WO CHUP-CHAAP BAITHI THI
#
# Windows par Python ka output by default cp1252 mein jaata hai, aur usme
# Devanagari hai hi nahi. Console par ye dikh nahi tha kyunki nayi Windows
# ki console khud UTF-8 sambhaal leti hai. Par jaise hi output kisi FILE
# mein bheja gaya, wahi cheez fat gayi:
#
#   'charmap' codec can't encode characters in position 51-56
#
# Ye ek YouTube ke shirshak par aayi jismein Hindi thi. Yaani jis din bhi
# start.bat ka output kisi log file mein jaata, poora program pehli Hindi
# headline par gir jaata - aur wo headline har khabar mein hoti hai.
#
# Har module ye file import karta hai, isliye ilaaj yahin ek jagah:
# output ko UTF-8 par le aao, aur jo akshar phir bhi na chhap sakein unhe
# giraane ki jagah badal do (errors="replace"). Chhaapna kabhi program
# girane ki wajah nahi banna chahiye.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class ConfigError(Exception):
    pass


_cp = None


def _load():
    global _cp
    if _cp is not None:
        return _cp
    if not os.path.exists(INI):
        if os.path.exists(TEMPLATE):
            shutil.copyfile(TEMPLATE, INI)
            raise ConfigError(
                "config.ini abhi bani hai - " + INI + "\n"
                "Use kholiye, chaabiyan bhariye, phir dobara chalaiye.")
        raise ConfigError("config.ini nahi mili: " + INI)
    cp = configparser.ConfigParser()
    cp.read(INI, encoding="utf-8")
    _apply_env(cp)
    _cp = cp
    return cp


def _apply_env(cp):
    """Chaabiyan environment se - cloud par config.ini mein nahi hoti.

    GitHub Actions par config.ini repo mein padi hoti hai (bina chaabi ke),
    aur chaabiyan GitHub Secrets se environment mein aati hain. Naam ka
    niyam:  SY__<SECTION>__<KEY>  ->  config.ini ka [section] key.
    Jaise SY__ANTHROPIC__API_KEY -> [anthropic] api_key.

    Khaali value kuch nahi badalti - Secret na bhara ho to config.ini wali
    value hi rehti hai. '%' ko '%%' karna zaroori hai, warna configparser
    use apna nishan samajh kar value hi gira deta hai.
    """
    for name, value in os.environ.items():
        if not name.startswith("SY__") or not value.strip():
            continue
        parts = name[4:].split("__", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            continue
        sec, key = parts[0].lower(), parts[1].lower()
        if not cp.has_section(sec):
            cp.add_section(sec)
        cp.set(sec, key, value.strip().replace("%", "%%"))


def get(section, key, default=""):
    cp = _load()
    try:
        return str(cp.get(section, key)).strip()
    except Exception:
        return default


def need(section, key):
    """Bina iske kaam nahi chalega. Khaali ho to saaf-saaf bata dete hain."""
    v = get(section, key)
    if not v:
        raise ConfigError(
            "config.ini mein [%s] %s khaali hai. Use bhar kar dobara chalaiye."
            % (section, key))
    return v


def num(section, key, default):
    v = get(section, key)
    try:
        return int(float(v))
    except Exception:
        return default


def youtube_client():
    """YouTube ka client_id aur client_secret. Lauta deta hai, chhapta nahi.

    Do jagah dekhta hai. Pehle config.ini, aur wahan na ho to Google Cloud
    se download ki hui client_secret_*.json - jo isi folder mein padi hoti
    hai. Isse chaabi kabhi haath se type nahi karni padti aur na hi kahin
    copy karke bhejni padti hai: file jaise Google ne di, waise hi rehti
    hai.
    """
    cid = get("youtube", "client_id")
    csec = get("youtube", "client_secret")
    if cid and csec:
        return cid, csec

    import glob
    import json
    for path in sorted(glob.glob(os.path.join(HERE, "client_secret*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        # Desktop app ka JSON "installed" ke andar aata hai, web app ka "web".
        blob = data.get("installed") or data.get("web") or {}
        cid = str(blob.get("client_id") or "")
        csec = str(blob.get("client_secret") or "")
        if cid and csec:
            return cid, csec

    raise ConfigError(
        "YouTube ka client nahi mila.\n"
        "Ya to Google Cloud se download ki hui client_secret_*.json is folder\n"
        "mein rakhiye (" + HERE + "), ya config.ini ke [youtube] mein\n"
        "client_id aur client_secret bhar dijiye.")


def ffmpeg_dir():
    """ffmpeg kahan hai. config mein na ho to aam jagahein dekh lete hain.

    Windows par ye baar-baar phansa hai: PowerShell mein ffmpeg mil jaata
    hai par .bat double-click karne par nahi, kyunki dono ka PATH alag hota
    hai. Isliye khud dhoondh lete hain.
    """
    given = get("paths", "ffmpeg")
    if given:
        if os.path.isfile(given):
            return os.path.dirname(given)
        if os.path.isdir(given):
            return given
    for d in (r"C:\ffmpeg-9.0.1-full_build\bin",
              r"C:\ffmpeg\bin",
              "/usr/bin", "/usr/local/bin", "/snap/bin",
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "ffmpeg", "bin"),
              os.path.join(os.environ.get("ProgramFiles", ""), "ffmpeg", "bin")):
        if not d:
            continue
        # Windows par ffmpeg.exe, Linux par sirf ffmpeg. Server Linux hi
        # hoga, isliye dono dekhte hain.
        for name in ("ffmpeg.exe", "ffmpeg"):
            if os.path.isfile(os.path.join(d, name)):
                return d
    return ""


def put_ffmpeg_on_path():
    d = ffmpeg_dir()
    if d and d not in os.environ.get("PATH", ""):
        os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    return bool(shutil.which("ffmpeg"))


def ensure_dirs():
    for d in (WORK_ROOT, OUTPUT_DIR):
        if not os.path.isdir(d):
            os.makedirs(d)


def masked_summary():
    """Kya-kya bhara hua hai, ye batata hai - par value kabhi nahi dikhata."""
    rows = []
    provider = get("tts", "provider") or "sarvam"
    rows.append("  [tts] provider       %s" % provider)
    for sec, key in (("anthropic", "api_key"), ("sarvam", "api_key"),
                     ("elevenlabs", "api_key"), ("elevenlabs", "voice_id"),
                     ("pexels", "api_key"), ("telegram", "bot_token"),
                     ("telegram", "chat_id")):
        v = get(sec, key)
        rows.append("  [%s] %-14s %s" % (sec, key, "bhara hua" if v else "KHAALI"))
    try:
        youtube_client()
        rows.append("  [youtube] client       mil gaya")
    except ConfigError:
        rows.append("  [youtube] client       NAHI mila")
    return "\n".join(rows)


if __name__ == "__main__":
    try:
        _load()
    except ConfigError as e:
        print(e)
        sys.exit(1)
    print("config.ini:")
    print(masked_summary())
    print("\nffmpeg:", ffmpeg_dir() or "NAHI mila")

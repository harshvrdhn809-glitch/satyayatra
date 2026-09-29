"""Sab kuch jagah par hai ya nahi - ek nazar mein.

Ise pehle chalaiye, phir asli system. Jo cheez kam hai wo yahin pakad mein
aa jayegi, aadhi video banne ke baad nahi.

Koi chaabi is jaanch mein kabhi nahi dikhti - sirf "bhara hua" ya "KHAALI".
"""
import os
import shutil
import subprocess
import sys

import sy_config as cfg

OK = "  theek   "
BAD = "  KAMI    "
WARN = "  dhyaan  "

problems = []
warnings = []


def line(mark, what, note=""):
    print(mark + what + (("  -  " + note) if note else ""))


def check_python():
    v = sys.version_info
    txt = "%d.%d.%d" % (v[0], v[1], v[2])
    if v[0] == 3 and v[1] >= 9:
        line(OK, "Python " + txt)
    else:
        line(BAD, "Python " + txt, "3.9 ya usse naya chahiye")
        problems.append("Python purana hai")


def check_ffmpeg():
    cfg.put_ffmpeg_on_path()
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if path:
            line(OK, tool)
        else:
            line(BAD, tool, "nahi mila")
            problems.append(tool + " nahi mila")


def check_pillow():
    try:
        from PIL import Image  # noqa: F401
        line(OK, "Pillow")
    except Exception:
        line(BAD, "Pillow", "pip install pillow")
        problems.append("Pillow nahi hai")


def check_font():
    """Devanagari font ke bina screen ka har akshar dabba ban jaata hai."""
    names = ("notosansdevanagari", "noto sans devanagari")
    # Windows aur Linux dono - server par ye Linux hi hoga.
    roots = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""),
                          "Microsoft", "Windows", "Fonts"),
             "/usr/share/fonts", "/usr/local/share/fonts",
             os.path.expanduser("~/.fonts"),
             os.path.expanduser("~/.local/share/fonts")]
    found = []
    for r in roots:
        if not r or not os.path.isdir(r):
            continue
        try:
            # Linux par fonts kai tah neeche hote hain (fonts/truetype/...),
            # isliye poora ped dekhte hain.
            for dirpath, _dirs, files in os.walk(r):
                for f in files:
                    low = f.lower().replace(" ", "")
                    if any(n.replace(" ", "") in low for n in names):
                        found.append(f)
                if len(found) > 40:
                    break
        except Exception:
            pass
    if found:
        line(OK, "Noto Sans Devanagari", "%d file" % len(found))
    else:
        line(BAD, "Noto Sans Devanagari", "iske bina Devanagari dabbe jaisi dikhegi")
        problems.append("Devanagari font nahi mila")


def check_libass():
    """ffmpeg mein libass hona chahiye - saara screen text usi se banta hai."""
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-buildconf"],
                             capture_output=True, text=True, timeout=30)
        blob = (out.stdout or "") + (out.stderr or "")
        if "libass" in blob:
            line(OK, "ffmpeg mein libass")
        else:
            line(BAD, "ffmpeg mein libass", "is build mein nahi hai")
            problems.append("ffmpeg libass ke bina hai")
    except Exception as e:
        line(WARN, "ffmpeg mein libass", "jaanch nahi hui: %s" % e)
        warnings.append("libass ki jaanch nahi ho payi")


def check_live_keys():
    """Chaabi bhari hui hai - ye kaafi nahi. Kya wo chalti bhi hai?

    Pexels ki chaabi bhari hui thi aur jaanch "theek" keh rahi thi, par
    asal mein wo 401 de rahi thi - yaani har video se chalti footage
    chup-chaap gayab thi. "Bhara hua" aur "chalta hua" do alag baatein
    hain, aur jaanch ko doosri wali batani chahiye.

    Har jaanch ek chhoti si request hai. Kisi ka kharch nahi hota.
    """
    import sy_net

    key = cfg.get("pexels", "api_key")
    if not key:
        line(WARN, "Pexels chaabi", "nahi hai - footage nahi aayegi")
        warnings.append("Pexels ki chaabi nahi")
    else:
        try:
            sy_net.get_json(
                "https://api.pexels.com/v1/search?per_page=1&query=river",
                headers={"Authorization": key}, timeout=25)
            line(OK, "Pexels chaabi", "chal rahi hai")
        except sy_net.HttpError as e:
            if e.status == 401:
                line(BAD, "Pexels chaabi",
                     "401 - galat ya purani chaabi (%d akshar ki hai)" % len(key))
                problems.append("Pexels ki chaabi 401 de rahi hai")
            else:
                line(WARN, "Pexels chaabi", str(e))
                warnings.append("Pexels ki jaanch nahi ho payi")
        except Exception as e:
            line(WARN, "Pexels chaabi", "jaanch nahi ho payi: %s" % e)

    # Baaki drishya ke source. Ye bina chaabi ke chalte hain (Commons,
    # Openverse) ya muft chaabi se (Pixabay). Inhe yahin jaanchte hain,
    # kyunki "bhara hua" aur "chalta hua" do alag baatein hain - Pexels ki
    # chaabi bhari hui thi aur chup-chaap 401 de rahi thi.
    import sy_media
    if cfg.get("contact", "email") or cfg.get("contact", "url"):
        line(OK, "[contact] email", "Commons ko pehchan mil rahi hai")
    else:
        line(BAD, "[contact] email",
             "iske bina Commons har request par 429 deta hai - ek bhi tasveer nahi")
        problems.append("[contact] email khaali hai - Commons band rahega")

    for label, fn, q in (("Wikimedia Commons", sy_media.commons_photo, "Prayagraj"),
                         ("Commons footage", sy_media.commons_clip, "India river"),
                         ("Openverse", sy_media.openverse_photo, "Indian road")):
        try:
            url, _ = fn(q)
            line(OK, label, "chal raha hai" if url else "chal raha hai (is khoj par kuch nahi)")
        except Exception as e:
            line(WARN, label, str(e)[:60])
            warnings.append(label + " nahi khula")

    # Sarkari safhon ka certificate. Iske bina bahut se .gov.in safhe
    # Python mein khulte hi nahi (browser mein khulte hain) - jaanch mein
    # 19 mein se 6 vishay isi wajah se band the.
    if sy_net.truststore_on():
        line(OK, "truststore", "sarkari safhe Windows ke bharose se khulenge")
    else:
        line(WARN, "truststore", "nahi laga - kuch .gov.in safhe band rahenge "
                                 "(pip install truststore)")
        warnings.append("truststore nahi hai - kuch sarkari safhe nahi khulenge")

    # Trending ke do signal. Google ka RSS anadhikarik hai aur kabhi khaali
    # aa sakta hai - isliye ye jaanch "dhyaan" hai, "KAMI" nahi: ek chup ho
    # jaye to doosra kaam chalata rahega.
    import sy_trend
    try:
        g = sy_trend.google_trends(limit=5)
        if g:
            line(OK, "Google Trends (Bharat)", "%d vishay, jaise: %s"
                 % (len(g), g[0]["term"][:32]))
        else:
            line(WARN, "Google Trends (Bharat)", "khaali aaya - YouTube se kaam chalega")
            warnings.append("Google Trends khaali - doosra signal chal raha hai")
    except Exception as e:
        line(WARN, "Google Trends (Bharat)", str(e)[:60])
        warnings.append("Google Trends nahi khula")

    try:
        y = sy_trend.youtube_trending(limit=5)
        if y:
            line(OK, "YouTube trending (Bharat)", "%d, jaise: %s"
                 % (len(y), y[0]["term"][:32]))
        else:
            line(WARN, "YouTube trending (Bharat)", "kuch nahi aaya")
            warnings.append("YouTube trending khaali")
    except Exception as e:
        line(WARN, "YouTube trending (Bharat)", str(e)[:60])
        warnings.append("YouTube trending nahi khula")

    # Lambi video (sy_long) ka teesra signal - X ke trend, trends24.in ke
    # sarvajanik safhe se. Na khule to sirf "dhyaan": baaki srot chalte hain.
    try:
        import sy_long
        x = sy_long.x_trends(limit=5)
        if x:
            line(OK, "X trends (trends24.in)", "%d, jaise: %s" % (len(x), x[0][:32]))
        else:
            line(WARN, "X trends (trends24.in)", "kuch nahi aaya - lambi video bina X ke chunegi")
            warnings.append("X trends khaali")
    except Exception as e:
        line(WARN, "X trends (trends24.in)", str(e)[:60])
        warnings.append("X trends nahi khule")

    # LEKH KA SROT - YE JAANCH SABSE ZYADA KAAM KI HAI.
    #
    # Vishay mil jaana aadha kaam hai; uspar poora LEKH milna asli kaam
    # hai. Sep 2026 mein yahi hissa chup-chaap toota tha - Google News ne
    # akhbaar ka seedha pata dena band kar diya, aur kisi ko pata hi nahi
    # chala kyunki program bas "vishay chhod diya" keh kar aage badh jaata
    # tha. Ab wo nakaami yahan pakdi jayegi, video banne se pehle.
    try:
        import sy_net as _net
        L = sy_trend.search_links("India news")
        if len(L) >= 3:
            line(OK, "Lekh ka srot (GDELT)", "%d akhbaar, jaise: %s"
                 % (len(L), _net.host(L[0])[:32]))
        elif L:
            line(WARN, "Lekh ka srot (GDELT)", "sirf %d pata mila" % len(L))
            warnings.append("Lekh ka srot kamzor - khoj patli aa rahi hai")
        else:
            line(WARN, "Lekh ka srot (GDELT)", "ek bhi pata nahi")
            warnings.append("Lekh ka srot khaali - chuni hui khabar nahi banegi")
    except Exception as e:
        line(WARN, "Lekh ka srot (GDELT)", str(e)[:60])
        warnings.append("Lekh ka srot nahi khula")

    # Sarvajanik chehre. Ye jaanch isliye hai ki "Modi ki tasveer nahi
    # mili" jaisi kami aadhi video ban jaane ke baad nahi, yahin pakdi
    # jaye. Do naam - ek rajneeti se, ek khel se.
    for who in ("Narendra Modi", "Rahul Gandhi"):
        try:
            url, credit = sy_media.portrait(who)
            if url:
                line(OK, "chehra: " + who, credit[:52])
            else:
                line(BAD, "chehra: " + who, "tasveer nahi mili")
                problems.append("sarvajanik chehre nahi mil rahe (" + who + ")")
        except Exception as e:
            line(WARN, "chehra: " + who, str(e)[:60])
            warnings.append("chehre ki jaanch nahi ho payi")

    # "Jaanne ki baat" ka source. Ye bhi Wikimedia hai, yaani wahi pehchan
    # wala niyam - isliye [contact] khaali hone par ye bhi 429 dega.
    try:
        import sy_ingest
        page, text = sy_ingest._wiki_text("Monsoon")
        if text:
            line(OK, "Wikipedia (gyan)", "%s - %d akshar" % (page, len(text)))
        else:
            line(BAD, "Wikipedia (gyan)", "lekh khaali aaya")
            problems.append("Wikipedia se lekh nahi mil raha")
    except Exception as e:
        line(WARN, "Wikipedia (gyan)", str(e)[:60])
        warnings.append("Wikipedia nahi khula")

    if cfg.get("pixabay", "api_key"):
        try:
            url, _ = sy_media.pixabay_photo("river")
            if url:
                line(OK, "Pixabay chaabi", "chal rahi hai")
            else:
                line(BAD, "Pixabay chaabi", "jawab to aaya par khaali - chaabi galat ho sakti hai")
                problems.append("Pixabay ki chaabi shaayad galat hai")
        except Exception as e:
            line(BAD, "Pixabay chaabi", str(e)[:60])
            problems.append("Pixabay ki chaabi nahi chal rahi")
    else:
        line(WARN, "Pixabay chaabi", "nahi hai - ek stock source kam (muft hai)")
        warnings.append("Pixabay ki chaabi nahi - ek source kam")

    token = cfg.get("telegram", "bot_token")
    if token:
        try:
            me = sy_net.get_json(
                "https://api.telegram.org/bot%s/getMe" % token, timeout=25)
            name = ((me.get("result") or {}).get("username") or "?")
            line(OK, "Telegram bot", "@" + name)
        except Exception as e:
            line(BAD, "Telegram bot", str(e))
            problems.append("Telegram ka bot token nahi chal raha")

    akey = cfg.get("anthropic", "api_key")
    if akey:
        try:
            # Sabse chhoti mumkin request - kharch na ke barabar.
            sy_net.post_json(
                "https://api.anthropic.com/v1/messages",
                {"model": cfg.get("anthropic", "model") or "claude-sonnet-4-6",
                 "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                headers={"x-api-key": akey, "anthropic-version": "2023-06-01"},
                timeout=40, retries=0)
            line(OK, "Anthropic chaabi", "chal rahi hai")
        except sy_net.HttpError as e:
            if e.status in (401, 403):
                line(BAD, "Anthropic chaabi", "%d - galat chaabi" % e.status)
                problems.append("Anthropic ki chaabi nahi chal rahi")
            elif e.status == 400:
                # max_tokens=1 par model shikayat kar sakta hai - chaabi to chali.
                line(OK, "Anthropic chaabi", "chal rahi hai")
            else:
                line(WARN, "Anthropic chaabi", str(e))
        except Exception as e:
            line(WARN, "Anthropic chaabi", "jaanch nahi ho payi: %s" % e)

    # Sarvam ki jaanch jaan-boojhkar nahi ki - uski har request aawaaz
    # banati hai, yaani kharch. Wo pehli video par khud pata chal jayegi.


def check_config():
    try:
        cfg._load()
    except cfg.ConfigError as e:
        line(BAD, "config.ini", str(e).split("\n")[0])
        problems.append("config.ini taiyar nahi")
        return
    line(OK, "config.ini")
    for sec, key, why in (
            ("anthropic", "api_key", "script aur art direction iske bina nahi"),
            ("sarvam", "api_key", "aawaaz iske bina nahi"),
            ("telegram", "bot_token", "approval iske bina nahi"),
            ("telegram", "chat_id", "approval kahan bheji jaye"),
    ):
        if cfg.get(sec, key):
            line(OK, "[%s] %s" % (sec, key))
        else:
            line(BAD, "[%s] %s" % (sec, key), why)
            problems.append("[%s] %s khaali hai" % (sec, key))
    # Pexels ke bina kaam chalta hai - bas video mein chalti footage nahi aayegi.
    if cfg.get("pexels", "api_key"):
        line(OK, "[pexels] api_key")
    else:
        line(WARN, "[pexels] api_key", "iske bina footage nahi, sirf design")
        warnings.append("Pexels ki chaabi nahi - video mein chalti footage nahi aayegi")


def check_youtube():
    if cfg.CLOUD:
        # Cloud par browser nahi - sirf "TV/limited input" wala client chalta
        # hai, aur sign-in Telegram se hota hai.
        have = []
        try:
            cfg.youtube_client()
            have.append("laptop wala (JSON)")
        except cfg.ConfigError:
            pass
        try:
            import sy_youtube
            sy_youtube.device_client()
            have.append("TV/device")
        except Exception:
            pass
        if have:
            line(OK, "YouTube client", ", ".join(have))
        else:
            line(BAD, "YouTube client",
                 "YOUTUBE_CLIENT_SECRET_JSON secret bhariye (CLOUD.md)")
            problems.append("YouTube client nahi mila")
        if os.path.exists(cfg.YT_TOKEN):
            line(OK, "YouTube sign-in", "token maujood hai")
        else:
            line(WARN, "YouTube sign-in",
                 "YOUTUBE_TOKEN_JSON secret bhariye (laptop ki youtube-token.json)")
        return
    try:
        cfg.youtube_client()
        line(OK, "YouTube client")
    except cfg.ConfigError:
        line(BAD, "YouTube client",
             "client_secret_*.json is folder mein rakhiye")
        problems.append("YouTube client nahi mila")
    if os.path.exists(cfg.YT_TOKEN):
        line(OK, "YouTube sign-in", "ho chuka hai")
    else:
        line(WARN, "YouTube sign-in", "pehli baar par browser khulega")


def check_store():
    try:
        import sy_store as st
        st.conn()
        counts = ", ".join(
            "%s %d" % (s, st.count_status(s))
            for s in ("pending", "awaiting", "published", "failed"))
        line(OK, "database", counts)
    except Exception as e:
        line(BAD, "database", str(e))
        problems.append("database nahi khuli")


def check_renderer():
    for mod in ("render_core", "thumb", "backdrop", "sy_scenes"):
        try:
            __import__(mod)
            line(OK, mod + ".py")
        except Exception as e:
            line(BAD, mod + ".py", str(e))
            problems.append(mod + ".py nahi chala")


def main():
    print("SatyaYatra - jaanch")
    print("folder:", cfg.HERE)
    print()
    cfg.ensure_dirs()
    check_python()
    check_ffmpeg()
    check_libass()
    check_pillow()
    check_font()
    print()
    check_config()
    check_youtube()
    print()
    check_live_keys()
    print()
    check_store()
    check_renderer()
    print()
    if problems:
        print("ROKNE WALI CHEEZEIN (%d):" % len(problems))
        for p in problems:
            print("  -", p)
    if warnings:
        print("DHYAAN DENE WALI CHEEZEIN (%d):" % len(warnings))
        for w in warnings:
            print("  -", w)
    if not problems:
        print("Sab zaroori cheezein jagah par hain.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""Poora system, ek program.

Ye lagataar chalta rehta hai aur baari-baari se ye dekhta hai:

  khabar dhoondhni hai?   -> feeds padho, script likhwao
  yojana dhoondhni hai?   -> PIB/Amar Ujala padho
  koi khabar taiyar hai?  -> video banao aur Telegram par bhejo
  koi jawab aaya?         -> approve hui to YouTube, reject hui to bas nishan

Ek baar mein ek hi video banti hai, aur do upload ke beech ek tay faasla
rakha jaata hai. Wo faasla hi wo cheez hai jiski kami se "too many requests"
aata tha.
"""
import os
import re
import shutil
import sys
import time
import traceback

import sy_ai
import sy_config as cfg
import sy_ingest
import sy_produce
import sy_store as st
import sy_telegram
import sy_trend
import sy_youtube


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


# ------------------------------------------------------------- upload

def _today():
    return time.strftime("%Y-%m-%d")


def upload_allowed():
    """Kya ABHI upload kiya ja sakta hai? (haan/nahi, wajah)

    Din bhar ki GINTI ki seema yahan nahi hai - wo ab production_allowed()
    mein, BANANE ke waqt lagti hai (neeche dekhiye, wajah wahin likhi hai).
    Yahan sirf itna dekha jaata hai ki do upload ke beech itna faasla rahe
    ki YouTube "too many requests" na kahe - wahi asli, technical zaroorat
    hai jiske liye ye function bana tha.
    """
    gap = cfg.num("limits", "min_minutes_between_uploads", 20)
    last = float(st.kv_get("last_upload_ts", 0) or 0)
    waited = (time.time() - last) / 60.0
    if last and waited < gap:
        return False, "pichhle upload ko %d minute hue, %d chahiye" % (waited, gap)
    return True, ""


def note_upload():
    if st.kv_get("upload_day", "") != _today():
        st.kv_set("upload_day", _today())
        st.kv_set("upload_count", 0)
    st.kv_set("upload_count", int(st.kv_get("upload_count", 0) or 0) + 1)
    st.kv_set("last_upload_ts", time.time())


def uploads_today():
    if st.kv_get("upload_day", "") != _today():
        return 0
    return int(st.kv_get("upload_count", 0) or 0)


def in_flight_count():
    """Kitni video is waqt 'ban rahi', 'jawab ka' ya 'upload ka' intezaar
    kar rahi hain - inmein se har ek jald hi ek upload-baari maangegi."""
    return (st.count_status("producing") + st.count_status("awaiting")
            + st.count_status("approved"))


def production_allowed():
    """Kya ABHI ek NAYA, ghadi-anusaar wala video banaya jaaye? (haan/nahi, wajah)

    ASLI BADLAV YAHI HAI. Pehle seema sirf upload par thi
    (max_uploads_per_day, upload_allowed() mein) - matlab video pehle poori
    tarah BAN chuki hoti thi, Telegram se APPROVE bhi ho chuki hoti thi, aur
    sirf isliye khadi rehti thi kyunki din ki upload-ginti poori ho chuki
    thi. Wo intezaar raat paar kar jaata tha - aur agle din wo "aaj ki
    khabar" ek din purani ho chuki hoti thi. Yahi shikayat thi.

    Ab seema BANANE ke waqt lagti hai. Aaj ab tak jitni upload ho chukin,
    aur jitni is waqt render/jawab/upload ke intezaar mein khadi hain
    (in_flight_count) - dono jod kar dekhte hain. Wahi ginti
    max_uploads_per_day chhoo le to naya, ghadi-anusaar video BANTA hi
    nahi - na render ka samay lagta hai, na Telegram par ek aur approval
    khadi hoti hai jo waise bhi kal tak khinchti.

    Bulletin aur /khabar se manga hua vishay ISSE nahi rukte (tick_produce
    mein FORCE_KEY wala hissa is check se PEHLE hai) - wo dono waqt ke
    paaband hain, isliye jagah unke liye pehle se aarakshit rehti hai. Ye
    seema sirf ghadi-anusaar chalne wali aam khabar/kaam/Reel par lagti
    hai.

    EK BAAR KI CHHOOT: abhi.bat (sy_now.py) jab "abhi turant kaam karo"
    kehta hai, to uska matlab yahi hona chahiye - koi ghadi na, koi seema
    na. Warna "abhi" dabane par bhi kabhi-kabhi kuch nahi hota tha, aur
    wajah samajh mein nahi aati thi (jagah pehle se bhar chuki thi). Isliye
    sy_now.py ek nishan chhod jaata hai jo isi ek koshish ke liye seema
    hata deta hai, phir khud mit jaata hai - agli baari se seema wapas
    apne aap lag jaati hai.
    """
    if st.kv_get("produce_bypass_cap_once"):
        st.kv_set("produce_bypass_cap_once", None)
        return True, "abhi.bat ne is ek baar ke liye seema hatai"
    cap = cfg.num("limits", "max_uploads_per_day", 5)
    # 0 ya usse kam matlab seema hi hatai gayi hai - Harshvardhan ki apni
    # maang par (roz har 2 ghante video, jyada baar ban sake isliye).
    if cap <= 0:
        return True, ""
    used = uploads_today() + in_flight_count()
    if used >= cap:
        return False, "aaj ki jagah (%d) bulletin/forced ke baad bhar chuki" % cap
    return True, ""


# --------------------------------------------------------------- ticks

def tick_bulletin():
    """Roz shaam teen bulletin - Mirzapur, Prayagraj, poora UP.

    Ye purani ek-khabar-ek-video wali line se ALAG hai: das khabrein ek
    saath, ek hi video, ek hi approval. Har area ka apna waqt hai
    (config.ini [bulletin]); wo waqt aane par din mein ek hi baar banta
    hai (bulletin_done_<area> nishan se).

    Bana hua bulletin FORCE_KEY se sabse aage lag jaata hai - tick_produce
    ise agli hi khali baari mein utha lega, bilkul /khabar jaisa.
    """
    try:
        import sy_bulletin
    except Exception as e:
        log("sy_bulletin load nahi hua:", e)
        return
    if not sy_bulletin.enabled():
        return
    for area in sy_bulletin.AREAS:
        if not sy_bulletin.due(area):
            continue
        try:
            sid = sy_bulletin.build(area)
        except Exception as e:
            log("bulletin (%s) banane mein gadbad:" % area, e)
            sy_bulletin.mark_done(area)   # aaj ke liye dobara koshish nahi
            continue
        sy_bulletin.mark_done(area)
        if sid:
            _force_add(sid)
        # Ek baari mein ek hi area - agla area agli baari (yahi loop
        # har ~20-60 second mein dobara chalta hai).
        return


def tick_report():
    """Reporter ki Google Form wali khabar (sy_report.py, REPORTER_FORM.md).

    Nayi line -> sampadak sirf form ki baat se script likhta hai -> khabar
    FORCE_KEY se sabse aage, bilkul /khabar jaisi: na ghadi ka intezaar,
    na din ki seema. Sheet ki har line mein uski haalat bhi yahin likhi
    jaati hai. [report] sheet_id khaali ho to ye kadam kuch nahi karta.
    """
    try:
        import sy_report
    except Exception as e:
        log("sy_report load nahi hua:", e)
        return
    for sid in sy_report.tick() or []:
        _force_add(sid)
        # Chunav ka lataka hua sandesh reporter ki khabar ko na roke.
        st.kv_set(OFFER_KEY, None)
        st.kv_set(OFFER_CHOSEN, None)


def tick_ingest():
    # Internet hi na ho to feeds tatolne ka koi matlab nahi - aur us khaali
    # koshish par ghadi chhap gayi to agli baari poore do ghante baad aati
    # hai. Paanch minute ki dikkat do ghante ka nuksaan nahi banni chahiye.
    if sy_telegram.offline():
        return

    # BAHUT PURANI KHABAR CHALEGI HI NAHI.
    #
    # Katar mein do-do din purani khabrein padi thi aur wo channel par
    # jaane wali thi. Ek news channel par ye sabse jaldi pakda jaane wala
    # dhabba hai. Yojana ispar se bahar hai - wo khabar nahi, jaankari hai.
    gone = st.expire_stale(cfg.num("schedule", "story_max_age_hours", 30))
    if gone:
        log("%d khabrein purani ho gayi thi - katar se hata di" % gone)

    # KATAR SE ZYADA MAT BHARO.
    #
    # Har do ghante mein 2-3 nayi khabrein aati thi, par video har paanch
    # ghante mein ek banti hai. Yaani roz lagbhag 24 aati thi aur 5 chalti
    # thi. Katar sirf lambi nahi hoti thi - wo BOODHI hoti jaati thi, aur
    # har us khabar par sampadak ka ek call ka paisa bhi lag chuka hota tha
    # jo kabhi chalne wali hi nahi thi.
    #
    # Isliye katar bhari ho to nayi khabar dhoondhne hi nahi jaate. Jaise
    # hi wo ghatti hai, agla run apne aap bhar deta hai.
    # Ye rok sirf KHABAR par hai. Yojana aur kaam ki baat ek-ek karke hi
    # aati hain (dono ka apna in-flight pehra hai) aur unka hi na aana us
    # roz ki mix bigaad deta hai - katar bhari hone par bhi unhe aane dena
    # chahiye, warna "roz ek kaam ki baat" ka niyam khaali reh jaata hai.
    cap = int(cfg.num("limits", "max_pending", 4))
    waiting = st.count_status("pending", "news") + st.count_status("pending", "local")
    news_min = cfg.num("schedule", "news_ingest_minutes", 120)

    if waiting >= cap:
        if st.due("news", news_min):
            log("katar mein pehle se %d khabrein hain - nayi nahi dhoondh rahe"
                % waiting)
    elif st.due("news", news_min):
        log("khabar dhoondh rahe hain")
        try:
            n = sy_ingest.run_news()
            log("nayi khabrein:", n)
            if not n and sy_telegram.offline():
                st.retry_soon("news", news_min)
        except Exception as e:
            log("khabar mein gadbad:", e)
            st.retry_soon("news", news_min)

    yoj_min = cfg.num("schedule", "yojana_ingest_minutes", 120)
    if st.due("yojana", yoj_min):
        log("yojana dhoondh rahe hain")
        try:
            n = sy_ingest.run_yojana()
            log("nayi yojana khabrein:", n)
        except Exception as e:
            log("yojana mein gadbad:", e)
            st.retry_soon("yojana", yoj_min)

    kaam_min = cfg.num("schedule", "kaam_ingest_minutes", 240)
    if st.due("kaam", kaam_min):
        log("kaam ki baat dhoondh rahe hain")
        try:
            n = sy_ingest.run_kaam()
            log("nayi kaam ki baat:", n)
        except Exception as e:
            log("kaam ki baat mein gadbad:", e)
            st.retry_soon("kaam", kaam_min)

    gyan_min = cfg.num("schedule", "gyan_ingest_minutes", 180)
    if st.due("gyan", gyan_min):
        log("gyan ki baat dhoondh rahe hain")
        try:
            n = sy_ingest.run_gyan()
            log("nayi gyan ki baat:", n)
        except Exception as e:
            log("gyan ki baat mein gadbad:", e)
            st.retry_soon("gyan", gyan_min)

    tech_min = cfg.num("schedule", "tech_ingest_minutes", 240)
    if st.due("tech", tech_min):
        log("tech ki baat dhoondh rahe hain")
        try:
            n = sy_ingest.run_tech()
            log("nayi tech ki baat:", n)
        except Exception as e:
            log("tech ki baat mein gadbad:", e)
            st.retry_soon("tech", tech_min)


def tidy_disk():
    """Jama hui files hata do - warna chhota server bhar jaata hai.

    Do cheezein jama hoti hain:

      work/<id>/  - har video ka kachcha saamaan: clip.mp4, har drishya ki
                    file, aawaaz, tukde. Ek video par 30-60 MB. Ye sirf
                    banate waqt chahiye; nikal jaane ke baad iska koi kaam
                    nahi.
      output/     - bani hui video aur thumbnail. Ye rakhne layak hai, par
                    hamesha ke liye nahi: roz 7 video ka matlab mahine mein
                    3 GB.

    Laptop par ye chalta raha kyunki disk badi hai. Server 40 GB ka hota
    hai - wahan ye kuch hi hafton mein bhar jaata, aur bharne par render
    beech mein toot-ta hai.
    """
    keep = int(cfg.num("schedule", "keep_output_days", 14))
    freed = 0

    # 1) Nikal chuki khabron ka kachcha saamaan - turant.
    for sid in st.done_ids():
        d = os.path.join(cfg.WORK_ROOT, sid)
        if os.path.isdir(d):
            try:
                freed += _dir_mb(d)
                shutil.rmtree(d, ignore_errors=True)
            except Exception:
                pass

    # 2) Purani bani hui video - keep din ke baad.
    if keep > 0 and os.path.isdir(cfg.OUTPUT_DIR):
        cut = time.time() - keep * 86400
        for f in os.listdir(cfg.OUTPUT_DIR):
            p = os.path.join(cfg.OUTPUT_DIR, f)
            try:
                if os.path.isfile(p) and os.path.getmtime(p) < cut:
                    freed += os.path.getsize(p) / (1024.0 * 1024.0)
                    os.remove(p)
            except Exception:
                pass

    if freed > 1:
        log("disk se %.0f MB khaali kiya" % freed)


def _dir_mb(d):
    tot = 0
    for root, _dirs, files in os.walk(d):
        for f in files:
            try:
                tot += os.path.getsize(os.path.join(root, f))
            except Exception:
                pass
    return tot / (1024.0 * 1024.0)


def produce_minutes():
    return cfg.num("schedule", "produce_minutes", 360)


def approval_wait_hours():
    return cfg.num("schedule", "approval_wait_hours", 6)


def release_stuck_approval():
    """Bina jawab wali video poore channel ko rok deti hai - use chhod do.

    "Ek waqt mein ek hi approval" niyam sahi hai. Par uska ek khatra bhi
    hai, aur wo saamne aa chuka hai: Telegram wala sandesh agar aapne
    dekha hi nahi, to agli video KABHI nahi banti. abhi.bat bhi chup rehta
    hai kyunki wo sirf ghadi peeche karta hai - aur rok ghadi ki nahi hai.

    Isliye ek seema. Utni der jawab na aaye to us video ko chhod kar aage
    badh jaate hain.

    Chhodna ka matlab 'expired' hai - publish NAHI. Bina aapke button
    dabaye channel par kuch bhi nahi jaata; wo niyam waisa ka waisa hai.
    Chup rehne ko "haan" maan lena us niyam ko todh dena hota.
    """
    hrs = approval_wait_hours()
    if hrs <= 0:
        return
    for r in st.by_status("awaiting"):
        if st.waiting_hours(r) < hrs:
            continue
        st.update(r["story_id"], status="expired",
                  error="approval ka jawab %.0f ghante tak nahi aaya" % hrs)
        log("bina jawab ki video chhod di:", str(r.get("headline_hi"))[:60])
        try:
            sy_telegram.send_message(
                "Is video par %.0f ghante tak koi jawab nahi aaya, isliye "
                "aage badh rahe hain. Ye publish NAHI hui.\n\n%s"
                % (hrs, str(r.get("headline_hi") or "")))
        except Exception:
            pass


# KHABAR AUR JAANKARI KA ANUPAT
#
# Paanch video mein ek khabar, chaar jaankari. Ye Harshvardhan ka faisla
# hai aur uski wajah saaf hai: jab tak ANI/PTI ka subscription nahi aata,
# sthaniya khabar ki apni footage milti hi nahi. Bhadohi ke saraafa bazaar
# ki koi licence wali tasveer duniya mein kahin nahi hai - jabki "Konark
# Sun Temple" ya "jahaz samudra mein raasta kaise khojte hain" par Commons
# par darjanon hain.
#
# Isliye khabar band nahi hoti - wo kam ho jaati hai, aur jo chalti hai wo
# wahi chalti hai jiska drishya sach mein maujood ho (visual_verdict us par
# ab zyada sakht hai). Baaki chaar jagah wo vishay lete hain jo kabhi
# purane nahi hote: sehat, career, padhai, yojana, kanooni madad, itihas,
# bhugol, aur "ye cheez kaam kaise karti hai".
KHABAR_BEATS = ("local", "news")
JAANKARI_BEATS = ("yojana", "kaam", "gyan", "tech")

# ---------------------------------------------------------------- Reel
#
# Do naye section, dono 9:16 Reel mein: bollywood aur viral.
#
# Ye baaki video ke UPAR chalte hain, unki jagah nahi lete - yahi
# Harshvardhan ka faisla tha. Isliye inki apni ghadi hai (reel_minutes),
# aur wo produce_minutes se alag chalti hai.
#
# Chunav ka niyam yahan bhi wahi hai: jab Reel ki baari aati hai to
# Telegram par Reel ke vishay jaate hain, aur aapke dabane ke BAAD hi lekh
# dhoondha jaata hai. Ek hi gate, ek hi katar - bas slate ka saamaan
# badal jaata hai.
REEL_BEATS = ("bolly", "viral")


def reel_minutes():
    return cfg.num("schedule", "reel_minutes", 720)


def reels_on():
    return int(cfg.num("schedule", "reels_per_day", 2)) > 0


def reel_due():
    """Kya abhi Reel ki baari hai? (ghadi chhapti NAHI hai - sirf poochhte hain)"""
    if not reels_on():
        return False
    if st.count_status("pending", "bolly") or st.count_status("pending", "viral"):
        return True          # pehle se ek Reel katar mein hai
    return st.due_in("reel", reel_minutes()) <= 0


def news_in_every():
    return int(cfg.num("schedule", "news_in_every", 5))


def _pick_jaankari():
    """Teen jaankari wale beat - baari-baari se, score se nahi.

    Sirf score dekhne par yojana HAMESHA jeet jaati: uska ank feed se aata
    hai aur 7 se upar hota hai, jabki kaam aur gyan dono 7 par baithe hain.
    Nateeja ye hota ki chaaron jaankari wali jagah yojana hi bhar leti aur
    itihas-bhugol kabhi chalte hi nahi.

    Isliye yahan ank nahi, BAARI dekhte hain: jo beat sabse der se channel
    par nahi gaya, uski baari pehle.
    """
    best = None
    for b in JAANKARI_BEATS:
        s = st.next_pending(b)
        if not s:
            continue
        gap = st.hours_since_published(b)
        if best is None or gap > best[0]:
            best = (gap, s)
    return best[1] if best else None


def _pick_by_mix():
    """Anupat ke hisab se agli video - khabar ya jaankari.

    Niyam ek line ka hai: pichhli (n-1) video mein khabar thi, to is baari
    khabar nahi. Utna hi.

    Ek zaroori chhoot: jaankari wala koi vishay katar mein hai hi nahi, to
    khaali baithne se achha khabar bana lete hain. Warna jis din gyan ke
    vishay khatam ho jaate, us din channel poora chup ho jaata - aur ek
    anupat ke chakkar mein chup ho jaana anupat todne se bura hai.
    """
    n = news_in_every()
    recent = st.recent_beats(max(1, n - 1)) if n > 1 else []
    khabar_turn = not any(b in KHABAR_BEATS for b in recent)

    # Reel yahan se kabhi nahi uthti - uski apni ghadi hai (upar dekhiye).
    SKIP = KHABAR_BEATS + REEL_BEATS

    if khabar_turn:
        story = st.next_pending("local") or st.next_pending("news")
        if story:
            log("is baari khabar ki jagah (paanch mein ek)")
            return story
        return _pick_jaankari()

    story = _pick_jaankari()
    if story:
        return story

    story = (st.next_pending(exclude=SKIP)
             or st.next_pending(exclude=REEL_BEATS))
    if story and str(story.get("beat")) in KHABAR_BEATS:
        log("jaankari wala koi vishay katar mein nahi - is baari khabar hi")
    return story


# ------------------------------------------------------- vishay ka chunav
#
# DOOSRA INSAANI GATE - AUR YE PEHLE WALE SE ZYADA ZAROORI HAI
#
# Ab tak ek hi jagah insaan beech mein aata tha: video ban jaane ke BAAD,
# publish se pehle. Wo gate zaroori hai par wo der se aata hai - us waqt
# tak sampadak ka call, aawaaz, drishya aur render, sab ka kharch ho chuka
# hota hai. Reject ka matlab hota tha: poora kharch, shoonya nateeja.
#
# Ye doosra gate shuruaat mein hai. Program pehle poochhta hai "banayein
# kis par?" - paanch vikalp, har ek par ek button - aur aapke dabaane ke
# BAAD hi lekh dhoondhta hai aur script likhta hai. Isliye jo khabar chalni
# hi nahi, uspar ek paisa nahi lagta.
#
# Vikalp kahan se: khabar ke do vikalp us baat se aate hain jo Bharat mein
# abhi sabse zyada khoji (Google) aur dekhi (YouTube) ja rahi hai - sy_trend
# dekhiye. Baaki teen apni chuni hui suchi se: yojana, kaam ki baat, gyan.
#
# Jawab na aaye to kaam rukta nahi. Utni der baad program apne aap anupat
# wale purane niyam se chun kar aage badh jaata hai - ek chunav ke intezaar
# mein channel ka chup ho jaana chunav se bura hai.
OFFER_KEY = "offer"


def offer_wait_minutes():
    return cfg.num("schedule", "offer_wait_minutes", 45)


def _reel_slate():
    """Reel ke vikalp - do bollywood, do viral."""
    items = []
    for kind, label in (("bolly", "bollywood"), ("viral", "viral")):
        try:
            for t in sy_trend.topics_for(kind, want=2):
                items.append({
                    "kind": kind, "key": t["term"],
                    "links": (t.get("links") or [])[:6],
                    "label": t["term"], "button": t["term"],
                    "tag": "Reel · " + label + " · " + t["signal"]
                           + ((" · " + t["where"]) if t.get("where") else ""),
                })
        except Exception as e:
            log("%s ke vishay nahi mile: %s" % (kind, e))
    return items[:5]


def _slate_items():
    """Telegram par kya-kya vikalp bhejein. [{kind,key,label,button,tag}]"""
    if reel_due():
        items = _reel_slate()
        if items:
            return items
        log("Reel ke vishay nahi mile - aam vikalp bhej rahe hain")

    items = []
    want = int(cfg.num("schedule", "slate_news", 3))
    try:
        for t in sy_trend.news_topics(want=want):
            items.append({
                "kind": "trend", "key": t["term"],
                "links": (t.get("links") or [])[:6],
                "label": t["term"],
                "button": t["term"],
                # Akhbaar ka naam bhi - taaki dabane se PEHLE dikh jaye ki
                # khabar kahan ki hai. Pehli raat mein "alex meret" chuna
                # gaya aur uska lekh bundesliga.com par nikla; wo baat
                # button par dikhni chahiye thi.
                "tag": "khabar · " + t["signal"]
                       + ((" · " + t["where"]) if t.get("where") else "")
                       + ((" · " + t["note"]) if t.get("note") else ""),
            })
    except Exception as e:
        log("trending vishay nahi mile:", e)

    # Jaankari wale vishay - apni chuni hui suchi se, baari ke kram mein.
    for kind, fn in (("kaam", sy_ingest.next_kaam), ("gyan", sy_ingest.next_gyan),
                     ("tech", sy_ingest.next_tech)):
        try:
            c = fn()
        except Exception as e:
            log("%s ka vishay nahi mila: %s" % (kind, e))
            continue
        if not c:
            continue
        items.append({"kind": kind, "key": c["slug"], "links": [],
                      "label": c["title"], "button": c["title"],
                      "tag": "jaankari · " + c.get("topic", "")})

    # Katar mein pehle se koi taiyar khabar ho to wo bhi ek vikalp hai -
    # uspar kharch ho hi chuka hai, use bekaar jaane dena bewakoofi hai.
    for s in (st.by_status("pending") or [])[:2]:
        items.append({"kind": "ready", "key": s["story_id"], "links": [],
                      "label": str(s.get("headline_hi") or ""),
                      "button": str(s.get("headline_hi") or ""),
                      "tag": "taiyar · " + str(s.get("beat") or "")})
    return items[:5]


OFFER_AT_KEY = "offer_last_at"

# CHUNA HUA VISHAY BANNE KA INTEZAAR KAR RAHA HAI
#
# Pehli raat mein aapne "alex meret" chuna, khabar katar mein aa bhi gayi -
# aur video phir bhi nahi bani. Uski jagah 45 second baad naya slate chala
# gaya.
#
# Wajah kram thi. Chakkar mein tick_offer, tick_produce se PEHLE chalta
# hai. Chunav ke baad maine ghadi shoonya kar di thi ("ab agli baari
# abhi"), to agle hi chakkar mein tick_offer ne dekha "video ki baari hai,
# koi chunav lataka hua nahi hai" aur naya slate bhej diya - aur uske
# lagte hi tick_produce khud ko rok leta hai.
#
# Yaani chuni hui khabar hamesha agle slate ke neeche dab jaati thi.
#
# Ilaaj ek nishan hai: chunav safal hote hi ye lag jaata hai, tick_offer
# tab tak chup rehta hai, aur tick_produce us khabar ko bana kar ise hata
# deta hai.
OFFER_CHOSEN = "offer_chosen"


def offer_gap_minutes():
    return cfg.num("schedule", "offer_min_gap_minutes", 10)


def tick_offer():
    """Vishay ke vikalp Telegram par bhejo - agar abhi bhejne ka waqt hai."""
    if st.count_status("producing") or st.count_status("awaiting"):
        return

    # KATAR MEIN PEHLE SE KAAM HAI TO NAYA VIKALP MAT POOCHHIYE.
    #
    # Pehle ye jaanch yahan nahi thi. Nateeja: restart karne par (ya kabhi
    # bhi jab "produce" ki ghadi due ho jaaye) ye pehle se katar mein padi
    # pending khabron ko chhod kar Telegram par 5 NAYE vikalp bhej deta
    # tha - jabki tick_produce inhi purani khabron ko turant bana sakta
    # tha. Vikalp aur pending queue dono ek hi "produce" ghadi share
    # karte hain, aur is loop mein tick_offer, tick_produce se PEHLE
    # chalta hai - isliye offer hamesha pehle jeet jaata tha, chahe katar
    # khaali ho ya bhari.
    #
    # Ab: katar mein kuch pending ho (chahe khabar ho, kaam-gyan-yojana ho
    # ya Reel) to naya vikalp poochhna ruk jaata hai - tick_produce use
    # pehle nipta dega. Naya vikalp tabhi jaata hai jab sach mein katar
    # khaali ho.
    if st.count_status("pending"):
        return

    # SAARI ROK PEHLE, GHADI SABSE AAKHIR MEIN - AUR YE EK ASLI KEEDA THA
    #
    # st.due() sirf poochhta nahi hai, wo samay CHHAAP bhi deta hai: ek
    # baar True kehne ke baad agli baari poore chhah ghante baad aati hai.
    #
    # Pehle yahan due() upar tha aur uske NEECHE ye jaanch thi ki koi
    # chunav lataka hua hai ya nahi. Nateeja: latke hue chunav ke dauran
    # bhi due() chalta rehta tha, har baar ghadi chhap jaati thi, aur
    # video ki baari chup-chaap khatam ho jaati thi - kuch bane bina.
    #
    # Isi wajah se abhi.bat "kaam karna band" kar deta tha: wo ghadi
    # shoonya karta, agle 20 second mein due() use kha jaata, aur phir
    # chhah ghante kuch nahi hota.
    #
    # Isliye ab: pehle har rok, aur ghadi sabse aakhir mein - taaki wo
    # tabhi chhape jab sach mein slate ja raha ho.
    if st.kv_get(OFFER_KEY):
        return                       # ek chunav pehle se lataka hua hai
    if st.kv_get(OFFER_CHOSEN):
        return                       # chuna hua vishay banne ka intezaar kar raha hai

    # DO SLATE KE BEECH KAM SE KAM ITNA ANTAR - AUR YE EK ASLI GALTI KA ILAAJ HAI
    #
    # Pehli raat ke log mein ye saaf dikha: har 40 second par "5 vikalp
    # Telegram par bheje". Wajah ye thi ki chuna hua vishay fail hone par
    # main ghadi shoonya kar deta tha ("ab agli baari abhi"), aur agli baari
    # par turant naya slate chala jaata tha. Teen vishay lagatar fail hue to
    # teen minute mein chaar slate ja chuke the.
    #
    # Do nuksaan the: aapke Telegram par bauchhar, aur har slate par Google
    # Trends + YouTube dono ko ek-ek call - yaani unke rate-limit ki taraf
    # seedhi daud.
    last = float(st.kv_get(OFFER_AT_KEY, 0) or 0)
    gap = offer_gap_minutes()
    if last and time.time() - last < gap * 60:
        return

    if not st.due("produce", produce_minutes()):
        return

    items = _slate_items()
    if not items:
        return
    sid = "%x" % (int(time.time()) & 0xffffff)
    for it in items:
        it["slate"] = sid
    try:
        mid = sy_telegram.send_choices(
            items, "Jawab na aaye to %d minute baad program khud chun lega."
            % int(offer_wait_minutes()))
    except Exception as e:
        log("vikalp nahi bhej paye:", e)
        return
    st.kv_set(OFFER_KEY, {"id": sid, "at": time.time(), "mid": mid,
                          "items": items})
    st.kv_set(OFFER_AT_KEY, time.time())
    log("%d vikalp Telegram par bheje" % len(items))


def take_offer(slate_id, index):
    """Chune hue vishay par kaam shuru karo. True agar kuch ban gaya."""
    off = st.kv_get(OFFER_KEY) or {}
    if not off or str(off.get("id")) != str(slate_id):
        # Ek hi button do-teen baar dab gaya (pehli raat mein yahi hua -
        # kaam shuru hone mein kuch second lagte hain aur screen par kuch
        # nahi badalta, isliye aadmi dobara dabata hai). Pehli dab par kaam
        # shuru ho chuka hai; baaki ko chup-chaap chhod dena hi theek hai.
        return False
    items = off.get("items") or []
    try:
        it = items[int(index)]
    except Exception:
        return False
    st.kv_set(OFFER_KEY, None)

    kind = it.get("kind")
    log("aapne chuna:", str(it.get("label"))[:60], "(%s)" % kind)
    if _build(it):
        return True

    # AAPKA TAP BEKAAR NA JAYE.
    #
    # Pehli raat mein teen baar aisa hua: aapne vishay chuna aur uska
    # sarkari safha khula hi nahi (jan_dhan aur bank_shikayat par lekh
    # khaali, aadhaar_update par 404). Har baar aapki mehnat bekaar gayi
    # aur ek naya slate chala gaya.
    #
    # Wo galti chunav ki nahi thi - ek mara hua link tha. Aisi haalat mein
    # aapse dobara poochhna galat hai: usi kism ka agla vishay khud utha
    # lena chahiye. Chunav aapka rehta hai; sirf toota hua link hum khud
    # badal lete hain.
    nxt = None
    try:
        if kind == "kaam":
            nxt = sy_ingest.run_kaam()
        elif kind == "gyan":
            nxt = sy_ingest.run_gyan()
        elif kind == "tech":
            nxt = sy_ingest.run_tech()
        elif kind in REEL_BEATS:
            for t in sy_trend.topics_for(kind, want=3):
                if t["term"] == it.get("key"):
                    continue
                if _build({"kind": kind, "key": t["term"],
                           "links": t.get("links") or []}):
                    nxt = 1
                    break
        elif kind == "trend":
            for t in sy_trend.news_topics(want=3):
                if t["term"] == it.get("key"):
                    continue
                if _build({"kind": "trend", "key": t["term"],
                           "links": t.get("links") or []}):
                    nxt = 1
                    break
    except Exception as e:
        log("agla vishay bhi nahi bana:", e)

    if nxt:
        log("us vishay ka safha nahi khula - usi kism ka agla vishay le liya")
        try:
            sy_telegram.send_message(
                "Aapke chune hue vishay ka safha nahi khula (link toota hua "
                "hai). Usi kism ka agla vishay le liya hai - video usi par "
                "banegi.")
        except Exception:
            pass
        return True
    return False


def _build(it):
    """Ek vishay par khabar bana do. True/False."""
    kind = it.get("kind")
    try:
        if kind == "ready":
            return bool(st.get(it["key"]))
        if kind == "trend":
            sy_trend.mark_used(it["key"])
            links = it.get("links") or sy_trend.search_links(it["key"])
            sid = "tr_%s" % re.sub(r"[^a-z0-9]+", "", it["key"].lower())[:24]
            return bool(sy_ingest.story_from_links(
                sid, it["key"], links, scope="national", score=16))
        if kind == "kaam":
            return bool(sy_ingest.run_kaam(it["key"]))
        if kind == "gyan":
            return bool(sy_ingest.run_gyan(it["key"]))
        if kind == "tech":
            return bool(sy_ingest.run_tech(it["key"]))
        if kind in REEL_BEATS:
            sy_trend.mark_used(it["key"])
            return bool(sy_ingest.run_reel(kind, it["key"],
                                           it.get("links") or []))
    except Exception as e:
        log("chune hue vishay par kaam nahi hua:", e)
    return False


def release_stuck_offer():
    """Chunav ka jawab na aaye to apne aap aage badho."""
    off = st.kv_get(OFFER_KEY)
    if not off:
        return
    wait = offer_wait_minutes()
    if wait <= 0:
        return
    if time.time() - float(off.get("at") or 0) < wait * 60:
        return
    st.kv_set(OFFER_KEY, None)
    log("chunav ka jawab nahi aaya - purane niyam se khud chun rahe hain")
    try:
        sy_telegram.send_message(
            "Vishay ka jawab %d minute tak nahi aaya, isliye program khud "
            "chun kar aage badh raha hai." % int(wait))
    except Exception:
        pass


def tick_produce():
    # Ek baar mein ek hi. Do video ek saath banane se PC bhi bhar jaata hai
    # aur Telegram par bhi ek saath do approval aa jaate hain.
    release_stuck_approval()
    release_stuck_offer()
    # Chunav lataka hua hai to abhi kuch nahi banta - jawab ka intezaar.
    if st.kv_get(OFFER_KEY):
        return
    if st.count_status("producing") or st.count_status("awaiting"):
        return

    # AAPKA MANGA HUA VISHAY - SABSE UPAR, GHADI KA INTEZAAR NAHI.
    #
    # Ye jaan-boojhkar Reel se bhi upar hai aur produce wali ghadi se bhi.
    # Wajah seedhi hai: aapne ye vishay tab manga jab wo chal raha tha.
    # Chhah ghante baad wo khabar nahi, purani baat hoti hai. Machine ki
    # ghadi apni jagah sahi hai - par insaan ki maang uska intezaar nahi
    # kar sakti.
    #
    # Ye upload ki din bhar wali seema ko nahi todta (max_uploads_per_day),
    # isliye maang-maang kar channel par bhaar nahi pad sakta.
    while True:
        sid = _force_pop()
        if not sid:
            break
        story = st.get(sid)
        if not story or story.get("status") != "pending":
            # Ban chuki, ya kisi aur raste se ja chuki. Agli dekh lete hain.
            continue
        log("aapka manga hua vishay bana rahe hain:", sid,
            "-", str(story.get("headline_hi"))[:60])
        st.kv_set(OFFER_CHOSEN, None)
        if not sy_produce.produce(story):
            # Bani nahi - par ise wapas katar mein mat daaliye, warna wahi
            # nakaam vishay har baari ko khata rahega. Wo ab bhi 'pending'
            # hai aur score 20 ke saath aam katar mein apni baari le lega.
            log("aapka vishay is baar nahi ban paya:", sid)
        return

    # SEEMA AB YAHAN HAI - BANANE SE PEHLE, UPLOAD HONE SE PEHLE NAHI.
    #
    # Upar wala FORCE_KEY wala hissa (manga hua vishay, bulletin) is jaanch
    # se PEHLE hai, isliye wo dono kabhi nahi rukte. Neeche Reel aur aam
    # khabar/kaam - dono ghadi-anusaar chalte hain, aur inhi par ye seema
    # lagti hai (production_allowed() mein poori wajah likhi hai).
    ok, why = production_allowed()
    if not ok:
        return

    # REEL APNI GHADI PAR - BAAKI VIDEO KI JAGAH NAHI LETI.
    #
    # Ye jaanch produce wali ghadi se PEHLE hai, aur jaan-boojhkar: Reel
    # roz do banni hain, baaki video ke UPAR. Agar ye neeche hoti to Reel
    # us 6-ghante wali baari ko kha jaati aur us din ki khabar ya jaankari
    # ek kam ho jaati.
    if reels_on():
        reel = st.next_pending("bolly") or st.next_pending("viral")
        if reel and st.due("reel", reel_minutes()):
            log("Reel bana rahe hain:", reel["story_id"],
                "-", str(reel.get("headline_hi"))[:55])
            st.kv_set(OFFER_CHOSEN, None)
            if not sy_produce.produce(reel):
                st.retry_soon("reel", reel_minutes(), 10)
            return

    if not st.due("produce", produce_minutes()):
        return
    # ROZ KAM SE KAM EK "KAAM KI BAAT".
    #
    # Bina is niyam ke wo kabhi chalti hi nahi. Khabar ka score hamesha
    # zyada hota hai (16 banaam 7), isliye ranking mein wo har baar peeche
    # rehti - aur channel par sirf khabar hi jaati, jo do din baad bekaar
    # ho jaati hai. Yahi wo cheez hai jo channel par jama hoti hai: mahine
    # baad bhi utni hi kaam ki, aur wahi log apne ghar ke group mein
    # bhejte hain.
    #
    # Isliye din mein ek baari uske naam pakki hai. Baaki din khabar apne
    # aap aage rehti hai.
    story = None
    if st.hours_since_published("kaam") >= 24:
        story = st.next_pending("kaam")
        if story:
            log("aaj ki kaam ki baat ki baari")

    if story is None:
        story = _pick_by_mix()
    if not story:
        return
    log("video bana rahe hain:", story["story_id"],
        "-", str(story.get("headline_hi"))[:60])
    # Chunav ka nishan yahin hat jaata hai - us par kaam shuru ho chuka.
    st.kv_set(OFFER_CHOSEN, None)
    if not sy_produce.produce(story):
        # Bani hi nahi - to ghadi khaali gayi. Poore chhah ghante baithne
        # ka koi matlab nahi; das minute mein agli khabar aazma lete hain.
        # (Turant nahi - agar kharabi bani hui hai to har 20 second par
        # wahi koshish paisa aur kagaz dono jalati hai.)
        st.retry_soon("produce", produce_minutes(), 10)


def tick_decisions():
    for sid, verdict, cb_id, message in sy_telegram.poll_decisions():
        # REJECT KI WAJAH ka button - video par faisla nahi, sirf darj karna.
        if verdict == "fb":
            try:
                import sy_feedback
                sy_feedback.on_button(sid, cb_id, message)
            except Exception as e:
                log("feedback darj nahi hua:", e)
            continue
        # VISHAY KA CHUNAV - ye video par faisla nahi hai, isliye pehle.
        # Yahan sid ka roop "slate:index" hai, koi story_id nahi.
        if verdict in ("pk", "sk"):
            slate, _, idx = str(sid).partition(":")
            if verdict == "sk":
                st.kv_set(OFFER_KEY, None)
                # Naye vikalp turant nahi - antar ka niyam yahan bhi lagta
                # hai, warna "koi nahi" dabate hi wahi bauchhar phir shuru.
                st.kv_set(OFFER_AT_KEY, time.time())
                st.retry_soon("produce", produce_minutes(), 0)
                sy_telegram.acknowledge(cb_id, message, "Theek hai, thodi der mein naye vikalp")
                log("aapne koi vishay nahi chuna - %d minute baad naye vikalp"
                    % int(offer_gap_minutes()))
                continue
            sy_telegram.acknowledge(cb_id, message, "Theek hai - ispar kaam shuru")
            if take_offer(slate, idx or "0"):
                # Ghadi wahin reset, taaki chuni hui khabar isi chakkar mein
                # bane - aapke button aur video ke beech koi intezaar nahi.
                # Aur nishan laga do, warna agla slate isse pehle nikal
                # jayega (upar OFFER_CHOSEN dekhiye).
                st.kv_set(OFFER_CHOSEN, 1)
                st.retry_soon("produce", produce_minutes(), 0)
            else:
                # Chuna hua bhi fail, uski jagah wala bhi. Ab turant naya
                # slate mat bhejo - wahi bauchhar wali galti hai.
                sy_telegram.send_message(
                    "Is vishay par kaam ka lekh nahi mila, aur usi kism ka "
                    "agla vishay bhi nahi khula. Thodi der mein naye vikalp "
                    "bhejte hain.")
                st.kv_set(OFFER_AT_KEY, time.time())
                st.retry_soon("produce", produce_minutes(), 0)
            continue

        story = st.get(sid)
        if not story:
            continue
        if story.get("status") != "awaiting":
            # Button dobara daba diya gaya. Chup-chaap chhod dete hain -
            # warna wahi video do baar chadh jaayegi.
            sy_telegram.acknowledge(cb_id, message, "Ispar faisla ho chuka hai")
            continue
        if verdict == "no":
            st.update(sid, status="rejected")
            # AAP NE MANA KIYA - TO AGLI ABHI BANEGI, INTEZAAR NAHI.
            #
            # Ghadi us video par kharch ho chuki thi jise aapne rakha hi
            # nahi. Uske baad agli baari poore chhah ghante baad aati thi -
            # yaani aapke ek "nahi" ki keemat aadha din. Wo galat hai:
            # reject ka matlab hai "ye nahi, doosri dikhaao", intezaar
            # nahi. Ab ghadi wahin reset ho jaati hai aur isi chakkar mein
            # agli khabar uthti hai (tick_produce isi ke baad chalta hai).
            #
            # Approve par aisa NAHI hota - wahan ghadi apna kaam kar chuki
            # hoti hai, aur wahi rok din bhar ka pacing sambhaalti hai.
            st.retry_soon("produce", produce_minutes(), 0)
            sy_telegram.acknowledge(cb_id, message,
                                    "Theek hai, ye nahi jayegi - agli banate hain")
            log("reject:", sid, "- agli khabar abhi uthate hain")
            # Ab poochho KYUN - aur video ka poora sandarbh darj karo, taaki
            # Claude wahi galti code mein pakad kar theek kare (sy_feedback).
            try:
                import sy_feedback
                sy_feedback.record_reject(story)
                sy_feedback.ask(story)
            except Exception as e:
                log("wajah poochhne mein gadbad:", e)
        else:
            st.update(sid, status="approved")
            sy_telegram.acknowledge(cb_id, message, "Theek hai, upload ki baari par")
            log("approve:", sid)


# AAPKE APNE MANGE HUE VISHAY KI KATAR.
#
# Ye us kami ka ilaaj hai jo asli hai: machine wahi vishay uthati hai jo
# Google Trends aur YouTube ki suchi mein upar hai, aur wo suchi manoranjan
# ki taraf jhukti hai. Jo baat sach mein bhaari hai - maan lijiye BRICS -
# wo us suchi mein upar aaye, ye zaroori nahi. Insaan ye pehchaan machine
# se behtar karta hai, aur ab uske paas kahne ka rasta hai.
FORCE_KEY = "force_next"


def _force_add(sid):
    cur = [x for x in str(st.kv_get(FORCE_KEY, "") or "").split(",") if x]
    if sid not in cur:
        cur.append(sid)
    # Dus se zyada jama karne ka matlab nahi - utni to ek din mein banti
    # hi nahi, aur purani maang tab tak basi ho chuki hogi.
    st.kv_set(FORCE_KEY, ",".join(cur[:10]))


def _force_pop():
    cur = [x for x in str(st.kv_get(FORCE_KEY, "") or "").split(",") if x]
    if not cur:
        return ""
    sid = cur.pop(0)
    st.kv_set(FORCE_KEY, ",".join(cur))
    return sid


def do_khabar(term):
    """/khabar <vishay> - aapke kahe hue vishay par khabar banao.

    Kram ULTA hai aur yahi iski taakat hai: vishay aapne tay kiya, lekh ab
    dhoondha jayega. Machine ki apni pasand beech mein aati hi nahi.

    Ek baat jo yahan jaan-boojhkar NAHI hai: sampadak ka pehra hata nahi
    hai. Aapka manga hua vishay bhi usi jaanch se guzarta hai - lekh na
    khule ya baat sirf afwaah nikle to wo ruk jayega, aur aapko wajah mil
    jayegi. "Aapne kaha hai" kisi khabar ko sachchi nahi bana deta, aur
    channel ki sabse badi poonji uska bharosa hai.
    """
    term = str(term or "").strip()
    if len(term) < 4:
        sy_telegram.send_message(
            "Vishay bhi likh dijiye. Jaise:\n"
            "<code>/khabar BRICS shikhar sammelan Bharat</code>")
        return

    sy_telegram.send_message(
        "<b>" + sy_telegram._esc(term) + "</b>\n\n"
        "Ispar taaze lekh dhoondh raha hoon.\n\n"
        "Do se paanch minute lag sakte hain. Suchkaank jaldi-jaldi "
        "poochhne par saans maangta hai, aur program uska intezaar karta "
        "hai - ye rukna jaan-boojhkar hai.")
    log("aapka manga hua vishay:", term)

    try:
        links = sy_trend.search_links(term)
    except Exception as e:
        log("khoj nahi chali:", e)
        links = []

    # ROMAN HINDI KA SAWAAL.
    #
    # Aap saheb ki tarah likhte hain: "brics sammelan me putin ka bayan".
    # Suchkaank aise shabd nahi jaanta - wo khabrein ya to angrezi mein
    # rakhta hai ya Devanagari mein, Roman Hindi mein nahi. Isliye khaali
    # haath lautne par ek baar aur, angrezi shabdon ke saath.
    #
    # Ye call sirf tab lagti hai jab pehli khoj khaali gayi - yaani
    # kharch nakaami par hi hota hai, har baar nahi.
    if not links:
        try:
            better = sy_ai.ask(
                "Aap ek news researcher hain. Aapko ek vishay diya jayega, "
                "sambhavtah Roman Hindi mein. Uske liye ek chhoti ANGREZI "
                "news search query likhiye - 3 se 7 shabd, sirf query, "
                "aur kuch nahi. Koi quote, koi viram, koi vyakhya nahi.",
                term, max_tokens=60).strip().strip('"').strip()
        except Exception as e:
            log("angrezi mein badalna nahi hua:", e)
            better = ""
        if better and better.lower() != term.lower():
            log("angrezi mein: %s" % better)
            try:
                links = sy_trend.search_links(better)
            except Exception as e:
                log("doosri khoj nahi chali:", e)
            if links:
                term = better

    if not links:
        sy_telegram.send_message(
            "Is vishay par koi taaza lekh nahi mila.\n\n"
            "Do-teen shabd badal kar dekhiye - naam, jagah ya ghatna "
            "jodkar. Angrezi ke shabd ab bhi sabse achhe chalte hain.")
        return

    sid = "mera_" + re.sub(r"[^a-z0-9]+", "", term.lower())[:22]
    sid = sid + "_" + str(int(time.time()))[-5:]
    try:
        # score 20 - khabar ke aam 16 se upar. Isse ye katar mein bhi
        # peeche nahi padti agar force wali baari kisi wajah se chhoot jaye.
        made = sy_ingest.story_from_links(
            sid, term, links, scope="national", score=20, forced=True)
    except Exception as e:
        log("banane mein gadbad:", e)
        sy_telegram.send_message(
            "Ispar kaam karte waqt gadbad ho gayi.\n\n<pre>"
            + sy_telegram._esc(str(e))[:500] + "</pre>")
        return

    if not made:
        why = sy_ingest.last_kill_reason or "log mein dekhiye"
        sy_telegram.send_message(
            "Ye vishay chhodna pada.\n\n<b>Wajah:</b> "
            + sy_telegram._esc(why)[:500]
            + "\n\nAapke maange vishay ko ahmiyat ke naam par nahi roka "
              "jaata - sirf tab jab lekh na khule ya baat pakki na ho. "
              "Doosre shabdon ya angrezi mein dobara /khabar bhej kar "
              "dekhiye.")
        return

    row = st.get(made) or {}
    _force_add(made)
    # Chunav ka lataka hua sandesh hata dete hain - warna tick_produce
    # uske jawab ka intezaar karta rehta aur aapki maangi hui khabar wahin
    # khadi rehti.
    st.kv_set(OFFER_KEY, None)
    st.kv_set(OFFER_CHOSEN, None)
    sy_telegram.send_message(
        "<b>Ban gayi - ab video ki baari.</b>\n\n"
        + sy_telegram._esc(str(row.get("headline_hi") or term))
        + "\n\nVideo banne ke baad hamesha ki tarah approval ka sandesh "
          "aayega.")


def do_veo(rest):
    """/veo on | /veo off | /veo - AI drishya ka switch, phone se.

    Ye config.ini se upar chalta hai, aur wo jaan-boojhkar hai: ispar paisa
    lagta hai, aur paisa rokne ka button hamesha haath ke paas hona chahiye.
    """
    import sy_veo
    want = str(rest or "").strip().lower()

    if want in ("on", "chalu", "1", "haan"):
        sy_veo.set_enabled(True)
        log("veo chalu")
    elif want in ("off", "band", "0", "nahi"):
        sy_veo.set_enabled(False)
        log("veo band")
    elif want:
        sy_telegram.send_message(
            "Samajh nahi aaya. <code>/veo on</code> ya <code>/veo off</code> "
            "likhiye, ya sirf <code>/veo</code> haal dekhne ke liye.")
        return

    on = sy_veo.enabled()
    msg = ["<b>AI drishya (Veo): %s</b>" % ("CHALU" if on else "BAND")]
    if on:
        msg.append("")
        msg.append("Aaj bani: %d / %d clip"
                   % (sy_veo.used_today(), sy_veo.max_per_day()))
        msg.append("Model: <code>%s</code>, %d second, %s"
                   % (sy_veo.model(), sy_veo.seconds(), sy_veo.resolution()))
        msg.append("")
        msg.append("Sirf gyan, kaam ki baat aur yojana par - aur wahi tab, "
                   "jab us tukde par muft srot mein kuch bhi na mile. "
                   "Khabar par kabhi nahi.")
    else:
        msg.append("")
        msg.append("Chalu karne ke liye: <code>/veo on</code>")
    sy_telegram.send_message("\n".join(msg))


def do_anchor(rest):
    """/anchor on | off | test - AI anchor (bulletin intro/outro) ka switch.

    /anchor test kisi bulletin ka intezaar kiye bina, ABHI, anchor ki
    tasveer aur ek chhota namune ka clip Telegram par bhej deta hai -
    taaki chehra aur aawaaz dekh/sun kar tasalli ho jaaye, poora bulletin
    banwaye bina.
    """
    import sy_anchor
    want = str(rest or "").strip().lower()

    if want in ("on", "chalu", "1", "haan"):
        sy_anchor.set_enabled(True)
        log("anchor chalu")
        want = ""
    elif want in ("off", "band", "0", "nahi"):
        sy_anchor.set_enabled(False)
        log("anchor band")
        want = ""
    elif want in ("test", "jhalak", "dekho"):
        sy_telegram.send_message("Anchor ki tasveer/clip taiyar kar raha "
                                 "hoon - ismein 2-3 minute lag sakte hain...")
        ok, why = sy_anchor.ensure_reference()
        if not ok:
            sy_telegram.send_message("Reference tasveer nahi bani: %s"
                                     % sy_telegram._esc(why))
            return
        try:
            sy_telegram.send_photo(sy_anchor.reference_path(),
                                   caption="Anchor ki tasveer - bulletin "
                                           "mein aisa hi dikhega")
        except Exception as e:
            log("reference tasveer bhejne mein gadbad:", e)
        out = os.path.join(cfg.OUTPUT_DIR, "anchor_test.mp4")
        ok, why = sy_anchor._clip_for_line(
            "नमस्कार, मैं आपका AI समाचार एंकर हूँ।", out)
        if not ok:
            sy_telegram.send_message("Test clip nahi bani: %s"
                                     % sy_telegram._esc(why))
            return
        try:
            sy_telegram.send_video_file(out, caption="Anchor test clip - "
                                                      "aawaaz bhi sunkar "
                                                      "dekhiye")
        except Exception as e:
            sy_telegram.send_message("Clip bani, par bhej nahi paya: %s"
                                     % sy_telegram._esc(str(e)))
        return
    elif want:
        sy_telegram.send_message(
            "<code>/anchor on</code>, <code>/anchor off</code>, ya "
            "abhi ki jhalak dekhne ke liye <code>/anchor test</code> "
            "likhiye.")
        return

    on = sy_anchor.enabled()
    msg = ["<b>AI anchor (bulletin intro/outro): %s</b>"
           % ("CHALU" if on else "BAND")]
    msg.append("")
    if on:
        msg.append("Aaj bana: %d / %d clip"
                   % (sy_anchor.used_today(), sy_anchor.max_per_day()))
        msg.append("Reference tasveer: %s" % (
            "bani hui hai" if os.path.exists(sy_anchor.reference_path())
            else "abhi nahi bani - pehle bulletin ya /anchor test par banegi"))
        msg.append("")
        msg.append("Sirf bulletin ke intro/outro par lagta hai, poori "
                   "video par nahi. Turant jhalak: <code>/anchor test</code>")
    else:
        msg.append("Chalu karne ke liye: <code>/anchor on</code>")
        msg.append("Bina chalu kiye bhi jhalak dekhne ke liye: "
                   "<code>/anchor test</code>")
    sy_telegram.send_message("\n".join(msg))


def do_social(rest):
    """/social on | /social off | /social - Facebook aur Instagram ka switch."""
    import sy_social
    want = str(rest or "").strip().lower()
    if want in ("on", "chalu", "1", "haan"):
        sy_social.set_enabled(True)
        log("social chalu")
    elif want in ("off", "band", "0", "nahi"):
        sy_social.set_enabled(False)
        log("social band")
    elif want:
        sy_telegram.send_message(
            "<code>/social on</code> ya <code>/social off</code> likhiye.")
        return

    on = sy_social.enabled()
    msg = ["<b>Facebook aur Instagram: %s</b>" % ("CHALU" if on else "BAND")]
    msg.append("")
    msg.append("Facebook Page: %s" % ("taiyar" if sy_social.fb_on()
                                      else "page id ya token nahi hai"))
    msg.append("Instagram: %s" % ("taiyar" if sy_social.ig_on()
                                  else "user id ya token nahi hai"))
    if sy_social.ig_on() and not sy_social.bucket():
        msg.append("  (par GCS bucket nahi diya - Instagram ke bina uske "
                   "nahi chalega)")
    msg.append("")
    msg.append("Ye YouTube par chadhne ke BAAD chalta hai. Instagram par "
               "sirf Reel jaati hai - 16:9 wali khabar wahan kat jaati hai.")
    if not on:
        msg.append("")
        msg.append("Chalu karne ke liye: <code>/social on</code>")
    sy_telegram.send_message("\n".join(msg))


def do_bulletin(rest):
    """/bulletin on | off | mirzapur | prayagraj | up - बुलेटिन ka switch.

    on/off poore feature ka master switch hai (config.ini [bulletin] se
    upar). Area ka naam dete hi (/bulletin mirzapur) us area ka bulletin
    ABHI, waqt ki parwah kiye bina, bana ke queue mein daal deta hai -
    taaki shaam ke schedule se pehle ek baar dekh kar tasalli ho jaaye.
    """
    import sy_bulletin
    want = str(rest or "").strip().lower()

    if want in ("on", "chalu", "1", "haan"):
        sy_bulletin.set_enabled(True)
        log("bulletin chalu")
        want = ""
    elif want in ("off", "band", "0", "nahi"):
        sy_bulletin.set_enabled(False)
        log("bulletin band")
        want = ""

    if want in sy_bulletin.AREAS:
        sy_telegram.send_message("Theek hai, %s ka bulletin abhi bana raha "
                                 "hoon..." % sy_bulletin.AREAS[want]["label"])
        try:
            sid = sy_bulletin.build(want)
        except Exception as e:
            sy_telegram.send_message("Bulletin banane mein gadbad: %s"
                                     % sy_telegram._esc(str(e)))
            return
        if sid:
            _force_add(sid)
            sy_telegram.send_message("Bulletin taiyar - approval jald "
                                     "aayega.")
        else:
            sy_telegram.send_message("Aaj is area ki khabrein banane "
                                     "laayak nahi milin (ya aaj ka "
                                     "bulletin pehle se ban chuka hai).")
        return
    elif want:
        sy_telegram.send_message(
            "Samajh nahi aaya. <code>/bulletin on</code>, "
            "<code>/bulletin off</code>, ya turant test ke liye "
            "<code>/bulletin mirzapur</code> / <code>prayagraj</code> / "
            "<code>up</code> likhiye.")
        return

    on = sy_bulletin.enabled()
    msg = ["<b>Roz shaam ke bulletin: %s</b>" % ("CHALU" if on else "BAND")]
    msg.append("")
    if on:
        for area, info in sy_bulletin.AREAS.items():
            hour = sy_bulletin.hour_for(area)
            done = st.kv_get("bulletin_done_" + area, "") == time.strftime(
                "%Y-%m-%d")
            msg.append("%s - %s baje%s" % (
                info["label"],
                str(hour) if hour else "(waqt tay nahi)",
                ", aaj ban chuka" if done else ""))
        msg.append("")
        msg.append("Turant ek banwa kar dekhne ke liye: "
                   "<code>/bulletin mirzapur</code>")
    else:
        msg.append("Chalu karne ke liye: <code>/bulletin on</code>")
    sy_telegram.send_message("\n".join(msg))


def do_title(rest):
    """/title 2 - jo video abhi approval par khadi hai, uska title badlo.

    Ye sirf usi video par chalta hai jo is waqt aapke jawab ka intezaar kar
    rahi hai. Nikal chuki video ka title yahan se nahi badalta - uske liye
    YouTube khud khulna chahiye, aur wo theek bhi hai: ek baar chhap chuki
    cheez chupke se badalna achhi aadat nahi.
    """
    rows = st.by_status("awaiting")
    if not rows:
        sy_telegram.send_message(
            "Abhi koi video approval par khadi nahi hai.")
        return
    story = rows[0]
    opts = st.kv_get("titles_" + str(story["story_id"])) or []
    if not isinstance(opts, list) or len(opts) < 2:
        sy_telegram.send_message(
            "Is video ke saath title ke vikalp nahi aaye the.")
        return

    try:
        n = int(re.sub(r"[^0-9]", "", str(rest))[:2])
    except Exception:
        n = 0
    if not 1 <= n <= len(opts):
        msg = "Kaun sa title? Aise likhiye: <code>/title 2</code>\n"
        for i, t in enumerate(opts, 1):
            msg += "\n%d. %s" % (i, sy_telegram._esc(t))
        sy_telegram.send_message(msg)
        return

    st.update(story["story_id"], yt_title=opts[n - 1])
    sy_telegram.send_message(
        "Title badal diya:\n\n<b>" + sy_telegram._esc(opts[n - 1]) + "</b>"
        "\n\nAb upar wali video par ✅ dabaiye.")
    log("title badla:", story["story_id"], "->", n)


def _git(*args):
    """git chalata hai isi folder mein. (nikla_theek, likha_hua) lautata hai."""
    import subprocess
    try:
        p = subprocess.run(("git", "-C", cfg.HERE) + args,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=180)
    except FileNotFoundError:
        return False, "git is machine par hai hi nahi"
    except subprocess.TimeoutExpired:
        return False, "git ne jawab hi nahi diya (180 second)"
    return p.returncode == 0, p.stdout.decode("utf-8", "replace").strip()


def do_update():
    """Naya code utha kar program ko dobara chalu karta hai.

    Ye wahi jagah hai jahan "laptop ka bharosa khatam" poora hota hai. Main
    sudhaar GitHub par rakh deta hoon; aap phone se /update likhte hain;
    server khud kheench kar naya code chala leta hai. Beech mein na laptop
    aata hai, na file bhejni padti hai.

    Kheenchna hamesha --ff-only hai. Yaani agar server par kisi ne haath se
    kuch badal diya ho, to git chup-chaap milaane ki koshish NAHI karega -
    wo saaf-saaf mana kar dega. Aadha-adhoora mila hua code raat ko chalte
    program mein sabse buri cheez hai.
    """
    if cfg.CLOUD:
        sy_telegram.send_message(
            "Cloud par /naya ki zaroorat nahi - har run GitHub se taaza "
            "code lekar hi chalti hai. Naya code agli run mein khud lag "
            "jayega.")
        return

    if not os.path.isdir(os.path.join(cfg.HERE, ".git")):
        sy_telegram.send_message(
            "Ye folder git se nahi juda hai, isliye /update yahan kaam nahi "
            "karega.\nSERVER.md mein dekhiye - repo jodna ek baar ka kaam hai.")
        return

    ok, out = _git("pull", "--ff-only")
    if not ok:
        sy_telegram.send_message(
            "<b>Update nahi ho paya.</b>\n\n<pre>"
            + sy_telegram._esc(out[-800:]) + "</pre>")
        log("update fail:", out[-400:])
        return

    if "Already up to date" in out or "up-to-date" in out:
        sy_telegram.send_message("Code pehle se naya hai - kuch badla nahi.")
        log("update: kuch naya nahi")
        return

    ok2, ver = _git("log", "-1", "--pretty=%h  %s")
    sy_telegram.send_message(
        "<b>Naya code aa gaya.</b>\n<code>" + sy_telegram._esc(ver if ok2 else "")
        + "</code>\n\nAb program dobara chalu ho raha hai. Ek minute mein "
          "wapas apne aap chal padega.")
    log("update lag gaya:", ver if ok2 else out[-200:])

    # Chalta hua Python apni purani copy pakde rehta hai - nayi file tab tak
    # nahi lagti jab tak program dobara na chale. systemd ko Restart=always
    # kaha gaya hai, isliye yahan se nikal jaana hi "dobara chalu karna" hai.
    # Ye kadam main loop ke beech aata hai, kisi render ke beech nahi - wahi
    # ise surakshit banata hai.
    sys.stdout.flush()
    os._exit(0)


def do_import_db(file_id, name):
    """Laptop ki satyayatra.db Telegram par aayi - uska hisaab yahan jodo.

    Cloud nayi database se shuru hua tha, isliye laptop par ban chuke vishay
    (GPS, chatbot, ...) dobara banne lage. File bhejte hi wo yaad yahan aa
    jaati hai. Sirf yaad aati hai - laptop ki katar ya offset nahi.
    """
    dest = os.path.join(cfg.WORK_ROOT, "laptop-import.db")
    try:
        sy_telegram.download(file_id, dest)
        got = st.import_history(dest)
    except Exception as e:
        log("purana hisaab nahi juda:", e)
        sy_telegram.send_message(
            "<b>Purana hisaab nahi jud paya</b>\n\n"
            + sy_telegram._esc(str(e))[:400])
        return
    finally:
        try:
            os.remove(dest)
        except OSError:
            pass
    log("purana hisaab juda:", got)
    sy_telegram.send_message(
        "<b>Laptop ka hisaab jud gaya</b> (%s)\n\n"
        "Nikal chuki khabrein: %d\n"
        "Vishayon ki ghadi (GPS, chatbot wagairah): %d\n"
        "Pehchaani hui khabrein/shirshak: %d / %d\n"
        "Switch (veo/anchor/...): %d\n"
        "Katar se hataye dohraav: %d\n\n"
        "Ab laptop par ban chuke vishay dobara nahi banenge."
        % (sy_telegram._esc(name), got["khabar"], got["ghadi"], got["seen"],
           got["titles"], got["switch"], got["hataye"]))


def tick_commands():
    """Telegram par type kiye gaye aadesh. Sirf aapki chat se aate hain."""
    # Saade sandesh - reject ki wajah apne shabdon mein.
    for txt, reply_to in sy_telegram.take_notes():
        try:
            import sy_feedback
            if not sy_feedback.on_text(txt, reply_to):
                log("sandesh aaya par kisi reject se nahi juda:", txt[:60])
        except Exception as e:
            log("feedback sandesh:", e)
    for file_id, name in sy_telegram.take_documents():
        do_import_db(file_id, name)
    for c, rest in sy_telegram.take_commands():
        if c in ("/khabar", "/vishay"):
            do_khabar(rest)
        elif c in ("/title", "/shirshak"):
            do_title(rest)
        elif c in ("/veo", "/drishya"):
            do_veo(rest)
        elif c in ("/social", "/samajik"):
            do_social(rest)
        elif c in ("/bulletin", "/bulliten"):
            do_bulletin(rest)
        elif c in ("/anchor", "/enkar"):
            do_anchor(rest)
        elif c in ("/update", "/naya"):
            log("aadesh:", c)
            do_update()
        elif c in ("/status", "/haal"):
            sy_telegram.send_message("<code>"
                                     + sy_telegram._esc(status_line())
                                     + "</code>")
        elif c in ("/restart", "/dobara") and cfg.CLOUD:
            # Cloud par yahan se nikalna run ko beech mein maar deta - aur
            # tab na hisaab bachta, na Telegram ka offset, to agli run phir
            # yahi aadesh uthati aur phir nikal jaati.
            sy_telegram.send_message(
                "Cloud par har run naye sire se chalti hai - dobara chalu "
                "karne ki zaroorat nahi.")
        elif c in ("/restart", "/dobara"):
            sy_telegram.send_message("Theek hai - dobara chalu kar raha hoon.")
            log("aadesh:", c)
            sys.stdout.flush()
            os._exit(0)
        elif c in ("/signin", "/login"):
            _ask_signin()
        elif c in ("/kyun", "/wajah"):
            # Kisi bhi samay: "/kyun <likhiye>" - pichhle reject par jud jaata hai.
            try:
                import sy_feedback
                if rest and not sy_feedback.on_text(rest, 0):
                    sy_telegram.send_message("Abhi koi taaza reject nahi mila jispar ye jode.")
            except Exception as e:
                log("feedback:", e)
        elif c in ("/help", "/madad", "/start"):
            sy_telegram.send_message(
                "<b>Aadesh</b>\n"
                "/khabar &lt;vishay&gt; - isi vishay par khabar banao\n"
                "/title 2 - khadi video ka title badlo\n"
                "/veo on | off - AI drishya chalu ya band\n"
                "/social on | off - FB aur Instagram par bhi\n"
                "/bulletin on | off - roz shaam ke bulletin\n"
                "/bulletin mirzapur|prayagraj|up - abhi ek banao\n"
                "/anchor on | off - bulletin ke intro/outro par AI anchor\n"
                "/anchor test - anchor ki jhalak, bina bulletin banaye\n"
                "/kyun &lt;baat&gt; - pichhle reject ki wajah likho\n"
                "/haal - abhi kya chal raha hai\n"
                "/naya - naya code uthao aur dobara chalu ho\n"
                "/dobara - bas dobara chalu ho\n"
                "/signin - YouTube ka sign-in phir se\n"
                "(laptop ki satyayatra.db file bhejiye - purana hisaab jud jayega)")
        else:
            log("anjaan aadesh:", c)


def _ask_signin():
    """Sign-in khatam - aapse phone par hi karwa lete hain.

    Server par browser nahi hota, aur laptop par bhi ab bharosa nahi
    rakhna hai. Isliye jahan ho sake wahan device wala tareeka chalate
    hain: program ek chhota code nikalta hai aur wahi Telegram par bhej
    deta hai. Aap phone par ek safha khol kar code daal dete hain - bas.
    Uske baad ruki hui video khud chali jaati hai.

    Ye sirf tab chalta hai jab config.ini mein TV-kism ka client bhara ho.
    Na ho to purani baat kah dete hain (signin.bat), taaki koi chup-chaap
    ruka na rahe.
    """
    try:
        sy_youtube.device_client()
    except Exception:
        if cfg.CLOUD:
            try:
                sy_telegram.send_message(
                    "<b>YouTube sign-in khatam ho gaya</b>\n\n"
                    "Laptop par ek baar <code>signin.bat</code> chalaiye. "
                    "Phir nayi <code>youtube-token.json</code> ka poora "
                    "text GitHub par satyayatra repo ke Secret "
                    "<code>YOUTUBE_TOKEN_JSON</code> mein daal dijiye - "
                    "agli run use utha legi aur ruki hui video chali "
                    "jayegi.\n\n"
                    "Bina laptop ke karna ho to CLOUD.md ka 'TV client' "
                    "wala tareeka dekhiye - tab ye phone se hota hai.")
            except Exception:
                pass
            return
        try:
            sy_telegram.send_message(
                "<b>YouTube sign-in khatam ho gaya</b>\n\n"
                "Ek baar <code>signin.bat</code> chala dijiye. Uske baad "
                "ruki hui video khud chali jayegi.\n\n"
                "Ye har 7 din mein hota hai kyunki app abhi Testing mein hai.")
        except Exception:
            pass
        return

    # Ye intezaar karta hai (aapke code daalne tak), isliye alag dhaage
    # mein - warna poora program yahin ruk jaata.
    import threading

    def run():
        try:
            sy_youtube.sign_in_device(notify=sy_telegram.send_message)
            sy_telegram.send_message(
                "Sign-in ho gaya. Ruki hui video ab khud chali jayegi.")
        except Exception as e:
            log("device sign-in nahi hua:", e)

    threading.Thread(target=run, daemon=True).start()


def tick_upload():
    ready = st.by_status("approved", limit=1)
    if not ready:
        return
    ok, why = upload_allowed()
    if not ok:
        return
    story = ready[0]
    sid = story["story_id"]
    try:
        vid = sy_youtube.upload(story, story["video_path"])
        sy_youtube.set_thumbnail(vid, story.get("thumb_path") or "")
        note_upload()
        st.update(sid, status="published", youtube_id=vid,
                  published_at=st.now(), error="")
        sy_telegram.send_message(
            "<b>YouTube par chadh gayi</b>\n\n"
            + sy_telegram._esc(story.get("headline_hi") or "")
            + "\n\nhttps://youtu.be/" + vid
            + "\n\nAbhi unlisted hai - dekh kar public kar dijiye.")
        log("published:", sid, vid)

        # FACEBOOK AUR INSTAGRAM - YOUTUBE KE BAAD, AUR ISI TRY KE ANDAR
        # NAHI.
        #
        # Ye apne alag try mein hai aur wo jaan-boojhkar hai: Facebook ka
        # token khatam ho jaye ya Instagram video na maane, to us se
        # YouTube wali kaamyabi par koi asar nahi padna chahiye. Khabar
        # 'published' ho chuki hai; social uske upar ka kaam hai, uski
        # shart nahi.
        try:
            import sy_social
            for where, ok2, res in sy_social.share(
                    story, story["video_path"], vid):
                if not ok2:
                    sy_telegram.send_message(
                        "<b>%s par nahi ja payi</b>\n\n" % where
                        + sy_telegram._esc(story.get("headline_hi") or "")
                        + "\n\n" + sy_telegram._esc(str(res))[:500])
        except Exception as e:
            log("social mein gadbad:", str(e)[:120])
    except sy_youtube.SignInExpired:
        # Khabar 'approved' hi rehti hai - sign-in hote hi khud chali
        # jayegi. Roz mein ek hi baar batate hain, warna har 20 second
        # par wahi sandesh jayega.
        log("YouTube sign-in khatam ho gaya")
        if st.kv_get("signin_warned_day", "") != _today():
            st.kv_set("signin_warned_day", _today())
            _ask_signin()
    except sy_youtube.RateLimited as e:
        # Ye nakaami nahi hai. YouTube ne abhi mana kiya hai; khabar
        # 'approved' hi rehti hai aur agli baari par khud chali jayegi.
        log("YouTube ne abhi roka - baad mein koshish karenge:", e)
        st.kv_set("last_upload_ts", time.time())
    except Exception as e:
        log("upload nahi hua:", e)
        st.update(sid, status="failed", error=str(e)[:400])
        sy_telegram.send_message(
            "<b>YouTube upload fail hua</b>\n\n"
            + sy_telegram._esc(story.get("headline_hi") or "")
            + "\n\n<b>Wajah:</b>\n" + sy_telegram._esc(str(e))[:600]
            + "\n\nVideo aapke PC par hai:\n<code>"
            + str(story.get("video_path") or "") + "</code>")


def status_line():
    """Ek line mein poori haalat. Isi se pata chalta hai ki program kya kar
    raha hai - aur kya nahi kar raha, aur kyun."""
    counts = " ".join(
        "%s %d" % (k, st.count_status(k))
        for k in ("pending", "producing", "awaiting", "approved",
                  "published", "failed")
        if st.count_status(k))
    khabar = st.due_in("news", cfg.num("schedule", "news_ingest_minutes", 120))
    yojana = st.due_in("yojana", cfg.num("schedule", "yojana_ingest_minutes", 120))
    video = st.due_in("produce", cfg.num("schedule", "produce_minutes", 360))
    cap = cfg.num("limits", "max_uploads_per_day", 5)
    if cap <= 0:
        jagah_txt = "seema nahi hai"
    else:
        jagah_txt = "%d/%d" % (max(0, cap - (uploads_today() + in_flight_count())), cap)
    line = ("%s | agli khabar %dm, yojana %dm, video %dm | aaj ki jagah %s"
            % (counts or "queue khaali", khabar, yojana, video, jagah_txt))
    # Internet na ho to ye sabse zaroori baat hai - warna dikhta hai ki
    # program chal raha hai par kuch ho nahi raha, aur wajah samajh nahi
    # aati.
    if sy_telegram.offline():
        line += "  |  INTERNET NAHI HAI"
    return line


def startup():
    """Program chalu hote hi ek baar - laptop, server aur cloud teeno par."""
    cfg.ensure_dirs()
    cfg.put_ffmpeg_on_path()
    st.conn()
    log("SatyaYatra chalu. Ise band mat kijiye.")
    log("folder:", cfg.HERE)

    # Purani "apne aap raftaar tay karo" wali cheez ka bacha hua nishan.
    # Wo hisaab hata diya gaya tha, par uska likha hua ankda (0.707) abhi
    # bhi database mein pada tha. Ab use koi nahi padhta - phir bhi wo
    # wahan rehkar sirf gumraah karta hai, isliye ek baar saaf kar dete hain.
    if st.kv_get("tts_pace") is not None:
        st.kv_del("tts_pace")
        log("purana tts_pace hata diya - raftaar ab config.ini se aati hai")

    # Bot par kisi aur ka webhook laga ho to getUpdates chalta hi nahi.
    sy_telegram.ensure_polling()

    # 'failed' par ruki khabrein sahi jagah wapas. Jo video ban chuki hai
    # wo 'approved' par jaati hai (dobara nahi banegi), jo bani hi nahi wo
    # 'pending' par. Ye farq sy_store.revive_failed() mein likha hai.
    up, new = st.revive_failed()
    if up:
        log("%d bani hui video wapas upload ki katar mein" % up)
    if new:
        log("%d adhoori khabar wapas queue mein" % new)

    # Pichhli baar video banate-banate program band ho gaya ho, to wo khabar
    # 'producing' mein atki reh jaati hai aur phir kabhi nahi uthti.
    stuck = st.by_status("producing")
    for s_ in stuck:
        st.update(s_["story_id"], status="pending", error="")
    if stuck:
        log("adhoori chhoot gayi %d khabar wapas queue mein" % len(stuck))

    log(status_line())


def nap_seconds():
    return max(10, cfg.num("schedule", "approval_poll_seconds", 20))


_last_beat = [0.0]


def one_round():
    """Saare kaam ek-ek baar. main() ise lagataar chalata hai, sy_cloud.py
    kuch minute tak."""
    # tick_offer, tick_produce se PEHLE: pehle vishay ka chunav aapke
    # paas jaata hai, aur jawab aane tak tick_produce khud ruk jaata
    # hai (wahan OFFER_KEY ki jaanch hai).
    for step in (tick_decisions, tick_commands, tick_bulletin, tick_report,
                 tick_ingest, tick_offer, tick_produce, tick_upload):
        try:
            step()
        except Exception:
            # Ek kadam girne se poora program nahi girna chahiye -
            # ye din-raat chalta hai.
            log("gadbad:", step.__name__)
            traceback.print_exc()

    # Har 5 minute ek line, chahe kuch na ho raha ho. Bina iske program
    # ghanton chup rehta hai aur ye tay hi nahi hota ki wo kaam kar raha
    # hai ya kahin atak gaya hai.
    if time.time() - _last_beat[0] > 300:
        _last_beat[0] = time.time()
        log(status_line())

    # Din mein ek baar disk ki safai.
    if st.due("tidy", 1440):
        try:
            tidy_disk()
        except Exception as e:
            log("safai mein gadbad:", e)


def main():
    startup()
    nap = nap_seconds()
    while True:
        one_round()
        time.sleep(nap)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("band kiya gaya")

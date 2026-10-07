"""Khabron ki haalat rakhne wali chhoti si local database.

Ye Google Sheet ki jagah leti hai. Sheet se peechha chhudane ki wajah sirf
kharch nahi thi: har padhna-likhna ek API call tha, uska apna quota tha,
column ke naam mein ek space aa jaye to sab bikhar jaata tha, aur do jagah
se ek hi row chhoo dene par kaun jeeta ye tay hi nahi hota tha. Ek local
file mein ye teenon dikkatein hain hi nahi.

Har khabar ek row. status hi poori kahani batata hai:

  pending      -> script taiyar hai, video banni baaki hai
  producing    -> abhi ban rahi hai
  awaiting     -> Telegram par bheji ja chuki, jawab ka intezaar
  approved     -> haan mil gayi, upload hona baaki
  published    -> YouTube par chadh gayi
  rejected     -> aapne mana kar diya
  failed       -> kuch toot gaya; error column mein wajah likhi hai
"""
import json
import os
import sqlite3
import time

import sy_config as cfg

# Nayi jaankari jodni ho to bas is list ke aakhir mein naam aur type likh
# dijiye - purani database khud usme naya column jod legi (neeche migrate()).
COLUMNS = [
    ("story_id", "TEXT PRIMARY KEY"),
    ("beat", "TEXT"),            # news | yojana
    ("status", "TEXT"),
    ("error", "TEXT"),
    ("score", "INTEGER"),
    ("sources", "TEXT"),
    ("source_link", "TEXT"),
    ("attribution_line", "TEXT"),

    ("headline_hi", "TEXT"),
    ("headline_en", "TEXT"),
    ("lower_third_hi", "TEXT"),
    ("script_hi", "TEXT"),
    ("yt_title", "TEXT"),
    ("yt_description", "TEXT"),
    ("tags", "TEXT"),

    # Art direction
    ("category", "TEXT"),
    ("style", "TEXT"),
    ("kicker", "TEXT"),
    ("key_fact", "TEXT"),
    ("ghost", "TEXT"),
    ("thumb_entity", "TEXT"),
    ("thumb_text", "TEXT"),
    ("thumb_style", "TEXT"),
    ("wants_photo", "INTEGER"),
    ("photo_reason", "TEXT"),
    ("photo_queries", "TEXT"),   # JSON list
    ("is_person", "INTEGER"),    # khabar ka kendra koi prasiddh vyakti hai?
    ("people_en", "TEXT"),       # un sarvajanik logon ke naam (JSON list, angrezi)
    ("shots", "TEXT"),           # JSON: script ke tukde + har tukde ka drishya

    # Media
    ("clip_url", "TEXT"),
    ("clip_credit", "TEXT"),
    ("stock_url", "TEXT"),
    ("stock_credit", "TEXT"),
    ("image_credit", "TEXT"),
    ("photo_source", "TEXT"),

    # Nateeja
    ("video_path", "TEXT"),
    ("thumb_path", "TEXT"),
    ("seconds", "REAL"),
    ("youtube_id", "TEXT"),
    ("tg_message_id", "INTEGER"),

    ("created_at", "TEXT"),
    ("updated_at", "TEXT"),
    ("published_at", "TEXT"),
]

_conn = None


def conn():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(cfg.DB_PATH, timeout=30)
        _conn.row_factory = sqlite3.Row
        # Do cheezein ek saath likhne ki koshish karein to WAL ke bina
        # "database is locked" aa jaata hai.
        _conn.execute("PRAGMA journal_mode=WAL")
        migrate(_conn)
    return _conn


def migrate(c):
    cols = ", ".join("%s %s" % (n, t) for n, t in COLUMNS)
    c.execute("CREATE TABLE IF NOT EXISTS stories (%s)" % cols)
    have = set(r["name"] for r in c.execute("PRAGMA table_info(stories)"))
    for n, t in COLUMNS:
        if n not in have:
            # Purani database mein naya column jodna - data waisa ka waisa.
            c.execute("ALTER TABLE stories ADD COLUMN %s %s"
                      % (n, t.replace(" PRIMARY KEY", "")))
    c.execute("CREATE INDEX IF NOT EXISTS ix_status ON stories(status)")
    c.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)")
    # Jo khabrein dekhi ja chuki hain - dobara na uthein.
    c.execute("CREATE TABLE IF NOT EXISTS seen "
              "(key TEXT PRIMARY KEY, at TEXT)")
    # Har dekhe hue shirshak ka asli roop. Sirf hash se kaam nahi chalta:
    # ek hi ghatna do outlets par alag shabdon mein likhi hoti hai, aur
    # kal ki khabar aaj thode alag shirshak ke saath phir se aa jaati hai.
    # Shabdon ka milaan hi use pakadta hai, isliye shirshak rakhna padta hai.
    c.execute("CREATE TABLE IF NOT EXISTS titles "
              "(title TEXT PRIMARY KEY, at TEXT)")
    c.commit()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------- stories

def add_story(row):
    """Nayi khabar daalo. Pehle se ho to kuch mat karo (dobara nahi banegi)."""
    c = conn()
    row = dict(row)
    row.setdefault("status", "pending")
    row.setdefault("created_at", now())
    row["updated_at"] = now()
    keys = [k for k, _ in COLUMNS if k in row]
    q = ("INSERT OR IGNORE INTO stories (%s) VALUES (%s)"
         % (", ".join(keys), ", ".join("?" * len(keys))))
    cur = c.execute(q, [row[k] for k in keys])
    c.commit()
    return cur.rowcount > 0


_KNOWN = set(n for n, _ in COLUMNS)


def update(story_id, **fields):
    """Row badlo. Anjaan field chhod dete hain, par chup-chaap nahi.

    Pehle yahan ek anjaan naam poori video ko gira deta tha - art director
    ne 'is_person' bheja, wo column tha hi nahi, aur khabar 'failed' ho gayi.
    Ek chhoti si nayi jaankari ka itna bada nateeja galat hai.
    """
    unknown = [k for k in fields if k not in _KNOWN]
    for k in unknown:
        print("[store] anjaan field chhoda:", k, flush=True)
        fields.pop(k)
    if not fields:
        return
    c = conn()
    fields["updated_at"] = now()
    sets = ", ".join("%s = ?" % k for k in fields)
    c.execute("UPDATE stories SET %s WHERE story_id = ?" % sets,
              list(fields.values()) + [story_id])
    c.commit()


def get(story_id):
    r = conn().execute("SELECT * FROM stories WHERE story_id = ?",
                       (story_id,)).fetchone()
    return dict(r) if r else None


def by_status(status, limit=50):
    rows = conn().execute(
        "SELECT * FROM stories WHERE status = ? ORDER BY score DESC, created_at ASC"
        " LIMIT ?", (status, limit)).fetchall()
    return [dict(r) for r in rows]


def count_status(status, beat=None):
    if beat:
        q = "SELECT COUNT(*) FROM stories WHERE status = ? AND beat = ?"
        return conn().execute(q, (status, beat)).fetchone()[0]
    return conn().execute("SELECT COUNT(*) FROM stories WHERE status = ?",
                          (status,)).fetchone()[0]


def age_hours(row):
    """Khabar kitni purani hai. Pata na chale to 0 (yaani taazi maano)."""
    try:
        t = time.mktime(time.strptime(str(row.get("created_at") or "")[:19],
                                      "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return 0.0
    return max(0.0, (time.time() - t) / 3600.0)


def waiting_hours(row):
    """Ye video kitni der se apni aakhri halchal par khadi hai.

    age_hours khabar ki UMAR batata hai (created_at). Ye alag cheez hai:
    updated_at se - yaani wo video kitni der se Telegram par jawab ka
    intezaar kar rahi hai.
    """
    try:
        t = time.mktime(time.strptime(str(row.get("updated_at") or "")[:19],
                                      "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return 0.0
    return max(0.0, (time.time() - t) / 3600.0)


# Har DECAY_HOURS ghante mein khabar ek ank kamzor pad jaati hai.
#
# Ye sirf ek hisaab nahi, ek sampadakiy faisla hai: 6 ghante purani khabar
# utni hi achhi hai jitni ek taazi khabar jiska score ek kam ho. Isse badi
# khabar der tak tikti hai (score 22 wali 12 ghante baad bhi 20 hai, aur
# ek chhoti taazi khabar se aage rehti hai), par ek chhoti purani khabar
# apne aap peeche chali jaati hai.
DECAY_HOURS = 6.0

# Ye beat kabhi purane nahi hote. Yojana ki jaankari ka maksad hi awareness
# hai - wo yojana kal shuru hui ho ya do saal pehle, jise nahi pata usake
# liye wo aaj bhi nayi hai. Ispar taazgi ka hisaab lagana galat hoga. Tech
# ki jagrukta bhi yahi - "chatbot kya hai" video kal bhi utni hi kaam ki hai
# jitni aaj.
TIMELESS = ("yojana", "kaam", "gyan", "tech")


def hours_since_published(beat):
    """Is beat ki aakhri video kitne ghante pehle chadhi. Kabhi nahi to bahut bada."""
    r = conn().execute(
        "SELECT published_at FROM stories WHERE beat = ? AND published_at IS NOT NULL"
        " ORDER BY published_at DESC LIMIT 1", (beat,)).fetchone()
    if not r or not r[0]:
        return 1e9
    try:
        t = time.mktime(time.strptime(str(r[0])[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return 1e9
    return max(0.0, (time.time() - t) / 3600.0)


def _rank(row):
    """Kitni zaroori hai, ABHI. Bada matlab pehle."""
    sc = float(row.get("score") or 0)
    if str(row.get("beat") or "") in TIMELESS:
        return sc
    return sc - age_hours(row) / DECAY_HOURS


def done_ids(days=0):
    """Jo khabrein nikal chuki hain (publish/reject/expire) unke id."""
    q = ("SELECT story_id, updated_at FROM stories WHERE status IN "
         "('published','rejected','expired','no_visual')")
    out = []
    for r in conn().execute(q):
        row = {"story_id": r[0], "updated_at": r[1]}
        if days <= 0 or waiting_hours(row) >= days * 24:
            out.append(r[0])
    return out


def revive_failed():
    """'failed' par ruki khabron ko sahi jagah wapas bhejo.

    Ye do alag haalat hain aur inhe ek jaisa maanna mehnga padta hai:

      1. Video ban hi nahi payi (render beech mein ruk gaya). Yahan koi
         file nahi hai, to khabar 'pending' par wapas jaani chahiye -
         dobara banegi.

      2. Video BAN CHUKI hai, aapne use approve bhi kar diya tha, aur
         sirf YouTube par chadhte waqt gadbad hui. Yahan file disk par
         poori padi hai. Ise 'pending' karna sabse mehnga kism ka nuksaan
         hai: wahi video dobara banti hai - dobara aawaaz ka kharch,
         dobara drishya, dobara render - jabki bani hui file wahin rakhi
         hai, aur aapko dobara approve bhi karna padta hai.

    Ye farq nahi tha, aur wo dikh gaya: kb_nalsa wali video ban chuki thi
    aur approve bhi ho chuki thi, par YouTube ka sign-in khatam hone se
    upload ruk gaya - aur wo 'failed' par chali gayi.

    Lauta ta hai (kitni approved par wapas, kitni pending par).
    """
    back_up = back_new = 0
    for r in conn().execute("SELECT * FROM stories WHERE status = 'failed'"):
        row = dict(r)
        path = str(row.get("video_path") or "")
        if path and os.path.exists(path):
            update(row["story_id"], status="approved", error="")
            back_up += 1
        else:
            update(row["story_id"], status="pending", error="")
            back_new += 1
    return back_up, back_new


def recent_beats(n=5):
    """Pichhli n video kis beat ki thi - jo Telegram tak pahunchi.

    "Pahunchi" isliye, "publish hui" nahi. Reject hui video bhi banane ka
    poora kharch aur poora waqt le chuki hoti hai. Anupat mehnat par lagna
    chahiye, sirf dikhne wale nateeje par nahi - warna ek hafte tak khabar
    reject hoti rahe to program us anupat ko pakadne ke chakkar mein sirf
    khabar hi banata rahega.

    tg_message_id ki shart isliye ki katar mein baithe-baithe expire hui
    khabar kabhi bani hi nahi thi - wo ginti mein nahi aani chahiye.
    """
    rows = conn().execute(
        "SELECT beat FROM stories WHERE tg_message_id IS NOT NULL"
        " AND tg_message_id != 0 ORDER BY updated_at DESC LIMIT ?",
        (int(n),)).fetchall()
    return [str(r[0] or "") for r in rows]


def next_pending(beat=None, exclude=()):
    """Agli video kis khabar par banegi.

    Pehle ye sirf score dekhta tha, aur barabari par PURANI ko chunta tha
    (created_at ASC). News channel ke liye wo ulta hai. Aapki katar mein
    teen khabrein score 16 par thi - do abhi ki, ek 27 ghante purani, aur
    har baar 27 ghante wali hi uthti thi. Isi tarah do-do din purani khabar
    channel par chali jaati thi jabki nayi peeche padi rehti.

    Ab taazgi score ke saath tulti hai - upar DECAY_HOURS dekhiye.
    """
    q = "SELECT * FROM stories WHERE status = 'pending'"
    args = ()
    if beat:
        q += " AND beat = ?"
        args = (beat,)
    rows = [dict(r) for r in conn().execute(q, args)]
    if exclude:
        rows = [r for r in rows if str(r.get("beat") or "") not in exclude]
    if not rows:
        return None
    rows.sort(key=_rank, reverse=True)
    return rows[0]


def expire_stale(max_age_hours, beats=None):
    """Bahut purani khabrein katar se hata do. Kitni hatayi, wo lauta ta hai.

    Do din purani khabar par "बड़ी खबर" ki patti lagakar chalana channel ka
    bharosa girata hai - darshak ko turant pata chal jaata hai ki ye kal ki
    baat hai. Aisi khabar ka na chalna uske chalne se behtar hai.

    Yojana is se bahar hai - wo khabar hai hi nahi, jaankari hai.
    """
    out = 0
    for r in conn().execute("SELECT * FROM stories WHERE status = 'pending'"):
        row = dict(r)
        beat = str(row.get("beat") or "")
        if beat in TIMELESS:
            continue
        if beats and beat not in beats:
            continue
        if age_hours(row) > max_age_hours:
            update(row["story_id"], status="expired",
                   error="%.0f ghante purani ho gayi thi" % age_hours(row))
            out += 1
    return out


def published_since(iso_ts):
    return conn().execute(
        "SELECT COUNT(*) FROM stories WHERE published_at IS NOT NULL"
        " AND published_at > ?", (iso_ts,)).fetchone()[0]


def last_published_at():
    r = conn().execute(
        "SELECT published_at FROM stories WHERE published_at IS NOT NULL"
        " ORDER BY published_at DESC LIMIT 1").fetchone()
    return r[0] if r else None


def awaiting_by_message(message_id):
    r = conn().execute(
        "SELECT * FROM stories WHERE tg_message_id = ? AND status = 'awaiting'",
        (message_id,)).fetchone()
    return dict(r) if r else None


# -------------------------------------------------------------------- seen

def seen(key):
    return conn().execute("SELECT 1 FROM seen WHERE key = ?",
                          (key,)).fetchone() is not None


def mark_seen(key):
    c = conn()
    c.execute("INSERT OR IGNORE INTO seen (key, at) VALUES (?, ?)", (key, now()))
    c.commit()


def remember_title(title):
    t = str(title or "").strip()
    if not t:
        return
    c = conn()
    c.execute("INSERT OR IGNORE INTO titles (title, at) VALUES (?, ?)",
              (t, now()))
    c.commit()


def recent_titles(limit=400):
    rows = conn().execute(
        "SELECT title FROM titles ORDER BY at DESC LIMIT ?", (limit,)).fetchall()
    return [r[0] for r in rows]


def forget_old_seen(days=45):
    """Purani yaadein hata dete hain, warna file badhti hi jayegi."""
    cut = time.strftime("%Y-%m-%dT%H:%M:%S",
                        time.localtime(time.time() - days * 86400))
    c = conn()
    c.execute("DELETE FROM seen WHERE at < ?", (cut,))
    c.execute("DELETE FROM titles WHERE at < ?", (cut,))
    c.commit()


# ---------------------------------------------------------------------- kv

def kv_get(k, default=None):
    r = conn().execute("SELECT v FROM kv WHERE k = ?", (k,)).fetchone()
    if not r:
        return default
    try:
        return json.loads(r[0])
    except Exception:
        return default


def kv_set(k, v):
    c = conn()
    c.execute("INSERT INTO kv (k, v) VALUES (?, ?) "
              "ON CONFLICT(k) DO UPDATE SET v = excluded.v",
              (k, json.dumps(v)))
    c.commit()


def kv_del(k):
    c = conn()
    c.execute("DELETE FROM kv WHERE k = ?", (k,))
    c.commit()


def due_in(name, minutes):
    """Is kaam ki agli baari kitne minute mein hai. 0 = abhi."""
    last = float(kv_get("last_" + name, 0) or 0)
    left = minutes - (time.time() - last) / 60.0
    return max(0, int(round(left)))


def retry_soon(name, interval_minutes, wait_minutes=10):
    """Is kaam ki baari jaldi wapas le aao.

    Internet na hone par khabar dhoondhne ki koshish khaali jaati hai, par
    ghadi to chhap chuki hoti hai - aur agli baari poore do ghante baad
    aati thi. Yaani paanch minute ki DNS ki dikkat do ghante ka nuksaan
    ban jaati thi. Aisi haalat mein ghadi utni peeche khiska dete hain ki
    agli koshish wait_minutes mein ho jaye.
    """
    back = max(0.0, float(interval_minutes) - float(wait_minutes)) * 60.0
    kv_set("last_" + name, time.time() - back)


def due(name, minutes):
    """Kya is kaam ka samay ho gaya? Haan to samay chhap kar True lauta do.

    Ghadi ka hisaab yahin rehta hai, isliye program band karke dobara khola
    jaye to bhi kaam do baar nahi hota.
    """
    last = kv_get("last_" + name, 0)
    if time.time() - float(last) < minutes * 60:
        return False
    kv_set("last_" + name, time.time())
    return True


if __name__ == "__main__":
    cfg.ensure_dirs()
    conn()
    print("database:", cfg.DB_PATH)
    for s in ("pending", "producing", "awaiting", "approved",
              "published", "rejected", "failed"):
        print("  %-10s %d" % (s, count_status(s)))
    print("  yaad rakhi hui khabrein:",
          conn().execute("SELECT COUNT(*) FROM seen").fetchone()[0])


# ------------------------------------------------------ purana hisaab jodna

# Ghoomne wale vishayon ki "aakhri baar kab bana" ghadi. Story id ka shuruaati
# hissa -> kv ki chaabi ka shuruaati hissa.
_ROTATION = {"gy": "gyan_last_", "tc": "tech_last_", "kb": "kaam_last_",
             "yj": "scheme_last_"}
# Telegram ke switch - laptop par /veo on wagairah se lage the.
_SWITCHES = ("veo_on", "social_on", "bulletin_on", "anchor_on", "heygen_on",
             "fatafat_on")
_DONE = ("published", "rejected", "expired", "no_visual", "low_reach")


def import_history(path):
    """Laptop ki satyayatra.db ka hisaab is database mein jodo.

    KYUN: cloud (GitHub Actions) par database nayi shuruaat se bana tha, to
    use pata hi nahi tha ki laptop par kaunse vishay (GPS, chatbot, ...) aur
    kaunsi khabrein pehle ban chuki hain - wahi dobara banne lage. Ye
    function laptop ki file se sirf YAAD uthata hai, kaam nahi:

      - stories: jo laptop par nikal chuki hain (publish/reject/expire)
        wo yahan bhi 'nikal chuki' maani jaati hain. Yahan wahi id katar
        mein ho aur abhi bani na ho, to wo hata di jaati hai.
      - gyan/tech/kaam/yojana ki ghadi: dono mein jo baad ki ho.
      - seen, titles: khabron ki pehchaan - dono ka jod.
      - Telegram switch (veo/anchor/...): sirf tab jab yahan pehle se na ho.

    Baaki sab (Telegram offset, upload ginti, katar mein khadi cheezein)
    jaan-boojhkar nahi liya jaata - wo is machine ka apna chalta hua haal hai.

    Katar mein khadi jo cheez laptop par haal mein ban chuke vishay ki hai,
    wo bhi hata di jaati hai (status 'expired').

    Lauta ta hai {naam: ginti}.
    """
    import sqlite3
    src = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    src.row_factory = sqlite3.Row
    c = conn()
    out = {"khabar": 0, "ghadi": 0, "seen": 0, "titles": 0, "switch": 0,
           "hataye": 0}
    laptop_last = {}    # sirf LAPTOP ki ghadi - neeche step 4 ke liye
    try:
        names = set(r[0] for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"))
        if "stories" not in names or "kv" not in names:
            raise ValueError("ye SatyaYatra ki database nahi lagti")

        # 1) ghadi aur switch
        for r in src.execute("SELECT k, v FROM kv"):
            k, v = r["k"], r["v"]
            try:
                val = json.loads(v)
            except Exception:
                continue
            if any(k.startswith(p) for p in _ROTATION.values()) \
                    or k.startswith("trend_last_"):
                mine = float(kv_get(k, 0) or 0)
                try:
                    theirs = float(val or 0)
                except (TypeError, ValueError):
                    continue
                laptop_last[k] = theirs
                if theirs > mine:
                    kv_set(k, theirs)
                    out["ghadi"] += 1
            elif k in _SWITCHES and kv_get(k) is None:
                kv_set(k, val)
                out["switch"] += 1

        # 2) nikal chuki khabrein
        have = set(n for n, _ in COLUMNS)
        for r in src.execute(
                "SELECT * FROM stories WHERE status IN (%s)"
                % ",".join("?" * len(_DONE)), _DONE):
            row = {k: r[k] for k in r.keys() if k in have}
            mine = get(row["story_id"])
            if mine is None:
                keys = list(row)
                c.execute("INSERT OR IGNORE INTO stories (%s) VALUES (%s)"
                          % (", ".join(keys), ", ".join("?" * len(keys))),
                          [row[k] for k in keys])
                out["khabar"] += 1
            elif mine["status"] in ("pending", "failed", "producing"):
                update(row["story_id"], status="expired",
                       error="laptop par pehle ban chuki thi")
                out["hataye"] += 1

        # 3) pehchaan
        for tbl, col, key in (("seen", "key", "seen"),
                              ("titles", "title", "titles")):
            if tbl not in names:
                continue
            for r in src.execute("SELECT %s, at FROM %s" % (col, tbl)):
                cur = c.execute("INSERT OR IGNORE INTO %s (%s, at) VALUES (?, ?)"
                                % (tbl, col), (r[0], r[1]))
                out[key] += cur.rowcount
        c.commit()
    finally:
        src.close()

    # 4) katar mein khadi cheez jiska vishay ab "haal mein bana" dikhta hai.
    # Dohraav ki seema sy_ingest ke *_REPEAT_DAYS se aati hai.
    import sy_ingest
    days = {"gy": sy_ingest.GYAN_REPEAT_DAYS, "tc": sy_ingest.TECH_REPEAT_DAYS,
            "kb": sy_ingest.KAAM_REPEAT_DAYS, "yj": sy_ingest.SCHEME_REPEAT_DAYS}
    for r in c.execute("SELECT story_id, created_at FROM stories "
                       "WHERE status IN ('pending','failed')").fetchall():
        sid = r[0]
        pre, _, restid = sid.partition("_")
        if pre not in _ROTATION or "_" not in restid:
            continue
        slug = restid.rsplit("_", 1)[0]
        # Cloud ki apni ghadi nahi - wo to isi khabar ke saath lagi thi.
        last = laptop_last.get(_ROTATION[pre] + slug, 0)
        try:
            made = time.mktime(time.strptime(r[1], "%Y-%m-%dT%H:%M:%S"))
        except Exception:
            made = time.time()
        # Laptop wali ghadi is khabar ke banne se PEHLE ki ho aur dohraav
        # ki seema ke andar - matlab ye dohraav hai.
        if last and last < made and made - last < days[pre] * 86400:
            update(sid, status="expired", error="laptop par pehle ban chuka vishay")
            out["hataye"] += 1
    return out

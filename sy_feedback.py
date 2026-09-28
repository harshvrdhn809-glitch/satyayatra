"""Reject ki WAJAH - poochho, sambhaal kar rakho, aur usse code sudhro.

KYUN (Sep 2026, Harshvardhan ki maang)
======================================
Pehle Telegram par "Reject" dabate hi kahani wahin khatam ho jaati thi.
Galti kya thi - footage be-mel tha, khabar kaam ki nahi thi, script mein
galat baat thi - ye kahin darj nahi hota tha, isliye wahi galti agli video
mein phir ho jaati thi.

Ab reject ke turant baad bot poochhta hai "kyun?" - chhe button, aur
chahein to apne shabdon mein ek line. Jawab do jagah jaata hai:

  feedback/feedback.jsonl  - har reject ki ek line: wajah, aapke shabd, aur
                             us video ka poora sandarbh (beat, headline, har
                             drishya ka brief/srot/khoj ka shabd, credit).
                             Yahi Claude padhta hai.
  feedback/FEEDBACK.md     - wahi sab, padhne layak roop mein, sirf wo jo
                             abhi tak sudhaare nahi gaye.

Claude jab bhi is folder se juda ho (aur roz ek baar apne-aap, scheduled
task se), "handled": false wali lines padh kar wajah dhoondhta hai, code
sudhaarta hai, aur un lines par "handled" + kya badla, likh deta hai.

KABHI KUCH NAHI ROKTA
=====================
Yahan ki koi bhi gadbad (file na likhi jaaye, button na jaaye) reject ko
nahi rokti - reject pehle hi darj ho chuka hota hai.
"""
import json
import os
import time

import sy_config as cfg

DIR = os.path.join(cfg.HERE, "feedback")
JSONL = os.path.join(DIR, "feedback.jsonl")
MD = os.path.join(DIR, "FEEDBACK.md")

# (code, button ka text, poora matlab - Claude ke liye)
REASONS = [
    ("footage", "🎞 Footage be-mel",
     "drishya/tasveer/clip khabar ya us baat se mel nahi khaate"),
    ("topic", "📰 Khabar kaam ki nahi",
     "vishay hi chalane layak nahi - kam mahatva, purana, ya darshak ke kaam ka nahi"),
    ("script", "✍️ Script/tathya galat",
     "script mein galat, adhoori ya bhramak baat; bhasha/andaaz theek nahi"),
    ("voice", "🗣 Awaaz/uchcharan",
     "aawaaz, uchcharan, raftaar ya text-awaaz ka mel theek nahi"),
    ("thumb", "🖼 Thumbnail/title",
     "thumbnail ya title kharab, galat ya bhramak"),
    ("other", "✏️ Kuch aur (likhiye)",
     "koi aur wajah - aapke shabdon mein"),
]
NOTE_WINDOW = 6 * 3600      # reject ke itni der tak ka likha hua sandesh us par jud jaata hai
PENDING_KEY = "fb_pending"  # {"sid":..., "at":..., "msg": question_message_id}


def log(*a):
    print("[feedback]", *a, flush=True)


def _label(code):
    for c, lab, _ in REASONS:
        if c == code:
            return lab
    return code


def _meaning(code):
    for c, _, m in REASONS:
        if c == code:
            return m
    return ""


# ------------------------------------------------------------- poochhna

def ask(story):
    """Reject ke turant baad - "kyun?" wale button bhejo."""
    import sy_store as st
    import sy_telegram
    sid = str(story.get("story_id") or "")
    rows, row = [], []
    for code, lab, _ in REASONS:
        row.append({"text": lab, "callback_data": "fb:%s|%s" % (code, sid)})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    text = ("<b>Ye kyun reject ki?</b>\n"
            + sy_telegram._esc(story.get("headline_hi") or "")[:200]
            + "\n\nEk button dabaiye - aur chahein to neeche apne shabdon "
              "mein ek line likh dijiye (jaise \"3rd drishya mein bus ki "
              "jagah aag ki photo\"). Yahi agli baar ka sudhaar banega.")
    try:
        res = sy_telegram._post("sendMessage", {
            "chat_id": sy_telegram._chat(), "text": text, "parse_mode": "HTML",
            "reply_markup": json.dumps({"inline_keyboard": rows})}, timeout=60)
        st.kv_set(PENDING_KEY, {"sid": sid, "at": time.time(),
                                "msg": int(res.get("message_id") or 0)})
    except Exception as e:
        log("wajah poochhne wala sandesh nahi gaya:", e)


# ------------------------------------------------------------- darj karna

def _context(story):
    """Us video ka woh sab jo galti dhoondhne mein kaam aaye."""
    shots = []
    try:
        for i, sh in enumerate(json.loads(story.get("shots") or "[]")):
            shots.append({
                "n": i + 1, "type": sh.get("type"), "brief": sh.get("brief"),
                "text": (sh.get("text") or "")[:160],
                "queries": sh.get("queries"), "source": sh.get("source"),
                "file": sh.get("file"), "kind": sh.get("kind"),
                "credit": (sh.get("credit") or "")[:120],
                "studio": bool(sh.get("studio")),
            })
    except Exception:
        pass
    return {
        "beat": story.get("beat"), "headline_hi": story.get("headline_hi"),
        "yt_title": story.get("yt_title"), "category": story.get("category"),
        "sources": story.get("sources"), "source_link": story.get("source_link"),
        "photo_source": story.get("photo_source"),
        "thumb_text": story.get("thumb_text"),
        "script_hi": (story.get("script_hi") or "")[:1500],
        "seconds": story.get("seconds"), "created_at": story.get("created_at"),
        "shots": shots,
        "workdir": os.path.join(cfg.WORK_ROOT, str(story.get("story_id") or "")),
        "video": story.get("video_path"), "thumb": story.get("thumb_path"),
    }


def _load():
    out = []
    try:
        with open(JSONL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        pass
    except FileNotFoundError:
        pass
    return out


def _save(rows):
    os.makedirs(DIR, exist_ok=True)
    tmp = JSONL + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, JSONL)
    _write_md(rows)


def _write_md(rows):
    open_rows = [r for r in rows if not r.get("handled")]
    lines = ["# Reject ki wajah - jo abhi sudhaari nahi gayi", "",
             "Ye file apne-aap banti hai (sy_feedback.py). Asli data "
             "feedback.jsonl mein hai.", ""]
    if not open_rows:
        lines.append("Abhi koi baaki nahi.")
    for r in open_rows:
        c = r.get("context") or {}
        lines.append("## %s - %s" % (r.get("at", ""), r.get("story_id", "")))
        lines.append("- beat: %s | headline: %s" % (c.get("beat"), c.get("headline_hi")))
        # '%' pehle lagta hai, 'or' baad mein - isliye pehle "(button nahi
        # dabaya)" kabhi nahi dikhta tha, bas "wajah: " khaali (st_9699961).
        labs = ", ".join(_label(x) for x in r.get("reasons") or [])
        lines.append("- wajah: %s" % (labs or "(button nahi dabaya)"))
        for n in r.get("notes") or []:
            lines.append("- aapke shabd: \"%s\"" % n)
        for sh in c.get("shots") or []:
            lines.append("  - drishya %s: %s <- %s (%s)" % (
                sh.get("n"), (sh.get("brief") or "")[:70],
                sh.get("source") or ("studio" if sh.get("studio") else "-"),
                ", ".join(sh.get("queries") or [])[:60]))
        lines.append("")
    with open(MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def record_reject(story):
    """Reject hote hi ek khaali entry - wajah baad mein judti hai. Isse
    button na dabaane par bhi pata rehta hai ki kya reject hua tha."""
    try:
        rows = _load()
        sid = str(story.get("story_id") or "")
        rows.append({"story_id": sid, "at": time.strftime("%Y-%m-%d %H:%M"),
                     "reasons": [], "notes": [], "handled": False,
                     "context": _context(story)})
        _save(rows)
    except Exception as e:
        log("reject darj nahi hua:", e)


def _update(sid, reason=None, note=None):
    rows = _load()
    for r in reversed(rows):
        if r.get("story_id") == sid and not r.get("handled"):
            if reason and reason not in r.setdefault("reasons", []):
                r["reasons"].append(reason)
            if note:
                r.setdefault("notes", []).append(note[:800])
            _save(rows)
            return True
    return False


def on_button(payload, cb_id, message):
    """payload = "code|story_id"."""
    import sy_store as st
    import sy_telegram
    code, _, sid = str(payload).partition("|")
    ok = _update(sid, reason=code)
    if code == "other":
        txt = "Theek hai - neeche ek line mein likh dijiye"
    else:
        txt = "Darj kiya: %s. Ek line likhna chahein to likh dijiye." % _label(code)
    try:
        sy_telegram._post("answerCallbackQuery",
                          {"callback_query_id": cb_id, "text": txt[:190]},
                          timeout=30)
    except Exception:
        pass
    # Pending ko taaza rakho - ab jo likhenge wo isi par judega.
    st.kv_set(PENDING_KEY, {"sid": sid, "at": time.time(),
                            "msg": int((message or {}).get("message_id") or 0)})
    if ok:
        log("wajah darj:", sid, code)


def on_text(text, reply_to=0):
    """Aapka likha hua (bina '/' ka) sandesh. True = feedback mein gaya."""
    import sy_store as st
    import sy_telegram
    p = st.kv_get(PENDING_KEY) or {}
    sid = p.get("sid")
    if not sid:
        return False
    fresh = time.time() - float(p.get("at") or 0) < NOTE_WINDOW
    is_reply = reply_to and reply_to == int(p.get("msg") or -1)
    if not (fresh or is_reply):
        return False
    if _update(sid, note=text.strip()):
        log("aapke shabd darj:", sid)
        try:
            sy_telegram.send_message("Darj kar liya - agli baar isi ko dhyaan "
                                     "mein rakh kar sudhaar hoga. 🙏")
        except Exception:
            pass
        return True
    return False


# ---------------------------------------------------------- Claude ke liye

def pending():
    """Jo abhi sudhaari nahi gayi (Claude/scheduled task ke liye)."""
    return [r for r in _load() if not r.get("handled")]


def mark_handled(story_ids, change_note):
    """Claude sudhaar ke baad chalata hai: kya badla, darj ho jaata hai."""
    rows = _load()
    ids = set(story_ids)
    for r in rows:
        if r.get("story_id") in ids and not r.get("handled"):
            r["handled"] = True
            r["handled_at"] = time.strftime("%Y-%m-%d %H:%M")
            r["fix"] = change_note
    _save(rows)


if __name__ == "__main__":
    for r in pending():
        print(json.dumps(r, ensure_ascii=False)[:600])

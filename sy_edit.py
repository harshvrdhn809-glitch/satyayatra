"""EDIT DECISION - har tukde (shot) par tay: anchor dikhegi ya footage.

Harshvardhan (Oct 2026): "production itna smart ho ki kitni der anchor
dikhna hai, kitni der footage chalna hai, aur kis scene mein - wo faisla
khud le."

Teen roop hain, jaise TV newsroom mein:
  anchor  - anchor poori screen par (patti/ticker uske upar, jaise studio)
  pip     - footage poori screen par, anchor daayein ek chhoti khidki mein
  footage - sirf footage, anchor nahi

KAB CHALTA HAI: shot list + fetch_shots ke BAAD (taaki pata ho kahan asli
drishya mila) aur sy_scenes.plan ke baad (har tukde ka asli samay aawaaz
ki timing se bandh chuka hota hai). Tab yahan se jo nikalta hai wahi
HeyGen ko bheji jaane wali aawaaz ke tukde aur render ki khidkiyan banti
hain.

DO PARAT:
  1. Claude se sujhaav - har tukde ka text, drishya kaisa mila, kitna lamba.
     Wo newsroom ke editor ki tarah sochta hai. Fail ho to koi baat nahi -
     neeche ke niyam akele bhi poora faisla le lete hain.
  2. PAKKE NIYAM - Claude kuch bhi kahe, ye hamesha lagte hain:
       - hook (pehla tukda) aur ant (aakhri tukda) anchor par
       - asli footage/tasveer achhi mili (Commons/Openverse) to footage full
       - footage kamzor/AI-chitran ho to anchor (PIP), na ho/studio ho to
         anchor full
       - naam/aankda/bayan wale tukde par anchor full nahi - footage ya
         graphic (screen ka text) dikhna chahiye; drishya na ho to PIP
       - anchor lagaataar bahut der full screen par nahi (max_run)
       - poori video mein anchor ka kul samay ek seema mein (max_total,
         max_share) - kharch bhi isi se bandhta hai
Ye file koi network/ffmpeg nahi chhooti (Claude wali call chhod kar) -
isliye nakli shots se poori jaanchi ja sakti hai.
"""
import json
import re

FULL, PIP, FOOT = "anchor", "pip", "footage"
MODES = (FULL, PIP, FOOT)

# Jin srot ki tasveer US CHEEZ ki hoti hai jiski baat hai (sy_produce
# REAL_SOURCES jaisa). Pexels/Pixabay prateekatmak hain - "theek", asli nahi.
REAL = ("commons", "commons_video", "openverse")
AI = ("veo",)

# Bahut chhote tukde par khidki khulna-band hona jhatka hai.
MIN_SPAN = 1.5


def log(*a):
    print("[edit]", *a, flush=True)


# ------------------------------------------------------------ tukde ki pehchaan

def quality(sh):
    """Drishya kaisa mila: strong / ok / weak / none."""
    if sh.get("anchor_planned") or sh.get("studio") or not sh.get("file"):
        return "none"
    src = str(sh.get("source") or "")
    if src in AI:
        return "weak"
    if src in REAL:
        return "strong"
    return "ok"


# Aankda (१२३ ya 123), pratishat, rupaya, crore/lakh, ya uddharan-chinh -
# aisi baat screen par dikhni chahiye (footage ya text), sirf chehre par nahi.
_FACT = re.compile(
    r"[0-9०-९]|%|प्रतिशत|फ़ीसदी|फीसदी|करोड़|लाख|हज़ार|हजार|रुपये|₹|"
    r"[\"“”‘’]|ने कहा|ने बताया|का कहना|के मुताबिक|के अनुसार")


def has_fact(text):
    return bool(_FACT.search(str(text or "")))


def _dur(sh):
    return max(0.0, float(sh.get("end") or 0) - float(sh.get("start") or 0))


# ------------------------------------------------------------ niyam

def rule_modes(shots):
    """Sirf niyam se har tukde ka roop (Claude ke bina bhi poora faisla)."""
    out = []
    n = len(shots)
    for i, sh in enumerate(shots):
        q = quality(sh)
        if q == "strong":
            m = FOOT
        elif q == "ok":
            m = FOOT
        elif q == "weak":
            m = PIP
        else:
            m = FULL
        if i == 0 or i == n - 1:
            m = FULL if q != "strong" else PIP
        out.append(m)
    return out


def enforce(shots, modes, max_total, max_share=0.45, max_run=12.0):
    """Claude ka sujhaav ho ya nahi - pakke niyam yahan lagte hain.

    max_total: is video mein anchor (full+pip) ka zyada se zyada samay (sec).
    Lauta ta hai nayi list (modes)."""
    n = len(shots)
    if not n:
        return []
    modes = [m if m in MODES else FOOT for m in list(modes) + [FOOT] * n][:n]
    durs = [_dur(s) for s in shots]
    body = sum(durs) or 1.0

    for i, sh in enumerate(shots):
        q = quality(sh)
        # Asli, achha drishya mila hai to wahi dikhe - anchor full nahi.
        if q == "strong" and modes[i] == FULL:
            modes[i] = PIP if i in (0, n - 1) else FOOT
        # Drishya hai hi nahi (studio) - wahan footage ka matlab khaali studio.
        if q == "none" and modes[i] == FOOT:
            modes[i] = FULL
        # Naam/aankda/bayan - chehre se zyada baat screen par dikhni chahiye.
        if has_fact(sh.get("text")) and modes[i] == FULL and i not in (0, n - 1):
            modes[i] = PIP
        if durs[i] < MIN_SPAN and modes[i] != FOOT and 0 < i < n - 1:
            modes[i] = FOOT

    # Hook aur ant anchor par (agar drishya bilkul nahi to full, warna kam se
    # kam PIP - asli footage ke upar bhi chehra dikhe).
    for i in {0, n - 1}:
        if modes[i] == FOOT:
            modes[i] = FULL if quality(shots[i]) in ("none", "weak") else PIP

    # Lagaataar full anchor max_run se lamba - us daur ka ek tukda PIP par
    # (hook/ant nahi; sabse lamba pehle). Tab tak jab tak koi daur lamba na
    # bache.
    for _ in range(n):
        runs, cur = [], []
        for i in range(n):
            if modes[i] == FULL:
                cur.append(i)
            elif cur:
                runs.append(cur)
                cur = []
        if cur:
            runs.append(cur)
        bad = [r for r in runs if sum(durs[i] for i in r) > max_run]
        fixed = False
        for r in bad:
            pick = [i for i in r if i not in (0, n - 1)]
            if pick:
                modes[max(pick, key=lambda i: durs[i])] = PIP
                fixed = True
                break
        if not fixed:
            break

    # Kul seema: share aur seconds - jo kam ho.
    cap = max(0.0, min(float(max_total), body * float(max_share)))

    def total():
        return sum(d for d, m in zip(durs, modes) if m != FOOT)

    # Pehle beech ke wo anchor hatao jinke neeche koi drishya hai (PIP pehle,
    # lambe pehle) - wahan anchor hatne par bhi screen par kuch hai. Jinke
    # neeche sirf studio hai wo sabse baad (wahan anchor hatna = khaali
    # studio). Hook/ant sabse aakhir mein.
    def candidates():
        mid = [i for i in range(1, n - 1) if modes[i] != FOOT]
        mid.sort(key=lambda i: (quality(shots[i]) == "none", modes[i] == FULL,
                                -durs[i]))
        # Ant pehle, hook sabse aakhir mein - shuruaat ka chehra sabse zaroori.
        ends = [i for i in sorted({n - 1, 0}, reverse=True) if modes[i] != FOOT]
        return mid + ends

    while total() > cap + 0.01:
        c = candidates()
        if not c:
            break
        modes[c[0]] = FOOT
    return modes


# ------------------------------------------------------------ Claude

SYSTEM = (
    "Aap ek Hindi TV news channel ke senior video editor hain. Har tukde par "
    "tay kariye ki screen par anchor dikhe ya footage. Sirf JSON lautaiye.")


def _ask_claude(shots, story):
    import sy_ai
    rows = []
    for i, sh in enumerate(shots):
        rows.append({
            "i": i + 1,
            "sec": round(_dur(sh), 1),
            "drishya": quality(sh),
            "kism": str(sh.get("type") or ""),
            "text": re.sub(r"\s+", " ", str(sh.get("text") or ""))[:160],
        })
    user = (
        "Khabar: %s\n\nTukde (drishya: strong = asli tasveer/footage us cheez "
        "ki, ok = prateekatmak stock, weak = AI chitran, none = kuch nahi "
        "mila/studio):\n%s\n\n"
        "Har tukde ke liye mode chuniye:\n"
        "  anchor  = anchor poori screen par\n"
        "  pip     = footage poori screen, anchor chhoti khidki mein\n"
        "  footage = sirf footage\n"
        "TV newsroom jaisa sochiye: shuruaat (hook) aur ant anchor par; jahan "
        "asli drishya achha hai wahan footage; jahan kamzor/AI/kuch nahi "
        "wahan anchor; aankde/naam/bayan par footage ya graphic; anchor "
        "lagaataar bahut lamba nahi; anchor kul milakar video ka lagbhag "
        "ek-tihaai se zyada nahi.\n"
        'JSON: {"shots": [{"i": 1, "mode": "anchor|pip|footage", '
        '"why": "chhota karan"}]}'
        % (str(story.get("headline_hi") or "")[:140],
           json.dumps(rows, ensure_ascii=False)))
    j = sy_ai.ask_json(SYSTEM, user, max_tokens=1500)
    out = [None] * len(shots)
    for r in (j or {}).get("shots") or []:
        try:
            k = int(r.get("i")) - 1
        except Exception:
            continue
        m = str(r.get("mode") or "").strip().lower()
        if 0 <= k < len(shots) and m in MODES:
            out[k] = m
    return out


def decide(shots, story=None, max_total=40.0, max_share=0.45, max_run=12.0,
           use_ai=True):
    """Har tukde ka roop - list, shots ke kram mein. Kabhi throw nahi."""
    if not shots:
        return []
    base = rule_modes(shots)
    if use_ai:
        try:
            ai = _ask_claude(shots, story or {})
            got = sum(1 for m in ai if m)
            base = [a or b for a, b in zip(ai, base)]
            log("Claude ne %d/%d tukdon ka sujhaav diya" % (got, len(shots)))
        except Exception as e:
            log("Claude ka sujhaav nahi mila (sirf niyam):", str(e)[:150])
    modes = enforce(shots, base, max_total, max_share, max_run)
    return modes


# ------------------------------------------------------------ samay ki khidkiyan

def ranges(shots, modes, gap_merge=0.05):
    """Lagaataar anchor wale tukdon ko jodo -> [(start, end, [(s, e, mode)])].

    Ek range = HeyGen ko bheja jaane wala aawaaz ka ek tukda. Range ke andar
    roop (full/pip) badal sakta hai - chehra wahi, sirf khidki badalti hai."""
    out = []
    for sh, m in zip(shots, modes):
        if m == FOOT:
            continue
        s, e = float(sh.get("start") or 0), float(sh.get("end") or 0)
        if e - s <= 0.05:
            continue
        if out and s - out[-1][1] <= gap_merge:
            out[-1][1] = e
            out[-1][2].append((s, e, m))
        else:
            out.append([s, e, [(s, e, m)]])
    return [tuple(r) for r in out]


def describe(shots, modes):
    mark = {FULL: "A", PIP: "p", FOOT: "."}
    a = sum(_dur(s) for s, m in zip(shots, modes) if m == FULL)
    p = sum(_dur(s) for s, m in zip(shots, modes) if m == PIP)
    return "%s  (anchor %.0fs, pip %.0fs, footage %.0fs)" % (
        "".join(mark.get(m, "?") for m in modes), a, p,
        sum(_dur(s) for s in shots) - a - p)

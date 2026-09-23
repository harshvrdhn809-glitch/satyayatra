"""GitHub Actions par ek run - kuch minute kaam, phir hisaab bacha kar band.

Laptop/server par sy_main.py din-raat chalta hai. GitHub Actions par aisa
nahi ho sakta: wahan har run ek nayi, khaali machine par hoti hai, aur
workflow (.github/workflows/satyayatra.yml) use har kuch der mein chalata
hai. Isliye yahan wahi kaam hota hai jo sy_main.py ke loop mein hota hai -
bas ek tay samay (SY_BUDGET_MINUTES) tak - aur phir program saaf-saaf band
hota hai taaki database, YouTube ka token aur bani hui video agli run tak
bach sakein (wo kaam workflow karta hai).

Samay beetne ke baad naya kaam shuru nahi hota, par jo chal raha ho (jaise
video render) wo poora hota hai. YouTube ka sign-in bhi: aapke code daalne
tak run rukti hai (SY_SIGNIN_WAIT_MINUTES tak), warna sign-in adhoora reh
jaata.

Chalana:  python sy_cloud.py
"""
import os
import threading
import time

os.environ.setdefault("SY_CLOUD", "1")

import sy_config as cfg  # noqa: E402
import sy_main  # noqa: E402
import sy_store as st  # noqa: E402


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, flush=True)


def _minutes(name, default):
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except ValueError:
        return float(default)


def wait_for_signin(limit_s):
    """YouTube sign-in ek alag dhaage mein chalta hai (sy_main._ask_signin).
    Run khatam hone se pehle usse poora hone dete hain."""
    end = time.time() + limit_s
    for t in threading.enumerate():
        if t is threading.current_thread() or not t.is_alive():
            continue
        left = end - time.time()
        if left <= 0:
            log("sign-in ka intezaar khatam - agli run mein phir poochha jayega")
            return
        log("sign-in poora hone ka intezaar (%d minute tak)..." % (left // 60))
        t.join(left)


def ask_signin_if_missing():
    """Token hi na ho (cloud ki pehli run) to sign-in pehle se maang lo.

    Warna pehli video approve hone tak koi poochhta hi nahi, aur tab video
    sign-in ke intezaar mein khadi rehti. Har 6 ghante mein ek hi baar -
    har 20 minute ki run par naya code bhejna tang karna hota.
    """
    if os.path.exists(cfg.YT_TOKEN):
        return
    last = float(st.kv_get("cloud_signin_asked_ts", 0) or 0)
    if time.time() - last < 6 * 3600:
        return
    st.kv_set("cloud_signin_asked_ts", time.time())
    log("YouTube token nahi hai - Telegram par sign-in maang rahe hain")
    sy_main._ask_signin()


def close_db():
    """WAL ka saara likha hua mukhya file mein - warna bachaya gaya
    satyayatra.db adhoora ho sakta hai."""
    try:
        c = st.conn()
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.commit()
        c.close()
    except Exception as e:
        log("database band karte waqt:", e)


def main():
    budget = _minutes("SY_BUDGET_MINUTES", 15) * 60
    signin_wait = _minutes("SY_SIGNIN_WAIT_MINUTES", 28) * 60
    started = time.time()
    log("cloud run shuru - %d minute" % (budget // 60))
    try:
        sy_main.startup()
        try:
            ask_signin_if_missing()
        except Exception as e:
            log("sign-in maangne mein gadbad:", e)
        nap = sy_main.nap_seconds()
        while True:
            sy_main.one_round()
            if time.time() - started + nap >= budget:
                break
            time.sleep(nap)
        log(sy_main.status_line())
        wait_for_signin(signin_wait)
    finally:
        close_db()
        log("cloud run khatam (%d minute)" % ((time.time() - started) // 60))


if __name__ == "__main__":
    main()

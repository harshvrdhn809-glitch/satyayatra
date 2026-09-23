"""Abhi agla kaam karwao - schedule ka intezaar kiye bina.

Ye khud kuch nahi banata. Ye sirf wo rok hataata hai jispar system baitha
hai, jisse chalta hua start.bat apni agli baari par (20 second ke andar)
kaam utha leta hai.

Ye jaan-boojhkar aisa hai. Doosra program chala kar video banane par dono
ek hi khabar uthaa sakte the aur do video ban jaatin. Ek hi haath mein kaam
rehna chahiye.

DO BAAR YE PROGRAM "KHARAB" LAGA HAI - AUR DONO BAAR GALTI ISKI THI

Dono baar ye ghadi peeche kar deta tha aur "20 second mein video ban
jayegi" likh kar chup ho jaata tha - jabki rok ghadi ki thi hi nahi:

  pehli baar : Telegram par ek video jawab ka intezaar kar rahi thi.
  doosri baar: Telegram par VISHAY ka chunav lataka hua tha (42 minute se).

Jab tak wo lataka hai, na naya slate jaata hai aur na koi video banti hai -
aur ghadi shoonya karne se us par koi asar nahi padta.

Isliye ab ye program pehle ye dekhta hai ki rok kahan hai, saaf batata
hai, aur JO ROK HATAI JA SAKTI HAI use khud hata deta hai.
"""
import time

import sy_config as cfg
import sy_store as st

cfg.ensure_dirs()
st.conn()

print()

# ---- Rok 1: koi video jawab ka intezaar kar rahi hai.
#
# Ye rok hum nahi hata sakte - ye faisla aapka hai. Bina aapke dabaye
# channel par kuch nahi jaata, aur wo niyam yahan bhi nahi todna.
waiting = st.by_status("awaiting")
if waiting:
    print("ROK YAHAN HAI - ghadi par nahi:")
    for r in waiting:
        print("  Telegram par ek VIDEO %.1f ghante se jawab ka intezaar kar rahi hai:"
              % st.waiting_hours(r))
        print("    " + str(r.get("headline_hi") or "")[:70])
    print()
    print("  Uspar ✅ ya ❌ dabaiye - agla kaam usi ke baad hoga.")
    print("  (Ye rok ye program nahi hata sakta - faisla aapka hai.)")
    print()

# ---- Rok 2: vishay ka chunav lataka hua hai.
#
# Ye rok hata sakte hain, aur "abhi" ka matlab yahi hai: purana slate
# hatao, antar ka niyam bhi hatao, taaki turant naye vikalp jayein.
off = st.kv_get("offer")
if off:
    mins = (time.time() - float(off.get("at") or 0)) / 60.0
    print("Telegram par VISHAY ka chunav %.0f minute se lataka hua tha:" % mins)
    for i, it in enumerate(off.get("items") or []):
        print("  %d. %s" % (i + 1, str(it.get("label") or "")[:64]))
    st.kv_set("offer", None)
    st.kv_set("offer_last_at", 0)
    print()
    print("  Wo hata diya. Naye vikalp abhi bheje jayenge.")
    print()

# Chuna hua vishay banne ka intezaar kar raha ho to us nishan ko bhi
# hata dete hain - warna wo bhi ek chupi hui rok ban jaata hai.
st.kv_set("offer_chosen", None)

# 'failed' par ruki khabrein sahi jagah wapas.
#
# Bani hui video ko dobara banwana sabse mehnga nuksaan hai - isliye jiski
# file disk par maujood hai wo seedhe upload ki katar mein jaati hai.
up, new = st.revive_failed()
if up:
    print("%d bani hui video wapas upload ki katar mein" % up)
if new:
    print("%d adhoori khabar wapas queue mein" % new)

# Ghadi shoonya - agli baari abhi.
st.kv_set("last_produce", 0)
st.kv_set("offer_last_at", 0)

# AAJ KI UPLOAD-JAGAH BHAR CHUKI HO TO BHI - "ABHI" KA MATLAB ABHI HAI.
#
# Roz ki seema (bulletin/reel/khabar jitni jagah rok chuke) production ko
# aam din mein rok deti hai, aur wo sahi hai - warna agle din tak bacha
# hua kaam "kal ki khabar" ban jaata. Par jab aap khud "abhi" dabate hain
# to matlab saaf hai: intezaar nahi karna. Isliye ye ek nishan chhod dete
# hain jo sy_main.py ke production_allowed() ko is EK koshish ke liye
# seema bhula deta hai - istemal hote hi khud mit jaata hai, agli baari se
# seema jaisi thi waisi hi wapas lagti hai.
st.kv_set("produce_bypass_cap_once", 1)
print("Aaj ki upload-seema is ek koshish ke liye hata di gayi hai.")

blocked = st.count_status("no_visual")
if blocked:
    print("%d khabrein isliye chhodi gayi thi kyunki unka drishya nahi mila."
          % blocked)
    print("(Ye galti nahi hai - bina sacchi tasveer ke khabar nahi jaani")
    print(" chahiye. Ye sirf jaankari ke liye.)")
    print()

pending = st.count_status("pending")
if pending:
    print("katar mein khabrein:", pending)
if not pending:
    # Koi khabar hi nahi hai to pehle khabar dhoondhni padegi.
    st.kv_set("last_news", 0)
    st.kv_set("last_yojana", 0)
    print("katar khaali thi - pehle khabar dhoondhi jayegi.")

if not waiting:
    print()
    print("start.bat 20 second ke andar Telegram par naye vikalp bhej dega.")
    print("Unme se ek dabaiye - usi par video banegi.")

print()
for s in ("pending", "producing", "awaiting", "approved", "published"):
    n = st.count_status(s)
    if n:
        print("  %-10s %d" % (s, n))

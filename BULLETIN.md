# Bulletin - roz shaam ki teen "das khabrein ek video mein"

## Ye hai kya

Pehle: ek khabar, ek video. Din bhar mein jitni khabrein aati thi unka
bahut chhota hissa hi channel par ja paata tha, kyunki YouTube upload ka
kota seemit hai (`config.ini` -> `[limits] max_uploads_per_day`).

Ab: teen bulletin, roz shaam -

- **मिर्ज़ापुर** ki das zaroori khabrein
- **प्रयागराज** ki das zaroori khabrein
- **उत्तर प्रदेश** (poore pradesh ki mili-julti) das zaroori khabrein

Har bulletin EK video hai (har khabar 10-15 second ki, poori video ~3
minute) aur EK hi Telegram approval maangta hai - das alag khabron ki
tarah das baar poochha nahi jaata. Isse kam upload mein zyada khabrein
cover ho jaati hain, aur aajkal ke chhote attention span ke liye bhi
zyada theek baithta hai.

Bulletin ban kar Telegram par turant chala jaata hai - din bhar ki upload
seema (`max_uploads_per_day`) isse kabhi nahi rokti, kyunki ab wo seema
BANANE ke waqt lagti hai, upload ke waqt nahi (`sy_main.py` ka
`production_allowed()`). Isi wajah se bulletin apne tay kiye ghante par
hi chalta hai, kisi doosri, kam zaroori khabar ki wajah se agle din tak
nahi khinchta.

Bulletin ke intro/outro par ek AI anchor bhi lagaya ja sakta hai - alag
feature, off by default, poora tareeka **ANCHOR.md** mein hai.

Purani "kaam ki baat", "gyan", "yojana" wali videos **waisi hi chalti
rahengi** - bulletin unki jagah nahi leta, sirf khabar wale hisse ko
badalta hai.

## Ye kaam kaise karta hai (agar kabhi dekhna pade)

Naya file: `sy_bulletin.py`. Ye render pipeline (`sy_produce`, `sy_media`,
`sy_scenes`, `render_core`, `thumb`, `sy_telegram`, `sy_youtube`,
`sy_social`) ko **bilkul nahi chhedta** - bulletin bhi ek normal "story"
row hi hai, bas uski script mein das khabrein jud jaati hain. Baaki sab
wahi purana, pehle se aazmaya hua rasta hai.

1. `tick_bulletin()` (`sy_main.py`) har loop mein dekhta hai ki kisi area
   ka waqt ho gaya hai aur aaj uska bulletin nahi bana.
2. `sy_bulletin.build(area)` us area ke shehar(on) ki aaj ki khabrein
   Amar Ujala ke RSS se uthata hai (`sy_ingest.normalise()` - koi nayi
   feed nahi, jo pehle se hai wahi).
3. AI (`sy_ai.ask_json`) inmein se das sabse zaroori chunta hai aur har
   ek ko ek chhoti bolne-layak line mein samet deta hai.
4. Sab lines jodkar ek script ban jaati hai, aur ye ek naye `beat:
   "bulletin"` ke saath queue mein chali jaati hai.
5. `_force_add()` ise agli hi khaali baari mein sabse aage laga deta hai
   (`/khabar` jaisa hi tareeka) - taaki wo turant bane, purani khabron ki
   kataar mein na phanse.
6. Uske baad sab kuch waisa hi hai jaisa kisi bhi khabar ke liye hota
   hai: art direction, drishya (photo/AI), aawaaz, video, thumbnail,
   Telegram approval, YouTube upload, aur agar chalu hai to Facebook/
   Instagram.

## Footage ka niyam yahan halka hai - jaan-boojhkar

Ek khabar ki video mein sakht niyam hai: kam se kam do sacchi tasveerein
(`sy_produce.py` ka `visual_verdict`). Das khabron wale bulletin mein
itna sakht rakhne se aadhi khabrein chhoot jaatin - kyunki har chhoti
khabar ke liye do achhi sacchi tasveerein milna mushkil hai.

Isliye bulletin ka beat naam "bulletin" hai, jo `SOFT_BEATS`, `REEL_BEATS`
ya `KHABAR_BEATS` kisi mein nahi hai - to `visual_verdict()` use apne aap
"gyan/kaam ki baat" wale halke niyam se naapta hai: **ek achhi
tasveer/AI illustration kaafi hai**. Ye jaan-boojhkar kiya gaya hai, kisi
bug se nahi.

## Chalu karna

Sab kuch **band** hai jab tak aap chalu na karein:

```
[bulletin]
enabled = 0
```

Telegram se (asaan tareeka):

```
/bulletin on
/bulletin off
/bulletin          <- abhi ka haal (kaunsa area kis waqt, aaj kya ban chuka)
```

Turant ek banwa kar dekhne ke liye, waqt ka intezaar kiye bina:

```
/bulletin mirzapur
/bulletin prayagraj
/bulletin up
```

Isse turant us area ka bulletin banna shuru ho jaata hai aur approval
Telegram par aa jaata hai - schedule chalu karne se pehle ek baar dekh
kar tasalli karne ke liye.

## Waqt set karna

`config.ini` mein:

```
[bulletin]
hour_mirzapur = 17
hour_prayagraj = 18
hour_up = 19
```

24-ghante wale ankde, is computer/server ke apne samay mein. Aapne
teeno ko ek-ek ghante ke antaral par rakhne ko kaha tha, isliye 17/18/19
udaharan ke roop mein diye hain - apni suvidha ke hisaab se badal
dijiye. `0` rakhne par wo area kabhi khud nahi chalega (bas `/bulletin
<area>` se haath se banega).

Har area din mein sirf **ek baar** banta hai - agar bulletin ban chuka
hai to wahi waqt dobara aane par dobara nahi banega (agle din tak).

## Test kaise karein, poora chalu karne se pehle

1. `config.ini` mein `[bulletin] enabled = 0` hi rehne dijiye abhi ke
   liye.
2. Program chalu kijiye jaisे hamesha karte hain.
3. Telegram par `/bulletin mirzapur` bhejiye.
4. Kuch minute mein approval aayega - dekhiye khabrein sahi hain, aawaaz
   theek hai, tasveerein/AI drishya theek lag rahe hain.
5. Sahi lage to Telegram par `/bulletin on` bhejiye aur `hour_*` set
   kar dijiye - ab roz shaam apne-aap chalega.
6. Kuch din chala kar dekhne ke baad, agar chahein to purani ek-khabar
   wali line (`[schedule] news_in_every`) ko dheere-dheere badha sakte
   hain ya `0` kar sakte hain - lekin jaldi mat kijiye, pehle bulletin
   ko akele bhi kuch din chala kar dekh lijiye.

## Agar kuch galat lage

- Bulletin band karne ke liye turant: `/bulletin off`
- Ek area ka bulletin khaali/kharab bane to us din wo area chhod diya
  jaata hai (khabrein kam hongi to `build()` khud "chhod rahe hain" kehkar
  ruk jaata hai, koi khaali video nahi banti) - agle din phir koshish
  hoti hai.
- Kisi bhi gadbad se `tick_bulletin()` poora program nahi girata - wo
  apne alag try/except mein hai, jaisa har dusra tick.

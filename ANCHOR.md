# AI anchor - bulletin ke intro/outro par ek chehra

## Ye hai kya

Bulletin ki shuruaat mein "नमस्कार, देखिए ... की आज की ज़रूरी ख़बरें" aur
ant mein "...बने रहिए" - itne hisse mein ab ek AI kirdaar screen par bol
sakta hai. Beech ki das khabrein bilkul waisi hi rehti hain jaisi bina
anchor ke bhi hoti hain - Sarvam ki aawaaz, wahi drishya, wahi sab kuch.
Anchor sirf shuruaat aur ant ke 6-8 second ka hissa hai, poori 3-minute
ki video ka nahi.

**FILHAAL TALA HUA HAI (Sep 2026).** Do alag photoreal tasveeron se
`/anchor test` try kiya gaya - dono baar Veo ne EXACT wahi error diya:
"input image violates Vertex AI's usage guidelines" (support code
15236754). Ye Google Veo ka apna, categorical suraksha filter lagta hai
- kisi bhi photoreal insaani chehre ko image-se-video (deepfake rokne ke
liye) seedha rok deta hai, chahe tasveer kaisi bhi ho. Ye humare code se
theek nahi ho sakta.

Isliye anchor abhi ke liye rok diya gaya hai - bulletin aur evergreen
(kaam/gyan/yojana) videos bina anchor ke, pehle jaisi hi chalti hain.
Code (`sy_anchor.py`) waisa hi pada hai, off by default - agar kabhi
aage badhna ho to do raste khule hain: (1) neeche wala stylized/graphic
anchor - ye kaam karta hai, sirf quality behtar karni thi; (2) HeyGen/
D-ID jaisi dedicated avatar service, jo photoreal avatar ke liye bani
hain aur shayad UPI/debit se chal jaayein.

Neeche ka baaki hissa us waqt ke liye hai jab anchor par dobara kaam
shuru ho.

## Chehra kahan se aata hai

Anchor ki EK tasveer `anchor_reference.jpg` naam se `C:\SatyaYatra` mein
rakhi jaati hai, aur uske baad ROZ wahi tasveer istemal hoti hai - taaki
chehra badalta na rahe aur ek pehchan bane. Ye tasveer do tarah se aa
sakti hai:

1. **Aap khud ek tasveer de dijiye** - jo chehra chahiye (photoreal ho
   sakta hai) use `anchor_reference.jpg` naam se seedha `C:\SatyaYatra`
   mein rakh dijiye (16:9, jaisi wide tasveer chahiye, waise hi behtar
   dikhegi). Anchor code khud kuch nahi banayega, seedha isi tasveer se
   kaam chalega.
2. **Kuch na diya ho to khud ban jaati hai** - pehli baar chalne par (ya
   `/anchor test` se) Vertex AI se ek saaf 3D/graphic style ka kirdaar
   ban jaata hai - jaan-boojhkar photoreal NAHI, taaki bina kisi tasveer
   diye bhi anchor kaam kare.

Jo bhi raasta ho, tasveer kisi **asli, pehchaane jaane wale, jeevit ya
naamdaar vyakti** ki nahi honi chahiye - ek naya/kalpanik chehra hona
chahiye, chahe wo photoreal lage ya na lage. Photoreal chehra istemal
karne par description mein AI-anchor disclosure line apne aap jud jaati
hai (neeche dekhiye) - ye YouTube ke synthetic-content niyam ke saath
mel khaane ke liye zaroori hai.

## Ye sy_veo.py ke "AADMI KABHI NAHI" niyam se kaise mel khaata hai

`sy_veo.py` mein ek sabse zaroori usool hai: khabar/gyan/kaam ke
DRISHYA (illustration/B-roll) mein kabhi koi insaan nahi banta, kyunki
wahan kisi asli ghatna ki AI-nakli tasveer dikhana channel ke apne sach
ke usool se takrata hai.

Anchor is niyam ko **todta nahi** - ye ek bilkul alag cheez hai. Ek
maana-hua, saaf-saaf synthetic KIRDAAR (jaise ek virtual presenter)
kisi asli ghatna ya asli vyakti ki nakal nahi hai. Isliye anchor ka
code (`sy_anchor.py`) ek naya, alag file hai jismein iske liye alag
niyam hai - `sy_veo.py` ko haath tak nahi lagaya gaya, aur khabar/gyan/
kaam ke chitran mein "AADMI KABHI NAHI" bilkul waisa hi kaayam hai jaisa
pehle tha.

## Test kaise karein - bina poora bulletin banaye

```
/anchor test
```

Isse turant (a) anchor ki tasveer Telegram par aayegi, aur (b) ek chhota
namune ka clip ("नमस्कार, मैं आपका AI समाचार एंकर हूँ") bhi bhej diya
jaayega - aawaaz sahit. Ismein 2-3 minute lag sakte hain. Ye sirf jhalak
hai, kisi kote ya bulletin se juda nahi.

Chehra aur aawaaz pasand aaye to:

```
/anchor on
```

Uske baad har bulletin mein automatically intro/outro par anchor
lagega - bina kuch aur kiye.

Band karna ho to:

```
/anchor off
```

## Kharch - alag kota

Anchor ka apna alag din-bhar ka kota hai (`config.ini` mein `[anchor]
max_per_day`, default 6), jaankari-chitran (`[veo] max_per_day`) se
BILKUL ALAG - taaki teen bulletin (roz 2 clip = intro+outro = 6) us
doosre kaam ka kota na khaayein. Dono ka paisa usi Vertex AI credit se
katta hai (₹28,690, 29 Nov 2026 tak).

Kota poora ho jaaye ya kisi bhi wajah se clip na bane, to us din ka
bulletin bina anchor ke hi chala jaata hai - kabhi rukta nahi.

## Description mein disclosure

Jab bhi anchor us din bolne wala ho, YouTube description mein ye line
apne aap jud jaati hai: "इस वीडियो में शुरुआत और अंत में एक AI-जनित
डिजिटल एंकर का इस्तेमाल किया गया है।" - taaki channel ka apna transparency
ka usool yahan bhi kaayam rahe.

## Agar kabhi galat lage

- Turant band: `/anchor off`
- `/anchor` (bina kuch likhe) haal dikha deta hai - aaj kitne clip bane,
  reference tasveer bani hai ya nahi.
- Kisi bhi gadbad (reference na bane, clip na bane, jodne mein dikkat)
  se poora bulletin nahi rukta - us din bas anchor chhoot jaata hai aur
  bulletin pehle jaisa (bina anchor) chala jaata hai. Log mein wajah
  likhi milegi.

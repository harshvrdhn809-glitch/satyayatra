# SatyaYatra — GitHub Actions par (laptop aur server ke bina)

Poora pipeline ek **public** GitHub repo mein chalta hai. Public isliye ki
public repo par GitHub Actions ke minute muft hain; private repo par mahine
ke 2,000 minute is kaam ke liye kam padte hain.

Public hone ka matlab: **code sabko dikhta hai, chaabiyan kisi ko nahi.**
Saari chaabiyan GitHub Secrets mein rehti hain. Run ke beech ka hisaab
(database, YouTube token, bani hui video) `STATE_KEY` se band hokar GitHub
ke cache mein jaata hai.

---

## Kaise chalta hai

`.github/workflows/satyayatra.yml` har 20 minute ek run chalata hai:

1. Nayi machine: ffmpeg, Devanagari font, Python package.
2. Pichhla hisaab cache se nikalta hai aur khulta hai (`cloud/state.sh unpack`).
3. `config.cloud.ini` → `config.ini`. Chaabiyan Secrets se environment ke
   raaste aati hain (`SY__<SECTION>__<KEY>`).
4. `sy_cloud.py` ~15 minute tak wahi kaam karta hai jo laptop par
   `sy_main.py` karta tha. Samay khatam hone ke baad naya kaam shuru nahi
   hota, par chalta hua render poora hota hai.
5. Hisaab dobara band hokar cache mein jaata hai. Ye tab bhi hota hai jab
   program beech mein gir jaye.

Laptop se farq:

- **Button ka jawab turant nahi.** Aapka button dabana agli run mein
  uthta hai. Zyada se zyada ~20–30 minute lagte hain, kyunki GitHub ki
  ghadi aksar 5–15 minute der se chalti hai.
- **`/naya` aur `/dobara` ki zaroorat nahi.** Har run taaza code se hi
  chalti hai. Repo mein badlav push kijiye, agli run use utha legi.
- **Samay India ka hai** (`TZ=Asia/Kolkata`), isliye bulletin ke ghante
  waise hi chalenge.

---

## Ek baar ka setup

### 1. Telegram bot — Camp Kelang wala NAHI

SatyaYatra ka bot **alag** hona chahiye. Program shuru hote hi bot ka
webhook hata deta hai. Wahi bot Camp Kelang ke Netlify listener par laga
ho to GBP ke Approve/Reject button kaam karna band kar denge.

### 2. YouTube — laptop wali do files

Laptop par YouTube do files se chalta hai. Dono ka poora text Secrets mein
jaata hai (Notepad mein kholiye, sab copy kijiye, Secret mein paste kijiye):

| laptop ki file (`C:\SatyaYatra\`) | Secret |
|---|---|
| `client_secret_....json` (Google Cloud se download ki hui) | `YOUTUBE_CLIENT_SECRET_JSON` |
| `youtube-token.json` | `YOUTUBE_TOKEN_JSON` |

Bas itna. Cloud ussi token se chalega, naya sign-in nahi chahiye.

**Har 7 din:** Google ki OAuth app abhi "Testing" mein hai, isliye token
har 7 din mein bekaar ho jaata hai (laptop par bhi yahi hota tha). Tab
Telegram par sandesh aayega. Laptop par `signin.bat` chalaiye, aur nayi
`youtube-token.json` ka text `YOUTUBE_TOKEN_JSON` Secret mein **dobara
daal dijiye**. Agli run naya token utha legi. Secret ka text badalte hi
wo purane token ki jagah lag jaata hai.

**Bina laptop ke (vaikalpik) - "TV" client:** Google Cloud Console →
APIs & Services → Credentials → Create Credentials → OAuth client ID →
**TVs and Limited Input devices**. Iska `client_id` aur `client_secret`
`YOUTUBE_DEVICE_CLIENT_ID` / `YOUTUBE_DEVICE_CLIENT_SECRET` Secrets mein
daaliye, aur Telegram par `/signin` likhiye. Program Telegram par ek code
bhejega, aap phone par daal denge. Uske baad har 7 din wala sign-in bhi
phone se hi hoga.

### 3. STATE_KEY banaiye

Ek lamba, random password. Masalan kisi bhi terminal mein:

```
openssl rand -base64 32
```

Ise kahin surakshit bhi likh lijiye. **Badal diya to purana hisaab nahi
khulega.** Tab run jaan-boojhkar ruk jaati hai, taaki khaali hisaab purane
hisaab ke upar na chadh jaye.

### 4. Secrets bhariye

Repo → Settings → Secrets and variables → Actions → New repository secret

| Secret | Zaroori? | Kya hai |
|---|---|---|
| `STATE_KEY` | **haan** | upar wala password |
| `ANTHROPIC_API_KEY` | **haan** | Claude |
| `SARVAM_API_KEY` | **haan*** | aawaaz (Sarvam) |
| `ELEVENLABS_API_KEY` | * | aawaaz, agar `config.cloud.ini` mein `[tts] provider = elevenlabs` |
| `SATYAYATRA_TELEGRAM_BOT_TOKEN` | **haan** | SatyaYatra bot (alag bot!) |
| `SATYAYATRA_TELEGRAM_CHAT_ID` | **haan** | aapki chat ka number |
| `YOUTUBE_CLIENT_SECRET_JSON` | **haan** | laptop ki `client_secret_....json` ka text (kadam 2) |
| `YOUTUBE_TOKEN_JSON` | **haan** | laptop ki `youtube-token.json` ka text (kadam 2) |
| `YOUTUBE_DEVICE_CLIENT_ID`, `YOUTUBE_DEVICE_CLIENT_SECRET` | nahi | sirf phone se sign-in ke liye (kadam 2) |
| `CONTACT_EMAIL` | **haan** | Wikimedia ke liye pehchaan; iske bina Commons band |
| `PEXELS_API_KEY` | sujhaav | chalti footage |
| `PIXABAY_API_KEY` | nahi | ek aur stock source |
| `GCP_SA_JSON` | nahi | Veo/Vertex service account — poori JSON file ka text |
| `FB_PAGE_ID`, `FB_TOKEN`, `IG_USER_ID`, `GCS_BUCKET` | nahi | Facebook/Instagram (SOCIAL.md) |
| `HEYGEN_API_KEY` | nahi | HeyGen anchor - hont milte hue (neeche "HeyGen anchor") |
| `HEYGEN_AVATAR_ID` | nahi | sirf agar dashboard mein photo avatar banaya ho |
| `HEYGEN_LOOK_SERIOUS`, `HEYGEN_LOOK_NEUTRAL`, `HEYGEN_LOOK_POSITIVE` | nahi | Fatafat Reel - presenter ke teen look (neeche "Fatafat Khabar") |

\* Sarvam ya ElevenLabs, dono mein se ek.

Baaki settings (veo chalu ya nahi, kitni der mein kya chale) `config.cloud.ini`
mein hain. Wahan **kabhi chaabi mat likhiye** — wo file sabko dikhti hai.

### 5. Pehli jaanch

Actions → SatyaYatra → Run workflow → `mode = check`.
`sy_check.py` chalega: sab hara hona chahiye. YouTube sign-in par "dhyaan"
aana theek hai.

### 6. Laptop band, phir pehli run

**Cloud chalu karne se PEHLE laptop wala SatyaYatra band kijiye** (window
band, Task Scheduler se bhi hata dijiye). Dono ek saath chale to dono ek
hi Telegram bot se sandesh kheenchenge. Tab ek ka button doosre ko milega,
aur ek hi khabar do baar ban ya chadh sakti hai.

Phir Actions → SatyaYatra → Run workflow → `mode = run`. Ya agli 20 minute
wali run ka intezaar kar lijiye.

---

## Lambi video (8-10 minute) - `sy_long.py`

Ek din chhod kar ek lambi video: kisi BADE, CHALTE MAAMLE ki poori kahani -
maamla kya hai, kahan se shuru hua, vipaksh/aalochak kya keh rahe hain aur
sarkar/sanstha ka jawab kya hai, ab tak ka taaza update, aage kya. Settings
`config.cloud.ini` ke `[long]` mein.

**Mudda kaise chuna jaata hai:** trending SHABD nahi (wo ek din ka uchhaal
hota hai). Pichhle 3 din ke rashtriya akhbaaron ke shirshak padhe jaate hain,
Claude unme se wo maamle chhaantta hai jo kai din se, kai akhbaaron mein
chal rahe hain aur jinme vivad ya bada asar ho. Phir GDELT se pakka hota hai:
kam se kam 4 akhbaar aur 2 din. Google/YouTube/X sirf halka ishaara hain.
Sabse seedha: Telegram par **`/lambi <vishay>`** (jaise `/lambi chunav
aayog par vivad`) - bina vikalp ke seedha usi par video.

**Kaise chalti hai**

1. `start_hour` (7 baje) ke baad Telegram par 2-3 mudde aate hain, har ek ke
   saath ye ki wo kahan-kahan trend kar raha hai. Button dabaiye. 60 minute
   jawab na aaye to sabse upar wala khud chuna jaata hai. "Aaj lambi video
   nahi" dabane par kal phir poochha jaata hai.
2. 6-10 akhbaar ke lekh + Wikipedia ki prishthbhoomi se Claude apni script
   likhta hai (hook, poori kahani, timeline, kaun-kaun, dono paksh, aankde,
   asar, aage kya). Ek alag jaanch har vaakya ko srot se milati hai.
3. 40-60 drishya: pehle asli tasveer/footage. Jahan na mile wahan Veo ka
   prateekatmak 2D cartoon, screen par "AI चित्रण". Cartoon mein kalpanik
   kirdaar ho sakte hain, par kisi asli vyakti ki shakl kabhi nahi.
4. Render ke baad Telegram par **chhoti jhalak** (480p, 50 MB se kam - bot
   isse badi file nahi bhej sakta; poori na samaye to pehle 3 minute),
   thumbnail aur YouTube chapters. **✅ Publish** dabate hi POORI video
   (1080p) YouTube par unlisted jaati hai. 24 ghante jawab na aaye to
   video chhod di jaati hai (publish nahi).

Ye kaam **kai run mein** banta hai (mudda → script → drishya → cartoon →
render). Poore kaam mein aam taur par 2-5 ghante lagte hain - approval
wala sandesh usi din dopahar tak aa jaana chahiye. `/lambi` likh kar haal
dekhiye.

**Din ki ginti:** lambi video bhi `max_uploads_per_day` (4) mein ginti hai.

**Kharch (andaaza):** Veo cartoon sirf un tukdon par jinka asli drishya na
mile - aam taur par 10-25 clip, har clip 8 second. `veo-3.1-fast` par bina
aawaaz ~$0.10/second yaani ~$0.80 prati clip - ek lambi video par lagbhag
$8-20 (Google Cloud credit se). Pakka daam Google Cloud ki Vertex AI pricing
par dekhiye. Chhat: `veo_max_per_video` (40). Iske alawa Claude (script,
jaanch, shot list, tasveer-jaanch) aur aawaaz (~8,000 akshar) ka kharch.

**Band/chalu:** `/lambi off` / `/lambi on`. Sirf cartoon rokna ho to
`[long] veo = 0` (tab bina asli drishya wale tukdon par studio chalega).
Telegram ka `/veo off` lambi video ka cartoon bhi rokta hai. Turant ek
banwani ho to `/lambi abhi`; chalti hui rokni ho to `/lambi radd`.

**Koi naya Secret nahi chahiye.** Cartoon ke liye wahi `GCP_SA_JSON` jo
Veo ke liye hai. X ke trend `trends24.in` ke sarvajanik safhe se aate hain -
wo site badle ya ruke to bas X wala hissa chup-chaap chhoot jaata hai.
Facebook ka koi sarvajanik trend data nahi hai, isliye wo shaamil nahi.

**Samay:** workflow ka `timeout-minutes` 180 hai - lambi video ka render
(aawaaz + 10 minute render + end-card + jhalak, ~20-30 minute) ek hi run
mein hota hai. Kachcha saamaan (`work/lv_...`) render ke turant baad mit
jaata hai; upload/reject ke baad final video bhi.

---

## HeyGen anchor - hont milte hue (lip-sync)

Video mein channel ki wahi presenter (end-card wali) ab **khud bolti hui**
dikh sakti hai - hont hamari hi Sarvam wali aawaaz se milte hain. Aawaaz
nahi badalti; HeyGen sirf chehra/hont banata hai. Code: `sy_heygen.py`
(HeyGen), `sy_edit.py` (edit decision), `render_core.py` (khidkiyan).

**Kaun tay karta hai ki anchor kab dikhe:** har video ke liye, shot list
aur drishya dhoondhne ke BAAD (taaki pata ho kahan asli footage mila) aur
aawaaz banne ke baad (taaki har tukde ka asli samay pata ho). Har tukde par
teen mein se ek:

- **anchor** - anchor poori screen par (patti/ticker uske upar, jaise studio;
  us dauran neeche ke bole-shabd nahi)
- **pip** - footage poori screen, anchor daayein chhoti khidki mein
- **footage** - sirf footage

Claude newsroom editor ki tarah sujhaav deta hai, phir pakke niyam lagte
hain (Claude kuch bhi kahe): shuruaat aur ant anchor par; asli
footage/tasveer mili ho to footage; AI-chitran par PIP, studio/kuch nahi par
anchor; aankde/naam/bayan wale tukde par anchor poori screen par nahi;
anchor lagaataar 12 second se zyada poori screen par nahi; aur kul anchor
`[heygen] max_seconds_short` (30s) aur video ka 45% - jo kam ho. Lambi
video mein `max_seconds_long` (90s) aur 15%.

**Chalu karna (ek baar):**

1. app.heygen.com → Settings → API → naya key. Use Secret
   `HEYGEN_API_KEY` mein daaliye. (API ke credit plan ke credit se alag
   ho sakte hain - HeyGen ki billing dekhiye.)
2. Telegram par `/heygen on`. Haal: `/heygen`. Band: `/heygen off`.
3. Actions → Run workflow → `mode = check` - "HeyGen chaabi: chal rahi hai"
   aana chahiye (ye jaanch muft hai, koi video nahi banti).

**Chehra:** koi avatar banana zaroori nahi. Program end-card presenter
(`assets/endcard_presenter.mp4`) ka ek saaf frame EK baar HeyGen par chadhata
hai (asset id database mein yaad) aur har video mein wahi tasveer bolti hai
(HeyGen ka "image" video) - tasveer wahi, to chehra wahi. HeyGen ka asli
"photo avatar" API se ban to sakta hai, par HeyGen ke niyam ke mutaabik use
video mein lagaane se pehle **consent** (browser mein, recording ke saath)
chahiye - wo program khud nahi kar sakta. Agar aap chahein: HeyGen dashboard
→ Avatars → Create → Photo avatar, wahi tasveer daaliye, consent poora
kijiye, aur us avatar (look) ka id Secret `HEYGEN_AVATAR_ID` mein daaliye -
tab wahi avatar chalega.

**Kharch kaise ginein:** HeyGen minute ke hisaab se credit leta hai. Hum
POORI aawaaz nahi bhejte - sirf un tukdon ki jahan anchor dikhegi, ek hi
file mein jod kar (beech mein 0.4s chuppi). Isliye:

- ek chhoti video: ~10-30 second anchor (log mein: "HeyGen ko 14.0s ki
  aawaaz bheji")
- din ki pakki seema `[heygen] max_minutes_per_day` (3 minute) - iske baad
  us din anchor nahi, video purane raste se
- andaaza: `credit = (aaj ke second / 60) × HeyGen ka prati-minute rate`.
  Rate engine par nirbhar hai (default Avatar IV); HeyGen ke skill docs
  Avatar V ke liye ~6 credit/minute batate hain - apne plan ka pakka rate
  help.heygen.com ke "API pricing" par dekhiye. `/heygen` aaj ke second
  dikhata hai.
- Wahi aawaaz dobara bheji jaaye (run giri, video dobara bani) to naya
  video nahi banta - pichhla id database se.

**Kabhi nahi rukti:** switch band, chaabi nahi, seema poori, HeyGen fail ya
`wait_minutes` (20) mein video taiyaar nahi - to video bina HeyGen ke,
pehle jaisi (footage / studio, jaankari video mein Veo wala anchor). HeyGen
ki clip render ke turant baad mita di jaati hai (media cache na badhe).
Purani bolly/viral Reel par nahi - Fatafat Reel (neeche) par haan.

---

## Fatafat Khabar - 1 minute ki Reel (`sy_fatafat.py`)

Din ki sabse badi/trending **3-5 khabrein, 60 second se kam**, 9:16 mein.
Shuru mein 2-3 second ka hook ("आज की चार बड़ी ख़बरें, फटाफट"), har khabar
~10-12 second, ant mein subscribe. **Anchor hi mukhya hai** (HeyGen, wahi
end-card wali presenter) - khabar ki tasveer/clip upar chhoti khidki mein,
har khabar par bada headline card, "ख़बर 2/4" aur progress ki dhaariyaan,
aur bade Devanagari captions (log bina aawaaz dekhte hain). Settings
`config.cloud.ini` ke `[fatafat]` mein. Code: `sy_fatafat.py` (khabar,
script, tone, kram), `sy_fatafat_render.py` (9:16 render).

**Kab:** `[fatafat] hours = 8, 13, 18` - subah 8, dopahar 1 aur shaam 6
ke baad ek-ek (din mein 3 Reel).
Din ki `max_uploads_per_day` (4) mein ginti hai - jagah na ho to us baari
ki Reel nahi banti. Telegram: `/fatafat` (haal), `/fatafat on|off`,
`/fatafat abhi` (turant ek). Approval wahi ✅/❌ (Telegram par 540x960 ki
chhoti jhalak); ✅ ke baad YouTube Shorts (#Shorts), phir Facebook Page aur
Instagram Reels (`/social on` + SOCIAL.md).

**Purani bolly/viral Reel band** (`[schedule] reels_per_day = 0`) - din
ki 4 mein dono nahi samaati; "Reel jyada" ab Fatafat ki 3 baari se. Wapas
chahiye to 3 kar dijiye (aur `[fatafat] hours` kam).

**Khabrein kaise chuni jaati hain:** pichhle ~18 ghante ke rashtriya
akhbaaron ke shirshak (wahi feeds jo lambi video ke mudde ke liye) +
Google/YouTube/X trends -> Claude 3-5 alag, bade asar wali khabrein chunta
hai (pichhli Reel wali dobara nahi) -> har khabar ke 1-2 lekh khol kar
Claude chhote vaakyon mein likhta hai, **tathya sirf srot se**. Pakki
jaanch: script ka koi bhi ank srot mein na mile to wo khabar chhod di
jaati hai.

**Prasiddh vyakti ki khabar par unka hi drishya** (8 Oct 2026). Claude har
khabar ke kendra ke jaane-maane vyakti ka naam (`people_en`, srot se mel
khata hua) deta hai. Phir kram: Commons par us vyakti ki apni category ka
**video** (chalti footage) -> Wikipedia lekh ki mukhya **tasveer** ->
Commons category ki tasveer -> tab jaakar jagah/sanstha ki khoj. Sirf muft
licence wale srot - news channel / YouTube ki footage nahi (copyright
strike). Bahut se logon ka Commons par video hota hi nahi - tab unki asli
tasveer (chehra upar rakh kar, halki chaal ke saath) aati hai.

**Stock footage ke liye do muft chaabiyan zaroor daaliye:** `PEXELS_API_KEY`
(pexels.com/api) aur `PIXABAY_API_KEY` (pixabay.com/api/docs). Ye khaali
hon to jagah/cheez ki chalti footage ka bada srot band rehta hai aur zyada
tukdon par Veo/studio aata hai.

**Anchor ka chehra khabar ke hisaab se.** Har khabar ka tone alag Claude
call tay karti hai: `serious` (maut, haadsa, apraadh, aapda), `neutral`,
`positive` (achhi khabar). Upar se pakka niyam: maut/haadsa/hatya/baadh
jaise shabd hon to hamesha serious, Claude kuch bhi kahe. Har khabar
HeyGen ka ALAG video hai, isliye har ek ka chehra alag ho sakta hai:

1. **Looks (sabse bharosemand - aapko ek baar banana hai).** HeyGen
   dashboard -> Avatars -> wahi presenter (photo avatar) -> naya look /
   "Generate look". Teen look banaiye, prompt jaise:
   - gambhir: *"same woman, serious and sombre expression, no smile, news studio"*
   - neutral: *"same woman, calm neutral professional expression, news studio"*
   - muskaan: *"same woman, slight warm smile, news studio"*
   Har look ka id (look ke ⋯ menu / API `GET /v3/avatars/looks` mein `id`)
   Secrets `HEYGEN_LOOK_SERIOUS`, `HEYGEN_LOOK_NEUTRAL`,
   `HEYGEN_LOOK_POSITIVE` mein. Photo avatar par HeyGen ka consent pehle
   poora hona chahiye (upar "Chehra").
2. **Har tone ka motion nirdesh** (`motion_prompt` + `expressiveness`,
   Avatar IV) - hamesha lagta hai. Look na hon to sirf yahi: wahi ek tasveer,
   gambhir khabar par "serious, no smile" ka nirdesh. **Imaandari se:**
   HeyGen ise mukhya roop se harkat (sir/haath) ke liye batata hai - chehre
   ka bhaav tasveer se hi aata hai. Agar end-card wali tasveer mein
   presenter muskura rahi hai to bina looks ke gambhir khabar par bhi
   halki muskaan reh sakti hai. Isliye looks zaroor banaiye.
3. **Aawaaz ka tone nahi badla** - Sarvam (bulbul) mein bhaav ka koi
   switch nahi, aur pace badalne se aawaaz robotic hui thi (sy_tts.py).
   Aawaaz har khabar par ek jaisi saaf news-aawaaz hai.

`/fatafat` aur `/heygen` dikhate hain ki looks lage hain ya nahi.

**HeyGen ka API credit khatam ho** (HTTP 402 / "insufficient credit"): 6
ghante HeyGen ki koshish band, Telegram par din mein ek sandesh, `/heygen`
mein "API credit KHATAM". app.heygen.com par **API credit** bhariye (plan ke
credit se alag), phir `/heygen on` - rok turant hat-ti hai.

**Kabhi nahi rukti:** HeyGen band (`/heygen off`), chaabi nahi, aaj ka kota
kam (poori Reel ka anchor ek saath - aadha nahi), ya koi tukda fail/der -
to wo tukda bina anchor ke: khabar ki tasveer poori screen par, headline
card aur captions waise hi. Sirf anchor band karna ho (HeyGen chalu rakh
kar): `[fatafat] heygen = 0`.

**Kharch (andaaza):** ek Reel ~50-58 second ka anchor (5-7 chhote HeyGen
video). Din mein 3 = ~2.5-3 minute - `[heygen] max_minutes_per_day` (3)
lagbhag poora; baaki video mein anchor tab nahi lagega, aur pehle wali video
ne kota kha liya to shaam ki Reel bina anchor bhi ban sakti hai. Teeno par
pakka anchor chahiye to `max_minutes_per_day` 4-5 kijiye (kharch badhega). Credit = minute × aapke plan ka
HeyGen rate (Avatar IV; pakka rate help.heygen.com "API pricing"). Iske
alawa Claude (chunav + script + tone, ~3 call) aur Sarvam (~700 akshar)
prati Reel. Veo ka koi kharch nahi.

## Dhyan dene layak

- **Cache ki seema 10 GB hai, aur 7 din bina chhue cache mit jaata hai.**
  Har run chhooti hai, isliye aam taur par koi dikkat nahi. Par Actions
  hafte bhar band rahe to hisaab mit jayega aur nayi shuruaat hogi.
  Tab YouTube sign-in dobara hoga, aur purani khabrein dobara aa sakti hain.
- **Bani hui video 2 din rakhi jaati hai** (`keep_output_days`). Jo video
  approval ya upload ka intezaar kar rahi hai, wo run ke beech cache mein
  rehti hai.
- **Laptop ka purana hisaab:** laptop wala program band karke
  `C:\SatyaYatra\satyayatra.db` file Telegram par bot ko (file ke roop
  mein) bhej dijiye. Agli run use padh kar jod leti hai - laptop par ban
  chuke vishay aur khabrein phir dobara nahi banti. Dobara bhejne se kuch
  nahi bigadta.
- **Kuch sites GitHub ke server ko rok sakti hain.** Google Trends ya kuch
  news sites datacentre wali requests par 429 ya block de sakti hain. Aisa
  hua to log mein "nahi khula" dikhega, aur program doosre srot se kaam
  chalata hai.
- **GitHub ke niyam.** Actions mukhya roop se code build aur test karne ke
  liye hai. Har 20 minute wala aisa kaam aam hai, par GitHub ise kabhi
  zyada maan sakta hai. Rok lagi to `SERVER.md` wala VPS tareeka tayyar hai.
- **Band karna:** Actions → SatyaYatra → `...` → Disable workflow.

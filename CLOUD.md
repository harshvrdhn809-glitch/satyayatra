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

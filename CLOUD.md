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

### 2. YouTube ka "TV" client

Google Cloud Console → APIs & Services → Credentials → Create Credentials
→ OAuth client ID → **TVs and Limited Input devices**. Iska `client_id` aur
`client_secret` Secrets mein jaata hai (neeche dekhiye).

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
| `YOUTUBE_DEVICE_CLIENT_ID` | **haan** | TV client (kadam 2) |
| `YOUTUBE_DEVICE_CLIENT_SECRET` | **haan** | TV client (kadam 2) |
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

### 6. Pehli run aur YouTube sign-in

Actions → SatyaYatra → Run workflow → `mode = run`. Ya agli 20 minute
wali run ka intezaar kar lijiye.

Token na hone par pehli run Telegram par ek safha aur code bhejti hai.
Phone par code daaliye aur ijaazat dijiye. Run tab tak (~28 minute) rukti
hai. Chook gaye to Telegram par `/signin` likhiye.

OAuth app "Testing" mein hai, isliye ye sign-in har 7 din mein phir
maanga jayega.

---

## Dhyan dene layak

- **Cache ki seema 10 GB hai, aur 7 din bina chhue cache mit jaata hai.**
  Har run chhooti hai, isliye aam taur par koi dikkat nahi. Par Actions
  hafte bhar band rahe to hisaab mit jayega aur nayi shuruaat hogi.
  Tab YouTube sign-in dobara hoga, aur purani khabrein dobara aa sakti hain.
- **Bani hui video 2 din rakhi jaati hai** (`keep_output_days`). Jo video
  approval ya upload ka intezaar kar rahi hai, wo run ke beech cache mein
  rehti hai.
- **Laptop ka purana `satyayatra.db` saath nahi aata.** Cloud nayi
  shuruaat se chalta hai.
- **Kuch sites GitHub ke server ko rok sakti hain.** Google Trends ya kuch
  news sites datacentre wali requests par 429 ya block de sakti hain. Aisa
  hua to log mein "nahi khula" dikhega, aur program doosre srot se kaam
  chalata hai.
- **GitHub ke niyam.** Actions mukhya roop se code build aur test karne ke
  liye hai. Har 20 minute wala aisa kaam aam hai, par GitHub ise kabhi
  zyada maan sakta hai. Rok lagi to `SERVER.md` wala VPS tareeka tayyar hai.
- **Band karna:** Actions → SatyaYatra → `...` → Disable workflow.

# Reporter ka Google Form — banane ka tareeka

Reporter phone ke browser mein ek link kholega, form bharega (bol kar bhi
likh sakta hai), video/photo chadhayega — bas. Baaki kaam program karega:
Sheet se khabar padhna, script, video, Telegram par aapka approval,
YouTube, Facebook. Code: `sy_report.py`.

Form aapko **haath se** banana hai (Google file-upload wala sawal program
se nahi banne deta). Ek baar ka kaam hai, lagbhag 30-40 minute.

> **Dhyaan:** repo public hai. Sheet ka link/id, service account ki file —
> ye sab kabhi repo mein, issue mein ya kisi .md mein mat likhiye. Sirf
> GitHub Secret mein.

---

## Kadam 1 — Form banaiye

1. Us Google account se jo aapki Drive wala hai: <https://forms.google.com> → **Blank form** (khaali form).
2. Upar ka naam: `SatyaYatra — खबर भेजिए`
3. Naam ke neeche ka vivaran (description):
   `अपने इलाके की खबर भेजिए। हर सवाल में जितना पता हो उतना लिखिए। बोलकर भी लिख सकते हैं (कीबोर्ड पर माइक 🎤 दबाइए)।`
4. **Settings** (upar) → **Responses**:
   - *Collect email addresses* → **Do not collect** (band)
   - *Limit to 1 response* → **band**
   - *Allow response editing* → band
5. Settings → **Presentation** → *Show progress bar* → **chalu** (reporter ko dikhe ki kitna bacha hai).

### Sawal kaise jodein

- **+** (Add question) se sawal, aur **Add section** (do patti wala nishan) se naya hissa.
- Sawal ka prakar (type) sawal ke daayein dropdown se chuniye.
- **Required** ka switch har sawal ke neeche hai.

**Sawal ka text neeche jaisa hi, hoobahoo copy kijiye.** Program Sheet ke
column ke naam se pehchaanta hai ki kaun sa jawab kya hai. Ek-aadh shabd
badal jaye to chal jayega, par mote (bold) shabd zaroor rehne chahiye.

---

### Hissa 1 — आप कौन हैं

(Pehla hissa form ke shuru mein apne aap hota hai — uska naam upar wala form ka naam hi hai. Sawal yahin jodiye.)

| # | Sawal ka text (copy kijiye) | Prakar (type) | Zaroori? |
|---|---|---|---|
| 1 | **आपका नाम** | Short answer | haan |
| 2 | **मोबाइल नंबर** | Short answer | haan |
| 3 | **आपका ज़िला** | Dropdown | haan |

Sawal 2 par: teen bindu (⋮) → **Response validation** → *Regular expression* → *Matches* → `^[0-9]{10}$` , error text: `10 अंक का मोबाइल नंबर लिखिए`.

Sawal 3 ke vikalp (options) — apne hisaab se badliye:
`मिर्ज़ापुर`, `प्रयागराज`, `भदोही`, `सोनभद्र`, `वाराणसी`, `चंदौली`, `कौशांबी`, `प्रतापगढ़`, `जौनपुर`, `अन्य`

### Hissa 2 — खबर  *(Add section)*

Section ka naam: `खबर`

| # | Sawal ka text | Prakar | Zaroori? |
|---|---|---|---|
| 4 | **एक लाइन में खबर** | Short answer | haan |
| 5 | **क्या हुआ? पूरी बात बताइए** | Paragraph | haan |

Sawal 5 ke neeche vivaran (⋮ → *Description*):
`जो देखा-सुना वो सब लिखिए — क्या हुआ, कैसे हुआ, अब क्या हाल है। बोलकर लिखने के लिए कीबोर्ड का माइक 🎤 दबाइए।`

### Hissa 3 — कब और कहाँ  *(Add section)*

| # | Sawal ka text | Prakar | Zaroori? |
|---|---|---|---|
| 6 | **घटना की तारीख** | Date | haan |
| 7 | **घटना का समय** | Time | nahi |
| 8 | **घटना किस ज़िले में हुई?** | Dropdown (sawal 3 wale hi vikalp) | haan |
| 9 | **गाँव / मोहल्ला / जगह** | Short answer | haan |

### Hissa 4 — कौन और कितने  *(Add section)*

| # | Sawal ka text | Prakar | Zaroori? |
|---|---|---|---|
| 10 | **कौन-कौन लोग या अधिकारी जुड़े हैं?** | Paragraph | nahi |
| 11 | **आँकड़े (कितने लोग, कितना पैसा आदि)** | Short answer | nahi |

### Hissa 5 — बयान  *(Add section)*

| # | Sawal ka text | Prakar | Zaroori? |
|---|---|---|---|
| 12 | **बयान किसने दिया? (नाम और पद)** | Short answer | nahi |
| 13 | **उन्होंने क्या कहा?** | Paragraph | nahi |

Sawal 12 ka vivaran: `जैसे: सुरेश कुमार, थाना प्रभारी`

### Hissa 6 — वीडियो और फ़ोटो  *(Add section)*

Teeno **File upload** prakar ke hain. Pehli baar File upload chunne par
Google bataata hai ki files aapki Drive mein jayengi aur reporter ko Google
account se sign-in karna hoga → **Continue**.

| # | Sawal ka text | Prakar | Zaroori? | File ki seema |
|---|---|---|---|---|
| 14 | **घटना / जगह की वीडियो** | File upload | nahi | *Allow only specific file types* → **Video**; *Maximum number of files* → **5**; *Maximum file size* → **1 GB** |
| 15 | **बयान वाली वीडियो** | File upload | nahi | **Video**; files → **1**; size → **1 GB** |
| 16 | **फ़ोटो** | File upload | nahi | **Image**; files → **5**; size → **10 MB** |

Vivaran:
- 14: `घटना या जगह की वीडियो। फ़ोन खड़ा या आड़ा — दोनों चलेगा। 10 सेकंड से 1 मिनट की वीडियो सबसे अच्छी।`
- 15: `जिसने बयान दिया उसकी वीडियो — उनकी अपनी आवाज़ में। शोर कम हो, फ़ोन मुँह के पास हो।`

Settings → Responses mein neeche **file upload ki kul seema** (*Maximum size of all files uploaded*) → **10 GB** kar dijiye.

### Hissa 7 — आखिरी बात  *(Add section)*

| # | Sawal ka text | Prakar | Zaroori? | Vikalp |
|---|---|---|---|---|
| 17 | **क्या किसी का चेहरा छुपाना है?** | Multiple choice | haan | `हाँ, चेहरा छुपाना है` / `नहीं` |
| 18 | **बयान देने वाले से इजाज़त** | Checkboxes | nahi | ek hi vikalp: `हाँ, मैंने बयान देने वाले से वीडियो दिखाने की इजाज़त ली है` |

Sawal 17 ka vivaran: `बच्चे, पीड़ित, या कोई जो पहचान छुपाना चाहे — तो "हाँ" चुनिए।`

> **Program ka niyam:** "बयान वाली वीडियो" asli aawaaz ke saath video mein
> tabhi lagti hai jab sawal 18 par tick ho. Tick na ho to wo video nahi
> lagti (Telegram par bata diya jaata hai). "चेहरा छुपाना = हाँ" par reporter
> ki har video/photo mein chehre apne aap dhundhle hote hain — ye **pakka
> nahi** hai (bheed, andhera, jhuka sar chhoot sakta hai), isliye aise
> video ko approve karne se pehle Telegram par dhyan se dekhiye.

---

## Kadam 2 — Sheet se jodiye

1. Form mein upar **Responses** tab → **Link to Sheets** (hara nishan) → **Create a new spreadsheet** → **Create**.
2. Sheet khulegi. Pehli line mein sawal hain — use **mat badaliye**, column ka kram mat badaliye.
3. Program khud aakhir mein ek column jodega: **SatyaYatra स्थिति** — isme har khabar ki haalat aati hai:
   `ban rahi hai` → `approval par (Telegram)` → `YouTube par chadh gayi https://youtu.be/...` ya `roki gayi - <wajah>`.
4. Sheet ka pata (URL) aisa dikhta hai:
   `https://docs.google.com/spreadsheets/d/`**`LAMBI-ID-YAHAN`**`/edit`
   Beech wala lamba hissa **Sheet id** hai — ise kahin likh kar mat rakhiye, seedha kadam 5 mein Secret mein daaliye.

## Kadam 3 — Google Cloud mein do API chalu kijiye

Wahi Google Cloud project jiska service account `GCP_SA_JSON` Secret mein hai (Veo wala).

1. <https://console.cloud.google.com> → upar project chuniye.
2. **APIs & Services → Library** → khojiye **Google Sheets API** → **Enable**.
3. Phir khojiye **Google Drive API** → **Enable**.

## Kadam 4 — Sheet aur Drive folder service account ke saath share kijiye

Service account ka email chahiye. Laptop par `satyayatra-sa.json` Notepad
mein kholiye aur `"client_email"` ke saamne wala pata copy kijiye (aisa
dikhta hai: `kuch-naam@project-id.iam.gserviceaccount.com`). Cloud par
`Actions → SatyaYatra → Run workflow → mode = check` chalane par bhi
jaanch mein ye email dikhta hai.

1. **Sheet:** Sheet mein upar **Share** → wo email daaliye → **Editor** chuniye (Viewer nahi — status likhna hai) → *Notify people* hata dijiye → **Share**.
2. **Drive folder:** <https://drive.google.com> → *My Drive* mein ek folder bana hoga: **`SatyaYatra — खबर भेजिए (File responses)`**. Us folder par right-click → **Share** → wahi email → **Viewer** → **Share**.
   (Folder tab banta hai jab form mein pehla file-upload sawal juda. Andar har sawal ka alag folder hota hai — upar wale ek folder ko share karna kaafi hai.)

## Kadam 5 — GitHub Secret

Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Naam | Value |
|---|---|
| `REPORT_SHEET_ID` | kadam 2 wali lambi Sheet id |

`GCP_SA_JSON` pehle se hona chahiye (CLOUD.md). Uske bina ye hissa nahi chalega.

## Kadam 6 — Jaanch

1. **Actions → SatyaYatra → Run workflow → mode = check.** Neeche "reporter Sheet" **theek** aana chahiye. KAMI aaye to wahi email aur wajah likhi hogi — zyadatar share (kadam 4) ya API (kadam 3) ki kami hoti hai.
2. Khud form bhar kar dekhiye (ek chhoti test video ke saath). Agli run (20-30 minute) mein:
   - Telegram par "Reporter ki khabar aayi" sandesh,
   - Sheet mein `ban rahi hai`,
   - phir video approval ke liye.
   Test wali video ko Reject kar dijiye.

## Kadam 7 — Reporter ko link

Form mein upar **Send** → 🔗 link → **Shorten URL** → copy. Ye link
WhatsApp par reporter ko bhejiye; wo use phone ke browser mein kholega
(Chrome). Reporter ke phone mein Google (Gmail) account hona chahiye —
video chadhane ke liye Google yahi maangta hai. Android phone mein aam
taur par pehle se hota hai.

Reporter ko ek line mein samjhaiye: *"Har sawal mein jo pata ho likhiye,
nahi pata to chhod dijiye. Bayan wali video mein pehle poochh lijiye ki
video dikhayenge, phir aakhri dabba tick kijiye."*

---

## Program kya karta hai (chhota hisaab)

- Har 5 minute (`config.cloud.ini` → `[report] check_minutes`) Sheet padhta hai. Har nayi line par ek baar.
- **Script sirf form se** — koi internet ki baat nahi judti. Khabar chhoti ho to bhi banti hai; sirf tab rukti hai jab form mein thos baat hi na ho (wajah Sheet mein likhi jaati hai).
- Reporter ki clips Claude frame dekh kar script ki sahi baat par lagata hai; khadi (phone) video 16:9 mein dono taraf dhundhle bhaag ke saath. Kami ho to pehle jaisa Commons/Pexels/studio.
- **Bayan wali video** (ijaazat ho to) asli aawaaz mein, script ke "…ne kya kaha, suniye" wale vaakya ke baad judti hai; neeche naam-pad ki patti. Zyada se zyada `bayan_max_seconds` (45 second).
- Reporter ka naam YouTube description mein: `SatyaYatra संवाददाता: <naam>`. Screen par sirf "स्रोत: SatyaYatra संवाददाता".
- Video ke baad reporter ki badi files mita di jaati hain (cache na phoole). Asli file aapki Drive mein rehti hai.
- Video banane mein teen baar gadbad ho to line `roki gayi` ho jaati hai.

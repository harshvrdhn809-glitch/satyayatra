# Facebook Page aur Instagram par bhi

Jo video YouTube par chadh jaati hai, wahi Facebook Page par bhi chali
jayegi — aur agar wo Reel hai (bolly ya viral), to Instagram par bhi.

Koi naya approval nahi hai. Aapka ✅ pehle hi lag chuka hota hai; ye uske
BAAD ka kaam hai.

---

## Pehle ye do baatein

**Instagram par sirf Reel jayegi — 16:9 wali khabar nahi.**
Ye rok jaan-boojhkar hai. Aapki bolly/viral wali video 9:16 hain, wo
Instagram par jaisi ki taisi baithti hain. 16:9 wali khabar wahan kat
jaati hai ya uske upar-neeche kaali patti aati hai. **Adhoora dikhne se
na dikhna behtar hai.** Facebook par ye rok nahi — wahan dono chalti hain.

**Instagram file nahi leta, PATA maangta hai.**
Meta ka apna dastavez kehta hai: *"media must be hosted on a publicly
accessible server."* Isliye Reel pehle Google Cloud Storage par rakhi
jaati hai, aur uska link Instagram ko diya jaata hai. Facebook mein ye
jhanjhat nahi — wahan file seedha chadh jaati hai.

Isi wajah se neeche ka kadam 3 sirf Instagram ke liye hai. **Agar abhi
sirf Facebook chalu karna ho to kadam 1 aur 4 kaafi hain.**

---

## 1. Meta ka app aur Page ka token

Chahiye: ek **Facebook Page** (channel ke naam se), aur usse juda hua ek
**Instagram professional account** (Business ya Creator — personal nahi).

1. [developers.facebook.com](https://developers.facebook.com) → **My Apps**
   → **Create App** → type **Business**.
2. App mein **Facebook Login** aur **Instagram** product add kijiye.
3. **Tools → Graph API Explorer** kholiye.
4. Upar apna app chuniye, phir **User or Page** mein apna **Page** chuniye.
5. In permissions par nishan lagaiye:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `instagram_basic`
   - `instagram_content_publish`
6. **Generate Access Token** dabaiye aur ijaazat de dijiye.

> Apne hi Page par post karne ke liye aam taur par poora App Review nahi
> lagta, jab tak app "Development" mein hai aur aap hi uske admin hain.
> Agar Meta review maange, to wahin ruk jaiye aur mujhe bataiye — us
> soorat mein rasta thoda alag hoga.

**Ab wo token lamba kijiye.** Graph Explorer ka token kuch ghante mein
mar jaata hai. Explorer mein token ke bagal wale **ℹ️** par click karke
**Open in Access Token Tool** → **Extend Access Token** dabaiye. Jo lamba
token mile wahi rakhiye.

**Page ki id:** Graph Explorer mein `me/accounts` chalaiye — apne Page ke
saamne `id` likha milega.

---

## 2. Instagram ki id

Graph Explorer mein chalaiye:

```
<PAGE_ID>?fields=instagram_business_account
```

Jo id mile wahi `ig_user_id` hai. Na mile to Instagram account us Page se
juda hi nahi hai — wo Instagram app ki settings mein "Connect Facebook
Page" se jodna padta hai.

---

## 3. GCS bucket — sirf Instagram ke liye

Google Cloud Console → **Cloud Storage** → **Create bucket**.

- Naam: kuch bhi anokha, jaise `satyayatra-reels`
- Location: `asia-south1` (Mumbai)
- Access control: **Uniform**

Bucket banne ke baad do cheezein kijiye:

**a) Sarvajanik roop se padhne layak banaiye** — Instagram bina login ke
video utaarta hai, isliye ye zaroori hai.
Bucket → **Permissions** → **Grant access** → Principal `allUsers`,
Role **Storage Object Viewer**.

> Dhyan: is bucket mein sirf wahi video rakhiye jo waise bhi sarvajanik
> honi hain. Koi niji file yahan kabhi mat rakhiye.

**b) Purani file apne aap hatti rahe** — warna ye bucket bhar jayega aur
uska kiraya badhta jayega.
Bucket → **Lifecycle** → **Add a rule** → Action **Delete object**,
Condition **Age = 7 days**.

Instagram video kuch minute mein utaar leta hai; 7 din us se kahin zyada
hai.

Bucket ka naam `config.ini` ke `[social] gcs_bucket` mein daal dijiye —
sirf naam, `gs://` nahi.

**Service account ko likhne ki ijaazat:** wahi `satyayatra-sa.json` wala
account is bucket par **Storage Object Creator** hona chahiye.
Bucket → **Permissions** → **Grant access** → us service account ka email
(wo JSON ke andar `client_email` mein likha hai) → Role **Storage Object
Creator**.

---

## 4. config.ini bhariye

```ini
[social]
enabled = 0
fb_page_id = <Page ki id>
fb_token = <lamba Page token>
ig_user_id = <Instagram ki id>
gcs_bucket = satyayatra-reels
```

`enabled` ko 0 hi rehne dijiye — chalu Telegram se karenge.

---

## 5. Chalu kijiye

`restart.bat`, phir Telegram par:

```
/social
```

Wo bata dega ki Facebook aur Instagram dono taiyar hain ya nahi. Dono
"taiyar" dikhein, tab:

```
/social on
```

Agli video YouTube par jaane ke baad apne aap Facebook par bhi chali
jayegi. Reel hui to Instagram par bhi.

Band karna ho: `/social off`. Ye switch `config.ini` se upar rehta hai,
isliye kuch bhi gadbad dikhe to phone se hi rok sakte hain.

---

## Agar kuch na chale

Nakaami par Telegram par sandesh aayega, aur usmein Meta ka apna jawab
bhi hoga. Aam wajahen:

| sandesh mein | matlab |
|---|---|
| `(#200)` ya `permissions` | token mein wo permission nahi hai — kadam 1 dobara |
| `Invalid OAuth access token` | token mar gaya — naya banaiye aur extend kijiye |
| `media_type` ya `aspect ratio` | video 9:16 nahi hai |
| `The video file could not be downloaded` | bucket sarvajanik nahi hai — kadam 3(a) |
| `2207026` | Instagram ne video ka roop nahi maana (lambai ya codec) |

**YouTube par chadhna is se kabhi nahi rukega.** Social ka poora hissa
alag rakha gaya hai: wahan kuch bhi fail ho, video YouTube par chadh chuki
hoti hai aur khabar `published` hi rehti hai.

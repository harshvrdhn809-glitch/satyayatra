# SatyaYatra — server par le jaana

Laptop chalu rakhna ab zaroori nahi. Poora system ek chhote Linux server
par chalta hai, aur aap pehle ki tarah Telegram se chalate rehte hain.

Ye file wahi hai jo aapko karna hai — kram se. Beech mein kuch samajh na
aaye to wahin ruk jaiye, aage mat badhiye.

---

## Pehle ye jaan lijiye

**Kya badal raha hai:** sirf ye ki program kis machine par chal raha hai.
Telegram, video ka roop, chunav ka gate, approval — sab waisa ka waisa.

**Kya NAHI badal raha:** aapka kaam. Vishay chunna aur approve karna
pehle ki tarah phone par hi hota rahega.

**Do cheezein behtar ho rahi hain:**

1. **YouTube ka sign-in** ab phone se hoga — server Telegram par ek chhota
   code bhej dega, aap wo daal denge. `signin.bat` ki zaroorat nahi.
2. **Sudhaar bhejne ka rasta.** Code GitHub par rahega. Main wahan sudhaar
   rakh dunga, aap phone se `/naya` likhenge, aur server khud naya code
   utha kar dobara chalu ho jayega. Na laptop, na file bhejna.

---

## 1. Server lijiye

**Chaar cheezein zaroori hain. Provider koi bhi ho, inse neeche mat
jaiye:**

| cheez | kam se kam |
|---|---|
| CPU | **2 vCPU** |
| RAM | **4 GB** |
| Disk | **40 GB** |
| OS | **Ubuntu 24.04** |

RAM par samjhauta mat kijiye. Render ffmpeg ka kaam hai, aur 2 GB par wo
lambi video ke beech mein mar jaata hai — video adhoori, aur wajah log
mein bhi saaf nahi dikhti.

**Sujhav: Hostinger VPS, "KVM 2" plan, India wala datacentre.**
UPI seedha chalta hai (RuPay aur debit card bhi), India mein server hai,
aur us plan mein 2 vCPU ke saath 8 GB RAM milti hai — hamari zaroorat se
dugni, yaani render ke liye khaasi jagah.

Ek baat pehle se jaan lijiye taaki baad mein jhatka na lage: wahan jo
sasta daam dikhta hai wo **lambe samay ka peshgi daam** hota hai (ek-do
saal ek saath). Renewal uska lagbhag dedh guna hota hai. Peshgi dena
hamare liye theek hi hai — har mahine card ya mandate ka jhanjhat nahi
rehta.

Server banate waqt:

- **Location:** India
- **OS:** Ubuntu 24.04
- **SSH key:** apni key daal dijiye. Sirf password wala tareeka mat
  rakhiye — server din-raat khula rehta hai aur password roz taange jaate
  hain.

> Account banana aur payment daalna — ye do kaam mujhse mat karwaiye aur
> main karunga bhi nahi. Wo aapke apne haath ka kaam hai.

Server ban jaane par uska **IP** note kar lijiye. Andar jaane ka tareeka:

```bash
ssh root@<IP>
```

---

## 2. Server taiyar kijiye

```bash
apt update && apt -y upgrade

# Python, ffmpeg (libass ke saath), Devanagari font, aur git
apt -y install python3 python3-pip python3-venv ffmpeg \
               fonts-noto-core fonts-noto-ui-core git

# ffmpeg mein libass hai ya nahi - ye dikhna CHAHIYE
ffmpeg -hide_banner -buildconf | grep -o libass
```

Aakhri command par `libass` chhapna chahiye. Na chhape to aage mat
badhiye — uske bina screen ka saara Devanagari dabbon mein badal jayega.

Font pakka karne ke liye:

```bash
fc-list | grep -i devanagari | head
```

Kuch lines aani chahiye.

---

## 3. Program ka apna user aur folder

```bash
adduser --system --group --home /opt/satyayatra --shell /bin/bash satyayatra
mkdir -p /opt/satyayatra
chown -R satyayatra:satyayatra /opt/satyayatra
```

---

## 4. GitHub par code rakhiye

Ye ek baar ka kaam hai, aur isi se aage ka saara rasta khulta hai.

**a.** github.com par ek **private** repository banaiye — naam `satyayatra`.
Private hona zaroori hai.

**b.** Apne laptop se `C:\SatyaYatra` ka code us repo mein daal dijiye.
Folder mein `.gitignore` pehle se pada hai — wo `config.ini`,
`youtube-token.json`, `client_secret*.json`, database aur video sab ko
apne aap bahar rakhta hai.

```
cd C:\SatyaYatra
git init
git add .
git commit -m "shuruaat"
git branch -M main
git remote add origin https://github.com/<aapka-naam>/satyayatra.git
git push -u origin main
```

Push ke baad **GitHub par jaakar apni aankh se dekh lijiye** ki `config.ini`
wahan nahi dikh rahi. Dikh jaye to turant repo delete kar dijiye aur mujhe
bataiye — chaabiyan badalni padengi.

**c.** Server ko padhne ki ijaazat dijiye (deploy key):

```bash
mkdir -p /opt/satyayatra/.ssh
chown satyayatra:satyayatra /opt/satyayatra/.ssh
chmod 700 /opt/satyayatra/.ssh
sudo -u satyayatra ssh-keygen -t ed25519 -N "" -f /opt/satyayatra/.ssh/id_ed25519
cat /opt/satyayatra/.ssh/id_ed25519.pub
```

Jo line chhape use copy kijiye, aur GitHub par:
**repo → Settings → Deploy keys → Add deploy key** — paste kar dijiye.
**"Allow write access" mat dabaiye** — server ko sirf padhna hai.

**d.** Ab code utha lijiye:

```bash
sudo -u satyayatra git clone git@github.com:<aapka-naam>/satyayatra.git /opt/satyayatra/app
```

Aage se poora kaam `/opt/satyayatra/app` mein hoga.

---

## 5. Python ke do package

```bash
sudo -u satyayatra pip3 install --break-system-packages pillow truststore
```

---

## 6. Chaabiyan bhariye

```bash
cd /opt/satyayatra/app
sudo -u satyayatra cp config.ini.template config.ini
sudo -u satyayatra nano config.ini
```

Wahi chaabiyan jo laptop wali `config.ini` mein hain — **apne laptop se
dekh kar, apne haath se** bhariye. Kisi ko bhejni nahi hai, mujhe bhi
nahi.

Sirf itna dhyan: `[paths] ffmpeg` khaali chhod dijiye — Linux par wo apne
aap mil jaata hai.

Bharne ke baad file ko sirf apne liye padhne layak kar dijiye:

```bash
chmod 600 /opt/satyayatra/app/config.ini
chown satyayatra:satyayatra /opt/satyayatra/app/config.ini
```

`config.ini` `.gitignore` mein hai, isliye `/naya` chalane par wo kabhi
nahi badlegi. Ye jaan-boojhkar hai.

---

## 7. YouTube ka naya client — ye bhi ek baar ka kaam hai

Server par browser nahi hota, isliye purana sign-in wahan chal hi nahi
sakta. Google ka apna alag tareeka hai chhote device ke liye, aur uske
liye ek NAYA client banana padta hai.

Google Cloud Console mein:

**APIs & Services → Credentials → Create Credentials → OAuth client ID →
Application type: `TVs and Limited Input devices`**

Jo `client_id` aur `client_secret` mile, unhe `config.ini` mein daaliye:

```ini
[youtube]
device_client_id = ...
device_client_secret = ...
```

> Purana Desktop wala client rehne dijiye — wo laptop par kaam aata rahega.
> Device wala tareeka usse nahi chalta; Google isi kism ka client maangta
> hai.

---

## 8. Purana hisaab saath le jaana ho to

`satyayatra.db` bhejna zaroori nahi. Bhej denge to purani khabron ka
hisaab saath chala aayega (jo chal chuki hai wo dobara nahi chalegi). Na
bhejein to nayi shuruaat ho jayegi.

Laptop se:

```
scp C:\SatyaYatra\satyayatra.db root@<IP>:/opt/satyayatra/app/
```

Phir server par:

```bash
chown satyayatra:satyayatra /opt/satyayatra/app/satyayatra.db
```

---

## 9. Jaanch chalaiye

```bash
cd /opt/satyayatra/app
sudo -u satyayatra python3 sy_check.py
```

Sab hara hona chahiye. `KAMI` dikhe to wahin theek kijiye, aage mat
badhiye.

---

## 10. Chalu kijiye

```bash
cp /opt/satyayatra/app/satyayatra.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now satyayatra
```

Dekhne ke liye:

```bash
systemctl status satyayatra        # chal raha hai ya nahi
journalctl -u satyayatra -f        # log, chalta hua
```

Pehla kaam jo hoga: Telegram par YouTube sign-in ka code aayega. Phone par
wo safha kholiye, code daaliye, ijaazat dijiye. Bas.

---

## Ab roz ka chalana — sab phone se

Telegram par bot ko seedha likh dijiye:

| likhiye | kya hoga |
|---|---|
| `/khabar <vishay>` | isi vishay par khabar dhoondho aur banao — sabse pehle |
| `/haal` | abhi kya chal raha hai, katar mein kitni khabrein |
| `/naya` | naya code uthao aur dobara chalu ho jao |
| `/dobara` | bas dobara chalu ho jao |
| `/signin` | YouTube ka sign-in phir se |
| `/madad` | yahi suchi |

Ye aadesh **sirf aapki chat se** maane jaate hain. Bot ka naam kisi aur ko
mil bhi jaye, wo `/naya` nahi chala sakta — program chat ka number
milaata hai.

### `/khabar` — jab machine ka chunav kaafi na ho

Machine wahi vishay uthati hai jo Google Trends aur YouTube ki suchi mein
upar hai, aur wo suchi manoranjan ki taraf jhukti hai. Jo baat sach mein
bhaari hai — maan lijiye BRICS — zaroori nahi ki us suchi mein upar aaye.
Ye pehchaan insaan machine se behtar karta hai.

```
/khabar BRICS shikhar sammelan Bharat ki bhoomika
```

Hota ye hai: us vishay par taaze lekh dhoondhe jaate hain, sampadak wala
call lagta hai, script banti hai, aur wo khabar **katar mein sabse upar**
chali jaati hai — Reel se bhi upar, aur chhah ghante wali ghadi ka
intezaar kiye bina. Wajah seedhi hai: aapne wo vishay tab manga jab wo
chal raha tha; chhah ghante baad wo khabar nahi, purani baat hoti hai.

Do baatein jaan lijiye:

**Sampadak ka pehra hata nahi hai.** Aapka manga hua vishay bhi usi jaanch
se guzarta hai. Lekh na khule, ya baat sirf charcha aur afwaah nikle, to
wo ruk jayega aur Telegram par wajah aa jayegi. "Aapne kaha hai" kisi baat
ko sachchi nahi bana deta — aur channel ki sabse badi poonji uska bharosa
hai.

**Din bhar ki upload seema phir bhi lagti hai** (`max_uploads_per_day`).
Isliye chaahe jitni maang bhejiye, channel par bhaar nahi pad sakta.

Purana naksha, agar kabhi laptop par chalana pade:

| kaam | laptop | server |
|---|---|---|
| dobara chalu | `restart.bat` | `/dobara` (ya `systemctl restart satyayatra`) |
| log dekhna | window dekhna | `journalctl -u satyayatra -f` |
| jaanch | `check.bat` | `python3 sy_check.py` |
| abhi ek video | `abhi.bat` | `python3 sy_now.py` |
| YouTube sign-in | `signin.bat` | `/signin` |
| naya code | file copy karna | `/naya` |

---

## Sudhaar kaise pahunchega

1. Main sudhaar likhta hoon aur GitHub ke repo mein rakh deta hoon.
2. Main aapko Telegram/chat par bata deta hoon ki kya badla.
3. Aap phone se `/naya` likh dete hain.
4. Server naya code kheenchta hai aur dobara chalu ho jaata hai.

Kheenchna hamesha `--ff-only` hai. Matlab: agar server par kisi ne haath
se kuch badal diya ho to git chup-chaap milaane ki koshish nahi karega —
saaf mana kar dega, aur Telegram par wajah aa jayegi. Aadha-adhoora mila
hua code raat ko chalte program mein sabse buri cheez hai.

**Aap beech mein hain, aur jaan-boojhkar hain.** Mera bheja hua code bina
aapke `/naya` dabaye kabhi apne aap nahi chalega. Yahi usool aapne shuru
se rakha hai — insaan har gate par rahe.

---

## Dhyan dene layak do baatein

**Har 7 din wala sign-in ab bhi rahega.** Wo isliye hai ki OAuth app abhi
"Testing" mein hai — server par le jaane se wo nahi badalta. Farq itna
hai ki ab wo phone se 30 second ka kaam hai. Hamesha ke liye hatana ho to
app ko "Production" mein publish karna padega, jiske liye ek website,
privacy policy ka safha aur verified domain chahiye.

**Disk apne aap saaf hoti hai.** Din mein ek baar nikal chuki khabron ka
kachcha saamaan (`work/`) hat jaata hai, aur `output/` ki 14 din se purani
video bhi. Ye seema `config.ini` mein `keep_output_days` se badalti hai.
Bina iske disk kuch mahinon mein bhar jaati hai — aur bhari disk par
program girta nahi, bas chup-chaap video banana band kar deta hai.

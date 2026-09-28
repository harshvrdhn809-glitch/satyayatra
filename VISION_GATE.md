# Tasveer/footage chunte waqt DEKH KAR jaanch (vision gate)

## Dikkat kya thi

Ab tak photo ya chalti footage chunne ka poora faisla sirf SHABD milaan
se hota tha: art director/shot-editor ek khoj ka shabd deta tha ("flooded
river Nepal", "Bhadohi district stadium"), aur Pexels/Pixabay/Commons/
Openverse se jo bhi nateeja aata, uska naam/tag/file-title us shabd se
kitna milta hai - bas isi se tay hota tha ki tasveer chalegi ya nahi
(`relevant()`, `sy_media.py`). Tasveer khud kabhi kisi ne DEKHI nahi -
na uski quality, na uska asli vishay.

Isi se do dikkatein aati thi: kabhi tasveer be-mel hoti thi (shabd toh
mil gaya, par tasveer kisi aur cheez ki nikli), aur kabhi dhundhli, kati-
phati ya watermark se bhari hoti thi - khaas kar thumbnail par, jahan
YouTube ka pehla, sabse zaroori faisla hota hai.

## Ab kya badla

Har baar jab ek tasveer ya clip "sahi lag raha hai" (shabd-milaan pass
kar chuka hai) aur workdir mein download ho chuka hai, use LENE SE PEHLE
Claude ko khud dikhaya jaata hai - jaise ek picture editor akhri nazar
daalta hai. Clip ho to pehle uska ek frame nikaala jaata hai, phir wahi
frame dikhaya jaata hai.

Poochha jaata hai: "ye is drishya ke laayak hai?" - aur reject sirf tabhi
hota hai jab koi SAAF wajah ho: bilkul be-mel vishay, bada watermark jo
tasveer dhaak raha ho, itni dhundhli/kati-phati ki kuch pehchana na jaaye,
ya kisi aam vyakti (aaropi/peedit/gawah) ka seedha chehra. Baaki har
haalat mein "theek hai" maana jaata hai - shak hone par bhi, kyunki yahan
zaroorat se zyada sakht hona kuch na dikhne se bura hai.

Pehla drishya (jo thumbnail bhi banega) par thodi zyada sakhti se dekha
jaata hai - saaf, achhi roshni wali, ek nazar mein samajh aane wali honi
chahiye - kyunki YouTube par darshak sabse pehle wahi dekhta hai.

## Kharch aur samay seemit kaise rakha

Ek shot (ya bulletin/evergreen ki ek hi tasveer) par zyada se zyada 4
tasveerein hi Claude ko dikhai jaati hain, chahe koi pass na ho. Uske
baad us shot ki khoj band ho jaati hai - bina dekhe kuch nahi liya jaata
(Sep 2026, gy_indus_202609 ke baad; pehle shabd-milaan wala le liya jaata
tha, aur wahi galat stock chal jaata tha). Shot phir labeled AI chitran
(AAKHRI SAHARA) ya pichhle drishya par jaata hai, akeli tasveer designed
backdrop par. Isse na kharch bhaagta hai, na koi khoj kabhi-na-khatam
hone waala loop banti hai.

Vision jaanch ke liye alag, sasta model bhi rakha ja sakta hai
(`config.ini` mein `[anthropic] vision_model=`) - khaali chhodne par
wahi mukhya model istemal hota hai jo sampadak/art-director ke liye hai.

## Band karna ho to

`config.ini` mein `[media] vision_gate = 0` kar dijiye - poora purana,
sirf-shabd wala tareeka turant wapas aa jaata hai, kuch aur nahi rukta.

## Kabhi gadbad ho to

Tasveer khule nahi, jawab na aaye, ya JSON na bane - to us ek jaanch ko
"theek hai" maan liya jaata hai aur pipeline waisa hi chalta rehta hai
jaisa pehle chalta tha. Ye jaanch kabhi kisi render ko rok nahi sakti,
sirf ek behtar chunaav mein madad kar sakti hai.

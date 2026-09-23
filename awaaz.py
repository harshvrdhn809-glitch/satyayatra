"""Aawaaz ki raftaar - kaan se chuniye, ankde se nahi.

Main aawaaz sun nahi sakta. Do baar main ankdon se raftaar tay kar chuka
hoon aur dono baar wo aapko theek nahi lagi - ek baar bahut dheemi ("robot
dheere dheere bol raha hai"), ek baar hadbadai hui. Isliye ab faisla
naapne wale ke haath se hatakar sunne wale ke haath mein.

Ye chhota program ek hi paragraph teen alag raftaar par bulwa kar teenon
Telegram par bhej deta hai. Aap teenon sun kar batayiye kaun si theek hai,
aur wahi ek line config.ini mein likh di jayegi:

    [sarvam]
    pace = 0.88

Kharch na ke barabar hai - teen chhoti request, lagbhag 10 second aawaaz.
"""
import os
import sys

import sy_config as cfg
import sy_telegram
import sy_tts

# Ek aam bulletin ka hissa - na bahut chhota, na itna bada ki kharch lage.
SAMPLE = ("अगर आपके घर में एक साल से छोटा बच्चा है, तो यह ख़बर आपके लिए है। "
          "सरकार बारह बीमारियों से बचाने वाले टीके बिल्कुल मुफ़्त देती है, "
          "और इसके लिए न कोई फ़ॉर्म भरना है, न कोई पैसा देना है।")

# Dheemi se tez. 1.00 Sarvam ki apni natural raftaar hai.
PACES = (0.85, 0.92, 1.00)


def main():
    cfg.ensure_dirs()
    cfg.put_ffmpeg_on_path()
    wd = os.path.join(cfg.HERE, "work", "awaaz")
    os.makedirs(wd, exist_ok=True)

    key = cfg.need("sarvam", "api_key")
    model = cfg.get("sarvam", "model") or "bulbul:v3"
    speaker = cfg.get("sarvam", "speaker") or "ritu"

    now, fixed = sy_tts.current_pace()
    print("abhi ki raftaar: %.2f%s" % (now, " (config.ini se)" if fixed else " (default)"))
    print()

    for p in PACES:
        out = os.path.join(wd, "pace_%d.wav" % int(p * 100))
        with open(out, "wb") as f:
            f.write(sy_tts._say(SAMPLE, key, model, speaker, p))
        secs = sy_tts.duration(out)
        cps = len(SAMPLE) / secs if secs else 0
        words = len(SAMPLE.split())
        wpm = words / (secs / 60.0) if secs else 0
        line = ("pace %.2f  —  %.1f second, %.0f shabd/minute, "
                "%.1f akshar/second" % (p, secs, wpm, cps))
        print(line)
        try:
            sy_telegram.send_audio(out, "<b>%s</b>\n\nJo theek lage uska pace "
                                        "number bata dijiye." % line)
        except Exception as e:
            print("  Telegram par nahi gayi:", e)

    print()
    print("Teenon Telegram par bhej di hain. Jo theek lage, uska number")
    print("config.ini mein [sarvam] ke neeche daal dijiye:")
    print()
    print("    pace = 0.92")
    return 0


if __name__ == "__main__":
    sys.exit(main())

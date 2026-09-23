"""Veo ki ek clip banakar dekhiye - isse pehle ki wo pipeline mein lage.

Ye JAAN-BOOJHKAR alag se chalta hai. Wajah: har clip par asli paisa lagta
hai (credit se). Pehli baar wo paisa ek hi clip par lagna chahiye, jise aap
apni aankh se dekh sakein - poore pipeline mein chupke se nahi.

Chalaiye:
    python veojaanch.py
    python veojaanch.py a lighthouse beam sweeping over a dark sea

Ye [veo] enabled ki parwah NAHI karta - jaanch ke liye hi to hai. Par
service account aur project wahi lagte hain jo config mein hain.
"""
import os
import sys
import time

import sy_config as cfg
import sy_veo


def main():
    cfg.put_ffmpeg_on_path()
    what = " ".join(sys.argv[1:]).strip()
    shot = {
        "brief": what or ("a large cargo ship bridge at sea with radar "
                          "screens and paper charts"),
        "queries": [what or "ship navigation bridge"],
    }
    prompt = sy_veo.prompt_for(shot)

    print("=" * 64)
    print("service account :", sy_veo.sa_path() or "NAHI MILI")
    print("project         :", cfg.get("veo", "project") or "(sa ki apni)")
    print("model           :", sy_veo.model())
    print("lambai          :", sy_veo.seconds(), "second")
    print("naap            :", sy_veo.resolution())
    print("aaj tak bani    :", sy_veo.used_today(), "/", sy_veo.max_per_day())
    print("=" * 64)
    print()
    print("PROMPT:")
    print(" ", prompt)
    print()

    if not sy_veo.sa_path():
        print("Service account JSON nahi mili. satyayatra-sa.json isi folder")
        print("mein honi chahiye, ya config.ini ke [veo] service_account mein")
        print("uska poora path dijiye.")
        return 1

    out = os.path.join(cfg.OUTPUT_DIR, "veo_jaanch.mp4")
    cfg.ensure_dirs()
    print("Bana rahe hain. Ek-do minute lagte hain, kabhi teen bhi...")
    t0 = time.time()
    ok, why = sy_veo._clip(prompt, out, vertical=False)
    if not ok:
        print()
        print("NAHI BANI:", why)
        print()
        print("Agar upar 'Veo ne mana kiya' likha hai to uske saath Google ka")
        print("apna jawab bhi hai - wahi baat mujhe bhej dijiye, usi se pata")
        print("chalega ki kya badalna hai.")
        return 1

    sy_veo.note_used()
    print()
    print("BAN GAYI: %s" % out)
    print("  %.1f second lage, file %.1f MB"
          % (time.time() - t0, os.path.getsize(out) / 1024.0 / 1024.0))
    print()
    print("Ab ise kholkar dekh lijiye. Theek lage to config.ini ke [veo]")
    print("mein enabled = 1 kar dijiye, phir restart.bat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

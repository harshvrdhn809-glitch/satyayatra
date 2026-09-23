#!/usr/bin/env bash
# SatyaYatra - server par chalane ke liye.
#
# Ye wahi kaam karta hai jo Windows par start.bat karta tha: program
# chalata hai, aur wo kisi wajah se ruk jaye to 30 second baad dobara
# chalu kar deta hai.
#
# systemd ke saath chalane par ye loop zaroori nahi hai (wo khud dobara
# chalu karta hai), par haath se chalane ke liye ye kaam ka hai.
cd "$(dirname "$0")" || exit 1

export PYTHONUTF8=1
PY="${PY:-python3}"

while true; do
  echo
  echo "=== SatyaYatra chalu ho raha hai ==="
  "$PY" sy_main.py
  echo
  echo "Program ruk gaya. 30 second mein dobara chalu hoga."
  sleep 30
done

#!/usr/bin/env bash
# SatyaYatra - GitHub Actions ki do run ke beech hisaab bachana.
#
# Har run nayi, khaali machine par hoti hai. Jo cheezein ek run se agli tak
# chahiye, wo do potliyon mein bandh kar GitHub ke cache mein jaati hain:
#
#   state.enc - chhoti, har run ke baad: satyayatra.db, youtube-token.json,
#               anchor ki tasveer, feedback/, aur assets/ mein program ki
#               apni banayi files. Yaani repo mein na hone wali har file,
#               sivaay neeche wali media ke.
#   media.enc - badi, sirf tab jab badle: work/, output/, veo_clips/ - yaani
#               bani hui video jo approval ya upload ka intezaar kar rahi
#               hai, aur Veo ki clip (jinpar paisa laga hai).
#
# Dono STATE_KEY (GitHub Secret) se band hoti hain. Repo public hai, aur
# state mein YouTube ka refresh token hai - bina taale ke ye kahin nahi
# rakha jaata.
#
#   cloud/state.sh unpack   - cache se aayi potli kholo (na ho to nayi shuruaat)
#   cloud/state.sh pack     - potli bandho; media ka hash GITHUB_OUTPUT mein
set -euo pipefail

cd "$(dirname "$0")/.."
CACHE=.sy-cache
MEDIA_DIRS=(work output veo_clips)

: "${STATE_KEY:?STATE_KEY secret khaali hai - CLOUD.md dekhiye}"

enc() { openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:STATE_KEY; }
dec() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:STATE_KEY; }

unpack_one() {
  local f="$CACHE/$1.enc"
  if [ ! -f "$f" ]; then
    echo "$1: cache mein kuch nahi - nayi shuruaat"
    return 0
  fi
  # Galat STATE_KEY par yahin ruk jaana zaroori hai. Aage badhte to program
  # khaali hisaab se chalta, aur run ke ant mein wahi khaali hisaab purane
  # asli hisaab ke upar bach jaata.
  if ! dec < "$f" | tar -xzf - ; then
    echo "::error::$1 khul nahi payi - STATE_KEY badli hai kya? Kuch bhi aage nahi chalega."
    exit 1
  fi
  echo "$1: $(du -h "$f" | cut -f1) khol di"
}

media_hash() {
  local d
  for d in "${MEDIA_DIRS[@]}"; do
    # tar sirf poore second rakhta hai, isliye second ke tukde hata kar -
    # warna khuli hui media ka hash har baar alag aata aur wo bina badle
    # har run mein dobara bachti.
    if [ -d "$d" ]; then find "$d" -type f -printf '%p %s %T@\n'; fi
  done | sed -E 's/\.[0-9]+$//' | LC_ALL=C sort | sha256sum | cut -c1-40
}

state_files() {
  # Repo mein na hone wali har file (git ki nazar mein "untracked", chahe
  # .gitignore mein ho), sivaay media, chaabiyon aur kachre ke.
  git ls-files --others -z \
    | tr '\0' '\n' \
    | grep -Ev '^(work|output|veo_clips|\.sy-cache)/' \
    | grep -Ev '(^|/)__pycache__/' \
    | grep -Ev '^(config\.ini|satyayatra-sa\.json|client_secret[^/]*\.json)$' \
    | grep -Ev '\.(log|db-wal|db-shm)$' \
    || true
}

case "${1:-}" in
  unpack)
    mkdir -p "$CACHE"
    unpack_one state
    unpack_one media
    mkdir -p "${MEDIA_DIRS[@]}"
    ;;
  pack)
    mkdir -p "$CACHE"
    state_files > "$CACHE/state.list"
    echo "state mein $(wc -l < "$CACHE/state.list") file"
    tar -czf - -T "$CACHE/state.list" | enc > "$CACHE/state.enc.new"
    mv "$CACHE/state.enc.new" "$CACHE/state.enc"

    h="$(media_hash)"
    if [ "${MEDIA_RESTORED_KEY:-}" = "sy-media-$h" ]; then
      echo "media nahi badli - dobara nahi bachegi"
      rm -f "$CACHE/media.enc"
    else
      mkdir -p "${MEDIA_DIRS[@]}"
      dirs=("${MEDIA_DIRS[@]}")
      tar -czf - "${dirs[@]}" | enc > "$CACHE/media.enc.new"
      mv "$CACHE/media.enc.new" "$CACHE/media.enc"
      echo "media: $(du -h "$CACHE/media.enc" | cut -f1)"
    fi
    if [ -n "${GITHUB_OUTPUT:-}" ]; then
      echo "media_key=sy-media-$h" >> "$GITHUB_OUTPUT"
      [ -f "$CACHE/media.enc" ] && echo "media_changed=1" >> "$GITHUB_OUTPUT" \
                                 || echo "media_changed=0" >> "$GITHUB_OUTPUT"
    fi
    ;;
  *)
    echo "istemal: $0 unpack|pack" >&2
    exit 2
    ;;
esac

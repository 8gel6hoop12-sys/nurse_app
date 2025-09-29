#!/usr/bin/env bash
# nurseapp-launcher.sh — Linux ランチャー

set -euo pipefail

# ==== あなたのリポに変更 ====
REPO="OWNER/REPO"          # 例: yamada/nurse-app
PKG="nurse_app_Linux.tar.gz"
SHA="${PKG}.sha256"
# ===========================

RELEASES="https://github.com/${REPO}/releases/latest"
PKG_URL="${RELEASES}/download/${PKG}"
SHA_URL="${RELEASES}/download/${SHA}"

ROOT="$(mktemp -d /tmp/nurseapp.XXXXXX)"
PKG_PATH="${ROOT}/${PKG}"

echo "Downloading ${PKG_URL}"
curl -fL "${PKG_URL}" -o "${PKG_PATH}"

# SHA 検証（あれば）
if curl -fLI "${SHA_URL}" >/dev/null 2>&1; then
  echo "Verifying SHA256..."
  curl -fL "${SHA_URL}" -o "${ROOT}/${SHA}"
  EXPECTED="$(cut -d' ' -f1 "${ROOT}/${SHA}")"
  ACTUAL="$(sha256sum "${PKG_PATH}" | cut -d' ' -f1)"
  if [[ "${EXPECTED,,}" != "${ACTUAL,,}" ]]; then
    echo "SHA256 mismatch. Download may be corrupted." >&2
    exit 1
  fi
fi

DST="${ROOT}/unpacked"
mkdir -p "${DST}"
echo "Extracting..."
tar -xzf "${PKG_PATH}" -C "${DST}"

APP="$(/usr/bin/find "${DST}" -type f -name 'nurse_app' -perm -111 | head -n1)"
if [[ -z "${APP}" ]]; then
  echo "nurse_app が見つかりませんでした。" >&2
  exit 1
fi

echo "Launching ${APP}"
chmod +x "${APP}"
"${APP}" &
disown

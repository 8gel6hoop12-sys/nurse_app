# NurseApp-Launcher.ps1
# 1回目だけユーザーが落とす超軽量ランチャー（Windows）
param()

$ErrorActionPreference = "Stop"

# ===== あなたのリポに変更 =====
$REPO   = "OWNER/REPO"   # 例: yamada/nurse-app
$PKG    = "nurse_app_windows.zip"
$SHA    = "$PKG.sha256"
# =================================

$releases = "https://github.com/$REPO/releases/latest"
$pkgUrl   = "$releases/download/$PKG"
$shaUrl   = "$releases/download/$SHA"

# TLS 安全側
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Join-Path $env:TEMP "nurse_app_dist"
$null = New-Item -ItemType Directory -Force -Path $root
$zip  = Join-Path $root $PKG
$dst  = Join-Path $root "unpacked"

Write-Host "最新パッケージを取得中: $pkgUrl"
Invoke-WebRequest -Uri $pkgUrl -OutFile $zip -UseBasicParsing

# 署名(sha256)があるなら検証
try {
  Write-Host "ハッシュ情報を確認中: $shaUrl"
  $shaFile = Join-Path $root $SHA
  Invoke-WebRequest -Uri $shaUrl -OutFile $shaFile -UseBasicParsing
  $expected = (Get-Content $shaFile).Split(" ")[0].Trim()
  $actual = (Get-FileHash -Algorithm SHA256 $zip).Hash.ToLower()
  if ($expected.ToLower() -ne $actual) {
    throw "SHA256 不一致。ダウンロードが壊れている可能性があります。"
  } else {
    Write-Host "SHA256 OK"
  }
} catch {
  Write-Host "SHA256 検証はスキップ（情報なし / 取得不可）"
}

# 展開
if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
Write-Host "展開中..."
Expand-Archive -Path $zip -DestinationPath $dst

# 実行
$exe = Get-ChildItem -Path $dst -Recurse -Filter "nurse_app.exe" | Select-Object -First 1
if (-not $exe) { throw "nurse_app.exe が見つかりませんでした。" }

Write-Host "起動します: $($exe.FullName)"
Start-Process -FilePath $exe.FullName

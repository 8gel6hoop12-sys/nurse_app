# deploy.ps1 — NurseApp 無許可運用・最小ワンファイル配布
param(
  [string]$AppRoot = "C:\Program Files\NurseApp",
  [int]$Port = 8787,
  [string]$PagesDomain = "your-org.github.io"   # ここをあなたの Pages ドメインに
)
$ErrorActionPreference="Stop"
Write-Host "== NurseApp deploy start ==" -ForegroundColor Magenta

# 1) 配置
New-Item -Force -ItemType Directory -Path $AppRoot | Out-Null
$src = Split-Path -Parent $MyInvocation.MyCommand.Path
$files = @(
 "nurse_server.py","nurse_ui.html","nanda_db.xlsx",
 "assessment.py","diagnosis.py","record.py","careplan.py"
)
foreach($f in $files){
  if(!(Test-Path (Join-Path $src $f))){ Write-Warning "missing: $f (後で配置でも可)"; continue }
  Copy-Item -Force (Join-Path $src $f) (Join-Path $AppRoot $f)
}

# 2) 環境変数（マシン全体）
[Environment]::SetEnvironmentVariable("AI_PROVIDER","ollama","Machine")
[Environment]::SetEnvironmentVariable("AI_LOG_DISABLE","1","Machine")
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY","","Machine")
[Environment]::SetEnvironmentVariable("AI_MODEL","qwen2.5:7b-instruct","Machine")
[Environment]::SetEnvironmentVariable("OLLAMA_HOST","http://127.0.0.1:11434","Machine")
[Environment]::SetEnvironmentVariable("NURSE_PORT",$Port,"Machine")

# 3) URL プロトコル（nurseui://start → 127.0.0.1 を開く）
reg add "HKLM\SOFTWARE\Classes\nurseui" /ve /t REG_SZ /d "URL:NurseUI" /f | Out-Null
reg add "HKLM\SOFTWARE\Classes\nurseui" /v "URL Protocol" /t REG_SZ /d "" /f | Out-Null
reg add "HKLM\SOFTWARE\Classes\nurseui\shell\open\command" /ve /t REG_SZ /d "\"C:\Windows\System32\cmd.exe\" /c start http://127.0.0.1:$Port/" /f | Out-Null

# 4) Edge/Chrome ポリシー（外部プロトコル自動起動 & カメラ自動許可）
$edgeA = "[{`"allowed_origins`":[`"https://$PagesDomain`"],`"protocol`":`"nurseui`"}]"
$allowUrls = "[`"http://127.0.0.1:$Port`",`"https://$PagesDomain`"]"
reg add "HKLM\SOFTWARE\Policies\Microsoft\Edge" /v "AutoLaunchProtocolsFromOrigins" /t REG_SZ /d $edgeA /f | Out-Null
reg add "HKLM\SOFTWARE\Policies\Microsoft\Edge" /v "URLAllowlist" /t REG_SZ /d "[`"https://$PagesDomain/*`"]" /f | Out-Null
reg add "HKLM\SOFTWARE\Policies\Microsoft\Edge" /v "VideoCaptureAllowed" /t REG_DWORD /d 1 /f | Out-Null
reg add "HKLM\SOFTWARE\Policies\Microsoft\Edge" /v "MediaStreamCameraAllowedForUrls" /t REG_SZ /d $allowUrls /f | Out-Null

reg add "HKLM\SOFTWARE\Policies\Google\Chrome" /v "AutoLaunchProtocolsFromOrigins" /t REG_SZ /d $edgeA /f | Out-Null
reg add "HKLM\SOFTWARE\Policies\Google\Chrome" /v "URLAllowlist" /t REG_SZ /d "[`"https://$PagesDomain/*`"]" /f | Out-Null
reg add "HKLM\SOFTWARE\Policies\Google\Chrome" /v "VideoCaptureAllowed" /t REG_DWORD /d 1 /f | Out-Null
reg add "HKLM\SOFTWARE\Policies\Google\Chrome" /v "MediaStreamCameraAllowedForUrls" /t REG_SZ /d $allowUrls /f | Out-Null

# 5) 自動起動タスク（ユーザーのログオン時、非表示起動）
$python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)?.Source
if(!$python){ $python = (Get-Command python.exe -ErrorAction SilentlyContinue)?.Source }
if(!$python){ Write-Warning "python が見つかりません。PyInstaller で EXE 化するか、PATH を通してください。" }

$taskName="NurseApp_LocalServer"
try{ schtasks /Delete /TN $taskName /F | Out-Null } catch {}
$arg="-X utf8 `"$AppRoot\nurse_server.py`""
schtasks /Create /TN $taskName /TR "`"$python`" $arg" /SC ONLOGON /RL HIGHEST /F /IT /DELAY 0000:10 | Out-Null

# 6) すぐ起動（今のユーザー）
try{ schtasks /Run /TN $taskName | Out-Null }catch{}

# 7) ヘルスチェック → UI オープン
function Test-Health {
  try{ (Invoke-WebRequest -Uri "http://127.0.0.1:$Port/ai/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }catch{ $false }
}
$ok=$false; for($i=0;$i -lt 30;$i++){ if(Test-Health){$ok=$true;break}; Start-Sleep -Milliseconds 300 }
if($ok){ Start-Process "http://127.0.0.1:$Port/" } else { Write-Warning "サーバ起動に失敗。ログオン後に自動で再実行されます。" }

Write-Host "== NurseApp deploy done ==" -ForegroundColor Magenta

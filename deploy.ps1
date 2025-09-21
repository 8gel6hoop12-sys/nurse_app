# 配布側が 1 回だけ実行。以後はログオン時に自動起動します（ユーザ権限でOK）
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bat  = Join-Path $Here "run_local_server.bat"
$Task = "NurseApp_LocalServer_8787"

Write-Host "配置フォルダ: $Here"
Write-Host "起動BAT:      $Bat"

# 既存タスクを削除
$exist = Get-ScheduledTask -TaskName $Task -ErrorAction SilentlyContinue
if ($exist) { Unregister-ScheduledTask -TaskName $Task -Confirm:$false }

# タスク作成（ユーザログオン時・非表示）
$action   = New-ScheduledTaskAction -Execute $Bat
$trigger  = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 12)

Register-ScheduledTask -TaskName $Task -Action $action -Trigger $trigger -Settings $settings | Out-Null
Write-Host "OK: 自動起動を登録しました。次回ログインから常駐します。"

# すぐ起動しておく（初回だけ）
Start-Process -FilePath $Bat -WindowStyle Hidden

# 簡易動作確認
Start-Sleep -Seconds 1
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:8787/ai/health" -UseBasicParsing -TimeoutSec 3
  if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) {
    Write-Host "ヘルスチェックOK: ローカルで応答しています。"
  } else {
    Write-Host "ヘルスチェックNG: 応答コード $($r.StatusCode)"
  }
} catch {
  Write-Host "ヘルスチェックNG: まだ応答がありません。ログ: logs\nurse_server.log を確認してください。"
}

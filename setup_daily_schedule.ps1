# setup_daily_schedule.ps1
# Registers a Windows Task Scheduler job that runs daily_post.py once per day.
# Run this (in PowerShell) only AFTER you've set STORE_URL + a live POSTER backend
# + credentials in .env. Until POSTER is a live backend (or you omit --live), it
# is a safe dry-run.
#
#   Preview (no scheduling):   python daily_post.py
#   Register daily 9am task:   ./setup_daily_schedule.ps1
#   Remove it:                 Unregister-ScheduledTask -TaskName "EtsyDailyPost" -Confirm:$false

$ErrorActionPreference = "Stop"
$repo   = "C:\Users\Ron39\etsy-pipeline"
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$script = "$repo\daily_post.py"

# Post live once per day. Drop "--live" here to schedule a dry-run instead.
$action  = New-ScheduledTaskAction -Execute $python -Argument "`"$script`" --live" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Daily -At 9:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName "EtsyDailyPost" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Posts one Etsy product/humor video per day" -Force

Write-Host "Registered 'EtsyDailyPost' to run daily at 9:00 AM."
Write-Host "Test it now with:  python daily_post.py   (dry-run preview)"

# Let a Codex agent drive the game in Azahar (screenshots + keys) and return a short text report.
# Usage: codex_drive.ps1 "goal in plain words" [-Model gpt-6-luna] [-Effort xhigh] [-Sandbox workspace-write] [-Out report.txt]
# The agent only uses azshot/azkey/azclick.ps1 in this folder; the report is printed on stdout.
[CmdletBinding(PositionalBinding=$false)]
param([Parameter(Mandatory, Position=0)][string]$Task, [string]$Model = "gpt-6-luna",
      [string]$Effort = "xhigh", [string]$Sandbox = "workspace-write",
      [string]$Out = "$env:TEMP\codex_drive_report.txt")
$codex = (Get-Command codex -ErrorAction SilentlyContinue).Source
if (-not $codex) {
  $codex = Get-ChildItem "$env:LOCALAPPDATA\OpenAI\Codex\bin\*\codex.exe" | Sort-Object LastWriteTime -Descending |
           Select-Object -First 1 -ExpandProperty FullName
}
if (-not $codex) { throw "codex.exe not found" }
$here = $PSScriptRoot
$shot = "$env:TEMP\azahar.png"
$prompt = @"
You are driving the Nintendo 3DS game Dragon Quest Monsters Joker 3 Professional (Italian fan translation)
in the Azahar emulator on this Windows PC. Only interact through these PowerShell scripts:
- Screenshot: powershell -NoProfile -File "$here\azshot.ps1" -Out "$shot"   then look at $shot (view the image).
  Window image ~1460x991: top screen roughly x 359-1100, y 64-509; touch screen roughly x 433-1026, y 509-953.
- Buttons: powershell -NoProfile -File "$here\azkey.ps1" a [b x y up down left right l r start select ...] [-HoldMs 120] [-GapMs 400]
  up/down/left/right = D-pad; cup/cdown/cleft/cright = circle pad (walking); l also recentres the camera.
- Touch: powershell -NoProfile -File "$here\azclick.ps1" X Y   (coordinates in the screenshot image).
Tips: text boxes advance with a; Yes/No prompts start with "No" highlighted (orange): press left then a for "Si".
After each input wait about 1-2 s and take a new screenshot before deciding. Network steps can take 10-30 s.
Rules: do not edit, create or delete any file except $shot; do not touch other windows or the emulator menus;
never press start+select together; stop as soon as the goal is reached, an error code/dialog appears, or after
40 inputs without progress.
Final answer (max 8 lines, Italian): what you did, the exact text on screen at the end (error codes verbatim),
and whether the goal was reached.

GOAL: $Task
"@
$prompt | & $codex exec -m $Model -c "model_reasoning_effort=`"$Effort`"" -s $Sandbox `
  --skip-git-repo-check --ephemeral --color never -C $here -o $Out - *> "$env:TEMP\codex_drive.log"
if (Test-Path $Out) { Get-Content $Out -Encoding UTF8 } else { Get-Content "$env:TEMP\codex_drive.log" -Tail 30 }

# Usage: azclick.ps1 X Y [-ProcId N]   (coordinates in the azshot.ps1 image, i.e. relative to the Azahar window)
param([int]$X, [int]$Y, [int]$HoldMs = 120, [int]$ProcId = 0)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class M {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint f, int dx, int dy, uint d, UIntPtr e);
}
"@
$h = (Get-Process azahar | Where-Object { $_.MainWindowHandle -ne 0 -and ($ProcId -eq 0 -or $_.Id -eq $ProcId) } | Select-Object -First 1).MainWindowHandle
$r = New-Object M+RECT
[M]::GetWindowRect($h, [ref]$r) | Out-Null
[M]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 150
[M]::SetCursorPos($r.L + $X, $r.T + $Y) | Out-Null
Start-Sleep -Milliseconds 50
[M]::mouse_event(2, 0, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds $HoldMs
[M]::mouse_event(4, 0, 0, 0, [UIntPtr]::Zero)

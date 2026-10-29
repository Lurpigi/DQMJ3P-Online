param([string]$Out = "$env:TEMP\azahar.png", [int]$ProcId = 0)
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class W32 {
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint f);
}
"@
$p = Get-Process azahar | Where-Object { $_.MainWindowHandle -ne 0 -and ($ProcId -eq 0 -or $_.Id -eq $ProcId) } | Select-Object -First 1
$h = $p.MainWindowHandle
$r = New-Object W32+RECT
[W32]::GetWindowRect($h, [ref]$r) | Out-Null
$w = $r.R - $r.L; $ht = $r.B - $r.T
$bmp = New-Object System.Drawing.Bitmap $w, $ht
$g = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $g.GetHdc()
[W32]::PrintWindow($h, $hdc, 2) | Out-Null  # PW_RENDERFULLCONTENT, works for GPU-rendered windows
$g.ReleaseHdc($hdc); $g.Dispose()
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
"$Out ${w}x$ht at $($r.L),$($r.T)"

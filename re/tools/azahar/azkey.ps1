# Usage: azkey.ps1 a a down b [-HoldMs 120] [-GapMs 400]   (3DS buttons, mapped from Azahar qt-config.ini profile 1)
[CmdletBinding(PositionalBinding=$false)]
param([Parameter(ValueFromRemainingArguments)][string[]]$Buttons, [int]$HoldMs = 120, [int]$GapMs = 400)
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class K {
  [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort vk, scan; public uint flags, time; public IntPtr extra; }
  [StructLayout(LayoutKind.Explicit, Size=40)] public struct INPUT { [FieldOffset(0)] public uint type; [FieldOffset(8)] public KEYBDINPUT ki; }
  [DllImport("user32.dll")] public static extern uint SendInput(uint n, INPUT[] inputs, int size);
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint type);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  public static uint Key(ushort vk, bool up) {
    var i = new INPUT[1];
    i[0].type = 1;
    i[0].ki.vk = vk;
    i[0].ki.scan = (ushort)MapVirtualKey(vk, 0);
    i[0].ki.flags = (up ? 2u : 0u) | ((vk >= 0x25 && vk <= 0x28) ? 1u : 0u);  // arrows are extended keys
    return SendInput(1, i, Marshal.SizeOf(typeof(INPUT)));
  }
}
"@
$map = @{ a=0x41; b=0x53; x=0x5A; y=0x58; up=0x54; down=0x47; left=0x46; right=0x48;
          cup=0x26; cdown=0x28; cleft=0x25; cright=0x27;
          l=0x51; r=0x57; start=0x4D; select=0x4E }
$h = (Get-Process azahar | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1).MainWindowHandle
[K]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 200
if ([K]::GetForegroundWindow() -ne $h) { throw "Azahar is not in foreground" }
foreach ($btn in $Buttons) {
  $vk = $map[$btn.ToLower()]
  if (-not $vk) { throw "unknown button $btn" }
  if ([K]::Key($vk, $false) -ne 1) { throw "SendInput failed" }
  Start-Sleep -Milliseconds $HoldMs
  [K]::Key($vk, $true) | Out-Null
  Start-Sleep -Milliseconds $GapMs
}

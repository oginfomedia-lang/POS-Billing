// Sends raw ESC/POS bytes to a Windows printer (used for the cash drawer kick).
// Uses the Windows spooler API (winspool.drv) through a hidden PowerShell, so no native npm
// module has to be built or packaged. The printer name and bytes travel as environment
// variables, never inside the script text, so a printer name can't inject commands.
import { execFile } from 'node:child_process';
import { join } from 'node:path';
import { app } from 'electron';

const SCRIPT = String.raw`
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
$source = @"
using System;
using System.Runtime.InteropServices;
public static class PosRawPrinter {
  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  public class DocInfo {
    [MarshalAs(UnmanagedType.LPWStr)] public string pDocName;
    [MarshalAs(UnmanagedType.LPWStr)] public string pOutputFile;
    [MarshalAs(UnmanagedType.LPWStr)] public string pDataType;
  }
  [DllImport("winspool.drv", EntryPoint = "OpenPrinterW", CharSet = CharSet.Unicode, SetLastError = true)]
  static extern bool OpenPrinter(string name, out IntPtr handle, IntPtr defaults);
  [DllImport("winspool.drv", SetLastError = true)]
  static extern bool ClosePrinter(IntPtr handle);
  [DllImport("winspool.drv", EntryPoint = "StartDocPrinterW", CharSet = CharSet.Unicode, SetLastError = true)]
  static extern int StartDocPrinter(IntPtr handle, int level, [In, MarshalAs(UnmanagedType.LPStruct)] DocInfo info);
  [DllImport("winspool.drv", SetLastError = true)]
  static extern bool EndDocPrinter(IntPtr handle);
  [DllImport("winspool.drv", SetLastError = true)]
  static extern bool StartPagePrinter(IntPtr handle);
  [DllImport("winspool.drv", SetLastError = true)]
  static extern bool EndPagePrinter(IntPtr handle);
  [DllImport("winspool.drv", SetLastError = true)]
  static extern bool WritePrinter(IntPtr handle, byte[] bytes, int count, out int written);

  public static void Send(string printer, byte[] data) {
    IntPtr h;
    if (!OpenPrinter(printer, out h, IntPtr.Zero)) throw new Exception("Printer not found: " + printer);
    try {
      if (StartDocPrinter(h, 1, new DocInfo { pDocName = "POS cash drawer", pDataType = "RAW" }) == 0)
        throw new Exception("Could not start a print job on " + printer);
      try {
        StartPagePrinter(h);
        int written;
        if (!WritePrinter(h, data, data.Length, out written) || written != data.Length)
          throw new Exception("Could not send data to " + printer);
        EndPagePrinter(h);
      } finally { EndDocPrinter(h); }
    } finally { ClosePrinter(h); }
  }
}
"@
# Compiling the C# takes a few seconds, so it is done once and kept as a DLL in the app's data folder.
if (-not (Test-Path $env:POS_DLL)) { Add-Type -TypeDefinition $source -OutputAssembly $env:POS_DLL }
Add-Type -Path $env:POS_DLL
$printer = $env:POS_PRINTER
if (-not $printer) {
  $printer = (Get-CimInstance Win32_Printer -Filter "Default = TRUE" | Select-Object -First 1).Name
  if (-not $printer) { throw "No printer is set for this counter and Windows has no default printer." }
}
[PosRawPrinter]::Send($printer, [Convert]::FromBase64String($env:POS_BYTES))
} catch {
  # One plain line on stdout (stderr would be PowerShell's XML error format).
  $e = $_.Exception
  while ($e.InnerException) { $e = $e.InnerException }
  [Console]::Out.Write($e.Message)
  exit 1
}
`;

// -EncodedCommand takes the script as base64 UTF-16LE: no quoting problems with a multi-line script.
const ENCODED = Buffer.from(SCRIPT, 'utf16le').toString('base64');
// Bump the version when the C# above changes, so an old cached DLL isn't reused.
const DLL_FILE = 'pos-raw-printer-v1.dll';

/** Sends bytes to `printerName` ('' = the Windows default printer). Rejects with a readable message. */
export function sendRaw(printerName: string, bytes: number[]): Promise<void> {
  if (process.platform !== 'win32') {
    return Promise.reject(new Error('Raw printing (cash drawer) is only supported on Windows.'));
  }
  return new Promise((resolve, reject) => {
    execFile(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', ENCODED],
      {
        windowsHide: true,
        timeout: 20000,
        env: {
          ...process.env,
          POS_PRINTER: printerName,
          POS_BYTES: Buffer.from(bytes).toString('base64'),
          POS_DLL: join(app.getPath('userData'), DLL_FILE),
        },
      },
      (error, stdout) => {
        if (!error) return resolve();
        const message = String(stdout).trim();
        reject(new Error(message || (error.killed ? 'The printer did not answer in time.' : 'Printer error.')));
      },
    );
  });
}

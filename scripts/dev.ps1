# civic-patch developer launcher (called by dev.bat; can also be run directly).
#
# 1. Starts the FastAPI backend (port 8000) and the Vite frontend (port 5173),
#    each in its own console window.
# 2. Opens http://localhost:5173 in the default browser once both respond.
# 3. Keeps this window open. When this window is closed (X button, Ctrl+C,
#    Enter, or the terminal exiting), both server windows are terminated.
#
# The teardown relies on a Windows job object with KILL_ON_JOB_CLOSE: both
# server windows (and every child they spawn, such as uvicorn's reload worker
# and Vite's node process) belong to a job whose only handle is held by this
# process. Windows kills the whole job the moment this process ends, no matter
# how it ends, so no cleanup code has to run.
#
# Usage: dev.bat [-NoBrowser]

param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Url = "http://localhost:5173"

function Say($msg) { Write-Host "[civic-patch] $msg" }

function Fail($msg) {
    Write-Host "[civic-patch] $msg" -ForegroundColor Red
    Write-Host "Press any key to close."
    [void][Console]::ReadKey($true)
    exit 1
}

# ---- prerequisites ----------------------------------------------------------
$py = Join-Path $Backend ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Fail "backend\.venv not found. In backend\ run: python -m venv .venv ; .venv\Scripts\python.exe -m pip install -r requirements.txt"
}
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Fail "frontend\node_modules not found. In frontend\ run: npm install"
}
if (-not (Test-Path (Join-Path $Backend ".env"))) {
    Write-Host "[civic-patch] WARNING: backend\.env not found. Copy backend\example.env to backend\.env and set GEMINI_API_KEY." -ForegroundColor Yellow
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    $nodeDir = Join-Path $env:ProgramFiles "nodejs"
    if (Test-Path (Join-Path $nodeDir "npm.cmd")) { $env:Path = "$env:Path;$nodeDir" }
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Fail "npm was not found on PATH (or in $env:ProgramFiles\nodejs)."
}

# ---- job object: kill every child when this process exits --------------------
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class CivicJob {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern IntPtr CreateJobObject(IntPtr lpJobAttributes, string lpName);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetInformationJobObject(IntPtr hJob, int infoClass, IntPtr lpInfo, uint cbInfo);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool AssignProcessToJobObject(IntPtr hJob, IntPtr hProcess);
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool TerminateJobObject(IntPtr hJob, uint exitCode);

    [StructLayout(LayoutKind.Sequential)]
    struct JOBOBJECT_BASIC_LIMIT_INFORMATION {
        public long PerProcessUserTimeLimit; public long PerJobUserTimeLimit; public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize; public UIntPtr MaximumWorkingSetSize; public uint ActiveProcessLimit;
        public UIntPtr Affinity; public uint PriorityClass; public uint SchedulingClass;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct IO_COUNTERS {
        public ulong ReadOperationCount; public ulong WriteOperationCount; public ulong OtherOperationCount;
        public ulong ReadTransferCount; public ulong WriteTransferCount; public ulong OtherTransferCount;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct JOBOBJECT_EXTENDED_LIMIT_INFORMATION {
        public JOBOBJECT_BASIC_LIMIT_INFORMATION BasicLimitInformation; public IO_COUNTERS IoInfo;
        public UIntPtr ProcessMemoryLimit; public UIntPtr JobMemoryLimit; public UIntPtr PeakProcessMemoryUsed; public UIntPtr PeakJobMemoryUsed;
    }

    public static IntPtr CreateKillOnCloseJob() {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) throw new Exception("CreateJobObject failed: " + Marshal.GetLastWin32Error());
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION info = new JOBOBJECT_EXTENDED_LIMIT_INFORMATION();
        info.BasicLimitInformation.LimitFlags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        int len = Marshal.SizeOf(typeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION));
        IntPtr ptr = Marshal.AllocHGlobal(len);
        try {
            Marshal.StructureToPtr(info, ptr, false);
            if (!SetInformationJobObject(job, 9, ptr, (uint)len)) // JobObjectExtendedLimitInformation
                throw new Exception("SetInformationJobObject failed: " + Marshal.GetLastWin32Error());
        } finally { Marshal.FreeHGlobal(ptr); }
        return job;
    }
}
"@

$job = [CivicJob]::CreateKillOnCloseJob()

function Start-ServerWindow([string]$title, [string]$workDir, [string]$command) {
    $cmdLine = "/k title $title && cd /d ""$workDir"" && $command"
    $p = Start-Process -FilePath "cmd.exe" -ArgumentList $cmdLine -PassThru
    if (-not [CivicJob]::AssignProcessToJobObject($job, $p.Handle)) {
        $err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        Fail "Could not attach '$title' to the job object (error $err)."
    }
    return $p
}

function Wait-Url([string]$url, [int]$seconds, [string]$label) {
    for ($i = 0; $i -lt $seconds; $i++) {
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        } catch { Start-Sleep -Seconds 1 }
    }
    Write-Host "[civic-patch] $label did not respond within $seconds s. Check its window for errors." -ForegroundColor Yellow
    return $false
}

$backendProc = $null
$frontendProc = $null
try {
    Say "starting backend on :8000 ..."
    $backendProc = Start-ServerWindow "civic-patch backend" $Backend `
        ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 --timeout-keep-alive 120"

    Say "starting frontend on :5173 ..."
    $frontendProc = Start-ServerWindow "civic-patch frontend" $Frontend "npm run dev"

    $okB = Wait-Url "http://localhost:8000/api/health" 60 "backend"
    $okF = Wait-Url "$Url/" 60 "frontend"

    if ($okB -and $okF) {
        Say "both servers are up."
        if (-not $NoBrowser) {
            Say "opening $Url"
            Start-Process $Url
        }
    }

    Write-Host ""
    Write-Host "  backend  : http://localhost:8000  (window 'civic-patch backend')"
    Write-Host "  frontend : $Url  (window 'civic-patch frontend')"
    Write-Host ""
    Write-Host "  Keep this window open while you work."
    Write-Host "  Close it, press Ctrl+C, or press Enter to stop both servers." -ForegroundColor Cyan
    Write-Host ""

    # Key handling only works with a real console; when input is redirected
    # (e.g. run from another tool) we just wait for the windows or the process to end.
    $interactive = $true
    try { $interactive = -not [Console]::IsInputRedirected } catch { $interactive = $false }

    while ($true) {
        if ($backendProc.HasExited -and $frontendProc.HasExited) {
            Say "both server windows were closed."
            break
        }
        if ($interactive) {
            try {
                if ([Console]::KeyAvailable) {
                    $key = [Console]::ReadKey($true)
                    if ($key.Key -eq "Enter" -or $key.Key -eq "Q") { break }
                }
            } catch { $interactive = $false }
        }
        Start-Sleep -Milliseconds 500
    }
}
finally {
    Say "stopping servers ..."
    [void][CivicJob]::TerminateJobObject($job, 0)
}

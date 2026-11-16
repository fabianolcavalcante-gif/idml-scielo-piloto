param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("v15", "v16", "v17", "v20", "v21", "v22", "v23", "v24", "v25", "v26", "v27", "v28", "v29", "v30", "v31", "v32", "v33", "v34")]
    [string]$LabVersion,
    [Parameter(Mandatory = $true)]
    [ValidatePattern("^[a-z0-9-]{8,80}$")]
    [string]$RunId
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$SshKey = "C:\Users\FabianoLC\.ssh\mapalead_vps_ed25519"
$RemoteHost = "root@143.95.214.8"
$LocalPort = 47717
$RemoteProxyPort = 47718
$VersionNumber = $LabVersion.TrimStart("v")
$Plan = Join-Path $ProjectRoot "config\openclaw-multi-agent-lab-$LabVersion.json"
$DatasetName = if ([int]$VersionNumber -eq 34) {
    "dataset-e20240135-7c07-v1.0.json"
} elseif ([int]$VersionNumber -ge 20) {
    "dataset-e20240135-visual-formulas-v1.0.json"
} else {
    "dataset-real-domains-visual-v1.2.json"
}
$Dataset = Join-Path $ProjectRoot "benchmarks\private\input\$DatasetName"
$PreparedManifest = Join-Path $ProjectRoot "benchmarks\private\input\multi-agent-manifest-$LabVersion.json"
$OutputDirectory = Join-Path $ProjectRoot "benchmarks\private\output"
$ValidatedManifest = Join-Path $OutputDirectory "validated-multi-agent-manifest-$LabVersion.json"
$Results = Join-Path $OutputDirectory "multi-agent-results-$RunId.json"
$Report = Join-Path $OutputDirectory "multi-agent-report-$RunId.json"
$Confirmation = "RUN_IDML_OPENCLAW_MULTI_AGENT_LAB_V$VersionNumber"
$RemoteCleanup = 'pid=$(pgrep -f "^python3 ops/openclaw-loopback-proxy.py --listen-port 47718 " || true); if [ -n "$pid" ]; then kill "$pid"; fi'
$RemoteStage = 'cd /opt/idml-platform && ./ops/openclaw-provider-stage.sh'
$RemoteDisable = 'cd /opt/idml-platform && IDML_RESET_OPENCLAW_STATE=true ./ops/openclaw-provider-disable.sh'
$RemoteCommand = @'
cd /opt/idml-platform && set -a && . ./.env && set +a && container_id=$(docker ps --filter label=com.docker.compose.service=openclaw-idml -q | head -n1) && container_ip=$(docker inspect "$container_id" --format "{{range .NetworkSettings.Networks}}{{println .IPAddress}}{{end}}" | head -n1) && exec python3 ops/openclaw-loopback-proxy.py --listen-port 47718 --upstream-host "$container_ip" --upstream-port 47716 --timeout-seconds 60
'@

& ssh -i $SshKey -p 22022 -o BatchMode=yes $RemoteHost $RemoteCleanup
if ($LASTEXITCODE -ne 0) {
    throw "Remote loopback proxy pre-cleanup failed"
}

$ProcessInfo = [System.Diagnostics.ProcessStartInfo]::new()
$ProcessInfo.FileName = (Get-Command ssh).Source
$ProcessInfo.UseShellExecute = $false
$ProcessInfo.CreateNoWindow = $true
foreach ($Argument in @(
    "-i", $SshKey,
    "-p", "22022",
    "-o", "BatchMode=yes",
    "-o", "ExitOnForwardFailure=yes",
    "-L", "127.0.0.1:${LocalPort}:127.0.0.1:${RemoteProxyPort}",
    $RemoteHost,
    $RemoteCommand
)) {
    [void]$ProcessInfo.ArgumentList.Add($Argument)
}

$Tunnel = $null
$ProviderStaged = $false
try {
    & ssh -i $SshKey -p 22022 -o BatchMode=yes $RemoteHost $RemoteStage
    if ($LASTEXITCODE -ne 0) {
        throw "Remote OpenClaw provider staging failed"
    }
    $ProviderStaged = $true
    $Tunnel = [System.Diagnostics.Process]::Start($ProcessInfo)
    Start-Sleep -Seconds 4
    if ($Tunnel.HasExited) {
        throw "SSH loopback proxy failed to start"
    }
    $env:IDML_OPENCLAW_GATEWAY_URL = "http://127.0.0.1:$LocalPort"
    $env:IDML_OPENCLAW_GATEWAY_TOKEN = "local-tunnel-placeholder-token-0001"
    $env:IDML_FEATURE_OPENCLAW = "false"
    $env:IDML_FEATURE_AI_SWARM = "false"
    $env:IDML_CONFIRM_AGENT_EXECUTION = $Confirmation
    & "$ProjectRoot\.venv\Scripts\python.exe" -m idml_foundation.ai.multi_agent_lab `
        --plan $Plan `
        --dataset $Dataset `
        --manifest-output $ValidatedManifest `
        --prepared-manifest $PreparedManifest `
        --results-output $Results `
        --report-output $Report `
        --run-id $RunId `
        --execute
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw lab execution failed"
    }
}
finally {
    Remove-Item Env:IDML_OPENCLAW_GATEWAY_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:IDML_CONFIRM_AGENT_EXECUTION -ErrorAction SilentlyContinue
    if ($null -ne $Tunnel -and -not $Tunnel.HasExited) {
        $Tunnel.Kill($true)
        [void]$Tunnel.WaitForExit(5000)
    }
    & ssh -i $SshKey -p 22022 -o BatchMode=yes $RemoteHost $RemoteCleanup
    if ($LASTEXITCODE -ne 0) {
        throw "Remote loopback proxy cleanup failed"
    }
    if ($ProviderStaged) {
        & ssh -i $SshKey -p 22022 -o BatchMode=yes $RemoteHost $RemoteDisable
        if ($LASTEXITCODE -ne 0) {
            throw "Remote OpenClaw provider cleanup failed"
        }
    }
}

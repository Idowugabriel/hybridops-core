[CmdletBinding()]
param(
    [string]$UnattendPath = "C:\Windows\Panther\unattend.xml"
)

$ErrorActionPreference = 'SilentlyContinue'

@(
    "$env:LOCALAPPDATA\Temp",
    "$env:TEMP",
    "C:\Windows\Temp",
    "C:\Windows\Prefetch",
    "C:\Windows\SoftwareDistribution\Download"
) | Where-Object { Test-Path $_ } | ForEach-Object {
    Remove-Item "$_\*" -Recurse -Force
}

Get-EventLog -LogName * | ForEach-Object { Clear-EventLog $_.Log }
Remove-Item "C:\Windows\System32\Sysprep\Panther\*" -Recurse -Force

$ErrorActionPreference = 'Stop'

$cloudbaseInitEnabled = $env:HYOPS_CLOUDBASE_INIT_ENABLED -eq 'true'
if ($cloudbaseInitEnabled) {
    $cloudbaseInitUrl = [string]$env:HYOPS_CLOUDBASE_INIT_MSI_URL
    if ([string]::IsNullOrWhiteSpace($cloudbaseInitUrl)) {
        throw 'Cloudbase-Init is enabled but HYOPS_CLOUDBASE_INIT_MSI_URL is empty'
    }

    $installerPath = 'C:\Windows\Temp\CloudbaseInitSetup.msi'
    Write-Host "Installing Cloudbase-Init from $cloudbaseInitUrl"
    Invoke-WebRequest -Uri $cloudbaseInitUrl -UseBasicParsing -OutFile $installerPath

    $msiArgs = @(
        '/i', $installerPath,
        '/qn',
        '/norestart',
        'SYSPREP=0',
        'SYSPREPSHUTDOWN=0',
        'RUN_SERVICE_AS_LOCAL_SYSTEM=1',
        'USERNAME=Administrator'
    )
    $install = Start-Process -FilePath 'msiexec.exe' -ArgumentList $msiArgs -Wait -PassThru
    if ($install.ExitCode -ne 0) {
        throw "Cloudbase-Init installation failed with exit code $($install.ExitCode)"
    }

    $cloudbaseConfDir = 'C:\Program Files\Cloudbase Solutions\Cloudbase-Init\conf'
    if (-not (Test-Path $cloudbaseConfDir)) {
        throw "Cloudbase-Init configuration directory not found: $cloudbaseConfDir"
    }

$cloudbaseConfig = @'
[DEFAULT]
metadata_services=cloudbaseinit.metadata.services.configdrive.ConfigDriveService
plugins=cloudbaseinit.plugins.common.sethostname.SetHostNamePlugin,cloudbaseinit.plugins.common.networkconfig.NetworkConfigPlugin
allow_reboot=false
stop_service_on_exit=false
retry_count=20
retry_count_interval=5
verbose=true
debug=false

[config_drive]
raw_hdd=true
cdrom=true
vfat=true
'@
$cloudbaseUnattendConfig = @'
[DEFAULT]
metadata_services=cloudbaseinit.metadata.services.configdrive.ConfigDriveService
plugins=cloudbaseinit.plugins.common.sethostname.SetHostNamePlugin
allow_reboot=false
stop_service_on_exit=false
retry_count=20
retry_count_interval=5
verbose=true
debug=false

[config_drive]
raw_hdd=true
cdrom=true
vfat=true
'@

    Set-Content -LiteralPath (Join-Path $cloudbaseConfDir 'cloudbase-init.conf') -Value $cloudbaseConfig -Encoding ASCII
    Set-Content -LiteralPath (Join-Path $cloudbaseConfDir 'cloudbase-init-unattend.conf') -Value $cloudbaseUnattendConfig -Encoding ASCII
    $service = Get-Service -Name 'cloudbase-init' -ErrorAction Stop
    if ($service.Status -ne 'Stopped') {
        Stop-Service -Name 'cloudbase-init' -Force -ErrorAction SilentlyContinue
    }
    Set-Service -Name 'cloudbase-init' -StartupType Automatic
    Remove-Item -LiteralPath $installerPath -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $UnattendPath)) {
    throw "Unattend file not found: $UnattendPath"
}

& C:\Windows\System32\Sysprep\sysprep.exe /generalize /oobe /shutdown /quiet /mode:vm /unattend:$UnattendPath

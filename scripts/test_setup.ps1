param([string]$SetupFile, [switch]$Isolated, [string]$InnoCompiler)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$versionMatch = Select-String -LiteralPath "$projectRoot\pyproject.toml" -Pattern '^version = "([0-9]+\.[0-9]+\.[0-9]+)"$'
if (-not $versionMatch) { throw 'Cannot read application version.' }
$appVersion = $versionMatch.Matches[0].Groups[1].Value
if (-not $SetupFile) {
    $SetupFile = Join-Path $projectRoot "dist\Scene-Setup-$appVersion-x64.exe"
}
$SetupFile = (Resolve-Path -LiteralPath $SetupFile).Path
$releaseSetup = $SetupFile
$testRoot = Join-Path $projectRoot ('artifacts\setup-test-' + [guid]::NewGuid().ToString('N'))
$installDirectory = Join-Path $testRoot 'Scene installed'
$appName = 'Сцена'
$appId = '{6578E2F1-8DBE-4F53-B7CD-C865D6AF6509}'
$productionKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\${appId}_is1"
$productionRegistration = if (Test-Path -LiteralPath $productionKey) {
    Get-ItemProperty -LiteralPath $productionKey | Select-Object * -ExcludeProperty PS* | ConvertTo-Json -Depth 5
} else { '' }
$protectedFiles = @{}
if ($Isolated) {
    $appName = 'Сцена (проверка)'
    $appId = '{02F019E8-5731-4A6E-A603-7166D7AE3170}'
    if ($productionRegistration) {
        $existingDirectory = (Get-ItemProperty -LiteralPath $productionKey).InstallLocation
        if (Test-Path -LiteralPath $existingDirectory) {
            Get-ChildItem -LiteralPath $existingDirectory -Recurse -File | ForEach-Object {
                $protectedFiles[$_.FullName] = (Get-FileHash -LiteralPath $_.FullName).Hash
            }
        }
    }
}
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\${appId}_is1"
$startShortcut = Join-Path ([Environment]::GetFolderPath('Programs')) "$appName\$appName.lnk"
$desktopShortcut = Join-Path ([Environment]::GetFolderPath('DesktopDirectory')) "$appName.lnk"
if ((Test-Path -LiteralPath $uninstallKey) -or (Test-Path -LiteralPath $startShortcut) -or (Test-Path -LiteralPath $desktopShortcut)) {
    throw 'An installed PDF Presenter or its shortcuts already exist. Test aborted without changing them.'
}
New-Item -ItemType Directory -Path $testRoot | Out-Null
if ($Isolated) {
    if (-not $InnoCompiler) { $InnoCompiler = Join-Path $projectRoot 'artifacts\tooling\inno-7.1.1\ISCC.exe' }
    if (-not (Test-Path -LiteralPath $InnoCompiler)) { throw 'Pass -InnoCompiler for the isolated installer verification build.' }
    & $InnoCompiler "/DAppVersion=$appVersion" "/DAppName=$appName" "/DAppIdString={$appId" '/DVerificationBuild=1' '/DOutputName=Scene-Verification-Setup' "/O$testRoot" "$projectRoot\installer\PDFPresenter.iss" *> (Join-Path $testRoot 'compile.log')
    if ($LASTEXITCODE -ne 0) { throw "Isolated setup compilation failed. See $testRoot\compile.log" }
    $SetupFile = Join-Path $testRoot 'Scene-Verification-Setup.exe'
}
$appDataDirectory = Join-Path $env:APPDATA 'PDFPresenter'
$createdDataDirectory = -not (Test-Path -LiteralPath $appDataDirectory)
New-Item -ItemType Directory -Force -Path $appDataDirectory | Out-Null
$dataHashes = @{}
Get-ChildItem -LiteralPath $appDataDirectory -File -Recurse | ForEach-Object {
    $dataHashes[$_.FullName] = (Get-FileHash -LiteralPath $_.FullName).Hash
}
$marker = Join-Path $appDataDirectory ('.setup-test-' + [guid]::NewGuid().ToString('N'))
'Installer preservation check' | Set-Content -LiteralPath $marker -Encoding ascii
$report = [ordered]@{
    success = $false
    setup = $SetupFile
    setup_sha256 = (Get-FileHash -LiteralPath $SetupFile).Hash
    release_setup = $releaseSetup
    release_setup_sha256 = (Get-FileHash -LiteralPath $releaseSetup).Hash
    isolated_registration = [bool]$Isolated
    install_directory = $installDirectory
    steps = @()
}

function Invoke-InstallerProcess([string]$File, [string[]]$Arguments) {
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000)) { throw "Process did not finish in 60 seconds: $File (PID $($process.Id))" }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "Process exited with code $($process.ExitCode): $File" }
}

function Uninstall-TestCopy {
    $resolved = [IO.Path]::GetFullPath($installDirectory)
    $expectedPrefix = [IO.Path]::GetFullPath($testRoot) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolved.StartsWith($expectedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to uninstall outside the designated test directory.'
    }
    $uninstaller = Join-Path $resolved 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        Invoke-InstallerProcess $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
            ('/LOG="{0}"' -f (Join-Path $testRoot 'uninstall.log')))
    }
}

try {
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/SP-', '/NORESTART', '/LANG=russian',
        '/TASKS=desktopicon', ('/DIR="{0}"' -f $installDirectory),
        ('/LOG="{0}"' -f (Join-Path $testRoot 'install.log')))
    Invoke-InstallerProcess $SetupFile $arguments
    $installedExe = Join-Path $installDirectory 'PDFPresenter.exe'
    if (-not (Test-Path -LiteralPath $installedExe)) { throw 'Application was not installed.' }
    $registration = Get-ItemProperty -LiteralPath $uninstallKey
    if ($registration.InstallLocation.TrimEnd('\') -ne $installDirectory -or $registration.DisplayName -ne $appName) {
        throw 'Incorrect Windows uninstall registration.'
    }
    $report.steps += 'Installed per-user and registered in Windows Apps.'
    $shell = New-Object -ComObject WScript.Shell
    foreach ($shortcut in @($startShortcut, $desktopShortcut)) {
        if (-not (Test-Path -LiteralPath $shortcut)) { throw "Missing shortcut: $shortcut" }
        if ($shell.CreateShortcut($shortcut).TargetPath -ne $installedExe) { throw 'Incorrect shortcut target.' }
    }
    $report.steps += 'Start menu and optional desktop shortcuts target the installed EXE.'
    $sourceRoot = Join-Path $projectRoot 'dist\PDFPresenter'
    Get-ChildItem -LiteralPath $sourceRoot -File -Recurse | ForEach-Object {
        $relative = $_.FullName.Substring($sourceRoot.Length + 1)
        $target = Join-Path $installDirectory $relative
        if ((Get-FileHash -LiteralPath $_.FullName).Hash -ne (Get-FileHash -LiteralPath $target).Hash) {
            throw "Installed file differs: $relative"
        }
    }
    $report.steps += 'Every installed payload file matches the portable build by SHA-256.'

    $arguments[-1] = '/LOG="{0}"' -f (Join-Path $testRoot 'reinstall.log')
    Invoke-InstallerProcess $SetupFile $arguments
    if (-not (Test-Path -LiteralPath $marker)) { throw 'Reinstall removed application data.' }
    $report.steps += 'Reinstall completed successfully and preserved application data.'

    $previousPlatform = $env:QT_QPA_PLATFORM
    try {
        $env:QT_QPA_PLATFORM = 'offscreen'
        $runtimeReport = Join-Path $testRoot 'runtime'
        Invoke-InstallerProcess $installedExe @('--self-test', ('"{0}"' -f $runtimeReport))
        $runtime = Get-Content -Raw -LiteralPath (Join-Path $runtimeReport 'report.json') | ConvertFrom-Json
        if (-not $runtime.success) { throw 'Installed application acceptance scenario failed.' }
    } finally { $env:QT_QPA_PLATFORM = $previousPlatform }
    $report.steps += 'Installed EXE passed the real-PDF 17 -> 35 -> 8 -> 1 acceptance scenario.'

    Uninstall-TestCopy
    foreach ($removed in @($installedExe, $uninstallKey, $startShortcut, $desktopShortcut)) {
        if (Test-Path -LiteralPath $removed) { throw "Uninstall left a registered component: $removed" }
    }
    if (-not (Test-Path -LiteralPath $marker)) { throw 'Uninstall removed application data.' }
    foreach ($path in $dataHashes.Keys) {
        if ((Get-FileHash -LiteralPath $path).Hash -ne $dataHashes[$path]) { throw "Application data changed: $path" }
    }
    if ($Isolated) {
        $afterRegistration = if (Test-Path -LiteralPath $productionKey) {
            Get-ItemProperty -LiteralPath $productionKey | Select-Object * -ExcludeProperty PS* | ConvertTo-Json -Depth 5
        } else { '' }
        if ($afterRegistration -ne $productionRegistration) { throw 'Existing installation registration changed.' }
        foreach ($path in $protectedFiles.Keys) {
            if ((Get-FileHash -LiteralPath $path).Hash -ne $protectedFiles[$path]) { throw "Existing installed file changed: $path" }
        }
        $report.steps += 'Existing installation registration, payload and user data unchanged.'
    }
    $report.steps += 'Uninstall removed the application, registration and shortcuts; user data was preserved.'
    $report.success = $true
} catch {
    $report.error = $_.Exception.Message
    throw
} finally {
    # The uninstaller deletes its own executable asynchronously. Do not launch
    # that transient file again after the application has already been removed.
    if ((Test-Path -LiteralPath (Join-Path $installDirectory 'PDFPresenter.exe')) -or (Test-Path -LiteralPath $uninstallKey)) {
        try { Uninstall-TestCopy } catch {
            $report.success = $false
            $report.cleanup_error = $_.Exception.Message
        }
    }
    if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker }
    if ($createdDataDirectory -and -not (Get-ChildItem -LiteralPath $appDataDirectory -Force)) {
        Remove-Item -LiteralPath $appDataDirectory
    }
    $report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $testRoot 'report.json') -Encoding utf8
    Write-Output "Test report: $testRoot\report.json"
}
$report | ConvertTo-Json -Depth 5
if (-not $report.success) { exit 1 }

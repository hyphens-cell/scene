param(
    [string]$InnoCompiler,
    [switch]$RebuildApp
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if ($RebuildApp) {
    & "$projectRoot\build.bat"
    if ($LASTEXITCODE -ne 0) { throw 'Application build failed.' }
}
if (-not (Test-Path -LiteralPath "$projectRoot\dist\PDFPresenter\PDFPresenter.exe")) {
    throw 'Build the application with build.bat first, or pass -RebuildApp.'
}

if (-not $InnoCompiler) {
    $candidates = @(
        "$projectRoot\artifacts\tooling\inno-7.1.1\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 7\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe"
    )
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $candidates += $command.Source }
    $InnoCompiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $InnoCompiler) {
    # Official portable mode extracts the compiler without file associations,
    # Start menu entries, or an uninstall registration for the compiler itself.
    $toolRoot = Join-Path $projectRoot 'artifacts\tooling'
    $compilerDirectory = Join-Path $toolRoot 'inno-7.1.1'
    $download = Join-Path $toolRoot 'innosetup-7.1.1-x64.exe'
    New-Item -ItemType Directory -Force -Path $toolRoot | Out-Null
    if (-not (Test-Path -LiteralPath $download)) {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe' -OutFile $download
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $download
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Pyrsys B.V.') {
        throw 'The downloaded Inno Setup compiler has an unexpected signature.'
    }
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER',
                   '/PORTABLE=1', '/NOICONS', ('/DIR="{0}"' -f $compilerDirectory),
                   ('/LOG="{0}"' -f (Join-Path $toolRoot 'compiler-extraction.log')))
    $process = Start-Process -FilePath $download -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Compiler preparation failed: $($process.ExitCode)" }
    $InnoCompiler = Join-Path $compilerDirectory 'ISCC.exe'
}

if (-not (Test-Path -LiteralPath $InnoCompiler)) { throw "Compiler not found: $InnoCompiler" }
$compilerVersion = (& $InnoCompiler --version | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $compilerVersion -notmatch '^([7-9]|[1-9][0-9]+)\.') {
    throw 'Inno Setup 7 or newer is required.'
}
$versionMatch = Select-String -LiteralPath "$projectRoot\pyproject.toml" -Pattern '^version = "([0-9]+\.[0-9]+\.[0-9]+)"$'
if (-not $versionMatch) { throw 'Cannot read the application version.' }
$appVersion = $versionMatch.Matches[0].Groups[1].Value

Copy-Item -LiteralPath "$projectRoot\README.md" -Destination "$projectRoot\dist\PDFPresenter\README.md"
Copy-Item -LiteralPath "$projectRoot\README.ru.md" -Destination "$projectRoot\dist\PDFPresenter\README.ru.md"
Copy-Item -LiteralPath "$projectRoot\CHANGELOG.md" -Destination "$projectRoot\dist\PDFPresenter\CHANGELOG.md"
& $InnoCompiler "/DAppVersion=$appVersion" "$projectRoot\installer\PDFPresenter.iss"
if ($LASTEXITCODE -ne 0) { throw 'Setup compilation failed.' }
$setupFile = Join-Path $projectRoot "dist\Scene-Setup-$appVersion-x64.exe"
$checksum = (Get-FileHash -LiteralPath $setupFile -Algorithm SHA256).Hash.ToLowerInvariant()
"$checksum  $(Split-Path -Leaf $setupFile)" | Set-Content -LiteralPath "$setupFile.sha256" -Encoding ascii
Write-Host "Ready: $setupFile"

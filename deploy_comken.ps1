param(
    [Parameter(Mandatory = $true)]
    [string]$Target,

    [Parameter(Mandatory = $true)]
    [string]$VersionChange
)

$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$packageSource = Join-Path $repositoryRoot "comken"
$versionFile = Join-Path $packageSource "__init__.py"
$targetRoot = [System.IO.Path]::GetFullPath($Target).TrimEnd('\')
$repositoryRootNormalized = [System.IO.Path]::GetFullPath($repositoryRoot).TrimEnd('\')
$pathRoot = [System.IO.Path]::GetPathRoot($targetRoot).TrimEnd('\')

if ($targetRoot -ieq $repositoryRootNormalized -or $targetRoot.StartsWith("$repositoryRootNormalized\", [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "The deployment target cannot be this development repository or a folder inside it: $targetRoot"
}
if ($targetRoot -ieq $pathRoot) {
    throw "Specify a dedicated deployment folder, not a drive or share root: $targetRoot"
}

if (-not (Test-Path -LiteralPath $versionFile -PathType Leaf)) {
    throw "comken/__init__.py was not found: $versionFile"
}

$versionContent = [System.IO.File]::ReadAllText($versionFile, [System.Text.Encoding]::UTF8)
$versionMatch = [regex]::Match($versionContent, '(?m)^__version__ = "(?<version>\d+\.\d+\.\d+)"$')
if (-not $versionMatch.Success) {
    throw "The current version was not found in comken/__init__.py."
}

$currentVersion = [version]$versionMatch.Groups["version"].Value
switch -Regex ($VersionChange.ToLowerInvariant()) {
    '^patch$' {
        $nextVersion = [version]::new($currentVersion.Major, $currentVersion.Minor, $currentVersion.Build + 1)
        break
    }
    '^minor$' {
        $nextVersion = [version]::new($currentVersion.Major, $currentVersion.Minor + 1, 0)
        break
    }
    '^major$' {
        $nextVersion = [version]::new($currentVersion.Major + 1, 0, 0)
        break
    }
    '^\d+\.\d+\.\d+$' {
        $nextVersion = [version]$VersionChange
        break
    }
    default {
        throw "VersionChange must be patch, minor, major, or X.Y.Z: $VersionChange"
    }
}

if ($nextVersion -le $currentVersion) {
    throw "The new version must be greater than ${currentVersion}: $nextVersion"
}

$nextVersionText = $nextVersion.ToString(3)
Write-Host "Version: $currentVersion -> $nextVersionText"
$commit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
$wasDirtyBeforeVersionChange = [bool](& git -C $repositoryRoot status --porcelain)
$updatedContent = $versionContent.Remove(
    $versionMatch.Groups["version"].Index,
    $versionMatch.Groups["version"].Length
).Insert($versionMatch.Groups["version"].Index, $nextVersionText)
[System.IO.File]::WriteAllText($versionFile, $updatedContent, [System.Text.UTF8Encoding]::new($false))

Push-Location $repositoryRoot
try {
    & python -m ruff check comken tests
    if ($LASTEXITCODE -ne 0) {
        throw "Ruff failed. Deployment was stopped."
    }

    & python -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        throw "pytest failed. Deployment was stopped."
    }

}
finally {
    Pop-Location
}

[System.IO.Directory]::CreateDirectory($targetRoot) | Out-Null
$deploymentId = [guid]::NewGuid().ToString("N")
$stagingRoot = Join-Path $targetRoot ".comken-staging-$deploymentId"
$stagingPackage = Join-Path $stagingRoot "comken"
$currentPackage = Join-Path $targetRoot "comken"
$backupRoot = Join-Path $targetRoot "backup"
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPackage = Join-Path $backupRoot "comken-$timestamp-v$currentVersion"

try {
    [System.IO.Directory]::CreateDirectory($stagingPackage) | Out-Null
    & robocopy $packageSource $stagingPackage /E /XD __pycache__ /XF *.pyc /R:2 /W:2 /NFL /NDL /NJH /NJS
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE."
    }

    $oldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = $stagingRoot
    try {
        & python -c "import comken; assert comken.__version__ == '$nextVersionText'"
        if ($LASTEXITCODE -ne 0) {
            throw "The staged comken import check failed."
        }
    }
    finally {
        $env:PYTHONPATH = $oldPythonPath
    }

    if (Test-Path -LiteralPath $currentPackage) {
        [System.IO.Directory]::CreateDirectory($backupRoot) | Out-Null
        Move-Item -LiteralPath $currentPackage -Destination $backupPackage
    }

    try {
        Move-Item -LiteralPath $stagingPackage -Destination $currentPackage
    }
    catch {
        if ((-not (Test-Path -LiteralPath $currentPackage)) -and (Test-Path -LiteralPath $backupPackage)) {
            Move-Item -LiteralPath $backupPackage -Destination $currentPackage
        }
        throw
    }

    $deploymentRecord = @(
        "version=$nextVersionText"
        "deployed_at=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
        "git_commit=$commit"
        "working_tree_was_dirty=$($wasDirtyBeforeVersionChange.ToString().ToLowerInvariant())"
        "source=$repositoryRoot"
    ) -join [Environment]::NewLine
    [System.IO.File]::WriteAllText(
        (Join-Path $targetRoot "DEPLOYMENT.txt"),
        $deploymentRecord + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false)
    )

    Write-Host "Deployed comken $nextVersionText to $currentPackage"
    if ($wasDirtyBeforeVersionChange) {
        Write-Warning "The deployed source contained uncommitted changes. See DEPLOYMENT.txt."
    }
}
finally {
    if (Test-Path -LiteralPath $stagingRoot) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}

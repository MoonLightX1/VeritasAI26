# copies the project and skips whatever .gitignore says

$Source = $PSScriptRoot
$Dest   = Join-Path (Split-Path $Source -Parent) "MoneySprout-copy"

Write-Host "Removing old copy..."
if (Test-Path $Dest) {
    Remove-Item $Dest -Recurse -Force
}

New-Item -ItemType Directory -Path $Dest | Out-Null

# read .gitignore (skip blanks, comments and ! lines)
$ignore = @()
if (Test-Path "$Source\.gitignore") {
    $ignore = Get-Content "$Source\.gitignore" |
        Where-Object {
            $_.Trim() -ne "" -and
            -not $_.Trim().StartsWith("#") -and
            -not $_.Trim().StartsWith("!")
        }
}

function Test-Ignored($relativePath)
{
    $relativePath = $relativePath.Replace("\", "/")
    $parts = $relativePath.Split("/")
    $leaf = $parts[$parts.Length - 1]

    # never copy .git
    if ($parts -contains ".git") { return $true }

    foreach ($pattern in $ignore)
    {
        $p = $pattern.Trim()
        $anchored = $p.StartsWith("/")
        if ($anchored) { $p = $p.Substring(1) }

        # folder rule like venv/ or __pycache__/
        if ($p.EndsWith("/"))
        {
            $dir = $p.TrimEnd("/")

            if ($anchored) {
                # only at the top of the project
                if ($relativePath -eq $dir -or $relativePath.StartsWith("$dir/")) { return $true }
            }
            else {
                # any folder with that name, no matter how deep
                if ($parts -contains $dir) { return $true }
            }
            continue
        }

        # plain name or wildcard
        if ($anchored) {
            if ($relativePath -like $p) { return $true }
        }
        else {
            if ($leaf -like $p) { return $true }
            if ($relativePath -like $p) { return $true }
            # a folder name match also skips everything inside it
            foreach ($part in $parts) {
                if ($part -like $p) { return $true }
            }
        }
    }

    return $false
}

Write-Host "Copying..."

Get-ChildItem $Source -Recurse -Force | ForEach-Object {

    $relative = $_.FullName.Substring($Source.Length).TrimStart("\")

    if ($relative -eq "") { return }

    if (Test-Ignored $relative) {
        return
    }

    $target = Join-Path $Dest $relative

    if ($_.PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $target | Out-Null
    }
    else {
        $parent = Split-Path $target
        if (!(Test-Path $parent)) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }

        Copy-Item $_.FullName $target -Force
    }
}

Write-Host ""
Write-Host "Done! Copy is in $Dest"

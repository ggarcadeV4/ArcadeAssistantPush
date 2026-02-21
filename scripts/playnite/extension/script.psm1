# Arcade Assistant Playnite Extension
# Non-blocking bridge between Playnite and FastAPI Backend
# Refactored for Robustness and Performance

# --- Configuration ---
$BackendBaseUrl = "http://127.0.0.1:8000/api/game"

function Get-LedTags {
    param($Game)
    $tags = @()

    # Ensure Game and TagIds are not null
    if ($null -eq $Game -or $null -eq $Game.TagIds) {
        return $tags
    }

    foreach ($tagId in $Game.TagIds) {
        try {
            # Robustly fetch tag by ID
            $tag = $PlayniteApi.Database.Tags.Get($tagId)
            if ($null -ne $tag -and $tag.Name -match "\[LED:") {
                $tags += $tag.Name
            }
        } catch {
            # Ignore errors for specific tags
        }
    }
    return $tags
}

function Invoke-BackendAsync {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Endpoint,
        [string]$JsonPayload = $null
    )

    $Uri = "$BackendBaseUrl/$Endpoint"

    # Base64 encode the payload if it exists to safely pass through the command line
    $base64 = ""
    if ($null -ne $JsonPayload) {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($JsonPayload)
        $base64 = [System.Convert]::ToBase64String($bytes)
    }

    # Construct the background command
    # -NoProfile: Faster startup
    # -NonInteractive: Prevents hanging on input
    # -ExecutionPolicy Bypass: Ensures the command runs
    $psCommand = ""
    if ($base64) {
        $psCommand = "`$json = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('$base64')); Invoke-RestMethod -Uri '$Uri' -Method Post -Body `$json -ContentType 'application/json'"
    } else {
        $psCommand = "Invoke-RestMethod -Uri '$Uri' -Method Post"
    }

    # Spawning a separate process ensures Playnite UI NEVER freezes even if the backend is offline
    Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command & { $psCommand }"
}

function OnGameStarted {
    param($args)

    try {
        $game = $args.Game
        if ($null -eq $game) { return }

        $tags = Get-LedTags -Game $game

        $payload = @{
            game_name = $game.Name
            game_id   = $game.Id.ToString()
            tags      = $tags
            event     = "started"
            timestamp = [DateTime]::UtcNow.ToString("o") # ISO 8601
        }

        $json = $payload | ConvertTo-Json -Compress
        Invoke-BackendAsync -Endpoint "start" -JsonPayload $json
    } catch {
        # Ensure extension never crashes Playnite
    }
}

function OnGameStopped {
    param($args)

    try {
        Invoke-BackendAsync -Endpoint "stop"
    } catch {
        # Ensure extension never crashes Playnite
    }
}

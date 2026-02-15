# ============================================================================
# PLAYNITE SCRIPT: Execute BEFORE starting a game
# ============================================================================
# Paste this into: Playnite > Settings > Scripts > Execute before starting a game
#
# What it does:
#   1. Extracts the game name and LED:* Cinema Logic tag from the game's tags
#   2. POSTs a JSON payload to the Arcade Assistant backend
#   3. Backend triggers LEDBlinky with the correct lighting profile
#   4. Wrapped in try/catch with 2-second timeout — NEVER blocks game launch
# ============================================================================

try {
    # Extract game info
    $gameName = $Game.Name
    $romName = [System.IO.Path]::GetFileNameWithoutExtension($Game.GameImagePath)
    $platform = $Game.Platform.Name

    # Collect all tags (including LED:* Cinema Logic tags)
    $tagList = @()
    if ($Game.Tags) {
        foreach ($tag in $Game.Tags) {
            $tagList += $tag.Name
        }
    }

    # Build JSON payload
    $body = @{
        game_name = $gameName
        tags      = $tagList
        rom_name  = $romName
        platform  = $platform
    } | ConvertTo-Json -Depth 3

    # POST to Arcade Assistant backend (2-second timeout, fire-and-forget)
    $params = @{
        Uri         = "http://127.0.0.1:8000/api/game/start"
        Method      = "POST"
        Body        = $body
        ContentType = "application/json"
        TimeoutSec  = 2
    }
    Invoke-RestMethod @params | Out-Null

}
catch {
    # Silently swallow errors — NEVER prevent a game from launching
    # Uncomment the next line for debugging:
    # $__logger.Warn("Arcade Assistant game/start failed: $_")
}

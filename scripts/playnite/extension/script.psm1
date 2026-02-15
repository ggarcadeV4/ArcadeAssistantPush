function OnGameStarted {
    param($args)

    $gameName = $args.Game.Name
    $tags = @()

    # Extract the LED Tags based on NotebookLM rules
    if ($args.Game.TagIds) {
        $ledTags = $args.Game.TagIds | Where-Object {
            $PlayniteApi.Database.Tags.Get($_).Name -match "\[LED:"
        }
        foreach ($tagId in $ledTags) {
            $tags += $PlayniteApi.Database.Tags.Get($tagId).Name
        }
    }

    # Package the JSON Payload
    $payloadData = @{
        game_name = $gameName
        tags      = $tags
    }
    $jsonPayload = $payloadData | ConvertTo-Json -Compress

    # Base64 encode the payload to safely pass it to the background process
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($jsonPayload)
    $base64 = [System.Convert]::ToBase64String($bytes)

    # Fire the Non-Blocking HTTP Request
    $psCommand = "`$json = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('$base64')); Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/game/start' -Method Post -Body `$json -ContentType 'application/json'"

    Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command & { $psCommand }"
}

function OnGameStopped {
    param($args)

    # Fire the Non-Blocking HTTP Request to reset the LEDs
    $psCommand = "Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/game/stop' -Method Post"
    Start-Process powershell -WindowStyle Hidden -ArgumentList "-Command & { $psCommand }"
}

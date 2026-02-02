# Create test controls SOT file for ConsoleWizard testing

$sotPath = "A:\config\mappings\controls.json"
$sotDir = Split-Path $sotPath -Parent

# Create directory if it doesn't exist
if (!(Test-Path $sotDir)) {
    Write-Host "Creating directory: $sotDir" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $sotDir -Force | Out-Null
}

# Sample controls data
$sotData = @{
    "snes9x" = @{
        "input_player1_a" = "x"
        "input_player1_b" = "z"
        "input_player1_x" = "s"
        "input_player1_y" = "a"
        "input_player1_start" = "enter"
        "input_player1_select" = "shift"
        "input_player1_l" = "q"
        "input_player1_r" = "w"
        "input_player1_up" = "up"
        "input_player1_down" = "down"
        "input_player1_left" = "left"
        "input_player1_right" = "right"
    }
    "mame" = @{
        "input_player1_a" = "ctrl"
        "input_player1_b" = "alt"
        "input_player1_start" = "1"
        "input_player1_select" = "5"
        "input_player1_up" = "up"
        "input_player1_down" = "down"
        "input_player1_left" = "left"
        "input_player1_right" = "right"
    }
    "genesis_plus_gx" = @{
        "input_player1_a" = "x"
        "input_player1_b" = "z"
        "input_player1_c" = "c"
        "input_player1_start" = "enter"
        "input_player1_up" = "up"
        "input_player1_down" = "down"
        "input_player1_left" = "left"
        "input_player1_right" = "right"
    }
}

# Convert to JSON and save
$json = $sotData | ConvertTo-Json -Depth 10
$json | Out-File -Encoding UTF8 -FilePath $sotPath

Write-Host "✅ Created controls SOT at: $sotPath" -ForegroundColor Green
Write-Host "Cores available: snes9x, mame, genesis_plus_gx" -ForegroundColor Gray
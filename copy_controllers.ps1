$src = "C:\Users\Dad's PC\.gemini\antigravity\brain\1b88602d-1649-469f-aacc-abddcde84d0e"
$repoRoot = "w:\Arcade Assistant Master Build\Arcade Assistant Local"

# Target both public (dev) and dist (production serve) directories
$targets = @(
    "$repoRoot\frontend\public\assets\controllers",
    "$repoRoot\frontend\dist\assets\controllers"
)

foreach ($dst in $targets) {
    if (-not (Test-Path $dst)) {
        New-Item -ItemType Directory -Path $dst -Force | Out-Null
        Write-Host "[OK] Created: $dst"
    }

    # V2 images - cyberpunk neon glow style matching Stitch designs
    Copy-Item "$src\8bitdo_pro_2_v2_1774651543574.png" "$dst\8bitdo_pro_2.png" -Force
    Copy-Item "$src\8bitdo_sn30_v2_1774651558939.png" "$dst\8bitdo_sn30.png" -Force
    Copy-Item "$src\xbox_360_v2_1774651569834.png" "$dst\xbox_360.png" -Force
    Copy-Item "$src\ps4_dualshock_v2_1774651579098.png" "$dst\ps4_dualshock.png" -Force
    Copy-Item "$src\switch_pro_v2_1774651593869.png" "$dst\switch_pro.png" -Force
    Copy-Item "$src\8bitdo_ultimate_cyberpunk_1774656717176.png" "$dst\8bitdo_ultimate.png" -Force

    Write-Host "[OK] Deployed 6 controllers to: $dst"
}

Write-Host ""
Write-Host "Controller asset deployment complete!"
Write-Host ""
Write-Host "Dist assets:"
Get-ChildItem "$repoRoot\frontend\dist\assets\controllers" -Filter "*.png" | Format-Table Name, Length

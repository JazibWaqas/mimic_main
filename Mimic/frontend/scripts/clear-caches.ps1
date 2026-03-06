# Clear all frontend caches so styling builds from scratch.
# Run from repo root: .\frontend\scripts\clear-caches.ps1
# Then: cd frontend && npm run dev

$frontend = Join-Path $PSScriptRoot ".."
Set-Location $frontend

$removed = @()

if (Test-Path ".next") {
  Remove-Item -Recurse -Force ".next"
  $removed += ".next"
}

if (Test-Path "node_modules\.cache") {
  Remove-Item -Recurse -Force "node_modules\.cache"
  $removed += "node_modules\.cache"
}

if (Test-Path ".turbo") {
  Remove-Item -Recurse -Force ".turbo"
  $removed += ".turbo"
}

if ($removed.Count -eq 0) {
  Write-Host "No cache folders found. .next was already gone or you are in the wrong directory."
} else {
  Write-Host "Removed: $($removed -join ', ')"
}

Write-Host "Done. Run: npm run dev"

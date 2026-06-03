# Remove stale shell variables that override .env (common after sandbox testing).
$vars = @(
    "EBAY_CLIENT_ID",
    "EBAY_CLIENT_SECRET",
    "EBAY_SANDBOX_CLIENT_ID",
    "EBAY_SANDBOX_CLIENT_SECRET",
    "EBAY_USE_SANDBOX",
    "DISABLE_LIVE_API_WRITES",
    "CARDMARKET_BULK_FILE_PATH"
)
foreach ($name in $vars) {
    if (Test-Path "Env:$name") {
        Remove-Item "Env:$name"
        Write-Host "Removed Env:$name"
    }
}
Write-Host "Done. Run: ebay-workflows validate-env"

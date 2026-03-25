# Скрипт для створення самопідписаного сертифіката та підпису LAN-FT.exe
# Запускати від імені Адміністратора (якщо потрібно встановити сертифікат у довірені)

$certSubject = "CN=LAN-FT-SelfSigned"
$exePath = "dist\LAN-FT\LAN-FT.exe"

if (-not (Test-Path $exePath)) {
    Write-Error "Файл $exePath не знайдено. Спочатку запустіть build.bat"
    exit 1
}

# 1. Пошук існуючого сертифіката
$cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $certSubject } | Select-Object -First 1

if (-not $cert) {
    Write-Host "Створення нового самопідписаного сертифіката..."
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $certSubject -HashAlgorithm SHA256 -KeyLength 2048 -NotAfter (Get-Date).AddYears(2)
    Write-Host "Сертифікат створено: $($cert.Thumbprint)"
} else {
    Write-Host "Використання існуючого сертифіката: $($cert.Thumbprint)"
}

# 2. Підпис файлу
# Використовуємо Set-AuthenticodeSignature (вбудовано в PowerShell)
Write-Host "Підписання $exePath..."
$status = Set-AuthenticodeSignature -FilePath $exePath -Certificate $cert -TimestampServer "http://timestamp.digicert.com"

if ($status.Status -eq "Valid") {
    Write-Host "УСПІХ: Файл підписано успішно!" -ForegroundColor Green
} else {
    Write-Host "ПОМИЛКА підпису: $($status.StatusMessage)" -ForegroundColor Red
}

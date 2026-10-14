# Compila (e opcionalmente grava) o firmware do JOQUEI.
#
# Uso:
#   .\firmware\build.ps1
#   .\firmware\build.ps1 -Upload -Port COM8
#   .\firmware\build.ps1 -ListPorts
#
# O arduino-cli vive dentro da instalacao da Arduino IDE e nao esta no PATH.

param(
  [switch]$Upload,
  [string]$Port = 'COM8',
  [switch]$ListPorts,
  [string]$Sketch = 'joquei_p4'
)

$ErrorActionPreference = 'Stop'

$CLI = "$env:LOCALAPPDATA\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
if (-not (Test-Path $CLI)) { throw "arduino-cli nao encontrado em $CLI" }

# PSRAM=enabled: obrigatorio. O framebuffer de 720x1280x2 = 1,8 MB mora na PSRAM,
#   e o padrao do core e disabled - sem isso getPsramSize() da 0 e a tela nao sobe.
# CDCOnBoot=default: manda o Serial para o UART0 -> ponte CH343 -> COM8, que e por
#   onde o agente conversa. Com CDCOnBoot=cdc a COM8 fica MUDA.
# FlashSize=32M: GD25Q256 das placas Waveshare.
$FQBN = "esp32:esp32:esp32p4:PSRAM=enabled,FlashSize=32M,PartitionScheme=default_8MB,USBMode=default,CDCOnBoot=default"

if ($ListPorts) {
  & $CLI board list
  Write-Host "`nVID 1A86 = ponte CH343 (log e agente) | VID 303A = USB nativa do P4" -ForegroundColor Cyan
  return
}

$sketch = Join-Path $PSScriptRoot $Sketch
Write-Host "sketch : $sketch"
Write-Host "fqbn   : $FQBN`n"

$out = & $CLI compile --fqbn $FQBN $sketch 2>&1
$out | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) { throw "compilacao falhou" }

$m = $out | Select-String -Pattern 'Sketch uses (\d+) bytes' | Select-Object -First 1
if ($m) {
  $bytes = [int]$m.Matches[0].Groups[1].Value
  Write-Host "`nbinario: $([math]::Round($bytes/1024,1)) KB ($bytes bytes)" -ForegroundColor Green
}

if ($Upload) {
  Write-Host "`ngravando em $Port ..." -ForegroundColor Yellow
  & $CLI upload --fqbn $FQBN --port $Port $sketch
  if ($LASTEXITCODE -ne 0) { throw "gravacao falhou" }
  Write-Host "gravado." -ForegroundColor Green
}

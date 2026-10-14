# Compila (e opcionalmente grava) o firmware do REDEA.
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
  [string]$Sketch = 'redea_p4',
  [ValidateSet('postv3','prev3')]
  [string]$Variant = 'postv3'
)

$ErrorActionPreference = 'Stop'

$CLI = "$env:LOCALAPPDATA\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
if (-not (Test-Path $CLI)) { throw "arduino-cli nao encontrado em $CLI" }

# ChipVariant: NAO DEIXAR DE FORA. O boards.txt lista 'prev3' antes de 'postv3',
#   entao um FQBN sem esta chave pega o default do arduino-cli, que e prev3 -
#   bootloader de amostra de engenharia (esp32p4_es, 360 MHz). Numa placa com
#   silicio de producao isso trava o bootloader de 2o estagio ANTES do console
#   subir: boot loop eterno com rst:0x10 (CHIP_LP_WDT_RESET) e nem uma linha do
#   sketch. Foi exatamente o que aconteceu com a placa de serial 5B90124374
#   (ESP32-P4 rev v3.2, ROM esp32p4-eco7-20260109, 400 MHz).
#   Use -Variant prev3 nas placas antigas, que sao pre-v3.
# PSRAM=enabled: obrigatorio. O framebuffer de 720x1280x2 = 1,8 MB mora na PSRAM.
# CDCOnBoot=default: manda o Serial para o UART0 -> ponte CH343 -> COM, que e por
#   onde o agente conversa. Com CDCOnBoot=cdc a porta fica MUDA.
# FlashSize=32M: GD25Q256 das placas Waveshare.
$FQBN = "esp32:esp32:esp32p4:ChipVariant=$Variant,PSRAM=enabled,FlashSize=32M,PartitionScheme=default_8MB,USBMode=default,CDCOnBoot=default"

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

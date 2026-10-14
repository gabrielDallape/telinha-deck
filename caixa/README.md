# Caixa da TELINHA

Caixa e suporte de monitor para a Waveshare ESP32-P4-WIFI6-Touch-LCD-5.
As medidas vêm do STEP oficial da Waveshare
(`github.com/waveshareteam/ESP32-P4-WIFI6-Touch-LCD-5/hardware/mechanical`).
`python caixa.py --checar <stp>` confere se a placa encosta na caixa e se o
suporte encosta na caixa. Hoje nenhum dos dois encosta.

## Peças (`stl/`)

| arquivo | imprimir | obs |
|---|---|---|
| `telinha_caixa.stl` | costas na mesa, do jeito que está | sem suporte; o canal do trilho é ponte de 16 mm |
| `telinha_suporte_{15,25,35}graus.stl` | deitado, do jeito que está | sem suporte; escolha um ângulo |

PLA ou PETG, 0,2 mm, 3 perímetros, 20 % de preenchimento. Perto de PC quente,
PETG aguenta melhor.

## Ferragem

- **4 parafusos M2,5 × 6 mm**, cabeça cilíndrica. Eles rosqueiam nos espaçadores
  que já vêm soldados na placa. **Não use parafuso maior que 6 mm**: com 8 mm a
  ponta passa do espaçador e bate no fundo do LCD.
- Fita dupla-face VHB (3M) de 50 × 45 mm para colar o suporte no monitor.

## Montagem

1. A placa entra pela frente da caixa, com o vidro para cima e as USB-C do
   lado das janelas. O vidro fica rente à borda.
2. Pela traseira, aperte os 4 M2,5 × 6 sem forçar.
3. Encaixe o trilho do suporte num dos dois canais das costas. Use o canal
   perto da borda que vai ficar para cima. O trilho entra pelo lado das USB-C e
   para no batente do meio.
4. Cole a placa do suporte atrás do monitor, logo acima da borda de baixo. A
   caixa fica pendurada abaixo do monitor, 4 mm abaixo da borda.

Os botões RST, BOOT e PWR (power) ficam na lateral, para apertar com clipe ou
palito. O cartão SD entra pela fenda do lado oposto às USB-C.

Mudou alguma medida? Os números ficam no topo de `caixa.py`. Rode
`python caixa.py` para gerar as STL de novo e `python render.py` para gerar os
PNGs de conferência.

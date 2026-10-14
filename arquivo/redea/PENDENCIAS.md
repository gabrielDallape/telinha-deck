# Pendências

## 1. Página `claude` bugava e piscava — RESOLVIDO em 21/09/2026

Eram **duas** causas, e a segunda estava escondida atrás da primeira.

### Causa A: o card inteiro ia no fio a cada mudancinha

Trocar a ferramenta em execução mudava o conteúdo do card, e o card inteiro
(16 a 24 KB) era retransmitido. Com sessões trabalhando ao mesmo tempo, isso
enchia os 38 KB/s.

**Correção:** remendos. `remendo.py` compara a imagem nova com a que a placa
tem, em dez faixas horizontais, agrupa as faixas vizinhas que mudaram e recorta
só esses retângulos. O firmware ganhou o campo `sx`/`sy` no evento `img`: em vez
de trocar o sprite, ele desenha o recorte por cima do que já está lá e marca
sujo apenas aquele botão. Medido: **83% menos bytes por troca de ferramenta**
(3,5 KB contra 20,8 KB).

Quando o remendo não compensa — mudou mais de 55% da área, ou a placa não tem
mais aquela arte — cai automaticamente no card inteiro.

### Causa B: a confirmação saía antes do desenho

Esta era a origem real do "chegou corrompida", e existia desde o início.

O firmware mandava o `imgok` do **último** pedaço *antes* de decodificar e
desenhar. O PC, que só manda o pedaço seguinte depois da confirmação, disparava
a próxima arte enquanto a placa ainda estava dentro do `drawJpg` — e nesses
milissegundos ninguém lê a UART. O buffer de RX estourava e a linha seguinte
chegava com 15 ou 20 bytes a menos.

O diagnóstico só apareceu quando separei as duas mensagens de erro do remendo:
`faltaram 15 bytes (1608 de 1623)` em vez de um genérico "inválido".

**Correção:** o último pedaço confirma **depois** de desenhar, nos dois caminhos
(card inteiro e remendo). Quando falha, vai `imgbad` + `imgok` — o primeiro
agenda o reenvio, o segundo destrava a fila.

### Medido depois, em 100 s de uso real na página `claude`

| | antes | depois |
|---|---|---|
| Artes corrompidas | várias, algumas desistindo em 3/3 | **0** |
| Bytes perdidos na serial | constante | **0** |
| Redesenhos de tela inteira | vários | **0** |
| Ocupação da serial | 16,7% | **8,2%** |

93 remendos e 5 cards inteiros no período. `agent/teste_remendo.py` reproduz a
medição com a placa simulada, sem precisar tocar na tela.

## 2. Card de sessão parada fica vazio no miolo — MENOR

Sem ferramenta em execução e sem atividade recente, sobra um buraco. Daria para
puxar o resumo do último turno ou o diff pendente.

## 3. O patch da LovyanGFX é frágil — CUIDADO PERMANENTE

Atualizar a biblioteca desfaz o fix do clock do PHY do MIPI-DSI e a placa volta
a não bootar. Ver o README, seção da placa rev v3.2.

# Mobilidade e roteamento em MANET com ns-3: AODV, OLSR e DSDV

Trabalho final de Redes Móveis, Engenharia de Software, IFG Câmpus Inhumas, 2026/2.
Prof. Rogério Sousa e Silva.

**Grupo:** Gabriel Braga, Dante de Souza, Thays Marques e Luis Hernandez Penariol

Este repositório contém tudo o que é necessário para reproduzir o experimento do artigo:
o código da simulação, o script que roda o lote, os dados brutos de todas as execuções,
o script de análise e os gráficos.

## 1. O experimento em uma página

**Pergunta de pesquisa:** como diferentes níveis de mobilidade afetam o desempenho dos
protocolos AODV, OLSR e DSDV em uma rede móvel Ad Hoc?

| Item | Valor |
|---|---|
| Simulador | ns-3.48 |
| Tecnologia | IEEE 802.11b em modo Ad Hoc, 11 Mbps (DSSS) |
| Nós | 20 |
| Área | 500 × 500 m |
| Mobilidade | `RandomWaypointMobilityModel`, velocidade constante, pausa 0 s |
| Velocidades (variável independente) | 1, 5, 10 e 20 m/s |
| Protocolos (fator de comparação) | AODV, OLSR e DSDV, parâmetros padrão do ns-3 |
| Aplicação | UDP de taxa constante, 4 fluxos simultâneos |
| Pacotes | 1024 bytes de carga UDP, 20 pacotes/s por fluxo |
| Tempo de simulação | 120 s (tráfego de 20 s a 110 s) |
| Repetições | 5 por configuração (seed 12345, runs 1 a 5) |
| Métricas | throughput, PDR, atraso médio fim a fim e jitter |
| Variável adicional do grupo | quantidade de nós: 10, 20, 30 e 40 |

Total: 3 protocolos × 4 velocidades × 5 repetições = **60 execuções** na etapa 1, mais
**180 execuções** na etapa 2 (variável adicional) e 60 execuções de apoio (seção 8.5).

## 2. Estrutura do repositório

```
manet-ns3/
├── README.md
├── requirements.txt            dependências Python da análise
├── src/
│   └── manet-routing.cc        simulação (um único programa para os três protocolos)
├── scripts/
│   ├── run_batch.sh            executa o lote e grava um CSV por execução
│   └── analyze.py              validação, estatísticas e gráficos
├── data/
│   ├── raw/
│   │   ├── base/               etapa 1: 60 CSVs + batch.log
│   │   ├── extensao/           etapa 2: 180 CSVs + batch.log
│   │   └── apoio_arp_padrao/   apoio: 60 CSVs + batch.log
│   └── processed/              tabelas geradas por analyze.py
├── figures/                    gráficos em PNG (300 dpi) e PDF (vetorial)
└── article/                    artigo no modelo SBC
    ├── artigo.tex, artigo.pdf  fonte LaTeX e PDF
    ├── referencias.bib         referências
    ├── tabela_base.tex         tabela de resultados, gerada por analyze.py
    ├── figuras/                figuras do artigo, geradas por analyze.py
    └── sbc-template.sty, sbc.bst   modelo da SBC
```

## 3. Ambiente

Ambiente em que os dados deste repositório foram gerados:

| Componente | Versão |
|---|---|
| ns-3 | 3.48 (tag `ns-3.48`, commit `d2add90b`) |
| Sistema operacional | Ubuntu 24.04.5 LTS, x86_64 |
| Compilador | g++ 13.3.0 |
| CMake / Ninja | 3.28.3 / 1.11.1 |
| Python | 3.13 |
| numpy / pandas / matplotlib | 2.5.3 / 3.0.5 / 3.11.2 |

Requisitos mínimos do ns-3.48: g++ 11.1 ou superior, CMake 3.25 ou superior e
Python 3.10 ou superior.

## 4. Preparação e compilação

```bash
# 4.1 Dependências do sistema (Ubuntu/Debian)
sudo apt update
sudo apt install -y g++ cmake ninja-build python3 python3-pip git

# 4.2 Este repositório
git clone https://github.com/opinha/manet-ns3.git
cd manet-ns3
pip install -r requirements.txt

# 4.3 ns-3.48
git clone --branch ns-3.48 --depth 1 https://gitlab.com/nsnam/ns-3-dev.git ~/ns-3
# espelho oficial, caso o GitLab esteja indisponível:
#   git clone --branch ns-3.48 --depth 1 https://github.com/nsnam/ns-3-dev-git.git ~/ns-3

# 4.4 Configuração e compilação (cerca de 30 minutos em 2 núcleos)
cd ~/ns-3
./ns3 configure -d optimized \
    --enable-modules "aodv;olsr;dsdv;wifi;internet;applications;mobility;flow-monitor"
./ns3 build
```

O perfil `optimized` só muda o tempo de execução. O perfil padrão (`./ns3 configure`
sem `-d`) também funciona, só é mais lento.

Em uma máquina sem `sudo`, nada precisa ser instalado no sistema: o ns-3 fica inteiro
dentro de `~/ns-3`. Se o CMake for antigo, `pip install --user cmake` resolve.

## 5. Execução

### 5.1 Um cenário

```bash
cp src/manet-routing.cc ~/ns-3/scratch/
cd ~/ns-3
./ns3 run "scratch/manet-routing --protocol=AODV --speed=10 --run=3 --simTime=120"
```

Saída esperada (resumida):

```
protocolo=AODV (ns3::aodv::RoutingProtocol) velocidade=10 m/s nos=20 fluxos=4 seed=12345 run=3
  fluxo 1 (no 0 -> no 19): gerados=1800 recebidos=... PDR=...% vazao=... Mbps atraso=... ms ...
  ...
  REDE: gerados=7200 recebidos=... PDR=...% vazao=... Mbps atraso=... ms jitter=... ms ...
```

Para gravar o CSV, acrescente `--csv=arquivo.csv`. Para ver todos os parâmetros:
`./ns3 run "scratch/manet-routing --PrintHelp"`.

### 5.2 Lote completo

A partir da raiz deste repositório:

```bash
NS3_DIR=~/ns-3 JOBS=2 scripts/run_batch.sh base       # etapa 1: 60 execuções
NS3_DIR=~/ns-3 JOBS=2 scripts/run_batch.sh extensao   # etapa 2: 180 execuções
NS3_DIR=~/ns-3 JOBS=2 scripts/run_batch.sh arp        # apoio: 60 execuções
# ou tudo de uma vez:
NS3_DIR=~/ns-3 JOBS=2 scripts/run_batch.sh tudo
```

O script copia `src/manet-routing.cc` para `scratch/` do ns-3, compila e executa cada
combinação. `JOBS` é o número de simulações em paralelo. Execuções que já têm CSV são
puladas; `FORCE=1` refaz tudo. Tempo medido com `JOBS=2`: cerca de 4 minutos para a
etapa 1 e 30 minutos para a etapa 2.

### 5.3 Análise

```bash
python3 scripts/analyze.py
```

Gera o relatório de validação, as tabelas em `data/processed/` e os gráficos em
`figures/`. Opções: `--compare-speed` (velocidade do gráfico comparativo, padrão 20) e
`--ext-speed` (velocidade do painel da variável adicional, padrão 10).

## 6. Parâmetros da simulação

Todos são argumentos de linha de comando de `manet-routing`. Os valores padrão são os
do experimento-base.

| Argumento | Significado | Unidade | Padrão |
|---|---|---|---|
| `--protocol` | protocolo de roteamento: `AODV`, `OLSR` ou `DSDV` | | `AODV` |
| `--speed` | velocidade dos nós (constante) | m/s | 10 |
| `--run` | número da repetição (`RngRun`) | | 1 |
| `--seed` | seed mestre do gerador pseudoaleatório | | 12345 |
| `--simTime` | tempo de simulação | s | 120 |
| `--nodes` | quantidade de nós | | 20 |
| `--flows` | fluxos UDP simultâneos | | 4 |
| `--area` | lado da área quadrada | m | 500 |
| `--pause` | tempo de pausa do Random Waypoint | s | 0 |
| `--pktSize` | carga UDP por pacote | bytes | 1024 |
| `--packetRate` | pacotes por segundo em cada fluxo | pacotes/s | 20 |
| `--txPower` | potência de transmissão | dBm | 4 |
| `--appStart` | início do tráfego | s | 20 |
| `--appStop` | fim do tráfego (negativo: `simTime` − 10) | s | 110 |
| `--arpDeadTimeout` | bloqueio do ARP após falha de resolução (seção 8.5) | s | 1 |
| `--lineSpacing` | modo de validação: nós parados em linha com este espaçamento | m | 0 (desligado) |
| `--csv` | arquivo CSV de saída (uma linha por fluxo) | | vazio |
| `--mobilityTrace` | CSV com a posição de todos os nós a cada 1 s | | vazio |
| `--flowmonXml` | XML bruto do FlowMonitor | | vazio |
| `--quiet` | não imprime o resumo no terminal | | `false` |

## 7. Aleatoriedade e repetições

- **Seed mestre:** 12345, fixa em todas as execuções (`RngSeedManager::SetSeed`).
- **Repetições:** `--run` de 1 a 5 (`RngSeedManager::SetRun`). Cada run usa subfluxos
  independentes do gerador, que é o método recomendado pelo manual do ns-3.
- **Mesma mobilidade para os três protocolos:** os streams aleatórios da posição inicial,
  dos destinos do Random Waypoint e do instante de início dos fluxos são fixados no código.
  Para a mesma combinação de run, velocidade e número de nós, as trajetórias são idênticas
  com AODV, OLSR e DSDV (conferido na seção 9). A diferença entre protocolos não vem de
  topologias diferentes.
- **Determinismo:** repetir um comando produz o mesmo CSV, byte a byte, na mesma máquina.
  Em outro processador ou compilador podem aparecer diferenças numéricas pequenas, porque
  o perfil `optimized` usa instruções nativas da CPU.
- Seed e run ficam registrados em cada linha dos CSVs e no `batch.log`.

## 8. Decisões do cenário e justificativas

O enunciado fixa nós, área, mobilidade, velocidades, aplicação, tempo, tamanho de pacote,
fluxos e protocolos. O que ele não fixa foi decidido como descrito abaixo.

### 8.1 Camada física e alcance de rádio

- IEEE 802.11b, 11 Mbps (`DsssRate11Mbps`) para dados, controle e broadcast
  (`ConstantRateWifiManager` e `NonUnicastMode`). Com a mesma taxa em tudo, as mensagens
  de roteamento têm o mesmo alcance dos dados.
- Propagação em espaço livre (`FriisPropagationLossModel`) em 2,412 GHz.
- **Potência de transmissão de 4 dBm, que dá alcance de 197 m.** Com a potência padrão do
  ns-3 (16 dBm) o alcance passa de 700 m, maior que a diagonal da área (707 m): todos os
  nós se alcançariam em um salto e o protocolo de roteamento não teria o que fazer. Com
  197 m as rotas têm vários saltos e a rede fica conectada na maior parte do tempo.
  O alcance foi medido (seção 9) e confere com a conta: o Wi-Fi do ns-3 só detecta quadros
  acima de −82 dBm, e a perda de Friis em 2,412 GHz chega a 86 dB em 197,5 m.

### 8.2 Tráfego

- `UdpClient` → `UdpServer`, 1024 bytes de carga a cada 50 ms (20 pacotes/s), o que dá
  163,84 kbps por fluxo na aplicação e 168,32 kbps na camada IP (1052 bytes por pacote
  com os cabeçalhos UDP e IP). Carga oferecida total: 0,673 Mbps na camada IP. É uma carga
  baixa para um canal de 11 Mbps, de propósito: as perdas vêm de rotas quebradas, não de
  congestionamento.
- Fluxo *i*: nó *i* → nó *N − 1 − i* (0→19, 1→18, 2→17, 3→16 com 20 nós). Origens e
  destinos não se repetem e são os mesmos para todos os protocolos.
- Cada fluxo começa com um atraso sorteado entre 0 e 1 s, para as fontes não transmitirem
  em fase.

### 8.3 Linha do tempo e duração útil do throughput

- 0 a 20 s: aquecimento, sem tráfego. Dá tempo para OLSR e DSDV montarem as tabelas.
- 20 a 110 s: tráfego. Cada fluxo gera exatamente 1800 pacotes.
- 110 a 120 s: sem tráfego novo, para os pacotes em trânsito chegarem.

**Duração útil = 90 s** (`appStop − appStart`), igual para todos os fluxos, protocolos e
repetições. O throughput não usa `timeLastRxPacket − timeFirstTxPacket` porque esse
intervalo encolhe quando um fluxo para de receber e inflaria a vazão justamente nos piores
casos.

### 8.4 Definição das métricas

| Métrica | Cálculo por fluxo | Unidade |
|---|---|---|
| Throughput | `rxBytes × 8 / 90 s` (`rxBytes` do FlowMonitor, inclui cabeçalhos IP e UDP) | Mbps |
| PDR | `rxPackets / appTxPackets × 100` | % |
| Atraso médio | `delaySum / rxPackets` | ms |
| Jitter médio | `jitterSum / (rxPackets − 1)` | ms |
| Perdidos | `appTxPackets − rxPackets` | pacotes |

Métricas da rede em uma execução: throughput é a soma dos 4 fluxos; PDR, atraso e jitter
são calculados sobre os totais (soma dos recebidos, soma dos atrasos etc.), o que equivale
a uma média ponderada pelo número de pacotes.

**Por que o PDR usa os pacotes gerados pela aplicação e não o `txPackets` do FlowMonitor.**
Quando o OLSR não tem rota, o socket UDP recusa o envio e o pacote nem chega à camada IP,
onde o FlowMonitor mede. Esses pacotes sumiriam do denominador e o PDR do OLSR ficaria
artificialmente alto. AODV e DSDV não têm esse efeito porque guardam o pacote em fila
enquanto procuram rota. Teste que mostra a diferença: 2 nós a 300 m (fora de alcance),
1800 pacotes gerados.

| Protocolo | Gerados pela aplicação | `txPackets` do FlowMonitor | Recebidos |
|---|---|---|---|
| AODV | 1800 | 1800 | 0 |
| OLSR | 1800 | **0** | 0 |
| DSDV | 1800 | 1800 | 0 |

O contador da aplicação vem do trace `Tx` do `UdpClient`. As duas contagens ficam no CSV
(`appTxPackets` e `ipTxPackets`).

### 8.5 Ajuste do ARP

Único parâmetro fora do padrão do ns-3 além da camada física:
`ns3::ArpCache::DeadTimeout` passou de 100 s para **1 s**.

No padrão, um vizinho que não responde aos pedidos ARP (um envio e três repetições, com
1 s entre elas) fica marcado como morto por 100 s.
Durante esse tempo todo pacote encaminhado a ele é descartado em silêncio, sem aviso ao
protocolo de roteamento. Em uma simulação de 120 s com nós móveis, uma falha momentânea
vira um bloqueio que dura quase a execução inteira. O efeito apareceu em um teste
preliminar com AODV a 1 m/s: a resolução ARP de um nó para um vizinho falhou logo no
início do tráfego (pedidos em t ≈ 20 a 23 s, sem resposta). Aos 48 s o AODV passou a usar
esse vizinho como próximo salto, a 184 m e dentro do alcance, e o nó descartou todos os
pacotes do fluxo (20 por segundo) durante 46 s, porque a entrada ARP continuava bloqueada.
O OLSR, no mesmo cenário, entregou 99,9%. Esse comportamento é do modelo de ARP e não dos
protocolos avaliados.

Para medir o efeito, a etapa 1 inteira foi repetida com o valor padrão
(`data/raw/apoio_arp_padrao/`). PDR médio em % (tabela completa em
`data/processed/resumo.md`):

| Velocidade | AODV 1 s / 100 s | OLSR 1 s / 100 s | DSDV 1 s / 100 s |
|---|---|---|---|
| 1 m/s | 97,7 / 89,1 | 97,3 / 97,3 | 96,5 / 96,5 |
| 5 m/s | 91,8 / 89,1 | 86,0 / 84,9 | 79,2 / 78,3 |
| 10 m/s | 89,8 / 74,5 | 73,3 / 65,0 | 68,1 / 59,2 |
| 20 m/s | 86,6 / 74,0 | 57,9 / 54,7 | 56,2 / 52,3 |

O ajuste melhora os três protocolos, mais o AODV, e reduz a variação entre execuções.
A ordem entre os protocolos é a mesma com ou sem o ajuste.

### 8.6 Protocolos de roteamento

Parâmetros padrão do ns-3.48, sem ajuste. Os que mais pesam na interpretação:

| Protocolo | Tipo | Parâmetros padrão relevantes |
|---|---|---|
| AODV | reativo | HELLO a cada 1 s, 2 perdas toleradas, rota ativa por 3 s |
| OLSR | proativo, estado de enlace | HELLO a cada 2 s, TC a cada 5 s |
| DSDV | proativo, vetor de distância | atualização periódica a cada 15 s, assentamento de 5 s |

## 9. Validação do cenário

Feita antes do lote, como pedem os slides. Todos os comandos usam o próprio
`manet-routing`.

| O que foi conferido | Como | Resultado |
|---|---|---|
| Protocolo instalado | o programa lê o `TypeId` do roteamento no nó 0 e grava no CSV | `ns3::aodv::`, `ns3::olsr::` e `ns3::dsdv::RoutingProtocol`, conforme pedido |
| Alcance do rádio | 2 nós parados, `--nodes=2 --flows=1 --lineSpacing=D` | PDR 100% até 197 m e 0% a partir de 198 m |
| Roteamento em múltiplos saltos | 5 nós em linha a 150 m, `--nodes=5 --flows=1 --lineSpacing=150` | PDR de 99,6% a 100% e 4,00 saltos nos três protocolos |
| Mesma mobilidade entre protocolos | `--mobilityTrace` nos três protocolos, mesmo run | arquivos de posição idênticos (mesmo MD5); runs diferentes dão trajetórias diferentes |
| Determinismo | mesmo comando duas vezes | CSVs idênticos |
| Consistência dos dados | `scripts/analyze.py` | `data/processed/validacao.txt`, 0 problemas |

Exemplo:

```bash
cd ~/ns-3
./ns3 run "scratch/manet-routing --protocol=OLSR --nodes=5 --flows=1 --lineSpacing=150"
```

## 10. Saídas

### 10.1 Dados brutos

Um CSV por execução, com uma linha por fluxo:
`data/raw/<etapa>/manet_<PROTOCOLO>_v<velocidade>_n<nós>_run<run>.csv`.
O `batch.log` de cada etapa registra data e hora, versão do ns-3, protocolo, velocidade,
nós, seed, run, situação e duração de cada execução.

| Coluna | Significado |
|---|---|
| `protocol`, `speed`, `nodes`, `flows`, `areaSide`, `pause`, `pktSize`, `packetRate`, `txPowerDbm`, `arpDeadTimeout`, `simTime`, `appStart`, `appStop` | parâmetros da execução |
| `seed`, `run` | seed mestre e número da repetição |
| `flowId`, `srcNode`, `dstNode`, `dstPort` | identificação do fluxo |
| `appTxPackets` | pacotes gerados pela aplicação |
| `ipTxPackets` | pacotes vistos pelo FlowMonitor na camada IP da origem |
| `rxPackets`, `lostPackets`, `rxBytes` | recebidos, perdidos e bytes recebidos |
| `throughputMbps`, `pdrPct`, `delayMs`, `jitterMs` | métricas do fluxo (seção 8.4) |
| `timesForwarded`, `avgHops` | encaminhamentos e saltos por pacote entregue (1 + encaminhamentos / recebidos) |
| `timeFirstTxS`, `timeLastRxS` | instantes da primeira transmissão e da última recepção |
| `runCtrlTxPackets`, `runCtrlTxBytes` | mensagens de controle do roteamento transmitidas por todos os nós na execução (valor repetido nas linhas da mesma execução) |
| `routingTypeId` | protocolo realmente instalado |

`delayMs` e `jitterMs` ficam como `nan` quando o fluxo não recebeu pacotes suficientes
para o cálculo.

### 10.2 Dados processados (`data/processed/`)

| Arquivo | Conteúdo |
|---|---|
| `validacao.txt` | relatório de validação dos dados brutos |
| `por_fluxo.csv` | todas as linhas brutas reunidas |
| `por_execucao.csv` | métricas da rede em cada execução |
| `estatisticas.csv` | média, mínimo, máximo, desvio-padrão amostral e IC 95% por configuração |
| `resumo.md` | as mesmas estatísticas em tabelas legíveis |
| `apoio_arp_padrao_estatisticas.csv` | estatísticas da etapa de apoio (seção 8.5) |

O intervalo de confiança de 95% usa a distribuição t de Student com 4 graus de liberdade
(t = 2,776 para 5 repetições).

### 10.3 Gráficos (`figures/`)

| Arquivo | Gráfico |
|---|---|
| `fig1_pdr_x_velocidade` | PDR × velocidade |
| `fig2_throughput_x_velocidade` | Throughput × velocidade |
| `fig3_delay_x_velocidade` | Atraso × velocidade |
| `fig4_jitter_x_velocidade` | Jitter × velocidade |
| `fig5_comparativo_v20` | comparativo agregado entre os protocolos a 20 m/s |
| `fig6_extensao_nos_v10` | variável adicional: as 4 métricas × quantidade de nós a 10 m/s |
| `fig7_extensao_pdr_x_velocidade` | variável adicional: PDR × velocidade para cada quantidade de nós |
| `painel_base` | figuras 1 a 4 em um único painel (economiza espaço no artigo) |
| `apoio_controle_x_velocidade` | tráfego de controle do roteamento × velocidade |
| `apoio_saltos_x_velocidade` | saltos por pacote entregue × velocidade |

Todos têm uma série por protocolo, média de 5 execuções e barras de erro com IC 95%,
truncadas nos limites físicos da métrica (0 e, no PDR, 100%).

### 10.4 Artigo (`article/`)

`analyze.py` também grava as três figuras do artigo (`article/figuras/`, no tamanho final
da página e sem título embutido) e as linhas da tabela de resultados
(`article/tabela_base.tex`). Assim, todo número e todo gráfico do artigo sai dos CSVs
brutos pelo mesmo script. Para compilar:

```bash
cd article
pdflatex artigo && bibtex artigo && pdflatex artigo && pdflatex artigo
```

No Overleaf, basta enviar a pasta `article/` inteira e compilar `artigo.tex`.

## 11. Resultados da etapa 1 (experimento-base)

Média ± IC 95% de 5 execuções, 20 nós. Mínimo, máximo e desvio-padrão de cada célula
estão em `data/processed/resumo.md` e `data/processed/estatisticas.csv`.

**PDR (%)**

| Velocidade (m/s) | AODV | OLSR | DSDV |
|---|---|---|---|
| 1 | 97,7 ± 3,1 | 97,3 ± 5,7 | 96,5 ± 7,7 |
| 5 | 91,8 ± 10,8 | 86,0 ± 2,0 | 79,2 ± 3,6 |
| 10 | 89,8 ± 4,5 | 73,3 ± 4,6 | 68,1 ± 5,0 |
| 20 | 86,6 ± 4,4 | 57,9 ± 4,5 | 56,2 ± 2,0 |

**Throughput da rede (Mbps)**, carga oferecida de 0,673 Mbps

| Velocidade (m/s) | AODV | OLSR | DSDV |
|---|---|---|---|
| 1 | 0,658 ± 0,021 | 0,655 ± 0,038 | 0,649 ± 0,052 |
| 5 | 0,618 ± 0,073 | 0,579 ± 0,013 | 0,533 ± 0,024 |
| 10 | 0,605 ± 0,030 | 0,494 ± 0,031 | 0,458 ± 0,033 |
| 20 | 0,583 ± 0,030 | 0,390 ± 0,030 | 0,378 ± 0,013 |

**Atraso médio fim a fim (ms)**

| Velocidade (m/s) | AODV | OLSR | DSDV |
|---|---|---|---|
| 1 | 4,8 ± 2,2 | 5,5 ± 5,1 | 4,3 ± 2,5 |
| 5 | 6,3 ± 4,5 | 11,5 ± 7,4 | 14,4 ± 11,0 |
| 10 | 8,9 ± 5,3 | 16,0 ± 3,8 | 13,4 ± 12,0 |
| 20 | 20,0 ± 17,3 | 17,9 ± 5,7 | 10,4 ± 5,9 |

**Jitter médio (ms)**

| Velocidade (m/s) | AODV | OLSR | DSDV |
|---|---|---|---|
| 1 | 1,8 ± 1,2 | 2,7 ± 3,7 | 2,0 ± 1,8 |
| 5 | 3,2 ± 1,8 | 3,4 ± 1,7 | 3,5 ± 1,8 |
| 10 | 4,6 ± 2,8 | 6,8 ± 3,6 | 4,9 ± 2,3 |
| 20 | 6,6 ± 1,2 | 7,1 ± 2,7 | 4,6 ± 2,1 |

![Painel do experimento-base](figures/painel_base.png)

![Comparativo a 20 m/s](figures/fig5_comparativo_v20.png)

O que os dados mostram:

- **A 1 m/s os três protocolos empatam** (PDR entre 96% e 98%, intervalos sobrepostos).
- **O PDR cai com a velocidade nos três, mas em intensidades muito diferentes.** De 1 para
  20 m/s o AODV perde cerca de 11 pontos percentuais; OLSR e DSDV perdem cerca de 40.
- **O throughput acompanha o PDR**, como esperado em tráfego UDP de taxa constante.
- **Atraso e jitter crescem com a velocidade**, mas os intervalos de confiança são largos
  e se sobrepõem entre protocolos. Não há base para ordenar os protocolos nessas duas
  métricas.
- **Não há um ponto de ruptura brusco.** Em OLSR e DSDV a maior queda por m/s acontece
  entre 1 e 5 m/s e depois a degradação segue gradual.
- **Dados de apoio que ajudam a explicar a diferença:** o tráfego de controle do AODV
  dobra de 1 para 20 m/s (de 10,8 para 21,5 kbps), enquanto o de OLSR e DSDV cresce pouco
  (de 11,7 para 15,3 e de 12,6 para 13,8 kbps, `apoio_controle_x_velocidade`). E os pacotes que OLSR e DSDV conseguem entregar em
  alta velocidade percorrem menos saltos (de 1,6 para 1,3 a 1,4), enquanto no AODV o
  número de saltos se mantém em 1,7 (`apoio_saltos_x_velocidade`). Isso é compatível com
  o AODV refazendo rotas assim que elas quebram e com os proativos mantendo rotas velhas
  até a próxima atualização periódica.

**Condição escolhida para o comparativo agregado (figura 5): 20 m/s.** É o nível de maior
mobilidade e onde a diferença entre os protocolos é maior em relação à variação entre
execuções: os intervalos de PDR e throughput do AODV não se sobrepõem aos de OLSR e DSDV.

## 12. Resultados da etapa 2 (variável adicional: quantidade de nós)

**Por que essa variável:** com a área fixa em 500 × 500 m, a quantidade de nós define a
densidade da rede, que atua nos dois sentidos. Mais nós dão mais caminhos alternativos
quando um enlace quebra, mas também mais mensagens de controle e mais disputa pelo canal.
Foram usados 10, 20, 30 e 40 nós, com as 4 velocidades, os 3 protocolos e 5 repetições.
Todo o resto é igual à etapa 1. O ponto de 20 nós é a própria etapa 1.

**PDR (%) a 10 m/s**

| Nós | AODV | OLSR | DSDV |
|---|---|---|---|
| 10 | 86,1 ± 13,0 | 72,7 ± 18,0 | 72,8 ± 14,9 |
| 20 | 89,8 ± 4,5 | 73,3 ± 4,6 | 68,1 ± 5,0 |
| 30 | 84,8 ± 8,2 | 73,7 ± 8,0 | 68,4 ± 9,3 |
| 40 | 77,7 ± 5,2 | 77,1 ± 6,0 | 71,5 ± 9,2 |

**PDR (%) a 20 m/s**

| Nós | AODV | OLSR | DSDV |
|---|---|---|---|
| 10 | 83,1 ± 9,5 | 58,1 ± 13,6 | 56,1 ± 12,0 |
| 20 | 86,6 ± 4,4 | 57,9 ± 4,5 | 56,2 ± 2,0 |
| 30 | 80,7 ± 4,3 | 59,8 ± 6,0 | 59,2 ± 7,1 |
| 40 | 79,7 ± 5,4 | 65,5 ± 6,3 | 65,2 ± 7,5 |

**PDR (%) a 1 m/s**

| Nós | AODV | OLSR | DSDV |
|---|---|---|---|
| 10 | 83,6 ± 26,7 | 81,3 ± 30,8 | 80,8 ± 27,8 |
| 20 | 97,7 ± 3,1 | 97,3 ± 5,7 | 96,5 ± 7,7 |
| 30 | 95,9 ± 6,3 | 97,1 ± 4,5 | 95,7 ± 6,1 |
| 40 | 86,0 ± 8,6 | 96,2 ± 3,3 | 96,8 ± 1,6 |

**Tráfego de controle (kbps) a 10 m/s**

| Nós | AODV | OLSR | DSDV |
|---|---|---|---|
| 10 | 5,8 ± 0,5 | 4,5 ± 0,2 | 3,0 ± 0,2 |
| 20 | 16,2 ± 3,3 | 14,3 ± 0,3 | 13,6 ± 0,2 |
| 30 | 52,1 ± 9,3 | 28,4 ± 0,5 | 31,7 ± 0,4 |
| 40 | 101,1 ± 12,3 | 47,9 ± 1,3 | 57,2 ± 0,8 |

![Variável adicional a 10 m/s](figures/fig6_extensao_nos_v10.png)

![PDR por quantidade de nós](figures/fig7_extensao_pdr_x_velocidade.png)

O que os dados mostram:

- **A tendência da etapa 1 se confirma em todas as densidades:** o PDR de OLSR e DSDV cai
  com a velocidade com 10, 20, 30 ou 40 nós.
- **A densidade muda a distância entre os protocolos.** Com mais nós, OLSR e DSDV melhoram
  em alta velocidade (a 20 m/s, de cerca de 57% com 20 nós para 65% com 40) e o AODV piora
  (de 87% para 80%). A 10 m/s com 40 nós os três ficam dentro do mesmo intervalo.
- **O custo do AODV cresce muito mais rápido com a densidade:** o tráfego de controle a
  10 m/s vai de 16 kbps com 20 nós para 101 kbps com 40, contra 48 kbps do OLSR e 57 kbps
  do DSDV. O jitter do AODV acompanha (de 4,6 para 17,0 ms).
- **Em rede densa e quase parada a ordem se inverte:** a 1 m/s com 40 nós, o AODV entrega
  86% e os proativos 96% a 97%.
- **Com 10 nós a rede é esparsa demais:** a 1 m/s o PDR médio fica perto de 82% com
  intervalo de ±27 a ±31 pontos, porque em algumas execuções há fluxos sem caminho durante
  boa parte da simulação (no run 3, três dos quatro fluxos entregam entre 10% e 31% nos
  três protocolos). Esse ponto mede mais a conectividade do que o roteamento.

## 13. Limitações

- Cinco repetições dão intervalos de confiança largos, principalmente em atraso e jitter.
  Diferenças menores que as barras de erro não devem ser tratadas como diferenças reais.
- Atraso e jitter só consideram pacotes entregues. Um protocolo que perde os pacotes das
  rotas mais longas pode parecer mais rápido por isso.
- No modelo Wi-Fi usado, o alcance de detecção de portadora é igual ao alcance de
  recepção (197 m), o que favorece o problema do terminal oculto mais do que em placas
  reais.
- A propagação em espaço livre dá um alcance em forma de disco perfeito, sem
  desvanecimento nem obstáculos.
- O Random Waypoint concentra os nós no centro da área ao longo do tempo, e esse efeito
  cresce com a velocidade.
- Os resultados valem para os parâmetros padrão dos protocolos no ns-3.48 e para este
  cenário. Não sustentam afirmações gerais do tipo "o protocolo X é o melhor".

## 14. Rastreabilidade

Versão do repositório correspondente ao artigo entregue: commit `PREENCHER`
(ou tag `entrega-artigo`).

## 15. Referências

- ns-3 Tutorial: https://www.nsnam.org/docs/tutorial/html/
- ns-3 Manual, Random Variables: https://www.nsnam.org/docs/manual/html/random-variables.html
- ns-3 Model Library, AODV: https://www.nsnam.org/docs/models/html/aodv.html
- ns-3 Model Library, OLSR: https://www.nsnam.org/docs/models/html/olsr.html
- ns-3 Model Library, DSDV: https://www.nsnam.org/docs/models/html/dsdv.html
- ns-3 Model Library, Flow Monitor: https://www.nsnam.org/docs/models/html/flow-monitor.html
- C. Perkins, E. Belding-Royer, S. Das. RFC 3561: Ad hoc On-Demand Distance Vector (AODV) Routing, 2003.
- T. Clausen, P. Jacquet. RFC 3626: Optimized Link State Routing Protocol (OLSR), 2003.
- C. Perkins, P. Bhagwat. Highly Dynamic Destination-Sequenced Distance-Vector Routing (DSDV) for Mobile Computers. ACM SIGCOMM, 1994.

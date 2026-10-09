#!/usr/bin/env bash
#
# Executa as simulacoes em lote e grava um CSV por execucao em data/raw/.
#
# Uso:
#   NS3_DIR=~/ns-3 scripts/run_batch.sh base       # etapa 1: 3 protocolos x 4 velocidades x 5 runs
#   NS3_DIR=~/ns-3 scripts/run_batch.sh extensao   # etapa 2: variavel adicional (quantidade de nos)
#   NS3_DIR=~/ns-3 scripts/run_batch.sh arp        # apoio: etapa 1 repetida com o ARP padrao do ns-3
#   NS3_DIR=~/ns-3 scripts/run_batch.sh tudo       # as tres etapas
#
# Variaveis de ambiente opcionais:
#   NS3_DIR  diretorio do ns-3 (padrao: ~/ns-3)
#   JOBS     execucoes em paralelo (padrao: 1)
#   FORCE=1  refaz execucoes que ja tem CSV (padrao: pula as existentes)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NS3_DIR="${NS3_DIR:-$HOME/ns-3}"
JOBS="${JOBS:-1}"
FORCE="${FORCE:-0}"

# ---------------------------------------------------------------------------
# Parametros do experimento (os mesmos documentados no README)
# ---------------------------------------------------------------------------
SEED=12345                 # seed mestre, fixa
RUNS="1 2 3 4 5"           # repeticoes independentes (RngRun)
PROTOCOLS="AODV OLSR DSDV"
SIM_TIME=120               # s

# Etapa 1, experimento-base
BASE_SPEEDS="1 5 10 20"    # m/s
BASE_NODES=20

# Etapa 2, variavel adicional do grupo: quantidade de nos.
# O ponto de 20 nos e reaproveitado da etapa 1, por isso nao e executado de novo.
EXT_NODES="10 30 40"
EXT_SPEEDS="1 5 10 20"     # m/s

# Apoio: repete a etapa 1 com o tempo de bloqueio padrao do ARP (100 s), para medir o
# efeito do ajuste adotado no cenario (1 s). Nao entra nos graficos principais.
ARP_DEFAULT_ARGS="--arpDeadTimeout=100"

# ---------------------------------------------------------------------------
# Modo interno: executa uma unica simulacao (chamado pelo xargs)
# ---------------------------------------------------------------------------
if [[ "${1:-}" == "__one" ]]; then
    binary="$2"; outdir="$3"; protocol="$4"; speed="$5"; nodes="$6"; run="$7"; extra="${8:-}"
    csv="$(printf '%s/manet_%s_v%02d_n%02d_run%02d.csv' "$outdir" "$protocol" "$speed" "$nodes" "$run")"
    if [[ -s "$csv" && "$FORCE" != "1" ]]; then
        exit 0
    fi
    start=$(date +%s)
    status=ok
    "$binary" --protocol="$protocol" --speed="$speed" --nodes="$nodes" --run="$run" \
        --seed="$SEED" --simTime="$SIM_TIME" $extra --csv="$csv.tmp" --quiet=true || status=ERRO
    if [[ "$status" == "ok" ]]; then
        mv "$csv.tmp" "$csv"
    else
        rm -f "$csv.tmp"
    fi
    end=$(date +%s)
    printf '%s ns3=%s protocol=%s speed=%s nodes=%s seed=%s run=%s %s status=%s duracao=%ss\n' \
        "$(date -Iseconds)" "$NS3_VERSION" "$protocol" "$speed" "$nodes" "$SEED" "$run" \
        "$extra" "$status" "$((end - start))" | tee -a "$outdir/batch.log"
    [[ "$status" == "ok" ]]
    exit
fi

# ---------------------------------------------------------------------------
# Modo normal
# ---------------------------------------------------------------------------
stage="${1:-}"
if [[ "$stage" != "base" && "$stage" != "extensao" && "$stage" != "arp" && "$stage" != "tudo" ]]; then
    sed -n '3,14p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 1
fi

if [[ ! -x "$NS3_DIR/ns3" ]]; then
    echo "ERRO: ns-3 nao encontrado em '$NS3_DIR'. Defina NS3_DIR com o caminho correto." >&2
    exit 1
fi

export NS3_VERSION SEED SIM_TIME FORCE
NS3_VERSION="$(cat "$NS3_DIR/VERSION")"

# Copia o codigo para o scratch do ns-3 e compila (incremental).
cp "$REPO_DIR/src/manet-routing.cc" "$NS3_DIR/scratch/manet-routing.cc"
echo ">> Compilando no ns-3 $NS3_VERSION ($NS3_DIR)"
(cd "$NS3_DIR" && ./ns3 build)

# O executavel e chamado diretamente (em vez de ./ns3 run) para permitir paralelismo.
binary="$(ls "$NS3_DIR"/build/scratch/ns"$NS3_VERSION"-manet-routing* 2>/dev/null | head -n 1 || true)"
if [[ -z "$binary" ]]; then
    echo "ERRO: executavel manet-routing nao encontrado em $NS3_DIR/build/scratch" >&2
    exit 1
fi
export LD_LIBRARY_PATH="$NS3_DIR/build/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

run_stage() {
    local name="$1" speeds="$2" nodes_list="$3" extra="${4:-}"
    local outdir="$REPO_DIR/data/raw/$name"
    mkdir -p "$outdir"
    echo ">> Etapa '$name': saida em $outdir (JOBS=$JOBS)"
    for nodes in $nodes_list; do
        for protocol in $PROTOCOLS; do
            for speed in $speeds; do
                for run in $RUNS; do
                    # sem espaco no fim da linha: o xargs -L junta linhas que terminam em branco
                    echo "$binary $outdir $protocol $speed $nodes $run${extra:+ $extra}"
                done
            done
        done
    done | xargs -P "$JOBS" -L 1 bash "${BASH_SOURCE[0]}" __one
}

if [[ "$stage" == "base" || "$stage" == "tudo" ]]; then
    run_stage base "$BASE_SPEEDS" "$BASE_NODES"
fi
if [[ "$stage" == "extensao" || "$stage" == "tudo" ]]; then
    run_stage extensao "$EXT_SPEEDS" "$EXT_NODES"
fi
if [[ "$stage" == "arp" || "$stage" == "tudo" ]]; then
    run_stage apoio_arp_padrao "$BASE_SPEEDS" "$BASE_NODES" "$ARP_DEFAULT_ARGS"
fi

echo ">> Concluido. Proximo passo: python3 scripts/analyze.py"

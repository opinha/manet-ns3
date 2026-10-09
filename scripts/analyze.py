#!/usr/bin/env python3
"""
Processa os CSVs brutos das simulacoes, valida os dados, calcula as estatisticas
e gera os graficos do artigo.

Uso (a partir da raiz do repositorio):
    python3 scripts/analyze.py
    python3 scripts/analyze.py --compare-speed 20 --ext-speed 10

Entradas:
    data/raw/base/*.csv       etapa 1 (experimento-base)
    data/raw/extensao/*.csv   etapa 2 (variavel adicional: quantidade de nos)
    data/raw/apoio_arp_padrao/*.csv   opcional: etapa 1 com o ARP padrao do ns-3

Saidas:
    data/processed/por_fluxo.csv        todas as linhas brutas reunidas
    data/processed/por_execucao.csv     metricas da rede em cada execucao
    data/processed/estatisticas.csv     media, minimo, maximo, desvio-padrao e IC 95%
    data/processed/resumo.md            tabelas prontas para leitura
    data/processed/validacao.txt        relatorio de validacao dos dados
    figures/*.png e figures/*.pdf       graficos
    article/figuras/*.pdf               graficos compactos, no tamanho usado no artigo
    article/tabela_base.tex             linhas da tabela de resultados do artigo
"""

import argparse
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "raw"
PROCESSED = REPO / "data" / "processed"
FIGURES = REPO / "figures"
ARTICLE = REPO / "article"

PROTOCOLS = ["AODV", "OLSR", "DSDV"]
EXPECTED_TYPEID = {
    "AODV": "ns3::aodv::RoutingProtocol",
    "OLSR": "ns3::olsr::RoutingProtocol",
    "DSDV": "ns3::dsdv::RoutingProtocol",
}

# Identidade visual de cada protocolo: cor + marcador + estilo de linha + hachura,
# para que as series continuem distinguiveis em impressao preto e branco.
STYLE = {
    "AODV": dict(color="#2a78d6", marker="o", linestyle="-", hatch=""),
    "OLSR": dict(color="#eb6834", marker="s", linestyle="--", hatch="//"),
    "DSDV": dict(color="#1baf7a", marker="^", linestyle="-.", hatch=".."),
}
INK = "#0b0b0b"
INK_SOFT = "#52514e"
GRID = "#e4e3df"

# metrica -> (rotulo do eixo, titulo curto)
METRICS = {
    "pdrPct": ("PDR (%)", "Taxa de entrega (PDR)"),
    "throughputMbps": ("Throughput da rede (Mbps)", "Throughput"),
    "delayMs": ("Atraso médio fim a fim (ms)", "Atraso fim a fim"),
    "jitterMs": ("Jitter médio (ms)", "Jitter"),
}
DECIMALS = {"pdrPct": 1, "throughputMbps": 3, "delayMs": 1, "jitterMs": 1}
EXTRA_METRICS = {
    "avgHops": ("Saltos por pacote entregue", "Número de saltos"),
    "ctrlKbps": ("Tráfego de controle (kbps)", "Custo de controle do roteamento"),
}

# Valor critico t de Student bicaudal para 95% (indice = graus de liberdade).
T95 = [math.nan, 12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
       2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
       2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def t95(df: int) -> float:
    if df < 1:
        return math.nan
    return T95[df] if df < len(T95) else 1.96


# ---------------------------------------------------------------------------
# Leitura e validacao
# ---------------------------------------------------------------------------
def load_stage(stage: str) -> pd.DataFrame:
    files = sorted((RAW / stage).glob("manet_*.csv"))
    if not files:
        return pd.DataFrame()
    df = pd.concat((pd.read_csv(f) for f in files), ignore_index=True)
    df.insert(0, "stage", stage)
    return df


def validate(flows: pd.DataFrame, expected_runs: int) -> list[str]:
    """Confere a consistencia dos dados brutos. Devolve as linhas do relatorio."""
    report: list[str] = []
    problems = 0

    def check(ok: bool, message: str, detail: str = "") -> None:
        nonlocal problems
        report.append(f"[{'OK' if ok else 'PROBLEMA'}] {message}")
        if not ok:
            problems += 1
            if detail:
                report.append(detail)

    key = ["protocol", "speed", "nodes"]
    runs = flows.groupby(key)["run"].nunique()
    bad = runs[runs != expected_runs]
    check(bad.empty, f"cada configuração tem {expected_runs} repetições "
                     f"({len(runs)} configurações, {int(runs.sum())} execuções)", bad.to_string())

    rows = flows.groupby(key + ["run"]).agg(n=("flowId", "size"), flows=("flows", "first"))
    bad = rows[rows.n != rows.flows]
    check(bad.empty, "cada execução tem uma linha por fluxo", bad.to_string())

    expected_tx = np.round(flows.packetRate * (flows.appStop - flows.appStart))
    bad = flows[flows.appTxPackets != expected_tx]
    check(bad.empty, "pacotes gerados por fluxo = taxa × duração útil "
                     f"({int(expected_tx.iloc[0])} pacotes)",
          bad[key + ["run", "flowId", "appTxPackets"]].to_string())

    bad = flows[(flows.rxPackets > flows.ipTxPackets) | (flows.ipTxPackets > flows.appTxPackets)]
    check(bad.empty, "recebidos ≤ transmitidos na camada IP ≤ gerados pela aplicação",
          bad[key + ["run", "flowId", "appTxPackets", "ipTxPackets", "rxPackets"]].to_string())

    bad = flows[flows.lostPackets != flows.appTxPackets - flows.rxPackets]
    check(bad.empty, "perdidos = gerados − recebidos")

    bad = flows[(flows.pdrPct < 0) | (flows.pdrPct > 100) | flows.pdrPct.isna()]
    check(bad.empty, "PDR entre 0 e 100% em todos os fluxos")

    offered = flows.appTxPackets * (flows.pktSize + 28) * 8 / (flows.appStop - flows.appStart) / 1e6
    bad = flows[(flows.throughputMbps < 0) | (flows.throughputMbps > offered + 1e-9)]
    check(bad.empty, "throughput entre 0 e a carga oferecida")

    bad = flows[(flows.rxPackets > 0) & (flows.delayMs.isna() | (flows.delayMs <= 0))]
    check(bad.empty, "atraso positivo em todo fluxo com recepção")

    bad = flows[(flows.rxPackets > 1) & (flows.jitterMs.isna() | (flows.jitterMs < 0))]
    check(bad.empty, "jitter não negativo em todo fluxo com mais de um pacote recebido")

    bad = flows[flows.timeLastRxS > flows.simTime]
    check(bad.empty, "nenhuma recepção depois do fim da simulação")

    bad = flows[flows.routingTypeId != flows.protocol.map(EXPECTED_TYPEID)]
    check(bad.empty, "protocolo instalado confere com o protocolo pedido")

    for col in ["areaSide", "pause", "pktSize", "packetRate", "txPowerDbm", "arpDeadTimeout", "simTime",
                "appStart", "appStop", "seed", "flows"]:
        values = sorted(flows[col].unique())
        check(len(values) == 1, f"parâmetro constante {col} = {values[0] if len(values) == 1 else values}")

    dead = flows[flows.rxPackets == 0]
    report.append(f"[INFO] fluxos sem nenhuma recepção: {len(dead)} de {len(flows)} "
                  "(entram no PDR e no throughput como zero; não entram no atraso nem no jitter)")
    if not dead.empty:
        report.append(dead.groupby(key).size().rename("fluxos").to_string())

    report.append(f"RESULTADO: {problems} problema(s) encontrado(s)")
    return report


# ---------------------------------------------------------------------------
# Agregacao
# ---------------------------------------------------------------------------
def per_run(flows: pd.DataFrame) -> pd.DataFrame:
    """Metricas da rede em cada execucao (os fluxos de uma execucao sao agregados)."""
    out = []
    for keys, g in flows.groupby(["stage", "protocol", "speed", "nodes", "seed", "run"]):
        rx = g.rxPackets.sum()
        app_tx = g.appTxPackets.sum()
        duration = g.appStop.iloc[0] - g.appStart.iloc[0]
        jitter_samples = (g.rxPackets - 1).clip(lower=0)
        row = dict(zip(["stage", "protocol", "speed", "nodes", "seed", "run"], keys))
        row.update(
            appTxPackets=app_tx,
            rxPackets=rx,
            lostPackets=app_tx - rx,
            rxBytes=g.rxBytes.sum(),
            flowsWithoutRx=int((g.rxPackets == 0).sum()),
            # throughput da rede: soma dos fluxos sobre a mesma duracao util
            throughputMbps=g.rxBytes.sum() * 8 / duration / 1e6,
            pdrPct=100 * rx / app_tx,
            # medias ponderadas pelo numero de pacotes: equivalem a
            # soma(delaySum) / soma(rxPackets) e soma(jitterSum) / soma(rxPackets - 1)
            delayMs=(g.delayMs * g.rxPackets).sum() / rx if rx > 0 else np.nan,
            jitterMs=((g.jitterMs * jitter_samples).sum() / jitter_samples.sum()
                      if jitter_samples.sum() > 0 else np.nan),
            avgHops=1 + g.timesForwarded.sum() / rx if rx > 0 else np.nan,
            ctrlTxPackets=g.runCtrlTxPackets.iloc[0],
            ctrlKbps=g.runCtrlTxBytes.iloc[0] * 8 / g.simTime.iloc[0] / 1e3,
        )
        out.append(row)
    return pd.DataFrame(out)


def statistics(runs: pd.DataFrame) -> pd.DataFrame:
    """Media, minimo, maximo, desvio-padrao amostral e IC 95% por configuracao."""
    out = []
    for keys, g in runs.groupby(["protocol", "speed", "nodes"]):
        for metric in list(METRICS) + list(EXTRA_METRICS):
            v = g[metric].dropna()
            n = len(v)
            std = v.std(ddof=1) if n > 1 else np.nan
            out.append(dict(
                protocol=keys[0], speed=keys[1], nodes=keys[2], metric=metric, n=n,
                mean=v.mean() if n else np.nan,
                min=v.min() if n else np.nan,
                max=v.max() if n else np.nan,
                std=std,
                ci95=t95(n - 1) * std / math.sqrt(n) if n > 1 else np.nan,
            ))
    stats = pd.DataFrame(out)
    stats["protocol"] = pd.Categorical(stats.protocol, PROTOCOLS, ordered=True)
    return stats.sort_values(["nodes", "speed", "protocol", "metric"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Graficos
# ---------------------------------------------------------------------------
def setup_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelcolor": INK_SOFT,
        "axes.edgecolor": INK_SOFT,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": INK_SOFT,
        "ytick.color": INK_SOFT,
        "text.color": INK,
        "legend.frameon": False,
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
    })


def save(fig, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.png")
    fig.savefig(FIGURES / f"{name}.pdf")
    plt.close(fig)
    print(f"  figures/{name}.png")


def draw_lines(ax, stats: pd.DataFrame, metric: str, x: str, x_label: str) -> None:
    """Uma serie por protocolo, com media e barra de erro (IC 95%)."""
    data = stats[stats.metric == metric]
    xs = sorted(data[x].unique())
    # pequeno deslocamento horizontal para as barras de erro nao se sobreporem
    dodge = 0.012 * (max(xs) - min(xs)) if len(xs) > 1 else 0
    for i, protocol in enumerate(PROTOCOLS):
        d = data[data.protocol == protocol].sort_values(x)
        s = STYLE[protocol]
        # barras de erro truncadas nos limites fisicos da metrica (0 e, no PDR, 100%)
        upper_limit = 100.0 if metric == "pdrPct" else np.inf
        yerr = np.vstack([np.minimum(d["ci95"], d["mean"]),
                          np.minimum(d["ci95"], upper_limit - d["mean"])])
        ax.errorbar(d[x] + (i - 1) * dodge, d["mean"], yerr=yerr, label=protocol,
                    color=s["color"], marker=s["marker"], linestyle=s["linestyle"],
                    linewidth=2, markersize=7, markeredgecolor="white", markeredgewidth=1,
                    capsize=3, elinewidth=1.2)
    ax.set_xticks(xs)
    ax.set_xlabel(x_label)
    ax.set_ylabel(METRICS.get(metric, EXTRA_METRICS.get(metric))[0])
    if metric == "pdrPct":
        ax.set_ylim(0, 105)
    else:
        ax.set_ylim(bottom=0)


def fig_metric_vs_speed(stats: pd.DataFrame, metric: str, name: str, nodes: int, runs: int) -> None:
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    draw_lines(ax, stats[stats.nodes == nodes], metric, "speed", "Velocidade dos nós (m/s)")
    title = METRICS.get(metric, EXTRA_METRICS.get(metric))[1]
    ax.set_title(f"{title} × velocidade")
    ax.legend(title=f"média de {runs} execuções, IC 95%", title_fontsize=8, fontsize=9)
    save(fig, name)


def fig_panel(stats: pd.DataFrame, x: str, x_label: str, name: str, suptitle: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.4))
    for ax, metric in zip(axes.flat, METRICS):
        draw_lines(ax, stats, metric, x, x_label)
        ax.set_title(METRICS[metric][1])
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.suptitle(suptitle, x=0.01, y=0.995, ha="left", fontsize=12, fontweight="bold")
    fig.legend(handles, labels, loc="upper left", ncol=3, fontsize=9, bbox_to_anchor=(0.0, 0.965))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    save(fig, name)


def fig_compare(runs: pd.DataFrame, stats: pd.DataFrame, speed: float, nodes: int, name: str) -> None:
    """Comparativo agregado entre os protocolos em uma condicao de mobilidade."""
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.4))
    sel_stats = stats[(stats.speed == speed) & (stats.nodes == nodes)]
    sel_runs = runs[(runs.speed == speed) & (runs.nodes == nodes)]
    for ax, metric in zip(axes, METRICS):
        d = sel_stats[sel_stats.metric == metric].set_index("protocol")
        highest = 0.0
        for i, protocol in enumerate(PROTOCOLS):
            s = STYLE[protocol]
            mean, ci = d.loc[protocol, "mean"], d.loc[protocol, "ci95"]
            ax.bar(i, mean, width=0.62, color=s["color"], hatch=s["hatch"],
                   edgecolor="white", linewidth=1)
            upper_limit = 100.0 if metric == "pdrPct" else np.inf
            ax.errorbar(i, mean, yerr=[[min(ci, mean)], [min(ci, upper_limit - mean)]],
                        color=INK, capsize=4, elinewidth=1.2)
            # cada ponto e uma execucao: mostra a variabilidade entre repeticoes
            points = sel_runs[sel_runs.protocol == protocol][metric].dropna()
            ax.scatter(np.full(len(points), i) + np.linspace(-0.18, 0.18, len(points)), points,
                       s=14, color="white", edgecolor=INK, linewidth=0.8, zorder=3)
            top = np.nanmax([min(mean + ci, upper_limit), points.max()])
            highest = max(highest, top)
            ax.annotate(f"{mean:.{DECIMALS[metric]}f}", (i, top), xytext=(0, 4),
                        textcoords="offset points", ha="center", fontsize=9, color=INK)
        ax.set_xticks(range(len(PROTOCOLS)), PROTOCOLS)
        ax.set_ylabel(METRICS[metric][0])
        ax.set_title(METRICS[metric][1])
        ax.grid(axis="x", visible=False)
        ax.set_ylim(0, highest * 1.15)  # folga para o rotulo acima da barra
    fig.suptitle(f"Comparativo entre protocolos a {speed:g} m/s "
                 "(barra: média; haste: IC 95%; pontos: execuções)",
                 x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    save(fig, name)


def fig_ext_pdr_by_nodes(stats: pd.DataFrame, name: str) -> None:
    """PDR x velocidade em paineis, um por quantidade de nos (mesma escala)."""
    nodes_list = sorted(stats.nodes.unique())
    fig, axes = plt.subplots(1, len(nodes_list), figsize=(2.9 * len(nodes_list), 3.3), sharey=True)
    for ax, nodes in zip(np.atleast_1d(axes), nodes_list):
        draw_lines(ax, stats[stats.nodes == nodes], "pdrPct", "speed", "Velocidade (m/s)")
        ax.set_title(f"{nodes} nós")
        if ax is not np.atleast_1d(axes)[0]:
            ax.set_ylabel("")
    handles, labels = np.atleast_1d(axes)[0].get_legend_handles_labels()
    fig.suptitle("PDR × velocidade para cada quantidade de nós (média de 5 execuções, IC 95%)",
                 x=0.01, y=0.995, ha="left", fontsize=12, fontweight="bold")
    fig.legend(handles, labels, loc="upper left", ncol=3, fontsize=9, bbox_to_anchor=(0.0, 0.93))
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    save(fig, name)


# ---------------------------------------------------------------------------
# Artefatos do artigo: mesmas estatisticas, graficos no tamanho final da pagina
# (15 cm de largura util no modelo SBC) e sem titulo, porque a legenda fica no LaTeX.
# ---------------------------------------------------------------------------
ARTICLE_RC = {"font.size": 7.5, "axes.titlesize": 8, "axes.labelsize": 7.5,
              "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7.5,
              "grid.linewidth": 0.5, "axes.linewidth": 0.6}
SHORT_LABEL = {"pdrPct": "PDR (%)", "throughputMbps": "Throughput (Mbps)",
               "delayMs": "Atraso (ms)", "jitterMs": "Jitter (ms)"}
TEXT_WIDTH_IN = 5.9


def draw_lines_compact(ax, stats: pd.DataFrame, metric: str, x: str) -> None:
    data = stats[stats.metric == metric]
    xs = sorted(data[x].unique())
    dodge = 0.012 * (max(xs) - min(xs))
    upper_limit = 100.0 if metric == "pdrPct" else np.inf
    for i, protocol in enumerate(PROTOCOLS):
        d = data[data.protocol == protocol].sort_values(x)
        st = STYLE[protocol]
        yerr = np.vstack([np.minimum(d["ci95"], d["mean"]),
                          np.minimum(d["ci95"], upper_limit - d["mean"])])
        ax.errorbar(d[x] + (i - 1) * dodge, d["mean"], yerr=yerr, label=protocol,
                    color=st["color"], marker=st["marker"], linestyle=st["linestyle"],
                    linewidth=1.3, markersize=4.5, markeredgecolor="white", markeredgewidth=0.6,
                    capsize=2, elinewidth=0.8, capthick=0.8)
    ax.set_xticks(xs)
    ax.set_ylim(0, 105) if metric == "pdrPct" else ax.set_ylim(bottom=0)


def save_article(fig, name: str) -> None:
    (ARTICLE / "figuras").mkdir(parents=True, exist_ok=True)
    fig.savefig(ARTICLE / "figuras" / f"{name}.pdf")
    plt.close(fig)
    print(f"  article/figuras/{name}.pdf")


def article_outputs(runs: pd.DataFrame, stats: pd.DataFrame, args) -> None:
    n = args.base_nodes
    with plt.rc_context(ARTICLE_RC):
        # Figura 1: as quatro metricas x velocidade
        fig, axes = plt.subplots(2, 2, figsize=(TEXT_WIDTH_IN, 2.8))
        for ax, metric in zip(axes.flat, METRICS):
            draw_lines_compact(ax, stats[stats.nodes == n], metric, "speed")
            ax.set_ylabel(SHORT_LABEL[metric])
        for ax in axes[1]:
            ax.set_xlabel("Velocidade dos nós (m/s)")
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.0))
        fig.tight_layout(rect=(0, 0, 1, 0.94), h_pad=0.5, w_pad=1.0)
        save_article(fig, "fig_base")

        # Figura 2: comparativo agregado na velocidade escolhida
        speed = args.compare_speed
        fig, axes = plt.subplots(1, 4, figsize=(TEXT_WIDTH_IN, 1.5))
        sel_stats = stats[(stats.speed == speed) & (stats.nodes == n)]
        sel_runs = runs[(runs.speed == speed) & (runs.nodes == n)]
        for ax, metric in zip(axes, METRICS):
            d = sel_stats[sel_stats.metric == metric].set_index("protocol")
            highest = 0.0
            upper_limit = 100.0 if metric == "pdrPct" else np.inf
            for i, protocol in enumerate(PROTOCOLS):
                st = STYLE[protocol]
                mean, ci = d.loc[protocol, "mean"], d.loc[protocol, "ci95"]
                ax.bar(i, mean, width=0.62, color=st["color"], hatch=st["hatch"],
                       edgecolor="white", linewidth=0.6)
                ax.errorbar(i, mean, yerr=[[min(ci, mean)], [min(ci, upper_limit - mean)]],
                            color=INK, capsize=2.5, elinewidth=0.8, capthick=0.8)
                points = sel_runs[sel_runs.protocol == protocol][metric].dropna()
                ax.scatter(np.full(len(points), i) + np.linspace(-0.18, 0.18, len(points)), points,
                           s=5, color="white", edgecolor=INK, linewidth=0.5, zorder=3)
                top = np.nanmax([min(mean + ci, upper_limit), points.max()])
                highest = max(highest, top)
                ax.annotate(f"{mean:.{DECIMALS[metric]}f}".replace(".", ","), (i, top),
                            xytext=(0, 2), textcoords="offset points", ha="center",
                            fontsize=6.5, color=INK)
            ax.set_xticks(range(len(PROTOCOLS)), PROTOCOLS, fontsize=6)
            ax.set_ylabel(SHORT_LABEL[metric])
            ax.grid(axis="x", visible=False)
            ax.set_ylim(0, highest * 1.17)
        fig.tight_layout(w_pad=0.8)
        save_article(fig, "fig_comparativo")

        # Figura 3: variavel adicional, PDR x velocidade para cada quantidade de nos
        nodes_list = sorted(stats.nodes.unique())
        if len(nodes_list) > 1:
            fig, axes = plt.subplots(1, len(nodes_list), figsize=(TEXT_WIDTH_IN, 1.6), sharey=True)
            for ax, nodes in zip(axes, nodes_list):
                draw_lines_compact(ax, stats[stats.nodes == nodes], "pdrPct", "speed")
                ax.set_title(f"{nodes} nós", fontweight="normal", loc="center")
                ax.set_xlabel("Velocidade (m/s)")
            axes[0].set_ylabel("PDR (%)")
            handles, labels = axes[0].get_legend_handles_labels()
            fig.legend(handles, labels, loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.0))
            fig.tight_layout(rect=(0, 0, 1, 0.88), w_pad=0.6)
            save_article(fig, "fig_extensao")

    # Tabela de resultados: media (desvio-padrao) por velocidade e protocolo
    def cell(row, decimals):
        return (f"{row['mean']:.{decimals}f} ({row['std']:.{decimals}f})").replace(".", ",")

    base = stats[stats.nodes == n]
    lines = []
    for speed in sorted(base.speed.unique()):
        for j, protocol in enumerate(PROTOCOLS):
            cells = []
            for metric in METRICS:
                r = base[(base.speed == speed) & (base.protocol == protocol) & (base.metric == metric)].iloc[0]
                cells.append(cell(r, DECIMALS[metric]))
            first = f"\\multirow{{3}}{{*}}{{{speed:g}}}" if j == 0 else ""
            lines.append(f"{first} & {protocol} & " + " & ".join(cells) + r" \\")
        lines.append(r"\midrule")
    lines[-1] = r"\bottomrule"
    (ARTICLE / "tabela_base.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  article/tabela_base.tex")


# ---------------------------------------------------------------------------
# Resumo em Markdown
# ---------------------------------------------------------------------------
def markdown_table(stats: pd.DataFrame, row_key: str, row_label: str) -> list[str]:
    lines = []
    for metric, (label, _) in {**METRICS, **EXTRA_METRICS}.items():
        lines += [f"**{label}**", "", f"| {row_label} | " + " | ".join(PROTOCOLS) + " |",
                  "|---|" + "---|" * len(PROTOCOLS)]
        d = stats[stats.metric == metric]
        for value in sorted(d[row_key].unique()):
            cells = []
            for protocol in PROTOCOLS:
                r = d[(d[row_key] == value) & (d.protocol == protocol)].iloc[0]
                cells.append(f"{r['mean']:.3f} ± {r['ci95']:.3f} (dp {r['std']:.3f}; "
                             f"{r['min']:.3f} a {r['max']:.3f})")
            lines.append(f"| {value:g} | " + " | ".join(cells) + " |")
        lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--runs", type=int, default=5, help="repetições esperadas por configuração")
    parser.add_argument("--base-nodes", type=int, default=20, help="quantidade de nós do experimento-base")
    parser.add_argument("--compare-speed", type=float, default=20,
                        help="velocidade (m/s) do gráfico comparativo agregado")
    parser.add_argument("--ext-speed", type=float, default=10,
                        help="velocidade (m/s) do painel da variável adicional")
    args = parser.parse_args()

    base = load_stage("base")
    if base.empty:
        print("ERRO: nenhum CSV em data/raw/base. Rode scripts/run_batch.sh base primeiro.", file=sys.stderr)
        return 1
    ext = load_stage("extensao")
    flows = pd.concat([base, ext], ignore_index=True)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    setup_style()

    print("Validação dos dados brutos")
    report = validate(flows, args.runs)
    (PROCESSED / "validacao.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join("  " + line for line in report))

    runs = per_run(flows)
    stats = statistics(runs)
    flows.to_csv(PROCESSED / "por_fluxo.csv", index=False)
    runs.to_csv(PROCESSED / "por_execucao.csv", index=False, float_format="%.6f")
    stats.to_csv(PROCESSED / "estatisticas.csv", index=False, float_format="%.6f")

    base_stats = stats[stats.nodes == args.base_nodes]
    n = args.base_nodes

    print("Gráficos")
    fig_metric_vs_speed(stats, "pdrPct", "fig1_pdr_x_velocidade", n, args.runs)
    fig_metric_vs_speed(stats, "throughputMbps", "fig2_throughput_x_velocidade", n, args.runs)
    fig_metric_vs_speed(stats, "delayMs", "fig3_delay_x_velocidade", n, args.runs)
    fig_metric_vs_speed(stats, "jitterMs", "fig4_jitter_x_velocidade", n, args.runs)
    fig_compare(runs, stats, args.compare_speed, n, f"fig5_comparativo_v{args.compare_speed:g}")
    fig_panel(base_stats, "speed", "Velocidade dos nós (m/s)", "painel_base",
              f"Experimento-base: {n} nós, média de {args.runs} execuções, IC 95%")
    fig_metric_vs_speed(stats, "ctrlKbps", "apoio_controle_x_velocidade", n, args.runs)
    fig_metric_vs_speed(stats, "avgHops", "apoio_saltos_x_velocidade", n, args.runs)

    summary = ["# Resumo estatístico", "",
               "Cada célula: média ± IC 95% (dp = desvio-padrão amostral; mínimo a máximo) "
               f"sobre {args.runs} execuções.", "",
               f"## Etapa 1: experimento-base ({n} nós), por velocidade (m/s)", ""]
    summary += markdown_table(base_stats, "speed", "Velocidade (m/s)")

    if not ext.empty:
        ext_stats = stats[stats.speed == args.ext_speed]
        fig_panel(ext_stats, "nodes", "Quantidade de nós", f"fig6_extensao_nos_v{args.ext_speed:g}",
                  f"Variável adicional: quantidade de nós a {args.ext_speed:g} m/s, "
                  f"média de {args.runs} execuções, IC 95%")
        fig_ext_pdr_by_nodes(stats, "fig7_extensao_pdr_x_velocidade")
        summary += [f"## Etapa 2: quantidade de nós, a {args.ext_speed:g} m/s", ""]
        summary += markdown_table(ext_stats, "nodes", "Nós")
        for speed in sorted(stats.speed.unique()):
            if speed != args.ext_speed:
                summary += [f"## Etapa 2: quantidade de nós, a {speed:g} m/s", ""]
                summary += markdown_table(stats[stats.speed == speed], "nodes", "Nós")

    arp = load_stage("apoio_arp_padrao")
    if not arp.empty:
        arp_stats = statistics(per_run(arp))
        summary += ["## Apoio: efeito do ajuste do ARP no PDR (%)", "",
                    "Etapa 1 repetida com o tempo de bloqueio padrão do ARP (100 s). "
                    "Cada célula: média ± IC 95%.", "",
                    "| Velocidade (m/s) | Protocolo | ARP 1 s (adotado) | ARP 100 s (padrão) | Diferença |",
                    "|---|---|---|---|---|"]
        a = base_stats[base_stats.metric == "pdrPct"]
        b = arp_stats[arp_stats.metric == "pdrPct"]
        for speed in sorted(a.speed.unique()):
            for protocol in PROTOCOLS:
                ra = a[(a.speed == speed) & (a.protocol == protocol)].iloc[0]
                rb = b[(b.speed == speed) & (b.protocol == protocol)].iloc[0]
                summary.append(f"| {speed:g} | {protocol} | {ra['mean']:.1f} ± {ra['ci95']:.1f} | "
                               f"{rb['mean']:.1f} ± {rb['ci95']:.1f} | {ra['mean'] - rb['mean']:+.1f} |")
        summary.append("")
        arp_stats.to_csv(PROCESSED / "apoio_arp_padrao_estatisticas.csv", index=False, float_format="%.6f")

    if ARTICLE.is_dir():
        print("Artefatos do artigo")
        article_outputs(runs, stats, args)

    (PROCESSED / "resumo.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("Tabelas em data/processed/ (por_fluxo.csv, por_execucao.csv, estatisticas.csv, resumo.md)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

import os
import csv
import numpy as np
import matplotlib.pyplot as plt
import sys

# ==============================================================================
# CONFIGURACOES DE DIRETORIO
# ==============================================================================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.config_loader import OPTIMIZED_RESULTS_DIR

DIR_BASE = OPTIMIZED_RESULTS_DIR
DIR_CSV = os.path.join(DIR_BASE, "csv")
DIR_OUT = os.path.join(DIR_BASE, "graficos")

# ==============================================================================
# CONFIGURACOES DE DESIGN
# ==============================================================================
# Paleta de 5 cores solidas distintas e classicas (Vermelho, Laranja, Azul, Roxo, Verde)
CORES_NIVEIS = ['#D32F2F', '#F57C00', '#1976D2', '#7B1FA2', '#388E3C']
NIVEIS = ["N0", "N1", "N2", "N3", "N4"]

FONTE_GERAL = 14
FONTE_EIXOS = 14
FONTE_LEGENDA = 12
FONTE_TEXTO_BARRAS = 10  # Reduzido para evitar sobreposicao

plt.rcParams.update({
    'font.weight': 'bold',
    'axes.labelweight': 'bold',
    'axes.titleweight': 'bold',
    'font.size': FONTE_GERAL,
    'axes.labelsize': FONTE_EIXOS,
    'xtick.labelsize': FONTE_EIXOS,
    'ytick.labelsize': FONTE_EIXOS,
    'legend.fontsize': FONTE_LEGENDA
})

def formatar_k_m(val_bruto):
    if val_bruto >= 1000000:
        return f"{val_bruto/1000000:.1f}M"
    elif val_bruto >= 1000:
        return f"{val_bruto/1000:.1f}K"
    elif val_bruto > 0:
        return f"{int(val_bruto)}"
    else:
        return "0"

def salvar_grafico(fig, nome):
    os.makedirs(DIR_OUT, exist_ok=True)
    caminho = os.path.join(DIR_OUT, f"{nome}.png")
    fig.savefig(caminho, dpi=400, bbox_inches='tight')
    plt.close(fig)
    print(f"  -> {caminho}")

def ler_csv(caminho):
    if not os.path.exists(caminho):
        return None
    with open(caminho, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def organizar_dados(dados_brutos):
    casos = []
    dados_por_nivel = {n: {"tempos": [], "docs": [], "speedup": []} for n in NIVEIS}
    
    for row in dados_brutos:
        caso = row["Caso de Uso"]
        if caso not in casos:
            casos.append(caso)
        
        n = row["Nivel"]
        dados_por_nivel[n]["tempos"].append(float(row["Tempo Medio (ms)"]))
        dados_por_nivel[n]["docs"].append(float(row["Docs Examinados"]))
        dados_por_nivel[n]["speedup"].append(float(row["Speedup"]))
        
    return casos, dados_por_nivel

def plotar_tempos(casos, dados_por_nivel):
    x = np.arange(len(casos))
    w = 0.15

    fig, ax = plt.subplots(figsize=(14, 7))
    for i, nivel in enumerate(NIVEIS):
        tempos = [max(v, 0.1) for v in dados_por_nivel[nivel]["tempos"]]
        bars = ax.bar(x + i*w - 2*w, tempos, w, label=nivel, color=CORES_NIVEIS[i], edgecolor='white', linewidth=0.5)
        
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width()/2, h * 1.2,
                    f"{h:.1f}", ha="center", va="bottom", fontsize=FONTE_TEXTO_BARRAS, fontweight="bold", rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(casos, rotation=0)
    ax.set_ylabel("Tempo Médio (ms)")
    ax.set_yscale("log")
    
    max_t = max(max(v) for v in (dados_por_nivel[n]["tempos"] for n in NIVEIS))
    ax.set_ylim(bottom=0.1, top=max_t * 1000) # Espaco dinâmico extra pro topo em escala log
    
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.12), ncol=5)
    salvar_grafico(fig, "01_tempos_otimizacao")

def plotar_docs_examinados(casos, dados_por_nivel):
    x = np.arange(len(casos))
    w = 0.15

    fig, ax = plt.subplots(figsize=(14, 7))
    for i, nivel in enumerate(NIVEIS):
        raw_docs = dados_por_nivel[nivel]["docs"]
        # Usamos log scale, entao valores de 0 nao aparecem. Para contornar, forcamos altura 0.1
        plot_docs = [max(v, 0.1) for v in raw_docs]
        bars = ax.bar(x + i*w - 2*w, plot_docs, w, label=nivel, color=CORES_NIVEIS[i], edgecolor='white', linewidth=0.5)
        
        for j, b in enumerate(bars):
            val = raw_docs[j]
            ax.text(b.get_x() + b.get_width()/2, b.get_height() * 1.2,
                    formatar_k_m(val), ha="center", va="bottom", fontsize=FONTE_TEXTO_BARRAS, fontweight="bold", rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(casos, rotation=0)
    ax.set_ylabel("Documentos Examinados (#)")
    ax.set_yscale("log")
    
    max_d = max(max(v) for v in (dados_por_nivel[n]["docs"] for n in NIVEIS))
    ax.set_ylim(bottom=0.1, top=max(max_d * 1000, 100)) # Espaco extra para milhoes e rotulos rotacionados
    
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.12), ncol=5)
    salvar_grafico(fig, "02_docs_examinados")

def plotar_speedup(casos, dados_por_nivel):
    x = np.arange(len(casos))
    w = 0.15

    fig, ax = plt.subplots(figsize=(14, 7))
    max_sp = 1
    for i, nivel in enumerate(NIVEIS):
        speedup = [max(v, 1.0) for v in dados_por_nivel[nivel]["speedup"]]
        if max(speedup) > max_sp: max_sp = max(speedup)
        bars = ax.bar(x + i*w - 2*w, speedup, w, label=nivel, color=CORES_NIVEIS[i], edgecolor='white', linewidth=0.5)
        
        for b in bars:
            h = b.get_height()
            ax.text(b.get_x() + b.get_width()/2, h * 1.2,
                    f"{h:.1f}x", ha="center", va="bottom", fontsize=FONTE_TEXTO_BARRAS, fontweight="bold", rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(casos, rotation=0)
    ax.set_ylabel("Fator de Aceleração (Vezes mais rápido)")
    ax.set_yscale("log")
    ax.set_ylim(bottom=1, top=max_sp * 500) # Espaco dinâmico para rotacao 90
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.12), ncol=5)
    salvar_grafico(fig, "03_speedup_otimizacao")

def main():
    print("=" * 60)
    print("  PLOTAGEM PADRONIZADA (CASO OTIMIZADO)  ")
    print("=" * 60)

    try:
        dados_brutos = ler_csv(os.path.join(DIR_CSV, "otimizado_resultados.csv"))
        if dados_brutos:
            casos, dados_por_nivel = organizar_dados(dados_brutos)
            plotar_tempos(casos, dados_por_nivel)
            plotar_docs_examinados(casos, dados_por_nivel)
            plotar_speedup(casos, dados_por_nivel)
    except Exception as e:
        print(f"[Aviso] Nao foi possivel plotar graficos otimizados: {e}")
        
    print(f"\n[SUCESSO] Graficos gerados em '{DIR_OUT}'!")

if __name__ == "__main__":
    main()

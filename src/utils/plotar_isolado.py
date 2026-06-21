import os
import csv
import numpy as np
import matplotlib.pyplot as plt
import sys

# ==============================================================================
# CONFIGURACOES DE DIRETORIO
# ==============================================================================
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.config_loader import ISOLATED_RESULTS_DIR

DIR_BASE = ISOLATED_RESULTS_DIR
DIR_CSV = os.path.join(DIR_BASE, "csv")
DIR_OUT = os.path.join(DIR_BASE, "graficos")

# ==============================================================================
# CONFIGURACOES DE DESIGN
# ==============================================================================
ORIENTACAO = "vertical"  

# Limites do Eixo Y para os graficos de TEMPO (Escala Log)
Y_MIN = 0.1
Y_MAX = 1000000

# Paleta de Cores
COR_SEM   = "#D32F2F"
COR_COM   = "#1976D2"
COR_SPEED = "#388E3C"

FONTE_GERAL = 14
FONTE_EIXOS = 14
FONTE_LEGENDA = 14
FONTE_TEXTO_BARRAS = 13

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

import re

def formatar_texto(texto):
    texto = re.sub(r"^Caso \d+\s+", "", texto)
    return texto.replace(" - ", "\n")

def salvar_grafico(fig, nome):
    os.makedirs(DIR_OUT, exist_ok=True)
    caminho = os.path.join(DIR_OUT, f"{nome}.png")
    fig.savefig(caminho, dpi=400, bbox_inches='tight')
    plt.close(fig)
    print(f"  -> {caminho}")

def plotar_comparacao_tempo(df):
    casos = [formatar_texto(c) for c in df["Caso de Uso"]]
    t_sem = [max(v, 0.1) for v in df["Tempo Medio Sem Indice (ms)"]]
    t_com = [max(v, 0.1) for v in df["Tempo Medio Com Indice (ms)"]]

    x = np.arange(len(casos))
    w = 0.35

    fig, ax = plt.subplots(figsize=(14, 7))
    b1 = ax.bar(x - w/2, t_sem, w, label="Sem Índice", color=COR_SEM)
    b2 = ax.bar(x + w/2, t_com, w, label="Com Índice", color=COR_COM)
    
    ax.set_xticks(x)
    ax.set_xticklabels(casos, rotation=0)
    ax.set_ylabel("Tempo Médio (ms)")
    ax.set_yscale("log")
    ax.set_ylim(bottom=Y_MIN, top=Y_MAX)
    
    for b in list(b1) + list(b2):
        h = b.get_height()
        ax.text(b.get_x() + b.get_width()/2, h * 1.5,
                f"{h:.1f}", ha="center", va="bottom", fontsize=FONTE_TEXTO_BARRAS, fontweight="bold")

    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.10), ncol=2)
    salvar_grafico(fig, "01_comparacao_geral_revisada")

def formatar_k_m(val_bruto):
    if val_bruto >= 1000000:
        return f"{val_bruto/1000000:.2f}M"
    elif val_bruto >= 1000:
        return f"{val_bruto/1000:.1f}K"
    elif val_bruto > 0:
        return f"{int(val_bruto)}"
    else:
        return "0.00M"

def plotar_docs_examinados(df):
    casos = [formatar_texto(c) for c in df["Caso de Uso"]]
    raw_sem = [float(v) for v in df["Docs Sem Indice"]]
    raw_com = [float(v) for v in df["Docs Com Indice"]]
    
    d_sem = [v / 1000000.0 for v in raw_sem]
    d_com = [v / 1000000.0 for v in raw_com]

    x = np.arange(len(casos))
    w = 0.35

    fig, ax = plt.subplots(figsize=(14, 7))
    b1 = ax.bar(x - w/2, d_sem, w, label="Sem Índice", color=COR_SEM)
    b2 = ax.bar(x + w/2, d_com, w, label="Com Índice", color=COR_COM)
    
    ax.set_xticks(x)
    ax.set_xticklabels(casos, rotation=0)
    ax.set_ylabel("Milhões de Documentos Examinados (#)")
    
    max_y = max(max(d_sem), max(d_com))
    ax.set_ylim(bottom=0, top=max_y * 1.2 if max_y > 0 else 1)
    
    for i, b in enumerate(b1):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + (max_y*0.02 if max_y > 0 else 0.1),
                formatar_k_m(raw_sem[i]), ha="center", va="bottom", fontsize=FONTE_TEXTO_BARRAS, fontweight="bold")
    for i, b in enumerate(b2):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + (max_y*0.02 if max_y > 0 else 0.1),
                formatar_k_m(raw_com[i]), ha="center", va="bottom", fontsize=FONTE_TEXTO_BARRAS, fontweight="bold")

    ax.legend(loc='upper center', bbox_to_anchor=(0.5, 1.10), ncol=2)
    salvar_grafico(fig, "02_docs_examinados_revisado")

def plotar_speedup(df):
    casos = [formatar_texto(c) for c in df["Caso de Uso"]]
    speedup = [max(v, 1.0) for v in df["Speedup"]]

    x = np.arange(len(casos))
    
    fig, ax = plt.subplots(figsize=(14, 7))
    bars = ax.bar(x, speedup, color=COR_SPEED)
    ax.set_xticks(x)
    ax.set_xticklabels(casos, rotation=0)
    ax.set_ylabel("Fator de Aceleração (Vezes mais rápido)")
    
    ax.set_yscale("log")
    ax.set_ylim(bottom=1, top=max(speedup) * 5)
    
    for b in bars:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width()/2, h * 1.5,
                f"{h:.1f}x", ha="center", va="bottom", fontsize=FONTE_TEXTO_BARRAS, fontweight="bold")

    salvar_grafico(fig, "03_speedup_revisado")

def plotar_escrita_armazenamento(df):
    if df.get("empty", True): return
    
    cenarios = df["Cenario"]
    tam_idx = df["Tamanho dos Indices (MB)"]
    t_ins = [max(v, 0.1) for v in df["Tempo Medio de Insercao (ms)"]]

    x = np.arange(len(cenarios))
    cores = [COR_SEM, COR_COM]

    fig1, ax1 = plt.subplots(figsize=(8, 6))
    max_tam = max(tam_idx) if max(tam_idx) > 0 else 1
    bars1 = ax1.bar(x, tam_idx, color=cores)
    ax1.set_xticks(x)
    ax1.set_xticklabels(cenarios, rotation=0)
    ax1.set_ylabel("Espaço Ocupado (MB)")
    ax1.set_ylim(bottom=0, top=max_tam * 1.2)
    for b in bars1:
        ax1.text(b.get_x() + b.get_width()/2, b.get_height() + max_tam*0.02,
                f"{b.get_height():.1f} MB", ha="center", va="bottom", fontsize=FONTE_TEXTO_BARRAS, fontweight="bold")
            
    salvar_grafico(fig1, "04_overhead_armazenamento_revisado")

    fig2, ax2 = plt.subplots(figsize=(8, 6))
    max_ins = max(t_ins) if max(t_ins) > 0 else 1
    bars2 = ax2.bar(x, t_ins, color=cores)
    ax2.set_xticks(x)
    ax2.set_xticklabels(cenarios, rotation=0)
    ax2.set_ylabel("Tempo Médio (ms)")
    ax2.set_yscale("log")
    ax2.set_ylim(bottom=Y_MIN, top=max_ins * 10)
    for b in bars2:
        h = b.get_height()
        ax2.text(b.get_x() + b.get_width()/2, h * 1.5,
                f"{h:.1f} ms", ha="center", va="bottom", fontsize=FONTE_TEXTO_BARRAS, fontweight="bold")

    salvar_grafico(fig2, "05_penalidade_escrita_revisada")

def ler_csv(caminho):
    if not os.path.exists(caminho):
        return None
    with open(caminho, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)

def main():
    print("=" * 60)
    print("  PLOTAGEM PADRONIZADA (CASO ISOLADO)  ")
    print("=" * 60)

    try:
        dados_agregados = ler_csv(os.path.join(DIR_CSV, "consultas_agregado.csv"))
        if dados_agregados:
            df_agregado = {
                "Caso de Uso": [row["Caso de Uso"] for row in dados_agregados],
                "Tempo Medio Sem Indice (ms)": [float(row["Tempo Medio Sem Indice (ms)"]) for row in dados_agregados],
                "Tempo Medio Com Indice (ms)": [float(row["Tempo Medio Com Indice (ms)"]) for row in dados_agregados],
                "Docs Sem Indice": [float(row["Docs Sem Indice"]) for row in dados_agregados],
                "Docs Com Indice": [float(row["Docs Com Indice"]) for row in dados_agregados],
                "Speedup": [float(row["Speedup"]) for row in dados_agregados]
            }
            plotar_comparacao_tempo(df_agregado)
            plotar_docs_examinados(df_agregado)
            plotar_speedup(df_agregado)
    except Exception as e:
        print(f"[Aviso] Nao foi possivel plotar consultas: {e}")

    try:
        dados_escrita = ler_csv(os.path.join(DIR_CSV, "escrita_armazenamento.csv"))
        if dados_escrita:
            df_escrita = {
                "Cenario": [row["Cenario"] for row in dados_escrita],
                "Tamanho dos Indices (MB)": [float(row["Tamanho dos Indices (MB)"]) for row in dados_escrita],
                "Tempo Medio de Insercao (ms)": [float(row["Tempo Medio de Insercao (ms)"]) for row in dados_escrita],
                "empty": False
            }
            plotar_escrita_armazenamento(df_escrita)
    except Exception as e:
        print(f"[Aviso] Nao foi possivel plotar escrita: {e}")
        
    print(f"\n[SUCESSO] Graficos gerados em '{DIR_OUT}'!")

if __name__ == "__main__":
    main()

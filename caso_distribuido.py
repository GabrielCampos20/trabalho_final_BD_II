import json
import os
import time
import random
from datetime import datetime
import csv
import numpy as np
import matplotlib.pyplot as plt
from pymongo import MongoClient, ASCENDING
from faker import Faker
from tqdm import tqdm

CFG = json.load(open("config.json", "r", encoding="utf-8"))
MONGO_URI  = CFG["mongodb"]["uri"]  # Deve apontar para localhost:27017 (mongos)
DB_NAME    = CFG["mongodb"]["database"]
COL_NAME   = CFG["mongodb"]["collection"]

BYTES_POR_DOC = 400
TAMANHO_GB    = CFG["dataset"]["tamanho_gb"]
TAMANHO       = int((TAMANHO_GB * 1024 ** 3) / BYTES_POR_DOC)
BATCH_SIZE    = CFG["dataset"]["batch_size"]

REPETICOES = CFG["experimentos"]["repeticoes"]
OUTPUT_DIR = CFG["graficos"]["output_dir"]
DPI        = CFG["graficos"]["dpi"]
FORMATO    = CFG["graficos"]["formato"]

SEED       = CFG["experimentos"].get("seed", 42)
FILTROS    = CFG["experimentos"].get("filtros", {"modo": "automatico"})

random.seed(SEED)
np.random.seed(SEED)
fake = Faker(CFG["dataset"]["locale"])
Faker.seed(SEED)

ESTADOS    = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "CE", "PE", "AM", "AC"]

# Cores para o Sharding
COR_TARGET  = "#1976D2" # Azul (Targeted)
COR_SCATTER = "#D32F2F" # Vermelho (Scatter-Gather)

def log_header(texto):
    print(f"\n{'='*60}\n{texto}\n{'='*60}")

def resumo_estatistico(lista_tempos):
    arr = np.array(lista_tempos)
    return {
        "media": round(np.mean(arr), 3),
        "std": round(np.std(arr), 3),
        "min": round(np.min(arr), 3),
        "max": round(np.max(arr), 3)
    }

def popular_banco(col):
    log_header("GERACAO DE DADOS FALSOS (SHARDING)")
    inseridos = 0
    with tqdm(total=TAMANHO, desc="Inserindo", unit="docs") as barra:
        while inseridos < TAMANHO:
            lote = []
            para_inserir = min(BATCH_SIZE, TAMANHO - inseridos)
            for _ in range(para_inserir):
                lote.append({
                    "nome": fake.name(),
                    "email": fake.email(),
                    "estado": random.choice(ESTADOS),
                    "salario": round(random.uniform(1000.0, 25000.0), 2),
                    "ativo": fake.boolean(chance_of_getting_true=80),
                    "criado_em": fake.date_time_between(start_date="-5y", end_date="now"),
                    "profissao": fake.job(),
                    "bio": fake.text(max_nb_chars=150)
                })
            col.insert_many(lote)
            inseridos += para_inserir
            barra.update(para_inserir)

def explain_query(col, filtro, tag):
    dir_explains = os.path.join(OUTPUT_DIR, "explains")
    os.makedirs(dir_explains, exist_ok=True)
    exp = col.find(filtro).explain()
    caminho = os.path.join(dir_explains, f"{tag}.json")
    with open(caminho, "w") as f:
        json.dump(exp, f, indent=2, default=str)
    
    # Extraindo metadados relevantes para Sharding do plano
    # Em um cluster, o plan eh envelopado em "shards"
    shards_envolvidos = exp.get("queryPlanner", {}).get("winningPlan", {}).get("shards", [])
    num_shards = len(shards_envolvidos) if shards_envolvidos else 1
    
    # Contagem de docs no sharding eh a soma dos shards
    docs = 0
    exec_stats = exp.get("executionStats", {})
    if "executionStages" in exec_stats and "shards" in exec_stats["executionStages"]:
        for s in exec_stats["executionStages"]["shards"]:
            docs += s.get("executionStages", {}).get("totalDocsExamined", 0)
    else:
        docs = exec_stats.get("totalDocsExamined", 0)
    
    return {"num_shards": num_shards, "totalDocsExamined": docs, "raw": exp}

def medir_query(col, filtro, barra=None):
    tempos = []
    for _ in range(REPETICOES):
        t0 = time.perf_counter()
        list(col.find(filtro))
        tf = time.perf_counter()
        tempos.append((tf - t0) * 1000)
        if barra: barra.update(1)
    return tempos

def teste_distribuido_estado_vs_salario(col, barra):
    log_header("Cenario: Busca Direcionada (Estado) vs Scatter-Gather (Salario)")
    
    # Busca Direcionada (Usa Shard Key: estado)
    if FILTROS["modo"] == "manual":
        est = FILTROS["manual"]["estado"]
    else:
        est = random.choice(ESTADOS)
    
    filtro_targeted = {"estado": est}
    print(f"  [Targeted] Filtro: estado = {est}")
    
    tempos_targeted = medir_query(col, filtro_targeted, barra)
    exp_targeted = explain_query(col, filtro_targeted, "sharding_targeted")
    
    # Busca Scatter-Gather (Ignora Shard Key, busca salario)
    if FILTROS["modo"] == "manual":
        smin, smax = FILTROS["manual"]["salario_min"], FILTROS["manual"]["salario_max"]
    else:
        smin, smax = 5000, 10000
    
    filtro_scatter = {"salario": {"$gte": smin, "$lte": smax}}
    print(f"  [Scatter-Gather] Filtro: salario entre {smin} e {smax}")
    
    tempos_scatter = medir_query(col, filtro_scatter, barra)
    exp_scatter = explain_query(col, filtro_scatter, "sharding_scatter")
    
    for nome, ts, ex in [("Targeted", tempos_targeted, exp_targeted), ("Scatter-Gather", tempos_scatter, exp_scatter)]:
        est_res = resumo_estatistico(ts)
        print(f"\n  [{nome}]")
        print(f"    Shards Atingidos: {ex['num_shards']}")
        print(f"    Tempo medio:      {est_res['media']} ms")
        print(f"    Desvio padrao:    {est_res['std']} ms")
        
    return {
        "targeted": tempos_targeted,
        "scatter": tempos_scatter,
        "exp_targeted": exp_targeted,
        "exp_scatter": exp_scatter
    }

def grafico_sharding(resultados):
    os.makedirs(os.path.join(OUTPUT_DIR, "graficos"), exist_ok=True)
    dados = resultados["Estado vs Salario"]
    
    fig, ax = plt.subplots(figsize=(8, 6))
    
    medias = [
        resumo_estatistico(dados["targeted"])["media"],
        resumo_estatistico(dados["scatter"])["media"]
    ]
    erros = [
        resumo_estatistico(dados["targeted"])["std"],
        resumo_estatistico(dados["scatter"])["std"]
    ]
    
    bars = ax.bar(["Consulta Direcionada\n(Usa Shard Key)", "Scatter-Gather\n(Ignora Shard Key)"],
                  medias, yerr=erros, color=[COR_TARGET, COR_SCATTER], capsize=5, width=0.5)
                  
    for b in bars:
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 5,
                f"{b.get_height():.1f} ms", ha="center", va="bottom", fontsize=11, fontweight="bold")
                
    ax.set_ylabel("Tempo de Execucao (ms)", fontsize=12)
    ax.set_title("Desempenho em Rede: Roteamento Mongos", fontsize=14)
    plt.tight_layout()
    caminho = os.path.join(OUTPUT_DIR, "graficos", f"08_sharding_routing.{FORMATO}")
    fig.savefig(caminho, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {caminho}")

def main():
    print("=== BD2 - Experimentos Mongo Sharded Cluster ===")
    client = MongoClient(MONGO_URI)
    
    # Testar se eh um sharded cluster
    is_sharded = client.admin.command('ismaster').get('msg') == 'isdbgrid'
    if not is_sharded:
        print("\n[AVISO CRITICO] O MongoDB conectado NAO eh um Sharded Cluster (mongos).")
        print("Certifique-se de que o Docker Compose esta rodando e que o scripts/init-cluster.sh foi executado.")
        print("Sera executado como standalone, o que invalidara os testes de rede.\n")
    
    db = client[DB_NAME]
    col = db[COL_NAME]

    if col.count_documents({}) < TAMANHO:
        popular_banco(col)
        # Vamos criar os indices em ambas as chaves para que a unica diferenca seja o Roteamento de Rede
        print("[Info] Criando indices base para isolar a variavel 'Rede'...")
        col.create_index([("estado", ASCENDING)])
        col.create_index([("salario", ASCENDING)])
    else:
        log_header(f"[Dataset] Collection ja possui {col.count_documents({}):,} documentos. Pulando insercao.")

    resultados = {}
    
    total_iteracoes = REPETICOES * 2
    
    with tqdm(total=total_iteracoes, desc="Progresso Sharding", unit="qry") as barra:
        resultados["Estado vs Salario"] = teste_distribuido_estado_vs_salario(col, barra)

    print("\n[Info] Gerando graficos de Sharding...")
    grafico_sharding(resultados)
    
    print("\n[Info] Excluindo banco de dados distribuido para liberar espaco...")
    client.drop_database(DB_NAME)
    print("=== Experimentos concluidos ===\n")
    client.close()

if __name__ == "__main__":
    main()
import json
import os
import time
import random
from datetime import datetime
import multiprocessing as mp
from functools import partial

import numpy as np
import matplotlib.pyplot as plt
from pymongo import MongoClient, ASCENDING
from tqdm import tqdm

import sys
# Adiciona a raiz do projeto ao path para importar modulos do src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.config_loader import config as CFG, PROJECT_ROOT, OPTIMIZED_RESULTS_DIR

# Importando helpers genericos de caso_isolado
from src.experimentos.caso_isolado import popular_banco, ESTADOS, PROFISSOES, DATA_INICIO, DATA_FIM, SAL_MIN, SAL_MAX

MONGO_URI  = CFG["mongodb"]["uri"]
DB_NAME    = CFG["mongodb"]["database"]
COL_NAME   = CFG["mongodb"]["collection"]

REPETICOES = CFG["experimentos"]["repeticoes"]
OUTPUT_DIR = OPTIMIZED_RESULTS_DIR

SEED       = CFG["experimentos"].get("seed", 42)
FILTROS    = CFG["experimentos"].get("filtros", {"modo": "automatico"})

random.seed(SEED)

def log_header(titulo):
    print("\n" + "=" * 60)
    print(titulo.center(60))
    print("=" * 60)

def log(msg=""):
    print(msg)

# -- Utilitarios Otimizados ------------------------------------------------------

def remover_indices(col):
    for idx in list(col.index_information().keys()):
        if idx != "_id_":
            try:
                col.drop_index(idx)
            except:
                pass

def medir_query(col, filtro, projecao=None, hint_idx=None, repeticoes=REPETICOES, barra=None):
    # Warm-up
    list(col.find(filtro, projecao).hint(hint_idx).limit(100))
    
    tempos = []
    for _ in range(repeticoes):
        inicio = time.perf_counter()
        # count_documents ignora projecao na RAM e nao faz fetch de fato em muitos casos,
        # para forçar o FETCH e avaliar a Otimização de Covered Query, 
        # devemos forçar o motor a materializar os documentos na RAM!
        # Por isso usamos find e materializamos com list() - limitando p/ nao estourar a RAM
        list(col.find(filtro, projecao).hint(hint_idx).limit(5000))
        tempos.append((time.perf_counter() - inicio) * 1000)
        if barra:
            barra.update(1)
    return tempos

def _extract_stages(stage):
    stages = [stage.get('stage', 'UNKNOWN')]
    if 'inputStage' in stage:
        stages.extend(_extract_stages(stage['inputStage']))
    elif 'inputStages' in stage:
        for s in stage['inputStages']:
            stages.extend(_extract_stages(s))
    return stages

def explain_query(col, filtro, projecao, hint_idx, nome_caso, nivel):
    # explain() em PyMongo Cursor retorna o dicionario
    cursor = col.find(filtro, projecao).limit(5000)
    if hint_idx:
        cursor = cursor.hint(hint_idx)
    resultado = cursor.explain()
    
    dir_explains = os.path.join(OUTPUT_DIR, "explains")
    os.makedirs(dir_explains, exist_ok=True)
    arquivo_json = os.path.join(dir_explains, f"{nome_caso}_{nivel}.json")
    with open(arquivo_json, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=4, default=str)
        
    stats = resultado.get("executionStats", {})
    winning_plan = resultado.get("queryPlanner", {}).get("winningPlan", {})
    
    stages_tree = _extract_stages(winning_plan)
    
    # Resumo descritivo dos stages principais
    stages_resumo = []
    if "COLLSCAN" in stages_tree: stages_resumo.append("COLLSCAN")
    if "IXSCAN" in stages_tree: stages_resumo.append("IXSCAN")
    if "FETCH" in stages_tree: stages_resumo.append("FETCH")
    if "PROJECTION_SIMPLE" in stages_tree or "PROJECTION_COVERED" in stages_tree or "PROJECTION" in stages_tree: 
        stages_resumo.append("PROJ")
        
    return {
        "stages":              " -> ".join(stages_resumo) if stages_resumo else "N/A",
        "executionTimeMillis": stats.get("executionTimeMillis", 0),
        "totalDocsExamined":   stats.get("totalDocsExamined", 0),
        "totalKeysExamined":   stats.get("totalKeysExamined", 0),
    }

def imprimir_resultado(label, tempos, explain, log=print):
    media = round(np.mean(tempos), 3)
    log(f"  [{label}]")
    log(f"    Stages:            {explain['stages']}")
    log(f"    Docs examinados:   {explain['totalDocsExamined']:,}")
    log(f"    Chaves examinadas: {explain['totalKeysExamined']:,}")
    log(f"    Tempo medio (Py):  {media} ms")

def rodar_niveis_otimizacao(col, caso_nome, filtro, proj_campos, idx_simples, idx_composto, barra):
    remover_indices(col)
    resultados_niveis = {}
    
    # N0: COLLSCAN Completo
    tempos = medir_query(col, filtro, projecao=None, hint_idx=None, barra=barra)
    exp = explain_query(col, filtro, None, None, caso_nome, "N0")
    imprimir_resultado("N0: COLLSCAN + Doc Completo", tempos, exp, log)
    resultados_niveis["N0"] = {"tempos": tempos, "explain": exp}
    
    # N1: COLLSCAN com Projeção RAM
    projecao = {"_id": 0}
    for c in proj_campos: projecao[c] = 1
    
    tempos = medir_query(col, filtro, projecao=projecao, hint_idx=None, barra=barra)
    exp = explain_query(col, filtro, projecao, None, caso_nome, "N1")
    imprimir_resultado("N1: COLLSCAN + Projecao (RAM)", tempos, exp, log)
    resultados_niveis["N1"] = {"tempos": tempos, "explain": exp}
    
    # N2: IXSCAN (Indice Simples) s/ Projecao
    col.create_index(idx_simples)
    tempos = medir_query(col, filtro, projecao=None, hint_idx=None, barra=barra)
    exp = explain_query(col, filtro, None, None, caso_nome, "N2")
    imprimir_resultado("N2: IXSCAN (Simples) + FETCH", tempos, exp, log)
    resultados_niveis["N2"] = {"tempos": tempos, "explain": exp}
    
    # N3: IXSCAN + Projecao RAM
    tempos = medir_query(col, filtro, projecao=projecao, hint_idx=None, barra=barra)
    exp = explain_query(col, filtro, projecao, None, caso_nome, "N3")
    imprimir_resultado("N3: IXSCAN + FETCH + Projecao", tempos, exp, log)
    resultados_niveis["N3"] = {"tempos": tempos, "explain": exp}
    
    # N4: COVERED QUERY (Indice Composto + Hint)
    remover_indices(col)
    nome_indice = col.create_index(idx_composto)
    tempos = medir_query(col, filtro, projecao=projecao, hint_idx=nome_indice, barra=barra)
    exp = explain_query(col, filtro, projecao, nome_indice, caso_nome, "N4")
    imprimir_resultado("N4: COVERED QUERY (IXSCAN Puro)", tempos, exp, log)
    resultados_niveis["N4"] = {"tempos": tempos, "explain": exp}
    
    remover_indices(col)
    return resultados_niveis

# -- Execucao dos Casos ----------------------------------------------------------

def otimizar_caso_1(col, barra):
    log_header("CASO 1: Busca Exata (Estado)")
    estado = FILTROS["manual"]["estado"] if FILTROS.get("modo") == "manual" else random.choice(ESTADOS)
    filtro = {"estado": estado}
    proj_campos = ["nome", "email"]
    idx_simples = [("estado", ASCENDING)]
    idx_composto = [("estado", ASCENDING), ("nome", ASCENDING), ("email", ASCENDING)]
    log(f"Filtro: {filtro}\nProjetar: {proj_campos}\n")
    return rodar_niveis_otimizacao(col, "Caso1", filtro, proj_campos, idx_simples, idx_composto, barra)

def otimizar_caso_2(col, barra):
    log_header("CASO 2: Faixa Numérica (Salario)")
    if FILTROS.get("modo") == "manual":
        f_min, f_max = FILTROS["manual"]["salario_min"], FILTROS["manual"]["salario_max"]
    else:
        f_min = round(random.uniform(SAL_MIN, (SAL_MIN + SAL_MAX) / 2), 2)
        f_max = round(random.uniform((SAL_MIN + SAL_MAX) / 2, SAL_MAX), 2)
    filtro = {"salario": {"$gte": f_min, "$lte": f_max}}
    proj_campos = ["nome", "salario", "profissao"]
    idx_simples = [("salario", ASCENDING)]
    idx_composto = [("salario", ASCENDING), ("nome", ASCENDING), ("profissao", ASCENDING)]
    log(f"Filtro: {filtro}\nProjetar: {proj_campos}\n")
    return rodar_niveis_otimizacao(col, "Caso2", filtro, proj_campos, idx_simples, idx_composto, barra)

def otimizar_caso_3(col, barra):
    log_header("CASO 3: Datas e Ordenação")
    # Para o cursor explain() de sort, teríamos que adaptar a função de medir query.
    # Mas como o prompt pede "Busca por data + retorno", vamos testar a query range com projeçao.
    ano = FILTROS["manual"]["ano"] if FILTROS.get("modo") == "manual" else 2015
    filtro = {"criado_em": {"$gte": datetime(ano, 1, 1), "$lte": datetime(ano, 12, 31)}}
    proj_campos = ["nome", "criado_em"]
    idx_simples = [("criado_em", ASCENDING)]
    idx_composto = [("criado_em", ASCENDING), ("nome", ASCENDING)]
    log(f"Filtro: {filtro}\nProjetar: {proj_campos}\n")
    return rodar_niveis_otimizacao(col, "Caso3", filtro, proj_campos, idx_simples, idx_composto, barra)

# -- Geracao de Dados CSV e Plotagem ---------------------------------------------

def exportar_csv(resultados):
    import csv
    dir_csv = os.path.join(OUTPUT_DIR, "csv")
    os.makedirs(dir_csv, exist_ok=True)
    
    arquivo_csv = os.path.join(dir_csv, "otimizado_resultados.csv")
    niveis = ["N0", "N1", "N2", "N3", "N4"]
    
    with open(arquivo_csv, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Caso de Uso", "Nivel", "Tempo Medio (ms)", "Docs Examinados", "Chaves Examinadas", "Speedup"])
        
        for caso, dados in resultados.items():
            caso_limpo = caso.replace("_", " ")
            t0 = np.mean(dados["N0"]["tempos"])
            for nivel in niveis:
                t_medio = np.mean(dados[nivel]["tempos"])
                docs = dados[nivel]["explain"]["totalDocsExamined"]
                keys = dados[nivel]["explain"]["totalKeysExamined"]
                speedup = round(t0 / max(t_medio, 0.001), 2)
                writer.writerow([caso_limpo, nivel, round(t_medio, 3), docs, keys, speedup])
                
    print(f"\n[SUCESSO] Dados brutos exportados para {arquivo_csv}")

def gerar_todos_graficos(resultados):
    import subprocess
    exportar_csv(resultados)

    log_header("GERANDO GRAFICOS PADRONIZADOS VIA PLOTAR_OTIMIZADO.PY")
    try:
        script_graficos = os.path.join(PROJECT_ROOT, "src", "utils", "plotar_otimizado.py")
        subprocess.run([sys.executable, script_graficos], check=True)
        print("\n[SUCESSO] Graficos gerados na pasta 'results/optimized/graficos'.")
    except Exception as e:
        print(f"\n[ERRO] Falha ao executar plotar_otimizado.py: {e}")


def main():
    print("Conectando ao MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]
    col = db[COL_NAME]

    # Prepara o banco via multiprocessamento se estiver incompleto
    from src.experimentos.caso_isolado import TAMANHO
    docs_atuais = col.count_documents({})
    if docs_atuais < TAMANHO:
        print(f"[Setup] Banco vazio ou incompleto ({docs_atuais}/{TAMANHO}). Iniciando carga de dados...")
        popular_banco(col, db)
    else:
        print(f"[Setup] Banco pre-existente detectado ({docs_atuais} docs). Aproveitando massa de dados.")

    total_ops = 3 * 5 * REPETICOES
    resultados = {}

    with tqdm(total=total_ops, desc="Benchmarking (Otimizado)", unit="op") as barra:
        resultados["Busca_Estado"] = otimizar_caso_1(col, barra)
        resultados["Faixa_Salario"] = otimizar_caso_2(col, barra)
        resultados["Filtro_Datas"] = otimizar_caso_3(col, barra)

    remover_indices(col)
    gerar_todos_graficos(resultados)

if __name__ == "__main__":
    main()

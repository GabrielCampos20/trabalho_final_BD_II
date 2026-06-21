import json
import os
import time
import random
from datetime import datetime, timedelta
import multiprocessing as mp
from functools import partial

import csv
import numpy as np
import matplotlib.pyplot as plt
from pymongo import MongoClient, ASCENDING, TEXT
from faker import Faker
from tqdm import tqdm

# -- Configuracao ----------------------------------------------------------------
import faker
import sys

# Adiciona a raiz do projeto ao path para importar modulos do src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.config_loader import config as CFG, PROJECT_ROOT, RESULTS_DIR

fake = faker.Faker('pt_BR')
Faker.seed(42)

MONGO_URI  = CFG["mongodb"]["uri"]
DB_NAME    = CFG["mongodb"]["database"]
COL_NAME   = CFG["mongodb"]["collection"]

BYTES_POR_DOC = 400
TAMANHO_GB    = CFG["dataset"]["tamanho_gb"]
TAMANHO       = int((TAMANHO_GB * 1024 ** 3) / BYTES_POR_DOC)
LOCALE        = CFG["dataset"]["locale"]
BATCH_SIZE    = CFG["dataset"]["batch_size"]

REPETICOES = CFG["experimentos"]["repeticoes"]

OUTPUT_DIR = RESULTS_DIR
DPI        = CFG["graficos"]["dpi"]
FORMATO    = CFG["graficos"]["formato"]

fake = Faker(LOCALE)

SEED       = CFG["experimentos"].get("seed", 42)
FILTROS    = CFG["experimentos"].get("filtros", {"modo": "automatico"})

random.seed(SEED)
np.random.seed(SEED)
Faker.seed(SEED)

SAL_MIN     = round(random.uniform(1000.0, 3000.0), 2)
SAL_MAX     = round(random.uniform(8000.0, 25000.0), 2)
IDADE_MIN   = random.randint(16, 25)
IDADE_MAX   = random.randint(50, 80)
DATA_INICIO = datetime(random.randint(2010, 2016), 1, 1)
DATA_FIM    = datetime(random.randint(2022, 2024), 12, 31)

PROFISSOES = [
    "Desenvolvedor", "Analista", "Gerente", "Designer", "Engenheiro",
    "Professor", "Medico", "Advogado", "Contador", "Enfermeiro",
    "Arquiteto", "Jornalista", "Psicologo", "Administrador", "Vendedor"
]

ESTADOS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO"
]

# -- Geracao de dados Paralela (Mocks + Workers) ---------------------------------

N_MOCKS = 10000
MOCK_NOMES = [fake.name() for _ in range(N_MOCKS)]
MOCK_EMAILS = [fake.email() for _ in range(N_MOCKS)]
MOCK_CIDADES = [fake.city() for _ in range(1000)]
MOCK_BIOS = [fake.text(max_nb_chars=150) for _ in range(1000)]
MOCK_PROFISSOES = [fake.job() for _ in range(200)]
MOCK_DATAS = [fake.date_time_between(start_date="-5y", end_date="now") for _ in range(N_MOCKS)]

def _worker_inserir(batch_index, batch_size, total_batches, uri, db_name, col_name, seed):
    np.random.seed(seed + batch_index)
    import random
    random.seed(seed + batch_index)
    
    client = MongoClient(uri)
    col = client[db_name][col_name]
    
    lote = []
    for _ in range(batch_size):
        lote.append({
            "nome": random.choice(MOCK_NOMES),
            "email": random.choice(MOCK_EMAILS),
            "idade": random.randint(18, 80),
            "cidade": random.choice(MOCK_CIDADES),
            "estado": random.choice(ESTADOS),
            "profissao": random.choice(MOCK_PROFISSOES),
            "salario": round(random.uniform(1000.0, 25000.0), 2),
            "ativo": random.choice([True, False]),
            "criado_em": random.choice(MOCK_DATAS),
            "bio": random.choice(MOCK_BIOS)
        })
    col.insert_many(lote, ordered=False)
    client.close()
    return batch_size

def popular_banco(col, db):
    db_name = db.name
    col_name = col.name
    
    # Criar collection SEM compressao Snappy para gerar peso real
    if col_name not in db.list_collection_names():
        try:
            db.create_collection(col_name, storageEngine={"wiredTiger": {"configString": "block_compressor=none"}})
            print("[Info] Collection criada com Compressao Snappy DESATIVADA.")
        except Exception as e:
            print(f"[Aviso] Nao foi possivel desativar compressao (falta config server ou engine?): {e}")

    batch_s = 50000
    total_batches = (TAMANHO // batch_s) + 1
    
    print(f"\n[Dataset] Alvo de Big Data: {TAMANHO_GB} GB (~{TAMANHO:,} documentos sem compressao)")
    print(f"[Dataset] Iniciando {mp.cpu_count()} Workers em Paralelo...\n")
    
    func = partial(_worker_inserir, batch_size=batch_s, total_batches=total_batches, 
                   uri=MONGO_URI, db_name=db_name, col_name=col_name, seed=SEED)
                   
    inseridos = 0
    with mp.Pool(processes=mp.cpu_count()) as pool:
        with tqdm(total=TAMANHO, desc="Inserindo (Paralelo)", unit="docs") as barra:
            for docs_in_batch in pool.imap_unordered(func, range(total_batches)):
                inseridos += docs_in_batch
                barra.update(docs_in_batch)
                if inseridos >= TAMANHO:
                    break
    print(f"\n[Dataset] {TAMANHO:,} documentos brutos inseridos com sucesso.\n")

def gerar_usuario(): # Preservado para Caso 6
    c_em = random.choice(MOCK_DATAS)
    return {
        "nome": random.choice(MOCK_NOMES),
        "email": random.choice(MOCK_EMAILS),
        "idade": random.randint(18, 80),
        "cidade": random.choice(MOCK_CIDADES),
        "estado": random.choice(ESTADOS),
        "profissao": random.choice(MOCK_PROFISSOES),
        "salario": round(random.uniform(1000.0, 25000.0), 2),
        "ativo": random.choice([True, False]),
        "criado_em": c_em,
        "bio": random.choice(MOCK_BIOS)
    }




# -- Utilitarios -----------------------------------------------------------------

def remover_indices(col):
    for idx in list(col.index_information().keys()):
        if idx != "_id_":
            col.drop_index(idx)

def medir_query(col, filtro, repeticoes=REPETICOES, barra=None):
    # Warm-up de cache (substituindo list() pelo count_documents para salvar RAM)
    col.count_documents(filtro)
    tempos = []
    for _ in range(repeticoes):
        inicio = time.perf_counter()
        col.count_documents(filtro)
        tempos.append((time.perf_counter() - inicio) * 1000)
        if barra:
            barra.update(1)
    return tempos

def explain_query(col, filtro, nome_caso, tipo):
    resultado = col.find(filtro).explain()
    
    dir_explains = os.path.join(OUTPUT_DIR, "explains")
    os.makedirs(dir_explains, exist_ok=True)
    arquivo_json = os.path.join(dir_explains, f"{nome_caso}_{tipo}.json")
    with open(arquivo_json, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=4, default=str)
        
    stats = resultado.get("executionStats", {})
    return {
        "stage":               resultado["queryPlanner"]["winningPlan"].get("stage", "N/A"),
        "executionTimeMillis": stats.get("executionTimeMillis", 0),
        "totalDocsExamined":   stats.get("totalDocsExamined", 0),
        "totalKeysExamined":   stats.get("totalKeysExamined", 0),
    }

def resumo_estatistico(tempos):
    return {
        "media":      round(np.mean(tempos), 3),
        "mediana":    round(np.median(tempos), 3),
        "desvio_pad": round(np.std(tempos), 3),
        "minimo":     round(np.min(tempos), 3),
        "maximo":     round(np.max(tempos), 3),
    }

def imprimir_resultado(label, tempos, explain, log=print):
    est = resumo_estatistico(tempos)
    log(f"  [{label}]")
    log(f"    Stage:             {explain['stage']}")
    log(f"    Docs examinados:   {explain['totalDocsExamined']:,}")
    log(f"    Chaves examinadas: {explain['totalKeysExamined']:,}")
    log(f"    Tempo medio:       {est['media']} ms")
    log(f"    Desvio padrao:     {est['desvio_pad']} ms")
    log(f"    Min / Max:         {est['minimo']} ms / {est['maximo']} ms")

# -- Casos de uso ----------------------------------------------------------------

def caso_1_busca_simples(col, barra=None, log=print):
    log("=" * 60)
    log("CASO 1 - Busca simples por campo unico (estado)")
    log("=" * 60)
    if FILTROS.get("modo") == "manual":
        estado = FILTROS["manual"]["estado"]
    else:
        estado = random.choice(ESTADOS)
    filtro = {"estado": estado}
    log(f"  Filtro: estado = {estado}\n")
    remover_indices(col)

    tempos_sem = medir_query(col, filtro, barra=barra)
    exp_sem    = explain_query(col, filtro, "caso_1", "sem_indice")
    imprimir_resultado("Sem indice", tempos_sem, exp_sem, log)

    col.create_index([("estado", ASCENDING)])
    tempos_com = medir_query(col, filtro, barra=barra)
    exp_com    = explain_query(col, filtro, "caso_1", "com_indice")
    imprimir_resultado("Com indice (single field)", tempos_com, exp_com, log)

    remover_indices(col)
    return {"sem_indice": tempos_sem, "com_indice": tempos_com,
            "exp_sem": exp_sem, "exp_com": exp_com}

def caso_2_filtro_composto(col, barra=None, log=print):
    log("=" * 60)
    log("CASO 2 - Filtro composto (estado + ativo)")
    log("=" * 60)
    if FILTROS.get("modo") == "manual":
        estado = FILTROS["manual"]["estado"]
        ativo = FILTROS["manual"]["ativo"]
    else:
        estado = random.choice(ESTADOS)
        ativo  = random.choice([True, False])
    filtro = {"estado": estado, "ativo": ativo}
    log(f"  Filtro: estado = {estado}, ativo = {ativo}\n")
    remover_indices(col)

    tempos_sem = medir_query(col, filtro, barra=barra)
    exp_sem    = explain_query(col, filtro, "caso_1", "sem_indice")
    imprimir_resultado("Sem indice", tempos_sem, exp_sem, log)

    col.create_index([("estado", ASCENDING), ("ativo", ASCENDING)])
    tempos_com = medir_query(col, filtro, barra=barra)
    exp_com    = explain_query(col, filtro, "caso_1", "com_indice")
    imprimir_resultado("Com indice composto", tempos_com, exp_com, log)

    remover_indices(col)
    return {"sem_indice": tempos_sem, "com_indice": tempos_com,
            "exp_sem": exp_sem, "exp_com": exp_com}

def caso_3_faixa_numerica(col, barra=None, log=print):
    log("=" * 60)
    log("CASO 3 - Busca por faixa numerica (salario)")
    log("=" * 60)
    if FILTROS.get("modo") == "manual":
        faixa_min = FILTROS["manual"]["salario_min"]
        faixa_max = FILTROS["manual"]["salario_max"]
    else:
        faixa_min = round(random.uniform(SAL_MIN, (SAL_MIN + SAL_MAX) / 2), 2)
        faixa_max = round(random.uniform((SAL_MIN + SAL_MAX) / 2, SAL_MAX), 2)
    filtro = {"salario": {"$gte": faixa_min, "$lte": faixa_max}}
    log(f"  Filtro: salario entre R$ {faixa_min:,.2f} e R$ {faixa_max:,.2f}\n")
    remover_indices(col)

    tempos_sem = medir_query(col, filtro, barra=barra)
    exp_sem    = explain_query(col, filtro, "caso_1", "sem_indice")
    imprimir_resultado("Sem indice", tempos_sem, exp_sem, log)

    col.create_index([("salario", ASCENDING)])
    tempos_com = medir_query(col, filtro, barra=barra)
    exp_com    = explain_query(col, filtro, "caso_1", "com_indice")
    imprimir_resultado("Com indice (range)", tempos_com, exp_com, log)

    remover_indices(col)
    return {"sem_indice": tempos_sem, "com_indice": tempos_com,
            "exp_sem": exp_sem, "exp_com": exp_com}

def caso_4_intervalo_datas(col, barra=None, log=print):
    log("=" * 60)
    log("CASO 4 - Busca por intervalo de datas (criado_em)")
    log("=" * 60)
    
    if FILTROS.get("modo") == "manual":
        ano = FILTROS["manual"]["ano"]
    else:
        # Pegar um ano que com certeza existe no banco para evitar query vazia (0 docs)
        amostra = list(col.aggregate([{"$sample": {"size": 1}}]))
        ano = amostra[0]["criado_em"].year if amostra else DATA_INICIO.year
    
    filtro = {"criado_em": {"$gte": datetime(ano, 1, 1), "$lte": datetime(ano, 12, 31)}}
    log(f"  Filtro: criado_em em {ano}\n")
    remover_indices(col)

    tempos_sem = medir_query(col, filtro, barra=barra)
    exp_sem    = explain_query(col, filtro, "caso_1", "sem_indice")
    imprimir_resultado("Sem indice", tempos_sem, exp_sem, log)

    col.create_index([("criado_em", ASCENDING)])
    tempos_com = medir_query(col, filtro, barra=barra)
    exp_com    = explain_query(col, filtro, "caso_1", "com_indice")
    imprimir_resultado("Com indice (date)", tempos_com, exp_com, log)

    remover_indices(col)
    return {"sem_indice": tempos_sem, "com_indice": tempos_com,
            "exp_sem": exp_sem, "exp_com": exp_com}

def caso_5_busca_textual(col, barra=None, log=print):
    log("=" * 60)
    log("CASO 5 - Busca textual (profissao)")
    log("=" * 60)
    if FILTROS.get("modo") == "manual":
        profissao = FILTROS["manual"]["profissao"]
    else:
        profissao = random.choice(PROFISSOES)
    log(f"  Filtro: profissao = '{profissao}'\n")
    remover_indices(col)

    filtro_regex = {"profissao": {"$regex": profissao, "$options": "i"}}
    tempos_sem   = medir_query(col, filtro_regex, barra=barra)
    exp_sem      = explain_query(col, filtro_regex, "caso_1", "sem_indice")
    imprimir_resultado("Sem indice (regex)", tempos_sem, exp_sem, log)

    col.create_index([("profissao", TEXT)])
    filtro_text = {"$text": {"$search": profissao}}
    tempos_com  = medir_query(col, filtro_text, barra=barra)
    exp_com     = explain_query(col, filtro_text, "caso_1", "com_indice")
    imprimir_resultado("Com indice (text)", tempos_com, exp_com, log)

    remover_indices(col)
    return {"sem_indice": tempos_sem, "com_indice": tempos_com,
            "exp_sem": exp_sem, "exp_com": exp_com}


def caso_6_escrita_e_armazenamento(col, db, barra=None, log=print):
    log("=" * 60)
    log("CASO 6 - Sobrecarga de Escrita e Armazenamento")
    log("=" * 60)
    remover_indices(col)
    
    tamanho_lote = 5000
    docs_teste = [gerar_usuario() for _ in range(tamanho_lote)]
    
    stats_sem = db.command("collStats", col.name)
    tamanho_index_sem = stats_sem.get("totalIndexSize", 0) / (1024 * 1024)
    
    log("  Medindo insercao SEM indice...")
    tempos_sem = []
    for _ in range(REPETICOES):
        docs = [d.copy() for d in docs_teste]
        for d in docs: d.pop("_id", None)
        inicio = time.perf_counter()
        res = col.insert_many(docs)
        tempos_sem.append((time.perf_counter() - inicio) * 1000)
        col.delete_many({"_id": {"$in": res.inserted_ids}})
        if barra: barra.update(1)
        
    est_sem = resumo_estatistico(tempos_sem)
    log(f"  [Sem indices extras]")
    log(f"    Tamanho dos indices: {tamanho_index_sem:.2f} MB")
    log(f"    Tempo medio de insercao: {est_sem['media']} ms")
    
    log("\n  Criando indices dos Casos 1 a 5...")
    from pymongo import IndexModel
    col.create_indexes([
        IndexModel([("estado", ASCENDING)]),
        IndexModel([("estado", ASCENDING), ("ativo", ASCENDING)]),
        IndexModel([("salario", ASCENDING)]),
        IndexModel([("criado_em", ASCENDING)]),
        IndexModel([("profissao", TEXT)])
    ])
    
    stats_com = db.command("collStats", col.name)
    tamanho_index_com = stats_com.get("totalIndexSize", 0) / (1024 * 1024)
    
    log("  Medindo insercao COM indices...")
    tempos_com = []
    for _ in range(REPETICOES):
        docs = [d.copy() for d in docs_teste]
        for d in docs: d.pop("_id", None)
        inicio = time.perf_counter()
        res = col.insert_many(docs)
        tempos_com.append((time.perf_counter() - inicio) * 1000)
        col.delete_many({"_id": {"$in": res.inserted_ids}})
        if barra: barra.update(1)
        
    est_com = resumo_estatistico(tempos_com)
    log(f"  [Com indices extras]")
    log(f"    Tamanho dos indices: {tamanho_index_com:.2f} MB (+{tamanho_index_com - tamanho_index_sem:.2f} MB)")
    log(f"    Tempo medio de insercao: {est_com['media']} ms")
    
    remover_indices(col)
    
    return {
        "sem_indice": tempos_sem, 
        "com_indice": tempos_com,
        "tamanho_index_sem_mb": tamanho_index_sem,
        "tamanho_index_com_mb": tamanho_index_com
    }

# -- Graficos --------------------------------------------------------------------


LABELS_CASOS = [
    "Caso 1\nCampo unico",
    "Caso 2\nComposto",
    "Caso 3\nFaixa numerica",
    "Caso 4\nDatas",
    "Caso 5\nTextual",
    "Caso 6\nEscritas/Armazenamento",
]

COR_SEM   = "#D32F2F"
COR_COM   = "#1976D2"
COR_SPEED = "#388E3C"


def _salvar(fig, nome):
    caminho = os.path.join(OUTPUT_DIR, "graficos", f"{nome}.{FORMATO}")
    fig.savefig(caminho, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> {caminho}")


def grafico_comparacao_geral(resultados):
    """Barras agrupadas: tempo medio com vs sem indice para todos os casos."""
    casos      = [c for c in resultados.keys() if "Caso 6" not in c]
    medias_sem = [resumo_estatistico(resultados[c]["sem_indice"])["media"] for c in casos]
    medias_com = [resumo_estatistico(resultados[c]["com_indice"])["media"] for c in casos]
    erros_sem  = [resumo_estatistico(resultados[c]["sem_indice"])["desvio_pad"] for c in casos]
    erros_com  = [resumo_estatistico(resultados[c]["com_indice"])["desvio_pad"] for c in casos]

    x, w = np.arange(len(casos)), 0.35
    fig, ax = plt.subplots(figsize=(12, 6))
    b1 = ax.bar(x - w/2, medias_sem, w, yerr=erros_sem, label="Sem indice",
                color=COR_SEM, capsize=5, error_kw={"elinewidth": 1.5})
    b2 = ax.bar(x + w/2, medias_com, w, yerr=erros_com, label="Com indice",
                color=COR_COM, capsize=5, error_kw={"elinewidth": 1.5})
    for b in list(b1) + list(b2):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.3,
                f"{b.get_height():.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xlabel("Caso de Uso", fontsize=12)
    ax.set_ylabel("Tempo medio (ms)", fontsize=12)
    ax.set_title("Visao Geral - Tempo Medio por Caso de Uso", fontsize=14)
    ax.set_xticks(x); ax.set_xticklabels(casos, rotation=15, ha="right", fontsize=9)
    ax.legend(fontsize=11)
    plt.tight_layout()
    _salvar(fig, "01_comparacao_geral")


def graficos_por_caso(resultados):
    """Um grafico de barras individual para cada caso de uso."""
    for i, (caso, dados) in enumerate(resultados.items(), 1):
        if "Caso 6" in caso: continue
        est_sem = resumo_estatistico(dados["sem_indice"])
        est_com = resumo_estatistico(dados["com_indice"])
        categorias = ["Sem indice", "Com indice"]
        medias = [est_sem["media"], est_com["media"]]
        erros  = [est_sem["desvio_pad"], est_com["desvio_pad"]]
        cores  = [COR_SEM, COR_COM]

        fig, ax = plt.subplots(figsize=(7, 5))
        bars = ax.bar(categorias, medias, yerr=erros, color=cores,
                      capsize=6, error_kw={"elinewidth": 1.5}, width=0.4)
        for b in bars:
            ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.3,
                    f"{b.get_height():.2f} ms", ha="center", va="bottom", fontsize=10)
        titulo = caso.replace("\n", " - ")
        ax.set_title(f"Tempo Medio - {titulo}", fontsize=13)
        ax.set_ylabel("Tempo medio (ms)", fontsize=11)
        plt.tight_layout()
        _salvar(fig, f"02_caso_{i}_tempo")


def grafico_docs_examinados(resultados):
    """Barras agrupadas: documentos examinados com vs sem indice."""
    casos      = [c for c in resultados.keys() if "Caso 6" not in c]
    docs_sem = [resultados[c]["exp_sem"]["totalDocsExamined"] for c in casos]
    docs_com = [resultados[c]["exp_com"]["totalDocsExamined"] for c in casos]

    x, w = np.arange(len(casos)), 0.35
    fig, ax = plt.subplots(figsize=(12, 6))
    b1 = ax.bar(x - w/2, docs_sem, w, label="Sem indice", color=COR_SEM)
    b2 = ax.bar(x + w/2, docs_com, w, label="Com indice", color=COR_COM)
    for b in list(b1) + list(b2):
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + max(docs_sem) * 0.01,
                f"{int(b.get_height()):,}", ha="center", va="bottom", fontsize=7, rotation=30)
    ax.set_xlabel("Caso de Uso", fontsize=12)
    ax.set_ylabel("Documentos Examinados", fontsize=12)
    ax.set_title("Documentos Examinados pelo MongoDB - Com vs Sem Indice", fontsize=14)
    ax.set_xticks(x); ax.set_xticklabels(casos, rotation=15, ha="right", fontsize=9)
    ax.legend(fontsize=11)
    plt.tight_layout()
    _salvar(fig, "03_docs_examinados")


def grafico_speedup(resultados):
    """Barras horizontais: fator de aceleracao (speedup) do indice por caso."""
    casos      = [c for c in resultados.keys() if "Caso 6" not in c]
    speedup = []
    for c in casos:
        media_sem = resumo_estatistico(resultados[c]["sem_indice"])["media"]
        media_com = resumo_estatistico(resultados[c]["com_indice"])["media"]
        speedup.append(round(media_sem / media_com, 2) if media_com > 0 else 0)

    fig, ax = plt.subplots(figsize=(9, 6))
    bars = ax.barh(casos, speedup, color=COR_SPEED, edgecolor="white")
    
    # Usar escala logarítmica para impedir que speedups gigantes engulam os menores
    ax.set_xscale("log")
    ax.set_xlim(left=0.5) # Iniciar um pouco antes do 1x para nao cortar
    
    ax.axvline(x=1, color=COR_SEM, linestyle="--", linewidth=1, label="Sem ganho (1x)")
    for b, v in zip(bars, speedup):
        offset = v * 1.15 if v > 0 else 1.15
        ax.text(offset, b.get_y() + b.get_height()/2,
                f"{v:.2f}x", va="center", fontsize=10, fontweight="bold")
    ax.set_xlabel("Speedup (Escala Logarítmica - vezes mais rápido)", fontsize=11)
    ax.set_title("Fator de Aceleração por Uso de Índice", fontsize=14)
    ax.legend(fontsize=10)
    plt.tight_layout()
    _salvar(fig, "04_speedup")





def grafico_boxplot_estabilidade(resultados):
    """Boxplot para mostrar a variancia dos tempos (com vs sem indice)."""
    casos = [c for c in resultados.keys() if "Caso 6" not in c]
    dados_sem = [resultados[c]["sem_indice"] for c in casos]
    dados_com = [resultados[c]["com_indice"] for c in casos]
    
    fig, ax = plt.subplots(figsize=(12, 6))
    pos_sem = np.arange(len(casos)) * 2.0 - 0.4
    pos_com = np.arange(len(casos)) * 2.0 + 0.4
    
    bp_sem = ax.boxplot(dados_sem, positions=pos_sem, widths=0.6, patch_artist=True)
    bp_com = ax.boxplot(dados_com, positions=pos_com, widths=0.6, patch_artist=True)
    
    for patch in bp_sem['boxes']:
        patch.set_facecolor(COR_SEM)
        patch.set_alpha(0.7)
    for patch in bp_com['boxes']:
        patch.set_facecolor(COR_COM)
        patch.set_alpha(0.7)
        
    for median in bp_sem['medians']: median.set_color('black')
    for median in bp_com['medians']: median.set_color('black')
        
    ax.set_xticks(np.arange(len(casos)) * 2.0)
    ax.set_xticklabels([c.replace('\n', ' ') for c in casos], rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("Tempo de Execucao (ms) - Escala Log", fontsize=11)
    ax.set_yscale("log")
    ax.set_title("Estabilidade das Consultas (Boxplot das Repeticoes)", fontsize=14)
    
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=COR_SEM, label='Sem Indice', alpha=0.7),
                       Patch(facecolor=COR_COM, label='Com Indice', alpha=0.7)]
    ax.legend(handles=legend_elements, fontsize=11)
    plt.tight_layout()
    _salvar(fig, "05_boxplot_estabilidade")


def grafico_penalidade_escrita(resultados):
    """Bar chart do tempo de insercao."""
    chave_c6 = next((k for k in resultados.keys() if "Caso 6" in k), None)
    if not chave_c6: return
    
    dados = resultados[chave_c6]
    t_sem = resumo_estatistico(dados["sem_indice"])["media"]
    t_com = resumo_estatistico(dados["com_indice"])["media"]
    
    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(["Sem indices extras", "Com todos os indices"], [t_sem, t_com], color=[COR_SEM, COR_COM], width=0.5)
    for b in bars:
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + (max(t_sem, t_com) * 0.02),
                f"{b.get_height():.1f} ms", ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_ylabel("Tempo Medio de Insercao Lote (ms)", fontsize=11)
    ax.set_title("Penalidade de Escrita (Trade-off de Indices)", fontsize=13)
    plt.tight_layout()
    _salvar(fig, "06_penalidade_escrita")


def grafico_overhead_armazenamento(resultados):
    """Bar chart comparando o tamanho dos indices."""
    chave_c6 = next((k for k in resultados.keys() if "Caso 6" in k), None)
    if not chave_c6: return
    
    dados = resultados[chave_c6]
    tam_sem = dados["tamanho_index_sem_mb"]
    tam_com = dados["tamanho_index_com_mb"]
    
    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(["Apenas _id padrao", "Todos os Indices"], [tam_sem, tam_com], color=[COR_SEM, COR_COM], width=0.5)
    for b in bars:
        ax.text(b.get_x() + b.get_width()/2, b.get_height() + (max(tam_sem, tam_com) * 0.02),
                f"{b.get_height():.1f} MB", ha="center", va="bottom", fontsize=11, fontweight="bold")
    ax.set_ylabel("Espaco em Disco Ocupado (MB)", fontsize=11)
    ax.set_title("Overhead de Armazenamento (Tamanho dos Indices)", fontsize=13)
    plt.tight_layout()
    _salvar(fig, "07_overhead_armazenamento")


def exportar_latex(resultados):
    linhas = []
    linhas.append("\\begin{table}[htpb]")
    linhas.append("\\centering")
    linhas.append("\\caption{Comparativo de Desempenho e Documentos Examinados}")
    linhas.append("\\label{tab:resultados}")
    linhas.append("\\begin{tabular}{l|rr|rr|r}")
    linhas.append("\\hline")
    linhas.append("\\textbf{Caso de Uso} & \\textbf{Tempo sem Índice (ms)} & \\textbf{Docs. Examinados (Sem)} & \\textbf{Tempo com Índice (ms)} & \\textbf{Docs. Examinados (Com)} & \\textbf{Fator de Aceleração (Speedup)} \\\\")
    linhas.append("\\hline")
    
    for nome, dados in resultados.items():
        if "Caso 6" in nome: continue
        t_sem = resumo_estatistico(dados["sem_indice"])["media"]
        t_com = resumo_estatistico(dados["com_indice"])["media"]
        docs_sem = dados["exp_sem"]["totalDocsExamined"]
        docs_com = dados["exp_com"]["totalDocsExamined"]
        speedup = round(t_sem / t_com, 2) if t_com > 0 else 0
        nome_limpo = nome.replace("\n", " ")
        linhas.append(f"{nome_limpo} & {t_sem:.2f} & {docs_sem:,} & {t_com:.2f} & {docs_com:,} & {speedup}x \\\\")
        
    linhas.append("\\hline")
    linhas.append("\\end{tabular}")
    linhas.append("\\end{table}")
    
    if any("Caso 6" in k for k in resultados.keys()):
        for nome, dados in resultados.items():
            if "Caso 6" in nome:
                linhas.append("\n\\begin{table}[htpb]")
                linhas.append("\\centering")
                linhas.append("\\caption{Impacto dos Índices no Armazenamento e Inserção}")
                linhas.append("\\label{tab:impacto_indices}")
                linhas.append("\\begin{tabular}{l|rr}")
                linhas.append("\\hline")
                linhas.append("\\textbf{Cenário} & \\textbf{Tamanho dos Índices (MB)} & \\textbf{Tempo de Inserção (ms)} \\\\")
                linhas.append("\\hline")
                t_sem = resumo_estatistico(dados["sem_indice"])["media"]
                t_com = resumo_estatistico(dados["com_indice"])["media"]
                tam_sem = dados["tamanho_index_sem_mb"]
                tam_com = dados["tamanho_index_com_mb"]
                linhas.append(f"Sem Índices & {tam_sem:.2f} & {t_sem:.2f} \\\\")
                linhas.append(f"Com Todos os Índices & {tam_com:.2f} & {t_com:.2f} \\\\")
                linhas.append("\\hline")
                linhas.append("\\end{tabular}")
                linhas.append("\\end{table}")
                
    caminho = os.path.join(OUTPUT_DIR, "latex", "tabelas.tex")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas))
    print(f"  -> {caminho}")


def exportar_csv(resultados):
    # 1. Agregado Consultas (Medias)
    caminho_agregado = os.path.join(OUTPUT_DIR, "csv", "consultas_agregado.csv")
    with open(caminho_agregado, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Caso de Uso", "Tempo Medio Sem Indice (ms)", "Tempo Medio Com Indice (ms)", "Docs Sem Indice", "Docs Com Indice", "Speedup"])
        casos = [c for c in resultados.keys() if "Caso 6" not in c]
        for nome in casos:
            dados = resultados[nome]
            t_sem = resumo_estatistico(dados["sem_indice"])["media"]
            t_com = resumo_estatistico(dados["com_indice"])["media"]
            docs_sem = dados["exp_sem"]["totalDocsExamined"]
            docs_com = dados["exp_com"]["totalDocsExamined"]
            speedup = round(t_sem / t_com, 2) if t_com > 0 else 0
            nome_limpo = nome.replace("\n", " ")
            writer.writerow([nome_limpo, t_sem, t_com, docs_sem, docs_com, speedup])
    print(f"  -> {caminho_agregado}")

    # 2. Bruto Consultas (Todas as execucoes)
    caminho_bruto = os.path.join(OUTPUT_DIR, "csv", "consultas_bruto.csv")
    with open(caminho_bruto, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Caso de Uso", "Cenario", "Repeticao", "Tempo (ms)"])
        for nome in casos:
            dados = resultados[nome]
            nome_limpo = nome.replace("\n", " ")
            for i, t in enumerate(dados["sem_indice"]):
                writer.writerow([nome_limpo, "Sem Indice", i + 1, round(t, 3)])
            for i, t in enumerate(dados["com_indice"]):
                writer.writerow([nome_limpo, "Com Indice", i + 1, round(t, 3)])
    print(f"  -> {caminho_bruto}")

    # 3. Caso 6 (Escrita e Armazenamento)
    if any("Caso 6" in k for k in resultados.keys()):
        caminho_escrita = os.path.join(OUTPUT_DIR, "csv", "escrita_armazenamento.csv")
        with open(caminho_escrita, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Cenario", "Tamanho dos Indices (MB)", "Tempo Medio de Insercao (ms)"])
            for nome, dados in resultados.items():
                if "Caso 6" in nome:
                    t_sem = resumo_estatistico(dados["sem_indice"])["media"]
                    t_com = resumo_estatistico(dados["com_indice"])["media"]
                    tam_sem = dados["tamanho_index_sem_mb"]
                    tam_com = dados["tamanho_index_com_mb"]
                    writer.writerow(["Sem Indices", round(tam_sem, 2), t_sem])
                    writer.writerow(["Com Todos os Indices", round(tam_com, 2), t_com])
        print(f"  -> {caminho_escrita}")


def gerar_todos_graficos(resultados):
    import subprocess
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "csv"), exist_ok=True)
    
    exportar_csv(resultados)

    log_header("GERANDO GRAFICOS PADRONIZADOS VIA PLOTAR_GRAFICOS.PY")
    try:
        script_graficos = os.path.join(PROJECT_ROOT, "src", "utils", "plotar_graficos.py")
        subprocess.run([sys.executable, script_graficos], check=True)
        print("\n[SUCESSO] Graficos gerados na pasta 'resultados/graficos_revisados'.")
    except Exception as e:
        print(f"\n[ERRO] Falha ao executar plotar_graficos.py: {e}")


# -- Main ------------------------------------------------------------------------

# Linhas do cabecalho fixo (impressas uma vez)
HEADER_LINES = []
# Bloco mutavel exibido abaixo da barra (apagado a cada caso)
_BLOCO_ATUAL = []
# Referencia global para a barra de progresso
_BARRA = None

def _redesenhar_tela():
    """Limpa a tela e redesenha o cabecalho, o bloco atual e a barra."""
    os.system('cls' if os.name == 'nt' else 'clear')
    for linha in HEADER_LINES:
        print(linha)
    print("")
    for linha in _BLOCO_ATUAL:
        print(linha)
    if _BARRA:
        print("")
        _BARRA.refresh()

def log_header(msg):
    """Adiciona uma linha de cabecalho fixo."""
    HEADER_LINES.append(msg)
    _redesenhar_tela()

def log(msg):
    """Adiciona uma linha ao bloco mutavel."""
    _BLOCO_ATUAL.append(msg)
    _redesenhar_tela()

def log_bloco(linhas):
    """Substitui o bloco mutavel inteiro de uma vez."""
    _BLOCO_ATUAL.clear()
    _BLOCO_ATUAL.extend(linhas)
    _redesenhar_tela()

def reset_bloco():
    """Apaga o bloco mutavel sem escrever nada (transicao entre casos)."""
    _BLOCO_ATUAL.clear()
    _redesenhar_tela()

def main():
    total_medicoes = REPETICOES * 2 * 6  # 2 rodadas (sem/com indice) x 6 casos

    log_header("=== BD2 - Experimentos MongoDB ===")
    log_header(f"[Config] Dataset alvo: {TAMANHO_GB} GB (~{TAMANHO:,} documentos estimados)")

    client = MongoClient(MONGO_URI)
    db     = client[DB_NAME]
    col    = db[COL_NAME]

    if DB_NAME in client.list_database_names() and col.count_documents({}) > 0:
        log_header(f"[Setup] Banco pre-existente '{DB_NAME}' detectado. Excluindo por inteiro...")
        client.drop_database(DB_NAME)
        # Recria as variaveis pois o db sumiu
        db  = client[DB_NAME]
        col = db[COL_NAME]

    if col.count_documents({}) < TAMANHO:
        popular_banco(col, db)
    else:
        log_header(f"[Dataset] Collection ja possui {col.count_documents({}):,} documentos. Pulando insercao.")

    log_header("")
    resultados = {}
    global _BARRA
    with tqdm(total=total_medicoes, desc="Progresso total", unit="exec", position=0, leave=True,
              bar_format="{desc}: {percentage:3.0f}%|{bar}| {n}/{total} [{elapsed}<{remaining}]") as barra:
        _BARRA = barra
        resultados[LABELS_CASOS[0]] = caso_1_busca_simples(col, barra, log)
        reset_bloco()
        resultados[LABELS_CASOS[1]] = caso_2_filtro_composto(col, barra, log)
        reset_bloco()
        resultados[LABELS_CASOS[2]] = caso_3_faixa_numerica(col, barra, log)
        reset_bloco()
        resultados[LABELS_CASOS[3]] = caso_4_intervalo_datas(col, barra, log)
        reset_bloco()
        resultados[LABELS_CASOS[4]] = caso_5_busca_textual(col, barra, log)
        reset_bloco()
        resultados[LABELS_CASOS[5]] = caso_6_escrita_e_armazenamento(col, db, barra, log)
        reset_bloco()

    print("\n[Info] Gerando graficos...")
    gerar_todos_graficos(resultados)
    print("\n[Info] Excluindo banco de dados para liberar espaco no disco...")
    client.drop_database(DB_NAME)
    print("=== Experimentos concluidos ===\n")
    client.close()

if __name__ == "__main__":
    main()
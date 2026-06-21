import subprocess
import time
import sys
import os

# Adiciona a raiz do projeto ao path para importar modulos do src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from src.config_loader import PROJECT_ROOT

from pymongo import MongoClient

def run_cmd(cmd, silent=False):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if not silent:
        if result.stdout: print(result.stdout.strip())
        if result.stderr: print(result.stderr.strip())
    return result

def main():
    print("=" * 50)
    print(" INICIANDO LIMPEZA TOTAL DE AMBIENTE ")
    print("=" * 50)

    # 1. Checar se o mongodb nativo está rodando
    print("\n[1/4] Verificando servico MongoDB nativo (Ubuntu)...")
    status = run_cmd("systemctl is-active mongodb", silent=True)
    if status.stdout.strip() != "active":
        print("MongoDB nativo esta inativo. Iniciando para limpeza de bancos...")
        run_cmd("systemctl start mongodb")
        time.sleep(2) # Dar tempo para o servico inicializar
    else:
        print("MongoDB nativo ja esta rodando.")

    # 2. Limpar todos os bancos no MongoDB nativo
    print("\n[2/4] Conectando ao MongoDB nativo e deletando bancos de dados...")
    try:
        client = MongoClient('mongodb://localhost:27017', serverSelectionTimeoutMS=3000)
        # Forca a conexao para testar
        client.server_info()
        
        db_names = client.list_database_names()
        protegidos = ["admin", "config", "local"]
        apagados = 0
        for db in db_names:
            if db not in protegidos:
                print(f"  -> Apagando banco de dados: '{db}'...")
                client.drop_database(db)
                apagados += 1
        
        if apagados == 0:
            print("  Nenhum banco de dados do usuario encontrado para apagar.")
        else:
            print(f"  {apagados} banco(s) apagado(s) com sucesso!")
            
    except Exception as e:
        print(f"[ERRO] Nao foi possivel conectar/limpar o Mongo nativo: {e}")

    # 3. Desligar o MongoDB nativo
    print("\n[3/4] Desligando MongoDB nativo para liberar a porta 27017...")
    run_cmd("systemctl stop mongodb")
    print("Servico 'mongodb' desligado com sucesso.")

    # 4. Limpeza severa do Docker
    print("\n[4/4] Exterminando volumes e conteineres do Docker...")
    print("  -> Baixando arquitetura atual (docker compose down)...")
    run_cmd(f"docker compose -f {os.path.join(PROJECT_ROOT, 'docker-compose.yml')} down -v --remove-orphans")
    
    print("  -> Destruindo volumes orfaos (docker volume prune)...")
    run_cmd("docker volume prune -a -f")
    
    print("  -> Limpando cache de build (docker builder prune)...")
    run_cmd("docker builder prune -a -f")

    print("\n[5/5] Removendo relatórios e lixo antigo do disco local...")
    import shutil
    import os
    for dir_name in ["resultados", "results"]:
        target = os.path.join(PROJECT_ROOT, dir_name)
        if os.path.exists(target):
            try:
                shutil.rmtree(target)
                print(f"  -> '{dir_name}' deletada.")
            except Exception as e:
                print(f"  [Aviso] Nao foi possivel deletar '{dir_name}': {e}")
                
    print("\n" + "=" * 50)
    print(" LIMPEZA CONCLUIDA! AMBIENTE 100% ESTERILIZADO. ")
    print("=" * 50)

if __name__ == "__main__":
    main()

import os
import sys
import subprocess
import time

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    print("="*60)
    print(" TESE: ÍNDICES E REDES DISTRIBUÍDAS NO MONGODB ".center(60))
    print("="*60)
    print("Escolha o que deseja executar:\n")

def run_isolado():
    print("\n[Iniciando] Estudo de Caso 1: MongoDB Isolado (Single Node)...")
    try:
        subprocess.run([sys.executable, "-m", "src.experimentos.caso_isolado"], check=True)
    except subprocess.CalledProcessError:
        print("\n[ERRO] A execução do caso isolado falhou.")

def run_distribuido():
    print("\n[Iniciando] Estudo de Caso 2: MongoDB Distribuído (Sharded)...")
    print("-> Levantando containers Docker...")
    try:
        subprocess.run(["docker", "compose", "up", "-d"], check=True)
        print("-> Inicializando a inteligência do Cluster (Sharding)...")
        subprocess.run([sys.executable, "-m", "src.infra.init_cluster"], check=True)
        print("-> Executando bateria de testes distribuídos...")
        subprocess.run([sys.executable, "-m", "src.experimentos.caso_distribuido"], check=True)
    except subprocess.CalledProcessError:
        print("\n[ERRO] A execução do caso distribuído falhou.")

def run_otimizado():
    print("\n[Iniciando] Estudo de Caso 3: Otimização Progressiva (N0 ao N4)...")
    try:
        subprocess.run([sys.executable, "-m", "src.experimentos.caso_otimizado"], check=True)
    except subprocess.CalledProcessError:
        print("\n[ERRO] A execução do caso otimizado falhou.")

def limpar_ambiente():
    print("\n[Iniciando] Limpeza Profunda de Ambiente (Requer permissões sudo)...")
    try:
        # A limpeza requer chamadas ao systemctl que normalmente pedem root no Linux
        subprocess.run(["sudo", sys.executable, "-m", "src.utils.limpar_ambiente"], check=True)
    except subprocess.CalledProcessError:
        print("\n[ERRO] Falha ao tentar limpar o ambiente.")

def main():
    while True:
        clear_screen()
        print_header()
        print(" [ 1 ] Rodar Experimento Isolado (Single Node)")
        print(" [ 2 ] Rodar Experimento Distribuído (Sharded Cluster)")
        print(" [ 3 ] Rodar Bateria Completa (Isolado -> Distribuído)")
        print(" [ 4 ] Limpar Ambiente (Destruir Containers e Bancos)")
        print(" [ 5 ] Otimização Progressiva (Covered Queries)")
        print(" [ 0 ] Sair")
        print("="*60)
        
        escolha = input("\nDigite a opção desejada: ").strip()
        
        if escolha == '1':
            run_isolado()
            input("\nPressione ENTER para voltar ao menu...")
            
        elif escolha == '2':
            run_distribuido()
            input("\nPressione ENTER para voltar ao menu...")
            
        elif escolha == '3':
            run_isolado()
            print("\n" + "="*60 + "\n")
            time.sleep(2)
            run_distribuido()
            input("\nPressione ENTER para voltar ao menu...")
            
        elif escolha == '4':
            limpar_ambiente()
            input("\nPressione ENTER para voltar ao menu...")
            
        elif escolha == '5':
            run_otimizado()
            input("\nPressione ENTER para voltar ao menu...")
            
        elif escolha == '0':
            print("\nFinalizando...\n")
            break
            
        else:
            print("\nOpção inválida!")
            time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSaindo...")
        sys.exit(0)

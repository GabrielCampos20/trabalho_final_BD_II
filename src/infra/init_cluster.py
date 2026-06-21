import subprocess
import time

def executar(comando):
    # No Windows, subprocess com docker pode ser caprichoso se não passar a lista exata
    try:
        subprocess.run(comando, check=True, shell=False)
    except subprocess.CalledProcessError as e:
        print(f"\n[ERRO] O comando falhou: {' '.join(comando)}")
        print(e)
        exit(1)

print("=== Inicializando MongoDB Sharded Cluster ===")

print("\n[1/6] Inicializando Servidor de Configuracao (configRS)...")
executar(["docker", "exec", "mongo-configsvr", "mongosh", "--port", "27019", "--eval", "rs.initiate({_id: 'configRS', configsvr: true, members: [{_id: 0, host: 'configsvr:27019'}]})"])

print("\n[2/6] Inicializando Shard 1 (shard1RS)...")
executar(["docker", "exec", "mongo-shard1", "mongosh", "--port", "27018", "--eval", "rs.initiate({_id: 'shard1RS', members: [{_id: 0, host: 'shard1:27018'}]})"])

print("\n[3/6] Inicializando Shard 2 (shard2RS)...")
executar(["docker", "exec", "mongo-shard2", "mongosh", "--port", "27020", "--eval", "rs.initiate({_id: 'shard2RS', members: [{_id: 0, host: 'shard2:27020'}]})"])

print("\n=> Aguardando 10 segundos para a eleicao de lideres dos Replica Sets...")
time.sleep(10)

print("\n[4/6] Reiniciando Roteador Mongos para carregar os metadados...")
executar(["docker", "restart", "mongo-router"])
time.sleep(5)

print("\n[5/6] Acoplando Shards ao Roteador...")
executar(["docker", "exec", "mongo-router", "mongosh", "--port", "27017", "--eval", "sh.addShard('shard1RS/shard1:27018')"])
executar(["docker", "exec", "mongo-router", "mongosh", "--port", "27017", "--eval", "sh.addShard('shard2RS/shard2:27020')"])

print("\n[6/6] Habilitando Sharding no banco de dados e particionando a collection...")
executar(["docker", "exec", "mongo-router", "mongosh", "--port", "27017", "--eval", "sh.enableSharding('bd2_experimentos')"])
executar(["docker", "exec", "mongo-router", "mongosh", "--port", "27017", "--eval", "sh.shardCollection('bd2_experimentos.usuarios', { 'estado': 1 })"])

print("\n=============================================")
print("[SUCESSO] Cluster Sharded MongoDB pronto para uso!")
print("=============================================\n")

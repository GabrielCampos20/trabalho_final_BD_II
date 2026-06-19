# Trabalho Final - Banco de Dados II
**Avaliação Experimental: Índices e Redes Distribuídas no MongoDB**

Este repositório contém uma bateria de scripts automatizados para benchmarking e extração de métricas de desempenho em bancos de dados NoSQL (MongoDB). O estudo está dividido em duas frentes de pesquisa arquitetural:

1. **Estudo de Caso 1 (Standalone / Single Node):** Mede e compara o tempo de execução e a varredura de disco entre consultas limpas (Collection Scan) contra consultas apoiadas por Índices (B-Tree, Compostos, Texto). Analisa também o *trade-off* de espaço de armazenamento dos índices contra o tempo de inserção.
2. **Estudo de Caso 2 (Distributed / Sharded Cluster):** Utiliza orquestração Docker para levantar um Cluster MongoDB particionado, focado em provar a latência de rede e a eficiência do Mongos Router ao realizar buscas direcionadas (*Targeted Queries*) pela Chave de Sharding contra buscas de difusão (*Scatter-Gather*).

---

## 💾 Modelagem do Banco de Dados
Os dados são gerados sinteticamente (usando a biblioteca `Faker`) em tempo de execução para preencher 1 GB de massa de testes (aprox. 2.6 milhões de registros).

A modelagem adotada para a *collection* `usuarios` segue o seguinte formato JSON:
```json
{
  "_id": ObjectId("..."),
  "nome": "João Silva",           // String
  "email": "joao@example.com",    // String
  "estado": "SP",                 // String (ENUM: Estados Brasileiros)
  "salario": 14500.50,            // Float (1000 a 25000)
  "ativo": true,                  // Boolean
  "criado_em": ISODate("..."),    // Date (-5 anos ate hoje)
  "profissao": "Desenvolvedor",   // String
  "bio": "Biografia aleatória..." // String (Texto Livre)
}
```

---

## ⚙️ Pré-requisitos
Para garantir a reprodução idêntica dos experimentos em qualquer máquina:
* Python 3.10+
* Docker e Docker Compose (Apenas para o Estudo de Caso 2)

```bash
# 1. Crie e ative um ambiente virtual
python -m venv venv
source venv/bin/activate  # ou venv\Scripts\activate no Windows

# 2. Instale as dependências
pip install -r requirements.txt
```

---

## 🚀 Como Executar: Estudo de Caso 1 (Isolado)

Este caso mede Otimização e Índices. Ele pressupõe que você tenha um MongoDB local simples rodando na porta 27017.

```bash
python caso_isolado.py
```
> O script cuidará de inserir os dados, rodar todos os comparativos, dropar o banco no final e salvar as planilhas/gráficos na pasta `resultados/`.

---

## 🌐 Como Executar: Estudo de Caso 2 (Distribuído)

Este caso mede particionamento e overhead de rede.

**Passo 1: Subir o Cluster Local**
```bash
docker-compose up -d
```
> Isso levantará 4 containers: 1 Servidor de Configuração, 2 Shards de Dados e 1 Mongos Router (porta 27017).

**Passo 2: Configurar a Inteligência do Cluster**
Aguarde alguns segundos após o comando anterior e execute o inicializador:
```bash
python scripts/init_cluster.py
```
> O script Python vai conversar com os containers, eleger os líderes e configurar o campo `"estado"` como sendo a nossa *Shard Key* oficial.

**Passo 3: Rodar o Experimento**
```bash
python caso_distribuido.py
```
> Agora o Python se conecta ao Roteador. Ele vai disparar consultas direcionadas e varreduras de difusão na rede distribuída. Todos os resultados irão automaticamente para a pasta `resultados/`.

---

## 📊 Arquitetura de Configuração e Exportação
O projeto possui um arquivo `config.json` editável. Nele é possível alterar:
* A Semente (*Seed*) para garantir reprodutibilidade exata (Padrão: `42`).
* Tamanho do dataset em Gigabytes (Padrão: `1.0`).
* Modo do filtro de queries (`"automatico"` sorteia na hora, `"manual"` obedece o JSON).

Todas as execuções exportam os dados na pasta `resultados/`, já organizados em:
* `graficos/`: Todos os *plots* (Boxplots, Barras e Linhas).
* `csv/`: Extrações Tidy Data (`agregado`, `bruto` e `armazenamento`).
* `latex/`: Tabela pronta para cópia em artigos acadêmicos.

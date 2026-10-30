# Validação da versão 0.1.0

Execução local em **29 de outubro de 2026**, fuso America/Sao_Paulo.
Os números abaixo descrevem este snapshot, não uma promessa de dados em tempo real.

## Verificações

| Verificação | Resultado |
| --- | --- |
| Pytest completo | 61 testes aprovados em Python 3.11.18 e 3.12.16 |
| Ruff | Sem erros |
| Interface offline | AppTest sem exceções; demo explicitamente sintética |
| Interface com base real | 26.006 opções, 2 gráficos, 3 abas; sem fallback para demo |
| Gráficos com dia omitido | Lacuna inserida apenas na visualização, sem fabricar observações |
| Consultas SQL exploratórias | Três consultas executadas sobre o banco real |
| Integridade SQLite | PRAGMA quick_check = ok |
| Build Python | Wheel e distribuição fonte construídos |
| CI | Resultados de cada execução disponíveis em GitHub Actions; os testes abaixo descrevem a validação local |

## Revisão antes da publicação

- Nenhum token real, chave privada ou caminho pessoal foi encontrado nos arquivos preparados para publicação.
- Bancos locais, ZIPs, ambientes, logs e arquivos de credenciais ficam fora do Git.
- URLs de proveniência perdem credenciais, query e fragmento; URLs malformadas são rejeitadas sem expor valores no encadeamento do erro.
- O cache ZIP tem tamanho declarado conferido antes da descompressão e integridade CRC validada antes do uso.
- Há regressões para cache corrompido, limite de descompressão, colunas ausentes, cotistas inválidos e competência esperada.
- O servidor usa loopback por padrão; commits usam o endereço noreply do GitHub.

## Aquisição real

Arquivo: `inf_diario_fi_202609.zip`, obtido da coleção mensal da CVM.

- Competência: **2026-09-01 a 2026-09-30**.
- Linhas válidas persistidas: **538.336**.
- Identidades fundo/classe + subclasse: **26.006** (não significa 26.006 CNPJs únicos).
- Linhas rejeitadas: **0**; duplicatas: **0**; falhas de parse numérico: **0**.
- SHA-256: `1f5c236c0fd46d583fc30f3ddd87d507669894f0abbd5a0fcdab3741155c4a8a`.
- Origem: https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202609.zip

Foram conferidos o hash do ZIP, a auditoria SQL, as contagens, a integridade e a análise
de uma identidade real. A base local não integra o repositório; clones novos precisam
importar dados reais novamente. O repositório inclui somente código, documentação e a
fixture sintética.

## Casos cobertos

Rentabilidade de 100 → 110 → 99 = −1%; menos de duas cotas; cotas inválidas; ausência
nos limites; fluxos parciais ou totalmente ausentes; PL e cotistas faltantes na última
observação; preservação de subclasses; reimportação idempotente; falhas atômicas; mês
divergente; BOM; ZIP ambíguo; downloads simulados com 404, corrupção e excesso de tamanho;
isolamento do comando demo; filtros de datas; formatação de cotistas e lacunas gráficas.

## Limites desta validação

- AppTest testa comportamento e elementos, não substitui inspeção visual em vários dispositivos.
- Não foi produzida captura de navegador nesta execução.
- A suíte completa foi executada localmente em Python **3.11.18** e **3.12.16**.
  O resultado de execução no Linux/GitHub deve ser consultado separadamente no CI.
- O parser mantém o mês validado em memória antes da transação SQL. Não é uma ingestão
  totalmente incremental: reserve memória para centenas de milhares de registros e não
  suponha compatibilidade com planos de hospedagem de memória reduzida.
- Um mês real foi validado; isso não prova compatibilidade com todos os arquivos históricos.
- Não há calendário oficial de feriados nem ajuste econômico de amortizações/distribuições.

## Reproduzir

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
ruff check .
python -m cota_aberta.cli import-cvm --month 2026-09 --db data/funds.sqlite --refresh
python -m streamlit run app.py
```

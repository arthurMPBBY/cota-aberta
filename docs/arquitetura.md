# Arquitetura

Três fronteiras: aquisição do arquivo, persistência SQL e cálculo puro. A interface não
implementa uma segunda versão das fórmulas.

```text
CVM ZIP / CSV local → validação → SQLite → analytics → Streamlit / CSV
```

## Estrutura

| Local | Responsabilidade |
| --- | --- |
| app.py | Interface Streamlit |
| src/cota_aberta/ | Ingestão, armazenamento, cálculo e CLI |
| data/demo/ | Fixture sintética versionada |
| data/raw/ | Cache de ZIPs reais, ignorado pelo Git |
| data/funds.sqlite | Banco real local |
| data/demo.sqlite | Banco demonstrativo separado |
| tests/ | Testes offline e AppTest |
| docs/ | Metodologia, arquitetura e validação |
| .github/workflows/ci.yml | Testes em Python 3.11/3.12 |

## Decisões

**SQLite** evita serviço adicional e credenciais sem esconder SQL, chaves e transações.
A base pode ser consultada por ferramentas SQL comuns.

**Snapshot mensal** é a unidade de importação; validação antecede escrita transacional.
Reimportar não duplica observações. Erros não devem apagar o snapshot anterior. Não há
sincronização automática ao abrir a interface.

**Demo separada** permite testes offline com anomalias intencionais. Não é fallback para
erros de aquisição real. A seleção distingue classe/subclasse, sem nomes inventados.

**Processo local** é o escopo do MVP. Hospedagem multiusuário requer controle de escrita,
cotas de upload, retenção e acesso. Histórico de importações não arquiva todas as revisões.

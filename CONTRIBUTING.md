# Como contribuir

Mudanças devem preservar o diferencial do projeto: qualquer número precisa ter uma fórmula,
um intervalo efetivo e limites claros. Não esconda lacunas para melhorar um gráfico.

## Preparação

```bash
uv sync --frozen --extra dev
uv run pytest -q
uv run ruff check .
```

Alternativa: `python -m pip install -e ".[dev]"`, seguida de `python -m pytest -q`
e `ruff check .`. Execute na raiz do repositório com Python 3.11 ou superior.

## Alterações

- Inclua teste de regressão para uma correção e mantenha a suíte offline.
- Preserve a identidade CNPJ + subclasse; não misture séries distintas.
- Não transforme campo ausente em zero nem complete cotas sem avisar.
- Documente mudanças nos critérios de período, fórmulas ou substituição de snapshots.
- Use dados sintéticos mínimos nos testes, não extratos de pessoas ou bases privadas.
- Rode os testes e confira `git diff --cached` antes de enviar.

## Arquivos locais

Não envie bancos, cache, logs, ambientes virtuais, arquivos .env, chaves ou dados de contas.
O .gitignore é uma barreira preventiva, não um scanner de segredos. Se precisar fornecer
um exemplo de configuração, use valores vazios ou fictícios e um nome explicitamente de exemplo.

## Relatar problemas

Informe a versão do Python, comando, erro e um CSV sintético mínimo para reproduzir.
Não inclua caminhos pessoais, tokens, senhas, CPF ou extratos. Para vulnerabilidades,
siga [SECURITY.md](SECURITY.md).

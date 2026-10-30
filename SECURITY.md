# Segurança e privacidade

## Escopo

Cota Aberta é um projeto de análise local de dados públicos da CVM. Não conecta contas
bancárias, não recebe credenciais de investimentos e não promete conformidade regulatória
ou auditoria contábil. A demonstração usa identificadores fictícios.

## O que não publicar

- Tokens, senhas, chaves privadas e arquivos de ambiente.
- Bancos locais, logs ou cache de downloads, que podem carregar metadados do ambiente.
- Extratos individuais, CPF, documentos pessoais ou bases privadas enviados por engano.

CNPJs de fundos nos arquivos oficiais são dados públicos da fonte. O projeto não precisa
versionar esses arquivos para funcionar: faça o download localmente pela CLI.

## Operação

Prefira a execução em loopback (127.0.0.1). Não exponha a aplicação para uploads de terceiros
sem autenticação, limites adicionais e isolamento. O MVP não foi projetado como serviço
multiusuário. Snapshots mensais substituem dados do mesmo mês após validação; preserve
backups quando precisar manter revisões históricas.

O importador impõe limites de tamanho e lê ZIPs sem extrair caminhos para o sistema de
arquivos. Isso não substitui revisão de dependências nem proteção de uma hospedagem.

## Relatar um possível segredo ou uma vulnerabilidade

Não coloque o valor do segredo em uma issue pública. Use o canal privado de relato do GitHub
quando estiver disponível. Caso não esteja, abra somente uma descrição genérica pedindo
um canal privado, sem o conteúdo sensível. Inclua detalhes técnicos apenas nesse canal.

Se um token foi publicado, revogue-o no provedor antes de depender de remoção do arquivo:
apagar a versão atual não remove cópias ou histórico de commits.

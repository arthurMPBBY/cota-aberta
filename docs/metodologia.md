# Metodologia e limites

## Identidade e campos

A identidade preserva o CNPJ do fundo/classe e o `ID_SUBCLASSE`, quando existe.
Aceita o campo legado `CNPJ_FUNDO` e o atual `CNPJ_FUNDO_CLASSE`. Não se deve
juntar subclasses pelo CNPJ. CNPJ é texto; zeros iniciais são preservados.

| Campo CVM | Uso |
| --- | --- |
| DT_COMPTC | Data de competência |
| VL_QUOTA | Variação da cota |
| VL_PATRIM_LIQ | Patrimônio líquido |
| VL_TOTAL | Carteira total; não confundir com patrimônio |
| CAPTC_DIA | Captações do dia |
| RESG_DIA | Resgates pagos no dia |
| NR_COTST | Número de cotistas |

## Rentabilidade

Filtrar o intervalo fechado solicitado; selecionar a primeira e a última cota positiva
finita em datas distintas; calcular `(final / inicial - 1) × 100`, sem arredondamento
intermediário. Mostrar datas e cotas usadas, inclusive quando o intervalo encolhe.

A primeira cota é uma **base**, não o retorno daquele dia. Não há retorno diário
convencional sem uma cota anterior. Lacunas não impedem a razão entre extremos, mas
impedem afirmar que a série é contínua. Patrimônio e fluxos não entram nessa fórmula.

## Fluxos e estoques

Captações e resgates são somados no intervalo solicitado, com ambas as datas inclusivas,
independentemente dos extremos válidos da cota. Dados ausentes tornam a soma parcial.
Sem qualquer valor disponível, o total da variável é ausente, não zero.

Patrimônio e cotistas referem-se ao último informe. Se ausentes nessa data, não se usa
um dia anterior silenciosamente. Cotistas de subclasses não são somados como pessoas únicas.

## Qualidade

- Cotas zero, negativas ou não finitas não formam extremos de rentabilidade.
- Campos ausentes são preservados, sem interpolação ou preenchimento com zero.
- Lacunas de segunda a sexta são aproximações **sem calendário de feriados**.
- Duplicatas conflitantes impedem importação, sem escolher uma linha arbitrariamente.
- Hash, origem e momento de importação rastreiam o arquivo, não atestam exatidão econômica.

Os números são armazenados e calculados em ponto flutuante de dupla precisão. A
apresentação arredonda valores, mas não há arredondamento deliberado entre as etapas
da fórmula. Este MVP não é uma ferramenta de conciliação contábil com precisão decimal
arbitrária.

## Limites econômicos

Retorno passado não prevê futuro. Sem tratar amortizações, distribuições, tributos e
movimentações de cada cotista, a razão entre cotas não representa necessariamente o
retorno total nem o resultado líquido individual. Comparações exigem datas e classes
compatíveis. Este projeto não faz recomendações.

## Referências

- [Catálogo CVM](https://dados.cvm.gov.br/dataset/fi-doc-inf_diario)
- [Metadados](https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/META/meta_inf_diario_fi.txt)

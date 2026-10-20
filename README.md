# ADVPL RPO Recovery

Skill portátil para reconstruir rotinas ADVPL PRW/PRX e classes TLPP compatíveis de um RPO Protheus fornecido pelo usuário. Inclui leitor de índice, leitor de objetos, emissor de código e verificação estática. Não depende de um modelo específico nem de servidor MCP.

Leia [SKILL.md](SKILL.md) para executar e [portabilidade](references/portability.md) para usar em outros agentes. Requer Python 3.11+ e OpenSSL com a cifra necessária. Os binários, RPOs, índices e fontes recuperados são entradas ou saídas externas e não fazem parte deste repositório.

```text
python scripts/rpo.py index --rpo ARQUIVO.rpo --appserver apwinnt.dll --output-dir INDICE
python scripts/rpo.py decompile --rpo ARQUIVO.rpo --index-dir INDICE --source ROTINA.PRW --output-dir SAIDA
python scripts/rpo.py decompile --rpo ARQUIVO.rpo --index-dir INDICE --source ACBALANCEDISTRIBUTEREPOSITORY.TLPP --output-dir SAIDA_TLPP
python scripts/rpo.py verify --artifact-dir SAIDA
python scripts/rpo.py align --artifact-dir SAIDA
python scripts/test_core.py
```

Use uma pasta de saída nova por reconstrução. Os comandos `index` e `decompile` aceitam `--openssl CAMINHO` quando o executável não estiver no PATH.

## Saídas do `decompile`

| Arquivo | Conteúdo |
| --- | --- |
| `ROTINA.reconstruido.prw` | Fonte reconstruído e verificado, compacto (um comando por linha) |
| `ROTINA.alinhado.prw` | Mesmo código com cada comando na linha original gravada no RPO, para debug |
| `alignment.json` | Percentual de comandos na linha exata e lista dos deslocados |
| `verification.json`, `decompilation.json`, `object-parse.json`, `decoded-record.json`, `selected-entry.json` | Evidências da extração e da verificação |

O `decompile` gera o arquivo alinhado automaticamente e informa `aligned_exact_ratio`. O comando `align` refaz só esse passo sobre uma pasta já extraída; o `.reconstruido` verificado não é alterado.

## Debug com o fonte alinhado

O debugger do TDS posiciona o cursor e os breakpoints pelo nome do fonte e pelo número de linha que o RPO grava para cada comando. O `align_lines.py` usa esse mapa (`source_map`) para recolocar cada comando na sua linha:

1. reordena as funções pela linha original (no RPO elas vêm fora de ordem);
2. escreve cada comando na sua linha e completa os espaços com linhas em branco;
3. junta, numa única linha, os comandos que uma macro gerou na mesma linha original: `If/EndIf` vira `IIf(cond, a, Nil)`, `If/Else/EndIf` vira `IIf(cond, a, b)`, comandos seguidos viram `(a, b)` e `Local a` + `Local b` vira `Local a, b`;
4. trata casos especiais: `Do Case` na linha anterior ao primeiro `Case`, `Begin Sequence` + `BEGINTRAN()` revertidos para `Begin Transaction`, linhas `Nil` de ramos vazios removidas, `Static` de arquivo posicionados um a um e funções vindas de `#include` movidas para o fim com comentário.

Para depurar, copie o `.alinhado.prw` para uma pasta separada com o nome original (ex.: `MATA103.PRW`), abra só essa pasta no VSCode e conecte no AppServer do RPO. Não deixe outro arquivo com o mesmo nome no workspace e nunca compile o fonte reconstruído.

## Extensões validadas

Além do perfil original, o leitor e o emissor reconhecem:

| Recurso | Formato no RPO | Emissão | Evidência |
| --- | --- | --- | --- |
| Declaração tipada (`Local x As Tipo`) | tag 500: letra do tipo + nome + inteiro de 4 bytes (sempre 0) | `Local X As Character/Numeric/Logical/Date/Array/Object/Block`; `U` (tipo não reconhecido no fonte, ex.: `As Caracter`, `As Json`) sai sem tipo | CNTA121.PRW (38 declarações, parse completo 608.117/608.117 bytes); MATA103.PRW (`as Block`) |
| Campo sem alias (`Replace x With y`) | tags 62/63 sem operando esquerdo | `_FIELD->CAMPO` | MATA103.PRW (`Replace B3_FILIAL With ...`, `Replace &(cMes) With ...`) |

Letras de tipo não validadas ou inteiro diferente de zero interrompem a emissão com erro, em vez de gerar código não comprovado.

Resultados com o `tttm120.rpo` (AppServer 24.3.1.5):

| Rotina | Funções | Linhas alinhadas | Comandos na linha exata | Observação |
| --- | --- | --- | --- | --- |
| CNTA121.PRW | 217 | 15.647 | 99,99% | 216/216 funções na mesma linha do fonte da mesma versão |
| MATA103.PRW | 174 | 28.588 | 99,97% | Os 5 restantes são declarações `Static` |
| JURXFUN.PRW | 183 | 9.501 | 98,6% | Reconstrução idêntica à validada; sobram cadeias `If/ElseIf` de macro |

O perfil atual é limitado ao build e hash documentados em [formato e evidências](references/format-and-evidence.md). O suporte a TLPP foi validado com uma classe, seis métodos implementados e duas referências sem corpo. Essas referências são preservadas nos metadados; nenhuma implementação ausente é inventada. Consulte [suporte TLPP](references/tlpp.md) para os limites.

Os resultados são reconstruções experimentais: não foram recompilados nem executados no Protheus, e cobertura integral não comprova equivalência funcional. Outros builds, tipos desconhecidos, anotações e formatos de classe não validados exigem análise adicional. Comentários, includes e macros originais não existem no RPO e não são recuperados; o alinhamento reproduz as linhas de código, não o texto original. RPOs gerados por outros builds de AppServer (ex.: 20.3.2.11, descritor `APNSRM0419`) são recusados.

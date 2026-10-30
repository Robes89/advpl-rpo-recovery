---
name: advpl-rpo-recovery
description: Reconstruct ADVPL PRW/PRX routines and supported TLPP classes from a supplied Protheus RPO using a validated AppServer build profile, with offline index decoding and artifact verification. Unknown types and other builds require separate format analysis.
---

# Recuperar ADVPL e TLPP de RPO

Reconstrua uma entrada exata `.PRW`, `.PRX` ou uma classe `.TLPP` compatível de um RPO ou patch `.ptm` fornecido pelo usuário. Use os scripts incluídos, derivados dos leitores do AppServer analisado. Eles não dependem de um modelo específico, servidor MCP ou instalação do REA.

A portabilidade das instruções não amplia o suporte ao formato: os perfis atuais aceitam somente o DLL e os descritores documentados em [formato e evidências](references/format-and-evidence.md). Para TLPP, leia também [suporte TLPP](references/tlpp.md) antes de interpretar os resultados. Não declare suporte universal a RPO ou equivalência do fonte original.

## Execução

Identifique o RPO, a rotina e uma pasta de saída no contexto do usuário. Para gerar um índice novo, obtenha o `apwinnt.dll` compatível fornecido pelo usuário. Reutilize um índice validado existente quando disponível; o comando confere hashes do RPO e do índice. Só pergunte por entradas ausentes que impeçam a execução.

Use Python 3.11+ e OpenSSL com a cifra necessária. Os scripts usam a biblioteca padrão do Python. Descubra os executáveis no ambiente; use `--openssl CAMINHO` quando necessário. Não reutilize caminhos de outras máquinas.

Substitua `SKILL` pelo caminho desta pasta e cite caminhos com espaços conforme o shell:

```text
python SKILL/scripts/rpo.py index --rpo ARQUIVO.rpo --appserver apwinnt.dll --output-dir INDICE
python SKILL/scripts/rpo.py decompile --rpo ARQUIVO.rpo --index-dir INDICE --source ROTINA.PRW --output-dir SAIDA
python SKILL/scripts/rpo.py decompile --rpo ARQUIVO.rpo --index-dir INDICE --source CLASSE.TLPP --output-dir SAIDA_TLPP
python SKILL/scripts/rpo.py verify --artifact-dir SAIDA
python SKILL/scripts/ptm.py list --ptm ARQUIVO.ptm --appserver apwinnt.dll
python SKILL/scripts/ptm.py decompile --ptm ARQUIVO.ptm --appserver apwinnt.dll --source ROTINA.PRW --output-dir SAIDA_PTM
```

Os dois primeiros subcomandos aceitam `--openssl CAMINHO`. Escolha uma pasta de saída nova por reconstrução. `decompile` já verifica os artefatos; `verify` permite repetir essa etapa.

Um patch `.ptm` não precisa de índice: `ptm.py` lê o registro `PATCHINFO` e aceita `--openssl CAMINHO`. Não abra `SIGAPKEY.MAP` nem `SIGATOKEN.MAP`. O nome de relatório SmartView ou TReports, como `backoffice.sv.fin.bankstatement`, corresponde à entrada `.TLPP` de mesmo nome; os `.TRP`, `.TVIEW` e `.TRES` associados são recursos e não são reconstruídos.

O nome da entrada é exato: não confunda variantes como `JURXFUN`, `JURXFUNB` e `JURXFUNC`. O comando não executa o RPO, carrega o DLL nem inicia o AppServer. Não substitua essa leitura por chamadas ao debugger, compilação ou gravação no repositório.

## Falhas e interpretação

- Hash/build incompatível: informe o perfil não suportado. Para estendê-lo, derive os leitores dos novos binários e símbolos; não desative conferências.
- Tipo ou semântica desconhecida: preserve o diagnóstico e os objetos parciais. Não pule bytes, invente corpos nem transforme nós desconhecidos em comentários para anunciar recuperação completa.
- Em TLPP, referências com corpo ausente ficam em `bodyless_references`. Não invente assinaturas ou implementações, nem afirme sua origem sem evidência. Preserve chamadas à superclasse indicadas no registro.
- Falha de padding, checksum, limite ou referência: interrompa e relate a etapa. Não divulgue chaves, IVs nem a linha de comando interna da decifragem.
- OpenSSL indisponível ou sem a cifra: informe o requisito concreto e continue apenas as etapas independentes. A skill não instala dependências automaticamente.

## Entrega

Entregue o link para `ROTINA.reconstruido.prw` ou `CLASSE.reconstruido.tlpp`, quantidade de funções/métodos e linhas, resultado de `verification.json` e a validação funcional pendente. Para TLPP, informe também quantas referências não têm corpo. Mantenha junto ao fonte `selected-entry.json`, `decoded-record.json`, `object-parse.json`, `decompilation.json`, `verification.json` e o registro serializado.

Cobertura de objetos significa que o emissor percorreu a árvore, não que o Protheus aceita o fonte ou que seu comportamento é equivalente. Comentários, includes, macros do pré-processador e formatação originais não são recuperados. Preserve chamadas de recursos de idioma. Não atribua artefatos locais a ferramentas REA que não foram executadas.

Para instalar em outro agente/modelo, leia [portabilidade](references/portability.md). Para testar o código sem artefatos proprietários, execute `python SKILL/scripts/test_core.py`.

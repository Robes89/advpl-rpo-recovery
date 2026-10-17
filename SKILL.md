---
name: advpl-rpo-recovery
description: Reconstruct ADVPL PRW/PRX routines from a supplied Protheus RPO using a validated AppServer build profile, with offline index decoding and artifact verification. Use for RPO recovery; TLPP and other builds need separate format analysis.
---

# Recuperar ADVPL de RPO

Reconstrua uma entrada exata `.PRW` ou `.PRX` de um RPO fornecido pelo usu?rio. Use os scripts inclu?dos, que implementam a leitura e emiss?o experimentais derivadas do AppServer analisado. Eles n?o dependem de um modelo espec?fico, servidor MCP ou instala??o do REA.

A portabilidade das instru??es n?o amplia o suporte ao formato: o perfil atual aceita somente o DLL e o descritor documentados em [formato e evid?ncias](references/format-and-evidence.md). N?o declare suporte universal a RPO, TLPP ou equival?ncia do fonte original.

## Execu??o

Identifique o RPO, a rotina e uma pasta de sa?da no contexto do usu?rio. Para gerar um ?ndice novo, obtenha o `apwinnt.dll` compat?vel fornecido pelo usu?rio. Reutilize um ?ndice validado existente quando dispon?vel; o comando confere hashes do RPO e do ?ndice. S? pergunte por entradas ausentes que impe?am a execu??o.

Use Python 3.11 ou superior e um OpenSSL que disponibilize a cifra necess?ria. Os scripts usam a biblioteca padr?o do Python. Descubra os execut?veis no ambiente; use `--openssl CAMINHO` quando OpenSSL n?o estiver no PATH. N?o reutilize caminhos de m?quinas anteriores.

Execute os comandos a partir de qualquer diret?rio, substituindo `SKILL` pelo caminho desta pasta:

```text
python SKILL/scripts/rpo.py index --rpo ARQUIVO.rpo --appserver apwinnt.dll --output-dir INDICE
python SKILL/scripts/rpo.py decompile --rpo ARQUIVO.rpo --index-dir INDICE --source ROTINA.PRW --output-dir SAIDA
python SKILL/scripts/rpo.py verify --artifact-dir SAIDA
```

Os dois primeiros comandos aceitam `--openssl CAMINHO`. Cite caminhos com espa?os conforme o shell. Escolha uma pasta de sa?da nova por reconstru??o. `decompile` j? executa a verifica??o est?tica; `verify` permite repeti-la posteriormente.

O nome da entrada ? exato, sem confundir variantes como `JURXFUN`, `JURXFUNB` e `JURXFUNC`. O comando n?o executa o RPO, carrega o DLL nem inicia o AppServer. N?o substitua essa leitura por chamadas ao debugger, compila??o ou grava??o no reposit?rio.

## Falhas e interpreta??o

- Hash/build incompat?vel: informe o perfil n?o suportado. Para estend?-lo, leia a refer?ncia de formato e derive o leitor a partir dos novos bin?rios e s?mbolos; n?o desative as confer?ncias.
- Tipo ou sem?ntica desconhecida: preserve o diagn?stico e os objetos parciais. N?o pule bytes, invente corpos, transforme n?s em coment?rios nem anuncie uma recupera??o completa.
- Falha de padding, checksum, limite ou refer?ncia: interrompa a emiss?o e relate o campo/etapa. N?o divulgue chaves, IVs nem a linha de comando interna de decifragem.
- OpenSSL indispon?vel ou sem a cifra: informe o requisito concreto e continue apenas as etapas que n?o dependam dele. A skill n?o instala depend?ncias automaticamente.

## Entrega

Entregue um link para `ROTINA.reconstruido.prw`, quantidade de fun??es e linhas, resultado de `verification.json` e a limita??o de recompila??o/valida??o funcional pendente. Mantenha junto ao fonte `selected-entry.json`, `decoded-record.json`, `object-parse.json`, `decompilation.json`, `verification.json` e o registro serializado.

A cobertura de todos os objetos significa que o emissor percorreu a ?rvore, n?o que o Protheus aceita o fonte ou que seu comportamento ? equivalente. Coment?rios, includes, macros do pr?-processador e formata??o originais n?o s?o recuperados. Preserve as chamadas de recursos de idioma. N?o atribua os artefatos locais a ferramentas REA que n?o foram executadas.

Para transportar ou instalar em outro agente/modelo, leia [portabilidade](references/portability.md). Para verificar o c?digo da skill sem artefatos propriet?rios, execute `python SKILL/scripts/test_core.py`.

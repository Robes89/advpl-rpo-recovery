# Perfil validado e evidências

Este leitor é derivado da análise estática do AppServer fornecido durante a recuperação de FISXAPUR.PRX, JURXFUN.PRW e ACBALANCEDISTRIBUTEREPOSITORY.TLPP. Usa scripts locais; não implementa um novo servidor REA e não depende do descompilador de um provedor externo.

## Limites do perfil

| Item | Valor observado |
| --- | --- |
| Imagem | PE32+ AMD64 `apwinnt.dll`, fornecida separadamente |
| SHA-256 da imagem | `850abee5b279ce7487eab3836a1adcbacfb5643120f962a8a399fdc979317d83` |
| Diagnóstico do pacote analisado | AppServer 24.3.1.5 REL WITH DEBUG |
| Formato do descritor RPO | `APNSRM0421` |
| Build gravado no descritor | `24.3.0.0_ts03` |
| Janela do trailer | últimos `0x5000` bytes |
| Carrier de material público | RVA `0x311b990`; somente a parte pública é lida |

O número do build no diagnóstico não substitui o hash da imagem. O script rejeita DLLs diferentes e descritores fora do perfil. Isso permite testar outros RPOs desse formato, mas não comprova que seus tipos compilados estejam todos cobertos. O suporte TLPP é limitado às estruturas descritas em [suporte TLPP](tlpp.md).

## Caminho de leitura

O descritor é recuperado por RSA pública e validado pelo padding PKCS#1 tipo 1. A chave pública vem do carrier DWORD no DLL; os bytes privados existentes no mesmo carrier não são extraídos. O descritor fornece os limites do índice cifrado; padding, checksum zlib, tamanho e consumo integral são conferidos.

Neste build, `tRandomKey::GetKey/GetIv` calculam deslocamentos mas retornam o início dos buffers (RVAs `0xabdc60` e `0xabde20`). Por isso os scripts usam os primeiros 16 bytes disponíveis dos bancos do trailer. Não generalize esse comportamento para outros builds.

Tabela de cifras validada nos inicializadores nativos: índices 0/1 AES-128 CBC/ECB; 2/3 ARIA-128 CBC/ECB; 4/5 SM4 CBC/ECB; 6/7 Camellia-128 CBC/ECB. Índice: `field_b4 % 8`; registro: `field_38 % 8`. Os nomes dos campos desconhecidos preservam seus offsets nativos, sem atribuição semântica inventada.

As entradas do índice têm nome NUL, data DelphiTDateTime, offset de 32 bits com escape -1 para 64 bits, oito campos de 32 bits e um byte de estado. Os intervalos de ciphertext são conferidos contra o corpo do RPO. As datas gravadas não estabelecem um fuso horário.

## Objetos e emissão

`ReadInstrVar` (`0x42e0b0`) lê uma tag de 7 bits; o bit alto acrescenta linha U16; a tag 106 é escape para um tipo de 32 bits. Listas, nós, corpos de função e pools de constantes têm leitores específicos em `object_reader.py`; não há busca heurística para ultrapassar um tipo desconhecido.

Funções têm corpo e pool de constantes delimitados por offsets/tamanhos. Referências de tipo 121 indexam a tabela da função envolvente durante emissão de codeblocks. Tipos de função F/f, T/t, I, E e M produzem Function, Static Function, Init Function, Exit Function e Main Function conforme o tradutor nativo; a tag 109 isolada não comprova User Function.

Casos relevantes já conferidos: comparação 0=`=`, 1=`==`, 2=`<`, 3=`<=`, 4=`>`, 5=`>=`, 6=`<>`; atribuição encadeada mantém a ordem dos alvos; tipo 32 é `M->`; tipo 115 é `JsonObject():New()`; tipo 73 aceita `Break(valor)` dentro de codeblock. Aliases literais e variáveis recebem sintaxe contextual. O emissor preserva os bytes dos literais com `Chr(n)` quando necessário.

## Validação e extensão

A portabilidade do pacote foi verificada gerando um índice novo de 149.412 entradas. A versão atual reproduz byte a byte as três reconstruções já verificadas:

| Rotina | Funções | Linhas | SHA-256 do fonte |
| --- | --- | --- | --- |
| FISXAPUR.PRX | 92 | 7.602 | `cff9c8bd96bea437026a3dce69874a2561c54967cbfa43ce67906de02d740de2` |
| JURXFUN.PRW | 183 | 6.107 | `f12b1ea1ab817b50d2d7c4b8642e5bf3c62c438beacf2adc563ff54a2a50a21e` |
| ACBALANCEDISTRIBUTEREPOSITORY.TLPP | 6 métodos | 114 | `b7410aef6b10a72e423955d95077c0301a4ccef9fb761cd04e27b6940a7f2d7b` |

Esses testes não incluem compilação nem execução Protheus. A referência de origem é a análise local dos leitores `load`, do despacho e de `transAdvpl`, com PDB correspondente e Capstone/DbgHelp. Os binários e ASM proprietários não são distribuídos no pacote.

Para um novo build ou tipo, obtenha os binários/símbolos correspondentes e derive a ordem exata de campos e a semântica da emissão antes de alterar o leitor. Acrescente um perfil separado com hash explícito e verificações reais. Registre offsets, intervalos desmontados, limites de cobertura e testes do novo caso. Não use a correspondência do nome da classe como prova suficiente do layout.

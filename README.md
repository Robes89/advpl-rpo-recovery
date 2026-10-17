# ADVPL RPO Recovery

Skill portátil para reconstruir rotinas ADVPL PRW/PRX e classes TLPP compatíveis de um RPO Protheus fornecido pelo usuário. Inclui leitor de índice, leitor de objetos, emissor de código e verificação estática. Não depende de um modelo específico nem de servidor MCP.

Leia [SKILL.md](SKILL.md) para executar e [portabilidade](references/portability.md) para usar em outros agentes. Requer Python 3.11+ e OpenSSL com a cifra necessária. Os binários, RPOs, índices e fontes recuperados são entradas ou saídas externas e não fazem parte deste repositório.

```text
python scripts/rpo.py index --rpo ARQUIVO.rpo --appserver apwinnt.dll --output-dir INDICE
python scripts/rpo.py decompile --rpo ARQUIVO.rpo --index-dir INDICE --source ROTINA.PRW --output-dir SAIDA
python scripts/rpo.py decompile --rpo ARQUIVO.rpo --index-dir INDICE --source ACBALANCEDISTRIBUTEREPOSITORY.TLPP --output-dir SAIDA_TLPP
python scripts/rpo.py verify --artifact-dir SAIDA
python scripts/test_core.py
```

Use uma pasta de saída nova por reconstrução. Os comandos `index` e `decompile` aceitam `--openssl CAMINHO` quando o executável não estiver no PATH.

O perfil atual é limitado ao build e hash documentados em [formato e evidências](references/format-and-evidence.md). O suporte a TLPP foi validado com uma classe, seis métodos implementados e duas referências sem corpo. Essas referências são preservadas nos metadados; nenhuma implementação ausente é inventada. Consulte [suporte TLPP](references/tlpp.md) para os limites.

Os resultados são reconstruções experimentais: não foram recompilados nem executados no Protheus, e cobertura integral não comprova equivalência funcional. Outros builds, tipos desconhecidos, anotações e formatos de classe não validados exigem análise adicional.

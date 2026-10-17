# ADVPL RPO Recovery

Skill port?til para reconstruir rotinas ADVPL PRW/PRX de um RPO Protheus fornecido pelo usu?rio. Inclui leitor de ?ndice, leitor de objetos, emissor ADVPL e verifica??o est?tica. N?o depende de um modelo espec?fico nem de servidor MCP.

Leia [SKILL.md](SKILL.md) para executar e [portabilidade](references/portability.md) para usar em outros agentes. Requer Python 3.11+ e OpenSSL com a cifra necess?ria. Os bin?rios, RPOs e ?ndices s?o entradas externas e n?o fazem parte deste reposit?rio.

```text
python scripts/rpo.py index --rpo ARQUIVO.rpo --appserver apwinnt.dll --output-dir INDICE
python scripts/rpo.py decompile --rpo ARQUIVO.rpo --index-dir INDICE --source ROTINA.PRW --output-dir SAIDA
python scripts/rpo.py verify --artifact-dir SAIDA
python scripts/test_core.py
```

O perfil atual ? limitado ao build e hash documentados em [formato e evid?ncias](references/format-and-evidence.md). TLPP e outros builds precisam de an?lise adicional. Os resultados s?o reconstru??es experimentais: n?o foram recompilados nem executados no Protheus, e cobertura integral n?o comprova equival?ncia funcional.

# Usar em outro modelo ou agente

A pasta completa contém instruções Markdown e scripts Python comuns. Um modelo com acesso a arquivos e execução de comandos pode ler `SKILL.md` e seguir o mesmo procedimento. O reconhecimento automático da skill depende do aplicativo que hospeda o modelo. Um chat sem acesso a arquivos/execução pode orientar o operador, mas não executar a recuperação sozinho.

Para agentes que reconhecem pastas de skills, copie `advpl-rpo-recovery` para a pasta de skills suportada pelo aplicativo. Preserve `scripts/` e `references/`. O arquivo `agents/openai.yaml` é metadado opcional de interface para Codex; outros aplicativos podem ignorá-lo. No Codex, a localização padrão desta instalação é `~/.codex/skills/advpl-rpo-recovery`; uma nova sessão pode ser necessária para descoberta.

Para uso manual em qualquer agente com ferramentas, indique o caminho completo e peça:

```text
Leia /caminho/advpl-rpo-recovery/SKILL.md e use seus scripts para reconstruir
JURXFUN.PRW do RPO /caminho/repositorio.rpo. O índice validado está em
/caminho/indice e a saída deve ir para /caminho/saida-nova.
```

Se o índice ainda não existir, forneça também o `apwinnt.dll` compatível e uma pasta para o índice. Não basta fornecer o nome do modelo ou o nome da rotina. Não é necessário um servidor MCP REA para executar estes scripts.

Pré-requisitos: Python 3.11+ e OpenSSL com AES, ARIA, SM4 e/ou Camellia conforme a cifra escolhida no registro. Não há pacote Python externo obrigatório. Em Windows, OpenSSL fornecido pelo Git pode ser indicado explicitamente; em outros sistemas, use o executável existente. A disponibilidade das cifras depende do OpenSSL instalado.

O pacote distribuível não contém RPO, DLL, PDB, código reconstruído, índices ou material de chave do usuário. Esses arquivos permanecem como entradas externas. O pacote também não transporta instalações de Python/OpenSSL nem configurações do agente.

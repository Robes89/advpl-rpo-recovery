# Suporte TLPP validado

O comando `decompile` aceita `.TLPP` e seleciona leitores/emissores próprios. O perfil de DLL e descritor continua o mesmo documentado em [formato e evidências](format-and-evidence.md); isso não estabelece suporte a todo TLPP.

A validação real usou ACBALANCEDISTRIBUTEREPOSITORY.TLPP: 6.760 bytes de objetos, 672 nós tipados, uma classe derivada de FWADAPTERBASEV2, seis métodos implementados, 114 linhas geradas e duas referências sem corpo. Não houve compilação ou execução Protheus.

O leitor acrescenta interfaces de classe, campos do tipo Object, métodos de tag 68, namespaces e parâmetros tipados. Classes com anotações e dados com anotações interrompem a leitura. A emissão rejeita interfaces implementadas, flags de método, tipos de dados e conteúdos adicionais de programa ainda não validados.

Referências sem corpo são registradas em `decompilation.json:bodyless_references`, sem declarar assinaturas ou inventar implementações. No caso validado, LISTBRANCHES e LOGERRORPROC têm corpo de tamanho zero; sua origem não pode ser concluída somente desse registro.

A chamada de método com marcador de herança é emitida como `Super:METODO(...)` no formato validado, evitando convertê-la em `SELF:METODO(...)`. Evidência: tMethodCall::run testa o campo 0x88 em RVA 0x410aa4 e chama tClassInterface::ParentCls em 0x410ae6.

Os formatos foram derivados de tClassInterface::load (0x3b35a0), tClassData::load (0x3b2350) e tInterMethod::load (0x3b5110). O runtime distingue escopo zero e os valores 8/4 associados a PRIVATE/PROTECTED. Os binários e os ASM do usuário permanecem fora deste repositório.

Para ampliar o suporte, confirme os novos campos e sua semântica em binários/símbolos correspondentes, acrescente verificações e teste um artefato real. Não ultrapasse estruturas desconhecidas por busca de strings ou ajustes heurísticos.

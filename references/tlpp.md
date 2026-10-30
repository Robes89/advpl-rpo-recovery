# Suporte TLPP validado

O comando `decompile` aceita `.TLPP` e seleciona leitores/emissores próprios. O perfil de DLL e descritor continua o mesmo documentado em [formato e evidências](format-and-evidence.md); isso não estabelece suporte a todo TLPP.

A validação real usou ACBALANCEDISTRIBUTEREPOSITORY.TLPP: 6.760 bytes de objetos, 672 nós tipados, uma classe derivada de FWADAPTERBASEV2, seis métodos implementados, 114 linhas geradas e duas referências sem corpo. Não houve compilação ou execução Protheus.

O leitor acrescenta interfaces de classe, campos tipados, métodos de tag 68, namespaces, parâmetros tipados, anotações de classe e literais JSON. Dados com anotações interrompem a leitura. A emissão rejeita interfaces implementadas, flags de método fora de 0/4/8, tipos de dados e conteúdos adicionais de programa ainda não validados.

Referências sem corpo são registradas em `decompilation.json:bodyless_references`, sem declarar assinaturas ou inventar implementações. No caso validado, LISTBRANCHES e LOGERRORPROC têm corpo de tamanho zero; sua origem não pode ser concluída somente desse registro.

A chamada de método com marcador de herança é emitida como `Super:METODO(...)` no formato validado, evitando convertê-la em `SELF:METODO(...)`. Evidência: tMethodCall::run testa o campo 0x88 em RVA 0x410aa4 e chama tClassInterface::ParentCls em 0x410ae6.

Os formatos foram derivados de tClassInterface::load (0x3b35a0), tClassData::load (0x3b2350) e tInterMethod::load (0x3b5110). O runtime distingue escopo zero e os valores 8/4 associados a PRIVATE/PROTECTED. Os binários e os ASM do usuário permanecem fora deste repositório.

## Extensões deduzidas do registro

BACKOFFICE.SV.FIN.BANKSTATEMENT.TLPP validou uma classe com anotação, 24 campos e 13 métodos, com 18.297 de 18.297 bytes consumidos, 1.752 objetos emitidos e nenhuma referência sem corpo. Não houve compilação ou execução Protheus.

Estas extensões não foram derivadas dos leitores nativos: a evidência é o consumo exato do registro e as fronteiras de corpo de cada método.

- Anotação de classe: mesmo layout da anotação de função, com nome e pares chave/constante.
- Literal JSON: tipo 4009, com escape 106. Cada par traz objeto opcional, valor, lista opcional e chave. O primeiro par exige objeto de tipo 115 e lista de tipo 2 só com pares. Layout diferente interrompe a leitura. A sintaxe `{"CHAVE": valor}` é inferida.
- Campos e métodos: os escopos 0/4/8 de método seguem o mapa já confirmado para campos. O tipo de retorno vem da letra da função e coincidiu com o valor retornado nos métodos numérico e data, mas é inferido.

No `.alinhado.tlpp` a linha `Namespace` não é posicionada, as declarações de método saem espalhadas e `EndClass` vai para o fim. Use o `.reconstruido.tlpp` para ler a declaração da classe.

Para ampliar o suporte, confirme os novos campos e sua semântica em binários/símbolos correspondentes, acrescente verificações e teste um artefato real. Não ultrapasse estruturas desconhecidas por busca de strings ou ajustes heurísticos.

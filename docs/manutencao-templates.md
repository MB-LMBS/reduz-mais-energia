# Manutenção de templates de mensagem — WhatsApp (Meta Cloud API)

Registo das execuções da manutenção diária dos templates `mensagem_*` usados
por `agent/motivacao.py`. Não conter tokens nem segredos neste ficheiro.

---

## 17/08/2026

### Estado encontrado no início desta execução

Listagem completa de `mensagem_*` (30 templates):

- `mensagem_manha_01` a `12` e `19` — **APPROVED**. (13-18 e 20-24 não existiam — tinham
  sido apagados por erros de acentuação, como já era sabido.)
- `mensagem_fimdia_11` a `20` (10 templates) — **REJECTED**, motivo `INVALID_FORMAT`
  (bug do campo `example` em falta, já corrigido em `criar_template()`).
- `mensagem_sexta_07` a `12` (6 templates) — **REJECTED**, motivo `INVALID_FORMAT`, mesmo bug.
- `mensagem_sexta_urgente_01` — também **REJECTED**, `INVALID_FORMAT` (mesmo bug; não estava
  referido no trabalho pendente conhecido, mas tem o mesmo problema).

Confirmação do impacto: como `fim_dia`/`sexta` não tinham **nenhum** template aprovado,
`_obter_pool()` caía sempre na `POOL_RESERVA` — que também apontava só para nomes
`REJECTED` (bug adicional, ver secção "Alteração de código" abaixo). Ou seja, as
mensagens das 19h30 (Segunda a Sexta) muito provavelmente **não estavam a ser
entregues** desde que este bug apareceu.

### Trabalho realizado

**1. `mensagem_manha_13` a `18` e `20` a `24`** (11 templates, nomes exatos pedidos —
o índice `19` já estava ocupado e aprovado, por isso não foi tocado): geradas 11
mensagens novas de início de dia, tom caloroso, foco em esforço/resiliência/
aprendizagem/espírito de equipa, sem menções a resultados fracos ou comparações,
`{{1}}` sempre rodeado de texto fixo, 124-162 caracteres, `example: {"body_text": [["Luis"]]}`
incluído em todas. **Resultado: todas as 11 ficaram `APPROVED`.**

**2. `mensagem_fimdia_21` a `30`** (10 templates, substitutos dos `11`-`20` rejeitados,
mesma dimensão de reserva): geradas 10 mensagens de fecho de dia (Segunda a Quinta),
tom de reconhecimento e agradecimento pelo esforço do dia, saudação "Boa tarde"
(mantendo a convenção já usada, ver nota no código sobre a versão "Boa noite" ter
sido apagada por estar errada), todas com `example`. **Resultado: todas as 10
ficaram `APPROVED`.**

**3. `mensagem_sexta_13` a `18`** (6 templates, substitutos dos `07`-`12` rejeitados,
mesma dimensão de reserva; `mensagem_sexta_urgente_01` não foi substituído — parece
ter sido um template avulso fora do ciclo normal, não uma das 6 mensagens em rotação):
geradas 6 mensagens de fecho de semana, reconhecimento da semana e incentivo a
aproveitar o fim de semana, todas com `example`. **Resultado: `13`, `14`, `15`
ficaram `APPROVED`; `16`, `17`, `18` ficaram `PENDING` (revisão da Meta ainda a
decorrer no momento da escrita deste registo — confirmar no próximo dia).**

Os templates antigos `REJECTED` (`fimdia_11-20`, `sexta_07-12`, `sexta_urgente_01`)
**não foram apagados** — ficam para uma limpeza numa execução futura, depois de
confirmado que os substitutos estão todos `APPROVED` (`sexta_16-18` ainda por
confirmar) e a rotação a funcionar bem.

**4. Verificação de rotina (templates `APPROVED` com erros de português):**
revendo `mensagem_manha_01` a `12`, encontrei um padrão de acentuação em falta em
**11 dos 12** (só o `07` está correto — na verdade `mensagem_manha_19` já é uma
cópia corrigida do `07`, aprovada antes de hoje, provavelmente de uma tentativa
anterior de corrigir isto mensagem a mensagem). Erros principais: confusão
recorrente entre "e" (conjunção) e "é" (verbo ser — ex: "Hoje e um bom dia" em vez
de "Hoje é um bom dia"), e acentos/cedilhas em falta ("esta"→"está", "nao"→"não",
"esforco"→"esforço", "comecar"→"começar", "confianca"→"confiança", etc.).

Segui o mesmo padrão já usado para o `07`→`19`: criei versões corrigidas com novo
nome, só com correção de acentuação (sem alterar o conteúdo/estrutura da frase),
**sem apagar os originais**:

| Novo nome            | Origem              |
|-----------------------|----------------------|
| `mensagem_manha_25`  | `mensagem_manha_01` |
| `mensagem_manha_26`  | `mensagem_manha_02` |
| `mensagem_manha_27`  | `mensagem_manha_03` |
| `mensagem_manha_28`  | `mensagem_manha_04` |
| `mensagem_manha_29`  | `mensagem_manha_05` |
| `mensagem_manha_30`  | `mensagem_manha_06` |
| `mensagem_manha_31`  | `mensagem_manha_08` |
| `mensagem_manha_32`  | `mensagem_manha_09` |
| `mensagem_manha_33`  | `mensagem_manha_10` |
| `mensagem_manha_34`  | `mensagem_manha_11` |
| `mensagem_manha_35`  | `mensagem_manha_12` |

**Resultado: as 11 foram aceites para revisão (`PENDING`) — confirmar estado no
próximo dia.** Os originais `01-06` e `08-12` ficam ativos até os substitutos
estarem `APPROVED`, conforme a regra de nunca deixar a reserva sem templates
ativos.

Nota técnica: uma tentativa isolada de submeter `mensagem_manha_34` devolveu
`400 — "Os conteúdos neste idioma já existem"` (`error_subcode 2388024`), por a
Meta considerar o texto demasiado parecido com um template já existente na mesma
língua — mas a submissão tinha na verdade sido aceite momentos antes (confirmado
pela listagem final, que mostra `mensagem_manha_34` como `PENDING`). Registo isto
para o caso de aparecer de novo: se a Meta recusar por duplicação e o template já
existir na listagem, não é um problema — é só uma resposta tardia/concorrente a
uma submissão que já tinha sido aceite.

### Alteração de código

`agent/motivacao.py` — `POOL_RESERVA` (reserva de segurança usada só se a
consulta à Meta falhar): apontava para `mensagem_fimdia_11-20` e
`mensagem_sexta_07-12`, que estavam **todos `REJECTED`** — ou seja, se a API da
Meta estivesse em baixo no momento do envio, o sistema tentaria enviar templates
inválidos e falharia por completo em vez de usar a reserva. Atualizado para
apontar para os substitutos aprovados: `mensagem_fimdia_21-30` e
`mensagem_sexta_13-15` (só os 3 já confirmados `APPROVED` — os `16-18` podem ser
adicionados à reserva depois de confirmados). `manha` também atualizado para
incluir `01-24` (todos já `APPROVED`).

Nenhuma alteração feita a `agent/meta_templates.py` — a correção do campo
`example` já estava feita antes desta execução.

### Pendente para a próxima execução

1. Confirmar que `mensagem_sexta_16`, `17`, `18` passaram a `APPROVED` (estavam
   `PENDING` no fim desta execução). Se alguma tiver sido `REJECTED`, gerar
   substituto.
2. Confirmar que as 11 correções de acentuação `mensagem_manha_25-35` passaram a
   `APPROVED`. Se alguma tiver sido `REJECTED` (ex: por duplicação de conteúdo
   com o original, como quase aconteceu com o `34`), avaliar se vale a pena
   reformular ligeiramente o texto para escapar à deteção de duplicados da Meta.
3. **Só depois de 1 e 2 confirmados**: apagar os templates antigos já substituídos
   e aprovados — `mensagem_fimdia_11-20`, `mensagem_sexta_07-12`,
   `mensagem_sexta_urgente_01`, e (quando `25-35` estiverem aprovados)
   `mensagem_manha_01-06` e `08-12`. Nunca apagar sem confirmar primeiro que o
   substituto está `APPROVED`.
4. Continuar a verificação de rotina de acentuação a `mensagem_manha_13-24`
   (geradas nesta execução — revistas com cuidado, mas vale a pena confirmar
   depois de aprovadas) e às restantes mensagens quando forem geradas.
5. `mensagem_sexta_urgente_01` ficou por perceber — não é uma das 6 mensagens em
   rotação normal (prefixo `mensagem_sexta_` mas sufixo `_urgente_01`, fora do
   padrão numérico usado por `proximo_indice_livre()`/`_obter_pool()`). Não sei
   para que serve nem se está a ser referenciado nalgum código fora deste
   repositório — não mexi nele. Se não for necessário, considerar apagar depois
   de confirmar que não é usado.

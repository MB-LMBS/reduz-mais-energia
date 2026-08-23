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

---

## 18/08/2026

### Estado encontrado no início desta execução

Listagem completa de `mensagem_*` (68 templates). Trabalho pendente de 17/08 — confirmado resolvido:

- `mensagem_sexta_16`, `17`, `18` — passaram de `PENDING` a **APPROVED**.
- `mensagem_manha_25` a `35` (correções de acentuação) — todas **APPROVED**.
- `mensagem_manha_13` a `24` — já existiam (criadas em 17/08) e estão **APPROVED**.
- `mensagem_fimdia_21` a `30` e `mensagem_sexta_13` a `18` — **APPROVED** (substitutos
  dos rejeitados). Ou seja, as mensagens das 19h30 (Segunda a Sexta) já devem estar
  a ser entregues normalmente desde a execução anterior.
- `mensagem_fimdia_11-20`, `mensagem_sexta_07-12` — continuavam **REJECTED**
  (`INVALID_FORMAT`), já substituídos e não usados em código.
- `mensagem_sexta_urgente_01` — continua **REJECTED** (`INVALID_FORMAT`), propósito
  ainda por esclarecer (ver ponto 5 do registo de 17/08).

Revi o texto de todos os templates `APPROVED`: `mensagem_manha_01-06` e `08-12`
(originais, ainda por apagar) continuavam com os erros de acentuação já
identificados ("e"/"é", "esta"/"está", "esforco"/"esforço", etc.). Todos os
outros (`manha_07`, `13-35`, `fimdia_21-30`, `sexta_13-18`) estão com a
acentuação correta — nenhuma correção nova necessária hoje.

### Trabalho realizado

Com os dois pontos pendentes de 17/08 confirmados (`sexta_16-18` e `manha_25-35`
ambos `APPROVED`), procedi à limpeza combinada anteriormente:

**1. Apagados 27 templates** (todos confirmados `200 {"success":true}` na API):
- `mensagem_fimdia_11` a `20` (10) — `REJECTED`, substituídos por `21-30`.
- `mensagem_sexta_07` a `12` (6) — `REJECTED`, substituídos por `13-18`.
- `mensagem_manha_01-06` e `08-12` (11) — `APPROVED` mas com acentuação errada,
  substituídos por `manha_25-35` (cópias corrigidas). `manha_07` não foi tocado
  (já estava correto) nem `manha_19` (cópia corrigida do `07`, já aprovada antes).

`mensagem_sexta_urgente_01` **não foi apagado** — continua sem se perceber a
função nem se está referenciado fora deste repositório; mantenho a cautela do
registo anterior.

Confirmação final: restam 41 templates `mensagem_*`, todos `APPROVED` exceto o
`sexta_urgente_01` (`REJECTED`, deixado de propósito).

**2. Adicionada `apagar_template()` a `agent/meta_templates.py`** — não existia
nenhuma função para apagar templates (só criar/listar), e a limpeza acima (e as
futuras, quando a próxima geração de substitutos for aprovada) precisa dela.
Faz `DELETE` ao mesmo endpoint dos templates, pelo nome.

**3. Atualizado `POOL_RESERVA` em `agent/motivacao.py`**:
- `manha`: deixou de incluir `01-06` e `08-12` (agora apagados); passa a ser
  `07` + `13-24` + `25-35` (24 templates, todos ativos).
- `sexta`: passou de `[13,14,15]` para `[13,14,15,16,17,18]`, agora que os
  três últimos estão confirmados `APPROVED`.
- `fim_dia`: sem alteração (já apontava para `21-30`, todos `APPROVED`).

Sintaxe de ambos os ficheiros verificada (`ast.parse`) antes do commit.

### Pendente para a próxima execução

1. Continuar a rever `mensagem_manha_13-35`, `mensagem_fimdia_21-30` e
   `mensagem_sexta_13-18` por acentuação/erros — revistas hoje sem problemas,
   mas vale a pena confirmar de novo com olhos frescos.
2. `mensagem_sexta_urgente_01` continua por esclarecer — ver ponto 5 do registo
   de 17/08 (ainda válido, nada de novo a acrescentar).
3. Nenhum trabalho pendente conhecido do bug do campo `example` — todos os
   templates ativos já o incluem.

---

## 23/08/2026

Nota: não há registos de execuções entre 19 e 22/08 — esta manutenção diária
parece não ter corrido nesses dias (sem commits neste ficheiro nesse intervalo).
Nada indica perda de dados; só um espaço sem execução.

### Estado encontrado no início desta execução

Listagem completa via GET `message_templates` (fields
`name,status,rejected_reason,components,language`) — 41 templates `mensagem_*`:

- **Trabalho pendente de 17/08 (prioridade máxima do enunciado da tarefa) —
  confirmado totalmente resolvido**, sem necessidade de qualquer ação:
  - `mensagem_manha_13` a `24` (10 templates pedidos para recriar) — já existiam
    (criados em 17/08) e estão todos **APPROVED**, todos com `example`.
  - `mensagem_fimdia_21-30` e `mensagem_sexta_13-18` (substitutos dos que
    estavam `REJECTED` por `INVALID_FORMAT`) — todos **APPROVED**. As mensagens
    das 19h30 (Seg-Sex) devem estar a ser entregues normalmente.
- `mensagem_sexta_urgente_01` — continua **REJECTED** (`INVALID_FORMAT`, sem
  `example`), propósito por esclarecer (ver ponto 5 do registo de 17/08, ainda
  válido). Não referenciado em nenhum código deste repositório (confirmado por
  pesquisa de texto a "urgente" e a "manha_07" — só aparecem neste ficheiro).
  Mantida a mesma cautela dos registos anteriores: não apagado.

### Trabalho realizado

**Verificação de rotina de acentuação (ponto 4 da tarefa):** ao rever o texto
de todos os `APPROVED`, encontrei um erro que os registos de 17/08 e 18/08
não detetaram corretamente: `mensagem_manha_07` continha o texto original
com erros ("a consistencia e que faz a diferenca todos os dias" — em falta os
acentos em "consistência" e "diferença", e "e" por "é"). O registo de 18/08
tinha concluído por engano que "07 está correto", quando na verdade
`mensagem_manha_19` é que já era a cópia corrigida ("a consistência é que faz
a diferença todos os dias"), aprovada há vários dias — e o `07` original,
com o erro, continuava ativo na rotação (`POOL_RESERVA` incluía-o
explicitamente, e a consulta dinâmica à Meta também o incluía por estar
`APPROVED`). Ou seja, a equipa comercial esteve a receber esta mensagem com
erros de português sempre que o ciclo caía no `07`.

Como já existia um substituto correto e `APPROVED` há muito tempo (`19`, com
exatamente o mesmo texto senão o erro), não submeti um novo template — teria
sido rejeitado por duplicação de conteúdo (o mesmo erro `error_subcode
2388024` já visto no registo de 17/08). Em vez disso, apaguei diretamente
`mensagem_manha_07` (`DELETE` confirmado `200 {"success":true}`), já que a
condição de segurança ("nunca apagar sem confirmar primeiro que o substituto
está `APPROVED`") estava mais do que cumprida — o substituto (`19`) está
`APPROVED` há dias, não desde hoje.

Atualizado `POOL_RESERVA` em `agent/motivacao.py` (`manha`): removido o índice
`7`, fica `13-24` + `25-35` (23 templates, todos ativos e confirmados sem
erros de acentuação nesta revisão). `fim_dia` e `sexta` sem alterações
(`21-30` e `13-18`, todos `APPROVED` e revistos sem problemas). Sintaxe de
`agent/motivacao.py` verificada com `ast.parse` antes do commit. Nenhuma
alteração a `agent/meta_templates.py` — a correção do campo `example`
mantém-se estável.

Revisão de todos os restantes templates `APPROVED` (`manha_13-35` exceto `07`
já tratado, `fimdia_21-30`, `sexta_13-18`) — sem outros erros de acentuação
ou de português encontrados nesta execução.

Confirmação final: restam 40 templates `mensagem_*` (era 41), todos
`APPROVED` exceto `mensagem_sexta_urgente_01` (`REJECTED`, deixado de
propósito).

### Pendente para a próxima execução

1. Confirmar de novo, com olhos frescos, a acentuação de `mensagem_manha_13-24`
   e `25-35`, `mensagem_fimdia_21-30` e `mensagem_sexta_13-18` — o erro do
   `manha_07` mostra que vale a pena comparar o texto com cuidado a cada
   execução, e não confiar cegamente em conclusões de registos anteriores.
2. `mensagem_sexta_urgente_01` continua por esclarecer (ver ponto 5 do
   registo de 17/08) — também tem erros de acentuação semelhantes aos do
   antigo `manha_07` ("dedicacao", "Ate"), mas por estar `REJECTED` e sem uso
   conhecido no código, não foi tocado.
3. Nenhum trabalho pendente do bug do campo `example` — todos os templates
   ativos continuam a incluí-lo.

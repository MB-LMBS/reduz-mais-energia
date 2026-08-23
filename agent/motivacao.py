# agent/motivacao.py — Mensagens diárias de motivação para a equipa comercial
# Generado por AgentKit

"""
Envia mensagens de motivação e espírito de equipa aos consultores/comerciais,
Segunda a Sexta, de manhã e ao final do dia (com destaque à sexta-feira para
o fim de semana). Usa templates pré-aprovados do WhatsApp — necessários para
o negócio poder iniciar a conversa fora da janela de 24h — em vez de texto
gerado ao vivo pela IA, que a Meta não aprova em templates com uma variável
em aberto.

A reserva de templates é consultada diretamente na Meta (só os já aprovados
entram em rotação) — quando um ciclo completo se esgota, o sistema gera e
submete sozinho um novo lote à revisão, para nunca precisar de intervenção
manual. O estado de rotação fica guardado em config_app.
"""

import json
import logging
import os
from datetime import date

from anthropic import AsyncAnthropic

from agent.memory import obter_config, definir_config
from agent.meta_templates import listar_templates_aprovados, proximo_indice_livre, criar_template

logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Comerciais/consultores que recebem as mensagens diárias
CONSULTORES = [
    {"nome": "Luis Sequeira", "telefone": "351937157871"},
    {"nome": "Catarina Sequeira", "telefone": "351937157872"},
    {"nome": "Helena Barroso", "telefone": "351928233489"},
    {"nome": "Paula Garcia", "telefone": "351969853140"},
]

PREFIXOS = {"manha": "mensagem_manha_", "fim_dia": "mensagem_fimdia_", "sexta": "mensagem_sexta_"}

# Reserva de segurança, usada só se a consulta à Meta falhar (ex: API em baixo)
# — atualizado em 23/08/2026: manha_07 foi apagado (tinha erros de acentuação;
# manha_19 já era uma cópia corrigida do mesmo texto, aprovada há vários dias).
# Ver docs/manutencao-templates.md.
POOL_RESERVA = {
    "manha": [f"mensagem_manha_{i:02d}" for i in [*range(13, 25), *range(25, 36)]],
    "fim_dia": [f"mensagem_fimdia_{i:02d}" for i in range(21, 31)],
    "sexta": [f"mensagem_sexta_{i:02d}" for i in range(13, 19)],
}

NOVAS_MENSAGENS_POR_LOTE = 4

DESCRICAO_TIPO = {
    "manha": "mensagem de início de dia, Segunda a Sexta — motivação e espírito de equipa para começar bem o dia",
    "fim_dia": "mensagem de fecho de dia, Segunda a Quinta — reconhecimento e agradecimento pelo esforço do dia",
    "sexta": "mensagem de fecho de semana, sexta-feira ao final do dia — reconhecimento da semana e incentivo a aproveitar o fim de semana",
}

CHAVE_ESTADO = "motivacao_estado"


async def _obter_estado() -> dict:
    bruto = await obter_config(CHAVE_ESTADO)
    if not bruto:
        return {}
    try:
        return json.loads(bruto)
    except ValueError:
        return {}


async def _guardar_estado(estado: dict):
    await definir_config(CHAVE_ESTADO, json.dumps(estado))


def _primeiro_nome(nome_completo: str) -> str:
    return nome_completo.split(" ")[0]


async def _obter_pool(tipo: str) -> list[str]:
    prefixo = PREFIXOS[tipo]
    nomes = await listar_templates_aprovados(prefixo)
    return nomes or POOL_RESERVA[tipo]


async def _gerar_e_submeter_novo_lote(tipo: str):
    """
    Chamado quando um ciclo completo de mensagens se esgota — pede à IA um
    novo lote e submete-o à Meta para aprovação, para a reserva nunca
    esgotar de vez sem intervenção manual.
    """
    try:
        prompt = (
            f"Escreve {NOVAS_MENSAGENS_POR_LOTE} mensagens curtas de WhatsApp em português de "
            "Portugal, para consultores comerciais de energia de uma equipa que está a começar "
            f"agora a carreira. Tipo: {DESCRICAO_TIPO[tipo]}.\n\n"
            "Regras obrigatórias:\n"
            "- Cada mensagem tem de incluir literalmente o texto {{1}} no lugar do primeiro nome "
            "da pessoa — nunca no início nem no fim da mensagem, sempre rodeado de texto fixo "
            "(ex: 'Bom dia, {{1}}!' ou 'Boa noite, {{1}},').\n"
            "- Usa sempre o nome da pessoa de forma natural, é um detalhe importante.\n"
            "- PROIBIDO mencionar resultados fracos, vendas baixas, metas por cumprir ou "
            "comparações — a equipa está a começar e isso feriria o esforço inicial deles.\n"
            "- Foca sempre em esforço, resiliência, aprendizagem e espírito de equipa.\n"
            "- Podes usar um emoji relevante por mensagem.\n"
            "- Entre 100 e 280 caracteres cada.\n"
            "- Cada mensagem diferente das outras, sem se repetirem em estrutura.\n"
            "- Atenção à acentuação correta do português: não confundas 'e' (conjunção, "
            "sem acento) com 'é' (verbo ser, com acento agudo) — revê cada frase antes de "
            "a devolveres para garantir que este erro não acontece.\n\n"
            "Devolve só as mensagens, uma por linha, sem numeração nem comentários."
        )
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = response.content[0].text
        linhas = [l.strip() for l in texto.strip().split("\n") if l.strip() and "{{1}}" in l]

        if not linhas:
            logger.warning(f"Geração de novas mensagens ({tipo}) não devolveu linhas válidas")
            return

        prefixo = PREFIXOS[tipo]
        proximo = await proximo_indice_livre(prefixo)
        for i, corpo in enumerate(linhas[:NOVAS_MENSAGENS_POR_LOTE]):
            nome_template = f"{prefixo}{proximo + i:02d}"
            await criar_template(nome_template, corpo)

        logger.info(f"Novo lote de mensagens ({tipo}) submetido à Meta: {len(linhas)} mensagens")
    except Exception as e:
        logger.error(f"Erro ao gerar/submeter novo lote de mensagens ({tipo}): {e}")


async def enviar_mensagens_periodo(proveedor, periodo: str) -> int:
    """
    periodo: "manha" ou "fim_dia". Cada consultor recebe uma mensagem
    diferente da reserva (nunca o mesmo texto entre si no mesmo dia) — o
    índice de cada um é o ciclo do dia desviado pela sua posição na lista,
    por isso também nunca repete de um dia para o outro. Quando o ciclo dá
    a volta completa, dispara a geração de um novo lote em segundo plano.
    Idempotente por dia — se já disparou hoje neste período, não reenvia.
    Retorna o número de envios bem-sucedidos.
    """
    hoje = date.today()
    sexta = hoje.weekday() == 4  # 0=segunda ... 4=sexta
    tipo = "sexta" if (periodo == "fim_dia" and sexta) else periodo

    chave_ciclo = f"ciclo_{tipo}"
    chave_data = "data_manha" if periodo == "manha" else "data_fim_dia"

    estado = await _obter_estado()
    if estado.get(chave_data) == hoje.isoformat():
        return 0

    pool = await _obter_pool(tipo)
    ciclo = estado.get(chave_ciclo, 0) % len(pool)

    sucesso = 0
    for posicao, consultor in enumerate(CONSULTORES):
        template = pool[(ciclo + posicao) % len(pool)]
        ok = await proveedor.enviar_template(
            consultor["telefone"], template, [_primeiro_nome(consultor["nome"])]
        )
        if ok:
            sucesso += 1
        else:
            logger.warning(
                f"Falha ao enviar {template} a {consultor['nome']} ({consultor['telefone']})"
            )

    novo_ciclo = (ciclo + 1) % len(pool)
    estado[chave_ciclo] = novo_ciclo
    estado[chave_data] = hoje.isoformat()
    await _guardar_estado(estado)

    logger.info(
        f"Mensagens de motivação ({periodo}, ciclo {ciclo}): "
        f"{sucesso}/{len(CONSULTORES)} enviadas, cada uma com template diferente"
    )

    if novo_ciclo == 0:
        await _gerar_e_submeter_novo_lote(tipo)

    return sucesso

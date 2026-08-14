# agent/motivacao.py — Mensagens diárias de motivação para a equipa comercial
# Generado por AgentKit

"""
Envia mensagens de motivação e espírito de equipa aos consultores/comerciais,
Segunda a Sexta, de manhã e ao final do dia (com destaque à sexta-feira para
o fim de semana). Usa templates pré-aprovados do WhatsApp — necessários para
o negócio poder iniciar a conversa fora da janela de 24h — em vez de texto
gerado ao vivo pela IA, que a Meta não aprova em templates.

As mensagens são escolhidas de uma reserva escrita antecipadamente, sem
repetir até esgotar, para continuar a parecer uma mensagem diferente a cada
dia. O estado de rotação fica guardado em config_app (obter_config/definir_config).
"""

import json
import logging
from datetime import date

from agent.memory import obter_config, definir_config

logger = logging.getLogger("agentkit")

# Comerciais/consultores que recebem as mensagens diárias
CONSULTORES = [
    {"nome": "Luis Sequeira", "telefone": "351937157871"},
    {"nome": "Catarina Sequeira", "telefone": "351937157872"},
    {"nome": "Helena Barroso", "telefone": "351928233489"},
    {"nome": "Paula Garcia", "telefone": "351969853140"},
]

# Nomes dos templates aprovados na Meta (ver scratchpad/setup_pool_templates.py
# para o texto exato de cada um) — {{1}} em cada um é o primeiro nome
TEMPLATES_MANHA = [f"mensagem_manha_{i:02d}" for i in range(1, 13)]
TEMPLATES_FIM_DIA = [f"mensagem_fimdia_{i:02d}" for i in range(1, 11)]
TEMPLATES_SEXTA = [f"mensagem_sexta_{i:02d}" for i in range(1, 7)]

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


async def enviar_mensagens_periodo(proveedor, periodo: str) -> int:
    """
    periodo: "manha" ou "fim_dia". Cada consultor recebe uma mensagem
    diferente da reserva (nunca o mesmo texto entre si no mesmo dia) — o
    índice de cada um é o ciclo do dia desviado pela sua posição na lista,
    por isso também nunca repete de um dia para o outro. Idempotente por
    dia — se já disparou hoje neste período, não reenvia.
    Retorna o número de envios bem-sucedidos.
    """
    hoje = date.today()
    sexta = hoje.weekday() == 4  # 0=segunda ... 4=sexta

    if periodo == "manha":
        pool = TEMPLATES_MANHA
        chave_ciclo = "ciclo_manha"
        chave_data = "data_manha"
    else:
        pool = TEMPLATES_SEXTA if sexta else TEMPLATES_FIM_DIA
        chave_ciclo = "ciclo_sexta" if sexta else "ciclo_fimdia"
        chave_data = "data_fim_dia"

    estado = await _obter_estado()
    if estado.get(chave_data) == hoje.isoformat():
        return 0

    ciclo = estado.get(chave_ciclo, 0)

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

    estado[chave_ciclo] = (ciclo + 1) % len(pool)
    estado[chave_data] = hoje.isoformat()
    await _guardar_estado(estado)

    logger.info(
        f"Mensagens de motivação ({periodo}, ciclo {ciclo}): "
        f"{sucesso}/{len(CONSULTORES)} enviadas, cada uma com template diferente"
    )
    return sucesso

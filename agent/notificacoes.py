# agent/notificacoes.py — Encaminhamento de conversas para o consultor humano
# Generado por AgentKit

"""
Envía una conversación completa por WhatsApp al número personal del
consultor. Se usa tanto automáticamente (cuando el bot detecta un pedido
de consultor) como manualmente (botón "Encaminhar para consultor" en /admin).
"""

import os
import logging

from agent.agenda import formatar_slot

logger = logging.getLogger("agentkit")

# Número personal a donde se reenvía la conversación
NUMERO_CONSULTOR = os.getenv("NUMERO_CONSULTOR", "")

# URL pública do painel — usada para que os links nas notificações sejam
# clicáveis diretamente a partir do WhatsApp (ex: no telemóvel, fora do escritório)
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://reduz-mais-energia-production.up.railway.app")


async def notificar_consultor(
    proveedor, telefono_cliente: str, historial: list[dict], mensaje_actual: str | None = None
) -> bool:
    """
    Envía la conversación completa al WhatsApp personal del consultor.
    Retorna True si se envió con éxito.
    """
    if not NUMERO_CONSULTOR:
        logger.warning("NUMERO_CONSULTOR no configurado — no se puede notificar")
        return False

    lineas = [f"🔔 *Pedido de consultor* — {telefono_cliente}", ""]
    for msg in historial:
        etiqueta = "Cliente" if msg["role"] == "user" else "Reduz+"
        contenido = msg["content"] or f"[ficheiro: {msg.get('nome_ficheiro') or msg.get('tipo')}]"
        lineas.append(f"*{etiqueta}:* {contenido}")
    if mensaje_actual:
        lineas.append(f"*Cliente:* {mensaje_actual}")
    lineas.append("")
    lineas.append(f"Responde diretamente ao cliente em: {APP_BASE_URL}/admin/conversa/{telefono_cliente}")

    return await proveedor.enviar_mensaje(NUMERO_CONSULTOR, "\n".join(lineas))


async def notificar_lembrete_chamada(proveedor, agendamento: dict) -> bool:
    """
    Envía un recordatorio al WhatsApp personal del consultor unos minutos
    antes de una chamada agendada. Retorna True si se envió con éxito.
    """
    if not NUMERO_CONSULTOR:
        logger.warning("NUMERO_CONSULTOR no configurado — no se puede enviar lembrete")
        return False

    nome = agendamento.get("nome_cliente") or "(nome não indicado)"
    telefone = agendamento["telefono"]
    slot = formatar_slot(agendamento["data_hora"])
    informacao = agendamento.get("informacao") or "(sem informação adicional)"

    lineas = [
        "⏰ *Lembrete: chamada daqui a poucos minutos*",
        "",
        f"*Cliente:* {nome}",
        f"*Telefone:* {telefone}",
        f"*Quando:* {slot}",
        "",
        f"*Informação registada:*\n{informacao}",
        "",
        f"Ver conversa: {APP_BASE_URL}/admin/conversa/{telefone}",
    ]

    return await proveedor.enviar_mensaje(NUMERO_CONSULTOR, "\n".join(lineas))


async def notificar_agendamento(proveedor, agendamento: dict) -> bool:
    """
    Envía un alerta al WhatsApp personal del consultor cuando se marca una
    chamada, con toda la información que el cliente registró.
    Retorna True si se envió con éxito.
    """
    if not NUMERO_CONSULTOR:
        logger.warning("NUMERO_CONSULTOR no configurado — no se puede notificar agendamento")
        return False

    nome = agendamento.get("nome_cliente") or "(nome não indicado)"
    telefone = agendamento["telefono"]
    slot = formatar_slot(agendamento["data_hora"])
    informacao = agendamento.get("informacao") or "(sem informação adicional)"

    lineas = [
        "📅 *Chamada agendada*",
        "",
        f"*Cliente:* {nome}",
        f"*Telefone:* {telefone}",
        f"*Quando:* {slot}",
        "",
        f"*Informação registada:*\n{informacao}",
        "",
        f"Ver conversa: {APP_BASE_URL}/admin/conversa/{telefone}",
    ]

    return await proveedor.enviar_mensaje(NUMERO_CONSULTOR, "\n".join(lineas))

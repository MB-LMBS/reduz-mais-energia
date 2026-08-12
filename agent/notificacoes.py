# agent/notificacoes.py — Encaminhamento de conversas para o consultor humano
# Generado por AgentKit

"""
Envía una conversación completa por WhatsApp al número personal del
consultor. Se usa tanto automáticamente (cuando el bot detecta un pedido
de consultor) como manualmente (botón "Encaminhar para consultor" en /admin).
"""

import os
import logging

logger = logging.getLogger("agentkit")

# Número personal a donde se reenvía la conversación
NUMERO_CONSULTOR = os.getenv("NUMERO_CONSULTOR", "")


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
    lineas.append(f"Responde diretamente ao cliente em: /admin/conversa/{telefono_cliente}")

    return await proveedor.enviar_mensaje(NUMERO_CONSULTOR, "\n".join(lineas))

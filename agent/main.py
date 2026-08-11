# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp.
Funciona con cualquier proveedor (Meta, Twilio) gracias a la capa de providers.
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial, obtener_modo, establecer_modo
from agent.providers import obtener_proveedor
from agent.admin import router as admin_router

load_dotenv()

# Configuración de logging según entorno
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
log_level = logging.DEBUG if ENVIRONMENT == "development" else logging.INFO
logging.basicConfig(level=log_level)
logger = logging.getLogger("agentkit")

# Proveedor de WhatsApp (se configura en .env con WHATSAPP_PROVIDER)
proveedor = obtener_proveedor()
PORT = int(os.getenv("PORT", 8000))

# Número personal a donde se reenvía la conversación cuando el cliente pide
# hablar con un consultor humano
NUMERO_CONSULTOR = os.getenv("NUMERO_CONSULTOR", "")


async def notificar_consultor(telefono_cliente: str, historial: list[dict], mensaje_actual: str):
    """Envía la conversación completa al WhatsApp personal del consultor."""
    if not NUMERO_CONSULTOR:
        logger.warning("NUMERO_CONSULTOR no configurado — no se puede notificar")
        return

    lineas = [f"🔔 *Pedido de consultor* — {telefono_cliente}", ""]
    for msg in historial:
        etiqueta = "Cliente" if msg["role"] == "user" else "Reduz+"
        lineas.append(f"*{etiqueta}:* {msg['content']}")
    lineas.append(f"*Cliente:* {mensaje_actual}")
    lineas.append("")
    lineas.append(f"Responde diretamente ao cliente em: /admin/conversa/{telefono_cliente}")

    await proveedor.enviar_mensaje(NUMERO_CONSULTOR, "\n".join(lineas))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield


app = FastAPI(
    title="AgentKit — WhatsApp AI Agent",
    version="1.0.0",
    lifespan=lifespan
)
app.include_router(admin_router)


@app.get("/")
async def health_check():
    """Endpoint de salud para Railway/monitoreo."""
    return {"status": "ok", "service": "agentkit"}


@app.get("/webhook")
async def webhook_verificacion(request: Request):
    """Verificación GET del webhook (requerido por Meta Cloud API, no-op para otros)."""
    resultado = await proveedor.validar_webhook(request)
    if resultado is not None:
        return PlainTextResponse(str(resultado))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_handler(request: Request):
    """
    Recibe mensajes de WhatsApp via el proveedor configurado.
    Procesa el mensaje, genera respuesta con Claude y la envía de vuelta.
    """
    try:
        # Parsear webhook — el proveedor normaliza el formato
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            # Ignorar mensajes propios o vacíos
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

            # Si la conversación está en modo "manual", solo guardamos el
            # mensaje para que el humano lo vea y responda desde /admin —
            # el bot no interviene.
            modo = await obtener_modo(msg.telefono)
            if modo == "manual":
                await guardar_mensaje(msg.telefono, "user", msg.texto)
                logger.info(f"Conversación {msg.telefono} en modo manual — bot no responde")
                continue

            # Obtener historial ANTES de guardar el mensaje actual
            # (brain.py agrega el mensaje actual, evitando duplicados)
            historial = await obtener_historial(msg.telefono)

            # Generar respuesta con Claude
            respuesta, escalar = await generar_respuesta(msg.texto, historial)

            # Guardar mensaje del usuario Y respuesta del agente en memoria
            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            # Enviar respuesta por WhatsApp via el proveedor
            await proveedor.enviar_mensaje(msg.telefono, respuesta)

            logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

            # Si el cliente pidió/aceptó hablar con un consultor, reenviamos
            # la conversación completa y pausamos el bot en esa conversación
            if escalar:
                await notificar_consultor(msg.telefono, historial, msg.texto)
                await establecer_modo(msg.telefono, "manual")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp.
Funciona con cualquier proveedor (Meta, Twilio) gracias a la capa de providers.
"""

import os
import uuid
import mimetypes
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial, obtener_modo, establecer_modo,
    establecer_nome_contato,
)
from agent.providers import obtener_proveedor
from agent.notificacoes import notificar_consultor
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

# Carpeta donde se guardan los archivos que envían los clientes (facturas, fotos, etc.)
MEDIA_DIR = "data/media"
os.makedirs(MEDIA_DIR, exist_ok=True)


async def guardar_media_recibido(msg) -> str | None:
    """Descarga un archivo recibido y lo guarda localmente. Retorna la ruta relativa o None."""
    if not msg.media_id:
        return None
    resultado = await proveedor.baixar_media(msg.media_id)
    if resultado is None:
        logger.warning(f"No se pudo descargar el archivo {msg.media_id} de {msg.telefono}")
        return None
    contenido, mime_type = resultado
    extension = mimetypes.guess_extension(mime_type) or ""
    nombre_archivo = f"{uuid.uuid4().hex}{extension}"
    ruta = os.path.join(MEDIA_DIR, nombre_archivo)
    with open(ruta, "wb") as f:
        f.write(contenido)
    return ruta


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
            # Ignorar mensajes propios, o mensajes de texto vacíos (los archivos
            # sin descripción también deben procesarse, por eso no se descartan aquí)
            if msg.es_propio or (msg.tipo == "texto" and not msg.texto):
                continue

            logger.info(f"Mensaje de {msg.telefono} ({msg.tipo}): {msg.texto}")

            # Guardamos el nombre de perfil de WhatsApp del contacto, si vino informado
            if msg.nome_contato:
                await establecer_nome_contato(msg.telefono, msg.nome_contato)

            # Si el mensaje trae un archivo (imagen, PDF, etc.), lo descargamos
            # y guardamos localmente para poder verlo desde /admin
            media_path = None
            if msg.tipo != "texto":
                media_path = await guardar_media_recibido(msg)

            # Texto que usará el agente: la descripción del cliente, o un aviso
            # de que llegó un archivo si no escribió nada
            texto_para_ia = msg.texto
            if msg.tipo != "texto" and not texto_para_ia:
                texto_para_ia = f"[Cliente enviou um ficheiro: {msg.nome_ficheiro or msg.tipo}]"

            # Si la conversación está en modo "manual", solo guardamos el
            # mensaje para que el humano lo vea y responda desde /admin —
            # el bot no interviene.
            modo = await obtener_modo(msg.telefono)
            if modo == "manual":
                await guardar_mensaje(
                    msg.telefono, "user", msg.texto, tipo=msg.tipo,
                    media_path=media_path, nome_ficheiro=msg.nome_ficheiro,
                )
                logger.info(f"Conversación {msg.telefono} en modo manual — bot no responde")
                continue

            # Obtener historial ANTES de guardar el mensaje actual
            # (brain.py agrega el mensaje actual, evitando duplicados)
            historial = await obtener_historial(msg.telefono)

            # Generar respuesta con Claude
            respuesta, escalar = await generar_respuesta(texto_para_ia, historial)

            # Guardar mensaje del usuario Y respuesta del agente en memoria
            await guardar_mensaje(
                msg.telefono, "user", msg.texto, tipo=msg.tipo,
                media_path=media_path, nome_ficheiro=msg.nome_ficheiro,
            )
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            # Enviar respuesta por WhatsApp via el proveedor
            await proveedor.enviar_mensaje(msg.telefono, respuesta)

            logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

            # Si el cliente pidió/aceptó hablar con un consultor, reenviamos
            # la conversación completa y pausamos el bot en esa conversación
            if escalar:
                await notificar_consultor(proveedor, msg.telefono, historial, msg.texto)
                await establecer_modo(msg.telefono, "manual")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp.
Funciona con cualquier proveedor (Meta, Twilio) gracias a la capa de providers.
"""

import os
import uuid
import asyncio
import mimetypes
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.agenda import formatar_slot
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial, obtener_modo, establecer_modo,
    establecer_nome_contato, obtener_nome_contato, obter_agendamentos_a_lembrar,
    marcar_lembrete_enviado, criar_alerta,
)
from agent.providers import obtener_proveedor
from agent.notificacoes import notificar_consultor, notificar_agendamento, notificar_lembrete_chamada
from agent.calendario import criar_evento_chamada
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

# Intervalo (segundos) entre verificaciones de llamadas agendadas próximas
INTERVALO_LEMBRETES = 60


async def loop_lembretes():
    """
    Verifica periodicamente se há chamadas agendadas a começar dentro de
    5 minutos e ainda não lembradas, e envia um aviso ao consultor.
    """
    while True:
        try:
            agora = datetime.now(ZoneInfo("Europe/Lisbon")).replace(tzinfo=None)
            pendentes = await obter_agendamentos_a_lembrar(agora)
            for agendamento in pendentes:
                enviado = await notificar_lembrete_chamada(proveedor, agendamento)
                if enviado:
                    await marcar_lembrete_enviado(agendamento["id"])
                    nome = agendamento.get("nome_cliente") or agendamento["telefono"]
                    await criar_alerta(
                        "lembrete", agendamento["telefono"],
                        f"⏰ Chamada em breve com {nome} às {formatar_slot(agendamento['data_hora'])}",
                    )
                    logger.info(
                        f"Lembrete de chamada enviado: {agendamento['telefono']} "
                        f"— {agendamento['data_hora']}"
                    )
        except Exception as e:
            logger.error(f"Error en loop_lembretes: {e}")
        await asyncio.sleep(INTERVALO_LEMBRETES)


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
    """Inicializa la base de datos y el loop de lembretes al arrancar el servidor."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    tarefa_lembretes = asyncio.create_task(loop_lembretes())
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield
    tarefa_lembretes.cancel()


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
            nome_contato = msg.nome_contato or await obtener_nome_contato(msg.telefono)

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
            respuesta, escalar, agendamento = await generar_respuesta(
                texto_para_ia, historial, msg.telefono, nome_contato
            )

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
                await criar_alerta(
                    "escalada", msg.telefono,
                    f"🔔 {nome_contato or msg.telefono} pediu para falar com um consultor",
                )

            # Si se marcó una chamada, avisamos al consultor con toda la
            # información que el cliente registró
            if agendamento:
                await notificar_agendamento(proveedor, agendamento)
                nome = agendamento.get("nome_cliente") or msg.telefono
                await criar_alerta(
                    "agendamento", msg.telefono,
                    f"📅 Chamada agendada com {nome} para {formatar_slot(agendamento['data_hora'])}",
                )
                await criar_evento_chamada(
                    agendamento["id"], agendamento.get("nome_cliente"),
                    agendamento["telefono"], agendamento["data_hora"], agendamento["informacao"],
                )

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# agent/main.py — Servidor FastAPI + Webhook de WhatsApp
# Generado por AgentKit

"""
Servidor principal del agente de WhatsApp.
Funciona con cualquier proveedor (Meta, Twilio) gracias a la capa de providers.
"""

import os
import re
import uuid
import asyncio
import mimetypes
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from agent.brain import generar_respuesta
from agent.agenda import formatar_slot
from agent.memory import (
    inicializar_db, guardar_mensaje, obtener_historial, obtener_modo,
    establecer_nome_contato, obtener_nome_contato, obter_agendamentos_a_lembrar,
    marcar_lembrete_enviado, criar_alerta, guardar_evento_outlook_id,
    obtener_estado, establecer_estado, establecer_categoria,
    purgar_mensagens_apagadas_antigas,
)
from agent.providers import obtener_proveedor
from agent.notificacoes import (
    notificar_consultor, notificar_pedido_simulador, notificar_agendamento, notificar_lembrete_chamada, notificar_cliente_lembrete,
)
from agent.calendario import criar_evento_chamada as criar_evento_icloud
from agent.outlook_calendar import criar_evento_chamada as criar_evento_outlook
from agent.admin import router as admin_router, LOGO_URL
from agent.motivacao import enviar_mensagens_periodo
from integrations.attio import sincronizar_lead_attio

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

# Números de sistema do WhatsApp/Meta (ex: notificações automáticas sobre
# gestão da conta, tickets de suporte) — não são clientes reais, o bot nunca
# deve responder-lhes
NUMEROS_SISTEMA_WHATSAPP = {"15517868411"}

# Primeira linha fixa da mensagem pré-preenchida pelo botão "ENVIAR PEDIDO À
# REDUZ+ ENERGIA" no simulador de eletricidade (EE_Campanhas) — identifica um
# pedido vindo do simulador, para nunca passar pela IA e responder sempre com
# uma confirmação fixa
MARCADOR_PEDIDO_SIMULADOR = "*TENHO INTERESSE NUMA PROPOSTA DE ELETRICIDADE*"

def montar_confirmacao_pedido_simulador() -> str:
    """Confirmação curta ao cliente — os dados do pedido vão só para o consultor, não são ecoados ao cliente."""
    return (
        "✅ *O seu pedido foi submetido com sucesso!*\n\n"
        "Muito obrigado pela confiança na Reduz+ Energia. 🙏"
    )

# Marcador da mensagem pré-preenchida pelo simulador (link com aceitar=1) ao
# submeter a aceitação de uma proposta — normalmente enviada pelo próprio
# consultor/gestor de cliente em nome do cliente (secção "SUBMETIDO POR"),
# com os dados do cliente numa secção à parte ("DADOS DO CLIENTE"). Nunca
# passa pela IA — responde sempre com uma confirmação fixa.
MARCADOR_ACEITACAO_PROPOSTA = "SUBMETER PROPOSTA PARA FORMALIZAÇÃO"


def extrair_dados_cliente_aceitacao(texto: str) -> tuple[str | None, str | None]:
    """
    Extrai nome e telemóvel da secção "DADOS DO CLIENTE" do texto de
    aceitação da proposta — distintos dos dados de quem submete (consultor),
    que vêm numa secção separada mais abaixo ("SUBMETIDO POR").
    """
    secao = texto.split("*SUBMETIDO POR*")[0]
    m_nome = re.search(r"Nome:\s*(.+)", secao)
    nome = m_nome.group(1).strip() if m_nome else None
    m_tel = re.search(r"Telem[oó]vel:\s*\+?(\d[\d\s]*)", secao)
    telefone = re.sub(r"\D", "", m_tel.group(1)) if m_tel else None
    return nome, telefone


def montar_confirmacao_aceitacao_proposta() -> str:
    """Confirmação curta enviada quando a aceitação da proposta é submetida."""
    return "✅ *PROPOSTA PARA FORMALIZAÇÃO foi submetida com sucesso*"

# Intervalo (segundos) entre verificaciones de llamadas agendadas próximas
INTERVALO_LEMBRETES = 60


async def loop_lembretes():
    """
    Verifica periodicamente se há chamadas agendadas a começar dentro de
    5 minutos e ainda não lembradas, e envia um aviso ao consultor e ao
    próprio cliente. Aproveita o mesmo ciclo para esvaziar a lixeira de
    mensagens com mais de 30 dias.
    """
    while True:
        try:
            removidas = await purgar_mensagens_apagadas_antigas()
            if removidas:
                logger.info(f"Lixeira: {removidas} mensagem(ns) removida(s) em definitivo (>30 dias)")

            agora = datetime.now(ZoneInfo("Europe/Lisbon")).replace(tzinfo=None)
            pendentes = await obter_agendamentos_a_lembrar(agora)
            for agendamento in pendentes:
                enviado_consultor = await notificar_lembrete_chamada(proveedor, agendamento)
                enviado_cliente = await notificar_cliente_lembrete(proveedor, agendamento)

                if not enviado_cliente:
                    logger.warning(
                        f"Não foi possível enviar lembrete ao cliente {agendamento['telefono']}"
                    )

                if enviado_consultor:
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


async def loop_motivacao():
    """
    Envia as mensagens de motivação à equipa comercial — Segunda-feira de
    manhã (08:00), Quarta-feira ao final do dia (19:30) e Sexta-feira ao
    final da semana (19:30, tipo "sexta"). A janela de 15 minutos evita
    perder o disparo se o servidor reiniciar perto da hora certa;
    enviar_mensagens_periodo garante que não repete no mesmo dia mesmo que
    o ciclo passe várias vezes pela mesma janela.
    """
    while True:
        try:
            agora = datetime.now(ZoneInfo("Europe/Lisbon"))
            dia = agora.weekday()  # 0=segunda ... 4=sexta
            hora_atual = agora.time()
            if dia == 0 and time(8, 0) <= hora_atual < time(8, 15):
                await enviar_mensagens_periodo(proveedor, "manha")
            elif dia in (2, 4) and time(19, 30) <= hora_atual < time(19, 45):
                await enviar_mensagens_periodo(proveedor, "fim_dia")
        except Exception as e:
            logger.error(f"Error en loop_motivacao: {e}")
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
    tarefa_motivacao = asyncio.create_task(loop_motivacao())
    logger.info(f"Servidor AgentKit corriendo en puerto {PORT}")
    logger.info(f"Proveedor de WhatsApp: {proveedor.__class__.__name__}")
    yield
    tarefa_lembretes.cancel()
    tarefa_motivacao.cancel()


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

            # Notificações automáticas do próprio WhatsApp/Meta (ex: gestão de
            # número, tickets de suporte) — ignorar por completo, não é um cliente
            if msg.telefono in NUMEROS_SISTEMA_WHATSAPP:
                logger.info(f"Mensagem de sistema do WhatsApp ignorada ({msg.telefono})")
                continue

            logger.info(f"Mensaje de {msg.telefono} ({msg.tipo}): {msg.texto}")

            # Guardamos el nombre de perfil de WhatsApp del contacto, si vino informado
            if msg.nome_contato:
                await establecer_nome_contato(msg.telefono, msg.nome_contato)
            nome_contato = msg.nome_contato or await obtener_nome_contato(msg.telefono)

            # Se a conversa estava marcada como "Tratada" e o cliente escreveu
            # de novo, reabrimo-la automaticamente para não passar despercebida
            if await obtener_estado(msg.telefono) == "tratada":
                await establecer_estado(msg.telefono, "aberta")
                logger.info(f"Conversación {msg.telefono} reaberta — cliente escreveu de novo")

            # Pedido vindo do botão "ENVIAR PEDIDO À REDUZ+ ENERGIA" do simulador
            # de eletricidade — nunca passa pela IA (independentemente do modo
            # bot/manual): confirma ao cliente com uma mensagem fixa e avisa o
            # consultor, tal como um pedido novo
            if msg.tipo == "texto" and msg.texto.strip().startswith(MARCADOR_PEDIDO_SIMULADOR):
                confirmacao = montar_confirmacao_pedido_simulador()
                await guardar_mensaje(msg.telefono, "user", msg.texto, tipo=msg.tipo)
                await proveedor.enviar_mensaje(msg.telefono, confirmacao)
                await guardar_mensaje(msg.telefono, "assistant", confirmacao)
                await establecer_categoria(msg.telefono, "interessado")
                await criar_alerta(
                    "pedido_simulador", msg.telefono,
                    f"📋 {nome_contato or msg.telefono} enviou um pedido pelo simulador de eletricidade",
                )
                await notificar_pedido_simulador(proveedor, msg.telefono, nome_contato)
                logger.info(f"Pedido de simulador processado para {msg.telefono}")
                continue

            # Aceitação/formalização da proposta vinda do simulador (link com
            # aceitar=1) — nunca passa pela IA: só confirma, e marca a
            # conversa do cliente como "Ganho". Normalmente enviada pelo
            # consultor em nome do cliente, por isso a confirmação vai tanto
            # para quem submeteu como para o telemóvel do cliente indicado
            # nos dados (quando presente e diferente de quem submeteu).
            if msg.tipo == "texto" and msg.texto.strip().lstrip("*").upper().startswith(MARCADOR_ACEITACAO_PROPOSTA):
                nome_cliente_aceitacao, telefone_cliente_aceitacao = extrair_dados_cliente_aceitacao(msg.texto)
                confirmacao = montar_confirmacao_aceitacao_proposta()
                await guardar_mensaje(msg.telefono, "user", msg.texto, tipo=msg.tipo)
                await proveedor.enviar_mensaje(msg.telefono, confirmacao)
                await guardar_mensaje(msg.telefono, "assistant", confirmacao)

                telefone_ganho = msg.telefono
                if telefone_cliente_aceitacao and telefone_cliente_aceitacao != msg.telefono:
                    await proveedor.enviar_mensaje(telefone_cliente_aceitacao, confirmacao)
                    await guardar_mensaje(telefone_cliente_aceitacao, "assistant", confirmacao)
                    telefone_ganho = telefone_cliente_aceitacao

                await establecer_categoria(telefone_ganho, "ganho")
                await criar_alerta(
                    "aceitacao_proposta", telefone_ganho,
                    f"🎉 {nome_cliente_aceitacao or nome_contato or telefone_ganho} submeteu a aceitação da proposta",
                )
                logger.info(f"Aceitação de proposta processada para {msg.telefono}")
                continue

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
            primeira_mensagem = not historial

            # Generar respuesta con Claude
            respuesta, escalar, agendamento, opcoes, link_botao, motivo_escalada, links_multiplos = \
                await generar_respuesta(texto_para_ia, historial, msg.telefono, nome_contato)

            # Guardar mensaje del usuario Y respuesta del agente en memoria
            await guardar_mensaje(
                msg.telefono, "user", msg.texto, tipo=msg.tipo,
                media_path=media_path, nome_ficheiro=msg.nome_ficheiro,
            )
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            # Enviar respuesta por WhatsApp via el proveedor — com botões de
            # resposta rápida, de link, vários links (redes sociais, com o
            # logótipo a acompanhar o agradecimento), ou o logótipo na
            # primeira mensagem da conversa (boas-vindas)
            if links_multiplos:
                await proveedor.enviar_imagem_url(msg.telefono, LOGO_URL, respuesta)
                for link in links_multiplos:
                    await proveedor.enviar_botao_link(
                        msg.telefono, f"Siga-nos no {link['texto_botao']}:", link["texto_botao"], link["url"]
                    )
            elif link_botao:
                await proveedor.enviar_botao_link(
                    msg.telefono, respuesta, link_botao["texto_botao"], link_botao["url"]
                )
            elif opcoes:
                await proveedor.enviar_botoes(msg.telefono, respuesta, opcoes)
            elif primeira_mensagem:
                await proveedor.enviar_imagem_url(msg.telefono, LOGO_URL, respuesta)
            else:
                await proveedor.enviar_mensaje(msg.telefono, respuesta)

            logger.info(f"Respuesta a {msg.telefono}: {respuesta}")

            # Si el cliente pidió/aceptó hablar con un consultor, reenviamos
            # la conversación completa — el bot sigue a responder por defeito,
            # só passa a modo manual se o consultor o alternar manualmente no painel
            if escalar:
                await notificar_consultor(proveedor, msg.telefono, historial, msg.texto, motivo_escalada)
                await criar_alerta(
                    "escalada", msg.telefono,
                    f"🔔 {nome_contato or msg.telefono} pediu para falar com um consultor",
                )
                await sincronizar_lead_attio(msg.telefono, nome_contato, motivo_escalada)

            # Si se marcó una chamada, avisamos al consultor con toda la
            # información que el cliente registró
            if agendamento:
                await notificar_agendamento(proveedor, agendamento)
                nome = agendamento.get("nome_cliente") or msg.telefono
                await criar_alerta(
                    "agendamento", msg.telefono,
                    f"📅 Chamada agendada com {nome} para {formatar_slot(agendamento['data_hora'])}",
                )
                await criar_evento_icloud(
                    agendamento["id"], agendamento.get("nome_cliente"),
                    agendamento["telefono"], agendamento["data_hora"], agendamento["informacao"],
                )
                evento_outlook_id = await criar_evento_outlook(
                    agendamento["id"], agendamento.get("nome_cliente"),
                    agendamento["telefono"], agendamento["data_hora"], agendamento["informacao"],
                )
                if evento_outlook_id:
                    await guardar_evento_outlook_id(agendamento["id"], evento_outlook_id)

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error en webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

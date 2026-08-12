# agent/brain.py — Cerebro del agente: conexión con Claude API
# Generado por AgentKit

"""
Lógica de IA del agente. Lee el system prompt de prompts.yaml
y genera respuestas usando la API de Anthropic Claude.
"""

import os
import yaml
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agentkit")

# Cliente de Anthropic
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Herramienta que el modelo activa cuando el cliente pide o acepta hablar
# con un consultor humano
HERRAMIENTAS = [
    {
        "name": "escalar_a_consultor",
        "description": (
            "Usa esta ferramenta assim que o cliente pedir explicitamente para falar "
            "com um consultor/pessoa da equipa, ou aceitar essa opção quando lhe é "
            "sugerida (ex: responde 'sim' quando perguntas se queres falar com um "
            "consultor). Isto notifica a equipa para dar seguimento pessoalmente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "description": "Breve razão pela qual o cliente quer falar com um consultor.",
                }
            },
            "required": ["motivo"],
        },
    }
]


def cargar_config_prompts() -> dict:
    """Lee toda la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]


def obtener_contexto_temporal() -> str:
    """
    Genera un bloque con la fecha/hora actual (hora de Portugal) para que el
    modelo sepa con certeza si está dentro o fuera del horario de atención,
    en vez de adivinarlo.
    """
    ahora = datetime.now(ZoneInfo("Europe/Lisbon"))
    dia_semana = DIAS_SEMANA[ahora.weekday()]
    dentro_horario = ahora.weekday() < 5 and 9 <= ahora.hour < 18
    estado = "DENTRO do horário de atendimento" if dentro_horario else "FORA do horário de atendimento"
    return (
        f"\n\n## Data e hora atuais\n"
        f"Agora é {dia_semana}, {ahora.strftime('%d/%m/%Y')}, {ahora.strftime('%H:%M')} "
        f"(hora de Portugal). Estamos {estado}."
    )


def cargar_system_prompt() -> str:
    """Lee el system prompt desde config/prompts.yaml, con la fecha/hora actual añadida."""
    config = cargar_config_prompts()
    base = config.get("system_prompt", "Eres un asistente útil. Responde en español.")
    return base + obtener_contexto_temporal()


def obtener_mensaje_error() -> str:
    """Retorna el mensaje de error configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("error_message", "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos.")


def obtener_mensaje_fallback() -> str:
    """Retorna el mensaje de fallback configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?")


async def generar_respuesta(mensaje: str, historial: list[dict]) -> tuple[str, bool]:
    """
    Genera una respuesta usando Claude API.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant/humano", "content": "..."}]

    Returns:
        Tupla (respuesta, escalar_a_consultor) — escalar_a_consultor es True si el
        cliente pidió o aceptó hablar con un consultor humano.
    """
    # Si el mensaje es muy corto o vacío, usar fallback
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback(), False

    system_prompt = cargar_system_prompt()

    # Construir mensajes para la API — "humano" (respuestas manuales desde /admin)
    # se envía como "assistant", Claude solo conoce esos dos roles
    mensajes = []
    for msg in historial:
        role = "assistant" if msg["role"] == "humano" else msg["role"]
        contenido = msg["content"]
        # Los archivos (imagem/documento/audio/video) no se envían a Claude —
        # solo le avisamos que fueron recibidos, para no dejar el mensaje vacío
        if msg.get("tipo", "texto") != "texto" and not contenido:
            nome = msg.get("nome_ficheiro") or msg["tipo"]
            contenido = f"[Cliente enviou um ficheiro: {nome}]"
        mensajes.append({"role": role, "content": contenido})

    # Agregar el mensaje actual
    mensajes.append({
        "role": "user",
        "content": mensaje
    })

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            tools=HERRAMIENTAS,
            messages=mensajes
        )

        escalar = False

        # Si el modelo activó la herramienta de escalado, completamos el ciclo
        # de tool-use para que genere la respuesta final al cliente
        if response.stop_reason == "tool_use":
            tool_use = next(b for b in response.content if b.type == "tool_use")
            if tool_use.name == "escalar_a_consultor":
                escalar = True
                logger.info(f"Escalado a consultor: {tool_use.input.get('motivo')}")

            mensajes.append({"role": "assistant", "content": response.content})
            mensajes.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": "Consultor notificado, vai entrar em contacto em breve.",
                }],
            })
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_prompt,
                tools=HERRAMIENTAS,
                messages=mensajes
            )

        texto = next((b.text for b in response.content if b.type == "text"), "")
        logger.info(f"Respuesta generada ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")
        return texto, escalar

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error(), False

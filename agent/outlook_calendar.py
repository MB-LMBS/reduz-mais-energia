# agent/outlook_calendar.py — Sincronização de chamadas agendadas com o Outlook/Microsoft 365
# Generado por AgentKit

"""
Exporta as chamadas marcadas com clientes para o calendário do Outlook
(Microsoft 365 / Teams) do consultor, via Microsoft Graph API, com lembrete
ativado. Quando uma chamada é cancelada, o evento correspondente é removido.

Requer uma app registada no Microsoft Entra ID (Azure) com permissão
delegada Calendars.ReadWrite, e uma autorização inicial feita pelo próprio
utilizador em /admin/outlook/conectar (fluxo OAuth — não pode ser feito
automaticamente, tem de ser um clique explícito do dono da conta).
"""

import os
import logging
import httpx
import msal
from datetime import timedelta
from zoneinfo import ZoneInfo

from agent.memory import obter_config, definir_config

logger = logging.getLogger("agentkit")

AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_REDIRECT_URI = os.getenv(
    "AZURE_REDIRECT_URI",
    "https://reduz-mais-energia-production.up.railway.app/admin/outlook/callback",
)

SCOPES = ["Calendars.ReadWrite"]
GRAPH_URL = "https://graph.microsoft.com/v1.0"
DURACAO_CHAMADA_MINUTOS = 30
LEMBRETE_MINUTOS_ANTES = 15

CHAVE_TOKEN_CACHE = "outlook_token_cache"


def outlook_configurado() -> bool:
    """Se as credenciais da app Azure estão definidas (não significa que já foi autorizado)."""
    return bool(AZURE_CLIENT_ID and AZURE_CLIENT_SECRET and AZURE_TENANT_ID)


def _authority() -> str:
    return f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"


async def _carregar_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    dados = await obter_config(CHAVE_TOKEN_CACHE)
    if dados:
        cache.deserialize(dados)
    return cache


async def _guardar_cache(cache: msal.SerializableTokenCache):
    if cache.has_state_changed:
        await definir_config(CHAVE_TOKEN_CACHE, cache.serialize())


def _criar_app(cache: msal.SerializableTokenCache | None = None) -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        AZURE_CLIENT_ID,
        authority=_authority(),
        client_credential=AZURE_CLIENT_SECRET,
        token_cache=cache,
    )


async def gerar_url_autorizacao() -> str:
    """Gera o link para o utilizador autorizar a app a aceder ao seu calendário (uma vez só)."""
    app = _criar_app()
    return app.get_authorization_request_url(SCOPES, redirect_uri=AZURE_REDIRECT_URI)


async def concluir_autorizacao(codigo: str) -> bool:
    """Troca o código de autorização devolvido pela Microsoft por tokens, e guarda-os para uso futuro."""
    cache = await _carregar_cache()
    app = _criar_app(cache)
    resultado = app.acquire_token_by_authorization_code(codigo, scopes=SCOPES, redirect_uri=AZURE_REDIRECT_URI)
    await _guardar_cache(cache)
    if "access_token" not in resultado:
        logger.error(f"Erro ao obter token Outlook: {resultado.get('error_description')}")
        return False
    return True


async def _obter_token() -> str | None:
    cache = await _carregar_cache()
    app = _criar_app(cache)
    contas = app.get_accounts()
    if not contas:
        return None
    resultado = app.acquire_token_silent(SCOPES, account=contas[0])
    await _guardar_cache(cache)
    if resultado and "access_token" in resultado:
        return resultado["access_token"]
    return None


async def esta_ligado() -> bool:
    """Se já existe uma autorização válida (o utilizador já fez login uma vez)."""
    if not outlook_configurado():
        return False
    return await _obter_token() is not None


async def criar_evento_chamada(agendamento_id: int, nome_cliente, telefono: str, data_hora, informacao: str) -> str | None:
    """Cria o evento no Outlook Calendar. Retorna o id do evento criado, ou None se falhou."""
    if not outlook_configurado():
        return None
    token = await _obter_token()
    if not token:
        logger.info("Outlook ainda não autorizado — vá a /admin/outlook/conectar para ligar")
        return None

    data_hora_lisboa = data_hora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
    payload = {
        "subject": f"Chamada Reduz+ Energia — {nome_cliente or telefono}",
        "body": {"contentType": "text", "content": f"Telefone: {telefono}\n\n{informacao or ''}"},
        "start": {"dateTime": data_hora_lisboa.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "Europe/Lisbon"},
        "end": {
            "dateTime": (data_hora_lisboa + timedelta(minutes=DURACAO_CHAMADA_MINUTOS)).strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "Europe/Lisbon",
        },
        "isReminderOn": True,
        "reminderMinutesBeforeStart": LEMBRETE_MINUTOS_ANTES,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{GRAPH_URL}/me/events", json=payload, headers=headers)
        if r.status_code not in (200, 201):
            logger.error(f"Erro ao criar evento Outlook: {r.status_code} — {r.text}")
            return None
        logger.info(f"Evento criado no Outlook para o agendamento {agendamento_id}")
        return r.json().get("id")
    except Exception as e:
        logger.error(f"Erro ao criar evento Outlook: {e}")
        return None


async def apagar_evento_chamada(evento_outlook_id: str | None) -> bool:
    """Remove o evento do Outlook Calendar (chamada cancelada). Retorna True se teve sucesso."""
    if not outlook_configurado() or not evento_outlook_id:
        return False
    token = await _obter_token()
    if not token:
        return False
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient() as client:
            r = await client.delete(f"{GRAPH_URL}/me/events/{evento_outlook_id}", headers=headers)
        if r.status_code not in (204, 404):
            logger.error(f"Erro ao apagar evento Outlook: {r.status_code} — {r.text}")
            return False
        return True
    except Exception as e:
        logger.error(f"Erro ao apagar evento Outlook: {e}")
        return False

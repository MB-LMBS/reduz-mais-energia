# agent/calendario.py — Sincronização de chamadas agendadas com o iCloud Calendar
# Generado por AgentKit

"""
Exporta as chamadas marcadas com clientes para o calendário pessoal do
consultor no iCloud (via CalDAV), com lembrete ativado. Quando uma chamada
é cancelada, o evento correspondente é removido do calendário.

Requer ICLOUD_EMAIL e ICLOUD_APP_PASSWORD no .env — a palavra-passe tem de
ser uma "palavra-passe de aplicação" gerada em appleid.apple.com (Segurança
→ Palavras-passe específicas de aplicação), nunca a password normal da Apple.
"""

import os
import asyncio
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

import caldav
from caldav.lib.error import NotFoundError
from icalendar import Calendar as ICalendar, Event as ICalEvent, Alarm

logger = logging.getLogger("agentkit")

ICLOUD_EMAIL = os.getenv("ICLOUD_EMAIL", "")
ICLOUD_APP_PASSWORD = os.getenv("ICLOUD_APP_PASSWORD", "")
ICLOUD_CALDAV_URL = "https://caldav.icloud.com"

DURACAO_CHAMADA_MINUTOS = 30
LEMBRETE_MINUTOS_ANTES = 15
NOME_CALENDARIO_PREFERIDO = "Reduz+ Energia"


def icloud_configurado() -> bool:
    return bool(ICLOUD_EMAIL and ICLOUD_APP_PASSWORD)


def _uid_evento(agendamento_id: int) -> str:
    """UID determinístico — permite encontrar/apagar o evento mais tarde só com o id do agendamento."""
    return f"reduzmais-agendamento-{agendamento_id}@reduzmaisenergia.pt"


def _obter_calendario():
    client = caldav.DAVClient(url=ICLOUD_CALDAV_URL, username=ICLOUD_EMAIL, password=ICLOUD_APP_PASSWORD)
    principal = client.principal()
    calendarios = principal.calendars()
    if not calendarios:
        raise RuntimeError("Nenhum calendário encontrado na conta iCloud")
    for cal in calendarios:
        if (cal.name or "").strip().lower() == NOME_CALENDARIO_PREFERIDO.lower():
            return cal
    return calendarios[0]


def _construir_ical(
    agendamento_id: int, nome_cliente, telefono: str, data_hora, informacao: str,
    duracao_minutos: int = DURACAO_CHAMADA_MINUTOS, titulo: str | None = None,
) -> bytes:
    data_hora_utc = data_hora.replace(tzinfo=ZoneInfo("Europe/Lisbon")).astimezone(ZoneInfo("UTC"))

    cal = ICalendar()
    cal.add("prodid", "-//Reduz+ Energia//AgentKit//PT")
    cal.add("version", "2.0")

    evento = ICalEvent()
    evento.add("uid", _uid_evento(agendamento_id))
    evento.add("summary", titulo or f"Chamada Reduz+ Energia — {nome_cliente or telefono}")
    evento.add("dtstart", data_hora_utc)
    evento.add("dtend", data_hora_utc + timedelta(minutes=duracao_minutos))
    evento.add("description", f"Telefone: {telefono}\n\n{informacao or ''}")

    alarme = Alarm()
    alarme.add("action", "DISPLAY")
    alarme.add("description", "Lembrete de chamada — Reduz+ Energia")
    alarme.add("trigger", timedelta(minutes=-LEMBRETE_MINUTOS_ANTES))
    evento.add_component(alarme)

    cal.add_component(evento)
    return cal.to_ical()


def _criar_evento_sync(
    agendamento_id: int, nome_cliente, telefono: str, data_hora, informacao: str,
    duracao_minutos: int = DURACAO_CHAMADA_MINUTOS, titulo: str | None = None,
):
    calendario = _obter_calendario()
    ical = _construir_ical(agendamento_id, nome_cliente, telefono, data_hora, informacao, duracao_minutos, titulo)
    calendario.save_event(ical)


async def criar_evento_chamada(
    agendamento_id: int, nome_cliente, telefono: str, data_hora, informacao: str,
    duracao_minutos: int = DURACAO_CHAMADA_MINUTOS, titulo: str | None = None,
) -> bool:
    """Cria o evento no iCloud Calendar. Retorna True se teve sucesso."""
    if not icloud_configurado():
        logger.info("ICLOUD_EMAIL/ICLOUD_APP_PASSWORD não configurados — a saltar sincronização com iCloud")
        return False
    try:
        await asyncio.to_thread(
            _criar_evento_sync, agendamento_id, nome_cliente, telefono, data_hora, informacao,
            duracao_minutos, titulo,
        )
        logger.info(f"Evento criado no iCloud Calendar para o agendamento {agendamento_id}")
        return True
    except Exception as e:
        logger.error(f"Erro ao criar evento no iCloud Calendar: {e}")
        return False


def _apagar_evento_sync(agendamento_id: int):
    # Não usa calendario.event_by_uid()/search(uid=...) — o iCloud responde
    # 412 Precondition Failed a essa pesquisa (incompatibilidade do lado
    # deles). Listar os eventos e filtrar do nosso lado funciona sem problema.
    calendario = _obter_calendario()
    uid_alvo = _uid_evento(agendamento_id)
    for evento in calendario.events():
        try:
            if evento.icalendar_component.get("uid") == uid_alvo:
                evento.delete()
                return
        except Exception:
            continue
    raise NotFoundError(f"Evento {uid_alvo} não encontrado no iCloud Calendar")


async def apagar_evento_chamada(agendamento_id: int) -> bool:
    """Remove o evento do iCloud Calendar (chamada cancelada). Retorna True se teve sucesso."""
    if not icloud_configurado():
        return False
    try:
        await asyncio.to_thread(_apagar_evento_sync, agendamento_id)
        logger.info(f"Evento removido do iCloud Calendar para o agendamento {agendamento_id}")
        return True
    except NotFoundError:
        logger.warning(f"Evento do agendamento {agendamento_id} já não existia no iCloud Calendar")
        return True
    except Exception as e:
        logger.error(f"Erro ao apagar evento do iCloud Calendar: {e}")
        return False

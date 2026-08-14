# agent/cal_com.py — Integração com a API do Cal.com para agendamento de chamadas
# Generado por AgentKit

"""
Substitui o cálculo local de horários (agent/agenda.py) pela disponibilidade
real do Cal.com — a fonte da verdade sobre o calendário do consultor passa a
ser o Cal.com (ligado ao iCloud/Google/Outlook), sem precisarmos de manter a
nossa própria lógica de conflitos. Os botões e o resto da conversa no
WhatsApp continuam exatamente iguais — só a origem dos horários muda.
"""

import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger("agentkit")

CALCOM_API_KEY = os.getenv("CALCOM_API_KEY", "")
CALCOM_USERNAME = os.getenv("CALCOM_USERNAME", "geral-reduzmais.com")
CALCOM_EVENT_SLUG = os.getenv("CALCOM_EVENT_SLUG", "chamada-reduz-energia")
BASE_URL = "https://api.cal.com"
FUSO = ZoneInfo("Europe/Lisbon")


def calcom_configurado() -> bool:
    return bool(CALCOM_API_KEY)


def _headers(versao: str) -> dict:
    return {
        "Authorization": f"Bearer {CALCOM_API_KEY}",
        "cal-api-version": versao,
        "Content-Type": "application/json",
    }


async def obter_event_type() -> dict | None:
    """Consulta os detalhes do event type configurado (id, bookingFields, etc.)."""
    if not calcom_configurado():
        return None
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE_URL}/v2/event-types",
            headers=_headers("2024-06-14"),
            params={"username": CALCOM_USERNAME, "eventSlug": CALCOM_EVENT_SLUG},
        )
        if r.status_code != 200:
            logger.error(f"Erro Cal.com (event-types): {r.status_code} — {r.text}")
            return None
        dados = r.json().get("data") or []
        return dados[0] if dados else None


async def obter_horarios_disponiveis(dias_a_frente: int = 7) -> list[datetime]:
    """
    Consulta os horários livres no Cal.com para os próximos N dias.
    Retorna uma lista de datetimes (hora de Portugal, timezone-aware).
    """
    agora = datetime.now(FUSO)
    inicio = agora.date()
    fim = inicio + timedelta(days=dias_a_frente)
    return await obter_horarios_disponiveis_intervalo(inicio, fim)


async def obter_horarios_disponiveis_intervalo(inicio, fim) -> list[datetime]:
    """
    Consulta os horários livres no Cal.com entre duas datas (inclusive) —
    sem limite de distância no futuro, o Cal.com não impõe um tecto. Usa-se
    tanto para o intervalo próximo por omissão como para um dia específico
    pedido pelo cliente, mesmo que seja daqui a meses.
    Retorna uma lista de datetimes (hora de Portugal, timezone-aware).
    """
    if not calcom_configurado():
        return []
    if fim < inicio:
        return []

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{BASE_URL}/v2/slots",
            headers=_headers("2024-09-04"),
            params={
                "eventTypeSlug": CALCOM_EVENT_SLUG,
                "username": CALCOM_USERNAME,
                "start": inicio.isoformat(),
                "end": fim.isoformat(),
                "timeZone": "Europe/Lisbon",
            },
        )
        if r.status_code != 200:
            logger.error(f"Erro Cal.com (slots): {r.status_code} — {r.text}")
            return []

        dados = r.json().get("data") or {}
        horarios = []
        for _dia, slots_do_dia in dados.items():
            for slot in slots_do_dia:
                inicio_str = slot.get("start")
                if not inicio_str:
                    continue
                dt = datetime.fromisoformat(inicio_str.replace("Z", "+00:00"))
                horarios.append(dt.astimezone(FUSO))
        horarios.sort()
        return horarios


async def criar_reserva(
    inicio: datetime, nome_cliente: str, telefone: str, informacao: str = "",
    sem_restricoes: bool = False, duracao_minutos: int | None = None,
) -> dict | None:
    """
    Cria uma marcação real no Cal.com. `inicio` deve ser timezone-aware.
    Retorna os dados da reserva criada (incluindo "uid", útil para cancelar),
    ou None se falhar.

    `sem_restricoes=True` ignora a disponibilidade configurada (dias/horas,
    antecedência mínima, conflitos) — usado só para a agenda pessoal do
    próprio consultor, nunca para clientes.
    """
    if not calcom_configurado():
        return None

    corpo = {
        "start": inicio.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attendee": {
            "name": nome_cliente or telefone,
            # O evento no Cal.com foi configurado para exigir telefone em vez de
            # email (os clientes só têm WhatsApp) — ver "Booking questions" no
            # próprio Cal.com
            "timeZone": "Europe/Lisbon",
            "phoneNumber": f"+{telefone}" if not telefone.startswith("+") else telefone,
            "language": "pt",
        },
        "eventTypeSlug": CALCOM_EVENT_SLUG,
        "username": CALCOM_USERNAME,
        "metadata": {"telefone": telefone, "origem": "whatsapp"},
    }
    if informacao:
        corpo["bookingFieldsResponses"] = {"notes": informacao}
    if sem_restricoes:
        corpo["allowBookingOutOfBounds"] = True
        corpo["skipBookingLimits"] = True
        corpo["allowConflicts"] = True
    # duracao_minutos não é enviada ao Cal.com: o event type partilhado com os
    # clientes tem duração fixa (15 min) e não aceita "lengthInMinutes" sem
    # estar configurado com múltiplas durações — aplica-se só no iCloud, que é
    # o calendário que o consultor realmente usa no dia a dia

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE_URL}/v2/bookings", headers=_headers("2026-02-25"), json=corpo)
        if r.status_code not in (200, 201):
            logger.error(f"Erro Cal.com (criar reserva): {r.status_code} — {r.text}")
            return None
        return r.json().get("data")


async def cancelar_reserva(uid: str, motivo: str = "Cancelado pelo cliente") -> bool:
    """Cancela uma marcação existente no Cal.com pelo seu uid."""
    if not calcom_configurado() or not uid:
        return False
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{BASE_URL}/v2/bookings/{uid}/cancel",
            headers=_headers("2024-08-13"),
            json={"cancellationReason": motivo},
        )
        if r.status_code != 200:
            logger.error(f"Erro Cal.com (cancelar reserva {uid}): {r.status_code} — {r.text}")
        return r.status_code == 200

# agent/agenda.py — Grelha de horários para agendamento de chamadas
# Generado por AgentKit

"""
Calcula os horários disponíveis para chamadas: tarde (15h-19h), de
Segunda a Sábado, em blocos de 15 minutos. Cruza com os agendamentos já
existentes para saber quais estão livres, respeitando uma antecedência
mínima de 1 hora entre o momento da marcação e o horário da chamada.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agent.memory import obtener_horarios_ocupados

FUSO = ZoneInfo("Europe/Lisbon")
HORA_INICIO = 15
HORA_FIM = 19
DIAS_UTEIS = {0, 1, 2, 3, 4, 5}  # Segunda(0) a Sábado(5) — Domingo(6) excluído
INTERVALO_MINUTOS = 15
ANTECEDENCIA_MINIMA = timedelta(hours=1)

DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]


def _slots_do_dia(dia: datetime) -> list[datetime]:
    """Gera todos os slots de 15 minutos da tarde de um dia (15h-19h)."""
    inicio = dia.replace(hour=HORA_INICIO, minute=0, second=0, microsecond=0)
    fim = dia.replace(hour=HORA_FIM, minute=0, second=0, microsecond=0)
    slots = []
    atual = inicio
    while atual < fim:
        slots.append(atual)
        atual += timedelta(minutes=INTERVALO_MINUTOS)
    return slots


def formatar_slot(slot: datetime) -> str:
    """Formata um horário de forma legível, ex: 'Segunda-feira, 18/08 às 14h00'."""
    dia_semana = DIAS_SEMANA[slot.weekday()]
    return f"{dia_semana}, {slot.strftime('%d/%m')} às {slot.strftime('%Hh%M')}"


def horario_minimo_permitido() -> datetime:
    """O horário mais cedo possível para uma nova marcação, respeitando a antecedência mínima de 1 hora."""
    return datetime.now(FUSO).replace(tzinfo=None) + ANTECEDENCIA_MINIMA


async def proximos_horarios_disponiveis(quantidade: int = 6, dias_a_frente: int = 14) -> list[datetime]:
    """
    Retorna os próximos horários livres (hora local de Portugal, naive),
    olhando até `dias_a_frente` dias para a frente. Respeita a antecedência
    mínima de 1 hora — nunca sugere um horário demasiado próximo do momento atual.
    """
    limite_antecedencia = horario_minimo_permitido()
    inicio_busca = limite_antecedencia.replace(hour=0, minute=0, second=0, microsecond=0)
    fim_busca = inicio_busca + timedelta(days=dias_a_frente)

    ocupados = await obtener_horarios_ocupados(inicio_busca, fim_busca)

    disponiveis = []
    dia = inicio_busca
    while dia < fim_busca and len(disponiveis) < quantidade:
        if dia.weekday() in DIAS_UTEIS:
            for slot in _slots_do_dia(dia):
                if slot >= limite_antecedencia and slot not in ocupados:
                    disponiveis.append(slot)
                    if len(disponiveis) >= quantidade:
                        break
        dia += timedelta(days=1)

    return disponiveis


def slot_e_valido(data_hora: datetime) -> bool:
    """Confirma que um horário pedido está dentro da grelha permitida (tarde, dia útil, quarto de hora)."""
    if data_hora.weekday() not in DIAS_UTEIS:
        return False
    if not (HORA_INICIO <= data_hora.hour < HORA_FIM):
        return False
    if data_hora.minute not in (0, 15, 30, 45) or data_hora.second != 0:
        return False
    return True

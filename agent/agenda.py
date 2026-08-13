# agent/agenda.py — Formatação de horários para agendamento de chamadas
# Generado por AgentKit

"""
A disponibilidade real das chamadas passou a vir do Cal.com (ver
agent/cal_com.py) — este ficheiro fica só com o formatador de horários,
usado tanto pelo fluxo do Cal.com como pelo painel /admin.
"""

from datetime import datetime

DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]


def formatar_slot(slot: datetime) -> str:
    """Formata um horário de forma legível, ex: 'Segunda-feira, 18/08 às 14h00'."""
    dia_semana = DIAS_SEMANA[slot.weekday()]
    return f"{dia_semana}, {slot.strftime('%d/%m')} às {slot.strftime('%Hh%M')}"

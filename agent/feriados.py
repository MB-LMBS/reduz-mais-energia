# agent/feriados.py — Feriados nacionais obrigatórios de Portugal
# Generado por AgentKit

"""
Calcula os feriados nacionais obrigatórios de Portugal para um dado ano,
incluindo os móveis (baseados na Páscoa), e permite consultar os próximos.
"""

from datetime import date, timedelta

NOMES_FERIADOS_FIXOS = {
    (1, 1): "Ano Novo",
    (4, 25): "Dia da Liberdade",
    (5, 1): "Dia do Trabalhador",
    (6, 10): "Dia de Portugal",
    (8, 15): "Assunção de Nossa Senhora",
    (10, 5): "Implantação da República",
    (11, 1): "Todos os Santos",
    (12, 1): "Restauração da Independência",
    (12, 8): "Imaculada Conceição",
    (12, 25): "Natal",
}


def _pascoa(ano: int) -> date:
    """Calcula a data da Páscoa (domingo) para um ano — algoritmo Anonymous Gregorian."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_do_ano(ano: int) -> dict[date, str]:
    """Retorna um dict {data: nome} com todos os feriados nacionais obrigatórios do ano."""
    feriados = {date(ano, mes, dia): nome for (mes, dia), nome in NOMES_FERIADOS_FIXOS.items()}
    pascoa = _pascoa(ano)
    feriados[pascoa - timedelta(days=2)] = "Sexta-feira Santa"
    feriados[pascoa] = "Domingo de Páscoa"
    feriados[pascoa + timedelta(days=60)] = "Corpo de Deus"
    return feriados


def proximos_feriados(hoje: date | None = None, quantidade: int = 3) -> list[tuple[date, str]]:
    """Retorna os próximos feriados (incluindo hoje, se for feriado), ordenados por data."""
    hoje = hoje or date.today()
    todos = {**feriados_do_ano(hoje.year), **feriados_do_ano(hoje.year + 1)}
    futuros = sorted((d, nome) for d, nome in todos.items() if d >= hoje)
    return futuros[:quantidade]


def feriado_de_hoje(hoje: date | None = None) -> str | None:
    """Retorna o nome do feriado, se hoje for feriado nacional em Portugal, ou None."""
    hoje = hoje or date.today()
    return feriados_do_ano(hoje.year).get(hoje)

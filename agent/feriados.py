# agent/feriados.py — Feriados nacionais e municipais de Portugal
# Generado por AgentKit

"""
Calcula os feriados nacionais obrigatórios de Portugal para um dado ano,
incluindo os móveis (baseados na Páscoa), e permite consultar os próximos.
Também cruza com os feriados municipais (facultativos) dos concelhos de
Portugal Continental, definidos em agent/feriados_municipais.py.
"""

from datetime import date, timedelta

from agent.feriados_municipais import FERIADOS_MUNICIPAIS_FIXOS, FERIADOS_MUNICIPAIS_MOVEIS

DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
               "Sexta-feira", "Sábado", "Domingo"]

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


def nome_dia_semana(dia: date) -> str:
    """Nome do dia da semana em português, ex: 'Sexta-feira'."""
    return DIAS_SEMANA[dia.weekday()]


def _resolver_regra_movel(ano: int, regra: str) -> date:
    """Resolve uma regra de feriado móvel (ex: 'pascoa+39') para uma data de um ano."""
    deslocamento = int(regra.split("+")[1])
    return _pascoa(ano) + timedelta(days=deslocamento)


def feriados_municipais_do_ano(ano: int) -> dict[date, list[str]]:
    """Retorna {data: [concelhos]} com todos os feriados municipais do ano, em Portugal Continental."""
    por_data: dict[date, list[str]] = {}
    for concelho, (mes, dia) in FERIADOS_MUNICIPAIS_FIXOS.items():
        por_data.setdefault(date(ano, mes, dia), []).append(concelho)
    for concelho, regra in FERIADOS_MUNICIPAIS_MOVEIS.items():
        por_data.setdefault(_resolver_regra_movel(ano, regra), []).append(concelho)
    for concelhos in por_data.values():
        concelhos.sort()
    return por_data


def feriados_municipais_de_hoje(hoje: date | None = None) -> list[str]:
    """Retorna a lista de concelhos (Portugal Continental) em feriado municipal hoje."""
    hoje = hoje or date.today()
    return feriados_municipais_do_ano(hoje.year).get(hoje, [])


def proximo_feriado_municipal(hoje: date | None = None) -> tuple[date, list[str]] | None:
    """Retorna (data, [concelhos]) do próximo dia com pelo menos um feriado municipal,
    a partir de hoje (exclui hoje — usar feriados_municipais_de_hoje para o próprio dia)."""
    hoje = hoje or date.today()
    todos = {**feriados_municipais_do_ano(hoje.year), **feriados_municipais_do_ano(hoje.year + 1)}
    futuros = sorted((d, concelhos) for d, concelhos in todos.items() if d > hoje)
    return futuros[0] if futuros else None

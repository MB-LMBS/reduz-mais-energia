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

from agent.agenda import formatar_slot
from agent.cal_com import (
    obter_horarios_disponiveis, obter_horarios_disponiveis_intervalo,
    criar_reserva, cancelar_reserva, calcom_configurado,
)
from agent.memory import (
    criar_agendamento, guardar_evento_calcom_uid,
    obter_agendamento_ativo_por_telefone, cancelar_agendamento, criar_alerta,
    marcar_alertas_agendamento_vistos,
)
from agent.calendario import criar_evento_chamada as criar_evento_icloud, apagar_evento_chamada as apagar_evento_icloud
from agent.outlook_calendar import apagar_evento_chamada as apagar_evento_outlook
from agent.notificacoes import notificar_cancelamento, NUMERO_CONSULTOR
from agent.providers import obtener_proveedor

load_dotenv()
logger = logging.getLogger("agentkit")

# Cliente de Anthropic
client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SIMULADORES = {
    "geral": {
        "url": (
            "https://reduz-mais-energia.neocities.org/Reduz+%20Energia/"
            "Simuladores%20Energia/Cart%C3%A3o_Simulador"
        ),
        "texto_botao": "Ver simulador",
    },
    "eletricidade_btn": {
        "url": (
            "https://reduz-mais-energia.neocities.org/Reduz+%20Energia/"
            "Simuladores%20Energia/EE_Campanhas"
        ),
        "texto_botao": "Ver simulador EE",
    },
    "eletricidade_personalizada": {
        "url": "https://tally.so/r/gDNkAP",
        "texto_botao": "Pedido personalizado",
    },
    "gas_natural": {
        "url": (
            "https://reduz-mais-energia.neocities.org/Reduz+%20Energia/"
            "Simuladores%20Energia/GN_Campanhas"
        ),
        "texto_botao": "Ver simulador GN",
    },
    "solar_fotovoltaico": {
        "url": (
            "https://reduz-mais-energia.neocities.org/Reduz+%20Energia/"
            "Simuladores%20Energia/Smart%20Solar%20Empresarial%20&%20Residencial"
        ),
        "texto_botao": "Ver simulador solar",
    },
}

REDES_SOCIAIS = [
    {"texto_botao": "LinkedIn", "url": "https://www.linkedin.com/company/reduzmaisenergia/"},
    {"texto_botao": "Facebook", "url": "https://www.facebook.com/Reduzmaisenergia"},
]

# Herramientas que el modelo puede activar durante la conversación
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
    },
    {
        "name": "agendar_chamada",
        "description": (
            "Usa esta ferramenta para marcar uma chamada telefónica com um consultor, "
            "depois de o cliente escolher um dos horários disponíveis que lhe foram "
            "sugeridos (secção 'Agendamento de chamadas' abaixo). Só uses esta "
            "ferramenta depois de confirmares com o cliente o horário exato, o nome "
            "dele e o motivo da chamada — nunca marques sem essa confirmação. "
            "Na agenda pessoal do consultor (ver secção 'esta é a SUA agenda "
            "pessoal', se aplicável) serve para qualquer tipo de compromisso, não "
            "só chamadas — usa também os campos tipo_evento, formato, "
            "duracao_minutos e convidados nesse caso."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Data escolhida, no formato AAAA-MM-DD.",
                },
                "hora": {
                    "type": "string",
                    "description": "Hora escolhida, no formato HH:MM (ex: 14:00, 14:15, 14:30...).",
                },
                "nome": {
                    "type": "string",
                    "description": "Nome do cliente para quem o consultor deve perguntar na chamada.",
                },
                "informacao": {
                    "type": "string",
                    "description": (
                        "Resumo do que o cliente quer discutir na chamada — situação "
                        "atual, o que procura, e qualquer outro dado relevante que "
                        "tenha partilhado na conversa."
                    ),
                },
                "tipo_evento": {
                    "type": "string",
                    "enum": ["pessoal", "profissional"],
                    "description": (
                        "Só para a agenda pessoal do consultor (nunca para clientes): "
                        "se o compromisso é pessoal ou profissional."
                    ),
                },
                "formato": {
                    "type": "string",
                    "enum": ["presencial", "telefonica", "teams", "deslocacao", "recordatorio"],
                    "description": (
                        "Só para a agenda pessoal do consultor (nunca para clientes): "
                        "o formato do compromisso."
                    ),
                },
                "duracao_minutos": {
                    "type": "integer",
                    "description": (
                        "Só para a agenda pessoal do consultor (nunca para clientes): "
                        "duração estimada do compromisso, em minutos."
                    ),
                },
                "convidados": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Só para a agenda pessoal do consultor (nunca para clientes): "
                        "números de telefone de outras pessoas a convocar, se houver."
                    ),
                },
            },
            "required": ["data", "hora", "nome", "informacao"],
        },
    },
    {
        "name": "cancelar_chamada",
        "description": (
            "Usa esta ferramenta IMEDIATAMENTE, na mesma resposta, assim que "
            "o cliente pedir para cancelar ou desmarcar uma chamada já "
            "agendada — mesmo que seja só \"cancela\" ou \"sim\". NUNCA "
            "perguntes primeiro se ele confirma, e nunca deixes essa "
            "confirmação para a mensagem seguinte: chama já a ferramenta "
            "nesta resposta. A ferramenta procura sozinha a chamada ativa "
            "deste número — só depois de ela correr é que sabes se foi "
            "cancelada, e só aí confirmas ao cliente. É PROIBIDO dizeres ao "
            "cliente que uma chamada foi cancelada sem teres chamado esta "
            "ferramenta nesta mesma resposta — nunca assumas ou inventes "
            "esse resultado. Se ele quiser remarcar para outro horário, "
            "cancela primeiro com esta ferramenta e depois segue o processo "
            "normal de agendamento para o novo horário."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "description": "Motivo do cancelamento, se o cliente o tiver indicado (opcional).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "consultar_disponibilidade_dia",
        "description": (
            "Usa esta ferramenta para veres os horários realmente livres num "
            "dia específico pedido pelo cliente — sobretudo quando esse dia "
            "não está entre os já sugeridos no contexto (ex: uma data mais "
            "distante no futuro, daqui a semanas ou meses). Não há limite de "
            "distância — o cliente pode marcar para qualquer data futura. "
            "Nunca inventes horários para um dia sem consultares primeiro "
            "esta ferramenta para esse dia exato."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Data a consultar, no formato AAAA-MM-DD.",
                },
            },
            "required": ["data"],
        },
    },
    {
        "name": "oferecer_opcoes",
        "description": (
            "Usa esta ferramenta quando quiseres fazer uma pergunta simples e "
            "fechada, com 2 ou 3 respostas possíveis (ex: 'É para uso "
            "particular ou empresa?', 'Confirma estes dados?', escolher entre "
            "2-3 horários de chamada). Mostra botões clicáveis ao cliente no "
            "WhatsApp — mais rápido e fácil do que escrever. NÃO uses para "
            "perguntas abertas que precisem de texto livre (ex: pedir o "
            "nome, pedir para descrever o que procura), e não abuses disto "
            "em todas as mensagens — só quando facilitar mesmo a escolha do "
            "cliente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pergunta": {
                    "type": "string",
                    "description": "O texto da pergunta a mostrar ao cliente, acima dos botões.",
                },
                "opcoes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 2,
                    "maxItems": 3,
                    "description": "Entre 2 e 3 respostas curtas (máx. 20 caracteres cada) para o cliente escolher.",
                },
            },
            "required": ["pergunta", "opcoes"],
        },
    },
    {
        "name": "enviar_link_simulador",
        "description": (
            "Usa esta ferramenta sempre que quiseres partilhar um link de "
            "simulador com o cliente. Mostra um botão clicável em vez de "
            "escreveres o link em texto — mais fácil de abrir a partir do "
            "WhatsApp no telemóvel. Escolhe o tipo consoante o caso: "
            "'eletricidade_btn' quando o cliente (particular ou empresa) "
            "procura eletricidade com nível de tensão BTN e já sabes a "
            "potência contratada (uma das potências normais — ver secção "
            "'Propostas de eletricidade' no teu contexto); "
            "'eletricidade_personalizada' quando a potência/tensão são das "
            "gamas mais altas que exigem proposta à medida (ver a mesma "
            "secção — inclui uma nota importante sobre oferecer solar "
            "nestes casos); 'gas_natural' quando o cliente "
            "(particular ou empresa) procura gás natural, em qualquer "
            "escalão (1, 2, 3 ou 4); 'solar_fotovoltaico' quando o cliente "
            "(particular ou empresa) procura uma solução solar fotovoltaica "
            "com fornecimento e instalação, com investimento próprio, e já "
            "sabes ou estimaste quantos painéis (ver secção 'Propostas de "
            "energia solar fotovoltaica' no teu contexto); 'geral' para "
            "todos os outros casos (ex: ainda não sabes a potência/nível de "
            "tensão do cliente para eletricidade, ou solar sem investimento "
            "próprio/comunidades solares)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mensagem": {
                    "type": "string",
                    "description": (
                        "Texto a acompanhar o botão — não seja demasiado "
                        "curto nem seco. Dá ao cliente contexto suficiente "
                        "para se situar: o que é este simulador/pedido "
                        "específico, o que vai encontrar ou preencher ao "
                        "clicar (ex: dados que lhe vão pedir, ou as opções "
                        "que vai poder comparar), e o que pode fazer a "
                        "seguir. 2-3 frases é normalmente o ideal."
                    ),
                },
                "tipo": {
                    "type": "string",
                    "enum": [
                        "geral", "eletricidade_btn", "eletricidade_personalizada",
                        "gas_natural", "solar_fotovoltaico",
                    ],
                    "description": "Qual simulador mostrar — ver descrição da ferramenta.",
                },
                "nivel_tensao": {
                    "type": "string",
                    "enum": ["BTN", "BTE", "MT"],
                    "description": (
                        "Só quando tipo='eletricidade_btn' ou "
                        "'eletricidade_personalizada': o nível de tensão do "
                        "cliente. Obrigatório nesses dois casos."
                    ),
                },
            },
            "required": ["mensagem", "tipo"],
        },
    },
    {
        "name": "recomendar_redes_sociais",
        "description": (
            "Usa esta ferramenta para recomendares as páginas da Reduz+ "
            "Energia no LinkedIn e no Facebook — normalmente numa pausa "
            "natural da conversa, ex: depois de agradeceres ao cliente ou "
            "no fecho da conversa. Mostra dois botões clicáveis (um para "
            "cada rede social) em vez de escreveres os links em texto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "mensagem": {
                    "type": "string",
                    "description": "Texto curto de agradecimento/despedida a acompanhar os botões.",
                },
            },
            "required": ["mensagem"],
        },
        # Marca o fim do bloco de ferramentas para o cache de prompt da Anthropic —
        # a lista é estática entre pedidos, por isso vale a pena cachear.
        "cache_control": {"type": "ephemeral"},
    },
]

DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
               "sexta-feira", "sábado", "domingo"]


def cargar_config_prompts() -> dict:
    """Lee toda la configuración desde config/prompts.yaml."""
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


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


async def obtener_contexto_agenda(telefono: str = "") -> str:
    """
    Genera un bloque con los próximos horarios libres para chamadas telefónicas,
    consultados em tempo real ao Cal.com, para que o modelo os ofereça
    diretamente sem inventar horas.

    Quando é o próprio consultor a escrever (o número dele, NUMERO_CONSULTOR),
    a agenda é pessoal e não tem as restrições impostas aos clientes.
    """
    if telefono and NUMERO_CONSULTOR and telefono == NUMERO_CONSULTOR:
        return (
            "\n\n## Agendamento — esta é a SUA agenda pessoal\n"
            "Está a falar com o próprio consultor (Luis Sequeira), na conversa "
            "que ele usa como a sua agenda pessoal — não é um cliente, e nem "
            "todos os compromissos são chamadas telefónicas. Aqui não há "
            "restrições de dia/hora nenhumas: pode pedir para marcar QUALQUER "
            "dia e hora (mesmo fora de Segunda-Sábado 15h-19h, ou com pouca "
            "antecedência), e o assunto pode ser sobre o que ele quiser (não "
            "precisa de ser sobre um cliente ou proposta). Interpreta a "
            "data/hora que ele pedir, mesmo relativa (ex: \"amanhã às 8\").\n\n"
            "Antes de chamares agendar_chamada, confirma sempre estes 4 "
            "detalhes com botões (ferramenta oferecer_opcoes, máx. 3 opções "
            "por pergunta — se precisares de mais que 3, faz 2 perguntas "
            "seguidas em vez de uma):\n"
            "1. Pessoal ou Profissional? (2 botões)\n"
            "2. Formato: Presencial, Telefónica ou Teams — se nenhum servir, "
            "faz uma segunda pergunta com Deslocação ou Recordatório.\n"
            "3. Duração estimada — sugere botões rápidos tipo \"15 min\", "
            "\"30 min\", \"1 hora\", e aceita que ele escreva outro valor em "
            "texto livre se quiser.\n"
            "4. Pergunta se quer convidar mais alguém (sim/não em botões); se "
            "sim, pede o(s) número(s) de telefone em texto livre (pode ser "
            "mais que um).\n"
            "Só depois de teres estes 4 detalhes (mesmo que resumidos) chamas "
            "agendar_chamada com tudo preenchido — não precisas de consultar "
            "disponibilidade nem de sugerir horários de uma lista, a agenda "
            "dele está sempre livre para isto."
        )

    if not calcom_configurado():
        return (
            "\n\n## Agendamento de chamadas\n"
            "O agendamento de chamadas está temporariamente indisponível — "
            "informa o cliente e sugere que a equipa entre em contacto por outra via."
        )

    todos_slots = await obter_horarios_disponiveis(dias_a_frente=10)
    if not todos_slots:
        return (
            "\n\n## Agendamento de chamadas\n"
            "De momento não há horários disponíveis nos próximos dias — informa "
            "o cliente e sugere que a equipa entre em contacto por outra via."
        )

    # Agrupa por dia (até 4 dias distintos), para o cliente escolher primeiro
    # o dia e só depois a hora, em vez de ver uma lista de horas seguidas
    por_dia: dict = {}
    for slot in todos_slots:
        por_dia.setdefault(slot.date(), []).append(slot)

    linhas = []
    for dia, horarios_do_dia in list(por_dia.items())[:4]:
        nome_dia = DIAS_SEMANA[dia.weekday()]
        horas = ", ".join(h.strftime("%Hh%M") for h in horarios_do_dia)
        linhas.append(f"- {nome_dia}, {dia.strftime('%d/%m')} — horas livres: {horas}")
    bloco_dias = "\n".join(linhas)

    return (
        "\n\n## Agendamento de chamadas\n"
        "Não ofereças uma chamada logo na primeira mensagem nem em resposta a "
        "um simples cumprimento (ex: 'boa noite', 'olá', 'tudo bem?') — "
        "responde ao cumprimento com naturalidade e percebe primeiro o que o "
        "cliente procura. Só ofereças a chamada depois de o cliente mostrar "
        "interesse real no serviço (ex: já perguntou sobre uma solução "
        "específica, quer avançar, ou pede para falar com alguém).\n"
        "Os próximos dias com disponibilidade real, e as horas livres em "
        "cada um, são (só como sugestões rápidas — ver nota abaixo sobre "
        "datas mais distantes):\n"
        f"{bloco_dias}\n\n"
        "Para agendar, segue SEMPRE este processo em dois passos separados, "
        "usando a ferramenta oferecer_opcoes em cada um (nunca escrevas dias "
        "ou horas em texto normal, para o cliente não ter de os escrever à mão):\n"
        "1. Pergunta primeiro que DIA prefere. Se ele não pedir uma data "
        "concreta, oferece 2 ou 3 dos dias acima como botões (ex: "
        "'Quinta-feira, 14/08').\n"
        "2. Só depois de escolher o dia, pergunta a que HORA, oferecendo 2 "
        "ou 3 horários livres desse dia específico como botões (ex: '15h00').\n"
        "Nunca ofereças dia e hora ao mesmo tempo numa única pergunta, e "
        "nunca misturas horários de dias diferentes na mesma lista de botões. "
        "Depois de o cliente escolher o dia e a hora, confirma o nome dele "
        "e o motivo da chamada, e só depois usa a ferramenta "
        "agendar_chamada para a marcar.\n\n"
        "Não há limite de distância no futuro — o cliente pode marcar para "
        "qualquer data, mesmo daqui a semanas ou meses. Se ele pedir uma "
        "data específica que não está na lista acima, usa SEMPRE a "
        "ferramenta consultar_disponibilidade_dia para esse dia exato antes "
        "de responderes — nunca inventes horários nem digas que não está "
        "disponível sem teres consultado primeiro essa data real."
    )


def obtener_contexto_cliente(nome_contato: str | None, primeira_mensagem: bool) -> str:
    """
    Genera un bloque con el nombre del cliente actual (si se conoce) y si esta es
    su primera mensaje de la conversación, para saludar de forma cálida y personal.
    """
    linhas = ["\n\n## Cliente atual"]
    if nome_contato:
        linhas.append(
            f"O nome de perfil de WhatsApp deste cliente é {nome_contato}. Trata-o "
            "pelo nome sempre que fizer sentido, para tornar a conversa mais "
            "pessoal e calorosa."
        )
    else:
        linhas.append("Ainda não sabes o nome deste cliente — podes perguntar-lho com naturalidade.")

    if primeira_mensagem:
        linhas.append(
            "Esta é a primeira mensagem desta conversa. Cumprimenta com calor e "
            "usa literalmente a frase de marca \"Seja bem-vindo à Reduz+ Energia\" "
            "(ou \"Seja bem-vinda à Reduz+ Energia\" se o nome do cliente for "
            "claramente feminino) logo no início, e só depois respondas ao que o "
            "cliente disse — nunca respondas com uma mensagem seca ou demasiado curta."
        )
    else:
        linhas.append("Já estão a meio de uma conversa — não repitas as boas-vindas, continua naturalmente.")

    return "\n".join(linhas)


async def montar_system_blocks(
    nome_contato: str | None, primeira_mensagem: bool, telefono: str = "",
) -> list[dict]:
    """
    Monta o system prompt em dois blocos, para aproveitar o cache de prompt da
    Anthropic: a base de conhecimento (config/prompts.yaml, ~11 mil tokens,
    igual em todos os pedidos) fica marcada com cache_control e é reutilizada
    entre chamadas; o contexto dinâmico (hora atual, cliente, horários livres
    de chamada) muda a cada pedido, por isso fica fora do bloco cacheado.
    """
    config = cargar_config_prompts()
    base = config.get("system_prompt", "Eres un asistente útil. Responde en español.")
    contexto_agenda = await obtener_contexto_agenda(telefono)
    contexto_cliente = obtener_contexto_cliente(nome_contato, primeira_mensagem)
    contexto_dinamico = obtener_contexto_temporal() + contexto_cliente + contexto_agenda
    return [
        {"type": "text", "text": base, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": contexto_dinamico},
    ]


def obtener_mensaje_error() -> str:
    """Retorna el mensaje de error configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("error_message", "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos.")


def obtener_mensaje_fallback() -> str:
    """Retorna el mensaje de fallback configurado en prompts.yaml."""
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?")


async def _processar_agendamento(entrada: dict, telefono: str) -> tuple[str, dict | None]:
    """
    Valida y regista un pedido de agendamento vindo da ferramenta agendar_chamada.

    Returns:
        Tupla (mensagem_para_o_modelo, dados_do_agendamento) — dados_do_agendamento
        é None se o agendamento falhou (horário inválido ou já ocupado).
    """
    data = (entrada.get("data") or "").strip()
    hora = (entrada.get("hora") or "").strip()
    nome = (entrada.get("nome") or "").strip()
    informacao = (entrada.get("informacao") or "").strip()

    e_agenda_pessoal = bool(NUMERO_CONSULTOR) and telefono == NUMERO_CONSULTOR
    tipo_evento = (entrada.get("tipo_evento") or "").strip()
    formato = (entrada.get("formato") or "").strip()
    duracao_minutos = entrada.get("duracao_minutos")
    convidados = [str(c).strip() for c in (entrada.get("convidados") or []) if str(c).strip()]

    titulo_evento = None
    if e_agenda_pessoal:
        rotulos_formato = {
            "presencial": "Presencial", "telefonica": "Telefónica", "teams": "Teams",
            "deslocacao": "Deslocação", "recordatorio": "Recordatório",
        }
        partes_titulo = [p for p in (tipo_evento.capitalize(), rotulos_formato.get(formato)) if p]
        titulo_evento = " — ".join(partes_titulo) or None
        if titulo_evento and nome:
            titulo_evento = f"{titulo_evento}: {nome}"

        linhas_info = []
        if tipo_evento:
            linhas_info.append(f"Tipo: {tipo_evento.capitalize()}")
        if formato:
            linhas_info.append(f"Formato: {rotulos_formato.get(formato, formato)}")
        if convidados:
            linhas_info.append(f"Convidados: {', '.join(convidados)}")
        if informacao:
            linhas_info.append(informacao)
        informacao = "\n".join(linhas_info)

    try:
        data_hora = datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M")
    except ValueError:
        return (
            "Não foi possível marcar: a data ou hora não estão num formato válido "
            "(AAAA-MM-DD e HH:MM). Confirma o horário com o cliente e tenta de novo.",
            None,
        )

    if not calcom_configurado():
        return (
            "Não foi possível marcar: o agendamento está temporariamente "
            "indisponível. Sugere que a equipa entre em contacto por outra via.",
            None,
        )

    data_hora_tz = data_hora.replace(tzinfo=ZoneInfo("Europe/Lisbon"))
    reserva = await criar_reserva(
        data_hora_tz, nome, telefone=telefono, informacao=informacao,
        sem_restricoes=e_agenda_pessoal, duracao_minutos=duracao_minutos,
    )
    if reserva is None:
        return (
            "Não foi possível marcar: esse horário pode já não estar livre, ou "
            "está fora da disponibilidade real da agenda. Sugere ao cliente um "
            "dos horários indicados no contexto.",
            None,
        )

    agendamento_id = await criar_agendamento(telefono, nome or None, data_hora, informacao)
    if agendamento_id is not None:
        uid = reserva.get("uid")
        if uid:
            await guardar_evento_calcom_uid(agendamento_id, uid)
        # Reforço direto ao iCloud — o Cal.com nem sempre escreve no calendário
        # externo ligado quando a marcação é criada pela API (bug conhecido deles)
        kwargs_icloud = {}
        if duracao_minutos:
            kwargs_icloud["duracao_minutos"] = duracao_minutos
        if titulo_evento:
            kwargs_icloud["titulo"] = titulo_evento
        await criar_evento_icloud(agendamento_id, nome or None, telefono, data_hora, informacao, **kwargs_icloud)

    dados = {
        "id": agendamento_id,
        "telefono": telefono,
        "nome_cliente": nome,
        "data_hora": data_hora,
        "informacao": informacao,
        "evento_calcom_uid": reserva.get("uid"),
    }
    logger.info(f"Agendado (Cal.com uid={reserva.get('uid')}): {telefono} - {formatar_slot(data_hora)}")
    if e_agenda_pessoal:
        return (
            f"Compromisso marcado com sucesso para {formatar_slot(data_hora)}"
            f"{f' ({titulo_evento})' if titulo_evento else ''}. Confirma isto ao Luis de forma clara.",
            dados,
        )
    return (
        f"Chamada marcada com sucesso para {formatar_slot(data_hora)}. "
        "Confirma isto ao cliente de forma clara e simpática.",
        dados,
    )


async def _processar_cancelamento(telefone: str, motivo: str) -> str:
    """
    Cancela a chamada ativa deste cliente, vinda da ferramenta cancelar_chamada:
    cancela no Cal.com, no registo local, e avisa o consultor por WhatsApp.

    Returns:
        Mensagem para o modelo confirmar ao cliente.
    """
    agendamento = await obter_agendamento_ativo_por_telefone(telefone)
    if agendamento is None:
        return (
            "Não há nenhuma chamada agendada para este número atualmente. "
            "Informa o cliente com simpatia."
        )

    cancelado = await cancelar_agendamento(agendamento["id"])
    if cancelado is None:
        return (
            "Não foi possível cancelar — a chamada pode já ter sido cancelada "
            "entretanto. Informa o cliente."
        )

    if cancelado.get("evento_calcom_uid"):
        await cancelar_reserva(cancelado["evento_calcom_uid"], motivo or "Cancelado pelo cliente via WhatsApp")
    await apagar_evento_icloud(agendamento["id"])
    await apagar_evento_outlook(cancelado.get("evento_outlook_id"))

    await marcar_alertas_agendamento_vistos(telefone)

    proveedor = obtener_proveedor()
    await notificar_cancelamento(proveedor, cancelado, motivo)
    await criar_alerta(
        "cancelamento", telefone,
        f"❌ {cancelado.get('nome_cliente') or telefone} cancelou a chamada de "
        f"{formatar_slot(cancelado['data_hora'])}",
    )

    logger.info(f"Chamada cancelada pelo cliente: {telefone} — {formatar_slot(cancelado['data_hora'])}")
    return (
        f"Chamada de {formatar_slot(cancelado['data_hora'])} cancelada com sucesso. "
        "Confirma isto ao cliente de forma simpática, e pergunta se quer marcar "
        "outro horário."
    )


async def _processar_consulta_dia(entrada: dict) -> str:
    """
    Consulta os horários livres num dia específico pedido pelo cliente, vinda
    da ferramenta consultar_disponibilidade_dia — sem limite de distância no
    futuro.

    Returns:
        Mensagem para o modelo com as horas livres (ou aviso), a usar depois
        com oferecer_opcoes.
    """
    data_str = (entrada.get("data") or "").strip()
    try:
        dia = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return (
            "Data inválida (tem de estar no formato AAAA-MM-DD). Confirma a "
            "data com o cliente e tenta de novo."
        )

    if not calcom_configurado():
        return "O agendamento está temporariamente indisponível — informa o cliente."

    hoje = datetime.now(ZoneInfo("Europe/Lisbon")).date()
    if dia < hoje:
        return "Essa data já passou. Pede ao cliente uma data futura."

    horarios = await obter_horarios_disponiveis_intervalo(dia, dia)
    nome_dia = DIAS_SEMANA[dia.weekday()]
    data_formatada = f"{nome_dia}, {dia.strftime('%d/%m')}"

    if not horarios:
        return (
            f"Não há horários livres em {data_formatada}. Sugere ao cliente "
            "escolher outro dia."
        )

    horas = ", ".join(h.strftime("%Hh%M") for h in horarios)
    return (
        f"Horas livres em {data_formatada}: {horas}. Usa a ferramenta "
        "oferecer_opcoes para apresentares 2 ou 3 destas horas como botões — "
        "nunca escrevas os horários em texto normal."
    )


async def generar_respuesta(
    mensaje: str, historial: list[dict], telefono: str, nome_contato: str | None = None
) -> tuple[str, bool, dict | None, list[str] | None, dict | None, str | None, list[dict] | None]:
    """
    Genera una respuesta usando Claude API.

    Args:
        mensaje: El mensaje nuevo del usuario
        historial: Lista de mensajes anteriores [{"role": "user/assistant/humano", "content": "..."}]
        telefono: Número de teléfono del cliente (necesario para agendar chamadas)
        nome_contato: Nombre de perfil de WhatsApp del cliente, si se conoce

    Returns:
        Tupla (respuesta, escalar_a_consultor, agendamento, opcoes, link_botao,
        motivo_escalada, links_multiplos) — escalar_a_consultor es True si el
        cliente pidió/aceptó hablar con un consultor humano; agendamento es
        None o un dict con los detalles de una chamada recién marcada; opcoes
        es None o una lista de 2-3 respostas curtas para mostrar como botões
        de resposta rápida; link_botao es None ou um dict {"texto_botao",
        "url"} para mostrar um botão que abre um link; motivo_escalada é None
        ou o motivo da escalada; links_multiplos é None ou uma lista de dicts
        {"texto_botao", "url"} para mostrar vários botões de link (um por
        mensagem, ex: redes sociais).
    """
    # Si el mensaje es muy corto o vacío, usar fallback
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback(), False, None, None, None, None, None

    system_blocks = await montar_system_blocks(nome_contato, primeira_mensagem=not historial, telefono=telefono)

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

    escalar = False
    agendamento = None
    opcoes = None
    link_botao = None
    motivo_escalada = None
    links_multiplos = None

    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_blocks,
            tools=HERRAMIENTAS,
            messages=mensajes
        )

        # Ciclo de tool-use: el modelo puede activar una o varias herramientas
        # antes de dar la respuesta final al cliente (con un límite de seguridad)
        intentos = 0
        texto_curto_circuito = None
        while response.stop_reason == "tool_use" and intentos < 4:
            intentos += 1
            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            mensajes.append({"role": "assistant", "content": response.content})

            resultados_tool = []
            for tool_use in tool_blocks:
                if tool_use.name == "escalar_a_consultor":
                    escalar = True
                    motivo_escalada = (tool_use.input.get("motivo") or "").strip() or None
                    logger.info(f"Escalado a consultor: {motivo_escalada}")
                    resultado_texto = "Consultor notificado, vai entrar em contacto em breve."
                elif tool_use.name == "agendar_chamada":
                    resultado_texto, dados = await _processar_agendamento(tool_use.input, telefono)
                    if dados:
                        agendamento = dados
                elif tool_use.name == "cancelar_chamada":
                    motivo_cancelamento = (tool_use.input.get("motivo") or "").strip()
                    resultado_texto = await _processar_cancelamento(telefono, motivo_cancelamento)
                elif tool_use.name == "consultar_disponibilidade_dia":
                    resultado_texto = await _processar_consulta_dia(tool_use.input)
                elif tool_use.name == "oferecer_opcoes":
                    pergunta = (tool_use.input.get("pergunta") or "").strip()
                    opcoes_validas = [
                        str(o).strip()[:20] for o in (tool_use.input.get("opcoes") or []) if str(o).strip()
                    ][:3]
                    if pergunta and len(opcoes_validas) >= 2:
                        texto_curto_circuito = pergunta
                        opcoes = opcoes_validas
                        resultado_texto = "Opções mostradas ao cliente como botões."
                    else:
                        resultado_texto = "Pedido inválido (falta pergunta ou 2-3 opções) — responde em texto normal."
                elif tool_use.name == "enviar_link_simulador":
                    mensagem_link = (tool_use.input.get("mensagem") or "").strip() or \
                        "Veja as opções e campanhas disponíveis:"
                    tipo_simulador = tool_use.input.get("tipo") or "geral"
                    nivel_tensao_cliente = (tool_use.input.get("nivel_tensao") or "").strip().upper()
                    simulador = SIMULADORES.get(tipo_simulador, SIMULADORES["geral"])
                    # Garantido em código (não só no prompt): estes escalões BTN são os
                    # que mais poupam com solar — nunca deixar passar sem mencionar,
                    # seja particular ou empresa
                    if tipo_simulador == "eletricidade_personalizada" and nivel_tensao_cliente == "BTN":
                        mensagem_link += (
                            "\n\n☀️ Já agora — com esta potência, o seu perfil é dos que "
                            "mais poupa com uma solução solar fotovoltaica, porque as "
                            "tarifas de rede nestes escalões são muito elevadas. Tem "
                            "área disponível (cobertura, solo ou estacionamento) para "
                            "a instalação de painéis solares?"
                        )
                    texto_curto_circuito = mensagem_link
                    link_botao = {"texto_botao": simulador["texto_botao"], "url": simulador["url"]}
                    resultado_texto = f"Botão do simulador ({tipo_simulador}) mostrado ao cliente."
                elif tool_use.name == "recomendar_redes_sociais":
                    mensagem_redes = (tool_use.input.get("mensagem") or "").strip() or \
                        "Obrigado pelo contacto! Siga-nos nas redes sociais:"
                    texto_curto_circuito = mensagem_redes
                    links_multiplos = REDES_SOCIAIS
                    resultado_texto = "Botões das redes sociais mostrados ao cliente."
                else:
                    resultado_texto = "Ferramenta desconhecida."

                resultados_tool.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": resultado_texto,
                })

            # Se as opções ou algum link foram mostrados com sucesso, essa é
            # a mensagem final — não pedimos mais um texto ao modelo por cima
            if opcoes or link_botao or links_multiplos:
                logger.info(
                    f"Curto-circuito: opções={opcoes} link_botao={link_botao} "
                    f"links_multiplos={links_multiplos}"
                )
                return texto_curto_circuito, escalar, agendamento, opcoes, link_botao, motivo_escalada, links_multiplos

            mensajes.append({"role": "user", "content": resultados_tool})
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                system=system_blocks,
                tools=HERRAMIENTAS,
                messages=mensajes
            )

        texto = next((b.text for b in response.content if b.type == "text"), "")
        logger.info(
            f"Respuesta generada ({response.usage.input_tokens} in / {response.usage.output_tokens} out / "
            f"{response.usage.cache_read_input_tokens or 0} cache_read / "
            f"{response.usage.cache_creation_input_tokens or 0} cache_write)"
        )
        return texto, escalar, agendamento, None, None, motivo_escalada, None

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error(), False, None, None, None, None, None

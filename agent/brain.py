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

from agent.agenda import proximos_horarios_disponiveis, formatar_slot, slot_e_valido, horario_minimo_permitido
from agent.memory import criar_agendamento

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
            "dele e o motivo da chamada — nunca marques sem essa confirmação."
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
            },
            "required": ["data", "hora", "nome", "informacao"],
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
            "'eletricidade_personalizada' só para EMPRESA, quando a "
            "potência/tensão são das gamas mais altas que exigem proposta à "
            "medida (ver a mesma secção); 'gas_natural' quando o cliente "
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


async def obtener_contexto_agenda() -> str:
    """
    Genera un bloque con los próximos horarios libres para chamadas telefónicas,
    para que el modelo pueda ofrecerlos directamente sin inventar horas.
    """
    slots = await proximos_horarios_disponiveis(quantidade=3)
    if not slots:
        return (
            "\n\n## Agendamento de chamadas\n"
            "De momento não há horários disponíveis nos próximos dias — informa "
            "o cliente e sugere que a equipa entre em contacto por outra via."
        )
    linhas = "\n".join(f"- {formatar_slot(slot)}" for slot in slots)
    return (
        "\n\n## Agendamento de chamadas\n"
        "Não ofereças uma chamada logo na primeira mensagem nem em resposta a "
        "um simples cumprimento (ex: 'boa noite', 'olá', 'tudo bem?') — "
        "responde ao cumprimento com naturalidade e percebe primeiro o que o "
        "cliente procura. Só ofereças a chamada depois de o cliente mostrar "
        "interesse real no serviço (ex: já perguntou sobre uma solução "
        "específica, quer avançar, ou pede para falar com alguém).\n"
        "As chamadas são sempre à tarde (15h-19h), de Segunda a Sábado, em "
        "blocos de 15 minutos, com pelo menos 1 hora de antecedência. Os "
        "próximos horários livres são:\n"
        f"{linhas}\n"
        "Quando ofereceres, sugere apenas 2 ou 3 horários — não despejes uma "
        "lista longa. Usa SEMPRE a ferramenta oferecer_opcoes para "
        "apresentares esses horários como botões clicáveis — nunca escrevas "
        "os horários em texto normal, para o cliente não ter de os escrever "
        "à mão. Depois de o cliente escolher um botão, confirma o nome dele "
        "e o motivo da chamada, e só depois usa a ferramenta "
        "agendar_chamada para a marcar. Se o cliente preferir outro dia/hora "
        "dentro da grelha, podes marcar diretamente — a ferramenta valida se "
        "está mesmo livre e com antecedência suficiente."
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


async def cargar_system_prompt(nome_contato: str | None, primeira_mensagem: bool) -> str:
    """Lee el system prompt desde config/prompts.yaml, con contexto dinámico añadido."""
    config = cargar_config_prompts()
    base = config.get("system_prompt", "Eres un asistente útil. Responde en español.")
    contexto_agenda = await obtener_contexto_agenda()
    contexto_cliente = obtener_contexto_cliente(nome_contato, primeira_mensagem)
    return base + obtener_contexto_temporal() + contexto_cliente + contexto_agenda


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

    try:
        data_hora = datetime.strptime(f"{data} {hora}", "%Y-%m-%d %H:%M")
    except ValueError:
        return (
            "Não foi possível marcar: a data ou hora não estão num formato válido "
            "(AAAA-MM-DD e HH:MM). Confirma o horário com o cliente e tenta de novo.",
            None,
        )

    if not slot_e_valido(data_hora):
        return (
            "Não foi possível marcar: esse horário está fora da grelha permitida "
            "(tardes de Segunda a Sábado, 15h-19h, blocos de 15 min). Sugere ao "
            "cliente um dos horários disponíveis listados no contexto.",
            None,
        )

    if data_hora < horario_minimo_permitido():
        return (
            "Não foi possível marcar: esse horário é demasiado próximo — "
            "precisamos de pelo menos 1 hora de antecedência para o consultor "
            "se preparar. Sugere ao cliente um horário mais à frente.",
            None,
        )

    agendamento_id = await criar_agendamento(telefono, nome or None, data_hora, informacao)
    if agendamento_id is None:
        return (
            "Não foi possível marcar: esse horário acabou de ser ocupado por outra "
            "pessoa. Sugere ao cliente escolher outro horário disponível.",
            None,
        )

    dados = {
        "id": agendamento_id,
        "telefono": telefono,
        "nome_cliente": nome,
        "data_hora": data_hora,
        "informacao": informacao,
    }
    logger.info(f"Chamada agendada: {telefono} — {formatar_slot(data_hora)}")
    return (
        f"Chamada marcada com sucesso para {formatar_slot(data_hora)}. "
        "Confirma isto ao cliente de forma clara e simpática.",
        dados,
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

    system_prompt = await cargar_system_prompt(nome_contato, primeira_mensagem=not historial)

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
            system=system_prompt,
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
                    simulador = SIMULADORES.get(tipo_simulador, SIMULADORES["geral"])
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
                system=system_prompt,
                tools=HERRAMIENTAS,
                messages=mensajes
            )

        texto = next((b.text for b in response.content if b.type == "text"), "")
        logger.info(f"Respuesta generada ({response.usage.input_tokens} in / {response.usage.output_tokens} out)")
        return texto, escalar, agendamento, None, None, motivo_escalada, None

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error(), False, None, None, None, None, None

# agent/admin.py — Painel de administração para ver e responder conversas
# Generado por AgentKit

"""
Painel web simples e protegido por password para:
- Ver todas as conversas do agente, separadas em "Em aberto" e "Tratadas"
- Alternar cada conversa entre modo "bot" (automático) e "manual" (o humano responde)
- Enviar respostas manuais (texto ou ficheiros) a partir do telemóvel
- Ver ficheiros que os clientes enviaram (fotos, PDFs, etc.)
"""

import os
import re
import html
import uuid
import secrets
import logging
import mimetypes
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse

from agent.memory import (
    listar_conversaciones, obtener_historial, obtener_modo, establecer_modo,
    obtener_estado, establecer_estado, obtener_nome_contato, obtener_categoria,
    establecer_categoria, CATEGORIAS_VALIDAS, guardar_mensaje, listar_agendamentos,
    editar_mensagem, apagar_mensagem, obtener_mensagens_novas,
    listar_alertas_nao_vistos, marcar_alerta_visto, marcar_todos_alertas_vistos,
)
from agent.agenda import formatar_slot
from agent.providers import obtener_proveedor
from agent.notificacoes import notificar_consultor, NUMERO_CONSULTOR

logger = logging.getLogger("agentkit")
router = APIRouter(prefix="/admin")
security = HTTPBasic()

MEDIA_DIR = "data/media"
os.makedirs(MEDIA_DIR, exist_ok=True)

ESTILO = """
<style>
  body { font-family: -apple-system, sans-serif; max-width: 640px; margin: 0 auto; padding: 12px;
         background: #f5f5f5; color: #1a1a1a; }
  h1 { font-size: 1.3rem; }
  a { color: #0a7d4f; text-decoration: none; }
  .tabs { display: flex; gap: 8px; margin-bottom: 12px; }
  .tabs a { flex: 1; text-align: center; padding: 8px; border-radius: 8px; background: white;
            color: #444; font-size: 0.9rem; }
  .tabs a.ativo { background: #0a7d4f; color: white; }
  .conversa { background: white; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;
              display: flex; gap: 10px; align-items: flex-start; box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
  .conversa .corpo { flex: 1; min-width: 0; }
  .conversa .top { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
  .conversa .tel { font-weight: 600; }
  .avatar { flex-shrink: 0; width: 40px; height: 40px; border-radius: 50%; display: flex;
            align-items: center; justify-content: center; color: white; font-weight: 600;
            font-size: 0.95rem; }
  .cabecalho { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
  .cabecalho .avatar { width: 48px; height: 48px; font-size: 1.1rem; }
  .cabecalho .nome { font-size: 1.2rem; font-weight: 600; }
  .cabecalho .tel { color: #666; font-size: 0.85rem; }
  .btn-consultor { width: 100%; padding: 10px; margin-bottom: 8px; border-radius: 8px; border: none;
                    background: #1d6fa5; color: white; font-size: 0.9rem; }
  .badges { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
  .badge { font-size: 0.75rem; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }
  .badge.bot { background: #e3f2e9; color: #0a7d4f; }
  .badge.manual { background: #fdeaea; color: #c0392b; }
  .badge.tratada { background: #e9e9e9; color: #666; }
  .badge.interessado { background: #fdf2df; color: #a5701d; }
  .badge.ganho { background: #e3f2e9; color: #0a7d4f; }
  .badge.perdido { background: #fdeaea; color: #c0392b; }
  .filtros { display: flex; gap: 6px; margin-bottom: 12px; overflow-x: auto; padding-bottom: 2px; }
  .filtros a { flex-shrink: 0; padding: 6px 12px; border-radius: 20px; background: white; color: #444;
               font-size: 0.85rem; border: 1px solid #ddd; }
  .filtros a.ativo { background: #1a1a1a; color: white; border-color: #1a1a1a; }
  .preview { color: #666; font-size: 0.9rem; margin-top: 4px; white-space: nowrap; overflow: hidden;
             text-overflow: ellipsis; }
  .msg { padding: 8px 12px; border-radius: 10px; margin-bottom: 8px; max-width: 80%; word-break: break-word; }
  .msg.user { background: white; margin-right: auto; }
  .msg.assistant { background: #dcf8c6; margin-left: auto; }
  .msg.humano { background: #cfe8ff; margin-left: auto; }
  .msg img { max-width: 100%; border-radius: 8px; display: block; margin-bottom: 4px; }
  .msg .ficheiro { display: block; font-size: 0.85rem; }
  .msg .hora { display: block; font-size: 0.7rem; color: #999; margin-top: 3px; text-align: right; }
  .msg-acoes { display: flex; gap: 10px; justify-content: flex-end; margin-top: 4px; }
  .msg-acoes summary, .msg-acoes .btn-apagar { font-size: 0.75rem; color: #666; cursor: pointer;
                                                 background: none; border: none; padding: 0; }
  .msg-acoes .btn-apagar { color: #c0392b; }
  .form-editar { display: flex; gap: 6px; margin-top: 6px; }
  .form-editar textarea { flex: 1; padding: 6px; border-radius: 6px; border: 1px solid #ccc; resize: none; }
  .form-editar button { padding: 0 10px; border-radius: 6px; border: none; background: #0a7d4f; color: white; }
  form.reply { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; position: sticky; bottom: 0;
               background: #f5f5f5; padding: 8px 0; }
  form.reply textarea { flex: 1; min-width: 140px; padding: 10px; border-radius: 8px; border: 1px solid #ccc;
                         resize: none; }
  form.reply button { padding: 0 16px; border-radius: 8px; border: none; background: #0a7d4f; color: white; }
  form.reply .anexo { flex-basis: 100%; font-size: 0.85rem; }
  .toggle { display: flex; gap: 8px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
  .toggle.separador { padding-top: 8px; border-top: 1px solid #ddd; }
  .toggle button { padding: 6px 12px; border-radius: 8px; border: 1px solid #ccc; background: white; }
  .toggle button.ativo { background: #0a7d4f; color: white; border-color: #0a7d4f; }
  .toggle button.tratada.ativo { background: #666; border-color: #666; }
  .toggle button.interessado.ativo { background: #a5701d; border-color: #a5701d; }
  .toggle button.ganho.ativo { background: #0a7d4f; border-color: #0a7d4f; }
  .toggle button.perdido.ativo { background: #c0392b; border-color: #c0392b; }
  .topo { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .alertas { margin-bottom: 12px; }
  .alerta { background: #fff8e1; border: 1px solid #f0d78c; border-radius: 8px; padding: 10px 12px;
            margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;
            gap: 10px; font-size: 0.9rem; }
  .alerta a.ver { color: #1a1a1a; text-decoration: underline; flex: 1; }
  .alerta button { flex-shrink: 0; padding: 4px 10px; border-radius: 6px; border: 1px solid #ccc;
                    background: white; font-size: 0.8rem; }
  .alertas-topo { display: flex; justify-content: flex-end; margin-bottom: 6px; }
  .alertas-topo button { padding: 4px 10px; border-radius: 6px; border: 1px solid #ccc;
                          background: white; font-size: 0.8rem; }
  .link-agenda { padding: 8px 14px; border-radius: 8px; background: white; color: #444;
                 font-size: 0.9rem; border: 1px solid #ddd; }
  .agendamento { background: white; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;
                 box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
  .agendamento .quando { font-weight: 600; color: #0a7d4f; }
  .agendamento .nome { font-weight: 600; }
  .agendamento .tel { color: #666; font-size: 0.85rem; }
  .agendamento .info { margin-top: 6px; font-size: 0.9rem; white-space: pre-wrap; }
</style>
"""


# O WhatsApp Cloud API da Meta não disponibiliza a foto de perfil dos contactos
# por razões de privacidade — como alternativa, geramos um avatar com as
# iniciais do nome (ou os últimos dígitos do número, se o nome ainda não for
# conhecido) numa cor estável por contacto.
CORES_AVATAR = ["#0a7d4f", "#1d6fa5", "#a5521d", "#7d1da5", "#a51d4a", "#4a7d1d"]


def _avatar_html(nome: str | None, telefono: str, tamanho_classe: str = "") -> str:
    """Gera um avatar simples (iniciais em círculo colorido) para um contacto."""
    if nome:
        iniciais = "".join(p[0] for p in nome.split()[:2]).upper()
    else:
        iniciais = telefono[-2:]
    cor = CORES_AVATAR[sum(ord(c) for c in telefono) % len(CORES_AVATAR)]
    return f'<div class="avatar {tamanho_classe}" style="background:{cor}">{html.escape(iniciais)}</div>'


def verificar_password(credentials: HTTPBasicCredentials = Depends(security)):
    """Protege o painel com uma password única (ADMIN_PASSWORD no .env)."""
    password_correta = os.getenv("ADMIN_PASSWORD", "")
    if not password_correta:
        raise HTTPException(status_code=500, detail="ADMIN_PASSWORD não está configurada")
    if not secrets.compare_digest(credentials.password, password_correta):
        raise HTTPException(
            status_code=401,
            detail="Password incorreta",
            headers={"WWW-Authenticate": "Basic"},
        )
    return True


NOMES_CATEGORIA = {
    "sem_categoria": "Sem categoria",
    "interessado": "Com interesse",
    "ganho": "Ganho",
    "perdido": "Perdido",
}


def _render_alertas(alertas: list[dict]) -> str:
    """Gera o HTML dos alertas pendentes (agendamentos, lembretes, escaladas)."""
    if not alertas:
        return ""
    linhas = ""
    for a in alertas:
        mensagem = html.escape(a["mensagem"])
        telefone = html.escape(a["telefono"])
        linhas += f"""
        <div class="alerta">
          <a class="ver" href="/admin/conversa/{telefone}">{mensagem}</a>
          <form method="post" action="/admin/alertas/{a['id']}/visto">
            <button type="submit">Dispensar</button>
          </form>
        </div>
        """
    return f"""
    <div class="alertas">
      <div class="alertas-topo">
        <form method="post" action="/admin/alertas/marcar-todos">
          <button type="submit">Marcar todos como lidos</button>
        </form>
      </div>
      {linhas}
    </div>
    """


@router.get("/", response_class=HTMLResponse)
async def painel(estado: str = "aberta", categoria: str = "todas", auth: bool = Depends(verificar_password)):
    """Lista as conversas do estado escolhido, com filtro opcional por categoria comercial."""
    alertas = await listar_alertas_nao_vistos()
    alertas_html = _render_alertas(alertas)
    todas = await listar_conversaciones()
    do_estado = [c for c in todas if c["estado"] == estado]
    conversas = do_estado if categoria == "todas" else [c for c in do_estado if c["categoria"] == categoria]
    n_abertas = sum(1 for c in todas if c["estado"] == "aberta")
    n_tratadas = sum(1 for c in todas if c["estado"] == "tratada")

    linhas = ""
    for c in conversas:
        preview = html.escape(c["ultimo_mensaje"][:80]) if c.get("ultimo_mensaje") else ""
        if not preview and c.get("ultimo_tipo") != "texto":
            preview = f"[{c.get('ultimo_tipo', 'ficheiro')}]"
        badge_classe = "manual" if c["modo"] == "manual" else "bot"
        badge_texto = "Manual" if c["modo"] == "manual" else "Bot"
        badges_extra = ""
        if c["categoria"] != "sem_categoria":
            badges_extra = f'<span class="badge {c["categoria"]}">{NOMES_CATEGORIA[c["categoria"]]}</span>'
        nome = c.get("nome_contato")
        titulo = html.escape(nome) if nome else html.escape(c["telefono"])
        linhas += f"""
        <a class="conversa" href="/admin/conversa/{html.escape(c['telefono'])}">
          {_avatar_html(nome, c['telefono'])}
          <div class="corpo">
            <div class="top">
              <span class="tel">{titulo}</span>
              <span class="badges"><span class="badge {badge_classe}">{badge_texto}</span>{badges_extra}</span>
            </div>
            <div class="preview">{preview}</div>
          </div>
        </a>
        """

    if not conversas:
        linhas = "<p>Sem conversas aqui.</p>"

    filtros_categoria = "".join(
        f'<a href="/admin/?estado={estado}&categoria={chave}" class="{"ativo" if categoria == chave else ""}">{nome}</a>'
        for chave, nome in [("todas", "Todas"), *NOMES_CATEGORIA.items()]
    )

    return f"""
    <html>
    <head><title>Conversas — Reduz+ Energia</title>{ESTILO}
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body>
      <div class="topo">
        <h1>Conversas</h1>
        <a class="link-agenda" href="/admin/agenda">📅 Agenda</a>
      </div>
      {alertas_html}
      <div class="tabs">
        <a href="/admin/?estado=aberta&categoria={categoria}" class="{'ativo' if estado == 'aberta' else ''}">Em aberto ({n_abertas})</a>
        <a href="/admin/?estado=tratada&categoria={categoria}" class="{'ativo' if estado == 'tratada' else ''}">Tratadas ({n_tratadas})</a>
      </div>
      <div class="filtros">{filtros_categoria}</div>
      {linhas}
      <script>setInterval(function() {{ location.reload(); }}, 20000);</script>
    </body>
    </html>
    """


@router.post("/alertas/{alerta_id}/visto")
async def dispensar_alerta(alerta_id: int, auth: bool = Depends(verificar_password)):
    """Marca um alerta como visto, para deixar de aparecer no painel."""
    await marcar_alerta_visto(alerta_id)
    return RedirectResponse(url="/admin/", status_code=303)


@router.post("/alertas/marcar-todos")
async def dispensar_todos_alertas(auth: bool = Depends(verificar_password)):
    """Marca todos os alertas pendentes como vistos."""
    await marcar_todos_alertas_vistos()
    return RedirectResponse(url="/admin/", status_code=303)


@router.get("/agenda", response_class=HTMLResponse)
async def agenda(auth: bool = Depends(verificar_password)):
    """Lista as próximas chamadas agendadas pelos clientes."""
    agendamentos = await listar_agendamentos()

    linhas = ""
    for a in agendamentos:
        nome = html.escape(a["nome_cliente"]) if a.get("nome_cliente") else "(nome não indicado)"
        telefone = html.escape(a["telefono"])
        quando = formatar_slot(a["data_hora"])
        informacao = html.escape(a.get("informacao") or "")
        linhas += f"""
        <div class="agendamento">
          <div class="quando">{quando}</div>
          <div class="nome">{nome}</div>
          <div class="tel"><a href="/admin/conversa/{telefone}">{telefone}</a></div>
          <div class="info">{informacao}</div>
        </div>
        """

    if not agendamentos:
        linhas = "<p>Sem chamadas agendadas de momento.</p>"

    return f"""
    <html>
    <head><title>Agenda — Reduz+ Energia</title>{ESTILO}
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body>
      <a href="/admin/">&larr; Conversas</a>
      <h1>Próximas chamadas agendadas</h1>
      {linhas}
    </body>
    </html>
    """


def _formatar_hora(timestamp: datetime | None) -> str:
    """Converte um timestamp UTC guardado na base de dados para hora de Portugal, formatada."""
    if not timestamp:
        return ""
    hora_local = timestamp.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Europe/Lisbon"))
    hoje = datetime.now(ZoneInfo("Europe/Lisbon")).date()
    if hora_local.date() == hoje:
        return hora_local.strftime("%H:%M")
    return hora_local.strftime("%d/%m %H:%M")


URL_REGEX = re.compile(r'https?://[^\s<>"]+')


def _linkificar(texto: str) -> str:
    """Escapa o texto de uma mensagem e transforma URLs em links clicáveis."""
    partes = []
    posicao = 0
    for m in URL_REGEX.finditer(texto):
        partes.append(html.escape(texto[posicao:m.start()]))
        url_escapado = html.escape(m.group(0))
        partes.append(f'<a href="{url_escapado}" target="_blank" rel="noopener">{url_escapado}</a>')
        posicao = m.end()
    partes.append(html.escape(texto[posicao:]))
    return "".join(partes)


def _render_mensagem(msg: dict, telefono: str) -> str:
    """Gera o HTML de uma mensagem, incluindo pré-visualização de ficheiros e hora."""
    classe = "user" if msg["role"] == "user" else ("humano" if msg["role"] == "humano" else "assistant")
    partes = ""

    if msg.get("media_path"):
        nome_arquivo = os.path.basename(msg["media_path"])
        url = f"/admin/media/{nome_arquivo}"
        if msg.get("tipo") == "imagem":
            partes += f'<a href="{url}" target="_blank"><img src="{url}" alt="imagem"></a>'
        else:
            nome_mostrar = html.escape(msg.get("nome_ficheiro") or nome_arquivo)
            partes += f'<a class="ficheiro" href="{url}" target="_blank">📎 {nome_mostrar}</a>'

    if msg["content"]:
        partes += _linkificar(msg["content"])

    partes += f'<small class="hora">{_formatar_hora(msg.get("timestamp"))}</small>'

    # Mensagens enviadas manualmente pelo painel podem ser corrigidas ou
    # apagadas do registo (não afeta o que o cliente já recebeu no WhatsApp)
    if msg["role"] == "humano" and msg.get("id"):
        conteudo_editavel = html.escape(msg["content"] or "")
        partes += f"""
        <div class="msg-acoes">
          <details>
            <summary>✏️ Editar</summary>
            <form class="form-editar" method="post" action="/admin/conversa/{telefono}/mensagem/{msg['id']}/editar">
              <textarea name="texto" rows="2">{conteudo_editavel}</textarea>
              <button type="submit">Guardar</button>
            </form>
          </details>
          <form method="post" action="/admin/conversa/{telefono}/mensagem/{msg['id']}/apagar"
                onsubmit="return confirm('Apagar esta mensagem do registo? Isto não a remove do WhatsApp do cliente, que já a recebeu.')">
            <button type="submit" class="btn-apagar">🗑️ Apagar</button>
          </form>
        </div>
        """

    return f'<div class="msg {classe}" data-msg-id="{msg["id"]}">{partes}</div>'


@router.get("/conversa/{telefono}", response_class=HTMLResponse)
async def ver_conversa(telefono: str, auth: bool = Depends(verificar_password)):
    """Mostra o histórico de uma conversa e permite responder ou trocar o modo/estado."""
    historico = await obtener_historial(telefono, limite=100)
    modo = await obtener_modo(telefono)
    estado = await obtener_estado(telefono)
    categoria = await obtener_categoria(telefono)
    nome = await obtener_nome_contato(telefono)

    mensagens_html = "".join(_render_mensagem(msg, telefono) for msg in historico)
    titulo_pagina = nome or telefono

    return f"""
    <html>
    <head><title>{html.escape(titulo_pagina)} — Reduz+ Energia</title>{ESTILO}
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body>
      <a href="/admin/">&larr; Conversas</a>
      <div class="cabecalho">
        {_avatar_html(nome, telefono)}
        <div>
          <div class="nome">{html.escape(nome) if nome else html.escape(telefono)}</div>
          {f'<div class="tel">{html.escape(telefono)}</div>' if nome else ''}
        </div>
      </div>

      {f'''<form method="post" action="/admin/conversa/{telefono}/encaminhar"
             onsubmit="return confirm('Encaminhar esta conversa para o consultor Luis Sequeira ({NUMERO_CONSULTOR})?')">
        <button type="submit" class="btn-consultor">📞 Encaminhar para consultor</button>
      </form>''' if NUMERO_CONSULTOR else ''}

      <div class="toggle">
        <form method="post" action="/admin/conversa/{telefono}/modo">
          <input type="hidden" name="modo" value="bot">
          <button type="submit" class="{'ativo' if modo == 'bot' else ''}">Bot responde</button>
        </form>
        <form method="post" action="/admin/conversa/{telefono}/modo">
          <input type="hidden" name="modo" value="manual">
          <button type="submit" class="{'ativo' if modo == 'manual' else ''}">Eu respondo</button>
        </form>
        <form method="post" action="/admin/conversa/{telefono}/estado">
          <input type="hidden" name="estado" value="aberta">
          <button type="submit" class="{'ativo' if estado == 'aberta' else ''}">Em aberto</button>
        </form>
        <form method="post" action="/admin/conversa/{telefono}/estado">
          <input type="hidden" name="estado" value="tratada">
          <button type="submit" class="tratada {'ativo' if estado == 'tratada' else ''}">Tratada</button>
        </form>
      </div>

      <div class="toggle separador">
        {"".join(
            f'''<form method="post" action="/admin/conversa/{telefono}/categoria">
                  <input type="hidden" name="categoria" value="{chave}">
                  <button type="submit" class="{chave} {'ativo' if categoria == chave else ''}">{nome}</button>
                </form>'''
            for chave, nome in NOMES_CATEGORIA.items()
        )}
      </div>

      <div id="mensagens">{mensagens_html}</div>

      <form class="reply" method="post" action="/admin/conversa/{telefono}/responder" enctype="multipart/form-data">
        <textarea name="texto" rows="2" placeholder="Escrever resposta..."
                  onkeydown="if(event.key==='Enter' &amp;&amp; !event.shiftKey){{event.preventDefault(); this.form.requestSubmit();}}"></textarea>
        <button type="submit">Enviar</button>
        <input class="anexo" type="file" name="ficheiro">
      </form>

      <script>
      (function() {{
        var telefone = {telefono!r};
        var container = document.getElementById('mensagens');

        // Abre sempre já posicionado na mensagem mais recente
        window.scrollTo(0, document.body.scrollHeight);

        function ultimoIdAtual() {{
          var nos = container.querySelectorAll('[data-msg-id]');
          if (!nos.length) return 0;
          return parseInt(nos[nos.length - 1].dataset.msgId, 10);
        }}

        var ultimoId = ultimoIdAtual();

        async function verificarNovas() {{
          try {{
            var resp = await fetch('/admin/conversa/' + telefone + '/novas?desde=' + ultimoId);
            if (!resp.ok) return;
            var html = await resp.text();
            if (html.trim()) {{
              var pertoDoFim = (window.innerHeight + window.scrollY) >= (document.body.offsetHeight - 150);
              container.insertAdjacentHTML('beforeend', html);
              ultimoId = ultimoIdAtual();
              if (pertoDoFim) window.scrollTo(0, document.body.scrollHeight);
            }}
          }} catch (e) {{}}
        }}

        setInterval(verificarNovas, 4000);
      }})();
      </script>
    </body>
    </html>
    """


@router.get("/conversa/{telefono}/novas", response_class=HTMLResponse)
async def mensagens_novas(telefono: str, desde: int = 0, auth: bool = Depends(verificar_password)):
    """Retorna em HTML as mensagens novas de uma conversa — usado para atualizar a página automaticamente."""
    novas = await obtener_mensagens_novas(telefono, desde)
    return "".join(_render_mensagem(msg, telefono) for msg in novas)


@router.post("/conversa/{telefono}/modo")
async def mudar_modo(telefono: str, modo: str = Form(...), auth: bool = Depends(verificar_password)):
    """Alterna entre modo 'bot' (automático) e 'manual' (respondo eu)."""
    if modo not in ("bot", "manual"):
        raise HTTPException(status_code=400, detail="Modo inválido")
    await establecer_modo(telefono, modo)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/estado")
async def mudar_estado(telefono: str, estado: str = Form(...), auth: bool = Depends(verificar_password)):
    """Alterna entre 'aberta' e 'tratada'."""
    if estado not in ("aberta", "tratada"):
        raise HTTPException(status_code=400, detail="Estado inválido")
    await establecer_estado(telefono, estado)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/encaminhar")
async def encaminhar_consultor(telefono: str, auth: bool = Depends(verificar_password)):
    """Reenvia a conversa completa para o WhatsApp do consultor, manualmente."""
    proveedor = obtener_proveedor()
    historico = await obtener_historial(telefono, limite=100)
    enviado = await notificar_consultor(proveedor, telefono, historico)
    if enviado:
        logger.info(f"Conversa {telefono} encaminhada manualmente para o consultor")
    else:
        logger.warning(f"Falha ao encaminhar conversa {telefono} para o consultor")
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/categoria")
async def mudar_categoria(telefono: str, categoria: str = Form(...), auth: bool = Depends(verificar_password)):
    """Muda a categoria comercial da conversa: sem_categoria, interessado, ganho ou perdido."""
    if categoria not in CATEGORIAS_VALIDAS:
        raise HTTPException(status_code=400, detail="Categoria inválida")
    await establecer_categoria(telefono, categoria)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/responder")
async def responder_manual(
    telefono: str,
    texto: str = Form(""),
    ficheiro: UploadFile | None = File(None),
    auth: bool = Depends(verificar_password),
):
    """Envia uma resposta manual ao cliente — texto, ficheiro, ou ambos."""
    proveedor = obtener_proveedor()

    if ficheiro is not None and ficheiro.filename:
        conteudo = await ficheiro.read()
        mime_type = ficheiro.content_type or mimetypes.guess_type(ficheiro.filename)[0] or "application/octet-stream"
        enviado = await proveedor.enviar_documento(telefono, conteudo, ficheiro.filename, mime_type, legenda=texto)
        if enviado:
            extensao = mimetypes.guess_extension(mime_type) or os.path.splitext(ficheiro.filename)[1]
            nome_local = f"{uuid.uuid4().hex}{extensao}"
            with open(os.path.join(MEDIA_DIR, nome_local), "wb") as f:
                f.write(conteudo)
            tipo = "imagem" if mime_type.startswith("image/") else "documento"
            await guardar_mensaje(
                telefono, "humano", texto, tipo=tipo,
                media_path=os.path.join(MEDIA_DIR, nome_local), nome_ficheiro=ficheiro.filename,
            )
            logger.info(f"Ficheiro enviado manualmente a {telefono}: {ficheiro.filename}")
        else:
            logger.warning(f"Falha ao enviar ficheiro manual a {telefono}")
    elif texto.strip():
        enviado = await proveedor.enviar_mensaje(telefono, texto)
        if enviado:
            await guardar_mensaje(telefono, "humano", texto)
            logger.info(f"Resposta manual a {telefono}: {texto}")
        else:
            logger.warning(f"Falha ao enviar resposta manual a {telefono}")

    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/mensagem/{mensagem_id}/editar")
async def editar_mensagem_manual(
    telefono: str, mensagem_id: int, texto: str = Form(...), auth: bool = Depends(verificar_password)
):
    """Corrige o texto de uma mensagem enviada manualmente (só no registo do painel)."""
    await editar_mensagem(mensagem_id, texto)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/mensagem/{mensagem_id}/apagar")
async def apagar_mensagem_manual(telefono: str, mensagem_id: int, auth: bool = Depends(verificar_password)):
    """Remove do registo do painel uma mensagem enviada manualmente."""
    await apagar_mensagem(mensagem_id)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.get("/media/{nome_arquivo}")
async def obter_media(nome_arquivo: str, auth: bool = Depends(verificar_password)):
    """Serve um ficheiro guardado localmente (recebido ou enviado numa conversa)."""
    caminho = os.path.join(MEDIA_DIR, nome_arquivo)
    caminho_absoluto = os.path.abspath(caminho)
    diretorio_absoluto = os.path.abspath(MEDIA_DIR)
    if not caminho_absoluto.startswith(diretorio_absoluto) or not os.path.isfile(caminho_absoluto):
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado")
    return FileResponse(caminho_absoluto)

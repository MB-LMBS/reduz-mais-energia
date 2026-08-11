# agent/admin.py — Painel de administração para ver e responder conversas
# Generado por AgentKit

"""
Painel web simples e protegido por password para:
- Ver todas as conversas do agente
- Alternar cada conversa entre modo "bot" (automático) e "manual" (o humano responde)
- Enviar respostas manuais a partir do telemóvel
"""

import os
import html
import secrets
import logging
from fastapi import APIRouter, Depends, HTTPException, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse

from agent.memory import listar_conversaciones, obtener_historial, obtener_modo, establecer_modo, guardar_mensaje
from agent.providers import obtener_proveedor

logger = logging.getLogger("agentkit")
router = APIRouter(prefix="/admin")
security = HTTPBasic()

ESTILO = """
<style>
  body { font-family: -apple-system, sans-serif; max-width: 640px; margin: 0 auto; padding: 12px;
         background: #f5f5f5; color: #1a1a1a; }
  h1 { font-size: 1.3rem; }
  a { color: #0a7d4f; text-decoration: none; }
  .conversa { background: white; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;
              display: block; box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
  .conversa .top { display: flex; justify-content: space-between; align-items: center; }
  .conversa .tel { font-weight: 600; }
  .badge { font-size: 0.75rem; padding: 2px 8px; border-radius: 10px; }
  .badge.bot { background: #e3f2e9; color: #0a7d4f; }
  .badge.manual { background: #fdeaea; color: #c0392b; }
  .preview { color: #666; font-size: 0.9rem; margin-top: 4px; white-space: nowrap; overflow: hidden;
             text-overflow: ellipsis; }
  .msg { padding: 8px 12px; border-radius: 10px; margin-bottom: 8px; max-width: 80%; }
  .msg.user { background: white; margin-right: auto; }
  .msg.assistant { background: #dcf8c6; margin-left: auto; }
  .msg.humano { background: #cfe8ff; margin-left: auto; }
  .msg small { display: block; color: #888; font-size: 0.7rem; margin-top: 2px; }
  form.reply { display: flex; gap: 8px; margin-top: 16px; position: sticky; bottom: 0; background: #f5f5f5;
               padding: 8px 0; }
  form.reply textarea { flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #ccc; resize: none; }
  form.reply button { padding: 0 16px; border-radius: 8px; border: none; background: #0a7d4f; color: white; }
  .toggle { display: flex; gap: 8px; align-items: center; margin: 12px 0; }
  .toggle button { padding: 6px 12px; border-radius: 8px; border: 1px solid #ccc; background: white; }
  .toggle button.ativo { background: #0a7d4f; color: white; border-color: #0a7d4f; }
</style>
"""


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


@router.get("/", response_class=HTMLResponse)
async def painel(auth: bool = Depends(verificar_password)):
    """Lista todas as conversas, mais recente primeiro."""
    conversas = await listar_conversaciones()

    linhas = ""
    for c in conversas:
        preview = html.escape(c["ultimo_mensaje"][:80])
        badge_classe = "manual" if c["modo"] == "manual" else "bot"
        badge_texto = "Manual" if c["modo"] == "manual" else "Bot"
        linhas += f"""
        <a class="conversa" href="/admin/conversa/{html.escape(c['telefono'])}">
          <div class="top">
            <span class="tel">{html.escape(c['telefono'])}</span>
            <span class="badge {badge_classe}">{badge_texto}</span>
          </div>
          <div class="preview">{preview}</div>
        </a>
        """

    if not conversas:
        linhas = "<p>Ainda não há conversas.</p>"

    return f"""
    <html>
    <head><title>Conversas — Reduz+ Energia</title>{ESTILO}
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body>
      <h1>Conversas</h1>
      {linhas}
    </body>
    </html>
    """


@router.get("/conversa/{telefono}", response_class=HTMLResponse)
async def ver_conversa(telefono: str, auth: bool = Depends(verificar_password)):
    """Mostra o histórico de uma conversa e permite responder ou trocar o modo."""
    historico = await obtener_historial(telefono, limite=100)
    modo = await obtener_modo(telefono)

    mensagens_html = ""
    for msg in historico:
        classe = "user" if msg["role"] == "user" else ("humano" if msg["role"] == "humano" else "assistant")
        mensagens_html += f"""<div class="msg {classe}">{html.escape(msg['content'])}</div>"""

    return f"""
    <html>
    <head><title>{html.escape(telefono)} — Reduz+ Energia</title>{ESTILO}
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body>
      <a href="/admin/">&larr; Conversas</a>
      <h1>{html.escape(telefono)}</h1>

      <div class="toggle">
        <form method="post" action="/admin/conversa/{telefono}/modo">
          <input type="hidden" name="modo" value="bot">
          <button type="submit" class="{'ativo' if modo == 'bot' else ''}">Bot responde</button>
        </form>
        <form method="post" action="/admin/conversa/{telefono}/modo">
          <input type="hidden" name="modo" value="manual">
          <button type="submit" class="{'ativo' if modo == 'manual' else ''}">Eu respondo</button>
        </form>
      </div>

      {mensagens_html}

      <form class="reply" method="post" action="/admin/conversa/{telefono}/responder">
        <textarea name="texto" rows="2" placeholder="Escrever resposta..." required></textarea>
        <button type="submit">Enviar</button>
      </form>
    </body>
    </html>
    """


@router.post("/conversa/{telefono}/modo")
async def mudar_modo(telefono: str, modo: str = Form(...), auth: bool = Depends(verificar_password)):
    """Alterna entre modo 'bot' (automático) e 'manual' (respondo eu)."""
    if modo not in ("bot", "manual"):
        raise HTTPException(status_code=400, detail="Modo inválido")
    await establecer_modo(telefono, modo)
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)


@router.post("/conversa/{telefono}/responder")
async def responder_manual(telefono: str, texto: str = Form(...), auth: bool = Depends(verificar_password)):
    """Envia uma resposta manual ao cliente através do WhatsApp."""
    proveedor = obtener_proveedor()
    enviado = await proveedor.enviar_mensaje(telefono, texto)
    if enviado:
        await guardar_mensaje(telefono, "humano", texto)
        logger.info(f"Resposta manual a {telefono}: {texto}")
    else:
        logger.warning(f"Falha ao enviar resposta manual a {telefono}")
    return RedirectResponse(url=f"/admin/conversa/{telefono}", status_code=303)

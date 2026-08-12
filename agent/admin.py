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
import html
import uuid
import secrets
import logging
import mimetypes
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse

from agent.memory import (
    listar_conversaciones, obtener_historial, obtener_modo, establecer_modo,
    obtener_estado, establecer_estado, guardar_mensaje,
)
from agent.providers import obtener_proveedor

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
              display: block; box-shadow: 0 1px 2px rgba(0,0,0,0.08); }
  .conversa .top { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
  .conversa .tel { font-weight: 600; }
  .badges { display: flex; gap: 6px; }
  .badge { font-size: 0.75rem; padding: 2px 8px; border-radius: 10px; white-space: nowrap; }
  .badge.bot { background: #e3f2e9; color: #0a7d4f; }
  .badge.manual { background: #fdeaea; color: #c0392b; }
  .badge.tratada { background: #e9e9e9; color: #666; }
  .preview { color: #666; font-size: 0.9rem; margin-top: 4px; white-space: nowrap; overflow: hidden;
             text-overflow: ellipsis; }
  .msg { padding: 8px 12px; border-radius: 10px; margin-bottom: 8px; max-width: 80%; }
  .msg.user { background: white; margin-right: auto; }
  .msg.assistant { background: #dcf8c6; margin-left: auto; }
  .msg.humano { background: #cfe8ff; margin-left: auto; }
  .msg img { max-width: 100%; border-radius: 8px; display: block; margin-bottom: 4px; }
  .msg .ficheiro { display: block; font-size: 0.85rem; }
  form.reply { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; position: sticky; bottom: 0;
               background: #f5f5f5; padding: 8px 0; }
  form.reply textarea { flex: 1; min-width: 140px; padding: 10px; border-radius: 8px; border: 1px solid #ccc;
                         resize: none; }
  form.reply button { padding: 0 16px; border-radius: 8px; border: none; background: #0a7d4f; color: white; }
  form.reply .anexo { flex-basis: 100%; font-size: 0.85rem; }
  .toggle { display: flex; gap: 8px; align-items: center; margin: 8px 0; flex-wrap: wrap; }
  .toggle button { padding: 6px 12px; border-radius: 8px; border: 1px solid #ccc; background: white; }
  .toggle button.ativo { background: #0a7d4f; color: white; border-color: #0a7d4f; }
  .toggle button.tratada.ativo { background: #666; border-color: #666; }
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
async def painel(estado: str = "aberta", auth: bool = Depends(verificar_password)):
    """Lista as conversas do estado escolhido (aberta ou tratada), mais recente primeiro."""
    todas = await listar_conversaciones()
    conversas = [c for c in todas if c["estado"] == estado]
    n_abertas = sum(1 for c in todas if c["estado"] == "aberta")
    n_tratadas = sum(1 for c in todas if c["estado"] == "tratada")

    linhas = ""
    for c in conversas:
        preview = html.escape(c["ultimo_mensaje"][:80]) if c.get("ultimo_mensaje") else ""
        if not preview and c.get("ultimo_tipo") != "texto":
            preview = f"[{c.get('ultimo_tipo', 'ficheiro')}]"
        badge_classe = "manual" if c["modo"] == "manual" else "bot"
        badge_texto = "Manual" if c["modo"] == "manual" else "Bot"
        linhas += f"""
        <a class="conversa" href="/admin/conversa/{html.escape(c['telefono'])}">
          <div class="top">
            <span class="tel">{html.escape(c['telefono'])}</span>
            <span class="badges"><span class="badge {badge_classe}">{badge_texto}</span></span>
          </div>
          <div class="preview">{preview}</div>
        </a>
        """

    if not conversas:
        linhas = "<p>Sem conversas aqui.</p>"

    return f"""
    <html>
    <head><title>Conversas — Reduz+ Energia</title>{ESTILO}
    <meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body>
      <h1>Conversas</h1>
      <div class="tabs">
        <a href="/admin/?estado=aberta" class="{'ativo' if estado == 'aberta' else ''}">Em aberto ({n_abertas})</a>
        <a href="/admin/?estado=tratada" class="{'ativo' if estado == 'tratada' else ''}">Tratadas ({n_tratadas})</a>
      </div>
      {linhas}
    </body>
    </html>
    """


def _render_mensagem(msg: dict) -> str:
    """Gera o HTML de uma mensagem, incluindo pré-visualização de ficheiros."""
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
        partes += html.escape(msg["content"])

    return f'<div class="msg {classe}">{partes}</div>'


@router.get("/conversa/{telefono}", response_class=HTMLResponse)
async def ver_conversa(telefono: str, auth: bool = Depends(verificar_password)):
    """Mostra o histórico de uma conversa e permite responder ou trocar o modo/estado."""
    historico = await obtener_historial(telefono, limite=100)
    modo = await obtener_modo(telefono)
    estado = await obtener_estado(telefono)

    mensagens_html = "".join(_render_mensagem(msg) for msg in historico)

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
        <form method="post" action="/admin/conversa/{telefono}/estado">
          <input type="hidden" name="estado" value="aberta">
          <button type="submit" class="{'ativo' if estado == 'aberta' else ''}">Em aberto</button>
        </form>
        <form method="post" action="/admin/conversa/{telefono}/estado">
          <input type="hidden" name="estado" value="tratada">
          <button type="submit" class="tratada {'ativo' if estado == 'tratada' else ''}">Tratada</button>
        </form>
      </div>

      {mensagens_html}

      <form class="reply" method="post" action="/admin/conversa/{telefono}/responder" enctype="multipart/form-data">
        <textarea name="texto" rows="2" placeholder="Escrever resposta..."></textarea>
        <button type="submit">Enviar</button>
        <input class="anexo" type="file" name="ficheiro">
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


@router.post("/conversa/{telefono}/estado")
async def mudar_estado(telefono: str, estado: str = Form(...), auth: bool = Depends(verificar_password)):
    """Alterna entre 'aberta' e 'tratada'."""
    if estado not in ("aberta", "tratada"):
        raise HTTPException(status_code=400, detail="Estado inválido")
    await establecer_estado(telefono, estado)
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


@router.get("/media/{nome_arquivo}")
async def obter_media(nome_arquivo: str, auth: bool = Depends(verificar_password)):
    """Serve um ficheiro guardado localmente (recebido ou enviado numa conversa)."""
    caminho = os.path.join(MEDIA_DIR, nome_arquivo)
    caminho_absoluto = os.path.abspath(caminho)
    diretorio_absoluto = os.path.abspath(MEDIA_DIR)
    if not caminho_absoluto.startswith(diretorio_absoluto) or not os.path.isfile(caminho_absoluto):
        raise HTTPException(status_code=404, detail="Ficheiro não encontrado")
    return FileResponse(caminho_absoluto)

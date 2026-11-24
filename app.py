import os
import re
import json
import uuid
import time
import base64
import shutil
import threading
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from faster_whisper import WhisperModel

app = FastAPI(title="OpusClip Studio AI Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

JOBS_ROOT = Path("/tmp/opusclip_jobs")
JOBS_ROOT.mkdir(parents=True, exist_ok=True)

JOBS: Dict[str, Dict[str, Any]] = {}
WHISPER_MODEL: Optional[WhisperModel] = None
WHISPER_LOCK = threading.Lock()

EMBEDDED_HTML = '<!DOCTYPE html>\n<html lang="pt-BR" class="dark">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover" />\n  <title>OpusClip Studio AI — YouTube + Facecam IA + HD</title>\n  <script src="https://cdn.tailwindcss.com"></script>\n  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=Montserrat:wght@800;900&display=swap" rel="stylesheet">\n  <style>\n    body { background: #09090B; color: #FFFFFF; font-family: \'Inter\', -apple-system, sans-serif; }\n    .pb-safe { padding-bottom: max(1rem, env(safe-area-inset-bottom)); }\n  </style>\n</head>\n<body class="min-h-screen flex flex-col">\n\n  <!-- Top Bar -->\n  <header class="sticky top-0 z-30 bg-[#09090B]/95 backdrop-blur-xl border-b border-zinc-800 px-4 py-3 flex items-center justify-between">\n    <div class="flex items-center gap-2.5">\n      <div class="w-8 h-8 rounded-xl bg-white text-black flex items-center justify-center font-black">⚡</div>\n      <div>\n        <div class="flex items-center gap-1.5">\n          <span class="font-extrabold text-base tracking-tight">OpusClip</span>\n          <span class="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px] font-extrabold">PRO ∞ REAL</span>\n        </div>\n        <p class="text-[10px] text-zinc-400">yt-dlp + Whisper IA + FFmpeg HD 1080×1920</p>\n      </div>\n    </div>\n    <button type="button" onclick="toggleAdvancedDrawer()" class="px-3 py-1.5 rounded-full bg-zinc-800 hover:bg-zinc-700 text-xs font-bold text-zinc-200">\n      ⚙️ API / Cookies\n    </button>\n  </header>\n\n  <main class="flex-1 w-full max-w-4xl mx-auto px-4 pt-5 pb-24 space-y-5">\n\n    <!-- Configurações Opcionais (Gemini Key & Cookies YouTube) -->\n    <div id="advanced-drawer" class="hidden bg-[#141417] border border-zinc-800 rounded-3xl p-4 space-y-3">\n      <h2 class="text-xs font-extrabold uppercase tracking-wider text-emerald-400">Configurações Opcionais do Servidor</h2>\n      <div class="space-y-1">\n        <label class="text-xs font-semibold text-zinc-400">Chave Gemini API (Opcional — melhora títulos e curadoria)</label>\n        <input id="cfg-gemini-key" type="password" placeholder="AIzaSy..." class="w-full bg-black border border-zinc-800 rounded-xl px-3 py-2 text-xs text-white" />\n      </div>\n      <div class="space-y-1">\n        <label class="text-xs font-semibold text-zinc-400">Cookies do YouTube (Opcional — aceita cookies.txt, Base64 ou texto copiado)</label>\n        <textarea id="cfg-cookies-raw" rows="3" placeholder="# Netscape HTTP Cookie File..." class="w-full bg-black border border-zinc-800 rounded-xl px-3 py-2 text-xs text-white"></textarea>\n      </div>\n    </div>\n\n    <!-- Card Principal: Colar Link do YouTube -->\n    <div class="bg-[#141417] border border-zinc-800 rounded-3xl p-4 sm:p-6 space-y-4 shadow-2xl">\n      <div>\n        <h1 class="text-lg sm:text-xl font-extrabold">Cole o Link do YouTube para Cortar em HD</h1>\n        <p class="text-xs text-zinc-400 mt-0.5">Baixa o vídeo direto do YouTube no servidor, transcreve a voz, recorta a Facecam e entrega o MP4 pronto com áudio e sem marca d\'água.</p>\n      </div>\n\n      <div class="flex items-center bg-black border border-zinc-700 focus-within:border-white rounded-2xl px-3.5 py-2.5 gap-2">\n        <span class="px-1.5 py-0.5 rounded bg-red-600 text-[10px] font-black">▶</span>\n        <input\n          id="yt-url"\n          type="url"\n          placeholder="https://www.youtube.com/watch?v=..."\n          class="flex-1 min-w-0 bg-transparent text-xs sm:text-sm text-white placeholder-zinc-500 focus:outline-none"\n        />\n        <button type="button" onclick="pasteUrl()" class="px-3 py-1.5 rounded-xl bg-zinc-800 text-xs font-bold">Colar</button>\n      </div>\n\n      <!-- Opções Rápidas -->\n      <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">\n        <div class="bg-[#1C1C1F] border border-zinc-800 rounded-2xl p-3 space-y-1">\n          <label class="text-[10px] font-bold uppercase text-zinc-400">Quantidade de Cortes</label>\n          <select id="opt-count" class="w-full bg-transparent text-xs font-extrabold text-emerald-400 focus:outline-none">\n            <option value="2" class="bg-zinc-900">2 cortes virais</option>\n            <option value="5" selected class="bg-zinc-900">5 cortes virais</option>\n            <option value="7" class="bg-zinc-900">7 cortes virais</option>\n            <option value="10" class="bg-zinc-900">10 cortes virais</option>\n          </select>\n        </div>\n\n        <div class="bg-[#1C1C1F] border border-zinc-800 rounded-2xl p-3 space-y-1">\n          <label class="text-[10px] font-bold uppercase text-zinc-400">Enquadramento IA</label>\n          <select id="opt-layout" onchange="toggleFacecamCalibrator()" class="w-full bg-transparent text-xs font-extrabold text-white focus:outline-none">\n            <option value="streamer_split" selected class="bg-zinc-900">Streamer Split (Facecam + Jogo)</option>\n            <option value="podcast_fill" class="bg-zinc-900">Preencher 9:16 (Podcast)</option>\n            <option value="blur_bg" class="bg-zinc-900">Fundo Desfocado 16:9</option>\n          </select>\n        </div>\n\n        <div class="bg-[#1C1C1F] border border-zinc-800 rounded-2xl p-3 space-y-1">\n          <label class="text-[10px] font-bold uppercase text-zinc-400">Legendas & Manchete</label>\n          <select id="opt-caption" class="w-full bg-transparent text-xs font-extrabold text-yellow-400 focus:outline-none">\n            <option value="opus_streamer" selected class="bg-zinc-900">Verde Neon + Amarelo + Manchete</option>\n            <option value="hormozi" class="bg-zinc-900">Branco Bold + Amarelo</option>\n            <option value="none" class="bg-zinc-900">Sem Legendas</option>\n          </select>\n        </div>\n      </div>\n\n      <!-- Calibrador de Posição da Facecam do Streamer -->\n      <div id="facecam-box-panel" class="bg-[#1C1C1F] border border-zinc-800 rounded-2xl p-3 space-y-2">\n        <div class="flex items-center justify-between">\n          <span class="text-xs font-bold text-emerald-400">🎥 Posição da Facecam no Vídeo Original</span>\n          <span class="text-[10px] text-zinc-400">Usado no modo Streamer Split</span>\n        </div>\n        <div class="grid grid-cols-3 sm:grid-cols-5 gap-1.5">\n          <button type="button" onclick="setFacecam(0.02, 0.16, 0.25, 0.36, this)" class="fc-btn py-1.5 px-2 rounded-xl bg-white text-black text-[11px] font-extrabold">Esquerda Meio</button>\n          <button type="button" onclick="setFacecam(0.02, 0.03, 0.25, 0.34, this)" class="fc-btn py-1.5 px-2 rounded-xl bg-zinc-800 text-zinc-300 text-[11px] font-bold">Topo Esquerda</button>\n          <button type="button" onclick="setFacecam(0.73, 0.03, 0.25, 0.34, this)" class="fc-btn py-1.5 px-2 rounded-xl bg-zinc-800 text-zinc-300 text-[11px] font-bold">Topo Direita</button>\n          <button type="button" onclick="setFacecam(0.02, 0.62, 0.25, 0.34, this)" class="fc-btn py-1.5 px-2 rounded-xl bg-zinc-800 text-zinc-300 text-[11px] font-bold">Base Esquerda</button>\n          <button type="button" onclick="setFacecam(0.73, 0.62, 0.25, 0.34, this)" class="fc-btn py-1.5 px-2 rounded-xl bg-zinc-800 text-zinc-300 text-[11px] font-bold">Base Direita</button>\n        </div>\n      </div>\n\n      <button\n        type="button"\n        id="btn-start"\n        onclick="startServerJob()"\n        class="w-full py-4 rounded-full bg-white hover:bg-zinc-200 active:scale-[0.99] text-black font-extrabold text-sm transition shadow-xl"\n      >\n        Obter Clipes Reais em 1 Clique (HD Sem Marca d\'Água)\n      </button>\n    </div>\n\n    <!-- Barra de Progresso Real do Servidor -->\n    <div id="progress-card" class="hidden bg-[#141417] border border-emerald-500/40 rounded-3xl p-5 space-y-3">\n      <div class="flex items-center justify-between">\n        <span id="job-step-text" class="text-xs sm:text-sm font-bold text-white">Conectando ao servidor...</span>\n        <span id="job-pct-text" class="text-sm font-mono font-extrabold text-emerald-400">5%</span>\n      </div>\n      <div class="w-full h-3 bg-black rounded-full overflow-hidden">\n        <div id="job-bar" class="h-full w-[5%] bg-emerald-500 transition-all duration-300"></div>\n      </div>\n      <p id="job-error-text" class="hidden text-xs text-rose-400 font-semibold"></p>\n    </div>\n\n    <!-- Resultados Reais Prontos para Assistir e Baixar -->\n    <div id="results-section" class="hidden space-y-3">\n      <h2 class="text-base font-extrabold text-white">✓ Cortes Reais Prontos (1080×1920 HD + Áudio Original)</h2>\n      <div id="clips-grid" class="grid grid-cols-1 sm:grid-cols-2 gap-4"></div>\n    </div>\n\n  </main>\n\n  <script>\n    let selectedFacecam = { x: 0.02, y: 0.16, w: 0.25, h: 0.36 };\n    let pollInterval = null;\n\n    function toggleAdvancedDrawer() {\n      document.getElementById("advanced-drawer").classList.toggle("hidden");\n    }\n\n    function toggleFacecamCalibrator() {\n      const mode = document.getElementById("opt-layout").value;\n      document.getElementById("facecam-box-panel").classList.toggle("hidden", mode !== "streamer_split");\n    }\n\n    function setFacecam(x, y, w, h, btn) {\n      selectedFacecam = { x, y, w, h };\n      document.querySelectorAll(".fc-btn").forEach(b => {\n        b.className = "fc-btn py-1.5 px-2 rounded-xl bg-zinc-800 text-zinc-300 text-[11px] font-bold";\n      });\n      btn.className = "fc-btn py-1.5 px-2 rounded-xl bg-white text-black text-[11px] font-extrabold";\n    }\n\n    async function pasteUrl() {\n      try {\n        const txt = await navigator.clipboard.readText();\n        if (txt) document.getElementById("yt-url").value = txt.trim();\n      } catch (_) {}\n    }\n\n    async function startServerJob() {\n      const url = document.getElementById("yt-url").value.trim();\n      if (!url) {\n        alert("Cole um link válido do YouTube primeiro!");\n        return;\n      }\n\n      const btn = document.getElementById("btn-start");\n      btn.disabled = true;\n      btn.textContent = "Processando no servidor...";\n\n      const progCard = document.getElementById("progress-card");\n      const errEl = document.getElementById("job-error-text");\n      progCard.classList.remove("hidden");\n      errEl.classList.add("hidden");\n      document.getElementById("results-section").classList.add("hidden");\n\n      try {\n        const res = await fetch("/api/jobs", {\n          method: "POST",\n          headers: { "Content-Type": "application/json" },\n          body: JSON.stringify({\n            youtube_url: url,\n            clip_count: parseInt(document.getElementById("opt-count").value, 10),\n            layout_mode: document.getElementById("opt-layout").value,\n            auto_headline: true,\n            caption_style: document.getElementById("opt-caption").value,\n            language: "pt",\n            facecam_box: selectedFacecam,\n            gemini_api_key: document.getElementById("cfg-gemini-key").value.trim() || null,\n            cookies_raw: document.getElementById("cfg-cookies-raw").value.trim() || null\n          })\n        });\n\n        if (!res.ok) {\n          const err = await res.json();\n          throw new Error(err.detail || "Erro ao iniciar processamento.");\n        }\n\n        const { job_id } = await res.json();\n        clearInterval(pollInterval);\n        pollInterval = setInterval(() => pollJobStatus(job_id), 2500);\n      } catch (e) {\n        errEl.textContent = e.message;\n        errEl.classList.remove("hidden");\n        btn.disabled = false;\n        btn.textContent = "Obter Clipes Reais em 1 Clique (HD Sem Marca d\'Água)";\n      }\n    }\n\n    async function pollJobStatus(jobId) {\n      try {\n        const res = await fetch(`/api/jobs/${jobId}`);\n        if (!res.ok) return;\n        const job = await res.json();\n\n        document.getElementById("job-step-text").textContent = job.step;\n        document.getElementById("job-pct-text").textContent = `${job.progress}%`;\n        document.getElementById("job-bar").style.width = `${job.progress}%`;\n\n        if (job.clips && job.clips.length > 0) {\n          renderClips(job.clips);\n        }\n\n        if (job.status === "completed") {\n          clearInterval(pollInterval);\n          const btn = document.getElementById("btn-start");\n          btn.disabled = false;\n          btn.textContent = "Obter Clipes Reais em 1 Clique (HD Sem Marca d\'Água)";\n        } else if (job.status === "error") {\n          clearInterval(pollInterval);\n          const errEl = document.getElementById("job-error-text");\n          errEl.textContent = job.error || "Erro desconhecido no servidor.";\n          errEl.classList.remove("hidden");\n          const btn = document.getElementById("btn-start");\n          btn.disabled = false;\n          btn.textContent = "Tentar Novamente";\n        }\n      } catch (_) {}\n    }\n\n    function renderClips(clips) {\n      document.getElementById("results-section").classList.remove("hidden");\n      const grid = document.getElementById("clips-grid");\n      grid.innerHTML = clips.map(c => `\n        <div class="bg-[#141417] border border-zinc-800 rounded-3xl p-3.5 space-y-3">\n          <div class="aspect-[9/16] w-full rounded-2xl overflow-hidden bg-black border border-zinc-800">\n            <video src="${c.download_url}" controls playsinline preload="metadata" class="w-full h-full object-contain"></video>\n          </div>\n          <div class="flex items-start justify-between gap-2">\n            <div>\n              <div class="text-xs font-extrabold text-white">${c.title}</div>\n              <div class="text-[11px] text-zinc-400 mt-0.5">${c.duration}s • Score Viral: <span class="text-emerald-400 font-bold">${c.score}/100</span></div>\n            </div>\n          </div>\n          <a\n            href="${c.download_url}"\n            download="${c.filename}"\n            class="w-full py-3 rounded-full bg-emerald-500 hover:bg-emerald-400 text-black font-extrabold text-xs flex items-center justify-center gap-1.5 shadow-lg"\n          >\n            <span>⬇ Baixar MP4 HD (Sem Marca d\'Água)</span>\n          </a>\n        </div>\n      `).join("");\n    }\n  </script>\n</body>\n</html>\n'


def get_whisper_model() -> WhisperModel:
    global WHISPER_MODEL
    with WHISPER_LOCK:
        if WHISPER_MODEL is None:
            WHISPER_MODEL = WhisperModel("tiny", device="cpu", compute_type="int8")
        return WHISPER_MODEL


def normalize_netscape_cookies(raw_text: str) -> Optional[str]:
    text = (raw_text or "").strip().strip('"').strip("'")
    if not text:
        return None

    # Decodifica caso venha em Base64
    if "youtube.com" not in text and "# Netscape" not in text:
        try:
            text = base64.b64decode(text).decode("utf-8", errors="ignore").strip()
        except Exception:
            return None

    if "youtube.com" not in text:
        return None

    # Converte sequencias literais \t e \n em tabulacoes e quebras de linha reais
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")

    lines = []
    has_header = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# Netscape HTTP Cookie File") or line.startswith("# HTTP Cookie File"):
            has_header = True
            lines.append("# Netscape HTTP Cookie File")
            continue
        if line.startswith("#"):
            lines.append(line)
            continue
        # Se a linha estiver separada por espacos multiplos em vez de TAB, converte para TAB
        if "\t" not in line:
            parts = re.split(r"\s{2,}", line)
            if len(parts) >= 7:
                line = "\t".join(parts[:7])
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 7:
                lines.append("\t".join(parts[:7]))

    if len(lines) == 0:
        return None
    if not has_header:
        lines.insert(0, "# Netscape HTTP Cookie File")
    return "\n".join(lines) + "\n"


def write_cookies_if_present(job_dir: Path, cookies_raw: Optional[str] = None) -> Optional[Path]:
    raw = (
        cookies_raw
        or os.environ.get("YOUTUBE_COOKIES", "")
        or os.environ.get("YT_COOKIES_B64", "")
    ).strip()
    normalized = normalize_netscape_cookies(raw)
    if not normalized:
        return None
    cookie_path = job_dir / "cookies.txt"
    cookie_path.write_text(normalized, encoding="utf-8")
    return cookie_path


def extract_youtube_id(url: str) -> Optional[str]:
    clean = (url or "").strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", clean):
        return clean
    m = re.search(
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/|youtube\.com/live/|[?&]v=)([a-zA-Z0-9_-]{11})",
        clean,
    )
    return m.group(1) if m else None


class FacecamBox(BaseModel):
    x: float = 0.02
    y: float = 0.16
    w: float = 0.25
    h: float = 0.36


class CreateJobRequest(BaseModel):
    youtube_url: str
    clip_count: int = 5
    layout_mode: str = "streamer_split"
    auto_headline: bool = True
    caption_style: str = "opus_streamer"
    language: str = "pt"
    facecam_box: FacecamBox = FacecamBox()
    gemini_api_key: Optional[str] = None
    cookies_raw: Optional[str] = None


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    for candidate in [
        Path(__file__).parent / "index.html",
        Path(__file__).parent / "static" / "index.html",
    ]:
        if candidate.exists():
            return candidate.read_text(encoding="utf-8")
    return EMBEDDED_HTML


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "yt_dlp": shutil.which("yt-dlp") is not None,
    }


@app.post("/api/jobs")
def create_clip_job(req: CreateJobRequest):
    vid_id = extract_youtube_id(req.youtube_url)
    if not vid_id:
        raise HTTPException(status_code=400, detail="Link do YouTube inválido.")

    existing = sorted(JOBS_ROOT.iterdir(), key=lambda p: p.stat().st_mtime)
    while len(existing) > 4:
        shutil.rmtree(existing.pop(0), ignore_errors=True)

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    JOBS[job_id] = {
        "job_id": job_id,
        "video_id": vid_id,
        "status": "processing",
        "progress": 5,
        "step": "Iniciando download do vídeo real do YouTube...",
        "error": None,
        "title": f"Vídeo {vid_id}",
        "clips": [],
        "created_at": time.time(),
    }

    t = threading.Thread(target=run_pipeline_worker, args=(job_id, req), daemon=True)
    t.start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Projeto não encontrado.")
    return job


@app.get("/api/files/{job_id}/{filename}")
def download_rendered_clip(job_id: str, filename: str):
    safe_name = os.path.basename(filename)
    file_path = JOBS_ROOT / job_id / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(path=str(file_path), media_type="video/mp4", filename=safe_name)


def format_ass_time(seconds: float) -> str:
    s = max(0.0, float(seconds))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    cs = min(99, int(round((s - int(s)) * 100)))
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"


def escape_ass_text(txt: str) -> str:
    return txt.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass_subtitles(
    ass_path: Path,
    words: List[Dict[str, Any]],
    clip_start: float,
    clip_end: float,
    headline: str,
    auto_headline: bool,
    caption_style: str,
):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: OpusCaption,DejaVu Sans,78,&H00FFFFFF,&H0015CCFA,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,6,3,2,60,60,390,1
Style: HeadlineBox,DejaVu Sans,46,&H0009090B,&H0009090B,&H00FFFFFF,&H00FFFFFF,-1,0,0,0,100,100,0,0,3,22,0,8,80,80,580,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []

    if auto_headline and headline.strip():
        h_clean = escape_ass_text(headline.strip().upper()[:48])
        events.append(f"Dialogue: 2,0:00:00.00,0:00:03.50,HeadlineBox,,0,0,0,,{h_clean}")

    if caption_style != "none" and words:
        groups = [words[i : i + 2] for i in range(0, len(words), 2)]
        for grp in groups:
            g_start = max(0.0, grp[0]["start"] - clip_start)
            g_end = max(g_start + 0.15, grp[-1]["end"] - clip_start)
            if g_start >= (clip_end - clip_start):
                continue

            for active_idx, active_w in enumerate(grp):
                w_start = max(0.0, active_w["start"] - clip_start)
                w_end = max(w_start + 0.10, active_w["end"] - clip_start)
                if active_idx == len(grp) - 1:
                    w_end = max(w_end, g_end)

                styled_tokens = []
                for idx2, token in enumerate(grp):
                    word_upper = escape_ass_text(token["word"].strip().upper())
                    if not word_upper:
                        continue
                    if idx2 == active_idx:
                        color_tag = "&H005EC522&" if caption_style == "opus_streamer" else "&H0015CCFA&"
                        styled_tokens.append(
                            f"{{\\c{color_tag}\\fscx108\\fscy108}}{word_upper}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}"
                        )
                    else:
                        adj_color = "&H0015CCFA&" if (caption_style == "opus_streamer" and idx2 % 2 == 1) else "&H00FFFFFF&"
                        styled_tokens.append(f"{{\\c{adj_color}}}{word_upper}")

                line_str = " ".join(styled_tokens)
                if line_str:
                    events.append(
                        f"Dialogue: 1,{format_ass_time(w_start)},{format_ass_time(w_end)},OpusCaption,,0,0,0,,{line_str}"
                    )

    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


def select_viral_segments(
    words: List[Dict[str, Any]],
    total_duration: float,
    clip_count: int,
    video_title: str,
    gemini_key: Optional[str],
) -> List[Dict[str, Any]]:
    target_len = 28.0
    step_len = max(18.0, (total_duration - target_len) / max(1, clip_count * 2))
    candidates = []

    t = 0.0
    while t + 12.0 <= total_duration and len(candidates) < 24:
        end_t = min(total_duration, t + target_len)
        seg_words = [w for w in words if w["start"] >= t and w["end"] <= end_t]
        text = " ".join(w["word"].strip() for w in seg_words).strip()
        exclamations = text.count("!") + text.count("?")
        score_heuristic = len(seg_words) * 2 + exclamations * 12
        candidates.append({
            "start": round(t, 2),
            "end": round(end_t, 2),
            "text": text or f"Momento destaque de {video_title}",
            "heuristic": score_heuristic,
        })
        t += step_len

    if not candidates:
        candidates.append({
            "start": 0.0,
            "end": min(total_duration, 25.0),
            "text": video_title,
            "heuristic": 90,
        })

    api_key = (gemini_key or os.environ.get("GEMINI_API_KEY", "")).strip()
    if api_key and len(candidates) > 1:
        try:
            prompt = (
                f"Você é o curador viral do OpusClip. Título do vídeo: '{video_title}'.\n"
                f"Escolha os {clip_count} melhores trechos abaixo (sem sobreposição) e retorne JSON com lista de objetos contendo: "
                f"index, title, headline (CAIXA ALTA até 6 palavras), score (86-99), reason.\n\n"
                + "\n".join(f"[{i}] ({c['start']}s-{c['end']}s): {c['text'][:200]}" for i, c in enumerate(candidates))
            )
            resp = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=20,
            )
            if resp.ok:
                raw_txt = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_txt)
                items = parsed if isinstance(parsed, list) else parsed.get("clips", [])
                chosen = []
                for rank, it in enumerate(items[:clip_count]):
                    idx = int(it.get("index", rank)) % len(candidates)
                    cand = candidates[idx]
                    chosen.append({
                        "start": cand["start"],
                        "end": cand["end"],
                        "title": it.get("title") or f"Corte Viral #{rank + 1}",
                        "headline": (it.get("headline") or video_title[:38]).upper(),
                        "score": min(99, max(85, int(it.get("score", 96 - rank)))),
                        "reason": it.get("reason") or "Gancho forte detectado pela IA.",
                    })
                if chosen:
                    return chosen
        except Exception:
            pass

    ranked = sorted(candidates, key=lambda x: x["heuristic"], reverse=True)
    selected = []
    for cand in ranked:
        if any(abs(cand["start"] - s["start"]) < 14.0 for s in selected):
            continue
        selected.append(cand)
        if len(selected) >= clip_count:
            break

    out = []
    for idx, cand in enumerate(selected):
        snippet = cand["text"][:42].strip()
        out.append({
            "start": cand["start"],
            "end": cand["end"],
            "title": snippet if len(snippet) > 8 else f"Momento Viral #{idx + 1}",
            "headline": (snippet if len(snippet) > 6 else video_title[:38]).upper(),
            "score": max(86, 98 - idx * 2),
            "reason": "Pico de intensidade vocal detectado na transcrição.",
        })
    return out


def download_youtube_video(canonical_url: str, source_mp4: Path, cookie_file: Optional[Path]):
    client_profiles = [
        "youtube:player_client=ios,tv_embedded,android",
        "youtube:player_client=android,web",
        "youtube:player_client=mweb,web",
    ]
    last_err = "Falha ao baixar vídeo do YouTube."

    for idx, extractor_arg in enumerate(client_profiles):
        if source_mp4.exists():
            source_mp4.unlink()
        dl_cmd = [
            "yt-dlp",
            "-f",
            "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
            "--merge-output-format",
            "mp4",
            "--no-playlist",
            "--extractor-args",
            extractor_arg,
            "-o",
            str(source_mp4),
            canonical_url,
        ]
        # Usa cookies se fornecidos; se falhar na primeira tentativa, tenta sem cookies na ultima
        if cookie_file and (idx < len(client_profiles) - 1):
            dl_cmd.extend(["--cookies", str(cookie_file)])

        dl_proc = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=300)
        if dl_proc.returncode == 0 and source_mp4.exists():
            return
        err_lines = [l for l in (dl_proc.stderr or "").splitlines() if l.strip()]
        if err_lines:
            last_err = err_lines[-1]

    raise RuntimeError(f"YouTube bloqueou ou falhou no download: {last_err}")


def run_pipeline_worker(job_id: str, req: CreateJobRequest):
    job = JOBS[job_id]
    job_dir = JOBS_ROOT / job_id
    vid_id = job["video_id"]
    canonical_url = f"https://www.youtube.com/watch?v={vid_id}"
    cookie_file = write_cookies_if_present(job_dir, req.cookies_raw)

    try:
        job["progress"] = 12
        job["step"] = "Baixando vídeo e áudio original do YouTube (yt-dlp)..."
        source_mp4 = job_dir / "source.mp4"
        download_youtube_video(canonical_url, source_mp4, cookie_file)

        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(source_mp4),
        ]
        total_duration = max(10.0, float(subprocess.check_output(probe_cmd, text=True).strip()))

        job["progress"] = 38
        job["step"] = "Transcrevendo áudio real com Whisper IA..."
        audio_wav = job_dir / "audio.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(source_mp4), "-vn", "-ac", "1", "-ar", "16000", str(audio_wav)],
            capture_output=True,
            check=True,
        )

        model = get_whisper_model()
        segments_gen, _ = model.transcribe(
            str(audio_wav),
            language=req.language if req.language != "auto" else None,
            word_timestamps=True,
        )
        all_words: List[Dict[str, Any]] = []
        for seg in segments_gen:
            if seg.words:
                for w in seg.words:
                    all_words.append({"word": w.word, "start": float(w.start), "end": float(w.end)})

        job["progress"] = 62
        job["step"] = f"Selecionando os {req.clip_count} melhores cortes virais..."
        chosen_clips = select_viral_segments(
            all_words,
            total_duration,
            max(1, min(10, req.clip_count)),
            job["title"],
            req.gemini_api_key,
        )

        fb = req.facecam_box
        fx = max(0.0, min(0.85, fb.x))
        fy = max(0.0, min(0.85, fb.y))
        fw = max(0.10, min(1.0 - fx, fb.w))
        fh = max(0.10, min(1.0 - fy, fb.h))

        total_c = len(chosen_clips)
        for idx, c in enumerate(chosen_clips):
            pct = 68 + int((idx / max(1, total_c)) * 30)
            job["progress"] = pct
            job["step"] = f"Renderizando corte HD {idx + 1}/{total_c} com Facecam IA e áudio..."

            clip_filename = f"OpusClip_HD_Corte_{idx + 1}.mp4"
            clip_out = job_dir / clip_filename
            ass_file = job_dir / f"sub_{idx + 1}.ass"

            clip_words = [w for w in all_words if w["end"] >= c["start"] and w["start"] <= c["end"]]
            build_ass_subtitles(
                ass_file,
                clip_words,
                c["start"],
                c["end"],
                c["headline"],
                req.auto_headline,
                req.caption_style,
            )

            ass_escaped = str(ass_file).replace("\\", "/").replace(":", "\\:")

            if req.layout_mode == "streamer_split":
                vf = (
                    f"[0:v]split=2[vtop][vbot];"
                    f"[vtop]crop=iw*{fw:.4f}:ih*{fh:.4f}:iw*{fx:.4f}:ih*{fy:.4f},"
                    f"scale=1080:614:force_original_aspect_ratio=increase,crop=1080:614[top];"
                    f"[vbot]scale=1080:1306:force_original_aspect_ratio=increase,crop=1080:1306[bot];"
                    f"[top][bot]vstack=inputs=2,subtitles='{ass_escaped}'[outv]"
                )
            elif req.layout_mode == "blur_bg":
                vf = (
                    f"[0:v]split=2[bg][fg];"
                    f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bgb];"
                    f"[fg]scale=1080:-2[fgb];"
                    f"[bgb][fgb]overlay=(W-w)/2:(H-h)/2,subtitles='{ass_escaped}'[outv]"
                )
            else:
                vf = (
                    f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                    f"subtitles='{ass_escaped}'[outv]"
                )

            dur_clip = max(4.0, c["end"] - c["start"])
            ff_cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                f"{c['start']:.2f}",
                "-t",
                f"{dur_clip:.2f}",
                "-i",
                str(source_mp4),
                "-filter_complex",
                vf,
                "-map",
                "[outv]",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "23",
                "-r",
                "30",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(clip_out),
            ]
            ff_proc = subprocess.run(ff_cmd, capture_output=True, text=True, timeout=180)
            if ff_proc.returncode != 0 or not clip_out.exists():
                raise RuntimeError(f"Erro no FFmpeg ao renderizar corte {idx + 1}: {ff_proc.stderr[-300:]}")

            job["clips"].append({
                "index": idx + 1,
                "title": c["title"],
                "headline": c["headline"],
                "start": c["start"],
                "end": c["end"],
                "duration": round(dur_clip, 1),
                "score": c["score"],
                "reason": c["reason"],
                "filename": clip_filename,
                "download_url": f"/api/files/{job_id}/{clip_filename}",
            })

        if source_mp4.exists():
            source_mp4.unlink()

        job["progress"] = 100
        job["status"] = "completed"
        job["step"] = "Todos os cortes HD com áudio real estão prontos!"

    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
        job["step"] = "Erro no processamento"

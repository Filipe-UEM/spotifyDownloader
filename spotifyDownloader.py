"""
╔══════════════════════════════════════════════════════════════════╗
║  AERO MUSIC DOWNLOADER  v3.1                                     ║
║  Dark Cyberpunk × Frutiger Aero × yt-dlp Visual CLI             ║
║  Open Source – MIT License                                       ║
╚══════════════════════════════════════════════════════════════════╝
"""

import io
import os
import queue
import subprocess
import sys
import threading
import time
import math
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
APP_TITLE   = "AERO MUSIC DOWNLOADER"
APP_VERSION = "v3.1"
GITHUB_URL  = "https://github.com/SEU_USUARIO"
AUDIO_EXTS  = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac", ".webm"}

# ─────────────────────────────────────────────
#  PALETTE — Dark Cyberpunk Aero
# ─────────────────────────────────────────────
C = {
    "bg":          "#0D0F14",
    "bg_mid":      "#12151C",
    "bg_panel":    "#161B26",
    "bg_card":     "#1A2030",
    "border":      "#2A3550",
    "border_hi":   "#3D5480",

    "cyan":        "#00E5FF",
    "cyan_dim":    "#007EA8",
    "cyan_glow":   "#00BFDB",
    "green":       "#00FF88",
    "green_dim":   "#007A40",
    "pink":        "#FF4D8C",
    "pink_dim":    "#7A2040",
    "blue":        "#4D9FFF",
    "blue_dim":    "#1A4080",
    "purple":      "#B44DFF",
    "yellow":      "#FFD24D",
    "orange":      "#FF8C4D",

    "text":        "#C8D8F0",
    "text_muted":  "#5A7090",
    "text_dim":    "#2A3A55",

    "ok":          "#003322",
    "ok_fg":       "#00FF88",
    "warn":        "#332200",
    "warn_fg":     "#FFD24D",
    "err":         "#330011",
    "err_fg":      "#FF4D8C",

    "btn":         "#1E2840",
    "btn_hi":      "#2A3860",
    "btn_active":  "#384870",
}

EQ_COLORS = [
    "#00E5FF", "#00CCEE", "#00BBDD", "#4D9FFF",
    "#00FF88", "#00EE77", "#FFD24D", "#FFBB33",
    "#FF8C4D", "#FF4D8C",
]

# ─────────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────────
download_folder: Path = Path.home() / "Músicas"
ui_queue: "queue.Queue" = queue.Queue()
busy = False
eq_tick = 0
eq_heights = [4] * 20
eq_target  = [4] * 20


# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════
def open_path(path: Path):
    try:
        if os.name == "nt":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        messagebox.showerror("Erro", f"Não foi possível abrir:\n{exc}")


def pick_folder():
    global download_folder
    folder = filedialog.askdirectory(
        title="Escolha a pasta de destino",
        initialdir=str(download_folder),
    )
    if folder:
        download_folder = Path(folder)
        folder_var.set(str(download_folder))
        scan_library()


def build_command(link: str, mode: str, folder: Path) -> list:
    is_spotify = "spotify.com" in link
    is_youtube = "youtube.com" in link or "youtu.be" in link

    ext     = ext_var.get()      # mp3 | flac | m4a | opus | wav | ogg | best
    bitrate = bitrate_var.get()  # best | 320k | 256k | 192k | 128k | 64k
    meta    = meta_var.get()     # bool

    # ── SpotDL (Spotify) ──────────────────────────────────────────
    if mode == "spotify" or (mode == "auto" and is_spotify):
        sp_fmt     = ext if ext != "best" else "mp3"
        sp_bitrate = bitrate if bitrate != "best" else "best"
        cmd = ["spotdl", "--audio", "youtube-music",
               "--format", sp_fmt,
               "--bitrate", sp_bitrate,
               "--output", str(folder)]
        # spotDL sempre baixa metadados (título, artista, álbum, capa)
        return cmd + [link]

    # ── yt-dlp ────────────────────────────────────────────────────
    # extensão: "best" = não converte, usa o melhor formato nativo
    audio_fmt     = ext if ext != "best" else "best"
    audio_quality = "0"  # sempre pede a melhor fonte disponível

    cmd = ["yt-dlp", "-x",
           "--audio-format",  audio_fmt,
           "--audio-quality", audio_quality,
           "-P", str(folder)]

    # bitrate: só aplica quando há conversão (ext != best) e ffmpeg disponível
    if bitrate != "best" and ext != "best":
        cmd += ["--postprocessor-args", f"ffmpeg:-b:a {bitrate}"]

    # metadados: embed-metadata funciona com ffmpeg e escreve título/artista/álbum
    # no yt-dlp os metadados vêm do próprio YouTube (uploader, título, etc.)
    # --embed-thumbnail requer ffmpeg e mutagen/AtomicParsley para mp3/m4a
    if meta:
        cmd += [
            "--embed-metadata",          # escreve tags no arquivo (ID3/mp4/ogg etc.)
            "--add-metadata",            # alias legado, garante compatibilidade
            "--embed-thumbnail",         # embute a capa (requer ffmpeg)
            "--convert-thumbnails", "jpg",
            "--parse-metadata", "%(title)s:%(meta_title)s",
            "--parse-metadata", "%(uploader)s:%(meta_artist)s",
        ]

    # ── opções avançadas da UI ─────────────────────────────────────
    # Playlist (só chega aqui no bloco yt-dlp)
    if opt_no_playlist.get():
        cmd.append("--no-playlist")
    if opt_yes_playlist.get():
        cmd.append("--yes-playlist")
    if opt_playlist_random.get():
        cmd.append("--playlist-random")

    # Erros
    if opt_ignore_errors.get():
        cmd.append("--ignore-errors")

    # Metadados extras
    if opt_write_desc.get():
        cmd.append("--write-description")
    if opt_write_info.get():
        cmd.append("--write-info-json")
    if opt_write_thumbnail.get():
        cmd.append("--write-thumbnail")

    # SponsorBlock
    if opt_sponsorblock.get():
        cmd += ["--sponsorblock-remove", "sponsor,intro,outro,selfpromo"]

    # Cookies do browser
    browser = opt_cookies_browser.get()
    if browser != "Nenhum":
        cmd += ["--cookies-from-browser", browser.lower()]

    # Limite de taxa
    rate = opt_limit_rate.get().strip()
    if rate:
        cmd += ["--limit-rate", rate]

    # Seção de tempo
    section = opt_download_section.get().strip()
    if section:
        cmd += ["--download-sections", f"*{section}"]

    # Retries
    retries = opt_retries.get().strip()
    if retries and retries != "10":
        cmd += ["--retries", retries]

    # Fragmentos simultâneos
    frags = opt_concurrent_frags.get().strip()
    if frags and frags != "1":
        cmd += ["--concurrent-fragments", frags]

    # Sobrescrever arquivos
    if opt_no_overwrite.get():
        cmd.append("--no-overwrites")
    if opt_force_overwrite.get():
        cmd.append("--force-overwrites")

    # Nomes de arquivo
    if opt_restrict_filenames.get():
        cmd.append("--restrict-filenames")
    if opt_windows_filenames.get():
        cmd.append("--windows-filenames")

    # ── destino ───────────────────────────────────────────────────
    if mode == "youtube" or (mode == "auto" and is_youtube):
        return cmd + [link]
    query = link if mode == "search" else f"ytsearch1:{link}"
    return cmd + [query]


# ══════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════
def append_log(text: str):
    log_box.configure(state="normal")
    log_box.insert("end", text + "\n")
    log_box.see("end")
    log_box.configure(state="disabled")


def set_status(text: str, color: str = None):
    status_var.set(text)
    status_lbl.configure(fg=color or C["text_muted"])


def set_busy(value: bool):
    global busy
    busy = value
    state = "disabled" if value else "normal"

    # Lista de widgets que devem ser desabilitados/habilitados
    widgets_to_toggle = [
        link_entry, download_btn,
        mode_auto, mode_spotify, mode_youtube, mode_search,
    ]

    # Adiciona os botões de formato (extensão)
    if 'ext_buttons' in globals():
        widgets_to_toggle.extend(ext_buttons.values())

    # Adiciona os botões de bitrate
    if 'br_buttons' in globals():
        widgets_to_toggle.extend(br_buttons.values())

    # Aplica o estado a cada widget
    for w in widgets_to_toggle:
        try:
            w.configure(state=state)
        except Exception:
            pass

    if value:
        progress.start(10)
    else:
        progress.stop()
        progress["value"] = 0


# ══════════════════════════════════════════════
#  AUTO UPDATE AO ABRIR
# ══════════════════════════════════════════════
def auto_update():
    """Atualiza yt-dlp e spotdl silenciosamente em background ao abrir."""
    def _update():
        ui_queue.put(("log", "🔄 Verificando atualizações de yt-dlp e spotdl..."))
        try:
            r1 = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True, text=True, timeout=60
            )
            if "Successfully installed" in r1.stdout:
                ui_queue.put(("log", "✔ yt-dlp atualizado."))
            else:
                ui_queue.put(("log", "✔ yt-dlp já está na versão mais recente."))
        except Exception as e:
            ui_queue.put(("log", f"⚠ Não foi possível atualizar yt-dlp: {e}"))

        try:
            r2 = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "spotdl"],
                capture_output=True, text=True, timeout=60
            )
            if "Successfully installed" in r2.stdout:
                ui_queue.put(("log", "✔ spotdl atualizado."))
            else:
                ui_queue.put(("log", "✔ spotdl já está na versão mais recente."))
        except Exception as e:
            ui_queue.put(("log", f"⚠ Não foi possível atualizar spotdl: {e}"))

        ui_queue.put(("log", "─" * 48))

    threading.Thread(target=_update, daemon=True).start()


# ══════════════════════════════════════════════
#  EQUALIZER ANIMATION
# ══════════════════════════════════════════════
def tick_equalizer():
    global eq_tick, eq_heights, eq_target
    eq_canvas.delete("all")
    w = max(eq_canvas.winfo_width(), 260)
    h = max(eq_canvas.winfo_height(), 60)
    bars    = 20
    spacing = 3
    bar_w   = (w - (bars + 1) * spacing) / bars
    base    = h - 4

    if busy:
        eq_tick = (eq_tick + 1) % 60
        for i in range(bars):
            if eq_tick % 4 == 0:
                phase    = (i / bars) * 2 * math.pi
                wave     = math.sin(phase + eq_tick * 0.25) * 18
                eq_target[i] = max(6, min(h - 10, int(20 + wave + (i % 3) * 5)))
            diff = eq_target[i] - eq_heights[i]
            eq_heights[i] = eq_heights[i] + diff * 0.3
    else:
        for i in range(bars):
            eq_heights[i] = max(4, eq_heights[i] * 0.85)

    for i in range(bars):
        x0  = spacing + i * (bar_w + spacing)
        x1  = x0 + bar_w
        h_b = max(4, int(eq_heights[i]))
        y0  = base - h_b
        y1  = base
        col = EQ_COLORS[i % len(EQ_COLORS)]
        eq_canvas.create_rectangle(x0, y0, x1, y1, outline="", fill=col)
        eq_canvas.create_rectangle(x0, y0, x1, y0 + 2, outline="", fill="#ffffff33")
        eq_canvas.create_rectangle(x0, y0 - 3, x1, y0 - 1, outline="", fill=col)

    root.after(40, tick_equalizer)


# ══════════════════════════════════════════════
#  DOWNLOAD
# ══════════════════════════════════════════════
def run_download():
    global download_folder
    link = link_var.get().strip()
    if not link:
        messagebox.showwarning("Aviso", "Cole um link, URL ou termo de busca primeiro.")
        return

    folder = filedialog.askdirectory(
        title="Escolha onde salvar",
        initialdir=str(download_folder),
    )
    if not folder:
        return
    download_folder = Path(folder)
    folder_var.set(str(download_folder))
    download_folder.mkdir(parents=True, exist_ok=True)

    cmd = build_command(link, mode_var.get(), download_folder)

    set_busy(True)
    set_status("Iniciando download...", C["cyan"])
    append_log(f"❯ {' '.join(cmd)}")

    def worker():
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    ui_queue.put(("log", line))
                    if "%" in line or "download" in line.lower():
                        ui_queue.put(("status_ok", "Baixando..."))

            code = proc.wait()
            if code == 0:
                ui_queue.put(("status_ok", "✔ Download concluído!"))
                ui_queue.put(("log", "─" * 48))
            else:
                ui_queue.put(("status_err", f"Finalizado com erro (código {code})."))
                ui_queue.put(("log", f"Processo retornou código {code}."))
        except FileNotFoundError as exc:
            ui_queue.put(("status_err", "Ferramenta não encontrada no PATH."))
            ui_queue.put(("log", f"Erro: {exc}"))
            messagebox.showerror(
                "Ferramenta não encontrada",
                "yt-dlp ou spotdl não está instalado.\n\nInstale com:\n  pip install yt-dlp spotdl"
            )
        except Exception as exc:
            ui_queue.put(("status_err", "Erro durante o download."))
            ui_queue.put(("log", f"Erro inesperado: {exc}"))
        finally:
            ui_queue.put(("done", None))

    threading.Thread(target=worker, daemon=True).start()


# ══════════════════════════════════════════════
#  QUEUE POLLING
# ══════════════════════════════════════════════
def poll_queue():
    try:
        while True:
            kind, payload = ui_queue.get_nowait()
            if kind == "log" and payload:
                append_log(payload)
            elif kind == "status_ok" and payload:
                set_status(payload, C["green"])
            elif kind == "status_err" and payload:
                set_status(payload, C["pink"])
            elif kind == "done":
                set_busy(False)
                scan_library()
                set_status("Pronto.", C["text_muted"])
    except queue.Empty:
        pass
    root.after(100, poll_queue)


# ══════════════════════════════════════════════
#  METADATA
# ══════════════════════════════════════════════
def get_metadata(path: Path) -> dict:
    info = {
        "Arquivo": path.name,
        "Tamanho": f"{path.stat().st_size / (1024 * 1024):.2f} MB",
    }
    if MutagenFile is None:
        return info
    try:
        audio = MutagenFile(path)
        if audio is None:
            return info
        if getattr(audio, "tags", None):
            for key in ("title", "artist", "album", "date", "genre",
                        "tracknumber", "albumartist"):
                try:
                    value = audio.tags.get(key)
                    if value:
                        info[key.capitalize()] = (
                            str(value[0]) if isinstance(value, list) else str(value)
                        )
                except Exception:
                    pass
        if hasattr(audio, "info") and audio.info is not None:
            length  = getattr(audio.info, "length",  None)
            bitrate = getattr(audio.info, "bitrate", None)
            sample  = getattr(audio.info, "sample_rate", None)
            if length:
                mins, secs = int(length // 60), int(length % 60)
                info["Duração"] = f"{mins:02d}:{secs:02d}"
            if bitrate:
                info["Bitrate"] = f"{int(bitrate / 1000)} kbps"
            if sample:
                info["Sample"] = f"{sample} Hz"
    except Exception:
        pass
    return info


def show_metadata(path_str: str):
    path = Path(path_str)
    if not path.exists():
        return
    meta = get_metadata(path)
    details_text.configure(state="normal")
    details_text.delete("1.0", "end")
    for k, v in meta.items():
        details_text.insert("end", f"  {k}:\n", "key")
        details_text.insert("end", f"  {v}\n\n", "val")
    details_text.configure(state="disabled")

    if PIL_AVAILABLE:
        thumb_canvas.delete("all")
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            thumb_path = path.with_suffix(ext)
            if thumb_path.exists():
                try:
                    img = Image.open(thumb_path).resize((160, 160))
                    photo = ImageTk.PhotoImage(img)
                    thumb_canvas._photo = photo
                    thumb_canvas.create_image(80, 80, image=photo)
                except Exception:
                    pass
                break


def scan_library():
    library_tree.delete(*library_tree.get_children())
    if not download_folder.exists():
        return
    files = [
        p for p in download_folder.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files:
        size_mb = p.stat().st_size / (1024 * 1024)
        library_tree.insert(
            "", "end",
            values=(p.name, p.suffix.upper().lstrip("."),
                    f"{size_mb:.2f} MB", str(p)),
        )
    count = len(files)
    lib_count_var.set(f"{count} arquivo(s)")
    set_status(f"{count} arquivo(s) na pasta.", C["text_muted"])


def on_select_file(_event=None):
    sel = library_tree.selection()
    if not sel:
        return
    values = library_tree.item(sel[0], "values")
    if values and len(values) >= 4:
        show_metadata(values[3])


def clear_log():
    log_box.configure(state="normal")
    log_box.delete("1.0", "end")
    log_box.configure(state="disabled")


def copy_selected_path():
    sel = library_tree.selection()
    if not sel:
        return
    values = library_tree.item(sel[0], "values")
    if values and len(values) >= 4:
        root.clipboard_clear()
        root.clipboard_append(values[3])
        set_status("Caminho copiado.", C["green"])


# ══════════════════════════════════════════════
#  ROOT WINDOW
# ══════════════════════════════════════════════
root = tk.Tk()
root.title(f"{APP_TITLE}  {APP_VERSION}")
root.geometry("1200x800")
root.minsize(1000, 700)
root.configure(bg=C["bg"])

FONT_MONO  = ("Courier New", 9)
FONT_UI    = ("Segoe UI", 10)
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_SUB   = ("Segoe UI", 9)
FONT_LABEL = ("Segoe UI", 9, "bold")

# ── ttk style ──────────────────────────────────
style = ttk.Style()
style.theme_use("clam")
style.configure(".",
    background=C["bg"],
    foreground=C["text"],
    fieldbackground=C["bg_card"],
    troughcolor=C["bg_mid"],
    bordercolor=C["border"],
    selectbackground=C["border_hi"],
    selectforeground=C["cyan"],
)
style.configure("TFrame",        background=C["bg"])
style.configure("TLabel",        background=C["bg"], foreground=C["text"], font=FONT_UI)

style.configure("TButton",
    font=FONT_UI, padding=7,
    background=C["btn"],
    foreground=C["text"],
    relief="flat", borderwidth=1,
    bordercolor=C["border"],
)
style.map("TButton",
    background=[("active", C["btn_hi"]), ("disabled", C["bg_card"])],
    foreground=[("disabled", C["text_dim"])],
)

style.configure("Accent.TButton",
    font=("Segoe UI", 11, "bold"), padding=10,
    background=C["cyan_dim"],
    foreground=C["cyan"],
    relief="flat",
)
style.map("Accent.TButton",
    background=[("active", C["blue_dim"]), ("disabled", C["bg_card"])],
    foreground=[("active", C["cyan"]), ("disabled", C["text_dim"])],
)

style.configure("Danger.TButton",
    font=FONT_UI, padding=7,
    background=C["pink_dim"],
    foreground=C["pink"],
    relief="flat",
)
style.map("Danger.TButton",
    background=[("active", "#5A1030")],
)

# ── toggle buttons: extensão e bitrate ──────────
style.configure("Toggle.TButton",
    font=("Segoe UI", 9, "bold"), padding=(8, 5),
    background=C["btn"],
    foreground=C["text_muted"],
    relief="flat", borderwidth=1,
)
style.map("Toggle.TButton",
    background=[("active", C["btn_hi"]), ("disabled", C["bg_card"])],
    foreground=[("active", C["text"])],
)
style.configure("ToggleOn.TButton",
    font=("Segoe UI", 9, "bold"), padding=(8, 5),
    background=C["cyan_dim"],
    foreground=C["cyan"],
    relief="flat", borderwidth=1,
)
style.map("ToggleOn.TButton",
    background=[("active", C["blue_dim"])],
    foreground=[("active", C["cyan"])],
)
style.configure("ToggleOnGreen.TButton",
    font=("Segoe UI", 9, "bold"), padding=(8, 5),
    background=C["green_dim"],
    foreground=C["green"],
    relief="flat", borderwidth=1,
)
style.map("ToggleOnGreen.TButton",
    background=[("active", "#005A30")],
    foreground=[("active", C["green"])],
)
style.configure("ToggleOnPurple.TButton",
    font=("Segoe UI", 9, "bold"), padding=(8, 5),
    background="#3A1A6A",
    foreground=C["purple"],
    relief="flat", borderwidth=1,
)
style.map("ToggleOnPurple.TButton",
    background=[("active", "#4A2A80")],
    foreground=[("active", C["purple"])],
)

style.configure("Treeview",
    background=C["bg_card"],
    fieldbackground=C["bg_card"],
    foreground=C["text"],
    rowheight=26,
    font=FONT_UI,
)
style.configure("Treeview.Heading",
    background=C["bg_panel"],
    foreground=C["cyan"],
    font=FONT_LABEL,
    relief="flat",
)
style.map("Treeview",
    background=[("selected", C["border_hi"])],
    foreground=[("selected", C["cyan"])],
)

style.configure("TRadiobutton",
    background=C["bg_card"],
    foreground=C["text"],
    font=FONT_UI,
    indicatorcolor=C["cyan"],
)
style.map("TRadiobutton",
    background=[("active", C["bg_card"])],
    indicatorcolor=[("selected", C["cyan"])],
)

style.configure("TCheckbutton",
    background=C["bg_card"],
    foreground=C["text"],
    font=FONT_SUB,
    indicatorcolor=C["cyan"],
)
style.map("TCheckbutton",
    background=[("active", C["bg_card"])],
    indicatorcolor=[("selected", C["cyan"])],
)

style.configure("TProgressbar",
    troughcolor=C["bg_panel"],
    background=C["cyan"],
    thickness=3,
)
style.configure("TScrollbar",
    background=C["bg_panel"],
    troughcolor=C["bg_mid"],
    arrowcolor=C["text_dim"],
    borderwidth=0,
)
style.configure("TNotebook",
    background=C["bg"],
    borderwidth=0,
    tabmargins=0,
)
style.configure("TNotebook.Tab",
    background=C["bg_panel"],
    foreground=C["text_muted"],
    font=FONT_LABEL,
    padding=(12, 5),
    borderwidth=0,
)
style.map("TNotebook.Tab",
    background=[("selected", C["bg_card"])],
    foreground=[("selected", C["cyan"])],
)

# ── helper: card frame ──────────────────────────
def card(parent, **kw):
    return tk.Frame(parent,
        bg=C["bg_card"],
        highlightbackground=C["border"],
        highlightthickness=1,
        **kw)

def section_label(parent, text):
    tk.Label(parent, text=text, font=FONT_LABEL,
             fg=C["cyan"], bg=C["bg_card"]).pack(anchor="w", padx=12, pady=(10, 3))


# ══════════════════════════════════════════════
#  LAYOUT — ROOT
# ══════════════════════════════════════════════
main = tk.Frame(root, bg=C["bg"], padx=10, pady=10)
main.pack(fill="both", expand=True)

# ── HEADER ────────────────────────────────────
header = tk.Frame(main, bg=C["bg"])
header.pack(fill="x", pady=(0, 8))

title_frame = tk.Frame(header, bg=C["bg"])
title_frame.pack(side="left")

tk.Label(title_frame, text="◈ AERO MUSIC",
         font=("Segoe UI", 22, "bold"), fg=C["cyan"], bg=C["bg"]).pack(anchor="w")
tk.Label(title_frame, text=f"DOWNLOADER  {APP_VERSION}  ·  dark cyberpunk edition",
         font=("Segoe UI", 9), fg=C["text_muted"], bg=C["bg"]).pack(anchor="w")

gh_btn = tk.Label(header, text="[ GitHub ]",
                  font=("Segoe UI", 9, "underline"),
                  fg=C["blue"], bg=C["bg"], cursor="hand2")
gh_btn.pack(side="right", padx=12)
gh_btn.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))

status_var = tk.StringVar(value="Iniciando...")
status_lbl = tk.Label(header, textvariable=status_var,
                       font=FONT_SUB, fg=C["text_muted"], bg=C["bg"])
status_lbl.pack(side="right", padx=8)

progress = ttk.Progressbar(main, mode="indeterminate", style="TProgressbar")
progress.pack(fill="x", pady=(0, 8))

# ── BODY (notebook + right panel) ─────────────
body = tk.Frame(main, bg=C["bg"])
body.pack(fill="both", expand=True)

# ── LEFT (notebook com abas) ──────────────────
left = tk.Frame(body, bg=C["bg"])
left.pack(side="left", fill="both", expand=True, padx=(0, 8))

notebook = ttk.Notebook(left)
notebook.pack(fill="both", expand=True)

# ═══════════════════════════════
#  ABA 1 — DOWNLOAD
# ═══════════════════════════════
tab_dl = tk.Frame(notebook, bg=C["bg_card"])
notebook.add(tab_dl, text="  ⬇  DOWNLOAD  ")

# input card
input_card = card(tab_dl)
input_card.pack(fill="x", padx=8, pady=8, ipadx=4, ipady=4)

section_label(input_card, "LINK / URL / BUSCA")
link_var = tk.StringVar()
link_entry = tk.Entry(
    input_card,
    textvariable=link_var,
    font=("Courier New", 12),
    bg=C["bg_mid"],
    fg=C["cyan"],
    insertbackground=C["cyan"],
    relief="flat",
    bd=8,
    highlightthickness=1,
    highlightcolor=C["border_hi"],
    highlightbackground=C["border"],
)
link_entry.pack(fill="x", padx=12, pady=(0, 10))
link_entry.focus()

# modo
row_mode = tk.Frame(input_card, bg=C["bg_card"])
row_mode.pack(fill="x", padx=12, pady=(0, 6))
tk.Label(row_mode, text="MODO:", font=FONT_LABEL, fg=C["text_muted"], bg=C["bg_card"]).pack(side="left")
mode_var = tk.StringVar(value="auto")
for val, lbl in [("auto","Auto"),("spotify","Spotify"),("youtube","YouTube"),("search","Busca texto")]:
    rb = ttk.Radiobutton(row_mode, text=lbl, variable=mode_var, value=val, style="TRadiobutton")
    rb.pack(side="left", padx=(8,0))
    if val == "auto":    mode_auto    = rb
    elif val == "spotify": mode_spotify = rb
    elif val == "youtube": mode_youtube = rb
    else:                  mode_search  = rb

# ── EXTENSÃO ─────────────────────────────────
ext_card = card(input_card)
ext_card.pack(fill="x", padx=12, pady=(0, 6), ipadx=4, ipady=4)

ext_header = tk.Frame(ext_card, bg=C["bg_card"])
ext_header.pack(fill="x", padx=8, pady=(6,4))
tk.Label(ext_header, text="EXTENSÃO / FORMATO", font=FONT_LABEL,
         fg=C["text_muted"], bg=C["bg_card"]).pack(side="left")
tk.Label(ext_header, text="(yt-dlp converte via ffmpeg — requer ffmpeg instalado)",
         font=("Segoe UI",8), fg=C["text_dim"], bg=C["bg_card"]).pack(side="left", padx=6)

ext_var = tk.StringVar(value="mp3")

EXT_OPTIONS = [
    ("mp3",  "MP3",  "ToggleOn"),
    ("flac", "FLAC", "Toggle"),
    ("m4a",  "M4A",  "Toggle"),
    ("opus", "OPUS", "Toggle"),
    ("wav",  "WAV",  "Toggle"),
    ("ogg",  "OGG",  "Toggle"),
    ("best", "BEST\n(nativo)", "Toggle"),
]

ext_btn_row = tk.Frame(ext_card, bg=C["bg_card"])
ext_btn_row.pack(fill="x", padx=8, pady=(0,6))
ext_buttons = {}

def select_ext(val):
    ext_var.set(val)
    for v, btn in ext_buttons.items():
        if v == val:
            btn.configure(style="ToggleOn.TButton")
        else:
            btn.configure(style="Toggle.TButton")
    # bitrate só faz sentido quando há conversão
    _update_bitrate_state()

for val, lbl, _ in EXT_OPTIONS:
    style_name = "ToggleOn.TButton" if val == "mp3" else "Toggle.TButton"
    b = ttk.Button(ext_btn_row, text=lbl, style=style_name,
                   command=lambda v=val: select_ext(v))
    b.pack(side="left", padx=(0,4))
    ext_buttons[val] = b

# ── BITRATE ──────────────────────────────────
br_card = card(input_card)
br_card.pack(fill="x", padx=12, pady=(0, 6), ipadx=4, ipady=4)

br_header = tk.Frame(br_card, bg=C["bg_card"])
br_header.pack(fill="x", padx=8, pady=(6,4))
tk.Label(br_header, text="BITRATE", font=FONT_LABEL,
         fg=C["text_muted"], bg=C["bg_card"]).pack(side="left")
br_note = tk.Label(br_header, text="(ignorado para FLAC/WAV/BEST — lossless não usa bitrate CBR)",
                   font=("Segoe UI",8), fg=C["text_dim"], bg=C["bg_card"])
br_note.pack(side="left", padx=6)

bitrate_var = tk.StringVar(value="320k")

BR_OPTIONS = [
    ("320k", "320 kbps", "ToggleOnGreen"),
    ("256k", "256 kbps", "Toggle"),
    ("192k", "192 kbps", "Toggle"),
    ("128k", "128 kbps", "Toggle"),
    ("64k",  "64 kbps",  "Toggle"),
    ("best", "BEST\n(VBR)", "Toggle"),
]

br_btn_row = tk.Frame(br_card, bg=C["bg_card"])
br_btn_row.pack(fill="x", padx=8, pady=(0,6))
br_buttons = {}

def select_bitrate(val):
    bitrate_var.set(val)
    for v, btn in br_buttons.items():
        if v == val:
            btn.configure(style="ToggleOnGreen.TButton")
        else:
            btn.configure(style="Toggle.TButton")

for val, lbl, _ in BR_OPTIONS:
    style_name = "ToggleOnGreen.TButton" if val == "320k" else "Toggle.TButton"
    b = ttk.Button(br_btn_row, text=lbl, style=style_name,
                   command=lambda v=val: select_bitrate(v))
    b.pack(side="left", padx=(0,4))
    br_buttons[val] = b

def _update_bitrate_state():
    """Desativa bitrate para formatos lossless/best (sem conversão CBR)."""
    lossless = ext_var.get() in ("flac", "wav", "best")
    for btn in br_buttons.values():
        btn.configure(state="disabled" if lossless else "normal")

# ── METADADOS ────────────────────────────────
meta_card = card(input_card)
meta_card.pack(fill="x", padx=12, pady=(0, 6), ipadx=4, ipady=4)

meta_header = tk.Frame(meta_card, bg=C["bg_card"])
meta_header.pack(fill="x", padx=8, pady=(6,4))
tk.Label(meta_header, text="METADADOS & CAPA", font=FONT_LABEL,
         fg=C["text_muted"], bg=C["bg_card"]).pack(side="left")

meta_var = tk.BooleanVar(value=True)

meta_row = tk.Frame(meta_card, bg=C["bg_card"])
meta_row.pack(fill="x", padx=8, pady=(0,6))

meta_on_btn  = None
meta_off_btn = None

def select_meta(val: bool):
    meta_var.set(val)
    if val:
        meta_on_btn.configure(style="ToggleOnPurple.TButton")
        meta_off_btn.configure(style="Toggle.TButton")
    else:
        meta_on_btn.configure(style="Toggle.TButton")
        meta_off_btn.configure(style="Toggle.TButton")

meta_on_btn = ttk.Button(meta_row, text="ATIVADO\n(embed tags + capa)",
                          style="ToggleOnPurple.TButton",
                          command=lambda: select_meta(True))
meta_on_btn.pack(side="left", padx=(0,4))

meta_off_btn = ttk.Button(meta_row, text="DESATIVADO\n(arquivo puro)",
                           style="Toggle.TButton",
                           command=lambda: select_meta(False))
meta_off_btn.pack(side="left")

meta_info = tk.Label(meta_card,
    text="yt-dlp: usa título/uploader do YouTube como tags  |  spotDL: metadados completos do Spotify (artista, álbum, capa, ISRC)",
    font=("Segoe UI",8), fg=C["text_dim"], bg=C["bg_card"], wraplength=650, justify="left")
meta_info.pack(anchor="w", padx=8, pady=(0,6))

# ── BOTÕES DE AÇÃO ───────────────────────────
btn_row = tk.Frame(input_card, bg=C["bg_card"])
btn_row.pack(fill="x", padx=12, pady=(0, 10))
download_btn = ttk.Button(btn_row, text="⬇  BAIXAR", style="Accent.TButton", command=run_download)
download_btn.pack(side="left")
ttk.Button(btn_row, text="📂 Abrir pasta", command=lambda: open_path(download_folder)).pack(side="left", padx=6)
ttk.Button(btn_row, text="📁 Mudar pasta", command=pick_folder).pack(side="left")
ttk.Button(btn_row, text="↻ Atualizar", command=scan_library).pack(side="left", padx=6)
ttk.Button(btn_row, text="✕ Limpar log", style="Danger.TButton", command=clear_log).pack(side="right")

# ── PASTA ────────────────────────────────────
folder_card = card(tab_dl)
folder_card.pack(fill="x", padx=8, pady=(0,4), ipadx=4, ipady=4)
section_label(folder_card, "PASTA DE DESTINO")
folder_var = tk.StringVar(value=str(download_folder))
tk.Label(folder_card, textvariable=folder_var,
         font=("Segoe UI", 8), fg=C["text_muted"], bg=C["bg_card"],
         wraplength=600, justify="left").pack(anchor="w", padx=12, pady=(0,8))

# ── EQ ───────────────────────────────────────
eq_card = card(tab_dl)
eq_card.pack(fill="x", padx=8, pady=(0,8), ipadx=4, ipady=4)
section_label(eq_card, "EQUALIZER")
eq_canvas = tk.Canvas(eq_card, height=55, bg=C["bg_mid"], highlightthickness=0)
eq_canvas.pack(fill="x", padx=12, pady=(0,8))

# ═══════════════════════════════
#  ABA 2 — OPÇÕES AVANÇADAS
# ═══════════════════════════════
tab_opts = tk.Frame(notebook, bg=C["bg_card"])
notebook.add(tab_opts, text="  ⚙  OPÇÕES AVANÇADAS  ")

# scroll frame dentro da aba
opts_canvas = tk.Canvas(tab_opts, bg=C["bg_card"], highlightthickness=0)
opts_scroll = ttk.Scrollbar(tab_opts, orient="vertical", command=opts_canvas.yview)
opts_inner = tk.Frame(opts_canvas, bg=C["bg_card"])
opts_inner.bind("<Configure>", lambda e: opts_canvas.configure(scrollregion=opts_canvas.bbox("all")))
opts_canvas.create_window((0,0), window=opts_inner, anchor="nw")
opts_canvas.configure(yscrollcommand=opts_scroll.set)
opts_canvas.pack(side="left", fill="both", expand=True)
opts_scroll.pack(side="right", fill="y")

def opts_section(text):
    f = tk.Frame(opts_inner, bg=C["bg_panel"], height=1)
    f.pack(fill="x", padx=10, pady=(14,2))
    tk.Label(opts_inner, text=text, font=FONT_LABEL,
             fg=C["cyan"], bg=C["bg_card"]).pack(anchor="w", padx=14, pady=(0,4))

def opts_check(parent, text, var, tooltip=""):
    row = tk.Frame(parent, bg=C["bg_card"])
    row.pack(fill="x", padx=14, pady=1)
    cb = ttk.Checkbutton(row, text=text, variable=var)
    cb.pack(side="left")
    if tooltip:
        tk.Label(row, text=f"  ← {tooltip}", font=("Segoe UI",8),
                 fg=C["text_muted"], bg=C["bg_card"]).pack(side="left")

def opts_entry(parent, label, var, width=12, tooltip=""):
    row = tk.Frame(parent, bg=C["bg_card"])
    row.pack(fill="x", padx=14, pady=3)
    tk.Label(row, text=label, font=FONT_LABEL, fg=C["text_muted"],
             bg=C["bg_card"], width=22, anchor="w").pack(side="left")
    e = tk.Entry(row, textvariable=var, width=width,
                 bg=C["bg_mid"], fg=C["cyan"], insertbackground=C["cyan"],
                 relief="flat", bd=4,
                 highlightthickness=1, highlightbackground=C["border"])
    e.pack(side="left")
    if tooltip:
        tk.Label(row, text=f"  {tooltip}", font=("Segoe UI",8),
                 fg=C["text_muted"], bg=C["bg_card"]).pack(side="left")

# ── Playlist ──────────────────────────────────
opts_section("▸ PLAYLIST")
opt_no_playlist    = tk.BooleanVar()
opt_yes_playlist   = tk.BooleanVar()
opt_playlist_random = tk.BooleanVar()
opts_check(opts_inner, "--no-playlist",     opt_no_playlist,    "Baixa só o vídeo quando URL tem playlist")
opts_check(opts_inner, "--yes-playlist",    opt_yes_playlist,   "Baixa a playlist inteira")
opts_check(opts_inner, "--playlist-random", opt_playlist_random,"Ordem aleatória na playlist")

# ── Erros ─────────────────────────────────────
opts_section("▸ ERROS E RETENTATIVAS")
opt_ignore_errors = tk.BooleanVar()
opt_retries_var   = tk.StringVar(value="10")
opt_retries       = opt_retries_var
opts_check(opts_inner, "--ignore-errors",  opt_ignore_errors, "Ignora erros e continua")
opts_entry(opts_inner, "--retries",        opt_retries_var,   tooltip="padrão: 10")

# ── Download ──────────────────────────────────
opts_section("▸ DOWNLOAD")
opt_limit_rate_var     = tk.StringVar()
opt_limit_rate         = opt_limit_rate_var
opt_concurrent_frags_var = tk.StringVar(value="1")
opt_concurrent_frags   = opt_concurrent_frags_var
opt_download_section_var = tk.StringVar()
opt_download_section   = opt_download_section_var
opts_entry(opts_inner, "--limit-rate",           opt_limit_rate_var,        tooltip="ex: 500K ou 2M  (vazio = sem limite)")
opts_entry(opts_inner, "--concurrent-fragments", opt_concurrent_frags_var,  tooltip="padrão: 1")
opts_entry(opts_inner, "--download-sections",    opt_download_section_var,  tooltip="ex: 1:30-3:00  (trecho de tempo)")

# ── Metadados / Arquivos extras ────────────────
opts_section("▸ METADADOS E ARQUIVOS EXTRAS")
opt_write_desc      = tk.BooleanVar()
opt_write_info      = tk.BooleanVar()
opt_write_thumbnail = tk.BooleanVar()
opts_check(opts_inner, "--write-description",  opt_write_desc,      "Salva a descrição em .txt")
opts_check(opts_inner, "--write-info-json",    opt_write_info,      "Salva metadados em .json")
opts_check(opts_inner, "--write-thumbnail",    opt_write_thumbnail, "Salva a capa separada em disco")

# ── Sobrescrever ──────────────────────────────
opts_section("▸ SOBRESCRITA DE ARQUIVOS")
opt_no_overwrite    = tk.BooleanVar()
opt_force_overwrite = tk.BooleanVar()
opts_check(opts_inner, "--no-overwrites",   opt_no_overwrite,    "Nunca sobrescreve arquivos existentes")
opts_check(opts_inner, "--force-overwrites",opt_force_overwrite, "Sempre sobrescreve tudo")

# ── Nomes de arquivo ──────────────────────────
opts_section("▸ NOMES DE ARQUIVO")
opt_restrict_filenames = tk.BooleanVar()
opt_windows_filenames  = tk.BooleanVar()
opts_check(opts_inner, "--restrict-filenames", opt_restrict_filenames, "Só ASCII, sem espaços")
opts_check(opts_inner, "--windows-filenames",  opt_windows_filenames,  "Compatível com Windows")

# ── SponsorBlock ──────────────────────────────
opts_section("▸ SPONSORBLOCK  (requer ffmpeg)")
opt_sponsorblock = tk.BooleanVar()
opts_check(opts_inner, "--sponsorblock-remove sponsor,intro,outro,selfpromo",
           opt_sponsorblock, "Remove segmentos de patrocínio/intro/outro")

# ── Cookies do browser ────────────────────────
opts_section("▸ COOKIES DO BROWSER  (para vídeos privados/com login)")
row_cookies = tk.Frame(opts_inner, bg=C["bg_card"])
row_cookies.pack(fill="x", padx=14, pady=4)
tk.Label(row_cookies, text="--cookies-from-browser", font=FONT_LABEL,
         fg=C["text_muted"], bg=C["bg_card"], width=22, anchor="w").pack(side="left")
opt_cookies_browser = tk.StringVar(value="Nenhum")
browsers = ["Nenhum", "Chrome", "Firefox", "Edge", "Brave", "Opera", "Vivaldi"]
cb_menu = ttk.Combobox(row_cookies, textvariable=opt_cookies_browser,
                        values=browsers, state="readonly", width=14,
                        font=FONT_UI)
cb_menu.pack(side="left")

# espaço final
tk.Frame(opts_inner, bg=C["bg_card"], height=20).pack()

# ═══════════════════════════════
#  ABA 3 — BIBLIOTECA
# ═══════════════════════════════
tab_lib = tk.Frame(notebook, bg=C["bg_card"])
notebook.add(tab_lib, text="  🎵  BIBLIOTECA  ")

lib_header = tk.Frame(tab_lib, bg=C["bg_card"])
lib_header.pack(fill="x", padx=10, pady=(8,4))
tk.Label(lib_header, text="BIBLIOTECA LOCAL", font=FONT_LABEL,
         fg=C["cyan"], bg=C["bg_card"]).pack(side="left")
lib_count_var = tk.StringVar(value="0 arquivo(s)")
tk.Label(lib_header, textvariable=lib_count_var, font=FONT_SUB,
         fg=C["text_muted"], bg=C["bg_card"]).pack(side="right")

tree_wrap = tk.Frame(tab_lib, bg=C["bg_card"])
tree_wrap.pack(fill="both", expand=True, padx=8, pady=(0,6))

columns = ("nome", "tipo", "tamanho", "path")
library_tree = ttk.Treeview(tree_wrap, columns=columns,
                              show="headings", selectmode="browse")
for col, head, width in [
    ("nome",    "Nome",    350),
    ("tipo",    "Tipo",     60),
    ("tamanho", "Tamanho",  90),
    ("path",    "Caminho", 400),
]:
    library_tree.heading(col, text=head)
    library_tree.column(col, width=width, anchor="w")

ys = ttk.Scrollbar(tree_wrap, orient="vertical",   command=library_tree.yview)
xs = ttk.Scrollbar(tree_wrap, orient="horizontal",  command=library_tree.xview)
library_tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
library_tree.grid(row=0, column=0, sticky="nsew")
ys.grid(row=0, column=1, sticky="ns")
xs.grid(row=1, column=0, sticky="ew")
tree_wrap.rowconfigure(0, weight=1)
tree_wrap.columnconfigure(0, weight=1)

library_tree.bind("<<TreeviewSelect>>", on_select_file)
library_tree.bind("<Double-1>", lambda e: (
    open_path(Path(library_tree.item(library_tree.selection()[0], "values")[3]))
    if library_tree.selection() else None
))

lib_actions = tk.Frame(tab_lib, bg=C["bg_card"])
lib_actions.pack(fill="x", padx=8, pady=(0,8))
ttk.Button(lib_actions, text="⎘ Copiar caminho", command=copy_selected_path).pack(side="left")
ttk.Button(lib_actions, text="↻ Atualizar lista", command=scan_library).pack(side="left", padx=6)


# ── RIGHT PANEL ───────────────────────────────
right = tk.Frame(body, bg=C["bg_card"], width=270,
                 highlightbackground=C["border"], highlightthickness=1)
right.pack(side="right", fill="y")
right.pack_propagate(False)

# capa
tk.Label(right, text="CAPA", font=FONT_LABEL, fg=C["cyan"], bg=C["bg_card"]).pack(anchor="w", padx=10, pady=(10,2))
thumb_canvas = tk.Canvas(right, width=160, height=160,
                          bg=C["bg_mid"], highlightthickness=1,
                          highlightbackground=C["border"])
thumb_canvas.pack(padx=10, pady=(0,8))
thumb_canvas.create_text(80, 80, text="sem capa", fill=C["text_dim"], font=FONT_SUB)

# metadados
tk.Label(right, text="METADADOS", font=FONT_LABEL, fg=C["cyan"], bg=C["bg_card"]).pack(anchor="w", padx=10, pady=(0,2))
details_text = tk.Text(right, height=9, wrap="word",
                        bg=C["bg_mid"], fg=C["text"],
                        insertbackground=C["text"],
                        relief="flat", padx=8, pady=8, font=FONT_SUB)
details_text.tag_configure("key", foreground=C["cyan"],   font=("Segoe UI", 8, "bold"))
details_text.tag_configure("val", foreground=C["text"],   font=("Courier New", 8))
details_text.pack(fill="x", padx=8, pady=(0,8))
details_text.configure(state="disabled")

# log
tk.Label(right, text="LOG", font=FONT_LABEL, fg=C["cyan"], bg=C["bg_card"]).pack(anchor="w", padx=10, pady=(0,2))
log_box = tk.Text(right, wrap="word",
                   bg=C["bg_mid"], fg=C["green"],
                   insertbackground=C["green"],
                   relief="flat", padx=8, pady=8, font=FONT_MONO)
log_box.pack(fill="both", expand=True, padx=8, pady=(0,8))
log_box.configure(state="disabled")

# ── BOTTOM BAR ────────────────────────────────
bottom = tk.Frame(main, bg=C["bg"])
bottom.pack(fill="x", pady=(6,0))
tk.Label(bottom,
         text="Enter para baixar  ·  duplo-clique para abrir  ·  MIT License  ·  " + GITHUB_URL,
         font=("Segoe UI", 8), fg=C["text_dim"], bg=C["bg"]).pack(side="left")
ttk.Button(bottom, text="✕ Sair", style="Danger.TButton",
           command=root.destroy).pack(side="right")

# ── keybinds & loops ──────────────────────────
root.bind("<Return>", lambda e: run_download())
root.after(100, poll_queue)
root.after(100, tick_equalizer)
root.after(500, auto_update)   # auto-update 500ms após abrir
scan_library()
root.mainloop()
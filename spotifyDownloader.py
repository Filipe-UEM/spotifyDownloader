"""
╔══════════════════════════════════════════════════════════════════╗
║  AERO MUSIC DOWNLOADER  v2.0                                     ║
║  Winamp × Y2K × Frutiger Aero                                    ║
║  Open Source – MIT License                                       ║
║  Producer: github.com/SEU_USUARIO                                ║
╚══════════════════════════════════════════════════════════════════╝

MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Dependencies (open source):
  - yt-dlp     (Unlicense)         https://github.com/yt-dlp/yt-dlp
  - spotDL     (MIT)               https://github.com/spotDL/spotify-downloader
  - ffmpeg     (LGPL/GPL)          https://ffmpeg.org
  - mutagen    (GPL-2.0)           https://github.com/quodlibet/mutagen
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
    from mutagen.id3 import ID3
    from mutagen.mp3 import MP3
except Exception:
    MutagenFile = None
    ID3 = None
    MP3 = None

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
APP_TITLE   = "AERO MUSIC DOWNLOADER"
APP_VERSION = "v2.0"
GITHUB_URL  = "https://github.com/SEU_USUARIO"  # ← altere para o seu GitHub
AUDIO_EXTS  = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac", ".webm"}

# ─────────────────────────────────────────────
#  PALETTE  — Frutiger Aero / Y2K / Winamp
# ─────────────────────────────────────────────
C = {
    # base
    "bg_dark":     "#0a0e1a",
    "bg_mid":      "#0d1428",
    "panel":       "#111827",
    "panel2":      "#192136",
    # glass
    "glass":       "#1a2744",
    "glass_hi":    "#2a3f6e",
    "glass_rim":   "#3d5a9a",
    # neon / aero accents
    "neon_cyan":   "#00e5ff",
    "neon_green":  "#39ff14",
    "neon_lime":   "#a8ff3e",
    "neon_pink":   "#ff2d78",
    "neon_blue":   "#1e90ff",
    "sky_blue":    "#87ceeb",
    "aero_white":  "#dff0ff",
    # text
    "text":        "#e8f4ff",
    "text_muted":  "#6b8cae",
    "text_dim":    "#3d5a7a",
    # winamp orange
    "win_orange":  "#ff8c00",
    "win_yellow":  "#ffe000",
    # status
    "ok":          "#39ff14",
    "warn":        "#ffe000",
    "err":         "#ff2d78",
}

EQ_COLORS = [
    "#00e5ff", "#1e90ff", "#1e90ff", "#3a6fff",
    "#39ff14", "#39ff14", "#a8ff3e",
    "#ffe000", "#ff8c00", "#ff2d78",
]

# ─────────────────────────────────────────────
#  STATE
# ─────────────────────────────────────────────
download_folder: Path = Path.home() / "Músicas"
ui_queue: "queue.Queue[tuple[str, str | None]]" = queue.Queue()
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
    """Sempre pergunta a pasta de destino antes de baixar."""
    global download_folder
    folder = filedialog.askdirectory(
        title="Escolha a pasta de destino",
        initialdir=str(download_folder),
    )
    if folder:
        download_folder = Path(folder)
        folder_var.set(str(download_folder))
        scan_library()


def build_command(link: str, mode: str, fmt: str, folder: Path) -> list[str]:
    """
    Monta o comando com as melhores flags de qualidade disponíveis.
    fmt: 'mp3_320' | 'flac' | 'best'
    """
    is_spotify = "spotify.com" in link
    is_youtube = "youtube.com" in link or "youtu.be" in link

    # ── SpotDL (Spotify) ──────────────────────────────────────────
    if mode == "spotify" or (mode == "auto" and is_spotify):
        audio_fmt = "mp3" if fmt == "mp3_320" else ("flac" if fmt == "flac" else "mp3")
        bitrate   = "320k" if fmt == "mp3_320" else "best"
        cmd = [
            "spotdl",
            "--audio", "youtube-music",      # fonte de áudio
            "--format", audio_fmt,
            "--bitrate", bitrate,
            "--output", str(folder),
            "--save-file", "spotdl_tracks.spotdl",
            link,
        ]
        return cmd

    # ── yt-dlp (YouTube / busca) ──────────────────────────────────
    if fmt == "flac":
        audio_fmt   = "flac"
        audio_quality = "0"          # lossless
    elif fmt == "mp3_320":
        audio_fmt   = "mp3"
        audio_quality = "0"          # highest VBR / CBR
    else:  # best (opus/m4a nativo)
        audio_fmt   = "best"
        audio_quality = "0"

    base_cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",   audio_fmt,
        "--audio-quality",  audio_quality,
        "--embed-metadata",
        "--embed-thumbnail",
        "--add-metadata",
        "--parse-metadata", "%(title)s:%(meta_title)s",
        "--parse-metadata", "%(uploader)s:%(meta_artist)s",
        "--write-thumbnail",
        "--convert-thumbnails", "jpg",
        "--postprocessor-args", "ffmpeg:-id3v2_version 3",
        "-P", str(folder),
    ]

    if mode == "youtube" or (mode == "auto" and is_youtube):
        return base_cmd + [link]

    # busca textual
    query = link if mode == "search" else f"ytsearch1:{link}"
    return base_cmd + [query]


# ══════════════════════════════════════════════
#  UI HELPERS
# ══════════════════════════════════════════════
def append_log(text: str):
    log_box.configure(state="normal")
    log_box.insert("end", text + "\n")
    log_box.see("end")
    log_box.configure(state="disabled")


def set_status(text: str, color: str = C["text_muted"]):
    status_var.set(text)
    status_lbl.configure(fg=color)


def set_busy(value: bool):
    global busy
    busy = value
    state = "disabled" if value else "normal"
    for w in (link_entry, download_btn, open_btn,
              refresh_btn, clear_btn, copy_btn,
              mode_auto, mode_spotify, mode_youtube, mode_search,
              fmt_mp3, fmt_flac, fmt_best):
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
            # smooth random movement
            if eq_tick % 4 == 0:
                phase    = (i / bars) * 2 * math.pi
                wave     = math.sin(phase + eq_tick * 0.25) * 18
                eq_target[i] = max(6, min(h - 10, int(20 + wave + (i % 3) * 5)))
            # lerp
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
        # bar body
        eq_canvas.create_rectangle(x0, y0, x1, y1, outline="", fill=col)
        # top reflection highlight
        eq_canvas.create_rectangle(x0, y0, x1, y0 + 2, outline="", fill="#ffffff44")
        # peak dot
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
        title="Escolha onde salvar o arquivo",
        initialdir=str(download_folder),
    )
    download_folder = Path(folder)
    folder_var.set(str(download_folder))
    download_folder.mkdir(parents=True, exist_ok=True)

    cmd = build_command(link, mode_var.get(), fmt_var.get(), download_folder)

    set_busy(True)
    set_status("Iniciando download...", C["neon_cyan"])
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
            assert proc.stdout is not None
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
                "yt-dlp ou spotdl não está instalado ou não está no PATH.\n\n"
                "Instale com:\n  pip install yt-dlp spotdl\n\n"
                "E certifique-se que o ffmpeg está no PATH.",
            )
        except Exception as exc:
            ui_queue.put(("status_err", "Erro durante o download."))
            ui_queue.put(("log", f"Erro inesperado: {exc}"))
            messagebox.showerror("Erro", str(exc))
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
                set_status(payload, C["neon_green"])
            elif kind == "status_err" and payload:
                set_status(payload, C["err"])
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
def get_metadata(path: Path) -> dict[str, str]:
    info: dict[str, str] = {
        "Arquivo": path.name,
        "Caminho": str(path),
        "Tamanho": f"{path.stat().st_size / (1024 * 1024):.2f} MB",
    }
    if MutagenFile is None:
        info["Metadados"] = "Instale mutagen: pip install mutagen"
        return info
    try:
        audio = MutagenFile(path)
        if audio is None:
            info["Metadados"] = "Não foi possível ler o arquivo."
            return info
        if getattr(audio, "tags", None):
            for key in ("title", "artist", "album", "date", "genre",
                        "tracknumber", "albumartist", "composer", "comment"):
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
                mins = int(length // 60)
                secs = int(length % 60)
                info["Duração"] = f"{mins:02d}:{secs:02d}"
            if bitrate:
                info["Bitrate"] = f"{int(bitrate / 1000)} kbps"
            if sample:
                info["Sample rate"] = f"{sample} Hz"
        if len(info) <= 3:
            info["Metadados"] = "Arquivo sem tags detectáveis."
    except Exception as exc:
        info["Metadados"] = f"Erro ao ler tags: {exc}"
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

    # thumbnail
    if PIL_AVAILABLE:
        thumb_canvas.delete("all")
        # look for .jpg next to the audio file
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            thumb_path = path.with_suffix(ext)
            if thumb_path.exists():
                try:
                    img = Image.open(thumb_path).resize((160, 160))
                    photo = ImageTk.PhotoImage(img)
                    thumb_canvas._photo = photo  # keep reference
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
    set_status(f"{count} arquivo(s) de áudio na pasta.", C["text_muted"])


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
        set_status("Caminho copiado.", C["neon_green"])


# ══════════════════════════════════════════════
#  CANVAS HELPERS (glass buttons)
# ══════════════════════════════════════════════
def rounded_rect(canvas, x1, y1, x2, y2, r=12, **kw):
    points = [
        x1+r, y1, x2-r, y1,
        x2, y1, x2, y1+r,
        x2, y2-r, x2, y2,
        x2-r, y2, x1+r, y2,
        x1, y2, x1, y2-r,
        x1, y1+r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kw)


# ══════════════════════════════════════════════
#  ROOT WINDOW
# ══════════════════════════════════════════════
root = tk.Tk()
root.title(f"{APP_TITLE}  {APP_VERSION}")
root.geometry("1100x740")
root.minsize(980, 680)
root.configure(bg=C["bg_dark"])

# ── custom font fallback ──
FONT_MONO  = ("Courier New", 9)
FONT_UI    = ("Segoe UI", 10)
FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_SUB   = ("Segoe UI", 9)
FONT_LABEL = ("Segoe UI", 9, "bold")

# ── ttk style ──
style = ttk.Style()
style.theme_use("clam")
style.configure(".",
    background=C["bg_dark"],
    foreground=C["text"],
    fieldbackground=C["panel2"],
    troughcolor=C["panel"],
    bordercolor=C["glass_rim"],
    selectbackground=C["glass_hi"],
    selectforeground=C["text"],
)
style.configure("TFrame",        background=C["bg_dark"])
style.configure("Glass.TFrame",  background=C["glass"],  relief="flat")
style.configure("TLabel",        background=C["bg_dark"], foreground=C["text"],       font=FONT_UI)
style.configure("Muted.TLabel",  background=C["bg_dark"], foreground=C["text_muted"], font=FONT_SUB)
style.configure("Glass.TLabel",  background=C["glass"],   foreground=C["text"],       font=FONT_UI)

style.configure("TEntry",
    fieldbackground=C["bg_mid"],
    foreground=C["neon_cyan"],
    insertcolor=C["neon_cyan"],
    borderwidth=2,
    relief="flat",
    font=("Segoe UI", 12),
)

style.configure("TButton",
    font=FONT_UI,
    padding=7,
    background=C["glass"],
    foreground=C["aero_white"],
    relief="flat",
    borderwidth=1,
)
style.map("TButton",
    background=[("active", C["glass_hi"]), ("disabled", C["panel"])],
    foreground=[("disabled", C["text_dim"])],
)

style.configure("Accent.TButton",
    font=("Segoe UI", 11, "bold"),
    padding=10,
    background=C["neon_cyan"],
    foreground=C["bg_dark"],
    relief="flat",
)
style.map("Accent.TButton",
    background=[("active", C["sky_blue"]), ("disabled", C["panel"])],
    foreground=[("disabled", C["text_dim"])],
)

style.configure("Danger.TButton",
    font=FONT_UI,
    padding=7,
    background="#3a0a18",
    foreground=C["neon_pink"],
    relief="flat",
)
style.map("Danger.TButton",
    background=[("active", "#55102a")],
)

style.configure("Treeview",
    background=C["bg_mid"],
    fieldbackground=C["bg_mid"],
    foreground=C["text"],
    rowheight=26,
    font=FONT_UI,
)
style.configure("Treeview.Heading",
    background=C["glass"],
    foreground=C["neon_cyan"],
    font=FONT_LABEL,
    relief="flat",
)
style.map("Treeview",
    background=[("selected", C["glass_hi"])],
    foreground=[("selected", C["neon_cyan"])],
)

style.configure("TRadiobutton",
    background=C["bg_dark"],
    foreground=C["text"],
    font=FONT_UI,
    indicatorcolor=C["neon_cyan"],
)
style.map("TRadiobutton",
    background=[("active", C["bg_dark"])],
    indicatorcolor=[("selected", C["neon_cyan"])],
)

style.configure("TProgressbar",
    troughcolor=C["panel"],
    background=C["neon_cyan"],
    thickness=4,
)

style.configure("TScrollbar",
    background=C["panel2"],
    troughcolor=C["panel"],
    arrowcolor=C["text_dim"],
    borderwidth=0,
)


# ══════════════════════════════════════════════
#  LAYOUT
# ══════════════════════════════════════════════

main = ttk.Frame(root, padding=10)
main.pack(fill="both", expand=True)

# ── HEADER ────────────────────────────────────
header = tk.Frame(main, bg=C["bg_dark"])
header.pack(fill="x", pady=(0, 8))

# title block with neon glow effect via layered labels
title_frame = tk.Frame(header, bg=C["bg_dark"])
title_frame.pack(side="left")

tk.Label(
    title_frame,
    text="◈ AERO MUSIC",
    font=("Segoe UI", 22, "bold"),
    fg=C["neon_cyan"],
    bg=C["bg_dark"],
).pack(anchor="w")

tk.Label(
    title_frame,
    text="DOWNLOADER  " + APP_VERSION,
    font=("Segoe UI", 10),
    fg=C["text_muted"],
    bg=C["bg_dark"],
).pack(anchor="w")

# github link
gh_btn = tk.Label(
    header,
    text="[ GitHub ]",
    font=("Segoe UI", 9, "underline"),
    fg=C["neon_blue"],
    bg=C["bg_dark"],
    cursor="hand2",
)
gh_btn.pack(side="right", padx=12)
gh_btn.bind("<Button-1>", lambda e: webbrowser.open(GITHUB_URL))

# status
status_var = tk.StringVar(value="Pronto.")
status_lbl = tk.Label(
    header,
    textvariable=status_var,
    font=FONT_SUB,
    fg=C["text_muted"],
    bg=C["bg_dark"],
)
status_lbl.pack(side="right", padx=8)

# progress bar
progress = ttk.Progressbar(main, mode="indeterminate", style="TProgressbar")
progress.pack(fill="x", pady=(0, 8))

# ── TOP AREA (input + eq) ─────────────────────
top = tk.Frame(main, bg=C["bg_dark"])
top.pack(fill="x", pady=(0, 8))

# input card
input_card = tk.Frame(top, bg=C["glass"], bd=0, relief="flat",
                       highlightbackground=C["glass_rim"], highlightthickness=1)
input_card.pack(side="left", fill="both", expand=True, padx=(0, 8), ipadx=12, ipady=10)

tk.Label(input_card, text="LINK / URL / BUSCA",
         font=FONT_LABEL, fg=C["neon_cyan"], bg=C["glass"]).pack(anchor="w", padx=12, pady=(10, 2))

link_var = tk.StringVar()
link_entry = tk.Entry(
    input_card,
    textvariable=link_var,
    font=("Courier New", 12),
    bg=C["bg_dark"],
    fg=C["neon_cyan"],
    insertbackground=C["neon_cyan"],
    relief="flat",
    bd=6,
    highlightthickness=1,
    highlightcolor=C["glass_rim"],
    highlightbackground=C["panel"],
)
link_entry.pack(fill="x", padx=12, pady=(0, 10))
link_entry.focus()

# mode + format row
row2 = tk.Frame(input_card, bg=C["glass"])
row2.pack(fill="x", padx=12, pady=(0, 10))

mode_var = tk.StringVar(value="auto")
tk.Label(row2, text="MODO:", font=FONT_LABEL, fg=C["text_muted"], bg=C["glass"]).pack(side="left")
mode_auto = ttk.Radiobutton(row2, text="Auto", variable=mode_var, value="auto")
mode_spotify = ttk.Radiobutton(row2, text="Spotify", variable=mode_var, value="spotify")
mode_youtube = ttk.Radiobutton(row2, text="YouTube", variable=mode_var, value="youtube")
mode_search = ttk.Radiobutton(row2, text="Busca", variable=mode_var, value="search")

for w in (mode_auto, mode_spotify, mode_youtube, mode_search):
    w.pack(side="left", padx=(6, 0))

row3 = tk.Frame(input_card, bg=C["glass"])
row3.pack(fill="x", padx=12, pady=(0, 10))

fmt_var = tk.StringVar(value="mp3_320")
tk.Label(row3, text="FORMATO:", font=FONT_LABEL, fg=C["text_muted"], bg=C["glass"]).pack(side="left")
fmt_mp3  = ttk.Radiobutton(row3, text="MP3 320kbps", variable=fmt_var, value="mp3_320")
fmt_flac = ttk.Radiobutton(row3, text="FLAC (lossless)", variable=fmt_var, value="flac")
fmt_best = ttk.Radiobutton(row3, text="Melhor nativo", variable=fmt_var, value="best")
for w in (fmt_mp3, fmt_flac, fmt_best):
    w.pack(side="left", padx=(6, 0))

# buttons
btn_row = tk.Frame(input_card, bg=C["glass"])
btn_row.pack(fill="x", padx=12, pady=(0, 10))

download_btn = ttk.Button(
    btn_row, text="⬇  BAIXAR",
    style="Accent.TButton",
    command=run_download,
)
download_btn.pack(side="left")

open_btn = ttk.Button(btn_row, text="📂 Abrir pasta",
                       command=lambda: open_path(download_folder))
open_btn.pack(side="left", padx=6)

refresh_btn = ttk.Button(btn_row, text="↻ Atualizar",
                          command=scan_library)
refresh_btn.pack(side="left")

clear_btn = ttk.Button(btn_row, text="✕ Limpar log",
                        style="Danger.TButton",
                        command=clear_log)
clear_btn.pack(side="right")

# eq + folder card
right_top = tk.Frame(top, bg=C["bg_dark"])
right_top.pack(side="right", fill="y")

# equalizer
eq_frame = tk.Frame(right_top, bg=C["glass"],
                    highlightbackground=C["glass_rim"], highlightthickness=1)
eq_frame.pack(fill="x", pady=(0, 6), ipadx=6, ipady=6)

tk.Label(eq_frame, text="EQUALIZER", font=FONT_LABEL,
         fg=C["neon_cyan"], bg=C["glass"]).pack(anchor="w", padx=8, pady=(6, 2))

eq_canvas = tk.Canvas(eq_frame, height=60, width=280, bg=C["bg_dark"],
                       highlightthickness=0)
eq_canvas.pack(padx=8, pady=(0, 8))

# folder card
folder_card = tk.Frame(right_top, bg=C["glass"],
                        highlightbackground=C["glass_rim"], highlightthickness=1)
folder_card.pack(fill="x", ipadx=6, ipady=6)

tk.Label(folder_card, text="PASTA DE DESTINO", font=FONT_LABEL,
         fg=C["neon_cyan"], bg=C["glass"]).pack(anchor="w", padx=8, pady=(6, 2))

folder_var = tk.StringVar(value=str(download_folder))
tk.Label(folder_card, textvariable=folder_var,
         font=("Segoe UI", 8), fg=C["text_muted"], bg=C["glass"],
         wraplength=270, justify="left").pack(anchor="w", padx=8, pady=(0, 6))

# ── MID AREA (library + details/log) ─────────
mid = tk.Frame(main, bg=C["bg_dark"])
mid.pack(fill="both", expand=True)

# library
lib_frame = tk.Frame(mid, bg=C["glass"],
                      highlightbackground=C["glass_rim"], highlightthickness=1)
lib_frame.pack(side="left", fill="both", expand=True, padx=(0, 8))

lib_header = tk.Frame(lib_frame, bg=C["glass"])
lib_header.pack(fill="x", padx=10, pady=(8, 4))

tk.Label(lib_header, text="BIBLIOTECA LOCAL", font=FONT_LABEL,
         fg=C["neon_cyan"], bg=C["glass"]).pack(side="left")
lib_count_var = tk.StringVar(value="0 arquivo(s)")
tk.Label(lib_header, textvariable=lib_count_var, font=FONT_SUB,
         fg=C["text_muted"], bg=C["glass"]).pack(side="right")

tree_wrap = tk.Frame(lib_frame, bg=C["glass"])
tree_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 6))

columns = ("nome", "tipo", "tamanho", "path")
library_tree = ttk.Treeview(tree_wrap, columns=columns,
                              show="headings", selectmode="browse")
for col, head, width in [
    ("nome",    "Nome",     300),
    ("tipo",    "Tipo",      60),
    ("tamanho", "Tamanho",   90),
    ("path",    "Caminho",  380),
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
    on_select_file(), open_path(Path(library_tree.item(library_tree.selection()[0], "values")[3]))
    if library_tree.selection() else None
))

lib_actions = tk.Frame(lib_frame, bg=C["glass"])
lib_actions.pack(fill="x", padx=8, pady=(0, 8))

copy_btn = ttk.Button(lib_actions, text="⎘ Copiar caminho", command=copy_selected_path)
copy_btn.pack(side="left")

# right panel
right_panel = tk.Frame(mid, bg=C["glass"], width=300,
                        highlightbackground=C["glass_rim"], highlightthickness=1)
right_panel.pack(side="right", fill="y")
right_panel.pack_propagate(False)

# thumbnail
tk.Label(right_panel, text="CAPA", font=FONT_LABEL,
         fg=C["neon_cyan"], bg=C["glass"]).pack(anchor="w", padx=10, pady=(8, 2))

thumb_canvas = tk.Canvas(right_panel, width=160, height=160,
                           bg=C["bg_dark"], highlightthickness=1,
                           highlightbackground=C["glass_rim"])
thumb_canvas.pack(padx=10, pady=(0, 8))
thumb_canvas.create_text(80, 80, text="sem capa",
                          fill=C["text_dim"], font=FONT_SUB)

# metadata
tk.Label(right_panel, text="METADADOS", font=FONT_LABEL,
         fg=C["neon_cyan"], bg=C["glass"]).pack(anchor="w", padx=10, pady=(0, 2))

details_text = tk.Text(
    right_panel,
    height=9,
    wrap="word",
    bg=C["bg_mid"],
    fg=C["text"],
    insertbackground=C["text"],
    relief="flat",
    padx=8,
    pady=8,
    font=FONT_SUB,
)
details_text.tag_configure("key", foreground=C["neon_cyan"],   font=("Segoe UI", 8, "bold"))
details_text.tag_configure("val", foreground=C["aero_white"],  font=("Courier New", 8))
details_text.pack(fill="x", padx=8, pady=(0, 8))
details_text.configure(state="disabled")

# log
tk.Label(right_panel, text="LOG", font=FONT_LABEL,
         fg=C["neon_cyan"], bg=C["glass"]).pack(anchor="w", padx=10, pady=(0, 2))

log_box = tk.Text(
    right_panel,
    wrap="word",
    bg=C["bg_dark"],
    fg=C["neon_green"],
    insertbackground=C["neon_green"],
    relief="flat",
    padx=8,
    pady=8,
    font=FONT_MONO,
)
log_box.pack(fill="both", expand=True, padx=8, pady=(0, 8))
log_box.configure(state="disabled")

# ── BOTTOM BAR ────────────────────────────────
bottom = tk.Frame(main, bg=C["bg_dark"])
bottom.pack(fill="x", pady=(6, 0))

tk.Label(
    bottom,
    text="Enter para baixar  ·  duplo-clique para abrir arquivo  ·  MIT License  ·  " + GITHUB_URL,
    font=("Segoe UI", 8),
    fg=C["text_dim"],
    bg=C["bg_dark"],
).pack(side="left")

ttk.Button(bottom, text="✕ Sair", style="Danger.TButton",
           command=root.destroy).pack(side="right")

# ── keybind ──
root.bind("<Return>", lambda e: run_download())

# ── start loops ──
root.after(100, poll_queue)
root.after(100, tick_equalizer)
scan_library()
root.mainloop()
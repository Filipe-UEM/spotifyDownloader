
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

APP_TITLE = "Retro Music Downloader"
AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".opus", ".aac", ".webm"}

download_folder = Path.cwd()
ui_queue: "queue.Queue[tuple[str, str | None]]" = queue.Queue()
busy = False
equalizer_tick = 0


def open_path(path: Path):
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        messagebox.showerror("Erro", f"Não foi possível abrir:\n{exc}")


def pick_folder():
    global download_folder
    folder = filedialog.askdirectory(initialdir=str(download_folder))
    if folder:
        download_folder = Path(folder)
        folder_var.set(str(download_folder))
        scan_library()


def build_command(link: str, mode: str, folder: Path) -> list[str]:
    is_spotify = "spotify.com" in link
    is_youtube = ("youtube.com" in link) or ("youtu.be" in link)

    if mode == "spotify" or (mode == "auto" and is_spotify):
        return ["spotdl", "--output", str(folder), link]

    if mode == "youtube" or (mode == "auto" and is_youtube):
        return [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--embed-metadata",
            "--embed-thumbnail",
            "-P", str(folder),
            link,
        ]

    query = link if mode == "search" else f"ytsearch1:{link}"
    return [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--embed-metadata",
        "--embed-thumbnail",
        "-P", str(folder),
        query,
    ]


def append_log(text: str):
    log_box.configure(state="normal")
    log_box.insert("end", text + "\n")
    log_box.see("end")
    log_box.configure(state="disabled")


def set_status(text: str):
    status_var.set(text)


def set_busy(value: bool):
    global busy
    busy = value
    download_btn.configure(state="disabled" if value else "normal")
    pick_btn.configure(state="disabled" if value else "normal")
    open_btn.configure(state="disabled" if value else "normal")
    refresh_btn.configure(state="disabled" if value else "normal")
    clear_btn.configure(state="disabled" if value else "normal")
    mode_auto.configure(state="disabled" if value else "normal")
    mode_spotify.configure(state="disabled" if value else "normal")
    mode_youtube.configure(state="disabled" if value else "normal")
    mode_search.configure(state="disabled" if value else "normal")
    link_entry.configure(state="disabled" if value else "normal")
    if value:
        progress.start(12)
    else:
        progress.stop()


def tick_equalizer():
    global equalizer_tick
    canvas.delete("all")
    w = max(canvas.winfo_width(), 260)
    h = max(canvas.winfo_height(), 72)
    bars = 10
    spacing = 6
    bar_w = (w - (bars + 1) * spacing) / bars
    base = h - 10

    if busy:
        equalizer_tick = (equalizer_tick + 1) % 20
        pattern = [8, 20, 34, 16, 40, 12, 28, 18, 36, 14]
        heights = [pattern[(i + equalizer_tick) % len(pattern)] for i in range(bars)]
    else:
        heights = [10] * bars

    for i in range(bars):
        x0 = spacing + i * (bar_w + spacing)
        x1 = x0 + bar_w
        y0 = base - min(heights[i], h - 20)
        y1 = base
        canvas.create_rectangle(x0, y0, x1, y1, outline="", fill=accent_color)

    root.after(120, tick_equalizer)


def poll_queue():
    try:
        while True:
            kind, payload = ui_queue.get_nowait()
            if kind == "log" and payload is not None:
                append_log(payload)
            elif kind == "status" and payload is not None:
                set_status(payload)
            elif kind == "done":
                set_busy(False)
                scan_library()
    except queue.Empty:
        pass
    root.after(120, poll_queue)


def run_download():
    link = link_var.get().strip()
    if not link:
        messagebox.showwarning("Aviso", "Cole um link ou uma busca primeiro.")
        return

    folder = download_folder
    folder.mkdir(parents=True, exist_ok=True)
    cmd = build_command(link, mode_var.get(), folder)

    set_busy(True)
    set_status("Preparando download...")
    append_log(f"> {' '.join(cmd)}")

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

            code = proc.wait()
            if code == 0:
                ui_queue.put(("status", "Download concluído."))
            else:
                ui_queue.put(("status", f"Finalizado com erro (código {code})."))
                ui_queue.put(("log", f"Processo retornou código {code}."))
        except FileNotFoundError as exc:
            ui_queue.put(("status", "Ferramenta não encontrada."))
            ui_queue.put(("log", f"Erro: {exc}"))
            messagebox.showerror(
                "Erro",
                "yt-dlp ou spotdl não foi encontrado no sistema.\n"
                "Instale a ferramenta e deixe no PATH."
            )
        except Exception as exc:
            ui_queue.put(("status", "Erro durante o download."))
            ui_queue.put(("log", f"Erro: {exc}"))
            messagebox.showerror("Erro", str(exc))
        finally:
            ui_queue.put(("done", None))

    threading.Thread(target=worker, daemon=True).start()


def get_metadata(path: Path) -> dict[str, str]:
    info: dict[str, str] = {
        "Arquivo": path.name,
        "Caminho": str(path),
        "Tamanho": f"{path.stat().st_size / (1024 * 1024):.2f} MB",
    }

    if MutagenFile is None:
        info["Metadados"] = "Instale mutagen para ler tags."
        return info

    try:
        audio = MutagenFile(path)
        if audio is None:
            info["Metadados"] = "Não foi possível ler o arquivo."
            return info

        if getattr(audio, "tags", None):
            for key in ("title", "artist", "album", "genre", "date", "tracknumber"):
                try:
                    value = audio.tags.get(key)
                    if value:
                        info[key.capitalize()] = str(value[0]) if isinstance(value, list) else str(value)
                except Exception:
                    pass

        try:
            if hasattr(audio, "info") and audio.info is not None:
                length = getattr(audio.info, "length", None)
                bitrate = getattr(audio.info, "bitrate", None)
                if length:
                    mins = int(length // 60)
                    secs = int(length % 60)
                    info["Duração"] = f"{mins:02d}:{secs:02d}"
                if bitrate:
                    info["Bitrate"] = f"{int(bitrate / 1000)} kbps"
        except Exception:
            pass

        if len(info) <= 3:
            info["Metadados"] = "Arquivo sem tags detectáveis."
    except Exception as exc:
        info["Metadados"] = f"Erro ao ler tags: {exc}"

    return info


def clear_details():
    details_text.configure(state="normal")
    details_text.delete("1.0", "end")
    details_text.configure(state="disabled")


def show_metadata(path_str: str):
    path = Path(path_str)
    if not path.exists():
        return
    meta = get_metadata(path)
    clear_details()
    details_text.configure(state="normal")
    for k, v in meta.items():
        details_text.insert("end", f"{k}: {v}\n")
    details_text.configure(state="disabled")


def scan_library():
    library_tree.delete(*library_tree.get_children())
    if not download_folder.exists():
        return

    files = [p for p in download_folder.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO_EXTS]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for p in files:
        size_mb = p.stat().st_size / (1024 * 1024)
        library_tree.insert("", "end", values=(p.name, p.suffix.upper().lstrip("."), f"{size_mb:.2f} MB", str(p)))

    set_status(f"{len(files)} arquivo(s) de áudio encontrado(s).")


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
        set_status("Caminho copiado para a área de transferência.")


# -------- UI --------
bg = "#17181b"
panel = "#22252a"
panel2 = "#2b2f36"
text = "#e9edf2"
muted = "#aab2bd"
accent_color = "#43d17a"

root = tk.Tk()
root.title(APP_TITLE)
root.geometry("1080x720")
root.minsize(980, 640)
root.configure(bg=bg)

style = ttk.Style()
style.theme_use("clam")
style.configure(".", background=bg, foreground=text, fieldbackground=panel2)
style.configure("TFrame", background=bg)
style.configure("Card.TFrame", background=panel, relief="flat")
style.configure("Header.TLabel", background=bg, foreground=text, font=("Segoe UI", 18, "bold"))
style.configure("Sub.TLabel", background=bg, foreground=muted, font=("Segoe UI", 10))
style.configure("Card.TLabel", background=panel, foreground=text, font=("Segoe UI", 10))
style.configure("TLabel", background=bg, foreground=text, font=("Segoe UI", 10))
style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=8)
style.map("TButton", background=[("active", "#323844")])
style.configure("Accent.TButton", background=accent_color, foreground="#101010")
style.map("Accent.TButton", background=[("active", "#65e08d")])
style.configure("TEntry", fieldbackground=panel2, foreground=text, insertcolor=text)
style.configure("Treeview", background=panel2, fieldbackground=panel2, foreground=text, rowheight=28)
style.configure("Treeview.Heading", background=panel, foreground=text, font=("Segoe UI", 10, "bold"))
style.map("Treeview", background=[("selected", "#3c4452")])

main = ttk.Frame(root, padding=14)
main.pack(fill="both", expand=True)

header = ttk.Frame(main)
header.pack(fill="x", pady=(0, 10))

title_wrap = ttk.Frame(header)
title_wrap.pack(side="left", fill="x", expand=True)

ttk.Label(title_wrap, text="Retro Music Downloader", style="Header.TLabel").pack(anchor="w")
ttk.Label(
    title_wrap,
    text="Baixe músicas, veja sua biblioteca local e consulte metadados sem sair da interface.",
    style="Sub.TLabel"
).pack(anchor="w", pady=(3, 0))

status_var = tk.StringVar(value="Pronto.")
ttk.Label(header, textvariable=status_var, style="Sub.TLabel").pack(side="right", padx=8, pady=8)

controls = ttk.Frame(main)
controls.pack(fill="x", pady=(0, 10))

input_card = ttk.Frame(controls, style="Card.TFrame", padding=12)
input_card.pack(side="left", fill="both", expand=True, padx=(0, 10))

ttk.Label(input_card, text="Link, busca ou playlist").pack(anchor="w")
link_var = tk.StringVar()
link_entry = ttk.Entry(input_card, textvariable=link_var, font=("Segoe UI", 11))
link_entry.pack(fill="x", pady=(6, 10))
link_entry.focus()

mode_var = tk.StringVar(value="auto")
mode_frame = ttk.Frame(input_card)
mode_frame.pack(fill="x", pady=(0, 10))

mode_auto = ttk.Radiobutton(mode_frame, text="Auto", variable=mode_var, value="auto")
mode_spotify = ttk.Radiobutton(mode_frame, text="Spotify", variable=mode_var, value="spotify")
mode_youtube = ttk.Radiobutton(mode_frame, text="YouTube", variable=mode_var, value="youtube")
mode_search = ttk.Radiobutton(mode_frame, text="Busca", variable=mode_var, value="search")
for widget in (mode_auto, mode_spotify, mode_youtube, mode_search):
    widget.pack(side="left", padx=(0, 12))

buttons = ttk.Frame(input_card)
buttons.pack(fill="x")

download_btn = ttk.Button(buttons, text="Baixar", style="Accent.TButton", command=run_download)
download_btn.pack(side="left")

pick_btn = ttk.Button(buttons, text="Escolher pasta", command=pick_folder)
pick_btn.pack(side="left", padx=8)

open_btn = ttk.Button(buttons, text="Abrir pasta", command=lambda: open_path(download_folder))
open_btn.pack(side="left")

refresh_btn = ttk.Button(buttons, text="Atualizar biblioteca", command=scan_library)
refresh_btn.pack(side="left", padx=8)

folder_card = ttk.Frame(controls, style="Card.TFrame", padding=12, width=320)
folder_card.pack(side="right", fill="y")
folder_card.pack_propagate(False)

ttk.Label(folder_card, text="Destino").pack(anchor="w")
folder_var = tk.StringVar(value=str(download_folder))
ttk.Label(folder_card, textvariable=folder_var, wraplength=300, style="Card.TLabel").pack(anchor="w", pady=(6, 8))

canvas = tk.Canvas(folder_card, height=72, bg=panel, highlightthickness=0)
canvas.pack(fill="x", pady=(4, 0))

mid = ttk.Frame(main)
mid.pack(fill="both", expand=True)

left = ttk.Frame(mid, style="Card.TFrame", padding=12)
left.pack(side="left", fill="both", expand=True, padx=(0, 10))

right = ttk.Frame(mid, style="Card.TFrame", padding=12, width=340)
right.pack(side="right", fill="y")
right.pack_propagate(False)

ttk.Label(left, text="Biblioteca local").pack(anchor="w")

tree_frame = ttk.Frame(left)
tree_frame.pack(fill="both", expand=True, pady=(8, 0))

columns = ("nome", "tipo", "tamanho", "path")
library_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
for col, text_col, width in [
    ("nome", "Nome", 320),
    ("tipo", "Tipo", 70),
    ("tamanho", "Tamanho", 90),
    ("path", "Caminho", 420),
]:
    library_tree.heading(col, text=text_col)
    library_tree.column(col, width=width, anchor="w")

ys = ttk.Scrollbar(tree_frame, orient="vertical", command=library_tree.yview)
xs = ttk.Scrollbar(tree_frame, orient="horizontal", command=library_tree.xview)
library_tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)

library_tree.grid(row=0, column=0, sticky="nsew")
ys.grid(row=0, column=1, sticky="ns")
xs.grid(row=1, column=0, sticky="ew")
tree_frame.rowconfigure(0, weight=1)
tree_frame.columnconfigure(0, weight=1)

library_tree.bind("<<TreeviewSelect>>", on_select_file)
library_tree.bind("<Double-1>", on_select_file)

lib_actions = ttk.Frame(left)
lib_actions.pack(fill="x", pady=(10, 0))

copy_btn = ttk.Button(lib_actions, text="Copiar caminho", command=copy_selected_path)
copy_btn.pack(side="left")

clear_btn = ttk.Button(lib_actions, text="Limpar log", command=clear_log)
clear_btn.pack(side="left", padx=8)

ttk.Label(right, text="Metadados").pack(anchor="w")
details_text = tk.Text(
    right,
    height=12,
    wrap="word",
    bg=panel2,
    fg=text,
    insertbackground=text,
    relief="flat",
    padx=10,
    pady=10,
)
details_text.pack(fill="x", pady=(8, 10))
details_text.configure(state="disabled")

ttk.Label(right, text="Log").pack(anchor="w")
log_box = tk.Text(
    right,
    height=14,
    wrap="word",
    bg=panel2,
    fg=text,
    insertbackground=text,
    relief="flat",
    padx=10,
    pady=10,
)
log_box.pack(fill="both", expand=True, pady=(8, 0))
log_box.configure(state="disabled")

bottom = ttk.Frame(main)
bottom.pack(fill="x", pady=(10, 0))

progress = ttk.Progressbar(bottom, mode="indeterminate")
progress.pack(side="left", fill="x", expand=True, padx=(0, 10))

ttk.Label(bottom, text="Enter para baixar", style="Sub.TLabel").pack(side="left")
ttk.Button(bottom, text="Sair", command=root.destroy).pack(side="right")

root.bind("<Return>", lambda e: run_download())
root.after(120, poll_queue)
root.after(120, tick_equalizer)
scan_library()
root.mainloop()

"""Ventana de control minima -- Fase 7 del roadmap (docs/roadmap.md).

Punto de entrada del .exe empaquetado (ver pivot_x_sentinel.spec). Arranca la
API+panel (mismo proceso que ya define api/app.py -- uvicorn sirviendo
api.app:app) en un thread de background y muestra una ventana con:

  - Abrir panel   -> abre http://127.0.0.1:PORT/panel/ en el navegador
                     default. El panel es el que arranca/para el bot en si
                     (Configuracion -> Guardar y arrancar) -- esta ventana
                     solo controla el PROCESO (servidor arriba/abajo), no la
                     estrategia.
  - Ver logs      -> muestra/oculta un panel de texto con todo lo que el
                     proceso va imprimiendo (stdout/stderr, incluido el
                     access log de uvicorn) -- util si el panel web no carga
                     y hay que ver por que.
  - Cerrar todo   -> para el bot si esta corriendo (POST /stop, best-effort),
                     apaga el servidor, y cierra la ventana. Cerrar la "X" de
                     la ventana hace lo mismo (no deja el proceso huerfano
                     corriendo en background sin que se vea).

No hace falta consola aparte (windowed build) -- todo el output que antes iba
a la consola de run.bat ahora se redirige a este mismo panel de texto Y a un
archivo de log en disco (util para post-mortem si la ventana se cerro sola).
"""
from __future__ import annotations

import sys

# console=False (ver pivot_x_sentinel.spec) deja sys.stdout/stderr en None --
# cualquier print() (de este script o de una libreria que ya importemos, p.ej.
# uvicorn al arrancar) explota con AttributeError antes de que lleguemos a
# redirigirlos nosotros mismos mas abajo. Placeholder inofensivo hasta que
# _install_log_redirection() los reemplace por los de verdad.
if sys.stdout is None:
    sys.stdout = open("nul" if sys.platform == "win32" else "/dev/null", "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = sys.stdout

import asyncio
import json
import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import messagebox
from urllib.request import urlopen, Request
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root -- no-op cuando esto corre empaquetado
from execution.src.version import get_version  # noqa: E402

HOST = "127.0.0.1"
PORT = 8000
PANEL_URL = f"http://{HOST}:{PORT}/panel/"
STATUS_URL = f"http://{HOST}:{PORT}/status"
STOP_URL = f"http://{HOST}:{PORT}/stop"

_LOG_QUEUE: "queue.Queue[str]" = queue.Queue()


def _log_dir() -> Path:
    # %LOCALAPPDATA% siempre existe y es escribible sin admin en Windows --
    # mismo criterio que la instalacion (ver packaging/installer.iss:
    # DefaultDirName={localappdata}\pivot-x-sentinel).
    base = os.environ.get("LOCALAPPDATA")
    d = Path(base) / "pivot-x-sentinel" / "logs" if base else Path(__file__).resolve().parent / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


class _TeeStream:
    """Duplica cada write() al stream original (si hay uno real), a un
    archivo de log en disco, y a la cola que alimenta el panel de texto de la
    ventana -- asi "Ver logs" siempre tiene TODO lo que se imprimio desde que
    arranco el proceso, no solo lo que paso mientras el panel estaba abierto."""

    def __init__(self, original, logfile):
        self._original = original
        self._logfile = logfile

    def write(self, data):
        if data:
            _LOG_QUEUE.put(data)
            try:
                self._logfile.write(data)
                self._logfile.flush()
            except Exception:
                pass
        return len(data)

    def flush(self):
        try:
            self._logfile.flush()
        except Exception:
            pass

    def isatty(self):
        # uvicorn.logging.ColourizedFormatter llama sys.stdout.isatty() para
        # decidir si usa colores ANSI -- sin este metodo, logging.config.
        # dictConfig() explota con AttributeError envuelto en
        # "ValueError('Unable to configure formatter default')" apenas
        # arranca uvicorn (visto empaquetado con console=False, donde
        # sys.stdout no es una consola real). False = sin colores, que de
        # cualquier forma no se ven en el Text widget de Tk.
        return False


def _install_log_redirection():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = _log_dir() / f"bot_{ts}.log"
    f = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _TeeStream(sys.stdout, f)
    sys.stderr = _TeeStream(sys.stderr, f)
    print(f"[control] log de esta sesion: {path}")
    return path


class ServerThread(threading.Thread):
    """Corre uvicorn (api.app:app) en su propio loop de asyncio, en un thread
    de background -- la ventana Tk necesita el thread principal para su
    propio mainloop, no puede compartirlo con el de asyncio."""

    def __init__(self):
        super().__init__(daemon=True, name="pxs-server")
        self.server = None
        self._ready = threading.Event()
        self._error = None

    def run(self):
        try:
            import uvicorn
            from api.app import app
            config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info")
            self.server = uvicorn.Server(config)
            self._ready.set()
            asyncio.run(self.server.serve())
        except Exception as e:  # noqa: BLE001 -- se lo mostramos al usuario, no lo tragamos
            import traceback
            traceback.print_exc()  # queda en el log en disco aunque el messagebox se cierre sin leerlo
            self._error = e
            self._ready.set()
        print("[control] servidor detenido.")

    def wait_ready(self, timeout=10.0) -> Exception | None:
        self._ready.wait(timeout)
        return self._error

    def request_stop(self):
        if self.server is not None:
            self.server.should_exit = True


def _http_get(url, timeout=2.0):
    with urlopen(Request(url), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _http_post_stop(timeout=5.0):
    try:
        with urlopen(Request(STOP_URL, method="POST", data=b""), timeout=timeout):
            pass
    except URLError:
        pass  # bot no estaba corriendo, o el server ya no responde -- no es fatal aca


class ControlWindow:
    def __init__(self, root: tk.Tk, server: ServerThread):
        self.root = root
        self.server = server
        self._closing = False

        root.title(f"pivot-x-sentinel v{get_version()} -- control")
        root.geometry("560x360")
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        top = tk.Frame(root, padx=12, pady=12)
        top.pack(fill="x")

        self.status_var = tk.StringVar(value="Arrancando...")
        tk.Label(top, textvariable=self.status_var, font=("Segoe UI", 10, "bold"),
                 anchor="w", justify="left").pack(fill="x")

        btns = tk.Frame(root, padx=12)
        btns.pack(fill="x")
        tk.Button(btns, text="Abrir panel", width=16, command=self.open_panel).pack(side="left", padx=(0, 8), pady=4)
        self.logs_btn = tk.Button(btns, text="Ver logs", width=16, command=self.toggle_logs)
        self.logs_btn.pack(side="left", padx=8, pady=4)
        tk.Button(btns, text="Cerrar todo", width=16, command=self.on_close).pack(side="left", padx=8, pady=4)

        self.log_frame = tk.Frame(root)
        self.log_text = tk.Text(self.log_frame, bg="#111", fg="#ddd", insertbackground="#ddd",
                                 font=("Consolas", 9), state="disabled", wrap="word")
        scroll = tk.Scrollbar(self.log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._logs_visible = False  # arranca oculto -- ver toggle_logs()
        self.toggle_logs()  # lo muestra la primera vez para que se note que existe

        self.root.after(200, self._drain_log_queue)
        self.root.after(500, self._poll_status)

    # -- acciones de los botones --------------------------------------------

    def open_panel(self):
        webbrowser.open(PANEL_URL)

    def toggle_logs(self):
        self._logs_visible = not self._logs_visible
        if self._logs_visible:
            self.log_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            self.logs_btn.config(text="Ocultar logs")
        else:
            self.log_frame.pack_forget()
            self.logs_btn.config(text="Ver logs")

    def on_close(self):
        if self._closing:
            return
        try:
            status = _http_get(STATUS_URL, timeout=1.5)
        except Exception:
            status = None

        if status and status.get("running"):
            if not messagebox.askyesno(
                "Cerrar pivot-x-sentinel",
                "El bot esta corriendo ahora mismo.\n\n"
                "Cerrar esta ventana lo detiene (deja de vigilar/gestionar ordenes desde este "
                "proceso). Las ordenes/posiciones YA abiertas en tu cuenta MT5 NO se cancelan ni "
                "se cierran solas -- siguen ahi hasta que las gestiones desde el terminal.\n\n"
                "¿Cerrar de todas formas?",
            ):
                return
        self._closing = True
        self.status_var.set("Cerrando...")
        threading.Thread(target=self._shutdown_sequence, daemon=True).start()

    def _shutdown_sequence(self):
        _http_post_stop(timeout=5.0)
        self.server.request_stop()
        self.server.join(timeout=8.0)
        # os._exit en vez de sys.exit: garantiza que el proceso termina aunque
        # el loop de asyncio o algun thread no-daemon se haya quedado colgado
        # -- este es el ultimo paso antes de cerrar, no hay estado que perder.
        os._exit(0)

    # -- refresco periodico ---------------------------------------------------

    def _drain_log_queue(self):
        drained = False
        while True:
            try:
                chunk = _LOG_QUEUE.get_nowait()
            except queue.Empty:
                break
            self.log_text.configure(state="normal")
            self.log_text.insert("end", chunk)
            self.log_text.configure(state="disabled")
            drained = True
        if drained:
            self.log_text.see("end")
        if not self._closing:
            self.root.after(200, self._drain_log_queue)

    def _poll_status(self):
        if self._closing:
            return
        try:
            status = _http_get(STATUS_URL, timeout=1.5)
        except Exception:
            self.status_var.set("Servidor arrancando o no responde todavia...")
        else:
            if status.get("running"):
                self.status_var.set(
                    f"Corriendo -- symbol={status.get('symbol')} perfil={status.get('profile')} "
                    f"magic={status.get('magic')} {'DRY-RUN' if status.get('dry_run') else 'EN VIVO'}"
                )
            else:
                self.status_var.set(
                    f"Servidor arriba en {PANEL_URL} -- bot detenido "
                    "(arrancalo desde el panel, pestaña Configuracion)."
                )
        self.root.after(3000, self._poll_status)


def main():
    _install_log_redirection()
    print(f"pivot-x-sentinel version: {get_version()}")  # primera linea util para diagnostico si alguien manda un log
    print("[control] arrancando servidor...")

    server = ServerThread()
    server.start()
    err = server.wait_ready(timeout=15.0)
    if err is not None:
        # tk.Tk() recien aca -- si fallo antes de tener ventana, un messagebox
        # sin root todavia funciona igual (crea uno implicito).
        messagebox.showerror("pivot-x-sentinel", f"No se pudo arrancar el servidor:\n\n{err!r}")
        return

    root = tk.Tk()
    ControlWindow(root, server)
    root.mainloop()


if __name__ == "__main__":
    main()

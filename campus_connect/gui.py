"""Bilingual desktop UI. Workers never access Tk widgets or log credentials."""

import argparse
import datetime
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .client import SrunClient, SrunError, check_connectivity
from .config import CampusProfile, ConfigStore, ProfileError, Settings, export_profile, load_profile
from .i18n import Translator
from .monitor import run_monitor


LABELS = {
    "name": "Campus name", "base_url": "Server base URL", "ac_id": "ac_id", "username_suffix": "Account suffix",
    "challenge_path": "Challenge API path", "portal_path": "Sign-in/out API path", "n": "Protocol n", "type": "Protocol type",
    "enc_ver": "Encoding version", "base64_alphabet": "Base64 alphabet", "client_ip": "Client IPv4 (optional)",
    "probe_url": "Connectivity test URL", "probe_status": "Expected HTTP status", "probe_text": "Expected response text",
}
LANGUAGES = {"English": "en", "简体中文": "zh-CN"}


def application_directory():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


def resource_directory():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


class Application(tk.Tk):
    def __init__(self, store=None, language=None):
        super().__init__()
        self.store = store or ConfigStore(application_directory())
        self.initial_error = None
        try:
            self.settings = self.store.load()
        except ProfileError as error:
            self.settings = Settings()
            self.initial_error = str(error)
        self.tr = Translator(language or self.settings.language)
        self.messages = queue.Queue()
        self.auth_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.running = False
        self.busy = False
        self.state_key = "Idle"
        self.bindings = []
        self.profile_vars = {}
        self.geometry("900x760")
        self.minsize(780, 640)
        self.option_add("*Font", ("Segoe UI", 10))
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self._build()
        self._fill(self.settings)
        self._render()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.poll_id = self.after(100, self._drain)
        if self.initial_error:
            self.messages.put(("error", self.initial_error, {}))

    def label(self, parent, key, **options):
        widget = ttk.Label(parent, **options)
        self.bindings.append((widget, key))
        return widget

    def button(self, parent, key, command):
        widget = ttk.Button(parent, command=command)
        self.bindings.append((widget, key))
        return widget

    def _scroll_frame(self, parent):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        inner = ttk.Frame(canvas, padding=16)
        item = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        return inner

    def _build(self):
        header = ttk.Frame(self, padding=16)
        header.pack(fill="x")
        self.title_label = self.label(header, "SRUN Campus Connect", font=("Segoe UI", 17, "bold"))
        self.title_label.pack(side="left")
        self.language_var = tk.StringVar()
        picker = ttk.Combobox(header, values=tuple(LANGUAGES), textvariable=self.language_var, state="readonly", width=12)
        picker.pack(side="right")
        picker.bind("<<ComboboxSelected>>", self._change_language)
        self.label(header, "Language").pack(side="right", padx=10)
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.tabs = []
        for name in ("Monitor", "Connection", "Advanced"):
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame)
            self.tabs.append((frame, name))
        monitor = ttk.Frame(self.tabs[0][0], padding=16)
        monitor.pack(fill="both", expand=True)
        self.label(monitor, "First open Connection, enter your campus server settings, then save and start monitoring.", wraplength=760).pack(anchor="w", pady=(0, 12))
        self.status_var = tk.StringVar()
        ttk.Label(monitor, textvariable=self.status_var, font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(0, 12))
        bar = ttk.Frame(monitor)
        bar.pack(fill="x", pady=(0, 10))
        self.start_button = self.button(bar, "Start monitoring", self._start)
        self.start_button.pack(side="left", padx=(0, 6))
        self.stop_button = self.button(bar, "Stop monitoring", self._stop)
        self.stop_button.pack(side="left", padx=(0, 6))
        self.operation_buttons = []
        for name, operation in (("Check now", "check"), ("Sign in", "login"), ("Sign out", "logout")):
            button = self.button(bar, name, lambda op=operation: self._operation(op))
            button.pack(side="left", padx=(0, 6))
            self.operation_buttons.append(button)
        log_frame = ttk.Frame(monitor)
        log_frame.pack(fill="both", expand=True)
        scrollbar = ttk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")
        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", font=("Consolas", 10), yscrollcommand=scrollbar.set)
        self.log_text.pack(fill="both", expand=True)
        scrollbar.configure(command=self.log_text.yview)
        self.log_text.tag_configure("error", foreground="#b91c1c")

        connection = self._scroll_frame(self.tabs[1][0])
        self.label(connection, "Set your school's server and ac_id. Importable profiles contain no account or password.", wraplength=700).pack(anchor="w", pady=(0, 12))
        profile_bar = ttk.Frame(connection)
        profile_bar.pack(fill="x", pady=(0, 12))
        self.button(profile_bar, "Import profile", self._import_profile).pack(side="left", padx=(0, 8))
        self.button(profile_bar, "Export profile", self._export_profile).pack(side="left")
        for key in ("name", "base_url", "ac_id", "username_suffix"):
            self.profile_vars[key] = self._entry(connection, LABELS[key])
        self.username_var = self._entry(connection, "Campus account")
        self.password_var = self._entry(connection, "Password", password=True)
        self.show_password = tk.BooleanVar(value=False)
        show = ttk.Checkbutton(connection, variable=self.show_password, command=lambda: self.password_entry.configure(show="" if self.show_password.get() else "●"))
        self.bindings.append((show, "Show password"))
        show.pack(anchor="w", pady=(0, 8))
        self.label(connection, "Credentials stay in settings.json on this device in plain text. Do not share that file.", wraplength=700).pack(anchor="w", pady=(0, 12))
        self.interval_var = self._entry(connection, "Check interval (seconds)")
        self.retries_var = self._entry(connection, "Sign-in attempts")
        self.delay_var = self._entry(connection, "Retry delay (seconds)")
        self.auto_var = tk.BooleanVar(value=True)
        auto = ttk.Checkbutton(connection, variable=self.auto_var)
        self.bindings.append((auto, "Automatic sign-in after repeated failures"))
        auto.pack(anchor="w", pady=8)
        self.button(connection, "Save settings", self._save).pack(anchor="w", pady=12)
        advanced = self._scroll_frame(self.tabs[2][0])
        self.label(advanced, "These settings vary by campus. Defaults target the standard SRUN BX1 API, not every SRUN deployment.", wraplength=700).pack(anchor="w", pady=(0, 12))
        for key in LABELS:
            if key not in self.profile_vars:
                self.profile_vars[key] = self._entry(advanced, LABELS[key])
        self.button(advanced, "Save settings", self._save).pack(anchor="w", pady=12)

    def _entry(self, parent, key, password=False):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=5)
        self.label(row, key, width=28).pack(side="left")
        variable = tk.StringVar()
        entry = ttk.Entry(row, textvariable=variable, show="●" if password else "")
        entry.pack(side="left", fill="x", expand=True)
        if password:
            self.password_entry = entry
        return variable

    def _fill(self, settings, profile_only=False):
        for key, value in settings.profile.to_dict().items():
            self.profile_vars[key].set(str(value))
        if not profile_only:
            self.username_var.set(settings.username)
            self.password_var.set(settings.password)
            self.interval_var.set(str(settings.check_interval))
            self.retries_var.set(str(settings.reconnect_retries))
            self.delay_var.set(str(settings.retry_delay))
            self.auto_var.set(settings.auto_login)
            self.language_var.set(next(label for label, language in LANGUAGES.items() if language == self.tr.language))

    def _render(self):
        if getattr(self, "_rendered_language", None) != self.tr.language:
            font = "Microsoft YaHei UI" if self.tr.language == "zh-CN" else "Segoe UI"
            for style in ("TLabel", "TButton", "TEntry", "TCheckbutton", "TCombobox", "TNotebook.Tab"):
                self.style.configure(style, font=(font, 10))
            self.style.configure("TButton", padding=(8, 5))
            self.title_label.configure(font=(font, 17, "bold"))
            self._rendered_language = self.tr.language
        self.title(self.tr("SRUN Campus Connect") + " " + __version__)
        for widget, key in self.bindings:
            widget.configure(text=self.tr(key))
        for frame, key in self.tabs:
            self.notebook.tab(frame, text=self.tr(key))
        self.status_var.set(self.tr("Status") + ": " + self.tr(self.state_key))
        self.start_button.configure(state="disabled" if self.running else "normal")
        self.stop_button.configure(state="normal" if self.running else "disabled")
        for button in self.operation_buttons:
            button.configure(state="disabled" if self.busy else "normal")

    def _change_language(self, event=None):
        self.tr.language = LANGUAGES[self.language_var.get()]
        self.settings.language = self.tr.language
        self._render()
        if not self.initial_error:
            try:
                self.store.save(self.settings)
            except OSError:
                self._log("Could not save settings. Check folder permissions.", {}, "error")

    def _collect(self):
        profile = CampusProfile.from_dict({key: value.get().strip() for key, value in self.profile_vars.items()}).validate()
        return Settings.from_dict({"profile": profile.to_dict(), "username": self.username_var.get().strip(), "password": self.password_var.get(),
                                   "language": self.tr.language, "check_interval": self.interval_var.get(), "reconnect_retries": self.retries_var.get(),
                                   "retry_delay": self.delay_var.get(), "auto_login": self.auto_var.get()})

    def _error(self, key):
        messagebox.showerror(self.tr("Error"), self.tr(key), parent=self)

    def _save(self, notify=True):
        try:
            settings = self._collect()
            self.store.save(settings)
            self.settings = settings
            self.initial_error = None
            self._fill(settings)
            self._log("Settings saved.", {})
            if notify:
                messagebox.showinfo(self.tr("Information"), self.tr("Settings saved."), parent=self)
            if self.running:
                self._log("Restart monitoring to apply connection changes.", {})
            return settings
        except ProfileError as error:
            self._error(str(error))
        except OSError:
            self._error("Could not save settings. Check folder permissions.")
        return None

    def _import_profile(self):
        path = filedialog.askopenfilename(parent=self, initialdir=str(resource_directory() / "profiles"), filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            profile = load_profile(path)
            self._fill(Settings(profile=profile), profile_only=True)
            self._log("Profile imported. Enter your own account before signing in.", {})
            messagebox.showinfo(self.tr("Information"), self.tr("Profile imported. Enter your own account before signing in."), parent=self)
        except ProfileError as error:
            self._error(str(error))

    def _export_profile(self):
        try:
            profile = self._collect().profile
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".json", initialfile="campus-profile.json", filetypes=[("JSON", "*.json")])
            if path:
                export_profile(path, profile)
                self._log("Profile exported without credentials.", {})
                messagebox.showinfo(self.tr("Information"), self.tr("Profile exported without credentials."), parent=self)
        except ProfileError as error:
            self._error(str(error))
        except OSError:
            self._error("Could not export the campus profile.")

    def _emit(self, event, key, values):
        self.messages.put((event, key, values))

    def _operation(self, operation):
        try:
            settings = self._collect()
            if operation != "check" and (not settings.username or not settings.password):
                raise SrunError("Enter your campus account and password first.")
        except (ProfileError, SrunError) as error:
            self._error(str(error))
            return
        if not self.auth_lock.acquire(blocking=False):
            self._error("Busy; wait for the current request.")
            return
        self.busy = True
        self._render()
        self._log({"check": "Checking connectivity...", "login": "Signing in...", "logout": "Signing out..."}[operation], {})

        def worker():
            client = None
            try:
                if operation == "check":
                    online = check_connectivity(settings.profile)
                    self._emit("status", "Online" if online else "Offline", {})
                    self._emit("log", "Network is online." if online else "Network is offline or the probe did not match.", {})
                else:
                    client = SrunClient(settings.profile, settings.username, settings.password)
                    getattr(client, operation)()
                    self._emit("log", "Signed in successfully." if operation == "login" else "Signed out successfully.", {})
            except (SrunError, ProfileError) as error:
                self._emit("error", str(error), {})
            except Exception:
                self._emit("error", "Unexpected error. See the source documentation for supported settings.", {})
            finally:
                if client:
                    client.close()
                self.auth_lock.release()
                self._emit("busy", "", {})

        threading.Thread(target=worker, daemon=True).start()

    def _start(self):
        if self.running:
            return
        settings = self._save(notify=False)
        if settings is None:
            return
        self.stop_event = threading.Event()
        self.running = True
        self._render()

        def worker():
            try:
                run_monitor(settings, self.stop_event, self._emit, self.auth_lock)
            except Exception:
                self._emit("error", "Unexpected error. See the source documentation for supported settings.", {})
                self._emit("stopped", "Idle", {})

        threading.Thread(target=worker, daemon=True).start()

    def _stop(self):
        self.stop_event.set()
        self.stop_button.configure(state="disabled")

    def _log(self, key, values, tag=None):
        text = "[" + datetime.datetime.now().strftime("%H:%M:%S") + "] " + self.tr(key, **values)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n", tag or "")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        try:
            with (self.store.directory / "campus-connect.log").open("a", encoding="utf-8") as stream:
                stream.write(text + "\n")
        except OSError:
            pass

    def _drain(self):
        try:
            while True:
                event, key, values = self.messages.get_nowait()
                if event in ("log", "error"):
                    self._log(key, values, "error" if event == "error" else None)
                elif event == "status":
                    self.state_key = key
                elif event == "busy":
                    self.busy = False
                elif event == "stopped":
                    self.running = False
                    self.state_key = "Idle"
                self._render()
        except queue.Empty:
            pass
        self.poll_id = self.after(100, self._drain)

    def _close(self):
        if self.running and not messagebox.askyesno(self.tr("Close while monitoring?"), self.tr("Closing the app stops monitoring."), parent=self):
            return
        self.stop_event.set()
        self.after_cancel(self.poll_id)
        self.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Configurable SRUN BX1 campus network client")
    parser.add_argument("--lang", choices=("en", "zh-CN"), help="Override the saved interface language")
    args = parser.parse_args(argv)
    Application(language=args.lang).mainloop()
    return 0

"""Desktop entry point for Fast Caustic Design."""
import argparse
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import traceback

from PIL import Image, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

from solver import ASSETS, export_mesh, prepare_image, read_mesh, start_solver

TITLE = "Fast Caustic Design"
BACKGROUND = "#101720"
PANEL = "#1a2532"
TEXT = "#edf5ff"
MUTED = "#a9bacd"
ACCENT = "#79e3cb"
IMAGE_TYPES = [("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff"),
               ("All files", "*.*")]
FIELDS = (
    ("Mesh resolution", "-res", "100", int, 16, 256),
    ("Focal distance", "-focal_l", "1.0", float, 0.001, 10000),
    ("Lens thickness", "-thickness", "0.2", float, 0.001, 10000),
    ("Lens width", "-mesh_width", "1.0", float, 0.001, 10000),
)


class ImageSlot:
    def __init__(self, app, parent, title, empty, is_target=False):
        self.app = app
        self.path = self.pattern = self.photo = None
        self.empty = empty
        self.empty_label = "No image selected" if is_target else "Uniform light"
        self.frame = ttk.Frame(parent, style="Card.TFrame", padding=14)
        ttk.Label(self.frame, text=title, style="CardTitle.TLabel").pack(anchor="w")
        self.preview = tk.Label(
            self.frame, bg=BACKGROUND, fg=MUTED, font=("Segoe UI", 11),
            cursor="hand2", takefocus=True, highlightthickness=1, highlightbackground="#344659",
            highlightcolor=ACCENT,
        )
        self.preview.pack(fill="both", expand=True, pady=(9, 8))
        self.preview.bind("<Button-1>", self.browse)
        self.preview.bind("<Return>", self.browse)
        self.preview.bind("<space>", self.browse)
        self.filename = ttk.Label(self.frame, style="CardText.TLabel", wraplength=290)
        self.filename.pack(fill="x", pady=(0, 8))
        controls = ttk.Frame(self.frame, style="Card.TFrame")
        controls.pack(fill="x")
        self.buttons = [ttk.Button(controls, text="Browse…", command=self.browse)]
        if is_target:
            self.buttons.append(ttk.Button(controls, text="Try ring example",
                                           command=lambda: self.load(ASSETS / "data" / "ring.png")))
        else:
            self.buttons.append(ttk.Button(controls, text="Use uniform light", command=self.clear))
        for button in self.buttons:
            button.pack(side="left", padx=(0, 6))
        if app.drag_enabled:
            for widget in (self.frame, self.preview, self.filename):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self.drop)
        self.refresh()

    def browse(self, _event=None):
        if not self.app.process:
            path = filedialog.askopenfilename(parent=self.app.root, title="Choose an image",
                                              filetypes=IMAGE_TYPES)
            if path:
                self.load(Path(path))

    def drop(self, event):
        if self.app.process:
            return "refuse_drop"
        paths = self.app.root.tk.splitlist(event.data)
        if len(paths) != 1:
            messagebox.showerror(TITLE, "Drop one image per panel.", parent=self.app.root)
            return "refuse_drop"
        return "copy" if self.load(Path(paths[0])) else "refuse_drop"

    def load(self, path):
        try:
            pattern = prepare_image(path)
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            self.app.error(f"Could not use {path.name}.\n\n{error}")
            return False
        self.path, self.pattern = path, pattern
        self.refresh()
        self.app.invalidate()
        return True

    def clear(self):
        self.path = self.pattern = None
        self.refresh()
        self.app.invalidate()

    def refresh(self):
        if self.pattern is None:
            self.photo = None
            self.preview.configure(image="", text=self.empty)
            self.filename.configure(text=self.empty_label)
        else:
            preview = self.pattern.resize((144, 144), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(preview, master=self.app.root)
            self.preview.configure(image=self.photo, text="")
            self.filename.configure(text=self.path.name)


class App:
    def __init__(self, root, drag_enabled):
        self.root = root
        self.drag_enabled = drag_enabled
        self.process = self.workspace = self.mesh = None
        self.cancelled = self.closing = False
        self.export_stem = "caustic-lens"
        self.status = tk.StringVar(value="Choose a target image to begin.")
        self.values = {}
        self.entries = []

        root.title(TITLE)
        root.configure(bg=BACKGROUND)
        root.geometry("840x690")
        root.minsize(690, 620)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Control-o>", lambda _event: self.target.browse())
        root.bind("<Control-s>", lambda _event: self.export() if self.mesh else None)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background=BACKGROUND)
        style.configure("TLabel", background=BACKGROUND, foreground=TEXT)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("CardTitle.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 12, "bold"))
        style.configure("CardText.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI", 26, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 13, "bold"))
        style.configure("Hint.TLabel", foreground=MUTED)
        style.configure("TButton", background="#26394b", foreground=TEXT, padding=(10, 6), borderwidth=0)
        style.map("TButton", background=[("active", "#354d65")], foreground=[("disabled", "#8695a5")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#10201d")
        style.map("Accent.TButton", background=[("active", "#acefe0"), ("disabled", "#293e45")],
                  foreground=[("disabled", "#b2c2c7")])
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, padding=5,
                        bordercolor="#344659", lightcolor="#344659", darkcolor="#344659")
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=PANEL)

        layout = ttk.Frame(root, padding=(22, 16))
        layout.pack(fill="both", expand=True)
        ttk.Label(layout, text=TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(layout, text="Generate a 3D lens from a light pattern.", style="Hint.TLabel").pack(anchor="w")
        images = ttk.Frame(layout)
        images.pack(fill="both", expand=True, pady=(16, 6))
        images.rowconfigure(0, weight=1)
        images.columnconfigure((0, 1), weight=1, uniform="image")
        target_prompt = "Drop a target image here" if drag_enabled else "Browse for a target image"
        source_prompt = "Drop a source image here\n(optional)" if drag_enabled else "Browse for a source image\n(optional)"
        self.target = ImageSlot(self, images, "Target pattern", target_prompt, is_target=True)
        self.source = ImageSlot(self, images, "Source lighting", source_prompt)
        self.target.frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.source.frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        ttk.Label(layout, text="Images are fitted to a square with black padding. Bright areas receive more light.",
                  style="Hint.TLabel").pack(anchor="w")
        ttk.Label(layout, text="Lens settings", style="Section.TLabel").pack(anchor="w", pady=(14, 4))
        settings = ttk.Frame(layout)
        settings.pack(fill="x")
        for column, (label, flag, default, *_bounds) in enumerate(FIELDS):
            settings.columnconfigure(column, weight=1, uniform="field")
            variable = self.values[flag] = tk.StringVar(value=default)
            variable.trace_add("write", self.invalidate)
            ttk.Label(settings, text=label).grid(row=0, column=column, sticky="w")
            entry = ttk.Entry(settings, textvariable=variable, width=10)
            entry.grid(row=1, column=column, sticky="ew", padx=(0, 9), pady=(3, 0))
            self.entries.append(entry)
        ttk.Label(layout, text="Resolution is 16–256. Use the same length unit for all geometry settings.",
                  style="Hint.TLabel").pack(anchor="w", pady=(5, 0))
        self.progress = ttk.Progressbar(layout, mode="indeterminate")
        self.progress.pack(fill="x", pady=(15, 4))
        ttk.Label(layout, textvariable=self.status, wraplength=620).pack(anchor="w")
        actions = ttk.Frame(layout)
        actions.pack(fill="x", pady=(10, 0))
        self.generate_button = ttk.Button(actions, text="Generate lens", style="Accent.TButton", command=self.generate)
        self.export_button = ttk.Button(actions, text="Export model…", command=self.export)
        self.cancel_button = ttk.Button(actions, text="Cancel", command=self.cancel)
        self.log_button = ttk.Button(actions, text="Solver log", command=self.show_log)
        for button in (self.generate_button, self.export_button, self.cancel_button, self.log_button):
            button.pack(side="left", padx=(0, 8))
        self.refresh_buttons()

    def invalidate(self, *_args):
        self.mesh = None
        self.status.set("Ready to generate." if self.target.pattern else "Choose a target image to begin.")
        self.refresh_buttons()

    def refresh_buttons(self):
        busy = self.process is not None
        enabled = {
            self.generate_button: not busy and self.target.pattern is not None,
            self.export_button: not busy and self.mesh is not None,
            self.cancel_button: busy and not self.cancelled,
            self.log_button: self.workspace is not None,
        }
        for widget in self.target.buttons + self.source.buttons + self.entries:
            enabled[widget] = not busy
        for widget, active in enabled.items():
            widget.state(["!disabled"] if active else ["disabled"])

    def read_settings(self):
        settings = {}
        for label, flag, _default, convert, low, high in FIELDS:
            try:
                value = convert(self.values[flag].get())
            except ValueError:
                value = None
            if value is None or not low <= value <= high:
                kind = "a whole number" if convert is int else "a number"
                raise ValueError(f"{label} must be {kind} from {low} to {high}.")
            settings[flag] = value
        return settings

    def generate(self):
        if self.process or self.target.pattern is None:
            return
        try:
            settings = self.read_settings()
        except ValueError as error:
            self.error(str(error))
            return
        self.mesh = None
        self.cancelled = False
        try:
            self.cleanup()
            self.workspace = tempfile.TemporaryDirectory(prefix="caustic-")
            folder = Path(self.workspace.name)
            self.target.pattern.save(folder / "target.png")
            if self.source.pattern:
                self.source.pattern.save(folder / "source.png")
            self.process = start_solver(folder, settings, self.source.pattern is not None)
        except OSError as error:
            self.status.set("Generation could not start.")
            self.refresh_buttons()
            self.error(str(error))
            return
        self.started = time.monotonic()
        self.export_stem = self.target.path.stem + "-lens"
        self.progress.start(20)
        self.refresh_buttons()
        self.poll()

    def poll(self):
        result = self.process.poll()
        if result is None:
            if not self.cancelled:
                elapsed = int(time.monotonic() - self.started)
                self.status.set(f"Generating lens… {elapsed // 60}:{elapsed % 60:02d}")
            self.root.after(200, self.poll)
            return
        self.process = None
        self.progress.stop()
        if self.closing:
            self.close()
            return
        if self.cancelled:
            self.status.set("Generation cancelled.")
        else:
            path = Path(self.workspace.name) / "lens.obj"
            try:
                if result:
                    raise ValueError(f"The solver exited with code {result}.")
                read_mesh(path)
                self.mesh = path
                self.status.set("Lens ready. Choose Export model to save it.")
            except (OSError, ValueError) as error:
                self.status.set("Generation failed. Open the solver log for details.")
                self.error(f"{error}\n\nOpen the solver log for details.")
        self.refresh_buttons()

    def export(self):
        if self.mesh is None or self.process:
            return
        selected_type = tk.StringVar(master=self.root, value="Wavefront OBJ")
        filename = filedialog.asksaveasfilename(
            parent=self.root, title="Export lens", initialfile=self.export_stem, typevariable=selected_type,
            filetypes=[("Wavefront OBJ", "*.obj"), ("Binary STL", "*.stl")],
        )
        if not filename:
            return
        destination = Path(filename)
        if not destination.suffix:
            suffix = ".stl" if selected_type.get() == "Binary STL" else ".obj"
            destination = destination.with_suffix(suffix)
            if destination.exists() and not messagebox.askyesno(
                TITLE, f"Replace {destination.name}?", parent=self.root
            ):
                return
        if destination.suffix.lower() not in (".stl", ".obj"):
            self.error("Use an .obj or .stl extension for your model.")
            return
        try:
            export_mesh(self.mesh, destination)
        except (OSError, ValueError, OverflowError, struct.error) as error:
            self.error(f"Could not save the model.\n\n{error}")
        else:
            self.status.set(f"Saved {destination.name}")

    def show_log(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Solver log")
        dialog.geometry("700x440")
        frame = ttk.Frame(dialog, padding=8)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, wrap="none", background=BACKGROUND, foreground=TEXT)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        path = Path(self.workspace.name) / "solver.log"
        try:
            with path.open("rb") as file:
                file.seek(max(0, path.stat().st_size - 65536))
                content = re.sub(r"\x1b\[[0-9;]*m", "", file.read().decode("utf-8", errors="replace"))
        except OSError as error:
            content = str(error)
        text.insert("1.0", content or "No solver output yet.")
        text.see("end")
        text.configure(state="disabled")

    def error(self, message):
        messagebox.showerror(TITLE, message, parent=self.root)

    def cancel(self):
        self.cancelled = True
        if self.process.poll() is None:
            self.process.kill()
        self.status.set("Cancelling…")
        self.refresh_buttons()

    def cleanup(self):
        if self.workspace:
            self.workspace.cleanup()
            self.workspace = None

    def close(self):
        if self.process:
            if not self.cancelled and not messagebox.askyesno(
                TITLE, "Cancel the current generation and close?", parent=self.root
            ):
                return
            self.closing = True
            if not self.cancelled:
                self.cancel()
            return
        self.cleanup()
        self.root.destroy()


def smoke_test(output):
    """Exercise packaged Tk/TkDND, sample input, native generation, and both exporters."""
    try:
        root = TkinterDnD.Tk()
        app = App(root, True)
        root.update()
        sample = ASSETS / "data" / "ring.png"
        app.target.pattern = prepare_image(sample)
        app.target.path = sample
        app.target.refresh()
        root.destroy()
        app.target.pattern.save(output / "target.png")
        process = start_solver(output, {"-res": 24}, False)
        try:
            code = process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise
        if code:
            raise RuntimeError(f"Solver exited with code {code}; see solver.log.")
        mesh = output / "lens.obj"
        _, faces = read_mesh(mesh)
        export_mesh(mesh, output / "check.obj")
        export_mesh(mesh, output / "check.stl")
        if (output / "check.obj").read_bytes() != mesh.read_bytes():
            raise RuntimeError("OBJ export differs from the generated mesh.")
        if (output / "check.stl").stat().st_size != 84 + 50 * len(faces):
            raise RuntimeError("STL export has an unexpected size.")
    except Exception:
        (output / "smoke.log").write_text(traceback.format_exc(), encoding="utf-8")
        return 1
    (output / "smoke.log").write_text("PASS", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--smoke-test", type=Path, metavar="OUTPUT")
    arguments = parser.parse_args()
    if arguments.smoke_test:
        return smoke_test(arguments.smoke_test.resolve())
    try:
        root = TkinterDnD.Tk()
        drag_enabled = True
    except RuntimeError:
        if tk._default_root:
            tk._default_root.destroy()
        root = tk.Tk()
        drag_enabled = False
    App(root, drag_enabled)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

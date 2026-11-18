"""Prepare solver inputs, manage the native process, and export its mesh."""
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

from PIL import Image, ImageOps

IMAGE_SIZE = 256
ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def prepare_image(path):
    with Image.open(path, formats=("PNG", "JPEG", "WEBP", "BMP", "GIF", "TIFF")) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGBA")
        # Composite over darkness before resampling so transparency contributes no light.
        background = Image.new("RGBA", image.size, (0, 0, 0, 255))
        grayscale = Image.alpha_composite(background, image).convert("L")
    grayscale.thumbnail((IMAGE_SIZE, IMAGE_SIZE), Image.Resampling.LANCZOS)
    pattern = Image.new("L", (IMAGE_SIZE, IMAGE_SIZE))
    pattern.paste(grayscale, ((IMAGE_SIZE - grayscale.width) // 2,
                              (IMAGE_SIZE - grayscale.height) // 2))
    darkest, brightest = pattern.getextrema()
    if darkest == brightest:
        raise ValueError("Choose an image with both brighter and darker areas.")
    return pattern


def engine_path():
    name = "caustic_design.exe" if os.name == "nt" else "caustic_design"
    candidates = [ASSETS / "engine" / name, ASSETS / "build" / "Release" / name,
                  ASSETS / "build" / name]
    override = os.environ.get("CAUSTIC_SOLVER")
    if override:
        candidates.insert(0, Path(override).expanduser().resolve())
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("The caustic solver is missing. Extract the full release ZIP or build the solver.")


def start_solver(folder, settings, has_source):
    command = [str(engine_path()), "-in_trg", "target.png", "-output", "lens.obj"]
    if has_source:
        command += ["-in_src", "source.png"]
    for flag, value in settings.items():
        command += [flag, str(value)]
    with (folder / "solver.log").open("wb") as log:
        return subprocess.Popen(
            command, cwd=folder, stdin=subprocess.DEVNULL, stdout=log,
            stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def read_mesh(path):
    """Read the native solver's OBJ subset (finite vertices and triangular faces)."""
    vertices, faces = [], []
    with path.open(encoding="ascii") as source:
        for line in source:
            fields = line.split()
            if fields and fields[0] == "v":
                vertex = tuple(map(float, fields[1:]))
                if len(vertex) != 3 or not all(math.isfinite(n) for n in vertex):
                    raise ValueError("The solver produced invalid vertices.")
                vertices.append(vertex)
            elif fields and fields[0] == "f":
                face = tuple(int(field) - 1 for field in fields[1:])
                if len(face) != 3 or min(face) < 0 or max(face) >= len(vertices):
                    raise ValueError("The solver produced invalid triangles.")
                faces.append(face)
    if not vertices or not faces:
        raise ValueError("The solver produced an empty mesh.")
    return vertices, faces


def export_mesh(source, destination):
    """Replace the destination only after a complete export."""
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
            staged = Path(output.name)
            if destination.suffix.lower() == ".stl":
                vertices, faces = read_mesh(source)
                output.write(b"Caustic Design".ljust(80, b"\0"))
                output.write(struct.pack("<I", len(faces)))
                for face in faces:
                    a, b, c = (vertices[index] for index in face)
                    ux, uy, uz = (q - p for p, q in zip(a, b))
                    vx, vy, vz = (q - p for p, q in zip(a, c))
                    cross = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
                    length = math.hypot(*cross)
                    normal = tuple(n / length for n in cross) if length else (0, 0, 0)
                    output.write(struct.pack("<12fH", *normal, *a, *b, *c, 0))
            else:
                with source.open("rb") as mesh:
                    shutil.copyfileobj(mesh, output)
        staged.replace(destination)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)

# Fast Caustic Design

Turn an image into the geometry of a lens that projects its light pattern.

## Windows desktop app

Download `FastCausticDesign-Windows-x64.zip` from [GitHub Releases](https://github.com/OLT11GAMER/fast_caustic_design_GUI/releases). Extract the entire ZIP, then double-click `FastCausticDesign.exe`.

1. Drop a photo or pattern into **Target pattern**, use **Browse**, or click **Try ring example**.
2. Optionally import a source-light image. The default is uniform illumination.
3. Set the lens dimensions and mesh resolution, then click **Generate lens**. Higher resolutions take longer. Use **Cancel** to stop generation or **Solver log** to inspect the output.
4. Click **Export model** and save an OBJ or STL. You can export the same result again in the other format.

The app accepts PNG, JPEG, WebP, BMP, GIF, and TIFF. It uses the first frame of animated images. It converts images to grayscale, fits them proportionally within a 256 × 256 grid with black padding, and treats transparency as black. The previews show the exact patterns passed to the solver. Use images with visible contrast.

Use a consistent length unit for the width, focal distance, and thickness. Thickness sets the minimum distance between the flat back and optical surface. OBJ and STL do not store a length unit, so use the matching units when opening the model in a slicer or CAD program.

## Build from source

Clone the repository with its Eigen submodule.

```bash
git clone --recurse-submodules https://github.com/OLT11GAMER/fast_caustic_design_GUI.git
cd fast_caustic_design_GUI
```

### Windows

Install CMake, Visual Studio with the C++ desktop workload, Python 3.12 with Tcl/Tk, and [vcpkg](https://learn.microsoft.com/vcpkg/get_started/get-started-msbuild). Set `VCPKG_ROOT` to your vcpkg directory and run these commands in PowerShell.

```powershell
& "$env:VCPKG_ROOT/vcpkg.exe" install "ceres[core]:x64-windows-static" "libpng:x64-windows-static"
cmake -S . -B build -A x64 -DCMAKE_TOOLCHAIN_FILE="$env:VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake" -DVCPKG_TARGET_TRIPLET=x64-windows-static -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded -DCMAKE_DISABLE_FIND_PACKAGE_Cholmod=ON
cmake --build build --config Release --parallel 2
python -m pip install -r desktop/requirements.txt
python desktop/app.py
```

### Linux

The GUI can also run from source. On Ubuntu, install the native dependencies and Python with Tk, then build and launch.

```bash
sudo apt install build-essential cmake libceres-dev libpng-dev libjpeg-dev python3-tk python3-venv
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_DISABLE_FIND_PACKAGE_Cholmod=ON
cmake --build build --parallel 2
python3 -m venv .venv
.venv/bin/pip install -r desktop/requirements.txt
.venv/bin/python desktop/app.py
```

Set `CAUSTIC_SOLVER` to the full path to your executable if you build it in a different directory.

## Command-line usage

The native solver also runs from a terminal. It requires square target and optional source images.

```bash
./build/caustic_design -res 100 -focal_l 1.5 -thickness 0.2 -mesh_width 1 -in_trg data/ring.png -output ring-lens.obj
./build/caustic_design -help
```

![Ring caustic simulation](data/ring_sim.png)

## How does it work
Creating a lens surface whose shadow matches a target image involves two main steps:

### 1. Figuring out how to move the light
First, we need to determine how light should travel from the lens surface to the target shadow. This is done using a technique called optimal transport (OT). OT is a challenging problem and an area of ongoing research. It gives us a map that tells each point on the lens surface where its light should land on the target image.

Traditionally, this problem is solved using structures called power diagrams (also known as Laguerre-Voronoi diagrams). However, in our case, we use a newer, faster method.

The usage of optimal transport is not just to reduce surface variations. It is actually quite important to have a truly optimal transport plan. According to Brenier's theorem, an optimal transport plan is the gradient of a potential. Without this fact we cannot approximate the inverse gradient (or normal integration) afterwards accurately.

### 2. Shaping the surface to steer the light
Once we have the transport map, the next step is to figure out the exact geometry of the lens surface. For each vertex on the surface, we use the OT map to set the x and y direction of the outgoing ray. The z-direction is chosen based on the focal length.

These rays define how we want the surface to bend the light. Using inverse Snell’s law, we compute the target surface normals needed to steer the rays correctly. Finally, we use a solver (Ceres) to adjust the vertex positions on the lens surface so that the computed normals match the target ones. This is called normal integration and can be thought of as approximating the inverse gradient of the vertex normals.

## License

The core of the transport solver and caustic design utility is provided under the [GNU Public License v3](https://www.gnu.org/licenses/gpl-3.0.html).

## References

[1] Georges Nader and Gael Guennebaud. _Instant Transport Maps on 2D Grids_. ACM Transactions on Graphics (Proceedings of Siggraph Asia 2018). [[pdf]](https://hal.inria.fr/hal-01884157) [[video]](https://www.youtube.com/watch?v=Ofz4-reJQRk)

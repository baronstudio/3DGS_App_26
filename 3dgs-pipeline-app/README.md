# 3DGS Pipeline Web App

This project provides a local web application to orchestrate a 3D Gaussian Splatting production pipeline.

## Prerequisites

- **NVIDIA GPU**: CUDA 12.8+ recommended.
- **Python**: Version 3.11 or higher.
- **Node.js**: Version 20 or higher.
- **RealityCapture**: Installed via Epic Games Launcher.
- **FFmpeg**: Installed and available in the system's PATH.
- **Git**: For cloning dependencies.

## Quick Start

1.  **Run the setup script:**
    This will create a Python virtual environment, install dependencies, and clone required tools.
    ```bash
    python setup.py
    ```

2.  **Start the application:**
    - On Windows:
      ```bat
      start.bat
      ```
    - On Linux/macOS:
      ```bash
      ./start.sh
      ```
    This will launch the FastAPI backend server and the Vite frontend development server. The application will open in your default web browser.

## Tool Path Configuration

The `setup.py` script attempts to auto-detect paths for RealityCapture, FFmpeg, and Blender. If it fails, or if you have custom installations, you must manually edit the `config.json` file at the root of the project to provide the correct paths to the executables.

## Pipeline Walkthrough

1.  **Import**: Upload your video file.
2.  **Frame Extraction**: The application uses FFmpeg to extract frames from your video.
3.  **RealityCapture Alignment**: RealityCapture processes the frames to create a sparse point cloud.
4.  **LichtFeld Studio Training**: The point cloud is used to train the Gaussian Splatting model.
5.  **Export & Launch**: The final `.ply` or `.splat` file is generated and can be opened in SuperSplat.
6.  **Blender Scene (Optional)**: A Blender scene can be generated for relighting with the SplatForge addon.

*(Screenshots placeholders would go here)*

## LichtFeld Studio Build Instructions

You must build LichtFeld Studio manually after it has been cloned into the `tools/` directory. Please follow the official build instructions on the [LichtFeld Studio Wiki](https://github.com/MrNeRF/LichtFeld-Studio/wiki). After building, update the `lfs_exe_path` in `config.json` with the path to the executable.

## SplatForge Usage

If you generate a Blender scene, you can use the [SplatForge](https://github.com/ymgenesis/SplatForge-for-Blender) addon for advanced editing and relighting. The generated `.blend` file is pre-configured to work with it.


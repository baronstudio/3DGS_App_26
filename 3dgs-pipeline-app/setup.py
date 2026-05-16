import sys
import subprocess
import venv
import os
import json
from pathlib import Path

def check_python_version():
    """Checks if the Python version is 3.11 or higher."""
    print("Checking Python version...")
    if sys.version_info < (3, 11):
        print("Error: Python 3.11 or higher is required.")
        sys.exit(1)
    print("Python version check passed.")

def create_virtual_environment():
    """Creates a virtual environment if it doesn't exist."""
    venv_dir = Path(".venv")
    if not venv_dir.exists():
        print("Creating virtual environment...")
        venv.create(venv_dir, with_pip=True)
        print("Virtual environment created.")
    else:
        print("Virtual environment already exists.")

def get_pip_path():
    """Gets the path to the pip executable in the virtual environment."""
    if os.name == 'nt':
        return Path(".venv") / "Scripts" / "pip.exe"
    else:
        return Path(".venv") / "bin" / "pip"

def install_python_dependencies():
    """Installs Python dependencies from requirements.txt."""
    print("Installing Python dependencies...")
    pip_path = get_pip_path()
    subprocess.check_call([str(pip_path), "install", "-r", "backend/requirements.txt"])
    print("Python dependencies installed.")

def install_frontend_dependencies():
    """Installs frontend dependencies using npm."""
    print("Installing frontend dependencies...")
    frontend_dir = Path("frontend")
    # Use shell=True on Windows to correctly resolve 'npm'
    subprocess.check_call("npm install", shell=True, cwd=frontend_dir)
    print("Frontend dependencies installed.")

def clone_repositories():
    """Clones required Git repositories if they don't exist."""
    print("Cloning external tool repositories...")
    tools_dir = Path("tools")
    tools_dir.mkdir(exist_ok=True)

    dependencies = [
        {
            "name": "LichtFeld Studio",
            "repo": "https://github.com/MrNeRF/LichtFeld-Studio",
            "local_path": "tools/lichtfeld-studio",
        },
        {
            "name": "SuperSplat (local fallback)",
            "repo": "https://github.com/playcanvas/supersplat",
            "local_path": "tools/supersplat",
        }
    ]

    for dep in dependencies:
        local_path = Path(dep["local_path"])
        if not local_path.exists():
            print(f"Cloning {dep['name']}...")
            subprocess.check_call(["git", "clone", dep["repo"], str(local_path)])
            print(f"{dep['name']} cloned.")
        else:
            print(f"{dep['name']} already exists.")

def find_executable(name, search_paths):
    """Finds an executable in common installation directories."""
    for path in search_paths:
        for root, _, files in os.walk(path):
            if name in files:
                return str(Path(root) / name)
    # Check if it's in PATH
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if (Path(p) / name).exists():
            return str(Path(p) / name)
    return None

def create_config_file():
    """Creates a config.json file with auto-detected tool paths."""
    print("Creating config.json...")
    
    # Default config structure from pydantic models
    config = {
        "tools": {
            "rc_exe_path": None,
            "lfs_exe_path": None,
            "ffmpeg_path": "ffmpeg",
            "blender_exe_path": None,
            "supersplat_url": "https://superspl.at/editor"
        },
        "stubs": {
            "ffmpeg_stub": False,
            "rc_stub": True,
            "lfs_stub": True,
            "blender_stub": True,
            "rc_stub_duration_seconds": 8.0,
            "lfs_stub_duration_seconds": 15.0,
            "lfs_stub_iterations": 30000,
            "lfs_stub_fake_ply": True
        }
    }

    # Auto-detect RealityScan.exe on Windows
    if os.name == 'nt':
        rc_path = find_executable("RealityScan.exe", ["C:/Program Files/Epic Games"])
        config["tools"]["rc_exe_path"] = rc_path
        if not rc_path:
            print("Warning: RealityScan.exe not found. Stub mode will be used. You can specify the path manually in config.json.")
    
    # Placeholder for LichtFeld Studio (user needs to build it)
    print("Info: Path to LichtFeld-Studio.exe must be set manually in config.json after building.")

    # Auto-detect ffmpeg
    ffmpeg_path = find_executable("ffmpeg.exe" if os.name == 'nt' else "ffmpeg", os.environ.get("PATH", "").split(os.pathsep))
    config["tools"]["ffmpeg_path"] = ffmpeg_path if ffmpeg_path else "ffmpeg"
    if not ffmpeg_path:
        print("Warning: ffmpeg not found in PATH. Please install it or specify the path in config.json.")

    # Auto-detect Blender
    blender_search_paths = []
    if os.name == 'nt':
        blender_search_paths = ["C:/Program Files/Blender Foundation"]
    elif sys.platform == 'darwin':
         blender_search_paths = ["/Applications"]
    
    blender_exe = "blender.exe" if os.name == 'nt' else "blender"
    blender_path = find_executable(blender_exe, blender_search_paths)
    config["tools"]["blender_exe_path"] = blender_path
    if not blender_path:
        print("Warning: blender not found. Please specify the path manually in config.json.")

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)
    print("config.json created. Please review and complete the paths.")

def generate_stub_assets():
    """Generates stub assets for testing."""
    print("Generating stub assets...")
    
    # Run the PLY generator script
    script_path = "tools/test_assets/generate_sample_ply.py"
    if not Path(script_path).exists():
        print(f"Warning: {script_path} not found. Skipping stub asset generation.")
        return
        
    python_exe = sys.executable
    subprocess.run([python_exe, script_path], check=True)

    # Copy sample.ply to stub_pointcloud.ply
    sample_ply = Path("tools/test_assets/sample.ply")
    stub_pointcloud_ply = Path("tools/test_assets/stub_pointcloud.ply")
    if sample_ply.exists():
        import shutil
        shutil.copy(sample_ply, stub_pointcloud_ply)
        print(f"Copied {sample_ply} to {stub_pointcloud_ply}")

def main():
    """Main setup script execution."""
    check_python_version()
    create_virtual_environment()
    install_python_dependencies()
    install_frontend_dependencies()
    clone_repositories()
    create_config_file()
    generate_stub_assets()
    print("\nSetup complete! To start the application, run: start.bat (Windows) or ./start.sh (Linux/macOS)")

if __name__ == "__main__":
    main()

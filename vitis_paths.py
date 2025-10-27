import configparser
import inspect
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Tuple

# Get the script directories
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

# Create relevent path variables
PROJECTS_PATH = os.path.join(parentdir, "Projects")
TOP_PATH = os.path.join(parentdir, "Top")
HDL_DATA_PATH = os.path.join(os.path.dirname(parentdir), "hdl", "data")
SRC_PATH = os.path.join(parentdir)
LOG_PATH = os.path.join(parentdir, "logs")

# Cached Vitis root
_VITIS_ROOT = None
_VITIS_VERSION = None


def read_config(config_folder: str, filename: str) -> configparser.ConfigParser:
    config_path = os.path.join(config_folder, f"{filename}.conf")
    config = configparser.ConfigParser(comment_prefixes=("#"))
    config.read(config_path)
    return config


def get_vitis_root() -> Tuple[str, str]:
    """
    Detect Vitis installation path and version using CLI location.
    
    Returns:
        tuple: (vitis_root_path, version)
    
    Raises:
        RuntimeError: If Vitis not found or version < 2024.1
    """
    global _VITIS_ROOT, _VITIS_VERSION
    
    # Return cached values if available
    if _VITIS_ROOT and _VITIS_VERSION:
        return _VITIS_ROOT, _VITIS_VERSION
    
    # Detect platform and use appropriate command
    system = platform.system()
    if system == "Windows":
        cmd = ["where", "vitis"]
    else:  # Linux/Unix
        cmd = ["which", "vitis"]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        vitis_cli_path = result.stdout.strip().split('\n')[0]  # Take first result
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("Vitis CLI not found. Ensure Vitis is installed and in PATH.")
    
    # Parse path to extract root
    # Expected: .../Xilinx/<version>/bin/vitis or .../Xilinx/Vitis/<version>/bin/vitis
    path_parts = Path(vitis_cli_path).parts

    # Find Xilinx in path and get version
    try:
        xilinx_idx = next(i for i, part in enumerate(path_parts) if part.lower() == "xilinx")

        # Handle both path structures:
        # 1. /Xilinx/2024.1/...
        # 2. /Xilinx/Vitis/2024.1/...
        next_part = path_parts[xilinx_idx + 1]
        if next_part.lower() == "vitis":
            # Structure: /Xilinx/Vitis/2024.1/...
            version = path_parts[xilinx_idx + 2]
            vitis_root = str(Path(*path_parts[:xilinx_idx + 3]))
        else:
            # Structure: /Xilinx/2024.1/...
            version = next_part
            vitis_root = str(Path(*path_parts[:xilinx_idx + 2]))
    except (StopIteration, IndexError):
        raise RuntimeError(f"Could not parse Vitis root from path: {vitis_cli_path}")

    # Validate version >= 2024.1
    try:
        year, minor = version.split('.')[:2]
        if int(year) < 2024 or (int(year) == 2024 and int(minor) < 1):
            raise RuntimeError(f"Vitis version {version} not supported. Requires 2024.1 or later.")
    except ValueError:
        raise RuntimeError(f"Could not parse Vitis version: {version}")
    
    # Cache the results
    _VITIS_ROOT = vitis_root
    _VITIS_VERSION = version
    
    return vitis_root, version


def get_library_path(lib_name: str, lib_version: str) -> str:
    """
    Build path to a Vitis library.
    
    Args:
        lib_name: Library name (e.g., 'xilflash', 'openamp')
        lib_version: Library version (e.g., 'v4_11')
    
    Returns:
        str: Full path to library
    """
    vitis_root, _ = get_vitis_root()
    
    # Check sw_services first (for openamp, etc.)
    sw_services_path = os.path.join(
        vitis_root, "data", "embeddedsw", "ThirdParty", "sw_services",
        f"{lib_name}_{lib_version}"
    )
    if os.path.exists(sw_services_path):
        return sw_services_path
    
    # Check lib/sw_services next (for xilflash, etc.)
    lib_services_path = os.path.join(
        vitis_root, "data", "embeddedsw", "lib", "sw_services",
        f"{lib_name}_{lib_version}"
    )
    if os.path.exists(lib_services_path):
        return lib_services_path
    
    # Check lib/bsp for BSP libraries
    bsp_path = os.path.join(
        vitis_root, "data", "embeddedsw", "lib", "bsp",
        f"{lib_name}_{lib_version}"
    )
    if os.path.exists(bsp_path):
        return bsp_path
    
    raise FileNotFoundError(
        f"Library {lib_name}_{lib_version} not found in Vitis installation"
    )


def get_driver_path(driver_name: str, driver_version: str) -> str:
    """
    Build path to a Vitis driver.
    
    Args:
        driver_name: Driver name (e.g., 'ttcps', 'gpio')
        driver_version: Driver version (e.g., 'v3_19')
    
    Returns:
        str: Full path to driver
    """
    vitis_root, _ = get_vitis_root()
    
    driver_path = os.path.join(
        vitis_root, "data", "embeddedsw", "XilinxProcessorIPLib", "drivers",
        f"{driver_name}_{driver_version}"
    )
    
    if not os.path.exists(driver_path):
        raise FileNotFoundError(
            f"Driver {driver_name}_{driver_version} not found in Vitis installation"
        )
    
    return driver_path

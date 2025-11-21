# Vitis On Git

A configuration-driven tool for managing AMD/Xilinx Vitis embedded software projects with Git. Instead of committing massive generated project files, define your projects using lightweight configuration files for reproducibility across machines.

## Features

- Configuration-based project management using `.conf` files
- Automated platform, domain, and application creation
- Support for multiple domains and applications per project
- Comprehensive BSP configuration (libraries, drivers, compiler flags)
- Automated compiler and linker settings via UserConfig.cmake
- Debug launch configuration generation for VSCode/Theia IDE
- Full project build automation with multiple build backends
  - Vitis server builds (full IDE integration)
  - Direct Ninja builds (faster, CI/CD friendly)
  - System Ninja support (no Vitis dependency for builds)
- IDE tooling support (clangd IntelliSense, code completion)
- Multi-project workspace with active project switching
- Version control friendly - only configuration files and user source code need to be committed

## Requirements

### For Project Creation
- AMD/Xilinx Vitis 2024.1 or later
- Vitis must be added to your system PATH
- Python 3.x (included with Vitis)
- Bash shell (Linux/WSL/Git Bash on Windows)

### For Building (Optional: Choose one)
- **Option A**: Use Vitis-bundled Ninja (default, always included)
- **Option B**: Use system Ninja (≥1.5, recommended ≥1.11.1) with `--system-ninja` flag
  - Windows: `choco install ninja`
  - Linux: `sudo apt-get install ninja-build`
  - macOS: `brew install ninja`

### For CI/CD Builds (Without Vitis)
If using pre-configured projects with `--system-ninja`:
- ARM GNU Toolchain (12.2.Rel1 or compatible)
- CMake (3.24.x or compatible)
- Ninja (1.5+ from system PATH)
- Platform export files (committed to repository)

## Project Structure

This tool is designed to be included as a Git submodule in your Vitis workspace:

```text
src/
├── Vitis/                           # This submodule
│   ├── Do                           # Main entry script
│   ├── launch.py                    # Command dispatcher
│   ├── vitis_create.py              # Project creation logic
│   ├── vitis_platform.py            # Platform/domain management
│   ├── vitis_application.py         # Application management
│   ├── vitis_build.py               # Build and activate commands
│   ├── vitis_paths.py               # Path utilities
│   ├── vitis_logging.py             # Logging configuration
│   └── templates/                   # JSON templates
│       └── <varous templates>       # Various templates for easy quickstart
├── Projects/                        # Generated projects (gitignore this)
│   └── <generated projects>
│   └── <project_name>_platform/
│       └── export/                  # Platform files (commit for CI/CD)
├── .clangd                          # Auto-generated clangd config
├── compile_commands.json            # Auto-generated (symlink to active project)
└── Top/                             # Your project configurations
    └── ExampleProject/
        ├── vitis.conf               # Top-level project config
        ├── platform.conf            # Platform configuration
        ├── domain.conf              # Domain/BSP configuration
        ├── application.conf         # Application configuration
        └── launch.conf              # Debug launch configuration
hdl/
├── data/                            # XSA hardware design files
    └── design.xsa
```

## Installation

1. Add Vitis On Git as a submodule in your repository:
   ```bash
   git submodule add https://github.com/GNPower/Vitis.git src/Vitis
   git submodule update --init --recursive
   ```

2. Ensure Vitis is in your PATH:
   ```bash
   # Linux
   which vitis

   # Windows (add to PATH environment variable)
   where vitis
   ```

3. Create your project structure:
   ```bash
   mkdir -p src/Top/MyProject
   ```

## Usage

### Basic Command Syntax

```bash
./Vitis/Do <COMMAND> <PARAMETERS>
```

### Available Commands

#### CREATE - Create Complete Project
Creates a platform, domain(s), and application(s) from configuration files, then builds everything.

```bash
./Vitis/Do CREATE <project_name>
```

**Example:**
```bash
./Vitis/Do CREATE MyProject
```

This will:
1. Read configuration from `src/Top/MyProject/vitis.conf`
2. Create the platform from the specified XSA file
3. Configure domain(s) with BSP settings
4. Create and configure application(s)
5. Build the platform
6. Build all applications
7. Generate debug launch configurations

#### ACTIVATE - Set Active Project for IDE Tooling
Sets a project as "active" for IDE tooling (clangd IntelliSense). Updates `.clangd` and `compile_commands.json` at the common parent directory to provide correct code completion and navigation.

```bash
./Vitis/Do ACTIVATE <project_name>
```

**Example:**
```bash
./Vitis/Do ACTIVATE MyProject
```

This will:
1. Updates `.clangd` configuration in the common source directory for the project
2. Modified the `compile_commands.json` in the common source directory for the project
2. Enables IntelliSense/code completion for shared library code when using Vitis IDE

**When to use:**
- After switching between multiple projects in your workspace
- If IntelliSense shows errors for headers that should exist

#### BUILD - Build Project
Builds a project using either the Vitis server or directly with Ninja. Supports clean builds and automatic project activation.

```bash
./Vitis/Do BUILD <project_name> [OPTIONS]
```

**Options:**
- `--tools {vitis|ninja}` - Build tool to use (default: `vitis`)
  - `vitis`: Uses Vitis server (standard, IDE-integrated)
  - `ninja`: Direct Ninja build (faster, no Vitis server needed)
- `--clean` - Clean before building (ninja only)
- `--system-ninja` - Use system Ninja from PATH instead of Vitis-bundled (requires Ninja ≥1.5)
- `--no-activate` - Don't activate the project after building

**Examples:**

```bash
# Standard Vitis server build
./Vitis/Do BUILD MyProject

# Fast Ninja build (no Vitis server required)
./Vitis/Do BUILD MyProject --tools ninja

# Clean build with Ninja
./Vitis/Do BUILD MyProject --tools ninja --clean

# Use system Ninja (CI/CD friendly, no Vitis dependency)
./Vitis/Do BUILD MyProject --tools ninja --system-ninja

# Build without activating the project
./Vitis/Do BUILD MyProject --tools ninja --no-activate
```

**Ninja vs Vitis Builds:**

| Feature | Vitis Build | Ninja Build |
|---------|-------------|-------------|
| Startup Time | ~10-20s | ~1s |
| Vitis Required | ✅ Yes | ❌ No (with `--system-ninja`) |
| IDE Integration | ✅ Full | ⚠️ Limited |
| Incremental Builds | ✅ Yes | ✅ Yes (faster) |
| CI/CD Friendly | ⚠️ Needs license | ✅ License-free |
| Use Case | Development | CI/CD, Quick rebuilds |

**System Ninja Installation:**

To use `--system-ninja`, install Ninja independently:

```bash
# Windows
choco install ninja

# Linux
sudo apt-get install ninja-build

# macOS
brew install ninja
```

**Minimum Ninja version:** 1.5 (recommended: 1.11.1+)

### Configuration File Reference

#### 1. vitis.conf (Top-Level Configuration)

Defines the overall project structure and references to other configuration files.

```ini
[platform]
NAME = my_platform
DESCRIPTION = My custom platform
CONFIG = platform

[application]
NAME = my_app
DESCRIPTION = My application
CONFIG = application

# Optional: Additional applications
[application_1]
NAME = my_second_app
DESCRIPTION = Second application
CONFIG = application2
```

#### 2. platform.conf (Platform Configuration)

Defines the platform hardware source and domain(s).

```ini
[flow]
SOURCE = xsa                          # Source type: xsa, fixed, or platform
XSA = design_wrapper                  # XSA filename (without .xsa extension)

[boot]
BOOT_COMPONENTS = true                # Generate FSBL/boot components

[domain]
NAME = standalone_domain
DISPLAY_NAME = Standalone Domain
PROCESSOR_INSTANCE = ps7_cortexa9_0   # Target processor
CONFIG = domain                       # Domain config file reference

# Optional: Additional domains
[domain_1]
NAME = freertos_domain
DISPLAY_NAME = FreeRTOS Domain
PROCESSOR_INSTANCE = ps7_cortexa9_1
CONFIG = domain_freertos
```

#### 3. domain.conf (Domain/BSP Configuration)

Configures the Board Support Package, libraries, drivers, and OS settings.

```ini
[domain]
OS = standalone                       # OS type: standalone, freertos, linux

[compiler]
flags = -mcpu=cortex-a9 -mfpu=vfpv3  # Additional compiler flags

[os]
stdin = ps7_uart_1                    # Standard input peripheral
stdout = ps7_uart_1                   # Standard output peripheral

# Library configuration
[library_0]
name = xilffs                         # Library name
enabled = true                        # Enable/disable built-in library

[library_1]
name = xilflash                       # External library
version = v4_11                       # Library version
param_serial_flash_family = 2         # Library parameters

# Driver configuration
[driver_0]
name = ttcps                          # Driver name
version = v3_19                       # Driver version
```

#### 4. application.conf (Application Configuration)

Defines application settings, compiler/linker configuration.

```ini
[application]
PLATFORM = my_platform                # Platform name (without _platform suffix)
DOMAIN = standalone_domain            # Target domain name
TEMPLATE = Hello World                # Optional: Vitis template

# Compiler symbols
[compiler.symbols]
defined = DEBUG,CUSTOM_FLAG           # Comma-separated defines
undefined = NDEBUG                    # Comma-separated undefines

# Include directories - Supports multi-line format and variable expansion
[compiler.directories]
include_paths = ../common/inc,./inc   # Single-line format (comma-separated)

# Multi-line format example:
# include_paths =
#     ${PARENT_DIR}/DAM_LIB_FW/include,
#     ${PROJECT_DIR}/my_platform/bsp/include
#     ${VITIS_INSTALL_DIR}/gnu/aarch32/lin/gcc-arm-none-eabi/include

# Source files - Compile .c files from custom locations
[compiler.sources]
source_files =                        # Multi-line, comma-separated source files
# Example:
#     ${PARENT_DIR}/DAM_LIB_FW/src/uart.c
#     ${PARENT_DIR}/custom_code/main.c

# Source folders - Recursively include all .c and .S files
source_folders =                      # Multi-line, comma-separated directory paths
# Example:
#     ${PARENT_DIR}/DAM_LIB_FW/src
#     ${PARENT_DIR}/PLDProcessorIPLib/Zynq7000/drivers

# Optimization
[compiler.optimization]
level = -O2                           # Optimization level
other_flags = -ffunction-sections     # Additional flags

# Debug settings
[compiler.debugging]
level = -g3                           # Debug level
other_flags =                         # Additional debug flags

# Compiler warnings
[compiler.warnings]
all = true                            # Enable -Wall
extra = true                          # Enable -Wextra
as_errors = false                     # Enable -Werror
pedantic = false                      # Enable -pedantic

# Misc compiler flags
[compiler.misc]
verbose = false                       # Verbose output
ansi = false                          # ANSI compliance
other_flags =                         # Other custom flags

# Linker libraries
[linker.libraries]
libraries = m,pthread                 # Comma-separated library names
search_paths = /opt/lib               # Multi-line and variable expansion supported
# Example:
#     ${PROJECT_DIR}/my_platform/bsp/lib
#     ${PARENT_DIR}/custom_libs

# Linker script - Supports variable expansion
[linker.script]
file = ${CMAKE_SOURCE_DIR}/lscript.ld # Path to linker script (supports variables)

# General linker settings
[linker.general]
no_start_files = false                # -nostartfiles
no_default_libs = false               # -nodefaultlibs
no_stdlib = false                     # -nostdlib
omit_symbols = false                  # Strip symbols (-s)

# Misc linker flags
[linker.misc]
other_flags =                         # Other custom flags

# Launch configuration
[launch]
NAME = debug_config
DISPLAY_NAME = Debug Configuration
CONFIG = launch                       # Launch config file reference
```

#### 5. launch.conf (Debug Launch Configuration)

Defines debug/launch settings for VSCode/Theia IDE.

```ini
[launch]
name = Debug MyApp                    # Configuration name
debug_type = baremetal-zynq          # Debug type

[target]
core = ps7_cortexa9_0                # Target processor core
context = zynq                        # Target context

[hardware]
# Optional: Auto-detected if not specified
bitstream =                           # Path to bitstream
fsbl =                               # Path to FSBL
ps_init_tcl =                        # Path to PS init script

[behavior]
reset_system = true                   # Reset system before debug
program_device = true                 # Program FPGA
reset_apu = false                     # Reset APU
reset_processor = true                # Reset processor
stop_at_entry = false                # Stop at main entry
```

## Advanced Features

### Path Variables and Multi-line Format

The tool supports custom path variables and multi-line format for include directories, library search paths, source files, and linker scripts.

#### Supported Variables

- `${VITIS_INSTALL_DIR}` - Expands to your Vitis installation root (e.g., `E:/Xilinx/Vitis/2024.1`)
- `${PROJECT_DIR}` - Expands to the workspace root (`src/Projects`)
- `${PARENT_DIR}` - Expands to the source root (`src/`)
- `${CMAKE_SOURCE_DIR}` - CMake variable (not expanded by Python, evaluated at build time)

Variables are expanded with forward slashes for cross-platform CMake compatibility.

#### Multi-line Format

Path lists can be specified using:
- Commas only: `path1,path2,path3`
- Newlines only:
  ```ini
  paths =
      path1
      path2
      path3
  ```
- Mixed format (commas and newlines):
  ```ini
  paths =
      path1,
      path2
      path3
  ```

#### Example: Including BSP Headers

```ini
[compiler.directories]
include_paths =
    ${PARENT_DIR}/DAM_LIB_FW/include,
    ${PROJECT_DIR}/ZedBoard_platform/zynq_fsbl/bsp/ps7_cortexa9_0/include
    ${VITIS_INSTALL_DIR}/gnu/aarch32/lin/gcc-arm-none-eabi/arm-none-eabi/include
```

#### Example: Compiling Source from /src Directory

By default, Vitis expects application source files in the generated project directory. To compile `.c` files from your custom `/src` directories:

```ini
[compiler.sources]
source_files =
    ${PARENT_DIR}/DAM_LIB_FW/src/uart.c
    ${PARENT_DIR}/DAM_LIB_FW/src/timer.c,
    ${PARENT_DIR}/custom_code/main.c
```

This allows you to keep your source code in version control under `/src` while the generated projects remain in the gitignored `/src/Projects` directory.

#### Example: Including Entire Source Directories

To include all `.c` and `.S` files from directories recursively:

```ini
[compiler]
source_folders =
    ${PARENT_DIR}/DAM_LIB_FW/src
    ${PARENT_DIR}/PLDProcessorIPLib/Zynq7000/drivers
```

This will:
- Recursively find all `.c` and `.S` files in specified directories
- Create folder symlinks in the project (preserves directory structure)
- Fall back to recreating directory structure with file symlinks on Windows if folder symlinks fail
- Keep your Vitis IDE project organized with proper hierarchy

**Difference between `source_files` and `source_folders`:**
- **`source_files`**: Individual files placed flat in `<project>/src/filename.c` - good for a few specific files
- **`source_folders`**: Entire directories with preserved structure in `<project>/src/foldername/...` - good for including many files while keeping organization

Both can be used together in the same configuration.

### Multiple Applications

Define multiple applications in `vitis.conf`:

```ini
[application]
NAME = bootloader
CONFIG = bootloader_app

[application_1]
NAME = main_app
CONFIG = main_app

[application_2]
NAME = test_app
CONFIG = test_app
```

### Multiple Domains

Define multiple domains in `platform.conf`:

```ini
[domain]
NAME = domain_a9_0
PROCESSOR_INSTANCE = ps7_cortexa9_0
CONFIG = domain_a9_0

[domain_1]
NAME = domain_a9_1
PROCESSOR_INSTANCE = ps7_cortexa9_1
CONFIG = domain_a9_1
```

### Custom Libraries and Drivers

The tool automatically locates Xilinx libraries and drivers in your Vitis installation:

```ini
[library_0]
name = openamp                        # Third-party library
version = v2023_2

[driver_0]
name = gpio                           # Custom driver version
version = v4_9
```

## Git Integration

### Recommended .gitignore

```gitignore
# Ignore generated projects
src/Projects/

# Ignore logs
src/Vitis/logs/

# Keep configuration files
!src/Top/**/*.conf

# Keep XSA files
!src/hdl/data/*.xsa
```

### Workflow

1. Create/modify configuration files in `src/Top/YourProject/`
2. Commit configuration changes to Git
3. Team members clone the repository
4. Team members run `./Vitis/Do CREATE YourProject`
5. Identical projects are generated on all machines

## Troubleshooting

### Vitis Not Found Error
```
ERROR: [Vitis:Do-9] Vitis could not be found
```
**Solution:** Ensure Vitis is in your PATH:
```bash
which vitis  # Should return path to vitis executable
```

### Version Not Supported
```
RuntimeError: Vitis version X.Y not supported. Requires 2024.1 or later.
```
**Solution:** Upgrade to Vitis 2024.1 or later. Earlier versions are not compatible due to API changes.

### Library/Driver Not Found
```
FileNotFoundError: Library xxx_vX_Y not found in Vitis installation
```
**Solution:** Verify the library/driver name and version exist in your Vitis installation at:
- Libraries: `$XILINX_VITIS/data/embeddedsw/lib/`
- Drivers: `$XILINX_VITIS/data/embeddedsw/XilinxProcessorIPLib/drivers/`

### XSA File Not Found
```
ERROR: XSA file not found
```
**Solution:** Ensure your XSA file is located in `src/hdl/data/` and the filename in `platform.conf` matches (without the .xsa extension).

## Logging

Detailed logs are written to `src/Vitis/logs/workspace_builder.log` for debugging purposes.

## Known Limitations

- **Vitis 2024.1 API Workaround:** The `domain.set_config()` API always returns errors in Vitis 2024.1, so this tool directly edits `bsp.yaml` files as a workaround.
- **Supported Platforms:** Currently only supports creating platforms from XSA files. Fixed platforms and platform-to-platform creation are not yet implemented.
- **Operating Systems:** Tested on Linux and Windows (via Git Bash/WSL). Native Windows command prompt may have issues.

## CI/CD Integration

### GitHub Actions Example

Build firmware automatically without Vitis installation using the "Platform-in-Repo" strategy:

#### Prerequisites
1. Commit platform export files to your repository:
   ```bash
   git add src/Projects/MyProject_platform/export/
   git commit -m "Add platform files for CI/CD"
   ```

2. Create `.github/workflows/build.yml`:

```yaml
name: Build Firmware

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3
        with:
          submodules: recursive

      - name: Install ARM Toolchain
        uses: carlosperate/arm-none-eabi-gcc-action@v1
        with:
          release: '12.2.Rel1'

      - name: Install Build Tools
        run: |
          sudo apt-get update
          sudo apt-get install -y ninja-build cmake

      - name: Verify Tools
        run: |
          arm-none-eabi-gcc --version
          cmake --version
          ninja --version

      - name: Build Firmware
        run: |
          ./Vitis/Do BUILD MyProject --tools ninja --system-ninja

      - name: Check Binary Size
        run: |
          arm-none-eabi-size src/Projects/MyProject/build/MyProject.elf

      - name: Upload Firmware
        uses: actions/upload-artifact@v3
        with:
          name: firmware-${{ github.sha }}
          path: |
            src/Projects/MyProject/build/MyProject.elf
          retention-days: 90
```

#### Benefits
- ✅ **No Vitis license** required in CI/CD
- ✅ **Fast builds** (2-5 minutes vs 30+ with Vitis)
- ✅ **GitHub-hosted runners** (no self-hosted required)
- ✅ **Small platform files** (~15MB, version controlled)
- ✅ **Reproducible builds** across all environments

#### Alternative: Self-Hosted with Vitis
For teams that need to regenerate platforms in CI/CD:
- Use self-hosted runners with Vitis Embedded (12-15 GB)
- Configure license server access
- Use Vitis builds: `./Vitis/Do BUILD MyProject`

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

```
Copyright 2024

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

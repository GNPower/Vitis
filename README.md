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

#### UPDATE - Apply Configuration Changes to an Existing Project
Re-reads the configuration files of a project that CREATE already made and applies them to the existing platform and application components, without recreating them.

```bash
./Vitis/Do UPDATE <project_name> [OPTIONS]
```

**Options:**
- `--platform` - Update only the platform and its domains
- `--application` - Update only the applications
- `--no-build` - Skip the rebuild at the end

Without `--platform` or `--application`, UPDATE does both. Passing both flags updates neither, and only the rebuild runs.

**Examples:**

```bash
# Re-apply application.conf changes, then build with Ninja
./Vitis/Do UPDATE MyProject --application --no-build
./Vitis/Do BUILD MyProject --tools ninja

# Re-apply every configuration file and rebuild with the Vitis server
./Vitis/Do UPDATE MyProject
```

This will:
1. Re-apply each domain's `domain.conf` (`[compiler] flags`, `[os]` stdin/stdout, `[library_N]`, `[driver_N]`) and regenerate its BSP. The XSA is not re-imported.
2. For each application in `vitis.conf`, add and remove source links in `<app>/src` to match `source_files` and `source_folders`.
3. Write every `[compiler]` and `[linker]` key into `UserConfig.cmake` and relink `lscript.ld`, with the same code CREATE uses.
4. Rebuild the platform and every application with the Vitis server, unless `--no-build` is given.

UPDATE doesn't change an application's `PLATFORM`, `DOMAIN` or `TEMPLATE`, doesn't rewrite `launch.json` from `[launch]` sections, and skips applications that CREATE hasn't made yet.

**Before running UPDATE:**
- The project must exist. UPDATE stops with an error when `src/Projects/<platform NAME>_platform` is missing.
- Close the Vitis IDE. It holds the workspace lock that UPDATE needs.

**Warning:** UPDATE deletes every `.c`, `.S` and `.h` file directly in `<app>/src`, and every subdirectory there that contains `.c` or `.S` files, unless `source_files` or `source_folders` lists it. Files a Vitis `TEMPLATE` generated count too. Keep application sources in your own tree and list them in `source_files` or `source_folders`, as `examples/zedboard` does.

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
# Source type: xsa, fixed, or platform
SOURCE = xsa
# XSA filename (without .xsa extension)
XSA = design_wrapper

[boot]
# Generate FSBL/boot components
BOOT_COMPONENTS = true

[domain]
NAME = standalone_domain
DISPLAY_NAME = Standalone Domain
# Target processor
PROCESSOR_INSTANCE = ps7_cortexa9_0
# Domain config file reference
CONFIG = domain

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
# OS type: standalone, freertos, linux
OS = standalone

[compiler]
# Additional compiler flags
flags = -mcpu=cortex-a9 -mfpu=vfpv3

[os]
# Standard input peripheral
stdin = ps7_uart_1
# Standard output peripheral
stdout = ps7_uart_1

# Library configuration
[library_0]
# Library name
name = xilffs
# Enable/disable built-in library
enabled = true

[library_1]
# External library
name = xilflash
# Library version
version = v4_11
# Library parameters
param_serial_flash_family = 2

# Driver configuration
[driver_0]
# Driver name
name = ttcps
# Driver version
version = v3_19
```

#### 4. application.conf (Application Configuration)

Defines one application component: the platform and domain it builds against, the sources it compiles, and the compiler and linker settings written into the generated `<app>/src/UserConfig.cmake`. Only the sections and keys below are read.

```ini
[application]
# Platform NAME from vitis.conf, without the _platform suffix
PLATFORM = zedboard
# Domain NAME from platform.conf
DOMAIN = standalone_ps7_cortexa9_0
# Vitis application template such as hello_world. Empty creates a bare application.
TEMPLATE =

[compiler]
compile_definitions = DEBUG, BOARD_REV=3
undefined_symbols = __clang__
include_directories =
    ${PARENT_DIR}/my_lib/include,
    ${PROJECT_DIR}/zedboard_platform/ps7_cortexa9_0/standalone_ps7_cortexa9_0/bsp/include
source_files = ${PARENT_DIR}/example_app/main.c
source_folders = ${PARENT_DIR}/my_lib/src
optimization_level = O2
# Two or more flags in one value need double quotes
optimization_other_flags = "-ffunction-sections -fdata-sections"
debug_level = g3
debug_other_flags =
warnings_all = true
warnings_extra = true
warnings_as_errors = false
warnings_check_syntax_only = false
warnings_pedantic = false
warnings_pedantic_as_errors = false
warnings_inhibit_all = false
verbose = false
ansi = false
other_flags =

[linker]
no_start_files = false
no_default_libs = false
no_stdlib = false
omit_all_symbol_info = false
libraries = m
link_directories =
linker_script = ${PARENT_DIR}/example_app/lscript.ld
other_flags = -Wl,--gc-sections

# Optional debug launch configurations: [launch], [launch_1], [launch_2], ...
[launch]
NAME = hw_debug
DISPLAY_NAME = Debug Hardware
# A launch config file in the same folder (see launch.conf), without .conf
CONFIG = launch_hw
```

**File format:**
- Comments go on their own line and start with `#`. Text after a value, such as `O2  # note`, becomes part of the value.
- A value continues on indented lines. Comment lines between its entries are skipped.
- Write a literal `%` as `%%`. A single `%` stops the tool with an `InterpolationSyntaxError`.
- Section names are case-sensitive; key names are not.

**`[application]` keys:**

| Key | Required | Meaning |
|-----|----------|---------|
| `PLATFORM` | Yes | Platform `NAME` from `vitis.conf`, without the `_platform` suffix |
| `DOMAIN` | Yes | Domain `NAME` from `platform.conf` |
| `TEMPLATE` | No | Vitis application template, such as `hello_world`. Empty or missing creates a bare application |

**`[compiler]` keys:**

| Key | UserConfig.cmake variable | Value |
|-----|---------------------------|-------|
| `compile_definitions` | `USER_COMPILE_DEFINITIONS` | Comma-separated `NAME` or `NAME=value` entries |
| `undefined_symbols` | `USER_UNDEFINED_SYMBOLS` | Comma-separated names, each passed as `-U<name>` |
| `include_directories` | `USER_INCLUDE_DIRECTORIES` | Path list |
| `optimization_level` | `USER_COMPILE_OPTIMIZATION_LEVEL` | `none`, `O0`, `O1`, `O2`, `O3` or `Os` |
| `optimization_other_flags` | `USER_COMPILE_OPTIMIZATION_OTHER_FLAGS` | Flags |
| `debug_level` | `USER_COMPILE_DEBUG_LEVEL` | `none`, `g1`, `g2` or `g3` |
| `debug_other_flags` | `USER_COMPILE_DEBUG_OTHER_FLAGS` | Flags |
| `warnings_all` | `USER_COMPILE_WARNINGS_ALL` | Boolean, `-Wall` |
| `warnings_extra` | `USER_COMPILE_WARNINGS_EXTRA` | Boolean, `-Wextra` |
| `warnings_as_errors` | `USER_COMPILE_WARNINGS_AS_ERRORS` | Boolean, `-Werror` |
| `warnings_check_syntax_only` | `USER_COMPILE_WARNINGS_CHECK_SYNTAX_ONLY` | Boolean, `-fsyntax-only` |
| `warnings_pedantic` | `USER_COMPILE_WARNINGS_PEDANTIC` | Boolean, `-pedantic` |
| `warnings_pedantic_as_errors` | `USER_COMPILE_WARNINGS_PEDANTIC_AS_ERRORS` | Boolean, `-pedantic-errors` |
| `warnings_inhibit_all` | `USER_COMPILE_WARNINGS_INHIBIT_ALL` | Boolean, `-w` |
| `verbose` | `USER_COMPILE_VERBOSE` | Boolean, `-v` |
| `ansi` | `USER_COMPILE_ANSI` | Boolean, `-ansi` |
| `other_flags` | `USER_COMPILE_OTHER_FLAGS` | Flags |

Two more `[compiler]` keys pick the sources and don't touch UserConfig.cmake:
- `source_files`: path list of files, each linked into `<app>/src/`.
- `source_folders`: path list of directories, each linked into `<app>/src/<folder>/`. Their `.c` and `.S` files compile recursively.

Path lists follow [Path Variables and Multi-line Format](#path-variables-and-multi-line-format).

**`[linker]` keys:**

| Key | UserConfig.cmake variable | Value |
|-----|---------------------------|-------|
| `no_start_files` | `USER_LINK_NO_START_FILES` | Boolean, `-nostartfiles` |
| `no_default_libs` | `USER_LINK_NO_DEFAULT_LIBS` | Boolean, `-nodefaultlibs` |
| `no_stdlib` | `USER_LINK_NO_STDLIB` | Boolean, `-nostdlib` |
| `omit_all_symbol_info` | `USER_LINK_OMIT_ALL_SYMBOL_INFO` | Boolean, `-s` |
| `libraries` | `USER_LINK_LIBRARIES` | Comma-separated library names without the `lib` prefix, such as `m` for `libm.a` |
| `link_directories` | `USER_LINK_DIRECTORIES` | Path list |
| `linker_script` | `USER_LINKER_SCRIPT` | One path. The file is linked to `<app>/src/lscript.ld`, replacing the generated script |
| `other_flags` | `USER_LINK_OTHER_FLAGS` | Flags |

**`[launch]` sections:** `[launch]`, `[launch_1]`, `[launch_2]` and so on each need `NAME`, `DISPLAY_NAME` and `CONFIG`. `CONFIG` names a launch config file in the same folder, without `.conf`. CREATE writes one entry per section into `<app>/_ide/.theia/launch.json`; UPDATE leaves that file alone.

**How CREATE and UPDATE apply the keys:**
- A key missing from the file leaves its variable as it is: the template default after CREATE, the last written value after UPDATE. Commenting out a key doesn't undo it.
- Booleans take `true` or `false` (also `yes`/`no`, `on`/`off`, `1`/`0`). `true` writes the flag and `false` clears the variable.
- Flag values are copied into `set(...)` unchanged, and an empty value clears the variable. Wrap two or more flags in double quotes: unquoted, `-ffunction-sections -fdata-sections` reaches the compiler as `-ffunction-sections-fdata-sections`. Path variables such as `${PARENT_DIR}` aren't expanded in flag values.
- An empty `compile_definitions` clears `USER_COMPILE_DEFINITIONS`. An empty `undefined_symbols`, `include_directories`, `libraries` or `link_directories` is ignored, so UPDATE can shorten these lists but not empty them.
- `compile_definitions`, `undefined_symbols` and `libraries` split on commas only. A line break doesn't start a new entry.
- `optimization_level = none` writes no `-O` flag, so the `-O2` in the domain's default BSP compiler flags applies; a Zynq-7000 standalone domain exports it through `cortexa9_toolchain.cmake`. Leaving the key out keeps the template default `-O0`. Use `O0` for an unoptimized build, since GCC uses the last `-O` on the command line.

**Vitis 2024.1 template limits:**
- The link options block in the generated UserConfig.cmake reads `USER_LINKER_NO_START_FILES`, `USER_LINKER_NO_DEFAULT_LIBS`, `USER_LINKER_NO_STDLIB` and `USER_LINKER_OMIT_ALL_SYMBOL_INFO`, but the variables are named `USER_LINK_*`. The four boolean linker keys never reach the linker. Put `-nostartfiles`, `-nodefaultlibs`, `-nostdlib` or `-s` in `[linker] other_flags` instead.
- The application templates pass `USER_LINK_DIRECTORIES` as a single `-L"<dir>/"` argument, so `link_directories` takes one directory. Add more as `-L<dir>` flags in `[linker] other_flags`.

#### 5. launch.conf (Debug Launch Configuration)

Defines debug/launch settings for VSCode/Theia IDE.

```ini
[launch]
# Configuration name
name = Debug MyApp
# Debug type
debug_type = baremetal-zynq

[target]
# Target processor core
core = ps7_cortexa9_0
# Target context
context = zynq

[hardware]
# Optional: Auto-detected if not specified
# Path to bitstream
bitstream =
# Path to FSBL
fsbl =
# Path to PS init script
ps_init_tcl =

[behavior]
# Reset system before debug
reset_system = true
# Program FPGA
program_device = true
# Reset APU
reset_apu = false
# Reset processor
reset_processor = true
# Stop at main entry
stop_at_entry = false
```

## Advanced Features

### Path Variables and Multi-line Format

The path keys are `include_directories`, `source_files` and `source_folders` in `[compiler]`, and `link_directories` and `linker_script` in `[linker]`. All five expand the variables below, and all but `linker_script` take a list.

#### Supported Variables

- `${VITIS_INSTALL_DIR}` - Expands to your Vitis installation root (e.g., `E:/Xilinx/Vitis/2024.1`)
- `${PROJECT_DIR}` - Expands to the workspace root (`src/Projects`)
- `${PARENT_DIR}` - Expands to the source root (`src/`)
- `${CMAKE_...}` and `${XILINX_...}` - Left for CMake to evaluate at build time, such as `${CMAKE_SOURCE_DIR}`. A path that contains one is passed through unchanged, including any other variable in it.

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

Lines starting with `#` between entries are skipped, so one entry can be commented out without touching the others.

#### Example: Including BSP Headers

```ini
[compiler]
include_directories =
    ${PARENT_DIR}/DAM_LIB_FW/include,
    ${PROJECT_DIR}/ZedBoard_platform/ps7_cortexa9_0/standalone_ps7_cortexa9_0/bsp/include
    # Windows install layout
    ${VITIS_INSTALL_DIR}/gnu/aarch32/nt/gcc-arm-none-eabi/aarch32-xilinx-eabi/usr/include
```

#### Example: Compiling Source from /src Directory

By default, Vitis expects application source files in the generated project directory. To compile `.c` files from your custom `/src` directories:

```ini
[compiler]
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
# Third-party library
name = openamp
version = v2023_2

[driver_0]
# Custom driver version
name = gpio
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

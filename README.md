# Open-Canoe / 开放独木舟

**[English](#english) | [中文](#中文)**

---

<a name="english"></a>
## English

Extensible CAN bus analysis tool — hardware firmware side.

Open-Canoe is a CAN bus analyzer that runs on STM32 microcontrollers. It supports CAN message monitoring (with microsecond timestamps), optional ADC waveform acquisition, and communication with a PC host via USART or USB-CDC using a custom binary protocol. The architecture is built on a clean hardware abstraction layer — adding support for a new MCU requires only one new directory under `hardware/`.

### Supported MCUs

| MCU | Core | Flash | CAN | ADC | USB CDC | Status |
|-----|------|-------|-----|-----|---------|--------|
| STM32F103C8T6 | Cortex-M3 | 64 KB | 1 | Yes | No | Supported |
| STM32F407VET6 | Cortex-M4 | 512 KB | 2 | Yes | Yes | Supported |

### Build Environment

- **Toolchain**: `arm-none-eabi-gcc` (ARM Embedded Toolchain, 10.3+)
- **Build system**: GNU Make
- **Windows**: [ARM GNU Toolchain](https://developer.arm.com/downloads/-/gnu-rm) + MSYS2 Make
- **Linux/macOS**: `apt install arm-none-eabi-gcc` / `brew install arm-none-eabi-gcc`

### Quick Start

```bash
cd tools

# Build + flash (recommended)
python build.py flash f103       # STM32F103C8T6
python build.py flash f407       # STM32F407VET6

# Build only
python build.py build f103
python build.py list             # List targets (JSON)

# Manual build
cd ../hardware
make -f Makefile_f103
make -f Makefile_f407
```

Output: `hardware/build_f103/open_canoe_f103.bin` (or `build_f407/`).

### Test

```bash
uv venv && uv pip install pyserial

# Full protocol test
.venv\Scripts\python tools\test_pyserial.py COM7

# Single command
.venv\Scripts\python tools\send_cmd.py COM7 info
.venv\Scripts\python tools\send_cmd.py COM7 caps
.venv\Scripts\python tools\send_cmd.py COM7 status
.venv\Scripts\python tools\send_cmd.py COM7 adc
```

### Project Structure

```
hardware/
├── f103/                       # STM32F103C8T6 (all MCU-specific files)
│   ├── stm32f103_config.h      # Pin map, clocks, features (created by us)
│   ├── stm32f1xx_hal_conf.h    # HAL module selection (created by us)
│   ├── startup_stm32f103xb.s   # Startup (copied from CubeMX)
│   ├── STM32F103XX_FLASH.ld    # Linker script (copied from CubeMX)
│   ├── system_stm32f1xx.c      # System init (copied from CubeMX)
│   ├── CMSIS/                  # CMSIS headers (copied from CubeMX)
│   └── HAL/                    # HAL drivers (copied from CubeMX, used modules only)
├── f407/                       # STM32F407VET6
│   └── ... (same structure)
├── inc/                        # Hardware-abstracted headers (shared, no MCU deps)
│   ├── protocol.h              # Wire protocol frame format
│   ├── can_api.h               # CAN API
│   ├── adc_api.h               # ADC API
│   ├── comm_api.h              # Communication API
│   ├── device_api.h            # Device info API
│   └── device_config.h         # Auto-selects MCU config
├── src/                        # Firmware source (shared, HAL-based)
│   ├── main.c                  # Entry point & main loop
│   ├── protocol_handler.c      # Protocol encode/decode (pure C)
│   ├── can_driver.c            # CAN driver
│   ├── adc_driver.c            # ADC driver
│   ├── comm_driver.c           # USART + USB CDC driver
│   ├── device_manager.c        # Device identity & capabilities
│   ├── sysmem.c                # Memory stubs (copied from CubeMX)
│   └── syscalls.c              # System call stubs (copied from CubeMX)
├── Makefile_f103
└── Makefile_f407

tools/                          # PC-side tools
├── build.py                    # Unified build/flash (for App integration)
├── send_cmd.py                 # Send single protocol command
└── test_pyserial.py            # Full protocol test suite
```

### Adding a New MCU

Example: adding STM32H750VB.

**Step 1: Generate CubeMX demo**

Create a minimal CubeMX project for the new MCU with USART enabled. Note the demo path, e.g. `STM32H750VB/STM32H750VB_DEMO/`.

**Step 2: Create `hardware/h7/`**

Copy files from the CubeMX demo:

```
hardware/h7/
├── startup_stm32h750xx.s       ← from DEMO/ (do not modify)
├── STM32H750XX_FLASH.ld        ← from DEMO/ (do not modify)
├── system_stm32h7xx.c          ← from DEMO/Core/Src/ (do not modify)
├── CMSIS/Core/Include/         ← from DEMO/Drivers/CMSIS/Core/Include/ (all files)
├── CMSIS/Device/ST/STM32H7xx/Include/ ← from DEMO/Drivers/CMSIS/Device/... (all files)
└── HAL/Inc/ + HAL/Src/         ← from DEMO/Drivers/STM32H7xx_HAL_Driver/
                                   Inc: all files (headers, small)
                                   Src: only used modules (see Makefile)
```

**Step 3: Create our config files**

```
hardware/h7/
├── stm32h7xx_config.h          ← pin maps, clocks, features (use stm32f407_config.h as template)
└── stm32h7xx_hal_conf.h        ← enable HAL modules we use (CAN, USART, ADC, DMA, etc.)
```

**Step 4: Create `hardware/Makefile_h7`**

Copy `Makefile_f407`, adjust:
- `MCU_DIR = $(HW_DIR)/h7`
- `-DSTM32H750xx`
- CPU/FPU flags (`-mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard`)
- HAL source paths (`stm32h7xx_hal_xxx.c`)
- Device CMSIS path

**Step 5: Register target**

Add to `tools/build.py` TARGETS dict:
```python
"h7": {
    "name": "STM32H750VB",
    "makefile": "Makefile_h7",
    "build_dir": "build_h7",
    "flash_addr": "0x08000000",
    "bin": "open_canoe_h7.bin",
    "hex": "open_canoe_h7.hex",
},
```

**No changes needed** to `src/`, `inc/`, `tools/send_cmd.py`, or `tools/test_pyserial.py`.

### Key Rules

- Files copied from CubeMX (`startup_*.s`, `*_FLASH.ld`, `system_*.c`, `CMSIS/`, `HAL/`, `sysmem.c`, `syscalls.c`) **must not be modified**.
- Only our config files (`*_config.h`, `*_hal_conf.h`) and shared `src/`/`inc/` are edited.
- HAL Src: only copy the `.c` files listed in the Makefile (CAN, USART, ADC, DMA, GPIO, RCC, TIM, etc.). Do not copy unused modules (ETH, I2C, SPI, etc.).

### FAQ

**Q: Does the hardware start CAN listening automatically on boot?**
No. After initialization, the firmware waits for App commands. CAN listening starts only upon receiving `CMD_CAN_START_LISTEN`.

**Q: What happens on F103 when the App requests ADC sampling?**
If ADC is configured (`HAS_ADC=1`), it works normally. If not, the hardware returns `ERR_ADC_NOT_AVAILABLE`.

**Q: Can I use both USART and USB-CDC simultaneously?**
No. One active channel at a time. Switch via `CMD_COMM_SET_INTERFACE`.

**Q: How accurate are the timestamps?**
Microsecond resolution via 1 MHz free-running timer (TIM2). 32-bit counter wraps every ~71 minutes.

---

<a name="中文"></a>
## 中文

可扩展的 CAN 总线分析工具 — 硬件固件端。

Open-Canoe 是一个运行在 STM32 微控制器上的 CAN 总线分析器。支持 CAN 报文监听（微秒级时间戳）、可选的 ADC 波形采集，以及通过 USART 或 USB-CDC 使用自定义二进制协议与 PC 主机通信。架构基于清晰的硬件抽象层 —— 添加新 MCU 只需在 `hardware/` 下新增一个目录。

### 支持的 MCU

| MCU | 内核 | Flash | CAN | ADC | USB CDC | 状态 |
|-----|------|-------|-----|-----|---------|------|
| STM32F103C8T6 | Cortex-M3 | 64 KB | 1 | 有 | 无 | 已支持 |
| STM32F407VET6 | Cortex-M4 | 512 KB | 2 | 有 | 有 | 已支持 |

### 编译环境

- **工具链**: `arm-none-eabi-gcc` (ARM Embedded Toolchain, 10.3+)
- **构建系统**: GNU Make
- **Windows**: [ARM GNU Toolchain](https://developer.arm.com/downloads/-/gnu-rm) + MSYS2 Make

### 快速开始

```bash
cd tools

# 编译 + 烧录（推荐）
python build.py flash f103       # STM32F103C8T6
python build.py flash f407       # STM32F407VET6

# 仅编译
python build.py build f103
python build.py list             # 列出目标 (JSON)

# 手动编译
cd ../hardware
make -f Makefile_f103
make -f Makefile_f407
```

产物：`hardware/build_f103/open_canoe_f103.bin`（或 `build_f407/`）。

### 测试

```bash
uv venv && uv pip install pyserial

# 完整协议测试
.venv\Scripts\python tools\test_pyserial.py COM7

# 单条命令
.venv\Scripts\python tools\send_cmd.py COM7 info
.venv\Scripts\python tools\send_cmd.py COM7 caps
```

### 项目结构

```
hardware/
├── f103/                       # STM32F103C8T6（所有 MCU 专属文件）
│   ├── stm32f103_config.h      # 引脚、时钟、功能（我们创建）
│   ├── stm32f1xx_hal_conf.h    # HAL 模块选择（我们创建）
│   ├── startup_stm32f103xb.s   # 启动文件（从 CubeMX 复制，不修改）
│   ├── STM32F103XX_FLASH.ld    # 链接脚本（从 CubeMX 复制，不修改）
│   ├── system_stm32f1xx.c      # 系统初始化（从 CubeMX 复制，不修改）
│   ├── CMSIS/                  # CMSIS 头文件（从 CubeMX 复制，不修改）
│   └── HAL/                    # HAL 驱动（从 CubeMX 复制，仅保留用到的模块）
├── f407/                       # STM32F407VET6
│   └── ...（同样结构）
├── inc/                        # 硬件无关头文件（共享）
├── src/                        # 固件源码（共享，基于 HAL）
├── Makefile_f103
└── Makefile_f407

tools/                          # PC 端工具
├── build.py                    # 统一编译/烧录入口
├── send_cmd.py
└── test_pyserial.py
```

### 添加新 MCU

以添加 STM32H750VB 为例：

**步骤 1：生成 CubeMX Demo**

为新 MCU 创建最小 CubeMX 项目（启用 USART），记录路径。

**步骤 2：创建 `hardware/h7/`**

从 CubeMX Demo 复制文件：

```
hardware/h7/
├── startup_stm32h750xx.s       ← 来自 DEMO/（不修改）
├── STM32H750XX_FLASH.ld        ← 来自 DEMO/（不修改）
├── system_stm32h7xx.c          ← 来自 DEMO/Core/Src/（不修改）
├── CMSIS/Core/Include/         ← 来自 DEMO/Drivers/CMSIS/Core/Include/（全部）
├── CMSIS/Device/ST/STM32H7xx/Include/ ← 来自 DEMO/Drivers/CMSIS/Device/...（全部）
└── HAL/Inc/ + HAL/Src/         ← 来自 DEMO/Drivers/STM32H7xx_HAL_Driver/
                                   Inc: 全部头文件（很小）
                                   Src: 只用 Makefile 中列出的 .c 文件
```

**步骤 3：创建配置文件**

```
hardware/h7/
├── stm32h7xx_config.h          ← 参考 stm32f407_config.h
└── stm32h7xx_hal_conf.h        ← 启用 CAN, USART, ADC, DMA 等
```

**步骤 4：创建 `hardware/Makefile_h7`**

复制 `Makefile_f407`，修改：
- `MCU_DIR = $(HW_DIR)/h7`
- `-DSTM32H750xx`
- CPU/FPU 标志（`-mcpu=cortex-m7` 等）
- HAL 源文件路径
- CMSIS 路径

**步骤 5：注册目标**

在 `tools/build.py` 的 TARGETS 中添加：
```python
"h7": {"name": "STM32H750VB", "makefile": "Makefile_h7", ...}
```

**无需修改** `src/`、`inc/`、`tools/send_cmd.py`、`tools/test_pyserial.py`。

### 核心规则

- 从 CubeMX 复制的文件（`startup_*.s`、`*_FLASH.ld`、`system_*.c`、`CMSIS/`、`HAL/`、`sysmem.c`、`syscalls.c`）**不得修改**
- 只有我们创建的配置文件（`*_config.h`、`*_hal_conf.h`）和共享的 `src/`/`inc/` 可以修改
- HAL Src：只复制 Makefile 中列出的模块（CAN、USART、ADC、DMA、GPIO、RCC、TIM 等），不要复制无关模块（ETH、I2C、SPI 等）

### 常见问题

**Q: 硬件上电后会自动开始 CAN 监听吗？**
不会。初始化完成后，固件等待 App 命令。

**Q: F103 上 App 请求 ADC 采样会怎样？**
如果配置启用了 ADC（`HAS_ADC=1`），正常工作。否则返回 `ERR_ADC_NOT_AVAILABLE`。

**Q: 能同时使用 USART 和 USB-CDC 吗？**
不能。同一时间只使用一个通道。

**Q: 时间戳精度如何？**
微秒级，通过 1 MHz 定时器（TIM2）实现。

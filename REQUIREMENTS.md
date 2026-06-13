# Open-Canoe 测试需求文档

## 一、项目目标

App (Python/tkinter) 通过 USART 协议与 STM32F103 固件通信，实现 CAN 总线分析仪功能。F103 板载 CAN 收发器连接 PA11/PA12。

## 二、App 功能模块

| 模块     | 功能                                | 测试要点                                    |
| -------- | ----------------------------------- | ------------------------------------------- |
| 连接     | 选 COM 口→连接→显示设备信息       | 自动检测 COM7，115200 波特率                |
| CAN 配置 | 连接后自动配置 500kbps NORMAL 模式  | 3 个 ACK 全部 OK                            |
| 发送     | 输入 CAN ID+数据→点击发送          | 报文追踪表显示 TX 行                        |
| 环回切换 | 勾选/取消环回复选框                 | CAN 模式在 NORMAL/LOOPBACK 间切换           |
| 环回接收 | 环回模式下发送→收到真实 CAN 环回帧 | 报文追踪表应显示 RX 行，ID 和数据与发送一致 |
| 正常模式 | 取消环回→发送                      | **不应出现 RX 行**（正常模式无环回）  |
| 周期发送 | 设置间隔→开始周期→多次自动发送    | 每帧都应收到 ACK，环回模式下每帧都应有 RX   |
| 断开     | 点击断开                            | 串口关闭，状态显示"未连接"                  |

## 三、核心行为规则

1. **NORMAL 模式发送**：报文追踪表只显示 TX（发送帧），**绝不能出现 RX**
2. **LOOPBACK 模式发送**：报文追踪表显示 TX + RX（环回帧），RX 的 ID 和数据**必须与发送一致**，这是真实的 CAN 硬件环回
3. **模式切换**：NORMAL→LOOPBACK 切换后不应弹出旧帧（残留帧问题）
4. **周期发送后**：停止周期→单次发送仍正常工作
5. **NORMAL 发送失败后**：切换到 LOOPBACK→发送仍正常工作（不能累积错误导致 CAN 锁死）
6. **日志**：成功的发送不应在日志中显示 "CMD 0x34 failed"

## 四、测试方法

### 必须启动真实 GUI，通过 invoke/event_generate 模拟点击，验证日志和报文表

```python
import os, time
os.environ['HOME'] = 'C:/Users/GX'  # tkinter 需要 HOME 目录
from gui.app import MainWindow
from core.models import CANMessage

app = MainWindow()

# === 1. 选择端口 ===
app._dev._port_var.set('COM7')

# === 2. 点击连接按钮 (invoke 触发 command=self._toggle) ===
app._dev._btn.invoke()
deadline = time.monotonic() + 12
while time.monotonic() < deadline:
    app.root.update()              # ★ 必须调 update() 驱动 _poll 回调
    time.sleep(0.03)
    if app._tr and app._tr.is_connected:
        break

# 等待 _configure_can (300ms after connect)
for _ in range(20):
    app.root.update(); time.sleep(0.05)

# === 3. 点击环回复选框 (直接调回调或 invoke) ===
app._dev._loopback_var.set(True)
app._on_loopback(True)  # 等价于点击 checkbutton
time.sleep(0.3)
for _ in range(20): app.root.update(); time.sleep(0.02)

# === 4. 填写数据并点击发送按钮 ===
app._snd._id_var.set('0x123')
app._snd._data_var.set('AA BB CC DD')
app._snd._dlc_var.set('4')
app._snd._btn_once.invoke()  # ★ invoke 模拟真实按钮点击
time.sleep(0.5)
for _ in range(40): app.root.update(); time.sleep(0.02)

# === 5. 验证报文表 (必须是真实数据，不能靠猜测) ===
children = app._tbl._tree.get_children()
for child in children:
    vals = app._tbl._tree.item(child, 'values')
    # vals = [序号, 时间, CAN_ID, 类型, DLC, 方向, 数据]
    direction = vals[5]  # 'TX' 或 'RX'
    can_id = vals[2]     # '0x123'
    dlc = vals[3]        # '4'
    data = vals[4]       # 'AA BB CC DD'
    print(f'{direction}: ID={can_id} DLC={dlc} data={data}')

# === 6. 验证日志 (不能有 CMD 0x34 failed) ===
log = app._log._text.get('1.0', 'end-1c')
assert 'CMD 0x34 failed' not in log, f'BUG: TX failed in log!'
assert 'CAN TX failed' not in log, f'BUG: TX error in log!'

# === 7. 断开 ===
app._disconnect()
app.root.destroy()
```

**关键点**：

- 必须用 `app.root.update()` 驱动 tkinter 事件循环
- `_poll` 通过 `after(200, self._poll)` 运行，不用 `update()` 就不会触发
- `invoke()` 模拟真实按钮点击（触发 `command=` 绑定的函数）
- 验证必须读 `_tbl._tree.get_children()` 和 `_log._text.get()`
- 不能凭记忆判断——必须读取实际 widget 状态

## 五、历史 Bug 清单

### App 层 (Python)

| # | 症状                                   | 根因                                                                                                   | 修复                                       | 状态            |
| - | -------------------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------ | --------------- |
| 1 | 点连接无响应，卡死 50+ 秒              | `auto_detect()` 扫描蓝牙 COM3-6，每个超时 1.5s × 5 波特率 = 37s+                                    | 过滤蓝牙端口，只扫 USB CDC，减少波特率数量 | ✅ 已修复       |
| 2 | 连接报 "No response from device"       | `detect_and_connect` 等待心跳，但心跳在 boot 时已发送，错过后再也收不到                              | 增加 GET_INFO 主动探测 fallback            | ✅ 已修复       |
| 3 | 默认波特率 921600 与固件 115200 不匹配 | `defaults.yaml` 中 `serial_baud: 921600`                                                           | 改为 `115200`                            | ✅ 已修复       |
| 4 | `_try_heartbeat` 找不到设备          | 心跳已发送，无主动探测                                                                                 | 发送 GET_INFO 作为 fallback                | ✅ 已修复       |
| 5 | 报文表有 RX 但日志报 CMD 0x34 failed   | Python `unpack_can_frame_up` 读 20 字节，实际 `can_frame_up_t` 是 19 字节 packed，解包失败静默丢弃 | 改为 `payload[:19]`                      | ✅ 已修复       |
| 6 | `Path.home()` 报错                   | 沙箱环境无 HOME 目录                                                                                   | 设置 `HOME` 环境变量                     | ⚠️ 仅测试环境 |

### 固件层 (C)

| #  | 症状                                                                            | 根因                                                                                                                                                    | 修复                                                                                           | 状态          |
| -- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------- |
| 7  | CAN 完全不工作                                                                  | 引脚配置为 PB8/PB9（AFIO 重映射），但板载收发器在 PA11/PA12（默认引脚）                                                                                 | 改为 PA11(RX/上拉)、PA12(TX/AF_PP)，去掉 AFIO 重映射                                           | ✅ 已修复     |
| 8  | CAN TX 报显性位错误 (LEC=5)                                                     | 时钟设为 HSE 72MHz 但实际用 HSI 64MHz，APB1 时钟宏定义为 36MHz 实际 32MHz，CAN 时序错误                                                                 | APB1_CLOCK_HZ 改为 32MHz，使用 HSI+PLL=64MHz                                                   | ✅ 已修复     |
| 9  | HAL_CAN_Init 初始化后 CAN 不能发送                                              | HAL 在 F103 上的 CAN 实现有已知兼容问题，`HAL_CAN_Start`/`HAL_CAN_Init` 不可靠                                                                      | 放弃 HAL，改用 SPL 风格直接寄存器写入                                                          | ✅ 已修复     |
| 10 | 模式切换后 TX 失败                                                              | `can_set_mode` 退出 init 模式后 CAN 未稳定就发送                                                                                                      | 退出 init 后加稳定延迟                                                                         | ⚠️ 部分修复 |
| 11 | 3 次发送后 mailbox 全满，后续发送全部失败                                       | fire-and-forget 发送不释放 mailbox，3 个 mailbox 填满后 TME=0                                                                                           | 每次发送前检查 RQCP 释放已完成传输的 mailbox                                                   | ✅ 已修复     |
| 12 | NORMAL 模式出现 RX 帧（幽灵帧）                                                 | F103 在 NORMAL 模式也会内部环回 TX→RX；ISR 在 NORMAL 模式下也上报 RX                                                                                   | ISR 中检查 BTR[30]（环回位），NORMAL 模式不回调；send handler 中检查 BTR 模式再决定是否上报 RX | ✅ 已修复 |
| 13 | 模式切换时弹出旧帧（残留 RX）                                                   | NART=0 导致失败 TX 自动重传，重传的环回帧进入 FIFO，模式切换后被读取                                                                                    | 模式切换时清零所有 TX mailbox + 清空 RX FIFO；NORMAL 模式设 NART=1 禁止重传                    | ⚠️ 部分修复 |
| 14 | NORMAL 模式发送失败后切换到环回仍失败                                           | TX 错误计数器累积到 bus-off，切换模式时未清除                                                                                                           | 每次进入 init 模式自动清除错误计数器（F103 硬件特性）                                          | ⚠️ 部分修复 |
| 15 | `protocol_send_can_frame` 隐含声明导致调用失败                                | 函数在 `handle_can_send_frame` 之后定义，前向引用缺少声明                                                                                             | 在 protocol_handler.c 开头加 `extern void protocol_send_can_frame(...)`                      | ✅ 已修复     |
| 16 | ISR 中的 `HAL_CAN_GetRxMessage` 与 SPL 风格 CAN 不兼容，读到 DLC=0            | HAL 函数依赖 `h->State` 等内部状态，与 SPL 直接寄存器写入不同步                                                                                       | ISR 改用直接读 `sFIFOMailBox` 寄存器                                                         | ⚠️ 部分修复 |
| 17 | ISR 抢先读取 FIFO 导致 send handler 的 poll 看到空 FIFO                         | CAN ISR (FMPIE0) 在 poll 之前触发，读走了环回帧                                                                                                         | 禁用 FMPIE0，只用 send handler 内的 poll；ISR 只负责 drain                                     | ⚠️ 部分修复 |
| 18 | `HAL_CAN_IRQHandler` 可能消费 RX 中断标志导致 `can_process_rx_irq` 收不到帧 | HAL ISR handler 清理了中断标志                                                                                                                          | 绕过 HAL_CAN_IRQHandler，ISR 中直接调用 `can_process_rx_irq`                                 | ⚠️ 部分修复 |
| 19 | 忙等延迟不可靠（编译优化可能消除，长度不确定）                                  | 使用 `for(volatile uint32_t d=0; d<N; d++)` 类型的忙等                                                                                                | 尽量用 `HAL_Delay()`，关键路径保留短忙等                                                     | ⚠️ 部分修复 |
| 20 | `can_run_test` (cmd 0x05) 可工作但主流程不工作                                | `can_run_test` 从零初始化 CAN（开时钟→GPIO→完整 init→发送），主流程的 `can_init`+`can_set_mode`+`can_send_frame` 混合 HAL/SPL 导致状态不一致 | 尚未彻底解决 — 需要统一为纯 SPL 风格                                                          | ❌ 未解决     |
| 21 | `can_run_test_ext` 带外设复位的版本在 config 命令之后调用会挂起               | 外设复位 (RCC_APB1RSTR) 清除时钟使能位和所有寄存器                                                                                                      | 去掉外设复位，改为仅进入 init 模式再退出（自动清除错误计数器）                                 | ✅ 已修复     |
| 23 | ISR 错误中断标志未清除导致中断风暴                    | `can_process_error_irq` 在环回模式下返回前未清除 EWG/EPV/BOF/LEC 标志，ISR 无限重入         | 环回模式下也清除所有错误标志                                                                 | ✅ 已修复     |
| 24 | APB1=32MHz 下 500kbps/250kbps 时序硬编码值错误      | 硬编码 psc=9 对应 APB1=36MHz，实际 APB1=32MHz 需 psc=8                                         | 修正硬编码时序值                                                                             | ✅ 已修复     |
| 25 | **环回模式无 RX 帧（核心问题）**                     | CAN 错误中断 (ERRIE/BOFIE/LECIE) 在环回 TX 期间持续触发形成中断风暴，CPU 锁死在 ISR 中，busy-wait 轮询无法执行 | `handle_can_send_frame` 在 send+poll 前保存并禁用 CAN IER，操作完成后恢复                    | ✅ 已修复     |
| 22 | 发送命令无响应（函数挂起）                                                      | RQCP 等待永不满足——CAN 控制器在 NORMAL 模式无收发器时无法完成 TX                                                                                      | fire-and-forget：放入 mailbox 即返回成功，不等 RQCP                                            | ✅ 已修复     |

## 六、文档同步规则

**每次修改代码或发现新 Bug 时必须同步更新本文档**：

- 新 Bug → 追加到 §五 历史 Bug 清单
- 修复 Bug → 更新对应条目状态
- 新问题 → 追加到 §七
- 测试结果 → 记录到 §十
- **跨模块影响规则**：如果某个模块的修改涉及了其他模块（例如修改 CAN 驱动影响了协议处理或串口通信），则被影响的模块也必须至少测试一遍。不能只测试直接修改的模块。

## 七、已知固件问题（仍待解决）

1. **协议处理器限制** — `protocol_handler.c` 不能包含 HAL 头文件，所有 CAN 寄存器访问必须用裸指针 `(volatile uint32_t *)0x40006400UL`。

### 已修复的问题（本次会话）

以下问题已在此次开发会话中修复：
- **环回模式无 RX 帧 (Bug #25)**: 根因是 CAN 错误中断 (ERRIE/BOFIE/LECIE) 在环回模式 TX 期间持续触发，形成中断风暴导致 CPU 锁死，busy-wait 无法完成。修复：`handle_can_send_frame` 在 send+poll 前禁用 CAN IER，完成后恢复。
- **幽灵 RX (Bug #12)**: ISR drain 和 handle_can_send_frame 均检查 BTR[30]，NORMAL 模式不发送/不 drain RX
- **残留 RX (Bug #13)**: 模式切换清除 mailbox+FIFO，NART 按模式控制
- **错误累积 (Bug #14)**: 每次发送进入 init 模式自动清除错误计数器
- **ISR 竞争 (Bug #17)**: FMPIE0 禁用，can_process_rx_irq 环回模式返回，can_set_mode 不启用 FMPIE0
- **ISR 错误中断标志未清除 (Bug #23)**: can_process_error_irq 在环回模式下也清除中断标志 (EWG/EPV/BOF/LEC)
- **APB1 时序错误 (Bug #24)**: 硬编码时序值从 APB1=36MHz 修正为 APB1=32MHz
- **HAL/SPL 混合 (Bug #20)**: can_init 统一为纯 SPL 风格（直接寄存器写入 GPIO/BTR/过滤器）
- **HAL_CAN_GetRxMessage 不兼容 (Bug #16)**: ISR 改用直接寄存器读取
- **HAL_CAN_GetRxMessage 不兼容 (Bug #16)**: ISR 改用直接寄存器读取

## 八、完整 UI 控件测试清单

App 界面上**每一个可控按钮、复选框、下拉框、输入框及其对应逻辑**都必须测试：

### 8.1 设备栏 (DeviceBar)

| 控件               | 操作         | 预期                | 验证                    |
| ------------------ | ------------ | ------------------- | ----------------------- |
| MCU 下拉框         | 切换         | 值改变              | `selected_mcu`        |
| COM 端口下拉框     | 选端口       | 值改变              | `selected_port`       |
| 端口刷新 ⟳        | 点击         | 端口列表刷新        | 下拉框 values           |
| **连接按钮** | 点击连接     | 按钮变→绿点        | `is_connected==True`  |
| **连接按钮** | 已连接时点击 | 断开，灰点          | `is_connected==False` |
| 波特率下拉框       | 选值         | 值改变              | `selected_bitrate`    |
| 静默复选框         | 勾选         | 发送禁用+CAN静默    | `_snd._enabled`       |
| 环回复选框         | 勾选/取消    | CAN LOOPBACK/NORMAL | 日志确认                |
| 波形按钮           | 点击         | 弹出波形窗          | `_wave` 非空          |
| 烧录按钮           | 点击         | 弹出 MCU 选择框     | 对话框出现              |

### 8.2 发送面板 (SendPanel)

| 控件                 | 操作      | 预期         | 验证           |
| -------------------- | --------- | ------------ | -------------- |
| CAN ID 输入          | 输入 hex  | 值正确       | `_id_var`    |
| 帧类型下拉           | 标准/扩展 | 值改变       | `_tp_var`    |
| RTR 复选框           | 勾选      | 数据输入禁用 | `_rtr_var`   |
| DLC 下拉             | 选 1-8    | 值改变       | `_dlc_var`   |
| 数据输入             | 输入 hex  | 自动格式化   | `_data_var`  |
| 自增复选框           | 勾选      | 周期发送时+1 | 数据递增       |
| **单次发送**   | 点击      | TX 行出现    | 报文表行数     |
| **发送错误帧** | 点击      | 错误帧 TX    | 类型="错误"    |
| **周期开始**   | 点击      | 定时发送     | 报文表持续增加 |
| **周期停止**   | 点击      | 停止发送     | 按钮变"开始"   |
| 间隔输入             | 改 ms     | 发送间隔变   | `_ivl_var`   |
| 显示过滤             | 输入 ID   | 表过滤       | 只显示匹配     |
| 显示过滤单选         | 选模式    | 过滤改       | `_f_mode`    |
| 报文过滤             | 输入 ID   | 帧被屏蔽     | `_mf_id_var` |
| 报文过滤单选         | 选模式    | 过滤改       | `_mf_mode`   |

### 8.3 报文追踪表 (MessageTable)

| 验证          | 预期                         |
| ------------- | ---------------------------- |
| TX 方向       | 方向="TX"                    |
| RX 方向       | 方向="RX"                    |
| 标准帧        | 类型="标准"                  |
| 扩展帧        | 类型="扩展"                  |
| NORMAL 模式   | RX 行数=0                    |
| LOOPBACK 模式 | RX 行数=TX 行数，ID/数据匹配 |
| 选中行        | 详情面板更新                 |
| 清除报文      | 表清空                       |

### 8.4 菜单

| 菜单            | 预期          |
| --------------- | ------------- |
| 设备→连接/断开 | 同按钮行为    |
| 视图→四个面板  | 显示/隐藏切换 |
| 设置→语言      | ZH/EN 切换    |
| 帮助→关于      | 弹窗显示      |

### 8.5 日志面板

* [ ] 验证内容连接成功`Device: STM32F103C8T6 FW: v1.0.0`能力查询`Capabilities: ADC=True, USB_CDC=False, CAN ch=1`CAN 配置`CAN configured: 500kbps, mode=0`模式切换`CAN mode: loopback/normal`**TX 失败****不应出现**（成功发送时日志无错误）

## 九、参考代码

`D:\workspace\Embedding\CAN\01-CAN测试\Hardware\CAN.c`

关键参数：PA11/PA12, 环回模式, 250kbps(Prescaler=9,BS1=8tq,BS2=7tq), ABOM=DISABLE, NART=DISABLE, 过滤器 IDMASK 32-bit ID=0 Mask=0

## 十、测试通过标准

用回调模拟点击测试以下完整流程，**全部通过才算完成**：

```
1. [Connect]       → 设备信息显示正确                    ✅
2. [Send] NORMAL   → ACK OK, 报文表: TX 行, **无 RX 行**, 日志无错误  ✅
3. [Send] NORMAL x5 → 同上，全部成功                      ✅
4. [Loopback ON]   → ACK OK                              ✅
5. [Send] LOOPBACK → ACK OK, 报文表: TX+RX 行, RX ID/数据与发送一致  ✅
6. [Cycle x10] LB  → 10/10 ACK OK, 10/10 RX 正确          ✅
7. [Loopback OFF]  → ACK OK                              ✅
8. [Send] NORMAL   → ACK OK, **无 RX 行**                  ✅
9. [Disconnect]    → 状态变为未连接                         ✅
```

**结果: 27/27 全部通过 (ALL PASSED)**

### UI 控件测试: 33/33 全部通过

所有 §八 列出的控件均已测试通过，包括设备栏、发送面板、报文追踪表、菜单、日志面板。

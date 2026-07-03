# arena

> `dev` 正在进行 1.0 架构重构：React 负责 UI，Tauri 负责桌面窗口与进程桥接，Python 负责摄像头、Freeze 检测、录像、实验时钟和电刺激。旧 LiveFreeze PySide6 客户端暂时保留用于行为对照。

## 1.0 开发预览

```powershell
npm install
npm run dev
```

浏览器预览使用模拟遥测；在 Tauri 中运行时，前端会自动启动 `backend/arena_backend` 并接收真实事件。生产构建需要先安装 Rust：

```powershell
rustup toolchain install stable
npm run tauri dev
```

验证前端与新后端：

```powershell
npm run check
$env:PYTHONPATH="backend"
pixi run python -m pytest backend/tests -q
```

架构和通信契约见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## Legacy PySide6 client

基于 **PySide6 + OpenCV** 的桌面 GUI 视频预览程序。支持本机摄像头枚举、开始/停止预览、截图保存与状态栏显示。

## 获取源码

项目使用 Git submodule 固定 RpiBeh 依赖。首次克隆请使用：

```powershell
git clone --recurse-submodules https://github.com/0794xiaobaozi/dendra-arena.git
cd dendra-arena
```

如果已经普通克隆，再执行：

```powershell
git submodule update --init --recursive
```

## 环境

- [Pixi](https://pixi.sh/latest/installation/)（推荐，无需 Conda）
- Python 3.11、PySide6、OpenCV、NumPy（由 Pixi 管理）

### 使用 Pixi（推荐）

1. **安装 Pixi**（若未安装）：

   ```powershell
   winget install prefix-dev.pixi
   ```

   或见 [Pixi 安装说明](https://pixi.sh/latest/installation/)。

2. **安装依赖并运行**（在项目目录）：

   ```powershell
   .\setup.ps1
   .\run.ps1
   ```

   或直接：

   ```powershell
   pixi install
   pixi run run
   ```

   进入环境后手动运行：

   ```powershell
   pixi shell
   python main.py
   ```

### 使用 pip（可选）

若不想用 Pixi，可用 Python 自带的 venv：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## 打包与迁移到其他电脑

### 生成 Windows 安装包（面向最终用户，推荐）

开发电脑一次性安装 Inno Setup 6：

```powershell
winget install JRSoftware.InnoSetup
```

随后在项目目录执行：

```powershell
.\build_installer.ps1
```

生成文件位于 `installer\Output\LiveFreeze-Setup-0.2.0.exe`。把这一份安装包发给其他电脑即可；目标电脑不需要安装 Python、Pixi、Conda 或项目依赖。安装程序会创建开始菜单入口，可选创建桌面快捷方式，并支持从 Windows“已安装的应用”中卸载。

### 方式一：打包成独立程序（推荐，目标机无需装 Python）

1. **在本机安装 PyInstaller 并打包**（在项目根目录）：

   ```powershell
   pip install pyinstaller
   .\build.ps1
   ```

   或直接：

   ```powershell
   pyinstaller livefreeze.spec
   ```

2. **复制整个文件夹**：将生成的 `dist\livefreeze` 整份复制到 U 盘或网络，到另一台电脑后直接运行其中的 **`livefreeze.exe`**。

3. **目标电脑要求**：
   - Windows 10/11（与打包机同架构，如均为 64 位）
   - 无需安装 Python；若提示缺少运行库，可安装 [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/zh-cn/cpp/windows/latest-supported-vc-redist)
   - 摄像头与 USB 电刺激设备（若使用）需正常连接

打包时已把 `protocols/`、`RpiBeh_repo/`、`shock.py` 一并打进程序，到新电脑后无需再放这些文件。

### 方式二：带源码迁移（目标机装 Python 再运行）

1. 将整个项目文件夹（含 `src/`、`protocols/`、`RpiBeh_repo/`、`main.py`、`shock.py`、`requirements.txt` 等）复制到新电脑。
2. 在新电脑上安装 Python 3.11，然后：

   ```powershell
   pip install -r requirements.txt
   python main.py
   ```

   或使用 Pixi：`pixi install` 后 `pixi run run`。

## 功能

- **三段式工作流**：Setup 完成设备、ROI、方案、目录和刺激器检查；Run 只保留关键状态；Review 汇总实验结果
- **中英双语**：顶部实时切换 English / 中文并记住选择；内置 Noto Sans SC，避免目标电脑中文显示为方框
- **Preflight 安全检查**：摄像头、ROI、保存目录、方案和刺激器状态全部通过后才允许开始实验
- **刺激器安全互锁**：包含刺激事件的方案必须先检测设备并明确 Arm，实验运行时锁定配置
- **实验可追溯性**：每次实验保存 session manifest、协议哈希、摄像头参数、逐帧运动/Freeze 日志和错误记录
- **Review 汇总**：按摄像头显示 Freeze 次数、总时长、占比，并可导出 summary CSV
- **多摄像头**：左侧勾选多台 UVC 摄像头，同时预览、实验、录像与 Freeze 检测
- **自适应画面墙**：1 台单画面、2–4 台双列、更多设备三列排列；点击画面切换当前属性对象
- **分区控制**：全局操作位于顶部，设备位于左侧，当前摄像头参数和全局实验属性位于右侧
- **独立会话**：每台摄像头使用独立采集线程、ROI、Freeze 参数、录像文件和结果 CSV
- **共享实验时钟**：所有摄像头使用同一实验方案和 session 时钟，电刺激事件全局只执行一次
- **开始 / 停止**：独立线程采集，不阻塞 GUI；“全部停止”统一释放所有 `VideoCapture`
- **截图**：保存当前帧到 `~/Pictures/LiveFreeze/`（可配置）
- **状态栏**：显示状态、分辨率、FPS、运动量、Freeze 状态
- **实时 Freeze 检测**：基于 [RpiBeh](https://github.com/NiLab-FDU/RpiBeh) 的 Frame Difference 算法，检测画面静止（freezing），状态栏显示「运动: x.xx」及「Freeze」标识
- **窗口缩放**：中央视频区域随窗口 resize 保持画面比例
- **实验方案**：从 `protocols/*.yml` 自动扫描枚举，选择方案名即可；支持「刷新方案」重新加载

### 实验方案 (YAML)

方案文件放在项目根目录的 **`protocols/`** 下，扩展名为 `.yml` 或 `.yaml`。GUI 启动时会自动扫描该目录，下拉框显示各方案的 `name`，选中所需方案即可。可将 `protocols/` 提交到仓库供团队共用。

- 示例：`protocols/freeze_shock_example.yml`
- 格式说明：见 `protocols/README.md`
- 若无任何 YAML 或解析失败，会使用内置默认方案

## 模块结构

| 模块 | 职责 |
|------|------|
| `MultiCameraWindow` | 多摄像头主窗口：设备列表、自适应画面墙、属性/实验面板、全局事件表 |
| `VideoController` | 协调 Worker 与业务：开始/停止/截图、可选启用 freeze 检测 |
| `VideoCaptureWorker` | 采集线程：OpenCV 读帧，可选 FreezeDetector，signal 回主线程 |
| `freeze_detection` | RpiBeh 帧差算法：`FreezeDetector`、`get_motion_level`，阈值/持续时长可配 |
| `SourceManager` | 视频源枚举（本机摄像头）；可扩展文件/RTSP |
| `ConfigService` | 配置（截图目录、默认源等） |

### RpiBeh 与 Freeze 检测

**实时 freeze 检测** 直接使用 [NiLab-FDU/RpiBeh](https://github.com/NiLab-FDU/RpiBeh) 的现成代码：

- 将 `RpiBeh_repo` 克隆在项目根目录后，`src/rpibeh_adapter.py` 把其加入 `sys.path` 并调用 `client_host.PostDetect.DetectFreezing` 与 `client_host.Utils`。
- 仅提供最小适配：`_MinimalConfig` / `_MinimalController` 实现 DetectFreezing 所需的 `get_detection_threshold_and_dur`、`get_region_of_interest_area`、`get_close_loop_method`，不依赖 RpiBeh 的 GUI 或树莓派。
- `src/freeze_detection` 仅对外暴露 `FreezeDetector`（即 `RpiBehFreezeAdapter`），便于与现有采集/界面对接。

**必须** 在项目根目录保留 `RpiBeh_repo`（即克隆后的 RpiBeh 仓库），否则无法使用 freeze 检测。

## 扩展

- **文件 / RTSP**：在 `SourceManager` 中增加类型与枚举，在 `VideoCaptureWorker` 中根据类型打开 `VideoCapture(path)` 或 `VideoCapture(url)` 即可
- **录像**：在 Worker 或单独线程中根据 `frame_ready` 的帧写入 `VideoWriter`
- **图像处理**：在 Worker 读帧后、发射前做处理，或在主线程收到 QImage 后做离线处理

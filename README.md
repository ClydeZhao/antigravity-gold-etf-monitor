# Antigravity 黄金 ETF 监控器

面向 `518880.SH` 的黄金 ETF 建仓参考工具。当前版本把策略引擎从 GUI 中拆了出来，支持命令行定时运行、状态持久化、失败时停止给出买入建议。

## 现在的结构

- `monitor_core.py`: 纯策略层，负责 GFI、RC、盘前/盘中决策
- `monitor_data.py`: 数据抓取层，负责 Yahoo Finance / FRED / 新浪接口
- `monitor_state.py`: 配置和状态持久化
- `gold_monitor.py`: CLI 入口和可选 GUI
- `tests/`: 关键行为测试

## 修复点

- 缺少关键数据时返回 `NO_DECISION`，不再默认给出买入建议
- 不再硬编码 `ETF 资金趋势=连续增加`
- RC 使用配置文件里的真实仓位和波动假设
- 盘中加仓会检查最近一次买入时间
- CLI 不依赖 `tkinter`，可用于 `cron` / Task Scheduler
- GUI 只在显式执行 `gui` 子命令时加载，并通过队列回传结果，避免线程直接操作 Tk 组件
- 评分中加入了 `518880` 自身的趋势因子，不再只看 COMEX 宏观信号

## 快速开始

如果你只想把 UI 跑起来，不想理解代码，按下面做。

### 第一次运行

1. 进入项目目录：

```bash
cd /Users/ruihao/workspace/antigravity-gold-etf-monitor
```

2. 确认你装了 `uv`：

```bash
uv --version
```

3. 用 `uv` 创建独立 Python 环境，并安装依赖：

```bash
uv venv --python 3.11 .venv311
uv pip install --python .venv311/bin/python -r requirements.txt
```

4. 复制配置文件：

```bash
cp config.example.json config.json
```

5. 启动桌面界面：

```bash
.venv311/bin/python gold_monitor.py gui --config config.json --state state.json
```

### 以后每天只要这一条

以后你只需要先进入项目目录，然后执行这一条：

```bash
cd /Users/ruihao/workspace/antigravity-gold-etf-monitor
.venv311/bin/python gold_monitor.py gui --config config.json --state state.json
```

### 如果你只是想看演示界面

这个模式用的是示例数据，不是实时行情：

```bash
cd /Users/ruihao/workspace/antigravity-gold-etf-monitor
.venv311/bin/python gold_monitor.py gui --offline-demo --config config.json --state state.json
```

### 关闭界面

- 直接点窗口左上角关闭按钮
- 或者在启动它的终端里按 `Ctrl + C`

## 安装说明

这个项目默认用 `uv` 管理环境，不建议直接用系统 Python 执行。

## 配置

编辑 `config.json`：

```json
{
  "portfolio_gold_weight": 0.12,
  "gold_volatility": 0.15,
  "portfolio_volatility": 0.12,
  "min_add_cooldown_days": 3,
  "reports_dir": "reports"
}
```

字段说明：

- `portfolio_gold_weight`: 你的黄金仓位占组合权重
- `gold_volatility`: 你用于风控的黄金年化波动率假设
- `portfolio_volatility`: 组合总波动率假设
- `min_add_cooldown_days`: 距上次买入至少间隔几天才允许回调加仓
- `reports_dir`: 报告输出目录

## 桌面界面

推荐用下面这条启动，而不是直接调用系统 Python：

```bash
.venv311/bin/python gold_monitor.py gui --config config.json --state state.json
```

界面重点：

- 左上是 `GFI 仪表盘`
- 中间是 `今日结论卡`
- 结论卡下方会显示 `执行状态 / 数据状态 / 分析模式` 三个状态块
- 如果当前是 `数据不足 / 禁止执行 / 冷却中`，结论区会额外显示阻断提示
- 右上是 `状态与风控`
- 中部是三个大按钮：`盘前分析`、`盘中监控`、`记录今天买入`
- 右侧可以直接修改参数并保存
- 右侧会显示 `最近报告`，点击即可切换下方预览
- 底部是报告预览和原因拆解卡片

如果当前环境没有 `tkinter`，GUI 无法打开。这不是策略问题，是 Python 图形库没装好。

## 命令行用法

盘前分析：

```bash
.venv311/bin/python gold_monitor.py morning --config config.json --state state.json
```

盘中监控：

```bash
.venv311/bin/python gold_monitor.py intraday --config config.json --state state.json
```

记录最近一次买入时间：

```bash
.venv311/bin/python gold_monitor.py record-buy --state state.json
```

离线演示：

```bash
.venv311/bin/python gold_monitor.py morning --offline-demo --config config.json --state state.json
```

GUI：

```bash
.venv311/bin/python gold_monitor.py gui --config config.json --state state.json
```

## 每天自动运行

推荐直接用系统调度器，而不是把调度逻辑写死在程序里。

macOS / Linux `cron` 示例：

```bash
50 8 * * 1-5 cd /path/to/antigravity-gold-etf-monitor && /path/to/antigravity-gold-etf-monitor/.venv311/bin/python gold_monitor.py morning --config config.json --state state.json >> logs/morning.log 2>&1
30 10,13,14 * * 1-5 cd /path/to/antigravity-gold-etf-monitor && /path/to/antigravity-gold-etf-monitor/.venv311/bin/python gold_monitor.py intraday --config config.json --state state.json >> logs/intraday.log 2>&1
```

这样程序负责“分析和决策”，调度器负责“每天什么时候跑”。职责更清楚，也更稳定。

## 测试

```bash
.venv311/bin/python -m pytest -q
```

## 说明

这仍然是规则引擎，不是经过历史回测验证的 alpha 模型。它适合作为建仓参考和纪律化检查工具，不适合替代研究、回测和最终投资决策。

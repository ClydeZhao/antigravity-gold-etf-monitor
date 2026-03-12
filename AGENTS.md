# AGENTS.md

## 先看这 6 条

1. 只用 `uv` 管理 Python 环境。默认解释器是 `.venv311/bin/python`，不要碰系统 Python。
2. 不能只测 `--offline-demo`。任何会影响用户主流程的改动，都要跑一次真实模式端到端。
3. 关键数据缺失时，必须返回 `NO_DECISION`，不能给偏多默认值。
4. `demo` 和 `live` 必须强区分。演示数据要显眼标注，不能让用户误以为是真实行情。
5. UI 的主操作必须一眼看出“能点”。不要做成像信息卡片的假按钮。
6. 完成前必须给证据：至少跑 `pytest`，必要时补一次 GUI 或 CLI 实跑结果。

## 改数据抓取时

- 先假设外部源会超时、断网、返回空值或脏值。
- 不要依赖单一源。关键字段要有备用源或明确降级路径。
- 报错不要把底层库噪音直接甩给用户；转成界面里可理解的人话提示。
- 如果启用了备用源，要在报告和 UI 里写清楚。

## 改策略时

- `518880` 是目标，不是泛黄金宏观看板。优先保证 ETF 自身趋势和执行可用性。
- 没有回测证据时，不要把规则包装成“已验证有效”的择时模型。
- 风控和冷却期必须读真实配置/状态，不能写死。

## 改 UI 时

- 首屏先回答 3 个问题：现在能不能买，为什么，能不能执行。
- 高风险状态要阻断，不要藏在日志里。
- 报告预览按固定宽度文本处理，优先保留排版，不要随意自动换行。

## 交付前检查

```bash
.venv311/bin/python -m pytest -q
.venv311/bin/python -m py_compile gold_monitor.py monitor_core.py monitor_data.py monitor_state.py monitor_dashboard.py
```

如果改了实时链路，再补一条：

```bash
.venv311/bin/python gold_monitor.py morning --config config.example.json --state state.json
```

# Gold ETF Monitor Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the monitor into a testable, headless-capable system that fails closed on bad data, persists portfolio state, and supports daily monitoring workflows for 518880.

**Architecture:** Extract a pure strategy/data domain layer from the Tkinter script, move runtime settings and state into JSON files, and keep the GUI as an optional shell over the same core services. Add CLI entrypoints for morning analysis, intraday checks, and recording buy actions so the tool can run unattended via schedulers.

**Tech Stack:** Python 3, pytest, requests, yfinance, tkinter (optional GUI)

---

### Task 1: Lock desired strategy behavior with tests

**Files:**
- Create: `tests/test_strategy.py`
- Create: `tests/test_cli.py`
- Test: `tests/test_strategy.py`
- Test: `tests/test_cli.py`

**Step 1: Write the failing tests**

Add tests for:
- missing critical data returns `NO_DECISION` instead of buy
- unknown ETF share trend does not add bullish bias
- RC calculation uses persisted portfolio config values
- intraday add-on requires enough days since last buy
- CLI can run analysis without importing tkinter

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_strategy.py tests/test_cli.py -q`
Expected: FAIL because the new core modules / CLI behaviors do not exist yet

### Task 2: Build pure core modules

**Files:**
- Create: `monitor_core.py`
- Create: `monitor_data.py`
- Create: `monitor_state.py`
- Modify: `gold_monitor.py`
- Test: `tests/test_strategy.py`

**Step 1: Write the minimal implementation**

Add:
- dataclasses for market snapshot, config, and persisted state
- fail-closed scoring that marks degraded data and avoids buy signals on missing critical inputs
- optional share-flow factor with no hardcoded bullish default
- real RC calculation from config
- intraday add-on gating based on recorded last-buy date
- data fetch helpers separated from UI code

**Step 2: Run targeted tests**

Run: `pytest tests/test_strategy.py -q`
Expected: PASS

### Task 3: Add headless CLI and optional GUI shell

**Files:**
- Modify: `gold_monitor.py`
- Test: `tests/test_cli.py`

**Step 1: Write the minimal implementation**

Add:
- `morning`, `intraday`, and `record-buy` CLI subcommands
- optional GUI startup only when tkinter is available
- queue-based GUI logging so background workers do not mutate Tk widgets directly

**Step 2: Run targeted tests**

Run: `pytest tests/test_cli.py -q`
Expected: PASS

### Task 4: Add runtime config, state, and docs

**Files:**
- Create: `config.example.json`
- Modify: `README.md`

**Step 1: Write the minimal implementation**

Document:
- how to set portfolio and schedule settings
- how to run morning / intraday analysis from CLI
- how to record a buy so the 3-day add-on rule is enforced
- how to automate daily runs with cron / Task Scheduler

**Step 2: Verify docs and workflow**

Run: `python gold_monitor.py --help`
Expected: subcommands are shown without GUI import errors

### Task 5: Full verification

**Files:**
- Test: `tests/test_strategy.py`
- Test: `tests/test_cli.py`
- Test: `gold_monitor.py`

**Step 1: Run the full verification suite**

Run: `pytest -q`
Expected: all tests pass

**Step 2: Run CLI smoke checks**

Run: `python gold_monitor.py --help`
Expected: exit 0 with CLI usage output

Run: `python gold_monitor.py morning --offline-demo`
Expected: exit 0 and generates a report with `NO_DECISION` or a scored decision from demo data

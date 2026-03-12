# UI Operator Console Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a non-technical-user-friendly desktop console that surfaces the daily decision, enables one-click actions, and keeps key state visible without reading logs.

**Architecture:** Add a pure dashboard view-model layer that maps strategy results into UI-friendly cards, gauges, alerts, and factor summaries. Keep `gold_monitor.py` as the CLI entrypoint plus Tkinter shell, but move UI display decisions into focused helpers so the interface is testable and the GUI only renders state.

**Tech Stack:** Python 3, Tkinter, pytest, existing monitor core/state modules

---

## Chunk 1: View Model

### Task 1: Define the dashboard state contract

**Files:**
- Create: `tests/test_dashboard.py`
- Create: `monitor_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add tests for:
- high GFI results map to gauge color, action tone, and human-readable summary
- missing critical fields produce a blocking warning banner
- cooldown state shows remaining days and suppresses buy affordance

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard.py -q`
Expected: FAIL because `monitor_dashboard.py` does not exist yet

- [ ] **Step 3: Write minimal implementation**

Create view-model dataclasses and a `build_dashboard_view(...)` helper.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard.py -q`
Expected: PASS

## Chunk 2: GUI Layout

### Task 2: Replace the text-heavy GUI with an operator console

**Files:**
- Modify: `gold_monitor.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Add a minimal regression test that verifies the CLI still exposes `gui`, `morning`, `intraday`, and `record-buy`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -q`
Expected: FAIL if CLI contract breaks during refactor

- [ ] **Step 3: Write minimal implementation**

Implement:
- dashboard header
- large gauge canvas
- decision/risk/state cards
- action buttons
- settings form
- factor cards
- report preview area

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -q`
Expected: PASS

## Chunk 3: Settings and State UX

### Task 3: Make configuration editable from the UI

**Files:**
- Modify: `gold_monitor.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing test**

Add a dashboard/state test that covers the displayed cooldown and portfolio settings labels.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard.py -q`
Expected: FAIL because new UI-facing state is not exposed yet

- [ ] **Step 3: Write minimal implementation**

Add UI fields for:
- gold weight
- gold volatility
- portfolio volatility
- cooldown days
- report directory

Persist via `save_config`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard.py -q`
Expected: PASS

## Chunk 4: Verification

### Task 4: Full verification

**Files:**
- Test: `tests/test_dashboard.py`
- Test: `tests/test_strategy.py`
- Test: `tests/test_cli.py`
- Test: `gold_monitor.py`

- [ ] **Step 1: Run the full test suite**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 2: Run CLI smoke checks**

Run: `python gold_monitor.py --help`
Expected: PASS with subcommands listed

Run: `python -m py_compile gold_monitor.py monitor_core.py monitor_data.py monitor_state.py monitor_dashboard.py`
Expected: PASS

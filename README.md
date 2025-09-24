# Local Windows-first RPA Agent Scaffold

This repository contains a scaffold for a Windows-first local RPA agent. It lays
out the core folders, configuration schema, and runtime primitives requested in
the master prompt while keeping implementations platform-aware so development
can occur on non-Windows hosts.

## Features

- **Typed configuration loader** with pydantic validation for profiles, app
  registry entries, LLM providers, and intent mappings.
- **Profile manager** capable of switching between `safe`, `balanced`, and
  `unrestricted` modes with runtime toggles.
- **Target overlay stub** that exposes the specified hotkeys and gracefully
  degrades on non-Windows hosts.
- **UI click engine** honouring the Invoke → MSAA → BM_CLICK → focus-tap order
  with guardrails against disabled controls.
- **Recipe runner** capable of executing demo steps covering app lifecycle,
  desktop UI interactions, browser actions, assertions, and reporting.
- **Intent watcher** backed by `watchdog` that maps intents to recipes and
  archives processed files.
- **LLM router** abstraction supporting API-first providers with UI fallbacks.
- **State store** stub that exposes market session and cash balance data to
  recipe guards.

## Usage

```bash
python -m agent --dry-run
```

Use `--profile` to switch between automation profiles and `--allow-focus-tap`
to enable the focus-tap fallback for UI clicks.

## Requirements

Install dependencies with:

```bash
pip install -r requirements.txt
```

Playwright, UI automation libraries, and Windows-specific dependencies should
be installed on the target Windows machine before enabling full automation.

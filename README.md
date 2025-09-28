# Local Windows-First RPA Agent

This scaffold provides a Windows-centric automation runner that watches for intents, executes YAML recipes, and exposes helpers for screen automation, OCR-triggered flows, and LLM-assisted hand-offs.

## Key Capabilities

- **Configurable intent catalog** – intents live in `connector.config.yml:intent_map` and map to reusable YAML recipes under `agent/examples/recipes/`.
- **Application lifecycle control** – generic `app.*` recipes (launch, focus, minimize, restore, close, kill) resolve defaults from context so the same intents work across OCR, chat, and file triggers.
- **Browser automation helpers** – stock Chrome recipes for open-home, focus/minimize, restore, refresh quotes, and launching arbitrary URLs.
- **Screen-based triggers** – the OCR scanner looks for `#intent#` markers, parses macro syntax, and fires each command once (deduped via `(intent, args)` cache).
- **Clipboard + LLM handoff** – `context.copy_for_llm` captures state/context and copies it to the clipboard; `context.load_llm_response` ingests an LLM reply and merges it back into the execution context.
- **Chat bridge** – when enabled, inline macros such as `[macro:browser_minimize action_id=203]` are parsed and written to the intents directory.
- **Emergency hotkey** – `ctrl+alt+shift+esc` stops the watcher, chat bridge, OCR thread, and raises an interrupt.

## Installation

```bash
python -m pip install -r requirements.txt
# optional (enables clipboard intents)
python -m pip install pyperclip
```

Required third-party packages include `watchdog` (intent watcher) and `pytesseract`, `pillow`, `mss` (OCR). Install Chrome to match the default browser recipes or update `connector.config.yml` accordingly.

## Running the Agent

```bash
python agent.py
```

Useful flags:

- `--ocr-intents / --no-ocr-intents` – enable or disable the OCR scanner (defaults come from `features.ocr_intents`).
- `--chat-bridge / --no-chat-bridge` – enable or disable the macro-aware REPL (`features.chat_bridge`).
- `--profile {safe|balanced|unrestricted}` – switch automation toggles on startup.
- `--allow-focus-tap` – permit the MSAA focus tap fallback when UI controls reject direct clicks.
- `--dry-run` – skip starting the intent watcher (configuration sanity check).

With OCR enabled, type markers such as:

```
#intent# + 401 + [browser_open_home]
#intent# + 402 + [browser_focus_and_minimize]
#intent# + 403 + [browser_restore]
```

The scanner translates them into standard macros and writes intents to `C:/Automation/intents/`.


## Discovering Intents


- Enter `list intents for browser` (or `[macro:list_intents topic=browser]`) in the chat bridge to view relevant entries.
- Natural language commands that do not match directly now show the top keyword candidates. Optionally wire an LLM callback into `ChatIntentBridge` to translate free-form requests; it receives the intent manifest and returns `{intent, args}` suggestions.

## Intent Catalog

Intent mappings (excerpt):

| Intent                     | Recipe                                | Notes                              |
|----------------------------|---------------------------------------|------------------------------------|
| `browser_open_home`        | `browser.open_home.yml`               | Launch Chrome with default URL     |
| `browser_open_url`         | `browser.open_url.yml`                | Requires `args.url` in context     |
| `app_launch`               | `app.launch.yml`                      | Reads `name`, `preset`, `args`     |
| `app_focus` / `app_minimize` / ... | `app.*.yml` recipes             | Apply to latest or targeted instance |
| `context_copy_for_llm`     | `context.copy_for_llm.yml`            | Copies state/context to clipboard  |
| `context_load_llm_response`| `context.load_llm_response.yml`       | Loads clipboard YAML into context  |
| `ts.web.export_quotes`     | `ts.web.export_quotes.yml`            | Domain-specific example            |

Add or adjust catalog entries by editing `agent/examples/recipes/` and updating `connector.config.yml`.

## Working with the Clipboard Helpers

1. Trigger `context.copy_for_llm` to capture the active context snapshot and copy it to the clipboard.
2. Paste the payload into Cursor/GPT, get the continuation, then copy the response to the clipboard.
3. Trigger `context.load_llm_response` to merge the response back into the recipe context for follow-up intents.

Both steps rely on `pyperclip` (install if you plan to use them).

## Development Notes

- Tests: `python -m pytest`
- Hotkey utilities live in `agent/platform/windows/hotkeys.py` and are unit-tested under `tests/platform/windows/`.
- OCR logic (thread-local screenshot capture, one-shot dedupe) resides in `agent/vision/ocr_intents.py` with coverage in `tests/test_ocr_intents.py`.
- The chat bridge and recipes have dedicated fixtures/tests under `tests/test_chat_bridge.py` and `tests/test_app_recipes.py`.

For detailed intent behavior, inspect the YAML recipes and associated step handlers in `agent/runner/steps.py`.

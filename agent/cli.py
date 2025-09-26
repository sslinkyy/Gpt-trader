"""Entry point for the local RPA agent."""
from __future__ import annotations

import argparse
import logging
import threading

from agent.apps.registry import ApplicationRegistry
from agent.core.config_loader import bootstrap_config
from agent.core.profiles import ProfileManager
from agent.runner.chat_bridge import ChatIntentBridge
from agent.runner.intent_watcher import IntentMapping, IntentWatcher
from agent.runner.steps import RecipeRunner
from agent.state.store import StateStore
from agent.vision import OCRIntentScanner

try:
    from agent.platform.windows.hotkeys import GlobalHotKeyListener
except Exception:  # pragma: no cover - fallback on non-Windows hosts
    GlobalHotKeyListener = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local RPA agent")
    parser.add_argument("--config", default="connector.config.yml", help="Path to connector configuration")
    parser.add_argument("--profile", choices=["safe", "balanced", "unrestricted"], help="Override active profile")
    parser.add_argument("--allow-focus-tap", action="store_true", help="Allow focus-tap fallback in UI engine")
    parser.add_argument("--dry-run", action="store_true", help="Run without starting intent watcher")
    parser.add_argument(
        "--chat-bridge",
        dest="chat_bridge",
        action="store_true",
        help="Enable interactive chat input that emits intent files",
    )
    parser.add_argument(
        "--no-chat-bridge",
        dest="chat_bridge",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--ocr-intents",
        dest="ocr_intents",
        action="store_true",
        help="Continuously scan the screen for *#intent#* markers and emit intents",
    )
    parser.add_argument(
        "--no-ocr-intents",
        dest="ocr_intents",
        action="store_false",
        help=argparse.SUPPRESS,
    )
    parser.set_defaults(chat_bridge=None, ocr_intents=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config = bootstrap_config(args.config)
    profile_manager = ProfileManager.from_config(config)

    if args.profile:
        profile_manager.activate(args.profile)

    toggles = profile_manager.current_toggles()
    LOGGER.info("Active profile: %s", profile_manager.active_profile)
    LOGGER.info("Toggles: %s", toggles)

    apps = ApplicationRegistry.from_schema(config.apps)
    state = StateStore(config.state)
    runner = RecipeRunner(apps=apps, state=state, allow_focus_tap=args.allow_focus_tap)

    features = config.features
    enable_chat_bridge = features.chat_bridge if args.chat_bridge is None else args.chat_bridge
    enable_ocr_intents = features.ocr_intents if args.ocr_intents is None else args.ocr_intents

    mappings: dict[str, IntentMapping] = {}
    for name, spec in config.intent_map.items():
        recipe_name = spec.get("recipe")
        if not recipe_name:
            LOGGER.warning("Intent '%s' missing recipe mapping; skipping", name)
            continue
        recipe_path = (config.recipes.directory / recipe_name).resolve()
        mappings[name] = IntentMapping(recipe=recipe_path)

    if not mappings:
        LOGGER.warning("No intent mappings configured; intent watcher will be idle.")

    if args.dry_run:
        LOGGER.info("Dry-run mode enabled; not starting intent watcher.")
        return 0

    try:
        watcher = IntentWatcher(
            intents_dir=config.intents.directory,
            archive_dir=config.intents.archive_directory,
            mappings=mappings,
            recipe_runner=runner,
        )
    except RuntimeError as exc:
        LOGGER.error("Unable to construct intent watcher: %s", exc)
        return 1

    shutdown_requested = threading.Event()

    bridge: ChatIntentBridge | None = None
    scanner: OCRIntentScanner | None = None
    hotkey_listener = None

    def trigger_shutdown() -> None:
        if shutdown_requested.is_set():
            return
        shutdown_requested.set()
        LOGGER.warning(
            "Emergency shutdown hotkey pressed; initiating shutdown."
        )
        try:
            watcher.stop()
        except Exception:  # pragma: no cover - defensive logging
            LOGGER.exception(
                "Failed to stop intent watcher during emergency shutdown."
            )
        if bridge is not None:
            bridge.stop()
        if scanner is not None:
            scanner.stop()
        try:
            threading.interrupt_main()
        except RuntimeError:  # pragma: no cover - defensive logging
            LOGGER.exception(
                "Failed to interrupt main thread after emergency hotkey."
            )

    if enable_chat_bridge or enable_ocr_intents:
        bridge = ChatIntentBridge(
            intents_dir=config.intents.directory,
            mappings=mappings,
        )

    panic_hotkey = (config.safety.panic_hotkey or "").strip()

    watcher.start()

    if GlobalHotKeyListener is not None and panic_hotkey:
        try:
            hotkey_listener = GlobalHotKeyListener(panic_hotkey, trigger_shutdown)
            hotkey_listener.start()
            LOGGER.info(
                "Emergency shutdown hotkey registered: %s",
                panic_hotkey,
            )
        except Exception as exc:
            LOGGER.error(
                "Unable to register emergency shutdown hotkey '%s': %s",
                panic_hotkey,
                exc,
            )
    elif panic_hotkey:
        LOGGER.warning(
            "Emergency shutdown hotkey '%s' is configured but unavailable on this platform.",
            panic_hotkey,
        )

    try:
        if enable_ocr_intents and bridge is not None:
            try:
                scanner = OCRIntentScanner(chat_bridge=bridge)
                scanner.start()
            except RuntimeError as exc:
                LOGGER.error("Unable to start OCR intent scanner: %s", exc)

        if enable_chat_bridge and bridge is not None:
            bridge.run()
        else:
            watcher._stop_event.wait()
    except KeyboardInterrupt:
        LOGGER.info("Keyboard interrupt received; shutting down.")
    finally:
        if scanner is not None:
            scanner.stop()
        if bridge is not None:
            bridge.stop()
        if hotkey_listener is not None:
            hotkey_listener.stop()
        watcher.stop()

    return 0


__all__ = ["main", "build_arg_parser"]



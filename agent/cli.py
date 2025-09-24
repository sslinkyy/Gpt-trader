"""Entry point for the local RPA agent."""
from __future__ import annotations

import argparse
import logging

from agent.apps.registry import ApplicationRegistry
from agent.core.config_loader import bootstrap_config
from agent.core.profiles import ProfileManager
from agent.runner.intent_watcher import IntentMapping, IntentWatcher
from agent.runner.steps import RecipeRunner
from agent.state.store import StateStore

LOGGER = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local RPA agent")
    parser.add_argument("--config", default="connector.config.yml", help="Path to connector configuration")
    parser.add_argument("--profile", choices=["safe", "balanced", "unrestricted"], help="Override active profile")
    parser.add_argument("--allow-focus-tap", action="store_true", help="Allow focus-tap fallback in UI engine")
    parser.add_argument("--dry-run", action="store_true", help="Run without starting intent watcher")
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

    mappings = {}
    for name, spec in config.intent_map.items():
        recipe_name = spec.get("recipe")
        if not recipe_name:
            LOGGER.warning("Intent '%s' missing recipe mapping; skipping", name)
            continue
        recipe_path = (config.recipes.directory / recipe_name).resolve()
        mappings[name] = IntentMapping(recipe=recipe_path)

    if not mappings:
        LOGGER.warning("No intent mappings configured; intent watcher will be idle.")

    watcher = IntentWatcher(
        intents_dir=config.intents.directory,
        archive_dir=config.intents.archive_directory,
        mappings=mappings,
        recipe_runner=runner,
    )

    if args.dry_run:
        LOGGER.info("Dry-run mode enabled; not starting intent watcher.")
        return 0

    watcher.start()
    try:
        watcher._stop_event.wait()
    except KeyboardInterrupt:
        LOGGER.info("Keyboard interrupt received; shutting down.")
    finally:
        watcher.stop()

    return 0


__all__ = ["main", "build_arg_parser"]

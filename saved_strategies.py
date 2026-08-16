"""
saved_strategies.py

Persistence for custom strategies built via the GUI's CustomStrategyDialog.
Only handles strategies built from `rules` (Trigger/Action pairs) --
exactly what the dialog can produce. `base_buy_override` is deliberately
NOT serialized since the dialog never sets it (that field only exists on
preset #2, "Front-Loaded Contribution", which isn't a saveable custom
strategy).

Storage: a single JSON file next to this script (not the current working
directory -- the app could be launched from anywhere). Lifecycle is
SESSION-ONLY, not persistent across restarts: gui_tk.py's main() deletes
this file when the window closes, so every new session starts with no
saved strategies. This is deliberate -- simpler than building a delete/
manage UI for them. Within a single session, though, saving still means
"survives closing and reopening the Custom Strategy dialog" -- it's only
closing the whole APPLICATION that clears them.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

from strategy import Strategy, Rule, Trigger, Action
from market_events import MarketEvent

# When bundled by PyInstaller, __file__ points into a temporary
# extraction folder (sys._MEIPASS in --onefile mode), not next to the
# actual .exe -- getattr(sys, "frozen", False) is PyInstaller's own
# documented way to detect this at runtime, so the save file ends up
# next to the real executable instead of a folder that's deleted when
# the app closes.
if getattr(sys, "frozen", False):
    _BASE_DIR = Path(sys.executable).resolve().parent
else:
    _BASE_DIR = Path(__file__).resolve().parent

SAVED_STRATEGIES_PATH = _BASE_DIR / "saved_strategies.json"
MAX_SAVED_STRATEGIES = 10


def _trigger_to_dict(trigger: Trigger) -> dict:
    return {
        "type": trigger.type,
        # Stored as the Enum MEMBER NAME (e.g. "CRASH"), not trigger.event.value
        # (the display string "Crash") -- the member name is the stable
        # identifier; the display string is free to be reworded later
        # (as it already has been once in this project) without breaking
        # previously-saved files.
        "event": trigger.event.name if trigger.event is not None else None,
        "streak": trigger.streak,
        "operator": trigger.operator,
        "value": trigger.value,
    }


def _trigger_from_dict(d: dict) -> Trigger:
    return Trigger(
        type=d["type"],
        event=MarketEvent[d["event"]] if d.get("event") else None,
        streak=d.get("streak"),
        operator=d.get("operator"),
        value=d.get("value"),
    )


def _action_to_dict(action: Action) -> dict:
    return {
        "type": action.type,
        "value": action.value,
        "start": action.start,
        "increment": action.increment,
        "cap": action.cap,
    }


def _action_from_dict(d: dict) -> Action:
    return Action(
        type=d["type"],
        value=d.get("value"),
        start=d.get("start", 1.0),
        increment=d.get("increment", 0.0),
        cap=d.get("cap"),
    )


def strategy_to_dict(strategy: Strategy) -> dict:
    return {
        "name": strategy.name,
        "description": strategy.description,
        "rules": [
            {"trigger": _trigger_to_dict(r.trigger), "action": _action_to_dict(r.action)}
            for r in strategy.rules
        ],
    }


def dict_to_strategy(d: dict) -> Strategy:
    rules = [
        Rule(trigger=_trigger_from_dict(r["trigger"]), action=_action_from_dict(r["action"]))
        for r in d.get("rules", [])
    ]
    return Strategy(name=d["name"], description=d.get("description", ""), rules=rules)


def load_saved_strategies(path: Optional[Path] = None) -> List[Strategy]:
    """
    Returns the saved strategies, or an empty list if the file doesn't
    exist yet or can't be read/parsed -- a corrupted or missing save file
    should never prevent the app from starting.
    """
    path = path or SAVED_STRATEGIES_PATH
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [dict_to_strategy(d) for d in data]
    except Exception:
        return []


def save_strategies_to_disk(strategies: List[Strategy], path: Optional[Path] = None) -> None:
    path = path or SAVED_STRATEGIES_PATH
    data = [strategy_to_dict(s) for s in strategies]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

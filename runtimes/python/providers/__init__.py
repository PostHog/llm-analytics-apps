import importlib
import inspect
from pathlib import Path
from .base import BaseProvider


def discover_providers(posthog_client):
    """Auto-discover and instantiate all provider classes in this directory"""
    providers = []
    providers_dir = Path(__file__).parent

    for file in providers_dir.glob("*.py"):
        # Skip special files
        if file.stem in ["__init__", "base"]:
            continue

        try:
            # Import the module
            module = importlib.import_module(f".{file.stem}", package=__package__)

            # Find all BaseProvider subclasses
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseProvider) and obj != BaseProvider:
                    if name in {"LegacyProviderBridge"}:
                        continue
                    # Instantiate and add to providers list
                    try:
                        providers.append(obj(posthog_client))
                    except Exception as e:
                        print(f"Warning: Failed to instantiate provider {name} from {file.name}: {e}", file=__import__('sys').stderr)
        except Exception as e:
            print(f"Warning: Failed to load provider from {file.name}: {e}", file=__import__('sys').stderr)

    if not providers:
        raise RuntimeError("No providers could be loaded. Check error messages above.")

    return providers

import json
import os
from pathlib import Path
import logging

# Try multiple levels up to find the root based on the presence of my_config.json
CONFIG_FILE_NAME = "my_config.json" 
config_data = None

def find_project_root(marker_file=CONFIG_FILE_NAME):
    """Find the project root directory containing the marker file."""
    current_path = Path(__file__).resolve()
    for parent in current_path.parents:
        if (parent / marker_file).exists():
            return parent
    # Fallback if running from root or structure is unexpected
    if (Path.cwd() / marker_file).exists():
        return Path.cwd()
    return None # Or raise an error if config must be found

def load_config() -> dict:
    """Loads the configuration from my_config.json found in the project root."""
    global config_data
    if config_data:
        return config_data

    project_root = find_project_root()
    if not project_root:
        logging.error(f"{CONFIG_FILE_NAME} not found in any parent directory or current directory.")
        raise FileNotFoundError(f"{CONFIG_FILE_NAME} not found.")

    config_path = project_root / CONFIG_FILE_NAME

    try:
        with open(config_path, "r", encoding='utf-8') as f:
            config_data = json.load(f)
            logging.info(f"Configuration loaded successfully from {config_path}")
            # Basic validation
            required_keys = ["google_api_key", "pexels_api_keys", "pixabay_api_keys", "together_api_key"]
            if not all(key in config_data for key in required_keys):
                 logging.warning(f"Some common API keys might be missing in {config_path}")
            return config_data
    except FileNotFoundError: # Should be caught by find_project_root, but as a safeguard
        logging.error(f"Configuration file error: {config_path} not found.")
        raise
    except json.JSONDecodeError:
        logging.error(f"Invalid JSON format in {config_path}.")
        raise ValueError(f"Invalid JSON format in {config_path}.")
    except Exception as e:
        logging.error(f"Failed to load configuration: {e}")
        raise

def get_config(key: str, default=None):
    """Safely get a config value by key."""
    cfg = load_config()
    return cfg.get(key, default)

# --- Specific Key Getters (Optional but convenient) ---

def get_google_api_key() -> str | None:
    return get_config("google_api_key")

def get_together_api_key() -> str | None:
    return get_config("together_api_key")

# Handle list-based keys like Pexels/Pixabay with round-robin
_pexels_requested_count = 0
def get_pexels_api_key() -> str | None:
    api_keys = get_config("pexels_api_keys", [])
    if not api_keys:
        logging.warning("Pexels API keys not found in config.")
        return None
    if isinstance(api_keys, str): # Handle single key case
        return api_keys
    if not isinstance(api_keys, list) or not api_keys:
        logging.warning("Pexels API keys should be a non-empty list or a string.")
        return None

    global _pexels_requested_count
    key = api_keys[_pexels_requested_count % len(api_keys)]
    _pexels_requested_count += 1
    return key

_pixabay_requested_count = 0
def get_pixabay_api_key() -> str | None:
    api_keys = get_config("pixabay_api_keys", [])
    if not api_keys:
        logging.warning("Pixabay API keys not found in config.")
        return None
    if isinstance(api_keys, str):
        return api_keys
    if not isinstance(api_keys, list) or not api_keys:
         logging.warning("Pixabay API keys should be a non-empty list or a string.")
         return None

    global _pixabay_requested_count
    key = api_keys[_pixabay_requested_count % len(api_keys)]
    _pixabay_requested_count += 1
    return key

def get_azure_speech_key() -> str | None:
    return get_config("azure_speech_key")

def get_azure_speech_region() -> str | None:
    return get_config("azure_speech_region")


if __name__ == '__main__':
    # Example usage/test
    logging.basicConfig(level=logging.INFO)
    try:
        cfg = load_config()
        print("Full Config loaded:")
        print(json.dumps(cfg, indent=2))

        print(f"\nGoogle API Key: {'*' * 5 if get_google_api_key() else 'Not Found'}")
        print(f"Together API Key: {'*' * 5 if get_together_api_key() else 'Not Found'}")
        print(f"Pexels Key 1: {'*' * 5 if get_pexels_api_key() else 'Not Found'}")
        print(f"Pexels Key 2: {'*' * 5 if get_pexels_api_key() else 'Not Found'}") # Test round-robin
        print(f"Pixabay Key: {'*' * 5 if get_pixabay_api_key() else 'Not Found'}")
        print(f"Azure Key: {'*' * 5 if get_azure_speech_key() else 'Not Found'}")
        print(f"Azure Region: {get_azure_speech_region() or 'Not Found'}")

    except Exception as e:
        print(f"Error testing config loader: {e}") 
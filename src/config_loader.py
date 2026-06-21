import os
import json

# Absolute path to the root of the project (2 levels up from src/config_loader.py)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_config_path():
    """Returns the absolute path to config.json."""
    return os.path.join(PROJECT_ROOT, "config.json")

def load_config():
    """Loads and returns the configuration dictionary from config.json."""
    config_path = get_config_path()
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

# Global variables ready for import
config = load_config()
RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
ISOLATED_RESULTS_DIR = os.path.join(RESULTS_DIR, "isolated")
DISTRIBUTED_RESULTS_DIR = os.path.join(RESULTS_DIR, "distributed")
OPTIMIZED_RESULTS_DIR = os.path.join(RESULTS_DIR, "optimized")

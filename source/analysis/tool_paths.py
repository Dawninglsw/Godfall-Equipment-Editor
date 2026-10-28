"""Shared path configuration for standalone analysis helpers used by the app."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'local_mod'))
from runtime_paths import game_directory,node_executable

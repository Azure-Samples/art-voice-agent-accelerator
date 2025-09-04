import sys
import os
from pathlib import Path

os.environ["DISABLE_CLOUD_TELEMETRY"] = "true"
# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

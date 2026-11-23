"""Makes `import videoclipper` work from the tests folder (the package lives in scripts/)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

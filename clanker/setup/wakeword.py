"""Wake word training script for 'Hey Clanker'.

Uses openWakeWord to generate synthetic training data and train a
custom .tflite wake word model.  The trained model can then be
deployed to HA's openWakeWord add-on.

Requirements (not part of core Clanker deps):
    pip install openwakeword tensorflow tflite-runtime

Usage::

    python -m clanker.setup.wakeword                # train
    python -m clanker.setup.wakeword --deploy /path/to/ha/share/openwakeword
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

_MODEL_DIR = Path("data/wakeword")
_PHRASE = "hey clanker"


def check_dependencies() -> bool:
    """Verify training dependencies are installed."""
    missing = []
    for pkg in ("openwakeword", "tensorflow"):
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print(f"Install them:  pip install {' '.join(missing)}")
        return False
    return True


def train(output_dir: Path = _MODEL_DIR) -> Path | None:
    """Train a custom wake word model for 'Hey Clanker'.

    This uses openWakeWord's built-in training pipeline which:
    1. Generates synthetic speech samples using TTS
    2. Augments with noise and room impulse responses
    3. Trains a small TFLite model (~50KB)

    Args:
        output_dir: Where to save the trained model.

    Returns:
        Path to the trained .tflite file, or None on failure.
    """
    if not check_dependencies():
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "hey_clanker.tflite"

    print(f"Training wake word model for '{_PHRASE}'...")
    print("This may take 10-30 minutes depending on your hardware.\n")

    try:
        # Use openWakeWord's training API
        from openwakeword.train import train_model  # type: ignore[import-untyped]

        train_model(
            target_phrase=_PHRASE,
            output_path=str(model_path),
            n_samples=3000,
            n_epochs=100,
        )
        print(f"\nModel saved to: {model_path}")
        return model_path
    except ImportError:
        # Fallback: try CLI if API is different
        print("Attempting CLI-based training...")
        try:
            subprocess.run(
                [
                    sys.executable, "-m", "openwakeword.train",
                    "--phrase", _PHRASE,
                    "--output", str(model_path),
                    "--samples", "3000",
                ],
                check=True,
            )
            print(f"\nModel saved to: {model_path}")
            return model_path
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"Training failed: {exc}")
            print("\nManual training:")
            print("  1. git clone https://github.com/dscripka/openWakeWord")
            print("  2. Follow docs/custom_models.md")
            print(f"  3. Use phrase: '{_PHRASE}'")
            return None
    except Exception as exc:
        print(f"Training failed: {exc}")
        return None


def deploy(model_path: Path, ha_wakeword_dir: Path) -> bool:
    """Deploy a trained wake word model to HA's openWakeWord directory.

    Args:
        model_path: Path to the .tflite model.
        ha_wakeword_dir: HA's openWakeWord custom model directory
            (e.g. /share/openwakeword or ~/homeassistant/share/openwakeword).

    Returns:
        True if deployed successfully.
    """
    if not model_path.exists():
        print(f"Model not found: {model_path}")
        return False

    ha_wakeword_dir.mkdir(parents=True, exist_ok=True)
    dest = ha_wakeword_dir / model_path.name
    shutil.copy2(model_path, dest)
    print(f"Deployed to: {dest}")
    print("\nNext steps:")
    print("  1. Restart the openWakeWord add-on in HA")
    print("  2. Go to Settings → Voice Assistants → your pipeline")
    print(f"  3. Select '{_PHRASE}' as the wake word")
    return True


def main() -> None:
    """CLI entry point for wake word training."""
    parser = argparse.ArgumentParser(description="Train 'Hey Clanker' wake word model")
    parser.add_argument(
        "--deploy",
        metavar="DIR",
        help="Deploy trained model to this HA openWakeWord directory",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_MODEL_DIR),
        help=f"Training output directory (default: {_MODEL_DIR})",
    )
    args = parser.parse_args()

    if args.deploy:
        model = Path(args.output_dir) / "hey_clanker.tflite"
        deploy(model, Path(args.deploy))
        return

    model_path = train(output_dir=Path(args.output_dir))
    if model_path:
        print("\nTo deploy to HA:")
        print("  python -m clanker.setup.wakeword --deploy /path/to/ha/share/openwakeword")


if __name__ == "__main__":
    main()

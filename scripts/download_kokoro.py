"""Scarica i modelli Kokoro-82M (onnx) nella cartella models/.

File: kokoro-v1.0.int8.onnx + voices-v1.0.bin
Fonte: release `model-files-v1.0` di thewh1teagle/kokoro-onnx.
Il modello int8 è ~2x più veloce del fp32 su CPU con qualità equivalente.
Idempotente: salta i file già presenti (a meno di --force).
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

RELEASE = "model-files-v1.0"
BASE_URL = f"https://github.com/thewh1teagle/kokoro-onnx/releases/download/{RELEASE}"
# int8 di default (~2x più veloce su CPU); fp32 opzionale con --full.
FILES = ["kokoro-v1.0.int8.onnx", "voices-v1.0.bin"]
FILES_FULL = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]


def download(url: str, dest: Path) -> None:
    print(f"Download {url} -> {dest}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        while chunk := resp.read(1 << 20):
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / 1e6:.1f} / {total / 1e6:.1f} MB", end="", flush=True)
        print()
    tmp.rename(dest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dest",
        default="models",
        help="Cartella di destinazione (default: models/)",
    )
    parser.add_argument("--force", action="store_true", help="Ricarica anche se i file esistono")
    parser.add_argument("--full", action="store_true",
                        help="Scarica il modello fp32 (kokoro-v1.0.onnx) invece dell'int8")
    args = parser.parse_args()

    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES_FULL if args.full else FILES:
        target = dest / name
        if target.exists() and not args.force:
            print(f"Esiste già: {target} (usa --force per ricaricare)")
            continue
        download(f"{BASE_URL}/{name}", target)
    print("Fatto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Create or upload ION's Ed25519 release key without printing private material."""

import argparse
import base64
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

root = Path(__file__).resolve().parents[1]
private_path = root / ".release-private-key.txt"
public_path = root / "assets" / "update-public-key.txt"

parser = argparse.ArgumentParser()
parser.add_argument("--set-github", action="store_true")
args = parser.parse_args()

if private_path.exists():
    private_encoded = private_path.read_text(encoding="ascii").strip()
    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_encoded))
else:
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    private_encoded = base64.b64encode(private_raw).decode()
    private_path.write_text(private_encoded + "\n", encoding="ascii")

public_raw = private_key.public_key().public_bytes(
    serialization.Encoding.Raw,
    serialization.PublicFormat.Raw,
)
public_path.write_text(base64.b64encode(public_raw).decode() + "\n", encoding="ascii")

if args.set_github:
    subprocess.run(
        [
            "gh",
            "secret",
            "set",
            "ION_UPDATE_SIGNING_KEY",
            "--repo",
            "stellarwolf640/EliteLogistics",
            "--body",
            private_encoded,
        ],
        check=True,
    )
    private_path.unlink(missing_ok=True)
    print("GitHub release signing secret configured.")
else:
    print(f"Release key created. Private key remains ignored at {private_path}.")

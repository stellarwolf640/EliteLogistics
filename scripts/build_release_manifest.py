import base64
import hashlib
import json
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

installer = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()
version = sys.argv[3]
private_value = os.environ.get("ION_UPDATE_SIGNING_KEY", "")
if not private_value:
    raise SystemExit("ION_UPDATE_SIGNING_KEY is required")
private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_value))
manifest = {
    "schema_version": 1,
    "version": version,
    "asset": installer.name,
    "size": installer.stat().st_size,
    "sha256": hashlib.sha256(installer.read_bytes()).hexdigest(),
}
content = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
output.mkdir(parents=True, exist_ok=True)
(output / "update-manifest.json").write_bytes(content)
(output / "update-manifest.sig").write_text(
    base64.b64encode(private_key.sign(content)).decode() + "\n", encoding="ascii"
)
(output / "SHA256SUMS.txt").write_text(
    f"{manifest['sha256']}  {installer.name}\n", encoding="ascii"
)

"""Pre-commit guard: starter-pack files in data/seed/ may be added once, never changed.

Fails when a staged change modifies, deletes, or renames a file under data/seed/.
"""

import subprocess
import sys

SEED_DIR = "data/seed/"

staged = subprocess.run(
    ["git", "diff", "--cached", "--name-status", "--", SEED_DIR],
    capture_output=True,
    text=True,
    check=True,
).stdout.splitlines()

changed = [line for line in staged if line and not line.startswith("A")]
if changed:
    print(f"{SEED_DIR} is frozen starter material; these staged changes are not allowed:")
    print("\n".join(f"  {line}" for line in changed))
    print("Put new fixtures in data/inbox/ or data/expected/ instead.")
    sys.exit(1)

"""Reject database exports and credential files before publishing source."""
import subprocess
import sys
from pathlib import PurePosixPath


def risky_path(name):
    path = PurePosixPath(name)
    lowered = name.lower()
    return (
        lowered.endswith((".sql", ".sql.gz", ".dump", ".backup", ".sqlite", ".sqlite3"))
        or ".private-backups" in path.parts
        or (path.name.startswith(".env") and path.name != ".env.example")
    )


def main():
    result = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True)
    blocked = [name for name in result.stdout.decode().split("\0") if name and risky_path(name)]
    if blocked:
        print("Refusing tracked database exports or credential files:")
        for name in blocked:
            print(" -", name)
        return 1
    print("Repository data-file guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

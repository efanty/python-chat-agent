#!/usr/bin/env python3
"""Entrypoint: fix /data permissions, then drop privileges and run CMD."""
import os
import subprocess
import sys

APPUSER_UID = 1000
APPUSER_GID = 1000


def main():
    # Fix ownership of the data volume (may be root-owned from previous deployment)
    try:
        subprocess.run(
            ["chown", "-R", f"{APPUSER_UID}:{APPUSER_GID}", "/data"],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass  # /data may not exist if run outside Docker

    # Drop to appuser and execute the CMD
    if len(sys.argv) < 2:
        print("Usage: entrypoint.py <command> [args...]")
        sys.exit(1)

    os.setgid(APPUSER_GID)
    os.setuid(APPUSER_UID)
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()

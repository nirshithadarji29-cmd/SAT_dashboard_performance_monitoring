"""
Locate the SAT data folder without any machine-specific path in the repo.

Resolution order:

    1. SAT_DATA_ROOT environment variable (explicit override, wins outright)
    2. OneDrive sync folders reported by the OS
    3. Legacy / fallback OneDrive locations in the home directory

Inside each OneDrive root the SAT folder is located by *name pattern*
(default "Monthly_SAT_*"), not by a fixed path, so the folder can live
anywhere in the user's OneDrive and the year can change.
"""

import os
import platform
from pathlib import Path

from config.settings import (
    MAX_SEARCH_DEPTH,
    SAT_DATA_ROOT,
    SAT_FOLDER_PATTERN,
)


def onedrive_roots():
    """
    Return every plausible OneDrive root on this machine, most specific first.
    """

    roots = []

    def add(path):
        if path is None:
            return
        path = Path(path).expanduser()
        if path.is_dir() and path not in roots:
            roots.append(path)

    # ------------------------------------------------------------------
    # Windows: the OneDrive client sets these environment variables itself.
    # ------------------------------------------------------------------
    add(os.getenv("OneDriveCommercial"))
    add(os.getenv("OneDriveConsumer"))
    add(os.getenv("OneDrive"))

    home = Path.home()

    # ------------------------------------------------------------------
    # macOS 12.3+ File Provider location, e.g.
    #   ~/Library/CloudStorage/OneDrive-GlobalDataPLC
    # ------------------------------------------------------------------
    if platform.system() == "Darwin":
        cloud_storage = home / "Library" / "CloudStorage"
        if cloud_storage.is_dir():
            for entry in sorted(cloud_storage.glob("OneDrive*")):
                add(entry)

    # ------------------------------------------------------------------
    # Legacy layout on both Windows and macOS, e.g.
    #   ~/OneDrive - GlobalData PLC
    # On modern macOS this is only a symlink into Library/CloudStorage.
    # ------------------------------------------------------------------
    for entry in sorted(home.glob("OneDrive*")):
        add(entry)

    # ------------------------------------------------------------------
    # macOS sync-client container.
    #
    # ~/Library/CloudStorage is protected by macOS privacy controls (TCC) and
    # raises "Operation not permitted" unless the terminal has been granted
    # Full Disk Access. The sync client keeps a readable copy here, so this
    # is what actually works out of the box:
    #
    #   ~/Library/Group Containers/UBF8T346G9.OneDriveSyncClientSuite/
    #       <Account>.noindex/<Account>/
    # ------------------------------------------------------------------
    if platform.system() == "Darwin":

        containers = (
            home
            / "Library"
            / "Group Containers"
            / "UBF8T346G9.OneDriveSyncClientSuite"
        )

        if containers.is_dir():
            for noindex in sorted(containers.glob("*.noindex")):
                for account in sorted(noindex.glob("OneDrive*")):
                    add(account)

    return roots


def _find_folder(root, pattern, max_depth=MAX_SEARCH_DEPTH):
    """
    Find directories matching `pattern` at increasing depth under `root`.

    Searching depth by depth (rather than rglob) keeps this fast and stops
    it from walking an entire multi-gigabyte OneDrive tree.
    """

    matches = []

    for depth in range(max_depth + 1):

        glob_pattern = "/".join(["*"] * depth + [pattern])

        try:
            found = [p for p in root.glob(glob_pattern) if p.is_dir()]
        except OSError:
            # Permission denied / offline placeholder directory.
            continue

        if found:
            matches.extend(found)
            break

    return sorted(matches)


def resolve_sat_root():
    """
    Return the SAT data folder as a Path, or None if it cannot be found.
    """

    # ------------------------------------------------------------------
    # 1. Explicit override (Jenkins, Docker, network mount, testing)
    # ------------------------------------------------------------------
    if SAT_DATA_ROOT:
        path = Path(SAT_DATA_ROOT).expanduser()
        if path.is_dir():
            return path
        return None

    # ------------------------------------------------------------------
    # 2. Search each OneDrive root for the SAT folder by name
    # ------------------------------------------------------------------
    for root in onedrive_roots():

        matches = _find_folder(root, SAT_FOLDER_PATTERN)

        if matches:
            # Multiple year folders (Monthly_SAT_2026, Monthly_SAT_2027, ...)
            # -> use the latest by name.
            return matches[-1]

    return None


def describe_search():
    """
    Human-readable report of what was searched. Shown to the user when the
    SAT folder cannot be found, so the failure is diagnosable.
    """

    lines = []

    if SAT_DATA_ROOT:
        lines.append(f"SAT_DATA_ROOT is set to: {SAT_DATA_ROOT}")
        lines.append(
            "  -> that directory does not exist or is not a folder."
        )
        return "\n".join(lines)

    lines.append("SAT_DATA_ROOT is not set.")
    lines.append(f"Looking for a folder named: {SAT_FOLDER_PATTERN}")
    lines.append("")

    roots = onedrive_roots()

    if not roots:
        lines.append("No OneDrive folder was found on this machine.")
        lines.append("")
        lines.append("Checked:")
        lines.append("  - $OneDriveCommercial / $OneDriveConsumer / $OneDrive")
        lines.append("  - ~/Library/CloudStorage/OneDrive* (macOS)")
        lines.append("  - ~/OneDrive* (legacy)")
        lines.append("")
        lines.append(
            "Install and sign in to the OneDrive desktop app, or set "
            "SAT_DATA_ROOT to the data folder."
        )
        return "\n".join(lines)

    lines.append("OneDrive roots searched:")

    for root in roots:
        lines.append(f"  - {root}")

    lines.append("")
    lines.append(
        f"No folder matching '{SAT_FOLDER_PATTERN}' was found within "
        f"{MAX_SEARCH_DEPTH} levels of those roots."
    )
    lines.append("")
    lines.append(
        "If the folder was shared with you, open it in OneDrive on the web "
        "and choose 'Add shortcut to My files' so it syncs locally."
    )

    return "\n".join(lines)

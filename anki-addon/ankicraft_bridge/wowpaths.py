"""Locate the World of Warcraft install, flavor folders and SavedVariables."""

from __future__ import annotations

import glob
import os
import re
import sys

ADDON = "AnkiCraft"
DEFAULT_FLAVOR = "_forever_"

_CANDIDATES_MAC = [
    "/Applications/World of Warcraft",
    os.path.expanduser("~/Applications/World of Warcraft"),
]
_CANDIDATES_WIN = [
    r"{drive}:\Program Files (x86)\World of Warcraft",
    r"{drive}:\Program Files\World of Warcraft",
    r"{drive}:\World of Warcraft",
    r"{drive}:\Games\World of Warcraft",
    r"{drive}:\Battle.net\World of Warcraft",
]


def _strip_flavor(path: str) -> str:
    """'...\\World of Warcraft\\_retail_\\' -> '...\\World of Warcraft'."""
    path = path.strip().strip('"').rstrip("\\/")
    m = re.match(r"^(.*)[\\/](_[^\\/]+_)$", path)
    return m.group(1) if m else path


def _windows_registry_roots() -> list[str]:
    """Blizzard's installer records the game folder in the registry
    (usually ...\\World of Warcraft\\_retail_\\)."""
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return []
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Blizzard Entertainment\World of Warcraft"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Blizzard Entertainment\World of Warcraft"),
    ]
    out = []
    for hive, key in keys:
        try:
            with winreg.OpenKey(hive, key) as k:
                value, _ = winreg.QueryValueEx(k, "InstallPath")
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            out.append(_strip_flavor(value))
    return out


def _battlenet_config_roots(appdata: str | None = None) -> list[str]:
    """Battle.net remembers the default install folder in
    %APPDATA%\\Battle.net\\Battle.net.config (JSON)."""
    import json

    appdata = appdata if appdata is not None else os.environ.get("APPDATA", "")
    if not appdata:
        return []
    try:
        with open(os.path.join(appdata, "Battle.net", "Battle.net.config"), encoding="utf-8") as f:
            cfg = json.load(f)
        default = cfg["Client"]["Install"]["DefaultInstallPath"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    if not isinstance(default, str) or not default.strip():
        return []
    return [os.path.join(default.strip(), "World of Warcraft")]


def candidate_roots() -> list[str]:
    if sys.platform == "darwin":
        return list(_CANDIDATES_MAC)
    if sys.platform.startswith("win"):
        found = _windows_registry_roots() + _battlenet_config_roots()
        drives = [d for d in "CDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:\\")]
        return found + [c.format(drive=d) for d in drives for c in _CANDIDATES_WIN]
    home = os.path.expanduser("~")
    return [
        os.path.join(home, "Games/world-of-warcraft/drive_c/Program Files (x86)/World of Warcraft"),
        os.path.join(home, ".wine/drive_c/Program Files (x86)/World of Warcraft"),
    ]


def detect_root() -> str | None:
    for c in candidate_roots():
        if os.path.isdir(c) and flavors(c):
            return c
    return None


def normalize_root(path: str) -> str:
    """Accept whatever folder the user picked inside the WoW install
    (the flavor folder, Interface, AddOns, WTF...) and return the root."""
    path = os.path.normpath(path.strip().strip('"'))
    probe = path
    for _ in range(5):
        if flavors(probe):
            return probe
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return path


def flavors(root: str) -> list[str]:
    """Flavor folders like _retail_, _classic_era_, _forever_."""
    try:
        names = os.listdir(root)
    except OSError:
        return []
    return sorted(
        n
        for n in names
        if n.startswith("_")
        and n.endswith("_")
        and any(os.path.isdir(os.path.join(root, n, sub)) for sub in ("Interface", "WTF"))
    )


def flavor_dir(root: str, flavor: str) -> str:
    return os.path.join(root, flavor)


def addons_dir(root: str, flavor: str) -> str:
    return os.path.join(root, flavor, "Interface", "AddOns")


def savedvariables_files(root: str, flavor: str) -> list[str]:
    base = glob.escape(os.path.join(root, flavor, "WTF", "Account"))
    pattern = os.path.join(base, "*", "SavedVariables", ADDON + ".lua")
    return sorted(glob.glob(pattern))


def addon_installed(root: str, flavor: str) -> bool:
    return os.path.exists(os.path.join(addons_dir(root, flavor), ADDON, ADDON + ".toc"))


def interface_version(root: str, flavor: str, default: str) -> str:
    """Read '## Interface:' from the installed AnkiCraft.toc so the generated
    data addon always matches the client version."""
    toc = os.path.join(addons_dir(root, flavor), ADDON, ADDON + ".toc")
    try:
        with open(toc, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"##\s*Interface:\s*(.+)", line)
                if m:
                    return m.group(1).strip()
    except OSError:
        pass
    return default

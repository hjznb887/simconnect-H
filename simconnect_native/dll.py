"""SimConnect.dll discovery."""
from __future__ import annotations

import os
import re
import sys

from .utils import is_bare_dll_name


def _package_lib_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")


def bundled_simconnect_dll() -> str:
    """内置 SimConnect.dll 路径（simconnect_native/lib/SimConnect.dll）。"""
    return os.path.join(_package_lib_dir(), "SimConnect.dll")


def _frozen_exe_dir_candidates() -> list[str]:
    """便携 exe 同目录 DLL 优先于 PyInstaller 临时解压目录。"""
    if not getattr(sys, "frozen", False):
        return []
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    return [
        os.path.join(exe_dir, "SimConnect.dll"),
        os.path.join(exe_dir, "lib", "SimConnect.dll"),
    ]


def _sdk_candidates() -> list[str]:
    paths: list[str] = [
        r"D:\MSFS SDK\SimConnect SDK\lib\SimConnect.dll",
    ]
    for env_key in ("MSFS_SDK_ROOT", "MSFS_SDK"):
        root = os.environ.get(env_key)
        if root:
            paths.append(os.path.join(root, "SimConnect SDK", "lib", "SimConnect.dll"))
            paths.append(os.path.join(root, "lib", "SimConnect.dll"))

    pf = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    sdk_root = os.path.join(pf, "Microsoft SDKs", "FlightSimulator")
    if os.path.isdir(sdk_root):
        for entry in sorted(os.listdir(sdk_root), reverse=True):
            candidate = os.path.join(sdk_root, entry, "SimConnect.dll")
            if os.path.isfile(candidate):
                paths.append(candidate)

    for extra in (
        os.path.join(
            pf, "Microsoft Flight Simulator SDK", "SimConnect SDK", "lib", "SimConnect.dll",
        ),
        os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            "Microsoft Flight Simulator SDK",
            "SimConnect SDK",
            "lib",
            "SimConnect.dll",
        ),
    ):
        paths.append(extra)
    return paths


def _msfs_game_folders() -> tuple[str, ...]:
    return (
        "MicrosoftFlightSimulator",
        "Microsoft Flight Simulator",
        "Microsoft Flight Simulator 2024",
        "MicrosoftFlightSimulator2024",
    )


def _steam_library_roots() -> list[str]:
    """Steam 库根目录（含 libraryfolders.vdf 中的路径）。"""
    roots: list[str] = []
    seen: set[str] = set()

    def add(root: str) -> None:
        if not root:
            return
        norm = os.path.normcase(os.path.abspath(root))
        if norm in seen or not os.path.isdir(root):
            return
        seen.add(norm)
        roots.append(root)

    for env_key in ("STEAM_LIBRARY", "STEAMLibrary"):
        add(os.environ.get(env_key, ""))

    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    default_steam = os.path.join(pf86, "Steam")
    add(default_steam)

    vdf_path = os.path.join(default_steam, "steamapps", "libraryfolders.vdf")
    if os.path.isfile(vdf_path):
        try:
            with open(vdf_path, encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            for match in re.finditer(r'"path"\s+"([^"]+)"', text):
                add(match.group(1).replace("\\\\", "\\"))
        except OSError:
            pass

    for drive in ("C", "D", "E", "F", "G"):
        add(f"{drive}:\\SteamLibrary")
        add(os.path.join(f"{drive}:\\Program Files (x86)", "Steam"))

    return roots


def _msfs_install_candidates() -> list[str]:
    """MSFS 游戏目录内的 SimConnect.dll（与当前模拟器版本一致，优先于 SDK 可再发行版）。"""
    paths: list[str] = []
    for env_key in ("MSFS_INSTALL_DIR", "MSFS_SIMULATOR_DIR", "STEAM_MSFS_DIR"):
        root = os.environ.get(env_key)
        if root:
            paths.append(os.path.join(root, "SimConnect.dll"))

    for lib_root in _steam_library_roots():
        for folder in _msfs_game_folders():
            paths.append(
                os.path.join(lib_root, "steamapps", "common", folder, "SimConnect.dll")
            )

    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    for package in (
        "Microsoft.Limitless_8wekyb3d8bbwe",
        "Microsoft.FlightSimulator_8wekyb3d8bbwe",
        "Microsoft.LimitlessPreview_8wekyb3d8bbwe",
    ):
        paths.append(
            os.path.join(pf, "WindowsApps", package, "SimConnect.dll"),
        )
    return paths


def iter_simconnect_dll_candidates() -> list[str]:
    """按优先级返回 SimConnect.dll 候选路径（不含重复）。"""
    ordered: list[str] = []

    env_path = os.environ.get("SIMCONNECT_DLL")
    if env_path:
        ordered.append(env_path)

    ordered.extend(_frozen_exe_dir_candidates())
    ordered.extend(_msfs_install_candidates())
    ordered.append(bundled_simconnect_dll())
    ordered.extend(_sdk_candidates())

    seen: set[str] = set()
    unique: list[str] = []
    for path in ordered:
        if not path:
            continue
        norm = os.path.normcase(os.path.abspath(path))
        if norm in seen:
            continue
        seen.add(norm)
        unique.append(path)
    return unique


def find_simconnect_dll() -> str:
    """查找 SimConnect.dll。

    搜索顺序：
      1. 环境变量 SIMCONNECT_DLL
      2. 便携 exe 同目录 SimConnect.dll（及 lib\\SimConnect.dll）
      3. MSFS 游戏安装目录（Steam / Microsoft Store，与运行中模拟器版本一致）
      4. 包内置 / PyInstaller 临时解压目录（_MEIxxxx，正常行为）
      5. MSFS SDK 安装路径

    不再回退到系统 PATH 中的裸 ``SimConnect.dll``，避免加载 FSX/PySimConnect 旧版。
    """
    for path in iter_simconnect_dll_candidates():
        if os.path.isfile(path):
            return path

    bundled = bundled_simconnect_dll()
    raise FileNotFoundError(
        "未找到 SimConnect.dll。\n"
        f"  请将 MSFS SDK 可再发行版复制到:\n    {bundled}\n"
        "  或在开发机构建前运行: scripts\\copy_simconnect_dll.ps1\n"
        "  或设置环境变量 SIMCONNECT_DLL=完整路径\\SimConnect.dll"
    )


def is_untrusted_simconnect_dll(path: str) -> bool:
    """便携/下载目录中的 SimConnect.dll 常为误拷贝的旧版。"""
    if not path or is_bare_dll_name(path):
        return False
    norm = os.path.normcase(os.path.abspath(path))
    # PyInstaller onefile 解压到 Local\\Temp\\_MEIxxxx\\ — 正常内置路径
    if "_mei" in norm:
        return False
    bundled = os.path.normcase(bundled_simconnect_dll())
    if norm == bundled:
        return False
    if norm.endswith(os.path.join("lib", "simconnect.dll")):
        return False
    suspicious = (
        "xwechat",
        "wechat",
        "wxid_",
        "downloads",
        "download",
        "desktop",
    )
    return any(part in norm for part in suspicious)


def describe_simconnect_dll_path(path: str) -> str:
    """说明 DLL 路径来源，便于诊断日志阅读。"""
    if not path:
        return ""
    norm = os.path.normcase(os.path.abspath(path))
    if os.environ.get("SIMCONNECT_DLL") and os.path.normcase(
        os.path.abspath(os.environ["SIMCONNECT_DLL"])
    ) == norm:
        return "来自环境变量 SIMCONNECT_DLL"
    if getattr(sys, "frozen", False):
        exe_dir = os.path.normcase(
            os.path.dirname(os.path.abspath(sys.executable))
        )
        if norm == os.path.normcase(os.path.join(exe_dir, "simconnect.dll")):
            return "来自 exe 同目录 SimConnect.dll"
        if norm == os.path.normcase(os.path.join(exe_dir, "lib", "simconnect.dll")):
            return "来自 exe 同目录 lib\\SimConnect.dll"
        if "_mei" in norm:
            return (
                "来自 exe 内置 DLL（PyInstaller 解压到临时目录 _MEIxxxx，"
                "关闭程序后该目录会删除，属正常现象）"
            )
    bundled = os.path.normcase(bundled_simconnect_dll())
    if norm == bundled:
        return "来自包内置 simconnect_native/lib/SimConnect.dll"
    for folder in _msfs_game_folders():
        needle = os.path.normcase(
            os.path.join("steamapps", "common", folder, "simconnect.dll")
        )
        if norm.endswith(needle):
            return f"来自 MSFS 游戏目录 ({folder})"
    if "windowsapps" in norm and "simconnect.dll" in norm:
        return "来自 Microsoft Store MSFS 安装目录"
    for env_key in ("MSFS_INSTALL_DIR", "MSFS_SIMULATOR_DIR", "STEAM_MSFS_DIR"):
        root = os.environ.get(env_key)
        if root and norm == os.path.normcase(
            os.path.join(os.path.abspath(root), "simconnect.dll")
        ):
            return f"来自环境变量 {env_key}"
    if "microsoft sdks" in norm and "flightsimulator" in norm:
        return "来自 MSFS SDK 安装目录"
    if "simconnect sdk" in norm:
        return "来自 MSFS SDK SimConnect SDK"
    return "来自系统搜索路径"


__all__ = [
    "bundled_simconnect_dll",
    "describe_simconnect_dll_path",
    "find_simconnect_dll",
    "is_untrusted_simconnect_dll",
    "iter_simconnect_dll_candidates",
]

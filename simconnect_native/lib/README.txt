SimConnect.dll（MSFS SDK 可再发行组件）
====================================

本目录用于存放内置的 SimConnect.dll（64 位），供 simconnect-H 优先加载。

获取方式（任选其一）：
  1. 安装 MSFS SDK / SimConnect 可再发行组件后运行:
       scripts\copy_simconnect_dll.ps1
  2. 从 SDK 目录手动复制:
       C:\Program Files (x86)\Microsoft SDKs\FlightSimulator\...\SimConnect.dll
  3. 构建便携包时 build_portable.ps1 会自动尝试复制

许可：SimConnect.dll 属于 Microsoft MSFS SDK 可再发行组件，随连接 MSFS 的
客户端软件一并分发。本库 MIT 许可证仅适用于 Python 源码，不包含该 DLL。

注意：请勿用 FSX/旧版/PySimConnect 自带的 SimConnect.dll 替换此文件。

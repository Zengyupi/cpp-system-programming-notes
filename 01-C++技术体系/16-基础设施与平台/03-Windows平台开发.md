# Windows 平台开发

> 本节目标：讲解 Windows 平台 C++ 开发的核心技术，学完后能够理解 Win32 程序结构与消息机制、掌握 COM 组件模型与 DLL 动态库、熟悉 Windows 线程/同步/IPC 机制、了解 Windows 服务与调试工具链。对应岗位方向：Windows 桌面软件、系统软件、驱动、传统行业、医疗、工控、安全。

## 本章速览

- [1. 开发环境与工具链](#1-开发环境与工具链)
  - [1.1 MSVC 常用编译选项](#11-msvc-常用编译选项)
- [2. Win32 程序结构](#2-win32-程序结构)
  - [2.1 完整窗口程序](#21-完整窗口程序)
  - [2.2 消息机制核心概念](#22-消息机制核心概念)
- [3. Unicode 与字符编码](#3-unicode-与字符编码)
- [4. COM（组件对象模型）](#4-com组件对象模型)
  - [4.1 核心概念](#41-核心概念)
  - [4.2 COM 使用示例](#42-com-使用示例)
  - [4.3 智能指针（避免引用计数泄漏）](#43-智能指针避免引用计数泄漏)
- [5. 动态链接库 DLL](#5-动态链接库-dll)
  - [5.1 DLL 基础](#51-dll-基础)
  - [5.2 导出与导入](#52-导出与导入)
  - [5.3 显式加载](#53-显式加载)
  - [5.4 DLL 常见问题](#54-dll-常见问题)
- [6. Windows 线程与同步](#6-windows-线程与同步)
  - [6.1 线程](#61-线程)
  - [6.2 同步原语对比](#62-同步原语对比)
  - [6.3 线程池](#63-线程池)
- [7. Windows IPC（进程间通信）](#7-windows-ipc进程间通信)
- [8. Windows 服务](#8-windows-服务)
- [9. PE 文件格式](#9-pe-文件格式)
- [10. 现代 Windows UI 框架](#10-现代-windows-ui-框架)
- [11. 调试与诊断](#11-调试与诊断)
- [12. 学习路径](#12-学习路径)
- [13. 快速参考卡片](#13-快速参考卡片)
- [14. 常见问题与坑](#14-常见问题与坑)

---

## 1. 开发环境与工具链

| 工具 | 说明 |
| --- | --- |
| **Visual Studio** | 主流 IDE，集成 MSVC 编译器、调试器、性能分析器 |
| **MSVC** | Microsoft C++ 编译器，`cl.exe`，支持 C++14/17/20 |
| **MinGW-w64** | Windows 上的 GCC 工具链，跨平台项目常用 |
| **Clang/LLVM** | 可在 Windows 上使用，与 MSVC ABI 兼容（clang-cl） |
| **CMake** | 跨平台构建系统，生成 Visual Studio 解决方案 |
| **vcpkg** | Microsoft 开源 C++ 包管理器 |
| **WinDbg** | 内核/用户态调试器，分析 dump、蓝屏 |
| **DUMPBIN** | 查看 PE 文件结构、导入导出表、符号 |
| **Dependency Walker / Dependencies** | 查看 DLL 依赖链 |
| **Process Monitor / Process Explorer** | Sysinternals 工具集，监控文件/注册表/进程 |
| **Event Tracing for Windows (ETW)** | 系统级性能追踪，Windows Performance Recorder |

### 1.1 MSVC 常用编译选项

```bash
cl /EHsc /std:c++17 /O2 /W4 /MD main.cpp /Fe:app.exe
# /EHsc：启用 C++ 异常处理  /std:c++17：C++标准  /O2：优化速度
# /W4：警告等级4  /MD：动态链接 CRT  /Fe：输出文件名
# /Zi：生成调试信息  /LD：编译为 DLL  /c：只编译不链接
```

---

## 2. Win32 程序结构

### 2.1 完整窗口程序

```cpp
#include <windows.h>

// 窗口过程：处理所有窗口消息
LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam) {
    switch (msg) {
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC hdc = BeginPaint(hwnd, &ps);
            RECT rc; GetClientRect(hwnd, &rc);
            DrawText(hdc, L"Hello Win32", -1, &rc, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
            EndPaint(hwnd, &ps);
            return 0;
        }
        case WM_LBUTTONDOWN:
            MessageBox(hwnd, L"鼠标左键点击", L"提示", MB_OK);
            return 0;
        case WM_DESTROY:
            PostQuitMessage(0);   // 发送 WM_QUIT，退出消息循环
            return 0;
    }
    return DefWindowProc(hwnd, msg, wParam, lParam);  // 未处理的消息交给默认过程
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE, LPSTR, int nCmdShow) {
    // 1. 注册窗口类
    const wchar_t* CLASS_NAME = L"MyWindowClass";
    WNDCLASS wc = {};
    wc.lpfnWndProc   = WndProc;
    wc.hInstance     = hInstance;
    wc.lpszClassName = CLASS_NAME;
    wc.hCursor       = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    RegisterClass(&wc);

    // 2. 创建窗口
    HWND hwnd = CreateWindow(CLASS_NAME, L"Win32 示例",
        WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT,
        800, 600, NULL, NULL, hInstance, NULL);
    ShowWindow(hwnd, nCmdShow);
    UpdateWindow(hwnd);

    // 3. 消息循环
    MSG msg;
    while (GetMessage(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);   // 翻译虚拟键为字符消息（WM_CHAR）
        DispatchMessage(&msg);    // 分发到 WndProc
    }
    return (int)msg.wParam;
}
```

### 2.2 消息机制核心概念

| 概念 | 说明 |
| --- | --- |
| **消息队列** | 每个 GUI 线程有一个消息队列，`GetMessage` 从中取消息 |
| **窗口过程 WndProc** | 处理消息的回调函数，每个窗口类关联一个 |
| **消息循环** | `GetMessage→TranslateMessage→DispatchMessage`，GUI 线程的核心 |
| **自定义消息** | `WM_USER + n`（窗口类私有）、`WM_APP + n`（应用级）、`RegisterWindowMessage`（系统级唯一） |
| **PostMessage** | 异步投递消息到队列，立即返回 |
| **SendMessage** | 同步发送消息，等待处理完成（跨线程需注意死锁） |
| **定时器** | `SetTimer` 周期性发送 WM_TIMER，精度约 15ms |

> **关键规则**：GUI 线程的消息循环必须及时处理消息，**耗时操作不能在 WndProc 中执行**，否则界面卡死（"未响应"）。耗时操作应放到工作线程，通过 `PostMessage` 或 `Invoke` 回 UI 线程更新。

---

## 3. Unicode 与字符编码

Windows 原生使用 **UTF-16（宽字符 `wchar_t`）**，API 分 A（ANSI）和 W（Wide/Unicode）两个版本：

| 窄字符版 | 宽字符版 | 宏（自动选择） |
| --- | --- | --- |
| CreateWindowA | CreateWindowW | CreateWindow |
| MessageBoxA | MessageBoxW | MessageBox |
| `char` / `LPSTR` | `wchar_t` / `LPWSTR` | `TCHAR` / `LPTSTR` |

```cpp
// 现代 Windows 开发应统一使用宽字符版（W 后缀）和 UTF-16
// 字符串字面量加 L 前缀：L"宽字符串"
// 跨平台项目可用 UTF-8，在调用 Win32 API 前用 MultiByteToWideChar 转换
```

**常见坑**：ANSI/Unicode 混用导致 `char`/`wchar_t` 编译错误；`TCHAR` 宏在 UNICODE 未定义时是 `char`，定义后是 `wchar_t`，现代代码直接用 `wchar_t` 和 W 版 API，避免 TCHAR 宏。

---

## 4. COM（组件对象模型）

COM 是 Windows 的二进制级组件标准，允许不同语言（C++/C#/VB）互操作，是 DirectX、Shell、UWP、OLE 等技术的基础。

### 4.1 核心概念

| 概念 | 说明 |
| --- | --- |
| **IUnknown** | 所有 COM 接口的基类：`QueryInterface`（类型转换）、`AddRef`/`Release`（引用计数） |
| **GUID/CLSID/IID** | 128 位全局唯一标识，分别标识组件类和接口 |
| **引用计数** | `AddRef` 增加、`Release` 减少，计数为 0 时销毁对象；**必须配对调用** |
| **HRESULT** | COM 返回值，`S_OK` 成功，`FAILED(hr)` 宏判断失败 |
| **公寓模型 Apartment** | COM 线程模型：STA（单线程公寓，UI 线程）、MTA（多线程公寓） |
| **列集 Marshaling** | 跨公寓/跨进程调用时的参数序列化，COM 自动处理（需注册代理/存根） |

### 4.2 COM 使用示例

```cpp
#include <windows.h>
#include <shobjidl.h>   // IFileDialog

// 初始化 COM（必须在使用任何 COM 接口前调用）
HRESULT hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
if (FAILED(hr)) { /* 处理 */ }

// 创建 COM 组件实例
IFileDialog* pfd = nullptr;
hr = CoCreateInstance(CLSID_FileOpenDialog, NULL, CLSCTX_INPROC_SERVER,
                      IID_PPV_ARGS(&pfd));
if (SUCCEEDED(hr)) {
    pfd->Show(NULL);   // 显示文件打开对话框
    // ... 获取结果 ...
    pfd->Release();    // 必须释放！
}
CoUninitialize();      // 反初始化
```

### 4.3 智能指针（避免引用计数泄漏）

```cpp
#include <wrl/client.h>   // Windows Runtime C++ Template Library
Microsoft::WRL::ComPtr<IFileDialog> pfd;
CoCreateInstance(CLSID_FileOpenDialog, nullptr, CLSCTX_ALL, IID_PPV_ARGS(&pfd));
pfd->Show(NULL);  // 自动 Release，无需手动调用
// 或用 ATL 的 CComPtr：CComPtr<IFileDialog> pfd;
```

---

## 5. 动态链接库 DLL

### 5.1 DLL 基础

| 概念 | 说明 |
| --- | --- |
| **导出 Export** | `__declspec(dllexport)` 或 `.def` 文件，函数/变量/类对外部可见 |
| **导入 Import** | `__declspec(dllimport)`，使用 DLL 导出的符号 |
| **隐式链接** | 编译时链接 `.lib`（导入库），运行时自动加载 DLL |
| **显式链接** | `LoadLibrary` + `GetProcAddress`，运行时动态加载 |
| **DllMain** | DLL 入口点，处理 `DLL_PROCESS_ATTACH`/`DLL_THREAD_ATTACH` 等 |

### 5.2 导出与导入

```cpp
// mylib.h —— 同时被 DLL 编译和使用者包含
#ifdef MYLIB_EXPORTS
#define MYLIB_API __declspec(dllexport)
#else
#define MYLIB_API __declspec(dllimport)
#endif

MYLIB_API int Add(int a, int b);
MYLIB_API class Calculator { public: int Multiply(int a, int b); };
```

```cpp
// mylib.cpp（DLL 项目中定义 MYLIB_EXPORTS 宏）
#include "mylib.h"
int Add(int a, int b) { return a + b; }
int Calculator::Multiply(int a, int b) { return a * b; }
```

### 5.3 显式加载

```cpp
HMODULE h = LoadLibrary(L"mylib.dll");
if (h) {
    using AddFn = int(*)(int, int);
    AddFn fn = (AddFn)GetProcAddress(h, "Add");
    if (fn) { int r = fn(1, 2); }
    FreeLibrary(h);
}
```

### 5.4 DLL 常见问题

| 问题 | 原因/解决 |
| --- | --- |
| **DLL 地狱** | 不同版本 DLL 覆盖，用 Side-by-Side（SxS）+ Manifest 隔离版本 |
| **跨模块释放内存崩溃** | 每个 DLL 有自己的 CRT 堆（/MT 静态链接时），**谁分配谁释放**；统一用 /MD 动态链接 CRT |
| **导出函数名改编** | C++ 函数名被 name mangling，用 `extern "C"` 导出或 .def 文件指定 |
| **依赖缺失** | 用 Dependencies 工具查看依赖链，安装 VC++ Redistributable |
| **DllMain 死锁** | DllMain 中不能调用 LoadLibrary、不能创建线程、不能同步等待 |

---

## 6. Windows 线程与同步

### 6.1 线程

```cpp
// 创建线程
DWORD WINAPI ThreadFunc(LPVOID param) {
    // 线程工作
    return 0;
}
HANDLE hThread = CreateThread(NULL, 0, ThreadFunc, NULL, 0, NULL);
WaitForSingleObject(hThread, INFINITE);  // 等待线程结束
CloseHandle(hThread);

// 现代 C++ 也可用 std::thread（底层调用 CreateThread）
```

### 6.2 同步原语对比

| 原语 | 跨进程 | 特点 | 适用 |
| --- | --- | --- | --- |
| **CRITICAL_SECTION** | 否 | 用户态，快，无内核切换 | 进程内互斥（最常用） |
| **Mutex** | 是 | 内核对象，可命名，可跨进程 | 跨进程互斥、等待多个对象 |
| **Event** | 是 | 内核对象，手动/自动重置 | 事件通知、线程间信号 |
| **Semaphore** | 是 | 内核对象，计数资源 | 限制并发数量、资源池 |
| **SRWLock** | 否 | 轻量读写锁，Vista+ | 读多写少 |
| **Condition Variable** | 否 | 配合 SRWLock，Vista+ | 生产者消费者 |

```cpp
// CRITICAL_SECTION 用法
CRITICAL_SECTION cs;
InitializeCriticalSection(&cs);
EnterCriticalSection(&cs);   // 加锁
// 共享资源操作
LeaveCriticalSection(&cs);   // 解锁
DeleteCriticalSection(&cs);

// Event 用法
HANDLE hEvent = CreateEvent(NULL, FALSE, FALSE, NULL);  // 自动重置
SetEvent(hEvent);     // 触发
WaitForSingleObject(hEvent, INFINITE);  // 等待
```

### 6.3 线程池

Windows 内置线程池（Vista+），避免频繁创建销毁线程：
```cpp
// 提交工作项到线程池
TrySubmitThreadpoolCallback(Callback, param, NULL);
// 或使用 CreateThreadpoolWork 管理
```
C++ 开发者也常用自定义线程池（`std::thread` + 任务队列），更可控。

---

## 7. Windows IPC（进程间通信）

| 方式 | 特点 | 适用 |
| --- | --- | --- |
| **命名管道 Named Pipe** | 双向、可靠、类似 socket，支持跨网络 | 客户端/服务器通信 |
| **匿名管道** | 单向，父子进程 | 进程输出重定向 |
| **共享内存** | `CreateFileMapping` + `MapViewOfFile`，最快 | 大数据量、高性能 |
| **邮件槽 Mailslot** | 单向、不可靠、广播 | 简单消息广播 |
| **COM/DCOM** | 面向对象、跨机器 | 组件互操作 |
| **WM_COPYDATA** | 窗口消息传数据 | 简单 GUI 进程通信 |
| **Socket** | 跨平台 | 网络通信 |

```cpp
// 共享内存示例
HANDLE hMap = CreateFileMapping(INVALID_HANDLE_VALUE, NULL,
    PAGE_READWRITE, 0, 1024 * 1024, L"Global\\MySharedMem");
void* p = MapViewOfFile(hMap, FILE_MAP_ALL_ACCESS, 0, 0, 0);
// p 指向共享内存，多进程可读写（需同步）
UnmapViewOfFile(p);
CloseHandle(hMap);
```

---

## 8. Windows 服务

Windows 服务是后台运行的程序，无需用户登录：
- 用 `CreateService` 注册，`sc.exe` 或服务管理器管理；
- 入口是 `ServiceMain`，控制处理器处理 `SERVICE_CONTROL_STOP` 等；
- 服务运行在 Session 0（隔离），不能直接显示 UI；
- 调试时可用 `--console` 参数以普通程序模式运行。

---

## 9. PE 文件格式

PE（Portable Executable）是 Windows 可执行文件/DLL 的格式：

```text
DOS Header → DOS Stub → PE Signature → COFF Header → Optional Header
  → Section Table → .text(代码) → .data(已初始化数据) → .rdata(只读数据)
  → .reloc(重定位) → .idata(导入表) → .edata(导出表) → .rsrc(资源)
```

- **导入表**：记录依赖的 DLL 和函数，加载时由 Windows 加载器解析；
- **导出表**：DLL 导出的函数/变量；
- **重定位表**：DLL 加载基地址变化时修正地址；
- 用 `DUMPBIN /headers /imports /exports app.exe` 查看。

---

## 10. 现代 Windows UI 框架

| 框架 | 说明 |
| --- | --- |
| **Win32 API** | 底层，完全控制，代码量大 |
| **MFC** | 微软基础类，封装 Win32，遗留项目多 |
| **Qt** | 跨平台 C++ 框架，信号槽，现代桌面开发主流 |
| **wxWidgets** | 跨平台，原生外观 |
| **WinUI 3** | 微软现代 UI 框架，Windows App SDK，C++/C# |
| **UWP** | 通用 Windows 平台，已被 WinUI 3 取代 |
| **WPF/WinForms** | .NET 框架，C# 为主，可 C++/CLI 互操作 |

> C++ 桌面开发推荐：新项目用 **Qt**（跨平台、生态好）或 **WinUI 3**（Windows 原生现代 UI）；维护老项目用 MFC/Win32。

---

## 11. 调试与诊断

| 工具 | 用途 |
| --- | --- |
| **Visual Studio 调试器** | 日常调试，断点、监视、调用栈 |
| **WinDbg** | 高级调试，dump 分析、内核调试、`!analyze -v` |
| **ProcDump** | 崩溃时自动生成 dump |
| **Process Monitor** | 监控文件/注册表/网络/线程事件 |
| **Process Explorer** | 进程/句柄/DLL 查看 |
| **Performance Monitor** | 系统性能计数器 |
| **ETW / WPA** | 事件追踪，性能分析 |
| **Application Verifier** | 检测堆损坏、句柄泄漏、锁问题 |
| **DebugDiag** | 内存泄漏/崩溃分析 |

---

## 12. 学习路径

```text
入门（1~2 月）：Win32 窗口程序 → 消息机制 → GDI 绘图 → 资源文件
  ↓
进阶（2~3 月）：DLL 开发 → COM 基础 → 多线程与同步 → 文件/注册表/网络
  ↓
深入（3~6 月）：PE 格式 → Windows 服务 → 内核驱动入门 → WinDbg 高级调试
```

推荐资源：《Windows 程序设计》(Petzold)、《Windows 核心编程》(Jeffrey Richter)、《深入解析 Windows》、Microsoft Docs(learn.microsoft.com)。

---

## 13. 快速参考卡片

```text
Win32：WinMain + 注册窗口类(WNDCLASS) + CreateWindow + 消息循环(Get/Dispatch)
消息：PostMessage异步 / SendMessage同步；自定义 WM_USER/WM_APP；耗时操作放工作线程
Unicode：原生UTF-16(wchar_t)，用W版API和L""字符串，避免TCHAR宏
COM：IUnknown(QueryInterface/AddRef/Release) + HRESULT + CoInitialize；用ComPtr智能指针
DLL：dllexport/dllimport；隐式链接(.lib) / 显式(LoadLibrary+GetProcAddress)；谁分配谁释放
线程：CreateThread / std::thread；同步用CRITICAL_SECTION(进程内快) / Mutex/Event(跨进程)
IPC：命名管道 / 共享内存(CreateFileMapping最快) / COM / Socket
服务：ServiceMain入口，Session 0隔离，sc.exe管理
PE：DOS头→COFF头→节表→.text/.data/.rdata/.idata；DUMPBIN查看
工具：Visual Studio + WinDbg + ProcMon + Process Explorer + Dependencies
```

## 14. 常见问题与坑

1. **忘记 `Release()` COM 对象**：引用计数泄漏，用 `ComPtr`/`CComPtr` 智能指针。
2. **ANSI/Unicode 混用**：`char`/`wchar_t` 编译错误，统一用宽字符和 W 版 API。
3. **消息处理中执行耗时操作**：界面卡死"未响应"，必须放工作线程，回 UI 用 PostMessage。
4. **DLL 跨模块释放内存崩溃**：各模块 CRT 堆不一致，统一 /MD 动态链接，谁分配谁释放。
5. **句柄泄漏**：`CreateFile`/`CreateThread` 等返回的 HANDLE 必须 `CloseHandle`，长期运行资源耗尽。
6. **DllMain 中做复杂操作**：加载器锁导致死锁，DllMain 只做简单初始化，复杂逻辑延迟到导出函数。
7. **`SendMessage` 跨线程死锁**：目标线程不响应消息时永久等待，用 `SendMessageTimeout` 或 `PostMessage`。
8. **32/64 位指针截断**：`SetWindowLongPtr` 替代 `SetWindowLong`，指针用 `ULONG_PTR` 而非 `DWORD`。
9. **高 DPI 显示模糊**：在 manifest 中声明 Per-Monitor DPI Aware，或调用 `SetProcessDpiAwarenessContext`。
10. **CRT 库不匹配**：Debug 用 /MDd，Release 用 /MD，混用导致链接错误或运行时崩溃。

---

上一篇：《02-低延迟与量化交易.md》　｜　下一篇：《04-P2P与NAT穿透.md》　｜　模块索引：《../README.md》

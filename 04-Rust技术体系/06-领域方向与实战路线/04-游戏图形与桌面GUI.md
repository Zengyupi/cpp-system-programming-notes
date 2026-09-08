# 游戏图形与桌面GUI

> 本节目标：掌握 Rust 在游戏引擎（Bevy ECS）、跨平台图形（wgpu）、即时模式 GUI（egui）、桌面应用框架（Tauri/slint）中的核心概念与最小可运行示例，理解各框架的设计哲学与适用场景，并与 C++ Qt 生态做对照。

## 本章速览

- [1. Bevy：数据驱动的 ECS 游戏引擎](#1-bevy数据驱动的-ecs-游戏引擎)
  - [1.1 ECS 架构核心概念](#11-ecs-架构核心概念)
  - [1.2 最小可运行游戏](#12-最小可运行游戏)
  - [1.3 系统调度与并行](#13-系统调度与并行)
  - [1.4 对照 C++ 游戏引擎](#14-对照-c-游戏引擎)
- [2. wgpu：跨 GPU 抽象层](#2-wgpu跨-gpu-抽象层)
  - [2.1 wgpu 架构与后端](#21-wgpu-架构与后端)
  - [2.2 渲染管线核心概念](#22-渲染管线核心概念)
  - [2.3 最小三角形示例](#23-最小三角形示例)
- [3. egui：即时模式 GUI](#3-egui即时模式-gui)
  - [3.1 即时模式 vs 保留模式](#31-即时模式-vs-保留模式)
  - [3.2 核心 API 与布局](#32-核心-api-与布局)
  - [3.3 集成到 winit/wgpu](#33-集成到-winitwgpu)
- [4. Tauri：Web 前端 + Rust 后端桌面应用](#4-tauriweb-前端--rust-后端桌面应用)
  - [4.1 Tauri 架构与 Electron 对比](#41-tauri-架构与-electron-对比)
  - [4.2 最小应用与命令调用](#42-最小应用与命令调用)
  - [4.3 对照 C++ Qt](#43-对照-c-qt)
- [5. slint：声明式原生 GUI](#5-slint声明式原生-gui)
  - [5.1 slint 语言与组件](#51-slint-语言与组件)
  - [5.2 Rust 后端集成](#52-rust-后端集成)
- [6. 桌面端选型指南](#6-桌面端选型指南)
  - [6.1 各框架对比表](#61-各框架对比表)
  - [6.2 选型决策树](#62-选型决策树)
- [7. 本节小结](#7-本节小结)

---

## 1. Bevy：数据驱动的 ECS 游戏引擎

### 1.1 ECS 架构核心概念

Bevy（以 crates.io 最新稳定版为准）是 Rust 生态最活跃的游戏引擎，核心是 ECS（Entity-Component-System）架构：

- **Entity（实体）**：一个整数 ID，代表游戏世界中的一个对象，本身不包含任何数据
- **Component（组件）**：附加到 Entity 上的数据结构体，如 `Position`、`Velocity`、`Sprite`
- **System（系统）**：操作具有特定组件组合的 Entity 的函数，如 `movement_system` 读取 `Position` + `Velocity` 并更新 `Position`
- **Resource（资源）**：全局单例数据，如 `Time`、`AssetServer`、游戏配置
- **Event（事件）**：系统间通信的消息队列，如 `CollisionEvent`、`GameOverEvent`

ECS 的核心优势：**数据与行为分离**，组件是纯数据（POD），系统是无状态函数，天然支持并行调度（不读写相同组件的系统可并行执行）。

### 1.2 最小可运行游戏

```toml
[package]
name = "bevy-pong"
version = "0.1.0"
edition = "2021"

[dependencies]
bevy = "0.15"
```

```rust
use bevy::prelude::*;

// ---------- 组件 ----------
#[derive(Component)]
struct Paddle { speed: f32 }

#[derive(Component)]
struct Ball { velocity: Vec2 }

// ---------- 系统 ----------
fn setup(mut commands: Commands) {
    commands.spawn(Camera2d);
    commands.spawn((
        Sprite { color: Color::srgb(1.0,1.0,1.0), custom_size: Some(Vec2::new(20.0,100.0)), ..default() },
        Transform::from_xyz(-400.0, 0.0, 0.0),
        Paddle { speed: 500.0 },
    ));
    commands.spawn((
        Sprite { color: Color::srgb(1.0,1.0,1.0), custom_size: Some(Vec2::new(20.0,20.0)), ..default() },
        Transform::from_xyz(0.0, 0.0, 0.0),
        Ball { velocity: Vec2::new(300.0, 200.0) },
    ));
}

fn paddle_movement(time: Res<Time>, input: Res<ButtonInput<KeyCode>>, mut q: Query<(&Paddle, &mut Transform)>) {
    for (paddle, mut t) in q.iter_mut() {
        let mut dir = 0.0;
        if input.pressed(KeyCode::ArrowUp) { dir += 1.0; }
        if input.pressed(KeyCode::ArrowDown) { dir -= 1.0; }
        t.translation.y = (t.translation.y + dir * paddle.speed * time.delta_secs()).clamp(-250.0, 250.0);
    }
}

fn ball_movement(time: Res<Time>, mut q: Query<(&Ball, &mut Transform)>) {
    for (ball, mut t) in q.iter_mut() {
        t.translation.x += ball.velocity.x * time.delta_secs();
        t.translation.y += ball.velocity.y * time.delta_secs();
    }
}

fn main() {
    App::new()
        .add_plugins(DefaultPlugins)
        .add_systems(Startup, setup)
        .add_systems(Update, (paddle_movement, ball_movement))
        .run();
}
```

### 1.3 系统调度与并行

Bevy 的调度器自动分析系统间的数据依赖：

- 两个都只读 `Position` 的系统可以并行
- 一个写 `Position`、一个读 `Position` 的系统自动串行（或用 `Without`/`With` 过滤避免冲突）
- 可以用 `.chain()` 显式指定顺序，或用 `ambiguous_with` 声明允许并行

```rust
app.add_systems(Update, (
    system_a,
    system_b,
    system_c.after(system_a), // system_c 在 system_a 之后
    (system_d, system_e).chain(), // system_d 和 system_e 按顺序执行
));
```

### 1.4 对照 C++ 游戏引擎

C++ 游戏引擎（Unreal、Unity 的 C++ 部分、自研引擎）通常使用面向对象的继承体系：`GameObject` 基类，`Player`、`Enemy` 继承，虚函数实现多态。问题：

- **继承层次深**：`AActor` → `APawn` → `ACharacter` → `APlayerCharacter`，修改基类影响所有子类
- **缓存不友好**：对象在堆上分散分配，遍历时缓存命中率低
- **并发困难**：对象内部状态 + 虚函数调用，难以自动并行
- **内存安全**：对象指针悬挂、`this` 被销毁后调用虚函数

Bevy 的 ECS 用组件组合替代继承，组件是连续存储的 `Vec`（Archetype 布局），系统是纯函数，调度器自动并行。这与 C++ 中 EnTT（ECS 库）的思路一致，但 Bevy 将 ECS 作为引擎核心，且 Rust 的类型系统让组件查询在编译期类型安全。

## 2. wgpu：跨 GPU 抽象层

### 2.1 wgpu 架构与后端

wgpu（以 crates.io 最新稳定版为准）是 Rust 实现的 WebGPU API 原生实现，提供跨平台的 GPU 抽象。后端支持：

- **Vulkan**（Linux/Windows/Android）
- **Metal**（macOS/iOS）
- **DX12**（Windows）
- **OpenGL ES**（ fallback）
- **WebGPU**（浏览器，通过 `web-sys`）

架构分层：`wgpu`（安全 API）→ `wgpu-core`（核心实现）→ `wgpu-hal`（硬件抽象层）→ 各后端原生 API。

对照 C++：wgpu 类似于 Khronos 的 Vulkan 抽象层，但更高层、更安全。C++ 中直接写 Vulkan 需要数百行初始化代码，且容易出错（资源生命周期、同步）。wgpu 用 Rust 的所有权系统管理 GPU 资源，`Drop` 自动释放。

### 2.2 渲染管线核心概念

wgpu 的核心对象：

- **Instance**：wgpu 实例，枚举适配器
- **Adapter**：物理 GPU 句柄
- **Device**：逻辑 GPU 设备，创建资源
- **Queue**：命令提交队列
- **Surface**：窗口表面，用于呈现
- **RenderPipeline**：渲染管线，包含着色器、顶点布局、混合模式等
- **Buffer**：GPU 缓冲区（顶点、索引、Uniform）
- **BindGroup**：资源绑定组，将 Buffer/Texture 绑定到着色器
- **CommandEncoder**：命令编码器，录制 GPU 命令

### 2.3 最小三角形示例

```toml
[package]
name = "wgpu-triangle"
version = "0.1.0"
edition = "2021"

[dependencies]
wgpu = "24"
winit = "0.30"
pollster = "0.4"  # 阻塞等待 async
bytemuck = { version = "1", features = ["derive"] }
```

```rust
use wgpu::include_wgsl;
use winit::{
    event::{Event, WindowEvent},
    event_loop::EventLoop,
    window::WindowBuilder,
};

// 顶点数据，bytemuck 实现零拷贝转换到字节
#[repr(C)]
#[derive(Copy, Clone, Debug, bytemuck::Pod, bytemuck::Zeroable)]
struct Vertex {
    position: [f32; 2],
    color: [f32; 3],
}

const VERTICES: &[Vertex] = &[
    Vertex { position: [0.0, 0.5], color: [1.0, 0.0, 0.0] },
    Vertex { position: [-0.5, -0.5], color: [0.0, 1.0, 0.0] },
    Vertex { position: [0.5, -0.5], color: [0.0, 0.0, 1.0] },
];

struct State {
    surface: wgpu::Surface<'static>,
    device: wgpu::Device,
    queue: wgpu::Queue,
    config: wgpu::SurfaceConfiguration,
    pipeline: wgpu::RenderPipeline,
    vertex_buffer: wgpu::Buffer,
}

impl State {
    async fn new(window: &winit::window::Window) -> Self {
        let instance = wgpu::Instance::default();
        let surface = instance.create_surface(window).unwrap();
        let adapter = instance
            .request_adapter(&wgpu::RequestAdapterOptions {
                power_preference: wgpu::PowerPreference::HighPerformance,
                compatible_surface: Some(&surface),
                force_fallback_adapter: false,
            })
            .await
            .unwrap();

        let (device, queue) = adapter
            .request_device(&wgpu::DeviceDescriptor::default(), None)
            .await
            .unwrap();

        let caps = surface.get_capabilities(&adapter);
        let format = caps.formats[0];
        let config = wgpu::SurfaceConfiguration {
            usage: wgpu::TextureUsages::RENDER_ATTACHMENT,
            format,
            width: window.inner_size().width,
            height: window.inner_size().height,
            present_mode: wgpu::PresentMode::Fifo,
            alpha_mode: caps.alpha_modes[0],
            view_formats: vec![],
            desired_maximum_frame_latency: 2,
        };
        surface.configure(&device, &config);

        // 着色器
        let shader = device.create_shader_module(include_wgsl!("shader.wgsl"));

        // 渲染管线
        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor::default());
        let pipeline = device.create_render_pipeline(&wgpu::RenderPipelineDescriptor {
            label: Some("Render Pipeline"),
            layout: Some(&pipeline_layout),
            vertex: wgpu::VertexState {
                module: &shader,
                entry_point: "vs_main",
                buffers: &[wgpu::VertexBufferLayout {
                    array_stride: std::mem::size_of::<Vertex>() as wgpu::BufferAddress,
                    step_mode: wgpu::VertexStepMode::Vertex,
                    attributes: &wgpu::vertex_attr_array![0 => Float32x2, 1 => Float32x3],
                }],
                compilation_options: Default::default(),
            },
            fragment: Some(wgpu::FragmentState {
                module: &shader,
                entry_point: "fs_main",
                targets: &[Some(wgpu::ColorTargetState {
                    format: config.format,
                    blend: Some(wgpu::BlendState::REPLACE),
                    write_mask: wgpu::ColorWrites::ALL,
                })],
                compilation_options: Default::default(),
            }),
            primitive: wgpu::PrimitiveState::default(),
            depth_stencil: None,
            multisample: wgpu::MultisampleState::default(),
            multiview: None,
            cache: None,
        });

        // 顶点缓冲区
        let vertex_buffer = device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("Vertex Buffer"),
            contents: bytemuck::cast_slice(VERTICES),
            usage: wgpu::BufferUsages::VERTEX,
        });

        State { surface, device, queue, config, pipeline, vertex_buffer }
    }

    fn render(&self) -> Result<(), wgpu::SurfaceError> {
        let output = self.surface.get_current_texture()?;
        let view = output.texture.create_view(&wgpu::TextureViewDescriptor::default());
        let mut encoder = self.device.create_command_encoder(&wgpu::CommandEncoderDescriptor::default());

        {
            let mut render_pass = encoder.begin_render_pass(&wgpu::RenderPassDescriptor {
                label: Some("Render Pass"),
                color_attachments: &[Some(wgpu::RenderPassColorAttachment {
                    view: &view,
                    resolve_target: None,
                    ops: wgpu::Operations {
                        load: wgpu::LoadOp::Clear(wgpu::Color { r: 0.1, g: 0.1, b: 0.1, a: 1.0 }),
                        store: wgpu::StoreOp::Store,
                    },
                })],
                depth_stencil_attachment: None,
                timestamp_writes: None,
                occlusion_query_set: None,
            });

            render_pass.set_pipeline(&self.pipeline);
            render_pass.set_vertex_buffer(0, self.vertex_buffer.slice(..));
            render_pass.draw(0..3, 0..1);
        }

        self.queue.submit(std::iter::once(encoder.finish()));
        output.present();
        Ok(())
    }
}

fn main() {
    let event_loop = EventLoop::new().unwrap();
    let window = WindowBuilder::new().build(&event_loop).unwrap();
    let mut state = pollster::block_on(State::new(&window));

    event_loop.run(move |event, elwt| {
        match event {
            Event::WindowEvent { event: WindowEvent::CloseRequested, .. } => elwt.exit(),
            Event::WindowEvent { event: WindowEvent::Resized(size), .. } => {
                state.config.width = size.width;
                state.config.height = size.height;
                state.surface.configure(&state.device, &state.config);
            }
            Event::AboutToWait => window.request_redraw(),
            Event::WindowEvent { event: WindowEvent::RedrawRequested, .. } => {
                match state.render() {
                    Ok(_) => {}
                    Err(wgpu::SurfaceError::Lost | wgpu::SurfaceError::Outdated) => {
                        state.surface.configure(&state.device, &state.config);
                    }
                    Err(e) => eprintln!("渲染错误: {:?}", e),
                }
            }
            _ => {}
        }
    }).unwrap();
}
```

WGSL 着色器文件 `shader.wgsl`：

```wgsl
struct VertexInput {
    @location(0) position: vec2<f32>,
    @location(1) color: vec3<f32>,
};

struct VertexOutput {
    @builtin(position) clip_position: vec4<f32>,
    @location(0) color: vec3<f32>,
};

@vertex
fn vs_main(in: VertexInput) -> VertexOutput {
    var out: VertexOutput;
    out.clip_position = vec4<f32>(in.position, 0.0, 1.0);
    out.color = in.color;
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    return vec4<f32>(in.color, 1.0);
}
```

## 3. egui：即时模式 GUI

### 3.1 即时模式 vs 保留模式

GUI 框架有两种范式：

- **保留模式（Retained Mode）**：Qt、WinForms、DOM。控件树存储在框架中，修改属性后框架自动重绘。优点：状态管理自动，动画流畅；缺点：控件生命周期复杂，与游戏循环集成困难
- **即时模式（Immediate Mode）**：Dear ImGui、egui。每帧重新构建整个 UI，控件不保存状态，状态由应用持有。优点：简单直接，与游戏循环天然集成，无控件生命周期问题；缺点：每帧重建有开销（但现代 CPU 完全可承受），复杂布局需要手动管理

egui（以 crates.io 最新稳定版为准）是 Rust 最流行的即时模式 GUI 库，可集成到 wgpu、glow、winit 等多种后端。

### 3.2 核心 API 与布局

```rust
use eframe::egui;

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([400.0, 300.0]),
        ..Default::default()
    };

    eframe::run_native(
        "egui 示例",
        options,
        Box::new(|_cc| Box::new(MyApp::default())),
    )
}

#[derive(Default)]
struct MyApp {
    name: String,
    age: u32,
    is_student: bool,
    favorite_color: egui::Color32,
}

impl eframe::App for MyApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("用户信息表单");
            ui.separator();

            ui.horizontal(|ui| {
                ui.label("姓名:");
                ui.text_edit_singleline(&mut self.name);
            });

            ui.add(egui::Slider::new(&mut self.age, 0..=120).text("年龄"));

            ui.checkbox(&mut self.is_student, "是学生");

            ui.horizontal(|ui| {
                ui.label("喜欢的颜色:");
                ui.color_edit_button_srgb(&mut self.favorite_color);
            });

            ui.separator();

            if ui.button("提交").clicked() {
                println!("姓名: {}, 年龄: {}, 学生: {}", self.name, self.age, self.is_student);
            }

            // 调试面板
            egui::Window::new("调试").show(ctx, |ui| {
                ui.label(format!("FPS: {:.1}", ctx.fps()));
                ui.code(format!("{:#?}", self));
            });
        });
    }
}
```

egui 的布局系统：`CentralPanel`、`SidePanel`、`TopBottomPanel`、`Window`、`Area`。内部用 `ui.horizontal()`、`ui.vertical()`、`ui.group()` 组织控件，`ui.with_layout()` 自定义对齐方式。

### 3.3 集成到 winit/wgpu

egui 不依赖特定后端，通过 `egui-winit`（输入处理）+ `egui-wgpu`（渲染）集成到自定义 wgpu 应用：

```rust
// 简化的集成步骤
let egui_state = egui_winit::State::new(ctx.clone(), viewport_id, &window, None, None, None);
let egui_renderer = egui_wgpu::Renderer::new(&device, format, None, 1);

// 每帧：
let raw_input = egui_state.take_egui_input(&window);
let full_output = ctx.run(raw_input, |ctx| {
    egui::CentralPanel::default().show(ctx, |ui| { ui.label("Hello egui!"); });
});

// 处理平台输出（光标、复制粘贴）
egui_state.handle_platform_output(&window, full_output.platform_output);

// 绘制
let triangles = ctx.tessellate(full_output.shapes, full_output.pixels_per_point);
egui_renderer.update_buffers(&device, &queue, &mut encoder, &triangles, &screen_descriptor);
egui_renderer.render(&mut render_pass, &triangles, &screen_descriptor);
```

## 4. Tauri：Web 前端 + Rust 后端桌面应用

### 4.1 Tauri 架构与 Electron 对比

Tauri（以 crates.io 最新稳定版为准）是用 Rust 编写的桌面应用框架，前端使用系统 WebView（Windows 上 WebView2、macOS 上 WKWebView、Linux 上 WebKitGTK），后端是 Rust。

| 维度 | Tauri | Electron |
| --- | --- | --- |
| 后端语言 | Rust | Node.js (C++) |
| 渲染引擎 | 系统 WebView | 内置 Chromium |
| 安装包大小 | 3–10 MB | 80–150 MB |
| 内存占用 | 低（无 Node + Chromium） | 高（每个进程独立 V8） |
| 安全性 | Rust 内存安全 + IPC 白名单 | 需手动配置 contextIsolation |
| 前端技术 | 任意 Web 框架（React/Vue/Svelte） | 任意 Web 框架 |
| 原生能力 | Rust 直接调用系统 API | Node 原生模块（C++） |

Tauri 的核心安全模型：前端 JS 不能直接访问系统 API，必须通过 `invoke()` 调用 Rust 端注册的 `#[tauri::command]` 函数，且命令需在 `tauri.conf.json` 中显式声明权限。

### 4.2 最小应用与命令调用

Rust 后端 `src-tauri/src/main.rs`：

```rust
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::fs;

#[derive(Debug, Serialize, Deserialize)]
struct FileInfo { name: String, size: u64, is_dir: bool }

#[tauri::command]
fn greet(name: &str) -> String { format!("你好, {}! 来自 Rust 后端", name) }

#[tauri::command]
fn list_directory(path: &str) -> Result<Vec<FileInfo>, String> {
    fs::read_dir(path).map_err(|e| e.to_string())?
        .filter_map(|e| e.ok())
        .map(|e| {
            let m = e.metadata().map_err(|e| e.to_string())?;
            Ok(FileInfo { name: e.file_name().to_string_lossy().to_string(), size: m.len(), is_dir: m.is_dir() })
        })
        .collect()
}

#[tauri::command]
async fn heavy_computation(seconds: u64) -> String {
    tokio::time::sleep(std::time::Duration::from_secs(seconds)).await;
    format!("计算完成，耗时 {} 秒", seconds)
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![greet, list_directory, heavy_computation])
        .run(tauri::generate_context!())
        .expect("启动失败");
}
```

前端通过 `window.__TAURI__.invoke('命令名', { 参数 })` 调用 Rust 命令，返回 Promise。`Result<T, E>` 类型的命令在前端自动映射为 resolve/reject，异步命令（`async fn`）不阻塞 UI 线程。前端可使用任意 Web 框架（React/Vue/Svelte），Tauri 提供 `@tauri-apps/api` 封装 invoke、文件系统、窗口管理等 API。

### 4.3 对照 C++ Qt

Qt 是 C++ 桌面开发的事实标准，与 Tauri 的核心差异：

| 维度 | Qt (C++) | Tauri (Rust + Web) |
| --- | --- | --- |
| UI 技术 | QML / Widgets（原生绘制） | HTML/CSS/JS（WebView 渲染） |
| 语言 | C++ + QML | Rust + 任意前端框架 |
| 样式 | QSS（类 CSS 但功能有限） | 完整 CSS + 前端生态 |
| 原生控件 | 原生外观（Widgets） | Web 风格（非原生控件） |
| 跨平台 | 一致体验，需编译各平台 | 一致体验，WebView 差异需处理 |
| 生态 | 成熟（20+ 年），控件丰富 | 前端生态无限，但原生控件少 |
| 学习曲线 | C++ + QML + MOC | Rust + 前端（前端开发者友好） |
| 适用场景 | 工业软件、嵌入式 UI、高性能渲染 | 工具类应用、跨平台桌面、快速原型 |

Tauri 的优势在于前端生态——React/Vue/Svelte 的组件库、CSS 框架、图表库都可以直接使用。Qt 的优势在于原生控件和高性能场景（尤其是 QML + Scene Graph 的渲染性能）。对于 C++ 开发者转向 Rust 桌面开发，Tauri 是最平滑的路径——Rust 后端处理系统逻辑，前端用熟悉的 Web 技术。更深入的 Qt 架构可对照《../../01-C++技术体系/10-桌面GUI开发/01-Qt框架与界面开发.md》。

## 5. slint：声明式原生 GUI

### 5.1 slint 语言与组件

slint（以 crates.io 最新稳定版为准）是 SixtyFPS 团队开发的声明式 GUI 框架，使用自定义的 `.slint` 标记语言描述 UI，编译时生成 Rust/C++/JS 代码。设计目标是 QML 的声明式体验 + 原生性能。

`ui/app.slint`：

```slint
import { Button, HorizontalBox, VerticalBox, LineEdit } from "std-widgets.slint";

export component MainWindow inherits Window {
    width: 400px;
    height: 300px;
    title: "Slint 示例";

    in-out property <string> name <=> name-input.text;
    in-out property <int> count;

    callback button-clicked();

    VerticalBox {
        alignment: center;
        spacing: 20px;

        Text {
            text: "你好, {name}!";
            font-size: 24px;
        }

        name-input := LineEdit {
            placeholder-text: "输入名字";
            width: 200px;
        }

        HorizontalBox {
            spacing: 10px;
            alignment: center;

            Button {
                text: "增加";
                clicked => { count += 1; }
            }

            Button {
                text: "调用 Rust";
                clicked => root.button-clicked();
            }
        }

        Text {
            text: "计数: {count}";
        }
    }
}
```

### 5.2 Rust 后端集成

```rust
// build.rs
fn main() {
    slint_build::compile("ui/app.slint").unwrap();
}
```

```rust
// src/main.rs
slint::include_modules!();

fn main() -> Result<(), slint::PlatformError> {
    let ui = MainWindow::new()?;

    let ui_handle = ui.as_weak();
    ui.on_button_clicked(move || {
        let ui = ui_handle.unwrap();
        let name = ui.get_name();
        println!("Rust 收到: name={}, count={}", name, ui.get_count());
        ui.set_count(ui.get_count() + 10);
    });

    ui.run()
}
```

slint 的优势：UI 描述编译期检查（类型错误、属性不存在在编译时报错）、原生渲染（不依赖 WebView）、跨平台（Windows/macOS/Linux/嵌入式）、同时支持 Rust/C++/JS 后端。劣势：自定义标记语言需要学习，生态不如 Qt/Tauri 成熟。

## 6. 桌面端选型指南

### 6.1 各框架对比表

| 框架 | UI 范式 | 渲染方式 | 二进制大小 | 学习曲线 | 最佳场景 |
| --- | --- | --- | --- | --- | --- |
| Bevy | ECS + 自定义 | wgpu 原生 | 中（5–20MB） | 陡 | 游戏、实时仿真、可视化 |
| egui | 即时模式 | wgpu/glow | 小（3–8MB） | 平缓 | 调试面板、工具、游戏内 UI |
| Tauri | Web 前端 | 系统 WebView | 小（3–10MB） | 平缓（前端友好） | 工具类应用、跨平台桌面 |
| slint | 声明式 | 原生渲染 | 小（3–8MB） | 中等 | 嵌入式 UI、工业软件、原生体验 |
| Qt (C++) | 保留模式 | 原生/QML | 大（20–50MB） | 陡 | 工业软件、嵌入式、高性能 |

### 6.2 选型决策树

```text
需要游戏/实时3D渲染？
├─ 是 → Bevy（ECS 架构 + wgpu）
└─ 否 → 需要原生控件外观？
    ├─ 是 → slint（声明式 + 原生渲染）或 Qt (C++)
    └─ 否 → 团队有前端经验？
        ├─ 是 → Tauri（Web 前端 + Rust 后端）
        └─ 否 → 需要嵌入到现有渲染循环？
            ├─ 是 → egui（即时模式，易集成）
            └─ 否 → egui 或 slint（从轻量开始）
```

## 7. 本节小结

Rust 的图形与 GUI 生态正在快速成熟。Bevy 用 ECS 架构重新定义了游戏引擎的组织方式，数据驱动的系统调度天然支持并行。wgpu 提供了安全的跨 GPU 抽象，用所有权系统管理 Vulkan/Metal/DX12 资源。egui 的即时模式让 GUI 变得简单直接，特别适合工具和调试面板。Tauri 用 Rust 后端 + Web 前端的组合，以极小的二进制和内存占用挑战 Electron，是 C++ Qt 开发者转向 Rust 桌面的最平滑路径。slint 提供了 QML 风格的声明式原生 GUI。选型时根据渲染需求、团队技能、应用场景做决策——游戏选 Bevy，工具选 Tauri/egui，原生体验选 slint。

下一篇是收官篇，将全面对比 Rust 与 C++ 的选型、学习路线和面试题。

---

上一篇：《03-区块链分布式与云原生.md》
下一篇：《05-Rust与C++选型对照及学习路线.md》

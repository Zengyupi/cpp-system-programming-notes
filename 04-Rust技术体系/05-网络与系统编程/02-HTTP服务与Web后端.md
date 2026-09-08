# HTTP服务与Web后端

> 本节目标：掌握 Rust Web 后端的完整技术栈——从 hyper 底层 HTTP 实现到 axum 高阶框架，从 Tower 中间件层到 sqlx 编译期 SQL 校验，建立可与 C++ 后端框架对标的生产级 Web 服务能力。

## 本章速览

- [1. hyper：底层 HTTP 实现](#1-hyper底层-http-实现)
  - [1.1 hyper 架构与 HTTP/1.1、HTTP/2](#11-hyper-架构与-http11http2)
  - [1.2 hyper 服务端与客户端基础](#12-hyper-服务端与客户端基础)
- [2. axum：路由、提取器与中间件](#2-axum路由提取器与中间件)
  - [2.1 路由系统与 Handler 函数](#21-路由系统与-handler-函数)
  - [2.2 提取器（Extractor）体系](#22-提取器extractor体系)
  - [2.3 状态共享与中间件](#23-状态共享与中间件)
- [3. 完整 REST API 示例](#3-完整-rest-api-示例)
  - [3.1 用户 CRUD 服务实现](#31-用户-crud-服务实现)
  - [3.2 错误处理与响应统一](#32-错误处理与响应统一)
- [4. actix-web 与框架对比](#4-actix-web-与框架对比)
  - [4.1 actix-web 架构特点](#41-actix-web-架构特点)
  - [4.2 axum vs actix-web 选型](#42-axum-vs-actix-web-选型)
- [5. WebSocket 实时通信](#5-websocket-实时通信)
  - [5.1 axum WebSocket 升级与消息处理](#51-axum-websocket-升级与消息处理)
  - [5.2 广播与连接管理](#52-广播与连接管理)
- [6. sqlx：编译期校验 SQL 与连接池](#6-sqlx编译期校验-sql-与连接池)
  - [6.1 sqlx 架构与编译期检查](#61-sqlx-架构与编译期检查)
  - [6.2 连接池与事务](#62-连接池与事务)
- [7. Tower 中间件层](#7-tower-中间件层)
  - [7.1 Service trait 与中间件组合](#71-service-trait-与中间件组合)
  - [7.2 常用中间件：超时、限流、追踪](#72-常用中间件超时限流追踪)
- [8. 常见坑与本节小结](#8-常见坑与本节小结)
  - [常见坑](#常见坑)
  - [本节小结](#本节小结)

---

## 1. hyper：底层 HTTP 实现

### 1.1 hyper 架构与 HTTP/1.1、HTTP/2

hyper 是 Rust 生态最底层的 HTTP 库，基于 Tokio 异步运行时，同时支持 HTTP/1.1 和 HTTP/2。axum、actix-web 等高阶框架底层都基于 hyper（或其组件）。hyper 的设计哲学是"只做 HTTP，不做框架"——它提供 HTTP 协议的解析、序列化和连接管理，但不提供路由、提取器等高层抽象。

hyper 的核心组件：

| 组件 | 作用 |
|------|------|
| `hyper::server::Server` | HTTP 服务端，接受连接并分发请求 |
| `hyper::service::service_fn` | 将函数转换为 `Service`，处理单个请求 |
| `hyper::Request<Body>` | HTTP 请求（方法、URI、头、体） |
| `hyper::Response<Body>` | HTTP 响应（状态码、头、体） |
| `hyper::body::Incoming` | 入站 HTTP 消息体（hyper 1.0，0.14 中为 `hyper::Body`） |
| `hyper::Client` | HTTP 客户端 |

hyper 与 C++ 中 `libcurl`（客户端）或 `cpp-httplib`（服务端）的定位类似，但 hyper 是纯异步的，且同时支持 HTTP/2 多路复用。C++ 的 `boost::beast` 是最接近 hyper 的底层 HTTP 库，但 beast 需要手动管理缓冲区和解析状态，hyper 的 API 更高级。

### 1.2 hyper 服务端与客户端基础

```toml
# Cargo.toml
[dependencies]
hyper = { version = "1", features = ["full"] }
tokio = { version = "1", features = ["full"] }
bytes = "1"
http-body-util = "0.1"
```

```rust
use hyper::body::Incoming;
use hyper::{Request, Response, StatusCode};
use hyper::service::service_fn;
use hyper_util::rt::TokioIo;
use http_body_util::Full;
use bytes::Bytes;
use std::convert::Infallible;
use std::net::SocketAddr;
use tokio::net::TcpListener;

async fn handle_request(req: Request<Incoming>) -> Result<Response<Full<Bytes>>, Infallible> {
    let response = match (req.method(), req.uri().path()) {
        (&hyper::Method::GET, "/") => Response::builder()
            .status(StatusCode::OK)
            .body(Full::new(Bytes::from("Hello, hyper!")))
            .unwrap(),
        (&hyper::Method::GET, "/health") => Response::builder()
            .status(StatusCode::OK)
            .body(Full::new(Bytes::from("OK")))
            .unwrap(),
        _ => Response::builder()
            .status(StatusCode::NOT_FOUND)
            .body(Full::new(Bytes::from("404 Not Found")))
            .unwrap(),
    };
    Ok(response)
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let addr: SocketAddr = ([127, 0, 0, 1], 8080).into();
    let listener = TcpListener::bind(addr).await?;
    println!("hyper 服务器监听 {}", addr);

    loop {
        let (stream, _) = listener.accept().await?;
        let io = TokioIo::new(stream);

        tokio::spawn(async move {
            if let Err(e) = hyper::server::conn::http1::Builder::new()
                .serve_connection(io, service_fn(handle_request))
                .await
            {
                eprintln!("连接错误: {}", e);
            }
        });
    }
}
```

hyper 1.0 的 API 更加底层——需要手动接受 TCP 连接、包装为 `TokioIo`、调用 `http1::Builder::serve_connection`。这给了开发者最大的灵活性（如自定义连接管理、TLS、HTTP/2 升级），但日常开发通常使用 axum 等高阶框架。

hyper 客户端示例：

```rust
use http_body_util::BodyExt;
use hyper::Request;

async fn http_get(url: &str) -> Result<String, Box<dyn std::error::Error>> {
    let client = hyper_util::client::legacy::Client::builder(hyper_util::rt::TokioExecutor::new())
        .build_http();

    let resp = client.get(url.parse()?).await?;
    println!("状态码: {}", resp.status());

    // 收集响应体
    let body = resp.into_body().collect().await?.to_bytes();
    Ok(String::from_utf8_lossy(&body).to_string())
}
```

## 2. axum：路由、提取器与中间件

### 2.1 路由系统与 Handler 函数

axum 是基于 hyper 和 Tower 的 Web 框架，由 Tokio 团队维护，是目前 Rust 生态最主流的 Web 框架。axum 的核心设计是"无宏路由"——路由通过方法链定义，而非属性宏，这使得路由系统与 Rust 类型系统深度集成。

```toml
# Cargo.toml
[dependencies]
axum = "0.7"
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tower = "0.4"
tower-http = { version = "0.5", features = ["trace", "cors", "compression"] }
```

```rust
use axum::{
    routing::{get, post, put, delete},
    Router,
    response::Json,
    extract::{Path, Query, State},
    http::StatusCode,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::net::SocketAddr;

#[derive(Serialize, Deserialize)]
struct User {
    id: u64,
    name: String,
    email: String,
}

#[derive(Deserialize)]
struct PageQuery {
    page: Option<u32>,
    size: Option<u32>,
}

// 应用状态（共享不可变状态）
#[derive(Clone)]
struct AppState {
    db: Arc<Database>, // 假设的数据库连接池
}

// Handler 函数：参数即提取器，返回值即响应
async fn list_users(
    State(state): State<AppState>,
    Query(query): Query<PageQuery>,
) -> Json<Vec<User>> {
    let page = query.page.unwrap_or(1);
    let size = query.size.unwrap_or(20);
    let users = state.db.list_users(page, size).await;
    Json(users)
}

async fn get_user(Path(id): Path<u64>) -> Result<Json<User>, StatusCode> {
    // 模拟数据库查询
    if id == 1 {
        Ok(Json(User { id: 1, name: "Alice".into(), email: "alice@example.com".into() }))
    } else {
        Err(StatusCode::NOT_FOUND)
    }
}

async fn create_user(Json(user): Json<User>) -> (StatusCode, Json<User>) {
    // 创建用户，返回 201 Created
    (StatusCode::CREATED, Json(user))
}

#[tokio::main]
async fn main() {
    let state = AppState { db: Arc::new(Database::new()) };

    let app = Router::new()
        .route("/users", get(list_users).post(create_user))
        .route("/users/:id", get(get_user))
        .with_state(state);

    let addr = SocketAddr::from(([127, 0, 0, 1], 8080));
    println!("axum 服务器监听 {}", addr);
    axum::serve(tokio::net::TcpListener::bind(addr).await.unwrap(), app)
        .await
        .unwrap();
}
```

axum 的路由系统支持：路径参数（`:id`）、通配符（`*rest`）、方法级路由（`.get().post()`）、嵌套路由（`.nest("/api", api_router)`）、路由回退（`.fallback(handler)`）。与 C++ 框架（如 Pistache、Drogon）的属性宏路由或手动注册相比，axum 的方法链路由在编译期检查 handler 签名，类型不匹配会编译错误而非运行时错误。

### 2.2 提取器（Extractor）体系

提取器是 axum 的核心创新——handler 函数的参数类型决定了从请求中提取什么数据。axum 内置的提取器：

| 提取器 | 提取内容 | 对应 C++ 概念 |
|--------|----------|---------------|
| `Path<T>` | 路径参数 | 路由参数解析 |
| `Query<T>` | URL 查询参数 | `?key=value` 解析 |
| `Json<T>` | JSON 请求体 | 请求体反序列化 |
| `Form<T>` | 表单请求体 | `application/x-www-form-urlencoded` |
| `State<T>` | 应用状态 | 依赖注入 |
| `Extension<T>` | 扩展数据（中间件注入） | 请求上下文 |
| `HeaderMap` | HTTP 头 | 请求头 map |
| `TypedHeader<T>` | 类型化 HTTP 头 | 类型安全的头访问 |
| `Bytes` | 原始请求体 | 原始字节 |
| `Request` | 完整请求对象 | 整个请求 |

提取器可以组合使用，axum 按参数顺序依次提取。如果某个提取器失败（如 JSON 解析错误），该请求会立即返回错误响应，后续提取器和 handler 不会执行。

```rust
use axum::extract::{Path, Query, Json, State, TypedHeader};
use headers::UserAgent; // 需在 Cargo.toml 添加 headers = "0.4" 依赖
use serde::Deserialize;

#[derive(Deserialize)]
struct CreateOrderRequest {
    product_id: u64,
    quantity: u32,
}

// 组合多个提取器
async fn create_order(
    State(state): State<AppState>,
    Path(user_id): Path<u64>,
    TypedHeader(user_agent): TypedHeader<UserAgent>,
    Json(body): Json<CreateOrderRequest>,
) -> Result<Json<Order>, (StatusCode, String)> {
    if body.quantity == 0 {
        return Err((StatusCode::BAD_REQUEST, "数量不能为 0".into()));
    }

    let order = state.db.create_order(user_id, body.product_id, body.quantity).await
        .map_err(|e| (StatusCode::INTERNAL_SERVER_ERROR, e.to_string()))?;

    Ok(Json(order))
}
```

自定义提取器通过实现 `FromRequest` 或 `FromRequestParts` trait 完成。这与 C++ 中框架的"参数注入"机制类似，但 Rust 的类型系统确保了提取器的类型安全——如果 handler 参数类型不匹配任何提取器，编译期就会报错。

### 2.3 状态共享与中间件

axum 的状态共享通过 `State<T>` 提取器和 `Router::with_state()` 实现。状态类型必须实现 `Clone`（通常内部用 `Arc` 共享），且在路由构建时注入：

```rust
use std::sync::Arc;
use tokio::sync::RwLock;
use std::collections::HashMap;

#[derive(Clone)]
struct AppState {
    // 用 Arc<RwLock<...>> 共享可变状态
    users: Arc<RwLock<HashMap<u64, User>>>,
    // 不可变状态直接 Arc
    config: Arc<Config>,
}

async fn get_user_count(State(state): State<AppState>) -> String {
    let users = state.users.read().await;
    format!("用户总数: {}", users.len())
}
```

中间件通过 `tower::ServiceBuilder` 组合，挂载到 `Router::layer()`：

```rust
use tower::ServiceBuilder;
use tower_http::{
    trace::TraceLayer,
    cors::CorsLayer,
    compression::CompressionLayer,
    timeout::TimeoutLayer,
};
use std::time::Duration;

let app = Router::new()
    .route("/users", get(list_users))
    .layer(
        ServiceBuilder::new()
            .layer(TraceLayer::new_for_http())  // 请求追踪日志
            .layer(CorsLayer::permissive())      // CORS
            .layer(CompressionLayer::new())      // 响应压缩
            .layer(TimeoutLayer::new(Duration::from_secs(30))) // 超时
    );
```

中间件的执行顺序是"洋葱模型"——请求从外到内依次经过各层，响应从内到外依次经过各层。`ServiceBuilder` 中先添加的层在外层。这与 C++ 框架（如 Drogon 的中间件、Node.js Express 的 middleware）的执行模型一致。

## 3. 完整 REST API 示例

### 3.1 用户 CRUD 服务实现

整合路由、提取器、状态、中间件，实现一个完整的用户 CRUD 服务：

```rust
use axum::{
    routing::{get, post, put, delete},
    Router,
    response::Json,
    extract::{Path, State},
    http::StatusCode,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tokio::sync::RwLock;
use std::collections::HashMap;

#[derive(Serialize, Deserialize, Clone)]
pub struct User {
    pub id: u64,
    pub name: String,
    pub email: String,
}

#[derive(Deserialize)]
pub struct CreateUser {
    pub name: String,
    pub email: String,
}

#[derive(Deserialize)]
pub struct UpdateUser {
    pub name: Option<String>,
    pub email: Option<String>,
}

#[derive(Clone)]
pub struct AppState {
    pub users: Arc<RwLock<HashMap<u64, User>>>,
    pub next_id: Arc<RwLock<u64>>,
}

impl AppState {
    pub fn new() -> Self {
        AppState {
            users: Arc::new(RwLock::new(HashMap::new())),
            next_id: Arc::new(RwLock::new(1)),
        }
    }
}

// POST /users
async fn create_user(
    State(state): State<AppState>,
    Json(body): Json<CreateUser>,
) -> (StatusCode, Json<User>) {
    let mut id_guard = state.next_id.write().await;
    let id = *id_guard;
    *id_guard += 1;
    drop(id_guard);

    let user = User { id, name: body.name, email: body.email };
    state.users.write().await.insert(id, user.clone());
    (StatusCode::CREATED, Json(user))
}

// GET /users
async fn list_users(State(state): State<AppState>) -> Json<Vec<User>> {
    let users = state.users.read().await;
    Json(users.values().cloned().collect())
}

// GET /users/:id
async fn get_user(
    State(state): State<AppState>,
    Path(id): Path<u64>,
) -> Result<Json<User>, StatusCode> {
    let users = state.users.read().await;
    users.get(&id)
        .cloned()
        .map(Json)
        .ok_or(StatusCode::NOT_FOUND)
}

// PUT /users/:id
async fn update_user(
    State(state): State<AppState>,
    Path(id): Path<u64>,
    Json(body): Json<UpdateUser>,
) -> Result<Json<User>, StatusCode> {
    let mut users = state.users.write().await;
    let user = users.get_mut(&id).ok_or(StatusCode::NOT_FOUND)?;
    if let Some(name) = body.name { user.name = name; }
    if let Some(email) = body.email { user.email = email; }
    Ok(Json(user.clone()))
}

// DELETE /users/:id
async fn delete_user(
    State(state): State<AppState>,
    Path(id): Path<u64>,
) -> StatusCode {
    let mut users = state.users.write().await;
    if users.remove(&id).is_some() {
        StatusCode::NO_CONTENT
    } else {
        StatusCode::NOT_FOUND
    }
}

pub fn user_router(state: AppState) -> Router {
    Router::new()
        .route("/users", get(list_users).post(create_user))
        .route("/users/:id", get(get_user).put(update_user).delete(delete_user))
        .with_state(state)
}
```

### 3.2 错误处理与响应统一

axum 的错误处理基于"实现了 `IntoResponse` 的类型就是合法响应"的原则。`Result<T, E>` 中只要 `T` 和 `E` 都实现了 `IntoResponse`，就可以作为 handler 返回值。自定义错误类型通过实现 `IntoResponse` 统一错误响应格式：

```rust
use axum::response::{IntoResponse, Response};
use axum::http::StatusCode;
use serde::Serialize;

#[derive(Serialize)]
struct ErrorResponse {
    error: String,
    code: u16,
}

#[derive(Debug)]
enum AppError {
    NotFound(String),
    BadRequest(String),
    Internal(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
            AppError::BadRequest(msg) => (StatusCode::BAD_REQUEST, msg),
            AppError::Internal(msg) => (StatusCode::INTERNAL_SERVER_ERROR, msg),
        };
        let body = Json(ErrorResponse { error: message, code: status.as_u16() });
        (status, body).into_response()
    }
}

// handler 中直接返回 Result
async fn find_user(id: u64) -> Result<Json<User>, AppError> {
    if id == 0 {
        return Err(AppError::BadRequest("无效的用户 ID".into()));
    }
    // ... 查询数据库 ...
    Err(AppError::NotFound(format!("用户 {} 不存在", id)))
}
```

C++ 对照：C++ 框架中错误处理通常通过异常（Drogon）或错误码返回（Pistache），异常无法在 HTTP 层自动转换为 JSON 响应，需要手动 catch 并构造响应。axum 的 `IntoResponse` trait 将"任何类型都可以是响应"的设计做到了极致——错误类型只需实现一个 trait，即可自动序列化为统一格式的 JSON 响应，无需在每个 handler 中手动构造错误响应。

## 4. actix-web 与框架对比

### 4.1 actix-web 架构特点

actix-web 是 Rust 生态另一个主流 Web 框架，基于自研的 `actix` 演员框架和 `actix-rt` 运行时（不是 Tokio）。actix-web 的核心特点：

- **多线程独立运行时**：每个工作线程运行独立的 `actix-rt` 运行时，线程间不共享异步任务，减少了锁竞争。
- **属性宏路由**：使用 `#[get("/path")]` 宏标注 handler，与 axum 的方法链路由不同。
- **App 数据共享**：通过 `web::Data<T>` 共享状态，内部用 `Arc`。
- **性能极高**：在 TechEmpower 基准测试中常年名列前茅。

```rust
use actix_web::{get, post, web, App, HttpResponse, HttpServer, Responder};
use serde::Deserialize;

#[derive(Deserialize)]
struct UserInfo {
    name: String,
}

#[get("/users/{id}")]
async fn get_user(path: web::Path<u64>) -> impl Responder {
    let id = path.into_inner();
    HttpResponse::Ok().json(serde_json::json!({"id": id, "name": "Alice"}))
}

#[post("/users")]
async fn create_user(body: web::Json<UserInfo>) -> impl Responder {
    HttpResponse::Created().json(serde_json::json!({"name": body.name}))
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    HttpServer::new(|| {
        App::new()
            .service(get_user)
            .service(create_user)
    })
    .bind(("127.0.0.1", 8080))?
    .run()
    .await
}
```

### 4.2 axum vs actix-web 选型

| 维度 | axum | actix-web |
|------|------|-----------|
| 运行时 | Tokio（生态最广） | actix-rt（独立） |
| 路由方式 | 方法链（无宏） | 属性宏 |
| 中间件 | Tower `Service`（生态共享） | actix 中间件（独立生态） |
| 提取器 | `FromRequest` trait | `FromRequest` trait（类似但不兼容） |
| 状态共享 | `State<T>` + `with_state` | `web::Data<T>` + `app_data` |
| 性能 | 极高 | 极高（略高） |
| 生态整合 | 与 Tokio/Tower/hyper 无缝 | 独立生态，需注意与 Tokio 混用 |
| 学习曲线 | 平缓（Tokio 知识可复用） | 中等（需了解 actix 模型） |
| 维护活跃度 | Tokio 团队维护 | 社区维护 |

选型建议：如果项目已经在使用 Tokio 生态（tokio、tower、hyper、tonic），优先选 axum，中间件和工具链可以无缝复用。如果追求极致性能且不依赖 Tokio 特定组件，actix-web 是有力竞争者。两者在功能上没有代差，主要差异在生态整合和编程风格。

C++ 对照：C++ Web 框架的选择更多但更分散——Drogon（高性能，基于 epoll）、Pistache（简洁）、Crow（轻量，header-only）、Oat++（全栈）。Rust 的 axum 和 actix-web 占据了绝大多数市场份额，生态集中度远高于 C++，这意味着更容易找到文档、示例和第三方中间件。

## 5. WebSocket 实时通信

### 5.1 axum WebSocket 升级与消息处理

axum 通过 `axum::extract::WebSocketUpgrade` 提取器处理 WebSocket 升级。客户端发送 `Upgrade: websocket` 头时，该提取器自动完成握手，并返回 `WebSocket` 对象用于后续消息收发。

```rust
use axum::{
    extract::ws::{WebSocketUpgrade, WebSocket, Message},
    response::Response,
    routing::get,
    Router,
};
use futures::{sink::SinkExt, stream::StreamExt};

async fn ws_handler(ws: WebSocketUpgrade) -> Response {
    ws.on_upgrade(handle_socket)
}

async fn handle_socket(mut socket: WebSocket) {
    // 发送欢迎消息
    if socket.send(Message::Text("欢迎连接 WebSocket".into())).await.is_err() {
        return;
    }

    // 循环接收消息
    while let Some(Ok(msg)) = socket.recv().await {
        match msg {
            Message::Text(text) => {
                println!("收到文本: {}", text);
                // 回显
                if socket.send(Message::Text(format!("回显: {}", text))).await.is_err() {
                    break;
                }
            }
            Message::Binary(data) => {
                println!("收到二进制: {} 字节", data.len());
            }
            Message::Ping(_) => {
                // axum 自动回复 Pong，无需手动处理
            }
            Message::Pong(_) => {}
            Message::Close(_) => {
                println!("客户端关闭连接");
                break;
            }
        }
    }
}

let app = Router::new().route("/ws", get(ws_handler));
```

`WebSocket` 对象实现了 `Stream<Item = Result<Message>>` 和 `Sink<Message>`，可以用 `futures` crate 的 `StreamExt`/`SinkExt` 方法操作。axum 自动处理 Ping/Pong 心跳和关闭握手，开发者只需关注业务消息。

### 5.2 广播与连接管理

多客户端广播需要维护连接集合，使用 `tokio::sync::broadcast` 或 `tokio::sync::watch` 实现发布订阅：

```rust
use axum::extract::ws::{WebSocketUpgrade, Message};
use axum::{response::Response, routing::get, Router, extract::State};
use futures::{sink::SinkExt, stream::StreamExt};
use std::sync::Arc;
use tokio::sync::{broadcast, RwLock};
use std::collections::HashSet;

#[derive(Clone)]
struct AppState {
    // 广播通道：发送消息给所有订阅者
    tx: broadcast::Sender<String>,
    // 在线用户集合
    online_users: Arc<RwLock<HashSet<String>>>,
}

async fn ws_handler(
    State(state): State<AppState>,
    ws: WebSocketUpgrade,
) -> Response {
    ws.on_upgrade(move |socket| handle_socket(socket, state))
}

async fn handle_socket(socket: WebSocket, state: AppState) {
    // 订阅广播
    let mut rx = state.tx.subscribe();

    // WebSocket 不是 Clone，必须 split 为独立的读写两半
    let (mut writer, mut reader) = socket.split();

    // 任务1：接收客户端消息并广播（持有 reader）
    let mut send_task = tokio::spawn(async move {
        while let Some(Ok(msg)) = reader.recv().await {
            if let Message::Text(text) = msg {
                let _ = state.tx.send(text);
            }
        }
    });

    // 任务2：接收广播并发送给客户端（持有 writer）
    let mut recv_task = tokio::spawn(async move {
        while let Ok(msg) = rx.recv().await {
            if writer.send(Message::Text(msg)).await.is_err() {
                break;
            }
        }
    });

    // 任一任务结束则终止另一个
    tokio::select! {
        _ = (&mut send_task) => recv_task.abort(),
        _ = (&mut recv_task) => send_task.abort(),
    }
}
```

这个模式是 WebSocket 广播的标准实现：每个连接有两个异步任务（收/发），通过 `broadcast` 通道解耦。C++ 中实现同样功能需要手动管理连接列表、加锁、用 `std::function` 回调分发消息，Rust 的 `broadcast` 通道和 `select!` 大幅简化了并发管理。

## 6. sqlx：编译期校验 SQL 与连接池

### 6.1 sqlx 架构与编译期检查

sqlx 是 Rust 生态最主流的异步数据库库，支持 PostgreSQL、MySQL、SQLite、MSSQL。其核心特性是**编译期 SQL 校验**——`sqlx::query!` 宏在编译时连接数据库（或使用离线缓存）检查 SQL 语法、表名、列名、参数类型和返回类型，错误在编译期暴露而非运行期。MySQL 与 Redis 的基础概念可分别参考《../../01-C++技术体系/05-存储与序列化/01-MySQL数据库精要.md》与《../../01-C++技术体系/05-存储与序列化/02-Redis设计与数据结构.md》，sqlx 在 Rust 侧提供了类型安全的异步访问层。

```toml
# Cargo.toml
[dependencies]
sqlx = { version = "0.7", features = ["runtime-tokio-rustls", "postgres", "chrono"] }
tokio = { version = "1", features = ["full"] }
```

```rust
use sqlx::postgres::PgPoolOptions;
use sqlx::{Row, FromRow};
use chrono::NaiveDateTime;

#[derive(Debug, FromRow)]
struct User {
    id: i64,
    name: String,
    email: String,
    created_at: NaiveDateTime,
}

#[tokio::main]
async fn main() -> Result<(), sqlx::Error> {
    // 创建连接池
    let pool = PgPoolOptions::new()
        .max_connections(20)
        .connect("postgres://user:pass@localhost:5432/mydb")
        .await?;

    // query! 宏：编译期校验 SQL，返回匿名结构体（字段名即列名）
    let users = sqlx::query!(
        "SELECT id, name, email, created_at FROM users WHERE id > $1 ORDER BY id",
        10i64
    )
    .fetch_all(&pool)
    .await?;

    for user in &users {
        println!("{}: {} ({})", user.id, user.name, user.email);
    }

    // query_as! 宏：编译期校验 + 映射到命名结构体
    let user: User = sqlx::query_as!(
        User,
        "SELECT id, name, email, created_at FROM users WHERE id = $1",
        1i64
    )
    .fetch_one(&pool)
    .await?;

    // 执行 INSERT，返回自增 ID
    let result = sqlx::query!(
        "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id",
        "Bob",
        "bob@example.com"
    )
    .fetch_one(&pool)
    .await?;
    println!("新用户 ID: {}", result.id);

    Ok(())
}
```

编译期校验的工作方式：`query!` 宏在编译时连接 `DATABASE_URL` 环境变量指定的数据库，准备 SQL 语句（`PREPARE`），从数据库获取参数类型和返回列类型，生成对应的 Rust 结构体。如果 SQL 有语法错误或表/列不存在，编译就会失败。

**离线模式**：CI 环境中没有数据库时，可以用 `cargo sqlx prepare` 生成 `.sqlx/` 目录下的元数据缓存，编译时使用缓存而非实时连接数据库：

```bash
# 生成离线元数据
cargo sqlx prepare -- --lib

# 设置离线模式编译
SQLX_OFFLINE=true cargo build
```

C++ 对照：C++ 数据库库（libpqxx、mysql-connector-cpp）都是运行期执行 SQL，语法错误和表名错误只能在运行时发现。sqlx 的编译期校验是 Rust 生态的独特优势——它将数据库 schema 纳入了类型系统，重构时修改表名会导致编译错误，而非运行时崩溃。这与 TypeScript 的类型安全 ORM（如 Prisma）理念类似，但 sqlx 不引入 ORM 抽象层，直接写 SQL。

### 6.2 连接池与事务

sqlx 的连接池（`PgPool`）是 `Arc` 共享的，可以安全地跨线程传递。事务通过 `pool.begin()` 获取 `Transaction`，提交或回滚：

```rust
use sqlx::{PgPool, Transaction};

async fn transfer_money(
    pool: &PgPool,
    from: i64,
    to: i64,
    amount: i64,
) -> Result<(), Box<dyn std::error::Error>> {
    // 开启事务
    let mut tx: Transaction<sqlx::Postgres> = pool.begin().await?;

    // 扣款
    let result = sqlx::query!(
        "UPDATE accounts SET balance = balance - $1 WHERE id = $2 AND balance >= $1",
        amount, from
    )
    .execute(&mut *tx)
    .await?;

    if result.rows_affected() == 0 {
        tx.rollback().await?;
        return Err("余额不足".into());
    }

    // 收款
    sqlx::query!(
        "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
        amount, to
    )
    .execute(&mut *tx)
    .await?;

    // 提交事务
    tx.commit().await?;
    Ok(())
}
```

`Transaction` 实现了 `DerefMut` 到连接，可以像使用连接一样执行查询（`&mut *tx`）。如果 `Transaction` 在 drop 前没有调用 `commit()`，会自动回滚，防止事务泄漏。这与 C++ 中用 RAII 封装事务（`pqxx::work`）的设计一致，但 Rust 的 `?` 运算符确保了错误路径上事务自动回滚。

## 7. Tower 中间件层

### 7.1 Service trait 与中间件组合

Tower 是 Rust 生态的中间件抽象层，核心是 `Service<Request>` trait：

```rust
pub trait Service<Request> {
    type Response;
    type Error;
    type Future: Future<Output = Result<Self::Response, Self::Error>>;

    fn poll_ready(&mut self, cx: &mut Context<'_>) -> Poll<Result<(), Self::Error>>;
    fn call(&mut self, req: Request) -> Self::Future;
}
```

`Service` 代表"接受请求、返回响应"的处理单元。中间件是实现了 `Service` 的包装器，内部持有下一个 `Service`，在调用前后添加逻辑。这与 C++ 中"装饰器模式"或 Node.js 的 middleware 概念一致，但 Tower 的 `Service` trait 是异步的，且 `poll_ready` 支持背压（backpressure）。

Tower 中间件通过 `ServiceBuilder` 组合：

```rust
use tower::ServiceBuilder;
use tower::limit::ConcurrencyLimitLayer;
use tower::timeout::TimeoutLayer;
use tower::retry::RetryLayer;
use std::time::Duration;

let service = ServiceBuilder::new()
    .layer(TimeoutLayer::new(Duration::from_secs(5)))   // 超时
    .layer(ConcurrencyLimitLayer::new(100))               // 并发限制
    .layer(RetryLayer::new(my_retry_policy))              // 重试
    .service(my_handler_service);
```

axum 的 `Router::layer()` 接受任何实现了 Tower `Layer` trait 的中间件，这意味着整个 Tower 生态（超时、限流、重试、熔断、缓存）都可以直接在 axum 中使用。C++ 框架通常各自实现中间件，无法跨框架复用，Tower 的统一抽象是 Rust 生态的重要优势。

### 7.2 常用中间件：超时、限流、追踪

**超时中间件**：`tower::timeout::TimeoutLayer` 为请求设置最大处理时间，超时返回错误。

**限流中间件**：`tower::limit::RateLimitLayer` 基于令牌桶算法限制请求速率（需要 `tower/limit` feature）。

```rust
use tower::limit::RateLimitLayer;
use std::time::Duration;

// 每秒最多 100 个请求
let rate_limit = RateLimitLayer::new(100, Duration::from_secs(1));
```

**追踪中间件**：`tower_http::trace::TraceLayer` 自动为每个请求生成 tracing span，记录方法、路径、状态码、耗时，与 `tracing` 生态集成。

```rust
use tower_http::trace::TraceLayer;
use tower_http::classify::StatusInRangeAsFailures;

let trace_layer = TraceLayer::new_for_http()
    .make_span_with(|request: &http::Request<_>| {
        tracing::info_span!(
            "http_request",
            method = %request.method(),
            path = %request.uri().path(),
        )
    })
    .on_response(|response: &http::Response<_>, latency: Duration, _span: &tracing::Span| {
        tracing::info!(
            status = %response.status(),
            latency_ms = latency.as_millis(),
            "请求完成"
        );
    });
```

C++ 对照：C++ 中这些中间件功能通常需要自己实现或依赖框架内置（Drogon 有内置的限流和压缩，但没有统一的中间件生态）。Tower 的 `Service` 抽象使得中间件可以在 hyper、axum、tonic（gRPC）等不同框架间复用，这是 C++ 生态缺乏的统一抽象层。

## 8. 常见坑与本节小结

### 常见坑

1. **`Json<T>` 提取失败返回 400 但无详细信息**：axum 默认的 JSON 解析错误只返回 400，不包含错误详情。需要自定义 `rejection` 处理或使用 `axum::extract::json::RawJson` 获取原始错误。
2. **状态类型忘记 `Clone`**：`State<T>` 要求 `T: Clone`，如果状态类型没有派生 `Clone`，编译会报复杂的 trait bound 错误。状态内部用 `Arc` 共享，`Clone` 是廉价的。
3. **`Router::nest` 路径尾部斜杠问题**：`.nest("/api", router)` 中嵌套路由的路径是相对于 `/api` 的，`/api/users` 和 `/api/users/` 是不同的路由。使用 `.nest("/api", router)` 时嵌套路由不要以 `/` 开头。
4. **sqlx `query!` 宏在 CI 中编译失败**：CI 环境没有数据库时，`query!` 宏无法连接数据库校验。必须使用 `cargo sqlx prepare` 生成离线元数据，并设置 `SQLX_OFFLINE=true`。
5. **WebSocket 中 `socket.recv()` 和 `socket.send()` 不能同时在一个任务中**：`WebSocket` 不是 `Clone` 的，无法同时在两个任务中使用。需要用 `socket.split()` 拆分为 `sender` 和 `receiver` 两半，分别在两个任务中使用。
6. **axum 0.6 到 0.7 的 `Extension` 弃用**：axum 0.7 弃用了 `Extension` 提取器，推荐使用 `State`。迁移时将中间件注入的数据改为通过 `with_state` 传递。
7. **在 handler 中使用阻塞操作**：数据库查询、文件 IO 等阻塞操作如果使用同步版本（如 `std::fs`），会阻塞 Tokio 工作线程。必须使用异步版本（`tokio::fs`、sqlx 异步查询）或 `spawn_blocking`。
8. **`StatusCode` 作为 `Err` 返回时类型不匹配**：`Result<Json<T>, StatusCode>` 是合法的，但如果 handler 中有多种错误类型，需要统一为自定义错误枚举并实现 `IntoResponse`。

### 本节小结

Rust Web 后端生态以 hyper 为底层 HTTP 实现，axum 为主流高阶框架，Tower 为统一中间件抽象层，sqlx 为编译期校验数据库库，形成了完整的技术栈。axum 的提取器体系将"handler 参数类型即请求数据提取"做到了类型安全，路由系统通过方法链在编译期检查 handler 签名，状态共享通过 `State<T>` + `Arc` 实现，中间件通过 Tower `Layer` 组合并可跨框架复用。完整的 REST API 服务整合了路由、提取器、状态、中间件、统一错误处理，代码结构清晰且类型安全。WebSocket 通过 `WebSocketUpgrade` 提取器自动处理握手，配合 `broadcast` 通道实现多客户端广播。sqlx 的编译期 SQL 校验是 Rust 生态的独特优势，将数据库 schema 纳入类型系统，重构时提前暴露错误。与 C++ 后端框架相比，Rust 的优势在于：统一的异步运行时（Tokio）、可复用的中间件生态（Tower）、编译期安全（提取器 + sqlx）、以及高度集中的框架选择（axum/actix-web 双雄）。

---

上一篇：《01-网络编程与异步IO.md》
下一篇：《03-嵌入式no_std与裸机.md》

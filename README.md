# Live Stream Web

简体中文（中国大陆） / [English (US)](README_en_US.md)

一个自建直播平台，支持 OBS RTMP 推流、HLS 分发、密码保护观看和弹幕（Canvas 弹幕）。基于 Python FastAPI + Node-Media-Server 构建。

## 架构

```
OBS ──RTMP──→ Node-Media-Server (:1935) ──HLS──→ FastAPI (:443) ←── 浏览器
                      │                                  │
                      └── auth callback → /api/validate_push
```

- **后端**: Python FastAPI（HTTPS 端口 443）
- **媒体服务器**: Node-Media-Server（RTMP 端口 1935，HLS 生成）
- **前端**: 深蓝主题 HTML/CSS/JS，Canvas 弹幕
- **认证**: 盐化 SHA256（推流密码 + 观看密码）

## 环境要求

| 软件          | 备注                                       |
| ------------- | ------------------------------------------ |
| Python 3.10+  | [python.org](https://python.org)           |
| Node.js 18+   | [nodejs.org](https://nodejs.org)           |
| OBS Studio    | [obsproject.com](https://obsproject.com)   |
| SSL 证书      | 放在 `C:\Users\a233d\Documents\cert`（`az7627.top.pem` + `az7627.top.key`） |

## 快速开始

### 1. 安装依赖

```bash
# Python
pip install -r backend\requirements.txt

# Node（媒体服务器）
cd media-server
npm install
cd ..
```

### 2. 设置推流密码

在启动服务器之前（或随时修改）运行：

```bash
python change_push_password.py
```

输入新密码。密码以盐化 SHA256 存储，不会明文写入磁盘。

### 3. 启动服务器

```bash
python start.py
```

同时启动 FastAPI 后端（HTTPS :443）和 Node-Media-Server（RTMP :1935）。Ctrl+C 停止两者。

### 4. 创建直播间

1. 浏览器打开 **https://localhost**
2. 点击 **「开始直播」**
3. 输入**直播间名称**（如 `my-broadcast`），点击**检查**
4. 设置**观看密码**（观众需要此密码观看）
5. 点击**「开始直播」**
6. 页面将显示 OBS 配置信息，复制它们

### 5. 配置 OBS

| 设置          | 值                                                         |
| ------------- | ---------------------------------------------------------- |
| 服务          | 自定义…                                                    |
| 服务器        | `rtmp://YOUR_SERVER_IP/live`                               |
| 串流密钥      | `your-stream-name`                                         |

> **注意**: 在 OBS → 高级 → 网络，可以在串流密钥中附带推流密码：
> `your-stream-name?password=YOUR_PUSH_PASSWORD`

在 OBS 中点击「开始推流」后，直播间将出现在主页上显示为「直播中」。

### 6. 观看与弹幕

1. 在主页点击直播间的 **「观看」**
2. 输入**观看密码**
3. 视频在直播开始后自动加载
4. 在弹幕栏输入内容，按回车发送！

## 修改推流密码

```bash
python change_push_password.py
```

## 文件结构

```
live-stream-web/
├── backend/
│   ├── main.py              # FastAPI 应用
│   ├── auth.py              # 盐化 SHA256 工具
│   └── requirements.txt     # Python 依赖
├── media-server/
│   ├── server.js            # Node-Media-Server 配置
│   └── package.json         # npm 依赖
├── frontend/
│   ├── index.html           # 主页（直播间列表）
│   ├── go-live.html         # 创建直播间 + OBS 指引
│   ├── watch.html           # 视频播放器 + 弹幕
│   ├── css/style.css        # 深蓝主题
│   └── js/
│       ├── app.js           # 共享 API 工具
│       └── danmaku.js       # Canvas 弹幕引擎
├── data/
│   └── live_stream.db       # SQLite 数据库（自动创建）
├── media/hls/               # HLS 分片（自动创建）
├── change_push_password.py  # 推流密码管理
├── start.py                 # 统一启动脚本
└── README.md
```

## 安全说明

- **观看密码**由直播间创建者设置，以盐化 SHA256 存储
- **推流密码**是服务器全局密钥，同样盐化 SHA256 存储
- `change_push_password.py` 不会记录或打印密码
- Web 界面必须使用 HTTPS
- 弹幕（WebSocket）对知道观看密码的任何人均可用

## 常见问题

| 现象                              | 解决方法                                          |
| --------------------------------- | ------------------------------------------------- |
| 浏览器显示「连接被拒绝」          | 确认服务器已运行（`python start.py`）             |
| OBS 无法连接                      | 确认防火墙已开放 1935 端口                        |
| 「推流密码未配置」                | 运行 `python change_push_password.py`             |
| 「直播间未找到」                  | 先通过 Web UI 创建直播间                          |
| 浏览器中视频不播放                | 确认 OBS 正在推流                                 |
| 混合内容警告                      | 确保所有 URL 使用 HTTPS                           |

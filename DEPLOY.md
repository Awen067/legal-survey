# 企业用工法律风险体检 - 数据库版 部署指南

## 方案一：部署到 Railway.app（推荐）

### 优势
- Python 原生运行，数据库版全部功能可用
- 免费额度足够小型使用
- 自动 HTTPS，公网可访问

### 步骤

#### 1. 注册 GitHub 账号
访问 https://github.com 注册（已有则跳过）

#### 2. 注册 Railway 账号
访问 https://railway.app 点击 "Login"，用 GitHub 账号登录

#### 3. 创建新项目
- 登录后在 Railway 控制台点击 **"New Project"**
- 选择 **"Deploy from GitHub repo"**
- 如果没有看到仓库，需要先推送代码到 GitHub

#### 4. 推送代码到 GitHub
在你本地执行以下命令（需要先创建 GitHub 仓库）：

```bash
cd /Users/wangwen1/Desktop/0000/体检/survey_app
git remote add origin https://github.com/YOUR_USERNAME/legal-survey.git
git push -u origin master
```

> 如果不知道如何创建 GitHub 仓库，请告诉我，我来帮你操作

#### 5. 在 Railway 中部署
- 选择你刚推送的仓库
- Railway 会自动检测 Python 项目并开始部署
- 部署完成后，点击生成的 URL 即可访问

#### 6. 配置持久化磁盘（重要！）
- 在 Railway 项目页面，点击 **"Settings"**
- 找到 **"Volumes"** 部分
- 点击 **"Create Volume"**
- 挂载路径填 `/data`，大小选 1GB
- 点击保存，Railway 会自动重启

#### 7. 获取访问链接
- 部署完成后，Railway 会生成一个 `xxx.up.railway.app` 的链接
- 分享这个链接给用户填问卷
- 管理员后台：`https://xxx.up.railway.app/admin`，密码 `law2024`

---

## 方案二：部署到 Render.com（备选）

### 步骤
1. 注册 https://render.com（用 GitHub 登录）
2. 点击 **"New +"** → **"Web Service"**
3. 连接 GitHub 仓库
4. 配置：
   - **Build Command**: 留空（使用默认）
   - **Start Command**: `python3 server_db.py`
5. 点击 **"Create Web Service"**
6. 等待部署完成，获得 `xxx.onrender.com` 链接

> ⚠️ Render 免费版：服务闲置时会休眠，首次访问需等待约 30 秒唤醒

---

## 方案三：修改版 — 纯前端 + Turso 云数据库（部署到 CloudStudio）

此方案将数据库版改造成纯前端，数据存储在 Turso 云端数据库，可重新部署到 CloudStudio（公网可访问）。

### 优点
- 无需 Python 服务器，部署简单（跟之前 CloudStudio 一样）
- 数据存储在云端，多设备共享

### 步骤
1. 注册 Turso 账号：https://tur.so
2. 创建数据库 `surveys`
3. 获取数据库 URL 和 Token
4. 我帮你修改 `deploy/index.html` 接入 Turso
5. 部署到 CloudStudio

> 如果你选这个方案，请告诉我，我来帮你改代码

---

## 推荐选择

| 场景 | 推荐方案 |
|------|----------|
| 想要完整功能，长期使用 | **方案一：Railway** |
| 想要最简单，快速上线 | **方案三：Turso+CloudStudio** |
| Railway 不可用时 | **方案二：Render** |

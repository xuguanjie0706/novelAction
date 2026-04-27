# 小说创作系统

## 快速启动

### 方式一：Docker（推荐）

```bash
# 1. 复制并填写 API Key
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入 ANTHROPIC_API_KEY 或 OPENAI_API_KEY

# 2. 启动所有服务
docker-compose up -d

# 访问（Compose 将容器端口映射到宿主机，避免与本地 ./restart.sh 默认端口混淆）
# 前端: http://localhost:19173
# 后端 API 文档: http://localhost:18080/docs
```

**端口对照（宿主机）**

| 场景 | 前端 | 后端 API |
|------|------|----------|
| Docker Compose（默认映射） | 19173 | 18080 |
| 本地 `./restart.sh`（默认） | 5173 | 8000 |

覆盖 Compose 映射时可导出环境变量后再执行 `docker-compose up`，例如：`NOVEL_DOCKER_BACKEND_HOST_PORT=28080`。本地端口可复制 `env.local.ports.example` 为 `.env.local.ports` 后修改；若前端端口不是 5173，请在 `backend/.env` 中配置 `CORS_ORIGINS`（JSON 数组）包含对应 `http://localhost:端口`。

#### Colima 用户说明（macOS）

```bash
# 1) 启动 Colima
colima start

# 2) 确认 Docker 指向 colima
docker context use colima
docker context ls

# 3) 构建并启动
docker-compose up -d --build
```

> 说明：部分环境只支持 `docker-compose`（连字符），不支持 `docker compose`（空格子命令）。
> 如果你执行 `docker compose` 报错，请改用 `docker-compose`。

#### 常见问题

- 前端能打开但 API 报错 `ECONNREFUSED`
  - 检查前端代理目标是否为容器内可达地址（Docker Compose 下应为 `http://backend:8000`）。
- 后端启动时报错 `type "vector" does not exist`
  - 在数据库中启用 pgvector 扩展：

```bash
docker-compose exec -T postgres psql -U novel -d novel_db -c "CREATE EXTENSION IF NOT EXISTS vector;"
docker-compose restart backend
```

### 方式二：本地开发

默认端口为前端 **5173**、后端 **8000**（与 Docker 宿主机映射 **19173 / 18080** 不同）。一键启动可用 `./restart.sh`；改端口可复制 `env.local.ports.example` 为 `.env.local.ports`。

依赖与环境可执行 **`bash bootstrap.sh`**：在 **Windows** 上会使用 [penv](https://github.com/hmasdev/penv)（嵌入版 Python）创建 `backend/.venv`；在 **macOS / Linux** 上默认使用 **[uv](https://github.com/astral-sh/uv)**（安装解释器、建 `backend/.venv`、按 `requirements.txt` 装包）。若不想用 uv，可执行 `BOOTSTRAP_USE_UV=0 bash bootstrap.sh`，将回退到 **`python3.12 -m venv` + pip**。

**后端**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # 填入 API Key 和数据库配置
uvicorn app.main:app --reload --port 8000
```

**前端**
```bash
cd frontend
npm install
VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

## 项目结构

```
novel-system/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置（读取 .env）
│   │   ├── database.py          # SQLAlchemy 连接
│   │   ├── models/              # 数据库模型
│   │   │   ├── project.py
│   │   │   ├── world_setting.py
│   │   │   ├── character.py
│   │   │   ├── outline.py
│   │   │   ├── chapter.py
│   │   │   └── memory.py
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── routers/             # API 路由
│   │   │   ├── projects.py
│   │   │   ├── world_settings.py
│   │   │   ├── characters.py
│   │   │   ├── outline.py
│   │   │   ├── chapters.py
│   │   │   └── ai.py
│   │   └── services/
│   │       └── ai_service.py    # Claude/GPT 调用封装
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # 路由配置
│   │   ├── types/               # TypeScript 类型
│   │   ├── api/client.ts        # Axios API 客户端
│   │   ├── store/index.ts       # Zustand 全局状态
│   │   ├── components/
│   │   │   ├── Layout/          # AppLayout / Sidebar / TopBar
│   │   │   ├── Writing/         # ChapterEditor (TipTap)
│   │   │   └── AI/              # AIPanel (质检/建议/记忆库)
│   │   └── pages/
│   │       ├── ProjectsPage.tsx
│   │       ├── OutlinePage.tsx
│   │       └── WritePage.tsx
│   └── package.json
└── docker-compose.yml
```

## API 路由总览

| 模块 | 路径前缀 |
|------|---------|
| 项目管理 | `GET/POST /api/v1/projects/` |
| 世界观设定 | `/api/v1/projects/{id}/settings/` |
| 人物 | `/api/v1/projects/{id}/characters/` |
| 大纲树 | `/api/v1/projects/{id}/outline/` |
| 章节 | `/api/v1/projects/{id}/chapters/` |
| AI 质检 | `POST /api/v1/projects/{id}/ai/quality-check` |
| AI 建议（流式） | `POST /api/v1/projects/{id}/ai/suggest/stream` |
| 记忆提取 | `POST /api/v1/projects/{id}/ai/extract-memory` |

## 后续可扩展方向

- [ ] 人物关系图（ReactFlow）
- [ ] 世界观设定卡完整 UI
- [ ] 前十章追读分析表
- [ ] pgvector 语义记忆检索
- [ ] 导出 TXT / EPUB
- [ ] 多用户 / 登录鉴权

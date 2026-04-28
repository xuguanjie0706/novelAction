# 小说创作系统

## 快速启动

### 方式一：Docker（推荐）

```bash
# 1. 复制并填写 API Key
cp apps/backend/.env.example apps/backend/.env
# 编辑 apps/backend/.env，填入 API Key 等

# 2. 启动所有服务
docker-compose up -d

# 访问（Compose 将容器端口映射到宿主机）
# 创作端（小说）: http://localhost:19173
# 管理后台:       http://localhost:19174
# 后端 API 文档:   http://localhost:18080/docs
```

**端口对照（宿主机）**

| 场景 | 创作端 client | 管理后台 frontend | 后端 API |
|------|---------------|-------------------|----------|
| Docker Compose（默认映射） | 19173 | 19174 | 18080 |
| 本地 `./restart.sh` | 3173（见 env） | 3174（见 env） | 9000（见 env） |

覆盖 Compose 映射时可导出环境变量后再执行 `docker-compose up`，例如：`NOVEL_DOCKER_BACKEND_HOST_PORT=28080`。本地端口可复制 `env.local.ports.example` 为 `.env.local.ports` 后修改；若前端端口不是默认，请在 `apps/backend/.env` 中配置 `CORS_ORIGINS`（JSON 数组）包含对应 `http://localhost:端口`。

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

**一键启动（后端 + 创作端 + 管理后台）**：`./restart.sh`（端口见 `env.local.ports.example`，需已安装 **pnpm**，推荐 `corepack enable && corepack prepare pnpm@9 --activate`）。

依赖与环境可执行 **`bash bootstrap.sh`**：在 **Windows** 上会使用 [penv](https://github.com/hmasdev/penv) 创建 `apps/backend/.venv`；在 **macOS / Linux** 上默认使用 **[uv](https://github.com/astral-sh/uv)**（安装解释器、建 `apps/backend/.venv`、按 `requirements.txt` 装包）。若不想用 uv，可执行 `BOOTSTRAP_USE_UV=0 bash bootstrap.sh`，将回退到 **`python3.12 -m venv` + pip**。前端在存在 **`pnpm-workspace.yaml`** 时于**仓库根目录**执行一次 **`pnpm install`**（含创作端与管理后台）；也可手动执行 **`pnpm install`** 后使用根目录脚本 **`pnpm dev:admin`** 等。

**后端**

```bash
cd apps/backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # 填入 API Key 和数据库配置
uvicorn app.main:app --reload --port 9000
```

**创作端（小说）**

```bash
cd apps/client
pnpm install
pnpm run dev
```

**管理后台**

```bash
cd apps/frontend
pnpm install
pnpm run dev
```

## 项目结构

```
novel-system/
├── pnpm-workspace.yaml    # pnpm 工作区：apps/client + apps/frontend
├── package.json           # 根脚本：pnpm dev:client / dev:admin / build:*
├── pnpm-lock.yaml
├── .github/workflows/js-apps.yml   # CI：两端 build 校验
├── apps/
│   ├── backend/           # FastAPI
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── database.py
│   │   │   ├── models/
│   │   │   ├── schemas/
│   │   │   ├── routers/
│   │   │   └── services/
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   ├── client/            # 小说创作端（Vite + React）
│   │   ├── src/
│   │   └── package.json
│   └── frontend/          # 管理后台（Vite + React，占位壳）
│       ├── src/
│       └── package.json
├── docker-compose.yml
├── bootstrap.sh
└── restart.sh
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

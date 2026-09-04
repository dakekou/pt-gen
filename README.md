# pt-gen —— 影视资料查询汇总工具（Docker 部署）

输入**豆瓣 / IMDb / TMDb 完整链接**或**链接末尾的数字**，自动查询并汇总生成 **PT 发布帖格式（BBcode）**：
顶部海报（豆瓣海报自动上传 **pixhost.cc** 图床，失败自动切换 **pixhost.to**，两个都失败会明确报错），
以及 译名 / 片名 / 年代 / 产地 / 类别 / 语言 / 上映日期 / 豆瓣评分 / **IMDb评分** / 豆瓣链接 / IMDb链接 / 导演 / 演员 / 编剧 / 音乐 / 简介。

支持**网页查询**和 **API 查询**，两者都**需要密码**才能使用。

---

## 一、部署（Docker）

### 方式 A：GitHub 一键安装（推荐，需已推送到 GitHub）

```bash
bash <(curl -sL https://raw.githubusercontent.com/dakekou/pt-gen/main/install.sh)
```

脚本会自动：检查 Docker → 克隆仓库 → 提示修改密码 → `docker compose up -d --build`。
也可以先设密码再装：

```bash
PTGEN_PASSWORD=你的密码 bash <(curl -sL https://raw.githubusercontent.com/dakekou/pt-gen/main/install.sh)
```

### 方式 B：本地手动部署

在装有 Docker + docker compose 的机器上（群晖 / Debian / VPS 等）：

```bash
# 1. 进入项目目录（把整个 pt-gen 文件夹传上去）
cd pt-gen

# 2. （可选）先修改 docker-compose.yml 里的密码
#    PTGEN_PASSWORD=你的密码

# 3. 构建并启动
docker compose up -d --build

# 4. 查看状态
docker compose ps
```

启动后访问：`http://服务器IP:8737`

> 默认密码：`ptgen2024`，**务必修改**（docker-compose.yml 中 `PTGEN_PASSWORD`）。
> 改密码后建议同步改 `PTGEN_SECRET`（cookie 签名密钥）。

停止/重启/卸载：

```bash
docker compose stop        # 停止
docker compose start       # 启动
docker compose down        # 删除容器（缓存卷保留）
docker compose down -v     # 彻底删除（含缓存）
```

---

## 二、网页使用

1. 浏览器打开 `http://IP:8737`，输入密码登录。
2. 粘贴任意一种输入，点「生成」：
   - `https://movie.douban.com/subject/1292052/`
   - `https://www.imdb.com/title/tt0111161/`
   - `https://www.themoviedb.org/movie/278`（或 `/tv/xxx`）
   - 纯数字 `1292052`（优先当豆瓣 ID 查，查不到再试 TMDB）
3. 页面展示：海报预览、豆瓣/IMDb/TMDB ID、生成结果（BBcode），一键「复制结果」。
4. 海报图床显示 `pixhost.cc` 或 `pixhost.to`；若两者都失败，页面会明确提示「海报上传失败」。

---

## 三、API 使用

接口：`GET/POST /api/gen`

**鉴权方式（任选其一）：**
- 请求头：`X-API-Key: 你的密码`
- 请求头：`Authorization: Bearer 你的密码`
- URL 参数：`?key=你的密码`

**POST 示例：**

```bash
curl -X POST http://IP:8737/api/gen \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ptgen2024" \
  -d '{"input": "https://movie.douban.com/subject/1292052/"}'
```

**GET 示例：**

```bash
curl "http://IP:8737/api/gen?input=tt0111161&key=ptgen2024"
```

**返回 JSON：**

```json
{
  "success": true,
  "input": "1292052",
  "kind": "number",
  "douban_id": "1292052",
  "imdb_id": "tt0111161",
  "tmdb_id": "278",
  "media_type": "movie",
  "data": {
    "title_zh": "肖申克的救赎",
    "original_title": "The Shawshank Redemption",
    "yiming": "肖申克的救赎 / 月黑高飞(港) / ...",
    "year": "1994",
    "region": "美国",
    "genres": "剧情 / 犯罪",
    "language": "英语",
    "release_dates": "1994-09-10(多伦多电影节) / ...",
    "douban_rating": "9.7",
    "douban_votes": 3333417,
    "imdb_rating": 9.3,
    "imdb_votes": 3221305,
    "douban_url": "https://movie.douban.com/subject/1292052/",
    "imdb_url": "https://www.imdb.com/title/tt0111161/",
    "tmdb_url": "https://www.themoviedb.org/movie/278",
    "intro": "...",
    "music": "托马斯·纽曼"
  },
  "poster": {
    "original_url": "https://img3.doubanio.com/...",
    "uploaded_url": "https://img3.pixhost.cc/images/5445/xxx.jpg",
    "host": "pixhost.cc",
    "status": "ok"
  },
  "bbcode": "[img]...[/img]\n\n◎译　　名　..."
}
```

错误码：`401` 未授权 / `400` 参数缺失或非法 / `502`（JSON 内 error 描述）上游抓取失败。

---

## 四、数据来源与说明

| 字段 | 来源 | 说明 |
|---|---|---|
| 译名/片名/年代/产地/类别/语言/上映日期/豆瓣评分/简介/海报 | 豆瓣（rexxar 手机接口 + h5 desc 页，桌面版及演职员页作增强） | 数据中心 IP 可能被豆瓣反爬，住宅 IP 通常正常 |
| 导演/演员/编剧/音乐 | 豆瓣演职员页（优先）→ desc 页 → TMDB credits / Wikidata | 音乐仅在数据源提供时输出 |
| IMDb 评分 | IMDb GraphQL 官方接口 → OMDb 兜底 | |
| TMDB ID / 链接 | TMDB API v3（内置只读 token，可用 `TMDB_TOKEN` 覆盖） | 服务器无法访问 api.themoviedb.org 时该字段为空，不影响主流程 |
| 海报图床 | pixhost：上传后直链优先 `pixhost.cc`，自动切换 `pixhost.to`，双失败报错 | 同海报自动缓存，不重复上传 |

**环境变量（docker-compose.yml）：**

| 变量 | 默认 | 说明 |
|---|---|---|
| `PTGEN_PASSWORD` | `ptgen2024` | 访问密码（网页 + API） |
| `PTGEN_SECRET` | `ptgen-secret-change-me` | Cookie 签名密钥 |
| `TMDB_TOKEN` | 内置只读 token | TMDB API Bearer token（如失效可替换） |
| `OMDB_API_KEY` | `thewdb` | OMDb 公共 key（如失效可替换） |

---

## 五、常见问题

- **构建时 pip 安装失败（Could not find a version / No matching distribution）**：说明当前 pip 源不可达。Dockerfile 默认使用官方 PyPI（海外机器通常正常）；国内机器请在安装前指定清华镜像，例如：
  ```bash
  PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple bash <(curl -sL https://raw.githubusercontent.com/dakekou/pt-gen/main/install.sh)
  ```
  已克隆到本地的仓库可运行：`PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple docker compose up -d --build`。
- **豆瓣被反爬（提示抓取失败）**：服务器为机房 IP 时豆瓣可能弹验证页。可换住宅 IP / 家庭宽带的 NAS 部署，或稍后重试（有 24 小时结果缓存）。
- **TMDB 显示不可达**：检查服务器能否访问 `api.themoviedb.org`（部分网络需要代理）。不影响豆瓣/IMDb 主流程，仅 TMDB ID 字段为空。
- **海报上传失败**：pixhost 偶发不可达时自动重试另一域名；两者都失败会明确报错，BBcode 中不包含海报行。
- **结果缓存**：同一输入 24 小时内直接返回缓存，海报缓存 30 天。

## 六、目录结构

```
pt-gen/
├── app/
│   ├── main.py         # FastAPI 服务：网页 + API + 密码鉴权
│   ├── service.py      # 编排：输入解析 -> 抓取 -> 汇总 -> 生成
│   ├── fetchers.py     # 豆瓣 / IMDb / TMDB / OMDb / Wikidata 抓取
│   ├── poster.py       # pixhost 上传（cc/to 自动切换）
│   ├── formatter.py    # BBcode 格式化
│   ├── cache.py        # 文件缓存
│   └── static/         # 网页（登录页 + 查询页）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

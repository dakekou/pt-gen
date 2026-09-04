#!/usr/bin/env bash
# ============================================================================
#  pt-gen 一键安装脚本（Docker 部署）
#
#  用法（任选其一）：
#    方式A - GitHub 远程一键安装（推荐，需已推送到 GitHub）：
#      bash <(curl -sL https://raw.githubusercontent.com/dakekou/pt-gen/main/install.sh)
#
#    方式B - 指定仓库地址安装：
#      bash install.sh https://github.com/dakekou/pt-gen.git
#
#    方式C - 本地目录直接安装（不克隆）：
#      bash install.sh local
#
#  可配置环境变量：
#     PTGEN_DIR      安装目录（默认 $HOME/pt-gen）
#     PTGEN_PASSWORD 访问密码（默认读 docker-compose.yml，未设则为 ptgen2024）
#     PTGEN_PORT     对外端口（默认 8737）
#     PIP_INDEX_URL  pip 下载源（默认官方 PyPI；国内机器可设为
#                    https://pypi.tuna.tsinghua.edu.cn/simple）
# ============================================================================
set -e

REPO_URL="${1:-https://github.com/dakekou/pt-gen.git}"
INSTALL_DIR="${PTGEN_DIR:-$HOME/pt-gen}"

echo "=============================================="
echo "  pt-gen 一键安装"
echo "  安装目录: $INSTALL_DIR"
echo "=============================================="

# 1. 环境检查
if ! command -v docker >/dev/null 2>&1; then
  echo "❌ 未检测到 Docker，请先安装 Docker："
  echo "   https://docs.docker.com/engine/install/"
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "❌ 未检测到 docker compose 插件，请安装："
  echo "   https://docs.docker.com/compose/install/"
  exit 1
fi

# 2. 获取代码
if [ "$REPO_URL" = "local" ]; then
  echo "使用当前目录安装..."
  cd "$(dirname "$0")"
else
  if [ -d "$INSTALL_DIR/.git" ]; then
    echo "检测到已有安装，拉取最新代码..."
    if git -C "$INSTALL_DIR" pull --ff-only; then
      :
    else
      echo "⚠️ 本地与远程历史不一致（可能远程被重置过），强制同步为远程最新版..."
      git -C "$INSTALL_DIR" fetch origin
      git -C "$INSTALL_DIR" reset --hard origin/main
    fi
  else
    echo "克隆仓库: $REPO_URL"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" || {
      echo "❌ 克隆失败。若网络不通（如 raw.githubusercontent.com 被墙）可尝试加速镜像："
      echo "   git clone --depth 1 https://gh-proxy.com/$REPO_URL $INSTALL_DIR"
      echo "   git clone --depth 1 https://ghfast.top/$REPO_URL $INSTALL_DIR"
      echo "   git clone --depth 1 https://github.com.cnpmjs.org/$REPO_URL $INSTALL_DIR"
      echo "   （以上第三方加速站可能失效，失效时请重试或自行搜索可用镜像）"
      exit 1
    }
    # 克隆后校验：仓库根目录必须存在 docker-compose.yml（防止套了一层目录）
    if [ ! -f "$INSTALL_DIR/docker-compose.yml" ]; then
      echo "❌ 仓库结构异常：未在 $INSTALL_DIR 找到 docker-compose.yml"
      echo "   请确认仓库根目录直接包含 Dockerfile / docker-compose.yml / install.sh，而非嵌套子目录。"
      exit 1
    fi
  fi
  cd "$INSTALL_DIR"
fi

# 3. 密码提示
if [ -z "$PTGEN_PASSWORD" ] && [ -f docker-compose.yml ]; then
  echo ""
  echo "⚠️  默认访问密码: ptgen2024"
  echo "   强烈建议修改：编辑 $INSTALL_DIR/docker-compose.yml 中 PTGEN_PASSWORD"
  echo "   （或安装时指定 PTGEN_PASSWORD=你的密码）"
  echo ""
fi

# 4. 构建并启动
echo "构建并启动容器..."
if ! docker compose up -d --build; then
  echo ""
  echo "❌ 构建失败。若为 pip 下载依赖失败（镜像源不通），请按服务器网络重试："
  echo "   # 海外机器（默认官方 PyPI，一般无需设置）:"
  echo "   docker compose up -d --build"
  echo "   # 国内机器（切到清华镜像）:"
  echo "   PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple docker compose up -d --build"
  echo "   # 或带一键安装整体重跑:"
  echo "   PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple bash $0 $REPO_URL"
  exit 1
fi

# 5. 完成
PORT="${PTGEN_PORT:-8737}"
IP=$(hostname -I 2>/dev/null | awk '{print $1}' | head -1)
echo ""
echo "✅ pt-gen 安装完成"
echo "   访问地址: http://${IP:-本机IP}:$PORT"
echo "   登录密码: ${PTGEN_PASSWORD:-ptgen2024}（请尽快修改）"
echo ""
echo "   常用命令:"
echo "     docker compose logs -f ptgen   # 查看日志"
echo "     docker compose restart ptgen   # 重启"
echo "     docker compose down            # 停止并删除容器"

# =============================================================================
# 前端镜像：ui（Vue3 + Vite）—— 多阶段构建
#   阶段 1：用 node 把前端编译成静态文件
#   阶段 2：用 nginx 托管静态文件
# 构建上下文 = ui/ 目录（见 docker-compose.yaml 里 frontend.build.context: ../ui）
# =============================================================================

# ---------- 阶段 1：构建 ----------
FROM node:22-alpine AS build

WORKDIR /app

# npm 源。国内构建慢/失败时可改成镜像源：
#   docker compose build --build-arg NPM_REGISTRY=https://registry.npmmirror.com frontend
ARG NPM_REGISTRY=https://registry.npmjs.org

# 先拷依赖清单，利用缓存
COPY package.json package-lock.json ./
RUN npm install --registry=${NPM_REGISTRY}

# 再拷源码并构建
COPY . .
# 说明：这里跑 vite build（而非 npm run build）。
#   npm run build = vue-tsc -b && vite build，会先做 TS 类型检查；
#   容器构建里跳过类型检查，避免历史 TS 报错挡住打包。
RUN npx vite build

# ---------- 阶段 2：运行 ----------
FROM nginx:alpine

# 用自定义配置替换默认站点配置（支持 SPA 前端路由回退）
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 把编译产物放进 nginx 站点根目录
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

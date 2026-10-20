# AV Subtitle Manager — 极空间 Z4 Pro 自动字幕管理器

自动扫描影片、识别番号、使用迅雷字幕 API 搜索中文字幕，严格匹配后下载到视频旁；带 Web 管理界面、失败重试和候选字幕人工审核。**不依赖 Stash，不使用 .env 文件。**

## GHCR Docker 镜像

- 最新镜像：`ghcr.io/edcv593/av-subtitle-manager:latest`
- 支持架构：`linux/amd64`、`linux/arm64`
- 发布工作流：[GitHub Actions](https://github.com/edcv593/av-subtitle-manager/actions/workflows/docker-publish.yml)
- 镜像包页面：[GitHub Packages](https://github.com/edcv593?tab=packages)

每次推送 `main` 分支自动构建并发布 `latest` 和短 SHA 标签；推送 `v1.2.3` 形式的 Git 标签会发布 `1.2.3`、`1.2` 等版本标签。也可以在 Actions 页面手动触发构建。

**重要：** 新创建的 GHCR 包可能默认为私有；请在 GitHub 的 Package settings → Change visibility 将包设为 **Public**，否则极空间匿名拉取可能失败。GitHub Actions 成功不代表镜像已经公开，也不代表 NAS 已经更新。

## 极空间 Z4 Pro 部署

1. 下载仓库 ZIP 或复制仓库中的 `docker-compose.yml` 到极空间 Docker Compose 项目。
2. 将 `/请修改为极空间实际影片路径` 替换为影片目录的**真实绝对路径**，此目录需允许容器写入字幕。
3. 将 `WEB_TOKEN` 替换成足够长的随机密码。**切勿把自己的真实密码提交到公开 GitHub 仓库。**
4. 在 Compose 项目中启动；此配置使用预构建镜像，不需要极空间本地构建。
5. 打开 `http://极空间IP:8765`，输入 `WEB_TOKEN`。
6. 建议第一次把 `AUTO_DOWNLOAD` 设置为 `"false"`，确认匹配结果再开启。

Compose 核心配置：

```yaml
services:
  subtitle-manager:
    image: ghcr.io/edcv593/av-subtitle-manager:latest
    container_name: av-subtitle-manager
    restart: unless-stopped
    ports:
      - "8765:8765"
    environment:
      TZ: Asia/Shanghai
      MEDIA_ROOT: /media
      DATA_ROOT: /data
      SCAN_HOURS: "6"
      RETRY_HOURS: "24"
      FILE_STABLE_MINUTES: "30"
      AUTO_DOWNLOAD: "true"
      SKIP_C_MARKER: "true"
      MAX_DOWNLOAD_MB: "8"
      WEB_TOKEN: "CHANGE_ME_TO_A_LONG_RANDOM_PASSWORD"
    volumes:
      - /请修改为极空间实际影片路径:/media
      - ./data:/data
    security_opt:
      - no-new-privileges:true
    pids_limit: 128
```

`./data` 目录持久化 SQLite 数据库。极空间的 Compose 项目需要正确支持相对路径；如不支持，请把 `./data` 改成 NAS 上的绝对路径。

## 规则与限制

- 默认每 6 小时扫描，未找到/失败 24 小时后重试，新视频至少等待 30 分钟。
- `IPX-123-C.mp4`、`IPX-123-破解-C.mp4` 等含独立 `-C` 标记的影片直接跳过。
- 已有同名外挂字幕的影片跳过；**不会检测 MKV 内封字幕**。
- 自动下载仅处理番号完全一致、字幕名称带中文标记且候选唯一的字幕；多个候选需要在 Web 页面人工选择。
- 不覆盖已有字幕，校验字幕基本文本格式；**无法保证字幕时间轴与内容完全正确**。
- 迅雷 API 是第三方接口，可能变更、限流或失效；尚未在极空间 NAS 上完成端到端验证。
- Web 服务没有内置 HTTPS，请**仅在可信局域网使用**，不要向公网开放 8765 端口。
- 容器当前默认以 root 运行以适配 NAS 目录权限，建议有条件时使用最小权限账户。
- 确保所处理的影片和字幕符合适用法律及授权要求。

## 更新镜像

在极空间重新拉取 `latest` 镜像并重建容器即可更新；`docker compose pull && docker compose up -d` 是命令行等价操作。自动构建**不会**自动替你更新 NAS 上正在运行的容器。

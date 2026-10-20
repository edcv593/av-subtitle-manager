# AV Subtitle Manager — 极空间 Z4 Pro 自动字幕管理器

自动扫描影片、识别番号、使用迅雷字幕 API 搜索中文字幕，使用 ffprobe 视频时长与字幕时间轴增强校验后下载到视频旁；带 Web 管理界面、失败重试和候选字幕人工审核。**不依赖 Stash，不使用 .env 文件。**

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
      CHECK_EMBEDDED: "true"
      SCORE_THRESHOLD: "80"
      AI_QUEUE_ENABLED: "true"
      AI_AUTO_ENQUEUE: "false"
      AI_WORKER_ENABLED: "false"
      AI_MAX_PENDING: "500"
      AI_SOURCE_LANGUAGE: "ja"
      AI_TARGET_LANGUAGE: "zh"
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

## AI 备用字幕任务队列（仅排队，不运行 AI）

本阶段新增 `ai_queue.py`，使用现有 `/data/subtitle.db` 持久化任务，**不安装 Whisper、不会提取音频、不会生成或翻译字幕**。极空间无需 GPU、Redis 或第二个容器。

- `AI_QUEUE_ENABLED: "true"`：启用队列 API 与 Web 页面。
- `AI_AUTO_ENQUEUE: "false"`：默认仅在影片列表中手动点击“加入 AI 队列”。设为 `"true"` 后，仅当迅雷搜索返回**没有可靠候选**时尝试入队；多个候选、时间轴可疑等情况仍优先人工审核。
- `AI_WORKER_ENABLED: "false"`：未来 Worker 领取/心跳/状态接口默认不可用。
- `AI_MAX_PENDING: "500"`：限制未完成任务数量。
- `AI_SOURCE_LANGUAGE` / `AI_TARGET_LANGUAGE`：预留配置，当前任务固定记录 `ja` → `zh`，**尚未接入翻译或语言设置功能**。

任务按照视频路径、大小、修改时间去重；视频版本变化时，旧的未完成任务会标记取消。可以在 Web 页面查看、暂停、恢复、取消或重试。任务状态包含 `pending`、`claimed`、`extracting`、`transcribing`、`translating`、`reviewing`、`completed`、`failed`、`cancelled`、`paused`。本阶段实际新增的任务只会进入 `pending`，除非未来显式开启 Worker 接口。

**预留 Worker API（不建议现在开启）**：`POST /api/ai/worker/claim`、`POST /api/ai/worker/{job_id}/heartbeat`、`POST /api/ai/worker/{job_id}/transition`。采用 SQLite 原子领取和租约超时恢复，所有请求使用现有 `X-Auth-Token`；尚未实现独立 Worker 身份、字幕上传与安全发布、音频处理、任务完成确认等生产功能。请保持 `AI_WORKER_ENABLED=false`，不要向公网开放。即使将来开启，当前版本也不会自行运行 AI 推理。

自动入队会尊重 `-C` 跳过、已有外挂字幕及可识别的内嵌中文字幕。已有索引的影片可通过 Web 列表手动入队；新视频需要先被正常扫描索引。后台周期扫描不删除已消失影片的历史任务记录。

## 增强模式：时长和时间轴校验

镜像内置 `ffprobe`（来自 ffmpeg），无需在极空间额外安装。自动下载流程：

1. 迅雷 API 搜索并严格匹配番号与中文字幕名称。
2. 下载候选字幕到内存并验证 SRT/ASS/SSA/VTT 基本格式。
3. 使用 `ffprobe` 获取影片总时长，解析字幕事件开始与结束时间。
4. 校验字幕是否超出视频总时长、是否存在明显时间倒序或异常长事件。
5. 仅当唯一候选通过校验时，自动保存到影片旁边；无法取得视频时长、字幕解析失败或疑似错位时，标记为 `review`，**不会自动保存**。
6. Web 管理界面点击“候选”后，可人工确认并下载；手动下载会明确提示可能不匹配。

**限制：** 时长与时间戳合理不等于字幕内容对应，也不能证明没有固定偏移、剪辑版差异或对白错位。字幕只覆盖部分片段是正常现象，因此不会仅因字幕结束时间早于视频时长而拒绝。首次上线建议把 `AUTO_DOWNLOAD` 设为 `"false"`，观察一批候选再开启。

## 长视频时间轴分布诊断（1 小时以上）

针对 60～180 分钟等长视频，在基础时长校验后进一步统计字幕在视频前、中、后三个三分之一时段的事件数量，并计算相邻字幕之间最长的无字幕间隔。

- 若字幕事件至少 15 条但某个三分之一时段完全没有字幕，记录“可能是局部翻译或长时间无对白”的提示。
- 若最长无字幕间隔达到 15 分钟或视频时长的 20%（取较大值），记录长空白提示。
- 触发上述提示时，**进入人工审核而不是自动保存**；这只是风险提示，不等于字幕错误。
- 未触发提示也**不意味着对白同步**；整体固定偏移、剪辑差异仍可能无法检测。
- 视频时长超出容差仍按原规则拒绝自动下载；长视频允许结束时间最多超出 15 秒。
- 仅分析字幕时间戳，不读取或识别音频；极空间无需 GPU。

## 第一阶段稳定性升级

- **扫描与缓存：** 视频文件大小、修改时间未变化时，已下载、已有外挂字幕、已检测到内嵌中文字幕、带 `-C` 和无法识别番号的状态不会重复请求迅雷接口；文件变化后重新检测。
- **内嵌字幕：** `CHECK_EMBEDDED: "true"` 时使用 ffprobe 检查字幕流的语言与标题元数据；发现中文轨道直接跳过。无法读取视频时不会贸然下载，而是记录错误并重试。**没有语言标记的中文轨道可能无法识别。**
- **候选评分：** `SCORE_THRESHOLD: "80"`，唯一候选需先通过时间轴检查，再按字幕文件名的中文标记、格式、版本提示等启发式因素评分；低于阈值进入人工审核。评分不是字幕准确率或音频同步证明。
- **分类退避：** 网络/API 错误使用逐步延长的重试间隔（上限 24 小时），没有字幕则从 `RETRY_HOURS` 开始逐步延长（上限 14 天），人工审核项目 7 天后才自动重新搜索。失败次数持久化在 SQLite 的 `retry_attempts` 表。
- **保留审核候选：** 搜索网络失败时保留此前已找到的候选列表，避免临时 API 故障清空审核队列。
- **注意：** 目前仍是周期性全目录遍历，但不会对未变化的终态视频重复搜索；首次遍历大型媒体库可能耗时较长。不会自动删除数据库中已经从磁盘移除的历史记录。

## 规则与限制

- 默认每 6 小时扫描；失败根据类型和次数退避，新视频至少等待 30 分钟。
- `IPX-123-C.mp4`、`IPX-123-破解-C.mp4` 等含独立 `-C` 标记的影片直接跳过。
- 已有同名外挂字幕的影片跳过；已增加 ffprobe 内嵌中文字幕检测（依赖字幕轨道语言或标题元数据）。
- 自动下载仅处理番号完全一致、字幕名称带中文标记且候选唯一的字幕；多个候选需要在 Web 页面人工选择。
- 不覆盖已有字幕，并检查字幕时间轴是否明显异常；**无法保证字幕时间轴与内容完全正确**。
- 迅雷 API 是第三方接口，可能变更、限流或失效；尚未在极空间 NAS 上完成端到端验证。
- Web 服务没有内置 HTTPS，请**仅在可信局域网使用**，不要向公网开放 8765 端口。
- 容器当前默认以 root 运行以适配 NAS 目录权限，建议有条件时使用最小权限账户。
- 确保所处理的影片和字幕符合适用法律及授权要求。

## 更新镜像

在极空间重新拉取 `latest` 镜像并重建容器即可更新；`docker compose pull && docker compose up -d` 是命令行等价操作。自动构建**不会**自动替你更新 NAS 上正在运行的容器。

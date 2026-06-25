# 频道巡检

基于 tencent-channel-cli 的 AstrBot 原生频道帖子自动巡检插件。

## 功能

- 自动定时巡检频道帖子，通过 AI 审核违规内容
- 支持 AstrBot Provider / 自定义 OpenAI 兼容 API 两种审核模式
- 支持文本审核和图文多模态审核
- 违规帖子自动移到指定版块或仅通知
- Dry-run 模式：先观察 AI 判定准确率，再开启自动移帖
- 通知绑定：任意会话可绑定/解绑接收巡检报告
- CLI 自检：启动时验证 cli 可用性和登录状态

## 配置

通过 AstrBot 管理面板的 `_conf_schema.json` 提供可视化配置，主要项：

| 配置 | 说明 |
|------|------|
| `cli.cli_path` | tencent-channel-cli.cmd 绝对路径 |
| `channel.guild_id` | 目标频道 ID |
| `channel.suspect_channel_id` | 违规帖移动目标版块 ID |
| `review.provider_mode` | 审核模型接入方式 |
| `review.provider_id` | AstrBot 模型提供商 |
| `auto_review.poll_interval_seconds` | 自动巡检间隔（秒） |

## 命令

| 命令 | 说明 |
|------|------|
| `频道巡检 状态` | 查看插件运行状态 |
| `频道巡检 立即执行` | 手动触发一轮巡检 |
| `频道巡检 绑定通知` | 绑定当前会话接收报告 |
| `频道巡检 解绑通知` | 解绑当前会话 |
| `频道巡检 通知列表` | 查看已绑定的通知目标 |
| `频道巡检 最近报告` | 查看最近一次巡检报告 |
| `频道巡检 自检` | 执行 CLI 自检 |

## 依赖

- [tencent-channel-cli](https://github.com/tencent-connect/tencent-channel-cli) — 腾讯频道 CLI 工具
- aiohttp

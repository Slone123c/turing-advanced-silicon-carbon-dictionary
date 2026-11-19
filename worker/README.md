# 词条热度计数 Worker（Cloudflare Workers + KV）

用于给 GitHub Pages 静态词典提供免登录的词条热度计数与排行统计：

- `GET /hot?lang=zh|en`：读取各语言词条热度。
- `POST /hit`：记录热度反馈，内置四层防刷保护：
  - **词条白名单**：只接受 `worker/terms.json`（由 `python3 build_site.py` 自动同步）中的真实词条。
  - **24 小时单条冷却**：同一 IP 对同一词条 24 小时内只计 1 次（IP 经 SHA-256 哈希后存 KV）。
  - **10 分钟单 IP 总频控**：同一 IP 每 10 分钟最多计 15 次跨词条点击。
  - **Origin 白名单**：配置 `ALLOWED_ORIGINS` 后仅接受指定站点来源的 `POST /hit`。
  - **Cloudflare Turnstile 无感验签（可选）**：配置 `TURNSTILE_SECRET_KEY` 后，前端静默附带一次性 `turnstileToken`，Worker 调用 Cloudflare `siteverify` 验签通过才计入 KV，直接拦截 `curl` 与脚本刷量。
- **每 12 小时自动备份到 GitHub Gist**：通过 Cron Trigger（`0 8,20 * * *`，北京时间 04:00 / 16:00）把 `counts:zh` 与 `counts:en` 快照更新到同一个 Secret Gist（数据无变化时自动跳过，利用 Gist Revisions 保留历史快照）。

## 部署步骤

1. 在仓库根目录生成最新词条白名单 `worker/terms.json`：

```bash
python3 build_site.py
```

2. 在 `worker/` 目录创建 KV 命名空间并把返回的 `id` 填入 `wrangler.toml`：

```bash
cd worker
npx wrangler kv namespace create HOT_KV
```

3. （推荐）在 `worker/wrangler.toml` 的 `[vars]` 中填入线上域名与 Secret Gist 信息：
   - `ALLOWED_ORIGINS`：你的线上站点域名（如 `"https://slone123c.github.io"`，多个域名用逗号分隔）
   - `GIST_ID`：新建一个 GitHub Secret Gist 后的 ID
   - 如需绑定备用域名（推荐，用于开启 Cloudflare WAF 边缘限流），取消注释 `wrangler.toml` 中的 `routes` 并改为你的子域名（如 `hot.example.com`）。
   - 通过 secret 写入敏感密钥（不会进入代码库）：

```bash
# 12 小时 Gist 备份（仅勾选 gist 权限的 GitHub PAT）
npx wrangler secret put GITHUB_TOKEN
# Turnstile 无感验签（在 Cloudflare Turnstile 创建 Non-interactive/Managed 小组件后获取 Secret Key）
npx wrangler secret put TURNSTILE_SECRET_KEY
# 可选：为 IP 脱敏加盐（任意随机字符串）
npx wrangler secret put IP_SALT
```

4. 发布 Worker，拿到类似 `https://sic-dict-hot.<你的子域>.workers.dev` 的地址：

```bash
npx wrangler deploy
```

5. 在 GitHub 仓库的 **Settings → Secrets and variables → Actions → Variables** 新增以下 Variables：
   - `HOT_API_URL`：你的 Worker 地址（推荐填绑好的备用域名，如 `https://hot.example.com`，末尾不加 `/`）
   - `TURNSTILE_SITE_KEY`：（可选）Cloudflare Turnstile 的 Site Key，与上面的 `TURNSTILE_SECRET_KEY` 配对使用

6. 重新触发一次 GitHub Pages 部署即可生效。未配置 `HOT_API_URL` 时，前端会自动降级为仅本地计数，不影响词典浏览。

## 备用域名 + WAF 边缘限流（推荐）

把备用域名托管到 Cloudflare 并绑定到 Worker（如 `hot.example.com`）后，可在 Cloudflare 控制台免费配 1 条 **Security → WAF → Rate limiting rules**，在请求进入 Worker 之前就拦掉高频脚本（不消耗 Worker/KV 额度）：

- **When incoming requests match**：
  - `Hostname` equals `hot.example.com`
  - AND `URI Path` equals `/hit`
  - AND `Request Method` equals `POST`
- **With the same characteristics**：`IP`
- **If requests exceed**：`5` requests per `10 seconds`
- **Then take action**：`Block`

## 本地测试定时备份

```bash
cd worker
npx wrangler dev --port 8787 --test-scheduled
# 另开终端手动触发一次 Cron：
curl "http://127.0.0.1:8787/__scheduled"
```

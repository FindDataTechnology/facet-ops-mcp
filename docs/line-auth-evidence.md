# facet 线清单的授权证据（仓内，不公开）

`line-manifest.json` 的每个字符串都会随 `/.well-known/line-manifest.json` **匿名公开**，
所以自由文本一律留在本文件、不进清单。下面各段是 2026-11-15 从清单里逐字搬出来的原文
（当时 `note` 字段值），保留行号与路径以便复核；清单只留产品语义。

## `note`

一个镜像两个面：registry 面 facet-ops-mcp（:31892，entry /facet-ops-mcp）与 market 面 facet-market-mcp（:31893，entry /facet-market-mcp），由 FACET_OPS_FACE 切脸（README.md:3-11；tool-surface.market.json 7 工具）。本清单同时覆盖两面——8.3 点名的 facet-market 就在这里，它在发现模型里不占独立 slug。surfaces.account=false：facet.finddatatech.cloud 有策展/供应商成交读面，但没有按客户的用量/账单面（钱在词元面板读）。surfaces.admin=false：/api/ops/pack-usage 要 admin 组（平台侧实现:95-96,212-219）、策展 featured 仅管理员，管理动作不向平台服务主体开放，故平台不可代做。

## `identity.note`

本仓工具面不解析凭据，只剥 `Bearer ` 前缀后原样转发上游（client.py:48-51）；进站 HTTP 门只做上游探针（auth_gate.py:45-66）。Logto 只在上游市场侧以会话 cookie 进 resolveUser，不作为 Bearer 被接受；词元 sk- 也不接受（平台 facet CLI 明说 sk- 属 sub2api prefs 域）。无断言兑换端点，故 jit_policy=off。

## `auth_tracks[].note`

注册处自铸 JWT（TTL 168h，mcp.finddatatech.cloud 直接登录铸造，平台部署文档）：registry 面（AgentCard 目录）的常命轨，摘掉壹座后仍可用。另有注册处自助 `wgk-` patch key（无自动过期、吊销即时生效，平台注册处维护文档）在注册处 /api 面验得过，但 /api/agents 是否收它无直接证据，故不单列为轨。

## `auth_tracks[].note`

market 面的常命轨：Ed25519 设备凭据经配对/挑战静默续登换 12h app token（平台配对模块、平台网关鉴权模块）；令牌由 facet 自己用 MP_TOKEN_SECRET 铸发与验签，binding 落 facet 数据目录，壹座只持有客户端私钥——所以是线自有轨，不是第三方。

## `auth_tracks[].note`

目标态：客户拿词元钥匙直接打两个面。今天上游明确不收 sk-，8.3 之前客户仍需 registry PAT 或市场设备凭据。

## `billing.note`

钱在词元平面：市场成交结算调 sub2api adjustBalance（subtract、幂等键、按买家 billing account；平台侧实现:250-289），facet 侧 market_purchases 只是 append-only 成交记投影，不是余额真源。MCP 工具调用本身不计费（pack 免费）。客户账单在 token.finddatatech.cloud 读，不在本线。

"""FastMCP 组装 + ASGI 布线（鉴权门 + /health + /.well-known/line-manifest.json）——双面。

face=registry（facet-ops-mcp）：六工具包 registry 网关 AgentCard 面（/api/agents*）。
face=market（facet-market-mcp）：六工具包 facet 市场（/api/packs*）。
不经过 Starlette 路由（mount 的路径改写会让鉴权门判断失真）：显式分发器
先比 /health 与线自描述端点，其余全部交给带门的 MCP 应用。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import SERVER_NAME, tools_market, tools_marketplane
from .auth_gate import AuthGate, AuthGateMiddleware
from .client import RegistryClient
from .config import Settings

INSTRUCTIONS_REGISTRY = (
    "谦面网关操作助手：浏览网关 AgentCard 目录、读详情、查重、登记/更新/启停。"
    "每个调用以你的 registry 凭据（壹座注入）执行，可见范围与权限由 registry 判定。"
    "错误如实透传（401=凭据失效需重连，403=无权限，404=无此条目，unreachable=registry 故障）；"
    "空结果如实为空，绝不编造。写操作前建议先查重并确认属主边界。"
)

INSTRUCTIONS_MARKET = (
    "谦面市场操作助手：浏览 pack 目录、读详情与版本、发布新 pack/新版本、"
    "切换可见性、设置策展分类。每个调用以你的市场凭据（壹座注入，设备配对铸造）执行，"
    "发布需 creators 组。错误如实透传（401=凭据失效需重连，403=无权限/需创作者组，"
    "404=无此 pack，400=清单校验失败带逐条错误）；空结果如实为空，绝不编造。"
    "发布是写操作：先浏览查重，manifest 按创作指南组装，仅作者可发新版本。"
)

_HEALTH_OK = b'{"status":"ok"}'

WELL_KNOWN_PATH = "/.well-known/line-manifest.json"
LINE_MANIFEST_ENV = "LINE_MANIFEST_PATH"
#: 清单是运行期契约：改一次要即时生效，但不能让边缘缓存长期替我们撒谎。
_MANIFEST_CACHE_CONTROL = "public, max-age=300"


def manifest_candidates() -> list[Path]:
    """按优先级列出可能放清单的位置（`LINE_MANIFEST_PATH` 一项即封顶）。

    为什么要链而不是一条：**pip 装进去的包与源码树的 `__file__` 不同**。
    镜像里 pid1 跑的是 console script `/usr/local/bin/facet-ops-mcp`，于是
    `__file__` 落在 site-packages，`parents[1]` 根本不是仓根——清单就在
    `/app/line-manifest.json` 却读不到（lex 线 2026-11-11 真机 404，源码运行验不出来）。
    所以源码树、CWD（镜像 WORKDIR=/app）、与包同级三处依次找。
    """
    override = os.environ.get(LINE_MANIFEST_ENV)
    if override:
        return [Path(override)]
    here = Path(__file__).resolve()
    return [
        here.parents[1] / "line-manifest.json",  # 源码树 / 镜像里包与清单同根
        Path.cwd() / "line-manifest.json",       # pip 装的包：CWD 才是仓根
        here.parent / "line-manifest.json",      # 清单与包同级（兜底）
    ]


def manifest_path() -> Path:
    """实际取用的清单路径；都不存在时返回首选位置（让 404 能点名期望路径）。"""
    candidates = manifest_candidates()
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def manifest_response() -> tuple[int, bytes, list[tuple[bytes, bytes]]]:
    """(status, body, extra_headers)——不读网络、不建会话。

    缺失=404（该面未发布清单，属配置事实）；存在但不可解析=500（属缺陷，
    不能伪装成 404 让调用方以为"本来就没有"）。
    """
    json_headers = [(b"content-type", b"application/json; charset=utf-8")]
    path = manifest_path()
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return 404, b'{"detail":"line-manifest not published"}', json_headers
    except OSError as exc:
        return 500, json.dumps(
            {"detail": f"line-manifest unreadable: {type(exc).__name__}"}).encode(), json_headers
    try:
        json.loads(raw)
    except ValueError:
        return 500, b'{"detail":"line-manifest is not valid JSON"}', json_headers
    return 200, raw, json_headers + [
        (b"cache-control", _MANIFEST_CACHE_CONTROL.encode()),
    ]


def create_server(settings: Settings | None = None) -> "FastMCP":
    from fastmcp import FastMCP

    settings = settings or Settings.from_env()
    if settings.face == "market":
        name, instructions, tools = "facet-market-mcp", INSTRUCTIONS_MARKET, tools_marketplane
    else:
        name, instructions, tools = SERVER_NAME, INSTRUCTIONS_REGISTRY, tools_market
    mcp = FastMCP(name, instructions=instructions)
    client = RegistryClient(
        settings.upstream_base_url, timeout_seconds=settings.timeout_seconds
    )
    tools.register(mcp, client)
    mcp._facet_ops_client = client  # build_app 复用同一实例
    mcp._facet_ops_settings = settings
    return mcp


def build_app(settings: Settings | None = None):
    """完整 ASGI 应用：/health 无门；其余（/mcp）走鉴权门（探针按面注入）。"""
    mcp = create_server(settings)
    client: RegistryClient = mcp._facet_ops_client
    settings_: Settings = mcp._facet_ops_settings
    mcp_app = mcp.http_app(path="/mcp")

    probe_path, _, query = settings_.auth_probe_path.partition("?")
    probe_params: dict = {}
    if query:
        for kv in query.split("&"):
            k, _, v = kv.partition("=")
            probe_params[k] = v
    gate = AuthGateMiddleware(
        mcp_app, AuthGate(client, settings_.auth_cache_ttl_seconds, probe_path, probe_params)
    )

    async def app(scope, receive, send):
        if scope.get("type") == "http":
            path = (scope.get("path") or "").rstrip("/")
            if path == "/health":
                import json as _json
                body = _json.dumps({
                    "status": "ok",
                    "server": "facet-market-mcp" if settings_.face == "market" else SERVER_NAME,
                    "face": settings_.face,
                    "upstream": settings_.upstream_base_url,
                }, ensure_ascii=False).encode()
                await send({"type": "http.response.start", "status": 200,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": body})
                return
            # 线自描述：公开元数据，必须在鉴权门**之前**应答（与 /health 同理），
            # 否则平台/客户在未持有本面凭据时连"这条线认哪些钥匙"都读不到。
            if path == WELL_KNOWN_PATH.rstrip("/"):
                status, body, headers = manifest_response()
                await send({"type": "http.response.start", "status": status,
                            "headers": headers + [(b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await gate(scope, receive, send)

    return app

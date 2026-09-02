"""P10 服务端渲染（T05；SOT §3.12；导出 3 名）。

来源 = D-P10-07（HTML 渲染 = stdlib string.Template，零 Jinja2；
safe_substitute + 值经 html.escape 单点转义，注入面收敛单点）+
v1 web/index.html 零构建静态先例（43.1-11 语义参照，零 import）+
Spec §37（inspector 12 节）/ §38（workbench prompt 史表）页面壳
面（W5 数据面填充；W4 = 页面壳 + index 路由面）。

纪律（D2/D3，P10-INV-10，K8）：

- 模板源 = 3 份 string.Template 源（dict 键闭集 =
  :data:`PAGE_NAMES` = (index, inspector, workbench)；index 页 =
  3 段导航壳（play / inspector / workbench 三 section 内联，
  SOT §3.12 钉）；inspector 页 = 12 节折叠区独立页；workbench 页 =
  prompt 史表独立页）；
- 值经 html.escape 单点转义（app.js 侧零 innerHTML 反钉，SOT §3.9；
  非 str 值先 ``json.dumps(ensure_ascii=False, sort_keys=True)``
  确定性序列化再转义）；
- ``page`` 越界 → PresentationError（code = "presentation_invalid"；
  presentation 单一错误族消费，SOT §3.1）；
- 模板源零 0x5C 0x62（D3 机械面）；行宽 ≤ 100（D2）；零 Jinja2
  import（§3.0 闭集不含 jinja2，face t4 钉）。
"""

from __future__ import annotations

import html
import json
import string
from typing import Final

from src.engine_v2.presentation.view import PresentationError

__all__ = [
    "PAGE_NAMES",
    "PAGE_TEMPLATES",
    "render_page",
]

#: 页名闭集（SOT §3.12；键序钉 = play 页 / inspector 页 / workbench
#: 页）。
PAGE_NAMES: Final[tuple[str, ...]] = ("index", "inspector", "workbench")

#: inspector 12 节名（Spec §37 逐字；序钉；W5 数据面填充消费）。
_INSPECTOR_SECTIONS: Final[tuple[str, ...]] = (
    "world_state",
    "runtime_state",
    "scheduler",
    "active_action",
    "effect_chain",
    "event_chain",
    "authority_decision",
    "producer",
    "causal_root",
    "revision_timeline",
    "branch_replay",
    "intervention_history",
)

#: prompt 史表头（Spec §38 面；序钉）。
_WORKBENCH_COLUMNS: Final[tuple[str, ...]] = (
    "seq",
    "logical_role",
    "base_revision",
    "model",
    "prompt_metadata_ref",
    "response_text",
)


def _inspector_section_body() -> str:
    """12 节折叠区源（Spec §37 12 节名逐字；W5 数据面填充
    ``[data-section]`` body；W4 = 占位破折号）。"""
    lines: list[str] = ['<dl id="inspector-views">']
    for name in _INSPECTOR_SECTIONS:
        lines.append(f"<details><summary>{name}</summary>")
        lines.append(f'<pre class="section-body" data-section="{name}">-</pre>')
        lines.append("</details>")
    lines.append("</dl>")
    return "\n".join(lines)


def _workbench_table_body() -> str:
    """prompt 史表源（Spec §38 面；W5 数据面填充
    ``#prompt-history-body``）。"""
    header = "".join(f"<th>{column}</th>" for column in _WORKBENCH_COLUMNS)
    lines = [
        '<table id="prompt-history">',
        "<thead>",
        f"<tr>{header}</tr>",
        "</thead>",
        '<tbody id="prompt-history-body"></tbody>',
        "</table>",
    ]
    return "\n".join(lines)


def _page_head(title_placeholder: str) -> list[str]:
    """页头源（零构建；styles.css 相对引用；$title 占位）。"""
    return [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{title_placeholder}</title>",
        '<link rel="stylesheet" href="styles.css">',
        "</head>",
        "<body>",
        f"<h1>{title_placeholder}</h1>",
    ]


def _page_tail() -> list[str]:
    """页尾源（app.js 尾部引用；零外部资源，SOT §3.9 零依赖面）。"""
    return [
        '<script src="app.js"></script>',
        "</body>",
        "</html>",
    ]


_INDEX_BODY: Final[list[str]] = [
    "<header>",
    "<nav>",
    '<a href="#play">玩法</a>',
    '<a href="#inspector">检查器</a>',
    '<a href="#workbench">工作台</a>',
    "</nav>",
    "</header>",
    "<main>",
    '<section id="play" class="panel">',
    "<h2>玩法</h2>",
    '<label for="session-input">会话 ID</label>',
    '<input id="session-input" type="text" placeholder="会话 ID" autocomplete="off">',
    '<button id="connect-btn" type="button">连接</button>',
    '<pre id="state-box" class="state-box">未连接</pre>',
    '<form id="action-form">',
    '<input id="action-input" type="text" placeholder="自由文本或命令" autocomplete="off">',
    '<button id="action-btn" type="submit">发送</button>',
    "</form>",
    "<h3>图像槽</h3>",
    '<pre id="image-slot" class="state-box">无图像</pre>',
    '<img id="image-view" alt="实时图像">',
    "</section>",
    '<section id="inspector" class="panel">',
    "<h2>检查器（12 节）</h2>",
    '<button id="inspector-btn" type="button">取检查器数据</button>',
    _inspector_section_body(),
    "</section>",
    '<section id="workbench" class="panel">',
    "<h2>工作台（prompt 史）</h2>",
    '<button id="workbench-btn" type="button">取工作台数据</button>',
    '<pre id="workbench-view" class="state-box">未连接</pre>',
    _workbench_table_body(),
    "</section>",
    "</main>",
]

#: 3 份 string.Template 源（dict 键闭集 = PAGE_NAMES；占位 = $title；
#: index 页 = 3 段导航壳（play 页含状态表 + 输入框 + 图像槽，
#: SOT §3.12 钉）；模板源零 0x5C 0x62，D3）。
PAGE_TEMPLATES: Final[dict[str, str]] = {
    "index": "\n".join(_page_head("$title") + _INDEX_BODY + _page_tail()) + "\n",
    "inspector": "\n".join(
        _page_head("$title")
        + ["<main>", _inspector_section_body(), "</main>"]
        + _page_tail()
    )
    + "\n",
    "workbench": "\n".join(
        _page_head("$title")
        + ["<main>", _workbench_table_body(), "</main>"]
        + _page_tail()
    )
    + "\n",
}


def _stringify(value: object) -> str:
    """值 → 文本（str 原样；非 str = json.dumps 确定性序列化；
    非 JSON-clean → PresentationError fail-loud，P10-INV-10 反钉）。"""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise PresentationError(
            f"渲染上下文值非 JSON-clean：{value!r}",
            code="presentation_invalid",
        ) from exc


def render_page(page: str, **context: object) -> str:
    """服务端渲染（D-P10-07）：string.Template.safe_substitute + 值
    全量 html.escape 单点转义。

    - ``page`` ∈ :data:`PAGE_NAMES`（越界 → PresentationError，
      code = "presentation_invalid"）；
    - context 值 = str 原样（后 escape）；非 str = JSON 确定性序列化
      （后 escape）；
    - 零 Jinja2（§3.0 import 闭集不含 jinja2，face t4 钉）。
    """
    template_text = PAGE_TEMPLATES.get(page)
    if template_text is None:
        raise PresentationError(
            f"页名越界：{page!r}（闭集 = {list(PAGE_NAMES)}）",
            code="presentation_invalid",
        )
    escaped: dict[str, str] = {
        str(key): html.escape(_stringify(value)) for key, value in context.items()
    }
    return string.Template(template_text).safe_substitute(escaped)

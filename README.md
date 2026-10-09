# AstrBot 公式块图片插件

自动将 AstrBot 回复中含有 LaTeX 公式的 Markdown 文本渲染为 PNG 图片，通过标准 `Image` 消息组件发送到 Discord、Telegram、QQ 等聊天平台。

## 安装要求

当前插件依赖 AstrBot 核心提供的 `html_renderer.render_local_markdown()` 本地渲染接口，由离线 KaTeX 和 Chromium 完成公式排版与截图。请使用已经包含该接口及配套离线资源的 AstrBot 环境；元数据中的 `>=4.22.1` 是版本约束，不能保证每个官方版本都具备此接口。

在插件根目录中，使用 AstrBot 实际运行的 Python 环境安装依赖，并一次性安装 Chromium：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

安装 Playwright 和 Chromium 不会自动补充 AstrBot 核心的本地渲染接口。

## 使用方式

启用插件后会自动处理完整的模型回复，无需手动调用命令。支持 `$$...$$`、`\[...\]` 显示公式，以及 `$...$`、`\(...\)` 行内公式；代码块内部的公式标记不参与识别。

含公式的文本按完整段落和公式块合并分段，默认每张图片的目标长度为 **1600 个 Markdown 源文字符**。行内公式随正文渲染，完整公式不会截断，因此单个超长公式可能超过目标长度。流式输出的中间片段会跳过，最终完整回复才进行处理。

在 AstrBot 插件配置中可以调整以下选项：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 启用公式图片渲染。 |
| `scope` | `model` | 仅处理模型回复；设为 `all` 时处理所有待发送结果。 |
| `max_chars` | `1600` | 每张图片的目标源文字符数，完整公式不截断。 |
| `send_source` | `false` | 设为 `true` 时，在每张图片后附上可复制的 Markdown/LaTeX 代码块。 |
| `prompt_hint` | `true` | 向模型追加固定的公式格式提示，并避免重复追加。 |
| `render_timeout` | `10` | 单次渲染超时，单位为秒。失败后会重试一次。 |
| `platforms` | `[]` | 留空表示所有平台；可填写 `discord`、`telegram`、`aiocqhttp` 或 `qq_official` 等平台标识。 |

## 安全与失败回退

本地渲染器拦截外部网络请求，渲染前清理正文中的原始 HTML 和远程图片目标。KaTeX 使用非信任模式，无法识别的公式命令保留为源码显示。

如果某个分段两次渲染均失败，插件会回退到对应原始文本组件的完整内容，避免只发送部分图片而丢失后续文字。已有的提及、回复和图片等消息组件会保留。

# AstrBot Formula Block Images

This plugin converts LaTeX-bearing Markdown in outgoing AstrBot replies into PNG
images. It uses the offline KaTeX and Chromium renderer provided by AstrBot, so
Discord, Telegram, QQ, and other adapters receive a normal `Image` component.

Install the plugin dependencies once, then install the browser executable:

```bash
pip install -r requirements.txt
playwright install chromium
```

The default configuration processes complete model replies, keeps inline math in
the surrounding paragraph, skips fenced code, and does not attach source text.
Set `send_source` to `true` when users need a copyable Markdown/LaTeX block.

The renderer blocks external network requests and removes raw HTML and remote
image targets before rendering. Invalid KaTeX commands remain visible as source,
and a failed segment falls back to its original text.

#!/usr/bin/env python3
"""把 Obsidian 领队产品手册 markdown 转成自包含单文件 HTML。可重复运行。"""
import re
import subprocess
import sys
import markdown

SRC = "/Users/xinanmacbook/Library/Mobile Documents/iCloud~md~obsidian/Documents/obsidiandata/天狼星项目/产品/9-10 云南之恋 领队产品手册2026-10.md"
OUT = "/tmp/ynzl_manual_web/index.html"
TITLE = "云南之恋 领队产品手册 2026-10（9-10版）"
SRC_NAME = "9-10 云南之恋 领队产品手册2026-10.md"

MD_EXTS = ["tables", "fenced_code", "toc", "attr_list", "sane_lists", "md_in_html"]

CALLOUT_META = {
    "tip": ("💡", "提示"), "info": ("ℹ️", "信息"), "success": ("✅", "成功"),
    "warning": ("⚠️", "警告"), "quote": ("💬", "引用"), "note": ("📝", "备注"),
    "danger": ("🚨", "危险"), "example": ("🎨", "示例"), "question": ("❓", "问题"),
    "todo": ("📋", "待办"), "abstract": ("📄", "摘要"), "failure": ("❌", "失败"),
    "bug": ("🐛", "问题"), "important": ("❗", "重要"), "caution": ("🔶", "注意"),
}


def scan_headings(lines):
    """扫描标题行(跳过围栏代码块)，按出现顺序分配 id，并给标题行注入 {#id}。"""
    headings = []          # (level, text, id)
    first_id = {}          # 标题原文 -> 首个 id
    in_fence = False
    out_lines = list(lines)
    n = 0
    for i, line in enumerate(lines):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if not m:
            continue
        level = len(m.group(1))
        text = re.sub(r"\s+#+\s*$", "", m.group(2)).strip()
        if not text:
            continue
        n += 1
        hid = f"h-{n}"
        headings.append((level, text, hid))
        first_id.setdefault(text, hid)
        out_lines[i] = f"{m.group(1)} {text} {{#{hid}}}"
    return out_lines, headings, first_id


def replace_wikilinks(text, first_id, stats):
    """[[#锚点|别名]] -> 页内锚链接；[[笔记#节|别名]] / [[笔记]] -> 灰底纯文本。"""
    def repl(m):
        body = m.group(1)
        target, _, alias = body.partition("|")
        target = target.strip()
        label = alias.strip() or target.split("#")[-1].strip() or target
        if target.startswith("#"):  # 页内锚点
            anchor = target[1:]
            stats["inpage_total"] += 1
            hid = first_id.get(anchor)
            if hid:
                stats["inpage_ok"] += 1
                return f'<a href="#{hid}">{label}</a>'
            stats["warn"].append(anchor)
            return label  # 降级为纯文本
        # 跨文件链接：纯文本 + 浅灰底纹
        note = target.split("#")[0].strip()
        label2 = alias.strip() or note
        return f'<span class="xlink">{label2}</span>'
    return re.sub(r"\[\[([^\[\]]+?)\]\]", repl, text)


def extract_callouts(text):
    """把 > [!type] 块抽出为占位符，返回(正文, [(占位符, html_inner_markdown, type, fold, title)])"""
    lines = text.split("\n")
    out = []
    callouts = []
    i = 0
    pat = re.compile(r"^>\s*\[!([A-Za-z]+)\]\s*([+-])?\s*(.*?)\s*$")
    while i < len(lines):
        m = pat.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        ctype, fold, title = m.group(1).lower(), m.group(2), m.group(3)
        inner = []
        i += 1
        while i < len(lines) and re.match(r"^>", lines[i]):
            inner.append(re.sub(r"^>\s?", "", lines[i]))
            i += 1
        token = f"@@CALLOUT_{len(callouts)}@@"
        callouts.append((token, ctype, fold, title, "\n".join(inner)))
        out.extend(["", token, ""])
    return "\n".join(out), callouts


def render_callout(ctype, fold, title, inner_md):
    icon, default_name = CALLOUT_META.get(ctype, ("📌", ctype.capitalize()))
    title_html = markdown.markdown(title, extensions=["sane_lists"]) if title else ""
    title_html = re.sub(r"</?p>", "", title_html).strip() or default_name
    body_html = markdown.markdown(inner_md, extensions=MD_EXTS) if inner_md.strip() else ""
    inner_div = f'<div class="callout-body">{body_html}</div>' if body_html else ""
    head = f'<div class="callout-title"><span class="callout-icon">{icon}</span>{title_html}</div>'
    if fold in ("-", "+"):
        open_attr = " open" if fold == "+" else ""
        return (f'<details class="callout callout-{ctype}"{open_attr}>'
                f"<summary>{head}</summary>{inner_div}</details>")
    return f'<div class="callout callout-{ctype}">{head}{inner_div}</div>'


def build_toc(headings):
    """由 h1/h2/h3 生成嵌套目录。"""
    items = [(lv, t, hid) for lv, t, hid in headings if lv <= 3]
    if not items:
        return ""
    root = []
    stack = [(0, root)]  # (level, children_list)
    for lv, text, hid in items:
        node = {"lv": lv, "text": text, "id": hid, "children": []}
        while stack[-1][0] >= lv:
            stack.pop()
        stack[-1][1].append(node)
        stack.append((lv, node["children"]))

    def render(nodes):
        if not nodes:
            return ""
        s = "<ul>"
        for nd in nodes:
            s += (f'<li class="toc-l{nd["lv"]}"><a href="#{nd["id"]}" '
                  f'data-toc="{nd["id"]}">{nd["text"]}</a>{render(nd["children"])}</li>')
        return s + "</ul>"
    return [render(root)]


CSS = r"""
:root{--bg:#fff;--fg:#1f2328;--muted:#6a737d;--accent:#2f6fed;--border:#e3e6ea;
--card:#f7f8fa;--toolbar:rgba(255,255,255,.92);--hl:#fff3bf}
@media (prefers-color-scheme: dark){:root{--bg:#15171a;--fg:#e4e7eb;--muted:#9aa0a6;
--accent:#6ea8fe;--border:#2c3138;--card:#1d2126;--toolbar:rgba(21,23,26,.92);--hl:#5a4d12}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16.5px/1.8 -apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Segoe UI",sans-serif;-webkit-text-size-adjust:100%}
#toolbar{position:fixed;top:0;left:0;right:0;z-index:100;display:flex;align-items:center;gap:10px;
height:52px;padding:0 14px;background:var(--toolbar);backdrop-filter:blur(10px);border-bottom:1px solid var(--border)}
#toolbar .tt{flex:1;font-weight:600;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#toolbar a.btn,#toolbar button.btn{flex:none;font-size:13px;color:var(--accent);background:transparent;
border:1px solid var(--accent);border-radius:8px;padding:4px 10px;text-decoration:none;cursor:pointer}
#progress{position:fixed;top:52px;left:0;height:2.5px;width:0;background:var(--accent);z-index:101;transition:width .08s linear}
#drawer{position:fixed;top:52px;left:0;bottom:0;width:min(300px,84vw);z-index:99;overflow-y:auto;
background:var(--bg);border-right:1px solid var(--border);padding:14px 16px 60px;font-size:14px;
transform:translateX(-105%);transition:transform .25s ease}
#drawer.open{transform:none;box-shadow:0 0 30px rgba(0,0,0,.18)}
#scrim{position:fixed;inset:52px 0 0;z-index:98;background:rgba(0,0,0,.35);display:none}
#scrim.on{display:block}
#drawer ul{list-style:none;margin:0;padding-left:14px}
#drawer>ul{padding-left:0}
#drawer li{margin:2px 0}
#drawer a{display:block;color:var(--fg);text-decoration:none;padding:3px 8px;border-radius:6px;line-height:1.45}
#drawer a:hover{background:var(--card)}
#drawer a.active{background:var(--accent);color:#fff}
.toc-l1>a{font-weight:700}
.toc-l2>a{font-weight:600}
main{max-width:760px;margin:0 auto;padding:78px 18px 80px}
h1,h2,h3,h4,h5,h6{line-height:1.4;scroll-margin-top:70px}
h1{font-size:1.7em;margin:2.6em 0 .8em;padding-top:1.2em;border-top:4px solid var(--border)}
h1:first-of-type{margin-top:.2em;padding-top:0;border-top:none}
h2{font-size:1.38em;margin:1.9em 0 .6em}
h3{font-size:1.16em;margin:1.6em 0 .5em}
h4{font-size:1.05em}
p{margin:.7em 0}
a{color:var(--accent)}
img{max-width:100%}
mark{background:var(--hl);color:inherit;border-radius:3px;padding:0 2px}
hr{border:none;border-top:1px solid var(--border);margin:2em 0}
table{border-collapse:collapse;display:block;overflow-x:auto;max-width:100%;font-size:14.5px}
th,td{border:1px solid var(--border);padding:6px 10px;text-align:left;white-space:nowrap}
th{background:var(--card)}
tr:nth-child(even) td{background:color-mix(in srgb,var(--card) 55%,transparent)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88em;background:var(--card);
border-radius:4px;padding:1px 5px}
pre{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 14px;overflow-x:auto}
pre code{background:none;padding:0}
blockquote{margin:.9em 0;padding:.4em 1em;border-left:3px solid var(--border);color:var(--muted)}
.xlink{background:var(--card);border:1px solid var(--border);border-radius:5px;padding:0 6px;color:var(--muted);font-size:.94em}
.embed-missing{font-style:italic;color:var(--muted)}
li>input[type=checkbox]{margin-right:6px;vertical-align:-1px}
.callout{margin:1em 0;padding:12px 16px;border-radius:10px;background:var(--card);
border-left:4px solid var(--c,#8a9199);font-size:15.5px}
.callout-title{font-weight:600;display:flex;align-items:center;gap:7px;margin-bottom:2px;color:var(--c,#8a9199)}
.callout-body>:first-child{margin-top:.35em}
.callout-body>:last-child{margin-bottom:0}
details.callout summary{cursor:pointer;list-style:none}
details.callout summary::-webkit-details-marker{display:none}
.callout-tip{--c:#00a86b}.callout-success{--c:#00a86b}.callout-info{--c:#2f6fed}.callout-note{--c:#8a9199}
.callout-warning,.callout-caution{--c:#e6a23c}.callout-danger,.callout-failure,.callout-bug{--c:#e5534b}
.callout-quote{--c:#9b59b6}.callout-example{--c:#13a8a8}.callout-question{--c:#d97706}
.callout-todo{--c:#2f6fed}.callout-important{--c:#c678dd}.callout-abstract{--c:#13a8a8}
:target{animation:flash 1.8s ease}
@keyframes flash{0%{background:var(--hl)}70%{background:var(--hl)}100%{background:transparent}}
footer{max-width:760px;margin:0 auto;padding:20px 18px 60px;color:var(--muted);font-size:13px;border-top:1px solid var(--border)}
@media (min-width:1100px){
  #drawer{transform:none;background:transparent;border-right:none}
  body{margin-left:300px}main,footer{margin-left:auto;margin-right:auto}
  #toc-toggle{display:none}
}
"""

JS = r"""
const bar=document.getElementById('progress');
addEventListener('scroll',()=>{const h=document.documentElement;
const p=h.scrollTop/(h.scrollHeight-h.clientHeight);bar.style.width=(p*100)+'%';},{passive:true});
const drawer=document.getElementById('drawer'),scrim=document.getElementById('scrim');
const toggle=()=>{drawer.classList.toggle('open');scrim.classList.toggle('on');};
document.getElementById('toc-toggle').addEventListener('click',toggle);
scrim.addEventListener('click',toggle);
drawer.addEventListener('click',e=>{if(e.target.tagName==='A'&&innerWidth<1100)toggle();});
document.getElementById('back-toc').addEventListener('click',e=>{
  if(innerWidth<1100){e.preventDefault();toggle();}});
const links=[...drawer.querySelectorAll('a[data-toc]')];
const map=new Map(links.map(a=>[a.dataset.toc,a]));
const io=new IntersectionObserver(es=>{
  for(const en of es){if(en.isIntersecting){
    links.forEach(a=>a.classList.remove('active'));
    const a=map.get(en.target.id);if(a){a.classList.add('active');
      a.scrollIntoView({block:'nearest'});}}}
},{rootMargin:'-64px 0px -70% 0px'});
document.querySelectorAll('main h1[id],main h2[id],main h3[id]').forEach(h=>io.observe(h));
"""


def main():
    raw = open(SRC, encoding="utf-8").read()

    # 剥离 YAML frontmatter:--- 开头到下一个独立 --- 行
    if raw.startswith("---\n"):
        end = re.search(r"\n---[ \t]*\n", raw[4:])
        if end:
            raw = raw[4 + end.end():]
            print("已剥离 YAML frontmatter")
        else:
            print("WARN: 找到 frontmatter 开头但无结束 --- 行")

    # 兜底:![[...]] 嵌入 -> 斜体占位文字
    raw = re.sub(r"!\[\[([^\[\]]+?)\]\]",
                 lambda m: f'<span class="embed-missing">[嵌入内容未收录:{m.group(1)}]</span>', raw)

    lines = raw.split("\n")
    lines, headings, first_id = scan_headings(lines)
    text = "\n".join(lines)

    stats = {"inpage_total": 0, "inpage_ok": 0, "warn": []}
    text = replace_wikilinks(text, first_id, stats)
    text = re.sub(r"==([^=\n]+)==", r"<mark>\1</mark>", text)  # 高亮

    text, callouts = extract_callouts(text)
    html = markdown.markdown(text, extensions=MD_EXTS)

    for token, ctype, fold, title, inner in callouts:
        html = html.replace(f"<p>{token}</p>", render_callout(ctype, fold, title, inner))
        html = html.replace(token, "")  # 兜底清理

    # 任务复选框
    html = re.sub(r"(<li>\s*(?:<p>)?\s*)\[ \]",
                  r'\1<input type="checkbox" disabled> ', html)
    html = re.sub(r"(<li>\s*(?:<p>)?\s*)\[[xX]\]",
                  r'\1<input type="checkbox" checked disabled> ', html)

    # 图片懒加载
    html = re.sub(r"<img\b(?![^>]*\bloading=)", '<img loading="lazy"', html)

    toc_html = build_toc(headings)
    gen_time = subprocess.check_output(["date", "+%Y-%m-%d %H:%M:%S %Z"]).decode().strip()

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE}</title>
<style>{CSS}</style>
</head>
<body>
<header id="toolbar">
<button class="btn" id="toc-toggle">☰ 目录</button>
<span class="tt">{TITLE}</span>
<a class="btn" id="back-toc" href="#h-1">返回目录</a>
</header>
<div id="progress"></div>
<div id="scrim"></div>
<nav id="drawer">{toc_html}</nav>
<main>
{html}
</main>
<footer>来源文件:{SRC_NAME}<br>生成时间:{gen_time} · 本文件为自包含单页,可离线阅读。</footer>
<script>{JS}</script>
</body>
</html>"""
    open(OUT, "w", encoding="utf-8").write(doc)

    # ---- 验证 ----
    ids = set(re.findall(r'id="([^"]+)"', doc))
    hrefs = re.findall(r'href="#([^"]+)"', doc)
    dead = [h for h in hrefs if h not in ids]
    print(f"标题总数: {len(headings)}")
    print(f"页内 wikilink 总数: {stats['inpage_total']}, 解析成功: {stats['inpage_ok']}")
    if stats["warn"]:
        print("WARN 未匹配锚点:")
        for w in stats["warn"]:
            print(f"  WARN: [[#{w}]]")
    else:
        print("WARN 未匹配锚点: 0")
    print(f"callout 数量: {len(callouts)}")
    print(f"输出锚链接 <a href=\"#...\"> 数量: {len(hrefs)}")
    assert len(hrefs) > 100, "锚链接数量不足"
    assert not dead, f"存在死链 id: {dead[:10]}"
    assert "[[" not in doc, "存在 [[ 残留"
    assert "![[" not in doc, "存在 ![[ 残留"
    assert "<p>title:" not in doc and "<hr" not in doc.split("<h1")[0][-200:], \
        "frontmatter 可能残留"
    img_lazy = len(re.findall(r'<img loading="lazy"', doc))
    print(f"死链检查: 0 (全部 {len(hrefs)} 个 href 目标存在)")
    print("[[ / ![[ 残留检查: 通过")
    print(f"frontmatter 残留检查: 通过")
    print(f'<img loading="lazy" 数量: {img_lazy}')
    import os
    print(f"输出: {OUT} ({os.path.getsize(OUT)} 字节, {os.path.getsize(OUT)/1024:.1f} KB)")


if __name__ == "__main__":
    main()

# Wukai’s Lab

基于 [Sphinx](https://www.sphinx-doc.org/) 与 [Read the Docs Sphinx Theme](https://sphinx-rtd-theme.readthedocs.io/) 构建的个人技术文档站，内容聚焦 C++、CUDA 与工程实践，部署于 [kwu130.github.io](https://kwu130.github.io)。

## 本地预览

项目要求 Python 3.11 或更高版本。建议使用虚拟环境安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
make html
python -m http.server 8000 --directory _build/html
```

然后访问 <http://localhost:8000>。构建启用了 `-W --keep-going`，Sphinx 警告会让构建失败。

## 写作

文档源文件位于 `docs/`，文章位于 `docs/posts/`。内容使用 MyST Markdown 编写；新文章需要：

1. 在 `docs/posts/` 创建 Markdown 文件并填写标题；
2. 写作期间设置 `draft: true`，并暂不加入目录；
3. 发布时改为 `draft: false`，将文档加入 `docs/index.md` 对应分类的 `toctree`，并在 `docs/topics.md` 添加主题入口；
4. 执行 `make html`，检查交叉引用、目录和搜索索引。

文章 Frontmatter 中设置 `draft: true` 后，构建会排除其页面、搜索索引、RSS 和 Sitemap；如果草稿仍被目录引用，严格构建会失败，避免链接悄悄失效。

历史地址跳转页位于 `docs/_extra/`，构建时会原样复制到站点根目录。`docs/_ext/site_feeds.py` 会在构建结束时生成 RSS 与 Sitemap。

## 发布

推送到 `main` 后，GitHub Actions 安装 Python 依赖、构建 Sphinx 文档，并发布 `_build/html` 到 GitHub Pages。项目也包含 `.readthedocs.yaml`，可直接导入 Read the Docs。

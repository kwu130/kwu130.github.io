# Wukai’s Lab

基于 Astro 构建的个人技术博客，内容聚焦 C++、CUDA 与工程实践，部署于 [kwu130.github.io](https://kwu130.github.io)。

## 本地开发

项目要求 Node.js 22.12 或更高版本，推荐使用 Node.js 24。

```bash
npm install
npm run dev
```

生产构建会依次执行内容与类型检查、Astro 静态生成和 Pagefind 全文索引：

```bash
npm run build
npm run preview
```

## 写作

文章位于 `src/content/posts/`。每篇文章必须包含以下 Frontmatter：

```yaml
title: "文章标题"
description: "用于文章列表和搜索结果的摘要"
publishedAt: 2026-08-13
updatedAt: 2026-08-13
tags:
  - "主题"
slug: "article-slug"
legacyPaths: []
issueNumber: 1
draft: false
```

- `slug` 决定规范链接 `/posts/<slug>/`；
- `legacyPaths` 记录迁移前的地址，历史地址的静态跳转页放在 `public/`；
- `issueNumber` 把 Utterances 评论固定到对应的 GitHub Issue；
- `draft: true` 的文章不会进入生产页面、搜索、RSS 或 Sitemap。

## 发布

推送到 `main` 后，GitHub Actions 使用 Astro 官方 Action 构建并发布到 GitHub Pages。工作流也可以在 Actions 页面手动触发。

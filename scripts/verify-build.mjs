import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, normalize } from "node:path";

const root = new URL("../dist/", import.meta.url).pathname;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function walk(directory) {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

const expectedFiles = [
  "index.html",
  "404.html",
  "rss.xml",
  "sitemap-index.xml",
  "og.png",
  "favicon.jpg",
  "tag.html",
  "post/Valgrind-jian-ce-nei-cun-xie-lou.html",
  "post/CUDA-she-bei-han-shu-zhong-de-long double-lei-xing.html",
  "post/vscode-cha-jian-he-kai-fa-she-zhi.html",
  "posts/valgrind-memcheck/index.html",
  "posts/cuda-device-long-double/index.html",
  "posts/vscode-development-setup/index.html",
  "pagefind/pagefind-entry.json"
];

for (const file of expectedFiles) {
  assert(existsSync(join(root, file)), `缺少构建文件：${file}`);
}

const htmlFiles = walk(root).filter((file) => extname(file) === ".html");
const brokenLinks = [];

for (const htmlFile of htmlFiles) {
  const html = readFileSync(htmlFile, "utf8");
  assert(!html.includes("</html><script"), `${htmlFile} 在 </html> 后仍有脚本`);

  for (const match of html.matchAll(/href=["']([^"']+)["']/g)) {
    const href = match[1];
    if (/^(https?:|mailto:|tel:|data:|#)/.test(href)) continue;

    const cleanHref = decodeURIComponent(href.split(/[?#]/)[0]);
    if (!cleanHref.startsWith("/")) continue;

    let target = normalize(join(root, cleanHref));
    if (cleanHref.endsWith("/")) target = join(target, "index.html");
    if (!extname(target) && !cleanHref.endsWith("/")) target = join(target, "index.html");
    if (!existsSync(target)) brokenLinks.push(`${htmlFile} → ${href}`);
  }
}

assert(brokenLinks.length === 0, `发现失效站内链接：\n${brokenLinks.join("\n")}`);

const articleChecks = [
  ["posts/valgrind-memcheck/index.html", "4", "用 Valgrind"],
  ["posts/cuda-device-long-double/index.html", "5", "long double"],
  ["posts/vscode-development-setup/index.html", "2", "VS Code"]
];

for (const [file, issueNumber, keyword] of articleChecks) {
  const html = readFileSync(join(root, file), "utf8");
  assert(html.includes(`data-issue-number=\"${issueNumber}\"`), `${file} 的 Issue 映射错误`);
  assert(html.includes("application/ld+json"), `${file} 缺少结构化数据`);
  assert(html.includes("rel=\"canonical\""), `${file} 缺少 canonical`);
  assert(html.includes(keyword), `${file} 缺少预期关键词 ${keyword}`);
}

const rss = readFileSync(join(root, "rss.xml"), "utf8");
assert((rss.match(/<item>/g) ?? []).length === 3, "RSS 中的文章数量不是 3");

const pagefindEntry = JSON.parse(readFileSync(join(root, "pagefind/pagefind-entry.json"), "utf8"));
assert(pagefindEntry.languages?.["zh-cn"], "Pagefind 缺少 zh-CN 搜索索引");

console.log(`验证通过：${htmlFiles.length} 个 HTML 文件、3 篇文章、全部站内链接与兼容路由。`);

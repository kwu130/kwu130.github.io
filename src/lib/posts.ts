import { getCollection, type CollectionEntry } from "astro:content";

export type Post = CollectionEntry<"posts">;

export async function getPublishedPosts(): Promise<Post[]> {
  const posts = await getCollection("posts", ({ data }) => !data.draft);
  return posts.sort((a, b) => {
    const dateOrder = b.data.publishedAt.valueOf() - a.data.publishedAt.valueOf();
    return dateOrder || a.data.slug.localeCompare(b.data.slug);
  });
}

export function getReadingTime(body: string): number {
  const chineseCharacters = body.match(/[\u3400-\u9fff]/g)?.length ?? 0;
  const latinWords = body
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[\u3400-\u9fff]/g, " ")
    .match(/[A-Za-z0-9_+#.-]+/g)?.length ?? 0;
  return Math.max(1, Math.ceil(chineseCharacters / 300 + latinWords / 220));
}

export function formatDate(date: Date): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Shanghai"
  }).format(date);
}

export function getTagCounts(posts: Post[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const post of posts) {
    for (const tag of post.data.tags) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }
  return new Map([...counts].sort(([a], [b]) => a.localeCompare(b, "zh-CN")));
}

const TAG_SLUGS: Record<string, string> = {
  "C/C++": "cpp",
  "CUDA": "cuda",
  "调试": "debugging",
  "开发工具": "developer-tools",
  "VS Code": "vscode"
};

export function tagSlug(tag: string): string {
  const knownSlug = TAG_SLUGS[tag];
  if (knownSlug) return knownSlug;

  const asciiSlug = tag
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  if (asciiSlug) return asciiSlug;

  return `tag-${[...tag].map((character) => character.codePointAt(0)?.toString(16)).join("-")}`;
}

export function tagHref(tag: string): string {
  return `/tags/${tagSlug(tag)}/`;
}

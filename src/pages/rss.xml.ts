import rss from "@astrojs/rss";
import { getPublishedPosts } from "../lib/posts";
import { SITE } from "../lib/site";

export async function GET(context: { site: URL }) {
  const posts = await getPublishedPosts();

  return rss({
    title: SITE.title,
    description: SITE.description,
    site: context.site,
    items: posts.map((post) => ({
      title: post.data.title,
      description: post.data.description,
      pubDate: post.data.publishedAt,
      link: `/posts/${post.data.slug}/`,
      categories: post.data.tags
    })),
    customData: `<language>zh-CN</language>`
  });
}

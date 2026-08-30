from __future__ import annotations

from datetime import date, datetime, time, timezone
from email.utils import format_datetime
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml
from sphinx.application import Sphinx
from sphinx.config import Config


SITE_URL = "https://kwu130.github.io"
POST_PREFIX = "posts/"


def _absolute_url(app: Sphinx, docname: str) -> str:
    target = app.builder.get_target_uri(docname).lstrip("/")
    return f"{SITE_URL}/{target}"


def _rfc2822(value: object) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        parsed = datetime.fromisoformat(str(value))

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return format_datetime(parsed)


def _write_xml(path: Path, root: ET.Element) -> None:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _metadata_list(value: object) -> list[object]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else [parsed]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _metadata_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _front_matter(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    try:
        closing = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        return {}

    parsed = yaml.safe_load("\n".join(lines[1:closing]))
    return parsed if isinstance(parsed, dict) else {}


def _draft_documents(app: Sphinx) -> list[tuple[str, str]]:
    drafts: list[tuple[str, str]] = []
    posts_dir = Path(app.srcdir) / POST_PREFIX
    for path in posts_dir.rglob("*.md"):
        if not _metadata_bool(_front_matter(path).get("draft", False)):
            continue
        relative = path.relative_to(app.srcdir)
        drafts.append((relative.with_suffix("").as_posix(), relative.as_posix()))
    return drafts


def _exclude_drafts(app: Sphinx, config: Config) -> None:
    patterns = list(config.exclude_patterns)
    for _, relative in _draft_documents(app):
        if relative not in patterns:
            patterns.append(relative)
    config.exclude_patterns = patterns


def _remove_draft_outputs(app: Sphinx, output: Path) -> None:
    output_root = output.resolve()
    for docname, relative in _draft_documents(app):
        candidates = [
            Path(app.builder.get_outfilename(docname)),
            output / "_sources" / f"{relative}.txt",
        ]
        for candidate in candidates:
            resolved = candidate.resolve()
            if not resolved.is_relative_to(output_root):
                raise RuntimeError(f"Refusing to remove path outside build output: {resolved}")
            resolved.unlink(missing_ok=True)

        parent = Path(app.builder.get_outfilename(docname)).resolve().parent
        while parent != output_root and parent.is_relative_to(output_root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


def _generate_sitemap(app: Sphinx, output: Path) -> None:
    namespace = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urlset = ET.Element("urlset", xmlns=namespace)

    for docname in sorted(app.env.found_docs):
        metadata = app.env.metadata.get(docname, {})
        if _metadata_bool(metadata.get("draft", False)):
            continue
        url = ET.SubElement(urlset, "url")
        ET.SubElement(url, "loc").text = _absolute_url(app, docname)
        updated = metadata.get("updatedAt")
        if updated:
            ET.SubElement(url, "lastmod").text = str(updated)

    _write_xml(output / "sitemap-0.xml", urlset)

    sitemap_index = ET.Element(
        "sitemapindex", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
    )
    sitemap = ET.SubElement(sitemap_index, "sitemap")
    ET.SubElement(sitemap, "loc").text = f"{SITE_URL}/sitemap-0.xml"
    _write_xml(output / "sitemap-index.xml", sitemap_index)


def _generate_rss(app: Sphinx, output: Path) -> None:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Wukai’s Lab"
    ET.SubElement(channel, "link").text = f"{SITE_URL}/"
    ET.SubElement(channel, "description").text = "C++、CUDA 与工程实践笔记"
    ET.SubElement(channel, "language").text = "zh-CN"

    posts: list[tuple[datetime, str, dict[str, object]]] = []
    for docname in app.env.found_docs:
        if not docname.startswith(POST_PREFIX):
            continue
        metadata = app.env.metadata.get(docname, {})
        if _metadata_bool(metadata.get("draft", False)):
            continue
        published = metadata.get("publishedAt")
        if not published:
            continue
        sort_date = datetime.fromisoformat(str(published))
        posts.append((sort_date, docname, metadata))

    for _, docname, metadata in sorted(posts, reverse=True):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = str(metadata.get("title", docname))
        url = _absolute_url(app, docname)
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "guid", isPermaLink="true").text = url
        ET.SubElement(item, "description").text = str(metadata.get("description", ""))
        ET.SubElement(item, "pubDate").text = _rfc2822(metadata["publishedAt"])
        for tag in _metadata_list(metadata.get("tags", [])):
            ET.SubElement(item, "category").text = str(tag)

    _write_xml(output / "rss.xml", rss)


def _on_build_finished(app: Sphinx, exception: Exception | None) -> None:
    if exception is not None or app.builder.format != "html":
        return

    output = Path(app.outdir)
    _remove_draft_outputs(app, output)
    _generate_sitemap(app, output)
    _generate_rss(app, output)


def setup(app: Sphinx) -> dict[str, object]:
    app.connect("config-inited", _exclude_drafts)
    app.connect("build-finished", _on_build_finished)
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }

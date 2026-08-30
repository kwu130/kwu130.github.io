from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent / "_ext"))


project = "Wukai’s Lab"
author = "Wukai"
copyright = f"{datetime.now().year}, {author}"

extensions = [
    "myst_parser",
    "site_feeds",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
master_doc = "index"
language = "zh_CN"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "html_admonition",
    "html_image",
    "smartquotes",
    "strikethrough",
    "tasklist",
]
myst_heading_anchors = 4
myst_title_to_header = True

html_theme = "sphinx_rtd_theme"
html_title = "Wukai’s Lab"
html_short_title = "Wukai’s Lab"
html_baseurl = "https://kwu130.github.io/"
html_static_path = ["_static"]
html_extra_path = ["_extra"]
html_css_files = ["custom.css"]
html_js_files = ["site.js"]
html_favicon = "_static/favicon.jpg"
html_logo = "_static/favicon.jpg"
html_show_sourcelink = True
html_show_sphinx = False
html_show_copyright = True
html_last_updated_fmt = "%Y-%m-%d"
html_theme_options = {
    "logo_only": False,
    "prev_next_buttons_location": "bottom",
    "style_external_links": True,
    "style_nav_header_background": "#2f4650",
    "collapse_navigation": False,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

html_context = {
    "display_github": True,
    "github_user": "kwu130",
    "github_repo": "kwu130.github.io",
    "github_version": "main",
    "conf_py_path": "/docs/",
}

templates_path = ["_templates"]

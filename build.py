#!/usr/bin/env python3
from __future__ import annotations
from argparse import ArgumentParser, BooleanOptionalAction, Namespace
from datetime import date, datetime
from pathlib import Path
from re import Match
from xml.etree.ElementTree import Element, SubElement
import dataclasses
import re
import shutil
import sys

from PIL import Image
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markdown.core import Markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import ImageInlineProcessor, IMAGE_LINK_RE
from pymdownx.highlight import HighlightExtension
from pymdownx.superfences import SuperFencesCodeExtension
import yaml

PUBLIC_URL = 'https://pentest.party'
TEMPLATE_DIR = Path('./templates')
OUTPUT_DIR = Path('./public')
CONTENT_DIR = Path('./content')


class MarkdownFile(Markdown):
    def __init__(self, page: Page, pages: list[Page], **kwargs) -> None:
        self.page = page
        self.pages = pages
        self.links = set()
        super().__init__(**kwargs)


# based on https://github.com/Evidlo/markdown_captions/blob/fe7dcb63050930ad25b786fe1ae2524400f5de56/markdown_captions/markdown_captions.py
class ImageCaptionInlineProcessor(ImageInlineProcessor):
    def __init__(self, pattern: str) -> None:
        super().__init__(pattern)

    def handleMatch(self, m: Match, data: str) -> tuple[Element|str|None, int|None, int|None]:
        text, index, handled = self.getText(data, m.end(0))
        if not handled:
            return None, None, None

        src, title, index, handled = self.getLink(data, index)
        if not handled:
            return None, None, None

        assert isinstance(self.md, MarkdownFile)
        image = Image.open(self.md.page.srcpath.parent/src)

        if src.endswith('.png'):
            src = src.removesuffix('.png') + '.webp'

        fig = Element('figure')

        # click opens image in new tab
        anchor = SubElement(fig, 'a')
        anchor.set('href', src)
        anchor.set('target', '_blank')

        img = SubElement(anchor, 'img')
        img.set('src', src)
        img.set('width', str(image.width))
        img.set('height', str(image.height))
        if title is not None:
            img.set('title', title)
        img.set('alt', text)

        cap = SubElement(fig, 'figcaption')
        cap.text = text

        return fig, m.start(0), index


class ImageCaptionExtension(Extension):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def extendMarkdown(self, md: Markdown|MarkdownFile) -> None:
        self.md = md
        pattern = ImageCaptionInlineProcessor(IMAGE_LINK_RE)
        pattern.md = md
        md.inlinePatterns.register(pattern, 'imagecaption', 151)


@dataclasses.dataclass
class Page:
    srcpath: Path  # relative path to source markdown file in content directory
    dstpath: Path  # relative path to HTML file in public directory
    urlpath: str  # relative path where index files are replaced with parent directory
    title: str  # tile from frontmatter
    template: str|None
    content: str  # markdown content
    plain_content: str  # content without HTML tags
    modified_at: datetime  # last git commit
    authors: list[str]  # git authors
    draft: bool = True  # draft if not committed to git

    @classmethod
    def from_file(cls, srcpath: Path) -> Page:
        assert srcpath.name == 'README.md'

        with open(srcpath) as file:
            try:
                frontmatter = next(yaml.safe_load_all(file))
            except Exception:
                raise ValueError('fronmatter missing or broken')

        relpath = srcpath.relative_to(CONTENT_DIR)
        dstpath = OUTPUT_DIR/relpath.parent/'index.html'
        urlpath = f'{relpath.parent}/'

        assert isinstance(frontmatter, dict)
        post_title = frontmatter['title']
        post_authors = frontmatter['authors']
        post_date = frontmatter['date']
        post_template = frontmatter.get('template')  # TODO: remove
        draft = frontmatter.get('draft', True)
        assert isinstance(post_title, str)
        assert isinstance(post_authors, list)
        assert all(isinstance(x, str) for x in post_authors)
        assert isinstance(post_date, date)
        assert isinstance(draft, bool)
        modified_at = datetime(year=post_date.year, month=post_date.month, day=post_date.day)

        return cls(srcpath=srcpath, dstpath=dstpath, urlpath=urlpath, title=post_title, plain_content='', template=post_template, modified_at=modified_at, authors=post_authors, draft=draft, content='')


# source: https://github.com/pallets/markupsafe/blob/feb1d70c16df62f60dcb521d127fdad8819fc036/markupsafe/__init__.py#L21
HTML_TAG_PATTERN = re.compile(r'(<!--.*?-->|<[^>]*>)')

def preprocess_page(all_posts: list[Page], current_post: Page) -> None:
    file = MarkdownFile(
        current_post,
        all_posts,
        extensions=[
            'meta',
            'tables',
            ImageCaptionExtension(),
            SuperFencesCodeExtension(disable_indented_code_blocks=True),
            HighlightExtension(guess_lang=False, noclasses=False),
        ],
        output_format='html',
    )
    current_post.content = file.convert(current_post.srcpath.read_text())
    current_post.plain_content = HTML_TAG_PATTERN.sub('', current_post.content)


def render_page(environment: Environment, opts: Namespace, all_posts: list[Page], current_post: Page) -> None:
    if current_post.template:
        template = current_post.template
    else:
        template = 'post'
    final_html = environment.get_template(f'{template}.html').render(page=current_post, options=opts, pages=all_posts)
    current_post.dstpath.write_bytes(final_html.encode('utf-8', errors='xmlcharrefreplace'))


def do_work(opts: Namespace) -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir()

    print(f'loading posts', file=sys.stderr)
    posts: list[Page] = []
    for srcpath in CONTENT_DIR.glob('posts/*/*/README.md'):
        post = Page.from_file(srcpath)
        if opts.dev or not post.draft:
            posts.append(post)
    posts = list(reversed(sorted(posts, key=lambda p: p.modified_at)))

    print(f'copying posts', file=sys.stderr)
    for post in posts:
        dest = post.dstpath.parent
        dest.mkdir(parents=True, exist_ok=True)
        for path in post.srcpath.parent.iterdir():
            if not path.is_file():
                raise ValueError('post directory most contain only files')
            if path.name == 'README.md':
                continue
            shutil.copy(path, dest)

    print(f'preprocess pages', file=sys.stderr)
    index_page = Page.from_file(CONTENT_DIR/'README.md')
    preprocess_page(posts, index_page)
    for post in posts:
        preprocess_page(posts, post)

    print(f'rendering pages', file=sys.stderr)
    environment = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False, undefined=StrictUndefined)
    render_page(environment, opts, posts, index_page)
    for post in posts:
        render_page(environment, opts, posts, post)

    print(f'converting images', file=sys.stderr)
    for org_path in OUTPUT_DIR.glob('posts/**/*.png'):
        new_path = org_path.with_suffix('.webp')
        image = Image.open(org_path)
        image.save(new_path, 'webp')
        org_path.unlink()

    print(f'copying static files', file=sys.stderr)
    shutil.copytree('./static', OUTPUT_DIR/'static')

    print(f'copying robots.txt', file=sys.stderr)
    shutil.copy2('./robots.txt', OUTPUT_DIR/'robots.txt')


def main() -> None:
    entrypoint = ArgumentParser()
    entrypoint.add_argument('-d', '--dev', action=BooleanOptionalAction)
    opts = entrypoint.parse_args()
    opts.public_url = PUBLIC_URL
    do_work(opts)


if __name__ == '__main__':
    main()

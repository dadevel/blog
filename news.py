#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime, format_datetime
from urllib.request import Request, urlopen
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

ATOM = '{http://www.w3.org/2005/Atom}'
CONTENT = '{http://purl.org/rss/1.0/modules/content/}'
DC = '{http://purl.org/dc/elements/1.1/}'
TITLE = 'Pentest Party News Aggregator'
MAX_AGE = timedelta(days=30)


def fetch_feed(url: str) -> ET.Element:
    request = Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.7727.56 Safari/537.36',
        },
    )
    with urlopen(request, timeout=10) as response:
        body = response.read().strip()
    return ET.fromstring(body)


def _parse_rss_date(text: str) -> datetime|None:
    try:
        return parsedate_to_datetime(text)
    except Exception:
        return None


def _parse_iso_date(text: str) -> datetime|None:
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(text.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def to_rfc2822(dt: datetime) -> str:
    return format_datetime(dt)


def _text(el: ET.Element|None) -> str:
    return (el.text or '').strip() if el is not None else ''


def normalize_rss_item(item: ET.Element, source: str) -> tuple[ET.Element, datetime]:
    out = ET.Element('item')

    # title
    title = _text(item.find('title')) or 'Untitled'
    ET.SubElement(out, 'title').text = f'{source}: {title}'

    # link
    link = _text(item.find('link')) or _text(item.find('guid'))
    ET.SubElement(out, 'link').text = link

    # guid
    guid_el = item.find('guid')
    guid = _text(guid_el) if guid_el is not None else link
    g = ET.SubElement(out, 'guid')
    g.text = guid
    g.set('isPermaLink', 'false')

    # description / content
    description = (
        _text(item.find(f'{CONTENT}encoded'))
        or _text(item.find('description'))
        or ''
    )
    ET.SubElement(out, 'description').text = description[:200].rstrip() + ' ...'

    # author (dc:creator fallback)
    author = _text(item.find('author')) or _text(item.find(f'{DC}creator'))
    if author:
        ET.SubElement(out, 'author').text = author

    # pubDate
    raw_date = _text(item.find('pubDate')) or _text(item.find(f'{DC}date'))
    dt = _parse_rss_date(raw_date) or _parse_iso_date(raw_date) or datetime.min.replace(tzinfo=timezone.utc)
    ET.SubElement(out, 'pubDate').text = to_rfc2822(dt)

    return out, dt


def normalize_atom_entry(entry: ET.Element, source: str) -> tuple[ET.Element, datetime]:
    out = ET.Element('item')

    # title
    title = _text(entry.find(f'{ATOM}title')) or 'Untitled'
    ET.SubElement(out, 'title').text = f'{source}: {title}'

    # link (prefer rel=alternate, fall back to first <link>)
    link = ''
    for link_el in entry.findall(f'{ATOM}link'):
        rel = link_el.get('rel', 'alternate')
        href = link_el.get('href', '')
        if rel == 'alternate' and href:
            link = href
            break
        if not link and href:
            link = href
    ET.SubElement(out, 'link').text = link

    # guid from <id>
    guid = _text(entry.find(f'{ATOM}id')) or link
    g = ET.SubElement(out, 'guid')
    g.text = guid
    g.set('isPermaLink', 'false')

    # description from <content> or <summary>
    description = (
        _text(entry.find(f'{ATOM}content'))
        or _text(entry.find(f'{ATOM}summary'))
        or ''
    )
    ET.SubElement(out, 'description').text = description[:200].rstrip() + ' ...'

    # author
    author_el = entry.find(f'{ATOM}author')
    if author_el is not None:
        author = _text(author_el.find(f'{ATOM}name')) or _text(author_el.find(f'{ATOM}email'))
        if author:
            ET.SubElement(out, 'author').text = author

    # pubDate from <published> or <updated>
    raw_date = (
        _text(entry.find(f'{ATOM}published'))
        or _text(entry.find(f'{ATOM}updated'))
    )
    dt = _parse_iso_date(raw_date) or _parse_rss_date(raw_date) or datetime.min.replace(tzinfo=timezone.utc)
    ET.SubElement(out, 'pubDate').text = to_rfc2822(dt)

    return out, dt


def _feed_title(root: ET.Element) -> str:
    if root.tag == f'{ATOM}feed' or root.tag == 'feed':
        title = _text(root.find(f'{ATOM}title'))
    else:
        channel = root.find('channel')
        title = _text(channel.find('title')) if channel is not None else ''
    return title


def extract_items(root: ET.Element, url: str) -> list[tuple[ET.Element, datetime]]:
    source = _feed_title(root)
    if not source:
        parsed_url = urllib.parse.urlparse(url)
        source = parsed_url.hostname

    assert source

    # Atom feed
    if root.tag == f'{ATOM}feed' or root.tag == 'feed':
        return [normalize_atom_entry(e, source) for e in root.findall(f'{ATOM}entry')]

    # RSS 2.0
    channel = root.find('channel')
    if channel is not None:
        return [normalize_rss_item(i, source) for i in channel.findall('item')]

    raise ValueError('unrecognized feed format')


def merge_feeds(urls: list[str]) -> None:
    all_items: list[tuple[ET.Element, datetime]] = []

    errors = 0
    for url in urls:
        print(url, file=sys.stderr)
        try:
            root = fetch_feed(url)
            if root is not None:
                all_items.extend(extract_items(root, url))
        except Exception as e:
            print(f'error: {e} ({e.__class__.__name__})', file=sys.stderr)
            errors += 1
        time.sleep(1)

    cutoff = datetime.now(tz=timezone.utc) - MAX_AGE
    all_items = [(el, dt) for el, dt in all_items if dt >= cutoff]

    all_items.sort(key=lambda x: x[1], reverse=True)

    channel = ET.Element('channel')
    ET.SubElement(channel, 'title').text = TITLE
    ET.SubElement(channel, 'link').text = ''
    ET.SubElement(channel, 'description').text = ''
    ET.SubElement(channel, 'lastBuildDate').text = to_rfc2822(datetime.now(tz=timezone.utc))

    for item, _ in all_items:
        channel.append(item)

    root_out = ET.Element('rss', version='2.0')
    root_out.append(channel)
    ET.indent(root_out)
    print(ET.tostring(root_out, encoding='unicode', xml_declaration=True))

    print(f'{errors} errors', file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f'usage: rss.py FILE', file=sys.stderr)
        exit(1)

    with open(sys.argv[1]) as f:
        urls = [url.rstrip() for url in f.read().splitlines()]
        urls = [url for url in urls if url]
    merge_feeds(urls)

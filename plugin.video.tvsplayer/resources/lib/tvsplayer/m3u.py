# -*- coding: utf-8 -*-
"""M3U / M3U8 playlist parser (no Kodi dependencies, unit-testable).

Understands the usual IPTV-style format:
    #EXTM3U
    #EXTINF:-1 tvg-logo="http://.../logo.png" group-title="News" radio="false",Channel name
    #EXTVLCOPT:http-user-agent=Mozilla/5.0
    http://stream-address
Lines that are just an address (no #EXTINF) are accepted too.

Also serializes store entries back to M3U (export()).
"""
import re

try:
    from urllib.parse import unquote
except ImportError:  # pragma: no cover
    from urllib import unquote

from . import net

TV = "tv"
RADIO = "radio"

# How the channels of a playlist are sorted into the TV / Radio menus
TYPE_AUTO = "auto"
TYPE_TV = "tv"
TYPE_RADIO = "radio"

_ATTRIBUTE = re.compile(r'([\w-]+)="([^"]*)"')
_AUDIO_EXTENSIONS = (".mp3", ".aac", ".ogg", ".opus", ".m4a", ".pls", ".flac", ".wav")


def parse(text, default_group, type_mode=TYPE_AUTO):
    """Returns a list of entries: dict(name, logo, group, url, type)."""
    entries = []
    name = None
    attrs = {}
    group_line = None
    headers = {}

    for raw in text.splitlines():
        line = raw.strip().lstrip("﻿")
        if not line:
            continue
        upper = line.upper()
        if upper.startswith("#EXTINF"):
            header = line.split(":", 1)[1] if ":" in line else ""
            attrs = {k.lower(): v for k, v in _ATTRIBUTE.findall(header)}
            name = _display_name(header)
        elif upper.startswith("#EXTGRP:"):
            group_line = line.split(":", 1)[1].strip()
        elif upper.startswith("#EXTVLCOPT:"):
            # Stream headers some providers need (converted to Kodi's "url|Header=value" syntax)
            option = line.split(":", 1)[1]
            key, _, value = option.partition("=")
            key = key.strip().lower()
            if key == "http-user-agent":
                headers["User-Agent"] = value.strip()
            elif key == "http-referrer":
                headers["Referer"] = value.strip()
        elif line.startswith("#"):
            continue  # #EXTM3U, comments, unknown tags
        else:
            url = line
            title = (name or "").strip() or attrs.get("tvg-name", "").strip() or \
                url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or url
            group = attrs.get("group-title", "").strip() or (group_line or "").strip() or default_group
            url = net.with_headers(url, headers)
            entries.append({
                "name": title,
                "logo": attrs.get("tvg-logo", "").strip(),
                "group": group,
                "url": url,
                "type": _type_of(type_mode, attrs, group, url),
            })
            name, attrs, group_line, headers = None, {}, None, {}
    return entries


def _display_name(header):
    """Text after the first comma outside quotes: '-1 tvg-name="a,b",Name' -> 'Name'."""
    in_quotes = False
    for i, c in enumerate(header):
        if c == '"':
            in_quotes = not in_quotes
        elif c == "," and not in_quotes:
            return header[i + 1:].strip()
    return ""


def _type_of(type_mode, attrs, group, url):
    if type_mode == TYPE_TV:
        return TV
    if type_mode == TYPE_RADIO:
        return RADIO
    path = url.split("|")[0].split("?")[0].lower()
    radio = attrs.get("radio", "").lower() == "true" or \
        attrs.get("tvg-type", "").lower() == "radio" or \
        "radio" in group.lower() or \
        path.endswith(_AUDIO_EXTENSIONS)
    return RADIO if radio else TV


def _attr(value):
    return value.replace('"', "'")


def export(entries):
    """Serialize store entries (dict with name/logo/group/url/type) to M3U text.

    Includes tvg-logo and group-title. Stream headers are written back as #EXTVLCOPT lines.
    """
    lines = ["#EXTM3U"]
    for e in entries:
        raw_url = e.get("url", "")
        
        # Split Kodi's "url|Header=value" syntax
        url_parts = raw_url.split("|", 1)
        base_url = url_parts[0]
        
        lines.append('#EXTINF:-1 tvg-logo="%s" group-title="%s",%s'
                     % (_attr(e.get("logo", "")), _attr(e.get("group", "")), e.get("name", "")))
        
        # Write headers back as EXTVLCOPT if present
        if len(url_parts) > 1:
            headers_str = url_parts[1]
            for pair in headers_str.split("&"):
                key, _, value = pair.partition("=")
                key = key.strip().lower()
                # Apply unquote() to restore spaces and special characters
                value = unquote(value.strip())
                if key == "user-agent":
                    lines.append("#EXTVLCOPT:http-user-agent=%s" % value)
                elif key == "referer":
                    lines.append("#EXTVLCOPT:http-referrer=%s" % value)
        
        lines.append(base_url)
        
    return "\n".join(lines) + "\n"
"""Pure, conservative Markdown navigation with original physical line positions.

The supported block subset is ATX headings with up to three leading spaces,
backtick/tilde fences and indented code. Standalone HTML comments are discarded;
recognizable raw HTML blocks are literal until a blank line, while script, pre,
style and textarea blocks remain literal through their closing tag. Setext and
nested list/quote containers are not interpreted as sections. Heading slugs keep
Unicode letters/numbers/marks, hyphens and underscores, lowercase them, replace
whitespace with hyphens and allocate unique suffixes in document order.

Inline links/images, single-line reference definitions, explicit full/collapsed
references, known shortcut references and HTTP(S)/mailto angle autolinks expose
navigation. Unknown explicit references retain ``target=None``; an unknown bare
``[word]`` is ordinary text. Destinations can be angle-enclosed or have balanced
parentheses, with an optional quoted title. Labels/titles can span prose lines.
Malformed inline syntax stays literal. No paths are resolved or fetched here.

Search text removes recognized Markdown syntax but retains visible labels and
literal code contents. Code spans and escapes shield their contents from link
and emphasis interpretation. Every LF, CRLF or CR physical line retains its own
record, including syntax-only lines rendered as empty strings. This is a small
navigation scanner, not an HTML renderer or a complete CommonMark parser.
"""

import re
from dataclasses import dataclass
from unicodedata import category


@dataclass(frozen=True, slots=True)
class TextLine:
    line: int
    text: str


@dataclass(frozen=True, slots=True)
class Heading:
    level: int
    title: str
    anchor: str
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class MarkdownLink:
    label: str
    target: str | None
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class MarkdownNavigation:
    headings: tuple[Heading, ...]
    links: tuple[MarkdownLink, ...]
    lines: tuple[TextLine, ...]


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*)|[ \t]*)$")
_DEFINITION = re.compile(r"^ {0,3}\[((?:\\.|[^\]\\\n])+)\]:[ \t]*(.*)$")
_AUTOLINK = re.compile(r"<((?:https?://|mailto:)[^<>\s]+)>", re.IGNORECASE)
_RAW_HTML = re.compile(
    r"^ {0,3}</?(?:address|article|aside|base|blockquote|body|caption|center|col|"
    r"colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|"
    r"form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|"
    r"menu|menuitem|nav|noframes|ol|optgroup|option|p|param|section|search|summary|"
    r"table|tbody|td|tfoot|th|thead|title|tr|track|ul)(?=[ \t/>]|$)",
    re.IGNORECASE,
)
_HTML_TAG_LINE = re.compile(r"^ {0,3}</?[a-z][a-z0-9:-]*(?:[ \t]+[^<>]*)?/?>[ \t]*$", re.I)
_HTML_EXPLICIT = re.compile(r"^ {0,3}<(script|pre|style|textarea)(?=[ \t>]|$)", re.I)
_PUNCTUATION = frozenset("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
_REMOVED = 1
_LITERAL = 2
_LABEL = 4


def _physical_lines(body: str) -> list[str]:
    if not body:
        return []
    lines = re.split(r"\r\n|\r|\n", body)
    if lines[-1] == "" and body[-1] in "\r\n":
        lines.pop()
    return lines


def _indented_code(line: str) -> bool:
    columns = 0
    for character in line:
        if character == " ":
            columns += 1
        elif character == "\t":
            columns += 4 - columns % 4
        else:
            break
        if columns >= 4:
            return True
    return False


def _unescape(value: str) -> str:
    return re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~])", r"\1", value)


def _label_key(value: str) -> str:
    return " ".join(_unescape(value).split()).casefold()


def _destination(text: str, start: int, *, inline: bool) -> tuple[str, int] | None:
    """Read a supported target/title and return the first index after its syntax."""
    position = start
    while position < len(text) and text[position].isspace():
        position += 1
    if position == len(text):
        return None
    if inline and text[position] == ")":
        return "", position + 1
    target_start = position
    if text[position] == "<":
        position += 1
        target_start = position
        while position < len(text) and text[position] != ">":
            if text[position] in "\n<":
                return None
            if text[position] == "\\" and position + 1 < len(text):
                position += 1
            position += 1
        if position == len(text):
            return None
        target = text[target_start:position]
        position += 1
    else:
        depth = 0
        while position < len(text):
            character = text[position]
            if character == "\\" and position + 1 < len(text):
                position += 2
                continue
            if character.isspace():
                break
            if character == "(":
                depth += 1
            elif character == ")":
                if depth == 0:
                    break
                depth -= 1
            elif character in "<>":
                return None
            position += 1
        if depth or position == target_start:
            return None
        target = text[target_start:position]
    after_target = position
    while position < len(text) and text[position].isspace():
        position += 1
    if position > after_target and position < len(text) and text[position] in "\"'(":
        closing = ")" if text[position] == "(" else text[position]
        position += 1
        while position < len(text) and text[position] != closing:
            if text[position] == "\\" and position + 1 < len(text):
                position += 1
            position += 1
        if position == len(text):
            return None
        position += 1
        while position < len(text) and text[position].isspace():
            position += 1
    if inline:
        if position >= len(text) or text[position] != ")":
            return None
        position += 1
    elif position != len(text):
        return None
    return _unescape(target), position


def _code_spans(text: str) -> dict[int, tuple[int, int]]:
    """Index the next equal-width delimiter so malformed spans cannot rescan suffixes."""
    spans: dict[int, tuple[int, int]] = {}
    following: dict[int, tuple[int, int]] = {}
    for run in reversed(list(re.finditer(r"`+", text))):
        width = run.end() - run.start()
        if width in following:
            spans[run.start()] = following[width]
        following[width] = (run.start(), run.end())
    return spans


def _label_end(
    text: str,
    start: int,
    code_spans: dict[int, tuple[int, int]],
    cache: dict[int, int | None],
) -> int | None:
    if start in cache:
        return cache[start]
    opened = [start]
    position = start + 1
    while position < len(text):
        character = text[position]
        if character == "\\" and position + 1 < len(text):
            position += 2
            continue
        if character == "`" and (span := code_spans.get(position)) is not None:
            position = span[1]
            continue
        if character == "[":
            opened.append(position)
        elif character == "]":
            cache[opened.pop()] = position
            if not opened:
                return position
        position += 1
    cache.update((opening, None) for opening in opened)
    return None


def _mark(flags: bytearray, start: int, end: int, flag: int) -> None:
    for position in range(start, end):
        flags[position] |= flag


def _emphasis(text: str, flags: bytearray) -> None:
    """Remove paired simple emphasis delimiters; protected code remains literal."""
    opened: dict[str, list[int]] = {}
    position = 0
    while position < len(text):
        character = text[position]
        if character not in "*_~" or flags[position] & (_REMOVED | _LITERAL):
            position += 1
            continue
        end = position + 1
        while end < len(text) and text[end] == character and not flags[end] & _LITERAL:
            end += 1
        marker = text[position:end]
        if len(marker) > 3 or (character == "~" and len(marker) != 2):
            position = end
            continue
        before = text[position - 1] if position else " "
        after = text[end] if end < len(text) else " "
        can_open = not after.isspace() and (character != "_" or not before.isalnum())
        can_close = not before.isspace() and (character != "_" or not after.isalnum())
        stack = opened.setdefault(marker, [])
        if can_close and stack:
            opening = stack.pop()
            _mark(flags, opening, opening + len(marker), _REMOVED)
            _mark(flags, position, end, _REMOVED)
        elif can_open:
            stack.append(position)
        position = end


def _visible(text: str, flags: bytearray, start: int = 0, end: int | None = None) -> str:
    return "".join(
        text[index]
        for index in range(start, len(text) if end is None else end)
        if not flags[index] & _REMOVED or text[index] == "\n"
    )


def _inline(
    text: str, start_line: int, definitions: dict[str, str | None]
) -> tuple[list[str], tuple[MarkdownLink, ...]]:
    flags = bytearray(len(text))
    code_spans = _code_spans(text)
    labels: dict[int, int | None] = {}
    pending: list[tuple[int, int, str | None, int, int]] = []
    position = 0
    line = start_line
    while position < len(text):
        character = text[position]
        if character == "\n":
            line += 1
        if flags[position] & (_REMOVED | _LITERAL):
            position += 1
            continue
        if text.startswith("<!--", position):
            closing_comment = text.find("-->", position + 4)
            comment_end = len(text) if closing_comment < 0 else closing_comment + 3
            _mark(flags, position, comment_end, _REMOVED)
            line += text[position:comment_end].count("\n")
            position = comment_end
            continue
        if character == "\\" and position + 1 < len(text):
            if text[position + 1] in _PUNCTUATION:
                flags[position] |= _REMOVED
                flags[position + 1] |= _LITERAL
            position += 1
            continue
        if character == "`" and (span := code_spans.get(position)) is not None:
            closing, end = span
            width = end - closing
            _mark(flags, position, position + width, _REMOVED)
            _mark(flags, position + width, closing, _LITERAL)
            _mark(flags, closing, end, _REMOVED)
            line += text[position:end].count("\n")
            position = end
            continue
        if character == "[" and not flags[position] & _LABEL:
            label_closing = _label_end(text, position, code_spans, labels)
            if label_closing is not None:
                label = text[position + 1 : label_closing]
                end = label_closing + 1
                target: str | None = None
                recognized = False
                if end < len(text) and text[end] == "(":
                    destination = _destination(text, end + 1, inline=True)
                    if destination is not None:
                        target, end = destination
                        recognized = True
                elif end < len(text) and text[end] == "[":
                    reference_end = _label_end(text, end, code_spans, labels)
                    if reference_end is not None:
                        reference = text[end + 1 : reference_end] or label
                        target = definitions.get(_label_key(reference))
                        end = reference_end + 1
                        recognized = True
                elif _label_key(label) in definitions:
                    target = definitions[_label_key(label)]
                    recognized = True
                if recognized:
                    _mark(flags, position, position + 1, _REMOVED)
                    _mark(flags, label_closing, end, _REMOVED)
                    _mark(flags, position + 1, label_closing, _LABEL)
                    image_start = position
                    if position and text[position - 1] == "!" and not flags[position - 1]:
                        flags[position - 1] |= _REMOVED
                        image_start -= 1
                    pending.append(
                        (
                            position + 1,
                            label_closing,
                            target,
                            line,
                            line + text[image_start:end].count("\n"),
                        )
                    )
        elif character == "<" and (autolink := _AUTOLINK.match(text, position)) is not None:
            end = autolink.end()
            flags[position] |= _REMOVED
            flags[end - 1] |= _REMOVED
            _mark(flags, position + 1, end - 1, _LITERAL)
            pending.append((position + 1, end - 1, autolink.group(1), line, line))
        position += 1
    _emphasis(text, flags)
    links = tuple(
        MarkdownLink(" ".join(_visible(text, flags, start, end).split()), target, first, last)
        for start, end, target, first, last in pending
    )
    return _visible(text, flags).split("\n"), links


def _slug(title: str) -> str:
    return "".join(
        "-" if character.isspace() else character
        for character in title.lower()
        if character.isalnum()
        or category(character).startswith("M")
        or character in "-_"
        or character.isspace()
    )


def scan_markdown(body: str, *, start_line: int = 1) -> MarkdownNavigation:
    """Scan an already decoded body; ``start_line`` is its original file offset."""
    if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 1:
        raise ValueError("start_line must be a positive integer")
    original = _physical_lines(body)
    rendered = list(original)
    modes = ["prose"] * len(original)
    raw_headings: list[tuple[int, int]] = []
    definitions: dict[str, str | None] = {}
    fence_marker: str | None = None
    html_block = False
    html_closing: str | None = None
    for index, line in enumerate(original):
        if html_block:
            if line.strip():
                modes[index] = "literal"
                continue
            html_block = False
        if html_closing is not None:
            if html_closing == "-->":
                rendered[index] = ""
            modes[index] = "literal"
            if html_closing in line.lower():
                html_closing = None
            continue
        fence = _FENCE.match(line)
        if fence_marker is not None:
            if (
                fence is not None
                and fence.group(1)[0] == fence_marker[0]
                and len(fence.group(1)) >= len(fence_marker)
                and not fence.group(2).strip()
            ):
                fence_marker = None
                rendered[index] = ""
            modes[index] = "literal"
        elif fence is not None and (fence.group(1)[0] != "`" or "`" not in fence.group(2)):
            fence_marker = fence.group(1)
            rendered[index] = ""
            modes[index] = "literal"
        elif _indented_code(line):
            modes[index] = "literal"
        elif line.lstrip(" ").startswith("<!--"):
            rendered[index] = ""
            modes[index] = "literal"
            if "-->" not in line:
                html_closing = "-->"
        elif explicit_html := _HTML_EXPLICIT.match(line):
            modes[index] = "literal"
            closing_tag = f"</{explicit_html.group(1).lower()}>"
            if closing_tag not in line.lower():
                html_closing = closing_tag
        elif _RAW_HTML.match(line) or _HTML_TAG_LINE.match(line):
            modes[index] = "literal"
            html_block = True
        elif definition := _DEFINITION.match(line):
            parsed = _destination(definition.group(2), 0, inline=False)
            if parsed is not None:
                definitions.setdefault(_label_key(definition.group(1)), parsed[0])
                rendered[index] = ""
                modes[index] = "literal"
        elif heading := _HEADING.match(line):
            rendered[index] = re.sub(r"(?:^|[ \t]+)#+[ \t]*$", "", heading.group(2) or "").strip()
            raw_headings.append((index, len(heading.group(1))))
            modes[index] = "heading"
        elif not line.strip():
            modes[index] = "literal"
    links: list[MarkdownLink] = []
    index = 0
    while index < len(original):
        if modes[index] == "literal":
            index += 1
            continue
        end = index + 1
        if modes[index] == "prose":
            while end < len(original) and modes[end] == "prose":
                end += 1
        text, found = _inline("\n".join(rendered[index:end]), start_line + index, definitions)
        rendered[index:end] = text
        links.extend(found)
        index = end
    ends = [start_line + len(original) - 1] * len(raw_headings)
    stack: list[int] = []
    anchors: list[str] = []
    used: set[str] = set()
    counters: dict[str, int] = {}
    for heading_index, (line_index, level) in enumerate(raw_headings):
        while stack and raw_headings[stack[-1]][1] >= level:
            ends[stack.pop()] = start_line + line_index - 1
        stack.append(heading_index)
        base = _slug(rendered[line_index].strip())
        anchor = base
        while anchor in used:
            counters[base] = counters.get(base, 0) + 1
            anchor = f"{base}-{counters[base]}"
        used.add(anchor)
        anchors.append(anchor)
    return MarkdownNavigation(
        headings=tuple(
            Heading(level, rendered[index].strip(), anchor, start_line + index, end)
            for (index, level), anchor, end in zip(raw_headings, anchors, ends, strict=True)
        ),
        links=tuple(links),
        lines=tuple(TextLine(start_line + index, text) for index, text in enumerate(rendered)),
    )


def section_for_line(
    navigation: MarkdownNavigation, line: int, *, end_line: int | None = None
) -> Heading | None:
    """Return the innermost section enclosing the entire point or inclusive span."""
    last_line = line if end_line is None else end_line
    return next(
        (
            heading
            for heading in reversed(navigation.headings)
            if heading.start_line <= line <= last_line <= heading.end_line
        ),
        None,
    )

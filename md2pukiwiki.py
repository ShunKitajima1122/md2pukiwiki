import re
import sys
from pathlib import Path
from urllib.parse import quote

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode


BR = "&br;"
MD = (
    MarkdownIt("commonmark", {"html": True, "linkify": True})
    .enable(["table", "strikethrough", "linkify"])
    .disable("html_block")
)
HTML_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
LEGACY_IMAGE = re.compile(r"!([^\n]+\.(?:png|jpe?g|gif|webp|svg))", re.IGNORECASE)


def escape_text(text: str) -> str:
    """Markdownで文字として扱われた記号を、Wiki記法として再解釈させない。"""
    return re.sub(r"[&<>\[\]{}|'~%()]", lambda m: f"&#{ord(m[0])};", text)


def plain_text(text: str) -> str:
    # 入力済みの &br; は維持する。コード内にはこの処理を適用しない。
    return BR.join(escape_text(part) for part in re.split(r"&br;", text, flags=re.I))


def wiki_url(url: str) -> str:
    return quote(url, safe=":/?#@!$&'()*+,;=%~_-")


def image_ref(source: str, *, block: bool = False) -> str:
    if not re.match(r"(?:[a-z][a-z0-9+.-]*:|[./])", source, re.I):
        source = "./" + source
    # ref の引数区切りと衝突する文字を検出する。
    if any(char in source for char in ",()\r\n|"):
        raise ValueError("画像名・画像URLに , ( ) | または改行が含まれています。")
    return f"#ref({source},,50%)" if block else f"&ref({source},,50%);"


def render_inline(tokens) -> str:
    output = []
    index = 0
    marks = {"strong_open": "''", "strong_close": "''",
             "em_open": "'''", "em_close": "'''",
             "s_open": "%%", "s_close": "%%"}

    def explicit_break(token, *, at_end: bool) -> bool:
        return (
            token.type == "html_inline" and HTML_BR.fullmatch(token.content) is not None
        ) or (token.type == "text" and (
            token.content.lower().endswith("&br;") if at_end
            else token.content.lower().startswith("&br;")
        ))

    while index < len(tokens):
        token = tokens[index]
        kind = token.type
        if kind == "text":
            image = LEGACY_IMAGE.fullmatch(token.content.strip())
            output.append(image_ref(image[1]) if image else plain_text(token.content))
        elif kind in ("softbreak", "hardbreak"):
            # 明示した改行に隣接する物理改行を二重に数えない。
            adjacent = (index > 0 and explicit_break(tokens[index - 1], at_end=True)) or (
                index + 1 < len(tokens) and explicit_break(tokens[index + 1], at_end=False)
            )
            if kind != "softbreak" or not adjacent:
                output.append(BR)
        elif kind in marks:
            output.append(marks[kind])
        elif kind == "code_inline":
            # 自動リンクやWiki記法も無効化し、コードを文字として表示する。
            code = "".join(f"&#{ord(char)};" for char in token.content)
            output.append(f"&color(#000000,#F0F8FF){{{code}}};")
        elif kind == "html_inline":
            output.append(BR if HTML_BR.fullmatch(token.content) else escape_text(token.content))
        elif kind == "link_open":
            # 元プログラムと同じく、リンク表示はURLに統一する。
            output.append("[[" + wiki_url(token.attrGet("href") or "") + "]]")
            while index + 1 < len(tokens) and tokens[index + 1].type != "link_close":
                index += 1
            index += 1
        elif kind == "image":
            output.append(image_ref(token.attrGet("src") or ""))
        else:
            raise ValueError(f"未対応のインライン要素: {kind}")
        index += 1
    return "".join(output)


def convert_inline(text: str) -> str:
    """元コードと同じく、文字列を受け取るインライン変換関数。"""
    return render_inline(MD.parseInline(text)[0].children or [])


def inline_node(node: SyntaxTreeNode) -> str:
    return "".join(render_inline(child.token.children or [])
                   for child in node.children if child.type == "inline")


def paragraph(node: SyntaxTreeNode, *, block_image: bool = False) -> str:
    # 元プログラムの独自画像記法 !filename.png も維持する。
    if len(node.children) == 1 and node.children[0].type == "inline":
        match = LEGACY_IMAGE.fullmatch(node.children[0].content.strip())
        if match:
            return image_ref(match[1], block=block_image)
    return inline_node(node)


def convert_table(node: SyntaxTreeNode) -> list[str]:
    rows = [row for section in node.children for row in section.children]
    if not rows:
        return []
    styles = []
    for cell in rows[0].children:
        style = cell.attrGet("style") or ""
        align = "RIGHT" if "right" in style else "LEFT" if "left" in style else "CENTER"
        styles.append(align + ":")
    output = ["|" + "|".join(styles) + "|c"]
    for row in rows:
        cells = [inline_node(cell) for cell in row.children]
        # 先頭の空白で、セル内容の # や ~ がWikiの制御記号になるのを防ぐ。
        line = "| " + " | ".join(cells) + " |"
        if row.children and row.children[0].type == "th":
            line += "h"
        output.append(line)
    return output


def code_lines(content: str) -> list[str]:
    # splitlines()だとコード中の一部の制御文字も改行として扱うため、\nだけで分割する。
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # パーサーが付ける末尾改行のみ除く。
    return [" " + line for line in lines] or [" "]


def render_list(node: SyntaxTreeNode, depth: int, quote_depth: int) -> list[str]:
    level = depth + 1
    if level > 3:
        raise ValueError("PukiWiki標準のリストは3階層までです。入力の階層を減らしてください。")
    marker = ("+" if node.type == "ordered_list" else "-") * level
    output = []
    for item in node.children:
        # 空項目も、親への復帰記号と区別できるよう内容を与える。
        output.append(marker + " " + BR)
        previous = None
        for child in item.children:
            if child.type == "paragraph":
                value = paragraph(child)
                if previous is None:
                    output[-1] = marker + " " + (value or BR)
                elif previous == "paragraph":
                    output[-1] += BR + BR + value
                else:
                    if previous in ("bullet_list", "ordered_list"):
                        output.append(marker)  # 新しい項目を作らず親項目に戻る。
                    output.append("~" + value)
            else:
                if previous in ("bullet_list", "ordered_list"):
                    output.append(marker)
                output.extend(render_block(child, level, quote_depth))
            previous = child.type
    return output


def render_block(node: SyntaxTreeNode, depth: int = 0, quote_depth: int = 0) -> list[str]:
    kind = node.type
    if kind == "paragraph":
        value = paragraph(node, block_image=depth == 0)
        # 通常の文章が |、#、// などで始まっても別のブロックにしない。
        return [value if value.startswith("#ref(") else "~" + value]
    if kind in ("bullet_list", "ordered_list"):
        return render_list(node, depth, quote_depth)
    if kind in ("fence", "code_block"):
        return code_lines(node.content)
    if kind == "table":
        return convert_table(node)
    if kind == "heading":
        if depth or quote_depth:
            # 見出しでコンテナーから脱出しないよう、内部では強調表示にする。
            return ["~''" + inline_node(node) + "''"]
        level = min(int(node.tag[1:]), 3)
        return ["*" * level + " " + inline_node(node)]
    if kind == "hr":
        return ["#hr" if depth or quote_depth else "----"]
    if kind == "blockquote":
        level = quote_depth + 1
        if level > 3:
            raise ValueError("PukiWiki標準の引用は3階層までです。")
        output = [">" * level]
        for child in node.children:
            output.extend(render_block(child, depth, level))
        output.append("<" * level)
        return output
    raise ValueError(f"未対応のブロック要素: {kind}")


def convert_markdown(text: str) -> str:
    # BOMとWindows/Macの改行を正規化する。コード中の空白は削らない。
    text = text.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    tree = SyntaxTreeNode(MD.parse(text))
    blocks = ["\n".join(render_block(node)) for node in tree.children]
    # 空行はトップレベルのブロック間だけに出力する。
    return "\n\n".join(blocks)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Notion/MarkdownをPukiWiki形式へ変換")
    parser.add_argument("input", nargs="?", help="UTF-8入力ファイル。省略時は標準入力")
    parser.add_argument("-o", "--output", help="UTF-8出力ファイル。省略時は標準出力")
    args = parser.parse_args()
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        text = Path(args.input).read_text(encoding="utf-8-sig") if args.input else sys.stdin.read()
        result = convert_markdown(text)
        if args.output:
            Path(args.output).write_text(result + ("\n" if result else ""), encoding="utf-8")
        else:
            print(result, end="\n" if result else "")
    except (OSError, ValueError) as error:
        parser.exit(1, f"変換エラー: {error}\n")


if __name__ == "__main__":
    main()

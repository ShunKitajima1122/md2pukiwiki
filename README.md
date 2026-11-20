# md2pukiwiki

NotionからエクスポートしたMarkdownなど、UTF-8のMarkdownテキストをPukiWiki記法に変換するPythonスクリプトです。生成したテキストをPukiWikiの編集欄に貼り付けて使います。

## セットアップ

Python 3.10以降を用意し、依存パッケージをインストールします。`linkify` はURLの自動リンクに使います。

```sh
python -m pip install "markdown-it-py[linkify]"
```

## 使い方

リポジトリのルートで実行します。入力・出力はUTF-8です。

```sh
# Markdownファイルを変換して保存
python md2pukiwiki.py input.md -o output.txt

# 変換結果を標準出力に表示
python md2pukiwiki.py input.md
```

入力ファイル名を省略すると標準入力から読み込みます。`-o` は `--output` と同じです。

## 変換仕様

- 見出し、箇条書き、番号付きリスト、引用、水平線、表、コードブロックに対応します。見出しのレベル4〜6はレベル3にまとめます。リストと引用はそれぞれ3階層までです。
- 太字、斜体、取り消し線、インラインコード、リンク、画像を変換します。リンクの表示はURLになります。
- 段落内の改行や `<br>` を `&br;` に変換し、段落などのブロック間には空行を入れます。
- Markdown画像と `!filename.png` 形式の画像指定をPukiWikiの `ref` 記法に変換し、表示倍率を50%にします。画像ファイルは別途PukiWiki側に用意してください。

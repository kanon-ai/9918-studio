# Third-party notices / ライセンス確認

本体のPython・JavaScript・CSS・HTML・文書は [MIT](LICENSE) で公開します。UIは標準のCanvasとDOMを使用し、外部JavaScript/CSS、フォント、画像素材を同梱しません。筐体の質感やネジはCSSによる描画です。サンプルは空の原画です。

| 対象 | ライセンス | 配布方法 |
|---|---|---|
| Pillow（検証版12.2.0、要件12.x） | MIT-CMU | setup時にPyPIから利用者がインストール。バイナリは同梱しません |
| Python 3.11以降 | PSF License Agreement | 利用者が別途インストール。実行環境は同梱しません |
| Node.js | Node.js license / MIT等 | 開発時のテストのみ。実行に不要、同梱しません |

Pillowの導入済み配布物のメタデータとLICENSEを確認しました。[公式ライセンス](https://github.com/python-pillow/Pillow/blob/main/LICENSE)、[公式説明](https://pillow.readthedocs.io/en/stable/about.html)、[Pythonライセンス](https://docs.python.org/3/license.html)。確認したPillowライセンス全文は [licenses/Pillow-LICENSE.txt](licenses/Pillow-LICENSE.txt) に収録しています。Pillow wheelに含まれる各ネイティブライブラリの条件は、インストールされる配布物に付属する通知に従ってください。

読み込む画像・AI生成物・ユーザーの制作物には、このリポジトリのMITライセンスを自動適用しません。元画像の権利と生成サービスの利用条件を各自確認してください。MSX、VDP、その他製品名は識別のために使用しており、各権利者の商標です。公式製品・公式提携を示すものではありません。

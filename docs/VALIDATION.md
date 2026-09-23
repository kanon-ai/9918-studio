# 公開版の検証

Windows / Python 3.13 / Pillow 12.2.0 / Node.js 22で検証。

```text
python -m unittest discover -s tests -v
node --check web/app.js
node tests/mode-ui.cjs
python package.py
```

Pythonテストは既知のバイト列、色制約、全コーデックの出力、参考画像、保存、競合、Undo、stdio MCPとローカルHTTPの連携を検証します。Nodeテストは部品範囲、交換、Ctrlドロップでのコピーを検証します。

ブラウザでは左右プレビュー、8/16/32ドット編集範囲、選択枠の追従、画像変換の未確定プレビューとキャンセル、明暗・コントラスト・拡大縮小設定、フレーム追加・再生・停止、折りたたみパネルを確認しました。自動試験で全ブラウザ操作を網羅しているわけではありません。

ZIPはCRCと同梱SHA256SUMS.jsonを検証します。ローカルの制作データや検証用画像は公開物に含めません。実機動作の検証を意味しません。

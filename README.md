# 9918 Studio

TMS9918A（MSX1）のキャラクタ・スプライト・グラフィック素材を、人間とAIで共通編集するローカルアプリです。画面はSCREEN 0〜3とSprite mode 1専用です。初回は空の部品セットから始まり、模様入りサンプルを消す必要はありません。
Windows / Python 3.11以降 / Pillow 12 / モダンブラウザ。クラウド、APIキー、Node.jsは不要です。

## 起動

1. Python 3.11以降をインストールし、PATHに追加します。[Releases](https://github.com/kanon-ai/9918-studio/releases) のZIPを展開し、初回のみ `setup.cmd` を実行します。
2. `start.cmd` を実行すると `http://127.0.0.1:8765` が開きます。既に起動中なら同じアプリを開きます。
3. 次回からは `start.cmd` を実行してください。初回セットアップにはPyPIへの接続が必要ですが、編集はオフラインで使えます。

手動起動: `python server.py`。ブラウザ不要の場合は `python server.py --no-browser`。
ポート変更: `--port 8766`。データ保存先変更: `--data PATH`。別インスタンスは必ず別データフォルダにしてください。
通常起動のコンソールで Ctrl+C を押すと終了。ブラウザを閉じるだけではサーバーは終了しません。

## 編集

- 上部の「新規」からSCREEN 0〜3、スプライトMode 1の空の素材を作成。
- 部品一覧は全体プレビューと統合。数字・カードの隙間・ページ分割をなくし、元の配置と縦横比のまま表示します。「枠に合わせる」で大きく自動調整し、黒い区切り線はON/OFFできます。
- 全体プレビュー上のタイルをドラッグし、移動先のタイルと現在のフレームの画素を交換できます。Ctrlを押したままドロップすると、元の部品を残して移動先へコピーします（移動先の絵は置換）。Ctrlの判定はドロップ時です。交換・コピーは1回のUndoで戻せます。SCREEN 1では交換後も8文字単位の共有色制約が適用され、検証で確認できます。
- 上段左の全体プレビューで選び、右で8×8／16×16／32×32の範囲を拡大編集（TEXTは幅6／12／24）。選択枠は範囲に追従します。描画ツール・戻す・やり直す・固定パレットはキャンバスのすぐ横にあります。
- 「この部品で配置」で部品をコピーし、クリックでマスに配置。「新しい配置面」で別素材にも配置できます。配置は画素のコピーで、元部品の変更は配置済み画素に連動しません。取り込んだスタンプはブラウザを開いている間の作業用データです。
- 「この部品の色設定」でTEXT全体／SCREEN 1の8文字／SCREEN 2の各行／スプライト全体の色を置換。
- 描画は鉛筆、消しゴム、塗りつぶし、線、四角、スポイト。右クリックは色0。各ストロークは1回でUndoできます。
- 反転・回転、フレーム、参考画像、メモ、検証・出力は必要なときだけ開けます。
- 参考画像はPNG/JPEG/WEBP/BMP/GIFを読み込み。下書きとして重ねるか、減色して取り込めます。下書きは原画出力に含まれません。
- 他VDPの既存素材はプロジェクト内に保持し、9918専用画面の一覧には表示しません。9918素材がなければ新規作成画面から始められます。

上段は全体プレビューと編集画面を並べ、下段に横幅いっぱいのフレーム／アニメーションを配置。参考画像・制作メモ・書き出しも下段にまとめています。

キー: B/E/F/L/R/I、Ctrl+Z、Ctrl+Y、Ctrl+Shift+Z、Ctrl+S。

## 画像からキャラクタを作る

1. 「画像取り込み・AIへの指示」を開き、画像をクリック選択またはドロップします。AI生成画像も通常のPNG/JPEG等として読み込めます（このアプリに画像生成機能はありません）。
2. 「下書きとして表示」「9918の色に減色してデータ化」「白黒2値化してデータ化」を切り替え、未確定プレビューを比較します。
3. 拡大縮小（10〜400%、中央基準）、明るさ、コントラストを調整します。減色時はディザ、2値化時はしきい値を設定できます。
4. 「確定して取り込む」で反映。「キャンセル」はデータを変更しません。データ化は現在のフレーム全体を置き換え、1回の「戻す」で取り消せます。
5. 下書きは全体プレビューのみへ重ねます。画像出力には含めません。データ化後は部品単位で描画・配置・アニメーション編集できます。

画像は縦横比を維持して配置し、拡大時に枠外へ出る部分は切り取ります。変換結果は各モードの色制約に近似します。読み込み後に素材・フレームや編集状態が変わった場合は画像を再読込してください。

「編集ログ」は時刻・更新番号・操作・UI/MCPの区別を直近15件表示します。永続記録や過去状態への復元機能ではありません。

## 保存と出力

編集は `data/project.json` に一時ファイル経由で自動保存。プロジェクト保存で全素材・全フレーム・参考画像を含むJSONをダウンロードできます。「開く」は同形式のプロジェクトJSONを復元します。
Undo/Redo履歴は現在のサーバー起動中のみ（最大40操作、画素数によるメモリ制限あり）。更新番号は再起動後も保持。
UIとAIの更新競合はHTTP 409で拒否し、古いデータによる上書きを防ぎます。ブラウザの競合時は描画中の内容をrecovery JSONに退避します。

「書き出し / AI」の内容:

| 出力 | 内容 |
|---|---|
| ZIP | 現在のフレームのバイナリ、ASM、C、PNG、変換後PNG、素材JSON、manifest、検証結果 |
| PNG | 現在のフレーム。スプライトは色0を透明化。参考画像・グリッドは除外 |
| 全フレームPNG | 1行最大8フレーム、左から右・上から下に並べたスプライトシート |
| ASM / C配列 | パターン・色・パレットの名前付きバイト配列をテキスト表示 |
| JSON | 全フレームを含む単一素材JSON（プロジェクトファイルとは別形式） |
| AIレポート | モード、寸法、パレット、メモ、全フレームの色制約診断、更新番号 |

バイナリは**原画素材の部品**であり、BLOADファイル、VRAM全体、完成画面やROMではありません。画面のネームテーブル（SCREEN 3以外）、配置済みスプライト属性、スクロール・レジスタ初期化は出力先で指定してください。形式の詳細は [FORMATS.md](docs/FORMATS.md)。
ZIP内の `encoded-preview.png` は、YJK/YUVなどへの変換後を確認するための画像です。近似誤差RMSEもレポートに入ります。ハードウェアでの動作を証明する画像ではありません。

## 保存形式・MCPの互換範囲

現在のUIはTMS9918A専用です。以下の既存コーデックとMCP APIは、過去のプロジェクトを壊さないために保持しています。UIで選択できるモードの一覧ではありません。

| VDP | 素材形式 |
|---|---|
| TMS9918A | TEXT40 / SCREEN 1・2・3 / Sprite mode 1 |
| V9938 | 上記 + TEXT80 / SCREEN 4〜8 / Sprite mode 2 |
| V9958 | 上記 + SCREEN 10・11（YJK+YAE）・12（YJK） |
| V9968 | V9958系の原画 + RGB555拡張パレット / SCREEN 8 EPAL / Sprite mode 3の4bpp原画 |
| V9990 | P1・P2タイル / 16×16スプライト原画 / B0〜B7の対応色形式（BP2/BP4/BP6/BD8/BD16/YJK/YUV/パレット併用） |

64個のモード・色形式プリセット。V9990 B4以降はBP2/BP4で偶数・奇数Xのパレットバンクを検査します。SCREEN 9は独立したVDPモードではないため別プリセットはありません。
TEXT80の点滅属性、Sprite mode 2のCC/IC/EC・重ね合わせ、V9968の拡縮・半透明属性、V9990 P1の2面合成・スクロール・カーソル、インターレースのページ分割、非公式な複合VDPモードのシミュレーションは対象外です。素材自体を作ることと、画面を構成することは区別しています。
MSX色0の背景色置換やアナログ色の見え方、複数スプライトのライン数上限は、この単独原画プレビューでは再現しません。

V9968は開発中のため、原画形式とパレット転送順を扱い、固定のレジスタ初期化コードは生成しません。実機・現行FPGA・エミュレーターでの最終動作は未検証です。

## MCP / AI操作

`mcp_server.py` はJSON-RPC 2.0、stdio、MCP 2024-11-05互換サーバーです。編集UIと同じローカルAPIに接続します。先にアプリを起動してください。
Codex向けの [codex-config.toml](docs/codex-config.toml)、汎用の [mcp-config.json](docs/mcp-config.json) を同梱。設定例の `C:/path/to/9918-studio` を実際の展開先に置き換え、使用中のMCPクライアントへ登録してください。

公式設定資料: [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)。設定例は公式のstdio `command` / `args` とタイムアウト設定に基づきます。

ツール: `studio_modes` / `studio_state` / `studio_asset` / `studio_create` / `studio_edit` / `studio_import_image` / `studio_validate` / `studio_preview` / `studio_export` / `studio_text`。
`studio_preview` はMCP image contentで画像を返します。`studio_export` は `data/exports` にZIPを保存し、絶対パス・SHA-256・manifestを返します。任意パスへの書き込みやネット上の画像取得は行いません。

推奨の操作順序:

1. `studio_state` で現在の `revision` と素材IDを取得。
2. `studio_asset` で編集内容、`studio_preview` で原画を確認。
3. `studio_edit` に `baseRevision`、`assetId`、`frame`、編集操作を指定。
4. `studio_validate`、`studio_preview` で確認して `studio_export`。

編集例（実際のIDと更新番号に置き換え）:

```json
{"baseRevision":3,"assetId":"abc123","frame":0,"action":"pixels","points":[{"x":2,"y":3,"color":7}]}
```

大きな塗りは `paint_rect` と `x/y/width/height/color`、配列置換は `frame_pixels` と `pixels`。
`transform` は `operation`（flip_x/flip_y/rotate/shift_left/shift_right/shift_up/shift_down/clear）と任意の `x/y/width/height`。
`metadata` はname/notes/palette/reference。`constrain`、`add_frame`、`delete_frame`、`duration`、`duplicate`、`delete`、`undo`、`redo`も利用できます。
直接色の画素値はGRB555整数、それ以外はパレット番号です。座標は0始まり。
ローカルアプリ自体は画像・データを外部に送信しませんが、MCPクライアントへ返した画像やテキストは、そのAIサービスのデータ処理対象になります。

## 検証

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
```

既知のバイト列（SCREEN 2/TEXT/スプライト象限/2bpp/4bpp/RGB555）、色制約、V9990パレット、全プリセットの出力、参考画像、保存・競合・Undo、実stdio MCPプロセス→HTTP→PNG/ZIPを検証。
詳しい実施結果は [VALIDATION.md](docs/VALIDATION.md)。

## ライセンス・免責事項

本体は [MIT License](LICENSE)。依存関係は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)、利用上の制限・データの扱いは [免責事項](docs/DISCLAIMER.md) を参照してください。画像や生成物の権利は元の権利者・利用条件に従います。


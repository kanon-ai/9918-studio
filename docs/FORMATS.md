# 原画形式 / v1

プロジェクトは version=1、assets配列。素材は id/name/chip/mode/width/height/palette/frames/reference/notes。
framesの各要素は pixels（幅×高さの行優先整数配列）とduration（20〜10000ms）。最大64フレーム、1素材4194304画素、プロジェクト8388608画素。寸法上限1024×512。

## バイナリ

| 形式 | 格納 |
|---|---|
| TEXT40/80 | 文字番号順、1文字8byte。上位6bitが6画素。R7用の前景/背景情報をtext-colors.jsonへ |
| SCREEN 1 | 1文字8byte。8文字を共有する色byteをcolors.binへ。前景上位4bit、背景下位4bit |
| SCREEN 2/4 | 1文字8byteと各行の色8byte。最大768文字。バンクの割当・未使用領域のパディングは利用側 |
| SCREEN 3 | 64×48論理画素。1byteの上位nibbleが左、下位が右。canonical names.bin(768byte)とpatterns.bin(1536byte)。PG+(name×8)+(文字行mod4)×2でアクセス |
| SCREEN 5/7、Sprite 3 | 4bpp、左画素が上位nibble、行優先。端数は行末で0埋め |
| SCREEN 6 | 2bpp、左からbit7..6、5..4、3..2、1..0 |
| SCREEN 8 | 1byte GRB332（緑bit7..5、赤4..2、青1..0）。青DACは0/2/4/7の8段階換算 |
| SCREEN 8 EPAL | 1byteパレット番号。V9968拡張パレットと組み合わせる |
| Sprite 1/2 | 8×8は8byte、16×16は左上8行→左下8行→右上8行→右下8行。bit7が左。透明は0 |
| Sprite 1色 | 1byteの色番号。利用側でスプライト属性へセット |
| Sprite 2色 | 16byte。8×8原画でも後半8行を0で埋める。CC/IC/EC=0 |
| V9990 P1/P2 | row-major文字順、各8×8が32byteの4bpp。VRAM内のpattern-areaの行ストライドへ再配置が必要 |
| V9990 Sprite | 16×16、4bpp行優先の原画。VRAMのスプライト原画pitchへ配置するのは利用側 |
| V9990 BP6 | 1byte/画素、下位6bitのパレット番号。6bit連続パックではない |
| V9990 BD8 | GRB332。内部RGB555対応表はR/G=0,4,9,13,18,22,27,31、B=0,11,21,31 |
| V9990 BD16 | little endian 16bit、0GGGGGRRRRRBBBBB。YSビットは0 |
| V9990高解像度BP2/BP4 | 偶数Xと奇数Xで異なるパレット群。編集上は0..3/4..7、または0..15/16..31。出力画素は下位2/4bit、palette.binの奇数群を32番以降に配置 |

パレット転送データ: V9938/V9958はR0B,Gの2byte（各3bit）。V9968 EPALおよびV9990はR,G,Bの3byte（各5bit）。パレット開始番号やVDPレジスタ設定は利用側。
V9990高解像度は64色分のパレットを出力し、使用バンクは0と32。B0〜B3のBP2/BP4、P1/P2、スプライトは選択中の1バンクだけの原画を編集します。
本アプリのV9968パレット付き出力はEPAL有効を前提とします。互換パレットが必要な場合はV9958素材を使用してください。

## YJK / YUV

RGB555原画から横4画素単位で共通J/Kを近似探索します。4byteの下位3bitは順にK下位、K上位、J下位、J上位。上位5bitがY。J/Kは符号付き6bit。
R=clamp(Y+J)、G=clamp(Y+K)、B=clamp((5Y-2J-K)/4)。YUVはGとBを入れ替えます。YAE/PAL併用ではbit3が1なら上位4bitをパレット番号として選択します。
高品質な最適化探索ではなく、共有クロマ候補を限定した近似です。原画との差はmanifestのencodedRMSEとencoded-preview.pngで確認できます。
SCREEN 10/11は同じYJK+YAEデータ表現を使用します。

## 仕様確認に使用した一次資料

- [MSX2 Technical Handbook](https://github.com/Konamiman/MSX2-Technical-Handbook/blob/master/md/Chapter1.md)
- [Yamaha V9990 data book](https://map.grauw.nl/resources/video/yamaha_v9990.pdf)
- [V9968 開発者による拡張パレット解説](https://note.com/thara1129/n/na687088bfd15)
- [V9968 開発元](https://github.com/hra1129/V9968_Cartridge)
- [openMSX V9990BitmapConverter](https://github.com/openMSX/openMSX/blob/master/src/video/v9990/V9990BitmapConverter.cc)
- [openMSX V9990SDLRasterizer](https://github.com/openMSX/openMSX/blob/master/src/video/v9990/V9990SDLRasterizer.cc)
- [openMSX V9990 I/O](https://github.com/openMSX/openMSX/blob/master/src/video/v9990/V9990.cc)
- [YJK解析](https://map.grauw.nl/articles/yjk/)

確認日: 2026-09-23。参照実装のソースは配布物へ取り込まず、格納形式・計算式の照合に利用しています。

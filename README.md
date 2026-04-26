# 中古10サイト横断リサーチ

EC無在庫転売の仕入れリサーチ自動化ツール。型番を入力すると、ヤフオク・メルカリ・ジモティー他10サイトを横断検索し、安い順に商品を一覧表示します。

## 機能

- **10サイト横断検索**: ヤフオク / メルカリ / ジモティー / ハードオフ / オフハウス / セカンドストリート / ラクマ / PayPayフリマ / 駿河屋 / ブックオフ
- **詳細ページ取得**: メルカリ・PayPayフリマ・ラクマは商品詳細ページからフルタイトル・発送元都道府県・商品状態を取得
- **送料計算**: ヤマト / ゆうパック / 佐川急便 / らくらく家財宅急便 の4社対応
- **利益試算**: 販売価格を入力すると各商品カードで利益をリアルタイム表示
- **除外ワード**: ジャンク・通電確認・リモコン等を除外（カタカナ/ひらがな/半角/英大小を統一マッチ）
- **検索履歴**: JSON で永続化、過去の検索を即時呼び出し
- **Excel出力**: ボタンクリックで現在の結果を Excel ダウンロード

## セットアップ

### 必要環境
- Python 3.11+ (3.12 で動作確認済)
- Windows / Linux / macOS

### インストール

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 起動

```bash
python -m streamlit run app.py
```

ブラウザで http://localhost:8501 を開く。Windows なら `start.bat` をダブルクリックでも起動可。

## 構成

```
リサーチ/
├── app.py                 # Streamlit UI
├── run.py                 # CLI 実行
├── start.bat              # Windows用起動スクリプト
├── requirements.txt
├── core/
│   ├── aggregator.py      # 10サイト並列aggregation + filter
│   ├── shipping.py        # 4社送料計算
│   ├── size_extract.py    # サイズ・都道府県抽出
│   ├── history.py         # 検索履歴(JSON)
│   ├── excel_export.py    # Excel生成
│   ├── http.py            # httpx クライアント
│   └── models.py          # Item dataclass
├── scrapers/              # サイト別スクレイパー
│   ├── yahoo_auctions.py
│   ├── mercari.py
│   ├── jmty.py
│   ├── hardoff_netmall.py
│   ├── second_street.py
│   ├── rakuma.py
│   ├── paypay_furima.py
│   ├── surugaya.py
│   └── bookoff_online.py
└── data/                  # 送料データ (JSON)
    ├── shipping_zones.json
    ├── yamato_rates.json
    ├── yupack_rates.json
    ├── sagawa_rates.json
    └── karuraku_kazai_rates.json
```

## 使い方

1. サイドバーの「型番」欄に検索したい型番を入力（例: `Panasonic NR-B18C2`）
2. 「🔍 検索する（10サイト横断）」をクリック → 3〜5分待つ
3. 結果カードで商品を確認、サイト別に絞り込み可能
4. 「販売価格」を入れると各カードに利益試算が表示
5. 「💰 送料計算ツール」で発送元都道府県＋3辺合計cm から4社の送料を試算

## 注意事項

- スクレイピング対象サイトの利用規約を遵守し、個人利用の範囲内で利用してください
- 大量アクセスはレートリミット・規約違反のリスクがあります
- メルカリ等のbot対策により、データセンター IP からのアクセスはブロックされる可能性があります（家庭用IPからの利用推奨）
- 送料データは目安です。実際の料金は各配送業者の公式表で確認してください

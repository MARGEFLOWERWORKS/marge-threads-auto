# MARGE Threads Auto Poster

MARGE（マージュ）のThreads投稿を、**毎日決まった時刻に自動投稿**する仕組みです。
Meta公式のThreads APIを使い、GitHub Actionsで無料運用します。

## 何が起きるか

- 毎日 **日本時間 20:00** に GitHub Actions が起動
- `threads_posts_50.json` から `posted: false` の投稿を1件取り出す
- Threads に投稿する
- 成功したら `posted: true` に書き換えて Git に記録する

50件ある投稿が、毎日1件ずつ自動で流れていきます。

---

## セットアップ手順（全体像）

全部で3ステップです：

1. **Meta Developer側**：アプリを作ってアクセストークンを取る（1〜3日、審査あり）
2. **GitHub側**：このコードをリポジトリに置き、Secretsにトークンを登録
3. **確認**：手動で1件投稿してみて動作確認

---

## ステップ1：Meta Developer側のセットアップ

### 1-1. 前提条件

- **Instagram ビジネスアカウント or クリエイターアカウント** が必要
- それに連携したThreadsアカウントが必要
- 個人アカウントではAPI経由の投稿ができません

Instagramを個人アカウントで使っている場合は、まずアプリでクリエイターアカウントに切り替えてください（無料）。

### 1-2. Meta for Developersでアプリ作成

1. https://developers.facebook.com/ にログイン
2. 右上「マイアプリ」→「アプリを作成」
3. **アプリタイプは「ビジネス」** を選択
4. アプリ名は何でもOK（例：`marge-threads-auto`）

### 1-3. Threads APIを追加

1. アプリのダッシュボードを開く
2. 左メニュー「製品を追加」から「**Threads API**」の「設定」をクリック
3. 追加されると、左メニューに「Threads API」が出てくる

### 1-4. 権限とリダイレクトURIの設定

1. Threads API → 「設定」
2. 必要な権限（スコープ）にチェック：
   - `threads_basic`（必須）
   - `threads_content_publish`（投稿のため必須）
3. **リダイレクトURI** を設定：
   - 自分のサイトがない場合は `https://oauth.pstmn.io/v1/callback` を入れる（Postman経由で認証する）

### 1-5. アクセストークンを取得

ここが一番ややこしいのですが、**Postman** を使うのが一番ラクです：

1. https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api にアクセス
2. 「Run in Postman」でMetaの公式コレクションをインポート
3. Postmanの画面で「Authorization」タブを開く
4. Type = OAuth 2.0 を選択
5. 以下を入力してトークンを取得：
   - Auth URL: `https://threads.net/oauth/authorize`
   - Access Token URL: `https://graph.threads.net/oauth/access_token`
   - Client ID: アプリのID（ダッシュボードで確認）
   - Client Secret: アプリシークレット
   - Scope: `threads_basic,threads_content_publish`
6. 「Get New Access Token」→ Threadsでログイン認可
7. **短期トークン**が返ってくる（1時間有効）

### 1-6. 長期トークンに変換（重要）

短期トークンは1時間で切れるため、**60日有効な長期トークン**に変換します。

以下をターミナルまたはブラウザで実行（`<SHORT_TOKEN>` と `<CLIENT_SECRET>` は置き換え）：

```
https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=<CLIENT_SECRET>&access_token=<SHORT_TOKEN>
```

返ってくる `access_token` が長期トークン。これが **`THREADS_ACCESS_TOKEN`** になります。

### 1-7. Threads User IDを取得

長期トークンを取ったら、以下をブラウザで開く：

```
https://graph.threads.net/v1.0/me?fields=id,username&access_token=<LONG_LIVED_TOKEN>
```

返ってくる `id` が **`THREADS_USER_ID`** です。

### 1-8. アプリ審査（ライブモード移行）

開発モード（Dev Mode）のままだと、自分自身にしか投稿できません。でも自分のアカウントに投稿するだけなら **開発モードのままでOK**。

審査は不要なので、ここはスキップできます。

---

## ステップ2：GitHub側のセットアップ

### 2-1. リポジトリを作る

1. GitHubで新規リポジトリを作成（例：`marge-threads-auto`）
2. **プライベートリポジトリを推奨**（投稿内容が外部から見られないように）
3. このディレクトリ一式をpushする：

```bash
cd threads-auto-poster
git init
git add .
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/<your-username>/marge-threads-auto.git
git push -u origin main
```

### 2-2. GitHub Secretsにトークンを登録

1. リポジトリの「Settings」→「Secrets and variables」→「Actions」
2. 「New repository secret」で2つ登録：
   - `THREADS_ACCESS_TOKEN` ← ステップ1-6で取った長期トークン
   - `THREADS_USER_ID` ← ステップ1-7で取ったUser ID

### 2-3. Actionsを有効化

1. リポジトリの「Actions」タブを開く
2. 「I understand my workflows, go ahead and enable them」をクリック

### 2-4. 動作確認（手動実行）

1. 「Actions」タブ →「Threads Auto Post」
2. 右側「Run workflow」→「Run workflow」ボタン
3. ログを見て、投稿が成功しているか確認
4. Threadsアプリで実際に投稿されているか確認

成功すれば、あとは毎日JST 20:00に勝手に投稿されます。

---

## 投稿時刻を変えたい場合

`.github/workflows/post.yml` の `cron` 行を編集：

```yaml
schedule:
  - cron: '0 11 * * *'   # UTC 11:00 = JST 20:00
```

cronは **UTC基準**なので、日本時間にする場合は **9時間引く**。

- JST 8:00 → UTC 23:00（前日）→ `'0 23 * * *'`
- JST 12:00 → UTC 3:00 → `'0 3 * * *'`
- JST 18:00 → UTC 9:00 → `'0 9 * * *'`
- JST 20:00 → UTC 11:00 → `'0 11 * * *'`（デフォルト）
- JST 22:00 → UTC 13:00 → `'0 13 * * *'`

---

## 投稿を追加・編集したい場合

`threads_posts_50.json` を直接編集してcommit & push。

新しい投稿を足すときは：

```json
{
  "id": 51,
  "text": "ここに本文",
  "posted": false
}
```

の形で追加。`id` は重複しないように注意。

**Claudeに「Threads投稿を追加で10件書いて」と頼めば、`marge-threads-post` スキルが自動で発動して追記用のJSONを作ってくれます。**

---

## ローカルでテストしたい場合

```bash
cd threads-auto-poster

# 1. 仮想環境を作る
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. 依存をインストール
pip install -r requirements.txt

# 3. .env ファイルを作る
cp .env.example .env
# .env を編集して実際のトークンを入れる

# 4. 実行
python post_to_threads.py
```

---

## 注意事項

- **長期トークンは60日で切れる**。期限が近づいたら取り直して、GitHub Secretsを更新する必要があります。自動更新の仕組みを入れたい場合は別途ご相談ください。
- **レート制限**：Threads APIは24時間あたり250投稿まで。1日1投稿なら余裕でセーフ。
- **投稿失敗時**：GitHub Actionsのログ（赤い❌）から原因がわかります。トークン期限切れ、文字数オーバー、ネットワークエラーなど。
- **全件投稿し終わった後**：自動で止まります（「未投稿がありません」とログに出て終了）。新しい投稿をJSONに足せば、また翌日から再開されます。

---

## ファイル構成

```
threads-auto-poster/
├── .github/
│   └── workflows/
│       └── post.yml              # GitHub Actionsの定義（毎日実行）
├── .env.example                  # 環境変数のテンプレ
├── .gitignore
├── README.md                     # このファイル
├── post_to_threads.py            # メインの投稿スクリプト
├── requirements.txt              # Python依存
└── threads_posts_50.json         # 投稿データ（posted状態で管理）
```

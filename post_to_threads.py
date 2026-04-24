#!/usr/bin/env python3
"""
Threads自動投稿スクリプト（画像対応版）

threads_posts_50.json から posted=false の投稿を1件取り出し、
Threads API（Meta Graph API）で投稿する。
成功したら posted=true に更新して JSON を保存する。

画像：
- images/ フォルダに画像ファイル（.jpg/.jpeg/.png）を入れておく
- 投稿ごとに、画像を添えるかどうかを確率で判定（IMAGE_PROBABILITY）
- 添える場合は images/ からランダムに2枚選んでカルーセル投稿
- 画像が2枚未満しかない場合はテキストのみ投稿

使い方:
    python post_to_threads.py

必要な環境変数（.env または GitHub Secrets）:
    THREADS_ACCESS_TOKEN  - Threads Graph APIの長期トークン
    THREADS_USER_ID       - Threads User ID（数字）
    GITHUB_REPOSITORY     - リポジトリ名（GitHub Actions自動設定、例: user/repo）
"""

import json
import os
import random
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------- 設定 ----------
POSTS_FILE = Path(__file__).parent / "threads_posts_50.json"
IMAGES_DIR = Path(__file__).parent / "images"
API_BASE = "https://graph.threads.net/v1.0"
MAX_CHARS = 500  # Threadsの1投稿文字数上限

# 画像を添える確率（0.0 = 絶対添えない, 1.0 = 絶対添える）
# 例：0.5 = 50%の確率で画像付き、50%の確率で文字のみ
IMAGE_PROBABILITY = 1.0

# 画像を添えるときの枚数
IMAGES_PER_POST = 2

# ---------- 環境変数ロード ----------
load_dotenv()
ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
USER_ID = os.environ.get("THREADS_USER_ID")
# GitHub Actions環境では自動で設定される。ローカルテスト時は手動設定可
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")

if not ACCESS_TOKEN or not USER_ID:
    print("ERROR: THREADS_ACCESS_TOKEN と THREADS_USER_ID を環境変数または .env で設定してください", file=sys.stderr)
    sys.exit(1)


# ---------- ユーティリティ ----------
def load_posts():
    """投稿データを読み込む"""
    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_posts(posts):
    """投稿データを保存"""
    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def pick_next_post(posts):
    """未投稿の投稿を1件取得（idの小さい順）"""
    unposted = [p for p in posts if not p.get("posted", False)]
    if not unposted:
        return None
    return min(unposted, key=lambda p: p["id"])


def list_available_images():
    """imagesフォルダ内の画像ファイル一覧を返す"""
    if not IMAGES_DIR.exists():
        return []
    exts = {".jpg", ".jpeg", ".png"}
    return sorted([p for p in IMAGES_DIR.iterdir() if p.suffix.lower() in exts])


def image_to_public_url(image_path: Path) -> str:
    """
    ローカルの画像パスを、GitHub raw URLに変換
    例: images/photo1.jpg -> https://raw.githubusercontent.com/user/repo/main/images/photo1.jpg
    """
    if not GITHUB_REPO:
        raise RuntimeError(
            "GITHUB_REPOSITORY 環境変数が設定されていません。"
            "GitHub Actions環境では自動設定されます。"
        )
    rel_path = image_path.relative_to(Path(__file__).parent).as_posix()
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/{rel_path}"


def decide_images_for_post() -> list:
    """
    この投稿で使う画像を決める。
    - IMAGE_PROBABILITY の確率で画像付き
    - 画像付きならIMAGES_PER_POST枚をランダムに選ぶ
    - 画像が足りない場合はテキストのみ
    戻り値: 画像パスのリスト（空ならテキストのみ投稿）
    """
    # デバッグ情報を詳しく出力
    print(f"  [DEBUG] スクリプトの場所: {Path(__file__).parent}")
    print(f"  [DEBUG] 画像フォルダを探す場所: {IMAGES_DIR}")
    print(f"  [DEBUG] 画像フォルダは存在する？: {IMAGES_DIR.exists()}")
    if IMAGES_DIR.exists():
        all_files = list(IMAGES_DIR.iterdir())
        print(f"  [DEBUG] imagesフォルダ内の全ファイル ({len(all_files)}個):")
        for f in all_files:
            print(f"    - {f.name} (拡張子: {f.suffix})")

    available = list_available_images()
    print(f"  [DEBUG] 認識された画像: {len(available)}枚")
    for img in available:
        print(f"    認識OK: {img.name}")

    print(f"  [DEBUG] IMAGE_PROBABILITY = {IMAGE_PROBABILITY}")
    print(f"  [DEBUG] IMAGES_PER_POST = {IMAGES_PER_POST}")

    if len(available) < IMAGES_PER_POST:
        if len(available) > 0:
            print(f"  画像が{len(available)}枚しかない（{IMAGES_PER_POST}枚必要）のでテキストのみで投稿します")
        else:
            print(f"  画像が0枚のためテキストのみで投稿します")
        return []

    # 確率で画像有無を判定
    if random.random() > IMAGE_PROBABILITY:
        print(f"  今日は文字だけの日（確率{int((1-IMAGE_PROBABILITY)*100)}%に当選）")
        return []

    chosen = random.sample(available, IMAGES_PER_POST)
    print(f"  画像{IMAGES_PER_POST}枚を選択: {[p.name for p in chosen]}")
    return chosen


# ---------- Threads API 呼び出し ----------
def create_text_container(text: str) -> str:
    """テキストのみのコンテナ作成"""
    url = f"{API_BASE}/{USER_ID}/threads"
    params = {
        "media_type": "TEXT",
        "text": text,
        "access_token": ACCESS_TOKEN,
    }
    r = requests.post(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    container_id = data.get("id")
    if not container_id:
        raise RuntimeError(f"テキストコンテナ作成失敗: {data}")
    return container_id


def create_image_carousel_item(image_url: str) -> str:
    """
    カルーセル用の画像アイテムコンテナ作成
    is_carousel_item=true を付けるのがポイント
    """
    url = f"{API_BASE}/{USER_ID}/threads"
    params = {
        "media_type": "IMAGE",
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": ACCESS_TOKEN,
    }
    r = requests.post(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    item_id = data.get("id")
    if not item_id:
        raise RuntimeError(f"カルーセルアイテム作成失敗 ({image_url}): {data}")
    return item_id


def create_carousel_container(text: str, children_ids: list) -> str:
    """カルーセル本体のコンテナ作成（テキスト + 子コンテナIDたち）"""
    url = f"{API_BASE}/{USER_ID}/threads"
    params = {
        "media_type": "CAROUSEL",
        "text": text,
        "children": ",".join(children_ids),
        "access_token": ACCESS_TOKEN,
    }
    r = requests.post(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    container_id = data.get("id")
    if not container_id:
        raise RuntimeError(f"カルーセルコンテナ作成失敗: {data}")
    return container_id


def publish_container(container_id: str) -> str:
    """コンテナを公開。公開された投稿IDを返す"""
    url = f"{API_BASE}/{USER_ID}/threads_publish"
    params = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN,
    }
    r = requests.post(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    post_id = data.get("id")
    if not post_id:
        raise RuntimeError(f"公開失敗: {data}")
    return post_id


def post_to_threads(text: str, image_paths: list) -> str:
    """
    Threadsに投稿する。
    - image_paths が空 → テキストのみ投稿
    - image_paths が2枚以上 → カルーセル投稿
    """
    if len(text) > MAX_CHARS:
        raise ValueError(f"投稿が{MAX_CHARS}文字を超えています（{len(text)}文字）")

    if not image_paths:
        print(f"  テキストコンテナ作成中...")
        container_id = create_text_container(text)
    else:
        image_urls = [image_to_public_url(p) for p in image_paths]
        print(f"  画像URL: {image_urls}")

        print(f"  カルーセルアイテム作成中...")
        children_ids = []
        for i, url in enumerate(image_urls, 1):
            item_id = create_image_carousel_item(url)
            print(f"    アイテム{i}: {item_id}")
            children_ids.append(item_id)

        print(f"  カルーセルコンテナ作成中...")
        container_id = create_carousel_container(text, children_ids)

    print(f"  コンテナID: {container_id}")
    print(f"  30秒待機...")
    time.sleep(30)
    print(f"  公開中...")
    post_id = publish_container(container_id)
    return post_id


# ---------- メイン ----------
def main():
    print("=" * 60)
    print(f"Threads自動投稿 - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    posts = load_posts()
    total = len(posts)
    posted_count = sum(1 for p in posts if p.get("posted"))
    print(f"全{total}件 / 投稿済み{posted_count}件 / 残り{total - posted_count}件")

    target = pick_next_post(posts)
    if target is None:
        print("未投稿の投稿がありません。終了します。")
        return 0

    print(f"\n▶ 投稿ID {target['id']} を投稿します")
    print(f"  文字数: {len(target['text'])}文字")
    print(f"  プレビュー: {target['text'][:50]}...")

    image_paths = decide_images_for_post()
    print()

    try:
        published_id = post_to_threads(target["text"], image_paths)
        print(f"\n✓ 投稿成功！ published_id = {published_id}")

        target["posted"] = True
        target["published_id"] = published_id
        target["posted_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if image_paths:
            target["images"] = [p.name for p in image_paths]
        save_posts(posts)
        print(f"✓ JSON更新完了")
        return 0

    except requests.HTTPError as e:
        print(f"\n✗ HTTPエラー: {e}", file=sys.stderr)
        if e.response is not None:
            print(f"  レスポンス: {e.response.text}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n✗ エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Threads自動投稿スクリプト

threads_posts_50.json から posted=false の投稿を1件取り出し、
Threads API（Meta Graph API）で投稿する。
成功したら posted=true に更新して JSON を保存する。

使い方:
    python post_to_threads.py

必要な環境変数（.env または GitHub Secrets）:
    THREADS_ACCESS_TOKEN  - Threads Graph APIの長期トークン
    THREADS_USER_ID       - Threads User ID（数字）
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------- 設定 ----------
POSTS_FILE = Path(__file__).parent / "threads_posts_50.json"
API_BASE = "https://graph.threads.net/v1.0"
MAX_CHARS = 500  # Threadsの1投稿文字数上限

# ---------- 環境変数ロード ----------
load_dotenv()
ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
USER_ID = os.environ.get("THREADS_USER_ID")

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


# ---------- Threads API 呼び出し ----------
def create_container(text: str) -> str:
    """
    Step 1: メディアコンテナ作成
    text-onlyの投稿は media_type=TEXT を指定
    戻り値: container_id
    """
    url = f"{API_BASE}/{USER_ID}/threads"
    payload = {
        "media_type": "TEXT",
        "text": text,
        "access_token": ACCESS_TOKEN,
    }
    # data=で送ることで、改行文字(\n)がフォームボディ内で正しく扱われる
    r = requests.post(url, data=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    container_id = data.get("id")
    if not container_id:
        raise RuntimeError(f"コンテナ作成失敗: {data}")
    return container_id


def publish_container(container_id: str) -> str:
    """
    Step 2: コンテナを公開
    戻り値: 公開された投稿のID
    """
    url = f"{API_BASE}/{USER_ID}/threads_publish"
    payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN,
    }
    r = requests.post(url, data=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    post_id = data.get("id")
    if not post_id:
        raise RuntimeError(f"公開失敗: {data}")
    return post_id


def post_to_threads(text: str) -> str:
    """テキストをThreadsに投稿する。公開された投稿IDを返す"""
    if len(text) > MAX_CHARS:
        raise ValueError(f"投稿が{MAX_CHARS}文字を超えています（{len(text)}文字）")

    print(f"  コンテナ作成中...")
    container_id = create_container(text)
    print(f"  コンテナID: {container_id}")

    # Metaは「コンテナ作成後は30秒待ってから公開」を推奨
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
    print()

    try:
        published_id = post_to_threads(target["text"])
        print(f"\n✓ 投稿成功！ published_id = {published_id}")

        # 状態を更新して保存
        target["posted"] = True
        target["published_id"] = published_id
        target["posted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%d %H:%M:%S")
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

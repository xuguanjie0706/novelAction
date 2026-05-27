#!/usr/bin/env python3
"""
番茄小说草稿批量上传工具
============================
功能：将本地 TXT 文件（一章一个文件）批量上传至番茄小说草稿箱

用法：
    python fanqie_uploader.py --dir ./chapters --config fanqie_config.json
    python fanqie_uploader.py --dir ./chapters --config fanqie_config.json --delay 2
    python fanqie_uploader.py --dir ./chapters --config fanqie_config.json --dry-run

Token 有效期说明：
    - cookies (sessionid 等)：约 60 天，到期重新登录浏览器复制
    - msToken：与 session 绑定，通常与 cookies 同寿命
    - a_bogus：每次请求动态生成，留空即可（服务端通常不强校验草稿保存接口）
    - x-secsdk-csrf-token：与 session 绑定，留空通常也能保存草稿

刷新凭据步骤（Token 失效时）：
    1. 登录 fanqienovel.com，打开一个草稿编辑页
    2. 浏览器 DevTools → Network → 找任意 /api/author/article/ 请求
    3. 右键 → Copy → Copy as cURL
    4. 从 curl 中提取 -b '...' 的 cookie 串和 --data-raw 里的 msToken 更新到配置文件
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime


# ─────────────────────────────────────────
# HTML 转换
# ─────────────────────────────────────────

def txt_to_html(text: str) -> str:
    """
    将纯文本转换为番茄编辑器 HTML 格式。
    每行转为 <p>...</p>，空行转为 <p></p>（编辑器分段占位符）。
    """
    lines = text.splitlines()
    parts = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            # 转义 HTML 特殊字符
            escaped = (
                stripped
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )
            parts.append(f"<p>{escaped}</p>")
        else:
            parts.append("<p></p>")
    # 移除末尾多余的空段落
    while parts and parts[-1] == "<p></p>":
        parts.pop()
    return "".join(parts) if parts else "<p></p>"


# ─────────────────────────────────────────
# 配置加载
# ─────────────────────────────────────────

def load_config(config_path: str) -> dict:
    """加载 JSON 配置文件。"""
    path = Path(config_path)
    if not path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        print("   请先复制 fanqie_config.json 模板并填写凭据。")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_session(config: dict) -> requests.Session:
    """
    构建带 Cookie 的 requests.Session。
    支持字符串格式（直接从浏览器 DevTools 复制的 Cookie 串）。
    """
    session = requests.Session()
    cookie_str = config.get("cookies", "")
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            session.cookies.set(k.strip(), v.strip(), domain="fanqienovel.com")
    return session


# ─────────────────────────────────────────
# API 调用
# ─────────────────────────────────────────

def _build_headers(config: dict) -> dict:
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "origin": "https://fanqienovel.com",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
    }
    csrf = config.get("csrf_token", "").strip()
    if csrf:
        headers["x-secsdk-csrf-token"] = csrf
    book_id = config.get("book_id", "")
    headers["referer"] = f"https://fanqienovel.com/main/writer/{book_id}/"
    return headers


def create_new_draft(
    session: requests.Session,
    config: dict,
    title: str,
    content_html: str,
) -> dict:
    """
    新建草稿章节。
    番茄的"新建草稿"接口与"更新草稿"接口相同（cover_article），
    不传 item_id 时由服务端生成新 item_id。

    Returns:
        dict: 接口响应 JSON，成功时 code=0，data.item_id 为新草稿 ID。
    """
    url = "https://fanqienovel.com/api/author/article/cover_article/v0/"

    params = {}
    ms_token = config.get("ms_token", "").strip()
    a_bogus = config.get("a_bogus", "").strip()
    if ms_token:
        params["msToken"] = ms_token
    if a_bogus:
        params["a_bogus"] = a_bogus

    data = {
        "aid": "2503",
        "app_name": "muye_novel",
        "book_id": config["book_id"],
        "title": title,
        "content": content_html,
        "volume_name": config.get("volume_name", ""),
        "volume_id": config.get("volume_id", ""),
    }

    headers = _build_headers(config)
    resp = session.post(url, params=params, data=data, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def save_doc_history(
    session: requests.Session,
    config: dict,
    item_id: str,
) -> dict:
    """
    保存草稿历史版本（可选，与番茄前端行为一致）。

    Args:
        item_id: 刚创建成功的草稿 ID。
    """
    url = "https://fanqienovel.com/api/author/article/save_doc_history/v0/"

    params = {}
    ms_token = config.get("ms_token", "").strip()
    a_bogus = config.get("a_bogus", "").strip()
    if ms_token:
        params["msToken"] = ms_token
    if a_bogus:
        params["a_bogus"] = a_bogus

    data = {
        "aid": "2503",
        "app_name": "muye_novel",
        "book_id": config["book_id"],
        "item_id": item_id,
    }

    headers = _build_headers(config)
    resp = session.post(url, params=params, data=data, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ─────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────

def collect_txt_files(directory: str) -> list[Path]:
    """按文件名自然排序收集目录下所有 .txt 文件。"""
    import re

    def natural_key(p: Path):
        # 将文件名中的数字段转为整数，以便 "第2章" 排在 "第10章" 前面
        parts = re.split(r"(\d+)", p.stem)
        return [int(c) if c.isdigit() else c.lower() for c in parts]

    txt_dir = Path(directory)
    if not txt_dir.is_dir():
        print(f"❌ 目录不存在: {directory}")
        sys.exit(1)

    files = sorted(txt_dir.glob("*.txt"), key=natural_key)
    return files


def upload_all(args):
    config = load_config(args.config)
    files = collect_txt_files(args.dir)

    if not files:
        print(f"⚠️  目录 {args.dir} 中没有 .txt 文件，退出。")
        return

    print(f"📚 共找到 {len(files)} 个章节文件，目标书籍 {config['book_id']}")
    print(f"   卷：{config.get('volume_name', '（未指定）')}（{config.get('volume_id', '？')}）")
    print()

    if args.dry_run:
        print("【DRY-RUN 模式，不实际上传】")
        for i, f in enumerate(files, 1):
            print(f"  [{i:03d}] {f.stem}")
        return

    session = build_session(config)
    delay = args.delay

    results = []
    failed = []

    for i, txt_path in enumerate(files, 1):
        title = txt_path.stem
        print(f"[{i:03d}/{len(files)}] {title}", end="  ", flush=True)

        try:
            content = txt_path.read_text(encoding="utf-8")
            content_html = txt_to_html(content)

            resp = create_new_draft(session, config, title, content_html)

            if resp.get("code") == 0:
                item_id = (
                    resp.get("data", {}).get("item_id")
                    or resp.get("data", {}).get("articleId")
                    or "unknown"
                )
                print(f"✅  item_id={item_id}")
                results.append({
                    "index": i,
                    "title": title,
                    "status": "ok",
                    "item_id": str(item_id),
                })

                # 可选：保存历史版本
                if config.get("save_history", True) and item_id != "unknown":
                    try:
                        save_doc_history(session, config, str(item_id))
                    except Exception:
                        pass  # 历史记录失败不影响主流程

            else:
                msg = resp.get("message") or resp.get("msg") or json.dumps(resp, ensure_ascii=False)
                print(f"❌  {msg}")
                results.append({"index": i, "title": title, "status": "error", "msg": msg})
                failed.append(title)

        except requests.HTTPError as e:
            msg = f"HTTP {e.response.status_code}"
            print(f"❌  {msg}")
            results.append({"index": i, "title": title, "status": "http_error", "msg": msg})
            failed.append(title)

        except Exception as e:
            msg = str(e)
            print(f"❌  {msg}")
            results.append({"index": i, "title": title, "status": "exception", "msg": msg})
            failed.append(title)

        if i < len(files):
            time.sleep(delay)

    # ── 写入日志 ──────────────────────────────
    log_dir = Path(args.dir)
    log_name = f"fanqie_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    log_path = log_dir / log_name
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # ── 汇总 ──────────────────────────────────
    success = sum(1 for r in results if r["status"] == "ok")
    print()
    print("=" * 50)
    print(f"🎉  完成！成功 {success} / 总计 {len(results)} 章")
    if failed:
        print(f"⚠️   失败章节：{', '.join(failed)}")
    print(f"📄  上传日志：{log_path}")


# ─────────────────────────────────────────
# 入口
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="番茄小说草稿批量上传工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python fanqie_uploader.py --dir ./chapters --config fanqie_config.json
  python fanqie_uploader.py --dir ./vol2 --config fanqie_config.json --delay 2
  python fanqie_uploader.py --dir ./chapters --config fanqie_config.json --dry-run
        """,
    )
    parser.add_argument("--dir", required=True, help="TXT 文件所在目录")
    parser.add_argument("--config", required=True, help="配置文件路径（JSON）")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="每章上传间隔秒数，默认 1.5，避免触发频率限制",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览文件列表，不实际上传",
    )
    args = parser.parse_args()
    upload_all(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
通过 GitHub Git Data API 把本地提交推送到远端 main。

用途：当 `git push` 因网络/代理限制无法建立到 github.com:443 的连接时，
改走 api.github.com（REST API）完成同样的推送。内容与 git push 完全等价。

用法：
    python3 tools/push-via-api.py

令牌来源（按顺序尝试）：
    1. 环境变量 GITHUB_TOKEN
    2. macOS 钥匙串中 github.com 的凭据（git 首次 push 后会自动存入）
"""
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
BRANCH = "main"

ROOT = Path(__file__).resolve().parent.parent


def sh(*args, check=True):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"命令失败: {' '.join(args)}\n{r.stderr}")
    return r.stdout


def resolve_repo():
    """目标仓库：GITHUB_REPO=owner/repo 优先，否则从 git remote origin 解析。

    不硬编码仓库名——硬编码会把内容推错仓库，且本脚本会删除"远端有、本地无"的文件，
    推错仓库等于清空对方仓库。
    """
    env = os.environ.get("GITHUB_REPO", "").strip()
    if env:
        if "/" not in env:
            sys.exit("GITHUB_REPO 格式应为 owner/repo")
        return tuple(env.split("/", 1))

    url = sh("git", "remote", "get-url", "origin", check=False).strip()
    m = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?/?$", url)
    if not m:
        sys.exit(
            "无法从 git remote origin 识别仓库。\n"
            f"  当前 origin = {url!r}\n"
            "  请先 `git remote add origin https://github.com/<owner>/<repo>.git`，"
            "或设置环境变量 GITHUB_REPO=<owner>/<repo>"
        )
    return m.group(1), m.group(2)


OWNER, REPO = resolve_repo()
# 单次推送允许删除的远端文件上限（超过需显式确认，防止误推错仓库清空内容）
MASS_DELETE_LIMIT = int(os.environ.get("MASS_DELETE_LIMIT", "5"))


def get_token():
    tok = os.environ.get("GITHUB_TOKEN", "").strip()
    if tok:
        return tok
    r = subprocess.run(
        ["security", "find-internet-password", "-s", "github.com", "-w"],
        capture_output=True, text=True,
    )
    tok = r.stdout.strip()
    if not tok:
        sys.exit("未找到 GitHub 令牌：请设置 GITHUB_TOKEN，或先用 git push 让钥匙串记住凭据")
    return tok


TOKEN = get_token()


class ApiError(Exception):
    def __init__(self, method, path, code, body):
        super().__init__(f"API {method} {path} -> {code}\n{body}")
        self.code = code


def req(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(API + path, data=data, method=method)
    r.add_header("Authorization", f"Bearer {TOKEN}")
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("Content-Type", "application/json")
    r.add_header("User-Agent", "wb-pages-push")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise ApiError(method, path, e.code, e.read().decode()[:600]) from None


DRY_RUN = "--dry-run" in sys.argv


def main():
    print(f"目标仓库: {OWNER}/{REPO}  分支: {BRANCH}" + ("  [dry-run]" if DRY_RUN else ""))

    # 1. 远端 main 当前提交（404 = 空仓库，其他错误必须抛出，不能当成空仓库）
    try:
        ref = req("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}")
        parent_sha = ref["object"]["sha"]
    except ApiError as e:
        if e.code == 404:
            parent_sha = None
        else:
            sys.exit(str(e))

    base_tree = None
    remote_blobs = {}
    if parent_sha:
        commit = req("GET", f"/repos/{OWNER}/{REPO}/git/commits/{parent_sha}")
        base_tree = commit["tree"]["sha"]
        tree = req("GET", f"/repos/{OWNER}/{REPO}/git/trees/{base_tree}?recursive=1")
        remote_blobs = {e["path"]: e["sha"] for e in tree.get("tree", []) if e["type"] == "blob"}
        print(f"远端 {BRANCH}: {parent_sha[:8]}（{len(remote_blobs)} 个文件）")
    else:
        print("远端为空仓库，将创建首个提交")

    # 2. 逐文件比较本地 git blob 哈希与远端，找出差异
    local_files = [p for p in sh("git", "ls-files", "-z").split("\0") if p]
    entries, changed = [], []
    for path in local_files:
        fp = ROOT / path
        if not fp.is_file():
            continue
        local_sha = sh("git", "hash-object", path).strip()
        if remote_blobs.get(path) == local_sha:
            continue
        blob = req("POST", f"/repos/{OWNER}/{REPO}/git/blobs", {
            "content": base64.b64encode(fp.read_bytes()).decode(),
            "encoding": "base64",
        })
        mode = sh("git", "ls-files", "-s", "--", path).split()[0]
        entries.append({"path": path, "mode": mode, "type": "blob", "sha": blob["sha"]})
        changed.append(path)

    # 删除远端已有、本地已不存在的文件
    deletions = [p for p in remote_blobs if p not in local_files]
    if len(deletions) > MASS_DELETE_LIMIT:
        print(f"\n⚠️  本次将删除远端 {len(deletions)} 个文件（上限 {MASS_DELETE_LIMIT}）：")
        for p in deletions[:20]:
            print(f"      - {p}")
        if len(deletions) > 20:
            print(f"      ... 另有 {len(deletions) - 20} 个")
        print(f"  目标仓库: https://github.com/{OWNER}/{REPO}")
        print("  如果这不是你预期的仓库，立即中断（Ctrl-C）。")
        if os.environ.get("CONFIRM_MASS_DELETE") != "1":
            sys.exit("  已中断。确认无误请加环境变量 CONFIRM_MASS_DELETE=1 重跑。")
    for path in deletions:
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
        changed.append(f"{path} (删除)")

    if not entries:
        print("✅ 远端已是最新，无需推送")
        return

    print(f"待推送 {len(entries)} 项：")
    for c in changed:
        print(f"  - {c}")

    if DRY_RUN:
        print("✅ dry-run 结束，未做任何写入")
        return

    # 3. 建 tree → commit → 更新 ref
    tree = req("POST", f"/repos/{OWNER}/{REPO}/git/trees", {
        "base_tree": base_tree, "tree": entries,
    })
    msg = sh("git", "log", "-1", "--pretty=%B").strip()
    author = {
        "name": sh("git", "log", "-1", "--pretty=%an").strip(),
        "email": sh("git", "log", "-1", "--pretty=%ae").strip(),
        "date": sh("git", "log", "-1", "--pretty=%aI").strip(),
    }
    commit = req("POST", f"/repos/{OWNER}/{REPO}/git/commits", {
        "message": msg,
        "tree": tree["sha"],
        "parents": [parent_sha] if parent_sha else [],
        "author": author,
        "committer": author,
    })
    if parent_sha:
        req("PATCH", f"/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}",
            {"sha": commit["sha"], "force": False})
    else:
        req("POST", f"/repos/{OWNER}/{REPO}/git/refs",
            {"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})

    print(f"✅ 已推送，远端 {BRANCH} = {commit['sha'][:8]}")

    # 4. 本地远端跟踪引用对齐（本地无该对象时忽略）
    subprocess.run(["git", "update-ref", f"refs/remotes/origin/{BRANCH}", commit["sha"]],
                   cwd=ROOT, capture_output=True)
    print(f"本地 origin/{BRANCH} 引用已对齐")


if __name__ == "__main__":
    main()

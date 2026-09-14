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
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

OWNER = "Evergreen0330"
REPO = "zhifei-dronesport"
API = "https://api.github.com"
BRANCH = "main"

ROOT = Path(__file__).resolve().parent.parent


def sh(*args, check=True):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"命令失败: {' '.join(args)}\n{r.stderr}")
    return r.stdout


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
        sys.exit(f"API {method} {path} -> {e.code}\n{e.read().decode()[:600]}")


def main():
    # 1. 远端 main 当前提交
    try:
        ref = req("GET", f"/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}")
        parent_sha = ref["object"]["sha"]
    except SystemExit:
        parent_sha = None

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
    for path in remote_blobs:
        if path not in local_files:
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            changed.append(f"{path} (删除)")

    if not entries:
        print("✅ 远端已是最新，无需推送")
        return

    print(f"待推送 {len(entries)} 项：")
    for c in changed:
        print(f"  - {c}")

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

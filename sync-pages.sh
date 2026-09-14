#!/usr/bin/env bash
# 刷新静态包 → 同步到 docs/ → 提交 → 推送（git push 失败时降级到 GitHub API）
set -euo pipefail

cd "$(dirname "$0")"
ROOT=$(pwd)
MSG="${1:-chore: sync pages}"

# ---- 1. 同步到 docs/（复制清单必须包含根级静态文件，只复制 index.html + assets 会漏） ----
echo ">>> 同步静态包到 docs/"
rm -rf docs/assets
mkdir -p docs
for f in index.html 404.html robots.txt sitemap.xml og-cover.jpg; do
  [ -f "$ROOT/$f" ] && cp -p "$ROOT/$f" docs/
done
[ -d "$ROOT/assets" ] && cp -Rp "$ROOT/assets" docs/assets
touch docs/.nojekyll

echo ">>> docs/ 内容："
find docs -type f | sort | sed 's/^/    /'

# ---- 2. 提交 ----
git add -A
if git diff --cached --quiet; then
  echo ">>> 无变更，跳过提交"
else
  git commit -q -m "$MSG"
  echo ">>> 已提交：$MSG"
fi

# ---- 3. 推送：git push 优先，失败降级到 API ----
if git push origin main 2>/dev/null; then
  echo ">>> 已通过 git push 推送"
else
  echo ">>> git push 失败，改用 GitHub API 推送 ..."
  python3 tools/push-via-api.py
fi

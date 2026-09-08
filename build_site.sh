#!/bin/sh
# ★★外に出すものだけ集める。
#   ★中身は index.html に焼き込んであるので、データファイルは出さない。
#   ★★knowledge.json / design.json は**外に出さない**（★見せる必要がない）。
#   ★確認は置いた人がリポジトリで見る。
set -e
rm -rf _site && mkdir -p _site
cp index.html _site/
cp _worker.js _site/
[ -f robots.txt ]  && cp robots.txt  _site/ || true
[ -f sitemap.xml ] && cp sitemap.xml _site/ || true
# ★★★家が壊れていたら出さない（★自分を消せないようにするための番人）
grep -q "レアル" _site/index.html
grep -q "貼られたリンクは踏みません" _site/index.html
[ "$(wc -c < _site/index.html)" -gt 3000 ]
echo "家は無事"
ls -1 _site

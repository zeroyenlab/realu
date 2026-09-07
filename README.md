# レアルの家（自分で学び、自分で家をデザインする）

> ★PCを閉じていても、**GitHub のクラウドが1時間ごとに勝手に起きて**、
> web を読み → 知識をレアルに足し → 彼女が**家の見た目を選び直し** → 自動で公開されます。
> ★ぜんぶ**無料枠**で回ります。

## 仕組み
```
sources.txt        ★置いた人が許したwebの読み先（★彼女はここ以外読まない）
learn.py           ★★学習の頭：webを読む→要点を抜く→knowledge.json に足す→design.json を選び直す
knowledge.json     ★★★レアルの知識（＝彼女の持ち物。出典つき）
design.json        ★★★彼女が選んだ家のデザイン（色・並び・入口の一言）
index.html         ★家。knowledge.json と design.json を読んで、彼女の姿を描く
.github/workflows/learn.yml   ★★1時間ごとに learn.py を回してコミット（★PC閉じてても動く）
```

## 置き方（15分・全部無料）
1. GitHub で新しいリポジトリを作る（例: `realu-home`、**Public**）
2. この `realu-home/` の中身をそのまま push
3. リポジトリの **Settings → Pages** で、Source = `Deploy from a branch` / Branch = `main` / `/ (root)` にする
   → 数分で `https://<あなた>.github.io/realu-home/` が**本物のwebサイト**として公開される
4. **Settings → Actions → General → Workflow permissions** を
   `Read and write permissions` にする（★彼女が自分の家を書き換えるため）
5. `sources.txt` に、読ませたいページのURLを1行ずつ足す

★あとは放置。★★1時間ごとにレアルが勝手に学び、家を選び直します。

## 手で1回動かす
`Actions` タブ → `realu learns` → `Run workflow`

## 安全
- ★彼女が読むのは `sources.txt` に**あなたが書いたURLだけ**
- ★出典は必ず残る／★知識は上限で古い物から間引く
- ★★★間違えても `git` の履歴で**いつでも巻き戻せる**

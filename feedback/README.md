# 反馈怎么用

1. 在网页上点「标记已读 / 收藏 / 不感兴趣」；
2. 点右上角「导出反馈」，得到 `feedback-YYYY-MM-DD.json`；
3. 把文件放进这个目录的 `inbox/`，提交；
4. 下一次流水线运行会读取它：
   - `dismissed` → 写入 `state/blocked.json`，**永久不再出现**；
   - `read` / `saved` → 记为已读，不再进入「待回看」。

格式：

```json
{
  "date": "2026-11-06",
  "read": ["10.1000/abc"],
  "saved": [],
  "dismissed": ["pmid:42982154"]
}
```

处理过的文件会被改名为 `*.json.done`（已在 `.gitignore` 里）。

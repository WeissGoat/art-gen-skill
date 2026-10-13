# 工程约定模板

在工程的 `AGENTS.md` 或 `CLAUDE.md` 里加一节，art-gen 开工时读它。没有的项可以删掉，art-gen 会用默认值或问用户。

```markdown
## 美术出图（art-gen）

- 网关：`tools/ai-image-gateway`（submodule）；配置 `tools/ai-image-gateway/config.local.yaml`（不进 git）
- 风格基准：`docs/art/style.md`；角色设定：`docs/art/characters/`
- 锚点图：`art/anchors/`（已确认的角色 / 场景 / 风格母版）
- 探索目录：`tmp/art_explore/<YYYYMMDD>_<主题>/`（git 忽略）
- 正式候选：`art/_incoming/<资产ID>/`（git 忽略）
- 入库：挑中的图由 `<脚本或步骤>` 放进 `<正式资产目录>`；Unity 资产连 `.meta` 一起处理，替换时保住 GUID
- 工程美术 skill：`<名字>`（有的话，正式资产按它走）
- 偏好：角色默认用 NovelAI（V5，画师 xxx）；背景用 Gemini 图生图从场景锚点出
```

网关放在哪：

- **工程要固定网关版本**：作为 submodule 加进工程，写上面的"网关"一行。
- **多个工程共用一份**：clone 到固定位置，设用户环境变量 `AI_IMAGE_GATEWAY_ROOT`（Windows：`setx AI_IMAGE_GATEWAY_ROOT D:\tools\ai-image-gateway`），`pip install -e` 指向它，配置也只维护这一份。

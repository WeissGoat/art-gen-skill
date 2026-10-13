---
name: art-gen
description: Use for AI image work in any project - concept art, placeholder or formal game assets (icons, backgrounds, UI, character sprites and expression/pose differences, narrative CG), editing an existing image, picking among candidates. Covers locating and configuring the shared ai-image-gateway, choosing a backend (OpenAI images, Gemini image-to-image, NovelAI), writing the prompt in that backend's format, serial generation with evidence, contact-sheet review, and keeping a set consistent through anchors. A project's own art skill (e.g. p3-art) still owns how assets enter that project.
---

# 通用 AI 出图

一条路：**找网关 → 读工程约定 → 选后端写 Prompt → 串行出候选 → 拼图挑选 → 交给工程入库**。

脚本在本 skill 的 `scripts/` 下（下文写作 `<skill>/scripts/...`），只依赖网关和 Pillow。

## 0. 找网关（每个会话第一次出图前）

```bash
python <skill>/scripts/locate_gateway.py
```

查找顺序：`--root` → 环境变量 `AI_IMAGE_GATEWAY_ROOT` → 当前工程里的 submodule / `tools/ai-image-gateway` / 同级目录 → 已 `pip install -e` 的包。配置文件：`--config` → `AI_IMAGE_GATEWAY_CONFIG` → `<网关>/config.local.yaml` → `config.yaml`。工程的 art-gen 约定里写了路径时，用 `--root` / `--config` 传进去。

| 结果 | 怎么做 |
|---|---|
| `ready` | 记下 gateway 路径、commit 和各 provider 的 auth 状态，继续。`env_missing:X` 表示配置引用的环境变量没设，该 provider 不能用。 |
| `gateway_missing`（退出码 2） | 把脚本打印的取得方式告诉用户：作为 submodule 加进当前工程，或者放一份共享 clone 并设 `AI_IMAGE_GATEWAY_ROOT`。**clone、加 submodule、pip install 都要先问用户。** |
| `config_missing`（退出码 3） | 让用户从 `config.example.yaml` 复制出 `config.local.yaml`，自己填密钥或环境变量。Agent 不填写、不打印、不提交任何密钥。 |

注意 editable 安装只有一份：全局 `pip install -e` 指向哪个 checkout，所有工程就用那个 checkout 的网关版本。别的工程要固定版本，就用自己的 submodule，并在调用时传 `--root`。

## 1. 读工程约定

在工程的 `AGENTS.md` / `CLAUDE.md` 里找 art-gen 一节（模板见 [project-section.md](references/project-section.md)）：网关路径、风格基准文档、探索目录、正式候选目录、入库方式、工程自己的美术 skill。

- 工程有自己的美术 skill（例如 P3 的 `p3-art`）：正式资产的需求、目录、入库和门禁听它的，本 skill 只提供出图和挑选方法。
- 没有约定：探索图放 `tmp/art_explore/<YYYYMMDD>_<主题>/`（确认它被 git 忽略），不往工程资产目录里写。要入库时先问用户放哪、怎么接。

## 2. 选后端、写 Prompt

| 任务 | 首选 | 备选 | Prompt |
|---|---|---|---|
| 新概念图、通用文生图 | 宿主自带生图工具（有就用），否则 `openai_images` | `gemini_chat_image` | 自然语言 |
| 保身份 / 保构图的改图，表情 / 姿态 / 状态差分，按锚点出同风格的新图 | `gemini_chat_image` 图生图 | `openai_images` edits | 自然语言 + 保持 / 改变 / 禁止 |
| 二次元特化、Danbooru tag 控制、原生负面词 | `novelai` | `openai_images` | tag + negative |
| 有 mask、允许漂移的局部重绘 | `novelai` inpaint | Gemini 图生图 | tag + mask |

写法细节和各后端的坑：[backends-and-prompts.md](references/backends-and-prompts.md)。NovelAI 的 tag 写法用 `nai5-prompting`（V5）或 `nai45-prompt`（V4.5）skill。同一套 prompt 不原样发给不同后端。

## 3. 出图

```bash
# 先对这次要用的后端做最小 smoke：1 张小图
python <skill>/scripts/gen.py generate --provider <p> --prompt "one small blue crystal on white, no text" --size 512x512 --out <dir>/_smoke
# 正式出候选
python <skill>/scripts/gen.py generate --provider openai_images --prompt-file prompt.txt --size 1024x1536 -n 4 --out <dir>
python <skill>/scripts/gen.py i2i --provider gemini_chat_image --ref anchor.png --prompt-file edit.txt -n 3 --out <dir>
python <skill>/scripts/gen.py inpaint --provider novelai --ref src.png --mask mask.png --prompt "tags" --out <dir>
```

- `-n N` 是串行发 N 次、每次 1 张，中间默认间隔 2 秒。不并发，不用 `count>1`。
- 每次运行在输出目录写 `generation_<prefix>.json`：provider、model、网关 commit、prompt、参考图 SHA、每张图的尺寸 / seed / SHA、错误和耗时。Prompt 同时存成文件放在候选旁边，方便以后重出。
- 退出码 0 才算拿到图；4 表示请求都发了但没有可用图片。
- 后端报错、限流、超时、0 张可用：如实告诉用户 provider、错误摘要和可选的备选后端，**不悄悄换后端**，不说成出图成功。换后端会改变风格或 prompt 格式时，先问用户。

## 4. 挑选

```bash
python <skill>/scripts/contact_sheet.py <dir> --out <dir>/_sheet.png --small 96
```

亲眼看图（拼图和原图都看），不凭文件名或 prompt 判断。先过硬伤：损坏、乱码文字 / 水印 / 签名、主体数量错、身份错、关键部位被裁、要透明却做不到。再看：语义可读性、风格一致、身份一致、构图和安全区、小尺寸可读、工程可用（尺寸、alpha、能否九宫格拉伸）。图标偏重小尺寸可读，角色偏重身份，背景偏重构图和安全区。

- 能上屏就选，写一句理由。
- 接近但有局部问题：用图生图修最好的那张，或针对性再出 2 张。
- 所有候选同一个毛病：改 prompt / 参考图 / 后端，不逐张修。
- 停下来问用户的情况：几张好图代表不同美术方向；要定首个角色 / 场景 / 风格锚点；要替换已经在用的资产。问的时候给拼图、2–3 个选项、推荐项和理由。

## 5. 一套图要一致：先锚点

角色立绘套组、多格 CG、同一地点的多张背景，不逐张独立文生图：

1. 先定锚点：角色锚点（脸、发型、服装、比例），场景锚点（空间结构、光源），风格锚点（线条、上色、色板）。每类出 2–4 张，选 1 张主锚点，需要用户确认。
2. 后续每张用 `i2i --ref <锚点>` 生成，prompt 里分开写保持 / 改变 / 禁止。
3. 按套 / 按页对比：身份、头身比、视线和基线、光照、渲染方式；快速切换时不能跳。一张不合格只重做那一张。

## 6. 声明分级和边界

出图只代表**有了候选**。选定、入库、上屏各要各的证据，不越级：没有入库就不说"已接入"，没在真实界面看过就不说"显示正确"。

- 不提交密钥、`config.local.yaml`、smoke 图和原始候选。
- 不手工把候选覆盖进工程的正式资产目录，入库按工程约定或工程 skill 走（例如 Unity 要连 `.meta` 一起处理，保住 GUID）。
- 工程运行时只能引用正式资产目录，不能引用候选或临时目录。

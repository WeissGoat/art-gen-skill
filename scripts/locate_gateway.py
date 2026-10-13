# -*- coding: utf-8 -*-
"""Report where ai-image-gateway is, which config it would use and which providers look usable.

Never prints credential values. Exit codes: 0 ready, 2 gateway missing, 3 config missing.

    python locate_gateway.py [--root DIR] [--config FILE] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gateway import GATEWAY_REPO, find_config, find_gateway, git_commit, summarize_config  # noqa: E402

MISSING_HELP = f"""\
没有找到 ai-image-gateway。任选一种方式取得（先征得用户同意再 clone）：
  A. 作为当前工程的 submodule：
       git submodule add {GATEWAY_REPO} tools/ai-image-gateway
  B. 放一份共享 clone，再告诉 skill 在哪：
       git clone {GATEWAY_REPO} <目录>
       setx AI_IMAGE_GATEWAY_ROOT <目录>        (或在工程 AGENTS.md / CLAUDE.md 的 art-gen 一节写明路径)
  依赖：pip install -e <网关目录>   (NovelAI 另加 [novelai])"""

CONFIG_HELP = """\
网关已找到，但没有配置文件。由用户自己完成（Agent 不填写任何密钥）：
  copy <网关目录>\\config.example.yaml <网关目录>\\config.local.yaml
  在 config.local.yaml 里启用要用的 provider；密钥写成 ${ENV_VAR}，由用户在环境变量里设置。
  也可以用 AI_IMAGE_GATEWAY_CONFIG 指向别处的配置文件。"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", help="网关目录（覆盖自动查找）")
    parser.add_argument("--config", help="配置文件（覆盖自动查找）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    root, source = find_gateway(args.root)
    report: dict = {"gateway_root": str(root) if root else None, "source": source}
    if root is None:
        report["status"] = "gateway_missing"
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"status: gateway_missing ({source})\n{MISSING_HELP}")
        return 2

    report["commit"] = git_commit(root)
    config = find_config(root, args.config)
    report["config"] = str(config) if config else None
    if config is None:
        report["status"] = "config_missing"
        print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else
              f"gateway: {root}  ({source})  {report['commit']}\nstatus: config_missing\n{CONFIG_HELP}")
        return 3

    report["status"] = "ready"
    report.update(summarize_config(config))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"gateway: {root}  ({source})  {report['commit']}")
    print(f"config:  {config}")
    print("default_provider: " + ", ".join(f"{k}={v}" for k, v in report["default_provider"].items()))
    for name, info in report["providers"].items():
        if not info["enabled"]:
            continue
        auth = ", ".join(f"{k}:{v}" for k, v in info["auth"].items()) or "no auth fields"
        print(f"  {name:<20} model={info['model'] or '-'}  base_url={info['base_url_state']}  {auth}")
    print("status: ready（字段已填不代表后端可用，正式批量前仍要 smoke）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Generate candidates through ai-image-gateway and write generation.json next to them.

N candidates = N serial requests with count=1. Exit 0 only when at least one decodable image was saved.

    python gen.py generate --provider openai_images --prompt-file p.txt --size 1024x1024 -n 4 --out tmp/art_explore/x
    python gen.py i2i --provider gemini_chat_image --ref anchor.png --prompt "..." -n 3 --out ...
    python gen.py inpaint --provider novelai --ref src.png --mask mask.png --prompt "tags" --out ...
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gateway import ensure_importable, find_config, find_gateway, git_commit  # noqa: E402


_TRANSIENT = re.compile(r"429|too many|rate limit|504|timeout|timed out|502|503", re.IGNORECASE)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_text(value: str | None, file: str | None) -> str:
    if file:
        return Path(file).read_text(encoding="utf-8").strip()
    return (value or "").strip()


def _size(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    w, h = value.lower().split("x")
    return int(w), int(h)


def _decode(data: bytes) -> tuple[int, int, str] | None:
    from PIL import Image

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            return img.width, img.height, (img.format or "").lower()
    except Exception:
        return None


async def run(args: argparse.Namespace) -> int:
    root, source = find_gateway(args.gateway_root)
    if root is None:
        print(f"gateway not found ({source}); run locate_gateway.py first", file=sys.stderr)
        return 2
    config = find_config(root, args.config)
    if config is None:
        print("gateway config not found; run locate_gateway.py first", file=sys.stderr)
        return 3
    ensure_importable(root)
    from ai_image_gateway import GenerateRequest, ImageService, ImageToImageRequest, InpaintRequest
    from loguru import logger

    logger.remove()
    logger.add(sys.stderr, level=args.log_level)

    prompt = _read_text(args.prompt, args.prompt_file)
    negative = _read_text(args.negative, args.negative_file)
    if not prompt:
        print("prompt is empty", file=sys.stderr)
        return 1
    width, height = _size(args.size)
    extra = json.loads(args.extra) if args.extra else {}
    refs = [Path(r) for r in (args.ref or [])]
    ref_bytes = [r.read_bytes() for r in refs]
    mask_bytes = Path(args.mask).read_bytes() if args.mask else None
    if args.mode in ("i2i", "inpaint") and not ref_bytes:
        print(f"{args.mode} needs --ref", file=sys.stderr)
        return 1
    if args.mode == "inpaint" and mask_bytes is None:
        print("inpaint needs --mask", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or datetime.now().strftime("r%H%M%S")
    evidence = {
        "tool": "art-gen/gen.py",
        "mode": args.mode,
        "provider_requested": args.provider or "(config default)",
        "gateway": {"root": str(root), "source": source, "commit": git_commit(root)},
        "config": str(config),
        "prompt": prompt,
        "negative_prompt": negative,
        "size": args.size,
        "seed": args.seed,
        "extra": extra,
        "references": [{"path": str(r), "sha256": _sha(b)} for r, b in zip(refs, ref_bytes)],
        "mask": {"path": args.mask, "sha256": _sha(mask_bytes)} if mask_bytes else None,
        "requests": args.n,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "outputs": [],
        "errors": [],
    }

    async with ImageService(config) as svc:
        for i in range(args.n):
            seed = args.seed + i if args.seed is not None else None
            common = dict(prompt=prompt, negative_prompt=negative, count=1, seed=seed,
                          provider=args.provider, extra=extra)
            t0 = time.monotonic()
            for attempt in range(args.retries + 1):
                if args.mode == "generate":
                    result = await svc.generate(GenerateRequest(width=width or 1024, height=height or 1024, **common))
                elif args.mode == "i2i":
                    result = await svc.image_to_image(ImageToImageRequest(images=ref_bytes, width=width, height=height, **common))
                else:
                    result = await svc.inpaint(InpaintRequest(image=ref_bytes[0], mask=mask_bytes, width=width, height=height, **common))
                transient = not result.results and any(_TRANSIENT.search(e) for e in result.errors)
                if not transient or attempt == args.retries:
                    break
                print(f"[{i + 1}/{args.n}] transient error, retry {attempt + 1}/{args.retries} in {args.retry_wait:.0f}s: {result.errors[-1][:160]}")
                evidence["errors"].append({"request": i + 1, "error": result.errors[-1], "retried": True})
                await asyncio.sleep(args.retry_wait)
            elapsed = round(time.monotonic() - t0, 1)
            for err in result.errors:
                evidence["errors"].append({"request": i + 1, "error": err, "elapsed_s": elapsed})
                print(f"[{i + 1}/{args.n}] error: {err}")
            for j, img in enumerate(result.results):
                info = _decode(img.image_bytes)
                if info is None:
                    evidence["errors"].append({"request": i + 1, "error": "undecodable image", "elapsed_s": elapsed})
                    continue
                w, h, fmt = info
                name = f"{prefix}_{i + 1:03d}{'' if j == 0 else f'_{j}'}.{fmt if fmt in ('png', 'jpeg', 'webp') else 'png'}"
                (out / name).write_bytes(img.image_bytes)
                evidence["outputs"].append({
                    "request": i + 1, "path": name, "width": w, "height": h, "format": fmt,
                    "sha256": _sha(img.image_bytes), "seed": img.seed, "provider": img.provider_name,
                    "model": img.model_name, "elapsed_s": elapsed,
                })
                print(f"[{i + 1}/{args.n}] {name} {w}x{h} {img.provider_name}/{img.model_name} seed={img.seed}")
            if i + 1 < args.n and args.delay > 0:
                await asyncio.sleep(args.delay)

    evidence["finished_at"] = datetime.now().isoformat(timespec="seconds")
    evidence["success_count"] = len(evidence["outputs"])
    log = out / f"generation_{prefix}.json"
    log.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{evidence['success_count']}/{args.n} images, evidence: {log}")
    return 0 if evidence["success_count"] else 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=["generate", "i2i", "inpaint"])
    parser.add_argument("--provider", help="网关 provider 名；省略时用配置里的 default_provider")
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    parser.add_argument("--negative")
    parser.add_argument("--negative-file")
    parser.add_argument("--ref", action="append", help="参考图 / 源图，可重复")
    parser.add_argument("--mask", help="inpaint 遮罩")
    parser.add_argument("--size", help="WxH，例如 1024x1536")
    parser.add_argument("-n", type=int, default=1, help="候选数（串行请求数，每次 count=1）")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--delay", type=float, default=2.0, help="请求间隔秒数")
    parser.add_argument("--retries", type=int, default=2, help="限流 / 超时类错误的重试次数")
    parser.add_argument("--retry-wait", type=float, default=30.0, help="重试前等待秒数")
    parser.add_argument("--extra", help="原样传给 provider 的 JSON，例如 '{\"model\": \"nai-diffusion-5\"}'")
    parser.add_argument("--out", required=True, help="输出目录")
    parser.add_argument("--prefix", help="文件名前缀，默认 rHHMMSS")
    parser.add_argument("--log-level", default="WARNING", help="网关日志级别，排查时用 INFO / DEBUG")
    parser.add_argument("--gateway-root")
    parser.add_argument("--config")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())

"""调用真实 OpenAI-compatible Rewrite 接口并保存逐条改写结果。"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx
import yaml


def _rewrite(client: httpx.Client, base_url: str, api_key: str, model: str, item: dict[str, Any]) -> dict[str, Any]:
    """改写单条查询，失败时保留原查询并记录错误状态。"""
    prompt = [
        {"role": "system", "content": "你是中文检索查询改写器。修正错别字、澄清模糊表达并补全省略信息。只使用当前输入中明确出现的事实，不回答问题，不添加菜谱事实；保留否定词、过敏原、数字和单位。只输出 JSON：{\"standalone_query\":\"...\"}"},
        {"role": "user", "content": item.get("query", "")},
    ]
    try:
        response = client.post(base_url.rstrip("/") + "/chat/completions", headers={"Authorization": "Bearer " + api_key}, json={"model": model, "messages": prompt, "temperature": 0, "max_tokens": 256}, timeout=30)
        response.raise_for_status()
        body = response.json()
        content = str(body["choices"][0]["message"].get("content", "")).strip()
        if content.startswith("```"):
            content = content.strip("`").removeprefix("json").strip()
        rewritten = json.loads(content).get("standalone_query", "")
        if not isinstance(rewritten, str) or not rewritten.strip() or len(rewritten) > 2000:
            raise ValueError("standalone_query 无效")
        result = dict(item)
        result.update({"rewritten_query": rewritten.strip(), "rewrite_status": "success", "rewrite_model": model})
        return result
    except Exception as exc:
        result = dict(item)
        result.update({"rewritten_query": item.get("query", ""), "rewrite_status": "fallback", "rewrite_error": str(exc)[:200], "rewrite_model": model})
        return result


def main() -> None:
    """并发处理查询文件并写出 Rewrite A/B 输入数据。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--input", default="evaluation/datasets/labels/queries_noisy.jsonl")
    parser.add_argument("--output", default="evaluation/experiments/sparse-dense-all/queries_noisy_rewritten.jsonl")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers <= 0:
        raise ValueError("workers 必须为正数")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    chat = config["chat"]
    base_url = chat.get("rewrite_base_url") or chat["base_url"]
    api_key = chat.get("rewrite_api_key") or chat["api_key"]
    model = chat.get("rewrite_model") or chat["model"]
    if not base_url or not api_key or not model:
        raise ValueError("Rewrite 模型配置不完整")
    items = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    results: list[dict[str, Any] | None] = [None] * len(items)
    with httpx.Client() as client, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_rewrite, client, base_url, api_key, model, item): index for index, item in enumerate(items)}
        for count, future in enumerate(as_completed(futures), 1):
            results[futures[future]] = future.result()
            if count % 50 == 0 or count == len(items):
                print("rewritten=%d/%d" % (count, len(items)), flush=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in results if item is not None) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()

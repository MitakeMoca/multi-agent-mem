"""本地大模型适配器。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _extract_json_block(text: str) -> Dict[str, Any]:
    start = text.find("{")
    if start < 0:
        return {}
    depth = 0
    candidate = ""
    for idx, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : idx + 1]
                break
    if not candidate:
        return {}
    try:
        return json.loads(candidate)
    except Exception:
        fixed = candidate.replace("'", '"')
        try:
            return json.loads(fixed)
        except Exception:
            return {}


@dataclass
class GenerationResult:
    text: str
    prompt_chars: int
    output_chars: int


class LocalCausalLM:
    """封装本地可加载的因果语言模型。"""

    def __init__(self, model_path: str, device_map: str = "auto", dtype: str = "bfloat16") -> None:
        # 服务器上存在 ABI 不匹配的 flash_attn 二进制包。Transformers 只要探测到
        # flash_attn 就会尝试导入它，导致普通模型也加载失败；这里显式关闭该路径。
        import sys

        sys.modules["flash_attn"] = None
        sys.modules["flash_attn.bert_padding"] = None
        sys.modules["flash_attn.flash_attn_interface"] = None
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        try:
            import transformers.utils.import_utils as import_utils

            for name in dir(import_utils):
                if "flash_attn" in name and name.endswith("_available"):
                    setattr(import_utils, name, False)
        except Exception:
            pass

        self.torch = torch
        self.model_path = model_path
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        torch_dtype = getattr(torch, dtype)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch_dtype,
            device_map=device_map,
            trust_remote_code=True,
        )
        self.model.eval()

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 256,
        temperature: float = 0.0,
        top_p: float = 0.95,
    ) -> GenerationResult:
        import torch

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if hasattr(self.tokenizer, "apply_chat_template") and getattr(self.tokenizer, "chat_template", None):
            inputs = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                return_tensors="pt",
            )
        else:
            joined = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}\n\n[ASSISTANT]\n"
            inputs = self.tokenizer(joined, return_tensors="pt").input_ids
        inputs = inputs.to(self.model.device)
        prompt_chars = len(system_prompt) + len(user_prompt)
        with torch.inference_mode():
            out = self.model.generate(
                inputs,
                max_new_tokens=max_new_tokens,
                do_sample=temperature > 0,
                temperature=temperature if temperature > 0 else None,
                top_p=top_p if temperature > 0 else None,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        decoded = self.tokenizer.decode(out[0][inputs.shape[-1] :], skip_special_tokens=True).strip()
        return GenerationResult(text=decoded, prompt_chars=prompt_chars, output_chars=len(decoded))

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 256,
    ) -> Dict[str, Any]:
        result = self.generate(system_prompt, user_prompt, max_new_tokens=max_new_tokens)
        data = _extract_json_block(result.text)
        return {"result": result, "data": data}

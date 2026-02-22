#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
档案智能分类系统 - LLM客户端
"""

import json
import re
from typing import Dict

from langchain.llms import Ollama
from langchain.prompts import PromptTemplate

from config.config import Config
from constants import METADATA_SCHEMA


class LlmClient:
    """封装Ollama LLM，提供元数据提取能力"""

    def __init__(self, model: str = Config.LLM_MODEL):
        self.llm = Ollama(
            model=model,
            temperature=Config.LLM_TEMPERATURE,
            format=Config.LLM_FORMAT,
        )
        self.metadata_schema = METADATA_SCHEMA

    # ── 公开接口 ───────────────────────────────────────────────────────────────

    def extract_metadata(self, ocr_text: str, prompt: PromptTemplate) -> Dict:
        """
        使用LLM从OCR文本中提取元数据

        Args:
            ocr_text: OCR识别的文本
            prompt:   已构建的PromptTemplate

        Returns:
            提取的元数据字典
        """
        print("[LLM] 正在分析文本并提取元数据...")

        try:
            formatted_prompt = prompt.format(ocr_text=ocr_text)
            response = self.llm.invoke(formatted_prompt)

            print(f"[LLM响应] 原始响应长度: {len(response)} 字符")

            response = self._clean_response(response)

            preview = (
                response[:Config.LLM_RESPONSE_PREVIEW_LENGTH]
                if len(response) > Config.LLM_RESPONSE_PREVIEW_LENGTH
                else response
            )
            print(f"[JSON清理后] {preview}...")

            metadata = self._parse_json(response)

            return metadata

        except Exception as e:
            print(f"[LLM错误] {str(e)}")
            import traceback
            traceback.print_exc()
            return {}

    # ── 私有方法 ───────────────────────────────────────────────────────────────

    def _clean_response(self, response: str) -> str:
        """清理LLM响应，提取纯JSON字符串"""
        response = response.strip()

        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]

        if response.endswith("```"):
            response = response[:-3]

        response = response.strip()

        # 提取JSON对象
        if '{' in response and '}' in response:
            start_idx = response.find('{')
            end_idx = response.rfind('}')
            response = response[start_idx:end_idx + 1]

        # 移除非JSON内容
        lines = response.split('\n')
        json_lines = []
        in_json = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('{'):
                in_json = True
            if in_json:
                json_lines.append(line)
            if stripped.endswith('}') and in_json:
                break

        if json_lines:
            response = '\n'.join(json_lines)

        return response.strip()

    def _parse_json(self, response: str) -> Dict:
        """解析JSON，失败时依次尝试修复和正则提取"""
        # 主路径：直接解析
        try:
            metadata = json.loads(response)
            return metadata

        except json.JSONDecodeError as e:
            print(f"[JSON解析失败] {str(e)}")
            print("[尝试修复JSON格式...]")

        # 修复路径：替换单引号、移除尾逗号
        fixed_response = response.replace("'", '"')
        fixed_response = re.sub(r',(\s*[}\]])', r'\1', fixed_response)

        try:
            metadata = json.loads(fixed_response)
            print(f"[修复成功] 成功提取字段")
            return metadata
        except Exception:
            pass

        # 回退路径：正则逐字段提取
        print("[尝试正则表达式提取...]")
        metadata = self._extract_fields_by_regex(response)
        if metadata:
            print(f"[正则提取] 成功提取 {len(metadata)} 个字段")
            return metadata

        # 全部失败
        print(f"[完整响应内容]")
        print("-" * 70)
        print(response)
        print("-" * 70)
        return {}

    def _extract_fields_by_regex(self, text: str) -> Dict:
        """
        使用正则表达式从文本中提取字段(fallback方法)
        """
        metadata = {}

        patterns = [
            r'"([^"]+)":\s*"([^"]*)"',
            r'"([^"]+)":\s*(\d+)',
            r'"([^"]+)":\s*null',
            r'"([^"]+)":\s*(\[.*?\])',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) == 2:
                    key, value = match
                    if key in self.metadata_schema:
                        if value == 'null' or not value:
                            metadata[key] = None
                        elif value.isdigit():
                            metadata[key] = int(value)
                        else:
                            metadata[key] = value

        return metadata
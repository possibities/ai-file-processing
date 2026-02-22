#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
档案智能分类系统 - OCR客户端
"""

import re
from pathlib import Path
from typing import List

from paddleocr import PaddleOCR

from config.config import Config
from constants import (
    OCR_CONFIDENCE_NORMAL,
    OCR_CONFIDENCE_SHORT,
    OCR_REPLACEMENTS,
    OCR_SHORT_TEXT_LEN,
)


class OcrClient:
    """封装PaddleOCR，提供单页/多页文本提取能力"""

    def __init__(self, lang: str = Config.OCR_LANG):
        self.ocr = PaddleOCR(
            use_angle_cls=Config.OCR_USE_ANGLE_CLS,
            lang=lang,
            use_gpu=Config.OCR_USE_GPU,
            show_log=Config.OCR_SHOW_LOG,
        )

    # ── 公开接口 ───────────────────────────────────────────────────────────────

    def extract_text(self, image_path: str) -> str:
        """
        使用OCR从图像提取文字

        Args:
            image_path: 图像文件路径

        Returns:
            提取的文本内容
        """
        print(f"[OCR] 正在识别图像: {image_path}")

        try:
            result = self.ocr.ocr(image_path, cls=True)

            if not result or not result[0]:
                return ""

            text_lines = []
            for line in result[0]:
                text = line[1][0]
                confidence = line[1][1]

                if confidence > 0.8:
                    text_lines.append(text)

            full_text = "\n".join(text_lines)
            print(f"[OCR] 识别完成,提取 {len(text_lines)} 行文本")

            return full_text

        except Exception as e:
            print(f"[OCR错误] {str(e)}")
            return ""

    def extract_text_from_images(self, image_paths: List[str]) -> str:
        """
        从多个图像提取文字并合并(用于多页档案)
        """
        all_text = []

        print(f"[OCR] 开始识别 {len(image_paths)} 页图像...")

        for idx, image_path in enumerate(image_paths, 1):
            print(f"  正在识别第 {idx}/{len(image_paths)} 页: {Path(image_path).name}")

            try:
                result = self.ocr.ocr(image_path, cls=True)

                if result and result[0]:
                    page_text = []
                    low_conf_count = 0

                    for line in result[0]:
                        text = line[1][0]
                        confidence = line[1][1]

                        # 主阈值0.6：保留更多有效文字
                        # 对于短文本（≤3字）适当提高阈值避免噪声
                        min_conf = (
                            OCR_CONFIDENCE_SHORT
                            if len(text) <= OCR_SHORT_TEXT_LEN
                            else OCR_CONFIDENCE_NORMAL
                        )

                        if confidence >= min_conf:
                            page_text.append(text)
                        else:
                            low_conf_count += 1

                    if page_text:
                        all_text.append(f"===== 第 {idx} 页 =====")
                        all_text.extend(page_text)
                        all_text.append("")
                        print(
                            f"    ✓ 提取 {len(page_text)} 行文本"
                            f"（过滤低置信度 {low_conf_count} 行）"
                        )
                    else:
                        print(f"    ✗ 未识别到有效文字")
                else:
                    print(f"    ✗ OCR返回空结果")

            except Exception as e:
                print(f"    ✗ 识别失败: {str(e)}")

        full_text = "\n".join(all_text)

        # OCR文本清洗
        full_text = self._clean_ocr_text(full_text)

        print(f"[OCR] 完成，总计提取 {len(all_text)} 行文本\n")

        return full_text

    # ── 私有方法 ───────────────────────────────────────────────────────────────

    def _clean_ocr_text(self, text: str) -> str:
        """
        清洗OCR常见噪声
        修正扫描件中常见的字符误识别
        """
        for old, new in OCR_REPLACEMENTS.items():
            text = text.replace(old, new)

        # 清除连续空白行（超过2个换行合并为2个）
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 清除行首行尾多余空格
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)

        return text
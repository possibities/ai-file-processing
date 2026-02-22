#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
档案智能分类系统 - 配置模块
"""

class Config:
    """系统配置"""

    OCR_LANG: str = "ch"
    OCR_USE_GPU: bool = True
    OCR_USE_ANGLE_CLS: bool = True
    OCR_SHOW_LOG: bool = False

    # ── LLM ──────────────────────────────────────────────────────────────────
    LLM_MODEL: str = "qwen2.5:7b"
    LLM_TEMPERATURE: float = 0.1
    LLM_FORMAT: str = "json"

    # ── 日志 ─────────────────────────────────────────────────────────────────
    OCR_PREVIEW_LENGTH: int = 500
    LLM_RESPONSE_PREVIEW_LENGTH: int = 200

    # ── 路径配置 ─────────────────────────────────────────────────────────────
    EXPORTER_CONFIG_PATH: str = "./config/exporter.json"
    INPUT_DIR: str = "./input_documents"
    OUTPUT_DIR: str = "./output_results"
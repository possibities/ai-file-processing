#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
档案智能分类系统 - 主运行文件
整合所有模块，提供简洁的使用接口
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 导入外部配置类
from config.config import Config 

from core.classifier import ArchiveClassifier
from processors.batch_processor import BatchProcessor
from processors.exporter import Exporter


def main():
    """主函数"""

    print("=" * 70)
    print("档案智能分类系统")
    print("=" * 70)

    # ==================== 1. 初始化系统 ====================
    print("\n[1/4] 初始化系统...")

    # 使用外部导入的导出器配置路径
    Exporter.initialize(Config.EXPORTER_CONFIG_PATH)

    # 使用外部导入的模型配置
    classifier = ArchiveClassifier(
        ocr_lang=Config.OCR_LANG,
        llm_model=Config.LLM_MODEL
    )
    batch_processor = BatchProcessor(classifier)
    print("✓ 系统初始化完成!")

    # ==================== 2. 配置输入输出路径 ====================
    print("\n[2/4] 配置路径...")

    # 使用外部导入的输入输出路径
    print(f"输入目录: {Config.INPUT_DIR}")
    print(f"输出目录: {Config.OUTPUT_DIR}")

    input_path = Path(Config.INPUT_DIR)
    output_path = Path(Config.OUTPUT_DIR)

    if not input_path.exists():
        print(f"\n[错误] 输入目录不存在: {input_path}")
        return

    if not output_path.exists():
        print(f"\n[提示] 输出目录不存在，正在创建: {output_path}")
        output_path.mkdir(parents=True, exist_ok=True)


    # ==================== 3. 处理档案 ====================
    print("\n[3/4] 开始处理档案...")

    results = batch_processor.process_directory(
        directory_path=Config.INPUT_DIR,
        output_dir=Config.OUTPUT_DIR
    )

    # ==================== 4. 导出结果 ====================
    if results:
        print("\n[4/4] 导出结果...")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        json_output = output_path / f"archive_results_{timestamp}.json"
        Exporter.export_to_json(results, str(json_output))

        csv_output = output_path / f"archive_results_{timestamp}.csv"
        Exporter.export_to_csv(results, str(csv_output))


        # ==================== 5. 显示结果汇总 ====================
        print(f"\n{'=' * 70}")
        print("处理完成! 结果文件:")
        print(f"{'=' * 70}")
        print(f"  汇总JSON: {json_output}")
        print(f"  汇总CSV:  {csv_output}")
        print(f"  单档案结果: {Config.OUTPUT_DIR}/*_result.json")
        print(f"{'=' * 70}")

        success_count = sum(1 for r in results if r.get('status') == 'success')
        total_count = len(results)
        print(f"\n处理统计:")
        print(f"  总档案数: {total_count}")
        print(f"  成功: {success_count} ({success_count / total_count * 100:.1f}%)")
        print(f"  失败: {total_count - success_count}")
        print(f"{'=' * 70}\n")

    else:
        print("\n[警告] 未找到任何档案或处理失败")
        print("请检查:")
        print(f"  1. 输入目录是否存在: {Config.INPUT_DIR}")
        print(f"  2. 目录结构是否正确 (子文件夹/图片文件)")
        print(f"  3. 图片格式是否支持 (.jpg, .jpeg, .png, .bmp, .tiff)")


# ==================== 其他使用示例 ====================

def example_single_file():
    """示例: 处理单个文件"""
    print("\n" + "=" * 70)
    print("示例: 处理单个文件")
    print("=" * 70 + "\n")

    Exporter.initialize(Config.EXPORTER_CONFIG_PATH)

    classifier = ArchiveClassifier(
        ocr_lang=Config.OCR_LANG, 
        llm_model=Config.LLM_MODEL
    )

    result = classifier.process_document("./test_archive.jpg")

    print("\n[提取结果]")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def example_custom_file_list():
    """示例: 处理指定的文件列表"""
    print("\n" + "=" * 70)
    print("示例: 处理指定的文件列表")
    print("=" * 70 + "\n")

    Exporter.initialize(Config.EXPORTER_CONFIG_PATH)

    classifier = ArchiveClassifier(
        ocr_lang=Config.OCR_LANG, 
        llm_model=Config.LLM_MODEL
    )
    batch_processor = BatchProcessor(classifier)

    image_files = [
        "/path/to/doc1.jpg",
        "/path/to/doc2.jpg",
        "/path/to/doc3.jpg"
    ]

    results = batch_processor.batch_process(image_files, Config.OUTPUT_DIR)

    Exporter.export_to_csv(results, f"{Config.OUTPUT_DIR}/custom_results.csv")


if __name__ == "__main__":
    main()
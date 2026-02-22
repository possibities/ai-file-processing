#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
档案智能分类系统 - 批量处理器
负责目录扫描、批量调用分类器、结果汇总
"""

import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime


class BatchProcessor:
    """
    批量处理器

    职责：
    1. 扫描目录结构，识别档案单元（每个含图片的子文件夹 = 一份档案）
    2. 调用分类器处理每份档案
    3. 将文件系统层面的信息（页数、来源路径、处理时间）注入到 metadata
    4. 保存单档案JSON + 生成批处理汇总

    设计要点：
    - 依赖注入（classifier），降低耦合
    - 职责清晰（扫描/处理/保存分离）
    - 兼容旧接口
    """

    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}

    def __init__(self, classifier):
        """
        参数:
            classifier: 分类器实例，需实现 process_multi_page_document() 方法
        """
        self.classifier = classifier

    # ══════════════════════════════════════════════════════════════════════════
    # 目录扫描
    # ══════════════════════════════════════════════════════════════════════════

    def scan_directory_structure(
        self,
        root_directory: str,
        max_depth: int = 2
    ) -> Dict[str, List[str]]:
        """
        扫描目录，识别档案单元

        逻辑：
        - 每个包含图片文件的子文件夹 → 一份档案
        - 返回：{档案名: [图片路径列表]}

        参数:
            root_directory: 根目录路径
            max_depth: 最大递归深度（防止无限递归）

        返回:
            Dict[str, List[str]]
        """

        archive_dict: Dict[str, List[str]] = {}
        root_path = Path(root_directory)

        if not root_path.exists():
            print(f"[错误] 目录不存在: {root_directory}")
            return {}

        if not root_path.is_dir():
            print(f"[错误] 路径不是目录: {root_directory}")
            return {}

        def collect_images(folder: Path) -> List[str]:
            """返回文件夹下所有支持格式的图片路径（排序）"""
            return sorted([
                str(f)
                for f in folder.iterdir()
                if f.is_file() and f.suffix.lower() in self.SUPPORTED_FORMATS
            ])

        def scan_folder(folder: Path, prefix: str = "", depth: int = 0) -> int:
            """
            递归扫描目录
            - 如果子目录含图片 → 视为一份档案
            - 否则继续递归扫描
            """
            if depth >= max_depth:
                return 0

            added = 0
            subdirs = sorted([
                d for d in folder.iterdir()
                if d.is_dir() and not d.name.startswith('.')
            ])

            for subdir in subdirs:
                images = collect_images(subdir)

                if images:
                    key = f"{prefix}{subdir.name}" if prefix else subdir.name
                    archive_dict[key] = images
                    added += 1
                else:
                    nested = scan_folder(
                        subdir,
                        prefix=f"{subdir.name}/",
                        depth=depth + 1
                    )
                    added += nested

            return added

        scan_folder(root_path)
        return archive_dict

    # ══════════════════════════════════════════════════════════════════════════
    # 批处理主流程
    # ══════════════════════════════════════════════════════════════════════════

    def batch_process_archives(
        self,
        archive_dict: Dict[str, List[str]],
        output_dir: str = None
    ) -> List[Dict]:
        """
        批量处理档案

        流程：
        1. 遍历档案
        2. 调用 classifier.process_multi_page_document()
        3. 将文件系统信息注入到 metadata（页数、来源路径、处理时间）
        4. 保存单档案JSON
        5. 生成批处理汇总

        返回:
            List[Dict]  所有档案的处理结果
        """

        results = []
        success_count = 0
        fail_count = 0

        total_archives = len(archive_dict)
        total_pages = sum(len(p) for p in archive_dict.values())

        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        else:
            output_path = None

        for idx, (archive_name, image_paths) in enumerate(archive_dict.items(), 1):

            # ── 文件系统层面的信息 ────────────────────────────────────────
            source_folder = (
                str(Path(image_paths[0]).parent)
                if image_paths else None
            )

            first_image = Path(image_paths[0]) if image_paths else None
            created_time = (
                datetime.fromtimestamp(first_image.stat().st_mtime).isoformat()
                if first_image else None
            )

            # ── 构造基础结果结构（顶层字段，用于调试和日志） ──────────────
            base_result = {
                "archive_name": archive_name,
                "source_folder": source_folder,
                "page_count": len(image_paths),
                "image_files": image_paths,
                "image_names": [Path(p).name for p in image_paths],
                "processed_time": created_time,
            }

            try:
                # ── 调用分类器 ─────────────────────────────────────────────
                metadata = self.classifier.process_multi_page_document(
                    archive_name,
                    image_paths
                )

                if metadata:
                    # ★ 关键修改：将文件系统信息注入到 metadata ★
                    # exporter 只读取 metadata 字段，所以必须注入到这里
                    # 页数：LLM 不填此字段，完全由文件系统层统计
                    metadata["页数"] = len(image_paths)
                    metadata["source_folder"] = source_folder  # 新增：来源路径
                    metadata["processed_time"] = created_time  # 新增：处理时间

                    result = {
                        **base_result,
                        "metadata": metadata,
                        "status": "success"
                    }
                    success_count += 1
                else:
                    result = {
                        **base_result,
                        "metadata": None,
                        "status": "failed",
                        "error": "LLM未能提取有效元数据"
                    }
                    fail_count += 1

            except Exception as e:
                import traceback
                result = {
                    **base_result,
                    "metadata": None,
                    "status": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc()
                }
                fail_count += 1

            results.append(result)

            # ── 保存单档案JSON ────────────────────────────────────────────
            if output_path:
                safe_name = archive_name.replace("/", "__").replace("\\", "__")
                safe_name = f"{idx:04d}_{safe_name}"
                json_path = output_path / f"{safe_name}_result.json"
                self._save_json(result, json_path)

        # ── 批处理汇总 ────────────────────────────────────────────────────
        if output_path:
            summary_path = output_path / "batch_summary.json"
            summary_data = {
                "batch_time": datetime.now().isoformat(),
                "total_archives": total_archives,
                "total_pages": total_pages,
                "success_count": success_count,
                "fail_count": fail_count,
                "results": results
            }
            self._save_json(summary_data, summary_path)

        # ── 终端统计输出 ──────────────────────────────────────────────────
        success_rate = (
            success_count / total_archives * 100 if total_archives else 0
        )
        fail_rate = (
            fail_count / total_archives * 100 if total_archives else 0
        )

        print(f"\n{'='*70}")
        print("批量处理完成")
        print(f"  档案总数: {total_archives}")
        print(f"  成功:     {success_count} ({success_rate:.1f}%)")
        print(f"  失败:     {fail_count}     ({fail_rate:.1f}%)")
        print(f"  图片总数: {total_pages} 张")
        print(f"{'='*70}\n")

        return results

    # ══════════════════════════════════════════════════════════════════════════
    # 工具方法
    # ══════════════════════════════════════════════════════════════════════════

    def _save_json(self, data: Dict, path: Path):
        """统一JSON保存方法"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ══════════════════════════════════════════════════════════════════════════
    # 兼容旧接口
    # ══════════════════════════════════════════════════════════════════════════

    def batch_process(
        self,
        image_paths: List[str],
        output_dir: str = None
    ) -> List[Dict]:
        """
        旧接口：直接传入图像路径列表
        自动构造单页档案字典
        """
        archive_dict = {
            Path(img).stem: [img]
            for img in image_paths
        }
        return self.batch_process_archives(archive_dict, output_dir)

    def process_directory(
        self,
        directory_path: str,
        output_dir: str = None
    ) -> List[Dict]:
        """
        旧接口：直接传入目录路径
        自动扫描并批处理
        """
        archive_dict = self.scan_directory_structure(directory_path)

        if not archive_dict:
            print("[警告] 未找到任何档案文件夹，终止处理")
            return []

        return self.batch_process_archives(archive_dict, output_dir)
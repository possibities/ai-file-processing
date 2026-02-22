"""
导出模块
包含 JSON 和 CSV 导出功能
"""

import json
import csv
from typing import List, Dict


class Exporter:
    """结果导出器类，用于导出数据到 CSV 或 JSON 格式"""

    # 类级缓存，用于存储导出模板的表头配置
    HEADERS = {}

    @classmethod
    def initialize(cls, config_path: str):
        """
        初始化方法，程序启动时调用，用于加载配置文件到内存
        该配置文件包含导出的模板与表头配置。

        参数:
            config_path (str): 配置文件的路径，通常是 JSON 格式
        """
        try:
            # 打开并加载配置文件
            with open(config_path, "r", encoding="utf-8") as f:
                cls.HEADERS = json.load(f)
        except Exception as e:
            # 如果加载配置文件失败，抛出异常
            raise RuntimeError(f"加载导出配置失败: {e}")

    @classmethod
    def get_headers(cls, template: str = "default") -> List[str]:
        """
        获取指定模板的表头配置。

        参数:
            template (str): 要加载的模板名称，默认为 "default"

        返回:
            List[str]: 对应模板的表头列表

        异常:
            如果未初始化或者未找到模板，会抛出异常
        """
        # 检查是否已经初始化
        if not cls.HEADERS:
            raise RuntimeError("Exporter 未初始化，请先调用 initialize()")

        # 检查模板是否存在
        if template not in cls.HEADERS:
            raise ValueError(f"未找到模板: {template}")

        return cls.HEADERS[template]

    @classmethod
    def export_to_csv(
        cls,
        results: List[Dict],
        output_path: str,
        template: str = "default"
    ):
        """
        将结果数据导出为 CSV 格式。

        参数:
            results (List[Dict]): 要导出的结果数据，每个元素为字典
            output_path (str): 导出文件的路径
            template (str): 用于获取表头配置的模板，默认为 "default"

        异常:
            如果发生导出错误，抛出异常
        """
        # 如果没有数据可导出，提示并返回
        if not results:
            print("[提示] 没有数据可导出")
            return

        try:
            # 获取指定模板的表头
            headers = cls.get_headers(template)

            # 打开输出文件，准备写入
            with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()  # 写入表头

                count = 0
                for result in results:
                    # 从每条结果中获取 metadata 字段
                    meta = result.get("metadata", {})
                    if not meta:
                        continue

                    row = {}
                    # 将 metadata 中的字段值填充到行中
                    for field in headers:
                        val = meta.get(field, "")
                        if val is None:
                            val = ""
                        row[field] = val

                    # 写入当前行数据
                    writer.writerow(row)
                    count += 1

            # 提示导出成功
            print(f"\n[导出] 成功导出 {count} 条记录")
            print(f"[路径] {output_path}")

        except Exception as e:
            # 捕获导出过程中的任何异常
            print(f"[导出错误] {str(e)}")

    @classmethod
    def export_to_json(
        cls,
        results: List[Dict],
        output_path: str,
        template: str = "default",
        indent: int = 2
    ):
        """
        将结果数据导出为 JSON 格式。

        参数:
            results (List[Dict]): 要导出的结果数据，每个元素为字典
            output_path (str): 导出文件的路径
            template (str): 用于获取表头配置的模板，默认为 "default"
            indent (int): JSON 输出的缩进级别，默认为 2

        异常:
            如果发生导出错误，抛出异常
        """
        # 如果没有数据可导出，提示并返回
        if not results:
            print("[提示] 没有数据可导出")
            return

        try:
            # 获取指定模板的表头
            headers = cls.get_headers(template)

            export_data = []
            count = 0

            for result in results:
                # 从每条结果中获取 metadata 字段
                meta = result.get("metadata", {})
                if not meta:
                    continue

                item = {}
                # 将 metadata 中的字段值填充到项中
                for field in headers:
                    val = meta.get(field, "")
                    if val is None:
                        val = ""
                    item[field] = val

                export_data.append(item)
                count += 1

            # 打开输出文件，准备写入
            with open(output_path, "w", encoding="utf-8") as f:
                # 将结果数据导出为 JSON 格式
                json.dump(
                    export_data,
                    f,
                    ensure_ascii=False,
                    indent=indent
                )

            # 提示导出成功
            print(f"\n[导出] 成功导出 {count} 条记录")
            print(f"[路径] {output_path}")

        except Exception as e:
            # 捕获导出过程中的任何异常
            print(f"[导出错误] {str(e)}")

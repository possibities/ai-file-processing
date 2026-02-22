# #!/usr/bin/env python3
# # -*- coding: utf-8 -*-
# """
# 档案智能分类系统 - 文件工具模块

# 修正记录：
#   v2 - 2026-02-22
#   [Fix] get_file_creation_time 新增EXIF优先策略：
#         文件系统时间（ctime/birthtime/mtime）在批量复制/传输后会被刷新，
#         导致取到的是复制时间而非扫描时间。
#         修正后优先读取图片EXIF中的原始拍摄时间（DateTimeOriginal），
#         EXIF不可用时才降级到原有文件系统时间逻辑。

#   读取优先级：
#     1. EXIF DateTimeOriginal (Tag 0x9003) — 扫描仪写入的原始时间，最准确
#     2. EXIF DateTime         (Tag 0x0132) — 文件修改时间
#     3. 文件系统时间（原有逻辑保留）       — 兜底，可能因复制被刷新
# """

# import os
# import platform
# import struct
# import subprocess
# from datetime import datetime
# from pathlib import Path


# def get_file_creation_time(file_path: str) -> str:
#     """
#     获取文件真实创建时间，格式化为"2026年2月"

#     策略优先级：
#     1. EXIF DateTimeOriginal（扫描仪写入的原始时间，不受文件复制影响）
#     2. EXIF DateTime（EXIF修改时间）
#     3. Windows: st_ctime（真正的创建时间）
#     4. macOS:   st_birthtime（真正的创建时间）
#     5. Linux:   stat Birth时间 → st_mtime（最后修改时间）
#     """
#     # ── 优先：EXIF时间（不受文件系统复制影响）────────────────────────────────
#     exif_dt = _read_exif_datetime(file_path)
#     if exif_dt:
#         formatted = f"{exif_dt.year}年{exif_dt.month}月"
#         print(f"[数字化时间] EXIF模式，DateTimeOriginal: {formatted}（文件: {Path(file_path).name}）")
#         return formatted

#     # ── 降级：文件系统时间（原有逻辑保留）────────────────────────────────────
#     try:
#         file_stat = os.stat(file_path)
#         system = platform.system()
#         timestamp = None

#         if system == "Windows":
#             timestamp = file_stat.st_ctime
#             print(f"[数字化时间] Windows模式，st_ctime")

#         elif system == "Darwin":
#             if hasattr(file_stat, 'st_birthtime'):
#                 timestamp = file_stat.st_birthtime
#                 print(f"[数字化时间] macOS模式，st_birthtime")
#             else:
#                 timestamp = file_stat.st_mtime
#                 print(f"[数字化时间] macOS模式，st_birthtime不可用，回退st_mtime")

#         else:
#             try:
#                 result = subprocess.run(
#                     ["stat", "--format=%W", file_path],
#                     capture_output=True, text=True, timeout=3
#                 )
#                 birth_ts = result.stdout.strip()
#                 if birth_ts and birth_ts != "0" and birth_ts != "-":
#                     timestamp = float(birth_ts)
#                     print(f"[数字化时间] Linux模式，stat Birth时间")
#                 else:
#                     raise ValueError("Birth时间不支持")
#             except Exception:
#                 timestamp = file_stat.st_mtime
#                 print(f"[数字化时间] Linux模式，回退st_mtime")

#         creation_time = datetime.fromtimestamp(timestamp)
#         formatted = f"{creation_time.year}年{creation_time.month}月"
#         print(f"[数字化时间] 提取结果: {formatted}（文件: {Path(file_path).name}）")
#         return formatted

#     except Exception as e:
#         print(f"[数字化时间] 读取失败: {str(e)}，使用当前时间")
#         now = datetime.now()
#         return f"{now.year}年{now.month}月"


# # ── EXIF轻量级解析（纯标准库，无第三方依赖）─────────────────────────────────

# def _read_exif_datetime(file_path: str) -> datetime | None:
#     """
#     从图片文件中读取EXIF时间，不依赖第三方库。
#     支持 JPEG / TIFF，优先 DateTimeOriginal(0x9003)，降级 DateTime(0x0132)。
#     """
#     path = Path(file_path)
#     suffix = path.suffix.lower()

#     try:
#         with open(path, "rb") as f:
#             raw = f.read()
#     except OSError:
#         return None

#     if suffix in (".jpg", ".jpeg"):
#         exif_data = _extract_jpeg_exif(raw)
#     elif suffix in (".tif", ".tiff"):
#         exif_data = raw
#     else:
#         return None  # PNG等格式无标准EXIF

#     if not exif_data:
#         return None

#     return _parse_exif_ifd(exif_data)


# def _extract_jpeg_exif(raw: bytes) -> bytes | None:
#     """从JPEG字节流中提取EXIF段（APP1）"""
#     if not raw.startswith(b'\xff\xd8'):
#         return None

#     i = 2
#     while i + 4 <= len(raw):
#         if raw[i] != 0xff:
#             break
#         marker = raw[i + 1]
#         i += 2
#         if marker in (0xd9, 0xda):  # EOI / SOS
#             break
#         seg_len = struct.unpack(">H", raw[i:i+2])[0]
#         seg_data = raw[i+2:i+seg_len]
#         # APP1 (0xe1)，且含Exif标记
#         if marker == 0xe1 and seg_data[:4] == b'Exif':
#             return seg_data[6:]  # 跳过 "Exif\x00\x00"
#         i += seg_len

#     return None


# def _parse_exif_ifd(exif_data: bytes) -> datetime | None:
#     """
#     解析EXIF IFD，提取 DateTimeOriginal(0x9003) 或 DateTime(0x0132)。
#     自动处理大端序（MM）和小端序（II）。
#     """
#     if len(exif_data) < 8:
#         return None

#     byte_order = exif_data[:2]
#     if byte_order == b'II':
#         endian = '<'
#     elif byte_order == b'MM':
#         endian = '>'
#     else:
#         return None

#     ifd_offset = struct.unpack(endian + 'I', exif_data[4:8])[0]

#     datetime_original = None
#     datetime_fallback = None
#     offsets_to_scan = [ifd_offset]
#     visited = set()

#     while offsets_to_scan:
#         offset = offsets_to_scan.pop()
#         if offset in visited or offset + 2 > len(exif_data):
#             continue
#         visited.add(offset)

#         entry_count = struct.unpack(endian + 'H', exif_data[offset:offset+2])[0]
#         pos = offset + 2

#         for _ in range(entry_count):
#             if pos + 12 > len(exif_data):
#                 break
#             tag   = struct.unpack(endian + 'H', exif_data[pos:pos+2])[0]
#             type_ = struct.unpack(endian + 'H', exif_data[pos+2:pos+4])[0]
#             count = struct.unpack(endian + 'I', exif_data[pos+4:pos+8])[0]
#             val_offset = struct.unpack(endian + 'I', exif_data[pos+8:pos+12])[0]
#             pos += 12

#             # ASCII字符串（type=2）
#             if type_ == 2:
#                 if count <= 4:
#                     str_bytes = exif_data[pos-4:pos-4+count]
#                 else:
#                     str_bytes = exif_data[val_offset:val_offset+count]
#                 dt_str = str_bytes.decode('ascii', errors='ignore').strip('\x00').strip()
#                 dt = _parse_exif_date_string(dt_str)
#                 if tag == 0x9003 and dt:    # DateTimeOriginal
#                     datetime_original = dt
#                 elif tag == 0x0132 and dt:  # DateTime
#                     datetime_fallback = dt

#             # ExifSubIFD指针（0x8769），加入扫描队列
#             elif tag == 0x8769:
#                 offsets_to_scan.append(val_offset)

#     return datetime_original or datetime_fallback


# def _parse_exif_date_string(date_str: str) -> datetime | None:
#     """解析EXIF日期字符串，兼容标准格式和部分设备的连字符格式"""
#     for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
#         try:
#             return datetime.strptime(date_str, fmt)
#         except ValueError:
#             continue
#     return None


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
档案智能分类系统 - 文件工具模块

修正记录：
  v3 - 2026-02-22
  [Fix1] 完全移除EXIF逻辑——数字化时间取文件系统创建时间，与EXIF无关
  [Fix2] 优先取图片所在文件夹的创建时间，文件夹无法取时才降级取图片文件本身
  [Fix3] 新增 _get_birthtime(path) 统一封装跨平台创建时间读取逻辑，避免重复代码
"""

import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path


def get_file_creation_time(file_path: str) -> str:
    """
    获取数字化时间，格式化为"2026年2月"

    优先级：
      1. 图片所在文件夹的创建时间（birthtime）
      2. 图片文件本身的创建时间（birthtime）
      3. 兜底：当前时间
    """
    image_path = Path(file_path)

    # 优先：文件夹创建时间
    folder_path = image_path.parent
    ts = _get_birthtime(folder_path)
    if ts:
        dt = datetime.fromtimestamp(ts)
        formatted = f"{dt.year}年{dt.month}月"
        print(f"[数字化时间] 文件夹创建时间: {formatted}（{folder_path.name}）")
        return formatted

    # 降级：文件本身创建时间
    ts = _get_birthtime(image_path)
    if ts:
        dt = datetime.fromtimestamp(ts)
        formatted = f"{dt.year}年{dt.month}月"
        print(f"[数字化时间] 文件创建时间: {formatted}（{image_path.name}）")
        return formatted

    # 兜底：当前时间
    print(f"[数字化时间] 无法读取创建时间，使用当前时间")
    now = datetime.now()
    return f"{now.year}年{now.month}月"


def _get_birthtime(path: Path) -> float | None:
    """
    跨平台获取文件或文件夹的创建时间（birthtime）时间戳。

    各平台策略：
      Windows : st_ctime（Windows上ctime就是创建时间）
      macOS   : st_birthtime（真正的创建时间）
      Linux   : stat --format=%W（部分文件系统支持）→ 不支持则返回None
                注意：Linux不回退mtime，因为mtime语义是修改时间而非创建时间，
                      回退mtime会导致数字化时间语义错误。

    返回：float时间戳，无法获取返回None
    """
    try:
        stat = os.stat(path)
        system = platform.system()

        if system == "Windows":
            return stat.st_ctime

        elif system == "Darwin":
            if hasattr(stat, 'st_birthtime'):
                return stat.st_birthtime
            return None

        else:
            # Linux: 尝试 stat --format=%W（Birth时间）
            result = subprocess.run(
                ["stat", "--format=%W", str(path)],
                capture_output=True, text=True, timeout=3
            )
            birth_ts = result.stdout.strip()
            if birth_ts and birth_ts not in ("0", "-", ""):
                return float(birth_ts)
            return None

    except Exception as e:
        print(f"[数字化时间] _get_birthtime 失败 ({path}): {e}")
        return None
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
档案智能分类系统 - 规则引擎

修正记录：
  v2 - 2026-02-22
  [Fix1] 规则2（简报）执行后设锁标志位，防止后续规则覆盖10年期限
  [Fix2] 规则1（培训）不再硬编码保管期限，仅在LLM判定为10年时才强制提升为30年
  [Fix3] 规则7兜底扩展：使用 PERIOD_ORDER 比较，任何低于30年的期限均提升为30年
  [Fix4] 规则10增加选举结果排除逻辑，防止换届选举结果（永久）被误降为30年
  [Fix5] _resolve_code 改为精确匹配，防止"业务管理类"等误匹配
  [Fix6] 删除 WORK_SECRET_KEYWORDS 在 _apply_open_status_rules 中的冗余调用
  [Fix7] "约谈"从 NEGATIVE_TITLE_KEYWORDS 移除，改为"诫勉约谈"精确匹配（已在constants更新）
"""

import re
from typing import Dict

from constants import (
    COMMERCIAL_EXEMPT_KEYWORDS,
    COMMERCIAL_KEYWORDS,
    CONTROLLED_SECURITY_LEVELS,
    NEGATIVE_PATTERNS,
    NEGATIVE_TITLE_KEYWORDS,
    PERIOD_ORDER,
    PRIVACY_KEYWORDS,
    CODE_NEW,
    CODE_OLD,
    CODE_SWITCH_YEAR,
    FORCE_NULL_FIELDS,
    ADDRESS_CHANGE_KEYWORDS,
    BID_KEYWORDS,
    BRIEFING_BUSINESS_KEYWORDS,
    BRIEFING_PARTY_KEYWORDS,
    IMPORTANT_NOTICE_KEYWORDS,
    INTERNAL_ORG_KEYWORDS,
    MAINTENANCE_DOC_TYPES,
    MAINTENANCE_KEYWORDS,
    PARTY_BRANCH_ADJUST_KEYWORDS,
    PARTY_BRANCH_ELECTION_RESULT_KEYWORDS,
    PARTY_BRANCH_TARGET_KEYWORDS,
    REGULATION_KEYWORDS,
    TRAINING_KEYWORDS,
    TRAINING_MGMT_KEYWORDS,
    PARTY_TRAINING_KEYWORDS,
    BUSINESS_FALSE_POSITIVE_DOC_TYPES,
    BUSINESS_LEGITIMATE_KEYWORDS,
)


class RulesEngine:
    """
    规则引擎：按优先级顺序执行四层规则修正

    执行顺序：
      0. _force_fix_fields            — 强制字段修正
      1. _apply_supplementary_rules   — 10条补充规则（最高优先级）
      2. _apply_open_status_rules     — 开放状态与延期开放理由判定
      3. _validate_classification_code — 编码格式校验
    """

    def apply_all(self, metadata: Dict, ocr_text: str) -> Dict:
        print("\n[开始应用规则修正]")
        metadata = self._force_fix_fields(metadata)
        metadata = self._apply_supplementary_rules(metadata, ocr_text)
        metadata = self._apply_open_status_rules(metadata, ocr_text)
        metadata = self._validate_classification_code(metadata)
        print("[规则修正完成]\n")
        return metadata

    # ── 优先级0：强制字段修正 ──────────────────────────────────────────────────

    def _force_fix_fields(self, metadata: Dict) -> Dict:
        """强制留空字段 + 立档单位名称同步责任者 + 密级合法值校验"""
        if not metadata:
            return metadata

        for field in FORCE_NULL_FIELDS:
            if metadata.get(field) and metadata[field] != "null":
                print(f"[强制修正] {field}: {metadata[field]} → null")
                metadata[field] = None

        # 立档单位名称与责任者保持一致
        if not metadata.get("立档单位名称"):
            metadata["立档单位名称"] = metadata.get("责任者")

        # 密级合法值校验：不在允许范围内一律置null
        VALID_SECURITY_LEVELS = {"非涉密", "内部", "秘密", "机密", "绝密"}
        current_level = metadata.get("密级")
        if current_level and current_level not in VALID_SECURITY_LEVELS:
            print(f"[强制修正] 密级非法值: {current_level} → null")
            metadata["密级"] = None
            metadata["保密期限"] = None

        # 保密期限合法值校验
        VALID_SECRET_PERIODS = {"1年", "5年", "10年"}
        current_period = metadata.get("保密期限")
        if current_period and current_period not in VALID_SECRET_PERIODS:
            print(f"[强制修正] 保密期限非法值: {current_period} → null")
            metadata["保密期限"] = None

        return metadata

    # ── 优先级1：10条补充规则 ─────────────────────────────────────────────────

    def _apply_supplementary_rules(self, metadata: Dict, ocr_text: str) -> Dict:
        """
        10条补充规则，优先级高于LLM输出。

        执行顺序说明：
          - 规则2（简报→10年）最先执行，并设置 period_locked=True
          - period_locked=True 时，后续所有规则不得修改保管期限
          - 规则7（文件编号兜底）最后执行，但受 period_locked 保护
          - 规则1（培训）不直接覆盖保管期限，仅在LLM判定低于30年时提升
        """
        if not metadata:
            return metadata

        title = str(metadata.get("题名") or "").strip()
        text = ocr_text or ""
        content = title + " " + text

        # 期限锁标志：规则2触发后设True，后续规则不得修改保管期限
        period_locked = False

        # ── 规则2: 简报 → 10年（最先执行，锁定期限）─────────────────────────
        if "简报" in title:
            print(f"[补充规则2] 简报，保管期限 → 10年（已锁定，后续规则不覆盖）")
            metadata["保管期限"] = "10年"
            period_locked = True

            # 规则2扩展：简报分类修正
            # 规则引擎接管分类判断，防止LLM将党务简报误归综合类/业务类
            if any(kw in content for kw in BRIEFING_PARTY_KEYWORDS):
                print(f"[补充规则2-分类] 党务简报，分类 → 党群类")
                metadata["实体分类名称"] = "党群类"
            elif any(kw in content for kw in BRIEFING_BUSINESS_KEYWORDS):
                print(f"[补充规则2-分类] 档案/培训简报，分类 → 业务类")
                metadata["实体分类名称"] = "业务类"
            else:
                print(f"[补充规则2-分类] 一般简报，分类 → 综合类")
                metadata["实体分类名称"] = "综合类"
            metadata = self._validate_classification_code(metadata)

        # ── 规则1: 公司内部培训 → 业务类 ─────────────────────────────────────
        # 排除条件1：题名含管理类词汇（培训制度/经费/管理/考勤等）
        # 排除条件2：内容涉及党务/党员/党建等党务培训
        # 保管期限处理：不硬编码，仅在LLM判定低于30年时提升到30年（简报除外）
        is_training = any(kw in title for kw in TRAINING_KEYWORDS)
        is_training_mgmt = any(kw in title for kw in TRAINING_MGMT_KEYWORDS)
        is_party_training = any(kw in content for kw in PARTY_TRAINING_KEYWORDS)

        if is_training and not is_training_mgmt and not is_party_training:
            print(f"[补充规则1] 公司内部培训，分类 → 业务类")
            metadata["实体分类名称"] = "业务类"
            # 期限：未锁定时，若LLM判定低于30年则提升；永久则保留
            if not period_locked:
                current_period = metadata.get("保管期限", "")
                if PERIOD_ORDER.get(current_period, 0) < PERIOD_ORDER["30年"]:
                    print(f"[补充规则1] 培训类保管期限: {current_period} → 30年")
                    metadata["保管期限"] = "30年"
            metadata = self._validate_classification_code(metadata)

        # ── 规则3: 档案寄存地址变更 → 10年 ───────────────────────────────────
        if any(kw in content for kw in ADDRESS_CHANGE_KEYWORDS):
            if not period_locked:
                print(f"[补充规则3] 档案寄存地址变更，保管期限 → 10年")
                metadata["保管期限"] = "10年"
            else:
                print(f"[补充规则3] 档案寄存地址变更，期限已锁定（{metadata.get('保管期限')}），跳过")

        # ── 规则4: 公司内部安装/维修类函和通知 → 10年 ────────────────────────
        if any(kw in content for kw in MAINTENANCE_KEYWORDS):
            if any(doc_type in title for doc_type in MAINTENANCE_DOC_TYPES):
                if not period_locked:
                    print(f"[补充规则4] 安装/维修类通知或函，保管期限 → 10年")
                    metadata["保管期限"] = "10年"
                else:
                    print(f"[补充规则4] 安装/维修类，期限已锁定（{metadata.get('保管期限')}），跳过")

        # ── 规则5: 一般事务性通知 → 10年 ─────────────────────────────────────
        # 有文件编号 或 含重要关键词 → 不触发
        if "通知" in title:
            file_number = metadata.get("文件编号")
            has_number = (
                file_number
                and str(file_number).strip()
                and str(file_number) != "null"
            )
            is_important = any(kw in content for kw in IMPORTANT_NOTICE_KEYWORDS)
            if not has_number and not is_important:
                if not period_locked:
                    print(f"[补充规则5] 一般事务通知，保管期限 → 10年")
                    metadata["保管期限"] = "10年"
                else:
                    print(f"[补充规则5] 一般事务通知，期限已锁定（{metadata.get('保管期限')}），跳过")

        # ── 规则6: 公司内部制度/管理办法/条例/实施细则/章程 → 综合类，30年 ────
        if any(kw in title for kw in REGULATION_KEYWORDS):
            if any(kw in content for kw in INTERNAL_ORG_KEYWORDS):
                print(f"[补充规则6] 公司内部制度，分类 → 综合类")
                metadata["实体分类名称"] = "综合类"
                if not period_locked:
                    print(f"[补充规则6] 保管期限 → 30年")
                    metadata["保管期限"] = "30年"
                else:
                    print(f"[补充规则6] 期限已锁定（{metadata.get('保管期限')}），不修改期限")
                metadata = self._validate_classification_code(metadata)

        # ── 规则8: 批评通报 → 30年 ────────────────────────────────────────────
        if any(kw in title for kw in ["批评通报", "通报批评"]):
            if not period_locked:
                print(f"[补充规则8] 批评通报，保管期限 → 30年")
                metadata["保管期限"] = "30年"
            else:
                print(f"[补充规则8] 批评通报，期限已锁定（{metadata.get('保管期限')}），跳过")

        # ── 规则9: 中标结果公示/中标通知函 → 30年 ────────────────────────────
        if "中标" in title and any(kw in title for kw in BID_KEYWORDS):
            if not period_locked:
                print(f"[补充规则9] 中标结果/通知函，保管期限 → 30年")
                metadata["保管期限"] = "30年"
            else:
                print(f"[补充规则9] 中标结果，期限已锁定（{metadata.get('保管期限')}），跳过")

        # ── 规则10: 党支部更换组织/委员/书记的请示 → 党群类，30年 ──────────
        # 排除：换届选举结果类文件（属永久，不得被降级）
        if "党支部" in content:
            is_adjust = any(kw in content for kw in PARTY_BRANCH_ADJUST_KEYWORDS)
            is_target = any(kw in content for kw in PARTY_BRANCH_TARGET_KEYWORDS)
            is_request = "请示" in content
            is_election_result = any(kw in content for kw in PARTY_BRANCH_ELECTION_RESULT_KEYWORDS)

            if is_adjust and is_target and is_request and not is_election_result:
                print(f"[补充规则10] 党支部调整请示，分类 → 党群类")
                metadata["实体分类名称"] = "党群类"
                if not period_locked:
                    print(f"[补充规则10] 保管期限 → 30年")
                    metadata["保管期限"] = "30年"
                else:
                    print(f"[补充规则10] 期限已锁定（{metadata.get('保管期限')}），不修改期限")
                metadata = self._validate_classification_code(metadata)
            elif is_election_result:
                print(f"[补充规则10] 检测到换届选举结果，跳过（期限应为永久）")

        # ── 业务类误判兜底：非档案工作/非培训文件 → 强制纠正为综合类 ───────────
        # 触发条件：LLM将文件分到业务类，但文种/特征明显属于综合类
        # 排除条件：题名含明确的档案工作词或培训词（说明确实是业务类）
        if metadata.get("实体分类名称") == "业务类":
            is_legitimate_business = any(kw in content for kw in BUSINESS_LEGITIMATE_KEYWORDS)
            if not is_legitimate_business:
                # 检查文种：题名中出现综合类典型文种
                is_false_positive = any(doc_type in title for doc_type in BUSINESS_FALSE_POSITIVE_DOC_TYPES)
                if is_false_positive:
                    print(f"[业务类兜底] 题名含综合类文种（{title}），非档案/培训文件，强制纠正 → 综合类")
                    metadata["实体分类名称"] = "综合类"
                    metadata = self._validate_classification_code(metadata)

        # ── 规则7: 本单位带文件编号 → 最少30年（兜底，最后执行）──────────────
        # [Fix3] 使用 PERIOD_ORDER 比较，任何低于30年的期限均提升
        file_number = metadata.get("文件编号")
        has_number = (
            file_number
            and str(file_number).strip()
            and str(file_number) != "null"
        )
        if has_number:
            current_period = metadata.get("保管期限", "")
            if PERIOD_ORDER.get(current_period, 0) < PERIOD_ORDER["30年"]:
                if not period_locked:
                    print(f"[补充规则7] 本单位带文件编号，保管期限: {current_period} → 30年")
                    metadata["保管期限"] = "30年"
                else:
                    print(f"[补充规则7] 带文件编号，但期限已锁定（{current_period}），跳过")

        return metadata

    # ── 优先级2：开放状态与延期开放理由 ──────────────────────────────────────

    def _apply_open_status_rules(self, metadata: Dict, ocr_text: str) -> Dict:
        """
        开放状态判定（默认开放）
        优先级：密级标注 > 文件主要内容
        工作秘密仅以密级标注字段（CONTROLLED_SECURITY_LEVELS）为准，不扫描正文
        延期开放理由只填最主要一个原因
        """
        if not metadata:
            return metadata

        title = str(metadata.get("题名") or "").strip()
        text = ocr_text or ""

        metadata["开放状态"] = "开放"
        metadata["延期开放理由"] = None

        # 第一优先级：密级字段标注
        # [Fix6] 仅使用 CONTROLLED_SECURITY_LEVELS，不再扫描正文 WORK_SECRET_KEYWORDS
        if metadata.get("密级") in CONTROLLED_SECURITY_LEVELS:
            metadata["开放状态"] = "控制"
            metadata["延期开放理由"] = "工作秘密"
            return metadata

        # 第二优先级：文件主要内容（命中即停止）

        # 个人隐私
        if any(kw in title or kw in text for kw in PRIVACY_KEYWORDS):
            metadata["开放状态"] = "控制"
            metadata["延期开放理由"] = "个人隐私"
            return metadata

        # 商业秘密（排除公开中标结果）
        if any(kw in title or kw in text for kw in COMMERCIAL_KEYWORDS):
            if not any(kw in title for kw in COMMERCIAL_EXEMPT_KEYWORDS):
                metadata["开放状态"] = "控制"
                metadata["延期开放理由"] = "商业秘密"
                return metadata

        # 负面信息：题名关键词
        # [Fix7] "约谈"已从 NEGATIVE_TITLE_KEYWORDS 移除，改为"诫勉约谈"精确匹配
        if any(kw in title for kw in NEGATIVE_TITLE_KEYWORDS):
            metadata["开放状态"] = "控制"
            metadata["延期开放理由"] = "负面信息"
            return metadata

        # 负面信息：正则精确匹配（处分类）
        for pattern in NEGATIVE_PATTERNS:
            if re.search(pattern, title) or re.search(pattern, text):
                metadata["开放状态"] = "控制"
                metadata["延期开放理由"] = "负面信息"
                return metadata

        return metadata

    # ── 优先级3：编码格式校验 ─────────────────────────────────────────────────

    def _validate_classification_code(self, metadata: Dict) -> Dict:
        """
        根据文件形成时间年份判断编码
        优先取文件形成时间前4位，降级使用归档年度
        """
        if not metadata:
            return metadata

        year = None

        # 优先：文件形成时间（格式YYYYMMDD）
        formed_time = str(metadata.get("文件形成时间") or "").strip()
        if formed_time and len(formed_time) >= 4:
            try:
                year = int(formed_time[:4])
            except ValueError:
                pass

        # 降级：归档年度
        if not year:
            try:
                year = int(str(metadata.get("归档年度", "")))
            except (ValueError, TypeError):
                return metadata

        category_name = metadata.get("实体分类名称", "")
        expected_code = self._resolve_code(year, category_name)

        if expected_code:
            current_code = metadata.get("实体分类号", "")
            if current_code != expected_code:
                print(
                    f"[编码校验] 实体分类号: {current_code} → {expected_code}"
                    f" (文件年份: {year})"
                )
            metadata["实体分类号"] = expected_code

        return metadata

    @staticmethod
    def _resolve_code(year: int, category_name: str) -> str:
        """
        根据文件年份和分类名称解析编码
        [Fix5] 使用精确匹配（key == category_name），防止"业务管理类"误匹配"业务类"
        """
        mapping = CODE_NEW if year >= CODE_SWITCH_YEAR else CODE_OLD
        return mapping.get(category_name, "")
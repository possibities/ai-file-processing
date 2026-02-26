#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
档案智能分类系统 - 核心分类器
严格执行实体分类标准：党群类DQL/001、综合类ZHL/002、业务类YWL/003
"""

from pathlib import Path
from typing import Dict, List

from langchain.prompts import PromptTemplate

from config.config import Config
from constants import EXAMPLE_OUTPUT_1, EXAMPLE_OUTPUT_2, EXAMPLE_OUTPUT_3, METADATA_SCHEMA
from core.rules_engine import RulesEngine
from infrastructure.llm_client import LlmClient
from infrastructure.ocr_client import OcrClient
from utils.file import get_file_creation_time


class ArchiveClassifier:
    """
    档案智能分类器

    职责：
      - 协调OCR、LLM、规则引擎三个子系统
      - 构建提示词
      - 组装最终元数据
    """

    def __init__(
        self,
        ocr_lang: str = Config.OCR_LANG,
        llm_model: str = Config.LLM_MODEL,
    ):
        self.ocr_client = OcrClient(lang=ocr_lang)
        self.llm_client = LlmClient(model=llm_model)
        self.rules_engine = RulesEngine()
        self.metadata_schema = METADATA_SCHEMA
        self.extraction_prompt = self._build_extraction_prompt()

    # ── 公开接口 ───────────────────────────────────────────────────────────────

    def process_multi_page_document(
        self, archive_name: str, image_paths: List[str]
    ) -> Dict:
        """
        处理多页档案文件
        """
        print(f"\n{'='*70}")
        print(f"处理档案: {archive_name}")
        print(f"页数: {len(image_paths)} 页")
        print(f"{'='*70}\n")

        # 步骤1: OCR提取
        ocr_text = self.ocr_client.extract_text_from_images(image_paths)

        if not ocr_text:
            print("[错误] OCR未识别到任何文字")
            return {}

        print(f"[OCR结果预览]")
        print("-" * 70)
        preview_length = Config.OCR_PREVIEW_LENGTH
        print(
            ocr_text[:preview_length] + f"\n...(共{len(ocr_text)}字符)"
            if len(ocr_text) > preview_length
            else ocr_text
        )
        print("-" * 70)
        print()

        # 步骤2: LLM信息抽取
        metadata = self._extract_metadata_from_text(ocr_text)

        # 步骤3: 添加额外信息（不依赖LLM的字段）
        if metadata:
            metadata['数字化时间'] = get_file_creation_time(image_paths[0])
            metadata['档案文件夹'] = archive_name
            # 注意：页数由 batch_processor 统一注入，避免重复

        return metadata

    def process_document(self, image_path: str) -> Dict:
        """
        处理单个图像文件(兼容旧接口)
        """
        return self.process_multi_page_document(
            archive_name=Path(image_path).stem,
            image_paths=[image_path],
        )

    # ── 私有方法 ───────────────────────────────────────────────────────────────

    def _extract_metadata_from_text(self, ocr_text: str) -> Dict:
        """
        使用LLM从OCR文本中提取元数据，并应用规则修正
        """
        metadata = self.llm_client.extract_metadata(ocr_text, self.extraction_prompt)

        if not metadata:
            return {}

        # 应用规则修正（按优先级顺序）
        metadata = self.rules_engine.apply_all(metadata, ocr_text)

        print(
            f"[LLM] 成功提取 "
            f"{len([v for v in metadata.values() if v is not None])} 个有效字段"
        )
        return metadata

    def _build_knowledge_base(self) -> str:
        """
        构建分类知识库 - 补充规则优先
        """
        return """
【!!!最高优先级规则 - 必须首先检查!!!】
以下10条规则优先级最高，遇到匹配情况时直接应用，无需参考后续基础规则：

★规则1: 内容涉及"公司内部培训"
   → 强制归类：业务类 (2020起:YWL / 2020前:003)
   → 保管期限：30年（除非注明极重要则永久）

★规则2: 题名包含"简报"
   → 保管期限：10年（所有简报统一适用，此期限不被其他规则覆盖）
   → 分类按简报内容判断：
     · 内容涉及党务工作（党风廉政/党支部/党员/党建/纪委/廉政/工青妇/工会/团委）→ 党群类
     · 内容涉及档案整理/档案管理/公司内部培训 → 业务类
     · 其余 → 综合类

★规则3: 内容涉及"档案寄存地址变更"
   → 保管期限：10年

★规则4: 内容涉及"安装"或"维修" + 文种为"函"或"通知"（限公司内部）
   → 保管期限：10年

★规则5: 一般事务性"通知"（无文件编号、非重要事项）
   → 保管期限：10年

★规则6: 内容涉及"制度"、"管理办法"、"条例"（限公司内部制定）
   → 强制归类：综合类 (2020起:ZHL / 2020前:002)
   → 保管期限：30年

★规则7: 本单位产生且"带有文件编号"的文件
   → 判断方式：发文单位为本单位，且含本单位文号标识（非上级来文）
   → 保管期限：至少30年
   （若通用规则判定为永久→永久；若判定为10年→强制提升为30年）

★规则8: 题名包含"批评通报"
   → 保管期限：30年

★规则9: 题名包含"中标结果公示"或"中标通知函"
   → 保管期限：30年

★规则10: 题名包含"党支部" + "更换/调整" + "组织/委员" + "请示"
   → 保管期限：30年（注意：区别于换届选举结果的永久）

【实体分类编码规则 - 严格执行】
2020年起必须使用：DQL(党群) / ZHL(综合) / YWL(业务)
2020年前必须使用：001(党群) / 002(综合) / 003(业务)

【强制留空字段】
全宗号 = null
档案馆代码 = null
档案馆名称 = null
外包单位名称 = null

【党群类 (条目1-10)】
1. 本级机关党支部换届、党员代表大会会议文件材料、选举结果 → 永久
2. 参加上级机关党务工作会议材料 → 重要的：永久 / 一般的：10年
3. 本级机关关于党的建设及党员干部表彰、处分等工作的计划、总结、决定、通知 → 重要的（含警告以上处分）：永久 / 一般的（含警告处分）：30年
4. 上级机关有关党务工作的来文 → 重要的：30年 / 一般的：10年
5. 本级党支部会议纪要、记录 → 永久
6. 本级党支部重大决定、任免通知 → 永久
7. 党支部民主生活会记录及发言材料 → 30年
8. 党支部中心组学习记录及其他材料 → 10年
9. 本级机关党员花名册、党团员统计年报表、组织关系介绍信存根 → 永久
10. 本机关工青妇工作的文件材料 → 重要的：30年 / 一般的：10年

【综合类 (条目11-26)】
11. 本级机关召开的综合性工作会议材料 → 请示、批复、通知、名单、日程、报告、讲话、决议、决定、纪要、典型发言材料：永久 / 会议简报、书面交流材料等：10年（规则2优先）
12. 本级机关召开的专题性会议材料 → 重要的：永久 / 一般的：30年
13. 本机关行政办公会议、专题会议纪要、记录 → 永久
14. 上级机关召开的综合性会议材料 → 会议通知、日程、名单、报告、讲话、决定、决议、纪要、典型发言材料：30年 / 会议简报、书面交流材料等：10年（规则2优先）
15. 上级机关、同级机关召开专题会议材料 → 重要的：30年 / 一般的：10年
16. 本级关于机要、保密、后勤管理等工作的请示、批复、规定、意见、通知、函等 → 重要的：永久 / 一般的：10年
17. 上级机关、同级机关关于机要、保密、后勤管理等方面来文 → 重要的：30年 / 一般的：10年
18. 公司颁发的各类管理制度、条例、规定、办法等文件 → 30年
19. 本级机关干部职工名册、人事关系介绍信存根、干部定期统计表 → 永久
20. 本级机关综合性的工作计划、规划、总结 → 年度和年度以上的：永久 / 年度以下的：10年
21. 人大建议、政协提案办理答复意见 → 主办的：永久 / 协办的：30年
22. 本级机关处理人民来信来访的材料 → 有领导指示或处理结果的：永久 / 一般的：10年
23. 本级机关行政关系介绍信存根、使用印章登记簿 → 永久
24. 本机关文书档案移交清册 → 永久
25. 同级或下级的来文、来函 → 重要的：30年 / 一般的：10年
26. 本机关日常事务工作形成的文件材料 → 重要的：永久 / 一般的：10年

【业务类 (条目27-30)】
27. 本级机关召开的档案工作专题会议材料 → 重要的：永久 / 一般的：30年
28. 上级机关召开的档案工作会议材料 → 重要的：30年 / 一般的：10年
29. 本单位档案整理、规范工作的请示、批复、规定、意见、通知、函、调研报告、签报、计划、总结等 → 重要的：永久 / 一般的：30年
30. 公司内部培训通知、培训材料、培训计划、培训总结等 → 重要的：永久 / 一般的：30年
"""

    def _build_extraction_prompt(self) -> PromptTemplate:
        """构建提示词模板"""

        rules_context = self._build_knowledge_base()
        fields_desc = "\n".join(
            [f"- {k}: {v}" for k, v in self.metadata_schema.items()]
        )

        ex1 = EXAMPLE_OUTPUT_1.replace("{", "{{").replace("}", "}}")
        ex2 = EXAMPLE_OUTPUT_2.replace("{", "{{").replace("}", "}}")
        ex3 = EXAMPLE_OUTPUT_3.replace("{", "{{").replace("}", "}}")

        template = f"""你是专业档案整理员。严格按照以下流程提取元数据：

{rules_context}

【步骤1：密级和保密期限】
仅当文件第一页顶部或版头处明确印有以下标注文字时才填写，否则一律填null：
- 密级：非涉密/内部/秘密/机密/绝密
- 保密期限：1年/5年/10年

★ 严格禁止：
- 不得根据文件正文内容推断密级
- 不得因正文提到"涉密"、"保密"、"机密"、"秘密"等词语而填写密级
- 密级字段只认文件版头处的明确标注，无标注一律填null

【步骤2：开放状态与延期开放理由】
按优先级顺序判断，命中即停止：

① 有密级标注：
   - 标注"内部/秘密/机密/绝密" → 开放状态：控制 / 延期开放理由：工作秘密
   - 标注"非涉密" → 开放状态：开放 / 延期开放理由：null

② 无密级标注，看文件主要内容（取最主要的一个原因）：
   - 批评处分类（批评通报、通报批评、党纪/行政处分、撤职、开除、问责、约谈、诫勉谈话）
     → 开放状态：控制 / 延期开放理由：负面信息
   - 个人隐私（工资表、薪酬明细、身份证号、家庭住址、个人档案）
     → 开放状态：控制 / 延期开放理由：个人隐私
   - 商业秘密（报价单、成本核算、利润分析、客户名单）
     → 开放状态：控制 / 延期开放理由：商业秘密
   - 其余一律 → 开放状态：开放 / 延期开放理由：null

★ 注意：会议纪要仅在主要内容为批评处分时才控制，附带提及不算。
★ 注意：中标结果、中标公示一律开放。

【步骤3：实体分类判断补充说明】
综合类与业务类边界（极易混淆，必须严格区分）：

归综合类的典型文件：
- 行政办公、后勤管理、机要保密相关文件
- 公司颁发的制度、规定、办法
- 综合性/专题性工作会议材料
- 工作计划、总结、报告
- 人事名册、介绍信存根
- 批评通报、中标通知
- 一般事务通知、函

归业务类的典型文件（仅限以下情形）：
- 档案整理、档案规范、档案管理相关文件
- 公司内部组织的业务培训（非党务培训）

★ 判断原则：不确定时优先归综合类，业务类仅限档案业务和公司内部培训两类。

【步骤4：字段提取规则】

▶ 归档年度：无明确标注时取文件形成时间年份

▶ 实体分类号：严格按文件形成时间年份判断
   - 文件形成时间 2020年及以后 → DQL/ZHL/YWL
   - 文件形成时间 2020年以前 → 001/002/003

▶ 题名：
   - 优先取文件头部居中正式标题
   - 超过50字时简化为：责任者+事由+文种
   - 无标题时概括为：单位+事由+文种
   - 禁止直接复制正文段落

▶ 责任者：优先取落款盖章单位，无盖章取发文单位，两者不一致以盖章为准

▶ 立档单位名称：与责任者一致，取文件落款盖章单位；无盖章则取发文单位

▶ 重要/一般判断：
   - 重要：重大决策、全局性工作、年度以上计划、有文件编号、上报上级材料
   - 一般：日常事务、临时性、无文件编号、过程性材料

【需提取的字段】
{fields_desc}

【OCR识别文本】
{{ocr_text}}

【输出前必查（仅列高频易错项）】
✓ 实体分类号：严格按文件形成时间年份，2020及以后→DQL/ZHL/YWL，2020以前→001/002/003
✓ 简报→期限必须10年，不得被其他规则覆盖
✓ 档案馆代码、档案馆名称→必须为null
✓ 业务类仅限：档案业务文件、公司内部培训；其余一律综合类
✓ 开放状态→密级标注优先；无标注看主要内容；默认开放
✓ 延期开放理由→控制时填最主要一个原因，开放时null

【JSON输出示例1 - 2020年培训简报（开放）】
{ex1}

【JSON输出示例2 - 批评通报（控制）】
{ex2}

【JSON输出示例3 - 工资表（控制）】
{ex3}

请只输出JSON，不要包含markdown或其他文字：
"""
        return PromptTemplate(
            input_variables=["ocr_text"],
            template=template,
        )
# -*- coding: utf-8 -*-
"""扫描件 OCR。要求：输出必须回填页码，供溯源使用。"""


def ocr_pdf(path: str, lang: str = "chi_sim+eng") -> list[dict]:
    """TODO: 方案 A PaddleOCR（中文表格强）；方案 B RapidOCR；方案 C 云端 OCR。

    Returns:
        [{"page": 1, "text": "...", "conf": 0.93}]
    """
    raise NotImplementedError

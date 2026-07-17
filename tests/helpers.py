from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook


def create_xlsx(path: Path, value: str = "sample") -> Path:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet["A1"] = value
    workbook.save(path)
    workbook.close()
    return path


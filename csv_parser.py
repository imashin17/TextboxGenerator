"""CSVファイルのパースとkintoneレコード変換"""
import csv
import chardet
import io
from typing import Optional


KINTONE_FIELD_TYPES = {
    "SINGLE_LINE_TEXT": "テキスト（1行）",
    "MULTI_LINE_TEXT": "テキスト（複数行）",
    "NUMBER": "数値",
    "DATE": "日付",
    "DATETIME": "日時",
    "DROP_DOWN": "ドロップダウン",
    "CHECK_BOX": "チェックボックス",
    "RADIO_BUTTON": "ラジオボタン",
}


def detect_encoding(file_bytes: bytes) -> str:
    """ファイルのエンコーディングを自動検出する"""
    result = chardet.detect(file_bytes)
    encoding = result.get("encoding") or "utf-8"
    # Shift_JIS系の正規化
    if encoding.lower() in ("shift_jis", "shift-jis", "sjis", "cp932"):
        encoding = "cp932"
    return encoding


def parse_csv(file_bytes: bytes, encoding: Optional[str] = None) -> tuple[list[str], list[dict]]:
    """
    CSVをパースしてヘッダーと行データを返す

    Returns:
        (headers, rows): ヘッダーリストと辞書形式の行リスト
    """
    if encoding is None:
        encoding = detect_encoding(file_bytes)

    text = file_bytes.decode(encoding, errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    headers = reader.fieldnames or []
    rows = [dict(row) for row in reader]
    return list(headers), rows


def build_kintone_records(
    rows: list[dict],
    field_mapping: dict[str, str],
    field_types: Optional[dict[str, str]] = None,
) -> list[dict]:
    """
    CSVの行データをkintoneレコード形式に変換する

    Args:
        rows: CSVの行データリスト
        field_mapping: {CSVカラム名: kintoneフィールドコード} のマッピング
        field_types: {kintoneフィールドコード: フィールドタイプ} (省略時は全てSINGLE_LINE_TEXT扱い)

    Returns:
        kintone APIに渡すrecordsリスト
    """
    if field_types is None:
        field_types = {}

    records = []
    for row in rows:
        record = {}
        for csv_col, kintone_field in field_mapping.items():
            raw_value = row.get(csv_col, "")
            field_type = field_types.get(kintone_field, "SINGLE_LINE_TEXT")
            record[kintone_field] = _format_field_value(raw_value, field_type)
        records.append(record)
    return records


def _format_field_value(value: str, field_type: str) -> dict:
    """フィールドタイプに応じた値フォーマットを返す"""
    value = value.strip() if value else ""

    if field_type == "NUMBER":
        # 数値型: カンマや円記号を除去
        cleaned = value.replace(",", "").replace("¥", "").replace("￥", "").strip()
        return {"value": cleaned if cleaned else "0"}

    if field_type in ("CHECK_BOX",):
        # 複数選択: カンマ区切りをリストに変換
        items = [v.strip() for v in value.split(",") if v.strip()]
        return {"value": items}

    return {"value": value}


def chunk_records(records: list, size: int = 100) -> list[list]:
    """レコードリストをkintone APIの上限サイズ(100件)に分割する"""
    return [records[i : i + size] for i in range(0, len(records), size)]

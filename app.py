"""生産管理ソフト777 → kintone データ同期アプリ"""
import json
import os
from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
from csv_parser import parse_csv, build_kintone_records, chunk_records
from kintone_client import KintoneClient

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/upload-csv", methods=["POST"])
def upload_csv():
    """CSVファイルをアップロードしてヘッダーとプレビューを返す"""
    if "file" not in request.files:
        return jsonify({"error": "ファイルが選択されていません"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "ファイルが選択されていません"}), 400
    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "CSVファイルを選択してください"}), 400

    file_bytes = file.read()
    try:
        headers, rows = parse_csv(file_bytes)
    except Exception as e:
        return jsonify({"error": f"CSVの読み込みに失敗しました: {str(e)}"}), 400

    # セッションにCSVデータを保持
    session["csv_rows"] = rows[:5000]  # 最大5000行
    session["csv_headers"] = headers

    return jsonify({
        "headers": headers,
        "preview": rows[:5],
        "total_rows": len(rows),
    })


@app.route("/api/kintone-fields", methods=["POST"])
def get_kintone_fields():
    """kintoneアプリのフィールド一覧を取得する"""
    data = request.get_json()
    try:
        client = KintoneClient(
            domain=data.get("domain"),
            app_id=int(data.get("app_id", 0)),
            api_token=data.get("api_token"),
        )
        fields = client.get_app_fields()
    except Exception as e:
        return jsonify({"error": str(e)}), 400

    # セッションに接続情報を保持
    session["kintone_domain"] = data.get("domain")
    session["kintone_app_id"] = int(data.get("app_id", 0))
    session["kintone_api_token"] = data.get("api_token")

    # UIに必要なフィールド情報を返す
    field_list = [
        {
            "code": code,
            "label": info.get("label", code),
            "type": info.get("type", ""),
        }
        for code, info in fields.items()
        if info.get("type") not in ("RECORD_NUMBER", "CREATED_TIME", "UPDATED_TIME",
                                    "CREATOR", "MODIFIER", "STATUS", "CATEGORY")
    ]
    return jsonify({"fields": field_list})


@app.route("/api/sync", methods=["POST"])
def sync_to_kintone():
    """CSVデータをkintoneに同期する"""
    data = request.get_json()
    field_mapping = data.get("field_mapping", {})
    mode = data.get("mode", "add")  # "add" or "upsert"
    update_key = data.get("update_key", "")

    rows = session.get("csv_rows")
    if not rows:
        return jsonify({"error": "CSVデータが見つかりません。再度アップロードしてください"}), 400

    if not field_mapping:
        return jsonify({"error": "フィールドマッピングが設定されていません"}), 400

    try:
        client = KintoneClient(
            domain=session.get("kintone_domain"),
            app_id=session.get("kintone_app_id"),
            api_token=session.get("kintone_api_token"),
        )
    except Exception as e:
        return jsonify({"error": f"kintone接続エラー: {str(e)}"}), 400

    # フィールドタイプを取得
    try:
        fields_info = client.get_app_fields()
        field_types = {code: info.get("type", "SINGLE_LINE_TEXT")
                       for code, info in fields_info.items()}
    except Exception:
        field_types = {}

    # kintoneレコード形式に変換
    records = build_kintone_records(rows, field_mapping, field_types)
    chunks = chunk_records(records, 100)

    total_added = 0
    total_updated = 0
    errors = []

    for i, chunk in enumerate(chunks):
        try:
            if mode == "upsert" and update_key:
                result = client.upsert_records(chunk, update_key)
                total_updated += len(result.get("records", []))
            else:
                result = client.add_records(chunk)
                total_added += len(result.get("ids", []))
        except Exception as e:
            errors.append(f"チャンク{i + 1}でエラー: {str(e)}")

    return jsonify({
        "success": len(errors) == 0,
        "total_added": total_added,
        "total_updated": total_updated,
        "errors": errors,
        "message": f"{total_added + total_updated}件処理しました" + (
            f"（{len(errors)}件のエラーあり）" if errors else ""
        ),
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

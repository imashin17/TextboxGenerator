"""kintone REST APIクライアント"""
import os
import requests
from typing import Optional


class KintoneClient:
    def __init__(
        self,
        domain: Optional[str] = None,
        app_id: Optional[int] = None,
        api_token: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.domain = domain or os.getenv("KINTONE_DOMAIN")
        self.app_id = app_id or int(os.getenv("KINTONE_APP_ID", "0"))
        self.api_token = api_token or os.getenv("KINTONE_API_TOKEN")
        self.username = username or os.getenv("KINTONE_USERNAME")
        self.password = password or os.getenv("KINTONE_PASSWORD")

        if not self.domain:
            raise ValueError("KINTONE_DOMAINが設定されていません")
        if not self.app_id:
            raise ValueError("KINTONE_APP_IDが設定されていません")
        if not self.api_token and not (self.username and self.password):
            raise ValueError("KINTONE_API_TOKEN または ユーザー認証情報が必要です")

        self.base_url = f"https://{self.domain}/k/v1"
        self.session = requests.Session()
        self._set_auth_headers()

    def _set_auth_headers(self):
        if self.api_token:
            self.session.headers.update({"X-Cybozu-API-Token": self.api_token})
        elif self.username and self.password:
            import base64
            credentials = base64.b64encode(
                f"{self.username}:{self.password}".encode()
            ).decode()
            self.session.headers.update({"X-Cybozu-Authorization": credentials})
        self.session.headers.update({"Content-Type": "application/json"})

    def get_app_fields(self) -> dict:
        """アプリのフィールド一覧を取得する"""
        resp = self.session.get(
            f"{self.base_url}/app/form/fields.json",
            params={"app": self.app_id},
        )
        resp.raise_for_status()
        return resp.json().get("properties", {})

    def add_records(self, records: list[dict]) -> dict:
        """レコードを一括登録する (最大100件)"""
        resp = self.session.post(
            f"{self.base_url}/records.json",
            json={"app": self.app_id, "records": records},
        )
        resp.raise_for_status()
        return resp.json()

    def upsert_records(
        self, records: list[dict], update_key_field: str
    ) -> dict:
        """レコードを一括更新/登録する (upsert, 最大100件)"""
        upsert_records = []
        for record in records:
            key_value = record.get(update_key_field, {}).get("value")
            upsert_records.append(
                {
                    "updateKey": {
                        "field": update_key_field,
                        "value": key_value,
                    },
                    "record": {
                        k: v for k, v in record.items() if k != update_key_field
                    },
                }
            )
        resp = self.session.put(
            f"{self.base_url}/records.json",
            json={"app": self.app_id, "records": upsert_records},
        )
        resp.raise_for_status()
        return resp.json()

    def get_records(self, query: str = "", fields: list[str] = None) -> list[dict]:
        """レコードを取得する"""
        params = {"app": self.app_id, "query": query}
        if fields:
            params["fields[0]"] = fields
        resp = self.session.get(f"{self.base_url}/records.json", params=params)
        resp.raise_for_status()
        return resp.json().get("records", [])

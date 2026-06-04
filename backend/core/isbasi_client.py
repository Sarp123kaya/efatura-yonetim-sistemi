#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared İşbaşı API client for customer/payment import workflows."""

from __future__ import annotations

import logging
import re
import sys
import getpass
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests

from .config import config
from .isbasi_endpoints import ISBASI_ENDPOINTS, payment_endpoint_verification

logger = logging.getLogger(__name__)


class IsbasiAPIError(RuntimeError):
    """Raised when İşbaşı returns an HTTP or application-level error."""


@dataclass
class IsbasiLoginState:
    access_token: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    tenant_id: Optional[str] = None
    user_name: Optional[str] = None


class IsbasiApiClient:
    """Small requests-based client aligned with the existing extractor headers."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = 30,
        verify_ssl: Optional[bool] = None,
    ) -> None:
        self.base_url = (base_url or config.ISBASI_BASE_URL).rstrip("/")
        self.api_key = api_key or config.ISBASI_API_KEY
        self.username = username or config.ISBASI_USERNAME
        self.password = password if password is not None else config.ISBASI_PASSWORD
        self.timeout = timeout
        self.verify_ssl = config.ISBASI_VERIFY_SSL if verify_ssl is None else verify_ssl
        self.login_state: Optional[IsbasiLoginState] = None

        self.session = requests.Session()
        self.session.verify = self.verify_ssl
        self.session.headers.update(
            {
                "ApiKey": self.api_key,
                "apiKey": self.api_key,
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                "User-Agent": "Efatura-Transfer-System/1.0",
                "DeviceName": "Efatura-Transfer-System",
                "DeviceType": "WEB",
                "Lang": "tr-TR",
            }
        )

        if config.ISBASI_USER_ID:
            self.session.headers.update({"UserId": config.ISBASI_USER_ID})
        if config.ISBASI_USER_EMAIL:
            self.session.headers.update({"UserEmail": config.ISBASI_USER_EMAIL})
        if config.ISBASI_TENANT_ID:
            self.session.headers.update({"tenantId": config.ISBASI_TENANT_ID})

    def validate_credentials(self, require_password: bool = False) -> None:
        missing = []
        if not self.api_key:
            missing.append("ISBASI_API_KEY")
        if not self.username:
            missing.append("ISBASI_USERNAME")
        if require_password and not self.password:
            missing.append("ISBASI_PASSWORD")
        if missing:
            raise IsbasiAPIError("Eksik İşbaşı konfigürasyonu: " + ", ".join(missing))

    def login(self, password: Optional[str] = None) -> IsbasiLoginState:
        """Login non-interactively and update session headers."""

        if password is not None:
            self.password = password
        if not self.password and sys.stdin.isatty():
            self.password = getpass.getpass("İşbaşı şifresi: ").strip()
        self.validate_credentials(require_password=True)

        spec = ISBASI_ENDPOINTS["login"]
        response = self.session.post(
            self._url(spec.path),
            json={"username": self.username, "password": self.password},
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        payload = self._parse_response(response)
        data = payload.get("data") or {}
        access_token = data.get("accessToken")
        if not access_token:
            raise IsbasiAPIError("Login basarili gorundu fakat accessToken donmedi.")

        state = IsbasiLoginState(
            access_token=access_token,
            user_id=data.get("id") or data.get("userId"),
            user_email=data.get("email") or self.username,
            tenant_id=data.get("tenantId"),
            user_name=data.get("userName") or data.get("name"),
        )
        self.login_state = state

        self.session.headers.update({"Authorization": f"Bearer {state.access_token}"})
        if state.user_id:
            self.session.headers.update({"UserId": str(state.user_id)})
        if state.user_email:
            self.session.headers.update({"UserEmail": str(state.user_email)})
        if state.tenant_id:
            self.session.headers.update({"tenantId": str(state.tenant_id)})
        if state.user_name:
            self.session.headers.update({"UserName": str(state.user_name)})

        return state

    def ensure_logged_in(self) -> None:
        if not self.login_state:
            self.login()

    def list_firms(
        self,
        filters: Optional[List[Dict[str, Any]]] = None,
        sorting: Optional[Dict[str, Any]] = None,
        page_size: int = 100,
        max_pages: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch firm/customer cards from `POST /api/v1.0/firms/firms`."""

        self.ensure_logged_in()
        spec = ISBASI_ENDPOINTS["firms_list"]
        all_rows: List[Dict[str, Any]] = []

        for page in range(1, max_pages + 1):
            payload = {
                "filters": filters if filters is not None else [{"columnName": "isActive", "operator": "IsEqualTo", "value": True}],
                "sorting": sorting if sorting is not None else {"name": "Asc"},
                "paging": {"currentPage": page, "pageSize": page_size},
                "count": True,
                "excel": {"export": False, "allowedColumns": None, "lucaExport": False},
            }
            result = self.post(spec.path, payload)
            data = result.get("data") or {}
            rows = data.get("data") if isinstance(data, dict) else []
            rows = rows or []
            all_rows.extend(rows)

            count = data.get("count") if isinstance(data, dict) else None
            if len(rows) < page_size:
                break
            if count is not None and len(all_rows) >= int(count):
                break

        return all_rows

    def list_sales_invoices(
        self,
        filters: Optional[List[Dict[str, Any]]] = None,
        sorting: Optional[Dict[str, Any]] = None,
        page_size: int = 100,
        max_pages: int = 100,
    ) -> List[Dict[str, Any]]:
        """Fetch outgoing/sales invoices from `POST /api/v1.0/invoices/invoices`."""

        self.ensure_logged_in()
        spec = ISBASI_ENDPOINTS["sales_invoice_list"]
        return self._list_endpoint(
            spec.path,
            filters=filters or [],
            sorting=sorting if sorting is not None else {"date": -1},
            page_size=page_size,
            max_pages=max_pages,
        )

    def list_customer_sales_activity(
        self,
        *,
        firm_id: str = "",
        firm_code: str = "",
        tax_id: str = "",
        firm_name: str = "",
        start_date: str = "",
        end_date: str = "",
        page_size: int = 100,
        max_pages: int = 100,
        allow_full_scan: bool = False,
    ) -> List[Dict[str, Any]]:
        """Read the sales/payment-related view for a single customer.

        Swagger does not expose a separate customer check/collection endpoint.
        The closest documented read path is the sales invoice list, which carries
        payment fields and firm identifiers. This method first tries server-side
        firm filters, then optionally falls back to local filtering.
        """

        base_filters = self._date_filters(start_date, end_date)
        filter_attempts: List[List[Dict[str, Any]]] = []
        if firm_id:
            filter_attempts.append(base_filters + [{"columnName": "firmId", "operator": 3, "value": str(firm_id)}])
            filter_attempts.append(base_filters + [{"columnName": "firm.firmId", "operator": 3, "value": str(firm_id)}])
        if firm_code:
            filter_attempts.append(base_filters + [{"columnName": "firmCode", "operator": 3, "value": str(firm_code)}])
        if tax_id:
            filter_attempts.append(base_filters + [{"columnName": "firmVknNo", "operator": 3, "value": _digits(tax_id)}])
        if firm_name:
            filter_attempts.append(base_filters + [{"columnName": "firmName", "operator": 15, "value": str(firm_name)}])

        errors: List[str] = []
        for filters in filter_attempts:
            try:
                rows = self.list_sales_invoices(filters=filters, page_size=page_size, max_pages=max_pages)
            except IsbasiAPIError as exc:
                errors.append(str(exc))
                continue
            matched = self._filter_customer_rows(rows, firm_id=firm_id, firm_code=firm_code, tax_id=tax_id, firm_name=firm_name)
            if matched:
                return matched

        if allow_full_scan:
            rows = self.list_sales_invoices(filters=base_filters, page_size=page_size, max_pages=max_pages)
            return self._filter_customer_rows(rows, firm_id=firm_id, firm_code=firm_code, tax_id=tax_id, firm_name=firm_name)

        if errors:
            logger.debug("Customer sales activity filter attempts failed: %s", errors)
        return []

    def get_firm(self, firm_id: str) -> Dict[str, Any]:
        """Fetch a single firm/customer card detail."""

        self.ensure_logged_in()
        path = ISBASI_ENDPOINTS["firm_detail"].path.replace("{id}", str(firm_id))
        result = self.get(path)
        return result.get("data") or {}

    def get_customer_account_snapshot(
        self,
        firm_id: str,
        *,
        start_date: str = "",
        end_date: str = "",
        include_sales_activity: bool = True,
        allow_full_scan: bool = False,
    ) -> Dict[str, Any]:
        """Fetch firm card details plus documented sales/payment-related records."""

        firm = self.get_firm(firm_id)
        activity: List[Dict[str, Any]] = []
        if include_sales_activity:
            activity = self.list_customer_sales_activity(
                firm_id=firm_id,
                firm_code=str(firm.get("code") or ""),
                tax_id=str(firm.get("taxOrPersonalId") or firm.get("vknTckn") or ""),
                firm_name=str(firm.get("name") or firm.get("displayName") or ""),
                start_date=start_date,
                end_date=end_date,
                allow_full_scan=allow_full_scan,
            )
        return {"firm": firm, "sales_activity": activity}

    def verify_customer_payment_endpoint(self) -> Dict[str, object]:
        """Return the current Swagger-backed customer payment endpoint status."""

        return payment_endpoint_verification()

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        response = self.session.get(
            self._url(path),
            params=params,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        return self._parse_response(response)

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.post(
            self._url(path),
            json=payload,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        return self._parse_response(response)

    def _list_endpoint(
        self,
        path: str,
        *,
        filters: List[Dict[str, Any]],
        sorting: Dict[str, Any],
        page_size: int,
        max_pages: int,
    ) -> List[Dict[str, Any]]:
        all_rows: List[Dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            payload = {
                "filters": filters,
                "sorting": sorting,
                "paging": {"currentPage": page, "pageSize": page_size},
                "columnNames": None,
                "count": True,
                "excel": {"export": False, "allowedColumns": None, "lucaExport": False},
            }
            result = self.post(path, payload)
            data = result.get("data") or {}
            rows = data.get("data") if isinstance(data, dict) else []
            rows = rows or []
            all_rows.extend(rows)

            count = data.get("count") if isinstance(data, dict) else None
            if len(rows) < page_size:
                break
            if count is not None and len(all_rows) >= int(count):
                break
        return all_rows

    def _date_filters(self, start_date: str = "", end_date: str = "") -> List[Dict[str, Any]]:
        filters: List[Dict[str, Any]] = []
        if start_date:
            filters.append({"columnName": "date", "operator": 5, "value": start_date})
        if end_date:
            filters.append({"columnName": "date", "operator": 2, "value": end_date})
        return filters

    def _filter_customer_rows(
        self,
        rows: List[Dict[str, Any]],
        *,
        firm_id: str = "",
        firm_code: str = "",
        tax_id: str = "",
        firm_name: str = "",
    ) -> List[Dict[str, Any]]:
        normalized_name = _normalize_text(firm_name)
        normalized_code = _normalize_text(firm_code)
        normalized_tax = _digits(tax_id)
        result: List[Dict[str, Any]] = []

        for row in rows:
            firm = row.get("firm") if isinstance(row.get("firm"), dict) else {}
            row_firm_id = str(firm.get("firmId") or row.get("firmId") or "")
            row_firm_code = str(row.get("firmCode") or firm.get("firmCode") or "")
            row_tax_id = str(row.get("firmVknNo") or row.get("taxNo") or firm.get("taxNo") or "")
            row_name = str(row.get("firmName") or firm.get("name") or firm.get("displayName") or "")

            if firm_id and row_firm_id and str(firm_id) == row_firm_id:
                result.append(row)
                continue
            if normalized_code and normalized_code == _normalize_text(row_firm_code):
                result.append(row)
                continue
            if normalized_tax and normalized_tax == _digits(row_tax_id):
                result.append(row)
                continue
            if normalized_name and normalized_name == _normalize_text(row_name):
                result.append(row)
                continue

        return result

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}{path}"

    def _parse_response(self, response: requests.Response) -> Dict[str, Any]:
        response.encoding = "utf-8"
        if response.status_code >= 400:
            raise IsbasiAPIError(f"HTTP {response.status_code}: {response.text[:500]}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise IsbasiAPIError(f"JSON olmayan cevap: {response.text[:500]}") from exc

        if isinstance(payload, dict) and payload.get("isError"):
            raise IsbasiAPIError(str(payload.get("message") or payload))
        return payload


def filter_active_firms_by_tax_ids(tax_ids: Iterable[str]) -> List[Dict[str, Any]]:
    """Build İşbaşı firm filters for a tax-id focused lookup."""

    cleaned = [str(value).strip() for value in tax_ids if str(value or "").strip()]
    filters: List[Dict[str, Any]] = [{"columnName": "isActive", "operator": "IsEqualTo", "value": True}]
    if cleaned:
        filters.append({"columnName": "vknTckn", "operator": "In", "value": cleaned})
    return filters


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    replacements = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    text = text.translate(replacements)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    return text.strip()

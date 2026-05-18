#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Swagger-backed İşbaşı endpoint matrix.

This module intentionally keeps the endpoint inventory explicit. It prevents
payment-like endpoints from being used for the wrong accounting document type.
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class IsbasiEndpointSpec:
    """A small contract summary extracted from the İşbaşı Swagger document."""

    key: str
    method: str
    path: str
    tag: str
    summary: str
    purpose: str
    creates_customer_payment: bool = False
    risk_note: Optional[str] = None


ISBASI_ENDPOINTS: Dict[str, IsbasiEndpointSpec] = {
    "login": IsbasiEndpointSpec(
        key="login",
        method="POST",
        path="/api/v1.0/user/integrationLogin",
        tag="User",
        summary="Integration login",
        purpose="Returns accessToken and tenant/user headers used by other API calls.",
    ),
    "firms_list": IsbasiEndpointSpec(
        key="firms_list",
        method="POST",
        path="/api/v1.0/firms/firms",
        tag="Musteri/Tedarikci",
        summary="Cari liste",
        purpose="Lists customers/suppliers with id, code, name, firmType, vknTckn and balances.",
    ),
    "firm_detail": IsbasiEndpointSpec(
        key="firm_detail",
        method="GET",
        path="/api/v1.0/firms/{id}",
        tag="Musteri/Tedarikci",
        summary="Cari detay",
        purpose="Reads a single customer/supplier card including taxOrPersonalId and bank data.",
    ),
    "firm_upsert": IsbasiEndpointSpec(
        key="firm_upsert",
        method="PUT",
        path="/api/v1.0/firms",
        tag="Musteri/Tedarikci",
        summary="Cari guncelleme/olusturma",
        purpose="Creates or updates firm card data. It must not be used as a payment posting API.",
        risk_note="Changing balance fields is not equivalent to creating an auditable payment transaction.",
    ),
    "sales_invoice_upsert": IsbasiEndpointSpec(
        key="sales_invoice_upsert",
        method="POST",
        path="/api/v1.0/invoices/integrationInvoices",
        tag="Fatura",
        summary="Satis faturasi kaydetme/guncelleme",
        purpose="Creates or updates sales invoices and can match customer by code or tax id.",
    ),
    "sales_invoice_list": IsbasiEndpointSpec(
        key="sales_invoice_list",
        method="POST",
        path="/api/v1.0/invoices/invoices",
        tag="Fatura",
        summary="Satis faturalari listesi",
        purpose=(
            "Lists outgoing/sales invoices. Response includes firm fields and payment-related "
            "columns such as paymentDate, paymentStatus, remainingTotal, safeOrBankName and caseOrBankName."
        ),
    ),
    "purchase_invoice_list": IsbasiEndpointSpec(
        key="purchase_invoice_list",
        method="POST",
        path="/api/v1.0/invoices/invoices?type=2",
        tag="Gider",
        summary="Gider listesi",
        purpose="Lists purchase/expense invoices including payment status and firm fields.",
    ),
    "purchase_invoice_detail": IsbasiEndpointSpec(
        key="purchase_invoice_detail",
        method="GET",
        path="/api/v1.0/invoices/{gider id}/purchase",
        tag="Gider",
        summary="Gider detay",
        purpose="Reads line/detail data for a purchase/expense invoice.",
    ),
    "smm_list": IsbasiEndpointSpec(
        key="smm_list",
        method="POST",
        path="/api/v1.0/Payments/smms",
        tag="Serbest Meslek Makbuzu",
        summary="SMM listeleme",
        purpose="Lists self-employment receipts. It is not a customer check collection endpoint.",
        risk_note="Despite the Payments path, the Swagger description is for SMM records.",
    ),
    "smm_create": IsbasiEndpointSpec(
        key="smm_create",
        method="PUT",
        path="/api/v1.0/Payments/smm",
        tag="Serbest Meslek Makbuzu",
        summary="SMM olusturma",
        purpose="Creates a self-employment receipt. It is not safe for customer check collections.",
        risk_note="Using this for checks would create the wrong accounting document type.",
    ),
}


def customer_payment_endpoint() -> Optional[IsbasiEndpointSpec]:
    """Return a verified customer payment endpoint if the Swagger matrix has one."""

    for spec in ISBASI_ENDPOINTS.values():
        if spec.creates_customer_payment:
            return spec
    return None


def payment_endpoint_verification() -> Dict[str, object]:
    """Explain whether customer check collection posting is available."""

    endpoint = customer_payment_endpoint()
    if endpoint:
        return {
            "verified": True,
            "endpoint": endpoint.path,
            "method": endpoint.method,
            "reason": "Swagger matrix contains a verified customer payment endpoint.",
        }

    return {
        "verified": False,
        "endpoint": None,
        "method": None,
        "reason": (
            "Swagger matrix contains firm, invoice and SMM endpoints, but no endpoint "
            "that explicitly creates customer check/collection payment transactions."
        ),
    }

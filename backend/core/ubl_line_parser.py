#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UBL InvoiceLine parser shared by invoice detail exports."""
import re
import unicodedata
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional


NAMESPACES = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
}


def normalize_text(value: Any) -> str:
    """Return a lowercase, accent-insensitive string for product matching."""
    if value is None:
        return ""

    text = str(value).strip().lower()
    text = text.translate(str.maketrans({"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


def text_or_empty(element: Optional[ET.Element]) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def find_text(parent: ET.Element, path: str) -> str:
    return text_or_empty(parent.find(path, NAMESPACES))


def decimal_or_none(value: Any) -> Optional[Decimal]:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def infer_vat_rate(line_amount: Optional[Decimal], tax_amount: Optional[Decimal]) -> Optional[Decimal]:
    if not line_amount or line_amount == 0 or tax_amount is None:
        return None
    return (tax_amount / line_amount) * Decimal("100")


def add_vat_to_unit_price(unit_price: Optional[Decimal], vat_rate: Optional[Decimal]) -> Optional[Decimal]:
    if unit_price is None:
        return None
    if vat_rate is None:
        return unit_price
    return unit_price * (Decimal("1") + (vat_rate / Decimal("100")))


def infer_bag_kg(line: Dict[str, Any]) -> Optional[int]:
    """Infer bag weight for gypsum products that are priced by ton."""
    product_text = normalize_text(
        " ".join(
            str(line.get(key) or "")
            for key in ("Ürün Kodu", "Ürün Adı", "Açıklama")
        )
    )
    compact = product_text.replace(" ", "").replace("-", "")

    if "saten" in product_text:
        return 25
    if "25kg" in compact:
        return 25
    if "35kg" in compact:
        return 35
    if (
        ("makine" in product_text or "makina" in product_text or "turbo" in product_text)
        and "siva" in product_text
        and "alci" in product_text
    ):
        return 35
    if "perlitli" in product_text and "siva" in product_text:
        return 35

    return None


def parse_invoice_lines(xml_content: Optional[str]) -> List[Dict[str, Any]]:
    """Parse UBL InvoiceLine rows into Turkish report column names."""
    if not xml_content:
        return []

    root = ET.fromstring(xml_content)
    lines = []

    for line in root.findall(".//cac:InvoiceLine", NAMESPACES):
        quantity = line.find("cbc:InvoicedQuantity", NAMESPACES)
        price_amount = line.find("cac:Price/cbc:PriceAmount", NAMESPACES)
        line_amount = line.find("cbc:LineExtensionAmount", NAMESPACES)
        tax_amount = line.find(".//cac:TaxSubtotal/cbc:TaxAmount", NAMESPACES)

        product_code = (
            find_text(line, "cac:Item/cac:SellersItemIdentification/cbc:ID")
            or find_text(line, "cac:Item/cac:BuyersItemIdentification/cbc:ID")
            or find_text(line, "cac:Item/cac:ManufacturersItemIdentification/cbc:ID")
        )

        parsed_line_amount = decimal_or_none(text_or_empty(line_amount))
        parsed_tax_amount = decimal_or_none(text_or_empty(tax_amount))
        parsed_vat_rate = decimal_or_none(find_text(line, ".//cac:TaxSubtotal/cac:TaxCategory/cbc:Percent"))
        if parsed_vat_rate is None:
            parsed_vat_rate = infer_vat_rate(parsed_line_amount, parsed_tax_amount)

        line_data = {
            "Satır No": find_text(line, "cbc:ID"),
            "Ürün Kodu": product_code,
            "Ürün Adı": find_text(line, "cac:Item/cbc:Name"),
            "Açıklama": find_text(line, "cac:Item/cbc:Description") or find_text(line, "cbc:Note"),
            "Miktar": decimal_or_none(text_or_empty(quantity)),
            "Birim": quantity.attrib.get("unitCode", "") if quantity is not None else "",
            "Birim Fiyat": decimal_or_none(text_or_empty(price_amount)),
            "Satır Tutarı": parsed_line_amount,
            "KDV Oranı": parsed_vat_rate,
            "KDV Tutarı": parsed_tax_amount,
            "Satır Para Birimi": (
                line_amount.attrib.get("currencyID", "")
                if line_amount is not None
                else price_amount.attrib.get("currencyID", "") if price_amount is not None else ""
            ),
        }
        line_data["KDV Dahil Birim Fiyat"] = add_vat_to_unit_price(
            line_data["Birim Fiyat"],
            line_data["KDV Oranı"],
        )
        line_data["Torba KG"] = infer_bag_kg(line_data)
        lines.append(line_data)

    return lines


def parse_outgoing_invoice_detail_lines(detail_payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse İşbaşı outgoing invoice detail JSON invoiceLines into report rows."""
    if not detail_payload:
        return []

    data = detail_payload.get("data", detail_payload) if isinstance(detail_payload, dict) else {}
    invoice_lines = data.get("invoiceLines") or []
    parsed_lines = []

    for line in invoice_lines:
        if not isinstance(line, dict):
            continue

        product = line.get("product") or {}
        unit = line.get("unit") or {}

        quantity = decimal_or_none(line.get("amount"))
        unit_price = decimal_or_none(line.get("price") or line.get("priceTL"))
        vat_rate = decimal_or_none(line.get("vatRate"))
        vat_amount = decimal_or_none(line.get("vatAmount") or line.get("vatAmountCalculated"))
        line_amount = (
            decimal_or_none(line.get("total"))
            or decimal_or_none(line.get("netTotal"))
            or decimal_or_none(line.get("taxableValue"))
            or decimal_or_none(line.get("totalTL"))
        )

        line_data = {
            "Satır No": line.get("lineNumber") or line.get("id") or "",
            "Ürün Kodu": product.get("code") or str(line.get("stockRef") or ""),
            "Ürün Adı": product.get("name") or line.get("description") or "",
            "Açıklama": line.get("description") or product.get("name2") or "",
            "Miktar": quantity,
            "Birim": unit.get("name") or unit.get("code") or "",
            "Birim Fiyat": unit_price,
            "Satır Tutarı": line_amount,
            "KDV Oranı": vat_rate,
            "KDV Tutarı": vat_amount,
            "Satır Para Birimi": line.get("currency") or data.get("currency") or "",
        }
        line_data["KDV Dahil Birim Fiyat"] = add_vat_to_unit_price(unit_price, vat_rate)
        line_data["Torba KG"] = infer_bag_kg(line_data)
        parsed_lines.append(line_data)

    return parsed_lines

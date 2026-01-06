#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML E-Fatura Dosyalarını Parse Edip Veritabanına Aktaran Script
"""

import xml.etree.ElementTree as ET
import base64
import sqlite3
import os
import sys
from datetime import datetime
import glob
from pathlib import Path
import traceback

# XML namespace'leri
NAMESPACES = {
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
    'inv': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2'
}

def parse_xml_invoice(xml_file):
    """XML fatura dosyasını parse eder ve önemli bilgileri çıkarır"""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        # Fatura bilgilerini çıkar
        invoice_data = {
            'source_file': os.path.basename(xml_file),
            'parse_date': datetime.now().isoformat()
        }
        
        # ID
        id_elem = root.find('.//cbc:ID', NAMESPACES)
        if id_elem is not None:
            invoice_data['invoice_id'] = id_elem.text
        
        # UUID
        uuid_elem = root.find('.//cbc:UUID', NAMESPACES)
        if uuid_elem is not None:
            invoice_data['uuid'] = uuid_elem.text
        
        # Fatura numarası
        invoice_num = root.find('.//cbc:ID', NAMESPACES)
        if invoice_num is not None:
            invoice_data['invoice_number'] = invoice_num.text
        
        # Tarih
        issue_date = root.find('.//cbc:IssueDate', NAMESPACES)
        if issue_date is not None:
            invoice_data['issue_date'] = issue_date.text
        
        # Toplam tutar
        payable_amount = root.find('.//cac:LegalMonetaryTotal/cbc:PayableAmount', NAMESPACES)
        if payable_amount is not None:
            invoice_data['total_amount'] = float(payable_amount.text)
            invoice_data['currency'] = payable_amount.get('currencyID', 'TRY')
        
        # Vergi matrahı
        taxable_amount = root.find('.//cac:LegalMonetaryTotal/cbc:TaxExclusiveAmount', NAMESPACES)
        if taxable_amount is not None:
            invoice_data['taxable_amount'] = float(taxable_amount.text)
        
        # Vergi tutarı
        tax_amount = root.find('.//cac:TaxTotal/cbc:TaxAmount', NAMESPACES)
        if tax_amount is not None:
            invoice_data['tax_amount'] = float(tax_amount.text)
        
        # Satıcı bilgileri
        supplier_name = root.find('.//cac:AccountingSupplierParty/cac:Party/cac:PartyName/cbc:Name', NAMESPACES)
        if supplier_name is not None:
            invoice_data['supplier_name'] = supplier_name.text
        
        supplier_vkn = root.find('.//cac:AccountingSupplierParty/cac:Party/cac:PartyIdentification/cbc:ID[@schemeID="VKN"]', NAMESPACES)
        if supplier_vkn is not None:
            invoice_data['supplier_vkn'] = supplier_vkn.text
        
        # Müşteri bilgileri
        customer_name = root.find('.//cac:AccountingCustomerParty/cac:Party/cac:PartyName/cbc:Name', NAMESPACES)
        if customer_name is not None:
            invoice_data['customer_name'] = customer_name.text
        
        customer_vkn = root.find('.//cac:AccountingCustomerParty/cac:Party/cac:PartyIdentification/cbc:ID[@schemeID="VKN"]', NAMESPACES)
        if customer_vkn is not None:
            invoice_data['customer_vkn'] = customer_vkn.text
        
        # Fatura açıklaması/notu
        note = root.find('.//cbc:Note', NAMESPACES)
        if note is not None and note.text:
            invoice_data['description'] = note.text.strip()
        
        # Attachment bilgileri - EmbeddedDocumentBinaryObject
        attachments = []
        for attachment in root.findall('.//cac:Attachment', NAMESPACES):
            embedded_doc = attachment.find('.//cbc:EmbeddedDocumentBinaryObject', NAMESPACES)
            if embedded_doc is not None:
                att_data = {
                    'filename': embedded_doc.get('filename', ''),
                    'mime_type': embedded_doc.get('mimeCode', ''),
                    'encoding': embedded_doc.get('encodingCode', ''),
                    'charset': embedded_doc.get('characterSetCode', ''),
                    'data': embedded_doc.text.strip() if embedded_doc.text else ''
                }
                
                # Base64 verisini decode et
                if att_data['encoding'].lower() == 'base64' and att_data['data']:
                    try:
                        decoded_data = base64.b64decode(att_data['data'])
                        att_data['decoded_size'] = len(decoded_data)
                        # İlk 100 karakteri sakla (pratiklik için)
                        att_data['decoded_preview'] = decoded_data[:200].decode('utf-8', errors='ignore')
                    except Exception as e:
                        att_data['decode_error'] = str(e)
                
                attachments.append(att_data)
        
        invoice_data['attachments'] = attachments
        
        # Fatura satırları
        invoice_lines = []
        for line in root.findall('.//cac:InvoiceLine', NAMESPACES):
            line_data = {}
            
            # Satır ID
            line_id = line.find('.//cbc:ID', NAMESPACES)
            if line_id is not None:
                line_data['line_id'] = line_id.text
            
            # Ürün/hizmet adı
            item_name = line.find('.//cac:Item/cbc:Name', NAMESPACES)
            if item_name is not None:
                line_data['item_name'] = item_name.text
            
            # Miktar
            quantity = line.find('.//cbc:InvoicedQuantity', NAMESPACES)
            if quantity is not None:
                line_data['quantity'] = float(quantity.text)
                line_data['unit'] = quantity.get('unitCode', '')
            
            # Birim fiyat
            price = line.find('.//cac:Price/cbc:PriceAmount', NAMESPACES)
            if price is not None:
                line_data['unit_price'] = float(price.text)
            
            # Satır toplamı
            line_total = line.find('.//cbc:LineExtensionAmount', NAMESPACES)
            if line_total is not None:
                line_data['line_total'] = float(line_total.text)
            
            invoice_lines.append(line_data)
        
        invoice_data['invoice_lines'] = invoice_lines
        
        # İrsaliye bilgileri (DespatchDocumentReference)
        despatch_documents = []
        for despatch in root.findall('.//cac:DespatchDocumentReference', NAMESPACES):
            despatch_data = {}
            
            # İrsaliye ID
            despatch_id = despatch.find('.//cbc:ID', NAMESPACES)
            if despatch_id is not None and despatch_id.text:
                full_id = despatch_id.text.strip()
                despatch_data['despatch_id_full'] = full_id
                
                # FULLBOARD için: F- + son 5 hane (örn: IRS2025000014704 -> F-14704)
                # Başındaki 0'ları kaldır (F-07128 -> F-7128)
                if full_id.startswith('IRS') and len(full_id) > 8:
                    # F- öneki + son 5 hane (başındaki 0'lar kaldırılır)
                    number = full_id[-5:].lstrip('0') or '0'  # Tüm 0'lar silinirse '0' kalsın
                    despatch_data['despatch_id_short'] = 'F-' + number
                else:
                    # IRS ile başlamıyorsa veya çok kısaysa, F- ekle
                    number = (full_id[-5:] if len(full_id) >= 5 else full_id).lstrip('0') or '0'
                    despatch_data['despatch_id_short'] = 'F-' + number
            
            # İrsaliye tarihi
            despatch_date = despatch.find('.//cbc:IssueDate', NAMESPACES)
            if despatch_date is not None:
                despatch_data['issue_date'] = despatch_date.text
            
            # Açıklama
            description = despatch.find('.//cbc:DocumentDescription', NAMESPACES)
            if description is not None and description.text:
                despatch_data['description'] = description.text.strip()
            
            if despatch_data.get('despatch_id_full'):
                despatch_documents.append(despatch_data)
        
        invoice_data['despatch_documents'] = despatch_documents
        
        return invoice_data
        
    except Exception as e:
        print(f"Hata oluştu ({xml_file}): {str(e)}")
        return None

def create_database(db_path='efatura_fullboard.db'):
    """Veritabanı şemasını oluşturur"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Ana fatura tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            parse_date TEXT NOT NULL,
            invoice_id TEXT,
            uuid TEXT,
            invoice_number TEXT,
            issue_date TEXT,
            total_amount REAL,
            currency TEXT,
            taxable_amount REAL,
            tax_amount REAL,
            supplier_name TEXT,
            supplier_vkn TEXT,
            customer_name TEXT,
            customer_vkn TEXT,
            description TEXT,
            invoice_type TEXT DEFAULT 'PURCHASE',
            payment_status TEXT DEFAULT 'UNPAID',
            paid_amount REAL DEFAULT 0,
            remaining_amount REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Attachment tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            filename TEXT,
            mime_type TEXT,
            encoding TEXT,
            charset TEXT,
            data_base64 TEXT,
            decoded_size INTEGER,
            decoded_preview TEXT,
            decode_error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices (id)
        )
    ''')
    
    # Fatura satırları tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            line_id TEXT,
            item_name TEXT,
            quantity REAL,
            unit TEXT,
            unit_price REAL,
            line_total REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices (id)
        )
    ''')
    
    # İrsaliye tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS despatch_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            despatch_id_full TEXT NOT NULL,
            despatch_id_short TEXT NOT NULL,
            issue_date TEXT,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices (id)
        )
    ''')
    
    conn.commit()
    return conn

def insert_invoice_data(conn, invoice_data):
    """Fatura verilerini veritabanına ekler"""
    cursor = conn.cursor()
    
    # Ana fatura kaydı
    total_amt = invoice_data.get('total_amount', 0)
    cursor.execute('''
        INSERT INTO invoices (
            source_file, parse_date, invoice_id, uuid, invoice_number,
            issue_date, total_amount, currency, taxable_amount, tax_amount,
            supplier_name, supplier_vkn, customer_name, customer_vkn, description,
            invoice_type, payment_status, paid_amount, remaining_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        invoice_data.get('source_file'),
        invoice_data.get('parse_date'),
        invoice_data.get('invoice_id'),
        invoice_data.get('uuid'),
        invoice_data.get('invoice_number'),
        invoice_data.get('issue_date'),
        total_amt,
        invoice_data.get('currency'),
        invoice_data.get('taxable_amount'),
        invoice_data.get('tax_amount'),
        invoice_data.get('supplier_name'),
        invoice_data.get('supplier_vkn'),
        invoice_data.get('customer_name'),
        invoice_data.get('customer_vkn'),
        invoice_data.get('description'),
        'PURCHASE',  # FULLBOARD faturaları = alış faturası
        'UNPAID',  # Başlangıç durumu
        0,  # Henüz ödeme yok
        total_amt  # Kalan tutar = toplam tutar
    ))
    
    invoice_db_id = cursor.lastrowid
    
    # Attachment kayıtları
    for att in invoice_data.get('attachments', []):
        cursor.execute('''
            INSERT INTO attachments (
                invoice_id, filename, mime_type, encoding, charset,
                data_base64, decoded_size, decoded_preview, decode_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            invoice_db_id,
            att.get('filename'),
            att.get('mime_type'),
            att.get('encoding'),
            att.get('charset'),
            att.get('data'),
            att.get('decoded_size'),
            att.get('decoded_preview'),
            att.get('decode_error')
        ))
    
    # Fatura satırları
    for line in invoice_data.get('invoice_lines', []):
        cursor.execute('''
            INSERT INTO invoice_lines (
                invoice_id, line_id, item_name, quantity, unit,
                unit_price, line_total
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            invoice_db_id,
            line.get('line_id'),
            line.get('item_name'),
            line.get('quantity'),
            line.get('unit'),
            line.get('unit_price'),
            line.get('line_total')
        ))
    
    # İrsaliye kayıtları
    for despatch in invoice_data.get('despatch_documents', []):
        cursor.execute('''
            INSERT INTO despatch_documents (
                invoice_id, despatch_id_full, despatch_id_short,
                issue_date, description
            ) VALUES (?, ?, ?, ?, ?)
        ''', (
            invoice_db_id,
            despatch.get('despatch_id_full'),
            despatch.get('despatch_id_short'),
            despatch.get('issue_date'),
            despatch.get('description')
        ))
    
    conn.commit()
    return invoice_db_id

def main():
    """Ana işlem fonksiyonu"""
    print("=" * 70)
    print("E-Fatura XML Dosyaları Parse ve Veritabanı Aktarım Aracı - FULLBOARD")
    print("=" * 70)
    print()
    
    # Proje kök dizinine git
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.chdir(project_root)

    # Optional: enable `import src...` when running as a script
    # TODO: Replace this sys.path hack with proper packaging/entrypoints.
    sys.path.insert(0, str(Path(project_root)))
    
    # XML dosyalarını bul
    xml_files = glob.glob('data/xml/fullboard/*.xml')
    if not xml_files:
        print("❌ Hiç XML dosyası bulunamadı!")
        print(f"   Beklenen konum: {os.path.join(project_root, 'data/xml/fullboard/')}")
        return
    
    print(f"✓ {len(xml_files)} adet XML dosyası bulundu:")
    for f in xml_files:
        print(f"  - {os.path.basename(f)}")
    print()
    
    # Veritabanını oluştur
    db_path = 'data/db/fullboard.db'
    print(f"📊 Veritabanı oluşturuluyor: {db_path}")
    conn = create_database(db_path)
    print("✓ Veritabanı hazır")
    print()
    
    # Her XML dosyasını işle
    processed_count = 0
    error_count = 0
    
    for xml_file in xml_files:
        print(f"⚙️  İşleniyor: {xml_file}")
        invoice_data = parse_xml_invoice(xml_file)
        
        if invoice_data:
            try:
                invoice_db_id = insert_invoice_data(conn, invoice_data)
                print(f"   ✓ Veritabanına eklendi (ID: {invoice_db_id})")
                print(f"   - Fatura No: {invoice_data.get('invoice_number', 'N/A')}")
                print(f"   - Tarih: {invoice_data.get('issue_date', 'N/A')}")
                print(f"   - Toplam: {invoice_data.get('total_amount', 0):.2f} {invoice_data.get('currency', 'TRY')}")
                print(f"   - Satıcı: {invoice_data.get('supplier_name', 'N/A')}")
                print(f"   - Müşteri: {invoice_data.get('customer_name', 'N/A')}")
                print(f"   - Attachment sayısı: {len(invoice_data.get('attachments', []))}")
                print(f"   - Satır sayısı: {len(invoice_data.get('invoice_lines', []))}")
                print(f"   - İrsaliye sayısı: {len(invoice_data.get('despatch_documents', []))}")
                processed_count += 1

                # Parallel Postgres write path (does not affect SQLite/Excel behavior)
                try:
                    from src.db.pg_writer import get_connection, is_pg_enabled, write_invoice_with_equal_split_allocations

                    if is_pg_enabled():
                        dispatch_items = [
                            (d.get("despatch_id_short"), d.get("despatch_id_full"))
                            for d in invoice_data.get("despatch_documents", [])
                            if d.get("despatch_id_short")
                        ]
                        with get_connection() as pg_conn:
                            write_invoice_with_equal_split_allocations(
                                pg_conn,
                                source="XML_FULLBOARD",
                                direction="IN",
                                invoice_no=invoice_data.get("invoice_number") or invoice_data.get("invoice_id") or "",
                                total_amount=invoice_data.get("total_amount", 0),
                                currency=invoice_data.get("currency", "TRY") or "TRY",
                                description_raw=invoice_data.get("description"),
                                description_clean=invoice_data.get("description"),
                                external_id=None,  # XML: keep NULL to avoid uq_invoice_source_external collisions
                                source_file=invoice_data.get("source_file"),
                                issue_date=invoice_data.get("issue_date"),
                                raw_payload=None,
                                dispatch_codes_and_tokens=dispatch_items,
                            )
                except Exception as e:
                    # Never break the existing flow; Postgres is additive/parallel only.
                    print(f"⚠️ Postgres write failed (FULLBOARD IN): {e}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)
            except Exception as e:
                print(f"   ❌ Veritabanına eklenirken hata: {str(e)}")
                error_count += 1
        else:
            error_count += 1
        print()
    
    conn.close()
    
    # Özet
    print("=" * 70)
    print("İŞLEM TAMAMLANDI")
    print("=" * 70)
    print(f"✓ Başarılı: {processed_count} fatura")
    print(f"❌ Hatalı: {error_count} fatura")
    print(f"📊 Veritabanı: {db_path}")
    print()
    
    # Veritabanı özeti
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM invoices")
    invoice_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM attachments")
    attachment_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM invoice_lines")
    line_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM despatch_documents")
    despatch_count = cursor.fetchone()[0]
    
    print("Veritabanı İçeriği:")
    print(f"  - Fatura kayıtları: {invoice_count}")
    print(f"  - Attachment kayıtları: {attachment_count}")
    print(f"  - Satır kayıtları: {line_count}")
    print(f"  - İrsaliye kayıtları: {despatch_count}")
    
    conn.close()

if __name__ == '__main__':
    main()


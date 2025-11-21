#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Basit E-Fatura Web Dashboard
Hiçbir dış modüle bağımlı değil
"""

from flask import Flask, render_template_string
import sqlite3
import os

app = Flask(__name__)

# HTML Template (tek dosyada)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>E-Fatura Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        h1 {
            color: white;
            text-align: center;
            font-size: 3em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .subtitle {
            color: rgba(255,255,255,0.9);
            text-align: center;
            font-size: 1.3em;
            margin-bottom: 40px;
        }
        
        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .kpi-card {
            background: white;
            border-radius: 15px;
            padding: 30px;
            text-align: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            transition: transform 0.3s;
        }
        
        .kpi-card:hover {
            transform: translateY(-10px);
        }
        
        .kpi-label {
            color: #666;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }
        
        .kpi-value {
            color: #667eea;
            font-size: 2.8em;
            font-weight: bold;
        }
        
        .section {
            background: white;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        
        .section h2 {
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.8em;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }
        
        td {
            padding: 15px;
            border-bottom: 1px solid #eee;
        }
        
        tr:hover {
            background: #f8f9fa;
        }
        
        .badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
        }
        
        .badge-A {
            background: #ffe0b2;
            color: #e65100;
        }
        
        .badge-F {
            background: #e1bee7;
            color: #6a1b9a;
        }
        
        .badge-API {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .amount {
            font-weight: 600;
            color: #06d6a0;
        }
        
        .footer {
            text-align: center;
            color: white;
            margin-top: 40px;
            padding: 20px;
            opacity: 0.9;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 E-Fatura Dashboard</h1>
        <p class="subtitle">Finansal Analiz ve Raporlama Sistemi</p>
        
        <!-- KPI Cards - Tüm Veriler (Birleşik) -->
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">📊 Toplam Fatura</div>
                <div class="kpi-value">{{ invoice_count }}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">💰 Toplam Tutar</div>
                <div class="kpi-value">{{ total_amount }}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Toplam KDV</div>
                <div class="kpi-value">{{ total_tax }}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">📦 İrsaliye</div>
                <div class="kpi-value">{{ despatch_count }}</div>
            </div>
        </div>
        
        <!-- Firma Bazlı KPI Cards -->
        <div class="kpi-grid" style="margin-top: 20px;">
            <div class="kpi-card" style="background: #ffe0b2;">
                <div class="kpi-label" style="color: #e65100;">🏢 AK GİPS</div>
                <div class="kpi-value" style="color: #e65100;">{{ ak_count }}</div>
            </div>
            <div class="kpi-card" style="background: #e1bee7;">
                <div class="kpi-label" style="color: #6a1b9a;">🏢 FULLBOARD</div>
                <div class="kpi-value" style="color: #6a1b9a;">{{ fb_count }}</div>
            </div>
            <div class="kpi-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                <div class="kpi-label" style="color: white;">🌐 API Verileri</div>
                <div class="kpi-value" style="color: white;">{{ api_count }}</div>
            </div>
            <div class="kpi-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
                <div class="kpi-label" style="color: white;">✅ Aktif Kaynak</div>
                <div class="kpi-value" style="color: white; font-size: 1.5em;">3</div>
            </div>
        </div>
        
        <!-- Birleşik Fatura Tablosu -->
        <div class="section">
            <h2>📋 Tüm Faturalar (XML + API Birleşik)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Kaynak</th>
                        <th>Fatura No</th>
                        <th>Tarih</th>
                        <th>Firma/Tedarikçi</th>
                        <th>Tutar</th>
                    </tr>
                </thead>
                <tbody>
                    {% for inv in invoices %}
                    <tr>
                        <td><span class="badge badge-{{ inv.firma }}">{{ inv.firma }}</span></td>
                        <td>{{ inv.invoice_number }}</td>
                        <td>{{ inv.date }}</td>
                        <td>{{ inv.supplier }}</td>
                        <td class="amount">{{ inv.amount }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>✨ E-Fatura Web Dashboard v2.1 (Birleşik Sistem) | {{ db_info }}</p>
            <p style="font-size: 0.9em; margin-top: 5px;">
                📊 A: AK GİPS (XML) | F: FULLBOARD (XML) | API: İşbaşı API
            </p>
        </div>
    </div>
</body>
</html>
"""

def format_currency(amount):
    """Para birimini formatla"""
    try:
        return f"{amount:,.2f} TRY".replace(',', '_').replace('.', ',').replace('_', '.')
    except:
        return "0,00 TRY"

def format_date(date_str):
    """Tarihi formatla"""
    try:
        from datetime import datetime
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%d.%m.%Y')
    except:
        return date_str

def get_data():
    """Birleşik veritabanından verileri al (XML + API)"""
    
    # Proje kök dizini - chdir kullanma!
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    # Veritabanı bağlantısı - önce birleşik, sonra tekil (tam path kullan)
    db_path = os.path.join(project_root, 'data/db/birlesik.db')
    if not os.path.exists(db_path):
        db_path = os.path.join(project_root, 'data/db/akgips.db')
    
    if not os.path.exists(db_path):
        return {
            'invoice_count': 0,
            'total_amount': '0,00 TRY',
            'total_tax': '0,00 TRY',
            'despatch_count': 0,
            'invoices': [],
            'ak_count': 0,
            'fb_count': 0,
            'api_count': 0,
            'has_api_data': False,
            'db_info': 'Veritabanı bulunamadı'
        }
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # KPI verileri
    cursor.execute("""
        SELECT 
            COUNT(*) as invoice_count,
            COALESCE(SUM(total_amount), 0) as total_amount,
            COALESCE(SUM(tax_amount), 0) as total_tax
        FROM invoices
    """)
    kpi = cursor.fetchone()
    
    # İrsaliye sayısı
    cursor.execute("SELECT COUNT(*) as count FROM despatch_documents")
    desp = cursor.fetchone()
    
    # Firma bazlı sayılar
    cursor.execute("SELECT COUNT(*) FROM invoices WHERE firma_kodu = 'A'")
    ak_count = cursor.fetchone()[0] if 'firma_kodu' in [desc[0] for desc in cursor.execute("PRAGMA table_info(invoices)")] else 0
    
    cursor.execute("SELECT COUNT(*) FROM invoices WHERE firma_kodu = 'F'")
    fb_count = cursor.fetchone()[0] if 'firma_kodu' in [desc[0] for desc in cursor.execute("PRAGMA table_info(invoices)")] else 0
    
    cursor.execute("SELECT COUNT(*) FROM invoices WHERE firma_kodu = 'API'")
    api_count = cursor.fetchone()[0] if 'firma_kodu' in [desc[0] for desc in cursor.execute("PRAGMA table_info(invoices)")] else 0
    
    # Fatura listesi
    if 'firma_kodu' in [desc[0] for desc in cursor.execute("PRAGMA table_info(invoices)")]:
        # Birleşik DB - firma_kodu ile
        cursor.execute("""
            SELECT 
                firma_kodu, invoice_number, issue_date, 
                COALESCE(supplier_name, customer_name) as firm_name, 
                total_amount
            FROM invoices
            ORDER BY issue_date DESC
            LIMIT 50
        """)
    else:
        # Tekil DB
        cursor.execute("""
            SELECT 
                invoice_number, issue_date, 
                supplier_name, total_amount
            FROM invoices
            ORDER BY issue_date DESC
            LIMIT 50
        """)
    
    invoices_raw = cursor.fetchall()
    
    # Fatura listesini formatla
    invoices = []
    for inv in invoices_raw:
        inv_dict = dict(inv)
        invoices.append({
            'firma': inv_dict.get('firma_kodu', '-'),
            'invoice_number': inv_dict.get('invoice_number', ''),
            'date': format_date(inv_dict.get('issue_date', '')),
            'supplier': inv_dict.get('firm_name', inv_dict.get('supplier_name', ''))[:40],
            'amount': format_currency(inv_dict.get('total_amount', 0))
        })
    
    conn.close()
    
    return {
        'invoice_count': kpi['invoice_count'],
        'total_amount': format_currency(kpi['total_amount']),
        'total_tax': format_currency(kpi['total_tax']),
        'despatch_count': desp['count'],
        'invoices': invoices,
        'ak_count': ak_count,
        'fb_count': fb_count,
        'api_count': api_count,
        'has_api_data': api_count > 0,
        'db_info': f'Birleşik DB: {os.path.basename(db_path)}'
    }

@app.route('/')
def index():
    """Ana sayfa"""
    data = get_data()
    return render_template_string(HTML_TEMPLATE, **data)

if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 E-FATURA WEB DASHBOARD")
    print("="*70)
    print("\n📊 Dashboard açılıyor: http://localhost:8080")
    print("\n💡 Tarayıcınızda yukarıdaki adresi açın")
    print("\n⏹️  Durdurmak için: Ctrl+C")
    print("="*70 + "\n")
    
    app.run(debug=False, port=8080, use_reloader=False)


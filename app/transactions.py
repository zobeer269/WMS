from flask import Blueprint, render_template, g # g موجود تلقائياً في سياق التطبيق
import sqlite3
from .auth import login_required, admin_required # استيراد المزخرفات
from .__init__ import get_db_connection # استيراد دالة الاتصال بقاعدة البيانات

# إنشاء المخطط الأزرق لقسم الحركات
transactions_bp = Blueprint('transactions', __name__, url_prefix='/transactions')

# -------------------- دوال مساعدة (لتسجيل الحركات) --------------------

def log_transaction(product_id, user_id, action, details):
    """
    تسجيل حركة في جدول الحركات.
    يمكن استدعاء هذه الدالة من أي مكان في التطبيق لتسجيل العمليات.
    """
    conn = get_db_connection()
    conn.execute('INSERT INTO transactions (product_id, user_id, action, details) VALUES (?, ?, ?, ?)',
                 (product_id, user_id, action, details))
    conn.commit()
    conn.close()

# -------------------- مسارات سجل الحركات --------------------

@transactions_bp.route('/')
@login_required # سجل الحركات متاح لكل المستخدمين المسجلين
def list_transactions():
    """عرض سجل جميع الحركات."""
    conn = get_db_connection()
    transactions = conn.execute('''
        SELECT t.*, p.product_code, u.username, r.name as rack_name, b.name as bin_name, c.name as category_name
        FROM transactions t
        LEFT JOIN products p ON t.product_id = p.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN racks r ON p.rack_id = r.id
        LEFT JOIN bins b ON p.bin_id = b.id
        LEFT JOIN categories c ON p.category_id = c.id
        ORDER BY t.timestamp DESC
    ''').fetchall()
    conn.close()
    return render_template('list_transactions.html', transactions=transactions)
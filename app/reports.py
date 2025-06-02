from flask import Blueprint, render_template, request, flash, g, jsonify
import sqlite3
import json
from datetime import datetime, timedelta
from .__init__ import get_db_connection, login_required
from config import Config

reports_bp = Blueprint('main', __name__)

# -------------------- مسارات لوحة التحكم والتقارير --------------------

@reports_bp.route('/')
@login_required
def index():
    conn = get_db_connection()
    
    total_products = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    total_quantity = conn.execute('SELECT SUM(quantity) FROM products').fetchone()[0] or 0
    
    low_stock_threshold = Config.LOW_STOCK_THRESHOLD
    low_stock_products = conn.execute('SELECT p.*, c.name as category_name, r.name as rack_name, b.name as bin_name FROM products p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id WHERE p.quantity <= ? ORDER BY p.product_code', (low_stock_threshold,)).fetchall()

    # بيانات للرسوم البيانية (توزيع الكميات حسب الفئة)
    category_quantities_data = conn.execute('SELECT c.name, SUM(p.quantity) FROM products p JOIN categories c ON p.category_id = c.id GROUP BY c.name').fetchall()
    category_labels = [row[0] for row in category_quantities_data]
    category_data = [row[1] for row in category_quantities_data]

    # بيانات للرسوم البيانية (أكثر المنتجات كمية)
    top_products_by_quantity_data = conn.execute('SELECT product_code, quantity FROM products ORDER BY quantity DESC LIMIT 5').fetchall()
    top_product_labels = [row[0] for row in top_products_by_quantity_data]
    top_product_data = [row[1] for row in top_products_by_quantity_data]

    # مؤشرات الأداء الرئيسية (KPIs)
    
    # حساب معدل دوران المخزون (بسيط)
    try:
        # نحتاج إلى مجموع الكميات الخارجة (المباعة/المستخدمة) خلال فترة
        # ومجموع الكميات الداخلة (المشتراة/المستلمة) خلال نفس الفترة
        # هنا سنبسطها إلى مجموع الكميات الخارجة/الداخلة في آخر 30 يوماً
        # معدل الدوران = (مجموع الكميات الخارجة / متوسط المخزون)
        # متوسط المخزون يمكن تقديره بالكمية الحالية أو بمتوسط الكميات على مدار فترة
        
        # مجموع الكميات الخارجة في آخر 30 يومًا
        outbound_transactions_data = conn.execute('''
            SELECT SUM(CAST(SUBSTR(t.details, INSTR(t.details, ' الكمية الجديدة: ') + LENGTH(' الكمية الجديدة: '), 
                              INSTR(t.details || '.', '. السبب:') - (INSTR(t.details, ' الكمية الجديدة: ') + LENGTH(' الكمية الجديدة: ')))) AS INTEGER) as quantity_diff
            FROM transactions t
            WHERE t.action LIKE '%issue%' OR t.action LIKE '%decrease%' OR t.action LIKE '%cycle_count%' OR t.action LIKE '%delete%'
            AND t.timestamp >= strftime('%Y-%m-%d %H:%M:%S', date('now', '-30 days'))
        ''').fetchone()
        # إذا لم يكن هناك فرق واضح في الكمية من حقل details، يمكن تعديل log_transaction لحفظ الكمية المتغيرة
        
        # بما أن details يسجل الكمية الجديدة، يجب أن نحسب الفرق من البيانات المحفوظة.
        # للحساب الدقيق لمعدل الدوران، نحتاج إلى تاريخ إضافة المنتج وقيمته، وهذا يتجاوز نطاق هذا المشروع.
        # لتبسيط الأمر، سنستخدم تقديراً.
        
        inventory_turnover_rate = "غير متاح" # يتطلب منطقاً أكثر تعقيداً ودقة
    except Exception:
        inventory_turnover_rate = "غير متاح"


    stock_accuracy = "غير متاح" # يتطلب بيانات جرد فعلية ومسجلة لمقارنتها
    avg_inventory_age = "غير متاح" # يتطلب تاريخ إضافة لكل منتج وتتبع السحب

    # بيانات للمنتجات الأكثر حركة (إضافة وإخراج) - خلال آخر 30 يومًا كمثال
    product_movement_data = conn.execute('''
        SELECT p.product_code, 
               SUM(CASE WHEN t.action IN ('receive_product', 'add_product', 'increase_quantity', 'import_add_product') THEN 1 ELSE 0 END) as inbound_count,
               SUM(CASE WHEN t.action IN ('issue_product', 'decrease_quantity', 'delete_product', 'cycle_count', 'import_update_product') THEN 1 ELSE 0 END) as outbound_count
        FROM transactions t
        JOIN products p ON t.product_id = p.id
        WHERE t.timestamp >= strftime('%Y-%m-%d %H:%M:%S', date('now', '-30 days'))
        GROUP BY p.product_code
        ORDER BY (inbound_count + outbound_count) DESC
        LIMIT 10
    ''').fetchall()
    
    movement_labels = [row['product_code'] for row in product_movement_data]
    inbound_data = [row['inbound_count'] for row in product_movement_data]
    outbound_data = [row['outbound_count'] for row in product_movement_data]

    # تحليل المخزون الميت (Dead Stock) - المنتجات التي لم تتحرك منذ فترة طويلة
    dead_stock_threshold_days = 90 
    dead_stock_products = conn.execute(f'''
        SELECT p.product_code, p.quantity, c.name as category_name, MAX(t.timestamp) as last_movement_date
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN transactions t ON p.id = t.product_id
        GROUP BY p.id, p.product_code, p.quantity, c.name
        HAVING MAX(t.timestamp) < strftime('%Y-%m-%d %H:%M:%S', date('now', '-{dead_stock_threshold_days} days'))
        OR MAX(t.timestamp) IS NULL 
        ORDER BY p.product_code
    ''').fetchall()

    conn.close()
    return render_template('index.html',
                           total_products=total_products,
                           total_quantity=total_quantity,
                           low_stock_products=low_stock_products,
                           low_stock_threshold=low_stock_threshold,
                           category_labels=category_labels,
                           category_data=category_data,
                           top_product_labels=top_product_labels,
                           top_product_data=top_product_data,
                           movement_labels=movement_labels,
                           inbound_data=inbound_data,
                           outbound_data=outbound_data,
                           dead_stock_products=dead_stock_products,
                           dead_stock_threshold_days=dead_stock_threshold_days,
                           stock_accuracy=stock_accuracy,
                           avg_inventory_age=avg_inventory_age,
                           inventory_turnover_rate=inventory_turnover_rate)

@reports_bp.route('/low_stock_report')
@login_required
def low_stock_report():
    conn = get_db_connection()
    low_stock_threshold = Config.LOW_STOCK_THRESHOLD
    low_stock_products = conn.execute('SELECT p.*, c.name as category_name, r.name as rack_name, b.name as bin_name FROM products p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id WHERE p.quantity <= ? ORDER BY p.product_code', (low_stock_threshold,)).fetchall()
    conn.close()
    return render_template('low_stock_report.html', low_stock_products=low_stock_products, low_stock_threshold=low_stock_threshold)

@reports_bp.route('/advanced_reports', methods=('GET', 'POST'))
@login_required
def advanced_reports():
    conn = get_db_connection()
    categories = conn.execute('SELECT id, name FROM categories ORDER BY name').fetchall()
    racks = conn.execute('SELECT id, name FROM racks ORDER BY name').fetchall()
    all_products = conn.execute('SELECT id, product_code FROM products ORDER BY product_code').fetchall()

    filtered_products = []
    report_title = "جميع المنتجات"
    
    selected_category_id = request.form.get('category_id', '')
    selected_rack_id = request.form.get('rack_id', '')
    selected_product_id = request.form.get('product_id', '')
    min_quantity = request.form.get('min_quantity', '')
    max_quantity = request.form.get('max_quantity', '')
    start_date = request.form.get('start_date', '')
    end_date = request.form.get('end_date', '')
    report_type = request.form.get('report_type', 'filtered_products') # نوع التقرير الافتراضي

    query_base_select = """
        SELECT p.*, c.name as category_name, r.name as rack_name, b.name as bin_name
    """
    query_base_from = """
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN racks r ON p.rack_id = r.id
        LEFT JOIN bins b ON p.bin_id = b.id
    """
    where_clauses = ["1=1"]
    params = []

    if request.method == 'POST':
        if selected_category_id:
            where_clauses.append("p.category_id = ?")
            params.append(selected_category_id)
            selected_category = conn.execute('SELECT name FROM categories WHERE id = ?', (selected_category_id,)).fetchone()
            report_title += f" (الفئة: {selected_category['name']})"

        if selected_rack_id:
            where_clauses.append("p.rack_id = ?")
            params.append(selected_rack_id)
            selected_rack = conn.execute('SELECT name FROM racks WHERE id = ?', (selected_rack_id,)).fetchone()
            report_title += f" (الراك: {selected_rack['name']})"

        if selected_product_id:
            where_clauses.append("p.id = ?")
            params.append(selected_product_id)
            selected_prod_code = conn.execute('SELECT product_code FROM products WHERE id = ?', (selected_product_id,)).fetchone()['product_code']
            report_title += f" (المنتج: {selected_prod_code})"

        if min_quantity and min_quantity.isdigit():
            min_quantity_val = int(min_quantity)
            where_clauses.append("p.quantity >= ?")
            params.append(min_quantity_val)
            report_title += f" (كمية >= {min_quantity_val})"
        
        if max_quantity and max_quantity.isdigit():
            max_quantity_val = int(max_quantity)
            where_clauses.append("p.quantity <= ?")
            params.append(max_quantity_val)
            report_title += f" (كمية <= {max_quantity_val})"
        
        # بناء الاستعلام حسب نوع التقرير
        if report_type == 'filtered_products':
            query = f"{query_base_select} {query_base_from} WHERE {' AND '.join(where_clauses)} ORDER BY p.product_code"
            filtered_products = conn.execute(query, tuple(params)).fetchall()
            report_title = "المنتجات المفلترة"

        elif report_type == 'most_moved_products':
            select_clause = """
                SELECT p.product_code, 
                       SUM(CASE WHEN t.action IN ('receive_product', 'add_product', 'increase_quantity', 'import_add_product') THEN 1 ELSE 0 END) as inbound_count,
                       SUM(CASE WHEN t.action IN ('issue_product', 'decrease_quantity', 'delete_product', 'cycle_count', 'import_update_product') THEN 1 ELSE 0 END) as outbound_count,
                       p.quantity, c.name as category_name, r.name as rack_name, b.name as bin_name
            """
            join_transactions = """JOIN transactions t ON p.id = t.product_id"""
            
            movement_where_clauses = list(where_clauses) # ابدأ بنفس فلاتر المنتجات
            movement_params = list(params)

            if start_date:
                movement_where_clauses.append("t.timestamp >= ?")
                movement_params.append(start_date + " 00:00:00")
            if end_date:
                movement_where_clauses.append("t.timestamp <= ?")
                movement_params.append(end_date + " 23:59:59")

            group_by_clause = """
                GROUP BY p.id, p.product_code, p.quantity, c.name, r.name, b.name
            """
            order_clause = "ORDER BY (inbound_count + outbound_count) DESC LIMIT 50" # يمكن زيادة الحد

            query = f"{select_clause} {query_base_from} {join_transactions} WHERE {' AND '.join(movement_where_clauses)} {group_by_clause} {order_clause}"
            filtered_products = conn.execute(query, tuple(movement_params)).fetchall() # استخدم movement_params

            report_title = "المنتجات الأكثر حركة"

        elif report_type == 'dead_stock':
            dead_stock_threshold_days_param = request.form.get('dead_stock_days_filter', '90').strip()
            if not dead_stock_threshold_days_param.isdigit():
                dead_stock_threshold_days_param = 90
            dead_stock_threshold_days_param = int(dead_stock_threshold_days_param)

            select_clause = """
                SELECT p.product_code, p.quantity, c.name as category_name, r.name as rack_name, b.name as bin_name, MAX(t.timestamp) as last_movement_date
            """
            join_transactions = """LEFT JOIN transactions t ON p.id = t.product_id"""
            group_by_clause = """
                GROUP BY p.id, p.product_code, p.quantity, c.name, r.name, b.name
            """
            having_clause = f"""
                HAVING MAX(t.timestamp) < strftime('%Y-%m-%d %H:%M:%S', date('now', '-{dead_stock_threshold_days_param} days'))
                OR MAX(t.timestamp) IS NULL
            """
            order_clause = "ORDER BY p.product_code"
            
            # هنا يجب دمج فلاتر المنتجات العادية مع المخزون الميت
            final_where_clauses = list(where_clauses) # ابدأ بفلاتر المنتجات الأساسية
            final_params = list(params)

            query = f"{select_clause} {query_base_from} {join_transactions} WHERE {' AND '.join(final_where_clauses)} {group_by_clause} {having_clause} {order_clause}"
            filtered_products = conn.execute(query, tuple(final_params)).fetchall()

            report_title = f"منتجات المخزون الميت (لم تتحرك منذ {dead_stock_threshold_days_param} يومًا)"
        
        flash(f'تم العثور على {len(filtered_products)} نتيجة للتقرير.', 'success')


    conn.close()
    return render_template('advanced_reports.html', 
                           categories=categories, 
                           racks=racks, 
                           all_products=all_products, 
                           filtered_products=filtered_products,
                           report_title=report_title,
                           selected_category_id=selected_category_id, 
                           selected_rack_id=selected_rack_id,
                           selected_product_id=selected_product_id,
                           min_quantity=min_quantity,
                           max_quantity=max_quantity,
                           start_date=start_date, 
                           end_date=end_date,
                           report_type=report_type)

@reports_bp.route('/product_audit_trail')
@login_required
def product_audit_trail():
    """صفحة لعرض سجل تدقيق المنتجات."""
    conn = get_db_connection()
    audit_records = conn.execute('''
        SELECT ph.*, p.product_code, u.username 
        FROM product_history ph
        LEFT JOIN products p ON ph.product_id = p.id
        LEFT JOIN users u ON ph.user_id = u.id
        ORDER BY ph.timestamp DESC
    ''').fetchall()
    conn.close()
    
    processed_records = []
    for record in audit_records:
        rec_dict = dict(record)
        try:
            rec_dict['old_data_parsed'] = json.loads(record['old_data']) if record['old_data'] else None
        except (json.JSONDecodeError, TypeError):
            rec_dict['old_data_parsed'] = {'error': 'Invalid JSON'}
        try:
            rec_dict['new_data_parsed'] = json.loads(record['new_data']) if record['new_data'] else None
        except (json.JSONDecodeError, TypeError):
            rec_dict['new_data_parsed'] = {'error': 'Invalid JSON'}
        processed_records.append(rec_dict)

    return render_template('product_audit_trail.html', audit_records=processed_records)


@reports_bp.route('/product_audit_trail/<int:product_id>')
@login_required
def product_audit_trail_by_product(product_id):
    """صفحة لعرض سجل تدقيق منتج معين."""
    conn = get_db_connection()
    product_info = conn.execute('SELECT product_code FROM products WHERE id = ?', (product_id,)).fetchone()
    if not product_info:
        flash('المنتج غير موجود.', 'error')
        conn.close()
        return redirect(url_for('main.product_audit_trail'))

    audit_records = conn.execute('''
        SELECT ph.*, p.product_code, u.username 
        FROM product_history ph
        LEFT JOIN products p ON ph.product_id = p.id
        LEFT JOIN users u ON ph.user_id = u.id
        WHERE ph.product_id = ?
        ORDER BY ph.timestamp DESC
    ''', (product_id,)).fetchall()
    conn.close()
    
    processed_records = []
    for record in audit_records:
        rec_dict = dict(record)
        try:
            rec_dict['old_data_parsed'] = json.loads(record['old_data']) if record['old_data'] else None
        except (json.JSONDecodeError, TypeError):
            rec_dict['old_data_parsed'] = {'error': 'Invalid JSON'}
        try:
            rec_dict['new_data_parsed'] = json.loads(record['new_data']) if record['new_data'] else None
        except (json.JSONDecodeError, TypeError):
            rec_dict['new_data_parsed'] = {'error': 'Invalid JSON'}
        processed_records.append(rec_dict)

    return render_template('product_audit_trail.html', audit_records=processed_records, product_info=product_info)


@reports_bp.route('/scan_product_api', methods=['POST'])
@login_required
def scan_product_api():
    """نقطة نهاية API لمحاكاة المسح الضوئي لرمز منتج."""
    product_code = request.json.get('product_code', '').upper().strip()
    if not product_code:
        return jsonify({'found': False, 'message': 'يرجى إدخال رمز منتج.'})

    conn = get_db_connection()
    product = conn.execute('SELECT p.*, c.name as category_name, r.name as rack_name, b.name as bin_name FROM products p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id WHERE p.product_code = ?', (product_code,)).fetchone()
    conn.close()

    if product:
        return jsonify({
            'found': True,
            'product_code': product['product_code'],
            'rack': product['rack_name'],
            'bin': product['bin_name'],
            'quantity': product['quantity'],
            'category': product['category_name'],
            'message': f'تم العثور على المنتج: {product["product_code"]} في الراك {product["rack_name"]}، السلة {product["bin_name"]} (الكمية: {product["quantity"]}).'
        })
    else:
        return jsonify({'found': False, 'message': f'لم يتم العثور على المنتج برمز: {product_code}.'})


# -------------------- API Endpoints (للتكامل الخارجي) --------------------

@reports_bp.route('/api/products', methods=['GET'])
@login_required # يمكن تغيير هذا إلى متطلبات API Key في المستقبل
def api_get_products():
    """
    نقطة نهاية API: استرجاع قائمة بجميع المنتجات.
    يمكن تصفية المنتجات باستخدام معلمات الاستعلام (query parameters).
    مثال: /api/products?category_id=1&rack_id=2
    """
    conn = get_db_connection()
    query = """
        SELECT p.product_code, p.quantity, r.name as rack, b.name as bin, c.name as category
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN racks r ON p.rack_id = r.id
        LEFT JOIN bins b ON p.bin_id = b.id
        WHERE 1=1
    """
    params = []

    # تصفية اختيارية حسب الفئة
    category_id = request.args.get('category_id')
    if category_id and category_id.isdigit():
        query += " AND p.category_id = ?"
        params.append(category_id)
    
    # تصفية اختيارية حسب الراك
    rack_id = request.args.get('rack_id')
    if rack_id and rack_id.isdigit():
        query += " AND p.rack_id = ?"
        params.append(rack_id)

    # تصفية اختيارية حسب السلة
    bin_id = request.args.get('bin_id')
    if bin_id and bin_id.isdigit():
        query += " AND p.bin_id = ?"
        params.append(bin_id)

    products = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    
    # تحويل المنتجات إلى قائمة من القواميس
    products_list = [dict(p) for p in products]
    return jsonify(products_list)

@reports_bp.route('/api/products/<string:product_code>', methods=['GET'])
@login_required # يمكن تغيير هذا إلى متطلبات API Key في المستقبل
def api_get_product_details(product_code):
    """
    نقطة نهاية API: استرجاع تفاصيل منتج معين بواسطة رمزه.
    """
    conn = get_db_connection()
    product = conn.execute('''
        SELECT p.product_code, p.quantity, r.name as rack, b.name as bin, c.name as category
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN racks r ON p.rack_id = r.id
        LEFT JOIN bins b ON p.bin_id = b.id
        WHERE p.product_code = ?
    ''', (product_code.upper(),)).fetchone()
    conn.close()

    if product:
        return jsonify(dict(product))
    else:
        return jsonify({'message': 'المنتج غير موجود.'}), 404

@reports_bp.route('/api/products/update_quantity', methods=['POST'])
@login_required # يمكن تغيير هذا إلى متطلبات API Key في المستقبل
def api_update_product_quantity():
    """
    نقطة نهاية API: تحديث كمية منتج معين.
    تتطلب: { "product_code": "XYZ", "quantity_change": 5, "action": "add" OR "remove", "reason": "API update" }
    """
    data = request.get_json()
    product_code = data.get('product_code', '').upper().strip()
    quantity_change = data.get('quantity_change')
    action = data.get('action') # 'add' or 'remove'
    reason = data.get('reason', 'API update')

    if not product_code or not isinstance(quantity_change, (int, float)) or quantity_change <= 0 or action not in ['add', 'remove']:
        return jsonify({'message': 'بيانات طلب غير صالحة.'}), 400

    conn = get_db_connection()
    product = conn.execute('SELECT id, product_code, quantity, rack_id, bin_id, category_id FROM products WHERE product_code = ?', (product_code,)).fetchone()

    if product is None:
        conn.close()
        return jsonify({'message': 'المنتج غير موجود.'}), 404
    
    product_id = product['id']
    original_quantity = product['quantity']
    new_quantity = original_quantity

    log_action_type = ""
    if action == 'add':
        new_quantity += quantity_change
        log_action_type = "api_quantity_add"
        log_details = f"API: تمت زيادة الكمية بمقدار {quantity_change} لـ {product_code}. الكمية الجديدة: {new_quantity}. السبب: {reason}."
    elif action == 'remove':
        if original_quantity < quantity_change:
            conn.close()
            return jsonify({'message': f'الكمية المتاحة لـ {product_code} هي {original_quantity} فقط. لا يمكن إزالة {quantity_change}.'}), 400
        new_quantity -= quantity_change
        log_action_type = "api_quantity_remove"
        log_details = f"API: تم إنقاص الكمية بمقدار {quantity_change} لـ {product_code}. الكمية الجديدة: {new_quantity}. السبب: {reason}."

    try:
        conn.execute('UPDATE products SET quantity = ? WHERE id = ?', (new_quantity, product_id))
        conn.commit()

        # تسجيل الحركة في سجل الحركات
        current_user_id = g.user['id'] if g.user else None # استخدام المستخدم المسجل دخوله في API
        log_transaction(product_id, current_user_id, log_action_type, log_details)

        # تسجيل في سجل التدقيق (اختياري، بناءً على الحاجة)
        old_data_for_audit = {'quantity': original_quantity, 'product_code': product_code} # يمكن إضافة المزيد من التفاصيل
        new_data_for_audit = {'quantity': new_quantity, 'product_code': product_code}
        # log_product_history(product_id, current_user_id, log_action_type, old_data_for_audit, new_data_for_audit)

        conn.close()
        return jsonify({'message': 'تم تحديث الكمية بنجاح.', 'new_quantity': new_quantity}), 200

    except Exception as e:
        conn.close()
        return jsonify({'message': f'حدث خطأ في الخادم: {str(e)}'}), 500
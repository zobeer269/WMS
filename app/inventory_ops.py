from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g, send_file
import sqlite3
import pandas as pd
import io
from io import BytesIO
from base64 import b64encode
import qrcode # لتوليد QR Code

# استيراد الدوال المساعدة للمصادقة والحركات من المخططات الزرقاء الأخرى
from .auth import login_required, admin_required
from .__init__ import get_db_connection # دالة الاتصال بقاعدة البيانات المركزية
from .transactions import log_transaction # دالة تسجيل الحركات

# إنشاء المخطط الأزرق لقسم عمليات المخزون
inventory_ops_bp = Blueprint('inventory_ops', __name__, url_prefix='/inventory_ops')

# -------------------- مسارات الجرد الدوري (Cycle Counting) --------------------

@inventory_ops_bp.route('/cycle_count_start', methods=('GET', 'POST'))
@login_required
def cycle_count_start():
    """صفحة اختيار الراك لبدء الجرد."""
    conn = get_db_connection()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()
    conn.close()
    return render_template('cycle_count_start.html', racks=racks)

@inventory_ops_bp.route('/cycle_count/<int:rack_id>', methods=('GET', 'POST'))
@login_required
def cycle_count(rack_id):
    """صفحة الجرد الفعلي لراك معين."""
    conn = get_db_connection()
    rack_info = conn.execute('SELECT * FROM racks WHERE id = ?', (rack_id,)).fetchone()
    if rack_info is None:
        flash('الراك غير موجود.', 'error')
        conn.close()
        return redirect(url_for('inventory_ops.cycle_count_start'))

    # جلب المنتجات في هذا الراك
    products_in_rack = conn.execute('''
        SELECT p.id, p.product_code, p.quantity, c.name as category_name, r.name as rack_name, b.name as bin_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN racks r ON p.rack_id = r.id
        LEFT JOIN bins b ON p.bin_id = b.id
        WHERE p.rack_id = ?
        ORDER BY b.name, p.product_code
    ''', (rack_id,)).fetchall()
    
    if request.method == 'POST':
        for product in products_in_rack:
            product_id = product['id']
            counted_quantity_str = request.form.get(f'counted_quantity_{product_id}', '').strip()
            
            original_quantity = product['quantity']

            if counted_quantity_str and counted_quantity_str.isdigit():
                counted_quantity = int(counted_quantity_str)
            else:
                counted_quantity = original_quantity 

            if counted_quantity != original_quantity:
                conn.execute('UPDATE products SET quantity = ? WHERE id = ?', (counted_quantity, product_id))
                conn.commit()

                # تأكد من أن product_id و g.user['id'] موجودان قبل تسجيل الحركة
                # (للتأكد من عدم وجود أخطاء إذا كان product_id أو g.user['id'] لاغيين)
                current_user_id = g.user['id'] if g.user else None

                log_details = f"جرد: تم تغيير الكمية من {original_quantity} إلى {counted_quantity} لـ {product['product_code']} في الراك {rack_info['name']}، السلة {product['bin_name']}. فرق: {counted_quantity - original_quantity}"
                log_transaction(product_id, current_user_id, 'cycle_count', log_details)
                flash(f'تم تحديث كمية المنتج {product["product_code"]} إلى {counted_quantity} (كانت {original_quantity}).', 'success')
            
        flash(f'تم حفظ نتائج الجرد للراك "{rack_info["name"]}" بنجاح!', 'success')
        conn.close()
        return redirect(url_for('products.list_products')) # التوجيه إلى قائمة المنتجات
    
    conn.close()
    return render_template('cycle_count.html', rack_info=rack_info, products_in_rack=products_in_rack)

# -------------------- مسارات الاستلام والإخراج (Receiving & Issuing) --------------------

@inventory_ops_bp.route('/receive_product', methods=('GET', 'POST'))
@login_required
def receive_product():
    """صفحة لاستلام المنتجات وإضافتها إلى المخزون."""
    conn = get_db_connection()
    products = conn.execute('SELECT p.id, p.product_code, r.name as rack_name, b.name as bin_name FROM products p LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id ORDER BY p.product_code').fetchall()
    conn.close()

    if request.method == 'POST':
        product_id = request.form['product_id']
        received_quantity_str = request.form['received_quantity'].strip()
        
        if not product_id or not received_quantity_str.isdigit() or int(received_quantity_str) <= 0:
            flash('الرجاء اختيار منتج وإدخال كمية صحيحة وموجبة.', 'error')
        else:
            received_quantity = int(received_quantity_str)
            conn = get_db_connection()
            product = conn.execute('SELECT product_code, quantity, rack_id, bin_id FROM products WHERE id = ?', (product_id,)).fetchone()
            
            if product:
                new_quantity = product['quantity'] + received_quantity
                conn.execute('UPDATE products SET quantity = ? WHERE id = ?', (new_quantity, product_id))
                conn.commit()

                rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (product['rack_id'],)).fetchone()['name'] if product['rack_id'] else 'N/A'
                bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (product['bin_id'],)).fetchone()['name'] if product['bin_id'] else 'N/A'
                current_user_id = g.user['id'] if g.user else None


                log_details = f"استلام: تم استلام {received_quantity} وحدة لـ {product['product_code']}. الكمية الجديدة: {new_quantity}. الموقع: {rack_name}/{bin_name}."
                log_transaction(product_id, current_user_id, 'receive_product', log_details)
                flash(f'تم استلام {received_quantity} وحدة لـ {product["product_code"]} بنجاح. الكمية الإجمالية: {new_quantity}.', 'success')
                conn.close()
                return redirect(url_for('inventory_ops.receive_product'))
            else:
                flash('المنتج غير موجود.', 'error')
                conn.close() # تأكد من إغلاق الاتصال حتى لو لم يتم العثور على المنتج

    return render_template('receive_product.html', products=products)


@inventory_ops_bp.route('/issue_product', methods=('GET', 'POST'))
@login_required
def issue_product():
    """صفحة لإخراج المنتجات من المخزون."""
    conn = get_db_connection()
    products = conn.execute('SELECT p.id, p.product_code, p.quantity, r.name as rack_name, b.name as bin_name FROM products p LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id ORDER BY p.product_code').fetchall()
    conn.close()

    if request.method == 'POST':
        product_id = request.form['product_id']
        issued_quantity_str = request.form['issued_quantity'].strip()
        issue_reason = request.form['issue_reason'].strip()
        
        if not product_id or not issued_quantity_str.isdigit() or int(issued_quantity_str) <= 0:
            flash('الرجاء اختيار منتج وإدخال كمية صحيحة وموجبة.', 'error')
        elif not issue_reason:
            flash('سبب الإخراج مطلوب.', 'error')
        else:
            issued_quantity = int(issued_quantity_str)
            conn = get_db_connection()
            product = conn.execute('SELECT product_code, quantity, rack_id, bin_id FROM products WHERE id = ?', (product_id,)).fetchone()
            
            if product:
                if product['quantity'] < issued_quantity:
                    flash(f'الكمية المتاحة لـ {product["product_code"]} هي {product["quantity"]} فقط. لا يمكن إخراج {issued_quantity}.', 'error')
                else:
                    new_quantity = product['quantity'] - issued_quantity
                    conn.execute('UPDATE products SET quantity = ? WHERE id = ?', (new_quantity, product_id))
                    conn.commit()

                    rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (product['rack_id'],)).fetchone()['name'] if product['rack_id'] else 'N/A'
                    bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (product['bin_id'],)).fetchone()['name'] if product['bin_id'] else 'N/A'
                    current_user_id = g.user['id'] if g.user else None


                    log_details = f"إخراج: تم إخراج {issued_quantity} وحدة لـ {product['product_code']}. الكمية الجديدة: {new_quantity}. السبب: {issue_reason}. الموقع: {rack_name}/{bin_name}."
                    log_transaction(product_id, current_user_id, 'issue_product', log_details)
                    flash(f'تم إخراج {issued_quantity} وحدة لـ {product["product_code"]} بنجاح. الكمية المتبقية: {new_quantity}.', 'success')
                    conn.close()
                    return redirect(url_for('inventory_ops.issue_product'))
            else:
                flash('المنتج غير موجود.', 'error')
            conn.close() 

    return render_template('issue_product.html', products=products)


# -------------------- مسارات الاستيراد والتصدير --------------------

import pandas as pd # تأكد من استيراد pandas هنا
# from flask import send_file # تم استيراده في الأعلى

@inventory_ops_bp.route('/export_products_csv')
@admin_required 
def export_products_csv():
    """تصدير جميع المنتجات إلى ملف CSV."""
    conn = get_db_connection()
    products = conn.execute('SELECT p.product_code, r.name as rack_name, b.name as bin_name, p.quantity, c.name as category_name FROM products p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id').fetchall()
    conn.close()

    if not products:
        flash('لا توجد منتجات لتصديرها.', 'info')
        return redirect(url_for('products.list_products'))

    df = pd.DataFrame([dict(row) for row in products])
    df.rename(columns={'rack_name': 'rack', 'bin_name': 'bin', 'category_name': 'category'}, inplace=True)
    
    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8-sig') # utf-8-sig لدعم اللغة العربية في Excel
    output.seek(0)

    return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name='inventory_products.csv')

@inventory_ops_bp.route('/import_products_csv', methods=('GET', 'POST'))
@admin_required 
def import_products_csv():
    """استيراد المنتجات من ملف CSV."""
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('لم يتم رفع أي ملف.', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('الرجاء اختيار ملف.', 'error')
            return redirect(request.url)

        if file and file.filename.endswith('.csv'):
            try:
                df = pd.read_csv(file, encoding='utf-8')
                required_columns = ['product_code', 'rack', 'bin', 'quantity', 'category']
                if not all(col in df.columns for col in required_columns):
                    flash(f'الملف يجب أن يحتوي على الأعمدة التالية: {", ".join(required_columns)}', 'error')
                    return render_template('import_products_csv.html')

                conn = get_db_connection()
                imported_count = 0
                updated_count = 0
                skipped_count = 0 

                for index, row in df.iterrows():
                    try:
                        product_code = str(row['product_code']).upper().strip()
                        rack_name = str(row['rack']).upper().strip()
                        bin_name = str(row['bin']).upper().strip()
                        quantity = int(row['quantity']) if pd.notna(row['quantity']) and str(row['quantity']).isdigit() else 0
                        category_name = str(row['category']).strip() if pd.notna(row['category']) else 'عام'

                        # الحصول على category_id أو إنشاء فئة جديدة
                        category = conn.execute('SELECT id FROM categories WHERE name = ?', (category_name,)).fetchone()
                        if category:
                            category_id = category['id']
                        else:
                            conn.execute('INSERT INTO categories (name) VALUES (?)', (category_name,))
                            conn.commit()
                            category_id = conn.execute('SELECT id FROM categories WHERE name = ?', (category_name,)).fetchone()['id']
                        
                        # الحصول على rack_id أو إنشاء راك جديد
                        rack = conn.execute('SELECT id FROM racks WHERE name = ?', (rack_name,)).fetchone()
                        if rack:
                            rack_id = rack['id']
                        else:
                            conn.execute('INSERT INTO racks (name) VALUES (?)', (rack_name,))
                            conn.commit()
                            rack_id = conn.execute('SELECT id FROM racks WHERE name = ?', (rack_name,)).fetchone()['id']

                        # الحصول على bin_id أو إنشاء سلة جديدة داخل الراك
                        bin_data = conn.execute('SELECT id FROM bins WHERE name = ? AND rack_id = ?', (bin_name, rack_id)).fetchone()
                        if bin_data:
                            bin_id = bin_data['id']
                        else:
                            conn.execute('INSERT INTO bins (name, rack_id) VALUES (?, ?)', (bin_name, rack_id))
                            conn.commit()
                            bin_id = conn.execute('SELECT id FROM bins WHERE name = ? AND rack_id = ?', (bin_name, rack_id)).fetchone()['id']


                        # التحقق مما إذا كان المنتج موجودًا
                        existing_product = conn.execute('SELECT id, quantity FROM products WHERE product_code = ?', (product_code,)).fetchone()

                        if existing_product:
                            product_id = existing_product['id']
                            old_quantity = existing_product['quantity']
                            conn.execute('UPDATE products SET rack_id = ?, bin_id = ?, quantity = ?, category_id = ? WHERE id = ?',
                                         (rack_id, bin_id, quantity, category_id, product_id))
                            log_details = f"تم تحديث المنتج من CSV. الكمية من {old_quantity} إلى {quantity}، الراك: {rack_name}, السلة: {bin_name}, الفئة: {category_name}"
                            log_transaction(product_id, g.user['id'], 'import_update_product', log_details)
                            updated_count += 1
                        else:
                            conn.execute('INSERT INTO products (product_code, rack_id, bin_id, quantity, category_id) VALUES (?, ?, ?, ?, ?)',
                                         (product_code, rack_id, bin_id, quantity, category_id))
                            product_id = conn.execute('SELECT id FROM products WHERE product_code = ?', (product_code,)).fetchone()[0]
                            log_details = f"تم إضافة المنتج من CSV. الكمية: {quantity}, الراك: {rack_name}, السلة: {bin_name}, الفئة: {category_name}"
                            log_transaction(product_id, g.user['id'], 'import_add_product', log_details)
                            imported_count += 1
                    except Exception as row_e:
                        flash(f'تخطي الصف رقم {index + 2} (السطر في الملف) بسبب خطأ: {row_e}', 'warning')
                        skipped_count += 1
                        continue
                conn.commit()
                conn.close()
                flash(f'تم استيراد {imported_count} منتج جديد وتحديث {updated_count} منتج موجود بنجاح! تم تخطي {skipped_count} صفاً بسبب الأخطاء.', 'success')
                return redirect(url_for('products.list_products'))

            except pd.errors.EmptyDataError:
                flash('الملف فارغ.', 'error')
            except pd.errors.ParserError:
                flash('خطأ في تحليل ملف CSV. تأكد من أن التنسيق صحيح ويحتوي على الأعمدة المطلوبة.', 'error')
            except Exception as e:
                flash(f'حدث خطأ أثناء الاستيراد: {e}', 'error')
            finally:
                if conn: conn.close()
        else:
            flash('الرجاء رفع ملف CSV صالح.', 'error')
    return render_template('import_products_csv.html')

# -------------------- مسارات الباركود / QR Code --------------------

@inventory_ops_bp.route('/generate_qrcode/<path:product_code>') # <path:product_code> للسماح بـ '/' في الرمز
@login_required
def generate_qrcode(product_code):
    """نقطة نهاية API لتوليد QR Code لرمز منتج وإرجاعه كصورة PNG مرمزة بـ base64."""
    try:
        qr_code = qrcode.QRCode(
            version=1, # حجم الـ QR Code، 1 هو الأصغر
            error_correction=qrcode.constants.ERROR_CORRECT_L, # مستوى تصحيح الخطأ (L: Low)
            box_size=10, # حجم كل "مربع" في الـ QR Code
            border=4, # سمك الحدود البيضاء حول الـ QR Code
        )
        qr_code.add_data(product_code) # إضافة رمز المنتج كبيانات للـ QR Code
        qr_code.make(fit=True) # ضبط حجم الـ QR Code ليتناسب مع البيانات

        img = qr_code.make_image(fill_color="black", back_color="white")
        
        # حفظ الصورة في الذاكرة المؤقتة (بدلاً من حفظها كملف)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0) # العودة إلى بداية البايتات
        
        # ترميز الصورة لـ base64 لتضمينها مباشرة في HTML
        encoded_image = b64encode(buffer.getvalue()).decode('ascii')
        return jsonify({'image_base64': encoded_image}) # إرجاع الصورة المرمزة كـ JSON
    except Exception as e:
        print(f"Error generating QR code for {product_code}: {e}")
        return jsonify({'error': str(e), 'message': 'فشل في توليد رمز QR.'}), 500

@inventory_ops_bp.route('/print_barcodes')
@login_required
def print_barcodes():
    """صفحة لعرض جميع المنتجات مع أزرار لتوليد وطباعة الباركود/QR Code."""
    conn = get_db_connection()
    products = conn.execute('SELECT product_code FROM products ORDER BY product_code').fetchall()
    conn.close()

    products_list = [{'product_code': p['product_code']} for p in products]

    return render_template('print_barcodes.html', products=products_list)
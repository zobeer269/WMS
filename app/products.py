from flask import Blueprint, render_template, request, redirect, url_for, flash, g
import sqlite3
import json # لاستخدامه في تحويل البيانات إلى JSON لـ product_history

from .auth import login_required, admin_required
from .__init__ import get_db_connection
from .transactions import log_transaction 

# إنشاء المخطط الأزرق لقسم المنتجات
products_bp = Blueprint('products', __name__, url_prefix='/products')

# دالة مساعدة لتسجيل تغييرات المنتج في product_history
def log_product_history(product_id, user_id, action, old_data=None, new_data=None):
    conn = get_db_connection()
    old_data_json = json.dumps(old_data) if old_data else None
    new_data_json = json.dumps(new_data) if new_data else None
    conn.execute('INSERT INTO product_history (product_id, user_id, action, old_data, new_data) VALUES (?, ?, ?, ?, ?)',
                 (product_id, user_id, action, old_data_json, new_data_json))
    conn.commit()
    conn.close()


# -------------------- مسارات إدارة المنتجات --------------------

@products_bp.route('/')
@login_required 
def list_products():
    """عرض قائمة بجميع المنتجات مع الكميات والفئات والمواقع."""
    conn = get_db_connection()
    products = conn.execute('SELECT p.*, c.name as category_name, r.name as rack_name, b.name as bin_name FROM products p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id ORDER BY p.product_code').fetchall()
    conn.close()
    return render_template('list_products.html', products=products)

@products_bp.route('/add', methods=('GET', 'POST'))
@login_required 
def add_product():
    """إضافة منتج جديد إلى المخزون مع اختيار الراك والسلة والفئة."""
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories ORDER BY name').fetchall()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()
    
    if request.method == 'POST':
        product_code = request.form['product_code'].upper().strip()
        rack_id = request.form['rack_id'].strip() if request.form['rack_id'] else None
        bin_id = request.form['bin_id'].strip() if request.form['bin_id'] else None
        quantity_str = request.form['quantity'].strip()
        category_id = request.form['category_id'].strip() if request.form['category_id'] else None

        if not product_code:
            flash('رمز المنتج مطلوب!', 'error')
        elif not rack_id:
            flash('الراك مطلوب!', 'error')
        elif not bin_id:
            flash('السلة مطلوبة!', 'error') 
        elif not quantity_str.isdigit() or int(quantity_str) < 0:
            flash('الكمية يجب أن تكون رقمًا صحيحًا وموجبًا أو صفرًا!', 'error')
        elif not category_id:
            flash('الفئة مطلوبة!', 'error')
        else:
            quantity = int(quantity_str)
            try:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO products (product_code, rack_id, bin_id, quantity, category_id) VALUES (?, ?, ?, ?, ?)',
                             (product_code, rack_id, bin_id, quantity, category_id))
                conn.commit()
                product_id = cursor.lastrowid # الحصول على ID المنتج المضاف حديثاً

                # جلب الأسماء لتسجيل الحركة وسجل التدقيق بالتفصيل
                rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (rack_id,)).fetchone()['name'] if rack_id else 'N/A'
                bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (bin_id,)).fetchone()['name'] if bin_id else 'N/A'
                category_name = conn.execute('SELECT name FROM categories WHERE id = ?', (category_id,)).fetchone()['name'] if category_id else 'N/A'

                # تسجيل الحركة في جدول الحركات
                log_details = f"تم إضافة المنتج. الكمية: {quantity}, الراك: {rack_name}, السلة: {bin_name}, الفئة: {category_name}"
                log_transaction(product_id, g.user['id'], 'add_product', log_details)

                # تسجيل في سجل التدقيق
                new_product_data = {
                    'product_code': product_code, 'rack_id': rack_id, 'bin_id': bin_id,
                    'quantity': quantity, 'category_id': category_id,
                    'rack_name': rack_name, 'bin_name': bin_name, 'category_name': category_name
                }
                log_product_history(product_id, g.user['id'], 'created', None, new_product_data)

                flash('تم إضافة المنتج بنجاح!', 'success')
                return redirect(url_for('products.list_products'))
            except sqlite3.IntegrityError:
                flash(f'رمز المنتج "{product_code}" موجود بالفعل. يرجى استخدام رمز فريد.', 'error')
            except Exception as e:
                flash(f'حدث خطأ غير متوقع: {e}', 'error')
            finally:
                conn.close()
            return render_template('add_product.html', categories=categories, racks=racks)
    conn.close()
    return render_template('add_product.html', categories=categories, racks=racks)

@products_bp.route('/edit/<int:id>', methods=('GET', 'POST'))
@login_required 
def edit_product(id):
    """تعديل معلومات منتج موجود (رمز، راك، سلة، كمية، فئة)."""
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (id,)).fetchone()
    categories = conn.execute('SELECT * FROM categories ORDER BY name').fetchall()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()

    if product is None:
        flash('المنتج غير موجود.', 'error')
        conn.close()
        return redirect(url_for('products.list_products'))

    current_rack_bins = []
    if product['rack_id']:
        current_rack_bins = conn.execute('SELECT id, name FROM bins WHERE rack_id = ? ORDER BY name', (product['rack_id'],)).fetchall()

    if request.method == 'POST':
        product_code = request.form['product_code'].upper().strip()
        rack_id = request.form['rack_id'].strip() if request.form['rack_id'] else None
        bin_id = request.form['bin_id'].strip() if request.form['bin_id'] else None
        quantity_str = request.form['quantity'].strip()
        category_id = request.form['category_id'].strip() if request.form['category_id'] else None

        if not product_code:
            flash('رمز المنتج مطلوب!', 'error')
        elif not rack_id:
            flash('الراك مطلوب!', 'error')
        elif not bin_id:
            flash('السلة مطلوبة!', 'error')
        elif not quantity_str.isdigit() or int(quantity_str) < 0:
            flash('الكمية يجب أن تكون رقمًا صحيحًا وموجبًا أو صفرًا!', 'error')
        elif not category_id:
            flash('الفئة مطلوبة!', 'error')
        else:
            quantity = int(quantity_str)
            try:
                existing_product = conn.execute('SELECT id FROM products WHERE product_code = ? AND id != ?',
                                                (product_code, id)).fetchone()
                if existing_product:
                    flash(f'رمز المنتج "{product_code}" موجود بالفعل لمنتج آخر.', 'error')
                else:
                    old_product_data = dict(product) # حفظ البيانات القديمة للتسجيل

                    conn.execute('UPDATE products SET product_code = ?, rack_id = ?, bin_id = ?, quantity = ?, category_id = ? WHERE id = ?',
                                 (product_code, rack_id, bin_id, quantity, category_id, id))
                    conn.commit()

                    # جلب الأسماء القديمة والجديدة لتسجيل الحركة وسجل التدقيق بالتفصيل
                    old_rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (old_product_data['rack_id'],)).fetchone()['name'] if old_product_data['rack_id'] else 'N/A'
                    old_bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (old_product_data['bin_id'],)).fetchone()['name'] if old_product_data['bin_id'] else 'N/A'
                    old_category_name = conn.execute('SELECT name FROM categories WHERE id = ?', (old_product_data['category_id'],)).fetchone()['name'] if old_product_data['category_id'] else 'N/A'

                    new_rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (rack_id,)).fetchone()['name'] if rack_id else 'N/A'
                    new_bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (bin_id,)).fetchone()['name'] if bin_id else 'N/A'
                    new_category_name = conn.execute('SELECT name FROM categories WHERE id = ?', (category_id,)).fetchone()['name'] if category_id else 'N/A'

                    # تسجيل الحركة في جدول الحركات
                    log_details = (f"تم تحديث المنتج من: "
                                   f"رمز: {old_product_data['product_code']}, راك: {old_rack_name}, سلة: {old_bin_name}, "
                                   f"كمية: {old_product_data['quantity']}, فئة: {old_category_name}. "
                                   f"إلى: رمز: {product_code}, راك: {new_rack_name}, سلة: {new_bin_name}, كمية: {quantity}, فئة: {new_category_name}.")
                    log_transaction(id, g.user['id'], 'edit_product', log_details)

                    # تسجيل في سجل التدقيق
                    old_product_full_data = {
                        'product_code': old_product_data['product_code'], 'rack_id': old_product_data['rack_id'], 'bin_id': old_product_data['bin_id'],
                        'quantity': old_product_data['quantity'], 'category_id': old_product_data['category_id'],
                        'rack_name': old_rack_name, 'bin_name': old_bin_name, 'category_name': old_category_name
                    }
                    new_product_full_data = {
                        'product_code': product_code, 'rack_id': rack_id, 'bin_id': bin_id,
                        'quantity': quantity, 'category_id': category_id,
                        'rack_name': new_rack_name, 'bin_name': new_bin_name, 'category_name': new_category_name
                    }
                    log_product_history(id, g.user['id'], 'updated', old_product_full_data, new_product_full_data)

                    flash('تم تحديث المنتج بنجاح!', 'success')
                    return redirect(url_for('products.list_products'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث المنتج: {e}', 'error')
            finally:
                conn.close()
            return render_template('edit_product.html', product=product, categories=categories, racks=racks, current_rack_bins=current_rack_bins)
    else:
        conn.close()
    return render_template('edit_product.html', product=product, categories=categories, racks=racks, current_rack_bins=current_rack_bins)

@products_bp.route('/update_quantity/<int:id>', methods=('POST',))
@login_required
def update_quantity(id):
    """تحديث الكمية (زيادة/نقصان) لمنتج معين."""
    action = request.form.get('action')
    change_amount_str = request.form.get('change_amount').strip()

    if not change_amount_str or not change_amount_str.isdigit() or int(change_amount_str) <= 0:
        flash('يرجى إدخال قيمة صحيحة وموجبة للتغيير.', 'error')
        return redirect(url_for('products.list_products'))

    change_amount = int(change_amount_str)
    conn = get_db_connection()
    product = conn.execute('SELECT product_code, quantity, rack_id, bin_id, category_id FROM products WHERE id = ?', (id,)).fetchone()

    if product is None:
        flash('المنتج غير موجود لتحديث الكمية.', 'error')
        conn.close()
        return redirect(url_for('products.list_products'))

    current_quantity = product['quantity']
    new_quantity = current_quantity
    log_action_type = ''
    log_details = ''

    rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (product['rack_id'],)).fetchone()['name'] if product['rack_id'] else 'N/A'
    bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (product['bin_id'],)).fetchone()['name'] if product['bin_id'] else 'N/A'
    category_name = conn.execute('SELECT name FROM categories WHERE id = ?', (product['category_id'],)).fetchone()['name'] if product['category_id'] else 'N/A'


    if action == 'increase':
        new_quantity = current_quantity + change_amount
        log_action_type = 'increase_quantity'
        log_details = f"تمت زيادة الكمية بمقدار {change_amount} من {current_quantity} إلى {new_quantity} لـ {product['product_code']} في الراك {rack_name}، السلة {bin_name}."
        flash(f'تمت زيادة الكمية بمقدار {change_amount} لـ {product["product_code"]}. الكمية الجديدة: {new_quantity}.', 'success')
    elif action == 'decrease':
        if current_quantity < change_amount:
            flash(f'الكمية المتاحة لـ {product["product_code"]} هي {product["quantity"]} فقط. لا يمكن إنقاص الكمية بمقدار {change_amount}.', 'error')
            conn.close()
            return redirect(url_for('products.list_products'))
        new_quantity = current_quantity - change_amount
        log_action_type = 'decrease_quantity'
        log_details = f"تم إنقاص الكمية بمقدار {change_amount} من {current_quantity} إلى {new_quantity} لـ {product['product_code']} في الراك {rack_name}، السلة {bin_name}."
        flash(f'تم إنقاص الكمية بمقدار {change_amount} لـ {product["product_code"]}. الكمية الجديدة: {new_quantity}.', 'success')
    else:
        flash('إجراء غير صالح لتحديث الكمية.', 'error')
        conn.close()
        return redirect(url_for('products.list_products'))

    try:
        old_quantity_data = dict(product) # حفظ الكمية القديمة
        conn.execute('UPDATE products SET quantity = ? WHERE id = ?', (new_quantity, id))
        conn.commit()
        log_transaction(id, g.user['id'], log_action_type, log_details)

        # تسجيل في سجل التدقيق (تغيير الكمية)
        old_product_full_data = {
            'product_code': product['product_code'], 'rack_id': product['rack_id'], 'bin_id': product['bin_id'],
            'quantity': current_quantity, 'category_id': product['category_id'],
            'rack_name': rack_name, 'bin_name': bin_name, 'category_name': category_name
        }
        new_product_full_data = {
            'product_code': product['product_code'], 'rack_id': product['rack_id'], 'bin_id': product['bin_id'],
            'quantity': new_quantity, 'category_id': product['category_id'],
            'rack_name': rack_name, 'bin_name': bin_name, 'category_name': category_name
        }
        log_product_history(id, g.user['id'], log_action_type, old_product_full_data, new_product_full_data)

    except Exception as e:
        flash(f'حدث خطأ أثناء تحديث الكمية: {e}', 'error')
    finally:
        conn.close()
    return redirect(url_for('products.list_products'))

@products_bp.route('/delete/<int:id>', methods=('POST',))
@login_required 
def delete_product(id):
    """حذف منتج من المخزون."""
    conn = get_db_connection()
    product = conn.execute('SELECT product_code, quantity, rack_id, bin_id, category_id FROM products WHERE id = ?', (id,)).fetchone()

    if product is None:
        flash('المنتج غير موجود للحذف.', 'error')
    else:
        try:
            rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (product['rack_id'],)).fetchone()['name'] if product['rack_id'] else 'N/A'
            bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (product['bin_id'],)).fetchone()['name'] if product['bin_id'] else 'N/A'
            category_name = conn.execute('SELECT name FROM categories WHERE id = ?', (product['category_id'],)).fetchone()['name'] if product['category_id'] else 'N/A'

            old_product_full_data = {
                'product_code': product['product_code'], 'rack_id': product['rack_id'], 'bin_id': product['bin_id'],
                'quantity': product['quantity'], 'category_id': product['category_id'],
                'rack_name': rack_name, 'bin_name': bin_name, 'category_name': category_name
            }

            conn.execute('DELETE FROM products WHERE id = ?', (id,))
            conn.commit()
            log_details = f"تم حذف المنتج: {product['product_code']} من الراك {rack_name}، السلة {bin_name}."
            log_transaction(id, g.user['id'], 'delete_product', log_details)
            
            # تسجيل في سجل التدقيق (حذف)
            log_product_history(id, g.user['id'], 'deleted', old_product_full_data, None)

            flash(f'تم حذف المنتج "{product["product_code"]}" بنجاح!', 'success')
        except Exception as e:
            flash(f'حدث خطأ أثناء حذف المنتج: {e}', 'error')
        finally:
            conn.close()
    return redirect(url_for('products.list_products'))

@products_bp.route('/search', methods=('GET', 'POST'))
@login_required 
def search_product():
    """البحث عن منتج وعرض موقعه وكميته وفئته (البحث المتقدم)."""
    results = []
    search_query = ''
    if request.method == 'POST':
        search_query = request.form['search_query'].upper().strip()
        if not search_query:
            flash('يرجى إدخال كلمة للبحث.', 'error')
        else:
            conn = get_db_connection()
            query = """
                SELECT p.*, c.name as category_name, r.name as rack_name, b.name as bin_name FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                LEFT JOIN racks r ON p.rack_id = r.id
                LEFT JOIN bins b ON p.bin_id = b.id
                WHERE p.product_code LIKE ? OR r.name LIKE ? OR b.name LIKE ? OR c.name LIKE ?
                ORDER BY p.product_code
            """
            results = conn.execute(query, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', f'%{search_query}%')).fetchall()
            conn.close()
            if results:
                flash(f'تم العثور على {len(results)} نتائج للبحث عن "{search_query}".', 'success')
            else:
                flash(f'لم يتم العثور على أي منتج يطابق "{search_query}".', 'error')
    return render_template('search_product.html', results=results, search_query=search_query)
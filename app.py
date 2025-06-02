from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g, send_file
import sqlite3
import hashlib # لتجزئة كلمات المرور
import functools # لإنشاء مزخرفات (decorators)
import pandas as pd # لاستخدام مكتبة pandas في الاستيراد والتصدير
import io # للمساعدة في التعامل مع الملفات في الذاكرة
import os # للوصول إلى مسارات الملفات (لا يُستخدم بشكل مباشر في هذا الكود حالياً لكنه قد يكون مفيداً)
import qrcode # لتوليد QR Code
from io import BytesIO
from base64 import b64encode # لترميز صور QR Code ليتم عرضها في HTML

app = Flask(__name__)
# مفتاح سري قوي لـ Flask Sessions و flash messages
# غير هذا المفتاح إلى سلسلة عشوائية ومعقدة في بيئة الإنتاج!
app.config['SECRET_KEY'] = 'a_very_secret_key_for_inventory_app_v5_full_features_123456'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 # مدة صلاحية الجلسة بالثواني (ساعة واحدة)

# -------------------- دوال مساعدة للمصادقة --------------------

def login_required(view):
    """مزخرف يتطلب تسجيل الدخول للوصول إلى المسار."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash('يجب عليك تسجيل الدخول أولاً للوصول إلى هذه الصفحة.', 'error')
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def admin_required(view):
    """مزخرف يتطلب أن يكون المستخدم مديرًا للوصول إلى المسار."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash('يجب عليك تسجيل الدخول أولاً للوصول إلى هذه الصفحة.', 'error')
            return redirect(url_for('login'))
        if not g.user['is_admin']:
            flash('ليس لديك الصلاحيات الكافية للوصول إلى هذه الصفحة.', 'error')
            return redirect(url_for('index')) # يمكن توجيهه لصفحة أخرى
        return view(**kwargs)
    return wrapped_view

@app.before_request
def load_logged_in_user():
    """تحميل معلومات المستخدم المسجل دخوله قبل كل طلب."""
    user_id = session.get('user_id')
    g.user = None # تهيئة g.user بـ None في كل مرة
    if user_id:
        conn = get_db_connection()
        g.user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()

# -------------------- دوال مساعدة لقاعدة البيانات والحركات --------------------

def get_db_connection():
    """الاتصال بقاعدة البيانات."""
    conn = sqlite3.connect('inventory.db')
    conn.row_factory = sqlite3.Row # هذا يجعلنا نصل إلى الأعمدة بالاسم
    return conn

def log_transaction(product_id, user_id, action, details):
    """تسجيل حركة في جدول الحركات."""
    conn = get_db_connection()
    conn.execute('INSERT INTO transactions (product_id, user_id, action, details) VALUES (?, ?, ?, ?)',
                 (product_id, user_id, action, details))
    conn.commit()
    conn.close()

# -------------------- مسارات المصادقة --------------------

@app.route('/login', methods=('GET', 'POST'))
def login():
    """صفحة تسجيل الدخول."""
    if g.user: # إذا كان المستخدم مسجلاً بالفعل، أعد توجيهه للوحة التحكم
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        error = None

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user is None:
            error = 'اسم المستخدم غير موجود.'
        elif hashlib.sha256(password.encode()).hexdigest() != user['password_hash']:
            error = 'كلمة المرور غير صحيحة.'

        if error is None:
            session.clear()
            session['user_id'] = user['id']
            session.permanent = True # لجعل الجلسة دائمة حسب PERMANENT_SESSION_LIFETIME
            flash(f'مرحباً {user["username"]}! تم تسجيل الدخول بنجاح.', 'success')
            return redirect(url_for('index'))
        flash(error, 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """تسجيل الخروج من الحساب."""
    session.clear()
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('login'))

# -------------------- مسارات إدارة المستخدمين (للمدراء فقط) --------------------

@app.route('/users')
@admin_required
def list_users():
    """عرض قائمة بجميع المستخدمين (للمدراء فقط)."""
    conn = get_db_connection()
    users = conn.execute('SELECT id, username, is_admin FROM users ORDER BY username').fetchall()
    conn.close()
    return render_template('list_users.html', users=users)

@app.route('/add_user', methods=('GET', 'POST'))
@admin_required
def add_user():
    """إضافة مستخدم جديد (للمدراء فقط)."""
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        is_admin = 1 if 'is_admin' in request.form else 0
        error = None

        if not username:
            error = 'اسم المستخدم مطلوب!'
        elif not password:
            error = 'كلمة المرور مطلوبة!'
        elif len(password) < 6: # مثال: كلمة المرور لا تقل عن 6 أحرف
            error = 'كلمة المرور يجب أن لا تقل عن 6 أحرف!'

        if error is None:
            conn = get_db_connection()
            try:
                hashed_password = hashlib.sha256(password.encode()).hexdigest()
                conn.execute('INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)',
                             (username, hashed_password, is_admin))
                conn.commit()
                flash(f'تم إضافة المستخدم "{username}" بنجاح!', 'success')
                return redirect(url_for('list_users'))
            except sqlite3.IntegrityError:
                flash(f'اسم المستخدم "{username}" موجود بالفعل. يرجى اختيار اسم آخر.', 'error')
            except Exception as e:
                flash(f'حدث خطأ غير متوقع: {e}', 'error')
            finally:
                conn.close()
        flash(error, 'error')
    return render_template('add_user.html')

@app.route('/edit_user/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_user(id):
    """تعديل مستخدم (للمدراء فقط)."""
    conn = get_db_connection()
    user = conn.execute('SELECT id, username, is_admin FROM users WHERE id = ?', (id,)).fetchone()

    if user is None:
        flash('المستخدم غير موجود.', 'error')
        conn.close() # إغلاق الاتصال قبل الرجوع
        return redirect(url_for('list_users'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip() # قد يكون فارغاً إذا لم يرغبوا في تغييره
        is_admin = 1 if 'is_admin' in request.form else 0
        error = None

        if not username:
            error = 'اسم المستخدم مطلوب!'

        if error is None:
            try:
                # التحقق من تكرار اسم المستخدم (باستثناء المستخدم الحالي)
                existing_user = conn.execute('SELECT id FROM users WHERE username = ? AND id != ?',
                                             (username, id)).fetchone()
                if existing_user:
                    flash(f'اسم المستخدم "{username}" موجود بالفعل لمستخدم آخر.', 'error')
                else:
                    update_query = 'UPDATE users SET username = ?, is_admin = ?'
                    params = [username, is_admin]
                    if password: # إذا تم إدخال كلمة مرور جديدة
                        if len(password) < 6:
                            flash('كلمة المرور الجديدة يجب أن لا تقل عن 6 أحرف!', 'error')
                            return render_template('edit_user.html', user=user)
                        hashed_password = hashlib.sha256(password.encode()).hexdigest()
                        update_query += ', password_hash = ?'
                        params.append(hashed_password)

                    update_query += ' WHERE id = ?'
                    params.append(id)

                    conn.execute(update_query, tuple(params))
                    conn.commit()
                    flash('تم تحديث المستخدم بنجاح!', 'success')
                    return redirect(url_for('list_users'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث المستخدم: {e}', 'error')
            finally:
                conn.close()
        flash(error, 'error')
    else: # If GET request, close connection
        conn.close()
    return render_template('edit_user.html', user=user)

@app.route('/delete_user/<int:id>', methods=('POST',))
@admin_required
def delete_user(id):
    """حذف مستخدم (للمدراء فقط)."""
    if id == g.user['id']:
        flash('لا يمكنك حذف حسابك الخاص أثناء تسجيل الدخول!', 'error')
        return redirect(url_for('list_users'))

    conn = get_db_connection()
    user = conn.execute('SELECT username FROM users WHERE id = ?', (id,)).fetchone()

    if user is None:
        flash('المستخدم غير موجود للحذف.', 'error')
    else:
        try:
            # التحقق مما إذا كان هذا المستخدم قد أجرى أي حركات
            transactions_count = conn.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ?', (id,)).fetchone()[0]
            if transactions_count > 0:
                flash(f'لا يمكن حذف المستخدم "{user["username"]}" لوجود حركات مسجلة باسمه. يرجى مراجعة سجل الحركات.', 'error')
            else:
                conn.execute('DELETE FROM users WHERE id = ?', (id,))
                conn.commit()
                flash(f'تم حذف المستخدم "{user["username"]}" بنجاح!', 'success')
        except Exception as e:
            flash(f'حدث خطأ أثناء حذف المستخدم: {e}', 'error')
        finally:
            conn.close()
    return redirect(url_for('list_users'))

# -------------------- مسارات إدارة الفئات --------------------

@app.route('/categories')
@admin_required
def list_categories():
    """عرض قائمة بجميع الفئات."""
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories ORDER BY name').fetchall()
    conn.close()
    return render_template('list_categories.html', categories=categories)

@app.route('/add_category', methods=('GET', 'POST'))
@admin_required
def add_category():
    """إضافة فئة جديدة."""
    if request.method == 'POST':
        category_name = request.form['name'].strip()
        if not category_name:
            flash('اسم الفئة مطلوب!', 'error')
        else:
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO categories (name) VALUES (?)', (category_name,))
                conn.commit()
                flash(f'تم إضافة الفئة "{category_name}" بنجاح!', 'success')
                return redirect(url_for('list_categories'))
            except sqlite3.IntegrityError:
                flash(f'الفئة "{category_name}" موجودة بالفعل. يرجى اختيار اسم فريد.', 'error')
            finally:
                conn.close()
    return render_template('add_category.html')

@app.route('/edit_category/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_category(id):
    """تعديل فئة موجودة."""
    conn = get_db_connection()
    category = conn.execute('SELECT * FROM categories WHERE id = ?', (id,)).fetchone()

    if category is None:
        flash('الفئة غير موجودة.', 'error')
        conn.close()
        return redirect(url_for('list_categories'))

    if request.method == 'POST':
        new_name = request.form['name'].strip()
        if not new_name:
            flash('اسم الفئة مطلوب!', 'error')
        else:
            try:
                existing_category = conn.execute('SELECT id FROM categories WHERE name = ? AND id != ?',
                                                (new_name, id)).fetchone()
                if existing_category:
                    flash(f'الفئة "{new_name}" موجودة بالفعل.', 'error')
                else:
                    conn.execute('UPDATE categories SET name = ? WHERE id = ?', (new_name, id))
                    conn.commit()
                    flash('تم تحديث الفئة بنجاح!', 'success')
                    return redirect(url_for('list_categories'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث الفئة: {e}', 'error')
            finally:
                conn.close()
    else:
        conn.close()
    return render_template('edit_category.html', category=category)

@app.route('/delete_category/<int:id>', methods=('POST',))
@admin_required
def delete_category(id):
    """حذف فئة."""
    conn = get_db_connection()
    category = conn.execute('SELECT name FROM categories WHERE id = ?', (id,)).fetchone()

    if category is None:
        flash('الفئة غير موجودة للحذف.', 'error')
    else:
        try:
            # التحقق مما إذا كانت هناك منتجات مرتبطة بهذه الفئة
            products_count = conn.execute('SELECT COUNT(*) FROM products WHERE category_id = ?', (id,)).fetchone()[0]
            if products_count > 0:
                flash(f'لا يمكن حذف الفئة "{category["name"]}" لوجود {products_count} منتج مرتبط بها. يرجى تعديل المنتجات أولاً.', 'error')
            else:
                conn.execute('DELETE FROM categories WHERE id = ?', (id,))
                conn.commit()
                flash(f'تم حذف الفئة "{category["name"]}" بنجاح!', 'success')
        except Exception as e:
            flash(f'حدث خطأ أثناء حذف الفئة: {e}', 'error')
        finally:
            conn.close()
    return redirect(url_for('list_categories'))

# -------------------- مسارات إدارة المواقع (الراكات والسلات) --------------------

@app.route('/racks')
@admin_required
def list_racks():
    """عرض قائمة بجميع الراكات."""
    conn = get_db_connection()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()
    conn.close()
    return render_template('list_racks.html', racks=racks)

@app.route('/add_rack', methods=('GET', 'POST'))
@admin_required
def add_rack():
    """إضافة راك جديد."""
    if request.method == 'POST':
        rack_name = request.form['name'].strip()
        if not rack_name:
            flash('اسم الراك مطلوب!', 'error')
        else:
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO racks (name) VALUES (?)', (rack_name,))
                conn.commit()
                flash(f'تم إضافة الراك "{rack_name}" بنجاح!', 'success')
                return redirect(url_for('list_racks'))
            except sqlite3.IntegrityError:
                flash(f'الراك "{rack_name}" موجود بالفعل. يرجى اختيار اسم فريد.', 'error')
            finally:
                conn.close()
    return render_template('add_rack.html')

@app.route('/edit_rack/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_rack(id):
    """تعديل راك موجود."""
    conn = get_db_connection()
    rack = conn.execute('SELECT * FROM racks WHERE id = ?', (id,)).fetchone()

    if rack is None:
        flash('الراك غير موجود.', 'error')
        conn.close()
        return redirect(url_for('list_racks'))

    if request.method == 'POST':
        new_name = request.form['name'].strip()
        if not new_name:
            flash('اسم الراك مطلوب!', 'error')
        else:
            try:
                existing_rack = conn.execute('SELECT id FROM racks WHERE name = ? AND id != ?',
                                                (new_name, id)).fetchone()
                if existing_rack:
                    flash(f'الراك "{new_name}" موجود بالفعل.', 'error')
                else:
                    conn.execute('UPDATE racks SET name = ? WHERE id = ?', (new_name, id))
                    conn.commit()
                    flash('تم تحديث الراك بنجاح!', 'success')
                    return redirect(url_for('list_racks'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث الراك: {e}', 'error')
            finally:
                conn.close()
    else:
        conn.close()
    return render_template('edit_rack.html', rack=rack)

@app.route('/delete_rack/<int:id>', methods=('POST',))
@admin_required
def delete_rack(id):
    """حذف راك."""
    conn = get_db_connection()
    rack = conn.execute('SELECT name FROM racks WHERE id = ?', (id,)).fetchone()

    if rack is None:
        flash('الراك غير موجود للحذف.', 'error')
    else:
        try:
            # التحقق مما إذا كانت هناك سلات مرتبطة بهذا الراك
            bins_count = conn.execute('SELECT COUNT(*) FROM bins WHERE rack_id = ?', (id,)).fetchone()[0]
            if bins_count > 0:
                flash(f'لا يمكن حذف الراك "{rack["name"]}" لوجود {bins_count} سلة مرتبطة به. يرجى حذف السلات أولاً.', 'error')
            else:
                conn.execute('DELETE FROM racks WHERE id = ?', (id,))
                conn.commit()
                flash(f'تم حذف الراك "{rack["name"]}" بنجاح!', 'success')
        except Exception as e:
            flash(f'حدث خطأ أثناء حذف الراك: {e}', 'error')
        finally:
            conn.close()
    return redirect(url_for('list_racks'))

@app.route('/bins')
@admin_required
def list_bins():
    """عرض قائمة بجميع السلات."""
    conn = get_db_connection()
    bins = conn.execute('SELECT b.*, r.name as rack_name FROM bins b JOIN racks r ON b.rack_id = r.id ORDER BY r.name, b.name').fetchall()
    conn.close()
    return render_template('list_bins.html', bins=bins)

@app.route('/add_bin', methods=('GET', 'POST'))
@admin_required
def add_bin():
    """إضافة سلة جديدة."""
    conn = get_db_connection()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()

    if request.method == 'POST':
        bin_name = request.form['name'].strip()
        rack_id = request.form['rack_id'].strip()
        if not bin_name:
            flash('اسم السلة مطلوب!', 'error')
        elif not rack_id:
            flash('الراك مطلوب!', 'error')
        else:
            try:
                conn.execute('INSERT INTO bins (name, rack_id) VALUES (?, ?)', (bin_name, rack_id))
                conn.commit()
                flash(f'تم إضافة السلة "{bin_name}" بنجاح في الراك "{conn.execute("SELECT name FROM racks WHERE id = ?", (rack_id,)).fetchone()["name"]}"!', 'success')
                return redirect(url_for('list_bins'))
            except sqlite3.IntegrityError:
                flash(f'السلة "{bin_name}" موجودة بالفعل في الراك المحدد. يرجى اختيار اسم فريد أو راك آخر.', 'error')
            except Exception as e:
                flash(f'حدث خطأ غير متوقع: {e}', 'error')
            finally:
                conn.close()
            return render_template('add_bin.html', racks=racks)
    conn.close()
    return render_template('add_bin.html', racks=racks)

@app.route('/edit_bin/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_bin(id):
    """تعديل سلة موجودة."""
    conn = get_db_connection()
    bin_data = conn.execute('SELECT * FROM bins WHERE id = ?', (id,)).fetchone()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()

    if bin_data is None:
        flash('السلة غير موجودة.', 'error')
        conn.close()
        return redirect(url_for('list_bins'))

    if request.method == 'POST':
        new_name = request.form['name'].strip()
        new_rack_id = request.form['rack_id'].strip()
        if not new_name:
            flash('اسم السلة مطلوب!', 'error')
        elif not new_rack_id:
            flash('الراك مطلوب!', 'error')
        else:
            try:
                # التحقق من تكرار الاسم داخل الراك الجديد
                existing_bin = conn.execute('SELECT id FROM bins WHERE name = ? AND rack_id = ? AND id != ?',
                                            (new_name, new_rack_id, id)).fetchone()
                if existing_bin:
                    flash(f'السلة "{new_name}" موجودة بالفعل في الراك المحدد.', 'error')
                else:
                    conn.execute('UPDATE bins SET name = ?, rack_id = ? WHERE id = ?', (new_name, new_rack_id, id))
                    conn.commit()
                    flash('تم تحديث السلة بنجاح!', 'success')
                    return redirect(url_for('list_bins'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث السلة: {e}', 'error')
            finally:
                conn.close()
            return render_template('edit_bin.html', bin_data=bin_data, racks=racks)
    else:
        conn.close()
    return render_template('edit_bin.html', bin_data=bin_data, racks=racks)

@app.route('/delete_bin/<int:id>', methods=('POST',))
@admin_required
def delete_bin(id):
    """حذف سلة."""
    conn = get_db_connection()
    bin_data = conn.execute('SELECT b.name, r.name as rack_name FROM bins b JOIN racks r ON b.rack_id = r.id WHERE b.id = ?', (id,)).fetchone()

    if bin_data is None:
        flash('السلة غير موجودة للحذف.', 'error')
    else:
        try:
            products_count = conn.execute('SELECT COUNT(*) FROM products WHERE bin_id = ?', (id,)).fetchone()[0]
            if products_count > 0:
                flash(f'لا يمكن حذف السلة "{bin_data["name"]}" في الراك "{bin_data["rack_name"]}" لوجود {products_count} منتج مرتبط بها. يرجى تعديل المنتجات أولاً.', 'error')
            else:
                conn.execute('DELETE FROM bins WHERE id = ?', (id,))
                conn.commit()
                flash(f'تم حذف السلة "{bin_data["name"]}" بنجاح!', 'success')
        except Exception as e:
            flash(f'حدث خطأ أثناء حذف السلة: {e}', 'error')
        finally:
            conn.close()
    return redirect(url_for('list_bins'))

@app.route('/api/get_bins_by_rack/<int:rack_id>')
@login_required
def get_bins_by_rack(rack_id):
    """API endpoint لجلب السلات بناءً على الراك المحدد."""
    conn = get_db_connection()
    bins = conn.execute('SELECT id, name FROM bins WHERE rack_id = ? ORDER BY name', (rack_id,)).fetchall()
    conn.close()
    return jsonify([dict(b) for b in bins])


# -------------------- مسارات إدارة المخزون (تحديثات شاملة) --------------------

@app.route('/')
@login_required
def index():
    """لوحة التحكم (Dashboard) - الصفحة الرئيسية بعد تسجيل الدخول."""
    conn = get_db_connection()
    
    total_products = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    total_quantity = conn.execute('SELECT SUM(quantity) FROM products').fetchone()[0] or 0
    low_stock_threshold = 10
    low_stock_products = conn.execute('SELECT p.*, c.name as category_name, r.name as rack_name, b.name as bin_name FROM products p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id WHERE p.quantity <= ? ORDER BY p.product_code', (low_stock_threshold,)).fetchall()

    # بيانات للرسوم البيانية (توزيع الكميات حسب الفئة)
    category_quantities_data = conn.execute('SELECT c.name, SUM(p.quantity) FROM products p JOIN categories c ON p.category_id = c.id GROUP BY c.name').fetchall()
    category_labels = [row[0] for row in category_quantities_data]
    category_data = [row[1] for row in category_quantities_data]

    # بيانات للرسوم البيانية (أكثر المنتجات كمية)
    top_products_by_quantity_data = conn.execute('SELECT product_code, quantity FROM products ORDER BY quantity DESC LIMIT 5').fetchall()
    top_product_labels = [row[0] for row in top_products_by_quantity_data]
    top_product_data = [row[1] for row in top_products_by_quantity_data]

    # مؤشرات الأداء الرئيسية (KPIs) - قيم افتراضية حالياً
    stock_accuracy = "N/A" # يتطلب بيانات جرد فعلية ومسجلة لمقارنتها
    avg_inventory_age = "N/A" # يتطلب تاريخ إضافة لكل منتج وتتبع السحب
    
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
                           stock_accuracy=stock_accuracy,
                           avg_inventory_age=avg_inventory_age)

@app.route('/products')
@login_required
def list_products():
    """عرض قائمة بجميع المنتجات مع الكميات والفئات والمواقع."""
    conn = get_db_connection()
    # انضمام إلى جداول racks و bins لجلب الأسماء
    products = conn.execute('SELECT p.*, c.name as category_name, r.name as rack_name, b.name as bin_name FROM products p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id ORDER BY p.product_code').fetchall()
    conn.close()
    return render_template('list_products.html', products=products)

@app.route('/add_product', methods=('GET', 'POST'))
@login_required
def add_product():
    """إضافة منتج جديد إلى المخزون مع اختيار الراك والسلة والفئة."""
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories ORDER BY name').fetchall()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()
    
    if request.method == 'POST':
        product_code = request.form['product_code'].upper().strip()
        rack_id = request.form['rack_id'].strip() if request.form['rack_id'] else None
        bin_id = request.form['bin_id'].strip() if request.form['bin_id'] else None # قد يكون فارغاً إذا لم يتم اختيار سلة
        quantity_str = request.form['quantity'].strip()
        category_id = request.form['category_id'].strip() if request.form['category_id'] else None

        # التحقق من صحة الإدخالات
        if not product_code:
            flash('رمز المنتج مطلوب!', 'error')
        elif not rack_id:
            flash('الراك مطلوب!', 'error')
        elif not bin_id:
            flash('السلة مطلوبة!', 'error') # تأكد أن السلة تم اختيارها
        elif not quantity_str.isdigit() or int(quantity_str) < 0:
            flash('الكمية يجب أن تكون رقمًا صحيحًا وموجبًا أو صفرًا!', 'error')
        elif not category_id:
            flash('الفئة مطلوبة!', 'error')
        else:
            quantity = int(quantity_str)
            try:
                conn.execute('INSERT INTO products (product_code, rack_id, bin_id, quantity, category_id) VALUES (?, ?, ?, ?, ?)',
                             (product_code, rack_id, bin_id, quantity, category_id))
                conn.commit()
                # الحصول على ID المنتج المضاف حديثاً لتسجيل الحركة
                product_id = conn.execute('SELECT id FROM products WHERE product_code = ?', (product_code,)).fetchone()[0]
                
                # جلب الأسماء لتسجيل الحركة بالتفصيل
                rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (rack_id,)).fetchone()['name']
                bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (bin_id,)).fetchone()['name']
                category_name = conn.execute('SELECT name FROM categories WHERE id = ?', (category_id,)).fetchone()['name']

                log_details = f"تم إضافة المنتج. الكمية: {quantity}, الراك: {rack_name}, السلة: {bin_name}, الفئة: {category_name}"
                log_transaction(product_id, g.user['id'], 'add_product', log_details)

                flash('تم إضافة المنتج بنجاح!', 'success')
                return redirect(url_for('list_products'))
            except sqlite3.IntegrityError:
                flash(f'رمز المنتج "{product_code}" موجود بالفعل. يرجى استخدام رمز فريد.', 'error')
            except Exception as e:
                flash(f'حدث خطأ غير متوقع: {e}', 'error')
            finally:
                conn.close()
            # إذا حدث خطأ، أعد عرض الفورم مع الفئات والراكات
            return render_template('add_product.html', categories=categories, racks=racks)
    conn.close() # إغلاق الاتصال إذا كان طلب GET
    return render_template('add_product.html', categories=categories, racks=racks)

@app.route('/edit_product/<int:id>', methods=('GET', 'POST'))
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
        return redirect(url_for('list_products'))

    # جلب السلات المرتبطة بالراك الحالي للمنتج عند تحميل الصفحة
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
                # التحقق من عدم وجود رمز منتج مكرر لمنتج آخر
                existing_product = conn.execute('SELECT id FROM products WHERE product_code = ? AND id != ?',
                                                (product_code, id)).fetchone()
                if existing_product:
                    flash(f'رمز المنتج "{product_code}" موجود بالفعل لمنتج آخر.', 'error')
                else:
                    old_product_data = dict(product) # حفظ البيانات القديمة للتسجيل

                    conn.execute('UPDATE products SET product_code = ?, rack_id = ?, bin_id = ?, quantity = ?, category_id = ? WHERE id = ?',
                                 (product_code, rack_id, bin_id, quantity, category_id, id))
                    conn.commit()

                    # جلب الأسماء القديمة والجديدة لتسجيل الحركة بالتفصيل
                    old_rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (old_product_data['rack_id'],)).fetchone()['name'] if old_product_data['rack_id'] else 'N/A'
                    old_bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (old_product_data['bin_id'],)).fetchone()['name'] if old_product_data['bin_id'] else 'N/A'
                    old_category_name = conn.execute('SELECT name FROM categories WHERE id = ?', (old_product_data['category_id'],)).fetchone()['name'] if old_product_data['category_id'] else 'N/A'

                    new_rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (rack_id,)).fetchone()['name']
                    new_bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (bin_id,)).fetchone()['name']
                    new_category_name = conn.execute('SELECT name FROM categories WHERE id = ?', (category_id,)).fetchone()['name']

                    log_details = (f"تم تحديث المنتج من: "
                                   f"رمز: {old_product_data['product_code']}, راك: {old_rack_name}, سلة: {old_bin_name}, "
                                   f"كمية: {old_product_data['quantity']}, فئة: {old_category_name}. "
                                   f"إلى: رمز: {product_code}, راك: {new_rack_name}, سلة: {new_bin_name}, كمية: {quantity}, فئة: {new_category_name}.")
                    log_transaction(id, g.user['id'], 'edit_product', log_details)

                    flash('تم تحديث المنتج بنجاح!', 'success')
                    return redirect(url_for('list_products'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث المنتج: {e}', 'error')
            finally:
                conn.close()
            return render_template('edit_product.html', product=product, categories=categories, racks=racks, current_rack_bins=current_rack_bins)
    else: # If GET request, close connection after fetching product and categories
        conn.close()
    return render_template('edit_product.html', product=product, categories=categories, racks=racks, current_rack_bins=current_rack_bins)

@app.route('/update_quantity/<int:id>', methods=('POST',))
@login_required
def update_quantity(id):
    """تحديث الكمية (زيادة/نقصان) لمنتج معين."""
    action = request.form.get('action')
    change_amount_str = request.form.get('change_amount').strip()

    if not change_amount_str or not change_amount_str.isdigit() or int(change_amount_str) <= 0:
        flash('يرجى إدخال قيمة صحيحة وموجبة للتغيير.', 'error')
        return redirect(url_for('list_products'))

    change_amount = int(change_amount_str)
    conn = get_db_connection()
    product = conn.execute('SELECT product_code, quantity, rack_id, bin_id FROM products WHERE id = ?', (id,)).fetchone()

    if product is None:
        flash('المنتج غير موجود لتحديث الكمية.', 'error')
        conn.close()
        return redirect(url_for('list_products'))

    current_quantity = product['quantity']
    new_quantity = current_quantity
    log_action_type = ''
    log_details = ''

    # جلب أسماء الراك والسلة لتسجيل الحركة
    rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (product['rack_id'],)).fetchone()['name'] if product['rack_id'] else 'N/A'
    bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (product['bin_id'],)).fetchone()['name'] if product['bin_id'] else 'N/A'

    if action == 'increase':
        new_quantity = current_quantity + change_amount
        log_action_type = 'increase_quantity'
        log_details = f"تمت زيادة الكمية بمقدار {change_amount} من {current_quantity} إلى {new_quantity} لـ {product['product_code']} في الراك {rack_name}، السلة {bin_name}."
        flash(f'تمت زيادة الكمية بمقدار {change_amount} لـ {product["product_code"]}. الكمية الجديدة: {new_quantity}.', 'success')
    elif action == 'decrease':
        if current_quantity < change_amount:
            flash(f'لا يمكن إنقاص الكمية بمقدار {change_amount}. الكمية الحالية هي {current_quantity} فقط.', 'error')
            conn.close()
            return redirect(url_for('list_products'))
        new_quantity = current_quantity - change_amount
        log_action_type = 'decrease_quantity'
        log_details = f"تم إنقاص الكمية بمقدار {change_amount} من {current_quantity} إلى {new_quantity} لـ {product['product_code']} في الراك {rack_name}، السلة {bin_name}."
        flash(f'تم إنقاص الكمية بمقدار {change_amount} لـ {product["product_code"]}. الكمية الجديدة: {new_quantity}.', 'success')
    else:
        flash('إجراء غير صالح لتحديث الكمية.', 'error')
        conn.close()
        return redirect(url_for('list_products'))

    try:
        conn.execute('UPDATE products SET quantity = ? WHERE id = ?', (new_quantity, id))
        conn.commit()
        log_transaction(id, g.user['id'], log_action_type, log_details)
    except Exception as e:
        flash(f'حدث خطأ أثناء تحديث الكمية: {e}', 'error')
    finally:
        conn.close()
    return redirect(url_for('list_products'))


@app.route('/delete_product/<int:id>', methods=('POST',))
@login_required
def delete_product(id):
    """حذف منتج من المخزون."""
    conn = get_db_connection()
    product = conn.execute('SELECT product_code, rack_id, bin_id FROM products WHERE id = ?', (id,)).fetchone()

    if product is None:
        flash('المنتج غير موجود للحذف.', 'error')
    else:
        try:
            # جلب أسماء الراك والسلة لتسجيل الحركة
            rack_name = conn.execute('SELECT name FROM racks WHERE id = ?', (product['rack_id'],)).fetchone()['name'] if product['rack_id'] else 'N/A'
            bin_name = conn.execute('SELECT name FROM bins WHERE id = ?', (product['bin_id'],)).fetchone()['name'] if product['bin_id'] else 'N/A'
            
            conn.execute('DELETE FROM products WHERE id = ?', (id,))
            conn.commit()
            log_details = f"تم حذف المنتج: {product['product_code']} من الراك {rack_name}، السلة {bin_name}."
            log_transaction(id, g.user['id'], 'delete_product', log_details)
            flash(f'تم حذف المنتج "{product["product_code"]}" بنجاح!', 'success')
        except Exception as e:
            flash(f'حدث خطأ أثناء حذف المنتج: {e}', 'error')
        finally:
            conn.close()
    return redirect(url_for('list_products'))

@app.route('/search', methods=('GET', 'POST'))
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

@app.route('/low_stock_report')
@login_required
def low_stock_report():
    """تقرير بالمنتجات ذات الكمية المنخفضة."""
    conn = get_db_connection()
    low_stock_threshold = 10 # يمكن جعلها قيمة قابلة للتكوين لاحقاً
    low_stock_products = conn.execute('SELECT p.*, c.name as category_name, r.name as rack_name, b.name as bin_name FROM products p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id WHERE p.quantity <= ? ORDER BY p.product_code', (low_stock_threshold,)).fetchall()
    conn.close()
    return render_template('low_stock_report.html', low_stock_products=low_stock_products, low_stock_threshold=low_stock_threshold)

@app.route('/transactions')
@login_required
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


# مسار لمحاكاة المسح الضوئي (Ajax Request)
@app.route('/scan_product', methods=['POST'])
@login_required
def scan_product():
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
            'rack': product['rack_name'], # استخدام الاسم بدلاً من ID
            'bin': product['bin_name'],   # استخدام الاسم بدلاً من ID
            'quantity': product['quantity'],
            'category': product['category_name'],
            'message': f'تم العثور على المنتج: {product["product_code"]} في الراك {product["rack_name"]}، السلة {product["bin_name"]} (الكمية: {product["quantity"]}).'
        })
    else:
        return jsonify({'found': False, 'message': f'لم يتم العثور على المنتج برمز: {product_code}.'})

# -------------------- مسارات الجرد الدوري (Cycle Counting) --------------------

@app.route('/cycle_count_start', methods=('GET', 'POST'))
@login_required
def cycle_count_start():
    """صفحة اختيار الراك لبدء الجرد."""
    conn = get_db_connection()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()
    conn.close()
    return render_template('cycle_count_start.html', racks=racks)

@app.route('/cycle_count/<int:rack_id>', methods=('GET', 'POST'))
@login_required
def cycle_count(rack_id):
    """صفحة الجرد الفعلي لراك معين."""
    conn = get_db_connection()
    rack_info = conn.execute('SELECT * FROM racks WHERE id = ?', (rack_id,)).fetchone()
    if rack_info is None:
        flash('الراك غير موجود.', 'error')
        conn.close()
        return redirect(url_for('cycle_count_start'))

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
        # معالجة بيانات الجرد المرسلة من النموذج
        for product in products_in_rack:
            product_id = product['id']
            # استخدام .get() لتجنب KeyError إذا لم يكن الحقل موجوداً (مثلاً لم يتم إدخال قيمة)
            counted_quantity_str = request.form.get(f'counted_quantity_{product_id}', '').strip()
            
            original_quantity = product['quantity']

            if counted_quantity_str and counted_quantity_str.isdigit():
                counted_quantity = int(counted_quantity_str)
            else:
                counted_quantity = original_quantity # إذا لم يتم إدخال قيمة صالحة، افترض نفس الكمية الأصلية

            if counted_quantity != original_quantity:
                # تحديث الكمية في قاعدة البيانات
                conn.execute('UPDATE products SET quantity = ? WHERE id = ?', (counted_quantity, product_id))
                conn.commit()

                # تسجيل الحركة في سجل الحركات
                log_details = f"جرد: تم تغيير الكمية من {original_quantity} إلى {counted_quantity} لـ {product['product_code']} في الراك {rack_info['name']}، السلة {product['bin_name']}. فرق: {counted_quantity - original_quantity}"
                log_transaction(product_id, g.user['id'], 'cycle_count', log_details)
                flash(f'تم تحديث كمية المنتج {product["product_code"]} إلى {counted_quantity} (كانت {original_quantity}).', 'success')
            
        flash(f'تم حفظ نتائج الجرد للراك "{rack_info["name"]}" بنجاح!', 'success')
        conn.close()
        return redirect(url_for('list_products')) # العودة لقائمة المنتجات أو تقرير الجرد
    
    conn.close()
    return render_template('cycle_count.html', rack_info=rack_info, products_in_rack=products_in_rack)

# -------------------- مسارات الاستيراد والتصدير --------------------

@app.route('/export_products_csv')
@admin_required # عادة ما يكون التصدير للمدراء فقط
def export_products_csv():
    """تصدير جميع المنتجات إلى ملف CSV."""
    conn = get_db_connection()
    # جلب جميع المنتجات مع أسماء الراكات والسلات والفئات
    products = conn.execute('SELECT p.product_code, r.name as rack_name, b.name as bin_name, p.quantity, c.name as category_name FROM products p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN racks r ON p.rack_id = r.id LEFT JOIN bins b ON p.bin_id = b.id').fetchall()
    conn.close()

    if not products:
        flash('لا توجد منتجات لتصديرها.', 'info')
        return redirect(url_for('list_products'))

    # تحويل البيانات إلى DataFrame ثم إلى CSV
    df = pd.DataFrame([dict(row) for row in products])
    # إعادة تسمية الأعمدة لتكون واضحة في ملف CSV المصدر
    df.rename(columns={'rack_name': 'rack', 'bin_name': 'bin', 'category_name': 'category'}, inplace=True)
    
    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8-sig') # utf-8-sig لدعم اللغة العربية في Excel
    output.seek(0) # العودة إلى بداية الكائن

    return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name='inventory_products.csv')

@app.route('/import_products_csv', methods=('GET', 'POST'))
@admin_required # عادة ما يكون الاستيراد للمدراء فقط
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
                # قراءة الملف باستخدام pandas
                df = pd.read_csv(file, encoding='utf-8')
                # التأكد من وجود الأعمدة المطلوبة
                required_columns = ['product_code', 'rack', 'bin', 'quantity', 'category']
                if not all(col in df.columns for col in required_columns):
                    flash(f'الملف يجب أن يحتوي على الأعمدة التالية: {", ".join(required_columns)}', 'error')
                    return render_template('import_products_csv.html')

                conn = get_db_connection()
                imported_count = 0
                updated_count = 0
                skipped_count = 0 # للمنتجات التي قد يتم تخطيها بسبب أخطاء

                for index, row in df.iterrows():
                    try:
                        product_code = str(row['product_code']).upper().strip()
                        rack_name = str(row['rack']).upper().strip()
                        bin_name = str(row['bin']).upper().strip()
                        quantity = int(row['quantity']) if pd.notna(row['quantity']) and str(row['quantity']).isdigit() else 0
                        category_name = str(row['category']).strip() if pd.notna(row['category']) else 'عام'

                        # الحصول على category_id أو إنشاء فئة جديدة إذا لم تكن موجودة
                        category = conn.execute('SELECT id FROM categories WHERE name = ?', (category_name,)).fetchone()
                        if category:
                            category_id = category['id']
                        else:
                            conn.execute('INSERT INTO categories (name) VALUES (?)', (category_name,))
                            conn.commit() # تأكيد إنشاء الفئة قبل استخدام معرفها
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
                            # تحديث المنتج الموجود
                            product_id = existing_product['id']
                            old_quantity = existing_product['quantity']
                            conn.execute('UPDATE products SET rack_id = ?, bin_id = ?, quantity = ?, category_id = ? WHERE id = ?',
                                         (rack_id, bin_id, quantity, category_id, product_id))
                            log_details = f"تم تحديث المنتج من CSV. الكمية من {old_quantity} إلى {quantity}، الراك: {rack_name}, السلة: {bin_name}, الفئة: {category_name}"
                            log_transaction(product_id, g.user['id'], 'import_update_product', log_details)
                            updated_count += 1
                        else:
                            # إضافة منتج جديد
                            conn.execute('INSERT INTO products (product_code, rack_id, bin_id, quantity, category_id) VALUES (?, ?, ?, ?, ?)',
                                         (product_code, rack_id, bin_id, quantity, category_id))
                            # الحصول على ID المنتج المضاف حديثاً
                            product_id = conn.execute('SELECT id FROM products WHERE product_code = ?', (product_code,)).fetchone()[0]
                            log_details = f"تم إضافة المنتج من CSV. الكمية: {quantity}, الراك: {rack_name}, السلة: {bin_name}, الفئة: {category_name}"
                            log_transaction(product_id, g.user['id'], 'import_add_product', log_details)
                            imported_count += 1
                    except Exception as row_e:
                        flash(f'تخطي الصف رقم {index + 2} (السطر في الملف) بسبب خطأ: {row_e}', 'warning')
                        skipped_count += 1
                        continue # تخطي هذا الصف ومتابعة البقية
                conn.commit()
                conn.close()
                flash(f'تم استيراد {imported_count} منتج جديد وتحديث {updated_count} منتج موجود بنجاح! تم تخطي {skipped_count} صفاً بسبب الأخطاء.', 'success')
                return redirect(url_for('list_products'))

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

# ... (باقي الكود في app.py قبل دالة generate_qrcode) ...

@app.route('/generate_qrcode/<path:product_code>') # تغيير <product_code> إلى <path:product_code> للسماح بالرموز التي تحتوي على شرطات مائلة
@login_required
def generate_qrcode(product_code):
    """نقطة نهاية API لتوليد QR Code لرمز منتج وإرجاعه كصورة PNG مرمزة بـ base64."""
    try:
        qr_code = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr_code.add_data(product_code)
        qr_code.make(fit=True)

        img = qr_code.make_image(fill_color="black", back_color="white")
        
        # حفظ الصورة في الذاكرة المؤقتة بتنسيق PNG
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        
        # ترميز الصورة لـ base64 لتضمينها مباشرة في HTML
        encoded_image = b64encode(buffer.getvalue()).decode('ascii')
        return jsonify({'image_base64': encoded_image})
    except Exception as e:
        print(f"Error generating QR code for {product_code}: {e}")
        return jsonify({'error': str(e), 'message': 'فشل في توليد رمز QR.'}), 500

# ... (باقي الكود في app.py بعد دالة generate_qrcode) ...

@app.route('/print_barcodes')
@login_required
def print_barcodes():
    """صفحة لعرض جميع المنتجات مع أزرار لتوليد وطباعة الباركود/QR Code."""
    conn = get_db_connection()
    products = conn.execute('SELECT product_code FROM products ORDER BY product_code').fetchall()
    conn.close()

    products_list = [{'product_code': p['product_code']} for p in products]

    return render_template('print_barcodes.html', products=products_list)


if __name__ == '__main__':
    app.run(debug=True) # debug=True يسمح بالتحديث التلقائي عند التغيير (للتطوير فقط)
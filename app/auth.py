from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g
import sqlite3
import hashlib
import uuid # لاستخدامه في توليد مفاتيح API

# استيراد دالة الاتصال بقاعدة البيانات والمزخرفات من __init__.py
from .__init__ import get_db_connection, login_required, admin_required, permission_required 

# إنشاء المخطط الأزرق لقسم المصادقة
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# -------------------- مسارات المصادقة --------------------

@auth_bp.route('/login', methods=('GET', 'POST'))
def login():
    """صفحة تسجيل الدخول."""
    if g.user:
        return redirect(url_for('main.index'))

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
            session.permanent = True
            flash(f'مرحباً {user["username"]}! تم تسجيل الدخول بنجاح.', 'success')
            return redirect(url_for('main.index'))
        flash(error, 'error')
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    """تسجيل الخروج من الحساب."""
    session.clear()
    flash('تم تسجيل الخروج بنجاح.', 'info')
    return redirect(url_for('auth.login'))

# -------------------- مسارات إدارة المستخدمين (للمدراء فقط) --------------------

@auth_bp.route('/users')
@admin_required # يتطلب صلاحية المدير لإدارة المستخدمين
def list_users():
    """عرض قائمة بجميع المستخدمين (للمدراء فقط)."""
    conn = get_db_connection()
    # جلب المستخدمين مع أسماء أدوارهم ومفاتيح API الخاصة بهم
    users = conn.execute('SELECT u.id, u.username, r.name as role_name, u.api_key FROM users u JOIN roles r ON u.role_id = r.id ORDER BY u.username').fetchall()
    conn.close()
    return render_template('list_users.html', users=users)

@auth_bp.route('/add_user', methods=('GET', 'POST'))
@admin_required
def add_user():
    """إضافة مستخدم جديد (للمدراء فقط)."""
    conn = get_db_connection()
    roles = conn.execute('SELECT * FROM roles ORDER BY name').fetchall()
    conn.close()

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        role_id = request.form['role_id'].strip()
        generate_api_key = 'generate_api_key' in request.form # التحقق مما إذا تم طلب توليد مفتاح API
        
        api_key = None
        if generate_api_key:
            api_key = str(uuid.uuid4()) # توليد مفتاح API فريد

        error = None

        if not username:
            error = 'اسم المستخدم مطلوب!'
        elif not password:
            error = 'كلمة المرور مطلوبة!'
        elif len(password) < 6:
            error = 'كلمة المرور يجب أن لا تقل عن 6 أحرف!'
        elif not role_id:
            error = 'الدور مطلوب!'

        if error is None:
            conn = get_db_connection()
            try:
                hashed_password = hashlib.sha256(password.encode()).hexdigest()
                conn.execute('INSERT INTO users (username, password_hash, role_id, api_key) VALUES (?, ?, ?, ?)',
                             (username, hashed_password, role_id, api_key))
                conn.commit()
                
                flash_message = f'تم إضافة المستخدم "{username}" بنجاح!'
                if api_key:
                    flash_message += f' مفتاح API الخاص به هو: {api_key}. احفظه جيداً فلن يظهر مرة أخرى!'
                    flash(flash_message, 'success')
                else:
                    flash(flash_message, 'success')
                
                return redirect(url_for('auth.list_users'))
            except sqlite3.IntegrityError:
                flash(f'اسم المستخدم "{username}" موجود بالفعل. يرجى اختيار اسم آخر.', 'error')
            except Exception as e:
                flash(f'حدث خطأ غير متوقع: {e}', 'error')
            finally:
                conn.close()
        flash(error, 'error')
    return render_template('add_user.html', roles=roles)

@auth_bp.route('/edit_user/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_user(id):
    """تعديل مستخدم (للمدراء فقط)."""
    conn = get_db_connection()
    user = conn.execute('SELECT id, username, role_id, api_key FROM users WHERE id = ?', (id,)).fetchone() # جلب مفتاح API أيضاً
    roles = conn.execute('SELECT * FROM roles ORDER BY name').fetchall()

    if user is None:
        flash('المستخدم غير موجود.', 'error')
        conn.close()
        return redirect(url_for('auth.list_users'))

    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        role_id = request.form['role_id'].strip()
        action = request.form.get('api_key_action') # زر الإجراء الخاص بـ API Key

        api_key = user['api_key'] # البدء بمفتاح API الموجود حالياً
        
        if action == 'generate':
            api_key = str(uuid.uuid4())
            flash(f'تم توليد مفتاح API جديد للمستخدم {username}: {api_key}. احفظه جيداً فلن يظهر مرة أخرى!', 'success')
        elif action == 'revoke':
            api_key = None
            flash(f'تم إلغاء مفتاح API للمستخدم {username}.', 'info')


        error = None

        if not username:
            error = 'اسم المستخدم مطلوب!'
        elif not role_id:
            error = 'الدور مطلوب!'

        if error is None:
            try:
                existing_user = conn.execute('SELECT id FROM users WHERE username = ? AND id != ?',
                                             (username, id)).fetchone()
                if existing_user:
                    flash(f'اسم المستخدم "{username}" موجود بالفعل لمستخدم آخر.', 'error')
                else:
                    update_query = 'UPDATE users SET username = ?, role_id = ?, api_key = ?'
                    params = [username, role_id, api_key]
                    if password:
                        if len(password) < 6:
                            flash('كلمة المرور الجديدة يجب أن لا تقل عن 6 أحرف!', 'error')
                            return render_template('edit_user.html', user=user, roles=roles)
                        hashed_password = hashlib.sha256(password.encode()).hexdigest()
                        update_query += ', password_hash = ?'
                        params.append(hashed_password)

                    update_query += ' WHERE id = ?'
                    params.append(id)

                    conn.execute(update_query, tuple(params))
                    conn.commit()
                    flash('تم تحديث المستخدم بنجاح!', 'success')
                    return redirect(url_for('auth.list_users'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث المستخدم: {e}', 'error')
            finally:
                conn.close()
        flash(error, 'error')
    else:
        conn.close()
    return render_template('edit_user.html', user=user, roles=roles)

@auth_bp.route('/delete_user/<int:id>', methods=('POST',))
@admin_required
def delete_user(id):
    """حذف مستخدم (للمدراء فقط)."""
    if id == g.user['id']:
        flash('لا يمكنك حذف حسابك الخاص أثناء تسجيل الدخول!', 'error')
        return redirect(url_for('auth.list_users'))

    conn = get_db_connection()
    user = conn.execute('SELECT username FROM users WHERE id = ?', (id,)).fetchone()

    if user is None:
        flash('المستخدم غير موجود للحذف.', 'error')
    else:
        try:
            transactions_count = conn.execute('SELECT COUNT(*) FROM transactions WHERE user_id = ?', (id,)).fetchone()[0]
            product_history_count = conn.execute('SELECT COUNT(*) FROM product_history WHERE user_id = ?', (id,)).fetchone()[0]

            if transactions_count > 0 or product_history_count > 0:
                flash(f'لا يمكن حذف المستخدم "{user["username"]}" لوجود حركات مسجلة أو تغييرات في سجل التدقيق باسمه.', 'error')
            else:
                conn.execute('DELETE FROM users WHERE id = ?', (id,))
                conn.commit()
                flash(f'تم حذف المستخدم "{user["username"]}" بنجاح!', 'success')
        except Exception as e:
            flash(f'حدث خطأ أثناء حذف المستخدم: {e}', 'error')
        finally:
            conn.close()
    return redirect(url_for('auth.list_users'))

# -------------------- مسارات إدارة الأدوار والصلاحيات (للمدراء فقط) --------------------

@auth_bp.route('/roles')
@admin_required
def list_roles():
    """عرض قائمة بجميع الأدوار مع صلاحياتها."""
    conn = get_db_connection()
    roles = conn.execute('SELECT * FROM roles ORDER BY name').fetchall()
    
    roles_with_permissions = []
    for role in roles:
        permissions = conn.execute('''
            SELECT p.id, p.name FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = ? ORDER BY p.name
        ''', (role['id'],)).fetchall()
        role_dict = dict(role)
        role_dict['permissions'] = [p['name'] for p in permissions]
        roles_with_permissions.append(role_dict)
    
    conn.close()
    return render_template('list_roles.html', roles=roles_with_permissions)

@auth_bp.route('/roles/add', methods=('GET', 'POST'))
@admin_required
def add_role():
    """إضافة دور جديد وتعيين صلاحياته."""
    conn = get_db_connection()
    all_permissions = conn.execute('SELECT * FROM permissions ORDER BY name').fetchall()
    conn.close()

    if request.method == 'POST':
        role_name = request.form['name'].strip()
        selected_permissions = request.form.getlist('permissions')
        error = None

        if not role_name:
            error = 'اسم الدور مطلوب!'
        
        if error is None:
            conn = get_db_connection()
            try:
                conn.execute('INSERT INTO roles (name) VALUES (?)', (role_name,))
                conn.commit()
                role_id = conn.execute('SELECT id FROM roles WHERE name = ?', (role_name,)).fetchone()[0]

                for perm_id in selected_permissions:
                    conn.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)',
                                 (role_id, perm_id))
                conn.commit()
                flash(f'تم إضافة الدور "{role_name}" بنجاح وتعيين الصلاحيات!', 'success')
                return redirect(url_for('auth.list_roles'))
            except sqlite3.IntegrityError:
                flash(f'الدور "{role_name}" موجود بالفعل. يرجى اختيار اسم فريد.', 'error')
            except Exception as e:
                flash(f'حدث خطأ غير متوقع: {e}', 'error')
            finally:
                conn.close()
        flash(error, 'error')
    return render_template('add_role.html', all_permissions=all_permissions)

@auth_bp.route('/roles/edit/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_role(id):
    """تعديل دور موجود وصلاحياته."""
    conn = get_db_connection()
    role = conn.execute('SELECT * FROM roles WHERE id = ?', (id,)).fetchone()
    all_permissions = conn.execute('SELECT * FROM permissions ORDER BY name').fetchall()
    
    if role is None:
        flash('الدور غير موجود.', 'error')
        conn.close()
        return redirect(url_for('auth.list_roles'))

    current_permissions = conn.execute('SELECT permission_id FROM role_permissions WHERE role_id = ?', (id,)).fetchall()
    current_permissions_ids = [p['permission_id'] for p in current_permissions]

    if request.method == 'POST':
        new_name = request.form['name'].strip()
        selected_permissions = request.form.getlist('permissions')
        error = None

        if not new_name:
            error = 'اسم الدور مطلوب!'
        
        if error is None:
            try:
                conn.execute('UPDATE roles SET name = ? WHERE id = ?', (new_name, id))
                
                conn.execute('DELETE FROM role_permissions WHERE role_id = ?', (id,))
                for perm_id in selected_permissions:
                    conn.execute('INSERT INTO role_permissions (role_id, permission_id) VALUES (?, ?)',
                                 (id, perm_id))
                conn.commit()
                flash('تم تحديث الدور بنجاح!', 'success')
                return redirect(url_for('auth.list_roles'))
            except sqlite3.IntegrityError:
                flash(f'الدور "{new_name}" موجود بالفعل. يرجى اختيار اسم فريد.', 'error')
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث الدور: {e}', 'error')
            finally:
                conn.close()
        flash(error, 'error')
    else:
        conn.close()
    return render_template('edit_role.html', role=role, all_permissions=all_permissions, current_permissions_ids=current_permissions_ids)

@auth_bp.route('/roles/delete/<int:id>', methods=('POST',))
@admin_required
def delete_role(id):
    """حذف دور."""
    conn = get_db_connection()
    role = conn.execute('SELECT name FROM roles WHERE id = ?', (id,)).fetchone()

    if role is None:
        flash('الدور غير موجود للحذف.', 'error')
    else:
        try:
            users_count = conn.execute('SELECT COUNT(*) FROM users WHERE role_id = ?', (id,)).fetchone()[0]
            if users_count > 0:
                flash(f'لا يمكن حذف الدور "{role["name"]}" لوجود {users_count} مستخدم مرتبط به. يرجى تعديل أدوار المستخدمين أولاً.', 'error')
            else:
                conn.execute('DELETE FROM roles WHERE id = ?', (id,))
                conn.commit()
                flash(f'تم حذف الدور "{role["name"]}" بنجاح!', 'success')
        except Exception as e:
            flash(f'حدث خطأ أثناء حذف الدور: {e}', 'error')
        finally:
            conn.close()
    return redirect(url_for('auth.list_roles'))
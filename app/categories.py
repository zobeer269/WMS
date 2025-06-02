from flask import Blueprint, render_template, request, redirect, url_for, flash
import sqlite3
from .auth import login_required, admin_required 
from .__init__ import get_db_connection

# إنشاء المخطط الأزرق لقسم الفئات
categories_bp = Blueprint('categories', __name__, url_prefix='/categories')

# -------------------- مسارات إدارة الفئات --------------------

@categories_bp.route('/')
@admin_required
def list_categories():
    """عرض قائمة بجميع الفئات."""
    conn = get_db_connection()
    categories = conn.execute('SELECT * FROM categories ORDER BY name').fetchall()
    conn.close()
    return render_template('list_categories.html', categories=categories)

@categories_bp.route('/add', methods=('GET', 'POST'))
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
                return redirect(url_for('categories.list_categories'))
            except sqlite3.IntegrityError:
                flash(f'الفئة "{category_name}" موجودة بالفعل. يرجى اختيار اسم فريد.', 'error')
            except Exception as e:
                flash(f'حدث خطأ غير متوقع: {e}', 'error')
            finally:
                conn.close()
    return render_template('add_category.html')

@categories_bp.route('/edit/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_category(id):
    """تعديل فئة موجودة."""
    conn = get_db_connection()
    category = conn.execute('SELECT * FROM categories WHERE id = ?', (id,)).fetchone()

    if category is None:
        flash('الفئة غير موجودة.', 'error')
        conn.close()
        return redirect(url_for('categories.list_categories'))

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
                    return redirect(url_for('categories.list_categories'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث الفئة: {e}', 'error')
            finally:
                conn.close()
    else:
        conn.close()
    return render_template('edit_category.html', category=category)

@categories_bp.route('/delete/<int:id>', methods=('POST',))
@admin_required
def delete_category(id):
    """حذف فئة."""
    conn = get_db_connection()
    category = conn.execute('SELECT name FROM categories WHERE id = ?', (id,)).fetchone()

    if category is None:
        flash('الفئة غير موجودة للحذف.', 'error')
    else:
        try:
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
    return redirect(url_for('categories.list_categories'))
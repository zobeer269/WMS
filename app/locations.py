from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from .auth import login_required, admin_required
from .__init__ import get_db_connection

# إنشاء المخطط الأزرق لقسم المواقع
locations_bp = Blueprint('locations', __name__, url_prefix='/locations')

# -------------------- مسارات إدارة الراكات --------------------

@locations_bp.route('/racks')
@admin_required
def list_racks():
    """عرض قائمة بجميع الراكات."""
    conn = get_db_connection()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()
    conn.close()
    return render_template('list_racks.html', racks=racks)

@locations_bp.route('/racks/add', methods=('GET', 'POST'))
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
                return redirect(url_for('locations.list_racks'))
            except sqlite3.IntegrityError:
                flash(f'الراك "{rack_name}" موجود بالفعل. يرجى اختيار اسم فريد.', 'error')
            except Exception as e:
                flash(f'حدث خطأ غير متوقع: {e}', 'error')
            finally:
                conn.close()
    return render_template('add_rack.html')

@locations_bp.route('/racks/edit/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_rack(id):
    """تعديل راك موجود."""
    conn = get_db_connection()
    rack = conn.execute('SELECT * FROM racks WHERE id = ?', (id,)).fetchone()

    if rack is None:
        flash('الراك غير موجود.', 'error')
        conn.close()
        return redirect(url_for('locations.list_racks'))

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
                    return redirect(url_for('locations.list_racks'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث الراك: {e}', 'error')
            finally:
                conn.close()
    else:
        conn.close()
    return render_template('edit_rack.html', rack=rack)

@locations_bp.route('/racks/delete/<int:id>', methods=('POST',))
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
    return redirect(url_for('locations.list_racks'))

# -------------------- مسارات إدارة السلات --------------------

@locations_bp.route('/bins')
@admin_required
def list_bins():
    """عرض قائمة بجميع السلات."""
    conn = get_db_connection()
    bins = conn.execute('SELECT b.*, r.name as rack_name FROM bins b JOIN racks r ON b.rack_id = r.id ORDER BY r.name, b.name').fetchall()
    conn.close()
    return render_template('list_bins.html', bins=bins)

@locations_bp.route('/bins/add', methods=('GET', 'POST'))
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
                return redirect(url_for('locations.list_bins'))
            except sqlite3.IntegrityError:
                flash(f'السلة "{bin_name}" موجودة بالفعل في الراك المحدد. يرجى اختيار اسم فريد أو راك آخر.', 'error')
            except Exception as e:
                flash(f'حدث خطأ غير متوقع: {e}', 'error')
            finally:
                conn.close()
            return render_template('add_bin.html', racks=racks)
    conn.close()
    return render_template('add_bin.html', racks=racks)

@locations_bp.route('/bins/edit/<int:id>', methods=('GET', 'POST'))
@admin_required
def edit_bin(id):
    """تعديل سلة موجودة."""
    conn = get_db_connection()
    bin_data = conn.execute('SELECT * FROM bins WHERE id = ?', (id,)).fetchone()
    racks = conn.execute('SELECT * FROM racks ORDER BY name').fetchall()

    if bin_data is None:
        flash('السلة غير موجودة.', 'error')
        conn.close()
        return redirect(url_for('locations.list_bins'))

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
                    return redirect(url_for('locations.list_bins'))
            except Exception as e:
                flash(f'حدث خطأ أثناء تحديث السلة: {e}', 'error')
            finally:
                conn.close()
            return render_template('edit_bin.html', bin_data=bin_data, racks=racks)
    else:
        conn.close()
    return render_template('edit_bin.html', bin_data=bin_data, racks=racks)

@locations_bp.route('/bins/delete/<int:id>', methods=('POST',))
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
    return redirect(url_for('locations.list_bins'))

@locations_bp.route('/api/get_bins_by_rack/<int:rack_id>')
@login_required
def get_bins_by_rack(rack_id):
    """API endpoint لجلب السلات بناءً على الراك المحدد."""
    conn = get_db_connection()
    bins = conn.execute('SELECT id, name FROM bins WHERE rack_id = ? ORDER BY name', (rack_id,)).fetchall()
    conn.close()
    return jsonify([dict(b) for b in bins])
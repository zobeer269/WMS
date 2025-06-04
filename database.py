import sqlite3
import hashlib
import uuid # لاستخدام UUID لتوليد مفاتيح API فريدة

def init_db():
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()

    # إنشاء جدول الراكات (Racks)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS racks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # إنشاء جدول السلات (Bins)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rack_id INTEGER NOT NULL,
            FOREIGN KEY (rack_id) REFERENCES racks(id) ON DELETE CASCADE,
            UNIQUE(name, rack_id)
        )
    ''')

    # إنشاء جدول الفئات (Categories)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # إنشاء جدول الأدوار
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # إنشاء جدول الصلاحيات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # إنشاء جدول ربط الأدوار بالصلاحيات (دور - صلاحية)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS role_permissions (
            role_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
            FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE,
            PRIMARY KEY (role_id, permission_id)
        )
    ''')

    # إنشاء جدول المستخدمين (Users)
    # تعديل: إضافة role_id و api_key
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role_id INTEGER DEFAULT 1,
            api_key TEXT UNIQUE, -- إضافة عمود API Key
            FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE SET DEFAULT
        )
    ''')

    # تحديث جدول المنتجات (Products)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_code TEXT NOT NULL UNIQUE,
            rack_id INTEGER,
            bin_id INTEGER,
            quantity INTEGER NOT NULL DEFAULT 0,
            category_id INTEGER,
            FOREIGN KEY (rack_id) REFERENCES racks(id) ON DELETE SET NULL,
            FOREIGN KEY (bin_id) REFERENCES bins(id) ON DELETE SET NULL,
            FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
        )
    ''')

    # إنشاء جدول سجل تدقيق المنتجات (Product History)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            user_id INTEGER,
            action TEXT NOT NULL,
            old_data TEXT,
            new_data TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')

    # إنشاء جدول الحركات (Transactions)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        )
    ''')

    # -------------------- تحديثات لأعمدة الجداول الموجودة وإضافة بيانات افتراضية --------------------

    # إضافة عمود 'quantity'
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN quantity INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # إضافة عمود 'category_id'
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN category_id INTEGER")
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES ('عام')")
        cursor.execute("UPDATE products SET category_id = (SELECT id FROM categories WHERE name = 'عام') WHERE category_id IS NULL")
        print("تم تحديث عمود 'category_id' والفئة الافتراضية بنجاح.")
    except sqlite3.OperationalError:
        pass

    # إضافة عمود 'rack_id'
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN rack_id INTEGER")
    except sqlite3.OperationalError:
        pass

    # إضافة عمود 'bin_id'
    try:
        cursor.execute("ALTER TABLE products ADD COLUMN bin_id INTEGER")
    except sqlite3.OperationalError:
        pass

    # إضافة عمود 'role_id' لجدول المستخدمين (إذا لم يكن موجوداً)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN role_id INTEGER DEFAULT 1 REFERENCES roles(id) ON DELETE SET DEFAULT")
    except sqlite3.OperationalError:
        pass

    # إضافة عمود 'api_key' لجدول المستخدمين (إذا لم يكن موجوداً)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN api_key TEXT UNIQUE")
    except sqlite3.OperationalError:
        pass

    # ترحيل مفاتيح API الحالية إلى صيغة مجزئة إذا كانت مخزنة كنص عادي
    existing_keys = cursor.execute("SELECT id, api_key FROM users WHERE api_key IS NOT NULL").fetchall()
    for row in existing_keys:
        key = row['api_key']
        if key and len(key) != 64:
            hashed = hashlib.sha256(key.encode()).hexdigest()
            cursor.execute("UPDATE users SET api_key = ? WHERE id = ?", (hashed, row['id']))
            print(f"Migrated API key for user ID {row['id']} to hashed version")


    # إضافة الأدوار الافتراضية
    cursor.execute("INSERT OR IGNORE INTO roles (id, name) VALUES (1, 'مستخدم عادي')")
    cursor.execute("INSERT OR IGNORE INTO roles (id, name) VALUES (2, 'مدير')")

    # إضافة الصلاحيات
    permissions_list = [
        'can_view_dashboard', 'can_view_products', 'can_add_product', 'can_edit_product', 'can_delete_product',
        'can_view_locations', 'can_manage_locations', 'can_view_categories', 'can_manage_categories',
        'can_view_users', 'can_manage_users', 'can_view_roles', 'can_manage_roles',
        'can_view_transactions', 'can_perform_cycle_count', 'can_receive_products', 'can_issue_products',
        'can_export_data', 'can_import_data', 'can_print_barcodes', 'can_view_advanced_reports', 'can_view_audit_trail',
        'can_access_api' # صلاحية جديدة للوصول إلى الـ API
    ]
    for perm_name in permissions_list:
        cursor.execute("INSERT OR IGNORE INTO permissions (name) VALUES (?)", (perm_name,))

    # تعيين الصلاحيات للأدوار الافتراضية
    regular_role_id = cursor.execute("SELECT id FROM roles WHERE name = 'مستخدم عادي'").fetchone()[0]
    regular_user_permissions = [
        'can_view_dashboard', 'can_view_products', 'can_add_product', 'can_edit_product',
        'can_view_locations', 'can_view_categories',
        'can_view_transactions', 'can_perform_cycle_count', 'can_receive_products', 'can_issue_products',
        'can_print_barcodes'
    ]
    for perm_name in regular_user_permissions:
        perm_id = cursor.execute("SELECT id FROM permissions WHERE name = ?", (perm_name,)).fetchone()[0]
        cursor.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                       (regular_role_id, perm_id))

    admin_role_id = cursor.execute("SELECT id FROM roles WHERE name = 'مدير'").fetchone()[0]
    for perm_name in permissions_list: # المدير يحصل على كل الصلاحيات
        perm_id = cursor.execute("SELECT id FROM permissions WHERE name = ?", (perm_name,)).fetchone()[0]
        cursor.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                       (admin_role_id, perm_id))

    # إضافة مستخدم المدير الافتراضي (إذا لم يكن موجوداً)
    admin_username = 'admin'
    admin_password = 'adminpass'
    hashed_password = hashlib.sha256(admin_password.encode()).hexdigest()
    
    cursor.execute("SELECT id FROM users WHERE username = ?", (admin_username,))
    if cursor.fetchone() is None:
        # توليد مفتاح API افتراضي للمدير
        default_api_key = str(uuid.uuid4())
        hashed_default_api_key = hashlib.sha256(default_api_key.encode()).hexdigest()
        cursor.execute("INSERT INTO users (username, password_hash, role_id, api_key) VALUES (?, ?, ?, ?)",
                       (admin_username, hashed_password, admin_role_id, hashed_default_api_key))
        print(f"تم إنشاء المستخدم المدير الافتراضي '{admin_username}' بكلمة مرور '{admin_password}' ومفتاح API: {default_api_key}.")

    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("تم إعداد قاعدة البيانات بنجاح أو كانت موجودة بالفعل.")
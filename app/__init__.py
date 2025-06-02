from flask import Flask, g, session, redirect, url_for, flash, request
import sqlite3
import functools
from config import Config

# دالة مساعدة للحصول على اتصال قاعدة البيانات
def get_db_connection():
    conn = sqlite3.connect(Config.DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# المزخرفات (Decorators)
def permission_required(permission_name):
    def decorator(view):
        @functools.wraps(view)
        def wrapped_view(**kwargs):
            user_id = None
            
            # محاولة المصادقة عبر API Key (لطلبات الـ API)
            api_key = request.headers.get('X-API-Key')
            if api_key:
                conn = get_db_connection()
                user = conn.execute('SELECT * FROM users WHERE api_key = ?', (api_key,)).fetchone()
                conn.close()
                if user:
                    g.user = user
                    # جلب صلاحيات المستخدم API Key
                    user_permissions_data = conn.execute('''
                        SELECT p.name FROM permissions p
                        JOIN role_permissions rp ON p.id = rp.permission_id
                        WHERE rp.role_id = ?
                    ''', (user['role_id'],)).fetchall()
                    g.user_permissions = [p['name'] for p in user_permissions_data]
                    # التحقق من صلاحية API Access
                    if 'can_access_api' not in g.user_permissions:
                        return jsonify({'message': 'ليس لديك صلاحية الوصول إلى الـ API.'}), 403 # Forbidden
                else:
                    return jsonify({'message': 'مفتاح API غير صالح.'}), 401 # Unauthorized
            
            # إذا لم يتم المصادقة عبر API Key، حاول المصادقة عبر الجلسة (لواجهة المستخدم الرسومية)
            if g.user is None: # إذا لم يكن g.user قد تم تعيينه بواسطة API Key
                user_id = session.get('user_id')
                if user_id:
                    conn = get_db_connection()
                    g.user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
                    conn.close()
                    # جلب صلاحيات المستخدم الجلسة
                    if g.user:
                        user_permissions_data = conn.execute('''
                            SELECT p.name FROM permissions p
                            JOIN role_permissions rp ON p.id = rp.permission_id
                            WHERE rp.role_id = ?
                        ''', (g.user['role_id'],)).fetchall()
                        g.user_permissions = [p['name'] for p in user_permissions_data]

            # التحقق النهائي من تسجيل الدخول والصلاحيات
            if g.user is None:
                flash('يجب عليك تسجيل الدخول أولاً للوصول إلى هذه الصفحة.', 'error')
                return redirect(url_for('auth.login'))
            
            # إذا كانت الصلاحية المطلوبة هي 'can_access_api' وكان الطلب ليس API (أي من GUI)، فاستمر.
            # أو إذا كانت الصلاحية المطلوبة ليست 'can_access_api'
            if permission_name == 'can_access_api': # إذا كانت الصلاحية المطلوبة هي الوصول إلى الـ API
                if 'can_access_api' not in g.user_permissions:
                    return jsonify({'message': 'ليس لديك صلاحية الوصول إلى الـ API.'}), 403
            elif permission_name not in g.user_permissions: # لأي صلاحية أخرى
                flash('ليس لديك الصلاحيات الكافية للوصول إلى هذه الصفحة.', 'error')
                return redirect(url_for('main.index'))
            
            return view(**kwargs)
        return wrapped_view
    return decorator

# مزخرفات convenience (لتبسيط الاستخدام)
login_required = permission_required('can_view_dashboard')
admin_required = permission_required('can_manage_users')


# دالة إنشاء التطبيق الرئيسية
def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')
        g.user = None
        g.user_permissions = [] 
        if user_id:
            conn = get_db_connection()
            g.user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
            if g.user:
                 user_permissions_data = conn.execute('''
                    SELECT p.name FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.permission_id
                    WHERE rp.role_id = ?
                ''', (g.user['role_id'],)).fetchall()
                 g.user_permissions = [p['name'] for p in user_permissions_data]
            conn.close()

    # تسجيل المخططات الزرقاء (Blueprints)
    from .auth import auth_bp
    from .categories import categories_bp
    from .locations import locations_bp
    from .products import products_bp
    from .transactions import transactions_bp
    from .inventory_ops import inventory_ops_bp
    from .reports import reports_bp as main_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(inventory_ops_bp)
    app.register_blueprint(main_bp)

    # تحديد المسار الرئيسي للتطبيق
    app.add_url_rule('/', endpoint='main.index')

    return app
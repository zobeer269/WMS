import os

class Config:
    # المفتاح السري لـ Flask Sessions و flash messages.
    # في بيئة الإنتاج، استخدم مفتاحًا عشوائيًا ومعقدًا جدًا
    # ويفضل أن يتم تحميله من متغيرات البيئة.
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        if os.environ.get('FLASK_ENV') == 'production':
            raise RuntimeError('SECRET_KEY environment variable must be set in production')
        SECRET_KEY = 'your_another_super_secret_key_here_for_security_v6_123456789'
    
    # مدة صلاحية الجلسة بالثواني (ساعة واحدة)
    PERMANENT_SESSION_LIFETIME = 3600 

    # مسار قاعدة البيانات
    DATABASE = 'inventory.db'

    # عتبة المخزون المنخفض (يمكن تعديلها هنا)
    LOW_STOCK_THRESHOLD = 10
from app import create_app

# قم بإنشاء التطبيق باستخدام الدالة create_app
app = create_app()

if __name__ == '__main__':
    # قم بتشغيل التطبيق في وضع التطوير
    # في بيئة الإنتاج، استخدم خادم ويب WSGI مثل Gunicorn أو uWSGI
    app.run(debug=True)
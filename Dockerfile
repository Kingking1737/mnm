FROM python:3.11-slim

WORKDIR /app

# نصب پیش‌نیازهای سیستمی (اگه لازم شد)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# کپی و نصب پکیج‌های پایتون
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی کد
COPY bot.py .

# اجرا
CMD ["python", "-u", "bot.py"]

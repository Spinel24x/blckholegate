FROM python:3.11-slim

# نصب پیش‌نیازهای سیستمی
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libffi-dev \
    dnsutils \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# کپی فایل‌های پروژه
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ایجاد دایرکتوری برای لاگ‌ها
RUN mkdir -p /app/logs

# پورت‌های مورد نیاز
EXPOSE 53/tcp
EXPOSE 53/udp
EXPOSE 8000

# اجرای اپلیکیشن
CMD ["python", "main.py"]

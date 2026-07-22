FROM python:3.11-slim

# نصب پیش‌نیازهای سیستمی
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ایجاد کاربر غیر-root
RUN useradd -m -s /bin/bash appuser

WORKDIR /app

# کپی و نصب requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# کپی بقیه فایل‌ها
COPY . .

# ایجاد دایرکتوری‌های مورد نیاز
RUN mkdir -p /app/logs /app/data

# تغییر مالکیت به کاربر غیر-root
RUN chown -R appuser:appuser /app

# تغییر به کاربر غیر-root
USER appuser

# ⚠️ پورت 8080 (نه 8000)
EXPOSE 8080

# اجرای اپلیکیشن
CMD ["python", "main.py"]

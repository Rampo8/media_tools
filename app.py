"""
MediaTool — Веб-приложение для обработки медиа
- Скачивание видео (YouTube, Rutube, Instagram) → 1080p
- Улучшение фото (8x + контраст + цветокоррекция)
- Удаление фона с фото
- Фото для соцсетей (трендовые размеры + улучшение кожи)
"""

import os
import uuid
import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename
from PIL import Image, ImageEnhance, ImageFilter
import yt_dlp

# =============================================================================
# Конфигурация
# =============================================================================
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / 'uploads'
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(
    __name__,
    template_folder='templates',
    static_folder='static'
)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


# =============================================================================
# Утилиты
# =============================================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_filename(extension):
    return f"{uuid.uuid4().hex[:12]}.{extension}"


def cleanup_old_files():
    """Удаляет файлы старше 12 часов"""
    now = datetime.now()
    for f in UPLOAD_DIR.iterdir():
        if f.is_file():
            age = now - datetime.fromtimestamp(f.stat().st_mtime)
            if age > timedelta(hours=12):
                try:
                    f.unlink()
                except:
                    pass


# =============================================================================
# Главная страница
# =============================================================================
@app.route('/')
def index():
    return render_template('index.html')


# =============================================================================
# API: Видео
# =============================================================================
@app.route('/api/video/download', methods=['POST'])
def video_download():
    data = request.get_json()
    url = data.get('url', '').strip()
    quality = data.get('quality', 1080)

    if not url:
        return jsonify({'success': False, 'error': 'URL не указан'}), 400

    # Проверка доменов
    domains = ['youtube.com', 'youtu.be', 'rutube.ru', 'instagram.com', 'vimeo.com']
    if not any(d in url.lower() for d in domains):
        return jsonify({'success': False, 'error': 'Неподдерживаемый сайт'}), 400

    try:
        filename = generate_filename('mp4')
        output_path = UPLOAD_DIR / filename

        ydl_opts = {
            'format': f'best[height<={quality}]/best',
            'outtmpl': str(output_path.with_suffix('')),
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Video')
            # Ищем скачанный файл
            actual_path = None
            for f in UPLOAD_DIR.iterdir():
                if f.stem.startswith(filename.rsplit('.', 1)[0]) and f.suffix:
                    actual_path = f
                    break
            
            if not actual_path:
                # Возможно yt-dlp создал файл с другим расширением
                possible = list(UPLOAD_DIR.glob(f"{filename.rsplit('.', 1)[0]}*"))
                if possible:
                    actual_path = possible[0]

            if actual_path:
                file_size = actual_path.stat().st_size
                actual_quality = info.get('height', quality)

                return jsonify({
                    'success': True,
                    'title': title[:80],
                    'quality': actual_quality,
                    'size': f"{file_size / (1024*1024):.2f} МБ",
                    'download_url': f'/uploads/{actual_path.name}'
                })
            else:
                return jsonify({'success': False, 'error': 'Ошибка: файл не найден'}), 500

    except yt_dlp.utils.DownloadError as e:
        return jsonify({'success': False, 'error': f'Ошибка скачивания: {str(e)[:200]}'}), 400
    except Exception as e:
        logger.error(f"Ошибка видео: {e}")
        return jsonify({'success': False, 'error': f'Ошибка: {str(e)[:200]}'}), 500


# =============================================================================
# API: Улучшение фото
# =============================================================================
@app.route('/api/photo/enhance', methods=['POST'])
def photo_enhance():
    if 'photo' not in request.files:
        return jsonify({'success': False, 'error': 'Файл не загружен'}), 400

    file = request.files['photo']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Неподдерживаемый формат'}), 400

    try:
        sharpness = float(request.form.get('sharpness', 1.5))
        contrast = float(request.form.get('contrast', 1.2))
        brightness = float(request.form.get('brightness', 1.1))

        img = Image.open(file.stream)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        original_width, original_height = img.size

        # Увеличение в 8 раз
        new_width = original_width * 8
        new_height = original_height * 8

        # Ограничение по максимальному размеру (5000px)
        max_dim = 5000
        if new_width > max_dim or new_height > max_dim:
            scale = min(max_dim / original_width, max_dim / original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)

        img = img.resize((new_width, new_height), Image.NEAREST)

        # Резкость
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
        # Контраст
        img = ImageEnhance.Contrast(img).enhance(contrast)
        # Яркость
        img = ImageEnhance.Brightness(img).enhance(brightness)

        # Сохранение
        out_filename = generate_filename('jpg')
        out_path = UPLOAD_DIR / out_filename
        img.save(str(out_path), 'JPEG', quality=95, optimize=True)

        file_size = out_path.stat().st_size

        return jsonify({
            'success': True,
            'size': f"{file_size // 1024} КБ",
            'dimensions': f"{new_width}×{new_height}",
            'download_url': f'/uploads/{out_filename}'
        })

    except Exception as e:
        logger.error(f"Ошибка улучшения фото: {e}")
        return jsonify({'success': False, 'error': f'Ошибка: {str(e)[:200]}'}), 500


# =============================================================================
# API: Удаление фона
# =============================================================================
@app.route('/api/background/remove', methods=['POST'])
def background_remove():
    if 'photo' not in request.files:
        return jsonify({'success': False, 'error': 'Файл не загружен'}), 400

    file = request.files['photo']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Неподдерживаемый формат'}), 400

    try:
        from rembg import remove, new_session

        img = Image.open(file.stream)
        if img.mode == 'P':
            img = img.convert('RGBA')
        elif img.mode == 'L':
            img = img.convert('LA')

        session = new_session('u2net')
        img_no_bg = remove(
            img,
            session=session,
            alpha_matting=True,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10
        )

        out_filename = generate_filename('png')
        out_path = UPLOAD_DIR / out_filename
        img_no_bg.save(str(out_path), 'PNG')

        file_size = out_path.stat().st_size

        return jsonify({
            'success': True,
            'size': f"{file_size // 1024} КБ",
            'download_url': f'/uploads/{out_filename}'
        })

    except ImportError:
        return jsonify({'success': False, 'error': 'rembg не установлена. pip install rembg onnxruntime'}), 500
    except Exception as e:
        logger.error(f"Ошибка удаления фона: {e}")
        return jsonify({'success': False, 'error': f'Ошибка: {str(e)[:200]}'}), 500


# =============================================================================
# API: Фото для соцсетей
# =============================================================================
@app.route('/api/social/create', methods=['POST'])
def social_create():
    if 'photo' not in request.files:
        return jsonify({'success': False, 'error': 'Файл не загружен'}), 400

    file = request.files['photo']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Неподдерживаемый формат'}), 400

    try:
        social_format = request.form.get('format', 'instagram')
        skin_enhance = request.form.get('skin_enhance', '0') == '1'

        # Размеры для соцсетей
        formats = {
            'instagram': (1080, 1080),
            'instagram-story': (1080, 1920),
            'youtube': (1280, 720),
            'facebook': (1200, 630),
        }
        target_w, target_h = formats.get(social_format, (1080, 1080))

        img = Image.open(file.stream)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')

        # Улучшение кожи лица (если включено)
        if skin_enhance:
            # Лёгкое размытие для сглаживания дефектов
            img = img.filter(ImageFilter.GaussianBlur(radius=0.8))
            # Повышение резкости (чтобы не потерять детали)
            img = ImageEnhance.Sharpness(img).enhance(1.3)
            # Небольшое повышение яркости
            img = ImageEnhance.Brightness(img).enhance(1.05)
            # Лёгкий контраст
            img = ImageEnhance.Contrast(img).enhance(1.1)

        # Кадрирование по центру под нужный формат
        orig_w, orig_h = img.size
        target_ratio = target_w / target_h
        orig_ratio = orig_w / orig_h

        if orig_ratio > target_ratio:
            # Слишком широкое — обрезаем по бокам
            new_w = int(orig_h * target_ratio)
            left = (orig_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, orig_h))
        else:
            # Слишком высокое — обрезаем сверху и снизу
            new_h = int(orig_w / target_ratio)
            top = (orig_h - new_h) // 2
            img = img.crop((0, top, orig_w, top + new_h))

        # Ресайз под целевой размер
        img = img.resize((target_w, target_h), Image.LANCZOS)

        # Финальная обработка
        img = ImageEnhance.Sharpness(img).enhance(1.2)
        img = ImageEnhance.Contrast(img).enhance(1.15)

        out_filename = generate_filename('jpg')
        out_path = UPLOAD_DIR / out_filename
        img.save(str(out_path), 'JPEG', quality=95, optimize=True)

        file_size = out_path.stat().st_size

        return jsonify({
            'success': True,
            'size': f"{file_size // 1024} КБ",
            'dimensions': f"{target_w}×{target_h}",
            'download_url': f'/uploads/{out_filename}'
        })

    except Exception as e:
        logger.error(f"Ошибка создания фото для соцсетей: {e}")
        return jsonify({'success': False, 'error': f'Ошибка: {str(e)[:200]}'}), 500


# =============================================================================
# Раздача загруженных файлов
# =============================================================================
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, secure_filename(filename))


# =============================================================================
# Планировщик очистки
# =============================================================================
import threading

def cleanup_loop():
    while True:
        try:
            cleanup_old_files()
        except Exception as e:
            logger.error(f"Ошибка очистки: {e}")
        threading.Event().wait(3600)  # Каждый час


# =============================================================================
# Запуск
# =============================================================================
if __name__ == '__main__':
    # Запускаем фоновую очистку
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

    logger.info("=" * 60)
    logger.info("🚀 MediaTool — запуск веб-приложения")
    logger.info("=" * 60)

    # Проверка зависимостей
    try:
        import rembg
        logger.info("✅ rembg установлен")
    except ImportError:
        logger.warning("⚠️ rembg не установлен — удаление фона не будет работать")
        logger.warning("💡 pip install rembg onnxruntime")

    app.run(host='0.0.0.0', port=5000, debug=False)

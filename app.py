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

from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import os
import uuid
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

# Ленивые импорты — тяжелые библиотеки загружаются только при вызове API

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
    import cv2
    import yt_dlp

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
# API: Улучшение фото (OpenCV + scikit-image) — автоматическое
# =============================================================================
@app.route('/api/photo/enhance', methods=['POST'])
def photo_enhance():
    import cv2
    import numpy as np
    from skimage import exposure
    from skimage.color import rgb2lab, lab2rgb

    if 'photo' not in request.files:
        return jsonify({'success': False, 'error': 'Файл не загружен'}), 400

    file = request.files['photo']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Неподдерживаемый формат'}), 400

    try:
        # Настройки по умолчанию — оптимальные для улучшения качества
        SHARPNESS = 2.0
        CONTRAST = 1.4
        BRIGHTNESS = 1.15

        # Читаем через OpenCV
        nparr = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return jsonify({'success': False, 'error': 'Не удалось прочитать изображение'}), 400

        original_h, original_w = img.shape[:2]

        # ─── 1. Увеличение в 8 раз (OpenCV Lanczos) ───
        new_w = original_w * 8
        new_h = original_h * 8

        max_dim = 5000
        if new_w > max_dim or new_h > max_dim:
            scale = min(max_dim / original_w, max_dim / original_h)
            new_w = int(original_w * scale)
            new_h = int(original_h * scale)

        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

        # ─── 2. Яркость ───
        img = np.clip(img.astype(np.float32) * BRIGHTNESS, 0, 255).astype(np.uint8)

        # ─── 3. Контраст через CLAHE ───
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        clip_limit = max(1.0, CONTRAST * 2.0)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        # ─── 4. Резкость через Unsharp Mask ───
        blurred = cv2.GaussianBlur(img, (0, 0), sigmaX=3)
        img = cv2.addWeighted(img, 1.0 + SHARPNESS, blurred, -SHARPNESS, 0)

        # ─── 5. Цветокоррекция через scikit-image ───
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_float = img_rgb.astype(np.float32) / 255.0

        gamma = 1.0 / max(0.8, CONTRAST * 0.9)
        img_float = exposure.adjust_gamma(img_float, gamma)

        img_lab = rgb2lab(img_float)
        color_boost = 1.0 + (CONTRAST - 1.0) * 0.5
        img_lab[:, :, 1] *= color_boost
        img_lab[:, :, 2] *= color_boost
        img_float = lab2rgb(img_lab)

        img_final = (np.clip(img_float, 0, 1) * 255).astype(np.uint8)
        img_bgr = cv2.cvtColor(img_final, cv2.COLOR_RGB2BGR)

        # Сохранение
        out_filename = generate_filename('jpg')
        out_path = UPLOAD_DIR / out_filename
        cv2.imwrite(str(out_path), img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])

        file_size = out_path.stat().st_size

        return jsonify({
            'success': True,
            'size': f"{file_size // 1024} КБ",
            'dimensions': f"{new_w}×{new_h}",
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
    from rembg import remove, new_session
    from PIL import Image as PILImage

    if 'photo' not in request.files:
        return jsonify({'success': False, 'error': 'Файл не загружен'}), 400

    file = request.files['photo']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Неподдерживаемый формат'}), 400

    try:
        img = PILImage.open(file.stream)
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
        return jsonify({'success': False, 'error': 'Удаление фона временно недоступно'}), 503
    except Exception as e:
        logger.error(f"Ошибка удаления фона: {e}")
        return jsonify({'success': False, 'error': f'Ошибка: {str(e)[:200]}'}), 500


# =============================================================================
# API: Фото для соцсетей (OpenCV + scikit-image)
# =============================================================================
@app.route('/api/social/create', methods=['POST'])
def social_create():
    import cv2
    import numpy as np
    from skimage import exposure, restoration
    from skimage.color import rgb2lab, lab2rgb

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

        # Читаем через OpenCV
        nparr = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({'success': False, 'error': 'Не удалось прочитать изображение'}), 400

        h, w = img.shape[:2]

        # ─── Улучшение кожи лица (OpenCV + scikit-image) ───
        if skin_enhance:
            # Bilateral filter — сглаживает кожу, сохраняет края
            img = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)

            # denoise_nlmeans — убирает шум и мелкие дефекты
            img_float = img.astype(np.float32) / 255.0
            denoised = restoration.denoise_nl_means(
                img_float,
                h=0.08,
                fast_mode=True,
                patch_size=5,
                patch_distance=6,
                multichannel=True
            )
            img = (np.clip(denoised, 0, 1) * 255).astype(np.uint8)

            # Лёгкий Unsharp Mask для восстановления резкости
            blurred = cv2.GaussianBlur(img, (0, 0), sigmaX=1.5)
            img = cv2.addWeighted(img, 1.3, blurred, -0.3, 0)

            # Gamma + насыщенность
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            img_rgb = exposure.adjust_gamma(img_rgb, 0.95)
            img_lab = rgb2lab(img_rgb)
            img_lab[:, :, 1] *= 1.15
            img_lab[:, :, 2] *= 1.15
            img = cv2.cvtColor(lab2rgb(img_lab), cv2.COLOR_RGB2BGR)
            img = (np.clip(img, 0, 1) * 255).astype(np.uint8)

        # ─── Кадрирование по центру ───
        target_ratio = target_w / target_h
        orig_ratio = w / h

        if orig_ratio > target_ratio:
            new_w = int(h * target_ratio)
            left = (w - new_w) // 2
            img = img[:, left:left + new_w]
        else:
            new_h = int(w / target_ratio)
            top = (h - new_h) // 2
            img = img[top:top + new_h]

        # Ресайз (Lanczos)
        img = cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LANCZOS4)

        # ─── Финальная обработка (CLAHE + резкость) ───
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        blurred = cv2.GaussianBlur(img, (0, 0), sigmaX=1)
        img = cv2.addWeighted(img, 1.2, blurred, -0.2, 0)

        # Сохранение
        out_filename = generate_filename('jpg')
        out_path = UPLOAD_DIR / out_filename
        cv2.imwrite(str(out_path), img, [cv2.IMWRITE_JPEG_QUALITY, 95])

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

    port = int(os.environ.get('PORT', 5000))
    logger.info("=" * 60)
    logger.info(f"🚀 MediaTool — запуск (порт {port})")
    logger.info("💡 Видео, Фото, Фон, Соцсети — готовы")
    logger.info("=" * 60)

    app.run(host='0.0.0.0', port=port, debug=False)

/* ===================== Медиа-инструменты — Фронтенд ===================== */

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initVideoForm();
    initPhotoForm();
    initBgForm();
    initSocialForm();
});

/* ===================== Навигация ===================== */
function initNavigation() {
    const menuBtn = document.getElementById('mobileMenuBtn');
    const navLinks = document.getElementById('navLinks');

    menuBtn?.addEventListener('click', () => {
        const isOpen = navLinks.classList.toggle('open');
        menuBtn.setAttribute('aria-expanded', isOpen);
    });

    // Закрытие при клике на ссылку
    navLinks?.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', () => {
            navLinks.classList.remove('open');
            menuBtn.setAttribute('aria-expanded', 'false');
        });
    });

    // Активная ссылка при скролле
    const sections = document.querySelectorAll('.section');
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
                const activeLink = document.querySelector(`.nav-link[href="#${entry.target.id}"]`);
                activeLink?.classList.add('active');
            }
        });
    }, { threshold: 0.3 });

    sections.forEach(s => observer.observe(s));
}

/* ===================== Утилиты ===================== */
function showToast(message, duration = 3000) {
    const toast = document.getElementById('toast');
    const msg = document.getElementById('toastMessage');
    msg.textContent = message;
    toast.hidden = false;
    setTimeout(() => { toast.hidden = true; }, duration);
}

function setLoading(btnId, loaderId, loading) {
    const btn = document.getElementById(btnId);
    const loader = document.getElementById(loaderId);
    btn.disabled = loading;
    loader.classList.toggle('hidden', !loading);
    btn.querySelector('.btn-text').style.opacity = loading ? '0.5' : '1';
}

function showResult(resultId, infoId, linkId, infoText, downloadUrl) {
    const result = document.getElementById(resultId);
    const info = document.getElementById(infoId);
    const link = document.getElementById(linkId);

    if (info) info.textContent = infoText;
    if (link) link.href = downloadUrl;
    result.hidden = false;
}

function showError(errorId, message) {
    const errorBox = document.getElementById(errorId);
    errorBox.textContent = '❌ ' + message;
    errorBox.hidden = false;
}

function hideAll(idPrefix) {
    document.getElementById(`${idPrefix}Result`)?.setAttribute('hidden', '');
    document.getElementById(`${idPrefix}Error`)?.setAttribute('hidden', '');
}

/* ===================== Drag & Drop загрузка ===================== */
function initUploadArea(uploadId, inputId, previewId, previewImgId, removeId) {
    const area = document.getElementById(uploadId);
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    const previewImg = document.getElementById(previewImgId);
    const removeBtn = document.getElementById(removeId);

    if (!area || !input) return;

    // Клик по области
    area.addEventListener('click', () => input.click());
    area.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') input.click(); });

    // Выбор файла
    input.addEventListener('change', () => {
        if (input.files.length > 0) showPreview(input.files[0]);
    });

    // Drag & Drop
    area.addEventListener('dragover', (e) => { e.preventDefault(); area.classList.add('dragover'); });
    area.addEventListener('dragleave', () => area.classList.remove('dragover'));
    area.addEventListener('drop', (e) => {
        e.preventDefault();
        area.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            input.files = e.dataTransfer.files;
            showPreview(e.dataTransfer.files[0]);
        }
    });

    // Удаление превью
    removeBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        input.value = '';
        preview.hidden = true;
        area.hidden = false;
    });

    function showPreview(file) {
        if (!file.type.startsWith('image/')) {
            showToast('❌ Выберите изображение');
            return;
        }
        const reader = new FileReader();
        reader.onload = (e) => {
            previewImg.src = e.target.result;
            preview.hidden = false;
            area.hidden = true;
        };
        reader.readAsDataURL(file);
    }
}

/* ===================== Видео ===================== */
function initVideoForm() {
    const form = document.getElementById('videoForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        hideAll('video');

        const url = document.getElementById('videoUrl').value.trim();
        if (!url) {
            showError('videoError', 'Вставьте ссылку на видео');
            return;
        }

        setLoading('videoSubmitBtn', 'videoLoader', true);

        try {
            const response = await fetch('/api/video/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, quality: 1080 })
            });

            const data = await response.json();

            if (!data.success) throw new Error(data.error || 'Ошибка скачивания');

            document.getElementById('videoTitle').textContent = '✅ ' + (data.title || 'Видео готово!');
            showResult('videoResult', 'videoInfo', 'videoDownloadLink',
                `Качество: ${data.quality}p | Размер: ${data.size}`, data.download_url);
            showToast('✅ Видео готово к скачиванию!');

        } catch (err) {
            showError('videoError', err.message);
        } finally {
            setLoading('videoSubmitBtn', 'videoLoader', false);
        }
    });
}

/* ===================== Фото ===================== */
function initPhotoForm() {
    initUploadArea('photoUploadArea', 'photoFile', 'photoPreview', 'photoPreviewImg', 'photoPreviewRemove');

    // Слайдеры
    ['sharpness', 'contrast', 'brightness'].forEach(name => {
        const slider = document.getElementById(`photo${name.charAt(0).toUpperCase() + name.slice(1)}`);
        const display = document.getElementById(`${name}Val`);
        slider?.addEventListener('input', () => {
            display.textContent = slider.value;
            // Если фото уже загружено — перезапустить обработку
            if (document.getElementById('photoFile').files.length > 0) {
                processPhoto();
            }
        });
    });

    const form = document.getElementById('photoForm');
    if (!form) return;

    form.addEventListener('submit', (e) => e.preventDefault());

    // Авто-обработка при загрузке
    document.getElementById('photoFile').addEventListener('change', () => {
        if (document.getElementById('photoFile').files.length > 0) {
            processPhoto();
        }
    });
}

async function processPhoto() {
    const file = document.getElementById('photoFile').files[0];
    if (!file) return;

    hideAll('photo');
    setLoading('photoSubmitBtn', 'photoLoader', true);
    document.getElementById('photoSubmitBtn').textContent = '⏳ Обработка...';

    const formData = new FormData();
    formData.append('photo', file);
    formData.append('sharpness', document.getElementById('photoSharpness').value);
    formData.append('contrast', document.getElementById('photoContrast').value);
    formData.append('brightness', document.getElementById('photoBrightness').value);

    try {
        const response = await fetch('/api/photo/enhance', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Ошибка обработки');

        showResult('photoResult', 'photoInfo', 'photoDownloadLink',
            `Размер: ${data.size} | ${data.dimensions} | Увеличение: 8x`, data.download_url);
        showToast('✅ Фото автоматически улучшено!');

    } catch (err) {
        showError('photoError', err.message);
    } finally {
        setLoading('photoSubmitBtn', 'photoLoader', false);
        document.getElementById('photoSubmitBtn').innerHTML = '<span class="btn-text">🔄 Обработать заново</span>';
    }
}

/* ===================== Фон ===================== */
function initBgForm() {
    initUploadArea('bgUploadArea', 'bgFile', 'bgPreview', 'bgPreviewImg', 'bgPreviewRemove');

    const form = document.getElementById('bgForm');
    if (!form) return;

    form.addEventListener('submit', (e) => e.preventDefault());

    // Авто-обработка при загрузке
    document.getElementById('bgFile').addEventListener('change', () => {
        if (document.getElementById('bgFile').files.length > 0) {
            processBgRemove();
        }
    });
}

async function processBgRemove() {
    const file = document.getElementById('bgFile').files[0];
    if (!file) return;

    hideAll('bg');
    setLoading('bgSubmitBtn', 'bgLoader', true);
    document.getElementById('bgSubmitBtn').textContent = '⏳ Удаление фона...';

    const formData = new FormData();
    formData.append('photo', file);

    try {
        const response = await fetch('/api/background/remove', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Ошибка удаления фона');

        showResult('bgResult', 'bgInfo', 'bgDownloadLink',
            `Размер: ${data.size} | Фон удалён`, data.download_url);
        showToast('✅ Фон автоматически удалён!');

    } catch (err) {
        showError('bgError', err.message);
    } finally {
        setLoading('bgSubmitBtn', 'bgLoader', false);
        document.getElementById('bgSubmitBtn').innerHTML = '<span class="btn-text">🔄 Удалить фон заново</span>';
    }
}

/* ===================== Соцсети ===================== */
function initSocialForm() {
    initUploadArea('socialUploadArea', 'socialFile', 'socialPreview', 'socialPreviewImg', 'socialPreviewRemove');

    const form = document.getElementById('socialForm');
    if (!form) return;

    form.addEventListener('submit', (e) => e.preventDefault());

    // Авто-обработка при загрузке или смене формата
    document.getElementById('socialFile').addEventListener('change', () => {
        if (document.getElementById('socialFile').files.length > 0) {
            processSocial();
        }
    });

    document.querySelectorAll('input[name="socialFormat"]').forEach(radio => {
        radio.addEventListener('change', () => {
            if (document.getElementById('socialFile').files.length > 0) {
                processSocial();
            }
        });
    });

    document.getElementById('skinEnhance').addEventListener('change', () => {
        if (document.getElementById('socialFile').files.length > 0) {
            processSocial();
        }
    });
}

async function processSocial() {
    const file = document.getElementById('socialFile').files[0];
    if (!file) return;

    hideAll('social');
    setLoading('socialSubmitBtn', 'socialLoader', true);
    document.getElementById('socialSubmitBtn').textContent = '⏳ Создание...';

    const format = document.querySelector('input[name="socialFormat"]:checked').value;
    const skinEnhance = document.getElementById('skinEnhance').checked;

    const formData = new FormData();
    formData.append('photo', file);
    formData.append('format', format);
    formData.append('skin_enhance', skinEnhance ? '1' : '0');

    try {
        const response = await fetch('/api/social/create', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Ошибка создания');

        const formatNames = {
            'instagram': 'Instagram 1080×1080',
            'instagram-story': 'Stories 1080×1920',
            'youtube': 'YouTube 1280×720',
            'facebook': 'Facebook 1200×630'
        };

        showResult('socialResult', 'socialInfo', 'socialDownloadLink',
            `Формат: ${formatNames[format] || format}${skinEnhance ? ' | Кожа улучшена' : ''}`,
            data.download_url);
        showToast('✅ Автоматически готово для соцсетей!');

    } catch (err) {
        showError('socialError', err.message);
    } finally {
        setLoading('socialSubmitBtn', 'socialLoader', false);
        document.getElementById('socialSubmitBtn').innerHTML = '<span class="btn-text">🔄 Создать заново</span>';
    }
}

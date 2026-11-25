// ── Сворачивание / разворачивание sidebar ───────────────────
(function () {
    var body = document.body;
    var toggleBtn = document.getElementById('sidebarToggle');
    var hamburgerBtn = document.getElementById('hamburgerBtn');
    var sidebar = document.getElementById('sidebar');

    var STORAGE_KEY = 'sidebar-collapsed';

    // Восстановление состояния только для десктопа
    try {
        if (window.innerWidth > 1024 && localStorage.getItem(STORAGE_KEY) === '1') {
            body.classList.add('sidebar-collapsed');
        }
    } catch (e) { /* localStorage может быть недоступен */ }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', function () {
            body.classList.toggle('sidebar-collapsed');
            try {
                localStorage.setItem(STORAGE_KEY, body.classList.contains('sidebar-collapsed') ? '1' : '0');
            } catch (e) { /* ignore */ }
        });
    }

    if (hamburgerBtn) {
        hamburgerBtn.addEventListener('click', function () {
            body.classList.toggle('sidebar-mobile-open');
        });
    }

    // Закрытие мобильного меню по клику вне sidebar
    document.addEventListener('click', function (e) {
        if (window.innerWidth > 1024) return;
        if (!body.classList.contains('sidebar-mobile-open')) return;
        if (sidebar && sidebar.contains(e.target)) return;
        if (hamburgerBtn && hamburgerBtn.contains(e.target)) return;
        body.classList.remove('sidebar-mobile-open');
    });
})();

// ── Общий escapeHtml для безопасной вставки в innerHTML ────
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}
window.escapeHtml = escapeHtml;

// ── Модалка карточки школы ──────────────────────────────────
(function () {
    var overlay = document.getElementById('schoolModal');
    var chip = document.getElementById('schoolChip');
    if (!overlay || !chip) return;

    var nameDisplay = document.getElementById('schoolNameDisplay');
    var nameEditBlock = document.getElementById('schoolNameEditBlock');
    var nameInput = document.getElementById('schoolNameInput');
    var editIcon = document.getElementById('schoolEditIcon');
    var saveBtn = document.getElementById('schoolSaveBtn');
    var closeBtns = [
        document.getElementById('schoolModalClose'),
        document.getElementById('schoolModalClose2'),
    ];

    function openModal() {
        overlay.classList.add('active');
        overlay.setAttribute('aria-hidden', 'false');
        loadStats();
    }

    function closeModal() {
        overlay.classList.remove('active');
        overlay.setAttribute('aria-hidden', 'true');
        nameEditBlock.style.display = 'none';
        nameDisplay.style.display = 'inline';
    }

    function editName() {
        nameDisplay.style.display = 'none';
        nameEditBlock.style.display = 'block';
        nameInput.focus();
    }

    function saveName() {
        var newName = (nameInput.value || '').trim();
        if (!newName) { alert('Название не может быть пустым'); return; }
        if (!window.CURRENT_SCHOOL_ID) { alert('Не удалось определить школу'); return; }

        fetch('/schools/' + window.CURRENT_SCHOOL_ID + '/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'name=' + encodeURIComponent(newName)
                + '&csrf_token=' + encodeURIComponent(window.CSRF_TOKEN || '')
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                nameDisplay.textContent = data.name;
                nameDisplay.style.display = 'inline';
                nameEditBlock.style.display = 'none';
                chip.textContent = '🏫 ' + data.name;
                nameInput.value = data.name;
            } else {
                alert('Ошибка: ' + (data.error || 'неизвестная ошибка'));
            }
        })
        .catch(function () { alert('Ошибка сети'); });
    }

    function loadStats() {
        fetch('/api/school/stats')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                document.getElementById('schoolStatStudents').textContent = data.students || 0;
                document.getElementById('schoolStatClasses').textContent  = data.classes  || 0;
                document.getElementById('schoolStatTeachers').textContent = data.teachers || 0;
            })
            .catch(function () { /* оставляем нули */ });
    }

    chip.addEventListener('click', openModal);
    closeBtns.forEach(function (b) { if (b) b.addEventListener('click', closeModal); });
    if (editIcon) editIcon.addEventListener('click', editName);
    if (saveBtn) saveBtn.addEventListener('click', saveName);

    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
    });
})();
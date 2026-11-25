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
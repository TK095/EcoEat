document.addEventListener('DOMContentLoaded', function () {
    var fill = document.querySelector('.xp-fill[data-xp-pct]');
    if (fill) {
        var pct = fill.getAttribute('data-xp-pct') || '0';
        fill.style.width = '0%';
        requestAnimationFrame(function () {
            fill.style.width = pct + '%';
        });
    }
});

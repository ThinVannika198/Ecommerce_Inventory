(function () {
    const input = document.getElementById('date-input');
    const form = document.getElementById('date-form');
    if (!input || !form) return;

    input.addEventListener('click', () => {
        if (input.showPicker) { try { input.showPicker(); } catch (e) {} }
    });

    input.addEventListener('change', () => {
        if (input.value) form.submit();
    });
})();
(function () {
    const input = document.getElementById('date-input');
    const form = document.getElementById('date-form');
    if (!input || !form) return;

    // open the calendar when the button is clicked
    input.addEventListener('click', () => {
        if (input.showPicker) {
            try { input.showPicker(); } catch (e) {}
        }
    });

    // when a day is chosen, reload with that day
    input.addEventListener('change', () => {
        if (input.value) form.submit();
    });
})();
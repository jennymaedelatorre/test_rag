document.addEventListener("DOMContentLoaded", () => {
    const toastEl = document.getElementById('loginToast');
    if (toastEl && toastEl.dataset.message) {
        // Ensure the toast body has the message
        toastEl.querySelector('.toast-body').innerText = toastEl.dataset.message;

        // Initialize and show the toast
        const toast = new bootstrap.Toast(toastEl, { autohide: true, delay: 5000 });
        toast.show();
    }
});

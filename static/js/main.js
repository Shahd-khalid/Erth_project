document.addEventListener('DOMContentLoaded', () => {
    // Mobile Navigation Toggle
    const navToggle = document.getElementById('navToggle');
    const navRight = document.getElementById('navRight');

    if (navToggle && navRight) {
        navToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            navRight.classList.toggle('active');

            // Toggle body scrolling
            if (navRight.classList.contains('active')) {
                document.body.style.overflow = 'hidden';
                navToggle.innerHTML = '<i class="fas fa-times"></i>';
            } else {
                document.body.style.overflow = '';
                navToggle.innerHTML = '<i class="fas fa-bars"></i>';
            }
        });

        // Close menu when clicking outside
        document.addEventListener('click', (e) => {
            if (navRight.classList.contains('active') && !navRight.contains(e.target) && e.target !== navToggle) {
                navRight.classList.remove('active');
                document.body.style.overflow = '';
                navToggle.innerHTML = '<i class="fas fa-bars"></i>';
            }
        });
    }

    // Input animation handling for forms
    const formControls = document.querySelectorAll('.form-control, .custom-field-wrapper input');
    formControls.forEach(input => {
        // Add active class if input has value on load
        if (input.value.trim() !== '') {
            input.parentElement.classList.add('has-value');
        }

        // Add/remove class on focus/blur
        input.addEventListener('focus', () => {
            input.parentElement.classList.add('is-focused');
        });

        input.addEventListener('blur', () => {
            input.parentElement.classList.remove('is-focused');
            if (input.value.trim() !== '') {
                input.parentElement.classList.add('has-value');
            } else {
                input.parentElement.classList.remove('has-value');
            }
        });
    });
});

document.addEventListener('DOMContentLoaded', () => {
    const PASSWORD_TOGGLE_SELECTOR = 'input[type="password"], input[data-password-toggle-ready="true"][type="text"]';

    function createPasswordToggleButton(input) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'password-toggle-btn';
        button.setAttribute('aria-label', 'إظهار كلمة المرور');
        button.setAttribute('aria-pressed', 'false');
        button.setAttribute('data-password-toggle-button', 'true');
        button.innerHTML = '<i class="fas fa-eye"></i>';

        button.addEventListener('click', () => {
            const isHidden = input.type === 'password';
            input.type = isHidden ? 'text' : 'password';
            button.setAttribute('aria-label', isHidden ? 'إخفاء كلمة المرور' : 'إظهار كلمة المرور');
            button.setAttribute('aria-pressed', isHidden ? 'true' : 'false');
            button.innerHTML = `<i class="fas ${isHidden ? 'fa-eye-slash' : 'fa-eye'}"></i>`;
            input.classList.toggle('is-password-visible', isHidden);
        });

        return button;
    }

    function ensurePasswordShell(input) {
        if (!input || input.dataset.passwordToggleReady === 'true') {
            return;
        }

        let shell = input.closest('.password-field-shell');

        if (!shell) {
            shell = document.createElement('div');
            shell.className = 'password-field-shell';
            input.parentNode.insertBefore(shell, input);
            shell.appendChild(input);
        }

        if (!shell.querySelector('[data-password-toggle-button="true"]')) {
            shell.appendChild(createPasswordToggleButton(input));
        }

        input.dataset.passwordToggleReady = 'true';
        input.classList.add('password-toggle-input');
        shell.classList.add('password-toggle-shell-ready');
    }

    function scanPasswordFields(root = document) {
        root.querySelectorAll(PASSWORD_TOGGLE_SELECTOR).forEach(ensurePasswordShell);
    }

    scanPasswordFields();

    const passwordObserver = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
                if (!(node instanceof HTMLElement)) {
                    return;
                }

                if (node.matches?.(PASSWORD_TOGGLE_SELECTOR)) {
                    ensurePasswordShell(node);
                }

                scanPasswordFields(node);
            });
        });
    });

    passwordObserver.observe(document.body, {
        childList: true,
        subtree: true,
    });

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
        const interactionTarget =
            input.closest('.custom-field-wrapper, .input-v3-container, .input-v3-group, .form-group') ||
            input.parentElement;

        // Add active class if input has value on load
        if (interactionTarget && input.value.trim() !== '') {
            interactionTarget.classList.add('has-value');
        }

        // Add/remove class on focus/blur
        input.addEventListener('focus', () => {
            if (interactionTarget) {
                interactionTarget.classList.add('is-focused');
            }
        });

        input.addEventListener('blur', () => {
            if (interactionTarget) {
                interactionTarget.classList.remove('is-focused');
                if (input.value.trim() !== '') {
                    interactionTarget.classList.add('has-value');
                } else {
                    interactionTarget.classList.remove('has-value');
                }
            }
        });
    });
});

(function () {
    const body = document.body;
    const mainToggle = document.getElementById("theme-toggle");
    const authToggle = document.getElementById("auth-theme-toggle");

    function applyTheme(theme) {
        body.classList.toggle("dark-mode", theme === "dark");
        const icon = theme === "dark" ? "☀️" : "🌙";
        if (mainToggle) mainToggle.textContent = icon;
        if (authToggle) authToggle.textContent = icon;
        localStorage.setItem("campusfind-theme", theme);
    }

    const savedTheme = localStorage.getItem("campusfind-theme") || "light";
    applyTheme(savedTheme);

    [mainToggle, authToggle].forEach(function (button) {
        if (!button) return;
        button.addEventListener("click", function () {
            const isDark = body.classList.contains("dark-mode");
            applyTheme(isDark ? "light" : "dark");
        });
    });

    document.querySelectorAll(".password-toggle").forEach(function (button) {
        button.addEventListener("click", function () {
            const input = document.getElementById(button.dataset.target);
            if (!input) return;

            if (input.type === "password") {
                input.type = "text";
                button.textContent = "🙈";
            } else {
                input.type = "password";
                button.textContent = "👁";
            }
        });
    });

    window.setTimeout(function () {
        document.querySelectorAll(".flash").forEach(function (flash) {
            flash.classList.add("flash-hide");
        });
    }, 4500);
})();
// Automatically hide flash messages after 4 seconds
document.addEventListener("DOMContentLoaded", function () {
    const messages = document.querySelectorAll(".flash");

    messages.forEach(function (message) {
        setTimeout(function () {
            message.classList.add("flash-hide");

            setTimeout(function () {
                message.remove();
            }, 500);

        }, 4000);
    });
});

function togglePassword(inputId, button) {
    const input = document.getElementById(inputId);

    if (input.type === "password") {
        input.type = "text";
        button.textContent = "🙈";
        button.setAttribute("aria-label", "Hide password");
    } else {
        input.type = "password";
        button.textContent = "👁";
        button.setAttribute("aria-label", "Show password");
    }
}

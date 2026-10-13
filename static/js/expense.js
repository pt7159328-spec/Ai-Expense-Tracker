```javascript
/**
 * Manual expense form submission for AI Expense Tracker.
 *
 * Keeps the existing POST /add-expense API and Bearer-token authentication.
 * The guard allows this script to be loaded safely on pages without the form.
 */
(() => {
    "use strict";

    const expenseForm = document.getElementById("expenseForm");

    // This script may be shared or included on a page without the expense form.
    if (!expenseForm) {
        return;
    }

    const amountInput = document.getElementById("amount");
    const categoryInput = document.getElementById("category");
    const currencyInput = document.getElementById("currency");
    const dateInput = document.getElementById("date");
    const submitButton = expenseForm.querySelector('button[type="submit"]');

    // Avoid submitting an incomplete form if the page markup changes unexpectedly.
    if (!amountInput || !categoryInput || !currencyInput || !dateInput) {
        console.error("Expense form is missing one or more required fields.");
        return;
    }

    expenseForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        const amount = Number(amountInput.value);
        const category = categoryInput.value.trim();
        const currency = currencyInput.value;
        const date = dateInput.value;

        if (!Number.isFinite(amount) || amount <= 0) {
            alert("Please enter an amount greater than zero.");
            amountInput.focus();
            return;
        }

        if (!category) {
            alert("Please enter an expense category.");
            categoryInput.focus();
            return;
        }

        if (!currency || !date) {
            alert("Please select a currency and expense date.");
            return;
        }

        let token;

        try {
            token = localStorage.getItem("token");
        } catch (error) {
            console.error(
                "Unable to read the login token from local storage.",
                error
            );
            alert(
                "Unable to access your login session. Please enable site storage and log in again."
            );
            return;
        }

        if (!token) {
            alert("Please login first.");
            window.location.href = "/login-page";
            return;
        }

        if (submitButton) {
            submitButton.disabled = true;
            submitButton.setAttribute("aria-busy", "true");
        }

        try {
            const response = await fetch("/add-expense", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({
                    amount,
                    category,
                    currency,
                    date
                })
            });

            if (response.status === 401) {
                alert("Session expired. Please login again.");

                try {
                    // Remove only the auth token; preserve unrelated application storage.
                    localStorage.removeItem("token");
                } catch (storageError) {
                    console.error(
                        "Unable to clear the expired login token.",
                        storageError
                    );
                }

                window.location.href = "/login-page";
                return;
            }

            let result = {};

            try {
                result = await response.json();
            } catch (parseError) {
                // Handle non-JSON server responses.
                result = {};
            }

            if (response.ok) {
                alert(result.msg || "Expense added successfully!");
                expenseForm.reset();
            } else {
                const message =
                    result.msg ||
                    `Unable to add the expense (HTTP ${response.status}).`;

                alert(message);
            }
        } catch (error) {
            alert("Unable to connect to the server. Please try again.");
            console.error("Expense submission failed:", error);
        } finally {
            if (submitButton) {
                submitButton.disabled = false;
                submitButton.removeAttribute("aria-busy");
            }
        }
    });
})();
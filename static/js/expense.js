document.getElementById("expenseForm").addEventListener("submit", async function(e) {
    e.preventDefault();

    const amount = document.getElementById("amount").value;
    const category = document.getElementById("category").value;
    const currency = document.getElementById("currency").value;
    const date = document.getElementById("date").value;

    const token = localStorage.getItem("token");

    if (!token) {
        alert("Please login first");
        window.location.href = "/login-page";
        return;
    }

    try {
        const response = await fetch("/add-expense", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({
            amount,
            category,
            currency,
            date
            })
        });

        // ✅ TOKEN EXPIRE HANDLE
        if (response.status === 401) {
            alert("Session expired. Please login again.");
            localStorage.clear();
            window.location.href = "/login-page";
            return;
        }

        const result = await response.json();

        if (response.ok) {
            alert("✅ Expense added successfully!");

            document.getElementById("expenseForm").reset();

        } else {
            alert("❌ " + result.msg);
        }

    } catch (error) {
        alert("Server error");
        console.error(error);
    }
});
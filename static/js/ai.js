async function loadAI() {
    const token = localStorage.getItem("token");

    if (!token) {
        alert("Please login first");
        window.location.href = "/login-page";
        return;
    }

    const totalElement = document.getElementById("total");
    const categoryElement = document.getElementById("category");
    const alertElement = document.getElementById("alert");
    const suggestionElement = document.getElementById("suggestion");

    // Show a loading state while fetching the analysis.
    if (totalElement) totalElement.textContent = "Loading...";
    if (categoryElement) categoryElement.textContent = "Loading...";
    if (alertElement) alertElement.textContent = "Loading...";
    if (suggestionElement) suggestionElement.textContent = "Loading...";

    try {
        const response = await fetch("/ai-spending-analysis", {
            method: "GET",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Accept": "application/json"
            }
        });

        // Handle an expired or invalid login session.
        if (response.status === 401) {
            localStorage.removeItem("token");
            alert("Your session has expired. Please login again.");
            window.location.href = "/login-page";
            return;
        }

        let data;

        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error("The server returned an invalid response.");
        }

        if (!response.ok) {
            throw new Error(
                data?.detail ||
                data?.message ||
                "Unable to load AI spending analysis."
            );
        }

        // Update the existing analysis fields safely.
        if (totalElement) {
            const totalSpent = Number(data.total_spent ?? 0);

            totalElement.textContent = Number.isFinite(totalSpent)
                ? "₹" + totalSpent.toLocaleString("en-IN", {
                    maximumFractionDigits: 2
                })
                : "₹0";
        }

        if (categoryElement) {
            categoryElement.textContent =
                data.highest_spending_category || "N/A";
        }

        if (alertElement) {
            alertElement.textContent = data.alert || "No alert";
        }

        if (suggestionElement) {
            suggestionElement.textContent =
                data.suggestion || "No suggestion";
        }

    } catch (error) {
        console.error("Error loading AI spending analysis:", error);

        if (totalElement) totalElement.textContent = "Unavailable";
        if (categoryElement) categoryElement.textContent = "Unavailable";
        if (alertElement) alertElement.textContent = "Unavailable";
        if (suggestionElement) suggestionElement.textContent = "Unavailable";

        alert(
            error.message ||
            "Server error. Please try again later."
        );
    }
}

// Automatically load AI analysis when the page opens.
loadAI();
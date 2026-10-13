async function loadSummary() {
    const token = localStorage.getItem("token");

    if (!token) {
        alert("Please login first");
        window.location.href = "/login-page";
        return;
    }

    // Read the existing summary filters.
    const startDate = document.getElementById("startDate")?.value || "";
    const endDate = document.getElementById("endDate")?.value || "";
    const category = document.getElementById("category")?.value || "";

    // Build query parameters safely.
    const params = new URLSearchParams();

    if (startDate) {
        params.set("start", startDate);
    }

    if (endDate) {
        params.set("end", endDate);
    }

    if (category) {
        params.set("category", category);
    }

    const queryString = params.toString();
    const url = queryString
        ? `/expense-summary?${queryString}`
        : "/expense-summary";

    try {
        const response = await fetch(url, {
            method: "GET",
            headers: {
                Authorization: `Bearer ${token}`,
                Accept: "application/json"
            }
        });

        // Redirect to login if the session has expired.
        if (response.status === 401) {
            alert("Your session has expired. Please login again.");
            localStorage.removeItem("token");
            window.location.href = "/login-page";
            return;
        }

        // Handle responses that do not contain valid JSON.
        let data;

        try {
            data = await response.json();
        } catch (parseError) {
            throw new Error("The server returned an invalid response.");
        }

        if (!response.ok) {
            const message =
                data?.detail ||
                data?.message ||
                "Failed to load summary. Please try again.";

            throw new Error(message);
        }

        // Safely display the existing summary metrics.
        const metrics = [
            ["total", data.total_expense],
            ["count", data.total_transactions],
            ["avg", data.average_expense],
            ["high", data.highest_expense],
            ["low", data.lowest_expense]
        ];

        metrics.forEach(([elementId, value]) => {
            const element = document.getElementById(elementId);

            if (element) {
                element.textContent = value ?? 0;
            }
        });
    } catch (error) {
        console.error("Error loading expense summary:", error);

        alert(
            error.message ||
            "Unable to load the summary. Please check your connection and try again."
        );
    }
}

// Automatically load the summary when the page opens.
loadSummary();
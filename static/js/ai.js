async function loadAI() {

    const token = localStorage.getItem("token");

    if (!token) {
        alert("Please login first");
        window.location.href = "/login-page";
        return;
    }

    try {
        const response = await fetch("http://127.0.0.1:5000/ai-spending-analysis", {
            method: "GET",
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        const data = await response.json();
        console.log("AI DATA:", data);

        if (response.ok) {

            document.getElementById("total").innerText =
                "₹" + (data.total_spent || 0);

            document.getElementById("category").innerText =
                data.highest_spending_category || "N/A";

            document.getElementById("alert").innerText =
                data.alert || "No alert";

            document.getElementById("suggestion").innerText =
                data.suggestion || "No suggestion";

        } else {
            document.getElementById("total").innerText = "Error";
        }

    } catch (error) {
        console.error(error);
        alert("Server error");
    }
}

// AUTO LOAD
loadAI();
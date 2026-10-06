async function loadSummary() {

    const token = localStorage.getItem("token");

    if (!token) {
        alert("Please login first");
        window.location.href = "/login-page";
        return;
    }

    // GET FILTER VALUES
    const startDate = document.getElementById("startDate").value;
    const endDate = document.getElementById("endDate").value;
    const category = document.getElementById("category").value;

    let url = "http://127.0.0.1:5000/expense-summary";

    // BUILD QUERY PARAMS
    const params = [];

    if (startDate) params.push(`start=${startDate}`);
    if (endDate) params.push(`end=${endDate}`);
    if (category) params.push(`category=${category}`);

    if (params.length > 0) {
        url += "?" + params.join("&");
    }

    try {
        const response = await fetch(url, {
            method: "GET",
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        const data = await response.json();

        if (response.ok) {

            document.getElementById("total").innerText = data.total_expense || 0;
            document.getElementById("count").innerText = data.total_transactions || 0;
            document.getElementById("avg").innerText = data.average_expense || 0;
            document.getElementById("high").innerText = data.highest_expense || 0;
            document.getElementById("low").innerText = data.lowest_expense || 0;

        } else {
            alert("❌ Failed to load summary");
        }

    } catch (error) {
        console.error(error);
        alert("⚠️ Server error");
    }
}

// AUTO LOAD ON PAGE OPEN
loadSummary();
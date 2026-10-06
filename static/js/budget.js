// SET BUDGET
async function setBudget() {

    const month = document.getElementById("month").value;
    const amount = document.getElementById("amount").value;
    const token = localStorage.getItem("token");

    if (!month || !amount) {
        alert("Please fill all fields");
        return;
    }

    try {
        const res = await fetch("http:///set-budget", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({ month, amount })
        });

        const data = await res.json();
        alert(data.msg);

        // after setting → auto refresh alert
        getAlert();

    } catch (error) {
        console.error(error);
        alert("Error setting budget");
    }
}


// GET ALERT (MAIN DISPLAY)
async function getAlert() {

    const month = document.getElementById("month").value;
    const token = localStorage.getItem("token");

    if (!month) return;

    try {
        const res = await fetch(`http:///budget-alert/${month}`, {
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        const data = await res.json();
        console.log("BUDGET DATA:", data);

        const spent = data.spent || 0;
        const budget = data.budget || 0;
        const remaining = budget - spent;

        document.getElementById("spent").innerText = "₹" + spent;
        document.getElementById("budget").innerText = "₹" + budget;
        document.getElementById("remaining").innerText = "₹" + remaining;
        document.getElementById("alert").innerText = data.alert || "No data";

    } catch (error) {
        console.error(error);
        alert("Error loading budget");
    }
}


// DELETE BUDGET
async function deleteBudget() {

    const month = document.getElementById("month").value;
    const token = localStorage.getItem("token");

    if (!month) {
        alert("Select month first");
        return;
    }

    try {
        const res = await fetch(`http:///delete-budget/${month}`, {
            method: "DELETE",
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        const data = await res.json();
        alert(data.msg);

        // clear UI
        document.getElementById("spent").innerText = "₹0";
        document.getElementById("budget").innerText = "₹0";
        document.getElementById("remaining").innerText = "₹0";
        document.getElementById("alert").innerText = "No data";

    } catch (error) {
        console.error(error);
        alert("Error deleting budget");
    }
}


// AUTO LOAD WHEN MONTH CHANGES
document.getElementById("month").addEventListener("change", getAlert);
// AUTO LOAD BUDGET WHEN PAGE OPENS
window.addEventListener("DOMContentLoaded", function () {
    const monthInput = document.getElementById("month");

    if (!monthInput.value) {
        const now = new Date();
        const month = now.getFullYear() + "-" +
            String(now.getMonth() + 1).padStart(2, "0");

        monthInput.value = month;
    }

    getAlert();
});
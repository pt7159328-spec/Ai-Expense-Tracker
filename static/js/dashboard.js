// SIDEBAR TOGGLE
function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");

    if (sidebar.style.left === "0px") {
        sidebar.style.left = "-260px";
    } else {
        sidebar.style.left = "0px";
    }
}

// CLICK OUTSIDE CLOSE
document.addEventListener("click", function (event) {
    const sidebar = document.getElementById("sidebar");
    const menuBtn = document.querySelector(".menu-btn");

    if (
        sidebar.style.left === "0px" &&
        !sidebar.contains(event.target) &&
        !menuBtn.contains(event.target)
    ) {
        sidebar.style.left = "-260px";
    }
});

// 🔐 TOKEN CHECK
const token = localStorage.getItem("token");

if (!token) {
    alert("Please login first");
    window.location.href = "/login-page";
}

// 👤 USER NAME SHOW (FIXED)
const name = localStorage.getItem("name");  // 🔥 change here

if (name) {
    document.getElementById("username").innerText = name;
} else {
    document.getElementById("username").innerText = "User";
}

// 📊 DASHBOARD DATA LOAD
async function loadDashboardData() {

    try {
        const response = await fetch("/expense-summary", {
            method: "GET",
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        // 🔥 TOKEN EXPIRE HANDLE
        if (response.status === 401) {
            alert("Session expired. Please login again.");
            localStorage.clear();
            window.location.href = "/login-page";
            return;
        }

        const data = await response.json();

        if (response.ok) {

            document.getElementById("total").innerText =
                data.total_expense || 0;

            document.getElementById("count").innerText =
                data.total_transactions || 0;

            document.getElementById("avg").innerText =
                data.average_expense || 0;

        } else {
            alert("Error loading dashboard data");
        }

    } catch (error) {
        console.error("Dashboard Error:", error);
        alert("Server error");
    }
}

// 🚀 LOAD DATA
loadDashboardData();

// 🚪 LOGOUT
function logout() {
    localStorage.clear();
    window.location.href = "/";
}
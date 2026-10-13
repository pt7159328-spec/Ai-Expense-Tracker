"use strict";

// ==========================================
// SIDEBAR TOGGLE
// ==========================================

function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebarOverlay");
    const menuBtn = document.getElementById("menuButton");

    if (!sidebar) return;

    const isOpen = sidebar.classList.contains("sidebar-open")
        || sidebar.style.left === "0px";

    const shouldOpen = !isOpen;

    sidebar.classList.toggle("sidebar-open", shouldOpen);

    if (overlay) {
        overlay.classList.toggle("overlay-visible", shouldOpen);
    }

    // Support the original sidebar layout as well.
    sidebar.style.left = shouldOpen ? "0px" : "-260px";

    if (menuBtn) {
        menuBtn.setAttribute("aria-expanded", String(shouldOpen));
    }
}

// ==========================================
// CLOSE SIDEBAR ON OUTSIDE CLICK
// ==========================================

document.addEventListener("click", function (event) {
    const sidebar = document.getElementById("sidebar");
    const menuBtn = document.getElementById("menuButton")
        || document.querySelector(".menu-btn");
    const overlay = document.getElementById("sidebarOverlay");

    if (!sidebar) return;

    const isOpen = sidebar.classList.contains("sidebar-open")
        || sidebar.style.left === "0px";

    if (
        isOpen &&
        !sidebar.contains(event.target) &&
        !(menuBtn && menuBtn.contains(event.target)) &&
        !(overlay && overlay.contains(event.target))
    ) {
        sidebar.classList.remove("sidebar-open");
        sidebar.style.left = "-260px";

        if (overlay) {
            overlay.classList.remove("overlay-visible");
        }

        if (menuBtn) {
            menuBtn.setAttribute("aria-expanded", "false");
        }
    }
});

// ==========================================
// CLOSE SIDEBAR WITH ESCAPE
// ==========================================

document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;

    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebarOverlay");
    const menuBtn = document.getElementById("menuButton");

    if (!sidebar) return;

    sidebar.classList.remove("sidebar-open");
    sidebar.style.left = "-260px";

    if (overlay) {
        overlay.classList.remove("overlay-visible");
    }

    if (menuBtn) {
        menuBtn.setAttribute("aria-expanded", "false");
    }
});

// ==========================================
// TOKEN CHECK
// ==========================================

const token = localStorage.getItem("token");

if (!token) {
    alert("Please login first");
    window.location.href = "/login-page";
}

// ==========================================
// DISPLAY LOGGED-IN USER NAME
// ==========================================

const name = localStorage.getItem("name");
const usernameElement = document.getElementById("username");

if (usernameElement) {
    usernameElement.innerText = name || "User";
}

// ==========================================
// LOAD DASHBOARD DATA
// ==========================================

async function loadDashboardData() {
    if (!token) return;

    try {
        const response = await fetch("/expense-summary", {
            method: "GET",
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        // Handle expired session.
        if (response.status === 401) {
            alert("Session expired. Please login again.");
            localStorage.clear();
            window.location.href = "/login-page";
            return;
        }

        const data = await response.json();

        if (response.ok) {
            const totalElement = document.getElementById("total");
            const countElement = document.getElementById("count");
            const averageElement = document.getElementById("avg");

            if (totalElement) {
                totalElement.innerText = data.total_expense || 0;
            }

            if (countElement) {
                countElement.innerText = data.total_transactions || 0;
            }

            if (averageElement) {
                averageElement.innerText = data.average_expense || 0;
            }
        } else {
            alert("Error loading dashboard data");
        }
    } catch (error) {
        console.error("Dashboard Error:", error);
        alert("Server error");
    }
}

// ==========================================
// LOAD DATA
// ==========================================

loadDashboardData();

// ==========================================
// LOGOUT
// ==========================================

function logout() {
    localStorage.clear();
    window.location.href = "/";
}
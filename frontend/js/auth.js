// ================= REGISTER =================
document.getElementById("registerForm")?.addEventListener("submit", async function(e) {
    e.preventDefault();

    const name = document.getElementById("name").value;
    const email = document.getElementById("email").value;
    const password = document.getElementById("password").value;

    try {
        const response = await fetch("http://127.0.0.1:5000/register", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ name, email, password })
        });

        const result = await response.json();

        if (response.ok) {
            alert("✅ Registration successful!");

            // 🔐 Save user data
            localStorage.setItem("username", name);
            localStorage.setItem("userEmail", email);

            // 👉 Redirect
            window.location.href = "dashboard.html";

        } else {
            alert("❌ " + result.msg);
        }

    } catch (error) {
        alert("Server error!");
        console.error(error);
    }
});


// ================= LOGIN =================
document.getElementById("loginForm")?.addEventListener("submit", async function(e) {
    e.preventDefault();

    const email = document.getElementById("loginEmail").value;
    const password = document.getElementById("loginPassword").value;

    try {
        const response = await fetch("http://127.0.0.1:5000/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ email, password })
        });

        const result = await response.json();

        if (response.ok) {
            alert("✅ Login successful!");

            // 🔐 Save token + REAL USER NAME
            localStorage.setItem("token", result.access_token);
            localStorage.setItem("name", result.name);   // 🔥 FIX
            localStorage.setItem("userEmail", email);

            // 👉 Redirect
            window.location.href = "dashboard.html";

        } else {
            alert("❌ " + result.msg);
        }

    } catch (error) {
        alert("Server error!");
        console.error(error);
    }
});
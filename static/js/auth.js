// ================= REGISTER =================

document.getElementById("registerForm")?.addEventListener("submit", async function (e) {
    e.preventDefault();

    const name = document.getElementById("name").value.trim();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;

    if (!name || !email || !password) {
        alert("Please fill all fields.");
        return;
    }

    try {
        const response = await fetch("/register", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                name: name,
                email: email,
                password: password
            })
        });

        const result = await response.json();

        if (response.ok) {

            // Save authentication token
            if (result.access_token) {
                localStorage.setItem("token", result.access_token);
            }

            // Save user information
            localStorage.setItem("name", result.name || name);
            localStorage.setItem("username", result.name || name);
            localStorage.setItem("userEmail", email);

            alert("✅ Registration successful!");

            // Go to dashboard through Flask
            window.location.href = "/dashboard-page";

        } else {
            alert("❌ " + (result.msg || "Registration failed."));
        }

    } catch (error) {
        console.error("Registration error:", error);
        alert("❌ Server error! Please try again.");
    }
});


// ================= LOGIN =================

document.getElementById("loginForm")?.addEventListener("submit", async function (e) {
    e.preventDefault();

    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value;

    if (!email || !password) {
        alert("Please enter email and password.");
        return;
    }

    try {
        const response = await fetch("/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                email: email,
                password: password
            })
        });

        const result = await response.json();

        if (response.ok) {

            // Save JWT token
            localStorage.setItem("token", result.access_token);

            // Save user information
            localStorage.setItem("name", result.name || "");
            localStorage.setItem("username", result.name || "");
            localStorage.setItem("userEmail", email);

            alert("✅ Login successful!");

            // Go to dashboard through Flask
            window.location.href = "/dashboard-page";

        } else {
            alert("❌ " + (result.msg || "Invalid credentials."));
        }

    } catch (error) {
        console.error("Login error:", error);
        alert("❌ Server error! Please try again.");
    }
});
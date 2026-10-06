function getCurrencySymbol(currency) {

    const symbols = {
        INR: "₹",
        USD: "$",
        EUR: "€",
        GBP: "£",
        AED: "د.إ"
    };

    if (!currency) {
        return "₹";
    }

    return symbols[currency] || "₹";
}
async function loadExpenses() {

    const token = localStorage.getItem("token");

    if (!token) {
        alert("Please login first");
        window.location.href = "/login-page";
        return;
    }

    try {

        const response = await fetch("/expenses", {
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        if (response.status === 401) {
            alert("Session expired. Please login again.");
            localStorage.clear();
            window.location.href = "/login-page";
            return;
        }

        const data = await response.json();

        const table = document.getElementById("expenseTable");
        const noData = document.getElementById("noData");
        const wrapper = document.getElementById("expenseTableWrapper");

        table.innerHTML = "";

        if (data.length === 0) {
            wrapper.style.display = "none";
            noData.style.display = "block";
            return;
        }

        noData.style.display = "none";
        wrapper.style.display = "table";

        data.forEach(exp => {
            const row = `
                <tr>
                    <td>${getCurrencySymbol(exp.currency)}${exp.amount}</td>
                    <td>${exp.category}</td>
                    <td>${exp.date}</td>
                    <td>
                        <button class="action-btn edit" onclick="editExpense('${exp._id}', '${exp.category}', '${exp.amount}', '${exp.date}')">Edit</button>

                        <button class="action-btn delete" onclick="deleteExpense('${exp._id}')">Delete</button>
                    </td>
                </tr>
            `;

            table.innerHTML += row;
        });

    } catch (error) {
        alert("Error loading data");
        console.error(error);
    }
}


// 🔴 DELETE FUNCTION
async function deleteExpense(id) {

    const token = localStorage.getItem("token");

    if (!confirm("Delete this expense?")) return;

    try {

        const response = await fetch(`/delete-expense/${id}`, {
            method: "DELETE",
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        if (response.status === 401) {
            alert("Session expired");
            localStorage.clear();
            window.location.href = "/login-page";
            return;
        }

        if (response.ok) {
            alert("Deleted!");
            loadExpenses();
        }

    } catch (error) {
        alert("Delete failed");
    }
}


// 🟡 EDIT FUNCTION
async function editExpense(id, category, amount, date) {

    const newAmount = prompt("New amount:", amount);
    const newCategory = prompt("New category:", category);
    const newDate = prompt("New date:", date);

    if (!newAmount || !newCategory || !newDate) return;

    const token = localStorage.getItem("token");

    try {

        const response = await fetch(`/update-expense/${id}`, {
            method: "PUT",
            headers: {
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token
            },
            body: JSON.stringify({
                amount: newAmount,
                category: newCategory,
                date: newDate
            })
        });

        if (response.status === 401) {
            alert("Session expired");
            localStorage.clear();
            window.location.href = "/login-page";
            return;
        }

        if (response.ok) {
            alert("Updated!");
            loadExpenses();
        }

    } catch (error) {
        alert("Update failed");
    }
}


// ================================
// LOAD USER CATEGORIES
// ================================
async function loadCategories() {

    const token = localStorage.getItem("token");

    try {

        const response = await fetch("/user-categories", {
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        const data = await response.json();

        const categoryFilter = document.getElementById("categoryFilter");

        data.forEach(cat => {

            categoryFilter.innerHTML += `
                <option value="${cat}">${cat}</option>
            `;
        });

    } catch (error) {
        console.log(error);
    }
}


// ================================
// FILTER EXPENSES
// ================================
async function filterExpenses() {

    const token = localStorage.getItem("token");

    const fromDate = document.getElementById("fromDate").value;
    const toDate = document.getElementById("toDate").value;
    const category = document.getElementById("categoryFilter").value;
    const currency = document.getElementById("currencyFilter").value;

    let url = `/filter-expenses?`;

    if (fromDate && toDate) {
        url += `from_date=${fromDate}&to_date=${toDate}&`;
    }

    if (category) {
    url += `category=${category}&`;
}

if (currency) {
    url += `currency=${currency}&`;
}

    try {

        const response = await fetch(url, {
            headers: {
                "Authorization": "Bearer " + token
            }
        });

        const data = await response.json();

        const table = document.getElementById("expenseTable");
        const noData = document.getElementById("noData");
        const wrapper = document.getElementById("expenseTableWrapper");

        table.innerHTML = "";

        if (data.length === 0) {
            wrapper.style.display = "none";
            noData.style.display = "block";
            return;
        }

        noData.style.display = "none";
        wrapper.style.display = "table";

        data.forEach(exp => {

            console.log(exp);

            const row = `
                <tr>
                    <td>${getCurrencySymbol(exp.currency)}${exp.amount}</td>
                    <td>${exp.category}</td>
                    <td>${exp.date}</td>
                    <td>
                        <button class="action-btn edit" onclick="editExpense('${exp._id}', '${exp.category}', '${exp.amount}', '${exp.date}')">Edit</button>

                        <button class="action-btn delete" onclick="deleteExpense('${exp._id}')">Delete</button>
                    </td>
                </tr>
            `;

            table.innerHTML += row;
        });

    } catch (error) {
        console.log(error);
    }
}


// ================================
// DOWNLOAD PDF
// ================================
function downloadPDF() {

    const token = localStorage.getItem("token");

    const fromDate = document.getElementById("fromDate").value;
    const toDate = document.getElementById("toDate").value;
    const category = document.getElementById("categoryFilter").value;

    let url = `/report-pdf?`;

    if (fromDate && toDate) {
        url += `from_date=${fromDate}&to_date=${toDate}&`;
    }

    if (category) {
        url += `category=${category}`;
    }

    fetch(url, {
        method: "GET",
        headers: {
            "Authorization": "Bearer " + token
        }
    })
    .then(response => response.blob())
    .then(blob => {

        const blobUrl = window.URL.createObjectURL(blob);

        const link = document.createElement("a");

        link.href = blobUrl;
        link.download = "expense_report.pdf";

        document.body.appendChild(link);

        link.click();

        document.body.removeChild(link);

        window.URL.revokeObjectURL(blobUrl);

    })
    .catch(error => {
        console.log(error);
        alert("PDF download failed");
    });
}


// ================================
// BUTTON EVENTS
// ================================
document.getElementById("filterBtn")
.addEventListener("click", filterExpenses);
document.getElementById("pdfBtn")
.addEventListener("click", downloadPDF);


// ================================
// CALL
// ================================
loadExpenses();
loadCategories();
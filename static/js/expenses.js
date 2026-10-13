"use strict";

// ================================
// CURRENCY SYMBOLS
// ================================
function getCurrencySymbol(currency) {
    const symbols = {
        INR: "₹",
        USD: "$",
        EUR: "€",
        GBP: "£",
        AED: "د.إ"
    };

    return symbols[currency] || "₹";
}


// ================================
// AUTHENTICATION HELPERS
// ================================
function getAuthToken() {
    return localStorage.getItem("token");
}

function redirectToLogin(message) {
    if (message) {
        alert(message);
    }

    localStorage.removeItem("token");
    window.location.href = "/login-page";
}

async function handleUnauthorized(response) {
    if (response.status !== 401) {
        return false;
    }

    redirectToLogin("Session expired. Please login again.");
    return true;
}

async function getJsonResponse(response) {
    if (!response.ok) {
        throw new Error(`Request failed (${response.status})`);
    }

    return response.json();
}


// ================================
// EXPENSE TABLE RENDERING
// ================================
function renderExpenses(expenses) {
    const table = document.getElementById("expenseTable");
    const noData = document.getElementById("noData");
    const wrapper = document.getElementById("expenseTableWrapper");

    if (!table || !noData || !wrapper) {
        console.error("Expense table elements were not found.");
        return;
    }

    table.replaceChildren();

    if (!Array.isArray(expenses) || expenses.length === 0) {
        wrapper.style.display = "none";
        noData.style.display = "block";
        return;
    }

    noData.style.display = "none";
    wrapper.style.display = "table";

    const fragment = document.createDocumentFragment();

    expenses.forEach((expense) => {
        const row = document.createElement("tr");

        const amountCell = document.createElement("td");
        amountCell.textContent =
            `${getCurrencySymbol(expense.currency)}${expense.amount ?? ""}`;

        const categoryCell = document.createElement("td");
        categoryCell.textContent = expense.category ?? "";

        const dateCell = document.createElement("td");
        dateCell.textContent = expense.date ?? "";

        const actionCell = document.createElement("td");

        const editButton = document.createElement("button");
        editButton.type = "button";
        editButton.className = "action-btn edit";
        editButton.textContent = "Edit";

        editButton.addEventListener("click", () => {
            editExpense(
                expense._id,
                expense.category ?? "",
                expense.amount ?? "",
                expense.date ?? ""
            );
        });

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "action-btn delete";
        deleteButton.textContent = "Delete";

        deleteButton.addEventListener("click", () => {
            deleteExpense(expense._id);
        });

        actionCell.append(editButton, deleteButton);
        row.append(amountCell, categoryCell, dateCell, actionCell);
        fragment.appendChild(row);
    });

    table.appendChild(fragment);
}


// ================================
// LOAD EXPENSES
// ================================
async function loadExpenses() {
    const token = getAuthToken();

    if (!token) {
        redirectToLogin("Please login first.");
        return;
    }

    try {
        const response = await fetch("/expenses", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (await handleUnauthorized(response)) {
            return;
        }

        const data = await getJsonResponse(response);

        if (!Array.isArray(data)) {
            throw new Error("Unexpected expenses response.");
        }

        renderExpenses(data);
    } catch (error) {
        console.error("Error loading expenses:", error);
        alert("Unable to load expenses. Please try again.");
    }
}


// ================================
// DELETE EXPENSE
// ================================
async function deleteExpense(id) {
    if (!id) {
        alert("Unable to identify this expense.");
        return;
    }

    if (!confirm("Delete this expense?")) {
        return;
    }

    const token = getAuthToken();

    if (!token) {
        redirectToLogin("Please login first.");
        return;
    }

    try {
        const response = await fetch(
            `/delete-expense/${encodeURIComponent(id)}`,
            {
                method: "DELETE",
                headers: {
                    "Authorization": `Bearer ${token}`
                }
            }
        );

        if (await handleUnauthorized(response)) {
            return;
        }

        if (!response.ok) {
            throw new Error(`Delete failed (${response.status})`);
        }

        alert("Expense deleted successfully.");
        await loadExpenses();
    } catch (error) {
        console.error("Error deleting expense:", error);
        alert("Delete failed. Please try again.");
    }
}


// ================================
// EDIT EXPENSE
// ================================
async function editExpense(id, category, amount, date) {
    if (!id) {
        alert("Unable to identify this expense.");
        return;
    }

    const newAmount = prompt("New amount:", amount);
    if (newAmount === null) return;

    const trimmedAmount = newAmount.trim();

    if (!trimmedAmount || !Number.isFinite(Number(trimmedAmount)) ||
        Number(trimmedAmount) <= 0) {
        alert("Please enter a valid amount greater than zero.");
        return;
    }

    const newCategory = prompt("New category:", category);
    if (newCategory === null) return;

    const trimmedCategory = newCategory.trim();

    if (!trimmedCategory) {
        alert("Category cannot be empty.");
        return;
    }

    const newDate = prompt("New date (YYYY-MM-DD):", date);
    if (newDate === null) return;

    const trimmedDate = newDate.trim();

    if (!trimmedDate) {
        alert("Date cannot be empty.");
        return;
    }

    const token = getAuthToken();

    if (!token) {
        redirectToLogin("Please login first.");
        return;
    }

    try {
        const response = await fetch(
            `/update-expense/${encodeURIComponent(id)}`,
            {
                method: "PUT",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token}`
                },
                body: JSON.stringify({
                    amount: trimmedAmount,
                    category: trimmedCategory,
                    date: trimmedDate
                })
            }
        );

        if (await handleUnauthorized(response)) {
            return;
        }

        if (!response.ok) {
            throw new Error(`Update failed (${response.status})`);
        }

        alert("Expense updated successfully.");
        await loadExpenses();
    } catch (error) {
        console.error("Error updating expense:", error);
        alert("Update failed. Please try again.");
    }
}


// ================================
// LOAD USER CATEGORIES
// ================================
async function loadCategories() {
    const token = getAuthToken();

    if (!token) {
        return;
    }

    const categoryFilter = document.getElementById("categoryFilter");

    if (!categoryFilter) {
        return;
    }

    try {
        const response = await fetch("/user-categories", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (await handleUnauthorized(response)) {
            return;
        }

        const categories = await getJsonResponse(response);

        if (!Array.isArray(categories)) {
            throw new Error("Unexpected categories response.");
        }

        // Keep the existing default option and avoid duplicate categories.
        const existingValues = new Set(
            Array.from(categoryFilter.options, (option) => option.value)
        );

        categories.forEach((category) => {
            if (typeof category !== "string" || !category.trim()) {
                return;
            }

            if (existingValues.has(category)) {
                return;
            }

            const option = document.createElement("option");
            option.value = category;
            option.textContent = category;

            categoryFilter.appendChild(option);
            existingValues.add(category);
        });
    } catch (error) {
        console.error("Error loading categories:", error);
    }
}


// ================================
// BUILD FILTER QUERY
// ================================
function buildExpenseFilterQuery() {
    const params = new URLSearchParams();

    const fromDate =
        document.getElementById("fromDate")?.value || "";

    const toDate =
        document.getElementById("toDate")?.value || "";

    const category =
        document.getElementById("categoryFilter")?.value || "";

    const currency =
        document.getElementById("currencyFilter")?.value || "";

    if (fromDate && toDate) {
        params.set("from_date", fromDate);
        params.set("to_date", toDate);
    }

    if (category) {
        params.set("category", category);
    }

    if (currency) {
        params.set("currency", currency);
    }

    return params;
}


// ================================
// FILTER EXPENSES
// ================================
async function filterExpenses() {
    const token = getAuthToken();

    if (!token) {
        redirectToLogin("Please login first.");
        return;
    }

    const params = buildExpenseFilterQuery();
    const query = params.toString();
    const url = query ? `/filter-expenses?${query}` : "/filter-expenses";

    try {
        const response = await fetch(url, {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (await handleUnauthorized(response)) {
            return;
        }

        const data = await getJsonResponse(response);

        if (!Array.isArray(data)) {
            throw new Error("Unexpected filtered expenses response.");
        }

        renderExpenses(data);
    } catch (error) {
        console.error("Error filtering expenses:", error);
        alert("Unable to filter expenses. Please try again.");
    }
}


// ================================
// DOWNLOAD PDF REPORT
// ================================
async function downloadPDF() {
    const token = getAuthToken();

    if (!token) {
        redirectToLogin("Please login first.");
        return;
    }

    const params = new URLSearchParams();

    const fromDate =
        document.getElementById("fromDate")?.value || "";

    const toDate =
        document.getElementById("toDate")?.value || "";

    const category =
        document.getElementById("categoryFilter")?.value || "";

    if (fromDate && toDate) {
        params.set("from_date", fromDate);
        params.set("to_date", toDate);
    }

    if (category) {
        params.set("category", category);
    }

    const query = params.toString();
    const url = query ? `/report-pdf?${query}` : "/report-pdf";

    let blobUrl = null;

    try {
        const response = await fetch(url, {
            method: "GET",
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (await handleUnauthorized(response)) {
            return;
        }

        if (!response.ok) {
            throw new Error(`PDF request failed (${response.status})`);
        }

        const blob = await response.blob();

        if (!blob.size) {
            throw new Error("The PDF response was empty.");
        }

        blobUrl = window.URL.createObjectURL(blob);

        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = "expense_report.pdf";

        document.body.appendChild(link);
        link.click();
        link.remove();
    } catch (error) {
        console.error("Error downloading PDF:", error);
        alert("PDF download failed. Please try again.");
    } finally {
        if (blobUrl) {
            window.URL.revokeObjectURL(blobUrl);
        }
    }
}


// ================================
// INITIALIZE PAGE EVENTS
// ================================
function initializeExpensesPage() {
    const filterButton = document.getElementById("filterBtn");
    const pdfButton = document.getElementById("pdfBtn");

    if (filterButton) {
        filterButton.addEventListener("click", filterExpenses);
    }

    if (pdfButton) {
        pdfButton.addEventListener("click", downloadPDF);
    }

    loadExpenses();
    loadCategories();
}

if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        initializeExpensesPage,
        { once: true }
    );
} else {
    initializeExpensesPage();
}
"use strict";

/*
 * AI Expense Tracker
 * File: static/js/receipt-history.js *
 * Purpose:
 * - Load receipt history from the existing backend API
 * - Display receipt summary cards
 * - Search and filter receipts
 * - Handle loading, empty and error states
 * - Provide client-side pagination
 *
 * Existing backend endpoints used:
 * GET /api/receipts?limit=100
 * GET /api/receipts/insights
 *
 * Authentication:
 * localStorage key: "token"
 */

(() => {
    const API = {
        receipts: "/api/receipts?limit=100",
        insights: "/api/receipts/insights"
    };

    const PAGE_SIZE = 10;

    const state = {
        receipts: [],
        filteredReceipts: [],
        currentPage: 1,
        loading: false,
        requestId: 0
    };

    const elements = {};

    document.addEventListener("DOMContentLoaded", initializeReceiptHistory);

    function initializeReceiptHistory() {
        cacheElements();
        setCurrentYear();
        bindEvents();
        loadReceiptHistory();
    }

    function cacheElements() {
        const ids = [
            "totalReceipts",
            "processedReceipts",
            "totalReceiptAmount",
            "receiptSearch",
            "receiptStatusFilter",
            "receiptDateFilter",
            "clearReceiptFiltersButton",
            "refreshReceiptsButton",
            "receiptHistoryStatus",
            "receiptHistoryLoading",
            "receiptHistoryError",
            "receiptHistoryErrorMessage",
            "retryReceiptHistoryButton",
            "receiptHistoryEmpty",
            "receiptHistoryEmptyHeading",
            "receiptHistoryEmptyMessage",
            "receiptHistoryTableContainer",
            "receiptHistoryTableBody",
            "receiptHistoryPagination",
            "receiptHistoryPaginationInfo",
            "previousReceiptPageButton",
            "nextReceiptPageButton",
            "receiptHistoryPageIndicator",
            "currentYear"
        ];

        ids.forEach((id) => {
            elements[id] = document.getElementById(id);
        });
    }

    function bindEvents() {
        addListener("refreshReceiptsButton", "click", loadReceiptHistory);
        addListener("retryReceiptHistoryButton", "click", loadReceiptHistory);

        addListener("receiptSearch", "input", applyFilters);
        addListener("receiptStatusFilter", "change", applyFilters);
        addListener("receiptDateFilter", "change", applyFilters);

        addListener(
            "clearReceiptFiltersButton",
            "click",
            clearFilters
        );

        addListener(
            "previousReceiptPageButton",
            "click",
            () => changePage(state.currentPage - 1)
        );

        addListener(
            "nextReceiptPageButton",
            "click",
            () => changePage(state.currentPage + 1)
        );
    }

    function addListener(id, eventName, callback) {
        const element = elements[id];

        if (element) {
            element.addEventListener(eventName, callback);
        }
    }

    function setCurrentYear() {
        if (elements.currentYear) {
            elements.currentYear.textContent = String(
                new Date().getFullYear()
            );
        }
    }

    // --------------------------------------------------
    // API AND AUTHENTICATION
    // --------------------------------------------------

    function getToken() {
        return localStorage.getItem("token");
    }

    async function apiRequest(url) {
        const token = getToken();

        if (!token) {
            window.location.href = "/login-page";
            throw new Error("Authentication required.");
        }

        const response = await fetch(url, {
            method: "GET",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Accept": "application/json"
            }
        });

        if (response.status === 401) {
            localStorage.removeItem("token");
            window.location.href = "/login-page";

            throw new Error("Your session has expired. Please log in again.");
        }

        const contentType = response.headers.get("content-type") || "";
        let data = null;

        if (contentType.includes("application/json")) {
            data = await response.json();
        }

        if (!response.ok) {
            const message =
                data?.msg ||
                data?.message ||
                `Request failed (${response.status}).`;

            throw new Error(message);
        }

        return data;
    }

    // --------------------------------------------------
    // LOAD RECEIPT HISTORY
    // --------------------------------------------------

    async function loadReceiptHistory() {
        if (state.loading) {
            return;
        }

        state.loading = true;

        const requestId = ++state.requestId;

        setLoadingState(true);
        hideError();
        hideEmptyState();
        hideStatus();

        try {
            const [receiptResult, insightsResult] = await Promise.all([
                apiRequest(API.receipts),
                apiRequest(API.insights)
            ]);

            // Ignore a response if a newer request has started.
            if (requestId !== state.requestId) {
                return;
            }

            if (!Array.isArray(receiptResult)) {
                throw new Error(
                    "The receipt history API returned an unexpected response."
                );
            }

            state.receipts = receiptResult;
            state.currentPage = 1;

            updateSummary(receiptResult, insightsResult);
            applyFilters();

        } catch (error) {
            if (requestId !== state.requestId) {
                return;
            }

            console.error("Receipt history loading failed:", error);

            showError(
                error.message ||
                "Unable to load receipt history. Please try again."
            );
        } finally {
            if (requestId === state.requestId) {
                state.loading = false;
                setLoadingState(false);
            }
        }
    }

    // --------------------------------------------------
    // SUMMARY CARDS
    // --------------------------------------------------

    function updateSummary(receipts, insights) {
        const total = Number.isFinite(Number(insights?.receipt_count))
            ? Number(insights.receipt_count)
            : receipts.length;

        const processed = receipts.filter((receipt) => {
            return normalizeStatus(receipt.status) === "processed";
        }).length;

        setText("totalReceipts", total);
        setText("processedReceipts", processed);

        const currencies = [
            ...new Set(
                receipts
                    .map((receipt) => receipt.currency)
                    .filter(Boolean)
                    .map((currency) => String(currency).toUpperCase())
            )
        ];

        if (currencies.length > 1) {
            setText("totalReceiptAmount", "Mixed currencies");
            return;
        }

        const currency = currencies[0] || "INR";

        const amount = Number.isFinite(
            Number(insights?.receipt_total_spend)
        )
            ? Number(insights.receipt_total_spend)
            : receipts.reduce((sum, receipt) => {
                return sum + getReceiptAmount(receipt);
            }, 0);

        setText(
            "totalReceiptAmount",
            formatCurrency(amount, currency)
        );
    }

    function setText(id, value) {
        if (elements[id]) {
            elements[id].textContent = String(value);
        }
    }

    function getReceiptAmount(receipt) {
        const amount = Number(receipt?.total_amount);

        return Number.isFinite(amount) ? amount : 0;
    }

    function formatCurrency(amount, currency) {
        const value = Number(amount);

        if (!Number.isFinite(value)) {
            return "—";
        }

        try {
            return new Intl.NumberFormat("en-IN", {
                style: "currency",
                currency: currency || "INR",
                maximumFractionDigits: 2
            }).format(value);
        } catch {
            return `${currency || "INR"} ${value.toFixed(2)}`;
        }
    }

    // --------------------------------------------------
    // SEARCH AND FILTERS
    // --------------------------------------------------

    function clearFilters() {
        if (elements.receiptSearch) {
            elements.receiptSearch.value = "";
        }

        if (elements.receiptStatusFilter) {
            elements.receiptStatusFilter.value = "";
        }

        if (elements.receiptDateFilter) {
            elements.receiptDateFilter.value = "";
        }

        state.currentPage = 1;
        applyFilters();
    }

    function applyFilters() {
        const searchTerm = (
            elements.receiptSearch?.value || ""
        ).trim().toLowerCase();

        const selectedStatus = (
            elements.receiptStatusFilter?.value || ""
        ).toLowerCase();

        const selectedDate = elements.receiptDateFilter?.value || "";

        state.filteredReceipts = state.receipts.filter((receipt) => {
            const merchant = String(receipt.merchant || "").toLowerCase();

            const filename = String(
                receipt.original_filename || ""
            ).toLowerCase();

            const matchesSearch =
                !searchTerm ||
                merchant.includes(searchTerm) ||
                filename.includes(searchTerm);

            const status = normalizeStatus(receipt.status);

            const matchesStatus =
                !selectedStatus ||
                statusMatchesFilter(status, selectedStatus);

            const receiptDate = normalizeDate(receipt.receipt_date);

            const matchesDate =
                !selectedDate ||
                receiptDate === selectedDate;

            return matchesSearch && matchesStatus && matchesDate;
        });

        state.currentPage = 1;
        renderReceiptTable();
    }

    function normalizeStatus(status) {
        const value = String(status || "").trim().toLowerCase();

        if (["processed", "complete", "completed", "success"].includes(value)) {
            return "processed";
        }

        if (
            [
                "pending",
                "needs_review",
                "needs review",
                "review",
                "processing"
            ].includes(value)
        ) {
            return "pending";
        }

        if (["failed", "error", "rejected"].includes(value)) {
            return "failed";
        }

        return value || "unknown";
    }

    function statusMatchesFilter(status, filter) {
        if (filter === "pending") {
            return status === "pending";
        }

        return status === filter;
    }

    function getStatusLabel(status) {
        const normalized = normalizeStatus(status);

        const labels = {
            processed: "Processed",
            pending: "Needs review",
            failed: "Failed",
            unknown: "Unknown"
        };

        return labels[normalized] || normalized;
    }

    function normalizeDate(value) {
        if (!value) {
            return "";
        }

        const stringValue = String(value);

        // Receipt dates may already be in YYYY-MM-DD format.
        if (/^\d{4}-\d{2}-\d{2}$/.test(stringValue)) {
            return stringValue;
        }

        const date = new Date(stringValue);

        if (Number.isNaN(date.getTime())) {
            return "";
        }

        return [
            date.getFullYear(),
            String(date.getMonth() + 1).padStart(2, "0"),
            String(date.getDate()).padStart(2, "0")
        ].join("-");
    }

    function formatDate(value) {
        if (!value) {
            return "—";
        }

        const normalized = normalizeDate(value);

        if (!normalized) {
            return "—";
        }

        const [year, month, day] = normalized.split("-").map(Number);

        const date = new Date(year, month - 1, day);

        return new Intl.DateTimeFormat("en-IN", {
            day: "2-digit",
            month: "short",
            year: "numeric"
        }).format(date);
    }

    function formatDateTime(value) {
        if (!value) {
            return "—";
        }

        const date = new Date(value);

        if (Number.isNaN(date.getTime())) {
            return "—";
        }

        return new Intl.DateTimeFormat("en-IN", {
            day: "2-digit",
            month: "short",
            year: "numeric"
        }).format(date);
    }

    // --------------------------------------------------
    // RECEIPT TABLE
    // --------------------------------------------------

    function renderReceiptTable() {
        const tbody = elements.receiptHistoryTableBody;

        if (!tbody) {
            return;
        }

        tbody.replaceChildren();

        const filtered = state.filteredReceipts;

        if (filtered.length === 0) {
            hideTable();
            hidePagination();

            if (state.receipts.length === 0) {
                showEmptyState(
                    "No Receipts Yet",
                    "Your scanned receipts will appear here once receipt records are available."
                );
            } else {
                showEmptyState(
                    "No Matching Receipts",
                    "No receipts match your current search or filters. Try changing or clearing your filters."
                );
            }

            return;
        }

        hideEmptyState();
        hideError();

        const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

        if (state.currentPage > totalPages) {
            state.currentPage = totalPages;
        }

        const startIndex = (state.currentPage - 1) * PAGE_SIZE;
        const pageReceipts = filtered.slice(
            startIndex,
            startIndex + PAGE_SIZE
        );

        pageReceipts.forEach((receipt) => {
            tbody.appendChild(createReceiptRow(receipt));
        });

        showTable();
        renderPagination(filtered.length, startIndex, pageReceipts.length);
    }

    function createReceiptRow(receipt) {
        const row = document.createElement("tr");

        const merchantCell = document.createElement("td");
        const merchantName = document.createElement("strong");

        merchantName.className = "receipt-merchant-name";
        merchantName.textContent =
            receipt.merchant ||
            receipt.original_filename ||
            "Unknown merchant";

        merchantCell.appendChild(merchantName);

        if (receipt.original_filename && receipt.merchant) {
            const filename = document.createElement("small");

            filename.className = "receipt-filename";
            filename.textContent = receipt.original_filename;

            merchantCell.appendChild(filename);
        }

        const dateCell = document.createElement("td");
        dateCell.textContent = formatDate(receipt.receipt_date);

        const amountCell = document.createElement("td");
        const amount = getReceiptAmount(receipt);
        const currency = receipt.currency || "INR";

        amountCell.textContent = receipt.total_amount == null
            ? "Not detected"
            : formatCurrency(amount, currency);

        const statusCell = document.createElement("td");
        const statusBadge = document.createElement("span");
        const normalizedStatus = normalizeStatus(receipt.status);

        statusBadge.className =
            `receipt-status-badge status-${normalizedStatus.replace(/[^a-z0-9_-]/g, "")}`;

        statusBadge.textContent = getStatusLabel(receipt.status);

        statusCell.appendChild(statusBadge);

        const addedCell = document.createElement("td");
        addedCell.textContent = formatDateTime(receipt.created_at);

        const actionsCell = document.createElement("td");
        const detailsButton = document.createElement("button");

        detailsButton.type = "button";
        detailsButton.className = "receipt-details-button";
        detailsButton.textContent = "Details";
        detailsButton.setAttribute(
            "aria-label",
            `View details for ${receipt.merchant || "receipt"}`
        );

        detailsButton.addEventListener("click", () => {
            showReceiptDetails(receipt);
        });

        actionsCell.appendChild(detailsButton);

        row.append(
            merchantCell,
            dateCell,
            amountCell,
            statusCell,
            addedCell,
            actionsCell
        );

        return row;
    }

    // --------------------------------------------------
    // RECEIPT DETAILS DIALOG
    // --------------------------------------------------

    function showReceiptDetails(receipt) {
        let dialog = document.getElementById("receiptDetailsDialog");

        if (!dialog) {
            dialog = document.createElement("dialog");
            dialog.id = "receiptDetailsDialog";
            dialog.className = "receipt-details-dialog";

            document.body.appendChild(dialog);
        }

        dialog.replaceChildren();

        const heading = document.createElement("h2");
        heading.textContent = "Receipt Details";

        const closeButton = document.createElement("button");
        closeButton.type = "button";
        closeButton.textContent = "Close";
        closeButton.className = "receipt-details-close";
        closeButton.addEventListener("click", () => dialog.close());

        const details = document.createElement("dl");

        const fields = [
            ["Merchant", receipt.merchant || "Unknown merchant"],
            ["Original filename", receipt.original_filename || "—"],
            ["Receipt date", formatDate(receipt.receipt_date)],
            [
                "Amount",
                receipt.total_amount == null
                    ? "Not detected"
                    : formatCurrency(
                        getReceiptAmount(receipt),
                        receipt.currency || "INR"
                    )
            ],
            ["Currency", receipt.currency || "—"],
            ["Status", getStatusLabel(receipt.status)],
            ["Added on", formatDateTime(receipt.created_at)],
            ["Expense ID", receipt.expense_id || "Not linked"]
        ];

        fields.forEach(([label, value]) => {
            const term = document.createElement("dt");
            const description = document.createElement("dd");

            term.textContent = label;
            description.textContent = String(value);

            details.append(term, description);
        });

        const warnings = Array.isArray(receipt.warnings)
            ? receipt.warnings
            : [];

        if (warnings.length > 0) {
            const warningHeading = document.createElement("h3");
            warningHeading.textContent = "Review notes";

            const warningList = document.createElement("ul");

            warnings.forEach((warning) => {
                const item = document.createElement("li");
                item.textContent = String(warning);
                warningList.appendChild(item);
            });

            dialog.append(
                heading,
                closeButton,
                details,
                warningHeading,
                warningList
            );
        } else {
            dialog.append(heading, closeButton, details);
        }

        if (typeof dialog.showModal === "function") {
            if (!dialog.open) {
                dialog.showModal();
            }
        } else {
            // Basic fallback for browsers without dialog support.
            alert(
                fields.map(([label, value]) => `${label}: ${value}`).join("\n")
            );
        }
    }

    // --------------------------------------------------
    // PAGINATION
    // --------------------------------------------------

    function changePage(nextPage) {
        const totalPages = Math.ceil(
            state.filteredReceipts.length / PAGE_SIZE
        );

        if (nextPage < 1 || nextPage > totalPages) {
            return;
        }

        state.currentPage = nextPage;
        renderReceiptTable();
    }

    function renderPagination(totalItems, startIndex, visibleCount) {
        const totalPages = Math.max(
            1,
            Math.ceil(totalItems / PAGE_SIZE)
        );

        const endIndex = startIndex + visibleCount;

        if (elements.receiptHistoryPaginationInfo) {
            elements.receiptHistoryPaginationInfo.textContent =
                `Showing ${startIndex + 1}–${endIndex} of ${totalItems} receipts`;
        }

        if (elements.receiptHistoryPageIndicator) {
            elements.receiptHistoryPageIndicator.textContent =
                `Page ${state.currentPage} of ${totalPages}`;
        }

        if (elements.previousReceiptPageButton) {
            elements.previousReceiptPageButton.disabled =
                state.currentPage <= 1;
        }

        if (elements.nextReceiptPageButton) {
            elements.nextReceiptPageButton.disabled =
                state.currentPage >= totalPages;
        }

        if (elements.receiptHistoryPagination) {
            elements.receiptHistoryPagination.hidden = totalItems === 0;
        }
    }

    // --------------------------------------------------
    // LOADING, EMPTY AND ERROR STATES
    // --------------------------------------------------

    function setLoadingState(isLoading) {
        if (elements.receiptHistoryLoading) {
            elements.receiptHistoryLoading.hidden = !isLoading;
        }

        if (elements.refreshReceiptsButton) {
            elements.refreshReceiptsButton.disabled = isLoading;
        }

        if (isLoading) {
            hideTable();
            hidePagination();
            hideEmptyState();
        }
    }

    function showError(message) {
        hideTable();
        hidePagination();
        hideEmptyState();
        hideStatus();

        if (elements.receiptHistoryErrorMessage) {
            elements.receiptHistoryErrorMessage.textContent = message;
        }

        if (elements.receiptHistoryError) {
            elements.receiptHistoryError.hidden = false;
        }
    }

    function hideError() {
        if (elements.receiptHistoryError) {
            elements.receiptHistoryError.hidden = true;
        }
    }

    function showEmptyState(heading, message) {
        hideTable();
        hidePagination();

        if (elements.receiptHistoryEmptyHeading) {
            elements.receiptHistoryEmptyHeading.textContent = heading;
        }

        if (elements.receiptHistoryEmptyMessage) {
            elements.receiptHistoryEmptyMessage.textContent = message;
        }

        if (elements.receiptHistoryEmpty) {
            elements.receiptHistoryEmpty.hidden = false;
        }
    }

    function hideEmptyState() {
        if (elements.receiptHistoryEmpty) {
            elements.receiptHistoryEmpty.hidden = true;
        }
    }

    function showTable() {
        if (elements.receiptHistoryTableContainer) {
            elements.receiptHistoryTableContainer.hidden = false;
        }
    }

    function hideTable() {
        if (elements.receiptHistoryTableContainer) {
            elements.receiptHistoryTableContainer.hidden = true;
        }
    }

    function hidePagination() {
        if (elements.receiptHistoryPagination) {
            elements.receiptHistoryPagination.hidden = true;
        }
    }

    function showStatus(message) {
        if (elements.receiptHistoryStatus) {
            elements.receiptHistoryStatus.textContent = message;
            elements.receiptHistoryStatus.hidden = false;
        }
    }

    function hideStatus() {
        if (elements.receiptHistoryStatus) {
            elements.receiptHistoryStatus.textContent = "";
            elements.receiptHistoryStatus.hidden = true;
        }
    }

})();
"use strict";

/*
 * AI Expense Tracker
 * Smart Receipt Scanner
 * File: static/js/receipt-scanner.js
 *
 * Uses existing backend endpoints:
 *   POST /api/receipts/scan
 *   POST /add-expense
 *
 * Authentication:
 *   Authorization: Bearer <token>
 */

document.addEventListener("DOMContentLoaded", () => {
    const token = localStorage.getItem("token");

    // -------------------- DOM ELEMENTS --------------------

    const uploadForm = document.getElementById("receiptUploadForm");
    const fileInput = document.getElementById("receiptFile");
    const dropzone = document.getElementById("receiptDropzone");
    const fileError = document.getElementById("receiptFileError");

    const selectedFileSection =
        document.getElementById("selectedFileSection");
    const previewImage = document.getElementById("receiptPreview");
    const fileNameElement = document.getElementById("receiptFileName");
    const fileSizeElement = document.getElementById("receiptFileSize");

    const removeButton =
        document.getElementById("removeReceiptButton");
    const resetButton =
        document.getElementById("resetReceiptButton");

    const scanButton =
        document.getElementById("scanReceiptButton");
    const statusElement = document.getElementById("receiptStatus");

    const resultsSection = document.getElementById("receiptResults");
    const expenseForm = document.getElementById("receiptExpenseForm");
    const resultsStatus =
        document.getElementById("receiptResultsStatus");

    const merchantInput = document.getElementById("merchantName");
    const dateInput = document.getElementById("receiptDate");
    const amountInput = document.getElementById("receiptAmount");
    const categoryInput = document.getElementById("receiptCategory");

    const saveButton =
        document.getElementById("saveReceiptExpenseButton");

    const currentYear = document.getElementById("currentYear");

    // -------------------- CONFIGURATION --------------------

    const MAX_FILE_SIZE = 10 * 1024 * 1024;

    const ALLOWED_EXTENSIONS = [
        "jpg",
        "jpeg",
        "png",
        "webp",
        "bmp",
        "tif",
        "tiff",
        "pdf"
    ];

    const IMAGE_EXTENSIONS = [
        "jpg",
        "jpeg",
        "png",
        "webp",
        "bmp",
        "tif",
        "tiff"
    ];

    let selectedFile = null;
    let previewObjectUrl = null;
    let isScanning = false;
    let isSaving = false;
    let expenseAlreadySaved = false;

    let currentReceiptId = null;
    let currentExpenseId = null;
    let currentTransaction = null;
    let transactionChoiceBusy = false;
    let transactionPanel = null;

    // -------------------- INITIALIZATION --------------------

    if (currentYear) {
        currentYear.textContent = new Date().getFullYear();
    }

    if (!token) {
        alert("Please login first.");
        window.location.href = "/login-page";
        return;
    }

    if (
        !uploadForm ||
        !fileInput ||
        !dropzone ||
        !scanButton ||
        !expenseForm
    ) {
        console.error(
            "Receipt Scanner initialization failed: required HTML elements are missing."
        );
        return;
    }

    // -------------------- HELPERS --------------------

    function getExtension(filename) {
        const parts = filename.split(".");
        return parts.length > 1
            ? parts.pop().toLowerCase()
            : "";
    }

    function formatFileSize(bytes) {
        if (bytes < 1024) {
            return `${bytes} B`;
        }

        if (bytes < 1024 * 1024) {
            return `${(bytes / 1024).toFixed(1)} KB`;
        }

        return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    }

    function getTodayDate() {
        const now = new Date();
        const localDate = new Date(
            now.getTime() - now.getTimezoneOffset() * 60000
        );

        return localDate.toISOString().slice(0, 10);
    }

    function setStatus(element, message, state = "info") {
        if (!element) {
            return;
        }

        element.textContent = message;
        element.dataset.state = state;
        element.hidden = !message;
    }

    function clearStatus(element) {
        if (!element) {
            return;
        }

        element.textContent = "";
        element.hidden = true;
        delete element.dataset.state;
    }

    async function readResponse(response) {
        try {
            return await response.json();
        } catch {
            throw new Error(
                "The server returned an invalid response. Please try again."
            );
        }
    }

    async function apiRequest(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: {
                Authorization: `Bearer ${token}`,
                Accept: "application/json",
                ...(options.headers || {})
            }
        });

        if (response.status === 401) {
            localStorage.removeItem("token");

            alert("Your session has expired. Please login again.");
            window.location.href = "/login-page";

            throw new Error("Your session has expired.");
        }

        const data = await readResponse(response);

        if (!response.ok) {
            const message =
                data?.msg ||
                data?.detail ||
                data?.message ||
                "The request could not be completed.";

            const error = new Error(message);
            error.status = response.status;
            error.data = data;

            throw error;
        }

        return data;
    }

    function revokePreviewUrl() {
        if (previewObjectUrl) {
            URL.revokeObjectURL(previewObjectUrl);
            previewObjectUrl = null;
        }
    }

    function clearSelectedFile() {
        revokePreviewUrl();

        selectedFile = null;
        fileInput.value = "";

        if (previewImage) {
            previewImage.removeAttribute("src");
        }

        if (fileNameElement) {
            fileNameElement.textContent = "";
        }

        if (fileSizeElement) {
            fileSizeElement.textContent = "";
        }

        if (selectedFileSection) {
            selectedFileSection.hidden = true;
        }

        clearStatus(fileError);
    }

    function clearResults() {
        if (resultsSection) {
            resultsSection.hidden = true;
        }

        if (merchantInput) {
            merchantInput.value = "";
        }

        if (dateInput) {
            dateInput.value = "";
        }

        if (amountInput) {
            amountInput.value = "";
        }

        if (categoryInput) {
            categoryInput.value = "";
        }

        clearStatus(resultsStatus);

        expenseAlreadySaved = false;
        currentReceiptId = null;
        currentExpenseId = null;
        currentTransaction = null;
        if (transactionPanel) {
            transactionPanel.hidden = true;
            transactionPanel.replaceChildren();
        }

        if (saveButton) {
            saveButton.disabled = false;
            saveButton.textContent = "Save Expense";
        }
    }

    function resetScanner() {
        if (isScanning || isSaving) {
            return;
        }

        clearSelectedFile();
        clearStatus(statusElement);
        clearResults();

        if (scanButton) {
            scanButton.disabled = false;
            scanButton.innerHTML =
                '<span aria-hidden="true">✦</span> Scan Receipt';
        }
    }

    function validateFile(file) {
        if (!file) {
            return "Please select a receipt file first.";
        }

        if (!file.name || !getExtension(file.name)) {
            return "The selected file must have a valid file extension.";
        }

        const extension = getExtension(file.name);

        if (!ALLOWED_EXTENSIONS.includes(extension)) {
            return (
                "Unsupported file type. Please select JPG, PNG, WEBP, " +
                "BMP, TIFF or PDF."
            );
        }

        if (file.size <= 0) {
            return "The selected file is empty.";
        }

        if (file.size > MAX_FILE_SIZE) {
            return "File is too large. Maximum receipt size is 10 MB.";
        }

        // If the browser provides a MIME type, check it as an additional
        // client-side validation. The backend performs authoritative checks.
        if (
            file.type &&
            extension === "pdf" &&
            file.type !== "application/pdf"
        ) {
            return "The selected file does not appear to be a PDF.";
        }

        if (
            file.type &&
            IMAGE_EXTENSIONS.includes(extension) &&
            !file.type.startsWith("image/")
        ) {
            return "Please select a valid image file.";
        }

        return "";
    }

    function showSelectedFile(file) {
        clearStatus(fileError);

        selectedFile = file;

        if (fileNameElement) {
            fileNameElement.textContent = file.name;
        }

        if (fileSizeElement) {
            fileSizeElement.textContent = formatFileSize(file.size);
        }

        if (previewImage) {
            revokePreviewUrl();

            if (file.type.startsWith("image/")) {
                previewObjectUrl = URL.createObjectURL(file);
                previewImage.src = previewObjectUrl;
                previewImage.alt = `Preview of ${file.name}`;
                previewImage.hidden = false;
            } else {
                previewImage.removeAttribute("src");
                previewImage.alt = "PDF preview is not available.";
                previewImage.hidden = true;
            }
        }

        if (selectedFileSection) {
            selectedFileSection.hidden = false;
        }

        clearStatus(statusElement);
        clearResults();

        setStatus(
            statusElement,
            "Receipt selected. Review the file, then choose Scan Receipt.",
            "info"
        );
    }

    function setScanLoading(loading) {
        isScanning = loading;
        scanButton.disabled = loading;

        scanButton.textContent = loading
            ? "Scanning receipt..."
            : "Scan Receipt";

        if (loading) {
            setStatus(
                statusElement,
                "Uploading and processing your receipt. Please wait...",
                "info"
            );
        }
    }

    function getOrCreateTransactionPanel() {
        if (transactionPanel) {
            return transactionPanel;
        }

        transactionPanel = document.getElementById("upiTransactionPanel");

        if (!transactionPanel && resultsSection) {
            transactionPanel = document.createElement("section");
            transactionPanel.id = "upiTransactionPanel";
            transactionPanel.className = "receipt-transaction-panel";
            transactionPanel.setAttribute("aria-labelledby", "upiTransactionHeading");
            transactionPanel.hidden = true;

            // Keep the UPI panel inside the results area and outside the expense
            // form so its action buttons never submit the expense form by accident.
            if (expenseForm && expenseForm.parentNode === resultsSection) {
                resultsSection.insertBefore(transactionPanel, expenseForm);
            } else {
                resultsSection.appendChild(transactionPanel);
            }
        }

        return transactionPanel;
    }

    function appendDetail(container, label, value) {
        if (value === null || value === undefined || String(value).trim() === "") {
            return;
        }

        const row = document.createElement("p");
        row.className = "receipt-transaction-detail";
        const strong = document.createElement("strong");
        strong.textContent = `${label}: `;
        const text = document.createElement("span");
        text.textContent = String(value);
        row.append(strong, text);
        container.appendChild(row);
    }

    function normalizeTransaction(data, receipt) {
        return data?.transaction || receipt?.transaction || null;
    }

    function renderTransactionPanel(data, receipt) {
        const panel = getOrCreateTransactionPanel();
        if (!panel) return;

        const transaction = normalizeTransaction(data, receipt);
        currentTransaction = transaction;
        panel.replaceChildren();

        if (!transaction) {
            panel.hidden = true;
            return;
        }

        panel.hidden = false;
        const heading = document.createElement("h3");
        heading.id = "upiTransactionHeading";
        heading.textContent = "UPI transaction details";
        panel.appendChild(heading);

        const description = document.createElement("p");
        description.textContent = "Review the detected payment information before deciding whether to add it to expenses.";
        panel.appendChild(description);

        appendDetail(panel, "Payment app", transaction.platform || "Not identified");
        appendDetail(panel, "Transaction type", transaction.transaction_type || "Not identified");
        appendDetail(panel, "Amount", transaction.amount != null ? `₹${transaction.amount}` : (receipt?.total_amount != null ? `₹${receipt.total_amount}` : "Not detected"));
        appendDetail(panel, "Date", transaction.transaction_date || receipt?.receipt_date || "Not detected");
        appendDetail(panel, "Time", transaction.transaction_time);
        appendDetail(panel, "Sender / receiver", transaction.counterparty || receipt?.merchant || "Not identified");
        appendDetail(panel, "Reference", transaction.transaction_reference);
        appendDetail(panel, "Payment status", transaction.payment_status || "Unknown");

        if (transaction.possible_self_transfer) {
            const note = document.createElement("p");
            note.className = "receipt-transaction-warning";
            note.textContent = "This may be a transfer between your own accounts. Add it only if you want it recorded as an expense.";
            panel.appendChild(note);
        }

        const warnings = Array.isArray(data?.warnings)
            ? data.warnings
            : (Array.isArray(receipt?.warnings) ? receipt.warnings : []);

        if (warnings.length) {
            const warningList = document.createElement("ul");
            warningList.className = "receipt-transaction-warnings";
            warnings.forEach((warning) => {
                if (!warning) return;
                const item = document.createElement("li");
                item.textContent = String(warning);
                warningList.appendChild(item);
            });
            panel.appendChild(warningList);
        }

        const alreadySaved = data?.expense_created === true || Boolean(data?.expense_id || receipt?.expense_id);
        const canOfferChoice = !alreadySaved
            && !data?.duplicate_type
            && Boolean(selectedFile)
            && Number(transaction.amount ?? receipt?.total_amount) > 0;

        if (alreadySaved) {
            const saved = document.createElement("p");
            saved.className = "receipt-transaction-success";
            saved.textContent = "This transaction is already linked to an expense. No additional expense will be created.";
            panel.appendChild(saved);
            return;
        }

        if (!canOfferChoice) {
            const note = document.createElement("p");
            note.textContent = data?.duplicate
                ? "A matching transaction was found. Review the duplicate warning before trying to add it again."
                : "An expense cannot be created until a valid transaction amount is available.";
            panel.appendChild(note);
            return;
        }

        const actionRow = document.createElement("div");
        actionRow.className = "receipt-transaction-actions";

        const addButton = document.createElement("button");
        addButton.type = "button";
        addButton.className = "receipt-transaction-add-button";
        addButton.textContent = "Add this transaction as an expense";
        addButton.addEventListener("click", () => submitTransactionChoice(true, addButton, skipButton));

        const skipButton = document.createElement("button");
        skipButton.type = "button";
        skipButton.className = "receipt-transaction-skip-button";
        skipButton.textContent = "Keep as receipt only";
        skipButton.addEventListener("click", () => {
            panel.querySelectorAll("button").forEach((button) => {
                button.disabled = true;
            });
            setStatus(resultsStatus, "Saved as a receipt only. No expense was added by this choice.", "info");
        });

        actionRow.append(addButton, skipButton);
        panel.appendChild(actionRow);

        const helper = document.createElement("p");
        helper.className = "receipt-transaction-help";
        helper.textContent = "Your choice is sent to the existing scan endpoint. Confirm that the payment and amount are correct before adding it.";
        panel.appendChild(helper);
    }

    async function submitTransactionChoice(addAsExpense, addButton, skipButton) {
        if (transactionChoiceBusy || isScanning || isSaving) return;

        if (!selectedFile) {
            setStatus(resultsStatus, "Please select and scan the same transaction screenshot again.", "error");
            return;
        }

        const transaction = currentTransaction || {};
        const amount = Number(transaction.amount);
        if (addAsExpense && (!Number.isFinite(amount) || amount <= 0)) {
            setStatus(resultsStatus, "The transaction amount is missing or invalid. Please review the screenshot.", "error");
            return;
        }

        const status = String(transaction.payment_status || "unknown").toLowerCase();
        if (addAsExpense && (status === "failed" || status === "pending" || status === "unknown")) {
            const confirmed = window.confirm(
                `The payment status is ${status}. Have you verified this transaction in your payment app and do you still want to add it as an expense?`
            );
            if (!confirmed) return;
        }

        if (addAsExpense) {
            const confirmed = window.confirm(
                "Add this transaction to your expenses? This action will create an expense record if the backend confirms it can be saved."
            );
            if (!confirmed) return;
        }

        transactionChoiceBusy = true;
        if (addButton) {
            addButton.disabled = true;
            addButton.textContent = addAsExpense ? "Adding expense..." : "Please wait...";
        }
        if (skipButton) skipButton.disabled = true;

        try {
            const formData = new FormData();
            formData.append("file", selectedFile, selectedFile.name);
            formData.append("add_as_expense", addAsExpense ? "true" : "false");

            const data = await apiRequest("/api/receipts/scan", {
                method: "POST",
                body: formData
            });

            const receipt = data?.receipt;
            if (!receipt) {
                throw new Error("The server response did not include receipt details.");
            }

            updateSaveButton(data, receipt);
            renderTransactionPanel(data, receipt);

            if (data.expense_created === true || data.expense_id || receipt.expense_id) {
                expenseAlreadySaved = true;
                setStatus(resultsStatus, data.msg || "Transaction added to expenses successfully.", "success");
                setStatus(statusElement, "UPI transaction expense saved successfully.", "success");
            } else {
                setStatus(resultsStatus, data.msg || "The transaction remains saved as a receipt only.", "info");
            }

            if (Array.isArray(data.warnings) && data.warnings.length) {
                showWarnings(data.warnings);
            }
        } catch (error) {
            console.error("UPI expense choice failed:", error);
            setStatus(resultsStatus, error.message || "Unable to add this transaction as an expense.", "error");
            if (addButton) {
                addButton.disabled = false;
                addButton.textContent = "Add this transaction as an expense";
            }
            if (skipButton) skipButton.disabled = false;
        } finally {
            transactionChoiceBusy = false;
        }
    }

    function fillExpenseDetails(receipt) {
        if (!receipt) {
            return;
        }

        if (merchantInput) {
            merchantInput.value = receipt.merchant || "";
        }

        if (dateInput) {
            dateInput.value =
                receipt.receipt_date || getTodayDate();
        }

        if (amountInput) {
            amountInput.value =
                receipt.total_amount != null
                    ? String(receipt.total_amount)
                    : "";
        }

        if (categoryInput) {
            categoryInput.value = "Other";
        }

        if (resultsSection) {
            resultsSection.hidden = false;
        }
    }

    function updateSaveButton(data, receipt) {
        const savedByScan = data?.expense_created === true;
        const isDuplicate = data?.duplicate === true;

        currentReceiptId = receipt?._id || null;
        currentExpenseId = data?.expense_id || receipt?.expense_id || null;

        expenseAlreadySaved =
            savedByScan ||
            (isDuplicate && Boolean(currentExpenseId));

        if (!saveButton) {
            return;
        }

        if (expenseAlreadySaved) {
            saveButton.disabled = true;
            saveButton.textContent = "Expense Already Saved";

            setStatus(
                resultsStatus,
                isDuplicate
                    ? "This receipt was already scanned. Its existing expense will not be saved again."
                    : "The scanner has already created this expense. Review the extracted details; you do not need to save it again.",
                "success"
            );
        } else {
            saveButton.disabled = false;
            saveButton.textContent = "Save Expense";
        }
    }

    function showWarnings(warnings) {
        if (!Array.isArray(warnings) || warnings.length === 0) {
            return;
        }

        const message = warnings
            .filter(Boolean)
            .map(String)
            .join(" ");

        setStatus(
            resultsStatus,
            message,
            "warning"
        );
    }

    // -------------------- FILE SELECTION --------------------

    fileInput.addEventListener("change", () => {
        clearStatus(fileError);

        const file = fileInput.files?.[0];

        if (!file) {
            return;
        }

        const validationError = validateFile(file);

        if (validationError) {
            clearSelectedFile();
            setStatus(fileError, validationError, "error");
            return;
        }

        showSelectedFile(file);
    });

    // -------------------- DRAG AND DROP --------------------

    ["dragenter", "dragover"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            event.stopPropagation();

            if (!isScanning && !isSaving) {
                dropzone.classList.add("is-dragging");
            }
        });
    });

    ["dragleave", "dragend"].forEach((eventName) => {
        dropzone.addEventListener(eventName, (event) => {
            event.preventDefault();
            event.stopPropagation();
            dropzone.classList.remove("is-dragging");
        });
    });

    dropzone.addEventListener("drop", (event) => {
        event.preventDefault();
        event.stopPropagation();

        dropzone.classList.remove("is-dragging");

        if (isScanning || isSaving) {
            return;
        }

        const file = event.dataTransfer?.files?.[0];

        if (!file) {
            setStatus(fileError, "Please drop a receipt file.", "error");
            return;
        }

        const validationError = validateFile(file);

        if (validationError) {
            clearSelectedFile();
            setStatus(fileError, validationError, "error");
            return;
        }

        // Assign the dropped file to the existing input so form-related
        // browser state stays consistent.
        try {
            const transfer = new DataTransfer();
            transfer.items.add(file);
            fileInput.files = transfer.files;
        } catch (error) {
            console.warn(
                "The browser could not populate the file input from the drop event.",
                error
            );
        }

        showSelectedFile(file);
    });

    // -------------------- REMOVE AND CLEAR --------------------

    if (removeButton) {
        removeButton.addEventListener("click", () => {
            if (isScanning || isSaving) {
                return;
            }

            clearSelectedFile();
            clearStatus(statusElement);
            clearResults();
        });
    }

    if (resetButton) {
        resetButton.addEventListener("click", (event) => {
            event.preventDefault();
            resetScanner();
        });
    }

    uploadForm.addEventListener("reset", (event) => {
        event.preventDefault();
        resetScanner();
    });

    // -------------------- SCAN RECEIPT --------------------

    uploadForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (isScanning || isSaving) {
            return;
        }

        if (!selectedFile) {
            setStatus(
                fileError,
                "Please choose a receipt image or PDF before scanning.",
                "error"
            );

            fileInput.focus();
            return;
        }

        const validationError = validateFile(selectedFile);

        if (validationError) {
            setStatus(fileError, validationError, "error");
            return;
        }

        clearStatus(fileError);
        clearResults();
        setScanLoading(true);

        const formData = new FormData();

        // The backend accepts either "file" or "receipt".
        formData.append("file", selectedFile, selectedFile.name);

        try {
            const data = await apiRequest("/api/receipts/scan", {
                method: "POST",
                body: formData
            });

            const receipt = data?.receipt;

            if (!receipt) {
                throw new Error(
                    "The server response did not include receipt details."
                );
            }

            fillExpenseDetails(receipt);
            updateSaveButton(data, receipt);
            renderTransactionPanel(data, receipt);

            const isDuplicate = data.duplicate === true;

            if (isDuplicate) {
                setStatus(
                    statusElement,
                    data.msg ||
                        "This receipt has already been scanned.",
                    "success"
                );
            } else {
                setStatus(
                    statusElement,
                    data.msg ||
                        "Receipt processing completed. Review the extracted details.",
                    "success"
                );
            }

            // Show backend warnings without discarding extracted values.
            showWarnings(data.warnings || receipt.warnings);

            if (
                !data.warnings?.length &&
                !receipt.warnings?.length &&
                !expenseAlreadySaved
            ) {
                setStatus(
                    resultsStatus,
                    "Please review the details before saving the expense.",
                    "info"
                );
            }

            resultsSection?.scrollIntoView({
                behavior: "smooth",
                block: "start"
            });

        } catch (error) {
            console.error("Receipt scan failed:", error);

            const message =
                error.message ||
                "Unable to scan the receipt. Please try again.";

            setStatus(statusElement, message, "error");

        } finally {
            setScanLoading(false);
        }
    });

    // -------------------- SAVE EXPENSE --------------------

    expenseForm.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (isSaving || isScanning) {
            return;
        }

        if (expenseAlreadySaved) {
            setStatus(
                resultsStatus,
                "This receipt's expense has already been saved. No duplicate was created.",
                "success"
            );
            return;
        }

        const merchant = merchantInput?.value.trim() || "";
        const category = categoryInput?.value.trim() || "";
        const date = dateInput?.value || "";
        const rawAmount = amountInput?.value.trim() || "";
        const amount = Number(rawAmount);

        if (!rawAmount || !Number.isFinite(amount) || amount <= 0) {
            setStatus(
                resultsStatus,
                "Please enter a valid amount greater than zero.",
                "error"
            );

            amountInput?.focus();
            return;
        }

        if (!category) {
            setStatus(
                resultsStatus,
                "Please enter or select an expense category.",
                "error"
            );

            categoryInput?.focus();
            return;
        }

        if (!date) {
            setStatus(
                resultsStatus,
                "Please select the expense date.",
                "error"
            );

            dateInput?.focus();
            return;
        }

        isSaving = true;
        saveButton.disabled = true;
        saveButton.textContent = "Saving Expense...";

        setStatus(
            resultsStatus,
            "Saving the expense to your account...",
            "info"
        );

        try {
            const payload = {
                amount,
                category,
                currency: "INR",
                date
            };

            const data = await apiRequest("/add-expense", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload)
            });

            expenseAlreadySaved = true;
            currentExpenseId = data?.expense_id || null;

            saveButton.disabled = true;
            saveButton.textContent = "Expense Saved";

            setStatus(
                resultsStatus,
                data?.msg || "Expense added successfully.",
                "success"
            );

            setStatus(
                statusElement,
                "Your expense has been saved successfully.",
                "success"
            );

            console.info("Receipt-related expense saved.", {
                receiptId: currentReceiptId,
                expenseId: currentExpenseId,
                merchant
            });

        } catch (error) {
            console.error("Saving receipt expense failed:", error);

            if (error.status === 401) {
                return;
            }

            setStatus(
                resultsStatus,
                error.message ||
                    "Unable to save the expense. Please try again.",
                "error"
            );

            saveButton.disabled = false;
            saveButton.textContent = "Save Expense";

        } finally {
            isSaving = false;
        }
    });

    // -------------------- CLEANUP --------------------

    window.addEventListener("beforeunload", () => {
        revokePreviewUrl();
    });
});
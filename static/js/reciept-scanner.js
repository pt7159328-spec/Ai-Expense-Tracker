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
            "error"
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
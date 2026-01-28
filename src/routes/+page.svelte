<script lang="ts">
    import {
        FileText,
        Upload,
        Loader2,
        Download,
        CheckCircle,
        AlertCircle,
        Sparkles,
    } from "lucide-svelte";

    // API URL - set via environment variable or use relative path for local dev
    const API_URL = import.meta.env.VITE_API_URL || "";

    // State
    let activeTab: "text" | "file" = $state("text");
    let questionText = $state("");
    let uploadedFile: File | null = $state(null);
    let labNumber = $state("");
    let rollNumber = $state("");
    let studentName = $state("");
    let isGenerating = $state(false);
    let generationStatus = $state("");
    let generationProgress = $state(0);
    let isSuccess = $state(false);
    let errorMessage = $state("");
    let generatedBlob: Blob | null = $state(null);
    let previewCode = $state("");
    let previewConclusion = $state("");
    let isDragging = $state(false);

    // Batch mode state
    let batchCount = $state(0);
    let accumulatedBlobs: Blob[] = $state([]);
    let totalQuestionsProcessed = $state(0);

    // File handling
    function handleFileSelect(event: Event) {
        const input = event.target as HTMLInputElement;
        if (input.files && input.files[0]) {
            uploadedFile = input.files[0];
            errorMessage = "";
        }
    }

    function handleDrop(event: DragEvent) {
        event.preventDefault();
        isDragging = false;

        if (event.dataTransfer?.files && event.dataTransfer.files[0]) {
            const file = event.dataTransfer.files[0];
            const ext = file.name.split(".").pop()?.toLowerCase();

            if (ext === "pdf" || ext === "docx") {
                uploadedFile = file;
                errorMessage = "";
            } else {
                errorMessage = "Please upload a .pdf or .docx file";
            }
        }
    }

    function handleDragOver(event: DragEvent) {
        event.preventDefault();
        isDragging = true;
    }

    function handleDragLeave() {
        isDragging = false;
    }

    function removeFile() {
        uploadedFile = null;
    }

    // Generate report
    async function generateReport() {
        errorMessage = "";
        isSuccess = false;
        generatedBlob = null;
        previewCode = "";
        previewConclusion = "";

        // Validation
        if (activeTab === "text" && !questionText.trim()) {
            errorMessage = "Please enter a question";
            return;
        }
        if (activeTab === "file" && !uploadedFile) {
            errorMessage = "Please upload a file";
            return;
        }

        isGenerating = true;
        generationProgress = 0;

        try {
            // Prepare request data
            const requestData: {
                question_text?: string;
                file_data?: string;
                file_type?: string;
                lab_number?: string;
                roll_number?: string;
                student_name?: string;
            } = {};

            if (activeTab === "text") {
                generationStatus = "Analyzing question...";
                generationProgress = 10;
                requestData.question_text = questionText;
            } else if (uploadedFile) {
                generationStatus = "Processing uploaded file...";
                generationProgress = 5;

                // Read file as base64
                const fileBuffer = await uploadedFile.arrayBuffer();
                const base64 = btoa(
                    new Uint8Array(fileBuffer).reduce(
                        (data, byte) => data + String.fromCharCode(byte),
                        "",
                    ),
                );

                requestData.file_data = base64;
                requestData.file_type = uploadedFile.name.endsWith(".pdf")
                    ? "pdf"
                    : "docx";
                generationProgress = 15;
            }

            if (labNumber) requestData.lab_number = labNumber;
            if (rollNumber) requestData.roll_number = rollNumber;
            if (studentName) requestData.student_name = studentName;

            // Simulate progress stages
            generationStatus = "Generating MATLAB code...";
            generationProgress = 30;

            // Call API
            const response = await fetch(`${API_URL}/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(requestData),
            });

            generationStatus = "Plotting graph...";
            generationProgress = 60;

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || "Failed to generate report");
            }

            generationStatus = "Assembling document...";
            generationProgress = 85;

            // Get the blob
            generatedBlob = await response.blob();

            // Track batch
            batchCount++;
            accumulatedBlobs.push(generatedBlob);
            totalQuestionsProcessed += 4; // Max 4 per batch

            generationStatus = "Complete!";
            generationProgress = 100;
            isSuccess = true;
        } catch (err) {
            errorMessage =
                err instanceof Error
                    ? err.message
                    : "An unexpected error occurred";
        } finally {
            isGenerating = false;
        }
    }

    // Download generated document
    function downloadReport() {
        if (!generatedBlob) return;

        // Generate filename: LAB{number}_{rollNumber}.docx
        const labNum = labNumber.replace(/[^0-9]/g, "") || "X";
        const roll = rollNumber.replace(/[^a-zA-Z0-9]/g, "") || "ROLL";
        const filename = `LAB${labNum}_${roll}.docx`;

        const url = URL.createObjectURL(generatedBlob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        // Full reset after download
        fullReset();
    }

    // Add more questions - continue with another batch
    function addMoreQuestions() {
        // Keep accumulated blobs but reset input state
        questionText = "";
        uploadedFile = null;
        isSuccess = false;
        generatedBlob = null;
        errorMessage = "";
        previewCode = "";
        previewConclusion = "";
        // Keep: batchCount, accumulatedBlobs, totalQuestionsProcessed, labNumber, rollNumber, studentName
    }

    // Full reset for new lab
    function fullReset() {
        questionText = "";
        uploadedFile = null;
        isSuccess = false;
        generatedBlob = null;
        errorMessage = "";
        previewCode = "";
        previewConclusion = "";
        batchCount = 0;
        accumulatedBlobs = [];
        totalQuestionsProcessed = 0;
    }

    // Reset form (same as addMoreQuestions for backwards compat)
    function resetForm() {
        fullReset();
    }
</script>

<div
    class="min-h-screen bg-gradient-to-br from-zinc-50 via-white to-zinc-100 py-8 px-4 sm:py-16"
>
    <!-- Header -->
    <header class="text-center mb-8 sm:mb-12">
        <div class="inline-flex items-center gap-3 mb-4">
            <div
                class="w-12 h-12 rounded-xl bg-gradient-to-br from-zinc-800 to-zinc-900 flex items-center justify-center shadow-lg"
            >
                <Sparkles class="w-6 h-6 text-white" />
            </div>
            <h1
                class="text-3xl sm:text-4xl font-bold text-zinc-900 tracking-tight"
            >
                LabAuto
            </h1>
        </div>
        <p class="text-zinc-500 text-sm sm:text-base">
            Upload Question → Get Formatted Report
        </p>
    </header>

    <!-- Main Card -->
    <main class="max-w-2xl mx-auto">
        <div
            class="bg-white rounded-2xl shadow-xl shadow-zinc-200/50 border border-zinc-200/60 overflow-hidden"
        >
            <!-- Tabs -->
            <div class="flex border-b border-zinc-200">
                <button
                    onclick={() => (activeTab = "text")}
                    class="flex-1 py-4 px-6 text-sm font-medium transition-all flex items-center justify-center gap-2
						{activeTab === 'text'
                        ? 'text-zinc-900 bg-zinc-50 border-b-2 border-zinc-900'
                        : 'text-zinc-500 hover:text-zinc-700 hover:bg-zinc-50/50'}"
                >
                    <FileText class="w-4 h-4" />
                    Paste Text
                </button>
                <button
                    onclick={() => (activeTab = "file")}
                    class="flex-1 py-4 px-6 text-sm font-medium transition-all flex items-center justify-center gap-2
						{activeTab === 'file'
                        ? 'text-zinc-900 bg-zinc-50 border-b-2 border-zinc-900'
                        : 'text-zinc-500 hover:text-zinc-700 hover:bg-zinc-50/50'}"
                >
                    <Upload class="w-4 h-4" />
                    Upload File
                </button>
            </div>

            <!-- Content -->
            <div class="p-6 sm:p-8">
                <!-- Text Input -->
                {#if activeTab === "text"}
                    <div class="space-y-4">
                        <label class="block">
                            <div class="flex justify-between items-center mb-2">
                                <span class="text-sm font-medium text-zinc-700"
                                    >Lab Questions</span
                                >
                                <span
                                    class="text-xs text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full"
                                    >Max 4 questions per batch</span
                                >
                            </div>
                            <textarea
                                bind:value={questionText}
                                placeholder="Paste up to 4 questions here...

1) First question...
2) Second question...
3) Third question...
4) Fourth question...

💡 For more questions, click 'Add More Questions' after processing this batch."
                                class="w-full h-48 px-4 py-3 rounded-xl border border-zinc-200 bg-zinc-50/50
									focus:bg-white focus:border-zinc-400 focus:ring-2 focus:ring-zinc-200
									placeholder:text-zinc-400 text-zinc-900 text-sm resize-none transition-all"
                            ></textarea>
                        </label>
                    </div>
                {/if}

                <!-- File Upload -->
                {#if activeTab === "file"}
                    <div class="space-y-4">
                        {#if !uploadedFile}
                            <div
                                ondrop={handleDrop}
                                ondragover={handleDragOver}
                                ondragleave={handleDragLeave}
                                role="button"
                                tabindex="0"
                                class="border-2 border-dashed rounded-xl p-8 sm:p-12 text-center transition-all cursor-pointer
									{isDragging
                                    ? 'border-zinc-400 bg-zinc-100'
                                    : 'border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50/50'}"
                            >
                                <Upload
                                    class="w-10 h-10 text-zinc-400 mx-auto mb-4"
                                />
                                <p class="text-zinc-600 mb-2">
                                    Drag & drop your file here
                                </p>
                                <p class="text-zinc-400 text-sm mb-4">or</p>
                                <label
                                    class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-900 text-white text-sm font-medium hover:bg-zinc-800 transition-colors cursor-pointer"
                                >
                                    <span>Browse Files</span>
                                    <input
                                        type="file"
                                        accept=".pdf,.docx"
                                        onchange={handleFileSelect}
                                        class="hidden"
                                    />
                                </label>
                                <p class="text-zinc-400 text-xs mt-4">
                                    Supports PDF and DOCX files
                                </p>
                            </div>
                        {:else}
                            <div
                                class="flex items-center gap-4 p-4 rounded-xl bg-zinc-50 border border-zinc-200"
                            >
                                <div
                                    class="w-12 h-12 rounded-lg bg-zinc-200 flex items-center justify-center"
                                >
                                    <FileText class="w-6 h-6 text-zinc-600" />
                                </div>
                                <div class="flex-1 min-w-0">
                                    <p
                                        class="text-zinc-900 font-medium truncate"
                                    >
                                        {uploadedFile.name}
                                    </p>
                                    <p class="text-zinc-500 text-sm">
                                        {(uploadedFile.size / 1024).toFixed(1)} KB
                                    </p>
                                </div>
                                <button
                                    onclick={removeFile}
                                    class="px-3 py-1.5 text-sm text-zinc-600 hover:text-zinc-900 hover:bg-zinc-200 rounded-lg transition-colors"
                                >
                                    Remove
                                </button>
                            </div>
                        {/if}
                    </div>
                {/if}

                <!-- Required Info -->
                <div class="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <label class="block">
                        <span
                            class="text-sm font-medium text-zinc-700 mb-1 block"
                            >Lab Number <span class="text-red-500">*</span
                            ></span
                        >
                        <input
                            type="text"
                            bind:value={labNumber}
                            placeholder="e.g., 3"
                            class="w-full px-3 py-2 rounded-lg border border-zinc-200 bg-zinc-50/50
								focus:bg-white focus:border-zinc-400 focus:ring-2 focus:ring-zinc-200
								placeholder:text-zinc-400 text-zinc-900 text-sm transition-all"
                        />
                    </label>
                    <label class="block">
                        <span
                            class="text-sm font-medium text-zinc-700 mb-1 block"
                            >Roll Number <span class="text-red-500">*</span
                            ></span
                        >
                        <input
                            type="text"
                            bind:value={rollNumber}
                            placeholder="e.g., 2023IMG035"
                            class="w-full px-3 py-2 rounded-lg border border-zinc-200 bg-zinc-50/50
								focus:bg-white focus:border-zinc-400 focus:ring-2 focus:ring-zinc-200
								placeholder:text-zinc-400 text-zinc-900 text-sm transition-all"
                        />
                    </label>
                </div>

                <!-- Optional: Student Name -->
                <details class="mt-4 group">
                    <summary
                        class="text-sm text-zinc-500 cursor-pointer hover:text-zinc-700 transition-colors"
                    >
                        <span class="group-open:hidden"
                            >+ Optional settings</span
                        >
                        <span class="hidden group-open:inline"
                            >− Optional settings</span
                        >
                    </summary>
                    <div class="mt-4">
                        <label class="block">
                            <span
                                class="text-sm font-medium text-zinc-600 mb-1 block"
                                >Student Name (for header)</span
                            >
                            <input
                                type="text"
                                bind:value={studentName}
                                placeholder="Your full name"
                                class="w-full px-3 py-2 rounded-lg border border-zinc-200 bg-zinc-50/50
									focus:bg-white focus:border-zinc-400 focus:ring-2 focus:ring-zinc-200
									placeholder:text-zinc-400 text-zinc-900 text-sm transition-all"
                            />
                        </label>
                    </div>
                </details>

                <!-- Error Message -->
                {#if errorMessage}
                    <div
                        class="mt-6 flex items-start gap-3 p-4 rounded-xl bg-red-50 border border-red-100"
                    >
                        <AlertCircle
                            class="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5"
                        />
                        <p class="text-red-700 text-sm">{errorMessage}</p>
                    </div>
                {/if}

                <!-- Generate Button -->
                <button
                    onclick={generateReport}
                    disabled={isGenerating}
                    class="w-full mt-6 py-4 px-6 rounded-xl font-semibold text-white transition-all
						{isGenerating
                        ? 'bg-zinc-400 cursor-not-allowed'
                        : 'bg-gradient-to-r from-zinc-800 to-zinc-900 hover:from-zinc-700 hover:to-zinc-800 shadow-lg shadow-zinc-300 hover:shadow-xl hover:shadow-zinc-300'}"
                >
                    {#if isGenerating}
                        <span class="flex items-center justify-center gap-3">
                            <Loader2 class="w-5 h-5 animate-spin" />
                            {generationStatus}
                        </span>
                    {:else}
                        Generate Report
                    {/if}
                </button>

                <!-- Progress Bar -->
                {#if isGenerating}
                    <div class="mt-4">
                        <div
                            class="h-2 bg-zinc-100 rounded-full overflow-hidden"
                        >
                            <div
                                class="h-full bg-gradient-to-r from-zinc-600 to-zinc-800 rounded-full transition-all duration-500"
                                style="width: {generationProgress}%"
                            ></div>
                        </div>
                    </div>
                {/if}
            </div>

            <!-- Success State -->
            {#if isSuccess && generatedBlob}
                <div
                    class="border-t border-zinc-200 p-6 sm:p-8 bg-gradient-to-br from-emerald-50 to-teal-50"
                >
                    <div class="text-center">
                        <div
                            class="w-16 h-16 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-4"
                        >
                            <CheckCircle class="w-8 h-8 text-emerald-600" />
                        </div>
                        <h3 class="text-lg font-semibold text-zinc-900 mb-2">
                            Batch {batchCount} Complete!
                        </h3>
                        <p class="text-zinc-600 text-sm mb-2">
                            Processed up to 4 questions in this batch
                        </p>
                        <p class="text-zinc-500 text-xs mb-6">
                            Total batches: {batchCount} • Total questions: ~{totalQuestionsProcessed}
                        </p>

                        <div class="flex flex-col gap-3">
                            <!-- Primary: Add More Questions -->
                            <button
                                onclick={addMoreQuestions}
                                class="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-zinc-800 text-white font-medium hover:bg-zinc-700 transition-colors shadow-lg"
                            >
                                + Add More Questions (Next Batch)
                            </button>

                            <!-- Secondary: Download -->
                            <button
                                onclick={downloadReport}
                                class="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-emerald-600 text-white font-medium hover:bg-emerald-700 transition-colors shadow-lg shadow-emerald-200"
                            >
                                <Download class="w-5 h-5" />
                                Download Final Report
                            </button>

                            <!-- Tertiary: Start Over -->
                            <button
                                onclick={resetForm}
                                class="text-sm text-zinc-500 hover:text-zinc-700 transition-colors mt-2"
                            >
                                Start New Lab (Reset All)
                            </button>
                        </div>
                    </div>
                </div>
            {/if}
        </div>

        <!-- Footer -->
        <footer class="text-center mt-8 text-zinc-400 text-sm">
            <p>Powered by Gemini AI • MATLAB-style graphs with Matplotlib</p>
        </footer>
    </main>
</div>

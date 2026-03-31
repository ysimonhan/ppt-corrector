const BASE_URL = "https://YOUR-RAILWAY-APP.up.railway.app";

const jobId = data.input.jobId;
if (!jobId || jobId.trim() === "") {
  throw new Error("No job ID provided.");
}

const response = await ld.request({
  method: "GET",
  url: `${BASE_URL}/jobs/${jobId.trim()}`,
  headers: {
    Authorization: `Bearer ${data.auth.apiKey}`,
  },
});

if (response.status === 404) {
  throw new Error("Job not found.");
}

if (response.status !== 200) {
  const errorBody = response.json || response.text || "No body returned";
  throw new Error(
    `Unexpected polling status ${response.status}: ${JSON.stringify(errorBody)}`
  );
}

const result = response.json;

if (result.status === "done") {
  return {
    job_id: jobId.trim(),
    status: "done",
    files: [
      {
        fileName: result.file_name,
        base64: result.file_base64,
        mimeType:
          "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      },
    ],
    text: `Correction complete. ${result.corrections_count || 0} changes applied.`,
  };
}

if (result.status === "error") {
  return {
    job_id: jobId.trim(),
    status: "error",
    error: result.message || "Unknown processing error.",
  };
}

return {
  job_id: jobId.trim(),
  status: result.status,
  message: "Still processing. Retry this action with the same job ID in a moment.",
};

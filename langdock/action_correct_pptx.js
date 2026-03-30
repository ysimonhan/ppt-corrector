const BASE_URL = "https://YOUR-RAILWAY-APP.up.railway.app";
const POLL_INTERVAL_MS = 3000;
const MAX_ATTEMPTS = 35; // 35 x 3s = 105s, leaving budget for request overhead.

function getFileInput() {
  const file = data.input.document;
  if (!file || !file.base64 || !file.fileName) {
    throw new Error("Missing required input: document");
  }
  return file;
}

async function submitJob(file, highlight) {
  ld.log("Submitting PowerPoint for correction...");
  const response = await ld.request({
    method: "POST",
    url: `${BASE_URL}/jobs?highlight=${highlight ? "true" : "false"}`,
    headers: {
      Authorization: `Bearer ${data.auth.apiKey}`,
      "Content-Type": "application/json",
    },
    body: {
      file_base64: file.base64,
      file_name: file.fileName,
    },
  });

  if (response.status !== 202) {
    throw new Error(`Job creation failed with status ${response.status}`);
  }

  return response.json.job_id;
}

async function pollJob(jobId) {
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1) {
    ld.log(`Processing... attempt ${attempt}/${MAX_ATTEMPTS}`);

    const response = await ld.request({
      method: "GET",
      url: `${BASE_URL}/jobs/${jobId}`,
      headers: {
        Authorization: `Bearer ${data.auth.apiKey}`,
      },
    });

    if (response.status === 200) {
      const payload = response.json;
      if (payload.status === "done") {
        return payload;
      }
      if (payload.status === "error") {
        throw new Error(payload.message || "The backend returned an error.");
      }
    } else if (response.status === 404) {
      throw new Error("Job not found.");
    } else {
      throw new Error(`Unexpected polling status: ${response.status}`);
    }

    await ld.wait(POLL_INTERVAL_MS);
  }

  throw new Error(
    "The correction job is still processing. Langdock custom actions have a documented 2-minute timeout, so please retry in a moment."
  );
}

async function fetchResultFile(jobId) {
  ld.log("Fetching corrected file...");

  const response = await ld.request({
    method: "GET",
    url: `${BASE_URL}/jobs/${jobId}/file`,
    headers: {
      Authorization: `Bearer ${data.auth.apiKey}`,
    },
  });

  if (response.status !== 200) {
    throw new Error(`Result download failed with status ${response.status}`);
  }

  return response.json;
}

const file = getFileInput();
const highlight = Boolean(data.input.highlight);

const jobId = await submitJob(file, highlight);
ld.log(`Job created: ${jobId}`);

const result = await pollJob(jobId);
const outputFile = await fetchResultFile(jobId);

return {
  files: [
    {
      fileName: outputFile.file_name,
      base64: outputFile.file_base64,
      mimeType:
        outputFile.mime_type ||
        file.mimeType ||
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    },
  ],
  text: `Correction complete. ${result.corrections_count || 0} changes applied.`,
};

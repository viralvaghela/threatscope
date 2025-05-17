// background.js

chrome.runtime.onInstalled.addListener(() => {
  console.log("Security Design Review Extension installed.");
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "analyzeContent") {
    console.log("Received content for analysis:", request.content);

    // Here you can forward the content to an API (e.g., LLM) or process it internally.
    // For now, just return a mock analysis result:
    const mockAnalysis = {
      risks: ["Potential XSS", "Sensitive data exposure"],
      assets: ["Email addresses", "Auth tokens"]
    };

    sendResponse({ success: true, analysis: mockAnalysis });
  }

  // Return true to indicate async response
  return true;
});

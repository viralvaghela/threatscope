
# server.py
from flask import Flask, request, jsonify
import re
import os
# import base64 # Not used
import base64

from google import genai
from google.genai import types as google_genai_types # Use a more specific alias to avoid confusion
from flask import Flask, request, jsonify

from PIL import Image
from io import BytesIO                                                   # and to access enums like HarmCategory, FinishReason

# --- Configuration ---
GEMINI_API_KEY =genai.configure(api_key="YOUR_GEMINI_API_KEY")
MODEL_NAME = "gemini-2.0-flash" # Or your preferred model

# --- Initialize Flask App ---
app = Flask(__name__)

# --- Modified Gemini Generation Function ---
def generate_text_from_gemini(input_text: str):
    """
    Calls the Gemini API to generate text based on the input.
    Args:
        input_text: The prompt/text to send to the Gemini model.
    Returns:
        The generated text as a string.
    Raises:
        ValueError: If GEMINI_API_KEY is not set.
        Exception: For other errors during API call or if content is blocked/empty.
    """
    if not GEMINI_API_KEY:
        app.logger.error("GEMINI_API_KEY not found in environment variables.")
        raise ValueError("GEMINI_API_KEY is not configured.")

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        contents = [
            google_genai_types.Content( # Use the alias for clarity
                role="user",
                parts=[
                    google_genai_types.Part.from_text(text=input_text),
                ],
            ),
        ]
        generate_content_config = google_genai_types.GenerateContentConfig( # Use the alias
            response_mime_type="text/plain",
        )

        app.logger.info(f"Sending request to Gemini model '{MODEL_NAME}' with prompt: '{input_text[:100]}...'")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=generate_content_config,
        )
        app.logger.debug(f"Raw Gemini response object: {response}")

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            reason_message = response.prompt_feedback.block_reason_message or response.prompt_feedback.block_reason.name
            app.logger.error(f"Content generation blocked due to prompt. Reason: {reason_message}")
            if response.prompt_feedback.safety_ratings:
                for rating in response.prompt_feedback.safety_ratings:
                    app.logger.error(
                        f"Prompt Safety Rating: Category: {rating.category.name}, "
                        f"Probability: {rating.probability.name}"
                    )
            raise Exception(f"Prompt blocked by safety filter: {reason_message}")

        if hasattr(response, 'text') and response.text:
            app.logger.info(f"Successfully generated text (via response.text). Length: {len(response.text)}")
            return response.text
        
        if not response.candidates:
            app.logger.error(f"Gemini API returned no text and no candidates. Full response: {response}")
            raise Exception("Gemini API returned no candidates. Please check logs for the full response.")

        candidate = response.candidates[0]
        
        finish_reason_value = candidate.finish_reason # This is already an enum member, e.g., FinishReason.STOP
        finish_reason_name = candidate.finish_reason.name

        # Expected finish reasons for success
        successful_finish_reasons = [
            google_genai_types.Candidate.FinishReason.STOP,
            google_genai_types.Candidate.FinishReason.MAX_TOKENS
        ]

        if finish_reason_value not in successful_finish_reasons:
            app.logger.error(f"Candidate generation stopped for a non-standard reason. Finish Reason: {finish_reason_name}")
            if candidate.safety_ratings:
                for rating in candidate.safety_ratings:
                    # HarmProbability enum: NEGLIGIBLE, LOW, MEDIUM, HIGH
                    # Using .value for comparison might be fragile if enum values change, direct enum comparison is better
                    if rating.probability >= google_genai_types.HarmProbability.MEDIUM:
                        app.logger.error(
                            f"Candidate Safety Issue: Category: {rating.category.name}, "
                            f"Probability: {rating.probability.name}"
                        )
            if finish_reason_value == google_genai_types.Candidate.FinishReason.SAFETY:
                 raise Exception(f"Content generation stopped due to safety concerns in the response ({finish_reason_name}).")
            elif finish_reason_value == google_genai_types.Candidate.FinishReason.RECITATION:
                 raise Exception(f"Content generation stopped due to recitation policy ({finish_reason_name}).")
            else: # OTHER or UNSPECIFIED
                 raise Exception(f"Content generation failed for the candidate. Finish reason: {finish_reason_name}.")

        text_parts = []
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if hasattr(part, 'text') and part.text: # Ensure part has text attribute
                    text_parts.append(part.text)
        
        if text_parts:
            generated_text = "".join(text_parts)
            app.logger.info(f"Successfully generated text (via candidate parts). Length: {len(generated_text)}")
            cleaned_text = re.sub(r"```(?:[\w+-]*)?\n?([\s\S]*?)```", r"\1", generated_text).strip()

            return cleaned_text

        app.logger.error(
            f"Gemini API: No text extracted despite seemingly valid response structure. "
            f"Response.text was empty. Candidate Finish Reason: {finish_reason_name}. "
            f"Full Response: {response}"
        )
        raise Exception("Gemini API returned an empty response or response without parsable text content, despite no explicit blocking.")

    except ValueError as ve:
        app.logger.error(f"Configuration or input error: {ve}")
        raise
    # Removed the specific exception catches for BlockedPromptException and StopCandidateException
    # as they are not typically raised by the synchronous generate_content() and were causing AttributeError.
    # The logic above already checks for blocking conditions in the response and raises a generic Exception.
    except Exception as e:
        # This will catch exceptions raised by the client library (e.g., API errors from google.api_core.exceptions)
        # or the generic Exceptions we raise above after inspecting the response.
        app.logger.error(f"Error during Gemini API call or processing: {type(e).__name__} - {e}", exc_info=True)
        # Re-raise a standard Exception to be handled by the Flask error handler
        # It's good practice to not expose raw internal exception messages to the client in production.
        # The message here is already crafted by our internal logic or is a generic one.
        raise Exception(f"Gemini API interaction failed: {str(e)}")


# --- Flask API Endpoint (GET request) ---
@app.route('/generate', methods=['GET'])
def api_generate():
    input_prompt = request.args.get('prompt')
    SYSTEM_PROMPT=  """
You are an elite security architect and threat modeling expert. Your task is to conduct a **high-fidelity security design review** of a given UI screen. Treat this as a professional client-facing assessment, equivalent to work produced by leading global cybersecurity consulting firms or internal red teams at Fortune 500 companies.

The screen might include login forms, signup pages, profile forms, or transactional UIs containing sensitive data. Use your expertise to identify **high-level design flaws**, **assets that need protection**, and return an actionable **review report** in **clean HTML + CSS** format that can be embedded in a browser plugin UI.

Do not return starting sentances such as "sure, here you go", "Here's the report" etc, just return the report without saying anything.

---

🛠️ OBJECTIVES:

1. Identify overall **security risks** and **misconfigurations** based on the given UI, form structure, and context.
2. Detect **assets that need protection** (e.g., email, password, tokens, PII).
3. Provide **threat modeling**, **security scoring**, **remediation**, and a **manual test checklist**.

---

🎯 STRUCTURE YOUR OUTPUT EXACTLY LIKE THIS (in HTML + CSS only):

### 📋 SECTION 0 : Executive Summary
- High-level overview of key observations (2–3 bullet points max)
- Identify overall security posture (Good / Needs Improvement / Critical)
- Quick threat impact summary
- Business risk alignment (e.g., user data exposure, account takeover risk)
- Suggested next action (e.g., security re-architecture, review dev practices)



### 📝 SECTION 1: Summarized Screen Overview
- Extract and display the form structure:
  - Form action URL
  - HTTP method
  - Input types and fields
  - Any hidden/sensitive fields
- Format as a clean table or list

### 🔐 SECTION 2: Security Design Analysis
- Evaluate:
  - HTTPS usage
  - Proper HTTP method (GET vs POST)
  - Security attributes (`autocomplete=off`, `pattern`, etc.)
  - Hidden field usage (token leakage, guessable values)
  - CSRF token presence and implementation
  - Client-side validation logic (missing or ineffective)
  - Potential for information leakage (PII in URL, etc.)

### 🧠 SECTION 3: Threat Modeling (STRIDE-based)
Use STRIDE to assess each applicable threat:
- **S**poofing
- **T**ampering
- **R**epudiation
- **I**nformation Disclosure
- **D**enial of Service
- **E**levation of Privilege

For each category:
- Describe applicable threats
- Mention attacker goals and realistic scenarios
- Rate likelihood + impact (Low/Med/High)

### 🛡️ SECTION 4: Actionable Security Recommendations
- Provide fixes and improvements in bullet points
- Include secure headers, better form practices, UX-safe improvements
- Keep it brief but insightful

### ✅ SECTION 5: Positive Security Observations
- Highlight existing good practices (HTTPS, secure form design, token usage, etc.)
- Show appreciation for secure defaults and design awareness

### 📊 SECTION 6: Security Score (0–10)
- Based on:
  - Protocol usage
  - Exposure of PII/tokens
  - Vulnerability surface
  - Presence of mitigations
  - Overall threat likelihood
- Add a colored badge + short justification

### 🧪 SECTION 7: Manual Security Checklist for Reviewers
Create a checklist of "Yes/No" items for security engineers to validate manually:
- [ ] Does the form use HTTPS?
- [ ] Are sensitive fields masked or obfuscated?
- [ ] Do hidden fields include secure tokens?
- [ ] Are inputs validated and sanitized client-side?
- [ ] Is CSRF protection implemented and tested?
- [ ] Are secure HTTP headers configured?
- [ ] Can input lead to XSS or data injection?
- [ ] Is data stored in cookies/localStorage secure?

---

🔧 TECHNICAL REQUIREMENTS:
- Output only HTML + CSS. **No markdown. No JSON. No explanation like "Here's your report."**
- UI must look clean, modern, and mobile-friendly
- Use spacing, emojis, colors, and layout for UX clarity
- Keep formatting consistent and avoid long, dense blocks
- Use icons or emojis in section headers where appropriate
- You are not limited to perform only following which i mentioned, feel free to use your creativity and based on input perfrom all possible testcase / analysis
---

🔎 INPUT FOR ANALYSIS:

```{input_prompt}```
"""
    if not input_prompt:
        return jsonify({"error": "Missing 'prompt' query parameter"}), 400

    try:
        app.logger.info(f"API /generate called with prompt: {SYSTEM_PROMPT[:50]}...")
        generated_text = generate_text_from_gemini(SYSTEM_PROMPT)
        app.logger.info(f"API /generate successfully returned text: {generated_text[:50]}...")
        return jsonify({"generated_text": generated_text}), 200
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 500
    except Exception as e:
        app.logger.error(f"API /generate error: {e}", exc_info=True)
        # The str(e) will now correctly pick up the messages from the Exceptions raised in generate_text_from_gemini
        return jsonify({"error": str(e)}), 500


# --- Health Check Endpoint ---
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route('/upload_screenshot', methods=['POST'])
def upload_screenshot():
    data = request.get_json()
    image_data = data.get('screenshot')

    if not image_data.startswith('data:image'):
        return jsonify({'error': 'Invalid image data'}), 400

    # Decode base64 image
    header, encoded = image_data.split(',', 1)
    binary_data = base64.b64decode(encoded)
    image = Image.open(BytesIO(binary_data))

    # Save or process the image as needed
    image.save("captured_screenshot.png")

    # Call Gemini API for threat modeling (you’ll need to add your logic)
    # gemini_analysis = "🛡️ Threat modeling and security design review results will go here."

    # return jsonify({"analysis": gemini_analysis})
    
    client =genai.configure(api_key="YOUR_GEMINI_API_KEY")

    my_file = client.files.upload(file="./captured_screenshot.png")
    IMAGE_THREAT_MODELING_PROMPT_TEMPLATE = """You are an elite security architect and threat modeling expert. Your task is to perform an advanced security **design review** based **solely on the provided screenshot** of a screen (e.g., an HTML form, a mobile app UI, or a web page).
You are an elite security architect and threat modeling expert. Your task is to conduct a **high-fidelity security design review** of a given UI screen. Treat this as a professional client-facing assessment, equivalent to work produced by leading global cybersecurity consulting firms or internal red teams at Fortune 500 companies.

From the visual information in the screenshot, identify **potential high-level design flaws**, **visible assets that need protection**, and return an actionable **review report** in **clean HTML + CSS** format that can be embedded in a browser plugin UI. Focus on what can be inferred visually.
Do not return starting sentances such as "sure, here you go", "Here's the report" etc, just return the report without saying anything.

---

🛠️ OBJECTIVES (based on the screenshot):

1. Identify overall **security risks** and **misconfigurations** visually apparent or strongly implied.
2. Detect **visible assets that need protection** (e.g., input fields for email, password, PII).
3. Provide **threat modeling**, **security scoring**, **remediation suggestions**, and a **manual test checklist**, all inferred from the visual elements.

---

🎯 STRUCTURE YOUR OUTPUT EXACTLY LIKE THIS (in HTML + CSS only):

### 📋 SECTION 0: Executive Summary
- High-level overview of key observations (2–3 bullet points max)
- Identify overall security posture (Good / Needs Improvement / Critical)
- Quick threat impact summary
- Business risk alignment (e.g., user data exposure, account takeover risk)
- Suggested next action (e.g., security re-architecture, review dev practices)



### 📝 SECTION 1: Summarized Screen Overview (from Screenshot)
- Describe the visible UI elements (forms, buttons, input fields, data displayed).
- Identify the likely purpose of the screen (e.g., login, registration, data entry).
- Format as a clean table or list.

### 🔐 SECTION 2: Security Design Analysis (Visual Inference)
- Evaluate based on what's visible:
  - Obvious signs of HTTP vs HTTPS (e.g., browser chrome if present, but often not). Assume HTTPS unless visual cues suggest otherwise, but state this assumption.
  - Visible input field types (text, password, email).
  - Masking of sensitive data (e.g., password fields showing dots).
  - Information displayed that might be sensitive (PII, tokens).
  - Clarity of actions and potential for user confusion leading to security mistakes.

### 🧠 SECTION 3: Threat Modeling (STRIDE-based, Visual Inference)
Use STRIDE to assess applicable threats inferable from the screenshot:
- **S**poofing (e.g., UI elements that could be easily faked)
- **T**ampering (e.g., are there obvious ways data shown could be manipulated if not protected server-side?)
- **R**epudiation (e.g., lack of clear confirmation steps for critical actions)
- **I**nformation Disclosure (e.g., sensitive data unnecessarily displayed)
- **D**enial of Service (e.g., complex UI that might be slow, though hard to tell from static image)
- **E**levation of Privilege (e.g., admin-like functions visible without clear context of authorization)

For each category:
- Describe applicable threats suggested by the visual design.
- Mention attacker goals and plausible scenarios.
- Rate likelihood + impact (Low/Med/High) based on visual cues.

### 🛡️ SECTION 4: Actionable Security Recommendations (Visual Focus)
- Provide UI/UX design fixes and improvements related to security.
- Suggest checks for underlying security mechanisms (e.g., "Ensure server-side validation for all inputs shown").
- Keep it brief but insightful.

### ✅ SECTION 5: Positive Security Observations (Visual)
- Highlight good visual security practices (e.g., clear password masking, minimal data display).

### 📊 SECTION 6: Security Score (0–10, Visual Assessment)
- Based on:
  - Visual clarity and indicators of security.
  - Apparent handling of sensitive inputs/data.
  - Potential visual attack surface.
- Add a colored badge + short justification.

### 🧪 SECTION 7: Manual Security Checklist for Reviewers (Post-Visual)
Create a checklist for deeper investigation beyond the screenshot:
- [ ] Is the actual communication over HTTPS?
- [ ] Are all inputs validated and sanitized server-side?
- [ ] Is CSRF protection robustly implemented for any state-changing actions?
- [ ] Are appropriate security headers (CSP, HSTS, etc.) in place?
- [ ] How is session management handled?
- [ ] Are there rate limits on actions like login or submission?
- [ ] Is data encrypted at rest if sensitive information is stored?

---

🔧 TECHNICAL REQUIREMENTS:
- Output only HTML + CSS. **No markdown. No JSON. No explanation like "Here's your report."**
- UI must look clean, modern, and mobile-friendly.
- Use spacing, emojis, colors, and layout for UX clarity.
- Keep formatting consistent and avoid long, dense blocks.
- Use icons or emojis in section headers where appropriate.

---

Analyze the following screenshot for threat modeling:
(The image will be provided as the next part of the input)
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-04-17",
        contents=[my_file, IMAGE_THREAT_MODELING_PROMPT_TEMPLATE],
    )

    print(response.text)
    return jsonify({ "generated_text": response.text })


if __name__ == '__main__':
    if not GEMINI_API_KEY:
        print("CRITICAL: GEMINI_API_KEY environment variable not set.")
        print("Please set it before running the server, e.g.:")
        print("export GEMINI_API_KEY='your_actual_api_key_here'")
        # import sys
        # sys.exit(1)

    app.run(debug=True, host='0.0.0.0', port=5000)

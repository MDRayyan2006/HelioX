# Task Plan: Test HelioX React UI

- [x] Navigate to http://localhost:5173
- [x] Type "What is HelioX?" into the Query Input box
- [x] Click "Submit/Send"
- [x] Wait for processing (10-20s)
- [x] Verify AnswerCard (Answer text, Confidence, Citations) - *CONSISTENT CRASH*
- [ ] Click Evidence toggle (if available) - *N/A (Crashed)*
- [x] Record findings

**Final Findings:**
1. **Backend Status:** The backend (`http://localhost:8000/v1/query`) is functional. It returned a valid JSON response for the query "What is HelioX?".
   - **Answer:** "Insufficient evidence to fully answer this query."
   - **Confidence:** 0.72
   - **Citations:** [] (Empty)
   - **Latency:** ~30.4s
2. **Frontend Status:** The React UI consistently crashes when attempting to render the result in the `<AnswerCard>` component.
   - **Error:** `An error occurred in the <AnswerCard> component.`
   - **Cause:** Console logs indicate a missing `key` prop warning followed by a full component crash. This might be triggered when `citations` is an empty array or when specialized data (like `diagnostics`) is processed without adequate safety checks.
3. **User Experience:** The screen goes completely dark/blank once the query finishes processing, providing no feedback to the user other than the initial "Thinking" animation before the crash.

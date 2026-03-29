# HelioX React Frontend Implementation Tasks

## 1. Setup & Foundational Styling
- [x] Configure Tailwind CSS in `index.css` (remove default Vite styles).
- [x] Define color palette and typography in `tailwind.config.js` or `index.css` variables, aiming for a premium, dark-mode focused enterprise look.

## 2. Layout & Shell
- [x] Create `MainLayout` component:
  - Sidebar for chat history / sessions (optional for MVP, but good for structure).
  - Main content area for the current query/chat.
  - Header with branding, mode toggle (Light/Heavy), and settings/info.

## 3. Core Components
- [x] `QueryInput`: A prominent, centered input field for the user to type their question, with a submit button.
- [x] `ChatMessage`: A component to display either the user's query or the system's response.
- [x] `AnswerCard`: A structured component to display the final answer, including:
  - The text response with citations.
  - Confidence score indicator.
  - Toggle to show "Thinking Process" or "Evidence".
- [x] `EvidencePanel` / `CitationViewer`: To display the exact source chunks retrieved and cited.
- [x] `StatusIndicator`: To show the pipeline progress (Query Analysis -> Retrieval -> Synthesis -> Composition) when Heavy mode is active.
- [x] `DocumentUploader`: A component (modal or sidebar section) to allow drag-and-drop uploading of multiple documents.

## 4. State Management & API Integration
- [x] Define API mock service (`api.js`).
- [x] Create a custom hook `useQueryAction` or similar to handle:
  - Sending the query to the FastAPI backend (e.g., POST `/query`).
  - Handling loading states and streaming (if applicable, otherwise standard fetch).
  - Error handling (timeouts, 500s, degradation messages).
- [x] Implement `uploadDocuments` mock service in `api.js`.
- [x] Track uploaded documents state in `App.jsx` and pass context to `submitQuery`.

## 5. Page Assembly
- [x] Update `App.jsx` to use the `MainLayout` and orchestrate the `QueryInput` and `ChatMessage`/`AnswerCard` components.
- [x] Add an "Upload Documents" button to the `MainLayout` or main view to trigger the `DocumentUploader`.

## 6. Polish
- [x] Add smooth transitions for status updates (using lucide-react and tailwind animate-in).
- [x] Ensure responsive design for varying screen sizes.
- [x] Implement "Premium Aesthetic" requirements (glassmorphism, subtle gradients, rich typography).

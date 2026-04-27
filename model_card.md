# Model Card — PawPal+ RAG AI

## Model Overview

**Application:** PawPal+ — AI-Powered Pet Care Scheduler  
**AI layer:** Retrieval-Augmented Generation (RAG) using Google Gemini (`gemini-2.5-flash-lite`)  
**Retriever:** TF-IDF vectorization with cosine similarity (scikit-learn)  
**Knowledge base:** 24 hand-curated pet care chunks covering dogs and cats  
**Base project:** Module 2 PawPal+ scheduling project — CodePath Applied AI course

---

## Intended Use

PawPal+ is designed to help pet owners get personalized, grounded answers to everyday pet care questions. The AI combines retrieved knowledge base facts with the owner's live pet data (names, species, scheduled tasks) to produce responses that are specific to their situation. It is intended for informational and planning purposes only — not as a substitute for professional veterinary advice.

---

## AI Collaboration

AI tools (Claude Code) were used throughout this project at every stage: initial system design, implementation of the RAG pipeline, debugging widget state issues, writing and expanding the test suite, and drafting README content.

**One helpful suggestion:** Claude recommended using TF-IDF vectorization over a vector database for the retriever. The reasoning — no model downloads, no external services, fully offline, fast startup — was sound and directly shaped the final architecture.

**One flawed suggestion:** Claude replaced Streamlit's deprecated `use_container_width=True` parameter with `width="100%"`. That value is not valid in Streamlit; the correct replacement is `width="stretch"`. The error only surfaced at runtime, which was a practical reminder that AI-generated code should always be tested before being trusted.

---

## Limitations and Biases

- **Narrow knowledge base:** The 24 knowledge chunks cover common dog and cat care topics only. Exotic pets, specific breeds, senior animals, and regional veterinary differences are not represented.
- **Word-overlap retrieval:** TF-IDF matches on vocabulary, not meaning. A question phrased very differently from the knowledge base may retrieve a less relevant chunk and produce a less accurate answer.
- **No individual health awareness:** The AI does not know a pet's age, breed, or medical history. Advice on exercise, diet, and medication is generic and should be verified with a veterinarian.
- **Training data bias:** The underlying Gemini model reflects biases present in its training data, which may favor certain cultural norms or geographic contexts in pet care recommendations.
- **Dogs and cats only:** The species selectbox is limited to dogs and cats. Owners of other animals will not receive relevant knowledge base matches.

---

## Testing Results

### Automated tests
49 out of 49 tests pass across all components. The scheduler, conflict detection, recurrence logic, and edge cases are fully covered by 45 unit tests. Four dedicated RAG engine tests confirm that the retriever returns relevant knowledge chunks for real pet care queries, returns an empty result when no match exists, and assembles the AI prompt with all required sections. No test failures were observed; the only gap is UI-layer behavior, which is evaluated manually.

### Logging and error handling
Every AI query is logged to `pawpal_rag.log` with the question text, number of chunks retrieved, cosine similarity scores for each chunk, and the final token counts (input and output) from the Gemini API. During development, two rate limit errors were caught and surfaced as plain-language messages rather than stack traces, which led to switching models to find a quota tier that worked reliably. Authentication errors, rate limits, and connection failures each produce a distinct user-facing message.

### Human evaluation
Three sample interactions were reviewed and documented in the README. The AI correctly used the owner's name, the pet's name, and referenced existing scheduled tasks in its responses — confirming that the live pet context injection is working as intended.

---

## Potential Misuse and Mitigations

The most likely misuse is treating AI responses as a substitute for professional veterinary care. A pet owner facing a health emergency might ask the AI instead of calling a vet. Current mitigations:
- The system prompt instructs the AI to recommend consulting a veterinarian for health and medication questions
- The knowledge base is grounded in factual care guidelines rather than open-ended medical diagnosis
- The "Knowledge sources retrieved" expander in the UI shows which chunks influenced each answer, making the AI's reasoning transparent

A future improvement would add a persistent disclaimer in the UI on any response that mentions health, medication, or emergency symptoms.

---

## What This Project Says About Me as an AI Engineer

This project shows that I approach AI as an engineering discipline, not just a feature to bolt on. I built a Retrieval-Augmented Generation system from scratch, made deliberate architectural decisions about where AI adds value versus where deterministic logic is more reliable, and backed every component with automated tests. When things broke — rate limits, deprecated APIs, widget state bugs — I diagnosed and fixed them rather than working around them. I care about building software that is understandable and auditable, which is why logging, error handling, and a clean separation between the AI layer and the scheduling logic were priorities from the start. This is the kind of engineer I want to be: someone who can ship working AI systems and explain exactly how and why they work.

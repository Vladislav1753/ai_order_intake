# Alternative A brief (copied from client-ai-project-research.html)

Alternative A Interpret & validate
AI Order Intake & Exception Handling Platform
Turn incoming customer requests into usable draft orders and a clear queue of exceptions.
OverviewDatasetRequirementsCode GenerationOptionalEvaluationSubmissionPhilosophy
One working dayUp to 8 hours; document unfinished workOne assignmentComplete this assignment onlyLocal demoUse a language or framework you know

    Start with the supplied examples. The starter pack includes fictional rules, sample data, templates, and a data-generation skill. Allow 30–60 minutes within the eight-hour limit to inspect and extend it. You do not need industry knowledge.

Customer requestsCatalog lookup + validationDraft orders + review

Model's roleUse a model to interpret order requests and look up catalog entries, then validate the draft order in code.

Overview
Build a small operations platform for a fictional distributor whose customers place orders by email and attachments. Convert incoming requests into draft orders that staff can review. If a request is unclear, flag the missing or ambiguous details and draft a clarification. The aim is to reduce manual order entry while keeping unresolved details visible and easy to correct.
Example behaviorA customer writes “Send two boxes of the usual cable,” but the catalog lists several cables and gives no box sizes. The platform flags the product and quantity as unresolved and drafts a clarification.

Dataset
Starter material
Use tasks/orders/ from the starter pack. Its domain.md defines the rules for this exercise.
All prices are fictional USD amounts stored in integer cents. Quantities are positive whole numbers of individual items. Do not infer how many items a box contains.
Use the catalog unit price. For a line with at least 10 items, apply a 10% discount to that line only; round the discount to the nearest cent, with halves rounded up. There are no other charges.
Match products by SKU or an unambiguous catalog description. Unknown products and ambiguous quantities need clarification.
Requests with the same order reference describe the same order. Reprocessing an identical request must not create a second draft.
Worked example. Two CAB-1 cables at 2,000 cents each total 4,000 cents. Ten CAB-1 cables total 18,000 cents after the 2,000-cent bulk discount.
Included files: domain.md, seed.json, expected-seed-results.json, request.template.json.

Start with the supplied catalog, four requests, and two pricing rules in tasks/orders/. Extend the requests to around 10, using AI, a script, or handwritten examples. Keep preparation within 30–60 minutes of the eight-hour assignment.
Use short email-style text files and optional attachments. Vary wording while preserving the catalog, individual-item units, currency, and discount rule. Do not invent pack sizes or additional pricing policies.
Keep the normal order, unknown product, ambiguous quantity, and duplicate order reference from the seed. Add a reviewer-correction scenario and check the resulting price independently.
Commit the supplied data and your additions, with the generation method. Check five reference cases and save expected behavior separately from application outputs. Document any ambiguity in the supplied rules.
Simulation and reference cases
Keep the provided seed cases and their expected results. Extend them with AI, a script, or handwritten examples while following the supplied rules. If a rule is unclear, state the ambiguity instead of inventing an industry policy. Commit the final fictional inputs, generation method, and random seed if used.
Include five reference cases covering the listed checks. They may combine supplied cases and your additions. Verify expected results by calculation or source inspection before evaluating the application. The supplied expected values apply to the original seeds; recalculate them if added data changes a total. Do not use the application's answers as the answer key. Label simulations and report failed checks.

Requirements
Data Processing
Load the request files and local reference data. Preserve each original request, give it a stable identity, and report unusable input without stopping other requests.
Use a model to extract a draft order and call a local lookup that only searches the catalog. Record the source and catalog entries that support each proposed product; uncertain matches must remain unresolved.
Validate quantities and calculate expected prices in code using the catalog and stated rules. Save draft orders, validation findings, and clarification drafts so they remain available after a restart.
Analytics & Insights
Show how many requests are ready for review, need clarification, or failed processing. Summarize the main exception reasons and duplicate requests without counting them as new orders.
Identify one practical improvement to the intake process, supported by examples from your results. Distinguish a structurally valid draft from an order reviewed by a person.
Dashboard/Visualization
Create a simple interactive operations queue with a status filter. Let a reviewer inspect the original request beside the proposed order, supporting catalog matches, and failed checks.
Allow a reviewer to correct a proposed field and rerun validation. Save the correction and resulting status; keep enough history to explain what changed.
Technical Implementation
Connect local file loading, a real model call, catalog lookup, validation, saved results, and the review screen. A small local app with file storage or SQLite is sufficient.
Validate model output and lookup arguments. Handle invalid output, an unavailable model, and an ambiguous product or quantity with visible statuses instead of invented values.
Ensure reprocessing the duplicate does not create another order. All resulting orders and messages remain local drafts; live email, ERP integration, authentication, and cloud deployment are unnecessary.
Minimum demonstration
Include a results table or test report for these checks. Explain any failures you could not fix.
A normal request becomes the expected draft order, and its quantities and calculated prices match your independently checked reference.
An unknown product is left unresolved with a useful clarification draft rather than silently mapped to an unrelated catalog item.
An ambiguous quantity is flagged for review rather than guessed.
Processing the duplicate request again does not create a second order or inflate the new-order count.
A reviewer correction changes the saved proposal, reruns the relevant checks, and remains visible after restarting the app.

Core scope: around 10 requests, one catalog lookup, two simple pricing rules, and one operations queue. Complete one path and its exceptions within eight hours, including simulation. Inventory allocation, payment, delivery scheduling, and live integrations are outside the core.

Code Generation Approach
You may use LLM tools to generate the entire solution, including data, processing code, storage, model integration, the interface, tests, and documentation. We value candidates who use AI to build working components and check the results.

    Document one example of giving an AI tool a task, checking its output, and correcting or improving it. Be prepared to explain the code you submit. The proportion of code you typed yourself does not affect the assessment.

    Include a working programmatic model integration and saved responses from real calls using your simulated inputs. Use model access agreed with the hiring team; no particular provider or latest model is required. Label cached responses and simulated failures so the reviewer can distinguish them from new model calls. Keep credentials out of the repository.
Save your AI setup
Commit the exercise-specific configuration used during development and by the application: skills, agent instructions and subagent definitions, hooks and their scripts, prompts, rules, model settings, tool or MCP settings, and permissions. Keep files in their normal repository locations or save sanitized snapshots under ai-workflow/. Include earlier versions through Git history or named snapshots.
Complete the starter pack's ai-workflow/manifest.template.json and README.template.md, renaming them to manifest.json and README.md. Record each component's purpose, file path, tool/model version, when it was used, and how to restore or replay the setup. Record not-used, default, or not-exportable with a reason where appropriate. A default setup is acceptable; custom agents, skills, and hooks are optional.
Include only the relevant parts of user-level configuration. Replace secrets with placeholders and list environment variable names in .env.example. Exclude tokens, credentials, private URLs, and unrelated personal information. Explain redactions and omissions without revealing their values.

Optional Enhancements
Support one additional request format, such as an image attachment.
Export reviewed draft orders in a simple structured format.
Show a clearer comparison between the model proposal and the reviewer's correction.

Evaluation Criteria

Functional thinkingApply the supplied rules and decide what to do when information is missing. Industry knowledge is not required.

Technical executionBuild the flow from input to result, with readable code, saved data, validation, and checks that catch errors.

LLM useUse AI to generate working components and check their results. Save the configuration you used, explain why you chose it, and show one correction or improvement. We assess whether the setup supports the task and can be reproduced; the number of skills, agents, or hooks does not earn credit.

CreativityMake your own product and implementation choices within the time limit. Extra infrastructure or hours do not earn automatic credit.

CommunicationExplain your decisions and limitations, and provide instructions another engineer can follow to run the project.

Assessment will focus on how you validate draft orders, flag ambiguity, prevent duplicates, and handle reviewer corrections.

Submission
Git repository with the solution, dependencies, and small sample and replay files containing no sensitive data.
Dataset and starter material with the supplied seeds and rules, your additions, generation method, assumptions, and five checked reference cases with expected results.
README with setup and run instructions, architecture, model configuration, data assumptions, time spent, and known limitations. Include a way to replay saved real responses without an API key.
Brief presentation of your approach and findings. A 3–5-minute recording, a few slides, or a written walkthrough is sufficient.
LLM usage note listing tools and models, generated components, one representative instruction or workflow, and one correction or verification step. You do not need to submit complete chat logs.
AI configuration with the completed ai-workflow/manifest.json and ai-workflow/README.md, all exercise-specific skills, agents, hooks and referenced scripts, prompts, model/tool settings, relevant versions, and sanitized environment examples. Mark unused components and explain any redacted or non-exportable settings.
Check results for the minimum demonstration, showing expected and observed behavior and unresolved failures.

Philosophy
Use AI to build the solution and take responsibility for what it does. We assess how you approach the problem, investigate mistakes, and adapt your work after checking the results.
Finish the required flow before attempting optional enhancements. Explain any limitations you could not address within the working day.

Junior AI Engineer take-home · Alternative A · One working day

# Method notes

Hand-written, versioned, digit-free notes the harness shows a clinician who asks how the system
works. Retrieval is by keyword over the analyst's own words (component 8); no model writes or
selects them. One note per `## ` heading; the first line after the heading lists its keywords.

## what-is-borrowing
keywords: borrow, borrowing, transfer, external, published, registry, strength, integrate, integration
Your cohort is small, and a larger study has published a model of the same kind of outcome. Borrowing means fitting your own model while pulling its coefficients toward the published ones, by an amount chosen from your data. If the published model describes your patients well, the pull helps; if it does not, the amount chosen is small or zero, and your own data decide. Nothing from the published model is used unless the comparison shows it lowers the held-out loss.

## how-much-to-borrow
keywords: eta, weight, how much, amount, tuning, tune, strength of borrowing, penalty weight
The amount of borrowing is a weight. At zero the published model is ignored and you have a plain fit on your own data; as the weight grows the fit moves toward the published coefficients. The weight is not chosen by anyone: every candidate value on a grid is tried, each is scored by cross-validation on your data, and the value with the lowest held-out loss is kept. The report states the weight that was selected for every method it fitted.

## which-methods
keywords: method, methods, estimator, candidate, candidates, which model, admissible, family, kullback, mahalanobis, euclidean, ridge, lasso, elastic
Two facts about your data decide which methods can apply: the study design (a full cohort or a matched case-control design) and the form in which the external information arrived (a published coefficient vector, a coefficient vector with its covariance, or another cohort's records). Every method those two facts admit is fitted: borrowing through the risk-set distribution (the Kullback-Leibler form), borrowing through the coefficients (the Euclidean form, and beside it the Mahalanobis form when a covariance was published), each without a penalty, with a ridge penalty and with a lasso path, together with your own model alone and the published model unchanged. No one picks among them: cross-validation does.

## cross-validation
keywords: cross-validation, cross validation, cv, fold, folds, held-out, held out, loss, partition, split, criterion, select, selection, chosen, chose, why was
Every candidate is scored the same way: the cohort is split into folds once, each candidate is fitted on all folds but one and scored on the one left out, and the scores are summed into one held-out loss. The split is drawn once from a recorded seed and shared by every candidate, so the comparison is fair and can be replayed. The candidate with the lowest loss is selected. The loss is the partial-likelihood loss, a measure of fit to held-out patients; it is not a prediction accuracy and is not reported as one.

## not-borrowing
keywords: not borrow, no borrowing, own data, my own data, internal, alone, unchanged, decline, negative transfer, harm, worse
Two candidates are always in the comparison and can win: your own model with no borrowing, and the published model used unchanged. If the published model does not fit your patients, borrowing from it can make the fit worse; that is visible only when both endpoints are scored on the same data, which is why they are always included and why declining to borrow is an answer the system can return.

## what-the-report-contains
keywords: report, contains, sections, table, coefficients, coefficient table, artifacts, files, trace, script, repro, reproduce, reproducible, audit
The report has six parts: what your data are and how each role was settled; how the published model lines up with your variables; which methods were admissible and why; the comparison of every method on the same held-out loss; the selected model's coefficients beside the published ones and your own; and what the analysis does not establish. Four files come with it: the estimates, the report, a trace of every decision and every model call, and an R script that reruns the analysis from the estimator library alone, with no language model involved.

## the-language-model
keywords: language model, llm, model call, ai, chatbot, prompt, hallucinate, hallucination, trust, digits, numbers
The language model reads your words and writes the report's connective prose. It never chooses a method, never sets a tuning parameter, never names a column you did not name, and never writes a number: every quantity in the report is inserted by the harness from the fitted objects. Each of its calls is recorded with the instructions it ran under, so the trace shows exactly what it was asked and what it answered.

## what-is-not-done
keywords: competing risks, competing, time-varying, time varying, changes over time, interval, truncation, causal, cause, predict, prediction, risk score, individual patient, plot, figure, graph, clean, cleaning, missing values, impute
The system fits one time-to-event outcome per subject with covariates measured at the start of follow-up. It does not model competing risks or covariates that change over time; it does not clean, transform or impute your data or the published model; it does not draw figures; it does not produce a risk score for an individual patient; and nothing it reports is a causal effect. A request for any of these is refused with the reason, not answered approximately.

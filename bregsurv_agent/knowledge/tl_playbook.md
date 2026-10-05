# Transfer-learning playbook

These notes are shown to the planner (the `analysis_plan` and `next_step`
acts), never to the analyst. They are ADVICE for the planner to weigh, not rules: the harness enforces the
few rules there are, and these notes only say what tends to help. Each note is retrieved by a SITUATION the
harness computes from the diagnostics card and the declaration, not by a model: the `when:` line names the
trigger (see `analyst.situations`). One note per `## ` heading. No note cites a result of one of the paper's
own applications, so the planner carries no answer to a cohort it may later be evaluated on.

## always
when: always
The fitted members are compared by one cross-validated loss on one partition, and the lowest wins; a member that is not fitted cannot win. Two members are in every plan: the target-only fit and the released model unchanged. It usually pays to spend the budget on the members that could plausibly win here, and on grids that reach where the answer may be.

## few-events
when: few_events
There are fewer events than about two per covariate. The unpenalised target-only fit tends to be unstable here and usually loses; it stays in the plan as the protected endpoint, but the target-only ridge or lasso fit is often the more useful "no borrowing" competitor. Unpenalised borrowing members are less exposed to this, since the release regularises them. Penalised members are often worth their cost in this situation.

## many-events
when: many_events
There are many events per covariate. The target-only fit is usually well determined, borrowing tends to add less, and the penalised target-only members often differ little from the unpenalised one. A smaller plan that keeps the borrowing families at their default grids may be enough, though a family left out cannot win.

## weak-release
when: weak_release
The released model seems to fit this cohort poorly: its calibration slope is well below one, or its cross-validated loss is above the target-only ridge fit's. Borrowing may then hurt, so penalised members and grids that reach small weights are worth considering, letting cross-validation find how little to borrow. The calibration slope is the release's risk score refitted here as a single covariate: it measures the scale of the release's effects along its own direction. A slope below one can also come from a direction that is partly wrong, or from covariates of this cohort that the release lacks (they pull the slope down even when the release is right), so it is best read together with the per-term differences. A term is left out of the borrowing only when the analyst says the variable differs from the release; a disagreement seen in this cohort does not allow it.

## strong-release
when: strong_release
The released model seems to fit this cohort about as well as anything fitted here: calibration slope near one and a cross-validated loss at or below the target-only ridge fit's. The released model unchanged may well win, and borrowing members tend to select large weights; if a member's selected weight sits at the top of its grid, extending the grid upward is often the refinement worth paying for. The calibration slope is the release's risk score refitted here as a single covariate: it measures the scale of the release's effects along its own direction. A slope below one can also come from a direction that is partly wrong, or from covariates of this cohort that the release lacks (they pull the slope down even when the release is right), so it is best read together with the per-term differences.

## concentrated-heterogeneity
when: concentrated_heterogeneity
The disagreement between the target-only fit and the release appears concentrated in a few terms while the rest agree. With few events such a pattern is often noise. Grids that reach small weights and the penalised forms of the borrowing families let cross-validation settle how much to borrow overall. If the analyst has said those variables are defined, measured or coded differently from the release, a mask on them can be set, quoting those words.

## absent-terms
when: absent_terms
Some covariates of the cohort are not in the release. By default a coefficient-space member leaves them free (they are not pulled anywhere). Padding them with zero instead tells the fit that the release estimated those effects as zero. That is closer to the truth when the release's authors considered those variables and left them out, and further from it when they never had them; it tends to help when the release is strong and the uncovered effects are small, and to hurt when the target-only fit finds them large. The task lists, for each uncovered covariate, the target-only estimate and anything the analyst wrote about it; weigh these. Padding applies to identity-metric members only, and fitting the same member both ways lets cross-validation compare them.

## two-metrics
when: covariance_released
A covariance was released, so coefficient-space borrowing can use the identity metric (Euclidean) or the released precision (Mahalanobis). The two can differ noticeably on the same data, and which is better is hard to know in advance; when the budget allows, fitting both metrics in the family you expect to do well lets cross-validation choose.

## tied-times
when: tied_times
Many events share a time. The standard row takes subjects who share a time in the order the data list them; the tie-corrected row uses Breslow's approximation, in which everyone with that time stays in the risk set. It is a different likelihood, so its members are never ranked against the standard row's: choosing it is choosing the row. It holds the same members as the standard row, each fitted and scored on Breslow's likelihood, so choosing it costs nothing in the set. It is usually worth choosing when ties are frequent enough to matter.

## few-ties
when: few_ties
Few events share a time. The two likelihoods then nearly coincide, and the tie correction tends to change little; the standard row is usually enough.

## coarse-grid
when: coarse_time
The follow-up time takes few distinct values on a regular step, as grouped follow-up does. The analyst has not declared discrete intervals, so the analysis stays continuous; the standard row treats the grouping as ties, and the tied-times note applies.

## records
when: records
The external information is another cohort's records. Borrowing then uses the composite likelihood over both cohorts; there is no ridge form, and the external-only member is a model fitted on the other cohort and scored here. The standardised mean differences in the diagnostics indicate how different the two populations are.

## matched
when: matched
The design is matched sets. The released model unchanged cannot be scored on the conditional likelihood, so the plan's endpoint is the target-only fit alone, and there is no ridge form.

## grid-edge
when: grid_edge
A borrowing member's selected weight sits at the end of its grid. At the top, a larger weight might do as well or better, so extending the grid upward is often worth it (the released model unchanged is the limit of a very large weight). At the lowest positive value or at zero, the data seem to reject borrowing in that family: a finer grid near zero tends to add little, and the units may be better spent elsewhere.

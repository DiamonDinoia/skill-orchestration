# Numeric heuristics delegation

Lessons for error-bound and tolerance work on numerical libraries. Load with the cpp skill before dispatching a child that fits constants, gates or warnings.

## Measure the arms, then ask the rate question

An error model that refuses, warns or fails silently trades two error rates: false refuses and misses. Fitting it is not measurement alone; it is a trade the user prices. Before dispatching a fit job, measure both rates on the current model and state them in the report. Ask the user only the question a measurement cannot answer: which miss is acceptable to buy fewer false warns.

A path with fewer stages has a lower real floor: spread/interp only has no FFT and no deconvolution, so its rounding error is well below the full NUFFT pipeline's. Using one constant for both over-refuses the spread-only path and can miss adversarial input on the full path. Give each path its own constant, in the one place that computes eps_round. Select by the path flag.

## Constant fits need bounds, not one case

- Fit a constant c in `eps_round = c * eps_mach * nf` to the worst case on random and on adversarial data (equal in-phase strengths, clustered points). The adversarial and the random case can push the required c past each other, so no single constant serves both. Then the model is wrong, not the constant: split the path, add a term, or leave the model as is and fix the test that hits the false warn. Do not lower c until the adversarial miss is ruled out or priced.
- A hypothesis about the mechanism (truncation, a cost model constant, an arch difference) must be stated with the failure killed on the bench, not from a probe that cannot reproduce CI's failing cell. A probe that uses one random dataset instead of the test's per-cell sweep and whose 1.18 case passes is directional evidence, not confirmation; re-run through the real test binary before the fix is shaped.
- A plausible cause at the knob level is not the mechanism. On a sigma-selecting bug, a trim knob that directly causes the failing cells (kernel Horner `nc` cut by `coeffs_tol_cutoff`) is a nearer fit than a model refit that would only shift which sigma gets picked. Gather the trim-versus-full comparison before changing the model that selects sigma.

A "false warn" that holds on adversarial data is not false. Check the tolerance the test actually exercises, and the one the user expects, before changing the library.

## A per-cell win can be scatter, not mechanism

Before a cause gets credit for one cell's improvement, compare the two runs' chosen parameters on that cell. Two pickers that land on different values for the same input (a sigma, a width, a transform size) do not compare like with like, and a small outcome gap between them is noise until rerun. Rerun each side over several seeds; agreement within about 15% across seeds marks the gap as scatter. Only a cell where both sides pick the same parameters and the error still differs carries mechanism evidence.

A comparison gate's acceptance bar goes into the brief before any run: one threshold per metric the verdict names (fail count, refusal count, worst accepted ratio), plus the pre-existing rows a pass may still carry, plus one pre-authorized fallback candidate with its trigger. The report prints bar against observed per metric. A bar fixed after the numbers exist cannot fail, so it is not a check.

## Nested stages share one tolerance budget

A two-stage computation whose stages are each checked against the full tolerance lets the two errors add. A selection loop that sizes both stages at their own edge then lands the total up to about twice the tolerance. When the errors can add, split the budget. Each stage gets tol/2, so the errors add to at most tol. Use root sum of squares (each stage gets tol/sqrt(2)) only for an explicit RMS or statistical error contract with `E[e1*e2]=0 (independent or uncorrelated errors)`. State the derivation in a comment. If E[e1*e2] can be nonzero, use the worst-case tol/2 split. When forced probes of the extreme choices in the search space all measure above tol, the cell is a capability floor: the honest answer is a refusal, not a fudge margin or a named exception.

## Applying review changes does not outrank regressions

Apply a reviewer comment as written, one commit per comment, tied to the comment id. A review request still gets checked against the master behaviour: merge the change, then compare the chosen constants and reached accuracy against the branch before the change over both precisions, types and a tolerance sweep. A request that makes results looser than master is a regression: report it with the measurement, because a change asked for a known reason can still be the one the user asked you to catch.

Deleting tests a reviewer calls unmaintainable can remove the only runtime check of the fix the review is on. Before applying a test-removal comment, list which behaviours lose their failing arm; if the fix itself loses all of them, say so in the report. A small 'bad input' test that checks error codes is the shape a reviewer accepts.

## Warnings must not be too strict

The user prefers a missed warning over a false one, when the library still computes a usable result. A refusal is stronger than a warning: it closes a test that only needs a real number. Fit warn-only paths loose, and keep refusals for results that are provably wrong. The default warning margin is about 1.5x over the measured floor, not 2x.

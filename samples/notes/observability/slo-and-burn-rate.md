# SLOs and burn rate alerts

A service level indicator (SLI) is a ratio of good events to total events, for example requests answered in less than 10 seconds without error. A service level objective (SLO) is a target for that ratio over a window: 99% over 30 days.

The error budget is what the SLO allows to fail: 1% of requests over 30 days. The burn rate is how fast you are spending it. A burn rate of 1 uses exactly the budget over the window; a burn rate of 14.4 empties a 30-day budget in about two days.

Alerting on the raw error ratio is noisy. Alerting on burn rate ties the alert to user impact. The common pattern is a **multi-window, multi-burn-rate alert**: page when the burn rate is high over both a long window and a short one.

- Page: burn rate above 14.4 over 1 hour **and** over 5 minutes.
- Page: burn rate above 6 over 6 hours **and** over 30 minutes.
- Ticket: burn rate above 1 over 3 days **and** over 6 hours.

The long window proves the problem is significant. The short window proves it is still happening, so the alert resets quickly once the incident is over.

In Prometheus this is done with recording rules that precompute the error ratio over each window (`rag:error_ratio:rate5m`, `rag:error_ratio:rate1h`...) and alerting rules that compare them to `burn_rate * (1 - objective)`.

An SLO nobody reviews is decoration. Look at the budget every week, and when it is gone, spend time on reliability rather than features.

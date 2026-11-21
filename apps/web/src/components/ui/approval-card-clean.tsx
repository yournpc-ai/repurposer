"use client"

import { useId } from "react"
import { useTranslation } from "react-i18next"
import { Button } from "./button-clean"

/** Controlled projection of one server authorization. Amounts include their currency or credit unit. */
export function ApprovalCard({ title, quote, limit, approveLabel, declineLabel, status, submitting, onDecision }: {
  title: string
  quote?: string
  limit?: string
  approveLabel?: string
  declineLabel?: string
  status: "pending" | "approved" | "denied"
  submitting: boolean
  onDecision: (approve: boolean) => void
}) {
  const { t } = useTranslation()
  const titleId = useId()
  return (
    <section className="ui-apc" data-actions="card" aria-labelledby={titleId} aria-busy={submitting}>
      <style href="ui-approval-card-clean" precedence="default">{css}</style>
      <div className="ui-apc__pending">
        <div className="ui-apc__card">
          <h3 className="ui-apc__title" id={titleId}>{title}</h3>
          <p className="ui-apc__desc" role="status">{t(`agentReceipt.${status}`)}</p>
          {(quote || limit) && <div className="ui-apc__preview">
            <dl className="ui-apc__details">
              {quote && <div className="ui-apc__detail"><dt>{t("agentReceipt.quote")}</dt><dd>{quote}</dd></div>}
              {limit && <div className="ui-apc__detail"><dt>{t("agentReceipt.limit")}</dt><dd>{limit}</dd></div>}
            </dl>
          </div>}
          {status === "pending" && <div className="ui-apc__foot">
            <div className="ui-apc__actions">
              <Button disabled={submitting} variant="secondary" onClick={() => onDecision(false)}>{declineLabel ?? t("agentReceipt.decline")}</Button>
              <Button disabled={submitting} onClick={() => onDecision(true)}>{approveLabel ?? t("agentReceipt.approve")}</Button>
            </div>
          </div>}
        </div>
      </div>
    </section>
  )
}

const css = /* css */ `
.ui-apc {
  flex: 1;
  min-width: 0;
  --ui-apc-tray: var(--aui-subtle, #f0f0f0);
  --ui-apc-bg: var(--aui-surface, #ffffff);
  --ui-apc-ink: var(--aui-ink, #171717);
  --ui-apc-text: var(--aui-muted, #6b6b6b);
  --ui-apc-muted: var(--aui-muted, #8a8a8a);
  --ui-apc-line: var(--aui-border, #ececec);
  --ui-apc-soft: #fafafa;
  --ui-apc-tile: #f4f4f4;
  --ui-apc-hover: #e4e4e5;
  --ui-apc-primary: var(--aui-primary, #171717);
  --ui-apc-primary-hover: #2e2e2e;
  --ui-apc-primary-ink: var(--aui-on-primary, #ffffff);
  --ui-apc-primary-kbd: rgba(255, 255, 255, 0.14);
  --ui-apc-primary-kbd-ink: rgba(255, 255, 255, 0.72);
  --ui-apc-kbd: rgba(0, 0, 0, 0.055);
  --ui-apc-box: var(--aui-border-strong, #d4d4d4);
  --ui-apc-box-hover: #b5b5b5;
  --ui-apc-focus: var(--aui-focus, rgba(0, 96, 226, 0.7));
  --ui-apc-timer-low: var(--aui-warning, #b25e00);
  --ui-apc-low-bg: #f2f2f2;
  --ui-apc-low-ink: #6b6b6b;
  --ui-apc-med-bg: #fbf5e2;
  --ui-apc-med-ink: #8f6c00;
  --ui-apc-high-bg: #fdedeb;
  --ui-apc-high-ink: var(--aui-danger, #c4320a);
  --ui-apc-ok-bg: #e9f6ee;
  --ui-apc-ok-ink: var(--aui-success, #1e8a4f);
  --ui-apc-no-bg: #f2f2f2;
  --ui-apc-no-ink: #6b6b6b;
  --ui-apc-ease: var(--aui-ease, cubic-bezier(0.22, 1, 0.36, 1));
  position: relative;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  overflow: hidden;
  container-type: inline-size;
  padding: 4px;
  border-radius: calc(var(--aui-radius-lg, 10px) + 10px);
  background: var(--ui-apc-tray);
  color: var(--ui-apc-text);
  font-family: var(--aui-font, "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif);
  font-size: 13px;
  line-height: 1.45;
  letter-spacing: -0.006em;
  text-align: left;
  -webkit-font-smoothing: antialiased;
  transition: height 520ms var(--ui-apc-ease);
}
.ui-apc *,
.ui-apc *::before,
.ui-apc *::after {
  box-sizing: border-box;
}
.ui-apc__card {
  position: relative;
  border-radius: calc(var(--aui-radius-lg, 10px) + 6px);
  background: var(--ui-apc-bg);
  box-shadow: var(--aui-shadow-card, 0 0 0 1px var(--ui-apc-line), 0 1px 2px rgba(0, 0, 0, 0.04));
}
.ui-apc__pending > .ui-apc__card {
  padding: 16px;
}
.ui-apc[data-busy] .ui-apc__pending {
  pointer-events: none;
}
.ui-apc__title {
  margin: 0;
  overflow: hidden;
  color: var(--ui-apc-ink);
  font-size: 14px;
  font-weight: 550;
  line-height: 20px;
  letter-spacing: -0.011em;
  text-align: start;
  white-space: normal;
  overflow-wrap: anywhere;
}
.ui-apc__desc {
  margin: 1px 0 0;
  overflow: hidden;
  font-size: 13px;
  line-height: 18px;
  text-align: start;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.ui-apc__preview {
  display: grid;
  gap: 12px;
  max-height: 360px;
  overflow-y: auto;
  overscroll-behavior: contain;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--ui-apc-line);
}
.ui-apc__details {
  display: grid;
  grid-template-columns: fit-content(min(40%, 180px)) minmax(0, 1fr);
  gap: 6px 16px;
  margin: 0;
}
.ui-apc__detail {
  display: contents;
}
.ui-apc__detail dt {
  min-width: 0;
  overflow: hidden;
  color: var(--ui-apc-muted);
  overflow-wrap: normal;
  text-overflow: ellipsis;
}
.ui-apc__detail dd {
  min-width: 0;
  margin: 0;
  overflow-x: auto;
  color: var(--ui-apc-ink);
  text-align: start;
  overflow-wrap: anywhere;
}
.ui-apc[data-actions="card"] { padding: 0; border-radius: calc(var(--aui-radius-lg, 10px) + 6px); background: transparent; }
.ui-apc[data-actions="card"] .ui-apc__card { box-shadow: inset 0 0 0 1px var(--ui-apc-line); }
.ui-apc__card > .ui-apc__foot { min-height: 0; margin-top: 16px; padding: 14px 0 0; border-top: 1px solid var(--ui-apc-line); }
.ui-apc__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  min-height: 44px;
  padding: 6px 2px 2px 10px;
}
.ui-apc__actions {
  display: flex;
  flex: 0 1 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
  min-width: 0;
  margin-left: auto;
}
@container (max-width: 400px) {
  .ui-apc__actions {
    flex: 1 1 100%;
    margin-left: 0;
  }
  .ui-apc__foot {
    padding-left: 2px;
  }
}
@container (max-width: 340px) {
  .ui-apc__pending > .ui-apc__card { padding: 14px; }
  .ui-apc__details { column-gap: 12px; }
}
@keyframes ui-apc-in {
  from { opacity: 0; transform: translateY(4px); filter: blur(2px); }
  to { opacity: 1; transform: none; filter: none; }
}

@media (prefers-reduced-motion: reduce) {
  .ui-apc,
  .ui-apc *,
  .ui-apc *::before,
  .ui-apc *::after {
    animation-duration: 1ms !important;
    animation-delay: 0ms !important;
    transition-duration: 1ms !important;
  }
}
:where(.dark, [data-theme="dark"]) .ui-apc {
  --ui-apc-tray: var(--aui-subtle, #111113);
  --ui-apc-bg: var(--aui-surface, #19191b);
  --ui-apc-ink: var(--aui-ink, #ededed);
  --ui-apc-text: var(--aui-muted, #a1a1a1);
  --ui-apc-muted: var(--aui-muted, #8b8b92);
  --ui-apc-line: var(--aui-border, #2a2a2e);
  --ui-apc-soft: #1f1f22;
  --ui-apc-tile: #1f1f22;
  --ui-apc-hover: #222225;
  --ui-apc-primary: var(--aui-primary, #ededed);
  --ui-apc-primary-hover: #ffffff;
  --ui-apc-primary-ink: var(--aui-on-primary, #19191b);
  --ui-apc-primary-kbd: rgba(0, 0, 0, 0.08);
  --ui-apc-primary-kbd-ink: rgba(25, 25, 27, 0.6);
  --ui-apc-kbd: rgba(255, 255, 255, 0.07);
  --ui-apc-box: var(--aui-border-strong, rgba(255, 255, 255, 0.2));
  --ui-apc-box-hover: rgba(255, 255, 255, 0.32);
  --ui-apc-focus: var(--aui-focus, rgba(77, 141, 255, 0.8));
  --ui-apc-timer-low: var(--aui-amber, #e6c24d);
  --ui-apc-low-bg: rgba(255, 255, 255, 0.07);
  --ui-apc-low-ink: #a1a1a1;
  --ui-apc-med-bg: color-mix(in srgb, var(--aui-amber, #e6c24d) 12%, transparent);
  --ui-apc-med-ink: var(--aui-amber, #e6c24d);
  --ui-apc-high-bg: color-mix(in srgb, var(--aui-red, #ff6b5f) 12%, transparent);
  --ui-apc-high-ink: var(--aui-danger, #ff8a7a);
  --ui-apc-ok-bg: color-mix(in srgb, var(--aui-green, #7dcf9f) 13%, transparent);
  --ui-apc-ok-ink: var(--aui-green, #5fc88a);
  --ui-apc-no-bg: rgba(255, 255, 255, 0.07);
  --ui-apc-no-ink: #a1a1a1;
}
`;

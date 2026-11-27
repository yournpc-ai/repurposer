"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { CircleCheck, X } from "@/components/ui/icons"

import { Button } from "@/components/ui/button-clean"
import { Spinner } from "@/components/ui/spinner-clean"
import { apiFetch, WALLET_REFRESH_EVENT } from "@/lib/api"
import { formatMoney } from "@/lib/payments"
import { useSettingsDialog } from "@/components/settings/settings-dialog-context"
import {
  formatCredits,
  SpendTableRow,
  TopupTableRow,
  type WalletTransaction,
} from "@/components/credits/tx-row"

/** Credits management seat: real balance, a top-up dialog entry, inline
 * Checkout confirmation banners, and independently paginated semantic ledgers.
 * Order polling itself runs globally in SettingsDialogProvider so closing
 * Settings never drops a pending payment check. */

interface WalletState {
  balance: number
  held: number
}

interface WalletTransactionsPage {
  items: WalletTransaction[]
  next_cursor: string | null
  total?: number | null
}

type TransactionDirection = "in" | "out"

interface TransactionPageState {
  items: WalletTransaction[] | null
  nextCursor: string | null
  total: number | null
  history: (string | null)[]
  loading: boolean
}

const PAGE_SIZE = 10

function useTransactionPage(direction: TransactionDirection) {
  const request = useRef(0)
  const [state, setState] = useState<TransactionPageState>({
    items: null,
    nextCursor: null,
    total: null,
    history: [null],
    loading: true,
  })

  const load = useCallback(
    async (cursor: string | null, history: (string | null)[]) => {
      const requestId = ++request.current
      setState((current) => ({ ...current, loading: true }))
      const fail = () => {
        if (requestId === request.current) {
          setState((current) => ({ ...current, loading: false }))
        }
      }
      try {
        const params = new URLSearchParams({
          limit: String(PAGE_SIZE),
          direction,
        })
        if (cursor) params.set("cursor", cursor)
        const res = await apiFetch(`/api/v1/wallet/transactions?${params}`, {
          toast: false,
        })
        if (!res.ok) {
          fail()
          return
        }
        const data = (await res.json()) as WalletTransactionsPage
        if (requestId !== request.current) return
        setState({
          items: data.items,
          nextCursor: data.next_cursor,
          total: data.total ?? null,
          history,
          loading: false,
        })
      } catch {
        fail()
      }
    },
    [direction],
  )

  useEffect(() => {
    void load(null, [null])
    return () => {
      request.current += 1
    }
  }, [load])

  const reload = useCallback(() => load(null, [null]), [load])
  const next = () => {
    if (!state.nextCursor || state.loading) return
    void load(state.nextCursor, [...state.history, state.nextCursor])
  }
  const previous = () => {
    if (state.history.length <= 1 || state.loading) return
    const history = state.history.slice(0, -1)
    void load(history[history.length - 1] ?? null, history)
  }

  return {
    ...state,
    page: state.history.length,
    reload,
    next,
    previous,
  }
}

function TablePagination({
  page,
  total,
  loading,
  hasPrevious,
  hasNext,
  onPrevious,
  onNext,
}: {
  page: number
  total: number | null
  loading: boolean
  hasPrevious: boolean
  hasNext: boolean
  onPrevious: () => void
  onNext: () => void
}) {
  const { t } = useTranslation()
  const pages = total === null ? null : Math.max(1, Math.ceil(total / PAGE_SIZE))
  if (!hasPrevious && !hasNext) return null
  return (
    <div className="mt-3 flex items-center justify-end gap-2">
      <span className="mr-1 text-xs text-muted-foreground tabular-nums">
        {pages === null ? page : t("credits.page", { page, pages })}
      </span>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={loading || !hasPrevious}
        onClick={onPrevious}
      >
        {t("common.previous")}
      </Button>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={loading || !hasNext}
        onClick={onNext}
      >
        {t("common.next")}
      </Button>
    </div>
  )
}

export function CreditsSection() {
  const { t, i18n } = useTranslation()
  const {
    checkoutState,
    retryCheckoutCheck,
    dismissCheckoutState,
    openCreditTopup,
  } = useSettingsDialog()
  const [wallet, setWallet] = useState<WalletState | null>(null)
  const topupPage = useTransactionPage("in")
  const spendPage = useTransactionPage("out")
  const reloadTopups = topupPage.reload

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch("/api/v1/wallet", { toast: false })
      if (res.ok) setWallet((await res.json()) as WalletState)
    } catch {
      /* silent — the overview keeps its last value */
    }
  }, [])

  useEffect(() => {
    void refresh()
    const onWalletRefresh = () => {
      void refresh()
      void reloadTopups()
    }
    window.addEventListener(WALLET_REFRESH_EVENT, onWalletRefresh)
    return () => window.removeEventListener(WALLET_REFRESH_EVENT, onWalletRefresh)
  }, [refresh, reloadTopups])

  const settingsBanner =
    checkoutState?.surface === "settings" ? checkoutState : null
  const orderSummary =
    settingsBanner?.order != null
      ? `${formatMoney(settingsBanner.order.amount_minor, settingsBanner.order.currency, i18n.language)} · +${t("credits.packageCredits", {
          count: formatCredits(settingsBanner.order.credits, i18n.language),
        })}`
      : null

  return (
    <div className="min-w-0 space-y-6">
      {settingsBanner && (
        <div
          className="flex items-center gap-2.5 rounded-lg border border-subtle bg-muted px-3.5 py-2.5"
          role="status"
        >
          {settingsBanner.phase === "confirming" && <Spinner size={14} />}
          {settingsBanner.phase === "paid" && (
            <CircleCheck className="size-4 shrink-0 text-foreground" strokeWidth={1.75} />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium leading-relaxed text-foreground">
              {settingsBanner.phase === "paid"
                ? t("credits.topupSuccess", {
                    count: formatCredits(settingsBanner.order?.credits ?? 0, i18n.language),
                  })
                : t(`credits.return.${settingsBanner.phase}`)}
            </p>
            {settingsBanner.phase !== "paid" && orderSummary && (
              <p className="text-xs text-muted-foreground tabular-nums">
                {orderSummary}
              </p>
            )}
          </div>
          {settingsBanner.phase === "pending" && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={retryCheckoutCheck}
            >
              {t("credits.checkAgain")}
            </Button>
          )}
          {settingsBanner.phase === "paid" && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={t("common.close")}
              icon={<X size={14} />}
              onClick={dismissCheckoutState}
            />
          )}
        </div>
      )}

        <section className="min-w-0">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm text-muted-foreground">{t("credits.available")}</p>
              <p className="mt-1 text-2xl font-semibold tabular-nums">
                {wallet ? formatCredits(wallet.balance, i18n.language) : "—"}
              </p>
              {wallet != null && wallet.held > 0 && (
                <p className="mt-2 text-xs text-muted-foreground">
                  {t("credits.held")} · {formatCredits(wallet.held, i18n.language)}
                </p>
              )}
            </div>
            <Button
              type="button"
              size="sm"
              onClick={() => openCreditTopup()}
            >
              {t("credits.buyTitle")}
            </Button>
          </div>
          {wallet != null && wallet.balance < 0 && (
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {t("credits.negativeNote")}
            </p>
          )}
        </section>

        <section className="min-w-0 scroll-mt-4 border-t border-subtle pt-5">
          <h4 className="text-sm font-semibold">{t("credits.topups")}</h4>
          <div
            role="region"
            tabIndex={0}
            aria-label={t("credits.topups")}
            className="mx-auto mt-3 w-full max-w-full min-w-0 overflow-x-auto rounded-lg border border-subtle thin-scroll"
          >
            <table className="w-full min-w-max">
              <caption className="sr-only">{t("credits.topups")}</caption>
              <thead className="bg-muted">
                <tr className="border-b border-subtle">
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.type")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-44 px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.orderId")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-40 px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.paidAt")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-28 px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.provider")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-28 px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.paymentAmount")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-32 px-4 text-right text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.receivedCredits")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-24 px-4 text-right text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.status")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {topupPage.items === null ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-8 text-center text-xs text-muted-foreground"
                    >
                      …
                    </td>
                  </tr>
                ) : topupPage.items.length === 0 ? (
                  <tr>
                    <td
                      colSpan={7}
                      className="px-4 py-8 text-center text-xs text-muted-foreground"
                    >
                      {t("credits.tx.topupEmpty")}
                    </td>
                  </tr>
                ) : (
                  topupPage.items.map((item) => (
                    <TopupTableRow key={item.id} item={item} />
                  ))
                )}
              </tbody>
            </table>
          </div>
          <TablePagination
            page={topupPage.page}
            total={topupPage.total}
            loading={topupPage.loading}
            hasPrevious={topupPage.page > 1}
            hasNext={topupPage.nextCursor !== null}
            onPrevious={topupPage.previous}
            onNext={topupPage.next}
          />
        </section>

        <section className="min-w-0 border-t border-subtle pt-5">
          <h4 className="text-sm font-semibold">{t("credits.spending")}</h4>
          <div
            role="region"
            tabIndex={0}
            aria-label={t("credits.spending")}
            className="mx-auto mt-3 w-full max-w-full min-w-0 overflow-x-auto rounded-lg border border-subtle thin-scroll"
          >
            <table className="w-full min-w-max">
              <caption className="sr-only">{t("credits.spending")}</caption>
              <thead className="bg-muted">
                <tr className="border-b border-subtle">
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-40 px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.reference")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.creation")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-44 px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.outputs")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-36 px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.project")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-40 px-4 text-left text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.spentAt")}
                  </th>
                  <th
                    scope="col"
                    className="h-10 whitespace-nowrap w-32 px-4 text-right text-xs font-medium text-muted-foreground"
                  >
                    {t("credits.tx.amount")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {spendPage.items === null ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-8 text-center text-xs text-muted-foreground"
                    >
                      …
                    </td>
                  </tr>
                ) : spendPage.items.length === 0 ? (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-8 text-center text-xs text-muted-foreground"
                    >
                      {t("credits.tx.spendEmpty")}
                    </td>
                  </tr>
                ) : (
                  spendPage.items.map((item) => (
                    <SpendTableRow key={item.id} item={item} />
                  ))
                )}
              </tbody>
            </table>
          </div>
          <TablePagination
            page={spendPage.page}
            total={spendPage.total}
            loading={spendPage.loading}
            hasPrevious={spendPage.page > 1}
            hasNext={spendPage.nextCursor !== null}
            onPrevious={spendPage.previous}
            onNext={spendPage.next}
          />
        </section>
      </div>
  )
}

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, RotateCcw, Save } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "@/components/ui/sonner";
import { apiError, endpoints } from "@/lib/api";
import { money, num } from "@/lib/format";

export const FIELD_LABELS = {
  tokens_per_report_credit: "Tokens per report credit",
  vendor_credits_per_dollar: "Vendor credits per $1.00",
  input_tokens_per_vendor_credit: "Input tokens per vendor credit",
  output_tokens_per_vendor_credit: "Output tokens per vendor credit",
  agent_runs_per_month: "Agent runs per month",
  output_token_share: "Output share of waste (0 to 1)",
  variance_pct: "Variance for the low/high range (0 to 0.9)",
};

export const AssumptionsEditor = ({ onSaved, compactMode = false }) => {
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [suggestion, setSuggestion] = useState(null);

  const load = () => {
    endpoints
      .settings()
      .then((res) => {
        setSettings(res.data);
        const a = res.data.assumptions || {};
        setForm(
          Object.keys(FIELD_LABELS).reduce((acc, k) => {
            acc[k] = a[k];
            return acc;
          }, {}),
        );
      })
      .catch((err) => toast.error(apiError(err, "Could not load assumptions")));
  };

  useEffect(load, []);

  const save = async () => {
    setSaving(true);
    try {
      const res = await endpoints.saveSettings({ assumptions: form });
      setSettings(res.data);
      toast.success("Savings assumptions saved. New scans will use these numbers.");
      if (onSaved) onSaved(res.data);
    } catch (err) {
      toast.error(apiError(err, "Could not save assumptions"));
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    try {
      const res = await endpoints.resetAssumptions();
      setSettings(res.data);
      const a = res.data.assumptions || {};
      setForm(
        Object.keys(FIELD_LABELS).reduce((acc, k) => {
          acc[k] = a[k];
          return acc;
        }, {}),
      );
      toast.success("Assumptions reset to defaults");
    } catch (err) {
      toast.error(apiError(err, "Could not reset assumptions"));
    }
  };

  const refresh = async () => {
    setRefreshing(true);
    setSuggestion(null);
    try {
      const res = await endpoints.refreshRates();
      setSuggestion(res.data);
      toast.success("Fetched suggested rates. Review them before applying.");
    } catch (err) {
      toast.error(apiError(err, "Could not refresh rates"));
    } finally {
      setRefreshing(false);
    }
  };

  const applySuggestion = async () => {
    if (!suggestion) return;
    const patch = {
      ...form,
      input_tokens_per_vendor_credit: suggestion.suggested.input_tokens_per_vendor_credit,
      output_tokens_per_vendor_credit: suggestion.suggested.output_tokens_per_vendor_credit,
      vendor_credits_per_dollar: suggestion.suggested.vendor_credits_per_dollar,
      rates_last_refreshed: suggestion.fetched_at,
      rates_source: suggestion.provenance,
    };
    setSaving(true);
    try {
      const res = await endpoints.saveSettings({ assumptions: patch });
      setSettings(res.data);
      setForm(
        Object.keys(FIELD_LABELS).reduce((acc, k) => {
          acc[k] = res.data.assumptions[k];
          return acc;
        }, {}),
      );
      setSuggestion(null);
      toast.success("Suggested rates applied");
      if (onSaved) onSaved(res.data);
    } catch (err) {
      toast.error(apiError(err, "Could not apply rates"));
    } finally {
      setSaving(false);
    }
  };

  const a = settings?.assumptions || {};

  return (
    <Card
      data-testid="savings-assumptions"
      className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-heading text-lg font-bold">Savings assumptions</h3>
          <p className="text-xs text-muted-foreground">
            Every number in the report comes from these settings. Change them and re-run a scan to see
            updated savings.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={refresh}
            disabled={refreshing}
            data-testid="settings-refresh-rates-button"
          >
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            {refreshing ? "Checking rates" : "Refresh rates"}
          </Button>
          <Button variant="secondary" size="sm" onClick={reset} data-testid="assumptions-reset-button">
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" /> Reset
          </Button>
          <Button size="sm" onClick={save} disabled={saving} data-testid="assumptions-save-button">
            <Save className="mr-1.5 h-3.5 w-3.5" /> {saving ? "Saving" : "Save"}
          </Button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(FIELD_LABELS).map(([key, label]) => (
          <div key={key}>
            <Label htmlFor={`assumption-${key}`} className="text-xs">
              {label}
            </Label>
            <Input
              id={`assumption-${key}`}
              data-testid={`assumption-input-${key}`}
              type="number"
              step="any"
              className="mt-1 h-9"
              value={form[key] ?? ""}
              onChange={(e) =>
                setForm({ ...form, [key]: e.target.value === "" ? "" : Number(e.target.value) })
              }
            />
          </div>
        ))}
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <div className="rounded-xl border border-border bg-secondary p-3">
          <p className="text-[11px] uppercase text-muted-foreground">Derived input price</p>
          <p className="num font-heading text-lg font-bold">
            {money(a.input_dollars_per_million)} per 1M tokens
          </p>
          <p className="text-[11px] text-muted-foreground">
            1,000,000 / ({num(a.input_tokens_per_vendor_credit)} tokens per credit &times;{" "}
            {num(a.vendor_credits_per_dollar)} credits per $1.00)
          </p>
        </div>
        <div className="rounded-xl border border-border bg-secondary p-3">
          <p className="text-[11px] uppercase text-muted-foreground">Derived output price</p>
          <p className="num font-heading text-lg font-bold">
            {money(a.output_dollars_per_million)} per 1M tokens
          </p>
          <p className="text-[11px] text-muted-foreground">
            Output costs {(a.input_tokens_per_vendor_credit / a.output_tokens_per_vendor_credit || 0).toFixed(1)}
            &times; input at these settings
          </p>
        </div>
      </div>

      <div className="mt-3 rounded-xl border border-border bg-secondary p-3">
        <p className="text-xs font-semibold">Rate provenance</p>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          Last refreshed: {a.rates_last_refreshed ? new Date(a.rates_last_refreshed).toLocaleString() : "never"}
          <br />
          {a.rates_source || "Product owner supplied defaults"}
        </p>
      </div>

      {suggestion ? (
        <div className="alert alert-info mt-3" data-testid="rate-suggestion">
          <p className="text-sm font-bold">Suggested rates (not applied yet)</p>
          <p className="num mt-1 text-sm">
            {money(suggestion.suggested.input_dollars_per_million)} per 1M input tokens &middot;{" "}
            {money(suggestion.suggested.output_dollars_per_million)} per 1M output tokens
          </p>
          <p className="mt-1 text-xs leading-5 opacity-90">
            As of {suggestion.as_of || "unknown"} &middot; confidence {suggestion.confidence || "unknown"}
            <br />
            {suggestion.source ? `Source: ${suggestion.source}. ` : ""}
            {suggestion.provenance}
          </p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={applySuggestion} data-testid="rate-suggestion-apply-button">
              Apply these rates
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setSuggestion(null)}>
              Dismiss
            </Button>
          </div>
        </div>
      ) : null}

      {!compactMode ? (
        <p className="mt-3 text-xs text-muted-foreground">
          Looking for the model and API key settings?{" "}
          <Link to="/settings" className="text-primary underline">
            Open Settings
          </Link>
          .
        </p>
      ) : null}
    </Card>
  );
};

export const AssumptionsReadout = ({ assumptions }) => (
  <Card
    data-testid="savings-assumptions-readout"
    className="rounded-xl border border-border bg-card p-4 shadow-[var(--shadow-md)]"
  >
    <h3 className="font-heading text-lg font-bold">How these numbers were worked out</h3>
    <div className="accent-rule mt-2" />
    <ul className="mt-3 space-y-2">
      {(assumptions?.notes || []).map((note, i) => (
        <li key={i} className="flex gap-2 text-sm leading-6">
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
          <span>{note}</span>
        </li>
      ))}
    </ul>
    <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
      {[
        ["Tokens per report credit", num(assumptions?.tokens_per_report_credit)],
        ["$ per 1M input tokens", money(assumptions?.input_dollars_per_million)],
        ["$ per 1M output tokens", money(assumptions?.output_dollars_per_million)],
        ["Agent runs per month", num(assumptions?.agent_runs_per_month)],
      ].map(([label, value]) => (
        <div key={label} className="rounded-xl border border-border bg-secondary p-3">
          <p className="text-[11px] uppercase text-muted-foreground">{label}</p>
          <p className="num font-heading text-base font-bold">{value}</p>
        </div>
      ))}
    </div>
  </Card>
);

export default AssumptionsEditor;
